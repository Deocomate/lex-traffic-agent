"""
Tầng truy xuất song song (Parallel Retrieval Nodes) cho StateGraph LangGraph.
Bao gồm 4 node:
1. retrieve_penalty: Tra cứu mức phạt, trừ điểm, tước bằng trên Nghị định 168/2024/NĐ-CP
2. retrieve_sign: Tra cứu biển báo giao thông & vạch kẻ đường trên QCVN 41:2019/BGTVT
3. retrieve_speed: Tra cứu ma trận tốc độ tối đa & cự ly an toàn trên Thông tư 31/2019/TT-BGTVT
4. retrieve_law: Tra cứu lai ghép (BM25 + Dense Vector + RRF) trên toàn bộ 6 văn bản pháp luật

Mỗi node phát sự kiện 'tool_call' trước khi chạy và 'tool_result' sau khi hoàn thành,
bảo toàn nguyên vẹn ngữ điệu tiếng Việt của _format_tool_explanation() và _summarize_tool_result()
cho giao diện theo dõi tiến trình (AgentTrace).
"""

import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import ToolMessage

from src.graph.events import emit
from src.graph.state import Evidence, LegalAgentState
from src.tools.law_search_tools import TrafficLawTools

_tools_instance: Optional[TrafficLawTools] = None


def get_traffic_law_tools() -> TrafficLawTools:
    """Singleton quản lý tài nguyên dữ liệu luật trong RAM."""
    global _tools_instance
    if _tools_instance is None:
        _tools_instance = TrafficLawTools()
    return _tools_instance


def format_tool_explanation(tool_name: str, args: Dict[str, Any]) -> str:
    """Tạo lời giải thích dễ hiểu về mục đích gọi từng công cụ theo quy chuẩn của hệ thống."""
    if tool_name == "penalty_lookup":
        return f"Tra cứu khung tiền phạt, tước GPLX và trừ điểm cho vi phạm: '{args.get('violation_keyword', '')}'"
    elif tool_name == "traffic_sign_lookup":
        return f"Tra cứu ý nghĩa và hình ảnh minh họa biển báo: '{args.get('sign_code_or_name', '')}'"
    elif tool_name == "speed_limit_lookup":
        return f"Tra cứu quy định tốc độ và khoảng cách an toàn: '{args.get('query', '')}'"
    elif tool_name == "keyword_search":
        return f"Tìm các Điều luật chứa từ khóa: '{args.get('keywords', '')}'"
    elif tool_name == "semantic_search":
        return f"Tìm kiếm ngữ nghĩa trong kho luật: '{args.get('question', '')}'"
    elif tool_name == "get_article":
        return f"Đọc toàn văn Điều {args.get('article_number', 0)} ({args.get('doc_id', 'Luật 36/2024')})"
    elif tool_name == "list_chapters":
        return "Xem mục lục 9 Chương để định vị phạm vi điều chỉnh"
    return f"Thực thi {tool_name} với tham số {args}"


def summarize_tool_result(tool_name: str, result_text: str) -> str:
    """Tóm tắt ngắn gọn kết quả công cụ thu về để giao diện trace hiển thị trực quan."""
    if not result_text:
        return "Không có dữ liệu trả về."
    if "Không tìm thấy" in result_text:
        return "Không tìm thấy điều khoản khớp trực tiếp."
    if tool_name == "penalty_lookup":
        lines = [l for l in result_text.splitlines() if "Mức phạt tiền:" in l]
        return f"Đã tìm thấy {len(lines)} khung mức phạt & chế tài kèm theo."
    elif tool_name == "traffic_sign_lookup":
        has_img = "![" in result_text
        img_note = " (kèm ảnh minh họa)" if has_img else ""
        return f"Đã nạp thông tin biển báo{img_note}."
    elif tool_name == "speed_limit_lookup":
        return "Đã nạp quy định tốc độ tối đa & khoảng cách an toàn (Thông tư 31/2019)."
    elif tool_name in ("keyword_search", "semantic_search"):
        articles = re.findall(r'📖\s+([^(\n]+)', result_text)
        if articles:
            arts_str = ", ".join(a.strip() for a in articles[:2])
            if len(articles) > 2:
                arts_str += f" và {len(articles) - 2} điều khác"
            return f"Đã tìm thấy: {arts_str}."
        return "Đã tìm thấy thông tin trích dẫn trong văn bản luật."
    elif tool_name == "get_article":
        first_line = result_text.splitlines()[0] if result_text.splitlines() else ""
        return f"Đã nạp nội dung: {first_line.replace('===', '').strip()}."
    return "Đã thu thập dữ liệu thành công."


