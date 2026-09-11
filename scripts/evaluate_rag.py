"""
Script đánh giá tự động hiệu năng truy xuất (Retrieval Benchmark) của hệ thống RAG.
Wrapper mỏng tương thích ngược gọi scripts.eval.retrieval_eval.
"""

import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from scripts.eval.retrieval_eval import run_retrieval_eval


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Script đánh giá tự động hiệu năng truy xuất RAG (Legacy Wrapper)")
    parser.add_argument("--quick", type=int, default=None, help="Số câu chạy nhanh")
    args, _ = parser.parse_known_args()

    # Giữ nguyên hành vi mặc định của lệnh cũ: chạy trên qa_testset.json và xuất evaluation_report.json
    dataset_path = os.path.join(base_dir, "data", "benchmark", "qa_testset.json")
    output_path = os.path.join(base_dir, "data", "benchmark", "evaluation_report.json")
    
    run_retrieval_eval(
        dataset_path=dataset_path,
        doc_filter="01_luat_36_2024_qh15",
        output_path=output_path,
        quick_limit=args.quick,
        top_k=3,
        verbose=True
    )


if __name__ == "__main__":
    main()
