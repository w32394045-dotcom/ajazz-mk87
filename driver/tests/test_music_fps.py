#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原生帧率（15/20/30/60/66）回归：发送策略、节奏、实测 fps、动画时间归一。

全部离线：假时钟 / 假发送器 / 假采集，不打开音频、不碰真键盘。
真机 USB 时序（66fps 带宽 / ACK 延迟 / 固件缓冲）由 Lead 上机验证。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import threading
import time
import unittest
from collections import deque
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import lighting, music  # noqa: E402
from mk87lib import ledger as ledger_mod  # noqa: E402

#: 默认档快照矩阵里用的喂料（与 test_music_preview.py 完全一致）
SNAPSHOT_AMPS = (0, 0, 0, 0, 0, 0, 300, 700, 1000, 520, 0, 0, 0, 0, 0, 820)
SNAPSHOT_PATH = os.path.join(HERE, "fixtures", "music_default_snapshot.json")


def _snapshot_bands(tick: int):
    return [((tick * 7 + i * 3) % 11) / 10.0 for i in range(32)]


def _snapshot_digest(mode: int, backmode: int = 0, dt_scale=None) -> str:
    """跑固定 tick 序列，返回全部 348B 载荷拼接后的 SHA-256（与快照生成逻辑一致）。"""
    engine = music.MusicEngine(mode, amplitude_ui=60, backmode=backmode,
                               backmode_brightness=55)
    random.seed(0x5EED)  # 模式 19 用 random.random()；固定种子才能逐字节复现
    kwargs = {} if dt_scale is None else {"dt_scale": dt_scale}
    buf = bytearray()
    for tick, amp in enumerate(SNAPSHOT_AMPS):
        payload = engine.tick(amp, _snapshot_bands(tick), **kwargs)
        assert len(payload) == 87 * 4
        buf.extend(payload)
    return hashlib.sha256(bytes(buf)).hexdigest()


class _FakeDevice:
    """MusicPlayer 只用到 transport，不真正打开设备。"""

    transport = "usb"

    def add_listener(self, *args, **kwargs) -> None:  # noqa: D401
        pass


# ======================================================================
# 1) 帧率归一 / 热更新
# ======================================================================
class TestFpsClamp(unittest.TestCase):
    def test_fps_choices_pass_through(self):
        self.assertEqual(music.FPS_CHOICES, (15, 20, 30, 60, 66))
        self.assertEqual(music.DEFAULT_FPS, 20)
        for fps in music.FPS_CHOICES:
            self.assertEqual(music._clamp_fps(fps), fps, f"{fps} 应原样保留")

    def test_fps_clamp_accepts_range_and_strings(self):
        self.assertEqual(music._clamp_fps(5), 5, "下限")
        self.assertEqual(music._clamp_fps(65), 65, "上限内任意整数兼容")
        self.assertEqual(music._clamp_fps("66"), 66, "字符串数字可解析")
        self.assertEqual(music._clamp_fps(60.0), 60, "浮点整数可解析")
        self.assertEqual(music._clamp_fps(0), 5, "越界钳到下限")
        self.assertEqual(music._clamp_fps(100), 66, "越界钳到上限")
        self.assertEqual(music._clamp_fps(-3), 5)

    def test_fps_invalid_falls_back_to_20(self):
        for bad in (None, "", "abc", [], {}, float("nan"), float("inf")):
            self.assertEqual(music._clamp_fps(bad), 20, f"无法解析的 {bad!r} 应回落 20")

    def test_update_stores_target_fps_without_restart(self):
        player = music.MusicPlayer(_FakeDevice())
        player._engine = music.MusicEngine(13)
        player._thread = threading.Thread(target=lambda: time.sleep(0.5), daemon=True)
        player._thread.start()
        try:
            st = player.update(fps=66)
            self.assertEqual(player.fps, 66)
            self.assertEqual(st["targetFps"], 66)
            self.assertIsNone(st["fps"], "刚换档/没有实测样本时 fps 必须是 None，不能拿配置值充数")
            st = player.update(fps=100)  # 越界 → 钳到上限 66
            self.assertEqual(player.fps, 66)
            self.assertEqual(st["targetFps"], 66)
            st = player.update(fps="abc")  # 无法解析 → 回落 20
            self.assertEqual(player.fps, 20)
            self.assertEqual(st["targetFps"], 20)
        finally:
            player._thread.join(timeout=1)
            player._thread = None

    def test_start_applies_fps_clamp(self):
        player = music.MusicPlayer(_FakeDevice())

        def _idle_loop(self_):
            self_._ready.set()
            while not self_._stop.is_set():
                time.sleep(0.005)

        with mock.patch.object(music.MusicPlayer, "_loop", _idle_loop):
            try:
                st = player.start(fps=66)
                self.assertEqual(player.fps, 66)
                self.assertEqual(st["targetFps"], 66)
                self.assertIsNone(st["fps"], "未出帧时 status.fps 为 None")
                self.assertEqual(st["sendMode"], "burst", "66fps 启动即 burst 策略")
                player.stop()
                player.start(fps=999)  # 越界 → 钳到 66
                self.assertEqual(player.fps, 66)
                player.stop()
                player.start(fps="nope")  # 无法解析 → 20
                self.assertEqual(player.fps, 20, "start 的非法帧率回落 20")
            finally:
                player.stop()


