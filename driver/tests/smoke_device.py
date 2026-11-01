#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真机冒烟测试：连接设备，读取全部可读状态并做一致性检查（默认不写设备）。

    python tests/smoke_device.py            # 只读检查
    python tests/smoke_device.py --write    # 额外做一次可恢复的写测试（改一个槽位再还原）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import backup, const, keymap, lighting, macro  # noqa: E402
from mk87lib.device import MK87Device  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="做一次改键写入/还原测试")
    args = ap.parse_args()

    dev = MK87Device()
    st = dev.connect()
    out = {"ok": True, "transport": st.transport, "firmware": st.firmware,
           "battery": st.battery, "charging": st.charging}
    print(f"[连接] {st.transport}  fw={st.firmware}  battery={st.battery}%  charging={st.charging}")

    info = dev.get_device_info()
    out["deviceInfo"] = {k: v for k, v in info.items() if k != "raw"}
    print(f"[信息] manufacturer={info['manufacturer']} product={info['product']} "
          f"workMode={info['workMode']} tftMaxFrames={info['tftMaxFrames']} "
          f"macroSpace={info['macroSpaceSize']}")

    led = lighting.get_effect(dev)
    out["lighting"] = {"mode": led["mode"], "name": led["name"], "rgb": led["rgb"],
                       "brightness": led["brightness"]}
    print(f"[灯效] mode={led['mode']} {led['name']} rgb={led['rgb']} br={led['brightness']}")

    km = keymap.read_normal_matrix(dev)
    fn = keymap.read_fn_matrix(dev)
    normal = keymap.decode_matrix(km)
    fnm = keymap.decode_matrix(fn)
    changed_n = [s for s in normal if s["type"] != "default"]
    changed_f = [s for s in fnm if s["type"] != "default"]
    out["keymap"] = {"normalChanged": len(changed_n), "fnChanged": len(changed_f)}
    print(f"[按键] 普通层非默认 {len(changed_n)} 槽 / FN 层 {len(changed_f)} 槽")

    custom = dev.get_custom_colors()
    out["customLed"] = len(custom)
    print(f"[逐键灯] 自定义表非零 {len(custom)} 槽")

    lights = dev.get_lights_frame()
    lit = sum(1 for c in lights.values() if max(c) > 0)
    out["lightsNow"] = lit
    print(f"[实时灯] 当前点亮 {lit} 槽（GET_ALL_LIGHTS_RGB）")

    try:
        mac = macro.read_all_macros(dev)
        out["macros"] = {"slots": len(mac["slots"]), "used": mac["used"], "capacity": mac["capacity"]}
        print(f"[宏] {len(mac['slots'])} 个宏，使用 {mac['used']}B / {mac['capacity']}B")
    except Exception as exc:  # noqa: BLE001
        out["macros"] = {"error": str(exc)}
        print(f"[宏] 读取失败: {exc}")

    if args.write:
        print("[写测试] 读取槽 103 → 改为 KEYBOARD 'a' → 回读 → 还原 …")
        slot = 103
        base = bytearray(keymap.read_normal_matrix(dev))
        original = bytes(base[slot * 4:slot * 4 + 4])
        try:
            ok, now = keymap.write_normal_matrix(
                dev, bytearray(base[:slot * 4]) + keymap.encode_entry(
                    {"type": "keyboard", "value": 4}) + base[slot * 4 + 4:])
            print(f"  写入{'成功' if ok else '失败'}  回读: {now[slot * 4:slot * 4 + 4].hex() if now else '-'}")
            out["writeTest"] = bool(ok)
        finally:
            base[slot * 4:slot * 4 + 4] = original
            keymap.write_normal_matrix(dev, bytes(base))
            print(f"  已还原: {original.hex()}")

    try:
        bak = backup.dump(dev, include_defaults=True)
        out["backup"] = {"version": bak["version"], "keys": sorted(bak.keys())}
        print(f"[备份] 可导出 {len(bak)} 个字段，{len(json.dumps(bak))} 字节")
    except Exception as exc:  # noqa: BLE001
        out["backup"] = {"error": str(exc)}
        print(f"[备份] 导出失败: {exc}")

    time.sleep(0.3)
    print("[通知] 最近事件:", [e.get("kind") or e.get("type") for e in dev.recent_events[:5]])
    dev.close()
    print("\n结果:", json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
