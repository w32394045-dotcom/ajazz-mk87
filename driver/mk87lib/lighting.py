"""灯效：19 种模式元数据、16 字节效果参数、逐键自定义灯、0x32 逐键帧流。

真机要点（docs/TEST-REPORT.md §2/§5）：
* SET_LED_EFFECT(0x23) 16 字节 payload，字段见 :func:`device.MK87Device.set_led_effect`；
* 亮度 identity 1..6，其中 **1 = 全灭**，工具侧建议 2..6（官方 UI 显示 1..6）；
* 逐键自定义灯 = SET_CUSTOM_LED_DATA(0x24) 512 字节 = 128 × [idx, R, G, B]；
* 自定义模式族 mode ∈ {20, 21, 128} 共用同一张表；128 是 UI 上的「自定义」；
  **fw1.19 写 128 会被固件归零（回读 mode=0）**，帧流展示入口改用 20/21（`ensure_frame_mode`）；
* 逐键帧流 cmd 0x32：每帧 87 键 × 4 字节 [keyValue, R, G, B]，按官方 keyList 行优先排列；
  必须先切到 mode 20/21/128 才显示，停发约 5 秒后回落到自定义表。
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from . import const
from .errors import MK87Error

log = logging.getLogger("mk87.lighting")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RGB = Tuple[int, int, int]
CUSTOM_FAMILY = (20, 21, 128)
CUSTOM_MODE = 128
#: 帧流展示入口：fw1.19 写 128 会被固件归零（回读 mode=0），改用官方自定义族 20/21。
#: 优先 20；若回读异常再试 21（两者共用同一张逐键表）。
FRAME_MODES = (20, 21)
#: 可以安全写回的灯效模式：1..19 官方效果 + 自定义族 20/21/128
VALID_EFFECT_MODES = frozenset(range(1, 20)) | frozenset(CUSTOM_FAMILY)

#: 最近一次 restore_effect 的结果（shell 退出时据此等待恢复完成，见 shell.py）
_restore_lock = threading.Lock()
_restore_state: Dict[str, object] = {"ts": 0.0, "mode": None, "result": "none"}


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


def colors_have_light(colors: Optional[Dict[int, tuple]]) -> bool:
    """逐键颜色表里是否存在非黑槽（空槽读回是 [idx,0,0,0]）。"""
    for rgb in (colors or {}).values():
        try:
            if max(int(rgb[0]), int(rgb[1]), int(rgb[2])) > 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def resolve_is_custom(mode: int, colors: Optional[Dict[int, tuple]] = None) -> bool:
    """isCustom 判定（纯函数，便于单测）。

    * 自定义族 20/21/128 → True；
    * mode 回读 0（fw1.19 把 128 固化成自定义族后回读 0）且逐键表有非黑颜色 → True；
    * 其它情况 → False。
    """
    mode = int(mode)
    if mode in CUSTOM_FAMILY:
        return True
    if mode == 0:
        return colors_have_light(colors)
    return False


#: 只在「mode 回读 0 → 判定为自定义态」状态切换时打一次 info，避免每次请求刷日志
_custom_fallback_logged = False


def get_effect_with_custom_fallback(device) -> dict:
    """读取灯效；mode 回读 0 时补读逐键表判断是否其实停在自定义逐键态。

    前端目前不消费这个兜底，但 API 语义更准，也方便日志诊断。
    2.4G 下不探测：GET_ALL_LIGHTS_RGB(0x33) 在 32B 报告上要拆 ~22 包，
    官方 2.4G 读灯走 0x37（5 包），这里不值得为一次页面加载付出这个代价。
    """
    global _custom_fallback_logged
    effect = get_effect(device)
    if int(effect["mode"]) != 0:
        _custom_fallback_logged = False
        return effect
    transport = str(getattr(getattr(device, "status", None), "transport", "") or "")
    if transport != "usb":
        return effect
    try:
        colors = device.get_lights_frame()
    except Exception as exc:  # noqa: BLE001
        log.debug("mode 回读 0，补读逐键灯表失败: %s", exc)
        return effect
    if resolve_is_custom(0, colors):
        effect["isCustom"] = True
        if not _custom_fallback_logged:
            lit = sum(1 for rgb in colors.values() if max(int(x) for x in rgb[:3]) > 0)
            log.info("灯效 mode 回读 0，但逐键灯表有 %d 个非黑槽 → 判定为自定义逐键态"
                     "（isCustom=true）", lit)
            _custom_fallback_logged = True
    return effect


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
        # fw1.19 实测：写 128 后回读 mode=0（被固件归零，灯仍停在自定义逐键表）。
        # 只有日志告警，不自动改写，避免误切到其它效果。
        time.sleep(0.2)
        try:
            backed = int(device.get_led_effect()["mode"])
        except Exception as exc:  # noqa: BLE001
            log.debug("自定义灯效写后回读失败: %s", exc)
            backed = CUSTOM_MODE
        if backed == 0:
            log.warning("mode 128 被固件归零，当前为自定义态（回读 mode=0，逐键表仍生效）")
        result["readbackMode"] = backed
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
               wait_ack: bool = True, timeout: float = 0.04, drain: int = 0) -> int:
    """发送一帧逐键颜色；返回成功 ACK 的包数。

    wait_ack=True：逐包等 ACK（会受 USB 轮询间隔限制，实测约 9ms/包 → 上限 ~14fps）；
    wait_ack=False：连续写 7 包（约 8ms/帧），帧末最多读 drain 个回包防止输入队列堆积，
                  音乐律动 20fps 走这条路径（真机实测 20fps、回读一致率 96.6%）。
    """
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
        if not wait_ack and drain:
            for _ in range(int(drain)):
                if iface.read_normalized(timeout=0.001) is None:
                    break
    return acks


def ensure_frame_mode(device) -> dict:
    """确保设备处于自定义族模式（帧流显示的前提），返回进入前的灯效快照。

    fw1.19 实测：写 ``mode=128`` 会被固件固化成自定义族并回读 0，因此展示入口
    改用 20/21（官方自定义族，共用同一张逐键表）。每次写入后等 200ms 回读确认；
    回读异常（如仍是 0）只告警，不中断帧流——逐键帧通常仍能显示。
    """
    cur = device.get_led_effect()
    snapshot = bytes(cur["raw"])
    if cur["mode"] in CUSTOM_FAMILY:
        return {"before": snapshot, "wasMode": cur["mode"], "entryMode": cur["mode"]}
    brightness = clamp_brightness(cur["brightness"])
    speed = clamp_speed(cur["speed"])
    entry_mode = None
    for mode in FRAME_MODES:
        device.set_led_effect(
            mode=mode,
            red=255, green=255, blue=255,
            color_mode=1,
            brightness=brightness,
            speed=speed,
            direction=0,
        )
        time.sleep(0.2)
        try:
            backed = int(device.get_led_effect()["mode"])
        except Exception as exc:  # noqa: BLE001
            log.warning("帧流入口 mode=%d 写后回读失败: %s", mode, exc)
            continue
        if backed in CUSTOM_FAMILY:
            entry_mode = mode
            break
        log.warning("帧流入口 mode=%d 写后回读异常: mode=%s（期望 %s），继续发送帧流",
                    mode, backed, "/".join(str(m) for m in CUSTOM_FAMILY))
    if entry_mode is None:
        log.warning("帧流入口写入 20/21 后回读均不在自定义族（可能被固件归零），"
                    "仍按自定义态继续发送逐键帧")
    return {"before": snapshot, "wasMode": cur["mode"], "entryMode": entry_mode}


def _record_restore(mode, result: str) -> None:
    with _restore_lock:
        _restore_state.update({"ts": time.time(), "mode": mode, "result": result})


def restore_state() -> dict:
    """最近一次 :func:`restore_effect` 的结果快照（shell 退出时等待恢复用）。"""
    with _restore_lock:
        return dict(_restore_state)


def restore_effect(device, snapshot: bytes, fallback: Optional[bytes] = None) -> bool:
    """把进入帧流前的灯效快照写回；快照无效时绝不原样写设备。

    真机事故（2026-11-02 22:45）：进程被关机杀死时快照里 mode 已被污染成 0，
    旧实现原样写回，键盘永远停在自定义逐键表。现在的规则：

    * 快照首字节（mode）必须在 1..19 ∪ {20,21,128}，否则跳过并 ``log.warning``；
    * 调用方可传 16 字节 ``fallback`` 指定安全值，仅在快照无效时使用；
    * 返回是否真的写入了设备。
    """
    raw = bytes(snapshot or b"")
    mode = int(raw[0]) if raw else -1
    # 设备不可用（拔线 / USB 重新枚举中）时快速失败：命令必然失败，还会白等
    # 设备锁和命令超时；音乐停止 / 外壳退出在设备离线路径上必须能快速返回，
    # 不能因为「恢复灯效」把调用方卡住（否则掉线后自动恢复的 5s 预算被吃掉）。
    status = getattr(device, "status", None)
    offline = (getattr(status, "connected", None) is False) if status is not None else False
    if not offline and hasattr(device, "protocol") and getattr(device, "protocol") is None:
        offline = True
    if offline:
        _record_restore(mode, "skipped-offline")
        log.debug("设备未连接，跳过灯效恢复（mode=%s）", mode)
        return False
    if len(raw) >= 16 and mode in VALID_EFFECT_MODES:
        try:
            device.request(const.CMD["SET_LED_EFFECT"], raw[:16],
                           content_size=16, timeout=0.8)
            _record_restore(mode, "restored")
            log.info("灯效快照已恢复: mode=%d", mode)
            return True
        except Exception as exc:  # noqa: BLE001
            _record_restore(mode, f"error: {exc}")
            log.warning("恢复灯效快照失败（mode=%d）: %s", mode, exc)
            return False

    fb = bytes(fallback or b"")
    fb_mode = int(fb[0]) if fb else -1
    if len(fb) >= 16 and fb_mode in VALID_EFFECT_MODES:
        try:
            device.request(const.CMD["SET_LED_EFFECT"], fb[:16],
                           content_size=16, timeout=0.8)
            _record_restore(fb_mode, "fallback")
            log.warning("灯效快照无效（mode=%s），已用 fallback mode=%d 恢复", mode, fb_mode)
            return True
        except Exception as exc:  # noqa: BLE001
            _record_restore(fb_mode, f"fallback-error: {exc}")
            log.warning("恢复 fallback 灯效失败（mode=%d）: %s", fb_mode, exc)
            return False

    _record_restore(mode, "skipped-invalid")
    log.warning("快照无效（mode=%s，首 16B=%s），跳过恢复：不把被污染的 mode 写回设备",
                mode, raw[:16].hex() or "(空)")
    return False


class FrameSender:
    """音乐帧流专用发送器：Windows 原生 WriteFile/overlapped ReadFile。

    背景（真机实测）：hidapi 在协议接口上逐包写+读 ACK 只能到 ~10fps（读超时要走
    CancelIoEx，单次 50~400ms）；而探针用的 Win32 原生句柄在同一设备上可以稳定
    逐包 ACK、20fps（docs/phase5_music.json 120 帧/6.0s）。因此这里 Windows 走原生通道。

    两种发送模式（由 MusicPlayer 按目标帧率选择，见 ``music._send_strategy``）：
    * ``wait_ack=True``（≤30fps）：逐包写 + 逐包等 ACK（单包 0.5~3ms，7 包平均 15.5ms）；
    * ``wait_ack=False, drain=N``（≥60fps）：连写 7 包后帧末读走 N 个回包。66fps 每帧
      预算 15.15ms，逐包等 ACK 的平均 15.5ms 已超预算，所以让写操作背靠背流水线化。
    """

    def __init__(self, device, channel=None):
        self.device = device
        self.frames = 0
        self.acks = 0
        #: 上一帧帧末没读到的回包数（欠账，下一帧多读回来，避免队列缓慢堆积）
        self._ack_backlog = 0
        if channel is not None:
            # 单测注入的假通道（不打开真实设备）；body_len 默认 MK87 的 64B
            self._ch = channel
            self.body = int(getattr(channel, "body_len", 64) or 64)
            return
        iface = device.protocol.iface
        self.body = iface.info.payload_len
        if sys.platform == "win32":
            from .winhid import NativeHidChannel

            self._ch = NativeHidChannel(
                iface.info.path,
                read_len=iface.info.read_max_len,
                write_len=iface.info.out_report_len,
            )
        else:
            self._ch = _HidapiFrameChannel(iface)

    def frame_packets(self, payload: bytes) -> int:
        """一帧会被拆成几个 0x32 包（87 键 348B、body=64 → 7 包）。"""
        chunk = max(1, self.body - 8)
        return max(1, math.ceil(len(payload) / chunk))

    def send(self, payload: bytes, frame_index: int = 0,
             wait_ack: bool = True, ack_timeout: float = 0.006,
             drain: int = 0) -> int:
        """发送一帧逐键颜色；返回本帧读到的 ACK 数。

        wait_ack=True：逐包等 ACK（受 USB 轮询限制，实测约 9ms/包 → 上限 ~14fps 是
        hidapi 路径；原生通道 0.5~3ms/包）；
        wait_ack=False：连续写所有包，若 ``drain>0`` 再在帧末把本帧的回包读走
        （读的是已经排队的回包，正常 ~0ms），防止固件输入缓冲堆积拖慢 WriteFile。
        """
        packets = build_frame_packets(payload, self.body, frame_index)
        acks = 0
        if wait_ack:
            for pkt in packets:
                self._ch.write(pkt)
                deadline = time.time() + ack_timeout
                while time.time() < deadline:
                    r = self._ch.read_normalized(timeout=max(0.001, deadline - time.time()))
                    if r is None:
                        break
                    if len(r) >= 2 and r[0] == 0x55:
                        acks += 1
                        break
        else:
            for pkt in packets:
                self._ch.write(pkt)
            if drain:
                acks += self._drain_queued(len(packets), int(drain), ack_timeout)
        self.frames += 1
        self.acks += acks
        return acks

    def _drain_queued(self, packet_count: int, drain: int, timeout: float) -> int:
        """帧末 drain：读走本帧（+上帧欠账）的回包，返回其中 ACK 的个数。

        正常情况每个 read 都立即返回（回包已排队）；只有固件丢了回包时才会多等
        一次 timeout（原生通道最小等待 10ms），下一帧按欠账多读几个补上。
        """
        expected = min(int(drain) + self._ack_backlog, packet_count * 4)
        got = 0
        acks = 0
        for _ in range(expected):
            r = self._ch.read_normalized(timeout=timeout)
            if r is None:
                break
            got += 1
            if len(r) >= 2 and r[0] == 0x55:
                acks += 1
        self._ack_backlog = max(0, expected - got)
        return acks

    def read_ack(self, timeout: float = 0.1):
        """读一个回包（ACK 清道夫线程专用；写走另一个句柄，可跨线程并发）。"""
        return self._ch.read_normalized(timeout=timeout)

    def drain(self, duration: float = 0.02) -> None:
        self._ch.drain(duration)

    def close(self) -> None:
        try:
            self._ch.close()
        except Exception:
            pass


class _HidapiFrameChannel:
    """非 Windows 回退：hidapi 接口（Linux hidraw 无 CancelIoEx 延迟问题）。"""

    def __init__(self, iface) -> None:
        self.iface = iface

    def write(self, data: bytes) -> int:
        return self.iface.write_report(data)

    def read_normalized(self, timeout: float = 0.1):
        return self.iface.read_normalized(timeout)

    def drain(self, duration: float = 0.02) -> None:
        self.iface.drain(duration)

    def close(self) -> None:
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
