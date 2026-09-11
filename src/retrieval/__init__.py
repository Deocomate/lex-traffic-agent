"""
Gói module truy xuất (Retrieval) cho LexTraffic AI.
Bao gồm:
- vi_text: Xử lý chuỗi, tokenizer unigram/bigram tiếng Việt, mở rộng truy vấn và alias pháp lý
- cache: Cache vector nhúng truy vấn SQLite trên đĩa
- dense: BaseRetriever LangChain bọc SemanticIndex hiện hữu
- sparse: Chỉ mục BM25Okapi trên corpus 2114 chunk
- hybrid: Hợp nhất RRF (Reciprocal Rank Fusion) có trọng số và gộp về parent chunk
- rerank: Xếp hạng lại ứng viên bằng mô hình nhỏ qua structured output
"""

from src.retrieval.vi_text import (
    STOPWORDS,
    COLLOQUIAL_ALIASES,
    VEHICLE_QUERY_HINTS,
    normalize_text,
    tokens,
    bigrams,
    expand_query,
    preferred_vehicles,
)

__all__ = [
    "STOPWORDS",
    "COLLOQUIAL_ALIASES",
    "VEHICLE_QUERY_HINTS",
    "normalize_text",
    "tokens",
    "bigrams",
    "expand_query",
    "preferred_vehicles",
]
