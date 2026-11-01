"""按键映射（改键 / FN 层）编解码与读写。

4 字节条目（来源：官方 bundle pX/mX，逐字节复刻；见 scripts/keymap.js 与 driver/data/keymap.json）::

    byte0 = pageType
    byte1..3 = 各页面语义参数字节

    pageType: 0=DEFAULT 1=MOUSE 2=KEYBOARD 3=CONSUMER_KEY 4=SYSTEM 5=EXTRA
              6=MACRO 7=CB(组合键) 8=DKS 9=MT 10=TGL 11=SOCD 12=RS 13=FUNC
              14=END 15=MPT；>=128 = FUNC_V2（12bit 槽A + 16bit 槽B）

对外统一 action 字典（server/API/前端共用）::

    {"type":"default"}
    {"type":"keyboard","value":4,"name":"A"}
    {"type":"mouse","param1":1,"value":1,"name":"鼠标左键"}
    {"type":"consumer","value":233,"name":"音量 +"}
    {"type":"macro","slot":0,"mask":0,"count":0}
    {"type":"combo","mods":[224],"key":6}
    {"type":"func","value":234,"name":"CTRL+C"}
    {"type":"funcV2","keyType":1,"value":28682,"name":"音量 +"}
    {"type":"raw","bytes":[...]}
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from . import const
from .errors import MK87Error

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

PAGE = {
    "DEFAULT": 0, "MOUSE": 1, "KEYBOARD": 2, "CONSUMER_KEY": 3, "SYSTEM_KEY": 4,
    "EXTRA_FUNCTION": 5, "MACRO": 6, "CB": 7, "DKS": 8, "MT": 9, "TGL": 10,
    "SOCD": 11, "RS": 12, "FUNC": 13, "END": 14, "MPT": 15,
}
PAGE_NAME = {v: k for k, v in PAGE.items()}
FUNC_V2_MIN = 128
MATRIX_LEN = const.KEY_MATRIX_SIZE
SLOT_COUNT = MATRIX_LEN // 4


class _Tables:
    """keymap.json 加载后的查表索引。"""

    def __init__(self, data: dict):
        self.data = data
        self.layout = data["layout"]
        self.key_list = {k["slot"]: k for k in data["keyListBySlot"]}
        self.empty_slots = set(data.get("emptySlots") or [])
        t = data["tables"]
        self.basic = t["basic"]
        self.extend = t["extend"]
        self.special = t["special"]
        self.func = t["func"]
        self.func_v2 = t["funcV2"]
        self.all_keys = t.get("allKeys") or []

        self.basic_by_value = {e["value"]: e for e in self.basic if e.get("page") == "KEYBOARD"}
        self.extend_by_value = {e["value"]: e for e in self.extend if e.get("page") == "KEYBOARD"}
        self.extend_by_param1 = {e.get("value"): e for e in self.extend}
        self.consumer_by_value = {
            e["value"]: e for e in self.special if e.get("page") == "CONSUMER_KEY"
        }
        self.mouse_by_key = {
            (e.get("param1", 1), e.get("value")): e for e in self.special if e.get("page") == "MOUSE"
        }
        self.func_by_value = {e["value"]: e for e in self.func}
        self.funcv2_by_value = {e["value"]: e for e in self.func_v2}
        self.all_by_keycode = {e["keyCode"]: e for e in self.all_keys}


_tables: Optional[_Tables] = None


def tables() -> _Tables:
    global _tables
    if _tables is None:
        with open(os.path.join(DATA_DIR, "keymap.json"), encoding="utf-8") as f:
            _tables = _Tables(json.load(f))
    return _tables


# ----------------------------------------------------------------------
# 名称解析
# ----------------------------------------------------------------------
def _name_of_keyboard(param1: int, param2: int) -> str:
    t = tables()
    if param1:
        e = t.extend_by_param1.get(param1)
        if e:
            return e["name"]
    e = t.basic_by_value.get(param2) or t.extend_by_value.get(param2)
    if e:
        return e["name"]
    e = t.all_by_keycode.get(param2)
    if e:
        return e["name"]
    return f"HID:{param2}"


def _name_of_consumer(value: int) -> str:
    e = tables().consumer_by_value.get(value)
    return e["name"] if e else f"Consumer:{value}"


def _name_of_mouse(param1: int, value: int) -> str:
    e = tables().mouse_by_key.get((param1, value))
    return e["name"] if e else f"Mouse:{param1}/{value}"


def _name_of_func(value: int) -> str:
    e = tables().func_by_value.get(value)
    return e["name"] if e else f"FUNC:{value}"


def _name_of_funcv2(code: int) -> str:
    t = tables()
    if 0 < code < 4096:
        e = t.basic_by_value.get(code) or t.extend_by_value.get(code)
        if e:
            return e["name"]
    e = t.funcv2_by_value.get(code)
    return e["name"] if e else f"FUNC_V2:{code}"


# ----------------------------------------------------------------------
# 解码
# ----------------------------------------------------------------------
def decode_entry(buf4) -> dict:
    b = bytes(buf4)
    if len(b) < 4:
        raise ValueError(f"decode_entry 需要 4 字节，收到 {len(b)}")
    pt, p1, p2, p3 = b[0], b[1], b[2], b[3]
    out: dict = {"raw": list(b), "pageType": pt}

    if pt >= FUNC_V2_MIN:
        slot_a = ((pt & 0x7F) << 8) | p1
        slot_b = (p2 << 8) | p3
        name = _name_of_funcv2(slot_b) if slot_b else _name_of_funcv2(slot_a)
        return {
            "type": "funcV2", "slotA": slot_a, "slotB": slot_b,
            "name": name, "display": name, **out,
        }

    if pt == PAGE["DEFAULT"]:
        return {"type": "default", "name": "默认", "display": "默认", **out}
    if pt == PAGE["MOUSE"]:
        name = _name_of_mouse(p1 or 1, p2)
        return {"type": "mouse", "param1": p1 or 1, "value": p2, "name": name, "display": name, **out}
    if pt == PAGE["KEYBOARD"]:
        name = _name_of_keyboard(p1, p2)
        return {"type": "keyboard", "value": p2, "param1": p1, "name": name, "display": name, **out}
    if pt == PAGE["CONSUMER_KEY"]:
        v = p1 | (p2 << 8)
        name = _name_of_consumer(v)
        return {"type": "consumer", "value": v, "name": name, "display": name, **out}
    if pt == PAGE["MACRO"]:
        return {
            "type": "macro", "slot": p1, "mask": p2, "count": p3,
            "name": f"宏 M{p1 + 1}", "display": f"宏 M{p1 + 1}", **out,
        }
    if pt == PAGE["CB"]:
        mods = [x for x in (p1, p2) if x]
        key_name = _name_of_keyboard(0, p3)
        mod_names = "+".join(_name_of_keyboard(0, m) for m in mods) if mods else ""
        display = f"{mod_names}+{key_name}" if mods else key_name
        return {"type": "combo", "mods": mods, "key": p3, "name": display, "display": display, **out}
    if pt == PAGE["FUNC"]:
        v = (p1 << 16) | (p2 << 8) | p3
        name = _name_of_func(v)
        return {"type": "func", "value": v, "name": name, "display": name, **out}
    if pt in (PAGE["DKS"], PAGE["TGL"], PAGE["MT"], PAGE["SOCD"], PAGE["RS"], PAGE["END"], PAGE["MPT"]):
        kind = PAGE_NAME[pt].lower()
        return {
            "type": kind, "param1": p1, "param2": p2, "param3": p3,
            "name": PAGE_NAME[pt], "display": f"{PAGE_NAME[pt]}:{p1}/{p2}/{p3}", **out,
        }
    return {
        "type": "raw", "bytes": [pt, p1, p2, p3],
        "name": f"未知(pageType {pt})", "display": f"未知({pt})", **out,
    }


# ----------------------------------------------------------------------
# 编码
# ----------------------------------------------------------------------
def encode_entry(action: Optional[dict]) -> bytes:
    if not action:
        return b"\x00\x00\x00\x00"
    t = action.get("type")
    if t in (None, "default"):
        return b"\x00\x00\x00\x00"
    if t == "keyboard":
        return bytes([PAGE["KEYBOARD"], 0, action.get("value", 0) & 0xFF, 0])
    if t == "mouse":
        return bytes([PAGE["MOUSE"], action.get("param1", 1) & 0xFF,
                      action.get("value", 0) & 0xFF, 0])
    if t == "consumer":
        v = int(action.get("value", 0)) & 0xFFFF
        return bytes([PAGE["CONSUMER_KEY"], v & 0xFF, (v >> 8) & 0xFF, 0])
    if t == "macro":
        return bytes([PAGE["MACRO"], action.get("slot", 0) & 0xFF,
                      action.get("mask", 0) & 0xFF, action.get("count", 0) & 0xFF])
    if t == "combo":
        mods = list(action.get("mods") or [])
        m1 = mods[0] if len(mods) > 0 else 0
        m2 = mods[1] if len(mods) > 1 else 0
        return bytes([PAGE["CB"], m1 & 0xFF, m2 & 0xFF, action.get("key", 0) & 0xFF])
    if t == "func":
        v = int(action.get("value", 0)) & 0xFFFFFF
        return bytes([PAGE["FUNC"], (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    if t == "funcV2":
        key_type = action.get("keyType")
        slot_a = int(action.get("slotA") or 0)
        slot_b = int(action.get("slotB") or 0)
        value = int(action.get("value") or 0)
        if key_type == 2:
            slot_a, slot_b = value, 0
        elif key_type == 1:
            slot_a, slot_b = 0, value
        elif slot_a == 0 and slot_b == 0:
            slot_b = value
        if not (0 <= slot_a <= 0x7FFF):
            raise MK87Error(f"FUNC_V2 槽 A 超出 12 位：{slot_a}")
        if not (0 <= slot_b <= 0xFFFF):
            raise MK87Error(f"FUNC_V2 槽 B 超出 16 位：{slot_b}")
        return bytes([0x80 | ((slot_a >> 8) & 0x7F), slot_a & 0xFF,
                      (slot_b >> 8) & 0xFF, slot_b & 0xFF])
    if t in ("dks", "tgl"):
        return bytes([PAGE[t.upper()], action.get("value", 0) & 0xFF, 0, 0])
    if t in ("mt", "socd", "rs", "mpt"):
        return bytes([PAGE[t.upper()], action.get("param1", 0) & 0xFF,
                      action.get("param2", 0) & 0xFF, action.get("param3", 0) & 0xFF])
    if t == "end":
        return bytes([PAGE["END"], action.get("param1", 0) & 0xFF, action.get("param2", 0) & 0xFF, 0])
    if t == "raw":
        return bytes(int(x) & 0xFF for x in (action.get("bytes") or [0, 0, 0, 0])[:4])
    raise MK87Error(f"未知的 action type: {t}")


# ----------------------------------------------------------------------
# 512 字节矩阵
# ----------------------------------------------------------------------
def decode_matrix(buf: bytes, layout: bool = True) -> List[dict]:
    b = bytes(buf)
    if len(b) != MATRIX_LEN:
        raise ValueError(f"矩阵必须是 {MATRIX_LEN} 字节，收到 {len(b)}")
    out = []
    for i in range(SLOT_COUNT):
        entry = decode_entry(b[i * 4:i * 4 + 4])
        entry["slot"] = i
        if layout:
            k = tables().key_list.get(i)
            entry["keyName"] = k["name"] if k else None
            entry["keyCode"] = k["keyCode"] if k else None
        out.append(entry)
    return out


def encode_matrix(actions: Dict[int, dict]) -> bytes:
    """{slot: action} → 512 字节；未给出的槽保持 0（= 出厂默认）。"""
    buf = bytearray(MATRIX_LEN)
    for slot, action in actions.items():
        slot = int(slot)
        if not 0 <= slot < SLOT_COUNT:
            raise MK87Error(f"槽号越界: {slot}")
        if not action or action.get("type") in (None, "default"):
            continue
        b4 = encode_entry(action)
        buf[slot * 4:slot * 4 + 4] = b4
    return bytes(buf)


# ----------------------------------------------------------------------
# 设备读写
# ----------------------------------------------------------------------
def read_normal_matrix(device) -> bytes:
    return device.request(const.CMD["GET_KEY"], content_size=MATRIX_LEN, timeout=1.0)


def read_fn_matrix(device) -> bytes:
    return device.request(const.CMD["GET_FN_KEY"], content_size=MATRIX_LEN, timeout=1.0)


def read_default_normal_matrix(device) -> bytes:
    return device.request(const.CMD["GET_DEFAULT_KEY_MATRIX"], content_size=MATRIX_LEN, timeout=1.0)


def read_default_fn_matrix(device) -> bytes:
    return device.request(const.CMD["GET_DEFAULT_FN_KEY_MATRIX"], content_size=MATRIX_LEN, timeout=1.0)


def write_normal_matrix(device, matrix: bytes, verify: bool = True):
    m = bytes(matrix)
    if len(m) != MATRIX_LEN:
        raise ValueError(f"矩阵必须是 {MATRIX_LEN} 字节，收到 {len(m)}")
    device.request(const.CMD["SET_KEY"], m, content_size=MATRIX_LEN, timeout=1.0, retries=1)
    if verify:
        now = read_normal_matrix(device)
        return now == m, now
    return True, None


def write_fn_matrix(device, matrix: bytes, verify: bool = True):
    m = bytes(matrix)
    if len(m) != MATRIX_LEN:
        raise ValueError(f"矩阵必须是 {MATRIX_LEN} 字节，收到 {len(m)}")
    device.request(const.CMD["SET_FN_KEY"], m, content_size=MATRIX_LEN, timeout=1.0, retries=1)
    if verify:
        now = read_fn_matrix(device)
        return now == m, now
    return True, None


def key_get(device, slot: int) -> bytes:
    """读取单个槽位的 4 字节（官方 getSingleKeyData 的自定义头方式）。"""
    addr = (int(slot) * 4) & 0xFFFF
    header = bytes([0xAA, const.CMD["GET_KEY"], 4, addr & 0xFF, (addr >> 8) & 0xFF, 0, 0, 0])
    return device.request_custom(const.CMD["GET_KEY"], header, content_size=4, timeout=0.5)


def patch_matrix(device, layer: str, patches: Dict[int, dict]) -> dict:
    """读-改-写：把 layer（normal/fn）里指定槽位改成给定 action，写回并校验。"""
    read = read_normal_matrix if layer == "normal" else read_fn_matrix
    write = write_normal_matrix if layer == "fn" else write_normal_matrix
    base = bytearray(read(device))
    for slot, action in patches.items():
        slot = int(slot)
        if not 0 <= slot < SLOT_COUNT:
            raise MK87Error(f"槽号越界: {slot}")
        b4 = encode_entry(action)
        base[slot * 4:slot * 4 + 4] = b4
    return _write_layer(device, layer, bytes(base))


def _write_layer(device, layer: str, matrix: bytes) -> dict:
    if layer == "normal":
        ok, now = write_normal_matrix(device, matrix, verify=True)
    else:
        ok, now = write_fn_matrix(device, matrix, verify=True)
    return {"ok": bool(ok), "readback": (now.hex() if now else None)}


def restore_layer(device, layer: str, slots: Optional[List[int]] = None) -> dict:
    """把指定槽位写 0（= 恢复出厂默认），slots=None 表示整层。"""
    read = read_normal_matrix if layer == "normal" else read_fn_matrix
    base = bytearray(read(device))
    if slots is None:
        base = bytearray(MATRIX_LEN)
    else:
        for s in slots:
            base[int(s) * 4:int(s) * 4 + 4] = b"\x00\x00\x00\x00"
    return _write_layer(device, layer, bytes(base))


# ----------------------------------------------------------------------
# 元数据（给 API / 前端）
# ----------------------------------------------------------------------
def get_layout() -> dict:
    t = tables()
    return {
        "layout": t.layout,
        "keyListBySlot": t.data["keyListBySlot"],
        "emptySlots": sorted(t.empty_slots),
        "physicalLedSlots": t.data.get("physicalLedSlots", 86),
        "ledSlotNotes": t.data.get("ledSlotNotes", {}),
    }


def get_actions_catalog() -> dict:
    t = tables()
    keyboard = []
    seen = set()
    for e in t.basic + t.extend:
        if e.get("page") != "KEYBOARD":
            continue
        v = e["value"]
        if v in seen:
            continue
        seen.add(v)
        keyboard.append({"value": v, "name": e["name"], "text": e.get("text")})
    consumer = [{"value": e["value"], "name": e["name"]}
                for e in t.special if e.get("page") == "CONSUMER_KEY"]
    mouse = [{"param1": e.get("param1", 1), "value": e["value"], "name": e["name"]}
             for e in t.special if e.get("page") == "MOUSE"]
    func = [{"value": e["value"], "name": e["name"]} for e in t.func]
    func_v2 = [{"value": e["value"], "name": e["name"], "keyType": e.get("keyType", 1)}
               for e in t.func_v2]
    return {
        "keyboard": keyboard,
        "consumer": consumer,
        "mouse": mouse,
        "func": func,
        "funcV2": func_v2,
        "pageTypes": t.data["pageTypes"],
    }


def get_slot_key(slot: int) -> Optional[dict]:
    return tables().key_list.get(int(slot))
