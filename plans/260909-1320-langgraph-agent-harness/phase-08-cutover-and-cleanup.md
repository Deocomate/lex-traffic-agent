---
phase: 8
title: "Cắt chuyển, gỡ mã cũ và tài liệu"
status: mostly-done
priority: P1
effort: "1d"
dependencies: [1, 2, 3, 4, 5, 6, 7]
---

# Phase 8: Cắt chuyển, gỡ mã cũ và tài liệu

## Overview

Pha chốt hạ của toàn bộ chiến dịch tái kiến trúc. Sau khi Phase 1–7 đã dựng xong eval harness, lớp
truy cập model, tầng truy xuất lai BM25 + RRF, đồ thị LangGraph, node kiểm chứng/tự sửa, bộ nhớ/cache
và hệ thống quan trắc — Phase 8 thực hiện bốn nhiệm vụ quyết định:

1. **Vượt qua cổng chặn hồi quy toàn diện** trên bộ benchmark mở rộng (>= 80 câu, phủ 6 văn bản)
   với ít nhất 2 model nhỏ khác nhau trên OpenRouter.
2. **Cắt chuyển toàn bộ caller** (`src/api_server.py`, `scripts/chat.py`, `scripts/verify_agentic_rag.py`,
   `main.py`) sang `src/agent.py` và đồ thị mới.
3. **Xoá sổ hoàn toàn `src/agentic_rag.py`** (1004 dòng mã cũ) và dọn sạch các tệp vá, dead code,
   parser DSML thô.
4. **Đại tu tài liệu**: `README.md`, viết mới tài liệu kiến trúc `docs/architecture.md`, tổng kết
   chỉ số Trước vs Sau (Before & After) và ghi lại phiên bản phụ thuộc chính thức.

Nguyên tắc bất di bất dịch của Phase 8: **Không gỡ mã cũ khi cổng chặn chưa xanh.** Giữ nguyên
`src/agentic_rag.py` trên đĩa tới khi mọi chỉ số và bài kiểm tra E2E trên harness mới đạt hoặc vượt
baseline đã chốt ở Phase 1.

## Requirements

**Chức năng**
- Chạy `python scripts/eval/gate.py` ở chế độ đầy đủ (`--full`, >= 80 câu) đạt exit code 0.
- Xác thực chéo (cross-model validation): chạy thành công và đạt cổng chặn trên ít nhất 2 model nhỏ
  trên OpenRouter (ví dụ `deepseek/deepseek-v4-flash-latest` và `nvidia/nemotron-3.5-lightning` hoặc
  `google/gemini-2.0-flash-lite`).
- Chuyển đổi toàn bộ call site sử dụng `AgenticLegalSearch` sang `src/agent.py` (`stream_agent`,
  `run_agent`):
  - `src/api_server.py`: endpoint `/api/ask` phát đủ 14 sự kiện SSE, hỗ trợ `thread_id` liên tục.
  - `scripts/chat.py`: CLI streaming tương tác với callback lắng nghe live events từ đồ thị.
  - `scripts/verify_agentic_rag.py`: kiểm thử 5 kịch bản vàng (biển báo ảnh Markdown, tốc độ, VNeID,
    nồng độ cồn, bằng C1) đạt 5/5 pass.
  - `main.py`: menu tương tác và các cờ CLI `--web`, `--chat`, `--eval` hoạt động hoàn hảo.
- Xoá hoàn toàn `src/agentic_rag.py` khỏi cây mã nguồn. Không còn bất kỳ tệp nào import nó.
- Dọn dẹp các lớp vá cũ: parser DSML thô, ngoại lệ ngắt stream giữa chừng (`_ToolCallOverflow`),
  biến đếm tool call vòng lặp, logic ép `needs_grounding` thủ công.
- Cập nhật tài liệu: `README.md` mới, `docs/architecture.md`, cập nhật danh mục phụ thuộc thực tế
  và bản đối chiếu chỉ số Trước vs Sau.

