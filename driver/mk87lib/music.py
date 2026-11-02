"""音乐律动（USB only）：系统音频采集 → 官方渲染器 → 0x32 逐键帧流。

协议真机结论（docs/music-rhythm.md §9 / TEST-REPORT §9）：
* 必须先 SET_LED_EFFECT 到自定义族 mode ∈ {20,21,128}，再发 cmd 0x32 逐键帧才显示；
* 一帧 = 87 键 × 4 字节 [keyValue, R, G, B]，按官方 keyList 行优先；USB 下 7 包/帧，20fps 稳定；
* 停发约 5 秒后固件回落到自定义表；本模块停止时会主动恢复进入前的灯效；
* 2.4G 官方不支持，仅 USB 可用。

渲染器：**逐行移植官方 bundle**（scripts/music_ref.js 已 31/31 自检通过），
不再使用早期自研的 spectrum/rainbow 等简化渲染（那种会点亮几乎全部按键，观感是"全亮"）。
已移植模式：
  13 = Dance to the Beat（同心环扩散，默认）
  14 = Dust Glow Spiral（中心四色射线旋转）
  17 = Firefly Trail（中心行正弦波 + 拖尾）
  4  = Curvature Frequency Steps（背景 + 包络柱状；1 与之相同）
其余官方模式（15/16/18/19/20/21/22）暂回落到 13，等后续补齐。

音频分析：官方 K7/Nse（总振幅）+ 3 段 Pse + 32 段频谱（前端电平条用）。
"""
from __future__ import annotations

import logging
import math
import platform
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import keymap, lighting
from .errors import MK87Error

log = logging.getLogger("mk87.music")

RGB = Tuple[int, int, int]

# ----------------------------------------------------------------------
# 官方常量 / 模式表
# ----------------------------------------------------------------------
_AMP_FLOOR = 0.01
_AMP_ATTACK = 0.3
_AMP_DECAY = 0.008
_AMP_GATE = 5

MODE_NAMES = {
    13: ("律动节拍", "Dance to the Beat"),
    14: ("光尘螺旋", "Dust Glow Spiral"),
    17: ("萤火轨迹", "Firefly Trail"),
    4: ("曲率频谱", "Curvature Frequency Steps"),
    1: ("曲率频谱（细）", "Curvature Frequency Steps"),
    15: ("休眠火山", "Dormant Volcano"),
    16: ("光箭穿刺", "Light Arrow Piercing"),
    18: ("光茧共鸣", "Light Cocoon Resonance"),
    19: ("音叉振动", "Tuning Fork Vibration"),
    20: ("曲率传承", "Curvature Legacy Track"),
    21: ("行波节奏", "Row Wave Rhythm"),
    22: ("双心共舞", "Dual Heart Dance"),
}

#: 前端可选模式（当前已完整移植的官方渲染器）
MODES = [
    {"mode": 13, "name": MODE_NAMES[13][0], "nameEn": MODE_NAMES[13][1]},
    {"mode": 14, "name": MODE_NAMES[14][0], "nameEn": MODE_NAMES[14][1]},
    {"mode": 17, "name": MODE_NAMES[17][0], "nameEn": MODE_NAMES[17][1]},
    {"mode": 4, "name": MODE_NAMES[4][0], "nameEn": MODE_NAMES[4][1]},
]

#: 旧版 style 字符串 → 官方模式（兼容旧前端/旧调用）
STYLE_TO_MODE = {
    "spectrum": 4,
    "rainbow": 13,
    "pulse": 13,
    "ripple": 13,
    "firefly": 17,
    "dance": 13,
    "spiral": 14,
    "frequency": 4,
}
IMPLEMENTED_MODES = {13, 14, 17, 4, 1}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _rnd(v: float) -> int:
    """JS Math.round 等价（.5 向上）。"""
    return int(math.floor(v + 0.5))


def _hsv(hue: float, saturation: float = 1.0, value: float = 1.0) -> RGB:
    """官方 kV(hue, saturation, value)：色相 → RGB（0..255）。"""
    r = value * saturation
    i = r * (1 - abs(((hue / 60.0) % 2) - 1))
    a = value - r
    if 0 <= hue < 60:
        o, s, c = r, i, 0.0
    elif hue < 120:
        o, s, c = i, r, 0.0
    elif hue < 180:
        o, s, c = 0.0, r, i
    elif hue < 240:
        o, s, c = 0.0, i, r
    elif hue < 300:
        o, s, c = i, 0.0, r
    else:
        o, s, c = r, 0.0, i
    return (_rnd((o + a) * 255), _rnd((s + a) * 255), _rnd((c + a) * 255))


# ----------------------------------------------------------------------
# 键盘布局（官方 buildLayout）
# ----------------------------------------------------------------------
#: 官方 musicConfig.keyOffset：{keyValue: offsetX}
_KEY_OFFSETS = {1: 1, 65: 1, 90: 2, 83: 3, 84: 3}

_LAYOUT: Optional[dict] = None


