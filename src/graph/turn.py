"""
Một lượt hỏi-đáp của Agent: tra cache ngữ nghĩa, chạy đồ thị khi trượt, ghi cache khi câu trả
lời đã qua kiểm chứng (Phase 6).

Vì sao tra cache ở ĐÂY chứ không phải trong đồ thị: khoá cache cần `intents`/`vehicles`/
`doc_scope` từ node `route`, nhưng lợi ích lớn nhất của cache là bỏ qua được cả truy xuất lẫn
sinh văn bản. Nên lượt chạy định tuyến trước, ngoài đồ thị — chỉ tốn đúng một lệnh gọi router
rẻ — rồi mới quyết định có chạy đồ thị hay không. Khi trượt cache, quyết định định tuyến được
dùng lại làm khoá cache, không tốn thêm một lệnh gọi LLM nào.

Cả hai façade `stream_agent()` và `astream_agent()` của `src/agent.py` dùng chung đúng hàm này.
"""

import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.cache.fingerprint import get_index_fingerprint
from src.cache.semantic_cache import (
    CacheSignals,
    build_cache_key,
    get_semantic_cache,
    is_cacheable,
)
from src.graph.build import build_run_config, get_legal_graph
from src.graph.events import emit
from src.graph.query_signals import detect_by_regex
from src.graph.state import LegalAgentState

CACHE_HIT_NOTICE = "♻️ Dùng lại kết quả đã kiểm chứng cho câu hỏi tương tự"


def new_thread_id() -> str:
    """Sinh định danh cuộc hội thoại mới cho checkpointer."""
    return uuid.uuid4().hex


def format_history_messages(history: Optional[List[Dict[str, str]]]) -> List[BaseMessage]:
    """Chuyển danh sách lịch sử hội thoại dạng dict sang danh sách BaseMessage."""
    messages: List[BaseMessage] = []
    for m in history or []:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not content:
            continue
        if role in ("user", "human"):
            messages.append(HumanMessage(content=content))
        elif role in ("assistant", "ai"):
            messages.append(AIMessage(content=content))
    return messages


def _checkpointed_messages(graph, config: Dict[str, Any]) -> List[BaseMessage]:
    """Đọc lịch sử đã lưu của thread. Trả về danh sách rỗng khi thread chưa có gì."""
    if "configurable" not in config:
        return []
    try:
        snapshot = graph.get_state(config)
        return list((snapshot.values or {}).get("messages", []) or [])
    except Exception:
        return []


def _embed_query(text: str):
    """
    Vector truy vấn dùng làm trục so sánh trong cache.

    Dùng lại đúng bộ nhúng có cache đĩa của tầng truy xuất, nên trên đường trúng cache lệnh gọi
    này gần như miễn phí sau lần đầu tiên.
    """
    try:
        from src.retrieval.dense import get_cached_semantic_index

        index = get_cached_semantic_index()
        if not index.available:
            return None
        return index.embed_query(text)
    except Exception:
        return None


def _deterministic_cache_route(grounding_query: str) -> CacheSignals:
    """
    Quyết định định tuyến TẤT ĐỊNH, chỉ dùng để dựng khoá cache.

    Không được dùng quyết định của LLM làm khoá: bộ định tuyến LLM cũ không tất định. Đo trực tiếp trên cùng một câu hỏi cho ba lượt
    chạy: hai lượt trả `vehicles=['o_to','xe_may']`, lượt còn lại trả `vehicles=[]` — ba lượt
    ra hai khoá khác nhau, nên cache không bao giờ trúng dù câu hỏi y hệt.

    Regex prior thì tất định, và quan trọng hơn: nó vẫn tách bạch đúng thứ cần tách. "Ô tô
    vượt đèn đỏ" cho `['o_to']`, "xe máy vượt đèn đỏ" cho `['xe_may']`, nên cái bẫy nguy hiểm
    nhất — trả mức phạt của loại xe này cho loại xe kia — vẫn bị chặn ở tầng khoá. Tương tự,
    "Luật 36" cho `['law']` còn "Nghị định 168" cho `['law','penalty']`, nên danh tính văn bản
    cũng đã nằm trong khoá; `doc_scope` (chỉ do LLM sinh ra, và dao động) bị giữ cố định.

    Đánh đổi đã biết: hai câu hỏi rất giống nhau mà LLM router thêm intent khác nhau sẽ dùng
    chung một mục cache. Câu trả lời được dùng lại vẫn là câu ĐÃ QUA KIỂM CHỨNG cho một câu
    hỏi có cosine >= 0.97, nên rủi ro là thiếu một khía cạnh phụ, không phải sai số liệu.
    """
    intents, vehicles = detect_by_regex(grounding_query)
    return CacheSignals(intents=intents, vehicles=vehicles, doc_scope="all")


def _emit_cached_answer(answer: str, sources: List[Dict[str, Any]], thread_id: str) -> None:
    """
    Phát chuỗi sự kiện rút gọn khi trúng cache: giao diện không cần biết đây là cache, nhưng
    trace nói rõ để người dùng tin được kết quả.
    """
    emit("tool_result", CACHE_HIT_NOTICE, tool="semantic_cache", cached=True)
    emit("token", answer, phase="answer")
    emit("answer_commit", "", answer=answer)

    # Câu lấy từ cache CŨNG là câu đã qua kiểm chứng, nên vẫn phát `verified`.
    #
    # `_store_cache()` chỉ ghi khi `is_cacheable(answer, issues, needs_search, sources)` đúng —
    # tức là không còn `issues`, không cần tra cứu ngoài, và có nguồn. Không có đường nào đưa
    # một câu chưa kiểm chứng vào cache. Bỏ qua sự kiện này ở đây sẽ tạo ra một khác biệt mà
    # người dùng không giải thích nổi: cùng một câu hỏi, lần đầu thấy dấu đã-kiểm-chứng, lần
    # sau (trúng cache) thì không — trong khi nội dung trả về giống hệt từng ký tự.
    emit("verified", "✅ Đã đối chiếu số liệu và trích dẫn với văn bản gốc")
    emit(
        "done",
        "✅ Hoàn tất tra cứu và giải đáp!",
        answer=answer,
        agent_steps=[],
        sources=sources,
        verification_issues=[],
        needs_search=False,
        search=None,
        model_used="semantic_cache",
        thread_id=thread_id,
        cached=True,
    )


