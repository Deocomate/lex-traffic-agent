"""
Lớp Adapter hợp nhất cho Bộ công cụ Đánh giá (Evaluation Adapters)
Chuẩn hóa giao diện giao tiếp giữa Benchmark Runner và Agent:
- GraphAdapter: Bọc đồ thị LangGraph mới (src/graph/build.py)

Lưu ý: LegacyAdapter (bọc vòng lặp ReAct cũ src/agentic_rag.py) đã bị xoá ở Phase 8
cùng với toàn bộ src/agentic_rag.py. Baseline đo trên harness cũ đã được chốt lại tại
scripts/eval/baselines/baseline-legacy-260909.json để đối chiếu hồi quy, không cần
chạy lại mã cũ.
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)


class BaseAgentAdapter:
    """Giao diện trừu tượng cho Agent Runner"""

    def run(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Chạy một lượt hỏi đáp.
        Kết quả trả về dictionary chuẩn hóa chứa:
        - answer: str
        - sources: List[str]
        - agent_steps: List[Dict[str, Any]]
        - verification_issues: List[str]
        - needs_search: bool
        - search: Optional[Dict[str, Any]]
        - latency_ms: float
        - tokens_in: int
        - tokens_out: int
        - raw_tool_outputs: List[str]
        """
        raise NotImplementedError


def get_adapter(adapter_type: str = "graph", **kwargs) -> BaseAgentAdapter:
    """Factory khởi tạo adapter phù hợp theo tham số dòng lệnh"""
    norm_type = adapter_type.strip().lower()
    if norm_type == "legacy":
        raise NotImplementedError(
            "LegacyAdapter đã bị gỡ bỏ ở Phase 8 cùng với src/agentic_rag.py (harness ReAct thủ công cũ). "
            "Dùng adapter_type='graph' để chạy trên đồ thị LangGraph hiện hành. "
            "Chỉ số baseline đã đo trên harness cũ được lưu lại tại "
            "scripts/eval/baselines/baseline-legacy-260909.json — dùng file đó để đối chiếu hồi quy "
            "thay vì chạy lại mã cũ."
        )
    elif norm_type == "graph":
        from src.graph.adapter import GraphAdapter
        return GraphAdapter(**kwargs)
    else:
        raise ValueError(f"Loại adapter không hợp lệ: '{adapter_type}'. Chọn 'graph' (hoặc 'legacy' để xem lỗi hướng dẫn).")
