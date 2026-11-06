# 原生窗口外壳（方案 B）设计

> 决策（2026-11-01）：**保留现有 web UI，外面套原生桌面窗口**（pywebview + WebView2/Qt WebEngine），
> 不用浏览器标签页、不暴露可访问的端口；补上系统托盘与开机自启。不改写 UI 层。
> v0.1.8（2026-11-05）：Linux 托盘从 pystray 换成 Qt（pystray 的 xorg 后端没有右键菜单），
> 并补上 GNOME AppIndicator 扩展的检测与一键安装。

## 1. 目标行为

| 行为 | 要求 |
|---|---|
| 启动 | 双击 exe / 桌面图标 → 直接出现独立应用窗口（无浏览器、无地址栏、无控制台黑框） |
| 关闭窗口（点 X） | **不退出程序**，隐藏到系统托盘继续运行；首次提示"程序仍在托盘运行"。**例外（v0.1.8）：当前桌面确实没有托盘宿主时（如未装 AppIndicator 扩展的 GNOME）点 X 直接退出程序**，避免窗口隐藏后找不回 |
| 托盘图标 | 存在常驻；左键单击/双击 = 显示/聚焦主窗口；右键菜单：显示主窗口 / 开机自启(勾选) / 退出。Linux 用 Qt（原生右键菜单），Windows 用 pystray |
| **退出程序** | 托盘菜单「退出」→ 停后台任务（TFT 上传、音乐流、按键捕获）→ 停 HTTP 线程 → 销毁窗口/托盘 → 进程完全退出（**必须能关干净**，不能残留进程/端口） |
| 开机自启 | 设置页开关；开启后开机**隐藏启动到托盘**（不弹窗口），托盘可随时打开 |
| 单实例 | 再次双击启动时，不新开进程，而是唤起已有窗口并聚焦 |
| 自启动开关持久化 | 写系统自启项 + 与设置页状态双向同步 |

## 2. 技术栈

- **窗口**：`pywebview`（Windows 用系统 WebView2 = 已装 Edge 运行时；Linux 用 Qt/WebEngine）
- **托盘**：
  - Windows：`pystray` + Pillow 图标（`assets/mk87.png`）——保持原实现；
  - Linux（v0.1.8 起）：`mk87lib/tray_linux.py` 的 **Qt `QSystemTrayIcon` + `QMenu`**。原因：pystray
    在打包体里没有 `gi`/AppIndicator 后端，只能回退 `_xorg`，而 `_xorg` 的 `HAS_MENU = False`
    （只处理左键），所以右键菜单无法实现。Qt 走 StatusNotifierItem + dbusmenu，KDE/XFCE/
    Cinnamon/MATE/Ubuntu GNOME 原生可用；GNOME 需要 AppIndicator 扩展（见 §6）。Qt 控件必须在
    GUI 线程创建，`tray_linux.start()` 会等 `QApplication` 就绪后用 QueuedConnection 投递创建任务。
- **后端**：现有 FastAPI 服务保留，但仅绑定 `127.0.0.1` 随机端口，作为窗口的内部后端；
  外壳通过 `window.load_url(f"http://127.0.0.1:{port}/")` 加载现有 `web/`。
  （保留 HTTP 层的价值：CLI/调试/自动化/未来远程控制；不对外暴露。）
- **自启动**：
  - Windows：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 写 `"<安装路径>\MK87Config.exe" --tray`
  - Linux：`~/.config/autostart/mk87.desktop`（`Exec=/usr/bin/mk87 --tray`，`X-GNOME-Autostart-enabled=true`）
- **单实例**：
  - Windows：命名互斥量 `Global\MK87Studio`
  - Linux：`~/.cache/mk87.lock` 文件锁（flock）
  - 二次启动 → 请求已有实例内部接口 `POST /api/activate`（显示窗口）→ 自身退出

## 3. 关闭/退出语义（用户明确要求）

