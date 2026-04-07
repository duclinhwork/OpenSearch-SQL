set -e

output_root="MultiSpider_VI_Bird"
value_mode="with_original_value" # with_original_value | with_english_value
max_databases="${MAX_DATABASES:-0}" # 0 = all
bert_model="hashing-fallback"

python3 -u src/database_process/prepare_multispider_vi.py \
  --output_root "${output_root}" \
  --value_mode "${value_mode}" \
  --max_databases "${max_databases}"

python3 -u src/database_process/make_emb.py \
  --db_root_directory "${output_root}" \
  --dev_database "dev/dev_databases" \
  --bert_model "${bert_model}"
