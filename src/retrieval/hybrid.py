"""
Tầng truy xuất lai ghép (Hybrid Retrieval) kết hợp Dense Vector và BM25 Sparse.

Hợp nhất bằng Reciprocal Rank Fusion CHUẨN (không trọng số) ở mức chunk con, sau đó gộp về
Điều/Biển báo cha (small-to-big). Việc chọn giữ lại bao nhiêu kết quả do `fusion.select_by_separation`
quyết định theo phân bố điểm của chính lượt truy vấn, chứ không so với ngưỡng cố định.

Bản trước dùng `RRF_K=30`, `RRF_WEIGHT_DENSE=0.6`, `RRF_WEIGHT_SPARSE=0.4` và `SEMANTIC_FLOOR=0.58`
— tất cả quét siêu tham số trên đúng corpus này với đúng embedding model này. Xem docstring của
`src/retrieval/fusion.py` để biết vì sao chúng bị gỡ bỏ.

Bảo toàn hợp đồng dữ liệu trả về cho law_search_tools và các node của LangGraph.
"""

import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.retrieval.dense import CachedSemanticIndex, get_cached_semantic_index
from src.retrieval.fusion import (
    EMPTY_CONFIDENCE,
    RRF_K,
    RetrievalConfidence,
    max_possible_rrf,
    reciprocal_rank_fusion,
    select_by_separation,
)
from src.retrieval.scope import (
    BRANCH_DENSE,
    BRANCH_SPARSE,
    UNCALIBRATED,
    ScopeSignal,
    get_scope_reference,
)
from src.retrieval.sparse import SparseIndex
from src.semantic_index import DOC_ALIASES, DOC_GROUPS

logger = logging.getLogger(__name__)

# Số ứng viên chunk con lấy từ MỖI nhánh trước khi hợp nhất. Không phải tham số hiệu chuẩn chất
# lượng mà là ngân sách tính toán: lấy rộng để RRF có đủ dữ liệu, rồi để bước chọn cắt xuống.
DEFAULT_CHILD_POOL_SIZE = 24


