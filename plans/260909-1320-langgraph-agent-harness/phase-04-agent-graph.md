---
phase: 4
title: "Đồ thị Agent LangGraph"
status: completed
priority: P1
effort: "3d"
dependencies: [2, 3]
---

# Phase 4: Đồ thị Agent LangGraph

## Overview

Thay vòng lặp ReAct thủ công bằng `StateGraph` của LangGraph. Điểm cốt lõi: **model không còn chọn
tool**. Một bộ định tuyến tất định (regex) hợp với một bộ định tuyến LLM quyết định cần tra cứu gì,
các node truy xuất chạy song song, bằng chứng được đóng gói theo ngân sách token, rồi model chỉ làm
đúng một việc cuối cùng là viết câu trả lời — với **không tool nào được bind**.

## Requirements

**Chức năng**
- `StateGraph` với các node: `normalize`, `route`, 4 node truy xuất song song, `rerank`, `compact`,
  `synthesize`. (Node `verify`/`repair` thuộc Phase 5.)
- Định tuyến hợp nhất: regex prior là nền, LLM chỉ được **thêm** ý định.
- Fan-out song song và fan-in qua reducer, không chạy tuần tự.
- Đóng gói bằng chứng theo ngân sách token cứng, gộp chỉ dẫn thành một khối duy nhất.
- Phát đủ hợp đồng SSE 14 sự kiện qua `get_stream_writer()` + `stream_mode=["custom","messages"]`.
- `src/agent.py` giữ nguyên chữ ký `stream_agent()` / `run_agent()` để `api_server` và CLI không đổi.

**Phi chức năng**
- `/api/ask` chuyển sang `async def`; SSE không được mất token hay treo.
- Đồ thị không có cạnh nào cho phép lặp vô hạn; mọi vòng đều có bộ đếm chặn.
- Chạy được với model không hỗ trợ function calling (không node nào bắt buộc phải có tool calling).

## Architecture

### State — `src/graph/state.py`

```python
class Evidence(TypedDict):
    source: Literal["penalty", "law", "sign", "speed"]
    parent_id: str
    doc_id: str
    citation: str
    header: str
    content: str
    snippet: str
    score: float
    image_path: str | None
    raw_tool_output: str      # nguyên văn, để answer_guard đối chiếu ở Phase 5

class LegalAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    grounding_query: str
    history_summary: str
    route: RouteDecision
    evidence: Annotated[list[Evidence], operator.add]   # reducer cho fan-in song song
    packed_context: str
    answer: str
    issues: list[str]
    repair_count: int
    sources: list[dict]
    agent_steps: list[dict]
    model_used: str
```

`evidence` dùng reducer `operator.add` — đây là điều kiện để 4 node truy xuất ghi đồng thời mà không
đè lên nhau. Đúng cảnh báo của LangChain: phần lớn sự cố production đến từ thiết kế state sai, và
fan-in không có reducer là dạng sai phổ biến nhất.

### Node `normalize` (tất định, không gọi LLM)

Port nguyên logic câu hỏi nối tiếp đang có ở `src/agentic_rag.py:~700`: câu hỏi <= 6 từ hoặc khớp
`^(vậy\s+)?còn\b|^thế\s+(còn|thì)\b` thì ghép với câu hỏi trước để tạo `grounding_query`. Thêm
`expand_query()` từ `vi_text.py`.

### Node `route` — trái tim của thiết kế cho model nhỏ

```python
class RouteDecision(BaseModel):
    intents: list[Literal["penalty", "law", "sign", "speed"]]
    doc_scope: Literal["all", "luat", "nghi_dinh", "thong_tu", "quy_chuan"] = "all"
    vehicles: list[Literal["o_to", "xe_may", "xe_dap", "khac"]] = []
    search_query: str
```

Chạy hai nguồn rồi **hợp**:

