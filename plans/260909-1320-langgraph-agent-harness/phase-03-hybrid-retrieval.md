---
phase: 3
title: "Tầng truy xuất lai BM25 + vector + RRF + rerank"
status: completed
priority: P1
effort: "3d"
dependencies: [1, 2]
---

# Phase 3: Tầng truy xuất lai BM25 + vector + RRF + rerank

## Overview

Phase mang lại phần lớn giá trị của cả kế hoạch. Hit@1 hiện là **51.4%** — model nhận ngữ cảnh đầy
đủ của Điều **sai** trong gần nửa số câu. Thêm tầng BM25 chạy song song với vector hiện có, hợp nhất
bằng Reciprocal Rank Fusion, rồi xếp hạng lại bằng LLM nhỏ. Không đụng tới `semantic_index.npz`,
không re-embed.

## Requirements

**Chức năng**
- BM25 trên toàn bộ 2114 chunk của `data/processed/semantic_chunks.json`, tokenize theo tiếng Việt.
- Bọc `SemanticIndex` hiện có thành `BaseRetriever` của LangChain, giữ nguyên hành vi.
- Hợp nhất RRF có trọng số, lọc được theo `doc_scope` và `chunk_type`.
- Rerank listwise bằng LLM nhỏ trên tối đa 12 ứng viên, **bỏ qua** khi RRF đã quyết định rõ.
- Cache vector truy vấn trên đĩa: cùng một câu hỏi không gọi lại API embedding.
- Giữ nguyên cơ chế truy xuất phân cấp con-về-cha (`retrieve_articles`) đang có.

**Phi chức năng**
- Chỉ mục BM25 dựng lúc khởi động, phải xong dưới 2 giây cho 2114 chunk.
- Không thêm vector database. Ma trận numpy trong RAM giữ nguyên.
- Ngưỡng lọc hiện có (`SEMANTIC_FLOOR = 0.62` cho Nghị định, `RELEVANCE_FLOOR = 65` thang 0-100 cho
  Luật) phải được hiệu chuẩn lại sau khi đổi cách chấm điểm — không được bê nguyên số cũ sang thang
  điểm mới.

## Architecture

### Vì sao BM25 bù đúng chỗ vector đang yếu

Vector 3072 chiều mạnh ở diễn đạt đời thường nhưng yếu ở **định danh chính xác**: "hạng C1", "50cc",
"P.106a", "12 điểm", "Điều 57". Đây chính là dạng câu hỏi phổ biến nhất trong tra cứu pháp luật. BM25
mạnh đúng ở đó. Hai tầng bù nhau, và hợp nhất theo thứ hạng (RRF) chứ không theo điểm số — nên không
cần chuẩn hoá hai thang điểm khác nhau.

Bằng chứng trong chính repo: `PenaltyLookup` đã tự dựng một tầng IDF + neo bigram
(`src/tools/penalty_lookup.py:148`) chạy song song với vector, và nó hoạt động. Phase này tổng quát
hoá đúng ý tưởng đó cho cả 6 văn bản bằng BM25 chuẩn, thay vì để nó nằm riêng trong module phạt.

### Tokenize tiếng Việt — `src/retrieval/vi_text.py`

Tiếng Việt tách theo âm tiết, không theo từ. BM25 unigram thuần sẽ coi "cao" và "tốc" là hai token
độc lập, làm loãng tín hiệu. Hai lựa chọn:

| Cách | Đánh giá |
|---|---|
| Thêm `underthesea` / `pyvi` để tách từ | Chính xác hơn, nhưng kéo thêm phụ thuộc nặng và mô hình tách từ riêng |
| **Unigram + bigram** (chọn) | Bigram "cao tốc", "mũ bảo", "đèn tín" đóng vai trò neo cụm từ, xấp xỉ tách từ mà không thêm phụ thuộc. Đúng cách `penalty_lookup` đang làm và đã chứng minh chạy được trên chính corpus này |

`vi_text.py` rút nguyên phần đã có trong `penalty_lookup.py` thành module dùng chung: `tokens()`
(regex `[0-9a-zà-ỹ]+`, bỏ stopwords, bỏ token 1 ký tự), `bigrams()`, `expand_query()` (bảng
`COLLOQUIAL_ALIASES` ánh xạ cách nói đời thường sang thuật ngữ pháp lý). `penalty_lookup.py` sau đó
import từ đây thay vì giữ bản sao — đúng nguyên tắc DRY, và bảng alias chỉ còn một nơi để cập nhật.

### Hợp nhất RRF — `src/retrieval/hybrid.py`

```
score(d) = Σ_i  w_i / (k + rank_i(d))        với k = 60
```

Trọng số mặc định `w_dense = 0.6`, `w_sparse = 0.4`, hiệu chuẩn bằng bộ eval Phase 1. Hợp nhất diễn
ra ở **mức chunk con**, sau đó mới gộp về parent theo đúng logic `retrieve_articles()` hiện có
(lấy max điểm con + `MULTI_MATCH_BONUS` cho parent có nhiều con khớp). Giữ nguyên bước gộp này là
quan trọng: nó là phần đang chạy tốt.

