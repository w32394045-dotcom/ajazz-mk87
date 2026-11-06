"""音乐律动会话守护 / 自动恢复 / 保后台接入的单测（v0.1.8.4）。

背景（用户 2026-11-06 实机事故 + py-spy 线程栈）：Windows 进入连接待机后
HID `WriteFile` 永久阻塞，`mk87-music` 线程停在 `NativeHidChannel.write`；
另一条路径是写失败 51 次后线程静默退出。两种情况下 `/api/music/status` 的
`running` 仍为 True、界面继续显示「律动中」，电平条冻结。

这里用假音频采集 / 假发送器 / 假保活句柄验证修复后的行为：
* 音频采集卡死（无新数据）→ 自动重建会话；
* HID 连续发送失败 → 自动重建会话；
* 原音频设备失效 → 回退默认输出回环；
* 恢复期间热更新参数不丢；
* status 暴露 health / recoveries / frameAgeMs / keepAwake 等字段；
* 用户 stop 能及时退出并停掉保后台。
"""
import threading
import time
import unittest
from unittest import mock

import numpy as np

from mk87lib import lighting, music


# ----------------------------------------------------------------------
# 假对象
# ----------------------------------------------------------------------
class _FakeDevice:
    """MusicPlayer 只用 transport / status.connected。"""

    transport = "usb"

    class status:  # noqa: N801 - 简单命名空间
        connected = True


class _FakeAnalyzer:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate

    def analyze(self, samples, dt_scale=1.0):
        return {"amp": 0.42, "amp1000": 420,
                "bands": [0.1, 0.2, 0.3], "bands32": [0.5] * 32}


class _FakeKeepAlive:
    instances = []

    def __init__(self):
        self.started = False
        self.stopped = False
        _FakeKeepAlive.instances.append(self)

    @property
    def active(self):
        return self.started and not self.stopped

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.stopped = True


class _NormalCapture:
    """正常音频采集：每次 read 都刷新数据时间戳。"""

    samplerate = 48000

    def __init__(self, device_id=None):
        self.device_id = device_id
        self.last_data_ts = None
        self.closed = False
        self.reads = 0

    def open(self):
        self.last_data_ts = time.monotonic()

    def read(self, frames=2048):
        self.reads += 1
        self.last_data_ts = time.monotonic()
        return np.zeros(frames, dtype=np.float32)

    def close(self):
        self.closed = True


class _StallingCapture(_NormalCapture):
    """第 3 次 read 起假装采集线程卡死（时间戳不再更新）。"""

    def read(self, frames=2048):
        self.reads += 1
        if self.reads >= 3:
            self.last_data_ts = time.monotonic() - 60.0
        return np.zeros(frames, dtype=np.float32)


class _RecordingSender:
    def __init__(self, fail=False):
        self.body = 64
        self.frames = 0
        self.acks = 0
        self.closed = False
        self.fail = fail

    def frame_packets(self, payload):
        return 7

    def send(self, payload, frame_index=0, wait_ack=True,
             ack_timeout=0.006, drain=0):
        if self.fail:
            raise OSError("WriteFile 超时（设备无响应）")
        self.frames += 1
        return 7

    def read_ack(self, timeout=0.1):
        return None

    def close(self):
        self.closed = True


