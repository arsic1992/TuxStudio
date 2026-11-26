#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements.txt
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --console --name TuxStudio --hidden-import pyte TuxStudio.py
exe=dist/TuxStudio/TuxStudio
"$exe" --version
.build-venv/bin/python smoke.py "$exe"
printf '\nBuild ready: %s\n' "$PWD/$exe"
