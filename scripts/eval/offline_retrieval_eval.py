"""
Đánh giá truy xuất KHÔNG CẦN MẠNG (Offline Retrieval Regression Harness).

Vì sao cần: `scripts/eval/retrieval_eval.py` phải nhúng câu hỏi qua API embedding, nên không
chạy được trong CI hay môi trường không có `OPENROUTER_API_KEY`. Nhưng phần lớn rủi ro hồi quy
khi refactor tầng truy xuất nằm ở *thuật toán xếp hạng* (hợp nhất thứ hạng, gộp về parent, chọn
ngưỡng) chứ không ở chất lượng vector — và toàn bộ phần đó chạy được offline nếu ta thay nhánh
dense bằng một chỉ mục rỗng.

Harness này chạy đúng `HybridSearch` thật với nhánh dense bị vô hiệu hóa, nên nó đo được:
- thứ hạng BM25 sau khi gộp về Điều/Biển báo cha,
- toàn bộ logic parent aggregation và chuẩn hóa điểm.

Con số tuyệt đối THẤP HƠN bản hybrid đầy đủ (mất hẳn nhánh ngữ nghĩa) — đó là dự kiến. Giá trị
của nó là tính TẤT ĐỊNH: cùng một corpus cho ra cùng một con số, nên mọi chênh lệch trước/sau
refactor đều là do thay đổi mã nguồn.

Dùng:
    python scripts/eval/offline_retrieval_eval.py
    python scripts/eval/offline_retrieval_eval.py --output data/benchmark/baseline.json
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)

from scripts.eval.datasets import filter_dataset, load_dataset
from scripts.eval.metrics import hit_at_k, ndcg_at_k, reciprocal_rank


class NullDenseIndex:
    """
    Chỉ mục dense giả: luôn trả về rỗng, nhưng vẫn cung cấp `parents` thật từ đĩa.

    `HybridSearch` cần `parents` để gộp chunk con về Điều/Biển báo cha; chỉ có bước nhúng câu hỏi
    mới cần mạng. Tách đúng một mình bước đó ra là đủ để chạy offline.
    """

    def __init__(self, base_dir: str):
        parents_path = os.path.join(base_dir, "data", "processed", "semantic_parents.json")
        with open(parents_path, "r", encoding="utf-8") as f:
            self.parents: Dict[str, Any] = json.load(f)
        self.chunks: List[Dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    def search_chunks(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        return []


def build_offline_retriever(base_dir: str):
    """`HybridSearch` thật, chỉ khác là nhánh dense bị vô hiệu hóa."""
    from src.retrieval.hybrid import HybridSearch
    from src.retrieval.sparse import SparseIndex

    return HybridSearch(
        base_dir=base_dir,
        dense_index=NullDenseIndex(base_dir),
        sparse_index=SparseIndex(base_dir),
    )


def _targets(item) -> List[str]:
    """Danh sách parent_id được coi là đáp án đúng cho một câu hỏi."""
    target_pid = item.target_parent_id
    if not target_pid:
        return []
    return list(target_pid) if isinstance(target_pid, list) else [target_pid]


def run_offline_eval(
    dataset_path: Optional[str] = None,
    output_path: Optional[str] = None,
    top_k: int = 5,
    verbose: bool = True,
) -> Dict[str, Any]:
    if not dataset_path:
        dataset_path = os.path.join(base_dir, "data", "benchmark", "qa_testset_v2.json")

    dataset = load_dataset(dataset_path)
    items = [
        it
        for it in filter_dataset(dataset, include_out_of_scope=False)
        if _targets(it)
    ]

    retriever = build_offline_retriever(base_dir)

    hits = {1: 0, 3: 0, 5: 0}
    rr_list: List[float] = []
    ndcg_list: List[float] = []
    per_item: List[Dict[str, Any]] = []

    for item in items:
        targets = _targets(item)
        # `semantic_floor=0.0`: nhánh dense rỗng nên ngưỡng cosine không áp dụng được ở đây.
        # `adaptive=False`: đo xếp hạng thuần trên danh sách độ dài cố định (Hit@k, MRR, nDCG@k
        # cần đúng `top_k` ứng viên). Việc cắt theo vách rơi là quyết định trình bày cho Agent,
        # đo ở đây sẽ trộn lẫn hai thứ khác nhau.
        retrieved = retriever.retrieve_articles(item.question, top_k=top_k, adaptive=False)
        pids = [d.get("parent_id") for d in retrieved]

        for k in (1, 3, 5):
            if hit_at_k(pids, targets, k) > 0.0:
                hits[k] += 1
        rr = reciprocal_rank(pids, targets)
        ndcg = ndcg_at_k(pids, targets, 5)
        rr_list.append(rr)
        ndcg_list.append(ndcg)

        per_item.append({
            "id": item.id,
            "question": item.question,
            "targets": targets,
            "retrieved": pids,
            "rr": round(rr, 4),
        })

    total = len(items) or 1
    summary = {
        "harness": "offline_sparse_only",
        "dataset": os.path.basename(dataset_path),
        "total_questions": len(items),
        "hit@1": round(hits[1] / total, 4),
        "hit@3": round(hits[3] / total, 4),
        "hit@5": round(hits[5] / total, 4),
        "mrr": round(sum(rr_list) / total, 4),
        "ndcg@5": round(sum(ndcg_list) / total, 4),
    }

    if verbose:
        print("=" * 66)
        print(" 📊 ĐÁNH GIÁ TRUY XUẤT OFFLINE (BM25 + gộp parent, không gọi mạng)")
        print("=" * 66)
        for key in ("total_questions", "hit@1", "hit@3", "hit@5", "mrr", "ndcg@5"):
            print(f"  {key:>16}: {summary[key]}")

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "items": per_item}, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"\n  💾 Đã lưu: {output_path}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Đánh giá truy xuất offline (không cần API key)")
    parser.add_argument("--dataset", default=None, help="Đường dẫn bộ câu hỏi kiểm thử")
    parser.add_argument("--output", default=None, help="Đường dẫn lưu báo cáo JSON")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    run_offline_eval(dataset_path=args.dataset, output_path=args.output, top_k=args.top_k)


if __name__ == "__main__":
    main()
