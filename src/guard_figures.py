"""
Cơ chế trích xuất số liệu cho lớp kiểm chứng tất định.

Phân chia trách nhiệm ở đây là điểm mấu chốt để `answer_guard` dùng lại được cho miền khác:

- ENGINE (tệp này) giữ CƠ CHẾ: cách viết số trong tiếng Việt (6.000.000 / 6 triệu / 6000000),
  cách quét con số theo dòng có ngữ cảnh và mang ngữ cảnh qua các dòng của bảng Markdown.
  Những thứ này đúng với mọi lĩnh vực dùng tiếng Việt.

- DOMAIN PACK khai báo LỰA CHỌN: miền có những lớp số liệu nào, gọi tên là gì, ngưỡng bỏ qua
  bao nhiêu. Giao thông khai báo tiền phạt / tháng tước bằng / điểm bị trừ; một miền y khoa
  khai báo liều lượng và số ngày điều trị, dùng đúng các cơ chế này.
"""

import re
from typing import Callable, List, Set, Tuple

# 6.000.000 — dạng số có dấu phân nhóm hàng nghìn của tiếng Việt
_GROUPED_NUMBER = re.compile(r'\d{1,3}(?:\.\d{3})+')

# 6 triệu, 6,5 triệu, 800 nghìn, 2tr — mô hình hay viết tắt thay vì chép nguyên văn
_SCALED_NUMBER = re.compile(r'(\d+(?:[.,]\d+)?)\s*(triệu|nghìn|ngàn|tr)\b', re.IGNORECASE)
_SCALE_FACTORS = {"triệu": 1_000_000, "tr": 1_000_000, "nghìn": 1_000, "ngàn": 1_000}

# 6000000 — số viết liền không dấu phân nhóm
_PLAIN_NUMBER = re.compile(r'(?<![\d.,])(\d{6,10})(?![\d.,])')


def money_values(text: str) -> Set[int]:
    """Mọi khoản tiền trong văn bản, quy về số nguyên để so khớp bất kể cách viết."""
    values: Set[int] = set()
    for raw in _GROUPED_NUMBER.findall(text):
        values.add(int(raw.replace(".", "")))
    for raw, unit in _SCALED_NUMBER.findall(text):
        try:
            amount = float(raw.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        values.add(int(amount * _SCALE_FACTORS[unit.lower()]))
    for raw in _PLAIN_NUMBER.findall(text):
        values.add(int(raw))
    return values


def format_money(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " đồng"


def contextual_counts(text: str, context: re.Pattern, unit: str) -> Set[int]:
    """
    Số đi kèm `unit`, chỉ tính ở những dòng có ngữ cảnh phù hợp.

    Mô hình hay trình bày chế tài dưới dạng bảng Markdown: cụm ngữ cảnh ('Tước GPLX') chỉ nằm ở
    dòng tiêu đề còn con số nằm ở các dòng sau — nên ngữ cảnh được giữ cho cả khối bảng. Không
    có cơ chế mang ngữ cảnh này thì mọi số liệu trong bảng đều bị bỏ sót.
    """
    single = re.compile(rf'(\d{{1,3}})\s*{re.escape(unit)}', re.IGNORECASE)
    # Khoảng viết tắt "10 – 12 tháng": số đầu không đi kèm đơn vị nên phải bắt riêng.
    ranged = re.compile(
        rf'(\d{{1,3}})\s*(?:[-–—]|đến|tới)\s*\d{{1,3}}\s*{re.escape(unit)}', re.IGNORECASE
    )

    values: Set[int] = set()
    table_context = False
    for line in text.splitlines():
        is_table_row = line.strip().startswith("|")
        if not is_table_row:
            table_context = False
        if context.search(line):
            table_context = is_table_row
        elif not (is_table_row and table_context):
            continue
        values.update(int(n) for n in single.findall(line))
        values.update(int(n) for n in ranged.findall(line))
    return values


def pattern_counts(text: str, pattern: re.Pattern) -> Set[int]:
    """Số bắt bởi một regex có đúng một nhóm bắt."""
    return {int(n) for n in pattern.findall(text)}


# (id, hàm trích xuất, hàm định dạng hiển thị, ngưỡng bỏ qua)
FigureCategory = Tuple[str, Callable[[str], Set[int]], Callable[[int], str], float]


def build_categories(figure_classes) -> List[FigureCategory]:
    """
    Dựng bảng trích xuất từ khai báo của Domain Pack.

    Lớp nào khai báo `kind` mà engine không hỗ trợ thì bị bỏ qua thay vì làm sập hệ thống: mất
    một lớp kiểm chứng vẫn tốt hơn là không trả lời được câu nào.
    """
    categories: List[FigureCategory] = []

    for spec in figure_classes:
        label = spec.label or spec.id

        if spec.kind == "money":
            categories.append((spec.id, money_values, format_money, spec.min_value))

        elif spec.kind == "contextual_count":
            if not spec.unit:
                continue
            context = re.compile(spec.context or ".", re.IGNORECASE)
            unit = spec.unit
            categories.append((
                spec.id,
                lambda text, c=context, u=unit: contextual_counts(text, c, u),
                lambda v, lb=label: f"{v} {lb}",
                spec.min_value,
            ))

        elif spec.kind == "pattern_count":
            if not spec.pattern:
                continue
            compiled = re.compile(spec.pattern, re.IGNORECASE)
            categories.append((
                spec.id,
                lambda text, p=compiled: pattern_counts(text, p),
                lambda v, lb=label: f"{v} {lb}",
                spec.min_value,
            ))

    return categories