class HybridSearch:
    """
    Bộ tìm kiếm lai ghép kết hợp Dense (Cosine similarity) và Sparse (BM25Okapi)
    thông qua Reciprocal Rank Fusion chuẩn, không trọng số.
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        dense_index: Optional[CachedSemanticIndex] = None,
        sparse_index: Optional[SparseIndex] = None,
        k: int = RRF_K,
    ):
        if not base_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.base_dir = base_dir
        self.dense_index = dense_index or get_cached_semantic_index(base_dir)
        self.sparse_index = sparse_index or SparseIndex(base_dir)
        self.parents = self.dense_index.parents
        self.k = k
        self.scope_reference = get_scope_reference(base_dir)

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
        k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm song song Dense & Sparse, hợp nhất bằng RRF chuẩn ở mức chunk con:

            score(d) = 1/(k + rank_dense(d)) + 1/(k + rank_sparse(d))

        KHÔNG còn ngưỡng cosine tuyệt đối chặn ở đây. Trước đây `semantic_floor=0.58` khiến hàm
        trả về rỗng mà Agent không hề biết vì sao — nó chỉ thấy "không tìm thấy gì". Giờ kết quả
        luôn được trả kèm `RetrievalConfidence` để Agent đọc và tự quyết định: tra lại bằng từ
        khác, mở rộng phạm vi, hay nói thẳng là kho tài liệu không bao phủ câu hỏi.
        """
        if not query or not self.available:
            return []

        rrf_k = self.k if k is None else k

        dense_hits = self.dense_index.search_chunks(
            query, doc_ids=doc_ids, chunk_types=chunk_types, top_k=child_pool_size
        )
        sparse_hits = self.sparse_index.search_chunks(
            query, doc_ids=doc_ids, chunk_types=chunk_types, top_k=child_pool_size
        )

        chunk_map: Dict[str, Dict[str, Any]] = {}
        dense_ranks: Dict[str, int] = {}
        sparse_ranks: Dict[str, int] = {}

        for rank, chunk in enumerate(dense_hits, start=1):
            cid = chunk["chunk_id"]
            c_copy = dict(chunk)
            c_copy["dense_cosine"] = float(chunk.get("score", 0.0))
            c_copy.setdefault("sparse_score", 0.0)
            chunk_map[cid] = c_copy
            dense_ranks[cid] = rank

        for rank, chunk in enumerate(sparse_hits, start=1):
            cid = chunk["chunk_id"]
            if cid not in chunk_map:
                c_copy = dict(chunk)
                c_copy["dense_cosine"] = 0.0
                chunk_map[cid] = c_copy
            # Điểm BM25 thô: RRF chỉ đọc thứ hạng nên sau hợp nhất mọi điểm đều xấp xỉ nhau.
            # Muốn biết kết quả "tốt tới đâu" thì phải giữ lại độ lớn liên quan gốc.
            chunk_map[cid]["sparse_score"] = float(chunk.get("score", 0.0))
            sparse_ranks[cid] = rank

        ranked_lists = {
            "dense": [c["chunk_id"] for c in dense_hits],
            "sparse": [c["chunk_id"] for c in sparse_hits],
        }
        active_lists = sum(1 for ids in ranked_lists.values() if ids)
        rrf_scores = reciprocal_rank_fusion(ranked_lists, k=rrf_k)
        if not rrf_scores:
            return []

        ceiling = max_possible_rrf(active_lists, k=rrf_k)

        fused_chunks = []
        for cid in sorted(rrf_scores, key=lambda c: rrf_scores[c], reverse=True):
            raw_rrf = rrf_scores[cid]
            c_dict = dict(chunk_map[cid])
            c_dict["rrf_score"] = raw_rrf
            c_dict["score"] = float(raw_rrf / ceiling) if ceiling > 0 else float(raw_rrf)
            c_dict["dense_rank"] = dense_ranks.get(cid)
            c_dict["sparse_rank"] = sparse_ranks.get(cid)
            fused_chunks.append(c_dict)

        return fused_chunks

    def retrieve_articles_with_confidence(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        top_k: int = 3,
        child_pool_size: int = DEFAULT_CHILD_POOL_SIZE,
        k: Optional[int] = None,
        adaptive: bool = True,
    ) -> Tuple[List[Dict[str, Any]], RetrievalConfidence, ScopeSignal]:
        """
        Truy xuất phân cấp: hợp nhất RRF các chunk con rồi gộp về Điều/Biển báo cha.

        Một Điều cha mạnh vì hai lý do khác nhau: có một đoạn con khớp RẤT sát, hoặc có NHIỀU
        đoạn con cùng khớp (đồng thuận). Bản trước trộn hai thứ đó bằng `max(điểm con) + điểm
        con * 0.05` — con số 0,05 chọn tay, và nó quyết định hẳn thứ hạng chứ không chỉ phá hoà.

        Ở đây hai lý do được coi là hai BẢNG XẾP HẠNG riêng rồi hợp nhất bằng chính RRF — đúng
        công cụ đã dùng ở tầng chunk con, và cũng không có tham số nào.

        Đã đo cả bốn cách trên benchmark 79 câu (nhánh BM25):

            cách gộp        hit@1    hit@3    hit@5    mrr      ndcg@5
            max + 0.05      0.4430   0.6709   0.7342   0.5616   0.6052
            max + phá hoà   0.4937   0.6329   0.7089   0.5726   0.6065
            cộng dồn        0.3418   0.6582   0.7089   0.5008   0.5538
            RRF hai bảng    0.4937   0.6456   0.7342   0.5827   0.6205   <- chọn

        Cộng dồn thiên vị Điều luật dài nhiều khoản nên đánh sập hit@1. RRF hai bảng tốt nhất ở
        4/5 chỉ số.

        `adaptive=True` (mặc định, dùng cho Agent): số lượng trả về do `select_by_separation`
        quyết định theo phân bố điểm của chính lượt truy vấn, bị chặn trên bởi `top_k` — cắt bớt
        phần đuôi nhiễu để không làm ngập ngữ cảnh của model.

        `adaptive=False`: trả đủ `top_k` ứng viên. Dùng cho đo đạc (Hit@k, MRR, nDCG@k cần một
        danh sách độ dài cố định) và cho nơi gọi muốn tự lọc. Độ tin cậy vẫn được tính như nhau.
        """
        rrf_k = self.k if k is None else k
        fused_children = self.search_fused_chunks(
            query,
            doc_ids=doc_ids,
            chunk_types=chunk_types,
            child_pool_size=child_pool_size,
            k=rrf_k,
        )

        if not fused_children:
            return [], EMPTY_CONFIDENCE, UNCALIBRATED

        article_scores: Dict[str, float] = {}
        matched_children: Dict[str, List[Dict[str, Any]]] = {}

        for child in fused_children:
            parent_id = child["parent_id"]
            score = child["score"]
            if score > article_scores.get(parent_id, 0.0):
                article_scores[parent_id] = score
            matched_children.setdefault(parent_id, []).append(child)

        # Hai bảng xếp hạng độc lập của cùng tập Điều cha, hợp nhất bằng RRF.
        # Mỗi bảng tự phá hoà bằng tiêu chí của bảng kia để thứ tự luôn tất định.
        by_best_score = sorted(
            article_scores,
            key=lambda pid: (article_scores[pid], len(matched_children[pid])),
            reverse=True,
        )
        by_match_count = sorted(
            article_scores,
            key=lambda pid: (len(matched_children[pid]), article_scores[pid]),
            reverse=True,
        )
        parent_rrf = reciprocal_rank_fusion(
            {"best_score": by_best_score, "match_count": by_match_count}, k=rrf_k
        )
        ranked_parents = sorted(
            parent_rrf, key=lambda pid: (parent_rrf[pid], article_scores[pid]), reverse=True
        )

        # Cắt và đo độ tách biệt trên ĐỘ LỚN liên quan (cosine hoặc BM25), không phải trên
        # điểm RRF: RRF chỉ đọc thứ hạng nên điểm của nó gần như cách đều nhau, đo vách rơi ở
        # đó sẽ luôn ra "không có vách rơi" kể cả với truy vấn trúng đích.
        relevance = {
            pid: max(
                (c.get("dense_cosine", 0.0) or c.get("sparse_score", 0.0)) for c in children
            )
            for pid, children in matched_children.items()
        }
        keep, confidence = select_by_separation(
            [relevance[pid] for pid in ranked_parents], max_k=top_k
        )
        scope = self._assess_scope(fused_children)
        if not adaptive:
            keep = min(top_k, len(ranked_parents))

        best_parent_score = parent_rrf[ranked_parents[0]] if ranked_parents else 0.0

        results = []
        for parent_id in ranked_parents[:keep]:
            parent_score = parent_rrf[parent_id]
            children = matched_children[parent_id]

            # `score` là độ liên quan TƯƠNG ĐỐI trong chính lượt truy vấn này (hạng 1 = 100%),
            # không phải một xác suất tuyệt đối. Nói đúng bản chất còn hơn đưa ra một con số
            # tuyệt đối chỉ có nghĩa với đúng một embedding model.
            score_100 = round(100.0 * parent_score / best_parent_score, 1) if best_parent_score > 0 else 0.0

            parent = self.parents.get(parent_id, {})
            has_illus = parent.get("has_illustration", False) or any(
                c.get("has_illustration") for c in children
            )
            img_path = parent.get("image_path") or next(
                (c.get("image_path") for c in children if c.get("image_path")), None
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
                "dense_cosine": max((c.get("dense_cosine", 0.0) for c in children), default=0.0),
                "matched_children": len(children),
                "key_clauses": [c.get("text", "") for c in children[:3]],
            })

        return results, confidence, scope

    def _assess_scope(self, children: List[Dict[str, Any]]) -> ScopeSignal:
        """
        Câu hỏi có nằm trong vùng kho tài liệu bao phủ không.

        Đánh giá ĐỘC LẬP trên từng nhánh rồi lấy kết luận rộng rãi hơn: một câu hỏi có thể dùng
        từ ngữ lạ (BM25 thấp) nhưng đúng chủ đề (cosine cao), hoặc ngược lại. Chỉ khi CẢ HAI
        nhánh đều thấy dưới mốc thì mới coi là ngoài phạm vi.
        """
        best = {
            BRANCH_DENSE: max((c.get("dense_cosine", 0.0) for c in children), default=0.0),
            BRANCH_SPARSE: max((c.get("sparse_score", 0.0) for c in children), default=0.0),
        }

        signals = [
            self.scope_reference.assess(score, branch)
            for branch, score in best.items()
            if score > 0.0 and self.scope_reference.available_for(branch)
        ]
        if not signals:
            return UNCALIBRATED

        # Nhánh "lạc quan" nhất quyết định: ratio cao nhất.
        return max(signals, key=lambda s: s.ratio)

    def retrieve_articles(
        self,
        query: str,
        doc_ids: Optional[Iterable[str]] = None,
        chunk_types: Optional[Iterable[str]] = None,
        top_k: int = 3,
        child_pool_size: int = DEFAULT_CHILD_POOL_SIZE,
        k: Optional[int] = None,
        adaptive: bool = True,
        **_legacy: Any,
    ) -> List[Dict[str, Any]]:
        """
        Bản chỉ trả danh sách, cho các nơi gọi không cần tín hiệu độ tin cậy.

        `**_legacy` nuốt các tham số hiệu chuẩn cũ (`floor`, `semantic_floor`, `w_dense`,
        `w_sparse`) để script bên ngoài truyền vào không bị vỡ; chúng không còn tác dụng gì.
        """
        results, _, _ = self.retrieve_articles_with_confidence(
            query,
            doc_ids=doc_ids,
            chunk_types=chunk_types,
            top_k=top_k,
            child_pool_size=child_pool_size,
            k=k,
            adaptive=adaptive,
        )
        return results


