# Phase 6 — Bộ nhớ đa lượt và cache ngữ nghĩa

Ngày: 2026-09-09 · Chế độ: `/ak:cook --auto` · Kế hoạch: `plans/260909-1320-langgraph-agent-harness/phase-06-memory-and-cache.md`

## Kết quả

Phase 6 hoàn tất. 162/162 test xanh. Toàn bộ 8 tiêu chí thành công đạt (một tiêu chí đạt kèm
ngoại lệ có chủ ý, xem mục "Hai tiêu chí xung đột" bên dưới).

Đo lại bằng `e2e_eval.py --adapter graph --quick 4`, chạy hai lần liên tiếp:

| | Lần 1 (cache rỗng) | Lần 2 (cache ấm) |
|---|---|---|
| Thời gian | 521.8s | **136.5s** (nhanh hơn 73.8%) |
| Tỉ lệ huỷ câu trả lời | 0.0% | 0.0% |
| Chính xác trích dẫn | 75.0% | 75.0% |
| Số liệu không có căn cứ | 0.0% | 0.0% |
| Từ chối đúng khi ngoài phạm vi | 100.0% | 100.0% |
| Trúng cache | — | 2/4 câu |

Mọi chỉ số chất lượng giống hệt. Hai câu **không** trúng cache có `answer_preview` khác nhau giữa
hai lần — đó là tính không tất định của LLM trên đường trượt cache, không phải cache trả nhầm: mọi
trường kiểm chứng (`citation_ok`, `has_ungrounded_figures`, `refusal_ok`, `verification_issues`,
`sources_count`) của cả bốn câu đều trùng khớp, và hai câu trúng cache trùng khớp đến từng ký tự.

## Ba lỗi thật đã phát hiện và sửa

**1. `langgraph-checkpoint-sqlite` 2.0.10 không chạy được với `langgraph-checkpoint` 4.2.0.**
Bản 2.x gọi `JsonPlusSerializer.dumps()`, API đã bị bỏ. Mọi lượt ghi checkpoint ném
`AttributeError`, làm hỏng 3 test SSE. Nâng lên `>=3.1,<4` và ghim lại trong `requirements.txt`
kèm lý do.

**2. Khoá cache dựng từ `route` thật thì cache không bao giờ trúng.**
Lần đo đầu tiên: 8 lượt tra cache, **0 lần trúng**, và lần chạy thứ hai còn *chậm hơn* 22%. Nguyên
nhân đo được trực tiếp — gọi router ba lần cho đúng một câu hỏi:

```
run1: vehicles=['o_to','xe_may']  key=97e82b7f...
run2: vehicles=['o_to','xe_may']  key=97e82b7f...
run3: vehicles=[]                 key=838e9476...
```

`route` là phép hợp giữa regex prior và LLM router, mà LLM router không tất định. Khoá vì thế
dao động theo từng lượt chạy. Đã chuyển sang dựng khoá từ **regex prior tất định**. Bất biến an
toàn không mất: regex vẫn cho `['o_to']` với "ô tô vượt đèn đỏ" và `['xe_may']` với "xe máy vượt
đèn đỏ", và `['law']` với "Luật 36" so với `['law','penalty']` với "Nghị định 168".

**3. Bộ eval đi vòng qua cache.**
`GraphAdapter` gọi thẳng `graph.invoke()` nên không bao giờ chạm tới cache — bước "chạy lại lần
hai" của kế hoạch sẽ không kiểm được gì. Đã cho nó đi qua `run_turn`, đúng đường mà máy chủ dùng.
Kéo theo: cache phải lưu thêm `tool_outputs`, nếu không bộ eval kết luận sai rằng câu trả lời từ
cache "không có căn cứ".

Ngoài ra: test đang đọc/ghi **tệp cache thật** của production, nên lần chạy suite thứ hai trúng
cache của lần thứ nhất và các test SSE thấy chuỗi sự kiện rút gọn. Đã thêm `tests/conftest.py`
cách ly trạng thái chạy sang thư mục tạm và tắt cache mặc định trong test.

