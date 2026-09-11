"""
Node Suy luận Trung tâm của Agent (Agent Node) trong LangGraph.
Sử dụng mô hình chính (LLM_MODEL) gắn trực tiếp 7 công cụ tra cứu.
Agent tự chủ suy luận, quyết định gọi công cụ hoặc tổng hợp câu trả lời cuối cùng.
"""

import json
import logging
from typing import Any, Dict, List, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.graph.events import emit
from src.graph.state import LegalAgentState
from src.graph.synthesize import clean_text_output, polish_answer
from src.llm.provider import get_model_tracker, get_synthesize_llm
from src.prompts.system_vi import get_system_prompt_vi
from src.tools.law_search_tools import TOOLS_SCHEMA

logger = logging.getLogger(__name__)

MAX_TURNS = 4


def agent_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node Agent: Tiếp nhận câu hỏi và lịch sử trao đổi, suy luận và:
    1. Phát sinh tool calls nếu cần thêm dữ liệu pháp lý.
    2. Hoặc sinh câu trả lời hoàn chỉnh (kèm streaming token) khi đã đủ dữ liệu.
    """
    messages = state.get("messages", [])
    turn = state.get("turn_count", 0) + 1

    if turn == 1:
        emit("start", "🧠 Đang phân tích câu hỏi và lập kế hoạch tra cứu...")

    emit("turn_start", f"🔄 [Lượt {turn}/{MAX_TURNS}] Đang suy luận và xử lý dữ liệu...", turn=turn)

    base_model = get_synthesize_llm()
    tracker = get_model_tracker(base_model)
    model_used = tracker.active_model if tracker and tracker.active_model else "deepseek/deepseek-v4-flash"

    model_with_tools = base_model.bind_tools(TOOLS_SCHEMA)

    system_prompt = get_system_prompt_vi()
    prompt_messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]
    for msg in messages:
        if not isinstance(msg, SystemMessage):
            prompt_messages.append(msg)

    # Chạy mô hình dạng streaming để phát token ngay lập tức nếu mô hình bắt đầu trả lời
    collected_tokens: List[str] = []
    final_tool_calls: List[Dict[str, Any]] = []
    has_emitted_synthesizing = False

    try:
        accumulated_msg = None
        for chunk in model_with_tools.stream(prompt_messages):
            if accumulated_msg is None:
                accumulated_msg = chunk
            else:
                accumulated_msg += chunk

            # Nếu có token nội dung (không phải tool call)
            if chunk.content and isinstance(chunk.content, str):
                if not has_emitted_synthesizing:
                    emit("synthesizing", "✍️ Đã có đủ dữ liệu. Đang tổng hợp lời giải đáp pháp lý...")
                    has_emitted_synthesizing = True
                collected_tokens.append(chunk.content)
                emit("token", chunk.content, phase="answer")

        if accumulated_msg is not None:
            if hasattr(accumulated_msg, "tool_calls") and accumulated_msg.tool_calls:
                final_tool_calls = accumulated_msg.tool_calls
    except Exception as stream_err:
        logger.warning(f"Stream error in agent_node, falling back to invoke: {stream_err}")
        try:
            res = model_with_tools.invoke(prompt_messages)
            if hasattr(res, "tool_calls") and res.tool_calls:
                final_tool_calls = res.tool_calls
            elif res.content:
                content_str = str(res.content)
                collected_tokens = [content_str]
                emit("synthesizing", "✍️ Đã có đủ dữ liệu. Đang tổng hợp lời giải đáp pháp lý...")
                emit("token", content_str, phase="answer")
        except Exception as e:
            emit("error", f"Lỗi trong quá trình suy luận của Agent: {e}")
            collected_tokens = [f"Đã xảy ra lỗi khi xử lý: {e}"]

    # Nếu có tool call -> chuyển sang node tools
    if final_tool_calls:
        ai_message = AIMessage(content="", tool_calls=final_tool_calls)
        return {
            "messages": [ai_message],
            "turn_count": turn,
            "model_used": model_used,
        }

    # Nếu không có tool call -> Đây là câu trả lời cuối cùng
    raw_answer = "".join(collected_tokens)
    final_answer = polish_answer(clean_text_output(raw_answer))
    emit("answer_commit", "", answer=final_answer)

    ai_message = AIMessage(content=final_answer)
    return {
        "messages": [ai_message],
        "answer": final_answer,
        "turn_count": turn,
        "model_used": model_used,
    }


def agent_router(state: LegalAgentState) -> Literal["tools", "verify"]:
    """Định tuyến sau node agent: Nếu có tool call và chưa quá giới hạn -> gọi tools, ngược lại -> kiểm chứng."""
    messages = state.get("messages", [])
    turn = state.get("turn_count", 0)

    if messages:
        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None) or []
        if tool_calls and turn < MAX_TURNS:
            return "tools"

    return "verify"
