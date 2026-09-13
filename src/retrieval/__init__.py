"""
Gói module truy xuất cho engine.

- vi_text : xử lý chuỗi và tách token tiếng Việt; từ vựng lĩnh vực đọc từ Domain Pack
- cache   : cache vector nhúng truy vấn trên đĩa (SQLite)
- dense   : BaseRetriever LangChain bọc chỉ mục vector
- sparse  : chỉ mục BM25Okapi
- fusion  : hợp nhất thứ hạng bằng RRF chuẩn và chọn kết quả theo vách rơi
- scope   : phán đoán câu hỏi có nằm trong phạm vi kho tài liệu không
- hybrid  : ghép dense + sparse rồi gộp về mục cha
"""

from src.retrieval.fusion import (
    RetrievalConfidence,
    reciprocal_rank_fusion,
    select_by_separation,
)
from src.retrieval.scope import ScopeSignal, get_scope_reference
from src.retrieval.vi_text import (
    BASE_STOPWORDS,
    bigrams,
    expand_query,
    normalize_text,
    preferred_entities,
    stopwords,
    tokens,
)

__all__ = [
    "RetrievalConfidence",
    "reciprocal_rank_fusion",
    "select_by_separation",
    "ScopeSignal",
    "get_scope_reference",
    "BASE_STOPWORDS",
    "bigrams",
    "expand_query",
    "normalize_text",
    "preferred_entities",
    "stopwords",
    "tokens",
]
