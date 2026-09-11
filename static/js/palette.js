/**
 * palette.js - Command Palette Ctrl+K (Tra cứu chéo toàn cục & Điều hướng nhanh)
 * Nạp on-demand (lazy), tìm kiếm tức thời biển báo & vạch kẻ, debounce API với luật & mức phạt.
 */

import { fetchJson, escapeHtml } from './utils.js';
import { getIcon } from './ui/icons.js';
import { navigate } from './router.js';

let modalOverlay = null;
let searchInput = null;
let resultsList = null;
let closeBtn = null;

let isOpen = false;
let previouslyFocused = null;
let activeItemIndex = -1;
let flatResults = [];

// Cache dữ liệu nạp một lần khi mở lần đầu
let signsCache = null;
let markingsCache = null;
let isCacheLoading = false;

// Debounce timer cho tìm kiếm API
let debounceTimer = null;

// Lối tắt điều hướng tĩnh
const STATIC_NAV = [
  { id: 'nav-chat', type: 'nav', title: 'Hỏi đáp AI', sub: 'Trợ lý pháp lý giao thông thông minh', url: '#/chat', icon: 'chat', badge: 'Khu vực' },
  { id: 'nav-law', type: 'nav', title: 'Tra cứu bộ luật', sub: '6 văn bản quy phạm pháp luật 2024–2025', url: '#/luat', icon: 'book', badge: 'Khu vực' },
  { id: 'nav-penalty', type: 'nav', title: 'Bảng mức phạt Nghị định 168', sub: '634 hành vi vi phạm có chế tài chi tiết', url: '#/muc-phat', icon: 'receipt', badge: 'Khu vực' },
  { id: 'nav-signs', type: 'nav', title: 'Kho 363 Biển báo giao thông', sub: 'Quy chuẩn QCVN 41:2019/BGTVT', url: '#/tien-ich/bien-bao', icon: 'traffic-cone', badge: 'Tiện ích' },
  { id: 'nav-speed', type: 'nav', title: 'Bộ tính tốc độ & khoảng cách an toàn', sub: 'Căn cứ Thông tư 31/2019/TT-BGTVT', url: '#/tien-ich/toc-do', icon: 'traffic-cone', badge: 'Tiện ích' },
  { id: 'nav-points', type: 'nav', title: 'Hệ thống 12 Điểm Giấy phép lái xe', sub: 'Cẩm nang trừ điểm & phục hồi điểm GPLX 2025', url: '#/tien-ich/diem-gplx', icon: 'traffic-cone', badge: 'Tiện ích' },
  { id: 'nav-markings', type: 'nav', title: 'Tra cứu 43 Vạch kẻ đường', sub: 'Tránh nhầm lẫn lỗi đè vạch và đi sai làn', url: '#/tien-ich/vach-ke', icon: 'traffic-cone', badge: 'Tiện ích' },
  { id: 'nav-pdf', type: 'nav', title: 'Xem văn bản gốc PDF', sub: 'Bản PDF có Text Layer tìm kiếm được', url: '#/van-ban', icon: 'file-text', badge: 'Tài liệu' }
];

/**
 * Nạp trước danh mục biển báo và vạch kẻ đường ở chế độ nền
 */
async function loadStaticCaches() {
  if (signsCache && markingsCache) return;
  if (isCacheLoading) return;
  isCacheLoading = true;

  try {
    const [signsRes, markingsRes] = await Promise.all([
      fetchJson('/api/utilities/signs?limit=400').catch(() => ({ items: [] })),
      fetchJson('/api/utilities/road-markings').catch(() => ({ items: [] }))
    ]);
    signsCache = signsRes.items || [];
    markingsCache = markingsRes.items || [];
  } catch (err) {
    console.warn('[Palette] Lỗi khi nạp dữ liệu biển báo/vạch kẻ:', err);
  } finally {
    isCacheLoading = false;
  }
}

/**
 * Lấy danh sách lịch sử tìm kiếm gần đây từ localStorage
 */
function getRecentSearches() {
  try {
    return JSON.parse(localStorage.getItem('lextraffic_recent_palette') || '[]');
  } catch {
    return [];
  }
}

/**
 * Lưu mục vừa chọn vào lịch sử tìm kiếm gần đây
 */
