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

from src.tools.tool_contract import (
    LAW_NAME,
    NO_DATA_HEADERS,
    PENALTY_DECREE_NAME,
    ROAD_LAW_MARKERS,
    ROAD_LAW_NAME,
)

# Ngưỡng sàn của một khoản tiền phạt thực tế (VNĐ). Dưới mức này gần như chắc chắn là
# con số khác (mg cồn, cc, km/h...) nên không tính vào nhóm "tiền phạt".
MONEY_FLOOR = 50_000

# 6.000.000 / 1.000 — dạng số có dấu phân nhóm hàng nghìn của tiếng Việt
_GROUPED_NUMBER = re.compile(r'\d{1,3}(?:\.\d{3})+')

# 6 triệu, 6,5 triệu, 800 nghìn, 2tr — mô hình hay viết tắt thay vì chép nguyên văn
_SCALED_NUMBER = re.compile(r'(\d+(?:[.,]\d+)?)\s*(triệu|nghìn|ngàn|tr)\b', re.IGNORECASE)
_SCALE_FACTORS = {"triệu": 1_000_000, "tr": 1_000_000, "nghìn": 1_000, "ngàn": 1_000}

# 6000000 — số viết liền không dấu phân nhóm
_PLAIN_NUMBER = re.compile(r'(?<![\d.,])(\d{6,10})(?![\d.,])')

# Thời hạn tước GPLX / tạm giữ phương tiện: chỉ tính con số nằm trong câu có ngữ cảnh chế tài
_SANCTION_CONTEXT = re.compile(r'tước|tạm giữ|thu hồi|giấy phép lái xe|gplx|bằng lái', re.IGNORECASE)
_MONTHS = re.compile(r'(\d{1,3})\s*tháng', re.IGNORECASE)
# Khoảng thời hạn viết tắt "10 – 12 tháng": số đầu không đi kèm chữ 'tháng' nên phải bắt riêng
_MONTH_RANGE = re.compile(r'(\d{1,3})\s*(?:[-–—]|đến|tới)\s*\d{1,3}\s*tháng', re.IGNORECASE)

# Trừ điểm GPLX. Bắt cả "trừ 2 điểm", "trừ hết 12 điểm" lẫn cách viết đầy đủ của Nghị định
# "bị trừ điểm giấy phép lái xe 04 điểm" và nhãn kết quả "Trừ điểm giấy phép lái xe: 4 điểm".
_DEDUCTED_POINTS = re.compile(r'trừ[^.\n]{0,45}?(\d{1,2})\s*điểm', re.IGNORECASE)

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


# ----------------------------------------------------------------------------
# Trích xuất và chuẩn hóa số liệu
# ----------------------------------------------------------------------------