# =====================================================================
# Bộ thực thi Tool Gọi Tự Động Cho Multi-Turn Agent
# =====================================================================

def execute_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    turn: int = 1,
) -> Tuple[str, List[Evidence], Dict[str, Any]]:
    """
    Thực thi một tool call do Agent phát ra, phát sự kiện SSE tool_call & tool_result,
    thu thập bằng chứng Evidence và ghi nhận bước thực thi agent_step.
    """
    desc = format_tool_explanation(tool_name, args)
    step = {
        "turn": turn,
        "action": tool_name,
        "args": args,
        "description": desc,
    }
    emit("tool_call", f"🛠️ {desc}", **step)

    tools = get_traffic_law_tools()
    raw_output = ""
    evidences: List[Evidence] = []

    if tool_name == "penalty_lookup":
        kw = args.get("violation_keyword", "")
        raw_output = tools.penalty_lookup(kw)
        chunks = tools.penalties.search(kw)
        for c in chunks:
            cid = f"penalty_{c.get('article_number')}_{c.get('clause_number')}_{c.get('point_letter') or ''}"
            vehicle = c.get("vehicle", "")
            citation = f"[{vehicle}] {c.get('citation', '')}"
            extra = ", ".join(c.get("extra_sanctions", []))
            content = (
                f"Hành vi: {c.get('behaviour', '')}\n"
                f"Mức phạt tiền: {c.get('fine_text', '')}\n"
                f"Trừ điểm GPLX: {c.get('points_deducted') or 'Không'}\n"
                f"Xử phạt bổ sung: {extra if extra else 'Không'}"
            )
            evidences.append({
                "source": "penalty",
                "parent_id": cid,
                "doc_id": "03_nghi_dinh_168_2024_nd_cp",
                "citation": citation,
                "header": f"{vehicle} - {c.get('article_title', '')}",
                "content": content,
                "snippet": f"{c.get('behaviour', '')} | Phạt tiền: {c.get('fine_text', '')}",
                "score": float(c.get("score", 1.0)),
                "image_path": None,
                "raw_tool_output": raw_output,
            })
        if not evidences and raw_output:
            evidences.append({
                "source": "penalty",
                "parent_id": "penalty_raw",
                "doc_id": "03_nghi_dinh_168_2024_nd_cp",
                "citation": "Nghị định 168/2024/NĐ-CP",
                "header": "Kết quả tra cứu mức phạt",
                "content": raw_output,
                "snippet": raw_output[:250],
                "score": 0.5,
                "image_path": None,
                "raw_tool_output": raw_output,
            })

    elif tool_name == "traffic_sign_lookup":
        sign_code = args.get("sign_code_or_name", "")
        raw_output = tools.traffic_sign_lookup(sign_code)
        img_match = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', raw_output)
        img_path = img_match.group(2) if img_match else None
        evidences.append({
            "source": "sign",
            "parent_id": f"sign_{sign_code}",
            "doc_id": "06_qcvn_41_2019_bgtvt",
            "citation": f"QCVN 41:2019 - Biển {sign_code}",
            "header": f"Biển báo / Vạch kẻ: {sign_code}",
            "content": raw_output,
            "snippet": raw_output[:250],
            "score": 1.0,
            "image_path": img_path,
            "raw_tool_output": raw_output,
        })

    elif tool_name == "speed_limit_lookup":
        query = args.get("query", "")
        raw_output = tools.speed_limit_lookup(query)
        evidences.append({
            "source": "speed",
            "parent_id": "tt31_speed_matrix",
            "doc_id": "04_thong_tu_31_2019_tt_bgtvt",
            "citation": "Thông tư 31/2019/TT-BGTVT",
            "header": "Quy định tốc độ tối đa & khoảng cách an toàn",
            "content": raw_output,
            "snippet": raw_output[:250],
            "score": 1.0,
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    elif tool_name == "keyword_search":
        keywords = args.get("keywords", "")
        raw_output = tools.keyword_search(keywords)
        matched_articles = tools.search_articles(keywords, max_results=4)
        for art in matched_articles:
            art_num = art.get("article_number", 0)
            header = art.get("article_header", "")
            snippets = "\n".join(art.get("snippets", []))
            evidences.append({
                "source": "law",
                "parent_id": f"luat36_dieu_{art_num}",
                "doc_id": "01_luat_36_2024_qh15",
                "citation": f"Luật 36/2024 - {header}",
                "header": header,
                "content": snippets,
                "snippet": snippets[:250],
                "score": float(art.get("score", 50.0)),
                "image_path": None,
                "raw_tool_output": raw_output,
            })
        if not evidences and raw_output:
            evidences.append({
                "source": "law",
                "parent_id": "law_kw_raw",
                "doc_id": "01_luat_36_2024_qh15",
                "citation": "Luật Trật tự, an toàn giao thông đường bộ 2024",
                "header": f"Tìm kiếm từ khóa: {keywords}",
                "content": raw_output,
                "snippet": raw_output[:250],
                "score": 0.5,
                "image_path": None,
                "raw_tool_output": raw_output,
            })

    elif tool_name == "semantic_search":
        question = args.get("question", "")
        doc_scope = args.get("doc_scope", "all")
        raw_output = tools.semantic_search(question, doc_scope=doc_scope)
        retriever = tools._get_vector_retriever()
        scope = None if doc_scope == "all" else [doc_scope]
        hits = []
        if retriever:
            try:
                hits = retriever.retrieve_articles(question, doc_ids=scope, top_k=4)
            except Exception:
                hits = []
        for hit in hits:
            doc_id = hit.get("doc_id", "01_luat_36_2024_qh15")
            doc_short = hit.get("doc_short", "Luật")
            header = hit.get("article_header", "")
            evidences.append({
                "source": "law",
                "parent_id": hit.get("parent_id", ""),
                "doc_id": doc_id,
                "citation": f"{doc_short} - {header}",
                "header": f"[{doc_short}] {header}",
                "content": hit.get("page_content", ""),
                "snippet": hit.get("page_content", "")[:250],
                "score": float(hit.get("score", 0.0)),
                "image_path": hit.get("image_path"),
                "raw_tool_output": raw_output,
            })
        if not evidences and raw_output:
            evidences.append({
                "source": "law",
                "parent_id": "law_sem_raw",
                "doc_id": "01_luat_36_2024_qh15",
                "citation": "Chỉ mục pháp luật giao thông",
                "header": f"Tìm kiếm ngữ nghĩa: {question}",
                "content": raw_output,
                "snippet": raw_output[:250],
                "score": 0.5,
                "image_path": None,
                "raw_tool_output": raw_output,
            })

    elif tool_name == "get_article":
        art_num = int(args.get("article_number", 0))
        doc_id = args.get("doc_id", "01_luat_36_2024_qh15")
        raw_output = tools.get_article(art_num, doc_id=doc_id)
        first_line = raw_output.splitlines()[0] if raw_output.splitlines() else f"Điều {art_num}"
        header = first_line.replace("===", "").strip()
        evidences.append({
            "source": "law",
            "parent_id": f"{doc_id}_dieu_{art_num}",
            "doc_id": doc_id,
            "citation": f"{doc_id} - Điều {art_num}",
            "header": header,
            "content": raw_output,
            "snippet": raw_output[:300],
            "score": 100.0,
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    elif tool_name == "list_chapters":
        raw_output = tools.list_chapters()

    else:
        raw_output = f"Không tìm thấy công cụ {tool_name}"

    summary = summarize_tool_result(tool_name, raw_output)
    step["summary"] = summary
    emit("tool_result", f"📥 {summary}", turn=turn, action=tool_name, summary=summary)

    return raw_output, evidences, step


def tools_node(state: LegalAgentState) -> Dict[str, Any]:
    """Node tools trong LangGraph: Thực thi toàn bộ các tool call do Agent yêu cầu."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []
    if not tool_calls:
        return {}

    turn = state.get("turn_count", 1)
    new_messages = []
    new_evidences: List[Evidence] = []
    new_steps: List[Dict[str, Any]] = []

    for tc in tool_calls:
        tool_name = tc.get("name", "")
        tool_args = tc.get("args") or {}
        tool_call_id = tc.get("id") or str(uuid.uuid4())

        raw_output, evidences, step = execute_tool_call(tool_name, tool_args, turn=turn)

        new_messages.append(ToolMessage(content=raw_output, tool_call_id=tool_call_id, name=tool_name))
        new_evidences.extend(evidences)
        new_steps.append(step)

    return {
        "messages": new_messages,
        "evidence": new_evidences,
        "agent_steps": new_steps,
    }


# =====================================================================
# 1. Node Tra cứu Mức phạt Nghị định 168/2024
# =====================================================================

def retrieve_penalty(state: LegalAgentState) -> Dict[str, Any]:
    """Node truy xuất các khung tiền phạt, trừ điểm GPLX và tước bằng."""
    route = state.get("route")
    query = (
        route.search_query.strip()
        if route and route.search_query.strip()
        else state.get("grounding_query") or state.get("question", "")
    )

    desc = format_tool_explanation("penalty_lookup", {"violation_keyword": query})
    step = {
        "turn": 1,
        "action": "penalty_lookup",
        "args": {"violation_keyword": query},
        "description": desc,
    }
    emit("tool_call", f"🛠️ {desc}", **step)

    tools = get_traffic_law_tools()
    raw_output = tools.penalties.lookup(query)
    summary = summarize_tool_result("penalty_lookup", raw_output)
    emit("tool_result", f"📥 {summary}", turn=1, action="penalty_lookup", summary=summary)

    # Chuyển đổi các bản ghi phạt thành cấu trúc Evidence
    chunks = tools.penalties.search(query)
    evidences: List[Evidence] = []
    for c in chunks:
        cid = f"penalty_{c.get('article_number')}_{c.get('clause_number')}_{c.get('point_letter') or ''}"
        vehicle = c.get("vehicle", "")
        citation = f"[{vehicle}] {c.get('citation', '')}"
        extra = ", ".join(c.get("extra_sanctions", []))
        content = (
            f"Hành vi: {c.get('behaviour', '')}\n"
            f"Mức phạt tiền: {c.get('fine_text', '')}\n"
            f"Trừ điểm GPLX: {c.get('points_deducted') or 'Không'}\n"
            f"Xử phạt bổ sung: {extra if extra else 'Không'}"
        )
        evidences.append({
            "source": "penalty",
            "parent_id": cid,
            "doc_id": "03_nghi_dinh_168_2024_nd_cp",
            "citation": citation,
            "header": f"{vehicle} - {c.get('article_title', '')}",
            "content": content,
            "snippet": f"{c.get('behaviour', '')} | Phạt tiền: {c.get('fine_text', '')}",
            "score": float(c.get("score", 1.0)),
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    if not evidences and raw_output:
        evidences.append({
            "source": "penalty",
            "parent_id": "penalty_raw",
            "doc_id": "03_nghi_dinh_168_2024_nd_cp",
            "citation": "Nghị định 168/2024/NĐ-CP",
            "header": "Kết quả tra cứu mức phạt",
            "content": raw_output,
            "snippet": summary,
            "score": 0.5,
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    return {
        "evidence": evidences,
        "agent_steps": [step],
    }


# =====================================================================
# 2. Node Tra cứu Biển báo & Vạch kẻ QCVN 41:2019
# =====================================================================

def retrieve_sign(state: LegalAgentState) -> Dict[str, Any]:
    """Node truy xuất danh mục biển báo giao thông và vạch kẻ đường kèm ảnh minh họa."""
    route = state.get("route")
    query = (
        route.search_query.strip()
        if route and route.search_query.strip()
        else state.get("grounding_query") or state.get("question", "")
    )

    tools = get_traffic_law_tools()

    # Nhận diện mã hiệu biển báo (P.106a, W.201, R.403a, Vạch 1.1...) hoặc dùng query
    sign_code_match = re.search(r'\b([PWIROS]\.\d+[a-z]?|Vạch\s*\d+\.\d+)\b', query, re.IGNORECASE)
    if not sign_code_match:
        orig_q = state.get("question", "")
        sign_code_match = re.search(r'\b([PWIROS]\.\d+[a-z]?|Vạch\s*\d+\.\d+)\b', orig_q, re.IGNORECASE)

    lookup_query = sign_code_match.group(1) if sign_code_match else query

    desc = format_tool_explanation("traffic_sign_lookup", {"sign_code_or_name": lookup_query})
    step = {
        "turn": 1,
        "action": "traffic_sign_lookup",
        "args": {"sign_code_or_name": lookup_query},
        "description": desc,
    }
    emit("tool_call", f"🛠️ {desc}", **step)

    raw_output = tools.traffic_sign_lookup(lookup_query)
    # Nếu dùng lookup_query không tìm thấy và khác query, thử lại bằng query đầy đủ
    if "KHÔNG TÌM THẤY BÁO HIỆU" in raw_output and lookup_query != query:
        fallback_output = tools.traffic_sign_lookup(query)
        if "KHÔNG TÌM THẤY BÁO HIỆU" not in fallback_output:
            raw_output = fallback_output
            lookup_query = query

    summary = summarize_tool_result("traffic_sign_lookup", raw_output)
    emit("tool_result", f"📥 {summary}", turn=1, action="traffic_sign_lookup", summary=summary)

    blocks = re.findall(r'🚸\s+\*\*([^:]+):\s*([^*]+)\*\*(?:\s*\(([^)]+)\))?', raw_output)
    img_matches = dict(re.findall(r'!\[([^\]]+)\]\(([^)]+)\)', raw_output))

    evidences: List[Evidence] = []
    for item in blocks:
        code = item[0].strip()
        name = item[1].strip()
        group = item[2].strip() if len(item) > 2 and item[2] else "Biển báo đường bộ"
        img_url = ""
        for alt, url in img_matches.items():
            if code.lower() in url.lower() or name.lower() in alt.lower() or code.lower() in alt.lower():
                img_url = url
                break
        if not img_url and img_matches:
            img_url = list(img_matches.values())[0]

        evidences.append({
            "source": "sign",
            "parent_id": f"sign_{code}",
            "doc_id": "06_qcvn_41_2019_bgtvt",
            "citation": f"QCVN 41:2019 - Biển {code} ({name})",
            "header": f"Biển {code}: {name}",
            "content": f"Biển {code}: {name} ({group}).\nHình ảnh: ![{name}]({img_url})" if img_url else f"Biển {code}: {name} ({group})",
            "snippet": f"Biển hiệu {code} - {name}",
            "score": 1.0,
            "image_path": img_url if img_url else None,
            "raw_tool_output": raw_output,
        })

    if not evidences and raw_output:
        evidences.append({
            "source": "sign",
            "parent_id": "sign_raw",
            "doc_id": "06_qcvn_41_2019_bgtvt",
            "citation": "QCVN 41:2019/BGTVT",
            "header": "Quy chuẩn báo hiệu đường bộ",
            "content": raw_output,
            "snippet": summary,
            "score": 0.5,
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    return {
        "evidence": evidences,
        "agent_steps": [step],
    }


# =====================================================================
# 3. Node Tra cứu Tốc độ & Cự ly an toàn Thông tư 31/2019
# =====================================================================

def retrieve_speed(state: LegalAgentState) -> Dict[str, Any]:
    """Node truy xuất ma trận tốc độ tối đa cho phép và khoảng cách an toàn."""
    route = state.get("route")
    query = (
        route.search_query.strip()
        if route and route.search_query.strip()
        else state.get("grounding_query") or state.get("question", "")
    )

    desc = format_tool_explanation("speed_limit_lookup", {"query": query})
    step = {
        "turn": 1,
        "action": "speed_limit_lookup",
        "args": {"query": query},
        "description": desc,
    }
    emit("tool_call", f"🛠️ {desc}", **step)

    tools = get_traffic_law_tools()
    raw_output = tools.speed_limit_lookup(query)
    summary = summarize_tool_result("speed_limit_lookup", raw_output)
    emit("tool_result", f"📥 {summary}", turn=1, action="speed_limit_lookup", summary=summary)

    evidence_item: Evidence = {
        "source": "speed",
        "parent_id": "tt31_speed_matrix",
        "doc_id": "04_thong_tu_31_2019_tt_bgtvt",
        "citation": "Thông tư 31/2019/TT-BGTVT",
        "header": "Quy định tốc độ tối đa & khoảng cách an toàn",
        "content": raw_output,
        "snippet": summary,
        "score": 1.0,
        "image_path": None,
        "raw_tool_output": raw_output,
    }

    return {
        "evidence": [evidence_item],
        "agent_steps": [step],
    }


# =====================================================================
# 4. Node Truy xuất Lai ghép Điều luật (Luật 36, Luật 35, v.v.)
# =====================================================================

def retrieve_law(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node truy xuất lai ghép (Hybrid Retrieval) luôn luôn chạy.
    Sử dụng RRF kết hợp BM25 + Dense Vector để thu thập căn cứ Điều luật gốc.
    """
    route = state.get("route")
    query = (
        route.search_query.strip()
        if route and route.search_query.strip()
        else state.get("grounding_query") or state.get("question", "")
    )

    desc = format_tool_explanation("semantic_search", {"question": query})
    step = {
        "turn": 1,
        "action": "semantic_search",
        "args": {"question": query},
        "description": desc,
    }
    emit("tool_call", f"🛠️ {desc}", **step)

    tools = get_traffic_law_tools()
    doc_scope = getattr(route, "doc_scope", "all") if route else "all"

    # Gọi trực tiếp bộ truy xuất hybrid phân cấp
    retriever = tools._get_vector_retriever()
    scope = None if doc_scope == "all" else [doc_scope]

    hits: List[Dict[str, Any]] = []
    if retriever:
        try:
            hits = retriever.retrieve_articles(query, doc_ids=scope, top_k=6)
        except Exception:
            hits = []

    if not hits:
        try:
            kw_hits = tools.search_articles(query, max_results=4)
            for h in kw_hits:
                hits.append({
                    "parent_id": f"01_luat_36_dieu_{h['article_number']}",
                    "doc_id": "01_luat_36_2024_qh15",
                    "doc_name": "Luật 36/2024",
                    "doc_short": "Luật 36",
                    "article_header": h.get("article_header", ""),
                    "page_content": "\n".join(h.get("snippets", [])),
                    "score": float(h.get("score", 50.0)),
                })
        except Exception:
            pass

    articles_str = ", ".join(h.get("article_header", "") for h in hits[:2] if h.get("article_header"))
    summary = f"Đã tìm thấy: {articles_str}." if hits else "Không tìm thấy điều khoản khớp trực tiếp."
    emit("tool_result", f"📥 {summary}", turn=1, action="semantic_search", summary=summary)

    raw_output = "\n".join(
        f"📖 [{h.get('doc_short', 'Luật')}] {h.get('article_header', '')}\n{h.get('page_content', '')[:1000]}"
        for h in hits
    ) if hits else "Không tìm thấy điều khoản phù hợp."

    evidences: List[Evidence] = []
    for hit in hits:
        pid = hit.get("parent_id", "")
        doc_id = hit.get("doc_id", "01_luat_36_2024_qh15")
        doc_name = hit.get("doc_name", "Luật Giao thông")
        doc_short = hit.get("doc_short", doc_name)
        header = hit.get("article_header", "")
        clauses = hit.get("key_clauses", [])
        snippet = "\n".join(c.strip() for c in clauses[:2] if c) if clauses else hit.get("page_content", "")[:250]

        evidences.append({
            "source": "law",
            "parent_id": pid,
            "doc_id": doc_id,
            "citation": f"{doc_short} - {header}",
            "header": f"[{doc_short}] {header}",
            "content": hit.get("page_content", ""),
            "snippet": snippet,
            "score": float(hit.get("score", 0.0)),
            "image_path": hit.get("image_path"),
            "raw_tool_output": raw_output,
        })

    if not evidences and raw_output:
        evidences.append({
            "source": "law",
            "parent_id": "law_raw",
            "doc_id": "01_luat_36_2024_qh15",
            "citation": "Hệ thống văn bản pháp luật giao thông",
            "header": "Kết quả tra cứu điều luật",
            "content": raw_output,
            "snippet": summary,
            "score": 0.5,
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    return {
        "evidence": evidences,
        "agent_steps": [step],
    }


# Aliases thuận tiện cho build graph
retrieve_penalty_node = retrieve_penalty
retrieve_law_node = retrieve_law
retrieve_sign_node = retrieve_sign
retrieve_speed_node = retrieve_speed


def route_fanout(state: LegalAgentState) -> List[str]:
    """
    Xác định danh sách các node truy xuất cần chạy song song:
    - retrieve_law luôn luôn chạy để đảm bảo trích dẫn Điều luật gốc
    - retrieve_penalty nếu 'penalty' in intents
    - retrieve_sign nếu 'sign' in intents
    - retrieve_speed nếu 'speed' in intents
    """
    route = state.get("route")
    intents = set(route.intents if route else ["law"])

    nodes = ["retrieve_law"]
    if "penalty" in intents:
        nodes.append("retrieve_penalty")
    if "sign" in intents:
        nodes.append("retrieve_sign")
    if "speed" in intents:
        nodes.append("retrieve_speed")

    return nodes


