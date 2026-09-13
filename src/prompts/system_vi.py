"""
Chỉ dẫn hệ thống cho Agent.

Persona và tri thức nền KHÔNG còn nằm trong mã nguồn. Trước đây hàm này trả về một chuỗi 7.000
ký tự mô tả 6 văn bản pháp luật giao thông, các hạng bằng lái, mức tốc độ trong khu dân cư,
quy tắc trích dẫn Nghị định 168 — toàn bộ là tri thức của đúng một miền, nướng cứng vào engine.

Giờ nó đọc từ `domains/<id>/prompts/system.md` của Domain Pack đang hoạt động, và engine chỉ
nối thêm phần chỉ dẫn CHUNG cho mọi miền: cách đọc tín hiệu chất lượng truy xuất.
"""

from src.domain.registry import get_active_domain

# Chỉ dẫn thuộc về ENGINE, không thuộc miền nào: mọi miền đều dùng chung tầng truy xuất có
# tín hiệu độ tin cậy và phạm vi, nên cách hành xử với hai tín hiệu đó cũng chung.
RETRIEVAL_SIGNAL_GUIDE = (
    "ĐỌC TÍN HIỆU CHẤT LƯỢNG TRA CỨU (BẮT BUỘC):\n"
    "Mỗi kết quả tra cứu ngữ nghĩa có tối đa 2 dòng tín hiệu ở đầu. Dùng chúng để quyết định bước tiếp theo:\n"
    "1. `[ĐỘ TIN CẬY TRUY XUẤT: ...]` cho biết trong số ứng viên lấy về có kết quả nào nổi bật hẳn không.\n"
    "   - MẠNH: nhóm đầu tách bạch rõ, dùng được ngay.\n"
    "   - TRUNG BÌNH / YẾU: KHÔNG có nghĩa là câu hỏi sai, chỉ nói các ứng viên ngang điểm nhau. "
    "Hãy tự đọc nội dung lấy về và đánh giá xem có đúng là căn cứ cho câu hỏi không; nếu chưa "
    "đúng thì tra lại bằng thuật ngữ chuyên ngành khác, hoặc thu hẹp phạm vi tài liệu.\n"
    "2. `[PHẠM VI: ...]` cảnh báo khi điểm khớp tốt nhất thấp hơn hẳn mức mà kho tài liệu thường "
    "đạt được. Khi thấy cảnh báo NẰM NGOÀI:\n"
    "   - Đọc kỹ nội dung lấy về. Nếu chúng thật sự không trả lời câu hỏi, hãy NÓI THẲNG là kho "
    "tài liệu không có quy định cho việc này.\n"
    "   - TUYỆT ĐỐI không ghép các mục không liên quan lại để tỏ ra có câu trả lời, và không lấy "
    "số liệu từ trí nhớ.\n"
    "   - Nếu câu hỏi vẫn thuộc lĩnh vực nhưng dùng từ ngữ đời thường, hãy thử tra lại bằng thuật "
    "ngữ chuyên ngành trước khi kết luận.\n"
    "Nguyên tắc chung: căn cứ để bạn kết luận là NỘI DUNG mục tài liệu lấy về có trả lời được câu "
    "hỏi hay không, chứ không phải con số điểm."
)


def get_system_prompt() -> str:
    """Chỉ dẫn hệ thống đầy đủ: persona của miền + chỉ dẫn đọc tín hiệu của engine."""
    return f"{get_active_domain().system_prompt}\n\n{RETRIEVAL_SIGNAL_GUIDE}"


# Tên cũ, giữ cho mã đã dùng.
get_system_prompt_vi = get_system_prompt
