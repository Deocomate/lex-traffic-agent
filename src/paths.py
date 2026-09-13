"""
Định vị thư mục gốc dự án — một nguồn sự thật duy nhất.

Trước đây mỗi module tự tính bằng cách đi ngược `os.path.dirname` đúng số cấp tương ứng với vị
trí của chính nó. Cách đó âm thầm sai ngay khi một tệp được chuyển sang thư mục khác độ sâu:
khi các module của miền giao thông dời từ `src/tools/` sang `domains/vietnam_traffic/lib/`,
`base_dir` trỏ vào `domains/`, mọi đường dẫn dữ liệu hỏng, và triệu chứng chỉ là "nạp được 0
điều luật" chứ không phải một lỗi rõ ràng.

`project_root()` đi lên từ tệp này cho tới khi gặp dấu hiệu của gốc dự án, nên đúng bất kể
module gọi nó nằm ở đâu.
"""

import os
from functools import lru_cache

# Dấu hiệu nhận biết thư mục gốc, xếp theo độ tin cậy giảm dần.
_ROOT_MARKERS = ("requirements.txt", "main.py", ".git")


@lru_cache(maxsize=1)
def project_root() -> str:
    """Thư mục gốc của dự án."""
    current = os.path.dirname(os.path.abspath(__file__))
    while True:
        if any(os.path.exists(os.path.join(current, marker)) for marker in _ROOT_MARKERS):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            # Chạm gốc hệ thống tệp mà không thấy dấu hiệu nào: lùi về thư mục cha của `src/`.
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        current = parent


def data_dir(*parts: str) -> str:
    """Đường dẫn bên trong `data/` của dự án."""
    return os.path.join(project_root(), "data", *parts)


def processed_dir(*parts: str) -> str:
    """Đường dẫn bên trong `data/processed/`."""
    return data_dir("processed", *parts)


def runtime_dir(*parts: str) -> str:
    """Đường dẫn bên trong `data/runtime/` (checkpoint, cache, trace)."""
    return data_dir("runtime", *parts)
