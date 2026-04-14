# OpenSearch-SQL

Repo này đã được rút gọn để tập trung vào **một dataset thật sự dùng được ngay**:

- `MultiSpider_VI_Bird`

Các nhánh `Bird` và `ViText2SQL` đã bị loại khỏi luồng sử dụng chính vì trong workspace hiện tại chúng không còn đầy đủ dữ liệu để chạy end-to-end, dễ gây nhầm lẫn cho người mới.

## 1. Dataset đang được hỗ trợ

Dataset chính thức:

- `MultiSpider_VI_Bird`

Trạng thái hiện tại:

- có `data_preprocess/dev.json` và `train.json`
- có SQLite thật cho `dev` và `train`
- có few-shot và `correct_fewshot2.json`
- có embedding cho dev split
- chạy được với pipeline hiện tại

Khuyến nghị:

- dùng `dev` để bắt đầu
- dùng `MultiSpider_VI_Bird` cho cả CLI và UI demo

## 2. Cài đặt thư viện

```bash
pip install -r requirements.txt
```

Kiểm tra nhanh môi trường:

```bash
bash run/check_ready.sh
```

## 3. Script cho người mới: tải và chuẩn bị dataset

Chạy một lệnh để tải metadata, tải SQLite và sinh embedding cho dev split:

```bash
bash run/setup_multispider_vi.sh
```

Biến môi trường hữu ích:

- `MAX_DATABASES=0`: tải toàn bộ database, mặc định là toàn bộ
- `FORCE_REFRESH=1`: tải lại metadata
- `SKIP_EMB=1`: bỏ qua bước sinh embedding
- `BERT_MODEL=hashing-fallback`: dùng encoder fallback nhẹ

Ví dụ:

```bash
MAX_DATABASES=0 bash run/setup_multispider_vi.sh
```

## 4. Chạy pipeline

Script chạy mặc định:

```bash
MODEL=minimax/minimax-m2.5:free OPENROUTER_API_KEY=... bash run/run_multispider_vi.sh
```

Các biến thường dùng:

- `DATA_MODE=dev`
- `START=0`
- `END=2`
- `N_CANDIDATES=3`
- `SKIP_ALIGN=false`
- `MODEL=...`

Ví dụ chỉ chạy 1 sample:

```bash
MODEL=minimax/minimax-m2.5:free OPENROUTER_API_KEY=... START=0 END=1 N_CANDIDATES=1 bash run/run_multispider_vi.sh
```

Kết quả sẽ nằm dưới:

```text
results/dev/<pipeline_nodes>/MultiSpider_VI_Bird/<timestamp>/
```

## 5. Mở UI demo

```bash
bash run/run_demo_ui.sh
```

Địa chỉ mặc định:

```text
http://127.0.0.1:8765
```

UI hỗ trợ:

- chọn dataset/sample theo từng bước
- nhập API key và model trực tiếp trên UI
- chạy sample hoặc tự nhập câu hỏi mới
- SQL sandbox để xem bảng và chạy query chỉ-đọc
- xem kết quả cuối hoặc full trace từng node

## 6. Cấu trúc repo sau khi dọn

Phần quan trọng:

- `src/main.py`: entrypoint chạy pipeline
- `src/pipeline/`: các node của pipeline
- `src/runner/`: runtime, logging, compare SQL, task manager
- `src/database_process/prepare_multispider_vi.py`: chuẩn bị dataset
- `src/database_process/make_emb.py`: sinh embedding
- `run/setup_multispider_vi.sh`: script setup cho người mới
- `run/check_ready.sh`: kiểm tra nhanh môi trường và dataset
- `run/run_multispider_vi.sh`: script chạy pipeline
- `run/run_demo_ui.sh`: mở UI demo

Dataset local:

- `MultiSpider_VI_Bird/`

## 7. Lưu ý vận hành

- Nếu model có dạng `provider/model` thì thường dùng `OPENROUTER_API_KEY`
- Nếu dùng model kiểu OpenAI-compatible như `gpt-4o-mini` thì cần `OPENAI_API_KEY`
- `train` có thể chạy, nhưng luồng được tối ưu và kiểm tra trước hết cho `dev`
- Nếu thiếu network, hãy copy sẵn thư mục `MultiSpider_VI_Bird/` từ máy khác rồi chạy tiếp

## 8. Mục tiêu của bản rút gọn này

Repo hiện tại ưu tiên:

- ít lựa chọn hơn
- ít script thừa hơn
- ít dataset mồi gây hiểu nhầm hơn
- onboarding rõ ràng cho người mới

Nếu cần mở rộng thêm dataset khác sau này, nên thêm lại theo cách:

- có script setup riêng
- có tài liệu riêng
- không trộn vào luồng mặc định của repo
