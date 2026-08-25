# Day 08 Lab - Điều phối Agent bằng LangGraph

Xây dựng một workflow LangGraph theo phong cách production cho agent xử lý ticket hỗ trợ, bao gồm quản lý state, định tuyến có điều kiện, vòng lặp retry, phê duyệt human-in-the-loop, persistence và metrics.

Đây là **starter skeleton**. Toàn bộ phần triển khai node, logic routing và wiring graph đang được để dưới dạng `TODO(student)` - bạn cần tự xây dựng từ đầu.

---

## Cách chấm điểm

| Hạng mục | Điểm | Tiêu chí đánh giá |
|---|---:|---|
| Kiến trúc & schema state | 15 | State có type rõ ràng với reducer đúng, có field sinh viên tự thêm, state gọn và serializable |
| Xây dựng & wiring graph | 15 | Đăng ký đủ node, edge đúng, conditional edge hoạt động, graph compile được |
| Tích hợp LLM | 15 | `classify_node` + `answer_node` dùng LLM thật (structured output, generation có grounding) |
| Hành vi graph | 20 | Tất cả scenario đi đúng route, retry loop có giới hạn, có luồng HITL approval, mọi route đều kết thúc |
| Persistence & recovery | 10 | Có nối checkpointer, mỗi lần chạy có `thread_id`, có bằng chứng state history hoặc crash-resume |
| Metrics & test | 15 | `metrics.json` hợp lệ, cover các scenario, test pass, số liệu có ý nghĩa |
| Report & demo | 10 | Giải thích kiến trúc, bảng metrics, phân tích lỗi, ý tưởng cải tiến |

**Khung điểm:**
- **90-100**: Graph chất lượng production + tích hợp LLM + metrics + report + ít nhất một bonus extension
- **75-89**: Core graph chạy được với LLM, metrics hợp lệ, report giải thích trade-off
- **60-74**: Graph cơ bản chạy được nhưng tích hợp LLM, persistence hoặc report còn thiếu
- **< 60**: Không chạy được, hard-code theo scenario, hoặc thiếu tích hợp LLM/metrics/report

> **Quy tắc quan trọng**: KHÔNG hard-code câu trả lời cho từng scenario cụ thể. Graph của bạn phải route dựa trên **LLM classification và logic state**, không phải so khớp chính xác scenario ID. Bài chấm sẽ có thêm các scenario ẩn.

---

## Yêu cầu tích hợp LLM

Lab này yêu cầu gọi API LLM thật trong một số node cụ thể:

| Node | Yêu cầu | Pattern |
|---|---|---|
| `classify_node` | **BẮT BUỘC dùng LLM** | Structured output (`.with_structured_output()`) để phân loại intent |
| `answer_node` | **BẮT BUỘC dùng LLM** | Sinh câu trả lời có grounding dựa trên `tool_results`/context |
| `evaluate_node` | **NÊN dùng LLM** (bonus) | Dùng LLM-as-judge để đánh giá chất lượng kết quả tool |

Helper đã được cung cấp trong `src/langgraph_agent_lab/llm.py` - file này đọc API key từ `.env` và trả về một LangChain chat model.

```bash
# Cài provider LLM bạn muốn dùng
pip install langchain-openai    # cho OpenAI
# HOẶC
pip install langchain-anthropic  # cho Anthropic

# Cấu hình .env
cp .env.example .env
# Sửa .env và đặt OPENAI_API_KEY hoặc ANTHROPIC_API_KEY
```

---

## Hiểu về `scenarios.jsonl`

File `data/sample/scenarios.jsonl` chứa **7 sample scenario** mà graph của bạn phải xử lý:

```jsonl
{"id":"S01_simple",      "query":"How do I reset my password?",                          "expected_route":"simple"}
{"id":"S02_tool",        "query":"Please lookup order status for order 12345",            "expected_route":"tool"}
{"id":"S03_missing",     "query":"Can you fix it?",                                      "expected_route":"missing_info"}
{"id":"S04_risky",       "query":"Refund this customer and send confirmation email",      "expected_route":"risky"}
{"id":"S05_error",       "query":"Timeout failure while processing request",              "expected_route":"error"}
{"id":"S06_delete",      "query":"Delete customer account after support verification",    "expected_route":"risky"}
{"id":"S07_dead_letter", "query":"System failure cannot recover after multiple attempts", "expected_route":"error", "max_attempts":1}
```

