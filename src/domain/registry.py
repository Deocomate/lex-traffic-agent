"""
Sổ đăng ký Domain Pack đang hoạt động.

Engine gọi `get_active_domain()` ở mọi nơi cần biết về miền. Pack được chọn bằng biến môi
trường `ACTIVE_DOMAIN` (mặc định `vietnam_traffic`) và nạp một lần duy nhất cho cả tiến trình.

`set_active_domain()` tồn tại cho kiểm thử và cho kịch bản phục vụ nhiều miền trong cùng một
tiến trình: nó nạp pack khác và xoá mọi cache dẫn xuất.
"""

import os
import threading
from typing import Optional

from src.domain.pack import DEFAULT_DOMAIN, DomainPack, load_domain_pack

_active: Optional[DomainPack] = None
_lock = threading.Lock()


def active_domain_id() -> str:
    """Mã miền đang được yêu cầu, theo biến môi trường."""
    return (os.getenv("ACTIVE_DOMAIN") or "").strip() or DEFAULT_DOMAIN


def get_active_domain() -> DomainPack:
    """Domain Pack đang hoạt động (singleton, nạp lười)."""
    global _active
    if _active is None:
        with _lock:
            if _active is None:
                _active = load_domain_pack(active_domain_id())
    return _active


def set_active_domain(domain: DomainPack | str | None) -> Optional[DomainPack]:
    """
    Đổi pack đang hoạt động. Nhận sẵn một `DomainPack`, một mã miền, hoặc None để nạp lại.

    Mọi cache dẫn xuất từ pack phải được xoá theo, nếu không miền mới sẽ chạy với bảng phân
    giải tài liệu và từ điển của miền cũ.
    """
    global _active
    with _lock:
        if domain is None:
            _active = None
        elif isinstance(domain, str):
            _active = load_domain_pack(domain)
        else:
            _active = domain
        _invalidate_derived_caches()
    return _active


def _invalidate_derived_caches() -> None:
    """
    Xoá mọi singleton mang dữ liệu của miền cũ.

    Bỏ sót một cái ở đây là lỗi âm thầm và khó lần ra: miền mới chạy với từ điển, chỉ mục hoặc
    mốc tham chiếu phạm vi của miền cũ, cho ra kết quả sai mà không có dấu hiệu lỗi nào.

    Nhập trong hàm để tránh phụ thuộc vòng lúc khởi động.
    """
    try:
        from src.retrieval import vi_text

        vi_text.reset_lexicon_cache()
    except Exception:
        pass

    # Chỉ mục truy xuất gắn với kho tài liệu của miền -> phải dựng lại.
    for module_name, attr in (
        ("src.retrieval.hybrid", "_shared_hybrid_search"),
        ("src.retrieval.dense", "_shared_dense_index"),
        ("src.retrieval.scope", "_shared_reference"),
    ):
        try:
            import importlib

            module = importlib.import_module(module_name)
            if hasattr(module, attr):
                setattr(module, attr, None)
        except Exception:
            pass
