#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音乐可视化回归测试（不需要设备/音频）：官方渲染器逐键颜色 + status 颜色快照。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
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
        for mode in sorted(music.IMPLEMENTED_MODES):
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
        self.assertEqual(music.MusicEngine(100).mode, 13, "屏光联动（100）仍回落 13")

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
            st = player.update(mode=100)  # 100 = 屏光联动（官方交给插件，主机侧无渲染器）→ 回落 13
        finally:
            player._thread.join(timeout=1)
            player._thread = None
        self.assertEqual(st["requestedMode"], 100)
        self.assertEqual(st["mode"], 13)


#: 本轮补齐的官方渲染器（13/14/17/1/4 由上面的用例覆盖）
NEW_MODES = (15, 16, 18, 19, 20, 21, 22)
#: 官方背景模式全表（0 无背景、1/2 横条、4 径向、5 旋转、6..11 纯色）
BACKMODES = (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11)


def _lit_cells(engine: "music.MusicEngine") -> set:
    """按引擎当前状态再渲染一帧（st 用副本，不推进引擎本身），返回亮起的 (row, col)。"""
    grid = music._render_frame(engine.lay, dict(engine.st), engine.mode)
    return {(r, c) for r, row in enumerate(grid)
            for c, rgb in enumerate(row) if sum(rgb) > 0}


class TestNewModeRenderers(unittest.TestCase):
    """模式 15/16/18/19/20/21/22：逐模式喂 400~900 振幅跑 45 tick，校验载荷/颜色/结构。"""

    def _drive(self, mode: int, ticks: int = 45):
        engine = music.MusicEngine(mode, amplitude_ui=75)
        payload = b""
        for i in range(ticks):
            payload = engine.tick(400 + (i * 53) % 500)
        return engine, payload

    def _assert_common(self, engine, payload: bytes, mode: int) -> None:
        self.assertEqual(len(payload), 87 * 4, f"mode {mode} 载荷长度")
        self.assertEqual(len(engine.last_colors), 87, f"mode {mode} 逐键颜色数量")
        self.assertTrue(any(sum(rgb) > 30 for rgb in engine.last_colors.values()),
                        f"mode {mode} 应该有非黑颜色")

    def test_mode_15_dormant_volcano(self):
        engine, payload = self._drive(15)
        self._assert_common(engine, payload, 15)
        lit = _lit_cells(engine)
        bottom = [c for (r, c) in lit if r == 5]
        self.assertEqual(len(bottom), 17, "火山底行应由左/中/右三塔拼成整行")

    def test_mode_16_light_arrow(self):
        engine, payload = self._drive(16)
        self._assert_common(engine, payload, 16)
        lit = _lit_cells(engine)
        for row in (2, 3):
            self.assertGreaterEqual(len([c for (r, c) in lit if r == row]), 12,
                                    f"中心行 {row} 应有右侧光条")

    def test_mode_18_light_cocoon(self):
        engine, payload = self._drive(18)
        self._assert_common(engine, payload, 18)
        lit = _lit_cells(engine)
        self.assertGreaterEqual(len([c for (r, c) in lit if r == 0]), 10, "光茧顶边应点亮")
        # 官方：右列点亮 ceil(F * smoothAmp) 行
        expected = int(math.ceil(engine.lay["F"] * min(engine.st["smoothAmp"], 1.0)))
        self.assertEqual(len([r for (r, c) in lit if c == 16]), expected, "光茧右列高度")

    def test_mode_19_tuning_fork(self):
        engine, payload = self._drive(19)
        self._assert_common(engine, payload, 19)
        lit = _lit_cells(engine)
        self.assertTrue(4 <= len(lit) <= 80, f"音叉触须不该铺满全屏（lit={len(lit)}）")

    def test_mode_20_curvature_track(self):
        engine, payload = self._drive(20)
        self._assert_common(engine, payload, 20)
        lit = _lit_cells(engine)
        self.assertTrue(any(c >= 12 for (_r, c) in lit), "曲率轨迹应从右侧进入")

    def test_mode_21_row_wave(self):
        engine, payload = self._drive(21)
        self._assert_common(engine, payload, 21)
        lit = _lit_cells(engine)
        self.assertTrue(any(c == 0 for (_r, c) in lit), "行波柱应从第 0 列起")
        self.assertGreater(len({r for (r, _c) in lit}), 1, "应有多行不同长度")

    def test_mode_22_dual_heart(self):
        engine, payload = self._drive(22, ticks=60)
        self._assert_common(engine, payload, 22)
        lit = _lit_cells(engine)
        self.assertIn((2, 4), lit, "左心心尖 (col 4, row 2) 应点亮")
        self.assertIn((2, 12), lit, "右心心尖 (col 12, row 2) 应点亮")

    def test_new_modes_silent_do_not_raise(self):
        for mode in NEW_MODES:
            engine = music.MusicEngine(mode)
            payload = b""
            for _ in range(20):
                payload = engine.tick(0)
            self.assertEqual(len(payload), 87 * 4, f"mode {mode} 静音载荷")
            self.assertEqual(len(engine.last_colors), 87, f"mode {mode} 静音键数")

    def test_new_modes_all_backgrounds_do_not_raise(self):
        for mode in NEW_MODES:
            engine = music.MusicEngine(mode, amplitude_ui=60)
            for backmode in BACKMODES:
                engine.set_backmode(backmode, 55)
                payload = b""
                for _ in range(3):
                    payload = engine.tick(700)
                self.assertEqual(len(payload), 87 * 4,
                                 f"mode {mode} + backmode {backmode} 载荷")
                self.assertEqual(len(engine.last_colors), 87,
                                 f"mode {mode} + backmode {backmode} 键数")
                self.assertTrue(any(sum(rgb) > 0 for rgb in engine.last_colors.values()),
                                f"mode {mode} + backmode {backmode} 不应全黑")

    def test_implemented_modes_exact(self):
        self.assertEqual(set(music.IMPLEMENTED_MODES),
                         {1, 4, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22},
                         "IMPLEMENTED_MODES 应含全部 12 个已移植官方模式")
        self.assertEqual(set(music.MODE_NAMES), set(music.IMPLEMENTED_MODES),
                         "MODE_NAMES 应覆盖且只覆盖已移植模式")


if __name__ == "__main__":
    unittest.main(verbosity=2)
