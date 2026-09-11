# Citation Accuracy Fix — Report

Scope: `src/graph/synthesize.py`, `src/graph/compact.py`, `src/graph/repair.py`, `src/graph/verify.py`. No other files touched (metrics.py, answer_guard.py, llm/provider.py, tests read-only).

## Diagnosis table

| Case | Symptom | Classification | Cause | Fix | Fixed? |
|---|---|---|---|---|---|
| qa_001, qa_015 | Long correct-sounding answer, never names "Điều X" | Prompt defect | `synthesize.py` user_prompt only said "có căn cứ rõ ràng"; `compact.py` `SINGLE_INSTRUCTION_BLOCK` only forced citation for NĐ 168 penalty figures, never for Luật 36 article numbers; trailing "Căn cứ pháp lý" block wasn't enough to stop the model discussing content without naming the Điều | Added bullet #5 to `SINGLE_INSTRUCTION_BLOCK` (compact.py) + strengthened `synthesize.py` user_prompt: both now explicitly demand the Điều/Khoản number appear **in the body text**, copied verbatim from the packed evidence, and ban vague "theo quy định hiện hành" phrasing. Also bolded the Rank-1 citation line in compact.py so it's visually unmissable. | **Yes** — verified: qa_001 flipped `citation_ok` False→True on rerun (see below) |
| qa_001, qa_015 (repair path) | Even if verify ran, a vague no-citation answer produced `issues=[]` (nothing "invalid" to catch) so repair never fired | verify/repair defect | `find_invalid_citations` only checks citations that exist in the answer for validity — it never flagged the *absence* of any citation | Added `find_missing_citation()` in `verify.py`: if the answer has zero citation markers (Điều/Khoản/Nghị định/Thông tư/QCVN/Biển) while the grounded evidence contains some, it's flagged as `MISSING_CITATION_ISSUE`. `repair.py` now has a dedicated `MISSING_CITATION_REPAIR_INSTRUCTION` distinct from the generic mismatch instruction, so the one repair pass targets the actual defect. | **Yes** |
| qa_007, qa_009, qa_018, qa_020 | `answer_preview` totally empty, `tokens_out=0`, but `has_verification_issue=False` | verify defect (symptom) + likely provider defect (root cause) | `verify_answer()` had `if not answer: return []` — an **empty** answer was treated as "nothing to verify, all good" and sailed straight to `build_sources` as a blank response to the user. Root trigger: `src/llm/provider.py` `MODEL_ROLES` gives `synthesize`/`repair` `allow_reasoning=True` with **no** reasoning-effort cap, unlike `router`/`rerank` which got `effort:"low"` specifically because the same codebase's own comments document that unconstrained reasoning can burn the entire `max_tokens` budget before emitting any content (documented failure at 25.6% rate for router/rerank before that fix). This is out of my scope (`src/llm/provider.py` is frozen). | `verify.py`: empty/whitespace answer now returns `EMPTY_ANSWER_ISSUE` instead of `[]`, forcing it through `repair` (one retry) then `cancel` (honest refusal) instead of leaking a blank string. `repair.py` has a dedicated `EMPTY_ANSWER_REPAIR_INSTRUCTION`. | **Symptom fixed** (blank never reaches the user anymore — verified: qa_007 went from `tokens_out=0`/blank to a full honest "Tôi chưa có dữ liệu..." answer on rerun). **Root cause NOT fixed** — belongs in `src/llm/provider.py`, out of scope. Recommend applying the same `_REASONING_LOW` cap to the `synthesize`/`repair` roles that was already applied to `router`/`rerank` for the identical failure mode. |
| qa_006 | Cited "khoản 1 Điều 16" instead of expected "Điều 17" | Retrieval/rerank defect | Điều 16 was ranked Rank-1 by the upstream `retrieve`/`rerank` node (not owned) and packed as the full-text article; Điều 17 (if retrieved at all) was lower-ranked/truncated. `find_invalid_citations` doesn't flag this because Điều 16 IS a real, retrieved, correctly-cited article — just the semantically wrong one. No amount of prompt/compact tuning inside my 4 files can fix a wrong upstream ranking. | None — out of scope (`src/graph/retrieve.py` / rerank logic not owned) | **Not fixed** — reported. Confirmed on rerun: still cites Điều 16, still `citation_ok=False`. |
| qa_014 | Refused with "Tôi chưa có dữ liệu về mức phạt..." for Điều 58 (GPLX points) | Retrieval defect | Điều 58 evidence apparently not retrieved/ranked high enough to reach compact's law block; question mixes "12 điểm" language with penalty-sounding intent which may have biased the router toward `penalty` intent instead of `law` intent (router.py not owned) | None — out of scope (`src/graph/retrieve.py`, router intent classification not owned) | **Not fixed** — reported |

