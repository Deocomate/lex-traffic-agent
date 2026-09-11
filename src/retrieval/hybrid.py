"""
Tầng truy xuất lai ghép (Hybrid Retrieval) kết hợp Dense Vector và BM25 Sparse.
Sử dụng Reciprocal Rank Fusion (RRF) có trọng số ở mức chunk con, sau đó gộp
về Điều/Biển báo cha (small-to-big) theo cấu trúc chuẩn của LexTraffic AI.
Bảo toàn hợp đồng dữ liệu trả về cho law_search_tools và các node của LangGraph.
"""

import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.retrieval.dense import CachedSemanticIndex, get_cached_semantic_index
from src.retrieval.sparse import SparseIndex
from src.semantic_index import DOC_ALIASES, DOC_GROUPS

logger = logging.getLogger(__name__)

# Tham số mặc định của RRF (được hiệu chuẩn bằng thực nghiệm quét siêu tham số trên 79 câu benchmark)
DEFAULT_RRF_K = int(os.getenv("RRF_K", "30"))
DEFAULT_WEIGHT_DENSE = float(os.getenv("RRF_WEIGHT_DENSE", "0.6"))
DEFAULT_WEIGHT_SPARSE = float(os.getenv("RRF_WEIGHT_SPARSE", "0.4"))

DEFAULT_CHILD_POOL_SIZE = 24
MULTI_MATCH_BONUS = 0.05

# Hiệu chuẩn ngưỡng sàn trên benchmark 95 câu và các câu hỏi thực tế:
# - Dải điểm câu lạc đề thuần túy (thời tiết, ẩm thực, giải trí...): Cosine 0.48 - 0.55
# - Dải điểm câu hỏi thực tế ngắn/đặc thù (GPLX C1, biển số, tuổi...): Cosine 0.63 - 0.69
# - Dải điểm câu đúng đề chuẩn: Cosine 0.710 - 0.948
# Chọn SEMANTIC_FLOOR = 0.58 (RELEVANCE_FLOOR = 60.0%) loại bỏ 100% câu hỏi ngoài ngành,
# bảo toàn 100% câu hỏi luật giao thông (kể cả câu ngắn như GPLX C1 đạt 68.6%).
DEFAULT_SEMANTIC_FLOOR = float(os.getenv("SEMANTIC_FLOOR", "0.58"))



