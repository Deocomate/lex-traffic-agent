---
title: "Tái Kiến Trúc Agent Harness LexTraffic AI Trên LangChain 1.x + LangGraph 1.x"
description: "Thay toàn bộ vòng lặp ReAct tự viết tay bằng một StateGraph LangGraph có định tuyến tất định, truy xuất lai BM25 + vector + RRF + LLM rerank, đóng gói bằng chứng theo ngân sách token, kiểm chứng và tự sửa thành node của đồ thị, bộ nhớ đa lượt qua checkpointer, cache ngữ nghĩa, quan trắc, và một bộ eval có cổng chặn hồi quy — mục tiêu để model nhỏ ít tham số vẫn trả lời đúng căn cứ pháp lý."
status: pending
priority: P1
effort: "15 days"
tags: [langgraph, langchain, agentic-rag, hybrid-retrieval, bm25, rrf, reranking, small-model, context-engineering, eval-harness, observability, semantic-cache]
created: 2026-09-09
---

# Tái Kiến Trúc Agent Harness LexTraffic AI Trên LangChain 1.x + LangGraph 1.x

## Overview

Hệ thống hiện tại chạy một vòng lặp ReAct **tự viết tay** trong `src/agentic_rag.py` (1004 dòng): gọi
thẳng OpenAI SDK tới OpenRouter, để mô hình tự chọn trong 7 tool bằng function calling, tự gom
tool result vào `messages`, tự cắt stream khi mô hình lặp, tự parse cả tool call dạng DSML thô mà
model nhỏ hay sinh sai. Lớp kiểm chứng tất định `src/answer_guard.py` (545 dòng) chạy **sau** vòng
lặp và có quyền huỷ nguyên câu trả lời.

Kiến trúc đó đã chứng minh được một điều quan trọng: **phòng vệ bằng code mạnh hơn phòng vệ bằng
prompt**. Nhưng nó đang chạm ba trần cứng.

### Trần 1 — Chất lượng truy xuất, nút thắt lớn nhất

Benchmark 35 câu (`data/benchmark/evaluation_report.json`) đo trên chính chỉ mục hiện tại:

| Chỉ số | Hiện tại |
|---|---|
| Hit Rate @1 | **51.4%** |
| Hit Rate @3 | 82.9% |
| MRR | 0.66 |

Gần một nửa số câu hỏi có Điều luật đúng **không nằm ở vị trí số 1**. `semantic_search`
(`src/tools/law_search_tools.py:363`) chỉ trả toàn văn cho kết quả rank-1; rank 2-3 chỉ còn hai dòng
tóm tắt. Nghĩa là trong khoảng 48% trường hợp, ngữ cảnh đầy đủ mà mô hình nhận được là của **Điều
sai**. Không mô hình nào — dù lớn tới đâu — sửa được ngữ cảnh sai; model nhỏ lại càng không.

### Trần 2 — Điều khiển: model nhỏ gánh quá nhiều quyết định

Harness hiện tại giao cho LLM ba việc cùng lúc: chọn tool, chọn tham số, và tổng hợp. Model nhỏ làm
kém cả ba, nên code phải chống đỡ bằng hàng loạt lớp vá: `MAX_TOOL_CALLS_PER_TURN`, ngoại lệ
`_ToolCallOverflow` cắt stream giữa chừng, `_parse_raw_dsml_tool_calls()` vớt tool call hỏng,
`_clean_text_output()` xoá thẻ rò rỉ, nhánh `needs_grounding` chèn tool thủ công khi mô hình định
trả lời từ trí nhớ. Mỗi lớp vá là một triệu chứng của cùng một nguyên nhân gốc: **để mô hình yếu tự
lái**.

### Trần 3 — Đo lường: không chứng minh được cải tiến

Chỉ có 3 chỉ số retrieval trên 35 câu (toàn bộ đều nhắm Luật 36; 5 văn bản còn lại **không có câu
benchmark nào**) và 5 test E2E chạy tay. Không đo được: độ chính xác trích dẫn, tỉ lệ câu trả lời bị
huỷ, tỉ lệ từ chối đúng khi hỏi lạc đề, độ trễ, chi phí. Không có baseline thì mọi tuyên bố "đã tối
ưu" đều là cảm tính.

