#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台「保后台」模块 powerkeep 单元测试（纯离线，不真的改系统状态）。

覆盖：
* Windows 保活：``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`` 循环、
  ``timeBeginPeriod(1)``、stop 后 ``ES_CONTINUOUS`` 清除且线程退出、重复 start/stop 幂等、
  kernel32 加载失败 / 返回值 0 时安全降级；
* Windows 节流：``SetProcessInformation`` 返回 1 → True、0 → False 且不抛、结构体掩码正确、
  模块级缓存、异常吞掉、非 Windows 平台不碰 Win32 API；
* Linux 保活：``systemd-inhibit`` 子进程参数、stop 时 terminate / wait(2) / kill 兜底、
  ``FileNotFoundError`` 与其它异常降级为 backend="none"、重复 stop 幂等、stop 后可重启；
* 未知平台 → backend="none"、start False、不调用任何系统 API；
* ``keep_awake()`` 工厂、context manager、``platform_report()`` 结构与语义。

系统调用全部通过 ``mock.patch.object(powerkeep.ctypes, "WinDLL")`` /
``mock.patch.object(powerkeep.subprocess, "Popen")`` 在模块内引用处替换：
不会真的加载 winmm、不会真的拉起 systemd-inhibit。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import powerkeep  # noqa: E402


# ----------------------------------------------------------------------
# 假 ctypes DLL / 假子进程
# ----------------------------------------------------------------------
class FakeFunc:
    """可设置 ``argtypes`` / ``restype`` 的假 ctypes 函数（普通函数不允许设置属性）。"""

    def __init__(self, name: str, result=1, impl=None) -> None:
        self.name = name
        self.result = result
        self.impl = impl
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        if self.impl is not None:
            return self.impl(*args)
        return self.result


class FakeDLL:
    """假的 ``ctypes.WinDLL`` 返回值：按属性名懒创建 ``FakeFunc``。"""

    def __init__(self, name: str, results=None) -> None:
        self.name = name
        self._results = dict(results or {})
        self._funcs = {}

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        funcs = self.__dict__.get("_funcs")
        if funcs is None:
            raise AttributeError(attr)
        if attr not in funcs:
            value = self.__dict__.get("_results", {}).get(attr, 1)
            if callable(value):
                funcs[attr] = FakeFunc(attr, impl=value)
            else:
                funcs[attr] = FakeFunc(attr, result=value)
        return funcs[attr]

    def func(self, name: str) -> FakeFunc:
        return getattr(self, name)


class FakeWinDLLs:
    """记录 ``WinDLL`` 加载，并把 DLL 名映射到 FakeDLL（彻底切断真实系统调用）。"""

    def __init__(self, results=None) -> None:
        self._results = results or {}
        self.loaded = []
        self.dlls = {}

    def windll(self, name, *args, **kwargs):
        self.loaded.append(name)
        dll = self.dlls.get(name)
        if dll is None:
            dll = FakeDLL(name, self._results.get(name))
            self.dlls[name] = dll
        return dll

    def func(self, dll_name: str, func_name: str) -> FakeFunc:
        dll = self.dlls.get(dll_name)
        if dll is None:
            dll = FakeDLL(dll_name, self._results.get(dll_name))
            self.dlls[dll_name] = dll
        return dll.func(func_name)


class FakeProc:
    """``systemd-inhibit`` 子进程替身：记录 terminate/kill/wait，不真起进程。"""

    def __init__(self, *, raise_timeout: bool = False, poll_none: bool = False) -> None:
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = []
        self._raise_timeout = raise_timeout
        self._poll_none = poll_none

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        # 只有 stop() 里带 timeout 的 wait 才模拟超时，收尸线程的无参 wait 立即返回
        if timeout is not None and self._raise_timeout:
            self._raise_timeout = False
            raise subprocess.TimeoutExpired(cmd="systemd-inhibit", timeout=timeout)
        return 0

    def poll(self):
        return None if self._poll_none else 0


