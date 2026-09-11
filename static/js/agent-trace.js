/**
 * agent-trace.js — Đường ray suy luận của Agent.
 *
 * Mỗi bước Agent thực hiện là một nút trên một đường ray dọc: công cụ nào được
 * gọi, tra cứu chính xác tham số gì, trả về bao nhiêu kết quả, hết bao lâu, và
 * đang ở trạng thái nào. Đồng hồ chạy theo thời gian thực trong lúc Agent làm việc.
 *
 * Sự kiện SSE được tiêu thụ: start, turn_start, tool_call, tool_result,
 * model_fallback, synthesizing, verifying, verified, warning, token, done, error.
 */

import { getIcon } from './ui/icons.js';

/** Ánh xạ 7 công cụ pháp lý sang icon, nhãn ngắn tiếng Việt và căn cứ văn bản */
const TOOL_CONFIG = {
  penalty_lookup: {
    icon: 'receipt',
    label: 'Tra mức phạt',
    source: 'NĐ 168/2024'
  },
  traffic_sign_lookup: {
    icon: 'traffic-cone',
    label: 'Tra biển báo & vạch kẻ',
    source: 'QCVN 41:2019'
  },
  speed_limit_lookup: {
    icon: 'gauge',
    label: 'Tra tốc độ & cự ly',
    source: 'TT 31/2019'
  },
  keyword_search: {
    icon: 'search',
    label: 'Tìm theo từ khoá',
    source: 'Toàn văn điều luật'
  },
  semantic_search: {
    icon: 'sparkle',
    label: 'Tìm theo ngữ nghĩa',
    source: 'Chỉ mục vector 6 văn bản'
  },
  get_article: {
    icon: 'file-text',
    label: 'Đọc toàn văn điều luật',
    source: 'Văn bản gốc'
  },
  list_chapters: {
    icon: 'list',
    label: 'Duyệt mục lục',
    source: 'Cây chương và điều'
  }
};

/** Tên tham số tra cứu dịch sang tiếng Việt để hiện trong hàng đối số */
const ARG_LABELS = {
  query: 'từ khoá',
  keyword: 'từ khoá',
  behaviour: 'hành vi',
  vehicle: 'phương tiện',
  vehicle_type: 'phương tiện',
  article_number: 'điều',
  doc_id: 'văn bản',
  sign_code: 'mã biển',
  sign_name: 'tên biển',
  road_type: 'loại đường',
  area: 'khu vực',
  top_k: 'số kết quả',
  chapter: 'chương'
};

const NOTICE_VARIANTS = {
  fallback: { icon: 'alert', tone: 'warn' },
  verifying: { icon: 'search', tone: 'info' },
  verified: { icon: 'check', tone: 'ok' },
  warning: { icon: 'alert', tone: 'warn' },
  error: { icon: 'alert', tone: 'bad' }
};

