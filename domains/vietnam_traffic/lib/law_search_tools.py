"""
TẬP HỢP CÁC CÔNG CỤ TÌM KIẾM & TRA CỨU PHÁP LUẬT GIAO THÔNG CHO AI AGENT:
1. penalty_lookup: Tra cứu mức phạt tiền (VNĐ), tước GPLX, trừ điểm theo Nghị định 168/2024/NĐ-CP
2. traffic_sign_lookup: Tra cứu biển báo & vạch kẻ đường theo QCVN 41:2019/BGTVT (kèm ảnh minh họa Markdown)
3. speed_limit_lookup: Tra cứu tốc độ tối đa và khoảng cách an toàn theo Thông tư 31/2019/TT-BGTVT
4. keyword_search: Tìm kiếm chính xác từ khóa, số hiệu bằng lái (C1, A1, B), con số (50cc, 12 điểm)
5. semantic_search: Tìm kiếm ngữ nghĩa sâu (Dense Vector Search 3072 chiều) trên toàn bộ 6 văn bản
6. get_article: Lấy toàn văn chi tiết của một Điều luật cụ thể trong các văn bản pháp luật
7. list_chapters: Xem danh mục 9 Chương của Luật 36/2024/QH15
"""

import os
import sys
import json
import re
from typing import List, Dict, Any, Optional
import numpy as np

from domains.vietnam_traffic.lib.penalty_lookup import PenaltyLookup
from domains.vietnam_traffic.lib.tool_contract import (
    AGENT_ONLY_TAG,
    NO_ARTICLE_MATCH_HEADER,
    NO_KEYWORD_MATCH_HEADER,
)
from src.paths import project_root

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PARENT_CONTENT_LIMIT = 3500

# Phạm vi văn bản mặc định cho semantic_search: toàn bộ 6 văn bản pháp luật giao thông
DEFAULT_SEARCH_DOCS = "all"


