"""
Adapter cho bộ công cụ đánh giá (Evaluation Harness) tích hợp StateGraph LangGraph.
Kế thừa BaseAgentAdapter để có thể chạy trực tiếp qua:
python scripts/eval/retrieval_eval.py --adapter graph
hoặc:
python scripts/eval/e2e_eval.py --adapter graph
"""

import time
from typing import Any, Dict, List, Optional

from scripts.eval.adapters import BaseAgentAdapter
from src.graph.build import get_legal_graph
from src.graph.events import set_event_callback
from src.graph.turn import run_turn


class GraphAdapter(BaseAgentAdapter):
    """Adapter bọc StateGraph LangGraph mới (src/graph/build.py)."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.graph = get_legal_graph()

    def run(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        # Chuẩn hóa messages từ history
        from langchain_core.messages import AIMessage, HumanMessage
        messages = []
        if history:
            for m in history:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        collected_events: List[Dict[str, Any]] = []

        def event_listener(evt: Dict[str, Any]) -> None:
            collected_events.append(evt)
            if self.verbose:
                print(f"  [{evt.get('timestamp')}] {evt.get('event')}: {evt.get('message')}")

        set_event_callback(event_listener)

        # Đi qua `run_turn` chứ không gọi thẳng `graph.invoke`: đó là đúng đường mà máy chủ
        # dùng, gồm cả tra và ghi cache ngữ nghĩa. Một bộ eval đi vòng qua cache thì không đo
        # hệ thống thật, và bước "chạy lại lần hai" của Phase 6 sẽ không kiểm được gì cả.
        history_payload = [
            {"role": "user" if m.type == "human" else "assistant", "content": m.content}
            for m in messages
        ]

        start_t = time.perf_counter()
        try:
            turn = run_turn(question, history=history_payload)
        finally:
            set_event_callback(None)

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0

        ans_text = turn.get("answer", "")
        tool_outputs = turn.get("tool_outputs", [])

        # Ước lượng token (~1.5 token / từ tiếng Việt)
        est_tokens_in = int(len(question.split()) * 1.5) + int(sum(len(t.split()) for t in tool_outputs) * 1.5)
        est_tokens_out = int(len(ans_text.split()) * 1.5)

        return {
            "answer": ans_text,
            "sources": turn.get("sources", []),
            "agent_steps": turn.get("agent_steps", []),
            "verification_issues": turn.get("issues", []),
            "needs_search": turn.get("needs_search", False),
            "search": turn.get("search"),
            "latency_ms": elapsed_ms,
            "tokens_in": est_tokens_in,
            "tokens_out": est_tokens_out,
            "raw_tool_outputs": tool_outputs,
            "cached": turn.get("cached", False),
        }
