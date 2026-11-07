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

> 原生窗口依赖：Windows 用系统 **WebView2**（Win10/11 自带）；Linux 用 **Qt 后端**
> （`pywebview[qt]` 带来 PyQt6 + QtWebEngine，随 PyInstaller 一起打包）。

## Linux 打包策略（v0.1.8.3 起，重要）

**应用库随包，宿主系统库不随包。**

- 随包：PyQt6/Qt 6.12 wheel 自带的 Qt/WebEngine/ICU、Python 运行时（含 `libpython3.12.so`）、
  wheel 自带的第三方库（numpy/Pillow 的 `*_libs`、auditwheel 改名库等）。
- 不随包（由发行版提供）：**编译器运行库**（libstdc++/libgcc）、**GLib/GTK**、**X11 / xcb /
  Wayland**、**显卡栈**（libdrm/libgbm/libEGL/libGL/libGLX）、NSS/OpenSSL、fontconfig/freetype、
  dbus、ALSA/Pulse、CUPS/Avahi 等 —— 这些库会被系统组件（Mesa 驱动、GIO 模块、GTK 主题）加载，
  必须和系统里其它程序用同一份，否则版本错配会出问题。

> 为什么（v0.1.8.2 的教训）：PyInstaller 会顺着 Qt 库的 DT_NEEDED 把**构建机** Ubuntu 22.04 的
> glib 2.72 / libstdc++(GCC 12) / wayland 1.20 / xcb 1.14 打进 `_internal/`。冻结程序把
> `_internal` 放在库搜索路径最前面，于是在用户 Ubuntu 24.04 上：
> `libdconfsettings.so: undefined symbol: g_assertion_message_cmpint`（系统 GIO 模块用了包里的旧 glib）、
> `iHD_drv_video.so: GLIBCXX_3.4.32 not found`（系统 DRI 驱动用了包里旧 libstdc++）、
> `qt.qpa.wayland: EGL not available` → QRhi 失败 → **QtWebEngine 段错误**。
> v0.1.6 之所以正常，只是因为它恰好构建在 24.04、与用户系统版本一致。

实现与校验：

- 规则：`packaging/libfilter.py`（被 `packaging/mk87.spec` 调用，剔除所有来自 `/usr/lib`、`/lib`
  的共享库；`libpython3*` 例外保留）。
- 卡口：`packaging/linux/check-bundle.sh`（打包前跑；包里再出现宿主系统库或缺少 libpython 就失败）。
  本地打 deb 时 `build-deb.sh` 会自动调用它。
- 依赖声明：deb `Depends` / rpm `Requires` 就是「宿主系统库」清单（含 Ubuntu 24.04 的 `t64 | 旧名`
  备选）；**少一个依赖，用户装完就会启动失败**，所以 CI 还会在干净容器里做 `ldd` 缺库检查。

## 启动器与图形回退（v0.1.8.3 起）

`/usr/bin/mk87` 不是直接 `exec` 程序，而是一个小的回退启动器（`packaging/linux/mk87-launcher`）：

1. 默认启动（Wayland 原生 / X11 原生）；
2. 若进程**被信号杀死**（exit ≥ 128，如 139 = 段错误）：Wayland 会话下先退回 **XWayland**
   （`QT_QPA_PLATFORM=xcb`）；
3. 仍崩溃则用 **软件渲染**重试（`MK87_SOFTWARE_RENDERING=1` → `LIBGL_ALWAYS_SOFTWARE=1`、
   `QT_OPENGL=software`、Chromium `--disable-gpu`）。

正常退出/关窗口不会触发重试。日志在 `~/.cache/mk87/launcher.log`（启动方式/退出码/回退原因）与
`~/.cache/mk87/launcher-console.log`（非终端启动时的 stdout/stderr）；设置页「日志与诊断」可导出。
手动排障可用：`QT_QPA_PLATFORM=xcb mk87`、`MK87_SOFTWARE_RENDERING=1 mk87`、`MK87_NO_FALLBACK=1 mk87`。

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
/usr/bin/mk87                     回退启动器（默认/ XWayland / 软件渲染三级重试）
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

### 托盘与 GNOME 扩展（v0.1.8.6）

- `mk87.desktop` 使用 `Terminal=false`：从应用菜单启动不会再弹出终端窗口。
- Linux 托盘走 Qt `QSystemTrayIcon`（左键显示窗口、右键原生菜单），KDE / XFCE / Cinnamon /
  MATE / Ubuntu GNOME 开箱可用；**GNOME Shell 原生不显示托盘图标**，需要
  `gnome-shell-extension-appindicator` 扩展。
- **一键安装（推荐，不用进终端）**：GNOME 缺扩展时设置页「系统托盘」卡片会自动置顶并显示醒目提示，
  点「一键安装 AppIndicator 扩展（一次管理员密码）」→ pkexec 弹出系统密码框（只需输入一次）→
  发行版包管理器自动安装并启用扩展 → 注销重登（Wayland）或 `Alt+F2` → `r`（X11）后托盘出现。
  扩展已安装未启用时按钮为「启用扩展（无需管理员密码）」；失败时卡片给出原因并提供可复制的
  手动命令（apt/dnf/zypper/pacman 均按检测到的发行版生成）。
- 一键安装要求：桌面会话里有 polkit 认证代理（GNOME/KDE 自带）。没有 pkexec 且不是从终端启动时，
  界面不会尝试 `sudo`（GUI 进程没有 tty 必然失败），而是直接给出手动命令。
- 浏览器模式（`python run.py`）没有提权入口：按钮显示为「复制安装命令」，一键安装仅在 deb/rpm
  桌面版内可用。
- 没有托盘宿主时，关闭窗口 = 退出程序（不会留下看不见的后台进程）。

## CI（推荐用于产出 rpm/deb）

Windows 机器上没有 rpmbuild/dpkg，**rpm/deb 通过 GitHub Actions 的 Linux runner 构建**
（固定 `ubuntu-22.04`，glibc 2.35 基线）：推送到 `main` 只跑离线测试；打 `v*` tag 或手动
`workflow_dispatch` 才构建安装包，产出 `linux-deb`、`linux-rpm`、`windows-package` 三个 artifact，
tag 时自动发布 Release（含 `SHA256SUMS.txt`）。

Linux 包的构建流程里有两道**阻塞**卡口（rpm 的 Fedora 容器检查暂为提示级）：

1. `check-bundle.sh`：打包体不得含宿主系统库、必须含 libpython；
2. 干净 `ubuntu:22.04` / `ubuntu:24.04` 容器：按 deb 声明的 Depends 安装 → 全部 ELF 的 `ldd`
   不得有 `not found` → Xvfb 下启动并稳定存活 40s、进入 WebEngine 初始化。

另有手动 `linux-smoke` 工作流：可指定任意 ref 构建并跑同样的检查，也可用
`asset_tag`/`asset_version` 复验**已发布**的 `.deb`。

## 内核级驱动？

**不做内核模块**，原因见 [`../docs/linux-kernel-driver.md`](../docs/linux-kernel-driver.md)：
Linux 内核 `hid-generic` 已经提供 `/dev/hidraw*`，全部配置命令都是普通 HID report，
用户态 hidapi + udev 规则即可；内核模块只会带来 DKMS/Secure Boot/内核 ABI 的维护负担，
不增加任何功能。
