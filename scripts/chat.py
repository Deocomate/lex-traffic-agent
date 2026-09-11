"""
Ứng dụng Chatbot AI Luật Giao Thông 2024 (Agentic Search CLI)
Tích hợp AI Agent tự động phân tích câu hỏi, gọi công cụ tra cứu (Tools Calling)
và hiển thị TOÀN BỘ TIẾN TRÌNH (Workflow Stream) thời gian thực.
"""

import os
import sys
import time

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.agent import get_agent

def print_header():
    print("\n" + "=" * 78)
    print(" 🚗 TRỢ LÝ AI LUẬT GIAO THÔNG 2024 - AGENTIC WORKFLOW & LEGAL SEARCH 🚗")
    print("  🧠 Model: ~deepseek/deepseek-v4-flash-latest / deepseek-chat")
    print("  🛠️ Cơ chế: Tự động trích xuất ý định, Gọi công cụ & Hiển thị Live Workflow")
    print("=" * 78)

def cli_step_callback(event_data: dict):
    """Callback in trực tiếp từng bước hành động của Agent ra màn hình thời gian thực"""
    evt = event_data.get("event")
    msg = event_data.get("message", "")
    ts = event_data.get("timestamp", time.strftime("%H:%M:%S"))
    
    if evt == "start":
        print(f"  [{ts}] {msg}")
    elif evt == "turn_start":
        print(f"\n  [{ts}] {msg}")
    elif evt == "tool_call":
        print(f"    👉 {msg}")
    elif evt == "tool_result":
        print(f"    {msg}")
    elif evt == "synthesizing":
        print(f"\n  [{ts}] {msg}")
    elif evt == "model_fallback":
        print(f"  [{ts}] {msg}")
    elif evt == "completed":
        print(f"  [{ts}] {msg}")

def main():
    print_header()
    print("\n[1/2] Đang khởi tạo AI Agent (LangGraph StateGraph) & nạp bộ công cụ tra cứu...")
    agent = get_agent()
    print("[2/2] Khởi tạo hoàn tất! Bạn có thể hỏi bất kỳ câu hỏi nào (Gõ 'exit' để thoát).\n")
    
    sample_queries = [
        "Ô tô uống rượu phạt nhiêu tiền?",
        "Ai lái được bằng C1?",
        "Bằng lái xe máy A1 theo luật 2024 lái được xe gì?",
        "Bao nhiêu tuổi thì học sinh được đi xe máy dưới 50cc?",
        "Hôm qua đi nhậu 3 lon bia sáng nay chạy xe máy có bị phạt không?",
        "Mỗi bằng lái xe có bao nhiêu điểm và phục hồi thế nào?"
    ]
    
    print("💡 Gợi ý câu hỏi:")
    for i, sq in enumerate(sample_queries, 1):
        print(f"  {i}. {sq}")
    print("-" * 78)
    
    while True:
        try:
            query = input("\n👉 Nhập câu hỏi của bạn: ").strip()
            if not query:
                continue
            if query.lower() in ['exit', 'quit', 'thoat', 'q']:
                print("\nCảm ơn bạn đã sử dụng AI Agent Luật Giao Thông! Tạm biệt!")
                break
                
            print("\n" + "─" * 78)
            print("🤖 TIẾN TRÌNH SUY LUẬN & TRA CỨU CỦA AGENT (LIVE WORKFLOW):")
            print("─" * 78)
            t0 = time.time()
            result = agent.run_agent(query, step_callback=cli_step_callback)
            elapsed = time.time() - t0
            print("─" * 78)
            
            print("\n" + "=" * 78)
            print(f"🤖 LỜI GIẢI ĐÁP PHÁP LÝ TỪ AI AGENT (Mô hình: {result.get('model_used', 'DeepSeek')}):")
            print("=" * 78)
            print(result.get("answer", "Không có câu trả lời."))
            # Ngoài vùng dữ liệu đã tra cứu: đưa sẵn liên kết Google để người dùng tự tra cứu tiếp
            search = result.get("search")
            if result.get("needs_search") and search:
                print("\n🔎 Tra cứu thêm trên Google:")
                print(f"   {search['url']}")
            print("=" * 78)
            print(f"⏱️ Tổng thời gian Agent xử lý: {elapsed:.2f}s | Số công cụ đã dùng: {len(result.get('agent_steps', []))}\n")
            
        except KeyboardInterrupt:
            print("\nThoát chương trình.")
            break
        except Exception as e:
            print(f"\n[Lỗi]: {e}")

if __name__ == "__main__":
    main()
