from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from langgraph_agent_lab.persistence import build_checkpointer


class CounterState(TypedDict):
    count: int


def increment(state: CounterState) -> dict[str, int]:
    return {"count": state["count"] + 1}


def build_counter_graph(checkpointer: object) -> object:
    workflow = StateGraph(CounterState)
    workflow.add_node("increment", increment)
    workflow.add_edge(START, "increment")
    workflow.add_edge("increment", END)
    return workflow.compile(checkpointer=checkpointer)


def close_sqlite_checkpointer(checkpointer: object) -> None:
    connection = getattr(checkpointer, "conn", None)
    if connection is not None:
        connection.close()


def test_sqlite_checkpointer_persists_state_history(tmp_path: Path) -> None:
    database_path = tmp_path / "checkpoints.db"
    config = {"configurable": {"thread_id": "persistence-test"}}

    first_checkpointer = build_checkpointer("sqlite", str(database_path))
    assert first_checkpointer is not None
    first_graph = build_counter_graph(first_checkpointer)
    first_result = first_graph.invoke({"count": 0}, config=config)
    first_history = list(first_graph.get_state_history(config))
    close_sqlite_checkpointer(first_checkpointer)

    second_checkpointer = build_checkpointer("sqlite", str(database_path))
    assert second_checkpointer is not None
    second_graph = build_counter_graph(second_checkpointer)
    recovered_state = second_graph.get_state(config)
    close_sqlite_checkpointer(second_checkpointer)

    assert database_path.exists()
    assert first_result["count"] == 1
    assert first_history
    assert recovered_state.values["count"] == 1
