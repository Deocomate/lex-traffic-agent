/** Tiện ích dùng chung cho mọi khu vực giao diện */

// Bộ dựng Markdown sống ở markdown.js: nó đủ lớn và đủ nhiều quy tắc riêng để
// đứng thành một module, còn tệp này giữ vai trò tiện ích chung.
export { escapeHtml, renderMarkdown } from './markdown.js';

/** Gọi API JSON, ném lỗi kèm thông điệp máy chủ trả về để giao diện hiển thị đúng nguyên nhân */
export async function fetchJson(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Máy chủ trả về lỗi ${res.status}`);
  return data;
}

/** Tạo phần tử DOM kèm class và nội dung, gọn hơn chuỗi createElement lặp lại */
export function el(tag, className, html) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (html !== undefined) node.innerHTML = html;
  return node;
}

import { showToast as uiShowToast } from './ui/toast.js';

/**
 * Hiển thị toast thông báo nhanh (ủy quyền sang ui/toast.js).
 * Chuyển tiếp `options` nguyên trạng — ui/toast.js tự nhận diện đó là số
 * (thời lượng), chuỗi ('success' | 'warning' | 'error', viết tắt cho biến
 * thể) hay object {variant, duration} đầy đủ. Trước đây tệp này đặt tên
 * tham số là `duration` rồi truyền thẳng xuống, khiến gọi showToast(msg,
 * 'success') bị hiểu nhầm thành duration và luôn rơi về biến thể mặc định.
 */
export function showToast(message, options) {
  uiShowToast(message, options);
}
