#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电量刷新 / 灯效快照恢复 / 帧流入口 / isCustom 兜底 的离线回归测试。

不连接真机：设备、protocol、HID 接口全部用 fake 对象。
运行：python -m unittest discover -s tests -q
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import const, lighting  # noqa: E402
from mk87lib import device as device_mod  # noqa: E402
from mk87lib.device import DeviceStatus  # noqa: E402
from mk87lib.errors import MK87Error  # noqa: E402
from server import state  # noqa: E402


# ----------------------------------------------------------------------
# fake 设备
# ----------------------------------------------------------------------
class _FakeDevice:
    def __init__(self, info: dict, *, transport: str = "usb",
                 battery_24g=None) -> None:
        self.status = DeviceStatus(connected=True, transport=transport)
        self.info = dict(info)
        self.battery_24g = battery_24g
        self.info_calls = 0
        self.battery_24g_calls = 0

    def get_device_info(self) -> dict:
        self.info_calls += 1
        return dict(self.info)

    def read_battery_24g(self):
        self.battery_24g_calls += 1
        if isinstance(self.battery_24g, Exception):
            raise self.battery_24g
        return self.battery_24g


def _manager(device) -> "state.DeviceManager":
    """绕过 __init__：只装配 _refresh_battery 需要的字段。"""
    mgr = object.__new__(state.DeviceManager)
    mgr.device = device
    mgr.lock = threading.RLock()
    mgr.loop = None
    mgr.subscribers = []
    mgr.sub_lock = threading.Lock()
    mgr.tft_job = SimpleNamespace(running=False)
    mgr._recent_events = []
    mgr._last_battery = None
    mgr._last_battery_state = None
    mgr._battery_error = ""
    mgr._battery_error_at = 0.0
    mgr._battery_24g_fails = 0
    mgr._battery_24g_retry_at = 0.0
    mgr._conn_gen = 0
    mgr._stop = threading.Event()
    mgr.events = []
    mgr.emit = mgr.events.append
    return mgr


def _effect(mode: int, raw: bytes | None = None) -> dict:
    return {
        "mode": int(mode),
        "red": 255, "green": 255, "blue": 255,
        "secondary": (0, 0, 0),
        "colorMode": 1, "brightness": 5, "speed": 3,
        "direction": 0, "effectModeType": 0,
        "raw": raw if raw is not None else bytes([int(mode)] + [0] * 15),
    }


# ----------------------------------------------------------------------
# A. _refresh_battery
# ----------------------------------------------------------------------
class TestRefreshBattery(unittest.TestCase):
    def test_updates_charging_even_when_percent_unchanged(self):
        dev = _FakeDevice({"batteryLevel": 78, "chargeStatus": 0, "workMode": 1})
        mgr = _manager(dev)
        mgr._refresh_battery()
        self.assertEqual(dev.status.battery, 78)
        self.assertEqual(dev.status.charging, 0)
        self.assertEqual(dev.status.work_mode, 1)  # workMode 也要跟着刷新

        # 百分比不变、charging 变化：旧实现会整块跳过，这里必须更新并广播
        dev.info.update({"chargeStatus": 1, "workMode": 2})
        mgr._refresh_battery()
        self.assertEqual(dev.status.battery, 78)
        self.assertEqual(dev.status.charging, 1)
        self.assertEqual(dev.status.work_mode, 2)
        self.assertEqual(len(mgr.events), 2, "状态变化应各发一次 battery 事件")
        self.assertEqual(mgr.events[-1]["data"]["charging"], 1)
        self.assertEqual(mgr.events[-1]["data"]["workMode"], 2)
        self.assertEqual(dev.status.battery_source, "device_info")

    def test_failure_is_logged_and_rate_limited(self):
        dev = _FakeDevice({})
        dev.get_device_info = mock.Mock(side_effect=MK87Error("设备无响应"))
        mgr = _manager(dev)
        with self.assertLogs("mk87.state", level="WARNING") as cap:
            mgr._refresh_battery()
        self.assertIn("刷新电量失败", cap.output[0])
        self.assertIn("设备无响应", cap.output[0])
        # 相同错误 60s 内不再刷屏
        with self.assertNoLogs("mk87.state", level="WARNING"):
            mgr._refresh_battery()
        self.assertEqual(dev.status.battery, 0, "失败时不应把电量改成 0")

    def test_24g_uses_rgb_packet_battery(self):
        dev = _FakeDevice({"batteryLevel": 78, "chargeStatus": 0, "workMode": 0},
                          transport="2.4g", battery_24g=55)
        mgr = _manager(dev)
        mgr._refresh_battery()
        self.assertEqual(dev.status.battery, 55, "2.4G 应以 0x37 回包电量覆写 d[17]")
        self.assertEqual(dev.status.battery_source, "24g_rgb")

    def test_24g_failure_falls_back_to_device_info(self):
        dev = _FakeDevice({"batteryLevel": 78, "chargeStatus": 0, "workMode": 0},
                          transport="2.4g", battery_24g=MK87Error("2.4G 超时"))
        mgr = _manager(dev)
        with self.assertLogs("mk87.state", level="WARNING") as cap:
            mgr._refresh_battery()
        self.assertIn("2.4G 电量读取失败", cap.output[0])
        self.assertEqual(dev.status.battery, 78)
        self.assertEqual(dev.status.battery_source, "24g_fallback")

    def test_usb_never_calls_24g_path(self):
        dev = _FakeDevice({"batteryLevel": 78, "chargeStatus": 1, "workMode": 0})
        mgr = _manager(dev)
        mgr._refresh_battery()
        self.assertEqual(dev.battery_24g_calls, 0)


