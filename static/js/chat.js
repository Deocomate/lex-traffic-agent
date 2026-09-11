/**
 * chat.js - Khu vực Hỏi đáp AI Agent:
 * Gọi Agentic Legal Search qua SSE, hiển thị tiến trình suy luận ReAct,
 * nguồn trích dẫn đa văn bản pháp luật, và lưu trữ lịch sử phiên trò chuyện.
 */

import { renderMarkdown, fetchJson, el, showToast } from './utils.js';
import { getIcon } from './ui/icons.js';
import { AgentTrace } from './agent-trace.js';
import { renderSources } from './sources.js';

const STORE_KEY = 'lextraffic.sessions';
const MAX_SESSIONS = 20;

const thread = document.getElementById('thread');
const emptyState = document.getElementById('empty-state');
const form = document.getElementById('composer');
const input = document.getElementById('input');
const btnSend = document.getElementById('btn-send');
const sessionList = document.getElementById('session-list');

let sessions = loadSessions();
let currentId = null;
let history = [];
let busy = false;

// Định danh thread của checkpointer phía máy chủ. Nó thuộc về từng phiên hội thoại chứ không
// phải từng tab: mở lại một phiên cũ sau khi F5 phải nối đúng ngữ cảnh của chính phiên đó,
// còn "Hỏi đáp mới" phải bắt đầu bằng thread rỗng.
let threadId = '';

function getThreadId() {
  return threadId;
}

function setThreadId(id) {
  threadId = id || '';
}

// ---------------------------------------------------------------------------
// 1. Quản lý phiên hội thoại trong LocalStorage
// ---------------------------------------------------------------------------

function loadSessions() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
  } catch {
    return [];
  }
}

function persist() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS)));
  } catch {
    /* Trình duyệt riêng tư hoặc chặn lưu trữ */
  }
}

function saveCurrent() {
  if (!history.length) return;
  const title = history[0].content.slice(0, 50);
  const existing = sessions.find(s => s.id === currentId);
  if (existing) {
    Object.assign(existing, { title, messages: history, threadId, updatedAt: Date.now() });
  } else {
    currentId = currentId || String(Date.now());
    sessions.unshift({ id: currentId, title, messages: history, threadId, updatedAt: Date.now() });
  }
  persist();
  renderSessions();
}

function renderSessions() {
  if (!sessionList) return;
  sessionList.innerHTML = '';
  if (!sessions.length) {
    sessionList.appendChild(el('div', 'sidebar__empty-notice', 'Chưa có phiên hỏi đáp nào.'));
    return;
  }
  sessions.forEach(s => {
    const item = el('div', 'session-item' + (s.id === currentId ? ' active' : ''));
    const label = el('span', 'session-item__label');
    label.textContent = s.title;
    label.title = s.title;
    item.appendChild(label);

    const del = el('button', 'btn-del-session', '×');
    del.type = 'button';
    del.title = 'Xoá phiên này';
    del.addEventListener('click', e => {
      e.stopPropagation();
      sessions = sessions.filter(x => x.id !== s.id);
      persist();
      if (s.id === currentId) newSession();
      else renderSessions();
    });
    item.appendChild(del);

    item.addEventListener('click', () => openSession(s.id));
    sessionList.appendChild(item);
  });
}

export function openSession(id) {
  if (busy) return;
  const s = sessions.find(x => x.id === id);
  if (!s) return;
  currentId = id;
  history = s.messages.slice();
  setThreadId(s.threadId);
  thread.querySelectorAll('.msg').forEach(m => m.remove());
  if (emptyState) emptyState.hidden = true;
  history.forEach(m => {
    if (m.role === 'user') addUserMessage(m.content);
    else renderStoredAnswer(m.content, m.search, m.sources, m.model_used);
  });
  renderSessions();
}
if (typeof window !== 'undefined') window.openSession = openSession;

export function newSession() {
  if (busy) return;
  currentId = null;
  history = [];
  setThreadId('');
  thread.querySelectorAll('.msg').forEach(m => m.remove());
  if (emptyState) emptyState.hidden = false;
  renderSessions();
  input?.focus();
}
if (typeof window !== 'undefined') window.newSession = newSession;

// ---------------------------------------------------------------------------
// 2. Hiển thị tin nhắn và giao diện Agent
// ---------------------------------------------------------------------------

function scrollToEnd() {
  if (thread) {
    thread.scrollTop = thread.scrollHeight;
  }
}

