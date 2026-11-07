"""音乐律动（USB only）：系统音频采集 → 官方渲染器 → 0x32 逐键帧流。

协议真机结论（docs/music-rhythm.md §9 / TEST-REPORT §9）：
* 必须先 SET_LED_EFFECT 到自定义族 mode ∈ {20,21,128}，再发 cmd 0x32 逐键帧才显示；
* 一帧 = 87 键 × 4 字节 [keyValue, R, G, B]，按官方 keyList 行优先；USB 下 7 包/帧，
  20fps 稳定；原生帧率可选 15/20/30/60/66（官方 v1 实测 ≈66fps = 530.5 包/s ÷ 8 包/帧），
  动画按 dt_scale 归一到 20fps 基准，帧率不影响动效速度；
* 停发约 5 秒后固件回落到自定义表；本模块停止时会主动恢复进入前的灯效；
* 2.4G 官方不支持，仅 USB 可用。

渲染器：**逐行移植官方 bundle**（scripts/music_ref.js 已 31/31 自检通过），
不再使用早期自研的 spectrum/rainbow 等简化渲染（那种会点亮几乎全部按键，观感是"全亮"）。
官方模式号 → 渲染器（20 个模式全部可用）：
  13 = Se  Dance to the Beat（同心环扩散，默认）
  14 = Dust Glow Spiral（中心四色射线旋转）
  15 = Dormant Volcano（左/中/右三塔火山，无坐标表走官方柱状兜底）
  16 = Light Arrow Piercing（右侧光条 + 固定箭形点阵）
  17 = Firefly Trail（中心行正弦波 + 拖尾）
  18 = Light Cocoon Resonance（顶部/右列边框 + 对角光带）
  19 = Tuning Fork Vibration（左右音叉触须 + 随机抖动暗色拖尾）
  20 = Curvature Legacy Track（右侧向内的弯曲波形）
  21 = Row Wave Rhythm（逐行不等长柱 + 色相渐变）
  22 = Dual Heart Dance（官方内置双心坐标图案逐层点亮）
  1/2/4/5/6/7/8/9/10/11 = Fe 曲率频阶柱状 + 调色板（模式号即调色板：1 绿黄红分行、
    2 六色横条、4 径向色相、5 旋转单色、6/7/8/9/10/11 纯白/红/橙/黄/蓝/绿）
模式 100（屏光联动）仍回落到 13：官方把它交给插件 Music.exe 读屏计算，主机侧没有渲染器
（本工具自研屏幕同步待做）。

官方 v1 参数真值见 docs/music-v1-config.json：显示模式列表见 V1_DISPLAY_MODES（官方 v1
的 12 个 + 补回的 14~22，共 21 项）、背景模式 11 个、振幅 1–100（默认 30）、背景亮度
1–100（默认 100）；纯色/亮度公式由 capture/official_music_colors3.jsonl 采样反推
（probe/analyze_official_v1_modes.py）。

LED 颜色覆盖（本工具增强）：COLOR_SCHEMES 的 color id 只替换**动态多色**模式的
「色相来源」——1/2/4/5/13 与 14~22 共 14 个模式（见 COLOR_OVERLAY_MODES），
动画相位/径向角度/环相位/拖尾明暗全部保留；纯色模式 6~11 与背景不受影响。

音频分析：官方 K7/Nse（总振幅）+ 3 段 Pse + 32 段频谱（前端电平条用）。
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import math
import platform
import random
import subprocess
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import keymap, lighting, powerkeep
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
    4: ("曲率频阶", "Curvature Frequency Steps"),
    15: ("休眠火山", "Dormant Volcano"),
    16: ("光箭穿刺", "Light Arrow Piercing"),
    18: ("光茧共鸣", "Light Cocoon Resonance"),
    19: ("音叉振动", "Tuning Fork Vibration"),
    20: ("曲率传承", "Curvature Legacy Track"),
    21: ("行波节奏", "Row Wave Rhythm"),
    22: ("双心共舞", "Dual Heart Dance"),
    # 官方 v1 UI 的其余显示模式（文案取自 docs/music-v1-config.json）
    1: ("绿色/黄色/红色", "Green/Yellow/Red"),
    2: ("彩虹色", "Rainbow"),
    5: ("频谱循环", "Spectrum Cycle"),
    6: ("白色", "White"),
    7: ("红色", "Red"),
    8: ("橙色", "Orange"),
    9: ("黄色", "Yellow"),
    10: ("蓝色", "Blue"),
    11: ("绿色", "Green"),
}

#: 前端「当前方案」可选模式（本工具自己的组合，与官方 v1 下拉无关）
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
IMPLEMENTED_MODES = {
    1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22,
}

#: 「官方方案」显示模式下拉的 21 项：官方 v1 UI 的 12 个 + 研究阶段确认存在、
#: 但 v1 页面未暴露的 9 个（14~22，取自 docs/music-constants.json 的 v2 列表；
#: 渲染器本工具早已逐行移植）。顺序按产品要求，100（屏光联动）排最后。
V1_DISPLAY_MODES = [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10,
                    14, 15, 16, 17, 18, 19, 20, 21, 22, 100]

#: 其中主机侧已实现渲染器的 20 个：100（屏光联动）由官方 Music.exe 读屏计算，
#: 本工具尚未做自研屏幕同步，仍回落 13；「官方方案」下拉据此标注未移植。
V1_IMPLEMENTED_MODES = [m for m in V1_DISPLAY_MODES if m != 100]

#: 走官方 Fe（曲率频阶柱状合成包络）几何的显示模式：模式号同时就是调色板 id
#: （1=绿黄红分行 / 2=6 色横条 / 5=旋转单色 / 6..11=纯色）。
#: 依据：capture/official_music_colors3.jsonl 采样反推（见 probe/analyze_official_v1_modes.py）。
#: 注意：显示模式 4「曲率频阶」不在其中 —— 官方 v1 真值是 17 列频谱柱
#: （见 `_render_mode_4`，2026-11-03 重新采样确认）。
V1_STEP_MODES = (1, 2, 5, 6, 7, 8, 9, 10, 11)


# ----------------------------------------------------------------------
# 帧率 / 动画时间归一（本工具增强）
# ----------------------------------------------------------------------
#: 前端原生帧率控件：官方方案 20/60/66（官方 v1 实测 ≈66fps = 530.5 包/s ÷ 8 包/帧），
#: 当前方案 15/20/30。后端不限制只能取这几个值（5..66 均可），但 UI 只提供这些档。
FPS_CHOICES = (15, 20, 30, 60, 66)
DEFAULT_FPS = 20
FPS_MIN, FPS_MAX = 5, 66
#: 动画基准帧率：所有渲染器的「每 tick 自增」常量都按官方 20fps 标定。
BASE_FPS = 20.0
#: 动画步长钳制：20fps → 1.0；66fps → 0.303；卡顿/挂起时最多按 3 个基准帧推进一次。
DT_SCALE_MIN, DT_SCALE_MAX = 0.2, 3.0
#: 逐包 ACK 与 burst 的分界：真机实测 7 包逐包 ACK 平均 15.5ms/帧（最大 20.06ms），
#: 30fps 的 33.3ms 预算有余量；66fps 的 15.15ms 预算不够 → ≥60fps 改走 burst + 帧末 drain。
BURST_MIN_FPS = 60
#: 实测帧率滚动窗口（秒）与最小可计算跨度（太短会有夸张抖动）。
MEASURED_FPS_WINDOW = 2.0
MEASURED_FPS_MIN_SPAN = 0.25
#: ≥60fps 的发送策略（真机实测 2026-11-03，MK87/USB fw1.19）：
#:   * 帧末同步 drain 7 个回包：send ≈ 19.8ms/帧 > 66fps 的 15.15ms 预算，实测掉到 45.96fps；
#:   * 连写 7 包 + ACK 清道夫线程异步读回包：send ≈ 8.9ms/帧，实测 66.14fps（lateFrames=0）。
#: 所以 ≥60fps 用「burst + 异步清道夫」，只有在清道夫起不来时才回退帧末同步 drain。
BURST_SYNC_DRAIN = 7


# ----------------------------------------------------------------------
# 会话守护 / 自动恢复（v0.1.8.4，2026-11-06 用户实机事故）
# ----------------------------------------------------------------------
# 事故链条（用户 Windows 机器日志 + py-spy 线程栈）：
#   合盖进入连接待机（modern standby）→ USB HID 挂起 → 原生 WriteFile 在
#   `mk87-music` 线程里**永久阻塞** → 帧流停在最后一帧、音频采集线程同时卡在
#   WASAPI 里 → 后端 `running` 仍为 True，界面一直显示「律动中」、电平条冻结；
#   另一条路径是 WriteFile 立刻返回 995，累计 50+ 次错误后线程静默退出。
# 因此音乐律动改为「监督循环」：任何一次会话（音频采集 + 帧流）中断都自动重建，
# 键盘掉线时等待自动重连后继续播，用户点「停止」才真正结束。
#: 音频采集「无新数据」超过该秒数 → 判定采集卡死（WASAPI 在系统待机、默认输出
#: 设备被拔掉/切换后可能永久阻塞在 read()，但不会报错，只能靠数据新鲜度发现）。
AUDIO_STALL_TIMEOUT = 2.0
#: 连续发送失败多少次判定 HID 通道不可用 → 重建会话（每次单包写超时 ~0.25s）。
SEND_ERROR_LIMIT = 5
#: 自动恢复重试退避（秒）：0.5 → 1 → 2 → 5 封顶；键盘离线时等待 monitor 线程重连。
RECOVER_MIN_DELAY, RECOVER_MAX_DELAY = 0.5, 5.0

# ----------------------------------------------------------------------
# 帧流看门狗（v0.1.8.6，2026-11-07 实机：切换 Win/Mac 模式 → USB 重新枚举）
# ----------------------------------------------------------------------
# 事故现象：连续 WriteFile 1167 后 HID 通道失效，设备 6s 后重连成功，但音乐律动
# 既没有「自动恢复」日志也不再出帧 —— 界面停在「律动中」，直到用户手动重开。
# 根因方向：只看「连续发送异常次数」不足以覆盖所有卡死形态 —— 一旦发送调用本身
# 卡在内核 IO 里（不再返回、也不再抛异常），主循环既不出帧也不进入 send-error
# 分支，监督循环永远等不到「会话结束」，表现为静默停更/线程卡死。
# 因此再加一层独立看门狗：主循环还活着（running=True）但超过阈值没有「成功下发帧」，
# 就由看门狗线程判定卡死 → 标记会话重建（主循环下一轮开头退出会话）；
# 若主循环连「退出会话」都做不到（真卡在 HID 调用里），宽限期后从旁路强关发送通道，
# 让阻塞的 write/read 立刻以异常返回，监督循环随即重建会话。
#: 超过该秒数没有成功下发帧（且健康状态为 ok）→ 判定帧流卡死。
FRAME_STALL_TIMEOUT = 2.0
#: 看门狗检查周期（秒）；同时也是「卡死 → 重建」的最小延迟。
WATCHDOG_INTERVAL = 0.5
#: 看门狗判定卡死后，等主循环自己退出会话的宽限期（秒）；超时则旁路强关发送通道。
WATCHDOG_HARD_GRACE = 3.0
#: 键盘掉线（USB 重新枚举）时的重连轮询间隔（秒）。状态层 monitor 线程负责重连，
#: 这里短轮询保证「重连完成 → 重建会话」的延迟 ≤ 1s（需求：≤5s 内恢复）。
DEVICE_WAIT_POLL = 0.25
#: 关闭旧会话资源的等待上限（秒）：设备在线时给在途 IO 收割留时间；
#: 设备已断开时快速失败，绝不能把音乐监督线程卡在死句柄上。
CLOSE_SENDER_TIMEOUT = 0.8
CLOSE_SENDER_TIMEOUT_OFFLINE = 0.25
CLOSE_CAPTURE_TIMEOUT = 1.2
CLOSE_CAPTURE_TIMEOUT_OFFLINE = 0.3


def _clamp_fps(fps) -> int:
    """帧率归一（start / update 共用）：``max(5, min(66, int(fps)))``。

    * 15/20/30/60/66（前端原生帧率控件）原样保留；
    * 5..66 内的其它整数也保留（兼容 CLI/手写配置，UI 不提供）；
    * 越界值钳到 5 / 66；**无法解析为整数**（None / "abc" / nan）回落默认 20。
    """
    try:
        value = int(fps)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_FPS
    return max(FPS_MIN, min(FPS_MAX, value))


def _dt_scale(dt: Optional[float]) -> float:
    """实际帧间隔（秒）→ 动画时间步长：``dt * 20`` 并钳制到 0.2~3.0。

    ``1.0`` 表示「标准 20fps tick」；66fps 传 ``1/66`` → ≈0.303，即每帧只推进
    0.303 个基准 tick，累计 1 秒仍是 20 个基准 tick —— 动画速度与帧率解耦。
    """
    try:
        seconds = float(dt)
    except (TypeError, ValueError):
        seconds = 1.0 / BASE_FPS
    return max(DT_SCALE_MIN, min(DT_SCALE_MAX, seconds * BASE_FPS))


def _smooth(prev: float, target: float, alpha: float, dt: float) -> float:
    """一阶低通（AMP attack/decay 平滑）。

    dt=1 时保持原算术顺序 ``prev + (target-prev)*alpha``，保证 20fps 输出逐位一致；
    dt≠1 时把每 tick 系数换算成等效的指数时间常数，66fps 的平滑速度与 20fps 相同。
    """
    if dt == 1.0:
        return prev + (target - prev) * alpha
    k = 1.0 - (1.0 - alpha) ** dt
    return prev + (target - prev) * k


def _advance(value: float, step: float, dt: float, wrap: Optional[float] = None) -> float:
    """相位推进：dt=1 时与原 ``(value + step) % wrap`` 逐位一致。"""
    result = value + step * dt
    if wrap is not None:
        result %= wrap
    return result


def _agc(prev: float, target: float, rate: float, dt: float) -> float:
    """自适应增益（Analyzer 的 z / 3 段 / 32 段 base）一阶跟踪。

    dt=1 时保留原算术顺序 ``prev*(1-rate) + target*rate``（逐位一致）；dt≠1 时按
    指数时间常数换算，66fps 的 AGC attack/decay 速度与 20fps 相同。
    """
    if dt == 1.0:
        return prev * (1 - rate) + target * rate
    k = 1.0 - (1.0 - rate) ** dt
    return prev * (1 - k) + target * k


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
# LED 颜色覆盖（本工具增强；「官方方案」的第三个下拉）
# ----------------------------------------------------------------------
#: 颜色方案表：id → stops（#RRGGBB）。**id 与色值必须与前端 web/js/data/music.js
#: 的 OFFICIAL_COLOR_SCHEMES 完全一致**（前端按同一张表画下拉与预览条）。
#: default = 不覆盖（走官方采样配色，输出与改动前逐字节一致）。
COLOR_SCHEMES = (
    ("default", ()),
    ("ice", ("#00E5FF",)),
    ("violet", ("#B36CFF",)),
    ("pink", ("#FF2E88",)),
    ("lime", ("#A8FF3E",)),
    ("amber", ("#FF6A00",)),
    ("sakura", ("#FF7AB6", "#B36CFF")),
    ("aurora", ("#3EFF9A", "#00E5FF", "#7A5CFF")),
    ("sunset", ("#FFC400", "#FF6A00", "#FF2E88")),
    ("icefire", ("#00E5FF", "#FEFEFE", "#FF6A00")),
)
COLOR_IDS = tuple(cid for cid, _stops in COLOR_SCHEMES)
DEFAULT_COLOR = "default"
#: 颜色覆盖只作用于**动态多色**模式（本工具增强，v0.1.4 起覆盖全部 14 个）：
#:   1 = 绿黄红分行 / 2 = 彩虹六色横条 / 4 = 径向色相频谱柱 / 5 = 旋转单色 /
#:   13 = 同心环；
#:   14~22 = 官方渲染器（4 色射线 / 三塔火山 / 光箭 / 萤火 / 光茧 / 音叉 /
#:   曲率传承 / 行波 / 双心）——这些模式的颜色同样只由色相决定，按同一
#:   「hue → 调色板位置」映射取样，动画相位/几何/明暗层次原样保留。
#: 纯色模式 6~11（官方采样色）保持原样；背景（backmode）永远不受影响。
COLOR_OVERLAY_MODES = frozenset({1, 2, 4, 5, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22})


def _hex_rgb(value: str) -> RGB:
    """``#RRGGBB`` → (r, g, b)。"""
    s = value.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def normalize_color_id(color) -> str:
    """颜色 id 归一化：未知/空值回落 default（未知值打 debug 日志，不抛错）。"""
    cid = str(color or "").strip().lower()
    if cid in COLOR_IDS:
        return cid
    if cid:
        log.debug("未知 LED 颜色方案 %r，回落 %s", color, DEFAULT_COLOR)
    return DEFAULT_COLOR


