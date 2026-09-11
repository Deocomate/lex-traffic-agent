#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TỐI ƯU HÓA CẤU TRÚC JSON VÀ KHO CHUNKS RAG PHÂN CẤP CHO TOÀN BỘ 6 VĂN BẢN PHÁP LUẬT GIAO THÔNG

Văn bản bao gồm:
1. 01_luat_36_2024_qh15: Luật Trật tự, ATGT đường bộ (89 Điều, quy tắc, GPLX, điểm)
2. 02_luat_35_2024_qh15: Luật Đường bộ (86 Điều, kết cấu hạ tầng, cao tốc, vận tải)
3. 03_nghi_dinh_168_2024_nd_cp: Nghị định 168/2024 (634 hành vi vi phạm, mức phạt, trừ điểm)
4. 04_thong_tu_31_2019_tt_bgtvt: Thông tư 31/2019 (tốc độ tối đa, khoảng cách an toàn)
5. 05_thong_tu_73_2024_tt_bca: Thông tư 73/2024 (quyền dừng xe của CSGT, kiểm tra VNeID)
6. 06_qcvn_41_2019_bgtvt: QCVN 41:2019 (báo hiệu đường bộ, 320 biển báo + 43 vạch kẻ + ảnh)

Đầu ra tạo/tối ưu:
- data/processed/all_legal_chunks.jsonl (kho chunk chuẩn hóa)
- data/processed/traffic_signs_catalog.json (tra cứu O(1) biển báo & vạch kẻ đường kèm ảnh)
- data/processed/speed_limits_matrix.json (ma trận tốc độ theo Thông tư 31)
"""

import os
import sys
import json
import re
from typing import Dict, List, Any, Optional

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")


def load_json(filename: str) -> Any:
    path = os.path.join(PROCESSED_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_jsonl(filename: str) -> List[Dict[str, Any]]:
    path = os.path.join(PROCESSED_DIR, filename)
    items = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))
    return items


def build_traffic_signs_catalog() -> Dict[str, Any]:
    """Tạo bảng tra cứu nhanh biển báo và vạch kẻ đường kèm hình ảnh minh họa"""
    print("🔹 Đang xây dựng traffic_signs_catalog.json...")
    qcvn_data = load_json("06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo_structured.json")
    catalog_list = load_json("illustrations_catalog.json") or []

    # Map image path theo sign_code
    img_by_code: Dict[str, Dict[str, Any]] = {}
    for item in catalog_list:
        code = item.get("sign_code")
        if code:
            norm_code = code.strip().upper()
            if norm_code not in img_by_code or "bien_" in item.get("category", ""):
                img_by_code[norm_code] = item

    signs_catalog: Dict[str, Any] = {
        "metadata": {
            "title": "Danh mục tra cứu Báo hiệu Đường bộ theo QCVN 41:2019/BGTVT",
            "total_signs": 0,
            "total_markings": 0
        },
        "by_code": {},
        "by_name": {},
        "items": []
    }

    # Bổ sung biển báo
    traffic_signs = qcvn_data.get("traffic_signs", []) if qcvn_data else []
    for s in traffic_signs:
        code = s.get("sign_code", "").strip()
        if not code:
            continue
        code_norm = code.upper()
        name = s.get("sign_name", "").strip()
        group = s.get("sign_group", "").strip()
        meaning = s.get("meaning", "").strip()
        appendix = s.get("appendix", "").strip()
        citation = f"Phụ lục {appendix}, QCVN 41:2019/BGTVT"

        # Tìm ảnh
        img_info = img_by_code.get(code_norm)
        img_path = s.get("image_path") or (img_info.get("image_path") if img_info else None)
        if not img_path:
            # Tìm gần đúng code_norm không có dấu chấm (e.g. DP.133 -> DP_133)
            alt_key = code_norm.replace(".", "_")
            for c_key, info in img_by_code.items():
                if alt_key in c_key.replace(".", "_"):
                    img_path = info.get("image_path")
                    break

        entry = {
            "sign_code": code,
            "sign_code_normalized": code_norm,
            "sign_name": name,
            "sign_group": group,
            "meaning": meaning,
            "citation": citation,
            "has_illustration": bool(img_path),
            "image_path": img_path,
            "doc_id": "06_qcvn_41_2019_bgtvt",
            "doc_name": "QCVN 41:2019/BGTVT",
            "type": "traffic_sign"
        }
        signs_catalog["items"].append(entry)
        signs_catalog["by_code"][code_norm] = entry
        signs_catalog["by_code"][code_norm.replace(".", "")] = entry
        signs_catalog["by_code"][code] = entry
        if name:
            signs_catalog["by_name"][name.lower()] = entry

    # Bổ sung vạch kẻ đường
    road_markings = qcvn_data.get("road_markings", []) if qcvn_data else []
    for m in road_markings:
        code = m.get("marking_code", "").strip()
        name = m.get("marking_name", "").strip()
        meaning = m.get("meaning", "").strip()
        citation = "Phụ lục G, QCVN 41:2019/BGTVT"

        full_code = f"Vạch {code}" if not code.lower().startswith("vạch") else code
        img_info = img_by_code.get(code.upper())
        img_path = m.get("image_path") or (img_info.get("image_path") if img_info else None)

        entry = {
            "sign_code": full_code,
            "sign_code_normalized": code.upper(),
            "sign_name": name,
            "sign_group": "Vạch kẻ đường",
            "meaning": meaning,
            "citation": citation,
            "has_illustration": bool(img_path),
            "image_path": img_path,
            "doc_id": "06_qcvn_41_2019_bgtvt",
            "doc_name": "QCVN 41:2019/BGTVT",
            "type": "road_marking"
        }
        signs_catalog["items"].append(entry)
        signs_catalog["by_code"][full_code.upper()] = entry
        signs_catalog["by_code"][code.upper()] = entry
        signs_catalog["by_code"][code] = entry
        if name:
            signs_catalog["by_name"][name.lower()] = entry

    signs_catalog["metadata"]["total_signs"] = len(traffic_signs)
    signs_catalog["metadata"]["total_markings"] = len(road_markings)
    signs_catalog["metadata"]["total_items"] = len(signs_catalog["items"])

    out_path = os.path.join(PROCESSED_DIR, "traffic_signs_catalog.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(signs_catalog, f, ensure_ascii=False, indent=2)
    print(f"✅ Đã tạo traffic_signs_catalog.json ({len(signs_catalog['items'])} mục báo hiệu).")
    return signs_catalog


def build_speed_limits_matrix() -> Dict[str, Any]:
    """Tạo ma trận quy định tốc độ tối đa và khoảng cách an toàn theo Thông tư 31/2019/TT-BGTVT"""
    print("🔹 Đang xây dựng speed_limits_matrix.json...")
    matrix = {
        "metadata": {
            "document": "Thông tư 31/2019/TT-BGTVT",
            "title": "Quy định về tốc độ và khoảng cách an toàn của xe cơ giới, xe máy chuyên dùng",
            "effective_date": "15/10/2019"
        },
        "urban_area": {
            "description": "Tốc độ tối đa cho phép trong khu vực đông dân cư (Điều 6)",
            "divided_road_or_multi_lane": {
                "road_type": "Đường đôi hoặc đường một chiều có từ 2 làn xe cơ giới trở lên",
                "max_speed_kmh": 60,
                "applicable_vehicles": [
                    "Xe ô tô con",
                    "Xe ô tô chở người",
                    "Xe ô tô tải",
                    "Xe mô tô (xe máy)",
                    "Các loại xe cơ giới khác (trừ xe máy chuyên dùng, xe gắn máy)"
                ]
            },
            "undivided_road_or_single_lane": {
                "road_type": "Đường hai chiều hoặc đường một chiều có 1 làn xe cơ giới",
                "max_speed_kmh": 50,
                "applicable_vehicles": [
                    "Xe ô tô con",
                    "Xe ô tô chở người",
                    "Xe ô tô tải",
                    "Xe mô tô (xe máy)",
                    "Các loại xe cơ giới khác (trừ xe máy chuyên dùng, xe gắn máy)"
                ]
            },
            "special_vehicles": {
                "road_type": "Mọi loại đường trong và ngoài khu vực đông dân cư",
                "max_speed_kmh": 40,
                "applicable_vehicles": [
                    "Xe máy chuyên dùng",
                    "Xe gắn máy (kể cả xe máy điện)",
                    "Các loại xe tương tự"
                ],
                "article_ref": "Điều 8 Thông tư 31/2019/TT-BGTVT"
            }
        },
        "non_urban_area": {
            "description": "Tốc độ tối đa cho phép ngoài khu vực đông dân cư (Điều 7)",
            "divided_road": {
                "road_type": "Đường đôi hoặc đường một chiều có từ 2 làn xe cơ giới trở lên",
                "speeds": [
                    {
                        "vehicles": "Xe ô tô con, ô tô chở người đến 30 chỗ (trừ xe buýt), ô tô tải đến 3,5 tấn",
                        "max_speed_kmh": 90
                    },
                    {
                        "vehicles": "Xe ô tô chở người trên 30 chỗ (trừ xe buýt), ô tô tải trên 3,5 tấn (trừ ô tô xi téc)",
                        "max_speed_kmh": 80
                    },
                    {
                        "vehicles": "Ô tô buýt, ô tô đầu kéo kéo sơ mi rơ moóc, xe mô tô, ô tô chuyên dùng (trừ ô tô trộn vữa, bê tông)",
                        "max_speed_kmh": 70
                    },
                    {
                        "vehicles": "Ô tô kéo rơ moóc, ô tô kéo xe khác, ô tô trộn vữa, trộn bê tông, ô tô xi téc",
                        "max_speed_kmh": 60
                    }
                ]
            },
            "undivided_road": {
                "road_type": "Đường hai chiều hoặc đường một chiều có 1 làn xe cơ giới",
                "speeds": [
                    {
                        "vehicles": "Xe ô tô con, ô tô chở người đến 30 chỗ (trừ xe buýt), ô tô tải đến 3,5 tấn",
                        "max_speed_kmh": 80
                    },
                    {
                        "vehicles": "Xe ô tô chở người trên 30 chỗ (trừ xe buýt), ô tô tải trên 3,5 tấn (trừ ô tô xi téc)",
                        "max_speed_kmh": 70
                    },
                    {
                        "vehicles": "Ô tô buýt, ô tô đầu kéo kéo sơ mi rơ moóc, xe mô tô, ô tô chuyên dùng (trừ ô tô trộn vữa, bê tông)",
                        "max_speed_kmh": 60
                    },
                    {
                        "vehicles": "Ô tô kéo rơ moóc, ô tô kéo xe khác, ô tô trộn vữa, trộn bê tông, ô tô xi téc",
                        "max_speed_kmh": 50
                    }
                ]
            }
        },
        "expressway": {
            "description": "Tốc độ trên đường cao tốc (Điều 9)",
            "max_speed_kmh": 120,
            "rule": "Tốc độ tối đa không vượt quá 120 km/h, tuân thủ biển báo hiệu đường bộ và thiết kế cao tốc."
        },
        "safe_distances": {
            "description": "Khoảng cách an toàn tối thiểu giữa hai xe (Điều 11)",
            "table": [
                {"speed_range": "v = 60 km/h", "min_distance_m": 35},
                {"speed_range": "60 km/h < v ≤ 80 km/h", "min_distance_m": 55},
                {"speed_range": "80 km/h < v ≤ 100 km/h", "min_distance_m": 70},
                {"speed_range": "100 km/h < v ≤ 120 km/h", "min_distance_m": 100}
            ],
            "low_speed_rule": "Khi điều khiển xe chạy với tốc độ dưới 60 km/h, người lái xe phải chủ động giữ khoảng cách an toàn phù hợp với xe chạy liền trước xe của mình.",
            "bad_weather_rule": "Khi trời mưa, có sương mù, mặt đường trơn trượt, đường có địa hình quanh co, đèo dốc, tầm nhìn hạn chế, người lái xe phải điều chỉnh khoảng cách an toàn thích hợp lớn hơn trị số ghi trên biển báo hoặc trị số tối thiểu quy định."
        }
    }

    out_path = os.path.join(PROCESSED_DIR, "speed_limits_matrix.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    print("✅ Đã tạo speed_limits_matrix.json.")
    return matrix


def build_unified_chunks(signs_catalog: Dict[str, Any], speed_matrix: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Xây dựng và chuẩn hóa danh sách chunks đầy đủ cho cả 6 văn bản pháp luật"""
    print("🔹 Đang chuẩn hóa kho chunks RAG (all_legal_chunks.jsonl)...")
    all_chunks: List[Dict[str, Any]] = []

    # 1. LUẬT 36/2024/QH15
    law36_tree = load_json("01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong_structured.json")
    law36_articles = {a["metadata"]["article_number"]: a for a in load_jsonl("rag_chunks.jsonl")}
    scenarios_by_art = {}
    enriched_path = os.path.join(PROCESSED_DIR, "rag_chunks_enriched.jsonl")
    if os.path.exists(enriched_path):
        for item in load_jsonl("rag_chunks_enriched.jsonl"):
            meta = item.get("metadata", {})
            scenarios_by_art[meta.get("article_number")] = meta.get("real_world_scenarios", [])

    if law36_tree:
        for ch in law36_tree.get("chapters", []):
            ch_title = ch.get("chapter_title", "")
            ch_roman = ch.get("chapter_roman", "")
            for art in ch.get("articles", []):
                num = art.get("article_number")
                title = art.get("article_title", "")
                header = art.get("full_header") or f"Điều {num}. {title}"
                parent_doc = law36_articles.get(num, {})
                full_content = parent_doc.get("page_content", "")
                parent_id = f"01_luat_36_dieu_{num:02d}"

                # Chunk tổng quan điều
                base_text = f"[Luật 36/2024/QH15 - {header} ({ch_roman}: {ch_title})] {title}."
                all_chunks.append({
                    "id": f"{parent_id}_overview",
                    "doc_id": "01_luat_36_2024_qh15",
                    "doc_name": "Luật 36/2024/QH15",
                    "doc_type": "luat",
                    "parent_id": parent_id,
                    "type": "overview",
                    "article_number": num,
                    "header": header,
                    "chapter_title": ch_title,
                    "citation": f"{header}, Luật số 36/2024/QH15",
                    "text": base_text + f" Nội dung chính: {full_content[:350]}",
                    "page_content": full_content or base_text,
                    "metadata": {
                        "article_number": num,
                        "chapter_roman": ch_roman,
                        "chapter_title": ch_title
                    }
                })

                # Chunks cho từng khoản
                for cl in art.get("clauses", []):
                    cl_num = cl.get("clause_number")
                    cl_text = cl.get("content", "")
                    all_chunks.append({
                        "id": f"{parent_id}_khoan_{cl_num}",
                        "doc_id": "01_luat_36_2024_qh15",
                        "doc_name": "Luật 36/2024/QH15",
                        "doc_type": "luat",
                        "parent_id": parent_id,
                        "type": "clause",
                        "article_number": num,
                        "clause_number": cl_num,
                        "header": header,
                        "chapter_title": ch_title,
                        "citation": f"Khoản {cl_num} {header}, Luật số 36/2024/QH15",
                        "text": f"[{header} - Luật 36/2024/QH15] Khoản {cl_num}: {cl_text}",
                        "page_content": f"Khoản {cl_num} {header}:\n{cl_text}",
                        "metadata": {
                            "article_number": num,
                            "clause_number": cl_num,
                            "chapter_roman": ch_roman,
                            "chapter_title": ch_title
                        }
                    })

                # Chunks tình huống thực tế
                for idx, scen in enumerate(scenarios_by_art.get(num, []), 1):
                    all_chunks.append({
                        "id": f"{parent_id}_tinhhuong_{idx}",
                        "doc_id": "01_luat_36_2024_qh15",
                        "doc_name": "Luật 36/2024/QH15",
                        "doc_type": "luat",
                        "parent_id": parent_id,
                        "type": "scenario",
                        "article_number": num,
                        "header": header,
                        "chapter_title": ch_title,
                        "citation": f"{header}, Luật số 36/2024/QH15",
                        "text": f"[{header} - Luật 36/2024] Tình huống đời thường: {scen}",
                        "page_content": f"Tình huống thực tế liên quan đến {header}:\n{scen}",
                        "metadata": {"article_number": num, "chapter_title": ch_title}
                    })

    # 2. LUẬT 35/2024/QH15 (Đường bộ)
    law35_tree = load_json("02_luat_35_2024_qh15_duong_bo_structured.json") or load_json("luat_35_2024_structured.json")
    law35_articles = {a["metadata"]["article_number"]: a["page_content"] for a in load_jsonl("luat_35_articles.jsonl")}
    if law35_tree:
        for art in law35_tree.get("articles", []):
            num = art.get("article_number")
            title = art.get("article_title", "")
            ch_title = art.get("chapter_title", "")
            header = f"Điều {num}. {title}"
            parent_id = f"02_luat_35_dieu_{num:02d}"
            full_content = law35_articles.get(num, "")

            all_chunks.append({
                "id": f"{parent_id}_overview",
                "doc_id": "02_luat_35_2024_qh15",
                "doc_name": "Luật Đường bộ 2024 (Số 35/2024/QH15)",
                "doc_type": "luat",
                "parent_id": parent_id,
                "type": "overview",
                "article_number": num,
                "header": header,
                "chapter_title": ch_title,
                "citation": f"{header}, Luật Đường bộ số 35/2024/QH15",
                "text": f"[Luật Đường bộ 35/2024/QH15 - {header}] {title}. {ch_title}. {full_content[:300]}",
                "page_content": full_content or f"{header}\n{title}",
                "metadata": {"article_number": num, "chapter_title": ch_title}
            })

            for cl in art.get("clauses", []):
                cl_num = cl.get("clause_number")
                cl_text = cl.get("text", "")
                points_text = " ".join(f"{p['point_letter']}) {p['text']}" for p in cl.get("points", []))
                combined_text = f"{cl_text} {points_text}".strip()
                all_chunks.append({
                    "id": f"{parent_id}_khoan_{cl_num}",
                    "doc_id": "02_luat_35_2024_qh15",
                    "doc_name": "Luật Đường bộ 2024 (Số 35/2024/QH15)",
                    "doc_type": "luat",
                    "parent_id": parent_id,
                    "type": "clause",
                    "article_number": num,
                    "clause_number": cl_num,
                    "header": header,
                    "chapter_title": ch_title,
                    "citation": f"Khoản {cl_num} {header}, Luật Đường bộ 2024",
                    "text": f"[{header} - Luật Đường bộ 35/2024] Khoản {cl_num}: {combined_text}",
                    "page_content": f"Khoản {cl_num} {header} (Luật 35/2024):\n{combined_text}",
                    "metadata": {"article_number": num, "clause_number": cl_num, "chapter_title": ch_title}
                })

    # 3. NGHỊ ĐỊNH 168/2024/NĐ-CP (634 hành vi vi phạm & tiền phạt)
    penalties = load_jsonl("penalty_chunks.jsonl")
    for row in penalties:
        cit = row.get("citation", "")
        parent_id = f"03_nd168_{cit.replace(' ', '_')}"
        veh = row.get("vehicle", "")
        beh = row.get("behaviour", "")
        fine = row.get("fine_text", "")
        pts = f"Trừ {row['points_deducted']} điểm giấy phép lái xe." if row.get("points_deducted") else ""
        extra = " ".join(row.get("extra_sanctions", []))
        content = f"{cit}\nPhương tiện: {veh}\nHành vi: {beh}\nMức phạt: {fine}\n{pts}\n{extra}".strip()

        all_chunks.append({
            "id": parent_id,
            "doc_id": "03_nghi_dinh_168_2024_nd_cp",
            "doc_name": "Nghị định 168/2024/NĐ-CP",
            "doc_type": "nghi_dinh",
            "parent_id": parent_id,
            "type": "penalty",
            "article_number": row.get("article_number"),
            "header": cit,
            "chapter_title": row.get("article_title", ""),
            "citation": cit,
            "vehicle": veh,
            "behaviour": beh,
            "fine_text": fine,
            "points_deducted": row.get("points_deducted", 0),
            "text": f"[{veh} - Nghị định 168/2024] {beh} ({fine}). {pts} {cit}".strip(),
            "page_content": content,
            "metadata": {
                "vehicle": veh,
                "citation": cit,
                "fine_text": fine,
                "points_deducted": row.get("points_deducted", 0),
                "article_number": row.get("article_number")
            }
        })

    # 4. THÔNG TƯ 31/2019/TT-BGTVT (Tốc độ & Khoảng cách)
    tt31_tree = load_json("04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach_structured.json")
    if tt31_tree:
        for ch in tt31_tree.get("chapters", []):
            ch_title = ch.get("chapter_title", "")
            for art in ch.get("articles", []):
                num = art.get("article_number")
                title = art.get("article_title", "")
                header = f"Điều {num}. {title}"
                parent_id = f"04_tt31_dieu_{num:02d}"
                intro = art.get("intro", "")
                clauses_text = []
                for cl in art.get("clauses", []):
                    c_num = cl.get("clause_number")
                    c_text = cl.get("text", "")
                    clauses_text.append(f"Khoản {c_num}: {c_text}")
                content = f"{header} (Thông tư 31/2019/TT-BGTVT)\n{intro}\n" + "\n".join(clauses_text)

                all_chunks.append({
                    "id": f"{parent_id}",
                    "doc_id": "04_thong_tu_31_2019_tt_bgtvt",
                    "doc_name": "Thông tư 31/2019/TT-BGTVT",
                    "doc_type": "thong_tu",
                    "parent_id": parent_id,
                    "type": "speed_rule",
                    "article_number": num,
                    "header": header,
                    "chapter_title": ch_title,
                    "citation": f"{header}, Thông tư 31/2019/TT-BGTVT",
                    "text": f"[Thông tư 31/2019/TT-BGTVT - Tốc độ & khoảng cách an toàn] {header}: {title}. {content[:600]}",
                    "page_content": content,
                    "metadata": {"article_number": num, "title": title}
                })

    # 5. THÔNG TƯ 73/2024/TT-BCA (Quyền hạn CSGT, 4 trường hợp dừng xe, VNeID)
    tt73_tree = load_json("05_thong_tu_73_2024_tt_bca_tuan_tra_csgt_structured.json")
    if tt73_tree:
        for ch in tt73_tree.get("chapters", []):
            ch_title = ch.get("chapter_title", "")
            for art in ch.get("articles", []):
                num = art.get("article_number")
                title = art.get("article_title", "")
                header = f"Điều {num}. {title}"
                parent_id = f"05_tt73_dieu_{num:02d}"
                intro = art.get("intro", "")
                clauses_text = []
                for cl in art.get("clauses", []):
                    c_num = cl.get("clause_number")
                    c_text = cl.get("text", "")
                    clauses_text.append(f"Khoản {c_num}: {c_text}")
                content = f"{header} (Thông tư 73/2024/TT-BCA)\n{intro}\n" + "\n".join(clauses_text)

                all_chunks.append({
                    "id": f"{parent_id}",
                    "doc_id": "05_thong_tu_73_2024_tt_bca",
                    "doc_name": "Thông tư 73/2024/TT-BCA",
                    "doc_type": "thong_tu",
                    "parent_id": parent_id,
                    "type": "police_inspection",
                    "article_number": num,
                    "header": header,
                    "chapter_title": ch_title,
                    "citation": f"{header}, Thông tư 73/2024/TT-BCA",
                    "text": f"[Thông tư 73/2024/TT-BCA - Tuần tra kiểm soát CSGT] {header}: {title}. Quyền dừng xe, kiểm soát giấy tờ VNeID, xử phạt: {content[:600]}",
                    "page_content": content,
                    "metadata": {"article_number": num, "title": title}
                })

    # 6. QCVN 41:2019/BGTVT (Biển báo & Vạch kẻ đường có kèm ảnh minh họa)
    for sign in signs_catalog.get("items", []):
        code = sign["sign_code"]
        norm_code = sign["sign_code_normalized"]
        name = sign["sign_name"]
        meaning = sign["meaning"]
        group = sign["sign_group"]
        citation = sign["citation"]
        img_path = sign["image_path"]
        parent_id = f"06_qcvn41_{norm_code.replace('.', '_')}"

        img_markdown = f"![{code} - {name}](/{img_path})" if img_path else ""
        content = f"### 🚸 {code}: {name} ({group})\n{citation}\n\n**Ý nghĩa sử dụng:**\n{meaning}\n\n{img_markdown}".strip()

        all_chunks.append({
            "id": parent_id,
            "doc_id": "06_qcvn_41_2019_bgtvt",
            "doc_name": "QCVN 41:2019/BGTVT",
            "doc_type": "quy_chuan",
            "parent_id": parent_id,
            "type": sign["type"],
            "sign_code": code,
            "sign_name": name,
            "sign_group": group,
            "header": f"{code} - {name}",
            "citation": citation,
            "has_illustration": bool(img_path),
            "image_path": img_path,
            "text": f"[QCVN 41:2019/BGTVT - {group}] {code}: {name}. Ý nghĩa: {meaning}",
            "page_content": content,
            "metadata": {
                "sign_code": code,
                "sign_name": name,
                "sign_group": group,
                "has_illustration": bool(img_path),
                "image_path": img_path,
                "citation": citation
            }
        })

    # Ghi đè all_legal_chunks.jsonl
    out_jsonl = os.path.join(PROCESSED_DIR, "all_legal_chunks.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"✅ Đã tạo all_legal_chunks.jsonl với tổng cộng {len(all_chunks)} chunks:")
    from collections import Counter
    doc_counts = Counter(c["doc_id"] for c in all_chunks)
    for doc_id, count in sorted(doc_counts.items()):
        illus_count = sum(1 for c in all_chunks if c["doc_id"] == doc_id and c.get("has_illustration"))
        print(f"   • {doc_id}: {count} chunks (có ảnh: {illus_count})")

    return all_chunks


def main():
    print("=" * 78)
    print("  TỐI ƯU HÓA CẤU TRÚC JSON & KHO CHUNKS RAG PHÂN CẤP (6 VĂN BẢN)")
    print("=" * 78)

    signs_cat = build_traffic_signs_catalog()
    speed_mat = build_speed_limits_matrix()
    chunks = build_unified_chunks(signs_cat, speed_mat)

    print("\n🎉 Hoàn tất Phase 1: Tối ưu Cấu trúc JSON & Chỉ mục Pháp lý!")


if __name__ == "__main__":
    main()
