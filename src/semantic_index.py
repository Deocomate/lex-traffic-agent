"""
Chỉ mục ngữ nghĩa (Dense Vector Index) trên kho tài liệu của Domain Pack đang hoạt động.

Danh sách tài liệu, alias và nhóm do pack khai báo, không còn hardcode ở đây.

Truy xuất phân cấp (small-to-big): khớp ở mức đoạn con cho chính xác ngữ nghĩa, rồi trả toàn
văn mục cha (kèm hình ảnh minh họa nếu có) để mô hình có đủ ngữ cảnh kết luận.
"""

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Set

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

from src.paths import project_root

load_dotenv(os.path.join(project_root(), ".env"))

CHILD_POOL_SIZE = 16
MULTI_MATCH_BONUS = 0.05

# Bảng phân giải tên tài liệu KHÔNG còn nằm ở đây.
#
# Trước đây module này chứa cứng `DOC_ALIASES` (18 alias) và `DOC_GROUPS` (5 nhóm) của đúng 6
# văn bản giao thông. Giờ chúng do Domain Pack khai báo (`domains/<id>/domain.yaml`), nên thêm
# hay bớt tài liệu là sửa cấu hình chứ không sửa mã nguồn engine.
#
# Hai hàm dưới giữ lại đúng hình dạng dữ liệu cũ cho mã đã dùng chúng.


def doc_aliases() -> Dict[str, str]:
    """Alias -> mã tài liệu chuẩn, lấy từ Domain Pack đang hoạt động."""
    from src.domain.registry import get_active_domain

    return get_active_domain().aliases


def doc_groups() -> Dict[str, List[str]]:
    """Tên nhóm -> danh sách mã tài liệu, lấy từ Domain Pack đang hoạt động."""
    from src.domain.registry import get_active_domain

    return get_active_domain().groups


