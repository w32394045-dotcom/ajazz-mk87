"""按键事件捕获（按键测试页用）。

厂商协议没有按键事件帧（docs/key-events.md），只能从操作系统拿：

* Windows：RegisterRawInputDevices + 隐藏窗口 + WM_INPUT，可拿到
  VKey / MakeCode / Flags / 设备路径（无需管理员权限）；
* Linux：读 /dev/input/event*（evdev），需要 input 组权限。

事件统一格式::

    {"type":"key", "vkey":65, "name":"A", "hid":4, "down":true,
     "device":"...", "ts":..., "scan":0x1E}
"""
from __future__ import annotations

import os
import platform
import threading
import time
from typing import Callable, List, Optional, Tuple

EventCb = Callable[[dict], None]

# Windows VKey → 显示名（常用键；未知键显示 VK_0xXX）
# 注意 0x10/0x11/0x12 是「通用」修饰键 VK（不带左右手），事件里还会用
# `_resolve_generic_modifier` 按扫描码/E0 标志纠正成 L-/R- 版本。
_VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter",
    0x10: "L-Shift", 0x11: "L-Ctrl", 0x12: "L-Alt",
    0x13: "Pause", 0x14: "CapsLock",
    0x1B: "Esc", 0x20: "Space", 0x21: "PgUp", 0x22: "PgDn", 0x23: "End", 0x24: "Home",
    0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓", 0x2C: "PrintScreen", 0x2D: "Insert",
    0x2E: "Delete", 0x5B: "L-Win", 0x5C: "R-Win", 0x5D: "Menu",
    0x90: "NumLock", 0x91: "ScrollLock",
    0xA0: "L-Shift", 0xA1: "R-Shift", 0xA2: "L-Ctrl", 0xA3: "R-Ctrl",
    0xA4: "L-Alt", 0xA5: "R-Alt",
    0xAD: "音量静音", 0xAE: "音量-", 0xAF: "音量+",
    0xB0: "下一曲", 0xB1: "上一曲", 0xB2: "停止", 0xB3: "播放/暂停",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
for _i in range(0x30, 0x3A):  # 0-9
    _VK_NAMES[_i] = chr(_i)
for _i in range(0x41, 0x5B):  # A-Z
    _VK_NAMES[_i] = chr(_i)
for _i in range(0x60, 0x6A):  # 小键盘 0-9
    _VK_NAMES[_i] = f"Num{_i - 0x60}"
for _i in range(0x70, 0x88):  # F1-F24
    _VK_NAMES[_i] = f"F{_i - 0x6F}"

# 常用键 VKey → HID usage（标准 ANSI 主键区；用于和改键表对照）
_VK_TO_HID = {
    0x41: 0x04, 0x42: 0x05, 0x43: 0x06, 0x44: 0x07, 0x45: 0x08, 0x46: 0x09,
    0x47: 0x0A, 0x48: 0x0B, 0x49: 0x0C, 0x4A: 0x0D, 0x4B: 0x0E, 0x4C: 0x0F,
    0x4D: 0x10, 0x4E: 0x11, 0x4F: 0x12, 0x50: 0x13, 0x51: 0x14, 0x52: 0x15,
    0x53: 0x16, 0x54: 0x17, 0x55: 0x18, 0x56: 0x19, 0x57: 0x1A, 0x58: 0x1B,
    0x59: 0x1C, 0x5A: 0x1D,
    0x31: 0x1E, 0x32: 0x1F, 0x33: 0x20, 0x34: 0x21, 0x35: 0x22, 0x36: 0x23,
    0x37: 0x24, 0x38: 0x25, 0x39: 0x26, 0x30: 0x27,
    0x0D: 0x28, 0x1B: 0x29, 0x08: 0x2A, 0x09: 0x2B, 0x20: 0x2C, 0xBD: 0x2D,
    0xBB: 0x2E, 0xDB: 0x2F, 0xDD: 0x30, 0xDC: 0x31, 0xBA: 0x33, 0xDE: 0x34,
    0xC0: 0x35, 0xBC: 0x36, 0xBE: 0x37, 0xBF: 0x38, 0x14: 0x39,
    0x70: 0x3A, 0x71: 0x3B, 0x72: 0x3C, 0x73: 0x3D, 0x74: 0x3E, 0x75: 0x3F,
    0x76: 0x40, 0x77: 0x41, 0x78: 0x42, 0x79: 0x43, 0x7A: 0x44, 0x7B: 0x45,
    0x2C: 0x46, 0x91: 0x47, 0x13: 0x48, 0x2D: 0x49, 0x24: 0x4A, 0x23: 0x4B,
    0x22: 0x4C, 0x21: 0x4D, 0x2E: 0x4E,
    # 通用修饰键 VK：静态表按左手给默认值，事件里再按扫描码纠正左右手
    0x10: 0xE1, 0x11: 0xE0, 0x12: 0xE2,
    0xA2: 0xE0, 0xA0: 0xE1, 0xA4: 0xE2, 0x5B: 0xE3, 0x5C: 0xE7,
    0xA3: 0xE4, 0xA1: 0xE5, 0xA5: 0xE6,
}


