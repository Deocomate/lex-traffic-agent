# 🚗 LexTraffic AI — Trợ lý Pháp lý Giao thông trên LangGraph 1.x
> Hệ thống Trợ lý AI Pháp lý kết hợp **Agentic ReAct StateGraph** và **kho công cụ tra cứu chuyên sâu**, phủ **6 văn bản pháp luật giao thông**.

---

## 🌟 1. Kiến trúc: Agentic ReAct Loop kết hợp Lớp Kiểm Chứng Tất Định

Lớp điều phối là một `StateGraph` LangGraph 1.x (`src/graph/build.py`). Mô hình hoạt động theo cơ chế **Agentic ReAct Loop**: LLM trực tiếp nhận câu hỏi của người dùng, chủ động gọi các công cụ tra cứu động nhiều lượt (`keyword_search`, `get_article`, `penalty_lookup`, `traffic_sign_lookup`, `speed_limit_lookup`), xem xét bằng chứng thu được và quyết định tra cứu tiếp hoặc tổng hợp câu trả lời (chi tiết đầy đủ: [`docs/architecture.md`](docs/architecture.md)).

```
[Người dùng hỏi]
        │
        ▼
   [agent_node] ◀──────────┐ (Multi-turn ReAct: tối đa 4 lượt)
        │                  │
        ├──────tool_calls──┴──▶ [tools_node] (thực thi tool, phát SSE tool_call & tool_result)
        │
        ▼ (câu trả lời)
   [verify_node] ──sai──▶ [repair_node] (sửa tối đa 1 vòng) ──▶ verify
        │                                                           │
     đạt│                                                      vẫn sai
        ▼                                                           ▼
 [build_sources] ◀───────────────────────────────────────────── [cancel_node]
        │
        ▼
 [Câu trả lời đã kiểm chứng]
```

Trước khi đồ thị chạy, `src/graph/turn.py` tra **cache ngữ nghĩa** (mục "Bộ nhớ hội thoại và cache" bên dưới) — trúng cache thì đồ thị trả ngay kết quả đã kiểm chứng mà không cần gọi LLM.

**Cơ chế đảm bảo câu trả lời có căn cứ thật (lớp phòng vệ tất định, chạy bằng code):**

| Cơ chế | Mục đích |
|---|---|
| **Agentic ReAct đa lượt** | LLM tự chọn công cụ, xem xét bằng chứng và tra cứu sâu (ví dụ: phát hiện Điều 57 -> gọi tiếp `get_article(57)` để đọc đủ điểm p về hạng DE) |
| **Kiểm chứng số liệu** (`verify`) | Mọi mức tiền phạt, số tháng tước GPLX và số điểm bị trừ được đối chiếu trực tiếp với `raw_tool_output` nguyên văn của công cụ |
| **Kiểm chứng trích dẫn** | Trích dẫn Luật: Điều phải tồn tại và đã được tra cứu. Trích dẫn Nghị định: cặp Điểm/Khoản/Điều phải xuất hiện đúng trong kết quả |
| **Chặn gán tiền cho Luật** | Câu trả lời nêu mức tiền mà chỉ dẫn Điều/Khoản của Luật 36/2024 bị đánh dấu sai — Luật không quy định số tiền phạt |
| **Tự sửa một lần** (`repair`) | Phát hiện số liệu/trích dẫn không có căn cứ → model được chỉ đích danh lỗi và sửa lại, chặn cứng ở đúng 1 vòng qua `repair_count` |
| **Huỷ câu trả lời** (`cancel`, tất định) | Nếu sau khi sửa vẫn còn chi tiết sai, câu trả lời bị huỷ và thay bằng thông báo an toàn, không để lọt mức phạt sai lệch |
| **Fallback mô hình** | Tự chuyển sang `FALLBACK_LLM_MODEL` khi model chính lỗi/quá tải (`ModelFallbackTracker`) |
| **Cache ngữ nghĩa an toàn** | Chỉ cache câu **đã qua kiểm chứng** với ngưỡng cosine cao $\ge 0.97$ |

> Toàn bộ danh sách node, mô hình state + reducer, hợp đồng sự kiện SSE và cấu hình biến môi trường nằm ở [`docs/architecture.md`](docs/architecture.md).

