"""
BỘ PARSER VĂN BẢN PHÁP LUẬT DÙNG CHUNG

Mọi văn bản quy phạm pháp luật Việt Nam đều có cùng phân cấp Chương > Điều > Khoản > Điểm,
nên phần tải và bóc tách được gom về một chỗ cho các script prepare_*.py dùng lại.

Nguồn văn bản: vi.wikisource (bản số hóa có lớp text). Bốn trong sáu PDF gốc của dự án là
bản scan ảnh, OCR chúng sẽ làm sai số liệu pháp lý — nên PDF chỉ dùng làm bản đối soát.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

WIKISOURCE_API = "https://vi.wikisource.org/w/api.php"
USER_AGENT = "TrafficLawRAG/1.0 (Educational Project)"

# Dòng mở đầu một Điều / Khoản / Điểm
RE_ARTICLE = re.compile(r'^Điều\s+(\d+)\.\s*(.+)$')
RE_CLAUSE = re.compile(r'^(\d{1,2})\.\s*(.+)$')
RE_POINT = re.compile(r'^([a-zđ]{1,2})\)\s*(.+)$', re.IGNORECASE)


def normalize(text: str) -> str:
    """Bỏ ký tự ẩn (zero-width) của wikisource và gộp khoảng trắng thừa"""
    return re.sub(r'\s{2,}', ' ', text.replace("​", "").replace("﻿", "")).strip()


def fetch_wikisource(page_title: str, max_retries: int = 5) -> str:
    """Tải một trang wikisource và trả về phần văn bản thuần"""
    url = f"{WIKISOURCE_API}?" + urllib.parse.urlencode(
        {"action": "parse", "page": page_title, "prop": "text", "format": "json"}
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return BeautifulSoup(payload["parse"]["text"]["*"], "html.parser").get_text("\n")
        except Exception as error:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Không tải được '{page_title}': {error}")
            time.sleep(2 * (attempt + 1))
    return ""


def clean_lines(raw_text: str) -> List[str]:
    """Bỏ dòng trống và khoảng trắng thừa, giữ nguyên thứ tự để nhận diện phân cấp"""
    return [line for line in (normalize(l) for l in raw_text.splitlines()) if line]


def parse_articles(raw_text: str, chapter_roman: str, chapter_title: str) -> List[Dict[str, Any]]:
    """
    Tách văn bản một Chương thành danh sách Điều, mỗi Điều gồm các Khoản, mỗi Khoản gồm các Điểm.

    Bản wikisource đã xuống dòng đúng theo từng Khoản/Điểm nên chỉ cần bám tiền tố dòng;
    dòng nối tiếp được ghép vào phần tử đang mở để không mất chữ của câu dài.
    """
    articles: List[Dict[str, Any]] = []
    article: Optional[Dict[str, Any]] = None
    clause: Optional[Dict[str, Any]] = None
    point: Optional[Dict[str, Any]] = None

    for line in clean_lines(raw_text):
        m_article = RE_ARTICLE.match(line)
        if m_article:
            article = {
                "article_number": int(m_article.group(1)),
                "article_title": m_article.group(2).strip(),
                "chapter_roman": chapter_roman,
                "chapter_title": chapter_title,
                "intro": "",
                "clauses": []
            }
            articles.append(article)
            clause = point = None
            continue

        if article is None:
            continue

        m_point = RE_POINT.match(line)
        if m_point and clause is not None:
            point = {"point_letter": m_point.group(1).lower(), "text": m_point.group(2).strip()}
            clause["points"].append(point)
            continue

        m_clause = RE_CLAUSE.match(line)
        if m_clause:
            clause = {"clause_number": int(m_clause.group(1)), "text": m_clause.group(2).strip(), "points": []}
            article["clauses"].append(clause)
            point = None
            continue

        # Dòng nối tiếp của phần tử đang mở; chưa có khoản nào thì đây là phần mở đầu của Điều
        # (nhiều Điều như "Phạm vi điều chỉnh" chỉ có một đoạn văn, không đánh số khoản).
        if point is not None:
            point["text"] += " " + line
        elif clause is not None:
            clause["text"] += " " + line
        else:
            article["intro"] = (article["intro"] + " " + line).strip()

    return articles


def pdf_article_titles(pdf_path: str) -> Dict[int, str]:
    """
    Đọc số hiệu + tiêu đề các Điều từ PDF gốc để đối soát với bản số hóa.

    Chỉ dùng cho PDF có lớp text. Trả về dict rỗng nếu là bản scan hoặc thiếu thư viện đọc PDF,
    khi đó bước đối soát sẽ được bỏ qua thay vì làm hỏng pipeline.
    """
    try:
        import fitz
    except ImportError:
        return {}
    try:
        with fitz.open(pdf_path) as document:
            text = "\n".join(page.get_text("text") for page in document)
    except Exception:
        return {}
    matches = re.findall(RE_ARTICLE.pattern, text, re.MULTILINE)
    return {int(num): normalize(title) for num, title in matches}
