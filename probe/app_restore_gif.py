# -*- coding: utf-8 -*-
"""通过 MK87 Studio 的 HTTP API 重新上传用户的 Loli GIF（73 帧 / 1155 包），验证长上传 + 恢复屏幕内容。"""
import base64
import json
import os
import sys
import time
import urllib.request

GIF = r"C:\Users\ptfm\Pictures\Loli is a BEAST KILLING MACHINE ｜ Onimai Oniichan wa Oshimai!.gif"

inst = os.path.join(os.environ["LOCALAPPDATA"], "mk87", "instance.json")
with open(inst, encoding="utf-8") as f:
    port = int(json.load(f)["port"])
base = f"http://127.0.0.1:{port}"
print(f"== app 端口: {port}", flush=True)

raw = open(GIF, "rb").read()
print(f"== GIF {len(raw)/1048576:.2f} MB，base64 编码 …", flush=True)
b64 = base64.b64encode(raw).decode()
print(f"   base64 {len(b64)/1048576:.2f} MB，POST /api/tft/upload_file …", flush=True)


def get(path, timeout=30):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


req = urllib.request.Request(
    base + "/api/tft/upload_file",
    data=json.dumps({"data": b64, "options": {"fit": "cover"}}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
t0 = time.time()
with urllib.request.urlopen(req, timeout=600) as r:
    print("== 启动响应:", json.dumps(json.loads(r.read().decode()), ensure_ascii=False)[:300], flush=True)

phase = None
for i in range(240):
    time.sleep(3)
    j = get("/api/tft/job")
    phase = j.get("phase")
    print(f"   {int(time.time()-t0):3d}s phase={phase} pct={j.get('pct')} sent={j.get('sent')}/{j.get('total')} err={j.get('error')}", flush=True)
    if phase in ("done", "error", "cancelled"):
        break
print(f"== 最终: {json.dumps(get('/api/tft/job'), ensure_ascii=False)[:400]}", flush=True)
print(f"== 墙钟 {time.time()-t0:.1f}s", flush=True)
sys.exit(0 if phase == "done" else 1)