## Verification run (permitted quick-8, same question IDs qa_001–qa_008 as the original 25Q set — direct before/after comparison)

Cache cleared before run. Command: `PYTHONIOENCODING=utf-8 python scripts/eval/e2e_eval.py --adapter graph --quick 8 --out data/benchmark/e2e_citation_check.json`

| id | expected | citation_ok BEFORE (from `e2e_graph_verify25.json`) | citation_ok AFTER |
|---|---|---|---|
| qa_001 | Điều 89 | False | **True** |
| qa_002 | Điều 9 | True | True |
| qa_003 | Điều 9 | True | True |
| qa_004 | Điều 14 | True | True |
| qa_005 | Điều 15 | True | True |
| qa_006 | Điều 17 | False | False (retrieval defect, unchanged) |
| qa_007 | Điều 20 | False (blank answer) | False (now an honest refusal, not blank) |
| qa_008 | Điều 11 | True | True |

**Citation accuracy on this 8-question slice: 62.5% (5/8) → 75.0% (6/8).**

This is an n=8 sample, not the full 95/25-question gate metric — per instructions I ran only this one capped eval. I am **not** claiming the full-set 48% moved to any specific number; I'm reporting the honest directional signal from the one permitted run, on the exact same question IDs as the original failing set for a clean before/after read. `tests/ -q` stayed green: **164 passed, 0 failed** (baseline was 162 — higher count, zero failures, no test was weakened or removed by me).

## Files changed
- `C:\Users\minhlong\Desktop\evo\ai-giaothong\src\graph\verify.py` — added `EMPTY_ANSWER_ISSUE`, `MISSING_CITATION_ISSUE`, `find_missing_citation()`; `verify_answer()` now catches empty answers and vague/no-citation answers instead of silently passing them.
- `C:\Users\minhlong\Desktop\evo\ai-giaothong\src\graph\repair.py` — split the single generic repair instruction into three targeted ones (`EMPTY_ANSWER_REPAIR_INSTRUCTION`, `MISSING_CITATION_REPAIR_INSTRUCTION`, `MISMATCH_REPAIR_INSTRUCTION`) composed by `_build_repair_instruction()` based on which issue(s) `verify` flagged.
- `C:\Users\minhlong\Desktop\evo\ai-giaothong\src\graph\compact.py` — `SINGLE_INSTRUCTION_BLOCK` gained an explicit "must name Điều/Khoản inline" bullet; Rank-1 law citation line is now bolded for visibility.
- `C:\Users\minhlong\Desktop\evo\ai-giaothong\src\graph\synthesize.py` — user_prompt now explicitly demands the article number appear in the answer body, copied verbatim, banning vague "theo quy định hiện hành" phrasing.

## Out-of-scope findings (reported, not fixed)
1. **`src/llm/provider.py`** `MODEL_ROLES["synthesize"]`/`["repair"]` = `allow_reasoning=True` with no reasoning-effort cap. The file's own comments document that unconstrained reasoning consuming the entire `max_tokens` budget was already diagnosed and fixed for `router`/`rerank` (`_REASONING_LOW`, `effort:"low"`) after measuring an 25.6% failure rate. The identical class of bug plausibly explains the qa_007/qa_009/qa_018/qa_020 empty completions (`tokens_out=0` with high latency, e.g. 84s/56s — consistent with reasoning burning the budget). I could not touch this file; recommend applying the same cap (or raising `max_tokens` for these two roles) as a follow-up.
2. **Retrieval/rerank ranking** (`src/graph/retrieve.py`, rerank logic) picks the wrong article as Rank-1 for some questions (qa_006: Điều 16 instead of 17) or misses relevant law evidence entirely (qa_014: Điều 58 miss, likely intent misclassification toward "penalty" for a GPLX-points question). Neither is fixable from `compact`/`synthesize`/`repair`/`verify` — they can only present/react to whatever evidence retrieval hands them.

Status: DONE_WITH_CONCERNS
Summary: Fixed the two provable, in-scope defects (vague/missing-citation answers passing verify unflagged, and empty answers silently bypassing repair/cancel) with prompt + verify/repair changes; measured a real 62.5%→75.0% citation-accuracy improvement on an identical 8-question before/after slice, tests stayed green (164 passed). Two failure modes (wrong-article ranking, retrieval miss) are genuinely retrieval/rerank/provider defects outside the four owned files and are reported, not patched.
Concerns/Blockers: Full 25/95-question re-measurement was not run per testing rules (only one capped 8-question eval allowed), so the headline 48%→X gate number is not directly confirmed — only the n=8 slice is. The empty-answer root cause (unconstrained reasoning token budget in `src/llm/provider.py`) still needs a real fix there; my verify.py change only guarantees the user never sees a raw blank string anymore (worst case degrades gracefully to an honest refusal via `cancel`), it doesn't stop the underlying token waste or latency.
