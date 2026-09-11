---
phase: 1
title: "Bộ eval và baseline đo lường"
status: completed
priority: P1
effort: "2d"
dependencies: []
---

# Phase 1: Bộ eval và baseline đo lường

## Overview

Dựng bộ đánh giá đo được cả truy xuất lẫn end-to-end, mở rộng benchmark từ 35 lên >= 80 câu phủ cả 6
văn bản, rồi **chốt baseline trên harness cũ** trước khi động vào kiến trúc. Không có bước này thì
mọi phase sau đều không chứng minh được là cải tiến chứ không phải hồi quy.

## Requirements

**Chức năng**
- Đo retrieval: Hit@1, Hit@3, Hit@5, MRR, nDCG@5 — tách theo từng văn bản và từng nhóm câu hỏi.
- Đo end-to-end: độ chính xác trích dẫn, tỉ lệ số liệu không căn cứ, tỉ lệ câu trả lời bị huỷ, độ
  chính xác từ chối khi hỏi lạc đề, độ trễ p50/p95, chi phí ước tính mỗi câu.
- Bộ dữ liệu mở rộng >= 80 câu: phủ cả 6 văn bản + >= 15 câu lạc đề (negative).
- Cổng chặn hồi quy: so kết quả với tệp baseline, exit code khác 0 khi tụt quá ngưỡng.
- Chạy được ở hai chế độ: `--quick` (20 câu, dùng khi lặp nhanh) và đầy đủ.

**Phi chức năng**
- Chạy được trên Windows, Python 3.12, không phụ thuộc LangChain (Phase 1 chạy trước Phase 2).
- Không gọi LLM trong phần đo retrieval — chỉ gọi embedding, để chi phí thấp và kết quả ổn định.
- Kết quả xuất JSON có version schema để so sánh giữa các lần chạy.

## Architecture

```
scripts/eval/
├── __init__.py
├── datasets.py          # nạp + validate testset, phân nhóm theo doc/category
├── retrieval_eval.py    # chỉ số truy xuất, không cần LLM
├── e2e_eval.py          # chạy agent thật qua một adapter, đo chất lượng câu trả lời
├── adapters.py          # LegacyAdapter (agentic_rag) | GraphAdapter (harness mới)
├── metrics.py           # hàm tính Hit@k, MRR, nDCG, citation accuracy
├── gate.py              # so với baseline, exit 0/1
└── baselines/
    └── baseline-legacy-260909.json
```

`adapters.py` là điểm mấu chốt: bộ eval nói chuyện với agent qua **một giao diện duy nhất**
(`run(question, history) -> {answer, sources, agent_steps, verification_issues, needs_search,
latency_ms, tokens}`). Nhờ đó cùng một bộ eval chạy được trên harness cũ (để lấy baseline) và
harness mới (để chứng minh cải tiến), không phải viết hai bộ.

### Schema testset mở rộng

Testset hiện tại (`data/benchmark/qa_testset.json`) chỉ có `target_article_number` — mặc định hiểu là
Luật 36. Schema mới phải định danh được văn bản, và với câu hỏi mức phạt phải nêu được trích dẫn kỳ
vọng:

```json
{
  "id": "qa_042",
  "category": "Mức phạt",
  "question": "Ô tô vượt đèn đỏ bị phạt bao nhiêu tiền và trừ mấy điểm?",
  "ground_truth_answer": "...",
  "target_doc_id": "03_nghi_dinh_168_2024_nd_cp",
  "target_parent_id": "03_nd_168_dieu_06_k09_dc",
  "expected_citation": "Điểm c Khoản 9 Điều 6",
  "expected_figures": { "fine_vnd": [18000000, 20000000], "points": 4 },
  "expected_vehicles": ["o_to"],
  "is_out_of_scope": false
}
```

Câu lạc đề dùng `is_out_of_scope: true`, không có target; đáp án đúng là **từ chối** kèm
`needs_search = true`.

### Định nghĩa các chỉ số E2E

| Chỉ số | Cách tính |
|---|---|
| Độ chính xác trích dẫn | Với câu có `expected_citation`: chuỗi trích dẫn phải xuất hiện trong `answer` **và** nằm trong `sources`. Tính theo tỉ lệ câu đạt |
| Tỉ lệ số liệu không căn cứ | Chạy `find_ungrounded_figures()` trên câu trả lời cuối với tool output đã thu. Bất kỳ phát hiện nào cũng tính là fail |
| Tỉ lệ câu trả lời bị huỷ | Số câu mà `verification_issues` không rỗng / tổng số câu |
| Từ chối đúng khi lạc đề | Với câu `is_out_of_scope`: đạt khi `needs_search == true` **và** câu trả lời không chứa mức tiền phạt nào |
| Độ trễ | Đo thời gian tường từ lúc gọi tới sự kiện `done` |
| Chi phí | Token vào/ra x đơn giá model từ bảng cấu hình trong `metrics.py` |

## Related Code Files

- Create: `scripts/eval/__init__.py`, `datasets.py`, `retrieval_eval.py`, `e2e_eval.py`,
  `adapters.py`, `metrics.py`, `gate.py`
- Create: `data/benchmark/qa_testset_v2.json` (>= 80 câu, schema mới)
- Create: `scripts/eval/baselines/baseline-legacy-260909.json`
- Modify: `scripts/evaluate_rag.py` — chuyển thành wrapper mỏng gọi `scripts/eval/retrieval_eval.py`,
  giữ lệnh cũ chạy được
