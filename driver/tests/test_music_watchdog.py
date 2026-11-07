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

v0.1.8.6 补充（2026-11-07 用户实机：切换键盘 Win/Mac 模式 → USB 重新枚举）：
* 发送连续 1167 → 设备离线 → state 层重连成功后 ≤5s 内自动恢复出帧，
  且 mode/amp/backmode/fps/color 参数不丢；
* 帧流看门狗：发送调用卡在内核 HID IO 里（不再出帧、也不再抛异常）时，
  看门狗必须强制重建会话，不能静默停更；
* 设备离线路径的会话收尾必须快速失败（不阻塞在死句柄 close / 灯效恢复上）。
"""
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from mk87lib import lighting, music
from mk87lib import ledger as ledger_mod

#: 保存真实实现：_MusicTestBase.setUp 会把 lighting.restore_effect /
#: ledger.begin_stream / ledger.end_stream 换成 no-op；需要验证真实恢复行为的
#: 用例要临时换回真实实现。
_REAL_RESTORE_EFFECT = lighting.restore_effect
_REAL_LEDGER_END = ledger_mod.end_stream


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
        # 灯效账本隔离到临时文件：不写用户真实配置，也避免用例之间互相污染
        self._ledger_dir = tempfile.mkdtemp(prefix="mk87-ledger-test-")
        ledger_mod.reset(os.path.join(self._ledger_dir, "lighting_state.json"))
        self._patches = [
            mock.patch.object(music, "Analyzer", _FakeAnalyzer),
            mock.patch.object(lighting, "ensure_frame_mode",
                              lambda dev: {"before": b"\x02"}),
            mock.patch.object(lighting, "restore_effect",
                              lambda dev, raw, fallback=None: True),
            # v0.1.8.7：会话收尾改走灯效账本；单测默认 no-op，
            # 真实恢复行为由 TestCloseSessionFastFail 换回真实实现单独验证。
            mock.patch.object(ledger_mod, "begin_stream",
                              lambda dev, snapshot=None: {"kind": "effect", "mode": 2}),
            mock.patch.object(ledger_mod, "end_stream",
                              lambda dev, snapshot=None, reason="": {
                                  "ok": True, "result": "restored"}),
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


# ----------------------------------------------------------------------
# 5) Win/Mac 模式切换 → USB 重新枚举 → 重连后自动恢复（v0.1.8.6）
# ----------------------------------------------------------------------
class _ReenumDevice:
    """可切换在线状态的假设备（模拟 state 层 monitor 线程的设备重连）。

    v0.1.8.7：补充最简 ``request`` / ``get_led_effect``，用于验证「会话收尾时
    灯效账本真的把 SET_LED_EFFECT 写回设备并回读校验」。
    """

    transport = "usb"

    class _Status:
        connected = True

    def __init__(self):
        self.status = _ReenumDevice._Status()
        self.writes = []
        self._last_effect = None

    def request(self, cmd, payload=b"", **kwargs):
        from mk87lib import const

        self.writes.append((int(cmd), bytes(payload)))
        if int(cmd) == const.CMD["SET_LED_EFFECT"]:
            self._last_effect = bytes(payload)[:16]
        return b""

    def get_led_effect(self):
        raw = self._last_effect or bytes(16)
        return {"raw": raw, "mode": raw[0]}


class _Fail1167Sender(_RecordingSender):
    """每次发送都抛 ``WriteFile 失败: 1167``（ERROR_DEVICE_NOT_CONNECTED）。

    首次失败时通过 ``on_first_fail`` 通知测试「设备已断开」（对应实机日志里
    13:59:44.407 第一条 1167 之后 0.5s state 层打印「设备已断开」）。
    """

    def __init__(self, on_first_fail=None):
        super().__init__()
        self._on_first_fail = on_first_fail

    def send(self, *args, **kwargs):
        cb = self._on_first_fail
        if cb is not None:
            self._on_first_fail = None
            cb()
        raise OSError("WriteFile 失败: 1167")


class TestModeSwitchReenumeration(_MusicTestBase):
    """实机 2026-11-07 13:59 场景：模式切换 → USB 重新枚举 → 掉线自动恢复。

    日志证据：连续 51 条 WriteFile 1167 → 「设备已断开」→ 6s 后「设备已连接」，
    但音乐既不再出帧也没有「自动恢复」日志，直到用户 14:06 手动重开。
    这里用假设备/假发送器复刻同一条链路，断言重连后 5s 内恢复、计数正确、参数不丢。
    """

    def test_recovers_within_5s_after_usb_reenumeration(self):
        dev = _ReenumDevice()
        senders: list = []

        def sender_factory(device):
            if not senders:
                sender = _Fail1167Sender(
                    on_first_fail=lambda: setattr(dev.status, "connected", False))
            else:
                sender = _RecordingSender()
            senders.append(sender)
            return sender

        with mock.patch.object(music, "AudioCapture", _NormalCapture), \
                mock.patch.object(lighting, "FrameSender", sender_factory):
            player = music.MusicPlayer(dev)
            self.addCleanup(player.stop)
            player.start(mode=14, amplitude=80, backmode=3, backmode_brightness=70,
                         fps=20, color="ice")
            self.assertTrue(_wait_until(lambda: player.recoveries >= 1, 5.0),
                            "连续发送 1167 应触发自动恢复计数")
            self.assertFalse(dev.status.connected)
            self.assertEqual(player.health, "waiting-device",
                             "键盘离线时应暴露 waiting-device（前端显示等待键盘）")
            # 离线等待期：只等重连，不反复累计恢复次数、不出假帧、线程不能死
            time.sleep(1.0)
            self.assertEqual(player.recoveries, 1, "离线等待不应反复累计「自动恢复」次数")
            self.assertEqual(player.frames, 0, "设备离线期间不应有成功下发的帧")
            self.assertTrue(player.running, "等待重连期间监督线程必须还活着")
            # 模拟 state 层 monitor 线程重连成功（实机约 6s，测试等 1s）
            dev.status.connected = True
            t0 = time.monotonic()
            self.assertTrue(
                _wait_until(lambda: player.health == "ok" and player.frames >= 2, 5.0),
                "设备重连后应在 5s 内自动恢复并继续出帧")
            latency = time.monotonic() - t0
            self.assertLess(latency, 5.0, f"重连后恢复耗时 {latency:.2f}s 超过 5s")
            self.assertEqual(player.recoveries, 1, "一次掉线只应累计一次自动恢复")
            self.assertGreaterEqual(len(senders), 2, "应重建 HID 发送通道")
            self.assertTrue(senders[0].closed, "坏掉的旧发送通道应被关闭")
            # 用户参数不得丢失（mode/amp/backmode/fps/color）
            st = player.status()
            self.assertEqual(st["mode"], 14)
            self.assertEqual(st["requestedMode"], 14)
            self.assertEqual(st["amplitude"], 80)
            self.assertEqual(st["backmode"], 3)
            self.assertEqual(st["backmodeBrightness"], 70)
            self.assertEqual(st["targetFps"], 20)
            self.assertEqual(st["color"], "ice")
            self.assertGreater(st["errors"], 0)
            self.assertGreaterEqual(st["frames"], 2)
            started = time.monotonic()
            player.stop()
            self.assertLess(time.monotonic() - started, 3.0, "恢复后 stop 必须及时退出")

    def test_recoveries_not_inflated_while_offline(self):
        """键盘持续离线时：health 停在 waiting-device，不刷 recoveries、不退出。"""
        dev = _ReenumDevice()

        def sender_factory(device):
            return _Fail1167Sender(
                on_first_fail=lambda: setattr(dev.status, "connected", False))

        with mock.patch.object(music, "AudioCapture", _NormalCapture), \
                mock.patch.object(lighting, "FrameSender", sender_factory):
            player = music.MusicPlayer(dev)
            self.addCleanup(player.stop)
            player.start(fps=20)
            self.assertTrue(_wait_until(lambda: player.recoveries >= 1, 5.0))
            time.sleep(1.2)  # 跨过多个 DEVICE_WAIT_POLL 周期
            self.assertEqual(player.recoveries, 1)
            self.assertEqual(player.health, "waiting-device")
            self.assertTrue(player.running)


# ----------------------------------------------------------------------
# 6) 帧流看门狗：发送调用卡死在 HID IO 里也要重建会话（v0.1.8.6）
# ----------------------------------------------------------------------
class _StuckSender(_RecordingSender):
    """前 ``ok_frames`` 帧正常，之后模拟 HID 写卡死（send 不再返回）。

    只有 ``close()`` 才让阻塞的 send 抛异常 —— 对应真实场景里看门狗旁路强关
    发送通道后，卡在内核里的 WriteFile 以 1167/995 返回。
    """

    def __init__(self, ok_frames=2):
        super().__init__()
        self.ok_frames = ok_frames
        self.release = threading.Event()
        self.blocked = threading.Event()

    def send(self, *args, **kwargs):
        if self.frames >= self.ok_frames:
            self.blocked.set()
            self.release.wait(10.0)
            raise OSError("HID 通道已关闭（看门狗强制重建）")
        return super().send(*args, **kwargs)

    def close(self):
        self.release.set()
        super().close()


class TestFrameStallWatchdog(_MusicTestBase):
    """只看「连续发送异常」覆盖不了的卡死形态：send 永不返回、也不抛异常。"""

    def _player(self, sender_factory):
        patches = [
            mock.patch.object(music, "AudioCapture", _NormalCapture),
            mock.patch.object(lighting, "FrameSender", sender_factory),
            # 把看门狗阈值压到毫秒级，避免单测真的等 2+3s
            mock.patch.object(music, "FRAME_STALL_TIMEOUT", 0.3),
            mock.patch.object(music, "WATCHDOG_INTERVAL", 0.05),
            mock.patch.object(music, "WATCHDOG_HARD_GRACE", 0.3),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        player = music.MusicPlayer(_FakeDevice())
        self.addCleanup(player.stop)
        return player

    def test_stalled_frame_stream_is_rebuilt_by_watchdog(self):
        senders: list = []

        def sender_factory(device):
            sender = _StuckSender(ok_frames=2) if not senders else _RecordingSender()
            senders.append(sender)
            return sender

        player = self._player(sender_factory)
        player.start(fps=20)
        self.assertTrue(_wait_until(lambda: senders and senders[0].frames >= 2, 2.0),
                        "会话建立后应先正常下发 2 帧")
        # 第 3 帧起 send 永久阻塞：既不出帧也不抛异常
        self.assertTrue(_wait_until(lambda: senders[0].blocked.is_set(), 2.0))
        self.assertTrue(_wait_until(lambda: player.stalls >= 1, 3.0),
                        ">FRAME_STALL_TIMEOUT 无成功帧时看门狗必须介入")
        self.assertTrue(
            _wait_until(lambda: len(senders) >= 2 and player.health == "ok"
                        and senders[-1].frames >= 2, 5.0),
            "看门狗应强制重建会话并恢复出帧（不能静默停更）")
        self.assertGreaterEqual(player.recoveries, 1)
        self.assertTrue(senders[0].closed, "卡死的旧发送通道应被强制关闭")
        st = player.status()
        self.assertGreaterEqual(st["stalls"], 1)
        self.assertEqual(st["health"], "ok")
        started = time.monotonic()
        player.stop()
        self.assertLess(time.monotonic() - started, 3.0, "看门狗场景下 stop 必须及时退出")

    def test_watchdog_does_not_fire_on_healthy_stream(self):
        senders: list = []

        def sender_factory(device):
            sender = _RecordingSender()
            senders.append(sender)
            return sender

        player = self._player(sender_factory)
        player.start(fps=20)
        self.assertTrue(_wait_until(lambda: senders and senders[0].frames >= 6, 3.0))
        self.assertEqual(player.stalls, 0, "正常出帧时看门狗不能误触发")
        self.assertEqual(player.recoveries, 0)
        self.assertEqual(player.health, "ok")


# ----------------------------------------------------------------------
# 7) 设备离线路径：会话收尾快速失败，不阻塞在死句柄/灯效恢复上
# ----------------------------------------------------------------------
class _BlockingCloseSender:
    """close() 模拟在途 IO 收割卡住（真机 NativeHidChannel.close 最长等 2s）。"""

    def __init__(self):
        self.close_started = None
        self.closed = False

    def close(self):
        self.close_started = time.monotonic()
        time.sleep(2.0)
        self.closed = True


class TestCloseSessionFastFail(_MusicTestBase):
    def test_offline_close_session_fast_fails(self):
        dev = _ReenumDevice()
        dev.status.connected = False
        player = music.MusicPlayer(dev)
        sender = _BlockingCloseSender()
        player._snapshot = {"before": bytes([11] + [0] * 15), "wasMode": 11}
        with mock.patch.object(ledger_mod, "end_stream", _REAL_LEDGER_END):
            t0 = time.monotonic()
            player._close_session(None, sender)
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.8,
                        f"设备离线时会话收尾应在 ~0.25s 内返回，实际 {elapsed:.2f}s")
        self.assertIsNotNone(sender.close_started, "仍应尝试关闭旧发送通道")
        # 灯效恢复走账本的设备离线快速失败（不发命令、立即记录，pending 保留待重连）
        restore = lighting.restore_state()
        self.assertEqual(restore["result"], "skipped-offline")
        self.assertEqual(restore["mode"], 11)
        self.assertEqual(dev.writes, [], "设备离线时不应发任何命令")
        self.assertIsNotNone(ledger_mod.get().pending(),
                             "离线恢复失败必须保留 pending，等重连/下次启动补写")
        self.assertIsNone(player._snapshot, "快照用掉后要清空，不能下次重复恢复")

    def test_restore_effect_offline_sends_no_command(self):
        """设备离线时 restore_effect 必须快速失败，不向死句柄发命令。"""
        calls = []

        class _OfflineDevice:
            protocol = None

            class status:  # noqa: N801 - 简单命名空间
                connected = False

            def request(self, *args, **kwargs):
                calls.append((args, kwargs))
                return b""

        t0 = time.monotonic()
        with mock.patch.object(lighting, "restore_effect", _REAL_RESTORE_EFFECT):
            ok = lighting.restore_effect(_OfflineDevice(), bytes([11] + [0] * 15))
        elapsed = time.monotonic() - t0
        self.assertFalse(ok)
        self.assertLess(elapsed, 0.2, "离线快速失败不能等命令超时")
        self.assertEqual(calls, [], "设备离线时不应发任何命令")
        self.assertEqual(lighting.restore_state()["result"], "skipped-offline")

    def test_online_close_session_still_restores_effect(self):
        dev = _ReenumDevice()
        player = music.MusicPlayer(dev)
        snap = bytes([11] + [0] * 15)
        player._snapshot = {"before": snap, "wasMode": 11}
        with mock.patch.object(ledger_mod, "end_stream", _REAL_LEDGER_END):
            player._close_session(None, _RecordingSender())
        from mk87lib import const

        effect_writes = [p for c, p in dev.writes if c == const.CMD["SET_LED_EFFECT"]]
        self.assertTrue(effect_writes, "设备在线时必须恢复进入前的灯效")
        self.assertEqual(effect_writes[0][0], 11, "必须写回快照的 mode=11")
        self.assertEqual(lighting.restore_state()["result"], "restored")
        self.assertIsNone(ledger_mod.get().pending(), "恢复成功后必须清掉 pending")


if __name__ == "__main__":
    unittest.main()