def layout() -> dict:
    """官方 me()/Re() 的 6 行 × 18 列网格布局（行优先、含 keyOffset 偏移）。"""
    global _LAYOUT
    if _LAYOUT is not None:
        return _LAYOUT
    rows = keymap.tables().layout["rows"]
    F = len(rows)
    P = max(len(r) for r in rows)
    cells: List[dict] = []
    for ri, row in enumerate(rows):
        shift = 0
        for idx, k in enumerate(row):
            col = idx + shift
            off = _KEY_OFFSETS.get(int(k["slot"]))
            if off:
                col += off
                shift += off
            cells.append({
                "row": ri,
                "col": col,
                "value": int(k["slot"]),
                "name": k.get("name", ""),
                "disabledLight": False,
            })
    visible = [c for c in cells if not c["disabledLight"]]
    le = F // 2 - 1 if F % 2 == 0 else F // 2
    row_len = len(rows[le]) if 0 <= le < F else P
    ce = row_len // 2 - 1 if row_len % 2 == 0 else row_len // 2
    _LAYOUT = {
        "F": F, "P": P, "width": P + 1,
        "cells": cells, "visible": visible,
        "centerRow": le, "centerCol": ce,
    }
    return _LAYOUT


def key_order() -> List[int]:
    """逐键帧流里的 87 个 keyValue（官方 keyList 行优先）。"""
    return [c["value"] for c in layout()["visible"]]


# ----------------------------------------------------------------------
# 官方渲染器（逐行移植 scripts/music_ref.js）
# ----------------------------------------------------------------------
def _zeros(F: int, P: int) -> List[List[RGB]]:
    return [[(0, 0, 0) for _ in range(P)] for _ in range(F)]


def _fill_solid(grid, color: RGB, brightness_pct: float) -> None:
    n = _rnd(brightness_pct * 2.55)
    c = (
        _rnd(n * color[0] / 256),
        _rnd(n * color[1] / 256),
        _rnd(n * color[2] / 256),
    )
    for row in grid:
        for i in range(len(row)):
            row[i] = c


def _fill_row_bands(grid, colors: List[RGB], brightness_pct: float) -> None:
    n = _rnd(brightness_pct * 2.55)
    rows = len(grid)
    per = rows // len(colors)
    extra = rows % len(colors)
    row_idx = 0
    for ci, color in enumerate(colors):
        cnt = per + (1 if ci < extra else 0)
        c = (_rnd(n * color[0] / 256), _rnd(n * color[1] / 256), _rnd(n * color[2] / 256))
        for _ in range(cnt):
            if row_idx >= rows:
                break
            for col in range(len(grid[row_idx])):
                grid[row_idx][col] = c
            row_idx += 1


def _fill_radial_hue(grid, center_row: int, center_col: int, hue_phase: float) -> None:
    rows, cols = len(grid), len(grid[0])
    for r in range(rows):
        for c in range(cols):
            angle = math.atan2(r - center_row, c - center_col)
            hue = hue_phase + ((180 + (180 / math.pi) * angle) % 360)
            if hue < 0:
                hue += 360
            if hue >= 360:
                hue -= 360
            grid[r][c] = _hsv(hue, 1.0, 1.0)


def _fill_solid_hue(grid, hue_phase: float, brightness_pct: float) -> None:
    hue = _rnd(hue_phase) % 360
    c = _hsv(hue, 1.0, brightness_pct / 255.0)
    for row in grid:
        for i in range(len(row)):
            row[i] = c


def _apply_background(grid, backmode: int, brightness_pct: float, st: dict) -> None:
    """官方 _e：背景模式（0 = 黑、6..11 纯色、1/2 横向分段、4 径向色相、5 旋转纯色）。"""
    if backmode == 6:
        _fill_solid(grid, (255, 255, 255), brightness_pct)
    elif backmode == 7:
        _fill_solid(grid, (255, 0, 0), brightness_pct)
    elif backmode == 8:
        _fill_solid(grid, (255, 64, 0), brightness_pct)
    elif backmode == 9:
        _fill_solid(grid, (255, 255, 0), brightness_pct)
    elif backmode == 10:
        _fill_solid(grid, (0, 0, 255), brightness_pct)
    elif backmode == 11:
        _fill_solid(grid, (0, 255, 0), brightness_pct)
    elif backmode == 1:
        _fill_row_bands(grid, [(0, 255, 0), (255, 255, 0), (255, 0, 0)], brightness_pct)
    elif backmode == 2:
        _fill_row_bands(grid, [
            (255, 0, 255), (0, 0, 255), (0, 255, 255),
            (0, 255, 0), (255, 255, 0), (255, 0, 0),
        ], brightness_pct)
    elif backmode == 4:
        _fill_radial_hue(grid, st["centerRow"], st["centerCol"], st["huePhase"])
    elif backmode == 5:
        _fill_solid_hue(grid, st["huePhase"], brightness_pct)
    # 0 / 3 等 = 不画背景


