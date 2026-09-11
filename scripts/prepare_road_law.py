"""
Trích xuất và cấu trúc hóa LUẬT ĐƯỜNG BỘ 2024 (Luật số 35/2024/QH15, hiệu lực 01/01/2025).

Phạm vi khác hẳn Luật 36/2024: Luật 35 điều chỉnh kết cấu hạ tầng đường bộ, đường cao tốc,
thu phí, và điều kiện kinh doanh vận tải (taxi, xe buýt, xe hợp đồng, xe công nghệ) — nhóm câu
hỏi mà trước đây hệ thống không có dữ liệu để trả lời.

Nguồn: vi.wikisource, đối soát số hiệu và tiêu đề từng Điều với PDF gốc
data/raw_data/02_luat_35_2024_qh15_duong_bo.pdf (PDF này có lớp text nên đối soát được).

Xuất ra:
1. data/processed/luat_35_2024_structured.json — cây Chương / Điều / Khoản / Điểm
2. data/processed/luat_35_articles.jsonl       — mỗi Điều một bản ghi toàn văn (parent chunk)
"""

import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legal_text_parser import fetch_wikisource, parse_articles, pdf_article_titles

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "processed")
SOURCE_PDF = os.path.join(BASE_DIR, "data", "raw_data", "02_luat_35_2024_qh15_duong_bo.pdf")

DOC_ID = "luat_35_2024"
DOC_NAME = "Luật 35/2024/QH15"
DOC_FULL_NAME = "Luật Đường bộ (Luật số 35/2024/QH15)"
DATE_EFFECTIVE = "01/01/2025"

PAGE_PREFIX = "Luật Đường bộ nước Cộng hòa xã hội chủ nghĩa Việt Nam 2024"
CHAPTERS = [
    ("I", "NHỮNG QUY ĐỊNH CHUNG"),
    ("II", "KẾT CẤU HẠ TẦNG ĐƯỜNG BỘ"),
    ("III", "ĐƯỜNG BỘ CAO TỐC"),
    ("IV", "VẬN TẢI ĐƯỜNG BỘ"),
    ("V", "QUẢN LÝ NHÀ NƯỚC VỀ HOẠT ĐỘNG ĐƯỜNG BỘ"),
    ("VI", "ĐIỀU KHOẢN THI HÀNH"),
]

EXPECTED_ARTICLES = 86


