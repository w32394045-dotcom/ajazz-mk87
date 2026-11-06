#!/usr/bin/env bash
# 校验 PyInstaller 产物符合「应用库随包、宿主系统库不随包」策略（v0.1.8.3）。
#
# 背景见 packaging/libfilter.py 与 packaging/mk87.spec 顶部注释：
# v0.1.8.2 及更早的 Linux 包把构建机 Ubuntu 22.04 的 glib/libstdc++/wayland/xcb/Mesa
# 打进 _internal，在 Ubuntu 24.04 上顶掉系统图形栈 → EGL 不可用 → QtWebEngine 段错误。
# 这里在打包阶段直接拦住回归：出现下列「宿主系统库」就失败。
#
# 用法： packaging/linux/check-bundle.sh [dist/MK87Config]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$(cd "$HERE/../.." && pwd)"
DIST="${1:-$DRIVER/dist/MK87Config}"
INTERNAL="$DIST/_internal"

if [ ! -d "$INTERNAL" ]; then
  echo "错误：找不到 $INTERNAL，请先运行 PyInstaller" >&2
  exit 1
fi

# 宿主系统库（发行版提供）：显卡栈、GLib/GTK、X11/Wayland、NSS/OpenSSL、编译期运行库等。
# 注意用**精确 soname**匹配，避免误伤 wheel 自带的改名库（如 Pillow 的 libjpeg-<hash>.so）。
FORBIDDEN=(
  'libstdc++.so*' 'libgcc_s.so*'
  'libglib-2.0.so*' 'libgio-2.0.so*' 'libgobject-2.0.so*' 'libgmodule-2.0.so*' 'libgthread-2.0.so*'
  'libgtk-3.so*' 'libgdk-3.so*' 'libgdk_pixbuf-2.0.so*' 'libatk-1.0.so*' 'libatk-bridge-2.0.so*' 'libatspi.so*'
  'libcairo.so*' 'libcairo-gobject.so*' 'libpango-1.0.so*' 'libpangocairo-1.0.so*' 'libpangoft2-1.0.so*'
  'libfontconfig.so*' 'libfreetype.so*' 'libharfbuzz.so*' 'libepoxy.so*' 'liblcms2.so*'
  'libX11.so*' 'libX11-xcb.so*' 'libXext.so*' 'libXrender.so*' 'libXi.so*' 'libXcursor.so*' 'libXrandr.so*'
  'libXfixes.so*' 'libXinerama.so*' 'libXtst.so*' 'libXcomposite.so*' 'libXdamage.so*' 'libXRes.so*'
  'libXau.so*' 'libXdmcp.so*' 'libbsd.so*' 'libmd.so*' 'liblz4.so*'
  'libxcb.so*' 'libxcb-*.so*' 'libxkbcommon.so*' 'libxkbfile.so*'
  'libwayland-client.so*' 'libwayland-cursor.so*' 'libwayland-egl.so*' 'libwayland-server.so*'
  'libdrm.so*' 'libgbm.so*' 'libEGL.so*' 'libGL.so*' 'libGLX.so*' 'libGLdispatch.so*' 'libOpenGL.so*'
  'libnss3.so' 'libnspr4.so' 'libnssutil3.so' 'libsmime3.so' 'libssl3.so' 'libfreebl3.so' 'libsoftokn3.so'
  'libdbus-1.so*' 'libasound.so*' 'libpulse.so*' 'libcups.so*' 'libavahi-client.so*' 'libavahi-common.so*'
  'libssl.so*' 'libcrypto.so*' 'libgnutls.so*' 'libgcrypt.so*' 'libgpg-error.so*'
  'libz.so*' 'libzstd.so*' 'liblzma.so*' 'libbz2.so*' 'libexpat.so*' 'libffi.so*' 'libsqlite3.so*'
  'libreadline.so*' 'libtinfo.so*' 'libuuid.so*' 'libcap.so*' 'libselinux.so*' 'libsystemd.so*'
  'libblkid.so*' 'libmount.so*' 'libpcre2-8.so*' 'libpcre2-16.so*' 'libpcre.so*'
  'libnettle.so*' 'libhogweed.so*' 'libgmp.so*' 'libp11-kit.so*' 'libtasn1.so*'
  'libidn2.so*' 'libunistring.so*' 'libkrb5.so*' 'libk5crypto.so*' 'libkrb5support.so*'
  'libcom_err.so*' 'libkeyutils.so*' 'libgssapi_krb5.so*'
)

fail=0
for pat in "${FORBIDDEN[@]}"; do
  # compgen -G 匹配不到返回非 0；用 nullglob 语义避免把字面量当文件
  for f in "$INTERNAL"/$pat; do
    [ -e "$f" ] || continue
    echo "错误：打包体里出现了宿主系统库 $(basename "$f")（应交给发行版提供）" >&2
    fail=1
  done
done

if [ "$fail" -ne 0 ]; then
  echo >&2
  echo "打包策略说明：应用库（Qt/WebEngine/wheel 自带的第三方库）随包，" >&2
  echo "宿主系统库（显卡栈/GLib/GTK/X11/Wayland/NSS/编译器运行库）由发行版提供。" >&2
  echo "规则实现：driver/packaging/libfilter.py（被 mk87.spec 调用）。" >&2
  exit 1
fi

# libpython 必须随包（冻结程序依赖它；目标机不一定有同版本 Python 共享库）
if ! ls "$INTERNAL"/libpython3*.so* >/dev/null 2>&1; then
  echo "错误：打包体缺少 libpython3*.so*（目标机没有同版本 Python 时无法启动）" >&2
  exit 1
fi

echo "OK：打包体符合策略（宿主系统库未随包，libpython 已随包）"
