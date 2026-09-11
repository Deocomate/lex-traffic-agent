"""
Script tự động trích xuất, làm sạch và cấu trúc hóa toàn văn Luật Trật tự, an toàn giao thông đường bộ 2024
(Luật số 36/2024/QH15 - 9 Chương, 89 Điều)
Xuất ra:
1. data/processed/law_36_2024_structured.json (Cấu trúc phân cấp Tree)
2. data/processed/rag_chunks.jsonl (Chunks tối ưu cho Vector DB kèm Breadcrumb Context)
3. data/processed/markdown/ (Từng file Markdown theo Chương và toàn văn sạch)
4. data/benchmark/qa_testset.json (Bộ 35 câu hỏi kiểm thử chuẩn kèm Điều luật đối sánh)
"""

import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CHAPTERS_INFO = [
    ("Chương I", "NHỮNG QUY ĐỊNH CHUNG", "Nhung_quy_dinh_chung", 1, 9),
    ("Chương II", "QUY TẮC GIAO THÔNG ĐƯỜNG BỘ", "Quy_tac_giao_thong_duong_bo", 10, 33),
    ("Chương III", "PHƯƠNG TIỆN THAM GIA GIAO THÔNG ĐƯỜNG BỘ", "Phuong_tien_tham_gia_giao_thong", 34, 55),
    ("Chương IV", "NGƯỜI ĐIỀU KHIỂN PHƯƠNG TIỆN THAM GIA GIAO THÔNG ĐƯỜNG BỘ", "Nguoi_dieu_khien_phuong_tien", 56, 64),
    ("Chương V", "TUẦN TRA, KIỂM SOÁT VỀ TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ", "Tuan_tra_kiem_soat", 65, 73),
    ("Chương VI", "CHỈ HUY, ĐIỀU KHIỂN GIAO THÔNG ĐƯỜNG BỘ BẢO ĐẢM TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ", "Chi_huy_dieu_khien_giao_thong", 74, 79),
    ("Chương VII", "GIẢI QUYẾT TAI NẠN GIAO THÔNG ĐƯỜNG BỘ", "Giai_quyet_tai_nan_giao_thong", 80, 85),
    ("Chương VIII", "QUẢN LÝ NHÀ NƯỚC VỀ TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ", "Quan_ly_nha_nuoc", 86, 87),
    ("Chương IX", "ĐIỀU KHOẢN THI HÀNH", "Dieu_khoan_thi_hanh", 88, 89),
]

def fetch_chapter_html(chapter_name: str, max_retries: int = 5) -> str:
    """Tải nội dung HTML của từng chương từ nguồn công báo số hóa chính thức"""
    title = f"Luật Trật tự, an toàn giao thông đường bộ nước Cộng hòa xã hội chủ nghĩa Việt Nam 2024/{chapter_name}"
    url = f"https://vi.wikisource.org/w/api.php?action=parse&page={urllib.parse.quote(title)}&prop=text&format=json"
    headers = {'User-Agent': 'TrafficLawRAG/1.0 (Educational Project; contact@edu.vn)'}
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode('utf-8'))
                html = data.get('parse', {}).get('text', {}).get('*', '')
                return html
        except Exception as e:
            wait_time = (attempt + 1) * 2
            print(f"  [Lần thử {attempt+1}/{max_retries}] Lỗi tải {chapter_name}: {e}. Đang đợi {wait_time}s...")
            time.sleep(wait_time)
            
    raise RuntimeError(f"Không thể tải nội dung {chapter_name} sau {max_retries} lần thử")

