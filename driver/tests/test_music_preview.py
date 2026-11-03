#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音乐可视化回归测试（不需要设备/音频）：官方渲染器逐键颜色 + status 颜色快照。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import threading
import time
import unittest
from unittest import mock

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
                         {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22},
                         "IMPLEMENTED_MODES 应含全部 20 个已移植官方模式")
        self.assertEqual(set(music.MODE_NAMES), set(music.IMPLEMENTED_MODES),
                         "MODE_NAMES 应覆盖且只覆盖已移植模式")


#: 官方 v1 纯色显示模式的采样真值（capture/official_music_colors3.jsonl，
#: backmode=0 / amp=30 / bb=100；6..11 两个文件里颜色 100% 命中，见
#: probe/analyze_official_v1_modes.py 的「调色板校验」列）。
V1_SAMPLED_SOLID = {
    6: (254, 254, 254),   # 白
    7: (254, 0, 0),       # 红
    8: (254, 63, 0),      # 橙（255,64,0 经 (c*255)>>8）
    9: (254, 254, 0),     # 黄
    10: (0, 0, 254),      # 蓝（v1 UI：10 = 蓝色）
    11: (0, 254, 0),      # 绿（v1 UI：11 = 绿色；旧 capture 脚本文案写反了）
}
#: 同一份采样的覆盖率统计 (min, avg, max)，分母是官方 102 键布局
V1_SAMPLED_COVERAGE = {
    6: (0, 3.2, 18), 7: (0, 7.5, 25), 8: (0, 3.2, 22),
    9: (0, 6.0, 22), 10: (0, 6.5, 26), 11: (0, 14.9, 52),
}
V1_BAND_COLORS = {
    # 官方调色板函数在 bb=100 下产出的颜色（6 色横条 / 绿黄红分行）
    1: {(0, 254, 0), (254, 254, 0), (254, 0, 0)},
    2: {(0, 0, 254), (0, 254, 0), (0, 254, 254), (254, 0, 0), (254, 0, 254), (254, 254, 0)},
}


def _drive(mode: int, ticks: int = 40, amplitude_ui: int = 30, backmode: int = 0, bb: int = 100):
    """喂一串「有声音」的振幅，返回 (engine, 每 tick 的点亮键数列表)。"""
    engine = music.MusicEngine(mode, amplitude_ui=amplitude_ui,
                               backmode=backmode, backmode_brightness=bb)
    lits = []
    for i in range(ticks):
        engine.tick(300 + (i * 37) % 500)
        lits.append(sum(1 for rgb in engine.last_colors.values() if sum(rgb) > 0))
    return engine, lits


