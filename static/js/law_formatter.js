/**
 * LexTraffic AI — Legal Text Formatter & Highlighter Engine
 * 
 * Chịu trách nhiệm:
 * 1. Phân tích cấu trúc văn bản pháp luật: Điều -> Khoản -> Điểm.
 * 2. Tự động in đậm và gán badge màu nổi bật (Highlighting) cho các thành phần chế tài:
 *    - Mức phạt tiền (VNĐ)
 *    - Số điểm giấy phép lái xe bị trừ
 *    - Tước quyền sử dụng GPLX
 *    - Tịch thu tang vật / phương tiện
 *    - Biện pháp khắc phục hậu quả
 *    - Các từ khóa nghĩa vụ / nghiêm cấm
 */

import { escapeHtml } from './utils.js';
import { getIcon } from './ui/icons.js';

/**
 * Tô sáng cú pháp và in đậm các thành tố pháp lý trọng yếu
 */
export function highlightLegalText(rawText) {
  if (!rawText) return '';
  let text = escapeHtml(rawText);

  // 1. In đậm Mức Phạt Tiền (VD: phạt tiền từ 400.000 đồng đến 600.000 đồng)
  text = text.replace(
    /(phạt tiền từ\s+[\d\.]+\s*(?:triệu|nghìn|tỷ)?\s*đồng\s+đến\s+[\d\.]+\s*(?:triệu|nghìn|tỷ)?\s*đồng|phạt tiền từ\s+[\d\.]+\s*đồng\s+đến\s+[\d\.]+\s*đồng|phạt tiền từ\s+[\d\.]+\s*đ\s+đến\s+[\d\.]+\s*đ|phạt cảnh cáo)/gi,
    '<strong class="badge badge--fine">$1</strong>'
  );

  // 2. In đậm Trừ Điểm Bằng Lái (VD: bị trừ 2 điểm giấy phép lái xe)
  text = text.replace(
    /(bị trừ\s+\d+\s+điểm(?:\s+giấy phép lái xe)?|trừ\s+\d+\s+điểm(?:\s+giấy phép lái xe)?)/gi,
    '<strong class="badge badge--severe">$1</strong>'
  );

  // 3. In đậm Tước Quyền Sử Dụng GPLX (VD: tước quyền sử dụng giấy phép lái xe từ 01 tháng đến 03 tháng)
  text = text.replace(
    /(tước quyền sử dụng giấy phép lái xe\s+từ\s+\d+\s+tháng\s+đến\s+\d+\s+tháng|tước quyền sử dụng giấy phép lái xe\s+đến\s+\d+\s+tháng|tước quyền sử dụng giấy phép lái xe[^\.;,\n]+)/gi,
    '<strong class="badge badge--severe">$1</strong>'
  );

  // 4. In đậm Tịch Thu Phương Tiện / Tang Vật
  text = text.replace(
    /(tịch thu phương tiện[^\.;,\n]*|tịch thu tang vật[^\.;,\n]*)/gi,
    '<strong class="badge badge--severe">$1</strong>'
  );

  // 5. In đậm Biện Pháp Khắc Phục Hậu Quả
  text = text.replace(
    /(buộc khôi phục lại tình trạng ban đầu[^\.;,\n]*|buộc hạ tải[^\.;,\n]*|buộc nộp lại[^\.;,\n]*|buộc tháo dỡ[^\.;,\n]*)/gi,
    '<strong class="badge badge--neutral">$1</strong>'
  );

  // 6. In đậm Hành Vi Nghiêm Cấm
  text = text.replace(
    /(nghiêm cấm[^\.;,\n]*|không được phép[^\.;,\n]*|bắt buộc phải[^\.;,\n]*)/gi,
    '<strong class="badge badge--severe">$1</strong>'
  );

  return text;
}

/**
 * Phân tích toàn văn bài viết thành các phân đoạn có cấu trúc:
 * Intro, Khoản (Clauses), Điểm (Points)
 */
