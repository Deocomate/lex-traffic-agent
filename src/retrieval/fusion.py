"""
Hợp nhất thứ hạng và chọn kết quả — không hằng số nào phụ thuộc corpus.

Bản trước dùng RRF *có trọng số* (`w_dense=0.6`, `w_sparse=0.4`, `k=30`) cùng một loạt ngưỡng
sàn tuyệt đối (`SEMANTIC_FLOOR=0.58`, `HYBRID_RELEVANCE_FLOOR=60.0`, `SCORE_FLOOR=12.0`,
`COVERAGE_FLOOR=0.40`). Toàn bộ chúng được quét siêu tham số trên đúng một corpus với đúng một
embedding model, nên đổi bất kỳ thứ gì — model, kho văn bản, ngôn ngữ — là mọi con số mất ý
nghĩa. Đó chính là thứ khiến hệ thống không dùng lại được cho miền khác.

Module này thay chúng bằng hai thứ bất biến với thang điểm:

1. `reciprocal_rank_fusion` — RRF ở dạng chuẩn, KHÔNG trọng số. RRF (Cormack, Clarke &
   Buettcher, SIGIR 2009) chỉ đọc THỨ HẠNG chứ không đọc điểm, nên nó vốn đã miễn nhiễm với
   việc hai nhánh có thang điểm khác nhau. Gắn trọng số quét tay vào chính là phá bỏ tính chất
   đó và buộc phải hiệu chuẩn lại mỗi khi đổi dữ liệu.

2. `select_by_separation` — chọn số lượng kết quả theo phân bố điểm của CHÍNH lượt truy vấn
   đó, thay vì so với một ngưỡng cố định, và báo lại độ tin cậy để Agent tự quyết định.

Nói cho sòng phẳng: vẫn còn hai hằng số (`STRONG_CLIFF` / `MODERATE_CLIFF`). Khác biệt nằm ở
chỗ chúng là TỶ LỆ trên điểm hạng 1 của chính lượt truy vấn, không phải một mốc cosine tuyệt
đối. Chúng không biết gì về embedding model, tiếng Việt hay luật giao thông, nên không phải
hiệu chuẩn lại khi đổi miền — khác hẳn `SEMANTIC_FLOOR=0.58`.
"""

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

# Hằng số làm mượt thứ hạng của RRF gốc (Cormack et al. 2009). Nó chỉ quyết định mức độ ưu ái
# các hạng đầu so với hạng sau, không phải tham số cần hiệu chuẩn theo dữ liệu — nên nó nằm
# trong mã nguồn kèm nguồn trích dẫn, không phải trong .env.
RRF_K = 60

# Ngưỡng của "vách rơi" (cliff): tại ranh giới cắt, điểm tụt bao nhiêu phần so với hạng 1.
# Đây là TỶ LỆ chứ không phải đơn vị điểm, nên đổi corpus hay embedding model không cần hiệu
# chuẩn lại.
STRONG_CLIFF = 0.35
MODERATE_CLIFF = 0.15

BAND_STRONG = "STRONG"
BAND_MODERATE = "MODERATE"
BAND_WEAK = "WEAK"

_BAND_LABEL_VI = {
    BAND_STRONG: "MẠNH — nhóm kết quả đầu tách hẳn khỏi phần còn lại",
    BAND_MODERATE: "TRUNG BÌNH — điểm giảm dần đều, ranh giới không dứt khoát",
    BAND_WEAK: "YẾU — các ứng viên gần như ngang điểm nhau, không kết quả nào nổi bật hẳn",
}


@dataclass(frozen=True)
class RetrievalConfidence:
    """
    Độ tin cậy của một lượt truy xuất, đo bằng chính phân bố điểm của lượt đó.

    `cliff` là đại lượng cốt lõi: tại ranh giới cắt, điểm tụt bao nhiêu phần so với hạng 1. Nó
    trả lời đúng MỘT câu hỏi — "trong số ứng viên lấy về, có kết quả nào nổi bật hẳn không?" —
    và do đó quyết định giữ lại bao nhiêu kết quả.

    Nó KHÔNG trả lời được "câu hỏi này có nằm trong phạm vi kho tài liệu không". Đó là một đại
    lượng tuyệt đối, cần mốc tham chiếu của corpus chứ không suy ra được từ hình dạng phân bố
    của riêng một lượt truy vấn (xem `src/retrieval/scope.py`). Việc phán xét phạm vi cuối cùng
    thuộc về Agent: nó đọc được nội dung điều luật lấy về và tự thấy có trả lời câu hỏi hay không.

    Vì mọi đại lượng đều là tỷ lệ trên điểm hạng 1, chúng bất biến với thang điểm: nhân toàn bộ
    điểm lên 1000 lần vẫn cho đúng kết luận.
    """

    band: str
    cliff: float
    margin: float
    top_score: float
    kept: int
    pool: int

    @property
    def label_vi(self) -> str:
        return _BAND_LABEL_VI.get(self.band, _BAND_LABEL_VI[BAND_WEAK])

    def header_vi(self) -> str:
        """Dòng tín hiệu chèn vào đầu kết quả công cụ để Agent đọc và tự quyết định."""
        return (
            f"[ĐỘ TIN CẬY TRUY XUẤT: {self.label_vi} "
            f"| vách rơi {self.cliff:.0%}, cách biệt hạng 1-2 {self.margin:.0%}, "
            f"giữ {self.kept}/{self.pool} ứng viên]"
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "band": self.band,
            "cliff": round(self.cliff, 3),
            "margin": round(self.margin, 3),
            "top_score": round(self.top_score, 3),
            "kept": self.kept,
            "pool": self.pool,
        }


