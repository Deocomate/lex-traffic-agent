"""
Script xây dựng và lưu trữ chỉ mục BM25 (sparse index) trên toàn bộ corpus 2114 chunk.
Tokenize theo unigram + bigram tiếng Việt thông qua src.retrieval.vi_text.
Chỉ mục được lưu dưới dạng pickle tại data/processed/bm25_index.pkl để nạp nhanh (<2 giây).
"""

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from typing import Any, Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from rank_bm25 import BM25Okapi
from src.retrieval.vi_text import tokens, bigrams


def tokenize_chunk_text(text: str) -> List[str]:
    """Tokenize nội dung văn bản thành danh sách unigram và bigram."""
    unigrams = tokens(text)
    bgrams = list(bigrams(unigrams))
    return unigrams + bgrams


def compute_file_hash(filepath: str) -> str:
    """Tính SHA256 hash của file để kiểm tra tính toàn vẹn."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_bm25_index(
    chunks_path: str = None,
    output_path: str = None,
    verbose: bool = True,
) -> str:
    if not chunks_path:
        chunks_path = os.path.join(base_dir, "data", "processed", "semantic_chunks.json")
    if not output_path:
        output_path = os.path.join(base_dir, "data", "processed", "bm25_index.pkl")

    if not os.path.exists(chunks_path):
        raise FileNotFoundError(f"Không tìm thấy file chunks tại: {chunks_path}")

    if verbose:
        print(f"📖 Đang đọc chunks từ: {chunks_path}")

    t0 = time.time()
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    num_chunks = len(chunks)
    if verbose:
        print(f"⚙️  Bắt đầu tokenize và dựng BM25 cho {num_chunks} chunks...")

    tokenized_corpus = []
    for c in chunks:
        text = c.get("text", "")
        tokenized_corpus.append(tokenize_chunk_text(text))

    t_tokenize = time.time()
    bm25 = BM25Okapi(tokenized_corpus)
    t_build = time.time()

    chunks_hash = compute_file_hash(chunks_path)
    payload = {
        "bm25": bm25,
        "num_chunks": num_chunks,
        "chunks_hash": chunks_hash,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    file_size_kb = os.path.getsize(output_path) // 1024

    if verbose:
        print(f"✅ Xây dựng thành công chỉ mục BM25!")
        print(f"   - Số lượng chunk: {num_chunks}")
        print(f"   - Thời gian tokenize: {t_tokenize - t0:.3f}s")
        print(f"   - Thời gian tạo BM25: {t_build - t_tokenize:.3f}s")
        print(f"   - Tổng thời gian: {t_build - t0:.3f}s")
        print(f"   - Kích thước file: {file_size_kb} KB")
        print(f"   - Lưu tại: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Xây dựng chỉ mục BM25 cho LexTraffic AI")
    parser.add_argument("--chunks", default=None, help="Đường dẫn file semantic_chunks.json")
    parser.add_argument("--output", default=None, help="Đường dẫn file lưu bm25_index.pkl")
    args = parser.parse_args()

    build_bm25_index(args.chunks, args.output, verbose=True)


if __name__ == "__main__":
    main()
