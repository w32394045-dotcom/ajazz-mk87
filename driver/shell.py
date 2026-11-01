#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MK87 Studio 原生桌面外壳（方案 B）。

行为（用户要求）：
* 独立应用窗口（pywebview + WebView2/WebKitGTK），不打开浏览器、不暴露端口；
* 点窗口 X **不退出**，隐藏到系统托盘继续运行；
* 托盘：双击显示主窗口；右键菜单 = 显示主窗口 / 开机自启(勾选) / **退出**；
* 托盘「退出」会完整关闭：停后台任务 → 停服务 → 关窗口/托盘 → 进程退出；
* 开机自启：`--tray` 参数静默启动到托盘；
* 单实例：重复启动时唤起已有窗口并退出本进程。

用法：
    python shell.py              # 正常启动（显示窗口）
    python shell.py --tray       # 静默启动到托盘（开机自启用）
    python shell.py --debug      # 打开 WebView 开发者工具
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

import uvicorn  # noqa: E402

from mk87lib import autostart  # noqa: E402

APP_NAME = "MK87 Studio"
LOCK_NAME = "MK87Studio.SingleInstance"
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache"), "mk87")
LOG_PATH = os.path.join(LOG_DIR, "shell.log")

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
# 外壳
# ----------------------------------------------------------------------
class Shell:
    def __init__(self, *, silent: bool = False, debug: bool = False) -> None:
        self.silent = silent
        self.debug = debug
        self.port = _free_port()
        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.window = None
        self.tray = None
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
        """点窗口 X：隐藏到托盘，不退出。返回 False 取消关闭。"""
        if self._quitting:
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
        try:
            if self.tray is not None:
                self.tray.notify("MK87 Studio 仍在系统托盘运行，右键托盘图标可退出。", "MK87 Studio")
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

    def _refresh_tray(self) -> None:
        try:
            if self.tray is not None:
                self.tray.update_menu()
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------- 退出
    def quit(self) -> None:
        """托盘「退出」：停后台任务 → 停服务 → 关窗口/托盘 → 进程退出（幂等）。

        注意：可能从托盘线程 / HTTP 定时器线程调用，而 pywebview 的窗口 API
        必须在 GUI 主线程使用，因此清理动作放到独立线程并设超时，最后
        os._exit 兜底，保证「点了退出就一定能退干净」。
        """
        if self._quitting:
            return
        self._quitting = True
        log.info("开始退出…")

        def _cleanup() -> None:
            try:
                self.manager.tft_job.cancel()
            except Exception:  # noqa: BLE001
                pass
            for stopper in ("music", "keytest"):
                try:
                    getattr(self.manager, stopper).stop()
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
                if self.tray is not None:
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
        t.join(timeout=6)
        # 兜底：清理线程卡住也强制退出（进程退出即释放托盘/窗口/端口）
        log.warning("清理超时，强制退出")
        os._exit(0)

    # ---------------------------------------------------------- 主流程
    def run(self) -> int:
        self.start_server()
        from server import app as server_app  # noqa: PLC0415

        server_app.activate_callback = self.show_window
        server_app.quit_callback = self.quit
        self.manager.shell_mode = True
        self.wait_ready()
        SingleInstance().write_port(self.port)

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

        self._build_tray()
        threading.Thread(target=self.tray.run, name="mk87-tray", daemon=True).start()

        webview.start(debug=self.debug)
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="MK87 Studio 桌面外壳")
    ap.add_argument("--tray", action="store_true", help="静默启动到系统托盘（开机自启用）")
    ap.add_argument("--debug", action="store_true", help="打开 WebView 开发者工具")
    ap.add_argument("--no-single-instance", action="store_true", help="跳过单实例检查（调试用）")
    args = ap.parse_args()
    setup_logging()

    if not args.no_single_instance:
        if not SingleInstance().acquire():
            log.info("已有实例在运行，尝试唤起…")
            if _activate_existing():
                return 0
            log.warning("未找到已有实例端口，继续启动新实例")

    shell = Shell(silent=args.tray, debug=args.debug)
    try:
        return shell.run()
    except Exception:  # noqa: BLE001
        log.exception("外壳启动失败")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
