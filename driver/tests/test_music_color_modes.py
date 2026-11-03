#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""LED 颜色覆盖扩展到 14~22 的回归（v0.1.4，不需要设备/音频）。

背景：v0.1.3 的颜色覆盖只作用于 1/2/4/5/13（COLOR_OVERLAY_MODES），用户实测
14~22 看不到颜色变化。本文件锁定新规格：
  * 14 个「动态多色」模式（1/2/4/5/13 + 14~22）全部消费 color：default 与
    ice/aurora 的输出逐字节不同，ice 下只剩冰蓝一个色相族，aurora 下出现渐变多色；
  * 纯色 6~11（官方采样色）与背景模式不受 color 影响（逐字节一致）；
  * default / 缺省 color 与改动前的 fixture 快照逐字节一致（14 个覆盖模式抽查
    背景 0/4；220 组全量由 test_music_preview 的快照回归覆盖）；
  * 模式 100（屏光联动）未实现、引擎回落 13，回落后的 13 仍随 color 变化；
  * 未知 color id 回落 default。

喂料直接复用 fixture 快照的 16 tick 振幅序列 + 32 段频谱，这样「default == 快照」
与「ice/aurora 生效」用的是同一组输入，证据可以互相对照。

运行：cd driver; .\.venv\Scripts\python.exe -m unittest discover -s tests -q
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import music  # noqa: E402

#: 灰度快照 fixtures/README.md 里的同一组喂料（前 6 tick 静音以覆盖官方 C=5 归零）
AMPS = (0, 0, 0, 0, 0, 0, 300, 700, 1000, 520, 0, 0, 0, 0, 0, 820)
SNAPSHOT_PATH = os.path.join(HERE, "fixtures", "music_default_snapshot.json")

#: 测试侧独立副本（不复用后端常量，才能交叉校验后端表没写错）
ICE_RGB = (0x00, 0xE5, 0xFF)  # ice #00E5FF
AURORA_STOPS = ("#3EFF9A", "#00E5FF", "#7A5CFF")

#: 新规格：颜色覆盖作用于全部 14 个「动态多色」模式
OVERLAY_MODES = frozenset({1, 2, 4, 5, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22})
#: 官方纯色模式（色值写死，不受 color 影响）
SOLID_MODES = (6, 7, 8, 9, 10, 11)
#: 14~22 里逐帧只有一种颜色的模式（mode 5 是整屏旋转单色，渐变只能跨帧看出）
SINGLE_COLOR_PER_FRAME = {5}
#: 带「拖尾/缩放」的模式：单色调色板下仍应保留明暗层次（多个亮度档）
SHADED_MODES = (16, 17, 19, 20)

#: _run 结果缓存（同一喂料只跑一次；dict/frozenset 不可变共享，测试只读）
_RUN_CACHE = {}


def _rgb(hexstr: str):
    """``#RRGGBB`` → (r, g, b)（测试侧独立实现）。"""
    s = hexstr.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _bands32(tick: int):
    """固定 32 段频谱（只有模式 4 消费；其余模式忽略），与快照喂料一致。"""
    return [((tick * 7 + i * 3) % 11) / 10.0 for i in range(32)]


def _run(mode: int, color=None, backmode: int = 0):
    """固定喂料跑 16 tick，返回 (348B 载荷拼接的 SHA-256, 每 tick 点亮颜色集合)。

    与 test_music_preview.music_default_digest 使用同一套参数（amplitude_ui=60 /
    backmode_brightness=55 / 固定随机种子），所以 digest 可以直接和 fixture 对比。
    """
    key = (int(mode), color, int(backmode))
    hit = _RUN_CACHE.get(key)
    if hit is not None:
        return hit
    engine = music.MusicEngine(mode, amplitude_ui=60, backmode=backmode,
                               backmode_brightness=55, color=color)
    random.seed(0x5EED)  # 模式 19 用 random.random()：固定种子才能逐字节复现
    buf = bytearray()
    frames = []
    for tick, amp in enumerate(AMPS):
        payload = engine.tick(amp, _bands32(tick))
        assert len(payload) == 87 * 4, f"mode {mode} 载荷长度"
        buf.extend(payload)
        frames.append(frozenset(rgb for rgb in engine.last_colors.values() if sum(rgb) > 0))
    result = (hashlib.sha256(bytes(buf)).hexdigest(), tuple(frames))
    _RUN_CACHE[key] = result
    return result


