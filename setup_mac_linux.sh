#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== WhisperFlow Local setup ==="
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10-3.12, then run this script again."
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9+ is required; Python 3.11/3.12 is recommended.")
PY

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
python smoke_test.py

echo
echo "Setup complete. Run ./run_mac_linux.sh"
