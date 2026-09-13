"""
Façade trung tâm điều phối Agent của LexTraffic AI (src/agent.py).
Cung cấp giao diện tương thích ngược 100% với:
- stream_agent(): generator đồng bộ phục vụ CLI và test scripts
- astream_agent(): async generator phục vụ FastAPI StreamingResponse
- run_agent(): phương thức blocking cho evaluation và benchmark
- LegalAgent / AgenticLegalSearch: class bọc cho client cũ
"""

import asyncio
import os
import queue
import threading
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional

from src.graph.events import set_event_callback
from src.domain.registry import get_active_domain
from src.graph.turn import format_history_messages, new_thread_id, run_turn

# Giữ tên cũ cho client nội bộ đã import; phần thân đã dời sang src/graph/turn.py.
_format_history_messages = format_history_messages


def stream_agent(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
    max_turns: int = 4,
    thread_id: str = "",
) -> Generator[Dict[str, Any], None, None]:
    """
    Chạy đồ thị LangGraph và phát 14 sự kiện SSE theo thời gian thực (đồng bộ).
    Sử dụng queue đa luồng để truyền sự kiện mượt mà từ callback của LangGraph.
    """
    thread_id = thread_id or new_thread_id()
    q: queue.Queue = queue.Queue()
    done_sentinel = object()

    def event_listener(evt: Dict[str, Any]) -> None:
        q.put(evt)

    def worker():
        try:
            set_event_callback(event_listener)
            run_turn(user_query, history=history, thread_id=thread_id)
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put({"event": "error", "message": f"Sự cố thực thi đồ thị Agent: {e}"})
            q.put({
                "event": "done",
                "answer": f"Đã xảy ra lỗi trong quá trình tra cứu: {e}",
                "agent_steps": [],
                "sources": [],
                "needs_search": False,
                "search": None,
                "thread_id": thread_id,
            })
        finally:
            set_event_callback(None)
            q.put(done_sentinel)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    while True:
        item = q.get()
        if item is done_sentinel:
            break
        yield item


async def astream_agent(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
    max_turns: int = 4,
    thread_id: str = "",
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Chạy đồ thị LangGraph và stream sự kiện SSE bất đồng bộ (Async Generator).
    Tối ưu hóa cho FastAPI StreamingResponse không bao giờ block event loop.
    """
    thread_id = thread_id or new_thread_id()
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    done_sentinel = object()

    def event_listener(evt: Dict[str, Any]) -> None:
        loop.call_soon_threadsafe(q.put_nowait, evt)

    def worker():
        try:
            set_event_callback(event_listener)
            run_turn(user_query, history=history, thread_id=thread_id)
        except Exception as e:
            loop.call_soon_threadsafe(q.put_nowait, {"event": "error", "message": f"Sự cố thực thi đồ thị Agent: {e}"})
            loop.call_soon_threadsafe(
                q.put_nowait,
                {
                    "event": "done",
                    "answer": f"Đã xảy ra lỗi trong quá trình tra cứu: {e}",
                    "agent_steps": [],
                    "sources": [],
                    "needs_search": False,
                    "search": None,
                    "thread_id": thread_id,
                },
            )
        finally:
            set_event_callback(None)
            loop.call_soon_threadsafe(q.put_nowait, done_sentinel)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    while True:
        item = await q.get()
        if item is done_sentinel:
            break
        yield item


def run_agent(
    user_query: str,
    max_turns: int = 4,
    step_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    thread_id: str = "",
) -> Dict[str, Any]:
    """
    Phiên bản đồng bộ (blocking) phục vụ CLI và script kiểm thử benchmark.
    Mọi sự kiện tiến trình được đẩy qua step_callback (bỏ qua token để không nhiễu console).
    """
    result: Dict[str, Any] = {
        "query": user_query,
        "answer": "",
        "agent_steps": [],
        "workflow_steps": [],
        "sources": [],
        "needs_search": False,
        "search": None,
        "verification_issues": [],
        "model_used": os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
    }

    for evt in stream_agent(user_query, history=history, max_turns=max_turns, thread_id=thread_id):
        if evt["event"] == "token":
            continue
        result["workflow_steps"].append(evt)
        if step_callback:
            try:
                step_callback(evt)
            except Exception:
                pass
        if evt["event"] == "done":
            result["answer"] = evt.get("answer", "")
            result["agent_steps"] = evt.get("agent_steps", [])
            result["sources"] = evt.get("sources", [])
            result["verification_issues"] = evt.get("verification_issues", [])
            result["needs_search"] = evt.get("needs_search", False)
            result["search"] = evt.get("search")
            result["model_used"] = evt.get("model_used", result["model_used"])
            result["thread_id"] = evt.get("thread_id", thread_id)

    return result


class LegalAgent:
    """Class bọc giao diện tương thích với AgenticLegalSearch cũ."""

    def __init__(self, llm_model: Optional[str] = None):
        self.llm_model = llm_model or os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
        self.fallback_llm_model = os.getenv("FALLBACK_LLM_MODEL", "deepseek/deepseek-chat")
        # Bộ công cụ đến từ Domain Pack đang hoạt động, không còn là hằng số của miền giao thông.
        self.tools_schema = get_active_domain().tools_schema

    def stream_agent(
        self,
        user_query: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_turns: int = 4,
        thread_id: str = "",
    ) -> Generator[Dict[str, Any], None, None]:
        return stream_agent(user_query, history=history, max_turns=max_turns, thread_id=thread_id)

    async def astream_agent(
        self,
        user_query: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_turns: int = 4,
        thread_id: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async for evt in astream_agent(
            user_query, history=history, max_turns=max_turns, thread_id=thread_id
        ):
            yield evt

    def run_agent(
        self,
        user_query: str,
        max_turns: int = 4,
        step_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        thread_id: str = "",
    ) -> Dict[str, Any]:
        return run_agent(
            user_query,
            max_turns=max_turns,
            step_callback=step_callback,
            history=history,
            thread_id=thread_id,
        )


# Alias tương thích ngược 100%
AgenticLegalSearch = LegalAgent
_default_agent: Optional[LegalAgent] = None


def get_agent() -> LegalAgent:
    """Singleton getter cho LegalAgent."""
    global _default_agent
    if _default_agent is None:
        _default_agent = LegalAgent()
    return _default_agent