def _build_rings(lay: dict) -> List[List[Tuple[int, int]]]:
    """官方 Se 的兜底环分桶（无 ringKeyPositions 时按到中心距离分环）。"""
    F, P = lay["F"], lay["P"]
    cr, cc = lay["centerRow"], lay["centerCol"]
    max_r = 0.0
    for r in range(F):
        for c in range(P):
            max_r = max(max_r, math.sqrt((c - cc) ** 2 + (r - cr) ** 2))
    r_count = max(4, int(math.ceil(max_r)))
    rings: List[List[Tuple[int, int]]] = [[] for _ in range(r_count)]
    for r in range(F):
        for c in range(P):
            dc, dr = c - cc, r - cr
            dist = math.sqrt(dc * dc + dr * dr)
            idx = int(math.floor((dist / r_count) * (r_count - 0.01)))
            is_center = idx == 0 and abs(dc) < 0.5 and abs(dr) < 0.5
            if not is_center and 0 <= idx < r_count:
                rings[idx].append((r, c))
    # 官方修正：ring1 首元素与第 4 个/末尾元素挪到 ring2
    if len(rings) > 2 and len(rings[1]) > 2:
        a = rings[1].pop(0)
        if F < 6:
            b = rings[1].pop(4) if len(rings[1]) > 4 else None
        else:
            b = rings[1].pop() if rings[1] else None
        if a:
            rings[2].append(a)
        if b:
            rings[2].append(b)
    return rings


def _render_mode_1or4(grid, mode: int, lay: dict, st: dict) -> None:
    """官方 Fe：背景 + 包络柱状（1 与 4 同一渲染器）。"""
    n = st["amplitudeUI"] / 100.0
    st["smoothAmp"] += (st["amp"] - st["smoothAmp"]) * n
    bg = _zeros(lay["F"], lay["P"])
    _apply_background(bg, mode, st["backmodeBrightness"], st)
    st["phase"] += st["amplitudeUI"] / 1000.0
    i = min(st["smoothAmp"], 1.0)
    bars: List[int] = []
    for e in range(lay["P"]):
        t = e / lay["P"]
        base = 0.2 + 0.3 * math.cos(t * math.pi)
        w1 = math.sin(st["phase"] * math.pi * 1.8 + e * 0.7) * 0.2
        w2 = math.sin(st["phase"] * math.pi * 0.9 + e * 1.3) * 0.15
        w3 = math.sin(st["phase"] * math.pi * 2.3 + e * 0.4) * 0.1
        w4 = math.sin(e * 2.1 + st["phase"] * 3.2) * 0.3
        lv = base + w1 + w2 + w3 + w4
        lv = 0.0 if lv < 0.1 else lv ** 1.5
        lv = _clamp(lv, 0.0, 1.2)
        u = i * (st["amplitudeUI"] / 8.0) * lv * lay["F"]
        bars.append(max(0, int(math.floor(u))))
    F = lay["F"]
    for row in range(F):
        target = F - 1 - row
        for col in range(lay["P"]):
            if target < bars[col]:
                grid[row][col] = bg[row][col]


def _render_mode_14(grid, lay: dict, st: dict) -> None:
    """官方 Ce：中心 4 色射线旋转。"""
    t = st["amplitudeUI"] / 100.0
    st["smoothAmp"] += (st["amp"] - st["smoothAmp"]) * t
    st["rotate"] = (st["rotate"] + 4) % 360
    F, P = lay["F"], lay["P"]
    max_dist = 0.0
    for r in range(F):
        for c in range(P):
            d = math.sqrt((c - lay["centerCol"]) ** 2 + (r - lay["centerRow"]) ** 2)
            max_dist = max(max_dist, d)
    r1 = min(st["smoothAmp"], 1.0)
    length = max(1.0, max_dist * r1)
    a = r1
    colors = [(0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 0)]
    angles = [0, 45, 90, 135]
    span = max(0.5, length)
    step_count = int(span / 0.5)
    for k in range(4):
        color = colors[k]
        rad = ((angles[k] + st["rotate"]) % 360) * math.pi / -180.0
        dx = math.cos(rad) * a * 2
        dy = math.sin(rad) * a * 1
        m = -length
        while m <= length:
            col = _rnd(lay["centerCol"] + dx * m)
            row = _rnd(lay["centerRow"] + dy * m)
            if 0 <= col < P and 0 <= row < F:
                grid[row][col] = color
            m += 0.5


