"""
Cấu trúc State luân chuyển qua các node của StateGraph.

Chỉ khai báo những trường mà đồ thị đang chạy thật sự đọc/ghi. Đồ thị hiện tại là một vòng
ReAct: `agent ⇄ tools → verify → (repair → verify | cancel) → build_sources → END`.
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class Evidence(TypedDict, total=False):
    """Một mục bằng chứng thu thập từ các công cụ tra cứu."""
    source: str
    parent_id: str
    doc_id: str
    citation: str
    header: str
    content: str
    snippet: str
    score: float
    image_path: Optional[str]
    raw_tool_output: str  # Dữ liệu nguyên văn để đối chiếu số liệu và căn cứ


class LegalAgentState(TypedDict, total=False):
    """
    Trạng thái luân chuyển qua các node trong StateGraph.

    - `messages`: dùng `add_messages` để quản lý lịch sử hội thoại
    - `evidence` / `agent_steps`: dùng `operator.add` làm reducer để nhiều tool call trong
      cùng một lượt ghi dồn an toàn thay vì ghi đè lẫn nhau
    """
    messages: Annotated[List[AnyMessage], add_messages]
    question: str
    grounding_query: str
    thread_id: str
    turn_count: int
    evidence: Annotated[List[Evidence], operator.add]
    agent_steps: Annotated[List[Dict[str, Any]], operator.add]
    answer: str
    issues: List[str]
    repair_count: int
    sources: List[Dict[str, Any]]
    model_used: str
    needs_search: bool
    search: Optional[Dict[str, Any]]
