#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.1.8.6「Windows 托盘消失 / 单实例唤起失败」修复的单元测试。

覆盖：
* ``mk87lib.tray_win``：任务栏/Explorer 句柄快照、Shell_NotifyIconGetRect 状态
  （visible/hidden/missing/unknown）、『显示隐藏的图标』溢出注册表、pystray 图标
  窗口枚举、唤起窗口兜底、汇总 probe（全部用注入的 fake Win32 API，不碰真实托盘）；
* ``shell.SingleInstance``：Windows 互斥量 / Linux 文件锁、instance.json 读写；
* ``shell._post_activate`` / ``_activate_existing`` / ``_handle_existing_instance``：
  唤起成功、HTTP 200 但 ok=false、超时/连接失败、重试时重新读端口、失败必须弹窗
  且返回非 0（**绝不**继续启动第二个实例）；
* ``shell._reuse_running_instance_if_any``：旧版本实例（未持有互斥量）仍活着时复用；
* ``shell.Shell`` 托盘降级：托盘不可用时点 X 只最小化 + 提示一次、不隐藏不退出；
  托盘实测状态到 ``_tray_available`` / ``tray_state`` 的映射；首次隐藏气泡含
  『显示隐藏的图标』提示（EnableAutoTray 语义）；
* ``shell.TrayWatchdog`` 状态机：Explorer 重启 token 变化、连续 missing 才重建、
  重建节流/上限后放弃、探测异常不重建；
* ``shell.main`` 单实例分支：唤起成功返回 0、失败返回 2、拿到互斥量后继续启动。

测试不依赖真实托盘 / 真实 Explorer / 真实 MessageBox / 真实键盘。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

import shell  # noqa: E402
from mk87lib import tray_win  # noqa: E402

#: 保存真实实现（仅用于测试 _message_box 本身），并给整个测试模块装上安全网：
#: 任何路径都不允许真的弹出 Windows MessageBox 打扰用户桌面。
_REAL_MESSAGE_BOX = shell._message_box
_MESSAGE_BOX_PATCH = None


def setUpModule():
    global _MESSAGE_BOX_PATCH
    _MESSAGE_BOX_PATCH = mock.patch.object(
        shell, "_message_box", mock.MagicMock(name="no-real-message-box"))
    _MESSAGE_BOX_PATCH.start()


def tearDownModule():
    if _MESSAGE_BOX_PATCH is not None:
        _MESSAGE_BOX_PATCH.stop()


# ----------------------------------------------------------------------
# fakes
# ----------------------------------------------------------------------
class FakeApi:
    """tray_win.Win32Api 的 fake（只实现被调用的查询方法）。"""

    def __init__(self, *, taskbar=65676, shell_window=262176, taskbar_visible=True,
                 rects=None, windows=None, iconic=False, foreground=True,
                 flash=True, visible_windows=None):
        self.taskbar = taskbar
        self.shell_window = shell_window
        self.taskbar_visible = taskbar_visible
        self.rects = dict(rects or {})          # (hwnd, uid) -> (hr, rect)
        self.windows = list(windows or [])      # [{hwnd,class,pid,title,visible}]
        self.iconic = iconic
        self.foreground = foreground
        self.flash = flash
        self.visible_windows = visible_windows or set()
        self.calls = []

    def _window(self, hwnd):
        for item in self.windows:
            if int(item.get("hwnd")) == int(hwnd):
                return item
        return {}

    # --- 查询
    def find_window(self, class_name, title=None):
        self.calls.append(("find_window", class_name, title))
        if class_name == "Shell_TrayWnd":
            return self.taskbar
        if class_name is None and title is not None:
            for item in self.windows:
                if item.get("title") == title:
                    return item["hwnd"]
        return 0

    def get_shell_window(self):
        return self.shell_window

    def get_class_name(self, hwnd):
        return self._window(hwnd).get("class", "")

    def get_window_text(self, hwnd):
        return self._window(hwnd).get("title", "")

    def is_window_visible(self, hwnd):
        if int(hwnd) == int(self.taskbar):
            return bool(self.taskbar_visible)
        return int(hwnd) in self.visible_windows

    def process_id_of_window(self, hwnd):
        return int(self._window(hwnd).get("pid", 0))

    def enum_windows(self):
        return [int(item["hwnd"]) for item in self.windows]

    def shell_notify_icon_get_rect(self, hwnd, u_id):
        self.calls.append(("get_rect", int(hwnd), int(u_id)))
        return self.rects.get((int(hwnd), int(u_id)), (tray_win.E_FAIL, None))

    # --- 唤起窗口兜底
    def is_iconic(self, hwnd):
        return bool(self.iconic)

    def show_window_async(self, hwnd, cmd):
        self.calls.append(("show_window_async", int(hwnd), int(cmd)))
        return True

    def set_foreground_window(self, hwnd):
        self.calls.append(("set_foreground_window", int(hwnd)))
        return bool(self.foreground)

    def flash_window(self, hwnd):
        self.calls.append(("flash_window", int(hwnd)))
        return bool(self.flash)


class BrokenApi:
    """所有方法都抛异常：验证诊断代码绝不向上抛。"""

    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise OSError(f"boom:{name}")
        return _boom


class FakeKernel32:
    def __init__(self, *, already=False, raise_on_create=False):
        self.already = already
        self.raise_on_create = raise_on_create
        self.created = []
        self.closed = []

    def create_mutex(self, name):
        if self.raise_on_create:
            raise OSError("CreateMutexW 不可用")
        self.created.append(name)
        return 1234, self.already

    def close(self, handle):
        self.closed.append(handle)


class FakeInstance:
    def __init__(self, port=None):
        self.port = port
        self.written = []

    def read_port(self):
        return self.port

    def write_port(self, port):
        self.written.append(port)


class FakeIcon:
    def __init__(self, *, running=True):
        self.stops = 0
        self._running = running

    def stop(self):
        self.stops += 1

    def run(self):
        """pystray Icon.run 的替身：空实现，线程立刻结束。"""


class FakeThread:
    def __init__(self, alive_sequence):
        self._alive = list(alive_sequence)
        self.joined = []

    def is_alive(self):
        if self._alive:
            return bool(self._alive.pop(0))
        return False

    def join(self, timeout=None):
        self.joined.append(timeout)


class FakeResp:
    def __init__(self, payload, *, status=200):
        self._payload = payload if isinstance(payload, bytes) else str(payload).encode()
        self.status = status

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(payload, *, status=200, capture=None):
    def _open(req, timeout=None, **kwargs):
        if capture is not None:
            capture.append({"url": getattr(req, "full_url", str(req)),
                            "timeout": timeout})
        return FakeResp(payload, status=status)
    return _open


def reader_returning(value):
    def _read(path, name):
        return value
    return _read


def make_shell(**kwargs):
    """构造一个不依赖真实 webview 的 Shell（只填托盘相关字段）。"""
    sh = shell.Shell(silent=True, **kwargs)
    sh.window = mock.MagicMock()
    sh.manager = SimpleNamespace(shell_mode=True)
    return sh


