#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 docs/ 里的官方提取数据整理成驱动运行时数据（driver/data/*.json）。

数据来源（均为已逆向/真机验证过的产物）：
  docs/keymap-tables.json  → 动作表、pageType、MK87 键位
  docs/lighting-modes.json → 19 种灯效 UI 元数据、自定义灯族
  docs/_default_gif.json   → 官方默认 135 帧动画（恢复默认用）

用法： python driver/tools/build_data.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "docs")
OUT = os.path.join(ROOT, "driver", "data")


def load(name):
    with open(os.path.join(DOCS, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 键位几何
# 87 键 ANSI TKL：主键区 15u，导航/方向键区从 15.25u 开始。单位为 1u。
# (slot, width, gap_before)
def _key(slot, w=1.0, gap=0.0):
    return {"slot": slot, "w": w, "gap": gap}


LAYOUT_SPEC = [
    # Row 0: Esc + F1..F12 + Print/Scroll/Pause
    [_key(0), _key(1, gap=0.5), _key(2), _key(3), _key(4),
     _key(5, gap=0.5), _key(6), _key(7), _key(8),
     _key(9, gap=0.5), _key(10), _key(11), _key(12),
     _key(99, gap=0.75), _key(100), _key(102)],
    # Row 1: `~ 1..0 - = Backspace | Insert Home PgUp
    [_key(16), _key(17), _key(18), _key(19), _key(20), _key(21), _key(22),
     _key(23), _key(24), _key(25), _key(26), _key(27), _key(28),
     _key(92, 2.0), _key(103, gap=0.25), _key(104), _key(105)],
    # Row 2: Tab Q..] \ | Del End PgDn
    [_key(32, 1.5), _key(33), _key(34), _key(35), _key(36), _key(37), _key(38),
     _key(39), _key(40), _key(41), _key(42), _key(43), _key(44),
     _key(60, 1.5), _key(106, gap=0.25), _key(107), _key(108)],
    # Row 3: Caps A..' Enter
    [_key(48, 1.75), _key(49), _key(50), _key(51), _key(52), _key(53), _key(54),
     _key(55), _key(56), _key(57), _key(58), _key(59), _key(76, 2.25)],
    # Row 4: LShift Z..? RShift | (Up)
    [_key(64, 2.25), _key(65), _key(66), _key(67), _key(68), _key(69), _key(70),
     _key(71), _key(72), _key(73), _key(74), _key(75, 2.75),
     _key(90, gap=0.25)],
    # Row 5: Ctrl Win Alt Space RAlt Fn Super RCtrl | Left Down Right
    [_key(80, 1.25), _key(81, 1.25), _key(82, 1.25), _key(83, 6.25),
     _key(84, 1.25), _key(85, 1.25), _key(86, 1.25), _key(87, 1.25),
     _key(88, gap=0.25), _key(89), _key(91)],
]

# 行 4 的 ↑ 标准位置在下方向键正上方：x = 16.25（东侧留空 1u）
ROW4_UP_X = 16.25


def build_layout(keylist_by_slot):
    by_slot = {k["slot"]: k for k in keylist_by_slot}
    rows = []
    for ri, spec in enumerate(LAYOUT_SPEC):
        x = 0.0
        row_keys = []
        for item in spec:
            slot = item["slot"]
            x += item["gap"]
            info = by_slot.get(slot, {})
            if ri == 4 and slot == 90:
                x = ROW4_UP_X
            row_keys.append({
                "slot": slot,
                "row": ri,
                "x": round(x, 3),
                "w": item["w"],
                "name": info.get("name", f"slot{slot}"),
                "key": info.get("key", ""),
                "keyCode": info.get("keyCode", 0),
            })
            x += item["w"]
        rows.append(row_keys)
    return {"unit": 1.0, "totalWidth": 18.25, "rows": rows}


def main():
    os.makedirs(OUT, exist_ok=True)

    km = load("keymap-tables.json")
    mk = km["mk87KeyboardConfig"]
    tables = km["tables"]

    def entries(name):
        t = tables[name]
        ents = t.get("entries") if isinstance(t, dict) else t
        keep = []
        for e in ents or []:
            keep.append({k: e[k] for k in ("name", "value", "page", "keyType", "param1", "text")
                         if k in e})
        return keep

    keymap_data = {
        "meta": {
            "device": "AJAZZ MK87",
            "vendorId": 0x0C45,
            "productId": 0x8047,
            "keyCount": mk.get("keyCount", 87),
        },
        "pageTypes": km["pageTypes"],
        "funcV2Layout": km.get("funcV2Layout"),
        "tables": {
            "keyboard": entries("basicChars") + entries("extendChars"),
            "basic": entries("basicChars"),
            "extend": entries("extendChars"),
            "special": entries("specialChars"),
            "func": entries("funcChars"),
            "funcV2": entries("funcV2Chars"),
        },
        "layout": build_layout(mk["keyListBySlot"]),
        "keyListBySlot": mk["keyListBySlot"],
        "emptySlots": mk.get("isEmptySlot", []),
        # 真机修正（docs/TEST-REPORT.md §12 / docs/lighting.md）
        "physicalLedSlots": 86,
        "ledSlotNotes": {
            "97": "有 LED 驱动通道但无可见光（真机确认）",
            "98": "有 LED 驱动通道但无可见光（真机确认）",
            "99": "该位置是 TFT 屏幕，无灯",
            "100": "该位置是 TFT 屏幕，无灯",
            "102": "该位置是 TFT 屏幕，无灯",
        },
    }
    with open(os.path.join(OUT, "keymap.json"), "w", encoding="utf-8") as f:
        json.dump(keymap_data, f, ensure_ascii=False, indent=1)
    print("keymap.json:", os.path.getsize(os.path.join(OUT, "keymap.json")) // 1024, "KB")

    lm = load("lighting-modes.json")
    lighting_data = {
        "modes": lm["modeListForThisDevice"],
        "params": lm["params"],
        "custom": {
            "mode": lm["customLighting"]["CUSTOM_LIGHTING_MODE"],
            "family": lm["customLighting"]["customModeFamily"],
            "dataTable": "128 × [idx, R, G, B] = 512 字节",
        },
        "wireFormats": lm.get("wireFormats"),
        "ledSlots": (lm.get("ledKeyMap") or {}).get("rowsInPreview"),
    }
    with open(os.path.join(OUT, "lighting_modes.json"), "w", encoding="utf-8") as f:
        json.dump(lighting_data, f, ensure_ascii=False, indent=1)
    print("lighting_modes.json:", os.path.getsize(os.path.join(OUT, "lighting_modes.json")) // 1024, "KB")

    gif = load("_default_gif.json")
    with open(os.path.join(OUT, "default_animation.json"), "w", encoding="utf-8") as f:
        json.dump(gif, f, ensure_ascii=False)
    print("default_animation.json:", os.path.getsize(os.path.join(OUT, "default_animation.json")) // 1024,
          "KB,", gif["frames"], "frames")


if __name__ == "__main__":
    main()
