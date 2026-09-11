> [!NOTE]
> **LƯU Ý LỊCH SỬ THIẾT KẾ (HISTORICAL REFERENCE)**  
> Tài liệu này được biên soạn cho mục đích giảng dạy và phản ánh bảng màu, giao diện trước tháng 09/2026. Mặc dù vẫn giữ nguyên toàn bộ giá trị sư phạm về tư duy UX/UI cho học sinh, bảng màu và mã nguồn giao diện thực tế hiện tại của LexTraffic AI đã được nâng cấp lên Hệ thiết kế Tối giản (Minimal Design System) thuần tokens CSS.  
> **Nguồn chuẩn kỹ thuật hiện tại:** Vui lòng tham khảo [`docs/design-system.md`](file:///c:/Users/minhlong/Desktop/evo/ai-giaothong/docs/design-system.md).

# 🎨 CẨM NANG THIẾT KẾ UI/UX DÀNH CHO HỌC SINH
## Dự án: Trợ Lý AI Tra Cứu Luật Trật Tự, An Toàn Giao Thông 2024
> **Dành cho:** Học sinh THCS (Cấp 2) & THPT (Cấp 3)  
> **Mục tiêu:** Giúp học sinh nắm vững tư duy thiết kế trải nghiệm người dùng (UX) và tự tay xây dựng giao diện (UI) đẹp mắt, hiện đại, dễ tiếp cận cho người dân.

---

## 🌟 1. HIỂU VỀ UI VÀ UX BẰNG VÍ DỤ ĐỜI THƯỜNG

Trước khi bắt tay vào code, bạn cần hiểu rõ **UI** và **UX** là gì:

| Khái niệm | Ý nghĩa đơn giản | Ví dụ chiếc Xe Đạp Điện | Ví dụ Ứng Dụng Luật Giao Thông |
| :--- | :--- | :--- | :--- |
| **UI** *(User Interface)* | **"Bộ mặt"** của ứng dụng: Màu sắc, phông chữ, nút bấm, biểu tượng, hình ảnh minh họa. | Màu sơn bóng bẩy, đèn pha LED rực rỡ, đồng hồ điện tử viền phát sáng. | Khung chat bo tròn mềm mại, biểu tượng xe máy/ô tô ngộ nghĩnh, màu xanh - đỏ báo hiệu giao thông. |
| **UX** *(User Experience)* | **"Cảm giác"** khi sử dụng: Có dễ tìm thông tin không, bấm có nhạy không, câu trả lời có dễ hiểu không. | Yên xe ngồi êm ái, tay ga nhẹ, phanh nhạy an toàn, xe đi không bị xóc. | Gõ 1 câu hỏi là 0.1 giây sau thấy ngay Điều luật cần tìm; có nút bấm chọn nhanh không cần gõ dài dòng. |

> 💡 **Quy tắc vàng:** *"Một ứng dụng có UI đẹp khiến người dùng muốn bấm vào xem, nhưng UX tốt mới là thứ giữ chân người dùng ở lại lâu dài!"*

---

## 🎯 2. TẠI SAO ỨNG DỤNG LUẬT GIAO THÔNG RẤT CẦN UI/UX TỐT?

1. **Văn bản Luật rất dài và khô khan:** Luật số 36/2024/QH15 dài tới 68 trang với 89 Điều và hàng trăm Khoản/Điểm. Người dân và học sinh rất ngại đọc.
2. **Cần câu trả lời ngay lập tức:** Khi ra đường hoặc trước kỳ thi lái xe, người dùng cần biết ngay: *"Bao nhiêu tuổi được đi xe 50cc?"*, *"Uống rượu bia bị phạt thế nào?"*.
3. **Nhiệm vụ của bạn:** Biến văn bản pháp luật phức tạp thành **trải nghiệm hỏi đáp trò chuyện thân thiện, dễ hiểu, sinh động như nói chuyện với một người bạn thông thái**.

---

## 🎨 3. BẢNG MÀU GIAO THÔNG CHUẨN (TRAFFIC COLOR PALETTE)

Khi thiết kế giao diện, hãy sử dụng các tông màu hài hòa mang tính gợi nhớ về an toàn giao thông:

```
[ 🔵 #1E3A8A - Xanh Biển Đậm ]  -> Màu thương hiệu chính, thanh Menu, Tiêu đề (Tạo sự tin cậy, chuẩn mực)
[ 🟢 #059669 - Xanh Lá An Toàn ] -> Điều luật hợp lệ, độ khớp cao, nút Tra cứu (Gợi ý đèn xanh thông suốt)
[ 🟡 #D97706 - Vàng Cảnh Báo ]  -> Lưu ý quan trọng, câu hỏi thường gặp (Gợi ý đèn vàng chú ý)
[ 🔴 #DC2626 - Đỏ Cấm Đoán ]   -> Hành vi bị nghiêm cấm, lỗi phạt nặng (Gợi ý đèn đỏ dừng lại)
[ ⚫ #0F172A - Xám Đen Slate ]   -> Nền giao diện Dark Mode hiện đại, chống mỏi mắt
```

---

## 🚀 4. GỢI Ý 5 Ý TƯỞNG NÂNG CẤP GIAO DIỆN (UI/UX IDEAS)

### Ý tưởng 1: Khung Chatbot Đàm Thoại (Interactive Chat Interface)
- Sử dụng dạng bong bóng tin nhắn (Chat Bubbles) giống Zalo / Messenger.
- Gắn Avatar mascot dễ thương:
  - 🤖 **Bot:** Avatar Chú Cảnh Sát Giao Thông AI vui vẻ.
  - 👤 **User:** Avatar bạn học sinh hoặc hình đại diện người dùng.
- Thêm hiệu ứng gõ chữ (Streaming / Typing animation) giúp trải nghiệm chân thực.

### Ý tưởng 2: Thẻ Gợi Ý Câu Hỏi Nhanh Theo Chủ Đề (Quick Filter Chips)
Tạo các nhóm nút bấm màu sắc theo đối tượng người dùng:
- 🎒 **Dành cho Học sinh:** *Độ tuổi đi xe 50cc?*, *Đi xe đạp điện có phải đội mũ bảo hiểm?*, *Học sinh có được đi xe phân khối lớn?*
- 🪪 **Bằng Lái & Điểm Số:** *Quy định bằng A1 mới 2024?*, *Bằng lái có bao nhiêu điểm?*, *Bị trừ điểm thế nào?*
- 🍺 **Quy Tắc An Toàn:** *Nồng độ cồn?*, *Chuyển làn đường?*, *Không được lùi xe ở đâu?*

### Ý tưởng 3: Thẻ Hiển Thị Điều Luật Thông Minh (Smart Law Card)
Mỗi Điều luật được tìm thấy sẽ hiển thị dưới dạng 1 Thẻ (Card):
- **Huy hiệu đầu thẻ:** Số Điều (Ví dụ: `Điều 59`), Tên Chương, và Tỷ lệ tương đồng (Ví dụ: `Độ khớp: 98%`).
- **Nội dung chính:** Tóm tắt ngắn gọn quy định bằng 1-2 câu dễ hiểu.
- **Nút "Xem toàn văn điều luật":** Dạng Accordion / Dropdown mở rộng khi người dùng muốn đọc chi tiết từng Khoản, Điểm.
- **Tính năng Highlight:** Bôi vàng các từ khóa người dùng vừa hỏi (ví dụ: `50 cm³`, `16 tuổi`).

### Ý tưởng 4: Bộ Công Cụ Tiện Ích Giao Thông (Interactive Mini-Tools)
- **Công cụ Tính Điểm Bằng Lái:** Thanh trượt (Slider) hiển thị 12 điểm bằng lái, khi tích chọn lỗi vi phạm thì thanh điểm sẽ giảm kèm lời cảnh báo.
- **Tra cứu Nhanh Độ Tuổi:** Nhập năm sinh của bạn -> Ứng dụng tự động thông báo bạn được phép điều khiển những loại xe nào!

### Ý tưởng 5: Trắc Nghiệm Ôn Luyện Luật Giao Thông (Gamification)
- Thêm tab "Thử tài hiểu luật" gồm 3 câu hỏi trắc nghiệm tình huống vui.
- Trả lời đúng nhận pháo hoa chúc mừng (`st.balloons()` trong Streamlit) và huy hiệu *Tay Lái An Toàn*!

---

## 💻 5. HƯỚNG DẪN CODE STREAMLIT NÂNG CAO CHO HỌC SINH

Bạn có thể chỉnh sửa tệp [app.py](file:///c:/Users/minhlong/Desktop/ai-giaothong/app.py) để áp dụng ngay các thành phần giao diện đẹp mắt sau:

### 5.1 Thêm CSS tùy biến làm đẹp giao diện
```python
import streamlit as st

# Thêm CSS để làm đẹp giao diện
st.markdown("""
<style>
    /* Nền và font chữ */
    .main {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    /* Thẻ Điều luật bo góc đẹp mắt */
    .law-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid rgba(59, 130, 246, 0.4);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .badge-article {
        background-color: #3b82f6;
        color: white;
        padding: 4px 12px;
        border-radius: 999px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-score {
        background-color: #10b981;
        color: white;
        padding: 4px 12px;
        border-radius: 999px;
        font-weight: bold;
        font-size: 0.85rem;
        float: right;
    }
</style>
""", unsafe_allow_html=True)
```

### 5.2 Xây dựng khung Chatbot tương tác
```python
# Khởi tạo lịch sử chat trong session_state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Xin chào! Mình là Trợ lý AI Luật Giao Thông 2024. Bạn đang muốn tìm hiểu về quy định nào?"}
    ]

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user", avatar="🎒").write(msg["content"])
    else:
        st.chat_message("assistant", avatar="👮‍♂️").write(msg["content"])

# Ô nhập tin nhắn
if prompt := st.chat_input("Hỏi bất kỳ điều gì về luật giao thông..."):
    # Lưu tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="🎒").write(prompt)
    
    # AI tìm kiếm và trả lời
    results = rag.retrieve(prompt, top_k=3)
    top_doc = results[0]
    
    bot_reply = f"""
    📌 **Căn cứ pháp lý:** {top_doc['article_header']} ({top_doc['chapter_title']})
    
    💡 **Quy định chi tiết:**
    {top_doc['page_content']}
    """
    
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    st.chat_message("assistant", avatar="👮‍♂️").markdown(bot_reply)
```

### 5.3 Nút chọn câu hỏi nhanh (Quick Chips)
```python
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🛵 Bao nhiêu tuổi được đi xe 50cc?"):
        st.session_state["query_input"] = "Bao nhiêu tuổi được đi xe máy 50cc?"
with col2:
    if st.button("🍺 Nồng độ cồn bị cấm ra sao?"):
        st.session_state["query_input"] = "Nồng độ cồn khi lái xe bị cấm như thế nào?"
with col3:
    if st.button("🪪 Bằng lái xe A1 mới 2024?"):
        st.session_state["query_input"] = "Bằng lái xe máy A1 áp dụng cho loại xe nào?"
```

---

## 🏆 6. BẢNG TIÊU CHÍ TỰ ĐÁNH GIÁ SẢN PHẨM UI/UX (RUBRIC)

Hãy dùng bảng này để tự chấm điểm sản phẩm của bạn trước khi báo cáo:

| Tiêu chí | Mức Đạt (5-7 điểm) | Mức Xuất Sắc (8-10 điểm) | Bạn Tự Đánh Giá |
| :--- | :--- | :--- | :--- |
| **1. Tính Thẩm Mỹ (UI)** | Màu sắc rõ ràng, dễ nhìn, chữ không bị lỗi font. | Sử dụng bảng màu giao thông hài hòa, có card bo góc, badge nổi bật, icon sống động. | [ ... / 10 ] |
| **2. Độ Dễ Dùng (UX)** | Người dùng biết chỗ nhập câu hỏi và đọc kết quả. | Có các nút câu hỏi mẫu 1 chạm, trích dẫn số Điều rõ ràng, thời gian phản hồi tức thì. | [ ... / 10 ] |
| **3. Tính Sáng Tạo** | Chỉ có ô tra cứu đơn thuần. | Có khung chat đàm thoại, hiệu ứng pháo hoa, mini quiz, hoặc công cụ tính điểm bằng lái. | [ ... / 10 ] |
| **4. Trải Nghiệm Di Động** | Xem được trên máy tính. | Bố cục vừa vặn cả trên màn hình điện thoại smartphone, nút bấm to dễ thao tác. | [ ... / 10 ] |

---

## 🏁 LỜI KHUYÊN DÀNH CHO CÁC BẠN HỌC SINH
- **Đừng sợ thử sai:** Hãy thoải mái đổi màu sắc, thêm nút bấm, thay đổi câu chữ. Nếu bị lỗi, chỉ cần `Ctrl + Z` để quay lại.
- **Hỏi ý kiến bạn bè:** Hãy cho người ngồi cạnh dùng thử và quan sát xem họ có gặp khó khăn gì không để cải tiến.
- **Chúc bạn tạo ra một sản phẩm AI giao thông thật ấn tượng và hữu ích cho cộng đồng!** 🚀
