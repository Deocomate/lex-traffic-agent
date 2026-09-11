/**
 * select.js — Select tự dựng theo mẫu WAI-ARIA Combobox + Listbox.
 *
 * Thay hoàn toàn <select> gốc của trình duyệt:
 * - Bàn phím đầy đủ: ↑ ↓, Home/End, Enter, Space, Esc, Tab, gõ để nhảy (500ms).
 * - Danh sách gắn vào <body> và định vị bằng position:fixed nên không bao giờ
 *   bị cắt bởi phần tử cha có overflow:hidden.
 * - Danh sách dài (từ 10 mục) tự có ô lọc; danh sách ngắn thì không.
 * - Dưới 640px chuyển thành bottom sheet, mỗi mục cao ≥ 44px.
 * - Phát sự kiện 'change' chuẩn trên phần tử gắn kết và hỗ trợ đọc/ghi `.value`.
 */

import { getIcon } from './icons.js';

/** Từ ngưỡng này trở lên, danh sách đáng có ô lọc */
const FILTER_THRESHOLD = 10;

let selectCounter = 0;

/** Bỏ dấu tiếng Việt để gõ "toc do" vẫn tìm ra "Tốc độ" */
function normalize(str) {
  return String(str)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd');
}

/**
 * @param {HTMLElement} mountEl Phần tử chứa
 * @param {Object} config
 * @param {Array<{value: string, label: string, group?: string}>} config.options
 * @param {string} [config.value] Giá trị khởi tạo
 * @param {string} [config.placeholder='Chọn…']
 * @param {string} [config.ariaLabel]
 * @param {string} [config.id] Gán vào trigger để <label for="..."> ngoài template bắt được focus
 * @param {Function} [config.onChange]
 * @returns {{getValue: Function, setValue: Function, setOptions: Function, destroy: Function, element: HTMLElement}}
 */