```
regex_intents = detect_by_regex(grounding_query)     # tất định, đã có sẵn trong code cũ
llm_route     = structured_call(router_model, RouteDecision, prompt)   # có thể trả None

intents = regex_intents ∪ (llm_route.intents if llm_route else ∅)
if not intents: intents = {"law"}          # mặc định an toàn: luôn tra ngữ nghĩa
vehicles = regex_vehicles ∪ (llm_route.vehicles if llm_route else ∅)
```

Các mẫu regex đã có sẵn và đã được kiểm chứng trong nhánh `needs_grounding` hiện tại: biển báo
(`biển\s*(báo|cấm|hiệu lệnh...)|[PWIROS]\.\d+|vạch`), tốc độ (`tốc\s*độ|km/h|khoảng cách an toàn`),
mức phạt (`penalties.search()` trả kết quả). Chúng chuyển từ vai trò "cứu hộ khi model không gọi
tool" thành **nguồn định tuyến chính**.

Vì sao hợp chứ không thay: model nhỏ hay **bỏ sót** ý định (hỏi "vượt đèn đỏ phạt bao nhiêu" mà chỉ
định tuyến `law`), hiếm khi thêm ý định vô lý. Phép hợp làm lỗi bỏ sót không thể xảy ra, còn lỗi
thừa chỉ tốn thêm một lượt truy xuất rẻ. Đổi lại, khi LLM router chết hoàn toàn, hệ thống vẫn chạy
đúng bằng regex.

### Fan-out truy xuất song song

```
route ──┬──> retrieve_penalty  (nếu "penalty" ∈ intents)
        ├──> retrieve_law      (luôn chạy)
        ├──> retrieve_sign     (nếu "sign" ∈ intents)
        └──> retrieve_speed    (nếu "speed" ∈ intents)
                    │
                    └──> rerank (fan-in qua reducer evidence)
```

Dùng `add_conditional_edges` trả về danh sách tên node để LangGraph chạy song song. Hiện tại 4 tool
chạy **tuần tự**, mỗi cái một vòng LLM — kiến trúc mới cắt hẳn 3 vòng LLM và chạy I/O song song.

`retrieve_law` luôn chạy: mọi câu trả lời pháp lý đều cần căn cứ Điều luật gốc, và nó thay thế cơ
chế "chèn tra cứu bắt buộc" đang có, nhưng ở tầng kiến trúc thay vì bằng nhánh vá.

### Node `compact` — kỹ thuật ngữ cảnh cho model nhỏ

Vấn đề đang có: mỗi tool result đính kèm nguyên khối `FIGURE_LOCK_NOTE` (~15 dòng). Gọi 4 tool là 60
dòng chỉ dẫn lặp lại xen giữa dữ liệu pháp lý. Model nhỏ có cửa sổ chú ý hẹp — lặp chỉ dẫn không làm
nó tuân thủ hơn, chỉ đẩy dữ liệu thật ra xa.

Quy tắc đóng gói:

| Hạng | Nội dung đưa vào |
|---|---|
| Rank 1 mỗi nguồn | Toàn văn parent, cắt ở 2500 ký tự (bằng `PARENT_CONTENT_LIMIT` hiện tại) |
| Rank 2-3 | Chỉ `key_clauses`, tối đa 2 khoản |
| Rank >= 4 | Chỉ một dòng `citation` + tiêu đề |
| Kết quả phạt | Giữ đủ trường (loại xe, trích dẫn, hành vi, mức tiền, điểm trừ) — đây là dữ liệu số, không được cắt |

Ngân sách tổng `CONTEXT_TOKEN_BUDGET` mặc định 6000 token, cắt từ hạng thấp lên. Khối chỉ dẫn
(`FIGURE_LOCK_NOTE` rút gọn) xuất hiện **đúng một lần**, đặt ngay sát trước câu hỏi ở cuối prompt —
vị trí mà model nhỏ bám chắc nhất.

### Node `synthesize` — không bind tool

Gọi `get_chat_model("synthesize")` **không có** `.bind_tools()`. Hệ quả trực tiếp: model nhỏ không
thể sinh tool call hỏng, không thể lặp vô hạn, không thể rò thẻ DSML. Toàn bộ `_parse_raw_dsml_tool_calls()`,
`_ToolCallOverflow`, `MAX_TOOL_CALLS_PER_TURN` trở nên vô nghĩa và bị xoá.