---

## 📂 2. Cấu trúc Thư mục Dự án

Ba lớp, phụ thuộc một chiều — `src/` (engine) không biết gì về giao thông đường bộ:

```
app/  ──>  domains/<miền>/  ──>  src/
   └──────────────────────────────^
```

```
lex-traffic-agent/
├── src/                             ENGINE — không chứa tri thức miền nào
│   ├── domain/                      Nạp Domain Pack: schema.py, pack.py, registry.py
│   ├── graph/                       StateGraph: build, turn, agent_node, retrieve, verify, repair...
│   ├── retrieval/                   dense, sparse (BM25), fusion (RRF + chọn theo vách rơi),
│   │                                scope (phán đoán phạm vi), hybrid, cache, vi_text
│   ├── llm/                         provider.py (model theo vai trò + fallback), structured.py
│   ├── cache/                       semantic_cache.py, fingerprint.py
│   ├── observability/               tracer.py (JSONL), langsmith.py, pricing.py
│   ├── answer_guard.py              Kiểm chứng số liệu & dựng câu từ chối an toàn
│   ├── guard_figures.py             Cơ chế bóc số liệu (tiền tiếng Việt, số theo ngữ cảnh)
│   ├── paths.py                     Một nguồn sự thật cho thư mục gốc dự án
│   ├── semantic_index.py            Chỉ mục vector
│   └── agent.py                     Façade: stream_agent() / astream_agent() / run_agent()
│
├── domains/                         CÁC MIỀN — toàn bộ phần "biết về lĩnh vực"
│   └── vietnam_traffic/
│       ├── domain.yaml              Kho tài liệu, bộ công cụ, policy
│       ├── lexicon.yaml             Từ lóng, nhóm phương tiện, regex nhận diện ý định
│       ├── guard.yaml               Lớp số liệu cần kiểm chứng, dấu hiệu trích dẫn
│       ├── prompts/system.md        Persona & tri thức 6 văn bản pháp luật
│       ├── tools.py                 Hàm thực thi 7 công cụ
│       ├── evidence.py              Dựng bằng chứng có cấu trúc cho khối nguồn
│       ├── presentation.py          Câu chữ mô tả tiến trình tra cứu
│       ├── guard.py                 Kiểm chứng trích dẫn Điều/Khoản/Điểm
│       ├── corpus.py                Tra cấu trúc kho văn bản
│       └── lib/                     Nghiệp vụ: law_search_tools, penalty_lookup, document_provider
│
├── app/server.py                    ỨNG DỤNG — FastAPI: SSE /api/ask + API tra cứu
├── templates/ · static/             Giao diện web (Jinja2 + JS xử lý 14 sự kiện SSE)
│
├── data/
│   ├── raw_data/                    PDF gốc của 6 văn bản
│   ├── processed/                   Dữ liệu đã bóc tách + chỉ mục
│   │   ├── semantic_chunks.json     2.114 chunk con cho BM25 + dense
│   │   ├── semantic_index.npz       Vector 3072 chiều
│   │   ├── semantic_parents.json    Toàn văn Điều/biển báo cha
│   │   ├── bm25_index.pkl           Chỉ mục BM25
│   │   └── scope_reference.json     Mốc phạm vi ĐO từ corpus (thay SEMANTIC_FLOOR gõ tay)
│   ├── benchmark/                   qa_testset_v2.json (95 câu) & báo cáo eval
│   └── runtime/                     checkpoint, trace, cache — .gitignore, KHÔNG commit
│
├── scripts/
│   ├── chat.py                      CLI streaming
│   ├── cache_admin.py               Thống kê/dọn cache và thread hội thoại
│   ├── ingest/                      Dựng lại corpus & chỉ mục từ nguồn gốc
│   │   └── calibrate_scope.py       Đo mốc tham chiếu phạm vi từ corpus
│   └── eval/                        Bộ eval + cổng chặn hồi quy
│       └── offline_retrieval_eval.py  Đo truy xuất tất định, KHÔNG cần API key
│
├── tests/                           pytest, gồm test_domain_pack.py chạy trên một miền khác hẳn
├── docs/domain-pack.md              Hướng dẫn tạo miền mới
├── main.py                          Trình khởi chạy (--web / --chat / --eval)
└── README.md
```

