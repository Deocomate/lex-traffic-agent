"""
Script tự động làm giàu dữ liệu RAG (Dataset Augmentation for Legal RAG)
Tự động bổ sung các tình huống thực tế đời thường (Everyday Real-world Scenarios) 
cho các Điều luật để hệ thống Semantic Search bao phủ 100% ngôn ngữ đời thường của người dân.
"""

import os
import sys
import json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


# Bộ ngân hàng tình huống đời thường ánh xạ vào từng Điều luật
REAL_WORLD_SITUATIONS = {
    9: [
        "Uống 1 lon bia, 1 chén rượu, nhậu nhẹt say xỉn có được chạy xe máy hoặc lái ô tô không?",
        "Ăn đồ ăn có cồn hoặc uống siro ho thổi nồng độ cồn bị xử lý ra sao?",
        "Sử dụng ma túy, hút cỏ, bóng cười, chất kích thích khi tham gia giao thông",
        "Bấm còi hơi, bấm còi inh ỏi trong đêm khuya từ 22h đêm đến 5h sáng",
        "Đua xe trái phép, lạng lách, đánh võng, bốc đầu xe trên đường",
        "Gây tai nạn giao thông rồi bỏ trốn khỏi hiện trường",
        "Đục sửa số khung số máy, che biển số xe, bẻ cong biển số xe",
        "Rải đinh, ném đất đá vào người và phương tiện đang chạy trên đường"
    ],
    10: [
        "Trẻ em con nít 7 tuổi có được ngồi ghế phụ phía trước cạnh tài xế không?",
        "Quy định về ghế trẻ em và thiết bị an toàn cho trẻ em dưới 10 tuổi cao dưới 1m35 trên ô tô",
        "Người ngồi hàng ghế sau trên xe ô tô con có bắt buộc phải thắt dây an toàn không?",
        "Quy tắc chung khi đi đường, đi bên phải theo chiều đi của mình"
    ],
    11: [
        "Vượt đèn đỏ, vượt đèn vàng bị xử lý thế nào?",
        "Ý nghĩa của đèn vàng nhấp nháy tại các ngã tư lúc nửa đêm",
        "Khi đèn vàng vừa bật sáng xe đã đi qua vạch dừng thì có được đi tiếp không?"
    ],
    14: [
        "Khi nào được vượt phải xe khác?",
        "Quy tắc xi nhan, bấm còi xin vượt xe tải phía trước an toàn",
        "Cấm vượt xe ở những đoạn đường quanh co, khuất tầm nhìn, đường cong"
    ],
    15: [
        "Rẽ trái, rẽ phải, quay đầu xe có phải bật xi nhan trước bao nhiêu mét?",
        "Nhường đường cho người đi bộ khi chuyển hướng xe tại ngã tư"
    ],
    16: [
        "Lùi xe ô tô trên đường cao tốc, trong hầm đường bộ",
        "Không được lùi xe ở nơi đường giao nhau ngã ba ngã tư"
    ],
    18: [
        "Dừng đỗ xe trên vỉa hè hè phố, đỗ xe trước cửa nhà dân có được không?",
        "Khoảng cách dừng đỗ xe cách lề đường bao nhiêu mét?",
        "Đỗ xe ngược chiều lưu thông, đỗ xe che khuất biển báo"
    ],
    20: [
        "Mấy giờ bắt buộc phải bật đèn pha xe máy ô tô?",
        "Bật đèn chiếu sáng khi trời mưa to, sương mù dày đặc ban ngày",
        "Bật đèn chiếu xa (pha) trong đô thị có bị cấm không?"
    ],
    21: [
        "Bấm còi trong thành phố ban đêm từ 10 giờ đêm đến 5 giờ sáng có bị phạt không?",
        "Lắp còi hơi xe tải vào xe con, xe máy có được không?"
    ],
    25: [
        "Chạy xe trên đường cao tốc bị nổ lốp, chết máy thì phải tấp vào đâu?",
        "Đặt biển cảnh báo nguy hiểm sau xe bao nhiêu mét khi gặp sự cố trên cao tốc?",
        "Chạy xe vào làn dừng khẩn cấp trên cao tốc khi không có sự cố"
    ],
    27: [
        "Xe cứu thương chở bệnh nhân cấp cứu có được vượt đèn đỏ không?",
        "Thứ tự nhường đường khi gặp đoàn xe cảnh sát dẫn đường, xe cứu hỏa chữa cháy"
    ],
    30: [
        "Người đi bộ qua đường không đúng vạch kẻ đường",
        "Người đi bộ đi vào đường cao tốc"
    ],
    31: [
        "Chở 3 người trên xe máy (kẹp 3) khi nào thì được phép?",
        "Chở người bệnh đi cấp cứu, chở trẻ em dưới 12 tuổi trên xe máy",
        "Đi xe máy điện, xe đạp điện có bắt buộc phải đội mũ bảo hiểm không?"
    ],
    32: [
        "Đội mũ bảo hiểm không cài quai hoặc cài quai lỏng lẻo có bị phạt không?"
    ],
    34: [
        "Xe máy 50cc là xe gì? Định nghĩa xe gắn máy dưới 50 phân khối",
        "Xe máy điện và xe đạp điện khác nhau như thế nào?"
    ],
    37: [
        "Bán xe có được giữ lại biển số định danh không?",
        "Thủ tục thu hồi biển số định danh khi sang tên đổi chủ xe"
    ],
    38: [
        "Đấu giá biển số xe ô tô đẹp, quyền của người trúng đấu giá biển số",
        "Có được chuyển nhượng biển số trúng đấu giá kèm theo xe không?"
    ],
    42: [
        "Xe ô tô mới mua có được miễn đăng kiểm lần đầu không?",
        "Hạn kiểm định an toàn kỹ thuật và bảo vệ môi trường của xe cơ giới"
    ],
    57: [
        "Bằng lái xe máy A1 chạy được xe bao nhiêu phân khối (cc)?",
        "Bằng A lái xe phân khối lớn PKL trên 175cc hay 125cc?",
        "Bằng lái xe B lái được ô tô mấy chỗ ngồi?"
    ],
    58: [
        "Mỗi bằng lái xe có bao nhiêu điểm? Bị trừ hết 12 điểm thì làm thế nào?",
        "Sau bao lâu không vi phạm thì được phục hồi đủ 12 điểm bằng lái?"
    ],
    59: [
        "Học sinh cấp 3 đủ 16 tuổi được chạy xe máy nào?",
        "Bao nhiêu tuổi thì được thi bằng lái xe máy 110cc, 125cc, 150cc?",
        "Bao nhiêu tuổi thì được học lái xe ô tô B1, B2?"
    ],
    64: [
        "Tài xế lái xe khách, xe tải được lái tối đa mấy tiếng một ngày?",
        "Lái xe liên tục không được quá mấy giờ?"
    ],
    66: [
        "Cảnh sát giao thông (CSGT) được dừng xe trong những trường hợp nào?",
        "CSGT có được dừng xe khi không có chuyên đề tuần tra không?"
    ],
    81: [
        "Khi xảy ra tai nạn giao thông, tài xế phải làm gì đầu tiên?",
        "Người gây tai nạn bỏ trốn khỏi hiện trường bị xử lý ra sao?"
    ],
    89: [
        "Luật giao thông mới năm 2024 khi nào chính thức có hiệu lực?",
        "Bằng lái xe cũ cấp trước năm 2025 có phải đổi sang bằng mới không?"
    ]
}

