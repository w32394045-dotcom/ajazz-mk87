# 打包说明（成品软件）

本目录负责把 `driver/` 打成可安装/可分发的成品：

| 平台 | 产物 | 构建方式 |
|---|---|---|
| Windows | 便携版 `MK87Studio-<ver>-win64-portable.zip` | `packaging/windows/build-portable.ps1` |
| Windows | 安装包 `MK87Studio-<ver>-win64-setup.exe`（Inno Setup） | `packaging/windows/build-installer.ps1` |
| Linux (Debian/Ubuntu) | `mk87_<ver>_<arch>.deb` | `packaging/linux/build-deb.sh` |
| Linux (Fedora/RHEL/openSUSE) | `mk87-<ver>-1.<dist>.x86_64.rpm` | `packaging/linux/build-rpm.sh` |
| 两者一键 | 先 PyInstaller 再打两种包 | `packaging/linux/make-package.sh` |
| CI | 以上全部（GitHub Actions） | `.github/workflows/build.yml` |

## Windows

```powershell
cd driver
powershell -ExecutionPolicy Bypass -File packaging\windows\build-portable.ps1
# 安装包（需先装 Inno Setup 6：winget install JRSoftware.InnoSetup）
powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1
```

产物：
- `dist/MK87Config/` —— PyInstaller onedir（`MK87Config.exe` + `_internal/`，**无控制台窗口**，入口是原生外壳 `shell.py`）
- `dist-packages/*.zip` —— 免安装便携版（解压后双击 exe：独立窗口 + 系统托盘）
- `dist-installer/*setup.exe` —— 安装包（开始菜单/桌面快捷方式/卸载项）

> 原生窗口依赖：Windows 用系统 **WebView2**（Win10/11 自带）；Linux 用 **Qt 后端**（PyInstaller 打包 PySide6/QtWebEngine，自包含）。

## Linux

```bash
cd driver
# Debian/Ubuntu 需要：dpkg-dev；Fedora/RHEL/openSUSE 需要：rpm-build
bash packaging/linux/make-package.sh
# 只打某一种：
bash packaging/linux/build-deb.sh
bash packaging/linux/build-rpm.sh
```

产物在 `dist-packages/`。

### 包内容

```
/opt/mk87/                        PyInstaller 程序（含 web/、data/、docs/）
/usr/bin/mk87                     启动器（exec /opt/mk87/MK87Config "$@"）
/usr/share/applications/mk87.desktop
/usr/share/icons/hicolor/scalable/apps/mk87.svg
/usr/lib/udev/rules.d/99-ajazz-mk87.rules   ← 免 root 访问键盘 HID
```

安装/卸载（deb）：
```bash
sudo dpkg -i dist-packages/mk87_*_amd64.deb
sudo apt-get -f install          # 若缺依赖
mk87                              # 启动
sudo dpkg -r mk87                 # 卸载
```

安装/卸载（rpm）：
```bash
sudo rpm -ivh dist-packages/mk87-*.rpm
mk87
sudo rpm -e mk87
```

安装时 postinst/postun 会自动 `udevadm control --reload-rules && udevadm trigger`。
如果按键测试读不到 `/dev/input/event*`，执行 `sudo usermod -aG input $USER` 后注销重登。

### 托盘与 GNOME 扩展（v0.1.8）

- `mk87.desktop` 使用 `Terminal=false`：从应用菜单启动不会再弹出终端窗口。
- Linux 托盘走 Qt `QSystemTrayIcon`（左键显示窗口、右键原生菜单），KDE / XFCE / Cinnamon /
  MATE / Ubuntu GNOME 开箱可用；**GNOME Shell 原生不显示托盘图标**，需要
  `gnome-shell-extension-appindicator` 扩展。设置页「系统托盘」卡片会检测状态，并提供一键安装
  （发行版包 + 一次 `pkexec` 管理员密码），装完注销重登（Wayland）或 `Alt+F2` → `r`（X11）。
- 没有托盘宿主时，关闭窗口 = 退出程序（不会留下看不见的后台进程）。

## CI（推荐用于产出 rpm/deb）

Windows 机器上没有 rpmbuild/dpkg，**rpm/deb 通过 GitHub Actions 的 Linux runner 构建**：
推送到 `main` 后 `.github/workflows/build.yml` 会自动跑离线测试并产出
`linux-packages`（deb+rpm）与 `windows-package`（zip+setup.exe）两个 artifact。

## 内核级驱动？

**不做内核模块**，原因见 [`../docs/linux-kernel-driver.md`](../docs/linux-kernel-driver.md)：
Linux 内核 `hid-generic` 已经提供 `/dev/hidraw*`，全部配置命令都是普通 HID report，
用户态 hidapi + udev 规则即可；内核模块只会带来 DKMS/Secure Boot/内核 ABI 的维护负担，
不增加任何功能。
