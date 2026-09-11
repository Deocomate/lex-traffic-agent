/**
 * LexTraffic AI — Logic điều phối Kho Tiện Ích Giao Thông Chuẩn (Traffic Utilities Hub)
 * 
 * 5 Phân hệ tiện ích:
 * 1. Biển báo giao thông (QCVN 41:2019 - 363 biển kèm ảnh và modal)
 * 2. Bộ tính toán tốc độ tối đa & khoảng cách an toàn (Thông tư 31/2019)
 * 3. Cẩm nang điểm giấy phép lái xe 12 điểm (Luật 36/2024 & NĐ 168)
 * 4. Tra cứu 43 vạch kẻ đường & cẩm nang tránh nhầm lỗi đè vạch vs sai làn
 * 5. Cẩm nang kiểm tra, dừng xe CSGT & xuất trình VNeID (Thông tư 73/2024)
 */

import { fetchJson, el, escapeHtml, showToast } from './utils.js';
import { createSelect } from './ui/select.js';

let loaded = false;
let currentSubView = 'signs';

// Caches
let signsData = [];
let currentSignGroup = '';
let pointsData = null;
let currentPointFilter = 'all';
let markingsData = [];
let policeData = null;

// Modal Elements
const modalOverlay = document.getElementById('detail-modal');
const modalBadge = document.getElementById('modal-badge');
const modalTitle = document.getElementById('modal-title');
const modalBody = document.getElementById('modal-body');
const btnModalClose = document.getElementById('btn-modal-close');
const btnModalDone = document.getElementById('btn-modal-done');
const btnModalCopy = document.getElementById('btn-modal-copy');

function openModal(badge, title, bodyHtml, copyText) {
  if (!modalOverlay) return;
  modalBadge.textContent = badge;
  modalTitle.textContent = title;
  modalBody.innerHTML = bodyHtml;
  modalOverlay.classList.add('open');
  modalOverlay.setAttribute('aria-hidden', 'false');

  if (btnModalCopy) {
    btnModalCopy.onclick = () => {
      navigator.clipboard.writeText(copyText || modalBody.innerText).then(() => {
        showToast('Đã sao chép thông tin chi tiết!', 'success');
      });
    };
  }
}

function closeModal() {
  if (modalOverlay) {
    modalOverlay.classList.remove('open');
    modalOverlay.setAttribute('aria-hidden', 'true');
  }
}

if (btnModalClose) btnModalClose.addEventListener('click', closeModal);
if (btnModalDone) btnModalDone.addEventListener('click', closeModal);
if (modalOverlay) {
  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay || e.target.classList.contains('modal__backdrop')) closeModal();
  });
}
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && modalOverlay?.classList.contains('open')) closeModal();
});

/* =========================================================================
   1. PHÂN HỆ BIỂN BÁO GIAO THÔNG (363 BIỂN)
   ========================================================================= */

