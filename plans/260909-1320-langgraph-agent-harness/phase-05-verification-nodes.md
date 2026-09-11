---
phase: 5
title: "Node kiểm chứng và tự sửa"
status: completed
priority: P1
effort: "2d"
dependencies: [4]
---

# Phase 5: Node kiểm chứng và tự sửa

## Overview

Đưa toàn bộ lớp phòng vệ tất định vào đồ thị dưới dạng node `verify` và `repair` nối bằng cạnh có
điều kiện có chặn số vòng. Đây là phần **không được phép hồi quy một chút nào**: nó là lý do duy nhất
khiến model nhỏ hiện tại không bịa được mức phạt.

## Requirements

**Chức năng**
- Node `verify` chạy đủ hai lớp kiểm chứng hiện có: số liệu (`find_ungrounded_figures`) và trích dẫn
  (`find_invalid_citations`).
- Node `repair` cho model đúng **một** cơ hội viết lại, chạy im lặng (không stream token ra giao diện).
- Kiểm chứng lại sau khi sửa; vẫn sai thì **huỷ** câu trả lời và thay bằng `build_unknown_answer()`.
- Xác định vùng ngoài hiểu biết theo đủ 3 dấu hiệu hiện có, dựng nút tra cứu Google.
- Dựng danh sách nguồn trích dẫn (`sources`) cho giao diện: luật, nghị định, biển báo kèm ảnh.
- Phát đúng các sự kiện `verifying`, `verified`, `warning`.

**Phi chức năng**
- Không sửa `src/answer_guard.py`. Node chỉ gọi vào nó.
- Tối đa 1 vòng sửa. `repair_count` nằm trong state, cạnh có điều kiện đọc nó.
- Nguồn đối chiếu phải bao gồm cả câu trả lời đã kiểm chứng của các lượt trước (hành vi hiện có, cần
  thiết cho câu hỏi nối tiếp).

## Architecture

### Cấu trúc đồ thị

```
synthesize ──> verify ──┬── issues rỗng ─────────────────> build_sources ──> END
                        │
                        └── có issues ──┬── repair_count == 0 ──> repair ──> verify
                                        │
                                        └── repair_count >= 1 ──> cancel ──> build_sources ──> END
```

`cancel` là node tất định: thay `answer` bằng `build_unknown_answer(question, sources, issues)`, đặt
`needs_search = True`. Không gọi LLM.

### Nguồn đối chiếu

Hiện tại `verified_sources` = mọi tool output trong lượt + mọi câu trả lời assistant trong lịch sử.
Chú thích trong code cũ giải thích rõ vì sao phải có vế thứ hai: một câu trả lời đúng cho "vậy còn xe
máy thì sao?" sẽ bị huỷ oan nếu lượt này không gọi lại đúng tool của lượt trước. Giữ nguyên logic đó,
chỉ đổi nguồn dữ liệu:

```python
verified_sources = (
    [e["raw_tool_output"] for e in state["evidence"]]        # thay tool_cache.values()
    + [m.content for m in state["messages"] if isinstance(m, AIMessage) and m.content]
)
```

Đây chính là lý do `Evidence` ở Phase 4 phải mang trường `raw_tool_output` nguyên văn: node `compact`
cắt bớt để đưa cho model, nhưng lớp kiểm chứng phải đối chiếu với **bản đầy đủ**. Cắt bằng chứng rồi
lấy bản cắt đi kiểm chứng sẽ sinh ra hàng loạt "số liệu không căn cứ" giả.

### Node `repair`

Port `_rewrite_unverified_details()` gần như nguyên vẹn: cùng câu chỉ dẫn tiếng Việt, cùng nguyên tắc
"bỏ hoặc sửa đúng chi tiết sai, không thêm số mới, nếu không đủ căn cứ thì nói thẳng chưa có dữ liệu".
Hai khác biệt:

1. Chạy trong node riêng, có `repair_count` trong state thay vì biến cục bộ — số vòng sửa trở thành
   một phần trạng thái quan sát được, ghi được vào trace.
2. Không stream token (giao diện chỉ nên thấy kết quả cuối). Chỉ phát `turn_start` (turn=2) để dòng
   thời gian trace cho thấy có một lượt sửa.

### Node `build_sources`

