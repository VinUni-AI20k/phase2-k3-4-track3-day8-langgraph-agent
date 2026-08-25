"""Routing functions for conditional graph edges."""

from __future__ import annotations

from .state import AgentState

_CLASSIFY_TARGETS = {
    "simple": "answer",
    "tool": "tool",
    "missing_info": "clarify",
    "risky": "risky_action",
    "error": "retry",
}


def route_after_classify(state: AgentState) -> str:
    """Select first node from classified route."""
    return _CLASSIFY_TARGETS.get(state.get("route", ""), "answer")


def route_after_evaluate(state: AgentState) -> str:
    """Send failed tool result to bounded retry path."""
    return "retry" if state.get("evaluation_result") == "needs_retry" else "answer"


def route_after_retry(state: AgentState) -> str:
    """Retry while attempt counter remains below configured limit."""
    return "tool" if state.get("attempt", 0) < state.get("max_attempts", 3) else "dead_letter"


def route_after_approval(state: AgentState) -> str:
    """Continue risky action only after approval."""
    approval = state.get("approval") or {}
    return "tool" if approval.get("approved", False) else "clarify"
