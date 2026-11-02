# -*- coding: utf-8 -*-
"""官方 MusicPlug（Music.exe, v1）音乐律动采样 v2 —— 直接从官方插件抓「渲染真值」。

关键事实（2026-11-02 实测）：
  * 官方网页音乐律动的启动顺序 = 先 `GET /api/keyboard/layout/base64?data=<b64>` 发键盘布局，
    再 `GET /api/keyboard/musiceffect?param=<mode>&<amp>&<backmode>&<bb>&1`，然后**每 100ms 轮询**
    `/api/keyboard/musiceffect/`（轮询本身是 keepalive：>200ms 不轮询插件会把 mode 归 0）。
  * 插件自己渲染 + 直接发 HID 帧：MI_02 上 `55 32` 回显，**8 包/帧（56B×7 + 40B=432B=108 项）**，
    约 60fps，`i=0`、`last=0`（没有 last 标志），帧起点是 addr=0。
  * 本脚本按组合调用 param 采样：帧流（60fps 真值）+ HTTP 每键颜色（10Hz, 含 row/col）+ 实时振幅。

输出 JSONL:
  {"k":"param",...} / {"k":"http",...} / {"k":"frame","t":...,"hex":<864 hex>,"mode":...,"amp":...,"backmode":...,"bb":...}
"""
import argparse
import base64
import json
import sys
import threading
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9191"
CFG = r"C:\Users\ptfm\Documents\ajazz-re\docs\device_config_32839.json"

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

CUR = {"mode": 13, "amp": 30, "backmode": 0, "bb": 100}


def http_json(path, timeout=1.5):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def build_layout():
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


