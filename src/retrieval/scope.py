"""
Phán đoán câu hỏi có nằm trong phạm vi kho tài liệu hay không — mốc tham chiếu lấy TỪ CHÍNH
CORPUS, không do người gõ tay.

Vì sao cần module riêng: `fusion.select_by_separation` đo độ *tách biệt* giữa các ứng viên —
"có kết quả nào nổi bật hẳn không". Đó là đại lượng TƯƠNG ĐỐI, và nó không trả lời được câu
hỏi "kho tài liệu này có nói gì về chuyện đó không". Đo thực tế cho thấy rõ: câu "hôm nay trời
mưa có nên mang ô không" vẫn cho vách rơi 55% (band MẠNH) vì BM25 tìm được đúng một đoạn trùng
chữ ngẫu nhiên nổi bật hẳn lên. Tách biệt cao, mà hoàn toàn lạc đề.

Phán đoán phạm vi buộc phải so với một mốc TUYỆT ĐỐI. Bản cũ giải quyết bằng `SEMANTIC_FLOOR
= 0.58` — một con số gõ tay sau khi quét trên đúng corpus này với đúng embedding model này.
Đổi model hay đổi miền là con số đó vô nghĩa, và đó chính là thứ khiến hệ thống không tái dùng
được.

Ở đây mốc tham chiếu được ĐO, theo một trong hai cách, xếp theo thứ tự ưu tiên:

1. **Khớp từ ví dụ gán nhãn** (chính xác nhất). Miền nào cung cấp được vài chục câu hỏi có nhãn
   trong/ngoài phạm vi thì mốc được chọn để tối đa hoá (bắt đúng lạc đề − báo nhầm câu hợp lệ).
   Đây là cách đúng để hiệu chuẩn một bộ phát hiện lạc đề: dùng chính ví dụ, không phải trực giác.

2. **Thống kê corpus** (khi không có nhãn). Lấy mẫu các đoạn văn bản trong kho, cắt thành truy
   vấn giả dài bằng câu hỏi thật, ghi lại phân bố điểm hạng 1, rồi lấy trung vị làm mốc.

Cả hai đều tự sinh lại cho mọi miền mới: thêm một Domain Pack rồi chạy
`scripts/ingest/calibrate_scope.py` là có ngay tham chiếu riêng, không ai phải gõ ngưỡng nào.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

SCOPE_REFERENCE_FILENAME = "scope_reference.json"

# Khi KHÔNG có ví dụ gán nhãn, mốc tham chiếu lấy trung vị của phân bố "điểm hạng 1 khi truy
# vấn chắc chắn thuộc phạm vi": câu hỏi ghi điểm thấp hơn hẳn mức một truy vấn trong kho thường
# đạt được là dấu hiệu kho tài liệu không bao phủ nó.
SCOPE_PERCENTILE = 50.0

# Dưới mốc tham chiếu bao nhiêu lần thì coi là ngoài phạm vi. Tỷ lệ, không phải đơn vị điểm.
OUT_OF_SCOPE_RATIO = 1.0

BRANCH_DENSE = "dense"
BRANCH_SPARSE = "sparse"


@dataclass(frozen=True)
class ScopeSignal:
    """Kết luận về phạm vi cho một lượt truy vấn."""

    in_scope: bool
    ratio: float           # điểm hạng 1 / mốc tham chiếu
    top_score: float
    reference: float
    branch: str
    calibrated: bool       # False = chưa có tệp tham chiếu, không kết luận gì

    def header_vi(self) -> str:
        if not self.calibrated:
            return ""
        if self.in_scope:
            return (
                f"[PHẠM VI: câu hỏi nằm trong vùng kho tài liệu bao phủ "
                f"(đạt {self.ratio:.0%} mốc tham chiếu của corpus)]"
            )
        return (
            f"[PHẠM VI: ⚠️ câu hỏi nhiều khả năng NẰM NGOÀI kho tài liệu — điểm khớp tốt nhất "
            f"chỉ đạt {self.ratio:.0%} mốc tham chiếu của corpus. Hãy đọc kỹ nội dung lấy về: "
            f"nếu chúng không thật sự trả lời câu hỏi, hãy nói thẳng là chưa có căn cứ thay vì "
            f"suy diễn.]"
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "in_scope": self.in_scope,
            "ratio": round(self.ratio, 3),
            "top_score": round(self.top_score, 4),
            "reference": round(self.reference, 4),
            "branch": self.branch,
            "calibrated": self.calibrated,
        }


UNCALIBRATED = ScopeSignal(
    in_scope=True, ratio=0.0, top_score=0.0, reference=0.0, branch="", calibrated=False
)


def percentile(values: Sequence[float], pct: float) -> float:
    """Phân vị theo nội suy tuyến tính. Tự cài để không kéo thêm phụ thuộc chỉ vì một hàm."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


