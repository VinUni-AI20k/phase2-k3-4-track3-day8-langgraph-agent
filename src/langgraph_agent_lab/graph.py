"""Graph construction."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .state import AgentState
from .nodes import (
    intake_node,
    classify_node,
    tool_node,
    evaluate_node,
    answer_node,
    ask_clarification_node,
    risky_action_node,
    approval_node,
    retry_or_fallback_node,
    dead_letter_node,
    finalize_node,
)
from .routing import (
    route_after_classify,
    route_after_evaluate,
    route_after_retry,
    route_after_approval,
)


def build_graph(checkpointer: Any | None = None):
    """Build and compile the LangGraph workflow.

    Architecture:
    START → intake → classify → [route_after_classify]
      simple       → answer → finalize → END
      tool         → tool → evaluate → [route_after_evaluate]
                                          success → answer → finalize → END
                                          needs_retry → retry → [route_after_retry]
                                                                  tool (loop)
                                                                  dead_letter → finalize → END
      missing_info → clarify → finalize → END
      risky        → risky_action → approval → [route_after_approval]
                                                  approved → tool → evaluate → ...
                                                  rejected → clarify → finalize → END
      error        → retry → [route_after_retry] → ...
    """
    from langgraph.graph import START

    # Create the state graph
    graph = StateGraph(AgentState)

    # Register all nodes
    graph.add_node("intake", intake_node)
    graph.add_node("classify", classify_node)
    graph.add_node("tool", tool_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("answer", answer_node)
    graph.add_node("clarify", ask_clarification_node)
    graph.add_node("risky_action", risky_action_node)
    graph.add_node("approval", approval_node)
    graph.add_node("retry", retry_or_fallback_node)
    graph.add_node("dead_letter", dead_letter_node)
    graph.add_node("finalize", finalize_node)

    # Fixed edges
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "classify")
    graph.add_edge("tool", "evaluate")  # Tool results need evaluation
    graph.add_edge("answer", "finalize")
    graph.add_edge("clarify", "evaluate")
    graph.add_edge("risky_action", "approval")

    # Conditional edge: classify → based on route (route_after_classify returns node name)
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "answer": "answer",
            "tool": "tool",
            "clarify": "clarify",
            "risky_action": "risky_action",
            "retry": "retry",
        },
    )

    # Conditional edge: evaluate → success or retry (route_after_evaluate returns node name)
    graph.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {
            "answer": "answer",
            "retry": "retry",
        },
    )

    # Conditional edge: retry → tool (loop) or dead_letter (route_after_retry returns node name)
    graph.add_conditional_edges(
        "retry",
        route_after_retry,
        {
            "tool": "tool",
            "dead_letter": "dead_letter",
        },
    )

    # Conditional edge: approval → tool or clarify (route_after_approval returns node name)
    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "tool": "tool",
            "clarify": "clarify",
        },
    )

    # Edge: dead_letter → finalize
    graph.add_edge("dead_letter", "finalize")

    # Finalize → END
    graph.add_edge("finalize", END)

    # Compile the graph
    return graph.compile(checkpointer=checkpointer)