def _upper(stops):
    """调色板各通道上限（线性插值必落在 stops 包围盒内；亮度缩放只会更暗）。"""
    rgbs = [_rgb(s) for s in stops]
    return tuple(max(c[i] for c in rgbs) for i in range(3))


class TestOverlayModeSet(unittest.TestCase):
    """覆盖范围（集合/接线）本身：14 个模式，且 14~22 的渲染器都收 pal 参数。"""

    def test_overlay_modes_match_new_spec(self):
        self.assertEqual(music.COLOR_OVERLAY_MODES, OVERLAY_MODES,
                         "颜色覆盖应扩到 1/2/4/5/13 + 14~22 共 14 个动态多色模式")
        self.assertEqual(len(music.COLOR_OVERLAY_MODES), 14)
        self.assertTrue(music.COLOR_OVERLAY_MODES <= music.IMPLEMENTED_MODES,
                        "覆盖集合里不允许出现未实现的模式")

    def test_solid_and_unimplemented_modes_excluded(self):
        for mode in SOLID_MODES:
            self.assertNotIn(mode, music.COLOR_OVERLAY_MODES,
                             f"纯色模式 {mode} 保持官方采样色")
        self.assertNotIn(100, music.COLOR_OVERLAY_MODES,
                         "100 未实现；引擎回落 13 后由 13 的覆盖生效")

    def test_every_overlay_renderer_accepts_palette(self):
        """14~22 的渲染器必须收 pal 且缺省 None（None = 原路径，逐字节不变）。"""
        funcs = [(m, getattr(music, f"_render_mode_{m}")) for m in (4, 13)]
        funcs += [(m, getattr(music, f"_render_mode_{m}")) for m in range(14, 23)]
        funcs.append((1, music._render_mode_steps))  # 1/2/5 共用
        for mode, fn in funcs:
            params = inspect.signature(fn).parameters
            self.assertIn("pal", params, f"mode {mode} 的渲染器必须接受 pal")
            self.assertIsNone(params["pal"].default,
                              f"mode {mode} 的 pal 必须缺省 None（default 走原代码路径）")

    def test_mode14_default_keeps_four_official_ray_colors(self):
        """default 下 mode 14 仍是官方固定四色（绿/蓝/黄/红），证明映射无损。"""
        engine = music.MusicEngine(14, amplitude_ui=100)
        for _ in range(20):
            engine.tick(900)
        lit = {rgb for rgb in engine.last_colors.values() if sum(rgb) > 0}
        self.assertEqual(lit, {(0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 0)})


class TestAllDynamicModesConsumeColor(unittest.TestCase):
    """14 个动态多色模式都随 color 变化，且只出现预设色相族。"""

    def test_default_differs_from_ice_and_aurora(self):
        for mode in sorted(OVERLAY_MODES):
            base = _run(mode)[0]
            for cid in ("ice", "aurora"):
                self.assertNotEqual(
                    _run(mode, cid)[0], base,
                    f"mode {mode} + color={cid} 应与 default 逐字节不同（覆盖没生效）")

    def test_ice_keep_single_ice_hue_family(self):
        """单色 id：所有点亮键都应是 ice 色系的缩放（红通道恒 0、蓝≥绿>0）。"""
        self.assertEqual(music.Palette("ice").at(0.37), ICE_RGB)
        for mode in sorted(OVERLAY_MODES):
            _digest, frames = _run(mode, "ice")
            lit = set().union(*frames)
            self.assertTrue(lit, f"mode {mode} + ice 应有点亮")
            for rgb in lit:
                self.assertEqual(rgb[0], 0, f"mode {mode} + ice 不应出现红通道：{rgb}")
                self.assertGreater(rgb[1], 0, f"mode {mode} + ice 的绿通道不该为 0：{rgb}")
                self.assertGreaterEqual(rgb[2], rgb[1],
                                        f"mode {mode} + ice 应以蓝为主（冰蓝 #00E5FF）：{rgb}")

    def test_aurora_is_gradient_and_within_palette(self):
        """渐变 id：整轮喂料内出现多个调色板取样位置，且颜色都在 stops 包围盒内。"""
        upper = _upper(AURORA_STOPS)
        for mode in sorted(OVERLAY_MODES):
            _digest, frames = _run(mode, "aurora")
            lit = set().union(*frames)
            self.assertGreaterEqual(len(lit), 3,
                                    f"mode {mode} + aurora 应出现渐变多色（只有 {sorted(lit)}）")
            for rgb in lit:
                for ch in range(3):
                    self.assertLessEqual(
                        rgb[ch], upper[ch],
                        f"mode {mode} + aurora 的 {rgb} 超出调色板通道上限 {upper}")
            self.assertTrue(frames[-1], f"mode {mode} + aurora 末帧应有亮键")
            if mode not in SINGLE_COLOR_PER_FRAME:
                self.assertGreaterEqual(
                    len(frames[-1]), 2,
                    f"mode {mode} + aurora 同一帧应有多色（按原色相在 stops 上取样）")

    def test_ice_keeps_brightness_layers(self):
        """单色 id 不是「整块死白」：带拖尾/缩放的模式仍有多个亮度档。"""
        for mode in SHADED_MODES:
            _digest, frames = _run(mode, "ice")
            lit = set().union(*frames)
            self.assertGreaterEqual(len(lit), 2,
                                    f"mode {mode} + ice 应保留明暗层次（多个亮度档）")
            self.assertGreater(max(sum(c) for c in lit), min(sum(c) for c in lit),
                               f"mode {mode} + ice 的亮度档应真的有差异")