function renderSigns() {
  const grid = document.getElementById('signs-grid');
  const countLabel = document.getElementById('signs-count-label');
  const searchInput = document.getElementById('signs-search');
  if (!grid) return;

  const q = (searchInput ? searchInput.value : '').trim().toLowerCase();

  const filtered = signsData.filter(item => {
    if (currentSignGroup && item.sign_group !== currentSignGroup) return false;
    if (q) {
      const matchCode = item.sign_code.toLowerCase().includes(q) || item.sign_code.toLowerCase().replace('.', '').includes(q);
      const matchName = item.sign_name.toLowerCase().includes(q);
      const matchMeaning = (item.meaning || '').toLowerCase().includes(q);
      if (!matchCode && !matchName && !matchMeaning) return false;
    }
    return true;
  });

  if (countLabel) {
    countLabel.textContent = `Hiển thị ${filtered.length} / ${signsData.length} biển báo giao thông`;
  }

  grid.innerHTML = '';
  if (!filtered.length) {
    grid.innerHTML = '<div class="placeholder grid-col-full">Không tìm thấy biển báo nào phù hợp với bộ lọc.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  filtered.forEach(item => {
    const card = document.createElement('div');
    card.className = 'sign-card';

    const cleanImg = item.image_path ? (item.image_path.startsWith('/') ? item.image_path : '/' + item.image_path) : '/static/img/sign-placeholder.svg';

    card.innerHTML = `
      <div class="sign-img-box">
        <img src="${cleanImg}" alt="${escapeHtml(item.sign_name)}" loading="lazy" />
      </div>
      <span class="sign-code">${escapeHtml(item.sign_code)}</span>
      <div class="sign-name" title="${escapeHtml(item.sign_name)}">${escapeHtml(item.sign_name)}</div>
      <div class="sign-group-tag">${escapeHtml(item.sign_group)}</div>
    `;

    card.addEventListener('click', () => {
      const bodyHtml = `
        <div class="modal-media-box">
          <img src="${cleanImg}" alt="${escapeHtml(item.sign_name)}" class="modal-media-img" />
        </div>
        <div class="modal-meta-row">
          <strong class="modal-meta-title">${escapeHtml(item.sign_code)}: ${escapeHtml(item.sign_name)}</strong>
          <div class="modal-meta-sub">Nhóm: ${escapeHtml(item.sign_group)}</div>
        </div>
        <div class="modal-content-section">
          <strong>Ý nghĩa sử dụng:</strong><br>
          ${escapeHtml(item.meaning || 'Theo quy định tại Quy chuẩn kỹ thuật quốc gia QCVN 41:2019/BGTVT.')}
        </div>
        <div class="modal-alert-box modal-alert-box--danger">
          <strong>Chế tài xử phạt khi không tuân thủ:</strong><br>
          Vi phạm không chấp hành hiệu lệnh biển báo bị xử phạt theo <strong>Điểm a Khoản 1 Điều 6 (Ô tô: 400.000 - 600.000 đ)</strong> hoặc <strong>Điểm a Khoản 1 Điều 7 (Xe máy: 200.000 - 400.000 đ)</strong> Nghị định 168/2024/NĐ-CP.
        </div>
      `;
      const copyText = `${item.sign_code} - ${item.sign_name}\nÝ nghĩa: ${item.meaning}\nCăn cứ: ${item.citation}`;
      openModal('QCVN 41:2019', `${item.sign_code} - ${item.sign_name}`, bodyHtml, copyText);
    });

    fragment.appendChild(card);
  });

  grid.appendChild(fragment);
}

async function loadSigns() {
  if (signsData.length) return;
  try {
    const data = await fetchJson('/api/utilities/signs?limit=400');
    signsData = data.items || [];
    renderSigns();
  } catch (err) {
    const grid = document.getElementById('signs-grid');
    if (grid) grid.innerHTML = `<div class="placeholder">Lỗi nạp biển báo: ${escapeHtml(err.message)}</div>`;
  }
}

/* =========================================================================
   2. BỘ TÍNH TOÁN TỐC ĐỘ VÀ KHOẢNG CÁCH (THÔNG TƯ 31/2019)
   ========================================================================= */

let speedVehicleSelect = null;
let speedRoadSelect = null;
let speedAreaSelect = null;

const VEHICLE_OPTIONS = [
  { value: 'car_light', label: 'Ô tô con, ô tô chở người đến 30 chỗ, ô tô tải đến 3.5 tấn' },
  { value: 'bus_heavy', label: 'Ô tô chở người trên 30 chỗ, xe khách, ô tô tải trên 3.5 tấn' },
  { value: 'trailer', label: 'Ô tô kéo rơ-moóc, ô tô đầu kéo sơ-mi rơ-moóc, xe buýt' },
  { value: 'motorcycle', label: 'Xe mô tô 2 bánh, xe mô tô 3 bánh' },
  { value: 'special', label: 'Xe máy chuyên dùng, xe gắn máy (kể cả xe máy điện, dưới 50cc)' }
];

const ROAD_OPTIONS = [
  { value: 'divided', label: 'Đường đôi (có dải phân cách giữa) hoặc Đường 1 chiều từ 2 làn xe' },
  { value: 'undivided', label: 'Đường hai chiều không có dải phân cách giữa hoặc Đường 1 chiều 1 làn xe' }
];

