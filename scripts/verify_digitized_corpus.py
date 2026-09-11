"""
BỘ KIỂM THỬ VÀ XÁC THỰC TOÀN DIỆN HỆ THỐNG SỐ HÓA PHÁP LUẬT GIAO THÔNG
Kiểm tra 4 tiêu chuẩn bắt buộc:
1. Kiểm tra 6/6 file Searchable PDF trong data/digitized_pdf (100% số trang có text layer).
2. Kiểm tra 6/6 file JSON cấu trúc trong data/processed (Đầy đủ và liên tục số Điều).
3. Kiểm tra tính toàn vẹn của toàn bộ ảnh minh họa (Không có ảnh 404, file hợp lệ trên đĩa).
4. Kiểm tra tập RAG Chunks hợp nhất all_legal_chunks.jsonl (Schema chuẩn, metadata phong phú).
"""

import os
import sys
import json
import fitz
from typing import Dict, Any, List

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGITIZED_DIR = os.path.join(BASE_DIR, "data", "digitized_pdf")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
IMAGES_DIR = os.path.join(BASE_DIR, "data", "images", "qcvn_41")


def test_searchable_pdfs() -> bool:
    print("\n" + "=" * 80)
    print("TIÊU CHÍ 1: KIỂM TRA LỚP SEARCHABLE TEXT LAYER CỦA 6/6 FILE PDF")
    print("=" * 80)

    expected_docs = [
        ("01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong_searchable.pdf", 68),
        ("02_luat_35_2024_qh15_duong_bo_searchable.pdf", 69),
        ("03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham_searchable.pdf", 111),
        ("04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach_searchable.pdf", 6),
        ("05_thong_tu_73_2024_tt_bca_tuan_tra_csgt_searchable.pdf", 41),
        ("06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo_searchable.pdf", 211),
    ]

    all_passed = True
    total_chars_all = 0

    for filename, exp_pages in expected_docs:
        filepath = os.path.join(DIGITIZED_DIR, filename)
        if not os.path.exists(filepath):
            print(f"❌ THIẾU FILE: {filename}")
            all_passed = False
            continue

        doc = fitz.open(filepath)
        page_count = len(doc)
        pages_with_text = sum(1 for p in doc if len(p.get_text().strip()) > 10)
        total_chars = sum(len(p.get_text()) for p in doc)
        total_chars_all += total_chars
        doc.close()

        status = "✅ PASS" if (page_count == exp_pages and pages_with_text == exp_pages) else "❌ FAIL"
        if status != "✅ PASS":
            all_passed = False

        print(f"{status} {filename:<65}: {page_count}/{exp_pages} trang ({pages_with_text} trang có text, {total_chars:,} ký tự)")

    print(f"\n📊 Tổng số ký tự text layer toàn bộ 6 file PDF: {total_chars_all:,} ký tự")
    return all_passed


def test_structured_jsons() -> bool:
    print("\n" + "=" * 80)
    print("TIÊU CHÍ 2: KIỂM TRA ĐỘ PHỦ VÀ TÍNH TOÀN VẸN CỦA 6/6 FILE JSON CẤU TRÚC")
    print("=" * 80)

    expected_jsons = [
        ("01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong_structured.json", 9, 89),
        ("02_luat_35_2024_qh15_duong_bo_structured.json", 6, 86),
        ("03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham_structured.json", 4, 55),
        ("04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach_structured.json", 3, 13),
        ("05_thong_tu_73_2024_tt_bca_tuan_tra_csgt_structured.json", 5, 33),
        ("06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo_structured.json", 16, 90),
    ]

    all_passed = True

    for filename, exp_chaps, exp_arts in expected_jsons:
        filepath = os.path.join(PROCESSED_DIR, filename)
        if not os.path.exists(filepath):
            print(f"❌ THIẾU FILE: {filename}")
            all_passed = False
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        chaps = data.get("total_chapters", len(data.get("chapters", [])))
        arts = data.get("articles", [])
        art_nums = [a["article_number"] for a in arts]
        missing = [i for i in range(1, exp_arts + 1) if i not in art_nums]

        status = "✅ PASS" if (chaps == exp_chaps and len(arts) == exp_arts and not missing) else "❌ FAIL"
        if status != "✅ PASS":
            all_passed = False

        print(f"{status} {filename:<65}")
        print(f"   - Số Chương: {chaps}/{exp_chaps} | Số Điều: {len(arts)}/{exp_arts}")
        if missing:
            print(f"   - ⚠️ Thiếu Điều: {missing}")

    return all_passed


