"""
Lớp truy cập mô hình ngôn ngữ (LLM Provider) cho LexTraffic AI.
Cung cấp mô hình đã cấu hình theo vai trò (Router, Rerank, Synthesize, Repair),
tích hợp chuỗi fallback tự động và cơ chế theo dõi model thực tế được dùng.
"""

import os
import logging
from typing import Any, Callable, Dict, List, Optional
from dotenv import load_dotenv

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

load_dotenv()
logger = logging.getLogger(__name__)

# Cấu hình vai trò mô hình: (biến môi trường, temperature, max_tokens, mức reasoning)
#
# `max_tokens` của OpenRouter tính CẢ reasoning token lẫn token nội dung. Model reasoning "nghĩ"
# quá dài là chạm trần trước khi kịp viết ra nội dung, và câu trả lời bị cắt cụt hoặc rỗng hẳn.
# Đo trên bộ trace 25 câu: 2 lệnh gọi `deepseek` dừng đúng ở 4.000 token và cho ra câu trả lời
# rỗng — chính là 2/25 câu bị huỷ (8%).
#
# Vì vậy: ghìm reasoning ở mức "low", và cấp hạn mức token rộng vì cả hai vai trò đều phải viết
# văn bản dài cho người dùng đọc.
MODEL_ROLES: Dict[str, tuple[str, float, int, str]] = {
    "synthesize": ("LLM_MODEL", 0.0, 8000, "low"),
    "repair": ("LLM_MODEL", 0.0, 8000, "low"),
}

# Ghìm reasoning bằng `effort` chứ KHÔNG phải `enabled: false`. Đã thử tắt hẳn và bị
# `openai/gpt-oss-20b` từ chối bằng lỗi 400 "Reasoning is mandatory for this endpoint and cannot
# be disabled" — mọi tầng structured output đổ theo, `structured_call` rơi thẳng xuống tầng 4 và
# trả về None. `effort` được cả model reasoning lẫn model thường chấp nhận nên an toàn với mọi
# provider; `exclude: True` để chuỗi reasoning không chiếm chỗ trong phần trả về.
def _reasoning_body(effort: str) -> Dict[str, Any]:
    """Khối `reasoning` gửi kèm yêu cầu OpenRouter cho một mức nỗ lực cho trước."""
    return {"reasoning": {"effort": effort, "exclude": True}}


class ModelFallbackTracker(BaseCallbackHandler):
    """
    Callback handler để theo dõi mô hình thực tế được gọi và ghi nhận
    sự kiện fallback khi mô hình chính gặp sự cố mạng hoặc lỗi API.
    """

    def __init__(
        self,
        primary_model: str,
        fallback_model: Optional[str] = None,
        on_fallback: Optional[Callable[[str, str], None]] = None,
    ):
        super().__init__()
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.on_fallback = on_fallback
        self.active_model: Optional[str] = None
        self.is_fallback: bool = False
        self._primary_errored: bool = False

    def reset(self) -> None:
        """Đặt lại trạng thái của tracker về ban đầu."""
        self.is_fallback = False
        self._primary_errored = False
        self.active_model = None

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Ghi nhận khi một lệnh gọi LLM bị lỗi."""
        self._primary_errored = True

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Kiểm tra mô hình bắt đầu chạy và phát hiện fallback."""
        inv_params = kwargs.get("invocation_params") or {}
        model_name = (
            inv_params.get("model")
            or inv_params.get("model_name")
            or (serialized.get("kwargs") or {}).get("model_name")
            or serialized.get("name")
        )
        self.active_model = str(model_name) if model_name else self.primary_model

        # Nếu model chính bắt đầu chạy lại, đặt lại trạng thái lỗi trước đó
        is_primary = (
            self.active_model == self.primary_model
            or (self.fallback_model and self.fallback_model not in self.active_model)
        )
        if is_primary:
            self._primary_errored = False
            self.is_fallback = False
            return

        is_fb = False
        if self._primary_errored:
            is_fb = True
        elif (
            self.fallback_model
            and self.active_model
            and (
                self.active_model == self.fallback_model
                or self.fallback_model in self.active_model
            )
            and self.active_model != self.primary_model
        ):
            is_fb = True

        if is_fb and not self.is_fallback:
            self.is_fallback = True
            logger.warning(
                "Model fallback kích hoạt: chuyển từ '%s' sang '%s'",
                self.primary_model,
                self.active_model,
            )
            try:
                from src.observability.tracer import record_model_fallback

                record_model_fallback(self.primary_model, self.active_model)
            except Exception:
                pass

            # Phát luôn sự kiện SSE `model_fallback`. Trước đây chỗ này chỉ ghi vào tệp trace, nên
            # giao diện có sẵn nhánh xử lý `model_fallback` (`static/js/agent-trace.js`) mà không
            # bao giờ nhận được sự kiện nào — người dùng không hề biết câu trả lời đang được sinh
            # bởi model dự phòng chứ không phải model chính. Bảng hợp đồng SSE trong `plan.md` liệt
            # kê sự kiện này là bắt buộc.
            try:
                from src.graph.events import emit

                emit(
                    "model_fallback",
                    f"Chuyển sang model dự phòng: {self.active_model}",
                    primary_model=self.primary_model,
                    active_model=self.active_model,
                )
            except Exception as err:
                logger.debug("Không phát được sự kiện SSE model_fallback: %s", err)

            if self.on_fallback:
                try:
                    self.on_fallback(self.primary_model, self.active_model)
                except Exception as err:
                    logger.error("Lỗi khi thực thi callback on_fallback: %s", err)


