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

# Depends 说明（2026-11-05）：PyQt6/Qt 6.12 依赖一批 Ubuntu 桌面默认不一定安装的系统库
# （libpcre2-16、libdouble-conversion、libb2、libmd4c 等）。这些库现在已经随 PyInstaller
# 一起打进 /opt/mk87（自包含），但这里仍显式声明，保证：
#   1) `sudo apt install ./mk87_*.deb` 时由包管理器一次装齐，不依赖用户手动补；
#   2) 即使某些库在打包机上也缺、没被 PyInstaller 收进去，安装时也能补齐。
# t64 是 Ubuntu 24.04 起的时间兼容重命名，用 `xxx-t64 | xxx` 兼容 22.04/24.04。
cat > "$PKG/DEBIAN/control" <<EOF
Package: mk87
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: mk87 studio <noreply@localhost>
Installed-Size: $(du -sk "$PKG/opt" | cut -f1)
Depends: libc6, libudev1, libusb-1.0-0, libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libnss3, libnspr4, libasound2t64 | libasound2 (>= 1.0.16), libpulse0, libxcb-cursor0, libpcre2-16-0, libdouble-conversion3, libb2-1, libmd4c0, libglib2.0-0t64 | libglib2.0-0, libdbus-1-3, libfontconfig1, libfreetype6, libharfbuzz0b, libgtk-3-0t64 | libgtk-3-0, libcairo2, libpango-1.0-0, libgdk-pixbuf-2.0-0t64 | libgdk-pixbuf-2.0-0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxres1, libxcomposite1, libxdamage1, libxfixes3, libxi6, libxinerama1, libxcursor1, libxtst6, libwayland-client0, libwayland-cursor0, libwayland-egl1, libwayland-server0
Recommends: pulseaudio-utils | pipewire-bin, libatk1.0-0t64 | libatk1.0-0, libatk-bridge2.0-0t64 | libatk-bridge2.0-0, libatspi2.0-0t64 | libatspi2.0-0, libcups2t64 | libcups2, libavahi-client3, libavahi-common3, libepoxy0, liblcms2-2, libgraphite2-3, libfribidi0, libthai0, libdatrie1, libexpat1, libzstd1, libpng16-16t64 | libpng16-16, libjpeg-turbo8t64 | libjpeg-turbo8, libwebp7t64 | libwebp7, libopus0t64 | libopus0, libsnappy1v5t64 | libsnappy1v5, libvpx9 | libvpx8 | libvpx7, libatomic1, libtinfo6, libreadline8t64 | libreadline8, libgnutls30t64 | libgnutls30, libssl3t64 | libssl3, libpangocairo-1.0-0
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