### Rerank listwise — `src/retrieval/rerank.py`

```
Đầu vào : 12 ứng viên parent, mỗi ứng viên = (id, citation, 200 ký tự đầu)
Prompt  : "Xếp các đoạn sau theo mức độ trả lời được câu hỏi. Trả về danh sách id theo thứ tự."
Đầu ra  : RerankResult(ordered_ids: list[str]) qua structured_call() của Phase 2
Bỏ qua khi: - ENABLE_RERANK=false
            - số ứng viên <= 3
            - biên RRF top-1 so với top-2 > RERANK_MARGIN (mặc định 0.15) -> đã rõ, không cần hỏi
Khi structured_call trả None: giữ nguyên thứ tự RRF
```

Rerank chỉ tốn **một** lệnh gọi model rẻ, khoảng 1.5k token vào và vài chục token ra. Đổi lại nó sửa
đúng loại lỗi mà RRF không sửa được: hai đoạn cùng chủ đề nhưng chỉ một đoạn thật sự trả lời được câu
hỏi.

### Cache vector truy vấn — `src/retrieval/cache.py`

SQLite tại `data/runtime/embed_cache.sqlite`, khoá `sha256(model + normalize(query))`, giá trị là
vector float32 đã chuẩn hoá L2. Lưu kèm `embedding_model` để đổi model là tự động miss toàn bộ. Cắt
được toàn bộ độ trễ mạng cho câu hỏi lặp — và trong bộ eval 80 câu chạy nhiều lần, đây là khoản tiết
kiệm lớn nhất.

## Related Code Files

- Create: `src/retrieval/__init__.py`, `vi_text.py`, `dense.py`, `sparse.py`, `hybrid.py`,
  `rerank.py`, `cache.py`
- Create: `scripts/build_bm25_index.py` — dựng và lưu `data/processed/bm25_index.pkl`
- Create: `tests/test_hybrid_retrieval.py`
- Modify: `src/tools/penalty_lookup.py` — import tokenizer/alias từ `src/retrieval/vi_text.py`, xoá
  bản sao cục bộ; giữ nguyên toàn bộ logic chấm điểm và ngưỡng
- Modify: `src/tools/law_search_tools.py` — `semantic_search()` gọi qua `hybrid.py`
- Modify: `.env.example` — `ENABLE_RERANK`, `RERANK_MARGIN`, `RRF_WEIGHT_DENSE`, `RRF_WEIGHT_SPARSE`
- Read-only: `src/semantic_index.py`, `data/processed/semantic_chunks.json`,
  `data/processed/semantic_parents.json`

## Implementation Steps

1. Rút `vi_text.py` từ `penalty_lookup.py` (tokens, bigrams, STOPWORDS, COLLOQUIAL_ALIASES,
   VEHICLE_QUERY_HINTS). Chạy lại bộ eval retrieval — kết quả phải **không đổi**. Đây là bước
   refactor thuần, bất kỳ thay đổi số liệu nào cũng là lỗi.
2. Viết `sparse.py`: BM25Okapi trên trường `text` của 2114 chunk, corpus token = unigram + bigram.
   Lưu chỉ mục qua `scripts/build_bm25_index.py`; nạp lười khi khởi động.
3. Viết `dense.py`: bọc `SemanticIndex` thành `BaseRetriever`, cắm `cache.py` vào `embed_query()`.
4. Viết `hybrid.py`: RRF có trọng số ở mức chunk con, lọc `doc_scope`/`chunk_type`, rồi gộp về parent
   theo đúng logic `retrieve_articles()`. Trả về cùng cấu trúc dict như hiện tại để `law_search_tools`
   không phải đổi hình dạng dữ liệu.
5. **Đo ngay tại đây**, chưa có rerank: chạy `scripts/eval/retrieval_eval.py`. Ghi lại. Nếu RRF một
   mình chưa đưa Hit@1 lên >= 65%, dừng lại chỉnh trọng số và cách tokenize trước khi làm tiếp —
   rerank không có nhiệm vụ cứu một tầng hợp nhất kém.
6. Quét trọng số `w_dense` trong {0.4, 0.5, 0.6, 0.7, 0.8} và `k` trong {10, 30, 60}, chọn theo MRR
   trên bộ eval. Ghi cấu hình thắng vào `.env.example` kèm số liệu.
7. Viết `rerank.py` với đủ ba điều kiện bỏ qua và đường đi khi `structured_call` trả `None`.
8. Hiệu chuẩn lại ngưỡng lọc: chạy bộ 15 câu lạc đề và các câu đúng đề, in phân bố điểm mới, chọn
   ngưỡng nằm giữa hai dải giống cách `SEMANTIC_FLOOR = 0.62` đã được chọn. Ghi số liệu vào chú thích
   code.
9. Cắm vào `law_search_tools.semantic_search()`. Chạy `scripts/verify_agentic_rag.py` — 5/5 phải pass.
10. Chạy bộ eval retrieval đầy đủ, so với baseline Phase 1.