Kế hoạch này viết lại **toàn bộ lớp điều phối** trên LangChain 1.x + LangGraph 1.x, đảo ngược mô
hình điều khiển: đồ thị tất định quyết định luồng, mô hình chỉ làm đúng hai việc hẹp mà nó làm tốt —
hiểu ý định câu hỏi, và viết câu trả lời từ bằng chứng đã có sẵn.

## Quyết Định Đã Chốt

| Quyết định | Lựa chọn của bạn | Hệ quả |
|---|---|---|
| Mức độ chuyển đổi | **Viết lại toàn bộ theo LangChain/LangGraph** | `src/agentic_rag.py` bị xoá hẳn ở Phase 8. Xem "Ranh giới viết lại" bên dưới |
| Tầng truy xuất | **Giữ embedding từ xa, thêm BM25 + LLM rerank** | `semantic_index.npz` giữ nguyên, KHÔNG phải re-embed. Thêm tầng BM25 + hợp nhất RRF + rerank bằng LLM nhỏ |
| Model nhỏ | **Hosted trên OpenRouter** | Không dựng runtime local. Cần structured output Pydantic + parser dự phòng cho model có function calling yếu |
| Phạm vi thêm | **Cả 4**: eval + cổng hồi quy, quan trắc, cache ngữ nghĩa, nén bộ nhớ đa lượt | 8 phase, khoảng 15 ngày |

### Ranh Giới Viết Lại (giả định đã nêu rõ)

"Viết lại toàn bộ" được hiểu là **viết lại toàn bộ lớp điều phối (orchestration)**, không phải xoá
sạch mọi thứ:

| Thành phần | Số phận | Lý do |
|---|---|---|
| `src/agentic_rag.py` | **Xoá hoàn toàn** | Chính là lớp điều phối cần thay |
| `src/answer_guard.py` | **Giữ nguyên hàm thuần, gọi từ node `verify`** | Là các hàm kiểm chứng tất định đã chứng minh đúng trên dữ liệu thật. Viết lại chỉ để "cho giống LangChain" là tự tạo hồi quy mà không đổi được gì |
| `src/tools/*.py` | **Giữ lớp truy cập dữ liệu, bọc lại thành Retriever/@tool** | 619 dòng `document_provider` + 432 dòng `penalty_lookup` là lớp dữ liệu, không phải harness |
| `src/semantic_index.py` | **Giữ, bọc thành `BaseRetriever`** | Bạn đã chọn giữ embedding từ xa |
| `src/api_server.py` | **Sửa: `/api/ask` thành `async def`, thêm `thread_id`** | Hợp đồng SSE giữ nguyên |
| `static/js/*` | **Gần như không đổi** | Hợp đồng sự kiện SSE được bảo toàn có chủ đích |

Nếu bạn muốn viết lại cả `answer_guard.py` và `src/tools/`, nói một câu, tôi mở rộng Phase 5 và
Phase 8. Mặc định **không** làm, vì nó đánh đổi rủi ro hồi quy lấy sự đồng nhất hình thức.

## Kiến Trúc Mục Tiêu

### Đảo ngược mô hình điều khiển

```
HIỆN TẠI (model lái)                      MỚI (đồ thị lái)

  LLM ──chọn tool?──> tool                  regex prior ─┐
   ^                    |                                +──> hợp nhất ý định
   +──── lặp 4 lượt ────+                   LLM router ──+          |
   |                                                                v
   v                                                     fan-out song song
  câu trả lời ──> guard ──> huỷ?                          |
                                                          +── penalty (BM25+vector+RRF)
  Model quyết định: tool nào, tham số gì,                 +── law     (BM25+vector+RRF)
  gọi mấy lần, khi nào dừng, viết gì.                     +── sign
  = 5 quyết định x model yếu = 5 điểm hỏng                +── speed
                                                          |
                                                          v
                                                  rerank (LLM listwise)
                                                          |
                                                          v
                                                  compact (ngân sách token)
                                                          |
                                                          v
                                                  synthesize (KHÔNG bind tool)
                                                          |
                                                          v
                                                  verify ──sai──> repair (<=1 vòng)
                                                          |
                                                          v
                                                        done

  Model chỉ quyết định: ý định (có regex đỡ) + viết câu trả lời.
  = 2 quyết định, cả hai đều có lưới an toàn tất định.
```

Ba nguyên tắc chi phối, đúng theo best practice harness cho model nhỏ:

1. **Thu hẹp không gian quyết định.** Không để model chọn tool. Bộ định tuyến regex chạy trước và
   cho ra tập ý định nền; LLM router chỉ được **thêm** ý định, không được **bớt** ý định mà regex đã
   chắc chắn. Hợp nhất bằng phép hợp, không phải phép thay thế.
2. **Bằng chứng gọn hơn, không nhiều hơn.** Hiện tại mỗi tool result đều đính kèm nguyên khối
   `FIGURE_LOCK_NOTE` (~15 dòng chỉ dẫn) — gọi 4 tool là 60 dòng chỉ dẫn lặp lại chen giữa dữ liệu
   pháp lý, ăn hết sự chú ý vốn đã hạn hẹp của model nhỏ. Node `compact` gộp thành **một** khối chỉ
   dẫn duy nhất đặt sát điểm sinh văn bản, và cắt bằng chứng theo ngân sách token cứng.
3. **Sinh văn bản không có tool.** Node `synthesize` không bind tool nào. Model nhỏ **không thể**
   sinh tool call hỏng, không thể lặp vô hạn, không thể rò thẻ DSML — vì đường đó bị đóng ở tầng
   kiến trúc chứ không phải bằng lời nhắc.

### Cây thư mục mới

```
src/
├── llm/
│   ├── provider.py        # ChatOpenAI -> OpenRouter, chuỗi fallback, cấu hình từ .env
│   └── structured.py      # with_structured_output + parser JSON dự phòng cho model yếu
├── retrieval/
│   ├── vi_text.py         # tokenizer tiếng Việt, stopwords, bigram, alias thông tục
│   ├── dense.py           # BaseRetriever bọc semantic_index.npz hiện có (KHÔNG re-embed)
│   ├── sparse.py          # BM25 unigram+bigram trên 2114 chunk
│   ├── hybrid.py          # hợp nhất RRF có trọng số + lọc doc_scope
│   ├── rerank.py          # LLM listwise rerank, bỏ qua khi RRF đã quyết định rõ
│   └── cache.py           # cache vector truy vấn trên đĩa
├── graph/
│   ├── state.py           # LegalAgentState + reducer
│   ├── router.py          # node định tuyến (regex prior hợp với LLM structured output)
│   ├── retrieve.py        # 4 node truy xuất chạy song song
│   ├── rerank_node.py     # node xếp hạng lại
│   ├── compact.py         # node đóng gói bằng chứng theo ngân sách token
│   ├── synthesize.py      # node tổng hợp, không bind tool
│   ├── verify.py          # node kiểm chứng (gọi answer_guard)
│   ├── repair.py          # node tự sửa, cạnh có điều kiện, tối đa 1 vòng
│   ├── memory.py          # nén lịch sử hội thoại
│   ├── events.py          # ánh xạ node -> hợp đồng SSE hiện có
│   └── build.py           # StateGraph, compile, checkpointer
├── observability/
│   ├── tracer.py          # BaseCallbackHandler ghi JSONL cục bộ
│   └── langsmith.py       # bật LangSmith qua biến môi trường (tuỳ chọn)
├── cache/
│   └── semantic_cache.py  # cache câu trả lời đã kiểm chứng theo khoá tổ hợp
├── agent.py               # façade: stream_agent()/run_agent(), giữ nguyên chữ ký cho api_server
├── answer_guard.py        # GIỮ NGUYÊN
├── semantic_index.py      # GIỮ NGUYÊN
└── tools/                 # GIỮ NGUYÊN lớp dữ liệu
```

### Hợp đồng SSE được bảo toàn tuyệt đối

Giao diện vừa hoàn tất đợt redesign (`plans/260908-1657-minimal-ui-redesign`, status `completed`).
`static/js/agent-trace.js:203-256` và `static/js/chat.js:295` xử lý đúng 14 loại sự kiện. Đồ thị mới
**phải phát ra đúng bộ đó**, nếu không đợt redesign vừa xong sẽ hỏng.

| Node LangGraph | Sự kiện SSE phát ra |
|---|---|
| vào đồ thị | `start` |
| `router` | `turn_start` (turn=1) |
| mỗi node truy xuất | `tool_call` -> `tool_result` |
| `rerank` | `tool_call` / `tool_result` với `action="rerank"` |
| `compact` | (im lặng) |
| `synthesize` | `synthesizing` -> `token` (`phase="answer"`) -> `answer_commit` |
| `verify` | `verifying` -> `verified` hoặc `warning` |
| `repair` | `turn_start` (turn=2) |
| fallback model | `model_fallback` |
| kết thúc | `done` (answer, agent_steps, sources, needs_search, search, verification_issues) |
| ngoại lệ | `error` |