---

## 🚀 3. Hướng Dẫn Chạy

### Bước 0: Cài đặt
```powershell
pip install -r requirements.txt
```
Sao chép `.env.example` thành `.env` và điền `OPENROUTER_API_KEY`. Dữ liệu và chỉ mục đã có sẵn
trong `data/processed/`; chỉ chạy lại các script `prepare_*.py` / `build_*_index.py` khi cần dựng
mới từ PDF gốc.

### Biến môi trường (`.env`, mẫu đầy đủ ở `.env.example`)

`.env` chỉ còn **cấu hình triển khai**. Mọi tham số điều chỉnh chất lượng truy xuất đã được gỡ bỏ — xem mục 7 của `docs/architecture.md` để biết chúng được thay bằng gì.

| Biến | Vai trò | Mặc định |
|---|---|---|
| `OPENROUTER_API_KEY` | Khoá API OpenRouter (bắt buộc) | — |
| `LLM_MODEL` | Model chạy vòng ReAct và viết câu trả lời. **Bắt buộc hỗ trợ Function Calling** | `deepseek/deepseek-v4-flash` |
| `FALLBACK_LLM_MODEL` | Model dự phòng khi `LLM_MODEL` lỗi/quá tải | `openai/gpt-oss-20b` |
| `EMBEDDING_MODEL` | Model nhúng, phải khớp số chiều với `semantic_index.npz` | `google/gemini-embedding-2` |
| `ACTIVE_DOMAIN` | Domain Pack đang dùng (tên thư mục trong `domains/`) | `vietnam_traffic` |
| `ENABLE_SEMANTIC_CACHE` | Bật cache câu trả lời đã kiểm chứng. Ngưỡng & TTL nằm trong `policy` của pack | `true` |
| `CHECKPOINT_DB_PATH`, `ANSWER_CACHE_DB_PATH` | Đường dẫn SQLite; để trống dùng `data/runtime/` | — |
| `TRACE_DIR` | Thư mục trace JSONL — **chứa toàn văn câu hỏi người dùng, không commit** | `data/runtime/traces` |
| `TRACE_RETENTION_DAYS` | Số ngày giữ tệp trace trước khi tự dọn | `14` |
| `LANGSMITH_TRACING` | Bật LangSmith Cloud — **khi bật, câu hỏi và câu trả lời rời khỏi máy này** | `false` |
| `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | Chỉ cần khi `LANGSMITH_TRACING=true` | — |

> **Ghi chú về reasoning token.** `max_tokens` của OpenRouter tính **cả reasoning token**. Model
> nghĩ quá dài sẽ chạm trần trước khi kịp viết xong câu trả lời — đo trên bộ trace 25 câu: 2 lệnh
> gọi dừng đúng ở 4.000 token và cho ra câu trả lời rỗng. Mã nguồn tự ghìm `reasoning.effort="low"`
> cho mọi vai trò (`src/llm/provider.py`); **không** dùng `reasoning.enabled=false` vì một số model
> (ví dụ `openai/gpt-oss-20b`) trả lỗi 400 *"Reasoning is mandatory for this endpoint"*.

### Dùng cho lĩnh vực khác

Engine không biết gì về giao thông. Tạo trợ lý cho quy chế nội bộ, hướng dẫn y khoa hay tài liệu nhân sự = viết một Domain Pack mới, không sửa code:

```bash
cp -r domains/vietnam_traffic domains/<miền_mới>   # rồi thay nội dung khai báo
echo "ACTIVE_DOMAIN=<miền_mới>" >> .env
```

Chi tiết ở **`docs/domain-pack.md`**.

### Cách 1: Menu khởi chạy trung tâm (khuyên dùng)
```powershell
python main.py
```

### Cách 2: Web App — giao diện chat với AI Agent
```powershell
python main.py --web
```
Máy chủ tự chọn cổng trống bắt đầu từ `8080` và mở trình duyệt. Thêm `--no-browser` nếu không muốn tự mở.

### Cách 3: Hỏi đáp qua CLI
```powershell
python main.py --chat
```

### Cách 4: Chạy kiểm thử & benchmark
```powershell
python main.py --eval
```

---

## 📊 4. Nguồn dữ liệu — cả 6 văn bản đã nạp

| Văn bản | Số Điều/mục | Ghi chú |
|---|---|---|
| Luật 36/2024/QH15 (Trật tự ATGT) | 89 Điều | Text từ nguồn số hóa vi.wikisource, PDF gốc là bản scan |
| Luật 35/2024/QH15 (Đường bộ) | 86 Điều | Đối soát 86/86 tiêu đề Điều với PDF gốc |
| Nghị định 168/2024/NĐ-CP | 55 Điều, 634 hành vi bị phạt | Parse từ vi.wikisource rồi kiểm chứng tự động; thay thế NĐ 100/2019 và 123/2021 từ 01/01/2025 |
| Thông tư 31/2019/TT-BGTVT (tốc độ) | 13 mục | Ma trận tốc độ tối đa & cự ly an toàn |
| Thông tư 73/2024/TT-BCA (CSGT) | 33 mục | Quy chuẩn tuần tra, kiểm soát, 4 trường hợp dừng xe |
| QCVN 41:2019/BGTVT (biển báo) | 453 mục | Biển báo & vạch kẻ đường kèm ảnh minh hoạ |

Tổng 1.308 mục gộp trong `all_legal_chunks.jsonl`, chia nhỏ thành 2.114 chunk con cho tầng
truy xuất BM25 + dense (`semantic_chunks.json`).

> **Nguyên tắc:** không OCR bản scan để lấy số tiền phạt. OCR sai một chữ số là sai mức phạt.
> Câu hỏi ngoài 6 văn bản trên nhận câu trả lời "chưa có dữ liệu" kèm nút tra cứu Google.

---

## 🧪 5. Chạy Eval

```powershell
# Retrieval: Hit@1/@3/@5, MRR, NDCG trên qa_testset_v2.json (95 câu)
python scripts/eval/retrieval_eval.py --retriever hybrid

