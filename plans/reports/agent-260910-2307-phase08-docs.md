# Báo cáo: Phase 8 — Tài liệu (docs/architecture.md + README.md)

## Phạm vi đã làm
- Tạo mới `docs/architecture.md` (352 dòng): mô tả StateGraph thực tế trong `src/graph/build.py`
  (node, cạnh, cạnh có điều kiện `route_fanout`/`verify_router`), sơ đồ Mermaid khớp chính xác với
  `create_legal_graph()`, state shape + reducer (`operator.add` cho `evidence`/`agent_steps`,
  `add_messages` cho `messages`), tầng truy xuất lai (BM25 `src/retrieval/sparse.py`, dense
  `src/retrieval/dense.py`, RRF `src/retrieval/hybrid.py`, LLM rerank `src/retrieval/rerank.py`),
  tầng structured output 4 bậc (`src/llm/structured.py`), verify/repair/cancel
  (`src/graph/verify.py`, `src/graph/repair.py`), checkpointer SQLite + semantic cache
  (`src/graph/build.py`, `src/cache/semantic_cache.py`), quan trắc JSONL + LangSmith tuỳ chọn
  (`src/observability/tracer.py`, `src/observability/langsmith.py`), và bảng hợp đồng SSE 14 sự
  kiện đối chiếu trực tiếp với từng lệnh gọi `emit()` trong mã.
- Cập nhật toàn bộ `README.md` (308 dòng): sơ đồ kiến trúc (thay ReAct cũ bằng flow StateGraph),
  cây thư mục (thêm `src/graph`, `src/llm`, `src/retrieval`, `src/observability`, `src/cache`,
  `data/runtime`, `scripts/eval`, `tests/`, sửa `static/js/` thay cho `web/` không còn tồn tại),
  bảng biến môi trường đầy đủ (`LLM_MODEL`, `FALLBACK_LLM_MODEL`, `ROUTER_LLM_MODEL`,
  `RERANK_LLM_MODEL`, `TRACE_DIR`, `TRACE_RETENTION_DAYS`, `LANGSMITH_TRACING`, và các biến RRF/
  cache/checkpointer khác), hướng dẫn chạy app và chạy eval (`retrieval_eval.py`, `e2e_eval.py`,
  `gate.py`, `summarize_traces.py`, `pytest`), bảng API cập nhật theo `src/api_server.py` thật
  (thêm `/api/trace/summary`, sửa mô tả `/api/ask`), và bảng Trước/Sau trung thực.
- Thêm ghi chú riêng tư về trace ở cả hai tệp: `data/runtime/traces/` chứa toàn văn câu hỏi, nằm
  trong `.gitignore`, `/api/trace/summary` chỉ trả số liệu tổng hợp.
- Sửa các tuyên bố lỗi thời phát hiện được trong lúc đọc mã: thư mục `web/` không còn tồn tại (đã
  đổi thành `static/js/` + `templates/`), tệp prototype `lextraffic_ai_desktop.html` không còn
  trong repo (đổi thành trỏ tới `docs/design-system.md`), bảng "nguồn dữ liệu chưa nạp" đã lỗi thời
  — thực tế cả 6 văn bản đã có structured JSON (đối chiếu `data/processed/all_legal_corpus_metadata.json`:
  1.308 mục, 6 văn bản).

## Số liệu đã dùng và nguồn xác minh
- Hit@1 = 72.15%, MRR = 0.7774, Hit@3 = 83.54% trên 79/95 câu: `data/benchmark/hybrid_eval_report.json`.
- Độ trễ p50 96.1s / p95 219.1s trên 43/95 câu, model `z-ai/glm-5.3-flash` (đã thay thế):
  `scripts/eval/baselines/baseline-graph-phase7-260910.json`, kể cả chi tiết rerank p95 139s do
  `LengthFinishReasonError` (25.6% lượt) — trích dẫn nguyên văn ghi chú `known_issues` trong file.
  Nhận thông tin từ nhiệm vụ giao việc rằng rerank đã giảm còn ~0.9s sau khi đổi model — trình bày
  đúng như "đã đo được sau khi đổi model", không suy đoán con số p50/p95 tổng thể mới.
  Model hiện tại xác nhận qua `.env.example`: `LLM_MODEL=deepseek/deepseek-v4-flash`,
  `ROUTER_LLM_MODEL=RERANK_LLM_MODEL=mistralai/ministral-8b-2512`.