export function parseArticleContent(rawContent) {
  if (!rawContent) return { intro: '', clauses: [], cleanText: '' };

  // Lớp nhúng ngữ nghĩa gắn tiền tố [TÀI LIỆU: …][CHƯƠNG: …][ĐIỀU: …] vào đầu
  // nội dung. Bóc chúng đi dù nằm trên dòng riêng hay dính liền một dòng.
  const stripped = rawContent.replace(
    /^\s*(?:(?:===[^\n]*===|\[(?:TÀI LIỆU|CHƯƠNG|ĐIỀU)[^\]]*\]|(?:Văn bản|Chương):[^\n]*)\s*)+/i,
    ''
  );

  const lines = stripped.split('\n');
  const cleanLines = lines;

  let intro = '';
  let clauses = [];
  let currentClause = null;
  let currentPoint = null;

  // Regex phát hiện bắt đầu Khoản: "1. ", "2. ", "Khoản 1. ", "Khoản 2. "
  const clauseRegex = /^(?:Khoản\s+)?(\d+)[\.\s]+(.*)/i;
  // Regex phát hiện bắt đầu Điểm: "a) ", "b) ", "c) ", "a. ", "đ) "
  const pointRegex = /^([a-zđĐ])[\)\.](.*)/i;

  for (let line of cleanLines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const clauseMatch = trimmed.match(clauseRegex);
    const pointMatch = trimmed.match(pointRegex);

    if (clauseMatch && !pointMatch) {
      // Bắt đầu một Khoản mới
      currentClause = {
        number: clauseMatch[1],
        leadText: clauseMatch[2].trim(),
        text: clauseMatch[2].trim(),
        points: []
      };
      clauses.push(currentClause);
      currentPoint = null;
    } else if (pointMatch) {
      // Bắt đầu một Điểm mới
      currentPoint = {
        letter: pointMatch[1].toLowerCase(),
        text: pointMatch[2].trim()
      };
      if (currentClause) {
        currentClause.points.push(currentPoint);
      } else {
        // Trường hợp bài viết không có khoản mà có trực tiếp điểm
        if (!clauses.length) {
          currentClause = { number: '1', leadText: '', text: '', points: [] };
          clauses.push(currentClause);
        }
        clauses[clauses.length - 1].points.push(currentPoint);
      }
    } else {
      // Dòng văn bản kéo dài
      if (currentPoint) {
        currentPoint.text += ' ' + trimmed;
      } else if (currentClause) {
        currentClause.text += ' ' + trimmed;
      } else {
        intro += (intro ? ' ' : '') + trimmed;
      }
    }
  }

  return { intro, clauses, cleanText: cleanLines.join('\n').trim() };
}

/**
 * Dựng cây HTML hoàn chỉnh cho một Điều luật
 */
