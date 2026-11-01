"""2.4G 无线：身份、休眠设置、连接通知。

实测（docs/TEST-REPORT.md §8）：
* 接收器 3141-65278 "2.4G Dongle"，设备信息 manufacturer=1 / product=18 / workMode=2；
* 休眠时间在游戏模式 56 字节的 payload[3]，单位=分钟，UI 取值 0/1/10/20/30，0=关；
* 通知：断连/休眠/复位帧 `55 FC 04/05/06` 走 0xFF60 协议口；
  唤醒帧 `A6 FF 01` 走 0xFFFF 接口（report ID 5），官方网页驱动收不到；
* 2.4G 下 TFT 与音乐律动不可用（官方确认音乐不支持）。
"""
from __future__ import annotations

from typing import List

from . import const
from .errors import UnsupportedFeature

WORK_MODE_NAMES = {0: "USB", 1: "蓝牙", 2: "2.4G"}
SLEEP_OPTIONS = [0, 1, 10, 20, 30]  # 分钟


def get_info(device) -> dict:
    info = device.get_device_info()
    gm = device.get_game_mode()
    events = [
        e for e in device.recent_events
        if e.get("type") == "notification" and e.get("kind") in ("sleep", "wake", "disconnect", "reset")
    ]
    return {
        "transport": device.transport,
        "is24g": device.transport == "2.4g",
        "connected": device.status.connected,
        "battery": {"percent": info.get("batteryLevel", 0), "charging": info.get("chargeStatus", 0)},
        "identity": {
            "manufacturer": info.get("manufacturer", 0),
            "product": info.get("product", 0),
            "workMode": info.get("workMode", 0),
            "workModeName": WORK_MODE_NAMES.get(info.get("workMode", 0), "未知"),
        },
        "sleepTime": int(gm.get("sleepTime", 0)),
        "sleepOptions": SLEEP_OPTIONS,
        "keyDelay": int(gm.get("keyDelay", 0)),
        "reportRate": int(gm.get("reportRate", 0)),
        "notifications": events[-20:],
        "note": "2.4G 下 TFT 上传与音乐律动不可用（仅 USB 有线支持）",
    }


def set_sleep_time(device, minutes: int) -> dict:
    minutes = int(minutes)
    if minutes not in SLEEP_OPTIONS:
        raise ValueError(f"休眠时间只支持 {SLEEP_OPTIONS} 分钟（0=关闭）")
    ok = device.set_sleep_time(minutes)
    gm = device.get_game_mode()
    return {
        "ok": bool(ok),
        "sleepTime": int(gm.get("sleepTime", 0)),
        "requested": minutes,
    }


def get_identity(device) -> dict:
    info = device.get_device_info()
    return {
        "manufacturer": info.get("manufacturer", 0),
        "product": info.get("product", 0),
        "workMode": info.get("workMode", 0),
        "workModeName": WORK_MODE_NAMES.get(info.get("workMode", 0), "未知"),
    }


def set_game_mode_fields(device, fields: dict) -> dict:
    """只支持已知字段（sleepTime / gameMode / fnSwitch / keyDelay ...），读改写保留其余字节。"""
    raw = bytearray(device.get_game_mode()["raw"])
    mapping = {
        "gameMode": 1, "fnSwitch": 2, "sleepTime": 3, "keyDelay": 4,
        "reportRate": 5, "systemMode": 6, "tftDisplayTime": 7,
        "stabilityMode": 11, "autoCalibration": 14, "singleKeyWakeup": 15,
        "pushButtonMode": 16, "nkroSwitch": 17, "powerMode": 20,
    }
    touched = []
    for name, idx in mapping.items():
        if name in fields and fields[name] is not None:
            raw[idx] = int(fields[name]) & 0xFF
            touched.append(name)
    ok, now = device.set_game_mode_raw(bytes(raw), verify=True)
    return {
        "ok": bool(ok),
        "touched": touched,
        "readback": (now.hex() if now else None),
        "fields": {k: int(raw[v]) for k, v in mapping.items()},
    }


def get_notifications(device) -> List[dict]:
    return [
        e for e in device.recent_events
        if e.get("type") == "notification"
    ]
