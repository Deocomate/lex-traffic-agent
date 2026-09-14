"""
Kiểm thử cho node xây dựng nguồn dẫn chứng (Phase 5).
Đảm bảo build_sources_from_evidence chạy trơn tru với mọi loại nguồn (law, penalty, sign, speed),
không bị lỗi thiếu biến môi trường hoặc hàm chưa định nghĩa.
"""

import pytest
from src.graph.sources import build_sources_from_evidence


def test_build_sources_law_evidence():
    """Kiểm tra xử lý bằng chứng dạng văn bản luật."""
    evidences = [
        {
            "source": "law",
            "doc_id": "01_luat_36_2024_qh15",
            "header": "Điều 57. Giấy phép lái xe",
            "citation": "Luật 36/2024 - Điều 57",
        }
    ]
    sources = build_sources_from_evidence(evidences)
    assert len(sources) == 1
    src = sources[0]
    assert src["source_type"] == "law"
    assert src["article_number"] == 57
    assert "Điều 57" in src["article_header"]


def test_build_sources_penalty_evidence():
    """Kiểm tra xử lý bằng chứng dạng mức phạt nghị định."""
    evidences = [
        {
            "source": "penalty",
            "citation": "[Ô tô] Điểm a Khoản 3 Điều 6",
            "content": (
                "Hành vi: Chạy quá tốc độ từ 5 đến dưới 10 km/h\n"
                "Mức phạt tiền: 800.000 - 1.000.000 đồng\n"
                "Trừ điểm GPLX: Không"
            ),
        }
    ]
    sources = build_sources_from_evidence(evidences)
    assert len(sources) == 1
    src = sources[0]
    assert src["source_type"] == "decree"
    assert src["vehicle"] == "Ô tô"
    assert "800.000" in src["fine_text"]


def test_build_sources_sign_evidence():
    """Kiểm tra xử lý bằng chứng dạng biển báo."""
    evidences = [
        {
            "source": "sign",
            "header": "Biển P.102: Cấm đi ngược chiều",
            "image_path": "/static/signs/P102.png",
        }
    ]
    sources = build_sources_from_evidence(evidences)
    assert len(sources) == 1
    src = sources[0]
    assert src["source_type"] == "sign"
    assert src["sign_code"] == "P.102"
    assert src["sign_name"] == "Cấm đi ngược chiều"