const AREA_OPTIONS = [
  { value: 'urban', label: 'Trong khu vực đông dân cư (Đô thị / Nội thị)' },
  { value: 'non_urban', label: 'Ngoài khu vực đông dân cư' },
  { value: 'expressway', label: 'Đường cao tốc' }
];

function calculateSpeed() {
  const vehicle = speedVehicleSelect ? speedVehicleSelect.getValue() : (document.getElementById('speed-vehicle')?.value || 'car_light');
  const road = speedRoadSelect ? speedRoadSelect.getValue() : (document.getElementById('speed-road')?.value || 'divided');
  const area = speedAreaSelect ? speedAreaSelect.getValue() : (document.getElementById('speed-area')?.value || 'urban');

  const valEl = document.getElementById('speed-val');
  const titleEl = document.getElementById('speed-rule-title');
  const descEl = document.getElementById('speed-rule-desc');
  const citationEl = document.getElementById('speed-citation');

  if (!valEl) return;

  let speed = 60;
  let ruleTitle = '';
  let ruleDesc = '';
  let citation = 'Thông tư 31/2019/TT-BGTVT';

  // 1. Xe máy chuyên dùng, xe gắn máy kể cả xe máy điện và xe dưới 50cc: Tối đa 40 km/h mọi nơi (trừ cao tốc không được đi)
  if (vehicle === 'special') {
    speed = 40;
    ruleTitle = 'Xe máy chuyên dùng, xe gắn máy (kể cả xe máy điện, dưới 50cc)';
    ruleDesc = 'Tốc độ tối đa cho phép không quá 40 km/h trên mọi tuyến đường bộ (trừ khi có biển báo quy định thấp hơn).';
    citation = 'Căn cứ: Điều 8 Thông tư 31/2019/TT-BGTVT';
  } else if (area === 'urban') {
    // Trong khu đông dân cư
    citation = 'Căn cứ: Điều 6 Thông tư 31/2019/TT-BGTVT';
    if (road === 'divided') {
      speed = 60;
      ruleTitle = 'Trong khu đông dân cư · Đường đôi / Đường từ 2 làn xe cơ giới';
      ruleDesc = 'Áp dụng cho ô tô con, ô tô khách, ô tô tải và xe mô tô 2 bánh.';
    } else {
      speed = 50;
      ruleTitle = 'Trong khu đông dân cư · Đường hai chiều / Đường 1 làn xe cơ giới';
      ruleDesc = 'Áp dụng cho ô tô con, ô tô khách, ô tô tải và xe mô tô 2 bánh.';
    }
  } else if (area === 'non_urban') {
    // Ngoài khu đông dân cư
    citation = 'Căn cứ: Điều 7 Thông tư 31/2019/TT-BGTVT';
    if (road === 'divided') {
      if (vehicle === 'car_light') {
        speed = 90;
        ruleTitle = 'Ngoài khu đông dân cư · Đường đôi · Ô tô con, xe tải ≤3.5t';
        ruleDesc = 'Ô tô con, ô tô chở người đến 30 chỗ (trừ xe buýt), ô tô tải có trọng tải đến 3.5 tấn.';
      } else if (vehicle === 'bus_heavy') {
        speed = 80;
        ruleTitle = 'Ngoài khu đông dân cư · Đường đôi · Ô tô chở người >30 chỗ, tải >3.5t';
        ruleDesc = 'Ô tô chở người trên 30 chỗ (trừ xe buýt), ô tô tải có trọng tải trên 3.5 tấn (trừ ô tô xi téc).';
      } else if (vehicle === 'trailer') {
        speed = 70;
        ruleTitle = 'Ngoài khu đông dân cư · Đường đôi · Xe buýt, đầu kéo sơ-mi rơ-moóc';
        ruleDesc = 'Ô tô buýt, ô tô đầu kéo kéo sơ mi rơ moóc, xe mô tô, ô tô chuyên dùng (trừ ô tô trộn vữa, ô tô trộn bê tông).';
      } else if (vehicle === 'motorcycle') {
        speed = 70;
        ruleTitle = 'Ngoài khu đông dân cư · Đường đôi · Xe mô tô';
        ruleDesc = 'Xe mô tô 2 bánh, xe mô tô 3 bánh lưu thông ngoài khu vực đông dân cư.';
      }
    } else {
      // Đường 2 chiều
      if (vehicle === 'car_light') {
        speed = 80;
        ruleTitle = 'Ngoài khu đông dân cư · Đường 2 chiều · Ô tô con, tải ≤3.5t';
        ruleDesc = 'Ô tô con, ô tô chở người đến 30 chỗ (trừ xe buýt), ô tô tải có trọng tải đến 3.5 tấn.';
      } else if (vehicle === 'bus_heavy') {
        speed = 70;
        ruleTitle = 'Ngoài khu đông dân cư · Đường 2 chiều · Xe khách >30 chỗ, tải >3.5t';
        ruleDesc = 'Ô tô chở người trên 30 chỗ (trừ xe buýt), ô tô tải có trọng tải trên 3.5 tấn.';
      } else if (vehicle === 'trailer' || vehicle === 'motorcycle') {
        speed = 60;
        ruleTitle = 'Ngoài khu đông dân cư · Đường 2 chiều · Xe buýt, mô tô';
        ruleDesc = 'Ô tô buýt, xe mô tô 2 bánh, ô tô đầu kéo kéo sơ mi rơ moóc.';
      }
    }
  } else if (area === 'expressway') {
    // Đường cao tốc
    speed = 120;
    ruleTitle = 'Đường cao tốc (Tốc độ tối đa thiết kế)';
    ruleDesc = 'Tốc độ tối đa không quá 120 km/h. Tốc độ cụ thể tuân thủ theo biển báo hiệu đặt trên từng tuyến cao tốc.';
    citation = 'Căn cứ: Điều 9 Thông tư 31/2019/TT-BGTVT và Điều 25 Luật 36/2024/QH15';
  }

  valEl.textContent = speed;
  titleEl.textContent = ruleTitle;
  descEl.textContent = ruleDesc;
  citationEl.textContent = citation;
}