function addUserMessage(text) {
  const node = el('div', 'msg msg-user');
  const bubble = el('div', 'bubble');
  bubble.textContent = text;
  node.appendChild(bubble);
  thread.appendChild(node);
  scrollToEnd();
}

function renderStoredAnswer(text, search, sources, modelUsed) {
  const node = el('div', 'msg msg-ai');
  const answerEl = el('div', 'answer');
  answerEl.innerHTML = renderMarkdown(text);
  node.appendChild(answerEl);

  const fallbackEl = el('div', 'fallback');
  renderSearchFallback(fallbackEl, search);
  node.appendChild(fallbackEl);

  const docEl = el('div', 'source-doc');
  docEl.hidden = true;

  const sourcesContainer = renderSources(sources, docEl);
  node.appendChild(sourcesContainer);
  node.appendChild(docEl);

  // Nút sao chép câu trả lời + model đã sinh câu trả lời (nếu phiên cũ có lưu)
  const actionsEl = renderMessageActions(text, modelUsed);
  node.appendChild(actionsEl);

  thread.appendChild(node);
  scrollToEnd();
}

function renderSearchFallback(container, search) {
  if (!container) return;
  container.innerHTML = '';
  if (!search || !search.url) return;

  const box = el('div', 'fallback-box');
  box.appendChild(el('div', 'fallback-text',
    'Nội dung này nằm ngoài dữ liệu hệ thống nhận diện được. Bạn có thể tra cứu trực tiếp trên Google:'));

  const link = el('a', 'btn-google');
  link.href = search.url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.innerHTML = `${getIcon('search', 'icon--xs')} ${escapeHtml(search.label || 'Tìm trên Google')}`;
  link.title = search.query || '';
  box.appendChild(link);

  if (search.query) {
    const q = el('div', 'fallback-query');
    q.textContent = `Từ khóa: ${search.query}`;
    box.appendChild(q);
  }
  container.appendChild(box);
}

/** "deepseek/deepseek-v4-flash" → "deepseek-v4-flash"; giá trị đặc biệt "semantic_cache"
 * nghĩa là câu trả lời lấy thẳng từ cache ngữ nghĩa, không qua lượt sinh mới nào. */
function formatModelLabel(modelUsed) {
  if (!modelUsed) return '';
  if (modelUsed === 'semantic_cache') return 'Bộ nhớ đệm ngữ nghĩa';
  const parts = String(modelUsed).split('/');
  return parts[parts.length - 1];
}

function renderMessageActions(fullText, modelUsed) {
  const bar = el('div', 'msg-actions');
  const copyBtn = el('button', 'btn btn--ghost btn--xs btn-copy-msg');
  copyBtn.type = 'button';
  copyBtn.innerHTML = `${getIcon('copy', 'icon--xs')} Sao chép`;
  copyBtn.title = 'Sao chép nội dung câu trả lời';
  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(fullText);
      showToast('Đã sao chép câu trả lời', 'success');
    } catch {
      showToast('Không thể truy cập clipboard', 'warning');
    }
  });
  bar.appendChild(copyBtn);

  // Model đã sinh câu trả lời — kín đáo, chỉ lộ cùng thanh hành động khi hover/focus.
  // Hữu ích vì hệ chạy nhiều model khác nhau và có cơ chế dự phòng tự động.
  const modelLabel = formatModelLabel(modelUsed);
  if (modelLabel) {
    const modelEl = el('span', 'msg-model', escapeHtml(modelLabel));
    modelEl.title = modelUsed === 'semantic_cache'
      ? 'Câu trả lời lấy trực tiếp từ bộ nhớ đệm ngữ nghĩa, không qua lượt sinh mới'
      : `Model đã sinh câu trả lời: ${modelUsed}`;
    bar.appendChild(modelEl);
  }

  return bar;
}

function createAgentMessage() {
  const node = el('div', 'msg msg-ai');

  // Khung timeline suy luận ReAct
  const traceContainer = el('div', 'agent-trace-container');
  node.appendChild(traceContainer);
  const trace = new AgentTrace(traceContainer);

  const answer = el('div', 'answer');
  node.appendChild(answer);

  const fallback = el('div', 'fallback');
  node.appendChild(fallback);

  const sourcesHost = el('div', 'chat-sources-host');
  node.appendChild(sourcesHost);

  const docEl = el('div', 'source-doc');
  docEl.hidden = true;
  node.appendChild(docEl);

  const actionsHost = el('div', 'msg-actions-host');
  node.appendChild(actionsHost);

  thread.appendChild(node);
  scrollToEnd();

  return {
    node,
    trace,
    answer,
    fallback,
    sourcesHost,
    docEl,
    actionsHost
  };
}

