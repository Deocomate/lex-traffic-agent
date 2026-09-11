"""
Hiệu chuẩn mốc tham chiếu phạm vi cho corpus (Corpus Scope Calibration).

Thay thế hằng số gõ tay `SEMANTIC_FLOOR=0.58` bằng một con số ĐO ĐƯỢC từ chính kho tài liệu.

Cách làm: lấy mẫu ngẫu nhiên các đoạn văn bản trong corpus, dùng chính chúng làm truy vấn giả,
loại bỏ kết quả tự khớp, rồi ghi lại điểm hạng 1. Phân bố thu được trả lời câu hỏi "một truy
vấn CHẮC CHẮN thuộc phạm vi thì thường đạt điểm bao nhiêu". Đuôi dưới của phân bố đó (phân vị
5) là mốc để nhận ra câu hỏi lạc đề.

Chạy lại mỗi khi dựng lại chỉ mục, hoặc khi thêm một Domain Pack mới:

    # Khớp từ ví dụ gán nhãn (chính xác nhất) — không cần mạng cho nhánh sparse/penalty:
    python scripts/ingest/calibrate_scope.py --labels data/benchmark/qa_testset_v2.json

    # Chỉ thống kê corpus, không có nhãn:
    python scripts/ingest/calibrate_scope.py --branch sparse
"""

import argparse
import json
import os
import random
import sys
from typing import Dict, List

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)

from src.retrieval.scope import (  # noqa: E402
    BRANCH_DENSE,
    BRANCH_SPARSE,
    SCOPE_REFERENCE_FILENAME,
    build_reference_payload,
    fit_threshold_from_labels,
)

BRANCH_PENALTY = "penalty_keyword"

# Phân vị mặc định khi KHÔNG có ví dụ gán nhãn. Khác nhau vì mỗi nhánh trả lời một câu hỏi khác:
#
# - `sparse`/`dense` trả lời "câu hỏi này có thuộc chủ đề của kho tài liệu không". Trung vị là
#   mốc hợp lý: thấp hơn hẳn mức một truy vấn trong kho thường đạt được thì đáng ngờ.
# - `penalty_keyword` trả lời câu hẹp hơn nhiều: "có hành vi vi phạm nào thật sự khớp không".
#   Rất nhiều câu hỏi giao thông hợp lệ (hạng bằng lái, biển báo, tốc độ) vốn KHÔNG nói về chế
#   tài, nên dùng trung vị sẽ chặn nhầm hàng loạt. Lấy đuôi dưới (p5) để chỉ loại đúng những
#   câu không hành vi nào khớp — đo được: câu lạc đề lọt 1/16, câu hợp lệ giữ 44/79, đúng bằng
#   mức của `SCORE_FLOOR = 12.0` cũ nhưng không còn con số gõ tay nào.
BRANCH_DEFAULT_PERCENTILE = {
    BRANCH_SPARSE: 50.0,
    BRANCH_DENSE: 50.0,
    BRANCH_PENALTY: 5.0,
}

DEFAULT_SAMPLES = 300
# Đoạn quá ngắn (tiêu đề, số hiệu lẻ) không đại diện cho một câu hỏi thật nên bỏ qua.
MIN_CHUNK_CHARS = 80

# Độ dài truy vấn giả, tính bằng từ. Người dùng thật hỏi ngắn ("nồng độ cồn ô tô", "vượt đèn đỏ
# phạt bao nhiêu"), không bao giờ dán nguyên một khoản luật dài vào ô tìm kiếm.
#
# Đây là chi tiết QUYẾT ĐỊNH việc hiệu chuẩn có dùng được hay không. Bản đầu lấy nguyên văn cả
# đoạn làm truy vấn giả: điểm khớp cao vống lên, mốc tham chiếu bị đẩy lên quá cao, và những
# câu hỏi thật hoàn toàn hợp lệ như "nồng độ cồn ô tô" bị coi là ngoài phạm vi. Truy vấn giả
# phải giống truy vấn thật thì mốc đo được mới có nghĩa.
QUERY_WORDS_MIN = 4
QUERY_WORDS_MAX = 12


def _pseudo_queries(texts: List[str], n: int, seed: int) -> List[str]:
    """
    Sinh truy vấn giả có độ dài giống câu hỏi thật: cắt một cửa sổ từ liên tiếp trong văn bản.
    """
    rng = random.Random(seed)
    usable = [t for t in texts if len(t) >= MIN_CHUNK_CHARS]
    rng.shuffle(usable)

    queries: List[str] = []
    for text in usable[:n]:
        words = text.split()
        if len(words) <= QUERY_WORDS_MIN:
            continue
        length = rng.randint(QUERY_WORDS_MIN, min(QUERY_WORDS_MAX, len(words)))
        start = rng.randint(0, len(words) - length)
        queries.append(" ".join(words[start:start + length]))
    return queries


