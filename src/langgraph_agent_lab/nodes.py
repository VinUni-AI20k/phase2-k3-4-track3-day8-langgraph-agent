"""Node functions for support-ticket workflow."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


class Classification(BaseModel):
    """Structured intent returned by classifier."""

    route: str = Field(description="simple, tool, missing_info, risky, or error")
    risk_level: str = Field(default="low")


def intake_node(state: AgentState) -> dict[str, Any]:
    """Normalize raw query."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict[str, Any]:
    """Classify query with structured LLM output."""
    llm = get_llm().with_structured_output(Classification)
    prompt = (
        "Classify support request. Priority: risky side effects (refund, delete, cancel, email); "
        "tool lookups; missing vague context; error/system failures; simple questions. "
        f"Return only schema. Query: {state.get('query', '')}"
    )
    result = llm.invoke(prompt)
    route = (
        result.route
        if result.route in {"simple", "tool", "missing_info", "risky", "error"}
        else "simple"
    )
    risk = "high" if route == "risky" else "low"
    return {
        "route": route,
        "risk_level": result.risk_level or risk,
        "events": [make_event("classify", "completed", "intent classified", route=route)],
    }


def tool_node(state: AgentState) -> dict[str, Any]:
    """Execute deterministic mock tool, including transient error simulation."""
    attempt = state.get("attempt", 0)
    is_error = state.get("route") == "error" and attempt < 2
    result = (
        f"ERROR: transient tool failure on attempt {attempt + 1}"
        if is_error
        else f"Tool result for: {state.get('query', '')}"
    )
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", "tool executed", attempt=attempt)],
    }


def evaluate_node(state: AgentState) -> dict[str, Any]:
    """Evaluate latest tool result as retry gate."""
    latest = (
        state.get("tool_results", [])[-1]
        if state.get("tool_results")
        else "ERROR: missing tool result"
    )
    evaluation = "needs_retry" if "ERROR" in latest else "success"
    return {
        "evaluation_result": evaluation,
        "events": [make_event("evaluate", "completed", "tool result evaluated", result=evaluation)],
    }


def answer_node(state: AgentState) -> dict[str, Any]:
    """Generate grounded answer with LLM."""
    context = "\n".join(state.get("tool_results", [])) or "No tool result."
    approval = state.get("approval") or {}
    prompt = (
        "Answer support request. Ground answer only in query and supplied context; "
        "do not invent facts. "
        f"Query: {state.get('query', '')}\nContext: {context}\nApproval: {approval}"
    )
    response = get_llm().invoke(prompt)
    content = getattr(response, "content", str(response))
    return {
        "final_answer": str(content),
        "events": [make_event("answer", "completed", "grounded answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict[str, Any]:
    """Request missing actionable detail."""
    question = f"Please provide more detail so we can act on: {state.get('query', '')}"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict[str, Any]:
    """Prepare side-effecting action for approval."""
    action = f"Proposed action: {state.get('query', '')}"
    return {
        "proposed_action": action,
        "events": [make_event("risky_action", "completed", "action prepared")],
    }


def approval_node(state: AgentState) -> dict[str, Any]:
    """Apply mock approval, or interrupt when explicitly enabled."""
    approved = True
    if os.getenv("LANGGRAPH_INTERRUPT", "false").lower() == "true":
        from langgraph.types import interrupt

        decision = interrupt({"proposed_action": state.get("proposed_action", "")})
        approved = (
            bool(decision.get("approved", False)) if isinstance(decision, dict) else bool(decision)
        )
    approval = {
        "approved": approved,
        "reviewer": "mock-reviewer",
        "comment": "approved by default" if approved else "rejected",
    }
    return {
        "approval": approval,
        "events": [make_event("approval", "completed", "approval recorded", approved=approved)],
    }


def retry_or_fallback_node(state: AgentState) -> dict[str, Any]:
    """Increment retry attempt and record failure."""
    attempt = state.get("attempt", 0) + 1
    return {
        "attempt": attempt,
        "errors": [f"retry attempt {attempt}"],
        "events": [make_event("retry", "completed", "retry scheduled", attempt=attempt)],
    }


def dead_letter_node(state: AgentState) -> dict[str, Any]:
    """Terminate exhausted retry path with escalation response."""
    answer = "Unable to complete request after retry limit; support escalation required."
    return {
        "final_answer": answer,
        "events": [
            make_event(
                "dead_letter", "completed", "request escalated", attempts=state.get("attempt", 0)
            )
        ],
    }


def finalize_node(state: AgentState) -> dict[str, Any]:
    """Emit terminal audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