// ---------------------------------------------------------------------------
// 3. Gọi AI Agent qua SSE Stream
// ---------------------------------------------------------------------------

async function askAgent(question) {
  const ui = createAgentMessage();
  let draft = '';
  let finalAnswer = '';
  let search = null;
  let sources = [];
  let modelUsed = '';
  let streamError = '';

  // Câu trả lời được đổ vào DOM tối đa mỗi khung hình thay vì mỗi token (một câu trả
  // lời trung bình phát ~140 sự kiện token): dựng lại toàn bộ Markdown và ghi lại
  // innerHTML ở MỖI token khiến độ trễ tăng theo bình phương độ dài câu trả lời và
  // gây giật khi cuộn. Gộp nhiều token rơi vào cùng một khung hình thành một lần vẽ.
  let renderScheduled = false;
  // 'answer_commit'/'done'/'error' tự vẽ nội dung chốt cuối cùng ngay lập tức (đồng bộ).
  // Nếu một khung hình đã lên lịch từ trước đó vẫn chưa kịp chạy, nó sẽ vẽ đè lên bằng
  // `draft` cũ ngay sau khi nội dung chốt vừa hiện — khoá lại để lần vẽ trễ đó thành vô hại.
  let answerFinalized = false;
  function scheduleAnswerRender() {
    if (renderScheduled || answerFinalized) return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      renderScheduled = false;
      if (answerFinalized) return;
      ui.answer.innerHTML = renderMarkdown(draft);
      scrollToEnd();
    });
  }

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        history: history.map(m => ({ role: m.role, content: m.content })),
        thread_id: getThreadId()
      })
    });

    if (!res.ok || !res.body) {
      throw new Error(`Máy chủ phản hồi mã lỗi ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      for (const part of parts) {
        const line = part.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;

        let evt;
        try {
          evt = JSON.parse(line.slice(6));
        } catch {
          continue;
        }

        // Đẩy mọi sự kiện vào AgentTrace
        ui.trace.handleEvent(evt);

        switch (evt.event) {
          // Mô hình thường viết vài câu cân nhắc rồi mới quyết định gọi công cụ, và
          // backend chỉ biết điều đó khi stream đã kết thúc. Vì vậy chỉ văn bản đã
          // được đánh dấu phase="answer" mới được đổ vào ô câu trả lời; phần còn lại
          // chảy vào khối suy nghĩ trên đường ray, nơi nó bị thay thế cũng không gây hụt hẫng.
          case 'token':
            if (evt.phase === 'answer') {
              draft += evt.message;
              scheduleAnswerRender();
            } else {
              ui.trace.appendDraft(evt.message);
            }
            break;

          case 'answer_reset':
            ui.trace.discardDraft();
            break;

          // Bản nháp vừa rồi hoá ra chính là câu trả lời: nâng nó từ khối suy nghĩ lên ô trả lời
          case 'answer_commit':
            draft = evt.answer || ui.trace.getDraft();
            ui.trace.commitDraft();
            ui.answer.innerHTML = renderMarkdown(draft);
            scrollToEnd();
            break;

          case 'done':
            // Chốt: mọi lần vẽ theo khung hình còn treo từ token trước đó không được vẽ đè
            answerFinalized = true;
            // Máy chủ sinh thread_id ở lượt đầu; giữ lại để hội thoại sống qua F5.
            if (evt.thread_id) setThreadId(evt.thread_id);
            finalAnswer = evt.answer || draft;
            search = evt.needs_search ? evt.search : null;
            sources = evt.sources || [];
            modelUsed = evt.model_used || '';
            ui.answer.innerHTML = renderMarkdown(finalAnswer);
            renderSearchFallback(ui.fallback, search);

            // Gắn khay chip nguồn trích dẫn
            ui.sourcesHost.innerHTML = '';
            ui.sourcesHost.appendChild(renderSources(sources, ui.docEl));

            // Gắn thanh công cụ tin nhắn
            ui.actionsHost.innerHTML = '';
            ui.actionsHost.appendChild(renderMessageActions(finalAnswer, modelUsed));
            break;

          case 'error':
            answerFinalized = true;
            streamError = evt.message || 'Lỗi không xác định';
            ui.answer.innerHTML = `<p class="state__desc state__desc--error">${escapeHtml(streamError)}</p>`;
            break;
        }
      }
    }
  } catch (err) {
    // Lỗi xảy ra trước hay giữa luồng (mất mạng, máy chủ không phản hồi): thẻ đường
    // ray đã được dựng và đồng hồ đang chạy từ createAgentMessage() ở đầu hàm. Không
    // chốt lại ở đây thì setInterval của nó chạy vĩnh viễn (rò rỉ) và spinner đứng
    // yên mãi mãi trong khi submitQuestion() lại chèn thêm một thẻ lỗi khác bên dưới.
    ui.trace.finalize(false, err.message || 'Mất kết nối tới máy chủ');
    throw err;
  }

  // Luồng có thể đứt giữa chừng mà không kịp gửi 'done' hay 'error' (mất mạng,
  // máy chủ chết). finalize() tự bỏ qua nếu đã chốt rồi, nên gọi ở đây là an toàn
  // và bảo đảm đường ray không quay spinner vĩnh viễn.
  ui.trace.finalize(Boolean(finalAnswer), streamError);

  // Máy chủ đã nói rõ hỏng ở đâu; giữ nguyên thông điệp đó thay vì ghi đè bằng một
  // câu chung chung, và không gắn nút sao chép cho một thông báo lỗi.
  if (streamError && !finalAnswer) {
    return { answer: '', search: null, sources: [], failed: true };
  }

  if (!finalAnswer) {
    finalAnswer = draft || 'Không nhận được câu trả lời từ máy chủ.';
    ui.answer.innerHTML = renderMarkdown(finalAnswer);
    ui.actionsHost.appendChild(renderMessageActions(finalAnswer, modelUsed));
  }

  return { answer: finalAnswer, search, sources, modelUsed };
}

async function submitQuestion(question) {
  if (busy || !question.trim()) return;
  busy = true;
  if (btnSend) btnSend.disabled = true;
  if (emptyState) emptyState.hidden = true;

  addUserMessage(question);
  history.push({ role: 'user', content: question });

  try {
    const { answer, search, sources, failed, modelUsed } = await askAgent(question);
    // Lượt hỏng không được vào lịch sử: nó sẽ thành ngữ cảnh rỗng cho câu hỏi kế tiếp
    if (!failed) {
      history.push({ role: 'assistant', content: answer, search, sources, model_used: modelUsed });
      saveCurrent();
    }
  } catch (err) {
    const node = el('div', 'msg msg-ai', '<div class="answer"></div>');
    node.querySelector('.answer').innerHTML = `
      <div class="state state--empty">
        <p class="state__title">Không kết nối được tới máy chủ AI</p>
        <p class="state__desc">${escapeHtml(err.message || 'Vui lòng kiểm tra lại kết nối mạng')}</p>
      </div>
    `;
    thread.appendChild(node);
  } finally {
    busy = false;
    if (btnSend) btnSend.disabled = false;
    input?.focus();
    scrollToEnd();
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

// ---------------------------------------------------------------------------
// 4. Khởi tạo & Gắn sự kiện
// ---------------------------------------------------------------------------

// switchView() trong app.js gọi lại view.init() ở MỌI lần khớp route, kể cả khi
// người dùng chỉ đổi giữa #/chat và #/chat/<sessionId> (vẫn cùng view). Không có
// cờ chống gọi lại thì mỗi lần điều hướng gắn thêm một bộ listener submit/keydown/
// input/click mới chồng lên bộ cũ — rò rỉ tăng dần theo số lần điều hướng.
let chatInited = false;

export function initChat() {
  if (!form || !input) return;
  if (chatInited) return;
  chatInited = true;

  form.addEventListener('submit', e => {
    e.preventDefault();
    const q = input.value.trim();
    input.value = '';
    input.style.height = 'auto';
    submitQuestion(q);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  });

  document.querySelectorAll('.suggestions button, .suggestion-card, .suggestion-chip').forEach(chip => {
    chip.addEventListener('click', () => submitQuestion(chip.textContent.trim()));
  });

  const btnNewChat = document.getElementById('btn-new-chat');
  if (btnNewChat) {
    btnNewChat.addEventListener('click', newSession);
  }

  renderSessions();
}
