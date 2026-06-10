#!/bin/bash
# Создаёт venv для движка и устанавливает зависимости.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/engine/.venv"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/engine/requirements.txt"

echo "OK: venv готов — $VENV_DIR"
