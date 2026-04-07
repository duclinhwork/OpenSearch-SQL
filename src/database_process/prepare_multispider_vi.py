import argparse
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


HF_BASE = "https://huggingface.co/datasets/dreamerdeo/multispider/resolve/main"


def download_json(path: str) -> Any:
    url = f"{HF_BASE}/{path}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(path: str, target: Path) -> bool:
    url = f"{HF_BASE}/{path}"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())
        return True
    except urllib.error.HTTPError:
        return False


def normalize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        normalized.append(
            {
                "question_id": i,
                "db_id": row["db_id"],
                "question": row.get("question", ""),
                "raw_question": row.get("question", ""),
                "evidence": "",
                "SQL": row.get("query", ""),
                "query": row.get("query", ""),
            }
        )
    return normalized


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)


def build_min_fewshot(dev_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    question_prompt = (
        "/* Some SQL examples are provided based on similar problems: */\n"
        "/* Answer the following: Example question */\n"
        "#reason: Analyze intent and schema.\n"
        "#columns: []\n"
        "#values: []\n"
        "#SELECT: target columns\n"
        "#SQL-Like: SELECT ...\n"
        "#SQL: SELECT 1"
    )
    extract_prompt = (
        "/* Some extract examples are provided based on similar problems: */\n"
        "/* Answer the following: Example question */\n"
        "#reason: Extract columns and values from question.\n"
        "#columns: []\n"
        "#values: []"
    )

    questions = []
    extracts = []
    for row in dev_rows:
        questions.append(
            {
                "question": row["question"],
                "evidence": "",
                "raw_question": row["raw_question"],
                "prompt": question_prompt,
                "n_examples": 1,
                "db_id": row["db_id"],
            }
        )
        extracts.append(
            {
                "question": row["question"],
                "evidence": "",
                "raw_question": row["raw_question"],
                "prompt": extract_prompt,
                "n_examples": 1,
                "db_id": row["db_id"],
            }
        )
    return {"args": {}, "costs": {}, "questions": questions, "extract": extracts}


def unique_db_ids(*datasets: List[Dict[str, Any]]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for ds in datasets:
        for row in ds:
            db_id = row["db_id"]
            if db_id not in seen:
                seen.add(db_id)
                ordered.append(db_id)
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare MultiSpider Vietnamese data in Bird-like layout.")
    parser.add_argument("--output_root", type=str, default="MultiSpider_VI_Bird")
    parser.add_argument("--value_mode", type=str, default="with_original_value", choices=["with_original_value", "with_english_value"])
    parser.add_argument("--max_databases", type=int, default=0, help="0 means download all databases used by train/dev.")
    parser.add_argument("--copy_correct_fewshot_from", type=str, default="Bird/correct_fewshot2.json")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    dev_raw = download_json(f"dataset/multispider/{args.value_mode}/dev_vi.json")
    train_raw = download_json(f"dataset/multispider/{args.value_mode}/train_vi.json")
    tables_vi = download_json(f"dataset/multispider/{args.value_mode}/tables_vi.json")

    dev_rows = normalize_rows(dev_raw)
    train_rows = normalize_rows(train_raw)

    write_json(output_root / "dev" / "dev.json", dev_rows)
    write_json(output_root / "train" / "train.json", train_rows)
    write_json(output_root / "dev" / "dev_tables.json", tables_vi)
    write_json(output_root / "train" / "train_tables.json", tables_vi)
    write_json(output_root / "data_preprocess" / "dev.json", dev_rows)
    write_json(output_root / "data_preprocess" / "train.json", train_rows)
    write_json(output_root / "data_preprocess" / "tables.json", tables_vi)
    write_json(output_root / "fewshot" / "questions.json", build_min_fewshot(dev_rows))

    source_correct = Path(args.copy_correct_fewshot_from)
    if source_correct.exists():
        shutil.copy2(source_correct, output_root / "correct_fewshot2.json")
    else:
        write_json(output_root / "correct_fewshot2.json", {})

    db_ids = unique_db_ids(dev_rows, train_rows)
    if args.max_databases > 0:
        db_ids = db_ids[: args.max_databases]

    downloaded = 0
    failed: List[str] = []
    for db_id in db_ids:
        rel = f"dataset/spider/database/{db_id}/{db_id}.sqlite"
        dev_target = output_root / "dev" / "dev_databases" / db_id / f"{db_id}.sqlite"
        train_target = output_root / "train" / "train_databases" / db_id / f"{db_id}.sqlite"
        ok = download_file(rel, dev_target)
        if not ok:
            failed.append(db_id)
            continue
        train_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dev_target, train_target)
        downloaded += 1

    print(f"Prepared dataset at: {output_root}")
    print(f"Downloaded sqlite databases: {downloaded}/{len(db_ids)}")
    if failed:
        print(f"Missing sqlite for {len(failed)} db_ids. First 20: {failed[:20]}")


if __name__ == "__main__":
    main()
