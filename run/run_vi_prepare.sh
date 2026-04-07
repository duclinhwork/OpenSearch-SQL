set -e

output_root="ViText2SQL_Bird"
level="word-level" # word-level | syllable-level
bert_model="hashing-fallback"

python3 -u src/database_process/prepare_vitext2sql.py \
  --output_root "${output_root}" \
  --level "${level}"

python3 -u src/database_process/make_emb.py \
  --db_root_directory "${output_root}" \
  --dev_database "dev/dev_databases" \
  --bert_model "${bert_model}"