### Ý nghĩa từng field

| Field | Mục đích |
|---|---|
| `id` | Mã định danh scenario duy nhất - dùng trong output metrics |
| `query` | Nội dung ticket hỗ trợ của người dùng - input cho graph |
| `expected_route` | Route mà `classify_node` của bạn nên chọn: `simple`, `tool`, `missing_info`, `risky`, hoặc `error` |
| `requires_approval` | Nếu là `true`, graph phải đi qua approval/HITL node trước khi trả lời |
| `should_retry` | Nếu là `true`, scenario mô phỏng lỗi tool tạm thời và cần retry |
| `max_attempts` | Ghi đè giới hạn retry (mặc định 3). S07 đặt giá trị này là 1, nên retry cạn ngay lập tức -> dead letter |
| `tags` | Nhãn mô tả để bạn tham khảo |

### Luồng scenario đi qua code

```text
scenarios.jsonl  ->  scenarios.py load dữ liệu  ->  cli.py chạy từng scenario qua graph
                                                   ->  metrics.py thu thập kết quả
                                                   ->  outputs/metrics.json
```

1. `make run-scenarios` đọc `data/sample/scenarios.jsonl`
2. Với mỗi scenario, chương trình gọi `initial_state(scenario)` -> `graph.invoke(state)`
3. Sau khi chạy xong, chương trình kiểm tra: `actual_route` có khớp `expected_route` không? HITL có được kích hoạt khi cần không?
4. Kết quả được ghi vào `outputs/metrics.json`

### Cách thiết kế classification

`classify_node` nên dùng LLM để phân loại intent. Hãy thiết kế prompt để route query:

| Route | Intent |
|---|---|
| `risky` | Hành động có side effect: refund, xóa dữ liệu, gửi email, hủy dịch vụ |
| `tool` | Tra cứu thông tin: trạng thái đơn hàng, tracking, search query |
| `missing_info` | Query mơ hồ/chưa đầy đủ, thiếu context để hành động |
| `error` | Lỗi hệ thống: timeout, crash, service unavailable |
| `simple` | Câu hỏi chung có thể trả lời không cần tool hoặc action |

**Thứ tự ưu tiên rất quan trọng**: risky > tool > missing_info > error > simple. Hãy thiết kế prompt LLM để tôn trọng thứ tự ưu tiên này.

### Thêm test scenario của riêng bạn

Bạn có thể thêm dòng mới vào `scenarios.jsonl` để test edge case:

```jsonl
{"id":"S08_custom","query":"Cancel my subscription immediately","expected_route":"risky","requires_approval":true,"tags":["custom"]}
```

Script chấm điểm cũng sẽ test bằng các scenario bạn chưa nhìn thấy.

---

## Quick start

```bash
# Option A: conda
conda activate ai-lab
pip install -e '.[dev]'
pip install langchain-openai  # hoặc langchain-anthropic

# Option B: venv
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pip install langchain-openai  # hoặc langchain-anthropic

# Cấu hình LLM
cp .env.example .env
# Sửa .env - đặt API key của bạn

# Kiểm tra setup
make test  # một số test sẽ fail cho đến khi bạn implement các TODO
```

---

## Workflow từng bước

### Phase 1: State + nodes (0-90 phút) - trị giá 30 điểm

1. **`state.py`** - Xem lại các field hiện có. Thêm field còn thiếu khi bạn phát hiện cần dùng:
   - `evaluation_result` cho gate của retry loop
   - `pending_question` cho luồng hỏi làm rõ
   - `proposed_action` cho luồng hành động rủi ro
   - `approval` cho quyết định HITL

2. **`llm.py`** - Xem lại helper. Cấu hình `.env` với API key của bạn.

3. **`nodes.py`** - Implement toàn bộ 10 node function:
   - `classify_node`: **LLM + structured output** để phân loại intent
   - `tool_node`: mock tool có mô phỏng lỗi
   - `evaluate_node`: kiểm tra chất lượng kết quả tool (LLM-as-judge cho bonus)
   - `answer_node`: câu trả lời **do LLM sinh ra** và có grounding
   - `ask_clarification_node`: tạo câu hỏi làm rõ
   - `risky_action_node`: chuẩn bị action để phê duyệt
   - `approval_node`: mock approval với `interrupt()` tùy chọn
   - `retry_or_fallback_node`: tăng bộ đếm attempt
   - `dead_letter_node`: xử lý khi vượt giới hạn retry
   - `finalize_node`: phát final audit event