class TestOfficialV1Renderers(unittest.TestCase):
    """官方 v1 的 1/2/4/5/6/7/8/9/10/11（采样反推：同一套曲率频阶柱状 + 不同调色板）。"""

    def test_v1_mode_lists(self):
        """「官方方案」显示模式 = 官方 v1 的 12 个 + 补回的 9 个隐藏模式（21 项）。"""
        self.assertEqual(music.V1_DISPLAY_MODES,
                         [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10,
                          14, 15, 16, 17, 18, 19, 20, 21, 22, 100],
                         "顺序：官方 v1 12 项 + 14~22 + 100（屏光联动排最后）")
        self.assertEqual(len(music.V1_DISPLAY_MODES), 21)
        self.assertEqual(music.V1_IMPLEMENTED_MODES,
                         [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10,
                          14, 15, 16, 17, 18, 19, 20, 21, 22],
                         "隐藏的 14~22 后端本来就有渲染器；只有 100 未移植")
        self.assertEqual(len(music.V1_IMPLEMENTED_MODES), 20)
        self.assertNotIn(100, music.IMPLEMENTED_MODES)
        self.assertEqual(music.MusicEngine(100).mode, 13, "100 仍回落 13")
        self.assertEqual(sorted(music.IMPLEMENTED_MODES),
                         sorted(music.V1_IMPLEMENTED_MODES),
                         "implementedModes 仍是这 20 个模式号")
        self.assertEqual(set(music.V1_STEP_MODES), {1, 2, 5, 6, 7, 8, 9, 10, 11},
                         "4 已单独实现（频谱柱），不再走 Fe 合成包络")

    def test_v1_names_match_official_config(self):
        self.assertEqual(music.MODE_NAMES[6][0], "白色")
        self.assertEqual(music.MODE_NAMES[7][0], "红色")
        self.assertEqual(music.MODE_NAMES[8][0], "橙色")
        self.assertEqual(music.MODE_NAMES[9][0], "黄色")
        self.assertEqual(music.MODE_NAMES[10][0], "蓝色", "官方 v1：10 = 蓝色")
        self.assertEqual(music.MODE_NAMES[11][0], "绿色", "官方 v1：11 = 绿色")
        self.assertEqual(music.MODE_NAMES[1][0], "绿色/黄色/红色")
        self.assertEqual(music.MODE_NAMES[5][0], "频谱循环")

    def test_solid_modes_color_equals_sampled(self):
        """6..11 每帧只有一个颜色，且等于官方采样主色（容差 0）。"""
        for mode, want in V1_SAMPLED_SOLID.items():
            engine, lits = _drive(mode)
            self.assertEqual(len(engine.last_colors), 87, f"mode {mode} 键数")
            lit_colors = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
            self.assertEqual(lit_colors, {want}, f"mode {mode} 颜色应为采样主色 {want}")
            self.assertGreater(max(lits), 0, f"mode {mode} 应该有点亮")

    def test_solid_modes_coverage_matches_sampled_magnitude(self):
        """覆盖率量级与采样一致：官方 102 键上 0~52，我们 87 键上同样只点亮一部分。"""
        for mode in V1_SAMPLED_SOLID:
            _engine, lits = _drive(mode, ticks=60)
            avg = sum(lits) / len(lits)
            _, s_avg, s_max = V1_SAMPLED_COVERAGE[mode]
            self.assertGreaterEqual(max(lits), 2, f"mode {mode} 应点亮")
            self.assertLess(max(lits), 87, f"mode {mode} 不应铺满全键（采样最大 {s_max}/102）")
            # 采样振幅与我们喂的振幅不同，只校验量级：都在「部分点亮」同一区间
            self.assertGreater(avg, 2, f"mode {mode} 平均点亮过少")
            self.assertLess(avg, 50, f"mode {mode} 平均点亮过多（采样平均 {s_avg}/102）")

    def test_mode1_green_yellow_red_rows(self):
        """1 = 绿黄红分行：同一调色板下 上绿/中黄/下红（采样：row3 黄、row4/5 红）。"""
        grid = music._zeros(6, 17)
        music._fill_row_bands(grid, [(0, 255, 0), (255, 255, 0), (255, 0, 0)], 100)
        self.assertEqual(grid[0][0], (0, 254, 0))
        self.assertEqual(grid[2][0], (254, 254, 0))
        self.assertEqual(grid[5][0], (254, 0, 0))
        engine, _lits = _drive(1)
        lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertTrue(lit, "mode 1 应该有点亮")
        self.assertTrue(lit <= V1_BAND_COLORS[1], f"mode 1 只应有绿黄红三色，实际 {lit}")

    def test_mode2_six_band_colors(self):
        engine, _lits = _drive(2)
        lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertTrue(lit, "mode 2 应该有点亮")
        self.assertTrue(lit <= V1_BAND_COLORS[2], f"mode 2 应只有六色横条的 6 种颜色，实际 {lit}")

    def test_mode5_hue_cycle(self):
        """5 = 频谱循环：每帧整帧单色，色相随时间转完色环（采样逐帧换色、最大通道 255）。"""
        engine = music.MusicEngine(5, amplitude_ui=30)
        seen = []
        for i in range(60):
            engine.tick(300 + (i * 37) % 500)
            lit = [rgb for rgb in engine.last_colors.values() if sum(rgb) > 0]
            if not lit:
                continue
            self.assertEqual(len(set(lit)), 1, "模式 5 每帧应只有一种颜色")
            self.assertEqual(max(lit[0]), 255, "模式 5 是满饱和 HSV（最大通道 255）")
            seen.append(lit[0])
        self.assertGreaterEqual(len(set(seen)), 8, f"模式 5 色相应随时间旋转，只见到 {len(set(seen))} 种")

    def test_mode4_spectrum_bars(self):
        """4「曲率频阶」= 官方 v1 真值：17 列频谱柱（底部对齐），列=频率（左低右高）。

        采样：capture/official_v1_mode4_*.jsonl（probe/capture_official_v1_mode4.py）。
        """
        lay = music.layout()

        def _drive(band_index):
            engine = music.MusicEngine(4, amplitude_ui=100)
            bands = [0.0] * 32
            bands[band_index] = 1.0
            for _ in range(12):
                payload = engine.tick(800, bands)
            self.assertEqual(len(payload), 87 * 4, "mode 4 载荷长度")
            self.assertEqual(len(engine.last_colors), 87, "mode 4 逐键颜色数量")
            grid = music._render_frame(lay, dict(engine.st), 4)
            return {(r, c) for r, row in enumerate(grid)
                    for c, rgb in enumerate(row) if sum(rgb) > 0}

        low = _drive(8)     # 低频段
        high = _drive(27)   # 高频段
        self.assertTrue(low and high, "mode 4 应该有点亮")
        # 底部对齐：每列亮起的行必须是「从第 5 行连续往上」的一段
        for lit in (low, high):
            by_col = {}
            for (r, c) in lit:
                by_col.setdefault(c, []).append(r)
            for c, rows in by_col.items():
                self.assertEqual(sorted(rows), list(range(6 - len(rows), 6)),
                                 f"第 {c} 列不是底部对齐的柱子: {sorted(rows)}")
        # 列=频率：低频的柱子更靠左，高频的柱子更靠右
        self.assertLessEqual(min(c for (_r, c) in low), 2, "低频应点亮最左列")
        self.assertGreaterEqual(max(c for (_r, c) in high), 12, "高频应点亮最右列")
        self.assertGreaterEqual(len({c for (_r, c) in high if c >= 10}), 2,
                                "高频柱应覆盖右侧多列")

    def test_mode4_radial_hue_rotates(self):
        """mode 4 颜色 = 以 (2,8) 为原点的径向色相（满饱和），整块调色板逐 tick 旋转。

        采样：同一格色相每 100ms 前进约 28°；左右半屏相差 180°。
        """
        engine = music.MusicEngine(4, amplitude_ui=100)
        bands = [1.0] * 32       # 全频段（左右半屏都亮，才能比较色相）
        engine.tick(800, bands)
        grid = music._render_frame(engine.lay, dict(engine.st), 4)
        lit = [(c, grid[r][c]) for r in range(6) for c in range(17) if sum(grid[r][c]) > 0]
        self.assertTrue(lit, "应该有点亮")
        for _c, rgb in lit:
            self.assertEqual(max(rgb), 255, "径向色相是满饱和 HSV（最大通道 255）")
        # 左右半屏色相相差约 180°
        def _hue(rgb):
            import colorsys
            h, _s, _v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
            return h * 360.0
        left = [rgb for c, rgb in lit if c <= 6]
        right = [rgb for c, rgb in lit if c >= 10]
        self.assertTrue(left and right)
        d = abs(_hue(left[0]) - _hue(right[0]))
        self.assertTrue(60 <= min(d, 360 - d) <= 300,
                        f"左右半屏应相差约 180°（实测 {d:.0f}°）")
        # 调色板旋转：同一格颜色逐 tick 变化
        col = max(c for (c, _rgb) in lit)
        seen = []
        for _ in range(6):
            engine.tick(800, bands)
            g = music._render_frame(engine.lay, dict(engine.st), 4)
            rgb = g[5][col]
            if sum(rgb) > 0:
                seen.append(_hue(rgb))
        self.assertGreaterEqual(len({round(h) for h in seen}), 4,
                                f"色相应逐帧旋转，只见到 {seen}")

    def test_official_brightness_scaling(self):
        """官方亮度缩放 = (通道 * int(bb*255/100)) >> 8：采样 bb=100/50/20 → FE/7E/32。"""
        self.assertEqual(music._brightness_scale(100), 255)
        self.assertEqual(music._brightness_scale(50), 127)
        self.assertEqual(music._brightness_scale(20), 51)
        self.assertEqual(music._scale_channel(255, 255), 254)
        self.assertEqual(music._scale_channel(255, 127), 126)
        self.assertEqual(music._scale_channel(255, 51), 50)

        expected = {100: 254, 50: 126, 20: 50}
        for bb, want in expected.items():
            engine = music.MusicEngine(6, amplitude_ui=60)
            engine.set_backmode(7, bb)          # 红背景
            for _ in range(3):
                engine.tick(400)
            # 背景铺满全键：取一个「前景柱状之外」的键颜色
            grid = music._render_frame(engine.lay, dict(engine.st), 6)
            bg_cells = {grid[r][c] for r in range(6) for c in range(len(grid[r]))
                        if grid[r][c] != (0, 0, 0)}
            self.assertIn((want, 0, 0), bg_cells, f"bb={bb} 背景红应为 {want:02X}0000")

    def test_v1_modes_silent_do_not_raise(self):
        for mode in music.V1_IMPLEMENTED_MODES:
            engine = music.MusicEngine(mode)
            payload = b""
            for _ in range(20):
                payload = engine.tick(0)
            self.assertEqual(len(payload), 87 * 4, f"mode {mode} 静音载荷")
            self.assertEqual(len(engine.last_colors), 87, f"mode {mode} 静音键数")

    def test_v1_modes_all_backgrounds_do_not_raise(self):
        for mode in music.V1_IMPLEMENTED_MODES:
            engine = music.MusicEngine(mode, amplitude_ui=45)
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

    def test_status_exposes_v1_lists(self):
        """前端「官方方案」下拉用 status.officialModes / officialImplementedModes 标注移植状态。"""
        st = music.MusicPlayer(_FakeDevice()).status()
        self.assertEqual(st["officialModes"],
                         [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10,
                          14, 15, 16, 17, 18, 19, 20, 21, 22, 100])
        self.assertEqual(len(st["officialModes"]), 21)
        self.assertEqual(st["officialImplementedModes"], st["officialModes"][:-1])
        self.assertEqual(len(st["officialImplementedModes"]), 20)
        self.assertNotIn(100, st["officialImplementedModes"])
        self.assertIn(14, st["implementedModes"], "当前方案的 14/15/…/22 仍应保留")
        self.assertEqual(st["amplitude"], 50)
        self.assertEqual(st["backmodeBrightness"], 100)
        self.assertEqual(st["color"], "default", "颜色覆盖缺省为 default")


