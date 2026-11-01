"""宏表编解码与读写（真机验证格式，见 docs/keymap.md §16）。

逻辑地址空间::

    0   .. 399   : 目录 = 100 × u32 LE 绝对偏移（0 = 空槽）
    400 .. 3071  : 动作数据区（容量 = macroSpaceSize - 400，fw1.19 为 2672 字节）

宏块::

    [0..1] 动作数 × 2 (u16 LE)   [2..3] 0
    每个动作 4 字节: delay(u16 LE) | HID usage | flags
    flags = ((actionType & 7) << 4) | (isPress ? 0x80 : 0)
      键盘 actionType=3 → 按下 0xB0 / 抬起 0x30
      鼠标 actionType=1 → 按下 0x90 / 抬起 0x10

写入（两次 SET_MACRO）::

    目录: contentSize=400, addrStart=0,   所有包 last=0
    数据: contentSize=len(data), addrStart=400, 末包 last=1
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from . import const
from .errors import MK87Error

DIR_SIZE = const.MACRO_DIR_SIZE
DATA_START = DIR_SIZE
SLOT_COUNT = const.MACRO_SLOT_COUNT
DEFAULT_CAPACITY = const.MACRO_SPACE  # 整个宏区（含 400B 目录）

ACTION_TYPE_KEYBOARD = 3
ACTION_TYPE_MOUSE = 1

_TYPE_NAMES = {
    ACTION_TYPE_KEYBOARD: "keyboard",
    ACTION_TYPE_MOUSE: "mouse",
    # 官方 mouse 分支还有 type=2（另一种鼠标动作）
    2: "mouse2",
}


# ----------------------------------------------------------------------
# 编解码
# ----------------------------------------------------------------------
def encode_action(delay: int, usage: int, action_type: int = ACTION_TYPE_KEYBOARD,
                  press: bool = True) -> bytes:
    """动作 4 字节。官方 PZ 对鼠标动作(actionType 1/2)统一写 0x90/0x10，
    只有键盘动作(3)用 ((type&7)<<4)|(press?0x80:0) 公式（见 spec-keymap.md §6）。"""
    if action_type in (1, 2):
        flags = 0x90 if press else 0x10
    else:
        flags = ((int(action_type) & 7) << 4) | (0x80 if press else 0)
    return bytes([int(delay) & 0xFF, (int(delay) >> 8) & 0xFF,
                  int(usage) & 0xFF, flags])


def decode_action(b4: bytes) -> dict:
    delay = b4[0] | (b4[1] << 8)
    usage = b4[2]
    flags = b4[3]
    return {
        "delay": delay,
        "usage": usage,
        "press": bool(flags & 0x80),
        "actionType": (flags >> 4) & 7,
    }


def encode_macros(macros: List[dict]) -> tuple:
    """markers: [{slot:int, actions:[{delay,usage,press,actionType,type?}]}] → (table400, data)"""
    table = bytearray(DIR_SIZE)
    data = bytearray()
    offset = DATA_START
    for macro in sorted(macros, key=lambda m: int(m.get("slot", 0))):
        slot = int(macro.get("slot", 0))
        if not 0 <= slot < SLOT_COUNT:
            raise MK87Error(f"宏槽号越界: {slot}")
        acts = macro.get("actions") or []
        if not acts:
            continue
        block = bytearray(4)
        n = len(acts)
        block[0] = (n * 2) & 0xFF
        block[1] = ((n * 2) >> 8) & 0xFF
        for a in acts:
            atype = a.get("actionType")
            if atype is None:
                atype = ACTION_TYPE_KEYBOARD if a.get("type", "keyboard") == "keyboard" else ACTION_TYPE_MOUSE
            block += encode_action(a.get("delay", 10), a.get("usage", 0), atype,
                                   bool(a.get("press", True)))
        table[slot * 4:slot * 4 + 4] = offset.to_bytes(4, "little")
        data += block
        offset += len(block)
    return bytes(table), bytes(data)


def decode_directory(table400: bytes) -> Dict[int, int]:
    t = bytes(table400)
    if len(t) < DIR_SIZE:
        raise ValueError(f"宏目录必须是 {DIR_SIZE} 字节，收到 {len(t)}")
    out = {}
    for i in range(SLOT_COUNT):
        off = int.from_bytes(t[i * 4:i * 4 + 4], "little")
        if off:
            out[i] = off
    return out


def decode_block(head4: bytes, body: bytes) -> List[dict]:
    count = (head4[0] | (head4[1] << 8)) // 2
    acts = []
    for i in range(count):
        a = body[i * 4:i * 4 + 4]
        if len(a) < 4:
            break
        d = decode_action(a)
        d["type"] = _TYPE_NAMES.get(d["actionType"], "unknown")
        acts.append(d)
    return acts


# ----------------------------------------------------------------------
# 设备读写
# ----------------------------------------------------------------------
def read_directory(device) -> bytes:
    return device.request(const.CMD["GET_MACRO"], content_size=DIR_SIZE, timeout=1.0)


def read_raw(device, addr: int, size: int) -> bytes:
    return device.request(const.CMD["GET_MACRO"], content_size=size, addr_start=addr, timeout=1.0)


def read_macro(device, slot: int) -> Optional[List[dict]]:
    table = read_directory(device)
    off = int.from_bytes(table[slot * 4:slot * 4 + 4], "little")
    if not off:
        return None
    head = read_raw(device, off, 4)
    count = (head[0] | (head[1] << 8)) // 2
    if count <= 0:
        return []
    body = read_raw(device, off + 4, count * 4)
    return decode_block(head, body)


def read_all_macros(device) -> dict:
    table = read_directory(device)
    entries = decode_directory(table)
    slots = []
    used = 0
    for slot, off in sorted(entries.items()):
        try:
            head = read_raw(device, off, 4)
            count = (head[0] | (head[1] << 8)) // 2
            body = read_raw(device, off + 4, count * 4) if count > 0 else b""
            actions = decode_block(head, body)
        except Exception as exc:  # noqa: BLE001 - 单个宏损坏不应让整表失败
            actions = []
            head = b"\x00\x00\x00\x00"
            body = b""
        block_len = 4 + len(body)
        used += block_len
        slots.append({
            "slot": slot,
            "offset": off,
            "actions": actions,
            "bytes": block_len,
        })
    capacity = getattr(getattr(device, "status", None), "macro_space", DEFAULT_CAPACITY)
    return {
        "slots": slots,
        "used": used,
        "capacity": capacity,
        "dataCapacity": max(0, capacity - DATA_START),
        "slotCount": SLOT_COUNT,
        "directory": [int.from_bytes(table[i * 4:i * 4 + 4], "little") for i in range(SLOT_COUNT)],
    }


def _write_chunks(device, cmd: int, payload: bytes, addr_start: int, final_last: bool,
                  timeout: float = 1.5) -> List[bool]:
    iface = device.protocol.iface
    body = iface.info.payload_len
    chunk = body - 8
    total = max(1, math.ceil(len(payload) / chunk)) if payload else 1
    acks: List[bool] = []
    with device._lock:  # noqa: SLF001 - 和常规请求共用同一把锁
        for k in range(total):
            part = payload[k * chunk:(k + 1) * chunk]
            pkt = bytearray([0]) + bytearray(body)
            pkt[1] = 0xAA
            pkt[2] = cmd & 0xFF
            pkt[3] = len(part) & 0xFF
            addr = addr_start + k * chunk
            pkt[4] = addr & 0xFF
            pkt[5] = (addr >> 8) & 0xFF
            pkt[6] = 0
            pkt[7] = 1 if (k == total - 1 and final_last) else 0
            pkt[9:9 + len(part)] = part
            iface.write_report(bytes(pkt))
            ok = False
            import time as _time
            deadline = _time.time() + timeout
            while _time.time() < deadline:
                r = iface.read_normalized(timeout=0.02)
                if not r:
                    continue
                if r[0] == 0x55 and r[1] == (cmd & 0xFF):
                    ok = True
                    break
            acks.append(ok)
    return acks


def write_macros(device, macros: List[dict]) -> dict:
    """全表写入（目录 + 数据两次 SET_MACRO），返回校验结果。"""
    table, data = encode_macros(macros)
    capacity = getattr(getattr(device, "status", None), "macro_space", DEFAULT_CAPACITY)
    if len(data) > capacity - DATA_START:
        raise MK87Error(
            f"宏数据 {len(data)} 字节超出容量 {capacity - DATA_START} 字节"
        )
    acks_dir = _write_chunks(device, const.CMD["SET_MACRO"], table, 0, final_last=False)
    acks_data = _write_chunks(device, const.CMD["SET_MACRO"], data, DATA_START, final_last=True) if data else []
    # 回读校验
    read_back = read_directory(device)
    ok = read_back == table
    return {
        "ok": ok,
        "tableAcks": sum(acks_dir),
        "tablePackets": len(acks_dir),
        "dataAcks": sum(acks_data),
        "dataPackets": len(acks_data),
        "dataBytes": len(data),
        "capacity": capacity - DATA_START,
        "readbackMatch": ok,
    }


def clear_macros(device) -> dict:
    """清空宏表（目录写 400 字节 0，last=1）。"""
    acks = _write_chunks(device, const.CMD["SET_MACRO"], bytes(DIR_SIZE), 0, final_last=True)
    read_back = read_directory(device)
    return {"ok": read_back == bytes(DIR_SIZE), "acks": sum(acks), "packets": len(acks)}