### Phase 2: Routing + graph (90-150 phút) - trị giá 35 điểm

4. **`routing.py`** - Implement toàn bộ 4 routing function từ đầu
5. **`graph.py`** - Xây dựng StateGraph hoàn chỉnh:
   - Import và đăng ký toàn bộ 11 node
   - Wire fixed edge + conditional edge
   - Mọi path phải kết thúc ở finalize -> END
6. **Kiểm tra**: `make test` và `make run-scenarios`

### Phase 3: Persistence (150-180 phút) - trị giá 10 điểm

7. **`persistence.py`** - Implement SQLite checkpointer
   - Đưa ra bằng chứng: mỗi lần chạy có `thread_id`, state history hoặc crash-resume

### Phase 4: Metrics & report (180-240 phút) - trị giá 25 điểm

8. **`report.py`** - Implement `render_report()` từ metrics data
9. **Chạy**: `make run-scenarios` -> `outputs/metrics.json`
10. **Validate**: `make grade-local`
11. **Report**: Điền `reports/lab_report.md`

### Phase 5: Extensions (240+ phút) - hướng tới 90+ điểm

Chọn một hoặc nhiều mục:
- **Parallel fan-out**: Dùng `Send()` để gọi tool song song
- **Real HITL**: `LANGGRAPH_INTERRUPT=true` với `interrupt()`
- **Streamlit UI**: Xây giao diện approval/reject
- **Time travel**: replay bằng `get_state_history()`
- **Crash recovery**: SQLite checkpoint vẫn tồn tại sau khi process bị kill
- **Graph diagram**: `graph.get_graph().draw_mermaid()`

---

## Lệnh Make

| Command | Chức năng |
|---|---|
| `make install` | Cài project + dev dependencies |
| `make test` | Chạy pytest |
| `make lint` | Chạy ruff linter |
| `make typecheck` | Chạy mypy type checker |
| `make run-scenarios` | Chạy toàn bộ scenario -> `outputs/metrics.json` |
| `make grade-local` | Validate schema của `metrics.json` |
| `make clean` | Xóa cache và file sinh ra |

---

## Checklist nộp bài

- [ ] Đã implement toàn bộ phần `TODO(student)`
- [ ] `.env` đã cấu hình LLM API key
- [ ] `classify_node` dùng lệnh gọi LLM thật với structured output
- [ ] `answer_node` dùng lệnh gọi LLM thật để tạo câu trả lời có grounding
- [ ] `make test` pass
- [ ] `make run-scenarios` tạo `outputs/metrics.json` hợp lệ
- [ ] `make grade-local` pass validation
- [ ] `reports/lab_report.md` hoàn thành với kiến trúc, metrics và phân tích
- [ ] Có thể giải thích ít nhất một route và một failure mode khi demo

**Để đạt 90+ điểm, cần thêm:**
- [ ] Ít nhất một bonus extension (persistence, parallel fan-out, HITL, time travel, diagram)
- [ ] Có bằng chứng về extension trong report (screenshot, log output hoặc diagram)

---

## Lỗi thường gặp

1. **Thiếu state field**: Starter cố ý bỏ thiếu một số field trong `AgentState`. Bạn phải thêm `evaluation_result`, `pending_question`, `proposed_action` và `approval` khi implement các node cần dùng chúng.

2. **LLM structured output**: Dùng `.with_structured_output(YourModel)` để classification ổn định. Parse raw text rất dễ lỗi và sẽ fail với hidden test scenario.

3. **Retry không giới hạn**: Luôn kiểm tra `attempt < max_attempts` trong `route_after_retry`. Nếu không có giới hạn này, error scenario sẽ loop mãi.

4. **Graph wiring**: Mọi path phải kết thúc tại `finalize -> END`. Nếu thiếu, graph sẽ bị treo với một số scenario.

5. **SqliteSaver API**: Trong `langgraph-checkpoint-sqlite` 3.x, dùng `SqliteSaver(conn=sqlite3.connect(...))`, không dùng `SqliteSaver.from_conn_string()`.

6. **Chưa đặt API key**: Nếu gặp lỗi "No LLM API key found", kiểm tra file `.env` và đảm bảo file được load (dùng `python-dotenv` hoặc export thủ công).
