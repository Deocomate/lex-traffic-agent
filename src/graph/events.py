"""
Quản lý và phát sự kiện tiến trình Server-Sent Events (SSE) cho LangGraph.
Sử dụng get_stream_writer() của LangGraph với cơ chế chịu lỗi khi chạy
ngoài luồng stream (trong unit tests hoặc chạy offline).
"""

import contextvars
import time
from typing import Any, Callable, Dict, Optional

# ContextVar lưu trữ callback tùy chọn khi chạy ngoài ngữ cảnh stream của LangGraph
_event_callback_var: contextvars.ContextVar[Optional[Callable[[Dict[str, Any]], None]]] = (
    contextvars.ContextVar("event_callback", default=None)
)


def set_event_callback(callback: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Thiết lập callback lắng nghe sự kiện trong ngữ cảnh luồng hiện tại."""
    _event_callback_var.set(callback)


def create_event(event_type: str, message: str = "", **payload) -> Dict[str, Any]:
    """Tạo payload sự kiện chuẩn hóa theo hợp đồng 14 sự kiện SSE của LexTraffic AI."""
    return {
        "event": event_type,
        "message": message,
        "timestamp": time.strftime("%H:%M:%S"),
        **payload,
    }


def emit(event_type: str, message: str = "", **payload) -> None:
    """
    Phát một sự kiện tiến trình:
    1. Gửi qua callback contextvar (nếu được thiết lập).
    2. Gửi qua get_stream_writer() của LangGraph khi đang trong luồng astream(..., stream_mode=["custom", ...]).
    """
    event_dict = create_event(event_type, message, **payload)

    # 1. Gọi qua callback context nếu có
    cb = _event_callback_var.get()
    if cb is not None:
        try:
            cb(event_dict)
        except Exception:
            pass

    # 2. Gọi qua StreamWriter của LangGraph
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
        if writer is not None:
            writer(event_dict)
    except Exception:
        # Khi chạy ngoài ngữ cảnh stream, bỏ qua một cách an toàn
        pass
