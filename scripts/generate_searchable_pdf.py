"""
Script bổ sung lớp text ẩn (searchable text layer) cho các file PDF scan tiếng Việt.
Sử dụng PyMuPDF chèn text layer vô hình (render_mode=3) với font Arial Unicode tiếng Việt.
Nhờ đó các file PDF scan trở nên tìm kiếm được (Ctrl+F), bôi đen copy được,
và cho phép mọi thư viện PDF (fitz, pdfplumber, pypdf, LangChain PyPDFLoader) trích xuất trực tiếp.
"""

import os
import sys
import fitz

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw_data")
CACHE_DIR = os.path.join(BASE_DIR, "data", "processed", "ocr_cache")
OUT_DIR = os.path.join(BASE_DIR, "data", "digitized_pdf")
FONT_PATH = r"C:\Windows\Fonts\arial.ttf"


def clean_markdown_for_text_layer(md_text: str) -> str:
    """Làm sạch các định dạng markdown cơ bản để text layer trong PDF tự nhiên nhất"""
    lines = md_text.splitlines()
    cleaned = []
    for l in lines:
        s = l.strip()
        if not s or s.startswith("<!--") or s.startswith("---"):
            continue
        # Bỏ dấu # tiêu đề và ** in đậm
        s = s.lstrip("#").strip()
        s = s.replace("**", "").replace("*", "")
        # Với bảng biểu markdown, thay | bằng khoảng cách tab
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s[1:-1].split("|")]
            if all(set(c).issubset({"-", ":", " "}) for c in cells):
                continue  # Dòng kẻ ngang bảng
            s = "  |  ".join(cells)
        cleaned.append(s)
    return "\n".join(cleaned)


def make_searchable_pdf(pdf_filename: str, doc_id: str, out_filename: str = None) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    src_pdf = os.path.join(RAW_DIR, pdf_filename)
    if not out_filename:
        out_filename = pdf_filename.replace(".pdf", "_searchable.pdf")
    out_pdf = os.path.join(OUT_DIR, out_filename)

    doc = fitz.open(src_pdf)
    total_pages = len(doc)
    print(f"\n📄 Đang xử lý tạo searchable PDF cho: {pdf_filename} ({total_pages} trang)...")

    # Nếu tài liệu đã có text layer số hóa gốc (Luật 35, QCVN 41)
    page_cache_dir = os.path.join(CACHE_DIR, doc_id)
    if not os.path.exists(page_cache_dir) or doc_id in ("02_luat_35_2024_qh15", "06_qcvn_41_2019_bgtvt"):
        existing_chars = sum(len(p.get_text()) for p in doc)
        if existing_chars > 50000:
            print(f"   ℹ️ Tài liệu đã có lớp text số hóa gốc ({existing_chars:,} ký tự). Đang tối ưu hóa và xuất bản...")
            doc.save(out_pdf, garbage=3, deflate=True)
            doc.close()
            print(f"✅ Hoàn tất lưu bản số hóa: {out_pdf}")
            return out_pdf

    if not os.path.exists(page_cache_dir):
        raise FileNotFoundError(f"Chưa có cache OCR cho {doc_id} tại {page_cache_dir}")

    inserted_pages = 0
    total_chars = 0

    for i in range(total_pages):
        page = doc[i]
        cache_file = os.path.join(page_cache_dir, f"page_{i + 1:03d}.md")
        if not os.path.exists(cache_file):
            continue

        with open(cache_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

        text_layer = clean_markdown_for_text_layer(raw_text)
        if not text_layer:
            continue

        rect = page.rect
        page.insert_font(fontname="arial", fontfile=FONT_PATH)
        # render_mode=3: văn bản vô hình (invisible text layer chuẩn PDF specification cho OCR)
        page.insert_textbox(rect, text_layer, fontname="arial", fontsize=9, render_mode=3)
        inserted_pages += 1
        total_chars += len(text_layer)

    doc.save(out_pdf, garbage=3, deflate=True)
    doc.close()

    # Kiểm tra xác nhận bằng cách mở lại file đã tạo và get_text()
    check_doc = fitz.open(out_pdf)
    extracted_chars = sum(len(p.get_text()) for p in check_doc)
    check_doc.close()

    print(f"✅ Hoàn tất: {out_pdf}")
    print(f"   - Số trang có text layer: {inserted_pages}/{total_pages}")
    print(f"   - Tổng số ký tự trích xuất được: {extracted_chars:,} ký tự")

    return out_pdf


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tạo searchable PDF từ OCR cache")
    parser.add_argument("--doc", type=str,
                        choices=["01_luat36", "02_luat35", "03_nd168", "04_tt31", "05_tt73", "06_qcvn41", "all"],
                        default="all")
    args = parser.parse_args()

    doc_map = {
        "01_luat36": ("01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong.pdf", "01_luat_36_2024_qh15"),
        "02_luat35": ("02_luat_35_2024_qh15_duong_bo.pdf", "02_luat_35_2024_qh15"),
        "03_nd168": ("03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham.pdf", "03_nghi_dinh_168_2024_nd_cp"),
        "04_tt31": ("04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach.pdf", "04_thong_tu_31_2019_tt_bgtvt"),
        "05_tt73": ("05_thong_tu_73_2024_tt_bca_tuan_tra_csgt.pdf", "05_thong_tu_73_2024_tt_bca"),
        "06_qcvn41": ("06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo.pdf", "06_qcvn_41_2019_bgtvt"),
    }

    targets = [args.doc] if args.doc != "all" else list(doc_map.keys())
    for t in targets:
        src, did = doc_map[t]
        make_searchable_pdf(src, did)
