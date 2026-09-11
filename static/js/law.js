/**
 * LexTraffic AI — Trình Khám Phá Đa Bộ Luật & Văn Bản Pháp Luật Giao Thông
 * 
 * Hỗ trợ chuyển đổi giữa 6 văn bản pháp luật:
 * 1. Luật Trật tự ATGTĐB 36/2024/QH15
 * 2. Luật Đường bộ 35/2024/QH15
 * 3. Nghị định 168/2024/NĐ-CP (Xử phạt VPHC)
 * 4. Thông tư 31/2019/TT-BGTVT (Tốc độ & cự ly)
 * 5. Thông tư 73/2024/TT-BCA (Tuần tra CSGT)
 * 6. QCVN 41:2019/BGTVT (Báo hiệu đường bộ)
 * 
 * Văn bản hiển thị phân cấp chuẩn Điều / Khoản / Điểm và tự động in đậm chế tài then chốt.
 */

import { fetchJson, el, escapeHtml, showToast } from './utils.js';
import { renderFormattedArticle } from './law_formatter.js';
import { getIcon } from './ui/icons.js';

const searchBox = document.getElementById('law-search');
const treeBox = document.getElementById('law-tree');
const reader = document.getElementById('law-reader');
const docTabsBox = document.getElementById('doc-tabs');
const bannerTitle = document.getElementById('doc-banner-title');
const bannerMeta = document.getElementById('doc-banner-meta');
const btnOpenPdf = document.getElementById('btn-open-pdf-current');

let currentDocId = '01_luat_36_2024_qh15';
let chapters = [];
let loaded = false;
let searchTimer = null;
let documentsList = [];

/** Cập nhật Banner thông tin văn bản đang chọn */
function updateDocumentBanner(docMeta) {
  if (!docMeta) return;
  if (bannerTitle) bannerTitle.textContent = docMeta.full_title || docMeta.short_title;
  if (bannerMeta) {
    bannerMeta.innerHTML = `
      <span>Số hiệu: <strong>${escapeHtml(docMeta.code)}</strong></span>
      <span>Cơ quan: <strong>${escapeHtml(docMeta.authority)}</strong></span>
      <span>Hiệu lực: <strong class="badge-effective">${escapeHtml(docMeta.effective_date)}</strong></span>
      <span>Quy mô: <strong>${docMeta.total_chapters} Chương · ${docMeta.total_articles} Điều</strong></span>
    `;
  }
}

/** Cây mục lục đầy đủ theo Chương, mỗi Chương là một <details> gập được */
function renderTree() {
  treeBox.innerHTML = '';
  if (!chapters || !chapters.length) {
    treeBox.innerHTML = '<div class="placeholder">Văn bản này không có mục lục chương hoặc đang nạp...</div>';
    return;
  }

  chapters.forEach((ch, idx) => {
    const box = el('details', 'tree-chapter');
    box.open = idx === 0; // Mở sẵn chương đầu tiên
    const roman = ch.chapter_roman ? `${escapeHtml(ch.chapter_roman)}: ` : '';
    const range = ch.article_range ? `<small>${escapeHtml(ch.article_range)}</small>` : '';
    box.innerHTML = `<summary>${roman}${escapeHtml(ch.chapter_title)} ${range}</summary>`;

    if (ch.articles && ch.articles.length > 0) {
      ch.articles.forEach(a => {
        const btn = el('button', 'tree-art');
        btn.type = 'button';
        btn.dataset.article = a.article_number;
        btn.textContent = `Điều ${a.article_number}. ${a.article_title}`;
        btn.addEventListener('click', () => openArticle(a.article_number));
        box.appendChild(btn);
      });
    } else {
      box.appendChild(el('div', 'tree-empty', 'Đang cập nhật danh mục Điều…'));
    }

    treeBox.appendChild(box);
  });
}

