"""mk87lib.keyscan 的 VK 名称/HID 映射与 raw input 生命周期单测。

背景（2026-11-07 用户实机崩溃，%LOCALAPPDATA%\\mk87\\logs\\crash.log）::

    Windows fatal exception: access violation
      File "mk87lib\\keyscan.py", line 205 in _windows_loop   ← RegisterClassW
      File "mk87lib\\keyscan.py", line 206 in _windows_loop   ← CreateWindowExW

根因：`WNDPROC(_wndproc)` 只被 `ctypes.cast(..., c_void_p)` 取走裸地址后就没有
Python 强引用，立刻被 GC；窗口消息（CreateWindowExW 内的 WM_NCCREATE、运行期
WM_INPUT）回调到已释放的函数指针 → access violation。同文件还缺 0x12 等通用
修饰键的 VK 名称/HID 映射（keytest 显示 `VK_0x12` / `slot —`）。

这些测试只用假 user32/kernel32 注入 `_windows_loop`：**不注册真实 raw input、
不读取真实键盘**，非 Windows 平台跳过 Win32 部分。
"""
import ctypes
import sys
import unittest

from mk87lib import keyscan


# ---------------------------------------------------------------------------
# 纯函数：VK 名称 / HID usage 映射
# ---------------------------------------------------------------------------
class TestVkNames(unittest.TestCase):
    def test_generic_modifier_vks_have_names(self):
        # 用户截图：按修饰键只报通用 VK 0x12 → `VK_0x12`、hid None、前端「未知」
        self.assertEqual(keyscan.vkey_name(0x10), "L-Shift")
        self.assertEqual(keyscan.vkey_name(0x11), "L-Ctrl")
        self.assertEqual(keyscan.vkey_name(0x12), "L-Alt")

    def test_win_and_specific_modifier_names(self):
        expected = {
            0x5B: "L-Win", 0x5C: "R-Win",
            0xA0: "L-Shift", 0xA1: "R-Shift",
            0xA2: "L-Ctrl", 0xA3: "R-Ctrl",
            0xA4: "L-Alt", 0xA5: "R-Alt",
            0x0D: "Enter",
        }
        for vkey, name in expected.items():
            with self.subTest(vkey=hex(vkey)):
                self.assertEqual(keyscan.vkey_name(vkey), name)

    def test_unknown_vkey_still_reports_hex(self):
        self.assertEqual(keyscan.vkey_name(0xFE), "VK_0xFE")
        self.assertEqual(keyscan.vkey_name(0x00), "VK_0x00")

    def test_vkey_to_hid_modifier_usage_ids(self):
        # HID usage 表（Keyboard page）：224 L-Ctrl, 225 L-Shift, 226 L-Alt,
        # 227 L-Win, 228 R-Ctrl, 229 R-Shift, 230 R-Alt, 231 R-Win
        expected = {
            0x10: 0xE1, 0x11: 0xE0, 0x12: 0xE2,   # 通用修饰键 VK 默认按左手
            0xA0: 0xE1, 0xA1: 0xE5,
            0xA2: 0xE0, 0xA3: 0xE4,
            0xA4: 0xE2, 0xA5: 0xE6,
            0x5B: 0xE3, 0x5C: 0xE7,
            0x0D: 0x28,
        }
        for vkey, hid in expected.items():
            with self.subTest(vkey=hex(vkey)):
                self.assertEqual(keyscan.vkey_to_hid(vkey), hid)

    def test_unknown_vkey_has_no_hid(self):
        self.assertIsNone(keyscan.vkey_to_hid(0xFE))
        self.assertIsNone(keyscan.vkey_to_hid(0x00))


class TestResolveGenericModifier(unittest.TestCase):
    """通用 VK 只能靠扫描码/E0 标志还原左右手。"""

    def test_generic_alt_left_right(self):
        self.assertEqual(keyscan._resolve_generic_modifier(0x12, 0x38, 0),
                         ("L-Alt", 0xE2))
        self.assertEqual(keyscan._resolve_generic_modifier(0x12, 0x38, keyscan._RI_KEY_E0),
                         ("R-Alt", 0xE6))

    def test_generic_ctrl_left_right(self):
        self.assertEqual(keyscan._resolve_generic_modifier(0x11, 0x1D, 0),
                         ("L-Ctrl", 0xE0))
        self.assertEqual(keyscan._resolve_generic_modifier(0x11, 0x1D, keyscan._RI_KEY_E0),
                         ("R-Ctrl", 0xE4))

    def test_generic_shift_uses_scan_code(self):
        self.assertEqual(keyscan._resolve_generic_modifier(0x10, 0x2A, 0),
                         ("L-Shift", 0xE1))
        self.assertEqual(keyscan._resolve_generic_modifier(0x10, 0x36, 0),
                         ("R-Shift", 0xE5))

    def test_non_generic_modifier_is_not_rewritten(self):
        # 左右手专用 VK 由 _VK_NAMES 直接处理，不应被通用逻辑覆盖
        self.assertIsNone(keyscan._resolve_generic_modifier(0xA5, 0x38, keyscan._RI_KEY_E0))
        self.assertIsNone(keyscan._resolve_generic_modifier(0x41, 0x1E, 0))