def _money_values(text: str) -> Set[int]:
    """Mọi khoản tiền trong văn bản, quy về số nguyên VNĐ để so khớp bất kể cách viết"""
    values: Set[int] = set()
    for raw in _GROUPED_NUMBER.findall(text):
        values.add(int(raw.replace(".", "")))
    for raw, unit in _SCALED_NUMBER.findall(text):
        try:
            amount = float(raw.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        values.add(int(amount * _SCALE_FACTORS[unit.lower()]))
    for raw in _PLAIN_NUMBER.findall(text):
        values.add(int(raw))
    return values


def _sanction_months(text: str) -> Set[int]:
    """
    Số tháng tước GPLX / tạm giữ phương tiện, bỏ qua chữ 'tháng' ở ngữ cảnh khác.

    Mô hình hay trình bày chế tài dưới dạng bảng Markdown, khi đó cụm 'Tước GPLX' chỉ nằm ở
    dòng tiêu đề còn số tháng nằm ở các dòng sau — nên ngữ cảnh được giữ cho cả khối bảng.
    """
    values: Set[int] = set()
    table_context = False
    for line in text.splitlines():
        is_table_row = line.strip().startswith("|")
        if not is_table_row:
            table_context = False
        if _SANCTION_CONTEXT.search(line):
            table_context = is_table_row
        elif not (is_table_row and table_context):
            continue
        values.update(int(n) for n in _MONTHS.findall(line))
        values.update(int(n) for n in _MONTH_RANGE.findall(line))
    return values


def _deducted_points(text: str) -> Set[int]:
    """Số điểm GPLX bị trừ"""
    return {int(n) for n in _DEDUCTED_POINTS.findall(text)}


def _format_money(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " đồng"


# Mỗi nhóm số liệu: (hàm trích xuất, hàm định dạng để hiển thị, ngưỡng bỏ qua khi kiểm câu trả lời)
_FIGURE_CATEGORIES = (
    ("money", _money_values, _format_money, MONEY_FLOOR),
    ("months", _sanction_months, lambda v: f"{v} tháng tước GPLX", 0),
    ("points", _deducted_points, lambda v: f"{v} điểm bị trừ", 0),
)


def find_ungrounded_figures(answer: str, tool_outputs: Iterable[str]) -> List[str]:
    """
    Trả về danh sách số liệu (đã định dạng) mà câu trả lời nêu ra nhưng KHÔNG có trong bất kỳ
    kết quả công cụ nào đã tra cứu — dấu hiệu mô hình lấy số từ trí nhớ.

    So khớp theo giá trị đã chuẩn hóa nên "6 triệu đồng" vẫn khớp với "6.000.000 VNĐ" trong
    dữ liệu gốc; chỉ những con số thực sự không tồn tại mới bị đánh dấu.
    """
    if not answer:
        return []

    grounded_text = "\n".join(t for t in tool_outputs if t)
    flagged: List[str] = []
    for _name, extract, fmt, floor in _FIGURE_CATEGORIES:
        grounded = extract(grounded_text)
        claimed = {v for v in extract(answer) if v >= floor}
        flagged.extend(fmt(v) for v in sorted(claimed - grounded))
    return flagged


# ----------------------------------------------------------------------------
# Kiểm chứng trích dẫn Điều / Khoản
# ----------------------------------------------------------------------------

# "Điều 11", "Khoản 4 Điều 11", "Điều 11 Khoản 4" — mô hình dùng cả ba cách viết
_ARTICLE_REF = re.compile(r'Điều\s+(\d{1,2})\b', re.IGNORECASE)
_CLAUSE_THEN_ARTICLE = re.compile(r'Khoản\s+(\d{1,2})[^.\n]{0,20}?Điều\s+(\d{1,2})\b', re.IGNORECASE)
_ARTICLE_THEN_CLAUSE = re.compile(r'Điều\s+(\d{1,2})\s*,?\s*Khoản\s+(\d{1,2})\b', re.IGNORECASE)

# Trích dẫn trỏ tới Nghị định xử phạt: "Điểm c Khoản 7 Điều 7 Nghị định 168/2024/NĐ-CP"
_DECREE_CITATION = re.compile(
    r'(?:Điểm\s+([a-zđ]{1,2})\s+)?(?:Khoản\s+(\d{1,2})\s+)?Điều\s+(\d{1,2})\s*'
    r'(?:của\s+)?(?:Nghị\s*định|NĐ\s*[-/ ]?\s*CP|NĐ\s*\d)',
    re.IGNORECASE
)

# Sau một tham chiếu, nếu thấy tên Nghị định thì đó là Điều của Nghị định, không phải của Luật 36/2024.
# Phải nhận cả cách viết tắt "NĐ 168/2024" mà mô hình hay dùng, nếu không một trích dẫn Nghị định
# hợp lệ sẽ bị đem đối chiếu nhầm với cấu trúc của Luật.
_DECREE_NEARBY = re.compile(r'Nghị\s*định|NĐ\s*[-/ ]?\s*CP|NĐ\s*\d{1,3}\s*/', re.IGNORECASE)
_CIRCULAR_NEARBY = re.compile(r'Thông\s*tư|TT\s*[-/ ]?\s*(?:BGTVT|BCA)|\bTT\s*\d{1,2}\b|QCVN|Quy\s*chuẩn', re.IGNORECASE)
_DECREE_LOOKAHEAD_CHARS = 40

# Tên Luật 36 để phân biệt với Luật 35 khi cả hai cùng xuất hiện quanh một tham chiếu
_MAIN_LAW_NEARBY = re.compile(r'Luật\s*36|36/2024|Trật tự, an toàn giao thông', re.IGNORECASE)
_LAW_LOOKBEHIND_CHARS = 30


def _is_road_law_ref(text: str, start: int, end: int) -> bool:
    """
    Tham chiếu này thuộc Luật Đường bộ 2024 hay không.

    Phải xét cả hai phía: câu trả lời thường viết "Điều 80 Luật 35/2024" (tên đứng sau) còn
    kết quả tra cứu lại in "[Luật 35/2024/QH15] Điều 80" (tên đứng trước). Chỉ nhìn một phía
    sẽ khiến một trích dẫn hợp lệ bị báo là chưa tra cứu.
    """
    after = text[end:end + _DECREE_LOOKAHEAD_CHARS]
    # Tên Luật 36 đứng ngay sau thì đã rõ, không cần đoán theo ngữ cảnh phía trước
    if _MAIN_LAW_NEARBY.search(after):
        return False
    context = text[max(0, start - _LAW_LOOKBEHIND_CHARS):start] + " " + after
    return any(marker.lower() in context.lower() for marker in ROAD_LAW_MARKERS)


def _article_refs(text: str, road_law: bool = False) -> Set[int]:
    """
    Các 'Điều N' được nêu trong văn bản, đã loại tham chiếu tới Điều của Nghị định và Thông tư/QCVN.

    `road_law=False` trả về tham chiếu Luật 36/2024, `road_law=True` trả về tham chiếu
    Luật 35/2024 — phân biệt bằng tên văn bản viết ngay sau số Điều, vì hai luật cùng
    đánh số Điều từ 1 nên nhầm lẫn sẽ báo sai hàng loạt.
    """
    found: Set[int] = set()
    text = text or ""
    for m in _ARTICLE_REF.finditer(text):
        tail = text[m.end():m.end() + _DECREE_LOOKAHEAD_CHARS]
        head = text[max(0, m.start() - _LAW_LOOKBEHIND_CHARS):m.start()]
        if _DECREE_NEARBY.search(tail) or _DECREE_NEARBY.search(head):
            continue
        if _CIRCULAR_NEARBY.search(tail) or _CIRCULAR_NEARBY.search(head):
            continue
        if _is_road_law_ref(text, m.start(), m.end()) != road_law:
            continue
        found.add(int(m.group(1)))
    return found


def _decree_refs(text: str) -> Set[Tuple[int, Optional[int], Optional[str]]]:
    """
    Các trích dẫn trỏ tới Nghị định xử phạt, dạng (Điều, Khoản|None, Điểm|None).

    Nhận cả cách viết đầy đủ "Điểm c Khoản 7 Điều 7 Nghị định 168/2024/NĐ-CP" lẫn cách viết
    rút gọn "Điều 7 NĐ 168/2024" mà mô hình hay dùng.
    """
    refs: Set[Tuple[int, Optional[int], Optional[str]]] = set()
    for m in _DECREE_CITATION.finditer(text or ""):
        point, clause, article = m.group(1), m.group(2), m.group(3)
        refs.add((int(article), int(clause) if clause else None, point.lower() if point else None))
    return refs


def _clause_refs(text: str, road_law: bool = False) -> Set[Tuple[int, int]]:
    """
    Các cặp (Điều, Khoản) trỏ tới Luật 36/2024/QH15.

    Bỏ qua cặp nằm trong một trích dẫn Nghị định hoặc Thông tư/QCVN.
    """
    text = text or ""
    pairs: Set[Tuple[int, int]] = set()
    for pattern, order in ((_CLAUSE_THEN_ARTICLE, "ca"), (_ARTICLE_THEN_CLAUSE, "ac")):
        for m in pattern.finditer(text):
            tail = text[m.end():m.end() + _DECREE_LOOKAHEAD_CHARS]
            head = text[max(0, m.start() - _LAW_LOOKBEHIND_CHARS):m.start()]
            if _DECREE_NEARBY.search(tail) or _DECREE_NEARBY.search(head):
                continue
            if _CIRCULAR_NEARBY.search(tail) or _CIRCULAR_NEARBY.search(head):
                continue
            if _is_road_law_ref(text, m.start(), m.end()) != road_law:
                continue
            first, second = m.group(1), m.group(2)
            clause, article = (first, second) if order == "ca" else (second, first)
            pairs.add((int(article), int(clause)))
    return pairs


def find_invalid_citations(answer: str, tool_outputs: Iterable[str],
                           articles_by_num: Dict[int, Any],
                           road_law_articles: Optional[Dict[int, Any]] = None) -> List[str]:
    """
    Kiểm chứng phần căn cứ pháp lý — lớp phòng vệ song song với kiểm chứng số liệu.

    Hai văn bản được kiểm theo hai cách khác nhau vì bản chất dữ liệu khác nhau:

    a) Trích dẫn Luật 36/2024/QH15 (hệ thống có toàn văn 89 Điều): Điều phải tồn tại, phải đã
       được tra cứu trong lượt này, và Khoản được dẫn phải có thật trong Điều đó.
    b) Trích dẫn Nghị định 168/2024/NĐ-CP (nguồn của mọi con số tiền phạt): cặp Điểm/Khoản/Điều
       phải xuất hiện đúng trong kết quả tra cứu. Đây là lớp chặn trực tiếp việc mô hình gán một
       mức phạt cho một điều khoản mà nó tự nghĩ ra.
    """
    if not answer:
        return []

    grounded_text = "\n".join(t for t in tool_outputs if t)
    grounded_articles = _article_refs(grounded_text)
    grounded_decree = _decree_refs(grounded_text)
    problems: List[str] = []

    # Nhắc lại một trích dẫn Nghị định ở dạng rút gọn ("...theo Khoản 9 Điều 7" sau khi đã ghi đủ
    # tên Nghị định ở câu trước) là cách viết bình thường. Không nhận ra thì các lần nhắc sau bị
    # đem đối chiếu với cấu trúc của Luật và câu trả lời đúng bị huỷ oan.
    answer_cites_decree = bool(_DECREE_NEARBY.search(answer))
    decree_articles = {a for a, _c, _p in grounded_decree}
    decree_pairs = {(a, c) for a, c, _p in grounded_decree if c is not None}

    for article in sorted(_article_refs(answer)):
        if answer_cites_decree and article in decree_articles:
            continue
        if article not in articles_by_num:
            problems.append(f"Điều {article} (không tồn tại trong {LAW_NAME})")
        elif article not in grounded_articles:
            problems.append(f"Điều {article} (hệ thống chưa tra cứu điều này)")

    for article, clause in sorted(_clause_refs(answer)):
        if answer_cites_decree and (article, clause) in decree_pairs:
            continue
        if article in articles_by_num and not _clause_exists(articles_by_num[article], clause):
            problems.append(f"Khoản {clause} Điều {article} ({LAW_NAME} không có khoản này)")

    # Luật Đường bộ chỉ được kiểm khi corpus của nó đã được nạp; thiếu dữ liệu thì bỏ qua
    # thay vì báo sai một trích dẫn hợp lệ.
    if road_law_articles:
        grounded_road = _article_refs(grounded_text, road_law=True)
        for article in sorted(_article_refs(answer, road_law=True)):
            if article not in road_law_articles:
                problems.append(f"Điều {article} (không tồn tại trong {ROAD_LAW_NAME})")
            elif article not in grounded_road:
                problems.append(f"Điều {article} {ROAD_LAW_NAME} (hệ thống chưa tra cứu điều này)")
        for article, clause in sorted(_clause_refs(answer, road_law=True)):
            if article in road_law_articles and not _clause_exists(road_law_articles[article], clause):
                problems.append(f"Khoản {clause} Điều {article} ({ROAD_LAW_NAME} không có khoản này)")

    for article, clause, point in sorted(_decree_refs(answer), key=lambda r: (r[0], r[1] or 0, r[2] or "")):
        # Cho phép trích dẫn ở mức khái quát hơn dữ liệu tra cứu (chỉ nêu Điều, hoặc Điều + Khoản),
        # nhưng không cho phép nêu một Điểm/Khoản chưa từng xuất hiện trong kết quả tra cứu.
        matched = any(
            article == a
            and (clause is None or clause == c)
            and (point is None or point == p)
            for a, c, p in grounded_decree
        )
        if not matched:
            label = " ".join(filter(None, [
                f"Điểm {point}" if point else "",
                f"Khoản {clause}" if clause else "",
                f"Điều {article}",
                PENALTY_DECREE_NAME
            ]))
            problems.append(f"{label} (không có trong dữ liệu tra cứu)")

    # Lỗi kinh điển: nêu mức tiền phạt rồi ghi căn cứ là một Điều của Luật, trong khi Luật
    # không hề quy định số tiền. Câu trả lời đúng luôn phải dẫn Nghị định xử phạt.
    claims_money = any(v >= MONEY_FLOOR for v in _money_values(answer))
    if claims_money and _article_refs(answer) and not _DECREE_NEARBY.search(answer):
        problems.append(
            f"mức tiền phạt đang được dẫn theo {LAW_NAME} "
            f"(Luật không quy định số tiền — căn cứ phải là {PENALTY_DECREE_NAME})"
        )

    return problems



def _clause_exists(article_doc: Any, clause: int) -> bool:
    """Điều luật có Khoản mang số này không (khoản bắt đầu bằng 'N.' ở đầu dòng)"""
    body = (article_doc or {}).get("page_content", "")
    return bool(re.search(rf'^\s*{clause}\.\s', body, re.MULTILINE))


# ----------------------------------------------------------------------------
# Nhận diện vùng ngoài hiểu biết
# ----------------------------------------------------------------------------

def all_tools_returned_no_data(tool_outputs: Iterable[str]) -> bool:
    """True khi mọi lượt tra cứu đều rơi vào nhánh 'không có dữ liệu' của công cụ"""
    outputs = [t for t in tool_outputs if t]
    if not outputs:
        return True
    return all(any(marker in text for marker in NO_DATA_HEADERS) for text in outputs)


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