function initSpeedCalculator() {
  const v = document.getElementById('speed-vehicle');
  const r = document.getElementById('speed-road');
  const a = document.getElementById('speed-area');

  if (v && !speedVehicleSelect) {
    speedVehicleSelect = createSelect(v, {
      options: VEHICLE_OPTIONS,
      value: 'car_light',
      ariaLabel: 'Loại phương tiện giao thông',
      id: 'speed-vehicle-trigger',
      onChange: calculateSpeed
    });
  }

  if (r && !speedRoadSelect) {
    speedRoadSelect = createSelect(r, {
      options: ROAD_OPTIONS,
      value: 'divided',
      ariaLabel: 'Loại kết cấu đường',
      id: 'speed-road-trigger',
      onChange: calculateSpeed
    });
  }

  if (a && !speedAreaSelect) {
    speedAreaSelect = createSelect(a, {
      options: AREA_OPTIONS,
      value: 'urban',
      ariaLabel: 'Khu vực di chuyển',
      id: 'speed-area-trigger',
      onChange: calculateSpeed
    });
  }

  calculateSpeed();
}

/* =========================================================================
   3. CẨM NANG ĐIỂM GIẤY PHÉP LÁI XE 12 ĐIỂM (LUẬT 36 & NĐ 168)
   ========================================================================= */

