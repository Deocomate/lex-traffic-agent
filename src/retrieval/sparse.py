"""
Chỉ mục thưa BM25 (Sparse Retriever) trên 2114 chunk của corpus LexTraffic AI.
Sử dụng BM25Okapi với tokenizer unigram + bigram tiếng Việt và mở rộng truy vấn thông tục.
Nạp lười chỉ mục từ cache pickle (dưới 0.1s), tự động tái tạo nếu chưa có.
"""

import json
import logging
import os
import pickle
import time
from typing import Any, Dict, Iterable, List, Optional, Set

import numpy as np
from rank_bm25 import BM25Okapi

from src.retrieval.vi_text import bigrams, expand_query, tokens
from src.paths import project_root

logger = logging.getLogger(__name__)


class SparseIndex:
    """Bộ truy xuất BM25 cho toàn bộ 6 văn bản giao thông (2114 chunks)."""

    def __init__(self, base_dir: Optional[str] = None):
        if not base_dir:
            base_dir = project_root()
        self.base_dir = base_dir
        self.chunks_path = os.path.join(base_dir, "data", "processed", "semantic_chunks.json")
        self.index_path = os.path.join(base_dir, "data", "processed", "bm25_index.pkl")

        self.chunks: List[Dict[str, Any]] = []
        self._bm25: Optional[BM25Okapi] = None
        self._loaded: bool = False

    def _ensure_loaded(self) -> None:
        """Nạp lười chỉ mục BM25 và danh sách chunks khi cần gọi truy xuất."""
        if self._loaded:
            return

        t0 = time.time()
        if not os.path.exists(self.chunks_path):
            logger.error("Không tìm thấy file chunks tại: %s", self.chunks_path)
            return

        with open(self.chunks_path, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "rb") as f:
                    payload = pickle.load(f)
                if isinstance(payload, dict) and "bm25" in payload:
                    self._bm25 = payload["bm25"]
                elif isinstance(payload, BM25Okapi):
                    self._bm25 = payload
                logger.info(
                    "Đã nạp BM25 index từ pickle (%s chunks) trong %.3fs",
                    len(self.chunks),
                    time.time() - t0,
                )
            except Exception as e:
                logger.warning("Không thể nạp bm25_index.pkl (%s), đang dựng lại...", e)
                self._build_and_save()
        else:
            self._build_and_save()

        self._loaded = self._bm25 is not None and len(self.chunks) > 0

    def _build_and_save(self) -> None:
        """Dựng BM25 index và lưu ra đĩa."""
        t0 = time.time()
        tokenized_corpus = []
        for c in self.chunks:
            text = c.get("text", "")
            u = tokens(text)
            tokenized_corpus.append(u + list(bigrams(u)))

        self._bm25 = BM25Okapi(tokenized_corpus)
        try:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            payload = {
                "bm25": self._bm25,
                "num_chunks": len(self.chunks),
                "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self.index_path, "wb") as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info("Đã xây dựng và lưu BM25 index trong %.3fs", time.time() - t0)
        except Exception as e:
            logger.warning("Không thể lưu bm25_index.pkl: %s", e)

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._loaded

    def _resolve_doc_ids(self, raw_doc_ids: Optional[Iterable[str]]) -> Optional[Set[str]]:
        """Phân giải tên tài liệu hoặc nhóm sang mã chuẩn, theo khai báo của Domain Pack."""
        from src.domain.registry import get_active_domain

        return get_active_domain().resolve_doc_ids(raw_doc_ids)

    def tokenize_query(self, query: str) -> List[str]:
        """Tokenize câu hỏi, có mở rộng các thuật ngữ thông tục sang thuật ngữ pháp lý."""
        expanded_q, _ = expand_query(query)
        u = tokens(expanded_q)
        b = list(bigrams(u))
        return u + b

    def search_chunks(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        top_k: int = 16,
        floor: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm các chunk khớp nhất theo điểm BM25.

        Args:
            query: Câu hỏi hoặc từ khóa tra cứu.
            doc_ids: Giới hạn danh sách mã văn bản.
            chunk_types: Giới hạn loại chunk (vd: article, clause, sign, penalty).
            top_k: Số lượng chunk tối đa trả về.
            floor: Điểm BM25 tối thiểu để giữ lại.

        Returns:
            Danh sách chunk dict kèm trường 'score' là điểm BM25 tương ứng.
        """
        self._ensure_loaded()
        if not self._loaded or not query or self._bm25 is None:
            return []

        q_tokens = self.tokenize_query(query)
        if not q_tokens:
            return []

        scores = np.array(self._bm25.get_scores(q_tokens), dtype=np.float32)

        allowed_docs = self._resolve_doc_ids(doc_ids)
        allowed_types = set(chunk_types) if chunk_types else None

        if allowed_docs is not None or allowed_types is not None:
            mask = np.ones(len(self.chunks), dtype=bool)
            if allowed_docs is not None:
                mask &= np.array([c["doc_id"] in allowed_docs for c in self.chunks])
            if allowed_types is not None:
                mask &= np.array([c.get("type") in allowed_types for c in self.chunks])
            scores = np.where(mask, scores, -1.0)

        # Lấy top_k điểm cao nhất
        order = np.argsort(scores)[::-1][:top_k]
        results = []
        for i in order:
            s = float(scores[i])
            if s >= floor and s > 0:
                results.append({**self.chunks[i], "score": s})

        return results
