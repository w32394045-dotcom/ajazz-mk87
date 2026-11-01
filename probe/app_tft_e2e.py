# -*- coding: utf-8 -*-
"""MK87 Studio（打包 exe）端到端测试：经 app HTTP API 上传一个 6 帧 TFT 动画，验证不再 1167。"""
import base64
import io
import json
import os
import sys
import time
import urllib.request

from PIL import Image, ImageDraw

# 1) 生成 6 帧 240x135 测试 GIF
frames = []
colors = [(220, 30, 30), (30, 200, 30), (30, 60, 220), (230, 200, 30), (200, 30, 200), (30, 200, 220)]
for i, c in enumerate(colors):
    im = Image.new("RGB", (240, 135), c)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 239, 134], outline=(255, 255, 255), width=3)
    d.text((10, 10), f"MK87 TFT TEST {i + 1}/6", fill=(0, 0, 0))
    frames.append(im)
buf = io.BytesIO()
frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
gif = buf.getvalue()
b64 = base64.b64encode(gif).decode()
print(f"== 测试 GIF: {len(gif)} 字节, 6 帧 (约 95 包 / 14s 上传)")

# 2) 找 app 端口
inst = os.path.join(os.environ["LOCALAPPDATA"], "mk87", "instance.json")
port = None
for _ in range(120):
    try:
        with open(inst, encoding="utf-8") as f:
            port = int(json.load(f)["port"])
        break
    except Exception:
        time.sleep(0.5)
if not port:
    print("!! 等不到 app 端口（instance.json）")
    sys.exit(1)
base = f"http://127.0.0.1:{port}"
print(f"== app 端口: {port}")


def api_get(path, timeout=30):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def api_post(path, payload, timeout=180):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


st = api_get("/api/status")
print("== 设备:", json.dumps({"connected": st.get("connected"), "transport": st.get("transport"),
                              "product": (st.get("device") or {}).get("product")}, ensure_ascii=False))

t0 = time.time()
r = api_post("/api/tft/upload_file", {"data": b64, "options": {"fit": "cover"}})
print("== 上传已启动:", json.dumps(r, ensure_ascii=False)[:300])

phase = None
for i in range(90):
    time.sleep(1)
    j = api_get("/api/tft/job")
    phase = j.get("phase")
    if i % 3 == 0 or phase in ("done", "error", "cancelled"):
        print(f"   {i + 1:2d}s phase={phase} pct={j.get('pct')} sent={j.get('sent')}/{j.get('total')} "
              f"err={j.get('error')}")
    if phase in ("done", "error", "cancelled"):
        break
print(f"== 最终: {json.dumps(api_get('/api/tft/job'), ensure_ascii=False)[:400]}")
print(f"== 墙钟 {time.time() - t0:.1f}s")
