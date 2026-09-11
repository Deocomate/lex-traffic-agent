"""
Bộ tính toán chỉ số đo lường hiệu năng RAG (Metrics Calculation)
Cung cấp các hàm toán học thuần túy:
- Retrieval: Hit@k, MRR, nDCG@k
- End-to-End: Citation Accuracy, Ungrounded Figure Rate, Refusal Accuracy
- System: Latency percentiles (p50, p90, p95), Cost Estimation
"""

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Union


# Bảng giá ước tính theo 1M token (USD) trên OpenRouter / OpenAI
# Cập nhật theo biểu giá thực tế các dòng mô hình nhỏ và phổ biến
MODEL_PRICING_PER_1M = {
    "default": {"prompt": 0.15, "completion": 0.60},
    "deepseek/deepseek-chat": {"prompt": 0.14, "completion": 0.28},
    "qwen/qwen-2.5-7b-instruct": {"prompt": 0.05, "completion": 0.10},
    "qwen/qwen-2.5-14b-instruct": {"prompt": 0.12, "completion": 0.24},
    "meta-llama/llama-3.1-8b-instruct": {"prompt": 0.06, "completion": 0.06},
    "openai/gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "google/gemini-2.0-flash-001": {"prompt": 0.10, "completion": 0.40},
}


def _normalize_id(val: Any) -> str:
    """Chuẩn hóa ID hoặc số Điều về chuỗi viết thường để so khớp"""
    if val is None:
        return ""
    return str(val).strip().lower()


def hit_at_k(
    retrieved_ids: Sequence[Any],
    target_id: Union[Any, Sequence[Any], Set[Any]],
    k: int
) -> float:
    """
    Hit Rate @ k: 1.0 nếu target_id (hoặc bất kỳ target hợp lệ nào)
    nằm trong top k kết quả truy xuất, ngược lại 0.0.
    """
    if k <= 0 or not retrieved_ids or target_id is None:
        return 0.0

    top_k = [_normalize_id(x) for x in retrieved_ids[:k]]
    
    if isinstance(target_id, (list, tuple, set)):
        targets = {_normalize_id(t) for t in target_id if t is not None}
        return 1.0 if any(t in top_k for t in targets) else 0.0
    
    target_norm = _normalize_id(target_id)
    return 1.0 if target_norm in top_k else 0.0


def reciprocal_rank(
    retrieved_ids: Sequence[Any],
    target_id: Union[Any, Sequence[Any], Set[Any]]
) -> float:
    """
    Reciprocal Rank (RR): 1 / rank của kết quả đúng đầu tiên (1-indexed).
    Nếu không tìm thấy trong danh sách, trả về 0.0.
    """
    if not retrieved_ids or target_id is None:
        return 0.0

    targets = {_normalize_id(t) for t in target_id} if isinstance(target_id, (list, tuple, set)) else {_normalize_id(target_id)}
    
    for idx, item in enumerate(retrieved_ids):
        if _normalize_id(item) in targets:
            return 1.0 / (idx + 1)
            
    return 0.0


def ndcg_at_k(
    retrieved_ids: Sequence[Any],
    target_id: Union[Any, Sequence[Any], Set[Any]],
    k: int = 5
) -> float:
    """
    Normalized Discounted Cumulative Gain @ k với binary relevance (0 hoặc 1).
    IDCG@k cho bài toán 1 target liên quan = 1 / log2(1 + 1) = 1.0.
    Nếu target xuất hiện ở thứ hạng r (1 <= r <= k), nDCG@k = 1 / log2(r + 1).
    Nếu không xuất hiện trong top k, trả về 0.0.
    """
    if k <= 0 or not retrieved_ids or target_id is None:
        return 0.0

    targets = {_normalize_id(t) for t in target_id} if isinstance(target_id, (list, tuple, set)) else {_normalize_id(target_id)}
    
    for idx, item in enumerate(retrieved_ids[:k]):
        if _normalize_id(item) in targets:
            rank = idx + 1
            dcg = 1.0 / math.log2(rank + 1)
            idcg = 1.0 / math.log2(1 + 1)  # = 1.0
            return dcg / idcg

    return 0.0


def _normalize_text_for_matching(text: Any) -> str:
    """Loại bỏ khoảng trắng thừa và chuẩn hóa chuỗi phục vụ kiểm tra regex"""
    if not text:
        return ""
    if isinstance(text, dict):
        text = " ".join(
            str(v)
            for k, v in text.items()
            if k in ("citation", "doc_name", "title", "header", "content", "sign_code", "doc_short") and v
        )
    elif not isinstance(text, str):
        text = str(text)
    return re.sub(r'\s+', ' ', text.strip().lower())


