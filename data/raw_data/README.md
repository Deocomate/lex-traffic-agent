# 📚 Kho Tài Liệu Pháp Luật Gốc (Raw Legal Data Corpus)

> Thư mục lưu trữ toàn bộ các văn bản quy phạm pháp luật, nghị định, thông tư và quy chuẩn kỹ thuật quốc gia nguyên bản (dạng PDF) phục vụ cho hệ thống **AI Trợ Lý Pháp Lý Giao Thông 2025**.

---

## 🗂️ 1. Quy ước Đặt tên Tập tin (Naming Convention)

Để hệ thống xử lý dữ liệu tự động (ETL / RAG Pipeline), lập chỉ mục và quản trị dễ dàng trên mọi môi trường (Windows, Linux, Docker, Git), tất cả các tệp văn bản được chuẩn hóa theo quy tắc:

```
[STT]_[LOAI_VAN_BAN]_[SO_HIEU]_[TEN_RUT_GON_CHU_DE].pdf
```

* **STT (`01_`, `02_`, ...):** Đánh số theo thứ bậc hiệu lực pháp lý và mức độ cốt lõi trong hệ thống pháp luật (Luật ➔ Nghị định ➔ Thông tư ➔ Quy chuẩn kỹ thuật).
* **Chữ thường, không dấu tiếng Việt, dùng dấu gạch dưới (`_`):** Ngăn ngừa lỗi encoding, lỗi đường dẫn trên terminal, server và Docker container.
* **Số hiệu & Tên rút gọn:** Thể hiện rõ ngay số hiệu và chủ đề chính mà văn bản điều chỉnh.

---

## 📋 2. Danh Mục Tài Liệu Pháp Lý Chuẩn Hóa

| STT | Tên tệp tin chuẩn hóa | Tên đầy đủ văn bản | Cơ quan ban hành | Ngày hiệu lực | Phạm vi điều chỉnh chính |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **01** | `01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong.pdf` | **Luật Trật tự, an toàn giao thông đường bộ** (Luật số 36/2024/QH15) | Quốc hội khóa XV | **01/01/2025** | Quy tắc giao thông đường bộ, phân hạng GPLX mới (A1, A, B, C1...), cơ chế trừ 12 điểm bằng lái, điều kiện an toàn phương tiện, giải quyết TNGT. |
| **02** | `02_luat_35_2024_qh15_duong_bo.pdf` | **Luật Đường bộ** (Luật số 35/2024/QH15) | Quốc hội khóa XV | **01/01/2025** | Kết cấu hạ tầng đường bộ, đường cao tốc, trạm thu phí không dừng (ETC), điều kiện kinh doanh vận tải (taxi, xe buýt, xe hợp đồng, xe công nghệ). |
| **03** | `03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham.pdf` | **Nghị định quy định xử phạt VPHC về trật tự ATGT đường bộ; trừ điểm, phục hồi điểm GPLX** (Nghị định 168/2024/NĐ-CP) | Chính phủ | **01/01/2025** | Chế tài xử phạt, khung tiền phạt (VNĐ), số điểm GPLX bị trừ cho từng lỗi, thời hạn tước GPLX, tạm giữ phương tiện *(thay thế NĐ 100/2019 và NĐ 123/2021)*. |
| **04** | `04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach.pdf` | **Thông tư quy định về tốc độ và khoảng cách an toàn của xe cơ giới, xe máy chuyên dùng** (Thông tư 31/2019/TT-BGTVT) | Bộ Giao thông vận tải | 15/10/2019 | Quy định chi tiết tốc độ tối đa cho phép trong/ngoài khu đông dân cư, cự ly an toàn tối thiểu theo dải tốc độ (km/h). |
| **05** | `05_thong_tu_73_2024_tt_bca_tuan_tra_csgt.pdf` | **Thông tư quy định công tác tuần tra, kiểm soát, xử lý vi phạm pháp luật về trật tự ATGT đường bộ của CSGT** (Thông tư 73/2024/TT-BCA) | Bộ Công an | **01/01/2025** | Quyền hạn của CSGT khi dừng xe, 4 trường hợp được dừng phương tiện, kiểm soát giấy tờ tích hợp trên VNeID, quy trình phạt nguội qua camera. |
| **06** | `06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo.pdf` | **Quy chuẩn kỹ thuật Quốc gia về Báo hiệu đường bộ** (QCVN 41:2019/BGTVT ban hành kèm Thông tư 54/2019/TT-BGTVT) | Bộ Giao thông vận tải | 01/07/2020 | Toàn bộ hệ thống biển báo hiệu (biển cấm P, hiệu lệnh R, nguy hiểm W, chỉ dẫn I, biển phụ S), ý nghĩa vạch kẻ đường, đèn tín hiệu, cọc tiêu. |

