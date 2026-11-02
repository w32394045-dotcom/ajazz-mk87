# -*- coding: utf-8 -*-
"""官方 Music.exe（MusicPlug.exe, v1 插件）音乐律动采样器 —— 只读官方 HTTP API + 被动监听 HID ACK。

原理：
  * 官方网页音乐律动（musicV1）调 `GET http://127.0.0.1:9191/api/keyboard/musiceffect?param=<mode>&<amp>&<backmode>&<bb>&1`
    让官方插件按该组合渲染；插件自己算颜色并直接发 HID 帧给键盘；
  * 我们每 ~50ms 轮询 `/api/keyboard/musiceffect/` 拿「官方每键颜色」（官方渲染 ground truth），
    每 250ms 拿 `/api/audio/amplitude`（实时振幅，用于之后喂我们自己的渲染器做同输入对比）；
  * 同时被动监听 MI_02（usagePage 0xFF68）上 `55 32` 的 ACK 回显，重组成官方真实 HID 帧。

用法:
  driver\\.venv\\Scripts\\python.exe probe\\capture_official_music.py [--out xxx.jsonl] [--per 6]

输出 JSONL，每行一个对象:
  {"k":"param","t":...,"mode":...,"amp":...,"backmode":...,"bb":...,"label":...}
  {"k":"http","t":...,"mode":...,"amp":...,"backmode":...,"bb":...,"live":<amplitude>,"colors":"RRGGBB,..."}
  {"k":"frame","t":...,"i":...,"n":<包数>,"hex":...}
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:9191"

# 线上 bundle（layout-classic-CMxiG14P.js，offset≈2301704，function D7 / musicV1）里的真实选项表
MODES = [
    (1, "绿色/黄色/红色"), (2, "彩虹色"), (13, "随曲起舞"), (4, "曲率频阶"),
    (5, "频谱循环"), (6, "白色"), (7, "红色"), (8, "橙色"), (9, "黄色"),
    (11, "蓝色"), (10, "绿色"), (100, "屏光联动"),
]
BGS = [
    (0, "无"), (6, "白色"), (7, "红色"), (8, "橙色"), (9, "黄色"),
    (10, "蓝色"), (11, "绿色"), (1, "绿色/黄色/红色"), (2, "彩虹色"),
    (4, "色谱"), (5, "频谱循环"),
]


def http_json(path, timeout=1.5):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


class FrameListener(threading.Thread):
    """被动监听 MI_02 上 55 32 的 ACK 回显，重组官方下发的逐键帧。"""

    def __init__(self, out_fh):
        super().__init__(daemon=True, name="hid-listener")
        self.out = out_fh
        self.stop = threading.Event()
        self.packets = 0
        self.frames = 0
        self.dev = None
        self._chunks = {}

    def open(self):
        import hid
        path = None
        for d in hid.enumerate(0x0C45, 0x8047):
            if int(d.get("usage_page") or 0) == 0xFF68:
                path = d.get("path")
                break
        if path is None:
            print("!! 找不到 MI_02（0xFF68）接口，帧监听禁用", flush=True)
            return False
        self.dev = hid.device()
        self.dev.open_path(path)
        print(f"== MI_02 监听已打开: {path}", flush=True)
        return True

    def run(self):
        if self.dev is None:
            return
        while not self.stop.is_set():
            try:
                data = self.dev.read(64, 20)
            except Exception as exc:  # noqa: BLE001
                print(f"!! HID 读取异常: {exc}", flush=True)
                return
            if not data:
                continue
            b = bytes(data)
            if b and b[0] == 0 and len(b) > 1 and b[1] == 0x55:
                b = b[1:]
            if len(b) < 8 or b[0] != 0x55 or b[1] != 0x32:
                continue
            self.packets += 1
            length, addr = b[2], b[3] | (b[4] << 8)
            i, last = b[5], b[6]
            payload = b[8:8 + length]
            slot = self._chunks.setdefault((i, addr), payload)
            if last == 1:
                # 官方一帧 = 多个 addr 段，按 addr 拼
                parts = []
                for (ii, aa) in sorted(k for k in self._chunks if k[0] == i):
                    parts.append(self._chunks[(ii, aa)])
                self._chunks = {k: v for k, v in self._chunks.items() if k[0] != i}
                frame = b"".join(parts)
                self.frames += 1
                rec = {"k": "frame", "t": round(time.time(), 3), "i": i,
                       "n": len(parts), "hex": frame.hex()}
                self.out.write(json.dumps(rec) + "\n")
                if self.frames % 100 == 0:
                    print(f"   [帧] 已重组 {self.frames} 帧 / {self.packets} 包", flush=True)

    def close(self):
        self.stop.set()
        try:
            self.join(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        if self.dev is not None:
            try:
                self.dev.close()
            except Exception:  # noqa: BLE001
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"C:\Users\ptfm\Documents\ajazz-re\capture\official_music_capture.jsonl")
    ap.add_argument("--per", type=float, default=6.0, help="每个组合采样秒数")
    ap.add_argument("--settle", type=float, default=0.7, help="切换后等待秒数")
    args = ap.parse_args()

    # 先拿 key 顺序（官方返回顺序固定）
    m0 = http_json("/api/keyboard/musiceffect/")
    keys = m0.get("keys", [])
    print(f"== 官方插件在线：{len(keys)} 键, 当前 amplitude={m0.get('amplitude')} "
          f"backmode={m0.get('backmode')} bb={m0.get('backmodebrightness')}", flush=True)

    out = open(args.out, "w", encoding="utf-8", buffering=1)
    fl = FrameListener(out)
    if fl.open():
        fl.start()

    stop = threading.Event()
    live = {"amp": 0}

    def poll_loop():
        n = 0
        while not stop.is_set():
            t0 = time.time()
            try:
                d = http_json("/api/keyboard/musiceffect/", timeout=1.0)
                colors = "".join(k.get("color", "#000000")[1:] for k in d.get("keys", []))
                rec = {"k": "http", "t": round(time.time(), 3),
                       "mode": CUR["mode"], "amp": CUR["amp"], "backmode": CUR["backmode"],
                       "bb": CUR["bb"], "live": live["amp"], "colors": colors}
                out.write(json.dumps(rec) + "\n")
            except Exception as exc:  # noqa: BLE001
                print(f"!! 轮询失败: {exc}", flush=True)
            n += 1
            if n % 5 == 0:
                try:
                    live["amp"] = int(http_json("/api/audio/amplitude", timeout=1.0).get("amplitude") or 0)
                except Exception:  # noqa: BLE001
                    pass
            dt = time.time() - t0
            stop.wait(max(0.0, 0.05 - dt))

    CUR = {"mode": 13, "amp": 30, "backmode": 0, "bb": 100}
    polling = threading.Thread(target=poll_loop, daemon=True)
    polling.start()

    def set_params(mode, amp, backmode, bb, label):
        CUR.update(mode=mode, amp=amp, backmode=backmode, bb=bb)
        param = f"{mode}&{amp}&{backmode}&{bb}&1"
        try:
            http_json(f"/api/keyboard/musiceffect?param={param}", timeout=2.0)
            ok = True
        except Exception as exc:  # noqa: BLE001
            print(f"!! 设置失败 {param}: {exc}", flush=True)
            ok = False
        out.write(json.dumps({"k": "param", "t": round(time.time(), 3), "param": param,
                              "mode": mode, "amp": amp, "backmode": backmode, "bb": bb,
                              "label": label, "ok": ok}) + "\n")
        print(f"== {label}: param={param}", flush=True)
        stop.wait(args.settle)

    def segment(mode, amp, backmode, bb, label):
        secs = args.per
        p0 = fl.frames
        set_params(mode, amp, backmode, bb, label)
        stop.wait(secs)
        print(f"   {label}: 采样结束（新增官方帧 {fl.frames - p0}）", flush=True)

    t_start = time.time()
    try:
        # 阶段 A：12 个显示模式（背景=无, 振幅=30, 背景亮度=100）
        print("\n--- 阶段 A：显示模式 × 12（backmode=0, amp=30, bb=100）---", flush=True)
        for mode, name in MODES:
            segment(mode, 30, 0, 100, f"A mode={mode} {name}")

        # 阶段 B：11 个背景模式（mode=13 随曲起舞）
        print("\n--- 阶段 B：背景灯光 × 11（mode=13, amp=30, bb=100）---", flush=True)
        for bg, name in BGS:
            segment(13, 30, bg, 100, f"B backmode={bg} {name}")

        # 阶段 C：振幅 3 档
        print("\n--- 阶段 C：振幅（mode=13, backmode=0, bb=100）---", flush=True)
        for amp in (30, 60, 100):
            segment(13, amp, 0, 100, f"C amp={amp}")

        # 阶段 D：背景亮度 3 档
        print("\n--- 阶段 D：背景亮度（mode=13, backmode=1 绿黄红, amp=30）---", flush=True)
        for bb in (100, 50, 20):
            segment(13, 30, 1, bb, f"D bb={bb}")
    finally:
        stop.set()
        try:
            polling.join(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        fl.close()
        # 关闭官方音乐律动，让键盘回落
        try:
            http_json("/api/keyboard/musiceffect/close/", timeout=2.0)
            print("== 已调用官方 close，键盘将回落原灯效", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"!! close 失败: {exc}", flush=True)
        out.close()
        print(f"\n== 采样完成：{args.out}", flush=True)
        print(f"   总耗时 {time.time()-t_start:.1f}s，官方帧 {fl.frames} 帧 / {fl.packets} 包", flush=True)


if __name__ == "__main__":
    main()