function renderPointsList() {
  const container = document.getElementById('points-list');
  if (!container || !pointsData) return;

  container.innerHTML = '';
  const groups = pointsData.groups || {};

  let itemsToRender = [];
  if (currentPointFilter === 'all') {
    Object.values(groups).forEach(g => {
      itemsToRender = itemsToRender.concat(g.items || []);
    });
  } else if (groups[currentPointFilter]) {
    itemsToRender = groups[currentPointFilter].items || [];
  }

  if (!itemsToRender.length) {
    container.innerHTML = '<div class="placeholder">Không có hành vi vi phạm nào trong nhóm điểm này.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  itemsToRender.slice(0, 100).forEach(item => {
    const card = document.createElement('div');
    card.className = 'point-violation-card';

    const pts = item.points_deducted;
    const ptsClass = `pts-${pts}`;

    card.innerHTML = `
      <div class="pv-main">
        <div class="pv-badges">
          <span class="badge-vehicle">${escapeHtml(item.vehicle)}</span>
          <span class="badge badge--fine">${escapeHtml(item.fine_text)}</span>
        </div>
        <div class="pv-behaviour">${escapeHtml(item.behaviour)}</div>
        <div class="pv-meta">${escapeHtml(item.citation)}</div>
      </div>
      <div class="pv-points-badge ${ptsClass}">
        -${pts} ĐIỂM
      </div>
    `;

    fragment.appendChild(card);
  });

  container.appendChild(fragment);
}

async function loadPointsData() {
  if (pointsData) return;
  try {
    pointsData = await fetchJson('/api/utilities/license-points');
    renderPointsList();
  } catch (err) {
    const container = document.getElementById('points-list');
    if (container) container.innerHTML = `<div class="placeholder">Lỗi tải dữ liệu điểm bằng lái: ${escapeHtml(err.message)}</div>`;
  }
}

/* =========================================================================
   4. TRA CỨU 43 VẠCH KẺ ĐƯỜNG & TRÁNH NHẦM LỖI (QCVN 41:2019)
   ========================================================================= */

function renderRoadMarkings() {
  const grid = document.getElementById('markings-grid');
  const searchInput = document.getElementById('markings-search');
  if (!grid) return;

  const q = (searchInput ? searchInput.value : '').trim().toLowerCase();

  const filtered = markingsData.filter(m => {
    if (!q) return true;
    return m.marking_code.toLowerCase().includes(q) ||
           m.marking_name.toLowerCase().includes(q) ||
           (m.meaning || '').toLowerCase().includes(q);
  });

  grid.innerHTML = '';
  if (!filtered.length) {
    grid.innerHTML = '<div class="placeholder grid-col-full">Không tìm thấy vạch kẻ đường nào phù hợp.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  filtered.forEach(m => {
    const card = document.createElement('div');
    card.className = 'marking-card';

    const cleanImg = m.image_path ? (m.image_path.startsWith('/') ? m.image_path : '/' + m.image_path) : '/static/img/sign-placeholder.svg';

    card.innerHTML = `
      <div class="marking-card-top">
        <span class="marking-code">Vạch ${escapeHtml(m.marking_code)}</span>
        <span class="marking-citation">${escapeHtml(m.citation)}</span>
      </div>
      <div class="marking-img-wrap">
        <img src="${cleanImg}" alt="${escapeHtml(m.marking_name)}" loading="lazy" />
      </div>
      <div class="marking-title">${escapeHtml(m.marking_name)}</div>
      <div class="marking-meaning">${escapeHtml((m.meaning || '').slice(0, 180))}...</div>
    `;

    card.addEventListener('click', () => {
      const bodyHtml = `
        <div class="modal-media-box">
          <img src="${cleanImg}" alt="${escapeHtml(m.marking_name)}" class="modal-media-img modal-media-img--marking" />
        </div>
        <div class="modal-meta-row">
          <strong class="modal-meta-title">Vạch ${escapeHtml(m.marking_code)}: ${escapeHtml(m.marking_name)}</strong>
        </div>
        <div class="modal-content-section">
          ${escapeHtml(m.meaning || 'Quy chuẩn theo Phụ lục G QCVN 41:2019/BGTVT.')}
        </div>
        <div class="modal-alert-box modal-alert-box--success">
          <strong>Lưu ý pháp lý khi đè vạch:</strong><br>
          Đè vạch ${escapeHtml(m.marking_code)} chỉ bị phạt lỗi <em>Không chấp hành hiệu lệnh, chỉ dẫn của vạch kẻ đường</em> (200k - 400k), hoàn toàn không phải lỗi đi sai làn đường (4 - 6 triệu)!
        </div>
      `;
      openModal('QCVN 41:2019 (Phụ lục G)', `Vạch ${m.marking_code} - ${m.marking_name}`, bodyHtml, `${m.marking_code}: ${m.marking_name}\n${m.meaning}`);
    });

    fragment.appendChild(card);
  });

  grid.appendChild(fragment);
}

