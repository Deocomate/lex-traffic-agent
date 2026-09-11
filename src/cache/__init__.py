"""Gói cache của LexTraffic AI: vân tay chỉ mục và cache ngữ nghĩa câu trả lời."""

from src.cache.fingerprint import compute_index_fingerprint, get_index_fingerprint
from src.cache.semantic_cache import (
    SemanticAnswerCache,
    build_cache_key,
    get_semantic_cache,
    is_cacheable,
)

__all__ = [
    "compute_index_fingerprint",
    "get_index_fingerprint",
    "SemanticAnswerCache",
    "build_cache_key",
    "get_semantic_cache",
    "is_cacheable",
]
