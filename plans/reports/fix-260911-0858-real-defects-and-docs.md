# Sửa lỗi thật + cập nhật tài liệu

**Ngày:** 2026-09-11 08:58 | **Chế độ:** `/ak:fix` | **Trạng thái:** DONE
**Phạm vi theo yêu cầu:** chấp nhận số benchmark hiện tại, chỉ sửa phần **thực sự lỗi** và cập nhật tài liệu.

## 1. Lỗi thật đã sửa

### 1.1 Tầng rerank âm thầm ngừng hoạt động (nghiêm trọng)

**Triệu chứng:** `LengthFinishReasonError: ... completion_tokens=1500, prompt_tokens=1212, reasoning_tokens=0`
tại node `rerank`, 10 lần trong lượt eval 95 câu; kèm 8 lần log `Rerank structured_call trả về None`.

**Nguyên nhân gốc:** `RerankResult` có trường `rationale: Optional[str]` — văn bản tự do, **không mã
chạy thật nào đọc** (`src/retrieval/rerank.py:28`, chỉ được dựng trong `tests/test_hybrid_retrieval.py:311`).
Model vẫn sinh và sinh dài, ăn hết hạn mức đầu ra **trước khi** `ordered_ids` kịp tuần tự hoá.
`reasoning_tokens=0` chứng minh đây là văn xuôi thuần, không phải reasoning.

**Vì sao lộ ra bây giờ:** phiên trước ghìm reasoning và hạ `max_tokens` của rerank 4000 → 1500; phần
đệm cũ vốn đang che khuyết điểm này biến mất.

**Blast radius:** `src/retrieval/rerank.py`, `src/graph/rerank_node.py`, `tests/test_hybrid_retrieval.py`,
và **chất lượng truy xuất** — 8/95 câu chạy qua rerank mà tầng đó không làm gì.

**Cách sửa:** bỏ hẳn `rationale` khỏi schema; nâng `max_tokens` rerank 1500 → 3000 làm đệm.

**Kiểm chứng (đo thật, trước/sau):**

| | Trước | Sau |
|---|---|---|
| `completion_tokens` rerank (trung vị) | 787 | **101** |
| Cao nhất | 1.464 (sát trần) | 242 |
| Lỗi `LengthFinishReasonError` | 10 / 95 câu | **0** |

Giảm ~7,8 lần đầu ra; đầu ra tối đa 242 so với hạn mức 3000 nên chạm trần là bất khả về mặt cấu trúc.
Thêm `test_rerank_schema_has_no_free_text_field` khoá bất biến.

### 1.2 Nhãn "tỉ lệ trúng cache" gây hiểu nhầm

**Nguyên nhân:** chỉ `src/retrieval/cache.py` (cache **vector truy vấn**) gọi `record_cache_event()`.
Cache **ngữ nghĩa câu trả lời** không ghi vào trace. Báo cáo in "Cache: N lượt tra, tỉ lệ trúng X%"
không nêu tên cache → người đọc tưởng là tỉ lệ trúng cache câu trả lời. Hai thứ khác hẳn: trúng cache
câu trả lời nghĩa là **đồ thị không chạy chút nào**; trúng cache embedding chỉ tiết kiệm một lần gọi API nhúng.

**Cách sửa:** ghi rõ tên cache trong `summarize_traces.py`, bổ sung docstring cho `record_cache_event()`,
thêm bảng so sánh hai loại cache vào `docs/architecture.md`. Không đổi khoá JSON (`/api/trace/summary`
và các tệp baseline đang dùng).

## 2. Đính chính một kết luận SAI của tôi ở phiên trước

Tôi đã báo cáo `is_uncertain_answer()` "gán nhầm 12/79 câu đúng phạm vi" và đề xuất cân nhắc mở khoá
`answer_guard.py`. **Sai.** Kiểm lại nội dung câu trả lời: cả 12 câu đó chính model tự nói *"Tôi chưa
có dữ liệu về quy định cho trường hợp này"* — vì **truy xuất trượt**, không tìm được Điều đúng. Lớp
phòng vệ nhận diện **đúng** và bật `needs_search` là hành vi mong muốn.

Hệ quả: **không có lý do gì để sửa `answer_guard.py`**, và câu hỏi "có mở khoá tệp này không" ở báo
cáo trước nên bỏ. 12 câu đó là thêm bằng chứng cho nút thắt truy xuất, không phải lỗi của guard.

## 3. Tài liệu đã cập nhật

- `README.md` — bảng chỉ số trước/sau thay bằng **số đo thật trên 95 câu**; sửa hai dòng
  `ROUTER_LLM_MODEL`/`RERANK_LLM_MODEL` (đang ghi "rỗng → dùng LLM_MODEL" trong khi `.env` đặt
  `ministral-8b`); thêm ghi chú vì sao hai vai trò này nên dùng model **không reasoning**, kèm cảnh báo
  `reasoning.enabled=false` bị `gpt-oss-20b` trả lỗi 400.
- `docs/architecture.md` — mục 14 thay toàn bộ số "chưa đo" bằng số nghiệm thu 95 câu; thêm mục giải
  thích độ trễ 96.1s → 30.9s; thêm mục nút thắt trích dẫn; thêm bài học schema (rerank) và bảng phân
  biệt hai loại cache.
- `plans/.../phase-03-hybrid-retrieval.md` — ghi chú thi công về lỗi rerank.

## 4. Kiểm thử

`167 passed` (từ 166; thêm `test_rerank_schema_has_no_free_text_field`). Không nới lỏng test nào.
Không đổi hợp đồng công khai: `RerankResult.rationale` chưa từng được mã chạy thật đọc.

## Câu hỏi còn treo

1. Có mở phase mới cho truy xuất `03_nghi_dinh_168_2024_nd_cp` (Hit@1 56.2%, MRR 0.5625) không? Đây
   là nguyên nhân chung của cả trích dẫn 63.29% lẫn MRR 0.7774 lẫn 12 câu "chưa có dữ liệu".
2. Sau khi bỏ `rationale`, rerank hoạt động trên 100% câu thay vì 92% — **chưa đo lại** Hit@1/MRR
   end-to-end vì `retrieval_eval.py` không gọi LLM rerank. Có muốn chạy một lượt 95 câu để xem con số
   mới không?
