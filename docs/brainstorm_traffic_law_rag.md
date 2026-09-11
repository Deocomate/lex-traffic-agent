# Báo Cáo Phân Tích & Thiết Kế Kiến Trúc RAG AI Chatbot Luật Giao Thông
**Dự án:** Trợ lý AI Hỏi đáp Luật Trật tự, An toàn giao thông đường bộ 2024 (Luật số 36/2024/QH15)  
**Đối tượng thực hiện:** Học sinh / Người mới bắt đầu (Beginner-friendly RAG Architecture)  
**Ngày lập:** 17/08/2026

---

## 1. Chẩn đoán vấn đề gốc (Problem-First Diagnosis)

### 1.1 Vấn đề cốt lõi
- **Tài liệu gốc dạng scan ảnh**: File PDF `data/raw_data/Luật-36-2024-QH15.pdf` (64 MB, 68 trang) hoàn toàn là ảnh scan không có text layer số. Sử dụng trực tiếp `pypdf` hay `PyPDFLoader` sẽ trả về văn bản rỗng.
- **Rủi ro khi cắt nhỏ ngẫu nhiên (Fixed-size / Token Chunking)**:
  - Luật có tính phân cấp chặt chẽ: `Văn bản > Chương > Mục > Điều > Khoản > Điểm`.
  - Cắt theo kích thước 500-1000 ký tự sẽ cắt đứt giữa các điều khoản, làm mất tiêu đề điều luật, mất chủ thể áp dụng và gây ra hiện tượng ảo giác (hallucination) trích dẫn sai số điều.
- **Mục tiêu giáo dục**: Cần một bộ dữ liệu đã được làm sạch, cấu trúc hóa chuẩn mực (100% không lỗi chính tả), kèm các định dạng phong phú (JSON, JSONL, Markdown) để học sinh tập trung học kiến trúc RAG mà không bị quá tải bởi việc tiền xử lý văn bản phức tạp.

---

## 2. So sánh các phương án kiến trúc Chunking & Xử lý dữ liệu

| Tiêu chí | Phương án A: Naive Token Chunking | Phương án B: Phân cấp Cha - Con (Parent-Child) | Phương án C: Điều luật + Tiêm ngữ cảnh (Context-Injected Article) *(Lựa chọn)* |
| :--- | :--- | :--- | :--- |
| **Đơn vị Chunk** | Cắt cứng 500 - 1000 ký tự | Chunk con (Khoản) -> Parent (Điều) | Trọn vẹn 1 Điều luật (Article-level) |
| **Bảo toàn ngữ nghĩa** | ❌ Kém (dễ cắt đôi câu/khoản) | ⭐ Rất cao (truy vết chính xác) | ⭐⭐⭐ Rất cao (Đầy đủ quy định trong 1 điều) |
| **Độ khó cho học sinh** | Dễ nhưng kết quả trả về kém | Phức tạp (cần cấu hình Retriever 2 tầng) | Rất dễ, trực quan, phù hợp LangChain/FAISS |
| **Độ dài chunk trung bình**| Cố định 500 ký tự | 50 - 200 từ (con), 400 từ (cha) | 150 - 600 từ (vừa vặn context window) |
| **Độ chính xác trích dẫn** | Thấp (thiếu số Điều) | Cao | Tuyệt đối (Metadata mang số Điều, tên Chương) |

---

## 3. Kiến trúc Bộ Dữ Liệu Toàn Diện (Full Bundle Specification)

Hệ thống cung cấp 4 cấu trúc dữ liệu đầu ra được lưu trữ trong `data/processed/` và `data/benchmark/`:

```
data/
├── raw_data/
│   └── Luật-36-2024-QH15.pdf             # Bản scan gốc
├── processed/
│   ├── law_36_2024_structured.json       # Dạng cây phân cấp (Hierarchical Tree)
│   ├── rag_chunks.jsonl                  # Dạng Document Chunks nạp Vector DB
│   └── markdown/                         # Markdown phân loại theo Chương & Điều
│       ├── Chuong_01_Nhung_quy_dinh_chung.md
│       ├── Chuong_02_Quy_tac_giao_thong_duong_bo.md
│       └── ... (Đủ 9 chương, 89 điều)
└── benchmark/
    └── qa_testset.json                   # 30+ bộ câu hỏi test đánh giá Chatbot
```

### 3.1 Chi tiết Schema JSON Cây (`law_36_2024_structured.json`)
```json
{
  "law_id": "36/2024/QH15",
  "law_name": "Luật Trật tự, an toàn giao thông đường bộ",
  "effective_date": "2025-01-01",
  "total_chapters": 9,
  "total_articles": 89,
  "chapters": [
    {
      "chapter_id": 1,
      "chapter_roman": "Chương I",
      "chapter_title": "NHỮNG QUY ĐỊNH CHUNG",
      "articles": [
        {
          "article_number": 1,
          "article_title": "Phạm vi điều chỉnh",
          "content_raw": "Luật này quy định về...",
          "clauses": [
            {
              "clause_number": 1,
              "content": "..."
            }
          ]
        }
      ]
    }
  ]
}
```

### 3.2 Kỹ thuật Tiêm Ngữ Cảnh (Context Injection) trong `rag_chunks.jsonl`
Mỗi dòng JSONL đại diện cho 1 Document trong LangChain / LlamaIndex / ChromaDB:
```json
{
  "id": "law36_dieu_15",
  "page_content": "[VĂN BẢN: Luật Trật tự, an toàn giao thông đường bộ 2024 (Số 36/2024/QH15)]\n[CHƯƠNG II: QUY TẮC GIAO THÔNG ĐƯỜNG BỘ]\n[ĐIỀU 15: Chuyển hướng xe]\n\n1. Khi muốn chuyển hướng, người điều khiển phương tiện tham gia giao thông đường bộ phải quan sát...",
  "metadata": {
    "source": "Luật 36/2024/QH15",
    "chapter_id": 2,
    "chapter_title": "QUY TẮC GIAO THÔNG ĐƯỜNG BỘ",
    "article_number": 15,
    "article_title": "Chuyển hướng xe",
    "word_count": 285
  }
}
```

---

## 4. Lộ trình Triển Khai cho Học Sinh (Student Roadmap)

1. **Giai đoạn 1: Chuẩn bị Dữ liệu (Data Pipeline Automation)**
   - Chạy script trích xuất dữ liệu sạch 100% từ văn bản Quốc hội/Công báo.
   - Phân tích và sinh ra bộ dữ liệu chuẩn: JSON cấu trúc cây, JSONL RAG chunks, Markdown theo chương.
2. **Giai đoạn 2: Xây dựng RAG Chatbot cơ bản (RAG Core Engine)**
   - Sử dụng mô hình Embedding đa ngôn ngữ (vd: `text-embedding-3-small`, `all-MiniLM-L6-v2`, `BKAI/vietnamese-bi-encoder` hoặc Gemini Embeddings).
   - Nạp vào Vector DB (FAISS / ChromaDB).
   - Viết Prompt hướng dẫn LLM trích dẫn chính xác Điều, Khoản luật khi trả lời.
3. **Giai đoạn 3: Giao diện Trực quan (UI Demo)**
   - Giao diện Streamlit tương tác mượt mà, có hiển thị nguồn trích dẫn pháp lý dưới mỗi câu trả lời.
4. **Giai đoạn 4: Đánh giá & Tinh chỉnh (Evaluation)**
   - Chạy kiểm thử tự động trên bộ `qa_testset.json` để đo độ chính xác (Retrieval Accuracy & Answer Faithfulness).