# ---------------------------------------------------------------------------
# 假 Win32：只记录调用，不做任何系统注册
# ---------------------------------------------------------------------------
class _FakeUser32:
    """最小假 user32。PeekMessageW 先投递一条 WM_INPUT，随后让 scanner 停止。"""

    def __init__(self, scanner, raw_input=b"", device_name="", hwnd=0x1234):
        self.scanner = scanner
        self.raw_input = raw_input
        self.device_name = device_name
        self.hwnd = hwnd
        self._peek_calls = 0
        # 记录点
        self.registered_wc = None
        self.registered_class_name = None
        self.wndproc_at_create = None
        self.wndproc_at_register = None
        self.create_args = None
        self.destroyed_hwnd = None
        self.unregistered = None
        self.raw_devices = None
        self.raw_input_sizes = []
        self.defwndproc_calls = []
        self.dispatch_count = 0

    # ---- 窗口类 / 窗口 ----
    def DefWindowProcW(self, hwnd, msg, wparam, lparam):
        self.defwndproc_calls.append((hwnd, msg, wparam, lparam))
        return 0

    def RegisterClassW(self, wc_ref):
        self.registered_wc = wc_ref._obj
        self.registered_class_name = self.registered_wc.lpszClassName
        # 模拟真实场景：注册后类里存的是裸函数指针，回调对象必须仍被强引用
        self.wndproc_at_register = self.scanner._wndproc
        return 0xC001

    def UnregisterClassW(self, class_name, hinstance):
        self.unregistered = (class_name, hinstance)
        return 1

    def CreateWindowExW(self, *args):
        self.create_args = args
        # CreateWindowExW 内部会同步回调 WndProc（WM_NCCREATE）——crash.log 的
        # access violation 正发生在这里，此时回调对象必须仍然存活。
        self.wndproc_at_create = self.scanner._wndproc
        return self.hwnd

    def DestroyWindow(self, hwnd):
        self.destroyed_hwnd = hwnd
        return 1

    def RegisterRawInputDevices(self, devices, count, size):
        self.raw_devices = [
            (devices[i].usUsagePage, devices[i].usUsage,
             devices[i].dwFlags, devices[i].hwndTarget)
            for i in range(count)
        ]
        return 1

    # ---- raw input ----
    @staticmethod
    def _uint_ref(ref):
        return ref._obj if hasattr(ref, "_obj") else ref

    def GetRawInputData(self, hdevice, command, pdata, psize, header_size):
        size = self._uint_ref(psize)
        if pdata is None:  # 第一次：查询所需字节数
            size.value = len(self.raw_input)
            self.raw_input_sizes.append(("query", size.value))
            return 0
        # 第二次：调用方必须把 pcbSize 设为「缓冲区字节数」
        self.raw_input_sizes.append(("data", size.value))
        assert size.value == len(self.raw_input), "pcbSize 应为缓冲区字节数"
        ctypes.memmove(pdata.value, self.raw_input, len(self.raw_input))
        return len(self.raw_input)

    def GetRawInputDeviceInfoW(self, hdevice, command, pdata, psize):
        size = self._uint_ref(psize)
        chars = len(self.device_name) + 1 if self.device_name else 0
        if pdata is None:
            size.value = chars
            return 0 if chars else keyscan._RAWINPUT_ERROR
        if not chars:
            return keyscan._RAWINPUT_ERROR
        raw = self.device_name.encode("utf-16-le")
        ctypes.memmove(pdata.value, raw, len(raw))
        return chars

    # ---- 消息泵 ----
    def PeekMessageW(self, msg_ref, hwnd, wmin, wmax, remove):
        msg = msg_ref._obj
        self._peek_calls += 1
        if self._peek_calls == 1:
            msg.hwnd = hwnd
            msg.message = keyscan._WM_INPUT
            msg.wParam = 0
            msg.lParam = 0x7777  # 假的 HRAWINPUT，假 GetRawInputData 不解析它
            return 1
        self.scanner._stop.set()  # 只处理一条消息，便于同步断言
        return 0

    def TranslateMessage(self, msg_ref):
        return 1

    def DispatchMessageW(self, msg_ref):
        # 真实 Windows 在这里回调窗口过程；照着模拟，验证 _wndproc → DefWindowProcW
        self.dispatch_count += 1
        wndproc = self.scanner._wndproc
        if wndproc is not None:
            msg = msg_ref._obj
            wndproc(msg.hwnd, msg.message, msg.wParam, msg.lParam)
        return 0


