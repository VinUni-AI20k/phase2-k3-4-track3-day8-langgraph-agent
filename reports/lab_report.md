# Day 08 Lab Report — LangGraph Agentic Orchestration

## 1. Team / student

- **Name**: Trần Hải Quân - 2A202601521
- **Repo/commit**: `phase2-k3-4-track3-day8-langgraph-agent`
- **Date**: 2026-08-25

## 2. Architecture

The support-ticket agent workflow is built using a **LangGraph `StateGraph`** featuring
11 specialized nodes and dynamic conditional routing:

- **Intake & Triage**: `intake_node` normalizes raw queries, followed by `classify_node`
  utilizing LLM with structured output (`.with_structured_output()`) prioritizing:
  `risky` > `tool` > `missing_info` > `error` > `simple`.
- **Fulfillment & Synthesis**: `answer_node` generates grounded responses;
  `ask_clarification_node` handles ambiguous queries.
- **Safety & HITL**: `risky_action_node` formats sensitive actions, gated by `approval_node`
  (supporting both mock auto-approval and real `interrupt()`).
- **Resilience & Bounded Retries**: `tool_node` simulates external execution; `evaluate_node`
  performs hybrid check (heuristic + LLM-as-judge); `retry_or_fallback_node` increments attempts
  with bounded routing (`attempt < max_attempts`), escalating exhausted retries to
  `dead_letter_node`.
- **Audit & Completion**: Every workflow terminates through `finalize_node` to ensure immutable
  audit trails before reaching `END`.

## 3. State schema

| Field | Reducer | Purpose / Justification |
|---|---|---|
| `messages` | `append` (`Annotated[list[str], add]`) | Preserves ordered conversation turns |
| `tool_results` | `append` (`Annotated[list[str], add]`) | Logs outputs from tool invocations |
| `errors` | `append` (`Annotated[list[str], add]`) | Cumulative record of transient failures |
| `events` | `append` (`Annotated[list[dict], add]`) | Immutable audit trail of node visits |
| `route` | `overwrite` | Currently active classified intent route |
| `risk_level` | `overwrite` | Risk tier (`high` for destructive operations, `low` otherwise) |
| `attempt` | `overwrite` | Monotonically increasing retry attempt counter |
| `max_attempts` | `overwrite` | Scenario-specific ceiling for retry loop boundedness |
| `final_answer` | `overwrite` | Final customer-facing synthesized answer |
| `evaluation_result` | `overwrite` | Outcome of tool evaluation (`success` vs `needs_retry`) |
| `pending_question` | `overwrite` | Specific clarification prompt for ambiguous queries |
| `proposed_action` | `overwrite` | Payload and rationale for operations awaiting approval |
| `approval` | `overwrite` | Structured approval decision (`approved`, `reviewer`, `comment`) |

## 4. Scenario results

### Metrics Summary
- **Total Scenarios**: 7
- **Success Rate**: 100.0%
- **Average Nodes Visited**: 6.43
- **Total Retries**: 3
- **Total Interrupts / Approvals**: 2

### Detailed Scenario Table
| Scenario ID | Expected Route | Actual Route | Success | Retries | Interrupts |
|---|---|---|:---:|---:|---:|
| `S01_simple` | `simple` | `simple` | ✅ PASS | 0 | 0 |
| `S02_tool` | `tool` | `tool` | ✅ PASS | 0 | 0 |
| `S03_missing` | `missing_info` | `missing_info` | ✅ PASS | 0 | 0 |
| `S04_risky` | `risky` | `risky` | ✅ PASS | 0 | 1 |
| `S05_error` | `error` | `error` | ✅ PASS | 2 | 0 |
| `S06_delete` | `risky` | `risky` | ✅ PASS | 0 | 1 |
| `S07_dead_letter` | `error` | `error` | ✅ PASS | 1 | 0 |

## 5. Failure analysis

1. **Transient Tool Failure & Unbounded Retry Prevention**:
   - *Risk*: External failure could cause graph to loop infinitely, exhausting quotas.
   - *Mitigation*: The `route_after_retry` conditional edge enforces a strict bound
     (`attempt < max_attempts`). Once reached, control routes to `dead_letter_node`.
2. **Unauthorized Destructive Action Execution**:
   - *Risk*: Destructive requests executing without verification.
   - *Mitigation*: Top priority given to `risky` routes. Gated by `approval_node`.
     Rejection deflects to `ask_clarification_node`.

## 6. Persistence & recovery evidence

- **Checkpointer Architecture**: Configured with `SqliteSaver` in WAL mode.
- **Thread Isolation**: Unique `thread_id` (e.g., `thread-S01_simple`) per run.
- **Crash Recovery**: State survives process termination, enabling recovery via checkpoint.

## 7. Extension work

1. **SQLite Checkpoint Persistence**: Implemented production-ready checkpointer with WAL.
2. **LLM-as-a-Judge Evaluation**: Integrated smart output validation in `evaluate_node`.
3. **Interruptible Human-in-the-Loop**: Added support for LangGraph native `interrupt()`.
4. **Mermaid Graph Visualization**: Exportable graph topology diagram.

## 8. Improvement plan

1. **Real-time Streaming**: Integrate `graph.astream_events()` for token-level streaming.
2. **Concurrent Tool Fan-out**: Implement `Send()` API for parallel lookups.
3. **Distributed Persistence**: Add Postgres checkpointer (`PostgresSaver`) for scaling.
