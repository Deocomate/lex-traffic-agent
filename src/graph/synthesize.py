"""
Node Tổng Hợp Câu Trả Lời (Synthesize Node) trong LangGraph.
Gọi get_synthesize_llm() KHÔNG BIND BẤT KỲ TOOL NÀO.
Bảo đảm:
- Model không thể phát sinh tool call hỏng hay lặp vô hạn
- Loại bỏ hoàn toàn mã xử lý DSML / tool call thừa
- Stream token ra SSE và emit sự kiện synthesizing / token / answer_commit
- Bàn giao việc kiểm chứng, dựng nguồn và phát sự kiện `done` cho Phase 5.
"""

import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.graph.events import emit
from src.graph.sources import build_sources_from_evidence  # noqa: F401  (tương thích ngược)
from src.graph.state import LegalAgentState
from src.llm.provider import get_model_tracker, get_synthesize_llm
from src.prompts.system_vi import get_system_prompt_vi

# Tên kỹ thuật của công cụ -> ngôn ngữ thường (phòng ngừa model nhắc tên)
TOOL_NAME_ALIASES = {
    "penalty_lookup": "tra cứu mức phạt",
    "traffic_sign_lookup": "tra cứu biển báo giao thông",
    "speed_limit_lookup": "tra cứu quy định tốc độ",
    "keyword_search": "tra cứu từ khóa điều luật",
    "semantic_search": "tra cứu ngữ nghĩa điều luật",
    "get_article": "đọc toàn văn điều luật",
    "list_chapters": "tra cứu mục lục chương",
}


def clean_text_output(text: str) -> str:
    """Loại bỏ các thẻ mã nội bộ của LLM (DSML, XML tool tags) nếu có."""
    if not text:
        return ""
    for tool_name, alias in TOOL_NAME_ALIASES.items():
        text = re.sub(rf'`?\b{tool_name}\b`?', alias, text)
    text = re.sub(r'<｜DSML｜tool_calls>.*?</｜DSML｜tool_calls>', '', text, flags=re.DOTALL)
    text = re.sub(r'<｜DSML｜[^>]+>', '', text)
    text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL)
    text = re.sub(r'<tool_call>.*', '', text, flags=re.DOTALL)
    text = re.sub(r'<\|.*?\|>', '', text)
    return text.strip()


def polish_answer(text: str) -> str:
    """Loại bỏ các câu râu ria nội bộ ở đầu câu và chuẩn hóa chữ viết hoa đầu dòng."""
    if not text:
        return ""

    for pattern, replacement in (
        (r'^\s*theo dữ liệu tra cứu (?:được )?(?:từ|trong|của)\s+', 'Theo '),
        (r'^\s*(?:dựa (?:trên|vào)|căn cứ)\s+(?:kết quả|dữ liệu)\s+tra cứu[^,:.\n]{0,70}[,:]\s*', ''),
        (r'^\s*kết quả tra cứu cho câu hỏi\s*"[^"\n]*"\s*cho thấy\s*', ''),
        (r'^\s*theo (?:kết quả|dữ liệu) tra cứu[,:]\s*', ''),
    ):
        new = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)
        if new != text:
            text = new
            break

    text = re.sub(r'[^.\n]*độ liên quan[^.\n]*\d+[.,]?\d*\s*%[^.\n]*\.\s*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'^.*CHỈ DẪN NỘI BỘ.*$\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = text.strip()

    match = re.search(r'[A-Za-zÀ-ỹ]', text)
    if match and text[match.start()].islower():
        i = match.start()
        text = text[:i] + text[i].upper() + text[i + 1:]
    return text


def synthesize_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node synthesize: Tạo câu trả lời pháp lý chất lượng cao.
    Không bind bất kỳ tool nào cho mô hình.
    """
    question = state.get("question", "")
    packed_context = state.get("packed_context", "")

    model = get_synthesize_llm()
    tracker = get_model_tracker(model)
    model_used = tracker.active_model if tracker and tracker.active_model else "deepseek/deepseek-chat"

    system_prompt = get_system_prompt_vi()

    user_prompt = (
        f"Dựa trên các tài liệu và dữ liệu pháp luật đã tra cứu dưới đây:\n\n"
        f"{packed_context}\n\n"
        f"Hãy trả lời câu hỏi sau của người dùng một cách chính xác, đầy đủ. BẮT BUỘC: ngay "
        f"trong PHẦN NỘI DUNG trả lời (không chỉ ở khối trích dẫn cuối cùng), nêu đích danh số "
        f"Điều (và số Khoản nếu có) đúng NGUYÊN VĂN như dữ liệu tra cứu ở trên ghi — TUYỆT ĐỐI "
        f"không viết mơ hồ kiểu 'theo quy định của pháp luật hiện hành' mà không kèm số Điều cụ "
        f"thể. Nếu dữ liệu tra cứu không có Điều nào phù hợp, nói thẳng 'Tôi chưa có dữ liệu về "
        f"quy định cho trường hợp này' thay vì viết chung chung:\n"
        f"\"{question}\""
    )

    prompt_messages: List[BaseMessage] = [
        SystemMessage(content=system_prompt),
    ]

    # Nạp lịch sử hội thoại trước đó (nếu có)
    existing_messages = state.get("messages", [])
    for msg in existing_messages:
        if isinstance(msg, (HumanMessage, AIMessage)):
            prompt_messages.append(msg)

    prompt_messages.append(HumanMessage(content=user_prompt))

    # Phát sự kiện bắt đầu tổng hợp
    emit("synthesizing", "✍️ Đã tra cứu xong. Đang tổng hợp lời giải đáp pháp lý...")

    # Gọi mô hình dạng streaming để phát token thời gian thực
    collected_tokens: List[str] = []
    try:
        for chunk in model.stream(prompt_messages):
            token_text = chunk.content if isinstance(chunk.content, str) else ""
            if token_text:
                collected_tokens.append(token_text)
                emit("token", token_text, phase="answer")
    except Exception as stream_err:
        # Fallback qua invoke thông thường nếu stream bị lỗi
        try:
            res = model.invoke(prompt_messages)
            content_res = res.content if isinstance(res.content, str) else str(res.content)
            collected_tokens = [content_res]
            emit("token", content_res, phase="answer")
        except Exception as e:
            emit("error", f"Lỗi khi tổng hợp câu trả lời: {e}")
            collected_tokens = [f"Đã xảy ra lỗi khi tạo câu trả lời: {e}"]

    raw_answer = "".join(collected_tokens)
    final_answer = polish_answer(clean_text_output(raw_answer))

    # Báo cho client chuyển văn bản sang ô câu trả lời
    emit("answer_commit", "", answer=final_answer)

    # Không ghi câu trả lời vào `messages` ở đây: nó chưa qua kiểm chứng. Node cuối đồ thị
    # chỉ đưa vào lịch sử hội thoại câu trả lời đã được `verify` chấp nhận.
    return {
        "answer": final_answer,
        "model_used": model_used,
        "repair_count": 0,
    }
