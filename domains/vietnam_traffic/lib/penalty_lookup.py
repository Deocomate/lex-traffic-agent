"""
CÔNG CỤ TRA CỨU MỨC PHẠT THEO NGHỊ ĐỊNH 168/2024/NĐ-CP

Nguồn dữ liệu: data/processed/penalty_chunks.jsonl — 634 hành vi vi phạm bóc tách từ toàn văn
Nghị định (sinh bởi scripts/ingest/prepare_penalties.py). Mỗi bản ghi giữ nguyên văn mô tả hành vi,
khung tiền phạt, hình thức xử phạt bổ sung, số điểm GPLX bị trừ và trích dẫn Điểm/Khoản/Điều.

Trước đây phần này là một bảng 10 mục viết tay trong mã nguồn: số tiền đã lạc hậu theo
Nghị định 100/2019 và trích dẫn Điều/Khoản sai. Tra cứu trên văn bản gốc loại bỏ cả hai lỗi đó.
"""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from domains.vietnam_traffic.lib.tool_contract import (
    AGENT_ONLY_TAG,
    FIGURE_LOCK_NOTE,
    NO_PENALTY_DATA_HEADER,
    PENALTY_DECREE_NAME,
)

# Số hành vi trả về tối đa cho một lượt tra cứu: đủ để so sánh giữa các loại xe / mức vi phạm
# mà không làm ngập ngữ cảnh của model nhỏ.
MAX_PENALTY_RESULTS = 5

# doc_id của corpus Nghị định trong chỉ mục ngữ nghĩa hợp nhất
DECREE_DOC_ID = "nghi_dinh_168"

# Nhánh hiệu chuẩn phạm vi riêng cho bộ chấm điểm từ khoá của Nghị định. Mốc so sánh được ĐO
# từ chính corpus bằng scripts/ingest/calibrate_scope.py, không gõ tay: trước đây là
# `SCORE_FLOOR = 12.0` và `SEMANTIC_FLOOR = 0.62`, hai con số chỉ đúng với đúng corpus này.
SCOPE_BRANCH = "penalty_keyword"

# Tỷ lệ trọng số IDF của câu hỏi phải khớp được. Đây là bộ lọc CẤU TRÚC chứ không phải ngưỡng
# chất lượng: dưới 40% trọng số khớp nghĩa là phần lớn từ mang thông tin của câu hỏi không hề
# xuất hiện trong hành vi — câu lạc đề chỉ trùng vài từ phổ thông ('trên', 'đường').
COVERAGE_FLOOR = 0.40

from src.retrieval.fusion import select_by_separation
from src.retrieval.scope import get_scope_reference
from src.retrieval.vi_text import (
    bigrams,
    expand_query,
    preferred_entities,
    stopwords,
    tokens,
)



