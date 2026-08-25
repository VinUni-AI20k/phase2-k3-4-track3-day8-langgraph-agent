"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _sqlite_database_path(database_url: str | None) -> str:
    """Resolve a plain SQLite path or a ``sqlite:///`` URL."""
    if not database_url:
        return "checkpoints.db"
    if database_url.startswith("sqlite:///"):
        return database_url.removeprefix("sqlite:///")
    if "://" in database_url:
        raise ValueError("SQLite database_url must be a file path or sqlite:/// URL")
    return database_url


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> object | None:
    """Return a LangGraph checkpointer.

    TODO(student): implement SQLite support for the persistence extension track.
    The starter provides MemorySaver only — SQLite/Postgres are extension tasks.

    For SQLite:
    - pip install langgraph-checkpoint-sqlite
    - Use SqliteSaver with sqlite3.connect() and WAL mode
    - See: https://langchain-ai.github.io/langgraph/how-tos/persistence/
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError(
                "Install SQLite persistence support: pip install -e '.[sqlite]'"
            ) from exc

        path = _sqlite_database_path(database_url)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.execute("PRAGMA journal_mode=WAL")
        checkpointer = SqliteSaver(connection)
        checkpointer.setup()
        return checkpointer
    if kind == "postgres":
        raise NotImplementedError(
            "TODO(student): implement Postgres checkpointer (optional extension)"
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