async function loadRoadMarkings() {
  if (markingsData.length) return;
  try {
    const data = await fetchJson('/api/utilities/road-markings');
    markingsData = data.items || [];
    renderRoadMarkings();
  } catch (err) {
    const grid = document.getElementById('markings-grid');
    if (grid) grid.innerHTML = `<div class="placeholder">Lỗi nạp vạch kẻ đường: ${escapeHtml(err.message)}</div>`;
  }
}

/* =========================================================================
   5. CẨM NANG TUẦN TRA CSGT & XUẤT TRÌNH VNeID (THÔNG TƯ 73/2024)
   ========================================================================= */

function renderPoliceGuide() {
  const container = document.getElementById('police-guide-content');
  if (!container || !policeData) return;

  container.innerHTML = `
    <!-- 4 Trường hợp dừng xe -->
    <div class="police-section-card">
      <h4>4 Trường Hợp Cảnh Sát Giao Thông Được Phép Dừng Xe Kiểm Soát</h4>
      <div class="police-stop-cases-grid">
        ${(policeData.stop_cases || []).map(sc => `
          <div class="stop-case-item">
            <span class="stop-case-number">${sc.case_number}</span>
            <div class="stop-case-title">${escapeHtml(sc.title)}</div>
            <div class="stop-case-detail">${escapeHtml(sc.detail)}</div>
          </div>
        `).join('')}
      </div>
    </div>

    <!-- Giấy tờ và VNeID -->
    <div class="police-section-card">
      <h4>Giấy Tờ Bắt Buộc &amp; Giá Trị Pháp Lý Của Căn Cước Điện Tử VNeID</h4>
      <ul class="police-step-list">
        ${(policeData.documents_check || []).map(doc => `
          <li${doc.startsWith('💡') ? ' class="police-step--tip"' : ''}>${escapeHtml(doc.replace('💡', '').trim())}</li>
        `).join('')}
      </ul>
    </div>

    <!-- Quy trình thổi nồng độ cồn -->
    <div class="police-section-card">
      <h4>Quy Trình Kiểm Tra Nồng Độ Cồn Chuẩn 2 Bước Của CSGT</h4>
      <ol class="police-step-list">
        ${(policeData.breathalyzer_procedure || []).map(step => `
          <li>${escapeHtml(step)}</li>
        `).join('')}
      </ol>
    </div>

    <!-- Quyền giám sát của người dân -->
    <div class="police-section-card">
      <h4>Quyền Lợi &amp; Trách Nhiệm Giám Sát Hợp Pháp Của Công Dân</h4>
      <ul class="police-step-list">
        ${(policeData.citizen_rights || []).map(right => `
          <li>${escapeHtml(right)}</li>
        `).join('')}
      </ul>
    </div>
  `;
}

async function loadPoliceGuide() {
  if (policeData) return;
  try {
    policeData = await fetchJson('/api/utilities/police-patrol');
    renderPoliceGuide();
  } catch (err) {
    const container = document.getElementById('police-guide-content');
    if (container) container.innerHTML = `<div class="placeholder">Lỗi tải cẩm nang tuần tra: ${escapeHtml(err.message)}</div>`;
  }
}

/* =========================================================================
   ĐIỀU PHỐI CHUYỂN SUB-VIEW TRONG KHO TIỆN ÍCH
   ========================================================================= */

function switchSubView(subName) {
  currentSubView = subName;

  document.querySelectorAll('.util-tab').forEach(t => {
    const isTarget = t.dataset.sub === subName;
    t.classList.toggle('active', isTarget);
    t.setAttribute('aria-selected', isTarget ? 'true' : 'false');
  });

  document.querySelectorAll('.util-subview').forEach(v => {
    v.classList.toggle('active', v.id === `subview-${subName}`);
  });

  const pane = document.querySelector('#view-utilities .scroll-pane');
  if (pane) pane.scrollTop = 0;

  if (subName === 'signs') loadSigns();
  else if (subName === 'speed') initSpeedCalculator();
  else if (subName === 'points') loadPointsData();
  else if (subName === 'markings') loadRoadMarkings();
  else if (subName === 'police') loadPoliceGuide();
}

