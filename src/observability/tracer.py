"""
Ghi trace JSONL cục bộ cho từng node và từng lệnh gọi LLM của đồ thị (Phase 7).

Mục tiêu hẹp và cụ thể: trả lời được câu hỏi "vì sao model nhỏ này trả lời sai câu đó"
mà không phải chạy lại và đoán.

Ghi qua hàng đợi + một luồng nền xả theo lô — đường chính (stream SSE) không bao giờ
phải chờ đĩa. Một dòng một sự kiện, không lồng nhau, nên vừa `grep` được vừa đọc bằng
một vòng lặp trong `scripts/eval/summarize_traces.py`.
"""

import atexit
import contextvars
import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler

from src.observability.pricing import estimate_cost_usd, estimate_tokens

logger = logging.getLogger(__name__)

DEFAULT_TRACE_DIR = os.path.join("data", "runtime", "traces")
DEFAULT_RETENTION_DAYS = 14
FLUSH_INTERVAL_SECONDS = 0.5
FLUSH_BATCH_SIZE = 64

# Đếm trúng/trượt cache theo từng lượt chạy. Dùng ContextVar để an toàn với cả luồng
# nền của stream_agent lẫn các lượt chạy song song trong bộ eval.
_cache_events_var: contextvars.ContextVar[Optional[List[bool]]] = contextvars.ContextVar(
    "trace_cache_events", default=None
)


# Tracer của lượt chạy hiện tại, để các lớp bên dưới (structured output, fallback model)
# ghi nhận sự kiện mà không phải nhận tham chiếu tracer qua chuỗi lời gọi.
_current_tracer_var: contextvars.ContextVar[Optional["JsonlTracer"]] = contextvars.ContextVar(
    "current_tracer", default=None
)


def get_trace_dir() -> str:
    """Thư mục ghi trace, đọc từ TRACE_DIR (mặc định data/runtime/traces)."""
    return (os.getenv("TRACE_DIR") or "").strip() or DEFAULT_TRACE_DIR


def get_retention_days() -> int:
    """Số ngày giữ tệp trace trước khi tự dọn."""
    try:
        return max(1, int(os.getenv("TRACE_RETENTION_DAYS") or DEFAULT_RETENTION_DAYS))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def record_cache_event(hit: bool) -> None:
    """
    Ghi nhận một lượt tra CACHE VECTOR TRUY VẤN (embedding) của lượt chạy hiện tại.

    Chỉ `src/retrieval/cache.py` gọi hàm này. Cache ngữ nghĩa câu trả lời
    (`src/cache/semantic_cache.py`) **không** ghi vào trace — nó có thống kê riêng qua
    `scripts/cache_admin.py --stats`. Đừng đọc `cache_hit` trong trace như tỉ lệ trúng cache
    câu trả lời: trúng cache câu trả lời nghĩa là đồ thị không chạy chút nào, còn trúng cache
    embedding chỉ nghĩa là tiết kiệm được một lần gọi API nhúng vector.
    """
    """
    Ghi nhận một lần tra cache trong lượt chạy hiện tại.
    Gọi từ các tầng có cache (cache vector truy vấn, cache ngữ nghĩa câu trả lời).
    """
    events = _cache_events_var.get()
    if events is not None:
        events.append(bool(hit))


def get_current_tracer() -> Optional["JsonlTracer"]:
    """Tracer của lượt chạy hiện tại, hoặc None khi đang chạy ngoài ngữ cảnh đồ thị."""
    return _current_tracer_var.get()


def record_structured_tier(tier: int, schema_name: str) -> None:
    """
    Ghi nhận tầng structured output vừa dùng.

    `structured_tier` là chỉ số cảnh báo sớm rẻ nhất khi đổi sang một model nhỏ mới: model
    luôn rơi xuống tầng 3 là model sẽ định tuyến kém, và biết được điều đó TRƯỚC khi thấy
    hậu quả trong chất lượng câu trả lời.
    """
    tracer = _current_tracer_var.get()
    if tracer is not None:
        tracer.log_event("structured_call", "structured_call", structured_tier=tier,
                         extra={"schema": schema_name})