# ======================================================================
# 官方方案 LED 颜色覆盖（本工具增强，第三个下拉）
# ======================================================================
#: 规格表：id → stops。**必须与前端 web/js/data/music.js 的 OFFICIAL_COLOR_SCHEMES 一致**
#: （后端 music.COLOR_SCHEMES 与前端各存一份，id/色值相同；本测试表是独立副本，
#: 用来交叉校验后端表没写错）。
COLOR_STOPS = {
    "default": (),
    "ice": ("#00E5FF",),
    "violet": ("#B36CFF",),
    "pink": ("#FF2E88",),
    "lime": ("#A8FF3E",),
    "amber": ("#FF6A00",),
    "sakura": ("#FF7AB6", "#B36CFF"),
    "aurora": ("#3EFF9A", "#00E5FF", "#7A5CFF"),
    "sunset": ("#FFC400", "#FF6A00", "#FF2E88"),
    "icefire": ("#00E5FF", "#FEFEFE", "#FF6A00"),
}
COLOR_ORDER = tuple(COLOR_STOPS)
#: 官方 v1 的纯色显示模式（不受颜色覆盖影响）
SOLID_V1_MODES = (6, 7, 8, 9, 10, 11)


def _rgb(hexstr: str):
    """``#RRGGBB`` → (r, g, b)（测试侧独立实现，不复用后端解析）。"""
    s = hexstr.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _scaled(color, scale: int = 255):
    """官方亮度缩放 ``(通道 * 系数) >> 8``（bb=100 → 系数 255）。"""
    return tuple((int(c) * int(scale)) >> 8 for c in color)