- Modify: `main.py` — thêm chế độ `--eval` gọi bộ eval mới
- Read-only: `data/benchmark/qa_testset.json`, `data/processed/semantic_chunks.json`,
  `data/processed/semantic_parents.json`, `src/answer_guard.py`, `src/agentic_rag.py`

## Implementation Steps

1. Dựng `scripts/eval/metrics.py`: Hit@k, MRR, nDCG@5, citation accuracy, thống kê độ trễ/chi phí.
   Viết unit test cho từng hàm bằng dữ liệu bịa nhỏ — đây là mã đo lường, sai ở đây làm hỏng mọi
   kết luận về sau.
2. Dựng `scripts/eval/datasets.py`: nạp cả schema cũ lẫn mới, validate bằng Pydantic, báo lỗi rõ khi
   thiếu trường bắt buộc.
3. Migrate 35 câu hiện có sang schema v2: thêm `target_doc_id = "01_luat_36_2024_qh15"`, ánh xạ
   `target_article_number` sang `target_parent_id` bằng `semantic_parents.json`.
4. Sinh thêm >= 45 câu mới **từ chính corpus** để ground truth luôn tồn tại thật:
   - >= 15 câu Nghị định 168 (mức phạt, trừ điểm) — có `expected_citation` và `expected_figures`
   - >= 8 câu QCVN 41 (biển báo, vạch kẻ)
   - >= 5 câu Thông tư 31 (tốc độ, khoảng cách)
   - >= 5 câu Thông tư 73 (CSGT, VNeID)
   - >= 7 câu Luật 35 (cao tốc, vận tải)
   - >= 15 câu lạc đề (`is_out_of_scope`), gồm cả bẫy trùng chữ đã biết: "thời tiết hôm nay",
     "nấu ăn trên đường", "giá xăng", "lịch thi bằng lái ở đâu rẻ"
   - >= 5 câu hỏi nối tiếp đa lượt (có trường `history`) kiểu "Vậy còn xe máy thì sao?"
<!-- Updated: Validation Session 1 - Confirmed benchmark expansion with human review -->
5. **Bạn duyệt** bộ >= 45 câu mới trước khi chốt (đã chốt chính thức tại Validation Session 1: giữ 35 câu cũ làm lõi, sinh bổ sung >= 45 câu và người dùng duyệt).
6. Dựng `adapters.py` với `LegacyAdapter` bọc `AgenticLegalSearch.run_agent()`.
7. Dựng `retrieval_eval.py` và `e2e_eval.py`, hỗ trợ `--quick`, `--doc`, `--category`, `--out`.
8. Chạy đầy đủ trên harness cũ, ghi `baselines/baseline-legacy-260909.json`. Đây là con số sẽ được
   so trong suốt phần còn lại của kế hoạch.
9. Dựng `gate.py`: đọc baseline + kết quả mới, áp ngưỡng trong bảng "Chỉ Số Mục Tiêu" của `plan.md`,
   in bảng so sánh, exit 1 khi vi phạm.

## Success Criteria

- [x] `data/benchmark/qa_testset_v2.json`: **95 câu** (>= 80), phủ **đủ 6/6 văn bản**, **16 câu lạc đề** (>= 15), 5 câu đa lượt, 79 câu có `expected_citation`. **Người dùng đã duyệt ngày 2026-09-11.**
      Phân bố theo văn bản: Luật 36/2024 = 35, NĐ 168/2024 = 16, QCVN 41:2019 = 8, Luật 35/2024 = 8, TT 31/2019 = 6, TT 73/2024 = 6, lạc đề = 16
- [x] `python scripts/eval/retrieval_eval.py` in đủ Hit@1/@3/@5, MRR, nDCG@5, tách theo từng văn bản
- [x] `python scripts/eval/e2e_eval.py --adapter legacy` chạy hết bộ và xuất JSON đủ 6 chỉ số E2E
- [x] `scripts/eval/baselines/baseline-legacy-260909.json` tồn tại, chứa đủ mọi chỉ số của bảng mục tiêu
- [x] `python scripts/eval/gate.py --baseline ... --current ...` exit 0 khi so baseline với chính nó
- [x] Unit test của `metrics.py` xanh
- [x] `python scripts/evaluate_rag.py` (lệnh cũ) vẫn chạy được

## Risk Assessment

| Rủi ro | Tín hiệu | Phản ứng |
|---|---|---|
| Ground truth sinh từ corpus bị lệch, làm baseline sai | Baseline Hit@1 lệch mạnh so với con số 51.4% đã biết trên 35 câu cũ | Chạy riêng 35 câu cũ trước, đối chiếu phải ra đúng 51.4%; chỉ khi khớp mới tin phần mở rộng |
| Chỉ số E2E dao động giữa các lần chạy do LLM ngẫu nhiên | Chạy hai lần ra kết quả lệch quá 3 điểm phần trăm | `temperature = 0`; chạy baseline 3 lần lấy trung vị; ghi cả độ lệch vào tệp baseline |
| Bộ eval E2E tốn tiền | Hoá đơn OpenRouter tăng | Mặc định `--quick` 20 câu; bộ đầy đủ chỉ chạy ở mốc Phase 3 và Phase 8 |
| Câu lạc đề "bẫy trùng chữ" vô tình đúng phạm vi | Harness cũ trả lời có căn cứ hợp lệ cho câu định là lạc đề | Kiểm lại thủ công từng câu negative khi duyệt; loại câu nào thật sự có quy định |
