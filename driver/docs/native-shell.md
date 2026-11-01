# 原生窗口外壳（方案 B）设计

> 决策（2026-11-01）：**保留现有 web UI，外面套原生桌面窗口**（pywebview + WebView2/WebKitGTK），
> 不用浏览器标签页、不暴露可访问的端口；补上系统托盘与开机自启。不改写 UI 层。

## 1. 目标行为

| 行为 | 要求 |
|---|---|
| 启动 | 双击 exe / 桌面图标 → 直接出现独立应用窗口（无浏览器、无地址栏、无控制台黑框） |
| 关闭窗口（点 X） | **不退出程序**，隐藏到系统托盘继续运行；首次提示"程序仍在托盘运行" |
| 托盘图标 | 存在常驻；左键双击 = 显示/聚焦主窗口；右键菜单：显示主窗口 / 开机自启(勾选) / 退出 |
| **退出程序** | 托盘菜单「退出」→ 停后台任务（TFT 上传、音乐流、按键捕获）→ 停 HTTP 线程 → 销毁窗口/托盘 → 进程完全退出（**必须能关干净**，不能残留进程/端口） |
| 开机自启 | 设置页开关；开启后开机**隐藏启动到托盘**（不弹窗口），托盘可随时打开 |
| 单实例 | 再次双击启动时，不新开进程，而是唤起已有窗口并聚焦 |
| 自启动开关持久化 | 写系统自启项 + 与设置页状态双向同步 |

## 2. 技术栈

- **窗口**：`pywebview`（Windows 用系统 WebView2 = 已装 Edge 运行时；Linux 用 WebKitGTK 4.1）
- **托盘**：`pystray` + Pillow 图标（`assets/mk87.png`）
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
点窗口 X ──► 拦截 closing 事件（返回 False 取消关闭）──► window.hide() ──► 托盘继续常驻
托盘双击/「显示主窗口」──► window.show(); window.restore(); 聚焦
托盘「退出」──► shell.quit():
                 1) 停止 TFT 上传任务（cancel）/ 音乐流 / 按键捕获
                 2) uvicorn Server.should_exit = True（等线程退出，超时兜底）
                 3) pystray icon.stop()
                 4) window.destroy()
                 5) os._exit(0) 兜底（确保没有残留）
```

- **绝不能出现**：点 X 就退出、点 X 后进程还在但没有托盘图标（变成"看不见的后台进程"）、托盘退出后仍有残留进程/端口。
- 退出路径要幂等（重复点只执行一次），并写日志到 `%LOCALAPPDATA%\mk87\shell.log` / `~/.cache/mk87/shell.log`。

## 4. 与现有代码的接入点

```
driver/
├── shell.py            # 新增：pywebview 窗口 + pystray 托盘 + 单实例 + 自启动（方案 B 的核心）
├── server/app.py       # 增加 POST /api/activate（唤起窗口，由 shell 注入回调）
└── server/state.py     # 增加 /api/autostart 的读写（由 shell 提供实现，或 shell 自己管）
```

- `run.py` 保持无界面模式（浏览器/服务器模式，调试/远程用）；
- `shell.py` 作为正式启动入口：`python shell.py` 或打包后的 `MK87Config.exe`（默认走 shell）；
- 设置页新增「开机自启」开关（等 UI 收尾后接 `/api/autostart`）；
- 打包：PyInstaller `console=False` + 图标；Linux deb/rpm 增加依赖 `gir1.2-webkit2-4.1`
  （或 `webkit2gtk-4.1`）；托盘在部分 GNOME/Wayland 需要 AppIndicator 支持（见 §6 风险）。

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

**S2 打包（进行中）**
- PyInstaller 入口改为 `shell.py`、`console=False`、带图标与版本信息；
- Linux deb/rpm 增加 Qt/WebKit 运行库依赖（见 packaging/README.md）；
- 待办：Linux 包在 CI 上构建验证、系统托盘在 GNOME/Wayland 的降级测试。

## 6. 风险与兜底

| 风险 | 兜底 |
|---|---|
| pywebview 的 `closing` 事件能否可靠取消关闭（不同版本行为不同） | 基于 pywebview 5.x 实测；若不能拦截，改用"隐藏窗口 + 自绘关闭按钮"或直接调用 `window.hide()`（X 仍会销毁窗口的话，改用无原生标题栏 + 自绘标题栏方案） |
| Linux Wayland/GNOME 托盘支持差异（pystray 依赖 X11/AppIndicator） | 检测失败时降级：窗口内提供「最小化到托盘」和「退出」按钮；文档注明需要扩展 |
| WebKitGTK 在部分发行版缺失 | deb/rpm 里写依赖；缺失时给出明确安装提示 |
| 自启写入被杀软/权限拦截 | 设置页显示失败原因，提供手动自启项路径 |
| 打包后 pywebview 的 WebView2/GTK 动态库缺失 | PyInstaller hooks 收集；CI 上跑冒烟检查 |
