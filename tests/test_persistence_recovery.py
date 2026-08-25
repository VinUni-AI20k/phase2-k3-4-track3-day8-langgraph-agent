"""SQLite checkpoint recovery integration test."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import AgentState, Route, Scenario, initial_state


class FakeResponse:
    """Minimal response consumed by answer_node."""

    content = "Recovered answer"


class FakeStructuredLlm:
    """Typed fake for classify_node structured-output boundary."""

    def with_structured_output(self, _schema: Any) -> FakeStructuredLlm:
        return self

    def invoke(self, _prompt: str) -> Any:
        return type("ClassificationResult", (), {"route": "simple", "risk_level": "low"})()


class FakeLlm(FakeStructuredLlm):
    """Typed fake covering classification and answer LLM calls."""

    def invoke(self, prompt: str) -> Any:
        if prompt.startswith("Classify support request"):
            return super().invoke(prompt)
        return FakeResponse()


def test_sqlite_checkpoint_recovers_after_graph_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given SQLite checkpoint, rebuilt graph recovers same thread state/history."""
    database_path = tmp_path / "checkpoints.sqlite"
    scenario = Scenario(
        id="sqlite-recovery", query="How do I reset my password?", expected_route=Route.SIMPLE
    )
    state = initial_state(scenario)
    thread_id = f"thread-{scenario.id}"
    config = {"configurable": {"thread_id": thread_id}}
    monkeypatch.setattr("langgraph_agent_lab.nodes.get_llm", lambda: FakeLlm())

    first_checkpointer = build_checkpointer("sqlite", str(database_path))
    assert first_checkpointer is not None
    first_graph = build_graph(checkpointer=first_checkpointer)
    result = first_graph.invoke(state, config=config)
    first_checkpointer.conn.close()

    second_checkpointer = build_checkpointer("sqlite", str(database_path))
    assert second_checkpointer is not None
    rebuilt_graph = build_graph(checkpointer=second_checkpointer)
    recovered_state: AgentState = rebuilt_graph.get_state(config).values
    history = list(rebuilt_graph.get_state_history(config))
    second_checkpointer.conn.close()

    assert result["final_answer"] == "Recovered answer"
    assert recovered_state.get("thread_id") == thread_id
    assert recovered_state.get("final_answer") == "Recovered answer"
    assert len(history) >= 4
