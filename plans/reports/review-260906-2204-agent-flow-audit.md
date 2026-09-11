# Kiểm toán & tối ưu flow suy luận của Agent

Ngày: 2026-09-06 22:04 · Phạm vi: `src/agentic_rag.py`, `src/tools/law_search_tools.py`

## 1. Cách kiểm toán

Không review bằng mắt. Viết bộ thăm dò chặn `_execute_tool` để bắt lại **toàn bộ dữ liệu công cụ
thật sự trả về**, rồi đối chiếu tự động với câu trả lời cuối trên 3 tiêu chí:

1. **Trung thực số liệu** — mọi con số tiền trong câu trả lời có nằm trong dữ liệu tra cứu không?
2. **Đúng sự thật** — đối chiếu với nội dung gốc của Điều luật.
3. **Văn phong** — có thuật lại quy trình nội bộ thay vì trả lời không?

6 case: phạt có trong DB · phạt không có trong DB · sự thật hạng C1 · ngoài phạm vi · sự thật điểm
GPLX · sự thật độ tuổi.

## 2. Bốn lỗi tìm được

### 🔴 L1 — Bịa số tiền phạt (nghiêm trọng nhất)

| Case | Câu trả lời cũ | Thực tế |
|---|---|---|
| Xe máy đi ngược chiều | nêu mức "200.000" | DB không có dữ liệu hành vi này |
| Thủ tục ly hôn | nêu mức "400.000" | câu hỏi ngoài phạm vi hoàn toàn |

Nguyên nhân: `penalty_lookup` khi không khớp trả về thông điệp mềm ("Mức phạt cụ thể được quy định
tại các Nghị định...") — không cấm gì cả, nên mô hình tự điền số từ trí nhớ.

### 🔴 L2 — Trả lời sai sự thật do retrieval trả thiếu nội dung

Hỏi "Bằng lái C1 lái được xe gì?" → trả lời **"3,5 tấn đến dưới 20 tấn, 9–16 chỗ"**. Sai. Điều 57
quy định C1 = **trên 3.500 kg đến 7.500 kg**.

Nguyên nhân gốc: `semantic_search` tìm **đúng** Điều 57 (82.1%) nhưng chỉ trả về các Khoản con khớp
vector — lại là Khoản 3 (xe bốn bánh) và phần đầu Khoản 1 bị cắt. Định nghĩa C1 nằm ở **điểm đ)
Khoản 1** chưa bao giờ được đưa ra. Thiếu nội dung, mô hình lấp bằng trí nhớ (định nghĩa C1 của
Luật 2008 cũ).

Đây là lỗi kiến trúc: dự án có sẵn parent-child chunking nhưng `semantic_search` **vứt phần parent đi**.

### 🟠 L3 — Câu ngoài phạm vi vẫn kéo về điều luật vô can

"Thủ tục ly hôn" → nguồn trích dẫn `[Điều 58, 81, 37]`. Vector search luôn trả top-k bất kể độ liên
quan, không có ngưỡng. Giao diện hiển thị chúng như "căn cứ pháp lý" → gây hiểu lầm.

Đo phân bố điểm: câu sát đề **72–88**, câu ngoài phạm vi **54–62**. Có khoảng tách rõ để đặt ngưỡng.

### 🟡 L4 — Thuật lại quy trình nội bộ ra cho người dùng

"Dựa trên kết quả tra cứu...", "# Đối chiếu và lời giải đáp cuối cùng", và rò rỉ cả điểm số nội bộ
"độ liên quan 58.8%". Người dùng cần kết luận, không cần nhật ký làm việc của Agent.

## 3. Đã sửa

| Lớp | Thay đổi |
|---|---|
| **Dữ liệu** | `penalty_lookup` không khớp → thông điệp cấm dứt khoát, không được nêu bất kỳ số tiền nào |
| **Truy xuất** | `semantic_search` trả **toàn văn Điều khớp nhất** (small-to-big, cắt ở 3.500 ký tự), các Điều sau giữ trích đoạn + gợi ý gọi `get_article` |
| **Truy xuất** | Ngưỡng liên quan: `< 62` loại bỏ hẳn · `< 70` giữ nhưng cảnh báo Agent |
| **Prompt** | Quy tắc số liệu thành điều khoản số 2 (quan trọng nhất): mọi con số phải xuất hiện nguyên văn trong kết quả công cụ |
| **Prompt** | Tách khối `[CHỈ DẪN NỘI BỘ CHO AGENT]` — chỉ dẫn cho Agent, cấm chép ra câu trả lời |
| **Hậu kiểm** | `_find_ungrounded_figures()` — quét số trong câu trả lời, đối chiếu cache công cụ; lệch thì **gắn cảnh báo hiển thị** thay vì âm thầm xoá |
| **Hậu kiểm** | `_polish_answer()` — bỏ mở đầu thuật lại quy trình và câu rò rỉ điểm số nội bộ |

Chọn **cảnh báo** thay vì tự xoá số: xoá đi làm câu văn sai nghĩa mà người dùng không biết; với trợ
lý pháp lý, nói rõ "chưa đối chiếu được" trung thực hơn.

## 4. Kết quả đo lại

| Chỉ số | Trước | Sau |
|---|---|---|
| Case bịa số tiền | **2/5** | **0/6** |
| Sai sự thật (C1, điểm GPLX, tuổi) | 1/3 sai | **3/3 đúng** |
| Nguồn trích dẫn cho câu ngoài phạm vi | 3 điều vô can | **0** |
| Thuật lại quy trình | 4/6 | **1/6** (câu còn lại là cách diễn đạt hợp lý cho ca không tìm thấy) |
| Rò rỉ điểm số nội bộ | có | không |
| Thời gian ca ngoài phạm vi | 14,4s | **5,0s** |

Kiểm thử đơn vị: `_find_ungrounded_figures` 4/4 PASS · `_polish_answer` giữ nguyên câu không có
narration, chỉ cắt phần thừa.

Hồi quy: 5 khu vực giao diện đủ chức năng, 0 lỗi console · phiên trò chuyện còn sau reload ·
CLI `chat.py` 2,94s · `compileall` sạch.

## 5. Việc còn để ngỏ

- **Guard chỉ bắt số có dấu phân nhóm** (`6.000.000`, `3.500`). Nếu mô hình viết "6 triệu" hay
  "3,5 tấn" thì không kiểm được. Mở rộng sang số viết chữ sẽ tăng cảnh báo giả — cần đánh đổi, muốn
  siết thêm không?
- **Bộ benchmark hiện đo `rag_engine` (vector thuần), không đo Agent.** Số hit@1 51.4% / hit@3 71.4%
  trong màn Quản trị **không phản ánh chất lượng Agent** đang chạy. Có nên viết bộ đo riêng cho
  Agent trên 35 câu hỏi (tốn ~35 lượt gọi LLM mỗi lần chạy) không?
- **DB xử phạt chỉ có 10 nhóm hành vi.** Sau các thay đổi trên, hành vi ngoài 10 nhóm này sẽ được
  trả lời trung thực là "chưa có dữ liệu" thay vì bịa số — đúng đắn hơn nhưng độ phủ vẫn hạn chế.
  Có muốn bổ sung thêm nhóm vi phạm vào DB không?
