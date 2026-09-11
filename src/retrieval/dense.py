"""
Tầng truy xuất vector dày (Dense Retriever) cho LexTraffic AI.
Bọc SemanticIndex hiện hữu thành BaseRetriever của LangChain, giữ nguyên
hoàn toàn hành vi phân cấp small-to-big và ma trận vector numpy trong RAM.
Tích hợp bộ nhớ đệm QueryVectorCache để triệt tiêu độ trễ gọi API cho các truy vấn lặp lại.
"""

import logging
import os
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from openai import OpenAI

from src.retrieval.cache import QueryVectorCache
from src.semantic_index import SemanticIndex

logger = logging.getLogger(__name__)


class CachedSemanticIndex(SemanticIndex):
    """
    Kế thừa SemanticIndex hiện có, bổ sung tầng cache vector truy vấn trên SQLite.
    Bảo toàn 100% logic search_chunks và retrieve_articles hiện hữu.
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        embedding_model: Optional[str] = None,
        client: Optional[OpenAI] = None,
        cache: Optional[QueryVectorCache] = None,
    ):
        if not base_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        super().__init__(base_dir, embedding_model=embedding_model, client=client)
        self.cache = cache or QueryVectorCache()

    def embed_query(self, query: str) -> np.ndarray:
        """
        Sinh vector L2 cho truy vấn, ưu tiên đọc từ cache đĩa.
        Nếu miss: gọi API embedding từ xa và tự động lưu vào cache.
        """
        if not query:
            return np.zeros(3072, dtype=np.float32)

        cached_vec = self.cache.get(query, self.embedding_model)
        if cached_vec is not None:
            return cached_vec

        # Gọi API gốc từ SemanticIndex
        vector = super().embed_query(query)
        self.cache.set(query, self.embedding_model, vector)
        return vector


class DenseRetriever(BaseRetriever):
    """
    Adapter chuẩn BaseRetriever của LangChain bọc quanh CachedSemanticIndex.
    Cho phép tích hợp mượt mà vào đồ thị LangGraph và các chuỗi Runnable.
    """

    index: Any
    top_k: int = 5
    doc_ids: Optional[List[str]] = None
    chunk_types: Optional[List[str]] = None
    floor: float = 0.0

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[CallbackManagerForRetrieverRun] = None
    ) -> List[Document]:
        """Truy xuất các tài liệu liên quan dưới dạng Document của LangChain."""
        articles = self.index.retrieve_articles(
            query,
            doc_ids=self.doc_ids,
            chunk_types=self.chunk_types,
            top_k=self.top_k,
            floor=self.floor,
        )
        documents = []
        for art in articles:
            content = art.get("page_content", "")
            meta = {k: v for k, v in art.items() if k != "page_content"}
            documents.append(Document(page_content=content, metadata=meta))
        return documents

    def retrieve_articles(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        top_k: Optional[int] = None,
        floor: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Ủy quyền trực tiếp về CachedSemanticIndex để tương thích ngược 100%."""
        return self.index.retrieve_articles(
            query,
            doc_ids=doc_ids or self.doc_ids,
            chunk_types=chunk_types or self.chunk_types,
            top_k=top_k or self.top_k,
            floor=self.floor if floor is None else floor,
        )

    def search_chunks(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        top_k: int = 16,
        floor: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Ủy quyền tìm kiếm chunk con về CachedSemanticIndex."""
        return self.index.search_chunks(
            query,
            doc_ids=doc_ids or self.doc_ids,
            chunk_types=chunk_types or self.chunk_types,
            top_k=top_k,
            floor=floor,
        )


_shared_dense_index: Optional[CachedSemanticIndex] = None


def get_cached_semantic_index(base_dir: Optional[str] = None) -> CachedSemanticIndex:
    """Lấy thể hiện CachedSemanticIndex dùng chung (singleton)."""
    global _shared_dense_index
    if _shared_dense_index is None:
        _shared_dense_index = CachedSemanticIndex(base_dir=base_dir)
    return _shared_dense_index


def get_dense_retriever(
    base_dir: Optional[str] = None,
    top_k: int = 5,
    doc_ids: Optional[List[str]] = None,
    chunk_types: Optional[List[str]] = None,
    floor: float = 0.0,
) -> DenseRetriever:
    """Tạo đối tượng DenseRetriever của LangChain."""
    idx = get_cached_semantic_index(base_dir)
    return DenseRetriever(
        index=idx,
        top_k=top_k,
        doc_ids=doc_ids,
        chunk_types=chunk_types,
        floor=floor,
    )
