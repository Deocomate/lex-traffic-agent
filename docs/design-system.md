# 📐 Hệ Thiết Kế LexTraffic AI (Design System Specification)

> **Phiên bản:** 2.0 (Tháng 09/2026)  
> **Nguyên tắc chi phối:** *Giảm số quyết định thị giác, tăng chất lượng của những quyết định còn lại.*  
> **Kiến trúc nền tảng:** Vanilla CSS phân tầng, 100% Token-based, WAI-ARIA Accessible, Light Mode Minimalist.

---

## 1. Triết Lý & Kiến Trúc Nền Tảng

LexTraffic AI là ứng dụng trợ lý pháp lý AI chuyên sâu về Luật Trật tự, An toàn giao thông đường bộ Việt Nam. Giao diện được thiết kế với mục tiêu mang lại trải nghiệm **chính xác, tinh tế, đĩnh đạc và tối giản tuyệt đối** cho người dùng khi tra cứu và làm việc với các văn bản pháp lý.

### 1.1 Nguyên Tắc Cốt Lõi
1. **Nguồn sự thật duy nhất (Single Source of Truth):** Toàn bộ màu sắc, khoảng cách, font chữ, độ bo góc, bóng đổ và thời gian chuyển động được quản trị tập trung tại `static/css/tokens.css`. Tuyệt đối không hardcode mã màu hex hoặc kích thước tự do ở các tệp CSS khác hoặc trong JavaScript.
2. **Không Style Inline:** Không nhúng thuộc tính `style="..."` trong bất kỳ template HTML hay mã JavaScript nào. Mọi trạng thái hiển thị được điều khiển thông qua class và thuộc tính ngữ nghĩa (`data-*`, `aria-*`).
3. **Control biểu mẫu tự dựng:** 100% control lựa chọn (`<select>`) sử dụng component tùy biến theo chuẩn WAI-ARIA Listbox để đảm bảo tính đồng nhất trên mọi nền tảng hệ điều hành.
4. **Chuẩn Tiếp cận WCAG 2.1 AA:** Mọi cặp màu văn bản/nền đều đạt tỷ lệ tương phản ≥ 4.5:1 (chữ thường) và ≥ 3:1 (chữ lớn, ranh giới control); hỗ trợ điều hướng bàn phím hoàn chỉnh và có `focus-visible`.

### 1.2 Cấu Trúc 6 Tầng CSS Phân Tầng

```
static/css/
  ├── tokens.css       [Tầng 0] Nguồn sự thật toàn cục: biến :root màu, chữ, radius, space, shadow
  ├── base.css         [Tầng 1] Reset trình duyệt, typography cơ bản, tiêu chuẩn focus, thanh cuộn
  ├── components.css   [Tầng 2] Thư viện 14 nhóm component tái sử dụng toàn hệ thống
  ├── shell.css        [Tầng 3] Khung ứng dụng: sidebar, topbar, responsive drawer, command palette
  ├── chat.css         [Tầng 4] Surface Chat: luồng hội thoại, Agent trace timeline, nguồn trích dẫn
  └── lookup.css       [Tầng 4] Surface Tra cứu: Bộ luật, Mức phạt, Tiện ích, PDF viewer, Hệ thống
```

---

## 2. Thang Design Tokens (`tokens.css`)

Ngôn ngữ thiết kế: **neo-grotesque product**. Giấy nguội chroma-0, mực gần đen,
MỘT màu nhấn cobalt, và **đường kẻ 1px là chiến lược phân tách duy nhất** — đổ
bóng chỉ dành cho lớp thật sự nổi lên trên mặt phẳng trang (dropdown, modal,
palette, toast), không bao giờ dùng trên thẻ tĩnh.

Mọi con số và mọi căn cứ pháp lý đều đi bằng chữ đơn cách, vì bản thân văn bản
luật đã là thứ được đánh số và neo theo căn cứ (Điều → Khoản → Điểm).

