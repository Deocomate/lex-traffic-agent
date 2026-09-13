"""
Node Suy luận Trung tâm của Agent (Agent Node) trong LangGraph.

Mô hình chính được gắn bộ công cụ do Domain Pack khai báo và tự quyết định: gọi công cụ nào,
với tham số gì, bao nhiêu vòng, và khi nào đã đủ dữ liệu để trả lời. Node này không biết trước
công cụ nào tồn tại — đổi miền là đổi cả bộ công cụ mà không sửa dòng code nào ở đây.

Ngân sách lượt được NÓI THẲNG cho Agent thay vì cắt câm. Bản trước chỉ có `agent_router` lặng
lẽ chuyển sang `verify` khi chạm `MAX_TURNS`: nếu lượt cuối Agent vẫn phát tool call thì câu
trả lời rỗng, `verify` bắt lỗi "câu trả lời trống" rồi phải chạy thêm một vòng `repair` — tốn
một lệnh gọi mô hình chỉ để sửa hậu quả của việc không báo trước. Biết còn mấy lượt thì Agent
tự cân đối được: tra tiếp hay chốt lại với dữ liệu đang có.
"""

import json
import logging
from typing import Any, Dict, List, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.graph.events import emit
from src.graph.state import LegalAgentState
from src.graph.answer_text import clean_text_output, polish_answer
from src.llm.provider import get_model_tracker, get_synthesize_llm
from src.domain.registry import get_active_domain
from src.prompts.system_vi import get_system_prompt

logger = logging.getLogger(__name__)

# Trần mặc định của số vòng suy luận, dùng khi không đọc được Domain Pack. Đây là lưới an toàn
# chống lặp vô hạn, KHÔNG phải nút điều chỉnh chất lượng: Agent được cho biết còn bao nhiêu lượt
# và tự quyết định dừng sớm hơn.
MAX_TURNS = 4


def max_turns() -> int:
    """Trần số vòng tra cứu, do miền khai báo (`policy.max_tool_turns`)."""
    try:
        return get_active_domain().policy.max_tool_turns
    except Exception:
        return MAX_TURNS


def _turn_budget_notice(turn: int) -> str:
    """Nhắc Agent còn bao nhiêu lượt tra cứu, để nó tự cân đối thay vì bị cắt giữa chừng."""
    remaining = max_turns() - turn
    if remaining <= 0:
        return (
            "\n\nNGÂN SÁCH TRA CỨU: đây là lượt CUỐI CÙNG. Không gọi thêm công cụ nào nữa. "
            "Hãy trả lời ngay bằng dữ liệu đã thu thập được. Nếu dữ liệu chưa đủ để kết luận, "
            "hãy nói thẳng là chưa tra cứu được và nêu rõ còn thiếu thông tin gì — tuyệt đối "
            "không suy đoán số liệu."
        )
    return (
        f"\n\nNGÂN SÁCH TRA CỨU: bạn còn {remaining} lượt gọi công cụ sau lượt này. "
        "Hãy tự cân đối: nếu đã đủ căn cứ thì trả lời luôn, nếu còn thiếu thì gọi công cụ cho "
        "đúng chỗ thiếu."
    )


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

    emit("turn_start", f"🔄 [Lượt {turn}/{max_turns()}] Đang suy luận và xử lý dữ liệu...", turn=turn)

    base_model = get_synthesize_llm()
    tracker = get_model_tracker(base_model)
    model_used = tracker.active_model if tracker and tracker.active_model else "deepseek/deepseek-v4-flash"

    # Bộ công cụ do Domain Pack khai báo — engine không biết trước công cụ nào tồn tại.
    model_with_tools = base_model.bind_tools(get_active_domain().tools_schema)

    system_prompt = get_system_prompt() + _turn_budget_notice(turn)
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
    """
    Định tuyến sau node agent: còn tool call và còn ngân sách thì chạy công cụ, ngược lại sang
    kiểm chứng.

    Trần số vòng ở đây là lưới an toàn cuối. Đường đi thông thường là Agent tự dừng gọi
    công cụ khi thấy đủ dữ liệu, vì nó đã được cho biết còn bao nhiêu lượt.
    """
    messages = state.get("messages", [])
    turn = state.get("turn_count", 0)

    if messages:
        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None) or []
        if tool_calls and turn < max_turns():
            return "tools"

    return "verify"
