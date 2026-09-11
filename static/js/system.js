/**
 * Khu vực Quản trị hệ thống: cấu hình model đang chạy, tình trạng các tệp dữ liệu,
 * và kết quả benchmark truy xuất RAG trên bộ 35 câu hỏi thực tế.
 */

import { fetchJson, escapeHtml } from './utils.js';

const pane = document.getElementById('system-pane');
let loaded = false;

function healthCard(h) {
  const files = h.data_files.map(f => `
    <tr>
      <td>${escapeHtml(f.name)}</td>
      <td><span class="badge ${f.exists ? 'badge--safe' : 'badge--severe'}">${f.exists ? 'Sẵn sàng' : 'Thiếu'}</span></td>
      <td class="num">${f.size_mb} MB</td>
    </tr>`).join('');

  return `
    <div class="card sys-card">
      <h3>Cấu hình đang chạy</h3>
      <dl class="kv">
        <dt>Model suy luận</dt><dd><code>${escapeHtml(h.model)}</code></dd>
        <dt>Model dự phòng</dt><dd><code>${escapeHtml(h.fallback_model)}</code></dd>
        <dt>Model embedding</dt><dd><code>${escapeHtml(h.embedding_model)}</code></dd>
        <dt>Công cụ của Agent</dt><dd>${h.tools.map(t => `<code>${escapeHtml(t)}</code>`).join(' · ')}</dd>
      </dl>
    </div>

    <div class="card sys-card">
      <h3>Dữ liệu đã nạp</h3>
      <div class="metric-row">
        <div class="metric"><div class="val">${h.documents_loaded}</div><div class="lbl">Văn bản</div></div>
        <div class="metric"><div class="val">${h.chapters_loaded}</div><div class="lbl">Chương</div></div>
        <div class="metric"><div class="val">${h.articles_loaded}</div><div class="lbl">Điều luật</div></div>
                <div class="metric"><div class="val">${h.penalty_behaviours}</div><div class="lbl">Hành vi bị phạt</div></div>
        <div class="metric"><div class="val">${h.semantic_chunks}</div><div class="lbl">Chunk ngữ nghĩa</div></div>
      </div>
      <div class="table-wrap"><table class="data-table sys-table">
        <thead><tr><th>Tệp</th><th>Trạng thái</th><th class="num">Dung lượng</th></tr></thead>
        <tbody>${files}</tbody>
      </table></div>
    </div>`;
}

function benchmarkCard(b) {
  const m = b.metrics;
  const rows = b.detailed_results.map(r => `
    <tr>
      <td>${escapeHtml(r.question)}</td>
      <td>Điều ${escapeHtml(String(r.target_article))}</td>
      <td>${(r.retrieved_articles || []).map(a => `Điều ${escapeHtml(String(a))}`).join(', ')}</td>
      <td><span class="badge ${r.is_hit_1 ? 'badge--safe' : (r.is_hit_3 ? 'badge--primary' : 'badge--severe')}">${r.is_hit_1 ? 'Top 1' : (r.is_hit_3 ? 'Top 3' : 'Trượt')}</span></td>
    </tr>`).join('');

  return `
    <div class="card sys-card">
      <h3>Hiệu năng truy xuất (bộ ${m.total_questions} câu hỏi thực tế)</h3>
      <div class="metric-row">
        <div class="metric"><div class="val">${m.hit_rate_at_1.toFixed(1)}%</div><div class="lbl">Đúng ngay Top 1</div></div>
        <div class="metric"><div class="val">${m.hit_rate_at_3.toFixed(1)}%</div><div class="lbl">Đúng trong Top 3</div></div>
        <div class="metric"><div class="val">${m.mrr.toFixed(2)}</div><div class="lbl">MRR</div></div>
      </div>
      <p class="sys-hint">
        Chạy lại bằng <code>python main.py --eval</code>.
      </p>
      <div class="table-wrap"><table class="data-table sys-table">
        <thead><tr><th>Câu hỏi</th><th>Điều đúng</th><th>Điều truy xuất được</th><th>Kết quả</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>`;
}

function fmtUsd(v) {
  return `$${Number(v || 0).toFixed(6)}`;
}

