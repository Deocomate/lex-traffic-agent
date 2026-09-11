"""
Bật LangSmith Cloud bằng biến môi trường (Phase 7) — mặc định TẮT.

Bật LangSmith nghĩa là câu hỏi của người dùng, bằng chứng pháp lý đã tra cứu và câu trả
lời sinh ra **rời khỏi máy này** và được gửi tới dịch vụ của LangChain. Đó là lý do mặc
định là tắt và vì sao hàm dưới đây ghi một dòng cảnh báo rõ ràng mỗi khi bật.

Không có mã nào khác trong hệ thống phải đổi: LangChain tự đọc các biến `LANGCHAIN_*`.
"""

import logging
import os

logger = logging.getLogger(__name__)

_configured = False


def configure_langsmith() -> bool:
    """
    Đặt các biến môi trường LangChain cần khi `LANGSMITH_TRACING=true`.
    Trả về True nếu LangSmith đang bật.
    """
    global _configured

    from src.observability.pricing import is_langsmith_enabled

    if not is_langsmith_enabled():
        return False

    api_key = (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or "").strip()
    if not api_key:
        logger.warning(
            "LANGSMITH_TRACING=true nhưng thiếu LANGSMITH_API_KEY — bỏ qua, chỉ ghi trace cục bộ."
        )
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ.setdefault(
        "LANGCHAIN_PROJECT", (os.getenv("LANGSMITH_PROJECT") or "lextraffic-ai").strip()
    )
    os.environ.setdefault(
        "LANGCHAIN_ENDPOINT",
        (os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com").strip(),
    )

    if not _configured:
        _configured = True
        logger.warning(
            "LangSmith ĐANG BẬT (project=%s): câu hỏi người dùng, bằng chứng tra cứu và câu "
            "trả lời sẽ được gửi tới dịch vụ ngoài. Đặt LANGSMITH_TRACING=false để chỉ ghi cục bộ.",
            os.environ.get("LANGCHAIN_PROJECT"),
        )
    return True
