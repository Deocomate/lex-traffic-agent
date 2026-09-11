"""
Quản trị cache ngữ nghĩa và các thread hội thoại (Phase 6).

    python scripts/cache_admin.py --stats
    python scripts/cache_admin.py --clear
    python scripts/cache_admin.py --prune-threads [--days 30]

`--stats` in tỉ lệ trúng cache; `--clear` xoá toàn bộ câu trả lời đã lưu; `--prune-threads`
dọn các thread không hoạt động quá `--days` ngày để tệp checkpoint không phình vô hạn.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.cache.fingerprint import get_index_fingerprint  # noqa: E402
from src.cache.semantic_cache import SemanticAnswerCache  # noqa: E402

DEFAULT_PRUNE_DAYS = 30


def print_stats() -> None:
    """In thống kê cache: số mục, số lần trúng/trượt, tỉ lệ trúng."""
    cache = SemanticAnswerCache()
    stats = cache.stats()

    print("=== Cache ngữ nghĩa câu trả lời ===")
    print(f"  Tệp lưu trữ      : {stats['db_path']}")
    print(f"  Số mục đang lưu  : {stats['entries']}")
    print(f"  Trúng cache      : {stats['hits']}")
    print(f"  Trượt cache      : {stats['misses']}")
    print(f"  Tỉ lệ trúng cache: {stats['hit_rate'] * 100:.1f}%")
    print(f"  Ngưỡng tương đồng: {stats['threshold']}")
    print(f"  TTL (ngày)       : {stats['ttl_days']}")
    print(f"  Vân tay chỉ mục  : {get_index_fingerprint()[:16]}...")

    print("\n=== Thread hội thoại (checkpointer) ===")
    threads = collect_thread_activity()
    print(f"  Tệp lưu trữ      : {checkpoint_path()}")
    print(f"  Số thread        : {len(threads)}")
    if threads:
        newest = max(threads.values())
        oldest = min(threads.values())
        print(f"  Hoạt động gần nhất: {newest.isoformat(timespec='seconds')}")
        print(f"  Hoạt động cũ nhất : {oldest.isoformat(timespec='seconds')}")


def clear_cache() -> None:
    """Xoá toàn bộ mục cache và bộ đếm thống kê."""
    removed = SemanticAnswerCache().clear()
    print(f"Đã xoá {removed} mục khỏi cache ngữ nghĩa.")


def checkpoint_path() -> str:
    from src.graph.build import _default_checkpoint_path

    return os.getenv("CHECKPOINT_DB_PATH") or _default_checkpoint_path()


def collect_thread_activity() -> Dict[str, datetime]:
    """
    Thời điểm hoạt động gần nhất của từng thread, đọc từ dấu thời gian của checkpoint.

    Dùng `ts` trong chính checkpoint chứ không suy ra từ `checkpoint_id`: định dạng id là chi
    tiết nội bộ của LangGraph và có thể đổi giữa các phiên bản, còn `ts` là dữ liệu công khai.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    path = checkpoint_path()
    if not os.path.exists(path):
        return {}

    latest: Dict[str, datetime] = {}
    with SqliteSaver.from_conn_string(path) as saver:
        for item in saver.list(None):
            thread_id = item.config.get("configurable", {}).get("thread_id")
            raw_ts = (item.checkpoint or {}).get("ts")
            if not thread_id or not raw_ts:
                continue
            try:
                ts = datetime.fromisoformat(raw_ts)
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if thread_id not in latest or ts > latest[thread_id]:
                latest[thread_id] = ts
    return latest


def prune_threads(days: int, dry_run: bool = False) -> int:
    """Xoá các thread không hoạt động quá `days` ngày. Trả về số thread đã xoá."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stale = [tid for tid, ts in collect_thread_activity().items() if ts < cutoff]

    if not stale:
        print(f"Không có thread nào không hoạt động quá {days} ngày.")
        return 0

    if dry_run:
        print(f"[dry-run] {len(stale)} thread sẽ bị xoá (cũ hơn {cutoff.isoformat(timespec='seconds')}).")
        return 0

    with SqliteSaver.from_conn_string(checkpoint_path()) as saver:
        for thread_id in stale:
            saver.delete_thread(thread_id)

    expired = SemanticAnswerCache().prune_expired(get_index_fingerprint())
    print(f"Đã xoá {len(stale)} thread không hoạt động quá {days} ngày.")
    print(f"Đã dọn thêm {expired} mục cache quá hạn TTL hoặc thuộc chỉ mục cũ.")
    return len(stale)


def main() -> int:
    parser = argparse.ArgumentParser(description="Quản trị cache ngữ nghĩa và thread hội thoại")
    parser.add_argument("--stats", action="store_true", help="In thống kê cache và thread")
    parser.add_argument("--clear", action="store_true", help="Xoá toàn bộ cache ngữ nghĩa")
    parser.add_argument("--prune-threads", action="store_true", help="Xoá thread cũ không hoạt động")
    parser.add_argument("--days", type=int, default=DEFAULT_PRUNE_DAYS,
                        help=f"Số ngày không hoạt động để coi là cũ (mặc định {DEFAULT_PRUNE_DAYS})")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê, không xoá gì")
    args = parser.parse_args()

    if not (args.stats or args.clear or args.prune_threads):
        parser.print_help()
        return 1

    if args.stats:
        print_stats()
    if args.clear:
        clear_cache()
    if args.prune_threads:
        prune_threads(args.days, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
