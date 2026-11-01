"""MK87 设备对象：连接管理（USB / 2.4G）、命令封装、通知监听。

所有协议操作都经过 :class:`MK87Device`，内部一把 RLock 串行化，
保证「请求-响应」不被后台通知线程抢帧。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import const
from .errors import DeviceDisconnected, DeviceNotFound, MK87Error
from .protocol import Protocol
from .transport import HidInterface, IfaceInfo, enumerate_ifaces

EventCallback = Callable[[dict], None]


# ----------------------------------------------------------------------
@dataclass
class DeviceStatus:
    connected: bool = False
    transport: str = "none"          # usb / 2.4g / none
    product: str = ""
    manufacturer: str = ""
    serial: str = ""
    firmware: str = ""
    vid: int = const.VID
    pid: int = 0
    battery: int = 0
    charging: int = 0
    work_mode: int = 0
    key_count: int = const.KEY_COUNT
    tft_max_frames: int = 0
    led_max_frames: int = 0
    max_profile: int = 0
    macro_space: int = const.MACRO_SPACE
    tft_byte_order: int = 0
    last_error: str = ""

    @property
    def has_tft(self) -> bool:
        return self.transport == "usb" and self.tft_max_frames > 0

    @property
    def has_music(self) -> bool:
        return self.transport == "usb"

    @property
    def has_wireless(self) -> bool:
        return self.transport == "2.4g"

    def to_dict(self) -> dict:
        return {
            "connected": self.connected,
            "transport": self.transport,
            "device": {
                "vid": self.vid,
                "pid": self.pid,
                "product": self.product,
                "manufacturer": self.manufacturer,
                "serial": self.serial,
                "firmware": self.firmware,
            },
            "battery": {"percent": self.battery, "charging": self.charging},
            "caps": {
                "keyCount": self.key_count,
                "tft": self.has_tft,
                "tftMaxFrames": self.tft_max_frames,
                "ledMaxFrames": self.led_max_frames,
                "maxProfile": self.max_profile,
                "macroSpace": self.macro_space,
                "music": self.has_music,
                "wireless": self.has_wireless,
            },
            "workMode": self.work_mode,
            "lastError": self.last_error,
        }


@dataclass
class _Channels:
    proto: Optional[HidInterface] = None
    tft: Optional[HidInterface] = None
    wake: Optional[HidInterface] = None


class MK87Device:
    """一个已连接的 MK87（USB 有线或 2.4G 接收器皆可）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._channels = _Channels()
        self.protocol: Optional[Protocol] = None
        self.tft_protocol: Optional[Protocol] = None
        self.status = DeviceStatus()
        self._ifaces: List[IfaceInfo] = []
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._listeners: List[EventCallback] = []
        self._events: List[dict] = []
        self._event_seq = 0

    # ==================================================================
    # 连接 / 断开
    # ==================================================================
    def connect(self) -> DeviceStatus:
        """扫描并连接设备（优先 USB 有线，否则 2.4G）。"""
        self.close()
        infos = enumerate_ifaces(const.VID)
        self._ifaces = infos
        usb_proto = next(
            (i for i in infos if i.pid == const.PID_USB and i.usage_page == const.USAGE_PAGE_PROTOCOL),
            None,
        )
        usb_tft = next(
            (i for i in infos if i.pid == const.PID_USB and i.usage_page == const.USAGE_PAGE_TFT),
            None,
        )
        g_proto = next(
            (i for i in infos if i.pid == const.PID_DONGLE and i.usage_page == const.USAGE_PAGE_24G_PROTOCOL),
            None,
        )
        g_wake = next(
            (i for i in infos if i.pid == const.PID_DONGLE and i.usage_page == const.USAGE_PAGE_24G_WAKE),
            None,
        )

        transport = "none"
        try:
            if usb_proto is not None:
                transport = "usb"
                channels = _Channels(
                    proto=HidInterface(usb_proto).open(),
                    tft=HidInterface(usb_tft).open() if usb_tft else None,
                )
            elif g_proto is not None:
                transport = "2.4g"
                channels = _Channels(
                    proto=HidInterface(g_proto).open(),
                    wake=HidInterface(g_wake).open() if g_wake else None,
                )
            else:
                raise DeviceNotFound(
                    "未找到可用的 MK87 协议接口。请确认键盘已连接（USB 线或 2.4G 接收器）。"
                )
        except DeviceDisconnected:
            self._close_channels()
            raise

        self._channels = channels
        self.protocol = Protocol(channels.proto) if channels.proto else None
        self.tft_protocol = Protocol(channels.tft) if channels.tft else None
        self.status.transport = transport
        self.status.pid = usb_proto.pid if transport == "usb" else g_proto.pid
        self.status.product = (usb_proto or g_proto).product if (usb_proto or g_proto) else ""
        if transport == "usb":
            self.status.manufacturer = usb_proto.manufacturer if usb_proto else ""
            self.status.serial = usb_proto.serial if usb_proto else ""
        else:
            self.status.manufacturer = g_proto.manufacturer if g_proto else ""
            self.status.serial = g_proto.serial if g_proto else ""

        # 用 GET_DEVICE_INFO 验证通道（同时拿到固件/电量/能力）
        try:
            info = self.get_device_info()
            self._apply_info(info)
            self.status.connected = True
            self.status.last_error = ""
        except Exception as exc:  # noqa: BLE001
            self._close_channels()
            self.status.connected = False
            self.status.transport = "none"
            self.status.pid = 0
            self.status.product = ""
            self.status.manufacturer = ""
            self.status.serial = ""
            self.status.last_error = str(exc)
            raise
        self._stop.clear()
        self._start_listeners()
        return self.status

    def _apply_info(self, info: dict) -> None:
        s = self.status
        s.firmware = f"{info.get('version', 0):.2f}"
        s.battery = int(info.get("batteryLevel", 0))
        s.charging = int(info.get("chargeStatus", 0))
        s.work_mode = int(info.get("workMode", 0))
        s.key_count = const.KEY_COUNT
        s.tft_max_frames = int(info.get("tftMaxFrames", 0))
        s.led_max_frames = int(info.get("ledMaxFrames", 0))
        s.max_profile = int(info.get("maxProfile", 0))
        s.macro_space = int(info.get("macroSpaceSize", const.MACRO_SPACE))
        s.tft_byte_order = int(info.get("tftColorByteOrder", 0))

    def close(self) -> None:
        """断开设备并停止后台线程。"""
        self._stop.set()
        for t in self._threads:
            t.join(timeout=0.4)
        self._threads.clear()
        with self._lock:
            self._close_channels()
        self.status.connected = False

    def _close_channels(self) -> None:
        for ch in (self._channels.proto, self._channels.tft, self._channels.wake):
            if ch is not None:
                try:
                    ch.close()
                except Exception:
                    pass
        self._channels = _Channels()
        self.protocol = None
        self.tft_protocol = None

    # ==================================================================
    # 通知 / 事件
    # ==================================================================
    def add_listener(self, cb: EventCallback) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: EventCallback) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    @property
    def recent_events(self) -> List[dict]:
        return list(self._events[-50:])

    def _emit(self, event: dict) -> None:
        event.setdefault("ts", time.time())
        self._event_seq += 1
        event["seq"] = self._event_seq
        self._events.append(event)
        if len(self._events) > 200:
            del self._events[:100]
        for cb in list(self._listeners):
            try:
                cb(event)
            except Exception:
                pass

    def _start_listeners(self) -> None:
        if self._channels.proto is not None:
            self._threads.append(
                threading.Thread(target=self._listen_proto, name="mk87-notify-proto", daemon=True)
            )
        if self._channels.wake is not None:
            self._threads.append(
                threading.Thread(target=self._listen_wake, name="mk87-notify-wake", daemon=True)
            )
        for t in self._threads:
            t.start()

    def _listen_proto(self) -> None:
        """空闲时读主协议通道，解析设备主动上报（55 FC xx）。"""
        while not self._stop.is_set():
            acquired = self._lock.acquire(timeout=0.05)
            if not acquired:
                continue
            try:
                r = self.protocol.read_event(0.05) if self.protocol else None
            except DeviceDisconnected:
                self._on_disconnect("HID 句柄失效")
                return
            except Exception:
                r = None
            finally:
                self._lock.release()
            if r:
                self._handle_raw_event(r, source="proto")

    def _listen_wake(self) -> None:
        """2.4G 唤醒帧通道（report ID 5 上的 A6 FF 01）。"""
        while not self._stop.is_set():
            ch = self._channels.wake
            if ch is None:
                return
            try:
                r = ch.read_report(0.1)
            except DeviceDisconnected:
                self._on_disconnect("唤醒通道句柄失效")
                return
            except Exception:
                r = None
            if r:
                self._handle_raw_event(r, source="wake")

    def _handle_raw_event(self, raw: bytes, source: str) -> None:
        kind = None
        if const.NOTIFY_WAKE in raw:
            kind = "wake"
        elif raw[:3] == const.NOTIFY_DISCONNECT[:3] or b"\x55\xfc\x04" in raw:
            kind = "disconnect"
        elif b"\x55\xfc\x05" in raw:
            kind = "sleep"
        elif b"\x55\xfc\x06" in raw:
            kind = "reset"
        elif b"\x55\xfa" in raw:
            kind = "notify"
        if kind:
            self._emit({"type": "notification", "kind": kind, "raw": raw.hex(), "source": source})
        else:
            self._emit({"type": "raw", "raw": raw.hex(), "source": source})

    def _on_disconnect(self, reason: str) -> None:
        if not self.status.connected:
            return
        self.status.connected = False
        self.status.last_error = reason
        self._emit({"type": "disconnected", "reason": reason})

    # ==================================================================
    # 底层请求（带锁）
    # ==================================================================
    def request(
        self,
        cmd: int,
        payload: bytes = b"",
        content_size: Optional[int] = None,
        timeout: float = 0.5,
        retries: int = 2,
        addr_start: int = 0,
        need_response: bool = True,
    ) -> bytes:
        if self.protocol is None:
            raise DeviceNotFound("设备未连接")
        with self._lock:
            try:
                return self.protocol.request(
                    cmd,
                    payload,
                    addr_start=addr_start,
                    timeout=timeout,
                    retries=retries,
                    content_size=content_size,
                    need_response=need_response,
                )
            except DeviceDisconnected:
                self._on_disconnect("设备断开")
                raise

    def request_custom(
        self,
        cmd: int,
        header: bytes,
        payload: bytes = b"",
        content_size: Optional[int] = None,
        timeout: float = 0.5,
        retries: int = 1,
    ) -> bytes:
        """带 8 字节自定义头的单包请求（如 GET_KEY 单槽读取）。"""
        if self.protocol is None:
            raise DeviceNotFound("设备未连接")
        iface = self.protocol.iface
        body = iface.info.payload_len
        pkt = bytearray([0]) + bytearray(body)
        pkt[1:1 + len(header)] = header
        if payload:
            pkt[1 + len(header):1 + len(header) + len(payload)] = payload
        want = content_size if content_size is not None else len(payload)
        with self._lock:
            for _ in range(retries + 1):
                iface.write_report(bytes(pkt))
                deadline = time.time() + timeout
                while time.time() < deadline:
                    r = iface.read_normalized(timeout=max(0.01, deadline - time.time()))
                    if r is None:
                        break
                    if len(r) >= 9 and r[0] == 0x55 and r[1] == (cmd & 0xFF):
                        return bytes(r[8:8 + want]) if want else bytes(r[8:])
            raise MK87Error(f"命令 0x{cmd:02X} 无响应")
        return b""

    # ==================================================================
    # 设备信息 / 设置
    # ==================================================================
    def get_device_info(self) -> dict:
        raw = self.request(const.CMD["GET_DEVICE_INFO"], content_size=48, timeout=0.8)
        d = bytes(raw[:48])
        if len(d) < 36:
            raise MK87Error(f"设备信息长度异常: {len(d)}")
        ver = ((d[8] & 0x0F) + ((d[8] & 0xF0) >> 4) * 10 + d[9] * 100) / 100
        return {
            "romSize": d[0],
            "macroSpaceSize": d[2] | (d[3] << 8),
            "vid": d[4] | (d[5] << 8),
            "pid": d[6] | (d[7] << 8),
            "version": ver,
            "sensor": d[10] | (d[11] << 8),
            "manufacturer": d[12] | (d[13] << 8),
            "product": d[14] | (d[15] << 8),
            "workMode": d[16],
            "batteryLevel": d[17],
            "chargeStatus": d[18],
            "currentProfile": d[19],
            "tftMaxFrames": d[22] | (d[23] << 8),
            "gifMaxFrames": d[24] | (d[25] << 8),
            "ledMaxFrames": d[26] | (d[27] << 8),
            "tftDirection": d[28],
            "frameVersion": d[30],
            "lightingVersion": d[31],
            "maxProfile": d[33],
            "tftColorByteOrder": d[35],
            "raw": d,
        }

    def get_game_mode(self) -> dict:
        d = bytes(self.request(const.CMD["GET_GAME_MODE"], content_size=56, timeout=0.8)[:56])
        return {
            "gameMode": d[1],
            "fnSwitch": d[2],
            "sleepTime": d[3],
            "keyDelay": d[4],
            "reportRate": d[5],
            "systemMode": d[6],
            "tftDisplayTime": d[7],
            "stabilityMode": d[11],
            "autoCalibration": d[14],
            "singleKeyWakeup": d[15],
            "pushButtonMode": d[16],
            "nkroSwitch": d[17],
            "powerMode": d[20],
            "raw": d,
        }

    def set_game_mode_raw(self, raw56: bytes, verify: bool = False):
        m = bytes(raw56)
        if len(m) != 56:
            raise ValueError(f"game mode payload 必须是 56 字节，实际 {len(m)}")
        self.request(const.CMD["SET_GAME_MODE"], m, content_size=56, timeout=0.8, retries=1)
        if verify:
            now = bytes(self.get_game_mode()["raw"])
            return now == m, now
        return True, None

    def set_sleep_time(self, minutes: int) -> bool:
        """休眠时间：分钟，0=关，UI 提供 1/10/20/30。"""
        minutes = max(0, min(255, int(minutes)))
        raw = bytearray(self.get_game_mode()["raw"])
        raw[3] = minutes
        ok, _ = self.set_game_mode_raw(bytes(raw), verify=True)
        return bool(ok)

    def sync_time(self, dt=None) -> bytes:
        import datetime as _dt

        dt = dt or _dt.datetime.now()
        weekday = dt.isoweekday() % 7  # 0=周日
        p = bytearray(10)
        p[0] = 90
        p[1] = 1
        p[2] = 90
        p[3] = dt.year % 100
        p[4] = dt.month
        p[5] = dt.day
        p[6] = dt.hour
        p[7] = dt.minute
        p[8] = dt.second
        p[9] = weekday & 0xFF
        return self.request(const.CMD["SET_TEMPORARY_COMMAND_DATA"], bytes(p), timeout=1.0, retries=0)

    def factory_reset(self) -> bool:
        try:
            self.request(const.CMD["SET_FACTORY_RESET"], b"", content_size=0, timeout=1.0, retries=0)
        except MK87Error:
            return False
        return True

    # ==================================================================
    # 灯效
    # ==================================================================
    def get_led_effect(self) -> dict:
        d = bytes(self.request(const.CMD["GET_LED_EFFECT"], content_size=16, timeout=0.8)[:16])
        return {
            "mode": d[0],
            "red": d[1],
            "green": d[2],
            "blue": d[3],
            "driverSetting": d[4],
            "secondary": (d[5], d[6], d[7]),
            "colorMode": d[8],
            "brightness": d[9],
            "speed": d[10],
            "direction": d[11],
            "effectModeType": d[12],
            "raw": d,
        }

    def set_led_effect(
        self,
        mode: int = 1,
        red: int = 255,
        green: int = 255,
        blue: int = 255,
        secondary=(0, 0, 0),
        color_mode: int = 1,
        brightness: int = 6,
        speed: int = 3,
        direction: int = 0,
        effect_mode_type: int = 0,
    ) -> bytes:
        p = bytearray(16)
        p[0] = mode & 0xFF
        p[1] = red & 0xFF
        p[2] = green & 0xFF
        p[3] = blue & 0xFF
        p[4] = 0xFF
        p[5] = secondary[0] & 0xFF
        p[6] = secondary[1] & 0xFF
        p[7] = secondary[2] & 0xFF
        p[8] = color_mode & 0xFF
        p[9] = brightness & 0xFF
        p[10] = speed & 0xFF
        p[11] = direction & 0xFF
        p[12] = effect_mode_type & 0xFF
        p[14] = 0xAA
        p[15] = 0x55
        return self.request(const.CMD["SET_LED_EFFECT"], bytes(p), content_size=16, timeout=0.8)

    def read_custom_led_data(self) -> bytes:
        return self.request(const.CMD["GET_CUSTOM_LED_DATA"], content_size=512, timeout=0.8)

    def write_custom_led_data(self, buf512: bytes) -> bytes:
        m = bytes(buf512)
        if len(m) != 512:
            raise ValueError(f"自定义灯数据必须是 512 字节，实际 {len(m)}")
        self.request(const.CMD["SET_CUSTOM_LED_DATA"], m, content_size=512, timeout=1.0, retries=1)
        return self.read_custom_led_data()

    def read_all_lights_rgb(self) -> bytes:
        payload = bytearray(512)
        for i in range(128):
            payload[i * 4] = i
        return self.request(
            const.CMD["GET_ALL_LIGHTS_RGB"], bytes(payload), content_size=512, timeout=1.0
        )

    def get_custom_colors(self) -> Dict[int, tuple]:
        """读自定义灯表 → {ledId: (r,g,b)}（只含有非零颜色的槽）。"""
        raw = self.read_custom_led_data()
        out: Dict[int, tuple] = {}
        for i in range(min(128, len(raw) // 4)):
            led, r, g, b = raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2], raw[i * 4 + 3]
            if led == 0 and r == 0 and g == 0 and b == 0:
                continue
            out[int(led)] = (int(r), int(g), int(b))
        return out

    def get_lights_frame(self) -> Dict[int, tuple]:
        """读回当前逐键 LED 颜色（帧流验证/取色器用）。"""
        raw = self.read_all_lights_rgb()
        out: Dict[int, tuple] = {}
        for i in range(min(128, len(raw) // 4)):
            led, r, g, b = raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2], raw[i * 4 + 3]
            out[int(led)] = (int(r), int(g), int(b))
        return out
