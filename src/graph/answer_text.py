"""
Làm sạch văn bản câu trả lời trước khi đưa ra người dùng.

Hai việc, đều thuần tuý xử lý chuỗi và không gọi mô hình:
- `clean_text_output`: bóc các thẻ nội bộ của LLM (DSML, `<tool_call>`) và thay tên kỹ thuật
  của công cụ bằng ngôn ngữ thường, phòng khi mô hình nhắc tên chúng ra màn hình.
- `polish_answer`: cắt câu râu ria mở đầu kiểu "theo kết quả tra cứu, ..." và chuẩn hoá chữ hoa.

Trước đây module này còn chứa `synthesize_node` của kiến trúc cũ (một node sinh câu trả lời
riêng, không bind tool). Vòng ReAct hiện tại để chính `agent_node` sinh câu trả lời khi nó thấy
đã đủ dữ liệu, nên node đó không còn được nối vào đồ thị và đã bị gỡ bỏ.
"""

import re

# Tên kỹ thuật của công cụ -> ngôn ngữ thường (phòng ngừa model nhắc tên)
TOOL_NAME_ALIASES = {
    "penalty_lookup": "tra cứu mức phạt",
    "traffic_sign_lookup": "tra cứu biển báo giao thông",
    "speed_limit_lookup": "tra cứu quy định tốc độ",
    "keyword_search": "tra cứu từ khóa điều luật",
    "semantic_search": "tra cứu ngữ nghĩa điều luật",
    "get_article": "đọc toàn văn điều luật",
    "list_chapters": "tra cứu mục lục chương",
}


def clean_text_output(text: str) -> str:
    """Loại bỏ các thẻ mã nội bộ của LLM (DSML, XML tool tags) nếu có."""
    if not text:
        return ""
    for tool_name, alias in TOOL_NAME_ALIASES.items():
        text = re.sub(rf'`?\b{tool_name}\b`?', alias, text)
    text = re.sub(r'<｜DSML｜tool_calls>.*?</｜DSML｜tool_calls>', '', text, flags=re.DOTALL)
    text = re.sub(r'<｜DSML｜[^>]+>', '', text)
    text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL)
    text = re.sub(r'<tool_call>.*', '', text, flags=re.DOTALL)
    text = re.sub(r'<\|.*?\|>', '', text)
    return text.strip()


def polish_answer(text: str) -> str:
    """Loại bỏ các câu râu ria nội bộ ở đầu câu và chuẩn hóa chữ viết hoa đầu dòng."""
    if not text:
        return ""

    for pattern, replacement in (
        (r'^\s*theo dữ liệu tra cứu (?:được )?(?:từ|trong|của)\s+', 'Theo '),
        (r'^\s*(?:dựa (?:trên|vào)|căn cứ)\s+(?:kết quả|dữ liệu)\s+tra cứu[^,:.\n]{0,70}[,:]\s*', ''),
        (r'^\s*kết quả tra cứu cho câu hỏi\s*"[^"\n]*"\s*cho thấy\s*', ''),
        (r'^\s*theo (?:kết quả|dữ liệu) tra cứu[,:]\s*', ''),
    ):
        new = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)
        if new != text:
            text = new
            break

    text = re.sub(r'[^.\n]*độ liên quan[^.\n]*\d+[.,]?\d*\s*%[^.\n]*\.\s*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'^.*CHỈ DẪN NỘI BỘ.*$\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = text.strip()

    match = re.search(r'[A-Za-zÀ-ỹ]', text)
    if match and text[match.start()].islower():
        i = match.start()
        text = text[:i] + text[i].upper() + text[i + 1:]
    return text
