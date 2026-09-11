"""
Kiểm thử lớp phán đoán phạm vi (src/retrieval/scope.py).

Phần cuối là bài kiểm tra QUAN TRỌNG NHẤT của cả đợt refactor: gỡ bỏ `SEMANTIC_FLOOR = 0.58`
đồng nghĩa với việc tháo đúng lớp đang chặn câu hỏi lạc đề. Bài test đó chạy lại trên chính bộ
16 câu ngoài phạm vi đã gán nhãn để bảo đảm mốc đo từ corpus thay thế được nó.
"""

import json
import os

import pytest

from src.retrieval.scope import (
    OUT_OF_SCOPE_RATIO,
    BRANCH_SPARSE,
    ScopeReference,
    ScopeSignal,
    build_reference_payload,
    fit_threshold_from_labels,
    get_scope_reference,
    percentile,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARK = os.path.join(BASE_DIR, "data", "benchmark", "qa_testset_v2.json")


# ---------------------------------------------------------------------------
# Hàm thuần
# ---------------------------------------------------------------------------

def test_percentile_noi_suy_tuyen_tinh():
    assert percentile([10, 20, 30, 40], 50.0) == 25.0
    assert percentile([5], 99.0) == 5
    assert percentile([], 50.0) == 0.0


def test_khop_moc_tu_vi_du_gan_nhan_tach_hai_nhom():
    fit = fit_threshold_from_labels(in_scope_scores=[50, 60, 70, 80], out_scope_scores=[10, 20, 30])
    assert fit["recall"] == 1.0
    assert fit["false_positive"] == 0.0
    assert 30 < fit["reference"] <= 50


def test_khong_co_nhan_thi_khong_khop():
    assert fit_threshold_from_labels([], [1, 2]) == {}
    assert fit_threshold_from_labels([1, 2], []) == {}


def test_uu_tien_moc_khop_tu_nhan_hon_thong_ke_corpus():
    payload = build_reference_payload(
        samples={"sparse": [10.0, 20.0, 30.0]},
        fitted={"sparse": {"reference": 99.0, "recall": 1.0, "false_positive": 0.1}},
    )
    entry = payload["branches"]["sparse"]
    assert entry["reference"] == 99.0
    assert entry["source"] == "labelled_examples"


def test_chua_hieu_chuan_thi_khong_ket_luan_gi(tmp_path):
    """Thiếu tệp tham chiếu phải im lặng, không được đoán bừa một ngưỡng."""
    ref = ScopeReference(str(tmp_path))
    signal = ref.assess(top_score=123.0, branch=BRANCH_SPARSE)
    assert signal.calibrated is False
    assert signal.in_scope is True          # không kết luận = không chặn
    assert signal.header_vi() == ""         # không hiển thị gì cho Agent


def test_header_canh_bao_khi_ngoai_pham_vi():
    trong = ScopeSignal(True, 1.5, 60.0, 40.0, BRANCH_SPARSE, True)
    ngoai = ScopeSignal(False, 0.3, 12.0, 40.0, BRANCH_SPARSE, True)
    assert "NẰM NGOÀI" not in trong.header_vi()
    assert "NẰM NGOÀI" in ngoai.header_vi()


# ---------------------------------------------------------------------------
# Hồi quy trên dữ liệu thật
# ---------------------------------------------------------------------------

def _load_benchmark():
    with open(BENCHMARK, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("items") or raw.get("questions") or []
    return (
        [i for i in items if not i.get("is_out_of_scope")],
        [i for i in items if i.get("is_out_of_scope")],
    )


@pytest.mark.skipif(not os.path.exists(BENCHMARK), reason="chưa có bộ benchmark")
def test_chan_duoc_cau_hoi_lac_de_khong_can_nguong_go_tay():
    """
    Bài test chốt của đợt refactor.

    `SEMANTIC_FLOOR = 0.58` từng chặn 100% câu hỏi ngoài ngành. Nó đã bị gỡ vì là con số gõ tay
    chỉ đúng với đúng corpus và đúng embedding model này. Mốc thay thế được ĐO từ corpus và
    khớp từ ví dụ gán nhãn — bài test này bảo đảm nó thật sự làm được việc đó.

    Chạy trên nhánh BM25 vì nhánh đó không cần mạng.
    """
    from src.retrieval.sparse import SparseIndex

    index = SparseIndex(BASE_DIR)
    reference = get_scope_reference(BASE_DIR)
    if not index.available or not reference.available_for(BRANCH_SPARSE):
        pytest.skip("chưa dựng chỉ mục BM25 hoặc chưa chạy calibrate_scope.py")

    in_scope, out_scope = _load_benchmark()

    def flagged(question: str) -> bool:
        hits = index.search_chunks(question, top_k=1)
        top = float(hits[0].get("score", 0.0)) if hits else 0.0
        return not reference.assess(top, BRANCH_SPARSE).in_scope

    caught = sum(1 for q in out_scope if flagged(q["question"]))
    false_alarms = sum(1 for q in in_scope if flagged(q["question"]))

    # Bắt được toàn bộ câu lạc đề — đúng mức mà ngưỡng gõ tay cũ đạt được.
    assert caught == len(out_scope), f"chỉ bắt được {caught}/{len(out_scope)} câu lạc đề"

    # Báo nhầm phải ở mức chấp nhận được. Đây chỉ là CẢNH BÁO gắn kèm kết quả cho Agent đọc,
    # không phải bộ lọc chặn — nên một phần báo nhầm rẻ hơn nhiều so với việc bỏ lọt câu lạc đề.
    assert false_alarms / len(in_scope) <= 0.30


@pytest.mark.skipif(not os.path.exists(BENCHMARK), reason="chưa có bộ benchmark")
def test_tra_muc_phat_khong_tra_loi_cau_lac_de():
    """
    Lớp phòng vệ quan trọng nhất về mặt an toàn: câu hỏi lạc đề không được ra mức phạt nào.

    Một con số tiền phạt sai nguy hiểm hơn hẳn câu "chưa tra được", vì người dùng có thể hành
    động theo nó mà không có cách nào tự phát hiện là nó bịa.
    """
    from src.tools.penalty_lookup import PenaltyLookup

    lookup = PenaltyLookup(BASE_DIR)
    if not lookup.chunks:
        pytest.skip("chưa có penalty_chunks.jsonl")

    _in_scope, out_scope = _load_benchmark()
    leaked = [q["question"] for q in out_scope if lookup._search_by_keyword(q["question"])]

    # Mức của bản gốc (ngưỡng gõ tay SCORE_FLOOR/COVERAGE_FLOOR) là lọt 1/16.
    assert len(leaked) <= 1, f"lọt {len(leaked)}/{len(out_scope)} câu lạc đề: {leaked}"
