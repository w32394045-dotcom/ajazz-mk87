Name:           mk87
# PyInstaller 产物没有需要拆分的 ELF 调试信息，不需要生成 -debuginfo 子包
%global debug_package %{nil}
# 显式版本号；build-rpm.sh 传 --define version_override 时以它为准（避免改了 __version__ 而 spec 忘记同步）
Version:        %{?version_override}%{!?version_override:0.1.8.2}
Release:        1%{?dist}
Summary:        AJAZZ MK87 keyboard configuration tool (unofficial)

License:        MIT
URL:            https://github.com/w32394045-dotcom/ajazz-mk87
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64

# 2026-11-05：PyQt6/Qt 6.12 需要一批系统库；虽然这些库已随 PyInstaller 打进
# /opt/mk87（自包含），仍需显式声明 Requires，让 dnf 安装时一次补齐（尤其
# pcre2(16bit)/double-conversion/libb2/md4c 在精简系统上可能缺失）。
Requires:       glibc, libusb1, systemd-udev, mesa-libGL, mesa-libEGL, libxkbcommon, libxkbcommon-x11, nss, nspr, alsa-lib, pulseaudio-libs, xcb-util-cursor, glib2, pcre2, double-conversion, libb2, md4c, dbus-libs, fontconfig, freetype, harfbuzz, graphite2, fribidi, cairo, pango, gdk-pixbuf2, gtk3, atk, at-spi2-atk, at-spi2-core, cups-libs, avahi-libs, libepoxy, wayland-libs-client, wayland-libs-cursor, wayland-libs-egl, lcms2, libthai, libdatrie, libXcomposite, libXdamage, libXfixes, libXi, libXinerama, libXres, libXcursor, libXtst, xcb-util-wm, xcb-util-keysyms, xcb-util, libpng, libjpeg-turbo, libwebp, opus, libvpx, snappy, expat, libzstd, readline, ncurses-libs, libatomic

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
