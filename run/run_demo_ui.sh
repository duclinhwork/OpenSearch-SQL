#!/usr/bin/env bash
set -euo pipefail

host="${HOST:-127.0.0.1}"
port="${PORT:-8765}"

python3 src/demo_ui.py --host "${host}" --port "${port}"