def _bounds(stops):
    rgbs = [_rgb(s) for s in stops]
    return tuple((min(c[i] for c in rgbs), max(c[i] for c in rgbs)) for i in range(3))


def _assert_within(test: unittest.TestCase, colors, stops, label: str,
                   tol: int = 2) -> None:
    """断言颜色都在调色板的逐通道范围内。

    线性插值结果必落在 stops 的包围盒里；调色板颜色再经官方亮度缩放
    ``(c*255)>>8`` 后每个通道最多少 2，故保留 tol=2 的容差。
    """
    bounds = _bounds(stops)
    for rgb in colors:
        for ch, (lo, hi) in enumerate(bounds):
            test.assertTrue(lo - tol <= rgb[ch] <= hi,
                            f"{label}: 通道 {ch} 越界 {rgb}（调色板范围 {bounds}）")


#: 默认档逐字节回归快照（由**改动前**的 music.py 生成，见 fixtures/README.md）
SNAPSHOT_PATH = os.path.join(HERE, "fixtures", "music_default_snapshot.json")
#: 固定喂料：前 6 tick 静音（覆盖官方 C=5 归零），随后强弱交替
SNAPSHOT_AMPS = (0, 0, 0, 0, 0, 0, 300, 700, 1000, 520, 0, 0, 0, 0, 0, 820)


