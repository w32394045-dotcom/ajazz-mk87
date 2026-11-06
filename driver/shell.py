#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MK87 Studio 原生桌面外壳（方案 B）。

行为（用户要求）：
* 独立应用窗口（pywebview + WebView2 / Qt WebEngine），不打开浏览器、不暴露端口；
* 点窗口 X **不退出**，隐藏到系统托盘继续运行；
* 例外（v0.1.8）：当前桌面没有托盘宿主时，点 X 直接退出程序，避免窗口藏起来找不回；
* 托盘：左键显示主窗口；右键菜单 = 显示主窗口 / 开机自启(勾选) / **退出**；
  Windows 用 pystray，Linux 用 Qt `QSystemTrayIcon`（pystray 的 Linux xorg 后端没有右键菜单）；
* 托盘「退出」会完整关闭：停后台任务 → 停服务 → 关窗口/托盘 → 进程退出；
* 开机自启：`--tray` 参数静默启动到托盘；
* 单实例：重复启动时唤起已有窗口并退出本进程。

用法：
    python shell.py              # 正常启动（显示窗口）
    python shell.py --tray       # 静默启动到托盘（开机自启用）
    python shell.py --debug      # 打开 WebView 开发者工具
    python shell.py --diagnose   # 只打印设备/HID 自检信息后退出（排查识别不到设备）
