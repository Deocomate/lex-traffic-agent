"""
Node Xếp hạng lại (Rerank Node) cho StateGraph LangGraph.
Tiếp nhận evidence fan-in từ 4 node truy xuất song song.
Nếu danh sách tài liệu luật (source == "law") có > 3 ứng viên và đủ điều kiện,
gọi LLMReranker từ tầng Phase 3 để tối ưu hóa thứ tự trước khi đưa vào compact.
"""

from typing import Any, Dict, List
from src.graph.state import Evidence, LegalAgentState
from src.retrieval.rerank import get_reranker


def rerank_node(state: LegalAgentState) -> Dict[str, Any]:
    """Node rerank: Xếp hạng lại các bằng chứng pháp luật nếu cần thiết."""
    raw_evidences = state.get("evidence", [])
    if not raw_evidences:
        return {"reranked_evidence": []}

    law_items: List[Evidence] = []
    other_items: List[Evidence] = []

    for ev in raw_evidences:
        if ev.get("source") == "law":
            law_items.append(ev)
        else:
            other_items.append(ev)

    # Nếu số lượng Điều luật <= 3, giữ nguyên thứ tự RRF vốn đã được tối ưu
    if len(law_items) <= 3:
        return {"reranked_evidence": other_items + law_items}

    reranker = get_reranker()
    candidate_dicts = [
        {
            "parent_id": item.get("parent_id", ""),
            "citation": item.get("citation", ""),
            "article_header": item.get("header", ""),
            "page_content": item.get("content", ""),
            "score": item.get("score", 0.0),
        }
        for item in law_items
    ]

    try:
        skip_res = reranker.should_skip(candidate_dicts)
        skip = skip_res[0] if isinstance(skip_res, (list, tuple)) else bool(skip_res)
    except Exception:
        skip = True

    if skip:
        return {"reranked_evidence": other_items + law_items}

    route = state.get("route")
    query = (
        route.search_query.strip()
        if route and route.search_query.strip()
        else state.get("grounding_query") or state.get("question", "")
    )

    try:
        reranked_dicts = reranker.rerank(query, candidate_dicts, top_k=len(candidate_dicts))
        pid_order = [d["parent_id"] for d in reranked_dicts if "parent_id" in d]
        law_map = {item.get("parent_id", ""): item for item in law_items}
        reordered_law: List[Evidence] = []
        for pid in pid_order:
            if pid in law_map:
                reordered_law.append(law_map[pid])
        for item in law_items:
            if item not in reordered_law:
                reordered_law.append(item)

        return {"reranked_evidence": other_items + reordered_law}
    except Exception:
        return {"reranked_evidence": other_items + law_items}
