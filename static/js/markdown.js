/**
 * markdown.js — Bộ dựng Markdown cho câu trả lời pháp lý của Agent.
 *
 * Vì sao tự viết thay vì dùng thư viện: dự án không có bước build, và câu trả lời
 * cần một khối đặc thù ("Căn cứ pháp lý trích dẫn") cùng cách chèn ảnh biển báo
 * riêng. Nhưng bộ dựng phải bám đúng thứ MÔ HÌNH thật sự sinh ra, không phải thứ
 * Markdown chuẩn giả định.
 *
 * Điểm mấu chốt: mô hình phân tách các khối bằng MỘT dòng trống, thậm chí không
 * có dòng trống nào — `---` dính ngay trên `### Căn cứ pháp lý`, tiêu đề dính
 * ngay trên danh sách, đoạn văn dính ngay trên bảng. Bộ dựng cũ cắt văn bản theo
 * dòng trống rồi đòi mỗi khối phải thuần một loại, nên mọi khối lẫn lộn đều rơi
 * xuống nhánh cuối và hiện ra ký hiệu Markdown thô. Ở đây quét theo TỪNG DÒNG và
 * để mỗi loại khối tự ăn đúng số dòng của nó.
 */

import { getIcon } from './ui/icons.js';

/** Mục danh sách: bắt cả `-`, `*`, `•`, `+`, `1.` và `1)` kèm mức thụt đầu dòng */
const LIST_ITEM = /^(\s*)([-*+•]|\d+[.)])\s+(.*)$/;

/** Đường kẻ ngang: `---`, `***`, `___` (cho phép có khoảng trắng xen giữa) */
const HR = /^([-*_])\1{2,}$/;

