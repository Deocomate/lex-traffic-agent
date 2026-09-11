# Báo cáo: Đồng bộ GIAO DIỆN HỘI THOẠI với backend LangGraph mới

Phạm vi: `static/js/agent-trace.js`, `static/js/chat.js`, `static/css/chat.css`,
`templates/views/chat.html` (không sửa), `templates/views/system.html` (không sửa,
đã đủ), `static/js/system.js`.

## 1. `verified` phát trên MỌI câu trả lời sạch — sửa hiển thị

Xác minh qua code (`src/graph/verify.py:135-149`): điều kiện cũ `not issues and
repair_count > 0` đã đổi thành phát `verified` bất cứ khi nào `not issues`, đúng
như đề mô tả. Test SSE thật (câu hỏi tốc độ xe máy) xác nhận: `verified` xuất hiện,
`verifying` KHÔNG xuất hiện (đường thuận lợi, không cần sửa lại).

**Vấn đề tìm thấy:** dòng `.trace__notice--verified` nằm TRONG `.trace__rail`, mà
`finalize()` tự thu gọn `.trace__rail` (hidden = true) ngay khi thành công. Tín hiệu
kiểm chứng — theo đúng lời trong comment nguồn `verify.py` là "lớp phòng vệ quan
trọng nhất của sản phẩm" — trở thành vô hình ngay sau khi trả lời xong, trừ khi
người dùng bấm mở lại chi tiết ray. Đây chính là điều mục 1 yêu cầu kiểm tra.

**Đã sửa:** thêm huy hiệu `.trace__verify` cố định ở hàng đầu (`trace__header`,
trong `trace__meta`), KHÔNG bị ẩn khi ray thu gọn:
- `verified` → `data-state="ok"`, nhãn "Đã xác minh", màu `--data-safe` (6.4:1).
- `warning` (cancel_node huỷ câu trả lời) → `data-state="warn"`, nhãn "Đã huỷ câu
  trả lời", màu `--data-fine` (5.4:1) — theo đúng convention tone `warn` đã có sẵn
  trong `NOTICE_VARIANTS`, không tự ý đổi mức nghiêm trọng.
- `title` mang nguyên văn message backend để xem chi tiết khi hover; dòng thông báo
  gốc trong ray vẫn giữ nguyên cho ai mở rộng xem toàn bộ diễn biến.

**Bug thật kèm theo tìm thấy:** `verifying` khai `tone: 'info'` trong
`NOTICE_VARIANTS` nhưng `chat.css` KHÔNG có rule `.trace__notice--info` nào — sự
kiện này (khi phải sửa lại câu trả lời) hiện ra không màu sắc, không phân biệt được
với trạng thái mặc định. Đã thêm rule dùng `--accent`/`--accent-soft`/`--accent-line`
(nhất quán với các trạng thái "đang chạy" khác trên ray).

File: `static/js/agent-trace.js` (thêm `_setVerifyBadge`, gọi ở case `verified`/
`warning`), `static/css/chat.css` (`.trace__verify*`, `.trace__notice--info`).

## 2. `model_used` — đã đọc và hiển thị kín đáo

Thêm vào `renderMessageActions(fullText, modelUsed)`: một `<span class="msg-model">`
nối vào thanh hành động cạnh nút Sao chép — thanh này vốn đã ẩn (`opacity:0`) và chỉ
lộ ra khi hover/focus vào tin nhắn (`.msg-ai:hover`, `:focus-within`), nên đúng tinh
thần "kín đáo, không làm rối giao diện" mà không cần thêm cơ chế ẩn/hiện mới.

- `"deepseek/deepseek-v4-flash"` → hiển thị `deepseek-v4-flash` (bỏ phần nhà cung
  cấp trước dấu `/`), `title` đầy đủ giữ nguyên chuỗi gốc.
- `model_used === "semantic_cache"` (câu trả lời lấy thẳng từ cache ngữ nghĩa, không
  qua model nào) → nhãn riêng "Bộ nhớ đệm ngữ nghĩa" thay vì hiện chuỗi kỹ thuật.
- Lưu `model_used` vào `history` (giống cách `search`/`sources` đã lưu) nên khi mở
  lại phiên cũ (F5, `openSession`) nhãn vẫn còn — không chỉ có ở lượt vừa stream.

Test thật: `done.model_used = "deepseek/deepseek-chat"` — đúng field, đúng format
`provider/model`, contract SSE nguyên vẹn (đối chiếu đủ 8 field:
answer/sources/agent_steps/verification_issues/needs_search/search/model_used/
thread_id).

File: `static/js/chat.js` (`formatModelLabel`, `renderMessageActions`, plumbing qua
`askAgent`→`submitQuestion`→`history`→`renderStoredAnswer`), `static/css/chat.css`
(`.msg-model`).

## 3. `model_fallback` — đã đúng, không sửa gì