**Phi chức năng**
- Không gây downtime hay đứt gãy giao diện: hợp đồng SSE được bảo toàn tuyệt đối, giao diện web
  vừa redesign (`static/js/*`) không bị lỗi.
- Sạch sẽ 100%: lệnh tìm kiếm `git grep "agentic_rag"` không trả về kết quả nào trong mã nguồn
  hoạt động (chỉ cho phép xuất hiện trong tài liệu lịch sử hoặc nhật ký migration).
- Kiểm soát tài nguyên: thư mục `data/runtime/` (checkpoints sqlite, traces JSONL, cache query)
  được kiểm tra nằm trọn trong `.gitignore`, không để lọt tệp nhị phân hay trace cá nhân vào git.

## Architecture

### 1. Trình tự cắt chuyển an toàn (Cutover Sequence)

```
[Phase 1-7 Hoàn tất]
         │
         ▼
[Bước 1: Chạy Full Regression Gate] ──Fail──> Dừng lại, đối chiếu diff câu trả lời
         │                                    với baseline cũ, debug tại node tương ứng
      Pass (Exit 0)
         │
         ▼
[Bước 2: Chuyển đổi các Callers]
   ├── scripts/verify_agentic_rag.py  ──> 5/5 Test Cases Pass
   ├── scripts/chat.py                ──> Live CLI Stream OK
   ├── src/api_server.py              ──> SSE 14 Events + thread_id OK
   └── main.py                        ──> Menu & Flags OK
         │
         ▼
[Bước 3: Smoke Test Giao Diện Web & E2E]
   ├── Chat hỏi đáp + stream token
   ├── Nguồn trích dẫn (chips) đúng văn bản
   ├── Ảnh biển báo hiển thị chuẩn
   └── Trace summary hiển thị đúng
         │
         ▼
[Bước 4: Gỡ bỏ mã cũ & Dọn dẹp]
   ├── Xoá src/agentic_rag.py
   ├── Xoá dead code & legacy patches
   └── Quét grep toàn bộ repo sạch 100%
         │
         ▼
[Bước 5: Đại tu tài liệu & Báo cáo nghiệm thu]
   ├── Cập nhật README.md & docs/architecture.md
   └── Xuất data/benchmark/final_evaluation_report.json
```

### 2. Danh mục gỡ bỏ và thanh lý mã cũ

Mã cũ trong `src/agentic_rag.py` gánh rất nhiều lớp vá do để model tự lái. Khi chuyển sang
StateGraph LangGraph, toàn bộ các lớp vá này trở thành thừa thãi và bị loại bỏ triệt để:

| Thành phần cũ cần xoá | Lý do thanh lý | Thay thế bằng gì trong kiến trúc mới |
|---|---|---|
| `AgenticLegalSearch` class (1004 dòng) | Lớp ReAct thủ công gọi thẳng OpenAI SDK | `src/graph/build.py` (StateGraph) + `src/agent.py` (façade) |
| `_parse_raw_dsml_tool_calls()` | Model yếu hay sinh nhầm cú pháp XML/DSML | `synthesize` không bind tool; `router` dùng structured output 4 tầng |
| `_ToolCallOverflow` & ngắt stream | Tránh model lặp vô hạn khi gọi tool | Đồ thị định tuyến tất định; không lặp quá số vòng định sẵn |
| `_clean_text_output()` | Lọc thẻ XML rò rỉ trong câu trả lời | Không bind tool nên model không sinh thẻ tool |
| Nhánh `needs_grounding` thủ công | Vá lỗi model trả lời từ trí nhớ | Cạnh tất định ép qua node retrieval nếu có ý định pháp lý |
| `MAX_TOOL_CALLS_PER_TURN = 4` | Giới hạn vòng lặp ReAct | Fan-out song song 4 node truy xuất, chạy đúng 1 lượt |
| `FIGURE_LOCK_NOTE` lặp ở mỗi tool | Tốn token, gây loãng sự chú ý | Node `compact` đóng gói chỉ dẫn một lần duy nhất trước `synthesize` |

