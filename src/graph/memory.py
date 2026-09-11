"""
Node `memory`: nén lịch sử hội thoại theo NGÂN SÁCH TOKEN (Phase 6).

Vì sao không cắt theo số tin nhắn: sáu tin nhắn có thể là 200 token hoặc 8000 token — câu trả
lời pháp lý dài, có bảng và khối trích dẫn. Cắt theo số tin nhắn làm ngân sách context dao động
không kiểm soát, đúng loại rủi ro mà model nhỏ chịu kém nhất. Cắt theo token cho ngân sách ổn
định; phần bị cắt không mất hẳn mà được tóm tắt vào `history_summary`.

Lưu ý an toàn: `history_summary` là VĂN XUÔI TÓM TẮT, không phải nguồn đối chiếu. Node `verify`
chỉ đối chiếu với `raw_tool_output` và các câu trả lời assistant đầy đủ — không bao giờ với bản
tóm tắt, vì một con số đi qua bước tóm tắt đã mất đường về căn cứ gốc.
"""

import os
from typing import Any, Dict, List

from langchain_core.messages import BaseMessage, HumanMessage, RemoveMessage, trim_messages

from src.graph.compact import estimate_tokens
from src.graph.state import LegalAgentState

DEFAULT_HISTORY_TOKEN_BUDGET = int(os.getenv("HISTORY_TOKEN_BUDGET", "2000"))

# Luôn giữ NGUYÊN VĂN lượt hỏi-đáp gần nhất, kể cả khi nó một mình đã vượt ngân sách.
# Câu nối tiếp ("vậy còn xe máy thì sao?") chỉ hiểu được nhờ đúng cặp tin nhắn này; thay nó
# bằng bản tóm tắt là cách chắc chắn nhất để trả lời lạc đề.
MIN_KEEP_MESSAGES = 2

SUMMARY_WORD_LIMIT = 150


def count_tokens(messages: List[BaseMessage]) -> int:
    """Đếm token của một danh sách tin nhắn bằng chính bộ đếm mà node `compact` dùng."""
    total = 0
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
    return total


def summarize_dropped(dropped: List[BaseMessage], previous_summary: str = "") -> str:
    """
    Tóm tắt các lượt bị cắt thành <= 150 từ, gộp cả bản tóm tắt trước đó.

    Gộp bản cũ vào là bắt buộc: các lượt bị cắt bị xoá hẳn khỏi state, nên nếu bản tóm tắt
    trước không được mang theo thì ngữ cảnh xa sẽ biến mất sau đúng một lần nén.
    """
    transcript_parts: List[str] = []
    if previous_summary:
        transcript_parts.append(f"Tóm tắt trước đó: {previous_summary}")
    for msg in dropped:
        content = getattr(msg, "content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        role = "Người dùng" if isinstance(msg, HumanMessage) else "Trợ lý"
        transcript_parts.append(f"{role}: {content.strip()}")

    if not transcript_parts:
        return previous_summary

    transcript = "\n".join(transcript_parts)

    prompt = (
        "Tóm tắt đoạn hội thoại pháp luật giao thông dưới đây thành văn xuôi tiếng Việt, "
        f"tối đa {SUMMARY_WORD_LIMIT} từ. Chỉ giữ chủ đề đã hỏi, loại phương tiện và kết luận "
        "chính. KHÔNG bịa thêm số liệu, KHÔNG thêm trích dẫn Điều/Khoản không có trong đoạn.\n\n"
        f"{transcript}\n\nBản tóm tắt:"
    )

    try:
        from src.llm.provider import get_router_llm

        response = get_router_llm().invoke(prompt)
        summary = response.content if isinstance(response.content, str) else ""
        summary = summary.strip()
        if summary:
            return _limit_words(summary, SUMMARY_WORD_LIMIT)
    except Exception:
        # LLM tóm tắt hỏng không được phép làm hỏng câu trả lời: rơi về bản rút gọn tất định.
        pass

    return _limit_words(" | ".join(transcript_parts), SUMMARY_WORD_LIMIT)


def _limit_words(text: str, limit: int) -> str:
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit]) + "..."


def memory_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node `memory` (chạy ngay sau `normalize`): cắt lịch sử theo ngân sách token và tóm tắt
    phần bị cắt. Các tin nhắn bị cắt được gỡ hẳn khỏi state qua `RemoveMessage` để lượt sau
    không phải tóm tắt lại chúng lần nữa.
    """
    messages: List[BaseMessage] = list(state.get("messages", []) or [])
    previous_summary = state.get("history_summary", "") or ""

    if len(messages) <= MIN_KEEP_MESSAGES:
        return {"history_summary": previous_summary}

    budget = DEFAULT_HISTORY_TOKEN_BUDGET
    try:
        kept = trim_messages(
            messages,
            max_tokens=budget,
            strategy="last",
            token_counter=count_tokens,
            include_system=False,
            allow_partial=False,
        )
    except Exception:
        kept = messages[-MIN_KEEP_MESSAGES:]

    # `trim_messages` có thể cắt sạch khi một tin nhắn đơn lẻ đã vượt ngân sách.
    if len(kept) < MIN_KEEP_MESSAGES:
        kept = messages[-MIN_KEEP_MESSAGES:]

    kept_ids = {id(m) for m in kept}
    dropped = [m for m in messages if id(m) not in kept_ids]
    if not dropped:
        return {"history_summary": previous_summary}

    summary = summarize_dropped(dropped, previous_summary)

    removals = [RemoveMessage(id=m.id) for m in dropped if getattr(m, "id", None)]
    return {"messages": removals, "history_summary": summary}


def build_history_context_block(history_summary: str) -> str:
    """Khối ngữ cảnh hội thoại trước, chèn vào prompt bởi node `compact`."""
    if not history_summary or not history_summary.strip():
        return ""
    return (
        "[NGỮ CẢNH HỘI THOẠI TRƯỚC — chỉ để hiểu ý câu hỏi, KHÔNG phải căn cứ pháp lý]:\n"
        f"{history_summary.strip()}"
    )


__all__ = [
    "memory_node",
    "count_tokens",
    "summarize_dropped",
    "build_history_context_block",
    "DEFAULT_HISTORY_TOKEN_BUDGET",
    "MIN_KEEP_MESSAGES",
]
