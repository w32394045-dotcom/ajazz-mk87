#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音乐可视化回归测试（不需要设备/音频）：官方渲染器逐键颜色 + status 颜色快照。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import music  # noqa: E402


class _FakeDevice:
    """MusicPlayer 只用到 transport / add_listener，不真正打开设备。"""

    transport = "usb"

    def add_listener(self, *args, **kwargs) -> None:  # noqa: D401
        pass


class TestMusicEngineColors(unittest.TestCase):
    def test_all_ported_modes_emit_colors(self):
        for mode in (13, 14, 17, 4, 1):
            engine = music.MusicEngine(mode)
            payload = b""
            for _ in range(30):
                payload = engine.tick(600)
            self.assertEqual(len(payload), 87 * 4, f"mode {mode} 载荷长度")
            self.assertEqual(len(engine.last_colors), 87, f"mode {mode} 逐键颜色数量")
            self.assertTrue(any(sum(rgb) > 20 for rgb in engine.last_colors.values()),
                            f"mode {mode} 应该有非黑颜色")

    def test_unknown_mode_falls_back_to_13(self):
        engine = music.MusicEngine(99)
        self.assertEqual(engine.mode, 13)

    def test_silence_diminishes(self):
        engine = music.MusicEngine(13)
        for _ in range(30):
            engine.tick(800)
        playing = sum(sum(rgb) for rgb in engine.last_colors.values())
        self.assertGreater(playing, 0)
        for _ in range(20):  # 官方 C=5：连续 5 tick 静音后振幅归零，但拖尾会慢慢衰减
            engine.tick(0)
        silent = sum(sum(rgb) for rgb in engine.last_colors.values())
        self.assertLess(silent, playing * 0.5)


class TestMusicPlayerSnapshot(unittest.TestCase):
    def test_status_exposes_colors_while_running(self):
        player = music.MusicPlayer(_FakeDevice())
        player.last_colors = {4: (255, 0, 0), 87: (0, 128, 255)}
        player.frames = 7
        self.assertEqual(player.status()["colors"], {}, "未运行时不应暴露颜色")
        # 用一个瞬时线程模拟 running=True
        player._thread = threading.Thread(target=lambda: time.sleep(0.3), daemon=True)
        player._thread.start()
        try:
            st = player.status()
            self.assertEqual(st["colors"], {"4": [255, 0, 0], "87": [0, 128, 255]})
            self.assertEqual(st["mode"], 13)
        finally:
            player._thread.join(timeout=1)
            player._thread = None


class TestMusicHotUpdate(unittest.TestCase):
    """运行中热切换：显示模式 / 背景模式 / 背景亮度 / 振幅 / 帧率。"""

    def test_engine_background_mode(self):
        engine = music.MusicEngine(13, backmode=7, backmode_brightness=50)
        for _ in range(10):
            engine.tick(0)
        self.assertTrue(any(rgb[0] > 20 and rgb[1] < 20 for rgb in engine.last_colors.values()),
                        "红色背景应点亮按键")

    def test_update_while_running(self):
        player = music.MusicPlayer(_FakeDevice())
        player._engine = music.MusicEngine(13)
        player._thread = threading.Thread(target=lambda: time.sleep(0.3), daemon=True)
        player._thread.start()
        try:
            st = player.update(mode=4, backmode=7, backmode_brightness=50,
                               amplitude=80, fps=30)
        finally:
            player._thread.join(timeout=1)
            player._thread = None
        self.assertEqual(player.mode, 4)
        self.assertEqual(player.requested_mode, 4)
        self.assertEqual(player.backmode, 7)
        self.assertEqual(player.backmode_brightness, 50)
        self.assertEqual(player.amplitude_ui, 80)
        self.assertEqual(player.fps, 30)
        self.assertEqual(st["mode"], 4)
        self.assertEqual(st["requestedMode"], 4)
        self.assertEqual(st["backmode"], 7)
        self.assertEqual(st["backmodeBrightness"], 50)
        self.assertEqual(st["amplitude"], 80)
        self.assertIn("implementedModes", st)

    def test_update_requires_running(self):
        player = music.MusicPlayer(_FakeDevice())
        with self.assertRaises(music.MK87Error):
            player.update(mode=14)

    def test_update_unported_mode_falls_back(self):
        player = music.MusicPlayer(_FakeDevice())
        player._engine = music.MusicEngine(13)
        player._thread = threading.Thread(target=lambda: time.sleep(0.3), daemon=True)
        player._thread.start()
        try:
            st = player.update(mode=15)  # 官方模式 15，渲染器未移植 → 回落 13
        finally:
            player._thread.join(timeout=1)
            player._thread = None
        self.assertEqual(st["requestedMode"], 15)
        self.assertEqual(st["mode"], 13)


if __name__ == "__main__":
    unittest.main(verbosity=2)
