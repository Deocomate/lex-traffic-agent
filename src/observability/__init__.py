"""
Lớp quan trắc cục bộ của LexTraffic AI (Phase 7).

Mặc định ghi trace JSONL xuống `data/runtime/traces/` — câu hỏi của người dùng không rời
khỏi máy. LangSmith là tuỳ chọn bật bằng biến môi trường `LANGSMITH_TRACING=true`.
"""

from src.observability.pricing import estimate_cost_usd
from src.observability.tracer import (
    JsonlTracer,
    get_current_tracer,
    get_trace_dir,
    new_run_tracer,
    record_cache_event,
    shutdown_tracing,
)

__all__ = [
    "JsonlTracer",
    "estimate_cost_usd",
    "get_current_tracer",
    "get_trace_dir",
    "new_run_tracer",
    "record_cache_event",
    "shutdown_tracing",
]
