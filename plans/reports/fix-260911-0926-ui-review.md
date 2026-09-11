# Rà soát và tối ưu UI theo backend mới

**Ngày:** 2026-09-11 09:26 | **Chế độ:** `/ak:fix` + 2 subagent `ui-ux-designer` (sonnet) chạy song song
**Trạng thái:** DONE

## 0. Trả lời câu hỏi gốc

Trước phiên này, giao diện **chưa** được cập nhật theo backend mới — đúng như non-goal đã chốt trong
`plan.md` ("Không redesign giao diện"). Hợp đồng SSE được giữ nguyên tuyệt đối chính là để frontend
không phải sửa. Thay đổi UI duy nhất từ đầu dự án là `thread_id` trong `chat.js` (Phase 6).

Phiên này đã kiểm chứng thật (chạy máy chủ, gửi câu hỏi thật) và tối ưu toàn diện.

## 1. Lỗi thật đã sửa

### 1.1 `verified` gần như không bao giờ được phát (backend)

Điều kiện cũ: `not issues AND repair_count > 0` — chỉ phát **sau khi đã phải sửa**. Ở đường đi thuận
lợi (câu trả lời đúng ngay, tức đa số lượt), giao diện không nhận tín hiệu nào cho thấy câu trả lời
đã được đối chiếu với văn bản gốc, dù `agent-trace.js` có sẵn nhánh hiển thị và style.

Cùng loại lỗi với `model_fallback` vá hôm qua: **handler tồn tại nhưng sự kiện không bao giờ tới**.
Kiểm chứng tất định là khác biệt lớn nhất của sản phẩm — để nó vô hình đúng lúc nó làm tốt là bỏ phí
tín hiệu tin cậy đáng giá nhất.

Nay phát cho mọi câu sạch, nội dung phân biệt hai trường hợp. Khoá bằng 2 test.
**Kiểm chứng thật:** `start → turn_start → tool_call → tool_result → synthesizing → token×113 →
answer_commit → verified → done`.

### 1.2 `showToast(msg, 'success'|'warning')` luôn ra màu mặc định

Wrapper trong `utils.js` đặt tên tham số là `duration` rồi truyền xuống, nên biến thể viết tắt dạng
chuỗi bị hiểu nhầm. **Ảnh hưởng toàn ứng dụng**: 5 tệp có lời gọi kiểu này (`chat.js`, `sources.js`,
`utilities.js`, `law.js`, `penalty.js`) — mọi toast "thành công"/"cảnh báo" đều hiển thị sai màu.

### 1.3 Rò rỉ spinner và listener trong `chat.js`

`setInterval` không được dọn khi `fetch` ban đầu thất bại → spinner quay vĩnh viễn. `initChat()`
thiếu cờ chống khởi tạo lại (trong khi `system.js` có) → chồng listener.

### 1.4 Re-render markdown O(n²) khi stream token

Mỗi câu trả lời phát ~140 sự kiện `token`, mỗi lần parse lại **toàn bộ** markdown. Đã tiết lưu bằng
`requestAnimationFrame`.

### 1.5 `.trace__notice--info` không tồn tại

Sự kiện `verifying` gắn class không có style → không hiển thị gì.

### 1.6 `aria-selected` không đồng bộ khi chuyển tab

`law.js` và `utilities.js`: trình đọc màn hình luôn đọc sai tab đang mở. `app.js`: `aria-expanded`
sai trạng thái khi tải trang trên mobile. `<label for>` trỏ vào phần tử không focus được ở
`utilities.html`/`pdf.html` (đã thêm `config.id` cho `ui/select.js`).

### 1.7 Vi phạm hệ thiết kế

Hardcode `32px`/`4px`/`22px` trong `components.css`, `shell.css`, `lookup.css` → đưa về token (thêm
`--control-height-xs`). Thay `style.overflow` inline trong `modal.js`/`palette.js` bằng class
`.scroll-locked`. Thêm `.toast--warning` còn thiếu. Nút sao chép quá nhỏ → thêm `hit-area`.

## 2. Bổ sung theo năng lực backend mới

- **`model_used`**: backend gửi trong `done` nhưng frontend bỏ qua. Nay hiển thị kín đáo ở thanh
  công cụ tin nhắn, có nhãn riêng khi câu trả lời đến từ `semantic_cache`.
- **Huy hiệu kiểm chứng** ở đầu khối trace, tồn tại kể cả sau khi trace tự thu gọn — để tín hiệu
  `verified`/`warning` không biến mất khỏi tầm mắt.
- **Trang `#/he-thong`**: panel mới đọc `GET /api/trace/summary` (độ trễ theo node, chi phí, phân bố
  tier, tỉ lệ fallback). Dựng từ class có sẵn, không phát sinh CSS mới. Ghi rõ endpoint **chỉ trả số
  liệu tổng hợp, không bao giờ trả nội dung câu hỏi**, và "tỉ lệ trúng cache" ở đây là **cache vector
  truy vấn**, không phải cache câu trả lời.

## 3. Tài liệu đã sửa

`docs/design-system.md` mô tả sai thực tế ở hai chỗ, đã sửa theo mã nguồn:
- §3.2: mô tả cấu trúc BEM `.field > .field__control > .input` **chưa bao giờ tồn tại**. Thực tế
  `.field` đặt thẳng trên ô nhập, khối bao là `.field-wrap`, nhãn là `.field-label`.
- §4: liệt kê `#/law`, `#/penalties`, `#/utilities` — **không đường nào tồn tại**. Định tuyến thật
  dùng tiếng Việt không dấu: `#/luat`, `#/muc-phat`, `#/tien-ich`, `#/van-ban`, `#/he-thong`.

`docs/architecture.md`: cập nhật bảng hợp đồng SSE cho `verified`, thêm mục giải thích vì sao tín
hiệu kiểm chứng phải nhìn thấy được cả khi mọi thứ đều ổn.

## 4. Kiểm chứng

- **169 test xanh** (từ 167; thêm 2 test cho điều kiện phát `verified`).
- `node --check` sạch trên toàn bộ JS đã sửa.
- Máy chủ chạy thật: `/`, `/api/health`, `/api/trace/summary` trả 200; toàn bộ JS/CSS đã sửa trả 200.
- `POST /api/ask` thật: chuỗi SSE đầy đủ, `verified` xuất hiện, `done` đủ 8 trường.
- Quét lại: **0** `style="..."` inline trong `templates/`+`static/js/`, **0** mã màu hex ngoài
  `tokens.css`. Các lệnh `.style.` còn lại là đo đạc động (chiều cao textarea, bề rộng thanh cuộn),
  không phải quyết định thị giác.
- Không còn tiến trình máy chủ mồ côi; cổng 8097/8098/8099 đã giải phóng.

## Câu hỏi còn treo

1. Câu trả lời **trúng cache ngữ nghĩa** hiện không phát `verified` (đồ thị không chạy). Nhưng theo
   thiết kế Phase 6, **chỉ câu đã qua kiểm chứng mới được ghi cache** — nên về bản chất nó vẫn là câu
   đã kiểm chứng. Có muốn phát `verified` cho cả đường cache không?
2. Còn một lỗ hổng tiềm ẩn về escape thuộc tính HTML trong `law_formatter.js`/`penalty.js`. Dữ liệu
   đưa vào là văn bản luật tĩnh đáng tin, không phải input người dùng, nên **chưa sửa**: sửa đúng cách
   phải đụng hợp đồng `escapeHtml` dùng chung với `chat.js`. Có muốn xử lý trong một phiên riêng không?
