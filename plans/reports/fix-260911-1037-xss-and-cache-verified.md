# Hai việc còn treo: chèn thuộc tính HTML + `verified` trên đường cache

**Ngày:** 2026-09-11 10:37 | **Chế độ:** `/ak:fix` | **Trạng thái:** DONE

## 1. XSS qua markdown do mô hình sinh (nghiêm trọng — nặng hơn báo cáo trước)

Báo cáo trước xếp việc này là "lỗ hổng tiềm ẩn trên dữ liệu pháp luật tĩnh đáng tin". **Đánh giá đó
quá nhẹ.** Kiểm chứng thực tế bằng `node` cho thấy đây là lỗ hổng sống, nằm trên đường kết xuất
**câu trả lời do mô hình sinh**.

**Nguyên nhân gốc:** `escapeHtml()` trong `static/js/markdown.js:46` chỉ escape `&`, `<`, `>` —
**không escape dấu nháy**. Trong khi đó `inline()` dựng thuộc tính từ chính văn bản đã escape đó:
`alt="${caption}"` và `src="${cleanSrc}"`.

**Bằng chứng chạy thật (trước khi sửa):**
```
![x" onerror="alert(1)](/a.png)
  -> <img src="/a.png" alt="x" onerror="alert(1)" class="traffic-sign-img" loading="lazy">
```
`onerror` là thuộc tính thật, chạy thật.

**Vì sao không thể coi là dữ liệu tin cậy:** markdown đi vào đây do **LLM sinh ra**, mà đầu vào của
LLM gồm văn bản pháp luật truy xuất được **và chính câu hỏi của người dùng**. Đây là đường prompt
injection kinh điển, không phải rủi ro lý thuyết.

**Blast radius:** `escapeHtml` được dùng ở **11 tệp JS**, và được nội suy vào thuộc tính ở
`penalty.js`, `sources.js`, `utilities.js`, `markdown.js`.

**Cách sửa — sửa tận gốc, không vá từng chỗ gọi:** escape thêm `"` → `&quot;` và `'` → `&#39;` ngay
trong `escapeHtml()`. Đã kiểm từng nơi gọi trước khi sửa:
- Không nơi nào gán kết quả vào `textContent` (chỉ dựng chuỗi HTML) → escape thêm không làm hiện
  `&quot;` nguyên dạng ra màn hình.
- Không luật markdown nào phụ thuộc dấu nháy (`QUOTE = /^(&gt;|>)/` vốn đã nhận dạng đầu vào đã
  escape — thiết kế này từ đầu đã lường trước việc escape sớm).

Cách này DRY hơn hẳn phương án thêm một hàm `escapeAttr()` song song mà mọi nơi gọi phải nhớ dùng.

**Kiểm chứng:** `tests/test_markdown_escaping.py` (3 test, gọi `node` thật, tự bỏ qua nếu máy không
có `node`). **Đã chứng minh test có ý nghĩa**: tạm gỡ fix ra thì 2/3 test đỏ, lắp lại thì xanh.
Kết xuất bình thường không hề đổi — đã kiểm ảnh biển báo, bảng, blockquote, liên kết, khối mã,
thẻ căn cứ pháp lý.

## 2. `verified` trên đường trúng cache

**Vấn đề:** câu lấy từ cache ngữ nghĩa không phát `verified`, nên cùng một câu hỏi hiển thị khác
nhau giữa lần đầu và lần sau, dù nội dung trả về **giống hệt từng ký tự**.

**Đã kiểm chứng tiền đề trước khi sửa:** `_store_cache()` (`src/graph/turn.py:239`) chỉ ghi khi
`is_cacheable(answer, issues, needs_search, sources)` đúng — tức không còn `issues`, không cần tra
cứu ngoài, và có nguồn. **Không có đường nào đưa câu chưa kiểm chứng vào cache**, nên phát
`verified` ở đây là đúng sự thật chứ không phải trang trí.

**Kiểm chứng thật:** gọi `POST /api/ask` trên máy chủ đang chạy, câu trúng cache cho chuỗi
`start → turn_start → tool_result → token → answer_commit → verified → done` với
`model_used: semantic_cache`.

## 3. Kiểm thử

- **173 test xanh** (từ 169; thêm 3 test XSS + 1 test đường cache).
- `node --check` sạch trên `markdown.js`.
- Máy chủ chạy thật, xác nhận cả hai đường (đồ thị và cache) đều phát `verified`.
- Không còn tiến trình máy chủ mồ côi.

## 4. Tài liệu

`docs/architecture.md`: cập nhật bảng hợp đồng SSE (`verified` nay có cả nguồn phát
`_emit_cached_answer`), thêm mục "Nội dung mô hình sinh ra KHÔNG phải dữ liệu tin cậy" kèm payload
tái hiện được.

## Đính chính

Báo cáo `fix-260911-0926-ui-review.md` mô tả lỗ hổng này là "dữ liệu đưa vào là văn bản luật tĩnh
đáng tin, không phải input người dùng". Sai — nó nằm trên đường kết xuất đầu ra mô hình, và đầu ra
đó chịu ảnh hưởng từ câu hỏi người dùng. Mức độ đúng là **lỗ hổng XSS thật**, không phải rủi ro
tiềm ẩn hạng thấp.

## Câu hỏi còn treo

Không.
