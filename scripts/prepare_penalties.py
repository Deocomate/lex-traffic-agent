"""
Trích xuất và cấu trúc hóa NGHỊ ĐỊNH 168/2024/NĐ-CP (xử phạt VPHC về trật tự ATGT đường bộ,
trừ điểm & phục hồi điểm GPLX — hiệu lực 01/01/2025, thay thế NĐ 100/2019 và NĐ 123/2021).

Vì sao không parse thẳng từ PDF: data/raw_data/03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham.pdf
là bản scan ảnh (111 trang, 0 lớp text), OCR sẽ sai lệch chính con số tiền phạt. Script dùng
bản số hóa trên vi.wikisource — cùng nguồn mà scripts/prepare_data.py đã dùng cho Luật 36/2024.

Xuất ra:
1. data/processed/nghi_dinh_168_2024_structured.json  — cây Chương / Điều / Khoản / Điểm
2. data/processed/penalty_chunks.jsonl                — mỗi hành vi vi phạm một bản ghi, kèm
   khung tiền phạt, hình thức xử phạt bổ sung, số điểm GPLX bị trừ và trích dẫn chính xác

Mỗi bản ghi mang đủ căn cứ để Agent trích dẫn đúng "Điểm c Khoản 7 Điều 7 Nghị định
168/2024/NĐ-CP" thay vì gán số tiền cho một Điều của Luật 36/2024 (Luật không quy định tiền phạt).
"""

import os
import re
import sys
import json
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legal_text_parser import fetch_wikisource, normalize, parse_articles

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "processed")

DOC_ID = "03_nghi_dinh_168_2024_nd_cp"
DOC_NAME = "Nghị định 168/2024/NĐ-CP"
DOC_FULL_NAME = (
    "Nghị định 168/2024/NĐ-CP quy định xử phạt vi phạm hành chính về trật tự, an toàn giao thông "
    "trong lĩnh vực giao thông đường bộ; trừ điểm, phục hồi điểm giấy phép lái xe"
)
DATE_EFFECTIVE = "01/01/2025"

PAGE_PREFIX = "Nghị định số 168/2024/NĐ-CP"

CHAPTERS = [
    ("I", "QUY ĐỊNH CHUNG"),
    ("II", "HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT, MỨC TRỪ ĐIỂM GIẤY PHÉP LÁI XE VÀ BIỆN PHÁP KHẮC PHỤC HẬU QUẢ VI PHẠM HÀNH CHÍNH VỀ TRẬT TỰ, AN TOÀN GIAO THÔNG TRONG LĨNH VỰC GIAO THÔNG ĐƯỜNG BỘ"),
    ("III", "THẨM QUYỀN XỬ PHẠT, THẨM QUYỀN LẬP BIÊN BẢN VI PHẠM HÀNH CHÍNH"),
    ("IV", "ĐIỀU KHOẢN THI HÀNH"),
]

# Nhãn phương tiện suy ra từ tiêu đề Điều — dùng để lọc kết quả theo loại xe người dùng hỏi.
# Thứ tự có ý nghĩa: mẫu cụ thể phải đứng trước mẫu tổng quát.
VEHICLE_PATTERNS: List[Tuple[str, str]] = [
    ("người đi bộ", "Người đi bộ"),
    ("dẫn dắt vật nuôi", "Người dẫn dắt vật nuôi"),
    ("hành khách đi xe", "Hành khách đi xe"),
    ("chủ phương tiện", "Chủ phương tiện"),
    ("xe đạp", "Xe đạp / Xe thô sơ"),
    ("xe thô sơ", "Xe đạp / Xe thô sơ"),
    ("xe mô tô, xe gắn máy", "Xe máy / Xe mô tô"),
    ("xe máy chuyên dùng", "Xe máy chuyên dùng"),
    ("xe cứu thương", "Xe cứu thương"),
    ("xe cứu hộ", "Xe cứu hộ giao thông"),
    ("xe ô tô chở hành khách", "Ô tô chở khách"),
    ("xe ô tô tải", "Ô tô tải"),
    ("xe ô tô", "Ô tô"),
    ("đua xe", "Đua xe trái phép"),
    ("đào tạo, sát hạch", "Đào tạo, sát hạch lái xe"),
    ("đăng kiểm", "Đăng kiểm"),
]

