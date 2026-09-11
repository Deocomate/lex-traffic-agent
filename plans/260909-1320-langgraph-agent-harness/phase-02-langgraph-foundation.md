---
phase: 2
title: "Nền tảng LangChain/LangGraph và lớp model"
status: completed
priority: P1
effort: "1.5d"
dependencies: [1]
---

# Phase 2: Nền tảng LangChain/LangGraph và lớp model

## Overview

Đặt nền: thêm phụ thuộc đã ghim phiên bản, dựng lớp truy cập model qua LangChain (`ChatOpenAI` trỏ
tới OpenRouter, chuỗi fallback), và quan trọng nhất là **lớp structured output chịu được model yếu** —
thứ quyết định harness mới có chạy nổi với model nhỏ hay không.

## Requirements

**Chức năng**
- `get_chat_model(purpose)` trả về model đã cấu hình theo mục đích: `router` (rẻ, nhanh),
  `synthesize` (chất lượng), `rerank` (rẻ), `repair` (bằng `synthesize`).
- Chuỗi fallback tự động: model chính lỗi/quá tải -> `FALLBACK_LLM_MODEL`, và phát ra tín hiệu để
  đồ thị emit sự kiện `model_fallback`.
- `structured_call(model, schema, prompt)` trả về instance Pydantic đã validate, có **ba tầng** dự
  phòng cho model không hỗ trợ structured output tốt.
- Cấu hình hoàn toàn qua `.env`, giữ nguyên tên biến hiện có, chỉ thêm biến mới.

**Phi chức năng**
- Không phá vỡ `.env` hiện tại: `OPENROUTER_API_KEY`, `LLM_MODEL`, `FALLBACK_LLM_MODEL`,
  `EMBEDDING_MODEL` giữ nguyên ý nghĩa.
- Mọi lệnh gọi model đều `temperature = 0` trừ khi có lý do ghi rõ.
- Không import LangGraph vào lớp model — lớp này phải test được độc lập.

## Architecture

### Ghim phụ thuộc

```
# Agent harness (LangChain 1.x + LangGraph 1.x)
langchain>=1.0,<2
langchain-core>=1.0,<2
langchain-openai>=1.0,<2
langgraph>=1.2,<2
langgraph-checkpoint-sqlite>=2.0,<3
aiosqlite>=0.20.0
rank-bm25>=0.2.2
```

Ghim `<2` trên mọi gói LangChain: bản 1.0 cam kết không có breaking change tới 2.0, nên khoảng này
an toàn và tránh việc một lần `pip install` sau này làm gãy import.

### Lớp model — `src/llm/provider.py`

```python
MODEL_ROLES = {
    "router":     ("ROUTER_LLM_MODEL",     0.0, 512),
    "rerank":     ("RERANK_LLM_MODEL",     0.0, 256),
    "synthesize": ("LLM_MODEL",            0.0, 4000),
    "repair":     ("LLM_MODEL",            0.0, 4000),
}

def get_chat_model(purpose: str) -> BaseChatModel:
    env_key, temperature, max_tokens = MODEL_ROLES[purpose]
    primary = ChatOpenAI(
        model=os.getenv(env_key) or os.getenv("LLM_MODEL"),
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60, max_retries=2,
    )
    fallback = ...  # cùng cấu hình, model = FALLBACK_LLM_MODEL
    return primary.with_fallbacks([fallback])
```

Tách vai trò model là một tối ưu chi phí thật: node `router` và `rerank` chỉ cần model rẻ nhất có
structured output ổn, node `synthesize` mới cần model tốt. Mặc định cả ba đều lấy `LLM_MODEL` nếu
biến riêng không được đặt, nên `.env` hiện tại chạy được ngay không cần sửa.

### Structured output ba tầng — `src/llm/structured.py`

Đây là điểm sống còn với model nhỏ trên OpenRouter: nhiều model rẻ khai báo hỗ trợ function calling
nhưng thực tế trả JSON hỏng, thừa lời dẫn, hoặc bọc trong khối ```json.

```
Tầng 1: model.with_structured_output(Schema, method="json_schema")
        -> chuẩn nhất, dùng khi provider hỗ trợ
Tầng 2: prompt kèm JSON schema + PydanticOutputParser
        -> khi tầng 1 ném lỗi không hỗ trợ
Tầng 3: gọi thường + trích khối JSON đầu tiên bằng regex + json.loads + Schema.model_validate
        -> vớt model trả JSON lẫn văn xuôi
