# Kiến trúc LexTraffic AI — Agentic ReAct StateGraph

Tài liệu này mô tả kiến trúc điều phối hiện tại của LexTraffic AI: **Agentic ReAct StateGraph** xây dựng trên nền tảng LangGraph 1.x, thay thế cho mô hình pipeline thác nước (waterfall) cứng nhắc trước đây.

Hệ thống cho phép mô hình ngôn ngữ lớn (LLM) chủ động suy luận, lựa chọn công cụ tra cứu động qua nhiều lượt (multi-turn reasoning), đồng thời được bao bọc bởi lớp kiểm chứng pháp lý tất định (deterministic verification guardrails) để triệt tiêu hiện tượng bịa đặt số liệu hoặc sai lệch trích dẫn.

---

## 1. Triết lý kiến trúc: Agentic ReAct kết hợp Lớp Kiểm Chứng Tất Định

### 1.1 Vấn đề của mô hình cũ (Waterfall Pipeline)

> Toàn bộ mã nguồn của pipeline này **đã được gỡ khỏi repo** (~1.350 dòng). Phần dưới giữ lại để giải thích vì sao kiến trúc hiện tại được chọn.

Trong kiến trúc cũ, luồng xử lý bị cố định theo dạng tuyến tính:
`START -> normalize -> memory -> route -> fanout -> rerank -> compact -> synthesize -> verify -> repair -> END`.
Mô hình này bộc lộ các nhược điểm chí tử:
1. **Router LLM bóp méo câu hỏi**: Một model nhỏ đóng vai trò router thường diễn giải sai hoặc thu hẹp từ khóa (ví dụ câu hỏi *"Ai lái được hạng xe DE"* bị router viết lại thành *"quy định về xe máy hạng D, xe ô tô hạng D"* làm công cụ tìm kiếm bỏ sót hoàn toàn hạng DE).
2. **Compact làm mất thông tin pháp lý**: Hàm cắt ngắn ngữ cảnh (compact) giới hạn tài liệu ở 250 ký tự khiến các điểm, khoản ở cuối điều luật (như điểm p Khoản 1 Điều 57 về Hạng DE) bị cắt bỏ.
3. **Mô hình bị tước đoạt công cụ**: Node `synthesize` không được bind công cụ (`bind_tools([])`), chỉ được đọc kết quả một lần thụ động và hoàn toàn bất lực nếu lần truy xuất ban đầu thiếu dữ kiện.
4. **Độ trễ tích lũy**: Trải qua 14 node trung gian và nhiều lần gọi LLM nối tiếp khiến thời gian phản hồi kéo dài lên tới hàng trăm giây.

### 1.2 Giải pháp kiến trúc mới: Agentic ReAct Loop
1. **Agent tự chủ suy luận & chọn công cụ**: LLM nhận trực tiếp câu hỏi người dùng cùng toàn bộ schema công cụ chuyên biệt (`TrafficLawTools`). Mô hình tự quyết định gọi công cụ nào (`keyword_search`, `get_article`, `penalty_lookup`, `traffic_sign_lookup`, `speed_limit_lookup`), xem xét bằng chứng trả về và quyết định tra cứu tiếp hay tổng hợp câu trả lời.
2. **Tra cứu động nhiều lượt (Multi-turn ReAct)**: Tối đa 4 vòng lặp (`MAX_TURNS = 4`). Nếu kết quả tìm kiếm sơ bộ chỉ ra Điều 57, Agent có thể gọi tiếp `get_article(57)` để đọc nguyên văn điều luật đầy đủ.
3. **Lớp kiểm chứng tất định độc lập**: Sau khi Agent hoàn thành câu trả lời, node `verify` đối chiếu số liệu tiền phạt, thời gian tước GPLX, và số Điều/Khoản với dữ liệu gốc (`raw_tool_output`). Nếu có lỗi sai, hệ thống cho phép sửa 1 lần (`repair`), nếu vẫn không đạt sẽ kích hoạt `cancel` để từ chối an toàn thay vì cung cấp thông tin sai lệch.

