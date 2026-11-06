#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台「保后台」：音乐律动运行期间阻止系统空闲休眠 / 关闭 Windows 能效节流 / 提升计时器精度。

背景
----
2026-11-06 用户实机日志：音乐律动开久了灯效停更、帧流线程卡死。日志显示 Windows
进入「连接待机（modern standby，合盖/空闲）」后 HID 写入被系统挂起；同时系统可能
把后台进程按 EcoQoS（进程能效节流）降频，60fps 帧流排期随之抖动。

本模块只做三件事（纯标准库，任何失败都只降级/写日志，绝不抛异常）：

1. ``KeepAwake``：音乐律动运行期间阻止系统空闲休眠。
   * Windows：常驻 daemon 线程里反复 ``SetThreadExecutionState``（``ES_CONTINUOUS``
     是 **per-thread** 状态，必须由同一个线程持续维护），并用 ``timeBeginPeriod(1)``
     把计时器精度提到 1ms，保证 60fps 帧流排期；
   * Linux：拉起 ``systemd-inhibit --what=sleep`` 子进程，stop 时 terminate → wait → kill；
   * 其它平台：backend="none"，start 直接返回 False。
2. ``opt_out_power_throttling``：Windows 上用 ``SetProcessInformation(ProcessPowerThrottling)``
   关闭执行速度节流（EcoQoS），并让系统忽略计时器精度请求（这样 ``timeBeginPeriod`` 才生效）；
   其它平台直接返回 False。
3. ``platform_report``：给启动 bootlog / 诊断包用的能力摘要（纯查询，不产生系统调用）。

