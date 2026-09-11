# Hoàn tất Phase 1–8 — LangGraph Agent Harness

**Ngày:** 2026-09-10 23:07 → 2026-09-11 04:30 | **Chế độ:** `/ak:cook --auto` + 3 subagent (sonnet)
**Trạng thái:** DONE_WITH_CONCERNS — mã và tài liệu xong, 3 cổng chất lượng chưa đạt

## 1. Sửa các vấn đề đã phát hiện

| Vấn đề | Nguyên nhân gốc | Cách sửa | Kết quả đo được |
|---|---|---|---|
| `rerank` hỏng tầng 1 25,6% lượt | `max_tokens=4000` tính cả reasoning token; model reasoning đốt hết hạn mức trước khi sinh nổi ký tự JSON → `LengthFinishReasonError` | Ghìm `reasoning.effort="low"` cho mọi vai trò; router/rerank chuyển sang `ministral-8b` (không reasoning) | rerank p50 **26.542ms → 912ms**; tier-1 hỏng **11 → 0**; `structured_tier` 100% tầng 1 trên 443 lệnh gọi |
| Độ trễ p50 96,1s (chậm hơn legacy 3,4x) | như trên | như trên | **30,9s** — qua cổng chặn (+8,6% so với legacy, dưới ngưỡng +10%) |
| Test đo chi phí trace chập chờn | Đo node giả **1ms**, lại tính `uuid4()` + `_node_meta()` vào nhánh có trace nhưng không tính vào nhánh nền → đang đo giàn giáo của test | Sửa **phép đo, giữ nguyên ngưỡng 5%**: node 5ms, metadata dựng sẵn ngoài vòng đo, lấy `min` của 3 lượt | 5/5 lượt xanh |
| Câu trả lời **rỗng** gửi tới người dùng | `verify_answer()` có `if not answer: return []` — câu rỗng bị coi là "không có gì để kiểm chứng, coi như đạt" | Câu rỗng trả `EMPTY_ANSWER_ISSUE` → `repair` → `cancel` (từ chối trung thực) | Lượt 95 câu cuối: **0 câu rỗng** |
| Nguồn của câu rỗng | `synthesize`/`repair` cũng bị đốt hạn mức: 2 lệnh gọi dừng đúng ở 4.000 token | Nâng lên 8.000 token + ghìm reasoning | hết truncation |
| `model_fallback` không bao giờ tới giao diện | Chỉ ghi vào tệp trace, **không** gọi `emit()`. Giao diện có sẵn nhánh xử lý mà không bao giờ nhận được sự kiện → người dùng không biết câu trả lời do model dự phòng sinh | Nối vào `emit()` | 2 test hồi quy |
| `FALLBACK_LLM_MODEL` vô tác dụng | Đặt trùng đúng model chính → `with_fallbacks` bị bỏ qua | Đổi thành model khác thật | fallback hoạt động |
| Từ chối lạc đề 68,75% | Model từ chối đúng nhưng bằng văn xuôi tự do mà regex không phủ ("không thuộc **lĩnh vực**" ≠ "không thuộc **phạm vi**"). `needs_search` không bật → `done` không kèm liên kết tra ngoài, người dùng bị từ chối mà không được mời tra Google | Chỉ dẫn số 7: câu lạc đề phải mở đầu bằng đúng câu chuẩn, cấm nêu số tiền. Thêm `declines_as_out_of_domain()` trong `sources.py` (**không** sửa `answer_guard.py` — đã chốt giữ nguyên) | **93,75%** trên tập 16 câu lạc đề |

## 2. Đổi model (rẻ hơn theo yêu cầu)

| Vai trò | Trước | Sau | Đơn giá /1M (in/out) |
|---|---|---|---|
| Chính | `glm-5.3-flash` | `deepseek/deepseek-v4-flash` | $0.087 / $0.174 (trước: $0.15 / $0.50) |
| Dự phòng | `glm-5.3-flash` (trùng!) | `openai/gpt-oss-20b` | $0.03 / $0.13 |
| Router + rerank | (theo model chính) | `mistralai/ministral-8b-2512` | $0.15 / $0.15, **không reasoning** |

Chi phí: **$0,001670/câu**. Chọn `ministral-8b` cho phân loại vì đo thực tế nhanh hơn hẳn: **912ms so với 5.041ms**, tầng 1 ổn định.