`_clean_text_output()` và `_polish_answer()` vẫn được port sang (model vẫn có thể mở đầu bằng "Theo
kết quả tra cứu..."), nhưng phần xử lý thẻ tool call thì bỏ.

Stream token qua `stream_mode="messages"`, gắn `phase="answer"` ngay từ đầu — vì kiến trúc mới đảm
bảo văn bản này chắc chắn là câu trả lời, không còn bản nháp.

### Ánh xạ sự kiện SSE — `src/graph/events.py`

```python
def emit(event_type: str, message: str = "", **payload) -> None:
    writer = get_stream_writer()
    writer({"event": event_type, "message": message,
            "timestamp": time.strftime("%H:%M:%S"), **payload})
```

Giữ nguyên hình dạng dict của `_event()` hiện tại. `api_server` tiêu thụ:

```python
async for mode, chunk in graph.astream(inputs, config, stream_mode=["custom", "messages"]):
    if mode == "custom":
        yield _sse(chunk)
    elif mode == "messages":
        msg, meta = chunk
        if meta["langgraph_node"] == "synthesize" and msg.content:
            yield _sse({"event": "token", "message": msg.content, "phase": "answer"})
```

## Related Code Files

- Create: `src/graph/__init__.py`, `state.py`, `router.py`, `retrieve.py`, `rerank_node.py`,
  `compact.py`, `synthesize.py`, `events.py`, `build.py`
- Create: `src/agent.py` — façade giữ chữ ký `stream_agent()` / `run_agent()`
- Create: `src/prompts/system_vi.py` — system prompt rút từ `_build_system_prompt()`, cắt phần mô tả
  tool (không còn tool để mô tả)
- Create: `tests/test_router.py`, `tests/test_compact.py`, `tests/test_graph_sse.py`
- Modify: `src/api_server.py` — `/api/ask` thành `async def`, dùng `graph.astream()`. Đồng thời tách rời các endpoint `/api/penalties` và `/api/health` nạp trực tiếp `PenaltyLookup` và `DocumentProvider` độc lập (giải phóng liên kết với `get_agent().tools_handler`)
- Modify: `main.py` — chế độ CLI gọi `src/agent.py`
- Read-only: `src/agentic_rag.py` (nguồn để port logic), `static/js/agent-trace.js`, `static/js/chat.js`

## Implementation Steps

<!-- Updated: Validation Session 1 - Decouple api_server.py endpoints from Agent tools_handler -->
1. Viết `state.py` với reducer đúng cho `evidence` và `messages`. Test riêng: hai node ghi song song
   phải cộng dồn, không đè.
2. Viết `router.py`: tách `detect_by_regex()` thành hàm thuần test được, rồi ghép với
   `structured_call()`. Viết `tests/test_router.py` với >= 20 câu mẫu phủ cả 4 ý định + câu nối tiếp
   + trường hợp LLM trả `None`.
3. Viết `retrieve.py`: 4 node gọi tầng lai của Phase 3, mỗi node emit `tool_call` trước và
   `tool_result` sau, giữ nguyên câu chữ mô tả tiếng Việt của `_format_tool_explanation()` và
   `_summarize_tool_result()` để giao diện trace không đổi giọng.
4. Viết `compact.py` với bảng ngân sách ở trên. `tests/test_compact.py` khẳng định: (a) không vượt
   ngân sách token, (b) khối chỉ dẫn xuất hiện đúng một lần, (c) dữ liệu số của kết quả phạt không
   bao giờ bị cắt.
5. Viết `synthesize.py` và `src/prompts/system_vi.py`. Giữ nguyên mọi quy tắc định dạng đầu ra đang
   có (tiêu đề `###`, ảnh Markdown biển báo, khối "Căn cứ pháp lý trích dẫn", phân tích đa phương
   tiện) — đó là hợp đồng với giao diện và với người dùng.
6. Viết `build.py`: lắp `StateGraph`, `add_conditional_edges` cho fan-out, compile. Chưa gắn
   checkpointer (Phase 6).
7. Viết `events.py` và `src/agent.py`. `run_agent()` tiêu thụ chính `stream_agent()` như hiện tại để
   CLI và bộ eval dùng chung một đường.
8. Sửa `/api/ask` thành `async def`. Đồng thời tái cấu trúc `/api/penalties` và `/api/health` trong
   `src/api_server.py` để nạp trực tiếp `PenaltyLookup` và `DocumentProvider`, không còn phụ thuộc vào
   `get_agent().tools_handler`. Viết `tests/test_graph_sse.py` khẳng định đủ thứ tự sự kiện:
   `start` -> `turn_start` -> `tool_call`+ -> `synthesizing` -> `token`+ -> `answer_commit` -> `done`.
9. Thêm `GraphAdapter` vào `scripts/eval/adapters.py`, chạy `e2e_eval.py --adapter graph --quick`,
   so với baseline.
10. Kiểm bằng mắt trên giao diện thật: chat, trace, chip nguồn, ảnh biển báo, nút Google.

## Success Criteria

- [x] Đồ thị chạy trọn vẹn một câu hỏi và phát đủ chuỗi sự kiện SSE theo đúng thứ tự
- [x] 4 node truy xuất chạy **song song** (xác nhận bằng dấu thời gian trong trace)
- [x] Một lượt hỏi tốn tối đa 3 lệnh gọi LLM (route + rerank + synthesize), giảm từ 4-8 lệnh hiện tại
- [x] `tests/test_router.py` >= 20 ca xanh, gồm ca LLM trả `None` (30/30 passed)
- [x] `compact` không bao giờ vượt `CONTEXT_TOKEN_BUDGET`; dữ liệu số của kết quả phạt còn nguyên
- [x] Giao diện chạy đúng **không sửa một dòng JS nào**
- [x] `scripts/verify_agentic_rag.py` chuyển sang adapter mới: 5/5 pass (100% đạt)
- [x] `e2e_eval.py --adapter graph --quick` không tệ hơn baseline ở mọi chỉ số (0% lỗi số liệu)
- [x] Không còn mã nào xử lý tool call hỏng / DSML trong đường đi mới

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| Bỏ tool-calling làm mất khả năng tra cứu nhiều bước ("tra Điều 57 rồi tra tiếp mức phạt") | Bộ eval cho thấy nhóm câu hỏi ghép bị tụt | Node `route` được phép sinh nhiều ý định cùng lúc, phủ phần lớn ca ghép. Nếu vẫn thiếu, thêm **một** cạnh có điều kiện `synthesize -> route` giới hạn đúng 1 vòng, dựa trên tín hiệu tất định (câu trả lời thừa nhận thiếu dữ liệu) chứ không dựa vào model tự xin |
| `stream_mode="messages"` không lọc được đúng node | Token của node `route` lọt vào ô câu trả lời | Lọc theo `meta["langgraph_node"] == "synthesize"`; có test riêng cho đúng việc này |
| Đổi `/api/ask` sang async làm hỏng SSE trên Windows | Trình duyệt treo spinner | Giữ nguyên `StreamingResponse` + header `X-Accel-Buffering: no`; test bằng `httpx.AsyncClient` đọc từng dòng |
| System prompt rút gọn làm mất quy tắc định dạng | Câu trả lời mất khối "Căn cứ pháp lý trích dẫn" hoặc mất ảnh biển báo | Chỉ cắt phần **mô tả tool**; mọi quy tắc định dạng giữ nguyên câu chữ. Bộ eval có ca kiểm ảnh biển báo (TC1) |
| Ngân sách token cắt nhầm bằng chứng cần thiết | Tỉ lệ câu trả lời bị huỷ ở Phase 5 tăng | Cắt từ hạng thấp lên và không bao giờ cắt dữ liệu số; theo dõi tỉ lệ huỷ như chỉ số cảnh báo sớm |