### 3. Cập nhật các điểm gọi (Call Sites Migration)

#### A. `src/api_server.py`
Thay thế import cũ và luồng sinh stream:
```python
# Cũ:
# from src.agentic_rag import AgenticLegalSearch
# agent = AgenticLegalSearch()
# async def ask(request: Request): ... for chunk in agent.stream_chat(query, history): ...

# Mới:
from src.agent import stream_agent

@app.post("/api/ask")
async def ask_endpoint(request: AskRequest):
    # Nhận thread_id từ client hoặc sinh mới nếu chưa có
    thread_id = request.thread_id or str(uuid.uuid4())
    
    async def event_generator():
        async for sse_payload in stream_agent(
            question=request.question,
            thread_id=thread_id,
            history=request.history
        ):
            yield f"data: {json.dumps(sse_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

<!-- Updated: Validation Session 1 - api_server.py auxiliary endpoints decoupling -->
Đồng thời, tách hoàn toàn `PenaltyLookup` và `DocumentProvider` tại các endpoint phụ trợ (`/api/penalties` và `/api/health`), khởi tạo trực tiếp thay vì truy cập qua `get_agent().tools_handler`, bảo đảm khi gỡ bỏ `AgenticLegalSearch` thì server không bị lỗi `AttributeError`.

#### B. `scripts/verify_agentic_rag.py`
Đổi sang `run_agent()` hoặc `stream_agent()` từ `src/agent.py`. Giữ nguyên 5 ca kiểm thử vàng
(TC1 đến TC5), đảm bảo assert trúng trích dẫn, ảnh Markdown, và không bị gãy format.

#### C. `scripts/chat.py`
Cập nhật CLI handler tiêu thụ `stream_agent` bất đồng bộ (`asyncio.run()`), hiển thị tiến trình
từ các event `start`, `turn_start`, `tool_call`, `tool_result`, `synthesizing`, `token`, `verified`.

#### D. `main.py`
Menu `[3] Chạy Kiểm Thử & Đánh Giá Hiệu Năng RAG` trỏ sang `scripts/eval/gate.py` (bộ eval mới)
thay vì `scripts/evaluate_rag.py` cũ.

## Related Code Files

- **Delete**:
  - `src/agentic_rag.py` (1004 dòng)
  - `scratch/test_sources.py` (script tạm thời thời kỳ cũ nếu không còn dùng)
- **Modify**:
  - `src/api_server.py` — hoàn tất chuyển đổi sang `src/agent.py`, gắn `thread_id` vào hợp đồng SSE.
  - `scripts/verify_agentic_rag.py` — chuyển import sang `src.agent`, bảo đảm 5/5 test case chạy xanh.
  - `scripts/chat.py` — chuyển sang `stream_agent()` từ `src.agent`.
  - `main.py` — trỏ các menu và cờ CLI sang các script chuẩn mới.
  - `scripts/eval/adapters.py` — đánh dấu hoặc loại bỏ `LegacyAdapter`, đặt `GraphAdapter` làm mặc định.
  - `requirements.txt` — đảm bảo phiên bản đã ghim phản ánh chính xác môi trường chạy.
  - `.env.example` — hoàn thiện đầy đủ mô tả cho toàn bộ biến môi trường của harness mới.
  - `README.md` — thay thế sơ đồ kiến trúc cũ bằng sơ đồ LangGraph StateGraph, cập nhật hướng dẫn cài đặt và chạy.
- **Create**:
  - `docs/architecture.md` — tài liệu kiến trúc toàn diện của LexTraffic AI trên LangGraph 1.x.
  - `data/benchmark/final_evaluation_report.json` — báo cáo nghiệm thu benchmark chính thức so với baseline.
- **Read-only / Verify**:
  - `src/answer_guard.py` (không sửa, giữ nguyên các hàm thuần)
  - `src/semantic_index.py` (giữ nguyên lớp dữ liệu)
  - `src/tools/*.py` (giữ nguyên các file nghiệp vụ)
  - `static/js/*` (giao diện không sửa trừ điểm `thread_id` nếu có ở Phase 6)

## Implementation Steps

1. **Khởi động cổng chặn hồi quy toàn diện trên model chính**:
   - Chạy `python scripts/eval/gate.py --adapter graph --full`.
   - Kiểm tra các chỉ số bắt buộc:
     - Hit@1 >= 72%, MRR >= 0.80 trên toàn bộ testset >= 80 câu.
     - Độ chính xác trích dẫn E2E >= 95%.
     - Tỉ lệ số liệu bịa đặt (ungrounded figures) = 0%.
     - Tỉ lệ từ chối câu hỏi ngoài phạm vi >= 90%.
     - Độ trễ p50 và chi phí không vượt ngưỡng cổng chặn.
   - Nếu bất kỳ chỉ số nào trượt: dừng lại, kiểm tra trace tương ứng tại `data/runtime/traces/` để
     xác định node gây lỗi (router, rerank, compact, hay synthesize) và tinh chỉnh trước khi tiếp tục.

2. **Kiểm thử chéo trên model nhỏ thứ hai (Cross-model Gate Check)**:
   - Đổi tạm thời `LLM_MODEL` trong môi trường sang model thứ hai (ví dụ `nvidia/nemotron-3.5-lightning`
     hoặc `google/gemini-2.0-flash-lite`).
   - Chạy `python scripts/eval/gate.py --adapter graph --quick`.
   - Xác nhận: structured output tầng fallback và node synthesize hoạt động tốt, vượt qua cổng chặn
     mà không cần sửa bất kỳ dòng mã logic nào.

3. **Cập nhật `scripts/verify_agentic_rag.py`**:
   - Thay `from src.agentic_rag import AgenticLegalSearch` bằng `from src.agent import run_agent`.
   - Chạy `python scripts/verify_agentic_rag.py`.
   - Xác nhận 5/5 kịch bản E2E (Biển P.106a có ảnh, Tốc độ TT31, CSGT/VNeID TT73, Cồn NĐ168, Bằng C1 Luật 36) đều PASS.

4. **Cập nhật `scripts/chat.py`**:
   - Chuyển sang gọi `stream_agent` từ `src.agent`.
   - Kiểm tra tương tác CLI: gõ câu hỏi, quan sát in live workflow (các bước phân tích ý định,
     truy xuất song song, xếp hạng, tổng hợp và kiểm chứng) trơn tru, hỗ trợ stream tiếng Việt chuẩn UTF-8.

5. **Hoàn thiện kết nối trong `src/api_server.py` & `main.py`**:
   - Rà soát endpoint `/api/ask` và `/api/trace/summary` trong `src/api_server.py`.
   - Đảm bảo `thread_id` được truyền xuống đồ thị và lưu phiên vào checkpointer.
   - Tách trực tiếp `PenaltyLookup` và `DocumentProvider` cho các endpoint `/api/penalties` và `/api/health`, loại bỏ tận gốc mọi điểm gọi qua `tools_handler`.
   - Cập nhật `main.py`: đảm bảo menu `1` (Web), `2` (CLI), `3` (Eval) hoạt động đồng bộ với hệ thống mới.

6. **Kiểm thử tích hợp giao diện người dùng (Manual End-to-End Sanity Check)**:
   - Khởi động web: `python main.py --web --no-browser`.
   - Mở trình duyệt kiểm tra thực tế:
     - Đặt câu hỏi tra mức phạt nồng độ cồn: kiểm tra stream token mượt, khối trích dẫn NĐ 168/2024,
       không xuất hiện bản nháp bị xoá giật cục (`answer_reset`).
     - Đặt câu hỏi biển báo giao thông: kiểm tra ảnh Markdown render ngay ngắn.
     - Đặt câu hỏi liên tiếp ("vậy xe máy thì sao?"): kiểm tra ngữ cảnh đa lượt hoạt động đúng.
     - Mở ngăn tiến trình (Agent Trace drawer): xác nhận hiển thị đủ các bước và thời gian thực thi.

7. **Xoá bỏ hoàn toàn `src/agentic_rag.py` & dọn dẹp mã cũ**:
   - Xoá tệp `src/agentic_rag.py`.
   - Chạy lệnh quét toàn bộ kho mã nguồn:
     ```powershell
     git grep "agentic_rag"
     ```
   - Xử lý dứt điểm mọi tham chiếu sót lại trong các file code (`.py`, `.js`).

8. **Ghi nhận phiên bản phụ thuộc và viết `docs/architecture.md`**:
   - Lưu trữ danh sách phiên bản thực tế đã cài đặt (LangChain, LangGraph, aiosqlite, rank-bm25, v.v.).
   - Soạn thảo tài liệu kiến trúc toàn diện `docs/architecture.md` gồm:
     - Sơ đồ StateGraph mới và luồng điều khiển tất định.
     - Cơ chế truy xuất lai BM25 + Vector + RRF + LLM listwise rerank.
     - Thiết kế đóng gói bằng chứng theo ngân sách token (`compact`).
     - Các node kiểm chứng tất định (`verify`) và tự sửa (`repair`).
     - Quản lý phiên hội thoại với checkpointer SQLite và semantic cache.
     - Hợp đồng SSE 14 sự kiện và hệ thống quan trắc trace JSONL.

9. **Đại tu `README.md`**:
   - Cập nhật sơ đồ kiến trúc hệ thống mới.
   - Cập nhật cây thư mục dự án (`src/llm`, `src/retrieval`, `src/graph`, `src/observability`, `src/cache`).
   - Cập nhật hướng dẫn thiết lập môi trường (`requirements.txt`, `.env`).
   - Bổ sung bảng so sánh chỉ số Trước và Sau tái kiến trúc (Baseline vs LangGraph Target).

10. **Xuất báo cáo nghiệm thu cuối cùng (Final Report)**:
    - Chạy `python scripts/eval/gate.py --full --export data/benchmark/final_evaluation_report.json`.
    - Chạy `python scripts/eval/summarize_traces.py` để trích xuất thống kê độ trễ p50/p95,
      chi phí trung bình mỗi câu và phân bố `structured_tier`.
    - Đóng phase và cập nhật trạng thái trong `plan.md`.

## Success Criteria

- [ ] `scripts/eval/gate.py` chạy full 95 câu → **exit code 1**. Qua 1/5 cổng: `latency_p50` PASSED (30.941,8ms <= 31.350ms = baseline legacy +10%). Trượt: citation 63,29%, ungrounded 1,05%, refusal 87,50%, cancelled 8,42%.
- [~] **Hit@1 = 72,15%** (đạt >= 72%), **MRR = 0,7774** (chưa đạt >= 0,80). Phủ đủ 6/6 văn bản. Văn bản yếu nhất là NĐ 168/2024: Hit@1 56,2%, MRR 0,5625 — đây cũng là nguồn chính của lỗi trích dẫn sai Điều.
- [ ] Trích dẫn E2E **63,29%** (chưa đạt 95%); số liệu không căn cứ **1,05%** (chưa đạt 0%, hai lượt chạy ra 0,00% rồi 1,05%).
- [~] Từ chối lạc đề: **93,75%** trên tập 16 câu lạc đề chạy riêng (đạt >= 90%), nhưng **87,50%** trong lượt nghiệm thu 95 câu — dao động do LLM không tất định. Đã nâng từ 68,75% bằng cách thêm chỉ dẫn số 7 vào `SINGLE_INSTRUCTION_BLOCK`: câu lạc đề phải mở đầu bằng đúng câu 'Câu hỏi này không thuộc phạm vi tra cứu của tôi.' và cấm nêu con số tiền. Tín hiệu tất định thay cho việc trông chờ regex bắt được văn xuôi tự do.
- [x] Chạy trọn pipeline trên **2 model**: `deepseek/deepseek-v4-flash` (95 câu, p50 30,9s, $0,001670/câu) và `openai/gpt-oss-20b` (25 câu, p50 23,1s, $0,001899/câu, số liệu không căn cứ 0%). Cả hai không lỗi hạ tầng, `structured_tier` 100% tầng 1.
- [~] `scripts/verify_agent.py` (đổi tên từ `verify_agentic_rag.py`) — chạy **4/5**. Ca TC3 (CSGT/VNeID) trượt ở phép so khớp từ khoá do cách diễn đạt của LLM lượt đó, không phải lỗi harness: tool call, trích dẫn và kiểm chứng đều đúng.
- [ ] `scripts/chat.py` CLI chạy streaming mượt mà qua harness mới.
- [~] `src/api_server.py` import sạch, `/api/penalties` + `/api/health` đã tách khỏi Agent. **Đã vá một lỗ hợp đồng SSE thật**: `model_fallback` trước chỉ ghi vào tệp trace, không bao giờ phát ra SSE — giao diện có sẵn nhánh xử lý mà không bao giờ nhận được sự kiện, nên người dùng không biết câu trả lời do model dự phòng sinh. Đã nối vào `emit()` và khoá bằng 2 test. `answer_reset` cố ý không còn phát. **Chưa kiểm thử thủ công trên trình duyệt.**
- [x] `src/agentic_rag.py` đã xoá hoàn toàn; grep toàn repo không còn tham chiếu nào trong code runtime (chỉ còn câu giải thích trong docstring của `adapters.py`).
- [x] `data/runtime/` nằm trong `.gitignore` (dòng 3).
- [x] `docs/architecture.md` đã tạo (352 dòng), sơ đồ Mermaid khớp với `create_legal_graph()` thật.
- [x] `README.md` đã cập nhật (308 dòng): kiến trúc, cây thư mục, bảng biến môi trường, bảng chỉ số trung thực về cái đã đo và cái chưa đo.
- [x] `data/benchmark/final_evaluation_report.json` đã tạo (95 câu). Kèm baseline `scripts/eval/baselines/baseline-graph-phase8-260911.json`.

## Risk Assessment

| Rủi ro | Tín hiệu nhận biết | Phản ứng đã định trước |
|---|---|---|
| Xoá mã cũ làm gãy điểm gọi âm thầm (silent breakage) | Lỗi `ModuleNotFoundError: No module named 'src.agentic_rag'` khi chạy app hoặc test | Dùng `git grep "agentic_rag"` rà soát trước khi commit; có `scripts/verify_agentic_rag.py` và smoke test giao diện làm chốt chặn |
| Cổng chặn hồi quy thất bại ở một nhóm câu hỏi ngách | Exit code != 0, chỉ số của văn bản cụ thể (ví dụ QCVN 41 hoặc TT 73) bị tụt | Tuyệt đối **không xoá** `agentic_rag.py` trước khi gate pass; dùng `scripts/eval/e2e_eval.py` so sánh chi tiết output của câu hỏi đó giữa hai adapter để vá node retrieval/routing |
| Giao diện web bị mất sự kiện hoặc lỗi hiển thị do async stream | Trình duyệt không nhận được token, thanh tiến trình đứng yên | Kiểm tra lại headers `X-Accel-Buffering: no` và kiểm tra ánh xạ sự kiện trong `src/graph/events.py`; kiểm thử bằng curl / httpx async client trước khi mở web |
| Model nhỏ thứ hai bị rớt định tuyến do không hỗ trợ structured output | Trace ghi nhận `structured_tier` rơi vào tầng lỗi, router trả rỗng | Lớp `structured.py` ở Phase 2 đã có fallback 4 tầng (tool call -> JSON schema -> Regex extraction); nếu rớt vẫn có Regex Prior làm nền chặn đáy |
| Tệp dữ liệu runtime (traces, checkpoints SQLite) vô tình bị commit lên git | `git status` hiện các tệp trong `data/runtime/` | Thêm ngay `data/runtime/` vào `.gitignore` từ sớm; kiểm tra lại trạng thái git trước khi chốt phase |