class SemanticIndex:
    """Bộ truy xuất vector dùng chung cho toàn bộ 6 văn bản pháp luật giao thông"""

    def __init__(self, base_dir: str, embedding_model: Optional[str] = None,
                 client: Optional[OpenAI] = None):
        processed_dir = os.path.join(base_dir, "data", "processed")
        self.chunks_path = os.path.join(processed_dir, "semantic_chunks.json")
        self.vectors_path = os.path.join(processed_dir, "semantic_index.npz")
        self.parents_path = os.path.join(processed_dir, "semantic_parents.json")

        self.embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "google/gemini-embedding-2")
        self._client = client
        self.chunks: List[Dict[str, Any]] = []
        self.parents: Dict[str, Dict[str, Any]] = {}
        self.vectors: Optional[np.ndarray] = None
        self._load()

    def _load(self) -> None:
        if not all(os.path.exists(p) for p in (self.chunks_path, self.vectors_path, self.parents_path)):
            return
        try:
            with open(self.chunks_path, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)
            with open(self.parents_path, "r", encoding="utf-8") as f:
                self.parents = json.load(f)
            self.vectors = np.load(self.vectors_path)["embeddings"]

            if len(self.chunks) != len(self.vectors):
                # Chỉ mục lệch với dữ liệu -> coi như không khả dụng
                self.chunks, self.vectors = [], None
        except Exception as e:
            print(f"[SemanticIndex] Lỗi khi nạp chỉ mục: {e}")
            self.chunks, self.vectors = [], None

    @property
    def available(self) -> bool:
        return self.vectors is not None and len(self.chunks) > 0

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
                timeout=30.0,
                max_retries=2
            )
        return self._client

    def doc_ids(self) -> List[str]:
        return sorted({c["doc_id"] for c in self.chunks})

    def _resolve_doc_ids(self, raw_doc_ids: Optional[Iterable[str]]) -> Optional[Set[str]]:
        """Phân giải tên văn bản, alias hoặc nhóm văn bản thành tập hợp doc_id chuẩn"""
        if not raw_doc_ids:
            return None
        resolved: Set[str] = set()
        for d in raw_doc_ids:
            d_clean = d.strip().lower()
            if d_clean in doc_groups():
                resolved.update(doc_groups()[d_clean])
            elif d_clean in doc_aliases():
                resolved.add(doc_aliases()[d_clean])
            else:
                resolved.add(d)
        return resolved

    def embed_query(self, query: str) -> np.ndarray:
        """Sinh vector đã chuẩn hóa L2 cho câu hỏi (dot product = cosine similarity)"""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=query[:1500],
            encoding_format="float"
        )
        vector = np.array(response.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector

    # ------------------------------------------------------------------
    # Tìm kiếm
    # ------------------------------------------------------------------

    def search_chunks(self, query: str, doc_ids: Optional[Iterable[str]] = None,
                      chunk_types: Optional[Iterable[str]] = None,
                      top_k: int = 8, floor: float = 0.0) -> List[Dict[str, Any]]:
        """
        Trả về các chunk con khớp nhất, kèm điểm tương đồng cosine (thang 0-1).
        Hỗ trợ lọc theo doc_ids và chunk_types.
        """
        if not self.available or not query:
            return []

        query_vector = self.embed_query(query)
        scores = self.vectors @ query_vector

        allowed_docs = self._resolve_doc_ids(doc_ids)
        allowed_types = set(chunk_types) if chunk_types else None

        if allowed_docs is not None or allowed_types is not None:
            mask = np.ones(len(self.chunks), dtype=bool)
            if allowed_docs is not None:
                mask &= np.array([c["doc_id"] in allowed_docs for c in self.chunks])
            if allowed_types is not None:
                mask &= np.array([c.get("type") in allowed_types for c in self.chunks])
            scores = np.where(mask, scores, -1.0)

        order = np.argsort(scores)[::-1][:top_k]
        return [
            {**self.chunks[i], "score": float(scores[i])}
            for i in order if scores[i] >= floor
        ]

    def retrieve_articles(self, query: str, doc_ids: Optional[Iterable[str]] = None,
                          chunk_types: Optional[Iterable[str]] = None,
                          top_k: int = 3, floor: float = 0.0) -> List[Dict[str, Any]]:
        """
        Truy xuất phân cấp: khớp ở mức Khoản/hành vi rồi gộp về Điều/Biển báo cha kèm toàn văn.
        Đảm bảo trả về hình ảnh minh họa (image_path) nếu mục cha có ảnh.
        """
        children = self.search_chunks(query, doc_ids=doc_ids, chunk_types=chunk_types, top_k=CHILD_POOL_SIZE)
        if not children:
            return []

        article_scores: Dict[str, float] = {}
        matched_children: Dict[str, List[Dict[str, Any]]] = {}
        for child in children:
            parent_id = child["parent_id"]
            if parent_id not in article_scores:
                article_scores[parent_id] = child["score"]
                matched_children[parent_id] = [child]
            else:
                article_scores[parent_id] = max(article_scores[parent_id], child["score"]) \
                    + child["score"] * MULTI_MATCH_BONUS
                matched_children[parent_id].append(child)

        ranked = sorted(article_scores, key=lambda pid: article_scores[pid], reverse=True)[:top_k]

        results = []
        for parent_id in ranked:
            score = article_scores[parent_id]
            if score < floor:
                continue
            parent = self.parents.get(parent_id, {})
            # Trích xuất ảnh nếu có từ parent hoặc child
            has_illus = parent.get("has_illustration", False) or any(c.get("has_illustration") for c in matched_children[parent_id])
            img_path = parent.get("image_path") or next((c.get("image_path") for c in matched_children[parent_id] if c.get("image_path")), None)

            results.append({
                "parent_id": parent_id,
                "doc_id": parent.get("doc_id", ""),
                "doc_name": parent.get("doc_name", ""),
                "doc_type": parent.get("doc_type", ""),
                "article_number": parent.get("article_number"),
                "article_header": parent.get("article_header", ""),
                "chapter_title": parent.get("chapter_title", ""),
                "citation": parent.get("citation", parent.get("article_header", "")),
                "page_content": parent.get("content", ""),
                "has_illustration": has_illus,
                "image_path": img_path,
                "score": round(score * 100, 1),
                "key_clauses": [c.get("text", "") for c in matched_children[parent_id][:3]]
            })
        return results
