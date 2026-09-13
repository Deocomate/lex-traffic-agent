"""
Tập hợp và hợp nhất toàn bộ RAG Chunks từ 6/6 tài liệu pháp luật giao thông:
1. 01_luat_36_2024_qh15 (Luật Trật tự ATGT đường bộ)
2. 02_luat_35_2024_qh15 (Luật Đường bộ)
3. 03_nghi_dinh_168_2024_nd_cp (Nghị định xử phạt VPHC & trừ điểm bằng lái)
4. 04_thong_tu_31_2019_tt_bgtvt (Thông tư tốc độ và cự ly an toàn tối thiểu)
5. 05_thong_tu_73_2024_tt_bca (Thông tư CSGT tuần tra, dừng xe, kiểm soát VNeID)
6. 06_qcvn_41_2019_bgtvt (Quy chuẩn báo hiệu đường bộ, biển báo & vạch kẻ)

Xuất ra:
- data/processed/all_legal_chunks.jsonl (Toàn bộ chunks chuẩn hóa cho Vector Embedding / RAG)
- data/processed/all_legal_corpus_metadata.json (Thống kê và siêu dữ liệu toàn bộ kho tri thức)
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


def load_jsonl(filename: str) -> List[Dict[str, Any]]:
    path = os.path.join(PROCESSED_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def standardize_chunk(c: Dict[str, Any], default_doc_id: str, default_doc_name: str, default_doc_type: str) -> Dict[str, Any]:
    """Quy chuẩn hóa một chunk về định dạng thống nhất id, page_content, metadata kèm ảnh minh họa"""
    meta = c.get("metadata", {})
    if not meta:
        # Nếu chunk lưu metadata phẳng
        meta = {k: v for k, v in c.items() if k not in ("id", "page_content", "text")}

    meta["doc_id"] = default_doc_id
    meta["doc_name"] = default_doc_name
    meta["doc_type"] = default_doc_type

    # Nội dung văn bản
    content = c.get("page_content") or c.get("text") or ""
    if not content and "behaviour" in c:
        # Xây dựng text cho chunk vi phạm giao thông
        pts = f" (Trừ {c['points_deducted']} điểm GPLX)" if c.get("points_deducted") else ""
        ext = f" [Hình thức bổ sung: {c['extra_sanctions']}]" if c.get("extra_sanctions") else ""
        content = f"[{c.get('citation', '')}] Đối với phương tiện {c.get('vehicle', 'phương tiện')}: Hành vi {c.get('behaviour', '')}. Mức phạt tiền: {c.get('fine_text', '')}.{pts}{ext}"
    elif not content and "sign_code" in c:
        # Xây dựng text cho chunk biển báo giao thông
        ill_note = f" [Có hình ảnh minh họa: {c['image_path']}]" if c.get("image_path") else ""
        content = f"[{c.get('citation', '')}] Biển số {c.get('sign_code')}: \"{c.get('sign_name', '')}\" ({c.get('sign_group', '')}). {c.get('heading', '')} Ý nghĩa sử dụng: {c.get('meaning', '')}.{ill_note}"
    elif not content and "marking_code" in c:
        # Xây dựng text cho chunk vạch kẻ đường
        ill_note = f" [Có hình ảnh minh họa: {c['image_path']}]" if c.get("image_path") else ""
        content = f"[{c.get('citation', '')}] Vạch {c.get('marking_code')}: {c.get('marking_name', '')} ({c.get('group_title', '')}). Quy cách và ý nghĩa: {c.get('meaning', '')}.{ill_note}"

    chunk_id = c.get("id") or c.get("chunk_id")
    if not chunk_id:
        if "sign_code" in meta:
            clean_code = str(meta["sign_code"]).replace(".", "_")
            chunk_id = f"{default_doc_id}_sign_{clean_code}"
        elif "marking_code" in meta:
            clean_mark = str(meta["marking_code"]).replace(".", "_")
            chunk_id = f"{default_doc_id}_marking_{clean_mark}"
        else:
            art_num = meta.get("article_number", 0)
            chunk_id = f"{default_doc_id}_chunk_{art_num}_{len(content)}"

    # Đồng bộ thông tin ảnh vào metadata
    if "image_path" in c and c["image_path"]:
        meta["image_path"] = c["image_path"]
        meta["has_illustration"] = True
    elif "image_path" in meta and meta["image_path"]:
        meta["has_illustration"] = True
    else:
        meta["has_illustration"] = False

    return {
        "id": chunk_id,
        "page_content": content,
        "metadata": meta
    }


def main():
    print("=" * 80)
    print("XÂY DỰNG TẬP RAG CHUNKS HỢP NHẤT TỪ TOÀN BỘ CORPUS PHÁP LUẬT GIAO THÔNG")
    print("=" * 80)

    all_chunks: List[Dict[str, Any]] = []
    stats: Dict[str, int] = {}

    # 1. Luật 36/2024 (Lấy từ rag_chunks_enriched.jsonl / rag_chunks.jsonl)
    chunks_36 = load_jsonl("rag_chunks_enriched.jsonl") or load_jsonl("rag_chunks.jsonl")
    for c in chunks_36:
        all_chunks.append(standardize_chunk(c, "01_luat_36_2024_qh15", "Luật 36/2024/QH15", "luat"))
    stats["01_luat_36_2024_qh15"] = len(chunks_36)
    print(f"✅ Luật 36/2024/QH15: {len(chunks_36)} chunks")

    # 2. Luật 35/2024 (Lấy từ luat_35_articles.jsonl)
    chunks_35 = load_jsonl("luat_35_articles.jsonl")
    for c in chunks_35:
        all_chunks.append(standardize_chunk(c, "02_luat_35_2024_qh15", "Luật 35/2024/QH15", "luat"))
    stats["02_luat_35_2024_qh15"] = len(chunks_35)
    print(f"✅ Luật 35/2024/QH15: {len(chunks_35)} chunks")

    # 3. Nghị định 168/2024 (Lấy từ penalty_chunks.jsonl)
    chunks_168 = load_jsonl("penalty_chunks.jsonl")
    for c in chunks_168:
        all_chunks.append(standardize_chunk(c, "03_nghi_dinh_168_2024_nd_cp", "Nghị định 168/2024/NĐ-CP", "nghi_dinh"))
    stats["03_nghi_dinh_168_2024_nd_cp"] = len(chunks_168)
    print(f"✅ Nghị định 168/2024/NĐ-CP: {len(chunks_168)} chunks")

    # 4. Thông tư 31/2019 (Lấy từ tt_31_articles.jsonl)
    chunks_31 = load_jsonl("tt_31_articles.jsonl")
    for c in chunks_31:
        all_chunks.append(standardize_chunk(c, "04_thong_tu_31_2019_tt_bgtvt", "Thông tư 31/2019/TT-BGTVT", "thong_tu"))
    stats["04_thong_tu_31_2019_tt_bgtvt"] = len(chunks_31)
    print(f"✅ Thông tư 31/2019/TT-BGTVT: {len(chunks_31)} chunks")

    # 5. Thông tư 73/2024 (Lấy từ tt_73_articles.jsonl)
    chunks_73 = load_jsonl("tt_73_articles.jsonl")
    for c in chunks_73:
        all_chunks.append(standardize_chunk(c, "05_thong_tu_73_2024_tt_bca", "Thông tư 73/2024/TT-BCA", "thong_tu"))
    stats["05_thong_tu_73_2024_tt_bca"] = len(chunks_73)
    print(f"✅ Thông tư 73/2024/TT-BCA: {len(chunks_73)} chunks")

    # 6. QCVN 41/2019 (Lấy từ qcvn_41_articles.jsonl, traffic_signs.jsonl, road_markings.jsonl)
    chunks_qcvn = load_jsonl("qcvn_41_articles.jsonl")
    chunks_signs = load_jsonl("traffic_signs.jsonl")
    chunks_markings = load_jsonl("road_markings.jsonl")
    for c in chunks_qcvn:
        all_chunks.append(standardize_chunk(c, "06_qcvn_41_2019_bgtvt", "QCVN 41:2019/BGTVT", "quy_chuan"))
    for c in chunks_signs:
        all_chunks.append(standardize_chunk(c, "06_qcvn_41_2019_bgtvt", "QCVN 41:2019/BGTVT", "quy_chuan"))
    for c in chunks_markings:
        all_chunks.append(standardize_chunk(c, "06_qcvn_41_2019_bgtvt", "QCVN 41:2019/BGTVT", "quy_chuan"))
    stats["06_qcvn_41_2019_bgtvt"] = len(chunks_qcvn) + len(chunks_signs) + len(chunks_markings)
    print(f"✅ QCVN 41:2019/BGTVT: {stats['06_qcvn_41_2019_bgtvt']} chunks ({len(chunks_qcvn)} Điều, {len(chunks_signs)} biển báo, {len(chunks_markings)} vạch kẻ)")

    # Ghi toàn bộ ra file master
    out_jsonl = os.path.join(PROCESSED_DIR, "all_legal_chunks.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    out_meta = os.path.join(PROCESSED_DIR, "all_legal_corpus_metadata.json")
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump({
            "total_chunks": len(all_chunks),
            "documents_count": len(stats),
            "distribution": stats,
            "master_file": "all_legal_chunks.jsonl"
        }, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 ĐÃ XUẤT TẬP CHUNKS HỢP NHẤT:")
    print(f"   - File: {out_jsonl}")
    print(f"   - Tổng số chunks: {len(all_chunks):,}")
    print(f"   - Metadata thống kê: {out_meta}")


if __name__ == "__main__":
    main()