def test_illustrations_integrity() -> bool:
    print("\n" + "=" * 80)
    print("TIÊU CHÍ 3: KIỂM TRA TÍNH TOÀN VẸN VÀ TỒN TẠI CỦA TẤT CẢ ẢNH MINH HỌA")
    print("=" * 80)

    catalog_path = os.path.join(PROCESSED_DIR, "illustrations_catalog.json")
    if not os.path.exists(catalog_path):
        print(f"❌ THIẾU FILE: {catalog_path}")
        return False

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    print(f"📋 Tổng số ảnh trong catalog: {len(catalog)} ảnh")

    broken_images = 0
    total_bytes = 0

    for item in catalog:
        rel_path = item.get("image_path")
        if not rel_path:
            broken_images += 1
            continue
        abs_path = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(abs_path) or os.path.getsize(abs_path) < 100:
            broken_images += 1
            print(f"   ❌ Ảnh lỗi hoặc không tồn tại: {rel_path}")
        else:
            total_bytes += os.path.getsize(abs_path)

    signs_path = os.path.join(PROCESSED_DIR, "traffic_signs.jsonl")
    signs_with_img = 0
    signs_broken = 0
    if os.path.exists(signs_path):
        with open(signs_path, "r", encoding="utf-8") as f:
            for line in f:
                s = json.loads(line)
                if s.get("has_illustration"):
                    signs_with_img += 1
                    ip = os.path.join(BASE_DIR, s["image_path"])
                    if not os.path.exists(ip):
                        signs_broken += 1

    status = "✅ PASS" if (broken_images == 0 and signs_broken == 0) else "❌ FAIL"
    print(f"{status} Kiểm tra tồn tại đĩa: {len(catalog) - broken_images}/{len(catalog)} ảnh hợp lệ ({total_bytes/1024/1024:.2f} MB)")
    print(f"{status} Biển báo có liên kết ảnh: {signs_with_img} biển ({signs_broken} link hỏng)")

    return (broken_images == 0 and signs_broken == 0)


def test_rag_chunks() -> bool:
    print("\n" + "=" * 80)
    print("TIÊU CHÍ 4: KIỂM TRA TẬP RAG CHUNKS HỢP NHẤT (ALL_LEGAL_CHUNKS.JSONL)")
    print("=" * 80)

    chunks_path = os.path.join(PROCESSED_DIR, "all_legal_chunks.jsonl")
    if not os.path.exists(chunks_path):
        print(f"❌ THIẾU FILE: {chunks_path}")
        return False

    chunks = []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if line.strip():
                chunks.append(json.loads(line))

    empty_content = 0
    missing_meta = 0
    with_illustrations = 0

    doc_distribution = {}

    for c in chunks:
        if not c.get("page_content") or len(c["page_content"].strip()) < 10:
            empty_content += 1
        meta = c.get("metadata", {})
        if not meta.get("doc_id") or not meta.get("doc_name"):
            missing_meta += 1
        if meta.get("has_illustration"):
            with_illustrations += 1
        doc_id = meta.get("doc_id", "unknown")
        doc_distribution[doc_id] = doc_distribution.get(doc_id, 0) + 1

    passed = (empty_content == 0 and missing_meta == 0 and len(chunks) > 1000)
    status = "✅ PASS" if passed else "❌ FAIL"

    print(f"{status} Tổng số RAG chunks: {len(chunks):,} chunks")
    print(f"   - Không có chunk rỗng ({empty_content} lỗi)")
    print(f"   - Không thiếu metadata cốt lõi ({missing_meta} lỗi)")
    print(f"   - Số chunks có gắn ảnh minh họa: {with_illustrations} chunks")
    print("\n📊 Phân bố chunks theo tài liệu:")
    for doc_id, count in sorted(doc_distribution.items()):
        print(f"   - {doc_id:<35}: {count:>4} chunks")

    return passed


def main():
    print("=" * 80)
    print("BẮT ĐẦU BỘ KIỂM THỬ TOÀN VẸN DỮ LIỆU SỐ HÓA GIAO THÔNG 2025")
    print("=" * 80)

    p1 = test_searchable_pdfs()
    p2 = test_structured_jsons()
    p3 = test_illustrations_integrity()
    p4 = test_rag_chunks()

    print("\n" + "=" * 80)
    print("KẾT QUẢ TỔNG HỢP KIỂM THỬ HỆ THỐNG")
    print("=" * 80)
    print(f"1. Searchable Text Layer PDF : {'✅ PASS' if p1 else '❌ FAIL'}")
    print(f"2. JSON Cấu Trúc Toàn Diện   : {'✅ PASS' if p2 else '❌ FAIL'}")
    print(f"3. Hình Ảnh Minh Họa Cắt Crop: {'✅ PASS' if p3 else '❌ FAIL'}")
    print(f"4. RAG Chunks Hợp Nhất       : {'✅ PASS' if p4 else '❌ FAIL'}")

    if p1 and p2 and p3 and p4:
        print("\n🎉🎉🎉 TOÀN BỘ 4 HẠNG MỤC ĐẠT CHUẨN 100%! HỆ THỐNG SẴN SÀNG CHO VECTOR EMBEDDING!")
        return 0
    else:
        print("\n⚠️ Có hạng mục chưa đạt yêu cầu. Vui lòng kiểm tra log chi tiết ở trên.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
