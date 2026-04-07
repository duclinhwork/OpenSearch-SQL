# OpenSearch-SQL trên ViText2SQL: Lý thuyết, Mapping, Tái tạo, Vấn đề

## 1) Các khái niệm chính trong OpenSearch-SQL
- Schema Linking: ánh xạ câu hỏi tự nhiên vào bảng/cột/giá trị có khả năng liên quan.
- SQL Candidate Generation: sinh nhiều SQL ứng viên từ prompt có schema + few-shot.
- Self-Consistency/Voting: gom các ứng viên và chọn câu trả lời ổn định nhất.
- Alignment & Correction: hậu kiểm logic/cú pháp/thực thi để giảm hallucination.
- Execution-based Evaluation: so sánh kết quả chạy SQL dự đoán với SQL gold trên SQLite.

Trong BIRD, các bước trên dùng dữ liệu + DB thật, nên alignment/evaluation có tín hiệu mạnh từ execution.

## 2) Mapping lý thuyết -> module trong repo
- Orchestration:
  - `src/main.py` -> nạp dataset, chạy workflow.
  - `src/runner/run_manager.py` -> điều phối task và ghi kết quả.
- Pipeline nodes (`src/pipeline/`):
  - `generate_db_schema`: mô tả schema DB.
  - `extract_col_value`, `extract_query_noun`: trích thực thể/giá trị từ câu hỏi.
  - `column_retrieve_and_other_info`: lấy cột liên quan + FK + value hints.
  - `candidate_generate`: sinh SQL ứng viên.
  - `align_correct`, `vote`, `evaluation`: alignment, chọn kết quả cuối, chấm execution.
- Utilities:
  - `src/llm/model.py`: lớp gọi LLM (đã refactor hỗ trợ OpenRouter qua env).
  - `src/database_process/prepare_vitext2sql.py`: adapter ViText2SQL -> Bird-like layout.

## 3) Quy trình tái tạo trên ViText2SQL (đã triển khai)
### 3.1 Chuẩn bị dữ liệu Việt
```bash
bash run/run_vi_prepare.sh
```
Script sẽ:
- tải ViText2SQL (`word-level`/`syllable-level`);
- chuyển thành layout tương thích OpenSearch-SQL (`data_preprocess`, `fewshot`, `dev/train/..._databases`);
- tạo SQLite schema-only từ `tables.json` (do ViText2SQL không phát hành DB records đầy đủ);
- tạo embedding nhẹ để pipeline chạy được.

### 3.2 Chạy pipeline
- Core (ổn định hơn, không chạy align/vote):
```bash
OPENROUTER_API_KEY=... OPENROUTER_MODEL=minimax/minimax-m2.5:free bash run/run_vi_core.sh
```
- Full chain (bao gồm align/vote/eval):
```bash
OPENROUTER_API_KEY=... OPENROUTER_MODEL=minimax/minimax-m2.5:free bash run/run_vi_main.sh
```

## 4) Kết quả tái tạo hiện tại
- Đã chạy thành công liên tục qua các node:
  - `generate_db_schema`
  - `extract_col_value`
  - `extract_query_noun`
  - `column_retrieve_and_other_info`
  - `candidate_generate`
- Ví dụ SQL sinh ra (task `architecture_0`):
  - `SELECT COUNT(*) FROM kiến_trúc_sư WHERE giới_tính = 'Nữ';`

## 5) Vấn đề tồn đọng và nguyên nhân
1. Thiếu dữ liệu DB thật của ViText2SQL:
- Hiện chỉ có schema-only DB, nên execution-based metric không phản ánh chất lượng thật.
- Alignment phụ thuộc mạnh vào execution/value grounding nên dễ nghẽn/chậm.

2. Metadata ViText2SQL có trường hợp trùng tên bảng/cột:
- Đã phải disambiguate khi dựng SQLite (`__dupN`), có thể làm lệch nhẹ so với SQL gốc.

3. Độ ổn định model free trên OpenRouter:
- Tốc độ/availability dao động; một số request dài có thể timeout/chậm.

## 6) Hướng xử lý tiếp theo (ưu tiên)
1. Bổ sung DB records thật cho ViText2SQL (ưu tiên cao nhất).
2. Tạo adapter đánh giá riêng cho tiếng Việt:
- tách “core generation quality” và “execution quality”.
3. Giảm độ nặng align phase:
- cắt prompt, giới hạn số candidate, thêm checkpoint/fallback rõ ràng.
