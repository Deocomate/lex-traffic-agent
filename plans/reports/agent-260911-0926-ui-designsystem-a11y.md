# Rà soát Hệ Thiết Kế + A11y + Responsive — LexTraffic AI

Phạm vi: `static/css/{tokens,base,components,shell,lookup}.css`, `templates/index.html` + `layouts/` + `partials/` + `views/{law,penalties,pdf,utilities}.html`, `static/js/{app,router,palette,law,law_formatter,penalty,utilities,pdf,sources,markdown,utils}.js` + `static/js/ui/*.js`. Không đụng `chat.js/chat.css/agent-trace.js/system.js/system.html/chat.html`, `src/`, `tests/`, `docs/`, `plans/`, `data/`.

## Đã sửa

| # | Vi phạm | Tệp:dòng | Cách sửa | Đã sửa |
|---|---|---|---|---|
| 1 | `border-radius: 4px` hardcode (11 chỗ), trùng khớp token `--radius-xs` có sẵn nhưng không dùng | `lookup.css:340,447,679,1263,1461,1513`; `components.css:481,1041`; `shell.css:274,418,607` | Đổi hết sang `var(--radius-xs)` | ✅ |
| 2 | `top: 4px; bottom: 4px;` hardcode trùng khớp `--space-1` | `lookup.css:385-386` | Đổi sang `var(--space-1)` | ✅ |
| 3 | `height: 26px` hardcode trùng `--control-height-sm` | `components.css:475` (`.segmented__item`) | Đổi sang `var(--control-height-sm)` | ✅ |
| 4 | `height: 32px` hardcode trùng `--control-height` | `shell.css:123` (`.nav-item`) | Đổi sang `var(--control-height)` | ✅ |
| 5 | `.btn--xs { height: 22px }`, `.btn--icon.btn--xs { width: 22px }` hardcode, không có token cho bậc "siêu nhỏ" dù pattern 22px lặp lại (dùng ở chat.js ngoài phạm vi + `.btn-copy-clause`) | `components.css:116-130` | Thêm token mới `--control-height-xs: 22px` vào `tokens.css` (nối tiếp `--control-height`/`--control-height-sm`), 2 rule ở `components.css` trỏ vào token này; `.btn-copy-clause` (`lookup.css:439-445`) cũng đổi theo | ✅ |
| 6 | Vùng chạm `.btn-copy-clause` (22×22px) dưới ngưỡng 44px, trong khi tiện ích `.hit-area` đã dựng sẵn cho đúng trường hợp này nhưng chưa từng được gắn ở đâu trong toàn dự án | `static/js/law_formatter.js:198,244` | Gắn thêm class `hit-area` vào nút | ✅ |
| 7 | `role="tab"` trên `.doc-tab` (Bộ luật) không bao giờ cập nhật `aria-selected` khi đổi văn bản — trình đọc màn hình luôn báo tab cũ là tab đang chọn. CSS đã có sẵn selector `[aria-selected="true"]` chờ JS đồng bộ | `static/js/law.js` hàm `switchDocument()` | Thêm `t.setAttribute('aria-selected', isTarget ? 'true' : 'false')` song song với toggle class `active` | ✅ |
| 8 | Bug tương tự #7 cho `.util-tab` (5 tab Kho tiện ích) | `static/js/utilities.js` hàm `switchSubView()` | Thêm cập nhật `aria-selected` | ✅ |
| 9 | `<label for="speed-vehicle/road/area">` và `<label for="pdf-doc-select">` trỏ vào `<div class="select">` — div không phải phần tử labelable/focusable, click vào label không mở được dropdown (screen reader vẫn đọc đúng nhờ `aria-label` set riêng trên trigger, nhưng chuột/click delegation hỏng) | `templates/views/utilities.html:121,126,131`; `templates/views/pdf.html:5` | Thêm `config.id` cho `createSelect()` để gán id ổn định lên `<button class="select__trigger">` thật sự nhận focus (`static/js/ui/select.js`); wire `id: 'speed-vehicle-trigger'` v.v. trong `utilities.js`/`pdf.js`; sửa `for=` trong 2 template trỏ đúng id mới | ✅ |
| 10 | `aria-expanded="true"` viết cứng trên nút toggle sidebar trong khi ở khổ ≤900px sidebar mặc định ĐÓNG (CSS `transform: translateX(-100%)`) — sai trạng thái lúc tải trang trên di động | `templates/partials/topbar.html:3` + `static/js/app.js` `bootstrap()` | Thêm kiểm tra `window.innerWidth <= 900` lúc khởi động để sửa `aria-expanded` về `false` trước khi người dùng bấm lần đầu | ✅ |
| 11 | Khoá cuộn trang nền bằng `document.body.style.overflow = 'hidden'/''` trực tiếp trong JS — vi phạm "không style inline trong JS", lặp lại y hệt ở 2 nơi | `static/js/ui/modal.js` (mở/đóng), `static/js/palette.js` (mở/đóng) | Thêm class tiện ích `.scroll-locked { overflow: hidden; }` vào `base.css`; 2 tệp JS chuyển sang `classList.add/remove('scroll-locked')`. Phần bù `paddingRight` giữ nguyên inline vì là giá trị đo runtime (bề rộng thanh cuộn khác nhau theo trình duyệt/OS) — không thể biểu diễn bằng token/class tĩnh, cùng bản chất với kỹ thuật định vị `select.js` đã được tài liệu hoá cho phép | ✅ |
| 12 | Bug hợp đồng API `showToast`: `docs/design-system.md` §3.5 và 3 lệnh gọi thật (`sources.js:320,322`; `utilities.js:46`) đều gọi `showToast(msg, 'success'/'warning')` — chuỗi biến thể. Nhưng wrapper `utils.js` khai báo tham số 2 là `duration` (number) rồi truyền thẳng xuống `ui/toast.js`, khiến `ui/toast.js` không nhận diện được chuỗi là variant (`typeof 'success' !== 'object'` và `!== 'number'`) → luôn rơi về style mặc định, im lặng sai màu | `static/js/utils.js`, `static/js/ui/toast.js` | `utils.js`: đổi wrapper thành forward nguyên `options` không ép tên/kiểu. `ui/toast.js`: nhận thêm nhánh `typeof options === 'string'` làm viết tắt cho `variant` | ✅ |
| 13 | Thiếu định nghĩa CSS cho biến thể `.toast--warning` dù được gọi trong data-flow thật (`sources.js`, và `chat.js` ngoài phạm vi) và được `docs/design-system.md` liệt kê là biến thể hợp lệ — vi phạm quy tắc 5 "mọi class dựng bằng JS phải có định nghĩa CSS" | `components.css` (sau `.toast--success`) | Thêm `.toast--warning { background-color: var(--data-fine); }` — tương phản trắng/amber ~5.45:1, đạt AA, nhất quán với 2 biến thể đã có | ✅ |