def _render_mode_17(grid, lay: dict, st: dict) -> None:
    """官方 je：中心行正弦波 + 拖尾。"""
    t = min(st["amp"], 1.0)
    st["phase"] += 0.5
    if st["phase"] >= math.pi * 2:
        st["phase"] -= math.pi * 2
    st["huePhase"] = (st["huePhase"] + 0.02) % 1.0
    F, P = lay["F"], lay["P"]
    centers = [F // 2 - 1, F // 2] if F % 2 == 0 else [F // 2]
    for n in range(P):
        phi = (n / P) * math.pi * 2
        wave = math.sin(st["phase"] + phi)
        fall = 1 - (n / (P - 1)) ** 0.8 if P > 1 else 1.0
        scale = (1 + t * 2) * max(0.3, st["amplitudeUI"] / 50.0) * fall
        c = _rnd(wave * scale)
        color = _hsv((n / P * 360 + st["huePhase"] * 360) % 360, 1.0, 1.0)
        for cr in centers:
            row = cr + c
            if 0 <= row < F:
                grid[row][n] = color
            trail = min(3, abs(c))
            for a in range(1, trail + 1):
                rr = cr + (a if c >= 0 else -a)
                if 0 <= rr < F and rr != row:
                    f = 1 - a / (trail + 1)
                    grid[rr][n] = (_rnd(color[0] * f * 0.6),
                                   _rnd(color[1] * f * 0.6),
                                   _rnd(color[2] * f * 0.6))


def _render_mode_13(grid, lay: dict, st: dict) -> None:
    """官方 Se：中心同心环扩散（默认模式）。"""
    rings = _build_rings(lay)
    center_cells = rings[0] if rings else []
    ring_list = rings[1:]
    st["phase"] = (st["phase"] + 0.005) % 1.0
    st["huePhase"] = (st["huePhase"] + 0.005) % 1.0
    ring_count = len(ring_list)
    phases = []
    for e in range(ring_count):
        phases.append((st["phase"] - e / max(1, ring_count) + 1) % 1.0)
    amp = min(st["amp"], 1.0)
    threshold = max(0.01, 0.06 - amp * 0.05)
    lit = 0 if amp < threshold else max(1, min(ring_count, _rnd(st["amp"] * ring_count)))
    k = st["amplitudeUI"] / 100.0
    st["smoothValue"] += (lit - st["smoothValue"]) * k
    active = _rnd(st["smoothValue"])
    center_color = _hsv((st["huePhase"] * 360) % 360, 1.0, 1.0)
    F, P = lay["F"], lay["P"]
    for (r, c) in center_cells:
        if 0 <= r < F and 0 <= c < P:
            grid[r][c] = center_color
    for e in range(active):
        if e >= len(ring_list):
            break
        ring = ring_list[e]
        color = _hsv(((phases[e] + st["huePhase"]) * 360) % 360, 1.0, 1.0)
        for (r, c) in ring:
            if 0 <= r < F and 0 <= c < P:
                grid[r][c] = color


def _render_frame(lay: dict, st: dict, mode: int) -> List[List[RGB]]:
    grid = _zeros(lay["F"], lay["width"])
    if st["backmode"]:
        _apply_background(grid, st["backmode"], st["backmodeBrightness"], st)
    if mode in (1, 4):
        _render_mode_1or4(grid, mode, lay, st)
    elif mode == 13:
        _render_mode_13(grid, lay, st)
    elif mode == 14:
        _render_mode_14(grid, lay, st)
    elif mode == 17:
        _render_mode_17(grid, lay, st)
    else:
        _render_mode_13(grid, lay, st)  # 未移植模式回落到 13
    return grid


class MusicEngine:
    """官方音乐引擎：每个 20fps tick 把振幅变成 87 键 4B 载荷。"""

    def __init__(self, mode: int = 13, amplitude_ui: int = 50,
                 backmode: int = 0, backmode_brightness: int = 100) -> None:
        mode = int(mode)
        if mode not in IMPLEMENTED_MODES:
            mode = 13
        self.mode = mode
        self.lay = layout()
        self.st = {
            "mode": mode,
            "amplitudeUI": _clamp(int(amplitude_ui), 1, 100),
            "backmode": int(backmode),
            "backmodeBrightness": _clamp(int(backmode_brightness), 10, 100),
            "amp": 0.0,
            "smoothAmp": 0.0,
            "phase": 0.0,
            "huePhase": 0.0,
            "smoothValue": 0.0,
            "rotate": 0.0,
            "centerRow": self.lay["centerRow"],
            "centerCol": self.lay["centerCol"],
        }
        self._silence = 0
        #: 最近一帧的逐键颜色 {keyValue: (r,g,b)}（供前端「官方方案」预览回放；
        #: 与设备实际收到的 348B 载荷同源，保证屏幕预览和键盘同步）
        self.last_colors: Dict[int, RGB] = {}

    def set_mode(self, mode: int) -> None:
        mode = int(mode)
        self.mode = mode if mode in IMPLEMENTED_MODES else 13
        self.st["mode"] = self.mode

    def set_amplitude(self, amplitude_ui: int) -> None:
        self.st["amplitudeUI"] = _clamp(int(amplitude_ui), 1, 100)

    def set_backmode(self, backmode: int, brightness: int) -> None:
        """热更新官方背景参数（backmode 0..11 / 亮度 10..100）。"""
        self.st["backmode"] = int(_clamp(int(backmode), 0, 11))
        self.st["backmodeBrightness"] = int(_clamp(int(brightness), 10, 100))

    def tick(self, amp1000: int) -> bytes:
        """喂当前总振幅（0..1000），返回 348 字节逐键载荷。"""
        if amp1000 > 0:
            self._silence = 0
            self.st["amp"] = min(1.0, amp1000 / 1000.0)
        else:
            self._silence += 1
            if self._silence >= 5:  # 官方 C=5：连续 5 tick 静音才归零
                self.st["amp"] = 0.0
        self.st["huePhase"] = (self.st["huePhase"] + 0.01) % 1.0
        grid = _render_frame(self.lay, self.st, self.mode)
        colors: Dict[int, RGB] = {}
        for cell in self.lay["visible"]:
            c = grid[cell["row"]][cell["col"]] if cell["col"] < len(grid[cell["row"]]) else (0, 0, 0)
            colors[cell["value"]] = c
        self.last_colors = colors
        return lighting.build_frame_payload(colors)


# ----------------------------------------------------------------------
# 音频分析（官方 K7/Nse ♂ 3 段 Pse + 32 段可视化频谱）
# ----------------------------------------------------------------------
class Analyzer:
    def __init__(self, sample_rate: int = 48000, n_fft: int = 2048):
        self.sample_rate = int(sample_rate)
        self.n_fft = int(n_fft)
        self.window = np.hanning(n_fft).astype(np.float32)
        self.z = _AMP_FLOOR
        self.bases = [_AMP_FLOOR, _AMP_FLOOR, _AMP_FLOOR]
        self.freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)
        self._ranges = [
            (self.freqs >= 20) & (self.freqs < 250),
            (self.freqs >= 250) & (self.freqs < 4000),
            (self.freqs >= 4000) & (self.freqs < 20000),
        ]
        # 32 段对数频谱（给前端可视化用）
        self.n_bands32 = 32
        self._band_edges = np.geomspace(20.0, 20000.0, self.n_bands32 + 1)
        self._bands32_ranges = [
            (self.freqs >= self._band_edges[i]) & (self.freqs < self._band_edges[i + 1])
            for i in range(self.n_bands32)
        ]
        self._base32 = [_AMP_FLOOR] * self.n_bands32
        self.bands32 = [0.0] * self.n_bands32

    def _norm32(self, spectrum: np.ndarray) -> list:
        out = []
        for i, rng in enumerate(self._bands32_ranges):
            seg = spectrum[rng]
            e = float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0
            base = self._base32[i]
            r = _AMP_ATTACK if e > base else _AMP_DECAY
            base = max(base * (1 - r) + e * r, _AMP_FLOOR)
            self._base32[i] = base
            v = min(1000, int(round(e / base * 1000)))
            out.append(0.0 if v <= 5 else v / 1000.0)
        self.bands32 = out
        return out

    def analyze(self, samples: np.ndarray) -> dict:
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size < self.n_fft:
            x = np.pad(x, (0, self.n_fft - x.size))
        elif x.size > self.n_fft:
            x = x[-self.n_fft:]
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
        raw = 0.6 * peak + 0.4 * rms
        if raw > self.z:
            self.z = self.z * 0.7 + raw * 0.3
        else:
            self.z = self.z * 0.992 + raw * 0.008
        self.z = max(self.z, _AMP_FLOOR)
        amp = min(1000, int(round(raw / self.z * 1000)))
        if amp <= _AMP_GATE:
            amp = 0
        spectrum = np.abs(np.fft.rfft(x * self.window)) / (self.n_fft / 2.0)
        bands = []
        for i, rng in enumerate(self._ranges):
            seg = spectrum[rng]
            e = float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0
            base = self.bases[i]
            r = _AMP_ATTACK if e > base else _AMP_DECAY
            base = max(base * (1 - r) + e * r, _AMP_FLOOR)
            self.bases[i] = base
            v = min(1000, int(round(e / base * 1000)))
            bands.append(0.0 if v <= 5 else v / 1000.0)
        bands32 = self._norm32(spectrum)
        return {
            "amp": amp / 1000.0,
            "amp1000": amp,
            "bands": bands,
            "bands32": bands32,
            "spectrum": spectrum,
            "peak": peak,
            "rms": rms,
        }


