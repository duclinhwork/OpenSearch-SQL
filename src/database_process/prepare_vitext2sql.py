import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List
import urllib.request


BASE_RAW_URL = "https://raw.githubusercontent.com/VinAIResearch/ViText2SQL/master/data"


def download_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_record(record: Dict[str, Any], question_id: int) -> Dict[str, Any]:
    return {
        "question_id": question_id,
        "db_id": record["db_id"],
        "question": record.get("question", ""),
        "raw_question": record.get("question", ""),
        "evidence": "",
        "SQL": record.get("query", ""),
        "query": record.get("query", ""),
    }


def build_fewshot_stub(dev_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    question_prompt = (
        "/* Some SQL examples are provided based on similar problems: */\n"
        "/* Answer the following: Example question */\n"
        "#reason: Identify relevant tables and filters.\n"
        "#columns: []\n"
        "#values: []\n"
        "#SELECT: key target columns\n"
        "#SQL-Like: SELECT ...\n"
        "#SQL: SELECT 1"
    )
    extract_prompt = (
        "/* Some extract examples are provided based on similar problems: */\n"
        "/* Answer the following: Example question */\n"
        "#reason: Parse key entities and values.\n"
        "#columns: []\n"
        "#values: []"
    )
    questions = []
    extracts = []
    for row in dev_records:
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


def map_type(raw_type: str) -> str:
    lowered = raw_type.lower()
    if lowered in {"number", "float", "real", "double"}:
        return "REAL"
    if lowered in {"int", "integer", "id", "boolean", "bool"}:
        return "INTEGER"
    if lowered in {"text", "varchar", "string", "time", "date"}:
        return "TEXT"
    return "TEXT"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_schema_only_sqlite(db_file: Path, table_meta: Dict[str, Any]) -> None:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists():
        db_file.unlink()

    raw_table_names = table_meta["table_names_original"]
    column_names = table_meta["column_names_original"]
    column_types = table_meta["column_types"]
    primary_keys = set(table_meta.get("primary_keys", []))
    foreign_keys = table_meta.get("foreign_keys", [])

    table_columns: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(len(raw_table_names))}
    physical_table_name: Dict[int, str] = {}
    table_name_seen: Dict[str, int] = {}
    for idx, table_name in enumerate(raw_table_names):
        if table_name in table_name_seen:
            table_name_seen[table_name] += 1
            physical_table_name[idx] = f"{table_name}__dup{table_name_seen[table_name]}"
        else:
            table_name_seen[table_name] = 0
            physical_table_name[idx] = table_name

    physical_col_name: Dict[int, str] = {}
    used_names: Dict[int, Dict[str, int]] = {i: {} for i in range(len(raw_table_names))}
    for col_idx, (table_idx, col_name) in enumerate(column_names):
        if table_idx == -1:
            continue
        name_counter = used_names[table_idx]
        if col_name in name_counter:
            name_counter[col_name] += 1
            real_name = f"{col_name}__dup{name_counter[col_name]}"
        else:
            name_counter[col_name] = 0
            real_name = col_name
        physical_col_name[col_idx] = real_name
        table_columns[table_idx].append(
            {
                "col_idx": col_idx,
                "name": real_name,
                "type": map_type(column_types[col_idx]),
                "is_pk": col_idx in primary_keys,
            }
        )

    fk_by_table: Dict[int, List[str]] = {i: [] for i in range(len(raw_table_names))}
    for src_idx, dst_idx in foreign_keys:
        src_table_idx, src_col = column_names[src_idx]
        dst_table_idx, dst_col = column_names[dst_idx]
        if src_table_idx == -1 or dst_table_idx == -1:
            continue
        fk_by_table[src_table_idx].append(
            f"FOREIGN KEY ({qident(physical_col_name.get(src_idx, src_col))}) REFERENCES {qident(physical_table_name[dst_table_idx])}({qident(physical_col_name.get(dst_idx, dst_col))})"
        )

    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        for table_idx, table_name in physical_table_name.items():
            cols = table_columns.get(table_idx, [])
            if not cols:
                continue
            col_defs = [f"{qident(c['name'])} {c['type']}" for c in cols]
            pk_cols = [qident(c["name"]) for c in cols if c["is_pk"]]
            constraints = []
            if pk_cols:
                constraints.append(f"PRIMARY KEY ({', '.join(pk_cols)})")
            constraints.extend(fk_by_table.get(table_idx, []))
            ddl_body = ", ".join(col_defs + constraints)
            cursor.execute(f"CREATE TABLE {qident(table_name)} ({ddl_body});")
        conn.commit()


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare ViText2SQL in Bird-like layout for OpenSearch-SQL.")
    parser.add_argument("--output_root", type=str, default="ViText2SQL_Bird")
    parser.add_argument("--level", type=str, default="word-level", choices=["word-level", "syllable-level"])
    parser.add_argument("--copy_correct_fewshot_from", type=str, default="Bird/correct_fewshot2.json")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    dev_raw = download_json(f"{BASE_RAW_URL}/{args.level}/dev.json")
    train_raw = download_json(f"{BASE_RAW_URL}/{args.level}/train.json")
    tables_raw = download_json(f"{BASE_RAW_URL}/{args.level}/tables.json")

    dev_records = [normalize_record(row, i) for i, row in enumerate(dev_raw)]
    train_records = [normalize_record(row, i) for i, row in enumerate(train_raw)]

    write_json(output_root / "dev" / "dev.json", dev_records)
    write_json(output_root / "train" / "train.json", train_records)
    write_json(output_root / "dev" / "dev_tables.json", tables_raw)
    write_json(output_root / "train" / "train_tables.json", tables_raw)

    write_json(output_root / "data_preprocess" / "dev.json", dev_records)
    write_json(output_root / "data_preprocess" / "train.json", train_records)
    write_json(output_root / "data_preprocess" / "tables.json", tables_raw)

    write_json(output_root / "fewshot" / "questions.json", build_fewshot_stub(dev_records))

    source_correct = Path(args.copy_correct_fewshot_from)
    target_correct = output_root / "correct_fewshot2.json"
    if source_correct.exists():
        shutil.copy2(source_correct, target_correct)
    else:
        write_json(target_correct, {})

    for table_meta in tables_raw:
        db_id = table_meta["db_id"]
        dev_db_file = output_root / "dev" / "dev_databases" / db_id / f"{db_id}.sqlite"
        train_db_file = output_root / "train" / "train_databases" / db_id / f"{db_id}.sqlite"
        create_schema_only_sqlite(dev_db_file, table_meta)
        train_db_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dev_db_file, train_db_file)

    print(f"Prepared dataset at: {output_root}")


if __name__ == "__main__":
    main()
