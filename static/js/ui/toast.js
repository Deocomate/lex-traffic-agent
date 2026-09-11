/**
 * toast.js - Quản lý thông báo nổi (Toast Notification System)
 * Tối giản, trượt êm ái góc dưới phải, hỗ trợ aria-live cho trợ năng.
 */

let toastStack = null;

function ensureToastStack() {
  if (!toastStack) {
    toastStack = document.getElementById('toast-container');
    if (!toastStack) {
      toastStack = document.createElement('div');
      toastStack.id = 'toast-container';
      toastStack.className = 'toast-stack';
      toastStack.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastStack);
    }
  }
  return toastStack;
}

/**
 * Hiển thị một toast thông báo
 * @param {string} message - Nội dung thông báo
 * @param {Object|number|string} [options=2500] - Thời gian hiển thị (ms), tên
 *   biến thể viết tắt ('success' | 'warning' | 'error') hoặc object đầy đủ
 * @param {string} [options.variant='default'] - 'default' | 'error' | 'success' | 'warning'
 * @param {number} [options.duration=2500] - Thời gian hiển thị tính bằng ms
 */
export function showToast(message, options = {}) {
  const isVariantShorthand = typeof options === 'string';
  const duration = typeof options === 'number'
    ? options
    : (!isVariantShorthand && options.duration) || 2500;
  const variant = isVariantShorthand
    ? options
    : (typeof options === 'object' && options.variant) || 'default';

  const container = ensureToastStack();
  const toast = document.createElement('div');
  toast.className = `toast ${variant !== 'default' ? `toast--${variant}` : ''}`.trim();
  toast.setAttribute('role', 'status');

  const textSpan = document.createElement('span');
  textSpan.className = 'toast__message';
  textSpan.textContent = message;
  toast.appendChild(textSpan);

  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add('toast--visible');
  });

  // Tự ẩn và xóa khỏi DOM
  setTimeout(() => {
    toast.classList.remove('toast--visible');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 200);
  }, duration);
}
