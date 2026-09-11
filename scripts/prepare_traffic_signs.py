"""
TRÍCH XUẤT QCVN 41:2019/BGTVT — QUY CHUẨN KỸ THUẬT QUỐC GIA VỀ BÁO HIỆU ĐƯỜNG BỘ

Đây là văn bản duy nhất trong kho tài liệu gốc vừa CÓ lớp text số hóa (319.761 ký tự trên
211 trang) vừa chưa từng được nạp vào chỉ mục — nhờ đó bổ sung được nhóm câu hỏi mà hệ
thống trước đây không có dữ liệu nào để trả lời: ý nghĩa biển báo (P/W/R/I/S/DP), ý nghĩa
vạch kẻ đường, thứ tự hiệu lực của hệ thống báo hiệu.

Khác với ba văn bản kia (lấy bản số hóa từ vi.wikisource), QCVN 41 không có trên wikisource
nên nguồn chính là chính lớp text của PDF gốc — không OCR, không suy đoán.

Xuất ra:
1. data/processed/qcvn_41_2019_structured.json  — cây Chương / Điều / Khoản
2. data/processed/qcvn_41_articles.jsonl        — mỗi Điều một bản ghi toàn văn (parent chunk)
3. data/processed/traffic_signs.jsonl           — catalogue biển báo (Phụ lục B, C, D, E, F)
4. data/processed/road_markings.jsonl           — catalogue vạch kẻ đường (Phụ lục G)

Catalogue biển báo tách riêng khỏi thân Quy chuẩn vì câu hỏi thực tế luôn hỏi theo mã hiệu
("biển P.106a cấm xe gì") — một bản ghi trên mỗi mã hiệu cho phép tra trực tiếp bằng mã,
không phụ thuộc vào việc vector có khớp hay không.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "processed")
SOURCE_PDF = os.path.join(BASE_DIR, "data", "raw_data",
                          "06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo.pdf")

DOC_ID = "qcvn_41_2019"
DOC_NAME = "QCVN 41:2019/BGTVT"
DOC_FULL_NAME = ("Quy chuẩn kỹ thuật quốc gia về báo hiệu đường bộ QCVN 41:2019/BGTVT "
                 "(ban hành kèm Thông tư 54/2019/TT-BGTVT)")
DATE_EFFECTIVE = "01/07/2020"

# Số Điều của thân Quy chuẩn. Đối soát sau khi parse: thiếu Điều nào là dấu hiệu lớp text
# của PDF bị đứt đoạn, khi đó chỉ mục sẽ khuyết kiến thức mà không ai biết.
EXPECTED_ARTICLES = 90

# Dòng mở đầu một Điều / Chương / mục Phụ lục
RE_ARTICLE = re.compile(r'^Điều\s+(\d{1,3})\.\s*(.*)$')
RE_CHAPTER = re.compile(r'^CHƯƠNG\s+(\d{1,2})\s*$', re.IGNORECASE)
RE_CLAUSE = re.compile(r'^(\d{1,3}\.\d{1,2})\.?\s+(.+)$')
RE_APPENDIX = re.compile(r'^Phụ lục\s+([A-Z])\s*$')

# Mã hiệu biển báo theo QCVN 41: nhóm chữ + dấu chấm + 3 chữ số + hậu tố chữ thường tùy chọn
RE_SIGN_CODE = re.compile(r'\b((?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}[a-z]?)\b')

# Mục catalogue trong Phụ lục B/C/D/E/F, ví dụ: "B.12" đứng riêng một dòng rồi tới tên biển
RE_APPENDIX_ITEM = re.compile(r'^([B-G])(\d?)\.(\d{1,2})(?:\.(\d{1,2}))?\s*$')

# Mục vạch kẻ đường trong Phụ lục G. Quy chuẩn dùng lẫn ba kiểu đánh mục — tiền tố chữ cái
# ("a. Vạch 1.1: ..."), gạch đầu dòng ("- Vạch 9.5a: ...") và không tiền tố ("Vạch 7.1: ...")
# — nên phải nhận cả ba, nếu không sẽ khuyết đúng những vạch hay bị hỏi (vạch chữ STOP, làn
# dành riêng cho xe buýt).
RE_MARKING = re.compile(
    r'^(?:[a-zđ]{1,2}[.)]\s*|[-–]\s*)?Vạch\s+(\d{1,2}\.\d{1,2}[a-z]?)\s*:\s*(.+)$')

# Dòng liệt kê mã hiệu + tên gọi chính thức trong thân Quy chuẩn (Điều 26, 32, 36, 40, 44...).
# Đây là nguồn phủ đầy đủ nhất: Phụ lục chỉ giải thích chi tiết một phần số biển, còn danh mục
# trong thân Quy chuẩn gọi tên toàn bộ.
RE_SIGN_ENUM = re.compile(
    r'[Bb]iển số\s+((?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}(?:\s*\(\s*[a-zđ,\s]+\))?[a-z]?)'
    r'\s*[:\-–]\s*([^;.]{3,120}?)\s*[;.]'
)

# Ký hiệu gộp nhiều biển cùng họ, ví dụ "P.124(a,b,c,d)" gom 4 mã hiệu vào một dòng liệt kê
RE_GROUPED_CODE = re.compile(r'^([A-Z]{1,2}\.\d{3})\s*\(\s*([a-zđ,\s]+)\)$')

# Nhóm biển báo theo ký tự đầu của mã hiệu (Điều 15 QCVN 41)
SIGN_GROUPS = {
    "P": "Biển báo cấm",
    "DP": "Biển báo hết cấm",
    "W": "Biển báo nguy hiểm và cảnh báo",
    "R": "Biển hiệu lệnh",
    "I": "Biển chỉ dẫn",
    "IE": "Biển chỉ dẫn trên đường cao tốc",
    "S": "Biển phụ",
    "SG": "Biển phụ (giá long môn)",
    "SH": "Biển phụ (hướng)",
    "SR": "Biển phụ (đường sắt)",
    "IS": "Biển chỉ dẫn (nhóm phụ)",
}

APPENDIX_TITLES = {
    "A": "Đèn tín hiệu",
    "B": "Ý nghĩa - Sử dụng biển báo cấm",
    "C": "Ý nghĩa - Sử dụng biển báo nguy hiểm và cảnh báo",
    "D": "Ý nghĩa - Sử dụng biển hiệu lệnh",
    "E": "Ý nghĩa - Sử dụng biển chỉ dẫn",
    "F": "Ý nghĩa - Sử dụng các biển phụ",
    "G": "Ý nghĩa - Sử dụng vạch kẻ đường",
}

# Dòng mở đầu phần giải thích của một mục Phụ lục: điểm a), b)..., gạch đầu dòng, hoặc các
# tiểu mục cố định của Phụ lục G.
RE_BODY_START = re.compile(r'^(?:[a-zđ]{1,2}\)|[-–•]|Ý nghĩa|Quy cách|Minh họa|Để )')

# Phụ lục chứa catalogue biển báo (mỗi mục là một mã hiệu kèm ý nghĩa sử dụng)
SIGN_APPENDICES = ("B", "C", "D", "E", "F")


# ---------------------------------------------------------------------------
# Làm sạch lớp text của PDF
# ---------------------------------------------------------------------------

def _is_noise(line: str) -> bool:
    """
    Loại các dòng không mang nội dung quy phạm: số trang, nhãn hình vẽ và chuỗi rác do
    bảng vẽ kỹ thuật dùng phông VNI cũ (ví dụ '§¬n vÞ: cm') không giải mã được sang Unicode.
    """
    if not line or line.isdigit():
        return True
    if re.match(r'^(Hình|Bảng)\s+[A-Z0-9]', line):
        return True
    # Chuỗi rác phông VNI: gần như không có nguyên âm tiếng Việt hợp lệ mà đầy ký tự lạ
    if re.search(r'[§¬­¾¸®Æ×Ëª©÷Ìͧ]', line):
        return True
    # Dòng chỉ gồm số đo, ký hiệu kích thước trên bản vẽ
    if re.fullmatch(r'[\d\s,.;:%×xX=\-/()]+', line):
        return True
    return False


# Quy chuẩn trộn lẫn ngoặc kép thẳng và ngoặc kép cong ngay trong cùng một tên biển
# ('P.106 (a,b) "Cấm xe ôtô tải" ... "Cấm các xe chở hàng nguy hiểm”'). Không chuẩn hóa thì
# phép đếm ngoặc để nối tiêu đề bị lệch và nuốt luôn phần giải thích vào tiêu đề.
QUOTE_MAP = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"',
                           "‘": "'", "’": "'"})


def _clean_lines(raw_text: str) -> List[str]:
    """Chuẩn hóa khoảng trắng, dấu ngoặc kép, bỏ dòng nhiễu, giữ nguyên thứ tự phân cấp"""
    lines = []
    for raw in raw_text.splitlines():
        text = raw.replace("​", "").replace("﻿", "").translate(QUOTE_MAP)
        line = re.sub(r'\s{2,}', ' ', text).strip()
        if not _is_noise(line):
            lines.append(line)
    return lines


def extract_pdf_lines(pdf_path: str) -> List[str]:
    """Đọc lớp text của PDF gốc. Bắt buộc phải có PyMuPDF — không có thì dừng hẳn."""
    try:
        import fitz
    except ImportError:
        raise RuntimeError("Thiếu PyMuPDF. Cài đặt: pip install PyMuPDF")

    with fitz.open(pdf_path) as document:
        pages = [page.get_text("text") for page in document]

    total = sum(len(p.strip()) for p in pages)
    if total < 50_000:
        raise RuntimeError(
            f"PDF chỉ có {total} ký tự text — đây là bản scan, không phải bản số hóa. "
            "Không được OCR để lấy nội dung quy phạm."
        )
    return _clean_lines("\n".join(pages))


# ---------------------------------------------------------------------------
# Bóc tách thân Quy chuẩn (Chương / Điều / Khoản)
# ---------------------------------------------------------------------------

def _appendix_start(lines: List[str]) -> int:
    """
    Vị trí bắt đầu phần Phụ lục — mốc 'Phụ lục A' đứng một mình sau thân Quy chuẩn.

    Mục lục ở đầu tài liệu cũng có dòng 'Phụ lục A - Đèn tín hiệu ....' nhưng luôn kèm dấu
    gạch và dòng chấm dẫn trang, nên regex đòi hỏi dòng đứng riêng sẽ không nhầm.
    """
    for index in range(len(lines) - 1, 0, -1):
        if RE_APPENDIX.match(lines[index]) and lines[index].endswith("A"):
            return index
    return len(lines)


def parse_body(lines: List[str]) -> List[Dict[str, Any]]:
    """Tách thân Quy chuẩn thành danh sách Điều, mỗi Điều gồm các Khoản đánh số 'N.M'"""
    articles: List[Dict[str, Any]] = []
    article: Optional[Dict[str, Any]] = None
    clause: Optional[Dict[str, Any]] = None
    chapter_number, chapter_title = 0, "NHỮNG QUY ĐỊNH CHUNG"
    seen: set = set()

    index = 0
    while index < len(lines):
        line = lines[index]

        m_chapter = RE_CHAPTER.match(line)
        if m_chapter:
            chapter_number = int(m_chapter.group(1))
            # Tiêu đề Chương nằm ở dòng kế tiếp; đôi khi PDF chèn một dòng trống đã bị lọc
            following = lines[index + 1] if index + 1 < len(lines) else ""
            chapter_title = following if following.isupper() else chapter_title
            index += 2 if following.isupper() else 1
            continue

        m_article = RE_ARTICLE.match(line)
        if m_article:
            number = int(m_article.group(1))
            title = m_article.group(2).strip()
            # Quy chuẩn tham chiếu chéo rất nhiều ("quy định ở Điều 82, ...") — chỉ mở Điều mới
            # khi số hiệu tăng đúng thứ tự, nếu không mọi tham chiếu sẽ cắt vụn nội dung.
            if number in seen or (articles and number != articles[-1]["article_number"] + 1):
                if article is not None:
                    _append_text(article, clause, line)
                index += 1
                continue

            article = {
                "article_number": number,
                "article_title": title,
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "intro": "",
                "clauses": []
            }
            articles.append(article)
            seen.add(number)
            clause = None
            index += 1
            continue

        if article is None:
            index += 1
            continue

        m_clause = RE_CLAUSE.match(line)
        # Khoản của QCVN đánh số theo Điều: Điều 30 có khoản 30.1, 30.2...
        if m_clause and m_clause.group(1).startswith(f"{article['article_number']}."):
            clause = {"clause_number": m_clause.group(1), "text": m_clause.group(2).strip()}
            article["clauses"].append(clause)
            index += 1
            continue

        _append_text(article, clause, line)
        index += 1

    return articles


def _append_text(article: Dict[str, Any], clause: Optional[Dict[str, Any]], line: str) -> None:
    """Ghép dòng nối tiếp vào Khoản đang mở, hoặc vào phần mở đầu của Điều nếu chưa có Khoản"""
    if clause is not None:
        clause["text"] += " " + line
    else:
        article["intro"] = (article["intro"] + " " + line).strip()


def article_full_text(article: Dict[str, Any]) -> str:
    """Dựng toàn văn một Điều để dùng làm parent chunk khi truy xuất phân cấp"""
    parts = [f"Điều {article['article_number']}. {article['article_title']}"]
    if article["intro"]:
        parts.append(article["intro"])
    for clause in article["clauses"]:
        parts.append(f"{clause['clause_number']}. {clause['text']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Bóc tách catalogue biển báo (Phụ lục B, C, D, E, F)
# ---------------------------------------------------------------------------

def _split_appendices(lines: List[str], start: int) -> Dict[str, List[str]]:
    """Cắt phần Phụ lục thành từng khối theo chữ cái Phụ lục"""
    blocks: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in lines[start:]:
        m = RE_APPENDIX.match(line)
        if m:
            current = m.group(1)
            blocks.setdefault(current, [])
            continue
        if current:
            blocks[current].append(line)
    return blocks


def _sign_group(code: str) -> str:
    prefix = code.split(".")[0]
    return SIGN_GROUPS.get(prefix, "Biển báo hiệu đường bộ")


def _expand_grouped_code(code: str) -> List[str]:
    """'P.124(a,b,c)' -> ['P.124a', 'P.124b', 'P.124c']; mã đơn trả về nguyên vẹn"""
    grouped = RE_GROUPED_CODE.match(code.strip())
    if not grouped:
        return [code.replace(" ", "")]
    base, suffixes = grouped.group(1), grouped.group(2)
    return [f"{base}{s.strip()}" for s in suffixes.split(",") if s.strip()]


def parse_sign_names(body_lines: List[str]) -> Dict[str, str]:
    """
    Tên gọi chính thức của từng mã hiệu, lấy từ các danh mục liệt kê trong thân Quy chuẩn.

    Ghép các dòng lại trước khi dò: lớp text của PDF ngắt dòng giữa chừng, tên biển dài bị
    cắt làm đôi thì regex bám theo từng dòng sẽ bỏ sót hoặc lấy thiếu chữ.
    """
    flat = " ".join(body_lines)
    names: Dict[str, str] = {}
    for raw_code, raw_name in RE_SIGN_ENUM.findall(flat):
        name = re.sub(r'\s{2,}', ' ', raw_name).strip(' "“”')
        for code in _expand_grouped_code(raw_code):
            # Danh mục đầu chương gọi tên ngắn gọn, phần sau nhắc lại kèm mô tả dài dòng hơn;
            # giữ tên đầu tiên gặp để catalogue thống nhất với bảng tra của Quy chuẩn.
            names.setdefault(code, name)
    return names


def _codes_in_heading(heading: str) -> List[str]:
    """
    Mã hiệu xuất hiện trong tiêu đề một mục Phụ lục, đã mở ký hiệu gộp.

    Tiêu đề hay viết gộp 'Biển số P.106 (a,b)' — nếu chỉ bắt 'P.106' thì phần giải thích
    không gắn được vào P.106a và P.106b, đúng hai mã mà người dùng hỏi.
    """
    codes: List[str] = []
    for match in re.finditer(
            r'((?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}[a-z]?)\s*(\(\s*[a-zđ,\s]+\))?', heading):
        base, suffixes = match.group(1), match.group(2)
        if suffixes and not base[-1].isalpha():
            codes.extend(f"{base}{s.strip()}"
                         for s in suffixes.strip("()").split(",") if s.strip())
        else:
            codes.append(base)
    return list(dict.fromkeys(codes))


def parse_sign_meanings(blocks: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    """
    Ý nghĩa - cách sử dụng chi tiết của từng mã hiệu, lấy từ Phụ lục B/C/D/E/F.

    Mỗi mục Phụ lục ("B.3") có thể mô tả vài mã cùng họ (P.103a, P.103b, P.103c) — tách ra
    thành từng mã vì người hỏi luôn hỏi đúng một mã hiệu.
    """
    meanings: Dict[str, Dict[str, Any]] = {}

    for letter in SIGN_APPENDICES:
        item_id: Optional[str] = None
        title = ""
        body: List[str] = []

        def flush() -> None:
            if not item_id or not title:
                return
            codes = _codes_in_heading(title)
            if not codes:
                return
            detail = " ".join(body).strip()
            local_names = _sign_names(title, codes)
            for code in codes:
                meanings.setdefault(code, {
                    "appendix": letter,
                    "appendix_title": APPENDIX_TITLES.get(letter, ""),
                    "item_id": item_id,
                    "heading": title,
                    "meaning": detail,
                    "local_name": local_names.get(code, ""),
                    "related_codes": [c for c in codes if c != code],
                })

        for line in blocks.get(letter, []):
            if RE_APPENDIX_ITEM.match(line):
                flush()
                item_id, title, body = line, "", []
                continue
            if item_id and not title:
                title = line
                continue
            if item_id:
                # Tiêu đề dài bị ngắt dòng giữa cặp ngoặc kép thì phải ghép tiếp mới đủ tên
                # biển — nhưng dừng ngay khi gặp dòng mở đầu phần giải thích, nếu không cả
                # phần "Ý nghĩa sử dụng" sẽ bị nuốt vào tiêu đề và biển mất mô tả.
                if title.count('"') % 2 == 1 and not RE_BODY_START.match(line):
                    title += " " + line
                else:
                    body.append(line)

        flush()

    return meanings


def build_sign_catalogue(body_lines: List[str],
                         blocks: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """
    Gộp hai nguồn thành một catalogue: danh mục trong thân Quy chuẩn cho tên gọi của mọi mã
    hiệu, Phụ lục cho phần giải thích chi tiết. Chỉ một trong hai thì catalogue sẽ khuyết —
    Phụ lục không gọi tên hết số biển, còn danh mục thì không giải thích cách sử dụng.
    """
    names = parse_sign_names(body_lines)
    meanings = parse_sign_meanings(blocks)

    # Đọc catalog ảnh minh họa đã trích xuất từ Phase 3
    catalog_path = os.path.join(OUT_DIR, "illustrations_catalog.json")
    image_map: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as f:
            cat_list = json.load(f)
            for c in cat_list:
                scode = c.get("sign_code")
                if scode:
                    # Chuẩn hóa key tra cứu: P.101, P101, P_101
                    image_map[scode.lower()] = c
                    image_map[scode.replace(".", "").lower()] = c
                    image_map[scode.replace(".", "_").lower()] = c

    signs: List[Dict[str, Any]] = []
    for code in sorted(set(names) | set(meanings), key=_sign_sort_key):
        detail = meanings.get(code, {})
        name = names.get(code) or detail.get("local_name", "")
        appendix = detail.get("appendix", "")

        # Ánh xạ ảnh
        norm_code = code.lower()
        img_info = image_map.get(norm_code) or image_map.get(norm_code.replace(".", "")) or image_map.get(norm_code.replace(".", "_"))
        # Thử tìm ảnh của mã cha (ví dụ P.103a nếu chưa có thì tìm P.103)
        if not img_info and len(code) > 2 and code[-1].isalpha():
            parent_code = code[:-1]
            img_info = image_map.get(parent_code.lower())

        img_path = img_info["image_path"] if img_info else None
        img_bbox = img_info["bbox"] if img_info else None
        fig_caption = img_info.get("figure_caption") if img_info else None

        signs.append({
            "doc_id": DOC_ID,
            "doc_name": DOC_NAME,
            "sign_code": code,
            "sign_group": _sign_group(code),
            "sign_name": name,
            "appendix": appendix,
            "appendix_title": detail.get("appendix_title", ""),
            "item_id": detail.get("item_id", ""),
            "heading": detail.get("heading", ""),
            "meaning": detail.get("meaning", ""),
            "has_illustration": bool(img_path),
            "image_path": img_path,
            "image_bbox": img_bbox,
            "figure_caption": fig_caption,
            "related_codes": detail.get("related_codes", []),
            "citation": (f"Phụ lục {appendix}, mục {detail['item_id']}, {DOC_NAME}"
                         if appendix else f"Danh mục biển báo, {DOC_NAME}")
        })
    return signs


def _sign_sort_key(code: str) -> Tuple[str, int, str]:
    """Sắp theo nhóm rồi tới số hiệu để catalogue đọc được như bảng tra của Quy chuẩn"""
    prefix, _, rest = code.partition(".")
    digits = re.match(r'(\d+)([a-z]*)', rest)
    return prefix, int(digits.group(1)) if digits else 0, digits.group(2) if digits else ""


def _sign_names(title: str, codes: List[str]) -> Dict[str, str]:
    """
    Ghép mã hiệu với tên gọi trong ngoặc kép ngay sau nó.

    Ví dụ: 'Biển số P.103a "Cấm xe ôtô", Biển số P.103b và P.103c "Cấm xe ôtô rẽ phải"...'
    Mã không có tên riêng liền sau sẽ dùng tên của cụm gần nhất phía trước.
    """
    names: Dict[str, str] = {}
    last_name = ""
    for match in re.finditer(r'((?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}[a-z]?)\s*(?:và\s*'
                             r'(?:biển số\s*)?(?:(?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}[a-z]?)\s*)?'
                             r'(?:"([^"]+)"|“([^”]+)”)?', title, re.IGNORECASE):
        code = match.group(1)
        name = (match.group(2) or match.group(3) or "").strip()
        if name:
            last_name = name
        names[code] = name or last_name

    # Mã chưa có tên (đứng trước cụm tên chung) lấy tên đầu tiên tìm được
    fallback = next((n for n in names.values() if n), "")
    return {code: names.get(code) or fallback for code in codes}


def parse_road_markings(block: List[str]) -> List[Dict[str, Any]]:
    """Catalogue vạch kẻ đường trong Phụ lục G: mỗi 'Vạch N.M' một bản ghi kèm ý nghĩa sử dụng và ảnh minh họa"""
    catalog_path = os.path.join(OUT_DIR, "illustrations_catalog.json")
    mark_img_map: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as f:
            for c in json.load(f):
                if c.get("category") == "vach_ke_duong":
                    scode = c.get("sign_code") or ""
                    # Lưu các biến thể mã: '1.1', 'vạch 1.1', 'vach_1_1'
                    clean = scode.replace("Vạch", "").replace("vạch", "").strip()
                    if clean:
                        mark_img_map[clean] = c
                        mark_img_map[clean.replace(".", "_")] = c

    markings: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    group_title = ""

    for line in block:
        # Tiêu đề nhóm: "G1.1. Nhóm vạch phân chia hai chiều xe chạy ngược chiều"
        m_group = re.match(r'^G\d(?:\.\d{1,2})?\.?\s+(.+)$', line)
        if m_group and "Vạch" not in line[:6]:
            group_title = m_group.group(1).strip()
            continue

        m_marking = RE_MARKING.match(line)
        if m_marking:
            if current:
                markings.append(current)

            mcode = m_marking.group(1)
            img_info = mark_img_map.get(mcode) or mark_img_map.get(mcode.replace(".", "_"))
            img_path = img_info["image_path"] if img_info else None
            img_bbox = img_info["bbox"] if img_info else None
            fig_caption = img_info.get("figure_caption") if img_info else None

            current = {
                "doc_id": DOC_ID,
                "doc_name": DOC_NAME,
                "marking_code": mcode,
                "marking_name": m_marking.group(2).strip(),
                "group_title": group_title,
                "meaning": "",
                "has_illustration": bool(img_path),
                "image_path": img_path,
                "image_bbox": img_bbox,
                "figure_caption": fig_caption,
                "citation": f"Phụ lục G, Vạch {mcode}, {DOC_NAME}"
            }
            continue

        if current:
            current["meaning"] = (current["meaning"] + " " + line).strip()

    if current:
        markings.append(current)
    return markings


# ---------------------------------------------------------------------------
# Ghi kết quả
# ---------------------------------------------------------------------------

def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    print("=" * 78)
    print(f"  TRÍCH XUẤT {DOC_NAME} — BÁO HIỆU ĐƯỜNG BỘ")
    print("=" * 78)

    if not os.path.exists(SOURCE_PDF):
        print(f"❌ Không tìm thấy PDF gốc: {SOURCE_PDF}")
        return 1

    lines = extract_pdf_lines(SOURCE_PDF)
    print(f"[Nguồn] {os.path.basename(SOURCE_PDF)} — {len(lines)} dòng text đã làm sạch")

    boundary = _appendix_start(lines)
    articles = parse_body(lines[:boundary])
    blocks = _split_appendices(lines, boundary)
    signs = build_sign_catalogue(lines[:boundary], blocks)
    markings = parse_road_markings(blocks.get("G", []))

    # Đối soát trước khi ghi: thiếu Điều hoặc thiếu catalogue nghĩa là lớp text bị đứt đoạn,
    # chỉ mục sẽ khuyết kiến thức mà không có dấu hiệu nào lộ ra lúc tra cứu.
    numbers = [a["article_number"] for a in articles]
    missing = [n for n in range(1, EXPECTED_ARTICLES + 1) if n not in numbers]
    errors = []
    if missing:
        errors.append(f"Thiếu {len(missing)} Điều: {missing[:15]}")
    if len(signs) < 300:
        errors.append(f"Chỉ bóc được {len(signs)} mã biển (kỳ vọng >= 300)")
    # Phụ lục G có 42 mục vạch được đặt tên (đếm trực tiếp trên văn bản); hụt so với mốc này
    # nghĩa là một nhóm vạch đã rơi mất khỏi catalogue.
    if len(markings) < 42:
        errors.append(f"Chỉ bóc được {len(markings)} vạch kẻ đường (kỳ vọng >= 42)")
    if errors:
        print("\n❌ KẾT QUẢ BÓC TÁCH KHÔNG ĐẠT ĐỐI SOÁT:")
        for e in errors:
            print(f"   - {e}")
        return 1

    chapters: Dict[int, Dict[str, Any]] = {}
    for article in articles:
        chapter = chapters.setdefault(article["chapter_number"], {
            "chapter_number": article["chapter_number"],
            "chapter_title": article["chapter_title"],
            "articles": []
        })
        chapter["articles"].append(article)

    tree = {
        "doc_id": DOC_ID,
        "doc_name": DOC_NAME,
        "doc_full_name": DOC_FULL_NAME,
        "doc_type": "quy_chuan",
        "date_effective": DATE_EFFECTIVE,
        "source": f"Lớp text số hóa của {os.path.basename(SOURCE_PDF)}",
        "chapters": [chapters[k] for k in sorted(chapters)],
        "appendices": [{"letter": k, "title": v} for k, v in APPENDIX_TITLES.items()]
    }

    with open(os.path.join(OUT_DIR, "qcvn_41_2019_structured.json"), "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=1)

    _write_jsonl(os.path.join(OUT_DIR, "qcvn_41_articles.jsonl"), [
        {
            "page_content": article_full_text(a),
            "metadata": {
                "doc_id": DOC_ID, "doc_name": DOC_NAME,
                "article_number": a["article_number"],
                "article_header": f"Điều {a['article_number']}. {a['article_title']}",
                "chapter_number": a["chapter_number"], "chapter_title": a["chapter_title"]
            }
        }
        for a in articles
    ])
    _write_jsonl(os.path.join(OUT_DIR, "traffic_signs.jsonl"), signs)
    _write_jsonl(os.path.join(OUT_DIR, "road_markings.jsonl"), markings)

    print(f"\n✅ {len(articles)} Điều / {len(chapters)} Chương")
    print(f"✅ {len(signs)} mã biển báo trong catalogue")
    for prefix, label in SIGN_GROUPS.items():
        count = sum(1 for s in signs if s["sign_code"].split(".")[0] == prefix)
        if count:
            print(f"   - {prefix}.xxx  {label}: {count}")
    print(f"✅ {len(markings)} vạch kẻ đường")
    print(f"   - Lưu tại: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
