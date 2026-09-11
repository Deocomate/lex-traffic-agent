"""
Định nghĩa cấu trúc State cho Đồ thị LangGraph (Phase 4).
Bao gồm bằng chứng (Evidence), quyết định định tuyến (RouteDecision),
và trạng thái xuyên suốt của phiên hỏi đáp (LegalAgentState).
"""

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class Evidence(TypedDict, total=False):
    """Một mục bằng chứng pháp lý thu thập từ các công cụ tra cứu."""
    source: Literal["penalty", "law", "sign", "speed"]
    parent_id: str
    doc_id: str
    citation: str
    header: str
    content: str
    snippet: str
    score: float
    image_path: Optional[str]
    raw_tool_output: str  # Dữ liệu nguyên văn để đối chiếu số liệu và căn cứ


class RouteDecision(BaseModel):
    """Quyết định định tuyến truy xuất tài liệu từ regex và LLM."""
    intents: List[Literal["penalty", "law", "sign", "speed"]] = Field(
        default_factory=list,
        description="Các mục đích tra cứu cần kích hoạt: penalty (mức phạt), law (điều luật), sign (biển báo/vạch kẻ), speed (tốc độ/cự ly)"
    )
    doc_scope: Literal["all", "luat", "nghi_dinh", "thong_tu", "quy_chuan"] = Field(
        default="all",
        description="Phạm vi nhóm văn bản cần tra cứu"
    )
    vehicles: List[Literal["o_to", "xe_may", "xe_dap", "khac"]] = Field(
        default_factory=list,
        description="Nhóm phương tiện liên quan đến câu hỏi"
    )
    search_query: str = Field(
        default="",
        description="Truy vấn tìm kiếm cốt lõi đã được tối ưu hóa"
    )


class LegalAgentState(TypedDict, total=False):
    """
    Trạng thái luân chuyển qua các node trong StateGraph của LexTraffic AI.
    - evidence: sử dụng operator.add làm reducer để các node truy xuất song song ghi dồn an toàn
    - agent_steps: sử dụng operator.add để ghi nhận các bước thực thi công cụ
    - messages: sử dụng add_messages để quản lý lịch sử hội thoại
    """
    messages: Annotated[List[AnyMessage], add_messages]
    question: str
    grounding_query: str
    history_summary: str
    thread_id: str
    turn_count: int
    route: RouteDecision
    evidence: Annotated[List[Evidence], operator.add]
    reranked_evidence: List[Evidence]
    agent_steps: Annotated[List[Dict[str, Any]], operator.add]
    packed_context: str
    answer: str
    issues: List[str]
    repair_count: int
    sources: List[Dict[str, Any]]
    model_used: str
    needs_search: bool
    search: Optional[Dict[str, Any]]
