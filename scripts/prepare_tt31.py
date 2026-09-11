"""
Trích xuất và cấu trúc hóa THÔNG TƯ 31/2019/TT-BGTVT
(Quy định về tốc độ và khoảng cách an toàn của xe cơ giới, xe máy chuyên dùng).
Nguồn: Kết quả OCR Gemini Vision từ raw_data/04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach.pdf.

Xuất ra:
1. data/processed/04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach_structured.json (Cấu trúc phân cấp Tree)
2. data/processed/tt_31_articles.jsonl (Toàn văn từng Điều và bảng tra cứu cự ly/tốc độ cho RAG)
"""

import os
import re
import sys
import json
from typing import Any, Dict, List, Optional

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_MD = os.path.join(BASE_DIR, "data", "processed", "ocr_cache", "04_thong_tu_31_2019_tt_bgtvt_full.md")
OUT_DIR = os.path.join(BASE_DIR, "data", "processed")

DOC_ID = "04_thong_tu_31_2019_tt_bgtvt"
DOC_NAME = "Thông tư 31/2019/TT-BGTVT"
DOC_FULL_NAME = "Thông tư quy định về tốc độ và khoảng cách an toàn của xe cơ giới, xe máy chuyên dùng tham gia giao thông đường bộ"
ISSUING_AUTHORITY = "Bộ Giao thông vận tải"
DATE_EFFECTIVE = "15/10/2019"

RE_CHAPTER = re.compile(r'^\s*#{1,3}\s*Chương\s+([IVXLCDM]+)\s*$', re.IGNORECASE)
RE_CHAPTER_TITLE = re.compile(r'^\s*#{1,3}\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐ\s,–-]+)\s*$')
RE_ARTICLE = re.compile(r'^\s*\*{0,2}Điều\s+(\d{1,2})\.\s*(.*?)\*{0,2}\s*$')
RE_CLAUSE = re.compile(r'^\s*(\d{1,2})\.\s*(.+)$')
RE_POINT = re.compile(r'^\s*([a-zđ]{1,2})\)\s*(.+)$', re.IGNORECASE)

CHAPTER_MAP = {
    "I": "QUY ĐỊNH CHUNG",
    "II": "QUY ĐỊNH TỐC ĐỘ, KHOẢNG CÁCH CỦA XE CƠ GIỚI, XE MÁY CHUYÊN DÙNG THAM GIA GIAO THÔNG TRÊN ĐƯỜNG BỘ",
    "III": "TỔ CHỨC THỰC HIỆN",
}


