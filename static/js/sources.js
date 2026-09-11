/**
 * sources.js - Xử lý hiển thị các nguồn trích dẫn pháp lý đa văn bản
 * Hỗ trợ Luật 36, Luật 35, Nghị định 168, QCVN 41, Thông tư 31, Thông tư 73
 */

import { getIcon } from './ui/icons.js';
import { showToast } from './utils.js';

/**
 * Trả về nhãn viết tắt gọn gàng cho từng loại văn bản
 */
export function getDocShortLabel(src) {
  if (src.source_type === 'sign') return 'QCVN 41';
  if (src.source_type === 'decree') return 'NĐ 168';
  
  const docId = src.doc_id || '';
  if (docId.includes('36')) return 'Luật 36';
  if (docId.includes('35')) return 'Luật 35';
  if (docId.includes('168')) return 'NĐ 168';
  if (docId.includes('31')) return 'TT 31';
  if (docId.includes('73')) return 'TT 73';
  if (docId.includes('41')) return 'QCVN 41';

  return src.doc_short || src.doc_code || 'Văn bản';
}

/**
 * Render danh sách chip trích dẫn
 * @param {Array} sources - Danh sách nguồn từ backend
 * @param {HTMLElement} docEl - Phần tử panel mở rộng tài liệu
 * @returns {HTMLElement} Container chứa các chip
 */
export function renderSources(sources, docEl) {
  const container = document.createElement('div');
  container.className = 'chat-sources';

  if (!sources || !sources.length) {
    return container;
  }

  const titleRow = document.createElement('div');
  titleRow.className = 'chat-sources__header';
  titleRow.innerHTML = `
    <span class="chat-sources__icon">${getIcon('book', 'icon--xs')}</span>
    <span class="chat-sources__label">Căn cứ pháp lý trích dẫn (${sources.length})</span>
  `;
  container.appendChild(titleRow);

  const chipsWrap = document.createElement('div');
  chipsWrap.className = 'chat-sources__chips';

  sources.forEach((src, idx) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = `chip chip--interactive source-chip source-chip--${src.source_type || 'law'}`;
    chip.setAttribute('aria-expanded', 'false');

    const badgeLabel = getDocShortLabel(src);

    if (src.source_type === 'sign') {
      const code = src.sign_code || 'Biển';
      chip.innerHTML = `
        <span class="badge badge--neutral badge--xs">${badgeLabel}</span>
        <span class="source-chip__text">${escapeHtml(code)}</span>
      `;
      chip.title = `${code}: ${src.sign_name || 'Biển báo giao thông'}`;
      chip.addEventListener('click', () => toggleSourceDetail(docEl, src, chip));
    } else if (src.source_type === 'decree' || (src.citation && !src.article_number)) {
      const citation = src.citation || 'Nghị định 168';
      chip.innerHTML = `
        <span class="badge badge--rose badge--xs">${badgeLabel}</span>
        <span class="source-chip__text">${escapeHtml(citation)}</span>
      `;
      chip.title = `${citation} (${src.vehicle || 'Vi phạm'}): ${src.fine_text || ''}`;
      chip.addEventListener('click', () => toggleSourceDetail(docEl, src, chip));
    } else {
      // Law article
      const artNum = src.article_number || '';
      const isLuat35 = (src.doc_id || '').includes('35');
      const badgeVariant = isLuat35 ? 'badge--sky' : 'badge--primary';
      chip.innerHTML = `
        <span class="badge ${badgeVariant} badge--xs">${badgeLabel}</span>
        <span class="source-chip__text">Điều ${artNum}</span>
      `;
      chip.title = src.article_header || `${badgeLabel} - Điều ${artNum}`;
      chip.addEventListener('click', () => toggleSourceDetail(docEl, src, chip));
    }

    chipsWrap.appendChild(chip);
  });

  container.appendChild(chipsWrap);
  return container;
}

/**
 * Mở / đóng panel chi tiết nguồn trích dẫn
 */
