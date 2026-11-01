#!/usr/bin/env bash
# 构建 RPM 安装包（.rpm）
# 前置：rpm-build 工具链（Fedora/RHEL/openSUSE: sudo dnf install rpm-build）
# 用法： packaging/linux/build-rpm.sh [版本号]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$(cd "$HERE/../.." && pwd)"
cd "$DRIVER"

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' mk87lib/__init__.py | head -1)}"
DIST="$DRIVER/dist/MK87Config"
OUT="$DRIVER/dist-packages"
TOPDIR="$DRIVER/build/rpmbuild"

if [ ! -d "$DIST" ]; then
  echo "错误：找不到 $DIST，请先运行 make-package.sh（会调用 PyInstaller）" >&2
  exit 1
fi

rm -rf "$TOPDIR"
mkdir -p "$TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

STAGE="$TOPDIR/stage/mk87-$VERSION"
mkdir -p "$STAGE"
cp -a "$DIST/." "$STAGE/MK87Config/"
rmdir "$STAGE/MK87Config"/../MK87Config 2>/dev/null || true
cp -a "$HERE/mk87-launcher" "$STAGE/"
cp -a "$HERE/mk87.desktop" "$STAGE/"
cp -a "$HERE/mk87.spec" "$STAGE/"
cp -a "$DRIVER/assets/mk87.svg" "$STAGE/"
cp -a "$DRIVER/packaging/udev/99-ajazz-mk87.rules" "$STAGE/"
tar -C "$TOPDIR/stage" -czf "$TOPDIR/SOURCES/mk87-$VERSION.tar.gz" "mk87-$VERSION"
cp "$HERE/mk87.spec" "$TOPDIR/SPECS/mk87.spec"

rpmbuild -bb \
  --define "_topdir $TOPDIR" \
  --define "version_override $VERSION" \
  "$TOPDIR/SPECS/mk87.spec"

mkdir -p "$OUT"
find "$TOPDIR/RPMS" -name '*.rpm' -exec cp -v {} "$OUT/" \;
echo "RPM 已输出到: $OUT"