/** Tiêu đề ATX: `# ` tới `###### ` */
const HEADING = /^(#{1,6})\s+(.*)$/;

/** Tiêu đề in đậm đứng riêng một dòng: `**Tiêu đề:**` hoặc `**1. Tiêu đề**` */
const BOLD_HEADING = /^\*\*[^*]+\*\*:?$/;

/** Hàng bảng — mô hình luôn mở đầu bằng dấu `|` */
const TABLE_ROW = /^\|/;

/** Hàng phân cách của bảng: `|---|:--:|` */
const TABLE_SEPARATOR = /^\|[\s:|-]+\|?\s*$/;

/** Trích dẫn — văn bản đã escape nên `>` thành `&gt;` */
const QUOTE = /^(&gt;|>)/;

/** Mở/đóng khối mã */
const FENCE = /^(`{3,}|~{3,})/;

/** Tiêu đề khối căn cứ pháp lý, có hoặc không có emoji mô hình tự thêm */
const CITATION_HEADING = /^[^\p{L}\p{N}]*Căn cứ pháp lý/iu;

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Dấu nháy BẮT BUỘC phải escape, không phải cho đẹp.
    //
    // Kết quả của hàm này được nội suy thẳng vào THUỘC TÍNH HTML ở nhiều nơi, và nguy hiểm
    // nhất là trong chính `inline()` ngay dưới đây: `alt="${caption}"` và `src="${cleanSrc}"`
    // được dựng từ markdown do MÔ HÌNH sinh ra. Thiếu escape dấu nháy thì
    //     ![x" onerror="alert(1)](/a.png)
    // sinh ra <img src="/a.png" alt="x" onerror="alert(1)" ...> — một trình xử lý sự kiện chạy
    // thật. Nội dung mô hình sinh không phải dữ liệu tin cậy: nó bắt nguồn từ văn bản truy xuất
    // được và từ câu hỏi người dùng.
    //
    // Trong ngữ cảnh văn bản thường, trình duyệt hiển thị &quot; và &#39; đúng thành " và '
    // nên việc escape thêm không làm đổi giao diện. Toàn bộ nơi gọi hàm này đều dựng chuỗi
    // HTML (innerHTML), không nơi nào gán vào textContent — đã kiểm lại từng chỗ.
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function isHr(trimmed) {
  return HR.test(trimmed.replace(/\s+/g, ''));
}

/** Dòng này có mở đầu một khối mới không — dùng để biết đoạn văn kết thúc ở đâu */
function startsBlock(trimmed) {
  return HEADING.test(trimmed)
    || BOLD_HEADING.test(trimmed)
    || isHr(trimmed)
    || TABLE_ROW.test(trimmed)
    || QUOTE.test(trimmed)
    || FENCE.test(trimmed)
    || LIST_ITEM.test(trimmed);
}

/**
 * Định dạng trong dòng: ảnh, liên kết, đậm, nghiêng, mã.
 * Đầu vào đã được escape HTML từ trước.
 */
function inline(text) {
  return text
    .replace(/&lt;br\s*\/?&gt;/g, '<br>')
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_m, caption, src) => {
      const cleanSrc = src.startsWith('/') ? src : '/' + src;
      return `<span class="legal-img-card">`
        + `<img src="${cleanSrc}" alt="${caption}" class="traffic-sign-img" loading="lazy">`
        + `<span class="img-caption">${caption}</span></span>`;
    })
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s")]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="link">$1</a>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
    // Dấu sao còn sót lại sau khi đã ghép hết các cặp đều là do mô hình mở đậm
    // hoặc nghiêng mà không đóng — hay gặp khi cụm vắt qua ranh giới ô bảng, hoặc
    // khi câu trả lời bị cắt giữa chừng vì chạm giới hạn token. Trong văn bản pháp
    // lý tiếng Việt dấu sao không mang nghĩa gì, nên bỏ đi thay vì để lộ ký hiệu
    // thô. Giữ lại dấu sao nằm giữa hai chữ số để không phá biểu thức như `5*3`.
    .replace(/(?<!\d)\*(?!\d)/g, '');
}

/**
 * Dựng một danh sách, bao gồm cả danh sách con lồng theo mức thụt đầu dòng.
 * @returns {[string, number]} HTML và chỉ số dòng tiếp theo chưa xử lý
 */
function renderList(lines, start) {
  const first = lines[start].match(LIST_ITEM);
  const baseIndent = first[1].length;
  const ordered = /\d/.test(first[2]);

  const items = [];
  let i = start;

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trim();

    if (!trimmed) {
      // Mô hình hay chèn dòng trống giữa các mục. Nhìn tới dòng có nội dung kế
      // tiếp: còn là mục cùng cấp thì danh sách chưa kết thúc.
      let j = i + 1;
      while (j < lines.length && !lines[j].trim()) j++;
      const continues = j < lines.length
        && LIST_ITEM.test(lines[j])
        && lines[j].match(LIST_ITEM)[1].length >= baseIndent;
      if (!continues) break;
      i = j;
      continue;
    }

    const match = raw.match(LIST_ITEM);

    if (!match) {
      // Dòng nối tiếp của mục hiện tại (mô hình xuống dòng giữa chừng một ý)
      if (items.length && !startsBlock(trimmed)) {
        items[items.length - 1].parts.push(trimmed);
        i++;
        continue;
      }
      break;
    }

    const indent = match[1].length;
    if (indent < baseIndent) break;

    if (indent > baseIndent) {
      // Thụt sâu hơn: đây là danh sách con thuộc về mục ngay trước
      const [childHtml, next] = renderList(lines, i);
      if (items.length) items[items.length - 1].children.push(childHtml);
      i = next;
      continue;
    }

    items.push({ parts: [match[3]], children: [] });
    i++;
  }

  const tag = ordered ? 'ol' : 'ul';
  const html = `<${tag}>`
    + items.map(it => `<li>${inline(it.parts.join(' '))}${it.children.join('')}</li>`).join('')
    + `</${tag}>`;

  return [html, i];
}

/**
 * Dựng khối "Căn cứ pháp lý trích dẫn" thành thẻ nổi bật.
 *
 * Phần thân được đưa ngược lại bộ dựng khối chung, nhờ vậy danh sách lồng nhau
 * bên trong (mô hình hay viết "- Nghị định 168:" rồi thụt vào liệt kê từng Điểm)
 * giữ nguyên được cấu trúc thay vì bị dàn phẳng.
 *
 * @returns {[string, number]}
 */
function renderCitationCard(lines, start) {
  const body = [];
  let i = start + 1;

  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (HEADING.test(trimmed) || isHr(trimmed)) break;
    body.push(lines[i]);
    i++;
  }

  const html = `<div class="legal-citation-card">`
    + `<div class="legal-citation-badge">`
    + `<span class="legal-citation-icon">${getIcon('book')}</span>`
    + `<span>Căn cứ pháp lý trích dẫn</span>`
    + `</div>`
    + `<div class="legal-citation-body">${renderBlocks(body)}</div>`
    + `</div>`;

  return [html, i];
}

/**
 * Dựng bảng từ các dòng bắt đầu bằng `|` liên tiếp.
 * @returns {[string, number]}
 */
function renderTable(lines, start) {
  const rows = [];
  let i = start;

  while (i < lines.length && TABLE_ROW.test(lines[i].trim())) {
    rows.push(lines[i].trim());
    i++;
  }

  const cells = rows
    .filter(r => !TABLE_SEPARATOR.test(r))
    .map(r => r.replace(/^\|/, '').replace(/\|\s*$/, '').split('|').map(c => inline(c.trim())));

  // Một dòng `|` đơn độc không phải bảng: trả về đoạn văn thường
  if (cells.length < 2) {
    return [`<p>${inline(rows.join('<br>'))}</p>`, i];
  }

  const head = `<thead><tr>${cells[0].map(c => `<th>${c}</th>`).join('')}</tr></thead>`;
  const body = cells.slice(1)
    .map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`)
    .join('');

  return [`<div class="table-wrap"><table>${head}<tbody>${body}</tbody></table></div>`, i];
}