class Win32TestMixin:
    """让 Win32 相关单测在 Linux CI 上也按 Windows 语义跑（fake API + 平台打补丁）。"""

    def setUp(self):
        super().setUp()
        patches = [
            mock.patch.object(tray_win, "supported", lambda: True),
            mock.patch.object(sys, "platform", "win32"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)


# ----------------------------------------------------------------------
# tray_win：平台判断 / 环境
# ----------------------------------------------------------------------
class TestTrayWinEnvironment(Win32TestMixin, unittest.TestCase):
    def test_environment_present(self):
        api = FakeApi()
        env = tray_win.environment(api=api)
        self.assertEqual(env["platform"], sys.platform)
        self.assertTrue(env["supported"])
        self.assertTrue(env["present"])
        self.assertEqual(env["taskbarHwnd"], 65676)
        self.assertEqual(env["shellHwnd"], 262176)
        self.assertIsNone(env["error"])

    def test_environment_no_taskbar(self):
        env = tray_win.environment(api=FakeApi(taskbar=0))
        self.assertFalse(env["present"])
        self.assertEqual(env["error"], "taskbar-not-found")

    def test_environment_invisible_taskbar(self):
        env = tray_win.environment(api=FakeApi(taskbar_visible=False))
        self.assertFalse(env["present"])

    def test_environment_api_error_is_swallowed(self):
        env = tray_win.environment(api=BrokenApi())
        self.assertFalse(env["present"])
        self.assertIn("boom", env["error"])

    def test_environment_non_windows(self):
        with mock.patch.object(tray_win, "supported", lambda: False), \
                mock.patch.object(sys, "platform", "linux"):
            env = tray_win.environment()
        self.assertFalse(env["supported"])
        self.assertEqual(env["error"], "not-windows")

    def test_environment_token(self):
        api = FakeApi()
        self.assertEqual(tray_win.environment_token(api=api), (65676, 262176))
        self.assertIsNone(tray_win.environment_token(api=FakeApi(taskbar=0)))

    def test_environment_token_changes_after_explorer_restart(self):
        first = tray_win.environment_token(api=FakeApi(taskbar=111, shell_window=222))
        second = tray_win.environment_token(api=FakeApi(taskbar=333, shell_window=444))
        self.assertNotEqual(first, second)


class TestOverflowRegistry(unittest.TestCase):
    def test_auto_hide_on(self):
        info = tray_win.overflow_info(reader=reader_returning(1))
        self.assertEqual(info["enableAutoTray"], 1)
        self.assertTrue(info["autoHide"])
        self.assertEqual(info["source"], "registry")
        self.assertIn("显示隐藏的图标", info["hint"])

    def test_show_all_icons(self):
        info = tray_win.overflow_info(reader=reader_returning(0))
        self.assertEqual(info["enableAutoTray"], 0)
        self.assertFalse(info["autoHide"])
        self.assertEqual(info["hint"], "")

    def test_missing_value_defaults_to_auto_hide(self):
        info = tray_win.overflow_info(reader=reader_returning(None))
        self.assertIsNone(info["enableAutoTray"])
        self.assertTrue(info["autoHide"])
        self.assertEqual(info["source"], "default")

    def test_reader_failure_defaults_to_auto_hide(self):
        def _broken(path, name):
            raise OSError("registry unavailable")

        info = tray_win.overflow_info(reader=_broken)
        self.assertTrue(info["autoHide"])
        self.assertTrue(tray_win.auto_hide_enabled(reader=_broken))

    def test_read_registry_dword_non_windows_is_safe(self):
        with mock.patch.object(tray_win, "supported", lambda: False):
            self.assertIsNone(tray_win.read_registry_dword("X", "Y"))


# ----------------------------------------------------------------------
# tray_win：图标注册状态
# ----------------------------------------------------------------------
class TestIconState(Win32TestMixin, unittest.TestCase):
    HWND = 43210

    def test_visible(self):
        api = FakeApi(rects={(self.HWND, 0):
                             (tray_win.S_OK, {"left": 1, "top": 2, "right": 3, "bottom": 4})})
        out = tray_win.icon_state(self.HWND, 0, api=api)
        self.assertEqual(out["state"], tray_win.STATE_VISIBLE)
        self.assertTrue(out["registered"])
        self.assertTrue(out["visible"])
        self.assertEqual(out["rect"]["top"], 2)
        self.assertEqual(out["hr"], 0)

    def test_hidden_in_overflow(self):
        api = FakeApi(rects={(self.HWND, 0): (tray_win.S_FALSE, None)})
        out = tray_win.icon_state(self.HWND, 0, api=api)
        self.assertEqual(out["state"], tray_win.STATE_HIDDEN)
        self.assertTrue(out["registered"])
        self.assertTrue(out["hidden"])
        self.assertFalse(out["visible"])

    def test_missing(self):
        out = tray_win.icon_state(self.HWND, 0, api=FakeApi())
        self.assertEqual(out["state"], tray_win.STATE_MISSING)
        self.assertFalse(out["registered"])
        self.assertEqual(out["hr"], tray_win.E_FAIL)

    def test_other_hresult_is_unknown_not_missing(self):
        hr = -2147024891  # 0x80070005 E_ACCESSDENIED
        api = FakeApi(rects={(self.HWND, 0): (hr, None)})
        out = tray_win.icon_state(self.HWND, 0, api=api)
        self.assertEqual(out["state"], tray_win.STATE_UNKNOWN)
        self.assertIn("hr=", out["error"])

    def test_zero_hwnd_is_missing_without_api_call(self):
        api = FakeApi()
        out = tray_win.icon_state(0, 0, api=api)
        self.assertEqual(out["state"], tray_win.STATE_MISSING)
        self.assertEqual(api.calls, [])

    def test_api_error_is_swallowed(self):
        out = tray_win.icon_state(self.HWND, 0, api=BrokenApi())
        self.assertEqual(out["state"], tray_win.STATE_UNKNOWN)
        self.assertIn("boom:shell_notify_icon_get_rect", out["error"])

    def test_non_windows(self):
        with mock.patch.object(tray_win, "supported", lambda: False):
            out = tray_win.icon_state(self.HWND, 0)
        self.assertEqual(out["state"], tray_win.STATE_UNKNOWN)
        self.assertEqual(out["error"], "not-windows")

    def test_probe_icon_uids_are_truncated_to_uint32(self):
        # pystray 传 id(self)（64 位）→ Win32 UINT 截断；probe 候选也要按 32 位比。
        uid = 7
        api = FakeApi(rects={(self.HWND, uid): (tray_win.S_OK, None)})
        out = tray_win.probe_icon(self.HWND, u_ids=[0, (1 << 32) + uid], api=api)
        self.assertTrue(out["registered"])
        self.assertEqual(out["uID"], uid)
        self.assertEqual(len(out["attempts"]), 2)

    def test_probe_icon_first_candidate_matches(self):
        api = FakeApi(rects={(self.HWND, 0): (tray_win.S_OK, None)})
        out = tray_win.probe_icon(self.HWND, u_ids=[0, 99], api=api)
        self.assertTrue(out["registered"])
        self.assertEqual([c for c in api.calls if c[0] == "get_rect"],
                         [("get_rect", self.HWND, 0)])


class TestFindIconHwnds(Win32TestMixin, unittest.TestCase):
    def test_filters_by_pid_and_class_suffix(self):
        api = FakeApi(windows=[
            {"hwnd": 1, "class": "mk87studio111SystemTrayIcon", "pid": 100},
            {"hwnd": 2, "class": "mk87studio111SystemTrayIcon", "pid": 100},
            {"hwnd": 3, "class": "other222SystemTrayIcon", "pid": 100},
            {"hwnd": 4, "class": "mk87studio333SystemTrayIcon", "pid": 999},
        ])
        found = tray_win.find_icon_hwnds(pid=100, name="mk87studio", api=api)
        self.assertEqual([item["hwnd"] for item in found], [1, 2])

    def test_name_filter(self):
        api = FakeApi(windows=[
            {"hwnd": 1, "class": "mk87studio111SystemTrayIcon", "pid": 100},
            {"hwnd": 2, "class": "foo222SystemTrayIcon", "pid": 100},
        ])
        found = tray_win.find_icon_hwnds(pid=100, name="mk87studio", api=api)
        self.assertEqual([item["hwnd"] for item in found], [1])

    def test_non_windows_returns_empty(self):
        with mock.patch.object(tray_win, "supported", lambda: False):
            self.assertEqual(tray_win.find_icon_hwnds(pid=1), [])

    def test_api_error_returns_partial(self):
        api = BrokenApi()
        self.assertEqual(tray_win.find_icon_hwnds(pid=1, api=api), [])


# ----------------------------------------------------------------------
# tray_win：唤起窗口 / 汇总 probe
# ----------------------------------------------------------------------
class TestForegroundWindow(Win32TestMixin, unittest.TestCase):
    TITLE = "MK87 Studio"

    def _api(self, **kwargs):
        defaults = dict(windows=[{"hwnd": 555, "class": "WindowsForms10.Window",
                                  "pid": 4242, "title": self.TITLE}])
        defaults.update(kwargs)
        return FakeApi(**defaults)

    def test_iconic_window_restored_and_foregrounded(self):
        api = self._api(iconic=True, foreground=True)
        out = tray_win.foreground_app_window(self.TITLE, 4242, api=api)
        self.assertTrue(out["found"])
        self.assertEqual(out["hwnd"], 555)
        self.assertTrue(out["restored"])
        self.assertTrue(out["foreground"])
        self.assertIn(("show_window_async", 555, tray_win.SW_RESTORE), api.calls)

    def test_foreground_failure_flashes_taskbar(self):
        api = self._api(iconic=False, foreground=False, flash=True)
        out = tray_win.foreground_app_window(self.TITLE, 4242, api=api)
        self.assertFalse(out["foreground"])
        self.assertTrue(out["flashed"])
        self.assertIn(("show_window_async", 555, tray_win.SW_SHOW), api.calls)
        self.assertIn(("flash_window", 555), api.calls)

    def test_window_not_found(self):
        out = tray_win.foreground_app_window(self.TITLE, 4242, api=FakeApi())
        self.assertFalse(out["found"])
        self.assertEqual(out["error"], "window-not-found")

    def test_found_by_enumeration_when_find_window_misses(self):
        # FindWindowW 只按标题找；标题匹配但 PID 不符时必须枚举找本进程窗口。
        api = self._api()
        api.windows.append({"hwnd": 556, "class": "X", "pid": 4242,
                            "title": self.TITLE})
        # 让 find_window 返回别的进程的窗口
        api.windows[0]["pid"] = 777
        out = tray_win.foreground_app_window(self.TITLE, 4242, api=api)
        self.assertTrue(out["found"])
        self.assertEqual(out["hwnd"], 556)

    def test_api_error_is_swallowed(self):
        out = tray_win.foreground_app_window(self.TITLE, 4242, api=BrokenApi())
        self.assertFalse(out["found"])
        self.assertIn("boom", out["error"])

    def test_non_windows(self):
        with mock.patch.object(tray_win, "supported", lambda: False):
            out = tray_win.foreground_app_window()
        self.assertEqual(out["error"], "not-windows")


class TestProbeSummary(Win32TestMixin, unittest.TestCase):
    HWND = 777

    def test_probe_with_tray_and_window(self):
        api = FakeApi(
            rects={(self.HWND, 0): (tray_win.S_FALSE, None)},
            windows=[{"hwnd": self.HWND, "class": "mk87studio1SystemTrayIcon",
                      "pid": os.getpid()}],
        )
        tray = SimpleNamespace(_hwnd=self.HWND)
        out = tray_win.probe(tray=tray, pid=os.getpid(),
                             reader=reader_returning(1), api=api)
        self.assertTrue(out["supported"])
        self.assertTrue(out["taskbar"]["present"])
        self.assertTrue(out["overflow"]["autoHide"])
        self.assertEqual(out["icon"]["state"], tray_win.STATE_HIDDEN)
        self.assertTrue(out["icon"]["registered"])
        json.dumps(out)  # 必须 JSON 可序列化（/api/tray/status）

    def test_probe_uses_icon_windows_fallback(self):
        api = FakeApi(
            rects={(self.HWND, 0): (tray_win.S_OK, None)},
            windows=[{"hwnd": self.HWND, "class": "mk87studio1SystemTrayIcon",
                      "pid": os.getpid()}],
        )
        out = tray_win.probe(pid=os.getpid(), reader=reader_returning(None), api=api)
        self.assertTrue(out["icon"]["registered"])
        self.assertEqual(out["iconWindows"][0]["hwnd"], self.HWND)

    def test_probe_fallback_skips_unregistered_menu_window(self):
        """pystray 有 2 个同前缀窗口：枚举时不能只查第一个（可能是菜单窗口）。"""
        menu_hwnd, icon_hwnd = 11, 22
        api = FakeApi(
            rects={(icon_hwnd, 0): (tray_win.S_OK, None)},
            windows=[
                {"hwnd": menu_hwnd, "class": "mk87studio1SystemTrayIcon",
                 "pid": os.getpid()},
                {"hwnd": icon_hwnd, "class": "mk87studio1SystemTrayIcon",
                 "pid": os.getpid()},
            ],
        )
        out = tray_win.probe(pid=os.getpid(), reader=reader_returning(1), api=api)
        self.assertTrue(out["icon"]["registered"])
        self.assertEqual(out["icon"]["hwnd"], icon_hwnd)
        self.assertEqual(len(out["iconWindows"]), 2)  # 2 个窗口属正常

    def test_probe_without_pid_does_not_guess_other_process_windows(self):
        api = FakeApi(windows=[{"hwnd": 33, "class": "other1SystemTrayIcon", "pid": 9}])
        out = tray_win.probe(reader=reader_returning(1), api=api)
        self.assertEqual(out["iconWindows"], [])
        self.assertEqual(out["icon"]["state"], tray_win.STATE_UNKNOWN)

    def test_probe_never_raises(self):
        out = tray_win.probe(pid=os.getpid(), api=BrokenApi())
        self.assertIsInstance(out, dict)
        json.dumps(out)
        self.assertIn("boom", out["taskbar"]["error"])

    def test_probe_non_windows(self):
        with mock.patch.object(tray_win, "supported", lambda: False), \
                mock.patch.object(tray_win, "environment",
                                  lambda **kw: {"present": False,
                                                "error": "not-windows"}):
            out = tray_win.probe()
        self.assertFalse(out["supported"])
        self.assertEqual(out["error"], "not-windows")


# ----------------------------------------------------------------------
# shell.SingleInstance
# ----------------------------------------------------------------------
class TestSingleInstance(unittest.TestCase):
    def test_win32_first_instance(self):
        k32 = FakeKernel32(already=False)
        with tempfile.TemporaryDirectory() as tmp:
            inst = shell.SingleInstance(directory=tmp)
            self.assertTrue(inst.acquire(platform="win32", kernel32=k32))
            self.assertEqual(k32.created, [shell.LOCK_NAME])
            inst.release()
        self.assertEqual(k32.closed, [1234])

    def test_win32_existing_instance_closes_own_handle(self):
        k32 = FakeKernel32(already=True)
        with tempfile.TemporaryDirectory() as tmp:
            inst = shell.SingleInstance(directory=tmp)
            self.assertFalse(inst.acquire(platform="win32", kernel32=k32))
        self.assertEqual(k32.closed, [1234])

    def test_win32_mutex_error_degrades_to_start(self):
        k32 = FakeKernel32(raise_on_create=True)
        marks = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(shell.bootlog, "mark",
                                  lambda stage, **kw: marks.append(stage)):
            inst = shell.SingleInstance(directory=tmp)
            # 互斥量创建不了不能把用户挡在外面：返回 True，退化到端口探测
            self.assertTrue(inst.acquire(platform="win32", kernel32=k32))
        self.assertIn("single-instance-mutex-error", marks)

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows 验证真实命名互斥量")
    def test_real_win32_mutex(self):
        k32 = shell._win_kernel32()
        name = f"MK87StudioUnitTest-{os.getpid()}-{time.time_ns()}"
        h1, already1 = k32.create_mutex(name)
        h2, already2 = k32.create_mutex(name)
        try:
            self.assertFalse(already1, "新名字的互斥量不应已存在")
            self.assertTrue(already2, "同名互斥量应报告已存在")
        finally:
            k32.close(h1)
            k32.close(h2)
        h3, already3 = k32.create_mutex(name)
        try:
            self.assertFalse(already3, "句柄都关闭后互斥量应消失")
        finally:
            k32.close(h3)

    @unittest.skipUnless(sys.platform.startswith("linux"), "仅 Linux 验证文件锁")
    def test_linux_flock(self):
        try:
            import fcntl  # noqa: F401
        except ImportError:  # 在 Windows 上模拟 Linux 平台跑测试时跳过
            self.skipTest("当前环境没有 fcntl")
        with tempfile.TemporaryDirectory() as tmp:
            first = shell.SingleInstance(directory=tmp)
            self.assertTrue(first.acquire(platform="linux"))
            second = shell.SingleInstance(directory=tmp)
            self.assertFalse(second.acquire(platform="linux"))
            first.release()
            third = shell.SingleInstance(directory=tmp)
            self.assertTrue(third.acquire(platform="linux"))
            third.release()

    def test_instance_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = shell.SingleInstance(directory=tmp)
            inst.write_port(65447)
            self.assertEqual(inst.read_port(), 65447)
            info = inst.read_info()
            self.assertEqual(info["pid"], os.getpid())
            self.assertEqual(info["port"], 65447)

    def test_instance_json_missing_or_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = shell.SingleInstance(directory=tmp)
            self.assertIsNone(inst.read_port())
            self.assertEqual(inst.read_info(), {})
            with open(inst.lock_file, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertIsNone(inst.read_port())

    def test_acquire_single_instance_holds_global(self):
        old = shell._INSTANCE
        k32 = FakeKernel32(already=False)
        try:
            with mock.patch.object(shell, "SingleInstance", autospec=True) as cls, \
                    mock.patch.object(shell, "_release_single_instance"):
                fake = cls.return_value
                fake.acquire.return_value = True
                instance = shell._acquire_single_instance()
                self.assertIs(instance, fake)
                self.assertIs(shell._INSTANCE, fake)
        finally:
            shell._INSTANCE = old


# ----------------------------------------------------------------------
# shell 单实例唤起
# ----------------------------------------------------------------------
class TestPostActivate(unittest.TestCase):
    def test_success(self):
        cap = []
        payload = json.dumps({"ok": True, "activated": True}).encode()
        with mock.patch("urllib.request.urlopen",
                        fake_urlopen(payload, capture=cap)):
            ok, info = shell._post_activate(65447, timeout=1.0)
        self.assertTrue(ok)
        self.assertEqual(info["status"], 200)
        self.assertEqual(cap[0]["url"], "http://127.0.0.1:65447/api/activate")

    def test_http_200_but_activate_rejected_is_failure(self):
        """核心 bug：旧代码只看 HTTP 200，这里必须解析 body 的 ok/activated。"""
        payload = json.dumps({"ok": False, "activated": False,
                              "message": "无窗口外壳（浏览器模式）"}).encode()
        with mock.patch("urllib.request.urlopen", fake_urlopen(payload)):
            ok, info = shell._post_activate(65447)
        self.assertFalse(ok)
        self.assertIn("无窗口外壳", info["error"])

    def test_callback_error_in_body_is_failure(self):
        payload = json.dumps({"ok": False, "error": "窗口已销毁"}).encode()
        with mock.patch("urllib.request.urlopen", fake_urlopen(payload)):
            ok, info = shell._post_activate(65447)
        self.assertFalse(ok)
        self.assertEqual(info["error"], "窗口已销毁")

    def test_http_error_status_is_failure(self):
        payload = b'{"ok": true}'
        with mock.patch("urllib.request.urlopen",
                        fake_urlopen(payload, status=500)):
            ok, info = shell._post_activate(65447)
        self.assertFalse(ok)
        self.assertEqual(info["error"], "HTTP 500")

    def test_non_json_200_treated_as_success_for_old_versions(self):
        with mock.patch("urllib.request.urlopen", fake_urlopen(b"OK")):
            ok, info = shell._post_activate(65447)
        self.assertTrue(ok)
        self.assertEqual(info.get("warning"), "non-json-response")

    def test_connection_error(self):
        def _boom(*args, **kwargs):
            raise ConnectionRefusedError("connection refused")

        with mock.patch("urllib.request.urlopen", _boom):
            ok, info = shell._post_activate(65447)
        self.assertFalse(ok)
        self.assertIn("ConnectionRefusedError", info["error"])


class TestActivateExisting(unittest.TestCase):
    def test_success_first_attempt(self):
        calls = []

        def post(port, timeout):
            calls.append((port, timeout))
            return True, {"error": None}

        ok, info = shell._activate_existing(port=65447, attempts=3, sleep=lambda s: None,
                                            post=post)
        self.assertTrue(ok)
        self.assertEqual(info["attempts"], 1)
        self.assertEqual(info["port"], 65447)
        self.assertEqual(len(calls), 1)

    def test_reads_port_again_on_retry(self):
        """已有实例刚启动、端口还没写进文件 → 重试时要重新读 instance.json。"""
        ports = [None, 65447]
        sleeps = []

        def provider():
            return ports.pop(0) if ports else None

        def post(port, timeout):
            return True, {"error": None}

        ok, info = shell._activate_existing(attempts=3, sleep=sleeps.append,
                                            post=post, port_provider=provider)
        self.assertTrue(ok)
        self.assertEqual(info["attempts"], 2)
        self.assertTrue(sleeps)

    def test_all_attempts_rejected(self):
        sleeps = []
        ok, info = shell._activate_existing(
            port=65447, attempts=3, sleep=sleeps.append,
            post=lambda p, t: (False, {"error": "activate-rejected"}))
        self.assertFalse(ok)
        self.assertEqual(info["attempts"], 3)
        self.assertEqual(info["reason"], "activate-rejected")
        self.assertEqual(len(sleeps), 2)

    def test_no_instance_port(self):
        ok, info = shell._activate_existing(attempts=2, sleep=lambda s: None,
                                            post=lambda p, t: (True, {}),
                                            port_provider=lambda: None)
        self.assertFalse(ok)
        self.assertEqual(info["reason"], "no-instance-port")


class TestProbeServerIdentity(unittest.TestCase):
    def test_match(self):
        payload = json.dumps({"version": "0.1.8.6", "mock": False,
                              "platform": os.name}).encode()
        with mock.patch("urllib.request.urlopen", fake_urlopen(payload)):
            out = shell._probe_server_identity(65447)
        self.assertTrue(out["match"])
        self.assertEqual(out["version"], "0.1.8.6")

    def test_mock_server_not_reused(self):
        payload = json.dumps({"version": "x", "mock": True}).encode()
        with mock.patch("urllib.request.urlopen", fake_urlopen(payload)):
            out = shell._probe_server_identity(65447)
        self.assertFalse(out["match"])
        self.assertEqual(out["error"], "mock-server")

    def test_foreign_platform_not_reused(self):
        payload = json.dumps({"version": "x", "mock": False,
                              "platform": "posix"}).encode()
        with mock.patch("urllib.request.urlopen", fake_urlopen(payload)):
            out = shell._probe_server_identity(65447)
        self.assertFalse(out["match"])

    def test_no_version_field(self):
        with mock.patch("urllib.request.urlopen", fake_urlopen(b'{"ok": true}')):
            out = shell._probe_server_identity(65447)
        self.assertFalse(out["match"])
        self.assertEqual(out["error"], "no-version-field")

    def test_connection_error(self):
        def _boom(*args, **kwargs):
            raise OSError("refused")

        with mock.patch("urllib.request.urlopen", _boom):
            out = shell._probe_server_identity(65447)
        self.assertFalse(out["match"])
        self.assertIn("refused", out["error"])


class TestHandleExistingInstance(unittest.TestCase):
    def test_activated_returns_zero_deterministically(self):
        prompts = []
        marks = []
        with mock.patch.object(shell.bootlog, "mark",
                               lambda stage, **kw: marks.append(stage)):
            code = shell._handle_existing_instance(
                activate=lambda: (True, {"port": 65447, "attempts": 2}),
                prompt=prompts.append)
        self.assertEqual(code, 0)
        self.assertEqual(prompts, [])
        self.assertIn("single-instance-activated", marks)

    def test_failure_prompts_and_returns_nonzero(self):
        prompts = []
        marks = []
        info = {"port": 65447, "attempts": 3, "reason": "timeout"}
        with mock.patch.object(shell.bootlog, "mark",
                               lambda stage, **kw: marks.append(stage)):
            code = shell._handle_existing_instance(activate=lambda: (False, info),
                                                   prompt=prompts.append)
        self.assertEqual(code, 2)
        self.assertEqual(prompts, [info])
        self.assertIn("single-instance-activate-failed", marks)

    def test_activate_exception_still_prompts(self):
        prompts = []

        def boom():
            raise RuntimeError("激活炸了")

        code = shell._handle_existing_instance(activate=boom, prompt=prompts.append)
        self.assertEqual(code, 2)
        self.assertEqual(len(prompts), 1)
        self.assertIn("激活炸了", prompts[0].get("reason"))

    def test_prompt_exception_does_not_crash(self):
        def prompt(info):
            raise RuntimeError("弹窗失败")

        code = shell._handle_existing_instance(
            activate=lambda: (False, {"reason": "x"}), prompt=prompt)
        self.assertEqual(code, 2)


class TestPromptExistingInstance(unittest.TestCase):
    def test_message_contains_where_to_find_window(self):
        boxes = []
        with mock.patch.object(shell, "_message_box",
                               lambda text, caption=None: boxes.append(text)):
            shell._prompt_existing_instance({"reason": "timeout"})
        self.assertEqual(len(boxes), 1)
        self.assertIn("任务栏", boxes[0])
        self.assertIn("显示隐藏的图标", boxes[0])
        self.assertIn("MK87Config", boxes[0])
        self.assertIn("timeout", boxes[0])

    def test_message_box_failure_is_swallowed(self):
        with mock.patch.object(shell, "_message_box",
                               mock.MagicMock(side_effect=OSError("no desktop"))):
            shell._prompt_existing_instance({"reason": "x"})  # 不抛

    def test_message_box_win32_uses_user32(self):
        fake_ctypes = mock.MagicMock()
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(shell, "ctypes", fake_ctypes):
            _REAL_MESSAGE_BOX("内容", "标题")
        fake_ctypes.windll.user32.MessageBoxW.assert_called_once()
        args = fake_ctypes.windll.user32.MessageBoxW.call_args[0]
        self.assertEqual(args[1], "内容")
        self.assertEqual(args[2], "标题")

    def test_message_box_non_windows_only_logs(self):
        with mock.patch.object(shell.sys, "platform", "linux"), \
                mock.patch.object(shell, "log") as fake_log:
            _REAL_MESSAGE_BOX("内容")
        fake_log.warning.assert_called_once()

    def test_message_box_error_swallowed(self):
        fake_ctypes = mock.MagicMock()
        fake_ctypes.windll.user32.MessageBoxW.side_effect = OSError("no desktop")
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(shell, "ctypes", fake_ctypes):
            _REAL_MESSAGE_BOX("内容")  # 不抛


class TestReuseRunningInstance(unittest.TestCase):
    def test_no_port_returns_none(self):
        instance = FakeInstance(port=None)
        activate = mock.MagicMock()
        self.assertIsNone(shell._reuse_running_instance_if_any(
            instance, probe=lambda p: {"match": True}, activate=activate))
        activate.assert_not_called()

    def test_stale_port_returns_none(self):
        instance = FakeInstance(port=65447)
        activate = mock.MagicMock()
        marks = []
        with mock.patch.object(shell.bootlog, "mark",
                               lambda stage, **kw: marks.append(stage)):
            self.assertIsNone(shell._reuse_running_instance_if_any(
                instance, probe=lambda p: {"match": False, "error": "refused"},
                activate=activate))
        activate.assert_not_called()
        self.assertIn("single-instance-stale-port", marks)

    def test_live_legacy_instance_reused(self):
        instance = FakeInstance(port=65447)
        seen = []

        def activate(**kwargs):
            seen.append(kwargs)
            return True, {"port": 65447, "attempts": 1}

        marks = []
        with mock.patch.object(shell.bootlog, "mark",
                               lambda stage, **kw: marks.append(stage)):
            code = shell._reuse_running_instance_if_any(
                instance, probe=lambda p: {"match": True, "version": "0.1.8.4"},
                activate=activate)
        self.assertEqual(code, 0)
        self.assertEqual(seen, [{"port": 65447}])
        self.assertIn("single-instance-legacy-alive", marks)
        self.assertIn("single-instance-activated-legacy", marks)

    def test_live_legacy_instance_activate_fails_prompts_and_exits(self):
        instance = FakeInstance(port=65447)
        prompts = []
        code = shell._reuse_running_instance_if_any(
            instance, probe=lambda p: {"match": True, "version": "0.1.8.4"},
            activate=lambda **kw: (False, {"reason": "boom"}),
            prompt=prompts.append)
        self.assertEqual(code, 2)
        self.assertEqual(len(prompts), 1)


# ----------------------------------------------------------------------
# shell 托盘降级
# ----------------------------------------------------------------------
class TestTrayAvailable(unittest.TestCase):
    def test_no_tray_is_false(self):
        sh = make_shell(no_tray=True)
        self.assertFalse(sh._tray_available())

    def test_tray_missing_object_attempted_is_false(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh._tray_attempted = True
        sh.tray = None
        self.assertFalse(sh._tray_available())

    def test_tray_missing_object_not_attempted_is_none(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh.tray = None
        self.assertIsNone(sh._tray_available())

    def test_tray_unknown_state_is_optimistic(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh.tray = mock.MagicMock()
        self.assertIsNone(sh._tray_icon_state)
        self.assertTrue(sh._tray_available())

    def test_tray_unconfirmed_after_verify_is_unavailable(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh._tray_attempted = True
        sh.tray = mock.MagicMock()
        sh._tray_verify_failed = True
        self.assertFalse(sh._tray_available())
        self.assertFalse(sh.tray_state()["available"])
        self.assertIn("未能确认", sh._tray_error())

    def test_registered_states_are_available(self):
        for state in ("visible", "hidden"):
            sh = make_shell()
            sh._tray_backend = "pystray"
            sh.tray = mock.MagicMock()
            sh._tray_icon_state = state
            self.assertTrue(sh._tray_available(), state)

    def test_missing_states_are_unavailable(self):
        for state in ("missing", "rebuilding"):
            sh = make_shell()
            sh._tray_backend = "pystray"
            sh.tray = mock.MagicMock()
            sh._tray_icon_state = state
            self.assertFalse(sh._tray_available(), state)


class TestOnClosingDegrade(unittest.TestCase):
    def _win_shell(self, state="missing", attempted=True, tray=...):
        sh = make_shell()
        sh.window = mock.MagicMock()
        sh._tray_backend = "pystray"
        sh._tray_attempted = attempted
        sh._tray_icon_state = state
        sh.tray = mock.MagicMock() if tray is ... else tray
        sh.quit = mock.MagicMock()
        return sh

    def test_windows_missing_icon_minimizes_instead_of_hiding(self):
        sh = self._win_shell()
        boxes = []
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(shell, "_message_box",
                                  lambda text, caption=None: boxes.append(text)):
            result = sh._on_closing()
        self.assertFalse(result, "返回 False = 取消关闭，窗口继续存在")
        sh.window.minimize.assert_called_once()
        sh.window.hide.assert_not_called()
        sh.quit.assert_not_called()
        self.assertEqual(len(boxes), 1)
        self.assertIn("最小化", boxes[0])

    def test_windows_warning_only_once_per_run(self):
        sh = self._win_shell()
        boxes = []
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(shell, "_message_box",
                                  lambda text, caption=None: boxes.append(text)):
            sh._on_closing()
            sh._on_closing()
        self.assertEqual(len(boxes), 1)
        self.assertEqual(sh.window.minimize.call_count, 2)

    def test_windows_visible_icon_hides_window(self):
        sh = self._win_shell(state="visible")
        sh._notify_tray_running = mock.MagicMock()
        with mock.patch.object(shell.sys, "platform", "win32"):
            result = sh._on_closing()
        self.assertFalse(result)
        sh.window.hide.assert_called_once()
        sh.window.minimize.assert_not_called()
        sh._notify_tray_running.assert_called_once()

    def test_windows_never_attempted_keeps_legacy_quit_behavior(self):
        # 合成/异常配置（从未尝试托盘）：保持旧行为，避免窗口凭空消失找不回。
        sh = self._win_shell(state=None, attempted=False, tray=None)
        with mock.patch.object(shell.sys, "platform", "win32"):
            result = sh._on_closing()
        self.assertTrue(result)
        sh.quit.assert_called_once()
        sh.window.hide.assert_not_called()

    def test_linux_unavailable_still_quits(self):
        sh = self._win_shell()
        sh._tray_backend = "pystray"
        with mock.patch.object(shell.sys, "platform", "linux"), \
                mock.patch("mk87lib.tray_linux.STATE",
                           {"available": False, "backend": "qt", "error": "no host"}):
            result = sh._on_closing()
        self.assertTrue(result)
        sh.quit.assert_called_once()
        sh.window.minimize.assert_not_called()

    def test_no_tray_mode_quits(self):
        sh = self._win_shell()
        sh.no_tray = True
        with mock.patch.object(shell.sys, "platform", "win32"):
            result = sh._on_closing()
        self.assertTrue(result)
        sh.quit.assert_called_once()

    def test_should_degrade_close_matrix(self):
        sh = make_shell()
        with mock.patch.object(shell.sys, "platform", "win32"):
            self.assertFalse(sh._should_degrade_close())  # 没尝试过托盘
            sh._tray_attempted = True
            self.assertTrue(sh._should_degrade_close())
            sh.no_tray = True
            self.assertFalse(sh._should_degrade_close())
        with mock.patch.object(shell.sys, "platform", "linux"):
            sh.no_tray = False
            self.assertFalse(sh._should_degrade_close())


class TestTrayFirstHideNotification(unittest.TestCase):
    def test_windows_includes_overflow_hint_when_auto_hide(self):
        sh = make_shell()
        sh.tray = mock.MagicMock()
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(tray_win, "auto_hide_enabled", lambda *a, **k: True):
            sh._notify_tray_running()
        message = sh.tray.notify.call_args[0][0]
        self.assertIn("显示隐藏的图标", message)
        self.assertIn("仍在系统托盘运行", message)
        # 只发一次
        sh._notify_tray_running()
        sh.tray.notify.assert_called_once()

    def test_windows_no_hint_when_show_all_icons(self):
        sh = make_shell()
        sh.tray = mock.MagicMock()
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(tray_win, "auto_hide_enabled", lambda *a, **k: False):
            sh._notify_tray_running()
        message = sh.tray.notify.call_args[0][0]
        self.assertNotIn("显示隐藏的图标", message)

    def test_linux_qt_backend(self):
        sh = make_shell()
        sh._tray_backend = "qt"
        with mock.patch.object(shell.sys, "platform", "linux"), \
                mock.patch("mk87lib.tray_linux.notify") as notify:
            sh._notify_tray_running()
        notify.assert_called_once()


class TestTrayState(unittest.TestCase):
    def _shell_with_state(self, state):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh._tray_attempted = True
        sh.tray = mock.MagicMock()
        sh._tray_icon_state = state
        return sh

    def test_visible_state(self):
        state = self._shell_with_state("visible").tray_state()
        self.assertTrue(state["available"])
        self.assertTrue(state["iconRegistered"])
        self.assertFalse(state["overflow"])
        self.assertTrue(state["shell"])

    def test_hidden_icon_still_available_but_flags_overflow(self):
        state = self._shell_with_state("hidden").tray_state()
        self.assertTrue(state["available"])
        self.assertTrue(state["iconRegistered"])
        self.assertTrue(state["overflow"])

    def test_missing_state_unavailable(self):
        state = self._shell_with_state("missing").tray_state()
        self.assertFalse(state["available"])
        self.assertFalse(state["iconRegistered"])
        self.assertTrue(state["error"])

    def test_unknown_state_is_none(self):
        state = self._shell_with_state(None).tray_state()
        self.assertIsNone(state["available"])

    def test_tray_object_missing_after_attempt(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh._tray_attempted = True
        sh.tray = None
        state = sh.tray_state()
        self.assertFalse(state["available"])
        self.assertIn("error", state)

    def test_tray_error_prefers_error_text(self):
        sh = self._shell_with_state("missing")
        sh._tray_error_text = "重建失败: xyz"
        self.assertEqual(sh._tray_error(), "重建失败: xyz")
        sh._tray_error_text = ""
        # 注意措辞：单次查不到 ≠ 没注册，只说「暂时不可用/正在恢复」
        self.assertIn("暂时不可用", sh._tray_error())


class TestTrayProbeIcon(unittest.TestCase):
    def test_uses_zero_and_id_candidates(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        fake_tray = SimpleNamespace(_hwnd=4321)
        sh.tray = fake_tray
        with mock.patch.object(tray_win, "probe_icon",
                               lambda hwnd, u_ids: {"state": "visible",
                                                    "hwnd": hwnd, "u_ids": list(u_ids)}):
            out = sh._tray_probe_icon()
        self.assertEqual(out["state"], "visible")
        self.assertEqual(out["hwnd"], 4321)
        # pystray 实际用 uID=0；同时带上 id(tray) 兼容未来 pystray 修复
        self.assertEqual(out["u_ids"][0], 0)
        self.assertEqual(out["u_ids"][1], id(fake_tray))

    def test_unknown_when_no_icon_window(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh.tray = SimpleNamespace()
        with mock.patch.object(tray_win, "find_icon_hwnds", lambda **kw: []):
            out = sh._tray_probe_icon()
        self.assertEqual(out["state"], "unknown")

    def test_falls_back_to_enumerated_window(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh.tray = SimpleNamespace()
        seen = []

        def fake_probe(hwnd, u_ids):
            seen.append(hwnd)
            return {"state": "hidden", "hwnd": hwnd}

        with mock.patch.object(tray_win, "find_icon_hwnds",
                               lambda **kw: [{"hwnd": 9876}]), \
                mock.patch.object(tray_win, "probe_icon", fake_probe):
            out = sh._tray_probe_icon()
        self.assertEqual(out["state"], "hidden")
        self.assertEqual(seen, [9876])

    def test_no_tray_object(self):
        sh = make_shell()
        sh.tray = None
        self.assertEqual(sh._tray_probe_icon()["state"], "unknown")
        sh._tray_attempted = True
        self.assertEqual(sh._tray_probe_icon()["state"], "missing")


class TestTrayLifecycleHelpers(unittest.TestCase):
    def test_stop_tray_icon_basic(self):
        sh = make_shell()
        icon = FakeIcon()
        thread = FakeThread([True, False])  # join 时 alive，join 之后已退出
        sh._stop_tray_icon(icon, thread, timeout=0.5)
        self.assertEqual(icon.stops, 1)
        self.assertEqual(thread.joined, [0.5])

    def test_stop_tray_icon_late_stop_after_running(self):
        sh = make_shell()
        icon = FakeIcon(running=True)
        thread = FakeThread([True, True])  # join 之后仍 alive → 触发延迟 stop
        sh._stop_tray_icon(icon, thread, timeout=0.01)
        deadline = time.time() + 2.0
        while icon.stops < 2 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(icon.stops, 2)

    def test_stop_tray_icon_none_is_noop(self):
        make_shell()._stop_tray_icon(None)

    def test_start_pystray_failure_degrades(self):
        sh = make_shell()
        with mock.patch.object(shell.Shell, "_build_tray",
                               mock.MagicMock(side_effect=ImportError("no pystray"))):
            ok = sh._start_pystray()
        self.assertFalse(ok)
        self.assertTrue(sh._tray_attempted)
        self.assertEqual(sh._tray_icon_state, "missing")
        self.assertIn("no pystray", sh._tray_error_text)

    def test_rebuild_tray_failure_degrades(self):
        sh = make_shell()
        sh.tray = mock.MagicMock()
        with mock.patch.object(shell.Shell, "_build_tray",
                               mock.MagicMock(side_effect=ImportError("boom"))):
            ok = sh._rebuild_tray("unit-test")
        self.assertFalse(ok)
        self.assertEqual(sh._tray_icon_state, "missing")
        self.assertIn("重建托盘失败", sh._tray_error_text)
        sh.tray = mock.MagicMock()  # 旧图标已 stop
        self.assertFalse(sh._quitting)

    def test_rebuild_tray_success_starts_new_icon(self):
        sh = make_shell()

        def fake_build(self):  # noqa: N805 - patch 到 Shell 上，需接收 self
            self.tray = FakeIcon(running=False)
            self._tray_backend = "pystray"

        with mock.patch.object(shell.Shell, "_build_tray", fake_build):
            ok = sh._rebuild_tray("unit-test")
        self.assertTrue(ok)
        self.assertIsNotNone(sh._tray_thread)
        sh._tray_thread.join(1.0)

    def test_tray_diagnostics_merges_watchdog_info(self):
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh._tray_icon_state = "visible"
        sh._tray_watch = {"action": "ok"}
        with mock.patch.object(tray_win, "probe",
                               lambda **kw: {"supported": True, "icon": {}}):
            out = sh.tray_diagnostics()
        self.assertTrue(out["supported"])
        self.assertEqual(out["backend"], "pystray")
        self.assertEqual(out["iconState"], "visible")
        self.assertEqual(out["watchdog"], {"action": "ok"})

    def test_tray_diagnostics_never_raises(self):
        sh = make_shell()
        with mock.patch.object(tray_win, "probe", mock.MagicMock(side_effect=OSError("x"))):
            out = sh.tray_diagnostics()
        self.assertFalse(out["supported"] and False)
        self.assertIn("OSError", out["error"])


class TestStartupTrayVerification(unittest.TestCase):
    """启动时同步确认图标注册（避免「还没确认就关窗→隐身」）。"""

    def test_verify_visible_ok(self):
        sh = make_shell()
        with mock.patch.object(shell.Shell, "_tray_probe_icon",
                               lambda self: {"state": "visible", "hwnd": 1,
                                             "uID": 0}):
            state = sh._verify_tray_icon(wait=0.5)
        self.assertEqual(state, "visible")
        self.assertEqual(sh._tray_icon_state, "visible")

    def test_verify_hidden_ok(self):
        sh = make_shell()
        with mock.patch.object(shell.Shell, "_tray_probe_icon",
                               lambda self: {"state": "hidden", "hwnd": 1}):
            self.assertEqual(sh._verify_tray_icon(wait=0.5), "hidden")
        self.assertEqual(sh._tray_icon_state, "hidden")

    def test_verify_missing_is_unconfirmed_not_dead(self):
        """单次 GetRect 失败不能断言「未注册」：只标未确认，关窗保守最小化。"""
        sh = make_shell()
        sh._tray_backend = "pystray"
        sh.tray = SimpleNamespace(_hwnd=123)
        with mock.patch.object(shell.Shell, "_tray_probe_icon",
                               lambda self: {"state": "missing"}):
            state = sh._verify_tray_icon(wait=0.05)
        self.assertIsNone(state)
        self.assertIsNone(sh._tray_icon_state, "未确认时不应写 missing 状态")
        self.assertTrue(sh._tray_verify_failed)
        self.assertFalse(sh._tray_available())
        self.assertIn("未能确认", sh._tray_error())

    def test_verify_no_icon_window_is_unconfirmed(self):
        sh = make_shell()
        sh.tray = SimpleNamespace()
        with mock.patch.object(shell.Shell, "_tray_probe_icon",
                               lambda self: {"state": "unknown"}):
            self.assertIsNone(sh._verify_tray_icon(wait=0.05))
        self.assertIsNone(sh._tray_icon_state)
        self.assertTrue(sh._tray_verify_failed)

    def test_tray_readd_icon_toggles_visible(self):
        sh = make_shell()

        class FakeTray:
            def __init__(self):
                self.visible = True

        sh.tray = FakeTray()
        self.assertTrue(sh._tray_readd_icon())
        self.assertTrue(sh.tray.visible)

    def test_tray_readd_icon_failure_is_safe(self):
        sh = make_shell()

        class ReaddFails:
            def __init__(self):
                self._visible = True

            @property
            def visible(self):
                return self._visible

            @visible.setter
            def visible(self, value):
                if value is True:
                    raise RuntimeError("pystray 未就绪")
                self._visible = value

        sh.tray = ReaddFails()
        self.assertFalse(sh._tray_readd_icon())
        self.assertFalse(sh._quitting)


class TestSilentWindowGuard(unittest.TestCase):
    """--tray 静默启动 + 托盘不可用 → 必须把窗口显示出来（不能彻底隐身）。"""

    def test_non_silent_is_noop(self):
        sh = make_shell()
        sh.silent = False
        sh.show_window = mock.MagicMock()
        sh._silent_window_guard(wait=0)
        sh.show_window.assert_not_called()
        sh._start_silent_window_guard()  # 非静默启动不会起兜底线程
        sh.show_window.assert_not_called()

    def test_silent_unavailable_shows_window_and_warns_once(self):
        sh = make_shell()
        sh.silent = True
        sh._tray_backend = "pystray"
        sh._tray_attempted = True
        sh.tray = None  # → _tray_available() False
        sh.show_window = mock.MagicMock()
        boxes = []
        marks = []
        with mock.patch.object(shell, "_message_box",
                               lambda text, caption=None: boxes.append(text)), \
                mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(shell.bootlog, "mark",
                                  lambda stage, **kw: marks.append(stage)):
            sh._silent_window_guard(wait=0)
            sh._silent_window_guard(wait=0)
        sh.show_window.assert_called()  # 每次检查都确保窗口可见
        self.assertEqual(len(boxes), 1)  # 提示只弹一次
        self.assertIn("静默启动", boxes[0])
        self.assertIn("silent-tray-unavailable-show-window", marks)

    def test_silent_available_does_not_show_window(self):
        sh = make_shell()
        sh.silent = True
        sh._tray_backend = "pystray"
        sh._tray_attempted = True
        sh.tray = mock.MagicMock()
        sh._tray_icon_state = "visible"
        sh.show_window = mock.MagicMock()
        sh._silent_window_guard(wait=0)
        sh.show_window.assert_not_called()

    def test_silent_guard_waits_for_watchdog_recovery(self):
        """看门狗在等待窗口内恢复图标 → 不弹窗、不显示窗口（避免误打扰）。"""
        sh = make_shell()
        sh.silent = True
        sh.show_window = mock.MagicMock()
        states = [False, False, True]

        def available(self):
            return states.pop(0) if states else True

        with mock.patch.object(shell.Shell, "_tray_available", available), \
                mock.patch.object(shell.bootlog, "mark", lambda *a, **k: None):
            sh._silent_window_guard(wait=2.0, interval=0.01)
        sh.show_window.assert_not_called()

    def test_start_guard_skips_non_windows(self):
        sh = make_shell()
        with mock.patch.object(shell.sys, "platform", "linux"), \
                mock.patch.object(shell.threading, "Thread") as thread_cls:
            sh._start_silent_window_guard()
        thread_cls.assert_not_called()

    def test_start_guard_skips_no_tray(self):
        sh = make_shell(no_tray=True)
        with mock.patch.object(shell.sys, "platform", "win32"), \
                mock.patch.object(shell.threading, "Thread") as thread_cls:
            sh._start_silent_window_guard()
        thread_cls.assert_not_called()


# ----------------------------------------------------------------------
# shell.TrayWatchdog 状态机
# ----------------------------------------------------------------------
class TestTrayWatchdog(unittest.TestCase):
    def _watchdog(self, env, icon_states, *, rebuild_ok=True, now=None, readd_ok=True,
                  **kwargs):
        self.rebuilds = []
        self.readds = []
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})
        env_value = env() if callable(env) else env
        self.env_calls = 0

        def probe_env():
            self.env_calls += 1
            value = env() if callable(env) else env
            return value

        states = list(icon_states)

        def probe_icon():
            if len(states) > 1:
                return states.pop(0)
            return states[0] if states else {"state": "unknown"}

        def rebuild(reason):
            self.rebuilds.append(reason)
            return rebuild_ok

        def readd():
            self.readds.append(True)
            return readd_ok

        return shell.TrayWatchdog(self.shell_obj, probe_env=probe_env,
                                  probe_icon=probe_icon, rebuild=rebuild,
                                  readd=readd,
                                  now=now or (lambda: 1000.0), **kwargs)

    def test_visible_icon_ok(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "visible"}])
        self.assertEqual(wd.tick(), "ok")
        self.assertEqual(self.shell_obj._tray_icon_state, "visible")
        self.assertFalse(self.rebuilds)

    def test_hidden_icon_counts_as_ok(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "hidden"}])
        self.assertEqual(wd.tick(), "ok")
        self.assertEqual(self.shell_obj._tray_icon_state, "hidden")
        self.assertFalse(self.rebuilds)

    def test_single_missing_tick_does_not_rebuild(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "missing"}], missing_threshold=2)
        self.assertEqual(wd.tick(), "missing?")
        self.assertFalse(self.rebuilds)

    def test_consecutive_missing_rebuilds(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "missing"}], missing_threshold=2,
                            max_readds=0)
        wd.tick()
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(self.rebuilds, ["icon-missing"])
        self.assertEqual(self.readds, [])

    def test_readd_before_rebuild(self):
        """查不到图标时先 NIM_ADD 重加一次，仍不行才重建（避免误判就重建出重复图标）。"""
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "missing"}], missing_threshold=2)
        self.assertEqual(wd.tick(), "missing?")
        self.assertEqual(wd.tick(), "re-add")
        self.assertEqual(self.readds, [True])
        self.assertFalse(self.rebuilds)
        self.assertEqual(wd.tick(), "missing?")
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(self.rebuilds, ["icon-missing"])

    def test_readd_failure_falls_back_to_rebuild(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "missing"}], missing_threshold=1,
                            readd_ok=False)
        self.assertEqual(wd.tick(), "re-add-failed")
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(self.rebuilds, ["icon-missing"])

    def test_no_taskbar_does_nothing(self):
        wd = self._watchdog({"present": False, "taskbarHwnd": 0, "shellHwnd": 0},
                            [{"state": "missing"}])
        self.assertEqual(wd.tick(), "no-taskbar")
        self.assertFalse(self.rebuilds)

    def test_unknown_probe_never_rebuilds(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "unknown"}], missing_threshold=1)
        for _ in range(5):
            self.assertEqual(wd.tick(), "unknown")
        self.assertFalse(self.rebuilds)

    def test_probe_exception_is_swallowed(self):
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})

        def boom():
            raise OSError("probe boom")

        wd = shell.TrayWatchdog(self.shell_obj, probe_env=boom,
                                probe_icon=boom, rebuild=lambda r: True)
        self.assertEqual(wd.tick(), "no-taskbar")  # env 探测失败 → 不动
        self.shell_obj._tray_icon_state = None

    def test_explorer_restart_token_resets_counters(self):
        envs = [
            {"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
            {"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
            {"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
            {"present": True, "taskbarHwnd": 9, "shellHwnd": 8},  # Explorer 重启
            {"present": True, "taskbarHwnd": 9, "shellHwnd": 8},
            {"present": True, "taskbarHwnd": 9, "shellHwnd": 8},
        ]
        nows = iter([1000.0, 1010.0, 1020.0, 1030.0, 1040.0, 1050.0])
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})
        self.rebuilds = []

        def probe_env():
            return envs.pop(0) if envs else {"present": True, "taskbarHwnd": 9,
                                             "shellHwnd": 8}

        def rebuild(reason):
            self.rebuilds.append(reason)
            return True

        wd = shell.TrayWatchdog(self.shell_obj, probe_env=probe_env,
                                probe_icon=lambda: {"state": "missing"},
                                rebuild=rebuild, readd=lambda: True,
                                now=lambda: next(nows),
                                missing_threshold=1, rebuild_interval=0.0,
                                max_readds=0)
        self.assertEqual(wd.tick(), "rebuilt")   # 第 1 拍：token 建立后缺失 → 重建
        self.assertEqual(len(self.rebuilds), 1)
        self.assertEqual(wd.tick(), "rebuilt")   # 第 2 拍：再次缺失 → 重建
        self.assertEqual(len(self.rebuilds), 2)
        self.assertEqual(wd.tick(), "rebuilt")   # 第 3 拍：token 未变 → 继续重建
        self.assertEqual(len(self.rebuilds), 3)
        self.assertEqual(wd.tick(), "rebuilt")   # 第 4 拍：Explorer 重启 token 变化 → 计数清零
        self.assertEqual(wd.snapshot()["rebuilds"], 1)
        self.assertEqual(len(self.rebuilds), 4)
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(len(self.rebuilds), 5)

    def test_throttle_between_rebuilds(self):
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})
        self.rebuilds = []
        wd = shell.TrayWatchdog(
            self.shell_obj,
            probe_env=lambda: {"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
            probe_icon=lambda: {"state": "missing"},
            rebuild=lambda reason: self.rebuilds.append(reason) or True,
            readd=lambda: True,
            now=lambda: 100.0, missing_threshold=1, rebuild_interval=10.0,
            max_readds=0)
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(wd.tick(), "throttled")
        self.assertEqual(len(self.rebuilds), 1)

    def test_max_rebuilds_gives_up_and_marks_missing(self):
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})
        clock = iter([100.0 + i * 20 for i in range(20)])
        wd = shell.TrayWatchdog(
            self.shell_obj,
            probe_env=lambda: {"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
            probe_icon=lambda: {"state": "missing"},
            rebuild=lambda reason: True,
            readd=lambda: True,
            now=lambda: next(clock),
            missing_threshold=1, rebuild_interval=0.0, max_rebuilds=2,
            max_readds=0)
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(wd.tick(), "rebuilt")
        self.assertEqual(wd.tick(), "give-up")
        self.assertEqual(self.shell_obj._tray_icon_state, "missing")
        self.assertTrue(self.shell_obj._tray_rebuild_exhausted)

    def test_quitting_stops_watchdog(self):
        self.shell_obj = SimpleNamespace(_quitting=True, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})
        rebuild = mock.MagicMock(return_value=True)
        wd = shell.TrayWatchdog(self.shell_obj, probe_env=lambda: {"present": True},
                                probe_icon=lambda: {"state": "missing"},
                                rebuild=rebuild)
        self.assertEqual(wd.tick(), "stopped")
        rebuild.assert_not_called()

    def test_no_tray_stops_watchdog(self):
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=True,
                                         _tray_icon_state=None, _tray_watch={})
        wd = shell.TrayWatchdog(self.shell_obj, probe_env=lambda: {"present": True},
                                probe_icon=lambda: {"state": "missing"},
                                rebuild=lambda r: True)
        self.assertEqual(wd.tick(), "stopped")

    def test_snapshot_keys(self):
        wd = self._watchdog({"present": True, "taskbarHwnd": 1, "shellHwnd": 2},
                            [{"state": "visible"}])
        wd.tick()
        snap = wd.snapshot()
        for key in ("action", "iconState", "missingTicks", "rebuilds", "token", "detail"):
            self.assertIn(key, snap)
        self.assertEqual(snap["token"], [1, 2])

    def test_loop_runs_and_stops(self):
        self.shell_obj = SimpleNamespace(_quitting=False, no_tray=False,
                                         _tray_icon_state=None, _tray_watch={})
        wd = shell.TrayWatchdog(self.shell_obj,
                                probe_env=lambda: {"present": False},
                                probe_icon=lambda: {"state": "unknown"},
                                rebuild=lambda r: True, interval=0.05)
        wd.start()
        time.sleep(0.12)
        wd.stop()
        wd._thread.join(2.0)
        self.assertFalse(wd._thread.is_alive())


