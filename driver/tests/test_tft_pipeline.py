#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TFT 动画压缩管线离线测试（不需要设备）。

运行： python -m unittest tests.test_tft_pipeline -v
"""
from __future__ import annotations

import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from PIL import Image  # noqa: E402

from mk87lib import tft  # noqa: E402


def make_gif(frames=10, size=(480, 270), duration=100):
    """生成一段水平移动色块的测试 GIF。"""
    imgs = []
    for i in range(frames):
        im = Image.new("RGB", size, (10, 10, 30))
        x = int((size[0] - 80) * i / max(1, frames - 1))
        for k in range(80):
            for y in range(size[1] // 3, size[1] * 2 // 3):
                im.putpixel((x + k, y), (250, 60 + (i * 7) % 180, 20))
        imgs.append(im)
    buf = io.BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=duration, loop=0)
    return buf.getvalue()


def make_static_png(size=(1920, 1080)):
    im = Image.new("RGB", size, (40, 80, 160))
    for x in range(0, size[0], 40):
        for y in range(0, size[1], 40):
            im.putpixel((x, y), (255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestTftPipeline(unittest.TestCase):
    def test_frame_count_reduction(self):
        raw = make_gif(frames=20)
        res = tft.convert_animation(raw, max_frames=140, frame_count=5, preview=False)
        self.assertLessEqual(res["framesCount"], 6)  # 5 + 可选的末帧占位
        self.assertGreaterEqual(res["framesCount"], 1)
        self.assertEqual(len(res["_frames565"]), res["framesCount"])
        self.assertEqual(len(res["delaysCs"]), res["framesCount"])
        # 总时长接近源（20 帧 × 100ms = 2000ms，去重/抽帧后仍保留时间轴）
        self.assertAlmostEqual(sum(res["delaysMs"]), 2000, delta=150)
        # 每帧必须是 64800 字节
        for data in res["_frames565"]:
            self.assertEqual(len(data), tft.FRAME_BYTES)

    def test_static_image_becomes_short(self):
        raw = make_static_png()
        res = tft.convert_animation(raw, max_frames=140, preview=False)
        # 静图：1 帧 + 末帧占位
        self.assertLessEqual(res["framesCount"], 2)

    def test_fit_modes(self):
        raw = make_static_png((300, 300))
        for fit in tft.FIT_MODES:
            res = tft.convert_animation(raw, max_frames=140, fit=fit, preview=False)
            self.assertEqual(len(res["_frames565"][0]), tft.FRAME_BYTES)

    def test_dither_and_adaptive(self):
        raw = make_gif(frames=12)
        res = tft.convert_animation(raw, max_frames=140, frame_count=8, dither=True,
                                    temporal="adaptive", preview=False)
        self.assertGreaterEqual(res["framesCount"], 1)
        self.assertTrue(res["dither"])
        self.assertEqual(res["temporal"], "adaptive")

    def test_preview_frames(self):
        raw = make_gif(frames=4)
        res = tft.convert_animation(raw, max_frames=140, frame_count=3, preview=True)
        self.assertIn("frames", res)
        self.assertEqual(len(res["frames"]), res["framesCount"])
        self.assertTrue(res["frames"][0].startswith("data:image/png;base64,"))

    def test_estimate(self):
        raw = make_gif(frames=10)
        res = tft.convert_animation(raw, max_frames=140, frame_count=5, preview=False)
        stats = res["stats"]
        expected_packets = (256 + res["framesCount"] * tft.FRAME_BYTES + 4095) // 4096
        self.assertEqual(stats["packets"], expected_packets)
        self.assertGreater(stats["estimatedSeconds"], 0)

    def test_max_frames_guard(self):
        raw = make_gif(frames=10)
        res = tft.convert_animation(raw, max_frames=140, frame_count=999, preview=False)
        self.assertLessEqual(res["framesCount"], 140)

    def test_reject_bad_file(self):
        with self.assertRaises(Exception):
            tft.convert_animation(b"not an image", preview=False)

    def test_trim_source_range(self):
        raw = make_gif(frames=12, duration=120)
        res = tft.convert_animation(raw, max_frames=140, trim_start_frame=3,
                                    trim_end_frame=8, preview=False)
        self.assertEqual(res["sourceFrames"], 6)          # 3..8 共 6 帧
        self.assertEqual(res["rawSourceFrames"], 12)
        self.assertTrue(res["trim"]["trimmed"])
        self.assertEqual(res["sourceDurationMs"], 720)     # 6 × 120ms
        self.assertAlmostEqual(sum(res["delaysMs"]), 720, delta=10)

    def test_over_limit_frame_count(self):
        raw = make_gif(frames=10)
        res = tft.convert_animation(raw, max_frames=140, frame_count=150, preview=False)
        self.assertEqual(res["requestedFrames"], 150)
        self.assertTrue(any("超过设备上限" in w for w in res["warnings"]))
        self.assertLessEqual(res["framesCount"], 140)

    def test_bad_trim_range(self):
        raw = make_gif(frames=10)
        with self.assertRaises(tft.MK87Error if hasattr(tft, "MK87Error") else Exception):
            tft.convert_animation(raw, max_frames=140, trim_start_frame=0,
                                  trim_end_frame=5, preview=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