def run_turn(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
    thread_id: str = "",
) -> Dict[str, Any]:
    """
    Chạy trọn một lượt hỏi-đáp theo kiến trúc Agentic và phát sự kiện SSE. Trả về kết quả của lượt.
    """
    thread_id = thread_id or new_thread_id()
    graph = get_legal_graph()
    config = build_run_config(thread_id)

    # Checkpointer là nguồn lịch sử duy nhất khi thread đã có dữ liệu.
    known_messages = _checkpointed_messages(graph, config)
    seed_messages = known_messages or format_history_messages(history)

    cache_route = _deterministic_cache_route(user_query)

    cached = _lookup_cache(user_query, cache_route)
    if cached is not None:
        _emit_cached_answer(cached["answer"], cached["sources"], thread_id)
        _record_cached_turn(graph, config, user_query, cached["answer"])
        return {
            "thread_id": thread_id,
            "answer": cached["answer"],
            "sources": cached["sources"],
            "tool_outputs": cached.get("tool_outputs", []),
            "agent_steps": [],
            "issues": [],
            "needs_search": False,
            "search": None,
            "model_used": "semantic_cache",
            "cached": True,
        }

    # Chuẩn bị luồng tin nhắn: lịch sử hội thoại trước đó + câu hỏi hiện tại của người dùng
    all_messages: List[BaseMessage] = list(seed_messages)
    all_messages.append(HumanMessage(content=user_query))

    initial_state: LegalAgentState = {
        "question": user_query,
        "grounding_query": user_query,
        "thread_id": thread_id,
        "turn_count": 0,
        "evidence": [],
        "agent_steps": [],
        "repair_count": 0,
        "messages": all_messages,
    }

    final_state = graph.invoke(initial_state, config=config)
    tool_outputs = _collect_tool_outputs(final_state)
    _store_cache(user_query, cache_route, final_state, tool_outputs)
    return {
        "thread_id": thread_id,
        "answer": final_state.get("answer", ""),
        "sources": final_state.get("sources", []) or [],
        "tool_outputs": tool_outputs,
        "agent_steps": final_state.get("agent_steps", []) or [],
        "issues": final_state.get("issues", []) or [],
        "needs_search": bool(final_state.get("needs_search")),
        "search": final_state.get("search"),
        "model_used": final_state.get("model_used", ""),
        "cached": False,
    }


def _collect_tool_outputs(final_state: Dict[str, Any]) -> List[str]:
    """Bằng chứng nguyên văn của lượt — cũng chính là thứ node `verify` đã đối chiếu."""
    return [
        ev.get("raw_tool_output", "")
        for ev in (final_state.get("evidence") or [])
        if ev.get("raw_tool_output")
    ]


# ---------------------------------------------------------------------------
# Cache ngữ nghĩa
# ---------------------------------------------------------------------------

def _lookup_cache(
    grounding_query: str,
    decision: Optional[CacheSignals],
) -> Optional[Dict[str, Any]]:
    """Tra cache theo khoá tổ hợp. Mọi sự cố đều quy về 'trượt cache' để đồ thị chạy bình thường."""
    if decision is None:
        return None
    vector = _embed_query(grounding_query)
    if vector is None:
        return None
    try:
        fingerprint = get_index_fingerprint()
        return get_semantic_cache().get(
            key=build_cache_key(decision, fingerprint),
            query_vector=vector,
            index_fingerprint=fingerprint,
        )
    except Exception:
        return None


def _store_cache(
    grounding_query: str,
    decision: Optional[CacheSignals],
    final_state: Dict[str, Any],
    tool_outputs: Optional[List[str]] = None,
) -> bool:
    """Ghi cache chỉ khi câu trả lời đã vượt kiểm chứng, không cần tìm kiếm ngoài, và có nguồn."""
    if decision is None or not isinstance(final_state, dict):
        return False

    answer = final_state.get("answer", "")
    issues = final_state.get("issues") or []
    needs_search = bool(final_state.get("needs_search"))
    sources = final_state.get("sources") or []

    if not is_cacheable(answer, issues, needs_search, sources):
        return False

    vector = _embed_query(grounding_query)
    if vector is None:
        return False

    try:
        fingerprint = get_index_fingerprint()
        return get_semantic_cache().put(
            key=build_cache_key(decision, fingerprint),
            query=grounding_query,
            query_vector=vector,
            answer=answer,
            sources=sources,
            index_fingerprint=fingerprint,
            tool_outputs=tool_outputs if tool_outputs is not None else _collect_tool_outputs(final_state),
        )
    except Exception:
        return False


def _record_cached_turn(graph, config: Dict[str, Any], question: str, answer: str) -> None:
    """
    Ghi lượt trúng cache vào lịch sử thread.

    Bỏ qua bước này thì câu nối tiếp ngay sau một lượt trúng cache sẽ không thấy lượt đó trong
    lịch sử và trả lời lạc đề — đúng cái giá mà cache không được phép làm phát sinh.
    """
    if "configurable" not in config:
        return
    try:
        graph.update_state(
            config,
            {"messages": [HumanMessage(content=question), AIMessage(content=answer)]},
        )
    except Exception:
        pass
