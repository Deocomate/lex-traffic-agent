---
title: "Tái Cấu Trúc Hệ Thống Tra Cứu: Cơ Chế Suy Luận Agentic Nhiều Vòng (Multi-Turn Agent Loop)"
description: "Chuyển đổi đồ thị LangGraph từ dạng thác nước khuôn mẫu cố định sang vòng lặp suy luận Agentic ReAct nhiều vòng, cắt bỏ các thành phần dư thừa (Router LLM ảo giác, Reranker LLM trễ cao), sửa lỗi trích xuất cụm từ khóa và khắc phục hoàn toàn sự cố tra cứu hạng xe DE."
status: pending
priority: P1
effort: "2h"
tags: [langgraph, multi-turn-agent, react-loop, tool-calling, speed-optimization, bugfix]
created: 2026-09-11
---

# Tái Cấu Trúc Hệ Thống Tra Cứu: Cơ Chế Suy Luận Agentic Nhiều Vòng

## 1. Bối cảnh & Vấn đề

- Khi tra cứu câu hỏi **"Ai lái được hạng xe DE"**, hệ thống hiện tại gặp các vấn đề:
  1. Router LLM nhỏ (`ministral-8b-2512`) tự ý viết lại câu hỏi thành `quy định về hạng xe máy hạng D, hạng xe ô tô hạng D theo Luật Giao thông đường b…` gây ảo giác nghiêm trọng.
  2. Toàn bộ đồ thị chạy theo một khuôn mẫu thác nước 1 chiều cố định (START -> route -> fanout -> rerank -> compact -> synthesize -> verify -> repair -> END).
  3. Node `compact` cắt cụt điều luật ở Rank 2 xuống còn 250 ký tự, làm mất hoàn toàn Điểm p của Điều 57 (quy định về hạng DE).
  4. Node `synthesize` không được cấp công cụ nào, hoàn toàn thụ động và không thể tự tra cứu tiếp.
  5. Thời gian phản hồi lên tới 170.9 giây vì chạy tuần tự 4-5 lần gọi OpenRouter.
  6. Hàm `search_articles` trong `law_search_tools.py` bị lỗi trích xuất trích đoạn khi gặp từ "hạng" lặp lại ở mọi dòng.

## 2. Giải pháp

1. **Chuyển sang Agentic ReAct Loop**:
   - Gắn trực tiếp 6 công cụ tra cứu cho mô hình chính `LLM_MODEL`.
   - Agent tự suy luận câu hỏi, tự chọn công cụ thích hợp (tra từ khóa, tìm kiếm ngữ nghĩa, hoặc đọc toàn văn điều luật).
   - Vòng lặp tối đa 4 lượt: Agent quan sát kết quả trả về của tool, nếu thấy cần bổ sung thì gọi tiếp tool khác (ví dụ: tìm thấy Điều 57 rồi tra tiếp Điều 59 về độ tuổi).
2. **Cắt bỏ các tầng khuôn mẫu gò bó**:
   - Bỏ Router LLM viết lại câu hỏi gây ảo giác.
   - Bỏ Reranker LLM gây trễ 30-40s.
   - Bỏ bộ cắt tỉa thô bạo 250 ký tự trong `compact`.
3. **Sửa thuật toán trích xuất trích đoạn trong `law_search_tools.py`**:
   - Ưu tiên các dòng khớp toàn bộ cụm từ khóa ("hạng DE").
4. **Cập nhật System Prompt**:
   - Bổ sung quy định đầy đủ 15 hạng GPLX (có DE), Điều 59 (độ tuổi), Điều 60 (đào tạo nâng hạng).
5. **Đảm bảo bảo toàn 100% hợp đồng sự kiện SSE** (`tool_call`, `tool_result`, `synthesizing`, `token`, `verified`, `done`).
