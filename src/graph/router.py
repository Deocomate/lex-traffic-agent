"""
Node Chuẩn hóa (Normalize) và Định tuyến (Route) trong LangGraph.
Kết hợp bộ định tuyến tất định (Regex prior) với bộ định tuyến LLM có cấu trúc
(Structured Output 4-tier). Bảo đảm lỗi bỏ sót không thể xảy ra và an toàn 100%
khi mô hình LLM router gặp sự cố mạng hoặc trả về None.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from src.graph.events import emit
from src.graph.state import LegalAgentState, RouteDecision
from src.llm.provider import get_router_llm
from src.llm.structured import structured_call
from src.retrieval.vi_text import expand_query


def normalize_query(
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Tuple[str, str]:
    """
    Chuẩn hóa câu hỏi người dùng:
    - Nhận diện câu hỏi nối tiếp (<= 6 từ hoặc mở đầu bằng 'vậy còn...', 'thế thì...').
    - Ghép câu hỏi trước để tạo grounding_query hoàn chỉnh.
    - Mở rộng từ viết tắt và biến thể phương tiện qua vi_text.expand_query().
    """
    q_clean = (question or "").strip()
    if not q_clean:
        return "", ""

    # Lấy câu hỏi người dùng trước đó từ lịch sử
    previous_question = ""
    history_parts: List[str] = []
    if history:
        for m in reversed(history):
            role = m.get("role", "")
            content = m.get("content", "").strip()
            if role == "user" and content and not previous_question:
                previous_question = content
            if content:
                history_parts.append(f"{role}: {content[:100]}")

    history_summary = " | ".join(reversed(history_parts[-3:])) if history_parts else ""

    # Nhận diện câu hỏi nối tiếp ngắn
    is_short_followup = (
        len(q_clean.split()) <= 6
        or bool(re.search(r'^\s*(?:vậy\s+)?còn\b|^\s*thế\s+(?:còn\b|thì\b)', q_clean, re.IGNORECASE))
    )

    if is_short_followup and previous_question:
        grounding = f"{previous_question} {q_clean}".strip()
    else:
        grounding = q_clean

    return grounding, history_summary


def detect_by_regex(query: str) -> Tuple[List[str], List[str]]:
    """
    Định tuyến tất định bằng biểu thức chính quy (Regex Prior):
    Trả về (intents, vehicles).
    Không bao giờ ném ngoại lệ.
    """
    if not query:
        return ["law"], []

    q = query.lower()
    intents_set = set()
    vehicles_set = set()

    # 1. Phát hiện Biển báo giao thông & Vạch kẻ đường (QCVN 41:2019)
    sign_pattern = re.compile(
        r'\b(biển\s*(?:báo|cấm|hiệu\s*lệnh|chỉ\s*dẫn|nguy\s*hiểm|phụ)?|[pwiros]\.\d+[a-z]?|vạch\s*(?:kẻ)?(?:đường)?)\b',
        re.IGNORECASE
    )
    if sign_pattern.search(q):
        intents_set.add("sign")

    # 2. Phát hiện Tốc độ & Khoảng cách an toàn (Thông tư 31/2019)
    speed_pattern = re.compile(
        r'\b(tốc\s*độ|km/h|chạy\s*bao\s*nhiêu|khoảng\s*cách\s*an\s*toàn|cự\s*ly)\b',
        re.IGNORECASE
    )
    if speed_pattern.search(q):
        intents_set.add("speed")

    # 3. Phát hiện Mức phạt, trừ điểm, tước bằng (Nghị định 168/2024)
    penalty_pattern = re.compile(
        r'\b(phạt|tiền\s*phạt|mức\s*phạt|bị\s*phạt|nhiêu\s*tiền|tước|trừ\s*điểm|gplx|bằng\s*lái|'
        r'nồng\s*độ\s*cồn|rượu|bia|quá\s*tải|vượt\s*đèn|đèn\s*đỏ|lấn\s*làn|đi\s*ngược\s*chiều|'
        r'nghị\s*định\s*168|nghị\s*định|chế\s*tài|giam\s*xe|tạm\s*giữ)\b',
        re.IGNORECASE
    )
    if penalty_pattern.search(q):
        intents_set.add("penalty")

    # 4. Nhận diện phương tiện
    if re.search(r'\b(ô\s*tô|xe\s*con|xe\s*tải|xe\s*khách|xe\s*hơi|container|xe\s*ben)\b', q):
        vehicles_set.add("o_to")
    if re.search(r'\b(xe\s*máy|mô\s*tô|xe\s*gắn\s*máy|xe\s*điện|xe\s*máy\s*điện)\b', q):
        vehicles_set.add("xe_may")
    if re.search(r'\b(xe\s*đạp|xe\s*thô\s*sơ)\b', q):
        vehicles_set.add("xe_dap")
    if re.search(r'\b(máy\s*kéo|xe\s*chuyên\s*dùng)\b', q):
        vehicles_set.add("khac")

    # 5. Nếu có từ khóa hỏi về điều luật cụ thể hoặc nguyên tắc, hoặc chưa có intent nào -> thêm law
    law_pattern = re.compile(
        r'\b(điều\s*\d+|luật\s*36|luật\s*35|luật|nguyên\s*tắc|hành\s*vi\s*bị\s*cấm|quy\s*tắc|'
        r'độ\s*tuổi|hạng\s*bằng|hạng\s*gplx|a1|a|b1|b|c1|c|d1|d2|d|csgt|cảnh\s*sát\s*giao\s*thông|'
        r'dừng\s*xe|tuần\s*tra|vneid|giấy\s*tờ|đăng\s*ký|đăng\s*kiểm)\b',
        re.IGNORECASE
    )
    if law_pattern.search(q) or not intents_set:
        intents_set.add("law")

    return list(intents_set), list(vehicles_set)


def normalize_node(state: LegalAgentState) -> Dict[str, Any]:
    """Node normalize: Chuẩn hóa câu hỏi và tạo grounding_query."""
    question = state.get("question", "")
    history_messages = state.get("messages", [])

    # Chuyển messages sang định dạng history dict
    history: List[Dict[str, str]] = []
    for msg in history_messages:
        role = getattr(msg, "type", "user")
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content:
            history.append({"role": role, "content": content})

    grounding_query, _ = normalize_query(question, history)
    expanded_query, _ = expand_query(grounding_query)

    # `history_summary` KHÔNG được ghi ở đây: node `memory` là chủ sở hữu duy nhất của nó.
    # Ghi đè bằng bản ghép thô ở đây sẽ xoá mất bản tóm tắt LLM của các lượt đã bị nén.
    return {"grounding_query": expanded_query}


def route_node(state: LegalAgentState) -> Dict[str, Any]:
    """
    Node route: Định tuyến truy xuất đa nguồn.
    Phát sự kiện 'start' và 'turn_start' ra SSE stream.
    Hợp nhất Regex Prior với LLM RouteDecision.
    """
    # `src/agent.py` phải định tuyến TRƯỚC khi chạy đồ thị để dựng khoá cache ngữ nghĩa. Khi
    # trượt cache, quyết định đó được truyền thẳng vào state — chạy lại router ở đây là trả
    # tiền cho đúng một lệnh gọi LLM lần thứ hai mà kết quả chắc chắn giống hệt.
    if state.get("route") is not None:
        return {}

    emit("start", "🧠 Đang phân tích câu hỏi và nhận diện mục tiêu pháp lý...")

    grounding_query = state.get("grounding_query", state.get("question", ""))

    # 1. Định tuyến tất định bằng Regex
    regex_intents, regex_vehicles = detect_by_regex(grounding_query)

    # 2. Định tuyến bằng LLM Router qua Structured Output 4 tầng
    prompt = (
        "Phân tích câu hỏi giao thông sau và xác định mục đích tra cứu (intents):\n"
        "- penalty: tra cứu mức tiền phạt, trừ điểm GPLX, tước bằng theo Nghị định 168/2024.\n"
        "- law: tra cứu quy định, điều luật, điều kiện, quy tắc trong 6 văn bản luật giao thông.\n"
        "- sign: tra cứu biển báo giao thông hoặc vạch kẻ đường (QCVN 41:2019).\n"
        "- speed: tra cứu tốc độ tối đa cho phép hoặc khoảng cách an toàn (Thông tư 31/2019).\n\n"
        f"Câu hỏi: \"{grounding_query}\"\n"
        "Hãy phân tích và trả về cấu trúc RouteDecision."
    )

    llm_route: Optional[RouteDecision] = None
    try:
        router_llm = get_router_llm()
        llm_route = structured_call(router_llm, RouteDecision, prompt)
    except Exception:
        llm_route = None

    # 3. Phép HỢP tập hợp: Regex Prior là nền tảng, LLM chỉ bổ sung
    final_intents_set = set(regex_intents)
    final_vehicles_set = set(regex_vehicles)

    if llm_route:
        final_intents_set.update(llm_route.intents)
        final_vehicles_set.update(llm_route.vehicles)

    # Đảm bảo retrieve_law luôn luôn chạy để có căn cứ Điều luật gốc
    final_intents_set.add("law")

    search_query = (
        llm_route.search_query.strip()
        if llm_route and llm_route.search_query.strip()
        else grounding_query
    )
    doc_scope = llm_route.doc_scope if llm_route else "all"

    decision = RouteDecision(
        intents=list(final_intents_set),
        doc_scope=doc_scope,
        vehicles=list(final_vehicles_set),
        search_query=search_query,
    )

    intents_str = ", ".join(decision.intents)
    emit("turn_start", f"🔄 [Lượt 1/1] Đang kích hoạt tra cứu song song ({intents_str})...", turn=1)

    return {"route": decision}