def _patch_win_dll(testcase, dlls: FakeWinDLLs) -> None:
    """把模块内引用的 ``ctypes.WinDLL`` 换成 FakeDLL 工厂（非 Windows 上 create=True）。"""
    patcher = mock.patch.object(powerkeep.ctypes, "WinDLL", dlls.windll, create=True)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def _keep_awake_threads() -> list:
    return [t for t in threading.enumerate() if t.name == "mk87-keep-awake"]


# ----------------------------------------------------------------------
# Windows：SetThreadExecutionState + timeBeginPeriod
# ----------------------------------------------------------------------
class TestWindowsKeepAwake(unittest.TestCase):
    def setUp(self):
        self.dlls = FakeWinDLLs({
            "winmm": {"timeBeginPeriod": 1, "timeEndPeriod": 1},
            "kernel32": {"SetThreadExecutionState": 1},
        })
        _patch_win_dll(self, self.dlls)

    def _make(self, **kwargs) -> powerkeep.KeepAwake:
        handle = powerkeep.KeepAwake(system="Windows", **kwargs)
        self.addCleanup(handle.stop)
        return handle

    def test_start_stop_uses_execution_state(self):
        handle = self._make()
        self.assertFalse(handle.active)
        self.assertEqual(handle.backend, "none")

        self.assertTrue(handle.start())
        self.assertTrue(handle.active)
        self.assertEqual(handle.backend, "windows-execution-state")
        self.assertEqual(self.dlls.loaded, ["winmm", "kernel32"])

        winmm = self.dlls.dlls["winmm"]
        self.assertEqual(winmm.func("timeBeginPeriod").calls, [(1,)])
        set_state = self.dlls.dlls["kernel32"].func("SetThreadExecutionState")
        # UINT32 签名：argtypes 输入、restype 返回
        self.assertEqual(set_state.argtypes, [ctypes.c_uint32])
        self.assertEqual(set_state.restype, ctypes.c_uint32)
        self.assertEqual(set_state.calls[0],
                         (powerkeep.ES_CONTINUOUS | powerkeep.ES_SYSTEM_REQUIRED,))
        # 常驻线程已起来（ES_CONTINUOUS 是 per-thread 的，必须同一个线程维护）
        self.assertEqual(len(_keep_awake_threads()), 1)

        handle.stop()
        self.assertFalse(handle.active)
        # 线程退出前用 ES_CONTINUOUS 清除本线程的执行状态请求
        self.assertEqual(set_state.calls[-1], (powerkeep.ES_CONTINUOUS,))
        self.assertEqual(winmm.func("timeEndPeriod").calls, [(1,)])
        self.assertEqual(_keep_awake_threads(), [])

        # 可重复 start/stop：stop 后能再次拉起
        self.assertTrue(handle.start())
        self.assertTrue(handle.active)
        handle.stop()
        self.assertFalse(handle.active)
        self.assertEqual(_keep_awake_threads(), [])

    def test_start_stop_are_idempotent(self):
        handle = self._make()
        self.assertTrue(handle.start())
        threads_before = _keep_awake_threads()
        set_state = self.dlls.dlls["kernel32"].func("SetThreadExecutionState")
        calls_after_first_start = len(set_state.calls)

        self.assertTrue(handle.start())  # 已激活 → 直接 True，不新建线程
        self.assertEqual(_keep_awake_threads(), threads_before)
        self.assertEqual(len(set_state.calls), calls_after_first_start)

        handle.stop()
        handle.stop()  # 重复 stop 不抛异常
        self.assertFalse(handle.active)
        self.assertEqual(_keep_awake_threads(), [])

    def test_execution_state_zero_degrades_to_inactive(self):
        dlls = FakeWinDLLs({
            "winmm": {"timeBeginPeriod": 1},
            "kernel32": {"SetThreadExecutionState": 0},
        })
        patcher = mock.patch.object(powerkeep.ctypes, "WinDLL", dlls.windll, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        handle = self._make()
        self.assertFalse(handle.start())
        self.assertFalse(handle.active)
        self.assertEqual(handle.backend, "none")
        handle.stop()
        self.assertEqual(_keep_awake_threads(), [])

    def test_kernel32_load_failure_degrades(self):
        def factory(name, *args, **kwargs):
            if name == "kernel32":
                raise OSError("kernel32 不可用")
            return self.dlls.windll(name)

        with mock.patch.object(powerkeep.ctypes, "WinDLL", factory, create=True):
            handle = self._make()
            self.assertFalse(handle.start())  # 不抛异常
            self.assertFalse(handle.active)
            self.assertEqual(handle.backend, "none")
            handle.stop()
            self.assertFalse(handle.start())  # 已判定不可用，不重复尝试
        self.assertEqual(_keep_awake_threads(), [])


# ----------------------------------------------------------------------
# Windows：关闭进程能效节流（EcoQoS）
# ----------------------------------------------------------------------
class TestWindowsPowerThrottling(unittest.TestCase):
    def setUp(self):
        powerkeep._reset_throttle_cache()
        self.addCleanup(powerkeep._reset_throttle_cache)
        self.dlls = FakeWinDLLs({
            "kernel32": {"GetCurrentProcess": 1, "SetProcessInformation": 1},
        })
        _patch_win_dll(self, self.dlls)

    def test_opt_out_sets_expected_masks(self):
        self.assertTrue(powerkeep.opt_out_power_throttling(system="Windows"))
        set_info = self.dlls.dlls["kernel32"].func("SetProcessInformation")
        self.assertEqual(len(set_info.calls), 1)
        handle, info_class, state_ref, size = set_info.calls[0]
        self.assertEqual(handle, 1)
        self.assertEqual(info_class, powerkeep.PROCESS_POWER_THROTTLING)
        self.assertEqual(info_class, 4)
        state = state_ref._obj
        self.assertEqual(state.Version, 1)
        self.assertEqual(
            state.ControlMask,
            powerkeep.PROCESS_POWER_THROTTLING_EXECUTION_SPEED
            | powerkeep.PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION,
        )
        self.assertEqual(
            state.StateMask,
            powerkeep.PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION,
        )
        self.assertEqual(size, ctypes.sizeof(powerkeep._PROCESS_POWER_THROTTLING_STATE))

        # 模块级缓存：重复调用返回上次结果，不再碰系统 API
        self.assertTrue(powerkeep.opt_out_power_throttling(system="Windows"))
        self.assertEqual(len(set_info.calls), 1)

    def test_opt_out_zero_is_false_without_raising(self):
        self.dlls.func("kernel32", "SetProcessInformation").result = 0
        self.assertFalse(powerkeep.opt_out_power_throttling(system="Windows"))
        set_info = self.dlls.func("kernel32", "SetProcessInformation")
        self.assertEqual(len(set_info.calls), 1)
        # 失败结果同样缓存
        self.assertFalse(powerkeep.opt_out_power_throttling(system="Windows"))
        self.assertEqual(len(set_info.calls), 1)

    def test_opt_out_swallows_exception(self):
        def boom(*args, **kwargs):
            raise OSError("拒绝访问")

        self.dlls.func("kernel32", "SetProcessInformation").impl = boom
        self.assertFalse(powerkeep.opt_out_power_throttling(system="Windows"))

    def test_other_platforms_do_not_touch_win32(self):
        for system in ("Linux", "Darwin", "FreeBSD", ""):
            self.assertFalse(powerkeep.opt_out_power_throttling(system=system))
        self.assertEqual(self.dlls.loaded, [])

    def test_default_uses_current_system(self):
        with mock.patch.object(powerkeep, "current_system", return_value="Linux"):
            self.assertFalse(powerkeep.opt_out_power_throttling())
        with mock.patch.object(powerkeep, "current_system", return_value="Windows"):
            self.assertTrue(powerkeep.opt_out_power_throttling())


# ----------------------------------------------------------------------
# Linux：systemd-inhibit
# ----------------------------------------------------------------------
class TestLinuxKeepAwake(unittest.TestCase):
    def _start(self, proc, **popen_kwargs):
        patcher = mock.patch.object(powerkeep.subprocess, "Popen", return_value=proc,
                                    **popen_kwargs)
        popen = patcher.start()
        self.addCleanup(patcher.stop)
        handle = powerkeep.KeepAwake(system="Linux")
        self.addCleanup(handle.stop)
        return handle, popen

    def test_start_stop_inhibit_process(self):
        proc = FakeProc()
        handle, popen = self._start(proc)
        self.assertFalse(handle.active)
        self.assertTrue(handle.start())
        self.assertTrue(handle.active)
        self.assertEqual(handle.backend, "systemd-inhibit")

        popen.assert_called_once()
        cmd = list(popen.call_args.args[0])
        kwargs = popen.call_args.kwargs
        self.assertEqual(cmd[0], "systemd-inhibit")
        self.assertIn("--what=sleep", cmd)
        self.assertIn("--mode=block", cmd)
        self.assertIn("--who=MK87 Studio", cmd)
        self.assertTrue(any(arg.startswith("--why=") for arg in cmd))
        self.assertEqual(cmd[-2:], ["sleep", "infinity"])
        self.assertEqual(kwargs, {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        })

        handle.stop()
        self.assertFalse(handle.active)
        self.assertEqual(proc.terminate_calls, 1)
        self.assertIn(2, proc.wait_calls)  # wait(timeout=2) 第一轮
        handle.stop()  # 幂等：不重复 terminate
        self.assertEqual(proc.terminate_calls, 1)

    def test_kill_fallback_when_terminate_times_out(self):
        proc = FakeProc(raise_timeout=True, poll_none=True)
        handle, _popen = self._start(proc)
        self.assertTrue(handle.start())
        handle.stop()
        self.assertEqual(proc.terminate_calls, 1)
        self.assertEqual(proc.kill_calls, 1)  # wait(2) 超时且进程未退出 → kill 兜底

    def test_missing_systemd_inhibit_degrades(self):
        with mock.patch.object(powerkeep.subprocess, "Popen",
                               side_effect=FileNotFoundError("no systemd-inhibit")) as popen:
            handle = powerkeep.KeepAwake(system="Linux")
            self.addCleanup(handle.stop)
            self.assertFalse(handle.start())
            self.assertFalse(handle.active)
            self.assertEqual(handle.backend, "none")
            self.assertFalse(handle.start())  # 已判定不可用，不重复尝试
            handle.stop()  # 幂等且不抛
        self.assertEqual(popen.call_count, 1)

    def test_generic_popen_error_degrades(self):
        with mock.patch.object(powerkeep.subprocess, "Popen",
                               side_effect=OSError("权限不足")):
            handle = powerkeep.KeepAwake(system="Linux")
            self.addCleanup(handle.stop)
            self.assertFalse(handle.start())
            self.assertEqual(handle.backend, "none")

    def test_restart_after_stop(self):
        first, second = FakeProc(), FakeProc()
        with mock.patch.object(powerkeep.subprocess, "Popen",
                               side_effect=[first, second]) as popen:
            handle = powerkeep.KeepAwake(system="Linux")
            self.addCleanup(handle.stop)
            self.assertTrue(handle.start())
            handle.stop()
            self.assertTrue(handle.start())
            self.assertTrue(handle.active)
            self.assertEqual(popen.call_count, 2)
            handle.stop()
        self.assertEqual(first.terminate_calls, 1)
        self.assertEqual(second.terminate_calls, 1)


# ----------------------------------------------------------------------
# 未知平台 / 工厂 / context manager
# ----------------------------------------------------------------------
class TestUnknownPlatform(unittest.TestCase):
    def test_unknown_system_does_nothing(self):
        for system in ("Darwin", "FreeBSD", "Java", ""):
            with mock.patch.object(powerkeep.ctypes, "WinDLL",
                                   side_effect=AssertionError("不应加载 Windows DLL"),
                                   create=True), \
                    mock.patch.object(powerkeep.subprocess, "Popen",
                                      side_effect=AssertionError("不应拉子进程")):
                handle = powerkeep.KeepAwake(system=system)
                self.assertEqual(handle.backend, "none")
                self.assertFalse(handle.start())
                self.assertFalse(handle.active)
                handle.stop()
                self.assertFalse(handle.active)


class TestFactoryAndContextManager(unittest.TestCase):
    def test_current_system_returns_string(self):
        self.assertIsInstance(powerkeep.current_system(), str)

    def test_keep_awake_factory_uses_current_system(self):
        with mock.patch.object(powerkeep, "current_system", return_value="FreeBSD"):
            handle = powerkeep.keep_awake()
        self.assertIsInstance(handle, powerkeep.KeepAwake)
        self.assertFalse(handle.start())
        self.assertEqual(handle.backend, "none")
        handle.stop()

    def test_context_manager_starts_and_stops(self):
        proc = FakeProc()
        with mock.patch.object(powerkeep.subprocess, "Popen", return_value=proc):
            handle = powerkeep.keep_awake(system="Linux")
            self.addCleanup(handle.stop)
            with handle as entered:
                self.assertIs(entered, handle)
                self.assertTrue(handle.active)
            self.assertFalse(handle.active)
            self.assertEqual(proc.terminate_calls, 1)

    def test_context_manager_does_not_swallow_exceptions(self):
        handle = powerkeep.keep_awake(system="FreeBSD")  # start 失败也不影响异常传播
        with self.assertRaises(ValueError):
            with handle:
                raise ValueError("boom")
        self.assertFalse(handle.active)


# ----------------------------------------------------------------------
# platform_report
# ----------------------------------------------------------------------
class TestPlatformReport(unittest.TestCase):
    def setUp(self):
        powerkeep._reset_throttle_cache()
        self.addCleanup(powerkeep._reset_throttle_cache)

    def _report(self, system: str) -> dict:
        with mock.patch.object(powerkeep, "current_system", return_value=system):
            return powerkeep.platform_report()

    def test_structure_and_windows(self):
        report = self._report("Windows")
        self.assertEqual(set(report), {
            "system", "keepAwakeBackend", "keepAwakeSupported", "throttlingOptOut",
        })
        self.assertEqual(report["system"], "Windows")
        self.assertEqual(report["keepAwakeBackend"], "windows-execution-state")
        self.assertTrue(report["keepAwakeSupported"])
        self.assertFalse(report["throttlingOptOut"])

    def test_linux(self):
        report = self._report("Linux")
        self.assertEqual(report["keepAwakeBackend"], "systemd-inhibit")
        self.assertTrue(report["keepAwakeSupported"])
        self.assertFalse(report["throttlingOptOut"])

    def test_unknown_platform(self):
        report = self._report("FreeBSD")
        self.assertEqual(report["keepAwakeBackend"], "none")
        self.assertFalse(report["keepAwakeSupported"])
        self.assertFalse(report["throttlingOptOut"])

    def test_reflects_throttle_optout_cache(self):
        dlls = FakeWinDLLs({
            "kernel32": {"GetCurrentProcess": 1, "SetProcessInformation": 1},
        })
        with mock.patch.object(powerkeep.ctypes, "WinDLL", dlls.windll, create=True), \
                mock.patch.object(powerkeep, "current_system", return_value="Windows"):
            self.assertTrue(powerkeep.opt_out_power_throttling())
            report = powerkeep.platform_report()
        self.assertTrue(report["throttlingOptOut"])


if __name__ == "__main__":
    unittest.main()
