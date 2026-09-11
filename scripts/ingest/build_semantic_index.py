#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XÂY DỰNG CHỈ MỤC NGỮ NGHĨA HỢP NHẤT CHO TOÀN BỘ 6 VĂN BẢN PHÁP LUẬT GIAO THÔNG ĐƯỜNG BỘ
Model: google/gemini-embedding-2 (3072 chiều) qua OpenRouter API

Văn bản bao gồm:
1. 01_luat_36_2024_qh15: Luật Trật tự, ATGT đường bộ 2024
2. 02_luat_35_2024_qh15: Luật Đường bộ 2024
3. 03_nghi_dinh_168_2024_nd_cp: Nghị định 168/2024/NĐ-CP (Xử phạt vi phạm hành chính)
4. 04_thong_tu_31_2019_tt_bgtvt: Thông tư 31/2019/TT-BGTVT (Tốc độ & khoảng cách)
5. 05_thong_tu_73_2024_tt_bca: Thông tư 73/2024/TT-BCA (Tuần tra CSGT, VNeID)
6. 06_qcvn_41_2019_bgtvt: QCVN 41:2019/BGTVT (Biển báo, vạch kẻ đường kèm ảnh)

Xuất ra:
  data/processed/semantic_chunks.json   danh sách chunk (thứ tự khớp với vector)
  data/processed/semantic_index.npz     ma trận vector 3072 chiều đã chuẩn hóa L2
  data/processed/semantic_parents.json  toàn văn Điều/Biển báo cha để trả về sau khi khớp
