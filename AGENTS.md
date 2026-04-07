# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/` and is split by responsibility:
- `src/main.py`: CLI entrypoint for running pipelines.
- `src/pipeline/`: workflow nodes (schema generation, retrieval, candidate generation, alignment, voting, evaluation).
- `src/runner/`: orchestration, logging, task lifecycle, database/result management.
- `src/llm/`: model wrappers and prompt definitions.
- `src/database_process/`: dataset preprocessing and embedding generation utilities.

Data and assets:
- `Bird/`: benchmark data and few-shot resources.
- `run/`: runnable shell entrypoints.
- `image/`: figures used by documentation.

## Build, Test, and Development Commands
Install dependencies:
```bash
pip install -r requirements.txt
```

Preprocess dataset artifacts (tables, few-shot inputs, embeddings):
```bash
sh run/run_preprocess.sh
```

Run the main Text-to-SQL pipeline:
```bash
sh run/run_main.sh
```

Run directly for quick debugging (example):
```bash
python -u src/main.py --data_mode dev --db_root_path Bird --pipeline_nodes "..." --pipeline_setup "{...}" --start 0 --end 1
```

## Coding Style & Naming Conventions
- Python code uses 4-space indentation and snake_case for functions, variables, and file names.
- Prefer explicit type hints (`List`, `Dict`, `Any`) for public function signatures.
- Keep modules focused by stage (pipeline node logic in `src/pipeline/`, orchestration in `src/runner/`).
- Follow existing import style: standard library first, then local packages.

## Testing Guidelines
This repository currently has no dedicated `tests/` suite. For changes:
- Validate with `sh run/run_preprocess.sh` (if preprocessing is affected).
- Validate with `sh run/run_main.sh` on a small slice (`--start`, `--end`) before full runs.
- Include expected output paths (for example `results/.../-evaluation.json`) in your PR notes.

## Commit & Pull Request Guidelines
Git history is currently minimal (`Initial clean commit`), so use concise, imperative commit messages (for example `Add checkpoint guard for empty history`).

For pull requests, include:
- What changed and why.
- Exact commands used to validate.
- Any dataset/model assumptions (API keys, `bert_model` path, engine names).
- Representative logs or result file paths when behavior changes.

## Security & Configuration Tips
- Do not commit secrets. Keep API keys out of source and set them locally.
- Update model/path settings in `run/run_main.sh` and related config points before running.
- Large generated artifacts under `results/` should not be committed unless explicitly required.