# ----------------------------------------------------------------------
# device.read_battery_24g 帧格式（2.4G 只读路径）
# ----------------------------------------------------------------------
class _FakeIface:
    def __init__(self) -> None:
        self.info = SimpleNamespace(payload_len=32)
        self.written = []
        self.responses = [bytes([0x55, 0x37, 0, 55]) + bytes(28)]

    def write_report(self, report: bytes) -> int:
        self.written.append(bytes(report))
        return len(report)

    def read_report(self, timeout: float = 0.1):
        return self.responses.pop(0) if self.responses else None


class TestBattery24GRead(unittest.TestCase):
    @staticmethod
    def _dev(iface, transport="2.4g"):
        dev = object.__new__(device_mod.MK87Device)
        dev._lock = threading.RLock()
        dev._tft_busy = threading.Event()
        dev._tft_busy_owner = None
        dev.status = DeviceStatus(connected=True, transport=transport)
        dev.protocol = SimpleNamespace(iface=iface)
        return dev

    def test_request_frame_and_battery_byte(self):
        iface = _FakeIface()
        dev = self._dev(iface)
        self.assertEqual(dev.read_battery_24g(), 55)
        self.assertEqual(len(iface.written), 1)
        pkt = iface.written[0]
        self.assertEqual(len(pkt), 33, "report ID + 32B payload")
        self.assertEqual(pkt[:5], bytes([0, 0xAA, 0x37, 0, 0]))
        self.assertEqual(pkt[5:], bytes(28), "请求体应全 0")

    def test_strips_linux_leading_report_id(self):
        iface = _FakeIface()
        iface.responses = [bytes([0, 0x55, 0x37, 0, 66]) + bytes(28)]
        self.assertEqual(self._dev(iface).read_battery_24g(), 66)

    def test_usb_returns_none_without_writing(self):
        iface = _FakeIface()
        dev = self._dev(iface, transport="usb")
        self.assertIsNone(dev.read_battery_24g())
        self.assertEqual(iface.written, [])


class TestStopMusic(unittest.TestCase):
    """退出顺序：music.stop() 之后必须确认 restore_effect 已记录（shell 依赖它）。"""

    def test_stop_music_when_not_running(self):
        mgr = _manager(_FakeDevice({}))
        calls = []
        mgr.music = SimpleNamespace(running=False, stop=lambda: calls.append("stop"))
        self.assertTrue(mgr.stop_music(0.5))
        self.assertEqual(calls, ["stop"], "即使未运行也应调用 stop（幂等清理）")

    def test_stop_music_waits_for_restore_record(self):
        mgr = _manager(_FakeDevice({}))

        def _stop():
            lighting.restore_effect(_FakeRequestDevice(), bytes([11] + [0] * 15))

        mgr.music = SimpleNamespace(running=True, stop=_stop)
        t0 = time.time()
        self.assertTrue(mgr.stop_music(1.0))
        self.assertLess(time.time() - t0, 0.9, "restore 已记录时应立即返回，不等满超时")


# ----------------------------------------------------------------------
# B. restore_effect：非法快照绝不写设备
# ----------------------------------------------------------------------
class _FakeRequestDevice:
    def __init__(self) -> None:
        self.calls = []

    def request(self, cmd, payload=b"", **kwargs):
        self.calls.append((cmd, bytes(payload), kwargs))
        return b""


