# Nối UI web vào Agent thật + tối giản giao diện

Ngày: 2026-09-06 · Phạm vi: `src/`, `web/`, `main.py`, `README.md`

## 1. Nguyên nhân gốc: UI không hề gọi AI

`lextraffic_ai_desktop.html` (8.726 dòng) **không chứa một lệnh `fetch`/`XMLHttpRequest` nào**.

- `matchLegalQA()` (dòng 5551) là chuỗi `if/else` so khớp từ khóa với hằng số
  `LEGAL_QA_DATABASE` — các hồ sơ pháp lý viết tay sẵn — và rơi về một "dossier" chung chung
  cho mọi câu hỏi lạ.
- `main.py --ui` chỉ chạy `SimpleHTTPRequestHandler` phục vụ file tĩnh, không có API.
- Kết luận: engine Agentic trong `src/agentic_rag.py` chạy đúng, nhưng **chưa từng được UI gọi tới**.

Phụ: `app.py` (Streamlit) là đường duy nhất nối UI với Agent, nhưng `streamlit` không được cài
trong môi trường nên cũng không chạy được.

## 2. Đã sửa

### Nối UI với Agent thật
- **Mới `src/api_server.py`** (FastAPI): `POST /api/ask` phát luồng SSE gồm `start`,
  `turn_start`, `tool_call`, `tool_result`, `token`, `done`; `GET /api/article/{n}` trả toàn văn
  điều luật; `GET /api/health`.
- **Mới `web/`** (`index.html` + `app.css` + `app.js`): mọi câu trả lời đến từ Agent, không còn
  một câu trả lời dựng sẵn nào trong giao diện.

### Tối ưu Agentic (`src/agentic_rag.py`)
| Thay đổi | Lý do |
|---|---|
| Chuyển sang vòng lặp **streaming** (`stream_agent`) | Hiện tiến trình + từng đoạn câu trả lời theo thời gian thực |
| **Hỗ trợ lịch sử hội thoại** (6 lượt gần nhất) | Trước đây mỗi câu hỏi là một phiên rời rạc, không hỏi nối tiếp được |
| **Chèn tra cứu bắt buộc** khi Agent định trả lời chay | Chặn việc trả lời số tiền phạt/số Điều theo trí nhớ mô hình |
| **Trần 4 tool/lượt, 8 tool/phiên + cắt stream sớm** | Khắc phục lỗi lặp vô hạn phát hiện khi kiểm thử (xem mục 3) |
| **Cache theo (tool, tham số)** | Mô hình hỏi lại cùng truy vấn không tốn thêm chi phí |
| **Trích xuất nguồn** (`sources`) | UI hiện chip `Điều 9`, `Điều 58`… mở được toàn văn |
| **Lọc tên tool khỏi câu trả lời** | Mô hình hay viết "dựa trên `semantic_search`…" ra cho người dùng |
| `run_agent()` giữ nguyên chữ ký, bọc lại `stream_agent` | `scripts/chat.py` chạy nguyên vẹn, không phá hợp đồng công khai |

### Bổ sung công cụ (`src/tools/law_search_tools.py`)
- **`semantic_search` được hiện thực và đăng ký vào `TOOLS_SCHEMA`.** Trước đó docstring có mô tả
  công cụ này nhưng chỉ tồn tại `_ensure_vector_loaded()` chết — Agent chỉ có tìm kiếm từ khóa.
  Nay tái sử dụng `SOTALegalRAG.retrieve` (không nhân bản logic child→parent), tự suy giảm mềm về
  `keyword_search` nếu vector index/API lỗi.
- **`penalty_lookup` trả tối đa 2 nhóm phương tiện** thay vì 1. Trước đây câu hỏi không nêu rõ loại
  xe chỉ thấy khung phạt ô tô, không thấy xe máy.

### Tối giản giao diện
Từ 3 màn hình / ~65 hàm JS xuống **một màn hình**:

