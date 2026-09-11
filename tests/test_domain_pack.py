"""
Kiểm thử lớp Domain Pack — bài kiểm tra chốt cho mục tiêu "tổng quát hoá" của đợt refactor.

Phần quan trọng nhất nằm ở cuối: nạp một pack HOÀN TOÀN KHÁC miền (quy chế nhân sự nội bộ, dữ
liệu bịa, công cụ riêng) rồi chạy các đường đi chính của engine. Nếu engine còn sót tri thức
giao thông nướng cứng ở đâu, những bài test đó sẽ hỏng.
"""

import os

import pytest

from src.domain.pack import DomainPackError, load_domain_pack
from src.domain.registry import get_active_domain, set_active_domain

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture
def hr_pack():
    """Nạp pack kiểm thử, và LUÔN trả engine về miền mặc định sau khi chạy xong."""
    pack = load_domain_pack("demo_hr", base_dir=FIXTURES)
    set_active_domain(pack)
    try:
        yield pack
    finally:
        set_active_domain(None)


# ---------------------------------------------------------------------------
# Nạp pack
# ---------------------------------------------------------------------------

def test_mien_mac_dinh_la_giao_thong():
    domain = get_active_domain()
    assert domain.id == "vietnam_traffic"
    assert len(domain.document_ids) == 6


def test_bao_loi_ro_rang_khi_thieu_pack():
    with pytest.raises(DomainPackError) as err:
        load_domain_pack("khong_ton_tai", base_dir=FIXTURES)
    # Thông báo phải nêu đường dẫn và các miền hiện có, để sửa được ngay.
    assert "khong_ton_tai" in str(err.value)
    assert "demo_hr" in str(err.value)


def test_nhom_tai_lieu_suy_ra_tu_doc_type(hr_pack):
    """Không khai báo `groups` thì nhóm được suy ra từ `doc_type`, cộng nhóm `all`."""
    assert set(hr_pack.groups) == {"noi_quy", "quy_che", "all"}
    assert len(hr_pack.groups["all"]) == 2


def test_phan_giai_alias_va_nhom(hr_pack):
    assert hr_pack.resolve_doc_ids(["qc_01"]) == {"qc_01_noi_quy_lao_dong"}
    assert hr_pack.resolve_doc_ids(["quy_che"]) == {"qc_02_quy_che_luong"}
    assert hr_pack.resolve_doc_ids(["all"]) == set(hr_pack.document_ids)
    assert hr_pack.resolve_doc_ids(None) is None


def test_policy_rieng_cua_mien(hr_pack):
    assert hr_pack.policy.cache_similarity == 0.9
    assert hr_pack.policy.max_tool_turns == 3


# ---------------------------------------------------------------------------
# Engine chạy với miền khác
# ---------------------------------------------------------------------------

def test_system_prompt_lay_tu_pack_va_ghep_phan_engine(hr_pack):
    from src.prompts import get_system_prompt

    prompt = get_system_prompt()
    assert "Quy chế Nhân sự" in prompt              # phần của miền
    assert "ĐỘ TIN CẬY TRUY XUẤT" in prompt         # phần chung của engine
    assert "giao thông" not in prompt.lower()       # KHÔNG còn dấu vết miền cũ


def test_bo_cong_cu_do_pack_quyet_dinh(hr_pack):
    schema = hr_pack.tools_schema
    assert [t["function"]["name"] for t in schema] == ["policy_search"]
    assert "penalty_lookup" not in hr_pack.tool_names()


def test_thuc_thi_cong_cu_cua_mien_khac(hr_pack):
    """Engine gọi được công cụ của miền mới mà không biết trước nó tồn tại."""
    from src.graph.retrieve import execute_tool_call

    raw, evidences, step = execute_tool_call("policy_search", {"question": "nghỉ thai sản"})

    assert "180 ngày" in raw
    assert step["action"] == "policy_search"
    # Không khai báo evidence_builder -> engine dựng bằng chứng chung, vẫn giữ nguyên văn.
    assert evidences and evidences[0]["raw_tool_output"] == raw


def test_cong_cu_khong_ton_tai_bao_loi_ro_rang(hr_pack):
    from src.graph.retrieve import execute_tool_call

    raw, evidences, _ = execute_tool_call("penalty_lookup", {})
    assert "không tồn tại" in raw
    assert "policy_search" in raw          # gợi ý công cụ hiện có
    assert evidences == []


def test_tin_hieu_truy_van_theo_lexicon_cua_mien(hr_pack):
    from src.graph.query_signals import detect_signals

    intents, entities = detect_signals("nhân viên nghỉ thai sản bao nhiêu ngày")
    assert "leave" in intents
    assert entities == ["nhan_vien"]

    # Không khớp gì -> rơi về ý định mặc định của miền
    assert detect_signals("xin chào")[0] == ["policy"]


def test_tu_dien_dong_thuong_theo_mien(hr_pack):
    from src.retrieval.vi_text import expand_query, preferred_entities

    expanded, added = expand_query("cho tôi hỏi nghỉ đẻ")
    assert "nghỉ thai sản" in expanded and added == ["nghỉ thai sản"]
    assert preferred_entities("trưởng phòng xin nghỉ") == ("Quản lý",)


def test_kiem_chung_so_lieu_theo_lop_cua_mien(hr_pack):
    """
    Lớp số liệu của miền nhân sự (số tiền, số ngày nghỉ) dùng đúng cơ chế của engine.

    Engine không hề biết "ngày nghỉ" là gì — nó chỉ chạy `contextual_count` mà pack khai báo.
    """
    from src.answer_guard import find_ungrounded_figures

    source = "Nghỉ thai sản 180 ngày. Trợ cấp một lần: 5.000.000 đồng."

    assert find_ungrounded_figures("Được nghỉ 180 ngày, trợ cấp 5 triệu đồng.", [source]) == []
    assert find_ungrounded_figures("Được nghỉ 999 ngày.", [source]) == ["999 ngày nghỉ"]
    assert find_ungrounded_figures("Trợ cấp 9.000.000 đồng.", [source]) == ["9.000.000 đồng"]


def test_dau_hieu_trich_dan_theo_mien(hr_pack):
    """Miền nhân sự dùng QC-01/Mục thay cho Điều/Khoản/Nghị định của miền giao thông."""
    from src.graph.verify import find_missing_citation

    source = "QC-01, Điều 12: nghỉ thai sản 180 ngày."

    assert find_missing_citation("Theo Điều 12 QC-01, được nghỉ 180 ngày.", [source]) == []
    assert find_missing_citation("Theo quy định hiện hành thì được nghỉ.", [source]) != []


def test_doi_pack_xong_tro_lai_mien_mac_dinh(hr_pack):
    """Sau khi fixture dọn dẹp, engine phải quay về miền giao thông (kiểm ở test kế tiếp)."""
    assert get_active_domain().id == "demo_hr"


def test_mien_mac_dinh_duoc_khoi_phuc():
    """Chạy sau test trên: xác nhận `set_active_domain(None)` thật sự khôi phục trạng thái."""
    assert get_active_domain().id == "vietnam_traffic"
