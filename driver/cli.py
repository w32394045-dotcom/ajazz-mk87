#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mk87ctl —— MK87 命令行工具（脚本化 / 无 GUI 操作 / 硬件回归测试）。

用法示例::

    python driver/cli.py status
    python driver/cli.py info
    python driver/cli.py keymap dump --json keymap.json
    python driver/cli.py keymap set 103 keyboard 4          # Insert -> A
    python driver/cli.py keymap set 33 combo 224 6          # Q -> Ctrl+C
    python driver/cli.py keymap set 105 func 13             # PgUp -> 亮度+
    python driver/cli.py lighting set 1 --rgb FF0000 --brightness 5
    python driver/cli.py lighting custom --colors "0:FF0000,1:00FF00" --apply
    python driver/cli.py macro apply macros.json
    python driver/cli.py tft upload demo.gif --fps 10
    python driver/cli.py tft default
    python driver/cli.py wireless --sleep 10
    python driver/cli.py backup dump backup.json
    python driver/cli.py backup restore backup.json --confirm
    python driver/cli.py music start --seconds 10 --style spectrum
    python driver/cli.py keytest 10
    python driver/cli.py raw 10 30 00 00 00 00 01
    python driver/cli.py serve --port 8477
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from mk87lib import backup as backup_mod  # noqa: E402
from mk87lib import keymap, lighting, macro, music, tft, wireless  # noqa: E402
from mk87lib import keyscan as keyscan_mod  # noqa: E402
from mk87lib.device import MK87Device  # noqa: E402
from mk87lib.errors import MK87Error, UnsupportedFeature  # noqa: E402


def _open() -> MK87Device:
    dev = MK87Device()
    st = dev.connect()
    print(f"# connected: {st.transport}  fw={st.firmware}  battery={st.battery}%  pid=0x{st.pid:04X}")
    return dev


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _parse_rgb(s: str):
    s = s.strip().lstrip("#")
    if len(s) == 6:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    if "," in s:
        parts = [int(x) for x in s.split(",")]
        return tuple(parts[:3])
    raise ValueError(f"无法解析颜色: {s}")


# ----------------------------------------------------------------------
def cmd_status(args, dev):
    _print_json(dev.status.to_dict())


def cmd_info(args, dev):
    info = dev.get_device_info()
    info["raw"] = info["raw"].hex()
    gm = dev.get_game_mode()
    gm["raw"] = gm["raw"].hex()
    _print_json({"info": info, "gameMode": gm})


def cmd_keymap(args, dev):
    if args.action == "dump":
        normal = keymap.decode_matrix(keymap.read_normal_matrix(dev))
        fn = keymap.decode_matrix(keymap.read_fn_matrix(dev))
        data = {"normal": normal, "fn": fn}
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"已保存 {args.json}")
        else:
            for layer, rows in (("normal", normal), ("fn", fn)):
                changed = [r for r in rows if r["type"] != "default"]
                print(f"== {layer} 层（{len(changed)} 个非默认）==")
                for r in changed:
                    k = keymap.get_slot_key(r["slot"])
                    print(f"  slot {r['slot']:3d} [{k['name'] if k else '-':10s}] "
                          f"{bytes(r['raw']).hex(' ')}  {r['display']}")
        return
    if args.action == "get":
        print(keymap.key_get(dev, args.slot).hex(" "))
        return
    if args.action == "set":
        action = _build_action(args)
        res = keymap.patch_matrix(dev, args.layer, {args.slot: action})
        print(res)
        return
    if args.action == "restore":
        print(keymap.restore_layer(dev, args.layer, args.slots or None))
        return


def _build_action(args) -> dict:
    kind = args.kind
    if kind == "default":
        return {"type": "default"}
    if kind == "keyboard":
        return {"type": "keyboard", "value": int(args.values[0])}
    if kind == "consumer":
        return {"type": "consumer", "value": int(args.values[0])}
    if kind == "combo":
        return {"type": "combo", "mods": [int(x) for x in args.values[:-1]],
                "key": int(args.values[-1])}
    if kind == "macro":
        return {"type": "macro", "slot": int(args.values[0]),
                "mask": int(args.values[1]) if len(args.values) > 1 else 0,
                "count": int(args.values[2]) if len(args.values) > 2 else 0}
    if kind == "func":
        return {"type": "func", "value": int(args.values[0])}
    if kind == "funcv2":
        return {"type": "funcV2", "value": int(args.values[0]),
                "keyType": int(args.values[1]) if len(args.values) > 1 else 1}
    if kind == "raw":
        return {"type": "raw", "bytes": [int(x, 16) for x in args.values[:4]]}
    raise ValueError(f"未知动作类型 {kind}")