/** Khởi tạo View Tiện ích Giao thông */
export function initUtilitiesView() {
  if (loaded) return;
  loaded = true;

  // 1. Lắng nghe chuyển đổi 5 tab tiện ích
  document.querySelectorAll('.util-tab').forEach(btn => {
    btn.addEventListener('click', () => switchSubView(btn.dataset.sub));
  });

  // 2. Lắng nghe lọc nhóm biển báo
  const pillsBox = document.getElementById('signs-group-pills');
  if (pillsBox) {
    pillsBox.querySelectorAll('.pill').forEach(pill => {
      pill.addEventListener('click', () => {
        pillsBox.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        currentSignGroup = pill.dataset.group;
        renderSigns();
      });
    });
  }

  // 3. Lắng nghe tìm kiếm biển báo
  const signsSearch = document.getElementById('signs-search');
  if (signsSearch) {
    signsSearch.addEventListener('input', renderSigns);
  }

  // 4. Lắng nghe lọc điểm bằng lái
  const pointsTabs = document.getElementById('points-filter-tabs');
  if (pointsTabs) {
    pointsTabs.querySelectorAll('.points-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        pointsTabs.querySelectorAll('.points-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPointFilter = btn.dataset.level;
        renderPointsList();
      });
    });
  }

  // 5. Lắng nghe tìm kiếm vạch kẻ đường
  const markingsSearch = document.getElementById('markings-search');
  if (markingsSearch) {
    markingsSearch.addEventListener('input', renderRoadMarkings);
  }

  // Nạp mặc định subview đầu tiên
  switchSubView('signs');
}

/** Khôi phục trạng thái từ URL route (#/tien-ich/<subview>/<id>) */
export function handleUtilitiesRoute(route) {
  if (!loaded) initUtilitiesView();
  const subMap = {
    'bien-bao': 'signs',
    'signs': 'signs',
    'toc-do': 'speed',
    'speed': 'speed',
    'diem-gplx': 'points',
    'points': 'points',
    'vach-ke': 'markings',
    'markings': 'markings',
    'csgt': 'police',
    'police': 'police'
  };
  const sub = subMap[route.params[0]] || 'signs';
  switchSubView(sub);

  // Deep-link modal biển báo
  if (sub === 'signs' && route.params[1]) {
    const signCode = decodeURIComponent(route.params[1]);
    const checkAndOpen = () => {
      const sign = signsData.find(s => s.sign_code.toLowerCase() === signCode.toLowerCase());
      if (sign) {
        const cleanImg = sign.image_path ? (sign.image_path.startsWith('/') ? sign.image_path : '/' + sign.image_path) : '';
        const bodyHtml = `
          <div class="modal-media-box">
            <img src="${cleanImg}" alt="${escapeHtml(sign.sign_name)}" class="modal-media-img" />
          </div>
          <div class="modal-meta-row">
            <strong class="modal-meta-title">${escapeHtml(sign.sign_code)}: ${escapeHtml(sign.sign_name)}</strong>
            <div class="modal-meta-sub">Nhóm: ${escapeHtml(sign.sign_group)}</div>
          </div>
          <div class="modal-content-section">
            <strong>Ý nghĩa sử dụng:</strong><br>
            ${escapeHtml(sign.meaning || 'Theo quy định tại Quy chuẩn kỹ thuật quốc gia QCVN 41:2019/BGTVT.')}
          </div>
        `;
        openModal('QCVN 41:2019', `${sign.sign_code} - ${sign.sign_name}`, bodyHtml, `${sign.sign_code} - ${sign.sign_name}`);
      }
    };
    if (signsData.length) checkAndOpen();
    else {
      const timer = setInterval(() => {
        if (signsData.length) {
          clearInterval(timer);
          checkAndOpen();
        }
      }, 100);
      setTimeout(() => clearInterval(timer), 3000);
    }
  }
}
