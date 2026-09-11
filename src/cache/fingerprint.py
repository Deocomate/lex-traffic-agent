"""
Vân tay chỉ mục truy xuất (index fingerprint).

Cache câu trả lời chỉ đúng chừng nào dữ liệu sinh ra nó còn nguyên. Dựng lại chỉ mục hay đổi
mô hình nhúng làm mọi câu trả lời đã lưu trở thành rác — nhưng không ai nhớ xoá cache bằng tay.
Vân tay này biến việc đó thành tự động: fingerprint đổi thì mọi khoá cache cũ không còn khớp,
toàn bộ cache miss mà không cần một lệnh dọn nào.
"""

import hashlib
import os
from typing import List, Optional

# Ba tệp chỉ mục quyết định kết quả truy xuất, cộng tên mô hình nhúng.
INDEX_FILES = (
    os.path.join("data", "processed", "semantic_index.npz"),
    os.path.join("data", "processed", "semantic_chunks.json"),
    os.path.join("data", "processed", "bm25_index.pkl"),
)


def _default_base_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def compute_index_fingerprint(
    base_dir: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> str:
    """
    Tính sha256 từ (đường dẫn + mtime + kích thước) của từng tệp chỉ mục, cộng tên mô hình nhúng.

    Tệp thiếu được ghi nhận rõ ràng là "missing" thay vì bị bỏ qua: chỉ mục thiếu rồi được dựng
    lại phải cho vân tay khác, nếu không cache cũ sẽ sống sót qua đúng lần thay đổi lớn nhất.
    """
    base = base_dir or _default_base_dir()
    model = embedding_model if embedding_model is not None else os.getenv("EMBEDDING_MODEL", "")

    parts: List[str] = [f"embedding_model={model}"]
    for rel_path in INDEX_FILES:
        abs_path = os.path.join(base, rel_path)
        try:
            st = os.stat(abs_path)
            parts.append(f"{rel_path}:{int(st.st_mtime_ns)}:{st.st_size}")
        except OSError:
            parts.append(f"{rel_path}:missing")

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


_cached_fingerprint: Optional[str] = None


def get_index_fingerprint(base_dir: Optional[str] = None) -> str:
    """
    Vân tay dùng chung cho cả tiến trình.

    Tính một lần rồi giữ lại: chỉ mục không đổi giữa chừng khi server đang chạy, còn `os.stat`
    ba tệp cho mỗi câu hỏi là chi phí đĩa không cần thiết. Dựng lại chỉ mục đòi hỏi khởi động
    lại tiến trình — đúng quy trình vốn có, vì chỉ mục được nạp vào RAM lúc khởi động.
    """
    global _cached_fingerprint
    if _cached_fingerprint is None:
        _cached_fingerprint = compute_index_fingerprint(base_dir)
    return _cached_fingerprint


def reset_fingerprint_cache() -> None:
    """Xoá vân tay đã ghi nhớ (dùng trong test và sau khi dựng lại chỉ mục trong cùng tiến trình)."""
    global _cached_fingerprint
    _cached_fingerprint = None
