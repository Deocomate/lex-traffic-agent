"""
Lắp ráp và biên dịch Đồ thị LangGraph StateGraph.

Khung kiến trúc (vòng ReAct đa lượt):
START -> agent -> (tools -> agent)* -> verify -> (repair -> verify | cancel)
      -> build_sources -> END.

Vòng sửa bị chặn cứng ở MAX_REPAIR_ROUNDS bằng `repair_count` trong state: không có đường đi
nào trong đồ thị cho phép quá một vòng `repair`.

Checkpointer SQLite: mỗi cuộc hội thoại là một `thread_id`, lịch sử sống qua F5 trình duyệt
và qua cả lần khởi động lại server.
"""

import atexit
import os
import sqlite3
import threading
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.graph.agent_node import agent_node, agent_router
from src.graph.retrieve import tools_node
from src.graph.repair import repair_node
from src.graph.sources import build_sources_node
from src.graph.state import LegalAgentState
from src.graph.verify import cancel_node, verify_node, verify_router
from src.observability.langsmith import configure_langsmith
from src.observability.tracer import new_run_tracer

_compiled_graph = None
_checkpointer_conn: sqlite3.Connection | None = None
_checkpointer: SqliteSaver | None = None
_build_lock = threading.Lock()

# Lưới an toàn thứ hai bên cạnh `repair_count`: kể cả khi state ghi hỏng, đồ thị vẫn dừng.
RECURSION_LIMIT = 25


def build_run_config(thread_id: str = "") -> dict:
    """
    Cấu hình cho một lượt chạy đồ thị: gắn tracer quan trắc, chặn đệ quy, và chọn
    `thread_id` cho checkpointer.

    Mỗi lượt chạy có một tracer riêng (một `run_id`), nên các lượt chạy song song trong bộ
    eval không trộn số liệu của nhau. LangSmith chỉ bật khi biến môi trường yêu cầu.
    """
    configure_langsmith()

    # Checkpointer của Phase 6 bắt buộc phải có `thread_id`. Lượt chạy không nêu thread
    # (CLI, bộ eval) được cấp một thread dùng một lần, để nó không đọc nhầm lịch sử của
    # cuộc hội thoại khác mà vẫn chạy được qua checkpointer.
    resolved_thread = thread_id or f"anon-{uuid.uuid4().hex[:16]}"
    return {
        "recursion_limit": RECURSION_LIMIT,
        "callbacks": [new_run_tracer(thread_id=resolved_thread)],
        "configurable": {"thread_id": resolved_thread},
    }


def _default_checkpoint_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "data", "runtime", "checkpoints.sqlite")


def get_checkpointer() -> SqliteSaver | None:
    """
    Checkpointer SQLite đồng bộ dùng chung.

    Dùng bản đồng bộ chứ không phải `AsyncSqliteSaver` vì đồ thị được chạy bằng `graph.invoke()`
    trong một worker thread ở CẢ hai façade của `src/agent.py` (bản sync lẫn bản async) — bản
    async đòi `ainvoke` và sẽ không bao giờ được gọi tới.

    `check_same_thread=False` + WAL là điều kiện bắt buộc: worker thread tạo mỗi lượt hỏi là một
    luồng khác với luồng đã mở kết nối, và WAL cho phép đọc/ghi đồng thời thay vì ném
    "database is locked" trên Windows.

    Trả về đúng MỘT thể hiện `SqliteSaver`: chính nó giữ `threading.Lock` bảo vệ kết nối, nên
    hai thể hiện dùng chung một kết nối sẽ có hai khoá độc lập và mất hẳn tác dụng tuần tự hoá
    khi nhiều request tới cùng lúc.
    """
    global _checkpointer_conn, _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    try:
        path = os.getenv("CHECKPOINT_DB_PATH") or _default_checkpoint_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _checkpointer_conn is None:
            _checkpointer_conn = sqlite3.connect(path, timeout=15.0, check_same_thread=False)
            _checkpointer_conn.execute("PRAGMA journal_mode=WAL;")
            _checkpointer_conn.execute("PRAGMA synchronous=NORMAL;")
            atexit.register(close_checkpointer)
        # Không còn model Pydantic nào đi vào state, nên checkpoint chỉ chứa các kiểu nằm
        # trong danh sách cho phép mặc định của msgpack — không cần khai báo allowlist riêng.
        _checkpointer = SqliteSaver(_checkpointer_conn)
        return _checkpointer
    except Exception as e:
        # Không có checkpointer thì mất bộ nhớ đa lượt, nhưng vẫn trả lời được câu hỏi hiện tại.
        print(f"[Graph] Không khởi tạo được checkpointer, chạy không bộ nhớ bền: {e}")
        return None


def close_checkpointer() -> None:
    """Đóng kết nối checkpointer gọn gàng khi tắt server."""
    global _checkpointer_conn, _checkpointer, _compiled_graph
    _checkpointer = None
    if _checkpointer_conn is not None:
        try:
            _checkpointer_conn.close()
        except Exception:
            pass
        _checkpointer_conn = None
        _compiled_graph = None


def create_legal_graph():
    """Xây dựng và biên dịch đồ thị xử lý câu hỏi pháp lý LexTraffic AI theo cơ chế Agentic ReAct đa vòng."""
    workflow = StateGraph(LegalAgentState)

    # 1. Thêm các Node
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("repair", repair_node)
    workflow.add_node("cancel", cancel_node)
    workflow.add_node("build_sources", build_sources_node)

    # 2. Thêm các Cạnh (Edges)
    workflow.add_edge(START, "agent")

    # Phân nhánh từ agent: gọi tools nếu có tool call, hoặc sang verify nếu đã có câu trả lời
    workflow.add_conditional_edges(
        "agent",
        agent_router,
        {
            "tools": "tools",
            "verify": "verify",
        },
    )

    # Cạnh vòng lặp từ tools quay lại agent để Agent xem kết quả và suy luận vòng tiếp theo
    workflow.add_edge("tools", "agent")

    # Lớp phòng vệ tất định: kiểm chứng -> sửa tối đa 1 vòng -> huỷ nếu vẫn sai
    workflow.add_conditional_edges(
        "verify",
        verify_router,
        ["repair", "cancel", "build_sources"],
    )
    workflow.add_edge("repair", "verify")
    workflow.add_edge("cancel", "build_sources")
    workflow.add_edge("build_sources", END)

    return workflow.compile(checkpointer=get_checkpointer())


def get_legal_graph():
    """Lấy singleton instance của đồ thị đã biên dịch."""
    global _compiled_graph
    if _compiled_graph is None:
        with _build_lock:
            if _compiled_graph is None:
                _compiled_graph = create_legal_graph()
    return _compiled_graph
