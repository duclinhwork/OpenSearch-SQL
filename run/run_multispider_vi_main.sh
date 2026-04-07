data_mode="dev"
db_root_path="MultiSpider_VI_Bird"
start="${START:-0}"
end="${END:-2}"
pipeline_nodes="generate_db_schema+extract_col_value+extract_query_noun+column_retrieve_and_other_info+candidate_generate+align_correct+vote+evaluation"

engine="${OPENROUTER_MODEL:-minimax/minimax-m2.5:free}"
bert_model="hashing-fallback"
n_candidates="${N_CANDIDATES:-3}"
skip_align="${SKIP_ALIGN:-false}"

pipeline_setup='{
  "generate_db_schema": {
    "engine": "'"${engine}"'",
    "bert_model": "'"${bert_model}"'",
    "device":"cpu"
  },
  "extract_col_value": {
    "engine": "'"${engine}"'",
    "temperature": 0.0
  },
  "extract_query_noun": {
    "engine": "'"${engine}"'",
    "temperature": 0.0
  },
  "column_retrieve_and_other_info": {
    "engine": "'"${engine}"'",
    "bert_model": "'"${bert_model}"'",
    "device":"cpu",
    "temperature":0.3,
    "top_k":10,
    "disable_query_order": true
  },
  "candidate_generate":{
    "engine": "'"${engine}"'",
    "temperature": 0.7,
    "n": '"${n_candidates}"',
    "return_question":"True",
    "single":"'"$([ "${n_candidates}" -eq 1 ] && echo True || echo False)"'"
  },
  "align_correct":{
    "engine": "'"${engine}"'",
    "n": '"${n_candidates}"',
    "bert_model": "'"${bert_model}"'",
    "device":"cpu",
    "align_methods":"style_align",
    "skip_align": '"${skip_align}"'
  }
}'

python3 -u src/main.py \
  --data_mode "${data_mode}" \
  --db_root_path "${db_root_path}" \
  --pipeline_nodes "${pipeline_nodes}" \
  --pipeline_setup "${pipeline_setup}" \
  --start "${start}" \
  --end "${end}"