`answer_reset` không còn được phát (kiến trúc mới không sinh bản nháp trước khi gọi tool nữa) nhưng
frontend xử lý nó như một `case` độc lập nên **không cần sửa gì**. Đây là lợi ích phụ đáng kể: bản
nháp bị xoá trước mắt người dùng — một khiếm khuyết UX của kiến trúc cũ — biến mất theo kiến trúc.

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Nâng Hit@1 truy xuất từ 51.4% lên >= 72% và MRR từ 0.66 lên >= 0.80 bằng truy xuất lai BM25 + vector + RRF + rerank | P1 |
| 2 | Thay vòng lặp ReAct thủ công bằng StateGraph LangGraph có định tuyến tất định, để model nhỏ chỉ còn 2 quyết định thay vì 5 | P1 |
| 3 | Bảo toàn 100% lớp phòng vệ tất định (kiểm chứng số liệu, kiểm chứng trích dẫn, huỷ câu trả lời) dưới dạng node đồ thị | P1 |
| 4 | Dựng bộ eval đo được cả retrieval lẫn end-to-end, có baseline và cổng chặn hồi quy | P1 |
| 5 | Giảm chi phí và độ trễ bằng cache vector truy vấn, cache ngữ nghĩa câu trả lời đã kiểm chứng, và nén bằng chứng theo ngân sách token | P2 |
| 6 | Bộ nhớ đa lượt qua checkpointer thay `MAX_HISTORY_MESSAGES = 6` thô | P2 |
| 7 | Quan trắc từng node: độ trễ, token, chi phí, tỉ lệ trúng cache, kết quả kiểm chứng | P2 |
| 8 | Giữ nguyên hợp đồng SSE và mọi endpoint API hiện có — giao diện không phải sửa | P1 |

## Non-Goals

- Không đổi mô hình embedding, không dựng lại `semantic_index.npz` (bạn đã chốt giữ embedding từ xa).
- Không chạy model local (Ollama/vLLM). Không dựng đường đi cho runtime local.
- Không đổi dữ liệu pháp luật, không chạy lại OCR, không đụng `data/processed/*` ngoài việc thêm
  tệp chỉ mục BM25 và các tệp cache/trace mới.
- Không redesign giao diện. Chỉ sửa `static/js/chat.js` đúng một chỗ để gửi/nhận `thread_id` (Phase 6).
- Không thêm vector database (Chroma/FAISS). Ma trận numpy 2114 x 3072 nạp trong RAM là đủ và nhanh
  hơn mọi DB ngoài ở quy mô này.

## Phases

| # | Phase | Status | Phụ thuộc |
|---|-------|--------|-----------|
| 1 | [Bộ eval và baseline đo lường](./phase-01-eval-harness-baseline.md) | Completed (benchmark v2 95 câu, người dùng duyệt 2026-09-11) | — |
| 2 | [Nền tảng LangChain/LangGraph và lớp model](./phase-02-langgraph-foundation.md) | Completed | 1 |
| 3 | [Tầng truy xuất lai BM25 + vector + RRF + rerank](./phase-03-hybrid-retrieval.md) | Completed | 1, 2 |
| 4 | [Đồ thị Agent LangGraph](./phase-04-agent-graph.md) | Completed | 2, 3 |
| 5 | [Node kiểm chứng và tự sửa](./phase-05-verification-nodes.md) | Completed | 4 |
| 6 | [Bộ nhớ đa lượt và cache ngữ nghĩa](./phase-06-memory-and-cache.md) | Completed | 4, 5 |
| 7 | [Quan trắc và truy vết](./phase-07-observability.md) | Completed | 4 |
| 8 | [Cắt chuyển, gỡ mã cũ và tài liệu](./phase-08-cutover-and-cleanup.md) | Mostly Done (mã + tài liệu xong; 3 cổng chất lượng chưa đạt) | 1-7 |

**Thứ tự có chủ đích:** Phase 1 đứng trước mọi thay đổi kiến trúc. Không có baseline đo được thì
Phase 3 không thể chứng minh là đã cải thiện, và Phase 8 không thể chứng minh là không hồi quy.

