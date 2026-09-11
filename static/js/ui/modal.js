/**
 * modal.js - Component Modal đạt chuẩn WAI-ARIA Dialog (Modal)
 * - Tự động bẫy tiêu điểm (focus trap)
 * - Đóng bằng phím Esc và click backdrop
 * - Khôi phục tiêu điểm cho phần tử trước đó
 * - Khóa cuộn trang nền không giật bố cục
 */

import { getIcon } from './icons.js';

let activeModals = [];
let scrollbarWidth = null;

function getScrollbarWidth() {
  if (scrollbarWidth !== null) return scrollbarWidth;
  const outer = document.createElement('div');
  outer.style.visibility = 'hidden';
  outer.style.overflow = 'scroll';
  document.body.appendChild(outer);
  const inner = document.createElement('div');
  outer.appendChild(inner);
  scrollbarWidth = outer.offsetWidth - inner.offsetWidth;
  outer.parentNode.removeChild(outer);
  return scrollbarWidth;
}

/**
 * Mở một cửa sổ modal mới
 * @param {Object} config
 * @param {string} config.title - Tiêu đề modal
 * @param {string} [config.badge] - Nhãn huy hiệu góc trên
 * @param {HTMLElement|string} config.bodyNode - Nội dung phần thân
 * @param {Array<{label: string, variant?: string, onClick?: Function}>} [config.actions] - Nút hành động
 * @param {Function} [config.onClose] - Callback khi modal đóng
 * @returns {{ close: Function, panel: HTMLElement }}
 */
export function openModal({ title, badge, bodyNode, actions = [], onClose }) {
  const previouslyFocused = document.activeElement;
  const modalId = `modal-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const titleId = `${modalId}-title`;

  // Khóa cuộn trang nền. Bề rộng thanh cuộn là giá trị đo runtime nên vẫn
  // gán trực tiếp qua style; phần overflow dùng class theo hệ thiết kế.
  if (activeModals.length === 0) {
    const sw = getScrollbarWidth();
    if (sw > 0 && window.innerWidth > document.documentElement.clientWidth) {
      document.body.style.paddingRight = `${sw}px`;
    }
    document.body.classList.add('scroll-locked');
  }

  // Khung DOM modal
  const wrapper = document.createElement('div');
  wrapper.className = 'modal';
  wrapper.id = modalId;
  wrapper.setAttribute('role', 'presentation');

  const backdrop = document.createElement('div');
  backdrop.className = 'modal__backdrop';

  const panel = document.createElement('div');
  panel.className = 'modal__panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-labelledby', titleId);

  // Header
  const head = document.createElement('div');
  head.className = 'modal__head';

  const titleGroup = document.createElement('div');
  titleGroup.className = 'modal__title-group';

  if (badge) {
    const badgeEl = document.createElement('span');
    badgeEl.className = 'badge badge--neutral';
    badgeEl.textContent = badge;
    titleGroup.appendChild(badgeEl);
  }

  const h3 = document.createElement('h3');
  h3.id = titleId;
  h3.className = 'modal__title';
  h3.textContent = title;
  titleGroup.appendChild(h3);
  head.appendChild(titleGroup);

  const closeBtn = document.createElement('button');
  closeBtn.className = 'btn btn--ghost btn--icon';
  closeBtn.setAttribute('type', 'button');
  closeBtn.setAttribute('aria-label', 'Đóng hộp thoại');
  closeBtn.innerHTML = getIcon('close');
  head.appendChild(closeBtn);
  panel.appendChild(head);

  // Body
  const body = document.createElement('div');
  body.className = 'modal__body';
  if (typeof bodyNode === 'string') {
    body.innerHTML = bodyNode;
  } else if (bodyNode instanceof HTMLElement) {
    body.appendChild(bodyNode);
  }
  panel.appendChild(body);

  // Footer / Actions
  if (actions && actions.length > 0) {
    const foot = document.createElement('div');
    foot.className = 'modal__foot';

    actions.forEach(action => {
      const btn = document.createElement('button');
      btn.type = 'button';
      const variantClass = action.variant === 'primary' ? 'btn--primary' : 'btn--ghost';
      btn.className = `btn ${variantClass}`;
      btn.textContent = action.label;
      btn.addEventListener('click', (e) => {
        if (action.onClick) {
          action.onClick(e, close);
        } else {
          close();
        }
      });
      foot.appendChild(btn);
    });

    panel.appendChild(foot);
  }

  wrapper.appendChild(backdrop);
  wrapper.appendChild(panel);
  document.body.appendChild(wrapper);

  // Thêm vào danh sách modal đang kích hoạt
  const modalEntry = {
    wrapper,
    previouslyFocused,
    close
  };
  activeModals.push(modalEntry);

  // Kích hoạt animation
  requestAnimationFrame(() => {
    wrapper.classList.add('modal--open');
  });

  // Bẫy tiêu điểm (Focus Trap)
  const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  
  function getFocusableElements() {
    return Array.from(panel.querySelectorAll(focusableSelector)).filter(el => !el.hasAttribute('disabled'));
  }

  // Tiêu điểm mặc định vào nút đóng hoặc phần tử đầu tiên
  const focusables = getFocusableElements();
  if (focusables.length > 0) {
    focusables[0].focus();
  } else {
    panel.focus();
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }

    if (e.key === 'Tab') {
      const items = getFocusableElements();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  }

  window.addEventListener('keydown', handleKeyDown);

  // Click backdrop để đóng
  backdrop.addEventListener('click', () => {
    close();
  });

  closeBtn.addEventListener('click', () => {
    close();
  });

  function close() {
    window.removeEventListener('keydown', handleKeyDown);
    wrapper.classList.remove('modal--open');

    setTimeout(() => {
      if (wrapper.parentNode) {
        wrapper.parentNode.removeChild(wrapper);
      }

      // Gỡ khỏi activeModals
      activeModals = activeModals.filter(m => m !== modalEntry);

      // Nếu không còn modal nào thì khôi phục cuộn trang
      if (activeModals.length === 0) {
        document.body.classList.remove('scroll-locked');
        document.body.style.paddingRight = '';
      }

      // Khôi phục tiêu điểm
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus();
      }

      if (onClose) onClose();
    }, 180);
  }

  return { close, panel };
}