def record_model_fallback(primary_model: str, active_model: str) -> None:
    """Ghi nhận một lần chuyển sang model dự phòng trong lượt chạy hiện tại."""
    tracer = _current_tracer_var.get()
    if tracer is not None:
        tracer.log_event("provider", "model_fallback", model=active_model,
                         extra={"primary_model": primary_model})


class TraceWriter:
    """
    Luồng nền ghi JSONL theo lô, xoay vòng tệp theo ngày và tự dọn tệp quá hạn.

    Hàng đợi không chặn: khi đầy thì bỏ sự kiện chứ không làm chậm đường chính —
    mất một dòng trace luôn rẻ hơn làm giật stream của người dùng.
    """

    def __init__(self, trace_dir: Optional[str] = None, max_queue: int = 10_000):
        self.trace_dir = trace_dir or get_trace_dir()
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_date: Optional[str] = None
        self._lock = threading.Lock()
        self.dropped = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        os.makedirs(self.trace_dir, exist_ok=True)
        self._purge_expired()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="trace-writer", daemon=True)
        self._thread.start()

    def write(self, record: Dict[str, Any]) -> None:
        """Đẩy một sự kiện vào hàng đợi. Không bao giờ chặn."""
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def _current_path(self) -> str:
        day = datetime.now().strftime("%Y-%m-%d")
        if day != self._current_date:
            self._current_date = day
            self._purge_expired()
        return os.path.join(self.trace_dir, f"trace-{day}.jsonl")

    def _purge_expired(self) -> None:
        """Xoá tệp trace cũ hơn TRACE_RETENTION_DAYS."""
        cutoff = datetime.now() - timedelta(days=get_retention_days())
        try:
            for name in os.listdir(self.trace_dir):
                if not (name.startswith("trace-") and name.endswith(".jsonl")):
                    continue
                try:
                    stamp = datetime.strptime(name[len("trace-"):-len(".jsonl")], "%Y-%m-%d")
                except ValueError:
                    continue
                if stamp < cutoff:
                    os.remove(os.path.join(self.trace_dir, name))
        except OSError as err:
            logger.debug("Không dọn được tệp trace cũ: %s", err)

    def _drain(self, block: bool) -> List[Dict[str, Any]]:
        batch: List[Dict[str, Any]] = []
        try:
            if block:
                batch.append(self._queue.get(timeout=FLUSH_INTERVAL_SECONDS))
            while len(batch) < FLUSH_BATCH_SIZE:
                batch.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        return batch

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        if not batch:
            return
        with self._lock:
            try:
                os.makedirs(self.trace_dir, exist_ok=True)
                with open(self._current_path(), "a", encoding="utf-8") as fh:
                    for record in batch:
                        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as err:
                logger.debug("Không ghi được trace: %s", err)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._write_batch(self._drain(block=True))
        # Xả nốt phần còn lại khi dừng
        while True:
            batch = self._drain(block=False)
            if not batch:
                break
            self._write_batch(batch)

    def flush(self, timeout: float = 3.0) -> None:
        """Chờ hàng đợi rỗng — dùng trong test và trước khi thoát tiến trình."""
        deadline = time.time() + timeout
        while not self._queue.empty() and time.time() < deadline:
            time.sleep(0.02)
        self._write_batch(self._drain(block=False))

    def stop(self, timeout: float = 3.0) -> None:
        self.flush(timeout=timeout)
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


_writer: Optional[TraceWriter] = None
_writer_lock = threading.Lock()


def get_writer() -> TraceWriter:
    """Singleton luồng ghi trace của tiến trình."""
    global _writer
    with _writer_lock:
        if _writer is None:
            _writer = TraceWriter()
            _writer.start()
        return _writer


def shutdown_tracing() -> None:
    """Xả và dừng luồng ghi trace."""
    global _writer
    with _writer_lock:
        if _writer is not None:
            _writer.stop()
            _writer = None


atexit.register(shutdown_tracing)