class HybridRetriever(BaseRetriever):
    """LangChain BaseRetriever adapter cho tầng truy xuất lai ghép HybridSearch."""

    search_engine: Any
    top_k: int = 5
    doc_ids: Optional[List[str]] = None
    chunk_types: Optional[List[str]] = None

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[CallbackManagerForRetrieverRun] = None
    ) -> List[Document]:
        articles = self.search_engine.retrieve_articles(
            query,
            doc_ids=self.doc_ids,
            chunk_types=self.chunk_types,
            top_k=self.top_k,
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
        **_legacy: Any,
    ) -> List[Dict[str, Any]]:
        return self.search_engine.retrieve_articles(
            query,
            doc_ids=doc_ids or self.doc_ids,
            chunk_types=chunk_types or self.chunk_types,
            top_k=top_k or self.top_k,
        )


_shared_hybrid_search: Optional[HybridSearch] = None


def get_hybrid_search(
    base_dir: Optional[str] = None,
    dense_index: Optional[CachedSemanticIndex] = None,
    sparse_index: Optional[SparseIndex] = None,
    k: int = RRF_K,
) -> HybridSearch:
    """Lấy thể hiện HybridSearch dùng chung (singleton)."""
    global _shared_hybrid_search
    if _shared_hybrid_search is None:
        _shared_hybrid_search = HybridSearch(
            base_dir=base_dir,
            dense_index=dense_index,
            sparse_index=sparse_index,
            k=k,
        )
    return _shared_hybrid_search


def get_hybrid_retriever(
    base_dir: Optional[str] = None,
    top_k: int = 5,
    doc_ids: Optional[List[str]] = None,
    chunk_types: Optional[List[str]] = None,
) -> HybridRetriever:
    """Tạo đối tượng HybridRetriever chuẩn LangChain."""
    return HybridRetriever(
        search_engine=get_hybrid_search(base_dir=base_dir),
        top_k=top_k,
        doc_ids=doc_ids,
        chunk_types=chunk_types,
    )
