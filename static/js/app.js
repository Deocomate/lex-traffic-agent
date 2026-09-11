/**
 * LexTraffic AI — Bộ điều phối giao diện chính (SPA Router & Shell Manager)
 * Quản lý chuyển tab và deep-link: Hỏi đáp AI, Tra cứu 6 bộ luật, Bảng mức phạt,
 * Kho Tiện Ích Giao Thông, Văn bản gốc PDF và Quản trị hệ thống.
 */

import { fetchJson } from './utils.js';
import { initRouter, navigate, getRoute } from './router.js';
import { initCommandPalette, openPalette } from './palette.js';
import { initChat } from './chat.js';
import { initLawView, handleLawRoute } from './law.js';
import { initPenaltyView, handlePenaltyRoute } from './penalty.js';
import { initUtilitiesView, handleUtilitiesRoute } from './utilities.js';
import { initPdfView, loadPdf } from './pdf.js';
import { initSystemView } from './system.js';

const VIEWS = {
  chat: {
    title: 'Hỏi đáp AI',
    sub: 'Trợ lý tra cứu phối hợp 6 văn bản Luật 2024 & Nghị định xử phạt',
    init: initChat
  },
  law: {
    title: 'Tra cứu 6 Bộ Luật & Văn Bản',
    sub: 'Luật 36/2024 · Luật 35/2024 · Nghị định 168/2024 · TT 31 · TT 73 · QCVN 41',
    init: initLawView
  },
  penalty: {
    title: 'Bảng mức phạt Nghị định 168',
    sub: '634 hành vi vi phạm có căn cứ Điểm, Khoản, Điều chính xác',
    init: initPenaltyView
  },
  utilities: {
    title: 'Kho Tiện Ích Giao Thông Chuẩn',
    sub: 'Biển báo QCVN 41 · Tính tốc độ & cự ly TT 31 · 12 Điểm GPLX · Vạch kẻ · CSGT',
    init: initUtilitiesView
  },
  pdf: {
    title: 'Văn bản gốc (PDF)',
    sub: 'Bản PDF có Text Layer tìm kiếm được của cả 6 văn bản quy phạm pháp luật',
    init: initPdfView
  },
  system: {
    title: 'Quản trị hệ thống',
    sub: 'Cấu hình model AI, dữ liệu đã nạp và hiệu năng truy xuất RAG',
    init: initSystemView
  }
};

const ROUTE_MAP = {
  'chat': 'chat',
  'luat': 'law',
  'muc-phat': 'penalty',
  'tien-ich': 'utilities',
  'van-ban': 'pdf',
  'he-thong': 'system'
};

const VIEW_TO_ROUTE = {
  'chat': 'chat',
  'law': 'luat',
  'penalty': 'muc-phat',
  'utilities': 'tien-ich',
  'pdf': 'van-ban',
  'system': 'he-thong'
};

/**
 * Chuyển đổi giao diện hiển thị giữa 6 view chức năng
 * @param {string} name - Tên nội bộ ('chat' | 'law' | 'penalty' | 'utilities' | 'pdf' | 'system')
 */
export function switchView(name) {
  const view = VIEWS[name];
  if (!view) return;

  // Cập nhật trạng thái active & aria-current trên các nav link
  document.querySelectorAll('.nav-item').forEach(el => {
    const isTarget = el.dataset.view === name;
    el.classList.toggle('active', isTarget);
    if (isTarget) {
      el.setAttribute('aria-current', 'page');
    } else {
      el.removeAttribute('aria-current');
    }
  });

  // Bật/tắt class active và thuộc tính hidden trên các khối view
  document.querySelectorAll('.view').forEach(v => {
    const isTarget = v.id === `view-${name}`;
    v.classList.toggle('active', isTarget);
    v.hidden = !isTarget;
  });

  const titleEl = document.getElementById('view-title');
  const subEl = document.getElementById('view-sub');
  if (titleEl) titleEl.textContent = view.title;
  if (subEl) subEl.textContent = view.sub;

  // Danh sách lịch sử chỉ hiện khi ở tab Chat
  document.body.classList.toggle('hide-history', name !== 'chat');

  // Đóng sidebar trên thiết bị di động khi chuyển trang
  if (window.innerWidth <= 900) {
    document.body.classList.remove('sidebar-open');
    const toggleBtn = document.getElementById('btn-toggle-sidebar');
    if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
  }

  // Khởi tạo lazy nội dung của view nếu chưa nạp
  if (view.init) view.init();
}

