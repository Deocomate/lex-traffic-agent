/**
 * router.js - Bộ định tuyến Hash Client-side (SPA Deep Linking)
 * Hỗ trợ deep-link cho mọi khu vực tra cứu, bảo đảm Back/Forward và khôi phục khi F5.
 */

let routesRegistry = {};
let fallbackRoute = 'chat';
let isInitialized = false;

/**
 * Phân tích chuỗi location.hash hiện tại thành đối tượng route
 * @returns {{ view: string, segments: string[], params: string[], query: Record<string, string>, raw: string }}
 */
export function parseHash() {
  const hash = window.location.hash || '';
  const cleanHash = hash.replace(/^#\/?/, '');
  const [pathPart, queryPart] = cleanHash.split('?');

  const segments = pathPart ? pathPart.split('/').filter(Boolean) : [];
  const view = segments[0] || fallbackRoute;
  const params = segments.slice(1);

  const query = {};
  if (queryPart) {
    const searchParams = new URLSearchParams(queryPart);
    for (const [k, v] of searchParams.entries()) {
      query[k] = v;
    }
  }

  return {
    view,
    segments,
    params,
    query,
    raw: hash
  };
}

/**
 * Lấy trạng thái route hiện tại
 */
export function getRoute() {
  return parseHash();
}

/**
 * Điều hướng tới một đường dẫn hash mới
 * @param {string} path - Đường dẫn hash (ví dụ '#/luat/01_luat_36_2024_qh15' hoặc 'luat')
 * @param {Object} [options]
 * @param {boolean} [options.replace=false] - Thay thế lịch sử thay vì đẩy thêm bước
 */
export function navigate(path, { replace = false } = {}) {
  let target = path.startsWith('#') ? path : `#/${path.replace(/^\//, '')}`;
  if (replace) {
    const currentUrl = new URL(window.location.href);
    currentUrl.hash = target;
    window.location.replace(currentUrl.href);
  } else {
    window.location.hash = target;
  }
}

/**
 * Xử lý khi hash thay đổi
 */
function handleHashChange() {
  const route = parseHash();
  const handler = routesRegistry[route.view] || routesRegistry[fallbackRoute];

  if (handler) {
    try {
      handler(route);
    } catch (err) {
      console.error(`[Router] Lỗi khi thực thi route ${route.view}:`, err);
    }
  }

  window.dispatchEvent(new CustomEvent('routechange', { detail: route }));
}

/**
 * Khởi tạo Router
 * @param {Object} config
 * @param {Record<string, Function>} config.routes - Bảng định tuyến { [viewName]: handler }
 * @param {string} [config.fallback='chat'] - Route mặc định khi hash rỗng
 */
export function initRouter(config = {}) {
  if (isInitialized) return;
  isInitialized = true;

  routesRegistry = config.routes || {};
  fallbackRoute = config.fallback || 'chat';

  window.addEventListener('hashchange', handleHashChange);

  // Kích hoạt ngay lần tải đầu tiên
  if (!window.location.hash || window.location.hash === '#' || window.location.hash === '#/') {
    navigate(`#/${fallbackRoute}`, { replace: true });
  } else {
    handleHashChange();
  }
}
