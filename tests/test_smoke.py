"""
Bộ kiểm thử tinh gọn (Smoke Tests) cho LexTraffic AI.
Bao quát 3 thành phần cốt lõi:
1. Công cụ tra cứu pháp luật (TrafficLawTools: keyword, penalty, get_article).
2. Cấu trúc đồ thị Agentic ReAct (LangGraph StateGraph).
3. Web server routes (Trang chủ & static).
"""

import pytest
from src.tools.law_search_tools import TrafficLawTools
from src.graph.build import create_legal_graph
from src.api_server import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def tools():
    return TrafficLawTools()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_keyword_search_hang_de(tools):
    """Kiểm tra tìm kiếm từ khóa hạng DE trả về đúng Điều 57 và các điều khoản liên quan."""
    res = tools.keyword_search("hạng DE")
    assert "Điều 57" in res
    assert "Hạng DE" in res


def test_penalty_lookup(tools):
    """Kiểm tra tra cứu mức phạt lỗi vượt đèn đỏ theo NĐ 168/2024."""
    res = tools.penalty_lookup("vượt đèn đỏ")
    assert "Nghị định 168/2024" in res or "168/2024" in res


def test_get_article(tools):
    """Kiểm tra đọc toàn văn Điều 57 Luật 36/2024."""
    art = tools.get_article(57)
    assert "Điều 57" in art
    assert "Hạng DE" in art


def test_graph_compilation():
    """Kiểm tra đồ thị LangGraph Agentic ReAct biên dịch thành công và có đủ các node chính."""
    graph = create_legal_graph()
    nodes = set(graph.nodes.keys())
    assert "agent" in nodes
    assert "tools" in nodes
    assert "verify" in nodes
    assert "build_sources" in nodes


def test_web_index(client):
    """Kiểm tra endpoint trang chủ web trả về mã 200 OK."""
    response = client.get("/")
    assert response.status_code == 200
    assert "LexTraffic" in response.text