"""

import json
import os
import sys
import time
from typing import Any, Dict, List

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
load_dotenv(os.path.join(BASE_DIR, ".env"))

EMBED_BATCH_SIZE = 32
EMBED_MAX_CHARS = 3500


def load_chunks_and_parents() -> (List[Dict[str, Any]], Dict[str, Dict[str, Any]]):
    """Nạp tất cả chunks từ all_legal_chunks.jsonl và xây dựng semantic_parents"""
    chunks_path = os.path.join(PROCESSED_DIR, "all_legal_chunks.jsonl")
    if not os.path.exists(chunks_path):
        raise FileNotFoundError(f"Không tìm thấy {chunks_path}. Hãy chạy scripts/optimize_legal_json.py trước.")

    all_chunks: List[Dict[str, Any]] = []
    parents: Dict[str, Dict[str, Any]] = {}

    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            chunk_id = item["id"]
            parent_id = item.get("parent_id") or chunk_id
            doc_id = item.get("doc_id", "")
            doc_name = item.get("doc_name", "")
            doc_type = item.get("doc_type", "")
            header = item.get("header") or item.get("citation", "")
            page_content = item.get("page_content", "")
            chapter_title = item.get("chapter_title", "")
            art_num = item.get("article_number")

            # Xây dựng parent document nếu chưa có
            if parent_id not in parents:
                parents[parent_id] = {
                    "parent_id": parent_id,
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "doc_type": doc_type,
                    "article_number": art_num,
                    "article_header": header,
                    "chapter_title": chapter_title,
                    "content": page_content,
                    "has_illustration": item.get("has_illustration", False),
                    "image_path": item.get("image_path"),
                    "citation": item.get("citation", header)
                }
            elif item.get("type") == "overview" or len(page_content) > len(parents[parent_id].get("content", "")):
                # Ưu tiên nội dung overview hoặc nội dung dài hơn cho parent
                parents[parent_id]["content"] = page_content

            chunk_dict = {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "parent_id": parent_id,
                "type": item.get("type", "article"),
                "article_number": art_num,
                "header": header,
                "chapter_title": chapter_title,
                "citation": item.get("citation", header),
                "text": item.get("text", page_content),
                "has_illustration": item.get("has_illustration", False),
                "image_path": item.get("image_path")
            }
            # Bổ sung các trường chuyên biệt nếu có
            for extra in ("vehicle", "behaviour", "fine_text", "points_deducted", "sign_code", "sign_name"):
                if extra in item:
                    chunk_dict[extra] = item[extra]

            all_chunks.append(chunk_dict)

    return all_chunks, parents


def embed_all(client: OpenAI, model: str, texts: List[str]) -> np.ndarray:
    """
    Sinh vector theo lô và chuẩn hóa L2 norm.
    Bắt buộc encoding_format='float' cho model google/gemini-embedding-2 trên OpenRouter.
    """
    vectors: List[np.ndarray] = []
    started = time.time()
    total_chunks = len(texts)

    for start in range(0, total_chunks, EMBED_BATCH_SIZE):
        batch = [t[:EMBED_MAX_CHARS].strip() for t in texts[start:start + EMBED_BATCH_SIZE]]
        for attempt in range(4):
            try:
                response = client.embeddings.create(
                    model=model,
                    input=batch,
                    encoding_format="float"
                )
                break
            except Exception as error:
                if attempt == 3:
                    raise RuntimeError(f"Lỗi embedding tại chunk {start}: {error}")
                wait_sec = 2 * (attempt + 1)
                time.sleep(wait_sec)

        for item in response.data:
            vector = np.array(item.embedding, dtype=np.float32)
            norm = np.linalg.norm(vector)
            vectors.append(vector / norm if norm > 0 else vector)

        done = min(start + EMBED_BATCH_SIZE, total_chunks)
        elapsed = time.time() - started
        remaining = elapsed / done * (total_chunks - done) if done > 0 else 0
        speed = done / elapsed if elapsed > 0 else 0
        print(f"\r   [{done}/{total_chunks}] chunk ({done/total_chunks*100:.1f}%) | "
              f"Tốc độ: {speed:.1f} chunk/s | Còn ~{remaining:.0f}s",
              end="", flush=True)

    print()
    return np.array(vectors, dtype=np.float32)


def main() -> int:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ Không tìm thấy OPENROUTER_API_KEY trong .env")
        return 1

    model = os.getenv("EMBEDDING_MODEL", "google/gemini-embedding-2")

    print("=" * 78)
    print("  XÂY DỰNG CHỈ MỤC NGỮ NGHĨA HỢP NHẤT CHO 6 VĂN BẢN PHÁP LUẬT")
    print(f"  Mô hình Embedding: {model}")
    print("=" * 78)

    all_chunks, all_parents = load_chunks_and_parents()
    print(f"🔹 Tổng số chunk cần embed: {len(all_chunks)} chunks / {len(all_parents)} mục cha (parents)")

    from collections import Counter
    doc_counts = Counter(c["doc_id"] for c in all_chunks)
    for doc_id, count in sorted(doc_counts.items()):
        print(f"   • {doc_id}: {count} chunks")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=120.0,
        max_retries=2
    )

    print(f"\n🚀 Đang tiến hành embedding bằng {model} (batch={EMBED_BATCH_SIZE}, float)...")
    texts = [c["text"] for c in all_chunks]
    vectors = embed_all(client, model, texts)

    # Kiểm định chất lượng ma trận vector
    print("\n🔍 Đang kiểm định ma trận vector...")
    errors = []
    if len(vectors) != len(all_chunks):
        errors.append(f"Số lượng vector ({len(vectors)}) không khớp với số chunk ({len(all_chunks)})")
    if vectors.shape[1] != 3072:
        errors.append(f"Số chiều vector là {vectors.shape[1]}, không phải 3072 của Gemini Embedding 2")
    if not np.isfinite(vectors).all():
        errors.append("Ma trận vector chứa giá trị NaN hoặc vô cùng (Inf)")
    missing_parents = [c["parent_id"] for c in all_chunks if c["parent_id"] not in all_parents]
    if missing_parents:
        errors.append(f"Có {len(missing_parents)} chunk trỏ tới parent_id không tồn tại")

    if errors:
        print("❌ KIỂM ĐỊNH THẤT BẠI:")
        for err in errors:
            print(f"   - {err}")
        return 1

    print(f"✅ Kiểm định thành công: {vectors.shape[0]} vector x {vectors.shape[1]} chiều!")

    # Lưu trữ kết quả
    chunks_file = os.path.join(PROCESSED_DIR, "semantic_chunks.json")
    parents_file = os.path.join(PROCESSED_DIR, "semantic_parents.json")
    index_file = os.path.join(PROCESSED_DIR, "semantic_index.npz")

    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False)
    with open(parents_file, "w", encoding="utf-8") as f:
        json.dump(all_parents, f, ensure_ascii=False)
    np.savez_compressed(index_file, embeddings=vectors)

    print("\n💾 ĐÃ LƯU THÀNH CÔNG:")
    print(f"   • {chunks_file} ({os.path.getsize(chunks_file) / 1048576:.2f} MB)")
    print(f"   • {parents_file} ({os.path.getsize(parents_file) / 1048576:.2f} MB)")
    print(f"   • {index_file} ({os.path.getsize(index_file) / 1048576:.2f} MB)")
    print("\n🎉 Hoàn tất Phase 2: Vector Embedding với Gemini Embedding 2!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
