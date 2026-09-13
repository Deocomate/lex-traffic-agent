"""
Xử lý văn bản tiếng Việt cho tầng truy xuất.

Ranh giới cố ý của module này: nó giữ phần XỬ LÝ NGÔN NGỮ (chuẩn hoá chuỗi, tách unigram, sinh
bigram) — thứ đúng với mọi văn bản tiếng Việt bất kể lĩnh vực — còn phần TRI THỨC MIỀN (từ lóng
của lĩnh vực, nhóm thực thể, stopword đặc thù) thì đọc từ Domain Pack đang hoạt động.

Trước đây module này chứa cứng 47 cặp tiếng lóng giao thông ("kẹp 3" -> "chở theo 02 người trên
xe"), bảng nhóm phương tiện và danh sách stopword có cả "phạt", "xe", "lái". Một hệ thống hỏi
đáp quy chế nội bộ hay hướng dẫn y khoa dùng lại module này sẽ nhận nguyên bộ từ vựng giao
thông — đó chính là kiểu ràng buộc khiến kiến trúc không tái dùng được.
"""

import re
from typing import List, Set, Tuple

# Hư từ tiếng Việt thuần tuý: không mang thông tin phân biệt trong BẤT KỲ lĩnh vực nào, nên
# thuộc về engine. Stopword đặc thù lĩnh vực ("phạt", "xe", "lái") do Domain Pack bổ sung.
BASE_STOPWORDS: Set[str] = {
    "là", "và", "của", "khi", "cho", "với", "thì", "bị", "được", "các", "những", "một", "có",
    "không", "trong", "trên", "về", "để", "hay", "hoặc", "này", "đó", "bao", "nhiêu",
    "sẽ", "nếu", "mà", "ra", "tôi", "bạn", "hỏi", "ạ", "nhỉ", "vậy",
}

_stopwords_cache: Set[str] | None = None
_aliases_cache: List[Tuple[str, str]] | None = None
_entity_hints_cache: List[Tuple[Tuple[str, ...], Tuple[str, ...]]] | None = None


def reset_lexicon_cache() -> None:
    """Xoá cache từ điển khi đổi Domain Pack. Gọi bởi `src.domain.registry.set_active_domain`."""
    global _stopwords_cache, _aliases_cache, _entity_hints_cache
    _stopwords_cache = None
    _aliases_cache = None
    _entity_hints_cache = None


def _domain():
    """Pack đang hoạt động. Nhập trong hàm để tránh phụ thuộc vòng lúc khởi động."""
    from src.domain.registry import get_active_domain

    return get_active_domain()


def stopwords() -> Set[str]:
    """Hư từ chung của tiếng Việt, hợp với stopword đặc thù của miền."""
    global _stopwords_cache
    if _stopwords_cache is None:
        try:
            _stopwords_cache = BASE_STOPWORDS | _domain().stopwords
        except Exception:
            _stopwords_cache = set(BASE_STOPWORDS)
    return _stopwords_cache


def colloquial_aliases() -> List[Tuple[str, str]]:
    """Cặp (cách nói đời thường, cách diễn đạt trong văn bản) do miền khai báo."""
    global _aliases_cache
    if _aliases_cache is None:
        try:
            _aliases_cache = _domain().colloquial_aliases
        except Exception:
            _aliases_cache = []
    return _aliases_cache


def entity_hints() -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    """Từ khoá trong câu hỏi -> nhóm thực thể của bản ghi (miền giao thông: loại phương tiện)."""
    global _entity_hints_cache
    if _entity_hints_cache is None:
        try:
            _entity_hints_cache = _domain().entity_hints
        except Exception:
            _entity_hints_cache = []
    return _entity_hints_cache


def normalize_text(text: str) -> str:
    """Chuẩn hóa văn bản tiếng Việt: chữ thường, chuẩn khoảng trắng, loại ký tự đặc biệt."""
    lowered = text.lower().strip()
    return re.sub(r"[\s\.,;:\?!_/\-]+", " ", lowered).strip()


def tokens(text: str, remove_stopwords: bool = True) -> List[str]:
    """Tách từ tiếng Việt đơn giản (unigram) không phụ thuộc thư viện ngoài."""
    words = re.findall(r"[0-9a-zà-ỹ]+", text.lower())
    if remove_stopwords:
        stop = stopwords()
        return [w for w in words if len(w) > 1 and w not in stop]
    return [w for w in words if len(w) > 1]


def bigrams(tokens_list: List[str]) -> Set[str]:
    """Tập cặp từ liền kề, đóng vai trò neo cụm từ khi so khớp."""
    return {f"{a} {b}" for a, b in zip(tokens_list, tokens_list[1:])}


def expand_query(query: str) -> Tuple[str, List[str]]:
    """
    Thêm cách diễn đạt chuẩn của lĩnh vực vào truy vấn thông tục.
    Trả kèm danh sách cụm đã được thêm vào.
    """
    lowered = query.strip().lower()
    added = [formal for slang, formal in colloquial_aliases() if slang in lowered]
    return " ".join([lowered] + added), added


def preferred_entities(query: str) -> Tuple[str, ...]:
    """Nhóm thực thể mà câu hỏi nhắm tới; rỗng nghĩa là câu hỏi không nêu rõ."""
    lowered = query.lower()
    for triggers, groups in entity_hints():
        if any(t in lowered for t in triggers):
            return groups
    return ()


# Tên cũ, giữ cho mã nội bộ đã dùng. Miền giao thông gọi nhóm thực thể là "phương tiện".
preferred_vehicles = preferred_entities