# ======================================================================
# 2) 实测 fps（滚动窗口 / status 契约）
# ======================================================================
class TestMeasuredFps(unittest.TestCase):
    def test_measured_fps_20fps(self):
        player = music.MusicPlayer(_FakeDevice())
        for i in range(40):
            player._record_frame_time(i / 20.0)
        self.assertAlmostEqual(player.measured_fps, 20.0, delta=0.1)

    def test_measured_fps_66fps(self):
        player = music.MusicPlayer(_FakeDevice())
        for i in range(40):
            player._record_frame_time(i / 66.0)
        self.assertAlmostEqual(player.measured_fps, 66.0, delta=0.3)

    def test_measured_fps_needs_enough_samples(self):
        player = music.MusicPlayer(_FakeDevice())
        self.assertIsNone(player.measured_fps, "没有样本 → None")
        player._record_frame_time(10.0)
        self.assertIsNone(player.measured_fps, "一个样本算不出帧率")
        player._record_frame_time(10.1)
        self.assertIsNone(player.measured_fps, "跨度 <250ms 不显示（抖动太大）")
        player._record_frame_time(10.3)
        self.assertAlmostEqual(player.measured_fps, 6.7, delta=0.1,
                               msg="2 个间隔 / 0.3s")

    def test_measured_fps_window_rolls(self):
        player = music.MusicPlayer(_FakeDevice())
        for i in range(400):  # 20fps × 20s
            player._record_frame_time(i * 0.05)
        self.assertLessEqual(len(player._frame_ts), 43, "只保留最近 ~2s 的样本")
        self.assertAlmostEqual(player.measured_fps, 20.0, delta=0.1)
        player._reset_measured_fps()
        self.assertIsNone(player.measured_fps)

    def test_status_fps_is_measured_not_target(self):
        player = music.MusicPlayer(_FakeDevice())
        st = player.status()
        self.assertIsNone(st["fps"], "未运行 → None")
        self.assertEqual(st["targetFps"], 20)
        self.assertEqual(st["sendMode"], "ack")

        player.fps = 66
        player._thread = threading.Thread(target=lambda: time.sleep(0.5), daemon=True)
        player._thread.start()
        try:
            for i in range(30):
                player._record_frame_time(i / 66.0)
            st = player.status()
            self.assertIsInstance(st["fps"], float, "运行中 fps 是实测浮点值")
            self.assertAlmostEqual(st["fps"], 66.0, delta=0.5)
            self.assertEqual(st["targetFps"], 66, "targetFps 才是配置值")
        finally:
            player._thread.join(timeout=1)
            player._thread = None