### 2.1 Bảng Màu (Color Tokens)

#### Thang trung tính
Một thang 12 bậc ám lạnh rất nhẹ (`--gray-50` … `--gray-950`) là gốc của mọi bề
mặt và mọi bậc mực. Không trộn xám ấm với xám lạnh ở bất kỳ đâu.

#### Nền & Bề mặt (Surfaces)
| Token | Giá trị | Ứng dụng |
| :--- | :--- | :--- |
| `--surface-page` | `#fdfdfe` | Khung nội dung chính, vùng đọc, thẻ |
| `--surface-raised` | `#f8f8fa` | Sidebar, thanh công cụ, header bảng |
| `--surface-sunken` | `#f1f1f4` | Ô nhập liệu, khối mã lệnh, vùng lõm |
| `--surface-overlay` | `#fdfdfe` | Dropdown, modal, command palette |
| `--surface-inverse` | `#0d0d11` | Toast, badge tương phản cao |

#### Màu mực (Inks)
Bốn bậc dùng cho chữ. **Cả bốn đều đạt WCAG AA cho chữ thường**; riêng
`--ink-ghost` không đạt và chỉ được dùng cho thứ trang trí, không bao giờ cho chữ
mang thông tin.

| Token | Giá trị | Tương phản trên giấy | Ứng dụng |
| :--- | :--- | :--- | :--- |
| `--ink-strong` | `#0d0d11` | 17.9:1 | Tiêu đề, số liệu trọng yếu |
| `--ink-base` | `#4d4d56` | 8.3:1 | Văn bản thường, thân điều luật |
| `--ink-muted` | `#5c5c66` | 6.5:1 | Nhãn phụ, mô tả |
| `--ink-faint` | `#6e6e78` | 4.7:1 | Metadata, placeholder |
| `--ink-ghost` | `#b8b8c0` | 2.2:1 | **Chỉ trang trí** — không dùng cho chữ |

#### Đường kẻ (Hairlines)
| Token | Giá trị | Ứng dụng |
| :--- | :--- | :--- |
| `--line-subtle` | `#ebebee` | Kẻ trong panel, giữa hàng danh sách |
| `--line-base` | `#e3e3e7` | Ranh giới thẻ, viền control |
| `--line-strong` | `#b8b8c0` | Viền control khi hover, nhấn mạnh |

#### Màu nhấn duy nhất (Cobalt)
| Token | Giá trị | Ứng dụng |
| :--- | :--- | :--- |
| `--accent` | `#0068e0` | Nút chính, vòng tiêu điểm, chỉ báo mục đang xem. 5.0:1 cả hai chiều |
| `--accent-hover` | `#0055ba` | Trạng thái hover của nút chính |
| `--accent-soft` | `#eef4fe` | Nền mục đang chọn, nút đang chạy trên đường ray |
| `--accent-line` | `#b9d5fb` | Viền của vùng `--accent-soft` |
| `--accent-ink` | `#0a4ba3` | Chữ trên nền `--accent-soft` (7.6:1) |

Màu nhấn chiếm dưới 10% bề mặt và **không bao giờ xuất hiện trên phần tử không
hoạt động** — nó có tác dụng chính vì nó hiếm.

#### Màu ngữ nghĩa (chỉ cho dữ liệu pháp lý)
Không dùng làm mảng nền lớn. Mỗi màu đi kèm một nền nhạt và một đường viền.

| Nhóm | Chữ | Nền | Viền | Ứng dụng |
| :--- | :--- | :--- | :--- | :--- |
| Mức phạt tiền | `--data-fine: #9a5b06` (5.4:1) | `--data-fine-bg` | `--data-fine-line` | Số tiền phạt |
| Nghiêm trọng | `--data-severe: #b81238` (6.5:1) | `--data-severe-bg` | `--data-severe-line` | Tước bằng, tịch thu, trừ từ 6 điểm |
| Hợp lệ | `--data-safe: #046c50` (6.4:1) | `--data-safe-bg` | `--data-safe-line` | Sẵn sàng, đã xác minh, hiệu lực |

