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
        self.assertEqual(music.V1_DISPLAY_MODES,
                         [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10, 100],
                         "官方 v1 显示模式顺序/编号必须与 docs/music-v1-config.json 一致")
        self.assertEqual(music.V1_IMPLEMENTED_MODES, [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10],
                         "屏光联动（100）尚未实现，不进已移植列表")
        self.assertNotIn(100, music.IMPLEMENTED_MODES)
        self.assertEqual(music.MusicEngine(100).mode, 13, "100 仍回落 13")
        self.assertEqual(set(music.V1_STEP_MODES), {1, 2, 4, 5, 6, 7, 8, 9, 10, 11})

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

    def test_mode4_radial_hue(self):
        engine, lits = _drive(4)
        lit = [rgb for rgb in engine.last_colors.values() if sum(rgb) > 0]
        self.assertGreater(max(lits), 0)
        self.assertTrue(all(max(rgb) == 255 for rgb in lit), "模式 4 是满饱和径向色相")

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
        self.assertEqual(st["officialModes"], [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10, 100])
        self.assertEqual(st["officialImplementedModes"],
                         [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10])
        self.assertIn(14, st["implementedModes"], "当前方案的 14/15/…/22 仍应保留")
        self.assertEqual(st["amplitude"], 50)
        self.assertEqual(st["backmodeBrightness"], 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
