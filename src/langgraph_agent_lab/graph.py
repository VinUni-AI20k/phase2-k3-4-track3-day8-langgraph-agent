"""LangGraph workflow construction."""

from __future__ import annotations

from typing import Any

from .state import AgentState


def build_graph(checkpointer: Any | None = None) -> Any:  # noqa: ANN401
    """Build and compile complete support-ticket graph."""
    from langgraph.graph import END, START, StateGraph

    from .nodes import (
        answer_node,
        approval_node,
        ask_clarification_node,
        classify_node,
        dead_letter_node,
        evaluate_node,
        finalize_node,
        intake_node,
        retry_or_fallback_node,
        risky_action_node,
        tool_node,
    )
    from .routing import (
        route_after_approval,
        route_after_classify,
        route_after_evaluate,
        route_after_retry,
    )

    builder = StateGraph(AgentState)
    builder.add_node("intake", intake_node)
    builder.add_node("classify", classify_node)
    builder.add_node("answer", answer_node)
    builder.add_node("tool", tool_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("clarify", ask_clarification_node)
    builder.add_node("risky_action", risky_action_node)
    builder.add_node("approval", approval_node)
    builder.add_node("retry", retry_or_fallback_node)
    builder.add_node("dead_letter", dead_letter_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "classify")
    builder.add_conditional_edges("classify", route_after_classify)
    builder.add_edge("tool", "evaluate")
    builder.add_conditional_edges("evaluate", route_after_evaluate)
    builder.add_conditional_edges("retry", route_after_retry)
    builder.add_edge("risky_action", "approval")
    builder.add_conditional_edges("approval", route_after_approval)
    for node in ("answer", "clarify", "dead_letter"):
        builder.add_edge(node, "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
