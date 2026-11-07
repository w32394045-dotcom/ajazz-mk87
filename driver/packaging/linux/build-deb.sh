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

# 打包策略卡口（v0.1.8.3）：宿主系统库不得随包，libpython 必须随包。
bash "$HERE/check-bundle.sh" "$DIST"

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

# ---------------------------------------------------------------------------
# Depends 说明（v0.1.8.3 起，2026-11-06）
#
# 打包策略：**Qt/WebEngine 与应用库随包；宿主系统库由发行版提供。**
# 所以这里必须把「打包体运行时真正需要的系统库」全部声明出来，否则用户装完启动
# 会缺库（v0.1.8.2 是把这些库打进包，结果在 Ubuntu 24.04 上顶掉系统 Mesa/GLib，
# 出现 EGL 不可用 + 段错误，见 packaging/libfilter.py 顶部说明）。
#
# 兼容性写法：
#   * `xxx-t64 | xxx`：Ubuntu 24.04 的 64 位 time_t 重命名，22.04/Debian 用旧名；
#   * 其它分支上不存在某个包时，apt 会自动选备选（Depends 的 a | b 语义）；
#   * 版本要求尽量宽松，不锁具体小版本，避免不同发行版版本号比较失败。
# ---------------------------------------------------------------------------
DEPENDS="libc6 (>= 2.35), libgcc-s1, libstdc++6, zlib1g, libbz2-1.0, liblzma5, libzstd1, \
 libexpat1, libffi8, libsqlite3-0, libssl3t64 | libssl3, libreadline8t64 | libreadline8, \
 libtinfo6, libuuid1t64 | libuuid1, libcap2t64 | libcap2, libselinux1t64 | libselinux1, \
 libblkid1t64 | libblkid1, libmount1t64 | libmount1, libsystemd0, \
 libpcre2-8-0, libpcre2-16-0, libdouble-conversion3, libb2-1, libmd4c0, \
 libglib2.0-0t64 | libglib2.0-0, libdbus-1-3, libudev1, libusb-1.0-0, \
 libfontconfig1, libfreetype6, libharfbuzz0b, libbrotli1, \
 libpng16-16t64 | libpng16-16, libjpeg-turbo8t64 | libjpeg-turbo8, libwebp7t64 | libwebp7, \
 libgtk-3-0t64 | libgtk-3-0, libgdk-pixbuf-2.0-0t64 | libgdk-pixbuf-2.0-0, \
 libatk1.0-0t64 | libatk1.0-0, libatk-bridge2.0-0t64 | libatk-bridge2.0-0, \
 libatspi2.0-0t64 | libatspi2.0-0, libcairo2, libcairo-gobject2, \
 libpango-1.0-0, libpangocairo-1.0-0, libpangoft2-1.0-0, \
 libepoxy0, liblcms2-2, libfribidi0, libgraphite2-3, libthai0, libdatrie1, libpixman-1-0, \
 libgl1, libegl1, libglx0, libopengl0, libglvnd0, libgbm1, libdrm2, \
 libx11-6, libx11-xcb1, libxcb1, libxau6, libxdmcp6, \
 libxcb-dri3-0, libxcb-glx0, libxcb-present0, libxcb-randr0, libxcb-render0, libxcb-shm0, \
 libxcb-sync1, libxcb-xfixes0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, \
 libxcb-image0, libxcb-render-util0, libxcb-xkb1, libxcb-cursor0, libxres1, \
 libxext6, libxrender1, libxi6, libxcursor1, libxrandr2, libxfixes3, libxinerama1, \
 libxtst6, libxcomposite1, libxdamage1, libxkbcommon0, libxkbcommon-x11-0, libxkbfile1, \
 libwayland-client0, libwayland-cursor0, libwayland-egl1, libwayland-server0, \
 libnss3, libnspr4, libasound2t64 | libasound2 (>= 1.0.16), libpulse0, \
 libcups2t64 | libcups2, libavahi-client3, libavahi-common3, \
 libgnutls30t64 | libgnutls30, libgcrypt20, libgpg-error0, libp11-kit0t64 | libp11-kit0, \
 libtasn1-6t64 | libtasn1-6, libidn2-0, libnettle8t64 | libnettle8, \
 libhogweed6t64 | libhogweed6, libgmp10, libbsd0, libmd0, liblz4-1, \
 libkrb5-3, libk5crypto3, libkrb5support0, \
 libcom-err2, libkeyutils1, libgssapi-krb5-2"

RECOMMENDS="libgl1-mesa-dri, pipewire-bin | pulseaudio-utils, fonts-dejavu-core, \
 xdg-utils, libnotify-bin, zenity, libcanberra-gtk3-module, \
 pkexec | policykit-1, gnome-shell-extension-appindicator"

cat > "$PKG/DEBIAN/control" <<EOF
Package: mk87
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: mk87 studio <noreply@localhost>
Installed-Size: $(du -sk "$PKG/opt" | cut -f1)
Depends: $DEPENDS
Recommends: $RECOMMENDS
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
