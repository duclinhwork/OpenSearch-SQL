# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/` and is split by responsibility:

- `src/main.py`: CLI entrypoint for chạy pipeline.
- `src/pipeline/`: các node của workflow như schema, retrieval, candidate generation, align, vote, evaluation.
- `src/runner/`: runtime, task lifecycle, logger, compare SQL, database manager.
- `src/llm/`: model wrappers và prompt.
- `src/database_process/`: script chuẩn bị `MultiSpider_VI_Bird` và sinh embedding.

Data và assets:

- `MultiSpider_VI_Bird/`: dataset đang được hỗ trợ chính thức.
- `resources/correct_fewshot2.json`: few-shot correction resource dùng khi setup dataset.
- `run/`: shell script cho setup, chạy pipeline và mở demo UI.
- `image/`: hình minh họa còn được dùng trong tài liệu.

## Build, Test, and Development Commands
Install dependencies:

```bash
pip install -r requirements.txt
```

Chuẩn bị dataset cho người mới:

```bash
bash run/setup_multispider_vi.sh
```

Chạy pipeline mặc định:

```bash
MODEL=minimax/minimax-m2.5:free OPENROUTER_API_KEY=... bash run/run_multispider_vi.sh
```

Mở demo UI:

```bash
bash run/run_demo_ui.sh
```

Chạy trực tiếp để debug:

```bash
python -u src/main.py --data_mode dev --db_root_path MultiSpider_VI_Bird --pipeline_nodes "..." --pipeline_setup "{...}" --start 0 --end 1
```

## Coding Style & Naming Conventions
- Python code uses 4-space indentation and snake_case for functions, variables, and file names.
- Prefer explicit type hints (`List`, `Dict`, `Any`) for public function signatures.
- Keep modules focused by stage (`src/pipeline/` cho node logic, `src/runner/` cho orchestration).
- Follow existing import style: standard library first, then local packages.

## Testing Guidelines
Repository hiện chưa có `tests/` riêng. Với thay đổi mới:

- Nếu sửa phần chuẩn bị dữ liệu, validate bằng `bash run/setup_multispider_vi.sh`.
- Nếu sửa pipeline/runtime, validate bằng `bash run/run_multispider_vi.sh` trên một lát nhỏ với `START` và `END`.
- Nếu sửa demo UI, ít nhất phải kiểm tra compile Python của backend và các hàm đọc dataset/SQLite.
- Ghi rõ artifact hoặc folder output liên quan khi hành vi thay đổi.

## Commit & Pull Request Guidelines
Use concise, imperative commit messages.

For pull requests, include:

- What changed and why.
- Exact commands used to validate.
- Any API/model assumptions (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `MODEL`, `BERT_MODEL`).
- Representative result paths if behavior changes.

## Security & Configuration Tips
- Do not commit secrets. Keep API keys out of source and set them locally or nhập qua demo UI.
- Không commit `results/` hoặc artifact sinh ra từ demo UI trừ khi thật sự cần.
- Dataset mặc định của repo là `MultiSpider_VI_Bird`; đừng thêm dataset mới vào luồng mặc định nếu chưa có script setup và tài liệu riêng.