Tầng 4 (không phải LLM): trả None -> node gọi phải có đường đi tất định thay thế
```

Tầng 4 không phải chỗ để ném ngoại lệ. **Mọi node dùng structured output đều phải chạy đúng khi
nhận `None`** — với `router` nghĩa là dùng nguyên kết quả regex prior; với `rerank` nghĩa là giữ thứ
tự RRF. Nguyên tắc: LLM chỉ được phép **cải thiện** kết quả tất định, không bao giờ là điều kiện cần
để hệ thống chạy.

### Biến môi trường mới (đều tuỳ chọn)

```
ROUTER_LLM_MODEL=        # mặc định = LLM_MODEL
RERANK_LLM_MODEL=        # mặc định = LLM_MODEL
ENABLE_RERANK=true
ENABLE_SEMANTIC_CACHE=true
LANGSMITH_TRACING=false
TRACE_DIR=data/runtime/traces
```

## Related Code Files

- Create: `src/llm/__init__.py`, `src/llm/provider.py`, `src/llm/structured.py`
- Create: `tests/test_llm_structured.py`
- Modify: `requirements.txt` — thêm khối phụ thuộc harness đã ghim
- Modify: `.env.example` — thêm 6 biến mới kèm chú thích tiếng Việt theo đúng phong cách hiện có
- Read-only: `src/agentic_rag.py` (tham chiếu `_stream_completion` để giữ nguyên hành vi fallback)

## Implementation Steps

1. Cập nhật `requirements.txt`, chạy `pip install -r requirements.txt`, ghi lại phiên bản thực tế đã
   cài vào `docs/` ở Phase 8.
2. Viết `src/llm/provider.py` với `MODEL_ROLES` và `get_chat_model()`; bọc `.with_fallbacks()` và
   một callback nhỏ ghi nhận model thực tế đã dùng để đồ thị biết có fallback hay không.
3. Viết `src/llm/structured.py` với `structured_call()` bốn tầng như trên; log rõ tầng nào được dùng
   (sẽ hữu ích ở Phase 7 để biết model nào yếu structured output).
4. Viết `tests/test_llm_structured.py`: giả lập model trả (a) JSON chuẩn, (b) JSON bọc trong ```json,
   (c) JSON lẫn văn xuôi, (d) rác hoàn toàn. Ba trường hợp đầu phải parse ra đúng object, trường hợp
   cuối phải trả `None` chứ không được ném ngoại lệ.
5. Smoke test thật: gọi `get_chat_model("router")` với `.env` hiện tại, hỏi một câu, xác nhận có
   phản hồi; rồi cố tình đặt `LLM_MODEL` sai để xác nhận fallback kích hoạt.
6. Cập nhật `.env.example`.

## Success Criteria

- [x] `pip install -r requirements.txt` thành công trên Python 3.12/Windows
- [x] `python -c "from src.llm.provider import get_chat_model; get_chat_model('router')"` chạy không lỗi
- [x] `pytest tests/test_llm_structured.py` xanh, gồm cả ca model trả rác -> `None`
- [x] Đặt `LLM_MODEL` sai -> fallback kích hoạt và ghi nhận được model thực dùng
- [x] `.env` hiện tại chạy được không cần thêm biến nào (mọi biến mới đều có mặc định)
- [x] Không có gói nào ngoài danh sách đã ghim bị kéo vào như phụ thuộc trực tiếp

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| `langchain-openai` không truyền được `base_url` OpenRouter đúng cách | Lỗi 401/404 khi smoke test | Đặt cả `base_url` lẫn `OPENAI_BASE_URL`; nếu vẫn hỏng, dùng `ChatOpenAI(client=...)` với client OpenAI SDK cấu hình sẵn như code hiện tại |
| Xung đột phiên bản với `openai>=1.40` đang có | `pip` báo conflict | `langchain-openai` phụ thuộc `openai` SDK; nới cận dưới `openai` thay vì ghim cứng |
| Model nhỏ luôn rơi xuống tầng 3 | Log cho thấy tầng 3 chiếm đa số | Chấp nhận — miễn parse ra được. Nếu cả tầng 3 cũng hỏng thường xuyên, đổi `ROUTER_LLM_MODEL` sang model rẻ khác; kiến trúc đã có đường đi khi `None` |
| `with_fallbacks` nuốt mất thông tin model thực dùng | Sự kiện `model_fallback` không bao giờ phát | Dùng callback `on_llm_start` đọc `serialized["kwargs"]["model_name"]`; nếu không lấy được thì bọc thủ công bằng try/except như `_stream_completion` cũ |
