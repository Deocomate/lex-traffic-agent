"""
Đánh giá Hiệu năng Truy xuất (Retrieval Benchmark Runner)
Đo lường các chỉ số Hit@1, Hit@3, Hit@5, MRR, nDCG@5 trên SemanticIndex
Hỗ trợ lọc theo văn bản, danh mục, chế độ --quick và lưu báo cáo chi tiết.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)

from scripts.eval.datasets import load_dataset, filter_dataset, BenchmarkDatasetV2
from scripts.eval.metrics import hit_at_k, reciprocal_rank, ndcg_at_k
from src.semantic_index import SemanticIndex


def run_retrieval_eval(
    dataset_path: Optional[str] = None,
    doc_filter: Optional[str] = None,
    cat_filter: Optional[str] = None,
    quick_limit: Optional[int] = None,
    output_path: Optional[str] = None,
    top_k: int = 5,
    verbose: bool = True,
    retriever: Optional[Any] = None,
    retriever_type: str = "hybrid",
) -> Dict[str, Any]:
    if not dataset_path:
        dataset_path = os.path.join(base_dir, "data", "benchmark", "qa_testset_v2.json")
        if not os.path.exists(dataset_path):
            dataset_path = os.path.join(base_dir, "data", "benchmark", "qa_testset.json")

    dataset = load_dataset(dataset_path)
    
    # Chỉ đánh giá retrieval trên các câu in-scope (có văn bản đối chứng)
    items = filter_dataset(
        dataset,
        doc_id=doc_filter,
        category=cat_filter,
        quick_limit=quick_limit,
        include_out_of_scope=False
    )
    
    total = len(items)
    if total == 0:
        print("⚠️ Không có câu hỏi nào thỏa mãn bộ lọc để đánh giá retrieval.")
        return {}

    if verbose:
        print("==================================================================")
        print(f" 📊 BẮT ĐẦU ĐÁNH GIÁ RETRIEVAL ({total} CÂU HỎI)")
        print(f"    Tập dữ liệu: {os.path.basename(dataset_path)}")
        print(f"    Bộ truy xuất: {retriever_type if retriever is None else type(retriever).__name__}")
        if doc_filter:
            print(f"    Lọc văn bản: {doc_filter}")
        if quick_limit:
            print(f"    Chế độ nhanh: {quick_limit} câu đầu tiên")
        print("==================================================================")

    if retriever is not None:
        rag = retriever
    elif retriever_type == "hybrid":
        from src.retrieval.hybrid import get_hybrid_search
        rag = get_hybrid_search(base_dir)
    else:
        rag = SemanticIndex(base_dir)

    if not getattr(rag, "available", True):
        raise RuntimeError("❌ Bộ truy xuất không khả dụng. Hãy kiểm tra data/processed/")


    hit1_count = 0
    hit3_count = 0
    hit5_count = 0
    rr_list = []
    ndcg5_list = []
    
    doc_stats: Dict[str, Dict[str, Any]] = {}
    detailed_results = []
    
    start_eval_time = time.time()

    for idx, item in enumerate(items, 1):
        q_text = item.question
        doc_id = item.target_doc_id or "unknown"
        target_pid = item.target_parent_id
        target_art = item.target_article_number

        # Truy xuất top_k kết quả từ chỉ mục
        # Nếu có lọc văn bản cụ thể (doc_filter), giới hạn phạm vi truy xuất vào văn bản đó
        allowed_docs = [doc_filter] if doc_filter else None
        retrieved_docs = rag.retrieve_articles(q_text, doc_ids=allowed_docs, top_k=top_k)
        retrieved_pids = [d.get("parent_id") for d in retrieved_docs]
        retrieved_arts = [d.get("article_number") for d in retrieved_docs]

        # Xác định target: ưu tiên target_parent_id; nếu là Luật 36 và target_art có thể so cả article_number
        target_candidates = []
        if target_pid:
            if isinstance(target_pid, list):
                target_candidates.extend(target_pid)
            else:
                target_candidates.append(target_pid)
        
        # Nếu so theo parent_id
        is_hit_1 = hit_at_k(retrieved_pids, target_candidates, 1) > 0.0
        is_hit_3 = hit_at_k(retrieved_pids, target_candidates, 3) > 0.0
        is_hit_5 = hit_at_k(retrieved_pids, target_candidates, 5) > 0.0
        rr = reciprocal_rank(retrieved_pids, target_candidates)
        ndcg5 = ndcg_at_k(retrieved_pids, target_candidates, 5)

        # Fallback cho trường hợp Luật 36 câu cũ: nếu khớp số Điều trong Luật 36 thì cũng chấp nhận
        if not is_hit_1 and target_art and (doc_id == "01_luat_36_2024_qh15"):
            if retrieved_arts and retrieved_arts[0] == target_art:
                is_hit_1 = True
            if target_art in retrieved_arts[:3]:
                is_hit_3 = True
            if target_art in retrieved_arts[:5]:
                is_hit_5 = True
            if target_art in retrieved_arts:
                rr = max(rr, 1.0 / (retrieved_arts.index(target_art) + 1))
                rank_art = retrieved_arts.index(target_art) + 1
                if rank_art <= 5:
                    import math
                    ndcg5 = max(ndcg5, 1.0 / math.log2(rank_art + 1))

        if is_hit_1:
            hit1_count += 1
        if is_hit_3:
            hit3_count += 1
        if is_hit_5:
            hit5_count += 1
        rr_list.append(rr)
        ndcg5_list.append(ndcg5)

        # Phân tích theo doc_id
        if doc_id not in doc_stats:
            doc_stats[doc_id] = {"count": 0, "hit1": 0, "hit3": 0, "rr": []}
        doc_stats[doc_id]["count"] += 1
        if is_hit_1:
            doc_stats[doc_id]["hit1"] += 1
        if is_hit_3:
            doc_stats[doc_id]["hit3"] += 1
        doc_stats[doc_id]["rr"].append(rr)

        status = "✅ TOP 1" if is_hit_1 else ("🟡 TOP 3" if is_hit_3 else ("🔵 TOP 5" if is_hit_5 else "❌ MISSED"))
        
        display_retrieved = []
        for d in retrieved_docs[:3]:
            pid = d.get("parent_id", "")
            art = d.get("article_number")
            display_retrieved.append(f"Đ.{art}" if art else pid[:20])

        if verbose:
            print(f"[{idx:02d}/{total}] {status} | Target: {target_pid or target_art} -> KQ: {display_retrieved} | {item.category}")

        detailed_results.append({
            "id": item.id,
            "category": item.category,
            "question": q_text,
            "target_doc_id": doc_id,
            "target_parent_id": target_pid,
            "target_article_number": target_art,
            "retrieved_parents": retrieved_pids,
            "is_hit_1": is_hit_1,
            "is_hit_3": is_hit_3,
            "is_hit_5": is_hit_5,
            "reciprocal_rank": rr,
            "ndcg_at_5": ndcg5
        })

    elapsed_time = round(time.time() - start_eval_time, 2)
    acc_hit1 = round((hit1_count / total) * 100, 2)
    acc_hit3 = round((hit3_count / total) * 100, 2)
    acc_hit5 = round((hit5_count / total) * 100, 2)
    mean_mrr = round(sum(rr_list) / total, 4)
    mean_ndcg5 = round(sum(ndcg5_list) / total, 4)

    # Tổng kết theo từng văn bản
    doc_breakdown = {}
    for d_id, s in doc_stats.items():
        c = s["count"]
        doc_breakdown[d_id] = {
            "questions": c,
            "hit_at_1": round((s["hit1"] / c) * 100, 2),
            "hit_at_3": round((s["hit3"] / c) * 100, 2),
            "mrr": round(sum(s["rr"]) / c, 4)
        }

    summary = {
        "dataset": os.path.basename(dataset_path),
        "total_evaluated": total,
        "elapsed_seconds": elapsed_time,
        "metrics": {
            "hit_rate_at_1": acc_hit1,
            "hit_rate_at_3": acc_hit3,
            "hit_rate_at_5": acc_hit5,
            "mrr": mean_mrr,
            "ndcg_at_5": mean_ndcg5
        },
        "doc_breakdown": doc_breakdown,
        "detailed_results": detailed_results
    }

    if verbose:
        print("\n" + "=" * 65)
        print(" 🏆 TỔNG KẾT HIỆU NĂNG RETRIEVAL")
        print("=" * 65)
        print(f" Tổng số câu hỏi kiểm thử:        {total}")
        print(f" 🎯 Độ chính xác Top-1 (Hit@1):   {acc_hit1:.2f}% ({hit1_count}/{total})")
        print(f" 🎯 Độ chính xác Top-3 (Hit@3):   {acc_hit3:.2f}% ({hit3_count}/{total})")
        print(f" 🎯 Độ chính xác Top-5 (Hit@5):   {acc_hit5:.2f}% ({hit5_count}/{total})")
        print(f" 📈 Mean Reciprocal Rank (MRR):    {mean_mrr:.4f}")
        print(f" 📈 nDCG@5:                        {mean_ndcg5:.4f}")
        print(f" ⏱️  Thời gian đánh giá:           {elapsed_time}s")
        print("=" * 65)
        print(" 📂 PHÂN BỐ THEO TỪNG VĂN BẢN:")
        for d_id, b in doc_breakdown.items():
            print(f"  • {d_id[:28]:<28}: Hit@1={b['hit_at_1']:>5.1f}% | Hit@3={b['hit_at_3']:>5.1f}% | MRR={b['mrr']:.4f} ({b['questions']} câu)")
        print("=" * 65)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"-> Đã ghi báo cáo retrieval tại: {output_path}\n")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Chạy đánh giá retrieval trên chỉ mục ngữ nghĩa")
    parser.add_argument("--dataset", type=str, default=None, help="Đường dẫn file dataset benchmark")
    parser.add_argument("--doc", type=str, default=None, help="Lọc theo mã văn bản (vd: luat_36, nghi_dinh_168)")
    parser.add_argument("--category", type=str, default=None, help="Lọc theo phân loại câu hỏi")
    parser.add_argument("--quick", type=int, default=None, help="Chế độ nhanh: chỉ chạy N câu đầu tiên")
    parser.add_argument("--retriever", type=str, choices=["hybrid", "semantic"], default="hybrid", help="Chọn bộ truy xuất: hybrid (mặc định) hoặc semantic (vector cũ)")
    parser.add_argument("--out", type=str, default=os.path.join(base_dir, "data", "benchmark", "evaluation_report.json"), help="Đường dẫn file lưu báo cáo")
    args = parser.parse_args()

    run_retrieval_eval(
        dataset_path=args.dataset,
        doc_filter=args.doc,
        cat_filter=args.category,
        quick_limit=args.quick,
        output_path=args.out,
        retriever_type=args.retriever,
    )



if __name__ == "__main__":
    main()
