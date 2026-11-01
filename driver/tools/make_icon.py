#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标（PNG / ICO / SVG）到 driver/assets/。

设计：深色圆角方块 + 三排键盘按键 + 一颗点亮的绿色键（呼应 RGB 键盘主题）。
用法：python tools/make_icon.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")


def rounded(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def draw_icon(size: int = 256) -> Image.Image:
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(S * 0.06)
    bg = (int(S * 0.03), int(S * 0.05), int(S * 0.09), 255)
    rounded(d, (pad, pad, S - pad, S - pad), int(S * 0.20), bg)
    # 内部微光边
    d.rounded_rectangle((pad, pad, S - pad, S - pad), radius=int(S * 0.20),
                        outline=(60, 90, 140, 160), width=max(1, S // 128))

    key_w = int(S * 0.150)
    key_h = int(S * 0.130)
    gap = int(S * 0.045)
    rows = 3
    cols = 4
    total_w = cols * key_w + (cols - 1) * gap
    total_h = rows * key_h + (rows - 1) * gap
    x0 = (S - total_w) // 2
    y0 = (S - total_h) // 2 + int(S * 0.01)
    key_color = (245, 248, 255, 255)
    dim = (150, 165, 190, 255)
    for r in range(rows):
        for c in range(cols):
            x = x0 + c * (key_w + gap)
            y = y0 + r * (key_h + gap)
            lit = (r == 1 and c == 2)
            color = (60, 220, 130, 255) if lit else (key_color if r != 2 else dim)
            rounded(d, (x, y, x + key_w, y + key_h), int(S * 0.030), color)
    # 底排空格键（横跨 3 列）
    y = y0 + 2 * (key_h + gap)
    x = x0 + (key_w + gap)
    rounded(d, (x, y, x + 3 * key_w + 2 * gap, y + key_h), int(S * 0.030), dim)
    # 右下角一个小 RGB 渐变点
    r = int(S * 0.055)
    cx, cy = S - pad - r - int(S * 0.03), S - pad - r - int(S * 0.03)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(120, 200, 255, 255))
    return img


SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect x="15" y="15" width="226" height="226" rx="51" fill="#081018"/>
  <rect x="15" y="15" width="226" height="226" rx="51" fill="none" stroke="#3c5a8c" stroke-opacity="0.6"/>
  <g>
    <rect x="40" y="63" width="38" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="88" y="63" width="38" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="136" y="63" width="38" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="184" y="63" width="32" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="40" y="106" width="38" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="88" y="106" width="38" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="136" y="106" width="38" height="33" rx="8" fill="#3cdc82"/>
    <rect x="184" y="106" width="32" height="33" rx="8" fill="#f5f8ff"/>
    <rect x="40" y="149" width="38" height="33" rx="8" fill="#96a5be"/>
    <rect x="88" y="149" width="128" height="33" rx="8" fill="#96a5be"/>
  </g>
  <circle cx="212" cy="212" r="14" fill="#78c8ff"/>
</svg>
"""


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    img = draw_icon(512)
    png = os.path.join(OUT, "mk87.png")
    img.save(png)
    ico = os.path.join(OUT, "mk87.ico")
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    svg = os.path.join(OUT, "mk87.svg")
    with open(svg, "w", encoding="utf-8") as f:
        f.write(SVG)
    print("saved:", png, ico, svg)


if __name__ == "__main__":
    main()