## Hai tiêu chí xung đột

Tiêu chí "prompt không bao giờ vượt `HISTORY_TOKEN_BUDGET`" và bảng rủi ro "luôn giữ **nguyên văn**
lượt hỏi-đáp gần nhất" mâu thuẫn trực tiếp khi một lượt đơn lẻ đã lớn hơn ngân sách. Đã chọn giữ
nguyên văn: câu nối tiếp ("vậy còn xe máy thì sao?") chỉ hiểu được nhờ đúng cặp tin nhắn đó. Ngân
sách được áp cho toàn bộ phần còn lại. Ngoại lệ khoá lại bằng
`test_single_oversized_exchange_is_the_budget_floor`.

## Thay đổi so với bản kế hoạch

Bảng đầy đủ nằm trong mục "Ghi chú thi công" của chính tệp phase. Tóm tắt: dùng `SqliteSaver`
đồng bộ thay `AsyncSqliteSaver` (đồ thị chạy bằng `graph.invoke()` trong worker thread ở cả hai
façade); `thread_id` lưu theo từng phiên hội thoại thay vì `sessionStorage` dùng chung cả tab (ứng
dụng có nhiều phiên trong thanh bên); thêm cột `tool_outputs`; sửa thêm `src/graph/adapter.py` và
`requirements.txt` ngoài danh sách tệp của kế hoạch.

## Tệp đã tạo / sửa

**Tạo:** `src/cache/{__init__,fingerprint,semantic_cache}.py`, `src/graph/memory.py`,
`src/graph/turn.py`, `scripts/cache_admin.py`, `tests/{conftest,test_semantic_cache,test_memory,test_thread_memory}.py`,
`.gitignore`

**Sửa:** `src/graph/{build,router,compact,sources,state,adapter}.py`, `src/agent.py`,
`src/api_server.py`, `static/js/chat.js`, `requirements.txt`, `.env.example`, `README.md`

## Kiểm thử

53 test mới trên 4 tệp. Ca chống hồi quy quan trọng nhất được viết **trước** phần cài đặt, đúng
yêu cầu của bước 2 trong kế hoạch. Suite chạy hai lần liên tiếp cho cùng kết quả (162 passed),
xác nhận không còn nhiễm trạng thái giữa các lần chạy.

Đáng chú ý: `test_concurrent_threads_do_not_lock_the_checkpoint_database` chạy 4 lượt hỏi đồng
thời để kiểm rủi ro "database is locked" trên Windows mà bảng rủi ro của phase đã nêu.

## Việc còn lại / cần bạn quyết

1. **Có phiên khác đang sửa cùng kho mã.** Trong lúc thi công, `src/observability/{tracer,langsmith}.py`
   được tạo và `src/graph/build.py`, `src/agent.py`, `src/api_server.py`, `src/graph/adapter.py` bị
   ghi đè từ một phiên khác (Phase 7). Các thay đổi của Phase 6 đã được kiểm lại và còn nguyên, nhưng
   kho mã **không phải git repo** nên không có lưới an toàn. Nên chạy hai phase nối tiếp thay vì song song.
2. **`test_tracer.py::test_tracing_overhead_under_five_percent` thỉnh thoảng đỏ** (đo 10.7% ở một
   lần chạy, xanh ở các lần khác). Đây là test của Phase 7, nhạy với tải máy — không liên quan Phase 6.
3. **`scripts/chat.py` (CLI) vẫn không nhớ ngữ cảnh giữa các câu.** Nó chưa từng truyền `history`,
   nên hành vi không đổi so với trước. Giờ chỉ cần giữ một `thread_id` xuyên suốt vòng lặp là có
   bộ nhớ đa lượt. Không nằm trong tiêu chí của phase nên chưa làm.
4. **Ngưỡng 0.97 chưa được kiểm trên dữ liệu thật quy mô lớn.** Bộ đo chỉ chạy 4 câu để giới hạn chi
   phí gọi API. Nên chạy `--quick 20` trở lên trước khi tin vào tỉ lệ trúng cache trong thực tế.
