#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import importlib
import json
import os
import sqlite3
from pathlib import Path

required_modules = [
    "requests",
    "sklearn",
    "pandas",
    "numpy",
    "func_timeout",
]

missing = []
for name in required_modules:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)

print("=== KIEM TRA MOI TRUONG ===")
print(f"python          : ok")
print(f"modules_missing : {missing if missing else 'none'}")

root = Path("MultiSpider_VI_Bird")
print("\n=== KIEM TRA DATASET ===")
print(f"dataset_dir     : {'ok' if root.exists() else 'missing'}")

required_paths = [
    root / "data_preprocess" / "dev.json",
    root / "data_preprocess" / "train.json",
    root / "dev" / "dev_databases",
    root / "train" / "train_databases",
    root / "fewshot" / "questions.json",
]

missing_paths = [str(path) for path in required_paths if not path.exists()]
print(f"paths_missing   : {missing_paths if missing_paths else 'none'}")

if root.exists() and not missing_paths:
    meta_path = root / "prepare_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        print(f"prepare_meta    : {meta}")
    db_path = root / "dev" / "dev_databases" / "concert_singer" / "concert_singer.sqlite"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        count = conn.execute("select count(*) from singer").fetchone()[0]
        conn.close()
        print(f"sqlite_smoke    : ok (concert_singer.singer={count})")
    else:
        print("sqlite_smoke    : skipped (concert_singer not found)")

print("\n=== KIEM TRA API KEY ===")
print(f"OPENAI_API_KEY      : {'set' if os.getenv('OPENAI_API_KEY') else 'missing'}")
print(f"OPENROUTER_API_KEY  : {'set' if os.getenv('OPENROUTER_API_KEY') else 'missing'}")
print(f"OPENAI_MODEL        : {os.getenv('OPENAI_MODEL', '') or '--'}")
print(f"OPENROUTER_MODEL    : {os.getenv('OPENROUTER_MODEL', '') or '--'}")
PY
