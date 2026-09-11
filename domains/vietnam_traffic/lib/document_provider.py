"""
DocumentProvider: Bộ quản lý & phục vụ dữ liệu tập trung cho 6 văn bản pháp luật
giao thông và kho dữ liệu tiện ích (Biển báo QCVN 41, Tốc độ TT 31, Vạch kẻ đường, Điểm GPLX).
"""

import os
import sys
import json
import re
from typing import List, Dict, Any, Optional

from src.paths import project_root

BASE_DIR = project_root()
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
PDF_DIR = os.path.join(BASE_DIR, "data", "digitized_pdf")


def _documents_metadata() -> List[Dict[str, Any]]:
    """
    Danh mục tài liệu cho lớp ứng dụng (trang tra cứu văn bản, API /api/documents).

    Trước đây là một hằng số 110 dòng liệt kê cứng 6 văn bản giao thông. Giờ dựng từ Domain Pack
    đang hoạt động: thêm hay bớt tài liệu chỉ cần sửa `domains/<id>/domain.yaml`.
    """
    from src.domain.registry import get_active_domain

    documents = []
    for doc in get_active_domain().spec.corpus.documents:
        entry: Dict[str, Any] = {
            "id": doc.id,
            "code": doc.code,
            "short_title": doc.short_title,
            "full_title": doc.full_title,
            "doc_type": _DOC_TYPE_LABELS.get(doc.doc_type, doc.doc_type),
            "summary": doc.summary,
        }
        entry.update(doc.metadata)
        documents.append(entry)
    return documents


# Nhãn hiển thị của từng loại tài liệu. Miền khai báo mã loại (`luat`, `nghi_dinh`...); lớp
# giao diện cần tên đầy đủ tiếng Việt.
_DOC_TYPE_LABELS = {
    "luat": "Luật",
    "nghi_dinh": "Nghị định",
    "thong_tu": "Thông tư",
    "quy_chuan": "Quy chuẩn",
}