`agent-trace.js` case `model_fallback` → `_addNotice('fallback', ...)` →
`NOTICE_VARIANTS.fallback = { icon:'alert', tone:'warn' }` → `.trace__notice--warn`
đã có CSS sẵn (dùng `--data-fine`). Đọc code backend (`src/llm/provider.py:132-147`)
xác nhận message thật: `"Chuyển sang model dự phòng: {active_model}"`, không có
emoji dẫn đầu nên `stripLeadingGlyph` không cắt nhầm ký tự đầu. Không có trace log
fallback thật nào trong dữ liệu hiện có (`fallback_runs: 0` trên 385 lượt) nên không
demo được bằng SSE thật trong ngân sách câu hỏi cho phép — xác minh bằng đọc code +
test tĩnh CSS/class, không phải bằng lượt fallback thật.

**Lưu ý về đánh đổi đã cân nhắc:** không thêm huy hiệu cố định riêng cho
`model_fallback` ở hàng đầu (như đã làm cho `verified`) dù nó cũng bị ẩn sau khi ray
thu gọn — vì huy hiệu `msg-model` (mục 2) đã phản ánh gián tiếp: khi có fallback,
`model_used` cuối cùng sẽ là model dự phòng, xem được qua hover. Thêm huy hiệu thứ
ba vào hàng đầu sẽ vi phạm đúng lời dặn "đừng làm rối giao diện" trong khi lợi ích
biên rất nhỏ (sự kiện hiếm, không xảy ra trong dữ liệu thật hiện có).

## 4. Trang `system.html` — panel Quan trắc vận hành

Đọc `scripts/eval/summarize_traces.py::summarize()` lấy đúng shape JSON thật (không
đoán): `runs, nodes{count,p50_ms,p95_ms}, llm_calls_per_run, total_cost_usd,
cost_per_run_usd, cache_lookups, cache_hit_rate|null, structured_tier_distribution,
model_distribution, fallback_rate, errors`.

Dựng `traceSummaryCard()` trong `system.js`, gọi `/api/trace/summary` sau
`/api/health`/`/api/benchmark`, cùng pattern try/catch tuỳ chọn (404 khi chưa có
trace → hiện `sys-desc` với message backend, không coi là lỗi hệ thống — giống hệt
cách `benchmarkCard` đã xử lý thiếu báo cáo).

**Không có CSS mới nào cần thêm** — panel dựng hoàn toàn từ class đã có sẵn trong
`components.css`/`lookup.css` (không thuộc phạm vi sở hữu của tôi): `.card.sys-card`,
`.metric-row/.metric/.val/.lbl`, `.kv`, `.table-wrap/.data-table/.sys-table`,
`.sys-hint`. Test thật trên server chạy: endpoint trả 385 lượt, 14 node, cost
$0.0419 tổng, cache_hit_rate 88.8% — panel hiển thị đúng số.

**Ràng buộc riêng tư đã tuân thủ:** không có bảng/khối nào hiển thị theo TỪNG lượt
hay bất kỳ nội dung câu hỏi nào — endpoint gốc vốn đã không trả field đó, và tôi
không dựng UI giả định có sẵn nó. Có câu ghi rõ trong card: endpoint không lưu/trả
nội dung câu hỏi. Nhãn cache ghi rõ "Cache vector truy vấn" + chú thích tách bạch
khỏi cache câu trả lời (đúng yêu cầu, đúng luôn với chú thích trong
`summarize_traces.py::print_report`).

`templates/views/system.html` không cần sửa — nó vốn chỉ là một `<div id="system-pane">`
rỗng để JS dựng vào, đã đúng chủ đích từ trước.

## 5. Bug thật tìm và sửa trong phạm vi

1. **Rò rỉ `setInterval` + spinner treo vĩnh viễn khi `fetch` lỗi ngay từ đầu**
   (`chat.js::askAgent`). `createAgentMessage()` khởi `AgentTrace` (bắt đầu
   `setInterval` đếm giờ) TRƯỚC lệnh `fetch()`. Nếu `fetch` reject (mất mạng) hoặc
   response không `ok`, lỗi ném ra khỏi `askAgent` mà KHÔNG bao giờ chạy tới dòng
   `ui.trace.finalize(...)` ở cuối hàm — interval chạy mãi, thẻ ray "ma" đứng
   spinner vĩnh viễn, trong khi `submitQuestion`'s catch lại chèn thêm MỘT thẻ lỗi
   khác bên dưới (2 thẻ trùng lặp cho 1 lượt hỏng). Sửa: bọc phần fetch+đọc SSE
   trong `try/catch`, catch gọi `ui.trace.finalize(false, err.message)` rồi ném
   tiếp lỗi ra ngoài (giữ nguyên hành vi `submitQuestion` hiện có).
