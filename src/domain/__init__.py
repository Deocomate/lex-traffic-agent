"""
Lớp Domain Pack: tách phần "biết về miền" ra khỏi engine.

Engine trong `src/` không chứa tri thức về giao thông đường bộ. Mọi thứ đặc thù — kho tài liệu,
persona, từ điển lĩnh vực, quy tắc kiểm chứng, bộ công cụ — nằm trong `domains/<id>/`.

Miền đang hoạt động chọn bằng biến môi trường `ACTIVE_DOMAIN` (mặc định `vietnam_traffic`).
"""

from src.domain.pack import DomainPack, DomainPackError, load_domain_pack
from src.domain.registry import active_domain_id, get_active_domain, set_active_domain
from src.domain.schema import DomainPackSpec

__all__ = [
    "DomainPack",
    "DomainPackError",
    "DomainPackSpec",
    "load_domain_pack",
    "active_domain_id",
    "get_active_domain",
    "set_active_domain",
]