class JsonlTracer(BaseCallbackHandler):
    """
    Callback handler ghi một dòng JSONL cho mỗi node của đồ thị và mỗi lệnh gọi LLM.

    Một instance ứng với một lượt chạy (một `run_id`), nên các lượt chạy song song trong
    bộ eval không trộn lẫn số liệu của nhau.
    """

    def __init__(
        self,
        run_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        writer: Optional[TraceWriter] = None,
    ):
        super().__init__()
        self.run_id = run_id or uuid.uuid4().hex[:16]
        self.thread_id = thread_id or ""
        self.writer = writer or get_writer()
        self._node_starts: Dict[str, Dict[str, Any]] = {}
        self._llm_starts: Dict[str, Dict[str, Any]] = {}
        self._cache_events: List[bool] = []
        _cache_events_var.set(self._cache_events)
        _current_tracer_var.set(self)

    # ------------------------------------------------------------------
    # Tiện ích
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")

    @staticmethod
    def _node_name(kwargs: Dict[str, Any]) -> Optional[str]:
        """
        Tên node LangGraph lấy từ metadata; None nghĩa là chain nội bộ, không đáng ghi.

        Chỉ dùng được ở callback *_start: LangGraph không truyền `metadata` cho
        `on_chain_end`/`on_chain_error`, nên phía kết thúc phải tra lại tên node theo
        `run_id` đã ghi lúc bắt đầu.
        """
        metadata = kwargs.get("metadata") or {}
        return metadata.get("langgraph_node")

    @staticmethod
    def _is_graph_step(kwargs: Dict[str, Any]) -> bool:
        """
        Phân biệt node thật với runnable của cạnh có điều kiện.

        Cả hai đều mang cùng `langgraph_node` trong metadata, nhưng node thật được gắn thẻ
        `graph:step:N` còn hàm rẽ nhánh mang `seq:step:N`. Không lọc thì `route` và `verify`
        — đúng hai node có `add_conditional_edges` — bị đếm hai lần và p50 của chúng bị trộn
        với thời gian chạy hàm rẽ nhánh.
        """
        return any(str(tag).startswith("graph:step:") for tag in (kwargs.get("tags") or []))

    def _emit(self, **fields: Any) -> None:
        record = {
            "run_id": self.run_id,
            "thread_id": self.thread_id,
            "node": None,
            "event": None,
            "t_start": self._now_iso(),
            "duration_ms": None,
            "model": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "cache_hit": None,
            "structured_tier": None,
            "error": None,
            "extra": {},
        }
        record.update(fields)
        self.writer.write(record)

    def cache_hit_rate(self) -> Optional[float]:
        """Tỉ lệ trúng cache của lượt chạy này; None khi lượt này không tra cache lần nào."""
        if not self._cache_events:
            return None
        return sum(1 for hit in self._cache_events if hit) / len(self._cache_events)

    # ------------------------------------------------------------------
    # Node của đồ thị
    # ------------------------------------------------------------------

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Any, **kwargs: Any) -> None:
        node = self._node_name(kwargs)
        if not node or not self._is_graph_step(kwargs):
            return
        self._node_starts[str(kwargs.get("run_id", node))] = {
            "t0": time.perf_counter(),
            "cache_mark": len(self._cache_events),
            "node": node,
        }

    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        started = self._node_starts.pop(str(kwargs.get("run_id", "")), None)
        if started is None:
            return  # Chain nội bộ, không phải node của đồ thị
        node = started["node"]
        t0 = started.get("t0")

        # Node này có tra cache lần nào không; None nghĩa là không tra, khác hẳn với "tra và trượt"
        during = self._cache_events[started.get("cache_mark", len(self._cache_events)):]
        self._emit(
            node=node,
            event="node_end",
            duration_ms=None if t0 is None else round((time.perf_counter() - t0) * 1000, 2),
            cache_hit=any(during) if during else None,
            extra=self._node_extra(node, outputs),
        )

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        started = self._node_starts.pop(str(kwargs.get("run_id", "")), None)
        if started is None:
            return
        node = started["node"]
        t0 = started.get("t0")
        self._emit(
            node=node,
            event="node_error",
            duration_ms=None if t0 is None else round((time.perf_counter() - t0) * 1000, 2),
            error=f"{type(error).__name__}: {error}",
        )

    @staticmethod
    def _node_extra(node: str, outputs: Any) -> Dict[str, Any]:
        """
        Trường theo ngữ cảnh của từng node — phần đắt giá nhất khi truy nguyên một câu sai:
        đã định tuyến đi đâu, rerank cắt bao nhiêu ứng viên, kiểm chứng bắt được bao nhiêu lỗi.
        """
        if not isinstance(outputs, dict):
            return {}
        extra: Dict[str, Any] = {}

        route = outputs.get("route")
        if route is not None:
            extra["intents"] = list(getattr(route, "intents", []) or [])
            extra["doc_scope"] = getattr(route, "doc_scope", None)
            extra["vehicles"] = list(getattr(route, "vehicles", []) or [])

        if "evidence" in outputs and isinstance(outputs["evidence"], list):
            extra["evidence_count"] = len(outputs["evidence"])
        if "reranked_evidence" in outputs and isinstance(outputs["reranked_evidence"], list):
            extra["reranked_count"] = len(outputs["reranked_evidence"])
        if "packed_context" in outputs and isinstance(outputs["packed_context"], str):
            extra["packed_chars"] = len(outputs["packed_context"])
        if "issues" in outputs and isinstance(outputs["issues"], list):
            extra["issue_count"] = len(outputs["issues"])
        if "repair_count" in outputs:
            extra["repair_count"] = outputs["repair_count"]
        if "needs_search" in outputs:
            extra["needs_search"] = bool(outputs["needs_search"])
        if "sources" in outputs and isinstance(outputs["sources"], list):
            extra["source_count"] = len(outputs["sources"])
        return extra

    # ------------------------------------------------------------------
    # Lệnh gọi mô hình
    # ------------------------------------------------------------------

    def _record_llm_start(self, key: str, kwargs: Dict[str, Any], prompt_text: str) -> None:
        inv = kwargs.get("invocation_params") or {}
        self._llm_starts[key] = {
            "t0": time.perf_counter(),
            "node": self._node_name(kwargs),
            "model": inv.get("model") or inv.get("model_name"),
            "prompt_chars": len(prompt_text),
        }

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self._record_llm_start(str(kwargs.get("run_id", "llm")), kwargs, "".join(prompts or []))

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: Any, **kwargs: Any) -> None:
        flat = ""
        try:
            flat = "".join(
                str(getattr(m, "content", "")) for batch in (messages or []) for m in batch
            )
        except TypeError:
            pass
        self._record_llm_start(str(kwargs.get("run_id", "llm")), kwargs, flat)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        key = str(kwargs.get("run_id", "llm"))
        started = self._llm_starts.pop(key, {})
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}

        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        estimated = False

        # Một số provider không trả `usage` khi stream — ước lượng và đánh dấu rõ ràng,
        # để số đo thật và số ước lượng không bị trộn khi tổng hợp.
        if prompt_tokens == 0 and completion_tokens == 0:
            estimated = True
            prompt_tokens = estimate_tokens("x" * started.get("prompt_chars", 0))
            completion_tokens = estimate_tokens(self._response_text(response))

        model = llm_output.get("model_name") or started.get("model") or ""
        cost, cost_source = estimate_cost_usd(
            model, prompt_tokens, completion_tokens, usage.get("cost")
        )

        t0 = started.get("t0")
        self._emit(
            node=started.get("node"),
            event="llm_end",
            duration_ms=None if t0 is None else round((time.perf_counter() - t0) * 1000, 2),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            extra={"tokens_estimated": estimated, "cost_source": cost_source},
        )

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        key = str(kwargs.get("run_id", "llm"))
        started = self._llm_starts.pop(key, {})
        t0 = started.get("t0")
        self._emit(
            node=started.get("node"),
            event="llm_error",
            duration_ms=None if t0 is None else round((time.perf_counter() - t0) * 1000, 2),
            model=started.get("model"),
            error=f"{type(error).__name__}: {error}",
        )

    @staticmethod
    def _response_text(response: Any) -> str:
        try:
            return "".join(
                str(getattr(gen, "text", "") or "")
                for batch in (getattr(response, "generations", None) or [])
                for gen in batch
            )
        except TypeError:
            return ""

    # ------------------------------------------------------------------
    # Sự kiện do đồ thị chủ động ghi
    # ------------------------------------------------------------------

    def log_event(self, node: str, event: str, **fields: Any) -> None:
        """Cho phép các lớp khác ghi thẳng một sự kiện (tầng structured, fallback model...)."""
        self._emit(node=node, event=event, **fields)


def new_run_tracer(thread_id: Optional[str] = None) -> JsonlTracer:
    """Tạo tracer cho một lượt chạy mới."""
    return JsonlTracer(thread_id=thread_id)