def vkey_name(vkey: int) -> str:
    return _VK_NAMES.get(vkey, f"VK_0x{vkey:02X}")


def vkey_to_hid(vkey: int) -> Optional[int]:
    return _VK_TO_HID.get(vkey)


# ---------------------------------------------------------------- Win32 raw input
_WM_INPUT = 0x00FF
_RID_INPUT = 0x10000003
_RIDI_DEVICENAME = 0x20000007
_RIDEV_INPUTSINK = 0x00000100
_RIM_TYPEKEYBOARD = 1
_PM_REMOVE = 0x0001
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_RAWINPUT_ERROR = 0xFFFFFFFF
_MAX_DEVICE_NAME_CHARS = 4096
#: RAWKEYBOARD.Flags 里的 RI_KEY_E0：置位表示扩展键（右 Ctrl / 右 Alt / 方向键等）
_RI_KEY_E0 = 0x02


def _resolve_generic_modifier(vkey: int, scan: int, flags: int) -> Optional[Tuple[str, int]]:
    """把「通用」修饰键 VK 还原成左右手版本。

    Windows raw input 通常直接给 0xA0..0xA5（左右手专用 VK），但部分键盘固件、
    SendInput 注入或 remap 路径只给 0x10/0x11/0x12。仅凭 VKey 无法区分左右：
    左手/右手 Alt、Ctrl 的扫描码相同，靠 E0 标志区分；左右 Shift 扫描码不同。
    返回 ``(name, hid)``；不是通用修饰键时返回 None。
    """
    if vkey == 0x10:  # VK_SHIFT：左 0x2A / 右 0x36（右 Shift 不带 E0）
        if scan == 0x36:
            return ("R-Shift", 0xE5)
        return ("L-Shift", 0xE1)
    if vkey == 0x11:  # VK_CONTROL：左 0x1D / 右 0x1D+E0
        if flags & _RI_KEY_E0:
            return ("R-Ctrl", 0xE4)
        return ("L-Ctrl", 0xE0)
    if vkey == 0x12:  # VK_MENU：左 0x38 / 右 0x38+E0（AltGr）
        if flags & _RI_KEY_E0:
            return ("R-Alt", 0xE6)
        return ("L-Alt", 0xE2)
    return None