def main():
    jsonl_path = os.path.join(base_dir, "data", "processed", "rag_chunks.jsonl")
    if not os.path.exists(jsonl_path):
        print(f"Không tìm thấy {jsonl_path}")
        return
        
    with open(jsonl_path, "r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
        
    enriched_chunks = []
    enriched_count = 0
    
    for chunk in chunks:
        art_num = chunk["metadata"]["article_number"]
        situations = REAL_WORLD_SITUATIONS.get(art_num, [])
        
        # Thêm situations vào metadata
        chunk["metadata"]["real_world_scenarios"] = situations
        
        if situations:
            enriched_count += 1
            # Thêm phần tình huống thực tế vào nội dung Document để mô hình Embedding & Search bắt trọn
            situations_text = "\n[CÁC TÌNH HUỐNG THỰC TẾ ĐỜI THƯỜNG LIÊN QUAN]:\n" + "\n".join([f"- {s}" for s in situations])
            
            # Cập nhật page_content mở rộng
            chunk["page_content_enriched"] = chunk["page_content"] + "\n" + situations_text
        else:
            chunk["page_content_enriched"] = chunk["page_content"]
            
        enriched_chunks.append(chunk)
        
    # Ghi lại file enriched jsonl
    enriched_path = os.path.join(base_dir, "data", "processed", "rag_chunks_enriched.jsonl")
    with open(enriched_path, "w", encoding="utf-8") as f:
        for c in enriched_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
            
    print(f"-> Đã làm giàu thành công {enriched_count} Điều luật với ngân hàng tình huống đời thường!")
    print(f"-> Đã lưu tại: {enriched_path}")

if __name__ == "__main__":
    main()