def _run_callbacks(tracker: "ModelFallbackTracker") -> List[BaseCallbackHandler]:
    """
    Danh sách callback gắn vào mô hình.

    `with_config(callbacks=[...])` của LangChain **thay thế** callback kế thừa từ lượt chạy
    cha chứ không gộp thêm. Nếu chỉ gắn tracker fallback ở đây thì tracer quan trắc của đồ
    thị không bao giờ thấy các lệnh gọi `synthesize` và `repair` (hai lệnh gọi đắt nhất),
    nên phải đưa tracer của lượt chạy hiện tại vào cùng danh sách.
    """
    handlers: List[BaseCallbackHandler] = [tracker]
    try:
        from src.observability.tracer import get_current_tracer

        current = get_current_tracer()
        if current is not None:
            handlers.append(current)
    except Exception:
        pass
    return handlers


def get_chat_model(
    purpose: str,
    on_fallback: Optional[Callable[[str, str], None]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    primary_model_override: Optional[str] = None,
    fallback_model_override: Optional[str] = None,
) -> BaseChatModel:
    """
    Khởi tạo và cấu hình mô hình ChatOpenAI trỏ tới OpenRouter theo vai trò nghiệp vụ.

    Args:
        purpose: Vai trò của mô hình ('router', 'rerank', 'synthesize', 'repair').
        on_fallback: Callback tùy chọn khi fallback kích hoạt (primary_name, fallback_name).
        api_key: Khóa API (mặc định đọc từ OPENROUTER_API_KEY).
        base_url: Base URL API (mặc định đọc từ OPENROUTER_BASE_URL hoặc https://openrouter.ai/api/v1).
        temperature: Ghi đè temperature nếu cần (mặc định 0.0).
        max_tokens: Ghi đè max_tokens nếu cần.
        primary_model_override: Ghi đè tên model chính.
        fallback_model_override: Ghi đè tên model dự phòng.

    Returns:
        BaseChatModel: Mô hình LangChain đã cấu hình chuỗi fallback và tracker.
    """
    if purpose not in MODEL_ROLES:
        raise ValueError(
            f"Vai trò mô hình '{purpose}' không hợp lệ. Hỗ trợ: {list(MODEL_ROLES.keys())}"
        )

    env_key, default_temp, default_max_tokens, reasoning_effort = MODEL_ROLES[purpose]
    temp = temperature if temperature is not None else default_temp
    tokens = max_tokens if max_tokens is not None else default_max_tokens
    extra_body = _reasoning_body(reasoning_effort)

    # Xác định model chính
    primary_model = (
        primary_model_override
        or (os.getenv(env_key) or "").strip()
        or (os.getenv("LLM_MODEL") or "").strip()
        or "nvidia/nemotron-3.5-lightning"
    )

    # Xác định model dự phòng
    fallback_model = (
        fallback_model_override
        or (os.getenv("FALLBACK_LLM_MODEL") or "").strip()
        or None
    )

    resolved_api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not resolved_api_key:
        raise ValueError("Không tìm thấy OPENROUTER_API_KEY trong file .env hoặc tham số truyền vào!")

    resolved_base_url = (
        base_url
        or os.getenv("OPENROUTER_BASE_URL")
        or "https://openrouter.ai/api/v1"
    )

    default_headers = {
        "HTTP-Referer": "https://github.com/lextraffic-ai",
        "X-Title": "LexTraffic AI",
    }

    # Khởi tạo primary model
    primary = ChatOpenAI(
        model=primary_model,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        temperature=temp,
        max_tokens=tokens,
        timeout=60.0,
        max_retries=2,
        default_headers=default_headers,
        extra_body=extra_body,
    )

    # Thiết lập fallback tracker
    tracker = ModelFallbackTracker(
        primary_model=primary_model,
        fallback_model=fallback_model,
        on_fallback=on_fallback,
    )

    # Nếu có model dự phòng và khác model chính -> bọc with_fallbacks
    if fallback_model and fallback_model != primary_model:
        fallback = ChatOpenAI(
            model=fallback_model,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            temperature=temp,
            max_tokens=tokens,
            timeout=60.0,
            max_retries=2,
            default_headers=default_headers,
            extra_body=extra_body,
        )
        return primary.with_fallbacks([fallback]).with_config(callbacks=_run_callbacks(tracker))

    return primary.with_config(callbacks=_run_callbacks(tracker))


def get_model_tracker(model: Any) -> Optional[ModelFallbackTracker]:
    """
    Lấy tracker gắn với mô hình runnable từ danh sách callbacks cấu hình.
    Không dùng registry toàn cục để tránh rò rỉ bộ nhớ.
    """
    config = getattr(model, "config", None) or {}
    callbacks = config.get("callbacks") or []
    for cb in callbacks:
        if isinstance(cb, ModelFallbackTracker):
            return cb
    return None


def get_synthesize_llm(**kwargs: Any) -> BaseChatModel:
    """Lấy mô hình ChatOpenAI cho vai trò Tổng hợp câu trả lời."""
    return get_chat_model(purpose="synthesize", **kwargs)


def get_repair_llm(**kwargs: Any) -> BaseChatModel:
    """Lấy mô hình ChatOpenAI cho vai trò Tự sửa câu trả lời."""
    return get_chat_model(purpose="repair", **kwargs)




