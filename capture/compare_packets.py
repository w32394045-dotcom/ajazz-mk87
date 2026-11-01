#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比：官方网驱抓包里的 4104B 大包 vs 我们本地 tft_upload_gif.py 生成的包"""
import json, sys, os, hashlib

CAP = r"C:\Users\ptfm\Documents\ajazz-re\capture\ajazz_tft_capture.jsonl"
GIF = r"C:\Users\ptfm\Pictures\Loli is a BEAST KILLING MACHINE ｜ Onimai Oniichan wa Oshimai!.gif"

sys.path.insert(0, r"C:\Users\ptfm\Documents\ajazz-re\probe")
from tft_upload_gif import load_gif, build_delay_table, CMD_TFT_USER_ANIMATION, W, H  # noqa

# 1) 本地生成
frames, delays, sizes, n_total = load_gif(GIF, 140, 0)
mv = build_delay_table(delays)
data = bytes(mv) + b''.join(frames)
body = 4104
chunk = body - 8
total = (len(data) + chunk - 1) // chunk
ours = []
for seq in range(total):
    part = data[seq * chunk:(seq + 1) * chunk]
    pkt = bytearray([0]) + bytearray(body)
    pkt[1:9] = bytes([0xAA, CMD_TFT_USER_ANIMATION, seq & 0xFF, (seq >> 8) & 0xFF,
                      total & 0xFF, (total >> 8) & 0xFF, 0x50, 0x06])
    pkt[9:9 + len(part)] = part
    ours.append(bytes(pkt))

print(f"本地: {len(frames)} 帧, delays[0..3]={delays[:4]}, data={len(data)}B, total={total} 包")
print(f"本地首包 sha1={hashlib.sha1(ours[0]).hexdigest()} len={len(ours[0])}")

# 2) 抓包里的官方包（最后一个完整会话 = 1155 包）
big = []
for line in open(CAP, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    d = r.get('data') or {}
    if r.get('dir') == 'out' and r.get('phase') == 'call' and (d.get('length') or 0) >= 4096:
        b = bytes.fromhex((d.get('hex') or '').replace(' ', ''))
        big.append((r.get('ts'), b))

sess, cur = [], []
for ts, b in big:
    if cur and ts - cur[-1][0] > 1000:
        sess.append(cur); cur = []
    cur.append((ts, b))
if cur: sess.append(cur)
full = [s for s in sess if len(s) >= 100]
print(f"抓包: {len(big)} 个大包, 会话数={len(sess)}, 完整会话={[len(s) for s in full]}")
off = full[-1]
print(f"官方首包 sha1={hashlib.sha1(off[0][1]).hexdigest()} len={len(off[0][1])}")
print(f"官方末包 hdr={off[-1][1][:8].hex(' ')}")

# 3) 逐包对比（官方数据 4104B == 我们去掉 report id 后的 4104B）
same = 0
diff = []
for i, (ts, b) in enumerate(off):
    o = ours[i][1:]
    if b == o:
        same += 1
    else:
        diff.append((i, len(b), len(o), b[:16].hex(' '), o[:16].hex(' ')))
print(f"逐包一致: {same}/{len(off)}")
for d in diff[:10]:
    print("  差异", d)
if same == len(off):
    print("\n*** 本地生成的报文与官方抓包 100% 一致 → 问题不在报文内容 ***")
else:
    print("\n!! 报文有差异，需要进一步查")
