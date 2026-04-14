#!/usr/bin/env bash
set -euo pipefail

output_root="${OUTPUT_ROOT:-MultiSpider_VI_Bird}"
value_mode="${VALUE_MODE:-with_original_value}"   # with_original_value | with_english_value
max_databases="${MAX_DATABASES:-0}"               # 0 = tải toàn bộ DB
bert_model="${BERT_MODEL:-hashing-fallback}"
force_refresh="${FORCE_REFRESH:-0}"               # 1 = tải lại metadata
skip_emb="${SKIP_EMB:-0}"                         # 1 = bỏ qua bước embedding

prepare_args=(
  --output_root "${output_root}"
  --value_mode "${value_mode}"
  --max_databases "${max_databases}"
)

if [ "${force_refresh}" = "1" ]; then
  prepare_args+=(--force_refresh)
fi

python3 -u src/database_process/prepare_multispider_vi.py "${prepare_args[@]}"

if [ "${skip_emb}" != "1" ]; then
  python3 -u src/database_process/make_emb.py \
    --db_root_directory "${output_root}" \
    --dev_database "dev/dev_databases" \
    --bert_model "${bert_model}"
fi

OUTPUT_ROOT_FOR_SUMMARY="${output_root}" python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["OUTPUT_ROOT_FOR_SUMMARY"])
meta_path = root / "prepare_meta.json"
if not meta_path.exists():
    raise SystemExit("Thiếu prepare_meta.json sau khi setup dataset.")

meta = json.loads(meta_path.read_text())
dev_sqlite = len(list((root / "dev" / "dev_databases").glob("*/*.sqlite")))
train_sqlite = len(list((root / "train" / "train_databases").glob("*/*.sqlite")))
emb_files = len(list((root / "emb").glob("*.pkl.gz")))

print("=== Dataset Sẵn Sàng ===")
print(f"output_root   : {root}")
print(f"value_mode    : {meta.get('value_mode')}")
print(f"dev_rows      : {meta.get('dev_rows')}")
print(f"train_rows    : {meta.get('train_rows')}")
print(f"dev_db_ids    : {meta.get('dev_db_ids')}")
print(f"train_db_ids  : {meta.get('train_db_ids')}")
print(f"dev_sqlite    : {dev_sqlite}")
print(f"train_sqlite  : {train_sqlite}")
print(f"emb_files     : {emb_files}")
PY
