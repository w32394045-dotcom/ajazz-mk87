#!/usr/bin/env bash
# Linux 一键安装权限规则 + 依赖（需 sudo 执行 udev 部分）
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1. 安装 Python 依赖（当前用户）=="
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r packaging/requirements.txt

echo "== 2. 安装 udev 规则（需要 sudo）=="
sudo cp packaging/udev/99-ajazz-mk87.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "== 3. 完成 =="
echo "启动：./.venv/bin/python run.py"
echo "如果按键测试读不到 /dev/input/event*，请执行： sudo usermod -aG input \$USER  然后注销重登"
