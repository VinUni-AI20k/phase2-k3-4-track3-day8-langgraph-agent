"""State schema for the Day 08 LangGraph lab.

Students should extend the schema only when needed. Keep state lean and serializable.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, TypedDict

from operator import add
from pydantic import BaseModel, Field, field_validator


class Route(StrEnum):
    SIMPLE = "simple"
    TOOL = "tool"
    MISSING_INFO = "missing_info"
    RISKY = "risky"
    ERROR = "error"
    DEAD_LETTER = "dead_letter"
    DONE = "done"


class LabEvent(BaseModel):
    """Append-only audit event for grading and debugging."""

    node: str
    event_type: str
    message: str
    latency_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approved: bool = False
    reviewer: str = "mock-reviewer"
    comment: str = ""


class AgentState(TypedDict, total=False):
    """LangGraph state.

    Reducer policy (FROZEN CONTRACT — see CONTRACT.md):
    - Scalar/control fields below use LAST-WRITE-WINS (no reducer). Only the newest value
      is meaningful for routing; an `add` reducer here would break conditional edges.
    - The four Annotated[..., add] lists at the bottom are APPEND-ONLY for auditability.
    """

    thread_id: str
    scenario_id: str
    query: str
    # `route` is written by classify_node ONLY. No other node may return "route".
    # metrics.metric_from_state compares this against Scenario.expected_route.
    route: str
    risk_level: str
    attempt: int
    max_attempts: int
    final_answer: str | None

    # ─── Contract fields (overwrite semantics, no reducer) ───────────────
    evaluation_result: str  # "success" | "needs_retry"  → route_after_evaluate
    pending_question: str  # clarification question       → ask_clarification_node
    proposed_action: str  # risky action description      → risky_action_node
    approval: dict[str, Any] | None  # ApprovalDecision().model_dump() — a plain dict

    messages: Annotated[list[str], add]
    tool_results: Annotated[list[str], add]
    errors: Annotated[list[str], add]
    events: Annotated[list[dict[str, Any]], add]


class Scenario(BaseModel):
    id: str
    query: str
    expected_route: Route
    requires_approval: bool = False
    should_retry: bool = False
    max_attempts: int = 3
    tags: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


def initial_state(scenario: Scenario) -> AgentState:
    """Create a serializable initial state for one scenario."""
    return {
        "thread_id": f"thread-{scenario.id}",
        "scenario_id": scenario.id,
        "query": scenario.query,
        "route": "",
        "risk_level": "unknown",
        "attempt": 0,
        "max_attempts": scenario.max_attempts,
        "final_answer": None,
        "messages": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }


def make_event(node: str, event_type: str, message: str, **metadata: Any) -> dict[str, Any]:
    """Create a normalized event payload."""
    return LabEvent(node=node, event_type=event_type, message=message, metadata=metadata).model_dump()