# ======================================================================
# 3) 动画时间归一（20fps 与 66fps 同一动画进度）
# ======================================================================
class TestAnimationTimeNormalization(unittest.TestCase):
    def test_dt_scale(self):
        self.assertAlmostEqual(music._dt_scale(1 / 20.0), 1.0, places=12)
        self.assertAlmostEqual(music._dt_scale(1 / 66.0), 20.0 / 66.0, places=12)
        self.assertAlmostEqual(music._dt_scale(1 / 60.0), 20.0 / 60.0, places=12)
        self.assertEqual(music._dt_scale(0.0), music.DT_SCALE_MIN, "卡死下限")
        self.assertEqual(music._dt_scale(10.0), music.DT_SCALE_MAX, "挂起上限 3 个基准 tick")
        self.assertEqual(music._dt_scale(None), 1.0, "缺省 = 标准 20fps tick")

    def test_mode4_hue_rate_normalized(self):
        """mode 4 色相：0.04 圈/基准 tick → 0.8 圈/s ≈ 288°/s（采样 ~275°/s 同量级）。"""
        e20 = music.MusicEngine(4)
        for _ in range(20):  # 1 秒 @20fps
            e20.tick(800)
        e66 = music.MusicEngine(4)
        for _ in range(66):  # 1 秒 @66fps
            e66.tick(800, dt_scale=20.0 / 66.0)
        self.assertAlmostEqual(e20.st["mode4Hue"], 0.8, places=9)
        self.assertAlmostEqual(e66.st["mode4Hue"], e20.st["mode4Hue"], places=9,
                               msg="66fps 跑 1s 与 20fps 跑 1s 的色相进度必须一致")
        deg_per_s = e20.st["mode4Hue"] * 360.0
        self.assertTrue(270.0 <= deg_per_s <= 300.0, f"色相转速 {deg_per_s:.0f}°/s 偏离预期")

    def test_mode5_hue_cycle_normalized(self):
        e20 = music.MusicEngine(5)
        e66 = music.MusicEngine(5)
        for _ in range(20):
            e20.tick(700)
        for _ in range(66):
            e66.tick(700, dt_scale=20.0 / 66.0)
        self.assertAlmostEqual(e20.st["huePhase"], 0.2, places=9, msg="20fps 1s = 0.2 圈")
        self.assertAlmostEqual(e66.st["huePhase"], e20.st["huePhase"], places=9)
        # 5 秒一圈（100 个基准 tick）
        for _ in range(80):
            e20.tick(700)
        self.assertAlmostEqual(e20.st["huePhase"], 0.0, places=9, msg="5s 走完整圈")

    def test_mode13_ring_phase_normalized(self):
        e20 = music.MusicEngine(13, amplitude_ui=80)
        e66 = music.MusicEngine(13, amplitude_ui=80)
        for _ in range(20):
            e20.tick(700)
        for _ in range(66):
            e66.tick(700, dt_scale=20.0 / 66.0)
        self.assertAlmostEqual(e20.st["phase"], 0.1, places=9, msg="环扩散 0.005/tick")
        self.assertAlmostEqual(e66.st["phase"], e20.st["phase"], places=9)
        self.assertAlmostEqual(e66.st["huePhase"], e20.st["huePhase"], places=9)
        self.assertAlmostEqual(e66.st["smoothValue"], e20.st["smoothValue"], delta=1e-6,
                               msg="环数平滑按时间归一")

    def test_silence_window_normalized(self):
        """官方 C=5（250ms）静音归零：66fps 下是 ~16.5 帧，不是 5 帧。"""
        e20 = music.MusicEngine(13)
        e20.tick(800)
        for _ in range(4):
            e20.tick(0)
        self.assertGreater(e20.st["amp"], 0.7, "20fps 静音 4 tick 还不该归零")
        e20.tick(0)
        self.assertEqual(e20.st["amp"], 0.0, "20fps 第 5 tick 归零（官方 C=5）")

        e66 = music.MusicEngine(13)
        e66.tick(800)
        for _ in range(16):  # 16 × 0.303 ≈ 4.85 个基准 tick < 5
            e66.tick(0, dt_scale=20.0 / 66.0)
        self.assertGreater(e66.st["amp"], 0.7, "66fps 静音 16 帧（~242ms）还不该归零")
        e66.tick(0, dt_scale=20.0 / 66.0)  # 17 × 0.303 ≈ 5.15
        self.assertEqual(e66.st["amp"], 0.0, "跨过 250ms 后归零")

    def test_volcano_climb_normalized(self):
        """mode 15 火山每基准 tick 爬 1 层：66fps 单帧不能爬 3 层。"""
        engine = music.MusicEngine(15, amplitude_ui=50)
        engine.tick(800)
        self.assertEqual(engine.st["volcanoHeight"], 0, "第一帧只设定目标，不爬升")
        for _ in range(3):
            engine.tick(800, dt_scale=20.0 / 66.0)
        self.assertLessEqual(engine.st["volcanoHeight"], 1,
                             "3 帧 66fps ≈ 0.9 个基准 tick，最多爬 1 层")
        e20 = music.MusicEngine(15, amplitude_ui=50)
        e66 = music.MusicEngine(15, amplitude_ui=50)
        for _ in range(20):
            e20.tick(800)
        for _ in range(66):
            e66.tick(800, dt_scale=20.0 / 66.0)
        self.assertEqual(e20.st["volcanoHeight"], e66.st["volcanoHeight"],
                         "1 秒后 20fps / 66fps 的火山高度应一致")

    def test_spectrum_bars_are_per_frame_not_scaled(self):
        """频谱柱高是「当帧量」：dt_scale 只影响色相，不影响哪些格子被点亮。"""
        bands = [0.0] * 32
        bands[12] = 1.0

        def _lit(dt_scale):
            engine = music.MusicEngine(4, amplitude_ui=100)
            engine.tick(800, bands, dt_scale=dt_scale)
            grid = music._render_frame(engine.lay, dict(engine.st), 4)
            return {(r, c) for r, row in enumerate(grid)
                    for c, rgb in enumerate(row) if sum(rgb) > 0}

        self.assertEqual(_lit(1.0), _lit(3.0), "柱高不随 dt 缩放")
        self.assertTrue(_lit(1.0), "应有柱子被点亮")

    def test_agc_composition_matches_one_second(self):
        """AGC attack/decay：20 步 dt=1 与 66 步 dt=20/66 的终值一致。"""
        one, other = 0.01, 0.01
        for _ in range(20):
            one = music._agc(one, 0.8, music._AMP_ATTACK, 1.0)
        for _ in range(66):
            other = music._agc(other, 0.8, music._AMP_ATTACK, 20.0 / 66.0)
        self.assertAlmostEqual(other, one, places=12)
        self.assertEqual(music._agc(0.01, 1.0, 0.3, 1.0), 0.01 * 0.7 + 1.0 * 0.3,
                         "dt=1 保持旧算术顺序")

    def test_analyzer_20fps_matches_legacy_agc(self):
        """默认调用（dt=1.0）必须保持改动前的 z 递推逐位一致。"""
        import numpy as np
        samples = np.zeros(2048, dtype=np.float32)
        samples[:512] = 0.5
        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples * samples)))
        raw = 0.6 * peak + 0.4 * rms
        analyzer = music.Analyzer()
        z = music._AMP_FLOOR
        for _ in range(10):
            analyzer.analyze(samples)
            z = (z * 0.7 + raw * 0.3) if raw > z else (z * 0.992 + raw * 0.008)
            z = max(z, music._AMP_FLOOR)
        self.assertEqual(analyzer.z, z, "20fps 的 AGC 递推必须与改动前逐位一致")

    def test_analyzer_agc_time_normalized(self):
        """同一信号跑 1 秒：66fps 的 AGC 增益/32 段频谱与 20fps 一致。"""
        import numpy as np
        samples = np.zeros(2048, dtype=np.float32)
        samples[:600] = np.linspace(0.0, 0.9, 600, dtype=np.float32)
        a20 = music.Analyzer()
        a66 = music.Analyzer()
        for _ in range(20):
            info20 = a20.analyze(samples)
        for _ in range(66):
            info66 = a66.analyze(samples, dt_scale=20.0 / 66.0)
        self.assertAlmostEqual(a66.z, a20.z, delta=abs(a20.z) * 1e-6 + 1e-9,
                               msg="1s 后 20fps / 66fps 的 AGC 增益应一致")
        for i, (b20, b66) in enumerate(zip(a20.bands32, a66.bands32)):
            self.assertAlmostEqual(b66, b20, delta=1e-6, msg=f"bands32[{i}]")
        self.assertLessEqual(abs(info66["amp1000"] - info20["amp1000"]), 2,
                             "同一信号同一增益 → 总振幅一致（允许整数舍入）")

    def test_default_dt1_payload_identical(self):
        """显式 dt_scale=1.0 必须与旧调用（默认参数）逐字节一致。"""
        for mode in sorted(music.IMPLEMENTED_MODES):
            self.assertEqual(_snapshot_digest(mode, 3, dt_scale=1.0),
                             _snapshot_digest(mode, 3, dt_scale=None),
                             f"mode {mode}: dt_scale=1.0 与默认调用必须一致")

    @unittest.skipUnless(
        sys.platform == "win32",
        "默认档快照在 Windows 上生成（不同 libm 的 sin/cos/atan2 末位可能不同）")
    def test_default_snapshot_not_regressed(self):
        """改动前快照（全部 20 个模式 × backmode=0）必须继续逐字节一致。"""
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            snapshot = json.load(f)
        for mode in sorted(music.IMPLEMENTED_MODES):
            want = snapshot["cases"][f"{mode}/0"]
            self.assertEqual(_snapshot_digest(mode, 0), want,
                             f"mode {mode} 默认档快照回归")


