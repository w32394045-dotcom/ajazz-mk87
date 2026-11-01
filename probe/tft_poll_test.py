# -*- coding: utf-8 -*-
"""复现实验：TFT 上传期间，后台每 2s 在主协议接口发 GET_DEVICE_INFO（模拟 app 的 monitor 轮询）。

目的：验证「上传 TFT 时并发主协议命令」是否会导致键盘 USB 掉线（Windows 1167）。
用法: driver\\.venv\\Scripts\\python.exe -X faulthandler probe\\tft_poll_test.py [--frames 32] [--no-poll]
"""
import sys
import threading
import time

sys.path.insert(0, r"C:\Users\ptfm\Documents\ajazz-re\driver")

from mk87lib import tft  # noqa: E402
from mk87lib.device import MK87Device  # noqa: E402

GIF = r"C:\Users\ptfm\Pictures\Loli is a BEAST KILLING MACHINE ｜ Onimai Oniichan wa Oshimai!.gif"
FRAMES = 32
POLL = True
for a in sys.argv[1:]:
    if a.startswith("--frames="):
        FRAMES = int(a.split("=", 1)[1])
    elif a == "--no-poll":
        POLL = False

print(f"== 实验参数: frames={FRAMES} poll={POLL}", flush=True)

dev = MK87Device()
st = dev.connect()
print(f"== 已连接 transport={st.transport} tft_frames={st.tft_max_frames} byteOrder={st.tft_byte_order}", flush=True)

raw = open(GIF, "rb").read()
print(f"== GIF {len(raw)/1048576:.2f} MB，转换 {FRAMES} 帧 …", flush=True)
t0 = time.time()
res = tft.convert_animation(raw, max_frames=FRAMES, dedupe=False, preview=False,
                            byte_order=st.tft_byte_order)
delays = res["delaysCs"][:FRAMES]
frames = res["_frames565"][:FRAMES]
print(f"   得到 {len(frames)} 帧, delays[:6]={delays[:6]}, 转换 {time.time()-t0:.1f}s", flush=True)

stop = threading.Event()
poll_err = []


def poll_loop():
    n = 0
    while not stop.is_set():
        try:
            dev.get_device_info()
            n += 1
            if n % 5 == 0:
                print(f"   [poll] GET_DEVICE_INFO x{n} ok", flush=True)
        except Exception as exc:  # noqa: BLE001
            poll_err.append(str(exc))
            print(f"   [poll] 失败: {exc}", flush=True)
            return
        stop.wait(2.0)


th = None
if POLL:
    th = threading.Thread(target=poll_loop, name="poll", daemon=True)
    th.start()
    print("== 已启动后台轮询线程（每 2s GET_DEVICE_INFO）", flush=True)

t_upload = time.time()
try:
    r = tft.upload_animation(dev, delays, b"".join(frames))
    print("== 上传成功:", {k: r.get(k) for k in ("packets", "acks", "retries", "ackAvgMs", "seconds")}, flush=True)
    print(f"== 墙钟 {time.time()-t_upload:.1f}s", flush=True)
except Exception as exc:  # noqa: BLE001
    print(f"== 上传失败: {type(exc).__name__}: {exc}", flush=True)
finally:
    stop.set()
    if th is not None:
        th.join(timeout=2)
    try:
        dev.close()
    except Exception:  # noqa: BLE001
        pass
    print(f"== poll 错误: {poll_err}", flush=True)
