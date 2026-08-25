# Day 08 Lab Report

## 1. Team / student

- **Thành viên & Phân công nhiệm vụ:**
  - **Phạm Trung Kiên** (`2A202601525`) — Phase 1: State schema + Node implementations
  - **Ngô Thị Hằng** (`2A202601365`) — Phase 2: Routing logic + Graph wiring
  - **Nguyễn Thị Hoàng Yến** (`2A202601959`) — Phase 3: Persistence & Checkpoint
  - **Phạm Thế Dũng** (`2A202601985`) — Phase 4: Metrics, Evaluation & Report
  - **Hoàng Tuấn Trung** (`2A202601807`) — Phase 5: Extensions (SQLite, Time travel)
- **Repo:** https://github.com/phamkien1917/Track3-DAY23-E3
- **Commit:** `91060d9a40355f09e4ec3b4ce3a1ae32ed3b8f16`
- **Date:** 2026-08-25

## 2. Architecture

The solution is a LangGraph `StateGraph` for customer-support tickets. It
normalizes a query, classifies its intent with a structured LLM response, then
uses conditional edges to choose a direct answer, a tool lookup, clarification,
human approval, or a bounded retry/dead-letter flow. All completed routes pass
through `finalize` before `END`.

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| Audit: messages, tool results, errors, events | append | Preserve workflow history. |
| Control: route, risk level, attempt, final answer | overwrite | Store current decisions. |
| Flow fields: evaluation, clarification, action, approval | overwrite | Carry node decisions. |

## 4. Scenario results

| Metric | Value |
|---|---:|
| Total scenarios | 7 |
| Success rate | 100.00% |
| Average nodes visited | 13.14 |
| Total retries | 6 |
| Total approval/HITL events | 4 |
| Resume success | Yes |

| Scenario | Expected route | Actual route | Success | Retries | Interrupts | Latency (ms) |
|---|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | Yes | 0 | 0 | 48855 |
| S02_tool | tool | tool | Yes | 0 | 0 | 4548 |
| S03_missing | missing_info | missing_info | Yes | 0 | 0 | 13339 |
| S04_risky | risky | risky | Yes | 0 | 2 | 10632 |
| S05_error | error | error | Yes | 4 | 0 | 7312 |
| S06_delete | risky | risky | Yes | 0 | 2 | 23508 |
| S07_dead_letter | error | error | Yes | 2 | 0 | 3239 |

### Recorded errors

- **S05_error**: Transient failure recorded. Attempt 1 of 3.; Transient failure recorded. Attempt 2 of 3.; Transient failure recorded. Attempt 1 of 3.; Transient failure recorded. Attempt 2 of 3.
- **S07_dead_letter**: Transient failure recorded. Attempt 1 of 1.; Transient failure recorded. Attempt 1 of 1.

## 5. Failure analysis

1. **Transient tool failure:** `evaluate` sends an unsuccessful tool result to
   `retry`. The retry node increments `attempt`; once `max_attempts` is reached,
   the graph routes to `dead_letter`, preventing an infinite loop.
2. **Risky action without approval:** side-effecting requests are routed through
   `risky_action` and `approval`. A rejected request goes to clarification rather
   than continuing to the tool.

## 6. Persistence / recovery evidence

SQLite checkpoint history was retrieved successfully after every scenario. The default configuration uses `SqliteSaver` with WAL mode in `checkpoints.db`; each scenario has its own `thread_id`.

## 7. Extension work

Five Phase 5 extensions are implemented:

1. **SQLite persistence:** `SqliteSaver` in WAL mode with per-scenario `thread_id`.
2. **Time-travel inspection:** `make inspect-history` exports checkpoint snapshots.
3. **Graph diagram:** `make graph-diagram` exports Mermaid diagram to `outputs/graph.mmd`.
4. **LLM-as-judge:** `evaluate_node` uses structured LLM evaluation to judge tool outputs.
5. **Streamlit Web UI:** `streamlit run streamlit_app.py` interactive demo dashboard.

## 8. Improvement plan

The next production improvement is stronger observability: measure per-node
latency, trace LLM and tool calls, and use a grounded evaluator to validate tool
results before answering customers.