def _snapshot_bands(tick: int):
    """固定 32 段频谱（只有模式 4 消费；其余模式忽略），保证快照可复现。"""
    return [((tick * 7 + i * 3) % 11) / 10.0 for i in range(32)]


def music_default_digest(mode: int, backmode: int, color=None) -> str:
    """跑固定 tick 序列，返回全部 348B 载荷拼接后的 SHA-256（默认档一致性证据）。"""
    kwargs = {} if color is None else {"color": color}
    engine = music.MusicEngine(mode, amplitude_ui=60, backmode=backmode,
                               backmode_brightness=55, **kwargs)
    random.seed(0x5EED)  # 模式 19 用 random.random()；固定种子才能逐字节复现
    buf = bytearray()
    for tick, amp in enumerate(SNAPSHOT_AMPS):
        payload = engine.tick(amp, _snapshot_bands(tick))
        assert len(payload) == 87 * 4, f"mode {mode} 载荷长度"
        buf.extend(payload)
    return hashlib.sha256(bytes(buf)).hexdigest()


def snapshot_cases():
    """默认档快照矩阵：全部 20 个官方实现模式 × 全部 11 个背景模式。"""
    for mode in sorted(music.IMPLEMENTED_MODES):
        for backmode in BACKMODES:
            yield mode, backmode


class TestColorDefaultByteIdentical(unittest.TestCase):
    """default 必须走原代码路径：与改动前快照逐字节一致（缺省 / "default" 两种写法）。"""

    @classmethod
    def setUpClass(cls):
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            cls.snapshot = json.load(f)

    def test_snapshot_matrix_is_complete(self):
        saved = {tuple(int(x) for x in key.split("/")) for key in self.snapshot["cases"]}
        self.assertEqual(saved, set(snapshot_cases()),
                         "快照应覆盖全部模式 × 全部背景模式")
        self.assertEqual(self.snapshot["meta"]["mode_count"],
                         len(music.IMPLEMENTED_MODES))
        self.assertEqual(tuple(self.snapshot["meta"]["amps"]), SNAPSHOT_AMPS)

    def test_omitted_and_default_color_are_identical(self):
        """跨平台可跑的强断言：color 缺省与显式 "default" 渲染结果逐字节相同。"""
        for mode, backmode in snapshot_cases():
            self.assertEqual(music_default_digest(mode, backmode, None),
                             music_default_digest(mode, backmode, "default"),
                             f"mode={mode} backmode={backmode}：缺省与 default 必须一致")

    @unittest.skipUnless(
        sys.platform == "win32",
        "默认档快照在 Windows 上生成（不同 libm 的 sin/cos/atan2 末位可能不同）；"
        "跨平台的一致性由 test_omitted_and_default_color_are_identical 覆盖")
    def test_default_matches_pre_change_snapshot(self):
        for key, want in self.snapshot["cases"].items():
            mode, backmode = (int(x) for x in key.split("/"))
            for color in (None, "default"):
                got = music_default_digest(mode, backmode, color)
                self.assertEqual(
                    got, want,
                    f"mode={mode} backmode={backmode} color={color!r} 与改动前快照不一致")