def _sample_chunks(chunks: List[dict], n: int, seed: int) -> List[dict]:
    usable = [c for c in chunks if len(c.get("text", "")) >= MIN_CHUNK_CHARS]
    rng = random.Random(seed)
    return rng.sample(usable, min(n, len(usable)))


def calibrate_sparse(samples: int, seed: int) -> List[float]:
    """Điểm hạng 1 của BM25 cho các truy vấn giả. Chạy được hoàn toàn offline."""
    from src.retrieval.sparse import SparseIndex

    index = SparseIndex(base_dir)
    if not index.available:
        raise RuntimeError("Chưa có chỉ mục BM25. Chạy scripts/ingest/build_bm25_index.py trước.")

    scores: List[float] = []
    for query in _pseudo_queries([c["text"] for c in index.chunks], samples, seed):
        hits = index.search_chunks(query, top_k=1)
        if hits:
            scores.append(float(hits[0].get("score", 0.0)))
    return scores


def calibrate_dense(samples: int, seed: int) -> List[float]:
    """Điểm cosine hạng 1 cho các truy vấn giả. Cần OPENROUTER_API_KEY và mạng."""
    from src.retrieval.dense import get_cached_semantic_index

    index = get_cached_semantic_index(base_dir)
    if not index.available:
        raise RuntimeError("Chưa có chỉ mục vector. Chạy scripts/ingest/build_semantic_index.py trước.")

    scores: List[float] = []
    for query in _pseudo_queries([c["text"] for c in index.chunks], samples, seed):
        hits = index.search_chunks(query, top_k=1)
        if hits:
            scores.append(float(hits[0].get("score", 0.0)))
    return scores


def calibrate_penalty_keyword(samples: int, seed: int) -> List[float]:
    """
    Điểm cao nhất của bộ chấm điểm từ khoá Nghị định cho các truy vấn giả. Offline hoàn toàn.

    Truy vấn giả cắt ra từ chính mô tả hành vi vi phạm — thứ gần nhất với một câu hỏi chắc chắn
    thuộc phạm vi — nhưng rút ngắn về đúng độ dài người dùng thật hay hỏi.
    """
    from src.tools.penalty_lookup import PenaltyLookup

    lookup = PenaltyLookup(base_dir)
    if not lookup.chunks:
        raise RuntimeError("Chưa có penalty_chunks.jsonl. Chạy scripts/ingest/prepare_penalties.py trước.")

    behaviours = [c.get("behaviour", "") for c in lookup.chunks]

    scores: List[float] = []
    for query in _pseudo_queries(behaviours, samples, seed):
        scored = lookup.score_by_keyword(query)
        if scored:
            scores.append(float(scored[0][0]))
    return scores