"""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 2026-11-05 用户 Ubuntu 现场：qtpy.QtBindingsNotFoundError: No Qt bindings could be found。
# 打包体里其实自带 PyQt6，但 qtpy 会参考外部 QT_API 环境变量；若用户环境设置了别的绑定
# （或只有某个绑定），qtpy 只会尝试那一个并直接报错。这里在任何 Qt 相关 import 之前
# 强制指定打包内自带的 PyQt6（可用 MK87_KEEP_QT_API=1 跳过，便于排查）。
if sys.platform.startswith("linux") and os.environ.get("MK87_KEEP_QT_API") != "1":
    os.environ["QT_API"] = "pyqt6"

import uvicorn  # noqa: E402

from mk87lib import autostart, bootlog  # noqa: E402

APP_NAME = "MK87 Studio"
LOCK_NAME = "MK87Studio.SingleInstance"
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache"), "mk87")
LOG_PATH = os.path.join(LOG_DIR, "shell.log")

#: faulthandler 的崩溃日志文件句柄（必须保持引用，否则会被 GC 关闭）
_crash_fh = None

log = logging.getLogger("mk87.shell")


# ----------------------------------------------------------------------
# 单实例
# ----------------------------------------------------------------------
class SingleInstance:
    """Windows 命名互斥量 / Linux 文件锁；锁文件里记录已运行实例的端口。"""

    def __init__(self) -> None:
        self._mutex = None
        self._fh = None
        self.lock_file = os.path.join(LOG_DIR, "instance.json")

    def acquire(self) -> bool:
        os.makedirs(LOG_DIR, exist_ok=True)
        if sys.platform == "win32":
            try:
                self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, LOCK_NAME)
                ERROR_ALREADY_EXISTS = 183
                return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS
            except Exception:  # noqa: BLE001
                return True
        try:
            import fcntl

            self._fh = open(os.path.join(LOG_DIR, "instance.lock"), "w")
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except Exception:  # noqa: BLE001
            return False

    def write_port(self, port: int) -> None:
        try:
            with open(self.lock_file, "w", encoding="utf-8") as f:
                json.dump({"port": int(port)}, f)
        except Exception:  # noqa: BLE001
            pass

    def read_port(self) -> int | None:
        try:
            with open(self.lock_file, encoding="utf-8") as f:
                return int(json.load(f).get("port") or 0) or None
        except Exception:  # noqa: BLE001
            return None


def _activate_existing() -> bool:
    """唤起已在运行的实例（通过其内部 HTTP 接口），成功返回 True。"""
    import urllib.request

    port = SingleInstance().read_port()
    if not port:
        return False
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/activate", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ----------------------------------------------------------------------
# Qt 预检（Linux 打包体）
# ----------------------------------------------------------------------
#: 冻结程序默认不加载系统 site-packages；但用户可能装了 python3-pyqt6，
#: 打包内 PyQt6 若因缺系统库导入失败，可作为兜底。
_SYSTEM_SITE_PACKAGES = (
    "/usr/lib/python3/dist-packages",
    "/usr/lib/python3.12/site-packages",
    "/usr/lib/python3.11/site-packages",
    "/usr/lib/python3.13/site-packages",
    "/usr/local/lib/python3.12/dist-packages",
    "/usr/local/lib/python3.12/site-packages",
)


def _env_snapshot() -> dict:
    keys = ("QT_API", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "XDG_RUNTIME_DIR",
            "DISPLAY", "WAYLAND_DISPLAY", "LD_LIBRARY_PATH", "QT_QPA_PLATFORM",
            "MK87_LAUNCH_MODE", "MK87_SOFTWARE_RENDERING", "QTWEBENGINE_CHROMIUM_FLAGS",
            "LIBGL_ALWAYS_SOFTWARE", "QT_OPENGL")
    return {k: os.environ.get(k) for k in keys}


def _apply_render_env() -> dict:
    """把回退启动模式（``MK87_SOFTWARE_RENDERING=1``）翻译成真正生效的渲染开关。

    v0.1.8.3：``packaging/linux/mk87-launcher`` 在默认启动被**信号杀死**（段错误/abort）
    后会用 ``QT_QPA_PLATFORM=xcb``、``MK87_SOFTWARE_RENDERING=1`` 逐级重试。这里负责
    把后者变成生效的环境变量：

    * ``LIBGL_ALWAYS_SOFTWARE=1`` / ``QT_OPENGL=software`` → Qt 走 Mesa llvmpipe 软件 GL；
    * ``QTWEBENGINE_CHROMIUM_FLAGS`` 追加 ``--disable-gpu --disable-gpu-compositing``
      → QtWebEngine 不做 GPU 合成。

    已经显式设置的值一律不覆盖，避免影响高级用户自己的调参。
    """
    info = {
        "launch_mode": os.environ.get("MK87_LAUNCH_MODE"),
        "requested": os.environ.get("MK87_SOFTWARE_RENDERING") == "1",
    }
    if not info["requested"]:
        return info
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    os.environ.setdefault("QT_OPENGL", "software")
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    for flag in ("--disable-gpu", "--disable-gpu-compositing"):
        if flag not in flags:
            flags.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
    info["chromium_flags"] = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
    return info


def _preflight_qt() -> bool:
    """Linux 启动前检查打包体里的 Python Qt 绑定能否导入。

    2026-11-05 用户 Ubuntu 现场：pywebview 启动时报
    ``qtpy.QtBindingsNotFoundError: No Qt bindings could be found``（闪退、看不到日志）。
    webview 抛出的异常把底层 ImportError 吞掉了，这里提前 import PyQt6，把**完整 traceback**
    写进 ``~/.mk87-boot.log`` 与日志目录，便于定位是缺系统库、绑定被环境变量带偏还是打包缺失。
    打包内失败时再尝试系统 python3-pyqt6 兜底。
    """
    import traceback as _tb  # noqa: PLC0415

    if not sys.platform.startswith("linux"):
        return True
    bootlog.mark("preflight-pyqt6-start", QT_API=os.environ.get("QT_API"),
                 frozen=getattr(sys, "frozen", False), env=_env_snapshot())
    try:
        import PyQt6  # noqa: PLC0415, F401
        from PyQt6 import QtCore  # noqa: PLC0415

        bootlog.mark("preflight-pyqt6-ok", qt=QtCore.QT_VERSION_STR,
                     pyqt=QtCore.PYQT_VERSION_STR)
        return True
    except BaseException:  # noqa: BLE001
        first = _tb.format_exc()
        bootlog.mark("preflight-pyqt6-failed",
                     traceback=first.replace("\n", " | ")[:4000])
        log.error("打包内 PyQt6 导入失败:\n%s", first)

    # 兜底：尝试系统 site-packages 里的 python3-pyqt6
    for path in _SYSTEM_SITE_PACKAGES:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
    try:
        from PyQt6 import QtCore  # noqa: PLC0415

        bootlog.mark("preflight-pyqt6-system-ok", qt=QtCore.QT_VERSION_STR,
                     sys_path=[p for p in _SYSTEM_SITE_PACKAGES if p in sys.path])
        return True
    except BaseException:  # noqa: BLE001
        second = _tb.format_exc()
        bootlog.mark("preflight-pyqt6-system-failed",
                     traceback=second.replace("\n", " | ")[:4000])
        log.error("系统 PyQt6 兜底导入也失败:\n%s", second)

    # 写一份独立报告，用户直接就能找到（不需要去翻日志目录）
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        report = os.path.join(LOG_DIR, "qt-error.txt")
        with open(report, "w", encoding="utf-8") as f:
            f.write("MK87 Studio 无法加载 Qt（PyQt6 导入失败）\n")
            f.write("=" * 60 + "\n\n打包内 PyQt6 traceback:\n")
            f.write(first + "\n")
            f.write("\n系统 python3-pyqt6 兜底 traceback:\n")
            f.write(second + "\n")
            f.write("\n环境变量:\n")
            for k, v in _env_snapshot().items():
                f.write(f"  {k}={v}\n")
            f.write("\nsys.path:\n" + "\n".join(sys.path) + "\n")
            f.write(f"\n启动日志: {bootlog.path()}\n")
        bootlog.mark("preflight-qt-report", path=report)
        try:
            print(f"MK87 Studio: Qt 无法加载，详细原因已写入 {report}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    return False


def _report_qt_failure() -> None:
    """GUI 起不来时尽量用桌面通知/对话框告诉用户去哪看错误报告。"""
    report = os.path.join(LOG_DIR, "qt-error.txt")
    text = (f"MK87 Studio 无法启动：Qt 组件加载失败。\n\n详细原因请查看：\n{report}\n\n"
            f"启动日志：{bootlog.path()}")
    # zenity 在 GNOME / Ubuntu 桌面通常可用
    for cmd in (["zenity", "--error", "--no-markup", "--text", text],
                ["kdialog", "--error", text],
                ["notify-send", "MK87 Studio", "Qt 组件加载失败，详情见 " + report]):
        try:
            import shutil
            import subprocess

            if shutil.which(cmd[0]):
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        except Exception:  # noqa: BLE001
            continue


# ----------------------------------------------------------------------
# 外壳
# ----------------------------------------------------------------------
class Shell:
    def __init__(self, *, silent: bool = False, debug: bool = False,
                 no_tray: bool = False) -> None:
        self.silent = silent
        self.debug = debug
        #: 完全禁用系统托盘（排查「启动闪退」用：`--no-tray` 或环境变量 MK87_NO_TRAY=1）
        self.no_tray = bool(no_tray) or os.environ.get("MK87_NO_TRAY", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        self.port = _free_port()
        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.window = None
        self.tray = None
        self._tray_backend = None
        self._quitting = False

    # ---------------------------------------------------------- 服务
    def start_server(self) -> None:
        from server.app import app, manager  # noqa: PLC0415

        self.manager = manager
        # 无控制台打包（console=False）时 sys.stdout/stderr 为 None，
        # uvicorn 默认日志配置会调 sys.stdout.isatty() 崩溃 → 跳过其日志配置，
        # 使用 shell 自己的文件日志。
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self.port,
            log_config=None,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.server.run, name="mk87-http", daemon=True)
        self.server_thread.start()
        # 等待端口就绪
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.3):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("本地服务启动超时")

    def wait_ready(self) -> None:
        import urllib.request

        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/version", timeout=0.5)
                return
            except Exception:  # noqa: BLE001
                time.sleep(0.1)

    # ---------------------------------------------------------- 窗口
    def _on_closing(self):
        """点窗口 X：有托盘时隐藏到托盘；没有托盘宿主时直接退出程序。

        Linux（v0.1.8 起）托盘走 Qt：GNOME 没装 AppIndicator 扩展、或桌面本身
        不提供托盘宿主时，窗口藏起来就再也找不回来了，因此这种环境下点 X
        等价于「退出程序」，与设置页「系统托盘」卡片的说明一致。
        """
        if self._quitting:
            return True
        available = self._tray_available(wait=1.0)
        bootlog.mark("window-closing", available=available, backend=self._tray_backend,
                     no_tray=self.no_tray)
        if available is not True:
            log.warning("系统托盘不可用，关闭窗口 = 退出程序（%s）", self._tray_error() or "无托盘宿主")
            self.quit()
            return True
        try:
            self.window.hide()
            self._notify_tray_running()
        except Exception:  # noqa: BLE001
            pass
        return False

    def _notify_tray_running(self) -> None:
        if getattr(self, "_tray_tip_shown", False):
            return
        self._tray_tip_shown = True
        message = "MK87 Studio 仍在系统托盘运行，右键托盘图标可退出。"
        try:
            if self._tray_backend == "qt":
                from mk87lib import tray_linux  # noqa: PLC0415

                tray_linux.notify("MK87 Studio", message)
            elif self.tray is not None:
                self.tray.notify(message, "MK87 Studio")
        except Exception:  # noqa: BLE001
            pass

    def show_window(self) -> None:
        try:
            self.window.show()
            self.window.restore()
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------- 托盘
    def _build_tray(self):
        import pystray
        from PIL import Image

        icon_path = os.path.join(HERE, "assets", "mk87.png")
        try:
            image = Image.open(icon_path)
        except Exception:  # noqa: BLE001
            image = Image.new("RGB", (64, 64), (20, 30, 45))

        def on_show(icon=None, item=None):
            self.show_window()

        def on_toggle_autostart(icon=None, item=None):
            try:
                st = autostart.status()
                autostart.set_enabled(not st["enabled"])
                self._refresh_tray()
            except Exception as exc:  # noqa: BLE001
                log.warning("切换开机自启失败: %s", exc)

        def on_quit(icon=None, item=None):
            self.quit()

        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", on_show, default=True),
            pystray.MenuItem("开机自启", on_toggle_autostart,
                             checked=lambda item: bool(autostart.status().get("enabled"))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )
        self.tray = pystray.Icon("mk87studio", image, APP_NAME, menu)
        self._tray_backend = "pystray"

    def _refresh_tray(self) -> None:
        try:
            if self.tray is not None:
                self.tray.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def _start_pystray(self) -> None:
        """启动 pystray 托盘（Windows 默认；Linux 仅作 Qt 不可用时的兜底）。"""
        self._build_tray()
        threading.Thread(target=self.tray.run, name="mk87-tray", daemon=True).start()

    def _linux_tray_bootstrap(self) -> None:
        """在 webview.start(func=...) 的子线程里启动 Qt 托盘（v0.1.8）。

        Qt 托盘需要 GUI 线程，tray_linux.start() 内部会等待 QApplication 就绪后
        用 QueuedConnection 把创建任务投递到主线程。失败时回退 pystray（Linux 下
        右键菜单不可用），保证至少还有一个图标。
        """
        from mk87lib import tray_linux, trayenv  # noqa: PLC0415

        bootlog.mark("tray-bootstrap-start")
        tray_linux.reset_state()
        # GNOME 且 AppIndicator 扩展不可用：GNOME 根本不会显示任何托盘图标，
        # 直接跳过 QSystemTrayIcon 创建（v0.1.8 用户「闪退」排查：尽量不碰 Qt 托盘路径）。
        try:
            desktop = trayenv.desktop_environment()
            bootlog.mark("tray-env", desktop=desktop.get("currentDesktop"),
                         session=desktop.get("sessionType"), family=desktop.get("family"))
            if desktop.get("family") == "gnome":
                ext = trayenv.extension_state()
                bootlog.mark("tray-gnome-ext", installed=ext.get("installed"),
                             enabled=ext.get("enabled"))
                if not (ext.get("installed") and ext.get("enabled")):
                    reason = ("GNOME 未启用 AppIndicator 扩展，托盘图标无法显示"
                              "（设置 → 系统托盘 可一键安装）")
                    tray_linux.set_unavailable(reason)
                    log.warning("跳过 Qt 托盘创建：%s", reason)
                    return
        except BaseException:  # noqa: BLE001
            bootlog.mark("tray-env-check-failed")
            log.exception("托盘环境检测失败，继续尝试创建 Qt 托盘")

        try:
            started = tray_linux.start(
                self,
                icon_path=os.path.join(HERE, "assets", "mk87.png"),
                app_name=APP_NAME,
            )
            bootlog.mark("tray-start-returned", started=started)
        except BaseException:  # noqa: BLE001
            log.exception("Qt 托盘启动失败")
            started = False
        if started:
            self._tray_backend = "qt"
            log.info("Linux 托盘：Qt QSystemTrayIcon（右键菜单可用）")
            return
        log.warning("Qt 托盘不可用（%s），回退 pystray：Linux 下没有右键菜单",
                    tray_linux.state().get("error") or "未知原因")
        bootlog.mark("tray-fallback-pystray", error=tray_linux.state().get("error"))
        try:
            self._start_pystray()
        except BaseException:  # noqa: BLE001
            log.exception("pystray 托盘也启动失败")

    # ---------------------------------------------------- 托盘（外壳接口）
    def autostart_enabled(self) -> bool:
        """托盘菜单「开机自启」勾选状态。"""
        try:
            return bool(autostart.status().get("enabled"))
        except Exception:  # noqa: BLE001
            return False

    def toggle_autostart(self, enabled: bool) -> bool:
        """切换开机自启，返回切换后的真实状态（失败保持原状）。"""
        try:
            actual = bool(autostart.set_enabled(bool(enabled)).get("enabled"))
        except Exception as exc:  # noqa: BLE001
            log.warning("切换开机自启失败: %s", exc)
            return self.autostart_enabled()
        self._refresh_tray()
        return actual

    def quit_app(self) -> None:
        """托盘菜单「退出」入口（与 /api/quit、设置页按钮同一路径）。"""
        self.quit()

    def _tray_available(self, wait: float = 0.0) -> bool | None:
        """当前是否有可用的托盘宿主（None = 还不知道/正在创建）。"""
        if self.no_tray:
            return False
        if self._tray_backend == "pystray":
            return self.tray is not None
        if sys.platform.startswith("linux"):
            from mk87lib import tray_linux  # noqa: PLC0415

            deadline = time.time() + max(0.0, wait)
            while True:
                available = tray_linux.STATE.get("available")
                if available is not None or time.time() >= deadline:
                    return available
                time.sleep(0.05)
        return True if self.tray is not None else None

    def _tray_error(self) -> str:
        if sys.platform.startswith("linux"):
            from mk87lib import tray_linux  # noqa: PLC0415

            return str(tray_linux.STATE.get("error") or "")
        return ""

    def tray_state(self) -> dict:
        """注入 server.app 的托盘状态（/api/status 与 /api/tray/status 使用）。"""
        shell_mode = bool(getattr(getattr(self, "manager", None), "shell_mode", False))
        if self._tray_backend == "pystray":
            return {
                "available": self.tray is not None,
                "backend": "pystray",
                "error": None,
                "shell": shell_mode,
            }
        if sys.platform.startswith("linux"):
            from mk87lib import tray_linux  # noqa: PLC0415

            st = tray_linux.state()
            st["shell"] = shell_mode
            return st
        return {"available": self.tray is not None, "backend": self._tray_backend,
                "error": None, "shell": shell_mode}

    # ---------------------------------------------------------- 退出
    def _stop_music_and_wait(self, timeout: float = 3.0) -> bool:
        """停止音乐律动，并同步等待 restore_effect 跑完（最多 timeout 秒）。

        事故背景（2026-11-02 22:45）：音乐 start 写了 mode=128 后进程被关机杀死，
        music.py 的 finally: restore_effect() 没执行，键盘一直停在自定义逐键表。
        具体等待逻辑在 state.DeviceManager.stop_music（按 lighting 记录的恢复
        时间戳确认），这里保证它在 os._exit 之前被调用且失败只告警。
        """
        manager = getattr(self, "manager", None)
        if manager is None:
            return True
        try:
            ok = bool(manager.stop_music(timeout))
        except Exception as exc:  # noqa: BLE001
            log.warning("退出：停止音乐/等待灯效恢复失败: %s", exc)
            return False
        if ok:
            log.info("退出：音乐已停止且灯效已恢复（或无需恢复）")
        return ok

    def quit(self) -> None:
        """托盘「退出」：停后台任务 → 停服务 → 关窗口/托盘 → 进程退出（幂等）。

        注意：可能从托盘线程 / HTTP 定时器线程调用，而 pywebview 的窗口 API
        必须在 GUI 主线程使用，因此清理动作放到独立线程并设超时，最后
        os._exit 兜底，保证「点了退出就一定能退干净」。
        """
        if self._quitting:
            return
        self._quitting = True
        bootlog.mark("quit-begin")
        log.info("开始退出…")

        def _cleanup() -> None:
            try:
                self.manager.tft_job.cancel()
            except Exception:  # noqa: BLE001
                pass
            # 顺序很重要：先停音乐并等 restore_effect 跑完，再关设备；
            # 否则 restore 写不进去，键盘会停在自定义逐键表。
            self._stop_music_and_wait(3.0)
            try:
                self.manager.keytest.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.manager.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                if self.server is not None:
                    self.server.should_exit = True
            except Exception:  # noqa: BLE001
                pass
            try:
                if self._tray_backend == "qt":
                    # Qt 托盘只能在 GUI 线程隐藏，这里用队列投递（进程马上退出，失败也无妨）
                    from mk87lib import tray_linux  # noqa: PLC0415

                    tray_linux.hide_async()
                elif self.tray is not None:
                    self.tray.stop()
            except Exception:  # noqa: BLE001
                pass
            # 进程即将退出，不需要再销毁窗口（os._exit 会回收全部资源），
            # 避免在非 GUI 线程调 pywebview 窗口 API 造成卡顿。
            log.info("退出完成")
            try:
                sys.stdout.flush()
            except Exception:  # noqa: BLE001
                pass
            os._exit(0)

        t = threading.Thread(target=_cleanup, name="mk87-quit", daemon=True)
        t.start()
        # 清理预算 8s：音乐停止/灯效恢复最多 3s + keytest 1.5s + 设备关闭 ~1s + 托盘
        t.join(timeout=8)
        # 兜底：清理线程卡住也强制退出（进程退出即释放托盘/窗口/端口）
        log.warning("清理超时，强制退出")
        os._exit(0)

    # ---------------------------------------------------------- 主流程
    def _start_stall_watchdog(self) -> None:
        """进程级卡顿探针（不影响功能，只写日志）。

        2026-11-04 用户 Linux 日志里有多次 2~9 秒的「整段时间没有任何日志」窗口，
        HTTP 请求耗时随之变大，但看不出是哪个线程卡住。这里每 0.5s 采样一次
        单调时钟：采样间隔远大于 0.5s 说明**整个进程被冻结**（OS 挂起 / 长 GIL
        占用 / 磁盘 IO 卡住），可与「某个线程在等设备锁」区分开。
        """

        def _loop() -> None:
            last = time.monotonic()
            while not self._quitting:
                time.sleep(0.5)
                now = time.monotonic()
                gap = now - last
                last = now
                if gap > 2.0:
                    log.warning("进程卡顿：%.1fs 内 watchdog 无采样（正常 0.5s）", gap)

        threading.Thread(target=_loop, name="mk87-watchdog", daemon=True).start()

    def run(self) -> int:
        bootlog.mark("shell-run-start", silent=self.silent, no_tray=self.no_tray,
                     debug=self.debug, platform=sys.platform, env=_env_snapshot())
        # Linux：先确认打包体里的 PyQt6 能导入。失败时把完整 traceback 写进
        # ~/.mk87-boot.log 与 <日志目录>/qt-error.txt，并弹桌面错误提示后退出，
        # 不再让 pywebview 丢出「No Qt bindings could be found」这种没有原因的错误。
        if sys.platform.startswith("linux") and not _preflight_qt():
            bootlog.mark("qt-preflight-failed")
            _report_qt_failure()
            return 3
        self.start_server()
        bootlog.mark("server-started", port=self.port)
        from server import app as server_app  # noqa: PLC0415

        server_app.activate_callback = self.show_window
        server_app.quit_callback = self.quit
        # 设置页「系统托盘」卡片 / /api/status 的托盘摘要由此注入（浏览器模式为 None）
        server_app.tray_status_callback = self.tray_state
        self.manager.shell_mode = True
        self.wait_ready()
        SingleInstance().write_port(self.port)
        self._start_stall_watchdog()
        bootlog.mark("server-ready")

        import webview  # noqa: PLC0415

        self.window = webview.create_window(
            APP_NAME,
            f"http://127.0.0.1:{self.port}/",
            width=1360, height=880, min_size=(1120, 720),
            background_color="#0f1418",
            hidden=self.silent,
            confirm_close=False,
        )
        self.window.events.closing += self._on_closing
        bootlog.mark("window-created", hidden=self.silent)

        # Linux 上 pywebview 默认先试 GTK（缺 python3-gi 时先刷一条 ERROR 再回退 Qt）；
        # 打包版只带 Qt，直接指定 qt，避免误导性报错和多余的回退尝试。
        gui = "qt" if sys.platform.startswith("linux") else None
        linux = sys.platform.startswith("linux")
        try:
            if self.no_tray:
                # 排查「启动闪退」用的安全模式：完全不创建托盘，关闭窗口 = 退出程序
                bootlog.mark("tray-disabled")
                log.info("已禁用系统托盘（--no-tray / MK87_NO_TRAY）")
                webview.start(debug=self.debug, gui=gui)
            elif linux:
                # v0.1.8：Linux 托盘改 Qt（自带右键菜单）。Qt 控件必须在 GUI 线程创建，
                # 用 start(func=...) 的子线程等 QApplication 就绪后投递（见 tray_linux.py）。
                bootlog.mark("webview-start-begin", tray="qt")
                webview.start(debug=self.debug, gui=gui, func=self._linux_tray_bootstrap)
            else:
                self._start_pystray()
                bootlog.mark("webview-start-begin", tray="pystray")
                webview.start(debug=self.debug, gui=gui)
        except BaseException:  # noqa: BLE001
            import traceback as _tb  # noqa: PLC0415

            bootlog.mark("webview-start-failed",
                         traceback=_tb.format_exc().replace("\n", " | ")[:4000])
            log.exception("webview.start 失败（图形环境 / Qt 绑定）")
            raise
        bootlog.mark("webview-start-returned")
        # webview.start 返回 = 窗口被销毁（正常退出路径已在 quit() 处理，这里兜底）
        if not self._quitting:
            self.quit()
        return 0


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    # console=False 的打包程序里 stdout/stderr 为 None，很多库会因此崩溃
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    # 完整日志（滚动 mk87.log + 本次运行 session-*.log + errors.log），
    # 设置页可一键导出诊断包。同时把启动/退出等外壳日志写到同一套日志里。
    from mk87lib import logsetup

    logsetup.setup_logging(console=False, role="shell")
    # 原生崩溃诊断：打包程序（console=False）崩溃时控制台什么都看不到，
    # faulthandler 会把所有线程的 Python 栈写进 crash.log，方便定位段错误/访问冲突。
    try:
        import faulthandler

        global _crash_fh
        _crash_fh = open(os.path.join(logsetup.log_dir(), "crash.log"), "a",
                         buffering=1, encoding="utf-8", errors="replace")
        faulthandler.enable(file=_crash_fh, all_threads=True)
    except Exception:  # noqa: BLE001
        pass
    logging.getLogger("mk87.shell").info(
        "外壳启动（tray=%s）; 日志目录=%s", "--tray" in sys.argv, logsetup.log_dir()
    )


def _run_diagnose() -> int:
    """打印 HID/设备自检信息（识别不到设备时用），同时保存到日志目录。"""
    from mk87lib import logsetup
    from mk87lib.diag import collect_diagnostics

    try:
        text = "\n".join(collect_diagnostics())
    except Exception:  # noqa: BLE001
        log.exception("自检失败")
        return 1
    out_path = os.path.join(logsetup.log_dir(), "diagnose.txt")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:  # noqa: BLE001
        out_path = ""
    if sys.stdout is not None:
        try:
            # Windows 控制台默认 GBK，✓/✗ 等字符会 UnicodeEncodeError
            sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - 旧版/被重定向的 stdout
            pass
        print(text)
        if out_path:
            print(f"\n（以上内容已保存到 {out_path}）")
    return 0


def main() -> int:
    bootlog.mark("main-start", argv=sys.argv[1:], frozen=getattr(sys, "frozen", False),
                 exec=sys.executable)
    # Linux 回退启动模式：launcher 崩溃重试时用 MK87_SOFTWARE_RENDERING=1 进来，
    # 这里在 Qt/WebEngine 初始化前把软件渲染开关落地，并把启动方式记进 boot log。
    _render = _apply_render_env()
    if _render.get("requested") or _render.get("launch_mode"):
        bootlog.mark("render-env", **{k: v for k, v in _render.items() if v is not None},
                     env=_env_snapshot())
    ap = argparse.ArgumentParser(description="MK87 Studio 桌面外壳")
    ap.add_argument("--tray", action="store_true", help="静默启动到系统托盘（开机自启用）")
    ap.add_argument("--debug", action="store_true", help="打开 WebView 开发者工具")
    ap.add_argument("--no-single-instance", action="store_true", help="跳过单实例检查（调试用）")
    ap.add_argument("--diagnose", action="store_true", help="打印设备/HID 自检信息后退出")
    ap.add_argument("--no-tray", action="store_true",
                    help="不创建系统托盘（排查启动闪退用；也可设 MK87_NO_TRAY=1）")
    args = ap.parse_args()
    setup_logging()
    bootlog.mark("logging-ready", log_dir=LOG_DIR)

    if args.diagnose:
        return _run_diagnose()

    if not args.no_single_instance:
        if not SingleInstance().acquire():
            bootlog.mark("single-instance-existing")
            log.info("已有实例在运行，尝试唤起…")
            if _activate_existing():
                return 0
            log.warning("未找到已有实例端口，继续启动新实例")
        else:
            bootlog.mark("single-instance-acquired")

    shell = Shell(silent=args.tray, debug=args.debug, no_tray=args.no_tray)
    try:
        return shell.run()
    except BaseException:  # noqa: BLE001
        bootlog.mark("shell-run-failed")
        log.exception("外壳启动失败")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