/** Bỏ emoji dẫn đầu mà backend gắn vào thông điệp SSE — giao diện tự vẽ icon */
function stripLeadingGlyph(text) {
  if (!text) return '';
  return String(text).replace(/^[^\p{L}\p{N}(]+/u, '').trim();
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/** Rút số lượng kết quả ra khỏi câu tóm tắt để hiện thành một con số đứng riêng */
function extractResultCount(summary) {
  if (!summary) return null;
  const match = String(summary).match(/(\d+)\s*(?:kết quả|điều|hành vi|biển|vạch|mục|bản ghi)/i);
  return match ? match[1] : null;
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export class AgentTrace {
  /** @param {HTMLElement} containerEl Phần tử chứa đường ray trong tin nhắn */
  constructor(containerEl) {
    this.container = containerEl;
    this.steps = [];
    this.startTime = Date.now();
    this.endTime = null;
    this.isDone = false;
    this.activeStep = null;
    this.currentTurn = 0;
    this.tickHandle = null;

    // Khối bản nháp: văn bản mô hình phát ra trước khi biết nó có gọi công cụ nữa hay không
    this.draftEl = null;
    this.draftTextEl = null;
    this.draftText = '';

    this._buildDom();
    this._startTicking();
  }

  // -------------------------------------------------------------------------
  // Dựng khung
  // -------------------------------------------------------------------------

  _buildDom() {
    this.container.className = 'trace';

    this.header = document.createElement('button');
    this.header.type = 'button';
    this.header.className = 'trace__header';
    this.header.setAttribute('aria-expanded', 'true');
    this.header.innerHTML = `
      <span class="trace__status" data-state="running">
        <span class="spinner spinner--sm"></span>
      </span>
      <span class="trace__headline">Đang phân tích câu hỏi</span>
      <span class="trace__meta">
        <span class="trace__verify" data-state="" hidden>
          <span class="trace__verify-icon" aria-hidden="true"></span>
          <span class="trace__verify-label"></span>
        </span>
        <span class="trace__count" hidden></span>
        <span class="trace__timer">0.0s</span>
      </span>
      <span class="trace__chevron" aria-hidden="true">${getIcon('chevron-down', 'icon--xs')}</span>
    `;

    this.rail = document.createElement('div');
    this.rail.className = 'trace__rail';
    this.rail.setAttribute('role', 'region');
    this.rail.setAttribute('aria-label', 'Tiến trình tra cứu của Agent');

    this.container.appendChild(this.header);
    this.container.appendChild(this.rail);

    this.headlineEl = this.header.querySelector('.trace__headline');
    this.statusEl = this.header.querySelector('.trace__status');
    this.timerEl = this.header.querySelector('.trace__timer');
    this.countEl = this.header.querySelector('.trace__count');
    this.verifyEl = this.header.querySelector('.trace__verify');
    this.verifyIconEl = this.header.querySelector('.trace__verify-icon');
    this.verifyLabelEl = this.header.querySelector('.trace__verify-label');

    this.header.addEventListener('click', () => this._toggle());
  }

  _toggle() {
    const expanded = this.header.getAttribute('aria-expanded') === 'true';
    this.header.setAttribute('aria-expanded', String(!expanded));
    this.rail.hidden = expanded;
  }

  // -------------------------------------------------------------------------
  // Đồng hồ chạy thật trong lúc Agent làm việc
  // -------------------------------------------------------------------------

  _startTicking() {
    this.tickHandle = setInterval(() => {
      if (this.isDone) return this._stopTicking();
      const elapsed = Date.now() - this.startTime;
      this.timerEl.textContent = `${(elapsed / 1000).toFixed(1)}s`;
      if (this.activeStep) {
        const stepElapsed = Date.now() - this.activeStep.startedAt;
        this.activeStep.durationEl.textContent = formatDuration(stepElapsed);
      }
    }, 100);
  }

  _stopTicking() {
    if (this.tickHandle) {
      clearInterval(this.tickHandle);
      this.tickHandle = null;
    }
  }

  // -------------------------------------------------------------------------
  // Tiêu thụ sự kiện SSE
  // -------------------------------------------------------------------------

  handleEvent(evt) {
    const { event, message, action, args, summary, turn } = evt;

    switch (event) {
      case 'start':
        this._setHeadline('Đang phân tích câu hỏi và nhận diện mục tiêu pháp lý');
        break;

      case 'turn_start':
        this._addTurnMarker(turn || this.currentTurn + 1);
        break;

      case 'tool_call':
        this._openStep(action, args, stripLeadingGlyph(message));
        break;

      case 'tool_result':
        this._closeStep(summary || stripLeadingGlyph(message));
        break;

      case 'model_fallback':
        this._addNotice('fallback', stripLeadingGlyph(message) || 'Chuyển sang mô hình dự phòng do máy chủ bận');
        break;

      case 'synthesizing':
        this._setHeadline('Đã tra cứu xong, đang tổng hợp lời giải đáp');
        break;

      case 'verifying':
        this._addNotice('verifying', stripLeadingGlyph(message) || 'Đang đối chiếu câu trả lời với dữ liệu tra cứu');
        break;

      case 'verified': {
        const verifiedMsg = stripLeadingGlyph(message) || 'Đã loại bỏ chi tiết không có căn cứ';
        this._addNotice('verified', verifiedMsg);
        // Lớp kiểm chứng tất định giờ chạy trên MỌI câu trả lời sạch, không chỉ khi
        // phải sửa lại. Đường ray tự thu gọn khi xong nên riêng dòng thông báo trong
        // ray sẽ bị giấu đi — tín hiệu tin cậy quan trọng nhất của sản phẩm phải còn
        // thấy được ở hàng đầu, kể cả khi đã thu gọn.
        this._setVerifyBadge('ok', 'Đã xác minh', verifiedMsg);
        break;
      }

      case 'warning': {
        const warnMsg = stripLeadingGlyph(message);
        this._addNotice('warning', warnMsg);
        this._setVerifyBadge('warn', 'Đã huỷ câu trả lời', warnMsg);
        break;
      }

      case 'token':
        if (this.isDone) break;
        if (evt.phase === 'answer') {
          if (this.headlineEl.dataset.phase !== 'writing') {
            this.headlineEl.dataset.phase = 'writing';
            this._setHeadline('Đang soạn câu trả lời từ dữ liệu đã tra cứu');
          }
        } else if (this.headlineEl.dataset.phase !== 'drafting') {
          this.headlineEl.dataset.phase = 'drafting';
          this._setHeadline('Đang cân nhắc hướng trả lời');
        }
        break;

      case 'done':
        this.finalize(true);
        break;

      case 'error':
        this.finalize(false, stripLeadingGlyph(message));
        break;
    }
  }

  _setHeadline(text) {
    this.headlineEl.textContent = text;
  }

  // -------------------------------------------------------------------------
  // Các nút trên đường ray
  // -------------------------------------------------------------------------

  _addTurnMarker(turnNumber) {
    if (turnNumber === this.currentTurn) return;
    this.currentTurn = turnNumber;

    const marker = document.createElement('div');
    marker.className = 'trace__turn';
    marker.innerHTML = `<span class="trace__turn-label">Lượt suy luận ${turnNumber}</span>`;
    this.rail.appendChild(marker);
  }

  /** Dựng hàng đối số: hiện đúng thứ Agent đang tra, không phải mô tả chung chung */
  _renderArgs(args) {
    if (!args || typeof args !== 'object') return '';
    const pairs = Object.entries(args)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => {
        const label = ARG_LABELS[k] || k;
        const value = Array.isArray(v) ? v.join(', ') : String(v);
        const clipped = value.length > 80 ? `${value.slice(0, 80)}…` : value;
        return `<span class="trace__arg">
          <span class="trace__arg-key">${escapeHtml(label)}</span>
          <span class="trace__arg-val">${escapeHtml(clipped)}</span>
        </span>`;
      });

    if (!pairs.length) return '';
    return `<div class="trace__args">${pairs.join('')}</div>`;
  }

  _openStep(toolName, args, description) {
    const cfg = TOOL_CONFIG[toolName] || {
      icon: 'search',
      label: 'Tra cứu dữ liệu',
      source: ''
    };

    const stepEl = document.createElement('div');
    stepEl.className = 'trace__step trace__step--running';
    stepEl.dataset.tool = toolName || '';
    stepEl.innerHTML = `
      <span class="trace__node" aria-hidden="true"><span class="spinner spinner--sm"></span></span>
      <div class="trace__body">
        <div class="trace__line">
          <span class="trace__tool-icon" aria-hidden="true">${getIcon(cfg.icon, 'icon--xs')}</span>
          <span class="trace__tool">${escapeHtml(cfg.label)}</span>
          ${cfg.source ? `<span class="trace__source">${escapeHtml(cfg.source)}</span>` : ''}
          <span class="trace__duration">0ms</span>
        </div>
        ${this._renderArgs(args)}
        <div class="trace__result" hidden></div>
      </div>
    `;

    this.rail.appendChild(stepEl);

    const step = {
      tool: toolName,
      el: stepEl,
      startedAt: Date.now(),
      durationEl: stepEl.querySelector('.trace__duration'),
      resultEl: stepEl.querySelector('.trace__result'),
      nodeEl: stepEl.querySelector('.trace__node')
    };

    this.steps.push(step);
    this.activeStep = step;

    this._setHeadline(`${cfg.label}${description ? ` · ${description}` : ''}`);
    this._updateCount();
  }

  _closeStep(summary) {
    const step = this.activeStep;
    if (!step) return;

    const elapsed = Date.now() - step.startedAt;
    step.el.classList.remove('trace__step--running');
    step.el.classList.add('trace__step--done');
    step.durationEl.textContent = formatDuration(elapsed);
    step.nodeEl.innerHTML = getIcon('check', 'icon--xs');

    if (summary) {
      const count = extractResultCount(summary);
      step.resultEl.hidden = false;
      step.resultEl.innerHTML = count
        ? `<span class="trace__result-count">${escapeHtml(count)}</span><span class="trace__result-text">${escapeHtml(summary)}</span>`
        : `<span class="trace__result-text">${escapeHtml(summary)}</span>`;
    }

    this.activeStep = null;
  }

  // -------------------------------------------------------------------------
  // Khối suy nghĩ: nơi văn bản chưa được chốt chảy vào
  // -------------------------------------------------------------------------

  /** Tạo (một lần) khối hiển thị bản nháp đang chảy ở cuối đường ray */
  _ensureDraftBlock() {
    if (this.draftEl) return this.draftEl;

    const block = document.createElement('div');
    block.className = 'trace__draft';
    block.innerHTML = `
      <span class="trace__node trace__node--draft" aria-hidden="true"><span class="spinner spinner--sm"></span></span>
      <div class="trace__draft-body">
        <span class="trace__draft-label">Đang cân nhắc</span>
        <p class="trace__draft-text"></p>
      </div>
    `;
    this.rail.appendChild(block);

    this.draftEl = block;
    this.draftTextEl = block.querySelector('.trace__draft-text');
    return block;
  }

  /**
   * Nối thêm một đoạn văn bản chưa được chốt.
   * Hiển thị dưới dạng văn bản thuần, không dựng Markdown — nó là suy nghĩ dở dang,
   * dựng thành tiêu đề và bảng sẽ khiến nó trông như một câu trả lời hoàn chỉnh.
   */
  appendDraft(chunk) {
    if (this.isDone || !chunk) return;
    this._ensureDraftBlock();
    this.draftText += chunk;
    this.draftTextEl.textContent = this.draftText;
    this.draftTextEl.scrollTop = this.draftTextEl.scrollHeight;
  }

  getDraft() {
    return this.draftText;
  }

  /** Bản nháp chỉ là lời dẫn trước khi gọi công cụ: giữ lại như một dấu vết suy nghĩ */
  discardDraft() {
    if (!this.draftEl) return;

    this.draftEl.classList.add('trace__draft--superseded');
    const label = this.draftEl.querySelector('.trace__draft-label');
    if (label) label.textContent = 'Đã cân nhắc';
    const node = this.draftEl.querySelector('.trace__node');
    if (node) node.innerHTML = getIcon('check', 'icon--xs');

    // Ngắt tham chiếu để lượt sau tạo khối mới thay vì nối tiếp vào khối cũ
    this.draftEl = null;
    this.draftTextEl = null;
    this.draftText = '';
  }

  /** Bản nháp đã được chốt thành câu trả lời: gỡ khỏi ray để không hiện hai lần */
  commitDraft() {
    if (this.draftEl) this.draftEl.remove();
    this.draftEl = null;
    this.draftTextEl = null;
    this.draftText = '';
    this._setHeadline('Đã soạn xong câu trả lời');
  }

  /**
   * Huy hiệu kiểm chứng đứng cố định ở hàng đầu — khác với `_addNotice`, huy hiệu này
   * KHÔNG bị ẩn khi đường ray tự thu gọn lúc xong, vì đây là tín hiệu tin cậy phải
   * đọc được ngay cả khi người dùng không mở lại chi tiết từng bước.
   * @param {'ok'|'warn'} state
   */
  _setVerifyBadge(state, label, fullMessage) {
    this.verifyEl.hidden = false;
    this.verifyEl.dataset.state = state;
    this.verifyEl.title = fullMessage || '';
    this.verifyIconEl.innerHTML = getIcon(state === 'ok' ? 'check' : 'alert', 'icon--xs');
    this.verifyLabelEl.textContent = label;
  }

  _addNotice(variant, message) {
    if (!message) return;
    const cfg = NOTICE_VARIANTS[variant] || NOTICE_VARIANTS.warning;

    const noticeEl = document.createElement('div');
    noticeEl.className = `trace__notice trace__notice--${cfg.tone}`;
    noticeEl.innerHTML = `
      <span class="trace__node trace__node--notice" aria-hidden="true">${getIcon(cfg.icon, 'icon--xs')}</span>
      <span class="trace__notice-text">${escapeHtml(message)}</span>
    `;
    this.rail.appendChild(noticeEl);
  }

  _updateCount() {
    const n = this.steps.length;
    if (!n) return;
    this.countEl.hidden = false;
    this.countEl.textContent = `${n} bước`;
  }

  // -------------------------------------------------------------------------
  // Kết thúc
  // -------------------------------------------------------------------------

  /**
   * @param {boolean} success Tra cứu có hoàn tất trọn vẹn hay không
   * @param {string} [errMsg] Thông điệp lỗi nếu thất bại
   */
  finalize(success, errMsg = '') {
    if (this.isDone) return;
    this.isDone = true;
    this.endTime = Date.now();
    this._stopTicking();

    const elapsed = this.endTime - this.startTime;
    this.timerEl.textContent = `${(elapsed / 1000).toFixed(1)}s`;

    // Bản nháp còn đang chảy khi luồng kết thúc: chốt lại để nó thôi quay
    if (this.draftEl) {
      if (success) this.commitDraft();
      else this.discardDraft();
    }

    // Lượt cuối thường chỉ sinh ra câu trả lời rồi thôi; nhãn lượt của nó sẽ đứng
    // trơ ở cuối ray mà không có gì bên dưới. Gỡ mọi nhãn lượt không còn nội dung.
    [...this.rail.querySelectorAll('.trace__turn')].forEach(marker => {
      if (!marker.nextElementSibling) marker.remove();
    });

    // Bước còn dở dang khi luồng kết thúc đột ngột phải thôi quay
    if (this.activeStep) {
      this.activeStep.el.classList.remove('trace__step--running');
      this.activeStep.nodeEl.innerHTML = getIcon(success ? 'check' : 'alert', 'icon--xs');
      this.activeStep = null;
    }

    const stepCount = this.steps.length;

    if (success) {
      this.statusEl.dataset.state = 'done';
      this.statusEl.innerHTML = getIcon('check', 'icon--xs');
      this._setHeadline(stepCount > 0
        ? `Đã tra cứu ${stepCount} bước trên văn bản gốc`
        : 'Đã trả lời từ dữ liệu sẵn có');

      // Thu gọn để nhường không gian cho câu trả lời — nội dung vẫn mở lại được
      this.header.setAttribute('aria-expanded', 'false');
      this.rail.hidden = true;
    } else {
      this.statusEl.dataset.state = 'error';
      this.statusEl.innerHTML = getIcon('alert', 'icon--xs');
      this._setHeadline('Tra cứu gặp lỗi');
      if (errMsg) this._addNotice('error', errMsg);
    }
  }
}