class TestRestoreEffect(unittest.TestCase):
    def test_valid_snapshot_written_back(self):
        dev = _FakeRequestDevice()
        snap = bytes([11] + [0] * 15)
        self.assertTrue(lighting.restore_effect(dev, snap))
        self.assertEqual(len(dev.calls), 1)
        self.assertEqual(dev.calls[0][0], const.CMD["SET_LED_EFFECT"])
        self.assertEqual(dev.calls[0][1], snap)

    def test_mode_zero_snapshot_skipped(self):
        dev = _FakeRequestDevice()
        with self.assertLogs("mk87.lighting", level="WARNING") as cap:
            self.assertFalse(lighting.restore_effect(dev, bytes(16)))
        self.assertEqual(dev.calls, [], "被污染的 mode=0 快照不能原样写回")
        self.assertIn("快照无效", cap.output[0])

    def test_unknown_mode_snapshot_skipped(self):
        dev = _FakeRequestDevice()
        with self.assertLogs("mk87.lighting", level="WARNING"):
            self.assertFalse(lighting.restore_effect(dev, bytes([200] + [0] * 15)))
        self.assertEqual(dev.calls, [])

    def test_empty_snapshot_skipped(self):
        dev = _FakeRequestDevice()
        with self.assertLogs("mk87.lighting", level="WARNING"):
            self.assertFalse(lighting.restore_effect(dev, b""))
        self.assertEqual(dev.calls, [])

    def test_invalid_snapshot_uses_fallback(self):
        dev = _FakeRequestDevice()
        fallback = bytes([11] + [0] * 15)
        with self.assertLogs("mk87.lighting", level="WARNING") as cap:
            self.assertTrue(lighting.restore_effect(dev, bytes(16), fallback=fallback))
        self.assertIn("fallback", cap.output[0])
        self.assertEqual(len(dev.calls), 1)
        self.assertEqual(dev.calls[0][1], fallback)

    def test_invalid_snapshot_and_invalid_fallback_skipped(self):
        dev = _FakeRequestDevice()
        with self.assertLogs("mk87.lighting", level="WARNING"):
            self.assertFalse(lighting.restore_effect(dev, bytes(16), fallback=bytes(16)))
        self.assertEqual(dev.calls, [])

    def test_restore_state_recorded_for_shell_wait(self):
        dev = _FakeRequestDevice()
        lighting.restore_effect(dev, bytes([11] + [0] * 15))
        st = lighting.restore_state()
        self.assertEqual(st["mode"], 11)
        self.assertEqual(st["result"], "restored")
        self.assertGreater(st["ts"], 0)


# ----------------------------------------------------------------------
# B. ensure_frame_mode：用 20/21，不用 128
# ----------------------------------------------------------------------
class _FakeLightingDevice:
    def __init__(self, start_mode: int = 6, readback_modes=None) -> None:
        self.mode = int(start_mode)
        self.readback_modes = list(readback_modes or [])
        self.writes = []
        self.raws = []

    def get_led_effect(self) -> dict:
        return _effect(self.mode)

    def set_led_effect(self, mode=1, **kwargs) -> bytes:
        self.writes.append(int(mode))
        raw = bytearray(16)
        raw[0] = int(mode)
        raw[8] = 1
        raw[9] = 5
        raw[10] = 3
        raw[14] = 0xAA
        raw[15] = 0x55
        self.raws.append(bytes(raw))
        self.mode = self.readback_modes.pop(0) if self.readback_modes else int(mode)
        return bytes(raw)


class TestEnsureFrameMode(unittest.TestCase):
    def test_uses_mode_20_not_128(self):
        dev = _FakeLightingDevice(start_mode=6)
        snap = lighting.ensure_frame_mode(dev)
        self.assertEqual(dev.writes, [20])
        self.assertNotIn(128, dev.writes)
        self.assertEqual(snap["entryMode"], 20)
        self.assertEqual(snap["wasMode"], 6)
        self.assertEqual(snap["before"][0], 6, "快照应是进入前的原始灯效")

    def test_already_custom_family_does_not_write(self):
        dev = _FakeLightingDevice(start_mode=21)
        snap = lighting.ensure_frame_mode(dev)
        self.assertEqual(dev.writes, [])
        self.assertEqual(snap["entryMode"], 21)

    def test_falls_back_to_21_when_20_zeroed(self):
        dev = _FakeLightingDevice(start_mode=6, readback_modes=[0, 21])
        with self.assertLogs("mk87.lighting", level="WARNING"):
            snap = lighting.ensure_frame_mode(dev)
        self.assertEqual(dev.writes, [20, 21])
        self.assertEqual(snap["entryMode"], 21)

    def test_all_readbacks_abnormal_still_returns_snapshot(self):
        dev = _FakeLightingDevice(start_mode=6, readback_modes=[0, 0])
        with self.assertLogs("mk87.lighting", level="WARNING"):
            snap = lighting.ensure_frame_mode(dev)
        self.assertEqual(dev.writes, [20, 21])
        self.assertIsNone(snap["entryMode"])
        self.assertEqual(snap["before"][0], 6)


