"""
Script kiến tạo bộ Benchmark mở rộng V2 (95 câu hỏi):
- 35 câu gốc (Luật 36/2024/QH15) từ qa_testset.json -> migrate sang schema v2
- 16 câu Nghị định 168/2024/NĐ-CP (mức phạt, trừ điểm, tạm giữ xe)
- 8 câu QCVN 41:2019/BGTVT (biển báo cấm, hiệu lệnh, vạch kẻ đường)
- 6 câu Thông tư 31/2019/TT-BGTVT (tốc độ tối đa, khoảng cách an toàn)
- 6 câu Thông tư 73/2024/TT-BCA (quyền dừng xe của CSGT, kiểm soát VNeID)
- 8 câu Luật Đường bộ 35/2024/QH15 (kết cấu hạ tầng, cao tốc, kinh doanh vận tải)
- 16 câu Out-of-scope / Negative (bẫy từ khóa giao thông, câu hỏi ngoài phạm vi luật)
- Bao gồm 5 câu hỏi có ngữ cảnh hội thoại đa lượt (history)
"""

import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)

from scripts.eval.datasets import BenchmarkDatasetV2, QAItemV2, ExpectedFigures, HistoryMessage, save_dataset


def build_v2_benchmark():
    parents_path = os.path.join(base_dir, "data", "processed", "semantic_parents.json")
    with open(parents_path, "r", encoding="utf-8") as f:
        parents = json.load(f)

    # 1. Nạp 35 câu cũ
    legacy_path = os.path.join(base_dir, "data", "benchmark", "qa_testset.json")
    with open(legacy_path, "r", encoding="utf-8") as f:
        legacy_data = json.load(f)

    questions_v2 = []

    # Map 35 câu cũ
    for item in legacy_data["questions"]:
        art = item["target_article_number"]
        pid = f"01_luat_36_dieu_{art:02d}"
        q_v2 = QAItemV2(
            id=item["id"],
            category=item.get("category", "Quy tắc giao thông"),
            question=item["question"],
            ground_truth_answer=item["ground_truth_answer"],
            target_doc_id="01_luat_36_2024_qh15",
            target_parent_id=pid,
            target_article_number=art,
            target_chapter=item.get("target_chapter"),
            expected_citation=f"Điều {art}",
            is_out_of_scope=False
        )
        questions_v2.append(q_v2)

    print(f"-> Đã chuyển đổi {len(questions_v2)} câu hỏi từ bản cũ (qa_001 - qa_035).")

    # 2. Sinh 16 câu Nghị định 168/2024/NĐ-CP
    # Tìm parent_id phù hợp trong parents
    def find_parent(doc_id, kwd, exclude=None):
        for k, v in parents.items():
            if v.get("doc_id") == doc_id:
                content = (v.get("article_header", "") + " " + v.get("content", "")).lower()
                if kwd.lower() in content:
                    if exclude and exclude.lower() in content:
                        continue
                    return k
        return None

    nd168_id = "03_nghi_dinh_168_2024_nd_cp"

    nd168_items = [
        QAItemV2(
            id="qa_036",
            category="Mức phạt & Chế tài",
            question="Người lái ô tô không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ) bị phạt bao nhiêu tiền và trừ mấy điểm GPLX?",
            ground_truth_answer="Theo Điểm a Khoản 9 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với hành vi không chấp hành hiệu lệnh của đèn tín hiệu giao thông. Bị trừ 04 điểm giấy phép lái xe (Điểm b Khoản 13 Điều 6).",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 9 Điều 6") or "03_nd168_Điểm_a_Khoản_9_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Điều 6 Nghị định 168/2024/NĐ-CP",
            expected_figures=ExpectedFigures(fine_vnd=[18000000, 20000000], points=4),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_037",
            category="Mức phạt & Chế tài",
            question="Lái xe ô tô mà trong máu hoặc hơi thở có nồng độ cồn chưa vượt quá 50 miligam/100 mililít máu hoặc chưa vượt quá 0,25 miligam/1 lít khí thở bị xử phạt thế nào?",
            ground_truth_answer="Theo Điểm c Khoản 6 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng. Bị trừ 04 điểm giấy phép lái xe (Điểm b Khoản 13 Điều 6).",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 6 Điều 6") or "03_nd168_Điểm_c_Khoản_6_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 6 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[6000000, 8000000], points=4),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_038",
            category="Mức phạt & Chế tài",
            question="Lái xe ô tô có nồng độ cồn vượt quá 80 miligam/100 mililít máu hoặc vượt quá 0,4 miligam/1 lít khí thở (mức kịch khung) bị phạt bao nhiêu tiền và trừ mấy điểm?",
            ground_truth_answer="Theo Điểm a Khoản 10 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 30.000.000 đồng đến 40.000.000 đồng. Bị trừ 12 điểm giấy phép lái xe (hết toàn bộ điểm) theo Điểm c Khoản 13 Điều 6.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 10 Điều 6") or "03_nd168_Điểm_a_Khoản_10_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 10 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[30000000, 40000000], points=12),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_039",
            category="Mức phạt & Chế tài",
            question="Người điều khiển xe mô tô, xe gắn máy (xe máy) vượt đèn đỏ thì bị xử phạt bao nhiêu tiền và trừ mấy điểm?",
            ground_truth_answer="Theo Điểm c Khoản 4 Điều 7 Nghị định 168/2024/NĐ-CP, người điều khiển xe mô tô, xe gắn máy không chấp hành hiệu lệnh của đèn tín hiệu giao thông bị phạt từ 4.000.000 đồng đến 6.000.000 đồng và bị trừ 02 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 4 Điều 7") or "03_nd168_Điểm_đ_Khoản_4_Điều_7_Nghị_định_168/2024/NĐ-CP",
            target_article_number=7,
            expected_citation="Khoản 4 Điều 7",
            expected_figures=ExpectedFigures(fine_vnd=[4000000, 6000000], points=2),
            expected_vehicles=["xe_may"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_040",
            category="Mức phạt & Chế tài",
            question="Điều khiển xe máy có nồng độ cồn ở mức thấp nhất (chưa vượt quá 50 mg/100 ml máu hoặc 0,25 mg/1 lít khí thở) bị phạt tiền và trừ điểm thế nào?",
            ground_truth_answer="Theo Điểm a Khoản 6 Điều 7 Nghị định 168/2024/NĐ-CP, phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng và bị trừ 02 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 6 Điều 7") or "03_nd168_Điểm_a_Khoản_6_Điều_7_Nghị_định_168/2024/NĐ-CP",
            target_article_number=7,
            expected_citation="Khoản 6 Điều 7",
            expected_figures=ExpectedFigures(fine_vnd=[2000000, 3000000], points=2),
            expected_vehicles=["xe_may"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_041",
            category="Mức phạt & Chế tài",
            question="Lái xe ô tô đi ngược chiều trên đường cao tốc hoặc lùi xe trên đường cao tốc bị phạt bao nhiêu tiền và trừ mấy điểm?",
            ground_truth_answer="Theo Điểm a Khoản 11 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 40.000.000 đồng đến 50.000.000 đồng đối với hành vi đi ngược chiều trên đường cao tốc hoặc lùi xe trên đường cao tốc. Bị trừ 12 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 11 Điều 6") or "03_nd168_Điểm_a_Khoản_11_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 11 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[40000000, 50000000], points=12),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_042",
            category="Mức phạt & Chế tài",
            question="Người đi xe máy không đội mũ bảo hiểm hoặc đội mũ không cài quai đúng quy cách bị phạt bao nhiêu tiền?",
            ground_truth_answer="Theo Điểm m Khoản 2 Điều 7 Nghị định 168/2024/NĐ-CP, phạt tiền từ 400.000 đồng đến 600.000 đồng đối với người điều khiển xe mô tô, xe gắn máy không đội 'mũ bảo hiểm cho người đi mô tô, xe máy' hoặc đội mũ nhưng không cài quai đúng quy cách.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 2 Điều 7") or "03_nd168_Điểm_a_Khoản_2_Điều_7_Nghị_định_168/2024/NĐ-CP",
            target_article_number=7,
            expected_citation="Khoản 2 Điều 7",
            expected_figures=ExpectedFigures(fine_vnd=[4000000, 600000], points=0),
            expected_vehicles=["xe_may"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_043",
            category="Mức phạt & Chế tài",
            question="Người lái xe ô tô dùng tay cầm và sử dụng điện thoại khi đang lái xe bị phạt bao nhiêu?",
            ground_truth_answer="Theo Điểm d Khoản 4 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng và bị trừ 02 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 4 Điều 6") or "03_nd168_Điểm_a_Khoản_4_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 4 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[2000000, 3000000], points=2),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_044",
            category="Mức phạt & Chế tài",
            question="Người đi xe máy sử dụng điện thoại hoặc thiết bị âm thanh (tai nghe) khi đang lái xe bị phạt bao nhiêu tiền?",
            ground_truth_answer="Theo Điểm h Khoản 3 Điều 7 Nghị định 168/2024/NĐ-CP, phạt tiền từ 800.000 đồng đến 1.000.000 đồng và bị trừ 02 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 3 Điều 7") or "03_nd168_Điểm_a_Khoản_3_Điều_7_Nghị_định_168/2024/NĐ-CP",
            target_article_number=7,
            expected_citation="Khoản 3 Điều 7",
            expected_figures=ExpectedFigures(fine_vnd=[800000, 1000000], points=2),
            expected_vehicles=["xe_may"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_045",
            category="Mức phạt & Chế tài",
            question="Ô tô không bật đèn chiếu sáng khi trời tối (từ 18h đến 06h sáng hôm sau) bị xử phạt bao nhiêu?",
            ground_truth_answer="Theo Điểm g Khoản 2 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe ô tô không sử dụng đèn chiếu sáng trong thời gian từ 18 giờ ngày hôm trước đến 06 giờ ngày hôm sau.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 2 Điều 6") or "03_nd168_Điểm_a_Khoản_2_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 2 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[800000, 1000000], points=0),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_046",
            category="Mức phạt & Chế tài",
            question="Chở 3 người trên xe máy (kẹp 3) bị phạt bao nhiêu tiền và có bị trừ điểm bằng lái không?",
            ground_truth_answer="Theo Điểm l Khoản 2 Điều 7 Nghị định 168/2024/NĐ-CP, phạt tiền từ 400.000 đồng đến 600.000 đồng đối với hành vi chở theo từ 02 người trở lên trên xe (trừ người bệnh đi cấp cứu, trẻ em dưới 12 tuổi hoặc áp giải người vi phạm). Hành vi này không bị trừ điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 2 Điều 7") or "03_nd168_Điểm_a_Khoản_2_Điều_7_Nghị_định_168/2024/NĐ-CP",
            target_article_number=7,
            expected_citation="Khoản 2 Điều 7",
            expected_figures=ExpectedFigures(fine_vnd=[400000, 600000], points=0),
            expected_vehicles=["xe_may"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_047",
            category="Mức phạt & Chế tài",
            question="Xe máy không có gương chiếu hậu bên trái hoặc có nhưng không có tác dụng bị phạt bao nhiêu tiền?",
            ground_truth_answer="Theo Điểm a Khoản 1 Điều 14 Nghị định 168/2024/NĐ-CP, phạt tiền từ 300.000 đồng đến 400.000 đồng đối với hành vi điều khiển xe không có gương chiếu hậu bên trái người điều khiển hoặc có nhưng không có tác dụng.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 1 Điều 14") or "03_nd168_Điểm_a_Khoản_1_Điều_14_Nghị_định_168/2024/NĐ-CP",
            target_article_number=14,
            expected_citation="Điều 14 Nghị định 168/2024/NĐ-CP",
            expected_figures=ExpectedFigures(fine_vnd=[300000, 400000], points=0),
            expected_vehicles=["xe_may"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_048",
            category="Mức phạt & Chế tài",
            question="Không chấp hành hiệu lệnh hoặc hướng dẫn của Cảnh sát giao thông (người điều khiển giao thông) khi lái ô tô bị phạt bao nhiêu và trừ mấy điểm?",
            ground_truth_answer="Theo Điểm b Khoản 8 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 16.000.000 đồng đến 18.000.000 đồng và bị trừ 06 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 8 Điều 6") or "03_nd168_Điểm_a_Khoản_8_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 8 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[16000000, 18000000], points=6),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_049",
            category="Mức phạt & Chế tài",
            question="Lái xe ô tô chạy quá tốc độ quy định từ 10 km/h đến 20 km/h bị xử phạt bao nhiêu tiền và trừ mấy điểm GPLX?",
            ground_truth_answer="Theo Điểm i Khoản 4 Điều 6 Nghị định 168/2024/NĐ-CP, phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng. Bị trừ 02 điểm GPLX.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 4 Điều 6") or "03_nd168_Điểm_a_Khoản_4_Điều_6_Nghị_định_168/2024/NĐ-CP",
            target_article_number=6,
            expected_citation="Khoản 4 Điều 6",
            expected_figures=ExpectedFigures(fine_vnd=[4000000, 6000000], points=2),
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_050",
            category="Mức phạt & Chế tài",
            question="Người đi bộ vượt đèn đỏ hoặc đi vào đường cao tốc bị xử phạt thế nào?",
            ground_truth_answer="Theo Điều 11 Nghị định 168/2024/NĐ-CP, người đi bộ không chấp hành hiệu lệnh đèn tín hiệu bị phạt tiền từ 150.000 đồng đến 250.000 đồng; đi vào đường cao tốc bị phạt từ 400.000 đồng đến 600.000 đồng.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Điều 11") or "03_nd168_Điểm_a_Khoản_1_Điều_11_Nghị_định_168/2024/NĐ-CP",
            target_article_number=11,
            expected_citation="Điều 11 Nghị định 168/2024/NĐ-CP",
            expected_figures=ExpectedFigures(fine_vnd=[150000, 250000], points=0),
            expected_vehicles=["nguoi_di_bo"],
            is_out_of_scope=False
        ),
        # Câu thứ 16 của NĐ 168: dạng hội thoại đa lượt
        QAItemV2(
            id="qa_051",
            category="Mức phạt & Chế tài (Đa lượt)",
            question="Vậy nếu chở trẻ em dưới 6 tuổi đi cùng mà không đội mũ bảo hiểm cho trẻ thì có bị phạt không và phạt bao nhiêu?",
            ground_truth_answer="Theo Điểm m Khoản 2 Điều 7 Nghị định 168/2024/NĐ-CP, chở người ngồi trên xe không đội mũ bảo hiểm bị phạt 400.000 - 600.000 đồng, trừ trường hợp chở trẻ em dưới 06 tuổi. Như vậy chở trẻ em dưới 6 tuổi không bị xử phạt vi phạm này.",
            target_doc_id=nd168_id,
            target_parent_id=find_parent(nd168_id, "Khoản 2 Điều 7") or "03_nd168_Điểm_a_Khoản_2_Điều_7_Nghị_định_168/2024/NĐ-CP",
            target_article_number=7,
            expected_citation="Khoản 2 Điều 7",
            expected_figures=ExpectedFigures(fine_vnd=[0, 0], points=0),
            expected_vehicles=["xe_may"],
            history=[
                HistoryMessage(role="user", content="Đi xe máy không đội mũ bảo hiểm bị phạt bao nhiêu tiền?"),
                HistoryMessage(role="assistant", content="Theo Điểm m Khoản 2 Điều 7 Nghị định 168/2024/NĐ-CP, người đi xe máy không đội mũ bảo hiểm bị phạt từ 400.000 đồng đến 600.000 đồng.")
            ],
            is_out_of_scope=False
        )
    ]
    questions_v2.extend(nd168_items)
    print(f"-> Đã thêm {len(nd168_items)} câu hỏi từ Nghị định 168/2024/NĐ-CP.")

    # 3. Sinh 8 câu QCVN 41:2019/BGTVT (Biển báo & Vạch kẻ đường)
    qcvn_id = "06_qcvn_41_2019_bgtvt"
    qcvn_items = [
        QAItemV2(
            id="qa_052",
            category="Biển báo giao thông",
            question="Biển báo P.106a có ý nghĩa gì và cấm những phương tiện nào?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, Biển số P.106a 'Cấm xe ôtô tải' có ý nghĩa cấm tất cả các loại xe ô tô tải trừ các xe được ưu tiên theo quy định. Biển có hiệu lực cấm đối với cả máy kéo và các xe máy chuyên dùng.",
            target_doc_id=qcvn_id,
            target_parent_id="06_qcvn41_P_106a" if "06_qcvn41_P_106a" in parents else find_parent(qcvn_id, "P.106a"),
            expected_citation="P.106a",
            expected_vehicles=["o_to"],
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_053",
            category="Biển báo giao thông",
            question="Biển báo DP.135 'Hết tất cả các lệnh cấm' có tác dụng gì?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, Biển số DP.135 báo hiệu đoạn đường hết tất cả các lệnh cấm đối với các phương tiện cơ giới đã được quy định ở các biển báo cấm trước đó.",
            target_doc_id=qcvn_id,
            target_parent_id="06_qcvn41_DP_135" if "06_qcvn41_DP_135" in parents else find_parent(qcvn_id, "DP.135"),
            expected_citation="DP.135",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_054",
            category="Biển báo giao thông",
            question="Biển P.130 và P.131 khác nhau như thế nào về quy định dừng, đỗ xe?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, Biển P.130 cấm cả dừng xe và đỗ xe (hai gạch chéo màu đỏ); trong khi Biển P.131 chỉ cấm đỗ xe (một gạch chéo màu đỏ), phương tiện vẫn được dừng xe tạm thời.",
            target_doc_id=qcvn_id,
            target_parent_id="06_qcvn41_P_130" if "06_qcvn41_P_130" in parents else find_parent(qcvn_id, "P.130"),
            expected_citation="P.130",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_055",
            category="Biển báo giao thông",
            question="Biển báo P.103a có cấm xe ô tô khách và xe ô tô tải không?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, Biển P.103a 'Cấm xe ôtô' cấm tất cả các loại xe cơ giới từ 4 bánh trở lên đi vào (bao gồm cả ô tô con, ô tô khách, ô tô tải), trừ xe mô tô hai bánh, ba bánh và các xe ưu tiên.",
            target_doc_id=qcvn_id,
            target_parent_id="06_qcvn41_P_103a" if "06_qcvn41_P_103a" in parents else find_parent(qcvn_id, "P.103a"),
            expected_citation="P.103a",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_056",
            category="Vạch kẻ đường",
            question="Ý nghĩa của vạch kẻ đường nét liền màu trắng phân chia các làn xe cùng chiều (Vạch 1.2 / 2.2)?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, vạch nét liền màu trắng dùng để phân chia các làn xe cùng chiều trong trường hợp không cho phép xe chuyển làn hoặc lấn sang làn khác; các phương tiện không được đè lên vạch.",
            target_doc_id=qcvn_id,
            target_parent_id=find_parent(qcvn_id, "Vạch") or find_parent(qcvn_id, "vạch kẻ đường"),
            expected_citation="QCVN 41:2019/BGTVT",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_057",
            category="Biển báo giao thông",
            question="Biển hiệu lệnh R.301a yêu cầu các phương tiện giao thông phải đi như thế nào?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, Biển R.301a 'Các xe chỉ được đi thẳng' yêu cầu các phương tiện chỉ được phép đi thẳng (trừ xe được quyền ưu tiên theo quy định).",
            target_doc_id=qcvn_id,
            target_parent_id="06_qcvn41_R_301a" if "06_qcvn41_R_301a" in parents else find_parent(qcvn_id, "R.301"),
            expected_citation="R.301",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_058",
            category="Biển báo giao thông",
            question="Biển cảnh báo nguy hiểm hình tam giác viền đỏ nền vàng có tác dụng gì đối với người lái xe?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, nhóm biển báo nguy hiểm và cảnh báo nhằm báo trước cho người tham gia giao thông biết trước tính chất nguy hiểm trên tuyến đường để chủ động giảm tốc độ và phòng ngừa tai nạn.",
            target_doc_id=qcvn_id,
            target_parent_id=find_parent(qcvn_id, "Biển báo nguy hiểm") or find_parent(qcvn_id, "tam giác"),
            expected_citation="QCVN 41:2019/BGTVT",
            is_out_of_scope=False
        ),
        # Câu thứ 8: dạng hội thoại đa lượt
        QAItemV2(
            id="qa_059",
            category="Biển báo giao thông (Đa lượt)",
            question="Thế còn biển P.106b thì cấm xe tải theo tiêu chí nào?",
            ground_truth_answer="Theo QCVN 41:2019/BGTVT, Biển P.106b cấm các loại xe ô tô tải có khối lượng chuyên chở lớn hơn giá trị số ghi trên biển (tính theo Giấy kiểm định an toàn kỹ thuật).",
            target_doc_id=qcvn_id,
            target_parent_id="06_qcvn41_P_106b" if "06_qcvn41_P_106b" in parents else find_parent(qcvn_id, "P.106b"),
            expected_citation="P.106b",
            history=[
                HistoryMessage(role="user", content="Biển P.106a cấm xe gì?"),
                HistoryMessage(role="assistant", content="Biển P.106a có ý nghĩa cấm tất cả các loại xe ô tô tải đi vào đoạn đường có đặt biển.")
            ],
            is_out_of_scope=False
        )
    ]
    questions_v2.extend(qcvn_items)
    print(f"-> Đã thêm {len(qcvn_items)} câu hỏi từ QCVN 41:2019/BGTVT.")

    # 4. Sinh 6 câu Thông tư 31/2019/TT-BGTVT (Tốc độ & Khoảng cách)
    tt31_id = "04_thong_tu_31_2019_tt_bgtvt"
    tt31_items = [
        QAItemV2(
            id="qa_060",
            category="Tốc độ xe cơ giới",
            question="Tốc độ tối đa cho phép của xe ô tô con và xe máy khi chạy trong khu vực đông dân cư trên đường đôi (hoặc đường một chiều có từ 2 làn xe cơ giới trở lên) là bao nhiêu km/h?",
            ground_truth_answer="Theo Điều 6 Thông tư 31/2019/TT-BGTVT, tốc độ tối đa cho phép trong khu vực đông dân cư trên đường đôi hoặc đường một chiều có từ 2 làn xe cơ giới trở lên là 60 km/h.",
            target_doc_id=tt31_id,
            target_parent_id="04_tt31_dieu_06",
            target_article_number=6,
            expected_citation="Điều 6 Thông tư 31/2019/TT-BGTVT",
            expected_figures=ExpectedFigures(points=None),
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_061",
            category="Tốc độ xe cơ giới",
            question="Trong khu vực đông dân cư, đường hai chiều không có dải phân cách giữa thì xe máy và ô tô được chạy tối đa bao nhiêu km/h?",
            ground_truth_answer="Theo Điều 6 Thông tư 31/2019/TT-BGTVT, trên đường hai chiều hoặc đường một chiều có 1 làn xe cơ giới trong khu vực đông dân cư, tốc độ tối đa cho phép là 50 km/h.",
            target_doc_id=tt31_id,
            target_parent_id="04_tt31_dieu_06",
            target_article_number=6,
            expected_citation="Điều 6 Thông tư 31/2019/TT-BGTVT",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_062",
            category="Tốc độ xe máy chuyên dùng",
            question="Tốc độ tối đa cho phép của xe máy chuyên dùng, xe gắn máy (kể cả xe máy điện) khi tham gia giao thông trên đường bộ là bao nhiêu?",
            ground_truth_answer="Theo Điều 8 Thông tư 31/2019/TT-BGTVT, tốc độ tối đa cho phép đối với xe máy chuyên dùng, xe gắn máy (kể cả xe máy điện) không quá 40 km/h.",
            target_doc_id=tt31_id,
            target_parent_id="04_tt31_dieu_08",
            target_article_number=8,
            expected_citation="Điều 8 Thông tư 31/2019/TT-BGTVT",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_063",
            category="Khoảng cách an toàn",
            question="Khi chạy xe với tốc độ từ trên 60 km/h đến 80 km/h trong điều kiện mặt đường khô ráo, khoảng cách an toàn tối thiểu giữa hai xe phải là bao nhiêu mét?",
            ground_truth_answer="Theo Điều 11 Thông tư 31/2019/TT-BGTVT, khi tốc độ lưu hành từ trên 60 km/h đến 80 km/h, khoảng cách an toàn tối thiểu giữa hai xe là 55 mét.",
            target_doc_id=tt31_id,
            target_parent_id="04_tt31_dieu_11",
            target_article_number=11,
            expected_citation="Điều 11 Thông tư 31/2019/TT-BGTVT",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_064",
            category="Khoảng cách an toàn",
            question="Khi chạy xe với tốc độ trên 100 km/h đến 120 km/h (như trên đường cao tốc), khoảng cách an toàn tối thiểu là bao nhiêu mét?",
            ground_truth_answer="Theo Điều 11 Thông tư 31/2019/TT-BGTVT, khi tốc độ lưu hành từ trên 100 km/h đến 120 km/h, khoảng cách an toàn tối thiểu giữa hai xe là 100 mét.",
            target_doc_id=tt31_id,
            target_parent_id="04_tt31_dieu_11",
            target_article_number=11,
            expected_citation="Điều 11 Thông tư 31/2019/TT-BGTVT",
            is_out_of_scope=False
        ),
        # Câu thứ 6: Đa lượt
        QAItemV2(
            id="qa_065",
            category="Tốc độ xe cơ giới (Đa lượt)",
            question="Nếu chạy ngoài khu vực đông dân cư trên đường đôi thì xe ô tô con được chạy tối đa bao nhiêu km/h?",
            ground_truth_answer="Theo Điều 7 Thông tư 31/2019/TT-BGTVT, ngoài khu vực đông dân cư trên đường đôi (hoặc đường 1 chiều từ 2 làn xe trở lên), xe ô tô con đến 30 chỗ được chạy tối đa 90 km/h.",
            target_doc_id=tt31_id,
            target_parent_id="04_tt31_dieu_07",
            target_article_number=7,
            expected_citation="Điều 7 Thông tư 31/2019/TT-BGTVT",
            history=[
                HistoryMessage(role="user", content="Trong khu đông dân cư đường đôi ô tô con được chạy tối đa bao nhiêu km/h?"),
                HistoryMessage(role="assistant", content="Theo Thông tư 31/2019/TT-BGTVT, tốc độ tối đa cho ô tô con trong khu đông dân cư đường đôi là 60 km/h.")
            ],
            is_out_of_scope=False
        )
    ]
    questions_v2.extend(tt31_items)
    print(f"-> Đã thêm {len(tt31_items)} câu hỏi từ Thông tư 31/2019/TT-BGTVT.")

    # 5. Sinh 6 câu Thông tư 73/2024/TT-BCA (CSGT & VNeID)
    tt73_id = "05_thong_tu_73_2024_tt_bca"
    tt73_items = [
        QAItemV2(
            id="qa_066",
            category="Quyền hạn CSGT & Kiểm soát",
            question="Cảnh sát giao thông được dừng phương tiện giao thông để kiểm soát trong những trường hợp cụ thể nào?",
            ground_truth_answer="Theo Điều 12 Thông tư 73/2024/TT-BCA (và Điều 66 Luật 36/2024/QH15), CSGT được dừng xe trong 4 trường hợp: trực tiếp phát hiện hành vi vi phạm; thực hiện mệnh lệnh/kế hoạch tuần tra đã được phê duyệt; có tin báo/phản ánh tố giác vi phạm; có yêu cầu nghiệp vụ của cơ quan có thẩm quyền.",
            target_doc_id=tt73_id,
            target_parent_id="05_tt73_dieu_12" if "05_tt73_dieu_12" in parents else find_parent(tt73_id, "dừng phương tiện"),
            expected_citation="Thông tư 73/2024/TT-BCA",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_067",
            category="Kiểm tra giấy tờ qua VNeID",
            question="Người tham gia giao thông xuất trình giấy phép lái xe và đăng ký xe qua tài khoản định danh điện tử VNeID có được chấp nhận thay thế bản giấy không?",
            ground_truth_answer="Theo Thông tư 73/2024/TT-BCA, khi thông tin giấy tờ đã được tích hợp, cập nhật trên tài khoản định danh điện tử VNeID hoặc cơ sở dữ liệu quốc gia thì việc kiểm tra, kiểm soát thông qua VNeID có giá trị như kiểm tra trực tiếp giấy tờ bản cứng.",
            target_doc_id=tt73_id,
            target_parent_id=find_parent(tt73_id, "VNeID") or find_parent(tt73_id, "định danh điện tử") or "05_tt73_dieu_05",
            expected_citation="Thông tư 73/2024/TT-BCA",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_068",
            category="Quy trình tuần tra CSGT",
            question="Cán bộ Cảnh sát giao thông thực hiện nhiệm vụ tuần tra kiểm soát công khai phải có trang phục và phương tiện như thế nào?",
            ground_truth_answer="Theo Thông tư 73/2024/TT-BCA, cán bộ CSGT phải mặc trang phục Cảnh sát giao thông theo quy định của Bộ Công an, đeo số hiệu CAND, mang theo Giấy chứng nhận Cảnh sát tuần tra, kiểm soát giao thông đường bộ và sử dụng phương tiện tuần tra đúng quy chuẩn.",
            target_doc_id=tt73_id,
            target_parent_id="05_tt73_dieu_03" if "05_tt73_dieu_03" in parents else "05_tt73_dieu_06",
            expected_citation="Thông tư 73/2024/TT-BCA",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_069",
            category="Kiểm soát phương tiện",
            question="CSGT kiểm soát những nội dung gì đối với người lái xe và phương tiện khi dừng xe?",
            ground_truth_answer="Theo Thông tư 73/2024/TT-BCA, CSGT kiểm soát giấy tờ của người điều khiển và phương tiện (GPLX, đăng ký, đăng kiểm, bảo hiểm); kiểm soát điều kiện an toàn kỹ thuật phương tiện; kiểm soát việc chấp hành nồng độ cồn, ma túy và việc chở hàng hóa, hành khách.",
            target_doc_id=tt73_id,
            target_parent_id=find_parent(tt73_id, "nội dung kiểm soát") or "05_tt73_dieu_05",
            expected_citation="Thông tư 73/2024/TT-BCA",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_070",
            category="Quy trình tuần tra CSGT",
            question="CSGT có được lập chốt tuần tra công khai kết hợp hóa trang bắn tốc độ không?",
            ground_truth_answer="Theo Thông tư 73/2024/TT-BCA, lực lượng CSGT được bố trí bộ phận cán bộ hóa trang (mặc thường phục) để sử dụng phương tiện, thiết bị nghiệp vụ giám sát trật tự giao thông, nhưng phải có kế hoạch tuần tra được cấp có thẩm quyền phê duyệt và phải phối hợp chặt chẽ với bộ phận tuần tra công khai.",
            target_doc_id=tt73_id,
            target_parent_id=find_parent(tt73_id, "hóa trang") or "05_tt73_dieu_06",
            expected_citation="Thông tư 73/2024/TT-BCA",
            is_out_of_scope=False
        ),
        # Câu thứ 6: Đa lượt
        QAItemV2(
            id="qa_071",
            category="Kiểm tra giấy tờ (Đa lượt)",
            question="Thế nếu giấy phép lái xe trên VNeID đang hiển thị trạng thái 'Đã bị tạm giữ' do vi phạm trước đó thì CSGT xử lý như thế nào?",
            ground_truth_answer="Theo quy định tại Thông tư 73/2024/TT-BCA, khi thông tin giấy tờ trên VNeID thể hiện đang bị tạm giữ hoặc tước quyền sử dụng thì có giá trị pháp lý chứng minh người lái xe không có quyền điều khiển phương tiện trong thời gian đó, CSGT sẽ lập biên bản xử lý hành vi không có giấy phép lái xe.",
            target_doc_id=tt73_id,
            target_parent_id=find_parent(tt73_id, "VNeID") or "05_tt73_dieu_05",
            expected_citation="Thông tư 73/2024/TT-BCA",
            history=[
                HistoryMessage(role="user", content="Xuất trình giấy tờ qua VNeID có được thay bằng lái xe giấy không?"),
                HistoryMessage(role="assistant", content="Có, Thông tư 73/2024/TT-BCA quy định thông tin giấy tờ trên VNeID có giá trị tương đương bản giấy.")
            ],
            is_out_of_scope=False
        )
    ]
    questions_v2.extend(tt73_items)
    print(f"-> Đã thêm {len(tt73_items)} câu hỏi từ Thông tư 73/2024/TT-BCA.")

    # 6. Sinh 8 câu Luật Đường bộ 35/2024/QH15
    luat35_id = "02_luat_35_2024_qh15"
    luat35_items = [
        QAItemV2(
            id="qa_072",
            category="Hạ tầng & Đường bộ",
            question="Luật Đường bộ số 35/2024/QH15 quy định phạm vi kết cấu hạ tầng đường bộ bao gồm những thành phần nào?",
            ground_truth_answer="Theo Điều 2 và Điều 10 Luật Đường bộ 35/2024/QH15, kết cấu hạ tầng đường bộ bao gồm công trình đường bộ, bến xe, bãi đỗ xe, trạm dừng nghỉ, hệ thống thoát nước, hệ thống chiếu sáng, trung tâm quản lý điều hành giao thông và đất dành cho kết cấu hạ tầng đường bộ.",
            target_doc_id=luat35_id,
            target_parent_id="02_luat_35_dieu_02",
            target_article_number=2,
            expected_citation="Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_073",
            category="Quy định đường cao tốc",
            question="Luật Đường bộ 2024 quy định những yêu cầu gì đối với việc đầu tư xây dựng và quản lý đường cao tốc?",
            ground_truth_answer="Theo Luật Đường bộ 35/2024/QH15 (Chương IV về Đường cao tốc), đường cao tốc phải được đầu tư xây dựng đồng bộ với công trình quản lý điều hành giao thông, trạm dừng nghỉ, hệ thống kiểm tra tải trọng xe và hệ thống thu phí điện tử không dừng.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "đường cao tốc") or "02_luat_35_dieu_45",
            expected_citation="Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_074",
            category="Thu phí giao thông",
            question="Hình thức thu phí sử dụng đường bộ theo cơ chế điện tử không dừng (ETC) được quy định như thế nào trong Luật Đường bộ?",
            ground_truth_answer="Theo Luật Đường bộ 35/2024/QH15, việc thu phí sử dụng đường bộ, trạm thu phí đường cao tốc được triển khai chủ yếu theo hình thức điện tử không dừng để bảo đảm lưu thông nhanh chóng, minh bạch và giảm ùn tắc.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "thu phí") or "02_luat_35_dieu_50",
            expected_citation="Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_075",
            category="Bảo vệ công trình đường bộ",
            question="Những hành vi nào bị nghiêm cấm đối với bảo vệ kết cấu hạ tầng đường bộ theo Luật Đường bộ 2024?",
            ground_truth_answer="Theo Điều 7 Luật Đường bộ 35/2024/QH15, cấm phá hoại công trình đường bộ; lấn chiếm hành lang an toàn đường bộ; tự ý mở đường nhánh đấu nối trái phép; xả nước thải vào công trình đường bộ.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "nghiêm cấm") or "02_luat_35_dieu_07",
            target_article_number=7,
            expected_citation="Điều 7 Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_076",
            category="Kinh doanh vận tải",
            question="Kinh doanh vận tải bằng xe ô tô gồm những loại hình nào theo Luật Đường bộ số 35/2024/QH15?",
            ground_truth_answer="Theo Luật Đường bộ 35/2024/QH15, kinh doanh vận tải hành khách bằng xe ô tô bao gồm vận tải theo tuyến cố định, vận tải bằng xe buýt, vận tải bằng xe taxi và vận tải theo hợp đồng.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "kinh doanh vận tải") or "02_luat_35_dieu_56",
            expected_citation="Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_077",
            category="Xe quá khổ, quá tải",
            question="Điều kiện lưu hành đối với xe quá khổ giới hạn hoặc xe quá tải trọng trên đường bộ là gì?",
            ground_truth_answer="Theo Luật Đường bộ 35/2024/QH15, xe quá khổ giới hạn hoặc quá tải trọng chỉ được lưu hành khi có Giấy phép lưu hành xe do cơ quan có thẩm quyền cấp và phải tuân thủ nghiêm ngặt các biện pháp bảo đảm an toàn kết cấu cầu đường.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "quá tải") or "02_luat_35_dieu_53",
            expected_citation="Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_078",
            category="Trạm dừng nghỉ",
            question="Quy định về quy hoạch và xây dựng trạm dừng nghỉ trên các tuyến quốc lộ và đường cao tốc?",
            ground_truth_answer="Theo Luật Đường bộ 35/2024/QH15, trạm dừng nghỉ là bộ phận thuộc kết cấu hạ tầng đường bộ, phải được đầu tư xây dựng đồng bộ theo tiêu chuẩn kỹ thuật quốc gia, cung cấp các dịch vụ phục vụ người lái xe và hành khách.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "trạm dừng nghỉ") or "02_luat_35_dieu_38",
            expected_citation="Luật Đường bộ",
            is_out_of_scope=False
        ),
        QAItemV2(
            id="qa_079",
            category="Hạ tầng & Đất đai (Đa lượt)",
            question="Đất hành lang an toàn đường bộ được quản lý và sử dụng như thế nào theo Luật Đường bộ?",
            ground_truth_answer="Theo Luật Đường bộ 35/2024/QH15, đất hành lang an toàn đường bộ được dùng để bảo đảm an toàn giao thông, mở rộng công trình trong tương lai; nghiêm cấm xây dựng nhà ở, công trình kiên cố trái phép trong phạm vi này.",
            target_doc_id=luat35_id,
            target_parent_id=find_parent(luat35_id, "hành lang an toàn") or "02_luat_35_dieu_15",
            expected_citation="Luật Đường bộ",
            history=[
                HistoryMessage(role="user", content="Kết cấu hạ tầng đường bộ gồm những gì?"),
                HistoryMessage(role="assistant", content="Kết cấu hạ tầng đường bộ gồm công trình đường bộ, trạm dừng nghỉ, bến xe và đất hành lang an toàn đường bộ.")
            ],
            is_out_of_scope=False
        )
    ]
    questions_v2.extend(luat35_items)
    print(f"-> Đã thêm {len(luat35_items)} câu hỏi từ Luật Đường bộ 35/2024/QH15.")

    # 7. Sinh 16 câu Out-of-scope / Negative (bẫy từ khóa giao thông, lạc đề)
    # Những câu này nhằm kiểm tra khả năng từ chối đúng (needs_search=True, không bịa tiền)
    negative_items = [
        QAItemV2(
            id="qa_080",
            category="Lạc đề - Thời tiết",
            question="Hôm nay thời tiết Hà Nội có mưa không, lái xe trên đường có bị ngập không?",
            ground_truth_answer="Hệ thống chỉ tra cứu văn bản quy phạm pháp luật giao thông đường bộ Việt Nam, không có thông tin dự báo thời tiết theo thời gian thực.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_081",
            category="Lạc đề - Nấu ăn",
            question="Nấu món phở bò thơm ngon khi đi cắm trại trên xe ô tô thì cần những gia vị gì?",
            ground_truth_answer="Câu hỏi về công thức nấu ăn không thuộc phạm vi tra cứu pháp luật giao thông đường bộ.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_082",
            category="Lạc đề - Giá cả xăng dầu",
            question="Giá xăng RON 95 hôm nay tăng hay giảm bao nhiêu tiền một lít tại các cây xăng?",
            ground_truth_answer="Hệ thống không cung cấp thông tin biến động giá thị trường xăng dầu hàng ngày.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_083",
            category="Lạc đề - Tài chính",
            question="Vay tiền ngân hàng mua xe ô tô trả góp lãi suất bao nhiêu là rẻ nhất hiện nay?",
            ground_truth_answer="Thông tin về lãi suất tín dụng và gói vay ngân hàng nằm ngoài phạm vi pháp luật giao thông đường bộ.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_084",
            category="Lạc đề - Lịch thi sát hạch",
            question="Cho tôi xem danh sách lịch thi sát hạch lái xe bằng B2 tại sân sát hạch Sài Gòn cuối tuần này?",
            ground_truth_answer="Hệ thống chỉ có quy định pháp lý về độ tuổi và điều kiện sát hạch GPLX, không nắm giữ lịch thi cụ thể của các trung tâm sát hạch địa phương.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_085",
            category="Lạc đề - Mua bán xe",
            question="Mua xe máy Honda SH cũ đời 2020 giá bao nhiêu tiền thì hợp lý?",
            ground_truth_answer="Hệ thống không có dữ liệu định giá mua bán phương tiện cũ trên thị trường.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_086",
            category="Lạc đề - Đăng kiểm",
            question="Trạm đăng kiểm xe ô tô nào ở Cầu Giấy đang vắng xe nhất bây giờ?",
            ground_truth_answer="Hệ thống không có dữ liệu trạng thái hoạt động thực tế thời gian thực tại các trạm đăng kiểm.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_087",
            category="Lạc đề - Bảo hiểm thân vỏ",
            question="Nên mua bảo hiểm thân vỏ xe ô tô của Bảo Việt hay PVI giá tốt hơn?",
            ground_truth_answer="Thông tin so sánh sản phẩm thương mại của các công ty bảo hiểm không thuộc phạm vi dữ liệu pháp luật.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_088",
            category="Lạc đề - Bẫy từ khóa 'đua xe'",
            question="Xem giải đua xe Công thức 1 (F1) ở kênh truyền hình nào tối nay?",
            ground_truth_answer="Câu hỏi về lịch phát sóng giải thể thao F1 nằm ngoài phạm vi quy định pháp luật giao thông.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_089",
            category="Lạc đề - Bẫy từ khóa 'đèn tín hiệu'",
            question="Mua đèn tín hiệu trang trí cây thông Noel ở đâu tại TP.HCM vừa đẹp vừa rẻ?",
            ground_truth_answer="Câu hỏi mua sắm đồ trang trí Noel không thuộc phạm vi pháp luật giao thông.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_090",
            category="Lạc đề - Bẫy từ khóa 'uống rượu bia'",
            question="Uống rượu vang đỏ mỗi ngày một ly có tốt cho tim mạch và sức khỏe không?",
            ground_truth_answer="Hệ thống chỉ cung cấp quy định pháp lý cấm điều khiển phương tiện khi có nồng độ cồn, không cung cấp tư vấn y khoa dinh dưỡng.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_091",
            category="Lạc đề - Bẫy từ khóa 'biển số xe'",
            question="Biển số xe đuôi số 68 có phải biển số phát lộc phong thủy không?",
            ground_truth_answer="Hệ thống chỉ giải thích quy định pháp luật về biển số định danh và đấu giá biển số, không có dữ liệu phong thủy.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_092",
            category="Lạc đề - Hành vi bất hợp pháp",
            question="Làm cách nào để mua bằng lái xe máy không cần đi thi sát hạch?",
            ground_truth_answer="Pháp luật nghiêm cấm tuyệt đối hành vi mua bán, sử dụng giấy phép lái xe giả. Mọi người muốn có bằng lái bắt buộc phải dự sát hạch theo quy định.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_093",
            category="Lạc đề - Sửa xe",
            question="Xe ô tô bị chảy dầu dưới gầm máy thì nên mang ra gara nào sửa uy tín?",
            ground_truth_answer="Hệ thống không đánh giá hoặc giới thiệu các cơ sở sửa chữa phương tiện thương mại.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_094",
            category="Lạc đề - Tuyến đường du lịch",
            question="Đường đi từ Hà Nội lên Sapa qua cao tốc Nội Bài Lào Cai có cảnh đẹp nào để chụp ảnh?",
            ground_truth_answer="Hệ thống không cung cấp thông tin hướng dẫn du lịch hoặc điểm check-in chụp ảnh.",
            is_out_of_scope=True
        ),
        QAItemV2(
            id="qa_095",
            category="Lạc đề - Bẫy từ khóa 'tốc độ'",
            question="Bộ phim Quá Nhanh Quá Nguy Hiểm (Fast & Furious) phần mới nhất chiếu rạp ngày nào?",
            ground_truth_answer="Hệ thống không nắm giữ lịch chiếu phim điện ảnh.",
            is_out_of_scope=True
        )
    ]
    questions_v2.extend(negative_items)
    print(f"-> Đã thêm {len(negative_items)} câu hỏi Out-of-scope / Negative.")

    dataset_v2 = BenchmarkDatasetV2(
        dataset_name="Traffic Law Vietnam Benchmark v2",
        version="2.0",
        description="Bộ dữ liệu 95 câu hỏi đánh giá hệ thống RAG LexTraffic AI (phủ đủ 6 văn bản pháp luật, câu hỏi phạt tiền/trừ điểm, đa lượt và câu hỏi tiêu cực ngoài phạm vi)",
        total_questions=len(questions_v2),
        questions=questions_v2
    )

    out_path = os.path.join(base_dir, "data", "benchmark", "qa_testset_v2.json")
    save_dataset(dataset_v2, out_path)
    print(f"✅ ĐÃ LƯU THÀNH CÔNG TẬP BENCHMARK V2 ({len(questions_v2)} CÂU HỎI) TẠI: {out_path}")


if __name__ == "__main__":
    build_v2_benchmark()
