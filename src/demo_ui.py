#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


SRC_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SRC_ROOT.parent
HTML_PATH = SRC_ROOT / "demo_ui.html"
RESULTS_ROOT = REPO_ROOT / "results" / "demo_ui"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pipeline.align_correct import align_correct
from pipeline.candidate_generate import candidate_generate
from pipeline.column_retrieve_and_other_info import column_retrieve_and_other_info
from pipeline.evaluation import evaluation
from pipeline.extract_col_value import extract_col_value
from pipeline.extract_query_noun import extract_query_noun
from pipeline.generate_db_schema import generate_db_schema
from pipeline.pipeline_manager import PipelineManager
from pipeline.vote import vote
from runner.database_manager import DatabaseManager
from runner.logger import Logger, make_serial
from runner.task import Task


NODE_ORDER = [
    "generate_db_schema",
    "extract_col_value",
    "extract_query_noun",
    "column_retrieve_and_other_info",
    "candidate_generate",
    "align_correct",
    "vote",
    "evaluation",
]

NODE_FUNCTIONS = {
    "generate_db_schema": generate_db_schema,
    "extract_col_value": extract_col_value,
    "extract_query_noun": extract_query_noun,
    "column_retrieve_and_other_info": column_retrieve_and_other_info,
    "candidate_generate": candidate_generate,
    "align_correct": align_correct,
    "vote": vote,
    "evaluation": evaluation,
}

NODE_META = {
    "generate_db_schema": {
        "title": "Bước 1: Đọc Schema",
        "description": "Tạo ảnh chụp schema và ngữ cảnh database để các bước sau dùng lại.",
    },
    "extract_col_value": {
        "title": "Bước 2: Phỏng đoán Cột/Giá Trị",
        "description": "Dùng few-shot để đoán những cột và giá trị có khả năng xuất hiện trong câu hỏi.",
    },
    "extract_query_noun": {
        "title": "Bước 3: Tách Ý Từ Câu Hỏi",
        "description": "Chuẩn hóa câu hỏi thành danh sách cột và giá trị ứng viên để truy hồi.",
    },
    "column_retrieve_and_other_info": {
        "title": "Bước 4: Truy Hồi Ngữ Cảnh",
        "description": "Lấy các cột liên quan, khóa ngoại và giá trị ứng viên từ database đích.",
    },
    "candidate_generate": {
        "title": "Bước 5: Sinh SQL Ứng Viên",
        "description": "Sinh một hoặc nhiều câu SQL từ prompt đã ghép với schema và ngữ cảnh.",
    },
    "align_correct": {
        "title": "Bước 6: Căn Chỉnh / Sửa Lỗi",
        "description": "Đối chiếu SQL ứng viên với schema và tín hiệu chạy thử để sửa và gom ứng viên.",
    },
    "vote": {
        "title": "Bước 7: Bầu Chọn",
        "description": "Chọn câu SQL tốt nhất trong các ứng viên sau khi căn chỉnh.",
    },
    "evaluation": {
        "title": "Bước 8: Đánh Giá",
        "description": "Chạy SQL dự đoán và SQL chuẩn trên SQLite rồi so sánh kết quả.",
    },
}

PIPELINE_PRESETS = {
    "full": {
        "label": "Full Pipeline",
        "nodes": NODE_ORDER,
    },
    "candidate_only": {
        "label": "Stop At Candidate Generation",
        "nodes": NODE_ORDER[:5],
    },
}

READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH|PRAGMA|EXPLAIN)\b", re.IGNORECASE)
LOG_HEADER = re.compile(r"^#+\s*(Human|AI) at step (.+?)\s*#+$")


def is_openrouter_model(model_name: str) -> bool:
    model = (model_name or "").strip()
    return "/" in model or model.startswith("qwen")


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(make_serial(payload), ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: BaseHTTPRequestHandler, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
    json_response(handler, {"error": message}, status=status)


def read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    raw_length = handler.headers.get("Content-Length", "0")
    length = int(raw_length or "0")
    body = handler.rfile.read(length) if length else b"{}"
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def now_ts() -> float:
    return time.time()


def now_label() -> str:
    return time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())


