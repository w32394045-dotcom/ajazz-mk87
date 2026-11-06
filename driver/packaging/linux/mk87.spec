Name:           mk87
# PyInstaller 产物没有需要拆分的 ELF 调试信息，不需要生成 -debuginfo 子包
%global debug_package %{nil}
# 显式版本号；build-rpm.sh 传 --define version_override 时以它为准（避免改了 __version__ 而 spec 忘记同步）
Version:        %{?version_override}%{!?version_override:0.1.8.4}
Release:        1%{?dist}
Summary:        AJAZZ MK87 keyboard configuration tool (unofficial)

License:        MIT
URL:            https://github.com/w32394045-dotcom/ajazz-mk87
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64

# 2026-11-05：PyInstaller 会把 wheel 自带的改名库（auditwheel 的 libxxx-<hash>.so）打进
# /opt/mk87，rpmbuild 的自动依赖生成器会把它们当成未满足的 Requires，导致 dnf 安装失败
# （nothing provides libattr-4f2a9577.so.1.1.0）。PyInstaller 产物必须关闭 AutoReqProv，
# 由下面显式声明运行时依赖。
AutoReqProv:    no

# 2026-11-06（v0.1.8.3）打包策略变更：**宿主系统库不再随包**（见 packaging/libfilter.py）。
# 因此必须显式 Requires 发行版提供的运行库，否则装完启动会缺库（Qt/WebEngine 需要
# 系统 Mesa/GLib/X11/Wayland/NSS 等）。这些名字在 Fedora 39–43 / RHEL9 都存在；
# 不确定的长尾包放 Recommends（弱依赖，名字不存在也不阻塞安装）。
# 注意：rpm 的 tag 行不支持 `\` 续行，多写几行 `Requires:`（逻辑上是 AND）。
Requires:       glibc, libgcc, libstdc++, zlib, bzip2-libs, xz-libs, libzstd, expat, libffi
Requires:       sqlite-libs, openssl-libs, readline, ncurses-libs, libuuid, libblkid, libmount
Requires:       libcap, libselinux, systemd-libs, systemd-udev, libusb1
Requires:       pcre2, glib2, dbus-libs, fontconfig, freetype, harfbuzz, libpng, libjpeg-turbo
Requires:       libwebp, gtk3, gdk-pixbuf2, atk, at-spi2-atk, at-spi2-core, cairo, pango
Requires:       libepoxy, lcms2, fribidi, graphite2, libthai, libdatrie, pixman
Requires:       mesa-libGL, mesa-libEGL, mesa-libgbm, libglvnd, libdrm
Requires:       libX11, libxcb, xcb-util, xcb-util-cursor, xcb-util-image, xcb-util-keysyms
Requires:       xcb-util-renderutil, xcb-util-wm, libXres, libXau, libXdmcp
Requires:       libXext, libXrender, libXi, libXcursor, libXrandr, libXfixes, libXinerama
Requires:       libXtst, libXcomposite, libXdamage, libxkbcommon, libxkbcommon-x11, libxkbfile
Requires:       libwayland-client, libwayland-cursor, libwayland-server
Requires:       nss, nss-softokn, nspr, alsa-lib, pulseaudio-libs, cups-libs, avahi-libs
Requires:       gnutls, libgcrypt, libgpg-error, p11-kit, libtasn1, libidn2, nettle, gmp
Requires:       krb5-libs, libcom_err, keyutils-libs
Recommends:     pcre2-utf16, brotli, double-conversion, libb2, md4c, libatomic
Recommends:     libglvnd-egl, libglvnd-glx, mesa-dri-drivers, pipewire-libs, opus, libvpx
Recommends:     snappy, xdg-utils, libnotify, libbsd, libmd, lz4-libs, cairo-gobject

%description
MK87 Studio is an unofficial cross-platform configuration tool for the
AJAZZ MK87 mechanical keyboard. It provides lighting, per-key RGB, TFT
animation upload, macro editing, key remapping, music-reactive lighting,
wireless settings, key testing and full backup/restore.

This package installs the desktop app and the udev rules required to
access the keyboard HID interfaces without root.

%prep
%setup -q

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/opt/mk87
cp -a MK87Config/. %{buildroot}/opt/mk87/
chmod +x %{buildroot}/opt/mk87/MK87Config

install -Dm755 mk87-launcher %{buildroot}%{_bindir}/mk87
install -Dm644 mk87.desktop %{buildroot}%{_datadir}/applications/mk87.desktop
install -Dm644 mk87.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/mk87.svg
install -Dm644 99-ajazz-mk87.rules %{buildroot}/usr/lib/udev/rules.d/99-ajazz-mk87.rules

%post
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || :
  udevadm trigger || :
fi

%postun
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || :
  udevadm trigger || :
fi

%files
/opt/mk87
%{_bindir}/mk87
%{_datadir}/applications/mk87.desktop
%{_datadir}/icons/hicolor/scalable/apps/mk87.svg
/usr/lib/udev/rules.d/99-ajazz-mk87.rules

%changelog
* Sat Nov 01 2026 MK87 Studio <noreply@localhost> - 0.1.0-1
- Initial RPM package
