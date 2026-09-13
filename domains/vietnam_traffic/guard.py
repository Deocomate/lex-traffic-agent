"""
Kiểm chứng trích dẫn pháp lý của miền giao thông.

Engine kiểm được SỐ LIỆU cho mọi miền (`src/guard_figures.py` + khai báo `figure_classes`),
nhưng kiểm TRÍCH DẪN thì không: "Điểm d Khoản 5 Điều 6 Nghị định 168/2024" là cách đánh số của
văn bản quy phạm pháp luật Việt Nam, và việc xác minh nó đòi phải đối chiếu với chính cây điều
khoản của kho văn bản. Miền khác có cách đánh số căn cứ hoàn toàn khác.

Vì vậy phần này do miền cung cấp, engine chỉ gọi qua khai báo `guard.citation_validator`.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from domains.vietnam_traffic.lib.tool_contract import (
    ROAD_LAW_MARKERS,
    ROAD_LAW_NAME,
)


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


def validate_citations(answer: str, verified_sources: Iterable[str]) -> List[str]:
    """
    Điểm vào mà engine gọi (khai báo ở `guard.citation_validator` trong guard.yaml).

    Đối chiếu mọi trích dẫn Điều/Khoản/Điểm trong câu trả lời với dữ liệu đã tra cứu của lượt này.
    """
    from domains.vietnam_traffic.tools import _traffic_tools

    tools = _traffic_tools()
    return find_invalid_citations(
        answer,
        verified_sources,
        tools.articles_by_num,
        tools.road_law_articles,
    )
