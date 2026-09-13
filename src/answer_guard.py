"""
LỚP KIỂM CHỨNG CÂU TRẢ LỜI (CHỐNG BỊA SỐ LIỆU & SAI TRÍCH DẪN)

Vấn đề: các mô hình nhỏ, ít tham số thường tự điền mức phạt tiền từ "trí nhớ" khi dữ liệu
tra cứu không có con số đó. Chỉ dẫn trong system prompt không đủ để chặn — mô hình càng nhỏ
càng hay bỏ qua yêu cầu phủ định. Vì vậy cần một lớp kiểm chứng tất định chạy sau khi Agent
đã sinh câu trả lời:

1. extract/find_ungrounded_figures: mọi con số tiền phạt, tháng tước GPLX, điểm bị trừ trong
   câu trả lời phải xuất hiện trong kết quả công cụ đã tra cứu, kể cả khi mô hình quy đổi
   đơn vị ("6.000.000 VNĐ" -> "6 triệu đồng").
2. find_invalid_citations: mọi trích dẫn Điều/Khoản phải tồn tại thật, phải đã được tra cứu
   trong lượt này, và phải đúng Khoản mà dữ liệu tra cứu chốt — chặn kiểu dẫn "Khoản 3 Điều 11"
   cho hành vi mà căn cứ thật là Khoản 4.
3. all_tools_returned_no_data / is_uncertain_answer: nhận diện trường hợp hệ thống thực sự
   không có dữ liệu, để trả lời "chưa biết" thay vì suy đoán.
4. build_unknown_answer + build_search_link: khi nằm ngoài vùng dữ liệu, trả về câu trả lời
   trung thực kèm liên kết Google để người dùng tự tra cứu tiếp.
"""

import re
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote_plus

# Câu chữ cho thấy chính mô hình cũng không chắc / không có dữ liệu
_UNCERTAIN_ANSWER = re.compile(
    r'chưa có dữ liệu|không có dữ liệu|chưa tra cứu được|không tra cứu được|chưa tìm thấy'
    r'|không tìm thấy|tôi không biết|chưa đủ (?:dữ liệu|căn cứ|thông tin)|ngoài phạm vi'
    r'|không thuộc phạm vi|không nằm trong phạm vi',
    re.IGNORECASE
)

# Câu hỏi về chế tài -> ưu tiên gợi ý tra cứu Nghị định xử phạt trên Google
_PENALTY_INTENT = re.compile(
    r'phạt|xử phạt|bao nhiêu tiền|tước|trừ điểm|tạm giữ|vi phạm|lỗi|mức phạt|'
    r'vượt đèn|khẩn cấp|nồng độ cồn|uống rượu|uống bia|tốc độ|ngược chiều|lấn làn|'
    r'không đội mũ|không có bằng|quên bằng|không gương|đua xe|dừng đỗ|quay đầu|lùi xe|đi vào đường',
    re.IGNORECASE
)

# Câu hỏi về quy tắc, độ tuổi, phân hạng GPLX -> Luật 36/2024
_RULE_INTENT = re.compile(
    r'bao\s+nhiêu\s+tuổi|mấy\s+tuổi|độ\s+tuổi|điều\s+kiện|thi\s+bằng|hồ\s+sơ|thủ\s+tục|'
    r'phân\s+hạng|hạng\s+[a-z0-9]+|được\s+lái|quy\s+tắc|chương|điều\s+\d',
    re.IGNORECASE
)

# Tiền tố và hậu tố mang tính khẩu ngữ, đệm lời cần lọc sạch khỏi câu hỏi Google
_CONVERSATIONAL_PREFIXES = re.compile(
    r'^(?:vậy\s+(?:thì\s+)?|thế\s+(?:thì\s+)?|còn\s+|nhưng\s+mà\s+|nếu\s+(?:mà\s+)?|'
    r'(?:làm\s+ơn\s+)?(?:cho\s+(?:tôi|mình|em)\s+hỏi|xin\s+hỏi|hỏi)\s+|'
    r'(?:ad|admin|bạn|mọi\s+người)\s+ơi[,:\s]*)+',
    re.IGNORECASE
)

_CONVERSATIONAL_SUFFIXES = re.compile(
    r'(?:[\s,.]+(?:thì\s+sao|thế\s+nào|như\s+thế\s+nào|sao\s+ạ|nhỉ|ạ|hả|vậy\s+ạ|vậy|sao|thế|nhé|'
    r'với\s+ạ|với|được\s+không(?:\s+ạ)?|có\s+sao\s+không|có\s+bị\s+phạt\s+không|bị\s+phạt\s+thế\s+nào|[?!.]+))+$',
    re.IGNORECASE
)