export function renderFormattedArticle(artData) {
  const { doc_name, doc_code, article_number, article_header, chapter_title, content, structured_clauses } = artData;

  const container = document.createElement('div');
  container.className = 'doc-body-formatted';

  // 1. Header Card
  const headerCard = document.createElement('div');
  headerCard.className = 'doc-header-card';
  headerCard.innerHTML = `
    <div class="doc-header-top">
      <span class="art-number-pill">ĐIỀU ${article_number}</span>
      <div class="art-actions">
        <button class="btn btn--ghost btn--sm" id="btn-copy-full-art" type="button" title="Sao chép toàn văn Điều luật">
          ${getIcon('copy', 'icon--xs')} Sao chép
        </button>
      </div>
    </div>
    <h2>${escapeHtml(article_header || `Điều ${article_number}`)}</h2>
    <div class="doc-breadcrumb">
      <span>${escapeHtml(doc_name || doc_code || 'Văn bản luật')}</span>
      <span class="crumb-sep">›</span>
      <span>${escapeHtml(chapter_title || 'Chương')}</span>
    </div>
  `;
  container.appendChild(headerCard);

  // 2. Nội dung chi tiết
  // Nếu có sẵn structured_clauses (như ở Nghị định 168)
  if (structured_clauses && structured_clauses.length > 0) {
    const clausesContainer = document.createElement('div');
    clausesContainer.className = 'law-clauses-container';

    structured_clauses.forEach(cl => {
      const clauseEl = document.createElement('div');
      clauseEl.className = 'law-clause';
      clauseEl.id = `clause-${cl.clause_number}`;

      const clTextHtml = highlightLegalText(cl.text || '');

      let pointsHtml = '';
      if (cl.points && cl.points.length > 0) {
        pointsHtml = '<div class="law-points-list">' + cl.points.map(pt => `
          <div class="law-point">
            <span class="point-badge">${escapeHtml(pt.point_letter)})</span>
            <div class="point-body">${highlightLegalText(pt.text)}</div>
          </div>
        `).join('') + '</div>';
      }

      clauseEl.innerHTML = `
        <div class="clause-head">
          <div class="clause-title-wrap">
            <span class="clause-badge">Khoản ${cl.clause_number}</span>
            <div class="clause-lead-text">${clTextHtml}</div>
          </div>
          <button class="btn-copy-clause hit-area" data-copy="Khoản ${cl.clause_number}. ${escapeHtml(cl.text || '')}" title="Sao chép khoản này" aria-label="Sao chép khoản này" type="button">${getIcon('copy', 'icon--xs')}</button>
        </div>
        ${pointsHtml ? `<div class="clause-content-block">${pointsHtml}</div>` : ''}
      `;
      clausesContainer.appendChild(clauseEl);
    });

    container.appendChild(clausesContainer);
  } else {
    // Parser động từ text content
    const parsed = parseArticleContent(content);

    if (parsed.intro) {
      const introEl = document.createElement('div');
      introEl.className = 'law-intro';
      introEl.innerHTML = highlightLegalText(parsed.intro);
      container.appendChild(introEl);
    }

    if (parsed.clauses && parsed.clauses.length > 0) {
      const clausesContainer = document.createElement('div');
      clausesContainer.className = 'law-clauses-container';

      parsed.clauses.forEach(cl => {
        const clauseEl = document.createElement('div');
        clauseEl.className = 'law-clause';
        clauseEl.id = `clause-${cl.number}`;

        const clLeadHtml = highlightLegalText(cl.leadText || cl.text || '');

        let pointsHtml = '';
        if (cl.points && cl.points.length > 0) {
          pointsHtml = '<div class="law-points-list">' + cl.points.map(pt => `
            <div class="law-point">
              <span class="point-badge">${escapeHtml(pt.letter)})</span>
              <div class="point-body">${highlightLegalText(pt.text)}</div>
            </div>
          `).join('') + '</div>';
        }

        clauseEl.innerHTML = `
          <div class="clause-head">
            <div class="clause-title-wrap">
              <span class="clause-badge">Khoản ${cl.number}</span>
              <div class="clause-lead-text">${clLeadHtml}</div>
            </div>
            <button class="btn-copy-clause hit-area" data-copy="Khoản ${cl.number}. ${escapeHtml(cl.leadText || cl.text || '')}" title="Sao chép khoản này" aria-label="Sao chép khoản này" type="button">${getIcon('copy', 'icon--xs')}</button>
          </div>
          ${pointsHtml ? `<div class="clause-content-block">${pointsHtml}</div>` : ''}
        `;
        clausesContainer.appendChild(clauseEl);
      });

      container.appendChild(clausesContainer);
    } else if (!parsed.intro && parsed.cleanText) {
      // Điều luật không phân Khoản và cũng không có đoạn mở đầu nào được nhận
      // diện: dựng lại từ phần văn bản đã bóc tiêu đề, không dùng chuỗi thô —
      // chuỗi thô còn mang tiền tố [TÀI LIỆU]/[CHƯƠNG]/[ĐIỀU] của lớp nhúng.
      const fallbackBox = document.createElement('div');
      fallbackBox.className = 'law-intro';
      fallbackBox.innerHTML = highlightLegalText(parsed.cleanText);
      container.appendChild(fallbackBox);
    }
  }

  return container;
}
