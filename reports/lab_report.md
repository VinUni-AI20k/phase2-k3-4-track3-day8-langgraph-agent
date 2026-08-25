# Day 08 Lab Report

## 1. Team / student

- Name: Phung Dinh Dat
- Repo/commit: Working tree artifact (no commit created)
- Date: 2026-08-25

## 2. Architecture

Graph flow: `START -> intake -> classify`, then conditional routing selects
`answer`, `tool`, `clarify`, `risky_action`, or `retry`. Tool results pass through
`evaluate`; failed results enter bounded `retry -> tool` cycles or `dead_letter`.
Risky actions pass through `approval`; every terminal path enters `finalize -> END`.

`classify_node` uses structured LLM output when an API key is configured.
`answer_node` uses LLM generation grounded by query, tool results, and approval
state. No scenario ID is used for production routing.

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| `messages` | append | Conversation/audit messages |
| `tool_results` | append | Preserve each tool attempt for evaluation |
| `errors` | append | Preserve retry and failure evidence |
| `events` | append | Node-level execution audit trail |
| `route` | overwrite | Current classified route |
| `attempt` | overwrite | Current bounded retry counter |
| `approval` | overwrite | Latest approval decision |
| `final_answer` | overwrite | Terminal user-facing result |

## 4. Scenario results

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | yes | 0 | 0 |
| S02_tool | tool | tool | yes | 0 | 0 |
| S03_missing | missing_info | missing_info | yes | 0 | 0 |
| S04_risky | risky | risky | yes | 0 | 1 |
| S05_error | error | error | yes | 2 | 0 |
| S06_delete | risky | risky | yes | 0 | 1 |
| S07_dead_letter | error | error | yes | 1 | 0 |

### Metrics summary

| Metric | Value |
|---|---:|
| Total scenarios | 7 |
| Success rate | 100.0% |
| Average nodes visited | 6.43 |
| Total retries | 3 |
| Total interrupts | 2 |
| Resume success | yes (SQLite rebuild integration test) |

## 5. Failure analysis

1. **Transient tool failure:** `tool_node` emits an error result, `evaluate_node` marks `needs_retry`, and routing increments `attempt`. `route_after_retry` stops at `max_attempts`; exhausted work reaches `dead_letter` instead of looping forever.
2. **Risky action without approval:** side-effecting requests first create `proposed_action`. `approval_node` records decision; rejection routes to clarification, preventing direct action execution. `LANGGRAPH_INTERRUPT=true` enables real interrupt/resume behavior.
3. **LLM unavailable:** classification and answer generation are LLM key-gated. This deterministic artifact does not claim API-backed execution when no provider key is available.

## 6. Persistence / recovery evidence

Default config uses `MemorySaver`, with unique `thread_id` per scenario (`thread-<scenario_id>`). SQLite recovery is verified by `tests/test_persistence_recovery.py`: test writes to `tmp_path` SQLite, closes saver-owned connection, rebuilds saver and graph, then recovers same thread state and state history without LLM network calls. This proves checkpoint recovery, not crash recovery of a live process.

## 7. Extension work

Persistence adapter and HITL interrupt path are implemented. SQLite checkpoint recovery across rebuilt saver/graph is test-verified; live-process crash recovery is not claimed.

## 8. Improvement plan

- Add provider-independent deterministic fallback harness for CI, while keeping production LLM routing unchanged.
- Exercise SQLite checkpoint history and interrupt resume in integration tests.
- Replace mock tool with authenticated adapter, typed tool results, timeout policy, and tracing.
- Add LLM-as-judge evaluation only behind explicit opt-in and record model/version metadata.
