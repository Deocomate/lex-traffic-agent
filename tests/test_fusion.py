"""
Kiểm thử tầng hợp nhất thứ hạng và chọn kết quả (src/retrieval/fusion.py).

Toàn bộ là hàm thuần, không gọi mạng, nên chạy được ở mọi môi trường — đúng chỗ để chốt các
tính chất mà cả kiến trúc dựa vào: bất biến với thang điểm, và không hằng số nào phụ thuộc
corpus.
"""

from src.retrieval.fusion import (
    BAND_MODERATE,
    BAND_STRONG,
    BAND_WEAK,
    RRF_K,
    assess_confidence,
    max_possible_rrf,
    reciprocal_rank_fusion,
    select_by_separation,
    take_by_separation,
)


# ---------------------------------------------------------------------------
# RRF
# ---------------------------------------------------------------------------

def test_rrf_khong_trong_so_doi_xung():
    """Hai nhánh đối xứng (hạng 1+2 so với 2+1) phải cho điểm bằng nhau."""
    scores = reciprocal_rank_fusion({"dense": ["a", "b", "c"], "sparse": ["b", "a", "d"]})
    assert scores["a"] == scores["b"]
    assert scores["a"] > scores["c"]


def test_rrf_thuong_dong_thuan_giua_cac_nhanh():
    """Tài liệu xuất hiện ở cả hai nhánh phải xếp trên tài liệu chỉ có ở một nhánh."""
    scores = reciprocal_rank_fusion({"dense": ["x", "y"], "sparse": ["z", "x"]})
    assert scores["x"] > scores["z"]
    assert scores["x"] > scores["y"]


def test_rrf_chi_doc_thu_hang_khong_doc_diem():
    """Đổi thang điểm của một nhánh không được ảnh hưởng kết quả — RRF chỉ đọc thứ hạng."""
    a = reciprocal_rank_fusion({"dense": ["p", "q", "r"]})
    b = reciprocal_rank_fusion({"dense": ["p", "q", "r"]})
    assert a == b
    assert a["p"] == 1.0 / (RRF_K + 1)


def test_max_possible_rrf():
    assert max_possible_rrf(2) == 2 / (RRF_K + 1)
    assert max_possible_rrf(0) == 0.0


# ---------------------------------------------------------------------------
# Chọn theo vách rơi
# ---------------------------------------------------------------------------

def test_mot_dinh_ro_thi_giu_mot_ket_qua():
    cut, conf = select_by_separation([0.95, 0.31, 0.29, 0.28, 0.27], max_k=5)
    assert cut == 1
    assert conf.band == BAND_STRONG


def test_cum_ba_ket_qua_tot_thi_giu_ca_ba():
    """Ba kết quả mạnh rồi rơi hẳn: phải giữ cả ba và vẫn là độ tin cậy MẠNH."""
    cut, conf = select_by_separation([0.95, 0.92, 0.88, 0.30, 0.28], max_k=5)
    assert cut == 3
    assert conf.band == BAND_STRONG


def test_phan_bo_phang_li_la_tin_hieu_yeu():
    """Các ứng viên ngang điểm nhau = không có gì nổi bật = YẾU (dấu hiệu câu hỏi lạc đề)."""
    _, conf = select_by_separation([0.41, 0.40, 0.39, 0.39, 0.38], max_k=5)
    assert conf.band == BAND_WEAK


def test_doc_deu_la_tin_hieu_trung_binh():
    _, conf = select_by_separation([0.90, 0.75, 0.60, 0.45, 0.30], max_k=5)
    assert conf.band == BAND_MODERATE


def test_bat_bien_voi_thang_diem():
    """
    Tính chất quan trọng nhất: nhân toàn bộ điểm lên 1000 lần phải cho kết luận y hệt.

    Đây là thứ mà `SEMANTIC_FLOOR=0.58` không có — đổi embedding model là ngưỡng đó vô nghĩa.
    """
    nho = select_by_separation([0.95, 0.92, 0.88, 0.30, 0.28], max_k=5)
    lon = select_by_separation([950.0, 920.0, 880.0, 300.0, 280.0], max_k=5)
    assert nho[0] == lon[0]
    assert nho[1].band == lon[1].band
    assert round(nho[1].cliff, 9) == round(lon[1].cliff, 9)


def test_luon_giu_it_nhat_mot_ket_qua():
    """Tầng truy xuất không bao giờ được tự ý trả rỗng — quyền phán xét thuộc về Agent."""
    cut, _ = select_by_separation([0.1, 0.1, 0.1], max_k=5)
    assert cut >= 1


def test_ton_trong_max_k():
    cut, _ = select_by_separation([0.9, 0.8, 0.7, 0.6, 0.5, 0.4], max_k=3)
    assert cut <= 3


def test_danh_sach_rong():
    cut, conf = select_by_separation([], max_k=5)
    assert cut == 0
    assert conf.band == BAND_WEAK
    assert conf.pool == 0


def test_diem_khong_duong_khong_lam_vo_ham():
    cut, conf = select_by_separation([0.0, 0.0], max_k=5)
    assert cut >= 1
    assert conf.band == BAND_WEAK


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------

def test_take_by_separation_sap_xep_va_cat():
    items = [
        {"id": "c", "score": 0.30},
        {"id": "a", "score": 0.95},
        {"id": "b", "score": 0.28},
    ]
    kept, conf = take_by_separation(items, max_k=3)
    assert [d["id"] for d in kept] == ["a"]
    assert conf.band == BAND_STRONG


def test_header_vi_neu_ro_tin_hieu_cho_agent():
    conf = assess_confidence([0.41, 0.40, 0.39], kept=1)
    header = conf.header_vi()
    assert "ĐỘ TIN CẬY TRUY XUẤT" in header
    assert "YẾU" in header