def cmd_lighting(args, dev):
    if args.action == "get":
        _print_json(lighting.get_effect(dev))
        return
    if args.action == "set":
        rgb = _parse_rgb(args.rgb) if args.rgb else (255, 255, 255)
        lighting.set_effect(dev, mode=args.mode, rgb=rgb,
                            brightness=args.brightness, speed=args.speed,
                            direction=args.direction, color_mode=args.color_mode)
        _print_json(lighting.get_effect(dev))
        return
    if args.action == "custom":
        colors = {}
        if args.colors:
            for pair in args.colors.split(","):
                slot, rgb = pair.split(":", 1)
                colors[int(slot)] = _parse_rgb(rgb)
        res = lighting.set_custom(dev, colors, apply=args.apply)
        print(res)
        return
    if args.action == "modes":
        _print_json(lighting.get_modes())


def cmd_macro(args, dev):
    if args.action == "dump":
        data = macro.read_all_macros(dev)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"已保存 {args.json}（{len(data['slots'])} 个宏，{data['used']}B）")
        else:
            _print_json(data)
        return
    if args.action == "apply":
        with open(args.file, encoding="utf-8") as f:
            doc = json.load(f)
        slots = doc.get("slots") if isinstance(doc, dict) else doc
        print(macro.write_macros(dev, slots))
        return
    if args.action == "clear":
        print(macro.clear_macros(dev))


def cmd_tft(args, dev):
    if args.action == "info":
        _print_json(tft.device_tft_info(dev))
        return
    if args.action == "upload":
        if dev.transport != "usb":
            raise UnsupportedFeature("TFT 上传仅支持 USB 有线连接")
        bo = dev.status.tft_byte_order
        max_frames = dev.status.tft_max_frames or 140
        if args.static:
            data = tft.image_to_rgb565(args.file, bo)
            print(f"单帧 {len(data)}B，上传中…")
            res = tft.upload_material(dev, 0, data, progress=_progress)
        else:
            delays, data = tft.gif_frames(args.file, max_frames=args.max_frames or max_frames,
                                          byte_order=bo)
            if args.fps:
                delays = [max(1, int(round(100 / args.fps)))] * len(delays)
            print(f"{len(delays)} 帧 / {len(data)}B，上传中…")
            res = tft.upload_animation(dev, delays, data, progress=_progress)
        print("\n" + json.dumps(res, ensure_ascii=False))
        return
    if args.action == "default":
        print("恢复官方默认 135 帧动画…")
        res = tft.restore_default(dev, progress=_progress)
        print("\n" + json.dumps(res, ensure_ascii=False))
        return


