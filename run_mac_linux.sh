#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Environment not installed yet. Starting setup first..."
  ./setup_mac_linux.sh
fi
source .venv/bin/activate
python webapp.py