Sau khi vá #12+#13, mọi lệnh gọi `showToast(msg, 'success'|'warning'|'error')` trong TOÀN dự án (kể cả `chat.js`, `sources.js` ngoài phạm vi vẫn dùng chung `utils.js`/`ui/toast.js` của tôi) tự động hiển thị đúng màu — sửa 1 chỗ, lan đúng khắp app mà không phải đụng file ngoài phạm vi.

## Đã rà, xác nhận KHÔNG phải vi phạm (để nguyên, có lý do)

| Vị trí | Vì sao không sửa |
|---|---|
| `base.css:178` `.skip-link { top: -100px }` | Kỹ thuật ẩn skip-link ngoài khung hình chuẩn, không phải giá trị trên thang spacing |
| `base.css:216` `.hit-area::before { inset: -10px }` | Đúng thiết kế mở rộng vùng chạm, không map vào token nào |
| `shell.css:154` `.nav-item.active::before { left: -9px }` | Offset canh vạch chỉ báo theo pixel thật, không thuộc thang space/radius |
| `components.css:494` `.segmented__item--active { box-shadow: 0 1px 2px rgb(13 13 17 / 0.06) }` | Giá trị rgb trùng đúng `--gray-950`, cùng công thức bóng translucent mà chính `tokens.css` dùng cho `--elevation-overlay/--elevation-modal` (không thể `var()` hoá alpha trên hex). Dùng token elevation đầy đủ (3 lớp, nặng) cho một tab 26px sẽ sai thị giác — đây là biến thể vi-nổi hợp lý cho trạng thái active của segmented control, không phải "thẻ tĩnh" bị cấm đổ bóng |
| `components.css:942,956` `animation: ... 1.4s/0.7s` (skeleton, spinner) | Đây là animation lặp vô hạn (loading), không phải chuyển trạng thái rời rạc mà thang `--motion-fast/base/slow` (120/180/240ms) nhắm tới. Ép về thang đó sẽ làm spinner quay/skeleton nhấp nháy sai tốc độ |
| `lookup.css:299` `.hit-snippet mark { border-radius: 2px }` | Không có token khớp 2px; đổi sang 4px (`--radius-xs`) sẽ đổi hình dạng highlight cho lợi ích tuân thủ không đáng kể trên 1 chỗ trang trí — để nguyên |
| `shell.css` `.btn-del-session` 18×18px (dùng bởi `chat.js`, ngoài phạm vi JS nhưng rule CSS nằm trong `shell.css` của tôi) | Không có token khớp 18px; 1 lần dùng duy nhất không đủ để mở thêm bậc token mới theo YAGNI. Nêu ra để cân nhắc nếu pattern 18px lặp lại thêm |
| `.field` áp trực tiếp lên `<input>` (khác pattern `.field`+`.field__control` mà `docs/design-system.md` §3.2 mô tả) | Đúng, đây là sai khác thật giữa docs và code — nhưng code nội bộ nhất quán (4 chỗ dùng), đổi tên class sẽ đụng JS query & rủi ro không cần thiết. Đây là lỗi TÀI LIỆU (`docs/` ngoài phạm vi của tôi), báo cáo chứ không sửa code |
| Route hash tiếng Việt (`#/luat`, `#/muc-phat`...) khác bảng route tiếng Anh trong `docs/design-system.md` §4 | `app.js` có `ROUTE_MAP`/`VIEW_TO_ROUTE` ánh xạ 2 chiều đầy đủ, hoạt động đúng — chỉ là tài liệu mô tả sai so với code thật. Báo cáo cho chủ tài liệu, không sửa |

