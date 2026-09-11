"""
Đánh giá Toàn trình End-to-End RAG (E2E Benchmark Runner)
Đo lường 6 chỉ số chất lượng câu trả lời thực tế:
1. Độ chính xác trích dẫn (Citation Accuracy)
2. Tỉ lệ số liệu không có căn cứ (Ungrounded Figures Rate)
3. Độ chính xác từ chối khi hỏi ngoài phạm vi (Out-of-Scope Refusal Rate)
4. Tỉ lệ câu trả lời bị hủy / cảnh báo (Cancelled Answer Rate)
5. Độ trễ phân vị (p50, p90, p95 ms)
6. Chi phí ước tính mỗi câu hỏi ($/query)
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
from scripts.eval.metrics import (
    check_citation_accuracy,
    check_out_of_scope_refusal,
    compute_latency_stats,
    estimate_token_cost,
)
from scripts.eval.adapters import get_adapter
from src.answer_guard import find_ungrounded_figures
from src.guard_figures import money_values


def run_e2e_eval(
    dataset_path: Optional[str] = None,
    adapter_type: str = "graph",
    doc_filter: Optional[str] = None,
    cat_filter: Optional[str] = None,
    quick_limit: Optional[int] = None,
    output_path: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    if not dataset_path:
        dataset_path = os.path.join(base_dir, "data", "benchmark", "qa_testset_v2.json")
        if not os.path.exists(dataset_path):
            dataset_path = os.path.join(base_dir, "data", "benchmark", "qa_testset.json")

    dataset = load_dataset(dataset_path)
    items = filter_dataset(
        dataset,
        doc_id=doc_filter,
        category=cat_filter,
        quick_limit=quick_limit,
        include_out_of_scope=True
    )

    total = len(items)
    if total == 0:
        print("⚠️ Không có câu hỏi nào để đánh giá E2E.")
        return {}

    if verbose:
        print("==================================================================")
        print(f" 🚀 BẮT ĐẦU ĐÁNH GIÁ E2E AGENT ({total} CÂU HỎI)")
        print(f"    Adapter: {adapter_type.upper()}")
        print(f"    Tập dữ liệu: {os.path.basename(dataset_path)}")
        if quick_limit:
            print(f"    Chế độ nhanh: {quick_limit} câu")
        print("==================================================================")

    adapter = get_adapter(adapter_type=adapter_type, verbose=False)

    citation_checks = []
    ungrounded_count = 0
    refusal_checks = []
    cancelled_count = 0
    latencies = []
    total_tokens_in = 0
    total_tokens_out = 0
    detailed_results = []

    start_all_time = time.time()

    for idx, item in enumerate(items, 1):
        q_text = item.question
        history = [m.model_dump() for m in item.history] if item.history else None
        
        if verbose:
            tag = "[OUT-OF-SCOPE]" if item.is_out_of_scope else f"[{item.category}]"
            print(f"[{idx:02d}/{total}] Đang xử lý: {q_text[:65]}... {tag}", flush=True)

        # Chạy agent qua adapter
        try:
            res = adapter.run(q_text, history=history)
        except Exception as e:
            if verbose:
                print(f"    ❌ Lỗi khi chạy câu hỏi {item.id}: {e}", flush=True)
            res = {
                "answer": "",
                "sources": [],
                "agent_steps": [],
                "verification_issues": [f"Runner error: {str(e)}"],
                "needs_search": True,
                "latency_ms": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "raw_tool_outputs": []
            }

        answer = res.get("answer", "")
        sources = res.get("sources", [])
        raw_tool_outputs = res.get("raw_tool_outputs", [])
        issues = res.get("verification_issues", [])
        needs_search = res.get("needs_search", False)
        lat_ms = res.get("latency_ms", 0.0)
        tok_in = res.get("tokens_in", 0)
        tok_out = res.get("tokens_out", 0)

        latencies.append(lat_ms)
        total_tokens_in += tok_in
        total_tokens_out += tok_out

        # 1. Kiểm tra trích dẫn kỳ vọng (cho câu in-scope có expected_citation)
        is_cit_ok = check_citation_accuracy(answer, sources, item.expected_citation)
        if is_cit_ok is not None:
            citation_checks.append(is_cit_ok)

        # 2. Kiểm tra số liệu không căn cứ bằng answer_guard
        ungrounded = find_ungrounded_figures(answer, raw_tool_outputs)
        has_ungrounded = (len(ungrounded) > 0)
        if has_ungrounded:
            ungrounded_count += 1

        # 3. Kiểm tra từ chối đúng khi hỏi ngoài phạm vi
        money_in_ans = len(money_values(answer)) if answer else 0
        is_refusal_ok = check_out_of_scope_refusal(item.is_out_of_scope, needs_search, answer, money_in_ans)
        if is_refusal_ok is not None:
            refusal_checks.append(is_refusal_ok)

        # 4. Kiểm tra câu trả lời bị hủy hoặc có vi phạm kiểm chứng
        has_verification_issue = (len(issues) > 0)
        if has_verification_issue:
            cancelled_count += 1

        detailed_results.append({
            "id": item.id,
            "category": item.category,
            "question": q_text,
            "is_out_of_scope": item.is_out_of_scope,
            "expected_citation": item.expected_citation,
            "citation_ok": is_cit_ok,
            "has_ungrounded_figures": has_ungrounded,
            "ungrounded_details": ungrounded,
            "refusal_ok": is_refusal_ok,
            "has_verification_issue": has_verification_issue,
            "verification_issues": issues,
            "latency_ms": round(lat_ms, 2),
            "tokens_in": tok_in,
            "tokens_out": tok_out,
            "sources_count": len(sources),
            "answer_preview": answer[:120] + "..." if len(answer) > 120 else answer
        })

    total_time = round(time.time() - start_all_time, 2)
    
    # Tính các tỉ lệ phần trăm
    cit_acc_pct = round((sum(1 for c in citation_checks if c) / len(citation_checks)) * 100, 2) if citation_checks else 100.0
    ungrounded_rate_pct = round((ungrounded_count / total) * 100, 2)
    refusal_acc_pct = round((sum(1 for r in refusal_checks if r) / len(refusal_checks)) * 100, 2) if refusal_checks else 100.0
    cancelled_rate_pct = round((cancelled_count / total) * 100, 2)
    
    latency_stats = compute_latency_stats(latencies)
    cost_total = estimate_token_cost(total_tokens_in, total_tokens_out, "default")
    cost_per_query = round(cost_total / total, 6)

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "adapter": adapter_type,
        "dataset": os.path.basename(dataset_path),
        "total_questions": total,
        "elapsed_seconds": total_time,
        "metrics": {
            "citation_accuracy_pct": cit_acc_pct,
            "ungrounded_figures_rate_pct": ungrounded_rate_pct,
            "out_of_scope_refusal_pct": refusal_acc_pct,
            "cancelled_answer_rate_pct": cancelled_rate_pct,
            "latency_p50_ms": latency_stats["p50_ms"],
            "latency_p90_ms": latency_stats["p90_ms"],
            "latency_p95_ms": latency_stats["p95_ms"],
            "latency_mean_ms": latency_stats["mean_ms"],
            "estimated_cost_usd_total": cost_total,
            "estimated_cost_usd_per_query": cost_per_query,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out
        },
        "latency_details": latency_stats,
        "detailed_results": detailed_results
    }

    if verbose:
        print("\n" + "=" * 65)
        print(" 🏆 TỔNG KẾT HIỆU NĂNG E2E AGENT")
        print("=" * 65)
        print(f" Tổng số câu hỏi kiểm thử:            {total}")
        print(f" 🎯 Độ chính xác trích dẫn (E2E):      {cit_acc_pct:.2f}% (trên {len(citation_checks)} câu yêu cầu dẫn chứng)")
        print(f" 🛡️  Tỉ lệ số liệu không căn cứ:       {ungrounded_rate_pct:.2f}% ({ungrounded_count}/{total} câu vi phạm)")
        print(f" 🚫 Từ chối đúng khi hỏi ngoài phạm vi: {refusal_acc_pct:.2f}% (trên {len(refusal_checks)} câu lạc đề)")
        print(f" ⚠️  Tỉ lệ câu trả lời bị hủy/lỗi:      {cancelled_rate_pct:.2f}% ({cancelled_count}/{total})")
        print(f" ⏱️  Độ trễ p50 / p90 / p95:           {latency_stats['p50_ms']:.1f}ms / {latency_stats['p90_ms']:.1f}ms / {latency_stats['p95_ms']:.1f}ms")
        print(f" 💰 Chi phí ước tính trung bình:       ${cost_per_query:.6f} / câu (${cost_total:.4f} tổng cộng)")
        print("=" * 65)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"-> Đã ghi báo cáo E2E tại: {output_path}\n")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Chạy đánh giá E2E RAG Agent")
    parser.add_argument("--adapter", type=str, default="graph", choices=["graph"], help="Loại adapter (chỉ còn graph: LegacyAdapter đã gỡ ở Phase 8)")
    parser.add_argument("--dataset", type=str, default=None, help="Đường dẫn file dataset benchmark")
    parser.add_argument("--doc", type=str, default=None, help="Lọc theo văn bản")
    parser.add_argument("--category", type=str, default=None, help="Lọc theo phân loại câu hỏi")
    parser.add_argument("--quick", type=int, default=None, help="Chế độ nhanh: chỉ chạy N câu")
    parser.add_argument("--out", type=str, default=os.path.join(base_dir, "data", "benchmark", "e2e_evaluation_report.json"), help="File lưu báo cáo")
    args = parser.parse_args()

    run_e2e_eval(
        dataset_path=args.dataset,
        adapter_type=args.adapter,
        doc_filter=args.doc,
        cat_filter=args.category,
        quick_limit=args.quick,
        output_path=args.out
    )


if __name__ == "__main__":
    main()
