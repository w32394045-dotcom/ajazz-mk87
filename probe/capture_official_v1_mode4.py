# -*- coding: utf-8 -*-
"""官方 v1（Music.exe / MusicPlug.exe, 127.0.0.1:9191）显示模式 4「曲率频阶」专项采样。

只读约束（重要，见 docs/music-rhythm.md §10 与 probe/capture_official_music_v2.py）：
  * 不打开任何 HID 句柄、不起我们的 app / 帧流 —— 只走插件 HTTP，避免和插件抢 ACK；
  * 不调用 `/api/audio/amplitude`（实测会重置官方音乐会话 mode->0），
    振幅直接读 `/api/keyboard/musiceffect/` 响应的 `amplitude` 字段；

协议（官方网页顺序）：
  1) GET /api/keyboard/musiceffect/close/                      先清掉残留会话
  2) GET /api/keyboard/layout/base64?data=<b64>                告诉插件 MK87 键盘几何
  3) GET /api/keyboard/musiceffect?param=<mode>&<amp>&<bg>&<bb>&1   启动/切换
  4) 每 100ms GET /api/keyboard/musiceffect/                   轮询（同时是 keepalive：>200ms 不轮询会归 0）

音频：采样期间必须有一段**恒定振幅**的声音在默认输出设备上循环播放（本脚本不负责播放；
推荐 440Hz 正弦 WAV + `(New-Object System.Media.SoundPlayer $wav).PlayLooping()`，
见 probe/make_mode4_tone.py）。脚本会把插件返回的 amplitude 一并记下来，采完可核对。

输出 JSONL（capture/*.jsonl 已在 .gitignore）：
  {"k":"param", ...} / {"k":"http", "t":..., "colors":"<6*N hex>", "keys":[...], "amp":<插件振幅>}
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9191"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CFG = os.path.join(REPO, "docs", "device_config_32839.json")
DEFAULT_OUT = os.path.join(REPO, "capture", "official_v1_mode4.jsonl")

#: (label, mode, amp, backmode, bb, seconds)
PROFILES = {
    # 第一轮：确认几何/调色板（440Hz 正弦常驻）
    "v1": [
        ("warmup mode=13", 13, 30, 0, 100, 2.0),
        ("mode=4 amp=30", 4, 30, 0, 100, 11.0),
        ("mode=4 amp=100", 4, 100, 0, 100, 11.0),
        ("control mode=1 amp=30", 1, 30, 0, 100, 5.0),
        ("control mode=13 amp=30", 13, 30, 0, 100, 5.0),
    ],
    # 第二轮：振幅扫描（同一段 440Hz 正弦，看柱高/覆盖率随 amplitude 如何变）
    "amp": [
        ("warmup mode=13", 13, 30, 0, 100, 2.0),
        ("mode=4 amp=10", 4, 10, 0, 100, 6.0),
        ("mode=4 amp=30", 4, 30, 0, 100, 6.0),
        ("mode=4 amp=50", 4, 50, 0, 100, 6.0),
        ("mode=4 amp=70", 4, 70, 0, 100, 6.0),
        ("mode=4 amp=100", 4, 100, 0, 100, 6.0),
        ("mode=4 amp=30 repeat", 4, 30, 0, 100, 6.0),
    ],
    # 第三轮：不同音源（判断柱高是否随频率/频谱变化）
    "freq": [
        ("warmup mode=13", 13, 30, 0, 100, 2.0),
        ("mode=4 amp=30", 4, 30, 0, 100, 8.0),
        ("mode=4 amp=100", 4, 100, 0, 100, 6.0),
    ],
    # 第四轮：同一时刻只跑 amp=30/100（音源由外部决定：静音 / 440 / 4k / 100Hz）
    "basic": [
        ("warmup mode=13", 13, 30, 0, 100, 2.0),
        ("mode=4 amp=30", 4, 30, 0, 100, 8.0),
        ("mode=4 amp=100", 4, 100, 0, 100, 8.0),
    ],
    # 第五轮：频率→列映射（单音 100/440/2k/4k/8k，background=静音）
    "tone": [
        ("warmup mode=13", 13, 30, 0, 100, 2.0),
        ("mode=4 amp=100", 4, 100, 0, 100, 6.0),
    ],
    # 第六轮：阶梯扫频（200/400/800/1600/3200/6400 Hz，每档 0.8s 循环）观察列映射
    "sweep": [
        ("mode=4 amp=100", 4, 100, 0, 100, 11.5),
    ],
}
SEGMENTS = PROFILES["v1"]


def http_json(path: str, timeout: float = 1.5) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def build_layout() -> str:
    """官方 buildLayout：MK87 6 行 keyListRaw + musicConfig.keyOffset 的列偏移。"""
    cfg = json.load(open(CFG, encoding="utf-8"))
    mc = cfg.get("musicConfig") or {}
    offs = {o["value"]: o["offsetX"] for o in (mc.get("keyOffset") or [])}
    keys = []
    for ri, row in enumerate(cfg["keyListRaw"]):
        n = 0
        for ci, e in enumerate(row):
            col = ci + n
            ox = offs.get(e.get("value"))
            if ox:
                col += ox
                n += ox
            keys.append({"row": ri, "col": col, "code": e.get("keyCode"),
                         "index": e.get("value"), "name": e.get("name", "")})
    lay = {"name": cfg.get("name"), "vendorId": cfg["vendorId"], "productId": cfg["productId"],
           "deviceMode": 0,
           "layouts": {"rows": len(cfg["keyListRaw"]),
                       "cols": max(len(r) for r in cfg["keyListRaw"]), "keys": keys}}
    raw = json.dumps(lay, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return urllib.parse.quote(base64.b64encode(raw).decode("ascii"), safe="")


def lit_count(colors: str) -> int:
    return sum(1 for i in range(0, len(colors) - 5, 6) if colors[i:i + 6] != "000000")


class Poller(threading.Thread):
    def __init__(self, out, stop_ev: threading.Event):
        super().__init__(daemon=True, name="http-poll")
        self.out = out
        self.stop_ev = stop_ev
        self.frames = 0
        self.last_lit = 0
        self.last_amp = -1
        self.last_mode = -1

    def run(self):
        while not self.stop_ev.is_set():
            t0 = time.time()
            try:
                d = http_json("/api/keyboard/musiceffect/", timeout=1.0)
                keys = d.get("keys") or []
                colors = "".join(k.get("color", "#000000")[1:] for k in keys)
                self.last_lit = lit_count(colors)
                self.last_amp = int(d.get("amplitude") or 0)
                self.last_mode = int(d.get("mode") or 0)
                rec = {"k": "http", "t": round(time.time(), 4),
                       "pluginMode": d.get("mode"),
                       "ampPlugin": self.last_amp,
                       "backmodePlugin": d.get("backmode"),
                       "nkeys": len(keys),
                       "colors": colors,
                       "keys": [{"i": k.get("keyIndex"), "r": k.get("row"), "c": k.get("col")}
                                for k in keys]}
                self.out.write(json.dumps(rec) + "\n")
                self.frames += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  !! 轮询失败: {exc}", flush=True)
            self.stop_ev.wait(max(0.0, 0.1 - (time.time() - t0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--settle", type=float, default=2.5, help="切模式后丢弃的稳定时间(s)")
    ap.add_argument("--profile", default="v1", choices=sorted(PROFILES), help="采样组合")
    args = ap.parse_args()
    segments = PROFILES[args.profile]

    try:
        http_json("/api/keyboard/musiceffect/close/", timeout=2.0)
        time.sleep(0.3)
    except Exception:  # noqa: BLE001
        pass
    print("== 发官方键盘布局 …", flush=True)
    print("   layout:", http_json("/api/keyboard/layout/base64?data=" + build_layout()).get("status"),
          flush=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out = open(args.out, "w", encoding="utf-8", buffering=1)
    stop = threading.Event()
    poller = Poller(out, stop)
    poller.start()
    t_start = time.time()
    try:
        for label, mode, amp, bg, bb, seconds in segments:
            param = f"{mode}&{amp}&{bg}&{bb}&1"
            ok = True
            try:
                http_json(f"/api/keyboard/musiceffect?param={param}", timeout=2.0)
            except Exception as exc:  # noqa: BLE001
                ok = False
                print(f"  !! param 失败 {param}: {exc}", flush=True)
            out.write(json.dumps({"k": "param", "t": round(time.time(), 4), "param": param,
                                  "label": label, "mode": mode, "amp": amp,
                                  "backmode": bg, "bb": bb, "ok": ok}) + "\n")
            print(f"== {label:<24} param={param} 采 {seconds:.0f}s", flush=True)
            t_end = time.time() + args.settle + seconds
            while time.time() < t_end and not stop.is_set():
                time.sleep(0.5)
                print(f"   [{time.time()-t_start:5.1f}s] lit={poller.last_lit:3d} "
                      f"plugin.amp={poller.last_amp:4d} plugin.mode={poller.last_mode}", flush=True)
    finally:
        stop.set()
        poller.join(timeout=1)
        try:
            http_json("/api/keyboard/musiceffect/close/", timeout=2.0)
            print("== 已 close 官方音乐会话", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"!! close 失败: {exc}", flush=True)
        out.close()
        print(f"\n== 采样完成: {args.out}  用时 {time.time()-t_start:.1f}s  "
              f"HTTP 帧 {poller.frames}", flush=True)


if __name__ == "__main__":
    main()