---

## 2. Sơ đồ StateGraph

Khớp chính xác với `create_legal_graph()` trong `src/graph/build.py`:

```mermaid
flowchart TD
    START([START]) --> agent[agent: LLM ReAct Reasoning]
    
    agent -->|agent_router: tool_calls & turn < 4| tools[tools: Multi-Tool Execution & SSE]
    tools -->|ToolMessage & Evidence| agent
    
    agent -->|agent_router: final answer or max turns| verify[verify: Deterministic Citation Guard]
    
    verify -->|phát hiện lỗi & repair_count < 1| repair[repair: Targeted Correction]
    verify -->|vẫn còn lỗi & repair_count >= 1| cancel[cancel: Safe Refusal]
    verify -->|không có lỗi| build_sources[build_sources: Citations & Final Packaging]
    
    repair --> verify
    cancel --> build_sources
    build_sources --> END([END])
```

### Chi tiết luồng điều phối:
- **Đường tắt ngoài đồ thị (Semantic Cache)**: Trước khi kích hoạt StateGraph, `src/graph/turn.py::run_turn()` kiểm tra Semantic Cache trong SQLite. Nếu câu hỏi trùng khớp ngữ nghĩa (độ tương đồng cosine $\ge 0.97$), hệ thống phát ngay câu trả lời đã qua kiểm chứng trước đó qua SSE mà không tốn chi phí gọi LLM.
- **Node `agent` (`src/graph/agent_node.py`)**: Gọi mô hình LLM chính (`LLM_MODEL`) với các công cụ tra cứu được bind qua cơ chế Function Calling chuẩn. LLM stream các token trực tiếp tới người dùng hoặc sinh `tool_calls`.
- **Node `tools` (`src/graph/retrieve.py`)**: Thực thi song song hoặc tuần tự các tool calls do Agent yêu cầu, thu thập bằng chứng `Evidence`, cập nhật `agent_steps` cho giao diện UI, và phát các sự kiện SSE `tool_call` & `tool_result`.
- **Node `verify` (`src/graph/verify.py`)**: Đối chiếu câu trả lời với `raw_tool_output` nguyên bản.
- **Node `repair` (`src/graph/repair.py`)**: Nhắc nhở mô hình sửa đúng các điểm sai lệch về số liệu hoặc căn cứ pháp luật. Bị giới hạn cứng ở tối đa 1 lượt.
- **Node `cancel` (`src/graph/verify.py`)**: Thay thế câu trả lời sai bằng phản hồi từ chối an toàn (Safe Fallback).
- **Node `build_sources` (`src/graph/verify.py`)**: Định dạng danh sách nguồn trích dẫn pháp lý hiển thị trên giao diện người dùng.

---

## 3. Trạng thái Đồ thị (LegalAgentState)

Định nghĩa tại `src/graph/state.py`:

| Trường | Kiểu dữ liệu | Reducer | Mục đích |
|---|---|---|---|
| `messages` | `List[AnyMessage]` | `add_messages` | Danh sách tin nhắn trao đổi (HumanMessage, AIMessage, ToolMessage). Được quản lý bởi LangGraph Checkpointer. |
| `turn_count` | `int` | ghi đè | Số lượt ReAct hiện tại của Agent trong một phiên truy vấn (tối đa 4). |
| `evidence` | `List[Evidence]` | `operator.add` | Danh sách bằng chứng pháp lý thu thập được từ các công cụ tra cứu. |
| `agent_steps` | `List[Dict]` | `operator.add` | Vết thực thi của các công cụ, phục vụ vẽ timeline trên giao diện Web UI. |
| `packed_context` | `str` | ghi đè | Ngữ cảnh bằng chứng tổng hợp (dùng khi chạy sửa lỗi hoặc đối chiếu phụ). |
| `issues` | `List[str]` | ghi đè | Danh sách lỗi vi phạm phát hiện bởi node kiểm chứng `verify`. |
| `repair_count` | `int` | ghi đè | Số lần đã chạy qua node `repair` (chặn cứng tối đa 1 lần). |
| `sources` | `List[Dict]` | ghi đè | Danh mục văn bản, điều khoản trích dẫn định dạng sẵn cho UI. |

