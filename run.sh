#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================================"
echo "  QBASwing MyServer"
echo '  "Todo al alcance de tus manos en cuestión de segundos"'
echo "============================================================"

if command -v python3 &>/dev/null; then
    PY=python3
else
    PY=python
fi

VENV="$HOME/qbaswing-myserver-venv"

if [ ! -d "$VENV" ]; then
    echo "Creando entorno virtual..."
    "$PY" -m venv "$VENV"
fi

source "$VENV/bin/activate"

pip install -r requirements.txt --quiet

python app.py