/** Hiển thị kết quả tìm kiếm thay thế cây mục lục */
function renderSearchResults(query, results) {
  treeBox.innerHTML = '';
  const head = el('div', 'sidebar-section-head');
  head.innerHTML = `<span>${results.length} kết quả trong văn bản cho "${escapeHtml(query)}"</span>`;
  treeBox.appendChild(head);

  if (!results.length) {
    treeBox.appendChild(el('div', 'placeholder', 'Không tìm thấy Điều luật nào khớp với từ khóa.'));
    return;
  }

  results.forEach(r => {
    const btn = el('button', 'tree-art');
    btn.type = 'button';
    btn.dataset.article = r.article_number;
    btn.textContent = r.article_header;
    btn.addEventListener('click', () => openArticle(r.article_number));
    treeBox.appendChild(btn);

    if (r.snippets && r.snippets.length) {
      const snip = el('div', 'hit-snippet');
      snip.textContent = r.snippets[0].slice(0, 160);
      treeBox.appendChild(snip);
    }
  });
}

/** Tải và hiển thị toàn văn một Điều luật với bộ định dạng phân cấp và in đậm */
async function openArticle(articleNumber) {
  // Highlight nút đang chọn trong cây
  treeBox.querySelectorAll('.tree-art').forEach(b => {
    b.classList.toggle('active', b.dataset.article === String(articleNumber));
  });

  reader.innerHTML = `
    <div class="placeholder">
      <div class="spinner"></div>
      <p>Đang tải và định dạng toàn văn Điều ${articleNumber}...</p>
    </div>
  `;

  try {
    const data = await fetchJson(`/api/documents/${currentDocId}/articles/${articleNumber}`);
    reader.innerHTML = '';
    
    // Sử dụng bộ định dạng cấu trúc pháp lý law_formatter.js
    const formattedNode = renderFormattedArticle(data);
    reader.appendChild(formattedNode);

    // Gắn sự kiện sao chép toàn văn Điều
    const btnCopyArt = formattedNode.querySelector('#btn-copy-full-art');
    if (btnCopyArt) {
      btnCopyArt.addEventListener('click', () => {
        const textToCopy = `${data.article_header}\n(${data.doc_name})\n\n${data.content}`;
        navigator.clipboard.writeText(textToCopy).then(() => {
          showToast(`Đã sao chép toàn văn Điều ${articleNumber}!`);
        });
      });
    }

    // Gắn sự kiện sao chép từng Khoản
    formattedNode.querySelectorAll('.btn-copy-clause').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const copyText = btn.dataset.copy || btn.parentElement.innerText;
        navigator.clipboard.writeText(copyText).then(() => {
          showToast('Đã sao chép nội dung Khoản!');
        });
      });
    });

    reader.scrollTop = 0;

    // Đồng bộ URL hash deep-link
    if (window.location.hash.startsWith('#/luat')) {
      const targetHash = `#/luat/${currentDocId}/dieu-${articleNumber}`;
      if (window.location.hash !== targetHash) {
        history.replaceState(null, '', targetHash);
      }
    }
  } catch (err) {
    reader.innerHTML = `
      <div class="placeholder">
        <div class="placeholder-icon">${getIcon('alert')}</div>
        <h3>Không thể tải toàn văn Điều ${articleNumber}</h3>
        <p>${escapeHtml(err.message)}</p>
      </div>
    `;
  }
}

/** Thực hiện tìm kiếm từ khóa */
async function runSearch(query) {
  const trimmed = query.trim();
  if (!trimmed) {
    renderTree();
    return;
  }
  try {
    const data = await fetchJson(`/api/search?doc_id=${currentDocId}&q=${encodeURIComponent(trimmed)}&limit=25`);
    renderSearchResults(trimmed, data.results || []);
  } catch (err) {
    treeBox.innerHTML = `<div class="placeholder">Lỗi tìm kiếm: ${escapeHtml(err.message)}</div>`;
  }
}