class Palette:
    """用户调色板：把「原始配色位置」t∈[0,1] 映射到 stops 上的插值颜色。

    颜色覆盖层只替换**色相来源**：各渲染器仍按原动画推进（mode 4 的径向色相
    旋转、mode 5 的相位推进、mode 13 的环相位…），算法本身不变，只把
    ``_hsv(hue, 1, 1)`` 换成 ``Palette.at(hue / 360)``。于是 t 天然就是「原始
    调色板位置」，动画相位与径向角度一点不丢。
    """

    __slots__ = ("id", "stops", "_rgb")

    def __init__(self, color_id: str) -> None:
        for cid, stops in COLOR_SCHEMES:
            if cid == color_id:
                if not stops:
                    raise ValueError("default 没有调色板（不覆盖，请用 palette_for）")
                self.id = cid
                self.stops = stops
                self._rgb = tuple(_hex_rgb(s) for s in stops)
                return
        raise ValueError(f"未知颜色方案: {color_id}")

    def at(self, t: float) -> RGB:
        """在 stops 上按位置 t（0..1，sRGB 线性插值）取样；单色 id 恒定。"""
        rgb = self._rgb
        if len(rgb) == 1:
            return rgb[0]
        pos = _clamp(float(t), 0.0, 1.0) * (len(rgb) - 1)
        i = int(math.floor(pos))
        if i >= len(rgb) - 1:
            return rgb[-1]
        f = pos - i
        a, b = rgb[i], rgb[i + 1]
        return (_rnd(a[0] + (b[0] - a[0]) * f),
                _rnd(a[1] + (b[1] - a[1]) * f),
                _rnd(a[2] + (b[2] - a[2]) * f))


def palette_for(color) -> Optional[Palette]:
    """颜色 id → Palette；default 返回 None（= 不覆盖，走官方原路径）。"""
    cid = normalize_color_id(color)
    if cid == DEFAULT_COLOR:
        return None
    return Palette(cid)


def _hue_color(hue: float, pal: Optional[Palette] = None) -> RGB:
    """色相 → RGB：默认走官方 kV 色环；有用户调色板时按 hue/360 在 stops 上取样。"""
    hue = float(hue) % 360.0
    if pal is None:
        return _hsv(hue, 1.0, 1.0)
    return pal.at(hue / 360.0)


def _scaled_rgb(color: RGB, scale: int) -> RGB:
    """按官方亮度系数缩放一个 RGB（与 _fill_solid/_fill_row_bands 同一公式）。"""
    return (_scale_channel(color[0], scale), _scale_channel(color[1], scale),
            _scale_channel(color[2], scale))


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


def _brightness_scale(brightness_pct: float) -> int:
    """官方亮度缩放系数 0..255：``int(bb*255/100)``（截断）。

    采样验证（capture/official_music_colors3.jsonl D 组，背景红 bb=100/50/20）：
    → 254/126/50，只有「系数 255/127/51 + 通道位运算」这组能同时对上；
    round(bb*2.55) 在 bb=50 会给 128 → 127（错），故必须截断。
    """
    return int(float(brightness_pct) * 255.0 / 100.0)


def _scale_channel(channel: int, scale: int) -> int:
    """官方通道缩放：``(通道 * 系数) >> 8``（等价于 floor(c*n/256)）。

    采样验证：纯白 bb=100 → FE（不是 FF）、橙 8 号色 → FE3F00（不是 FE4000）、
    红 bb=50 → 7E、bb=20 → 32。JS 的 Math.round 会给出 FE4000，与实际不符。
    """
    return (int(channel) * int(scale)) >> 8


def _fill_solid(grid, color: RGB, brightness_pct: float) -> None:
    n = _brightness_scale(brightness_pct)
    c = (_scale_channel(color[0], n), _scale_channel(color[1], n), _scale_channel(color[2], n))
    for row in grid:
        for i in range(len(row)):
            row[i] = c


def _fill_row_bands(grid, colors: List[RGB], brightness_pct: float,
                    pal: Optional[Palette] = None) -> None:
    """横向分段（显示模式 1/2 与背景模式 1/2 共用）。

    pal 不为 None 时不再逐段用官方色，而是按「该行在原调色板里的纵向位置」
    （row_idx / (rows-1)）在新调色板上取样：单色 id → 整屏统一色（保留官方
    亮度缩放），渐变 id → 上下铺开的渐变。默认档（pal=None）走原逻辑不变。
    """
    n = _brightness_scale(brightness_pct)
    rows = len(grid)
    per = rows // len(colors)
    extra = rows % len(colors)
    row_idx = 0
    for ci, color in enumerate(colors):
        cnt = per + (1 if ci < extra else 0)
        for _ in range(cnt):
            if row_idx >= rows:
                break
            if pal is None:
                c = _scaled_rgb(color, n)
            else:
                c = _scaled_rgb(pal.at(row_idx / (rows - 1) if rows > 1 else 0.0), n)
            for col in range(len(grid[row_idx])):
                grid[row_idx][col] = c
            row_idx += 1


def _fill_radial_hue(grid, center_row: int, center_col: int, hue_phase: float,
                     pal: Optional[Palette] = None) -> None:
    rows, cols = len(grid), len(grid[0])
    for r in range(rows):
        for c in range(cols):
            angle = math.atan2(r - center_row, c - center_col)
            hue = hue_phase + ((180 + (180 / math.pi) * angle) % 360)
            if hue < 0:
                hue += 360
            if hue >= 360:
                hue -= 360
            # 径向色相是「按角度取色」：有用户调色板时按同一角度位置在 stops 上取样，
            # huePhase 推进（色相旋转）原样保留。
            grid[r][c] = _hue_color(hue, pal)


def _fill_solid_hue(grid, hue_phase: float, brightness_pct: float,
                    pal: Optional[Palette] = None) -> None:
    """整屏单色，色相随时间旋转（官方 v1 显示模式 5 / 背景模式 5「频谱循环」）。

    hue_phase 是 0..1 的相位（引擎每 tick +0.01 → 5s 转一圈）：
    采样里同一段内整帧只有一种颜色、颜色逐帧走完整个色环（AA00FF → 006AFF → …），
    且饱和色最大通道是 FF（满值），故 value = bb/100。
    有用户调色板时：整屏颜色 = 在 stops 上按 hue 位置取样后乘同一个亮度 value，
    相位推进（颜色循环）不变。
    """
    hue = (float(hue_phase) * 360.0) % 360.0
    value = _clamp(float(brightness_pct) / 100.0, 0.0, 1.0)
    if pal is None:
        c = _hsv(hue, 1.0, value)
    else:
        src = pal.at(hue / 360.0)
        c = (_rnd(src[0] * value), _rnd(src[1] * value), _rnd(src[2] * value))
    for row in grid:
        for i in range(len(row)):
            row[i] = c


def _apply_background(grid, backmode: int, brightness_pct: float, st: dict,
                      pal: Optional[Palette] = None) -> None:
    """官方 _e：调色板（背景模式与「曲率频阶」显示模式的共用颜色方案）。

    backmode：0 = 不画、6..11 纯色、1/2 横向分段、4 径向色相、5 旋转纯色。
    显示模式 1/2/5/6..11 也把显示模式号当调色板 id 传进来（官方同一个函数）。

    pal 只在「显示模式把模式号当调色板」时由 `_render_mode_steps` 传入（颜色覆盖）；
    真正的背景调用永远不传 pal —— 纯色 6..11、背景配色都不受颜色覆盖影响。
    """
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
        _fill_row_bands(grid, [(0, 255, 0), (255, 255, 0), (255, 0, 0)],
                        brightness_pct, pal)
    elif backmode == 2:
        _fill_row_bands(grid, [
            (255, 0, 255), (0, 0, 255), (0, 255, 255),
            (0, 255, 0), (255, 255, 0), (255, 0, 0),
        ], brightness_pct, pal)
    elif backmode == 4:
        _fill_radial_hue(grid, st["centerRow"], st["centerCol"], st["huePhase"], pal)
    elif backmode == 5:
        _fill_solid_hue(grid, st["huePhase"], brightness_pct, pal)
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


def _render_mode_steps(grid, mode: int, lay: dict, st: dict,
                       pal: Optional[Palette] = None) -> None:
    """官方 Fe（曲率频阶柱状）+ 调色板 = 显示模式号。

    官方 v1 的 1/2/5/6/7/8/9/10/11 共用这一种几何：包络柱状只在柱高范围内点亮，
    柱子颜色由「显示模式号」当调色板 id 决定（同一个调色板函数也用于背景模式）：
      1 绿黄红分行 / 2 六色横条 / 5 旋转单色 / 6..11 纯色。
    采样证据（capture/official_music_colors3.jsonl）：这些模式每帧只有单一颜色族、
    覆盖率随振幅在 10%~50% 波动、6..11 的主色与背景同号纯色完全一致（FE0000…）。
    注意：显示模式 4 已单独实现（`_render_mode_4`，官方 v1 真值是频谱柱，不是这条合成包络）。

    pal：颜色覆盖（本工具增强）。只作用于「模式号当调色板」的分支（1/2/5），
    纯色 6..11 走 `_fill_solid`，天然不受影响。
    """
    n = st["amplitudeUI"] / 100.0
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"], n, dt)
    bg = _zeros(lay["F"], lay["P"])
    # 注意：这里的 palette 参数就是「显示模式号」，不是背景模式
    _apply_background(bg, mode, st["backmodeBrightness"], st, pal)
    st["phase"] = _advance(st["phase"], st["amplitudeUI"] / 1000.0, dt)
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


#: 兼容旧名字（1 与 4 曾被认为是「同一渲染器」；4 现已单独实现为频谱柱）
_render_mode_1or4 = _render_mode_steps


# ----------------------------------------------------------------------
# 显示模式 4「曲率频阶」—— 官方 v1 真值（2026-11-03 重新采样）
# ----------------------------------------------------------------------
#: 17 根柱子（= 官方 102 键网格的 17 列，底部对齐）。
_MODE4_COLS = 17
#: 调色板色相每 tick 前进的圈数（20fps → 0.8 圈/s）。
#: 采样：同一格色相每 100ms 前进约 28°（capture/official_v1_mode4_silence.jsonl）。
_MODE4_HUE_STEP = 0.04
#: 「曲率」兜底轮廓：没有频谱输入时（例如直接 tick(amp) 的单测/外部调用）
#: 用这条左高右低的曲线代替频谱，保证模式 4 不会全黑。
#: 数值来自官方静音采样 amp=30 的柱高归一化
#: [3.8,3.1,3.7,2.4,1.8,1.4,2.1,1.5,1.4,1.0,1.4,1.2,1.2,0.7,0.7,0.9,0.6]。
_MODE4_CURVATURE = (
    1.00, 0.82, 0.97, 0.63, 0.47, 0.37, 0.55, 0.39, 0.37,
    0.26, 0.37, 0.32, 0.32, 0.18, 0.18, 0.24, 0.16,
)


def _bands32_to_17(bands32) -> List[float]:
    """把 Analyzer 的 32 段对数频谱压成模式 4 的 17 根柱子（左低右高）。

    官方列↔频率映射（采样推断）：阶梯扫频 200/400/800/1600/3200/6400 Hz
    （capture/official_v1_mode4_sweep.jsonl）的柱峰逐级右移，拟合出的对数区间约
    110 Hz(第 0 列) … 12 kHz(第 16 列)，对应 bands32（20 Hz…20 kHz 对数 32 段）
    的下标 7.9 … 29.6。单音只点亮 1~3 列，与采样一致。
    """
    src = [float(x) for x in (bands32 or []) if x is not None]
    n = len(src)
    if n < 8:
        return [0.0] * _MODE4_COLS
    lo = 0.247 * (n - 1)
    hi = 0.926 * (n - 1)
    step = (hi - lo) / _MODE4_COLS
    out: List[float] = []
    for i in range(_MODE4_COLS):
        a = lo + step * i
        b = a + step
        j0 = max(0, int(math.floor(a)))
        j1 = min(n - 1, int(math.ceil(b)))
        # 取区间内最大值：单音在它的那一列得到满幅，相邻列按频段边界衰减
        out.append(_clamp(max(src[j0:j1 + 1]), 0.0, 1.0))
    return out