## Chỉ Số Mục Tiêu

| Chỉ số | Baseline (đo được hôm nay) | Mục tiêu | Ngưỡng cổng chặn |
|---|---|---|---|
| Hit Rate @1 | 51.4% | >= 72% | **72.15% — ĐẠT** |
| Hit Rate @3 | 82.9% | >= 92% | **83.54% — chưa đạt mục tiêu 92%, nhưng không tụt so với baseline** |
| MRR | 0.66 | >= 0.80 | **0.7774 — chưa đạt** |
| Độ chính xác trích dẫn (E2E) | chưa đo | >= 95% | **63.29% — chưa đạt** |
| Tỉ lệ số liệu không căn cứ | chưa đo | 0% | **1.05% — sát mục tiêu, dao động 0.00%–1.05% giữa hai lượt** |
| Từ chối đúng khi hỏi lạc đề | chưa đo | >= 93% | **93.75% trên tập lạc đề / 87.50% trong lượt 95 câu** |
| Tỉ lệ câu trả lời bị huỷ | chưa đo | giảm so với baseline | **8.42% — tăng** |
| Độ trễ p50 | 28.5s (legacy) | giảm >= 20% | **30.9s — QUA cổng chặn (+8.6%, dưới ngưỡng +10%)**; đã hạ từ 96.1s sau khi ghìm reasoning |

Baseline của 5 chỉ số "chưa đo" được chốt ở cuối Phase 1, đo trên chính harness cũ.

## Success Criteria

- [ ] `gate.py` chạy được nhưng trả **exit code 1**: qua cổng độ trễ, trượt 4 cổng chất lượng
- [~] Hit@1 **72.15%** đạt; MRR **0.7774** chưa đạt. Bộ benchmark 95 câu phủ đủ 6 văn bản
- [ ] Trích dẫn **63.29%** chưa đạt; số liệu không căn cứ **1.05%** chưa chốt được là 0%
- [~] Hợp đồng SSE: đã vá `model_fallback` (trước chỉ ghi vào tệp trace, không bao giờ phát ra SSE — giao diện có nhánh xử lý mà không bao giờ nhận được sự kiện), khoá bằng 2 test. `answer_reset` cố ý không còn phát theo đúng thiết kế mới. **Chưa kiểm thử thủ công trên trình duyệt.**
- [x] Hội thoại đa lượt giữ ngữ cảnh qua checkpointer (Phase 6, `langgraph-checkpoint-sqlite 3.1.1`)
- [x] `src/agentic_rag.py` đã xoá; không còn import nào trong code runtime
- [x] Trace JSONL ghi đủ node / độ trễ / token / chi phí cho mọi lượt chạy (`baseline-graph-phase7-260910.json`, 43 lượt)
- [~] Chạy trọn hệ thống trên 2 model (`deepseek-v4-flash`, `gpt-oss-20b`) không lỗi hạ tầng; **chưa model nào qua đủ cổng chất lượng**
- [x] `README.md` và `docs/architecture.md` phản ánh kiến trúc mới

## Rủi Ro Xuyên Suốt

| Rủi ro | Tín hiệu nhận biết | Phản ứng đã định trước |
|---|---|---|
| Viết lại làm mất hành vi đã đúng | Cổng chặn Phase 8 fail ở chỉ số E2E | Giữ `agentic_rag.py` trên đĩa tới khi cổng chặn xanh; so từng câu trong bộ eval để tìm hồi quy |
| API LangChain/LangGraph đổi giữa chừng | `pip install` kéo về minor mới, import gãy | Ghim `langchain>=1.0,<2`, `langgraph>=1.2,<2` trong `requirements.txt`; không dùng API đã deprecated |
| Rerank làm tăng độ trễ | p50 tăng quá 10% | Bỏ qua rerank khi biên điểm RRF top-1 so với top-2 đã rõ; giới hạn 12 ứng viên |
| Cache ngữ nghĩa trả nhầm câu của loại xe khác | Câu hỏi "xe máy" nhận câu trả lời "ô tô" | Khoá cache là tổ hợp (vector, tập ý định, tập phương tiện), không chỉ vector; chỉ cache câu **đã qua kiểm chứng** |
| Cây phụ thuộc phình từ 8 lên khoảng 60 gói | `pip install` chậm, xung đột phiên bản | Chấp nhận theo quyết định đã chốt; cố định phiên bản, ghi rõ trong README; không thêm gói ngoài danh sách Phase 2 |
| `/api/ask` đang là `def` đồng bộ, LangGraph stream là async | SSE treo hoặc mất token | Đổi thành `async def` + `graph.astream()` ngay trong Phase 4, có test SSE riêng |