- Citation accuracy 50–66.7% trên mẫu 3 và 20 câu: `data/benchmark/e2e_evaluation_report.json`
  (3 câu) và `data/benchmark/e2e_graph_phase5.json` (20 câu, trước khi đổi model Phase 7) — trình
  bày rõ là mẫu quá nhỏ, KHÔNG phải kết quả cổng chặn cuối cùng.
- Baseline legacy Hit@1 51.4%, MRR 0.66, độ trễ p50 28.5s: lấy từ `plan.md` (mục "Chỉ Số Mục Tiêu"),
  không tự đo lại.
- 95 câu trong `qa_testset_v2.json`, 1.308 mục / 2.114 chunk trong `data/processed/`: đếm trực tiếp
  bằng script Python đọc JSON, không phỏng đoán.

## Phát hiện quan trọng khi đối chiếu mã — đã đưa vào docs/architecture.md §13
- `model_fallback` **không được phát ra SSE** hiện tại — `ModelFallbackTracker` trong
  `src/llm/provider.py` chỉ gọi `record_model_fallback()` để ghi vào trace JSONL
  (`src/observability/tracer.py`), không gọi `src.graph.events.emit()`. Frontend
  (`static/js/agent-trace.js`) có `case 'model_fallback'` nhưng backend chưa bao giờ gửi sự kiện
  này. Đây là một khoảng trống thật giữa 14 loại sự kiện frontend xử lý và 12 loại thực sự được
  phát — đã ghi rõ trong bảng hợp đồng SSE, không trình bày như "cả 14 đều hoạt động".
- `answer_reset` xác nhận không còn được phát ở đâu trong `src/` (khớp với mô tả trong `plan.md`),
  giữ lại ở frontend làm no-op tương thích ngược.
- `rerank_node` (`src/graph/rerank_node.py`) **không phát sự kiện SSE nào** (không có `tool_call`/
  `tool_result` như bảng trong `plan.md` mô tả là ý định thiết kế) — ghi đúng hiện trạng mã, không
  copy nguyên bảng dự định từ plan.
- `src/agentic_rag.py` vẫn còn tồn tại trên đĩa tại thời điểm viết tài liệu (chưa bị xoá) —
  không thuộc phạm vi được giao (src/ do worker khác sở hữu), nên không đề cập trong README theo
  hướng khẳng định đã xoá; README chỉ mô tả kiến trúc StateGraph hiện hành, không nhắc file cũ.

## Không đưa vào README/docs vì chưa xác minh được
- Không có báo cáo `gate.py --full` nào chạy trên đủ 95 câu tại thời điểm viết — đã ghi rõ "chưa
  chạy trọn" thay vì suy đoán kết quả.
- Không đo lại độ trễ end-to-end trên tổ hợp model hiện tại (`deepseek-v4-flash` +
  `ministral-8b`) — ghi rõ "chưa đo lại", không nội suy từ p50 cũ trừ đi phần rerank giảm được.

Status: DONE
Summary: Đã viết `docs/architecture.md` (mới, 352 dòng) và cập nhật toàn bộ `README.md` (308 dòng)
phản ánh đúng kiến trúc StateGraph thực tế trong `src/graph/`, kèm bảng hợp đồng SSE đối chiếu
từng `emit()`, bảng biến môi trường đầy đủ, hướng dẫn chạy app/eval, và bảng Trước/Sau chỉ dùng số
liệu đã đo được kèm nguồn, không trình bày mục tiêu Phase 8 chưa đạt như đã đạt.
Concerns/Blockers: Không có phần nào của plan.md không xác minh được trong mã — chỗ duy nhất lệch
giữa "ý định thiết kế" (bảng SSE trong plan.md) và mã thật là `model_fallback` chưa nối vào SSE và
`rerank` không phát sự kiện gì; cả hai đã ghi rõ trong docs/architecture.md thay vì im lặng theo
plan. `src/agentic_rag.py` vẫn còn trên đĩa — nằm ngoài phạm vi của tôi (src/ do worker khác sở
hữu), cờ này nên được worker phụ trách cutover xử lý trước khi coi Phase 8 là DONE toàn cục.