def detect_dataset_roots() -> List[Path]:
    roots: List[Path] = []
    for path in sorted(REPO_ROOT.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if (path / "data_preprocess").is_dir():
            roots.append(path)
    return roots


def dataset_root_by_name(name: str) -> Path:
    root = REPO_ROOT / name
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset root '{name}' does not exist.")
    if not (root / "data_preprocess").is_dir():
        raise FileNotFoundError(f"Dataset root '{name}' is missing 'data_preprocess/'.")
    return root


def load_dataset_rows(dataset_name: str, data_mode: str) -> List[Dict[str, Any]]:
    path = dataset_root_by_name(dataset_name) / "data_preprocess" / f"{data_mode}.json"
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        rows = json.load(file)
    return rows


def load_sample(dataset_name: str, data_mode: str, question_id: int) -> Dict[str, Any]:
    rows = load_dataset_rows(dataset_name, data_mode)
    for row in rows:
        if int(row.get("question_id", -1)) == int(question_id):
            return row
    raise KeyError(f"Question id {question_id} was not found in {dataset_name}/{data_mode}.")


def list_dataset_modes(dataset_root: Path) -> List[str]:
    modes: List[str] = []
    for mode in ("dev", "train"):
        if (dataset_root / "data_preprocess" / f"{mode}.json").exists():
            modes.append(mode)
    return modes


def dataset_summary(dataset_root: Path) -> Dict[str, Any]:
    modes = list_dataset_modes(dataset_root)
    sample_counts: Dict[str, int] = {}
    db_counts: Dict[str, int] = {}
    db_ids: Dict[str, List[str]] = {}
    for mode in modes:
        rows = load_dataset_rows(dataset_root.name, mode)
        ids = sorted({row["db_id"] for row in rows})
        sample_counts[mode] = len(rows)
        db_counts[mode] = len(ids)
        db_ids[mode] = ids
    dev_dir = dataset_root / "dev" / "dev_databases"
    train_dir = dataset_root / "train" / "train_databases"
    return {
        "name": dataset_root.name,
        "modes": modes,
        "sample_counts": sample_counts,
        "db_counts": db_counts,
        "db_ids": db_ids,
        "has_embeddings": (dataset_root / "emb").exists(),
        "has_dev_sqlite": dev_dir.exists(),
        "has_train_sqlite": train_dir.exists(),
        "path": str(dataset_root),
    }


def catalog() -> List[Dict[str, Any]]:
    return [dataset_summary(path) for path in detect_dataset_roots()]


def sample_brief(row: Dict[str, Any]) -> Dict[str, Any]:
    question = row.get("raw_question") or row.get("question") or ""
    return {
        "question_id": int(row.get("question_id", 0)),
        "db_id": row.get("db_id", ""),
        "question": question,
        "evidence": row.get("evidence", ""),
        "sql": row.get("SQL", ""),
    }


def list_samples(dataset_name: str, data_mode: str, query: str = "", db_id: str = "", limit: int = 80) -> List[Dict[str, Any]]:
    query_lower = query.lower().strip()
    selected_db = db_id.strip()
    rows = load_dataset_rows(dataset_name, data_mode)
    matches: List[Dict[str, Any]] = []
    for row in rows:
        if selected_db and row.get("db_id") != selected_db:
            continue
        haystack = f"{row.get('db_id', '')} {row.get('question', '')} {row.get('raw_question', '')}".lower()
        if query_lower and query_lower not in haystack:
            continue
        matches.append(sample_brief(row))
        if len(matches) >= limit:
            break
    return matches


def list_db_ids(dataset_name: str, data_mode: str) -> List[str]:
    rows = load_dataset_rows(dataset_name, data_mode)
    return sorted({row["db_id"] for row in rows})


def sqlite_path(dataset_name: str, data_mode: str, db_id: str) -> Path:
    path = dataset_root_by_name(dataset_name) / data_mode / f"{data_mode}_databases" / db_id / f"{db_id}.sqlite"
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    return path


def sqlite_connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def list_tables(dataset_name: str, data_mode: str, db_id: str) -> List[str]:
    path = sqlite_path(dataset_name, data_mode, db_id)
    with sqlite_connect_readonly(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]


def table_preview(dataset_name: str, data_mode: str, db_id: str, table: str, limit: int = 10) -> Dict[str, Any]:
    path = sqlite_path(dataset_name, data_mode, db_id)
    with sqlite_connect_readonly(path) as conn:
        column_rows = conn.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34) * 2)}")').fetchall()
        data_rows = conn.execute(f'SELECT * FROM "{table.replace(chr(34), chr(34) * 2)}" LIMIT ?', (limit,)).fetchall()
    columns = [row[1] for row in column_rows]
    schema = [
        {
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        }
        for row in column_rows
    ]
    preview_rows = [list(row) for row in data_rows]
    return {
        "table": table,
        "schema": schema,
        "columns": columns,
        "rows": preview_rows,
    }


