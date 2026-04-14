import argparse
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


HF_BASE = "https://huggingface.co/datasets/dreamerdeo/multispider/resolve/main"


class DatasetDownloadError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def download_json(path: str) -> Any:
    url = f"{HF_BASE}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise DatasetDownloadError(f"Unable to download {url}: {exc}") from exc


def download_file(path: str, target: Path) -> bool:
    url = f"{HF_BASE}/{path}"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())
        return True
    except (urllib.error.HTTPError, urllib.error.URLError):
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


def prepared_dataset_paths(output_root: Path) -> Dict[str, Path]:
    return {
        "dev_rows": output_root / "dev" / "dev.json",
        "train_rows": output_root / "train" / "train.json",
        "tables": output_root / "dev" / "dev_tables.json",
    }


def load_existing_prepared_dataset(
    output_root: Path,
    value_mode: str,
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
    meta_path = output_root / "prepare_meta.json"
    if meta_path.exists():
        meta = read_json(meta_path)
        if meta.get("dataset") != "multispider_vi" or meta.get("value_mode") != value_mode:
            return None

    paths = prepared_dataset_paths(output_root)
    if not all(path.exists() for path in paths.values()):
        return None
    return (
        read_json(paths["dev_rows"]),
        read_json(paths["train_rows"]),
        read_json(paths["tables"]),
    )


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


def ensure_sqlite_available(output_root: Path, db_id: str) -> str:
    dev_target = output_root / "dev" / "dev_databases" / db_id / f"{db_id}.sqlite"
    train_target = output_root / "train" / "train_databases" / db_id / f"{db_id}.sqlite"

    if dev_target.exists():
        train_target.parent.mkdir(parents=True, exist_ok=True)
        if not train_target.exists():
            shutil.copy2(dev_target, train_target)
        return "reused"

    if train_target.exists():
        dev_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(train_target, dev_target)
        return "reused"

    rel = f"dataset/spider/database/{db_id}/{db_id}.sqlite"
    if not download_file(rel, dev_target):
        return "missing"

    train_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dev_target, train_target)
    return "downloaded"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare MultiSpider Vietnamese data in the OpenSearch-SQL layout.")
    parser.add_argument("--output_root", type=str, default="MultiSpider_VI_Bird")
    parser.add_argument(
        "--value_mode",
        type=str,
        default="with_original_value",
        choices=["with_original_value", "with_english_value"],
    )
    parser.add_argument(
        "--max_databases",
        type=int,
        default=0,
        help="0 means download all databases used by train/dev.",
    )
    parser.add_argument("--copy_correct_fewshot_from", type=str, default="resources/correct_fewshot2.json")
    parser.add_argument(
        "--force_refresh",
        action="store_true",
        help="Ignore locally prepared JSON files and re-download dataset metadata.",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    existing_prepared = None if args.force_refresh else load_existing_prepared_dataset(output_root, args.value_mode)
    if existing_prepared is not None:
        dev_rows, train_rows, tables_vi = existing_prepared
        print(f"Reusing existing prepared dataset JSON from: {output_root}")
    else:
        try:
            dev_raw = download_json(f"dataset/multispider/{args.value_mode}/dev_vi.json")
            train_raw = download_json(f"dataset/multispider/{args.value_mode}/train_vi.json")
            tables_vi = download_json(f"dataset/multispider/{args.value_mode}/tables_vi.json")
        except DatasetDownloadError as exc:
            expected_paths = prepared_dataset_paths(output_root)
            expected = ", ".join(str(path.relative_to(output_root)) for path in expected_paths.values())
            raise SystemExit(
                "Failed to fetch MultiSpider-VI metadata and no reusable local prepared dataset was found.\n"
                f"Reason: {exc}\n"
                f"Expected existing files under {output_root}: {expected}\n"
                "Either rerun with network access or reuse/copy a prepared MultiSpider_VI_Bird directory."
            ) from exc
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
    write_json(
        output_root / "prepare_meta.json",
        {
            "dataset": "multispider_vi",
            "value_mode": args.value_mode,
            "dev_rows": len(dev_rows),
            "train_rows": len(train_rows),
            "dev_db_ids": len({row["db_id"] for row in dev_rows}),
            "train_db_ids": len({row["db_id"] for row in train_rows}),
        },
    )

    source_correct = Path(args.copy_correct_fewshot_from)
    if source_correct.exists():
        shutil.copy2(source_correct, output_root / "correct_fewshot2.json")
    else:
        write_json(output_root / "correct_fewshot2.json", {})

    db_ids = unique_db_ids(dev_rows, train_rows)
    if args.max_databases > 0:
        db_ids = db_ids[: args.max_databases]

    dev_db_ids = {row["db_id"] for row in dev_rows}
    reused = 0
    downloaded = 0
    failed: List[str] = []
    for db_id in db_ids:
        status = ensure_sqlite_available(output_root, db_id)
        if status == "missing":
            failed.append(db_id)
            continue
        if status == "reused":
            reused += 1
        else:
            downloaded += 1

    print(f"Prepared dataset at: {output_root}")
    print(f"SQLite databases available: {downloaded + reused}/{len(db_ids)} (reused {reused}, downloaded {downloaded})")
    if failed:
        print(f"Missing sqlite for {len(failed)} db_ids. First 20: {failed[:20]}")
        missing_dev = [db_id for db_id in failed if db_id in dev_db_ids]
        if missing_dev:
            raise SystemExit(
                "Missing SQLite databases required by the dev split, so embedding generation cannot continue.\n"
                f"First 20 missing dev db_ids: {missing_dev[:20]}"
            )


if __name__ == "__main__":
    main()
