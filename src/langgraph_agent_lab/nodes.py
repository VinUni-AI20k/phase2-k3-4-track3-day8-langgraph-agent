"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

from .state import AgentState, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── TODO(student): implement ALL nodes below ────────────────────────


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM."""
    from .llm import get_llm
    from pydantic import BaseModel

    class Classification(BaseModel):
        route: str
        reason: str

    llm = get_llm()
    structured_llm = llm.with_structured_output(Classification)

    query = state.get("query", "")

    prompt = f"""Classify this support query into one of these routes:
- "simple": General questions answerable without tools or actions
- "tool": Information lookups: order status, tracking, search queries
- "missing_info": Vague/incomplete queries lacking actionable context
- "risky": Actions with side effects: refunds, deletions, sending emails, cancellations
- "error": System failures: timeouts, crashes, service unavailable

Query: {query}

Return the route and a brief reason."""

    result = structured_llm.invoke(prompt)
    route = result.route if result.route else "simple"
    risk_level = "high" if route == "risky" else "low"

    return {
        "route": route,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"classified as {route}: {result.reason}")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Simulate transient failures for error-route scenarios to test retry loops.

    - If route is "error" and attempt < 2: return error result
    - Otherwise: return a mock success result string
    """
    route = state.get("route", "")
    attempt = state.get("attempt", 0)

    # Simulate transient failure for error route (first 2 attempts fail)
    if route == "error" and attempt < 2:
        result = f"ERROR: Transient failure on attempt {attempt + 1}"
    else:
        # Mock successful tool execution
        scenario_id = state.get("scenario_id", "unknown")
        if route == "tool":
            result = f"Order status for {scenario_id}: Processing complete"
        elif route == "risky":
            result = f"Action prepared for {scenario_id}: Ready for approval"
        else:
            result = f"Tool executed successfully for {scenario_id}"

    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", result)],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Heuristic: check for "ERROR" substring in the latest tool result.
    For bonus: use LLM-as-judge.
    """
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""

    # Heuristic: if result contains ERROR, needs retry
    if "ERROR" in latest_result:
        evaluation_result = "needs_retry"
    else:
        evaluation_result = "success"

    return {
        "evaluation_result": evaluation_result,
        "events": [make_event("evaluate", "completed", f"evaluation: {evaluation_result}")],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM."""
    from .llm import get_llm

    llm = get_llm(temperature=0.7)

    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")

    # Build context from available information
    context_parts = []
    if tool_results:
        context_parts.append(f"Tool results: {', '.join(tool_results)}")
    if approval:
        status = "approved" if approval.get("approved") else "rejected"
        context_parts.append(f"Approval status: {status}")

    context = "\n".join(context_parts) if context_parts else "No additional context"

    prompt = f"""You are a helpful support agent. Generate a friendly, informative response.

Original query: {query}

{context}

Provide a helpful response that addresses the user's query based on the available information."""

    final_answer = llm.invoke(prompt).content

    return {
        "final_answer": final_answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Generate a specific clarification question based on the vague/incomplete query.
    """
    from .llm import get_llm

    llm = get_llm(temperature=0.7)

    query = state.get("query", "")

    prompt = f"""The following support query is too vague or incomplete to answer directly.
Generate ONE specific question to ask the user to clarify what they need.

Query: {query}

Return a single, specific clarification question."""

    pending_question = llm.invoke(prompt).content

    return {
        "pending_question": pending_question,
        "final_answer": None,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval.

    Describe the proposed action and why it requires approval.
    """
    from .llm import get_llm

    llm = get_llm(temperature=0.3)

    query = state.get("query", "")

    prompt = f"""The following request contains a risky action that requires human approval.
Identify the specific action and explain why it needs review.

Request: {query}

Return a description of the proposed action and why approval is needed."""

    proposed_action = llm.invoke(prompt).content

    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", "action prepared for approval")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default behavior: mock approval (approved=True) so tests and CI run offline.
    Extension: if env LANGGRAPH_INTERRUPT=true, use langgraph.types.interrupt() for real HITL.
    """
    import os
    from .state import ApprovalDecision

    # Check for real HITL mode
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        interrupt("Approval required for risky action")

    # Mock approval for testing
    proposed_action = state.get("proposed_action", "")
    approval = ApprovalDecision(
        approved=True,
        reviewer="mock-reviewer",
        comment="Auto-approved for testing",
    )

    return {
        "approval": approval.model_dump(),
        "events": [make_event("approval", "completed", f"action {approval.comment}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt.

    Increment the attempt counter and log the transient failure.
    """
    attempt = state.get("attempt", 0) + 1
    route = state.get("route", "")
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else "Unknown error"

    error_msg = f"Retry {attempt}: {latest_result}"

    return {
        "attempt": attempt,
        "errors": [error_msg],
        "events": [make_event("retry", "completed", error_msg)],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded.

    This is the third layer: retry → fallback → dead letter.
    Log the failure and set a final_answer explaining that the request could not be completed.
    """
    scenario_id = state.get("scenario_id", "unknown")
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    errors = state.get("errors", [])

    final_answer = (
        f"I apologize, but I was unable to complete your request (scenario: {scenario_id}). "
        f"After {attempt} attempts (max: {max_attempts}), the system could not process "
        f"your request successfully. The errors encountered were: {'; '.join(errors)}. "
        f"Please contact support for further assistance."
    )

    return {
        "final_answer": final_answer,
        "events": [make_event("dead_letter", "completed", "max retries exceeded")],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
