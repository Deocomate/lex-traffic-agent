"""
Tầng xếp hạng lại danh sách tài liệu bằng mô hình ngôn ngữ nhỏ (Listwise LLM Reranking).
Tiếp nhận tối đa 12 ứng viên parent từ tầng RRF, sử dụng structured output Pydantic
để xếp hạng lại dựa trên mức độ trả lời trực tiếp câu hỏi.
Có 3 điều kiện bỏ qua tất định để tiết kiệm chi phí và độ trễ, và đường đi fallback an toàn.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple


from pydantic import BaseModel, Field

from src.llm.provider import get_rerank_llm
from src.llm.structured import structured_call

logger = logging.getLogger(__name__)


class RerankResult(BaseModel):
    """Kết quả xếp hạng lại danh sách tài liệu từ LLM."""

    ordered_ids: List[str] = Field(
        description="Danh sách các parent_id theo thứ tự giảm dần về mức độ liên quan và khả năng trả lời câu hỏi"
    )

    # KHÔNG thêm trường văn bản tự do vào schema này.
    #
    # Trước đây có trường `rationale: Optional[str]` để model giải thích lý do xếp hạng. Không nơi
    # nào trong mã chạy thật đọc nó — chỉ một test dựng nó lên — nhưng model thì cứ viết, và viết
    # dài. Đo trên lượt eval 95 câu: 10 lệnh gọi rerank chạm trần `max_tokens` với
    # `reasoning_tokens=0`, tức toàn bộ hạn mức bị văn xuôi của `rationale` ăn hết TRƯỚC KHI
    # `ordered_ids` kịp được tuần tự hoá. `structured_call` ném `LengthFinishReasonError`, trả None,
    # và `rerank()` lặng lẽ trả về đúng thứ tự RRF ban đầu — tức là **tầng rerank không làm gì cả**
    # trên 8/95 câu mà không ai biết, làm hỏng đúng chỉ số đang yếu nhất (Hit@1/MRR).
    #
    # Schema chỉ trả về thứ tự ID nên đầu ra luôn ngắn và đóng được trong mọi hạn mức hợp lý.


class LLMReranker:
    """Bộ xếp hạng lại tài liệu theo danh sách (Listwise Reranker)."""

    def __init__(
        self,
        model: Optional[Any] = None,
        enable_rerank: Optional[bool] = None,
        rerank_margin: Optional[float] = None,
        max_candidates: int = 12,
    ):
        self._model = model
        if enable_rerank is None:
            enable_rerank = os.getenv("ENABLE_RERANK", "true").lower() in ("true", "1", "yes")
        self.enable_rerank = enable_rerank

        if rerank_margin is None:
            rerank_margin = float(os.getenv("RERANK_MARGIN", "0.15"))
        self.rerank_margin = rerank_margin
        self.max_candidates = max_candidates

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = get_rerank_llm()
        return self._model

    def should_skip(self, candidates: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Kiểm tra 3 điều kiện bỏ qua Reranking:
        1. Biến cấu hình ENABLE_RERANK = false
        2. Số ứng viên <= 3
        3. Biên điểm RRF giữa Top-1 và Top-2 vượt ngưỡng RERANK_MARGIN (đã quá rõ)
        """
        if not self.enable_rerank:
            return True, "Cấu hình ENABLE_RERANK = false"

        if len(candidates) <= 3:
            return True, f"Số ứng viên <= 3 ({len(candidates)} ứng viên)"

        if len(candidates) >= 2:
            score1 = candidates[0].get("score", 0.0)
            score2 = candidates[1].get("score", 0.0)
            # Thang điểm 0-100: margin 0.15 tương đương 15 điểm
            margin_100 = self.rerank_margin * 100.0
            if (score1 - score2) >= margin_100:
                return (
                    True,
                    f"Biên điểm Top-1 ({score1:.1f}) so với Top-2 ({score2:.1f}) >= {margin_100:.1f} điểm",
                )

        return False, ""

    def _build_prompt(self, query: str, candidate_pool: List[Dict[str, Any]]) -> str:
        """Xây dựng chuỗi prompt súc tích chứa ID, trích dẫn và 200 ký tự đầu của mỗi ứng viên."""
        items = []
        for idx, c in enumerate(candidate_pool, start=1):
            pid = c.get("parent_id", f"doc_{idx}")
            citation = c.get("citation", c.get("article_header", ""))
            content = c.get("page_content", "").strip().replace("\n", " ")
            snippet = content[:200] + ("..." if len(content) > 200 else "")
            items.append(f"[{idx}] ID: {pid}\nTrích dẫn: {citation}\nNội dung: {snippet}")

        candidates_str = "\n\n".join(items)
        return (
            f"Câu hỏi của người dùng:\n\"{query}\"\n\n"
            f"Danh sách {len(candidate_pool)} đoạn văn bản pháp luật ứng viên:\n{candidates_str}\n\n"
            "Hãy phân tích và xếp các ID trên theo thứ tự mức độ trả lời ĐÚNG và TRỰC TIẾP nhất "
            "vào câu hỏi (đoạn trả lời chính xác nhất đứng đầu). Trả về danh sách ordered_ids."
        )

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Xếp hạng lại danh sách ứng viên đồng bộ.
        """
        if not candidates:
            return []

        limit = top_k or len(candidates)

        # 1. Kiểm tra điều kiện bỏ qua
        skip, reason = self.should_skip(candidates)
        if skip:
            logger.debug("Bỏ qua Rerank: %s", reason)
            return candidates[:limit]

        # 2. Chuẩn bị tối đa 12 ứng viên để gửi tới LLM
        pool = candidates[: self.max_candidates]
        id_to_doc = {c.get("parent_id"): c for c in candidates if c.get("parent_id")}

        system_prompt = (
            "Bạn là trợ lý pháp lý giao thông chuẩn xác. Nhiệm vụ của bạn là xếp hạng lại "
            "các điều luật/biển báo theo mức độ trả lời trực tiếp cho câu hỏi của người dùng."
        )
        user_prompt = self._build_prompt(query, pool)

        # 3. Gọi LLM có cấu trúc qua structured_call
        res = structured_call(
            model=self.model,
            schema=RerankResult,
            prompt=user_prompt,
            system_instruction=system_prompt,
        )

        # 4. Khi structured_call trả None hoặc lỗi: Giữ nguyên thứ tự RRF
        if res is None or not res.ordered_ids:
            logger.warning("Rerank structured_call trả về None, giữ nguyên thứ tự RRF ban đầu")
            return candidates[:limit]

        # 5. Tái sắp xếp các ứng viên theo thứ tự mới
        reordered: List[Dict[str, Any]] = []
        seen_pids = set()

        for pid in res.ordered_ids:
            clean_pid = pid.strip()
            resolved_pid = clean_pid
            if resolved_pid not in id_to_doc:
                clean_num = clean_pid.strip("[]# ")
                if clean_num.isdigit() and 1 <= int(clean_num) <= len(pool):
                    resolved_pid = pool[int(clean_num) - 1].get("parent_id")

            if resolved_pid in id_to_doc and resolved_pid not in seen_pids:
                doc = dict(id_to_doc[resolved_pid])
                doc["reranked"] = True
                reordered.append(doc)
                seen_pids.add(resolved_pid)

        # Đưa các ứng viên còn lại chưa được model nhắc tới vào sau cùng theo thứ tự cũ
        for c in candidates:
            pid = c.get("parent_id")
            if pid not in seen_pids:
                reordered.append(c)
                seen_pids.add(pid)

        return reordered[:limit]

    async def arerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Xếp hạng lại danh sách ứng viên bất đồng bộ (async)."""
        return await asyncio.to_thread(self.rerank, query, candidates, top_k)


_shared_reranker: Optional[LLMReranker] = None


def get_reranker(
    model: Optional[Any] = None,
    enable_rerank: Optional[bool] = None,
    rerank_margin: Optional[float] = None,
) -> LLMReranker:
    """Lấy thể hiện LLMReranker dùng chung."""
    global _shared_reranker
    if _shared_reranker is None:
        _shared_reranker = LLMReranker(
            model=model,
            enable_rerank=enable_rerank,
            rerank_margin=rerank_margin,
        )
    return _shared_reranker