```
点窗口 X ──► 有托盘：拦截 closing（返回 False）──► window.hide() ──► 托盘继续常驻
          └─ 无托盘宿主（v0.1.8）：直接 shell.quit() 退出程序
托盘单击/双击/「显示主窗口」──► window.show(); window.restore(); 聚焦
托盘「退出」──► shell.quit():
                 1) 停止 TFT 上传任务（cancel）/ 音乐流 / 按键捕获
                 2) uvicorn Server.should_exit = True（等线程退出，超时兜底）
                 3) 停托盘（Linux：Qt hide 投递到 GUI 线程；Windows：pystray icon.stop()）
                 4) os._exit(0) 兜底（确保没有残留）
```

- **绝不能出现**：点 X 就退出、点 X 后进程还在但没有托盘图标（变成"看不见的后台进程"）、托盘退出后仍有残留进程/端口。
- 退出路径要幂等（重复点只执行一次），并写日志到 `%LOCALAPPDATA%\mk87\shell.log` / `~/.local/state/mk87/logs/`。

## 4. 与现有代码的接入点

```
driver/
├── shell.py             # pywebview 窗口 + 托盘（Linux Qt / Windows pystray）+ 单实例 + 自启动
├── mk87lib/tray_linux.py# Linux Qt 托盘（QSystemTrayIcon + QMenu，GUI 线程投递）
├── mk87lib/trayenv.py   # Linux 托盘环境探测 + GNOME AppIndicator 扩展安装/启用
├── server/app.py        # POST /api/activate、/api/quit、GET /api/tray/status、
│                        # POST /api/tray/install-extension、/api/tray/enable-extension
└── server/state.py      # /api/autostart 的读写（由 shell 提供实现，或 shell 自己管）
```

- `run.py` 保持无界面模式（浏览器/服务器模式，调试/远程用）；
- `shell.py` 作为正式启动入口：`python shell.py` 或打包后的 `MK87Config.exe`（默认走 shell）；
- 设置页「开机自启」开关接 `/api/autostart`；「系统托盘」卡片接 `/api/tray/*`（v0.1.8）；
- 打包：PyInstaller `console=False` + 图标；Linux 打包体自带 Qt/WebEngine（`pywebview[qt]` +
  PyInstaller Qt hook），不依赖系统 WebKitGTK；托盘在 GNOME/Wayland 需要 AppIndicator 支持（见 §6 风险）。

## 5. 实施状态

**S0 外壳（已完成，2026-11-01 实测）**
- `shell.py`：pywebview 独立窗口加载内嵌 FastAPI（随机端口，仅 127.0.0.1）；
- 点窗口 X → `closing` 事件返回 False 取消关闭 → `window.hide()` 隐藏到托盘；
- 托盘：双击/「显示主窗口」唤起；右键菜单「显示主窗口 / 开机自启(勾选) / 退出」；
- 托盘「退出」→ 停 TFT/音乐/按键捕获 → 停服务 → 停托盘 → `os._exit` 兜底：
  实测 **2.3–3.8 秒干净退出、无残留进程**（含清理线程超时 6s 强制退出兜底）；
- 单实例（Windows 命名互斥量 / Linux flock + `instance.json` 记录端口）：
  二次启动 **1 秒内**唤起已有窗口并退出；
- `--tray` 静默启动到托盘；`--debug` 打开 WebView 开发者工具。

**S1 自启动 / 退出接口（已完成）**
- `mk87lib/autostart.py`：Windows 写 `HKCU\...\Run`、Linux 写 `~/.config/autostart/mk87.desktop`（带 `--tray`）；
- 接口：`GET/PUT /api/autostart`；`POST /api/activate`（唤起窗口）；`POST /api/quit`（完整退出）；
- `/api/status` 增加 `shell` 字段（原生外壳模式=true），供设置页显示「退出程序」按钮；
- 已验证：Windows 注册/取消注册往返、托盘静默启动、API 退出、打包 exe（console=False）运行与退出。

**S2 打包（已完成，v0.1.4 起持续）**
- PyInstaller 入口改为 `shell.py`、`console=False`、带图标与版本信息；
- Linux 包只带 Qt（PyInstaller 收集 PyQt6/PySide6），不依赖系统 WebKitGTK；
- CI 上构建 deb/rpm + Windows portable/setup。