---

## 4. Kho Công Cụ Tra Cứu Pháp Luật (TrafficLawTools)

Bộ công cụ **do Domain Pack khai báo**, không còn là hằng số của engine:

- Khai báo (tên, mô tả, JSON Schema tham số): `domains/vietnam_traffic/domain.yaml`
- Hàm thực thi: `domains/vietnam_traffic/tools.py`
- Nghiệp vụ tra cứu: `domains/vietnam_traffic/lib/law_search_tools.py`

`src/graph/retrieve.py` chỉ tra tên công cụ trong pack rồi gọi — nó không biết trước công cụ nào tồn tại. Đổi miền là đổi cả bộ công cụ mà không sửa mã engine. Xem `docs/domain-pack.md`.

Các công cụ của miền giao thông (khai báo tại `domains/vietnam_traffic/domain.yaml`):

### 4.1 `penalty_lookup(violation_keyword: str)`
- **Chức năng**: Tra cứu 634 hành vi vi phạm, khung tiền phạt, hình thức phạt bổ sung, trừ điểm GPLX trên toàn văn Nghị định 168/2024/NĐ-CP (hiệu lực 01/01/2025). Dùng cho mọi câu hỏi về chế tài: nồng độ cồn, đèn đỏ, tốc độ, mũ bảo hiểm, vỉa hè...

### 4.2 `traffic_sign_lookup(sign_code_or_name: str)`
- **Chức năng**: Tra cứu mã hiệu, tên gọi, nhóm biển, quy chuẩn và hình ảnh minh họa Markdown của 453 biển báo giao thông và vạch kẻ đường theo QCVN 41:2019/BGTVT.

### 4.3 `speed_limit_lookup(query: str)`
- **Chức năng**: Tra cứu ma trận tốc độ tối đa cho phép (km/h) và khoảng cách an toàn tối thiểu (mét) theo Thông tư 31/2019/TT-BGTVT (trong/ngoài khu đông dân cư, đường đôi/hai chiều, cao tốc).

### 4.4 `keyword_search(keywords: str)`
- **Chức năng**: Tra cứu nhanh các điều khoản trong văn bản luật chứa từ khóa chính xác, tên hạng GPLX (A1, C1, B, DE...), số tuổi, con số cụ thể hoặc thuật ngữ pháp lý.

### 4.5 `semantic_search(question: str, doc_scope: str = "all")`
- **Chức năng**: Tìm kiếm ngữ nghĩa sâu (Dense Vector Search 3072 chiều) trên toàn bộ 6 văn bản (Luật 36, Luật 35, NĐ 168, TT 31, TT 73, QCVN 41). Dùng khi câu hỏi mô tả tình huống đời thường hoặc hỏi về quyền hạn tuần tra CSGT.

### 4.6 `get_article(article_number: int, doc_id: str = "01_luat_36_2024_qh15")`
- **Chức năng**: Lấy toàn văn một Điều luật cụ thể theo số hiệu và mã văn bản mà không qua bất kỳ khâu rút gọn hay tóm tắt nào.
- **Vai trò trong ReAct**: Cho phép Agent khi phát hiện nghi vấn (ví dụ tìm thấy Điều 57 liên quan đến phân hạng bằng lái) có thể chủ động gọi `get_article(57)` để đọc trọn vẹn tất cả các điểm a tới p và phân tích chi tiết.

### 4.7 `list_chapters()`
- **Chức năng**: Xem danh mục 9 Chương của Luật 36/2024/QH15 để định hướng phân vùng tra cứu khi câu hỏi có phạm vi rộng.

---

## 5. Lớp Kiểm Chứng Tất Định (Verification Guardrails)

Nằm tại `src/graph/verify.py` và `src/answer_guard.py`:

1. **Kiểm tra số liệu phạt (`find_ungrounded_figures`)**:
   - Quét câu trả lời tìm các mức tiền phạt (ví dụ: "4.000.000 - 6.000.000 đồng"), số tháng tước bằng lái, số điểm GPLX.
   - So khớp trực tiếp với `raw_tool_output` nguyên văn nhận được từ Nghị định 168/2024. Nếu Agent tự ý bịa số liệu không có trong văn bản, câu trả lời sẽ bị chặn ngay.
2. **Kiểm tra căn cứ pháp lý (`find_invalid_citations`)**:
   - Đảm bảo Điều luật được viện dẫn phải thực sự tồn tại và đã được tra cứu trong phiên làm việc.
   - Chặn hiện tượng gán mức phạt tiền cho Luật (Luật Giao thông đường bộ chỉ quy định nguyên tắc và hành vi bị nghiêm cấm; thẩm quyền quy định tiền phạt thuộc về Nghị định).

---

## 6. Hợp Đồng Sự Kiện SSE (Server-Sent Events)

Giao tiếp thời gian thực giữa backend và frontend (`static/js/agent-trace.js`, `static/js/chat.js`) thông qua 14 sự kiện SSE chuẩn:

| Sự kiện SSE | Nguồn phát | Mục đích hiển thị trên Web UI |
|---|---|---|
| `start` | `agent_node` | Khởi tạo phiên làm việc mới |
| `turn_start` | `agent_node` / `repair_node` | Bắt đầu một vòng suy luận ReAct (`turn=1..4`) |
| `tool_call` | `tools_node` | Hiển thị thẻ công cụ Agent đang gọi (tên tool, tham số) |
| `tool_result` | `tools_node` / `turn.py` (cache) | Hiển thị kết quả tóm tắt từ công cụ hoặc thông báo trúng cache |
| `model_fallback` | `provider.py` | Thông báo tự động chuyển sang mô hình dự phòng khi model chính quá tải/lỗi |
| `synthesizing` | `agent_node` | Bắt đầu giai đoạn tổng hợp lời giải đáp |
| `token` | `agent_node` / `turn.py` (cache) | Stream từng ký tự văn bản trực tiếp ra màn hình (`phase="answer"`) |
| `verifying` | `verify_node` | Trạng thái đang rà soát căn cứ pháp lý |
| `verified` | `verify_node` / `turn.py` (cache) | Xác nhận câu trả lời đã đối chiếu chính xác với văn bản gốc |
| `warning` | `cancel_node` | Cảnh báo câu trả lời có điểm nghi vấn / không đủ căn cứ, kích hoạt Safe Fallback |
| `answer_commit` | `agent_node` / `turn.py` (cache) | Chốt nội dung câu trả lời cuối cùng |
| `sources` | `build_sources_node` | Danh sách tài liệu tham chiếu (Điều luật, Nghị định, Biển báo) |
| `done` | `build_sources_node` | Hoàn tất phiên tra cứu, gửi kèm `thread_id` và đóng stream |
| `error` | Bất kỳ node nào / `agent.py` | Thông báo lỗi hệ thống hoặc ngoại lệ kết nối |

> **Lưu ý:** Sự kiện `answer_reset` đã ngừng phát theo thiết kế mới (nâng bản nháp từ khối suy nghĩ trực tiếp qua `answer_commit`).

---

## 7. Cấu Hình Biến Môi Trường (.env)

`.env` chỉ còn **cấu hình triển khai**: khoá API, chọn mô hình, chọn miền, đường dẫn lưu trữ. Không còn tham số nào điều chỉnh chất lượng truy xuất.

```dotenv
OPENROUTER_API_KEY=...            # bắt buộc
LLM_MODEL=deepseek/deepseek-v4-flash
FALLBACK_LLM_MODEL=openai/gpt-oss-20b
EMBEDDING_MODEL=google/gemini-embedding-2

ACTIVE_DOMAIN=vietnam_traffic     # chọn Domain Pack trong domains/

ENABLE_SEMANTIC_CACHE=true
TRACE_DIR=data/runtime/traces
TRACE_RETENTION_DAYS=14
LANGSMITH_TRACING=false
```

