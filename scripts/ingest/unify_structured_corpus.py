"""
Script chuẩn hóa toàn bộ 6/6 tài liệu pháp luật giao thông thành các tệp JSON cấu trúc hoàn chỉnh.
Mỗi file JSON đều có:
- Metadata chuẩn: doc_id, doc_name, doc_full_name, doc_type, issuing_authority, date_effective, total_chapters, total_articles.
- Phân cấp theo Chương (chapters): chapter_roman, chapter_title, articles.
- Danh sách phẳng toàn bộ Điều luật (articles): article_number, article_title, intro, clauses (clause_number, text, points).
- Dữ liệu chuyên biệt nếu có (penalties, speed tables, traffic signs, road markings).
"""

import os
import sys
import json
from typing import Any, Dict, List

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")


def process_luat_36() -> Dict[str, Any]:
    src = os.path.join(PROCESSED_DIR, "law_36_2024_structured.json")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_articles = []
    chapters = []

    for c in data.get("chapters", []):
        chap_articles = []
        for a in c.get("articles", []):
            clauses = []
            for cl in a.get("clauses", []):
                points = []
                for pt in cl.get("points", []):
                    points.append({
                        "point_letter": pt.get("point_id", "").replace(")", "").strip().lower(),
                        "text": pt.get("point_text", "").strip()
                    })
                clauses.append({
                    "clause_number": cl.get("clause_number", 0),
                    "text": cl.get("clause_text", "").strip(),
                    "points": points
                })

            art_obj = {
                "article_number": a.get("article_number", 0),
                "article_title": a.get("article_title", "").strip(),
                "chapter_roman": c.get("chapter_roman", ""),
                "chapter_title": c.get("chapter_title", "").strip(),
                "intro": a.get("content_raw", "").strip() if not clauses else "",
                "clauses": clauses
            }
            chap_articles.append(art_obj)
            flat_articles.append(art_obj)

        chapters.append({
            "chapter_roman": c.get("chapter_roman", ""),
            "chapter_title": c.get("chapter_title", "").strip(),
            "articles": chap_articles
        })

    return {
        "doc_id": "01_luat_36_2024_qh15",
        "doc_name": "Luật 36/2024/QH15",
        "doc_full_name": "Luật Trật tự, an toàn giao thông đường bộ (Luật số 36/2024/QH15)",
        "doc_type": "luat",
        "issuing_authority": "Quốc hội khóa XV",
        "date_effective": "01/01/2025",
        "total_chapters": len(chapters),
        "total_articles": len(flat_articles),
        "chapters": chapters,
        "articles": flat_articles
    }


def process_luat_35() -> Dict[str, Any]:
    src = os.path.join(PROCESSED_DIR, "luat_35_2024_structured.json")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_articles = data.get("articles", [])
    # Nhóm theo Chương
    chapters_dict = {}
    for a in flat_articles:
        cr = a.get("chapter_roman", "")
        ct = a.get("chapter_title", "")
        if cr not in chapters_dict:
            chapters_dict[cr] = {
                "chapter_roman": cr,
                "chapter_title": ct,
                "articles": []
            }
        chapters_dict[cr]["articles"].append(a)

    chapters = list(chapters_dict.values())
    return {
        "doc_id": "02_luat_35_2024_qh15",
        "doc_name": "Luật 35/2024/QH15",
        "doc_full_name": "Luật Đường bộ (Luật số 35/2024/QH15)",
        "doc_type": "luat",
        "issuing_authority": "Quốc hội khóa XV",
        "date_effective": "01/01/2025",
        "total_chapters": len(chapters),
        "total_articles": len(flat_articles),
        "chapters": chapters,
        "articles": flat_articles
    }


def process_nghi_dinh_168() -> Dict[str, Any]:
    src = os.path.join(PROCESSED_DIR, "nghi_dinh_168_2024_structured.json")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_articles = data.get("articles", [])
    chapters_dict = {}
    for a in flat_articles:
        cr = a.get("chapter_roman", "")
        ct = a.get("chapter_title", "")
        if cr not in chapters_dict:
            chapters_dict[cr] = {
                "chapter_roman": cr,
                "chapter_title": ct,
                "articles": []
            }
        chapters_dict[cr]["articles"].append(a)

    chapters = list(chapters_dict.values())
    return {
        "doc_id": "03_nghi_dinh_168_2024_nd_cp",
        "doc_name": "Nghị định 168/2024/NĐ-CP",
        "doc_full_name": "Nghị định quy định xử phạt vi phạm hành chính về trật tự, an toàn giao thông trong lĩnh vực giao thông đường bộ; trừ điểm, phục hồi điểm giấy phép lái xe (Nghị định số 168/2024/NĐ-CP)",
        "doc_type": "nghi_dinh",
        "issuing_authority": "Chính phủ",
        "date_effective": "01/01/2025",
        "replaces": ["Nghị định 100/2019/NĐ-CP", "Nghị định 123/2021/NĐ-CP"],
        "total_chapters": len(chapters),
        "total_articles": len(flat_articles),
        "chapters": chapters,
        "articles": flat_articles
    }


