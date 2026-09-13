"""
HỢP ĐỒNG GIỮA CÔNG CỤ TRA CỨU VÀ LỚP KIỂM CHỨNG

Các nhãn và chỉ dẫn dùng chung cho mọi công cụ của Agent. Tách riêng khỏi từng module tra cứu
vì lớp kiểm chứng (src/answer_guard.py) phải nhận diện được chúng, mà không nên phải nạp theo
toàn bộ dữ liệu luật/nghị định và numpy chỉ để đọc vài hằng số.
"""

# Nhãn tách phần chỉ dẫn dành riêng cho Agent khỏi phần dữ liệu pháp lý.
# Thiếu nhãn này mô hình hay chép nguyên văn lời hướng dẫn (kể cả điểm số nội bộ) ra câu trả lời.
AGENT_ONLY_TAG = "[CHỈ DẪN NỘI BỘ CHO AGENT — KHÔNG ĐƯỢC NHẮC LẠI VỚI NGƯỜI DÙNG]"

# Tiêu đề chuẩn của các nhánh "không có dữ liệu". Lớp kiểm chứng dựa vào đúng các chuỗi này
# để biết hệ thống thực sự không tra được gì, nên không được đổi tự do.
NO_PENALTY_DATA_HEADER = "=== KHÔNG CÓ DỮ LIỆU MỨC PHẠT CHO:"
NO_ARTICLE_MATCH_HEADER = "=== KHÔNG TÌM THẤY ĐIỀU KHOẢN LIÊN QUAN TỚI:"
NO_KEYWORD_MATCH_HEADER = "=== KHÔNG TÌM THẤY ĐIỀU LUẬT KHỚP TỪ KHÓA:"
NO_DATA_HEADERS = (NO_PENALTY_DATA_HEADER, NO_ARTICLE_MATCH_HEADER, NO_KEYWORD_MATCH_HEADER)

# Tên hai văn bản có vai trò khác nhau — nguồn gốc của mọi nhầm lẫn "phạt X đồng theo Luật".
LAW_NAME = "Luật 36/2024/QH15"
ROAD_LAW_NAME = "Luật 35/2024/QH15"

# Cụm từ nhận diện trích dẫn thuộc Luật Đường bộ. Hai luật cùng đánh số Điều từ 1 nên nếu
# không phân biệt, một trích dẫn Luật 35 hợp lệ sẽ bị đem đối chiếu với cấu trúc Luật 36.
ROAD_LAW_MARKERS = ("Luật 35", "35/2024", "Luật Đường bộ")
PENALTY_DECREE_NAME = "Nghị định 168/2024/NĐ-CP"

# Nhắc lại quy tắc số liệu & trích dẫn ngay trong kết quả công cụ. Model nhỏ bám vào ngữ cảnh
# gần nhất mạnh hơn nhiều so với system prompt ở đầu hội thoại.
FIGURE_LOCK_NOTE = (
    f"{AGENT_ONLY_TAG}\n"
    "1. Chỉ được dùng đúng những con số xuất hiện nguyên văn ở trên (tiền phạt, số điểm bị trừ, "
    "thời hạn tước GPLX). KHÔNG quy đổi, KHÔNG làm tròn, KHÔNG bổ sung số liệu từ trí nhớ.\n"
    f"2. QUY TẮC TRÍCH DẪN: mức tiền phạt và số điểm bị trừ chỉ có trong {PENALTY_DECREE_NAME}. "
    f"{LAW_NAME} KHÔNG quy định số tiền phạt — tuyệt đối không ghi Điều/Khoản của Luật làm căn cứ "
    "cho số tiền.\n"
    "3. Phải chép nguyên văn trích dẫn 'Điểm ... Khoản ... Điều ... Nghị định 168/2024/NĐ-CP' như "
    "ghi ở trên. Không tự đổi số Khoản, số Điểm.\n"
    "4. PHÂN TÍCH ĐA PHƯƠNG TIỆN: Nếu kết quả trên có hành vi của nhiều loại phương tiện (Ô tô, Xe máy...) "
    "hoặc câu hỏi không nêu rõ loại xe, bạn PHẢI phân tích đầy đủ theo từng loại xe (ví dụ: đối với Ô tô thì..., "
    "đối với Xe máy thì...). Chú ý bản chất pháp lý (ví dụ: xe máy bị cấm hoàn toàn vào đường cao tốc nên đi vào bất kỳ "
    "làn nào của cao tốc cũng bị xử phạt theo lỗi 'Đi vào đường cao tốc').\n"
    "5. Chỉ nói 'chưa có dữ liệu' khi kết quả tra cứu hoàn toàn không có hành vi hoặc phương tiện nào tương ứng."
)