# E2E qua đồ thị: độ chính xác trích dẫn, tỉ lệ số liệu không căn cứ, từ chối lạc đề, độ trễ, chi phí
python scripts/eval/e2e_eval.py --adapter graph

# So sánh với baseline đã chốt, trả exit code khác 0 nếu hồi quy
python scripts/eval/gate.py --baseline <baseline.json> --current <report.json>

# Tổng hợp trace JSONL: độ trễ p50/p95 theo node, chi phí, phân bố structured_tier
python scripts/eval/summarize_traces.py
```

Chạy bộ test đơn vị:
```powershell
pytest tests/ -q
```

---

## 🖥️ 6. Giao diện Web

Một thanh bên duy nhất dẫn tới 5 khu vực. Mỗi khu vực chỉ giữ đúng những nút cần cho việc của nó,
và chỉ nạp dữ liệu ở lần mở đầu tiên (PDF 61 MB không tải khi khởi động).

| Khu vực | Nội dung |
|---|---|
| 💬 **Hỏi đáp AI** | Chat với Agent, xem tiến trình tra cứu trực tiếp, chip nguồn mở toàn văn điều luật. Phiên trò chuyện lưu ở thanh bên (localStorage) |
| 📖 **Tra cứu luật** | Cây 9 Chương / 89 Điều, ô tìm từ khóa kèm trích đoạn, khung đọc toàn văn |
| 💰 **Bảng mức phạt** | 634 hành vi trong Nghị định 168/2024/NĐ-CP: khung tiền phạt, số điểm bị trừ, xử phạt bổ sung, trích dẫn Điểm/Khoản/Điều; lọc theo phương tiện và hành vi |
| 📄 **Văn bản gốc** | Bản PDF 68 trang của Luật 36/2024/QH15, xem ngay trong trang |
| ⚙️ **Quản trị hệ thống** | Model đang chạy (`/api/health`), tình trạng từng tệp dữ liệu/chỉ mục, kết quả benchmark gần nhất (`/api/benchmark`) |

Trong khu vực hỏi đáp: `Enter` gửi, `Shift+Enter` xuống dòng.

**Hệ thiết kế** (chi tiết ở [`docs/design-system.md`](docs/design-system.md)): sidebar navy
`#0f172a` với logo gradient emerald và thanh nhấn emerald ở mục đang mở; canvas trắng ngà
`#f8fafc`; thẻ trắng bo 12px đổ bóng nhẹ; màu theo ngữ nghĩa — **amber** cho tiền phạt, **rose**
cho vi phạm nghiêm trọng, **emerald** cho trạng thái hợp lệ, **blue** cho căn cứ pháp lý. Font
Inter + Plus Jakarta Sans (tiêu đề) + JetBrains Mono (mã).

