"""
Hàm thực thi công cụ của miền giao thông đường bộ Việt Nam.

`domain.yaml` trỏ tới từng hàm ở đây qua trường `handler` ('module:hàm'). Engine chỉ nạp và
gọi theo tên, không biết công cụ làm gì — nhờ vậy bộ công cụ hoàn toàn do miền quyết định.

Mỗi hàm nhận tham số đúng như JSON Schema đã khai báo và trả về MỘT CHUỖI: chính là nội dung
sẽ đi vào `ToolMessage` cho mô hình đọc. Engine tự lo phần dựng `Evidence`, phát sự kiện SSE
và ghi trace.
"""

from typing import Optional

_tools = None


def _traffic_tools():
    """Kho dữ liệu luật nạp sẵn trong RAM (singleton)."""
    global _tools
    if _tools is None:
        from domains.vietnam_traffic.lib.law_search_tools import TrafficLawTools

        _tools = TrafficLawTools()
    return _tools


def reset() -> None:
    """Xoá singleton. Dùng cho kiểm thử khi đổi Domain Pack."""
    global _tools
    _tools = None


def penalty_lookup(violation_keyword: str = "", **_: object) -> str:
    """Tra mức phạt tiền, trừ điểm GPLX và xử phạt bổ sung trên Nghị định 168/2024/NĐ-CP."""
    return _traffic_tools().penalty_lookup(violation_keyword)


def traffic_sign_lookup(sign_code_or_name: str = "", **_: object) -> str:
    """Tra biển báo giao thông và vạch kẻ đường theo QCVN 41:2019/BGTVT, kèm ảnh minh hoạ."""
    return _traffic_tools().traffic_sign_lookup(sign_code_or_name)


def speed_limit_lookup(query: str = "", **_: object) -> str:
    """Tra tốc độ tối đa cho phép và khoảng cách an toàn theo Thông tư 31/2019/TT-BGTVT."""
    return _traffic_tools().speed_limit_lookup(query)


def keyword_search(keywords: str = "", **_: object) -> str:
    """Tìm chính xác từ khoá, số hiệu bằng lái hoặc con số trong các Điều luật."""
    return _traffic_tools().keyword_search(keywords)


def semantic_search(question: str = "", doc_scope: str = "all", **_: object) -> str:
    """Tìm kiếm ngữ nghĩa trên toàn bộ kho văn bản pháp luật giao thông."""
    return _traffic_tools().semantic_search(question, doc_scope=doc_scope)


def get_article(article_number: int = 0, doc_id: Optional[str] = None, **_: object) -> str:
    """Đọc toàn văn một Điều luật cụ thể."""
    return _traffic_tools().get_article(
        int(article_number), doc_id=doc_id or "01_luat_36_2024_qh15"
    )


def list_chapters(**_: object) -> str:
    """Xem danh mục Chương của Luật 36/2024/QH15."""
    return _traffic_tools().list_chapters()
