"""Checkpointer adapter with SQLite persistence support."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    Supports:
    - "none": No checkpointer (stateless)
    - "memory": In-memory checkpointer (default, for testing)
    - "sqlite": SQLite persistence with WAL mode (production-ready)
    - "postgres": PostgreSQL persistence (optional)
    """
    if kind == "none":
        return None

    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError:
            raise RuntimeError(
                "Install langgraph-checkpoint-sqlite: uv add langgraph-checkpoint-sqlite"
            )

        # Get database path from env or use default
        db_path = os.getenv("SQLITE_DB_PATH", "outputs/checkpoints.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create connection with WAL mode for better concurrency
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        return SqliteSaver(conn=conn)

    if kind == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError:
            raise RuntimeError(
                "Install langgraph-checkpoint-postgres: uv add langgraph-checkpoint-postgres"
            )

        if not database_url:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError(
                    "Postgres checkpointer requires DATABASE_URL env var or database_url parameter"
                )

        return PostgresSaver.from_conn_string(database_url)

    raise ValueError(f"Unknown checkpointer kind: {kind}")


def get_checkpointer_info(kind: str = "memory") -> dict[str, Any]:
    """Return information about the configured checkpointer for logging/debugging."""
    info = {"kind": kind}

    if kind == "memory":
        info["description"] = "In-memory checkpointer (data lost on restart)"
        info["persistence"] = False

    elif kind == "sqlite":
        db_path = os.getenv("SQLITE_DB_PATH", "outputs/checkpoints.db")
        info["description"] = f"SQLite checkpointer at {db_path}"
        info["persistence"] = True
        info["database_path"] = db_path

        if Path(db_path).exists():
            info["database_size_bytes"] = Path(db_path).stat().st_size

    elif kind == "postgres":
        info["description"] = "PostgreSQL checkpointer (production-ready)"
        info["persistence"] = True

    elif kind == "none":
        info["description"] = "No checkpointer (stateless mode)"
        info["persistence"] = False

    return info
