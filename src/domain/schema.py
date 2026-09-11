"""
Lược đồ khai báo của một Domain Pack.

Một Domain Pack là toàn bộ phần "biết về miền" của hệ thống, tách khỏi engine: kho văn bản gồm
những tài liệu nào, persona và tri thức nền của trợ lý, từ điển ngôn ngữ đời thường của lĩnh
vực đó, và các quy tắc kiểm chứng số liệu/trích dẫn đặc thù.

Engine không được biết gì về giao thông đường bộ. Nó chỉ biết "có một pack đang hoạt động" và
đọc các trường dưới đây. Muốn dùng hệ thống cho quy chế nội bộ, hướng dẫn y khoa hay tài liệu
nhân sự: viết một pack mới, không sửa dòng code engine nào.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentSpec(BaseModel):
    """Một tài liệu trong kho. Thay cho DOC_ALIASES / DOC_GROUPS / DOCUMENTS_METADATA cũ."""

    id: str = Field(description="Mã tài liệu, trùng với doc_id trong chỉ mục")
    code: str = Field(default="", description="Số hiệu văn bản, vd '36/2024/QH15'")
    short_title: str = Field(default="")
    full_title: str = Field(default="")
    doc_type: str = Field(default="", description="Loại tài liệu; cũng dùng để gom nhóm mặc định")
    aliases: List[str] = Field(default_factory=list, description="Tên gọi tắt phân giải về id này")
    summary: str = Field(default="")

    # Siêu dữ liệu tuỳ miền, engine không diễn giải — chỉ chuyển tiếp cho lớp ứng dụng.
    metadata: Dict[str, object] = Field(default_factory=dict)


class CorpusSpec(BaseModel):
    """Kho tài liệu của miền."""

    index_dir: str = Field(default="data/processed")
    documents: List[DocumentSpec] = Field(default_factory=list)
    article_exists: Optional[str] = Field(
        default=None,
        description=(
            "Tuỳ chọn: 'module:hàm' nhận (doc_id, number) -> bool, trả lời mục tài liệu được "
            "trích dẫn có thật trong kho không. Cách đánh số mục là của từng miền nên engine "
            "không tự tra được."
        ),
    )
    groups: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Nhóm tài liệu đặt tên. Bỏ trống thì suy ra từ `doc_type`.",
    )


class LexiconSpec(BaseModel):
    """
    Từ điển ngôn ngữ của miền: bắc cầu giữa cách nói đời thường và thuật ngữ trong văn bản.

    Phần TÁCH TỪ tiếng Việt vẫn nằm trong engine (đó là xử lý ngôn ngữ, không phải tri thức
    miền); còn từ lóng, nhóm thực thể và stopword đặc thù thì thuộc về pack.
    """

    colloquial_aliases: List[List[str]] = Field(
        default_factory=list,
        description="Cặp [cách nói đời thường, cách diễn đạt trong văn bản]",
    )
    entity_hints: List[Dict[str, List[str]]] = Field(
        default_factory=list,
        description="Từ khoá trong câu hỏi -> nhóm thực thể của bản ghi (vd loại phương tiện)",
    )
    stopwords: List[str] = Field(default_factory=list)

    intent_patterns: Dict[str, str] = Field(
        default_factory=dict,
        description="Tên ý định -> biểu thức chính quy nhận diện. Dùng dựng khoá cache tất định.",
    )
    entity_patterns: Dict[str, str] = Field(
        default_factory=dict,
        description="Tên nhóm thực thể -> biểu thức chính quy nhận diện",
    )
    default_intent: str = Field(default="", description="Ý định mặc định khi không khớp gì")


class FigureClassSpec(BaseModel):
    """
    Một lớp số liệu mà lớp kiểm chứng phải đối chiếu với dữ liệu tra cứu nguyên văn.

    Đây là phần đặc thù miền của `answer_guard`: tiền phạt và điểm bằng lái là của giao thông;
    một miền y khoa khai báo liều lượng, một miền nhân sự khai báo số ngày phép.

    CƠ CHẾ trích xuất (cách viết số tiền tiếng Việt, cách quét theo dòng có ngữ cảnh) nằm trong
    engine dưới dạng các `kind` dùng lại được; pack chỉ chọn kind và tham số.
    """

    id: str
    kind: str = Field(
        default="money",
        description=(
            "Cơ chế trích xuất do engine cung cấp: "
            "'money' (số tiền, mọi cách viết tiếng Việt: 6.000.000 / 6 triệu / 6000000), "
            "'contextual_count' (số đi kèm `unit`, chỉ tính ở dòng khớp `context`), "
            "'pattern_count' (số bắt bởi `pattern`, đúng một nhóm bắt)"
        ),
    )
    label: str = Field(default="", description="Cách gọi khi báo lỗi cho người dùng")
    min_value: float = Field(default=0.0, description="Dưới mức này thì bỏ qua, tránh nhiễu")

    unit: str = Field(default="", description="Đơn vị đi sau con số (kind='contextual_count')")
    context: str = Field(default="", description="Regex ngữ cảnh của dòng (kind='contextual_count')")
    pattern: str = Field(default="", description="Regex có đúng 1 nhóm bắt (kind='pattern_count')")


class GuardSpec(BaseModel):
    """Quy tắc kiểm chứng tất định của miền."""

    figure_classes: List[FigureClassSpec] = Field(default_factory=list)
    citation_marker: str = Field(
        default="",
        description="Regex nhận biết câu trả lời CÓ nêu trích dẫn cụ thể",
    )
    no_data_markers: List[str] = Field(
        default_factory=list,
        description=(
            "Chuỗi mà công cụ của miền phát ra để báo 'không tra được gì'. Engine dùng để nhận "
            "ra lượt tra cứu trắng tay và đề xuất người dùng tìm nguồn ngoài."
        ),
    )
    citation_validator: Optional[str] = Field(
        default=None,
        description=(
            "Tuỳ chọn: 'module:hàm' nhận (answer, verified_sources) và trả danh sách trích dẫn "
            "SAI. Engine kiểm được số liệu cho mọi miền, nhưng xác minh một trích dẫn có thật "
            "hay không đòi hiểu cách đánh số căn cứ của chính lĩnh vực đó."
        ),
    )


class PolicySpec(BaseModel):
    """
    Chính sách vận hành phụ thuộc mức rủi ro của miền.

    Ví dụ dung sai trúng cache: miền pháp lý đòi rất chặt (0.97) vì trả nhầm câu hỏi tương tự
    có thể cho ra mức phạt của loại xe khác; một miền hỏi đáp nội bộ có thể nới hơn.
    """

    cache_similarity: float = Field(default=0.97, ge=0.0, le=1.0)
    cache_ttl_days: int = Field(default=30, ge=1)
    max_tool_turns: int = Field(default=4, ge=1)


class ToolSpec(BaseModel):
    """
    Một công cụ mà pack phơi ra cho Agent.

    `handler` trỏ tới hàm thực thi theo dạng 'module:hàm'. Engine chỉ nạp và gọi, không biết
    công cụ đó làm gì — nhờ vậy bộ công cụ hoàn toàn do pack quyết định.
    """

    name: str
    description: str
    handler: str = Field(description="Đường dẫn 'module:hàm' của hàm thực thi, trả về chuỗi")
    parameters: Dict[str, object] = Field(
        default_factory=dict,
        description="JSON Schema tham số, đúng định dạng function calling",
    )
    evidence_builder: Optional[str] = Field(
        default=None,
        description=(
            "Tuỳ chọn: 'module:hàm' nhận (args, raw_output) và trả danh sách Evidence có cấu "
            "trúc (trích dẫn, ảnh minh hoạ, điểm liên quan) để dựng khối nguồn cho giao diện. "
            "Không khai báo thì engine dựng một Evidence chung từ nguyên văn kết quả — miền mới "
            "chạy được ngay mà không cần viết gì thêm."
        ),
    )


class PresentationSpec(BaseModel):
    """
    Tuỳ chọn: cách diễn đạt tiến trình tra cứu cho người dùng xem.

    Engine có bản mặc định dùng được cho mọi miền; pack khai báo thêm khi muốn câu chữ sát với
    lĩnh vực của mình ("Tra cứu khung tiền phạt..." thay vì "Đang chạy công cụ penalty_lookup").
    """

    describe_call: Optional[str] = Field(
        default=None, description="'module:hàm' nhận (tool_name, args) -> chuỗi mô tả"
    )
    summarize_result: Optional[str] = Field(
        default=None, description="'module:hàm' nhận (tool_name, raw_output) -> chuỗi tóm tắt"
    )


class DomainPackSpec(BaseModel):
    """Toàn bộ khai báo của một miền."""

    id: str
    name: str = Field(default="")
    language: str = Field(default="vi")

    corpus: CorpusSpec = Field(default_factory=CorpusSpec)
    lexicon: LexiconSpec = Field(default_factory=LexiconSpec)
    guard: GuardSpec = Field(default_factory=GuardSpec)
    policy: PolicySpec = Field(default_factory=PolicySpec)
    tools: List[ToolSpec] = Field(default_factory=list)
    presentation: PresentationSpec = Field(default_factory=PresentationSpec)

    system_prompt_file: str = Field(default="prompts/system.md")
    lexicon_file: Optional[str] = Field(default=None, description="Tách lexicon ra tệp riêng")
    guard_file: Optional[str] = Field(default=None, description="Tách guard ra tệp riêng")
