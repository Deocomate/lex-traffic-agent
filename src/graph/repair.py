"""
Node tự sửa câu trả lời (Phase 5).

Cho mô hình đúng MỘT cơ hội viết lại sau khi bị chỉ đích danh những số liệu và trích dẫn
Điều/Khoản không đối chiếu được với dữ liệu tra cứu.

Chạy im lặng — không phát token ra giao diện — vì đây là bản nháp sửa lỗi; người dùng chỉ
nên thấy kết quả cuối cùng đã qua kiểm chứng. Chỉ phát `turn_start` (turn=2) để dòng thời
gian trace cho thấy đã có một lượt sửa.
"""

from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.events import emit
from src.graph.state import LegalAgentState
from src.graph.answer_text import clean_text_output, polish_answer
from src.graph.verify import EMPTY_ANSWER_ISSUE, MISSING_CITATION_ISSUE
from src.llm.provider import get_synthesize_llm
from src.prompts.system_vi import get_system_prompt_vi

# Chỉ dẫn sửa cho lỗi "chi tiết không khớp dữ liệu" (số liệu bịa, trích dẫn sai Khoản/Điều...).
MISMATCH_REPAIR_INSTRUCTION = (
    "KIỂM CHỨNG THẤT BẠI. Các chi tiết sau trong câu trả lời của bạn KHÔNG khớp với dữ liệu "
    "đã tra cứu: {issues}.\n"
    "Viết lại câu trả lời: bỏ hoặc sửa đúng những chi tiết đó, chỉ giữ nội dung có căn cứ "
    "trong dữ liệu tra cứu ở trên. Trích dẫn Điều/Khoản phải chép đúng như dữ liệu tra cứu "
    "ghi, không tự đổi số Khoản. Nhớ rằng Luật 36/2024/QH15 không quy định số tiền phạt, "
    "nên căn cứ của mức tiền luôn là Nghị định xử phạt. Nếu sau khi bỏ đi mà không còn đủ "
    "căn cứ, hãy nói thẳng 'Tôi chưa có dữ liệu về mức phạt cho trường hợp này'. "
    "TUYỆT ĐỐI không thêm bất kỳ con số hay điều khoản mới nào."
)

# Chỉ dẫn sửa riêng cho lỗi né tránh trích dẫn: nội dung đúng nhưng không nêu số Điều/Khoản —
# đây là nguyên nhân phổ biến nhất khiến citation accuracy thấp, nên cần một chỉ dẫn đích danh
# thay vì gộp chung vào chỉ dẫn "chi tiết không khớp" (ở đây không có chi tiết nào sai cả, chỉ
# thiếu trích dẫn).
MISSING_CITATION_REPAIR_INSTRUCTION = (
    "KIỂM CHỨNG THẤT BẠI: câu trả lời trước đó của bạn KHÔNG nêu rõ số Điều/Khoản hoặc tên văn "
    "bản pháp lý cụ thể — chỉ viết chung chung kiểu 'theo quy định của pháp luật hiện hành'. "
    "Viết lại câu trả lời: giữ nguyên nội dung đúng, nhưng ngay TRONG PHẦN NỘI DUNG trả lời "
    "(không chỉ ở khối trích dẫn cuối cùng), nêu đích danh số Điều (và số Khoản nếu có) đúng "
    "NGUYÊN VĂN như dữ liệu tra cứu ở trên ghi. TUYỆT ĐỐI không tự suy diễn số Điều/Khoản; nếu "
    "không xác định được Điều nào phù hợp trong dữ liệu tra cứu, hãy nói thẳng 'Tôi chưa có dữ "
    "liệu về quy định cho trường hợp này' thay vì viết mơ hồ."
)

# Chỉ dẫn sửa riêng cho câu trả lời trống (model không sinh nội dung ở lượt trước).
EMPTY_ANSWER_REPAIR_INSTRUCTION = (
    "Lượt trước bạn KHÔNG sinh ra câu trả lời nào (trống). Hãy trả lời lại từ đầu: đi thẳng "
    "vào trọng tâm câu hỏi, dựa hoàn toàn vào dữ liệu tra cứu ở trên, nêu rõ số Điều/Khoản đã "
    "dùng, và trả lời trọn vẹn — không dừng câu dở dang."
)


def _build_repair_instruction(issues: List[str]) -> str:
    """
    Ghép chỉ dẫn sửa khớp với từng loại lỗi mà `verify` bắt được, để lượt sửa DUY NHẤT nhắm
    đúng nguyên nhân thay vì một câu nhắc chung chung không đủ cụ thể để mô hình nhỏ sửa đúng.
    """
    blocks: List[str] = []
    other_issues = [i for i in issues if i not in (EMPTY_ANSWER_ISSUE, MISSING_CITATION_ISSUE)]

    if EMPTY_ANSWER_ISSUE in issues:
        blocks.append(EMPTY_ANSWER_REPAIR_INSTRUCTION)
    if MISSING_CITATION_ISSUE in issues:
        blocks.append(MISSING_CITATION_REPAIR_INSTRUCTION)
    if other_issues:
        blocks.append(MISMATCH_REPAIR_INSTRUCTION.format(issues=", ".join(other_issues)))

    return "\n\n".join(blocks)


def build_repair_messages(state: LegalAgentState) -> List[Any]:
    """Dựng bộ tin nhắn cho lượt sửa: cùng ngữ cảnh bằng chứng, cộng chỉ dẫn sửa đích danh."""
    issues = state.get("issues", []) or []
    previous_answer = state.get("answer", "") or "(trống — không có nội dung)"

    evidence_texts = [
        ev.get("raw_tool_output", "") for ev in state.get("evidence", []) if ev.get("raw_tool_output")
    ]
    context_text = state.get("packed_context", "") or "\n\n".join(evidence_texts)

    return [
        SystemMessage(content=get_system_prompt_vi()),
        HumanMessage(
            content=(
                f"Dựa trên các tài liệu và dữ liệu pháp luật đã tra cứu dưới đây:\n\n"
                f"{context_text}\n\n"
                f"Câu hỏi của người dùng: \"{state.get('question', '')}\""
            )
        ),
        HumanMessage(
            content=(
                f"Câu trả lời trước đó của bạn:\n\n{previous_answer}\n\n"
                + _build_repair_instruction(issues)
            )
        ),
    ]


def repair_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node `repair`: viết lại câu trả lời một lần duy nhất và tăng `repair_count`.

    `repair_count` luôn được tăng kể cả khi lượt sửa thất bại — nếu không, cạnh có điều kiện
    sau `verify` sẽ quay lại đây mãi mãi.
    """
    emit("turn_start", "🔁 Đang viết lại câu trả lời theo đúng dữ liệu đã tra cứu...", turn=2)

    repaired = ""
    try:
        response = get_synthesize_llm().invoke(build_repair_messages(state))
        content = response.content if isinstance(response.content, str) else ""
        repaired = polish_answer(clean_text_output(content))
    except Exception as err:
        emit("error", f"Không thể viết lại câu trả lời: {err}")

    return {
        # Sửa hỏng thì giữ nguyên câu cũ để `verify` bắt lại và đưa sang `cancel`
        "answer": repaired or state.get("answer", ""),
        "repair_count": state.get("repair_count", 0) + 1,
    }