Port `_build_sources()`, `_collect_cited_articles()`, `_collect_cited_decree_items()`,
`_collect_cited_sign_items()`. Có một cải thiện thật ở đây: kiến trúc cũ phải **bóc tách ngược** cấu
trúc từ chuỗi văn bản mà tool đã format ra (regex trên `📖`, `• [`, `🚸`) vì tool chỉ trả string. Kiến
trúc mới có `Evidence` là dữ liệu có cấu trúc ngay từ tầng truy xuất, nên `build_sources` đọc thẳng
trường, không regex.

Giữ nguyên hai hành vi quan trọng của bản cũ:
- Chỉ đọc **dòng tiêu đề** kết quả, không quét toàn thân điều luật (thân điều tham chiếu chéo nhiều
  điều không liên quan, quét hết làm nhiễu danh sách nguồn).
- Đối chiếu tồn tại của Điều qua `DocumentProvider` trước khi đưa vào `sources`.

## Related Code Files

- Create: `src/graph/verify.py`, `src/graph/repair.py`, `src/graph/sources.py`
- Create: `tests/test_verify_node.py`
- Modify: `src/graph/build.py` — thêm 4 node và các cạnh có điều kiện
- Modify: `src/graph/state.py` — dùng `repair_count`, `issues`, `needs_search`, `search`
- Read-only, KHÔNG SỬA: `src/answer_guard.py`
- Read-only: `src/agentic_rag.py` (nguồn port), `src/tools/document_provider.py`

## Implementation Steps

1. Viết `src/graph/verify.py`: gom `verified_sources` như trên, gọi `find_ungrounded_figures()` +
   `find_invalid_citations()` (truyền `articles_by_num` và `road_law_articles` như hiện tại), ghi
   `issues` vào state, emit `verifying` khi có issue.
2. Viết `src/graph/repair.py`: port `_rewrite_unverified_details()`, tăng `repair_count`, emit
   `turn_start` (turn=2).
3. Viết node `cancel` (đặt trong `verify.py`): gọi `build_unknown_answer()`, emit `warning` với đúng
   câu chữ hiện tại.
4. Viết `src/graph/sources.py`: dựng `sources` từ `Evidence` có cấu trúc; giữ nguyên thứ tự ưu tiên
   (nghị định -> biển báo -> điều luật) và `MAX_SOURCES + 4`.
5. Port phần xác định `needs_search`: `verification_failed or all_tools_returned_no_data(...) or
   is_uncertain_answer(...)`, rồi `build_search_link()`.
6. Lắp cạnh có điều kiện trong `build.py`. Khẳng định bằng test rằng không có đường nào cho phép quá
   1 vòng sửa.
7. Viết `tests/test_verify_node.py` với các ca dựng sẵn, **không gọi LLM thật**:
   - Câu trả lời nêu "6.000.000 đồng" mà evidence không có -> phải bị bắt
   - Câu trả lời gán mức tiền cho Điều của Luật 36 -> phải bị bắt
   - Trích dẫn Khoản không tồn tại trong Điều -> phải bị bắt
   - Câu trả lời đúng hoàn toàn -> `issues` rỗng, không kích hoạt `repair`
   - Sửa một lần rồi vẫn sai -> đi vào `cancel`, `needs_search = True`
   - Câu hỏi nối tiếp mà lượt này không gọi lại tool cũ -> **không** bị huỷ oan (lấy căn cứ từ câu
     trả lời đã kiểm chứng của lượt trước)
8. Chạy `e2e_eval.py --adapter graph` đầy đủ, so với baseline: tỉ lệ số liệu không căn cứ phải bằng 0.

## Success Criteria

