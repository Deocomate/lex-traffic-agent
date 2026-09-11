"""
Cổng chặn Hồi quy (Regression Gate)
So sánh báo cáo đánh giá hiện tại với tệp baseline đối chứng theo các ngưỡng đã định trong plan.md:
- Hit@1: không thấp hơn baseline
- Hit@3: không thấp hơn baseline
- MRR: không thấp hơn baseline
- Citation Accuracy (E2E): >= 95.0%
- Ungrounded figures rate: = 0.0%
- Out-of-scope refusal rate: >= 90.0%
- Cancelled answers rate: không tăng so với baseline
- Latency p50: không tăng quá 10%

Trả về exit code 0 nếu đạt, exit code 1 nếu vi phạm bất kỳ cổng chặn nào.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)


def check_gate(
    baseline_path: str,
    current_path: str,
    strict: bool = True
) -> bool:
    if not os.path.exists(baseline_path):
        print(f"❌ Không tìm thấy file baseline tại: {baseline_path}")
        return False

    if not os.path.exists(current_path):
        print(f"❌ Không tìm thấy file current report tại: {current_path}")
        return False

    with open(baseline_path, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    with open(current_path, "r", encoding="utf-8") as f:
        curr_data = json.load(f)

    base_m = base_data.get("metrics", {})
    curr_m = curr_data.get("metrics", {})

    print("==================================================================")
    print(" 🚪 KIỂM TRA CỔNG CHẶN HỒI QUY (REGRESSION GATE CHECK)")
    print(f"    Baseline : {os.path.basename(baseline_path)}")
    print(f"    Current  : {os.path.basename(current_path)}")
    print("==================================================================")

    # Định nghĩa các cổng kiểm tra: (tên_chỉ_số, khóa, ngưỡng_tối_thiểu, so_sánh_baseline, đơn vị)
    # so_sánh_baseline: 'no_drop' (không được giảm), 'no_increase' (không được tăng), 'max_10pct_increase'
    checks: List[Tuple[str, str, str]] = []
    
    # 1. Retrieval metrics (nếu có trong report)
    if "hit_rate_at_1" in base_m and "hit_rate_at_1" in curr_m:
        b_val = float(base_m["hit_rate_at_1"])
        c_val = float(curr_m["hit_rate_at_1"])
        passed = (c_val >= b_val - 0.05)  # cho phép sai số làm tròn 0.05%
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Hit@1: Baseline={b_val:.2f}% -> Hiện tại={c_val:.2f}% (Yêu cầu: không tụt)")
        checks.append(("Hit@1", status, f"{b_val:.2f}% -> {c_val:.2f}%"))

    if "hit_rate_at_3" in base_m and "hit_rate_at_3" in curr_m:
        b_val = float(base_m["hit_rate_at_3"])
        c_val = float(curr_m["hit_rate_at_3"])
        passed = (c_val >= b_val - 0.05)
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Hit@3: Baseline={b_val:.2f}% -> Hiện tại={c_val:.2f}% (Yêu cầu: không tụt)")
        checks.append(("Hit@3", status, f"{b_val:.2f}% -> {c_val:.2f}%"))

    if "mrr" in base_m and "mrr" in curr_m:
        b_val = float(base_m["mrr"])
        c_val = float(curr_m["mrr"])
        passed = (c_val >= b_val - 0.001)
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] MRR: Baseline={b_val:.4f} -> Hiện tại={c_val:.4f} (Yêu cầu: không tụt)")
        checks.append(("MRR", status, f"{b_val:.4f} -> {c_val:.4f}"))

    # 2. E2E metrics (nếu có)
    if "citation_accuracy_pct" in curr_m:
        c_val = float(curr_m["citation_accuracy_pct"])
        # Mục tiêu plan.md: >= 95.0%
        passed = (c_val >= 95.0) if strict else (c_val >= float(base_m.get("citation_accuracy_pct", 90.0)))
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Citation Accuracy: {c_val:.2f}% (Ngưỡng: >= 95.0%)")
        checks.append(("Citation Accuracy", status, f"{c_val:.2f}%"))

    if "ungrounded_figures_rate_pct" in curr_m:
        c_val = float(curr_m["ungrounded_figures_rate_pct"])
        # Mục tiêu plan.md: 0.0%
        passed = (c_val == 0.0)
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Ungrounded Figures Rate: {c_val:.2f}% (Ngưỡng: = 0.0%)")
        checks.append(("Ungrounded Figures", status, f"{c_val:.2f}%"))

    if "out_of_scope_refusal_pct" in curr_m:
        c_val = float(curr_m["out_of_scope_refusal_pct"])
        # Mục tiêu plan.md: >= 90.0%
        passed = (c_val >= 90.0)
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Out-of-Scope Refusal: {c_val:.2f}% (Ngưỡng: >= 90.0%)")
        checks.append(("Refusal Rate", status, f"{c_val:.2f}%"))

    if "cancelled_answer_rate_pct" in base_m and "cancelled_answer_rate_pct" in curr_m:
        b_val = float(base_m["cancelled_answer_rate_pct"])
        c_val = float(curr_m["cancelled_answer_rate_pct"])
        passed = (c_val <= b_val + 0.05)
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Cancelled Answers: Baseline={b_val:.2f}% -> Hiện tại={c_val:.2f}% (Yêu cầu: không tăng)")
        checks.append(("Cancelled Answers", status, f"{b_val:.2f}% -> {c_val:.2f}%"))

    if "latency_p50_ms" in base_m and "latency_p50_ms" in curr_m:
        b_val = float(base_m["latency_p50_ms"])
        c_val = float(curr_m["latency_p50_ms"])
        max_allowed = b_val * 1.10
        passed = (c_val <= max_allowed)
        status = "PASSED" if passed else "FAILED"
        print(f" [{status}] Latency p50: Baseline={b_val:.1f}ms -> Hiện tại={c_val:.1f}ms (Tối đa +10%: {max_allowed:.1f}ms)")
        checks.append(("Latency p50", status, f"{b_val:.1f}ms -> {c_val:.1f}ms"))

    all_passed = all(st == "PASSED" for _, st, _ in checks)
    print("==================================================================")
    if all_passed:
        print(" 🎉 KẾT QUẢ: TOÀN BỘ CỔNG CHẶN HỢP LỆ! EXIT 0.")
    else:
        print(" ❌ KẾT QUẢ: PHÁT HIỆN HỒI QUY HOẶC VI PHẠM CỔNG CHẶN! EXIT 1.")
    print("==================================================================")
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra cổng chặn hồi quy giữa 2 báo cáo đánh giá")
    parser.add_argument("--baseline", type=str, required=True, help="Đường dẫn file baseline chuẩn")
    parser.add_argument("--current", type=str, required=True, help="Đường dẫn file đánh giá hiện tại")
    parser.add_argument("--lax", action="store_true", help="Nới lỏng một số tiêu chí nếu đang đo giai đoạn thử nghiệm")
    args = parser.parse_args()

    passed = check_gate(
        baseline_path=args.baseline,
        current_path=args.current,
        strict=not args.lax
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
