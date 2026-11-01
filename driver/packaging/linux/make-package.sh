#!/usr/bin/env bash
# Linux 一键打包：PyInstaller → .deb + .rpm
# 用法（在任意目录）： packaging/linux/make-package.sh [--no-build]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$(cd "$HERE/../.." && pwd)"
cd "$DRIVER"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' mk87lib/__init__.py | head -1)"
OUT="$DRIVER/dist-packages"
mkdir -p "$OUT"

if [ ! -d "$DRIVER/dist/MK87Config" ] || [ "${1:-}" != "--no-build" ]; then
  echo "== 1/3 PyInstaller 打包 =="
  python3 -m PyInstaller packaging/mk87.spec --noconfirm --clean
else
  echo "== 1/3 跳过 PyInstaller（已有 dist/MK87Config）=="
fi

if command -v dpkg-deb >/dev/null 2>&1; then
  echo "== 2/3 构建 .deb =="
  bash "$HERE/build-deb.sh" "$VERSION"
else
  echo "== 2/3 跳过 .deb（未安装 dpkg-deb）=="
fi

if command -v rpmbuild >/dev/null 2>&1; then
  echo "== 3/3 构建 .rpm =="
  bash "$HERE/build-rpm.sh" "$VERSION"
else
  echo "== 3/3 跳过 .rpm（未安装 rpmbuild）=="
fi

echo
echo "输出目录：$OUT"
ls -lh "$OUT" 2>/dev/null || true