def process_thong_tu_31() -> Dict[str, Any]:
    src = os.path.join(PROCESSED_DIR, "04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach_structured.json")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_articles = [a for c in data.get("chapters", []) for a in c.get("articles", [])]
    data["doc_type"] = "thong_tu"
    data["articles"] = flat_articles
    return data


def process_thong_tu_73() -> Dict[str, Any]:
    src = os.path.join(PROCESSED_DIR, "05_thong_tu_73_2024_tt_bca_tuan_tra_csgt_structured.json")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_articles = [a for c in data.get("chapters", []) for a in c.get("articles", [])]
    data["doc_type"] = "thong_tu"
    data["articles"] = flat_articles
    return data


def process_qcvn_41() -> Dict[str, Any]:
    src = os.path.join(PROCESSED_DIR, "qcvn_41_2019_structured.json")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_articles = [a for c in data.get("chapters", []) for a in c.get("articles", [])]

    # Đọc catalogue biển báo và vạch kẻ đường kèm link ảnh
    signs_file = os.path.join(PROCESSED_DIR, "traffic_signs.jsonl")
    signs = []
    if os.path.exists(signs_file):
        with open(signs_file, "r", encoding="utf-8") as sf:
            signs = [json.loads(line) for line in sf]

    markings_file = os.path.join(PROCESSED_DIR, "road_markings.jsonl")
    markings = []
    if os.path.exists(markings_file):
        with open(markings_file, "r", encoding="utf-8") as mf:
            markings = [json.loads(line) for line in mf]

    return {
        "doc_id": "06_qcvn_41_2019_bgtvt",
        "doc_name": "QCVN 41:2019/BGTVT",
        "doc_full_name": "Quy chuẩn kỹ thuật quốc gia về báo hiệu đường bộ (QCVN 41:2019/BGTVT ban hành kèm Thông tư 54/2019/TT-BGTVT)",
        "doc_type": "quy_chuan_ky_thuat",
        "issuing_authority": "Bộ Giao thông vận tải",
        "date_effective": "01/07/2020",
        "total_chapters": len(data.get("chapters", [])),
        "total_articles": len(flat_articles),
        "total_appendices": len(data.get("appendices", [])),
        "total_traffic_signs": len(signs),
        "total_road_markings": len(markings),
        "chapters": data.get("chapters", []),
        "articles": flat_articles,
        "appendices": data.get("appendices", []),
        "traffic_signs": signs,
        "road_markings": markings
    }


def main():
    generators = [
        ("01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong_structured.json", process_luat_36),
        ("02_luat_35_2024_qh15_duong_bo_structured.json", process_luat_35),
        ("03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham_structured.json", process_nghi_dinh_168),
        ("04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach_structured.json", process_thong_tu_31),
        ("05_thong_tu_73_2024_tt_bca_tuan_tra_csgt_structured.json", process_thong_tu_73),
        ("06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo_structured.json", process_qcvn_41),
    ]

    print("=" * 80)
    print("CHUYỂN ĐỔI VÀ ĐỒNG BỘ 6/6 TẬP TIN JSON HOÀN CHỈNH TỪ RAW DATA")
    print("=" * 80)

    summary = []
    for filename, fn in generators:
        out_path = os.path.join(PROCESSED_DIR, filename)
        doc_json = fn()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc_json, f, ensure_ascii=False, indent=2)

        file_size = os.path.getsize(out_path)
        summary.append({
            "file": filename,
            "doc_id": doc_json["doc_id"],
            "doc_name": doc_json["doc_name"],
            "total_chapters": doc_json["total_chapters"],
            "total_articles": doc_json["total_articles"],
            "size_kb": f"{file_size / 1024:.1f} KB"
        })
        print(f"✅ {filename}: {doc_json['total_chapters']} Chương, {doc_json['total_articles']} Điều ({file_size/1024:.1f} KB)")

    print("\nBẢNG TỔNG HỢP 6 VĂN BẢN ĐÃ BÓC TÁCH HOÀN CHỈNH:")
    for s in summary:
        print(f" - [{s['doc_id']}] {s['doc_name']}: {s['total_articles']} Điều, {s['total_chapters']} Chương -> {s['file']} ({s['size_kb']})")


if __name__ == "__main__":
    main()