**S3 Linux 托盘与桌面集成（v0.1.8，2026-11-05）**
- `Terminal=true` → `false`：从应用菜单启动不再弹终端窗口；
- Linux 托盘改 Qt（右键菜单可用），Windows 保持 pystray；
- 无托盘宿主时点 X 直接退出程序（不再隐藏到找不回的地方），主窗口显示横幅说明；
- 设置页「系统托盘」卡片：后端/宿主/桌面环境/会话类型/GNOME 版本/扩展安装与启用状态；
- GNOME 一键安装 AppIndicator 扩展（发行版包 + 一次 pkexec 提权，失败回退复制命令）；
- 接口：`GET /api/tray/status`、`POST /api/tray/install-extension`、`POST /api/tray/enable-extension`；
- 验证：277 单测全绿（新增 32 项托盘测试）+ linkedom 前端冒烟 16 项；Linux 真机待用户验证。

**S4 Linux 图形栈稳定性（v0.1.8.3，2026-11-06）**
- 打包策略：**应用库随包（Qt/WebEngine/wheel 自带库），宿主系统库不随包**
  （`packaging/libfilter.py`）；否则构建机 Ubuntu 22.04 的 glib/libstdc++/wayland/xcb 会在
  Ubuntu 24.04 上顶掉系统 Mesa/GLib，导致 `EGL not available` → QtWebEngine 段错误。
- `/usr/bin/mk87` 改为**回退启动器**：仅在进程被信号杀死（exit ≥ 128）时依次重试
  默认 → XWayland（`QT_QPA_PLATFORM=xcb`）→ 软件渲染（`MK87_SOFTWARE_RENDERING=1`）；
  正常退出不重试。日志 `~/.cache/mk87/launcher.log`、`~/.cache/mk87/launcher-console.log`。
- `shell.py`：`_apply_render_env()` 把 `MK87_SOFTWARE_RENDERING=1` 翻译为
  `LIBGL_ALWAYS_SOFTWARE=1` / `QT_OPENGL=software` / Chromium `--disable-gpu --disable-gpu-compositing`，
  并把启动方式（`MK87_LAUNCH_MODE`）、渲染环境写入 `~/.mk87-boot.log`（`render-env` 标记）。
- 排障变量：`MK87_NO_FALLBACK=1`（只启动一次）、`MK87_FORCE_X11=1`、`MK87_SOFTWARE_RENDERING=1`。
- 验证：300 单测全绿；CI 干净 Ubuntu 22.04/24.04 容器做 `ldd` 缺库检查 + 启动存活 40s。
  真机最终确认仍以用户 Ubuntu 24.04 为准。

## 6. 风险与兜底

| 风险 | 兜底 |
|---|---|
| pywebview 的 `closing` 事件能否可靠取消关闭（不同版本行为不同） | 基于 pywebview 5.x/6.x 实测；若不能拦截，改用"隐藏窗口 + 自绘关闭按钮"（X 仍会销毁窗口的话，改用无原生标题栏 + 自绘标题栏方案） |
| GNOME 原生不显示托盘图标（需要 AppIndicator 扩展） | 启动时检测 `QSystemTrayIcon.isSystemTrayAvailable()`；设置页「系统托盘」卡片检测扩展状态并提供一键安装（发行版包 + 一次 pkexec），失败回退复制命令；Wayland 提示注销重登、X11 提示 Alt+F2 → r |
| 某些桌面（旧式 XEmbed-only / 无 SNI 宿主）Qt 托盘仍不显示 | 无托盘宿主时点 X 直接退出（不会变成隐形后台进程），主窗口横幅说明原因；设置页展示真实后端与桌面环境，便于反馈定位 |
| pkexec/polkit 不可用、无网络、包管理器锁 | 返回安装输出与 `manualCommands` 供用户复制执行；无 pkexec 时自动退到 sudo，再不行只给手动命令 |
| 自启写入被杀软/权限拦截 | 设置页显示失败原因，提供手动自启项路径 |
| 打包后 Qt 动态库缺失 | PyInstaller 收集 PyQt6/Qt 插件；CI 上跑 Linux deb/rpm 构建冒烟 |