2. **`.trace__notice--info` không tồn tại trong CSS** — xem mục 1.
3. **Thao tác DOM trong vòng lặp token (~140 sự kiện/câu):** mỗi token phase="answer"
   gọi `renderMarkdown(draft)` (bộ dựng Markdown tự viết, quét lại toàn bộ chuỗi từ
   đầu) rồi ghi `innerHTML` — chi phí tăng theo O(n²) độ dài câu trả lời, có khả
   năng gây giật khi câu trả lời dài. Sửa: gộp nhiều token rơi vào cùng một khung
   hình bằng `requestAnimationFrame`, chỉ vẽ 1 lần/frame thay vì 1 lần/token. Có
   thêm cờ `answerFinalized` để chặn trường hợp một khung hình đã lên lịch từ trước
   vẽ ĐÈ lên nội dung chốt cuối cùng khi `done`/`error` đến ngay sau đó (race điều
   kiện tự tạo ra nếu không khoá — đã kiểm tra kỹ và chặn đúng chỗ).
4. **`initChat()` không có cờ chống gọi lại** — `app.js::switchView()` (ngoài phạm
   vi, chỉ đọc không sửa) gọi `view.init()` ở MỌI lần khớp route, kể cả đổi giữa
   `#/chat` và `#/chat/<sessionId>` (cùng view `chat`). Không có cờ, mỗi lần điều
   hướng gắn thêm một bộ listener `submit`/`keydown`/`input`/click MỚI chồng lên bộ
   cũ — rò rỉ tăng dần không giới hạn theo số lần điều hướng. `initSystemView()` đã
   có cờ `loaded` chống việc này nhưng `initChat()` thì không. Đã thêm cờ
   `chatInited` mô phỏng đúng pattern đã có, không đổi hành vi lần init đầu tiên.
5. **Rà nhưng KHÔNG phải bug — biến/case chết:** không tìm thấy `case` chết nào
   trong 2 switch (`agent-trace.js::handleEvent`, `chat.js::askAgent`'s switch) —
   toàn bộ event trong docstring đều có nhánh xử lý tương ứng. Không có biến khai
   báo mà không dùng trong 2 file JS thuộc phạm vi.

## Việc đã KHÔNG làm (nằm ngoài phạm vi, chỉ báo cáo)

- `chat.js` có hàm `escapeHtml` tự viết (escape thêm `"`/`'`) trùng lặp một phần với
  `escapeHtml` export từ `utils.js`/`markdown.js` (chỉ escape `&`/`<`/`>`). Không
  giống hệt nhau (khác hành vi với quote) nên không phải bug thật — không đổi vì
  không thuộc yêu cầu và không ảnh hưởng hiển thị (mọi lệnh gọi hiện tại đều chèn
  vào nội dung text trong `innerHTML`, không phải giá trị attribute).
- Không sửa `app.js::switchView()` dù nó là nguyên nhân gốc của bug #4 — file ngoài
  phạm vi sở hữu; đã vá triệt để từ phía `chat.js` (đủ để loại bỏ rò rỉ).

## Kiểm thử thật đã chạy

- Server cổng 8099, tắt sạch sau khi xong (xác nhận `curl` trả `000` sau
  `taskkill`).
- 1/3 câu hỏi ngân sách: "Xe máy chạy quá tốc độ 10km/h trong khu dân cư bị phạt
  bao nhiêu tiền?" → chuỗi sự kiện thật: `start, turn_start, tool_call×3,
  tool_result×3, synthesizing, token×110, answer_commit, verified, done` — đúng
  hợp đồng, `verified` đúng như backend đã sửa, `done` đủ 8 field kể cả
  `model_used`.
- `/api/trace/summary` đọc dữ liệu trace có sẵn (385 lượt, không tốn thêm API) để
  xác nhận shape JSON và hiển thị panel mới.
- `node --check` sạch trên cả 3 file JS đã sửa.
- Lint gate thủ công theo mục 5 `docs/design-system.md`: không `style="..."`, không
  hex ngoài tokens.css, không `transition: all`, không emoji trong JS, mọi class
  JS dựng đều có rule CSS tương ứng (trace__verify, trace__verify-icon [kế thừa từ
  cha, không cần rule riêng — giống `.trace__draft-label` không span con riêng],
  msg-model, trace__notice--info).

Status: DONE
Summary: Vá hiển thị `verified`/`verifying`/`warning` (huy hiệu cố định + CSS tone info bị thiếu), thêm hiển thị `model_used` kín đáo, dựng panel quan trắc mới cho `system.html`, và sửa 3 bug thật trong phạm vi (rò rỉ interval khi fetch lỗi, giật do render token đồng bộ, rò rỉ listener khi initChat gọi lại). Đã test bằng 1 câu hỏi thật + đọc trace có sẵn, server đã tắt sạch.
Concerns/Blockers: `model_fallback` không demo được bằng SSE thật (0 lượt fallback trong dữ liệu hiện có, và ngân sách câu hỏi không cho phép ép fallback xảy ra) — chỉ xác minh tĩnh qua code + CSS đã tồn tại sẵn, không phải bug mới. Cân nhắc chưa chốt: có nên thêm huy hiệu hàng đầu riêng cho fallback hay không — tôi chọn không thêm (xem lý do mục 3), có thể đổi ý nếu người dùng muốn tín hiệu đó nổi bật hơn `model_used` hover hiện tại.