### API

| Endpoint | Mô tả |
|---|---|
| `POST /api/ask` | Chạy đồ thị LangGraph (qua `src/agent.py::astream_agent`), trả luồng SSE (14 loại sự kiện, hợp đồng đầy đủ ở [`docs/architecture.md`](docs/architecture.md#13-hợp-đồng-sự-kiện-sse)). Thân yêu cầu nhận `question`, `history`, `thread_id` tuỳ chọn (bỏ trống thì máy chủ tự sinh, trả lại trong `done`). Sự kiện `done` kèm `answer`, `sources`, `verification_issues`, `needs_search`, `search`, `model_used`, `thread_id` |
| `GET /api/documents` | Danh sách cả 6 văn bản pháp luật kèm metadata |
| `GET /api/documents/{doc_id}/chapters` · `.../articles/{n}` | Mục lục và toàn văn Điều của một văn bản bất kỳ trong 6 văn bản |
| `GET /api/article/{n}` · `GET /api/chapters` | Tương thích ngược: toàn văn/mục lục Luật 36/2024 |
| `GET /api/search?q=` | Tìm từ khóa trong các Điều luật |
| `GET /api/penalties?vehicle=&q=&limit=` | Bảng tra 634 hành vi của Nghị định 168/2024/NĐ-CP (nạp trực tiếp qua `PenaltyLookup`, độc lập với Agent) |
| `GET /api/utilities/signs` · `/speed-matrix` · `/license-points` · `/road-markings` · `/police-patrol` | Biển báo, ma trận tốc độ, 12 điểm GPLX, vạch kẻ đường, quy chuẩn tuần tra CSGT |
| `GET /api/benchmark` | Báo cáo `data/benchmark/evaluation_report.json` gần nhất |
| `GET /api/trace/summary?since=` | Chỉ số quan trắc tổng hợp (độ trễ theo node, chi phí, cache hit rate, phân bố `structured_tier`) — **không bao giờ trả nội dung câu hỏi**, chỉ số liệu |
| `GET /api/pdf?doc=` | PDF gốc của văn bản (hỗ trợ range request) |
| `GET /api/health` | Model đang cấu hình, tình trạng từng tệp dữ liệu/chỉ mục (nạp trực tiếp qua `DocumentProvider`/`PenaltyLookup`, độc lập với Agent) |

### Bộ nhớ hội thoại và cache câu trả lời

Lịch sử hội thoại nằm ở **checkpointer SQLite phía máy chủ**, khoá theo `thread_id`, nên nó sống
qua F5 trình duyệt. Bỏ trống `thread_id` thì máy chủ tự sinh và trả về trong sự kiện `done`;
client gửi lại giá trị đó ở các lượt sau. Lịch sử được cắt theo **ngân sách token**
(`HISTORY_TOKEN_BUDGET`) chứ không theo số tin nhắn, phần bị cắt được tóm tắt lại thay vì mất hẳn.

Câu trả lời **đã qua kiểm chứng** được cache theo khoá tổ hợp `(intents, vehicles, doc_scope,
vân tay chỉ mục)`, rồi mới so cosine ở ngưỡng `SEMANTIC_CACHE_THRESHOLD`. Khoá tổ hợp là phần
quan trọng nhất: "ô tô vượt đèn đỏ" và "xe máy vượt đèn đỏ" có cosine rất cao nhưng mức phạt khác
hẳn, nên riêng độ tương đồng vector là không đủ an toàn ở miền này. Câu có `issues` hoặc
`needs_search` không bao giờ được ghi cache. Dựng lại chỉ mục làm đổi vân tay và toàn bộ cache tự
hết hiệu lực.

```bash
python scripts/cache_admin.py --stats           # tỉ lệ trúng cache, số thread đang giữ
python scripts/cache_admin.py --clear           # xoá toàn bộ câu trả lời đã cache
python scripts/cache_admin.py --prune-threads   # dọn thread không hoạt động quá 30 ngày
```

Mọi tệp trạng thái (checkpoint, cache, trace) nằm dưới `data/runtime/` và đã được `.gitignore` bỏ
qua — không commit.

> **Riêng tư trace:** tệp trace JSONL dưới `data/runtime/traces/` chứa **toàn văn câu hỏi người
> dùng**. Thư mục này chỉ nằm trên máy chạy server, nằm trong `.gitignore`. Endpoint
> `GET /api/trace/summary` chỉ trả số liệu tổng hợp, không bao giờ trả nội dung câu hỏi. Bật
> `LANGSMITH_TRACING=true` thì câu hỏi và câu trả lời **rời khỏi máy này**, gửi tới LangSmith Cloud.

> **Yêu cầu về model:** `ROUTER_LLM_MODEL`/`RERANK_LLM_MODEL` chỉ cần trả JSON có cấu trúc (tầng
> structured output 4 bậc tự xử lý model function-calling yếu — chi tiết ở
> [`docs/architecture.md`](docs/architecture.md#5-tầng-structured-output-4-bậc)). `LLM_MODEL`
> (vai trò `synthesize`/`repair`) không cần function calling — node `synthesize` không bind tool.
> Đổi `EMBEDDING_MODEL` thì phải chạy lại `python scripts/ingest/build_semantic_index.py` để dựng lại
> vector cho khớp số chiều.

---

## 📈 7. Trước / Sau tái kiến trúc

Xem trạng thái đo lường đầy đủ, kèm nguồn từng con số, ở
[`docs/architecture.md` §14](docs/architecture.md#14-trạng-thái-đo-lường-đọc-trước-khi-trích-dẫn-số-liệu-ở-nơi-khác).
Tóm tắt — **không con số nào dưới đây được trình bày như đã đạt mục tiêu trừ khi ghi rõ**:

| Chỉ số | Trước (harness ReAct cũ) | Sau (StateGraph, 95 câu) | Mục tiêu Phase 8 | |
|---|---|---|---|---|
| Hit@1 truy xuất | 51.4% (35 câu) | **72.15%** (79/95 câu) | >= 72% | ✅ |
| Hit@3 truy xuất | 82.9% | 83.54% | >= 92% | ❌ |
| MRR truy xuất | 0.66 | 0.7774 | >= 0.80 | ❌ |
| Độ trễ p50 | 28.5s | **30.9s** | không tăng quá 10% | ✅ (+8.6%) |
| Trích dẫn E2E | chưa đo | 63.29% | >= 95% | ❌ |
| Số liệu không căn cứ | chưa đo | 1.05% | 0% | ❌ (sát) |
| Từ chối câu lạc đề | chưa đo | 93.75% (tập lạc đề) / 87.50% (lượt 95 câu) | >= 90% | ⚠️ |
| Câu trả lời bị huỷ | 0% | 8.42% | không tăng | ❌ |
| Chi phí mỗi câu | — | $0.001670 | — | — |
| Bộ benchmark | 35 câu, chỉ phủ Luật 36 | **95 câu, phủ cả 6 văn bản** | >= 80 câu | ✅ |

Nguồn: `data/benchmark/final_evaluation_report.json` và
`scripts/eval/baselines/baseline-graph-phase8-260911.json`. Cache ngữ nghĩa đã xoá trước khi chạy
nên mọi câu đi đường lạnh.

`scripts/eval/gate.py` trên bộ đầy đủ trả **exit code 1**: qua cổng độ trễ, trượt 4 cổng chất lượng.
Đã chạy trọn pipeline trên **2 model** (`deepseek/deepseek-v4-flash` 95 câu, `openai/gpt-oss-20b`
25 câu); chưa model nào qua đủ cổng chất lượng.

**Nút thắt còn lại nằm ở tầng truy xuất, không phải prompt.** Trích dẫn đã lên từ 48% tới 63.29%
nhờ siết prompt; phần còn lại do truy xuất trả sai Điều, tập trung ở `03_nghi_dinh_168_2024_nd_cp`
(Hit@1 56.2%, MRR 0.5625 — thấp nhất trong 6 văn bản). Chi tiết ở
[`docs/architecture.md`](docs/architecture.md).
