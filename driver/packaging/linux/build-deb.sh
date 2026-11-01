#!/usr/bin/env bash
# 构建 Debian 安装包（.deb）
# 前置：已安装 pyinstaller 依赖并生成 dist/MK87Config（make-package.sh 会自动做）
# 用法： packaging/linux/build-deb.sh [版本号]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$(cd "$HERE/../.." && pwd)"
cd "$DRIVER"

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' mk87lib/__init__.py | head -1)}"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
DIST="$DRIVER/dist/MK87Config"
OUT="$DRIVER/dist-packages"
PKG="$OUT/mk87_${VERSION}_${ARCH}"

if [ ! -d "$DIST" ]; then
  echo "错误：找不到 $DIST，请先运行 make-package.sh（会调用 PyInstaller）" >&2
  exit 1
fi

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/mk87" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/lib/udev/rules.d"

cp -a "$DIST/." "$PKG/opt/mk87/"
chmod +x "$PKG/opt/mk87/MK87Config"

install -m 755 "$HERE/mk87-launcher" "$PKG/usr/bin/mk87"
install -m 644 "$HERE/mk87.desktop" "$PKG/usr/share/applications/mk87.desktop"
install -m 644 "$DRIVER/assets/mk87.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/mk87.svg"
install -m 644 "$DRIVER/packaging/udev/99-ajazz-mk87.rules" "$PKG/usr/lib/udev/rules.d/99-ajazz-mk87.rules"

cat > "$PKG/DEBIAN/control" <<EOF
Package: mk87
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: mk87 studio <noreply@localhost>
Installed-Size: $(du -sk "$PKG/opt" | cut -f1)
Depends: libc6, libudev1, libusb-1.0-0, libgl1, libegl1, libxkbcommon-x11-0, libnss3, libasound2, libpulse0, libxcb-cursor0
Recommends: pulseaudio-utils | pipewire-bin
Homepage: https://github.com/w32394045-dotcom/ajazz-mk87
Description: AJAZZ MK87 keyboard configuration tool (unofficial)
 MK87 Studio is an unofficial cross-platform configuration tool for the
 AJAZZ MK87 mechanical keyboard. It provides lighting, per-key RGB,
 TFT animation upload, macro editing, key remapping, music-reactive
 lighting, wireless settings, key testing and full backup/restore.
 .
 This package installs the desktop app and the udev rules required to
 access the keyboard HID interfaces without root.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || true
  udevadm trigger || true
fi
exit 0
EOF

cat > "$PKG/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || true
  udevadm trigger || true
fi
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "$PKG" "$OUT/mk87_${VERSION}_${ARCH}.deb"
echo "已生成: $OUT/mk87_${VERSION}_${ARCH}.deb"
