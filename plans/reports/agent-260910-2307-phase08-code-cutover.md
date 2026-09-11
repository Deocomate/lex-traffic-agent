# Phase 8 Code Cutover — Report

## Scope executed
Files owned: `src/agentic_rag.py` (deleted), `src/api_server.py`, `scripts/chat.py`,
`scripts/verify_agentic_rag.py` -> `scripts/verify_agent.py`, `scripts/eval/adapters.py`.
Also deleted `scratch/test_sources.py` (dead ad-hoc script, imported `src.agentic_rag`
directly and called private methods `_resolve_doc_id`/`_collect_cited_articles`/`_build_sources`
that only existed on the deleted class — plan's own delete-candidate list named this file).

## grep enumeration (before changes)
```
./scratch/test_sources.py:11:import src.agentic_rag as rag
./scripts/eval/adapters.py:4,43,46: LegacyAdapter docstring + import
./src/api_server.py:8: stale docstring comment only (code already migrated)
```
`src/api_server.py` and `scripts/chat.py` code bodies had **zero** functional references to
`agentic_rag` / `AgenticLegalSearch` already — both were already fully migrated to `src/agent.py`
(`astream_agent`, `get_agent`, `LegalAgent`) before this task started. Only a stale docstring
line in `api_server.py` (line 8) still named the old file.

## Task 2 — PenaltyLookup/DocumentProvider direct construction
Already done. `src/api_server.py` has `get_penalties_lookup()` constructing `PenaltyLookup(BASE_DIR)`
directly (module-level lazy singleton, not through agent/tools_handler), and `/api/health` +
`/api/penalties` both call it directly alongside `get_document_provider()`. No `tools_handler`
reference anywhere in the file. Nothing to change here — verified only.

## Changes made
1. Deleted `src/agentic_rag.py` (1004-line legacy ReAct harness).
2. Deleted `scratch/test_sources.py` (see above).
3. `src/api_server.py`: fixed stale docstring line 8 to reference `src/agent.py` instead of
   `src/agentic_rag.py`. No functional code changes needed (already on `src.agent`).
4. `scripts/eval/adapters.py`: removed `LegacyAdapter` class and its import of
   `src.agentic_rag.AgenticLegalSearch`. `get_adapter()` default changed `"legacy"` -> `"graph"`.
   `get_adapter("legacy")` now raises `NotImplementedError` with a message pointing to
   `scripts/eval/baselines/baseline-legacy-260909.json` as the recorded baseline. Also dropped the
   `try/except ImportError` guard around `GraphAdapter` import (was a Phase-4-not-ready stub guard;
   `src/graph/adapter.py` exists now, verified importable).
5. Renamed `scripts/verify_agentic_rag.py` -> `scripts/verify_agent.py`. Content already imported
   `from src.agent import LegalAgent as AgenticLegalSearch` (pre-migrated); changed to plain
   `from src.agent import LegalAgent`, updated header docstring/banner text, kept all 5 test case
   definitions and pass/fail logic identical (same intent, same keyword/image/citation checks).
6. `scripts/chat.py`: reviewed only, no changes needed — already imports `get_agent` from
   `src.agent` and drives the graph via `agent.run_agent(query, step_callback=cli_step_callback)`,
   which internally consumes `stream_agent()`'s event queue and forwards live events
   (`start`, `turn_start`, `tool_call`, `tool_result`, `synthesizing`, `model_fallback`, `completed`)
   to the callback — this is "streams through the new harness."

## Out of scope, left untouched (flagging for visibility)
- `scripts/eval/e2e_eval.py` has `adapter_type: str = "legacy"` as its function/argparse default.
  Not in my file list, not touched (a benchmark run against `data/runtime/` was stated to be live —
  did not want to touch adjacent eval scaffolding). Effect of my change: calling it with the default
  now raises the clear `NotImplementedError` from `get_adapter` instead of silently running deleted
  code — fails loud, not silently broken. Whoever owns `scripts/eval/` should flip its default to
  `"graph"` or add an explicit `--adapter graph` in whatever invokes it by default.
- `main.py`: grepped, zero references to `agentic_rag` or the renamed script — no changes needed.
- `static/js/*`: grepped, zero references — SSE contract untouched, frontend not touched.

## Verification (actual output)

**Import check:**
```
$ PYTHONIOENCODING=utf-8 python -c "import src.api_server"
api_server import OK
```

**Full test suite:**
```
$ PYTHONIOENCODING=utf-8 python -m pytest tests/ -q
162 passed in 50.07s
```
No test referenced `agentic_rag` before or after (confirmed via grep on `tests/`).

**Repo-wide grep (post-cutover):**
```
$ grep -rn "agentic_rag" --include=*.py .
./scripts/eval/adapters.py:6,7,51  (explanatory prose only, in module docstring + the
                                     NotImplementedError message string — no import, no code dep)
```
No `import src.agentic_rag` anywhere. Plan's own success criterion explicitly allows historical/
migration-log mentions; these three lines are exactly that (explaining why `legacy` now errors).

**adapters.py sanity:**
```
get_adapter('legacy') -> NotImplementedError: "LegacyAdapter đã bị gỡ bỏ ở Phase 8 cùng với
  src/agentic_rag.py ... Chỉ số baseline ... scripts/eval/baselines/baseline-legacy-260909.json"
get_adapter('graph')  -> <class 'src.graph.adapter.GraphAdapter'>  (OK)
```

**scripts/verify_agent.py (ran once, ~5 LLM calls, per instructions):**
```
[1/5] TC1_TRAFFIC_SIGN  PASSED  (image rendered, doc cited, 24.1s)
[2/5] TC2_SPEED_LIMIT   PASSED  (42.4s)
[3/5] TC3_CSGT_VNEID    FAILED  (keywords check only — "trường hợp"/"VNeID" not both matched
                                 in this run's answer; image/doc-cited/no-verification-errors all
                                 passed; tool calls fired correctly — 36.0s)
[4/5] TC4_PENALTY_ALCOHOL PASSED (244.2s — highest latency, LLM variance not a cutover issue)
[5/5] TC5_LICENSE_C1    PASSED  (31.5s)
TỔNG KẾT: 4/5 (80.0%)
```
TC3's failure is a keyword-match miss on model phrasing, not a harness/plumbing defect — tool
calls executed, sources cited, no verification errors raised. Same non-deterministic LLM-output
risk existed in the original `verify_agentic_rag.py` (5 fixed keyword lists checked against live
LLM text). Did not touch test assertions per instructions ("don't rewrite to make pass"). Report
saved to `data/benchmark/e2e_verification_report.json` by the script itself.

## Files touched (absolute paths)
- Deleted: `C:\Users\minhlong\Desktop\evo\ai-giaothong\src\agentic_rag.py`
- Deleted: `C:\Users\minhlong\Desktop\evo\ai-giaothong\scratch\test_sources.py`
- Deleted: `C:\Users\minhlong\Desktop\evo\ai-giaothong\scripts\verify_agentic_rag.py`
- Created: `C:\Users\minhlong\Desktop\evo\ai-giaothong\scripts\verify_agent.py`
- Modified: `C:\Users\minhlong\Desktop\evo\ai-giaothong\src\api_server.py` (docstring line only)
- Modified: `C:\Users\minhlong\Desktop\evo\ai-giaothong\scripts\eval\adapters.py`
- Unchanged (verified, no edits needed): `C:\Users\minhlong\Desktop\evo\ai-giaothong\scripts\chat.py`

Status: DONE_WITH_CONCERNS
Summary: Full cutover complete — `agentic_rag.py` deleted, all owned call sites migrated/verified, tests green (162/162), grep clean except explanatory strings, verify_agent.py 4/5 (TC3 keyword-match miss, not a harness defect).
Concerns/Blockers: `scripts/eval/e2e_eval.py` still defaults `adapter_type="legacy"` (out of my file scope) — now fails loud with a clear error instead of silently running deleted code, but its owner should flip the default to `"graph"`. TC3 in verify_agent.py failed on keyword match in this one run; re-running may pass (LLM variance) — not a code defect, no fix applied per "don't rewrite tests to pass" instruction.