## Nguồn Tham Khảo

- LangChain v1 Agents API — https://docs.langchain.com/oss/python/langchain/agents
- LangGraph streaming và `get_stream_writer()` — https://docs.langchain.com/oss/python/langgraph/streaming
- LangChain và LangGraph 1.0 release — https://blog.langchain.com/langchain-langgraph-1dot0/
- LangGraph PyPI (1.2.x hiện hành) — https://pypi.org/project/langgraph/
- Hybrid search và EnsembleRetriever/RRF — https://apxml.com/courses/langchain-production-llm/chapter-4-production-data-retrieval/hybrid-search-implementation

## Quyết Định Đã Chốt Bổ Sung (từ Validation Interview)

1. **src/answer_guard.py và src/tools/**: **Giữ nguyên 100%**, chỉ bọc ngoài làm Node/Retriever trong LangGraph để triệt tiêu nguy cơ hồi quy logic nghiệp vụ đã kiểm chứng.
2. **Hệ thống quan trắc (Phase 7)**: Mặc định ghi **trace JSONL cục bộ** trong `data/runtime/traces/`, hỗ trợ LangSmith qua biến môi trường tùy chọn (`LANGSMITH_TRACING=true`).
3. **Mở rộng bộ benchmark (Phase 1)**: Giữ nguyên 35 câu cũ làm lõi, sinh bổ sung >= 45 câu từ corpus 6 văn bản (gồm cả câu hỏi bẫy/lạc đề) và **người dùng duyệt nghiệm thu** trước khi chốt baseline.
4. **Phụ thuộc tại api_server.py**: Tách hoàn toàn các endpoint phụ trợ (`/api/penalties`, `/api/health`) khỏi Agent bằng cách nạp trực tiếp `PenaltyLookup` và `DocumentProvider` độc lập.

## Validation Log

### Session 1 — 2026-09-09
**Trigger:** `/ak:plan validate` verification pass & critical assumptions interview
**Questions asked:** 4

#### Verification Results
- **Tier:** Full (8 phases)
- **Claims checked:** 16
- **Verified:** 15 | **Failed:** 1 | **Unverified:** 0
- **Failures:**
  1. [Contract Verifier] `src/api_server.py:208, 320` — gọi `get_agent().tools_handler` phụ thuộc `AgenticLegalSearch`. Đã xử lý giải phóng liên kết trong Quyết định 4.

#### Questions & Answers

1. **[Kiến trúc & Phạm vi]** Kế hoạch tái kiến trúc có nên giữ nguyên mã nguồn của `src/answer_guard.py` và `src/tools/` hay viết lại toàn bộ theo chuẩn LangChain?
   - **Lựa chọn:** Giữ nguyên hàm thuần và lớp dữ liệu hiện có (Recommended) | Viết lại toàn bộ theo chuẩn LangChain | Chỉ viết lại src/tools/
   - **Câu trả lời:** Giữ nguyên hàm thuần và lớp dữ liệu hiện có, chỉ bọc làm Node/Retriever trong LangGraph để tránh nguy cơ hồi quy logic đã kiểm chứng
   - **Lý do:** Giữ vững các thuật toán tất định đã chứng minh hoạt động chính xác trên văn bản thật; tránh tạo ra hồi quy chỉ vì mục tiêu đồng nhất cú pháp hình thức.

2. **[Quan trắc & Đánh đổi]** Chiến lược quan trắc và truy vết (Phase 7): Bạn muốn ưu tiên hệ thống trace JSONL cục bộ hay tích hợp LangSmith Cloud?
   - **Lựa chọn:** Mặc định ghi trace JSONL cục bộ trong data/runtime/traces/, hỗ trợ LangSmith qua biến môi trường tùy chọn (Recommended) | Chỉ dùng trace JSONL cục bộ hoàn toàn | Tích hợp và bật mặc định LangSmith Cloud
   - **Câu trả lời:** Mặc định ghi trace JSONL cục bộ trong data/runtime/traces/, hỗ trợ LangSmith qua biến môi trường tùy chọn (LANGSMITH_TRACING=true)
   - **Lý do:** Bảo mật dữ liệu câu hỏi của người dùng trên máy cục bộ theo mặc định; cho phép nhà phát triển bật LangSmith Cloud khi cần debug chuyên sâu mà không đổi mã nguồn.

3. **[Bộ dữ liệu Eval]** Phương án mở rộng bộ benchmark đánh giá từ 35 câu hiện tại lên >= 80 câu (phủ đủ 6 văn bản pháp luật và các câu hỏi ngoài phạm vi/tiêu cực)?
   - **Lựa chọn:** Giữ 35 câu cũ làm lõi, sinh bổ sung >= 45 câu từ corpus rồi bạn duyệt (Recommended) | Agent sinh mới toàn bộ >= 80 câu | Người dùng tự chuẩn bị thủ công
   - **Câu trả lời:** Giữ 35 câu cũ làm lõi, sinh bổ sung >= 45 câu (phủ 5 văn bản còn lại và câu hỏi lạc đề) từ corpus rồi bạn duyệt nghiệm thu
   - **Lý do:** Bảo toàn tính so sánh liên tục của baseline 35 câu đã đo, đồng thời mở rộng nhanh chóng vùng phủ sang 5 văn bản còn lại và câu hỏi bẫy/lạc đề với sự kiểm soát chất lượng từ con người.

4. **[Contract Verifier / Kiến trúc]** Các endpoint phụ trợ trong `src/api_server.py` (`/api/penalties` và `/api/health`) đang gọi `get_agent().tools_handler`. Khi thay thế `agentic_rag.py`, nên giải quyết liên kết này thế nào?
   - **Lựa chọn:** Tách hoàn toàn api_server.py khỏi Agent ở các endpoint này: nạp trực tiếp PenaltyLookup và DocumentProvider độc lập (Recommended) | src/agent.py phải bọc và expose lại thuộc tính tools_handler
   - **Câu trả lời:** Tách hoàn toàn api_server.py khỏi Agent ở các endpoint này: nạp trực tiếp PenaltyLookup và DocumentProvider độc lập
   - **Lý do:** Phân định ranh giới kiến trúc rõ ràng: Agent chỉ đảm nhận orchestration/hỏi đáp (`stream_agent`, `run_agent`), còn việc browse bảng mức phạt và đọc dữ liệu tĩnh thuộc trách nhiệm của Provider/Lookup chuyên trách.

#### Confirmed Decisions
- [x] Giữ nguyên `src/answer_guard.py` và `src/tools/`, chỉ bọc ngoài làm Node/Retriever.
- [x] Trace JSONL cục bộ là mặc định, LangSmith là tùy chọn cấu hình qua `.env`.
- [x] Mở rộng benchmark thành 35 câu cũ + >= 45 câu sinh từ corpus có con người duyệt.
- [x] Decouple `src/api_server.py` khỏi `AgenticLegalSearch.tools_handler`, khởi tạo trực tiếp `PenaltyLookup` và `DocumentProvider`.

#### Impact on Phases
- Phase 1: Xác nhận quy trình sinh bổ sung >= 45 câu benchmark kết hợp 35 câu cũ, đưa qua người dùng duyệt.
- Phase 4: Bổ sung nhiệm vụ tách `PenaltyLookup` và `DocumentProvider` độc lập trong `src/api_server.py` (`/api/penalties` và `/api/health`).
- Phase 7: Xác nhận kiến trúc tracer JSONL cục bộ là mặc định, LangSmith là adapter qua biến môi trường.
- Phase 8: Bổ sung kiểm thử độc lập cho các endpoint `/api/penalties` và `/api/health` sau khi gỡ bỏ hoàn toàn `AgenticLegalSearch`.

### Whole-Plan Consistency Sweep
- Files reread: `plan.md`, `phase-01-eval-harness-baseline.md`, `phase-02-langgraph-foundation.md`, `phase-03-hybrid-retrieval.md`, `phase-04-agent-graph.md`, `phase-05-verification-nodes.md`, `phase-06-memory-and-cache.md`, `phase-07-observability.md`, `phase-08-cutover-and-cleanup.md`
- Decision deltas checked: 4
- Reconciled stale references: 4 (đã đóng 3 câu hỏi mở, cập nhật coupling tại api_server.py)
- Unresolved contradictions: 0

<!-- slug: langgraph-agent-harness -->