幂等性
------
``KeepAwake.start/stop`` 可重复调用；``opt_out_power_throttling`` 带模块级缓存，
重复调用返回上次结果；某平台一旦判定没有可用手段，后续 ``start()`` 直接返回 False。
"""
from __future__ import annotations

import ctypes
import logging
import platform
import subprocess
import threading
import time

log = logging.getLogger("mk87.powerkeep")

# ----------------------------------------------------------------------
# 平台名 / Windows 常量
# ----------------------------------------------------------------------
WINDOWS = "Windows"
LINUX = "Linux"
DARWIN = "Darwin"

#: SetThreadExecutionState 标志：系统需要保持唤醒（其它条件满足时也不进睡眠）
ES_SYSTEM_REQUIRED = 0x00000001
#: SetThreadExecutionState 标志：让上面的请求持续生效，直到再次调用清除
ES_CONTINUOUS = 0x80000000

#: PROCESS_POWER_THROTTLING_STATE.Version
PROCESS_POWER_THROTTLING_STATE_VERSION = 1
#: PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
PROCESS_POWER_THROTTLING = 4
#: 控制掩码位：执行速度节流（EcoQoS）
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
#: 控制掩码位：忽略系统的计时器精度请求
PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x2

#: 每 30 秒重申一次「系统需要保持唤醒」
REFRESH_INTERVAL = 30.0
#: 等待保活线程完成首次系统调用的上限（秒）
READY_TIMEOUT = 2.0
#: stop() 等待保活线程退出的上限（秒）
JOIN_TIMEOUT = 1.0
#: 等待 systemd-inhibit 退出的上限（秒）
TERMINATE_TIMEOUT = 2

#: Linux 阻止 sleep 的命令（音乐律动进行中由 systemd-inhibit 持有 sleep 阻断锁）
_LINUX_INHIBIT_CMD = (
    "systemd-inhibit",
    "--what=sleep",
    "--mode=block",
    "--who=MK87 Studio",
    "--why=音乐律动进行中（防止系统休眠中断灯效）",
    "--",
    "sleep",
    "infinity",
)


class _PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    """PROCESS_POWER_THROTTLING_STATE（Windows 10 1809+）：ULONG × 3。"""

    _fields_ = [
        ("Version", ctypes.c_ulong),
        ("ControlMask", ctypes.c_ulong),
        ("StateMask", ctypes.c_ulong),
    ]


# ----------------------------------------------------------------------
# 平台探测
# ----------------------------------------------------------------------
def current_system() -> str:
    """当前系统名（``platform.system()``）；单独函数便于测试注入。"""
    try:
        return platform.system()
    except Exception:  # noqa: BLE001 - 探测失败按未知平台处理
        return ""


def _backend_for_system(system: str | None = None) -> str:
    """给定平台「理论上」使用的保活后端名（纯查询，不产生任何系统调用）。"""
    name = system if system is not None else current_system()
    if name == WINDOWS:
        return "windows-execution-state"
    if name == LINUX:
        return "systemd-inhibit"
    return "none"


# ----------------------------------------------------------------------
# Windows：关闭进程能效节流（EcoQoS）+ 忽略计时器精度请求
# ----------------------------------------------------------------------
_throttle_lock = threading.Lock()
#: 进程级缓存（None = 还没调用过）；重复调用直接返回上次结果
_throttle_result: bool | None = None


def _reset_throttle_cache() -> None:
    """清空 ``opt_out_power_throttling`` 的进程级缓存（仅供单测，运行期无需调用）。"""
    global _throttle_result
    with _throttle_lock:
        _throttle_result = None


def _windows_opt_out_power_throttling() -> bool:
    """``SetProcessInformation(ProcessPowerThrottling)`` 实现；失败返回 False 且不抛异常。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        get_current_process = kernel32.GetCurrentProcess
        set_process_information = kernel32.SetProcessInformation
        try:
            get_current_process.argtypes = []
            get_current_process.restype = ctypes.c_void_p
            set_process_information.argtypes = [
                ctypes.c_void_p,      # HANDLE hProcess
                ctypes.c_int,         # PROCESS_INFORMATION_CLASS
                ctypes.c_void_p,      # LPVOID ProcessInformation
                ctypes.c_uint32,      # DWORD ProcessInformationSize
            ]
            set_process_information.restype = ctypes.c_int  # BOOL
        except Exception:  # noqa: BLE001 - 假 DLL / 老系统不关心签名
            pass
        state = _PROCESS_POWER_THROTTLING_STATE()
        state.Version = PROCESS_POWER_THROTTLING_STATE_VERSION
        # 声明要控制「执行速度」与「计时器精度」两项
        state.ControlMask = (PROCESS_POWER_THROTTLING_EXECUTION_SPEED
                             | PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION)
        # 只置位 IGNORE_TIMER_RESOLUTION、不置位 EXECUTION_SPEED → 关闭执行速度节流
        state.StateMask = PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION
        handle = get_current_process()
        ok = set_process_information(
            handle,
            PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        if not ok:
            log.debug("保后台：SetProcessInformation(ProcessPowerThrottling) 返回 0（忽略）")
            return False
        log.debug("保后台：已关闭进程能效节流（EcoQoS），并忽略计时器精度请求")
        return True
    except Exception as exc:  # noqa: BLE001 - 保后台失败绝不影响主流程
        log.debug("保后台：关闭进程能效节流失败（忽略）: %s", exc)
        return False


def opt_out_power_throttling(system: str | None = None) -> bool:
    """Windows：关闭执行速度节流（EcoQoS）并让系统忽略计时器精度请求；其它平台返回 False。

    幂等、不抛异常；模块级缓存，重复调用返回上次结果。
    """
    global _throttle_result
    if (system if system is not None else current_system()) != WINDOWS:
        return False
    with _throttle_lock:
        if _throttle_result is None:
            _throttle_result = _windows_opt_out_power_throttling()
        return _throttle_result


# ----------------------------------------------------------------------
# 保活句柄
# ----------------------------------------------------------------------
class KeepAwake:
    """可重复 start/stop 的保活句柄；任何平台失败都不抛异常，只 log.debug/warning。

    参数
    ----
    system:
        注入的平台名（默认 ``current_system()``），单测用。
    log:
        注入的日志器（默认模块 logger ``mk87.powerkeep``）。

    ``active``：当前是否处于保活状态；``backend``：最近一次生效的后端名
    （``"windows-execution-state"`` / ``"systemd-inhibit"`` / ``"none"``；
    未启动或启动失败时为 ``"none"``，stop 后保留便于诊断）。
    """

    def __init__(self, system: str | None = None, log=None) -> None:
        self._system = system if system is not None else current_system()
        self._log = log if log is not None else logging.getLogger("mk87.powerkeep")
        self._backend = "none"
        self._active = False
        #: 当前平台已判定没有可用手段（避免每次 start 重复失败的系统调用）
        self._failed = False
        self._lock = threading.Lock()
        #: 通知 Windows 保活线程退出
        self._stop_evt = threading.Event()
        #: Windows 保活线程完成首次 SetThreadExecutionState 后置位
        self._ready_evt = threading.Event()
        self._windows_ok = False
        self._thread: threading.Thread | None = None
        #: Linux 的 systemd-inhibit 子进程
        self._proc = None

    # ---------------------------------------------------------- 状态
    @property
    def active(self) -> bool:
        return self._active

    @property
    def backend(self) -> str:
        return self._backend

    # ---------------------------------------------------------- 生命周期
    def start(self) -> bool:
        """开始保活（幂等）；返回是否真的生效。"""
        with self._lock:
            if self._active:
                return True
            if self._failed:
                return False
            system = self._system
            if system == WINDOWS:
                ok = self._start_windows()
            elif system == LINUX:
                ok = self._start_linux()
            else:
                self._log.debug("保后台：平台 %r 不支持，跳过", system)
                self._failed = True
                return False
            self._active = bool(ok)
            if not ok:
                self._failed = True
            return self._active

    def stop(self) -> None:
        """结束保活（幂等，绝不抛异常）。"""
        try:
            with self._lock:
                thread = self._thread
                proc = self._proc
                self._thread = None
                self._proc = None
                self._active = False
            self._stop_evt.set()
            if thread is not None:
                try:
                    thread.join(JOIN_TIMEOUT)
                except Exception:  # noqa: BLE001
                    pass
                if thread.is_alive():
                    self._log.debug("保后台：保活线程未在 %.1fs 内退出", JOIN_TIMEOUT)
            if proc is not None:
                self._stop_linux_proc(proc)
            self._stop_evt.clear()
            self._ready_evt.clear()
        except Exception as exc:  # noqa: BLE001 - stop 绝不抛
            self._log.debug("保后台：停止保活失败（忽略）: %s", exc)

    def __enter__(self) -> "KeepAwake":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
        return None

    # ---------------------------------------------------------- Windows
    def _start_windows(self) -> bool:
        self._ready_evt.clear()
        self._stop_evt.clear()
        self._windows_ok = False
        thread = threading.Thread(
            target=self._windows_keep_awake_loop, name="mk87-keep-awake", daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:  # noqa: BLE001
            self._log.debug("保后台：创建保活线程失败: %s", exc)
            return False
        self._thread = thread
        if not self._ready_evt.wait(READY_TIMEOUT):
            self._log.debug("保后台：保活线程初始化超时（%.1fs）", READY_TIMEOUT)
            self._stop_evt.set()
            try:
                thread.join(JOIN_TIMEOUT)
            except Exception:  # noqa: BLE001
                pass
            self._thread = None
            self._stop_evt.clear()
            return False
        if not self._windows_ok:
            self._stop_evt.set()
            try:
                thread.join(JOIN_TIMEOUT)
            except Exception:  # noqa: BLE001
                pass
            self._thread = None
            self._stop_evt.clear()
            return False
        self._backend = "windows-execution-state"
        self._log.debug("保后台：Windows SetThreadExecutionState + timeBeginPeriod(1) 已生效")
        return True

    def _windows_keep_awake_loop(self) -> None:
        """常驻线程：维持本线程的 ES_CONTINUOUS 状态并每 30s 重申一次。

        注意 ``SetThreadExecutionState`` 的执行状态是 **per-thread** 的：线程退出前
        必须用 ``ES_CONTINUOUS`` 清除，否则该线程的「系统保持唤醒」请求会残留。
        """
        winmm = None
        period_started = False
        try:
            winmm = ctypes.WinDLL("winmm")
        except Exception as exc:  # noqa: BLE001 - 计时器精度只是加分项
            self._log.debug("保后台：加载 winmm 失败（忽略计时器精度）: %s", exc)
            winmm = None
        if winmm is not None:
            try:
                winmm.timeBeginPeriod.argtypes = [ctypes.c_uint32]
                winmm.timeBeginPeriod.restype = ctypes.c_uint32
            except Exception:  # noqa: BLE001
                pass
            try:
                period_started = bool(winmm.timeBeginPeriod(1))
                if not period_started:
                    self._log.debug("保后台：timeBeginPeriod(1) 返回 0（忽略）")
            except Exception as exc:  # noqa: BLE001
                self._log.debug("保后台：timeBeginPeriod(1) 失败（忽略）: %s", exc)

        try:
            kernel32 = ctypes.WinDLL("kernel32")
            set_thread_execution_state = kernel32.SetThreadExecutionState
            try:
                set_thread_execution_state.argtypes = [ctypes.c_uint32]
                set_thread_execution_state.restype = ctypes.c_uint32
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            self._log.debug("保后台：加载 kernel32 失败，无法阻止系统休眠: %s", exc)
            self._windows_ok = False
            self._ready_evt.set()
            if period_started and winmm is not None:
                try:
                    winmm.timeEndPeriod(1)
                except Exception:  # noqa: BLE001
                    pass
            return

        try:
            first = True
            while not self._stop_evt.is_set():
                try:
                    state = set_thread_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                except Exception as exc:  # noqa: BLE001
                    self._log.debug("保后台：SetThreadExecutionState 调用失败（稍后重试）: %s", exc)
                    if first:
                        self._windows_ok = False
                        self._ready_evt.set()
                    first = False
                else:
                    if first:
                        self._windows_ok = bool(state)
                        self._ready_evt.set()
                        if not self._windows_ok:
                            self._log.debug("保后台：SetThreadExecutionState 返回 0（忽略）")
                    first = False
                self._stop_evt.wait(REFRESH_INTERVAL)
        finally:
            # 线程退出前清除本线程的 ES_CONTINUOUS 状态并归还计时器精度
            try:
                set_thread_execution_state(ES_CONTINUOUS)
            except Exception:  # noqa: BLE001
                pass
            if period_started and winmm is not None:
                try:
                    winmm.timeEndPeriod(1)
                except Exception:  # noqa: BLE001
                    pass

    # ---------------------------------------------------------- Linux
    def _start_linux(self) -> bool:
        try:
            proc = subprocess.Popen(
                list(_LINUX_INHIBIT_CMD),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            self._log.debug("保后台：系统没有 systemd-inhibit，无法阻止休眠: %s", exc)
            self._backend = "none"
            return False
        except Exception as exc:  # noqa: BLE001
            self._log.debug("保后台：启动 systemd-inhibit 失败（忽略）: %s", exc)
            self._backend = "none"
            return False
        self._proc = proc
        self._backend = "systemd-inhibit"
        # 收尸线程：避免 systemd-inhibit 退出后留下僵尸进程
        try:
            threading.Thread(
                target=self._reap_linux_proc,
                args=(proc,),
                name="mk87-keep-awake-reaper",
                daemon=True,
            ).start()
        except Exception as exc:  # noqa: BLE001
            self._log.debug("保后台：systemd-inhibit 收尸线程启动失败（忽略）: %s", exc)
        self._log.debug("保后台：已启动 systemd-inhibit（阻止系统 sleep）")
        return True

    @staticmethod
    def _reap_linux_proc(proc) -> None:
        """等待 systemd-inhibit 子进程退出（在 daemon 线程里跑，失败静默）。"""
        try:
            proc.wait()
        except Exception:  # noqa: BLE001
            pass

    def _stop_linux_proc(self, proc) -> None:
        """结束 systemd-inhibit：先 terminate，wait(2s)，再不退出就 kill 兜底。"""
        try:
            proc.terminate()
        except Exception as exc:  # noqa: BLE001
            self._log.debug("保后台：terminate systemd-inhibit 失败（忽略）: %s", exc)
        try:
            proc.wait(timeout=TERMINATE_TIMEOUT)
        except TypeError:
            # 假对象 / 不兼容实现不接受 timeout
            try:
                proc.wait()
            except Exception:  # noqa: BLE001
                pass
        except subprocess.TimeoutExpired:
            self._log.debug("保后台：systemd-inhibit %ss 内未退出，kill 兜底", TERMINATE_TIMEOUT)
        except Exception:  # noqa: BLE001
            pass
        try:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=TERMINATE_TIMEOUT)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass


def keep_awake(system: str | None = None) -> KeepAwake:
    """创建 ``KeepAwake`` 句柄（便于音乐律动用 ``with keep_awake(): ...`` 包裹）。"""
    return KeepAwake(system=system)


def platform_report() -> dict:
    """当前平台的保后台能力摘要（纯查询，不产生任何系统调用/子进程）。

    返回 ``{"system", "keepAwakeBackend", "keepAwakeSupported", "throttlingOptOut"}``；
    ``throttlingOptOut`` 反映 ``opt_out_power_throttling()`` 的缓存结果（没调用过 = False）。
    """
    system = current_system()
    backend = _backend_for_system(system)
    with _throttle_lock:
        throttling = _throttle_result
    return {
        "system": system,
        "keepAwakeBackend": backend,
        "keepAwakeSupported": backend != "none",
        "throttlingOptOut": bool(throttling) if system == WINDOWS else False,
    }