export function createSelect(mountEl, config = {}) {
  const instanceId = ++selectCounter;
  const listId = `select-list-${instanceId}`;

  let options = config.options || [];
  let currentValue = config.value !== undefined ? config.value : (options[0]?.value || '');
  const placeholder = config.placeholder || 'Chọn…';
  const ariaLabel = config.ariaLabel || 'Lựa chọn';
  const onChange = config.onChange || null;

  let isOpen = false;
  let filterText = '';
  let visible = [];        // Các mục đang hiện, kèm chỉ số gốc: {opt, index}
  let activePos = -1;      // Vị trí trong `visible`, không phải trong `options`
  let typeahead = '';
  let typeaheadTimer = null;

  // -------------------------------------------------------------------------
  // Dựng DOM
  // -------------------------------------------------------------------------
  mountEl.classList.add('select');
  mountEl.setAttribute('data-select', '');
  mountEl.innerHTML = '';

  const trigger = document.createElement('button');
  trigger.className = 'select__trigger';
  trigger.type = 'button';
  trigger.setAttribute('role', 'combobox');
  trigger.setAttribute('aria-haspopup', 'listbox');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.setAttribute('aria-controls', listId);
  trigger.setAttribute('aria-label', ariaLabel);
  // Cho phép <label for="..."> trỏ thẳng vào control thật sự nhận focus
  // (mountEl chỉ là hộp chứa <div>, không phải phần tử gắn nhãn được).
  if (config.id) trigger.id = config.id;

  const valueSpan = document.createElement('span');
  valueSpan.className = 'select__value';

  const caretSpan = document.createElement('span');
  caretSpan.className = 'select__caret';
  caretSpan.setAttribute('aria-hidden', 'true');
  caretSpan.innerHTML = getIcon('chevron-down');

  trigger.append(valueSpan, caretSpan);
  mountEl.appendChild(trigger);

  // Danh sách sống ở <body> để thoát mọi ngữ cảnh overflow của trang
  const listbox = document.createElement('ul');
  listbox.className = 'select__list';
  listbox.id = listId;
  listbox.setAttribute('role', 'listbox');
  listbox.setAttribute('aria-label', ariaLabel);
  listbox.hidden = true;
  document.body.appendChild(listbox);

  let filterInput = null;

  // -------------------------------------------------------------------------
  // Kết xuất
  // -------------------------------------------------------------------------

  function updateTriggerLabel() {
    const selected = options.find(o => String(o.value) === String(currentValue));
    valueSpan.textContent = selected ? selected.label : placeholder;
    valueSpan.classList.toggle('select__value--placeholder', !selected);
  }

  function computeVisible() {
    if (!filterText) {
      visible = options.map((opt, index) => ({ opt, index }));
      return;
    }
    const needle = normalize(filterText);
    visible = options
      .map((opt, index) => ({ opt, index }))
      .filter(({ opt }) => normalize(opt.label).includes(needle));
  }

  function renderFilterBox() {
    if (options.length < FILTER_THRESHOLD) {
      filterInput = null;
      return;
    }

    const box = document.createElement('li');
    box.className = 'select__filter-box';
    box.setAttribute('role', 'presentation');

    const icon = document.createElement('span');
    icon.className = 'select__filter-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = getIcon('search');

    filterInput = document.createElement('input');
    filterInput.type = 'text';
    filterInput.className = 'select__filter-input';
    filterInput.placeholder = 'Lọc danh sách…';
    filterInput.autocomplete = 'off';
    filterInput.spellcheck = false;
    filterInput.value = filterText;
    filterInput.setAttribute('aria-label', `Lọc ${ariaLabel}`);

    filterInput.addEventListener('input', () => {
      filterText = filterInput.value;
      renderOptions();
      activePos = visible.length ? 0 : -1;
      highlight(activePos);
      positionList();
    });

    filterInput.addEventListener('keydown', onNavigationKey);

    box.append(icon, filterInput);
    listbox.appendChild(box);
  }

  function renderOptions() {
    const keepFocus = filterInput && document.activeElement === filterInput;

    listbox.innerHTML = '';
    renderFilterBox();
    computeVisible();

    if (!visible.length) {
      const empty = document.createElement('li');
      empty.className = 'select__no-result';
      empty.setAttribute('role', 'presentation');
      empty.textContent = 'Không có mục nào khớp';
      listbox.appendChild(empty);
      if (keepFocus && filterInput) filterInput.focus();
      return;
    }

    let currentGroup = null;

    visible.forEach(({ opt, index }, pos) => {
      if (opt.group && opt.group !== currentGroup) {
        currentGroup = opt.group;
        const groupEl = document.createElement('li');
        groupEl.className = 'select__group-label';
        groupEl.setAttribute('role', 'presentation');
        groupEl.textContent = currentGroup;
        listbox.appendChild(groupEl);
      }

      const optEl = document.createElement('li');
      optEl.className = 'select__option';
      optEl.id = `${listId}-opt-${index}`;
      optEl.setAttribute('role', 'option');
      optEl.dataset.value = opt.value;
      optEl.dataset.pos = String(pos);

      const isSelected = String(opt.value) === String(currentValue);
      optEl.setAttribute('aria-selected', isSelected ? 'true' : 'false');
      optEl.classList.toggle('select__option--selected', isSelected);

      const text = document.createElement('span');
      text.className = 'select__option-text';
      text.textContent = opt.label;

      const check = document.createElement('span');
      check.className = 'select__option-check';
      check.setAttribute('aria-hidden', 'true');
      check.innerHTML = getIcon('check');

      optEl.append(text, check);

      optEl.addEventListener('click', (e) => {
        e.stopPropagation();
        commit(index);
        closeList();
        trigger.focus();
      });

      // Rê chuột đồng bộ với mục đang được bàn phím trỏ tới
      optEl.addEventListener('mousemove', () => {
        if (activePos !== pos) {
          activePos = pos;
          highlight(activePos);
        }
      });

      listbox.appendChild(optEl);
    });

    if (keepFocus && filterInput) filterInput.focus();
  }

  function highlight(pos) {
    const items = listbox.querySelectorAll('.select__option');
    items.forEach((item, i) => {
      const active = i === pos;
      item.classList.toggle('select__option--active', active);
      if (active) {
        trigger.setAttribute('aria-activedescendant', item.id);
        item.scrollIntoView({ block: 'nearest' });
      }
    });
    if (pos < 0) trigger.removeAttribute('aria-activedescendant');
  }

  // -------------------------------------------------------------------------
  // Định vị
  // -------------------------------------------------------------------------

  function positionList() {
    if (!isOpen) return;

    if (window.innerWidth <= 640) {
      listbox.classList.add('select__list--sheet');
      listbox.classList.remove('select__list--flipped');
      listbox.style.cssText = '';
      return;
    }

    listbox.classList.remove('select__list--sheet');

    const rect = trigger.getBoundingClientRect();
    const GAP = 4;
    const MARGIN = 8;

    // Bề rộng bám trigger nhưng không bao giờ vượt mép màn hình
    const width = Math.min(Math.max(rect.width, 200), window.innerWidth - MARGIN * 2);
    const left = Math.min(Math.max(rect.left, MARGIN), window.innerWidth - width - MARGIN);
    listbox.style.left = `${left}px`;
    listbox.style.width = `${width}px`;

    const spaceBelow = window.innerHeight - rect.bottom - GAP - MARGIN;
    const spaceAbove = rect.top - GAP - MARGIN;
    const needed = listbox.scrollHeight;

    // Chỉ lật lên trên khi phía dưới thật sự không đủ và phía trên rộng hơn
    if (needed > spaceBelow && spaceAbove > spaceBelow) {
      listbox.style.top = '';
      listbox.style.bottom = `${window.innerHeight - rect.top + GAP}px`;
      listbox.style.maxHeight = `${spaceAbove}px`;
      listbox.classList.add('select__list--flipped');
    } else {
      listbox.style.bottom = '';
      listbox.style.top = `${rect.bottom + GAP}px`;
      listbox.style.maxHeight = `${spaceBelow}px`;
      listbox.classList.remove('select__list--flipped');
    }
  }

  // -------------------------------------------------------------------------
  // Mở / đóng
  // -------------------------------------------------------------------------

  function openList() {
    if (isOpen) return;
    isOpen = true;
    filterText = '';
    trigger.setAttribute('aria-expanded', 'true');
    mountEl.classList.add('select--open');
    listbox.hidden = false;

    renderOptions();
    activePos = visible.findIndex(({ opt }) => String(opt.value) === String(currentValue));
    if (activePos === -1 && visible.length) activePos = 0;

    positionList();
    highlight(activePos);

    if (filterInput) filterInput.focus();

    // Đăng ký ở lượt sự kiện kế tiếp để cú click đang mở không tự đóng ngay
    setTimeout(() => {
      window.addEventListener('click', onOutsideClick);
      window.addEventListener('resize', positionList);
      window.addEventListener('scroll', onViewportScroll, true);
    }, 0);

    // Danh sách sống ở <body> nên nó không biến mất khi ứng dụng đổi khu vực.
    // Đóng theo điều hướng để không có dropdown mồ côi trôi trên màn hình.
    window.addEventListener('hashchange', closeList);
  }

  function closeList() {
    if (!isOpen) return;
    isOpen = false;
    filterText = '';
    trigger.setAttribute('aria-expanded', 'false');
    trigger.removeAttribute('aria-activedescendant');
    mountEl.classList.remove('select--open');
    listbox.hidden = true;

    window.removeEventListener('click', onOutsideClick);
    window.removeEventListener('resize', positionList);
    window.removeEventListener('scroll', onViewportScroll, true);
    window.removeEventListener('hashchange', closeList);
  }

  function onOutsideClick(e) {
    if (!mountEl.contains(e.target) && !listbox.contains(e.target)) closeList();
  }

  function onViewportScroll(e) {
    // Cuộn bên trong chính danh sách thì giữ nguyên vị trí
    if (e && e.target && e.target !== document && listbox.contains(e.target)) return;
    positionList();
  }

  // -------------------------------------------------------------------------
  // Chọn giá trị
  // -------------------------------------------------------------------------

  function commit(index) {
    const selected = options[index];
    if (!selected) return;

    const oldValue = currentValue;
    currentValue = selected.value;
    updateTriggerLabel();

    if (String(oldValue) === String(currentValue)) return;

    if (onChange) onChange(currentValue, selected);
    mountEl.dispatchEvent(new CustomEvent('change', {
      bubbles: true,
      detail: { value: currentValue, option: selected }
    }));
  }

  // -------------------------------------------------------------------------
  // Bàn phím
  // -------------------------------------------------------------------------

  function move(delta) {
    if (!visible.length) return;
    activePos = Math.max(0, Math.min(activePos + delta, visible.length - 1));
    highlight(activePos);
  }

  function onNavigationKey(e) {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (!isOpen) openList(); else move(1);
        return true;

      case 'ArrowUp':
        e.preventDefault();
        if (!isOpen) openList(); else move(-1);
        return true;

      case 'Home':
        if (isOpen) { e.preventDefault(); activePos = 0; highlight(activePos); }
        return true;

      case 'End':
        if (isOpen) { e.preventDefault(); activePos = visible.length - 1; highlight(activePos); }
        return true;

      case 'Enter':
        if (isOpen) {
          e.preventDefault();
          if (activePos >= 0 && visible[activePos]) commit(visible[activePos].index);
          closeList();
          trigger.focus();
        }
        return true;

      case 'Escape':
        if (isOpen) {
          e.preventDefault();
          e.stopPropagation();
          closeList();
          trigger.focus();
        }
        return true;

      case 'Tab':
        if (isOpen) closeList();
        return true;

      default:
        return false;
    }
  }

  trigger.addEventListener('keydown', (e) => {
    if (onNavigationKey(e)) return;

    if (e.key === ' ') {
      e.preventDefault();
      if (isOpen) {
        if (activePos >= 0 && visible[activePos]) commit(visible[activePos].index);
        closeList();
      } else {
        openList();
      }
      return;
    }

    // Gõ ký tự để nhảy tới mục tương ứng (chỉ khi danh sách không có ô lọc)
    if (!filterInput && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (!isOpen) openList();
      clearTimeout(typeaheadTimer);
      typeahead += e.key;
      typeaheadTimer = setTimeout(() => { typeahead = ''; }, 500);

      const needle = normalize(typeahead);
      const found = visible.findIndex(({ opt }) => normalize(opt.label).startsWith(needle));
      if (found !== -1) {
        activePos = found;
        highlight(activePos);
      }
    }
  });

  trigger.addEventListener('click', () => {
    if (isOpen) closeList();
    else openList();
  });

  // -------------------------------------------------------------------------
  // API công khai
  // -------------------------------------------------------------------------

  const api = {
    getValue: () => currentValue,

    setValue(val) {
      currentValue = val;
      updateTriggerLabel();
      if (isOpen) renderOptions();
    },

    setOptions(newOpts, newVal) {
      options = newOpts || [];
      if (newVal !== undefined) {
        currentValue = newVal;
      } else if (!options.some(o => String(o.value) === String(currentValue))) {
        currentValue = options[0]?.value || '';
      }
      updateTriggerLabel();
      if (isOpen) { renderOptions(); positionList(); }
    },

    destroy() {
      closeList();
      listbox.remove();
    },

    element: mountEl
  };

  // Cho phép đọc/ghi `.value` thẳng trên phần tử gắn kết, tương thích mã cũ
  Object.defineProperty(mountEl, 'value', {
    get() { return currentValue; },
    set(v) { api.setValue(v); },
    configurable: true
  });
  mountEl._selectInstance = api;

  updateTriggerLabel();
  computeVisible();

  return api;
}