def _render_mode_4(grid, lay: dict, st: dict,
                   pal: Optional[Palette] = None) -> None:
    """官方 v1 显示模式 4「曲率频阶」：17 列频谱柱（底部对齐）+ 旋转径向色相。

    重新采样真值（probe/capture_official_v1_mode4.py → capture/official_v1_mode4_*.jsonl，
    440Hz/100Hz/2k/4k/8k 单音 + 阶梯扫频 + 静音，均为官方 MusicPlug.exe 自己算的颜色）：
      * 柱子**底部对齐**，17 列 = 频率（左低右高，对数）；200 Hz 只点亮最左 1~3 列，
        6.4 kHz 只点亮最右几列 —— 旧的合成包络（任何声音都点满左半边）与真值不符；
      * 每列柱高 = 该频段能量（Analyzer 的 32 段对数频谱压成 17 段）× amplitude 增益；
        真实音频链路给过频谱后，静音就是柱子归零（不会退回旧轮廓）；只有从未收到
        频谱输入（单测/外部直接 tick(amp)）时才退化成 _MODE4_CURVATURE 轮廓；
      * 颜色 = 以 (centerRow,centerCol) 为原点的径向色相（满饱和），
        左右半屏相差 180°；整个调色板约 0.8 圈/s 旋转；
      * 柱高随 amplitude 增长：amp=30 时单音峰值约 4/6 行，amp=100 时顶到 6/6。

    pal：颜色覆盖（本工具增强）——只把「色相 → RGB」换成在新调色板 hue/360 处取样，
    hue0 的旋转（约 275°/s）与径向角度原样保留。
    """
    F, P = lay["F"], lay["P"]
    cols = min(_MODE4_COLS, P)
    dt = float(st.get("dt", 1.0))
    st["mode4Hue"] = _advance(st.get("mode4Hue", 0.0), _MODE4_HUE_STEP, dt, 1.0)
    hue0 = st["mode4Hue"] * 360.0
    bands = st.get("spectrum17") or []
    if not any(bands) and not st.get("has_spectrum"):
        # 从未收到过频谱输入（单测/外部直接 tick(amp)）：退化成随振幅伸缩的「曲率」轮廓。
        # 注意：真实音频链路只要给过一次 bands32（has_spectrum=True），即使某一帧全 0
        # （安静段落/回环瞬时断流）也不再退回旧轮廓——否则真机上会闪回「旧方案」观感。
        amp = _clamp(st["amp"] * 2.0, 0.0, 1.0)
        bands = [_MODE4_CURVATURE[c] * amp for c in range(_MODE4_COLS)]
    # 柱高 = 该频段能量 × amplitude 增益：amp=30 时单音峰值约 4/6 行、amp=100 时顶到 6/6
    # （采样：capture/official_v1_mode4_tone100.jsonl / _sweep.jsonl）
    gain = st["amplitudeUI"] / 42.0
    for c in range(cols):
        lv = float(bands[c]) if c < len(bands) else 0.0
        h = int(math.floor(_clamp(lv * gain, 0.0, 1.0) * F))
        for k in range(max(0, h)):
            row = F - 1 - k
            angle = math.atan2(row - st["centerRow"], c - st["centerCol"])
            hue = (hue0 + 180.0 + math.degrees(angle)) % 360.0
            # 颜色覆盖：只替换「色相 → RGB」，hue0 的旋转与径向角度都不动
            grid[row][c] = _hue_color(hue, pal)


#: 模式 14 四条射线的官方固定色相：绿 120° / 蓝 240° / 黄 60° / 红 0°。
#: 无调色板时 ``_hue_color(h, None)`` 就是 ``_hsv(h, 1, 1)``，与官方四个固定
#: RGB 逐字节一致（120→(0,255,0) / 240→(0,0,255) / 60→(255,255,0) / 0→(255,0,0)）。
_MODE14_RAY_HUES = (120.0, 240.0, 60.0, 0.0)


def _render_mode_14(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Ce：中心 4 色射线旋转。

    pal：颜色覆盖（本工具增强）——射线角度/旋转/线段几何全部不动，只把四条
    射线的「固定色」换成按各自原色相（120/240/60/0°）在新调色板上取样：
    单色 id → 四条射线同色（旋转的十字）；渐变 id → 四条射线分取渐变上四个
    位置，「四色射线」的观感保留。
    """
    t = st["amplitudeUI"] / 100.0
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"], t, dt)
    st["rotate"] = _advance(st["rotate"], 4, dt, 360)
    F, P = lay["F"], lay["P"]
    max_dist = 0.0
    for r in range(F):
        for c in range(P):
            d = math.sqrt((c - lay["centerCol"]) ** 2 + (r - lay["centerRow"]) ** 2)
            max_dist = max(max_dist, d)
    r1 = min(st["smoothAmp"], 1.0)
    length = max(1.0, max_dist * r1)
    a = r1
    colors = [_hue_color(h, pal) for h in _MODE14_RAY_HUES]
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


def _render_mode_17(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 je：中心行正弦波 + 拖尾。

    pal：颜色覆盖（本工具增强）——列方向色相（含 huePhase 推进）与波形/拖尾
    全部不变，只把「色相 → RGB」换成在新调色板 hue/360 处取样；拖尾仍按原
    系数衰减（单色 id 下整条波同色，但明暗层次保留）。
    """
    t = min(st["amp"], 1.0)
    dt = float(st.get("dt", 1.0))
    st["phase"] = _advance(st["phase"], 0.5, dt)
    if st["phase"] >= math.pi * 2:
        st["phase"] -= math.pi * 2
    st["huePhase"] = _advance(st["huePhase"], 0.02, dt, 1.0)
    F, P = lay["F"], lay["P"]
    centers = [F // 2 - 1, F // 2] if F % 2 == 0 else [F // 2]
    for n in range(P):
        phi = (n / P) * math.pi * 2
        wave = math.sin(st["phase"] + phi)
        fall = 1 - (n / (P - 1)) ** 0.8 if P > 1 else 1.0
        scale = (1 + t * 2) * max(0.3, st["amplitudeUI"] / 50.0) * fall
        c = _rnd(wave * scale)
        color = _hue_color((n / P * 360 + st["huePhase"] * 360) % 360, pal)
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


def _render_mode_13(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Se：中心同心环扩散（默认模式）。

    pal：颜色覆盖（本工具增强）——中心/各环仍按原相位算色相，只把「色相 → RGB」
    换成在新调色板 hue/360 处取样；环相位推进（扩散动画）不变。
    """
    rings = _build_rings(lay)
    center_cells = rings[0] if rings else []
    ring_list = rings[1:]
    dt = float(st.get("dt", 1.0))
    st["phase"] = _advance(st["phase"], 0.005, dt, 1.0)
    st["huePhase"] = _advance(st["huePhase"], 0.005, dt, 1.0)
    ring_count = len(ring_list)
    phases = []
    for e in range(ring_count):
        phases.append((st["phase"] - e / max(1, ring_count) + 1) % 1.0)
    amp = min(st["amp"], 1.0)
    threshold = max(0.01, 0.06 - amp * 0.05)
    lit = 0 if amp < threshold else max(1, min(ring_count, _rnd(st["amp"] * ring_count)))
    k = st["amplitudeUI"] / 100.0
    st["smoothValue"] = _smooth(st["smoothValue"], lit, k, dt)
    active = _rnd(st["smoothValue"])
    center_color = _hue_color((st["huePhase"] * 360) % 360, pal)
    F, P = lay["F"], lay["P"]
    for (r, c) in center_cells:
        if 0 <= r < F and 0 <= c < P:
            grid[r][c] = center_color
    for e in range(active):
        if e >= len(ring_list):
            break
        ring = ring_list[e]
        color = _hue_color(((phases[e] + st["huePhase"]) * 360) % 360, pal)
        for (r, c) in ring:
            if 0 <= r < F and 0 <= c < P:
                grid[r][c] = color


def _render_mode_15(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Ee：休眠火山（左/中/右三塔随振幅长高，彩虹色相各自错开 120°）。

    MK87 没有 musicConfig.volcanoKeyPositions，走官方 fallback 分支：三座塔按
    「固定宽度表 + 列比例」逐层画——左塔从第 0 列向右展、右塔从最后一列向左展、
    中塔是以中间列为轴逐层收窄的梯形。高度用 0/±1 的爬山滞回（官方 we/Te）。
    官方"有 volcanoKeyPositions 坐标表"的分支未移植（MK87 无该配置，不可达）。

    pal：颜色覆盖（本工具增强）——三塔仍按原色相（相差 120°）与相位推进取色，
    只把「色相 → RGB」换成在新调色板 hue/360 处取样；塔高/宽度/爬山逻辑不变。
    """
    dt = float(st.get("dt", 1.0))
    st["huePhase"] = _advance(st["huePhase"], 0.01, dt, 1.0)
    n = (st["huePhase"] * 360.0) % 360.0
    F, P = lay["F"], lay["P"]
    left_widths: List[int] = [3, 3, 2, 2, 2, 1]
    right_widths: List[int] = [4, 3, 3, 3, 2, 1]
    total_keys = len(lay["cells"])  # 官方 keyList.flat().length
    if total_keys < 75:
        right_widths = [4, 3, 3, 2, 1, 1]
    elif total_keys > 100:
        right_widths = [5, 4, 4, 2, 1, 1]
    elif total_keys > 90:
        right_widths = [4, 4, 4, 2, 1, 1]
    mid_peak = int(math.floor(P / 2))
    right_peak = P - 1
    # 官方 d：目标高度；we/Te 为当前高度/剩余步数（爬升或回落都每 tick 只走 1 层）
    target = min(F, int(math.floor((st["amp"] + st["amplitudeUI"] / 100.0 * 0.5) * F)))
    height = st["volcanoHeight"]
    # 时间归一：每「基准 tick」爬 1 层。dt=1 时恰好 1 步（与原实现逐位一致），
    # 66fps 下用累计器攒够 1 个基准 tick 才走一步，不会快 3.3 倍。
    if dt == 1.0:
        moves = 1
        st["volcanoStep"] = 0.0
    else:
        pending = float(st.get("volcanoStep", 0.0)) + dt
        moves = int(pending)
        st["volcanoStep"] = pending - moves
    for _ in range(moves):
        if st["volcanoDir"] > 0:
            st["volcanoDir"] -= 1
            height = min(F, st["volcanoHeight"] + 1)
            st["volcanoHeight"] = height
        elif st["volcanoDir"] < 0:
            st["volcanoDir"] += 1
            height = max(0, st["volcanoHeight"] - 1)
            st["volcanoHeight"] = height
        else:
            st["volcanoDir"] = target - st["volcanoHeight"]
    rows = min(height, F)
    if rows <= 0:
        return
    towers = (
        (0, left_widths, _hue_color(n, pal)),
        (mid_peak, None, _hue_color((n + 120.0) % 360.0, pal)),
        (right_peak, right_widths, _hue_color((n + 240.0) % 360.0, pal)),
    )
    for idx, (peak, widths, color) in enumerate(towers):
        if idx == 0:
            for k in range(rows):
                row = F - 1 - k
                w = (widths[k] if widths and k < len(widths) else 0) or 1
                for col in range(peak, min(P - 1, peak + w - 1) + 1):
                    if 0 <= col < P:
                        grid[row][col] = color
        elif idx == 2:
            for k in range(rows):
                row = F - 1 - k
                w = (widths[k] if widths and k < len(widths) else 0) or 1
                for col in range(max(0, peak - w + 1), peak + 1):
                    if 0 <= col < P:
                        grid[row][col] = color
        else:
            # 中塔：官方 fallback 用 a[]/o[] 两张宽度表算内边界，逐层向中心收窄
            for k in range(rows):
                row = F - 1 - k
                left_w = (left_widths[k] if k < len(left_widths) else 0) or 1
                right_w = (right_widths[k] if k < len(right_widths) else 0) or 1
                lo = left_w
                hi = right_peak - right_w
                span = hi - lo + 1
                if span <= 0:
                    continue
                mid = (lo + hi) / 2.0
                shrink = 0.0 if rows == 1 else k / (rows - 1)
                half = max(1.0, math.floor(span * (1 - shrink))) / 2.0
                start = max(lo, int(math.ceil(mid - half)))
                stop = min(hi, int(math.floor(mid + half)))
                for col in range(start, stop + 1):
                    if 0 <= col < P:
                        grid[row][col] = color


#: 官方 De 的"光箭"固定点阵（row, col）：按键盘行数分支，MK87（6 行）用第三张表。
_ARROW_CELLS_TALL = (
    (1, 4), (1, 5), (1, 8), (1, 9), (2, 3), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8),
    (2, 9), (2, 10), (3, 4), (3, 5), (3, 6), (3, 7), (3, 8), (4, 5), (4, 6), (4, 7),
    (5, 6), (5, 7),
)
_ARROW_CELLS_SHORT = (
    (0, 4), (0, 5), (0, 8), (0, 9), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (1, 9), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8), (3, 6), (3, 7),
)
_ARROW_CELLS_MID = (
    (0, 4), (0, 5), (0, 8), (0, 9), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (1, 9), (1, 10), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8), (3, 5), (3, 6), (3, 7),
    (4, 6), (4, 7),
)


