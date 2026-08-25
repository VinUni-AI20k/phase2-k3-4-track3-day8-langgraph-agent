"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, Route, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict[str, Any]:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── Pydantic Schema for Structured LLM Classification ───────────────
class IntentClassification(BaseModel):
    """Structured output schema for intent classification."""

    route: Route = Field(
        description=(
            "Exact route category: "
            "'risky' (actions with side-effects: refunds, deletions, cancellations), "
            "'tool' (lookups, order status, database checks), "
            "'missing_info' (vague, ambiguous, or incomplete queries), "
            "'error' (system failures, timeout reports, crash errors), "
            "'simple' (general FAQ questions answerable without tools)."
        )
    )
    risk_level: str = Field(
        default="low",
        description="'high' for risky actions (refunds, deletions, cancellations), 'low' otherwise",
    )
    reasoning: str = Field(
        default="",
        description="Brief reasoning explaining the route choice",
    )


# ─── Phase 1: Node Implementations ────────────────────────────────────


def classify_node(state: AgentState) -> dict[str, Any]:
    """Classify the query into a route using an LLM with structured output.

    Uses .with_structured_output() to get reliable enum classification.
    Priority order: risky > tool > missing_info > error > simple.
    """
    query = state.get("query", "").strip()
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(IntentClassification)

    prompt = (
        "You are an intent classification system for an enterprise customer support agent.\n"
        "Classify the user query into exactly one of the following route categories:\n\n"
        "- 'risky': Actions with critical side-effects, modifying user data, or performing "
        "financial transactions/deletions (e.g. 'Refund customer', 'Delete account').\n"
        "- 'tool': Queries requiring data lookup or retrieval without side-effects "
        "(e.g. 'lookup order status for order 12345').\n"
        "- 'missing_info': Queries that are too vague, ambiguous, or lack required details "
        "to take action (e.g. 'Can you fix it?').\n"
        "- 'error': Inquiries reporting explicit system errors, timeout failures, or technical "
        "service disruptions (e.g. 'Timeout failure while processing request', 'System failure').\n"
        "- 'simple': General FAQ inquiries that can be answered directly without tool lookup "
        "(e.g. 'How do I reset my password?').\n\n"
        "Classification priority: risky > tool > missing_info > error > simple.\n\n"
        f"Customer query: {query}"
    )

    result = structured_llm.invoke(prompt)

    # Extract route and risk level cleanly
    if isinstance(result, IntentClassification):
        route_val = result.route.value if hasattr(result.route, "value") else str(result.route)
        risk_level = (
            "high"
            if (route_val == Route.RISKY.value or result.risk_level == "high")
            else "low"
        )
        reasoning = result.reasoning
    else:
        # Fallback if structured dict is returned
        route_val = str(getattr(result, "route", "simple"))
        risk_level = "high" if route_val == "risky" else "low"
        reasoning = str(getattr(result, "reasoning", ""))

    return {
        "route": route_val,
        "risk_level": risk_level,
        "events": [
            make_event(
                "classify",
                "completed",
                f"classified as {route_val}",
                reasoning=reasoning,
                risk_level=risk_level,
            )
        ],
    }


def tool_node(state: AgentState) -> dict[str, Any]:
    """Execute a mock tool call with simulated transient failures for retry testing.

    Requirements:
    - If route is 'error' and attempt < 2: return error result containing 'ERROR'.
    - Otherwise: return a mock success result string.
    - Append result to tool_results list.
    """
    route = state.get("route", "")
    attempt = state.get("attempt", 0)
    query = state.get("query", "")

    if route == Route.ERROR.value and attempt < 2:
        result_str = f"ERROR: Transient service timeout on attempt {attempt} for query: {query}"
    else:
        result_str = f"SUCCESS: Tool retrieved valid data for query: '{query}'"

    return {
        "tool_results": [result_str],
        "events": [make_event("tool", "completed", result_str, attempt=attempt)],
    }


def evaluate_node(state: AgentState) -> dict[str, Any]:
    """Evaluate tool results — the retry-loop gate.

    Checks whether the latest tool result is satisfactory or needs retry.
    Sets evaluation_result to 'needs_retry' or 'success'.
    """
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""

    if "ERROR" in latest_result:
        eval_result = "needs_retry"
        message = f"Evaluation failed: {latest_result}"
    else:
        eval_result = "success"
        message = "Evaluation passed: tool output verified"

    return {
        "evaluation_result": eval_result,
        "events": [make_event("evaluate", "completed", message, result=eval_result)],
    }


