"""
Node kiểm chứng tất định và node huỷ câu trả lời (Phase 5).

Đây là lý do duy nhất khiến model nhỏ không bịa được mức phạt, nên node ở đây KHÔNG
chứa logic kiểm chứng riêng: nó chỉ gom nguồn đối chiếu rồi gọi thẳng vào các hàm thuần
của `src/answer_guard.py` — bộ hàm đã được chứng minh đúng trên dữ liệu thật.

Điểm then chốt: đối chiếu với `raw_tool_output` NGUYÊN VĂN, không bao giờ với
`packed_context`. Node `compact` cắt bằng chứng để vừa ngân sách token của model; đem
bản đã cắt đi kiểm chứng sẽ sinh ra hàng loạt "số liệu không có căn cứ" giả.
"""

import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from src.answer_guard import (
    build_unknown_answer,
    find_invalid_citations,
    find_ungrounded_figures,
    is_uncertain_answer,
)
from src.graph.events import emit
from src.graph.sources import build_sources_from_evidence
from src.graph.state import LegalAgentState

MAX_REPAIR_ROUNDS = 1

# Câu trả lời trống — model không sinh ra nội dung nào (thường do reasoning ăn hết ngân sách
# token trước khi kịp sinh câu trả lời). Trống nguy hiểm hơn một câu trả lời sai vì người dùng
# không nhận được gì cả; PHẢI đi qua lại `repair`/`cancel` như mọi lỗi khác, không được lọt qua.
EMPTY_ANSWER_ISSUE = "câu trả lời trống — mô hình không sinh được nội dung"

# Câu trả lời né tránh trích dẫn cụ thể, chỉ viết mơ hồ kiểu "theo quy định của pháp luật hiện
# hành" dù dữ liệu tra cứu đã có sẵn Điều/Khoản/văn bản để chép lại nguyên văn. Đây là nguyên
# nhân phổ biến nhất khiến citation accuracy E2E thấp: nội dung đúng nhưng không có căn cứ.
MISSING_CITATION_ISSUE = "câu trả lời không nêu rõ Điều/Khoản hoặc văn bản pháp lý cụ thể đã dùng"

# Bất kỳ dấu hiệu nào cho thấy câu trả lời CÓ trích dẫn cụ thể (Điều/Khoản của Luật, hoặc tên
# Nghị định/Thông tư/QCVN/biển báo). Nếu không có dấu hiệu nào trong khi dữ liệu tra cứu có,
# câu trả lời coi như né tránh trích dẫn.
_CITATION_MARKER = re.compile(
    r'Điều\s*\d|Khoản\s*\d|Biển\s*[A-Za-zĐ0-9]|Nghị\s*định|Thông\s*tư|QCVN',
    re.IGNORECASE,
)


def find_missing_citation(answer: str, verified_sources: List[str]) -> List[str]:
    """
    Bắt trường hợp câu trả lời bàn đúng nội dung nhưng không chịu ghi số Điều/Khoản — kiểu
    "theo quy định của pháp luật hiện hành..." — trong khi dữ liệu tra cứu đã có sẵn căn cứ để
    chép lại. Bỏ qua khi câu trả lời trống (đã có `EMPTY_ANSWER_ISSUE` xử lý riêng), khi chính
    câu trả lời đã thành thật từ chối (`is_uncertain_answer`), hoặc khi dữ liệu tra cứu không
    hề có căn cứ nào để trích (không có gì đáng trách mô hình).
    """
    if not answer or not answer.strip():
        return []
    if is_uncertain_answer(answer):
        return []
    if _CITATION_MARKER.search(answer):
        return []

    grounded_text = "\n".join(s for s in verified_sources if s)
    if not _CITATION_MARKER.search(grounded_text):
        return []

    return [MISSING_CITATION_ISSUE]


def collect_verified_sources(state: LegalAgentState) -> List[str]:
    """
    Gom nguồn đối chiếu: bằng chứng nguyên văn của lượt này, cộng với câu trả lời đã qua
    kiểm chứng của các lượt trước.

    Vế thứ hai là bắt buộc: mọi câu trả lời của lượt trước đều đã đi qua đúng lớp kiểm chứng
    này trước khi tới người dùng. Thiếu chúng, một câu trả lời đúng cho câu hỏi nối tiếp
    ("vậy còn xe máy thì sao?") bị huỷ oan chỉ vì lượt này không gọi lại đúng công cụ cũ.
    """
    raw_evidence = [
        ev.get("raw_tool_output", "")
        for ev in state.get("evidence", [])
        if ev.get("raw_tool_output")
    ]
    prior_answers = [
        msg.content
        for msg in state.get("messages", [])
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content
    ]
    return raw_evidence + prior_answers


