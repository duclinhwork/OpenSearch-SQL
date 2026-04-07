# Work Report - 2026-04-07
Owner: **Nguyen Duc Linh (Nguyễn Đức Linh)**

## Objective
- Integrate Vietnamese dataset with real SQLite support.
- Run full OpenSearch-SQL pipeline end-to-end.
- Stabilize runtime for constrained environments and OpenRouter usage.

## Delivered Changes
- Added MultiSpider-VI adapter:
  - `src/database_process/prepare_multispider_vi.py`
- Added runnable scripts:
  - `run/run_multispider_vi_prepare.sh`
  - `run/run_multispider_vi_core.sh`
  - `run/run_multispider_vi_main.sh`
- LLM/OpenRouter runtime improvements:
  - `src/llm/model.py` (OpenRouter support + payload hardening + timeout handling)
- Pipeline/runtime hardening:
  - `src/pipeline/column_retrieve_and_other_info.py` (embedding fallback)
  - `src/pipeline/align_correct.py` (`skip_align` mode support)
  - `src/runner/check_and_correct.py` (timeout/env controls, align variable bug fix)

## Experiment Evidence
### Data + Embedding Preparation
- Command:
  - `MAX_DATABASES=30 bash run/run_multispider_vi_prepare.sh`
- Result:
  - `Prepared dataset at: MultiSpider_VI_Bird`
  - `Downloaded sqlite databases: 30/30`

### Full Pipeline (Paid Model) - Successful End-to-End
- Command:
  - `OPENROUTER_MODEL='google/gemini-2.5-flash-lite' START=0 END=1 N_CANDIDATES=1 SKIP_ALIGN=false bash run/run_multispider_vi_main.sh`
- Result artifact:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-09-15-53/0_concert_singer.json`
- Node status:
  - `generate_db_schema`, `extract_col_value`, `extract_query_noun`, `column_retrieve_and_other_info`, `candidate_generate`, `align_correct`, `vote`, `evaluation` -> **success**
- Example evaluation:
  - GOLD SQL: `SELECT count(*) FROM singer`
  - PREDICTED SQL: `SELECT COUNT(Singer_ID) FROM singer`
  - `exec_res: 1`

## Observations
- Free-tier models frequently returned OpenRouter `429` and caused downstream node errors.
- Paid route (`google/gemini-2.5-flash-lite`) resolved rate-limit bottleneck for the tested full run.

## Continue Run Update (User request: "continue")
- Ran full chain on 5 samples (`START=0 END=5`) for `concert_singer` subset.
- Result folder:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-09-24-50/`
- Summary from `-statistics.json`:
  - `align_correct`: 4 correct, 1 incorrect
  - `vote`: 4 correct, 1 incorrect
- One-time infrastructure note:
  - Had to rerun with elevated network permission after DNS sandbox failure.

## Full Run Update (100 Samples)
- Owner log tag: **Nguyen Duc Linh (Nguyễn Đức Linh)**
- Command:
  - `OPENROUTER_MODEL='google/gemini-2.5-flash-lite' START=0 END=100 N_CANDIDATES=1 SKIP_ALIGN=true OPENROUTER_TIMEOUT=90 bash run/run_multispider_vi_main.sh`
- Result folder:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-10-23-13/`
- Statistics (`-statistics.json`):
  - `candidate_generate`: `75 correct / 22 incorrect / 3 error` (total `100`)
  - `align_correct`: `75 correct / 22 incorrect / 3 error` (total `100`)
  - `vote`: `75 correct / 22 incorrect / 3 error` (total `100`)

## Bug Fixes During Full Run
- Fixed string/list handling bug in `skip_align` path:
  - `src/pipeline/align_correct.py`
- Fixed fallback SQL handling for single-candidate mode:
  - `src/pipeline/vote.py`
  - `src/pipeline/evaluation.py`
- Impact:
  - Removed false syntax failures caused by single-character SQL fallback (e.g., `"S"`).
