# Project Change Log

## 2026-04-07 - MultiSpider Vietnamese Integration
Owner: **Nguyen Duc Linh (Nguyễn Đức Linh)**

### Scope
- Added dataset adapter for MultiSpider Vietnamese with SQLite assets.
- Added run scripts for prepare/core/full pipeline on MultiSpider-VI.
- Refactored runtime fallbacks to keep pipeline runnable under missing embeddings and constrained environments.

### Commands Executed (Evidence)
- `MAX_DATABASES=30 bash run/run_multispider_vi_prepare.sh`
  - Result: `Prepared dataset at: MultiSpider_VI_Bird`
  - Result: `Downloaded sqlite databases: 30/30`
- `OPENROUTER_MODEL=minimax/minimax-m2.5:free ... bash run/run_multispider_vi_main.sh`
  - Result: full node chain executed (`generate_db_schema -> ... -> evaluation`)
  - Noted runtime constraint: OpenRouter free models returned `429 Too Many Requests` during `extract_col_value` in some runs.

### New/Updated Artifacts
- Added:
  - `src/database_process/prepare_multispider_vi.py`
  - `run/run_multispider_vi_prepare.sh`
  - `run/run_multispider_vi_core.sh`
  - `run/run_multispider_vi_main.sh`
- Updated:
  - `src/pipeline/column_retrieve_and_other_info.py` (embedding fallback)
  - `src/pipeline/align_correct.py` (`skip_align` fast mode)
  - `src/runner/check_and_correct.py` (configurable timeouts, align bug fix)

### Experiment Logs
- Prepare/embedding logs are captured in terminal output and generated artifacts under:
  - `MultiSpider_VI_Bird/`
- Pipeline run outputs captured under:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/`

### Full Pipeline Trial (Requested)
Owner: **Nguyen Duc Linh (Nguyễn Đức Linh)**

- Command:
  - `OPENROUTER_MODEL=minimax/minimax-m2.5:free START=0 END=1 N_CANDIDATES=1 bash run/run_multispider_vi_main.sh`
  - `OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free START=0 END=1 N_CANDIDATES=1 bash run/run_multispider_vi_main.sh`
- Artifact:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-09-01-18/0_concert_singer.json`
- Outcome:
  - Full node chain executed up to `evaluation`.
  - Free-tier OpenRouter rate limit (`429`) occurred at `extract_col_value`, causing downstream nodes to mark `error`.

### Full Pipeline Trial (Paid) - Success
Owner: **Nguyen Duc Linh (Nguyễn Đức Linh)**

- Command:
  - `OPENROUTER_MODEL='google/gemini-2.5-flash-lite' START=0 END=1 N_CANDIDATES=1 SKIP_ALIGN=false bash run/run_multispider_vi_main.sh`
- Artifact:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-09-15-53/0_concert_singer.json`
- Outcome:
  - End-to-end full chain finished with all nodes `success`.
  - Execution evaluation on sample `concert_singer_0` returned `exec_res = 1`.

### Continue Run (5 Samples, Full Chain)
Owner: **Nguyen Duc Linh (Nguyễn Đức Linh)**

- Command:
  - `OPENROUTER_MODEL='google/gemini-2.5-flash-lite' START=0 END=5 N_CANDIDATES=1 SKIP_ALIGN=false bash run/run_multispider_vi_main.sh`
- Note:
  - Network sandbox produced DNS failures initially; rerun with elevated network permission.
- Artifact:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-09-24-50/`
- Outcome summary:
  - Completed `5/5` tasks with full node chain.
  - `align_correct`: `4 correct / 1 incorrect`
  - `vote`: `4 correct / 1 incorrect`

### Full Run (100 Samples, User requested)
Owner: **Nguyen Duc Linh (Nguyễn Đức Linh)**

- Command:
  - `OPENROUTER_MODEL='google/gemini-2.5-flash-lite' START=0 END=100 N_CANDIDATES=1 SKIP_ALIGN=true OPENROUTER_TIMEOUT=90 bash run/run_multispider_vi_main.sh`
- Artifact:
  - `results/dev/generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation/MultiSpider_VI_Bird/2026-04-07-10-23-13/`
- Statistics (`-statistics.json`):
  - `candidate_generate`: `75 correct / 22 incorrect / 3 error` (total `100`)
  - `align_correct`: `75 correct / 22 incorrect / 3 error` (total `100`)
  - `vote`: `75 correct / 22 incorrect / 3 error` (total `100`)

### Hotfixes while scaling 5 -> 100
- `src/pipeline/align_correct.py`:
  - fixed `skip_align` behavior when `candidate_generate.SQL` is a plain string.
- `src/pipeline/vote.py`:
  - fixed fallback SQL normalization for single candidate mode.
- `src/pipeline/evaluation.py`:
  - fixed candidate SQL extraction to avoid single-character parse.
- Why:
  - Prevent false SQL errors such as `near "S": syntax error` during evaluation.
