#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\ptfm\Documents\ajazz-re\capture\ajazz_tft_capture.jsonl"
recs = []
with open(path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass

def hx(r):
    return ((r.get('data') or {}).get('hex') or '').replace(' ', '')

def bts(r):
    try:
        return bytes.fromhex(hx(r))
    except Exception:
        return b''

def hdr(r):
    b = bts(r)
    if len(b) >= 8 and b[0] == 0xAA:
        return b[1], b[2] | (b[3] << 8), b[4] | (b[5] << 8), b[6], b[7]
    return None

sends = [r for r in recs if r.get('dir') == 'out' and r.get('phase') == 'call']
ins = [r for r in recs if r.get('dir') == 'in']
big = [r for r in sends if len(bts(r)) >= 4096]
small = [r for r in sends if len(bts(r)) < 4096]

print(f"recs={len(recs)} sends={len(sends)} big={len(big)} small={len(small)} in={len(ins)}")

# big packets: group sessions by >1s gap
sessions, cur = [], []
for r in big:
    ts = r.get('ts') or 0
    if cur and ts - (cur[-1].get('ts') or 0) > 1000:
        sessions.append(cur); cur = []
    cur.append(r)
if cur: sessions.append(cur)

print("\n=== 上传会话（按 >1s 间隔切分）===")
for i, s in enumerate(sessions):
    h = hdr(s[0]); hl = hdr(s[-1])
    seqs = [hdr(r)[1] for r in s if hdr(r)]
    gaps = [(s[k].get('ts') or 0) - (s[k-1].get('ts') or 0) for k in range(1, len(s))]
    print(f"#{i+1:02d} n={len(s):4d} seq={min(seqs)}..{max(seqs)} total={h[2]} ts={s[0].get('ts'):.0f}->{s[-1].get('ts'):.0f} "
          f"span={(s[-1].get('ts')-s[0].get('ts'))/1000:.1f}s gap_avg={(sum(gaps)/len(gaps) if gaps else 0):.1f}ms "
          f"dup={len(seqs)-len(set(seqs))}")

# ACK frames: dir=in with first byte 0x55
print("\n=== in 帧 0x55 xx 统计 ===")
c = collections.Counter()
for r in ins:
    b = bts(r)
    if len(b) >= 2:
        c[(b[0], b[1])] += 1
for k, v in sorted(c.items(), key=lambda x: -x[1])[:12]:
    print(f"  {v:6d}  {k[0]:02X} {k[1]:02X}")

# ACK relative to big packet window
if big:
    t0 = big[0].get('ts') or 0
    t1 = big[-1].get('ts') or 0
    def inwin(r):
        ts = r.get('ts') or 0
        return t0 - 200 <= ts <= t1 + 2000
    w = [r for r in ins if inwin(r)]
    cw = collections.Counter()
    for r in w:
        b = bts(r)
        if len(b) >= 2:
            cw[(b[0], b[1])] += 1
    print(f"\n=== 上传窗口内 in 帧 {len(w)} 条，cmd 分布 top ===")
    for k, v in sorted(cw.items(), key=lambda x: -x[1])[:12]:
        print(f"  {v:6d}  {k[0]:02X} {k[1]:02X}")
    # ack per big packet: count 55 41 frames within 200ms after each big send? sample first 6
    print("\n=== 前 6 个大包的发送间隔与紧随其后的 in 帧 ===")
    for idx in range(min(6, len(big))):
        r = big[idx]
        ts = r.get('ts') or 0
        print(f"  send#{idx} ts={ts:.1f} hdr={hdr(r)}")
        nxt = [x for x in ins if ts <= (x.get('ts') or 0) <= ts + 400]
        for x in nxt[:3]:
            b = bts(x)
            print(f"      in ts={(x.get('ts') or 0):.1f} +{(x.get('ts') or 0)-ts:.1f}ms len={len(b)} {b[:20].hex(' ')}")

# small commands: first/last 40
print(f"\n=== 小命令 out {len(small)} 条 ===")
for i, r in enumerate(small):
    b = bts(r)
    if i < 40 or i >= len(small) - 20:
        print(f"  [{i:3d}] ts={(r.get('ts') or 0):10.1f} rid={r.get('reportId')} len={len(b)} {b[:24].hex(' ')}")
    elif i == 40:
        print("  ...")

# errors
print("\n=== sendReport error 记录 ===")
for r in recs:
    if r.get('dir') == 'out' and r.get('phase') == 'error':
        print(f"  ts={(r.get('ts') or 0):.1f} rid={r.get('reportId')} len={(r.get('data') or {}).get('length')} err={r.get('error')}")

# requestDevice / open / event timeline
print("\n=== 设备控制时间线 ===")
for r in recs:
    if r.get('dir') in ('hid', 'open', 'close', 'forget', 'event') and r.get('phase') in ('call', 'ok', None):
        d = r.get('devices')
        print(f"  ts={(r.get('ts') or 0):10.1f} dir={r.get('dir')} phase={r.get('phase')} method={r.get('method')} "
              f"rid={r.get('reportId')} dev={json.dumps(d, ensure_ascii=False)[:180] if d else ''} err={r.get('error') or ''}")