---

### 2.2 Chữ (Typography)

Hai họ font, ghép trên trục tương phản grotesque ↔ đơn cách:

- **Giao diện & văn bản luật:** `Geist` (Google Fonts, có subset `vietnamese`).
- **Số liệu, mã hiệu, căn cứ pháp lý, thời lượng:** `Geist Mono`.

Thang cố định theo `rem`, tỉ lệ khoảng 1.15 — đúng với product register. Thang
chữ giãn rộng chỉ hợp với trang tiếp thị, không hợp với công cụ tra cứu dày đặc.

| Token | Kích thước | Ứng dụng |
| :--- | :--- | :--- |
| `--text-2xs` | 11px | Nhãn viết hoa, badge, thời lượng |
| `--text-xs` | 12px | Metadata, căn cứ pháp lý, chú giải |
| `--text-sm` | 13px | Nhãn control, nút, hàng bảng |
| `--text-base` | 14px | Nền tảng giao diện |
| `--text-read` | 15px | **Thân điều luật & câu trả lời của Agent** |
| `--text-md` | 17px | Tiêu đề thẻ, tiêu đề khu vực |
| `--text-lg` | 21px | Tiêu đề trang |
| `--text-xl` | 28px | Số liệu lớn |
| `--text-2xl` | 36px | Tiêu đề trạng thái rỗng |

Chiều cao dòng: `--leading-tight: 1.2` (tiêu đề), `--leading-base: 1.5` (giao
diện), `--leading-legal: 1.7` (thân điều luật). `font-variant-numeric:
tabular-nums` bật ở cấp `body` để mọi cột số so sánh được theo hàng dọc.

Ở khổ từ 768px trở xuống, mọi ô nhập liệu tăng lên `1rem` để trình duyệt di động
không tự phóng to trang khi người dùng chạm vào.

---

### 2.3 Khoảng cách, bo góc, độ nổi & chuyển động

```css
/* Khoảng cách — thang 4px, 8 bậc. Không có giá trị nào ngoài thang. */
--space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
--space-5: 24px;  --space-6: 32px;  --space-7: 48px;  --space-8: 64px;

/* Bo góc — MỘT hệ duy nhất cho toàn trang */
--radius-control: 6px;    /* Nút, ô nhập, select, badge */
--radius-panel:   8px;    /* Thẻ, panel, dropdown */
--radius-overlay: 12px;   /* Modal, palette, ô soạn chat */
--radius-full:    999px;  /* Pill, chấm trạng thái */

/* Độ nổi — CHỈ cho lớp nổi thật sự; bóng nhiều tầng, ám theo màu nền */
--elevation-overlay   /* Dropdown, toast */
--elevation-modal     /* Modal, command palette */

/* Chuyển động — quy tắc 120/180/240 */
--motion-fast: 120ms;   /* Phản hồi tức thì: nhấn, bật/tắt */
--motion-base: 180ms;   /* Đổi trạng thái: hover, mở menu */
--motion-slow: 240ms;   /* Đổi bố cục: drawer, accordion */
--motion-ease: cubic-bezier(0.25, 1, 0.5, 1);   /* ease-out-quart */

/* Tiêu điểm — vòng 2px nền + 4px accent, nằm ngoài phần tử */
--focus-ring: 0 0 0 2px var(--surface-page), 0 0 0 4px var(--accent);
```

Đây là giao diện công cụ, không phải trang tiếp thị: **không có màn dàn dựng
chuyển động lúc tải trang**. Chuyển động chỉ tồn tại để truyền đạt trạng thái, và
mọi hoạt ảnh đều có nhánh thay thế dưới `prefers-reduced-motion: reduce`.

### 2.4 Kích thước khung & control

