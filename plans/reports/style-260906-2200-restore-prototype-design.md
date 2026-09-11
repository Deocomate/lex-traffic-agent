# Áp lại hệ thiết kế của bản prototype gốc

Ngày: 2026-09-06 22:00 · Tiếp nối `feat-260906-2135-restore-utilities-sidebar.md`

## 1. Vấn đề

Giao diện mới chạy đúng chức năng nhưng dùng hệ màu trung tính tự nghĩ ra, khác hẳn phong cách
bản prototype cũ mà người dùng thích.

## 2. Cách làm

Không dựng lại từ đầu. Trích hệ thiết kế từ file prototype đã sao lưu, rồi **thay toàn bộ tầng
trình bày** (`app.css` + phần khung `index.html`). Toàn bộ JS, API và logic Agent giữ nguyên,
mọi tên class/ID cũ được giữ nên không file JS nào phải sửa.

Chụp lại 3 màn hình của prototype cũ để đối chiếu trực tiếp thay vì đoán theo trí nhớ.

## 3. Hệ thiết kế đã khôi phục

| Thành phần | Đặc trưng |
|---|---|
| Sidebar | Navy `#0f172a`, chữ slate, mục đang mở = nền `#1e293b` + thanh nhấn **emerald** bên trái |
| Logo | Badge gradient emerald `#10b981 → #059669` kèm glow, nhãn `2024` màu amber |
| Nhóm menu | Nhãn in hoa cỡ 9.5px, giãn chữ 0.08em |
| Chân sidebar | Thẻ trạng thái nền emerald mờ, chấm phát sáng |
| Canvas | Trắng ngà `#f8fafc`, thẻ trắng bo 12px, viền `#e2e8f0`, bóng 2 lớp |
| Màu ngữ nghĩa | **amber** = tiền phạt · **rose** = nghiêm trọng · **emerald** = hợp lệ · **blue** = căn cứ pháp lý |
| Bubble người dùng | Navy `#1e293b`, chữ trắng, bóng nổi |
| Chip nguồn | Nền `blue-50`, viền `blue-100`, chữ `blue-600`, hover đảo thành nền xanh đặc |
| Typography | Inter 13.5px · Plus Jakarta Sans cho tiêu đề · JetBrains Mono cho mã |

Bỏ chế độ tối tự động: bản gốc là thiết kế sáng có chủ đích (sidebar tối + nội dung sáng), thêm
dark mode sẽ phá vỡ tương phản đó.

## 4. Kiểm chứng (Playwright, 0 lỗi console)

Chạy lại nguyên bộ kiểm thử của vòng trước — không có hồi quy:

| Kiểm thử | Kết quả |
|---|---|
| Thanh bên / trạng thái | "89 Điều đã nạp" |
| Tra cứu luật | 9 Chương · 89 Điều · đọc được toàn văn |
| Tìm "nồng độ cồn" | 15 kết quả |
| Bảng mức phạt | 10 thẻ · lọc "Ô tô" còn 3 |
| Quản trị | 3 thẻ · 6 chỉ số · 40 dòng |
| PDF | iframe render |
| Hỏi đáp AI | Nguồn `[Điều 9, Điều 58]`, chip mở toàn văn 5.994 ký tự |
| Lưu phiên | Còn nguyên sau reload, khôi phục đúng 2 tin nhắn |

## 5. Đã khôi phục file

`lextraffic_ai_desktop.html` và `README.html` được đặt lại vào thư mục gốc từ bản sao lưu, làm
tài liệu tham chiếu thiết kế — vì bản sao lưu nằm trong thư mục tạm của phiên làm việc, để nguyên
ở đó thì mất khi phiên kết thúc. Chúng vẫn không được nối vào launcher. Xoá lại lúc nào cũng được.

## 6. Câu hỏi còn lại

- Font Inter / Plus Jakarta Sans / JetBrains Mono tải từ Google Fonts như bản prototype cũ. Máy
  không có mạng sẽ tự lùi về font hệ thống (bố cục không vỡ). Có cần nhúng font vào máy để chạy
  hoàn toàn offline không?
- Bản prototype cũ còn vài chi tiết trang trí chưa mang sang: ô tìm nhanh kèm phím tắt `⌘K` trên
  topbar, avatar người dùng, hình minh hoạ ô tô ở trang chủ. Có muốn thêm không?
