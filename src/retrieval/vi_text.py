"""
Module xử lý văn bản tiếng Việt cho hệ thống truy xuất LexTraffic AI.
Bao gồm tách token (unigram), sinh bigram neo ngữ nghĩa, loại bỏ stopword,
và mở rộng truy vấn thông tục sang ngôn ngữ văn bản pháp luật.
"""

import re
from typing import List, Set, Tuple

# Từ thông tục -> cách diễn đạt trong văn bản pháp luật.
# Bắc cầu ngôn ngữ đời thường sang thuật ngữ chuẩn xác của văn bản.
COLLOQUIAL_ALIASES: List[Tuple[str, str]] = [
    ("vượt đèn đỏ", "không chấp hành hiệu lệnh của đèn tín hiệu giao thông"),
    ("đèn đỏ", "không chấp hành hiệu lệnh của đèn tín hiệu giao thông"),
    ("vượt đèn vàng", "không chấp hành hiệu lệnh của đèn tín hiệu giao thông"),
    ("nhậu", "nồng độ cồn"),
    ("uống bia", "nồng độ cồn"),
    ("uống rượu", "nồng độ cồn"),
    ("say xỉn", "nồng độ cồn"),
    ("thổi cồn", "nồng độ cồn"),
    ("kẹp 3", "chở theo 02 người trên xe"),
    ("kẹp ba", "chở theo 02 người trên xe"),
    ("chở 3", "chở theo 02 người trên xe"),
    ("leo vỉa hè", "điều khiển xe đi trên vỉa hè"),
    ("lên vỉa hè", "điều khiển xe đi trên vỉa hè"),
    ("bấm điện thoại", "dùng tay cầm và sử dụng điện thoại"),
    ("nghe điện thoại", "dùng tay cầm và sử dụng điện thoại"),
    ("lướt điện thoại", "dùng tay cầm và sử dụng điện thoại"),
    ("bắn tốc độ", "chạy quá tốc độ quy định"),
    ("phóng nhanh", "chạy quá tốc độ quy định"),
    ("chạy quá tốc độ", "chạy quá tốc độ quy định"),
    ("không đội mũ", "không đội mũ bảo hiểm"),
    ("quên mũ", "không đội mũ bảo hiểm"),
    ("đi ngược chiều", "đi ngược chiều của đường một chiều"),
    ("lấn làn", "không đi đúng phần đường, làn đường"),
    ("không gương", "không có gương chiếu hậu"),
    ("không bằng lái", "không có giấy phép lái xe"),
    ("quên bằng lái", "không mang theo giấy phép lái xe"),
    ("đua xe", "đua xe trái phép"),
    ("bốc đầu", "điều khiển xe bằng một bánh"),
    ("dàn hàng ngang", "đi dàn hàng ngang"),
    ("làn khẩn cấp", "chạy ở làn dừng xe khẩn cấp"),
    ("làn dừng khẩn cấp", "chạy ở làn dừng xe khẩn cấp"),
    ("làn dừng xe khẩn cấp", "chạy ở làn dừng xe khẩn cấp"),
    ("vào cao tốc", "đi vào đường cao tốc"),
    ("lên cao tốc", "đi vào đường cao tốc"),
    ("chạy vào cao tốc", "đi vào đường cao tốc"),
    ("dừng ở làn khẩn cấp", "dừng xe, đỗ xe ở làn dừng xe khẩn cấp"),
    ("đỗ ở làn khẩn cấp", "dừng xe, đỗ xe ở làn dừng xe khẩn cấp"),
]

# Từ khóa loại phương tiện trong câu hỏi -> nhóm phương tiện của bản ghi
VEHICLE_QUERY_HINTS: List[Tuple[Tuple[str, ...], Tuple[str, ...]]] = [
    (("ô tô", "oto", "xe hơi", "xe con", "xe 4 chỗ", "xe bốn chỗ"), ("Ô tô", "Ô tô tải", "Ô tô chở khách")),
    (("xe máy", "mô tô", "xe gắn máy", "xe số", "tay ga", "xe côn"), ("Xe máy / Xe mô tô",)),
    (("xe đạp", "xe thô sơ", "xe đạp điện"), ("Xe đạp / Xe thô sơ",)),
    (("đi bộ", "người đi bộ"), ("Người đi bộ",)),
    (("xe tải",), ("Ô tô tải",)),
    (("xe khách", "xe buýt", "chở khách"), ("Ô tô chở khách",)),
    (("máy chuyên dùng",), ("Xe máy chuyên dùng",)),
]

# Hư từ tiếng Việt: không mang thông tin phân biệt hành vi nên loại khỏi việc chấm điểm
STOPWORDS: Set[str] = {
    "là", "và", "của", "khi", "cho", "với", "thì", "bị", "được", "các", "những", "một", "có",
    "không", "trong", "trên", "về", "để", "hay", "hoặc", "này", "đó", "bao", "nhiêu", "tiền",
    "phạt", "mức", "xử", "lỗi", "vi", "phạm", "sẽ", "nếu", "mà", "ra", "đi", "lái", "người",
    "điều", "khiển", "xe", "tôi", "bạn", "hỏi", "ạ", "nhỉ", "vậy",
}


def normalize_text(text: str) -> str:
    """Chuẩn hóa văn bản tiếng Việt: chữ thường, chuẩn khoảng trắng, loại ký tự đặc biệt."""
    lowered = text.lower().strip()
    return re.sub(r"[\s\.,;:\?!_/\-]+", " ", lowered).strip()


def tokens(text: str, remove_stopwords: bool = True) -> List[str]:
    """Tách từ tiếng Việt đơn giản (unigram) không phụ thuộc thư viện ngoài."""
    words = re.findall(r"[0-9a-zà-ỹ]+", text.lower())
    if remove_stopwords:
        return [w for w in words if len(w) > 1 and w not in STOPWORDS]
    return [w for w in words if len(w) > 1]


def bigrams(tokens_list: List[str]) -> Set[str]:
    """Tập cặp từ liền kề, đóng vai trò neo cụm từ khi so khớp."""
    return {f"{a} {b}" for a, b in zip(tokens_list, tokens_list[1:])}


def expand_query(query: str) -> Tuple[str, List[str]]:
    """
    Thêm cách diễn đạt pháp lý tương ứng vào truy vấn thông tục.
    Trả kèm danh sách cụm pháp lý ĐÃ được thêm vào.
    """
    lowered = query.strip().lower()
    added = [legal for slang, legal in COLLOQUIAL_ALIASES if slang in lowered]
    return " ".join([lowered] + added), added


def preferred_vehicles(query: str) -> Tuple[str, ...]:
    """Nhóm phương tiện mà câu hỏi nhắm tới; rỗng nghĩa là không nêu rõ loại xe."""
    lowered = query.lower()
    for hints, vehicles in VEHICLE_QUERY_HINTS:
        if any(h in lowered for h in hints):
            return vehicles
    return ()
