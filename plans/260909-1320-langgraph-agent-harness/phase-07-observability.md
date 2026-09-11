---
phase: 7
title: "Quan trắc và truy vết"
status: completed
priority: P2
effort: "1d"
dependencies: [4]
---

# Phase 7: Quan trắc và truy vết

## Overview

Ghi lại từng node chạy gì, mất bao lâu, tốn bao nhiêu token và tiền, có trúng cache không, kiểm chứng
ra sao. Mục tiêu cụ thể và hẹp: **trả lời được câu hỏi "vì sao model nhỏ này trả lời sai câu đó"**
mà không phải chạy lại và đoán.

Mặc định ghi cục bộ ra JSONL. LangSmith là tuỳ chọn bật bằng biến môi trường — vì bật nó nghĩa là câu
hỏi của người dùng rời khỏi máy.

## Requirements

**Chức năng**
- `BaseCallbackHandler` ghi JSONL mỗi lượt chạy: một dòng cho mỗi node và mỗi lệnh gọi LLM.
- Trường bắt buộc: `run_id`, `thread_id`, `node`, `event`, `t_start`, `duration_ms`, `model`,
  `prompt_tokens`, `completion_tokens`, `cost_usd`, `cache_hit`, `structured_tier`, `error`.
- Trường theo ngữ cảnh: `route.intents`, số ứng viên trước/sau rerank, số issue trước/sau sửa, có
  fallback model hay không.
- LangSmith bật bằng `LANGSMITH_TRACING=true`, không cần đổi code.
- `scripts/eval/summarize_traces.py` tổng hợp: độ trễ p50/p95 theo node, chi phí trung bình mỗi câu,
  tỉ lệ trúng cache, phân bố tầng structured output, tỉ lệ fallback model.

**Phi chức năng**
- Ghi trace không được làm chậm đường chính: ghi đệm, xả theo lô, không chặn stream.
- Xoay vòng theo ngày, tự dọn tệp cũ hơn `TRACE_RETENTION_DAYS` (mặc định 14).
- Không ghi API key. Câu hỏi người dùng ghi ở dạng đầy đủ (cần để debug), nhưng chỉ nằm trong
  `data/runtime/traces/` và thư mục này đã bị `.gitignore`.

## Architecture

### Vì sao `structured_tier` là trường đáng giá nhất

Phase 2 dựng structured output bốn tầng. Trường `structured_tier` cho biết model đang dùng thực sự
"khoẻ" tới đâu về structured output: model luôn rơi xuống tầng 3 là model sẽ định tuyến kém, và bạn
biết điều đó **trước khi** thấy hậu quả trong chất lượng câu trả lời. Đây là chỉ số cảnh báo sớm rẻ
nhất khi đổi sang một model nhỏ mới trên OpenRouter.

### Bảng đơn giá

`src/observability/pricing.py` giữ một bảng `{model_id: (usd_per_1m_in, usd_per_1m_out)}` cho các
model đang dùng, kèm mặc định 0 cho model chưa biết (chi phí hiện là 0, không phải chi phí sai). Đây
là ước lượng cục bộ — con số quyết toán vẫn là hoá đơn OpenRouter, ghi rõ điều đó trong docstring để
không ai nhầm.

### Định dạng JSONL

```json
{"run_id":"...","thread_id":"...","node":"route","event":"node_end",
 "t_start":"2026-09-09T13:20:11.412+07:00","duration_ms":842,
 "model":"nvidia/nemotron-3.5-lightning","prompt_tokens":611,"completion_tokens":48,
 "cost_usd":0.00012,"cache_hit":false,"structured_tier":1,
 "extra":{"intents":["penalty","law"],"regex_only":false},"error":null}
```

Một dòng một sự kiện, không lồng nhau — `summarize_traces.py` đọc bằng một vòng lặp, và bạn cũng
`grep` được trực tiếp.

## Related Code Files

- Create: `src/observability/__init__.py`, `tracer.py`, `pricing.py`, `langsmith.py`
- Create: `scripts/eval/summarize_traces.py`
- Create: `tests/test_tracer.py`
- Modify: `src/graph/build.py` — gắn callback handler khi compile
- Modify: `src/llm/structured.py` — trả kèm `tier` đã dùng để tracer ghi lại
- Modify: `src/api_server.py` — thêm `GET /api/trace/summary` (chỉ số tổng hợp, **không** trả nội
  dung câu hỏi)
- Modify: `.env.example` — `TRACE_DIR`, `TRACE_RETENTION_DAYS`, `LANGSMITH_TRACING`,
  `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`

## Implementation Steps

1. Viết `src/observability/tracer.py`: kế thừa `BaseCallbackHandler`, hook `on_chain_start/end`,
   `on_llm_start/end/error`. Ghi qua hàng đợi + luồng nền xả theo lô.
