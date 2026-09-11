"""
Cấu hình kiểm thử cách ly cho LexTraffic AI.
Đảm bảo môi trường test không ghi đè vào cơ sở dữ liệu runtime thật.
"""

import os
import sys
import pytest

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)


@pytest.fixture(scope="session", autouse=True)
def isolate_runtime_state(tmp_path_factory):
    """Trỏ mọi tệp trạng thái chạy sang thư mục tạm và tắt cache ngữ nghĩa."""
    runtime_dir = tmp_path_factory.mktemp("runtime")

    previous = {
        key: os.environ.get(key)
        for key in ("ANSWER_CACHE_DB_PATH", "CHECKPOINT_DB_PATH", "ENABLE_SEMANTIC_CACHE")
    }

    os.environ["ANSWER_CACHE_DB_PATH"] = str(runtime_dir / "answer_cache.sqlite")
    os.environ["CHECKPOINT_DB_PATH"] = str(runtime_dir / "checkpoints.sqlite")
    os.environ["ENABLE_SEMANTIC_CACHE"] = "false"

    yield

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
