"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:  # noqa: ANN401
    """Return configured LangGraph checkpointer."""
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError("SQLite checkpointer requires langgraph-checkpoint-sqlite") from exc
        database_path = Path(database_url or "langgraph_checkpoints.sqlite")
        connection = sqlite3.connect(database_path, check_same_thread=False)
        _ = connection.execute("PRAGMA journal_mode=WAL")
        return SqliteSaver(conn=connection)
    if kind == "postgres":
        raise RuntimeError(
            "Postgres checkpointer requires project-specific connection configuration"
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