class HybridSearch:
    """
    Bộ tìm kiếm lai ghép kết hợp Dense (Cosine similarity) và Sparse (BM25Okapi)
    thông qua thuật toán Weighted Reciprocal Rank Fusion.
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        dense_index: Optional[CachedSemanticIndex] = None,
        sparse_index: Optional[SparseIndex] = None,
        k: int = DEFAULT_RRF_K,
        w_dense: float = DEFAULT_WEIGHT_DENSE,
        w_sparse: float = DEFAULT_WEIGHT_SPARSE,
    ):
        if not base_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.base_dir = base_dir
        self.dense_index = dense_index or get_cached_semantic_index(base_dir)
        self.sparse_index = sparse_index or SparseIndex(base_dir)
        self.parents = self.dense_index.parents

        self.k = k
        self.w_dense = w_dense
        self.w_sparse = w_sparse

    @property
    def available(self) -> bool:
        return self.dense_index.available and self.sparse_index.available

    @property
    def chunks(self) -> List[Dict[str, Any]]:
        """Tập hợp các chunk con từ chỉ mục dense để tương thích ngược."""
        return getattr(self.dense_index, "chunks", [])

    def _resolve_doc_ids(self, raw_doc_ids: Optional[Iterable[str]]) -> Optional[Set[str]]:
        """Phân giải tên văn bản hoặc nhóm sang mã văn bản chuẩn."""
        if not raw_doc_ids:
            return None
        resolved: Set[str] = set()
        for d in raw_doc_ids:
            d_clean = d.strip().lower()
            if d_clean in DOC_GROUPS:
                resolved.update(DOC_GROUPS[d_clean])
            elif d_clean in DOC_ALIASES:
                resolved.add(DOC_ALIASES[d_clean])
            else:
                resolved.add(d)
        return resolved

    def search_fused_chunks(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        child_pool_size: int = DEFAULT_CHILD_POOL_SIZE,
        w_dense: Optional[float] = None,
        w_sparse: Optional[float] = None,
        k: Optional[int] = None,
        semantic_floor: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Thực hiện tìm kiếm song song Dense & Sparse, sau đó hợp nhất bằng RRF ở mức chunk con.

        Công thức RRF có trọng số:
            score(d) = w_dense / (k + rank_dense(d)) + w_sparse / (k + rank_sparse(d))
        """
        if not query or not self.available:
            return []

        w_d = self.w_dense if w_dense is None else w_dense
        w_s = self.w_sparse if w_sparse is None else w_sparse
        rrf_k = self.k if k is None else k
        s_floor = DEFAULT_SEMANTIC_FLOOR if semantic_floor is None else semantic_floor

        # 1. Truy xuất danh sách ứng viên chunk con từ hai tầng
        dense_hits = self.dense_index.search_chunks(
            query, doc_ids=doc_ids, chunk_types=chunk_types, top_k=child_pool_size
        )
        sparse_hits = self.sparse_index.search_chunks(
            query, doc_ids=doc_ids, chunk_types=chunk_types, top_k=child_pool_size
        )

        # Nếu độ tương đồng ngữ nghĩa cao nhất < semantic_floor:
        # Câu hỏi hoàn toàn nằm ngoài phạm vi pháp luật giao thông.
        # Loại bỏ các kết quả từ khóa trùng chữ ngẫu nhiên (tương tự cơ chế của penalty_lookup).
        if s_floor > 0.0:
            best_cosine = dense_hits[0]["score"] if dense_hits else 0.0
            if best_cosine < s_floor:
                logger.debug(
                    "Truy vấn '%s' có cosine cao nhất (%.3f) < semantic_floor (%.2f), bỏ qua kết quả.",
                    query,
                    best_cosine,
                    s_floor,
                )
                return []

        # 2. Hợp nhất RRF theo thứ hạng
        chunk_map: Dict[str, Dict[str, Any]] = {}
        rrf_scores: Dict[str, float] = {}
        dense_ranks: Dict[str, int] = {}
        sparse_ranks: Dict[str, int] = {}

        for rank, chunk in enumerate(dense_hits, start=1):
            cid = chunk["chunk_id"]
            c_copy = dict(chunk)
            c_copy["dense_cosine"] = float(chunk.get("score", 0.0))
            chunk_map[cid] = c_copy
            dense_ranks[cid] = rank
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (w_d / (rrf_k + rank))

        for rank, chunk in enumerate(sparse_hits, start=1):
            cid = chunk["chunk_id"]
            if cid not in chunk_map:
                c_copy = dict(chunk)
                c_copy["dense_cosine"] = 0.0
                chunk_map[cid] = c_copy
            sparse_ranks[cid] = rank
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (w_s / (rrf_k + rank))

        # Điểm cực đại lý thuyết khi đứng rank 1 ở cả hai nhánh
        max_possible_rrf = (w_d + w_s) / (rrf_k + 1)

        # Sắp xếp các chunk con theo RRF giảm dần
        sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
        fused_chunks = []
        for cid in sorted_cids:
            raw_rrf = rrf_scores[cid]
            norm_score = raw_rrf / max_possible_rrf if max_possible_rrf > 0 else raw_rrf
            c_dict = dict(chunk_map[cid])
            c_dict["rrf_score"] = raw_rrf
            c_dict["score"] = float(norm_score)
            c_dict["dense_rank"] = dense_ranks.get(cid)
            c_dict["sparse_rank"] = sparse_ranks.get(cid)
            fused_chunks.append(c_dict)

        return fused_chunks

    def retrieve_articles(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        top_k: int = 3,
        floor: float = 0.0,
        child_pool_size: int = DEFAULT_CHILD_POOL_SIZE,
        w_dense: Optional[float] = None,
        w_sparse: Optional[float] = None,
        k: Optional[int] = None,
        semantic_floor: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Truy xuất phân cấp: Hợp nhất RRF các chunk con rồi gộp về Điều/Biển báo cha.
        Giữ nguyên hoàn toàn logic parent aggregation (max điểm con + MULTI_MATCH_BONUS)
        và hình dạng dữ liệu trả về của SemanticIndex.
        """
        fused_children = self.search_fused_chunks(
            query,
            doc_ids=doc_ids,
            chunk_types=chunk_types,
            child_pool_size=child_pool_size,
            w_dense=w_dense,
            w_sparse=w_sparse,
            k=k,
            semantic_floor=semantic_floor,
        )

        if not fused_children:
            return []

        article_scores: Dict[str, float] = {}
        matched_children: Dict[str, List[Dict[str, Any]]] = {}

        for child in fused_children:
            parent_id = child["parent_id"]
            # Sử dụng điểm chuẩn hóa của chunk con
            c_score = child["score"]
            if parent_id not in article_scores:
                article_scores[parent_id] = c_score
                matched_children[parent_id] = [child]
            else:
                article_scores[parent_id] = (
                    max(article_scores[parent_id], c_score) + c_score * MULTI_MATCH_BONUS
                )
                matched_children[parent_id].append(child)

        # Sắp xếp các parent chunk theo điểm giảm dần
        ranked_parents = sorted(
            article_scores.keys(), key=lambda pid: article_scores[pid], reverse=True
        )[:top_k]

        results = []
        for parent_id in ranked_parents:
            parent_score = article_scores[parent_id]
            # Điểm phần trăm: ưu tiên cosine của chunk khớp cao nhất để giữ tính chuẩn hóa ngữ nghĩa
            best_cos = max(
                (c.get("dense_cosine", 0.0) for c in matched_children[parent_id]),
                default=0.0,
            )
            if best_cos > 0.0:
                score_100 = round(best_cos * 100, 1)
            else:
                # Nếu khớp qua BM25 thuần túy, chuẩn hóa theo trọng số sparse để không bị kẹt ở trần 40%
                w_s_val = self.w_sparse if w_sparse is None else w_sparse
                normalized_sparse_ratio = min(parent_score / w_s_val, 1.0) if w_s_val > 0 else parent_score
                score_100 = round(normalized_sparse_ratio * 100, 1)

            if score_100 < floor:
                continue

            parent = self.parents.get(parent_id, {})
            has_illus = parent.get("has_illustration", False) or any(
                c.get("has_illustration") for c in matched_children[parent_id]
            )
            img_path = parent.get("image_path") or next(
                (c.get("image_path") for c in matched_children[parent_id] if c.get("image_path")),
                None,
            )

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
                "score": score_100,
                "raw_rrf_score": parent_score,
                "key_clauses": [c.get("text", "") for c in matched_children[parent_id][:3]],
            })

        return results


class HybridRetriever(BaseRetriever):
    """LangChain BaseRetriever adapter cho tầng truy xuất lai ghép HybridSearch."""

    search_engine: Any
    top_k: int = 5
    doc_ids: Optional[List[str]] = None
    chunk_types: Optional[List[str]] = None
    floor: float = 0.0

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[CallbackManagerForRetrieverRun] = None
    ) -> List[Document]:
        articles = self.search_engine.retrieve_articles(
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
        return self.search_engine.retrieve_articles(
            query,
            doc_ids=doc_ids or self.doc_ids,
            chunk_types=chunk_types or self.chunk_types,
            top_k=top_k or self.top_k,
            floor=self.floor if floor is None else floor,
        )


_shared_hybrid_search: Optional[HybridSearch] = None


def get_hybrid_search(
    base_dir: Optional[str] = None,
    dense_index: Optional[CachedSemanticIndex] = None,
    sparse_index: Optional[SparseIndex] = None,
    k: int = DEFAULT_RRF_K,
    w_dense: float = DEFAULT_WEIGHT_DENSE,
    w_sparse: float = DEFAULT_WEIGHT_SPARSE,
) -> HybridSearch:
    """Lấy thể hiện HybridSearch dùng chung (singleton)."""
    global _shared_hybrid_search
    if _shared_hybrid_search is None:
        _shared_hybrid_search = HybridSearch(
            base_dir=base_dir,
            dense_index=dense_index,
            sparse_index=sparse_index,
            k=k,
            w_dense=w_dense,
            w_sparse=w_sparse,
        )
    return _shared_hybrid_search


def get_hybrid_retriever(
    base_dir: Optional[str] = None,
    top_k: int = 5,
    doc_ids: Optional[List[str]] = None,
    chunk_types: Optional[List[str]] = None,
    floor: float = 0.0,
) -> HybridRetriever:
    """Tạo đối tượng HybridRetriever chuẩn LangChain."""
    engine = get_hybrid_search(base_dir=base_dir)
    return HybridRetriever(
        search_engine=engine,
        top_k=top_k,
        doc_ids=doc_ids,
        chunk_types=chunk_types,
        floor=floor,
    )
