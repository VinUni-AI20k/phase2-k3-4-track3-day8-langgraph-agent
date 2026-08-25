# Day 08 Lab Report

## 1. Team / student

- Name: Trần Văn Hiếu, Phạm Quốc Tuấn 
- Repo/commit: local
- Date: 2026-08-25

## 2. Architecture

### Graph Design
The support ticket agent uses LangGraph with the following flow:

```
START → intake → classify → [5 routes based on intent]
  ├── simple    → answer → finalize → END
  ├── tool      → tool → evaluate → [retry loop if needed] → answer → finalize → END
  ├── missing_info → clarify → evaluate → answer → finalize → END
  ├── risky     → risky_action → approval → [tool or clarify] → ...
  └── error     → retry → [bounded retry loop] → dead_letter → END
```

### Key Design Decisions
1. **Bounded retry loop**: Uses `attempt < max_attempts` check to prevent infinite loops
2. **Shared evaluate node**: Both tool and clarify paths converge here for retry gating
3. **Mock approval by default**: Allows offline/CI testing; real HITL via `LANGGRAPH_INTERRUPT=true`
4. **LLM for classification**: Uses structured output for reliable intent detection

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| thread_id | overwrite | Unique per scenario run |
| scenario_id | overwrite | Scenario identifier |
| query | overwrite | Normalized query |
| route | overwrite | Current route classification |
| risk_level | overwrite | High/low based on route |
| attempt | overwrite | Retry counter |
| max_attempts | overwrite | Retry limit from scenario |
| final_answer | overwrite | Final response |
| evaluation_result | overwrite | Retry gate decision |
| pending_question | overwrite | Clarification question |
| proposed_action | overwrite | Risky action description |
| approval | overwrite | Approval decision |
| messages | append | Event audit trail |
| tool_results | append | Tool execution history |
| errors | append | Error log for debugging |
| events | append | Full event history |

## 4. Scenario results

### Summary
- **Total scenarios**: 7
- **Success rate**: 100.0%
- **Avg nodes visited**: 6.7
- **Total retries**: 3
- **Total interrupts**: 2

### Per-Scenario Results

| Scenario | Expected | Actual | Success | Retries | Interrupts |
|---|---|---|:---:|:---:|:---:|
| S01_simple | simple | simple | ✅ | 0 | 0 |
| S02_tool | tool | tool | ✅ | 0 | 0 |
| S03_missing | missing_info | missing_info | ✅ | 0 | 0 |
| S04_risky | risky | risky | ✅ | 0 | 1 |
| S05_error | error | error | ✅ | 2 | 0 |
| S06_delete | risky | risky | ✅ | 0 | 1 |
| S07_dead_letter | error | error | ✅ | 1 | 0 |

## 5. Failure analysis

1. **Retry loop exhaustion**:
   - S07 (dead_letter) has max_attempts=1, fails immediately
   - The bounded retry prevents infinite loops but logs failure appropriately
   - Dead letter pattern ensures graceful degradation

2. **Risky action without approval**:
   - Risky routes require approval before execution
   - Mock approval allows testing; real HITL available via env var
   - Rejected actions redirect to clarification flow

## 6. Persistence / recovery evidence

The graph supports checkpointer via the `build_graph(checkpointer=...)` parameter:
- **Memory checkpointer** (default): Good for testing
- **SQLite checkpointer** (bonus): Enables crash recovery and state history
- Each run uses unique `thread_id = "thread-<scenario_id>"`

## 7. Extension work

- **Hit real LLM calls**: Using Ollama Phi3 for classification and answer generation
- **Structured output**: Pydantic models for reliable LLM classification
- **Environment-based HITL**: Mock by default, real interrupt available via LANGGRAPH_INTERRUPT=true

## 8. Improvement plan

If I had one more day, I would productionize:
1. **Add real tool integrations** (order lookup, customer DB)
2. **Implement SQLite checkpointer** for production persistence
3. **Add streaming** for better UX in real-time applications