def verify_answer(answer: str, verified_sources: List[str]) -> List[str]:
    """
    Chạy song song ba lớp kiểm chứng tất định: câu trả lời trống, số liệu không căn cứ, và
    trích dẫn Điều/Khoản (kể cả trích dẫn sai lẫn trích dẫn bị né tránh/mơ hồ).

    Câu trả lời trống phải bị chặn ngay ở đây — nếu không, `not answer` khiến các hàm kiểm
    chứng phía dưới trả về `[]` (đúng bản chất "không có gì để kiểm"), và câu trả lời trống
    sẽ bị hiểu nhầm là "đã kiểm chứng, không có vấn đề" rồi lọt thẳng ra người dùng.
    """
    if not answer or not answer.strip():
        return [EMPTY_ANSWER_ISSUE]

    from src.graph.retrieve import get_traffic_law_tools

    tools = get_traffic_law_tools()
    return (
        find_ungrounded_figures(answer, verified_sources)
        + find_invalid_citations(
            answer,
            verified_sources,
            tools.articles_by_num,
            tools.road_law_articles,
        )
        + find_missing_citation(answer, verified_sources)
    )


def verify_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node `verify`: đối chiếu câu trả lời với bằng chứng nguyên văn, ghi `issues` vào state.
    Node này không tự quyết định đi đâu — việc đó thuộc cạnh có điều kiện `verify_router`.
    """
    answer = state.get("answer", "")
    repair_count = state.get("repair_count", 0)

    issues = verify_answer(answer, collect_verified_sources(state))

    if issues and repair_count < MAX_REPAIR_ROUNDS:
        emit(
            "verifying",
            f"🔎 {len(issues)} chi tiết không khớp dữ liệu tra cứu — đang yêu cầu Agent viết lại...",
        )
    elif not issues:
        # Phát `verified` cho MỌI câu trả lời sạch, không chỉ câu vừa phải sửa.
        #
        # Điều kiện cũ là `not issues and repair_count > 0`, nghĩa là ở đường đi thuận lợi —
        # câu trả lời đúng ngay từ đầu, tức đa số lượt — giao diện không nhận được tín hiệu nào
        # cho thấy câu trả lời đã được đối chiếu với văn bản gốc. `static/js/agent-trace.js` có
        # sẵn nhánh xử lý và kiểu hiển thị cho `verified` mà không bao giờ nhận được sự kiện.
        # Kiểm chứng tất định là lớp phòng vệ quan trọng nhất của sản phẩm này; để nó vô hình
        # đúng lúc nó làm việc tốt là bỏ phí tín hiệu tin cậy đáng giá nhất với người dùng.
        emit(
            "verified",
            "✅ Đã loại bỏ chi tiết không có căn cứ khỏi câu trả lời"
            if repair_count > 0
            else "✅ Đã đối chiếu số liệu và trích dẫn với văn bản gốc",
        )

    return {"issues": issues}


def verify_router(state: LegalAgentState) -> str:
    """
    Cạnh có điều kiện sau `verify`. Chỉ có đúng ba lối ra và tối đa MAX_REPAIR_ROUNDS vòng sửa:
    không có đường đi nào cho phép lặp vô hạn.
    """
    if not state.get("issues"):
        return "build_sources"
    if state.get("repair_count", 0) < MAX_REPAIR_ROUNDS:
        return "repair"
    return "cancel"


def cancel_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node `cancel` (tất định, không gọi LLM): huỷ câu trả lời không vượt qua kiểm chứng và
    thay bằng lời từ chối trung thực.

    Một mức phạt sai nguy hiểm hơn nhiều so với việc nói "chưa biết": người dùng có thể
    hành động dựa trên con số đó và không có cách nào tự phát hiện nó bị bịa.
    """
    issues = state.get("issues", []) or []
    question = state.get("question", "")
    sources = state.get("sources") or build_sources_from_evidence(state.get("evidence", []))

    emit(
        "warning",
        f"⚠️ Đã huỷ câu trả lời vì chứa chi tiết không có trong dữ liệu tra cứu: {', '.join(issues)}",
    )

    return {
        "answer": build_unknown_answer(question, sources, issues),
        "sources": sources,
        "needs_search": True,
    }
