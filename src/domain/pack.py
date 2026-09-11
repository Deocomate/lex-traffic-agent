"""
Nạp và truy vấn Domain Pack đang hoạt động.

`DomainPack` là lớp bọc quanh `DomainPackSpec` đã nạp, cung cấp sẵn các tra cứu mà engine cần
mỗi lượt chạy (phân giải alias tài liệu, gom nhóm, biên dịch sẵn regex của lexicon) thay vì bắt
mỗi nơi gọi tự dựng lại.

Pack hoạt động chọn bằng biến môi trường `ACTIVE_DOMAIN`, mặc định `vietnam_traffic`. Đây là
biến cấu hình DUY NHẤT còn lại thay cho cả loạt tham số hiệu chuẩn đã gỡ bỏ.
"""

import importlib
import os
import re
from functools import cached_property
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import yaml

from src.domain.schema import DomainPackSpec, GuardSpec, LexiconSpec
from src.paths import project_root

DEFAULT_DOMAIN = "vietnam_traffic"
DOMAINS_DIRNAME = "domains"
MANIFEST_FILENAME = "domain.yaml"


class DomainPackError(RuntimeError):
    """Pack thiếu hoặc khai báo sai. Luôn nêu rõ đường dẫn để sửa được ngay."""


def _read_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class DomainPack:
    """Một miền đã nạp: kho tài liệu, persona, từ điển, quy tắc kiểm chứng và bộ công cụ."""

    def __init__(self, spec: DomainPackSpec, root: str, base_dir: str):
        self.spec = spec
        self.root = root
        self.base_dir = base_dir

    # ------------------------------------------------------------------
    # Nhận dạng
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def name(self) -> str:
        return self.spec.name or self.spec.id

    @property
    def policy(self):
        return self.spec.policy

    # ------------------------------------------------------------------
    # Kho tài liệu
    # ------------------------------------------------------------------

    @cached_property
    def document_ids(self) -> List[str]:
        return [d.id for d in self.spec.corpus.documents]

    @cached_property
    def documents_by_id(self) -> Dict[str, Any]:
        return {d.id: d for d in self.spec.corpus.documents}

    @cached_property
    def aliases(self) -> Dict[str, str]:
        """Mọi tên gọi tắt -> mã tài liệu chuẩn. Thay cho DOC_ALIASES gõ tay."""
        table: Dict[str, str] = {}
        for doc in self.spec.corpus.documents:
            table[doc.id.lower()] = doc.id
            for alias in doc.aliases:
                table[alias.strip().lower()] = doc.id
        return table

    @cached_property
    def groups(self) -> Dict[str, List[str]]:
        """
        Nhóm tài liệu. Khai báo tường minh thì dùng luôn; không thì suy ra từ `doc_type`.

        Nhóm `all` luôn có sẵn để nơi gọi không phải xử lý riêng trường hợp "toàn bộ kho".
        """
        groups: Dict[str, List[str]] = {k: list(v) for k, v in self.spec.corpus.groups.items()}
        for doc in self.spec.corpus.documents:
            if doc.doc_type:
                groups.setdefault(doc.doc_type, []).append(doc.id)
        groups["all"] = list(self.document_ids)
        return groups

    @cached_property
    def article_exists(self) -> Optional[Callable[..., bool]]:
        target = self.spec.corpus.article_exists
        return _lazy_handler(target, "corpus.article_exists") if target else None

    def resolve_doc_ids(self, raw: Optional[Iterable[str]]) -> Optional[Set[str]]:
        """Phân giải tên nhóm hoặc alias thành tập mã tài liệu chuẩn."""
        if not raw:
            return None
        resolved: Set[str] = set()
        for item in raw:
            key = str(item).strip().lower()
            if key in self.groups:
                resolved.update(self.groups[key])
            elif key in self.aliases:
                resolved.add(self.aliases[key])
            else:
                resolved.add(item)
        return resolved

    # ------------------------------------------------------------------
    # Persona
    # ------------------------------------------------------------------

    @cached_property
    def system_prompt(self) -> str:
        path = os.path.join(self.root, self.spec.system_prompt_file)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            raise DomainPackError(f"Không đọc được system prompt của miền tại {path}: {e}") from e

    # ------------------------------------------------------------------
    # Từ điển
    # ------------------------------------------------------------------

    @cached_property
    def lexicon(self) -> LexiconSpec:
        if self.spec.lexicon_file:
            return LexiconSpec.model_validate(_read_yaml(os.path.join(self.root, self.spec.lexicon_file)))
        return self.spec.lexicon

    @cached_property
    def colloquial_aliases(self) -> List[Tuple[str, str]]:
        return [(pair[0], pair[1]) for pair in self.lexicon.colloquial_aliases if len(pair) >= 2]

    @cached_property
    def entity_hints(self) -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
        hints = []
        for entry in self.lexicon.entity_hints:
            triggers = tuple(entry.get("match", []))
            values = tuple(entry.get("groups", []))
            if triggers and values:
                hints.append((triggers, values))
        return hints

    @cached_property
    def stopwords(self) -> Set[str]:
        return set(self.lexicon.stopwords)

    @cached_property
    def intent_patterns(self) -> Dict[str, re.Pattern]:
        return {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.lexicon.intent_patterns.items()
        }

    @cached_property
    def entity_patterns(self) -> Dict[str, re.Pattern]:
        return {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.lexicon.entity_patterns.items()
        }

    @property
    def default_intent(self) -> str:
        return self.lexicon.default_intent

    # ------------------------------------------------------------------
    # Kiểm chứng
    # ------------------------------------------------------------------

    @cached_property
    def guard(self) -> GuardSpec:
        if self.spec.guard_file:
            return GuardSpec.model_validate(_read_yaml(os.path.join(self.root, self.spec.guard_file)))
        return self.spec.guard

    @cached_property
    def citation_marker(self) -> Optional[re.Pattern]:
        marker = self.guard.citation_marker
        return re.compile(marker, re.IGNORECASE) if marker else None

    @cached_property
    def no_data_markers(self) -> List[str]:
        return list(self.guard.no_data_markers)

    @cached_property
    def citation_validator(self) -> Optional[Callable[..., List[str]]]:
        target = self.guard.citation_validator
        return _lazy_handler(target, "guard.citation_validator") if target else None

    # ------------------------------------------------------------------
    # Công cụ
    # ------------------------------------------------------------------

    @cached_property
    def tools_schema(self) -> List[Dict[str, Any]]:
        """Khai báo công cụ theo đúng định dạng function calling để bind vào mô hình."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.spec.tools
        ]

    @cached_property
    def tool_handlers(self) -> Dict[str, Callable[..., str]]:
        """
        Nạp hàm thực thi của từng công cụ từ chuỗi 'module:hàm'.

        Nạp lười theo từng công cụ để một pack khai báo hỏng một handler không làm sập cả hệ
        thống — lỗi chỉ nổ ra khi Agent thật sự gọi tới đúng công cụ đó.
        """
        handlers: Dict[str, Callable[..., str]] = {}
        for tool in self.spec.tools:
            handlers[tool.name] = _lazy_handler(tool.handler, tool.name)
        return handlers

    def tool_names(self) -> List[str]:
        return [tool.name for tool in self.spec.tools]

    @cached_property
    def evidence_builders(self) -> Dict[str, Callable[..., Any]]:
        """Hàm dựng Evidence có cấu trúc cho từng công cụ, nếu miền khai báo."""
        return {
            tool.name: _lazy_handler(tool.evidence_builder, f"{tool.name}.evidence_builder")
            for tool in self.spec.tools
            if tool.evidence_builder
        }

    @cached_property
    def describe_call(self) -> Optional[Callable[..., str]]:
        target = self.spec.presentation.describe_call
        return _lazy_handler(target, "presentation.describe_call") if target else None

    @cached_property
    def summarize_result(self) -> Optional[Callable[..., str]]:
        target = self.spec.presentation.summarize_result
        return _lazy_handler(target, "presentation.summarize_result") if target else None


def _lazy_handler(target: str, tool_name: str) -> Callable[..., str]:
    """Bọc 'module:hàm' thành callable chỉ import khi được gọi lần đầu."""
    cache: Dict[str, Callable[..., str]] = {}

    def call(**kwargs: Any) -> str:
        if "fn" not in cache:
            if ":" not in target:
                raise DomainPackError(
                    f"Công cụ '{tool_name}' khai báo handler sai: '{target}'. Cần dạng 'module:hàm'."
                )
            module_name, func_name = target.split(":", 1)
            try:
                module = importlib.import_module(module_name)
                cache["fn"] = getattr(module, func_name)
            except (ImportError, AttributeError) as e:
                raise DomainPackError(
                    f"Không nạp được handler '{target}' của công cụ '{tool_name}': {e}"
                ) from e
        return cache["fn"](**kwargs)

    return call


def load_domain_pack(domain_id: str, base_dir: Optional[str] = None) -> DomainPack:
    """Nạp một pack từ `domains/<domain_id>/domain.yaml`."""
    if not base_dir:
        base_dir = project_root()

    root = os.path.join(base_dir, DOMAINS_DIRNAME, domain_id)
    manifest = os.path.join(root, MANIFEST_FILENAME)
    if not os.path.exists(manifest):
        available = _available_domains(base_dir)
        raise DomainPackError(
            f"Không tìm thấy Domain Pack '{domain_id}' tại {manifest}. "
            f"Các miền hiện có: {', '.join(available) or '(chưa có)'}"
        )

    spec = DomainPackSpec.model_validate(_read_yaml(manifest))
    return DomainPack(spec=spec, root=root, base_dir=base_dir)


def _available_domains(base_dir: str) -> List[str]:
    domains_dir = os.path.join(base_dir, DOMAINS_DIRNAME)
    if not os.path.isdir(domains_dir):
        return []
    return sorted(
        name
        for name in os.listdir(domains_dir)
        if os.path.exists(os.path.join(domains_dir, name, MANIFEST_FILENAME))
    )
