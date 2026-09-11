"""
Cache ngữ nghĩa cho câu trả lời ĐÃ QUA KIỂM CHỨNG.

Cache theo độ tương đồng vector đơn thuần là nguy hiểm với miền pháp luật. "Ô tô vượt đèn đỏ
phạt bao nhiêu" và "Xe máy vượt đèn đỏ phạt bao nhiêu" khác nhau đúng một cụm từ nên cosine
rất cao, nhưng mức phạt hoàn toàn khác. Trúng cache sai ở đây nghĩa là đưa cho người dùng một
con số sai — đúng loại lỗi mà cả kiến trúc này sinh ra để chặn.

Vì vậy khoá cache là TỔ HỢP, không phải chỉ vector:

    (intents, vehicles, doc_scope, index_fingerprint)  -> phải khớp CHÍNH XÁC
    trong cùng một khoá, mới so cosine của vector truy vấn

Ngưỡng 0.97 (thay vì 0.95 thường dùng) là có chủ ý: một lần trúng nhầm tốn kém hơn nhiều so
với mười lần trượt cache.
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CacheSignals(BaseModel):
    """
    Tín hiệu tất định dùng để dựng khoá cache ngữ nghĩa.

    Trước đây đây là `RouteDecision` trong state của đồ thị, phục vụ một node router LLM đã bị
    gỡ bỏ. Giờ nó chỉ còn đúng một vai trò — thành phần của khoá cache — nên nó sống ở đây,
    cạnh chỗ dùng, thay vì trong state.
    """

    intents: List[str] = Field(default_factory=list)
    vehicles: List[str] = Field(default_factory=list)
    doc_scope: str = "all"

DEFAULT_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.97"))
DEFAULT_TTL_DAYS = int(os.getenv("CACHE_TTL_DAYS", "30"))


def is_semantic_cache_enabled() -> bool:
    """Đọc công tắc bật/tắt tại thời điểm gọi để test có thể đảo qua monkeypatch env."""
    return os.getenv("ENABLE_SEMANTIC_CACHE", "true").strip().lower() not in ("false", "0", "no")


def build_cache_key(route: CacheSignals, index_fingerprint: str) -> str:
    """
    Dựng khoá tổ hợp từ tín hiệu tất định của câu hỏi và vân tay chỉ mục.

    `intents` và `vehicles` đến từ tập hợp (set) nên thứ tự không ổn định giữa hai lần chạy —
    phải sắp xếp trước khi băm, nếu không cùng một câu hỏi sẽ sinh hai khoá khác nhau và cache
    không bao giờ trúng.
    """
    payload = "|".join(
        [
            "intents=" + ",".join(sorted(route.intents)),
            "vehicles=" + ",".join(sorted(route.vehicles)),
            f"doc_scope={route.doc_scope}",
            f"index={index_fingerprint}",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_cacheable(
    answer: str,
    issues: Optional[List[str]],
    needs_search: bool,
    sources: Optional[List[Dict[str, Any]]],
) -> bool:
    """
    Ba điều kiện ghi cache, tất cả phải đúng.

    Câu trả lời chưa qua kiểm chứng hoặc đã bị huỷ không bao giờ được cache: ghi nó lại là
    hợp thức hoá vĩnh viễn đúng những con số mà node `verify` vừa bắt được.
    """
    return bool(answer and answer.strip()) and not issues and not needs_search and bool(sources)


class SemanticAnswerCache:
    """Cache SQLite lưu câu trả lời đã kiểm chứng, tra theo khoá tổ hợp rồi mới so cosine."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        threshold: Optional[float] = None,
        ttl_days: Optional[int] = None,
    ):
        if not db_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.getenv("ANSWER_CACHE_DB_PATH") or os.path.join(
                base_dir, "data", "runtime", "answer_cache.sqlite"
            )
        self.db_path = db_path
        self.threshold = DEFAULT_THRESHOLD if threshold is None else threshold
        self.ttl_days = DEFAULT_TTL_DAYS if ttl_days is None else ttl_days
        self._local = threading.local()
        self._init_db()

    # -- Kết nối ------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Kết nối SQLite riêng cho từng luồng: đồ thị chạy trong worker thread riêng."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS answer_cache (
                    key_hash TEXT NOT NULL,
                    query TEXT NOT NULL,
                    query_vector BLOB NOT NULL,
                    dim INTEGER NOT NULL,
                    answer TEXT NOT NULL,
                    sources TEXT NOT NULL,
                    tool_outputs TEXT NOT NULL DEFAULT '[]',
                    index_fingerprint TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (key_hash, query)
                );
                """
            )
            # Tệp cache sinh trước khi có cột `tool_outputs` vẫn phải mở được: nó là dữ liệu
            # chạy có thể tái tạo, nhưng sập vì thiếu cột thì lại là một lỗi khó hiểu.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(answer_cache);")}
            if "tool_outputs" not in columns:
                conn.execute(
                    "ALTER TABLE answer_cache ADD COLUMN tool_outputs TEXT NOT NULL DEFAULT '[]';"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_answer_cache_key ON answer_cache(key_hash);"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_stats (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.commit()

    def _bump_stat(self, name: str, conn: Optional[sqlite3.Connection] = None) -> None:
        conn = conn or self._get_connection()
        conn.execute(
            "INSERT INTO cache_stats(name, value) VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1;",
            (name,),
        )
        conn.commit()

    # -- Tra cứu ------------------------------------------------------------

    def get(
        self,
        key: str,
        query_vector: np.ndarray,
        index_fingerprint: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Trả về `{"answer", "sources", "query", "similarity"}` khi trúng cache, `None` khi trượt.

        Lọc theo khoá tổ hợp ngay trong SQL trước, chỉ so cosine trong nhóm còn lại: chuyện
        "ô tô/xe máy" bị chặn ở tầng SQL chứ không phụ thuộc vào ngưỡng tương đồng.
        """
        if not is_semantic_cache_enabled():
            return None

        try:
            conn = self._get_connection()
            min_created_at = self._min_created_at()
            rows = conn.execute(
                "SELECT query, query_vector, dim, answer, sources, tool_outputs FROM answer_cache "
                "WHERE key_hash = ? AND index_fingerprint = ? AND created_at >= ?;",
                (key, index_fingerprint, min_created_at),
            ).fetchall()

            best_row, best_score = None, -1.0
            probe = self._normalize(query_vector)
            for row in rows:
                stored = np.frombuffer(row["query_vector"], dtype=np.float32)
                if stored.shape[0] != probe.shape[0]:
                    continue  # Đổi số chiều nhúng: mục cũ không so sánh được
                score = float(np.dot(probe, stored))
                if score > best_score:
                    best_row, best_score = row, score

            if best_row is not None and best_score >= self.threshold:
                self._bump_stat("hits", conn)
                return {
                    "answer": best_row["answer"],
                    "sources": json.loads(best_row["sources"]),
                    # Bang chung nguyen van di kem cau tra loi: thieu no, moi lop do chieu
                    # chay sau (kiem chung, do luong eval) se ket luan sai rang cau tra loi
                    # tu cache khong co can cu, chi vi khong ai dua can cu cho no.
                    "tool_outputs": json.loads(best_row["tool_outputs"] or "[]"),
                    "query": best_row["query"],
                    "similarity": best_score,
                }

            self._bump_stat("misses", conn)
            return None
        except Exception as e:
            # Cache hỏng không được phép làm hỏng câu trả lời: coi như trượt và chạy đồ thị.
            logger.warning("[SemanticCache] Lỗi khi tra cache, bỏ qua: %s", e)
            return None

    def put(
        self,
        key: str,
        query: str,
        query_vector: np.ndarray,
        answer: str,
        sources: List[Dict[str, Any]],
        index_fingerprint: str,
        tool_outputs: Optional[List[str]] = None,
    ) -> bool:
        """Ghi một câu trả lời đã kiểm chứng vào cache. Trả về True nếu ghi thành công."""
        # Tắt cache phải có nghĩa là không đọc VÀ không ghi: ghi tiếp khi đang tắt sẽ để lại
        # một kho câu trả lời cũ, âm thầm sống lại nguyên vẹn vào ngày ai đó bật lại công tắc.
        if not is_semantic_cache_enabled():
            return False
        try:
            vector = self._normalize(query_vector)
            conn = self._get_connection()
            conn.execute(
                "INSERT INTO answer_cache "
                "(key_hash, query, query_vector, dim, answer, sources, tool_outputs, "
                " index_fingerprint, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now')) "
                "ON CONFLICT(key_hash, query) DO UPDATE SET "
                "  query_vector = excluded.query_vector, dim = excluded.dim, "
                "  answer = excluded.answer, sources = excluded.sources, "
                "  tool_outputs = excluded.tool_outputs, "
                "  index_fingerprint = excluded.index_fingerprint, created_at = excluded.created_at;",
                (
                    key,
                    query,
                    vector.tobytes(),
                    int(vector.shape[0]),
                    answer,
                    json.dumps(sources, ensure_ascii=False),
                    json.dumps(tool_outputs or [], ensure_ascii=False),
                    index_fingerprint,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning("[SemanticCache] Lỗi khi ghi cache, bỏ qua: %s", e)
            return False

    # -- Quản trị -----------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Số mục đang lưu, số lần trúng/trượt và tỉ lệ trúng cache."""
        conn = self._get_connection()
        entries = conn.execute("SELECT COUNT(*) FROM answer_cache;").fetchone()[0]
        counters = {
            row["name"]: row["value"]
            for row in conn.execute("SELECT name, value FROM cache_stats;").fetchall()
        }
        hits = int(counters.get("hits", 0))
        misses = int(counters.get("misses", 0))
        total = hits + misses
        return {
            "entries": entries,
            "hits": hits,
            "misses": misses,
            "hit_rate": (hits / total) if total else 0.0,
            "db_path": self.db_path,
            "threshold": self.threshold,
            "ttl_days": self.ttl_days,
        }

    def clear(self) -> int:
        """Xoá toàn bộ mục cache và bộ đếm. Trả về số mục đã xoá."""
        conn = self._get_connection()
        removed = conn.execute("SELECT COUNT(*) FROM answer_cache;").fetchone()[0]
        conn.execute("DELETE FROM answer_cache;")
        conn.execute("DELETE FROM cache_stats;")
        conn.commit()
        return int(removed)

    def prune_expired(self, current_fingerprint: Optional[str] = None) -> int:
        """
        Xoá các mục quá hạn TTL, và khi biết vân tay hiện tại thì xoá luôn các mục thuộc vân
        tay cũ. Trả về số mục đã xoá.

        Mục thuộc vân tay cũ đã không thể trúng cache được nữa, nhưng nếu không dọn thì chúng
        nằm lại vĩnh viễn và mỗi lần dựng lại chỉ mục lại bồi thêm một lớp.
        """
        conn = self._get_connection()
        if current_fingerprint:
            cur = conn.execute(
                "DELETE FROM answer_cache WHERE created_at < ? OR index_fingerprint != ?;",
                (self._min_created_at(), current_fingerprint),
            )
        else:
            cur = conn.execute(
                "DELETE FROM answer_cache WHERE created_at < ?;", (self._min_created_at(),)
            )
        conn.commit()
        return int(cur.rowcount or 0)

    # -- Tiện ích -----------------------------------------------------------

    def _min_created_at(self) -> float:
        """Mốc thời gian sớm nhất còn hợp lệ theo TTL (giây epoch)."""
        import time

        return time.time() - self.ttl_days * 86400.0

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        """Chuẩn hoá L2 để tích vô hướng chính là cosine."""
        v = np.asarray(vector, dtype=np.float32).ravel()
        norm = float(np.linalg.norm(v))
        return v / norm if norm > 0 else v


_shared_cache: Optional[SemanticAnswerCache] = None
_shared_cache_lock = threading.Lock()


def get_semantic_cache() -> SemanticAnswerCache:
    """Singleton cache dùng chung cho toàn tiến trình."""
    global _shared_cache
    if _shared_cache is None:
        with _shared_cache_lock:
            if _shared_cache is None:
                _shared_cache = SemanticAnswerCache()
    return _shared_cache
