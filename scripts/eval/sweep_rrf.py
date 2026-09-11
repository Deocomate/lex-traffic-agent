"""
Script quét siêu tham số RRF (Hyperparameter Sweep):
Quét w_dense trong {0.4, 0.5, 0.6, 0.7, 0.8} (với w_sparse = 1.0 - w_dense)
và k trong {10, 30, 60} trên bộ dữ liệu benchmark in-scope.
Lựa chọn cấu hình tối ưu theo MRR và Hit@1, ghi kết quả so sánh chi tiết.
"""

import argparse
import itertools
import json
import os
import sys
import time
from typing import Any, Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)

from scripts.eval.retrieval_eval import run_retrieval_eval
from src.retrieval.hybrid import HybridSearch, get_hybrid_search


def sweep_rrf(dataset_path: str = None, quick_limit: int = None, output_path: str = None):
    dense_weights = [0.4, 0.5, 0.6, 0.7, 0.8]
    k_values = [10, 30, 60]

    print("=" * 70)
    print(" 🔍 BẮT ĐẦU QUÉT SIÊU THAM SỐ RRF (w_dense, w_sparse, k)")
    print(f"    w_dense options : {dense_weights}")
    print(f"    k options       : {k_values}")
    if quick_limit:
        print(f"    Chế độ nhanh    : {quick_limit} câu")
    print("=" * 70)

    hybrid_engine = get_hybrid_search(base_dir=base_dir)

    results = []
    best_config = None
    best_mrr = -1.0
    best_hit1 = -1.0

    # Chạy lần đầu 1 lượt để nạp toàn bộ query vào SQLite vector cache
    print("⚡ Khởi động và đảm bảo cache vector sẵn sàng...")
    run_retrieval_eval(
        dataset_path=dataset_path,
        quick_limit=quick_limit,
        retriever=hybrid_engine,
        verbose=False,
    )
    print("✅ Cache vector đã sẵn sàng. Bắt đầu quét không tốn chi phí API!\n")

    grid = list(itertools.product(dense_weights, k_values))
    total_runs = len(grid)

    for idx, (w_d, k_val) in enumerate(grid, 1):
        w_s = round(1.0 - w_d, 2)
        
        # Cập nhật trọng số tạm thời cho engine
        hybrid_engine.w_dense = w_d
        hybrid_engine.w_sparse = w_s
        hybrid_engine.k = k_val

        t0 = time.time()
        summary = run_retrieval_eval(
            dataset_path=dataset_path,
            quick_limit=quick_limit,
            retriever=hybrid_engine,
            verbose=False,
        )
        elapsed = round(time.time() - t0, 2)

        m = summary.get("metrics", {})
        hit1 = m.get("hit_rate_at_1", 0.0)
        hit3 = m.get("hit_rate_at_3", 0.0)
        hit5 = m.get("hit_rate_at_5", 0.0)
        mrr = m.get("mrr", 0.0)
        ndcg5 = m.get("ndcg_at_5", 0.0)


        record = {
            "w_dense": w_d,
            "w_sparse": w_s,
            "k": k_val,
            "hit_at_1": hit1,
            "hit_at_3": hit3,
            "hit_at_5": hit5,
            "mrr": mrr,
            "ndcg_at_5": ndcg5,
            "elapsed_s": elapsed,
        }
        results.append(record)

        is_best = False
        if mrr > best_mrr or (mrr == best_mrr and hit1 > best_hit1):
            best_mrr = mrr
            best_hit1 = hit1
            best_config = record
            is_best = True

        tag = "⭐ BEST" if is_best else ""
        print(
            f"[{idx:02d}/{total_runs}] w_dense={w_d:.1f}, w_sparse={w_s:.1f}, k={k_val:2d} | "
            f"Hit@1={hit1:5.1f}% | Hit@3={hit3:5.1f}% | MRR={mrr:.4f} | {elapsed}s {tag}"
        )

    # Đặt lại trọng số của engine về cấu hình tốt nhất
    if best_config:
        hybrid_engine.w_dense = best_config["w_dense"]
        hybrid_engine.w_sparse = best_config["w_sparse"]
        hybrid_engine.k = best_config["k"]

    print("\n" + "=" * 70)
    print(" 🏆 CẤU HÌNH RRF CHIẾN THẮNG TỐI ƯU")
    print("=" * 70)
    print(f" w_dense : {best_config['w_dense']}")
    print(f" w_sparse: {best_config['w_sparse']}")
    print(f" k       : {best_config['k']}")
    print(f" Hit@1   : {best_config['hit_at_1']:.2f}%")
    print(f" Hit@3   : {best_config['hit_at_3']:.2f}%")
    print(f" MRR     : {best_config['mrr']:.4f}")
    print(f" nDCG@5  : {best_config['ndcg_at_5']:.4f}")
    print("=" * 70)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "best_config": best_config,
                "all_results": results,
            }, f, ensure_ascii=False, indent=2)
        print(f"-> Đã ghi báo cáo sweep tại: {output_path}\n")

    return best_config, results


def main():
    parser = argparse.ArgumentParser(description="Quét trọng số RRF trên bộ dữ liệu benchmark")
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--quick", type=int, default=None)
    parser.add_argument("--out", type=str, default=os.path.join(base_dir, "data", "benchmark", "rrf_sweep_report.json"))
    args = parser.parse_args()

    sweep_rrf(dataset_path=args.dataset, quick_limit=args.quick, output_path=args.out)


if __name__ == "__main__":
    main()
