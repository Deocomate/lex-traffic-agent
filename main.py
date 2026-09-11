#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LexTraffic AI - Hệ Thống Trợ Lý Pháp Lý Giao Thông Đường Bộ Thông Minh 2024
Entry Point / Launcher Trung Tâm

Hỗ trợ các chế độ:
1. 🌐 Web App: Giao diện web nối trực tiếp với AI Agent (FastAPI + SSE)
2. 💬 Agentic Search CLI: Hỏi đáp trên Terminal với Live Workflow
3. 📈 Evaluation Benchmark: Chạy bộ kiểm thử tình huống thực tế
"""

import os
import sys
import argparse
import socket
import threading
import webbrowser

# Cấu hình encoding trên Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DEFAULT_PORT = 8080


def find_available_port(start_port=DEFAULT_PORT, max_attempts=20):
    """Tìm cổng mạng khả dụng, bắt đầu từ cổng mặc định của dự án"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port


def launch_web(open_browser=True, custom_port=None, reload=False):
    """Khởi động máy chủ web phục vụ giao diện + API của AI Agent"""
    try:
        import uvicorn
    except ImportError:
        print("❌ Thiếu thư viện máy chủ web. Cài đặt bằng: pip install -r requirements.txt")
        return

    start_port = custom_port if custom_port is not None else DEFAULT_PORT
    port = find_available_port(start_port=start_port)
    if custom_port is not None and port != custom_port:
        print(f"⚠️ Cổng {custom_port} đã bị ứng dụng khác chiếm dụng! Tự động chuyển sang cổng khả dụng: {port}")

    url = f"http://127.0.0.1:{port}"

    print(f"\n🚀 LexTraffic AI Web App: {url}")
    print("💡 Nhấn Ctrl+C để dừng máy chủ.\n")

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run("src.api_server:app", host="127.0.0.1", port=port, log_level="warning", reload=reload)
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng máy chủ web.")


def launch_cli_chat():
    """Khởi động CLI Chat Agentic"""
    chat_script = os.path.join(BASE_DIR, "scripts", "chat.py")
    if not os.path.exists(chat_script):
        print(f"❌ Không tìm thấy script: {chat_script}")
        return
    os.system(f'"{sys.executable}" "{chat_script}"')


def launch_eval():
    """Khởi động Benchmark Evaluation mới"""
    eval_script = os.path.join(BASE_DIR, "scripts", "eval", "retrieval_eval.py")
    if not os.path.exists(eval_script):
        print(f"❌ Không tìm thấy script: {eval_script}")
        return
    os.system(f'"{sys.executable}" "{eval_script}"')


def interactive_menu():
    """Menu tương tác lựa chọn chế độ chạy"""
    print("=" * 78)
    print("  🏛️  LEXTRAFFIC AI - TRỢ LÝ PHÁP LÝ & KHO TIỆN ÍCH GIAO THÔNG 2024  🏛️")
    print("   Căn cứ: 6 văn bản pháp luật giao thông & Nghị định xử phạt 168/2024")
    print("=" * 78)
    print("\n [1] 🌐 Mở Web App (Jinja2: Chat AI, 6 Bộ luật, 634 Lỗi phạt & Kho Tiện ích)")
    print(" [2] 💬 Trợ lý AI trên Terminal (Agentic Search CLI)")
    print(" [3] 🧪 Chạy Kiểm Thử & Đánh Giá Hiệu Năng RAG")
    print(" [0] 🚪 Thoát\n")

    actions = {"1": launch_web, "2": launch_cli_chat, "3": launch_eval}

    while True:
        try:
            choice = input("👉 Nhập lựa chọn của bạn [0-3]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Tạm biệt!")
            return

        if choice in actions:
            actions[choice]()
            return
        if choice == "0" or choice.lower() in ("exit", "quit"):
            print("👋 Tạm biệt!")
            return
        print("⚠️ Lựa chọn không hợp lệ, vui lòng thử lại!")


def main():
    parser = argparse.ArgumentParser(description="LexTraffic AI - Trợ lý Pháp lý Giao thông 2024")
    parser.add_argument("--web", "--ui", action="store_true", help="Mở Web App giao diện chat với AI Agent")
    parser.add_argument("--chat", "--cli", action="store_true", help="Bật CLI Agentic Chatbot")
    parser.add_argument("--eval", "--benchmark", action="store_true", help="Chạy đánh giá benchmark RAG")
    parser.add_argument("--no-browser", action="store_true", help="Không tự mở trình duyệt khi chạy Web App")
    parser.add_argument("--port", type=int, default=None, help="Cổng mạng tùy chọn (mặc định tự động tìm từ 8080)")
    parser.add_argument("--reload", action="store_true", help="Tự động tải lại mã nguồn khi có thay đổi (Hot reload)")

    args = parser.parse_args()

    if args.web:
        launch_web(open_browser=not args.no_browser, custom_port=args.port, reload=args.reload)
    elif args.chat:
        launch_cli_chat()
    elif args.eval:
        launch_eval()
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