class TestNonOverlayModesUnchanged(unittest.TestCase):
    """纯色 6~11、背景模式：完全不消费 color（逐字节一致）。"""

    def test_solid_modes_ignore_color(self):
        for mode in SOLID_MODES:
            base = _run(mode)[0]
            for cid in ("ice", "aurora", "sunset"):
                self.assertEqual(_run(mode, cid)[0], base,
                                 f"纯色模式 {mode} 不应受 color={cid} 影响")

    def test_background_modes_ignore_color(self):
        for backmode in (1, 2, 4, 5):
            self.assertEqual(_run(6, "ice", backmode)[0], _run(6, None, backmode)[0],
                             f"背景模式 {backmode} 不应受颜色覆盖影响")


class TestFallbacks(unittest.TestCase):
    """mode 100 回落 13、未知 color id 回落 default。"""

    def test_mode_100_falls_back_to_13_with_color(self):
        engine = music.MusicEngine(100, color="ice")
        self.assertEqual(engine.mode, 13, "100（屏光联动）未实现，引擎回落 13")
        self.assertIsNotNone(engine.st["palette"], "回落后的 13 仍应加载调色板")
        self.assertEqual(_run(100, "ice")[0], _run(13, "ice")[0],
                         "mode 100 与 13 的渲染必须完全一致（回落路径）")
        self.assertNotEqual(_run(100, "ice")[0], _run(100)[0],
                            "回落后的 13 应随 color 变化")
        lit = set().union(*_run(100, "ice")[1])
        for rgb in lit:
            self.assertEqual(rgb[0], 0, f"回落 13 + ice 也不该出现红通道：{rgb}")

    def test_unknown_color_id_falls_back_to_default(self):
        for mode in (13, 14, 17, 22):
            engine = music.MusicEngine(mode, color="bogus")
            self.assertEqual(engine.color, "default")
            self.assertIsNone(engine.st["palette"])
            self.assertEqual(_run(mode, "bogus")[0], _run(mode)[0],
                             f"未知 color 应回落 default（mode {mode}）")


class TestDefaultStillByteIdentical(unittest.TestCase):
    """default / 缺省 color：与改动前 fixture 快照逐字节一致。"""

    @classmethod
    def setUpClass(cls):
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            cls.snapshot = json.load(f)

    def test_omitted_and_explicit_default_identical(self):
        for mode in sorted(OVERLAY_MODES):
            self.assertEqual(_run(mode)[0], _run(mode, "default")[0],
                             f"mode {mode}：缺省 color 与显式 default 必须一致")

    @unittest.skipUnless(
        sys.platform == "win32",
        "默认档快照在 Windows 上生成（不同 libm 的 sin/cos/atan2 末位可能不同）")
    def test_matches_pre_change_snapshot_for_overlay_modes(self):
        for mode in sorted(OVERLAY_MODES):
            for backmode in (0, 4):
                want = self.snapshot["cases"][f"{mode}/{backmode}"]
                self.assertEqual(
                    _run(mode, None, backmode)[0], want,
                    f"mode {mode} backmode {backmode} 与改动前快照不一致")


if __name__ == "__main__":
    unittest.main(verbosity=2)
