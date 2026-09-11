"""
Script đối soát toàn diện giữa dữ liệu Wikisource và tài liệu gốc trong data/raw_data.
So sánh các mốc điều khoản, số lượng điều, các phần thiếu sót trên Wikisource.
"""

import os
import re
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
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CACHE_DIR = os.path.join(PROCESSED_DIR, "ocr_cache")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw_data")


def audit_nd168():
    print("=" * 80)
    print("1. ĐỐI SOÁT NGHỊ ĐỊNH 168/2024/NĐ-CP: WIKISOURCE VS RAW PDF OCR (111 TRANG)")
    print("=" * 80)

    # 1. Wikisource JSON
    wiki_path = os.path.join(PROCESSED_DIR, "nghi_dinh_168_2024_structured.json")
    wiki_articles = {}
    if os.path.exists(wiki_path):
        with open(wiki_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for a in data.get("articles", []):
                wiki_articles[a["article_number"]] = a

    # 2. Raw OCR Full
    ocr_path = os.path.join(CACHE_DIR, "03_nghi_dinh_168_2024_nd_cp_full.md")
    with open(ocr_path, "r", encoding="utf-8") as f:
        ocr_text = f.read()

    # Tìm các Điều trong OCR
    ocr_articles_raw = re.findall(r'(?:^|\n)Điều\s+(\d{1,2})\.\s*([^\n\r]+)', ocr_text)
    ocr_articles = {int(num): title.strip() for num, title in ocr_articles_raw}

    print(f"Tổng số Điều trên Wikisource: {len(wiki_articles)} Điều")
    print(f"Tổng số Điều từ Raw PDF OCR:  {len(ocr_articles)} Điều")

    # Kiểm tra các điều vắng mặt
    missing_in_wiki = [n for n in sorted(ocr_articles.keys()) if n not in wiki_articles]
    print(f"Các Điều thiếu trên Wikisource: {missing_in_wiki if missing_in_wiki else 'Không thiếu số điều tổng quan'}")

    # Kiểm tra sâu các điều khoản quan trọng về chủ phương tiện & thẩm quyền
    print("\nChi tiết đối chiếu nội dung các Điều trọng yếu:")
    for check_num in [28, 32, 33, 34, 35, 36, 47, 50]:
        wiki_art = wiki_articles.get(check_num)
        ocr_title = ocr_articles.get(check_num, "N/A")
        wiki_clauses = len(wiki_art.get("clauses", [])) if wiki_art else 0

        # Đếm số Khoản trong OCR text của Điều này
        pattern = rf'Điều\s+{check_num}\..*?(?=Điều\s+{check_num + 1}\.|\Z)'
        m = re.search(pattern, ocr_text, re.DOTALL)
        ocr_clauses = 0
        if m:
            art_content = m.group(0)
            clause_matches = re.findall(r'\n\s*(\d{1,2})\.\s+[A-ZÀ-Ỹ]', art_content)
            ocr_clauses = len(set(clause_matches))

        print(f" - Điều {check_num:<2} ({ocr_title[:45]}...): Wikisource có {wiki_clauses} khoản | Raw OCR có {ocr_clauses} khoản")


def audit_luat35():
    print("\n" + "=" * 80)
    print("2. ĐỐI SOÁT LUẬT 35/2024/QH15 (ĐƯỜNG BỘ): WIKISOURCE VS RAW DIGITAL PDF")
    print("=" * 80)

    wiki_path = os.path.join(PROCESSED_DIR, "luat_35_2024_structured.json")
    with open(wiki_path, "r", encoding="utf-8") as f:
        wiki_data = json.load(f)
    wiki_articles = {a["article_number"]: a["article_title"] for a in wiki_data.get("articles", [])}

    pdf_path = os.path.join(RAW_DIR, "02_luat_35_2024_qh15_duong_bo.pdf")
    doc = fitz.open(pdf_path)
    full_text = "\n".join(p.get_text() for p in doc)
    pdf_arts = re.findall(r'Điều\s+(\d+)\.\s*([^\n]+)', full_text)
    pdf_articles = {int(num): title.strip() for num, title in pdf_arts}

    print(f"Tổng số Điều trên Wikisource: {len(wiki_articles)} Điều")
    print(f"Tổng số Điều từ Raw PDF Text: {len(pdf_articles)} Điều")

    title_diffs = []
    for num in sorted(pdf_articles.keys()):
        if num in wiki_articles:
            if wiki_articles[num].lower() != pdf_articles[num].lower():
                title_diffs.append((num, wiki_articles[num], pdf_articles[num]))

    print(f"Số Điều có tiêu đề khác biệt giữa Wikisource và PDF gốc: {len(title_diffs)}")
    for num, w_t, p_t in title_diffs[:5]:
        print(f" - Điều {num}: Wikisource='{w_t}' vs PDF='{p_t}'")


def audit_luat36():
    print("\n" + "=" * 80)
    print("3. ĐỐI SOÁT LUẬT 36/2024/QH15 (TRẬT TỰ ATGT): WIKISOURCE VS RAW OCR FULL")
    print("=" * 80)

    wiki_path = os.path.join(PROCESSED_DIR, "law_36_2024_structured.json")
    with open(wiki_path, "r", encoding="utf-8") as f:
        wiki_data = json.load(f)
    wiki_articles = []
    for c in wiki_data.get("chapters", []):
        wiki_articles.extend(c.get("articles", []))

    ocr_path = os.path.join(CACHE_DIR, "01_luat_36_2024_qh15_full.md")
    with open(ocr_path, "r", encoding="utf-8") as f:
        ocr_text = f.read()
    ocr_articles_raw = re.findall(r'(?:^|\n)Điều\s+(\d{1,2})\.\s*([^\n\r]+)', ocr_text)

    print(f"Tổng số Điều trên Wikisource: {len(wiki_articles)} Điều")
    print(f"Tổng số Điều từ Raw PDF OCR:  {len(ocr_articles_raw)} Điều")


def main():
    audit_nd168()
    audit_luat35()
    audit_luat36()


if __name__ == "__main__":
    main()
