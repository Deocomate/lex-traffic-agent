"""
Dựng bằng chứng có cấu trúc cho từng công cụ của miền giao thông.

Engine luôn dựng được một `Evidence` chung từ nguyên văn kết quả công cụ, đủ để lớp kiểm chứng
tất định làm việc. Các hàm ở đây làm phần hơn thế: bóc ra trích dẫn Điều/Khoản, mã biển báo,
đường dẫn ảnh minh hoạ và điểm liên quan — chính là dữ liệu dựng nên khối "Căn cứ pháp lý" mà
người dùng nhìn thấy dưới mỗi câu trả lời.

Bất biến quan trọng nhất: mọi `Evidence` PHẢI mang `raw_tool_output` là nguyên văn kết quả công
cụ. Node `verify` đối chiếu từng con số trong câu trả lời với đúng trường đó; đưa bản đã cắt gọn
vào sẽ sinh ra hàng loạt cảnh báo "số liệu không có căn cứ" giả.
"""

import re
from typing import Any, Dict, List

DOC_LAW_36 = "01_luat_36_2024_qh15"
DOC_DECREE_168 = "03_nghi_dinh_168_2024_nd_cp"
DOC_CIRCULAR_31 = "04_thong_tu_31_2019_tt_bgtvt"
DOC_QCVN_41 = "06_qcvn_41_2019_bgtvt"


def _tools():
    from domains.vietnam_traffic.tools import _traffic_tools

    return _traffic_tools()


def penalty_lookup(args: Dict[str, Any], raw_output: str) -> List[Dict[str, Any]]:
    """Mỗi hành vi vi phạm khớp được thành một mục bằng chứng riêng, kèm chế tài đầy đủ."""
    keyword = args.get("violation_keyword", "")
    evidences: List[Dict[str, Any]] = []

    for chunk in _tools().penalties.search(keyword):
        vehicle = chunk.get("vehicle", "")
        extra = ", ".join(chunk.get("extra_sanctions", []))
        evidences.append({
            "source": "penalty",
            "parent_id": (
                f"penalty_{chunk.get('article_number')}_{chunk.get('clause_number')}"
                f"_{chunk.get('point_letter') or ''}"
            ),
            "doc_id": DOC_DECREE_168,
            "citation": f"[{vehicle}] {chunk.get('citation', '')}",
            "header": f"{vehicle} - {chunk.get('article_title', '')}",
            "content": (
                f"Hành vi: {chunk.get('behaviour', '')}\n"
                f"Mức phạt tiền: {chunk.get('fine_text', '')}\n"
                f"Trừ điểm GPLX: {chunk.get('points_deducted') or 'Không'}\n"
                f"Xử phạt bổ sung: {extra if extra else 'Không'}"
            ),
            "snippet": f"{chunk.get('behaviour', '')} | Phạt tiền: {chunk.get('fine_text', '')}",
            "score": float(chunk.get("score", 1.0)),
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    return evidences


def traffic_sign_lookup(args: Dict[str, Any], raw_output: str) -> List[Dict[str, Any]]:
    """Biển báo kèm ảnh minh hoạ; ảnh được bóc ra để giao diện hiển thị trực quan."""
    sign_code = args.get("sign_code_or_name", "")
    image = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', raw_output)

    return [{
        "source": "sign",
        "parent_id": f"sign_{sign_code}",
        "doc_id": DOC_QCVN_41,
        "citation": f"QCVN 41:2019 - Biển {sign_code}",
        "header": f"Biển báo / Vạch kẻ: {sign_code}",
        "content": raw_output,
        "snippet": raw_output[:250],
        "score": 1.0,
        "image_path": image.group(2) if image else None,
        "raw_tool_output": raw_output,
    }]


def speed_limit_lookup(args: Dict[str, Any], raw_output: str) -> List[Dict[str, Any]]:
    """Ma trận tốc độ là một khối thống nhất nên chỉ cần một mục bằng chứng."""
    return [{
        "source": "speed",
        "parent_id": "tt31_speed_matrix",
        "doc_id": DOC_CIRCULAR_31,
        "citation": "Thông tư 31/2019/TT-BGTVT",
        "header": "Quy định tốc độ tối đa & khoảng cách an toàn",
        "content": raw_output,
        "snippet": raw_output[:250],
        "score": 1.0,
        "image_path": None,
        "raw_tool_output": raw_output,
    }]


def keyword_search(args: Dict[str, Any], raw_output: str) -> List[Dict[str, Any]]:
    """Mỗi Điều luật khớp từ khoá thành một mục bằng chứng."""
    keywords = args.get("keywords", "")
    evidences: List[Dict[str, Any]] = []

    for article in _tools().search_articles(keywords, max_results=4):
        header = article.get("article_header", "")
        snippets = "\n".join(article.get("snippets", []))
        evidences.append({
            "source": "law",
            "parent_id": f"luat36_dieu_{article.get('article_number', 0)}",
            "doc_id": DOC_LAW_36,
            "citation": f"Luật 36/2024 - {header}",
            "header": header,
            "content": snippets,
            "snippet": snippets[:250],
            "score": float(article.get("score", 50.0)),
            "image_path": None,
            "raw_tool_output": raw_output,
        })

    return evidences


def semantic_search(args: Dict[str, Any], raw_output: str) -> List[Dict[str, Any]]:
    """Các Điều luật do tầng truy xuất lai ghép trả về, giữ nguyên điểm liên quan tương đối."""
    question = args.get("question", "")
    doc_scope = args.get("doc_scope", "all")

    retriever = _tools()._get_vector_retriever()
    if not retriever:
        return []

    scope = None if doc_scope == "all" else [doc_scope]
    try:
        hits = retriever.retrieve_articles(question, doc_ids=scope, top_k=4)
    except Exception:
        return []

    evidences: List[Dict[str, Any]] = []
    for hit in hits:
        doc_short = hit.get("doc_short") or hit.get("doc_name", "Luật")
        header = hit.get("article_header", "")
        evidences.append({
            "source": "law",
            "parent_id": hit.get("parent_id", ""),
            "doc_id": hit.get("doc_id", DOC_LAW_36),
            "citation": f"{doc_short} - {header}",
            "header": f"[{doc_short}] {header}",
            "content": hit.get("page_content", ""),
            "snippet": hit.get("page_content", "")[:250],
            "score": float(hit.get("score", 0.0)),
            "image_path": hit.get("image_path"),
            "raw_tool_output": raw_output,
        })

    return evidences


def get_article(args: Dict[str, Any], raw_output: str) -> List[Dict[str, Any]]:
    """Toàn văn một Điều luật: điểm 100 vì đây là căn cứ do Agent chỉ đích danh."""
    article_number = int(args.get("article_number", 0))
    doc_id = args.get("doc_id") or DOC_LAW_36
    lines = raw_output.splitlines()
    header = lines[0].replace("===", "").strip() if lines else f"Điều {article_number}"

    return [{
        "source": "law",
        "parent_id": f"{doc_id}_dieu_{article_number}",
        "doc_id": doc_id,
        "citation": f"{doc_id} - Điều {article_number}",
        "header": header,
        "content": raw_output,
        "snippet": raw_output[:300],
        "score": 100.0,
        "image_path": None,
        "raw_tool_output": raw_output,
    }]