# "Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng"
RE_FINE = re.compile(r'Phạt tiền từ\s+([\d.]+)\s*đồng\s+đến\s+([\d.]+)\s*đồng')

# Khoản chứa chế tài áp cho hành vi ở khoản/điểm khác
RE_EXTRA_CLAUSE = re.compile(r'hình thức xử phạt bổ sung', re.IGNORECASE)
RE_POINTS_CLAUSE = re.compile(r'bị trừ điểm giấy phép lái xe', re.IGNORECASE)
RE_POINTS_VALUE = re.compile(r'trừ điểm giấy phép lái xe\s+(\d{1,2})\s*điểm', re.IGNORECASE)

# Một đơn vị dẫn chiếu: "điểm b, điểm c, điểm d khoản 6" hoặc "khoản 5"
RE_REF_UNIT = re.compile(
    r'((?:điểm\s+[a-zđ]{1,2}\s*(?:,\s*điểm\s+[a-zđ]{1,2}\s*)*)?)khoản\s+(\d{1,2})',
    re.IGNORECASE
)
RE_REF_POINT_LETTERS = re.compile(r'điểm\s+([a-zđ]{1,2})', re.IGNORECASE)
RE_REF_OTHER_ARTICLE = re.compile(r'Điều\s+(\d+)(?!\s*này)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Giải mã dẫn chiếu chế tài bổ sung & trừ điểm
# ---------------------------------------------------------------------------

def _parse_references(text: str, current_article: int) -> List[Tuple[int, int, Optional[str]]]:
    """
    Đọc chuỗi dẫn chiếu kiểu 'điểm b, điểm c khoản 6; điểm a khoản 7 Điều này'
    thành danh sách (điều, khoản, điểm|None).
    """
    other_article = RE_REF_OTHER_ARTICLE.search(text)
    article_number = int(other_article.group(1)) if other_article else current_article

    refs: List[Tuple[int, int, Optional[str]]] = []
    for match in RE_REF_UNIT.finditer(text):
        clause_number = int(match.group(2))
        letters = RE_REF_POINT_LETTERS.findall(match.group(1) or "")
        if letters:
            refs.extend((article_number, clause_number, letter.lower()) for letter in letters)
        else:
            refs.append((article_number, clause_number, None))
    return refs


def build_sanction_maps(articles: List[Dict[str, Any]]) -> Tuple[Dict[Tuple, List[str]], Dict[Tuple, int]]:
    """
    Dựng hai bảng tra từ các Khoản 'xử phạt bổ sung' và 'trừ điểm giấy phép lái xe':
      - extras: (điều, khoản, điểm) -> danh sách hình thức xử phạt bổ sung
      - points: (điều, khoản, điểm) -> số điểm GPLX bị trừ

    Các khoản này không mô tả hành vi mà dẫn chiếu ngược tới khoản/điểm khác, nên phải giải mã
    thì Agent mới trả lời được "trừ mấy điểm" cho đúng hành vi người dùng hỏi.
    """
    extras: Dict[Tuple, List[str]] = {}
    points: Dict[Tuple, int] = {}

    for article in articles:
        art_num = article["article_number"]
        for clause in article["clauses"]:
            is_extra = bool(RE_EXTRA_CLAUSE.search(clause["text"]))
            is_points = bool(RE_POINTS_CLAUSE.search(clause["text"]))
            if not (is_extra or is_points):
                continue

            for item in clause["points"] or [{"point_letter": "", "text": clause["text"]}]:
                item_text = item["text"]
                refs = _parse_references(item_text, art_num)
                if not refs:
                    continue

                if is_points:
                    value = RE_POINTS_VALUE.search(item_text)
                    if value:
                        for ref in refs:
                            points[ref] = int(value.group(1))
                else:
                    # Phần chế tài nằm sau cụm dẫn chiếu ("... Điều này bị tước quyền sử dụng ...")
                    sanction = re.sub(r'^.*?Điều\s+(?:này|\d+)\s*', '', item_text)
                    sanction = normalize(sanction).rstrip(';.').strip()
                    if sanction:
                        for ref in refs:
                            extras.setdefault(ref, []).append(sanction)

    return extras, points


# ---------------------------------------------------------------------------
# Sinh bản ghi tra cứu cho từng hành vi vi phạm
# ---------------------------------------------------------------------------

def detect_vehicle(article_title: str) -> str:
    """Suy ra nhóm phương tiện từ tiêu đề Điều để lọc kết quả theo loại xe"""
    lowered = article_title.lower()
    for pattern, label in VEHICLE_PATTERNS:
        if pattern in lowered:
            return label
    return "Chung"


def _money(raw: str) -> int:
    return int(raw.replace(".", ""))


def build_penalty_chunks(articles: List[Dict[str, Any]],
                         extras: Dict[Tuple, List[str]],
                         points: Dict[Tuple, int]) -> List[Dict[str, Any]]:
    """Mỗi hành vi bị phạt tiền trở thành một bản ghi tra cứu độc lập, có trích dẫn đầy đủ"""
    chunks: List[Dict[str, Any]] = []

    for article in articles:
        art_num = article["article_number"]
        vehicle = detect_vehicle(article["article_title"])

        for clause in article["clauses"]:
            fine = RE_FINE.search(clause["text"])
            if not fine:
                continue
            fine_text = fine.group(0)
            fine_min, fine_max = _money(fine.group(1)), _money(fine.group(2))

            # Khoản có điểm a) b) c): mỗi điểm là một hành vi riêng; không có điểm thì lấy cả khoản
            entries = clause["points"] or [{"point_letter": "", "text": clause["text"]}]
            for entry in entries:
                letter = entry["point_letter"]
                key = (art_num, clause["clause_number"], letter or None)
                citation_parts = []
                if letter:
                    citation_parts.append(f"Điểm {letter}")
                citation_parts += [f"Khoản {clause['clause_number']}", f"Điều {art_num}", DOC_NAME]

                chunks.append({
                    "doc_id": DOC_ID,
                    "doc_name": DOC_NAME,
                    "citation": " ".join(citation_parts),
                    "article_number": art_num,
                    "article_title": article["article_title"],
                    "chapter_roman": article["chapter_roman"],
                    "clause_number": clause["clause_number"],
                    "point_letter": letter or None,
                    "vehicle": vehicle,
                    "behaviour": normalize(entry["text"]).rstrip(";").strip(),
                    "fine_text": fine_text,
                    "fine_min": fine_min,
                    "fine_max": fine_max,
                    "extra_sanctions": extras.get(key, []) + extras.get((art_num, clause["clause_number"], None), []),
                    "points_deducted": points.get(key) or points.get((art_num, clause["clause_number"], None))
                })

    return chunks


# ---------------------------------------------------------------------------
# Kiểm chứng dữ liệu sau khi parse
# ---------------------------------------------------------------------------

# Các mốc đối soát lấy trực tiếp từ văn bản gốc: sai một trong số này nghĩa là parser hỏng.
EXPECTED_ARTICLES = 55
SPOT_CHECKS = [
    # (điều, khoản, điểm, tiền tối thiểu, tiền tối đa, mô tả rút gọn để đối chiếu)
    (7, 7, "c", 4_000_000, 6_000_000, "đèn tín hiệu giao thông"),
    (7, 7, "a", 4_000_000, 6_000_000, "vỉa hè"),
]


def validate(articles: List[Dict[str, Any]], chunks: List[Dict[str, Any]]) -> List[str]:
    """Trả về danh sách lỗi phát hiện được; rỗng nghĩa là dữ liệu đạt"""
    errors: List[str] = []

    numbers = [a["article_number"] for a in articles]
    if len(numbers) != EXPECTED_ARTICLES:
        errors.append(f"Số Điều parse được là {len(numbers)}, kỳ vọng {EXPECTED_ARTICLES}")
    missing = [n for n in range(1, EXPECTED_ARTICLES + 1) if n not in numbers]
    if missing:
        errors.append(f"Thiếu Điều: {missing}")

    by_key = {(c["article_number"], c["clause_number"], c["point_letter"]): c for c in chunks}
    for art, clause, letter, low, high, keyword in SPOT_CHECKS:
        chunk = by_key.get((art, clause, letter))
        if not chunk:
            errors.append(f"Không sinh được bản ghi cho Điểm {letter} Khoản {clause} Điều {art}")
            continue
        if (chunk["fine_min"], chunk["fine_max"]) != (low, high):
            errors.append(
                f"Điểm {letter} Khoản {clause} Điều {art}: mức phạt {chunk['fine_min']}-{chunk['fine_max']}, "
                f"kỳ vọng {low}-{high}"
            )
        if keyword not in chunk["behaviour"].lower():
            errors.append(f"Điểm {letter} Khoản {clause} Điều {art}: nội dung không chứa '{keyword}'")

    if any(c["fine_min"] > c["fine_max"] for c in chunks):
        errors.append("Có bản ghi mức phạt tối thiểu lớn hơn tối đa")
    if any(c["fine_min"] < 10_000 for c in chunks):
        errors.append("Có bản ghi mức phạt nhỏ bất thường (< 10.000 đồng) — nghi lỗi tách số")

    return errors


# ---------------------------------------------------------------------------
# Chạy pipeline
# ---------------------------------------------------------------------------

def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 78)
    print(f"  TRÍCH XUẤT {DOC_NAME} (hiệu lực {DATE_EFFECTIVE})")
    print("=" * 78)

    full_md_path = os.path.join(OUT_DIR, "ocr_cache", "03_nghi_dinh_168_2024_nd_cp_full.md")
    all_articles: List[Dict[str, Any]] = []

    if os.path.exists(full_md_path):
        print(f"[Nguồn] Trích xuất trực tiếp từ bản OCR PDF gốc: {os.path.basename(full_md_path)}")
        with open(full_md_path, "r", encoding="utf-8") as f:
            text = f.read()
        text_cleaned = re.sub(r'[\#\*]+', '', text)
        chapter_splits = re.split(r'\n\s*Chương\s+([IVXLCDM]+)\s*\n', text_cleaned, flags=re.IGNORECASE)
        for i in range(1, len(chapter_splits), 2):
            roman = chapter_splits[i].strip()
            content = chapter_splits[i + 1].strip()
            lines = content.splitlines()
            ch_title = lines[0].strip()
            ch_body = "\n".join(lines[1:])
            parsed = parse_articles(ch_body, roman, ch_title)
            all_articles.extend(parsed)
            print(f"   - Chương {roman:<4} ({ch_title[:45]}...): {len(parsed)} Điều")
    else:
        print("[Nguồn] Không thấy cache OCR, tải từ vi.wikisource...")
        for roman, title in CHAPTERS:
            print(f"[Tải] Chương {roman}...", end=" ", flush=True)
            raw = fetch_wikisource(f"{PAGE_PREFIX}/Chương {roman}")
            parsed = parse_articles(raw, roman, title)
            all_articles.extend(parsed)
            print(f"{len(raw):,} ký tự -> {len(parsed)} Điều")

    extras, points = build_sanction_maps(all_articles)
    chunks = build_penalty_chunks(all_articles, extras, points)

    errors = validate(all_articles, chunks)
    if errors:
        print("\n❌ DỮ LIỆU KHÔNG ĐẠT KIỂM CHỨNG:")
        for e in errors:
            print(f"   - {e}")
        return 1

    tree_path = os.path.join(OUT_DIR, "nghi_dinh_168_2024_structured.json")
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump({
            "doc_id": DOC_ID,
            "doc_name": DOC_NAME,
            "doc_full_name": DOC_FULL_NAME,
            "date_effective": DATE_EFFECTIVE,
            "replaces": ["Nghị định 100/2019/NĐ-CP", "Nghị định 123/2021/NĐ-CP"],
            "source": f"Bản OCR 111 trang từ 03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham.pdf",
            "articles": all_articles
        }, f, ensure_ascii=False, indent=2)

    chunks_path = os.path.join(OUT_DIR, "penalty_chunks.jsonl")
    with open(chunks_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    with_points = sum(1 for c in chunks if c["points_deducted"])
    with_extras = sum(1 for c in chunks if c["extra_sanctions"])
    print(f"\n✅ {len(all_articles)} Điều, {len(chunks)} hành vi bị phạt tiền")
    print(f"   - {with_points} hành vi có trừ điểm GPLX, {with_extras} hành vi có xử phạt bổ sung")
    print(f"   - Cây văn bản : {tree_path}")
    print(f"   - Bảng tra    : {chunks_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