### 7.1 Vì sao không còn tham số hiệu chuẩn

15 biến đã được gỡ bỏ. Ba nhóm, ba lý do khác nhau:

| Biến cũ | Lý do gỡ |
|---|---|
| `RRF_K=30`, `RRF_WEIGHT_DENSE=0.6`, `RRF_WEIGHT_SPARSE=0.4` | RRF chuẩn (Cormack et al. 2009) chỉ đọc **thứ hạng** nên vốn miễn nhiễm với chênh lệch thang điểm giữa hai nhánh. Gắn trọng số quét tay vào chính là phá bỏ tính chất đó và buộc hiệu chuẩn lại mỗi khi đổi dữ liệu. Nay dùng RRF không trọng số, `k=60` là hằng số làm mượt của bài báo gốc nằm trong mã. |
| `HYBRID_RELEVANCE_FLOOR=60.0`, `SEMANTIC_FLOOR=0.58/0.62`, `SCORE_FLOOR=12.0`, `COVERAGE_FLOOR=0.40`, `RERANK_MARGIN`, `ENABLE_RERANK` | Ngưỡng tuyệt đối chỉ đúng với đúng corpus và đúng embedding model đã quét. Thay bằng: (a) cắt theo **vách rơi** trong phân bố điểm của chính lượt truy vấn — bất biến với thang điểm; (b) mốc phạm vi **đo từ corpus** bằng `scripts/ingest/calibrate_scope.py`. |
| `SEMANTIC_CACHE_THRESHOLD`, `CACHE_TTL_DAYS` | Là quyết định **rủi ro của miền**, chuyển vào `policy` trong `domains/<id>/domain.yaml`. Miền pháp lý đòi 0.97; miền hỏi đáp nội bộ nới hơn được. |
| `ROUTER_LLM_MODEL`, `RERANK_LLM_MODEL`, `HISTORY_TOKEN_BUDGET`, `CONTEXT_TOKEN_BUDGET` | Thuộc các node đã bị gỡ bỏ (router LLM, rerank, memory, compact). |
| `TEMPERATURE`, `MAX_TOKENS` | **Chưa từng được mã nguồn đọc.** `MODEL_ROLES` trong `src/llm/provider.py` đặt giá trị riêng cho từng vai trò. |

### 7.2 Hai tín hiệu Agent nhận thay cho ngưỡng lọc

Tầng truy xuất không còn âm thầm trả rỗng khi thấy điểm thấp. Nó luôn trả kết quả kèm tín hiệu để Agent tự quyết định:

```
[ĐỘ TIN CẬY TRUY XUẤT: MẠNH — nhóm kết quả đầu tách hẳn khỏi phần còn lại | vách rơi 61% ...]
[PHẠM VI: ⚠️ câu hỏi nhiều khả năng NẰM NGOÀI kho tài liệu — điểm khớp tốt nhất chỉ đạt 30% mốc tham chiếu]
```

Hai tín hiệu trả lời hai câu hỏi **khác nhau**, và đó là lý do phải có cả hai:

- **Độ tin cậy** (`src/retrieval/fusion.py`) đo *tương đối*: trong số ứng viên lấy về, có kết quả nào nổi bật hẳn không. Quyết định giữ lại bao nhiêu kết quả.
- **Phạm vi** (`src/retrieval/scope.py`) đo *tuyệt đối*: điểm khớp tốt nhất có đạt mức mà kho tài liệu thường đạt được không. Đây là thứ thay thế `SEMANTIC_FLOOR`.

Đo thực tế cho thấy vì sao không thể gộp làm một: câu *"hôm nay trời mưa có nên mang ô không"* vẫn cho vách rơi 55% (độ tin cậy MẠNH) vì BM25 tìm được đúng một đoạn trùng chữ ngẫu nhiên nổi bật hẳn lên. Tách biệt cao, mà hoàn toàn lạc đề.

Mốc tham chiếu phạm vi được **đo**, không gõ tay:

```bash
python scripts/ingest/calibrate_scope.py --labels data/benchmark/qa_testset_v2.json
```