| Giữ lại | Đã bỏ |
|---|---|
| Dòng hội thoại | Màn hình dashboard hero + màn hình split-view |
| Bảng tiến trình Agent (tự thu gọn khi xong) | Bảng tính tiền phạt (slider, tile, checkbox) — vốn tính bằng số liệu hardcode |
| Chip nguồn trích dẫn mở toàn văn điều luật | Voice input, bookmark, trung tâm thông báo, lịch sử chat popover + modal |
| Ô nhập (Enter gửi, Shift+Enter xuống dòng) | Nút tỉ lệ chia 40/50/30/60, xuất PDF, in, chỉnh cỡ chữ, chọn nghị định |
| Nút "Trò chuyện mới" | |

Giao diện tự đổi màu theo chế độ sáng/tối của hệ điều hành.

### Dọn dẹp
- Xóa `app.py` (Streamlit) — trùng vai trò với web app mới và thư viện không được cài.
- Thêm `requirements.txt`.
- `main.py`: menu còn 3 lựa chọn (Web App / CLI / Benchmark); `--ui` nay là bí danh của `--web`.
- Cập nhật `README.md` đúng hiện trạng.

## 3. Lỗi phát hiện trong lúc kiểm thử

Bản sửa đầu tiên đặt `tool_choice="required"` ở lượt 1 để ép Agent tra cứu. Model
`nvidia/nemotron-3.5-lightning` **thoái hóa thành vòng lặp gọi tool vô hạn** — hơn 40 lệnh
`keyword_search` gần trùng nhau trong một tin nhắn, chạy quá 4 phút không dừng.

Đã thay bằng: `tool_choice="auto"` + chèn một bước `semantic_search` xác định khi Agent định trả
lời mà chưa tra cứu + trần số lệnh gọi + `max_tokens`. Vừa đảm bảo có căn cứ dữ liệu, vừa không
ép mô hình vào trạng thái thoái hóa.

## 4. Kiểm chứng

Chạy thật với `.env` hiện tại (`nvidia/nemotron-3.5-lightning`, embedding `google/gemini-embedding-2` 3072 chiều):

| Kiểm thử | Kết quả |
|---|---|
| `/api/health` | ok · 89 Điều · 5 tool |
| Hỏi mức phạt (SSE) | 1 `penalty_lookup` → 122 đoạn token → nguồn `[9, 58, 11]` |
| Tình huống đời thường ("chở con 5 tuổi ngồi trước xe máy") | Chuỗi 3 bước: `semantic_search` → `get_article(31)` → `penalty_lookup` |
| Hỏi nối tiếp ("Vậy còn xe máy thì sao?") | Giữ ngữ cảnh, kích hoạt đúng cơ chế chèn tra cứu bắt buộc |
| Trình duyệt (Playwright) | Không lỗi console; tiến trình live hiển thị đúng; chip nguồn mở toàn văn Điều 9 (5.994 ký tự) |
| Bảng Markdown | Render thành `<table>`, 0 dấu `|` thừa, 0 rò rỉ tên tool |
| Nút "Trò chuyện mới" | Xóa sạch hội thoại, hiện lại màn hình rỗng |
| `scripts/chat.py` (CLI) | Chạy nguyên vẹn — 2 tool, 7,27s |
| `python -m compileall` + `node --check` | Sạch |

Thời gian trả lời thực đo: 4,8s – 10,7s tùy số bước tra cứu.

## 5. Việc còn để lại cho bạn quyết định

- `lextraffic_ai_desktop.html` (588 KB) và `README.html` vẫn nằm trong thư mục gốc, không còn được
  nối vào launcher. Giữ để tham khảo thiết kế; xóa được nếu bạn muốn.
- Cổng `8080` đang bị một tiến trình có sẵn (PID 27108, không thuộc phiên làm việc này) chiếm giữ —
  web app tự nhảy sang `8081`. Bạn có thể tự dừng tiến trình đó nếu muốn dùng đúng cổng 8080.
- `.env.example` vẫn liệt kê bộ model cũ (`deepseek`, `gemini`), khác với `.env` thực tế
  (`nvidia/nemotron-3.5-lightning`). Cần cập nhật không?
- Bảng tính tiền phạt ở màn hình 3 cũ đã bị bỏ theo yêu cầu tối giản. Nếu bạn vẫn cần công cụ tính
  nhanh, nên dựng lại dựa trên `penalty_lookup` (dữ liệu thật) thay vì số liệu hardcode như bản cũ.
