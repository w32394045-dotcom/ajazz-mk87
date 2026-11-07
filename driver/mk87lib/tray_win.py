#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 托盘诊断（纯标准库 + 可选 ctypes，不依赖真实托盘）。

背景
----
2026-11-07 用户实机报告「Windows 托盘消失」。实测证据（只读探测，PID 13212，
dev build 0.1.8.2，端口 65447）：

* ``/api/tray/status`` 返回 ``available=true backend=pystray``；
* 但用 ``Shell_NotifyIconGetRect`` 查它的 pystray 图标窗口 → ``E_FAIL``
  （图标根本不在通知区域里注册），也就是说「有 Icon 对象」≠「图标真的显示着」；
* 用户随后点窗口 X（boot log ``[window-closing] available=True``）→ 窗口被隐藏，
  而托盘图标又不存在 → 应用彻底找不回来（用户看到的「托盘消失」）。

本模块只做**只读探测**，把「图标到底注册没有 / 在不在『显示隐藏的图标』溢出区 /
任务栏（Explorer）是否换了」变成可测试的 dict，供：

* ``shell.py`` 的托盘看门狗（图标丢失/Explorer 重启后重建）；
* ``/api/tray/status`` 与设置页「系统托盘」卡片（Lead 接线）；
* 诊断包导出。

设计约束
--------
* import 安全：Linux/macOS 上也能 import（单测矩阵 Windows + Ubuntu 都跑）；
* 绝不向外抛异常：任何探测失败都折成 dict 里的 ``error`` 字段；
* 所有 Win32 访问集中在一个 ``Win32Api`` 包装里，单测可注入 fake 对象；
* 只读：只调用 FindWindow/GetShellWindow/GetClassName/EnumWindows/
  Shell_NotifyIconGetRect 等查询 API；唯一会改窗口状态的是
  :func:`foreground_app_window`（唤起窗口失败时兜底），由 shell 显式调用。

一个 pystray 的坑（2026-11-07 实测）
------------------------------------
pystray 0.19.5 的 ``_win32.py`` 里 ``NOTIFYICONDATAW(..., hID=id(self), ...)``：
结构体字段实际叫 ``uID``，``hID`` 是非法的关键字参数，而 ctypes 会**静默忽略**
未知关键字 —— 所以 pystray 图标注册时的 uID 恒为 0，窗口类名里那个
``mk87studio<id>SystemTrayIcon`` 数字只是 ``id(self)``，**不能**当 uID 用。
因此 :func:`probe_icon` 默认按 ``uID=0`` 查，同时保留「按 id 猜」的候选以兼容
将来修好这个 bug 的 pystray 版本。
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# ctypes.wintypes 在非 Windows 上也能 import（纯 Python 定义）。
from ctypes import wintypes

log = logging.getLogger("mk87.tray_win")

#: Shell_NotifyIconGetRect 的返回码（实测语义，见模块头注释）
S_OK = 0
#: S_FALSE = 图标已注册但当前不可见（在「显示隐藏的图标」溢出区里）
S_FALSE = 1
#: E_FAIL = 图标未注册 / 已经被删除
E_FAIL = -2147467259  # 0x80004005

#: 图标状态
STATE_VISIBLE = "visible"      # 已注册且在通知区域可见
STATE_HIDDEN = "hidden"        # 已注册但在溢出区（『显示隐藏的图标』）
STATE_MISSING = "missing"      # 未注册（需要重建）
STATE_UNKNOWN = "unknown"      # 探测不了（非 Windows / 还没有窗口 / API 失败）

#: 任务栏/界面相关的只读常量
SW_SHOW = 5
SW_RESTORE = 9
FLASHW_ALL = 0x00000003
FLASHW_TIMERNOFG = 0x0000000C

#: 「自动隐藏不常用图标」的注册表位置（HKCU）
EXPLORER_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer"
ENABLE_AUTO_TRAY_VALUE = "EnableAutoTray"

#: pystray 创建的托图标窗口类名前缀（``<name><id>SystemTrayIcon``）
TRAY_WINDOW_CLASS_SUFFIX = "SystemTrayIcon"


def supported() -> bool:
    """当前平台是否支持这些 Win32 探测。"""
    return sys.platform == "win32"


# ----------------------------------------------------------------------
# ctypes 结构体
# ----------------------------------------------------------------------
class NotifyIconIdentifier(ctypes.Structure):
    """Win32 ``NOTIFYICONIDENTIFIER``（Shell_NotifyIconGetRect 的入参）。"""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


class Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class FlashWindowInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("hwnd", wintypes.HWND),
        ("dwFlags", wintypes.DWORD),
        ("uCount", wintypes.UINT),
        ("dwTimeout", wintypes.DWORD),
    ]


_WNDENUMPROC = None
if sys.platform == "win32":  # Linux/macOS：没有 WINFUNCTYPE，import 必须保持安全
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _to_uint32(value) -> int:
    """把任意 Python int 折成 Win32 UINT（pystray 传 id(self) 时会被截断）。"""
    try:
        return int(value) & 0xFFFFFFFF
    except Exception:  # noqa: BLE001
        return 0


class Win32Api:
    """user32/shell32 的只读查询封装；单测可换成同名方法的 fake 对象。"""

    def __init__(self, *, user32=None, shell32=None):
        if not supported():
            raise OSError("托盘 Win32 探测仅支持 Windows")
        self.user32 = user32 or ctypes.WinDLL("user32", use_last_error=True)
        self.shell32 = shell32 or ctypes.WinDLL("shell32", use_last_error=True)
        self._setup_prototypes()

    def _setup_prototypes(self) -> None:
        u = self.user32
        u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u.FindWindowW.restype = wintypes.HWND
        u.GetShellWindow.argtypes = []
        u.GetShellWindow.restype = wintypes.HWND
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.IsIconic.argtypes = [wintypes.HWND]
        u.IsIconic.restype = wintypes.BOOL
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                               ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
        u.EnumWindows.restype = wintypes.BOOL
        u.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindowAsync.restype = wintypes.BOOL
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.FlashWindowEx.argtypes = [ctypes.POINTER(FlashWindowInfo)]
        u.FlashWindowEx.restype = wintypes.BOOL
        self.shell32.Shell_NotifyIconGetRect.argtypes = [
            ctypes.POINTER(NotifyIconIdentifier), ctypes.POINTER(Rect)]
        self.shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long

    # ---------------------------------------------------------------- 窗口
    def find_window(self, class_name: Optional[str], title: Optional[str] = None) -> int:
        try:
            return int(self.user32.FindWindowW(class_name, title) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def get_shell_window(self) -> int:
        try:
            return int(self.user32.GetShellWindow() or 0)
        except Exception:  # noqa: BLE001
            return 0

    def get_class_name(self, hwnd: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
            return buf.value
        except Exception:  # noqa: BLE001
            return ""

    def get_window_text(self, hwnd: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(512)
            self.user32.GetWindowTextW(wintypes.HWND(hwnd), buf, 512)
            return buf.value
        except Exception:  # noqa: BLE001
            return ""

    def is_window_visible(self, hwnd: int) -> bool:
        try:
            return bool(self.user32.IsWindowVisible(wintypes.HWND(hwnd)))
        except Exception:  # noqa: BLE001
            return False

    def is_iconic(self, hwnd: int) -> bool:
        try:
            return bool(self.user32.IsIconic(wintypes.HWND(hwnd)))
        except Exception:  # noqa: BLE001
            return False

    def process_id_of_window(self, hwnd: int) -> int:
        try:
            pid = wintypes.DWORD(0)
            self.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
            return int(pid.value)
        except Exception:  # noqa: BLE001
            return 0

    def enum_windows(self) -> List[int]:
        handles: List[int] = []

        def _collect(hwnd, _lparam):
            handles.append(int(hwnd))
            return True

        try:
            self.user32.EnumWindows(_WNDENUMPROC(_collect), 0)
        except Exception:  # noqa: BLE001
            pass
        return handles

    # ---------------------------------------------------------------- 托盘
    def shell_notify_icon_get_rect(self, hwnd: int, u_id: int) -> Tuple[int, Optional[dict]]:
        ident = NotifyIconIdentifier()
        ident.cbSize = ctypes.sizeof(NotifyIconIdentifier)
        ident.hWnd = wintypes.HWND(hwnd)
        ident.uID = _to_uint32(u_id)
        ctypes.memset(ident.guidItem, 0, 16)
        rect = Rect()
        hr = int(self.shell32.Shell_NotifyIconGetRect(ctypes.byref(ident),
                                                      ctypes.byref(rect)))
        if hr == S_OK:
            return hr, {"left": int(rect.left), "top": int(rect.top),
                        "right": int(rect.right), "bottom": int(rect.bottom)}
        return hr, None

    # ------------------------------------------------------- 唤起窗口（兜底）
    def show_window_async(self, hwnd: int, cmd: int) -> bool:
        try:
            return bool(self.user32.ShowWindowAsync(wintypes.HWND(hwnd), int(cmd)))
        except Exception:  # noqa: BLE001
            return False

    def set_foreground_window(self, hwnd: int) -> bool:
        try:
            return bool(self.user32.SetForegroundWindow(wintypes.HWND(hwnd)))
        except Exception:  # noqa: BLE001
            return False

    def flash_window(self, hwnd: int) -> bool:
        try:
            info = FlashWindowInfo()
            info.cbSize = ctypes.sizeof(FlashWindowInfo)
            info.hwnd = wintypes.HWND(hwnd)
            info.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
            info.uCount = 3
            info.dwTimeout = 0
            return bool(self.user32.FlashWindowEx(ctypes.byref(info)))
        except Exception:  # noqa: BLE001
            return False


_API: Optional[Win32Api] = None


def _get_api(api=None):
    """返回注入的 api、缓存的真实 Win32Api，或抛 OSError（调用方负责兜底）。"""
    if api is not None:
        return api
    global _API
    if _API is None:
        _API = Win32Api()
    return _API


# ----------------------------------------------------------------------
# 注册表：『显示隐藏的图标』溢出行为
# ----------------------------------------------------------------------
def read_registry_dword(path: str, name: str) -> Optional[int]:
    """读 HKCU 下的 DWORD；不存在/失败返回 None（绝不抛）。"""
    if not supported():
        return None
    try:
        import winreg  # noqa: PLC0415 - 仅 Windows 可用
    except Exception:  # noqa: BLE001
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _value_type = winreg.QueryValueEx(key, name)
            return int(value)
    except OSError:
        return None
    except Exception:  # noqa: BLE001
        return None


def overflow_info(reader=None) -> dict:
    """通知区域溢出（『显示隐藏的图标』）设置。

    ``EnableAutoTray`` 语义（Windows 10 实测/官方论坛）：
    * ``1`` = 自动隐藏不常用图标（Windows 默认行为，图标可能落进溢出区）；
    * ``0`` = 始终显示所有通知区域图标；
    * 值不存在 = Windows 默认，等同 ``1``。
    """
    read = reader or read_registry_dword
    try:
        value = read(EXPLORER_KEY, ENABLE_AUTO_TRAY_VALUE)
    except Exception:  # noqa: BLE001
        value = None
    auto_hide = True if value is None else bool(value)
    return {
        "enableAutoTray": value,
        "autoHide": auto_hide,
        "source": "default" if value is None else "registry",
        "hint": ("图标可能被系统收进了任务栏右下角的『显示隐藏的图标』里。"
                 if auto_hide else ""),
    }


def auto_hide_enabled(reader=None) -> bool:
    """True = 新图标可能被收进『显示隐藏的图标』（首次隐藏提示用）。"""
    return bool(overflow_info(reader=reader).get("autoHide"))


# ----------------------------------------------------------------------
# 任务栏 / Explorer 环境
# ----------------------------------------------------------------------
def environment(api=None) -> dict:
    """任务栏（Explorer）是否存在，返回可用于检测 Explorer 重启的句柄快照。"""
    out = {
        "platform": sys.platform,
        "supported": supported(),
        "present": False,
        "taskbarHwnd": 0,
        "shellHwnd": 0,
        "error": None,
    }
    if not supported():
        out["error"] = "not-windows"
        return out
    try:
        w = _get_api(api)
        taskbar = int(w.find_window("Shell_TrayWnd") or 0)
        shell = int(w.get_shell_window() or 0)
        out["taskbarHwnd"] = taskbar
        out["shellHwnd"] = shell
        out["present"] = bool(taskbar and w.is_window_visible(taskbar))
        if not taskbar:
            out["error"] = "taskbar-not-found"
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def environment_token(api=None) -> Optional[Tuple[int, int]]:
    """(Shell_TrayWnd, GetShellWindow) —— Explorer 重启后这两个句柄都会变。"""
    env = environment(api=api)
    if not env.get("present"):
        return None
    return (int(env.get("taskbarHwnd") or 0), int(env.get("shellHwnd") or 0))


# ----------------------------------------------------------------------
# 图标注册状态
# ----------------------------------------------------------------------
def icon_state(hwnd, u_id: int = 0, api=None) -> dict:
    """查询单个 (hwnd, uID) 的托盘图标注册状态。

    :returns: ``{state, registered, visible, hidden, rect, hr, hwnd, uID, error}``；
              ``state`` ∈ visible / hidden / missing / unknown。
    """
    out = {
        "hwnd": 0,
        "uID": _to_uint32(u_id),
        "state": STATE_UNKNOWN,
        "registered": False,
        "visible": False,
        "hidden": False,
        "rect": None,
        "hr": None,
        "error": None,
    }
    try:
        out["hwnd"] = int(hwnd or 0)
    except Exception:  # noqa: BLE001
        out["hwnd"] = 0
    if not out["hwnd"]:
        out["state"] = STATE_MISSING
        return out
    if not supported():
        out["error"] = "not-windows"
        return out
    try:
        hr, rect = _get_api(api).shell_notify_icon_get_rect(out["hwnd"], out["uID"])
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    out["hr"] = int(hr)
    if hr == S_OK:
        out.update(state=STATE_VISIBLE, registered=True, visible=True, rect=rect)
    elif hr == S_FALSE:
        out.update(state=STATE_HIDDEN, registered=True, hidden=True)
    elif hr == E_FAIL:
        out.update(state=STATE_MISSING)
    else:
        # 其它错误码：无法判断，交给调用方按 unknown 处理（不要据此重建图标）
        out["error"] = f"hr=0x{_to_uint32(hr):08x}"
    return out


def probe_icon(hwnd, u_ids: Sequence[int] = (0,), api=None) -> dict:
    """按候选 uID 依次查询图标状态，返回第一个「已注册」的结果。

    默认 ``u_ids=(0,)``：pystray 实际用 uID=0 注册（见模块头注释）。
    兼容性：可同时传 ``id(tray)`` 作为候选，当 pystray 将来修好 ``hID`` 时仍能查到。
    """
    attempts: List[dict] = []
    fallback: Optional[dict] = None
    for uid in u_ids:
        result = icon_state(hwnd, uid, api=api)
        attempts.append({"uID": result.get("uID"), "hr": result.get("hr"),
                         "state": result.get("state")})
        if result.get("registered"):
            result["attempts"] = attempts
            return result
        if fallback is None or (
                result.get("state") == STATE_MISSING
                and fallback.get("state") != STATE_MISSING):
            fallback = result
    out = fallback if fallback is not None else icon_state(hwnd, 0, api=api)
    out["attempts"] = attempts
    return out


def find_icon_hwnds(pid: Optional[int] = None, name: Optional[str] = None,
                    api=None) -> List[dict]:
    """枚举托图标窗口（``<name><id>SystemTrayIcon`` 类名），可选按进程过滤。

    只读；用于 ``tray._hwnd`` 拿不到时的兜底（例如 pystray 尚未建好窗口）。
    """
    if not supported():
        return []
    found: List[dict] = []
    try:
        w = _get_api(api)
        for hwnd in w.enum_windows():
            class_name = w.get_class_name(hwnd)
            if not class_name.endswith(TRAY_WINDOW_CLASS_SUFFIX):
                continue
            owner = w.process_id_of_window(hwnd)
            if pid is not None and owner != int(pid):
                continue
            if name and not class_name.startswith(str(name)):
                continue
            found.append({
                "hwnd": int(hwnd),
                "class": class_name,
                "pid": owner,
                "visible": bool(w.is_window_visible(hwnd)),
            })
    except Exception as exc:  # noqa: BLE001
        log.debug("枚举托图标窗口失败（忽略）: %s", exc)
    return found


# ----------------------------------------------------------------------
# 唤起窗口（Windows 前台限制的兜底）
# ----------------------------------------------------------------------
def _find_app_window(title: str, pid: Optional[int], api) -> int:
    hwnd = int(api.find_window(None, title) or 0)
    if hwnd and (pid is None or api.process_id_of_window(hwnd) == int(pid)):
        return hwnd
    if pid is None:
        return 0
    for candidate in api.enum_windows():
        try:
            if (api.process_id_of_window(candidate) == int(pid)
                    and api.get_window_text(candidate) == title):
                return int(candidate)
        except Exception:  # noqa: BLE001
            continue
    return 0


def foreground_app_window(title: str = "MK87 Studio", pid: Optional[int] = None,
                          api=None) -> dict:
    """把主窗口恢复并尽量拉到前台（SetForegroundWindow 失败时闪烁任务栏提醒）。

    为什么需要：单实例唤起走 ``POST /api/activate``，pywebview 的 ``show/restore``
    只是在 GUI 线程恢复窗口，Windows 前台锁（foreground lock）下窗口可能仍被压在
    其它窗口后面 —— 用户就会觉得「点了没反应」。这里做 best-effort 兜底，失败只降级。
    """
    out = {
        "platform": sys.platform,
        "found": False,
        "hwnd": 0,
        "restored": False,
        "foreground": False,
        "flashed": False,
        "error": None,
    }
    if not supported():
        out["error"] = "not-windows"
        return out
    try:
        w = _get_api(api)
        hwnd = _find_app_window(title, pid, w)
        if not hwnd:
            out["error"] = "window-not-found"
            return out
        out["found"] = True
        out["hwnd"] = hwnd
        out["restored"] = bool(w.show_window_async(
            hwnd, SW_RESTORE if w.is_iconic(hwnd) else SW_SHOW))
        out["foreground"] = bool(w.set_foreground_window(hwnd))
        if not out["foreground"]:
            out["flashed"] = bool(w.flash_window(hwnd))
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ----------------------------------------------------------------------
# 汇总诊断（/api/tray/status、设置页、诊断包）
# ----------------------------------------------------------------------
def probe(*, tray=None, icon_hwnd=None, pid: Optional[int] = None,
          api=None, reader=None) -> dict:
    """一次性托盘诊断快照（JSON 可序列化；任何失败都折进字段里，不抛异常）。

    :param tray: pystray.Icon 对象（可选，用来取 ``_hwnd`` / id 兜底）；
    :param icon_hwnd: 已知的图标窗口句柄（优先于 tray._hwnd）；
    :param pid: 进程号（只有它才能安全地枚举「本进程」的托图标窗口；
                不传时不会去猜别的进程的窗口）。

    注意：pystray 会创建 2 个同名前缀窗口（图标窗口 + 菜单窗口），
    ``iconWindows`` 长度为 2 是**正常现象**，不能用它判断重复图标。
    """
    out: Dict[str, object] = {
        "platform": sys.platform,
        "supported": supported(),
        "taskbar": {},
        "overflow": {},
        "icon": {},
        "iconWindows": [],
        "error": None,
    }
    try:
        out["taskbar"] = environment(api=api)
        out["overflow"] = overflow_info(reader=reader)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"

    if not supported():
        out["error"] = out["error"] or "not-windows"
        return out

    # 候选图标窗口：显式 hwnd > tray._hwnd > （有 pid 时）本进程枚举。
    candidates: List[int] = []
    if icon_hwnd:
        try:
            candidates.append(int(icon_hwnd))
        except Exception:  # noqa: BLE001
            pass
    if not candidates and tray is not None:
        try:
            hwnd = int(getattr(tray, "_hwnd", 0) or 0)
            if hwnd:
                candidates.append(hwnd)
        except Exception:  # noqa: BLE001
            pass
    if not candidates and pid is not None:
        try:
            windows = find_icon_hwnds(pid=pid, api=api)
            out["iconWindows"] = windows[:8]
            candidates.extend(int(item["hwnd"]) for item in windows)
        except Exception:  # noqa: BLE001
            pass
    elif pid is not None:
        # tray 已有 hwnd 时仍枚举，便于设置页显示「窗口数」（2 个属正常）
        try:
            out["iconWindows"] = find_icon_hwnds(pid=pid, api=api)[:8]
        except Exception:  # noqa: BLE001
            pass

    u_ids: List[int] = [0]
    if tray is not None:
        try:
            u_ids.append(_to_uint32(id(tray)))
        except Exception:  # noqa: BLE001
            pass
    try:
        best: Optional[dict] = None
        for hwnd in candidates:
            result = probe_icon(hwnd, u_ids=u_ids, api=api)
            if best is None or (result.get("registered") and not best.get("registered")):
                best = result
            if result.get("registered"):
                break
        if best is not None:
            out["icon"] = best
        else:
            out["icon"] = {"state": STATE_UNKNOWN, "hwnd": 0,
                           "error": "icon-window-not-found"}
    except Exception as exc:  # noqa: BLE001
        out["icon"] = {"state": STATE_UNKNOWN,
                       "error": f"{type(exc).__name__}: {exc}"}
    return out


def _reset_api_cache() -> None:
    """单测用：清掉缓存的真实 Win32Api。"""
    global _API
    _API = None
