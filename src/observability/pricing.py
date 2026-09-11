"""
Ước lượng chi phí mỗi lệnh gọi mô hình (Phase 7).

QUAN TRỌNG — đây là **ước lượng cục bộ**, không phải số quyết toán. Con số thật luôn là
hoá đơn OpenRouter. Bảng đơn giá dưới đây chỉ dùng khi nhà cung cấp không tự báo chi phí.

Thứ tự ưu tiên khi tính chi phí một lệnh gọi:
1. `usage.cost` do chính OpenRouter trả về trong phản hồi — chính xác nhất, đã tính cả
   chiết khấu, cache và phụ phí; không phụ thuộc bảng đơn giá cục bộ có lạc hậu hay không.
2. Bảng `PRICING_USD_PER_1M` dưới đây, khi biết đơn giá của model.
3. 0.0 cho model chưa biết — chi phí hiện là 0, không phải chi phí sai. Model chưa có
   trong bảng sẽ hiện `cost_usd: 0.0` kèm `cost_source: "unknown"` trong trace, nên
   `summarize_traces.py` phân biệt được "miễn phí" với "chưa biết giá".
"""

import os
from typing import Dict, Optional, Tuple

# {model_id: (USD mỗi 1 triệu token vào, USD mỗi 1 triệu token ra)}
# Cập nhật bằng tay khi đổi model trong .env. Model kết thúc bằng ":free" luôn là 0.
PRICING_USD_PER_1M: Dict[str, Tuple[float, float]] = {
    "deepseek/deepseek-chat": (0.14, 0.28),
}

FREE_SUFFIX = ":free"


def _lookup_rates(model: str) -> Optional[Tuple[float, float]]:
    """Tra đơn giá theo tên model, chấp nhận cả tên có hậu tố biến thể của OpenRouter."""
    if not model:
        return None
    if model.endswith(FREE_SUFFIX):
        return (0.0, 0.0)
    if model in PRICING_USD_PER_1M:
        return PRICING_USD_PER_1M[model]
    # OpenRouter đôi khi thêm hậu tố biến thể ("model:nitro"), khớp theo phần gốc
    base = model.split(":", 1)[0]
    return PRICING_USD_PER_1M.get(base)


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    reported_cost: Optional[float] = None,
) -> Tuple[float, str]:
    """
    Trả về `(cost_usd, cost_source)`.

    `cost_source` là một trong: "provider" (nhà cung cấp tự báo), "table" (bảng cục bộ),
    "unknown" (chưa biết đơn giá — chi phí ghi 0 và được đánh dấu để không ai đọc nhầm là miễn phí).
    """
    if reported_cost is not None:
        try:
            return float(reported_cost), "provider"
        except (TypeError, ValueError):
            pass

    rates = _lookup_rates(model)
    if rates is None:
        return 0.0, "unknown"

    in_rate, out_rate = rates
    cost = (prompt_tokens / 1_000_000.0) * in_rate + (completion_tokens / 1_000_000.0) * out_rate
    return round(cost, 8), "table"


def estimate_tokens(text: str) -> int:
    """
    Ước lượng số token khi nhà cung cấp không báo `usage`.

    Xấp xỉ 4 ký tự/token. Mọi dòng trace dùng con số này đều mang `tokens_estimated: true`
    để không bị trộn lẫn với số đo thật khi tổng hợp.
    """
    return max(0, len(text or "") // 4)


def is_langsmith_enabled() -> bool:
    """LangSmith chỉ bật khi biến môi trường được đặt tường minh."""
    return (os.getenv("LANGSMITH_TRACING") or "").strip().lower() in ("1", "true", "yes")