# ----------------------------------------------------------------------
# 音频采集
# ----------------------------------------------------------------------
class AudioCapture:
    """系统输出回环采集（Windows: soundcard WASAPI / Linux: parec）。

    关键：采集在**独立线程**里持续读取小片段（默认 512 帧 ≈ 10.7ms）写入环形缓冲，
    主循环每 50ms 取最新 2048 帧做 FFT。否则主循环里同步 record(2048) 一次就要 43ms，
    帧率会被音频读卡到 ~11fps（真机实测）。
    """

    def __init__(self, device_id: Optional[str] = None, samplerate: int = 48000,
                 chunk: int = 512):
        self.device_id = device_id
        self.samplerate = int(samplerate)
        self.chunk = max(128, int(chunk))
        self._impl = None
        self._proc = None
        self.system = platform.system()
        self._buf = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error: Optional[str] = None

    # ------------------------------------------------- 设备打开/单次读取
    def _open_impl(self):
        if self.system == "Windows":
            import soundcard as sc  # type: ignore

            if self.device_id:
                mic = sc.get_microphone(id=self.device_id, include_loopback=True)
            else:
                spk = sc.default_speaker()
                mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
            rec = mic.recorder(samplerate=self.samplerate)
            rec.__enter__()
            self._impl = rec
        elif self.system == "Linux":
            device = self.device_id or "@DEFAULT_MONITOR@"
            self._proc = subprocess.Popen(
                ["parec", "--format=float32le", f"--rate={self.samplerate}",
                 "--channels=2", f"--device={device}"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        else:
            raise MK87Error(f"当前平台不支持系统音频采集: {self.system}")

    def _read_impl(self, frames: int) -> np.ndarray:
        if self.system == "Windows":
            data = self._impl.record(numframes=frames)
            if getattr(data, "ndim", 1) > 1:
                data = data.mean(axis=1)
            return np.asarray(data, dtype=np.float32)
        need = frames * 2 * 4  # 2ch float32
        buf = self._proc.stdout.read(need) if self._proc.stdout else b""
        if not buf:
            return np.zeros(frames, dtype=np.float32)
        return np.frombuffer(buf, dtype="<f4").reshape(-1, 2).mean(axis=1).astype(np.float32)

    def _close_impl(self):
        if self._impl is not None:
            try:
                self._impl.__exit__(None, None, None)
            except Exception:
                pass
            self._impl = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None

    # ------------------------------------------------- 采集线程
    def _reader_loop(self) -> None:
        try:
            if self.system == "Windows":
                try:
                    import ctypes

                    ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
                except Exception:
                    pass
            self._open_impl()
            self._ready.set()
            while not self._stop.is_set():
                try:
                    data = self._read_impl(self.chunk)
                except Exception as exc:  # noqa: BLE001
                    self._error = str(exc)
                    break
                if data.size:
                    with self._lock:
                        self._buf = np.concatenate((self._buf, data))[-8192:]
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._ready.set()
        finally:
            self._close_impl()

    def open(self):
        self._stop.clear()
        self._error = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._reader_loop, name="mk87-audio", daemon=True)
        self._thread.start()
        # 等音频设备真正打开再返回：失败要立刻报错，不能"假装成功"
        if not self._ready.wait(timeout=5.0):
            self._stop.set()
            raise MK87Error("音频设备打开超时（无响应）")
        if self._error:
            self._stop.set()
            raise MK87Error(f"音频采集打开失败（设备: {self.device_id or '默认输出'}）：{self._error}")

    def read(self, frames: int = 2048) -> np.ndarray:
        with self._lock:
            if self._error:
                raise MK87Error(f"音频采集中断: {self._error}")
            if self._buf.size >= frames:
                return self._buf[-frames:].copy()
            out = np.zeros(frames, dtype=np.float32)
            if self._buf.size:
                out[-self._buf.size:] = self._buf
            return out

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None


def list_devices() -> List[dict]:
    """列出可用于音乐律动的音频设备（默认：系统输出回环）。"""
    system = platform.system()
    if system == "Windows":
        try:
            # WASAPI/COM 需要在该线程初始化，否则返回 0x800401f0（CO_E_NOTINITIALIZED）
            import ctypes

            try:
                ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
            except Exception:
                pass
            import soundcard as sc  # type: ignore

            default_speaker = sc.default_speaker()
            out = []
            for mic in sc.all_microphones(include_loopback=True):
                is_loop = bool(getattr(mic, "isloopback", False))
                out.append({
                    "id": str(mic.id),
                    "name": mic.name,
                    "loopback": is_loop,
                    "default": is_loop and default_speaker is not None
                    and default_speaker.name in mic.name,
                })
            return out
        except Exception as exc:  # noqa: BLE001
            return [{"id": None, "name": f"(音频设备不可用: {exc})", "loopback": False, "default": True}]
    if system == "Linux":
        try:
            res = subprocess.run(["pactl", "list", "short", "sources"],
                                 capture_output=True, text=True, timeout=3)
            out = []
            for line in res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    name = parts[1]
                    out.append({
                        "id": name,
                        "name": name,
                        "loopback": name.endswith(".monitor"),
                        "default": name.startswith("@DEFAULT") or ".monitor" in name,
                    })
            return out
        except Exception as exc:  # noqa: BLE001
            return [{"id": None, "name": f"(pactl 不可用: {exc})", "loopback": False, "default": True}]
    return []


# ----------------------------------------------------------------------
# ACK 清道夫：音乐帧流 140 包/秒的 ACK 必须被读走，否则固件输入缓冲满后
# 连 WriteFile 都会被拖慢（真机实测：不读 ACK 时帧率掉到 6fps 且越来越慢）。
# 但 hidapi 的 read(timeout) 在空队列上会卡 50~400ms（CancelIoEx 延迟），
# 所以用独立线程持续阻塞读并丢弃，绝不阻塞发送线程。
# ----------------------------------------------------------------------
class AckDrainer:
    def __init__(self, device):
        self.device = device
        self.count = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.count = 0
        self._thread = threading.Thread(target=self._run, name="mk87-ack-drain", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        iface = self.device.protocol.iface
        while not self._stop.is_set():
            try:
                r = iface.read_report(timeout=0.1)
            except Exception:  # noqa: BLE001
                break
            if r:
                self.count += 1

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None


# ----------------------------------------------------------------------
# 播放器
# ----------------------------------------------------------------------
class MusicPlayer:
    def __init__(self, device):
        self.device = device
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.mode = 13
        self.requested_mode = 13
        self.amplitude_ui = 50
        self.sensitivity = 1.0
        self.backmode = 0
        self.backmode_brightness = 100
        self.fps = 20
        self.device_id: Optional[str] = None
        self.level = 0.0
        self.bands: List[float] = [0.0, 0.0, 0.0]
        self.levels32: List[float] = [0.0] * 32
        self.frames = 0
        self.errors = 0
        self.last_error = ""
        self.last_payload: bytes = b""
        #: 最近一帧逐键颜色（与 last_payload 同源，供前端官方方案预览）
        self.last_colors: Dict[int, RGB] = {}
        self._snapshot: Optional[dict] = None
        self._engine: Optional[MusicEngine] = None
        self._drainer: Optional[AckDrainer] = None
        self._sender = None
        #: ACK 处理方式：none=不读（依赖独立清道夫）、drainer=独立线程、sync=每帧同步读 2 个
        self.ack_mode = "none"
        self.timing = {"read": 0.0, "analyze": 0.0, "send": 0.0, "frames": 0}
        self._ready = threading.Event()
        self._start_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, device_id: Optional[str] = None, mode: Optional[int] = None,
              style: Optional[str] = None, sensitivity: float = 1.0,
              fps: int = 20, backmode: int = 0, backmode_brightness: int = 100,
              amplitude: Optional[int] = None) -> dict:
        if self.device.transport != "usb":
            raise MK87Error("音乐律动仅支持 USB 有线连接（2.4G 官方不支持）")
        self.stop()
        if mode is None:
            mode = STYLE_TO_MODE.get(str(style or ""), 13)
        self.requested_mode = int(mode)
        self.mode = int(mode) if int(mode) in IMPLEMENTED_MODES else 13
        self.sensitivity = max(0.1, min(4.0, float(sensitivity)))
        # 官方 amplitude(1..100)：默认 50；显式传 amplitude 时直接采用，否则由灵敏度换算
        if amplitude is not None:
            self.amplitude_ui = int(_clamp(int(amplitude), 1, 100))
        else:
            self.amplitude_ui = int(_clamp(round(self.sensitivity * 50), 10, 100))
        # 官方背景参数：backmode(0..11) / backmodeBrightness(10..100)
        self.backmode = int(_clamp(int(backmode or 0), 0, 11))
        self.backmode_brightness = int(_clamp(int(backmode_brightness or 100), 10, 100))
        self.fps = max(5, min(40, int(fps)))
        self.device_id = device_id
        self.errors = 0
        self.last_error = ""
        self.frames = 0
        self.levels32 = [0.0] * 32
        self.last_colors = {}
        self._stop.clear()
        self._ready = threading.Event()
        self._start_error = None
        self.timing = {"read": 0.0, "analyze": 0.0, "send": 0.0, "frames": 0}
        self._thread = threading.Thread(target=self._loop, name="mk87-music", daemon=True)
        self._thread.start()
        log.info("音乐律动启动: mode=%s(请求 %s) amplitude=%s backmode=%s bb=%s fps=%s device=%s",
                 self.mode, self.requested_mode, self.amplitude_ui,
                 self.backmode, self.backmode_brightness, self.fps, device_id or "默认输出")
        # 等音频引擎真正打开再返回：失败要立刻报错，不能"假装成功"
        if not self._ready.wait(timeout=5.0):
            self._stop.set()
            raise MK87Error("音乐引擎启动超时（音频设备无响应）")
        if self._start_error:
            self._stop.set()
            raise MK87Error(f"音频采集打开失败（设备: {device_id or '默认输出'}）：{self._start_error}")
        return self.status()

    def _loop(self) -> None:
        capture = None
        try:
            # WASAPI/COM 需要线程内初始化（soundcard 打开设备/循环采集依赖 COM）
            if platform.system() == "Windows":
                try:
                    import ctypes

                    ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
                except Exception:
                    pass
            capture = AudioCapture(self.device_id)
            capture.open()
            analyzer = Analyzer(capture.samplerate)
            self._engine = MusicEngine(self.mode, amplitude_ui=self.amplitude_ui,
                                       backmode=self.backmode,
                                       backmode_brightness=self.backmode_brightness)
            self._snapshot = lighting.ensure_frame_mode(self.device)
            # 帧流走原生通道（Windows）：hidapi 逐包 ACK 只能到 ~10fps，原生通道实测 20fps
            self._sender = lighting.FrameSender(self.device)
            self._ready.set()
        except Exception as exc:  # noqa: BLE001
            self._start_error = str(exc)
            self.errors += 1
            self.last_error = f"音频采集打开失败: {exc}"
            self._ready.set()
            if capture is not None:
                try:
                    capture.close()
                except Exception:
                    pass
            return
        next_t = time.time()
        self.timing = {"read": 0.0, "analyze": 0.0, "send": 0.0, "frames": 0}
        try:
            while not self._stop.is_set():
                try:
                    t_a = time.perf_counter()
                    samples = capture.read(2048)
                    t_b = time.perf_counter()
                    analysis = analyzer.analyze(samples)
                    t_c = time.perf_counter()
                    self.level = analysis["amp"]
                    self.bands = analysis["bands"]
                    self.levels32 = analysis.get("bands32") or []
                    payload = self._engine.tick(analysis["amp1000"]) if self._engine else b""
                    # 记录本帧逐键颜色：前端「官方方案」预览直接回放（与设备实发帧同源）
                    self.last_colors = self._engine.last_colors if self._engine else {}
                    # 音乐帧流 20fps：原生通道逐包等 ACK（单包 0.5~3ms），不再走 hidapi
                    if self._sender is not None:
                        self._sender.send(payload, self.frames & 0xFF, wait_ack=True,
                                          ack_timeout=0.006)
                    t_d = time.perf_counter()
                    tm = self.timing
                    tm["read"] += t_b - t_a
                    tm["analyze"] += t_c - t_b
                    tm["send"] += t_d - t_c
                    tm["frames"] += 1
                    self.last_payload = payload
                    self.frames += 1
                    if self.frames % 200 == 0:
                        n = max(1, self.timing.get("frames", 1))
                        log.debug("音乐帧流: %d 帧, 平均 send=%.1fms analyze=%.1fms, amp=%.2f",
                                  self.frames, self.timing["send"] / n * 1000,
                                  self.timing["analyze"] / n * 1000, self.level)
                except MK87Error:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = str(exc)
                    log.warning("音乐帧发送异常 #%d: %s", self.errors, exc)
                    if self.errors > 50:
                        break
                # 周期每帧重算：支持运行中热更新 fps
                period = 1.0 / max(5, min(40, int(self.fps or 20)))
                next_t += period
                sleep = next_t - time.time()
                if sleep < -period:
                    next_t = time.time()
                elif sleep > 0:
                    time.sleep(sleep)
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = str(exc)
        finally:
            self.last_colors = {}
            try:
                capture.close()
            except Exception:
                pass
            if self._drainer is not None:
                self._drainer.stop()
                self._drainer = None
            if self._sender is not None:
                self._sender.close()
                self._sender = None
            if self._snapshot:
                lighting.restore_effect(self.device, self._snapshot["before"])
                self._snapshot = None

    def update(self, mode: Optional[int] = None, amplitude: Optional[int] = None,
               backmode: Optional[int] = None, backmode_brightness: Optional[int] = None,
               fps: Optional[int] = None) -> dict:
        """运行中热更新参数（显示模式 / 背景模式 / 背景亮度 / 振幅 / 帧率），不打断音频采集。"""
        engine = self._engine
        if engine is None or not self.running:
            raise MK87Error("音乐律动未在运行，无法热更新参数")
        if mode is not None:
            self.requested_mode = int(mode)
            engine.set_mode(int(mode))
            self.mode = engine.mode
        if amplitude is not None:
            self.amplitude_ui = int(_clamp(int(amplitude), 1, 100))
            engine.set_amplitude(self.amplitude_ui)
        if backmode is not None or backmode_brightness is not None:
            engine.set_backmode(
                self.backmode if backmode is None else backmode,
                self.backmode_brightness if backmode_brightness is None else backmode_brightness,
            )
            self.backmode = int(engine.st["backmode"])
            self.backmode_brightness = int(engine.st["backmodeBrightness"])
        if fps is not None:
            self.fps = max(5, min(40, int(fps)))
        log.info("音乐律动热更新: mode=%s(请求 %s) backmode=%s bb=%s amp=%s fps=%s",
                 self.mode, self.requested_mode, self.backmode,
                 self.backmode_brightness, self.amplitude_ui, self.fps)
        return self.status()

    def stop(self) -> dict:
        if self.running:
            log.info("音乐律动停止: 共 %d 帧, %d 错误", self.frames, self.errors)
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        return self.status()

    def status(self) -> dict:
        tm = self.timing
        n = max(1, int(tm.get("frames", 0)))
        return {
            "running": self.running,
            "mode": self.mode,
            "requestedMode": self.requested_mode,
            "modes": MODES,
            "amplitude": self.amplitude_ui,
            "backmode": self.backmode,
            "backmodeBrightness": self.backmode_brightness,
            "implementedModes": sorted(IMPLEMENTED_MODES),
            "sensitivity": self.sensitivity,
            "fps": self.fps,
            "deviceId": self.device_id,
            "level": round(float(self.level), 3),
            "bands": [round(float(b), 3) for b in self.bands],
            "bands32": [round(float(b), 3) for b in self.levels32],
            # 官方方案预览：运行中返回当前帧逐键颜色 {slot: [r,g,b]}，未运行返回空对象
            "colors": ({str(int(slot)): [int(rgb[0]), int(rgb[1]), int(rgb[2])]
                        for slot, rgb in self.last_colors.items()} if self.running else {}),
            "frames": self.frames,
            "errors": self.errors,
            "lastError": self.last_error,
            "timing": {
                "readMs": round(tm.get("read", 0.0) / n * 1000, 2),
                "analyzeMs": round(tm.get("analyze", 0.0) / n * 1000, 2),
                "sendMs": round(tm.get("send", 0.0) / n * 1000, 2),
            },
            "supported": self.device.transport == "usb",
        }
