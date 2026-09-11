"""
Script kiểm thử E2E hệ thống Agent Luật Giao Thông (đồ thị LangGraph StateGraph)
Kiểm tra 5 kịch bản chính:
1. Biển báo giao thông (QCVN 41:2019) kèm hiển thị ảnh minh họa Markdown
2. Quy định tốc độ xe chạy (Thông tư 31/2019)
3. Thẩm quyền CSGT dừng xe & giá trị pháp lý giấy tờ VNeID (Thông tư 73/2024)
4. Mức phạt tiền & trừ điểm nồng độ cồn ô tô (Nghị định 168/2024)
5. Phân hạng giấy phép lái xe C1 & độ tuổi (Luật 36/2024)
"""

import os
import sys
import json
import time

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.agent import LegalAgent

TEST_CASES = [
    {
        "id": "TC1_TRAFFIC_SIGN",
        "title": "Tra cứu Biển báo giao thông P.106a (QCVN 41:2019)",
        "query": "Biển P.106a là biển gì, có ý nghĩa như thế nào?",
        "expected_keywords": ["P.106a", "cấm xe ô tô tải", "QCVN 41"],
        "expected_image": True,
        "expected_doc": "QCVN 41:2019/BGTVT"
    },
    {
        "id": "TC2_SPEED_LIMIT",
        "title": "Tra cứu Tốc độ xe máy trong khu đông dân cư (Thông tư 31/2019)",
        "query": "Tốc độ tối đa của xe máy trong khu vực đông dân cư là bao nhiêu km/h?",
        "expected_keywords": ["60", "50", "km/h", "Thông tư 31"],
        "expected_image": False,
        "expected_doc": "Thông tư 31/2019/TT-BGTVT"
    },
    {
        "id": "TC3_CSGT_VNEID",
        "title": "Thẩm quyền CSGT dừng xe & Kiểm tra giấy tờ qua VNeID (Thông tư 73/2024 & Luật 36/2024)",
        "query": "Cảnh sát giao thông được dừng xe trong những trường hợp nào? Kiểm tra giấy tờ qua VNeID có được chấp nhận không?",
        "expected_keywords": ["trường hợp", "VNeID"],
        "expected_image": False,
        "expected_docs": ["Thông tư 73", "Luật 36"]
    },
    {
        "id": "TC4_PENALTY_ALCOHOL",
        "title": "Mức phạt nồng độ cồn ô tô (Nghị định 168/2024)",
        "query": "Uống rượu lái xe ô tô bị phạt bao nhiêu tiền?",
        "expected_keywords": ["6.000.000", "16.000.000", "30.000.000", "Nghị định 168"],
        "expected_image": False,
        "expected_doc": "Nghị định 168/2024/NĐ-CP"
    },
    {
        "id": "TC5_LICENSE_C1",
        "title": "Phân hạng GPLX C1 & Độ tuổi dự sát hạch (Luật 36/2024)",
        "query": "Bằng lái xe C1 được điều khiển xe gì, bao nhiêu tuổi được thi?",
        "expected_keywords": ["C1", "3.500", "7.500", "18 tuổi", "Luật"],
        "expected_image": False,
        "expected_doc": "Luật 36/2024/QH15"
    }
]

def main():
    print("=" * 75, flush=True)
    print(" 🚀 BẮT ĐẦU KIỂM THỬ E2E HỆ THỐNG AGENT (LANGGRAPH) VỚI 6 VĂN BẢN PHÁP LUẬT", flush=True)
    print("=" * 75, flush=True)

    agent = LegalAgent()
    results = []
    total_passed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] 🧪 KIỂM THỬ: {tc['title']}", flush=True)
        print(f"  Câu hỏi: \"{tc['query']}\"", flush=True)

        start_t = time.time()
        res = agent.run_agent(tc["query"], max_turns=3)
        elapsed = time.time() - start_t

        answer = res.get("answer", "")
        agent_steps = res.get("agent_steps", [])
        sources = res.get("sources", [])
        verification_issues = res.get("verification_issues", [])

        # Kiểm tra điều kiện đạt
        checks = {}

        # 1. Từ khóa mong đợi
        matched_kw = [kw for kw in tc["expected_keywords"] if kw.lower() in answer.lower()]
        checks["keywords"] = len(matched_kw) >= (len(tc["expected_keywords"]) - 1)

        # 2. Ảnh minh họa (nếu là biển báo)
        if tc["expected_image"]:
            has_markdown_img = "![" in answer and "/data/images/" in answer
            checks["image_rendered"] = has_markdown_img
        else:
            checks["image_rendered"] = True

        # 3. Nguồn trích dẫn văn bản
        exp_docs = tc.get("expected_docs") or [tc.get("expected_doc")]
        doc_cited = any(
            any(
                ed.lower() in str(src.get("doc_name", "")).lower() or
                ed.lower() in str(src.get("citation", "")).lower()
                for src in sources
            ) or any(ed.lower() in answer.lower() for ed in exp_docs)
            for ed in exp_docs
        )
        checks["document_cited"] = doc_cited

        # 4. Không bị lỗi kiểm chứng
        checks["no_verification_errors"] = len(verification_issues) == 0

        passed = all(checks.values())
        if passed:
            total_passed += 1
            status_str = "✅ ĐẠT (PASSED)"
        else:
            status_str = "❌ CHƯA ĐẠT (FAILED)"

        print(f"  Kết quả: {status_str} (Thời gian: {elapsed:.2f}s, Tool calls: {len(agent_steps)})", flush=True)
        print(f"  Chi tiết checks: {checks}", flush=True)
        if tc["expected_image"]:
            print(f"  Đã render ảnh: {checks['image_rendered']}", flush=True)
        print(f"  Đoạn trích câu trả lời:\n  {answer[:250].replace(chr(10), ' ')}...\n", flush=True)

        results.append({
            "test_id": tc["id"],
            "title": tc["title"],
            "query": tc["query"],
            "passed": passed,
            "checks": checks,
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls_count": len(agent_steps),
            "sources_count": len(sources),
            "answer_preview": answer[:300]
        })

    print("=" * 75, flush=True)
    print(f" 🏁 TỔNG KẾT KIỂM THỬ: {total_passed}/{len(TEST_CASES)} KỊCH BẢN ĐẠT ({total_passed/len(TEST_CASES)*100:.1f}%)", flush=True)
    print("=" * 75, flush=True)

    # Lưu báo cáo vào data/benchmark/e2e_verification_report.json
    out_dir = os.path.join(base_dir, "data", "benchmark")
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "e2e_verification_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tests": len(TEST_CASES),
            "passed_tests": total_passed,
            "pass_rate": f"{total_passed/len(TEST_CASES)*100:.1f}%",
            "results": results
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 Đã lưu báo cáo chi tiết tại: {report_file}", flush=True)

if __name__ == "__main__":
    main()
