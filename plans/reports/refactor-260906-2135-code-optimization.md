# Tối ưu code — vòng 2

Ngày: 2026-09-06 21:35 · Tiếp nối `fix-260906-2105-agentic-ui-rewire.md`

## 1. Dọn lặp code do vòng 1 tạo ra (DRY)

`stream_agent()` có **3 khối lặp gần như giống hệt nhau** (đường tool_calls chuẩn, đường DSML thô,
đường chèn tra cứu bắt buộc) — mỗi khối ~8 dòng làm cùng việc: tạo mô tả, ghi step, phát `tool_call`,
thực thi, tóm tắt, gom nguồn, phát `tool_result`.

Đã tách thành helper, dùng `yield from` để giữ nguyên tính streaming:

| Helper mới | Vai trò |
|---|---|
| `_run_tool_step()` | Một lệnh gọi công cụ trọn vẹn — thay cho cả 3 khối lặp |
| `_consume_stream()` | Đọc stream, phát token, gom tool call — thay 2 chỗ đọc stream |
| `_build_sources()` | Khử trùng lặp + gắn tiêu đề nguồn trích dẫn |
| `_parse_tool_arguments()` | Giải mã JSON tham số, chịu được JSON hỏng do mô hình sinh |
| `_fail()` | Kết thúc sớm chuẩn hoá: luôn phát `error` rồi `done` |
| `_RunState` (dataclass) | Gom `agent_steps` + `cited_articles` + `tool_cache` |
| `_event()` (module-level) | Đưa ra ngoài closure để helper dùng chung |

**Kết quả:** `stream_agent` từ ~230 → **143 dòng**; không method nào vượt 35 dòng ngoài nó.

## 2. Sửa lỗi chất lượng: nguồn trích dẫn bị nhiễu

`_collect_cited_articles()` cũ quét regex `Điều\s+(\d+)` trên **toàn bộ** nội dung công cụ trả về.
Thân một Điều luật tham chiếu chéo rất nhiều Điều khác → chip nguồn hiện cả những Điều không liên
quan tới câu hỏi.

Nay chỉ đọc phần tiêu đề kết quả:
- `keyword_search` / `semantic_search`: dòng `📖 Điều N.`
- `penalty_lookup`: chỉ dòng `📜 Căn cứ Luật 36/2024/QH15:`
- `get_article`: lấy thẳng từ tham số

## 3. Sửa lỗi chất lượng: câu hỏi nối tiếp mất ngữ cảnh

Câu kiểu *"Vậy còn xe máy thì sao?"* được đưa nguyên văn vào `semantic_search` → truy vấn vô nghĩa.
Nay ghép thêm câu hỏi trước đó của người dùng làm ngữ cảnh.

Đo thực tế cùng một kịch bản:

| | Trước | Sau |
|---|---|---|
| Truy vấn tra cứu | `"Vậy còn xe máy thì sao?"` | `"Ô tô uống rượu phạt bao nhiêu tiền? Vậy còn xe máy thì sao?"` |
| Nguồn trích dẫn | `[33, 2, 42]` (Điều 2 = định nghĩa, Điều 42 = kiểm định khí thải — nhiễu) | `[9, 59, 58]` (đúng trọng tâm nồng độ cồn & GPLX) |

## 4. Dọn dẹp kho mã

- **Xoá** `lextraffic_ai_desktop.html` (588 KB) và `README.html` — prototype tĩnh, không còn nối vào
  launcher. Dự án không dùng git nên đã sao lưu trước khi xoá vào:
  `…\74acf854-…\scratchpad\backup-prototype\` (còn trong phiên làm việc này).
- **Cập nhật `.env.example`** khớp model thực tế (`nvidia/nemotron-3.5-lightning` /
  `minimax/minimax-m2.7:free`), thêm cảnh báo: `LLM_MODEL` bắt buộc hỗ trợ function calling; đổi
  `EMBEDDING_MODEL` phải chạy lại `build_hierarchical_index.py` cho khớp số chiều vector.
- **README** thay ghi chú về file đã xoá bằng ràng buộc cấu hình model.

## 5. Kiểm chứng (chạy thật sau refactor)

| Kiểm thử | Kết quả |
|---|---|
| Hỏi mức phạt | 1 `penalty_lookup` → nguồn `[9, 58]` · 21,7s |
| Tình huống đời thường | `semantic_search` → `get_article(31)` → trả lời · 7,3s |
| Hỏi nối tiếp | Ghép ngữ cảnh đúng, nguồn `[9, 59, 58]` |
| Trình duyệt — bảng Markdown | 1 `<table>`, 0 dấu `\|` thừa, 0 rò rỉ tên tool, 0 lỗi console |
| Trình duyệt — hỏi nối tiếp + nút reset | 2 câu trả lời, xoá sạch đúng, 0 lỗi console |
| CLI `scripts/chat.py` | Chạy nguyên vẹn · 4,35s |
| `compileall` + `node --check` | Sạch, không import thừa |

Server test chạy ở cổng 8099 rồi dừng hẳn, không đụng app đang chạy của bạn ở 8080.

## 6. Việc đã tự khép lại

Cổng 8080: tiến trình cũ (PID 27108) đã tự tắt. Hiện cổng do `python main.py` khởi động lúc
21:35:18 chiếm — tức chính bạn đang chạy app. Không đụng tới.

## 7. Còn lại một quyết định

Đề xuất #4 vòng trước (dựng lại bảng tính tiền phạt dựa trên `penalty_lookup`) **chưa làm** — đây là
thêm tính năng chứ không phải tối ưu code, và nó mâu thuẫn trực tiếp với yêu cầu tối giản giao diện.
Agent hiện đã trả lời được mọi câu hỏi mức phạt bằng dữ liệu thật. Cần dựng lại không?