Có ví dụ gán nhãn thì mốc được khớp để tối đa hoá (bắt đúng lạc đề − báo nhầm câu hợp lệ); không có thì lấy phân vị của phân bố điểm trên truy vấn giả sinh từ chính corpus. Kết quả trên miền giao thông: **bắt 16/16 câu lạc đề, báo nhầm 20%** — và là cảnh báo gắn kèm kết quả cho Agent đọc, không phải bộ lọc chặn như ngưỡng cũ.

---

## 8. Kiểm Thử & Đảm Bảo Chất Lượng

Dự án áp dụng bộ kiểm thử tinh gọn tốc độ cao (Smoke Test Suite) tại [`tests/test_smoke.py`](../tests/test_smoke.py):
- **Thời gian chạy**: ~5 giây.
- **Độ bao phủ**: Kiểm tra tra cứu từ khóa hạng DE, mức phạt đèn đỏ NĐ 168, đọc toàn văn Điều 57, biên dịch LangGraph StateGraph và tính sẵn sàng của Web API.
- **Lệnh chạy**:
  ```powershell
  pytest tests/
  ```

---

## 9. Trạng Thái Đo Lường & Đánh Giá Baseline

Trạng thái đo lường trên bộ benchmark đầy đủ 95 câu (`data/benchmark/qa_testset_v2.json`), phủ cả 6 văn bản pháp luật giao thông. Nguồn đối soát: `data/benchmark/final_evaluation_report.json` và `scripts/eval/baselines/baseline-graph-phase8-260911.json`.

| Chỉ số | Trước (harness ReAct cũ) | Sau (StateGraph, 95 câu) | Mục tiêu Phase 8 | Đánh giá |
|---|---|---|---|---|
| **Hit@1 truy xuất** | 51.4% (35 câu) | **72.15%** (79/95 câu) | >= 72% | ✅ Đạt |
| **Hit@3 truy xuất** | 82.9% | **83.54%** | >= 92% | ❌ Chưa đạt |
| **MRR truy xuất** | 0.66 | **0.7774** | >= 0.80 | ❌ Cận mục tiêu |
| **Độ trễ p50** | 28.5s | **30.9s** | không tăng quá 10% | ✅ Đạt (+8.6%) |
| **Trích dẫn E2E chính xác** | chưa đo | **63.29%** | >= 95% | ❌ Cần cải thiện |
| **Số liệu không căn cứ** | chưa đo | **1.05%** | 0% | ❌ Sát mục tiêu |
| **Từ chối câu lạc đề** | chưa đo | **93.75%** (tập lạc đề) / **87.50%** (lượt 95 câu) | >= 90% | ⚠️ Cận mục tiêu |
| **Tỷ lệ câu bị huỷ (Safe Fallback)** | 0% | **8.42%** | không tăng | ❌ Cần tối ưu |
| **Chi phí trung bình / câu** | — | **$0.001670** | — | Tiết kiệm |
| **Quy mô tập Benchmark** | 35 câu (chỉ Luật 36) | **95 câu (phủ cả 6 văn bản)** | >= 80 câu | ✅ Đạt |

### Phân tích nút thắt chất lượng:
- **Nút thắt nằm ở tầng truy xuất văn bản, không phải do Prompt**: Tỷ lệ trích dẫn đã cải thiện từ 48% lên 63.29% khi siết chặt prompt hệ thống. Phần lỗi còn lại chủ yếu do truy xuất trả sai số Điều, tập trung lớn nhất ở `03_nghi_dinh_168_2024_nd_cp` (Hit@1 đạt 56.2%, MRR 0.5625 do số lượng hành vi vi phạm dày đặc 634 mục).
- **Cổng đánh giá hồi quy (`scripts/eval/gate.py`)**: Hiện trả exit code 1 (vượt qua cổng độ trễ nhưng cần tiếp tục thu hẹp khoảng cách ở 4 cổng chất lượng trích dẫn). Mọi câu hỏi đánh giá đều được chạy ở chế độ đường lạnh (đã xóa Semantic Cache trước khi chạy).