class _FakeKernel32:
    def GetModuleHandleW(self, name):
        return 0x140000000


@unittest.skipUnless(sys.platform == "win32", "raw input 接口仅 Windows 可用")
class TestWindowsRawInputLoop(unittest.TestCase):
    def setUp(self):
        # 只加载 user32/kernel32 并声明原型；不注册 raw input、不建真实窗口
        self.api = keyscan._Win32Api()

    # ---- helpers ----
    def _build_raw_input(self, vkey, scan, flags, message, dw_type=None):
        api = self.api
        header = api.RAWINPUTHEADER()
        header.dwType = keyscan._RIM_TYPEKEYBOARD if dw_type is None else dw_type
        header.dwSize = ctypes.sizeof(api.RAWINPUTHEADER) + ctypes.sizeof(api.RAWKEYBOARD)
        header.hDevice = 0x4321
        keyboard = api.RAWKEYBOARD()
        keyboard.MakeCode = scan
        keyboard.Flags = flags
        keyboard.VKey = vkey
        keyboard.Message = message
        return bytes(header) + bytes(keyboard)

    def _run_loop(self, *, vkey=0x12, scan=0x38, flags=0, message=keyscan._WM_KEYDOWN,
                  device_name="\\\\?\\HID#VID_0C45&PID_0001", dw_type=None,
                  only_ajazz=False):
        raw = self._build_raw_input(vkey, scan, flags, message, dw_type)
        scanner = keyscan.KeyScanner(only_ajazz=only_ajazz)
        events = []
        seen = {}

        def cb(ev):
            events.append(ev)
            # 消息处理期间回调对象必须被 scanner 强引用（否则又是悬空指针）
            seen["wndproc_alive"] = scanner._wndproc is not None

        scanner.callback = cb
        fake_user32 = _FakeUser32(scanner, raw, device_name)
        self.api.user32 = fake_user32
        self.api.kernel32 = _FakeKernel32()
        scanner._windows_loop(api=self.api)
        return scanner, fake_user32, events, seen

    # ---- 主路径 ----
    def test_wm_input_generic_alt_event_wire_format(self):
        scanner, user32, events, seen = self._run_loop(
            vkey=0x12, scan=0x38, flags=0, message=keyscan._WM_KEYDOWN)

        self.assertTrue(seen.get("wndproc_alive"), "WNDPROC 必须在处理消息期间存活")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["type"], "key")
        for field in ("type", "vkey", "name", "hid", "down", "scan", "flags", "device"):
            self.assertIn(field, ev)
        self.assertEqual(ev["vkey"], 0x12)
        self.assertEqual(ev["name"], "L-Alt")
        self.assertEqual(ev["hid"], 0xE2)
        self.assertTrue(ev["down"])
        self.assertEqual(ev["scan"], 0x38)
        self.assertEqual(ev["flags"], 0)
        self.assertIn("VID_0C45", ev["device"])
        self.assertIn("ts", ev)  # _emit 补时间戳

    def test_right_alt_generic_vk_is_resolved_by_e0(self):
        _, _, events, _ = self._run_loop(
            vkey=0x12, scan=0x38, flags=keyscan._RI_KEY_E0, message=0x0101)  # WM_KEYUP
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "R-Alt")
        self.assertEqual(events[0]["hid"], 0xE6)
        self.assertFalse(events[0]["down"])

    def test_win_key_event_uses_win_hid(self):
        _, _, events, _ = self._run_loop(vkey=0x5B, scan=0x5B, flags=0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "L-Win")
        self.assertEqual(events[0]["hid"], 0xE3)

    def test_unknown_vkey_keeps_hex_name(self):
        _, _, events, _ = self._run_loop(vkey=0xFE, scan=0x00, flags=0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "VK_0xFE")
        self.assertIsNone(events[0]["hid"])

    # ---- 资源生命周期（crash.log 回归点） ----
    def test_wndproc_lifetime_class_registration_and_cleanup(self):
        scanner, user32, events, _ = self._run_loop()
        # 注册期间/创建窗口期间回调对象存活（修复前根本没有这个强引用）
        self.assertIsNotNone(user32.wndproc_at_register)
        self.assertIsNotNone(user32.wndproc_at_create)
        # 窗口类名唯一、创建/注册/注销成对出现，句柄一致
        self.assertTrue(user32.registered_class_name.startswith("mk87_keyscan_"))
        self.assertEqual(user32.create_args[1], user32.registered_class_name)
        self.assertEqual(user32.destroyed_hwnd, user32.hwnd)
        self.assertEqual(user32.unregistered,
                         (user32.registered_class_name, 0x140000000))
        # 循环结束后强引用释放（窗口与类都已注销，晚一步就是悬空指针）
        self.assertIsNone(scanner._wndproc)
        # raw input 注册了两个 usage：keyboard(0x01/0x06) + consumer(0x0C/0x01)
        self.assertEqual([(d[0], d[1]) for d in user32.raw_devices],
                         [(0x01, 0x06), (0x0C, 0x01)])
        self.assertTrue(all(d[3] == user32.hwnd for d in user32.raw_devices))
        self.assertTrue(all(d[2] == keyscan._RIDEV_INPUTSINK for d in user32.raw_devices))
        # WM_INPUT 仍需 DispatchMessageW → DefWindowProc 做系统侧清理
        self.assertGreaterEqual(user32.dispatch_count, 1)
        self.assertTrue(user32.defwndproc_calls)
        # 回调本身仍可安全调用（由假 user32 持有的引用）
        self.assertEqual(user32.wndproc_at_create(0x1, keyscan._WM_INPUT, 0, 0), 0)

    def test_raw_input_second_call_passes_buffer_size(self):
        _, user32, events, _ = self._run_loop()
        self.assertEqual(len(events), 1)
        self.assertEqual(len(user32.raw_input_sizes), 2)
        query_kind, query_size = user32.raw_input_sizes[0]
        data_kind, data_size = user32.raw_input_sizes[1]
        self.assertEqual((query_kind, data_kind), ("query", "data"))
        # 第二次调用的 pcbSize 必须是缓冲区字节数（Win32 文档语义）
        self.assertEqual(data_size, query_size)
        self.assertGreater(query_size, 0)

    def test_class_names_are_unique_between_scanners(self):
        _, user32_a, _, _ = self._run_loop()
        _, user32_b, _, _ = self._run_loop()
        self.assertNotEqual(user32_a.registered_class_name,
                            user32_b.registered_class_name)

    def test_only_ajazz_filters_other_devices(self):
        _, _, events, _ = self._run_loop(device_name="\\\\?\\HID#VID_1234&PID_0001",
                                         only_ajazz=True)
        self.assertEqual(events, [])

    # ---- 失败路径：同样必须清理窗口类与回调引用 ----
    def test_create_window_failure_cleans_up_class(self):
        scanner = keyscan.KeyScanner()
        fake_user32 = _FakeUser32(scanner, b"", "")
        fake_user32.CreateWindowExW = lambda *a: 0
        self.api.user32 = fake_user32
        self.api.kernel32 = _FakeKernel32()
        with self.assertRaises(OSError):
            scanner._windows_loop(api=self.api)
        self.assertIsNone(scanner._wndproc)
        self.assertIsNotNone(fake_user32.unregistered)
        self.assertIsNone(fake_user32.destroyed_hwnd)

    def test_register_class_failure_raises_and_releases_callback(self):
        scanner = keyscan.KeyScanner()
        fake_user32 = _FakeUser32(scanner, b"", "")
        fake_user32.RegisterClassW = lambda wc_ref: 0
        self.api.user32 = fake_user32
        self.api.kernel32 = _FakeKernel32()
        with self.assertRaises(OSError):
            scanner._windows_loop(api=self.api)
        self.assertIsNone(scanner._wndproc)
        self.assertIsNone(fake_user32.unregistered)  # 类没注册成功，无需注销
        self.assertIsNone(fake_user32.create_args)

    def test_register_raw_input_failure_cleans_up(self):
        scanner = keyscan.KeyScanner()
        fake_user32 = _FakeUser32(scanner, b"", "")
        fake_user32.RegisterRawInputDevices = lambda *a: 0
        self.api.user32 = fake_user32
        self.api.kernel32 = _FakeKernel32()
        with self.assertRaises(OSError):
            scanner._windows_loop(api=self.api)
        self.assertIsNone(scanner._wndproc)
        self.assertEqual(fake_user32.destroyed_hwnd, fake_user32.hwnd)
        self.assertIsNotNone(fake_user32.unregistered)

    def test_non_keyboard_raw_input_is_ignored(self):
        _, _, events, _ = self._run_loop(dw_type=2)  # RIM_TYPEMOUSE
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
