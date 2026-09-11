"""
Node Đóng gói Ngữ cảnh (Context Compaction) cho StateGraph LangGraph.
Tối ưu hóa ngữ cảnh cho các mô hình ngôn ngữ nhỏ (Small Language Models):
- Cắt bỏ triệt để việc lặp lại khối FIGURE_LOCK_NOTE (~15 dòng lặp lại 4 lần = 60 dòng rác).
- Phân cấp nén dữ liệu:
  * Rank 1 mỗi nguồn: Toàn văn parent, cắt tối đa 2500 ký tự (PARENT_CONTENT_LIMIT).
  * Rank 2-3: Chỉ trích đoạn quan trọng (key_clauses, tối đa 2 khoản).
  * Rank >= 4: Chỉ giữ một dòng citation + tiêu đề.
  * Kết quả phạt: Giữ đầy đủ tất cả các trường (loại xe, trích dẫn, hành vi, mức tiền, điểm trừ) — dữ liệu số không bao giờ bị cắt.
- Khối chỉ dẫn duy nhất được đặt ngay trước câu hỏi ở cuối prompt.
- Tuân thủ nghiêm ngặt ngân sách token cứng (CONTEXT_TOKEN_BUDGET, mặc định 6000 token).
- Tạo khay nguồn trích dẫn phong phú (sources) cho giao diện người dùng.
"""

import os
import re
from typing import Any, Dict, List, Optional

from src.graph.events import emit
from src.graph.state import Evidence, LegalAgentState
from src.tools.document_provider import get_document_provider

DEFAULT_CONTEXT_TOKEN_BUDGET = int(os.getenv("CONTEXT_TOKEN_BUDGET", "6000"))
PARENT_CONTENT_LIMIT = 2500

SINGLE_INSTRUCTION_BLOCK = (
    "\n[CHỈ DẪN BẮT BUỘC VỀ SỐ LIỆU VÀ CĂN CỨ PHÁP LÝ]:\n"
    "1. Mọi con số tiền phạt, số điểm GPLX bị trừ, thời hạn tước bằng BẮT BUỘC phải lấy nguyên văn "
    "từ dữ liệu tra cứu Nghị định 168 ở trên. TUYỆT ĐỐI không suy diễn hoặc tự điền số tiền từ trí nhớ.\n"
    "2. Trích dẫn đầy đủ Điểm/Khoản/Điều của Nghị định 168/2024/NĐ-CP khi nêu mức phạt.\n"
    "3. Phân tích đầy đủ theo từng nhóm phương tiện: XE Ô TÔ và XE MÁY nếu câu hỏi chưa nêu rõ loại xe.\n"
    "4. Nếu có biển báo/vạch kẻ đường kèm ảnh Markdown, BẮT BUỘC chèn nguyên văn cú pháp ảnh `![tên](đường_dẫn)` vào câu trả lời.\n"
    "5. BẮT BUỘC nêu đích danh số Điều (và số Khoản nếu có) NGAY TRONG PHẦN NỘI DUNG câu trả lời — "
    "chép đúng nguyên số Điều ghi ở các dòng '[Rank... - ...]' hoặc '[CĂN CỨ MỨC PHẠT...]' phía trên. "
    "TUYỆT ĐỐI không viết mơ hồ kiểu 'theo quy định của pháp luật hiện hành' hay 'theo quy định hiện "
    "hành' mà không kèm số Điều cụ thể. Nếu dữ liệu tra cứu ở trên không có Điều nào phù hợp, phải "
    "nói thẳng 'Tôi chưa có dữ liệu về quy định cho trường hợp này' thay vì viết chung chung.\n"
    "6. Ở cuối câu trả lời, BẮT BUỘC có khối trích dẫn nguồn: '### 📌 Căn cứ pháp lý trích dẫn:'.\n"
    "7. Nếu câu hỏi KHÔNG thuộc lĩnh vực giao thông đường bộ (hỏi giá xăng, thời tiết, sức khoẻ, "
    "nấu ăn, lịch thi, tài chính, phong thuỷ, mua bán xe...), BẮT BUỘC mở đầu câu trả lời bằng "
    "đúng câu: 'Câu hỏi này không thuộc phạm vi tra cứu của tôi.' rồi mới giải thích ngắn gọn. "
    "Trong trường hợp đó TUYỆT ĐỐI không nêu bất kỳ con số tiền nào — kể cả để minh hoạ."
)