def check_citation_accuracy(
    answer: str,
    sources: Sequence[Any],
    expected_citation: Optional[str]
) -> Optional[bool]:
    """
    Độ chính xác trích dẫn E2E:
    - Nếu không yêu cầu trích dẫn cụ thể (expected_citation is None or empty), trả về None.
    - Nếu có expected_citation:
      1. Nội dung trích dẫn (hoặc các thành phần then chốt như Điều X, Khoản Y)
         phải xuất hiện trong văn bản `answer`.
      2. Ít nhất một tài liệu liên quan phải xuất hiện trong `sources`.
    """
    if not expected_citation or not expected_citation.strip():
        return None

    if not answer:
        return False

    norm_ans = _normalize_text_for_matching(answer)
    norm_exp = _normalize_text_for_matching(expected_citation)
    
    # 1. Kiểm tra trích dẫn nguyên văn trước
    if norm_exp in norm_ans:
        answer_has_citation = True
    else:
        # Nếu mô hình tách từ (vd "khoản 9, điều 6" thay vì "khoản 9 điều 6"), bóc các token chính:
        tokens = re.findall(r'(?:điểm\s+[a-zđ]|khoản\s+\d+|điều\s+\d+|nghị\s*định\s*\d+|thông\s*tư\s*\d+|qcvn\s*\d+)', norm_exp)
        if tokens:
            answer_has_citation = all(tok in norm_ans for tok in tokens)
        else:
            answer_has_citation = False

    if not answer_has_citation:
        return False

    # 2. Phải có ít nhất 1 source trích dẫn được ghi nhận
    if not sources or len(sources) == 0:
        return False

    norm_sources = [_normalize_text_for_matching(s) for s in sources]
    # Nguồn tra cứu phải chứa dấu vết của văn bản hoặc điều luật
    match_source = False
    dieu_match = re.search(r'điều\s+(\d+)', norm_exp)
    dieu_str = f"điều {dieu_match.group(1)}" if dieu_match else None

    for s in norm_sources:
        if norm_exp in s:
            match_source = True
            break
        if dieu_str and dieu_str in s:
            match_source = True
            break

    return match_source


def check_out_of_scope_refusal(
    is_out_of_scope: bool,
    needs_search: bool,
    answer: str,
    claimed_money_count: int = 0
) -> Optional[bool]:
    """
    Kiểm tra khả năng từ chối đúng khi câu hỏi nằm ngoài phạm vi (out-of-scope / negative):
    - Đạt chuẩn khi: needs_search == True (yêu cầu tra ngoài/từ chối khẳng định)
      VÀ không tự sinh ra số tiền phạt tùy tiện.
    """
    if not is_out_of_scope:
        return None

    # Phải kích hoạt cờ tìm kiếm ngoài hoặc nhận diện chưa đủ dữ liệu
    refused_properly = bool(needs_search)
    no_hallucinated_fine = (claimed_money_count == 0)
    return refused_properly and no_hallucinated_fine


def percentile(data: Sequence[float], p: float) -> float:
    """Tính phân vị p (0 <= p <= 100) trên dãy dữ liệu"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    if len(sorted_data) == 1:
        return float(sorted_data[0])
    
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_data[int(k)])
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return float(d0 + d1)


def compute_latency_stats(latencies_ms: Sequence[float]) -> Dict[str, float]:
    """Tính các thống kê độ trễ (ms): mean, p50, p90, p95, min, max"""
    if not latencies_ms:
        return {
            "count": 0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p95_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
        }
    
    values = [float(x) for x in latencies_ms]
    return {
        "count": len(values),
        "mean_ms": round(sum(values) / len(values), 2),
        "p50_ms": round(percentile(values, 50.0), 2),
        "p90_ms": round(percentile(values, 90.0), 2),
        "p95_ms": round(percentile(values, 95.0), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


def estimate_token_cost(
    tokens_in: int,
    tokens_out: int,
    model: str = "default"
) -> float:
    """Ước tính chi phí tính bằng USD dựa trên số token vào/ra"""
    pricing = MODEL_PRICING_PER_1M.get(model, MODEL_PRICING_PER_1M["default"])
    cost_prompt = (tokens_in / 1_000_000.0) * pricing["prompt"]
    cost_completion = (tokens_out / 1_000_000.0) * pricing["completion"]
    return round(cost_prompt + cost_completion, 6)
