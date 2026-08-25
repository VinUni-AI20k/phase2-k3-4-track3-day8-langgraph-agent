"""Unit tests for individual node implementations."""

from __future__ import annotations

from langgraph_agent_lab.nodes import (
    approval_node,
    ask_clarification_node,
    dead_letter_node,
    evaluate_node,
    finalize_node,
    intake_node,
    retry_or_fallback_node,
    risky_action_node,
    tool_node,
)
from langgraph_agent_lab.state import Route, Scenario, initial_state


def test_intake_node() -> None:
    scenario = Scenario(id="test", query="  Need help with login  ", expected_route=Route.SIMPLE)
    state = initial_state(scenario)
    result = intake_node(state)
    assert result["query"] == "Need help with login"
    assert len(result["events"]) == 1
    assert result["events"][0]["node"] == "intake"


def test_tool_node_error_simulation() -> None:
    scenario = Scenario(id="test-err", query="Timeout error in system", expected_route=Route.ERROR)
    state = initial_state(scenario)
    state["route"] = "error"
    state["attempt"] = 0

    result = tool_node(state)
    assert len(result["tool_results"]) == 1
    assert "ERROR" in result["tool_results"][0]


def test_tool_node_success() -> None:
    scenario = Scenario(id="test-tool", query="Lookup order 123", expected_route=Route.TOOL)
    state = initial_state(scenario)
    state["route"] = "tool"
    state["attempt"] = 0

    result = tool_node(state)
    assert len(result["tool_results"]) == 1
    assert "SUCCESS" in result["tool_results"][0]


def test_evaluate_node_needs_retry() -> None:
    state = {
        "tool_results": ["ERROR: service unavailable"],
        "events": [],
    }
    result = evaluate_node(state)
    assert result["evaluation_result"] == "needs_retry"
    assert result["events"][0]["node"] == "evaluate"


def test_evaluate_node_success() -> None:
    state = {
        "tool_results": ["SUCCESS: order status is shipped"],
        "events": [],
    }
    result = evaluate_node(state)
    assert result["evaluation_result"] == "success"
    assert result["events"][0]["node"] == "evaluate"


def test_ask_clarification_node() -> None:
    state = {"query": "Fix it", "events": []}
    result = ask_clarification_node(state)
    assert "pending_question" in result
    assert "Fix it" in result["pending_question"]
    assert result["final_answer"] == result["pending_question"]
    assert result["events"][0]["node"] == "clarify"


def test_risky_action_node() -> None:
    state = {"query": "Refund customer $500", "events": []}
    result = risky_action_node(state)
    assert "proposed_action" in result
    assert "Refund customer $500" in result["proposed_action"]
    assert result["events"][0]["node"] == "risky_action"


def test_approval_node() -> None:
    state = {"proposed_action": "Refund customer $500", "events": []}
    result = approval_node(state)
    assert "approval" in result
    assert result["approval"]["approved"] is True
    assert result["events"][0]["node"] == "approval"


def test_retry_or_fallback_node() -> None:
    state = {"attempt": 1, "max_attempts": 3, "errors": [], "events": []}
    result = retry_or_fallback_node(state)
    assert result["attempt"] == 2
    assert len(result["errors"]) == 1
    assert result["events"][0]["node"] == "retry"


def test_dead_letter_node() -> None:
    state = {"attempt": 3, "max_attempts": 3, "events": []}
    result = dead_letter_node(state)
    assert "final_answer" in result
    assert "3/3" in result["final_answer"]
    assert result["events"][0]["node"] == "dead_letter"


def test_finalize_node() -> None:
    state = {"events": []}
    result = finalize_node(state)
    assert len(result["events"]) == 1
    assert result["events"][0]["node"] == "finalize"
    assert result["events"][0]["event_type"] == "completed"