class DocumentProvider:
    """Kho dữ liệu và dịch vụ tra cứu đa văn bản pháp luật giao thông"""

    def __init__(self, base_dir: str = BASE_DIR):
        self.base_dir = base_dir
        self.processed_dir = os.path.join(base_dir, "data", "processed")
        self.pdf_dir = os.path.join(base_dir, "data", "digitized_pdf")

        self.documents_meta = {d["id"]: d for d in _documents_metadata()}
        self._trees: Dict[str, dict] = {}
        self._articles_content: Dict[str, Dict[int, dict]] = {}
        self._traffic_signs: Optional[dict] = None
        self._speed_matrix: Optional[dict] = None
        self._road_markings: Optional[List[dict]] = None
        self._penalty_chunks: Optional[List[dict]] = None

        self._load_all()

    def _load_all(self):
        """Khởi nạp toàn bộ cấu trúc và bài viết của 6 văn bản vào RAM"""
        for doc_meta in _documents_metadata():
            doc_id = doc_meta["id"]
            st_file = doc_meta["structure_file"]
            st_path = os.path.join(self.processed_dir, st_file)
            if os.path.exists(st_path):
                try:
                    with open(st_path, "r", encoding="utf-8") as f:
                        self._trees[doc_id] = json.load(f)
                except Exception as e:
                    print(f"[DocumentProvider] Lỗi nạp cây văn bản {doc_id}: {e}")

            # Nạp bài viết
            self._articles_content[doc_id] = {}
            art_file = doc_meta.get("articles_file")
            if art_file:
                art_path = os.path.join(self.processed_dir, art_file)
                if os.path.exists(art_path):
                    try:
                        with open(art_path, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                item = json.loads(line)
                                art_num = item.get("metadata", {}).get("article_number")
                                if art_num is not None:
                                    try:
                                        art_num = int(art_num)
                                        self._articles_content[doc_id][art_num] = item
                                    except ValueError:
                                        pass
                    except Exception as e:
                        print(f"[DocumentProvider] Lỗi nạp bài viết {art_file}: {e}")

        # Xử lý đặc biệt cho Nghị định 168 (toàn văn lưu trực tiếp trong các Khoản của file cấu trúc)
        nd168_id = "03_nghi_dinh_168_2024_nd_cp"
        if nd168_id in self._trees:
            tree = self._trees[nd168_id]
            for ch in tree.get("chapters", []):
                for art in ch.get("articles", []):
                    art_num_raw = art.get("article_number")
                    try:
                        art_num = int(art_num_raw)
                    except (ValueError, TypeError):
                        continue

                    content_lines = [
                        f"=== Điều {art_num}. {art.get('article_title', '')} ===",
                        f"Văn bản: {doc_meta.get('full_title', 'Nghị định 168/2024/NĐ-CP')}",
                        f"Chương: {ch.get('chapter_roman', '')} - {ch.get('chapter_title', '')}",
                        ""
                    ]
                    if art.get("intro"):
                        content_lines.append(art["intro"])
                        content_lines.append("")

                    for cl in art.get("clauses", []):
                        cl_num = cl.get("clause_number", "")
                        cl_text = cl.get("text", "")
                        content_lines.append(f"{cl_num}. {cl_text}")
                        for pt in cl.get("points", []):
                            pt_letter = pt.get("point_letter", "")
                            pt_text = pt.get("text", "")
                            content_lines.append(f"   {pt_letter}) {pt_text}")
                        content_lines.append("")

                    self._articles_content[nd168_id][art_num] = {
                        "id": f"nd168_art_{art_num}",
                        "doc_id": nd168_id,
                        "doc_name": "Nghị định 168/2024/NĐ-CP",
                        "page_content": "\n".join(content_lines).strip(),
                        "metadata": {
                            "article_number": art_num,
                            "article_title": art.get("article_title", ""),
                            "article_header": f"Điều {art_num}. {art.get('article_title', '')}",
                            "chapter_roman": ch.get("chapter_roman", ""),
                            "chapter_title": ch.get("chapter_title", ""),
                            "clause_count": len(art.get("clauses", []))
                        },
                        "structured_clauses": art.get("clauses", [])
                    }

    def list_documents(self) -> List[dict]:
        """Trả về metadata danh sách 6 văn bản kèm số lượng thực tế đã nạp"""
        results = []
        for d in _documents_metadata():
            doc_id = d["id"]
            tree = self._trees.get(doc_id, {})
            loaded_arts = len(self._articles_content.get(doc_id, {}))
            chapters_count = len(tree.get("chapters", []))
            item = dict(d)
            item["loaded_articles"] = loaded_arts
            item["loaded_chapters"] = chapters_count
            results.append(item)
        return results

    def get_document_meta(self, doc_id: str) -> Optional[dict]:
        return self.documents_meta.get(doc_id)

    def get_chapters(self, doc_id: str) -> dict:
        """Trả về cây mục lục chương & điều cho một văn bản"""
        meta = self.documents_meta.get(doc_id)
        if not meta:
            # Fallback nếu truyền short id như 'luat_36'
            for d in _documents_metadata():
                if doc_id in d["id"]:
                    meta = d
                    doc_id = d["id"]
                    break

        if not meta:
            raise KeyError(f"Không tìm thấy văn bản: {doc_id}")

        tree = self._trees.get(doc_id, {})
        chapters_out = []
        for ch in tree.get("chapters", []):
            arts = []
            for a in ch.get("articles", []):
                try:
                    num = int(a.get("article_number", 0))
                except (ValueError, TypeError):
                    continue
                arts.append({
                    "article_number": num,
                    "article_title": a.get("article_title", "")
                })

            chapters_out.append({
                "chapter_id": ch.get("chapter_id", ch.get("chapter_roman", "")),
                "chapter_roman": ch.get("chapter_roman", ""),
                "chapter_title": ch.get("chapter_title", ""),
                "article_range": ch.get("article_range", ""),
                "articles": arts
            })

        return {
            "doc_id": doc_id,
            "doc_code": meta["code"],
            "doc_name": meta["full_title"],
            "short_title": meta["short_title"],
            "date_effective": meta["effective_date"],
            "authority": meta["authority"],
            "chapters": chapters_out
        }

    def get_article(self, doc_id: str, article_number: int) -> dict:
        """Trả về toàn văn và metadata của một Điều luật cụ thể"""
        # Resolve doc_id alias
        if doc_id not in self.documents_meta:
            for d in _documents_metadata():
                if doc_id in d["id"]:
                    doc_id = d["id"]
                    break

        meta = self.documents_meta.get(doc_id, {})
        arts = self._articles_content.get(doc_id, {})
        art = arts.get(int(article_number))

        if not art:
            # Tìm trong cây cấu trúc nếu chưa có trong jsonl
            tree = self._trees.get(doc_id, {})
            found = None
            found_ch = None
            for ch in tree.get("chapters", []):
                for a in ch.get("articles", []):
                    if int(a.get("article_number", -1)) == int(article_number):
                        found = a
                        found_ch = ch
                        break
                if found:
                    break

            if found:
                header = f"Điều {article_number}. {found.get('article_title', '')}"
                content = f"=== {header} ===\n\n[Đang cập nhật toàn văn từ tệp nguồn]"
                return {
                    "doc_id": doc_id,
                    "doc_name": meta.get("short_title", ""),
                    "article_number": article_number,
                    "article_header": header,
                    "chapter_title": f"{found_ch.get('chapter_roman', '')}: {found_ch.get('chapter_title', '')}",
                    "content": content
                }
            raise KeyError(f"Không tìm thấy Điều {article_number} trong văn bản {doc_id}")

        art_meta = art.get("metadata", {})
        header = art_meta.get("article_header") or f"Điều {article_number}. {art_meta.get('article_title', '')}"
        chapter_str = f"{art_meta.get('chapter_roman', '')} {art_meta.get('chapter_title', '')}".strip()
        if not chapter_str and art_meta.get("chapter_id"):
            chapter_str = f"Chương {art_meta.get('chapter_id')}: {art_meta.get('chapter_title', '')}".strip()

        return {
            "doc_id": doc_id,
            "doc_name": meta.get("short_title", ""),
            "doc_code": meta.get("code", ""),
            "article_number": article_number,
            "article_header": header,
            "chapter_title": chapter_str,
            "content": art.get("page_content", ""),
            "structured_clauses": art.get("structured_clauses")
        }

    def search_articles(self, query: str, doc_id: Optional[str] = None, limit: int = 15) -> List[dict]:
        """Tìm kiếm từ khóa trong các Điều luật"""
        query_words = [w.lower() for w in query.strip().split() if len(w) > 1]
        if not query_words:
            return []

        search_docs = [doc_id] if doc_id and doc_id in self._articles_content else list(self._articles_content.keys())
        results = []

        for did in search_docs:
            dmeta = self.documents_meta.get(did, {})
            arts = self._articles_content.get(did, {})
            for art_num, art in arts.items():
                content = art.get("page_content", "")
                header = art.get("metadata", {}).get("article_header", f"Điều {art_num}")
                content_lower = content.lower()
                header_lower = header.lower()

                matches = sum(1 for w in query_words if w in content_lower)
                header_matches = sum(3 for w in query_words if w in header_lower)
                score = matches + header_matches

                if score > 0:
                    snippets = []
                    lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
                    for ln in lines:
                        if any(w in ln.lower() for w in query_words):
                            snippets.append(ln)
                            if len(snippets) >= 2:
                                break
                    if not snippets and lines:
                        snippets = [lines[0][:150]]

                    results.append({
                        "doc_id": did,
                        "doc_name": dmeta.get("short_title", did),
                        "article_number": art_num,
                        "article_header": header,
                        "chapter_title": art.get("metadata", {}).get("chapter_title", ""),
                        "snippets": snippets,
                        "score": score
                    })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Dữ liệu Tiện ích: Biển báo, Tốc độ, Vạch kẻ, Điểm bằng lái
    # ------------------------------------------------------------------

    def get_traffic_signs(self, group: Optional[str] = None, query: Optional[str] = None, limit: int = 400) -> dict:
        """Trả về 363 biển báo giao thông QCVN 41:2019"""
        if self._traffic_signs is None:
            path = os.path.join(self.processed_dir, "traffic_signs_catalog.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._traffic_signs = json.load(f)
            else:
                self._traffic_signs = {"items": [], "groups": []}

        items = self._traffic_signs.get("items", [])
        q = (query or "").strip().lower()
        grp = (group or "").strip()

        filtered = []
        for item in items:
            if grp and item.get("sign_group") != grp and grp.lower() not in item.get("sign_group", "").lower():
                continue
            if q:
                match_code = q in item.get("sign_code", "").lower() or q.replace(".", "") in item.get("sign_code", "").lower().replace(".", "")
                match_name = q in item.get("sign_name", "").lower()
                match_meaning = q in item.get("meaning", "").lower()
                if not (match_code or match_name or match_meaning):
                    continue
            filtered.append(item)

        # Lấy danh sách nhóm biển duy nhất
        groups = sorted(list(set(it.get("sign_group", "") for it in items if it.get("sign_group"))))

        return {
            "total": len(items),
            "returned": len(filtered[:limit]),
            "groups": groups,
            "items": filtered[:limit]
        }

    def get_speed_matrix(self) -> dict:
        """Ma trận tốc độ và cự ly an toàn Thông tư 31/2019"""
        if self._speed_matrix is None:
            path = os.path.join(self.processed_dir, "speed_limits_matrix.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._speed_matrix = json.load(f)
            else:
                self._speed_matrix = {}
        return self._speed_matrix

    def get_road_markings(self, query: Optional[str] = None) -> List[dict]:
        """Danh mục 43 vạch kẻ đường QCVN 41:2019"""
        if self._road_markings is None:
            self._road_markings = []
            path = os.path.join(self.processed_dir, "road_markings.jsonl")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            self._road_markings.append(json.loads(line))

        if not query:
            return self._road_markings

        q = query.strip().lower()
        return [
            m for m in self._road_markings
            if q in m.get("marking_code", "").lower()
            or q in m.get("marking_name", "").lower()
            or q in m.get("meaning", "").lower()
        ]

    def get_license_points_data(self) -> dict:
        """Hệ thống 12 điểm bằng lái và các mức trừ điểm theo NĐ 168 & Luật 36"""
        if self._penalty_chunks is None:
            self._penalty_chunks = []
            path = os.path.join(self.processed_dir, "penalty_chunks.jsonl")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            self._penalty_chunks.append(json.loads(line))

        points_buckets = {
            "2_points": [],
            "3_points": [],
            "6_points": [],
            "12_points": []
        }

        for item in self._penalty_chunks:
            pts = item.get("points_deducted")
            if pts == 2:
                points_buckets["2_points"].append(item)
            elif pts == 3:
                points_buckets["3_points"].append(item)
            elif pts == 6:
                points_buckets["6_points"].append(item)
            elif pts == 12:
                points_buckets["12_points"].append(item)

        return {
            "total_violations_with_points": sum(len(v) for v in points_buckets.values()),
            "groups": {
                "2_points": {
                    "points": 2,
                    "label": "Trừ 2 điểm",
                    "severity": "Nhẹ / Phổ biến",
                    "color": "amber",
                    "count": len(points_buckets["2_points"]),
                    "description": "Các lỗi phổ biến như không thắt dây an toàn, dùng điện thoại khi lái xe, dừng đỗ sai quy định...",
                    "items": points_buckets["2_points"]
                },
                "3_points": {
                    "points": 3,
                    "label": "Trừ 3 điểm",
                    "severity": "Trung bình",
                    "color": "orange",
                    "count": len(points_buckets["3_points"]),
                    "description": "Chạy quá tốc độ từ 10 - 20 km/h, đi vào đường cấm, đi ngược chiều đường một chiều...",
                    "items": points_buckets["3_points"]
                },
                "6_points": {
                    "points": 6,
                    "label": "Trừ 6 điểm",
                    "severity": "Nghiêm trọng",
                    "color": "rose",
                    "count": len(points_buckets["6_points"]),
                    "description": "Chạy quá tốc độ từ 20 - 35 km/h, nồng độ cồn mức 1 (chưa vượt quá 50mg/100ml máu hoặc 0.25mg/1l khí thở)...",
                    "items": points_buckets["6_points"]
                },
                "12_points": {
                    "points": 12,
                    "label": "Trừ 12 điểm (Hết điểm)",
                    "severity": "Đặc biệt nghiêm trọng",
                    "color": "red",
                    "count": len(points_buckets["12_points"]),
                    "description": "Nồng độ cồn mức 2 & 3, ma túy, chạy lùi/ngược chiều trên cao tốc, lạng lách đánh võng... Bị tước quyền lái xe và phải thi lại lý thuyết.",
                    "items": points_buckets["12_points"]
                }
            },
            "rules": [
                {
                    "title": "Tổng điểm ban đầu",
                    "detail": "Mỗi giấy phép lái xe có 12 điểm/năm (Điều 58 Luật 36/2024/QH15, hiệu lực 01/01/2025)."
                },
                {
                    "title": "Điều kiện phục hồi điểm tự động",
                    "detail": "Nếu trong 12 tháng kể từ ngày bị trừ điểm gần nhất mà không bị trừ thêm điểm nào thì được phục hồi đủ 12 điểm."
                },
                {
                    "title": "Xử lý khi bị trừ hết 12 điểm",
                    "detail": "Người có GPLX bị trừ hết điểm không được phép điều khiển phương tiện. Phải tham gia kiểm tra lại kiến thức pháp luật trật tự ATGTĐB sau ít nhất 06 tháng kể từ ngày hết điểm, nếu đạt yêu cầu mới được phục hồi đủ 12 điểm."
                }
            ]
        }

    def get_police_inspection_guide(self) -> dict:
        """Cẩm nang kiểm tra, dừng xe CSGT theo Thông tư 73/2024/TT-BCA"""
        return {
            "title": "Quy chuẩn tuần tra, kiểm soát & dừng xe của CSGT",
            "circular": "Thông tư 73/2024/TT-BCA (Có hiệu lực từ 01/01/2025)",
            "stop_cases": [
                {
                    "case_number": 1,
                    "title": "Trực tiếp phát hiện hoặc ghi nhận hành vi vi phạm",
                    "detail": "Phát hiện thông qua các phương tiện, thiết bị kỹ thuật nghiệp vụ (máy bắn tốc độ, camera phạt nguội) hành vi vi phạm pháp luật về trật tự ATGTĐB."
                },
                {
                    "case_number": 2,
                    "title": "Thực hiện mệnh lệnh, kế hoạch tuần tra kiểm soát",
                    "detail": "Có văn bản kế hoạch tuần tra, kiểm soát công khai định kỳ hoặc chuyên đề đã được cấp có thẩm quyền phê duyệt."
                },
                {
                    "case_number": 3,
                    "title": "Có văn bản đề nghị của cơ quan chức năng",
                    "detail": "Văn bản đề nghị dừng phương tiện của Thủ trưởng, Phó Thủ trưởng cơ quan điều tra; cơ quan liên quan để phục vụ bảo đảm an ninh trật tự, đấu tranh phòng chống tội phạm."
                },
                {
                    "case_number": 4,
                    "title": "Tin báo, phản ánh, tố giác tội phạm",
                    "detail": "Có tin báo, kiến nghị, phản ánh hoặc tố cáo của tổ chức, cá nhân về hành vi vi phạm pháp luật của người và phương tiện."
                }
            ],
            "documents_check": [
                "Giấy phép lái xe (GPLX) phù hợp với loại xe đang điều khiển",
                "Chứng nhận đăng ký xe hoặc bản sao chứng thực kèm bản gốc giấy biên nhận thế chấp ngân hàng còn hiệu lực",
                "Chứng nhận kiểm định an toàn kỹ thuật và bảo vệ môi trường (đối với xe cơ giới bắt buộc kiểm định)",
                "Chứng nhận bảo hiểm bắt buộc trách nhiệm dân sự của chủ xe cơ giới",
                "💡 LƯU Ý ĐẶC BIỆT: Trường hợp các giấy tờ trên đã được tích hợp, cập nhật căn cước điện tử trên ứng dụng VNeID thì có giá trị pháp lý tương đương bản giấy khi kiểm tra."
            ],
            "breathalyzer_procedure": [
                "1. CSGT chào theo Điều lệnh Công an nhân dân, thông báo lý do dừng xe và nội dung kiểm soát.",
                "2. Kiểm tra nồng độ cồn bằng phương pháp định tính: Sử dụng phễu đo cách miệng tài xế 5-10cm, tài xế đếm 1-2-3 hoặc nói câu ngắn. Nếu máy báo 'Không có cồn' -> Cho tiếp tục lưu thông.",
                "3. Kiểm tra bằng phương pháp định lượng (khi phễu báo có cồn): Sử dụng ống thổi dùng một lần (người lái xe có quyền kiểm tra niêm phong bọc nilon của ống thổi trước khi gắn vào máy đo).",
                "4. In kết quả đo: Máy đo in phiếu kết quả đo gồm thời gian, chỉ số mg/l, số seri máy. Tài xế và CSGT cùng ký xác nhận trên phiếu đo."
            ],
            "citizen_rights": [
                "Người dân có quyền ghi âm, ghi hình quá trình làm việc của CSGT nhưng phải bảo đảm không làm ảnh hưởng đến quá trình thực thi nhiệm vụ của lực lượng chức năng.",
                "Có quyền yêu cầu CSGT thông báo lỗi vi phạm và xem lại hình ảnh, video ghi nhận hành vi vi phạm (nếu bị xử phạt qua thiết bị nghiệp vụ) trước khi ký biên bản.",
                "Được quyền ghi ý kiến không đồng ý của mình vào mục 'Ý kiến của người vi phạm' trên biên bản xử phạt vi phạm hành chính."
            ]
        }

    def get_pdf_path(self, doc_id: str) -> Optional[str]:
        """Trả về đường dẫn tệp PDF tuyệt đối của văn bản"""
        for d in _documents_metadata():
            if doc_id == d["id"] or doc_id == d["code"] or doc_id in d["id"]:
                path = os.path.join(self.pdf_dir, d["pdf_file"])
                if os.path.exists(path):
                    return path
        return None


# Singleton instance
_provider_instance: Optional[DocumentProvider] = None


def get_document_provider() -> DocumentProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = DocumentProvider()
    return _provider_instance