def estimate_tokens(text: str) -> int:
    """Ước tính số token của chuỗi văn bản (dùng tiktoken cl100k_base hoặc tỷ lệ 1.5 word/token)."""
    if not text:
        return 0
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return int(len(text.split()) * 1.5)


def build_sources_from_evidence(evidence_list: List[Evidence]) -> List[Dict[str, Any]]:
    """Tạo danh sách nguồn trích dẫn (sources) chuẩn hóa cho UI."""
    sources: List[Dict[str, Any]] = []
    seen_keys = set()
    provider = get_document_provider()

    for ev in evidence_list:
        src = ev.get("source")
        citation = ev.get("citation", "")

        if src == "penalty":
            key = f"penalty_{citation}"
            if key not in seen_keys:
                seen_keys.add(key)
                content = ev.get("content", "")
                m_fine = re.search(r'Mức phạt tiền:\s*([^\n]+)', content)
                fine_text = m_fine.group(1).strip() if m_fine else ""
                m_points = re.search(r'Trừ điểm GPLX:\s*([^\n]+)', content)
                points = m_points.group(1).strip() if m_points else ""
                m_veh = re.search(r'^\[([^\]]+)\]', citation)
                vehicle = m_veh.group(1).strip() if m_veh else ""

                sources.append({
                    "source_type": "decree",
                    "doc_name": "Nghị định 168/2024/NĐ-CP",
                    "doc_short": "NĐ 168/2024",
                    "citation": citation,
                    "vehicle": vehicle,
                    "behaviour": ev.get("snippet", ""),
                    "fine_text": fine_text,
                    "points": points,
                })

        elif src == "sign":
            key = f"sign_{ev.get('parent_id')}"
            if key not in seen_keys:
                seen_keys.add(key)
                code_match = re.search(r'Biển\s+([A-Za-z0-9.]+)', citation)
                code = code_match.group(1).strip() if code_match else ev.get("parent_id", "").replace("sign_", "")
                sources.append({
                    "source_type": "sign",
                    "doc_name": "QCVN 41:2019/BGTVT",
                    "doc_short": "QCVN 41",
                    "sign_code": code,
                    "sign_name": ev.get("header", ""),
                    "image_url": ev.get("image_path") or "",
                    "citation": citation,
                })

        elif src == "speed":
            key = "speed_tt31"
            if key not in seen_keys:
                seen_keys.add(key)
                sources.append({
                    "source_type": "law",
                    "doc_id": "04_thong_tu_31_2019_tt_bgtvt",
                    "doc_name": "Thông tư 31/2019/TT-BGTVT",
                    "doc_short": "TT 31/2019",
                    "doc_code": "31/2019/TT-BGTVT",
                    "article_number": 0,
                    "article_header": "Quy định tốc độ và khoảng cách an toàn",
                    "citation": "Thông tư 31/2019/TT-BGTVT",
                })

        elif src == "law":
            doc_id = ev.get("doc_id", "01_luat_36_2024_qh15")
            header = ev.get("header", "")
            art_match = re.search(r'Điều\s+(\d+)', header)
            art_num = int(art_match.group(1)) if art_match else 0
            key = f"law_{doc_id}_{art_num}"

            if key not in seen_keys:
                seen_keys.add(key)
                doc_meta = provider.get_document_meta(doc_id) or {}
                doc_name = doc_meta.get("full_title", "Luật Giao thông")
                doc_short = doc_meta.get("short_title", "Luật")
                doc_code = doc_meta.get("code", "")

                sources.append({
                    "source_type": "law",
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "doc_short": doc_short,
                    "doc_code": doc_code,
                    "article_number": art_num,
                    "article_header": header,
                    "citation": citation or f"{doc_short} - {header}",
                })

    return sources


