"""
Nhận diện tín hiệu tất định từ câu hỏi (Deterministic Query Signals).

Chỉ còn đúng một chỗ dùng: dựng khoá cache ngữ nghĩa trong `src/graph/turn.py`. Khoá cache BẮT
BUỘC phải tất định — bộ định tuyến LLM cũ không tất định (cùng một câu hỏi cho ra `vehicles`
khác nhau giữa các lượt chạy, nên cache không bao giờ trúng), còn regex thì luôn cho cùng kết quả.

Việc CHỌN công cụ tra cứu nào không thuộc về đây: Agent tự quyết trong vòng ReAct.

Các biểu thức nhận diện do Domain Pack khai báo (`lexicon.intent_patterns` và
`lexicon.entity_patterns`), nên module này không biết gì về giao thông đường bộ.
"""

from typing import List, Tuple


def _domain():
    from src.domain.registry import get_active_domain

    return get_active_domain()


def detect_signals(query: str) -> Tuple[List[str], List[str]]:
    """
    Trả về `(intents, entities)` cho một câu hỏi. Tất định và không bao giờ ném ngoại lệ.

    `intents` là loại thông tin câu hỏi nhắm tới; `entities` là nhóm đối tượng liên quan (miền
    giao thông: loại phương tiện). Cả hai đi vào khoá cache, nên việc tách bạch chúng chính là
    thứ ngăn hệ thống trả mức phạt của ô tô cho câu hỏi về xe máy.
    """
    if not query:
        return _default_intents(), []

    lowered = query.lower()

    try:
        domain = _domain()
        intent_patterns = domain.intent_patterns
        entity_patterns = domain.entity_patterns
        default_intent = domain.default_intent
    except Exception:
        return _default_intents(), []

    intents = {name for name, pattern in intent_patterns.items() if pattern.search(lowered)}

    # Ý định mặc định luôn được thêm khi nó tự khớp, hoặc khi không ý định nào khớp — để mọi
    # câu hỏi đều có ít nhất một tín hiệu và khoá cache không bao giờ rỗng.
    if default_intent and (default_intent in intents or not intents):
        intents.add(default_intent)
    if not intents:
        intents = set(_default_intents())

    entities = {name for name, pattern in entity_patterns.items() if pattern.search(lowered)}

    return sorted(intents), sorted(entities)


def _default_intents() -> List[str]:
    try:
        return [_domain().default_intent or "general"]
    except Exception:
        return ["general"]


# Tên cũ, giữ cho mã đã dùng.
detect_by_regex = detect_signals