# ----------------------------------------------------------------------
# 128 写后归零告警（set_custom）
# ----------------------------------------------------------------------
class _FakeCustomDevice:
    def __init__(self) -> None:
        self.mode = 0
        self.writes = []

    def write_custom_led_data(self, buf: bytes) -> bytes:
        return bytes(buf)

    def get_led_effect(self) -> dict:
        return _effect(self.mode)

    def set_led_effect(self, mode=1, **kwargs) -> bytes:
        self.writes.append(int(mode))
        self.mode = 0  # fw1.19：写 128 后回读 0
        return b""


class TestSetCustomZeroReadback(unittest.TestCase):
    def test_warns_when_mode_128_zeroed(self):
        dev = _FakeCustomDevice()
        with self.assertLogs("mk87.lighting", level="WARNING") as cap:
            res = lighting.set_custom(dev, {0: (255, 0, 0)}, apply=True)
        self.assertEqual(dev.writes, [128])
        self.assertEqual(res["readbackMode"], 0)
        self.assertIn("mode 128 被固件归零", cap.output[0])


# ----------------------------------------------------------------------
# D. GET /api/lighting 的 isCustom 兜底
# ----------------------------------------------------------------------
class _FakeEffectDevice:
    def __init__(self, mode: int, colors=None, *, transport: str = "usb") -> None:
        self._mode = int(mode)
        self._colors = dict(colors or {})
        self.status = DeviceStatus(connected=True, transport=transport)
        self.lights_calls = 0

    def get_led_effect(self) -> dict:
        return _effect(self._mode)

    def get_lights_frame(self) -> dict:
        self.lights_calls += 1
        return dict(self._colors)


class TestIsCustomFallback(unittest.TestCase):
    def test_resolve_is_custom_pure_logic(self):
        self.assertTrue(lighting.resolve_is_custom(128))
        self.assertTrue(lighting.resolve_is_custom(20))
        self.assertTrue(lighting.resolve_is_custom(21))
        self.assertFalse(lighting.resolve_is_custom(0, {}))
        self.assertFalse(lighting.resolve_is_custom(0, {1: (0, 0, 0)}))
        self.assertTrue(lighting.resolve_is_custom(0, {1: (0, 0, 0), 2: (1, 0, 0)}))
        self.assertFalse(lighting.resolve_is_custom(11, {1: (255, 0, 0)}),
                         "非 0 的普通模式不应因逐键表有颜色而判成自定义")

    def test_mode_zero_lit_table_returns_is_custom(self):
        dev = _FakeEffectDevice(0, {4: (255, 0, 0)}, transport="usb")
        effect = lighting.get_effect_with_custom_fallback(dev)
        self.assertEqual(dev.lights_calls, 1)
        self.assertTrue(effect["isCustom"])
        self.assertEqual(effect["mode"], 0, "不应篡改 mode 字段")

    def test_mode_zero_black_table_not_custom(self):
        dev = _FakeEffectDevice(0, {4: (0, 0, 0)}, transport="usb")
        self.assertFalse(lighting.get_effect_with_custom_fallback(dev)["isCustom"])

    def test_normal_mode_skips_probe(self):
        dev = _FakeEffectDevice(11, {4: (255, 0, 0)}, transport="usb")
        self.assertFalse(lighting.get_effect_with_custom_fallback(dev)["isCustom"])
        self.assertEqual(dev.lights_calls, 0)

    def test_2_4g_mode_zero_skips_probe(self):
        dev = _FakeEffectDevice(0, {4: (255, 0, 0)}, transport="2.4g")
        self.assertFalse(lighting.get_effect_with_custom_fallback(dev)["isCustom"])
        self.assertEqual(dev.lights_calls, 0, "2.4G 不应发 0x33 整表读（22 包）")

    def test_api_lighting_delegates_to_fallback(self):
        from server import app as server_app

        fake_dev = object()
        with mock.patch.object(server_app, "_dev", return_value=fake_dev), \
                mock.patch.object(server_app.lighting, "get_effect_with_custom_fallback",
                                  return_value={"ok": True}) as fn:
            self.assertEqual(server_app.api_lighting(), {"ok": True})
        fn.assert_called_once_with(fake_dev)


if __name__ == "__main__":
    unittest.main(verbosity=2)
