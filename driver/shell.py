#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MK87 Studio 原生桌面外壳（方案 B）。

行为（用户要求）：
* 独立应用窗口（pywebview + WebView2 / Qt WebEngine），不打开浏览器、不暴露端口；
* 点窗口 X **不退出**，隐藏到系统托盘继续运行；
* 例外（v0.1.8）：当前桌面没有托盘宿主时，点 X 直接退出程序，避免窗口藏起来找不回；
  v0.1.8.6 Windows：托盘图标创建/注册失败时**不隐藏窗口**，改为最小化并提示原因
  （「关窗即隐身」正是用户报告「托盘消失」的来源，见下方托盘看门狗说明）；
* 托盘：左键显示主窗口；右键菜单 = 显示主窗口 / 开机自启(勾选) / **退出**；
  Windows 用 pystray，Linux 用 Qt `QSystemTrayIcon`（pystray 的 Linux xorg 后端没有右键菜单）；
* 托盘「退出」会完整关闭：停后台任务 → 停服务 → 关窗口/托盘 → 进程退出；
* 开机自启：`--tray` 参数静默启动到托盘；
* 单实例：重复启动时唤起已有窗口并**确定性退出**本进程。唤起失败绝不静默变成
  第二个实例（那会留下重复托盘图标/隐藏实例），而是弹 Windows MessageBox 明确告知
  用户去哪里找窗口；日志记录每一次尝试与结果；
* Windows 托盘看门狗（v0.1.8.6）：`Shell_NotifyIconGetRect` 探测图标是否真的注册在
  通知区域里；图标丢失（Explorer 崩溃/重启、通知区域异常）时重建 pystray 图标，
  重建失败则把托盘状态降级为「不可用」，关窗改为最小化而不是隐藏。首次隐藏到托盘
  时发一次气泡，提示图标可能被收进「显示隐藏的图标」。

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

from mk87lib import autostart, bootlog, tray_win  # noqa: E402

APP_NAME = "MK87 Studio"
#: 命名互斥量（无前缀 = 当前登录 Session 内可见，等价于 ``Local\``）。
#: 保持旧名字不变，这样新版本仍能识别正在运行的旧版实例。
LOCK_NAME = "MK87Studio.SingleInstance"
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache"), "mk87")
LOG_PATH = os.path.join(LOG_DIR, "shell.log")

#: 单实例唤起（POST /api/activate）的超时与重试：短超时，避免重复启动时卡住启动器。
ACTIVATE_TIMEOUT = 1.5
ACTIVATE_ATTEMPTS = 3
#: 重试间隔（秒）：每次重试都会重新读一次 instance.json，覆盖「已有实例正在启动、
#: 端口还没写进文件」的窗口期。
ACTIVATE_RETRY_DELAY = 0.6

#: Windows MessageBox 图标/置顶标志
_MB_ICONINFORMATION = 0x00000040
_MB_SETFOREGROUND = 0x00010000
_MB_TOPMOST = 0x00040000

#: faulthandler 的崩溃日志文件句柄（必须保持引用，否则会被 GC 关闭）
_crash_fh = None

log = logging.getLogger("mk87.shell")


# ----------------------------------------------------------------------
# 单实例
# ----------------------------------------------------------------------
class _WinKernel32:
    """kernel32 的最小封装（正确声明 HANDLE，避免 64 位句柄被截断）。"""

    def __init__(self) -> None:
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_wchar_p]
        self._k32.CreateMutexW.restype = ctypes.c_void_p
        self._k32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._k32.CloseHandle.restype = ctypes.c_int

    def create_mutex(self, name: str):
        """返回 (handle, already_exists)。"""
        handle = self._k32.CreateMutexW(None, False, name)
        return handle, ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS

    def close(self, handle) -> None:
        try:
            if handle:
                self._k32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            pass


_WIN_KERNEL32: _WinKernel32 | None = None


def _win_kernel32() -> _WinKernel32:
    global _WIN_KERNEL32
    if _WIN_KERNEL32 is None:
        _WIN_KERNEL32 = _WinKernel32()
    return _WIN_KERNEL32