_QUESTION_PATTERNS = re.compile(
    r'\b(?:thì\s+)?(?:bị\s+)?phạt\s+bao\s+nhiêu(?:\s+tiền)?\b|\bbao\s+nhiêu\s+tiền\b',
    re.IGNORECASE
)

GOOGLE_SEARCH_ENDPOINT = "https://www.google.com/search?q="
MAX_SEARCH_QUERY_CHARS = 180


def _figure_categories():
    """
    Các lớp số liệu cần đối chiếu, do Domain Pack khai báo.

    Không cache ở mức module: đổi pack (kiểm thử, hoặc phục vụ nhiều miền) phải thấy ngay bảng
    mới. Chi phí dựng lại là vài lệnh biên dịch regex, không đáng kể so với một lượt gọi mô hình.
    """
    from src.domain.registry import get_active_domain
    from src.guard_figures import build_categories

    return build_categories(get_active_domain().guard.figure_classes)


def find_ungrounded_figures(answer: str, tool_outputs: Iterable[str]) -> List[str]:
    """
    Trả về danh sách số liệu (đã định dạng) mà câu trả lời nêu ra nhưng KHÔNG có trong bất kỳ
    kết quả công cụ nào đã tra cứu — dấu hiệu mô hình lấy số từ trí nhớ.

    So khớp theo giá trị đã chuẩn hóa nên "6 triệu đồng" vẫn khớp với "6.000.000 VNĐ" trong
    dữ liệu gốc; chỉ những con số thực sự không tồn tại mới bị đánh dấu.

    Lớp số liệu nào cần kiểm là do miền khai báo (`guard.figure_classes`); cơ chế bóc số nằm
    trong `src/guard_figures.py` của engine.
    """
    if not answer:
        return []

    grounded_text = "\n".join(t for t in tool_outputs if t)
    flagged: List[str] = []
    for _name, extract, fmt, floor in _figure_categories():
        grounded = extract(grounded_text)
        claimed = {v for v in extract(answer) if v >= floor}
        flagged.extend(fmt(v) for v in sorted(claimed - grounded))
    return flagged


def all_tools_returned_no_data(tool_outputs: Iterable[str]) -> bool:
    """True khi mọi lượt tra cứu đều rơi vào nhánh 'không có dữ liệu' của công cụ"""
    outputs = [t for t in tool_outputs if t]
    if not outputs:
        return True
    from src.domain.registry import get_active_domain

    try:
        markers = get_active_domain().no_data_markers
    except Exception:
        markers = []
    if not markers:
        return False

    return all(any(marker in text for marker in markers) for text in outputs)


def is_uncertain_answer(answer: str) -> bool:
    """True khi chính câu trả lời thừa nhận chưa có dữ liệu / nằm ngoài phạm vi"""
    return bool(answer) and bool(_UNCERTAIN_ANSWER.search(answer))


# ----------------------------------------------------------------------------
# Lối thoát khi không biết: tra cứu tiếp trên Google
# ----------------------------------------------------------------------------

