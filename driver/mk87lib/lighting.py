"""灯效：19 种模式元数据、16 字节效果参数、逐键自定义灯、0x32 逐键帧流。

真机要点（docs/TEST-REPORT.md §2/§5）：
* SET_LED_EFFECT(0x23) 16 字节 payload，字段见 :func:`device.MK87Device.set_led_effect`；
* 亮度 identity 1..6，其中 **1 = 全灭**，工具侧建议 2..6（官方 UI 显示 1..6）；
* 逐键自定义灯 = SET_CUSTOM_LED_DATA(0x24) 512 字节 = 128 × [idx, R, G, B]；
* 自定义模式族 mode ∈ {20, 21, 128} 共用同一张表；128 是 UI 上的「自定义」；
* 逐键帧流 cmd 0x32：每帧 87 键 × 4 字节 [keyValue, R, G, B]，按官方 keyList 行优先排列；
  必须先切到 mode 20/21/128 才显示，停发约 5 秒后回落到自定义表。
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from . import const
from .errors import MK87Error

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RGB = Tuple[int, int, int]
CUSTOM_FAMILY = (20, 21, 128)
CUSTOM_MODE = 128


# ----------------------------------------------------------------------
# 元数据
# ----------------------------------------------------------------------
_data: Optional[dict] = None


def data() -> dict:
    global _data
    if _data is None:
        with open(os.path.join(DATA_DIR, "lighting_modes.json"), encoding="utf-8") as f:
            _data = json.load(f)
    return _data


def get_modes() -> List[dict]:
    return data()["modes"]


def get_mode_meta(mode: int) -> Optional[dict]:
    for m in data()["modes"]:
        if m["mode"] == int(mode):
            return m
    return None


def mode_name(mode: int) -> str:
    m = get_mode_meta(mode)
    return m["name"] if m else f"模式 {mode}"


def key_order() -> List[int]:
    """官方 keyList 行优先的 87 个键槽（= 帧流里的 keyValue 顺序 = ledId）。"""
    from . import keymap

    rows = keymap.tables().layout["rows"]
    return [k["slot"] for row in rows for k in row]


# ----------------------------------------------------------------------
# 效果参数
# ----------------------------------------------------------------------
def clamp_brightness(v: int) -> int:
    return max(1, min(6, int(v)))


def clamp_speed(v: int) -> int:
    return max(1, min(6, int(v)))


def clamp_direction(v: int) -> int:
    return max(0, min(3, int(v)))


def get_effect(device) -> dict:
    e = device.get_led_effect()
    mode = e["mode"]
    meta = get_mode_meta(mode)
    return {
        "mode": mode,
        "name": meta["name"] if meta else f"模式 {mode}",
        "rgb": [e["red"], e["green"], e["blue"]],
        "secondary": list(e["secondary"]),
        "colorMode": e["colorMode"],
        "brightness": e["brightness"],
        "speed": e["speed"],
        "direction": e["direction"],
        "effectModeType": e["effectModeType"],
        "isCustom": mode in CUSTOM_FAMILY,
        "meta": meta,
        "raw": e["raw"].hex(),
    }


def set_effect(device, *,
               mode: int,
               rgb: RGB = (255, 255, 255),
               secondary: RGB = (0, 0, 0),
               color_mode: int = 1,
               brightness: int = 5,
               speed: int = 3,
               direction: int = 0,
               effect_mode_type: int = 0) -> bytes:
    mode = int(mode)
    if not 0 <= mode <= 255:
        raise MK87Error(f"灯效模式越界: {mode}")
    meta = get_mode_meta(mode)
    ui = (meta or {}).get("ui") or {}
    if meta:
        brightness = clamp_brightness(brightness)
        speed = clamp_speed(speed)
        direction = clamp_direction(direction)
    return device.set_led_effect(
        mode=mode,
        red=int(rgb[0]), green=int(rgb[1]), blue=int(rgb[2]),
        secondary=(int(secondary[0]), int(secondary[1]), int(secondary[2])),
        color_mode=int(color_mode),
        brightness=brightness,
        speed=speed,
        direction=direction,
        effect_mode_type=int(effect_mode_type),
    )


# ----------------------------------------------------------------------
# 逐键自定义灯
# ----------------------------------------------------------------------
def get_custom(device) -> dict:
    colors = device.get_custom_colors()
    return {
        "colors": {str(k): list(v) for k, v in sorted(colors.items())},
        "mode": device.get_led_effect()["mode"],
        "family": list(CUSTOM_FAMILY),
    }


def set_custom(device, colors: Dict[int, RGB], apply: bool = True,
               brightness: int = 5, speed: int = 3) -> dict:
    buf = bytearray(512)
    for slot_raw, rgb in colors.items():
        slot = int(slot_raw)
        if not 0 <= slot < 128:
            raise MK87Error(f"LED 槽号越界: {slot}")
        r, g, b = (int(x) & 0xFF for x in rgb)
        buf[slot * 4:slot * 4 + 4] = bytes([slot, r, g, b])
    read_back = device.write_custom_led_data(bytes(buf))
    result = {
        "ok": read_back == bytes(buf),
        "readback": read_back.hex(),
    }
    if apply:
        cur = device.get_led_effect()
        device.set_led_effect(
            mode=CUSTOM_MODE,
            red=255, green=255, blue=255,
            color_mode=1,
            brightness=clamp_brightness(brightness or cur["brightness"]),
            speed=clamp_speed(speed or cur["speed"]),
            direction=0,
        )
        result["appliedMode"] = CUSTOM_MODE
    return result


# ----------------------------------------------------------------------
# 逐键帧流（cmd 0x32）
# ----------------------------------------------------------------------
#: 逐键帧流使用 GET_LED_DATA(0x32) 命令（真机验证，见 docs/music-rhythm.md §5.1）
FRAME_CMD = const.CMD["GET_LED_DATA"]


def build_frame_payload(colors: Dict[int, RGB]) -> bytes:
    """{slot: (r,g,b)} → 87 键 × 4 字节（按官方 keyList 顺序）。"""
    out = bytearray()
    for slot in key_order():
        r, g, b = colors.get(slot, (0, 0, 0))
        out += bytes([slot & 0xFF, int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF])
    return bytes(out)


def build_frame_packets(payload: bytes, body_len: int, frame_index: int = 0) -> List[bytes]:
    chunk = max(1, body_len - 8)
    total = max(1, math.ceil(len(payload) / chunk))
    pkts = []
    for k in range(total):
        addr = k * chunk
        part = payload[addr:addr + chunk]
        pkt = bytearray(body_len + 1)
        pkt[0] = 0
        pkt[1] = 0xAA
        pkt[2] = FRAME_CMD
        pkt[3] = len(part) & 0xFF
        pkt[4] = addr & 0xFF
        pkt[5] = (addr >> 8) & 0xFF
        pkt[6] = frame_index & 0xFF
        pkt[7] = 1 if k == total - 1 else 0
        pkt[8] = 0
        pkt[9:9 + len(part)] = part
        pkts.append(bytes(pkt))
    return pkts


def send_frame(device, payload: bytes, frame_index: int = 0,
               wait_ack: bool = True, timeout: float = 0.04) -> int:
    """发送一帧逐键颜色；返回成功 ACK 的包数。不持锁太久（每包写后立即读）。"""
    iface = device.protocol.iface
    body = iface.info.payload_len
    packets = build_frame_packets(payload, body, frame_index)
    acks = 0
    with device._lock:  # noqa: SLF001
        for pkt in packets:
            iface.write_report(pkt)
            if not wait_ack:
                continue
            deadline = time.time() + timeout
            while time.time() < deadline:
                r = iface.read_normalized(timeout=max(0.001, deadline - time.time()))
                if r is None:
                    break
                if len(r) >= 2 and r[0] == 0x55:
                    acks += 1
                    break
    return acks


def ensure_frame_mode(device) -> dict:
    """确保设备处于自定义族模式（帧流显示的前提），返回进入前的灯效快照。"""
    cur = device.get_led_effect()
    snapshot = bytes(cur["raw"])
    if cur["mode"] not in CUSTOM_FAMILY:
        device.set_led_effect(
            mode=CUSTOM_MODE,
            red=255, green=255, blue=255,
            color_mode=1,
            brightness=clamp_brightness(cur["brightness"]),
            speed=clamp_speed(cur["speed"]),
            direction=0,
        )
    return {"before": snapshot, "wasMode": cur["mode"]}


def restore_effect(device, snapshot: bytes) -> None:
    if snapshot:
        try:
            device.request(const.CMD["SET_LED_EFFECT"], bytes(snapshot), content_size=16, timeout=0.8)
        except Exception:
            pass


class FrameStreamer:
    """按固定 FPS 渲染并下发逐键帧的后台流（音乐/自定义动画共用）。"""

    def __init__(self, device, render: Callable[[], Dict[int, RGB]], fps: int = 20):
        self.device = device
        self.render = render
        self.fps = max(1, min(60, int(fps)))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.frames = 0
        self.acks = 0
        self.errors = 0
        self.last_error = ""
        self._snapshot: Optional[dict] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._snapshot = ensure_frame_mode(self.device)
        self._thread = threading.Thread(target=self._loop, name="mk87-frame-stream", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        period = 1.0 / self.fps
        frame_index = 0
        next_t = time.time()
        while not self._stop.is_set():
            t0 = time.time()
            try:
                colors = self.render()
                payload = build_frame_payload(colors)
                sent = send_frame(self.device, payload, frame_index)
                self.acks += sent
                self.frames += 1
                frame_index = (frame_index + 1) & 0xFF
            except Exception as exc:  # noqa: BLE001
                self.errors += 1
                self.last_error = str(exc)
                if self.errors > 30:
                    break
                time.sleep(0.05)
            next_t += period
            sleep = next_t - time.time()
            if sleep < -period:
                next_t = time.time()
                sleep = 0
            if sleep > 0:
                time.sleep(sleep)
        # 停止后恢复进入前的灯效
        if self._snapshot:
            restore_effect(self.device, self._snapshot["before"])

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "fps": self.fps,
            "frames": self.frames,
            "acks": self.acks,
            "errors": self.errors,
            "lastError": self.last_error,
        }
