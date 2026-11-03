# -*- coding: utf-8 -*-
"""模式 4（曲率频阶）静音兜底行为：真实音频链路给过频谱后不再退回旧轮廓。

背景：v0.1.3 真机反馈「选了 LED 颜色后模式 4 像旧方案」——根因是某帧 17 段频谱
全 0（安静/回环断流）时整帧退回 _MODE4_CURVATURE 合成轮廓。修复后：只要
tick() 收到过 bands32（哪怕全 0），就永不退回旧轮廓；静音 = 柱子归零。
"""
import unittest

from mk87lib import music


def lit_count(payload: bytes) -> int:
    n = 0
    for k in range(87):
        r, g, b = payload[k * 4 + 1], payload[k * 4 + 2], payload[k * 4 + 3]
        if r + g + b > 12:
            n += 1
    return n


class TestMode4SilenceFallback(unittest.TestCase):
    def test_silence_after_real_spectrum_never_falls_back_to_old_contour(self):
        eng = music.MusicEngine(4, amplitude_ui=50, backmode=0, color="default")
        bands = [0.2] * 32
        for _ in range(5):
            payload = eng.tick(600, bands)
        self.assertGreater(lit_count(payload), 0, "有频谱时应有柱子")
        # 全 0 频谱（安静/断流）→ 柱子归零，不能出现旧合成轮廓
        for _ in range(4):
            payload = eng.tick(600, [0.0] * 32)
            self.assertEqual(lit_count(payload), 0,
                             "真实链路给过频谱后，静音必须是空帧（旧轮廓已禁用）")

    def test_no_spectrum_input_keeps_legacy_contour(self):
        """纯 tick(amp)（bands32=None，单测/外部调用）保留旧轮廓行为。"""
        eng = music.MusicEngine(4, amplitude_ui=50, backmode=0, color="default")
        for _ in range(5):
            payload = eng.tick(600)
        self.assertGreater(lit_count(payload), 0,
                           "无频谱输入时应退化为随振幅伸缩的曲率轮廓")

    def test_silence_frames_are_zero_not_contour_bytes(self):
        """再喂非零频谱后仍能恢复柱子（has_spectrum 不影响恢复）。"""
        eng = music.MusicEngine(4, amplitude_ui=50, backmode=0, color="default")
        bands = [0.2] * 32
        for _ in range(3):
            eng.tick(600, bands)
        eng.tick(600, [0.0] * 32)
        payload = eng.tick(600, bands)
        self.assertGreater(lit_count(payload), 0, "频谱恢复后柱子应恢复")


if __name__ == "__main__":
    unittest.main(verbosity=2)