class TestColorSchemes(unittest.TestCase):
    def test_color_table_matches_spec(self):
        self.assertEqual(music.COLOR_IDS, COLOR_ORDER,
                         "后端颜色表 id 必须与前端一致（顺序也一致）")
        self.assertEqual(music.DEFAULT_COLOR, "default")
        self.assertEqual(music.COLOR_OVERLAY_MODES,
                         frozenset({1, 2, 4, 5, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}),
                         "覆盖作用于全部动态多色模式 1/2/4/5/13 + 14~22")
        for cid in COLOR_ORDER:
            if cid == "default":
                continue
            self.assertEqual(music.Palette(cid).stops, COLOR_STOPS[cid],
                             f"{cid} 的 stops 与规格表不一致")
        self.assertIsNone(music.palette_for("default"), "default = 不覆盖（无调色板对象）")
        with self.assertRaises(ValueError):
            music.Palette("default")

    def test_palette_sampling(self):
        # 单色 id：任意位置输出恒定
        for cid in ("ice", "violet", "pink", "lime", "amber"):
            pal = music.Palette(cid)
            want = _rgb(COLOR_STOPS[cid][0])
            for t in (0.0, 0.13, 0.5, 0.87, 1.0):
                self.assertEqual(pal.at(t), want, f"{cid} 单色应恒定")
        # 2 段渐变：#FF7AB6 → #B36CFF，中点 = 各通道均值（.5 向上取整）
        sakura = music.Palette("sakura")
        self.assertEqual(sakura.at(0.0), _rgb("#FF7AB6"))
        self.assertEqual(sakura.at(1.0), _rgb("#B36CFF"))
        self.assertEqual(sakura.at(0.5), (217, 115, 219))
        # 3 段渐变：中点正好落在中间 stop；1/4 处是前两段的中点
        aurora = music.Palette("aurora")
        self.assertEqual(aurora.at(0.0), _rgb("#3EFF9A"))
        self.assertEqual(aurora.at(0.5), _rgb("#00E5FF"))
        self.assertEqual(aurora.at(1.0), _rgb("#7A5CFF"))
        self.assertEqual(aurora.at(0.25), (31, 242, 205))
        # 越界 t 收敛到端点
        self.assertEqual(sakura.at(-3.0), _rgb("#FF7AB6"))
        self.assertEqual(sakura.at(9.0), _rgb("#B36CFF"))

    def test_unknown_color_falls_back_to_default(self):
        self.assertEqual(music.normalize_color_id("nope"), "default")
        self.assertEqual(music.normalize_color_id(None), "default")
        self.assertEqual(music.normalize_color_id(""), "default")
        self.assertEqual(music.normalize_color_id("ICE"), "ice", "id 大小写归一")
        for cid in COLOR_ORDER:
            self.assertEqual(music.normalize_color_id(cid), cid)
        with self.assertLogs("mk87.music", level="DEBUG") as logs:
            music.normalize_color_id("nope")
        self.assertIn("nope", "\n".join(logs.output), "未知 id 应打 debug 日志")
        engine = music.MusicEngine(4, color="bogus")
        self.assertEqual(engine.color, "default")
        self.assertIsNone(engine.st["palette"])