## Đã rà, thấy nhưng KHÔNG sửa vì rủi ro/ngoài phạm vi — chỉ báo cáo

- **Escape thuộc tính HTML không nhất quán.** `sources.js` tự định nghĩa `escapeHtml()` riêng (dòng 328-336, escape cả `"`/`'`) thay vì import bản dùng chung từ `utils.js`/`markdown.js` (chỉ escape `&<>`, KHÔNG escape dấu ngoặc kép). Đây là **cố ý đúng**: `sources.js` dùng escapeHtml để build thuộc tính `src="…" alt="…"` trong chuỗi HTML rồi gán `innerHTML` — nếu dùng bản chung sẽ hở lỗi thoát thuộc tính khi giá trị chứa `"`. Tuy nhiên phát hiện thêm: `law_formatter.js:198,244` và `penalty.js:71` cũng đưa `escapeHtml()` (bản dùng chung, KHÔNG escape quote) vào thuộc tính `data-copy="…"`/`title="…"` trong template string rồi gán `innerHTML`. Nếu nội dung Khoản/mức phạt trong dữ liệu luật chứa dấu `"` thì có thể phá vỡ thuộc tính. Rủi ro thực tế thấp (nguồn dữ liệu là văn bản luật tĩnh do hệ thống nạp, không phải input người dùng), nhưng đổi hành vi `escapeHtml` dùng chung ảnh hưởng cả `chat.js` (ngoài phạm vi, không kiểm chứng được tác động) nên tôi không sửa hàm chung. Đề xuất: nếu cần vá, thêm escape quote cục bộ chỉ tại 3 điểm chèn thuộc tính này, không đổi `markdown.js`.
- **`pdf.js`, `sources.js` dùng `fetch()` thô thay vì `fetchJson()` dùng chung** (`static/js/pdf.js:57`, `static/js/sources.js:250,253`) — không phải lỗi, chỉ là không nhất quán tiện ích, rủi ro thấp/giá trị thấp nên không đổi để tránh đổi hành vi xử lý lỗi hiện có.
- **`.points-filter-tabs`** (`templates/views/utilities.html:213-219`) không có `role="tablist"`/`role="tab"` dù style class `.segmented`. Đây là bộ lọc (filter), không phải chuyển đổi panel/tab thật sự — để dạng nút thường là hợp lý, không bắt buộc phải mang ngữ nghĩa tab. Không sửa.