| Token | Giá trị | Ghi chú |
| :--- | :--- | :--- |
| `--control-height` | 32px | Chiều cao chuẩn của nút, ô nhập, select |
| `--control-height-sm` | 26px | Chip, pill, nút phụ |
| `--topbar-height` | 52px | |
| `--sidebar-width` | 236px | Thu gọn còn `--sidebar-collapsed: 56px` |
| `--content-max` | 1120px | Bề rộng tối đa khu vực tra cứu |
| `--thread-max` | 768px | Cột hội thoại — giữ measure khoảng 70ch |
| `--reading-max` | 720px | Cột đọc văn bản luật |

---

## 3. Danh Mục Component Chuẩn (`components.css`)

### 3.1 Nút Bấm (`.btn`)
Hỗ trợ các biến thể ngữ nghĩa: `.btn--primary`, `.btn--secondary`, `.btn--ghost`, `.btn--sm`, `.btn--icon`.

```html
<!-- Nút Chính (Primary) -->
<button type="button" class="btn btn--primary">
  <span class="btn__icon"><!-- SVG Icon --></span>
  <span>Gửi câu hỏi</span>
</button>

<!-- Nút Phụ (Secondary) -->
<button type="button" class="btn btn--secondary">Sao chép</button>

<!-- Nút Ghost (Chỉ có viền khi hover) -->
<button type="button" class="btn btn--ghost btn--icon" aria-label="Đóng">
  <!-- SVG Icon -->
</button>
```

### 3.2 Trường Nhập Dữ Liệu (`.field-wrap`, `.field-label`, `.field`)

`.field` là class đặt **trực tiếp trên chính ô nhập liệu**, không phải khối bao ngoài. Khối bao là
`.field-wrap`, nhãn là `.field-label`. (Bản 2.0 của tài liệu này từng mô tả một cấu trúc BEM
`.field > .field__control > .input` chưa bao giờ tồn tại trong mã — đã sửa lại theo đúng
`static/css/components.css` mục 3.)

```html
<div class="field-wrap">
  <label class="field-label" for="law-search">Tìm kiếm điều luật</label>
  <input type="search" id="law-search" class="field" placeholder="Nhập từ khóa hoặc số điều..." />
</div>
```

### 3.3 Custom Select Dropdown (WAI-ARIA Combobox + Listbox)

Dựng bởi `static/js/ui/select.js`. **Không có `<select>` HTML thô nào trong
`templates/`** — kiểm chứng bằng cổng lint ở mục 5.

Template chỉ cần một phần tử neo rỗng; toàn bộ phần còn lại do JS dựng:

```html
<div id="penalty-vehicle" class="select" data-select></div>
```

```javascript
import { createSelect } from './ui/select.js';

const vehicleSelect = createSelect(document.getElementById('penalty-vehicle'), {
  options: [{ value: '', label: 'Tất cả phương tiện' }, ...],
  value: '',
  ariaLabel: 'Lọc theo loại phương tiện',
  onChange: (value, option) => render()
});
```

Hành vi bắt buộc của component:

| Khía cạnh | Cách xử lý |
| :--- | :--- |
| Cắt bởi `overflow` | Danh sách gắn vào `<body>` và định vị `position: fixed`, nên không bao giờ bị phần tử cha cắt |
| Định vị | Bám theo trigger, kẹp trong viewport, tự lật lên trên khi phía dưới không đủ chỗ, `max-height` theo chỗ trống thật |
| Danh sách dài | Từ 10 mục trở lên tự hiện ô lọc; lọc bỏ dấu tiếng Việt (gõ `toc do` ra `Tốc độ`) |
| Bàn phím | ↑ ↓, Home/End, Enter, Space, Esc, Tab; gõ để nhảy (500ms) khi không có ô lọc |
| ARIA | `role="combobox"` trên trigger, `aria-activedescendant` **đặt trên trigger** (không phải trên listbox), `aria-selected` trên từng mục |
| Di động (≤ 640px) | Chuyển thành bottom sheet, mỗi mục cao ≥ 44px, ô lọc 16px |
| Điều hướng SPA | Tự đóng theo `hashchange` — danh sách sống ở `<body>` nên nếu không đóng sẽ thành dropdown mồ côi trôi trên màn hình |
| Tương thích ngược | `mountEl.value` đọc/ghi được; component phát sự kiện `change` chuẩn có `bubbles` |