def build_article_chunks(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dựng bản ghi toàn văn từng Điều để hiển thị và làm ngữ cảnh cho LLM"""
    chunks = []
    for article in articles:
        body_parts = [article["intro"]] if article.get("intro") else []
        for clause in article["clauses"]:
            body_parts.append(f"{clause['clause_number']}. {clause['text']}")
            body_parts.extend(f"   {p['point_letter']}) {p['text']}" for p in clause["points"])

        header = f"Điều {article['article_number']}. {article['article_title']}"
        chunks.append({
            "id": f"{DOC_ID}_dieu_{article['article_number']:02d}",
            "doc_id": DOC_ID,
            "doc_name": DOC_NAME,
            "page_content": "\n".join([f"=== {header} ===", ""] + body_parts),
            "metadata": {
                "article_number": article["article_number"],
                "article_title": article["article_title"],
                "article_header": header,
                "chapter_id": article["chapter_roman"],
                "chapter_title": article["chapter_title"],
                "clause_count": len(article["clauses"])
            }
        })
    return chunks


def validate(articles: List[Dict[str, Any]]) -> List[str]:
    """Đối soát bản số hóa với PDF gốc; rỗng nghĩa là dữ liệu đạt"""
    errors: List[str] = []
    numbers = [a["article_number"] for a in articles]

    if len(numbers) != EXPECTED_ARTICLES:
        errors.append(f"Parse được {len(numbers)} Điều, kỳ vọng {EXPECTED_ARTICLES}")
    missing = [n for n in range(1, EXPECTED_ARTICLES + 1) if n not in numbers]
    if missing:
        errors.append(f"Thiếu Điều: {missing}")
    # Điều chỉ gồm một đoạn văn (Phạm vi điều chỉnh, Hiệu lực thi hành) là hợp lệ,
    # nhưng Điều rỗng hoàn toàn nghĩa là parser đã mất nội dung.
    empty = [a["article_number"] for a in articles if not a["clauses"] and not a.get("intro")]
    if empty:
        errors.append(f"Điều không có nội dung: {empty}")

    # Đối soát tiêu đề với PDF gốc — bắt trường hợp bản số hóa thiếu hoặc lệch Điều
    pdf_titles = pdf_article_titles(SOURCE_PDF)
    if not pdf_titles:
        print("   [Bỏ qua đối soát PDF: không đọc được lớp text]")
        return errors

    mismatched = []
    for article in articles:
        pdf_title = pdf_titles.get(article["article_number"])
        if not pdf_title:
            mismatched.append(f"Điều {article['article_number']} không có trong PDF")
            continue
        # So khớp 20 ký tự đầu sau khi bỏ dấu câu cuối: PDF hay xuống dòng giữa tiêu đề dài,
        # và bản số hóa đôi khi thêm dấu chấm cuối tiêu đề.
        def key(title: str) -> str:
            return title.rstrip(" .;:").lower()[:20]

        if key(pdf_title) != key(article["article_title"]):
            mismatched.append(
                f"Điều {article['article_number']}: wikisource '{article['article_title'][:40]}' "
                f"≠ PDF '{pdf_title[:40]}'"
            )
    if mismatched:
        errors.extend(mismatched[:10])
    else:
        print(f"   [Đối soát PDF: {len(pdf_titles)} tiêu đề Điều khớp hoàn toàn]")

    return errors


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 78)
    print(f"  TRÍCH XUẤT {DOC_FULL_NAME} — hiệu lực {DATE_EFFECTIVE}")
    print("=" * 78)

    all_articles: List[Dict[str, Any]] = []

    if os.path.exists(SOURCE_PDF):
        print(f"[Nguồn] Trích xuất trực tiếp từ text layer PDF gốc: {os.path.basename(SOURCE_PDF)}")
        import fitz
        import re
        doc = fitz.open(SOURCE_PDF)
        full_text = "\n".join(p.get_text() for p in doc)
        doc.close()

        splits = re.split(r'\n\s*Chương\s+([IVXLCDM]+)\s*\n', full_text, flags=re.IGNORECASE)
        for i in range(1, len(splits), 2):
            roman = splits[i].strip()
            content = splits[i + 1].strip()
            lines = content.splitlines()
            ch_title = lines[0].strip()
            ch_body = "\n".join(lines[1:])
            parsed = parse_articles(ch_body, roman, ch_title)
            all_articles.extend(parsed)
            print(f"   - Chương {roman:<4} ({ch_title[:45]}...): {len(parsed)} Điều")
    else:
        print("[Nguồn] Không thấy PDF gốc, tải từ vi.wikisource...")
        for roman, title in CHAPTERS:
            print(f"[Tải] Chương {roman}...", end=" ", flush=True)
            raw = fetch_wikisource(f"{PAGE_PREFIX}/Chương {roman}")
            parsed = parse_articles(raw, roman, title)
            all_articles.extend(parsed)
            print(f"{len(raw):,} ký tự -> {len(parsed)} Điều")

    print("[Kiểm chứng]")
    errors = validate(all_articles)
    if errors:
        print("\n❌ DỮ LIỆU KHÔNG ĐẠT KIỂM CHỨNG:")
        for e in errors:
            print(f"   - {e}")
        return 1

    tree_path = os.path.join(OUT_DIR, "luat_35_2024_structured.json")
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump({
            "doc_id": DOC_ID,
            "doc_name": DOC_NAME,
            "doc_full_name": DOC_FULL_NAME,
            "date_effective": DATE_EFFECTIVE,
            "source": f"Text layer số hóa gốc từ {os.path.basename(SOURCE_PDF)}",
            "articles": all_articles
        }, f, ensure_ascii=False, indent=2)

    chunks = build_article_chunks(all_articles)
    chunks_path = os.path.join(OUT_DIR, "luat_35_articles.jsonl")
    with open(chunks_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    total_clauses = sum(len(a["clauses"]) for a in all_articles)
    print(f"\n✅ {len(all_articles)} Điều / {total_clauses} Khoản")
    print(f"   - Cây văn bản: {tree_path}")
    print(f"   - Toàn văn Điều: {chunks_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