def _progress(pct: int, sent: int, total: int) -> None:
    bar = "#" * (pct // 4)
    sys.stdout.write(f"\r[{bar:<25}] {pct:3d}%  {sent}/{total}")
    sys.stdout.flush()


def cmd_wireless(args, dev):
    if args.sleep is not None:
        _print_json(wireless.set_sleep_time(dev, args.sleep))
    info = wireless.get_info(dev)
    _print_json(info)


def cmd_backup(args, dev):
    if args.action == "dump":
        data = backup_mod.dump(dev)
        with open(args.file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已备份到 {args.file}（{os.path.getsize(args.file)} 字节）")
        return
    if args.action == "restore":
        if not args.confirm:
            raise MK87Error("恢复会覆盖设备配置，需要 --confirm")
        with open(args.file, encoding="utf-8") as f:
            doc = json.load(f)
        res = backup_mod.restore(dev, doc, progress=lambda n, p: print(f"  {n} {p}%"))
        _print_json(res)


def cmd_music(args, dev):
    player = music.MusicPlayer(dev)
    if args.action == "devices":
        _print_json(music.list_devices())
        return
    if args.action == "start":
        player.start(device_id=args.device, style=args.style,
                     sensitivity=args.sensitivity, fps=args.fps)
        print(f"音乐律动已启动（{args.seconds}s，style={args.style}）…")
        try:
            t0 = time.time()
            while time.time() - t0 < args.seconds:
                time.sleep(0.5)
                st = player.status()
                sys.stdout.write(f"\rlevel={st['level']:.2f} bands={st['bands']} frames={st['frames']}")
                sys.stdout.flush()
        finally:
            print("\n" + json.dumps(player.stop(), ensure_ascii=False))


def cmd_keytest(args, dev):
    events = []

    def cb(ev):
        events.append(ev)
        if ev.get("type") == "key":
            state = "↓" if ev["down"] else "↑"
            print(f"  {state} {ev['name']:<10} vkey=0x{ev['vkey']:02X} hid={ev.get('hid')} "
                  f"scan=0x{ev['scan']:02X}")
    scanner = keyscan_mod.KeyScanner(callback=cb)
    scanner.start()
    print(f"按键捕获已启动（{args.seconds}s，backend={scanner.backend}），请按键…")
    try:
        time.sleep(args.seconds)
    finally:
        scanner.stop()
    print(f"共 {len(events)} 条事件")


def cmd_raw(args, dev):
    data = bytes(int(x, 16) for x in args.bytes)
    resp = dev.request(data[1] if len(data) > 1 else 0,
                       data[8:] if len(data) > 8 else b"",
                       content_size=int(args.content_size) if args.content_size else None,
                       timeout=args.timeout)
    print("response:", resp.hex(" "))


def cmd_serve(args, dev):
    import run  # noqa: F401

    run.main()


# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mk87ctl", description="AJAZZ MK87 命令行工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="设备状态")

    sub.add_parser("info", help="设备信息 / 游戏模式")

    km = sub.add_parser("keymap", help="改键 / FN 层")
    km.add_argument("action", choices=["dump", "get", "set", "restore"])
    km.add_argument("slot", nargs="?", type=int)
    km.add_argument("kind", nargs="?",
                    choices=["keyboard", "consumer", "combo", "macro", "func", "funcv2",
                             "default", "raw"])
    km.add_argument("values", nargs="*")
    km.add_argument("--layer", default="normal", choices=["normal", "fn"])
    km.add_argument("--json")
    km.add_argument("--slots", nargs="*", type=int)

    li = sub.add_parser("lighting", help="灯效")
    li.add_argument("action", choices=["get", "set", "custom", "modes"])
    li.add_argument("mode", nargs="?", type=int)
    li.add_argument("--rgb", default="FFFFFF")
    li.add_argument("--brightness", type=int, default=5)
    li.add_argument("--speed", type=int, default=3)
    li.add_argument("--direction", type=int, default=0)
    li.add_argument("--color-mode", type=int, default=1)
    li.add_argument("--colors", help='逐键颜色，如 "0:FF0000,1:00FF00"')
    li.add_argument("--apply", action="store_true")

    mc = sub.add_parser("macro", help="宏")
    mc.add_argument("action", choices=["dump", "apply", "clear"])
    mc.add_argument("file", nargs="?")
    mc.add_argument("--json")

    tf = sub.add_parser("tft", help="TFT 屏幕")
    tf.add_argument("action", choices=["info", "upload", "default"])
    tf.add_argument("file", nargs="?")
    tf.add_argument("--fps", type=int)
    tf.add_argument("--max-frames", type=int)
    tf.add_argument("--static", action="store_true")

    wl = sub.add_parser("wireless", help="2.4G 无线")
    wl.add_argument("--sleep", type=int, choices=[0, 1, 10, 20, 30])

    bk = sub.add_parser("backup", help="备份 / 恢复")
    bk.add_argument("action", choices=["dump", "restore"])
    bk.add_argument("file")
    bk.add_argument("--confirm", action="store_true")

    mu = sub.add_parser("music", help="音乐律动")
    mu.add_argument("action", choices=["devices", "start"])
    mu.add_argument("--device")
    mu.add_argument("--style", default="spectrum")
    mu.add_argument("--sensitivity", type=float, default=1.0)
    mu.add_argument("--fps", type=int, default=20)
    mu.add_argument("--seconds", type=float, default=10.0)

    kt = sub.add_parser("keytest", help="按键测试")
    kt.add_argument("seconds", nargs="?", type=float, default=10.0)

    rw = sub.add_parser("raw", help="发送原始帧（hex）")
    rw.add_argument("bytes", nargs="+")
    rw.add_argument("--content-size", type=int)
    rw.add_argument("--timeout", type=float, default=1.0)

    sv = sub.add_parser("serve", help="启动 Web UI 服务")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "serve":
        import run
        run.main()
        return 0
    if args.cmd == "music" and args.action == "devices":
        _print_json(music.list_devices())
        return 0
    dev = _open()
    try:
        handlers = {
            "status": cmd_status, "info": cmd_info, "keymap": cmd_keymap,
            "lighting": cmd_lighting, "macro": cmd_macro, "tft": cmd_tft,
            "wireless": cmd_wireless, "backup": cmd_backup, "music": cmd_music,
            "keytest": cmd_keytest, "raw": cmd_raw,
        }
        handlers[args.cmd](args, dev)
        return 0
    finally:
        dev.close()


if __name__ == "__main__":
    raise SystemExit(main())
