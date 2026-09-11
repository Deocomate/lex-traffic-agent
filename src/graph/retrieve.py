"""
Node `tools` của đồ thị: thực thi các tool call do Agent phát ra.

Agent tự quyết định gọi công cụ nào và với tham số gì; module này chỉ thực thi, chuyển kết quả
thành `Evidence` có cấu trúc, và phát sự kiện `tool_call` / `tool_result` cho giao diện theo
dõi tiến trình (AgentTrace).

Bản trước còn giữ 4 node truy xuất song song cố định (`retrieve_penalty/sign/speed/law`) của
kiến trúc fan-out cũ. Đồ thị đã chuyển sang vòng ReAct nên chúng không còn được nối vào đâu
nữa và đã bị gỡ bỏ.
"""

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