## Rà responsive — `lookup.css`

Đã đọc toàn bộ 3 breakpoint (1100/900/640px). Cấu trúc `.split`, `.penalty-card`/`.penalty-grid`, `.signs-grid`, `.safe-distance-grid`, `.metric-row` đều chuyển 1 cột hoặc gấp hàng hợp lý ở khổ hẹp, không có `min-width` cứng gây tràn ngang, không dùng `<table>` (toàn bộ bảng dữ liệu là div/grid nên tự vỡ dòng được). Không phát hiện tràn ngang hay bảng không cuộn được. Vùng chạm control chuẩn (`--control-height` 32px) đạt yêu cầu thực dụng của bộ token hiện tại; đã bổ sung `.hit-area` cho điểm duy nhất dưới ngưỡng thực sự nhỏ (`.btn-copy-clause`).

## Dead code `answer_reset`

Grep toàn bộ phạm vi CSS/JS/template của tôi cho `answer_reset`, `answer-reset`, `draft--superseded`, `trace__draft`: chỉ xuất hiện trong `chat.css` (ngoài phạm vi). Không có gì cần gỡ trong phần tôi sở hữu.

## Kiểm thử

- Khởi `uvicorn` cổng 8098, `curl` `/`, `/api/health`, `/api/penalties?limit=5`, và toàn bộ 5 tệp CSS + các JS đã sửa → tất cả 200.
- `node --check` cho mọi tệp JS đã sửa → không lỗi cú pháp.
- Đếm `{`/`}` khớp cho cả 5 tệp CSS.
- Đã tắt uvicorn (PID nền) trước khi kết thúc, cổng 8098 xác nhận trống. Không gọi `POST /api/ask`.

Status: DONE
Summary: Sửa 13 vi phạm thật (token hardcode, thiếu `aria-selected` đồng bộ tab, label-for trỏ sai phần tử không focus được, `aria-expanded` sai trạng thái ban đầu trên di động, style inline JS cho scroll-lock, bug hợp đồng `showToast` khiến toast luôn sai màu biến thể) trong đúng phạm vi sở hữu; server khởi động và phục vụ bình thường sau khi sửa, đã tắt sạch tiến trình nền.
Concerns/Blockers: 2 việc ngoài phạm vi cần chủ khác xử lý — (1) `docs/design-system.md` §3.2 và §4 mô tả sai so với code thật (`.field` pattern, route hash tiếng Anh vs tiếng Việt); (2) cân nhắc vá escape thuộc tính `data-copy`/`title` ở `law_formatter.js`/`penalty.js` nếu dữ liệu luật tương lai có thể chứa dấu ngoặc kép — hiện đánh giá rủi ro thấp nên chưa sửa.