export async function toggleSourceDetail(docEl, src, activeChip) {
  if (!docEl) return;

  const currentKey = `${src.source_type}_${src.doc_id || ''}_${src.article_number || src.sign_code || src.citation || ''}`;
  
  if (!docEl.hidden && docEl.dataset.activeKey === currentKey) {
    docEl.hidden = true;
    docEl.dataset.activeKey = '';
    if (activeChip) activeChip.setAttribute('aria-expanded', 'false');
    return;
  }

  // Đóng chip khác nếu có
  const parentSources = docEl.closest('.chat-message') || docEl.parentElement;
  if (parentSources) {
    parentSources.querySelectorAll('.source-chip[aria-expanded="true"]').forEach(c => {
      c.setAttribute('aria-expanded', 'false');
    });
  }

  docEl.hidden = false;
  docEl.dataset.activeKey = currentKey;
  if (activeChip) activeChip.setAttribute('aria-expanded', 'true');

  if (src.source_type === 'sign') {
    renderSignDetail(docEl, src);
  } else if (src.source_type === 'decree' || (src.citation && !src.article_number)) {
    renderDecreeDetail(docEl, src);
  } else {
    await renderLawArticleDetail(docEl, src);
  }

  // Cuộn nhẹ nếu bị khuất
  docEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderSignDetail(docEl, src) {
  const code = src.sign_code || '';
  const name = src.sign_name || 'Báo hiệu đường bộ';
  
  docEl.innerHTML = `
    <div class="source-panel card">
      <div class="source-panel__header">
        <div class="source-panel__meta">
          <span class="badge badge--neutral">QCVN 41:2019/BGTVT</span>
          <h4 class="source-panel__title">${escapeHtml(code ? `${code}: ${name}` : name)}</h4>
        </div>
        <button type="button" class="btn btn--ghost btn--icon btn-close-source" aria-label="Đóng bảng trích dẫn">
          ${getIcon('close', 'icon--sm')}
        </button>
      </div>
      <div class="source-panel__body source-panel__body--sign">
        ${src.image_url ? `
          <div class="source-panel__sign-media">
            <img src="${escapeHtml(src.image_url)}" alt="${escapeHtml(name)}" loading="lazy" class="source-panel__sign-img">
          </div>
        ` : ''}
        <div class="source-panel__sign-info">
          <p class="source-panel__doc-name">Quy chuẩn kỹ thuật quốc gia về báo hiệu đường bộ (QCVN 41:2019/BGTVT)</p>
          <p class="source-panel__sign-desc">Hiệu lực áp dụng toàn quốc. Vui lòng quan sát kỹ các biển báo phụ và vạch kẻ đi kèm.</p>
        </div>
      </div>
      <div class="source-panel__footer">
        <button type="button" class="btn btn--ghost btn--sm btn-copy-source">
          ${getIcon('copy', 'icon--xs')} Sao chép tên biển
        </button>
      </div>
    </div>
  `;

  bindPanelActions(docEl, `${code} - ${name} (QCVN 41:2019/BGTVT)`);
}

function renderDecreeDetail(docEl, src) {
  const citation = src.citation || 'Nghị định 168/2024/NĐ-CP';
  const vehicle = src.vehicle ? `Phương tiện: ${src.vehicle}` : 'Quy định xử phạt';

  docEl.innerHTML = `
    <div class="source-panel card">
      <div class="source-panel__header">
        <div class="source-panel__meta">
          <span class="badge badge--rose">Nghị định 168/2024/NĐ-CP</span>
          <h4 class="source-panel__title">${escapeHtml(citation)}</h4>
          <span class="badge badge--neutral badge--xs">${escapeHtml(vehicle)}</span>
        </div>
        <button type="button" class="btn btn--ghost btn--icon btn-close-source" aria-label="Đóng bảng trích dẫn">
          ${getIcon('close', 'icon--sm')}
        </button>
      </div>
      <div class="source-panel__body source-panel__body--decree">
        ${src.behaviour ? `
          <div class="source-panel__row">
            <span class="source-panel__label">Hành vi vi phạm:</span>
            <span class="source-panel__value">${escapeHtml(src.behaviour)}</span>
          </div>
        ` : ''}
        ${src.fine_text ? `
          <div class="source-panel__row source-panel__row--highlight">
            <span class="source-panel__label">Mức phạt tiền:</span>
            <span class="source-panel__value source-panel__value--fine">${escapeHtml(src.fine_text)}</span>
          </div>
        ` : ''}
        ${src.points ? `
          <div class="source-panel__row">
            <span class="source-panel__label">Trừ điểm GPLX:</span>
            <span class="source-panel__value source-panel__value--points">${escapeHtml(src.points)}</span>
          </div>
        ` : ''}
      </div>
      <div class="source-panel__footer">
        <button type="button" class="btn btn--ghost btn--sm btn-copy-source">
          ${getIcon('copy', 'icon--xs')} Sao chép chế tài
        </button>
      </div>
    </div>
  `;

  const copyContent = `${citation}\nPhương tiện: ${src.vehicle || ''}\nHành vi: ${src.behaviour || ''}\nPhạt tiền: ${src.fine_text || ''}\nTrừ điểm: ${src.points || ''}`;
  bindPanelActions(docEl, copyContent);
}

async function renderLawArticleDetail(docEl, src) {
  const docId = src.doc_id || '01_luat_36_2024_qh15';
  const artNum = src.article_number;
  const isLuat35 = docId.includes('35');
  const badgeClass = isLuat35 ? 'badge--sky' : 'badge--primary';
  const docTitle = src.doc_name || (isLuat35 ? 'Luật Đường bộ 2024' : 'Luật Trật tự, ATGT đường bộ 2024');

  docEl.innerHTML = `
    <div class="source-panel card">
      <div class="source-panel__header">
        <div class="source-panel__meta">
          <span class="badge ${badgeClass}">${escapeHtml(getDocShortLabel(src))}</span>
          <h4 class="source-panel__title">${escapeHtml(src.article_header || `Điều ${artNum}`)}</h4>
        </div>
        <button type="button" class="btn btn--ghost btn--icon btn-close-source" aria-label="Đóng bảng trích dẫn">
          ${getIcon('close', 'icon--sm')}
        </button>
      </div>
      <div class="source-panel__body">
        <div class="source-panel__loading">
          <span class="spinner spinner--sm"></span>
          <span>Đang tải toàn văn điều luật từ máy chủ…</span>
        </div>
      </div>
    </div>
  `;

  bindCloseOnly(docEl);

  try {
    let res = await fetch(`/api/documents/${encodeURIComponent(docId)}/articles/${artNum}`);
    if (!res.ok && !docId.includes('35')) {
      // Thử fallback sang endpoint cũ
      res = await fetch(`/api/article/${artNum}`);
    }

    if (!res.ok) {
      throw new Error(`Mã lỗi ${res.status}: Không thể tải nội dung`);
    }

    const data = await res.json();
    const content = data.content || data.page_content || 'Nội dung điều luật đang được cập nhật.';
    const header = data.article_header || src.article_header || `Điều ${artNum}`;
    const chapter = data.chapter_title || '';

    docEl.innerHTML = `
      <div class="source-panel card">
        <div class="source-panel__header">
          <div class="source-panel__meta">
            <span class="badge ${badgeClass}">${escapeHtml(data.doc_name || docTitle)}</span>
            <h4 class="source-panel__title">${escapeHtml(header)}</h4>
            ${chapter ? `<span class="source-panel__chapter">${escapeHtml(chapter)}</span>` : ''}
          </div>
          <button type="button" class="btn btn--ghost btn--icon btn-close-source" aria-label="Đóng bảng trích dẫn">
            ${getIcon('close', 'icon--sm')}
          </button>
        </div>
        <div class="source-panel__body">
          <pre class="source-panel__text">${escapeHtml(content)}</pre>
        </div>
        <div class="source-panel__footer">
          <button type="button" class="btn btn--ghost btn--sm btn-copy-source">
            ${getIcon('copy', 'icon--xs')} Sao chép toàn văn
          </button>
        </div>
      </div>
    `;

    bindPanelActions(docEl, `=== ${header} ===\n${chapter ? `${chapter}\n\n` : ''}${content}`);
  } catch (err) {
    const bodyEl = docEl.querySelector('.source-panel__body');
    if (bodyEl) {
      bodyEl.innerHTML = `
        <div class="state state--empty">
          <p class="state__title">Không thể tải điều luật</p>
          <p class="state__desc">${escapeHtml(err.message || 'Lỗi mạng hoặc không tìm thấy điều luật')}</p>
        </div>
      `;
    }
  }
}

function bindCloseOnly(docEl) {
  const closeBtn = docEl.querySelector('.btn-close-source');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      docEl.hidden = true;
      docEl.dataset.activeKey = '';
    });
  }
}

function bindPanelActions(docEl, textToCopy) {
  bindCloseOnly(docEl);

  const copyBtn = docEl.querySelector('.btn-copy-source');
  if (copyBtn && textToCopy) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(textToCopy);
        showToast('Đã sao chép nội dung vào bộ nhớ tạm', 'success');
      } catch {
        showToast('Không thể truy cập clipboard', 'warning');
      }
    });
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
