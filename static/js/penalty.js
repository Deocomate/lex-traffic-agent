/**
 * Khu vực Bảng mức phạt: tra cứu trực tiếp 634 hành vi vi phạm bóc tách từ toàn văn
 * Nghị định 168/2024/NĐ-CP (hiệu lực 01/01/2025).
 * 
 * Hiển thị in đậm số tiền phạt, trừ điểm GPLX và các hình thức xử phạt bổ sung.
 */

import { fetchJson, el, escapeHtml, showToast } from './utils.js';
import { createSelect } from './ui/select.js';

const searchBox = document.getElementById('penalty-search');
const vehicleBox = document.getElementById('penalty-vehicle');
const listBox = document.getElementById('penalty-list');
const statsBar = document.getElementById('penalty-stats-bar');
const quickTagsBox = document.getElementById('penalty-quick-tags');

let items = [];
let loaded = false;
let vehicleSelect = null;

/**
 * Cột chế tài đã có tiêu đề riêng nên không cần lặp lại chữ "Phạt tiền từ … đến …"
 * ở mọi dòng. Rút về đúng khoảng tiền để mắt so sánh được theo hàng dọc; chuỗi
 * nào không khớp khuôn thì giữ nguyên văn.
 */
function compactFine(fineText) {
  if (!fineText) return '';
  const range = fineText.match(/từ\s+([\d.]+)\s*đồng\s+đến\s+([\d.]+)\s*đồng/i);
  if (range) return `${range[1]} – ${range[2]} đồng`;
  return fineText;
}

function render() {
  const keyword = searchBox.value.trim().toLowerCase();
  const vehicle = vehicleBox.value;

  const filtered = items.filter(item =>
    (!vehicle || item.vehicle === vehicle) &&
    (!keyword || item.behaviour.toLowerCase().includes(keyword)
              || item.article_title.toLowerCase().includes(keyword))
  );

  if (statsBar) {
    statsBar.innerHTML = `<span>Đang hiển thị <strong>${filtered.length}</strong> / <strong>${items.length}</strong> hành vi vi phạm (Nghị định 168/2024/NĐ-CP)</span>`;
  }

  listBox.innerHTML = '';
  if (!filtered.length) {
    listBox.appendChild(el('div', 'placeholder', 'Không có hành vi nào khớp với bộ lọc tra cứu.'));
    return;
  }

  const fragment = document.createDocumentFragment();
  filtered.forEach(item => {
    const card = el('div', 'penalty-card');

    const sanctions = (item.extra_sanctions || [])
      .map(s => `<span class="pv-sanction">${escapeHtml(s)}</span>`)
      .join('');

    card.innerHTML = `
      <div class="pv-main">
        <div class="pv-badges">
          <span class="badge badge--neutral badge--xs">${escapeHtml(item.vehicle)}</span>
          <span class="pv-meta">${escapeHtml(item.citation)}</span>
        </div>
        <p class="pv-behaviour"></p>
        ${sanctions ? `<div class="pv-sanctions">${sanctions}</div>` : ''}
      </div>
      <div class="pv-verdict">
        <span class="pv-fine" title="${escapeHtml(item.fine_text)}">${escapeHtml(compactFine(item.fine_text))}</span>
        ${item.points_deducted
          ? `<span class="pv-points-badge pts-${item.points_deducted}">&minus;${item.points_deducted} điểm GPLX</span>`
          : ''}
      </div>
    `;

    card.querySelector('.pv-behaviour').textContent = item.behaviour;

    card.addEventListener('click', () => {
      const copyText = `${item.behaviour} (${item.vehicle})\nMức phạt: ${item.fine_text}\n${item.points_deducted ? `Trừ điểm: ${item.points_deducted} điểm GPLX\n` : ''}Căn cứ: ${item.citation}`;
      navigator.clipboard.writeText(copyText).then(() => {
        showToast('Đã sao chép hành vi & mức phạt!');
      });
    });

    fragment.appendChild(card);
  });
  listBox.appendChild(fragment);
}

export async function initPenaltyView() {
  if (loaded) return;
  loaded = true;

  searchBox.addEventListener('input', render);
  vehicleBox.addEventListener('change', render);

  // Gắn sự kiện cho các tag chip nhanh
  if (quickTagsBox) {
    quickTagsBox.querySelectorAll('.tag-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        searchBox.value = btn.dataset.q || '';
        render();
      });
    });
  }

  try {
    const data = await fetchJson('/api/penalties?limit=1000');
    items = data.items;

    if (vehicleBox) {
      const options = [
        { value: '', label: 'Tất cả phương tiện' },
        ...data.vehicles.map(v => ({ value: v, label: v }))
      ];
      vehicleSelect = createSelect(vehicleBox, {
        options,
        value: '',
        ariaLabel: 'Lọc theo loại phương tiện',
        onChange: () => render()
      });
    }

    render();
  } catch (err) {
    loaded = false;
    listBox.innerHTML = `<div class="placeholder">Không tải được bảng mức phạt: ${escapeHtml(err.message)}</div>`;
  }
}

/** Khôi phục bộ lọc từ URL route (#/muc-phat?xe=...&q=...) */
export async function handlePenaltyRoute(route) {
  if (!loaded) await initPenaltyView();
  const q = route.query.q || '';
  const vehicle = route.query.xe || '';

  if (searchBox && q !== undefined) searchBox.value = q;
  if (vehicleSelect && vehicle) {
    vehicleSelect.setValue(vehicle);
  }
  render();
}

