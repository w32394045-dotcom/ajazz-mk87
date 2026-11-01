#!/usr/bin/env bash
# Linux 打包脚本（在 driver/ 目录下运行）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r packaging/requirements.txt -q
.venv/bin/pip install pyinstaller -q
.venv/bin/pyinstaller packaging/mk87.spec --noconfirm --clean

echo
echo "打包完成: $(pwd)/dist/MK87Config/"
echo "可选：把 dist/MK87Config/MK87Config 复制到 /usr/local/bin/"