# ----------------------------------------------------------------------
# shell.main 单实例分支（集成）
# ----------------------------------------------------------------------
class FakeShell:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.ran = False
        FakeShell.instances.append(self)

    def run(self):
        self.ran = True
        return 0


class TestMainSingleInstance(unittest.TestCase):
    def _main(self, argv, *, acquire=None, handle=None, reuse=None, shell_cls=None):
        FakeShell.instances.clear()
        patches = [
            mock.patch.object(shell.sys, "argv", list(argv)),
            mock.patch.object(shell, "setup_logging"),
            mock.patch.object(shell, "_apply_render_env",
                              lambda: {"requested": False}),
            mock.patch.object(shell.bootlog, "mark", lambda *a, **k: None),
        ]
        acquire = acquire or (lambda: shell.SingleInstance(directory=tempfile.mkdtemp()))
        patches.append(mock.patch.object(shell, "_acquire_single_instance", acquire))
        if handle is not None:
            patches.append(mock.patch.object(shell, "_handle_existing_instance", handle))
        if reuse is not None:
            patches.append(mock.patch.object(shell, "_reuse_running_instance_if_any", reuse))
        patches.append(mock.patch.object(shell, "Shell", shell_cls or FakeShell))
        for patch in patches:
            patch.start()
        try:
            return shell.main()
        finally:
            for patch in reversed(patches):
                patch.stop()

    def test_existing_instance_activated_exits_zero(self):
        handle = mock.MagicMock(return_value=0)
        code = self._main(["shell.py"], acquire=lambda: None, handle=handle)
        self.assertEqual(code, 0)
        handle.assert_called_once()
        self.assertEqual(FakeShell.instances, [], "唤起成功不能再启动外壳")

    def test_existing_instance_activation_failed_exits_nonzero(self):
        handle = mock.MagicMock(return_value=2)
        code = self._main(["shell.py", "--tray"], acquire=lambda: None, handle=handle)
        self.assertEqual(code, 2)
        self.assertEqual(FakeShell.instances, [])

    def test_acquired_then_legacy_reused_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = shell.SingleInstance(directory=tmp)
            reuse = mock.MagicMock(return_value=0)
            code = self._main(["shell.py"], acquire=lambda: instance, reuse=reuse)
        self.assertEqual(code, 0)
        reuse.assert_called_once_with(instance)
        self.assertEqual(FakeShell.instances, [])

    def test_acquired_and_no_legacy_starts_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = shell.SingleInstance(directory=tmp)
            code = self._main(["shell.py", "--tray"], acquire=lambda: instance,
                              reuse=lambda inst: None)
        self.assertEqual(code, 0)
        self.assertEqual(len(FakeShell.instances), 1)
        self.assertTrue(FakeShell.instances[0].ran)
        self.assertTrue(FakeShell.instances[0].kwargs.get("silent"))

    def test_no_single_instance_flag_skips_lock(self):
        acquire = mock.MagicMock(side_effect=AssertionError("不应获取单实例锁"))
        code = self._main(["shell.py", "--no-single-instance"], acquire=acquire)
        self.assertEqual(code, 0)
        acquire.assert_not_called()
        self.assertEqual(len(FakeShell.instances), 1)


if __name__ == "__main__":
    unittest.main()