class _Win32Api:
    """Windows raw-input 所需的 Win32 接口封装（ctypes）。

    ``KeyScanner._windows_loop`` 只依赖本对象暴露的属性，单测可把 ``user32`` /
    ``kernel32`` 换成假的，从而在不注册 raw input、不碰真实键盘的前提下验证
    调用序列、缓冲区语义与窗口类生命周期。
    """

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes as wt

        self.ctypes = ctypes
        self.wt = wt

        class RAWINPUTDEVICE(ctypes.Structure):
            _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT),
                        ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]

        class RAWINPUTHEADER(ctypes.Structure):
            _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD),
                        ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]

        class RAWKEYBOARD(ctypes.Structure):
            _fields_ = [("MakeCode", wt.USHORT), ("Flags", wt.USHORT),
                        ("Reserved", wt.USHORT), ("VKey", wt.USHORT),
                        ("Message", wt.UINT), ("ExtraInformation", wt.ULONG)]

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wt.UINT), ("lpfnWndProc", ctypes.c_void_p),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

        self.RAWINPUTDEVICE = RAWINPUTDEVICE
        self.RAWINPUTHEADER = RAWINPUTHEADER
        self.RAWKEYBOARD = RAWKEYBOARD
        self.WNDCLASSW = WNDCLASSW
        self.WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._declare_prototypes(user32, kernel32)
        self.user32 = user32
        self.kernel32 = kernel32

    def _declare_prototypes(self, user32, kernel32) -> None:
        """显式声明 argtypes/restype。

        64 位下不声明时 ctypes 默认按 c_int 处理返回值/参数，
        ``GetModuleHandleW`` 的 HINSTANCE 会被截成 32 位，窗口类注册随之异常。
        """
        ctypes = self.ctypes
        wt = self.wt
        user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.RegisterClassW.argtypes = [ctypes.POINTER(self.WNDCLASSW)]
        user32.RegisterClassW.restype = wt.ATOM
        user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
        user32.UnregisterClassW.restype = wt.BOOL
        user32.CreateWindowExW.argtypes = [
            wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
        user32.CreateWindowExW.restype = wt.HWND
        user32.DestroyWindow.argtypes = [wt.HWND]
        user32.DestroyWindow.restype = wt.BOOL
        user32.RegisterRawInputDevices.argtypes = [
            ctypes.POINTER(self.RAWINPUTDEVICE), wt.UINT, wt.UINT]
        user32.RegisterRawInputDevices.restype = wt.BOOL
        user32.GetRawInputData.argtypes = [wt.HANDLE, wt.UINT, ctypes.c_void_p,
                                           ctypes.POINTER(wt.UINT), wt.UINT]
        user32.GetRawInputData.restype = wt.UINT
        user32.GetRawInputDeviceInfoW.argtypes = [
            wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT)]
        user32.GetRawInputDeviceInfoW.restype = wt.UINT
        user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT,
                                        wt.UINT, wt.UINT]
        user32.PeekMessageW.restype = wt.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
        user32.TranslateMessage.restype = wt.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wt.HMODULE


