"""Windows 原生 HID 读写通道（大报文 TFT 专用）。

背景：本项目的 TFT 通道（usagePage 0xFF67，输出报文 4105 字节）在 hidapi 0.15 上
写入会失败（`hid_write` 返回 -1，耗时约 1000ms 后超时），而探针阶段用 Win32
`WriteFile` + overlapped `ReadFile` 原生读写是正常且快速的（见 docs/TEST-REPORT.md §6、
probe/phase2_tft.py 的真机测试）。
因此 Windows 下 TFT 上传走本模块的原生读写路径；其它平台仍用 hidapi。

`NativeHidChannel` 与探针 `probe/ajazz.py::HidInterface` 行为一致：
* 写句柄：WriteFile 写完整 output report（含 report ID 首字节），USB 满帧时阻塞约 65ms；
* 读句柄：FILE_FLAG_OVERLAPPED + 事件，带超时读 input report（含 report ID 首字节）；
* 逐包 ACK 必须等到，否则固件会丢弃后续数据（真机结论，见 docs/tft-page.md）。

只依赖 ctypes/kernel32，不需要额外依赖。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import time

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("winhid 仅用于 Windows")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0x00000000

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                               ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wt.BOOL
kernel32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                              ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.ReadFile.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.WaitForSingleObject.restype = wt.DWORD
kernel32.GetOverlappedResult.argtypes = [wt.HANDLE, ctypes.c_void_p,
                                         ctypes.POINTER(wt.DWORD), wt.BOOL]
kernel32.GetOverlappedResult.restype = wt.BOOL
kernel32.ResetEvent.argtypes = [wt.HANDLE]
try:
    kernel32.CancelIoEx.argtypes = [wt.HANDLE, ctypes.c_void_p]
    kernel32.CancelIoEx.restype = wt.BOOL
except AttributeError:  # pragma: no cover - 老系统没有 CancelIoEx
    pass


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wt.DWORD),
        ("OffsetHigh", wt.DWORD),
        ("hEvent", wt.HANDLE),
    ]


class NativeHidWriter:
    """按设备路径打开一个只写 HID 句柄，用 WriteFile 写完整 output report。"""

    def __init__(self, path):
        if isinstance(path, bytes):
            path = path.decode("utf-8", "ignore")
        self.path = path
        self._handle = kernel32.CreateFileW(
            path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None,
        )
        if not self._handle or self._handle == INVALID_HANDLE_VALUE:
            raise OSError(f"打开 HID 写入句柄失败: {ctypes.get_last_error()} path={path}")

    def write(self, data: bytes) -> int:
        written = wt.DWORD(0)
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        ok = kernel32.WriteFile(self._handle, ctypes.cast(buf, ctypes.c_void_p),
                                len(data), ctypes.byref(written), None)
        if not ok:
            raise OSError(f"WriteFile 失败: {ctypes.get_last_error()}")
        return int(written.value)

    def close(self) -> None:
        if self._handle:
            try:
                kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class NativeHidChannel:
    """原生读写通道：WriteFile 写报文 + overlapped ReadFile 带超时读回包。

    读到的数据包含 report ID 首字节（TFT 通道 input report 2105/4105 字节时为 0）。
    """

    def __init__(self, path, read_len: int = 4105, write_len: int = 4105):
        if isinstance(path, bytes):
            path = path.decode("utf-8", "ignore")
        self.path = path
        self.read_len = int(read_len)
        self.write_len = int(write_len)
        self._wr = kernel32.CreateFileW(
            path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None,
        )
        if not self._wr or self._wr == INVALID_HANDLE_VALUE:
            raise OSError(f"打开 HID 写句柄失败: {ctypes.get_last_error()} path={path}")
        self._rd = kernel32.CreateFileW(
            path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None,
        )
        if not self._rd or self._rd == INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(self._wr)
            raise OSError(f"打开 HID 读句柄失败: {ctypes.get_last_error()} path={path}")
        self._event = kernel32.CreateEventW(None, True, False, None)
        if not self._event:
            self.close()
            raise OSError(f"创建读事件失败: {ctypes.get_last_error()}")
        # 持久读缓冲区 + 保管在途 OVERLAPPED 的引用。
        # 绝不能让内核在 I/O 未完成时写进已被 Python 回收的内存：轻则丢 ACK，
        # 重则堆损坏导致进程随机崩溃（overlapped 必须等完成/取消完成后再释放）。
        self._buf = ctypes.create_string_buffer(self.read_len)
        self._pending_ov = None

    # ------------------------------------------------------------------ 写
    def write(self, data: bytes) -> int:
        written = wt.DWORD(0)
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        ok = kernel32.WriteFile(self._wr, ctypes.cast(buf, ctypes.c_void_p),
                                len(data), ctypes.byref(written), None)
        if not ok:
            raise OSError(f"WriteFile 失败: {ctypes.get_last_error()}")
        return int(written.value)

    # ------------------------------------------------------------------ 读
    def read(self, timeout: float = 0.6):
        """读一个 input report（含 report ID 首字节）；超时返回 None。"""
        deadline = time.time() + max(0.001, float(timeout))
        if self._pending_ov is not None:
            # 上一次超时取消的读还没被收割：先等它真正结束，不能并发复用/释放
            self._reap_pending()
        while time.time() < deadline:
            ov = OVERLAPPED()
            ov.hEvent = self._event
            self._pending_ov = ov  # 保留引用，防止内核完成时内存已被回收
            got = wt.DWORD(0)
            ok = kernel32.ReadFile(self._rd, ctypes.cast(self._buf, ctypes.c_void_p),
                                   self.read_len, ctypes.byref(got), ctypes.byref(ov))
            if not ok:
                err = ctypes.get_last_error()
                if err != ERROR_IO_PENDING:
                    self._pending_ov = None
                    try:
                        kernel32.ResetEvent(self._event)
                    except Exception:
                        pass
                    raise OSError(f"ReadFile 失败: {err}")
                wait_ms = max(10, int((deadline - time.time()) * 1000))
                waited = kernel32.WaitForSingleObject(self._event, wait_ms)
                if waited != WAIT_OBJECT_0:
                    # 超时：请求取消，但**不立刻释放 ov/buffer**；
                    # 由 _reap_pending() 等到取消完成后再归还内存。
                    try:
                        kernel32.CancelIoEx(self._rd, ctypes.byref(ov))
                    except Exception:
                        pass
                    self._reap_pending()
                    return None
            success = kernel32.GetOverlappedResult(self._rd, ctypes.byref(ov),
                                                   ctypes.byref(got), False)
            err2 = 0 if success else ctypes.get_last_error()
            self._pending_ov = None
            try:
                kernel32.ResetEvent(self._event)
            except Exception:
                pass
            if not success:
                if err2 == 995:  # ERROR_OPERATION_ABORTED：被取消/设备复位，视为无数据
                    continue
                raise OSError(f"GetOverlappedResult 失败: {err2}")
            if got.value:
                return self._buf.raw[:got.value]
        return None

    def _reap_pending(self) -> None:
        """等待上一笔在途/已取消的读真正完成并收割结果。

        内核完成 I/O 时会写 OVERLAPPED 和读缓冲区，因此必须确认完成
        （或取消已生效）之后才允许释放引用，否则会出现随机崩溃。
        """
        ov = self._pending_ov
        if ov is None:
            return
        try:
            if kernel32.WaitForSingleObject(self._event, 2000) == WAIT_OBJECT_0:
                got = wt.DWORD(0)
                kernel32.GetOverlappedResult(self._rd, ctypes.byref(ov), ctypes.byref(got), False)
        except Exception:
            pass
        finally:
            self._pending_ov = None
            try:
                kernel32.ResetEvent(self._event)
            except Exception:
                pass

    def read_normalized(self, timeout: float = 0.6):
        """读回包并去掉可能的 report ID=0 前导字节（协议回包以 0x55 开头）。"""
        r = self.read(timeout)
        if r and r[0] == 0 and len(r) > 8 and r[1] == 0x55:
            return r[1:]
        return r

    def drain(self, duration: float = 0.02) -> None:
        end = time.time() + duration
        while time.time() < end:
            if self.read(timeout=min(0.01, max(0.001, end - time.time()))) is None:
                break

    def close(self) -> None:
        # 关句柄前先把在途/已取消的读收割干净，避免内核完成后写已释放内存
        try:
            self._reap_pending()
        except Exception:
            pass
        for h in (self._rd, self._wr):
            if h:
                try:
                    kernel32.CloseHandle(h)
                except Exception:
                    pass
        self._rd = None
        self._wr = None
        if self._event:
            try:
                kernel32.CloseHandle(self._event)
            except Exception:
                pass
            self._event = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