class FrameListener(threading.Thread):
    """MI_02 被动读 55 32 回显；按 addr==0 切帧（官方没有 last 标志）。"""

    def __init__(self, out_fh):
        super().__init__(daemon=True, name="frame-listener")
        self.out = out_fh
        self.stop_ev = threading.Event()
        self.frames = 0
        self.bytes_total = 0
        self.dev = None
        self._cur = bytearray()
        self._last_addr = -1

    def open(self):
        import hid
        path = next((d["path"] for d in hid.enumerate(0x0C45, 0x8047)
                     if int(d.get("usage_page") or 0) == 0xFF68), None)
        if path is None:
            print("!! 找不到 MI_02(0xFF68)，帧监听禁用", flush=True)
            return False
        self.dev = hid.device()
        self.dev.open_path(path)
        self.dev.set_nonblocking(1)
        return True

    def run(self):
        while not self.stop_ev.is_set() and self.dev is not None:
            try:
                b = self.dev.read(64, 20)
            except Exception as exc:  # noqa: BLE001
                print(f"!! HID 读取异常: {exc}", flush=True)
                return
            if not b:
                continue
            b = bytes(b)
            if b and b[0] == 0 and len(b) > 1 and b[1] == 0x55:
                b = b[1:]
            if len(b) < 8 or b[0] != 0x55 or b[1] != 0x32:
                continue
            ln, addr = b[2], b[3] | (b[4] << 8)
            payload = b[8:8 + ln]
            if addr == 0 and self._cur:
                self._flush()
            self._cur += payload
            self._last_addr = addr

    def _flush(self):
        frame = bytes(self._cur)
        self._cur = bytearray()
        if not frame:
            return
        self.frames += 1
        self.bytes_total += len(frame)
        rec = {"k": "frame", "t": round(time.time(), 4), "n": len(frame),
               "hex": frame.hex(), "mode": CUR["mode"], "amp": CUR["amp"],
               "backmode": CUR["backmode"], "bb": CUR["bb"]}
        self.out.write(json.dumps(rec) + "\n")
        if self.frames % 200 == 0:
            print(f"   [帧] {self.frames} 帧 ({len(frame)}B)", flush=True)

    def close(self):
        self.stop_ev.set()
        try:
            self.join(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._cur:
                self._flush()
        except Exception:  # noqa: BLE001
            pass
        if self.dev is not None:
            try:
                self.dev.close()
            except Exception:  # noqa: BLE001
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"C:\Users\ptfm\Documents\ajazz-re\capture\official_music_capture_v2.jsonl")
    ap.add_argument("--per", type=float, default=6.0)
    ap.add_argument("--settle", type=float, default=1.0)
    ap.add_argument("--frames", action="store_true",
                    help="同时被动监听 MI_02 官方帧（默认关闭：与插件抢 ACK 容易把键盘 USB 打挂）")
    ap.add_argument("--amp", action="store_true",
                    help="轮询 /api/audio/amplitude（注意：实测该接口会重置官方音乐会话 mode->0，采样颜色时必须关闭）")
    args = ap.parse_args()

    # 先把插件上次可能残留的会话关掉，再按官方顺序 layout → param → 100ms 轮询
    try:
        http_json("/api/keyboard/musiceffect/close/", timeout=2.0)
        time.sleep(0.3)
    except Exception:  # noqa: BLE001
        pass
    print("== 发官方键盘布局 …", flush=True)
    print("   layout:", http_json("/api/keyboard/layout/base64?data=" + build_layout()).get("status"), flush=True)

    out = open(args.out, "w", encoding="utf-8", buffering=1)
    stop = threading.Event()
    live = {"amp": 0}

    def poll_loop():
        """官方网页就是每 100ms 轮询一次 musiceffect（keepalive），我们照做。"""
        n = 0
        while not stop.is_set():
            t0 = time.time()
            try:
                d = http_json("/api/keyboard/musiceffect/", timeout=1.0)
                colors = "".join(k.get("color", "#000000")[1:] for k in d.get("keys", []))
                rec = {"k": "http", "t": round(time.time(), 3), "mode": CUR["mode"],
                       "amp": CUR["amp"], "backmode": CUR["backmode"], "bb": CUR["bb"],
                       "live": live["amp"], "nkeys": len(d.get("keys", [])),
                       "colors": colors,
                       "keys": [{"i": k.get("keyIndex"), "r": k.get("row"), "c": k.get("col")}
                                for k in d.get("keys", [])]}
                out.write(json.dumps(rec) + "\n")
            except Exception as exc:  # noqa: BLE001
                print(f"!! 轮询失败: {exc}", flush=True)
            n += 1
            if args.amp and n % 5 == 0:
                try:
                    live["amp"] = int(http_json("/api/audio/amplitude", timeout=1.0).get("amplitude") or 0)
                except Exception:  # noqa: BLE001
                    pass
            stop.wait(max(0.0, 0.1 - (time.time() - t0)))

    poll_thread = threading.Thread(target=poll_loop, daemon=True, name="http-poll")
    fl = FrameListener(out) if args.frames else None
    if fl is not None:
        if fl.open():
            fl.start()
            print("== MI_02 帧监听已打开（官方 ~60fps 0x32 回显）", flush=True)
        else:
            fl = None
            print("!! 帧监听不可用，只抓 HTTP 颜色", flush=True)
    else:
        print("== 仅抓 HTTP 颜色（不打开 HID，避免与插件抢 ACK）", flush=True)
    try:
        http_json("/api/keyboard/musiceffect?param=13&30&0&100&1", timeout=2.0)
        time.sleep(0.5)
    except Exception as exc:  # noqa: BLE001
        print(f"!! 预热启动失败: {exc}", flush=True)
    poll_thread.start()

    def set_params(mode, amp, backmode, bb, label):
        CUR.update(mode=mode, amp=amp, backmode=backmode, bb=bb)
        param = f"{mode}&{amp}&{backmode}&{bb}&1"
        try:
            http_json(f"/api/keyboard/musiceffect?param={param}", timeout=2.0)
            ok = True
        except Exception as exc:  # noqa: BLE001
            print(f"!! param 失败 {param}: {exc}", flush=True)
            ok = False
        out.write(json.dumps({"k": "param", "t": round(time.time(), 3), "param": param,
                              "mode": mode, "amp": amp, "backmode": backmode, "bb": bb,
                              "label": label, "ok": ok}) + "\n")
        print(f"== {label}  param={param}", flush=True)
        stop.wait(args.settle)

    def segment(mode, amp, backmode, bb, label):
        p0, f0 = (fl.frames, fl.bytes_total) if fl is not None else (0, 0)
        set_params(mode, amp, backmode, bb, label)
        stop.wait(args.per)
        if fl is not None:
            print(f"   {label}: 新增帧 {fl.frames - p0} / {fl.bytes_total - f0} 字节", flush=True)
        else:
            print(f"   {label}: 采样 {args.per:.0f}s 完成", flush=True)

    t_start = time.time()
    try:
        print("\n--- A: 12 个显示模式（backmode=0, amp=30, bb=100）---", flush=True)
        for mode, name in MODES:
            segment(mode, 30, 0, 100, f"A mode={mode} {name}")
        print("\n--- B: 11 个背景灯光（mode=13, amp=30, bb=100）---", flush=True)
        for bg, name in BGS:
            segment(13, 30, bg, 100, f"B backmode={bg} {name}")
        print("\n--- C: 振幅（mode=13, backmode=0, bb=100）---", flush=True)
        for amp in (30, 60, 100):
            segment(13, amp, 0, 100, f"C amp={amp}")
        print("\n--- D: 背景亮度（mode=13, backmode=1, amp=30）---", flush=True)
        for bb in (100, 50, 20):
            segment(13, 30, 1, bb, f"D bb={bb}")
    finally:
        stop.set()
        poll_thread.join(timeout=1)
        if fl is not None:
            fl.close()
        try:
            http_json("/api/keyboard/musiceffect/close/", timeout=2.0)
            print("== 已 close 官方音乐律动", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"!! close 失败: {exc}", flush=True)
        out.close()
        extra = (f" 官方帧 {fl.frames} 帧 / {fl.bytes_total} 字节" if fl is not None else "（未监听 HID）")
        print(f"\n== 采样完成: {args.out}  用时 {time.time()-t_start:.1f}s{extra}", flush=True)


if __name__ == "__main__":
    main()