function fmtPct(v) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`;
}

function codeList(dist) {
  const entries = Object.entries(dist || {});
  if (!entries.length) return '—';
  return entries.map(([k, v]) => `<code>${escapeHtml(k)}</code> × ${v}`).join(' · ');
}

function traceSummaryCard(s) {
  const nodeRows = Object.entries(s.nodes || {}).map(([node, st]) => `
    <tr>
      <td>${escapeHtml(node)}</td>
      <td class="num">${st.count}</td>
      <td class="num">${st.p50_ms}</td>
      <td class="num">${st.p95_ms}</td>
    </tr>`).join('');

  return `
    <div class="card sys-card">
      <h3>Quan trắc vận hành (LangGraph)</h3>
      <p class="sys-hint">
        Số liệu tổng hợp từ ${s.runs} lượt chạy đã ghi trace cục bộ. Đây chỉ là con số đo
        lường — endpoint <code>/api/trace/summary</code> KHÔNG trả về và không lưu nội dung
        câu hỏi của người dùng.
      </p>

      <div class="metric-row">
        <div class="metric"><div class="val">${s.runs}</div><div class="lbl">Lượt chạy</div></div>
        <div class="metric"><div class="val">${s.llm_calls_per_run}</div><div class="lbl">Lệnh gọi LLM / lượt</div></div>
        <div class="metric"><div class="val">${fmtUsd(s.cost_per_run_usd)}</div><div class="lbl">Chi phí / lượt</div></div>
        <div class="metric"><div class="val">${fmtUsd(s.total_cost_usd)}</div><div class="lbl">Tổng chi phí ước tính</div></div>
        <div class="metric"><div class="val">${fmtPct(s.fallback_rate)}</div><div class="lbl">Tỉ lệ dùng model dự phòng</div></div>
        <div class="metric"><div class="val">${s.errors}</div><div class="lbl">Sự kiện lỗi</div></div>
      </div>

      <dl class="kv">
        <dt>Model đã dùng</dt><dd>${codeList(s.model_distribution)}</dd>
        <dt>Tầng structured output</dt><dd>${codeList(s.structured_tier_distribution)}</dd>
        <dt>Cache vector truy vấn</dt>
        <dd>${s.cache_lookups} lượt tra · tỉ lệ trúng ${fmtPct(s.cache_hit_rate)}</dd>
      </dl>
      <p class="sys-hint">
        "Cache vector truy vấn" ở trên là cache <strong>embedding</strong> dùng để rút gọn bước
        tìm kiếm ngữ nghĩa — không phải cache lưu sẵn câu trả lời (thống kê riêng qua
        <code>python scripts/cache_admin.py --stats</code>).
      </p>

      <div class="table-wrap"><table class="data-table sys-table">
        <thead><tr><th>Node</th><th class="num">Số lần</th><th class="num">p50 (ms)</th><th class="num">p95 (ms)</th></tr></thead>
        <tbody>${nodeRows}</tbody>
      </table></div>
    </div>`;
}

export async function initSystemView() {
  if (loaded) return;
  loaded = true;
  pane.innerHTML = '<div class="placeholder">Đang tải thông tin hệ thống…</div>';

  try {
    const health = await fetchJson('/api/health');
    pane.innerHTML = healthCard(health);
  } catch (err) {
    loaded = false;
    pane.innerHTML = `<div class="placeholder">Không tải được trạng thái: ${escapeHtml(err.message)}</div>`;
    return;
  }

  // Benchmark là tuỳ chọn: thiếu báo cáo thì chỉ hiện hướng dẫn, không coi là lỗi hệ thống
  try {
    const bench = await fetchJson('/api/benchmark');
    pane.insertAdjacentHTML('beforeend', benchmarkCard(bench));
  } catch (err) {
    pane.insertAdjacentHTML('beforeend', `
      <div class="card sys-card"><h3>Hiệu năng truy xuất</h3>
      <p class="sys-desc">${escapeHtml(err.message)}</p></div>`);
  }

  // Quan trắc trace cũng tuỳ chọn: chưa có lượt chạy nào thì chỉ hiện hướng dẫn
  try {
    const trace = await fetchJson('/api/trace/summary');
    pane.insertAdjacentHTML('beforeend', traceSummaryCard(trace));
  } catch (err) {
    pane.insertAdjacentHTML('beforeend', `
      <div class="card sys-card"><h3>Quan trắc vận hành (LangGraph)</h3>
      <p class="sys-desc">${escapeHtml(err.message)}</p></div>`);
  }
}