class KeyScanner:
    """后台按键捕获。用法: scanner = KeyScanner(cb); scanner.start(); ...; scanner.stop()"""

    def __init__(self, callback: Optional[EventCb] = None, only_ajazz: bool = False):
        self.callback = callback
        self.only_ajazz = only_ajazz
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._events: List[dict] = []
        self.events_seen = 0
        self.errors = 0
        self.last_error = ""
        self.backend = self._detect_backend()
        self.started_at = 0.0
        #: Win32 窗口过程强引用（裸指针塞给 WNDCLASSW 后必须有人持有，见 _windows_loop）
        self._wndproc = None

    @staticmethod
    def _detect_backend() -> str:
        if platform.system() == "Windows":
            return "rawinput"
        if platform.system() == "Linux":
            return "evdev"
        return "none"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if self.backend == "rawinput":
            target = self._run_windows
        elif self.backend == "evdev":
            target = self._run_linux
        else:
            raise RuntimeError(f"当前平台不支持按键捕获: {platform.system()}")
        self._stop.clear()
        self._thread = threading.Thread(target=target, name="mk87-keyscan", daemon=True)
        self._thread.start()
        self.started_at = time.time()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "backend": self.backend,
            "events": self.events_seen,
            "errors": self.errors,
            "lastError": self.last_error,
            "uptime": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "recent": self._events[-50:],
        }

    def _emit(self, ev: dict) -> None:
        ev.setdefault("ts", time.time())
        self.events_seen += 1
        self._events.append(ev)
        if len(self._events) > 500:
            del self._events[:250]
        if self.callback:
            try:
                self.callback(ev)
            except Exception:
                pass

    # ------------------------------------------------------------------ Windows
    def _run_windows(self) -> None:
        try:
            self._windows_loop()
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = str(exc)

    def _windows_loop(self, api: Optional["_Win32Api"] = None) -> None:
        """Raw input 消息循环（阻塞到 stop()）。

        :param api: 仅供单测注入假 Win32 接口；正常启动传 None。
        """
        win = _Win32Api() if api is None else api
        ctypes = win.ctypes
        user32 = win.user32
        kernel32 = win.kernel32

        hinstance = kernel32.GetModuleHandleW(None)
        # 类名必须唯一：scanner 反复 start/stop 时上一轮的窗口类可能尚未注销，
        # 复用同名类会让 CreateWindowExW 拿到旧类（及其可能已失效的 WndProc）。
        class_name = "mk87_keyscan_%d_%x" % (os.getpid(), id(self))
        hwnd = None
        atom = 0

        def _wndproc(hwnd_, msg_, wparam_, lparam_):
            # 所有窗口消息交默认处理；异常绝不能穿过 ctypes 回调边界
            try:
                return user32.DefWindowProcW(hwnd_, msg_, wparam_, lparam_)
            except Exception:  # noqa: BLE001
                return 0

        # ⚠ 2026-11-07 crash.log（`_windows_loop` line 205/206 access violation）根因：
        # `ctypes.cast(WNDPROC(_wndproc), c_void_p)` 只把瞬时生成的 Python 函数
        # 指针地址塞进 WNDCLASSW，WNDPROC 对象随后立刻被 GC；窗口消息（创建窗口
        # 时的 WM_NCCREATE、运行期的 WM_INPUT）回调到已释放内存即访问违例。
        # 修复：scanner 持强引用，直到 DestroyWindow + UnregisterClassW 之后才释放。
        wndproc = win.WNDPROC(_wndproc)
        self._wndproc = wndproc
        try:
            wc = win.WNDCLASSW()
            wc.lpfnWndProc = ctypes.cast(wndproc, ctypes.c_void_p)
            wc.hInstance = hinstance
            wc.lpszClassName = class_name
            atom = user32.RegisterClassW(ctypes.byref(wc))
            if not atom:
                raise OSError(f"RegisterClassW 失败: {ctypes.get_last_error()}")
            hwnd = user32.CreateWindowExW(
                0, class_name, "mk87_keyscan", 0, 0, 0, 0, 0,
                None, None, hinstance, None)
            if not hwnd:
                raise OSError(f"CreateWindowExW 失败: {ctypes.get_last_error()}")

            devs = (win.RAWINPUTDEVICE * 2)()
            devs[0].usUsagePage, devs[0].usUsage = 0x01, 0x06
            devs[0].dwFlags, devs[0].hwndTarget = _RIDEV_INPUTSINK, hwnd
            devs[1].usUsagePage, devs[1].usUsage = 0x0C, 0x01
            devs[1].dwFlags, devs[1].hwndTarget = _RIDEV_INPUTSINK, hwnd
            if not user32.RegisterRawInputDevices(
                    devs, 2, ctypes.sizeof(win.RAWINPUTDEVICE)):
                raise OSError(f"RegisterRawInputDevices 失败: {ctypes.get_last_error()}")

            self._windows_message_loop(win, hwnd)
        finally:
            if hwnd:
                try:
                    user32.DestroyWindow(hwnd)
                except Exception:  # noqa: BLE001
                    pass
            if atom:
                try:
                    user32.UnregisterClassW(class_name, hinstance)
                except Exception:  # noqa: BLE001
                    pass
            # 窗口已销毁、类已注销，回调对象才能安全释放；顺序反了就是悬空指针
            self._wndproc = None

    def _windows_message_loop(self, win: "_Win32Api", hwnd) -> None:
        ctypes = win.ctypes
        wt = win.wt
        user32 = win.user32
        msg = wt.MSG()
        while not self._stop.is_set():
            got = False
            while user32.PeekMessageW(ctypes.byref(msg), hwnd, 0, 0, _PM_REMOVE):
                got = True
                if msg.message == _WM_INPUT:
                    try:
                        self._handle_raw_input(win, msg)
                    except Exception:  # noqa: BLE001
                        self.errors += 1
                # WM_INPUT 仍要交给 DefWindowProc：系统在默认窗口过程里清理
                # raw input 内部缓冲；Translate/Dispatch 保持标准消息泵行为。
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if not got:
                time.sleep(0.002)

    def _handle_raw_input(self, win: "_Win32Api", msg) -> None:
        ctypes = win.ctypes
        wt = win.wt
        user32 = win.user32
        header_size = ctypes.sizeof(win.RAWINPUTHEADER)

        # 第一次调用：pData=NULL 查询所需字节数（pcbSize 输出）
        size = wt.UINT(0)
        user32.GetRawInputData(msg.lParam, _RID_INPUT, None, ctypes.byref(size),
                               header_size)
        if size.value < header_size:
            return  # 无数据，或连 RAWINPUTHEADER 都放不下

        # 第二次调用：pcbSize 必须先设成「缓冲区字节数」（Win32 文档语义）；
        # 若沿用第一次查询到的所需大小，两次调用之间数据变化就可能越界。
        buf = ctypes.create_string_buffer(size.value)
        size = wt.UINT(len(buf))
        n = user32.GetRawInputData(msg.lParam, _RID_INPUT,
                                   ctypes.cast(buf, ctypes.c_void_p),
                                   ctypes.byref(size), header_size)
        if not n or n == _RAWINPUT_ERROR:
            return

        hdr = win.RAWINPUTHEADER.from_buffer_copy(buf.raw[:header_size])
        if hdr.dwType != _RIM_TYPEKEYBOARD:
            return
        kb_size = ctypes.sizeof(win.RAWKEYBOARD)
        if len(buf) < header_size + kb_size:
            return
        kb = win.RAWKEYBOARD.from_buffer_copy(buf.raw[header_size:header_size + kb_size])
        vkey = int(kb.VKey)
        scan = int(kb.MakeCode)
        flags = int(kb.Flags)
        device = self._get_device_name(win, hdr.hDevice)
        if self.only_ajazz and "VID_0C45" not in device.upper():
            return
        name = vkey_name(vkey)
        hid = vkey_to_hid(vkey)
        resolved = _resolve_generic_modifier(vkey, scan, flags)
        if resolved is not None:
            name, hid = resolved
        self._emit({
            "type": "key",
            "vkey": vkey,
            "name": name,
            "hid": hid,
            "down": kb.Message in (_WM_KEYDOWN, _WM_SYSKEYDOWN),
            "scan": scan,
            "flags": flags,
            "device": device,
        })

    def _get_device_name(self, win: "_Win32Api", hdevice) -> str:
        ctypes = win.ctypes
        wt = win.wt
        user32 = win.user32
        # RIDI_DEVICENAME 的 pcbSize 语义是「WCHAR 字符数」（含结尾 NUL），
        # 不是字节数；两次调用都必须按字符数传入/创建缓冲。
        size = wt.UINT(0)
        user32.GetRawInputDeviceInfoW(hdevice, _RIDI_DEVICENAME, None,
                                      ctypes.byref(size))
        if size.value == 0 or size.value > _MAX_DEVICE_NAME_CHARS:
            return ""
        buf = ctypes.create_unicode_buffer(size.value)
        n = user32.GetRawInputDeviceInfoW(hdevice, _RIDI_DEVICENAME,
                                          ctypes.cast(buf, ctypes.c_void_p),
                                          ctypes.byref(size))
        if n == _RAWINPUT_ERROR:
            return ""
        return buf.value

    # ------------------------------------------------------------------ Linux
    def _run_linux(self) -> None:
        try:
            import glob
            import select

            import evdev  # type: ignore
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = f"缺少 python-evdev 或无法读取设备: {exc}"
            return
        devices = []
        for path in glob.glob("/dev/input/event*"):
            try:
                d = evdev.InputDevice(path)
                caps = d.capabilities(verbose=False)
                if evdev.ecodes.EV_KEY in caps and any(
                        k in (evdev.ecodes.KEY_A, evdev.ecodes.KEY_ESC) for k in caps[evdev.ecodes.EV_KEY]):
                    if self.only_ajazz and "ajazz" not in d.name.lower():
                        continue
                    devices.append(d)
            except Exception:
                continue
        if not devices:
            self.errors += 1
            self.last_error = "未找到可读的键盘输入设备（检查 input 组权限）"
            return
        try:
            while not self._stop.is_set():
                r, _, _ = select.select(devices, [], [], 0.2)
                for dev in r:
                    for ev in dev.read():
                        if ev.type != evdev.ecodes.EV_KEY:
                            continue
                        name = evdev.ecodes.KEY.get(ev.code) or str(ev.code)
                        if isinstance(name, (list, tuple)):
                            name = name[0]
                        down = ev.value != 0
                        self._emit({
                            "type": "key",
                            "vkey": int(ev.code),
                            "name": str(name),
                            "hid": int(ev.code),
                            "down": bool(down),
                            "scan": int(ev.code),
                            "device": dev.path,
                        })
        finally:
            for d in devices:
                try:
                    d.close()
                except Exception:
                    pass


_scanner: Optional[KeyScanner] = None


def get_scanner(callback: Optional[EventCb] = None, only_ajazz: bool = False) -> KeyScanner:
    global _scanner
    if _scanner is None:
        _scanner = KeyScanner(callback=callback, only_ajazz=only_ajazz)
    elif callback is not None:
        _scanner.callback = callback
    return _scanner
