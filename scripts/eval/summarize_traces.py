"""
Tổng hợp trace JSONL thành bảng số liệu quan trắc (Phase 7).

Đọc `data/runtime/traces/*.jsonl` bằng một vòng lặp (một dòng một sự kiện, không lồng nhau)
và in ra: độ trễ p50/p95 theo node, chi phí trung bình mỗi câu, tỉ lệ trúng cache, phân bố
tầng structured output, tỉ lệ fallback model.

Dùng:
    python scripts/eval/summarize_traces.py
    python scripts/eval/summarize_traces.py --since 2026-09-09 --out report.json
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.observability.tracer import get_trace_dir  # noqa: E402


def percentile(values: List[float], pct: float) -> float:
    """Phân vị theo phương pháp nearest-rank — đủ chính xác cho số mẫu ở quy mô này."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * len(ordered) + 0.5)) - 1))
    return ordered[index]


def iter_records(trace_dir: str, since: Optional[str] = None) -> Iterable[Dict[str, Any]]:
    """Duyệt mọi dòng trace hợp lệ, bỏ qua dòng hỏng thay vì làm hỏng cả báo cáo."""
    if not os.path.isdir(trace_dir):
        return
    for name in sorted(os.listdir(trace_dir)):
        if not (name.startswith("trace-") and name.endswith(".jsonl")):
            continue
        if since and name[len("trace-"):-len(".jsonl")] < since:
            continue
        with open(os.path.join(trace_dir, name), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def summarize(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Gom số liệu tổng hợp — không giữ lại nội dung câu hỏi, chỉ giữ con số."""
    node_latency: Dict[str, List[float]] = defaultdict(list)
    node_counts: Counter = Counter()
    tier_counts: Counter = Counter()
    model_counts: Counter = Counter()
    runs: set = set()
    total_cost = 0.0
    cost_unknown_calls = 0
    llm_calls = 0
    estimated_token_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    cache_hits = 0
    cache_lookups = 0
    errors = 0
    fallback_runs: set = set()

    for rec in records:
        run_id = rec.get("run_id")
        if run_id:
            runs.add(run_id)

        event = rec.get("event")
        node = rec.get("node") or "(unknown)"
        duration = rec.get("duration_ms")

        if event == "node_end":
            node_counts[node] += 1
            if isinstance(duration, (int, float)):
                node_latency[node].append(float(duration))
            hit = rec.get("cache_hit")
            if hit is not None:
                cache_lookups += 1
                cache_hits += 1 if hit else 0

        elif event == "llm_end":
            llm_calls += 1
            prompt_tokens += int(rec.get("prompt_tokens") or 0)
            completion_tokens += int(rec.get("completion_tokens") or 0)
            total_cost += float(rec.get("cost_usd") or 0.0)
            model = rec.get("model")
            if model:
                model_counts[model] += 1
            extra = rec.get("extra") or {}
            if extra.get("tokens_estimated"):
                estimated_token_calls += 1
            if extra.get("cost_source") == "unknown":
                cost_unknown_calls += 1

        elif event == "structured_call":
            # Tầng structured output được chốt SAU khi lệnh gọi kết thúc, nên nó là một
            # sự kiện riêng chứ không phải một trường của llm_end.
            tier = rec.get("structured_tier")
            if tier:
                tier_counts[str(tier)] += 1

        elif event == "model_fallback":
            if run_id:
                fallback_runs.add(run_id)

        if rec.get("error"):
            errors += 1

    run_count = len(runs) or 1
    return {
        "runs": len(runs),
        "nodes": {
            node: {
                "count": node_counts[node],
                "p50_ms": round(percentile(node_latency[node], 50), 2),
                "p95_ms": round(percentile(node_latency[node], 95), 2),
            }
            for node in sorted(node_counts)
        },
        "llm_calls": llm_calls,
        "llm_calls_per_run": round(llm_calls / run_count, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_cost_usd": round(total_cost, 6),
        "cost_per_run_usd": round(total_cost / run_count, 6),
        "cost_unknown_calls": cost_unknown_calls,
        "estimated_token_calls": estimated_token_calls,
        "cache_lookups": cache_lookups,
        "cache_hit_rate": round(cache_hits / cache_lookups, 4) if cache_lookups else None,
        "structured_tier_distribution": dict(sorted(tier_counts.items())),
        "model_distribution": dict(model_counts.most_common()),
        "fallback_runs": len(fallback_runs),
        "fallback_rate": round(len(fallback_runs) / run_count, 4),
        "errors": errors,
    }


def print_report(summary: Dict[str, Any]) -> None:
    print("=" * 74)
    print("BÁO CÁO QUAN TRẮC — LexTraffic AI")
    print("=" * 74)
    print(f"Số lượt chạy: {summary['runs']}    Số lệnh gọi LLM: {summary['llm_calls']} "
          f"({summary['llm_calls_per_run']} / lượt)")
    print()

    print(f"{'Node':<20}{'Số lần':>10}{'p50 (ms)':>14}{'p95 (ms)':>14}")
    print("-" * 74)
    for node, stats in summary["nodes"].items():
        print(f"{node:<20}{stats['count']:>10}{stats['p50_ms']:>14.2f}{stats['p95_ms']:>14.2f}")
    print()

    print(f"Token vào / ra: {summary['prompt_tokens']:,} / {summary['completion_tokens']:,}")
    print(f"Chi phí ước tính: ${summary['total_cost_usd']:.6f} tổng, "
          f"${summary['cost_per_run_usd']:.6f} / lượt")
    if summary["cost_unknown_calls"]:
        print(f"  ! {summary['cost_unknown_calls']} lệnh gọi chưa biết đơn giá — ghi 0, không phải miễn phí")
    if summary["estimated_token_calls"]:
        print(f"  ! {summary['estimated_token_calls']} lệnh gọi phải ước lượng token (provider không báo usage)")

    rate = summary["cache_hit_rate"]
    # Nói rõ ĐÂY LÀ CACHE NÀO. Chỉ `src/retrieval/cache.py` (cache vector truy vấn) gọi
    # `record_cache_event()`; cache ngữ nghĩa câu trả lời KHÔNG ghi vào trace mà có thống kê
    # riêng ở `scripts/cache_admin.py --stats`. Ghi trống tên cache khiến người đọc tưởng con số
    # này là tỉ lệ trúng cache câu trả lời — hai thứ hoàn toàn khác nhau về ý nghĩa vận hành.
    print(f"Cache vector truy vấn (embedding): {summary['cache_lookups']} lượt tra, tỉ lệ trúng "
          f"{'—' if rate is None else f'{rate:.1%}'}")
    print("  (cache ngữ nghĩa câu trả lời thống kê riêng: python scripts/cache_admin.py --stats)")
    print(f"Phân bố structured_tier: {summary['structured_tier_distribution'] or '—'}")
    print(f"Model đã dùng: {summary['model_distribution'] or '—'}")
    print(f"Fallback model: {summary['fallback_runs']} lượt ({summary['fallback_rate']:.1%})")
    print(f"Số sự kiện lỗi: {summary['errors']}")
    print("=" * 74)
    print("Lưu ý: chi phí là ước lượng cục bộ. Con số quyết toán là hoá đơn OpenRouter.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tổng hợp trace quan trắc JSONL")
    parser.add_argument("--trace-dir", default=None, help="Thư mục trace (mặc định TRACE_DIR)")
    parser.add_argument("--since", default=None, help="Chỉ đọc trace từ ngày này (YYYY-MM-DD)")
    parser.add_argument("--out", default=None, help="Ghi báo cáo JSON ra tệp")
    args = parser.parse_args()

    trace_dir = args.trace_dir or get_trace_dir()
    summary = summarize(iter_records(trace_dir, since=args.since))

    if summary["runs"] == 0:
        print(f"Không tìm thấy dòng trace nào trong {trace_dir}.")
        return 1

    print_report(summary)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        print(f"\nĐã ghi báo cáo JSON: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