def parse_tt31_markdown(md_path: str) -> Dict[str, Any]:
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    chapters: List[Dict[str, Any]] = []
    current_chapter: Optional[Dict[str, Any]] = None
    current_article: Optional[Dict[str, Any]] = None
    current_clause: Optional[Dict[str, Any]] = None
    current_point: Optional[Dict[str, Any]] = None

    # Mặc định khởi tạo Chương I nếu gặp Điều 1 trước khi bắt gặp header Chương
    current_chapter = {
        "chapter_roman": "I",
        "chapter_title": CHAPTER_MAP["I"],
        "articles": []
    }
    chapters.append(current_chapter)

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("<!--") or line.startswith("---") or line.startswith("Ký bởi:") or line.startswith("Email:") or line.startswith("Cơ quan:") or line.startswith("Thời gian ký:"):
            continue
        if re.match(r'^\d+$', line): # Bỏ qua số trang lẻ
            continue

        # Nhận diện Chương
        m_chap = RE_CHAPTER.match(line)
        if m_chap:
            roman = m_chap.group(1).upper()
            title = CHAPTER_MAP.get(roman, "")
            current_chapter = {
                "chapter_roman": roman,
                "chapter_title": title,
                "articles": []
            }
            chapters.append(current_chapter)
            current_article = None
            current_clause = None
            current_point = None
            continue

        # Nhận diện Điều
        m_art = RE_ARTICLE.match(line)
        if m_art:
            art_num = int(m_art.group(1))
            art_title = m_art.group(2).strip()

            # Gán vào chương tương ứng dựa trên số điều
            if art_num <= 5:
                chap_roman = "I"
            elif art_num <= 11:
                chap_roman = "II"
            else:
                chap_roman = "III"

            # Đảm bảo gán đúng chương
            target_chap = None
            for c in chapters:
                if c["chapter_roman"] == chap_roman:
                    target_chap = c
                    break
            if not target_chap:
                target_chap = {
                    "chapter_roman": chap_roman,
                    "chapter_title": CHAPTER_MAP.get(chap_roman, ""),
                    "articles": []
                }
                chapters.append(target_chap)

            current_chapter = target_chap
            current_article = {
                "article_number": art_num,
                "article_title": art_title,
                "chapter_roman": current_chapter["chapter_roman"],
                "chapter_title": current_chapter["chapter_title"],
                "intro": "",
                "clauses": []
            }
            current_chapter["articles"].append(current_article)
            current_clause = None
            current_point = None
            continue

        if current_article is None:
            continue

        # Nhận diện Khoản
        m_clause = RE_CLAUSE.match(line)
        if m_clause and not line.startswith("|"):
            current_clause = {
                "clause_number": int(m_clause.group(1)),
                "text": m_clause.group(2).strip(),
                "points": []
            }
            current_article["clauses"].append(current_clause)
            current_point = None
            continue

        # Nhận diện Điểm
        m_point = RE_POINT.match(line)
        if m_point and current_clause is not None and not line.startswith("|"):
            current_point = {
                "point_letter": m_point.group(1).lower(),
                "text": m_point.group(2).strip()
            }
            current_clause["points"].append(current_point)
            continue

        # Nội dung bảng biểu hoặc văn bản nối tiếp
        if current_point is not None:
            current_point["text"] += "\n" + line
        elif current_clause is not None:
            current_clause["text"] += "\n" + line
        else:
            if current_article["intro"]:
                current_article["intro"] += "\n" + line
            else:
                current_article["intro"] = line

    # Lọc các chương rỗng nếu có
    chapters = [c for c in chapters if c["articles"]]

    total_articles = sum(len(c["articles"]) for c in chapters)
    return {
        "doc_id": DOC_ID,
        "doc_name": DOC_NAME,
        "doc_full_name": DOC_FULL_NAME,
        "issuing_authority": ISSUING_AUTHORITY,
        "date_effective": DATE_EFFECTIVE,
        "total_chapters": len(chapters),
        "total_articles": total_articles,
        "chapters": chapters
    }


def build_article_chunks(doc_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    chunks = []
    for chapter in doc_data["chapters"]:
        for article in chapter["articles"]:
            body_parts = []
            if article.get("intro"):
                body_parts.append(article["intro"])

            for clause in article["clauses"]:
                body_parts.append(f"{clause['clause_number']}. {clause['text']}")
                for p in clause["points"]:
                    body_parts.append(f"   {p['point_letter']}) {p['text']}")

            header = f"Điều {article['article_number']}. {article['article_title']}"
            chunk_text = "\n".join([f"=== {header} ===", f"Văn bản: {DOC_FULL_NAME}", f"Chương: Chương {article['chapter_roman']} - {article['chapter_title']}", ""] + body_parts)

            chunks.append({
                "id": f"{DOC_ID}_dieu_{article['article_number']:02d}",
                "doc_id": DOC_ID,
                "doc_name": DOC_NAME,
                "page_content": chunk_text,
                "metadata": {
                    "article_number": article["article_number"],
                    "article_title": article["article_title"],
                    "article_header": header,
                    "chapter_id": article["chapter_roman"],
                    "chapter_title": article["chapter_title"],
                    "clause_count": len(article["clauses"]),
                    "doc_type": "thong_tu",
                    "category": "speed_and_distance"
                }
            })
    return chunks


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    structured = parse_tt31_markdown(CACHE_MD)
    print(f"✅ Đã trích xuất {structured['total_articles']} Điều thuộc {structured['total_chapters']} Chương của Thông tư 31/2019.")

    out_json = os.path.join(OUT_DIR, f"{DOC_ID}_toc_do_khoang_cach_structured.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(structured, f, ensure_ascii=False, indent=2)
    print(f"   - File JSON phân cấp: {out_json}")

    chunks = build_article_chunks(structured)
    out_jsonl = os.path.join(OUT_DIR, "tt_31_articles.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"   - File JSONL RAG chunks: {out_jsonl} ({len(chunks)} chunks)")


if __name__ == "__main__":
    main()
