"""
Nhận diện tín hiệu tất định từ câu hỏi (Deterministic Query Signals).

Chỉ còn đúng một chỗ dùng: dựng khoá cache ngữ nghĩa trong `src/graph/turn.py`. Khoá cache
BẮT BUỘC phải tất định — bộ định tuyến LLM cũ không tất định (cùng một câu hỏi cho ra
`vehicles` khác nhau giữa các lượt chạy, nên cache không bao giờ trúng), còn regex thì luôn
cho cùng một kết quả.

Việc CHỌN công cụ tra cứu nào không còn thuộc về đây: Agent tự quyết trong vòng ReAct.

Các biểu thức dưới đây là tri thức của miền giao thông đường bộ Việt Nam; Phase 3 sẽ chuyển
chúng sang phần `lexicon` của Domain Pack và để lõi chỉ giữ bộ so khớp tổng quát.
"""

import re
from typing import List, Tuple

# Biển báo & vạch kẻ đường (QCVN 41:2019)
_SIGN_PATTERN = re.compile(
    r'\b(biển\s*(?:báo|cấm|hiệu\s*lệnh|chỉ\s*dẫn|nguy\s*hiểm|phụ)?|[pwiros]\.\d+[a-z]?|vạch\s*(?:kẻ)?(?:đường)?)\b',
    re.IGNORECASE,
)

# Tốc độ & khoảng cách an toàn (Thông tư 31/2019)
_SPEED_PATTERN = re.compile(
    r'\b(tốc\s*độ|km/h|chạy\s*bao\s*nhiêu|khoảng\s*cách\s*an\s*toàn|cự\s*ly)\b',
    re.IGNORECASE,
)

# Mức phạt, trừ điểm, tước bằng (Nghị định 168/2024)
_PENALTY_PATTERN = re.compile(
    r'\b(phạt|tiền\s*phạt|mức\s*phạt|bị\s*phạt|nhiêu\s*tiền|tước|trừ\s*điểm|gplx|bằng\s*lái|'
    r'nồng\s*độ\s*cồn|rượu|bia|quá\s*tải|vượt\s*đèn|đèn\s*đỏ|lấn\s*làn|đi\s*ngược\s*chiều|'
    r'nghị\s*định\s*168|nghị\s*định|chế\s*tài|giam\s*xe|tạm\s*giữ)\b',
    re.IGNORECASE,
)

# Điều luật, quy tắc, thẩm quyền
_LAW_PATTERN = re.compile(
    r'\b(điều\s*\d+|luật\s*36|luật\s*35|luật|nguyên\s*tắc|hành\s*vi\s*bị\s*cấm|quy\s*tắc|'
    r'độ\s*tuổi|hạng\s*bằng|hạng\s*gplx|a1|a|b1|b|c1|c|d1|d2|d|csgt|cảnh\s*sát\s*giao\s*thông|'
    r'dừng\s*xe|tuần\s*tra|vneid|giấy\s*tờ|đăng\s*ký|đăng\s*kiểm)\b',
    re.IGNORECASE,
)

# Nhóm phương tiện. Tách bạch đúng cái cần tách: "ô tô vượt đèn đỏ" và "xe máy vượt đèn đỏ"
# phải ra hai khoá cache khác nhau, vì trả mức phạt của loại xe này cho loại xe kia là cái
# bẫy nguy hiểm nhất của hệ thống.
_VEHICLE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("o_to", re.compile(r'\b(ô\s*tô|xe\s*con|xe\s*tải|xe\s*khách|xe\s*hơi|container|xe\s*ben)\b')),
    ("xe_may", re.compile(r'\b(xe\s*máy|mô\s*tô|xe\s*gắn\s*máy|xe\s*điện|xe\s*máy\s*điện)\b')),
    ("xe_dap", re.compile(r'\b(xe\s*đạp|xe\s*thô\s*sơ)\b')),
    ("khac", re.compile(r'\b(máy\s*kéo|xe\s*chuyên\s*dùng)\b')),
]


def detect_by_regex(query: str) -> Tuple[List[str], List[str]]:
    """
    Trả về `(intents, vehicles)` cho một câu hỏi. Tất định và không bao giờ ném ngoại lệ.
    """
    if not query:
        return ["law"], []

    q = query.lower()
    intents = set()

    if _SIGN_PATTERN.search(q):
        intents.add("sign")
    if _SPEED_PATTERN.search(q):
        intents.add("speed")
    if _PENALTY_PATTERN.search(q):
        intents.add("penalty")
    if _LAW_PATTERN.search(q) or not intents:
        intents.add("law")

    vehicles = {name for name, pattern in _VEHICLE_PATTERNS if pattern.search(q)}

    return list(intents), list(vehicles)