- [x] `src/answer_guard.py` **không thay đổi một dòng nào** (mtime 2026-09-09 11:52, trước toàn bộ Phase 5)
- [x] `tests/test_verify_node.py` xanh: 11/11 ca, phủ đủ 6 ca ở bước 7 cộng 5 ca cấu trúc
- [x] Không có đường đi nào trong đồ thị cho phép quá 1 vòng `repair` (`repair` chỉ nối về `verify`; `repair_count` luôn tăng kể cả khi LLM lỗi; `recursion_limit=25` là lưới thứ hai)
- [~] Tỉ lệ số liệu không có căn cứ trên bộ eval đầy đủ 95 câu: **1,05%** (1/95). Hai lượt chạy 95 câu liền nhau ra **0,00%** rồi **1,05%** — dao động do LLM không tất định, không phải do đổi mã. Đã rất gần mục tiêu 0% nhưng **chưa chốt được là đạt**.
- [ ] Độ chính xác trích dẫn **63,29%** trên 79 câu yêu cầu dẫn chứng — **chưa đạt** mục tiêu 95%. Đã nâng từ 48% lên 63% bằng cách siết prompt (bắt buộc nêu đích danh số Điều, cấm lối viết 'theo quy định hiện hành'). Phần còn lại **không phải lỗi prompt**: truy xuất chọn sai Điều (ví dụ trả Điều 16 khi đáp án là Điều 17), nên phải sửa ở tầng truy xuất chứ không sửa được ở node này.
- [ ] Tỉ lệ câu trả lời bị huỷ **8,42%** (8/95) so với baseline legacy 0% — **cao hơn**. Đã sửa
      được một nguyên nhân thật: `verify_answer()` có `if not answer: return []`, nghĩa là câu trả
      lời RỖNG bị coi là "không có gì để kiểm chứng, coi như đạt" và được gửi thẳng tới người dùng.
      Nay câu rỗng bị trả về `EMPTY_ANSWER_ISSUE`, đi qua `repair` rồi `cancel` — từ chối trung
      thực thay vì trả về khoảng trắng. Bộ eval 95 câu cuối không còn câu rỗng nào. Phần huỷ còn
      lại là câu bị `verify` bắt lỗi thật.
- [x] Câu hỏi nối tiếp không bị huỷ oan — `test_followup_answer_grounded_by_previous_verified_answer`
- [x] Sự kiện `verifying` / `verified` / `warning` hiển thị đúng trên trace giao diện (`static/js/agent-trace.js:227-236`, không sửa một dòng JS nào)

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| Đối chiếu với bằng chứng đã cắt thay vì bản đầy đủ | Tỉ lệ huỷ tăng vọt so với baseline | `Evidence.raw_tool_output` là bắt buộc; có test khẳng định `verify` dùng bản đầy đủ chứ không dùng `packed_context` |
| Cạnh có điều kiện vòng lại vô hạn khi `repair_count` không được ghi | Đồ thị chạy mãi, chạm giới hạn đệ quy của LangGraph | Đặt `recursion_limit` khi compile như lưới an toàn thứ hai; test riêng cho ca sửa-vẫn-sai |
| `build_sources` đọc từ `Evidence` bỏ sót nguồn mà bản regex cũ bắt được | Chip nguồn ít hơn trước | So sánh song song trên 20 câu: chạy cả hai cách, đối chiếu danh sách nguồn |
| Model nhỏ khi sửa lại thêm số mới | `issues` sau sửa nhiều hơn trước sửa | Đã có: sửa không sạch thì huỷ. Thêm ghi trace số issue trước/sau để theo dõi model nào sửa tệ |

## Ghi Chú Thực Thi

**Chỉ câu trả lời đã kiểm chứng mới vào lịch sử hội thoại.** Phase 4 để `synthesize` ghi thẳng
`AIMessage(final_answer)` vào `messages`. Kết hợp với quy tắc "câu trả lời của lượt trước là nguồn
đã xác minh" của Phase 5, điều đó tạo ra một lỗ hổng: một câu trả lời bị `cancel` vì bịa mức phạt
vẫn nằm trong lịch sử, và ở lượt sau chính con số vừa bị bắt lại trở thành căn cứ hợp lệ.

Vì vậy `synthesize` không còn ghi `messages`; node cuối `build_sources` mới ghi, và chỉ ghi khi
`issues` rỗng. Câu từ chối do `cancel` sinh ra cũng không vào lịch sử — nó liệt kê chính các số liệu
vừa bị loại bỏ, đưa vào sẽ tái lập đúng lỗ hổng trên.

**Sự kiện `done` chuyển từ `synthesize` sang `build_sources`.** `done` mang `answer`,
`verification_issues`, `needs_search` và `search` — cả bốn chỉ được chốt sau khi kiểm chứng xong.
Hợp đồng SSE với giao diện không đổi: `done` vẫn là sự kiện cuối cùng, vẫn đủ trường.
