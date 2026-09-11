"""
Cách diễn đạt tiến trình tra cứu cho người dùng của miền giao thông.

Engine có bản mô tả chung dùng được cho mọi miền ("Tra cứu bằng công cụ `penalty_lookup` với
violation_keyword='vượt đèn đỏ'"). Phần ở đây thay nó bằng câu chữ sát nghiệp vụ ("Tra cứu
khung tiền phạt, tước GPLX và trừ điểm cho vi phạm: 'vượt đèn đỏ'") — thứ người dùng thật sự
đọc trên bảng theo dõi tiến trình.

Đây là trình bày, không phải logic: miền mới bỏ qua tệp này vẫn chạy đầy đủ.
"""

import re
from typing import Any, Dict


def describe_call(tool_name: str, args: Dict[str, Any]) -> str:
    """Lời giải thích mục đích của từng lượt gọi công cụ."""
    if tool_name == "penalty_lookup":
        return f"Tra cứu khung tiền phạt, tước GPLX và trừ điểm cho vi phạm: '{args.get('violation_keyword', '')}'"
    if tool_name == "traffic_sign_lookup":
        return f"Tra cứu ý nghĩa và hình ảnh minh họa biển báo: '{args.get('sign_code_or_name', '')}'"
    if tool_name == "speed_limit_lookup":
        return f"Tra cứu quy định tốc độ và khoảng cách an toàn: '{args.get('query', '')}'"
    if tool_name == "keyword_search":
        return f"Tìm các Điều luật chứa từ khóa: '{args.get('keywords', '')}'"
    if tool_name == "semantic_search":
        return f"Tìm kiếm ngữ nghĩa trong kho luật: '{args.get('question', '')}'"
    if tool_name == "get_article":
        return f"Đọc toàn văn Điều {args.get('article_number', 0)} ({args.get('doc_id', 'Luật 36/2024')})"
    if tool_name == "list_chapters":
        return "Xem mục lục 9 Chương để định vị phạm vi điều chỉnh"
    return ""


def summarize_result(tool_name: str, raw_output: str) -> str:
    """Tóm tắt kết quả công cụ thu về, để giao diện trace hiển thị trực quan."""
    if not raw_output:
        return "Không có dữ liệu trả về."
    if "Không tìm thấy" in raw_output:
        return "Không tìm thấy điều khoản khớp trực tiếp."

    if tool_name == "penalty_lookup":
        lines = [l for l in raw_output.splitlines() if "Mức phạt tiền:" in l]
        return f"Đã tìm thấy {len(lines)} khung mức phạt & chế tài kèm theo."
    if tool_name == "traffic_sign_lookup":
        img_note = " (kèm ảnh minh họa)" if "![" in raw_output else ""
        return f"Đã nạp thông tin biển báo{img_note}."
    if tool_name == "speed_limit_lookup":
        return "Đã nạp quy định tốc độ tối đa & khoảng cách an toàn (Thông tư 31/2019)."
    if tool_name in ("keyword_search", "semantic_search"):
        articles = re.findall(r'📖\s+([^(\n]+)', raw_output)
        if articles:
            shown = ", ".join(a.strip() for a in articles[:2])
            if len(articles) > 2:
                shown += f" và {len(articles) - 2} điều khác"
            return f"Đã tìm thấy: {shown}."
        return "Đã tìm thấy thông tin trích dẫn trong văn bản luật."
    if tool_name == "get_article":
        first_line = raw_output.splitlines()[0] if raw_output.splitlines() else ""
        return f"Đã nạp nội dung: {first_line.replace('===', '').strip()}."
    return ""