# ======================================================================
# 4) 发送策略分档 + FrameSender burst/drain（假通道，不碰 USB）
# ======================================================================
class _FakeChannel:
    """模拟原生通道：写事件和读事件顺序可观测，ACK 由 pending 队列提供。"""

    body_len = 64

    def __init__(self, acks: int = 0):
        self.pending = deque()
        self.events = []
        self.writes = []
        self.reads = 0
        self.read_none = 0
        self.queue_acks(acks)

    def queue_acks(self, count: int) -> None:
        for _ in range(int(count)):
            self.pending.append(b"\x55\x00")

    def write(self, data):
        self.events.append("w")
        self.writes.append(bytes(data))

    def read_normalized(self, timeout=0.1):
        self.events.append("r")
        self.reads += 1
        if not self.pending:
            self.read_none += 1
            return None
        return self.pending.popleft()

    def drain(self, duration=0.02):
        self.pending.clear()

    def close(self):
        pass


class TestSendStrategy(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(music._send_strategy(15), (True, 0))
        self.assertEqual(music._send_strategy(20), (True, 0))
        self.assertEqual(music._send_strategy(30), (True, 0), "≤30fps 逐包 ACK")
        self.assertEqual(music._send_strategy(60), (False, 0),
                         "≥60fps 连写 7 包、回包交给 ACK 清道夫异步读")
        self.assertEqual(music._send_strategy(66), (False, 0))

    def test_timing_budget_from_real_measurements(self):
        """静态核算（真机数据 docs/spec-lighting.md §4.3）：

        7 包逐包 ACK：平均 15.5ms/帧、最大 20.06ms/帧 → 66fps 的 15.15ms 预算不够；
        30fps 预算 33.3ms > 最大 20.06ms → 逐包 ACK 仍安全。
        包率：87 键 = 7 包/帧，66fps → 462 包/s，仍低于官方 102 键 8 包/帧 × 66fps
        的 530.5 包/s（官方实测可持续）。
        """
        budget_66 = 1000.0 / 66.0
        budget_30 = 1000.0 / 30.0
        avg_ack_frame_ms = 15.5      # 真机：7 包逐包 ACK 平均
        max_ack_frame_ms = 20.06     # 真机：单帧最大
        official_packets_per_s = 530.5
        self.assertLess(budget_66, avg_ack_frame_ms, "66fps 逐包 ACK 不可行 → 必须 burst")
        self.assertGreater(budget_30, max_ack_frame_ms, "30fps 逐包 ACK 有余量")
        self.assertAlmostEqual(budget_66, 15.1515, places=3)
        self.assertLessEqual(7 * 66, official_packets_per_s, "包率不超过官方实测")

    def test_frame_sender_packet_count(self):
        sender, _ch = self._sender()
        self.assertEqual(sender.frame_packets(self.payload()), 7)

    @staticmethod
    def payload() -> bytes:
        return b"\x11" * (87 * 4)

    def _sender(self, acks: int = 0):
        ch = _FakeChannel()
        ch.queue_acks(acks)
        return lighting.FrameSender(None, channel=ch), ch

    def test_burst_writes_then_drains(self):
        sender, ch = self._sender(acks=7)
        acks = sender.send(self.payload(), 3, wait_ack=False, drain=7)
        self.assertEqual(acks, 7, "帧末 drain 应读回 7 个 ACK")
        self.assertEqual(len(ch.writes), 7)
        self.assertEqual(ch.events, ["w"] * 7 + ["r"] * 7,
                         "先连续写 7 包，再统一读走回包（不在包间等 ACK）")
        self.assertEqual(sender._ack_backlog, 0)

    def test_per_packet_ack_path_preserved(self):
        """20fps 原有行为：写一包立刻等一包 ACK（逐包交替）。"""
        sender, ch = self._sender(acks=7)
        self.assertEqual(sender.send(self.payload(), 0, wait_ack=True), 7)
        self.assertEqual(ch.events, ["w", "r"] * 7)

    def test_drain_backlog_catches_up(self):
        sender, ch = self._sender(acks=6)
        self.assertEqual(sender.send(self.payload(), 0, wait_ack=False, drain=7), 6)
        self.assertEqual(sender._ack_backlog, 1, "少读到的回包记为欠账")
        ch.queue_acks(8)  # 1 个补上 + 本帧 7 个
        self.assertEqual(sender.send(self.payload(), 1, wait_ack=False, drain=7), 8)
        self.assertEqual(sender._ack_backlog, 0)
        self.assertEqual(len(ch.writes), 14, "每帧仍是 7 包")

    def test_read_ack_for_drainer_thread(self):
        sender, ch = self._sender(acks=1)
        self.assertEqual(sender.read_ack(timeout=0.001), b"\x55\x00")


# ======================================================================
# 5) MusicPlayer 主循环（假时钟 / 假采集 / 假发送器）
# ======================================================================
class _FakeClock:
    """单调时钟替身：sleep 推进时间；step>0 时每次取时间也推进（模拟工作耗时）。"""

    def __init__(self, step: float = 0.0):
        self.t = 0.0
        self.step = float(step)

    def __call__(self) -> float:
        self.t += self.step
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += max(0.0, float(seconds))


class _FakeCapture:
    samplerate = 48000

    def __init__(self, device_id=None):
        self.closed = False

    def open(self):
        pass

    def read(self, frames=2048):
        return None  # _FakeAnalyzer 不读样本

    def close(self):
        self.closed = True


class _FakeAnalyzer:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate

    def analyze(self, samples, dt_scale=1.0):
        return {"amp": 0.42, "amp1000": 420,
                "bands": [0.1, 0.2, 0.3], "bands32": [0.5] * 32}


class _FakeSender:
    def __init__(self):
        self.body = 64
        self.strategies = []
        self.frames = 0
        self.acks = 0
        self.closed = False
        self.on_frame = None

    def frame_packets(self, payload):
        return 7

    def send(self, payload, frame_index=0, wait_ack=True,
             ack_timeout=0.006, drain=0):
        self.strategies.append((wait_ack, drain))
        self.frames += 1
        if self.on_frame is not None:
            self.on_frame(self)
        return 7

    def read_ack(self, timeout=0.1):
        time.sleep(0.001)
        return None

    def close(self):
        self.closed = True


class TestMusicPlayerLoop(unittest.TestCase):
    payload = b""

    def _run_loop(self, fps, frames=40, clock=None, on_frame=None):
        player = music.MusicPlayer(_FakeDevice())
        clock = clock or _FakeClock()
        sender = _FakeSender()
        player._clock = clock
        player._sleep = clock.sleep

        def _hook(sender_):
            if on_frame is not None:
                on_frame(player, sender_)
            if sender_.frames >= frames:
                player._stop.set()

        sender.on_frame = _hook
        patches = [
            mock.patch.object(music, "AudioCapture", _FakeCapture),
            mock.patch.object(music, "Analyzer", _FakeAnalyzer),
            mock.patch.object(lighting, "ensure_frame_mode",
                              lambda dev: {"before": b"\x02"}),
            mock.patch.object(lighting, "restore_effect",
                              lambda dev, raw, fallback=None: True),
            # v0.1.8.7：会话收尾改走灯效账本（单测里 no-op，不写真实配置文件）
            mock.patch.object(ledger_mod, "begin_stream",
                              lambda dev, snapshot=None: {"kind": "effect", "mode": 2}),
            mock.patch.object(ledger_mod, "end_stream",
                              lambda dev, snapshot=None, reason="": {
                                  "ok": True, "result": "restored"}),
            mock.patch.object(lighting, "FrameSender", lambda dev: sender),
        ]
        for patch in patches:
            patch.start()
        try:
            player.start(fps=fps)
            player._thread.join(timeout=5.0)
            self.assertFalse(player._thread.is_alive(), "循环应在限制帧数内退出")
        finally:
            player._stop.set()
            if player._thread is not None and player._thread.is_alive():
                player._thread.join(timeout=2.0)
            for patch in reversed(patches):
                patch.stop()
        return player, sender

    def test_loop_20fps_keeps_per_packet_ack(self):
        captured = {}

        def _on_frame(player, sender):
            if sender.frames == 40:
                captured["measured"] = player.measured_fps
                captured["send_mode"] = player.send_mode

        player, sender = self._run_loop(20, 40, on_frame=_on_frame)
        self.assertEqual(sender.frames, 40)
        self.assertEqual(set(sender.strategies), {(True, 0)},
                         "20fps 必须保持逐包 ACK（不退化）")
        self.assertEqual(captured["send_mode"], "ack")
        self.assertAlmostEqual(captured["measured"], 20.0, delta=0.5,
                               msg="假时钟下实测应为目标帧率")
        self.assertAlmostEqual(player._engine.st["dt"], 1.0, places=6,
                               msg="20fps 的动画步长必须是标准 1.0 tick")

    def test_loop_66fps_uses_burst_drainer(self):
        captured = {}

        def _on_frame(player, sender):
            if sender.frames == 40:
                captured["measured"] = player.measured_fps
                captured["send_mode"] = player.send_mode
                captured["late"] = player.status()["timing"]["lateFrames"]
                captured["drainer"] = player._drainer

        player, sender = self._run_loop(66, 40, on_frame=_on_frame)
        self.assertEqual(sender.frames, 40)
        self.assertEqual(set(sender.strategies), {(False, 0)},
                         "66fps 连写 7 包，回包由 ACK 清道夫异步读走")
        self.assertEqual(captured["send_mode"], "burst+drainer")
        self.assertIsNotNone(captured["drainer"], "≥60fps 应启用 ACK 清道夫")
        self.assertAlmostEqual(captured["measured"], 66.0, delta=1.0)
        self.assertEqual(captured["late"], 0, "假时钟精确排期不应有滞后重置")
        self.assertAlmostEqual(player._engine.st["dt"], 20.0 / 66.0, places=3,
                               msg="主循环应按实际帧间隔把 dt_scale 传给引擎")
        self.assertIsNone(player._drainer, "循环退出后清道夫必须停掉")

    def test_loop_hot_fps_update_takes_effect(self):
        def _on_frame(player, sender):
            if sender.frames == 5:
                player.update(fps=66)

        player, sender = self._run_loop(20, 20, on_frame=_on_frame)
        self.assertEqual(player.fps, 66)
        self.assertEqual(sender.strategies[:5], [(True, 0)] * 5,
                         "热更新前仍走逐包 ACK")
        self.assertTrue(all(s == (False, 0) for s in sender.strategies[5:]),
                        f"热更新后应立刻切 burst: {sender.strategies[5:]}")

    def test_loop_lag_does_not_burst(self):
        clock = _FakeClock(step=0.02)  # 每次取时间都推进 20ms > 66fps 的 15.2ms
        player, sender = self._run_loop(66, 10, clock=clock)
        self.assertEqual(sender.frames, 10)
        self.assertGreaterEqual(player.status()["timing"]["lateFrames"], 5,
                                "滞后超过 1 个 period 应重置而不是补发")

    def test_66fps_keeps_drainer_running_and_stops_it(self):
        captured = {}

        def _on_frame(player, sender):
            if sender.frames == 10:
                captured["drainer"] = player._drainer
                captured["send_mode"] = player.send_mode

        player, sender = self._run_loop(66, 20, on_frame=_on_frame)
        self.assertIsNotNone(captured["drainer"], "60fps 以上常驻 ACK 清道夫")
        self.assertEqual(captured["send_mode"], "burst+drainer")
        self.assertIsNone(player._drainer, "循环退出后清道夫必须停掉")

    def test_drainer_failure_falls_back_to_sync_drain(self):
        player = music.MusicPlayer(_FakeDevice())
        player._sender = _FakeSender()  # read_ack 立即返回 None
        with mock.patch.object(music, "AckDrainer", side_effect=RuntimeError("boom")):
            with self.assertLogs("mk87.music", level="WARNING"):
                self.assertFalse(player._ensure_drainer(), "清道夫启动失败应返回 False")
            self.assertTrue(player._drainer_failed)
            self.assertFalse(player._ensure_drainer(), "失败后不反复重试")
        self.assertIsNone(player._drainer)
        self.assertEqual(music.BURST_SYNC_DRAIN, 7, "回退路径仍是 7 包同步 drain")


class TestRealClockPacing(unittest.TestCase):
    """真时钟（不连设备）：验证 Windows 上 20fps / 66fps 的实际排期精度。"""

    def _run(self, fps, frames):
        player = music.MusicPlayer(_FakeDevice())
        sender = _FakeSender()
        captured = {}

        def _hook(sender_):
            if sender_.frames == frames:
                captured["measured"] = player.measured_fps
                captured["late"] = player.status()["timing"]["lateFrames"]
                player._stop.set()

        sender.on_frame = _hook
        patches = [
            mock.patch.object(music, "AudioCapture", _FakeCapture),
            mock.patch.object(music, "Analyzer", _FakeAnalyzer),
            mock.patch.object(lighting, "ensure_frame_mode",
                              lambda dev: {"before": b"\x02"}),
            mock.patch.object(lighting, "restore_effect",
                              lambda dev, raw, fallback=None: True),
            # v0.1.8.7：会话收尾改走灯效账本（单测里 no-op，不写真实配置文件）
            mock.patch.object(ledger_mod, "begin_stream",
                              lambda dev, snapshot=None: {"kind": "effect", "mode": 2}),
            mock.patch.object(ledger_mod, "end_stream",
                              lambda dev, snapshot=None, reason="": {
                                  "ok": True, "result": "restored"}),
            mock.patch.object(lighting, "FrameSender", lambda dev: sender),
        ]
        for patch in patches:
            patch.start()
        try:
            player.start(fps=fps)
            player._thread.join(timeout=10.0)
            self.assertFalse(player._thread.is_alive(), "循环应正常退出")
        finally:
            player._stop.set()
            for patch in reversed(patches):
                patch.stop()
        return captured

    def test_real_clock_20fps_pacing(self):
        captured = self._run(20, 20)  # ~1s
        self.assertAlmostEqual(captured["measured"], 20.0, delta=2.0,
                               msg="20fps 实际排期（当前方案默认档）")
        self.assertEqual(captured["late"], 0)

    def test_real_clock_66fps_pacing(self):
        captured = self._run(66, 40)  # ~0.6s
        self.assertGreater(captured["measured"], 55.0,
                           f"66fps 实际排期偏低: {captured['measured']}")
        self.assertLessEqual(captured["late"], 2,
                             "正常负载下不应频繁滞后重置")


# ======================================================================
# 6) WS / HTTP API 契约（fps=实测值，targetFps=配置值）
# ======================================================================
class _FakeMusicPlayer:
    def __init__(self):
        self.calls = []
        self.device = None
        self.status_value = {"running": False}

    def start(self, **kwargs):
        self.calls.append(("start", kwargs))
        return {"ok": True}

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return dict(self.status_value)

    def status(self):
        return dict(self.status_value)


class TestWsAndApiContract(unittest.TestCase):
    def test_preview_period_capped_at_30fps(self):
        from server import state as server_state
        self.assertAlmostEqual(server_state._music_preview_period(20), 0.05, places=6)
        self.assertAlmostEqual(server_state._music_preview_period(15), 1 / 15.0, places=6)
        self.assertAlmostEqual(server_state._music_preview_period(30), 1 / 30.0, places=6)
        self.assertAlmostEqual(server_state._music_preview_period(66), 1 / 30.0, places=6,
                               msg="66fps 预览事件限速到 30Hz")
        self.assertAlmostEqual(server_state._music_preview_period(5), 0.2, places=6)
        self.assertAlmostEqual(server_state._music_preview_period(None), 0.05, places=6)
        self.assertAlmostEqual(server_state._music_preview_period("abc"), 0.05, places=6)
        self.assertAlmostEqual(server_state._music_preview_period(100), 1 / 30.0, places=6)

    def test_ws_music_frame_uses_measured_fps(self):
        from server import state as server_state
        fake = mock.Mock()
        fake.music.mode = 4
        fake.music.frames = 123
        fake.music.measured_fps = 65.8
        fake.music.last_colors = {4: (1, 2, 3), 87: (9, 8, 7)}
        event = server_state.DeviceManager._music_frame_event(fake)
        self.assertEqual(event["type"], "music_frame")
        self.assertEqual(event["data"]["fps"], 65.8)
        self.assertIsInstance(event["data"]["fps"], float)
        self.assertEqual(event["data"]["frame"], 123)
        self.assertEqual(event["data"]["colors"]["4"], [1, 2, 3])

        fake.music.last_colors = {}
        self.assertIsNone(server_state.DeviceManager._music_frame_event(fake),
                          "还没出帧时不发事件")

    def test_api_status_exposes_measured_fps_and_target(self):
        from server import app as server_app
        fake = _FakeMusicPlayer()
        fake.status_value = {"running": True, "fps": 65.8, "targetFps": 66,
                             "sendMode": "burst", "color": "default"}
        dev = mock.Mock()
        dev.status = mock.Mock(transport="usb")
        with mock.patch.object(server_app.manager, "music", fake), \
                mock.patch.object(server_app.manager, "device", dev):
            st = server_app.api_music_status()
        self.assertEqual(st["fps"], 65.8, "status.fps 必须是实测值")
        self.assertEqual(st["targetFps"], 66, "targetFps 是配置档位")
        self.assertTrue(st["supported"])

    def test_api_forwards_fps_without_coercion(self):
        from server import app as server_app
        fake = _FakeMusicPlayer()
        dev = mock.Mock()
        dev.status = mock.Mock(transport="usb")
        with mock.patch.object(server_app.manager, "music", fake), \
                mock.patch.object(server_app.manager, "device", dev), \
                mock.patch.object(server_app, "_dev", return_value=_FakeDevice()):
            server_app.api_music_start({"mode": 4, "fps": 66})
            server_app.api_music_start({"mode": 4})
            server_app.api_music_start({"mode": 4, "fps": "abc"})
            server_app.api_music_update({"fps": 60})
            server_app.api_music_update({})
        starts = [kw for kind, kw in fake.calls if kind == "start"]
        updates = [kw for kind, kw in fake.calls if kind == "update"]
        self.assertEqual(starts[0]["fps"], 66)
        self.assertEqual(starts[1]["fps"], 20, "缺省帧率 = 20")
        self.assertEqual(starts[2]["fps"], "abc",
                         "非法值原样交给 music._clamp_fps 回落（API 不 500）")
        self.assertEqual(updates[0]["fps"], 60)
        self.assertIsNone(updates[1]["fps"], "update 不带 fps 时保持不变")


if __name__ == "__main__":
    unittest.main(verbosity=2)