def _render_mode_16(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 De：光箭穿刺（中心两行从右侧铺光条 + 固定箭形点阵随振幅放大）。

    pal：颜色覆盖（本工具增强）——主色（箭形）与背景色（光条，原色相 +180°）
    仍按原相位推进，只把「色相 → RGB」换成在新调色板 hue/360 处取样；单色 id
    下光条与箭头同色相，箭头仍按振幅放大（保持明暗/大小层次）。
    """
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"], st["amplitudeUI"] / 100.0, dt)
    n = min(st["smoothAmp"], 1.0)
    scale = 1 + n * 0.2
    st["huePhase"] = _advance(st["huePhase"], 0.005, dt, 1.0)
    hue = (st["huePhase"] * 360.0) % 360.0
    main = _hue_color(hue, pal)
    back = _hue_color((hue + 180.0) % 360.0, pal)
    F, P = lay["F"], lay["P"]
    if F >= 7:
        cells = _ARROW_CELLS_TALL
    elif F < 6:
        cells = _ARROW_CELLS_SHORT
    else:
        cells = _ARROW_CELLS_MID
    centers = [F // 2 - 1, F // 2] if F % 2 == 0 else [F // 2]
    bar = min(1.0, n + st["amplitudeUI"] / 100.0 * 0.1) * P
    count = int(math.ceil(bar))
    for row in centers:
        for i in range(min(count, P)):
            col = P - 1 - i
            if 0 <= row < F and 0 <= col < P:
                grid[row][col] = back
    arrow = (
        min(255, int(main[0] * scale)),
        min(255, int(main[1] * scale)),
        min(255, int(main[2] * scale)),
    )
    for (row, col) in cells:
        if row < F and col < P:
            grid[row][col] = arrow


def _render_mode_18(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Oe：光茧共鸣（顶部横条 + 右列竖条 + 对角光带，随振幅扩张）。

    pal：颜色覆盖（本工具增强）——三条光带各自的色相（顶行 +0~120°、右列
    +60~180°、对角线 180°/步）与相位推进不变，只把「色相 → RGB」换成在新调色板
    hue/360 处取样；单色 id 下三条光带同色（几何/长度层次保留）。
    """
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"], st["amplitudeUI"] / 100.0, dt)
    n = st["smoothAmp"]
    F, P = lay["F"], lay["P"]
    length = int(math.ceil(P * n))
    st["huePhase"] = _advance(st["huePhase"], 0.005, dt, 1.0)
    base_hue = st["huePhase"] * 360.0
    cache: Dict[int, RGB] = {}

    def _color(hue: float) -> RGB:
        key = _rnd(hue)
        if key not in cache:
            cache[key] = _hue_color(float(key), pal)
        return cache[key]

    if length > 0:
        start = max(0, P - length)
        for col in range(start, P):
            grid[0][col] = _color((base_hue + col / P * 120.0) % 360.0)
        top = int(math.ceil(F * n))
        for row in range(min(top, F)):
            grid[row][P - 1] = _color((base_hue + 60.0 + row / F * 120.0) % 360.0)
        dx = (P - 1) - start
        dy = 0 - (F - 1)
        steps = max(abs(dx), abs(dy))
        if steps > 0:
            rx = dx / steps
            ry = dy / steps
            dh = 180.0 / steps
            for k in range(steps + 1):
                col = _rnd(start + k * rx)
                row = _rnd((F - 1) + k * ry)
                color = _color((base_hue + k * dh) % 360.0)
                for t in range(2):
                    cx = col + t - 1
                    if 0 <= cx < P and 0 <= row < F:
                        grid[row][cx] = color
                    if t < 1:
                        cy = row + t - 1
                        if 0 <= col < P and 0 <= cy < F and cy != row:
                            grid[cy][col] = color


def _render_mode_19(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Ae：音叉振动（左右两条触须，波形上下抖动 + 暗色余晖拖尾）。

    pal：颜色覆盖（本工具增强）——左右触须仍按原色相（相差 180°，随 amp 偏移）
    取色，抖动/触须长度/拖尾衰减（0.5/0.3 系数）全部不变，只把「色相 → RGB」
    换成在新调色板 hue/360 处取样。
    """
    F, P = lay["F"], lay["P"]
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"], st["amplitudeUI"] / 100.0, dt)
    st["smoothAmp"] = _clamp(st["smoothAmp"], 0.0, 1.0)
    n = st["smoothAmp"]
    st["tuningPhase"] = _advance(st["tuningPhase"], 0.1, dt)
    if st["tuningPhase"] >= math.pi * 2:
        st["tuningPhase"] = 0.0
    # 保持原加法顺序（dt=1 时逐位一致）：(hue + 0.005*dt) + n*0.01*dt
    st["huePhase"] = (st["huePhase"] + 0.005 * dt + n * 0.01 * dt) % 1.0
    hue = st["huePhase"] * 360.0
    cache: Dict[int, RGB] = {}

    def _color(h: float) -> RGB:
        key = _rnd(h)
        if key not in cache:
            cache[key] = _hue_color(float(key), pal)
        return cache[key]

    mid = int(math.floor(P / 2))
    jitter = (random.random() - 0.5) * n * 0.1
    base = mid * 0.2
    reach = n * mid * 0.6
    extra = jitter * mid * 0.15
    count = int(math.floor(max(2.0, base + reach + extra)))
    offset = int(math.floor(
        n * P * 0.15 + n * P * 0.2 + (random.random() - 0.5) * n * P * 0.15
    ))
    fan = n * 0.8

    def _fork(start_col: int, direction: int, color: RGB, steps: int,
              left_side: bool) -> None:
        width = 3 if offset > 2 else 2
        trail = min(2, int(math.floor(n * 2)))
        wave_amp = (random.random() * 2 - 1) * fan
        freq = 0.2 + n * 0.4 + random.random() * fan * 0.1
        phase = st["tuningPhase"] + (random.random() - 0.5) * fan
        for r in range(steps):
            col0 = start_col + r * direction
            row_off = 0
            if n > 0.1:
                wave = math.sin(r * freq + phase) + (random.random() - 0.5) * fan * 0.5
                row_off = int(math.floor(wave_amp * wave))
            row = r + row_off
            if 0 <= row < F:
                for t in range(width):
                    col = col0 + t if left_side else col0 + t + 1
                    if 0 <= col < P:
                        grid[row][col] = color
            if trail > 0:
                for t in range(1, trail + 1):
                    col2 = col0 - direction * t
                    row_off2 = 0
                    if n > 0.1:
                        wave2 = (math.sin((r - t) * freq + phase)
                                 + (random.random() - 0.5) * fan * 0.3)
                        row_off2 = int(math.floor(wave_amp * wave2))
                    row2 = (r - t) + row_off2
                    if 0 <= col2 < P and 0 <= row2 < F and grid[row2][col2][0] == 0:
                        fade = 0.5 - t * 0.2
                        grid[row2][col2] = (
                            _rnd(color[0] * fade),
                            _rnd(color[1] * fade),
                            _rnd(color[2] * fade),
                        )

    if count > 0:
        _fork(mid - 1 - offset, -1, _color((hue + n * 60.0) % 360.0), count, True)
        _fork(mid + 1 + offset, -1, _color((hue + 180.0 + n * 60.0) % 360.0), count, False)


def _render_mode_20(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Ne：曲率传承轨迹（右半区弯曲波形，从右向左推进并按列变细）。

    pal：颜色覆盖（本工具增强）——列方向色相（含 huePhase 推进）与波形弯曲/
    拖尾衰减不变，只把「色相 → RGB」换成在新调色板 hue/360 处取样。
    """
    F, P = lay["F"], lay["P"]
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"], 0.2, dt)
    n = min(st["smoothAmp"], 1.0)
    st["phase"] = _advance(st["phase"], 0.5, dt)
    if st["phase"] >= math.pi * 2:  # 官方 ie：越界直接归零（不是取模）
        st["phase"] = 0.0
    st["huePhase"] = _advance(st["huePhase"], 0.02, dt, 1.0)
    centers = [F // 2 - 1, F // 2] if F % 2 == 0 else [F // 2]
    thickness = max(2.0, math.floor(F / 2.5))
    quarter = int(math.floor(P / 4))
    rest = P - quarter
    start_col = quarter + int(math.floor(rest * n))
    for col in range(P - start_col, P):
        phi = col / P * math.pi * 2
        wave = math.sin(st["phase"] + phi)
        fall = 1 - (col / (P - 1)) ** 1.2
        body = max(2.0, thickness * 0.6)
        amp_px = body * (1 + n) * max(0.3, st["amplitudeUI"] / 50.0) * fall
        bend = _rnd(wave * amp_px)
        color = _hue_color((col / P * 360.0 + st["huePhase"] * 360.0) % 360.0, pal)
        for cr in centers:
            row = cr + bend
            if 0 <= row < F:
                grid[row][col] = color
            trail = min(3, abs(bend))
            direction = 0 if bend == 0 else (1 if bend > 0 else -1)
            for k in range(1, trail + 1):
                rr = cr + direction * k
                if 0 <= rr < F and rr != row:
                    fade = 1 - k / (trail + 1)
                    grid[rr][col] = (
                        _rnd(color[0] * fade * 0.6),
                        _rnd(color[1] * fade * 0.6),
                        _rnd(color[2] * fade * 0.6),
                    )


def _render_mode_21(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 Pe：行波浪节奏（逐行伪随机哈希波决定柱长，色相逐行渐变）。

    pal：颜色覆盖（本工具增强）——行方向色相（huePhase + row/F*180°）与柱长
    哈希/相位推进不变，只把「色相 → RGB」换成在新调色板 hue/360 处取样。
    """
    F, P = lay["F"], lay["P"]
    dt = float(st.get("dt", 1.0))
    st["smoothAmp"] = _smooth(st["smoothAmp"], st["amp"],
                              st["amplitudeUI"] / 100.0 * 0.8, dt)
    n = min(st["smoothAmp"], 1.0)
    st["phase"] = _advance(st["phase"], 0.02, dt)
    if st["phase"] >= math.pi * 2:  # 官方 ie：越界直接归零（不是取模）
        st["phase"] = 0.0
    st["huePhase"] = _advance(st["huePhase"], 0.01, dt, 1.0)
    for row in range(F):
        seed = row * 123.456 + st["phase"] * 10
        v1 = math.sin(seed) * 0.5 + 0.5
        v2 = math.sin(seed * 1.618) * 0.5 + 0.5
        v3 = math.sin(seed * 2.718) * 0.5 + 0.5
        mix = v1 * 0.3 + v2 * 0.6 + v3 * 0.1
        length = max(0, int(math.floor(n * P * 1.2 * mix)))
        color = _hue_color((st["huePhase"] * 360.0 + row / F * 180.0) % 360.0, pal)
        for col in range(min(length, P)):
            grid[row][col] = color


#: 官方 L（mode 22 双心共舞）内置坐标图案：两片心，按 (x=列, y=行) 从心尖向外分层。
#: 官方按几何选表：F>=7 → 总键数>102 → >90 → >75 → 其余；MK87（F=6、87 键）命中 >75 分支，
#: 即第 4 项——官方对 87 键布局内置了这张表，不需要 musicConfig 坐标配置。
_DUAL_HEART_TABLES = (
    (  # F.value>=7（7 行及以上键盘）
        (  # 左心
            ((3, 3),),
            ((3, 2), (4, 2), (2, 3), (4, 3), (2, 4), (3, 4)),
            ((2, 1), (3, 1), (4, 1), (5, 1), (1, 2), (5, 2), (1, 3), (5, 3), (1, 5), (2, 5),
             (3, 5), (4, 5), (5, 5), (2, 2), (4, 4)),
            ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (6, 1), (0, 2), (6, 2), (0, 3), (6, 3),
             (0, 4), (6, 4), (0, 5), (6, 5), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (5, 4),
             (1, 4), (1, 1)),
            ((5, 0), (7, 1), (7, 2), (7, 3), (7, 4), (7, 5), (0, 6), (6, 6)),
            ((6, 0), (7, 6), (0, 1)),
        ),
        (  # 右心
            ((11, 3),),
            ((11, 2), (12, 2), (10, 3), (12, 3), (10, 4), (11, 4)),
            ((10, 1), (11, 1), (12, 1), (13, 1), (9, 2), (13, 2), (9, 3), (13, 3), (9, 5),
             (10, 5), (11, 5), (12, 5), (13, 5), (10, 2), (12, 4)),
            ((8, 0), (9, 0), (10, 0), (11, 0), (12, 0), (14, 1), (8, 2), (14, 2), (8, 3), (14, 3),
             (8, 4), (14, 4), (8, 5), (14, 5), (9, 6), (10, 6), (11, 6), (12, 6), (13, 6),
             (13, 4), (9, 4), (9, 1)),
            ((7, 0), (13, 0), (15, 1), (15, 2), (15, 3), (15, 4), (15, 5), (8, 6), (14, 6)),
            ((14, 0), (15, 0), (16, 1), (16, 2), (16, 3), (16, 4), (16, 5), (15, 6), (16, 6),
             (8, 1)),
        ),
    ),
    (  # 总键数 >102
        (  # 左心
            ((4, 2),),
            ((4, 1), (5, 1), (3, 2), (5, 2), (3, 3), (4, 3)),
            ((4, 0), (5, 0), (3, 1), (6, 1), (2, 2), (6, 2), (2, 3), (5, 3), (3, 4), (4, 4),
             (5, 4)),
            ((3, 0), (6, 0), (2, 1), (7, 1), (1, 2), (7, 2), (1, 3), (6, 3), (2, 4), (6, 4),
             (3, 5), (4, 5), (5, 5), (6, 5), (7, 5), (8, 5), (9, 5)),
            ((2, 0), (7, 0), (1, 1), (8, 1), (0, 2), (8, 2), (0, 3), (7, 3), (0, 4), (1, 4),
             (7, 4), (1, 5), (2, 5)),
            ((0, 0), (1, 0), (8, 0), (9, 0), (0, 1), (9, 1), (9, 2), (8, 3), (8, 4), (0, 5)),
            ((9, 0), (9, 4)),
        ),
        (  # 右心
            ((15, 2),),
            ((15, 1), (14, 2), (16, 2), (14, 3), (15, 3)),
            ((15, 0), (14, 1), (16, 1), (13, 2), (17, 2), (12, 3), (13, 3), (16, 3), (14, 4),
             (15, 4), (16, 4)),
            ((14, 0), (16, 0), (13, 1), (17, 1), (12, 2), (18, 2), (11, 3), (17, 3), (12, 4),
             (13, 4), (17, 4), (18, 4), (13, 5), (14, 5), (15, 5), (16, 5), (17, 5), (18, 5)),
            ((12, 0), (13, 0), (17, 0), (12, 1), (18, 1), (11, 2), (19, 2), (10, 3), (18, 3),
             (11, 4), (19, 4), (11, 5), (12, 5), (19, 5)),
            ((11, 0), (18, 0), (11, 1), (19, 1), (10, 2), (20, 2), (9, 3), (19, 3), (10, 4),
             (20, 4), (10, 5), (20, 5)),
            ((10, 0), (19, 0), (20, 0), (10, 1), (20, 1), (21, 1)),
        ),
    ),
    (  # 总键数 >90
        (  # 左心
            ((4, 2),),
            ((4, 1), (5, 1), (3, 2), (5, 2), (3, 3), (4, 3)),
            ((4, 0), (6, 1), (2, 2), (6, 2), (2, 3), (6, 3), (4, 4), (3, 1), (5, 3)),
            ((2, 0), (6, 0), (7, 1), (1, 2), (7, 2), (1, 3), (7, 3), (2, 4), (6, 4), (3, 5),
             (4, 5), (5, 5), (5, 0), (3, 0), (5, 4), (3, 4), (2, 1)),
            ((1, 0), (7, 0), (8, 1), (0, 2), (8, 2), (0, 3), (8, 3), (1, 4), (7, 4), (2, 5),
             (6, 5), (1, 1)),
            ((0, 0), (8, 0), (9, 2), (0, 4), (8, 4), (0, 5), (1, 5), (7, 5), (8, 5)),
            ((9, 0), (9, 1), (9, 3), (9, 4), (9, 5), (0, 1)),
        ),
        (  # 右心
            ((14, 2),),
            ((14, 1), (15, 1), (13, 2), (15, 2), (13, 3), (14, 3)),
            ((14, 0), (16, 1), (12, 2), (16, 2), (12, 3), (16, 3), (14, 4), (13, 1), (15, 3)),
            ((12, 0), (16, 0), (17, 1), (11, 2), (17, 2), (11, 3), (17, 3), (12, 4), (16, 4),
             (13, 5), (14, 5), (15, 5), (15, 0), (13, 0), (15, 4), (13, 4), (12, 1)),
            ((11, 0), (17, 0), (18, 1), (10, 2), (18, 2), (10, 3), (18, 3), (11, 4), (17, 4),
             (12, 5), (16, 5), (11, 1)),
            ((10, 0), (18, 0), (10, 4), (18, 4), (10, 5), (11, 5), (17, 5), (18, 5)),
            ((19, 0), (20, 0), (10, 1), (19, 4), (19, 5)),
        ),
    ),
    (  # 总键数 >75（MK87 走这里）
        (  # 左心
            ((4, 2),),
            ((4, 1), (5, 1), (3, 2), (5, 2), (3, 3), (4, 3)),
            ((4, 0), (5, 0), (3, 1), (6, 1), (2, 2), (6, 2), (2, 3), (5, 3), (6, 3), (3, 4),
             (4, 4), (5, 4), (6, 4)),
            ((3, 0), (6, 0), (2, 1), (7, 1), (1, 2), (7, 2), (1, 3), (7, 3), (2, 4), (7, 4),
             (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5)),
            ((0, 0), (1, 0), (2, 0), (7, 0), (8, 0), (0, 1), (1, 1), (8, 1), (0, 2), (8, 2),
             (8, 2), (0, 3), (8, 3), (0, 4), (1, 4), (8, 4), (0, 5), (1, 5), (8, 5)),
        ),
        (  # 右心
            ((12, 2),),
            ((12, 1), (13, 1), (11, 2), (13, 2), (11, 3), (12, 3)),
            ((11, 0), (12, 0), (13, 0), (11, 1), (14, 1), (10, 2), (14, 2), (10, 3), (13, 3),
             (14, 3), (11, 4), (12, 4), (13, 4)),
            ((10, 0), (14, 0), (10, 1), (15, 1), (9, 2), (15, 2), (9, 3), (15, 3), (10, 4),
             (14, 4), (15, 4), (11, 5), (12, 5), (13, 5), (14, 5)),
            ((9, 0), (15, 0), (16, 0), (9, 1), (16, 1), (16, 2), (16, 3), (9, 4), (16, 4), (9, 5),
             (10, 5), (15, 5), (16, 5)),
        ),
    ),
    (  # 其余（少量键）
        (  # 左心
            ((3, 2),),
            ((3, 1), (4, 1), (2, 2), (4, 2), (3, 3), (4, 3)),
            ((3, 0), (4, 0), (2, 1), (5, 1), (1, 2), (5, 2), (2, 3), (5, 3), (4, 4), (5, 4),
             (6, 4)),
            ((2, 0), (5, 0), (1, 1), (6, 1), (0, 2), (6, 2), (0, 3), (1, 3), (6, 3), (2, 4)),
            ((0, 0), (1, 0), (6, 0), (0, 1), (0, 4), (1, 4)),
        ),
        (  # 右心
            ((9, 2),),
            ((9, 1), (10, 1), (8, 2), (10, 2), (9, 3), (10, 3)),
            ((9, 0), (10, 0), (8, 1), (11, 1), (7, 2), (11, 2), (8, 3), (11, 3), (7, 4), (8, 4),
             (9, 4)),
            ((8, 0), (11, 0), (12, 0), (7, 1), (12, 1), (12, 2), (7, 3), (12, 3), (13, 3), (7, 4),
             (10, 4), (11, 4)),
            ((7, 0), (13, 0), (14, 0), (13, 1), (14, 1), (13, 2), (14, 2), (14, 3), (12, 4),
             (13, 4), (14, 4), (15, 4), (15, 0), (15, 1)),
        ),
    ),
)


def _render_mode_22(grid, lay: dict, st: dict,
                    pal: Optional[Palette] = None) -> None:
    """官方 L：双心共舞（内置双心坐标图案逐层点亮，脉搏/阈值与 13 同一套算法）。

    官方开头算的左右心中心（a/o）与最大半径 l 在图案表里没有再用，故只保留选表逻辑。

    pal：颜色覆盖（本工具增强）——两颗心共用同一「层色相」（phases + huePhase，
    与 13 的环相位同构），按同一 hue→调色板映射取样；层级点亮/脉搏不变。
    渐变 id 下随层相位在 stops 上铺开（两心同层同色，保留原左右对称观感）。
    """
    F, P = lay["F"], lay["P"]
    total_keys = len(lay["cells"])  # 官方 keyList.flat().length
    if F >= 7:
        left, right = _DUAL_HEART_TABLES[0]
    elif total_keys > 102:
        left, right = _DUAL_HEART_TABLES[1]
    elif total_keys > 90:
        left, right = _DUAL_HEART_TABLES[2]
    elif total_keys > 75:
        left, right = _DUAL_HEART_TABLES[3]
    else:
        left, right = _DUAL_HEART_TABLES[4]
    layers = int(math.ceil((len(left) + len(right)) / 2.0))
    dt = float(st.get("dt", 1.0))
    st["phase"] = _advance(st["phase"], 0.005, dt)
    if st["phase"] >= 1.0:  # 官方 ie：越界直接归零（不是取模）
        st["phase"] = 0.0
    st["huePhase"] = _advance(st["huePhase"], 0.005, dt)
    if st["huePhase"] >= 1.0:
        st["huePhase"] = 0.0
    phases = [(st["phase"] - e / layers + 1) % 1.0 for e in range(layers)]
    amp = min(st["amp"], 1.0)
    threshold = max(0.01, 0.06 - amp * 0.05)
    lit = 0 if amp < threshold else max(1, min(layers, _rnd(st["amp"] * layers)))
    st["smoothValue"] = _smooth(st["smoothValue"], lit, st["amplitudeUI"] / 100.0, dt)
    active = int(math.ceil(st["smoothValue"]))
    for e in range(active):
        if e >= len(left):
            continue
        color = _hue_color(((phases[e] + st["huePhase"]) % 1.0) * 360.0, pal)
        for (x, y) in left[e]:
            if 0 <= x < P and 0 <= y < F:
                grid[y][x] = color
    for e in range(active):
        # 官方第二段的层数守卫写的是 u[e]（左心），这里照原样保留该判定
        if e >= len(left) or e >= len(right):
            continue
        color = _hue_color(((phases[e] + st["huePhase"]) % 1.0) * 360.0, pal)
        for (x, y) in right[e]:
            if 0 <= x < P and 0 <= y < F:
                grid[y][x] = color


def _render_frame(lay: dict, st: dict, mode: int) -> List[List[RGB]]:
    grid = _zeros(lay["F"], lay["width"])
    if st["backmode"]:
        # 背景永远用官方配色：颜色覆盖层只作用于前景调色板，不传 pal
        _apply_background(grid, st["backmode"], st["backmodeBrightness"], st)
    # ---- 颜色覆盖层的唯一入口（本工具增强）----
    # 只有「动态多色」模式消费用户调色板（COLOR_OVERLAY_MODES：1/2/4/5/13 + 14~22）；
    # 纯色 6~11、未实现的 100（回落 13）都不消费。
    pal = st.get("palette") if mode in COLOR_OVERLAY_MODES else None
    if mode == 4:
        _render_mode_4(grid, lay, st, pal)  # 官方 v1 真值：频谱柱 + 旋转径向色相
    elif mode in V1_STEP_MODES:
        _render_mode_steps(grid, mode, lay, st, pal)
    elif mode == 13:
        _render_mode_13(grid, lay, st, pal)
    elif mode == 14:
        _render_mode_14(grid, lay, st, pal)
    elif mode == 15:
        _render_mode_15(grid, lay, st, pal)
    elif mode == 16:
        _render_mode_16(grid, lay, st, pal)
    elif mode == 17:
        _render_mode_17(grid, lay, st, pal)
    elif mode == 18:
        _render_mode_18(grid, lay, st, pal)
    elif mode == 19:
        _render_mode_19(grid, lay, st, pal)
    elif mode == 20:
        _render_mode_20(grid, lay, st, pal)
    elif mode == 21:
        _render_mode_21(grid, lay, st, pal)
    elif mode == 22:
        _render_mode_22(grid, lay, st, pal)
    else:
        _render_mode_13(grid, lay, st)  # 100（屏光联动）等未移植模式回落到 13
    return grid


class MusicEngine:
    """官方音乐引擎：每个 20fps 基准 tick 把振幅变成 87 键 4B 载荷。

    动画速度与真实帧率解耦：``tick(..., dt_scale=N)`` 里 N 表示「本帧相当于几个
    20fps 基准 tick」（20fps → 1.0，66fps → 0.303，见 :func:`_dt_scale`）。
    所有随时间推进的相位/旋转/环扩散/AMP 平滑都乘 ``dt_scale``；振幅、频谱柱高
    这类「当帧量」不缩放。
    """

    def __init__(self, mode: int = 13, amplitude_ui: int = 50,
                 backmode: int = 0, backmode_brightness: int = 100,
                 color: str = DEFAULT_COLOR) -> None:
        mode = int(mode)
        if mode not in IMPLEMENTED_MODES:
            mode = 13
        self.mode = mode
        #: LED 颜色覆盖 id（本工具增强）：default = 不覆盖，走官方采样配色
        self.color = normalize_color_id(color)
        self.lay = layout()
        self.st = {
            "mode": mode,
            "amplitudeUI": _clamp(int(amplitude_ui), 1, 100),
            "backmode": int(backmode),
            "backmodeBrightness": _clamp(int(backmode_brightness), 1, 100),
            "amp": 0.0,
            "smoothAmp": 0.0,
            "phase": 0.0,
            "huePhase": 0.0,
            "smoothValue": 0.0,
            "rotate": 0.0,
            # 动画时间步长（1.0 = 标准 20fps tick），由 tick() 每帧写入
            "dt": 1.0,
            # 模式 15（官方 we/Te）：火山当前高度、剩余爬升/回落步数、不足一步的累计
            "volcanoHeight": 0,
            "volcanoDir": 0,
            "volcanoStep": 0.0,
            # 模式 19（官方 ke）：音叉的波形相位
            "tuningPhase": 0.0,
            # 模式 4（官方 v1「曲率频阶」）：17 段频谱 + 径向色相相位
            "spectrum17": [0.0] * _MODE4_COLS,
            #: 是否收到过真实音频链路的 bands32（区分「静音」与「无频谱输入」：
            #: 收到过就永不退回旧轮廓，静音就是柱子归零）
            "has_spectrum": False,
            "mode4Hue": 0.0,
            # 颜色覆盖调色板（None = default/不覆盖）：渲染层唯一消费点
            "palette": palette_for(self.color),
            "centerRow": self.lay["centerRow"],
            "centerCol": self.lay["centerCol"],
        }
        self._silence = 0.0
        #: 最近一帧的逐键颜色 {keyValue: (r,g,b)}（供前端「官方方案」预览回放；
        #: 与设备实际收到的 348B 载荷同源，保证屏幕预览和键盘同步）
        self.last_colors: Dict[int, RGB] = {}

    def set_mode(self, mode: int) -> None:
        mode = int(mode)
        self.mode = mode if mode in IMPLEMENTED_MODES else 13
        self.st["mode"] = self.mode

    def set_color(self, color) -> str:
        """热更新 LED 颜色覆盖（未知 id 回落 default）；返回生效的 id。"""
        self.color = normalize_color_id(color)
        self.st["palette"] = palette_for(self.color)
        return self.color

    def set_amplitude(self, amplitude_ui: int) -> None:
        self.st["amplitudeUI"] = _clamp(int(amplitude_ui), 1, 100)

    def set_backmode(self, backmode: int, brightness: int) -> None:
        """热更新官方背景参数（backmode 0..11 / 亮度 1..100，官方 v1 范围）。"""
        self.st["backmode"] = int(_clamp(int(backmode), 0, 11))
        self.st["backmodeBrightness"] = int(_clamp(int(brightness), 1, 100))

    def tick(self, amp1000: int, bands32: Optional[List[float]] = None,
             dt_scale: float = 1.0) -> bytes:
        """喂当前总振幅（0..1000），返回 348 字节逐键载荷。

        bands32：Analyzer 的 32 段对数频谱（0..1）。只有显示模式 4「曲率频阶」
        用它画 17 根柱子；其余模式完全忽略这个参数（默认 None → 模式 4 退化成
        纯「曲率」轮廓，不影响任何其它模式）。

        dt_scale：本帧相当于几个标准 20fps tick（默认 1.0，保持旧调用逐位一致）。
        MusicPlayer 按实际帧间隔传入 ``dt * 20``；渲染器只缩放随时间推进的动画量。
        """
        try:
            dt = float(dt_scale)
        except (TypeError, ValueError):
            dt = 1.0
        if not math.isfinite(dt) or dt <= 0:
            dt = 1.0
        if amp1000 > 0:
            self._silence = 0.0
            self.st["amp"] = min(1.0, amp1000 / 1000.0)
        else:
            # 官方 C=5：连续 5 个基准 tick（250ms）静音才归零；按时间归一，
            # 66fps 下是 ~16.5 帧而不是 5 帧，避免静音闪烁变快。
            self._silence += dt
            if self._silence >= 5:
                self.st["amp"] = 0.0
        if bands32 is not None:
            self.st["spectrum17"] = _bands32_to_17(bands32)
            self.st["has_spectrum"] = True
        self.st["dt"] = dt
        self.st["huePhase"] = _advance(self.st["huePhase"], 0.01, dt, 1.0)
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

    def _norm32(self, spectrum: np.ndarray, dt: float = 1.0) -> list:
        out = []
        for i, rng in enumerate(self._bands32_ranges):
            seg = spectrum[rng]
            e = float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0
            base = self._base32[i]
            r = _AMP_ATTACK if e > base else _AMP_DECAY
            base = max(_agc(base, e, r, dt), _AMP_FLOOR)
            self._base32[i] = base
            v = min(1000, int(round(e / base * 1000)))
            out.append(0.0 if v <= 5 else v / 1000.0)
        self.bands32 = out
        return out

    def analyze(self, samples: np.ndarray, dt_scale: float = 1.0) -> dict:
        """分析一帧音频；``dt_scale`` 用于把 AGC 的 attack/decay 按时间归一。

        默认 1.0 = 标准 20fps tick（输出与旧实现逐位一致）；66fps 传 ``20/66`` 时
        z / 3 段 / 32 段 base 的等效时间常数与 20fps 相同，避免高频下增益跟得太快。
        """
        try:
            dt = float(dt_scale)
        except (TypeError, ValueError):
            dt = 1.0
        if not math.isfinite(dt) or dt <= 0:
            dt = 1.0
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size < self.n_fft:
            x = np.pad(x, (0, self.n_fft - x.size))
        elif x.size > self.n_fft:
            x = x[-self.n_fft:]
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
        raw = 0.6 * peak + 0.4 * rms
        if raw > self.z:
            self.z = _agc(self.z, raw, _AMP_ATTACK, dt)
        else:
            self.z = _agc(self.z, raw, _AMP_DECAY, dt)
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
            base = max(_agc(base, e, r, dt), _AMP_FLOOR)
            self.bases[i] = base
            v = min(1000, int(round(e / base * 1000)))
            bands.append(0.0 if v <= 5 else v / 1000.0)
        bands32 = self._norm32(spectrum, dt)
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
#: PulseAudio/PipeWire 采样格式：PA_SAMPLE_FLOAT32LE（pa_sample_format_t 枚举值 5）
PA_SAMPLE_FLOAT32LE = 5
#: pa_stream_direction_t：PA_STREAM_RECORD
PA_STREAM_RECORD = 2
#: PulseAudio 特殊源名：默认输出的 monitor（PipeWire 的 pulse 兼容层同样支持；
#: Chromium 的 loopback 采集也是用这个名字）
DEFAULT_MONITOR = "@DEFAULT_MONITOR@"


class _PaSampleSpec(ctypes.Structure):
    """libpulse ``pa_sample_spec``（format 是枚举 = int，结构体有 3 字节对齐填充）。"""

    _fields_ = [
        ("format", ctypes.c_int),
        ("rate", ctypes.c_uint32),
        ("channels", ctypes.c_uint8),
    ]


class PulseSimpleRecorder:
    """Linux：用 libpulse-simple 直接采集系统输出回环（PulseAudio / PipeWire 通用）。

    为什么不再依赖 ``parec``：parec 属于 pulseaudio-utils，Fedora/Debian 的
    PipeWire 桌面默认不装，于是音乐律动会直接报「音频采集打开失败」。
    ``libpulse-simple.so.0`` 则是 libpulse0 / pulseaudio-libs 的一部分（安装包已
    声明依赖），PipeWire 的 pulse 兼容层同样可用，不需要任何外部命令。
    """

    CHANNELS = 2

    def __init__(self, device_id: Optional[str] = None, samplerate: int = 48000):
        self.samplerate = int(samplerate)
        self.device = str(device_id) if device_id else DEFAULT_MONITOR
        self._handle = None
        self._pulse = None
        self._ps = self._load_libpulse_simple()
        self._configure()
        spec = _PaSampleSpec(PA_SAMPLE_FLOAT32LE, self.samplerate, self.CHANNELS)
        error = ctypes.c_int(0)
        self._handle = self._ps.pa_simple_new(
            None,
            b"MK87 Studio",
            PA_STREAM_RECORD,
            self.device.encode("utf-8"),
            b"music",
            ctypes.byref(spec),
            None,
            None,
            ctypes.byref(error),
        )
        if not self._handle:
            raise MK87Error(
                f"打开系统输出采集失败（源: {self.device}）: {self._strerror(error.value)}"
            )

    # ------------------------------------------------------------ 加载 / 配置
    @staticmethod
    def _load_libpulse_simple():
        try:
            return ctypes.CDLL("libpulse-simple.so.0")
        except OSError:
            pass
        name = ctypes.util.find_library("pulse-simple")
        if not name:
            raise MK87Error(
                "找不到 libpulse-simple.so.0（PulseAudio/PipeWire 客户端库缺失；"
                "Debian/Ubuntu 装 libpulse0，Fedora 装 pulseaudio-libs）"
            )
        return ctypes.CDLL(name)

    def _configure(self) -> None:
        self._ps.pa_simple_new.restype = ctypes.c_void_p
        self._ps.pa_simple_new.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.POINTER(_PaSampleSpec), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
        ]
        self._ps.pa_simple_read.restype = ctypes.c_int
        self._ps.pa_simple_read.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._ps.pa_simple_free.restype = None
        self._ps.pa_simple_free.argtypes = [ctypes.c_void_p]
        try:
            self._pulse = ctypes.CDLL("libpulse.so.0")
            self._pulse.pa_strerror.restype = ctypes.c_char_p
            self._pulse.pa_strerror.argtypes = [ctypes.c_int]
        except OSError:
            self._pulse = None

    def _strerror(self, code: int) -> str:
        try:
            if self._pulse is not None:
                msg = self._pulse.pa_strerror(int(code))
                if msg:
                    return msg.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        return f"错误码 {code}"

    # ------------------------------------------------------------ 读写
    def read(self, frames: int) -> np.ndarray:
        if self._handle is None:
            raise MK87Error("音频采集已关闭")
        frames = max(1, int(frames))
        nbytes = frames * self.CHANNELS * 4  # float32 × 声道
        buf = ctypes.create_string_buffer(nbytes)
        error = ctypes.c_int(0)
        rc = self._ps.pa_simple_read(self._handle, buf, nbytes, ctypes.byref(error))
        if rc < 0:
            raise MK87Error(f"系统音频采集失败: {self._strerror(error.value)}")
        data = np.frombuffer(buf.raw, dtype="<f4")
        if data.size == 0:
            return np.zeros(frames, dtype=np.float32)
        return data.reshape(-1, self.CHANNELS).mean(axis=1).astype(np.float32)

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._ps.pa_simple_free(self._handle)
            except Exception:  # noqa: BLE001
                pass
            self._handle = None


def _pactl_default_monitor() -> Optional[str]:
    """用 ``pactl get-default-sink`` 拼默认输出的 monitor 源名（不可用返回 None）。

    某些 PipeWire 版本不解析 PulseAudio 的 ``@DEFAULT_MONITOR@`` 特殊源名，
    这时用真实源名 ``<默认 sink>.monitor`` 再打开一次。
    """
    try:
        res = subprocess.run(["pactl", "get-default-sink"], capture_output=True,
                             text=True, timeout=2)
    except Exception:  # noqa: BLE001 - pactl 未安装 / 无 pulse 服务
        return None
    sink = (res.stdout or "").strip().splitlines()
    if not sink or not sink[0].strip():
        return None
    return f"{sink[0].strip()}.monitor"


class AudioCapture:
    """系统输出回环采集（Windows: soundcard WASAPI / Linux: libpulse-simple，parec 兜底）。

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
        self._pulse = None
        self._proc = None
        self._backend = ""
        self.system = platform.system()
        self._buf = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error: Optional[str] = None
        #: 最近一次读到**新数据**的单调时钟（音乐会话据此检测采集卡死）。
        #: 系统待机 / 拔掉默认输出设备后 WASAPI 会永久阻塞在 record()，
        #: 不会抛异常，只能靠这个时间戳发现「采集线程还活着但不再出数据」。
        self._last_data_ts: Optional[float] = None

    @property
    def last_data_ts(self) -> Optional[float]:
        """最近一次采集到新音频数据的单调时钟时间；None = 还没出过数据。"""
        return self._last_data_ts

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
            self._open_linux()
        else:
            raise MK87Error(f"当前平台不支持系统音频采集: {self.system}")

    def _open_linux(self) -> None:
        """Linux 采集后端：libpulse-simple（系统自带库）→ parec（外部命令兜底）。"""
        errors: List[str] = []
        candidates: List[Optional[str]] = [self.device_id]
        if self.device_id is None:
            # 个别 PipeWire 版本不认 @DEFAULT_MONITOR@ 特殊源名，
            # 再用 pactl 查到的真实 "<默认 sink>.monitor" 试一次。
            monitor_name = _pactl_default_monitor()
            if monitor_name:
                candidates.append(monitor_name)
        for dev in candidates:
            try:
                self._pulse = PulseSimpleRecorder(dev, self.samplerate)
                self._backend = "libpulse"
                log.info("音频采集后端: libpulse-simple（源: %s）", self._pulse.device)
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"libpulse({dev or DEFAULT_MONITOR}): {exc}")
                self._pulse = None
        device = self.device_id or DEFAULT_MONITOR
        try:
            self._proc = subprocess.Popen(
                ["parec", "--format=float32le", f"--rate={self.samplerate}",
                 "--channels=2", f"--device={device}"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self._backend = "parec"
            log.info("音频采集后端: parec（源: %s）", device)
            return
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, FileNotFoundError):
                errors.append("parec 未安装（Debian/Ubuntu: pulseaudio-utils，"
                              "Fedora: pulseaudio-utils）")
            else:
                errors.append(f"parec: {exc}")
            self._proc = None
        raise MK87Error(
            "Linux 音频采集不可用 —— " + "；".join(errors)
            + "。请确认 PipeWire / PulseAudio 正在运行："
              "systemctl --user status pipewire-pulse"
        )

    def _read_impl(self, frames: int) -> np.ndarray:
        if self.system == "Windows":
            data = self._impl.record(numframes=frames)
            if getattr(data, "ndim", 1) > 1:
                data = data.mean(axis=1)
            return np.asarray(data, dtype=np.float32)
        if self._pulse is not None:
            return self._pulse.read(frames)
        if self._proc is None or self._proc.stdout is None:
            return np.zeros(frames, dtype=np.float32)
        need = frames * 2 * 4  # 2ch float32
        buf = self._proc.stdout.read(need)
        if not buf:
            code = self._proc.poll()
            if code is not None:
                raise MK87Error(f"parec 已退出（code={code}），音频采集中断")
            return np.zeros(frames, dtype=np.float32)
        return np.frombuffer(buf, dtype="<f4").reshape(-1, 2).mean(axis=1).astype(np.float32)

    def _close_impl(self):
        if self._impl is not None:
            try:
                self._impl.__exit__(None, None, None)
            except Exception:
                pass
            self._impl = None
        if self._pulse is not None:
            try:
                self._pulse.close()
            except Exception:
                pass
            self._pulse = None
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
            self._last_data_ts = time.monotonic()
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
                    self._last_data_ts = time.monotonic()
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
        out: List[dict] = []
        try:
            res = subprocess.run(["pactl", "list", "short", "sources"],
                                 capture_output=True, text=True, timeout=3)
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
        except FileNotFoundError:
            log.debug("pactl 未安装（pulseaudio-utils），音频设备列表回落到默认输出回环")
        except Exception as exc:  # noqa: BLE001
            log.debug("pactl 枚举音频源失败: %s", exc)
        if not out:
            # pactl 缺失时仍可用：采集直接连 PulseAudio/PipeWire 的默认 monitor
            # （libpulse 支持 @DEFAULT_MONITOR@ 特殊源名）
            out = [{"id": None, "name": "默认输出回环（PulseAudio / PipeWire）",
                    "loopback": True, "default": True}]
        return out
    return []


# ----------------------------------------------------------------------
# ACK 清道夫：音乐帧流 140 包/秒（66fps 时 462 包/秒）的 ACK 必须被读走，否则固件
# 输入缓冲满后连 WriteFile 都会被拖慢（真机实测：不读 ACK 时帧率掉到 6fps 且越来越慢）。
# 但 hidapi 的 read(timeout) 在空队列上会卡 50~400ms（CancelIoEx 延迟），
# 所以用独立线程持续阻塞读并丢弃，绝不阻塞发送线程。
#
# 平时不需要它：≤30fps 逐包 ACK；≥60fps 帧末 drain（同一线程读走本帧回包）。
# 只有「≥60fps 且帧末 drain 连续多帧一个回包都没读到」才会启用本兜底。
# ----------------------------------------------------------------------
class AckDrainer:
    def __init__(self, device=None, read=None, name: str = "mk87-ack-drain"):
        self.device = device
        #: 读函数 ``read(timeout) -> bytes | None``；None → 读设备协议接口（hidapi）
        self._read = read
        self._name = name
        self.count = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _reader(self):
        if self._read is not None:
            return self._read
        iface = self.device.protocol.iface
        return iface.read_report

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.count = 0
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            read = self._reader()
        except Exception:  # noqa: BLE001
            return
        while not self._stop.is_set():
            try:
                r = read(timeout=0.1)
            except Exception:  # noqa: BLE001
                break
            if r:
                self.count += 1
            else:
                # 真机读超时是 0.1s；这里只在「无回包」时让出一点 CPU（单测假读立即返回）
                time.sleep(0.002)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None


# ----------------------------------------------------------------------
# 播放器
# ----------------------------------------------------------------------
def _send_strategy(fps: int, packet_count: int = 7) -> Tuple[bool, int]:
    """按目标帧率选发送策略：返回 ``(wait_ack, drain)``。

    * 低于 60fps（UI 档位 15/20/30）：逐包等 ACK（``wait_ack=True``）。真机实测 7 包
      平均 **15.5ms**、最大 20.06ms（docs/spec-lighting.md §4.3），30fps 的 33.3ms
      预算有 ~13ms 余量，可靠性优先，20fps 行为与改动前完全一致；
    * ≥60fps（UI 档位 60/66）：连续写 7 包后帧末 drain 本帧的 7 个回包
      （``wait_ack=False``）。66fps 每帧预算只有 15.15ms < 逐包 ACK 的平均 15.5ms，
      逐包等 ACK 必然掉帧；而 7 个写操作背靠背完成时 ACK 通常已排队，帧末 drain
      读的是现成数据。
    """
    target = _clamp_fps(fps)
    if target >= BURST_MIN_FPS:
        return False, 0
    return True, 0


def _call_with_timeout(fn, timeout: float, label: str) -> bool:
    """在旁路线程执行可能阻塞的清理调用，最多等 ``timeout`` 秒。

    设备被拔掉 / USB 重新枚举时，HID 句柄 ``close()`` 可能卡在收割在途 IO
    （``NativeHidChannel.close`` 里的 ``_reap_pending`` 最长等 2s）；会话重建是
    自动恢复的关键路径，不能为了关旧资源把音乐监督线程卡死。超时后直接放弃等待，
    由后台线程兜底收尾（daemon，异常吞掉），主线程继续重建会话。

    返回 True = 在时限内完成；False = 超时（已放弃等待）。
    """
    done = threading.Event()

    def _run() -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 - 清理失败不能影响恢复
            log.debug("%s失败（忽略）", label, exc_info=True)
        finally:
            done.set()

    t = threading.Thread(target=_run, name="mk87-music-cleanup", daemon=True)
    t.start()
    if done.wait(max(0.05, float(timeout))):
        return True
    log.warning("%s超时（>%.2fs），已放弃等待，由后台线程兜底收尾", label, timeout)
    return False


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
        #: LED 颜色覆盖 id（本工具增强；default = 官方采样配色）
        self.color = DEFAULT_COLOR
        #: 目标帧率（配置值）；实测值走 :attr:`measured_fps`
        self.fps = DEFAULT_FPS
        self.device_id: Optional[str] = None
        self.level = 0.0
        self.bands: List[float] = [0.0, 0.0, 0.0]
        self.levels32: List[float] = [0.0] * 32
        self.frames = 0
        self.errors = 0
        self.last_error = ""
        #: 实际使用的音频采集后端（Linux: libpulse / parec；Windows 空字符串）
        self.audio_backend = ""
        self.last_payload: bytes = b""
        #: 最近一帧逐键颜色（与 last_payload 同源，供前端官方方案预览）
        self.last_colors: Dict[int, RGB] = {}
        self._snapshot: Optional[dict] = None
        self._engine: Optional[MusicEngine] = None
        self._drainer: Optional[AckDrainer] = None
        self._drainer_failed = False
        self._sender = None
        #: 当前发送策略：ack（<60fps 逐包等）/ burst（≥60fps 帧末 drain）/ burst+drainer
        self.send_mode = "ack"
        self.timing = {"read": 0.0, "analyze": 0.0, "send": 0.0, "frames": 0}
        self._ready = threading.Event()
        self._start_error: Optional[str] = None
        # ---- 实测帧率（最近 ~2s 的帧时间戳；线程安全） ----
        self._fps_lock = threading.Lock()
        self._frame_ts: deque = deque()
        # ---- 节奏 / 健康度（单测可注入假时钟） ----
        self._clock = time.perf_counter
        self._sleep = time.sleep
        self._pace_fps = 0
        self._late_frames = 0
        self._ack_miss_streak = 0
        # ---- 会话守护 / 自动恢复（v0.1.8.4） ----
        #: 健康状态：starting / ok / recovering / waiting-device / stopped（前端徽章用）
        self.health = "stopped"
        #: 自动恢复次数（同一段律动里会话中断后重建的次数）
        self.recoveries = 0
        #: 最近一次自动恢复开始的 unix 时间戳
        self.last_recovery: Optional[float] = None
        #: 最近一次成功下发帧的单调时钟（前端 frameAgeMs / 卡死检测用）
        self._last_frame_ts: Optional[float] = None
        #: 当前会话是否已成功建立过（区分「首次建立失败」与「运行中中断」）
        self._session_ok = False
        #: 是否因为原音频设备失效回退到了默认输出回环
        self._audio_fallback = False
        #: 是否由用户主动停止（用于区分「意外停止」的事件通知）
        self._user_stopped = False
        #: 保后台句柄（音乐律动期间阻止系统休眠；Windows 关闭能效节流）
        self._keepalive = None
        # ---- 帧流看门狗（v0.1.8.6）：最后成功帧时间 / 会话起始时间 ----
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop = threading.Event()
        #: 帧流卡死次数（看门狗判定 >2s 无成功帧的次数；status 暴露，排障用）
        self.stalls = 0
        #: 本次卡死开始时间（单调时钟）；None = 当前没有卡死
        self._stall_since: Optional[float] = None
        #: 卡死是否已升级为「旁路强关发送通道」（每次卡死只升级一次）
        self._stall_escalated = False
        #: 看门狗要求主循环重建会话（主循环每轮开头检查）
        self._force_rebuild = threading.Event()
        #: 当前会话的音频采集引用（看门狗旁路收尾用）
        self._capture = None
        #: 当前会话建立时间（还没发出第一帧时，看门狗按它判卡死）
        self._session_started_ts: Optional[float] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ 实测帧率
    def _reset_measured_fps(self) -> None:
        with self._fps_lock:
            self._frame_ts.clear()

    def _record_frame_time(self, ts: float) -> None:
        """记录一帧实际下发完成的单调时钟时间戳（滚动 2s 窗口）。"""
        with self._fps_lock:
            dq = self._frame_ts
            dq.append(float(ts))
            cutoff = float(ts) - MEASURED_FPS_WINDOW
            # 至少保留 2 个样本，避免窗口清空后没有可算的跨度
            while len(dq) > 2 and dq[0] < cutoff:
                dq.popleft()

    @property
    def measured_fps(self) -> Optional[float]:
        """最近 ~2s 的实测帧率（1 位小数）；样本不足时 None（不拿配置值充数）。"""
        with self._fps_lock:
            dq = self._frame_ts
            if len(dq) < 2:
                return None
            span = dq[-1] - dq[0]
            if span < MEASURED_FPS_MIN_SPAN:
                return None
            return round((len(dq) - 1) / span, 1)

    def _ensure_drainer(self) -> bool:
        """确保 ≥60fps 的 ACK 清道夫线程在跑（异步读走回包）。

        真机实测：清道夫在跑时 send ≈ 8.9ms/帧（66fps 稳定）；起不来时调用方回退
        帧末同步 drain（≈19.8ms/帧，只能跑到 ~45fps）。
        """
        d = self._drainer
        if d is not None and d.is_alive():
            return True
        if d is not None:
            d.stop()
            self._drainer = None
        if self._drainer_failed or self._sender is None:
            return False
        try:
            # 只读 FrameSender 的原生句柄：不碰协议接口，避免偷走其它命令的回包
            d = AckDrainer(read=self._sender.read_ack)
            d.start()
            if d.is_alive():
                self._drainer = d
                return True
        except Exception as exc:  # noqa: BLE001
            log.warning("ACK 清道夫启动失败，回退帧末同步 drain: %s", exc)
        self._drainer_failed = True
        return False

    def start(self, device_id: Optional[str] = None, mode: Optional[int] = None,
              style: Optional[str] = None, sensitivity: float = 1.0,
              fps: int = DEFAULT_FPS, backmode: int = 0, backmode_brightness: int = 100,
              amplitude: Optional[int] = None, color: Optional[str] = None) -> dict:
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
        self.backmode_brightness = int(_clamp(int(backmode_brightness or 100), 1, 100))
        # LED 颜色覆盖（本工具增强）：缺省/default = 不覆盖；未知 id 回落 default
        self.color = normalize_color_id(color)
        # 原生帧率：15/20/30/60/66（5..66 兼容；越界钳制到 5/66，无法解析回落 20）
        self.fps = _clamp_fps(fps)
        self.device_id = device_id
        self.errors = 0
        self.last_error = ""
        self.audio_backend = ""
        self.frames = 0
        self.levels32 = [0.0] * 32
        self.last_colors = {}
        self._stop.clear()
        self._ready = threading.Event()
        self._start_error = None
        self.timing = {"read": 0.0, "analyze": 0.0, "send": 0.0, "frames": 0}
        self.send_mode = "burst" if self.fps >= BURST_MIN_FPS else "ack"
        self._pace_fps = 0
        self._late_frames = 0
        self._drainer_failed = False
        self._reset_measured_fps()
        # 会话守护字段：新一轮启动从干净状态开始（restart 后恢复次数归零）
        self._user_stopped = False
        self._session_ok = False
        self._last_frame_ts = None
        self.health = "starting"
        self.recoveries = 0
        self.last_recovery = None
        self._audio_fallback = False
        # 帧流看门狗字段：新一轮启动从干净状态开始
        self.stalls = 0
        self._stall_since = None
        self._stall_escalated = False
        self._force_rebuild.clear()
        self._capture = None
        self._session_started_ts = None
        # 保后台：音乐律动期间阻止系统空闲休眠 / 关闭 Windows 能效节流，
        # 否则合盖待机或后台节流会让帧流中断（v0.1.8.4，见文件头会话守护注释）。
        self._keepalive = powerkeep.keep_awake()
        try:
            self._keepalive.start()
        except Exception:  # noqa: BLE001 - 保后台失败不能影响律动本身
            log.debug("保后台启动失败（忽略）", exc_info=True)
        self._thread = threading.Thread(target=self._loop, name="mk87-music", daemon=True)
        self._thread.start()
        # 帧流看门狗：主循环活着但不再出帧时兜底重建会话（与业务线程解耦）
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="mk87-music-watchdog", daemon=True
        )
        self._watchdog_thread.start()
        log.info("音乐律动启动: mode=%s(请求 %s) amplitude=%s backmode=%s bb=%s color=%s "
                 "targetFps=%s send=%s device=%s keepAwake=%s",
                 self.mode, self.requested_mode, self.amplitude_ui,
                 self.backmode, self.backmode_brightness, self.color,
                 self.fps, "burst" if self.fps >= BURST_MIN_FPS else "ack",
                 device_id or "默认输出",
                 bool(getattr(self._keepalive, "active", False)))
        # 等音频引擎真正打开再返回：失败要立刻报错，不能"假装成功"
        if not self._ready.wait(timeout=5.0):
            self._stop.set()
            self._stop_keepalive()
            raise MK87Error("音乐引擎启动超时（音频设备无响应）")
        if self._start_error:
            self._stop.set()
            self._stop_keepalive()
            raise MK87Error(f"音乐律动启动失败（设备: {device_id or '默认输出'}）：{self._start_error}")
        return self.status()

    def _stop_keepalive(self) -> None:
        keepalive = self._keepalive
        self._keepalive = None
        if keepalive is not None:
            try:
                keepalive.stop()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ 会话守护
    def _device_connected(self) -> bool:
        """键盘当前是否在线（假设备 / 无状态对象按在线处理）。"""
        try:
            return bool(getattr(getattr(self.device, "status", None), "connected", True))
        except Exception:  # noqa: BLE001
            return True

    def _frame_age(self) -> Optional[float]:
        ts = self._last_frame_ts
        if ts is None:
            return None
        return max(0.0, time.monotonic() - ts)

    def _set_health(self, state: str) -> None:
        if self.health != state:
            log.debug("音乐律动健康状态: %s -> %s", self.health, state)
            self.health = state

    # ------------------------------------------------------------------ 帧流看门狗
    def _stop_watchdog(self) -> None:
        """停止看门狗线程（幂等；最多等 0.6s，不能拖住停止/清理路径）。"""
        self._watchdog_stop.set()
        t = self._watchdog_thread
        self._watchdog_thread = None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=0.6)

    def _watchdog_loop(self) -> None:
        """帧流看门狗：主循环还活着但「最后成功帧」太旧 → 判定卡死并重建会话。

        与业务线程解耦的原因：只靠主循环里的「连续发送异常计数」覆盖不了所有卡死
        形态 —— 一旦某次 HID 写/读调用卡在内核 IO 里再也不返回，主循环既不出帧、
        也不抛异常、也走不到 send-error 分支，监督循环会一直等下去（界面显示
        「律动中」但电平条静默冻结）。看门狗按「最后成功帧时间」独立判活：
        超时先通知主循环退出会话（正常情况下一轮循环内生效）；
        主循环若连会话都退不出来，宽限期后旁路强关发送通道把它逼醒。
        """
        while not self._watchdog_stop.wait(WATCHDOG_INTERVAL):
            try:
                if not self.running:
                    return
                if self.health == "waiting-device":
                    # 键盘离线：监督循环在等 monitor 线程重连，本来就不出帧
                    self._stall_since = None
                    self._stall_escalated = False
                    continue
                if self.health != "ok" and self._stall_since is None:
                    # 普通恢复中（由 send-error / audio-stalled 等触发），不判卡死
                    continue
                now = time.monotonic()
                age = self._frame_age()
                if age is None:
                    # 会话刚建立、还没下发第一帧：按会话建立时间计时
                    started = self._session_started_ts
                    if started is None or now - started < FRAME_STALL_TIMEOUT:
                        if self.health == "ok":
                            self._stall_since = None
                            self._stall_escalated = False
                        continue
                    age = now - started
                if age < FRAME_STALL_TIMEOUT:
                    self._stall_since = None
                    self._stall_escalated = False
                    continue
                if self._stall_since is None:
                    self._stall_since = now
                    self.stalls += 1
                    self.last_error = f"帧流卡死（{age:.1f}s 无成功帧），重建会话"
                    log.warning("音乐帧流卡死（%.1fs 无成功帧），通知主循环重建会话", age)
                    # 立即把健康度标成恢复中：前端徽章不必等主循环退出会话
                    self._set_health("recovering")
                    self._force_rebuild.set()
                    continue
                if (not self._stall_escalated
                        and now - self._stall_since >= WATCHDOG_HARD_GRACE):
                    self._stall_escalated = True
                    log.warning("音乐帧流卡死超过 %.1fs 仍未退出会话，旁路强关发送通道",
                                WATCHDOG_HARD_GRACE)
                    self._abort_active_session()
            except Exception:  # noqa: BLE001 - 看门狗自身异常不能影响音乐线程
                log.debug("音乐看门狗异常（忽略）", exc_info=True)

    def _abort_active_session(self) -> None:
        """看门狗兜底：从旁路线程强关当前发送通道，逼醒卡在 HID IO 里的主循环。

        只关发送通道（音频采集的 read 是内存拷贝，不会永久阻塞）。关闭动作放在
        独立 daemon 线程里并限时等待，避免看门狗自己被死句柄拖住。
        """
        sender = self._sender
        if sender is None:
            return
        _call_with_timeout(sender.close, CLOSE_SENDER_TIMEOUT_OFFLINE,
                           "看门狗强关帧流发送通道")

    def _open_capture(self) -> AudioCapture:
        """打开音频采集；原设备失效时回退默认输出回环。

        用户拔掉耳机 / 切换默认输出设备后，旧的 loopback 设备 ID 会永久失效，
        此时回退默认输出比直接报错更符合预期（界面会显示 audioFallback 提示）。
        """
        try:
            capture = AudioCapture(self.device_id)
            capture.open()
            return capture
        except Exception as exc:  # noqa: BLE001
            if not self.device_id:
                raise
            log.warning("原音频设备不可用（%s），回退默认输出回环: %s", self.device_id, exc)
            capture = AudioCapture(None)
            capture.open()
            self._audio_fallback = True
            return capture

    def _new_engine(self) -> MusicEngine:
        return MusicEngine(self.mode, amplitude_ui=self.amplitude_ui,
                           backmode=self.backmode,
                           backmode_brightness=self.backmode_brightness,
                           color=self.color)

    def _close_session(self, capture, sender) -> None:
        """关闭一次会话的音频/发送资源，并恢复进入前的灯效（失败只告警）。

        设备不可用路径（拔线 / USB 重新枚举）必须快速失败：死句柄上的
        ``close()`` 可能卡在收割在途 IO 上（``NativeHidChannel.close`` 最长等 2s），
        一旦在这里阻塞，音乐监督线程就会错过设备重连窗口，表现为「掉线后不自动
        恢复」。所以设备离线时缩短 close 等待上限；灯效恢复也由 lighting 侧先查
        设备状态快速失败，不向死句柄发命令。
        """
        online = self._device_connected()
        # 1) 先停 ACK 清道夫：它和发送器共用同一个原生读句柄
        drainer = self._drainer
        self._drainer = None
        if drainer is not None:
            try:
                drainer.stop()
            except Exception:  # noqa: BLE001
                pass
        # 2) 关闭发送通道：设备在线给宽限收割在途 IO；已断开则快速失败
        if sender is not None:
            if self._sender is sender:
                self._sender = None
            _call_with_timeout(
                sender.close,
                CLOSE_SENDER_TIMEOUT if online else CLOSE_SENDER_TIMEOUT_OFFLINE,
                "关闭帧流发送通道",
            )
        # 3) 关闭音频采集
        if capture is not None:
            _call_with_timeout(
                capture.close,
                CLOSE_CAPTURE_TIMEOUT if online else CLOSE_CAPTURE_TIMEOUT_OFFLINE,
                "关闭音频采集",
            )
        self._capture = None
        # 4) 恢复进入帧流前的灯效。设备不可用时不阻塞：lighting.restore_effect
        #    内部会先查设备状态快速失败（并记录 skipped-offline，供 shell 退出 /
        #    stop_music 的「恢复已发生」确认），不会发命令白等超时。
        snap = self._snapshot
        self._snapshot = None
        if snap:
            try:
                lighting.restore_effect(self.device, snap["before"])
            except Exception:  # noqa: BLE001
                pass

    def _note_recovery(self, reason: str, failures: int) -> None:
        """会话中断：累计恢复次数、清空预览并更新健康状态（前端据此显示恢复中）。"""
        self.recoveries += 1
        self.last_recovery = time.time()
        self._reset_measured_fps()
        self.last_colors = {}
        self.level = 0.0
        self.bands = [0.0, 0.0, 0.0]
        self.levels32 = [0.0] * 32
        online = self._device_connected()
        self._set_health("recovering" if online else "waiting-device")
        if failures == 1 or failures % 5 == 0:
            log.warning("音乐律动会话中断（%s），第 %d 次自动恢复（键盘%s）",
                        reason, self.recoveries, "在线" if online else "离线，等待重连")

    def _run_session(self, first: bool = False) -> str:
        """跑一段「音频采集 + 帧流」会话，返回结束原因。

        ``stop`` = 用户停止；``first-error`` = 首次启动失败（start() 抛给调用方）；
        ``audio-error`` / ``audio-stalled`` = 音频采集中断/卡死；``send-error`` =
        HID 帧流连续失败（设备挂起/拔线）；``frame-stall`` = 帧流看门狗判定卡死；
        ``session-error`` = 会话建立失败。
        """
        capture = None
        sender = None
        # 新会话从干净的看门狗状态开始（上一轮卡死标记/强制重建请求不能带进来）
        self._stall_since = None
        self._stall_escalated = False
        self._force_rebuild.clear()
        self._last_frame_ts = None
        self._session_started_ts = None
        if not first and not self._device_connected():
            # 键盘还没回来：不要反复开关音频采集，等 monitor 线程自动重连。
            self.last_error = "键盘已断开，等待重新连接"
            return "session-error"
        try:
            capture = self._open_capture()
            self._capture = capture
            self.audio_backend = getattr(capture, "_backend", "") or ""
            analyzer = Analyzer(capture.samplerate)
            self._engine = self._new_engine()
            self._snapshot = lighting.ensure_frame_mode(self.device)
            # 帧流走原生通道（Windows）：hidapi 逐包 ACK 只能到 ~10fps，原生通道实测 20fps
            self._sender = sender = lighting.FrameSender(self.device)
            self._session_ok = True
            self._session_started_ts = time.monotonic()
            self._set_health("ok")
            if first:
                self._ready.set()
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.errors += 1
            self._close_session(capture, sender)
            if first:
                self._start_error = str(exc)
                self._ready.set()
                self._set_health("stopped")
                # 关键：把具体原因写进日志，否则只剩 HTTP 400，支持包看不出是哪个后端失败
                log.error("音乐律动启动失败: %s", exc)
                return "first-error"
            log.warning("音乐律动会话建立失败: %s", exc)
            return "session-error"

        self.timing = {"read": 0.0, "analyze": 0.0, "send": 0.0, "frames": 0}
        next_t = self._clock()
        last_frame: Optional[float] = None
        consecutive = 0
        try:
            while not self._stop.is_set():
                # 帧流看门狗要求重建（>2s 无成功帧）：立即退出会话走自动恢复。
                # 正常情况看门狗只置标记，由这里在下一轮循环生效；只有主循环卡死在
                # HID 调用里时，看门狗才会旁路强关通道把 send() 逼成异常。
                if self._force_rebuild.is_set():
                    self._force_rebuild.clear()
                    self.last_error = "帧流看门狗触发会话重建"
                    log.warning("帧流看门狗触发会话重建（连续 %.1fs 无成功帧）",
                                self._frame_age() or 0.0)
                    return "frame-stall"
                frame_start = self._clock()
                target_fps = _clamp_fps(self.fps)
                period = 1.0 / target_fps
                # 动画时间步长 = 实际帧间隔 × 20（20fps → 1.0；66fps → ≈0.303）
                dt = period if last_frame is None else frame_start - last_frame
                last_frame = frame_start
                dt_scale = _dt_scale(dt)
                # 音频采集卡死检测：采集线程仍活着但不再出新数据（系统待机、
                # 默认输出设备被拔掉/切换后 WASAPI 会永久阻塞，且不报错）。
                last_data = getattr(capture, "last_data_ts", None)
                if last_data is not None:
                    stall = time.monotonic() - last_data
                    if stall > AUDIO_STALL_TIMEOUT:
                        self.last_error = f"音频采集卡死（{stall:.1f}s 无新数据）"
                        log.warning("音频采集卡死（%.1fs 无新数据），重建采集", stall)
                        return "audio-stalled"
                wait_ack, _ = _send_strategy(target_fps)
                if wait_ack:
                    if self._drainer is not None:
                        # 热更新回 ≤30fps：先停清道夫，避免两个线程同时读同一句柄
                        self._drainer.stop()
                        self._drainer = None
                    drain_now = 0
                else:
                    # ≥60fps：连写 7 包，回包交给清道夫异步读；起不来才回退同步 drain
                    drain_now = 0 if self._ensure_drainer() else BURST_SYNC_DRAIN
                self.send_mode = ("ack" if wait_ack
                                  else ("burst+drainer" if self._drainer is not None
                                        else "burst+drain"))
                try:
                    t_a = time.perf_counter()
                    samples = capture.read(2048)
                    t_b = time.perf_counter()
                except Exception as exc:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = f"音频采集中断: {exc}"
                    log.warning("音频采集中断: %s", exc)
                    return "audio-error"
                try:
                    analysis = analyzer.analyze(samples, dt_scale=dt_scale)
                    t_c = time.perf_counter()
                    self.level = analysis["amp"]
                    self.bands = analysis["bands"]
                    self.levels32 = analysis.get("bands32") or []
                    payload = (self._engine.tick(analysis["amp1000"], analysis.get("bands32"),
                                                 dt_scale=dt_scale)
                               if self._engine else b"")
                    # 记录本帧逐键颜色：前端「官方方案」预览直接回放（与设备实发帧同源）
                    self.last_colors = self._engine.last_colors if self._engine else {}
                    if self._sender is not None:
                        # ≤30fps 逐包 ACK；≥60fps 连写 7 包（回包由清道夫线程读走；
                        # 清道夫起不来时才在帧末同步 drain）
                        self._sender.send(
                            payload, self.frames & 0xFF,
                            wait_ack=wait_ack,
                            ack_timeout=0.006,
                            drain=drain_now,
                        )
                    t_d = time.perf_counter()
                except Exception as exc:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = str(exc)
                    consecutive += 1
                    if consecutive == 1:
                        log.warning("音乐帧发送失败: %s", exc)
                    if consecutive >= SEND_ERROR_LIMIT:
                        log.warning("音乐帧连续发送失败 %d 次，重建 HID 通道: %s",
                                    consecutive, exc)
                        return "send-error"
                else:
                    consecutive = 0
                    tm = self.timing
                    tm["read"] += t_b - t_a
                    tm["analyze"] += t_c - t_b
                    tm["send"] += t_d - t_c
                    tm["frames"] += 1
                    self.last_payload = payload
                    self.frames += 1
                    self._last_frame_ts = time.monotonic()
                    # 实测帧率用单调时钟的「发送完成」时间戳（可注入假时钟做单测）
                    self._record_frame_time(self._clock())
                    if self.frames % 200 == 0:
                        n = max(1, self.timing.get("frames", 1))
                        log.debug("音乐帧流: %d 帧, 平均 send=%.1fms analyze=%.1fms, "
                                  "target=%sfps measured=%sfps dtScale=%.3f, amp=%.2f",
                                  self.frames, self.timing["send"] / n * 1000,
                                  self.timing["analyze"] / n * 1000, target_fps,
                                  self.measured_fps, dt_scale, self.level)
                # ----------------------------------------------------------
                # 节奏：按目标 period 用单调时钟排绝对 deadline。
                # * 周期每帧重算 → 运行中热更新 fps 立即生效；
                # * 滞后超过 1 个 period 时重置 next_t（不补发、不突发）；
                # * fps 档位变化时从本帧起重新排期，不背旧周期的欠账。
                # ----------------------------------------------------------
                now = self._clock()
                target_now = _clamp_fps(self.fps)
                period_now = 1.0 / target_now
                if target_now != self._pace_fps or self._pace_fps == 0:
                    self._pace_fps = target_now
                    next_t = frame_start + period_now
                else:
                    next_t += period_now
                if now - next_t > period_now:
                    self._late_frames += 1
                    next_t = now
                elif next_t > now:
                    self._sleep(next_t - now)
        finally:
            self._close_session(capture, sender)
        return "stop"

    def _cleanup_loop(self) -> None:
        """监督循环退出：停清道夫/看门狗/保活，清预览与实测值，健康状态归 stopped。"""
        self._stop_watchdog()
        if self._drainer is not None:
            try:
                self._drainer.stop()
            except Exception:  # noqa: BLE001
                pass
            self._drainer = None
        self.last_colors = {}
        self._reset_measured_fps()
        self._last_frame_ts = None
        self._sender = None
        self._capture = None
        self._stall_since = None
        self._stall_escalated = False
        self._force_rebuild.clear()
        keepalive = self._keepalive
        self._keepalive = None
        if keepalive is not None:
            try:
                keepalive.stop()
            except Exception:  # noqa: BLE001
                pass
        self._set_health("stopped")

    def _loop(self) -> None:
        """监督循环：会话中断自动重建，键盘掉线时等重连后继续，直到用户停止。"""
        try:
            # WASAPI/COM 需要线程内初始化（soundcard 打开设备/循环采集依赖 COM）
            if platform.system() == "Windows":
                try:
                    import ctypes

                    ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
                except Exception:
                    pass
            first = True
            failures = 0
            while not self._stop.is_set():
                if not first and not self._device_connected():
                    # 键盘掉线（USB 重新枚举 / Win-Mac 模式切换）：状态层 monitor
                    # 线程负责重连，这里短轮询等待。不能按失败次数退避 —— 重连可能在
                    # 5s 退避睡眠中间完成，那样恢复就会超出「重连后 ≤5s」的预算；
                    # 设备未在线时 _run_session 也只会立即返回 session-error。
                    self._set_health("waiting-device")
                    if self._stop.wait(DEVICE_WAIT_POLL):
                        break
                    continue
                was_ok = self._session_ok
                reason = self._run_session(first=first)
                first = False
                if self._stop.is_set() or reason == "stop":
                    break
                if reason == "first-error":
                    break
                if reason == "session-error" and not was_ok:
                    # 会话还没建立成功（设备未就绪 / 音频设备暂时不可用）：
                    # 只按退避等待重试，不累计「自动恢复」次数，避免 UI 数字乱涨。
                    online = self._device_connected()
                    self._set_health("recovering" if online else "waiting-device")
                    if not online:
                        if self._stop.wait(DEVICE_WAIT_POLL):
                            break
                        continue
                    delay = min(RECOVER_MAX_DELAY,
                                RECOVER_MIN_DELAY * (2 ** min(failures, 3)))
                    failures += 1
                    if self._stop.wait(delay):
                        break
                    continue
                self._session_ok = False
                # 建立成功过的会话中断：退避从最短档重新开始（重连/重建要快）；
                # 只有「连续建立不起来」才逐步拉长，避免一次长时运行后中断要等 5s。
                failures = 1 if was_ok else failures + 1
                self._note_recovery(reason, failures)
                delay = min(RECOVER_MAX_DELAY,
                            RECOVER_MIN_DELAY * (2 ** min(failures - 1, 3)))
                if self._stop.wait(delay):
                    break
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = f"音乐律动线程异常: {exc}"
            log.exception("音乐律动线程异常")
        finally:
            self._cleanup_loop()

    def update(self, mode: Optional[int] = None, amplitude: Optional[int] = None,
               backmode: Optional[int] = None, backmode_brightness: Optional[int] = None,
               fps: Optional[int] = None, color: Optional[str] = None) -> dict:
        """运行中热更新参数（显示模式 / 背景模式 / 背景亮度 / 振幅 / 帧率 / LED 颜色），
        不打断音频采集。color=None 表示本次不改（显式传 "default" 才会恢复官方配色）。
        """
        engine = self._engine
        if not self.running:
            raise MK87Error("音乐律动未在运行，无法热更新参数")
        if engine is None:
            # 自动恢复中（音频/键盘重建会话）：参数先缓存在 player 上，
            # 下一次会话建立时由 _new_engine() 带进新引擎，界面上的调节不丢。
            if mode is not None:
                self.requested_mode = int(mode)
                self.mode = int(mode) if int(mode) in IMPLEMENTED_MODES else 13
            if color is not None:
                self.color = normalize_color_id(color)
            if amplitude is not None:
                self.amplitude_ui = int(_clamp(int(amplitude), 1, 100))
            if backmode is not None or backmode_brightness is not None:
                self.backmode = int(_clamp(
                    int(self.backmode if backmode is None else backmode), 0, 11))
                self.backmode_brightness = int(_clamp(
                    int(self.backmode_brightness if backmode_brightness is None
                        else backmode_brightness), 1, 100))
            if fps is not None:
                target = _clamp_fps(fps)
                if target != self.fps:
                    self.fps = target
                    self._reset_measured_fps()
                    self._pace_fps = 0
                    self._late_frames = 0
            log.info("音乐律动恢复中，参数已缓存: mode=%s(请求 %s) backmode=%s bb=%s "
                     "amp=%s color=%s targetFps=%s",
                     self.mode, self.requested_mode, self.backmode,
                     self.backmode_brightness, self.amplitude_ui, self.color, self.fps)
            return self.status()
        if mode is not None:
            self.requested_mode = int(mode)
            engine.set_mode(int(mode))
            self.mode = engine.mode
        if color is not None:
            self.color = engine.set_color(color)
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
            target = _clamp_fps(fps)
            if target != self.fps:
                self.fps = target
                # 换档后旧窗口的样本会把实测值拖在旧档位附近 ~2s，直接清空重测
                self._reset_measured_fps()
                self._pace_fps = 0
                self._late_frames = 0
        log.info("音乐律动热更新: mode=%s(请求 %s) backmode=%s bb=%s amp=%s color=%s targetFps=%s",
                 self.mode, self.requested_mode, self.backmode,
                 self.backmode_brightness, self.amplitude_ui, self.color, self.fps)
        return self.status()

    def stop(self) -> dict:
        self._user_stopped = True
        if self.running:
            log.info("音乐律动停止: 共 %d 帧, %d 错误, 自动恢复 %d 次, 看门狗触发 %d 次",
                     self.frames, self.errors, self.recoveries, self.stalls)
        self._stop.set()
        # 先停看门狗再等业务线程：避免退出过程中看门狗又触发一次「重建」
        self._stop_watchdog()
        if self._thread is not None:
            self._thread.join(timeout=2.5)
            self._thread = None
        self._stop_keepalive()
        self._set_health("stopped")
        self._reset_measured_fps()
        return self.status()

    def status(self) -> dict:
        tm = self.timing
        n = max(1, int(tm.get("frames", 0)))
        frame_age = self._frame_age()
        keepalive = self._keepalive
        return {
            "running": self.running,
            # 健康状态（v0.1.8.4）：starting / ok / recovering / waiting-device / stopped
            "health": self.health,
            # 自动恢复次数与最近一次恢复开始时间（前端显示「已自动恢复 N 次」）
            "recoveries": int(self.recoveries),
            "lastRecovery": self.last_recovery,
            # 帧流看门狗触发次数（>2s 无成功帧 → 重建会话；排障字段，前端忽略）
            "stalls": int(self.stalls),
            # 距最后一帧成功下发多少毫秒（运行中且出过帧才有；前端可显示卡顿）
            "frameAgeMs": (int(frame_age * 1000) if frame_age is not None else None),
            # 保后台是否生效（阻止系统空闲休眠）；键盘是否在线；音频是否回退默认
            "keepAwake": bool(getattr(keepalive, "active", False)) if keepalive else False,
            "deviceConnected": self._device_connected(),
            "audioFallback": bool(self._audio_fallback),
            # 是否用户主动停止（区别「意外停止」，仅诊断用）
            "stoppedByUser": bool(self._user_stopped),
            "mode": self.mode,
            "requestedMode": self.requested_mode,
            "modes": MODES,
            "amplitude": self.amplitude_ui,
            "backmode": self.backmode,
            "backmodeBrightness": self.backmode_brightness,
            # LED 颜色覆盖 id（本工具增强）；default = 官方采样配色
            "color": self.color,
            "implementedModes": sorted(IMPLEMENTED_MODES),
            # 「官方方案」下拉：21 项（官方 v1 的 12 个 + 补回的 14~22 + 100）；这里是其中
            # 主机侧已实现渲染器的 20 个（100 屏光联动未移植）
            "officialModes": list(V1_DISPLAY_MODES),
            "officialImplementedModes": list(V1_IMPLEMENTED_MODES),
            "sensitivity": self.sensitivity,
            # 契约：fps = 运行时实测值（float，未运行/样本不足 → None）；
            # targetFps = 用户配置的目标档位（int，前端原生帧率控件回填用）。
            "fps": self.measured_fps if self.running else None,
            "targetFps": int(self.fps),
            # 发送策略诊断：ack / burst / burst+drainer（真机验证用，前端忽略）
            "sendMode": self.send_mode,
            "deviceId": self.device_id,
            # 实际音频采集后端（Linux: libpulse / parec；Windows 为空），排障用
            "audioBackend": self.audio_backend,
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
                # 排期滞后超过 1 个 period 而被重置的次数（66fps 真机调优用）
                "lateFrames": int(self._late_frames),
            },
            "supported": self.device.transport == "usb",
        }
