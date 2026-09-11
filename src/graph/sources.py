"""
Node dựng danh sách nguồn trích dẫn pháp lý (Phase 5).

Khác với kiến trúc cũ phải bóc tách ngược cấu trúc từ chuỗi văn bản đã được công cụ
format ra (regex trên '📖', '• [', '🚸'), node này đọc thẳng các trường của `Evidence`
— dữ liệu đã có cấu trúc ngay từ tầng truy xuất.

Hai hành vi của bản cũ được giữ nguyên vì chúng quan trọng:
1. Chỉ lấy Điều luật từ dòng tiêu đề kết quả, không quét thân điều luật (thân điều
   tham chiếu chéo nhiều điều khác không liên quan, quét hết làm nhiễu danh sách nguồn).
2. Đối chiếu sự tồn tại của Điều qua DocumentProvider trước khi đưa vào `sources`.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage

from src.answer_guard import (
    all_tools_returned_no_data,
    build_search_link,
    is_uncertain_answer,
)
from src.graph.events import emit
from src.graph.state import Evidence, LegalAgentState
from src.tools.document_provider import get_document_provider

# Câu trả lời tự tuyên bố câu hỏi nằm ngoài lĩnh vực của trợ lý.
#
# `is_uncertain_answer()` trong `answer_guard.py` đã bắt các lối nói kiểu "chưa có dữ liệu",
# "ngoài phạm vi", "không thuộc phạm vi". Nhưng model còn từ chối bằng nhiều lối nói khác mà
# regex đó không phủ — đo trên bộ eval 95 câu: 4/16 câu lạc đề bị chấm trượt dù câu trả lời
# TỪ CHỐI RẤT ĐÚNG, chỉ vì dùng chữ khác:
#   qa_090 "không thuộc **lĩnh vực**"  (regex cũ chỉ có "không thuộc phạm vi")
#   qa_083 "tôi **chỉ được cung cấp** dữ liệu pháp luật về giao thông đường bộ"
#   qa_084 "tôi là **trợ lý pháp luật chuyên về** ... không có chức năng"
#
# Hệ quả thật, không phải chuyện điểm số: `needs_search` không bật thì `done` không kèm liên kết
# tra cứu ngoài, nên người dùng hỏi lạc đề bị từ chối mà KHÔNG được mời tra Google — đúng lúc họ
# cần lối thoát đó nhất.
#
# Sửa ở đây chứ không sửa `answer_guard.py`: tệp đó được chốt giữ nguyên 100% trong `plan.md`
# (Quyết Định Đã Chốt số 1) vì là lớp phòng vệ tất định đã kiểm chứng trên dữ liệu thật.
_OUT_OF_DOMAIN_REFUSAL = re.compile(
    r'không thuộc\s+(?:lĩnh vực|chuyên môn|chức năng)'
    r'|ngoài\s+(?:lĩnh vực|chuyên môn)'
    r'|không có\s+(?:chức năng|thẩm quyền)'
    r'|(?:tôi là|tôi chỉ là)\s+(?:trợ lý|chatbot)[^.]{0,60}(?:giao thông|pháp luật)',
    re.IGNORECASE,
)

# Đã thử thêm nhánh rộng hơn `chỉ (được cung cấp|trả lời)...(giao thông|pháp luật)` và bỏ đi:
# nó khớp nhầm câu mở đầu mang tính khuôn mẫu "tôi chỉ trả lời dựa trên 6 văn bản quy phạm pháp
# luật" xuất hiện trong CÁC CÂU TRẢ LỜI ĐÚNG TRONG PHẠM VI — câu đó nói về nguồn dữ liệu, không
# phải lời từ chối. Giữ đúng những lối nói không thể hiểu nhầm.


def declines_as_out_of_domain(answer: str) -> bool:
    """True khi chính câu trả lời tuyên bố câu hỏi nằm ngoài lĩnh vực của trợ lý."""
    return bool(answer) and bool(_OUT_OF_DOMAIN_REFUSAL.search(answer))


# Giữ nguyên hạn mức của kiến trúc cũ: MAX_SOURCES = 6, cộng thêm 4 chỗ cho nguồn phong phú
MAX_SOURCES = 6
SOURCES_LIMIT = MAX_SOURCES + 4

# Tiêu đề Điều luật do tầng truy xuất sinh ra luôn ở dạng "[Luật 36] Điều 57. <tiêu đề>"
_ARTICLE_IN_HEADER = re.compile(r'Điều\s+(\d{1,3})\b', re.IGNORECASE)
_ARTICLE_IN_PARENT_ID = re.compile(r'dieu[_-](\d{1,3})\b', re.IGNORECASE)


def _article_number(evidence: Evidence) -> Optional[int]:
    """Lấy số Điều từ tiêu đề kết quả; trả None khi bằng chứng không gắn với một Điều cụ thể."""
    for field in ("header", "citation"):
        match = _ARTICLE_IN_HEADER.search(evidence.get(field) or "")
        if match:
            return int(match.group(1))

    match = _ARTICLE_IN_PARENT_ID.search(evidence.get("parent_id") or "")
    if match:
        return int(match.group(1))
    return None


def _article_exists(doc_id: str, number: int) -> bool:
    """Điều luật này có thật trong văn bản không (đối chiếu qua DocumentProvider)."""
    provider = get_document_provider()
    try:
        if number in (provider._articles_content.get(doc_id) or {}):
            return True
        tree = provider._trees.get(doc_id) or {}
        for chapter in tree.get("chapters", []):
            for article in chapter.get("articles", []):
                if int(article.get("article_number", -1)) == number:
                    return True
        return False
    except Exception:
        # Thiếu dữ liệu đối chiếu thì tin vào tầng truy xuất, không loại bỏ nguồn hợp lệ
        return True


def _parse_penalty_content(content: str) -> Dict[str, str]:
    """Đọc lại các trường mà retrieve_penalty đã ghi theo định dạng cố định của chính hệ thống."""
    fields = {"behaviour": "", "fine_text": "", "points": ""}
    for line in (content or "").splitlines():
        line = line.strip()
        if line.startswith("Hành vi:"):
            fields["behaviour"] = line.split(":", 1)[1].strip()
        elif line.startswith("Mức phạt tiền:"):
            fields["fine_text"] = line.split(":", 1)[1].strip()
        elif line.startswith("Trừ điểm GPLX:"):
            fields["points"] = line.split(":", 1)[1].strip()
    return fields


def _split_penalty_citation(citation: str) -> Tuple[str, str]:
    """Tách "[Ô tô] Điểm c Khoản 9 Điều 6" thành (vehicle, citation)."""
    match = re.match(r'^\s*\[([^\]]+)\]\s*(.*)$', citation or "")
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", (citation or "").strip()


def _split_sign_header(header: str) -> Tuple[str, str]:
    """Tách "Biển P.124a: Cấm quay đầu xe" thành (code, name)."""
    match = re.match(r'^\s*(?:Biển\s+)?([^:]+?)\s*:\s*(.+)$', header or "")
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return (header or "").strip(), ""


def build_sources_from_evidence(evidence_list: List[Evidence]) -> List[Dict[str, Any]]:
    """
    Dựng danh sách nguồn trích dẫn cho giao diện từ bằng chứng có cấu trúc.
    Thứ tự ưu tiên giữ nguyên như kiến trúc cũ: nghị định -> biển báo -> điều luật.
    """
    decree_sources: List[Dict[str, Any]] = []
    sign_sources: List[Dict[str, Any]] = []
    law_sources: List[Dict[str, Any]] = []

    seen_decree: set = set()
    seen_signs: set = set()
    seen_articles: set = set()

    provider = get_document_provider()

    for ev in evidence_list or []:
        source = ev.get("source", "law")

        if source == "penalty":
            vehicle, citation = _split_penalty_citation(ev.get("citation", ""))
            if not citation or citation in seen_decree:
                continue
            seen_decree.add(citation)
            fields = _parse_penalty_content(ev.get("content", ""))
            decree_sources.append({
                "source_type": "decree",
                "doc_name": "Nghị định 168/2024/NĐ-CP",
                "doc_short": "NĐ 168/2024",
                "citation": citation,
                "vehicle": vehicle,
                "behaviour": fields["behaviour"],
                "fine_text": fields["fine_text"],
                "points": fields["points"],
            })

        elif source == "sign":
            code, name = _split_sign_header(ev.get("header", ""))
            if not code or code in seen_signs:
                continue
            seen_signs.add(code)
            sign_sources.append({
                "source_type": "sign",
                "doc_name": "QCVN 41:2019/BGTVT",
                "doc_short": "QCVN 41",
                "sign_code": code,
                "sign_name": name,
                "image_url": ev.get("image_path") or "",
                "citation": f"QCVN 41:2019 - Biển {code}",
            })

        elif source in ("law", "speed"):
            number = _article_number(ev)
            if number is None:
                continue
            doc_id = ev.get("doc_id") or "01_luat_36_2024_qh15"
            key = (doc_id, number)
            if key in seen_articles or not _article_exists(doc_id, number):
                continue
            seen_articles.add(key)

            meta = provider.get_document_meta(doc_id) or {}
            doc_short = meta.get("short_title", "Luật 36/2024")
            article_header = f"Điều {number}"
            try:
                article = provider.get_article(doc_id, number)
                if article and article.get("article_header"):
                    article_header = article["article_header"]
            except Exception:
                pass

            law_sources.append({
                "source_type": "law",
                "doc_id": doc_id,
                "doc_name": meta.get("full_title", "Luật 36/2024/QH15"),
                "doc_short": doc_short,
                "doc_code": meta.get("code", ""),
                "article_number": number,
                "article_header": article_header,
                "citation": f"{doc_short} - Điều {number}",
            })

    return (decree_sources + sign_sources + law_sources)[:SOURCES_LIMIT]


def build_sources_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node cuối đồ thị: chốt danh sách nguồn, xác định vùng ngoài hiểu biết, phát sự kiện `done`.

    Ba dấu hiệu của vùng ngoài hiểu biết giữ nguyên từ kiến trúc cũ: kiểm chứng thất bại,
    mọi công cụ đều báo không có dữ liệu, hoặc chính câu trả lời thừa nhận chưa biết.
    """
    evidence = state.get("evidence", [])
    sources = state.get("sources") or build_sources_from_evidence(evidence)
    answer = state.get("answer", "")
    issues = state.get("issues", []) or []
    question = state.get("question", "")

    tool_outputs = [ev.get("raw_tool_output", "") for ev in evidence if ev.get("raw_tool_output")]

    needs_search = bool(
        issues
        or not answer
        or all_tools_returned_no_data(tool_outputs)
        or is_uncertain_answer(answer)
        or declines_as_out_of_domain(answer)
    )
    search = build_search_link(question) if needs_search else None

    emit(
        "done",
        "✅ Hoàn tất tra cứu và giải đáp!",
        answer=answer,
        agent_steps=state.get("agent_steps", []),
        sources=sources,
        verification_issues=issues,
        needs_search=needs_search,
        search=search,
        model_used=state.get("model_used", ""),
        thread_id=state.get("thread_id", ""),
    )

    result: Dict[str, Any] = {
        "sources": sources,
        "needs_search": needs_search,
        "search": search,
    }

    # Chỉ câu trả lời đã vượt kiểm chứng mới được vào lịch sử hội thoại: lượt sau dùng chính
    # lịch sử này làm nguồn đối chiếu, nên một câu đã bị huỷ mà lọt vào đây sẽ hợp thức hoá
    # đúng những con số vừa bị bắt.
    #
    # Câu hỏi đi kèm câu trả lời, không sớm hơn: với checkpointer của Phase 6, `messages` là
    # nguồn lịch sử duy nhất, nên ghi câu hỏi vào lúc câu trả lời bị huỷ sẽ để lại một lượt
    # hỏi cụt không có đáp án trong mọi lượt sau.
    if answer and not issues:
        result["messages"] = [HumanMessage(content=question), AIMessage(content=answer)]
    return result