def clean_search_keywords(question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Làm sạch câu hỏi của người dùng thành từ khóa tìm kiếm Google chuẩn xác.
    - Loại bỏ từ đệm, từ cảm thán hội thoại (vậy, thì sao, cho em hỏi, ạ, nhỉ...).
    - Lược bỏ cấu trúc hỏi giá tiền ('phạt bao nhiêu tiền' -> 'mức phạt').
    - Xác định ý định (chế tài xử phạt hay quy tắc an toàn).
    - Thêm văn bản pháp lý tương ứng (Nghị định 168/2024/NĐ-CP hoặc Luật 36/2024/QH15).
    """
    text = (question or "").strip()
    # Xoá dấu câu thừa ở đầu/cuối
    text = re.sub(r'^[?!,.\s]+|[?!,.\s]+$', '', text)

    # Loại bỏ prefix và suffix hội thoại lặp lại
    prev = None
    while prev != text:
        prev = text
        text = _CONVERSATIONAL_PREFIXES.sub('', text).strip()
        text = _CONVERSATIONAL_SUFFIXES.sub('', text).strip()

    # Loại bỏ các cụm từ hỏi bao nhiêu tiền
    text = _QUESTION_PATTERNS.sub('', text).strip()

    cleaned = " ".join(text.split())
    if not cleaned:
        cleaned = "luật giao thông đường bộ 2024"

    # Kiểm tra ngữ cảnh lịch sử xem có đang hỏi về mức phạt không
    history_has_penalty = False
    if history:
        for msg in reversed(history[-4:]):
            content = msg.get("content", "")
            if _PENALTY_INTENT.search(content):
                history_has_penalty = True
                break

    is_penalty = bool(_PENALTY_INTENT.search(cleaned)) or history_has_penalty
    if _RULE_INTENT.search(cleaned) and not re.search(r'\b(?:mức\s+)?phạt\b|\btước\b|\btrừ\s+điểm\b', cleaned, re.IGNORECASE):
        is_penalty = False

    # Nếu hỏi về mức phạt hoặc hành vi vi phạm
    if is_penalty:
        if not re.search(r'\b(?:mức\s+)?phạt\b', cleaned, re.IGNORECASE):
            cleaned = f"mức phạt {cleaned}"
        suffix = "Nghị định 168/2024/NĐ-CP"
    else:
        suffix = "Luật Trật tự an toàn giao thông đường bộ 2024"

    query = f"{cleaned} {suffix}".strip()
    return query[:MAX_SEARCH_QUERY_CHARS]


def build_search_link(question: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, str]:
    """
    Dựng truy vấn Google sát với câu hỏi đã được làm sạch và chuẩn hóa pháp lý,
    để người dùng bấm một nút là tra cứu tiếp được trên Google một cách chuẩn xác nhất.
    """
    query = clean_search_keywords(question, history)
    return {
        "query": query,
        "url": GOOGLE_SEARCH_ENDPOINT + quote_plus(query),
        "label": "Tìm câu trả lời trên Google"
    }


def _format_source_refs(sources: Optional[List[Dict[str, Any]]]) -> str:
    """
    Gom danh sách nguồn trích dẫn thành một dòng đọc được, nhóm theo văn bản.

    `sources` do `_build_sources` dựng và chứa BA dạng khác nhau: điều luật
    (`source_type="law"`, có `article_number`), chế tài Nghị định (`"decree"`) và
    biển báo (`"sign"`). Chỉ dạng đầu có `article_number`, nên phải đọc qua
    `citation` — trường duy nhất cả ba dạng đều có — và luôn dùng `.get()`.
    """
    if not sources:
        return ""

    grouped: "OrderedDict[str, List[str]]" = OrderedDict()
    for src in sources:
        if not isinstance(src, dict):
            continue

        doc = src.get("doc_short") or src.get("doc_name") or "Văn bản"

        if src.get("source_type") == "law" and src.get("article_number") is not None:
            label = f"Điều {src['article_number']}"
        elif src.get("source_type") == "sign" and src.get("sign_code"):
            label = f"Biển {src['sign_code']}"
        else:
            # Chế tài Nghị định: citation ở dạng "Điểm a Khoản 1 Điều 6"
            label = src.get("citation") or ""
            # Citation do công cụ bóc ra thường đã kèm sẵn tên văn bản ở đầu hoặc
            # cuối. Bỏ đi để không lặp lại tên đã đứng trong ngoặc của cả nhóm.
            if " - " in label:
                label = label.split(" - ", 1)[1]
            doc_name = src.get("doc_name") or ""
            if doc_name and label.endswith(doc_name):
                label = label[: -len(doc_name)].strip(" ,-–")

        if not label:
            continue
        grouped.setdefault(doc, [])
        if label not in grouped[doc]:
            grouped[doc].append(label)

    if not grouped:
        return ""

    return "; ".join(f"{', '.join(labels)} ({doc})" for doc, labels in grouped.items())


def build_unknown_answer(question: str, sources: List[Dict[str, Any]] = None,
                         issues: List[str] = None) -> str:
    """
    Câu trả lời trung thực dùng khi hệ thống không có dữ liệu, hoặc khi câu trả lời của mô hình
    không vượt qua kiểm chứng số liệu.

    Thà nói "chưa biết" còn hơn đưa một mức phạt sai: người dùng có thể hành động dựa trên con số
    đó, và không có cách nào để họ tự phát hiện nó bị bịa.
    """
    lines = [
        "**Tôi chưa có dữ liệu đủ tin cậy để trả lời câu hỏi này.**",
        "",
        "Hệ thống chỉ trả lời dựa trên 6 văn bản quy phạm pháp luật đã được nạp sẵn. "
        "Lần tra cứu này không tìm thấy căn cứ tương ứng, nên tôi không đưa ra con số hay quy định "
        "nào để tránh cung cấp thông tin sai.",
    ]

    if issues:
        lines += [
            "",
            "Các chi tiết mà mô hình định đưa ra nhưng không đối chiếu được với dữ liệu tra cứu "
            f"(đã bị loại bỏ): {', '.join(issues)}.",
        ]

    refs = _format_source_refs(sources)
    if refs:
        lines += ["", f"Căn cứ có liên quan mà hệ thống tìm được: {refs}."]

    lines += [
        "",
        "**Bạn nên làm gì tiếp theo:** mô tả rõ hơn tình huống (loại xe, hành vi cụ thể), "
        "hoặc bấm nút tra cứu Google bên dưới để tìm trực tiếp trong Nghị định xử phạt hiện hành.",
    ]
    return "\n".join(lines)
