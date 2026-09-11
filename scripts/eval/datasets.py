"""
Quản lý và thẩm định tập dữ liệu Benchmark (Dataset Loader & Validator)
Sử dụng Pydantic để chuẩn hóa schema câu hỏi kiểm thử V2.
Hỗ trợ nạp cả file cũ (v1) và file mới (v2), lọc theo văn bản / danh mục / chế độ quick.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Union
from pydantic import BaseModel, Field, field_validator


class ExpectedFigures(BaseModel):
    """Mức phạt và chế tài kỳ vọng trong đáp án đối chứng"""
    fine_vnd: Optional[List[int]] = Field(default=None, description="Khoảng tiền phạt [min, max] theo VNĐ")
    points: Optional[int] = Field(default=None, description="Số điểm GPLX bị trừ")
    suspension_months: Optional[List[int]] = Field(default=None, description="Khoảng thời gian tước GPLX [min, max] (tháng)")


class HistoryMessage(BaseModel):
    """Lịch sử hội thoại trước câu hỏi (cho câu hỏi đa lượt)"""
    role: str = Field(description="'user' hoặc 'assistant'")
    content: str = Field(description="Nội dung tin nhắn")


class QAItemV2(BaseModel):
    """Schema một câu hỏi kiểm thử trong bộ dữ liệu chuẩn V2"""
    id: str = Field(description="Định danh duy nhất, vd qa_001")
    category: str = Field(description="Phân loại chủ đề giao thông")
    question: str = Field(description="Nội dung câu hỏi của người dùng")
    ground_truth_answer: str = Field(description="Câu trả lời chuẩn căn cứ pháp lý")
    
    # Định danh tài liệu và chunk mục tiêu
    target_doc_id: Optional[str] = Field(default=None, description="Mã tài liệu pháp luật (vd 01_luat_36_2024_qh15)")
    target_parent_id: Optional[Union[str, List[str]]] = Field(default=None, description="Mã parent chunk trong semantic_parents.json")
    target_article_number: Optional[int] = Field(default=None, description="Số Điều (tương thích ngược với v1)")
    target_chapter: Optional[str] = Field(default=None, description="Tên chương")
    
    # Kỳ vọng E2E
    expected_citation: Optional[str] = Field(default=None, description="Chuỗi trích dẫn bắt buộc xuất hiện trong câu trả lời")
    expected_figures: Optional[ExpectedFigures] = Field(default=None, description="Con số chế tài kỳ vọng")
    expected_vehicles: Optional[List[str]] = Field(default=None, description="Phương tiện liên quan (o_to, xe_may, ...)")
    
    # Cờ câu hỏi đặc biệt
    is_out_of_scope: bool = Field(default=False, description="True nếu là câu hỏi lạc đề / ngoài phạm vi pháp luật giao thông")
    history: Optional[List[HistoryMessage]] = Field(default=None, description="Lịch sử đa lượt nếu có")

    @field_validator("id")
    @classmethod
    def validate_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id không được để trống")
        return v.strip()

    @field_validator("question")
    @classmethod
    def validate_question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("question không được để trống")
        return v.strip()


class BenchmarkDatasetV2(BaseModel):
    """Schema toàn bộ tập dữ liệu Benchmark"""
    dataset_name: str = Field(default="Traffic Law Benchmark v2")
    version: str = Field(default="2.0")
    description: Optional[str] = Field(default=None)
    total_questions: int = Field(default=0)
    questions: List[QAItemV2] = Field(default_factory=list)


def load_dataset(file_path: str) -> BenchmarkDatasetV2:
    """
    Nạp và kiểm chứng tệp testset JSON.
    Tự động chuẩn hóa tệp schema v1 (qa_testset.json) nếu nạp tệp cũ.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Không tìm thấy file dataset tại: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_questions = raw.get("questions", [])
    normalized_questions: List[QAItemV2] = []

    for q in raw_questions:
        # Nếu là bản v1 thiếu target_doc_id nhưng có target_article_number
        if "target_doc_id" not in q and "target_article_number" in q:
            target_art = q.get("target_article_number")
            doc_id = "01_luat_36_2024_qh15"
            # Dự đoán parent_id mẫu cho Luật 36: 01_luat_36_dieu_{art:02d}
            parent_id = f"01_luat_36_dieu_{target_art:02d}" if target_art is not None else None
            
            q_dict = dict(q)
            q_dict["target_doc_id"] = doc_id
            q_dict["target_parent_id"] = parent_id
            normalized_questions.append(QAItemV2(**q_dict))
        else:
            normalized_questions.append(QAItemV2(**q))

    dataset = BenchmarkDatasetV2(
        dataset_name=raw.get("dataset_name", "Traffic Law Benchmark v2"),
        version=raw.get("version", "2.0"),
        description=raw.get("description"),
        total_questions=len(normalized_questions),
        questions=normalized_questions
    )
    return dataset


def filter_dataset(
    dataset: BenchmarkDatasetV2,
    doc_id: Optional[str] = None,
    category: Optional[str] = None,
    quick_limit: Optional[int] = None,
    include_out_of_scope: bool = True
) -> List[QAItemV2]:
    """
    Lọc các câu hỏi theo tiêu chí để đánh giá linh hoạt.
    """
    items = dataset.questions

    if not include_out_of_scope:
        items = [q for q in items if not q.is_out_of_scope]

    if doc_id:
        norm_doc = doc_id.strip().lower()
        items = [q for q in items if q.target_doc_id and norm_doc in q.target_doc_id.lower()]

    if category:
        norm_cat = category.strip().lower()
        items = [q for q in items if q.category and norm_cat in q.category.lower()]

    if quick_limit is not None and quick_limit > 0:
        items = items[:quick_limit]

    return items


def save_dataset(dataset: BenchmarkDatasetV2, file_path: str) -> None:
    """Lưu tập dữ liệu ra file JSON có định dạng đẹp"""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(dataset.model_dump(), f, ensure_ascii=False, indent=2)