class TrafficLawTools:
    def __init__(self):
        self.base_dir = project_root()
        self.processed_dir = os.path.join(self.base_dir, "data", "processed")

        self.structured_json_path = os.path.join(self.processed_dir, "law_36_2024_structured.json")
        self.rag_chunks_path = os.path.join(self.processed_dir, "rag_chunks.jsonl")
        self.semantic_chunks_path = os.path.join(self.processed_dir, "semantic_chunks.json")
        self.semantic_index_path = os.path.join(self.processed_dir, "semantic_index.npz")
        self.semantic_parents_path = os.path.join(self.processed_dir, "semantic_parents.json")
        self.road_law_path = os.path.join(self.processed_dir, "luat_35_articles.jsonl")
        self.traffic_signs_path = os.path.join(self.processed_dir, "traffic_signs_catalog.json")
        self.speed_matrix_path = os.path.join(self.processed_dir, "speed_limits_matrix.json")

        self.law_tree = {}
        self.articles_by_num = {}
        self.articles_list = []
        self.road_law_articles = {}
        self.traffic_signs = {}
        self.speed_matrix = {}
        self.parents_map = {}

        self.penalties = PenaltyLookup(self.base_dir)

        # Bộ truy xuất vector phân cấp (khởi tạo lười khi gọi semantic_search)
        self._vector_retriever = None
        self._vector_unavailable = False

        self._load_data()

    def _load_data(self):
        """Đọc và lập chỉ mục dữ liệu luật vào bộ nhớ"""
        if os.path.exists(self.structured_json_path):
            with open(self.structured_json_path, "r", encoding="utf-8") as f:
                self.law_tree = json.load(f)

        if os.path.exists(self.rag_chunks_path):
            with open(self.rag_chunks_path, "r", encoding="utf-8") as f:
                for line in f:
                    doc = json.loads(line)
                    art_num = doc["metadata"]["article_number"]
                    self.articles_by_num[art_num] = doc
                    self.articles_list.append(doc)

        if os.path.exists(self.road_law_path):
            with open(self.road_law_path, "r", encoding="utf-8") as f:
                for line in f:
                    doc = json.loads(line)
                    self.road_law_articles[doc["metadata"]["article_number"]] = doc

        if os.path.exists(self.traffic_signs_path):
            with open(self.traffic_signs_path, "r", encoding="utf-8") as f:
                self.traffic_signs = json.load(f)

        if os.path.exists(self.speed_matrix_path):
            with open(self.speed_matrix_path, "r", encoding="utf-8") as f:
                self.speed_matrix = json.load(f)

        if os.path.exists(self.semantic_parents_path):
            with open(self.semantic_parents_path, "r", encoding="utf-8") as f:
                self.parents_map = json.load(f)

    def _get_vector_retriever(self):
        """Khởi tạo lười (lazy) tầng truy xuất lai ghép BM25 + Vector + RRF (HybridSearch)"""
        if self._vector_retriever is not None:
            return self._vector_retriever
        if self._vector_unavailable:
            return None
        try:
            from src.retrieval.hybrid import get_hybrid_search
            index = get_hybrid_search(self.base_dir)
            if not index.available:
                raise RuntimeError("chưa có chỉ mục lai ghép vector/BM25")
            self._vector_retriever = index
        except Exception as e:
            self._vector_unavailable = True
            print(f"[Cảnh báo]: Không thể khởi tạo chỉ mục lai ghép: {e}")
            return None
        return self._vector_retriever


    # ------------------------------------------------------------------
    # 1. Tra cứu Biển Báo & Báo Hiệu Đường Bộ (QCVN 41:2019)
    # ------------------------------------------------------------------

    def traffic_sign_lookup(self, sign_code_or_name: str) -> str:
        """
        Tra cứu biển báo giao thông hoặc vạch kẻ đường theo mã hiệu (ví dụ: 'P.106a', 'P106a', 'W.201', 'Vạch 1.1')
        hoặc tên biển (ví dụ: 'cấm xe tải', 'cấm đi ngược chiều', 'vạch người đi bộ qua đường').
        Trả về tên biển, ý nghĩa sử dụng và hình ảnh minh họa Markdown (![tên](/data/images/...)).
        """
        if not sign_code_or_name:
            return "Vui lòng nhập mã biển báo hoặc tên biển báo cần tra cứu."

        query = sign_code_or_name.strip()
        query_upper = query.upper()
        query_norm = query_upper.replace(".", "").replace(" ", "")

        matched_items = []

        # 1. Tìm chính xác theo mã
        by_code = self.traffic_signs.get("by_code", {})
        if query_upper in by_code:
            matched_items.append(by_code[query_upper])
        elif query_norm in by_code:
            matched_items.append(by_code[query_norm])
        elif query in by_code:
            matched_items.append(by_code[query])

        # 2. Tìm theo tên hoặc tìm kiếm mờ trong catalog nếu chưa có
        if not matched_items:
            q_lower = query.lower()
            all_items = self.traffic_signs.get("items", [])
            for item in all_items:
                code_i = item.get("sign_code", "").upper()
                name_i = item.get("sign_name", "").lower()
                meaning_i = item.get("meaning", "").lower()

                # So khớp mã không phân biệt dấu chấm (P.106a == P106a)
                if query_norm in code_i.replace(".", "").replace(" ", ""):
                    matched_items.append(item)
                elif q_lower in name_i:
                    matched_items.append(item)
                elif len(q_lower) >= 4 and q_lower in meaning_i:
                    matched_items.append(item)

                if len(matched_items) >= 4:
                    break

        if not matched_items:
            return (
                f"=== KHÔNG TÌM THẤY BÁO HIỆU: '{sign_code_or_name}' ===\n"
                f"{AGENT_ONLY_TAG}\n"
                "Không tìm thấy biển báo hoặc vạch kẻ đường phù hợp trong QCVN 41:2019/BGTVT. "
                "Hãy thử tìm kiếm bằng từ khóa chung hơn hoặc gọi 'semantic_search' với nguyên văn câu hỏi."
            )

        output = [f"=== KẾT QUẢ TRA CỨU BÁO HIỆU ĐƯỜNG BỘ: '{sign_code_or_name}' (QCVN 41:2019/BGTVT) ==="]

        for item in matched_items[:3]:
            code = item.get("sign_code", "")
            name = item.get("sign_name", "")
            group = item.get("sign_group", "")
            meaning = item.get("meaning", "")
            citation = item.get("citation", "")
            img_path = item.get("image_path")

            block = [
                f"\n🚸 **{code}: {name}** ({group})",
                f"• Căn cứ: {citation}",
                f"• Ý nghĩa sử dụng: {meaning}"
            ]
            if img_path:
                clean_img = img_path if img_path.startswith("/") else f"/{img_path}"
                block.append(f"• **Hình ảnh minh họa**: ![{code} - {name}]({clean_img})")

            output.append("\n".join(block))

        return "\n".join(output)

    # ------------------------------------------------------------------
    # 2. Tra cứu Quy Định Tốc Độ & Khoảng Cách An Toàn (Thông tư 31/2019)
    # ------------------------------------------------------------------

    def speed_limit_lookup(self, query: str) -> str:
        """
        Tra cứu tốc độ tối đa cho phép và khoảng cách an toàn của xe cơ giới, xe máy chuyên dùng
        theo Thông tư 31/2019/TT-BGTVT (khu vực đông dân cư, ngoài khu vực đông dân cư, cao tốc, khoảng cách an toàn).
        """
        if not self.speed_matrix:
            return "Chưa nạp được dữ liệu bảng tốc độ Thông tư 31/2019/TT-BGTVT."

        q_lower = query.lower() if query else ""

        # Phát hiện ý định tra cứu
        is_distance = any(k in q_lower for k in ("khoảng cách", "cự ly", "mét", "mặt đường trơn", "sương mù"))
        is_expressway = any(k in q_lower for k in ("cao tốc", "đường cao tốc", "expressway"))
        is_non_urban = any(k in q_lower for k in ("ngoài khu", "ngoài đô thị", "ngoài dân cư", "ngoài thành"))
        is_special = any(k in q_lower for k in ("xe máy chuyên dùng", "xe gắn máy", "xe máy điện", "dưới 50cc", "50cc"))
        is_urban = any(k in q_lower for k in ("trong khu", "đông dân cư", "nội thành", "nội thị", "đô thị")) or not is_non_urban

        output = ["=== BẢNG QUY ĐỊNH TỐC ĐỘ VÀ KHOẢNG CÁCH AN TOÀN (THÔNG TƯ 31/2019/TT-BGTVT) ==="]

        if is_distance:
            dist_info = self.speed_matrix.get("safe_distances", {})
            output.append(f"\n📏 **{dist_info.get('description', 'Khoảng cách an toàn')}**:")
            for row in dist_info.get("table", []):
                output.append(f"  • Vận tốc {row['speed_range']}: Cự ly an toàn tối thiểu **{row['min_distance_m']} mét**")
            output.append(f"  • *Vận tốc dưới 60 km/h*: {dist_info.get('low_speed_rule')}")
            output.append(f"  • *Thời tiết xấu (mưa, sương mù, trơn trượt)*: {dist_info.get('bad_weather_rule')}")
            output.append("  • *Căn cứ pháp lý*: Điều 11 Thông tư 31/2019/TT-BGTVT.")
            return "\n".join(output)

        if is_expressway:
            exp_info = self.speed_matrix.get("expressway", {})
            output.append(f"\n🛣️ **{exp_info.get('description')}**:")
            output.append(f"  • Tốc độ tối đa: **{exp_info.get('max_speed_kmh')} km/h**")
            output.append(f"  • {exp_info.get('rule')}")
            output.append("  • *Căn cứ pháp lý*: Điều 9 Thông tư 31/2019/TT-BGTVT và Điều 25 Luật 36/2024/QH15.")
            return "\n".join(output)

        # Mặc định hoặc hỏi về khu vực đông dân cư
        if is_urban:
            urban = self.speed_matrix.get("urban_area", {})
            output.append(f"\n🏙️ **{urban.get('description')}**:")
            d1 = urban.get("divided_road_or_multi_lane", {})
            output.append(f"  • **{d1.get('road_type')}**: Tối đa **{d1.get('max_speed_kmh')} km/h** (áp dụng cho xe ô tô con, ô tô khách, ô tô tải, xe mô tô/xe máy).")
            d2 = urban.get("undivided_road_or_single_lane", {})
            output.append(f"  • **{d2.get('road_type')}**: Tối đa **{d2.get('max_speed_kmh')} km/h** (áp dụng cho xe ô tô con, ô tô khách, ô tô tải, xe mô tô/xe máy).")
            sp = urban.get("special_vehicles", {})
            output.append(f"  • **{', '.join(sp.get('applicable_vehicles', []))}**: Tối đa **{sp.get('max_speed_kmh')} km/h** ({sp.get('article_ref')}).")
            output.append("  • *Căn cứ pháp lý*: Điều 6 & Điều 8 Thông tư 31/2019/TT-BGTVT.")

        if is_non_urban:
            non_urban = self.speed_matrix.get("non_urban_area", {})
            output.append(f"\n🏞️ **{non_urban.get('description')}**:")
            output.append("  • **Đường đôi, đường một chiều có từ 2 làn xe cơ giới trở lên**:")
            for s in non_urban.get("divided_road", {}).get("speeds", []):
                output.append(f"    - {s['vehicles']}: Tối đa **{s['max_speed_kmh']} km/h**")
            output.append("  • **Đường hai chiều, đường một chiều có 1 làn xe cơ giới**:")
            for s in non_urban.get("undivided_road", {}).get("speeds", []):
                output.append(f"    - {s['vehicles']}: Tối đa **{s['max_speed_kmh']} km/h**")
            output.append("  • *Xe máy chuyên dùng, xe gắn máy (kể cả xe máy điện)*: Tối đa **40 km/h** (Điều 8).")
            output.append("  • *Căn cứ pháp lý*: Điều 7 & Điều 8 Thông tư 31/2019/TT-BGTVT.")

        return "\n".join(output)

    # ------------------------------------------------------------------
    # 3. Tra Cứu Mức Phạt Xử Phạt Vi Phạm (Nghị định 168/2024)
    # ------------------------------------------------------------------

    def penalty_lookup(self, violation_keyword: str) -> str:
        """
        Tra cứu mức phạt tiền, hình thức xử phạt bổ sung và số điểm GPLX bị trừ trên toàn văn
        Nghị định 168/2024/NĐ-CP (hiệu lực 01/01/2025, thay thế NĐ 100/2019 và NĐ 123/2021).
        """
        return self.penalties.lookup(violation_keyword)

    # ------------------------------------------------------------------
    # 4. Tìm kiếm từ khóa & Tìm kiếm ngữ nghĩa
    # ------------------------------------------------------------------

    def search_articles(self, keywords: str, max_results: int = 4) -> List[Dict[str, Any]]:
        """Tìm kiếm từ khóa trong danh sách Điều luật"""
        if not keywords:
            return []

        kw_clean = keywords.strip().lower()
        kw_list = [k.strip() for k in re.split(r'[,;\s]+', kw_clean) if len(k.strip()) > 1]
        if not kw_list:
            kw_list = [kw_clean]

        generic_words = {"hạng", "xe", "điều", "luật", "của", "cho", "người", "các", "loại", "quy", "định"}
        spec_kw = [k for k in kw_list if k not in generic_words] or kw_list

        matched = []
        for doc in self.articles_list:
            content_lower = doc["page_content"].lower()
            header_lower = doc["metadata"]["article_header"].lower()

            score = 0
            if kw_clean in header_lower:
                score += 50
            elif kw_clean in content_lower:
                score += 40

            for kw in spec_kw:
                if kw in header_lower:
                    score += 25
                if len(kw) <= 2:
                    c = len(re.findall(r'\b' + re.escape(kw) + r'\b', content_lower))
                else:
                    c = content_lower.count(kw)
                if c > 0:
                    score += min(c, 5) * 5

            for kw in kw_list:
                if kw in header_lower:
                    score += 5
                elif kw in content_lower:
                    score += 2

            if score > 0:
                matched.append((score, doc))

        matched.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, doc in matched[:max_results]:
            meta = doc["metadata"]
            
            # Chấm điểm độ phù hợp của từng dòng để chọn trích đoạn chính xác nhất
            scored_lines = []
            for idx, line in enumerate(doc["page_content"].splitlines()):
                l_strip = line.strip()
                if not l_strip:
                    continue
                l_lower = l_strip.lower()
                l_score = 0
                if kw_clean in l_lower:
                    l_score += 100
                for kw in spec_kw:
                    if len(kw) <= 2:
                        if re.search(r'\b' + re.escape(kw) + r'\b', l_lower):
                            l_score += 40
                    elif kw in l_lower:
                        l_score += 20
                for kw in kw_list:
                    if kw in l_lower:
                        l_score += 5
                if l_score > 0:
                    scored_lines.append((l_score, idx, l_strip))

            scored_lines.sort(key=lambda x: (x[0], -x[1]), reverse=True)
            top_picked = sorted(scored_lines[:4], key=lambda x: x[1])
            snippets = [item[2] for item in top_picked]

            if not snippets:
                snippets = [doc["page_content"][:250]]

            results.append({
                "article_number": meta["article_number"],
                "article_header": meta["article_header"],
                "chapter_id": meta.get("chapter_id", 1),
                "chapter_title": meta.get("chapter_title", ""),
                "score": score,
                "snippets": snippets
            })
        return results

    def keyword_search(self, keywords: str, max_results: int = 4) -> str:
        """
        Tìm kiếm chính xác các Điều luật trong Luật 36/2024 chứa từ khóa hoặc cụm từ chỉ định (A1, C1, B, 12 điểm...).
        """
        if not keywords:
            return "Không có từ khóa tìm kiếm."

        results = self.search_articles(keywords, max_results)
        if not results:
            return (
                f"{NO_KEYWORD_MATCH_HEADER} '{keywords}' ===\n"
                "Không có Điều luật nào trong Luật 36/2024/QH15 chứa từ khóa này.\n\n"
                f"{AGENT_ONLY_TAG}\n"
                "Hãy thử 'semantic_search' với nguyên văn câu hỏi để tìm kiếm trong cả 6 văn bản pháp luật."
            )

        output = [f"=== KẾT QUẢ TÌM KIẾM TỪ KHÓA: '{keywords}' ==="]
        for r in results:
            snippet = "\n  ... ".join(r["snippets"])
            output.append(
                f"\n📖 {r['article_header']} (Chương {r['chapter_id']}: {r['chapter_title']})\n"
                f"  Trích đoạn quan trọng:\n  {snippet}"
            )
        return "\n".join(output)

    def semantic_search(self, question: str, top_k: int = 3, doc_scope: str = DEFAULT_SEARCH_DOCS) -> str:
        """
        Tìm kiếm ngữ nghĩa (Dense Vector Search 3072 chiều) phủ toàn bộ 6 văn bản:
        - Luật 36/2024 (Quy tắc, bằng lái, điểm GPLX)
        - Luật 35/2024 (Đường bộ, cao tốc, vận tải)
        - Thông tư 31/2019 (Tốc độ & khoảng cách an toàn)
        - Thông tư 73/2024 (Tuần tra CSGT, dừng xe, VNeID)
        - QCVN 41:2019 (Biển báo, vạch kẻ đường kèm ảnh)
        - Nghị định 168/2024 (Chế tài mức phạt)

        Kết quả LUÔN kèm dòng độ tin cậy ở đầu. Tầng truy xuất không tự ý trả rỗng khi thấy
        điểm thấp nữa — nó báo tín hiệu và để Agent quyết định tra lại, mở rộng phạm vi, hay
        nói thẳng là kho tài liệu không bao phủ câu hỏi.
        """
        if not question:
            return "Không có nội dung để tìm kiếm."

        retriever = self._get_vector_retriever()
        if retriever is None:
            return (
                "[Chú ý: Chỉ mục vector không khả dụng, chuyển sang tìm kiếm từ khóa thay thế]\n"
                + self.keyword_search(question)
            )

        try:
            scope = None if doc_scope == "all" else [doc_scope]
            kept, confidence, scope_signal = retriever.retrieve_articles_with_confidence(
                question, doc_ids=scope, top_k=top_k
            )
        except Exception as e:
            return (
                f"[Chú ý: Lỗi truy xuất ({e}), chuyển sang tìm kiếm từ khóa]\n"
                + self.keyword_search(question)
            )

        if not kept:
            return (
                f"{NO_ARTICLE_MATCH_HEADER} '{question}' ===\n"
                f"{AGENT_ONLY_TAG}\n"
                "Chỉ mục không trả về ứng viên nào. Hãy thử lại bằng thuật ngữ pháp lý khác, "
                "hoặc nói rõ với người dùng là chưa tìm thấy quy định liên quan."
            )

        output = [f"=== KẾT QUẢ TRA CỨU NGỮ NGHĨA CHO: '{question}' ===", confidence.header_vi()]
        scope_header = scope_signal.header_vi()
        if scope_header:
            output.append(scope_header)
        for rank, r in enumerate(kept):
            doc_name = r.get("doc_name", "")
            header = r.get("article_header", "")
            score = r.get("score", 0)
            img_path = r.get("image_path")

            head_str = f"\n📖 [{doc_name}] {header} — độ liên quan tương đối {score}%"
            if img_path:
                clean_img = img_path if img_path.startswith("/") else f"/{img_path}"
                head_str += f"\n  📷 Ảnh minh họa: ![{header}]({clean_img})"

            if rank == 0:
                body = r.get("page_content", "")
                if len(body) > PARENT_CONTENT_LIMIT:
                    body = body[:PARENT_CONTENT_LIMIT] + "\n[... nội dung còn lại bị cắt bớt]"
                output.append(f"{head_str}\n  Toàn văn nội dung:\n{body}")
            else:
                clauses = r.get("key_clauses", [])
                snippet = "\n  ... ".join(c.strip() for c in clauses[:2] if c)
                output.append(f"{head_str}\n  Nội dung tóm tắt:\n  {snippet}")

        return "\n".join(output)

    # ------------------------------------------------------------------
    # 5. Xem Toàn Văn Điều Luật & Danh Mục Chương
    # ------------------------------------------------------------------

    def get_article(self, article_number: int, doc_id: str = "01_luat_36_2024_qh15") -> str:
        """
        Lấy toàn văn nội dung chi tiết của một Điều luật cụ thể trong các văn bản pháp luật.
        """
        try:
            art_num = int(article_number)
        except (ValueError, TypeError):
            return f"Số Điều luật không hợp lệ: {article_number}"

        # 1. Tìm trong Luật 36
        if "36" in doc_id and art_num in self.articles_by_num:
            doc = self.articles_by_num[art_num]
            return (
                f"=== TOÀN VĂN {doc['metadata']['article_header']} (Luật số 36/2024/QH15) ===\n"
                f"Chương {doc['metadata'].get('chapter_id', '')}: {doc['metadata'].get('chapter_title', '')}\n\n"
                f"{doc['page_content']}"
            )

        # 2. Tìm trong Luật 35
        if "35" in doc_id and art_num in self.road_law_articles:
            doc = self.road_law_articles[art_num]
            return (
                f"=== TOÀN VĂN {doc['metadata']['article_header']} (Luật Đường bộ số 35/2024/QH15) ===\n\n"
                f"{doc['page_content']}"
            )

        # 3. Tìm trong parents_map
        for pid, p in self.parents_map.items():
            if p.get("article_number") == art_num and (not doc_id or doc_id in p.get("doc_id", "")):
                return (
                    f"=== TOÀN VĂN {p.get('article_header')} ({p.get('doc_name')}) ===\n\n"
                    f"{p.get('content')}"
                )

        return f"Không tìm thấy Điều {art_num} trong văn bản {doc_id}."

    def list_chapters(self) -> str:
        """Liệt kê danh mục 9 Chương của Luật 36/2024/QH15"""
        lines = ["=== DANH MỤC CÁC CHƯƠNG TRONG LUẬT SỐ 36/2024/QH15 ==="]
        for ch in self.law_tree.get("chapters", []):
            lines.append(f"• {ch.get('chapter_roman')}: {ch.get('chapter_title')} ({ch.get('article_range')})")
        return "\n".join(lines)


# SCHEMA FUNCTION CALLING DÀNH CHO AI AGENT


# TOOLS_SCHEMA KHÔNG còn ở đây.
#
# Khai báo công cụ (tên, mô tả, JSON Schema tham số) đã chuyển sang `domains/vietnam_traffic/
# domain.yaml`, và hàm thực thi sang `domains/vietnam_traffic/tools.py`. Nhờ vậy engine không
# giữ danh sách công cụ cố định nào: đổi miền là đổi cả bộ công cụ mà không sửa mã engine.
#
# Lớp `TrafficLawTools` ở trên vẫn là nơi chứa dữ liệu và nghiệp vụ tra cứu của miền giao thông.