def _wait_until(pred, timeout=5.0):
    """轮询等待条件成立（测试线程用，避免固定 sleep 造成偶发失败）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


class _MusicTestBase(unittest.TestCase):
    def setUp(self):
        self._patches = [
            mock.patch.object(music, "Analyzer", _FakeAnalyzer),
            mock.patch.object(lighting, "ensure_frame_mode",
                              lambda dev: {"before": b"\x02"}),
            mock.patch.object(lighting, "restore_effect",
                              lambda dev, raw, fallback=None: True),
            mock.patch.object(music.powerkeep, "keep_awake",
                              lambda: _FakeKeepAlive()),
        ]
        for patch in self._patches:
            patch.start()
        _FakeKeepAlive.instances.clear()

    def tearDown(self):
        for patch in reversed(self._patches):
            patch.stop()


# ----------------------------------------------------------------------
# 1) 音频采集卡死 → 自动恢复
# ----------------------------------------------------------------------
class TestAudioStallRecovery(_MusicTestBase):
    def test_audio_stall_triggers_auto_recovery(self):
        captures = []
        senders = []

        def cap_factory(device_id=None):
            cap = (_StallingCapture if not captures else _NormalCapture)(device_id)
            captures.append(cap)
            return cap

        def sender_factory(dev):
            sender = _RecordingSender()
            senders.append(sender)
            return sender

        with mock.patch.object(music, "AudioCapture", cap_factory), \
                mock.patch.object(lighting, "FrameSender", sender_factory):
            player = music.MusicPlayer(_FakeDevice())
            self.addCleanup(player.stop)
            player.start(fps=20)
            self.assertTrue(_wait_until(lambda: player.recoveries >= 1, 5.0),
                            "音频采集卡死应触发自动恢复")
            self.assertTrue(_wait_until(lambda: len(captures) >= 2, 5.0),
                            "应重建音频采集（第二次会话）")
            self.assertTrue(_wait_until(lambda: senders[-1].frames >= 2, 5.0),
                            "恢复后应继续向键盘下发帧")
            self.assertTrue(_wait_until(lambda: player.health == "ok", 5.0),
                            "恢复成功后健康状态应回到 ok")
            st = player.status()
            self.assertEqual(st["recoveries"], 1)
            self.assertEqual(st["health"], "ok")
            self.assertGreater(st["frames"], 0)
            player.stop()
        self.assertTrue(captures[0].closed, "旧音频采集应被关闭")
        self.assertTrue(_FakeKeepAlive.instances[0].stopped,
                        "停止律动必须停掉保后台")

    def test_audio_stall_does_not_count_recovery_before_first_session(self):
        """首次会话就建立失败（如设备未就绪）不应累计「自动恢复」次数。"""
        attempts = {"n": 0}

        def cap_factory(device_id=None):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise RuntimeError("音频设备暂时不可用")
            return _NormalCapture(device_id)

        with mock.patch.object(music, "AudioCapture", cap_factory), \
                mock.patch.object(lighting, "FrameSender",
                                  lambda dev: _RecordingSender()):
            player = music.MusicPlayer(_FakeDevice())
            self.addCleanup(player.stop)
            # 首次 start 会等待 _ready；先让首次失败暴露出来
            with self.assertRaises(music.MK87Error):
                player.start(fps=20)
        # 首次启动失败 → 线程退出、保后台停止，不会进入自动恢复
        self.assertEqual(player.health, "stopped")
        self.assertTrue(_FakeKeepAlive.instances[0].stopped)


# ----------------------------------------------------------------------
# 2) HID 连续发送失败 → 自动恢复
# ----------------------------------------------------------------------
class TestSendErrorRecovery(_MusicTestBase):
    def test_send_errors_trigger_auto_recovery(self):
        senders = []

        def sender_factory(dev):
            sender = _RecordingSender(fail=not senders)  # 第一段会话永远写失败
            senders.append(sender)
            return sender

        with mock.patch.object(music, "AudioCapture", _NormalCapture), \
                mock.patch.object(lighting, "FrameSender", sender_factory):
            player = music.MusicPlayer(_FakeDevice())
            self.addCleanup(player.stop)
            player.start(fps=20)
            self.assertTrue(_wait_until(lambda: player.recoveries >= 1, 5.0),
                            "连续发送失败应触发自动恢复")
            self.assertTrue(_wait_until(lambda: len(senders) >= 2, 5.0),
                            "应重建 HID 发送通道")
            self.assertTrue(_wait_until(lambda: senders[-1].frames >= 2, 5.0),
                            "新通道应能继续下发帧")
            self.assertGreater(player.status()["errors"], 0)
            player.stop()
        self.assertTrue(senders[0].closed, "坏掉的发送器应被关闭")

    def test_send_errors_below_limit_do_not_restart(self):
        """偶发 1-2 次失败不应重建会话（避免抖动）。"""
        senders = []

        def sender_factory(dev):
            sender = _RecordingSender()
            senders.append(sender)
            return sender

        with mock.patch.object(music, "AudioCapture", _NormalCapture), \
                mock.patch.object(lighting, "FrameSender", sender_factory):
            player = music.MusicPlayer(_FakeDevice())
            self.addCleanup(player.stop)
            player.start(fps=20)
            # 第 2 帧失败一次，之后恢复（不触发重建）
            calls = {"n": 0}
            real_send = senders[0].send

            def _flaky_send(*args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise OSError("WriteFile 失败: 995")
                return real_send(*args, **kwargs)

            senders[0].send = _flaky_send
            self.assertTrue(_wait_until(lambda: senders[0].frames >= 6, 3.0))
            self.assertEqual(player.recoveries, 0, "偶发失败不应触发自动恢复")
            self.assertGreaterEqual(player.status()["errors"], 1)
            player.stop()


# ----------------------------------------------------------------------
# 3) 音频设备失效 → 回退默认输出
# ----------------------------------------------------------------------
class TestAudioFallback(_MusicTestBase):
    def test_invalid_device_falls_back_to_default(self):
        opened = []

        def cap_factory(device_id=None):
            opened.append(device_id)
            if device_id is not None:
                raise RuntimeError("音频设备不存在")
            return _NormalCapture(device_id)

        with mock.patch.object(music, "AudioCapture", cap_factory), \
                mock.patch.object(lighting, "FrameSender",
                                  lambda dev: _RecordingSender()):
            player = music.MusicPlayer(_FakeDevice())
            self.addCleanup(player.stop)
            player.start(device_id="bad-device-id", fps=20)
            self.assertTrue(_wait_until(lambda: player.frames >= 2, 3.0))
            st = player.status()
            self.assertTrue(st["audioFallback"], "应标记回退默认输出")
            self.assertTrue(player._audio_fallback)
            self.assertEqual(opened[0], "bad-device-id")
            self.assertIsNone(opened[1], "回退时用默认输出回环")
            player.stop()


# ----------------------------------------------------------------------
# 4) 恢复期间热更新 / 状态字段 / 保后台
# ----------------------------------------------------------------------
class TestRecoveryUpdateAndStatus(_MusicTestBase):
    def test_update_while_recovering_caches_params(self):
        player = music.MusicPlayer(_FakeDevice())
        player._thread = threading.Thread(target=lambda: time.sleep(0.5), daemon=True)
        player._thread.start()
        self.addCleanup(player.stop)
        player._engine = None
        player.health = "recovering"
        st = player.update(mode=14, amplitude=80, fps=30, color="ice")
        self.assertEqual(player.mode, 14, "恢复中也要记住显示模式")
        self.assertEqual(player.amplitude_ui, 80)
        self.assertEqual(player.fps, 30)
        self.assertEqual(player.color, "ice")
        self.assertEqual(st["health"], "recovering")
        self.assertEqual(st["targetFps"], 30)
        player.stop()

    def test_status_exposes_health_and_frame_age(self):
        with mock.patch.object(music, "AudioCapture", _NormalCapture), \
                mock.patch.object(lighting, "FrameSender",
                                  lambda dev: _RecordingSender()):
            player = music.MusicPlayer(_FakeDevice())
            self.addCleanup(player.stop)
            player.start(fps=20)
            self.assertTrue(_wait_until(lambda: player.frames >= 3, 3.0))
            st = player.status()
            self.assertEqual(st["health"], "ok")
            self.assertEqual(st["recoveries"], 0)
            self.assertIsNotNone(st["frameAgeMs"])
            self.assertLess(st["frameAgeMs"], 2000)
            self.assertTrue(st["keepAwake"], "律动期间保后台应生效")
            self.assertTrue(st["deviceConnected"])
            player.stop()
        st = player.status()
        self.assertEqual(st["health"], "stopped")
        self.assertIsNone(st["frameAgeMs"])
        self.assertFalse(st["keepAwake"], "停止后保后台应关闭")
        self.assertTrue(_FakeKeepAlive.instances[0].stopped)

    def test_stop_during_recovery_exits_quickly(self):
        senders = []

        def sender_factory(dev):
            sender = _RecordingSender(fail=True)
            senders.append(sender)
            return sender

        with mock.patch.object(music, "AudioCapture", _NormalCapture), \
                mock.patch.object(lighting, "FrameSender", sender_factory):
            player = music.MusicPlayer(_FakeDevice())
            player.start(fps=20)
            self.assertTrue(_wait_until(lambda: player.recoveries >= 1, 5.0))
            started = time.monotonic()
            player.stop()
            self.assertLess(time.monotonic() - started, 3.0, "恢复等待中 stop 必须及时退出")
            self.assertFalse(player.running)
        self.assertTrue(_FakeKeepAlive.instances[0].stopped)


if __name__ == "__main__":
    unittest.main()
