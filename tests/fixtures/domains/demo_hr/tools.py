"""Công cụ giả lập của pack kiểm thử: trả dữ liệu cố định, không đụng tới kho giao thông."""

_FAKE_CORPUS = {
    "thai sản": (
        "=== QUY ĐỊNH VỀ NGHỈ THAI SẢN (QC-01, Điều 12) ===\n"
        "Lao động nữ được nghỉ thai sản 180 ngày.\n"
        "Trợ cấp một lần: 5.000.000 đồng."
    ),
    "lương": (
        "=== QUY CHẾ LƯƠNG (QC-02, Điều 4) ===\n"
        "Phụ cấp ăn trưa: 730.000 đồng mỗi tháng."
    ),
}


def policy_search(question: str = "", **_: object) -> str:
    lowered = (question or "").lower()
    for keyword, content in _FAKE_CORPUS.items():
        if keyword in lowered:
            return content
    return "=== KHÔNG TÌM THẤY QUY ĐỊNH: " + question + " ==="
