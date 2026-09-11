---
phase: 6
title: "Bộ nhớ đa lượt và cache ngữ nghĩa"
status: completed
priority: P2
effort: "2d"
dependencies: [4, 5]
---

# Phase 6: Bộ nhớ đa lượt và cache ngữ nghĩa

## Overview

Thay `MAX_HISTORY_MESSAGES = 6` thô bằng checkpointer của LangGraph cộng nén lịch sử theo ngân sách
token, và thêm cache ngữ nghĩa cho câu trả lời **đã qua kiểm chứng**. Hai việc phục vụ cùng một mục
tiêu: giữ ngữ cảnh cần thiết mà không phình context — điều kiện sống còn với model nhỏ.

## Requirements

**Chức năng**
- Checkpointer SQLite, một `thread_id` cho mỗi cuộc hội thoại.
- Nén lịch sử: cắt theo token, tóm tắt các lượt bị cắt thành `history_summary`.
- Cache ngữ nghĩa câu trả lời: trúng cache thì trả ngay, không chạy đồ thị.
- `/api/ask` nhận `thread_id` tuỳ chọn; nếu thiếu thì server sinh và trả về trong sự kiện `done`.
- Lệnh dọn cache và xoá thread cũ.

**Phi chức năng**
- **Chỉ cache câu trả lời có `issues` rỗng.** Câu chưa qua kiểm chứng hoặc đã bị huỷ không bao giờ
  được cache.
- Cache tự vô hiệu khi chỉ mục hoặc model embedding đổi.
- Tệp trạng thái nằm dưới `data/runtime/`, thêm vào `.gitignore`.

## Architecture

### Checkpointer và nén lịch sử

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
checkpointer = AsyncSqliteSaver.from_conn_string("data/runtime/checkpoints.sqlite")
graph = builder.compile(checkpointer=checkpointer)
```

Node `memory` chạy ngay sau `normalize`:

```
messages = trim_messages(state["messages"],
                         max_tokens=HISTORY_TOKEN_BUDGET,   # mặc định 2000
                         strategy="last",
                         token_counter=count_tokens)
if có lượt bị cắt và chưa được tóm tắt:
    history_summary = LLM tóm tắt các lượt bị cắt thành <= 150 từ