/** Chuyển đổi giữa 6 văn bản pháp luật */
export async function switchDocument(docId, targetArticle = null) {
  if (currentDocId === docId && chapters.length > 0) {
    if (targetArticle) openArticle(targetArticle);
    return;
  }
  currentDocId = docId;

  // Cập nhật trạng thái nút tab
  if (docTabsBox) {
    docTabsBox.querySelectorAll('.doc-tab').forEach(t => {
      const isTarget = t.dataset.doc === docId;
      t.classList.toggle('active', isTarget);
      t.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    });
  }

  // Cập nhật banner thông tin
  const meta = documentsList.find(d => d.id === docId);
  if (meta) updateDocumentBanner(meta);

  // Xóa ô tìm kiếm
  if (searchBox) searchBox.value = '';

  // Nạp cây mục lục của văn bản mới
  treeBox.innerHTML = `
    <div class="tree-loading">
      <div class="spinner"></div>
      <p>Đang tải mục lục văn bản...</p>
    </div>
  `;
  reader.innerHTML = `
    <div class="placeholder">
      <div class="placeholder-icon">${getIcon('book')}</div>
      <h3>Đã chuyển sang văn bản: ${escapeHtml(meta ? meta.short_title : docId)}</h3>
      <p>Chọn một Điều luật ở danh sách bên trái để đọc toàn văn với cấu trúc in đậm chuẩn mực.</p>
    </div>
  `;

  try {
    const data = await fetchJson(`/api/documents/${docId}/chapters`);
    chapters = data.chapters || [];
    renderTree();

    if (targetArticle) {
      openArticle(targetArticle);
    } else if (chapters.length > 0 && chapters[0].articles && chapters[0].articles.length > 0) {
      openArticle(chapters[0].articles[0].article_number);
    }
  } catch (err) {
    treeBox.innerHTML = `<div class="placeholder">Lỗi nạp mục lục: ${escapeHtml(err.message)}</div>`;
  }
}

/** Khởi tạo khu vực Tra cứu luật */
export async function initLawView() {
  if (loaded) return;
  loaded = true;

  // 1. Lắng nghe tìm kiếm từ khóa (debounce 250ms)
  if (searchBox) {
    searchBox.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runSearch(searchBox.value), 250);
    });
  }

  // 2. Lắng nghe sự kiện chuyển đổi văn bản trên các Tab
  if (docTabsBox) {
    docTabsBox.querySelectorAll('.doc-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const docId = tab.dataset.doc;
        if (docId) switchDocument(docId);
      });
    });
  }

  // 3. Nút mở bản PDF gốc
  if (btnOpenPdf) {
    btnOpenPdf.addEventListener('click', () => {
      window.open(`/api/pdf?doc=${currentDocId}`, '_blank');
    });
  }

  // 4. Tải danh sách 6 văn bản và khởi tạo văn bản đầu tiên
  try {
    const docsData = await fetchJson('/api/documents');
    documentsList = docsData.documents || [];
    const initialMeta = documentsList.find(d => d.id === currentDocId) || documentsList[0];
    if (initialMeta) updateDocumentBanner(initialMeta);

    const data = await fetchJson(`/api/documents/${currentDocId}/chapters`);
    chapters = data.chapters || [];
    renderTree();

    // Mở sẵn Điều 1 của văn bản đầu tiên
    if (chapters.length > 0 && chapters[0].articles && chapters[0].articles.length > 0) {
      openArticle(chapters[0].articles[0].article_number);
    }
  } catch (err) {
    loaded = false;
    treeBox.innerHTML = `<div class="placeholder">Không tải được danh mục văn bản: ${escapeHtml(err.message)}</div>`;
  }
}

/** Khôi phục trạng thái sâu từ URL route */
export async function handleLawRoute(route) {
  if (!loaded) await initLawView();
  const docId = route.params[0] || currentDocId;
  let articleNum = null;
  if (route.params[1] && route.params[1].startsWith('dieu-')) {
    articleNum = parseInt(route.params[1].replace('dieu-', ''), 10);
  }
  await switchDocument(docId, articleNum);
}