function saveRecentSearch(item) {
  try {
    let recents = getRecentSearches().filter(r => r.url !== item.url);
    recents.unshift({
      title: item.title,
      sub: item.sub,
      url: item.url,
      type: item.type,
      icon: item.icon,
      badge: item.badge
    });
    if (recents.length > 5) recents = recents.slice(0, 5);
    localStorage.setItem('lextraffic_recent_palette', JSON.stringify(recents));
  } catch {}
}

/**
 * Render trạng thái mặc định ban đầu (khi chưa gõ từ khóa)
 */
function renderDefaultView() {
  flatResults = [];
  resultsList.innerHTML = '';

  const recents = getRecentSearches();
  if (recents.length > 0) {
    appendGroup('Tìm kiếm gần đây', recents);
  }

  appendGroup('Lối tắt điều hướng nhanh', STATIC_NAV);
  highlightItem(0);
}

function appendGroup(groupTitle, items) {
  if (!items || !items.length) return;

  const titleEl = document.createElement('div');
  titleEl.className = 'palette__group-title';
  titleEl.textContent = groupTitle;
  resultsList.appendChild(titleEl);

  items.forEach(item => {
    const itemIndex = flatResults.length;
    flatResults.push(item);

    const row = document.createElement('div');
    row.className = 'palette__item';
    row.setAttribute('role', 'option');
    row.setAttribute('data-index', itemIndex);

    const mainDiv = document.createElement('div');
    mainDiv.className = 'palette__item-main';

    const iconDiv = document.createElement('div');
    iconDiv.className = 'palette__item-icon';
    iconDiv.innerHTML = getIcon(item.icon || 'search');

    const textsDiv = document.createElement('div');
    textsDiv.className = 'palette__item-texts';

    const titleSpan = document.createElement('span');
    titleSpan.className = 'palette__item-title';
    titleSpan.textContent = item.title;

    const subSpan = document.createElement('span');
    subSpan.className = 'palette__item-sub';
    subSpan.textContent = item.sub;

    textsDiv.appendChild(titleSpan);
    textsDiv.appendChild(subSpan);

    mainDiv.appendChild(iconDiv);
    mainDiv.appendChild(textsDiv);

    row.appendChild(mainDiv);

    if (item.badge) {
      const badgeSpan = document.createElement('span');
      badgeSpan.className = 'palette__item-badge';
      badgeSpan.textContent = item.badge;
      row.appendChild(badgeSpan);
    }

    row.addEventListener('click', () => {
      selectResult(item);
    });

    resultsList.appendChild(row);
  });
}

function highlightItem(index) {
  if (flatResults.length === 0) {
    activeItemIndex = -1;
    return;
  }

  activeItemIndex = Math.max(0, Math.min(index, flatResults.length - 1));
  const rows = resultsList.querySelectorAll('.palette__item');
  rows.forEach((row, idx) => {
    if (idx === activeItemIndex) {
      row.classList.add('palette__item--active');
      row.scrollIntoView({ block: 'nearest' });
    } else {
      row.classList.remove('palette__item--active');
    }
  });
}

function selectResult(item) {
  if (!item) return;
  saveRecentSearch(item);
  closePalette();
  navigate(item.url);
}

/**
 * Thực hiện tìm kiếm chéo 4 nguồn dữ liệu
 */