### 3.4 Modal Hộp Thoại Có Bẫy Tiêu Điểm (`ui/modal.js`)
Tuân thủ đầy đủ chuẩn WCAG dialog: bẫy Tab bàn phím, đóng bằng `Esc`, khôi phục focus về nút kích hoạt khi đóng.

```html
<div class="modal" id="sign-detail-modal" role="dialog" aria-modal="true" aria-labelledby="modal-sign-title" hidden>
  <div class="modal__backdrop" data-modal-close></div>
  <div class="modal__dialog">
    <header class="modal__header">
      <h3 class="modal__title" id="modal-sign-title">Chi tiết biển báo</h3>
      <button type="button" class="btn btn--ghost btn--icon modal__close" data-modal-close aria-label="Đóng hộp thoại">
        <!-- SVG Close -->
      </button>
    </header>
    <div class="modal__body" id="modal-sign-content">
      <!-- Nội dung động -->
    </div>
  </div>
</div>
```

API điều khiển:
```javascript
window.ModalController.open('sign-detail-modal');
window.ModalController.close('sign-detail-modal');
```

### 3.5 Thông Báo Toast (`ui/toast.js`)
```javascript
window.showToast('Đã sao chép nội dung Điều luật', 'success');
window.showToast('Không tìm thấy dữ liệu', 'warning');
window.showToast('Lỗi kết nối máy chủ', 'error');
```

### 3.6 Segmented Controls & Tabs
```html
<div class="segmented" role="tablist">
  <button type="button" class="segmented__item active" role="tab" aria-selected="true" data-tab="tab-1">Luật 36/2024</button>
  <button type="button" class="segmented__item" role="tab" aria-selected="false" data-tab="tab-2">Nghị định 168</button>
</div>
```

### 3.7 Badges

Mọi biến thể được dùng trong JS đều phải có mặt trong `components.css`. Danh sách
đầy đủ hiện tại:

| Class | Màu | Ứng dụng |
| :--- | :--- | :--- |
| `.badge--neutral` | Trung tính | Điều khoản, căn cứ, thẩm quyền, nhãn phương tiện |
| `.badge--primary` / `.badge--sky` | Cobalt nhạt | Nguồn trích dẫn là điều luật |
| `.badge--fine` / `.badge--amber` | `--data-fine` | Mức phạt tiền |
| `.badge--severe` / `.badge--rose` | `--data-severe` | Tước GPLX, tịch thu, trừ điểm, hành vi nghiêm cấm |
| `.badge--safe` / `.badge--emerald` | `--data-safe` | Sẵn sàng, hiệu lực, đã xác minh |
| `.badge--xs` | — | Bổ trợ kích thước, ghép với biến thể màu |

Badge chế tài xuất hiện **giữa dòng văn bản luật** (do `law_formatter.js` sinh ra)
được ghi đè để giữ nhịp đọc: không viết hoa, không đổi cỡ chữ, `vertical-align:
baseline`.

---

### 3.8 Đường Ray Suy Luận Của Agent (`agent-trace.js` + `chat.css`)

Đây là phần tử đặc trưng của giao diện. Hình thức của nó lấy từ chính nội dung:
văn bản luật là thứ được đánh số và phân cấp, nên tiến trình tra cứu cũng được
trình bày như một đường ray dọc có các nút neo vào.

Cấu trúc một bước trên ray:

```
● Tra mức phạt            NĐ 168/2024                          412ms
  [hành vi: nồng độ cồn] [phương tiện: Ô tô]
  12  Tìm thấy 12 hành vi vi phạm liên quan nồng độ cồn với ô tô
```

| Thành phần | Class | Nội dung |
| :--- | :--- | :--- |
| Nút trên ray | `.trace__node` | Spinner khi đang chạy → dấu tích khi xong; đổi màu theo trạng thái |
| Tên công cụ | `.trace__tool` | Nhãn tiếng Việt của 1 trong 7 công cụ pháp lý |
| Căn cứ công cụ | `.trace__source` | Văn bản mà công cụ đó tra (ẩn ở khổ hẹp) |
| Tham số tra cứu | `.trace__arg` | Cặp khoá/giá trị thật Agent gửi đi, tên khoá dịch sang tiếng Việt |
| Kết quả | `.trace__result-count` + `.trace__result-text` | Số lượng tách riêng đứng trước câu tóm tắt |
| Thời lượng | `.trace__duration` | Chữ đơn cách, **đếm thật theo thời gian thực** trong lúc bước đang chạy |

Hàng đầu (`.trace__header`) mang trạng thái tổng, số bước và một đồng hồ chạy
100ms/lần. Khi nhận sự kiện `done`, ray tự thu gọn để nhường chỗ cho câu trả lời
nhưng vẫn mở lại được.

Các sự kiện SSE được tiêu thụ: `start`, `turn_start`, `tool_call`, `tool_result`,
`model_fallback`, `synthesizing`, `verifying`, `verified`, `warning`, `token`,
`answer_reset`, `answer_commit`, `done`, `error`. Backend gắn emoji dẫn đầu vào
`message`; giao diện bóc emoji đó đi và tự vẽ icon SVG tương ứng.

#### Hợp đồng bản nháp: `token.phase`

Mô hình thường viết vài câu cân nhắc rồi mới quyết định gọi công cụ. Backend chỉ
biết văn bản đó là lời dẫn hay câu trả lời **sau khi stream đã kết thúc**. Nếu
giao diện đổ thẳng token vào ô câu trả lời, người dùng sẽ thấy một câu trả lời
hiện ra rồi biến mất khi Agent quay lại tra cứu tiếp.

Vì vậy mọi sự kiện `token` đều mang trường `phase`:

| `phase` | Nguồn phát | Giao diện phải làm gì |
| :--- | :--- | :--- |
| `"draft"` | Vòng lặp suy luận (`_consume_stream` mặc định) | Đổ vào khối `.trace__draft` trên đường ray, **tuyệt đối không** vào `.answer` |
| `"answer"` | Lượt tổng hợp cuối, đã cấm gọi công cụ | Stream thẳng vào `.answer` |

Hai sự kiện chốt trạng thái của bản nháp:

- **`answer_reset`** — bản nháp chỉ là lời dẫn, Agent sắp gọi công cụ. Khối nháp
  chuyển sang `.trace__draft--superseded` và ở lại ray như một dấu vết suy nghĩ.
  Không xoá đi: người dùng vừa đọc nó, làm nó biến mất là gây hụt hẫng.
- **`answer_commit`** — bản nháp chính là câu trả lời cuối. Khối nháp bị gỡ khỏi
  ray và nội dung được nâng lên `.answer` để không hiện hai lần.

**Khi thêm bất kỳ nhánh phát token mới nào ở backend, bắt buộc phải khai báo
`phase`.** Bỏ sót sẽ khiến lỗi "trả lời trước khi suy luận xong rồi tự ẩn đi"
quay lại, và đây là lỗi không có thông báo nào báo cho biết.

#### Bảo đảm luồng luôn có kết cục

Đường ray chạy một `setInterval` để đếm thời gian, và chỉ dừng khi nhận `done`
hoặc `error`. Nếu luồng SSE đứt mà không có sự kiện kết thúc, spinner sẽ quay
vĩnh viễn. Hai lớp bảo vệ:

- `app/server.py` (hàm `stream_agent_events()`) bọc toàn bộ vòng lặp `astream_agent` trong
  `try/except`; mọi ngoại lệ đều in stack trace ra console **và** phát `error` +
  `done` xuống trình duyệt.
- `chat.js` gọi `trace.finalize()` sau khi đọc hết luồng, phòng trường hợp kết
  nối đứt hẳn (mất mạng, máy chủ bị tắt) nên không sự kiện nào tới được.

`sources` truyền cho `build_unknown_answer` chứa **ba dạng** (`law` / `decree` /
`sign`) và chỉ dạng `law` có `article_number`; luôn đọc bằng `.get()` và phân
nhánh theo `source_type`.

---

### 3.9 Bộ Dựng Markdown (`markdown.js`)

Câu trả lời của Agent là Markdown do mô hình sinh ra, dựng bằng `renderMarkdown()`.
Tự viết vì dự án không có bước build và cần hai khối đặc thù: thẻ "Căn cứ pháp lý
trích dẫn" và ảnh biển báo chèn giữa văn bản.

**Nguyên tắc chi phối: bám đúng thứ mô hình THẬT SỰ sinh ra, không phải Markdown
chuẩn giả định.** Mô hình phân tách khối bằng một dòng trống, thường là không có
dòng trống nào: `---` dính ngay trên `### Căn cứ pháp lý`, tiêu đề dính ngay trên
danh sách, đoạn văn dính ngay trên bảng.

Vì vậy bộ dựng quét theo **từng dòng**, mỗi loại khối tự ăn đúng số dòng của nó
rồi trả về chỉ số dòng kế tiếp. Không được quay lại kiểu "cắt theo dòng trống rồi
đòi mỗi khối thuần một loại" — kiểu đó khiến mọi khối lẫn lộn rơi xuống nhánh
đoạn văn và hiện ký hiệu Markdown thô ra màn hình.

| Khối | Nhận diện | Ghi chú |
| :--- | :--- | :--- |
| Khối mã | ` ``` ` hoặc `~~~` | Giữ nguyên văn, không áp định dạng trong dòng |
| Đường kẻ | `---`, `***`, `___` | |
| Tiêu đề | `#` … `######` | Tối đa `h4` |
| Thẻ căn cứ | tiêu đề khớp `Căn cứ pháp lý` (kể cả có emoji) | Thân đưa ngược vào `renderBlocks` nên giữ được danh sách lồng |
| Bảng | các dòng liên tiếp mở đầu `\|` | Dưới 2 hàng thì coi là đoạn văn |
| Trích dẫn | `>` (đã escape thành `&gt;`) | |
| Danh sách | `-`, `*`, `•`, `1.`, `1)` | Lồng nhau theo mức thụt đầu dòng; gộp dòng nối tiếp |
| Đoạn văn | còn lại | Dừng khi gặp dòng trống hoặc một khối khác mở ra |

Dấu `*` và `**` còn sót lại sau khi đã ghép hết cặp đều bị bỏ đi: chúng là do mô
hình mở đậm/nghiêng mà không đóng (cụm vắt qua ranh giới ô bảng, hoặc câu trả lời
bị cắt vì chạm giới hạn token). Dấu sao giữa hai chữ số được giữ để không phá
biểu thức như `5*3`.

---

## 4. Sơ Đồ Định Tuyến URL (Client-Side Hash Routing)

LexTraffic AI sử dụng hệ thống Client-Side Router (`static/js/router.js`) dựa trên chuẩn `location.hash`. Mọi trạng thái tra cứu đều có URL định danh riêng, hỗ trợ sao chép liên kết, phím Back/Forward và F5 tải lại trang không mất ngữ cảnh.