2. Viết `pricing.py` với bảng đơn giá cho các model đang cấu hình trong `.env`.
3. Sửa `structured_call()` trả về `(obj, tier)` để tracer ghi được tầng đã dùng.
4. Gắn handler vào `build.py` (qua `config={"callbacks": [...]}"` khi chạy đồ thị).
5. Viết `langsmith.py`: chỉ đặt biến môi trường LangChain cần và log một dòng cảnh báo rõ ràng rằng
   dữ liệu sẽ được gửi lên dịch vụ ngoài. Mặc định tắt.
6. Viết `scripts/eval/summarize_traces.py` in bảng: node × (p50, p95, số lần chạy), tổng chi phí,
   tỉ lệ trúng cache, phân bố `structured_tier`, tỉ lệ fallback.
7. Thêm `GET /api/trace/summary`.
8. Viết `tests/test_tracer.py`: khẳng định (a) JSONL đúng schema, (b) không ghi API key, (c) ghi
   trace không làm chậm đường chính quá 5% (đo bằng một node giả).
9. Chạy bộ eval đầy đủ rồi chạy `summarize_traces.py`, đưa bảng kết quả vào tệp baseline làm số liệu
   độ trễ và chi phí chính thức.

## Success Criteria

- [x] Mỗi lượt hỏi sinh đủ dòng trace cho tất cả node đã chạy (kiểm trên lượt chạy thật: 10/10 node, mỗi node đúng một dòng)
- [x] `summarize_traces.py` in được p50/p95 theo node, chi phí mỗi câu, tỉ lệ trúng cache, phân bố
      `structured_tier`, phân bố model và tỉ lệ fallback
- [x] Bật `LANGSMITH_TRACING=true` là có trace trên LangSmith, không cần sửa code (`configure_langsmith()` gọi từ `build_run_config()`; thiếu API key thì cảnh báo và chỉ ghi cục bộ)
- [x] Không có API key hay secret nào trong tệp trace (`test_trace_never_contains_api_key`, cộng kiểm lại trên lượt chạy thật)
- [x] Chi phí ghi trace < 5% độ trễ tổng — `test_tracing_overhead_under_five_percent`. Bản cũ chập chờn (3 lần chạy ra 1 xanh 2 đỏ) vì đo trên node giả **1ms** và tính cả `uuid4()` + `_node_meta()` vào nhánh có trace nhưng không tính vào nhánh nền — tức đang đo giàn giáo của test. Đã sửa **phép đo, không sửa ngưỡng**: node giả 5ms, metadata dựng sẵn ngoài vòng đo, lấy `min` của 3 lượt. Chạy 5 lần liên tiếp: 5/5 xanh
- [x] Tệp trace tự xoay vòng theo ngày và tự dọn theo `TRACE_RETENTION_DAYS` (`test_expired_trace_files_are_purged`)
- [x] Số liệu độ trễ và chi phí trong baseline được lấy từ chính bộ trace này — `scripts/eval/baselines/baseline-graph-phase7-260910.json`, sinh từ `summarize_traces.py --since 2026-09-10` trên `trace-2026-09-10.jsonl`. **Cỡ mẫu 43/95 câu**: lượt chạy bị dừng sớm theo yêu cầu người dùng (đã chạy 95 phút, còn ~114 phút nữa). Cache ngữ nghĩa được xoá trước khi chạy nên mọi câu đều đi đường lạnh

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| Ghi trace đồng bộ làm nghẽn SSE | Token về giật cục | Hàng đợi + luồng nền ngay từ đầu, không phải tối ưu về sau |
| Callback của LangChain không báo token cho một số provider | `prompt_tokens` bằng 0 | OpenRouter trả `usage` trong response; đọc từ `response.llm_output["token_usage"]`, thiếu thì ước lượng bằng đếm ký tự chia 4 và đánh dấu `estimated: true` |
| Trace chứa toàn văn câu hỏi của người dùng | Rò dữ liệu nếu tệp bị chia sẻ | `data/runtime/` trong `.gitignore`; `/api/trace/summary` chỉ trả số liệu tổng hợp; ghi rõ trong README |
| Bảng đơn giá lạc hậu | Chi phí ước tính lệch hoá đơn | Docstring nói rõ đây là ước lượng; hoá đơn OpenRouter là con số thật |


## Ghi Chú Thực Thi

**`with_config(callbacks=[...])` thay thế callback kế thừa, không gộp thêm.** `src/llm/provider.py`
gắn `ModelFallbackTracker` vào mô hình theo cách đó, nên tracer quan trắc của đồ thị chỉ thấy các
lệnh gọi đi qua `structured_call()` (`route`, `rerank`) và **không thấy** `synthesize` với `repair` —
đúng hai lệnh gọi đắt nhất. Đã sửa bằng `_run_callbacks()`: đưa tracer của lượt chạy hiện tại vào
cùng danh sách callback với tracker fallback. Đo lại trên lượt chạy thật: số lệnh gọi ghi được tăng
từ 2 lên 3, token từ 1.254/418 lên 7.956/2.343.