def execute_read_only_sql(dataset_name: str, data_mode: str, db_id: str, sql: str, limit: int = 20) -> Dict[str, Any]:
    if not READ_ONLY_SQL.match(sql or ""):
        raise ValueError("Only read-only SQL is allowed here: SELECT, WITH, PRAGMA, or EXPLAIN.")
    path = sqlite_path(dataset_name, data_mode, db_id)
    with sqlite_connect_readonly(path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(limit)
        columns = [item[0] for item in (cursor.description or [])]
    return {
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "limit": limit,
    }


class DemoSettingsStore:
    def __init__(self) -> None:
        default_engine = ""
        if os.getenv("OPENROUTER_API_KEY"):
            default_engine = os.getenv("OPENROUTER_MODEL", "")
        if not default_engine and os.getenv("OPENAI_API_KEY"):
            default_engine = os.getenv("OPENAI_MODEL", "")
        self._lock = threading.Lock()
        self._settings = {
            "default_engine": default_engine or "gpt-4o-mini",
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "openai_api_url": os.getenv("OPENAI_API_URL", ""),
            "openrouter_api_url": os.getenv("OPENROUTER_API_URL", ""),
            "openrouter_site_url": os.getenv("OPENROUTER_SITE_URL", ""),
            "openrouter_app_name": os.getenv("OPENROUTER_APP_NAME", "OpenSearch-SQL"),
        }

    def snapshot(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._settings)

    def public(self) -> Dict[str, Any]:
        current = self.snapshot()
        return {
            "default_engine": current["default_engine"],
            "has_openai_api_key": bool(current["openai_api_key"]),
            "has_openrouter_api_key": bool(current["openrouter_api_key"]),
            "openai_api_url": current["openai_api_url"],
            "openrouter_api_url": current["openrouter_api_url"],
            "openrouter_site_url": current["openrouter_site_url"],
            "openrouter_app_name": current["openrouter_app_name"],
        }

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if payload.get("default_engine"):
                self._settings["default_engine"] = str(payload["default_engine"]).strip()
            if payload.get("openai_api_key"):
                self._settings["openai_api_key"] = str(payload["openai_api_key"]).strip()
            if payload.get("openrouter_api_key"):
                self._settings["openrouter_api_key"] = str(payload["openrouter_api_key"]).strip()
            if payload.get("openai_api_url"):
                self._settings["openai_api_url"] = str(payload["openai_api_url"]).strip()
            if payload.get("openrouter_api_url"):
                self._settings["openrouter_api_url"] = str(payload["openrouter_api_url"]).strip()
            if payload.get("openrouter_site_url"):
                self._settings["openrouter_site_url"] = str(payload["openrouter_site_url"]).strip()
            if payload.get("openrouter_app_name"):
                self._settings["openrouter_app_name"] = str(payload["openrouter_app_name"]).strip()
            if payload.get("clear_openai_api_key"):
                self._settings["openai_api_key"] = ""
            if payload.get("clear_openrouter_api_key"):
                self._settings["openrouter_api_key"] = ""
        return self.public()

    def apply_environment(self) -> Dict[str, str]:
        current = self.snapshot()
        env_mapping = {
            "OPENAI_API_KEY": current["openai_api_key"],
            "OPENROUTER_API_KEY": current["openrouter_api_key"],
            "OPENAI_API_URL": current["openai_api_url"],
            "OPENROUTER_API_URL": current["openrouter_api_url"],
            "OPENROUTER_SITE_URL": current["openrouter_site_url"],
            "OPENROUTER_APP_NAME": current["openrouter_app_name"],
        }
        for env_name, value in env_mapping.items():
            if value:
                os.environ[env_name] = value
            else:
                os.environ.pop(env_name, None)
        if current["default_engine"]:
            if is_openrouter_model(current["default_engine"]):
                os.environ["OPENROUTER_MODEL"] = current["default_engine"]
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = current["default_engine"]
                os.environ.pop("OPENROUTER_MODEL", None)
        return current


SETTINGS = DemoSettingsStore()


def preferred_engine() -> str:
    current = SETTINGS.snapshot()
    return current.get("default_engine") or "gpt-4o-mini"


def build_pipeline_setup(payload: Dict[str, Any]) -> Dict[str, Any]:
    dataset_name = payload["dataset"]
    engine = (payload.get("engine") or preferred_engine()).strip()
    bert_model = (payload.get("bert_model") or "hashing-fallback").strip()
    n_candidates = max(1, int(payload.get("n_candidates", 3)))
    skip_align = bool(payload.get("skip_align", False))
    disable_query_order = bool(payload.get("disable_query_order", True))
    align_methods = "style_align" if "MultiSpider" in dataset_name else "style_align+function_align+agent_align"

    return {
        "generate_db_schema": {
            "engine": engine,
            "bert_model": bert_model,
            "device": "cpu",
        },
        "extract_col_value": {
            "engine": engine,
            "temperature": 0.0,
        },
        "extract_query_noun": {
            "engine": engine,
            "temperature": 0.0,
        },
        "column_retrieve_and_other_info": {
            "engine": engine,
            "bert_model": bert_model,
            "device": "cpu",
            "temperature": 0.3,
            "top_k": 10,
            "disable_query_order": disable_query_order,
        },
        "candidate_generate": {
            "engine": engine,
            "temperature": 0.7,
            "n": n_candidates,
            "return_question": "True",
            "single": "True" if n_candidates == 1 else "False",
        },
        "align_correct": {
            "engine": engine,
            "n": n_candidates,
            "bert_model": bert_model,
            "device": "cpu",
            "align_methods": align_methods,
            "skip_align": skip_align,
        },
        "vote": {},
        "evaluation": {},
    }


def resolve_pipeline_nodes(payload: Dict[str, Any], has_gold_sql: bool) -> List[str]:
    preset_name = payload.get("pipeline_preset", "full")
    preset = PIPELINE_PRESETS.get(preset_name, PIPELINE_PRESETS["full"])
    nodes = list(preset["nodes"])
    if not has_gold_sql and "evaluation" in nodes:
        nodes.remove("evaluation")
    return nodes


def ensure_run_directory(dataset_name: str, run_id: str) -> Path:
    run_dir = RESULTS_ROOT / dataset_name / f"{now_label()}-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def parse_log_file(log_file: Path) -> Dict[str, Dict[str, List[str]]]:
    parsed: Dict[str, Dict[str, List[str]]] = {}
    if not log_file.exists():
        return parsed

    current_step: Optional[str] = None
    current_role: Optional[str] = None
    buffer: List[str] = []

    def flush() -> None:
        nonlocal buffer, current_step, current_role
        if not current_step or not current_role:
            buffer = []
            return
        parsed.setdefault(current_step, {"human": [], "ai": []})
        text = "\n".join(buffer).strip()
        if text:
            parsed[current_step][current_role].append(text)
        buffer = []

    for line in log_file.read_text(encoding="utf-8").splitlines():
        match = LOG_HEADER.match(line.strip())
        if match:
            flush()
            role = "human" if match.group(1) == "Human" else "ai"
            current_step = match.group(2).strip()
            current_role = role
        else:
            buffer.append(line)
    flush()
    return parsed


def select_candidate_sql(sql_value: Any) -> Optional[str]:
    if isinstance(sql_value, str):
        return sql_value
    if isinstance(sql_value, list) and sql_value:
        return sql_value[0]
    return None


def step_highlight(node_type: str, result: Dict[str, Any]) -> str:
    if result.get("status") == "error":
        return result.get("error", "Lỗi không xác định")
    if node_type == "generate_db_schema":
        return f"so truong schema: {len(result.get('db_col_dic', {}))}"
    if node_type == "extract_col_value":
        return "da tao nhap cot va gia tri"
    if node_type == "extract_query_noun":
        return f"cot: {len(result.get('col', []))}, gia tri: {len(result.get('values', []))}"
    if node_type == "column_retrieve_and_other_info":
        return f"gia tri truy hoi: {len(result.get('L_values', []))}"
    if node_type == "candidate_generate":
        sql = select_candidate_sql(result.get("SQL"))
        return sql[:120] if sql else "khong co SQL ung vien"
    if node_type == "align_correct":
        return f"ung vien bo phieu: {len(result.get('vote', []))}"
    if node_type == "vote":
        return result.get("SQL", "--")[:120]
    if node_type == "evaluation":
        vote_eval = result.get("vote", {})
        if vote_eval:
            return f"exec_res={vote_eval.get('exec_res', '--')}, exec_err={vote_eval.get('exec_err', '--')}"
        return "da danh gia xong"
    return "hoan thanh"


def final_summary(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_node = {step["node_type"]: step for step in history}
    candidate_sql = select_candidate_sql(by_node.get("candidate_generate", {}).get("SQL"))
    vote_sql = by_node.get("vote", {}).get("SQL")
    evaluation_step = by_node.get("evaluation", {})
    return {
        "last_node": history[-1]["node_type"] if history else None,
        "candidate_sql": candidate_sql,
        "vote_sql": vote_sql,
        "evaluation": evaluation_step,
        "completed_nodes": [step["node_type"] for step in history],
    }


def anchor_sample_for_db(dataset_name: str, data_mode: str, db_id: str) -> Dict[str, Any]:
    rows = load_dataset_rows(dataset_name, data_mode)
    for row in rows:
        if row.get("db_id") == db_id:
            return row
    if rows:
        return rows[0]
    raise ValueError(f"No rows were found in {dataset_name}/{data_mode}.")


def task_payload_from_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    run_mode = payload.get("run_mode", "sample")
    selected_db_id = payload.get("db_id", "")
    if run_mode == "sample" and payload.get("question_id") not in {None, ""}:
        sample = load_sample(payload["dataset"], payload["data_mode"], int(payload["question_id"]))
    elif payload.get("question_id") not in {None, ""}:
        sample = load_sample(payload["dataset"], payload["data_mode"], int(payload["question_id"]))
    else:
        sample = anchor_sample_for_db(payload["dataset"], payload["data_mode"], selected_db_id)

    raw_question = (payload.get("question") or sample.get("raw_question") or sample.get("question") or "").strip()
    if not raw_question:
        raise ValueError("question is required.")
    evidence = payload.get("evidence", sample.get("evidence", ""))
    gold_sql = payload.get("gold_sql", sample.get("SQL", ""))
    db_id = payload.get("db_id") or sample.get("db_id")
    if not db_id:
        raise ValueError("db_id is required.")
    return {
        "question_id": int(sample.get("question_id", 0)),
        "db_id": db_id,
        "question": raw_question,
        "raw_question": raw_question,
        "evidence": evidence,
        "SQL": gold_sql,
    }


class DemoRunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._runs: Dict[str, Dict[str, Any]] = {}

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._runs.values())
        items.sort(key=lambda item: item["created_at"], reverse=True)
        shallow: List[Dict[str, Any]] = []
        for item in items:
            shallow.append(
                {
                    "id": item["id"],
                    "status": item["status"],
                    "dataset": item["request"].get("dataset"),
                    "data_mode": item["request"].get("data_mode"),
                    "question_id": item["request"].get("question_id"),
                    "db_id": item["request"].get("db_id"),
                    "run_mode": item["request"].get("run_mode", "sample"),
                    "created_at": item["created_at"],
                    "started_at": item.get("started_at"),
                    "finished_at": item.get("finished_at"),
                    "final": item.get("final"),
                    "error": item.get("error"),
                }
            )
        return shallow

    def get_run(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            return json.loads(json.dumps(make_serial(self._runs[run_id]), ensure_ascii=False))

    def has_active_run(self) -> bool:
        with self._lock:
            return any(item["status"] in {"queued", "running"} for item in self._runs.values())

    def start_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_mode = payload.get("run_mode", "sample")
        for field in ["dataset", "data_mode"]:
            if payload.get(field) in {None, ""}:
                raise ValueError(f"Missing required field: {field}")
        if run_mode == "sample" and payload.get("question_id") in {None, ""}:
            raise ValueError("Missing required field: question_id")
        if run_mode == "custom":
            if payload.get("db_id") in {None, ""}:
                raise ValueError("Missing required field: db_id")
            if not str(payload.get("question", "")).strip():
                raise ValueError("Missing required field: question")

        with self._lock:
            if any(item["status"] in {"queued", "running"} for item in self._runs.values()):
                raise RuntimeError("Only one live pipeline run is allowed at a time in this demo UI.")

            run_id = uuid.uuid4().hex[:10]
            record = {
                "id": run_id,
                "status": "queued",
                "created_at": now_ts(),
                "request": payload,
                "trace": [],
                "final": None,
                "error": None,
                "traceback": None,
                "result_directory": None,
                "artifact_file": None,
                "log_file": None,
            }
            self._runs[run_id] = record

        thread = threading.Thread(target=self._execute_run, args=(run_id,), daemon=True)
        thread.start()
        return self.get_run(run_id)

    def _update_run(self, run_id: str, **updates: Any) -> None:
        with self._lock:
            self._runs[run_id].update(updates)

    def _append_trace(self, run_id: str, step_entry: Dict[str, Any]) -> None:
        with self._lock:
            self._runs[run_id]["trace"].append(step_entry)

    def _execute_run(self, run_id: str) -> None:
        with self._run_lock:
            with self._lock:
                payload = dict(self._runs[run_id]["request"])
                self._runs[run_id]["status"] = "running"
                self._runs[run_id]["started_at"] = now_ts()

            try:
                task_data = task_payload_from_request(payload)
                has_gold_sql = bool(task_data.get("SQL"))
                pipeline_nodes = resolve_pipeline_nodes(payload, has_gold_sql)
                pipeline_setup = build_pipeline_setup(payload)
                dataset_root = dataset_root_by_name(payload["dataset"])
                runtime_settings = SETTINGS.apply_environment()

                run_dir = ensure_run_directory(payload["dataset"], run_id)
                artifact_file = run_dir / "request.json"
                artifact_file.write_text(
                    json.dumps(
                        {
                            "request": payload,
                            "dataset_root": str(dataset_root),
                            "task": task_data,
                            "pipeline_nodes": pipeline_nodes,
                            "pipeline_setup": pipeline_setup,
                            "runtime_settings": SETTINGS.public(),
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                self._update_run(
                    run_id,
                    result_directory=str(run_dir),
                    artifact_file=str(artifact_file),
                    log_file=str(run_dir / "logs" / f"{task_data['question_id']}_{task_data['db_id']}.log"),
                    runtime_settings=SETTINGS.public(),
                )

                task = Task(task_data)
                logger = Logger(db_id=task.db_id, question_id=task.question_id, result_directory=str(run_dir))
                logger._set_log_level(payload.get("log_level", "warning"))
                DatabaseManager(db_mode=payload["data_mode"], db_root_path=str(dataset_root), db_id=task.db_id)
                PipelineManager(pipeline_setup)

                state = {"keys": {"task": task, "execution_history": []}}
                for index, node_name in enumerate(pipeline_nodes, start=1):
                    before_history = make_serial(state["keys"]["execution_history"])
                    step_start = now_ts()
                    NODE_FUNCTIONS[node_name](state)
                    step_end = now_ts()
                    history = state["keys"]["execution_history"]
                    if not history:
                        raise RuntimeError(f"Node '{node_name}' did not append to execution history.")
                    current_output = make_serial(history[-1])
                    log_file = Path(self.get_run(run_id)["log_file"])
                    logs = parse_log_file(log_file).get(node_name, {"human": [], "ai": []})
                    trace_entry = {
                        "index": index,
                        "node_type": node_name,
                        "title": NODE_META[node_name]["title"],
                        "description": NODE_META[node_name]["description"],
                        "status": current_output.get("status", "unknown"),
                        "duration_ms": int((step_end - step_start) * 1000),
                        "highlight": step_highlight(node_name, current_output),
                        "input": {
                            "task": make_serial(task_data),
                            "config": make_serial(pipeline_setup.get(node_name, {})),
                            "history_before": before_history,
                        },
                        "output": current_output,
                        "llm_log": logs,
                    }
                    self._append_trace(run_id, trace_entry)
                    if current_output.get("status") == "error":
                        raise RuntimeError(current_output.get("error", f"Node '{node_name}' failed."))

                final = final_summary(make_serial(state["keys"]["execution_history"]))
                self._update_run(
                    run_id,
                    status="completed",
                    finished_at=now_ts(),
                    final=final,
                )
            except Exception as exc:
                self._update_run(
                    run_id,
                    status="failed",
                    finished_at=now_ts(),
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )


RUNS = DemoRunStore()


class DemoRequestHandler(BaseHTTPRequestHandler):
    server_version = "OpenSearchSQLDemoUI/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                html_response(self, HTML_PATH.read_text(encoding="utf-8"))
                return

            if path == "/api/bootstrap":
                json_response(
                    self,
                    {
                        "datasets": catalog(),
                        "nodes": [
                            {"name": name, **NODE_META[name]}
                            for name in NODE_ORDER
                        ],
                        "pipeline_presets": PIPELINE_PRESETS,
                        "default_config": {
                            "run_mode": "sample",
                            "engine": preferred_engine(),
                            "bert_model": "hashing-fallback",
                            "n_candidates": 3,
                            "skip_align": False,
                            "disable_query_order": True,
                            "pipeline_preset": "full",
                            "view_mode": "trace",
                        },
                        "settings": SETTINGS.public(),
                        "runs": RUNS.list_runs(),
                    },
                )
                return

            if path == "/api/runs":
                json_response(self, {"runs": RUNS.list_runs()})
                return

            if path.startswith("/api/runs/"):
                run_id = path.split("/")[-1]
                json_response(self, RUNS.get_run(run_id))
                return

            if path.startswith("/api/datasets/"):
                parts = [part for part in path.split("/") if part]
                if len(parts) < 3:
                    raise ValueError("Dataset route is incomplete.")
                dataset_name = parts[2]
                action = parts[3] if len(parts) > 3 else ""
                data_mode = query.get("mode", ["dev"])[0]

                if action == "samples":
                    limit = int(query.get("limit", ["80"])[0])
                    db_id = query.get("db_id", [""])[0]
                    search = query.get("q", [""])[0]
                    json_response(
                        self,
                        {
                            "items": list_samples(dataset_name, data_mode, query=search, db_id=db_id, limit=limit),
                            "db_ids": list_db_ids(dataset_name, data_mode),
                        },
                    )
                    return

                if action == "sample":
                    question_id = int(parts[4])
                    json_response(self, sample_brief(load_sample(dataset_name, data_mode, question_id)))
                    return

                if action == "dbs":
                    json_response(self, {"items": list_db_ids(dataset_name, data_mode)})
                    return

                if action == "tables":
                    db_id = query.get("db_id", [""])[0]
                    json_response(self, {"items": list_tables(dataset_name, data_mode, db_id)})
                    return

                if action == "table-preview":
                    db_id = query.get("db_id", [""])[0]
                    table = query.get("table", [""])[0]
                    limit = int(query.get("limit", ["10"])[0])
                    json_response(self, table_preview(dataset_name, data_mode, db_id, table, limit=limit))
                    return

            error_response(self, f"Unknown route: {path}", HTTPStatus.NOT_FOUND)
        except FileNotFoundError as exc:
            error_response(self, str(exc), HTTPStatus.NOT_FOUND)
        except KeyError as exc:
            error_response(self, str(exc), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            error_response(self, f"{type(exc).__name__}: {exc}", HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/sql-query":
                payload = read_json_body(self)
                limit = int(payload.get("limit", 20))
                result = execute_read_only_sql(
                    payload["dataset"],
                    payload["data_mode"],
                    payload["db_id"],
                    payload["sql"],
                    limit=limit,
                )
                json_response(self, result)
                return

            if path == "/api/runs":
                payload = read_json_body(self)
                record = RUNS.start_run(payload)
                json_response(self, record, status=HTTPStatus.ACCEPTED)
                return

            if path == "/api/settings":
                payload = read_json_body(self)
                updated = SETTINGS.update(payload)
                json_response(self, {"settings": updated})
                return

            error_response(self, f"Unknown route: {path}", HTTPStatus.NOT_FOUND)
        except RuntimeError as exc:
            error_response(self, str(exc), HTTPStatus.CONFLICT)
        except Exception as exc:
            error_response(self, f"{type(exc).__name__}: {exc}", HTTPStatus.BAD_REQUEST)


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSearch-SQL demo UI server.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8765")))
    args = parser.parse_args()

    if not HTML_PATH.exists():
        raise FileNotFoundError(f"Missing UI template: {HTML_PATH}")

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), DemoRequestHandler)
    print(f"OpenSearch-SQL demo UI listening at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