EMPTY_CONFIDENCE = RetrievalConfidence(
    band=BAND_WEAK, cliff=0.0, margin=0.0, top_score=0.0, kept=0, pool=0
)


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[str]],
    k: int = RRF_K,
) -> Dict[str, float]:
    """
    RRF chuẩn, không trọng số:  score(d) = Σ_lists 1 / (k + rank_list(d))

    `ranked_lists` ánh xạ tên nhánh -> danh sách id đã sắp theo thứ hạng giảm dần độ liên quan.
    Một tài liệu xuất hiện ở nhiều nhánh được cộng dồn tự nhiên — đó là toàn bộ cơ chế "đồng
    thuận giữa các nhánh" của RRF, không cần thêm bonus thủ công nào.
    """
    scores: Dict[str, float] = {}
    for ids in ranked_lists.values():
        for rank, doc_id in enumerate(ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def max_possible_rrf(num_lists: int, k: int = RRF_K) -> float:
    """Điểm RRF cực đại lý thuyết: đứng hạng 1 ở mọi nhánh. Dùng để chuẩn hoá về [0, 1]."""
    return num_lists / (k + 1) if num_lists > 0 else 0.0


def _band_for(cliff: float) -> str:
    if cliff >= STRONG_CLIFF:
        return BAND_STRONG
    if cliff >= MODERATE_CLIFF:
        return BAND_MODERATE
    return BAND_WEAK


def _knee(relative: Sequence[float], min_k: int) -> Tuple[int, float]:
    """
    Tìm chỗ tụt mạnh nhất giữa hai ứng viên liền kề.

    `relative` là điểm đã chia cho hạng 1, nên độ lớn vách rơi là một tỷ lệ trong [0, 1].
    Trả về `(số_lượng_giữ, độ_lớn_vách_rơi)`.
    """
    cut, largest = min_k, 0.0
    for i in range(len(relative) - 1):
        drop = relative[i] - relative[i + 1]
        if drop > largest:
            largest, cut = drop, i + 1
    return max(min_k, cut), largest


def select_by_separation(
    scores: Sequence[float],
    max_k: int,
    min_k: int = 1,
) -> Tuple[int, RetrievalConfidence]:
    """
    Quyết định giữ lại bao nhiêu ứng viên, dựa trên phân bố điểm của chính lượt truy vấn.

    Trả về `(số_lượng_giữ, độ_tin_cậy)`.

    Cách làm: chuẩn hoá điểm theo hạng 1 (nên bất biến với thang điểm), rồi cắt ngay sau chỗ
    TỤT MẠNH NHẤT giữa hai ứng viên liền kề trong phạm vi `max_k`. Trực giác: một truy vấn tốt
    thường có vài kết quả thật sự liên quan rồi rơi hẳn xuống nhiễu; điểm rơi đó là ranh giới
    tự nhiên, và nó tự dịch chuyển theo từng truy vấn thay vì bị ghim bởi một hằng số.

    Luôn giữ ít nhất `min_k` kết quả: việc phán xét một truy vấn là ngoài phạm vi thuộc về
    Agent (đã có `RetrievalConfidence` để đọc), không thuộc về tầng truy xuất âm thầm trả rỗng.
    """
    values = [float(v) for v in scores]
    if not values:
        return 0, EMPTY_CONFIDENCE

    ordered = sorted(values, reverse=True)
    limit = max(min_k, min(max_k, len(ordered)))
    top = ordered[0]

    if top <= 0:
        return limit, RetrievalConfidence(
            band=BAND_WEAK, cliff=0.0, margin=0.0, top_score=top,
            kept=limit, pool=len(ordered),
        )

    relative = [v / top for v in ordered[:limit]]
    cut, cliff = _knee(relative, min_k)

    second = ordered[1] if len(ordered) > 1 else 0.0
    margin = (top - second) / top

    return cut, RetrievalConfidence(
        band=_band_for(cliff),
        cliff=cliff,
        margin=margin,
        top_score=top,
        kept=cut,
        pool=len(ordered),
    )


def assess_confidence(scores: Sequence[float], kept: int = 0) -> RetrievalConfidence:
    """Độ tin cậy cho một danh sách điểm, tuỳ chọn ghi đè số lượng thực sự giữ lại."""
    values = list(scores)
    _, confidence = select_by_separation(values, max_k=len(values) or 1)
    if kept and kept != confidence.kept:
        return RetrievalConfidence(
            band=confidence.band,
            cliff=confidence.cliff,
            margin=confidence.margin,
            top_score=confidence.top_score,
            kept=kept,
            pool=confidence.pool,
        )
    return confidence


def take_by_separation(
    items: Sequence[dict],
    max_k: int,
    score_key: str = "score",
    min_k: int = 1,
) -> Tuple[List[dict], RetrievalConfidence]:
    """Tiện ích: áp `select_by_separation` thẳng lên danh sách kết quả có trường điểm."""
    ordered = sorted(items, key=lambda d: float(d.get(score_key, 0.0)), reverse=True)
    cut, confidence = select_by_separation(
        [float(d.get(score_key, 0.0)) for d in ordered], max_k=max_k, min_k=min_k
    )
    return list(ordered[:cut]), confidence
