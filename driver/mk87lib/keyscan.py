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

import platform
import threading
import time
from typing import Callable, List, Optional

EventCb = Callable[[dict], None]

# Windows VKey → 显示名（常用键；未知键显示 VK_0xXX）
_VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "CapsLock",
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
    0xA2: 0xE0, 0xA0: 0xE1, 0xA4: 0xE2, 0x5B: 0xE3, 0x5C: 0xE7,
    0xA3: 0xE4, 0xA1: 0xE5, 0xA5: 0xE6,
}


def vkey_name(vkey: int) -> str:
    return _VK_NAMES.get(vkey, f"VK_0x{vkey:02X}")


def vkey_to_hid(vkey: int) -> Optional[int]:
    return _VK_TO_HID.get(vkey)


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

    def _windows_loop(self) -> None:
        import ctypes
        from ctypes import wintypes as wt

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        WM_INPUT = 0x00FF
        RID_INPUT = 0x10000003
        RIDEV_INPUTSINK = 0x00000100
        RIM_TYPEKEYBOARD = 1
        PM_REMOVE = 0x0001

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

        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        user32.CreateWindowExW.restype = wt.HWND
        user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE,
                                           wt.LPVOID]
        user32.RegisterClassW.restype = wt.ATOM
        user32.GetRawInputData.restype = wt.UINT
        user32.PeekMessageW.restype = wt.BOOL

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        def _wndproc(hwnd, msg, wparam, lparam):
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(WNDPROC(_wndproc), ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "mk87_keyscan"
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(0, "mk87_keyscan", "mk87", 0, 0, 0, 0, 0,
                                      None, None, wc.hInstance, None)
        if not hwnd:
            raise OSError(f"CreateWindow failed {ctypes.get_last_error()}")

        devs = (RAWINPUTDEVICE * 2)()
        devs[0].usUsagePage, devs[0].usUsage = 0x01, 0x06
        devs[0].dwFlags, devs[0].hwndTarget = RIDEV_INPUTSINK, hwnd
        devs[1].usUsagePage, devs[1].usUsage = 0x0C, 0x01
        devs[1].dwFlags, devs[1].hwndTarget = RIDEV_INPUTSINK, hwnd
        if not user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE)):
            raise OSError(f"RegisterRawInputDevices failed {ctypes.get_last_error()}")

        def get_device_name(hdevice):
            size = wt.UINT(0)
            user32.GetRawInputDeviceInfoW(hdevice, 0x20000007, None, ctypes.byref(size))
            if not size.value:
                return ""
            buf = ctypes.create_unicode_buffer(size.value)
            user32.GetRawInputDeviceInfoW(hdevice, 0x20000007, buf, ctypes.byref(size))
            return buf.value

        msg = wt.MSG()
        while not self._stop.is_set():
            got = False
            while user32.PeekMessageW(ctypes.byref(msg), hwnd, 0, 0, PM_REMOVE):
                got = True
                if msg.message == WM_INPUT:
                    try:
                        size = wt.UINT(0)
                        user32.GetRawInputData(msg.lParam, RID_INPUT, None,
                                               ctypes.byref(size),
                                               ctypes.sizeof(RAWINPUTHEADER))
                        if size.value:
                            buf = ctypes.create_string_buffer(size.value)
                            n = user32.GetRawInputData(msg.lParam, RID_INPUT, buf,
                                                       ctypes.byref(size),
                                                       ctypes.sizeof(RAWINPUTHEADER))
                            if n and n != 0xFFFFFFFF:
                                hdr_sz = ctypes.sizeof(RAWINPUTHEADER)
                                hdr = RAWINPUTHEADER.from_buffer_copy(buf.raw[:hdr_sz])
                                if hdr.dwType == RIM_TYPEKEYBOARD:
                                    kb = RAWKEYBOARD.from_buffer_copy(
                                        buf.raw[hdr_sz:hdr_sz + ctypes.sizeof(RAWKEYBOARD)])
                                    dev = get_device_name(hdr.hDevice)
                                    if self.only_ajazz and "VID_0C45" not in dev.upper():
                                        continue
                                    down = kb.Message in (0x0100, 0x0104)  # WM_KEYDOWN/SYSKEYDOWN
                                    ev = {
                                        "type": "key",
                                        "vkey": int(kb.VKey),
                                        "name": vkey_name(int(kb.VKey)),
                                        "hid": vkey_to_hid(int(kb.VKey)),
                                        "down": bool(down),
                                        "scan": int(kb.MakeCode),
                                        "flags": int(kb.Flags),
                                        "device": dev,
                                    }
                                    self._emit(ev)
                    except Exception:
                        self.errors += 1
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if not got:
                time.sleep(0.002)
        try:
            user32.DestroyWindow(hwnd)
        except Exception:
            pass

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
