#!/bin/sh
# Ek baar: court websites wale scraper (scripts/fetch_live.py) ke liye Python 3.12 + bharat-courts.
#   sh scripts/setup_live.sh
# bharat-courts ko Python 3.11+ chahiye, Mac ka python3 3.9 hai — isliye uv se alag .venv-live.
set -u
cd "$(dirname "$0")/.." || exit 1
[ -d vendor/product/bharat-courts ] || { echo "vendor/product/bharat-courts nahi mila — pehle: python3 scripts/vendor_sync.py"; exit 1; }
{ [ -x .venv-tools/bin/uv ] || { python3 -m venv .venv-tools && .venv-tools/bin/python -m pip install -q --upgrade pip uv; }; } \
  && .venv-tools/bin/uv venv -q --allow-existing --python 3.12 .venv-live \
  && .venv-tools/bin/uv pip install -q --python .venv-live/bin/python "./vendor/product/bharat-courts[ocr]" pypdfium2 \
  || { echo "Install nahi hua — upar ka error bhejo."; exit 1; }
.venv-live/bin/python -c "import bharat_courts, ddddocr; print('Setup poora: bharat-courts', bharat_courts.__version__)"