def clean_extracted_text(html: str) -> str:
    """Loại bỏ các thẻ điều hướng, chuẩn hóa ký tự đặc biệt, số mũ và bảng biểu"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Xử lý thẻ sup (cm3 -> cm³, m2 -> m²)
    for sup in soup.find_all('sup'):
        sup_text = sup.get_text()
        if sup_text == '3':
            sup.replace_with('³')
        elif sup_text == '2':
            sup.replace_with('²')
        elif sup_text == 'o' or sup_text == '0':
            sup.replace_with('°')
        else:
            sup.replace_with(f"^{sup_text}")
            
    for sub in soup.find_all('sub'):
        sub.replace_with(f"_{sub.get_text()}")
        
    for tag in soup.find_all(['table', 'div'], class_=['headertemplate', 'navigation', 'noprint', 'mw-jump-link', 'mw-editsection']):
        tag.decompose()
        
    text = soup.get_text(separator='\n')
    
    # Làm sạch dòng và khoảng trắng
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []
    
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            continue
        if re.search(r'Luật Trật tự, an toàn giao thông đường bộ nước Cộng hòa', line):
            continue
        if re.search(r'←Chương|Chương.*→', line):
            continue
        # Chuẩn hóa lỗi dính dòng cm\n3
        line = re.sub(r'cm\s*3', 'cm³', line)
        line = re.sub(r'm\s*2', 'm²', line)
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def parse_articles_from_text(chapter_text: str, ch_start: int, ch_end: int):
    """Tách văn bản chương thành danh sách các Điều và Khoản"""
    articles = []
    pattern = re.compile(r'(?:^|\n)(Điều\s+(\d+)\.\s+([^\n\r]+))', re.MULTILINE)
    matches = list(pattern.finditer(chapter_text))
    
    for i, match in enumerate(matches):
        article_num = int(match.group(2))
        article_title = match.group(3).strip()
        
        start_pos = match.end()
        end_pos = matches[i + 1].start() if (i + 1) < len(matches) else len(chapter_text)
        
        body = chapter_text[start_pos:end_pos].strip()
        
        # Tách các khoản (1. ..., 2. ...)
        clauses = []
        clause_pattern = re.compile(r'(?:^|\n)((\d+)\.\s+([^\n\r]+(?:\n(?!\d+\.\s+)[^\n\r]+)*))')
        clause_matches = list(clause_pattern.finditer(body))
        
        if clause_matches:
            for cm in clause_matches:
                c_num = int(cm.group(2))
                c_content = cm.group(1).strip()
                clauses.append({
                    "clause_number": c_num,
                    "content": c_content
                })
        else:
            clauses.append({
                "clause_number": 1,
                "content": body
            })
            
        articles.append({
            "article_number": article_num,
            "article_title": article_title,
            "full_header": f"Điều {article_num}. {article_title}",
            "body": body,
            "clauses": clauses
        })
        
    return articles

def generate_curated_qa_benchmark():
    """Tạo bộ dữ liệu 35 câu hỏi thực tế đa dạng các tình huống làm benchmark RAG"""
    return [
        {
            "id": "qa_001",
            "category": "Hiệu lực văn bản",
            "question": "Luật Trật tự, an toàn giao thông đường bộ số 36/2024/QH15 có hiệu lực thi hành từ ngày nào và có điều khoản nào có hiệu lực muộn hơn không?",
            "ground_truth_answer": "Luật có hiệu lực thi hành từ ngày 01/01/2025 (Khoản 1 Điều 89). Riêng quy định tại khoản 3 Điều 10 (về thiết bị an toàn và vị trí ngồi cho trẻ em trên ô tô) có hiệu lực từ ngày 01/01/2026.",
            "target_article_number": 89,
            "target_chapter": "Chương IX"
        },
        {
            "id": "qa_002",
            "category": "Hành vi bị nghiêm cấm",
            "question": "Quy định về nồng độ cồn đối với người điều khiển phương tiện tham gia giao thông trong Luật mới 2024 như thế nào?",
            "ground_truth_answer": "Khoản 2 Điều 9 nghiêm cấm tuyệt đối hành vi điều khiển phương tiện tham gia giao thông đường bộ mà trong máu hoặc hơi thở có nồng độ cồn.",
            "target_article_number": 9,
            "target_chapter": "Chương I"
        },
        {
            "id": "qa_003",
            "category": "Hành vi bị nghiêm cấm",
            "question": "Hành vi bấm còi, rú ga liên tục trong đô thị và khu đông dân cư bị xử lý như thế nào theo Luật 2024?",
            "ground_truth_answer": "Khoản 8 Điều 9 nghiêm cấm bấm còi liên tục; bấm còi hơi; bấm còi trong thời gian từ 22 giờ ngày hôm trước đến 05 giờ ngày hôm sau trong đô thị, khu đông dân cư (trừ các xe ưu tiên đang đi làm nhiệm vụ).",
            "target_article_number": 9,
            "target_chapter": "Chương I"
        },
        {
            "id": "qa_004",
            "category": "Quy tắc vượt xe",
            "question": "Người lái xe chỉ được phép vượt xe khác khi đáp ứng những điều kiện an toàn nào?",
            "ground_truth_answer": "Theo Điều 14, xe xin vượt phải báo hiệu bằng đèn hoặc còi; chỉ được vượt khi không có chướng ngại vật phía trước, không có xe chạy ngược chiều trong đoạn đường định vượt, xe chạy trước không có tín hiệu vượt xe khác và đã tránh về bên phải. Phải vượt về bên trái (trừ các trường hợp được phép vượt phải).",
            "target_article_number": 14,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_005",
            "category": "Chuyển hướng xe",
            "question": "Khi muốn chuyển hướng (rẽ trái, rẽ phải), người lái xe phải thực hiện những thao tác gì?",
            "ground_truth_answer": "Theo Điều 15, người lái xe phải quan sát, giảm tốc độ và bật tín hiệu báo hướng rẽ trước khi chuyển hướng; phải nhường đường cho người đi bộ, người đi xe lăn, xe thô sơ và xe đi ngược chiều.",
            "target_article_number": 15,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_006",
            "category": "Lùi xe",
            "question": "Luật giao thông cấm lùi xe ở những vị trí và cung đường nào?",
            "ground_truth_answer": "Theo Điều 17, không được lùi xe ở khu vực cấm dừng, cấm đỗ, nơi đường giao nhau, đường giao nhau cùng mức với đường sắt, nơi tầm nhìn bị che khuất, trong hầm đường bộ, trên đường cao tốc.",
            "target_article_number": 17,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_007",
            "category": "Đèn chiếu sáng",
            "question": "Khung giờ bắt buộc bật đèn chiếu sáng phía trước và các trường hợp thời tiết đặc biệt?",
            "ground_truth_answer": "Theo Điều 20, bắt buộc bật đèn chiếu sáng phía trước từ 18 giờ ngày hôm trước đến 06 giờ ngày hôm sau hoặc khi có sương mù, khói, bụi, trời mưa, thời tiết xấu làm hạn chế tầm nhìn.",
            "target_article_number": 20,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_008",
            "category": "Tín hiệu đèn giao thông",
            "question": "Ý nghĩa hiệu lệnh của đèn tín hiệu giao thông (Xanh, Vàng, Đỏ) được quy định như thế nào?",
            "ground_truth_answer": "Theo Điều 11: Tín hiệu xanh là được đi; Tín hiệu đỏ là cấm đi; Tín hiệu vàng là phải dừng lại trước vạch dừng (nếu đã đi quá vạch dừng thì được đi tiếp). Tín hiệu vàng nhấp nháy là được đi nhưng phải giảm tốc độ và nhường đường.",
            "target_article_number": 11,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_009",
            "category": "Thứ tự xe ưu tiên",
            "question": "Thứ tự quyền ưu tiên của các loại xe khi cùng đến nơi giao nhau?",
            "ground_truth_answer": "Theo Điều 27: 1. Xe chữa cháy đi làm nhiệm vụ; 2. Xe quân sự, công an đi làm nhiệm vụ khẩn cấp; 3. Xe cứu thương đang cấp cứu; 4. Xe hộ đê, xe đi khắc phục sự cố thiên tai, dịch bệnh; 5. Đoàn xe có Cảnh sát giao thông dẫn đường.",
            "target_article_number": 27,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_010",
            "category": "Giao thông đường cao tốc",
            "question": "Xe gặp sự cố trên đường cao tốc phải xử lý dừng đỗ như thế nào để đảm bảo an toàn?",
            "ground_truth_answer": "Theo Điều 25, phải đưa xe ra khỏi phần đường xe chạy vào làn dừng khẩn cấp; trường hợp không thể di chuyển được, phải bật đèn khẩn cấp và đặt biển cảnh báo nguy hiểm phía sau xe tối thiểu 150 mét, đồng thời liên hệ cơ quan quản lý.",
            "target_article_number": 25,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_011",
            "category": "Độ tuổi lái xe",
            "question": "Người từ đủ 16 tuổi và từ đủ 18 tuổi được phép điều khiển những loại xe nào?",
            "ground_truth_answer": "Theo Điều 59: Người đủ 16 tuổi trở lên được lái xe gắn máy dưới 50 cm³ hoặc công suất điện không quá 4 kW. Người đủ 18 tuổi trở lên được lái xe mô tô hai bánh từ 50 cm³ trở lên, xe ô tô chở người đến 8 chỗ ngồi, ô tô tải dưới 3.500 kg.",
            "target_article_number": 59,
            "target_chapter": "Chương IV"
        },
        {
            "id": "qa_012",
            "category": "Phân hạng Giấy phép lái xe",
            "question": "Bằng lái xe máy hạng A1 theo Luật 2024 áp dụng cho xe có dung tích bao nhiêu?",
            "ground_truth_answer": "Theo Điểm a Khoản 1 Điều 57, Giấy phép lái xe hạng A1 cấp cho người lái xe mô tô hai bánh có dung tích xi-lanh đến 125 cm³ hoặc công suất động cơ điện đến 11 kW.",
            "target_article_number": 57,
            "target_chapter": "Chương IV"
        },
        {
            "id": "qa_013",
            "category": "Phân hạng Giấy phép lái xe",
            "question": "Bằng lái xe máy hạng A theo quy định mới cấp cho đối tượng xe nào?",
            "ground_truth_answer": "Theo Điểm b Khoản 1 Điều 57, Giấy phép lái xe hạng A cấp cho người lái xe mô tô hai bánh có dung tích xi-lanh trên 125 cm³ hoặc công suất động cơ điện trên 11 kW và các loại xe quy định cho GPLX hạng A1.",
            "target_article_number": 57,
            "target_chapter": "Chương IV"
        },
        {
            "id": "qa_014",
            "category": "Điểm Giấy phép lái xe",
            "question": "Cơ chế quản lý và phục hồi điểm của Giấy phép lái xe (12 điểm) hoạt động ra sao?",
            "ground_truth_answer": "Theo Điều 58, mỗi GPLX có 12 điểm. Khi vi phạm pháp luật sẽ bị trừ điểm. Nếu chưa bị trừ hết điểm và không bị trừ điểm trong thời hạn 12 tháng kể từ ngày bị trừ điểm gần nhất thì được phục hồi đủ 12 điểm. Nếu bị trừ hết 12 điểm thì phải tham gia kiểm tra kiến thức pháp luật.",
            "target_article_number": 58,
            "target_chapter": "Chương IV"
        },
        {
            "id": "qa_015",
            "category": "Quy định mũ bảo hiểm",
            "question": "Đối tượng nào bắt buộc phải đội mũ bảo hiểm khi tham gia giao thông?",
            "ground_truth_answer": "Theo Điều 31 và Điều 32, người lái xe và người ngồi trên xe mô tô hai bánh, ba bánh, xe gắn máy, xe đạp điện, xe máy điện bắt buộc phải đội mũ bảo hiểm và cài quai đúng quy cách.",
            "target_article_number": 31,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_016",
            "category": "Dây đai an toàn",
            "question": "Quy định về thắt dây an toàn trên xe ô tô áp dụng cho những vị trí ngồi nào?",
            "ground_truth_answer": "Theo Khoản 3 Điều 10, người lái xe và toàn bộ người ngồi trên xe ô tô phải thắt dây đai an toàn tại tất cả các vị trí có trang bị dây an toàn khi xe đang tham gia giao thông.",
            "target_article_number": 10,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_017",
            "category": "Bảo vệ trẻ em trên ô tô",
            "question": "Quy định bảo đảm an toàn cho trẻ em dưới 10 tuổi và dưới 1,35m khi đi trên ô tô?",
            "ground_truth_answer": "Theo Khoản 3 Điều 10, không được cho trẻ em dưới 10 tuổi và chiều cao dưới 1,35 mét ngồi cùng hàng ghế với người lái xe ô tô con (trừ xe chỉ có 1 hàng ghế); người lái xe phải sử dụng thiết bị an toàn phù hợp cho trẻ em.",
            "target_article_number": 10,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_018",
            "category": "Thời gian lái xe",
            "question": "Thời gian làm việc tối đa trong ngày và thời gian lái xe liên tục của tài xế ô tô?",
            "ground_truth_answer": "Theo Điều 64, tổng thời gian lái xe của người lái xe ô tô không quá 10 giờ trong 1 ngày và không quá 48 giờ trong 1 tuần; thời gian lái xe liên tục không quá 04 giờ (ban đêm từ 22h - 6h lái liên tục không quá 3 giờ đối với xe kinh doanh vận tải).",
            "target_article_number": 64,
            "target_chapter": "Chương IV"
        },
        {
            "id": "qa_019",
            "category": "Trường hợp dừng xe của CSGT",
            "question": "Cảnh sát giao thông được quyền dừng phương tiện để kiểm soát trong những trường hợp nào?",
            "ground_truth_answer": "Theo Điều 66, CSGT được dừng xe khi trực tiếp phát hiện hoặc thông qua phương tiện kỹ thuật ghi nhận hành vi vi phạm; khi thực hiện mệnh lệnh, kế hoạch tuần tra kiểm soát đã được phê duyệt; khi có văn bản đề nghị của cơ quan có thẩm quyền hoặc có tin báo tố giác tội phạm.",
            "target_article_number": 66,
            "target_chapter": "Chương V"
        },
        {
            "id": "qa_020",
            "category": "Trách nhiệm khi xảy ra tai nạn",
            "question": "Người lái xe liên quan trực tiếp đến vụ tai nạn giao thông phải làm gì ngay tại hiện trường?",
            "ground_truth_answer": "Theo Điều 81, phải dừng ngay phương tiện, giữ nguyên hiện trường, kịp thời cứu chữa người bị nạn, báo ngay cho cơ quan công an hoặc y tế gần nhất và ở lại hiện trường cho đến khi lực lượng chức năng đến.",
            "target_article_number": 81,
            "target_chapter": "Chương VII"
        },
        {
            "id": "qa_021",
            "category": "Người đi bộ",
            "question": "Người đi bộ phải tuân thủ những quy tắc nào khi qua đường?",
            "ground_truth_answer": "Theo Điều 30, người đi bộ phải qua đường ở nơi có vạch kẻ đường, cầu vượt, hầm dành cho người đi bộ và tuân thủ tín hiệu chỉ dẫn; nơi không có vạch kẻ đường thì phải quan sát an toàn và nhường đường cho phương tiện trước khi qua đường.",
            "target_article_number": 30,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_022",
            "category": "Biển số xe định danh",
            "question": "Khái niệm và nguyên tắc quản lý biển số xe định danh theo Luật 2024?",
            "ground_truth_answer": "Theo Điều 37 và Điều 38, biển số xe được cấp và quản lý theo mã định danh của chủ xe. Khi chuyển quyền sở hữu xe, chủ xe phải giữ lại biển số và nộp lại chứng nhận đăng ký, biển số cho cơ quan đăng ký để cấp lại khi đăng ký xe khác.",
            "target_article_number": 37,
            "target_chapter": "Chương III"
        },
        {
            "id": "qa_023",
            "category": "Đấu giá biển số xe",
            "question": "Các loại biển số xe nào được đưa ra đấu giá và quyền của người trúng đấu giá?",
            "ground_truth_answer": "Theo Điều 38, biển số xe ô tô được đưa ra đấu giá công khai. Người trúng đấu giá được cấp văn bản xác nhận, được đăng ký biển số cho xe thuộc sở hữu của mình và được giữ lại biển số khi chuyển nhượng, cho tặng xe.",
            "target_article_number": 38,
            "target_chapter": "Chương III"
        },
        {
            "id": "qa_024",
            "category": "Nhường đường tại nơi giao nhau",
            "question": "Quy tắc nhường đường tại nơi đường giao nhau không có vòng xuyến và có vòng xuyến?",
            "ground_truth_answer": "Theo Điều 18: Tại nơi giao nhau không có báo hiệu đi theo vòng xuyến, phải nhường đường cho xe đi đến từ bên phải; tại nơi giao nhau có báo hiệu đi theo vòng xuyến, phải nhường đường cho xe đi bên trái.",
            "target_article_number": 18,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_025",
            "category": "Khoảng cách an toàn giữa các xe",
            "question": "Người lái xe phải duy trì khoảng cách an toàn với xe chạy liền trước như thế nào?",
            "ground_truth_answer": "Theo Điều 13, người lái xe phải giữ khoảng cách an toàn phù hợp với xe chạy liền trước của mình; khi có biển báo khoảng cách an toàn tối thiểu giữa hai xe thì phải giữ khoảng cách không nhỏ hơn trị số ghi trên biển báo.",
            "target_article_number": 13,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_026",
            "category": "Dừng xe và Đỗ xe",
            "question": "Phân biệt khái niệm Dừng xe và Đỗ xe theo Luật 2024?",
            "ground_truth_answer": "Theo Điều 16: Dừng xe là trạng thái đứng yên tạm thời của phương tiện trong khoảng thời gian cần thiết để cho người lên, xuống hoặc xếp dỡ hàng hóa; Đỗ xe là trạng thái đứng yên của phương tiện không giới hạn thời gian.",
            "target_article_number": 16,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_027",
            "category": "Kéo xe và Chở người trên xe",
            "question": "Những điều kiện cấm khi kéo xe khác và xe chở hàng hóa cồng kềnh?",
            "ground_truth_answer": "Theo Điều 29, xe kéo xe phải có thanh nối cứng nếu hệ thống hãm của xe bị kéo không còn hiệu lực; cấm kéo rơ-moóc hoặc xe khác khi xe đang kéo một xe khác; không được kéo xe chở người.",
            "target_article_number": 29,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_028",
            "category": "Xe máy chuyên dùng",
            "question": "Điều kiện để xe máy chuyên dùng được phép tham gia giao thông đường bộ?",
            "ground_truth_answer": "Theo Điều 40 và Điều 60, xe máy chuyên dùng phải bảo đảm các quy định về an toàn kỹ thuật, bảo vệ môi trường, có đăng ký và biển số; người điều khiển phải có bằng hoặc chứng chỉ điều khiển phù hợp và chứng chỉ bồi dưỡng kiến thức pháp luật giao thông.",
            "target_article_number": 40,
            "target_chapter": "Chương III"
        },
        {
            "id": "qa_029",
            "category": "Kiểm định phương tiện",
            "question": "Quy định về việc kiểm định an toàn kỹ thuật và bảo vệ môi trường đối với xe cơ giới?",
            "ground_truth_answer": "Theo Điều 42, xe cơ giới tham gia giao thông đường bộ phải được kiểm định và cấp Giấy chứng nhận kiểm định an toàn kỹ thuật và bảo vệ môi trường định kỳ (trừ các trường hợp xe mới được miễn kiểm định lần đầu theo quy định).",
            "target_article_number": 42,
            "target_chapter": "Chương III"
        },
        {
            "id": "qa_030",
            "category": "Giao thông trong hầm đường bộ",
            "question": "Các quy tắc bắt buộc khi điều khiển phương tiện lưu thông trong hầm đường bộ?",
            "ground_truth_answer": "Theo Điều 24, xe cơ giới phải bật đèn chiếu sáng gần; xe thô sơ phải bật đèn hoặc có vật phát sáng báo hiệu; không được quay đầu xe, lùi xe; chỉ được dừng, đỗ xe ở nơi quy định.",
            "target_article_number": 24,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_031",
            "category": "Điều kiện sức khỏe lái xe",
            "question": "Quy định về khám sức khỏe định kỳ và quản lý dữ liệu sức khỏe của người lái xe?",
            "ground_truth_answer": "Theo Điều 61, người lái xe phải có đủ điều kiện sức khỏe phù hợp với từng hạng GPLX; việc khám sức khỏe định kỳ đối với người lái xe kinh doanh vận tải được kết nối liên thông dữ liệu với Cơ sở dữ liệu về trật tự an toàn giao thông.",
            "target_article_number": 61,
            "target_chapter": "Chương IV"
        },
        {
            "id": "qa_032",
            "category": "Cơ sở dữ liệu trật tự an toàn giao thông",
            "question": "Cơ sở dữ liệu về trật tự, an toàn giao thông đường bộ bao gồm những hệ thống thông tin nào?",
            "ground_truth_answer": "Theo Điều 7, cơ sở dữ liệu bao gồm: dữ liệu về phương tiện, dữ liệu về giấy phép lái xe, dữ liệu về xử lý vi phạm hành chính, dữ liệu về tai nạn giao thông, dữ liệu giám sát hành trình và dữ liệu bảo hiểm bắt buộc.",
            "target_article_number": 7,
            "target_chapter": "Chương I"
        },
        {
            "id": "qa_033",
            "category": "Sử dụng còi và đèn tín hiệu",
            "question": "Các trường hợp bị cấm sử dụng còi xe theo quy định của Luật?",
            "ground_truth_answer": "Theo Điều 21, cấm bấm còi trong thời gian từ 22 giờ ngày hôm trước đến 05 giờ ngày hôm sau trong đô thị và khu đông dân cư; cấm sử dụng còi hơi, còi có âm lượng vượt quy chuẩn kỹ thuật trong đô thị (trừ xe ưu tiên).",
            "target_article_number": 21,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_034",
            "category": "Quy định chở người trên xe máy",
            "question": "Người lái xe mô tô hai bánh, xe gắn máy chỉ được chở tối đa bao nhiêu người và các trường hợp ngoại lệ?",
            "ground_truth_answer": "Theo Điều 31, chỉ được chở 01 người; trừ các trường hợp được chở tối đa 02 người gồm: chở người bệnh đi cấp cứu; áp giải người có hành vi vi phạm pháp luật; chở trẻ em dưới 12 tuổi; chở người già yếu hoặc người khuyết tật.",
            "target_article_number": 31,
            "target_chapter": "Chương II"
        },
        {
            "id": "qa_035",
            "category": "Trách nhiệm của cơ quan, tổ chức",
            "question": "Trách nhiệm của nhà trường và cơ sở giáo dục trong việc giáo dục pháp luật an toàn giao thông?",
            "ground_truth_answer": "Theo Điều 6, cơ sở giáo dục có trách nhiệm đưa nội dung giáo dục kiến thức pháp luật và kỹ năng tham gia giao thông an toàn vào chương trình giảng dạy, phối hợp với gia đình quản lý học sinh tuân thủ quy định giao thông.",
            "target_article_number": 6,
            "target_chapter": "Chương I"
        }
    ]

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    processed_dir = os.path.join(base_dir, "data", "processed")
    markdown_dir = os.path.join(processed_dir, "markdown")
    benchmark_dir = os.path.join(base_dir, "data", "benchmark")
    
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(markdown_dir, exist_ok=True)
    os.makedirs(benchmark_dir, exist_ok=True)
    
    print("==================================================================")
    print(" BẮT ĐẦU PIPELINE XỬ LÝ & CẤU TRÚC HÓA LUẬT 36/2024/QH15 CHO RAG")
    print("==================================================================")
    
    law_structured = {
        "law_id": "36/2024/QH15",
        "law_name": "Luật Trật tự, an toàn giao thông đường bộ",
        "issuing_authority": "Quốc hội Nước CHXHCN Việt Nam",
        "date_issued": "2024-06-27",
        "date_effective": "2025-01-01",
        "total_chapters": 9,
        "total_articles": 89,
        "chapters": []
    }
    
    rag_chunks = []
    full_markdown_content = ["# Luật Trật tự, an toàn giao thông đường bộ 2024 (Số 36/2024/QH15)\n\n"]
    total_parsed_articles = 0
    
    for ch_idx, (ch_roman, ch_title, ch_slug, start_dieu, end_dieu) in enumerate(CHAPTERS_INFO, 1):
        print(f"\n[Chương {ch_idx}/9] Đang xử lý: {ch_roman} - {ch_title} (Điều {start_dieu} đến {end_dieu})...")
        
        raw_html = fetch_chapter_html(ch_roman)
        clean_text = clean_extracted_text(raw_html)
        articles = parse_articles_from_text(clean_text, start_dieu, end_dieu)
        print(f"  -> Trích xuất thành công {len(articles)}/{end_dieu - start_dieu + 1} Điều luật.")
        
        chapter_obj = {
            "chapter_id": ch_idx,
            "chapter_roman": ch_roman,
            "chapter_title": ch_title,
            "article_range": f"Điều {start_dieu} - Điều {end_dieu}",
            "articles": []
        }
        
        ch_md_filename = f"Chuong_{ch_idx:02d}_{ch_slug}.md"
        ch_md_path = os.path.join(markdown_dir, ch_md_filename)
        ch_md_lines = [f"# {ch_roman}: {ch_title}\n\n"]
        full_markdown_content.append(f"## {ch_roman}: {ch_title}\n\n")
        
        for art in articles:
            total_parsed_articles += 1
            art_num = art["article_number"]
            art_title = art["article_title"]
            body_text = art["body"]
            
            chapter_obj["articles"].append({
                "article_number": art_num,
                "article_title": art_title,
                "full_header": art["full_header"],
                "content_raw": body_text,
                "clauses": art["clauses"]
            })
            
            context_header = (
                f"[TÀI LIỆU: Luật Trật tự, an toàn giao thông đường bộ 2024 (Số 36/2024/QH15)]\n"
                f"[CHƯƠNG {ch_idx}: {ch_title}]\n"
                f"[ĐIỀU {art_num}: {art_title}]\n\n"
            )
            page_content = context_header + body_text
            
            chunk_record = {
                "id": f"law36_dieu_{art_num:02d}",
                "page_content": page_content,
                "metadata": {
                    "source": "Luật số 36/2024/QH15",
                    "chapter_id": ch_idx,
                    "chapter_roman": ch_roman,
                    "chapter_title": ch_title,
                    "article_number": art_num,
                    "article_title": art_title,
                    "article_header": art["full_header"],
                    "char_count": len(page_content),
                    "word_count": len(page_content.split())
                }
            }
            rag_chunks.append(chunk_record)
            
            md_art_block = f"### Điều {art_num}. {art_title}\n\n{body_text}\n\n"
            ch_md_lines.append(md_art_block)
            full_markdown_content.append(md_art_block)
            
        law_structured["chapters"].append(chapter_obj)
        
        with open(ch_md_path, "w", encoding="utf-8") as f:
            f.write("".join(ch_md_lines))
            
        time.sleep(0.5)
        
    print("\n------------------------------------------------------------------")
    print(f"Tổng số Điều luật đã xử lý: {total_parsed_articles}/89 Điều.")
    
    # 1. Ghi file JSON cây
    json_path = os.path.join(processed_dir, "law_36_2024_structured.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(law_structured, f, ensure_ascii=False, indent=2)
    print(f"-> Đã lưu JSON cấu trúc cây: {json_path}")
    
    # 2. Ghi file JSONL RAG chunks
    jsonl_path = os.path.join(processed_dir, "rag_chunks.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for chunk in rag_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"-> Đã lưu JSONL RAG Chunks: {jsonl_path} ({len(rag_chunks)} documents)")
    
    # 3. Ghi file Markdown toàn văn
    full_md_path = os.path.join(markdown_dir, "Luat_36_2024_QH15_Toan_Van.md")
    with open(full_md_path, "w", encoding="utf-8") as f:
        f.write("".join(full_markdown_content))
    print(f"-> Đã lưu Markdown toàn văn: {full_md_path}")
    
    # 4. Ghi file QA benchmark testset
    qa_list = generate_curated_qa_benchmark()
    qa_path = os.path.join(benchmark_dir, "qa_testset.json")
    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump({
            "dataset_name": "Traffic Law 2024 QA Benchmark",
            "description": "Bộ dữ liệu 35 câu hỏi thực tế kèm trích dẫn Điều luật đối chứng phục vụ đánh giá RAG",
            "total_questions": len(qa_list),
            "questions": qa_list
        }, f, ensure_ascii=False, indent=2)
    print(f"-> Đã lưu Benchmark QA Testset: {qa_path} ({len(qa_list)} câu hỏi mẫu)")
    
    print("\n HOÀN TẤT PIPELINE TIỀN XỬ LÝ DỮ LIỆU RAG!")

if __name__ == "__main__":
    main()
