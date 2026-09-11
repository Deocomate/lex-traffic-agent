# Dựng lại thanh bên & các tiện ích đã bị cắt quá tay

Ngày: 2026-09-06 · Tiếp nối `refactor-260906-2135-code-optimization.md`

## 1. Vấn đề

Vòng tối giản trước cắt xuống còn một khung chat trống. Mất: thanh bên, khu quản trị, khả năng
tự đọc văn bản luật, và xem PDF gốc. Yêu cầu ban đầu là *bớt rối*, không phải *bỏ công năng*.

## 2. Nguyên tắc dựng lại

Một thanh bên → 5 khu vực. Mỗi khu vực chỉ giữ nút cần cho việc của nó, thay vì dồn mọi nút lên
cùng một màn hình như bản prototype cũ. **Mọi tiện ích đều chạy trên dữ liệu thật đã có sẵn trong
kho, không có số liệu dựng sẵn.**

| Khu vực | Nguồn dữ liệu thật |
|---|---|
| 💬 Hỏi đáp AI | Agent qua SSE (giữ nguyên) + phiên trò chuyện lưu localStorage |
| 📖 Tra cứu luật | `law_36_2024_structured.json` (9 Chương/89 Điều) + `rag_chunks.jsonl` |
| 💰 Bảng mức phạt | `TRAFFIC_PENALTIES_DB` — 10 nhóm vi phạm, đủ khung phạt/tước GPLX/trừ điểm |
| 📄 Văn bản gốc | `data/raw_data/Luật-36-2024-QH15.pdf` (61 MB, 68 trang) |
| ⚙️ Quản trị hệ thống | `/api/health` + `data/benchmark/evaluation_report.json` |

## 3. Backend — 5 endpoint mới

| Endpoint | Trả về |
|---|---|
| `GET /api/chapters` | Cây mục lục 9 Chương / 89 Điều |
| `GET /api/search?q=` | Kết quả tìm từ khóa có cấu trúc kèm trích đoạn |
| `GET /api/penalties` | Bảng mức phạt + danh sách phương tiện để lọc |
| `GET /api/benchmark` | Metrics + 35 kết quả chi tiết |
| `GET /api/pdf` | PDF gốc, `Content-Disposition: inline` + range request |

`/api/health` mở rộng: thêm model embedding, số Chương, số nhóm vi phạm, và bảng tình trạng
5 tệp dữ liệu (tồn tại chưa, dung lượng).

**DRY:** tách `TrafficLawTools.search_articles()` trả kết quả có cấu trúc; `keyword_search()`
(công cụ của Agent) và `/api/search` (giao diện) cùng dùng nó, nên hai nơi không chấm điểm lệch nhau.

## 4. Frontend — tách module theo khu vực

`app.js` cũ 1 file đã phình. Nay tách theo ES modules, không file nào quá 350 dòng:

| Tệp | Dòng | Vai trò |
|---|---|---|
| `utils.js` | 57 | Markdown, `fetchJson`, tiện ích DOM |
| `app.js` | 80 | Điều phối khu vực, thanh bên, đèn trạng thái |
| `penalty.js` | 85 | Bảng mức phạt |
| `system.js` | 95 | Quản trị & benchmark |
| `law.js` | 111 | Cây mục lục, tìm kiếm, khung đọc |
| `chat.js` | 345 | Hỏi đáp AI + lưu phiên |

Mỗi khu vực tự nạp dữ liệu ở lần mở đầu tiên → khởi động không kéo theo 61 MB PDF hay bảng benchmark.

## 5. Lỗi phát hiện khi kiểm thử

`FileResponse(..., filename=...)` đặt header `Content-Disposition: attachment` → trình duyệt **tải
file về** thay vì hiển thị, khung PDF trắng trơn. Đã đổi sang `inline`. Xác nhận lại bằng Chrome
thật: PDF hiện đủ 68 trang kèm thumbnail, zoom, in.

## 6. Kiểm chứng (Playwright, 0 lỗi console)

| Kiểm thử | Kết quả |
|---|---|
| Thanh bên / đèn trạng thái | "89 Điều đã nạp" |
| Tra cứu luật | 9 Chương · 89 Điều · mở Điều 1 đọc được toàn văn |
| Tìm kiếm "nồng độ cồn" | 15 kết quả kèm trích đoạn |
| Bảng mức phạt | 10 thẻ · 6 lựa chọn phương tiện · lọc "Ô tô" còn 3 |
| Quản trị | 3 thẻ · 6 chỉ số · 40 dòng bảng (35 benchmark + 5 tệp dữ liệu) |
| PDF | Header `inline` + `accept-ranges: bytes`; Chrome render đủ 68 trang |
| Hỏi đáp AI | Nguồn `[Điều 9, Điều 58]`, chip mở toàn văn 5.994 ký tự |
| Lưu phiên | Còn nguyên sau khi tải lại trang, khôi phục đúng 2 tin nhắn |
| CLI `chat.py` | 4,19s — không ảnh hưởng |
| `compileall` + kiểm cú pháp 6 module ES | Sạch |

Server test chạy cổng 8099 rồi dừng hẳn; app của bạn ở cổng 8080 không bị đụng.

## 7. Câu hỏi còn lại

- Bảng tính tiền phạt tương tác (nhập tốc độ/nồng độ cồn → ra số tiền) vẫn chưa dựng lại. Khu vực
  "Bảng mức phạt" hiện là bảng tra cứu đầy đủ nhưng không tính toán theo tham số. Có cần thêm không?
- `data/processed/markdown/` (9 file .md theo chương) hiện chưa được giao diện dùng tới — nội dung
  trùng với dữ liệu đã hiển thị ở khu Tra cứu luật. Giữ nguyên hay bỏ?
