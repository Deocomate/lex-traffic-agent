"""
Node `tools` của đồ thị: thực thi các tool call do Agent phát ra.

Module này KHÔNG biết công cụ nào tồn tại. Nó tra Domain Pack đang hoạt động để lấy hàm thực
thi theo tên, gọi, rồi chuyển kết quả thành `Evidence` và phát sự kiện cho giao diện theo dõi
tiến trình.

Trước đây đây là một chuỗi `if tool_name == "penalty_lookup" ... elif "traffic_sign_lookup" ...`
dài 200 dòng, mỗi nhánh gắn cứng doc_id của một văn bản giao thông. Thêm một công cụ hay đổi
sang lĩnh vực khác đều phải sửa chính tệp này. Giờ engine chỉ còn cơ chế; danh sách công cụ,
cách mô tả và cách dựng bằng chứng đều do pack khai báo.

Miền không khai báo gì thêm vẫn chạy được: engine dựng một `Evidence` chung từ nguyên văn kết
quả công cụ.
"""

import logging
import uuid
from typing import Any, Dict, List, Tuple

from langchain_core.messages import ToolMessage

from src.graph.events import emit
from src.graph.state import Evidence, LegalAgentState

logger = logging.getLogger(__name__)


def _domain():
    from src.domain.registry import get_active_domain

    return get_active_domain()


# =====================================================================
# Diễn đạt tiến trình cho người dùng
# =====================================================================

def format_tool_explanation(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Mô tả mục đích của một lượt gọi công cụ.

    Ưu tiên hàm mà pack khai báo ở `presentation.describe_call`; không có thì dựng một câu mô
    tả chung từ tên công cụ và tham số — đủ dùng cho miền mới chưa kịp viết phần trình bày.
    """
    try:
        describe = _domain().describe_call
        if describe is not None:
            text = describe(tool_name=tool_name, args=args)
            if text:
                return text
    except Exception:
        logger.debug("Pack không mô tả được lượt gọi '%s', dùng bản chung", tool_name)

    shown = ", ".join(f"{k}={v!r}" for k, v in args.items() if v not in ("", None))
    return f"Tra cứu bằng công cụ `{tool_name}`" + (f" với {shown}" if shown else "")


def summarize_tool_result(tool_name: str, result_text: str) -> str:
    """Tóm tắt ngắn kết quả công cụ để giao diện trace hiển thị."""
    if not result_text:
        return "Không có dữ liệu trả về."

    try:
        summarize = _domain().summarize_result
        if summarize is not None:
            text = summarize(tool_name=tool_name, raw_output=result_text)
            if text:
                return text
    except Exception:
        logger.debug("Pack không tóm tắt được kết quả '%s', dùng bản chung", tool_name)

    return "Đã thu thập dữ liệu thành công."


# =====================================================================
# Thực thi tool call
# =====================================================================

def _generic_evidence(tool_name: str, raw_output: str) -> List[Evidence]:
    """
    Bằng chứng mặc định khi miền không khai báo `evidence_builder` cho công cụ.

    Giữ nguyên văn kết quả trong `raw_tool_output` là điều kiện BẮT BUỘC: node `verify` đối
    chiếu từng con số trong câu trả lời với đúng trường này. Thiếu nó thì lớp kiểm chứng tất
    định mất căn cứ và mô hình bịa số mà không ai bắt được.
    """
    if not raw_output:
        return []
    return [{
        "source": tool_name,
        "parent_id": f"{tool_name}_raw",
        "doc_id": "",
        "citation": "",
        "header": f"Kết quả tra cứu: {tool_name}",
        "content": raw_output,
        "snippet": raw_output[:250],
        "score": 0.5,
        "image_path": None,
        "raw_tool_output": raw_output,
    }]


def execute_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    turn: int = 1,
) -> Tuple[str, List[Evidence], Dict[str, Any]]:
    """
    Thực thi một tool call do Agent phát ra: phát sự kiện SSE, gọi handler của miền, dựng
    `Evidence` và ghi nhận bước thực thi.
    """
    desc = format_tool_explanation(tool_name, args)
    step = {"turn": turn, "action": tool_name, "args": args, "description": desc}
    emit("tool_call", f"🛠️ {desc}", **step)

    domain = _domain()
    handler = domain.tool_handlers.get(tool_name)

    if handler is None:
        raw_output = (
            f"Công cụ '{tool_name}' không tồn tại trong miền '{domain.id}'. "
            f"Các công cụ hiện có: {', '.join(domain.tool_names())}."
        )
        evidences: List[Evidence] = []
    else:
        try:
            raw_output = handler(**args) or ""
        except Exception as e:
            logger.warning("Công cụ '%s' lỗi: %s", tool_name, e)
            raw_output = f"Lỗi khi chạy công cụ '{tool_name}': {e}"

        evidences = _build_evidence(domain, tool_name, args, raw_output)

    summary = summarize_tool_result(tool_name, raw_output)
    step["summary"] = summary
    emit("tool_result", f"📥 {summary}", turn=turn, action=tool_name, summary=summary)

    return raw_output, evidences, step


def _build_evidence(domain, tool_name: str, args: Dict[str, Any], raw_output: str) -> List[Evidence]:
    """Dựng bằng chứng: ưu tiên builder của miền, rơi về bản chung khi thiếu hoặc lỗi."""
    builder = domain.evidence_builders.get(tool_name)
    if builder is None:
        return _generic_evidence(tool_name, raw_output)

    try:
        evidences = builder(args=args, raw_output=raw_output) or []
    except Exception as e:
        logger.warning("Builder bằng chứng của '%s' lỗi (%s), dùng bản chung", tool_name, e)
        return _generic_evidence(tool_name, raw_output)

    # Builder trả rỗng vẫn phải có bằng chứng nguyên văn, nếu không `verify` mất căn cứ đối chiếu.
    return evidences or _generic_evidence(tool_name, raw_output)


def tools_node(state: LegalAgentState) -> Dict[str, Any]:
    """Thực thi toàn bộ tool call mà Agent yêu cầu trong lượt này."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    tool_calls = getattr(messages[-1], "tool_calls", None) or []
    if not tool_calls:
        return {}

    turn = state.get("turn_count", 1)
    new_messages = []
    new_evidences: List[Evidence] = []
    new_steps: List[Dict[str, Any]] = []

    for call in tool_calls:
        tool_name = call.get("name", "")
        tool_args = call.get("args") or {}
        tool_call_id = call.get("id") or str(uuid.uuid4())

        raw_output, evidences, step = execute_tool_call(tool_name, tool_args, turn=turn)

        new_messages.append(ToolMessage(content=raw_output, tool_call_id=tool_call_id, name=tool_name))
        new_evidences.extend(evidences)
        new_steps.append(step)

    return {
        "messages": new_messages,
        "evidence": new_evidences,
        "agent_steps": new_steps,
    }