/**
 * Xử lý khi URL route thay đổi
 */
function onRouteMatched(route) {
  const viewKey = ROUTE_MAP[route.view] || 'chat';
  switchView(viewKey);

  if (route.view === 'chat' && route.params[0]) {
    if (typeof window.openSession === 'function') {
      window.openSession(route.params[0]);
    }
  } else if (route.view === 'luat') {
    handleLawRoute(route);
  } else if (route.view === 'muc-phat') {
    handlePenaltyRoute(route);
  } else if (route.view === 'tien-ich') {
    handleUtilitiesRoute(route);
  } else if (route.view === 'van-ban' && route.params[0]) {
    loadPdf(route.params[0]);
  }
}

/**
 * Đèn trạng thái ở chân thanh bên: kiểm tra kết nối máy chủ và số lượng dữ liệu
 */
async function checkStatus() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  if (!dot || !text) return;

  try {
    const h = await fetchJson('/api/health');
    dot.className = 'dot ok';
    const docsCount = h.documents_loaded || 6;
    text.textContent = `${docsCount} Văn bản · ${h.penalty_behaviours || 634} Lỗi phạt`;
    text.title = `Model: ${h.model} | Embedding: ${h.embedding_model}`;
  } catch {
    dot.className = 'dot bad';
    text.textContent = 'Mất kết nối máy chủ';
  }
}

/**
 * Ảnh biển báo / vạch kẻ thiếu tệp sẽ hiện chữ alt trần. Thay bằng ô chỗ trống
 * dựng sẵn để lưới giữ được nhịp thị giác.
 */
function installImageFallback() {
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    if (img.dataset.fallbackApplied) return;
    img.dataset.fallbackApplied = '1';
    img.src = '/static/img/sign-placeholder.svg';
  }, true);
}

function bootstrap() {
  // 1. Nút mở Command Palette
  const paletteBtn = document.getElementById('btn-open-palette');
  if (paletteBtn) {
    paletteBtn.addEventListener('click', openPalette);
  }
  initCommandPalette();

  // 2. Nút ẩn/hiện thanh bên Sidebar
  const sidebarToggle = document.getElementById('btn-toggle-sidebar');
  if (sidebarToggle) {
    // Template gắn cứng aria-expanded="true" (đúng cho desktop). Ở khổ ≤900px
    // sidebar mặc định đóng (CSS translateX(-100%)) nên phải sửa lại ngay khi
    // khởi động, tránh trợ năng báo sai trạng thái trước cú click đầu tiên.
    if (window.innerWidth <= 900) {
      sidebarToggle.setAttribute('aria-expanded', 'false');
    }

    sidebarToggle.addEventListener('click', () => {
      const isMobile = window.innerWidth <= 900;
      if (isMobile) {
        const isOpen = document.body.classList.toggle('sidebar-open');
        sidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      } else {
        const isHidden = document.body.classList.toggle('sidebar-hidden');
        sidebarToggle.setAttribute('aria-expanded', isHidden ? 'false' : 'true');
      }
    });
  }

  // 3. Khởi tạo Router và đăng ký 6 view
  initRouter({
    routes: {
      'chat': onRouteMatched,
      'luat': onRouteMatched,
      'muc-phat': onRouteMatched,
      'tien-ich': onRouteMatched,
      'van-ban': onRouteMatched,
      'he-thong': onRouteMatched
    },
    fallback: 'chat'
  });

  // 4. Ảnh hỏng lùi về ô chỗ trống
  installImageFallback();

  // 5. Kiểm tra trạng thái máy chủ
  checkStatus();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}

