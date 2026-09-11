"""
Trích xuất và cấu trúc hóa THÔNG TƯ 73/2024/TT-BCA
(Quy định công tác tuần tra, kiểm soát, xử lý vi phạm pháp luật về trật tự ATGT đường bộ của CSGT, hiệu lực 01/01/2025).
Nguồn: Toàn văn OCR Gemini Vision từ raw_data/05_thong_tu_73_2024_tt_bca_tuan_tra_csgt.pdf.

Xuất ra:
1. data/processed/05_thong_tu_73_2024_tt_bca_tuan_tra_csgt_structured.json (Cây phân cấp hoàn chỉnh)
2. data/processed/tt_73_articles.jsonl (Toàn văn từng Điều kèm Breadcrumb và Metadata cho RAG)
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
CACHE_DIR = os.path.join(BASE_DIR, "data", "processed", "ocr_cache", "05_thong_tu_73_2024_tt_bca")
OUT_DIR = os.path.join(BASE_DIR, "data", "processed")

DOC_ID = "05_thong_tu_73_2024_tt_bca"
DOC_NAME = "Thông tư 73/2024/TT-BCA"
DOC_FULL_NAME = "Thông tư quy định công tác tuần tra, kiểm soát, xử lý vi phạm pháp luật về trật tự, an toàn giao thông đường bộ của Cảnh sát giao thông"
ISSUING_AUTHORITY = "Bộ Công an"
DATE_EFFECTIVE = "01/01/2025"

RE_CHAPTER = re.compile(r'^\s*#{0,3}\s*\*{0,2}Chương\s+([IVXLCDM]+)\*{0,2}\s*$', re.IGNORECASE)
RE_SECTION = re.compile(r'^\s*#{0,3}\s*\*{0,2}Mục\s+(\d+)\*{0,2}\s*$', re.IGNORECASE)
RE_ARTICLE = re.compile(r'^\s*\*{0,2}Điều\s+(\d{1,2})\.\s*(.*?)\*{0,2}\s*$')
RE_CLAUSE = re.compile(r'^\s*(\d{1,2})\.\s*(.+)$')
RE_POINT = re.compile(r'^\s*([a-zđ]{1,2})\)\s*(.+)$', re.IGNORECASE)

CHAPTER_TITLES = {
    "I": "QUY ĐỊNH CHUNG",
    "II": "HÌNH THỨC, NỘI DUNG TUẦN TRA, KIỂM SOÁT; TRANG BỊ CỦA CẢNH SÁT GIAO THÔNG KHI TUẦN TRA, KIỂM SOÁT",
    "III": "QUY TRÌNH TUẦN TRA, KIỂM SOÁT, XỬ LÝ VI PHẠM",
    "IV": "HUY ĐỘNG LỰC LƯỢNG KHÁC TRONG CÔNG AN NHÂN DÂN THAM GIA PHỐI HỢP VỚI CẢNH SÁT GIAO THÔNG THỰC HIỆN TUẦN TRA, KIỂM SOÁT TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ TRONG TRƯỜNG HỢP CẦN THIẾT",
    "V": "ĐIỀU KHOẢN THI HÀNH"
}

def get_chapter_by_article(art_num: int) -> str:
    if art_num <= 4:
        return "I"
    elif art_num <= 10:
        return "II"
    elif art_num <= 26:
        return "III"
    elif art_num <= 31:
        return "IV"
    else:
        return "V"


def load_full_text_pages() -> List[str]:
    pages = []
    for i in range(1, 42):
        fn = os.path.join(CACHE_DIR, f"page_{i:03d}.md")
        if not os.path.exists(fn):
            raise FileNotFoundError(f"Chưa hoàn tất trang {fn}")
        with open(fn, "r", encoding="utf-8") as f:
            pages.append(f.read())
    return pages


def parse_tt73() -> Dict[str, Any]:
    pages = load_full_text_pages()

    full_lines = []
    for p_idx, page in enumerate(pages):
        lines = page.splitlines()
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if re.match(r'^\d+$', line) and len(line) <= 3:
                continue
            if line.startswith("<!--") or line.startswith("---"):
                continue
            full_lines.append(line)

    chapters_dict = {
        r: {
            "chapter_roman": r,
            "chapter_title": CHAPTER_TITLES[r],
            "articles": []
        }
        for r in ["I", "II", "III", "IV", "V"]
    }

    current_article: Optional[Dict[str, Any]] = None
    current_clause: Optional[Dict[str, Any]] = None
    current_point: Optional[Dict[str, Any]] = None

    for line in full_lines:
        m_art = RE_ARTICLE.match(line)
        if m_art:
            art_num = int(m_art.group(1))
            art_title = m_art.group(2).strip()
            chap_roman = get_chapter_by_article(art_num)

            current_article = {
                "article_number": art_num,
                "article_title": art_title,
                "chapter_roman": chap_roman,
                "chapter_title": CHAPTER_TITLES[chap_roman],
                "intro": "",
                "clauses": []
            }
            chapters_dict[chap_roman]["articles"].append(current_article)
            current_clause = None
            current_point = None
            continue

        if current_article is None:
            continue

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

        m_point = RE_POINT.match(line)
        if m_point and current_clause is not None and not line.startswith("|"):
            current_point = {
                "point_letter": m_point.group(1).lower(),
                "text": m_point.group(2).strip()
            }
            current_clause["points"].append(current_point)
            continue

        # Nối dòng văn bản
        if current_point is not None:
            current_point["text"] += "\n" + line
        elif current_clause is not None:
            current_clause["text"] += "\n" + line
        else:
            if current_article["intro"]:
                current_article["intro"] += "\n" + line
            else:
                current_article["intro"] = line

    chapters = [c for c in chapters_dict.values() if c["articles"]]
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
            chunk_text = "\n".join([
                f"=== {header} ===",
                f"Văn bản: {DOC_FULL_NAME}",
                f"Chương: Chương {article['chapter_roman']} - {article['chapter_title']}",
                ""
            ] + body_parts)

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
                    "category": "traffic_police_inspection"
                }
            })
    return chunks


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    structured = parse_tt73()
    print(f"✅ Đã trích xuất {structured['total_articles']} Điều thuộc {structured['total_chapters']} Chương của Thông tư 73/2024.")

    out_json = os.path.join(OUT_DIR, f"{DOC_ID}_tuan_tra_csgt_structured.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(structured, f, ensure_ascii=False, indent=2)
    print(f"   - File JSON phân cấp: {out_json}")

    chunks = build_article_chunks(structured)
    out_jsonl = os.path.join(OUT_DIR, "tt_73_articles.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"   - File JSONL RAG chunks: {out_jsonl} ({len(chunks)} chunks)")


if __name__ == "__main__":
    main()