class ScopeReference:
    """Mốc tham chiếu phạm vi, đọc từ `data/processed/scope_reference.json`."""

    def __init__(self, processed_dir: str):
        self.path = os.path.join(processed_dir, SCOPE_REFERENCE_FILENAME)
        self._data: Optional[Dict[str, Dict[str, float]]] = None

    @property
    def data(self) -> Dict[str, Dict[str, float]]:
        if self._data is None:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f).get("branches", {})
            except (OSError, ValueError):
                # Chưa hiệu chuẩn: không kết luận gì về phạm vi, thay vì đoán bừa một ngưỡng.
                self._data = {}
        return self._data

    def available_for(self, branch: str) -> bool:
        return bool(self.data.get(branch, {}).get("reference"))

    def assess(self, top_score: float, branch: str) -> ScopeSignal:
        """So điểm hạng 1 của lượt truy vấn với mốc tham chiếu của nhánh tương ứng."""
        entry = self.data.get(branch) or {}
        reference = float(entry.get("reference") or 0.0)
        if reference <= 0.0:
            return UNCALIBRATED

        ratio = top_score / reference
        return ScopeSignal(
            in_scope=ratio >= OUT_OF_SCOPE_RATIO,
            ratio=ratio,
            top_score=top_score,
            reference=reference,
            branch=branch,
            calibrated=True,
        )


_shared_reference: Optional[ScopeReference] = None


def get_scope_reference(base_dir: Optional[str] = None) -> ScopeReference:
    """Mốc tham chiếu dùng chung (singleton)."""
    global _shared_reference
    if _shared_reference is None:
        if not base_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _shared_reference = ScopeReference(os.path.join(base_dir, "data", "processed"))
    return _shared_reference


def fit_threshold_from_labels(
    in_scope_scores: Sequence[float],
    out_scope_scores: Sequence[float],
) -> Dict[str, float]:
    """
    Chọn mốc tối đa hoá (tỷ lệ bắt đúng lạc đề − tỷ lệ báo nhầm câu hợp lệ) — chỉ số Youden's J.

    Ứng viên là chính các điểm quan sát được, nên không có lưới tham số nào phải gõ tay.
    """
    if not in_scope_scores or not out_scope_scores:
        return {}

    candidates = sorted({*in_scope_scores, *out_scope_scores})
    best = {"reference": 0.0, "recall": 0.0, "false_positive": 1.0, "youden_j": -1.0}

    for cut in candidates:
        caught = sum(1 for v in out_scope_scores if v < cut) / len(out_scope_scores)
        flagged = sum(1 for v in in_scope_scores if v < cut) / len(in_scope_scores)
        j = caught - flagged
        if j > best["youden_j"]:
            best = {
                "reference": round(float(cut), 6),
                "recall": round(caught, 4),
                "false_positive": round(flagged, 4),
                "youden_j": round(j, 4),
            }
    return best


def build_reference_payload(
    samples: Dict[str, List[float]],
    fitted: Optional[Dict[str, Dict[str, float]]] = None,
    pct: float = SCOPE_PERCENTILE,
) -> Dict[str, object]:
    """
    Dựng nội dung tệp tham chiếu.

    `samples`: điểm hạng 1 của các truy vấn giả theo từng nhánh (thống kê corpus).
    `fitted`: kết quả khớp từ ví dụ gán nhãn, nếu có — được ưu tiên làm `reference`.
    `pct`: phân vị dùng khi không có nhãn. Mỗi nhánh trả lời một câu hỏi khác nhau nên phân vị
    hợp lý cũng khác nhau — xem chú thích ở `scripts/ingest/calibrate_scope.py`.
    """
    fitted = fitted or {}
    branches: Dict[str, Dict[str, float]] = {}

    for branch, scores in samples.items():
        if not scores:
            continue
        entry: Dict[str, float] = {
            "reference": round(percentile(scores, pct), 6),
            "percentile": pct,
            "source": "corpus_statistics",
            "median": round(percentile(scores, 50.0), 6),
            "p25": round(percentile(scores, 25.0), 6),
            "p5": round(percentile(scores, 5.0), 6),
            "samples": len(scores),
        }
        fit = fitted.get(branch)
        if fit and fit.get("reference"):
            entry.update(fit)
            entry["source"] = "labelled_examples"
        branches[branch] = entry

    for branch, fit in fitted.items():
        if branch not in branches and fit.get("reference"):
            branches[branch] = {**fit, "source": "labelled_examples"}

    return {
        "default_percentile": pct,
        "out_of_scope_ratio": OUT_OF_SCOPE_RATIO,
        "branches": branches,
    }