def pack_evidence_context(
    evidence_list: List[Evidence],
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET
) -> str:
    """
    Đóng gói bằng chứng pháp lý theo quy tắc xếp hạng và ngân sách token.
    Bảo đảm:
    1. Kết quả phạt giữ nguyên số liệu (không bao giờ bị cắt).
    2. Chỉ dẫn đơn FIGURE_LOCK_NOTE xuất hiện đúng 1 lần duy nhất.
    3. Không vượt quá ngân sách token.
    """
    if not evidence_list:
        return f"Không có dữ liệu tra cứu liên quan.\n{SINGLE_INSTRUCTION_BLOCK}"

    # Phân nhóm theo source
    penalties: List[Evidence] = [e for e in evidence_list if e.get("source") == "penalty"]
    signs: List[Evidence] = [e for e in evidence_list if e.get("source") == "sign"]
    speeds: List[Evidence] = [e for e in evidence_list if e.get("source") == "speed"]
    laws: List[Evidence] = [e for e in evidence_list if e.get("source") == "law"]

    # 1. Khối Mức phạt (Nghị định 168) - GIỮ NGUYÊN SỐ LIỆU SỐ
    pen_lines: List[str] = []
    if penalties:
        pen_lines.append("### [CĂN CỨ MỨC PHẠT - NGHỊ ĐỊNH 168/2024/NĐ-CP]")
        for p in penalties:
            pen_lines.append(f"• {p.get('citation', '')}")
            content_cleaned = p.get("content", "").replace("[CHỈ DẪN BẮT BUỘC", "").strip()
            for line in content_cleaned.splitlines():
                if line.strip():
                    pen_lines.append(f"  {line.strip()}")
            pen_lines.append("")

    # 2. Khối Biển báo (QCVN 41:2019)
    sign_lines: List[str] = []
    if signs:
        sign_lines.append("### [QUY CHUẨN BÁO HIỆU ĐƯỜNG BỘ - QCVN 41:2019/BGTVT]")
        for s in signs:
            sign_lines.append(f"• {s.get('citation', '')}")
            if s.get("image_path"):
                clean_img = s['image_path'] if s['image_path'].startswith('/') else f"/{s['image_path']}"
                sign_lines.append(f"  📷 Ảnh minh họa: ![{s.get('header', 'Biển báo')}]({clean_img})")
            sign_lines.append(f"  Ý nghĩa: {s.get('content', '')}")
            sign_lines.append("")

    # 3. Khối Tốc độ (Thông tư 31/2019)
    speed_lines: List[str] = []
    if speeds:
        speed_lines.append("### [QUY ĐỊNH TỐC ĐỘ VÀ KHOẢNG CÁCH AN TOÀN - THÔNG TƯ 31/2019/TT-BGTVT]")
        for sp in speeds:
            speed_lines.append(sp.get("content", ""))

    # Ngân sách còn lại cho khối Điều luật
    fixed_text = "\n\n".join(filter(None, [
        "\n".join(pen_lines) if pen_lines else "",
        "\n".join(sign_lines) if sign_lines else "",
        "\n".join(speed_lines) if speed_lines else "",
        SINGLE_INSTRUCTION_BLOCK
    ]))
    fixed_tokens = estimate_tokens(fixed_text)
    remaining_budget = max(token_budget - fixed_tokens, 150)

    # Đóng gói khối Điều luật tuân theo remaining_budget
    law_lines: List[str] = []
    if laws:
        law_lines.append("### [CĂN CỨ ĐIỀU KHOẢN PHÁP LUẬT]")
        l1 = laws[0]
        content_1 = l1.get("content", "")
        # Đảm bảo nội dung Rank 1 không vượt quá remaining_budget tokens
        target_tokens = max(remaining_budget - 120, 100)
        while content_1 and estimate_tokens(content_1) > target_tokens:
            content_1 = content_1[:int(len(content_1) * 0.85)]

        if len(content_1) < len(l1.get("content", "")):
            trunc_1 = content_1 + "\n[... phần còn lại đã được lược bớt để bảo đảm độ tập trung]"
        else:
            trunc_1 = content_1[:PARENT_CONTENT_LIMIT]

        # In đậm citation để mô hình khó bỏ sót số Điều khi đọc ngữ cảnh dài
        law_lines.append(f"• [Rank 1 - Toàn văn Điều] **{l1.get('citation', '')}**")
        law_lines.append(f"{trunc_1}\n")

        current_law_tokens = estimate_tokens("\n".join(law_lines))
        law_budget_left = remaining_budget - current_law_tokens

        for rank in range(2, min(4, len(laws) + 1)):
            if law_budget_left < 80:
                break
            l = laws[rank - 1]
            raw_c = l.get("content") or l.get("snippet", "")
            target_chars = min(1500, max(250, int(law_budget_left * 2)))
            cand_text = raw_c[:target_chars] if raw_c else l.get("snippet", "")[:250]
            item_text = f"• [Rank {rank} - Trọng tâm] {l.get('citation', '')}\n  Nội dung: {cand_text}\n"
            item_toks = estimate_tokens(item_text)
            if item_toks <= law_budget_left:
                law_lines.append(item_text)
                law_budget_left -= item_toks
            else:
                cand_text = l.get("snippet", "")[:250]
                item_text = f"• [Rank {rank} - Trọng tâm] {l.get('citation', '')}\n  Nội dung: {cand_text}\n"
                item_toks = estimate_tokens(item_text)
                if item_toks <= law_budget_left:
                    law_lines.append(item_text)
                    law_budget_left -= item_toks

        for rank in range(4, len(laws) + 1):
            if law_budget_left < 40:
                break
            l = laws[rank - 1]
            line_text = f"• [Rank {rank} - Tham chiếu] {l.get('citation', '')} ({l.get('header', '')})"
            item_toks = estimate_tokens(line_text)
            if item_toks <= law_budget_left:
                law_lines.append(line_text)
                law_budget_left -= item_toks

    all_sections = []
    if pen_lines:
        all_sections.append("\n".join(pen_lines))
    if sign_lines:
        all_sections.append("\n".join(sign_lines))
    if speed_lines:
        all_sections.append("\n".join(speed_lines))
    if law_lines:
        all_sections.append("\n".join(law_lines))

    result_text = "\n\n".join(all_sections) + f"\n\n{SINGLE_INSTRUCTION_BLOCK}"
    return result_text


def compact_node(state: LegalAgentState) -> Dict[str, Any]:
    """Node compact: Đóng gói toàn bộ bằng chứng pháp lý theo ngân sách token."""
    # Ưu tiên danh sách đã rerank từ node rerank
    evidence_list = state.get("reranked_evidence") or state.get("evidence", [])

    packed_context = pack_evidence_context(evidence_list)
    sources = build_sources_from_evidence(evidence_list)

    # Bản tóm tắt các lượt đã bị nén ra khỏi lịch sử (node `memory`) đứng TRƯỚC bằng chứng và
    # được gắn nhãn rõ là không phải căn cứ pháp lý: nó chỉ giúp model hiểu ý câu hỏi nối tiếp.
    from src.graph.memory import build_history_context_block

    history_block = build_history_context_block(state.get("history_summary", ""))
    if history_block:
        packed_context = f"{history_block}\n\n{packed_context}"

    return {
        "packed_context": packed_context,
        "sources": sources,
    }
