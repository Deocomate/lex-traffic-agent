# Phase 7 — Quan trắc và truy vết: chốt baseline

**Ngày:** 2026-09-10 17:27 | **Chế độ:** `/ak:cook --auto` | **Trạng thái:** DONE_WITH_CONCERNS

## Việc đã làm

Phase 7 trước đó còn đúng một tiêu chí treo: số liệu độ trễ/chi phí trong baseline phải lấy từ chính
bộ trace. Tiêu chí này bị chặn bởi lỗi checkpointer của Phase 6.

1. **Xác nhận lỗi Phase 6 đã hết** — `langgraph-checkpoint-sqlite 3.1.1` + `langgraph-checkpoint 4.2.0`
   chạy sạch, 28 thread đọc lại được, 0 lỗi checkpointer trên 43 lượt.
2. **Xoá cache ngữ nghĩa trước khi đo** (đã backup cả `answer_cache.sqlite` lẫn `checkpoints.sqlite`).
   Không xoá thì câu trúng cache đi tắt, không chạm đồ thị, và baseline sẽ đo cache chứ không đo pipeline.
3. **Chạy `e2e_eval.py --adapter graph`** trên `qa_testset_v2` — **dừng ở câu 43/95 theo yêu cầu người dùng**
   (đã chạy 95 phút, còn ~114 phút). Tiến trình nền đã kill sạch, không để lại process mồ côi.
4. **Sinh baseline** `scripts/eval/baselines/baseline-graph-phase7-260910.json` từ
   `summarize_traces.py --since 2026-09-10`.

## Số liệu chốt (43 lượt, đường lạnh)

| Chỉ số | Giá trị |
|---|---|
| Độ trễ đầu-cuối p50 / p90 / p95 | **96.106ms** / 182.529ms / 219.082ms |
| Chi phí / câu | $0.001664 (cận dưới) |
| Lệnh gọi LLM / câu | 2.33 |
| Token vào / ra | 231.592 / 133.921 |
| Tỉ lệ trúng cache | 3.2% |
| Fallback model | 0% |
| Phân bố `structured_tier` | tier1=83, tier2=2, tier4=1 |
| Sự kiện lỗi | 11 (toàn bộ ở `rerank`) |

Node chậm nhất: `synthesize` p50 35.854ms · `repair` p50 39.149ms · `rerank` p50 26.542ms (p95 **139.443ms**).

## Phát hiện quan trọng nhất

**Harness mới đang chậm hơn harness cũ 3.4 lần** (p50 96.1s so với 28.5s). Cổng chặn Phase 8 yêu cầu
p50 không tăng quá 10% — đây là rủi ro hồi quy lớn nhất còn lại của cả kế hoạch.

Nguyên nhân gốc đã chỉ đích danh, không phải phỏng đoán:

- `rerank` tier-1 (`json_schema`) thất bại **11/43 lượt (25.6%)** với `LengthFinishReasonError`:
  `z-ai/glm-5.3-flash` đốt trọn 4.000 reasoning token rồi chạm trần độ dài, phải chạy lại bằng
  `function_calling`.
- `repair` phải chạy **13/43 lượt (30.2%)**, mỗi lần thêm một lượt LLM đắt tiền.
- `cancel` 3/43 lượt (7.0%).

Đúng như thiết kế Phase 7 dự đoán: `structured_tier` là trường rẻ nhất chỉ ra model yếu ở đâu, và nó
đã làm đúng việc đó.

Hướng xử lý (thuộc Phase 8): nâng `max_tokens` cho lệnh gọi rerank, hoặc cho model này xuống thẳng
tầng `function_calling`, hoặc bỏ qua rerank khi biên điểm RRF đã đủ rõ (đã có sẵn trong bảng rủi ro `plan.md`).

## Hai ghi chú cũ của Phase 7 bị chứng minh là sai

- "Phụ thuộc vào Phase 6 đang hỏng" — đã hết hiệu lực.
- "`agent_steps` rỗng do lỗi checkpointer" — **sai**. `detailed_results` của `e2e_eval.py` chưa bao giờ
  có trường `agent_steps`; đọc thẳng trạng thái checkpoint thấy dữ liệu đúng. Không có bug.

## Test

`161 passed, 1 failed`. Lỗi duy nhất: `test_tracing_overhead_under_five_percent` — **flaky có sẵn từ trước**,
không do thay đổi lần này (lần này không đụng một dòng code nào). Chạy riêng 3 lần: 1 xanh / 2 đỏ.
Test đo trên node giả **1ms**, ở thang đó nhiễu đồng hồ át tín hiệu. Node thật 1.490–35.854ms nên chi phí
ghi trace thực tế không đáng kể. Đã hạ tiêu chí xuống `[~]` và ghi rõ cần sửa test ở Phase 8 —
**không hạ ngưỡng 5%**.

## Câu hỏi còn treo

1. Có chạy nốt 52 câu còn lại để baseline đủ 95 câu không? Baseline hiện tại ghi rõ cỡ mẫu 43/95.
   Số liệu độ trễ/chi phí đã đủ ổn định để dùng, nhưng chỉ số **chất lượng E2E** (citation accuracy,
   refusal) thì **chưa có** vì `e2e_eval.py` chỉ ghi báo cáo khi chạy hết bộ.
2. Xử lý nút thắt `rerank` ở Phase 8 theo hướng nào trong ba hướng nêu trên?