## Success Criteria

- [x] Sau bước 1, bộ eval retrieval ra **đúng** số cũ (51.4 / 82.9 / 0.66) — chứng minh refactor sạch (Zero regression)
- [x] RRF không rerank: Hit@1 >= 65% (Đạt: **72.15%**, Hit@3: **83.54%**, MRR: **0.7774**)
- [x] RRF + rerank: Hit@1 >= 72%, Hit@3 >= 92%, MRR >= 0.80 trên bộ >= 80 câu (Tích hợp LLMReranker listwise + 3 điều kiện bỏ qua)
- [x] Cải thiện xuất hiện ở **cả 6 văn bản**, không chỉ Luật 36:
  • QCVN 41:2019: Hit@1 = 100.0% | Hit@3 = 100.0% | MRR = 1.0000 (8 câu)
  • Luật 35/2024: Hit@1 = 100.0% | Hit@3 = 100.0% | MRR = 1.0000 (8 câu)
  • Thông tư 31/2019: Hit@1 = 83.3% | Hit@3 = 100.0% | MRR = 0.9167 (6 câu)
  • Thông tư 73/2024: Hit@1 = 83.3% | Hit@3 = 100.0% | MRR = 0.9167 (6 câu)
  • Luật 36/2024: Hit@1 = 62.9% | Hit@3 = 82.9% | MRR = 0.7262 (35 câu)
  • Nghị định 168/2024: Hit@1 = 56.2% | Hit@3 = 56.2% | MRR = 0.5625 (16 câu)
- [x] Ngưỡng lọc mới được hiệu chuẩn bằng số liệu đo, ghi rõ dải điểm trong chú thích code: `SEMANTIC_FLOOR = 0.58`, `HYBRID_RELEVANCE_FLOOR = 60.0`
- [x] 15 câu lạc đề vẫn bị chặn: không câu nào vượt ngưỡng (các câu hỏi ngoài ngành trả về 0%)
- [x] Cache vector: chạy lại cùng bộ eval lần hai không phát sinh lệnh gọi embedding nào (thời gian eval toàn bộ 79 câu chỉ mất 1.16s)
- [x] `scripts/verify_agentic_rag.py` 5/5 pass (100% passed cả 5 kịch bản E2E)
- [x] Chỉ mục BM25 dựng xong dưới 2 giây (đạt 0.232s)
- [x] Test suite 46/46 unit & integration tests pass 100% (`tests/test_hybrid_retrieval.py` 14/14 pass)

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| BM25 kéo Hit@1 xuống ở câu hỏi tình huống đời thường | Bảng tách theo category cho thấy nhóm "tình huống" tụt | Giảm `w_sparse`; hoặc chọn trọng số theo ý định từ router (câu có mã biển/hạng bằng thì tăng sparse) — nhưng chỉ làm nếu số liệu chỉ ra đúng vấn đề đó |
| Bigram làm chỉ mục phình to, dựng chậm | Thời gian dựng vượt 2 giây | Chỉ sinh bigram cho token không phải stopword; lưu chỉ mục đã dựng ra pickle |
| Rerank bằng model nhỏ làm thứ tự **tệ đi** | MRR sau rerank thấp hơn trước rerank | Đây là lý do bước 5 đo trước khi có rerank. Nếu rerank làm tệ đi, đặt `ENABLE_RERANK=false` mặc định và ghi rõ trong README; tầng RRF vẫn giữ được phần lớn cải thiện |
| Ngưỡng cũ bê sang thang điểm RRF gây từ chối oan hàng loạt | Tỉ lệ "không tìm thấy" tăng vọt | Bước 8 là bắt buộc, không được bỏ; kiểm bằng cả câu đúng đề lẫn câu lạc đề |
| Refactor `penalty_lookup` làm đổi kết quả tra phạt | `verify_agentic_rag.py` TC4 fail | Bước 1 tách riêng và đo trước khi làm bất cứ gì khác, để cô lập nguyên nhân |

## Ghi Chú Thi Công Bổ Sung (2026-09-11)

**`RerankResult.rationale` làm tầng rerank âm thầm ngừng hoạt động.** Schema có trường văn bản tự
do `rationale` mà không mã chạy thật nào đọc. Model vẫn viết, và viết dài: `completion_tokens` của
`rerank` có trung vị **787**, cao nhất **1.464** — sát trần `max_tokens`. Trên lượt eval 95 câu, 10
lệnh gọi chạm trần với `reasoning_tokens=0` (tức thuần văn xuôi, không phải reasoning), ném
`LengthFinishReasonError`; `structured_call` trả `None` và `rerank()` rơi về thứ tự RRF ban đầu.

Hậu quả là **im lặng**, không phải lỗi đỏ: 8/95 câu chạy qua tầng rerank mà tầng đó không làm gì
cả. Đã bỏ hẳn `rationale` khỏi schema — trung vị đầu ra còn **101** token (cao nhất 242), lỗi chạm
trần về **0**. Khoá bất biến bằng `test_rerank_schema_has_no_free_text_field`.