def answer_node(state: AgentState) -> dict[str, Any]:
    """Generate a final grounded response using an LLM.

    The response is grounded in available context (tool_results, approval decision, query).
    """
    query = state.get("query", "").strip()
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")
    context_parts: list[str] = []

    if tool_results:
        context_parts.append("Tool Information:\n" + "\n".join(tool_results))
    if approval:
        context_parts.append(f"Security Approval Decision: {approval}")

    context_str = "\n\n".join(context_parts) if context_parts else "No external tools required."

    llm = get_llm(temperature=0.0)
    prompt = (
        "You are an enterprise support assistant. Provide a helpful, clear response.\n"
        "Ground your answer strictly in the available context below whenever relevant.\n\n"
        f"Context:\n{context_str}\n\n"
        f"Customer Query: {query}\n\n"
        "Response:"
    )

    response = llm.invoke(prompt)
    answer_text = response.content if hasattr(response, "content") else str(response)
    if isinstance(answer_text, list):
        answer_text = "".join(str(block) for block in answer_text)

    return {
        "final_answer": str(answer_text).strip(),
        "events": [make_event("answer", "completed", "grounded response generated")],
    }


def ask_clarification_node(state: AgentState) -> dict[str, Any]:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "").strip()
    clarification_msg = (
        f"Could you please provide additional details? Your request '{query}' is missing key "
        "information such as account identifier, order number, or specific error message."
    )

    return {
        "pending_question": clarification_msg,
        "final_answer": clarification_msg,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict[str, Any]:
    """Prepare a risky action for human approval."""
    query = state.get("query", "").strip()
    action_desc = (
        f"Proposed Action: Execute sensitive operation for '{query}'. "
        "Requires human supervisor review and confirmation before execution."
    )

    return {
        "proposed_action": action_desc,
        "events": [make_event("risky_action", "completed", action_desc)],
    }


def approval_node(state: AgentState) -> dict[str, Any]:
    """Human-in-the-loop approval step.

    Default: Mock approval (approved=True).
    Extension: If LANGGRAPH_INTERRUPT=true, trigger interrupt().
    """
    if os.getenv("LANGGRAPH_INTERRUPT", "false").lower() in ("true", "1"):
        try:
            from langgraph.types import interrupt

            decision = interrupt({"proposed_action": state.get("proposed_action")})
            if not isinstance(decision, dict):
                decision = {
                    "approved": bool(decision),
                    "reviewer": "human-reviewer",
                    "comment": "Via interrupt",
                }
        except ImportError:
            decision = {
                "approved": True,
                "reviewer": "mock-reviewer",
                "comment": "Approved (mock)",
            }
    else:
        decision = {
            "approved": True,
            "reviewer": "security-supervisor",
            "comment": "Approved automatically under mock policy",
        }

    return {
        "approval": decision,
        "events": [make_event("approval", "completed", "approval processed", **decision)],
    }


def retry_or_fallback_node(state: AgentState) -> dict[str, Any]:
    """Record a retry attempt and log transient failure."""
    current_attempt = state.get("attempt", 0)
    new_attempt = current_attempt + 1
    max_attempts = state.get("max_attempts", 3)
    error_msg = f"Transient failure recorded. Attempt {new_attempt} of {max_attempts}."

    return {
        "attempt": new_attempt,
        "errors": [error_msg],
        "events": [make_event("retry", "completed", f"attempt incremented to {new_attempt}")],
    }


def dead_letter_node(state: AgentState) -> dict[str, Any]:
    """Handle unresolvable failures after max retries exceeded."""
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    dead_letter_msg = (
        f"We apologize, but your request could not be processed after {attempt}/{max_attempts} "
        "attempts due to persistent system errors. This ticket has been escalated."
    )

    return {
        "final_answer": dead_letter_msg,
        "events": [make_event("dead_letter", "completed", "max retries reached, escalated")],
    }


def finalize_node(state: AgentState) -> dict[str, Any]:
    """Emit a final audit event. All routes pass through here before END."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }
