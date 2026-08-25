# CONTRACT — chốt tại T+00, không đổi sau đó

Đọc hết file này trước khi gõ dòng code đầu tiên. Mọi con số/chuỗi ở đây đã được đối chiếu
với `tests/`, `metrics.py`, `cli.py` trong repo — không phải phỏng đoán.

---

## 0. Setup (mọi máy, làm ngay)

```bash
pip install -e '.[dev]'
pip install langchain-google-genai          # hoặc langchain-openai / langchain-anthropic
pip install langgraph-checkpoint-sqlite     # chỉ M5 cần

cp .env.example .env                        # điền GEMINI_API_KEY

# ⚠ Repo KHÔNG có python-dotenv và KHÔNG có load_dotenv() ở đâu cả.
# Chỉ tạo .env là get_llm() vẫn báo "No LLM API key found". Phải export thật:
set -a; source .env; set +a

python -c "from langgraph_agent_lab.llm import get_llm; print(get_llm().invoke('ping').content)"
```

`pip install -e '.[dev]'` là bắt buộc — không có nó thì `pytest` fail toàn bộ với
`ModuleNotFoundError: No module named 'langgraph_agent_lab'`.

---

## 1. Tên node — 11 chuỗi BẤT BIẾN

Dùng đúng chuỗi này ở cả 3 chỗ: `add_node()`, giá trị trả về của routing function, và
tham số đầu của `make_event()`.

```
intake  classify  tool  evaluate  answer  clarify
risky_action  approval  retry  dead_letter  finalize
```

Lưu ý hai chỗ tên hàm ≠ tên node:
- hàm `ask_clarification_node` → node `"clarify"`
- hàm `retry_or_fallback_node` → node `"retry"`

---

## 2. Giá trị chuỗi — BẤT BIẾN

| Field | Ai ghi | Giá trị hợp lệ | Ai đọc |
|---|---|---|---|
| `route` | **chỉ** `classify_node` | `simple` `tool` `missing_info` `risky` `error` | `route_after_classify`, `metric_from_state` |
| `evaluation_result` | `evaluate_node` (M4) | `success` \| `needs_retry` | `route_after_evaluate` (M1) |
| `risk_level` | `classify_node` (M2) | `high` \| `low` | báo cáo |
| `approval` | `approval_node` (M5) | **dict** `{"approved":bool,"reviewer":str,"comment":str}` | `route_after_approval` (M1), `metric_from_state` |
| `attempt` / `max_attempts` | `retry_or_fallback_node` / `initial_state` | int | `route_after_retry` (M1) |

`Route.DEAD_LETTER` và `Route.DONE` có trong enum nhưng **không phải** output hợp lệ của
classify — đừng đưa vào `Literal[...]`.

---

## 3. Năm luật vàng (vi phạm là hỏng ở Gate 2, không hỏng ở Gate 1 — nên rất khó tìm)

**① Chỉ `classify_node` được trả về `"route"`.**
`metric_from_state` chấm `success = (state["route"] == scenario.expected_route)`.
S05/S07 có `expected_route="error"`; nếu `dead_letter_node` hay `answer_node` ghi đè
`route` thì scenario fail dù graph chạy đúng. S04/S06 tương tự với `"risky"`.

**② `approval` phải là dict, không phải Pydantic object.**
`route_after_approval` làm `state["approval"]["approved"]`. Trả về `ApprovalDecision(...)`
là `TypeError`. Dùng `ApprovalDecision(...).model_dump()`.

**③ Tên trong `make_event(...)` là thứ metrics đếm.**
```python
retry_count     = sum(1 for n in nodes if n == "retry")      # M4 phải emit đúng "retry"
interrupt_count = sum(1 for n in nodes if n == "approval")   # M5 phải emit đúng "approval"
```
Sai tên → `total_retries=0`, `total_interrupts=0` → trượt Gate 2 dù logic đúng.
`nodes_visited` = tổng số event, nên **mọi node đều phải emit ít nhất 1 event**.

**④ Field có reducer `add` → trả về list 1 phần tử, không trả cả list.**
`messages`, `tool_results`, `errors`, `events` là `Annotated[list, add]`.
Trả `{"tool_results": state["tool_results"] + [x]}` sẽ nhân đôi dữ liệu.
Đúng: `{"tool_results": [x]}`.
Bốn field mới (`evaluation_result`, `pending_question`, `proposed_action`, `approval`)
**không có reducer** → ghi đè, đúng như routing cần.

**⑤ Node không được ném exception.**
Một node raise là cả `graph.invoke()` chết, mất toàn bộ scenario. M2 bọc `try/except`
quanh LLM call, fallback route `"simple"` + ghi vào `errors`.

---

## 4. Vòng retry — số liệu đã trace sẵn

`retry_or_fallback_node` tăng `attempt` **trước**, rồi `route_after_retry` mới đọc.
Ngưỡng là `attempt < max_attempts` (test: `attempt=3, max=3` → `dead_letter`).

```
S05 (max_attempts=3, mặc định):
  classify(route=error) → retry(attempt 0→1) → 1<3 → tool
  tool: route=="error" and attempt(1)<2 → trả chuỗi chứa "ERROR"
      → evaluate: needs_retry → retry(attempt 1→2) → 2<3 → tool
  tool: attempt(2)<2 sai → trả success → evaluate: success → answer → finalize
  ⇒ 2 event "retry", tool_results có 2 phần tử, errors có 2 dòng

S07 (max_attempts=1):
  classify(route=error) → retry(attempt 0→1) → 1<1 sai → dead_letter → finalize
  ⇒ 1 event "retry", 0 tool call, không lặp vô hạn
```

Nếu bạn trace ra khác con số này thì một trong hai bên sai — nói ra ở Gate 1, đừng tự sửa.

---

## 5. Sở hữu file

| File | Chủ | Ai khác đụng vào = conflict |
|---|---|---|
| `state.py` `routing.py` `graph.py` `nodes.py` `nodes_core.py` | M1 | ✅ đã freeze `state.py` + `nodes.py` |
| `nodes_classify.py` · `data/sample/scenarios.jsonl` | M2 | |
| `nodes_generate.py` | M3 | |
| `nodes_tools.py` | M4 | |
| `nodes_hitl.py` `persistence.py` `report.py` `reports/lab_report.md` | M5 | |
| `metrics.py` `cli.py` `scenarios.py` `llm.py` `tests/` | **read-only cả team** | |

Nhánh: `feat/m<n>-<tên>`. Chỉ commit file mình sở hữu. Không format lại file người khác.

---

## 6. Hai cái bẫy trong repo gốc (đã xử lý — để biết)

**`configs/lab.yaml → report_path`**: `cli.run_scenarios` gọi `write_report()` ở cuối mỗi
lần chạy, mà `render_report()` đang là `NotImplementedError`. Nghĩa là:
- `make run-scenarios` sẽ **crash ở bước cuối** (sau khi đã ghi `metrics.json`) cho tới khi
  M5 implement `render_report`. → M5 phải xong `report.py` **trước Gate 2**, không phải T+45.
- File này đã đổi trỏ sang `reports/lab_report_generated.md` để không ghi đè bản báo cáo
  M5 viết tay ở `reports/lab_report.md`.

**`load_scenarios` yêu cầu ≥ 6 scenario** và `validate-metrics` yêu cầu ≥ 6. M2 thêm S08–S12
→ 12 scenario, thoả.

---

## 7. Lệnh tự kiểm tra, chạy được ngay cả khi 4 người kia chưa xong

```bash
# M1
pytest tests/test_routing.py tests/test_state.py -q

# M2
python -c "
from langgraph_agent_lab.nodes_classify import classify_node
for q in ['Refund this customer','lookup order 12345','fix it','Timeout failure','How to reset password?']:
    print(q,'→',classify_node({'query':q}))"

# M3
python -c "
from langgraph_agent_lab.nodes_generate import answer_node
print(answer_node({'query':'order status 12345','tool_results':['OK: order 12345 shipped'],'approval':None}))"

# M4
python -c "
from langgraph_agent_lab.nodes_tools import tool_node, evaluate_node
s={'query':'timeout','route':'error','attempt':1,'tool_results':[]}
r=tool_node(s); print(r); print(evaluate_node({**s,**r})['evaluation_result'])  # needs_retry"

# M5
python -c "
from langgraph_agent_lab.nodes_hitl import approval_node
from langgraph_agent_lab.persistence import build_checkpointer
a=approval_node({}); assert isinstance(a['approval'], dict), 'phải là dict!'
print(a); print(build_checkpointer('sqlite','outputs/lab.db'))"
```

## 8. Grep phải sạch trước khi nộp

```bash
grep -rn "with_structured_output" src/    # phải CÓ  (M2)
grep -rn "get_llm()"              src/    # phải CÓ  (M2+M3)
grep -rn "max_attempts" src/routing.py    # phải CÓ  (M1)
grep -rn "scenario_id ==" src/            # phải RỖNG — hard-code là dưới 60đ
grep -rn "TODO(M[1-5])" src/              # phải RỖNG trước Gate 1
```