class TestColorOverlayRenderers(unittest.TestCase):
    """颜色覆盖的渲染行为：动态多色模式（1/2/4/5/13 + 14~22）生效，纯色/背景不变。"""

    def test_mode4_single_color_exact(self):
        bands = [1.0] * 32
        for cid in ("ice", "violet", "pink", "lime", "amber"):
            engine = music.MusicEngine(4, amplitude_ui=100, color=cid)
            for _ in range(3):
                engine.tick(800, bands)
            lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
            self.assertEqual(lit, {_rgb(COLOR_STOPS[cid][0])},
                             f"mode 4 + {cid} 应整块统一成该颜色")

    def test_mode4_gradient_keeps_rotation(self):
        """径向色相动画（~275°/s）保留：渐变取样位置随原色相一起旋转。"""
        bands = [1.0] * 32
        engine = music.MusicEngine(4, amplitude_ui=100, color="aurora")
        engine.tick(800, bands)
        frames = []
        for _ in range(8):
            engine.tick(800, bands)
            grid = music._render_frame(engine.lay, dict(engine.st), 4)
            lit = [grid[r][c] for r in range(6) for c in range(17) if sum(grid[r][c]) > 0]
            self.assertTrue(lit, "mode 4 应有点亮")
            _assert_within(self, lit, COLOR_STOPS["aurora"], "mode4/aurora")
            frames.append(tuple(lit))
        self.assertGreaterEqual(len(set(frames)), 6,
                                "调色板应继续逐 tick 旋转（新色板按原相位取样）")

    def test_mode5_single_color_exact_and_gradient_cycles(self):
        engine = music.MusicEngine(5, color="ice")
        for _ in range(20):
            engine.tick(700)
        lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertEqual(lit, {_rgb("#00E5FF")}, "mode 5 + ice 每帧整屏统一冰蓝")
        engine = music.MusicEngine(5, color="sunset")
        seen = set()
        for i in range(60):
            engine.tick(300 + (i * 37) % 500)
            lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
            if not lit:
                continue
            self.assertEqual(len(lit), 1, "模式 5 每帧仍只有一种颜色")
            rgb = next(iter(lit))
            _assert_within(self, [rgb], COLOR_STOPS["sunset"], "mode5/sunset")
            seen.add(rgb)
        self.assertGreaterEqual(len(seen), 20,
                                "新调色板按原相位推进（5s 走完整个渐变）")

    def test_mode13_single_color_exact_and_gradient_rings(self):
        engine = music.MusicEngine(13, color="lime")
        for _ in range(30):
            engine.tick(800)
        lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertEqual(lit, {_rgb("#A8FF3E")}, "mode 13 + lime 同心环统一色")
        engine = music.MusicEngine(13, color="sakura")
        seen = set()
        for _ in range(30):
            engine.tick(800)
            seen |= {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertGreaterEqual(len(seen), 3, "不同环相位 → 渐变上多个位置")
        _assert_within(self, seen, COLOR_STOPS["sakura"], "mode13/sakura")

    def test_mode1_mode2_single_color_is_uniform(self):
        """1/2 的单色 id：整块统一色，但保留官方亮度缩放（(c*255)>>8）。"""
        for mode in (1, 2):
            engine = music.MusicEngine(mode, amplitude_ui=60, color="amber")
            for _ in range(30):
                engine.tick(700)
            lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
            self.assertTrue(lit, f"mode {mode} 应有点亮")
            self.assertEqual(lit, {_scaled(_rgb("#FF6A00"))},
                             f"mode {mode} + amber 应整块统一")

    def test_row_bands_gradient_samples_by_row(self):
        """1/2 的横条按「原始行位置」在 stops 上取样（顶部→底部）。"""
        grid = music._zeros(6, 17)
        music._fill_row_bands(grid, [(0, 255, 0), (255, 255, 0), (255, 0, 0)], 100,
                              music.Palette("sakura"))
        self.assertEqual(grid[0][0], _scaled(_rgb("#FF7AB6")), "顶行 = 渐变起点")
        self.assertEqual(grid[5][0], _scaled(_rgb("#B36CFF")), "底行 = 渐变终点")
        self.assertNotEqual(grid[2][0], grid[3][0], "渐变应在行间铺开")
        _assert_within(self, {grid[r][c] for r in range(6) for c in range(17)},
                       COLOR_STOPS["sakura"], "row_bands/sakura")

    def test_solid_modes_ignore_color(self):
        for cid in ("ice", "sunset", "aurora"):
            for mode in SOLID_V1_MODES:
                self.assertEqual(music_default_digest(mode, 0, cid),
                                 music_default_digest(mode, 0),
                                 f"纯色模式 {mode} 不应受 color={cid} 影响")
        engine = music.MusicEngine(6, color="pink")
        for _ in range(10):
            engine.tick(700)
        lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertEqual(lit, {(254, 254, 254)}, "模式 6 仍是官方纯白")

    def test_other_modes_consume_color(self):
        """14~22 自 v0.1.4 起也消费颜色覆盖（逐模式细节见 test_music_color_modes）。"""
        for mode in (14, 15, 16, 17, 18, 19, 20, 21, 22):
            self.assertNotEqual(music_default_digest(mode, 4, "aurora"),
                                music_default_digest(mode, 4),
                                f"模式 {mode} 现在应受颜色覆盖影响")

    def test_background_ignores_color(self):
        for backmode in (1, 2, 4, 5):
            self.assertEqual(music_default_digest(6, backmode, "ice"),
                             music_default_digest(6, backmode),
                             f"背景模式 {backmode} 不应受颜色覆盖影响")

    def test_unimplemented_mode_100_ignores_color(self):
        engine = music.MusicEngine(13, color="ice")
        base = dict(engine.st)
        with_pal = dict(engine.st)
        with_pal["palette"] = music.Palette("ice")
        self.assertEqual(music._render_frame(engine.lay, dict(base), 100),
                         music._render_frame(engine.lay, dict(with_pal), 100),
                         "未实现的 100 不消费用户调色板")
        self.assertNotIn(100, music.COLOR_OVERLAY_MODES)


class _FakeMusicPlayer:
    """只记录调用参数的假 MusicPlayer（API 层测试用）。"""

    def __init__(self):
        self.calls = []
        self.device = None
        self.status_value = {"running": False, "color": "default"}

    def start(self, **kwargs):
        self.calls.append(("start", kwargs))
        return {"ok": True}

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return dict(self.status_value)

    def status(self):
        return dict(self.status_value)


class TestColorPlumbing(unittest.TestCase):
    """status / update / HTTP API 贯通：color 可选、缺省 default、热更新立即生效。"""

    def test_status_exposes_color(self):
        self.assertEqual(music.MusicPlayer(_FakeDevice()).status()["color"], "default")

    def test_update_color_hot_switch(self):
        player = music.MusicPlayer(_FakeDevice())
        player._engine = music.MusicEngine(4)
        player._thread = threading.Thread(target=lambda: time.sleep(0.3), daemon=True)
        player._thread.start()
        try:
            st = player.update(color="aurora")
            self.assertEqual(st["color"], "aurora")
            self.assertEqual(player.color, "aurora")
            self.assertEqual(player._engine.color, "aurora")
            self.assertEqual(player._engine.st["palette"].id, "aurora",
                             "热更新后下一帧就用新色板（不重启音乐）")
            self.assertEqual(player.update(color="bogus")["color"], "default",
                             "未知 id 热更新应回落 default")
            self.assertEqual(player.update(mode=5)["color"], "default",
                             "不传 color 的热更新不改变当前档")
        finally:
            player._thread.join(timeout=1)
            player._thread = None

    def test_api_forwards_color(self):
        from server import app as server_app

        fake = _FakeMusicPlayer()
        fake.status_value = {"running": True, "color": "sakura"}
        with mock.patch.object(server_app.manager, "music", fake), \
                mock.patch.object(server_app, "_dev", return_value=_FakeDevice()):
            server_app.api_music_start({"mode": 4, "color": "ice", "amplitude": 30})
            server_app.api_music_start({"mode": 4})
            res = server_app.api_music_update({"mode": 1, "color": "sakura"})
            server_app.api_music_update({"mode": 1})
        starts = [kw for kind, kw in fake.calls if kind == "start"]
        updates = [kw for kind, kw in fake.calls if kind == "update"]
        self.assertEqual(starts[0]["color"], "ice", "start 应透传 color")
        self.assertEqual(starts[1]["color"], "default", "start 缺省 color → default")
        self.assertEqual(updates[0]["color"], "sakura", "update 应透传 color")
        self.assertEqual(updates[1]["color"], "default",
                         "「当前方案」不带 color → 恢复官方配色（不报错）")
        self.assertEqual(res["color"], "sakura", "update 返回的 status 带当前 color")


if __name__ == "__main__":
    unittest.main(verbosity=2)
