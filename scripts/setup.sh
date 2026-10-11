#!/bin/sh
# Ek baar: database ke liye zaroori Python libraries .venv mein install karo.
#   sh scripts/setup.sh
set -u
cd "$(dirname "$0")/.." || exit 1
python3 -m venv .venv || { echo "Python venv nahi bana — upar ka error bhejo."; exit 1; }
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt || { echo "Libraries install nahi huin — upar ka error bhejo."; exit 1; }
.venv/bin/python -c "import pyarrow, pypdfium2; print('Setup poora: pyarrow', pyarrow.__version__, '+ pypdfium2 ok')"
