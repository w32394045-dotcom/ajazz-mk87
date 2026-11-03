Name:           mk87
# 显式版本号；build-rpm.sh 传 --define version_override 时以它为准（避免改了 __version__ 而 spec 忘记同步）
Version:        %{?version_override}%{!?version_override:0.1.6}
Release:        1%{?dist}
Summary:        AJAZZ MK87 keyboard configuration tool (unofficial)

License:        MIT
URL:            https://github.com/w32394045-dotcom/ajazz-mk87
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64

Requires:       glibc, libusb1, systemd-udev, mesa-libGL, libxkbcommon-x11, nss, alsa-lib, pulseaudio-libs, xcb-util-cursor

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
