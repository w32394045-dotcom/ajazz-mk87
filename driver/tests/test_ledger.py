"""灯效账本（mk87lib/ledger.py）与 TFT 上传自动暂停音乐的单测（v0.1.8.7）。

背景（2026-11-07 实机事故）：
* TFT 上传要求整机独占，但音乐帧流在自己的原生通道上持续写 0xFF68，
  `tft_exclusive` 挡不住它 → 上传第 1 包 4 次无 ACK 中止；
* 音乐/帧流停止后固件约 5s 会回落到逐键自定义表；若恢复被跳过
  （快照 mode=0 / 设备离线 / 进程崩溃），键盘就停在逐键态。

这里全部离线（假设备/假音乐），验证账本的记录、恢复链、pending 兜底，
以及「上传前暂停音乐、结束后自动恢复」的接口行为。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from mk87lib import const, ledger as ledger_mod


def _raw(mode: int, *, r: int = 255, g: int = 255, b: int = 255,
         brightness: int = 6, speed: int = 3) -> bytes:
    return ledger_mod.make_payload(mode, rgb=(r, g, b), brightness=brightness, speed=speed)


class _FakeDevice:
    """最小假设备：记录 SET_LED_EFFECT，可配置「固件忽略某些 mode」。"""

    def __init__(self) -> None:
        self.status = SimpleNamespace(connected=True)
        self.protocol = object()
        self.effect = _raw(1)
        self.custom = {34: (25, 253, 0), 49: (25, 253, 0),
                       50: (25, 253, 0), 51: (25, 253, 0),
                       83: (253, 127, 223)}
        self.lights = {}
        self.writes = []
        #: 写入后固件不生效的 mode（模拟写入被拒绝/归零）
        self.ignore_modes = set()

    def request(self, cmd, payload=b"", **kwargs):
        raw = bytes(payload)[:16]
        self.writes.append((int(cmd), raw))
        if int(cmd) == const.CMD["SET_LED_EFFECT"]:
            mode = raw[0]
            if mode in self.ignore_modes:
                return b""
            self.effect = raw
            if mode == 0:
                self.lights = {}
            elif mode in (20, 21, 128):
                self.lights = dict(self.custom)
            else:
                self.lights = {}
        return b""

    def get_led_effect(self):
        return {"raw": self.effect, "mode": self.effect[0]}

    def get_custom_colors(self):
        return dict(self.custom)

    def get_lights_frame(self):
        return dict(self.lights)


class _LedgerTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mk87-ledger-unit-")
        self.path = os.path.join(self.tmp, "lighting_state.json")
        self.led = ledger_mod.reset(self.path)
        self.dev = _FakeDevice()

    def tearDown(self) -> None:
        # 复位到另一个临时路径，避免后续用例复用本用例状态
        ledger_mod.reset(os.path.join(tempfile.mkdtemp(prefix="mk87-ledger-"), "state.json"))


# ----------------------------------------------------------------------
# 1) 纯函数：状态分类 / payload / 回读校验
# ----------------------------------------------------------------------
class TestStateModel(_LedgerTestBase):
    def test_state_from_raw_classification(self):
        self.assertEqual(ledger_mod.state_from_raw(_raw(7))["kind"], "effect")
        self.assertEqual(ledger_mod.state_from_raw(_raw(128))["kind"], "custom")
        self.assertEqual(ledger_mod.state_from_raw(_raw(20))["kind"], "custom")
        self.assertEqual(ledger_mod.state_from_raw(_raw(0))["kind"], "off")
        self.assertEqual(ledger_mod.state_from_raw(_raw(200))["kind"], "unknown")
        self.assertEqual(ledger_mod.state_from_raw(b"")["kind"], "unknown")

    def test_state_fields_parse(self):
        st = ledger_mod.state_from_raw(_raw(11, r=10, g=20, b=30, brightness=4, speed=2))
        self.assertEqual(st["mode"], 11)
        self.assertEqual(st["rgb"], [10, 20, 30])
        self.assertEqual(st["brightness"], 4)
        self.assertEqual(st["speed"], 2)
        self.assertEqual(st["colorMode"], 1)

    def test_payload_roundtrip(self):
        st = ledger_mod.state_from_raw(_raw(13))
        self.assertEqual(ledger_mod.payload_of(st), _raw(13))

    def test_payload_of_custom_forces_mode_128(self):
        st = ledger_mod.state_from_raw(_raw(21, brightness=5))
        self.assertEqual(ledger_mod.payload_of(st)[0], 128)

    def test_default_state_is_static_white(self):
        st = ledger_mod.default_state()
        self.assertEqual(st["kind"], "effect")
        self.assertEqual(st["mode"], 1)
        self.assertEqual(st["rgb"], [255, 255, 255])

    def test_states_match(self):
        eff11 = ledger_mod.state_from_raw(_raw(11))
        eff12 = ledger_mod.state_from_raw(_raw(12))
        custom = ledger_mod.state_from_raw(_raw(128))
        off = ledger_mod.state_from_raw(_raw(0))
        self.assertTrue(ledger_mod.states_match(eff11, eff11))
        self.assertFalse(ledger_mod.states_match(eff11, eff12))
        self.assertTrue(ledger_mod.states_match(custom, custom))
        self.assertTrue(ledger_mod.states_match(off, off))
        self.assertFalse(ledger_mod.states_match(eff11, None))

    def test_public_view_names(self):
        eff = ledger_mod.public_view(ledger_mod.state_from_raw(_raw(7)))
        self.assertEqual(eff["kind"], "effect")
        self.assertEqual(eff["mode"], 7)
        self.assertTrue(eff["name"])
        custom = ledger_mod.public_view(ledger_mod.state_from_raw(_raw(128)))
        self.assertEqual(custom["kind"], "custom")
        self.assertIn("自定义", custom["name"])
        off = ledger_mod.public_view(ledger_mod.state_from_raw(_raw(0)))
        self.assertEqual(off["name"], "关灯")

    def test_default_path_env_override(self):
        target = os.path.join(self.tmp, "custom-ledger.json")
        with mock.patch.dict(os.environ, {"MK87_LEDGER_PATH": target}):
            self.assertEqual(ledger_mod.default_path(), target)


# ----------------------------------------------------------------------
# 2) 深度读状态：mode 0 的「关灯 / 逐键态」区分
# ----------------------------------------------------------------------
class TestReadState(_LedgerTestBase):
    def test_mode0_with_custom_table_is_custom(self):
        self.dev.effect = _raw(0)
        self.dev.lights = dict(self.dev.custom)
        st = ledger_mod.read_state(self.dev, deep=True)
        self.assertEqual(st["kind"], "custom")
        self.assertEqual(st["mode"], 128)

    def test_mode0_black_lights_is_off(self):
        self.dev.effect = _raw(0)
        self.dev.lights = {}
        st = ledger_mod.read_state(self.dev, deep=True)
        self.assertEqual(st["kind"], "off")

    def test_mode0_mismatched_lights_is_off(self):
        self.dev.effect = _raw(0)
        self.dev.lights = {1: (255, 0, 0)}
        self.assertEqual(ledger_mod.read_state(self.dev, deep=True)["kind"], "off")

    def test_effect_mode_skips_deep_read(self):
        self.dev.effect = _raw(9)
        self.dev.lights = dict(self.dev.custom)  # 不该被用到
        self.assertEqual(ledger_mod.read_state(self.dev, deep=True)["kind"], "effect")

    def test_lights_match_custom(self):
        self.dev.lights = dict(self.dev.custom)
        self.assertTrue(ledger_mod.lights_match_custom(self.dev))
        self.dev.lights = {}
        self.assertFalse(ledger_mod.lights_match_custom(self.dev))
        self.dev.custom = {}
        self.dev.lights = {}
        self.assertFalse(ledger_mod.lights_match_custom(self.dev))


# ----------------------------------------------------------------------
# 3) 持久化：last / pending 原子落盘
# ----------------------------------------------------------------------
class TestPersistence(_LedgerTestBase):
    def test_last_persists_across_instances(self):
        self.led.set_last(ledger_mod.state_from_raw(_raw(7)), source="app")
        with open(self.path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["version"], ledger_mod.SCHEMA_VERSION)
        self.assertEqual(saved["last"]["mode"], 7)
        other = ledger_mod.new_ledger(self.path)
        self.assertEqual(other.last()["mode"], 7)
        self.assertEqual(other.last()["source"], "app")

    def test_pending_set_clear(self):
        self.assertIsNone(self.led.pending())
        self.led.set_pending(ledger_mod.state_from_raw(_raw(11)), reason="stream")
        self.assertIsNotNone(self.led.pending())
        self.assertEqual(self.led.pending()["target"]["mode"], 11)
        self.led.clear_pending()
        self.assertIsNone(ledger_mod.new_ledger(self.path).pending())

    def test_corrupt_file_treated_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        led = ledger_mod.new_ledger(self.path)
        self.assertIsNone(led.last())
        self.assertIsNone(led.pending())


# ----------------------------------------------------------------------
# 4) 恢复链：快照 → 账本 last → 默认静态恒亮
# ----------------------------------------------------------------------
class TestRestoreChain(_LedgerTestBase):
    def test_resolve_target_prefers_valid_snapshot(self):
        self.led.set_last(ledger_mod.state_from_raw(_raw(9)))
        target = ledger_mod.resolve_target({"before": _raw(11)})
        self.assertEqual(target["mode"], 11)

    def test_resolve_target_invalid_snapshot_uses_last(self):
        self.led.set_last(ledger_mod.state_from_raw(_raw(9)))
        target = ledger_mod.resolve_target({"before": _raw(0)})
        self.assertEqual(target["mode"], 9)

    def test_resolve_target_none(self):
        self.assertIsNone(ledger_mod.resolve_target(None))
        self.assertIsNone(ledger_mod.resolve_target({"before": _raw(0)}))

    def test_apply_state_effect_ok(self):
        res = ledger_mod.apply_state(self.dev, ledger_mod.state_from_raw(_raw(11)))
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.effect[0], 11)

    def test_apply_state_offline_fast_fail(self):
        self.dev.status.connected = False
        t0 = time.monotonic()
        res = ledger_mod.apply_state(self.dev, ledger_mod.state_from_raw(_raw(11)))
        self.assertLess(time.monotonic() - t0, 0.2)
        self.assertFalse(res["ok"])
        self.assertEqual(res["result"], "offline")
        self.assertEqual(self.dev.writes, [])

    def test_apply_state_custom_verified_by_lights(self):
        st = ledger_mod.state_from_raw(_raw(128))
        res = ledger_mod.apply_state(self.dev, st, reason="test")
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.effect[0], 128)
        self.assertEqual(ledger_mod.read_state(self.dev, deep=True)["kind"], "custom")


# ----------------------------------------------------------------------
# 5) 帧流生命周期：begin_stream / end_stream / pending
# ----------------------------------------------------------------------
class TestStreamLifecycle(_LedgerTestBase):
    def test_begin_stream_uses_snapshot_and_persists_pending(self):
        target = ledger_mod.begin_stream(self.dev, {"before": _raw(11)})
        self.assertEqual(target["mode"], 11)
        self.assertEqual(self.led.pending()["target"]["mode"], 11)
        self.assertEqual(self.led.last()["mode"], 11)
        # 落盘可读（模拟崩溃后重启）
        self.assertEqual(ledger_mod.new_ledger(self.path).pending()["target"]["mode"], 11)

    def test_begin_stream_reads_device_when_no_snapshot(self):
        self.dev.effect = _raw(5)
        target = ledger_mod.begin_stream(self.dev, None)
        self.assertEqual(target["mode"], 5)
        self.assertEqual(self.led.pending()["target"]["mode"], 5)

    def test_begin_stream_reuses_existing_pending(self):
        self.led.set_pending(ledger_mod.state_from_raw(_raw(12)), reason="stream")
        target = ledger_mod.begin_stream(self.dev, {"before": _raw(3)})
        self.assertEqual(target["mode"], 12, "上次未完成的恢复目标优先（不能丢用户原灯效）")

    def test_begin_stream_keeps_off_state(self):
        # 设备当前是「关灯」（mode 0 + 0x33 全黑）→ 结束后应恢复关灯，而不是白灯
        self.dev.effect = _raw(0)
        self.dev.lights = {}
        target = ledger_mod.begin_stream(self.dev, {"before": _raw(0)})
        self.assertEqual(target["kind"], "off")

    def test_begin_stream_defaults_to_static_white_when_unreadable(self):
        with mock.patch.object(ledger_mod, "read_state", side_effect=RuntimeError("no device")):
            target = ledger_mod.begin_stream(self.dev, {"before": _raw(0)})
        self.assertEqual(target["kind"], "effect")
        self.assertEqual(target["mode"], 1)

    def test_end_stream_restores_and_clears_pending(self):
        self.led.set_pending(ledger_mod.state_from_raw(_raw(11)), reason="stream")
        res = ledger_mod.end_stream(self.dev, {"before": _raw(11)})
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.effect[0], 11)
        self.assertIsNone(self.led.pending())
        self.assertEqual(self.led.last()["mode"], 11)

    def test_end_stream_offline_keeps_pending(self):
        self.dev.status.connected = False
        self.led.set_pending(ledger_mod.state_from_raw(_raw(11)), reason="stream")
        res = ledger_mod.end_stream(self.dev, None)
        self.assertFalse(res["ok"])
        self.assertEqual(res["result"], "offline")
        self.assertIsNotNone(self.led.pending(), "离线时 pending 必须保留，重连后补写")
        self.assertEqual(self.dev.writes, [])

    def test_end_stream_falls_back_to_static_white(self):
        # 固件拒绝写 mode=11（回读仍是别的值）→ 降级写静态恒亮（mode 1）
        self.dev.ignore_modes = {11}
        self.led.set_pending(ledger_mod.state_from_raw(_raw(11)), reason="stream")
        res = ledger_mod.end_stream(self.dev, None)
        self.assertTrue(res["ok"], "降级恢复应成功，不能停在逐键态")
        modes = [raw[0] for _, raw in self.dev.writes]
        self.assertEqual(modes[0], 11)
        self.assertIn(1, modes, "目标恢复失败后应降级写 mode=1")
        self.assertIsNone(self.led.pending())


# ----------------------------------------------------------------------
# 6) 重连 / 启动补恢复
# ----------------------------------------------------------------------
class TestPendingRecovery(_LedgerTestBase):
    def test_flush_pending_restores_target(self):
        target = ledger_mod.state_from_raw(_raw(4))
        self.led.set_pending(target, reason="crash")
        res = ledger_mod.flush_pending(self.dev, reason="reconnect")
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.effect[0], 4)
        self.assertIsNone(self.led.pending())

    def test_flush_pending_noop_without_pending(self):
        res = ledger_mod.flush_pending(self.dev)
        self.assertEqual(res["result"], "none")
        self.assertEqual(self.dev.writes, [])

    def test_resync_records_device_state(self):
        self.dev.effect = _raw(9)
        res = ledger_mod.resync(self.dev, reason="startup")
        self.assertTrue(res["ok"])
        self.assertEqual(self.led.last()["mode"], 9)
        self.assertEqual(self.led.last()["source"], "device")

    def test_resync_flushes_pending_first(self):
        self.dev.effect = _raw(3)
        self.led.set_pending(ledger_mod.state_from_raw(_raw(9)), reason="crash")
        res = ledger_mod.resync(self.dev, reason="startup")
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.effect[0], 9)


# ----------------------------------------------------------------------
# 7) 服务层：TFT 上传自动暂停 / 恢复音乐
# ----------------------------------------------------------------------
class _FakeMusic:
    def __init__(self) -> None:
        self.running = True
        self.start_calls = []
        self.device = None

    def status(self):
        return {
            "deviceId": "{fake-device}", "mode": 13, "targetFps": 60,
            "backmode": 2, "backmodeBrightness": 80, "amplitude": 55,
            "color": "aurora", "sensitivity": 1.25,
        }

    def start(self, **kwargs):
        self.start_calls.append(kwargs)
        self.running = True
        return {"running": True}


class TestTftMusicPause(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mk87-ledger-manager-")
        ledger_mod.reset(os.path.join(self.tmp, "lighting_state.json"))
        from server import state as state_mod

        self.manager = state_mod.DeviceManager()
        self.manager.device.status.connected = True
        self.music = _FakeMusic()
        self.manager.music = self.music
        self.manager.stop_music = mock.Mock(return_value=True)

    def tearDown(self) -> None:
        ledger_mod.reset(os.path.join(tempfile.mkdtemp(prefix="mk87-ledger-"), "state.json"))

    def test_pause_returns_params_and_marks_status(self):
        token = self.manager.pause_music_for_upload()
        self.assertIsNotNone(token)
        self.assertEqual(token["params"]["mode"], 13)
        self.assertEqual(token["params"]["fps"], 60)
        self.assertTrue(self.manager.tft_job.status()["musicPaused"])
        self.manager.stop_music.assert_called_once()

    def test_pause_noop_when_music_not_running(self):
        self.music.running = False
        self.assertIsNone(self.manager.pause_music_for_upload())
        self.assertFalse(self.manager.tft_job.status()["musicPaused"])

    def test_resume_restarts_with_saved_params(self):
        token = self.manager.pause_music_for_upload()
        self.music.running = False
        ok = self.manager.resume_music_after_upload(token)
        self.assertTrue(ok)
        self.assertEqual(len(self.music.start_calls), 1)
        kwargs = self.music.start_calls[0]
        self.assertEqual(kwargs["mode"], 13)
        self.assertEqual(kwargs["fps"], 60)
        self.assertEqual(kwargs["backmode"], 2)
        self.assertEqual(kwargs["backmode_brightness"], 80)
        self.assertEqual(kwargs["amplitude"], 55)
        self.assertEqual(kwargs["color"], "aurora")
        self.assertEqual(kwargs["sensitivity"], 1.25)
        self.assertFalse(self.manager.tft_job.status()["musicPaused"])

    def test_resume_without_token_is_noop(self):
        self.assertFalse(self.manager.resume_music_after_upload(None))
        self.assertEqual(self.music.start_calls, [])

    def test_pause_twice_returns_same_token(self):
        """TFT 因设备重枚举重试时，不能丢第一次暂停时保存的参数。"""
        t1 = self.manager.pause_music_for_upload()
        self.music.running = False
        t2 = self.manager.pause_music_for_upload()
        self.assertIs(t1, t2)
        token = self.manager.resume_music_after_upload()
        self.assertTrue(token)
        self.assertEqual(self.music.start_calls[0]["mode"], 13)

    def test_tft_job_finally_resumes_paused_music(self):
        """任务结束（成功/失败/取消）统一由 TftJob 收尾恢复音乐。"""
        from server import state as state_mod

        self.manager.resume_music_after_upload = mock.Mock(return_value=True)
        job = state_mod.TftJob(self.manager)
        job.start(kind="file", frames=0, runner=lambda progress, cancel: {"packets": 1})
        deadline = time.time() + 5.0
        while job.running and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(job.running)
        self.manager.resume_music_after_upload.assert_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