class SingleInstance:
    """Windows 命名互斥量 / Linux 文件锁；锁文件里记录已运行实例的端口。

    Windows 用 ``MK87Studio.SingleInstance``（无前缀 = 当前 Session 命名空间，
    等价于 ``Local\\``）：同一用户 Session 只允许一个实例，快速切换用户时其它
    Session 仍可各跑一个。互斥量句柄必须**由进程一直持有**，不能只拿临时对象的
    返回值（早期版本的句柄一旦被 CloseHandle 就会静默失效，导致多实例）。
    """

    def __init__(self, directory: str | None = None) -> None:
        self._mutex = None
        self._fh = None
        self._kernel32 = None
        self._directory = directory or LOG_DIR
        self.lock_file = os.path.join(self._directory, "instance.json")

    @property
    def directory(self) -> str:
        return self._directory

    def acquire(self, *, platform: str | None = None, kernel32=None) -> bool:
        try:
            os.makedirs(self._directory, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        if (platform or sys.platform) == "win32":
            try:
                k32 = kernel32 or _win_kernel32()
                self._kernel32 = k32
                handle, already = k32.create_mutex(LOCK_NAME)
                if already:
                    # 关掉我们这次打开的同名句柄；互斥量仍归已有实例持有。
                    try:
                        k32.close(handle)
                    except Exception:  # noqa: BLE001
                        pass
                    return False
                self._mutex = handle
                return True
            except Exception as exc:  # noqa: BLE001
                # 互斥量不可用时不能把用户挡在外面：退化为端口探测（至少写日志）
                log.warning("创建单实例互斥量失败（退化为端口探测）: %s", exc)
                bootlog.mark("single-instance-mutex-error", error=exc)
                return True
        try:
            import fcntl

            self._fh = open(os.path.join(self._directory, "instance.lock"), "w")
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except Exception:  # noqa: BLE001
            return False

    def release(self) -> None:
        """释放互斥量/文件锁（正常退出其实靠进程退出即可，这里主要给单测用）。"""
        if self._mutex is not None:
            try:
                (self._kernel32 or _win_kernel32()).close(self._mutex)
            except Exception:  # noqa: BLE001
                pass
            self._mutex = None
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001
                pass
            self._fh = None

    def write_port(self, port: int) -> None:
        """把本实例端口写入 instance.json（旧版本只读取 ``port`` 字段）。"""
        try:
            with open(self.lock_file, "w", encoding="utf-8") as f:
                json.dump({"port": int(port), "pid": os.getpid(),
                           "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
        except Exception:  # noqa: BLE001
            pass

    def read_info(self) -> dict:
        try:
            with open(self.lock_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def read_port(self) -> int | None:
        info = self.read_info()
        try:
            return int(info.get("port") or 0) or None
        except Exception:  # noqa: BLE001
            return None


#: 一直持有单实例锁的全局对象（互斥量要活到进程退出，不能只拿临时对象）。
_INSTANCE: SingleInstance | None = None


def _acquire_single_instance() -> SingleInstance | None:
    """获取单实例锁；成功返回持有者对象，失败（已有实例）返回 None。"""
    global _INSTANCE
    instance = SingleInstance()
    if not instance.acquire():
        return None
    _INSTANCE = instance
    return instance


def _release_single_instance() -> None:
    """释放单实例锁（单测/调试用；正常退出交给进程退出释放）。"""
    global _INSTANCE
    if _INSTANCE is not None:
        try:
            _INSTANCE.release()
        except Exception:  # noqa: BLE001
            pass
        _INSTANCE = None


def _read_instance_port(instance: SingleInstance | None = None) -> int | None:
    try:
        return (instance or _INSTANCE or SingleInstance()).read_port()
    except Exception:  # noqa: BLE001
        return None


def _post_activate(port: int, timeout: float = ACTIVATE_TIMEOUT) -> tuple[bool, dict]:
    """POST /api/activate 并解析响应；任何失败都折成 (False, info)，不抛异常。

    v0.1.8.6 修复：旧代码只看「HTTP 没抛异常」就当作唤起成功 —— 但
    ``/api/activate`` 在无窗口外壳（浏览器模式）或 GUI 线程出问题时仍返回 HTTP 200
    且 body 是 ``{"ok": false}``，导致重复启动静默退出却什么也没发生。
    """
    import urllib.request

    info: dict = {"port": int(port), "status": None, "body": None,
                  "error": None, "url": f"http://127.0.0.1:{int(port)}/api/activate"}
    try:
        req = urllib.request.Request(info["url"], data=b"{}",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=max(0.1, float(timeout))) as resp:
            info["status"] = int(getattr(resp, "status", 0) or 0)
            raw = resp.read(4096).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
        return False, info

    try:
        body = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        body = None
    info["body"] = body if isinstance(body, dict) else raw[:300]
    if info["status"] != 200:
        info["error"] = f"HTTP {info['status']}"
        return False, info
    if not isinstance(body, dict):
        # 旧版/异常响应：HTTP 200 但非 JSON。当作已唤起（保持对旧版本兼容）。
        info["warning"] = "non-json-response"
        return True, info
    if body.get("ok") and body.get("activated") is not False:
        return True, info
    info["error"] = str(body.get("error") or body.get("message") or "activate-rejected")
    return False, info


def _activate_existing(*, port: int | None = None, attempts: int = ACTIVATE_ATTEMPTS,
                       timeout: float = ACTIVATE_TIMEOUT, sleep=None,
                       post=None, port_provider=None) -> tuple[bool, dict]:
    """唤起已在运行的实例，返回 ``(成功?, 诊断信息)``。

    短超时 + 重试：每次重试都重新读一次 instance.json（``port_provider``），
    覆盖「已有实例刚启动、端口还没写进文件」的窗口期。
    """
    do_sleep = sleep or time.sleep
    do_post = post or _post_activate
    get_port = port_provider or _read_instance_port
    info: dict = {"port": port, "attempts": 0, "reason": "", "lastError": None,
                  "results": []}
    tries = max(1, int(attempts))
    for index in range(tries):
        current = int(port) if port else get_port()
        info["attempts"] = index + 1
        if not current:
            info["lastError"] = "no-instance-port"
            if index + 1 < tries:
                do_sleep(ACTIVATE_RETRY_DELAY)
            continue
        info["port"] = int(current)
        ok, result = do_post(int(current), timeout)
        info["results"].append({"port": int(current), "ok": bool(ok),
                                "error": (result or {}).get("error")})
        info["lastError"] = (result or {}).get("error")
        if ok:
            info["reason"] = "activated"
            return True, info
        if index + 1 < tries:
            do_sleep(ACTIVATE_RETRY_DELAY)
    info["reason"] = info["lastError"] or "activate-failed"
    return False, info


def _probe_server_identity(port: int, timeout: float = 1.0) -> dict:
    """判断某端口上跑的是不是（能复用的）MK87 后端。"""
    import urllib.request

    info: dict = {"port": int(port), "match": False, "version": None, "error": None}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/api/version",
                                    timeout=max(0.1, float(timeout))) as resp:
            raw = resp.read(2048).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
        return info
    try:
        body = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        body = {}
    if not isinstance(body, dict):
        info["error"] = "non-json-version"
        return info
    info["version"] = body.get("version")
    if not info["version"]:
        info["error"] = "no-version-field"
        return info
    if body.get("mock"):
        info["error"] = "mock-server"
        return info
    platform = body.get("platform")
    if platform not in (None, os.name):
        info["error"] = f"foreign-platform:{platform}"
        return info
    info["match"] = True
    return info


def _message_box(text: str, caption: str = APP_NAME) -> None:
    """Windows 原生提示框；其它平台只写日志。任何失败都不抛（不能因为提示崩启动）。"""
    try:
        if sys.platform == "win32":
            flags = _MB_ICONINFORMATION | _MB_SETFOREGROUND | _MB_TOPMOST
            user32 = ctypes.windll.user32
            # 显式声明原型，确保 Python str 转成 wchar_t*（未声明时依赖 ctypes 推断，
            # 打包环境里出过参数被截断/乱码的案例）。
            try:
                user32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                               ctypes.c_wchar_p, ctypes.c_uint]
                user32.MessageBoxW.restype = ctypes.c_int
            except Exception:  # noqa: BLE001 - 已声明过/被 mock 时忽略
                pass
            user32.MessageBoxW(None, str(text), str(caption), flags)
        else:
            log.warning("%s", text)
    except Exception:  # noqa: BLE001
        log.warning("提示框显示失败（以下为原文）：%s", text)


def _prompt_existing_instance(info: dict | None = None) -> None:
    """唤起已有实例失败时，明确告诉用户去哪里找窗口（而不是静默退出/再起一个）。"""
    reason = str((info or {}).get("reason") or (info or {}).get("lastError") or "未知原因")
    text = (
        "MK87 Studio 已经在运行，但无法唤起它的窗口。\n\n"
        "1. 请在任务栏中找到 MK87 Studio 的窗口；\n"
        "2. 如果看不到窗口，请点开任务栏右下角的「显示隐藏的图标」，"
        "看看托盘图标是否在那里（可能被系统收进了溢出区）；\n"
        "3. 仍然找不到时：打开任务管理器 → 详细信息 → 结束 MK87Config 进程，"
        "然后重新启动本程序。\n\n"
        f"技术细节：{reason}"
    )
    bootlog.mark("prompt-existing-instance", reason=reason)
    try:
        _message_box(text)
    except Exception:  # noqa: BLE001 - 提示失败也不能影响退出决策
        log.warning("唤起失败提示框显示失败（忽略）：%s", reason)


def _handle_existing_instance(*, activate=None, prompt=None) -> int:
    """已有实例（互斥量被占用）时的退出码决策：唤起成功 → 0；失败 → 提示 + 2。

    关键：**任何情况下都不继续启动**。继续启动会留下第二个托盘图标/隐藏实例
    （v0.1.8.4 用户实机：3 次启动静默退出 + 多实例/托盘消失）。
    """
    do_activate = activate or _activate_existing
    ask = prompt or _prompt_existing_instance
    bootlog.mark("single-instance-activate-begin",
                 timeout=ACTIVATE_TIMEOUT, attempts=ACTIVATE_ATTEMPTS)
    log.info("已有实例在运行，尝试唤起…（超时 %.1fs，最多 %d 次）",
             ACTIVATE_TIMEOUT, ACTIVATE_ATTEMPTS)
    try:
        ok, info = do_activate()
    except Exception as exc:  # noqa: BLE001
        log.exception("唤起已有实例时出现异常")
        ok, info = False, {"reason": f"{type(exc).__name__}: {exc}"}
    if ok:
        bootlog.mark("single-instance-activated", port=info.get("port"),
                     attempts=info.get("attempts"))
        log.info("已唤起正在运行的实例（端口 %s，第 %s 次尝试），本进程确定性退出",
                 info.get("port"), info.get("attempts"))
        return 0
    bootlog.mark("single-instance-activate-failed", reason=info.get("reason"),
                 port=info.get("port"), attempts=info.get("attempts"),
                 lastError=info.get("lastError"))
    log.error("唤起已有实例失败（%s）：不启动第二个实例，改为提示用户窗口/托盘位置",
              info.get("reason") or info.get("lastError"))
    try:
        ask(info)
    except Exception:  # noqa: BLE001
        log.warning("提示用户失败（忽略）", exc_info=True)
    return 2


def _reuse_running_instance_if_any(instance: SingleInstance | None = None, *,
                                   probe=None, activate=None, prompt=None) -> int | None:
    """互斥量拿到手后的旧实例兜底：端口文件里的实例若真的活着就复用它。

    v0.1.8.6 之前部分版本的单实例句柄可能没有活到进程退出（或用户在调试时
    ``--no-single-instance`` 起过实例）。如果 instance.json 指向的端口确实响应
    且身份匹配（/api/version），说明有旧实例在跑 —— 唤起它，而不是再起第二个。

    :returns: 0/2 = 已处理（本进程应退出）；None = 没有可复用实例，继续正常启动。
    """
    try:
        port = instance.read_port() if instance is not None else _read_instance_port()
    except Exception:  # noqa: BLE001
        port = None
    if not port:
        return None
    ident = {}
    try:
        ident = (probe or _probe_server_identity)(int(port)) or {}
    except Exception as exc:  # noqa: BLE001
        ident = {"match": False, "error": f"{type(exc).__name__}: {exc}"}
    if not ident.get("match"):
        bootlog.mark("single-instance-stale-port", port=port, reason=ident.get("error"))
        log.info("instance.json 的端口 %s 没有响应或不是 MK87（%s），按新实例启动",
                 port, ident.get("error"))
        return None
    bootlog.mark("single-instance-legacy-alive", port=port, version=ident.get("version"))
    log.warning("检测到未持有单实例互斥量的旧实例（端口 %s，版本 %s），"
                "尝试唤起它而不是再起一个", port, ident.get("version"))
    try:
        ok, info = (activate or _activate_existing)(port=int(port))
    except Exception as exc:  # noqa: BLE001
        ok, info = False, {"reason": f"{type(exc).__name__}: {exc}"}
    if ok:
        bootlog.mark("single-instance-activated-legacy", port=port)
        log.info("已唤起旧实例（端口 %s），本进程确定性退出", port)
        return 0
    bootlog.mark("single-instance-legacy-activate-failed", port=port,
                 reason=info.get("reason"))
    log.error("旧实例（端口 %s）无法唤起：%s", port, info.get("reason"))
    try:
        (prompt or _prompt_existing_instance)(info)
    except Exception:  # noqa: BLE001
        pass
    return 2


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
# Windows 托盘看门狗（图标丢失 / Explorer 重启后自愈）
# ----------------------------------------------------------------------
class TrayWatchdog:
    """检测 Windows 托盘图标是否真的注册在通知区域，丢失时重建 pystray 图标。

    为什么需要（2026-11-07 实机证据）：用户实例 PID 13212 的 pystray 消息循环还活着、
    ``/api/tray/status`` 也返回 ``available=true``，但 ``Shell_NotifyIconGetRect`` 对它的
    图标窗口返回 ``E_FAIL`` —— 图标根本不在通知区域里。用户点窗口 X 后窗口被隐藏
    （boot log ``[window-closing] available=True``），应用就再也找不回来了，也就是
    用户报告的「托盘消失」。所以「有 Icon 对象」不能当作「图标显示着」，必须实测。

    状态机（每 ``interval`` 秒一拍）：
    * 任务栏不在（Explorer 正在重启）→ ``no-taskbar``，不动；
    * 探测失败/还没有图标窗口 → ``unknown``，**不重建**（避免误判出重复图标）；
    * ``visible`` / ``hidden`` → ``ok``。``hidden`` = 图标已注册但被系统收进
      「显示隐藏的图标」溢出区（``Shell_NotifyIconGetRect`` 返回 S_FALSE）——
      这是 Windows 默认行为，**不能**当成丢失去重建；
    * 连续 ``missing_threshold`` 拍 ``missing``（GetRect 返回 E_FAIL）→ 先做一次
      轻量 **NIM_ADD 重加**（同一个 hWnd/uID 不会产生重复图标；GetRect 偶尔查不到时
      这一步能自愈）；仍查不到才重建 pystray 图标（有节流与次数上限）；重建用尽
      仍注册不上才最终判定「托盘不可用」（关窗降级为最小化）。
    """

    INTERVAL = 2.0

    def __init__(self, shell, *, interval: float | None = None, missing_threshold: int = 2,
                 rebuild_interval: float = 15.0, max_rebuilds: int = 3,
                 max_readds: int = 1,
                 probe_env=None, probe_icon=None, rebuild=None, readd=None,
                 now=None) -> None:
        self.shell = shell
        self.interval = float(interval if interval is not None else self.INTERVAL)
        self.missing_threshold = max(1, int(missing_threshold))
        self.rebuild_interval = max(0.0, float(rebuild_interval))
        self.max_rebuilds = max(1, int(max_rebuilds))
        self.max_readds = max(0, int(max_readds))
        self._probe_env = probe_env or shell._tray_probe_environment
        self._probe_icon = probe_icon or shell._tray_probe_icon
        self._rebuild = rebuild or shell._rebuild_tray
        # Shell 一定有 _tray_readd_icon；测试用 fake shell 时可以没有（退化为直接重建）
        self._readd = readd or getattr(shell, "_tray_readd_icon", None)
        self._now = now or time.monotonic
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._token = None
        self._missing = 0
        self._rebuilds = 0
        self._readds = 0
        self._last_rebuild = 0.0
        self._action = "init"
        self._state = "unknown"
        self._detail: dict = {}

    # ------------------------------------------------------------ 线程
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="mk87-tray-watchdog",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except BaseException:  # noqa: BLE001
                log.debug("托盘看门狗单拍异常（忽略）", exc_info=True)
            self._stop.wait(self.interval)

    # ------------------------------------------------------------ 状态机
    @property
    def action(self) -> str:
        return self._action

    def snapshot(self) -> dict:
        return {"action": self._action, "iconState": self._state,
                "missingTicks": self._missing, "rebuilds": self._rebuilds,
                "readds": self._readds,
                "token": list(self._token) if self._token else None,
                "detail": dict(self._detail)}

    def _safe(self, fn, default):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001
            log.debug("托盘探测失败（忽略）: %s", exc)
            return default

    def _record(self, action: str, *, state: str | None = None,
                detail: dict | None = None) -> str:
        self._action = action
        if state is not None:
            self._state = state
        if detail is not None:
            self._detail = detail
        try:
            self.shell._tray_watch = self.snapshot()
        except Exception:  # noqa: BLE001
            pass
        return action

    def _do_rebuild(self, reason: str, *, now: float | None = None) -> str:
        current = self._now() if now is None else now
        self._rebuilds += 1
        self._last_rebuild = current
        self._missing = 0
        self._readds = 0  # 每重建一次，允许再尝试一次轻量重加
        bootlog.mark("tray-watchdog-rebuild", reason=reason, count=self._rebuilds)
        log.warning("托盘图标丢失（%s），重建 pystray 托盘（第 %d 次）", reason, self._rebuilds)
        ok = False
        try:
            ok = bool(self._rebuild(reason))
        except BaseException:  # noqa: BLE001
            log.exception("重建托盘图标失败（已降级，不影响主窗口）")
        if ok:
            self.shell._tray_icon_state = None  # 等下一拍探测确认
            return self._record("rebuilt", state="unknown", detail={"reason": reason})
        self.shell._tray_icon_state = "missing"
        return self._record("rebuild-failed", state="missing", detail={"reason": reason})

    def _do_readd(self) -> str:
        """轻量重加一次图标（NIM_ADD），不重建整个 pystray 对象。"""
        self._readds += 1
        self._missing = 0
        bootlog.mark("tray-watchdog-readd", count=self._readds)
        log.warning("托盘图标查询不到，先尝试重新注册一次（第 %d 次，不重建）", self._readds)
        if self._readd is None:
            return self._record("re-add-failed", state="unknown",
                                detail={"readds": self._readds,
                                        "error": "readd-not-available"})
        ok = False
        try:
            ok = bool(self._readd())
        except BaseException:  # noqa: BLE001
            log.exception("重新注册托盘图标失败（忽略，下一步会重建）")
        return self._record("re-add" if ok else "re-add-failed", state="unknown",
                            detail={"readds": self._readds})

    def tick(self, *, now: float | None = None):
        """执行一拍检测，返回动作字符串（单测直接调它，不启线程）。"""
        shell = self.shell
        if getattr(shell, "_quitting", False) or getattr(shell, "no_tray", False):
            return self._record("stopped")
        env = self._safe(self._probe_env, {}) or {}
        if not env.get("present"):
            self._missing = 0
            return self._record("no-taskbar", state="unknown",
                                detail={"taskbar": env.get("taskbarHwnd")})
        token = (env.get("taskbarHwnd"), env.get("shellHwnd"))
        if self._token is not None and token != self._token:
            # Explorer 重启/托盘宿主换了：图标多半被清空；清零计数后按正常流程探测。
            bootlog.mark("tray-environment-changed", old=list(self._token),
                         new=list(token))
            log.info("检测到任务栏变化（Explorer 重启？），重新确认托盘图标；"
                     "以前是 %s，现在是 %s", self._token, token)
            self._token = token
            self._rebuilds = 0
            self._readds = 0
            self._missing = 0
            self.shell._tray_rebuild_exhausted = False
        else:
            self._token = token
        result = self._safe(self._probe_icon, {"state": "unknown"}) or {}
        state = str(result.get("state") or "unknown")
        self._state = state
        if state in ("visible", "hidden"):
            self._missing = 0
            shell._tray_icon_state = state
            return self._record("ok", state=state, detail=result)
        if state != "missing":
            # 探测不了（没有 hwnd / API 失败）：绝不据此重建，避免误判重复图标。
            self._missing = 0
            return self._record("unknown", state=state, detail=result)
        self._missing += 1
        if self._missing < self.missing_threshold:
            return self._record("missing?", state=state, detail=result)
        # 第一步：先轻量重加（NIM_ADD），不重建。GetRect 查不到不等于真丢了
        # （可能只是溢出区/Explorer 恢复中），同一个 hWnd/uID 重加不会产生重复图标。
        if self._readds < self.max_readds:
            return self._do_readd()
        # 第二步：重加无效才重建（有节流/次数上限，失败才最终判定不可用）。
        current = self._now() if now is None else now
        if current - self._last_rebuild < self.rebuild_interval:
            return self._record("throttled", state=state, detail=result)
        if self._rebuilds >= self.max_rebuilds:
            shell._tray_icon_state = "missing"
            shell._tray_rebuild_exhausted = True
            return self._record("give-up", state="missing", detail=result)
        return self._do_rebuild("icon-missing", now=current)


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
        # ---- 托盘图标生命周期（v0.1.8.6）---------------------------------
        #: 是否尝试创建过托盘（创建失败 vs 从未创建 在关窗时行为不同）
        self._tray_attempted = False
        #: 图标实测状态：None=还没探测/重建中，visible/hidden/missing 见 tray_win
        self._tray_icon_state: str | None = None
        #: 启动时同步验证没成功（状态未确认）：关窗按「不可用」保守处理（只最小化）
        self._tray_verify_failed = False
        #: 看门狗重建次数用尽仍注册不上（此时才真算「托盘不可用」）
        self._tray_rebuild_exhausted = False
        #: 托盘错误原因（Windows 创建/重建失败、Linux Qt 不可用等）
        self._tray_error_text = ""
        #: 托盘线程（重建时需要停掉旧线程，避免留下孤儿图标）
        self._tray_thread: threading.Thread | None = None
        #: Windows 托盘看门狗
        self._tray_watchdog: TrayWatchdog | None = None
        self._tray_watch: dict = {}
        #: 首次隐藏气泡（只发一次）
        self._tray_tip_shown = False
        #: 托盘不可用关窗提示（每次运行只弹一次）
        self._tray_warn_shown = False

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
        """点窗口 X：托盘图标真的可用时隐藏到托盘；否则保持窗口可见（最小化）。

        Linux（v0.1.8 起）：没有托盘宿主时点 X = 退出程序（与设置页说明一致）。
        Windows（v0.1.8.6）：托盘图标创建/注册失败时**不能隐藏窗口** —— 用户报告的
        「托盘消失」正是窗口藏起来后再也没有图标可以找回。这时改为最小化 + 首次
        弹窗说明原因，并保留程序继续运行（设备/灯光状态不丢）。
        """
        if self._quitting:
            return True
        available = self._tray_available(wait=1.0)
        bootlog.mark("window-closing", available=available, backend=self._tray_backend,
                     no_tray=self.no_tray, iconState=self._tray_icon_state,
                     attempted=self._tray_attempted)
        if available is not True:
            if self._should_degrade_close():
                self._degrade_close_keep_window()
                return False
            log.warning("系统托盘不可用，关闭窗口 = 退出程序（%s）",
                        self._tray_error() or "无托盘宿主")
            self.quit()
            return True
        try:
            self.window.hide()
            self._notify_tray_running()
        except Exception:  # noqa: BLE001
            log.debug("隐藏窗口到托盘失败（忽略）", exc_info=True)
        return False

    def _should_degrade_close(self) -> bool:
        """Windows 且确实尝试过创建托盘但不可用 → 关窗应最小化而不是隐藏/退出。"""
        if sys.platform != "win32" or self.no_tray or not self._tray_attempted:
            return False
        return True

    def _degrade_close_keep_window(self) -> None:
        """托盘不可用时的关窗降级：最小化到任务栏（而不是隐藏），并告知原因。"""
        reason = self._tray_error() or (
            "托盘图标未注册（可能被系统收进溢出区或 Explorer 重启后未恢复）")
        bootlog.mark("window-close-degraded", reason=reason,
                     iconState=self._tray_icon_state,
                     watchdog=dict(self._tray_watch))
        log.warning("系统托盘不可用（%s）：窗口保持可见（最小化），不隐藏到托盘", reason)
        try:
            self.window.minimize()
        except Exception:  # noqa: BLE001
            log.debug("最小化窗口失败（忽略）", exc_info=True)
        if not self._tray_warn_shown:
            self._tray_warn_shown = True
            _message_box(
                "系统托盘图标当前不可用，窗口已最小化到任务栏（不会隐藏）。\n\n"
                f"原因：{reason}\n\n"
                "程序会在后台尝试恢复托盘图标；也可以在任务栏找到本窗口继续使用。"
            )

    def _notify_tray_running(self) -> None:
        """首次隐藏到托盘的气泡提示（只发一次；Windows 含『显示隐藏的图标』提示）。"""
        if self._tray_tip_shown:
            return
        self._tray_tip_shown = True
        message = "MK87 Studio 仍在系统托盘运行，右键托盘图标可退出。"
        hint = ""
        try:
            if sys.platform == "win32" and tray_win.auto_hide_enabled():
                hint = "图标可能在任务栏右下角的「显示隐藏的图标」里。"
        except Exception:  # noqa: BLE001
            hint = ""
        if hint:
            message = message + hint
        bootlog.mark("tray-first-hide-notify", overflowHint=bool(hint),
                     backend=self._tray_backend)
        try:
            if self._tray_backend == "qt":
                from mk87lib import tray_linux  # noqa: PLC0415

                tray_linux.notify("MK87 Studio", message)
            elif self.tray is not None:
                self.tray.notify(message, "MK87 Studio")
        except Exception:  # noqa: BLE001
            pass

    def show_window(self) -> None:
        """显示/激活主窗口（托盘左键、/api/activate、重复启动唤起都走这里）。"""
        if self.window is None:
            return
        try:
            self.window.show()
            self.window.restore()
        except Exception:  # noqa: BLE001
            log.debug("pywebview 显示/恢复窗口失败", exc_info=True)
        if sys.platform == "win32":
            # pywebview 的 show/restore 只负责把窗口恢复成普通状态；Windows 前台锁
            # （foreground lock）下窗口可能仍压在其它窗口后面，用户会觉得
            # 「重复启动没反应」。这里 best-effort 兜底，失败只降级为闪烁任务栏。
            try:
                result = tray_win.foreground_app_window(APP_NAME, os.getpid())
                bootlog.mark("window-foreground",
                             **{k: v for k, v in result.items() if k != "platform"})
            except Exception:  # noqa: BLE001
                log.debug("把窗口唤到前台失败（忽略）", exc_info=True)

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

    def _start_pystray(self) -> bool:
        """启动 pystray 托盘（Windows 默认；Linux 仅作 Qt 不可用时的兜底）。

        返回是否成功创建并启动；失败不抛出（主窗口仍可用，关窗时降级为最小化）。
        """
        self._tray_attempted = True
        try:
            self._build_tray()
        except BaseException as exc:  # noqa: BLE001
            self._tray_icon_state = "missing"
            self._tray_error_text = f"创建托盘失败: {exc}"
            bootlog.mark("tray-create-failed", error=str(exc))
            log.exception("创建 pystray 托盘失败（已降级：关窗将只最小化）")
            return False
        self._tray_icon_state = None
        self._tray_thread = threading.Thread(target=self.tray.run, name="mk87-tray",
                                             daemon=True)
        self._tray_thread.start()
        bootlog.mark("tray-pystray-started", thread=getattr(self._tray_thread, "name", ""))
        # Windows：图标可能被系统/Explorer 弄丢（pystray 的 TaskbarCreated 处理不总是
        # 生效），启动看门狗实测注册状态，丢了就重建。Linux 下该方法直接返回。
        self._start_tray_watchdog()
        if sys.platform == "win32":
            # 启动时同步确认一次图标是否注册成功（约 0.1~1.5s），避免在「还没确认」
            # 的窗口期里点 X 把窗口隐藏进一个不存在的托盘。
            self._verify_tray_icon()
        return True

    def _verify_tray_icon(self, wait: float = 2.5) -> str | None:
        """启动时同步确认托盘图标注册状态（Windows）；返回 visible/hidden/None。

        注意：这里**不会**因为一次 GetRect 失败就断言「图标未注册」——图标在溢出区、
        Explorer 正在启动、或注册稍慢都可能让查询暂时失败。未确认时只把
        ``_tray_verify_failed`` 置 True（关窗改为保守最小化），真正的「不可用」
        由看门狗连续多次探测 + NIM_ADD 重加 + 重建之后才判定。
        """
        deadline = time.time() + max(0.0, float(wait))
        while time.time() < deadline and not self._quitting:
            result = self._tray_probe_icon()
            state = result.get("state")
            if state in ("visible", "hidden"):
                self._tray_icon_state = state
                self._tray_verify_failed = False
                bootlog.mark("tray-verify-ok", state=state,
                             hwnd=result.get("hwnd"), uID=result.get("uID"))
                return state
            time.sleep(0.1)
        # 超时：不判死。保留「未确认」状态，看门狗会继续探测并尝试恢复。
        self._tray_verify_failed = True
        bootlog.mark("tray-verify-unconfirmed", hwnd=self._tray_icon_hwnd(),
                     last=str(self._tray_probe_icon().get("state")))
        log.warning("启动时未能确认托盘图标已显示（不判死，看门狗继续恢复）；"
                    "在确认之前关闭窗口只会最小化，不会隐藏")
        return None

    def _tray_readd_icon(self) -> bool:
        """重新 NIM_ADD 一次托盘图标（pystray 的 visible 切换）。

        为什么先重加而不是直接重建：``Shell_NotifyIconGetRect`` 在少数状态
        （图标在溢出区/Explorer 刚重启）可能查不到。用同一个 hWnd/uID 重新
        NIM_ADD 不会产生重复图标：图标若还在只是刷新，真丢了就重新注册。
        失败（pystray 还没 running 等）只降级，交给看门狗下一步重建。
        """
        tray = self.tray
        if tray is None:
            return False
        try:
            try:
                tray.visible = False
            finally:
                tray.visible = True
            bootlog.mark("tray-readd-ok")
            log.info("已重新注册托盘图标（NIM_ADD）")
            return True
        except Exception as exc:  # noqa: BLE001
            bootlog.mark("tray-readd-error", error=str(exc))
            log.debug("重新注册托盘图标失败（忽略）: %s", exc)
            return False

    def _start_silent_window_guard(self) -> None:
        """`--tray` 静默启动时，若托盘不可用则自动把窗口显示出来。

        场景：开机自启（``--tray``）窗口 hidden=True；如果托盘图标没有创建/注册成功，
        用户既看不到窗口也看不到托盘图标，只能去任务管理器杀进程 —— 这也是用户报告
        「托盘消失」的一种形态。这里延迟几秒等托盘状态确定后兜底显示窗口。
        """
        if sys.platform != "win32" or not self.silent or self.no_tray:
            return
        try:
            threading.Thread(target=self._silent_window_guard,
                             name="mk87-silent-guard", daemon=True).start()
        except Exception:  # noqa: BLE001
            log.debug("启动静默启动兜底线程失败（忽略）", exc_info=True)

    def _silent_window_guard(self, wait: float = 8.0, interval: float = 0.5) -> None:
        """等托盘状态稳定后检查：静默启动但托盘不可用 → 显示主窗口并说明原因。

        多轮轮询（而不是只查一次）：看门狗可能在启动后几秒内就重建好图标，不能因为
        一次探测失败就弹窗打扰用户。只有整个 ``wait`` 窗口内都没确认可用才兜底显示。
        """
        deadline = time.time() + max(0.0, float(wait))
        while not self._quitting:
            if self._tray_available() is True:
                bootlog.mark("silent-tray-ok", state=self._tray_icon_state)
                return
            if time.time() >= deadline:
                break
            try:
                time.sleep(max(0.02, float(interval)))
            except Exception:  # noqa: BLE001
                return
        if self._quitting or not self.silent or self.no_tray:
            return
        bootlog.mark("silent-tray-unavailable-show-window",
                     available=self._tray_available(), state=self._tray_icon_state,
                     verifyFailed=self._tray_verify_failed,
                     rebuilds=dict(self._tray_watch).get("rebuilds"))
        log.warning("静默启动（--tray）但托盘暂不可用，改为显示主窗口，避免应用隐身")
        self.show_window()
        if not self._tray_warn_shown:
            self._tray_warn_shown = True
            _message_box(
                "MK87 Studio 以「静默启动到托盘」方式启动，但暂时无法确认系统托盘图标"
                "已经显示，已改为直接显示主窗口。\n\n"
                f"状态：{self._tray_error() or '托盘图标状态未确认'}\n\n"
                "程序会在后台继续尝试恢复托盘图标；也可以右键任务栏通知区域，"
                "点「显示隐藏的图标」看看图标是否在那里。"
            )

    # ---------------------------------------------- 托盘看门狗（仅 Windows）
    def _tray_icon_hwnd(self) -> int:
        """当前 pystray 图标窗口句柄（拿不到时返回 0）。"""
        try:
            return int(getattr(self.tray, "_hwnd", 0) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _tray_probe_environment(self) -> dict:
        """任务栏（Explorer）是否存在及其句柄快照（Windows 看门狗用）。"""
        return tray_win.environment()

    def _tray_probe_icon(self) -> dict:
        """实测 pystray 图标是否注册在通知区域。

        uID 候选：0 是 pystray 0.19.x 的真实值（``hID`` 关键字被 ctypes 忽略，见
        ``tray_win`` 模块头注释）；``id(tray)`` 兼容将来修好该 bug 的版本。
        """
        tray = self.tray
        if tray is None:
            return {"state": "missing" if self._tray_attempted else "unknown",
                    "error": "no-tray-object"}
        hwnd = self._tray_icon_hwnd()
        candidates = [hwnd] if hwnd else []
        if not candidates and not self._quitting:
            # pystray 线程可能还没把 _hwnd 挂上：枚举本进程的托图标窗口兜底。
            try:
                found = tray_win.find_icon_hwnds(pid=os.getpid(), name="mk87studio")
            except Exception:  # noqa: BLE001
                found = []
            candidates = [int(item.get("hwnd") or 0) for item in found]
        if not candidates:
            # pystray 线程还没建好窗口：状态未知，看门狗不会据此重建。
            return {"state": "unknown", "error": "no-icon-window"}
        u_ids = [0, id(tray)]  # 0=pystray 实际 uID；id 兼容未来修复的版本
        best: dict | None = None
        for candidate in candidates:
            try:
                result = tray_win.probe_icon(candidate, u_ids=u_ids)
            except Exception as exc:  # noqa: BLE001
                result = {"state": "unknown", "hwnd": candidate,
                          "error": f"{type(exc).__name__}: {exc}"}
            if best is None or (result.get("registered") and not best.get("registered")):
                best = result
            if result.get("registered"):
                return result
        return best or {"state": "unknown", "error": "probe-failed"}

    def _stop_tray_icon(self, icon, thread=None, timeout: float = 2.0) -> None:
        """停掉一个 pystray 图标（重建前必须先删除旧图标，避免留下重复图标）。"""
        if icon is None:
            return
        try:
            icon.stop()
        except Exception:  # noqa: BLE001
            pass
        if thread is None:
            return
        try:
            if thread.is_alive():
                thread.join(timeout)
        except Exception:  # noqa: BLE001
            pass

        def _late_stop() -> None:
            # pystray 的 stop() 在消息循环启动前调用是空操作：轮询到它真正 running
            # 再停一次，避免旧图标一直留在通知区域。
            for _ in range(100):
                try:
                    if getattr(icon, "_running", False) or getattr(icon, "visible", False):
                        icon.stop()
                        return
                except Exception:  # noqa: BLE001
                    return
                time.sleep(0.1)

        try:
            if thread.is_alive():
                threading.Thread(target=_late_stop, name="mk87-tray-late-stop",
                                 daemon=True).start()
        except Exception:  # noqa: BLE001
            pass

    def _rebuild_tray(self, reason: str = "") -> bool:
        """重建 pystray 托盘图标（图标丢失/Explorer 重启后恢复）。失败只降级不崩。"""
        if self._quitting or self.no_tray:
            return False
        bootlog.mark("tray-rebuild-begin", reason=reason)
        old_icon, old_thread = self.tray, self._tray_thread
        self.tray = None
        self._tray_icon_state = "rebuilding"
        self._stop_tray_icon(old_icon, old_thread)
        if self._quitting:
            return False
        try:
            self._build_tray()
            self._tray_thread = threading.Thread(target=self.tray.run, name="mk87-tray",
                                                 daemon=True)
            self._tray_thread.start()
        except BaseException as exc:  # noqa: BLE001
            self.tray = None
            self._tray_icon_state = "missing"
            self._tray_error_text = f"重建托盘失败: {exc}"
            bootlog.mark("tray-rebuild-failed", error=str(exc))
            log.exception("重建 pystray 托盘失败（已降级：关窗只最小化）")
            return False
        self._tray_error_text = ""
        bootlog.mark("tray-rebuild-started", reason=reason)
        log.info("已重建托盘图标（%s）", reason or "原因未标注")
        return True

    def _start_tray_watchdog(self) -> None:
        """Windows：启动托盘图标看门狗（其它平台/禁用托盘时不启动）。"""
        if sys.platform != "win32" or self.no_tray:
            return
        try:
            self._tray_watchdog = TrayWatchdog(self)
            self._tray_watchdog.start()
            bootlog.mark("tray-watchdog-started", interval=self._tray_watchdog.interval)
        except BaseException:  # noqa: BLE001
            log.exception("启动托盘看门狗失败（忽略，托盘仍可用）")

    def tray_diagnostics(self) -> dict:
        """托盘诊断快照（Lead 可接进 /api/tray/status 与设置页；非 Windows 返回 supported=False）。"""
        try:
            info = tray_win.probe(tray=self.tray, pid=os.getpid())
        except Exception as exc:  # noqa: BLE001
            info = {"supported": tray_win.supported(),
                    "error": f"{type(exc).__name__}: {exc}"}
        info["backend"] = self._tray_backend
        info["iconState"] = self._tray_icon_state
        info["errorText"] = self._tray_error_text or None
        info["watchdog"] = dict(self._tray_watch)
        info["attempted"] = self._tray_attempted
        return info

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
        """当前托盘图标是否真的可用（None = 还不知道/正在创建）。

        与旧实现的区别（v0.1.8.6）：Windows 不再只看「有没有 pystray.Icon 对象」，
        而是看看门狗实测的图标注册状态。``self.tray`` 存在但还没探测过时保持乐观
        （返回 True），探测到 missing 后返回 False —— 关窗据此决定隐藏还是最小化。
        """
        if self.no_tray:
            return False
        if self._tray_backend == "pystray":
            if self.tray is None:
                # 尝试过创建但失败 → 明确不可用；从未尝试（异常/单测合成状态）→ 未知
                return False if self._tray_attempted else None
            state = self._tray_icon_state
            if state in ("visible", "hidden"):
                return True
            if state in ("missing", "rebuilding"):
                return False
            if self._tray_verify_failed:
                # 启动时没能确认图标真的显示：关窗保守地最小化，而不是隐藏。
                return False
            return True  # 还没探测（启动后约 2s 内）：乐观处理，保持旧行为
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
        if self._tray_error_text:
            return self._tray_error_text
        # Qt 后端（Linux）的错误在 tray_linux.STATE 里；pystray 后端走下面的通用文案，
        # 避免 Linux 上 pystray 兜底时读到无关的 Qt 错误。
        if self._tray_backend == "qt" or (
                self._tray_backend is None and sys.platform.startswith("linux")):
            from mk87lib import tray_linux  # noqa: PLC0415

            return str(tray_linux.STATE.get("error") or "")
        if self._tray_rebuild_exhausted:
            return "系统托盘图标不可用（已多次重建仍未注册成功）"
        if self._tray_icon_state in ("missing", "rebuilding"):
            # 注意措辞：单次 GetRect 失败不等于没注册（可能只是溢出/Explorer 恢复中），
            # 这里只说「暂时不可用、正在恢复」，避免误导用户。
            return "托盘图标暂时不可用（可能被系统收进「显示隐藏的图标」或正在自动恢复）"
        if self._tray_verify_failed:
            return "启动时未能确认托盘图标已显示（可能被系统收进了「显示隐藏的图标」）"
        return ""

    def tray_state(self) -> dict:
        """注入 server.app 的托盘状态（/api/status 与 /api/tray/status 使用）。"""
        shell_mode = bool(getattr(getattr(self, "manager", None), "shell_mode", False))
        if self._tray_backend == "pystray":
            state = self._tray_icon_state
            if state in ("visible", "hidden"):
                available: bool | None = True
            elif state in ("missing", "rebuilding"):
                available = False
            elif self.tray is None and self._tray_attempted:
                available = False
            elif self._tray_verify_failed:
                available = False  # 启动时没确认图标显示：按不可用上报（关窗只最小化）
            else:
                available = None  # 启动早期/还没探测
            return {
                "available": available,
                "backend": "pystray",
                # 供前端/诊断区分的细节（Lead 接线 /api/tray/status 时可直接用）
                "iconState": state,
                "iconRegistered": state in ("visible", "hidden"),
                "overflow": state == "hidden",
                "watchdog": dict(self._tray_watch),
                "error": self._tray_error() or None,
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
        try:
            if self._tray_watchdog is not None:
                self._tray_watchdog.stop()
        except Exception:  # noqa: BLE001
            pass
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
        # 托盘深度诊断（Windows：GetRect/溢出区/看门狗状态）。Lead 的
        # /api/tray/status 若接这个回调就能拿到 tray_win.probe() 的完整 dict。
        server_app.tray_diagnostics_callback = self.tray_diagnostics
        self.manager.shell_mode = True
        self.wait_ready()
        # 端口写进 instance.json 供「重复启动唤起」使用；单实例锁对象由 main() 持有。
        try:
            (_INSTANCE or SingleInstance()).write_port(self.port)
        except Exception:  # noqa: BLE001
            log.warning("写入 instance.json 失败（重复启动唤起可能不可用）", exc_info=True)
        self._start_stall_watchdog()
        bootlog.mark("server-ready", port=self.port)

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
                # --tray 静默启动 + 托盘失败时，别让应用彻底隐身（Windows）。
                self._start_silent_window_guard()
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

    # 音乐律动长时间运行会因系统「连接待机 / EcoQoS 能效节流」导致 HID 写入挂起、帧流卡死。
    # 启动早期就关闭 Windows 进程能效节流并记录平台能力（其它平台为空操作，失败只忽略）。
    try:
        from mk87lib import powerkeep  # noqa: PLC0415

        _throttle_ok = powerkeep.opt_out_power_throttling()
        bootlog.mark("power-throttle-optout", ok=bool(_throttle_ok),
                     report=powerkeep.platform_report())
    except Exception:  # noqa: BLE001
        log.debug("关闭进程能效节流失败（忽略）", exc_info=True)

    if args.diagnose:
        return _run_diagnose()

    if not args.no_single_instance:
        instance = _acquire_single_instance()
        if instance is None:
            bootlog.mark("single-instance-existing")
            # 唤起成功 → 确定性退出（0）；失败 → 弹窗告知用户 + 退出（2）。
            # 绝不再「继续启动新实例」：那会留下第二个托盘图标/隐藏实例。
            return _handle_existing_instance()
        bootlog.mark("single-instance-acquired", pid=os.getpid())
        # 兜底：旧版本实例可能没把互斥量句柄保活。若 instance.json 指向的实例
        # 确实还活着（/api/version 身份匹配），复用/唤起它而不是再起一个。
        reused = _reuse_running_instance_if_any(instance)
        if reused is not None:
            return reused
    else:
        bootlog.mark("single-instance-skipped")

    shell = Shell(silent=args.tray, debug=args.debug, no_tray=args.no_tray)
    try:
        return shell.run()
    except BaseException:  # noqa: BLE001
        bootlog.mark("shell-run-failed")
        log.exception("外壳启动失败")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