Ghi chú: đã thử `reasoning.enabled=false` và bị `gpt-oss-20b` trả lỗi 400 *"Reasoning is mandatory for this endpoint and cannot be disabled"*, kéo sập cả 4 tầng structured output. `effort:"low"` được mọi provider chấp nhận.

## 3. Kết quả nghiệm thu (95 câu, cache đã xoá, đường lạnh)

| Chỉ số | Legacy | Trước phiên này | **Sau** | Mục tiêu | |
|---|---|---|---|---|---|
| Độ trễ p50 | 28,5s | 96,1s | **30,9s** | +10% tối đa | ✅ |
| Hit@1 | 51,4% | 72,15% | **72,15%** | >= 72% | ✅ |
| MRR | 0,66 | 0,7774 | **0,7774** | >= 0,80 | ❌ |
| Trích dẫn E2E | — | 48% | **63,29%** | >= 95% | ❌ |
| Số liệu không căn cứ | — | 8% | **1,05%** | 0% | ❌ (sát) |
| Từ chối lạc đề | — | 68,75% | **93,75%** / 87,50%* | >= 90% | ⚠️ |
| Câu bị huỷ | 0% | 9,47% | **8,42%** | không tăng | ❌ |

\* 93,75% khi chạy riêng 16 câu lạc đề, 87,50% trong lượt 95 câu — LLM không tất định.

`gate.py` → **exit code 1**: qua 1/5 cổng (độ trễ).

**Hai model** đã chạy trọn pipeline: `deepseek-v4-flash` (95 câu, p50 30,9s) và `gpt-oss-20b` (25 câu, p50 23,1s, số liệu không căn cứ 0%).

## 4. Cắt chuyển và tài liệu

- `src/agentic_rag.py` (1004 dòng) **đã xoá**; không còn import trong code runtime.
- `LegacyAdapter` gỡ; `get_adapter("legacy")` báo lỗi rõ ràng, trỏ về baseline đã lưu.
- `scripts/verify_agentic_rag.py` → `scripts/verify_agent.py` (4/5 ca; ca trượt do so khớp từ khoá, không phải lỗi harness).
- `docs/architecture.md` (mới, sơ đồ Mermaid khớp `create_legal_graph()` thật) và `README.md` đã cập nhật.
- **166 test xanh** (từ 162; thêm 4 test hồi quy cho SSE và nhận diện lạc đề).

## 5. Việc còn lại — và vì sao chưa làm được ở đây

**Trích dẫn 63,29% là nút thắt lớn nhất.** Siết prompt đã nâng từ 48% lên 63%; phần còn lại **không sửa được bằng prompt**: truy xuất chọn sai Điều (ví dụ trả Điều 16 khi đáp án là Điều 17). Model không thể trích dẫn đúng thứ nó chưa bao giờ được đọc.

Gốc rễ nằm ở chất lượng truy xuất trên **NĐ 168/2024**: Hit@1 **56,2%**, MRR **0,5625** — thấp nhất trong 6 văn bản, mà đây lại là văn bản bị hỏi nhiều nhất (mức phạt). Nâng được văn bản này là nâng cả trích dẫn lẫn MRR tổng.

**Một khiếm khuyết có sẵn được phát hiện nhưng cố ý KHÔNG sửa:** `is_uncertain_answer()` trong `answer_guard.py` gán nhầm **12/79 câu đúng phạm vi** thành "không chắc chắn", làm giao diện mời tra Google vô cớ. `answer_guard.py` được chốt giữ nguyên 100% trong `plan.md` (Quyết Định số 1), nên chỉ báo cáo, không tự ý sửa.

## Câu hỏi còn treo

1. Có mở phase mới cho tầng truy xuất NĐ 168 không? Đây là đường duy nhất đưa trích dẫn lên 95% và MRR lên 0,80.
2. Có cho phép sửa `answer_guard.py` để chữa 12 câu bị gán nhầm không? Đang bị khoá bởi quyết định "giữ nguyên 100%".
3. Ngưỡng "câu bị huỷ không được tăng so với 0%" có thực tế không? Huỷ đúng khi `verify` bắt được lỗi thật là hành vi **mong muốn**; baseline legacy 0% có thể phản ánh việc harness cũ không huỷ đủ, chứ không phải nó tốt hơn.