---

## 🎯 3. Phân Công Vai Trò Kiến Thức Cho AI Agent

Hệ thống AI Agent sử dụng 6 văn bản này theo ma trận nghiệp vụ:

```
                                  [CÂU HỎI NGƯỜI DÙNG]
                                            │
         ┌──────────────────────────────────┼──────────────────────────────────┐
         ▼                                  ▼                                  ▼
[Quy tắc, Bằng lái, Điểm số]        [Tốc độ & Biển báo]             [Mức phạt tiền & CSGT]
  ├─ 01_luat_36 (Luật Trật tự ATGT)  ├─ 04_thong_tu_31 (Tốc độ)       ├─ 03_nghi_dinh_168 (Mức phạt)
  └─ 02_luat_35 (Luật Đường bộ)      └─ 06_qcvn_41 (Biển & Vạch)      └─ 05_thong_tu_73 (CSGT, VNeID)
```

| Tình huống người dùng hỏi | Tài liệu tra cứu chính | Công cụ Agent tương ứng |
| :--- | :--- | :--- |
| *"Bằng B1 khác bằng B thế nào theo luật mới?"* | `01_luat_36...` (Điều 57) | `get_article`, `keyword_search` |
| *"Chở con 5 tuổi ngồi trước xe máy có được không?"* | `01_luat_36...` (Điều 31) | `semantic_search` |
| *"Xe máy trong khu đông dân cư chạy tối đa bao nhiêu?"* | `04_thong_tu_31...` (Điều 6) | `speed_limit_lookup` / `semantic_search` |
| *"Biển P.106a cấm xe tải thì xe bán tải có được đi vào không?"* | `06_qcvn_41...` (Mục 3.24 & B.6) | `traffic_sign_lookup` |
| *"Vượt đèn đỏ xe máy phạt bao nhiêu, trừ mấy điểm?"* | `03_nghi_dinh_168...` (Điều 7) | `penalty_lookup` |
| *"CSGT kiểm tra bằng lái trên VNeID có hợp lệ không?"* | `05_thong_tu_73...` (Điều 8) | `semantic_search` |
| *"Xe kinh doanh taxi công nghệ cần điều kiện gì?"* | `02_luat_35...` (Điều 56) | `semantic_search` |

---

## ⚙️ 4. Hướng Dẫn Pipeline Xử Lý Dữ Liệu (Data Pipeline)

Khi bổ sung hoặc cập nhật chỉ mục tìm kiếm (Vector Search / RAG):

1. **Trích xuất & Làm sạch:**
   - Dùng script trong `scripts/` (hoặc module parser PDF) để bóc tách văn bản, giữ nguyên số thứ tự Chương, Mục, Điều, Khoản, Điểm.
   - Với `06_qcvn_41...`, cần bóc tách riêng từng biển báo thành JSON có trường mã hiệu (`sign_code`), tên gọi (`name`), mô tả ngoại quan (`visual_features`), và ý nghĩa cấm/hiệu lệnh (`meaning`).

2. **Gán Metadata định danh nguồn:**
   Khi tạo chunk để nạp vào Vector Database, luôn gắn metadata:
   ```json
   {
     "doc_id": "01_luat_36_2024_qh15",
     "doc_type": "luat",
     "chapter": "Chương II",
     "article": 11,
     "title": "Tín hiệu giao thông đường bộ"
   }
   ```
   Việc này giúp AI Agent trích dẫn chính xác nguồn văn bản, tránh tình trạng "râu ông nọ cắm cằm bà kia".

---

## ⚠️ 5. Lưu Ý Về Tính Pháp Lý & Toàn Vẹn Dữ Liệu

* **Tuyệt đối không chỉnh sửa nội dung văn bản:** Các tệp PDF trong thư mục này là tài liệu đối soát gốc (Ground Truth).
* **Đồng bộ thời điểm hiệu lực:** Luật 36, Luật 35, Nghị định 168 và Thông tư 73 đều có cùng mốc hiệu lực thi hành từ ngày **01/01/2025**.