class PenaltyLookup:
    """Tra cứu mức phạt trên toàn văn Nghị định 168/2024/NĐ-CP đã cấu trúc hóa"""

    def __init__(self, base_dir: str, semantic_index=None):
        self.base_dir = base_dir
        self.chunks_path = os.path.join(base_dir, "data", "processed", "penalty_chunks.jsonl")
        self.chunks: List[Dict[str, Any]] = []
        # Chỉ mục ngữ nghĩa dùng chung với semantic_search, tiêm vào để không nạp vector hai lần
        self._semantic = semantic_index
        self._semantic_unavailable = False
        self._load()

    def _get_semantic(self):
        """Khởi tạo lười chỉ mục ngữ nghĩa; thiếu chỉ mục thì tra cứu vẫn chạy bằng từ khóa"""
        if self._semantic is not None or self._semantic_unavailable:
            return self._semantic
        try:
            from src.semantic_index import SemanticIndex
            index = SemanticIndex(self.base_dir)
            if not index.available:
                raise RuntimeError("chưa có chỉ mục ngữ nghĩa")
            self._semantic = index
        except Exception:
            self._semantic_unavailable = True
            return None
        return self._semantic

    def _load(self) -> None:
        if not os.path.exists(self.chunks_path):
            return
        with open(self.chunks_path, "r", encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f if line.strip()]

        # Token hóa sẵn từng hành vi. Bắt buộc phải so khớp theo TOKEN chứ không phải chuỗi con:
        # 'ăn' là chuỗi con của 'khả năng', nên khớp chuỗi làm câu lạc đề vẫn ra kết quả.
        self._chunk_tokens = [set(self._tokens(c["behaviour"])) for c in self.chunks]
        self._title_tokens = [set(self._tokens(c["article_title"])) for c in self.chunks]
        # Cặp từ liền kề: neo ngữ nghĩa của truy vấn. Trùng từ rời rạc có thể là ngẫu nhiên,
        # trùng cả cụm ('đèn tín', 'mũ bảo', 'cao tốc') thì gần như chắc chắn cùng nói về một hành vi.
        self._chunk_bigrams = [self._bigrams(self._tokens(c["behaviour"])) for c in self.chunks]
        self._build_idf()

    def _build_idf(self) -> None:
        """
        Trọng số IDF cho từng từ trong corpus Nghị định.

        Cần thiết vì các từ như 'đường', 'xe', 'giao thông' xuất hiện ở hầu hết 634 hành vi:
        nếu chấm điểm đều nhau thì một câu hỏi lạc đề ('nấu ăn trên đường') vẫn khớp hàng loạt
        hành vi chỉ nhờ hai từ vô nghĩa, và hệ thống lại đưa ra một mức phạt không liên quan.
        """
        total = len(self.chunks)
        document_freq: Dict[str, int] = {}
        for tokens in self._chunk_tokens:
            for token in tokens:
                document_freq[token] = document_freq.get(token, 0) + 1
        self._idf = {
            token: math.log(total / (1 + freq)) + 0.1
            for token, freq in document_freq.items()
        }
        # Từ chưa từng xuất hiện trong Nghị định: coi như rất hiếm, nhưng sẽ không khớp được gì
        self._default_idf = math.log(total) + 0.1

    def _weight(self, token: str) -> float:
        return max(self._idf.get(token, self._default_idf), 0.0)

    @property
    def available(self) -> bool:
        return bool(self.chunks)

    # ------------------------------------------------------------------
    # Chuẩn hóa truy vấn
    # ------------------------------------------------------------------

    _expand_query = staticmethod(expand_query)
    _tokens = staticmethod(tokens)
    _bigrams = staticmethod(bigrams)
    _preferred_vehicles = staticmethod(preferred_entities)


    # ------------------------------------------------------------------
    # Tìm kiếm
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = MAX_PENALTY_RESULTS) -> List[Dict[str, Any]]:
        """
        Tra cứu lai ghép: từ khóa cho độ chính xác, ngữ nghĩa cho độ bao phủ.

        Hai tầng bù khuyết cho nhau. Từ khóa bắt đúng thuật ngữ pháp lý nhưng bó tay với cách
        nói đời thường không trùng chữ nào ("đi bốc đầu", "chở cồng kềnh"). Ngữ nghĩa bao được
        cách nói đó nhưng dễ trả về hành vi na ná khi câu hỏi lạc đề — nên vẫn phải có ngưỡng.
        """
        keyword_hits = self._search_by_keyword(query, limit)
        semantic_hits = self._search_by_meaning(query, limit)
        semantic_ready = self._get_semantic() is not None

        # Không có hành vi nào trong Nghị định gần nghĩa với câu hỏi -> câu hỏi nằm ngoài phạm vi.
        # Khi đó bỏ luôn kết quả của tầng từ khóa: chúng chỉ trùng chữ ngẫu nhiên
        # ("thời tiết hôm nay" trùng cụm "thời tiết" trong điều khoản về đèn chiếu sáng).
        if semantic_ready and not semantic_hits:
            return []
        if not semantic_hits:
            return keyword_hits

        # Gộp theo trích dẫn, giữ thứ tự ưu tiên: khớp cả hai tầng > khớp từ khóa > khớp ngữ nghĩa
        merged: Dict[str, Dict[str, Any]] = {}
        for rank, chunk in enumerate(keyword_hits):
            merged[chunk["citation"]] = {"chunk": chunk, "rank": rank, "both": False}
        for rank, chunk in enumerate(semantic_hits):
            existing = merged.get(chunk["citation"])
            if existing:
                existing["both"] = True
                existing["rank"] = min(existing["rank"], rank)
            else:
                merged[chunk["citation"]] = {"chunk": chunk, "rank": rank + len(keyword_hits), "both": False}

        # Nếu câu hỏi về làn khẩn cấp / cao tốc mà không chỉ định riêng ô tô:
        # Luật cấm tuyệt đối xe máy vào cao tốc (kể cả làn khẩn cấp). Đảm bảo kết quả có
        # chế tài xử phạt xe máy đi vào cao tốc (Điểm b Khoản 7 Điều 7) để Agent luôn phân tích đủ cả hai loại xe.
        lowered_q = query.lower()
        if any(term in lowered_q for term in ("làn khẩn cấp", "làn dừng", "cao tốc")):
            if not any(h in lowered_q for h in ("ô tô", "oto", "xe con", "xe tải", "xe khách")):
                motorbike_highway_chunk = next(
                    (c for c in self.chunks if c.get("article_number") == 7 and c.get("clause_number") == 7 and c.get("point_letter") == "b"),
                    None
                )
                if motorbike_highway_chunk and motorbike_highway_chunk["citation"] not in merged:
                    merged[motorbike_highway_chunk["citation"]] = {
                        "chunk": motorbike_highway_chunk,
                        "rank": 0,
                        "both": True
                    }

        # Loại phương tiện người dùng hỏi được ưu tiên trước hết: tầng ngữ nghĩa không phân biệt
        # được "ô tô đỗ trên cầu" với "xe máy đỗ trên cầu" vì hai hành vi mô tả gần như y hệt.
        preferred = self._preferred_vehicles(query)

        def sort_key(entry):
            vehicle_miss = bool(preferred) and entry["chunk"]["vehicle"] not in preferred
            return (vehicle_miss, not entry["both"], entry["rank"])

        ordered = sorted(merged.values(), key=sort_key)
        return [e["chunk"] for e in ordered[:limit]]

    def _search_by_meaning(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Tra theo vector trên riêng corpus Nghị định.

        Không còn ngưỡng cosine tuyệt đối ở đây: việc chặn câu lạc đề đã chuyển sang mốc tham
        chiếu đo từ corpus trong `_search_by_keyword`.
        """
        index = self._get_semantic()
        if index is None or not query:
            return []
        try:
            hits = index.search_chunks(query, doc_ids=(DECREE_DOC_ID,), top_k=limit)
        except Exception:
            return []

        by_citation = {c["citation"]: c for c in self.chunks}
        return [by_citation[h["citation"]] for h in hits if h.get("citation") in by_citation]

    def score_by_keyword(self, query: str) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Chấm điểm mọi hành vi trong Nghị định theo mức trùng khớp với câu hỏi, KHÔNG cắt ngưỡng.

        Tách riêng khỏi `_search_by_keyword` để `scripts/ingest/calibrate_scope.py` dùng lại
        được: hiệu chuẩn cần chính phân bố điểm thô mà tra cứu sẽ nhìn thấy.
        """
        if not query or not self.chunks:
            return []

        expanded, alias_phrases = self._expand_query(query)
        token_sequence = self._tokens(expanded)
        tokens = set(token_sequence)
        if not tokens:
            return []
        query_bigrams = self._bigrams(token_sequence)
        # Truy vấn một từ ("cồn", "tốc độ") không có cặp từ nào để neo -> bỏ qua điều kiện này
        require_phrase_anchor = len(query_bigrams) > 0
        preferred = self._preferred_vehicles(query)
        total_weight = sum(self._weight(t) for t in tokens) or 1.0

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for index, chunk in enumerate(self.chunks):
            behaviour_tokens = self._chunk_tokens[index]
            matched_weight = sum(self._weight(t) for t in tokens if t in behaviour_tokens)
            if matched_weight == 0:
                continue

            # Tỷ lệ phủ tính theo trọng số: khớp được các từ hiếm mới có ý nghĩa,
            # khớp toàn từ phổ thông thì coverage vẫn thấp và bị loại ở ngưỡng sàn.
            coverage = matched_weight / total_weight
            if coverage < COVERAGE_FLOOR:
                continue

            # Neo cụm từ: thiếu nó thì các từ trùng chỉ là trùng hợp ngẫu nhiên
            # ('nấu ăn trên đường' trùng 'ăn' và 'đường' ở hai vế không liên quan).
            shared_bigrams = query_bigrams & self._chunk_bigrams[index]
            if require_phrase_anchor and not shared_bigrams:
                continue

            score = matched_weight * 3.0 + coverage * 10.0 + min(len(shared_bigrams), 4) * 4.0
            score += sum(self._weight(t) for t in tokens if t in self._title_tokens[index]) * 0.5

            # Thưởng khi cụm pháp lý do alias sinh ra xuất hiện nguyên văn trong hành vi
            behaviour = chunk["behaviour"].lower()
            if any(phrase in behaviour for phrase in alias_phrases):
                score += 15.0

            if preferred:
                score += 8.0 if chunk["vehicle"] in preferred else -4.0

            scored.append((score, chunk))

        scored.sort(key=lambda x: (-x[0], x[1]["article_number"], x[1]["clause_number"]))
        return scored

    def _search_by_keyword(self, query: str, limit: int = MAX_PENALTY_RESULTS) -> List[Dict[str, Any]]:
        """
        Tra theo từ khoá: chấm điểm, đối chiếu mốc phạm vi đo từ corpus, rồi cắt theo vách rơi.

        Hai tầng bảo vệ thay cho `SCORE_FLOOR = 12.0`:
        1. Điểm cao nhất phải đạt mốc tham chiếu của corpus, nếu không coi như không tra được —
           giữ nguyên tính chất quan trọng nhất của bản cũ: THÀ KHÔNG CÓ DỮ LIỆU còn hơn đưa ra
           một hành vi gần đúng, vì một mức phạt sai nguy hiểm hơn hẳn câu "chưa tra được".
        2. Phần đuôi bị cắt theo phân bố điểm của chính lượt truy vấn (`select_by_separation`).
        """
        scored = self.score_by_keyword(query)
        if not scored:
            return []

        scope = get_scope_reference(self.base_dir).assess(scored[0][0], SCOPE_BRANCH)
        if scope.calibrated and not scope.in_scope:
            return []

        keep, _confidence = select_by_separation([s for s, _c in scored], max_k=limit)
        scored = scored[:keep]

        preferred = self._preferred_vehicles(query)
        if preferred:
            return [c for _s, c in scored[:limit]]

        # Không nêu loại xe: ưu tiên đa dạng nhóm phương tiện thay vì 5 dòng cùng một nhóm
        seen_vehicles = set()
        diverse: List[Dict[str, Any]] = []
        for _score, chunk in scored:
            if chunk["vehicle"] in seen_vehicles:
                continue
            seen_vehicles.add(chunk["vehicle"])
            diverse.append(chunk)
            if len(diverse) >= limit:
                break
        return diverse

    # ------------------------------------------------------------------
    # Định dạng kết quả cho Agent
    # ------------------------------------------------------------------

    def _no_data(self, query: str) -> str:
        """Không tra được thì phải nói dứt khoát, nếu không mô hình sẽ tự điền số tiền từ trí nhớ"""
        return (
            f"{NO_PENALTY_DATA_HEADER} '{query}' ===\n"
            f"Không tìm thấy hành vi vi phạm nào khớp trong toàn văn {PENALTY_DECREE_NAME}.\n\n"
            f"{AGENT_ONLY_TAG}\n"
            "- TUYỆT ĐỐI KHÔNG nêu bất kỳ con số tiền phạt nào cho hành vi này.\n"
            "- Phải nói rõ với người dùng rằng chưa tra cứu được mức phạt cho hành vi này và "
            "đề nghị họ mô tả cụ thể hơn (loại xe, hành vi chính xác).\n"
            f"- Có thể trình bày quy tắc/hành vi bị cấm theo Luật 36/2024/QH15 nếu tra cứu được, "
            "nhưng không được suy ra mức tiền phạt từ đó."
        )

    def format_results(self, query: str, results: List[Dict[str, Any]]) -> str:
        """Kết xuất dạng văn bản để Agent trích dẫn nguyên văn"""
        if not results:
            return self._no_data(query)

        lines = [
            f"=== MỨC XỬ PHẠT THEO {PENALTY_DECREE_NAME} (hiệu lực 01/01/2025) ===",
            f"Hành vi tra cứu: '{query}'",
            f"Nguồn duy nhất của mọi con số dưới đây: {PENALTY_DECREE_NAME}.",
            ""
        ]
        for chunk in results:
            lines.append(f"• [{chunk['vehicle']}] {chunk['citation']}")
            lines.append(f"  Hành vi: {chunk['behaviour']}")
            lines.append(f"  💰 Mức phạt tiền: {chunk['fine_text']}")
            if chunk.get("points_deducted"):
                lines.append(f"  ➖ Trừ điểm giấy phép lái xe: {chunk['points_deducted']} điểm")
            for sanction in chunk.get("extra_sanctions", [])[:2]:
                lines.append(f"  🛑 Xử phạt bổ sung: {sanction}")
            lines.append("")

        lines.append(FIGURE_LOCK_NOTE)
        return "\n".join(lines)

    def lookup(self, violation_keyword: str) -> str:
        """Điểm vào của công cụ: tra cứu và kết xuất trong một bước"""
        query = (violation_keyword or "").strip()
        if not query:
            return "Vui lòng cung cấp hành vi vi phạm cần tra cứu mức phạt."
        if not self.available:
            return (
                f"{NO_PENALTY_DATA_HEADER} '{query}' ===\n"
                "Chưa nạp được dữ liệu Nghị định 168/2024/NĐ-CP. "
                "Chạy: python scripts/ingest/prepare_penalties.py để tạo data/processed/penalty_chunks.jsonl.\n\n"
                f"{AGENT_ONLY_TAG}\nKhông được nêu bất kỳ mức phạt nào khi chưa có dữ liệu."
            )
        return self.format_results(query, self.search(query))

    # ------------------------------------------------------------------
    # Phục vụ giao diện tra cứu
    # ------------------------------------------------------------------

    def vehicles(self) -> List[str]:
        return sorted({c["vehicle"] for c in self.chunks})

    def browse(self, vehicle: Optional[str] = None, keyword: Optional[str] = None,
               limit: int = 200) -> List[Dict[str, Any]]:
        """Duyệt bảng mức phạt cho màn hình tra cứu của người dùng"""
        kw = (keyword or "").strip().lower()
        rows = [
            c for c in self.chunks
            if (not vehicle or c["vehicle"] == vehicle)
            and (not kw or kw in c["behaviour"].lower() or kw in c["article_title"].lower())
        ]
        rows.sort(key=lambda c: (c["article_number"], c["clause_number"], c["point_letter"] or ""))
        return rows[:limit]