**Node thật và runnable của cạnh có điều kiện mang cùng `langgraph_node`.** Không lọc thì `route` và
`verify` — đúng hai node có `add_conditional_edges` — bị đếm hai lần và p50 bị trộn với thời gian
chạy hàm rẽ nhánh. Phân biệt bằng thẻ: node thật có `graph:step:N`, hàm rẽ nhánh có `seq:step:N`.

**LangGraph không truyền `metadata` cho `on_chain_end`.** Tên node chỉ có ở callback `*_start`, nên
phía kết thúc phải tra lại theo `run_id` đã ghi lúc bắt đầu. Bản đầu tiên đọc metadata ở cả hai phía
và ghi ra **0 dòng trace** dù mọi unit test đều xanh — vì unit test gọi thẳng callback với metadata
tự dựng. Bài học đã phản ánh vào test: `_node_meta()` mô phỏng đúng kwargs mà LangGraph truyền.

**Chi phí lấy từ nhà cung cấp trước, bảng đơn giá cục bộ sau.** OpenRouter trả `usage.cost` trong
phản hồi, chính xác hơn mọi bảng tự giữ. Bảng chỉ dùng khi provider không báo; model chưa biết giá
được đánh dấu `cost_source: "unknown"` và đếm riêng, để không ai đọc nhầm "chưa biết giá" thành
"miễn phí".

**Phụ thuộc vào Phase 6 đang hỏng.** `langgraph-checkpoint-sqlite 2.0.10` không tương thích với
`langgraph-checkpoint 4.2.0` (`JsonPlusSerializer` đã bỏ `dumps`, chuyển sang `dumps_typed`).
Checkpointer ném lỗi ở cuối mỗi lượt chạy, làm `agent_steps` rỗng và phát thừa một cặp `error`+`done`.
Đồ thị vẫn chạy đúng toàn bộ pipeline trước đó. Việc này thuộc Phase 6, chưa sửa ở đây.

**Lỗi checkpointer của Phase 6 đã được sửa.** `langgraph-checkpoint-sqlite` lên `3.1.1` ghép với
`langgraph-checkpoint 4.2.0` chạy sạch: 28 thread đọc lại được, 0 sự kiện lỗi checkpointer trên 43
lượt chạy. Ghi chú "phụ thuộc vào Phase 6 đang hỏng" ở trên không còn hiệu lực.

**`agent_steps` rỗng là lỗi phép đo, không phải lỗi checkpointer.** Ghi chú cũ quy cho checkpointer
là sai. `detailed_results` của `e2e_eval.py` **chưa bao giờ** có trường `agent_steps`, nên đọc ra
rỗng là đương nhiên. Đọc thẳng trạng thái đã checkpoint cho thấy `agent_steps` có dữ liệu đúng
(1 bước `semantic_search` cho câu chỉ chạm một node truy xuất). Không có gì phải sửa.

**Điều bộ trace nói ra — và đây mới là phát hiện đáng giá nhất của Phase 7.** Đúng như phần
"Vì sao `structured_tier` là trường đáng giá nhất" đã dự đoán, chính trường này chỉ thẳng ra nút thắt:

| Triệu chứng | Số đo | Hệ quả |
|---|---|---|
| `rerank` tier-1 (`json_schema`) thất bại | 11/43 lượt (25.6%), `LengthFinishReasonError` | Model đốt trọn 4.000 reasoning token rồi chạm trần độ dài, phải chạy lại bằng `function_calling`. `rerank` p95 vọt lên 139s |
| `repair` phải chạy | 13/43 lượt (30.2%), p50 39.1s | Mỗi lần là thêm một lượt LLM đắt tiền |
| `cancel` | 3/43 lượt (7.0%) | 3 câu bị huỷ |
| Độ trễ đầu-cuối p50 | **96,1s** so với baseline legacy **28,5s** | **Chậm hơn 3,4 lần** |

Cổng chặn Phase 8 yêu cầu p50 không tăng quá 10%. Với con số hiện tại đây là **rủi ro hồi quy lớn
nhất còn lại của cả kế hoạch**, và nguyên nhân gốc đã được chỉ đích danh chứ không còn phải đoán:
`z-ai/glm-5.3-flash` sinh reasoning token không kiểm soát ở chế độ `json_schema`. Hướng xử lý thuộc
Phase 8 — nâng trần `max_tokens` cho lệnh gọi rerank, hạ `rerank` xuống thẳng tầng `function_calling`
cho model này, hoặc bỏ qua rerank khi biên điểm RRF đã đủ rõ (biện pháp đã ghi sẵn trong bảng rủi ro
của `plan.md`).

**Chi phí ghi nhận được là cận dưới.** 43 lệnh gọi không được provider báo giá và 43 lệnh phải ước
lượng token, nên $0,001664/câu là con số sàn, không phải con số quyết toán.