async function performSearch(query) {
  const q = query.trim().toLowerCase();
  if (!q) {
    renderDefaultView();
    return;
  }

  flatResults = [];
  resultsList.innerHTML = '';

  // 1. Biển báo khớp từ khóa (In-Memory)
  let matchedSigns = [];
  if (signsCache) {
    matchedSigns = signsCache.filter(s =>
      s.sign_code.toLowerCase().includes(q) ||
      s.sign_name.toLowerCase().includes(q) ||
      (s.meaning || '').toLowerCase().includes(q)
    ).slice(0, 5).map(s => ({
      title: `${s.sign_code} · ${s.sign_name}`,
      sub: s.sign_group || 'QCVN 41:2019/BGTVT',
      url: `#/tien-ich/bien-bao/${encodeURIComponent(s.sign_code)}`,
      icon: 'traffic-cone',
      badge: 'Biển báo',
      type: 'sign'
    }));
  }

  // 2. Vạch kẻ đường khớp từ khóa (In-Memory)
  let matchedMarkings = [];
  if (markingsCache) {
    matchedMarkings = markingsCache.filter(m =>
      (m.marking_code || '').toLowerCase().includes(q) ||
      (m.name || '').toLowerCase().includes(q)
    ).slice(0, 5).map(m => ({
      title: `${m.marking_code || 'Vạch'} · ${m.name}`,
      sub: m.type || 'Vạch kẻ đường',
      url: `#/tien-ich/vach-ke/${m.id || ''}`,
      icon: 'traffic-cone',
      badge: 'Vạch kẻ',
      type: 'marking'
    }));
  }

  // 3. Mức phạt vi phạm (API Call)
  let matchedPenalties = [];
  try {
    const pData = await fetchJson(`/api/penalties?q=${encodeURIComponent(q)}&limit=5`);
    if (pData && pData.items) {
      matchedPenalties = pData.items.map(p => ({
        title: p.behaviour,
        sub: `Phạt: ${p.fine_text} · ${p.citation}`,
        url: `#/muc-phat?q=${encodeURIComponent(p.behaviour)}`,
        icon: 'receipt',
        badge: 'Mức phạt',
        type: 'penalty'
      }));
    }
  } catch {}

  // 4. Điều luật (API Call)
  let matchedLaws = [];
  try {
    const lData = await fetchJson(`/api/search?q=${encodeURIComponent(q)}`);
    if (lData && lData.results) {
      // /api/search trả về `article_header` (đã gồm cả "Điều N."), không phải `title`
      matchedLaws = lData.results.slice(0, 5).map(r => ({
        title: r.article_header || `Điều ${r.article_number || ''}`,
        sub: [r.doc_name, r.chapter_title].filter(Boolean).join(' · ') || 'Văn bản quy phạm pháp luật',
        url: `#/luat/${r.doc_id || '01_luat_36_2024_qh15'}/dieu-${r.article_number || 1}`,
        icon: 'book',
        badge: 'Điều luật',
        type: 'law'
      }));
    }
  } catch {}

  // Hiển thị các nhóm kết quả theo thứ tự ưu tiên
  if (matchedLaws.length > 0) appendGroup('Điều luật quy định', matchedLaws);
  if (matchedPenalties.length > 0) appendGroup('Hành vi xử phạt (NĐ 168)', matchedPenalties);
  if (matchedSigns.length > 0) appendGroup('Biển báo giao thông (QCVN 41)', matchedSigns);
  if (matchedMarkings.length > 0) appendGroup('Vạch kẻ đường', matchedMarkings);

  if (flatResults.length === 0) {
    resultsList.innerHTML = `
      <div class="palette__empty">
        <p>Không tìm thấy kết quả phù hợp với "<strong>${escapeHtml(query)}</strong>"</p>
        <span class="palette__empty-hint">Thử tìm kiếm với từ khóa khác như "nồng độ cồn", "P.106a", "Điều 9"...</span>
      </div>
    `;
    activeItemIndex = -1;
  } else {
    highlightItem(0);
  }
}

export function openPalette() {
  if (isOpen) return;
  isOpen = true;
  previouslyFocused = document.activeElement;

  modalOverlay.classList.add('palette--open');
  modalOverlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('scroll-locked');

  loadStaticCaches();
  searchInput.value = '';
  renderDefaultView();

  requestAnimationFrame(() => {
    searchInput.focus();
    searchInput.select();
  });
}

export function closePalette() {
  if (!isOpen) return;
  isOpen = false;

  modalOverlay.classList.remove('palette--open');
  modalOverlay.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('scroll-locked');

  if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
    previouslyFocused.focus();
  }
}

export function initCommandPalette() {
  modalOverlay = document.getElementById('command-palette-modal');
  if (!modalOverlay) return;

  searchInput = document.getElementById('palette-search-input');
  resultsList = document.getElementById('palette-results-list');
  closeBtn = document.getElementById('btn-palette-close');

  // Phím tắt toàn cục Ctrl+K / Cmd+K
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (isOpen) closePalette();
      else openPalette();
    }
  });

  // Nút đóng
  if (closeBtn) {
    closeBtn.addEventListener('click', closePalette);
  }

  // Click ra ngoài backdrop để đóng
  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) {
      closePalette();
    }
  });

  // Điều khiển bàn phím trong ô tìm kiếm
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closePalette();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlightItem(activeItemIndex + 1);
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlightItem(activeItemIndex - 1);
      return;
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      if (activeItemIndex >= 0 && activeItemIndex < flatResults.length) {
        selectResult(flatResults[activeItemIndex]);
      }
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault(); // Chặn Tab thoát khỏi ô tìm kiếm
    }
  });

  // Tìm kiếm với Debounce 200ms
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      performSearch(searchInput.value);
    }, 200);
  });
}
