/**
 * LexTraffic AI — Trình Xem Văn Bản Gốc PDF Đa Văn Bản
 * Hỗ trợ chuyển đổi đọc trực tiếp 6 file PDF có Text Layer tìm kiếm được
 */

import { createSelect } from './ui/select.js';

let loaded = false;
let currentDoc = '01_luat_36_2024_qh15';
let docSelect = null;

const DEFAULT_DOCS = [
  { value: '01_luat_36_2024_qh15', label: 'Luật 36/2024/QH15 · Trật tự, ATGT đường bộ' },
  { value: '02_luat_35_2024_qh15', label: 'Luật 35/2024/QH15 · Luật Đường bộ' },
  { value: '03_nghi_dinh_168_2024_nd_cp', label: 'Nghị định 168/2024/NĐ-CP · Xử phạt VPHC' },
  { value: '04_thong_tu_31_2019_tt_bgtvt', label: 'Thông tư 31/2019/TT-BGTVT · Tốc độ & cự ly' },
  { value: '05_thong_tu_73_2024_tt_bca', label: 'Thông tư 73/2024/TT-BCA · Tuần tra CSGT' },
  { value: '06_qcvn_41_2019_bgtvt', label: 'QCVN 41:2019/BGTVT · Báo hiệu đường bộ' }
];

export function loadPdf(docId) {
  currentDoc = docId || currentDoc;
  const frame = document.getElementById('pdf-frame');
  const extBtn = document.getElementById('btn-pdf-external');
  if (!frame) return;

  if (docSelect && docSelect.getValue() !== currentDoc) {
    docSelect.setValue(currentDoc);
  }

  const url = `/api/pdf?doc=${currentDoc}`;
  if (extBtn) extBtn.href = url;

  frame.innerHTML = '';
  const iframe = document.createElement('iframe');
  iframe.src = url;
  iframe.title = `Tài liệu PDF (${currentDoc})`;
  iframe.className = 'pdf-frame__iframe';

  frame.appendChild(iframe);
}

export function initPdfView() {
  if (loaded) return;
  loaded = true;

  const mountEl = document.getElementById('pdf-doc-select');
  if (mountEl) {
    docSelect = createSelect(mountEl, {
      options: DEFAULT_DOCS,
      value: currentDoc,
      ariaLabel: 'Chọn tài liệu PDF gốc',
      id: 'pdf-doc-select-trigger',
      onChange: (val) => loadPdf(val)
    });

    // Nạp metadata động từ API để cập nhật tên chuẩn xác
    fetch('/api/documents')
      .then(r => r.json())
      .then(data => {
        if (data && data.documents && data.documents.length) {
          const dynamicOpts = data.documents.map(d => ({
            value: d.id,
            label: `${d.code} · ${d.short_title}`
          }));
          docSelect.setOptions(dynamicOpts, currentDoc);
        }
      })
      .catch(() => {});
  }

  // Nạp mặc định văn bản đầu tiên
  loadPdf(currentDoc);
}