| URL Hash | Tên View | Mô Tả & Trạng Thái Tham Số |
| :--- | :--- | :--- |
| `#/chat` | Chat | Giao diện hội thoại mặc định với Agent |
| `#/chat/<sessionId>` | Chat | Mở lại phiên hội thoại đã lưu với ID cụ thể |
| `#/luat` | Bộ luật | Xem danh mục 6 văn bản pháp luật giao thông |
| `#/luat/<docId>` | Bộ luật | Đọc văn bản luật cụ thể (ví dụ: `#/luat/01_luat_36_2024_qh15`) |
| `#/luat/<docId>/<articleNumber>` | Bộ luật | Cuộn và làm nổi bật Điều luật |
| `#/muc-phat` | Mức phạt | Tra cứu danh mục xử phạt vi phạm hành chính |
| `#/tien-ich` | Tiện ích | Trang tổng quan tiện ích (biển báo, vạch kẻ, tốc độ) |
| `#/van-ban` | Văn bản | Trình đọc PDF văn bản gốc |
| `#/he-thong` | Hệ thống | Số liệu quan trắc tổng hợp (đọc `GET /api/trace/summary`) |

**Định tuyến dùng tiếng Việt không dấu.** Bản 2.0 của tài liệu này liệt kê `#/law`, `#/penalties`,
`#/utilities` — những đường dẫn đó chưa bao giờ tồn tại. Danh sách trên lấy trực tiếp từ thuộc tính
`data-route` trong `templates/` và `static/js/router.js`.

---

## 5. Quy Tắc Mở Rộng & Bảo Trì Hệ Thống

Để giữ vững tính nhất quán và ngăn chặn nợ kỹ thuật tái phát, đội ngũ phát triển tuân thủ nghiêm ngặt các quy tắc sau:

1. **Phân định phạm vi CSS:**
   - Nếu component mang tính chất dùng chung cho ≥ 2 khu vực: Khai báo vào `components.css`.
   - Nếu style thuộc về dòng thời gian Agent, ô soạn thảo chat hoặc khay trích dẫn nguồn: Khai báo vào `chat.css`.
   - Nếu style thuộc về trình đọc luật, bảng mức phạt, lưới tiện ích hoặc viewer: Khai báo vào `lookup.css`.
   - Tuyệt đối không thêm tệp CSS mới mà không thông qua đánh giá kiến trúc.
2. **Không ghi đè (override) màu bằng giá trị thô:** Bất kỳ thuộc tính `color`, `background-color`, `border-color` nào cũng phải sử dụng cú pháp `var(--tên-token)`.
3. **Biểu tượng (Icons):** 100% biểu tượng giao diện sử dụng các hàm helper trong `static/js/ui/icons.js` (SVG nét đơn 1.5px, 20px, kế thừa `currentColor`). Không đưa thêm emoji vào các nút điều hướng hoặc thẻ tab.
4. **Kiểm tra tự động trước khi commit (Linter Gates):**
   ```bash
   # 1. Không còn thẻ <select> HTML thô trong template
   grep -rn "<select" templates/

   # 2. Không có mã màu hex nào ngoài tokens.css
   grep -rn "#[0-9a-fA-F]\{3,8\}" static/css/ | grep -v tokens.css

   # 3. Không dùng transition: all (chặn hoạt ảnh trên thuộc tính gây reflow)
   grep -rn "transition: all" static/css/

   # 4. Không còn emoji trong giao diện (emoji chỉ được phép nằm trong dữ liệu luật)
   grep -rnoP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]" static/js/ templates/
   ```

5. **Mọi class dựng bằng JS phải có định nghĩa trong CSS.** Đây là nguồn hồi quy
   thị giác âm thầm nguy hiểm nhất của dự án: JS đổi tên class, giao diện mất
   style mà không có lỗi nào được ném ra. Trước khi hợp nhất, đối chiếu tập class
   xuất hiện trong `static/js/` và `templates/` với tập selector khai báo trong
   `static/css/` và bảo đảm hiệu số bằng rỗng.