def _load_labelled(path: str) -> Dict[str, List[str]]:
    """
    Đọc ví dụ gán nhãn: câu hỏi nào trong phạm vi, câu nào ngoài.

    Chấp nhận cấu trúc benchmark của dự án (`items` / `questions` / danh sách phẳng) với cờ
    `is_out_of_scope`. Miền mới chỉ cần một tệp JSON cùng dạng.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("items") or raw.get("questions") or (raw if isinstance(raw, list) else [])

    grouped: Dict[str, List[str]] = {"in": [], "out": []}
    for item in items:
        question = (item or {}).get("question")
        if not question:
            continue
        grouped["out" if item.get("is_out_of_scope") else "in"].append(question)
    return grouped


def _top_score(branch: str, query: str) -> float:
    """Điểm hạng 1 của một truy vấn trên nhánh tương ứng."""
    if branch == BRANCH_SPARSE:
        from src.retrieval.sparse import SparseIndex

        hits = SparseIndex(base_dir).search_chunks(query, top_k=1)
        return float(hits[0].get("score", 0.0)) if hits else 0.0

    if branch == BRANCH_DENSE:
        from src.retrieval.dense import get_cached_semantic_index

        hits = get_cached_semantic_index(base_dir).search_chunks(query, top_k=1)
        return float(hits[0].get("score", 0.0)) if hits else 0.0

    from src.tools.penalty_lookup import PenaltyLookup

    scored = PenaltyLookup(base_dir).score_by_keyword(query)
    return float(scored[0][0]) if scored else 0.0


def fit_from_labels(branch: str, labelled: Dict[str, List[str]]) -> Dict[str, float]:
    """Khớp mốc tham chiếu của một nhánh từ ví dụ gán nhãn."""
    in_scores = [_top_score(branch, q) for q in labelled["in"]]
    out_scores = [_top_score(branch, q) for q in labelled["out"]]
    return fit_threshold_from_labels(in_scores, out_scores)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hiệu chuẩn mốc tham chiếu phạm vi từ corpus")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--seed", type=int, default=20240911, help="Cố định để kết quả lặp lại được")
    parser.add_argument(
        "--branch",
        choices=[BRANCH_SPARSE, BRANCH_DENSE, BRANCH_PENALTY, "both"],
        default="both",
        help="Nhánh cần hiệu chuẩn ('sparse' và 'penalty_keyword' chạy được offline)",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=None,
        help=(
            "Phân vị dùng khi không có nhãn (mặc định theo nhánh). Mỗi nhánh trả lời một câu "
            "hỏi khác nhau nên phân vị hợp lý khác nhau — xem BRANCH_DEFAULT_PERCENTILE."
        ),
    )
    parser.add_argument(
        "--labels",
        default=None,
        help=(
            "Tệp JSON chứa câu hỏi có nhãn `is_out_of_scope`. Có thì mốc được KHỚP từ ví dụ "
            "(chính xác hơn hẳn); không có thì rơi về thống kê corpus."
        ),
    )
    args = parser.parse_args()

    processed_dir = os.path.join(base_dir, "data", "processed")
    out_path = os.path.join(processed_dir, SCOPE_REFERENCE_FILENAME)

    # Giữ lại nhánh đã hiệu chuẩn trước đó khi lần này chỉ chạy một nhánh.
    existing: Dict[str, List[float]] = {}
    previous_branches = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                previous_branches = json.load(f).get("branches", {})
        except ValueError:
            previous_branches = {}

    samples: Dict[str, List[float]] = {}
    wanted = (
        [BRANCH_SPARSE, BRANCH_PENALTY, BRANCH_DENSE]
        if args.branch == "both"
        else [args.branch]
    )
    runners = {
        BRANCH_SPARSE: calibrate_sparse,
        BRANCH_DENSE: calibrate_dense,
        BRANCH_PENALTY: calibrate_penalty_keyword,
    }

    for branch in wanted:
        runner = runners[branch]
        try:
            scores = runner(args.samples, args.seed)
            samples[branch] = scores
            print(f"  ✓ {branch}: {len(scores)} truy vấn giả")
        except Exception as e:
            print(f"  ⚠️ Bỏ qua nhánh '{branch}': {e}")

    fitted: Dict[str, Dict[str, float]] = {}
    if args.labels:
        labelled = _load_labelled(args.labels)
        print(
            f"\n  📌 Ví dụ gán nhãn: {len(labelled['in'])} câu trong phạm vi, "
            f"{len(labelled['out'])} câu ngoài phạm vi"
        )
        for branch in samples:
            try:
                fit = fit_from_labels(branch, labelled)
                if fit:
                    fitted[branch] = fit
                    print(
                        f"  ✓ {branch}: mốc khớp = {fit['reference']:.4f} "
                        f"(bắt đúng lạc đề {fit['recall']:.0%}, báo nhầm {fit['false_positive']:.0%})"
                    )
            except Exception as e:
                print(f"  ⚠️ Không khớp được nhánh '{branch}' từ nhãn: {e}")

    # Mỗi nhánh hiệu chuẩn theo phân vị riêng rồi ghép lại.
    payload = {"default_percentile": None, "out_of_scope_ratio": None, "branches": {}}
    for branch, scores in samples.items():
        pct = args.percentile if args.percentile is not None else BRANCH_DEFAULT_PERCENTILE.get(branch, 50.0)
        single = build_reference_payload({branch: scores}, {branch: fitted[branch]} if branch in fitted else None, pct=pct)
        payload["out_of_scope_ratio"] = single["out_of_scope_ratio"]
        payload["branches"].update(single["branches"])
    payload["default_percentile"] = args.percentile

    # Ghép lại các nhánh cũ không được hiệu chuẩn trong lần chạy này
    for branch, entry in previous_branches.items():
        payload["branches"].setdefault(branch, entry)

    if not payload["branches"]:
        print("❌ Không hiệu chuẩn được nhánh nào.")
        raise SystemExit(1)

    os.makedirs(processed_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 62)
    print(" 📐 MỐC THAM CHIẾU PHẠM VI (đo từ corpus, không gõ tay)")
    print("=" * 62)
    for branch, entry in payload["branches"].items():
        source = entry.get("source", "corpus_statistics")
        detail = (
            f"bắt lạc đề {entry['recall']:.0%}, báo nhầm {entry['false_positive']:.0%}"
            if source == "labelled_examples"
            else f"trung vị corpus={entry.get('median', 0.0):.4f}, n={entry.get('samples', 0)}"
        )
        print(f"  {branch:<16} mốc={entry['reference']:<10.4f} [{source}] {detail}")
    print(f"\n  💾 Đã lưu: {out_path}")


if __name__ == "__main__":
    main()