```

Vì sao hơn `MAX_HISTORY_MESSAGES = 6`: sáu tin nhắn có thể là 200 token hoặc 8000 token — câu trả lời
pháp lý dài, có bảng và khối trích dẫn. Cắt theo **số tin nhắn** làm ngân sách context dao động không
kiểm soát, đúng loại rủi ro mà model nhỏ chịu kém nhất. Cắt theo token cho ngân sách ổn định; phần bị
cắt không mất hẳn mà được tóm tắt lại.

`history_summary` được `compact` chèn vào prompt dưới nhãn "Ngữ cảnh hội thoại trước". Lưu ý an toàn:
nó là **văn xuôi tóm tắt**, không phải nguồn đối chiếu — node `verify` ở Phase 5 vẫn chỉ đối chiếu
với `raw_tool_output` và các câu trả lời assistant đầy đủ, không bao giờ với bản tóm tắt.

### Cache ngữ nghĩa — và cái bẫy phải tránh

Cache theo độ tương đồng vector đơn thuần là **nguy hiểm với miền pháp luật**. "Ô tô vượt đèn đỏ phạt
bao nhiêu" và "Xe máy vượt đèn đỏ phạt bao nhiêu" có cosine rất cao (khác đúng một cụm từ) nhưng mức
phạt hoàn toàn khác nhau. Trúng cache sai ở đây nghĩa là đưa cho người dùng một con số sai — đúng
loại lỗi mà cả kiến trúc này sinh ra để chặn.

Khoá cache vì vậy là **tổ hợp**, không phải chỉ vector:

```python
key = (
    frozenset(route.intents),        # phải khớp chính xác
    frozenset(route.vehicles),       # phải khớp chính xác  <- chặn bẫy ô tô/xe máy
    route.doc_scope,                 # phải khớp chính xác
    index_fingerprint,               # đổi chỉ mục -> miss toàn bộ
)
# trong cùng một key, mới so cosine của vector truy vấn
hit khi cosine >= SEMANTIC_CACHE_THRESHOLD (mặc định 0.97)
```

Ngưỡng đặt cao (0.97 thay vì 0.95 thường dùng) có chủ ý: trong miền này, một lần trúng nhầm tốn kém
hơn nhiều so với mười lần trượt cache.

Điều kiện ghi cache — tất cả phải đúng:
- `issues` rỗng (đã qua kiểm chứng)
- `needs_search` là False (không phải câu ngoài vùng dữ liệu)
- có ít nhất một nguồn trích dẫn

Lưu trữ: SQLite `data/runtime/answer_cache.sqlite`, cột (key_hash, query_vector BLOB, answer, sources
JSON, created_at, index_fingerprint). TTL mặc định 30 ngày.

`index_fingerprint` = sha256 của (đường dẫn + mtime + kích thước) của `semantic_index.npz`,
`semantic_chunks.json`, `bm25_index.pkl`, cộng tên `EMBEDDING_MODEL`. Dựng lại chỉ mục là cache tự
chết, không cần nhớ xoá tay.

Khi trúng cache, đồ thị **không chạy**; `agent.py` phát thẳng chuỗi sự kiện rút gọn:
`start` -> `tool_result` ("Dùng lại kết quả đã kiểm chứng cho câu hỏi tương tự") -> `token`(cả câu)
-> `done`. Giao diện không cần biết đây là cache, nhưng trace nên nói rõ để bạn tin được kết quả.

### Thay đổi phía giao diện

Đúng một chỗ trong `static/js/chat.js`: gửi kèm `thread_id` từ `sessionStorage`, và lưu lại
`thread_id` nhận được trong sự kiện `done`. Không đụng gì khác.

## Related Code Files

- Create: `src/graph/memory.py`, `src/cache/__init__.py`, `src/cache/semantic_cache.py`,
  `src/cache/fingerprint.py`
- Create: `scripts/cache_admin.py` — `--stats`, `--clear`, `--prune-threads`
- Create: `tests/test_semantic_cache.py`
- Modify: `src/graph/build.py` — gắn checkpointer, thêm node `memory`
- Modify: `src/agent.py` — tra cache trước khi chạy đồ thị, ghi cache sau khi kiểm chứng xong
- Modify: `src/api_server.py` — `AskRequest` thêm `thread_id: str | None`, trả về trong `done`
- Modify: `static/js/chat.js` — gửi/nhận `thread_id` (thay đổi JS duy nhất của cả kế hoạch)
- Modify: `.gitignore` — thêm `data/runtime/`
- Modify: `.env.example` — `HISTORY_TOKEN_BUDGET`, `SEMANTIC_CACHE_THRESHOLD`, `CACHE_TTL_DAYS`

## Implementation Steps

1. Viết `src/cache/fingerprint.py`, có test khẳng định fingerprint đổi khi bất kỳ tệp chỉ mục nào đổi.
2. Viết `src/cache/semantic_cache.py` với khoá tổ hợp như trên. Viết
   `tests/test_semantic_cache.py` **bắt đầu bằng ca chống hồi quy quan trọng nhất**: câu hỏi ô tô đã
   cache, hỏi câu xe máy tương tự -> **phải trượt cache**. Viết ca này trước khi viết logic.
3. Cắm tra cache vào `src/agent.py`, sau `route` (cần `intents`/`vehicles` để dựng khoá) nhưng trước
   khi truy xuất — nghĩa là cache tiết kiệm được cả truy xuất lẫn sinh văn bản, chỉ tốn một lệnh gọi
   router rẻ.
4. Viết `src/graph/memory.py` với `trim_messages` + tóm tắt lượt bị cắt. Đặt ngân sách mặc định 2000
   token, cho chỉnh qua `.env`.
5. Gắn `AsyncSqliteSaver` trong `build.py`; đảm bảo đóng kết nối gọn khi tắt server.
6. Thêm `thread_id` vào `AskRequest` và sự kiện `done`; sinh UUID phía server khi thiếu.
7. Sửa `static/js/chat.js` (một chỗ), kiểm bằng tay: hỏi 3 lượt nối tiếp, F5, hỏi tiếp — ngữ cảnh
   phải còn.
8. Viết `scripts/cache_admin.py`.
9. Đo lại: chạy `e2e_eval.py` hai lần liên tiếp, lần hai phải nhanh hơn rõ rệt và **không đổi kết
   quả**. Nếu kết quả đổi, cache đang trả nhầm — dừng và sửa khoá.

## Success Criteria

- [x] Ca "ô tô đã cache, hỏi xe máy" **trượt cache** — `test_motorbike_question_misses_cached_car_answer`,
      cộng `test_deterministic_key_still_separates_car_from_motorbike` kiểm cùng bất biến ở tầng câu hỏi
- [x] Hội thoại đa lượt giữ đúng ngữ cảnh qua checkpointer, sống qua F5 trình duyệt —
      `test_context_survives_a_browser_refresh` (lượt hai gửi `history` rỗng, chỉ còn `thread_id`)
- [x] Prompt gửi lên model không vượt `HISTORY_TOKEN_BUDGET` cho phần lịch sử — với **một ngoại lệ
      có chủ ý**: khi một lượt hỏi-đáp đơn lẻ đã lớn hơn ngân sách, nó vẫn được giữ nguyên văn, vì
      bảng rủi ro của chính phase này yêu cầu "luôn giữ nguyên văn lượt gần nhất". Hai tiêu chí đó
      xung đột trực tiếp; giữ nguyên văn thắng, và ngoại lệ được khoá lại bằng
      `test_single_oversized_exchange_is_the_budget_floor`
- [x] Câu có `issues` hoặc `needs_search` **không bao giờ** được ghi cache —
      `test_answer_with_issues_is_never_cacheable`, `test_turn_never_stores_a_cancelled_answer`
- [x] Dựng lại chỉ mục làm toàn bộ cache miss — `test_fingerprint_changes_when_any_index_file_changes`
- [x] Chạy `e2e_eval.py` lần hai: **nhanh hơn 73.8%** (521.8s -> 136.5s, 2/4 câu trúng cache).
      Toàn bộ chỉ số chất lượng giống hệt (huỷ câu 0%, chính xác trích dẫn 75%, số liệu không căn cứ
      0%, từ chối đúng 100%). Hai câu **không** trúng cache có `answer_preview` khác nhau — đó là
      tính không tất định của LLM trên đường trượt cache, không phải cache trả nhầm: mọi trường kiểm
      chứng của cả bốn câu đều trùng khớp, và hai câu trúng cache trùng khớp đến từng ký tự
- [x] `scripts/cache_admin.py --stats` in được tỉ lệ trúng cache
- [x] `data/runtime/` đã nằm trong `.gitignore`

## Ghi chú thi công (khác với bản kế hoạch)

| Điểm | Kế hoạch viết | Đã làm | Vì sao |
|---|---|---|---|
| Checkpointer | `AsyncSqliteSaver` | `SqliteSaver` đồng bộ, WAL + `check_same_thread=False`, đúng một thể hiện dùng chung | Đồ thị chạy bằng `graph.invoke()` trong worker thread ở **cả hai** façade của `src/agent.py`; bản async đòi `ainvoke` nên sẽ không bao giờ được gọi tới |
| Khoá cache | `frozenset(route.intents)`, `frozenset(route.vehicles)`, `route.doc_scope` từ `route` thật | Cùng cấu trúc nhưng dựng từ **regex prior tất định**, `doc_scope` giữ cố định | `route` thật là phép hợp với LLM router, mà LLM router **không tất định**: đo ba lượt trên cùng một câu hỏi ra hai bộ `vehicles` khác nhau, tức hai khoá khác nhau. Dùng nó làm khoá thì cache **không bao giờ trúng** — lần đo đầu tiên đúng như vậy: 8 lượt tra, 0 trúng. Regex prior vẫn tách bạch ô tô/xe máy và Luật/Nghị định nên bất biến an toàn được giữ nguyên |
| Cột cache | `(key_hash, query_vector, answer, sources, created_at, index_fingerprint)` | Thêm cột `tool_outputs` | Không có bằng chứng nguyên văn đi kèm, bộ eval kết luận sai rằng câu trả lời từ cache "không có căn cứ", và tiêu chí "kết quả giống hệt" không thể đạt được |
| `static/js/chat.js` | `thread_id` lưu trong `sessionStorage` | `thread_id` lưu **theo từng phiên hội thoại** trong bản ghi phiên (localStorage) | Ứng dụng có nhiều phiên trong thanh bên; một `thread_id` dùng chung cho cả tab sẽ nối câu hỏi của phiên này vào ngữ cảnh của phiên khác. Lưu theo phiên vẫn sống qua F5 và còn đúng khi chuyển phiên |
| `src/graph/adapter.py` | không nằm trong danh sách tệp | `GraphAdapter` chuyển sang gọi `run_turn` | Nó gọi thẳng `graph.invoke()` nên **đi vòng qua cache**; bộ eval khi đó không đo hệ thống thật và bước "chạy lại lần hai" không kiểm được gì |
| `requirements.txt` | `langgraph-checkpoint-sqlite>=2.0,<3` | `>=3.1,<4` | Bản 2.x gọi `JsonPlusSerializer.dumps()`, API đã bị bỏ trong `langgraph-checkpoint` 4.x: mọi lượt ghi checkpoint ném `AttributeError` |

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| Cache trả câu của loại xe khác | Bước 9 cho kết quả eval đổi giữa hai lần chạy | Khoá tổ hợp + ngưỡng 0.97 + test viết trước. Nếu vẫn lọt, hạ xuống chỉ cache khi **chuỗi câu hỏi chuẩn hoá trùng khớp tuyệt đối** — mất một phần lợi ích nhưng an toàn |
| Tóm tắt lịch sử làm sai lệch ngữ cảnh câu nối tiếp | Câu "vậy còn xe máy thì sao?" trả lời lạc đề | Luôn giữ **nguyên văn** lượt hỏi-đáp gần nhất, chỉ tóm tắt phần cũ hơn |
| Bản tóm tắt bị dùng làm nguồn đối chiếu kiểm chứng | Số liệu bịa lọt qua `verify` | `verify` chỉ nhận `raw_tool_output` + câu trả lời assistant đầy đủ; `history_summary` không nằm trong `verified_sources`. Có test khẳng định |
| SQLite khoá file trên Windows khi nhiều request đồng thời | Lỗi "database is locked" | Dùng bản async + WAL mode; checkpointer và cache dùng hai tệp riêng |
| Thread tích luỹ vô hạn | Tệp checkpoint phình to | `scripts/cache_admin.py --prune-threads` xoá thread không hoạt động quá 30 ngày |
