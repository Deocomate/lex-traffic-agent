"""
Bộ nhớ đệm vector truy vấn trên đĩa SQLite (Query Vector Cache).
Lưu trữ vector float32 đã chuẩn hóa L2 tại data/runtime/embed_cache.sqlite.
Khóa băm SHA-256 kết hợp giữa tên mô hình và truy vấn đã chuẩn hóa, tự động
miss khi thay đổi mô hình nhúng, giúp triệt tiêu độ trễ mạng cho các câu hỏi lặp.
"""

import hashlib
import logging
import os
import sqlite3
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _report_cache_event(hit: bool) -> None:
    """Báo một lần tra cache cho lớp quan trắc; im lặng khi quan trắc chưa được nạp."""
    try:
        from src.observability.tracer import record_cache_event

        record_cache_event(hit)
    except Exception:
        pass


class QueryVectorCache:
    """Cache lưu trữ vector nhúng truy vấn trên đĩa sử dụng SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(base_dir, "data", "runtime", "embed_cache.sqlite")
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Lấy kết nối SQLite riêng cho từng luồng (thread-safe)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Khởi tạo bảng cache nếu chưa tồn tại."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embed_cache (
                    cache_key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    query TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    @staticmethod
    def _normalize_query(query: str) -> str:
        """Chuẩn hóa chuỗi truy vấn trước khi tính khóa băm."""
        return " ".join(query.strip().lower().split())

    @classmethod
    def compute_key(cls, query: str, model: str) -> str:
        """Sinh mã khóa băm SHA256 cho cặp (query, model)."""
        norm_q = cls._normalize_query(query)
        payload = f"{model}\n{norm_q}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def get(self, query: str, model: str) -> Optional[np.ndarray]:
        """
        Lấy vector đã chuẩn hóa từ cache. Trả về None nếu miss.
        """
        key = self.compute_key(query, model)
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT vector, dim FROM embed_cache WHERE cache_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                blob, dim = row
                vec = np.frombuffer(blob, dtype=np.float32)
                if vec.shape[0] == dim:
                    _report_cache_event(True)
                    return vec
        except Exception as e:
            logger.warning("Lỗi đọc cache vector (%s): %s", key, e)
        _report_cache_event(False)
        return None

    def set(self, query: str, model: str, vector: np.ndarray) -> None:
        """
        Lưu vector vào cache. Tự động chuẩn hóa L2 và ép kiểu float32.
        """
        key = self.compute_key(query, model)
        try:
            vec = np.asarray(vector, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            blob = vec.tobytes()
            dim = int(vec.shape[0])

            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO embed_cache (cache_key, model, query, dim, vector)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, model, query[:1500], dim, blob),
                )
        except Exception as e:
            logger.warning("Lỗi ghi cache vector (%s): %s", key, e)

    def count(self) -> int:
        """Đếm tổng số bản ghi vector trong cache."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM embed_cache")
            return int(cursor.fetchone()[0])
        except Exception:
            return 0

    def clear(self) -> None:
        """Xóa toàn bộ bản ghi trong cache."""
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("DELETE FROM embed_cache")
        except Exception as e:
            logger.warning("Lỗi khi dọn cache: %s", e)

    def close(self) -> None:
        """Đóng kết nối SQLite của thread hiện tại nếu có."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None