/**
 * Dựng một dãy dòng ĐÃ escape thành HTML. Tách riêng khỏi `renderMarkdown` để
 * thẻ căn cứ pháp lý dựng lại được phần thân của nó bằng đúng bộ luật này.
 * @param {string[]} lines
 * @returns {string}
 */
function renderBlocks(lines) {
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trim();

    if (!trimmed) { i++; continue; }

    // Khối mã: giữ nguyên văn, không áp định dạng trong dòng
    if (FENCE.test(trimmed)) {
      const marker = trimmed[0].repeat(3);
      const buffer = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(marker)) {
        buffer.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;   // bỏ qua dòng đóng khối
      out.push(`<pre><code>${buffer.join('\n')}</code></pre>`);
      continue;
    }

    if (isHr(trimmed)) {
      out.push('<hr class="legal-divider">');
      i++;
      continue;
    }

    const heading = trimmed.match(HEADING);
    if (heading) {
      if (CITATION_HEADING.test(heading[2])) {
        const [html, next] = renderCitationCard(lines, i);
        out.push(html);
        i = next;
        continue;
      }
      const level = Math.min(heading[1].length, 4);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      i++;
      continue;
    }

    // Mô hình đôi khi viết tiêu đề căn cứ thành đoạn văn thường, không có dấu #
    if (CITATION_HEADING.test(trimmed)) {
      const [html, next] = renderCitationCard(lines, i);
      out.push(html);
      i = next;
      continue;
    }

    if (BOLD_HEADING.test(trimmed)) {
      out.push(`<p class="legal-subheading">${inline(trimmed)}</p>`);
      i++;
      continue;
    }

    if (TABLE_ROW.test(trimmed)) {
      const [html, next] = renderTable(lines, i);
      out.push(html);
      i = next;
      continue;
    }

    if (QUOTE.test(trimmed)) {
      const buffer = [];
      while (i < lines.length && QUOTE.test(lines[i].trim())) {
        buffer.push(lines[i].trim().replace(/^(&gt;|>)\s?/, ''));
        i++;
      }
      out.push(`<blockquote class="legal-quote">${inline(buffer.join('<br>'))}</blockquote>`);
      continue;
    }

    if (LIST_ITEM.test(trimmed)) {
      const [html, next] = renderList(lines, i);
      out.push(html);
      i = next;
      continue;
    }

    // Đoạn văn: gom tới khi gặp dòng trống hoặc một khối khác mở ra
    const buffer = [];
    while (i < lines.length) {
      const lineTrimmed = lines[i].trim();
      if (!lineTrimmed) { i++; break; }
      if (startsBlock(lineTrimmed) || CITATION_HEADING.test(lineTrimmed)) break;
      buffer.push(lineTrimmed);
      i++;
    }
    if (buffer.length) out.push(`<p>${inline(buffer.join('<br>'))}</p>`);
  }

  return out.join('');
}

/**
 * Chuyển Markdown do Agent sinh ra thành HTML.
 * @param {string} md
 * @returns {string}
 */
export function renderMarkdown(md) {
  if (!md) return '';
  return renderBlocks(escapeHtml(String(md).replace(/\r\n/g, '\n')).split('\n'));
}
