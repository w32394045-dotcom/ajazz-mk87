#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 capture/ajazz_tft_capture.jsonl —— 重点看官方网驱的 TFT 上传序列"""
import json, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\ptfm\Documents\ajazz-re\capture\ajazz_tft_capture.jsonl"

recs = []
with open(path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            pass

print(f"== 总记录: {len(recs)}")

cnt = collections.Counter((r.get('dir'), r.get('method'), r.get('phase')) for r in recs)
print("== (dir, method, phase) 统计")
for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
    print(f"  {v:6d}  {k[0]} / {k[1]} / {k[2]}")

# ---- meta & 设备信息 ----
print("\n== meta / 设备")
for r in recs:
    if r.get('dir') == 'meta':
        print("  meta:", json.dumps(r.get('extra'), ensure_ascii=False)[:500])
for r in recs:
    if r.get('dir') in ('hid', 'event') and r.get('phase') == 'ok':
        print(f"  {r.get('dir')}: devices={json.dumps(r.get('devices'), ensure_ascii=False)[:400]}")
        break

def hexclean(s):
    return (s or '').replace(' ', '')

def parse_hdr(h):
    b = bytes.fromhex(hexclean(h))
    if len(b) >= 8 and b[0] == 0xAA:
        return dict(cmd=b[1], seq=b[2] | (b[3] << 8), total=b[4] | (b[5] << 8), b6=b[6], b7=b[7], b=b)
    return dict(b=b)

sends = [r for r in recs if r.get('dir') in ('out',) and r.get('phase') == 'call']
ins   = [r for r in recs if r.get('dir') == 'in']

# ---- 大报文（TFT）----
big = [r for r in sends if (r.get('data') or {}).get('length', 0) > 1000]
print(f"\n== 大报文 sendReport: {len(big)}")
if big:
    print("  reportId 分布:", dict(collections.Counter(r.get('reportId') for r in big)))
    print("  长度分布:", dict(collections.Counter((r.get('data') or {}).get('length') for r in big)))

    sessions = []
    cur = []
    for r in big:
        ts = r.get('ts') or 0
        if cur and ts - (cur[-1].get('ts') or 0) > 1000:
            sessions.append(cur)
            cur = []
        cur.append(r)
    if cur:
        sessions.append(cur)

    for si, s in enumerate(sessions):
        h0 = parse_hdr((s[0].get('data') or {}).get('hex'))
        last = parse_hdr((s[-1].get('data') or {}).get('hex'))
        seqs = [parse_hdr((r.get('data') or {}).get('hex'))['seq'] for r in s if 'seq' in parse_hdr((r.get('data') or {}).get('hex'))]
        gaps = [ (s[i].get('ts') or 0) - (s[i-1].get('ts') or 0) for i in range(1, len(s)) ]
        print(f"\n  --- 上传会话 #{si+1}: {len(s)} 包, ts {s[0].get('ts'):.1f} -> {s[-1].get('ts'):.1f} ({(s[-1].get('ts')-s[0].get('ts'))/1000:.2f}s)")
        if 'cmd' in h0:
            print(f"      首包 hdr: AA {h0['cmd']:02X} seq={h0['seq']} total={h0['total']} b6={h0['b6']:02X} b7={h0['b7']:02X}")
            print(f"      末包 hdr: AA {last['cmd']:02X} seq={last['seq']} total={last['total']} b6={last['b6']:02X} b7={last['b7']:02X}")
            print(f"      seq 范围: {min(seqs)}..{max(seqs)}  唯一数={len(set(seqs))}")
        if gaps:
            print(f"      间隔 ms: min={min(gaps):.2f} avg={sum(gaps)/len(gaps):.2f} max={max(gaps):.2f}")
        print(f"      首包 reportId={s[0].get('reportId')} len={(s[0].get('data') or {}).get('length')}")
        print(f"      首包 caller:\n        " + "\n        ".join((s[0].get('caller') or '').splitlines()[:5]))
        # 帧数据：延时表前 16 字节
        b = h0['b']
        if len(b) > 40:
            print(f"      首包 data[8:40]: {b[8:40].hex(' ')}")
        # 每包数据尾长度检查
        lens = collections.Counter((r.get('data') or {}).get('length') for r in s)
        print(f"      包长分布: {dict(lens)}")

# ---- ACK / 输入帧 ----
print(f"\n== in 帧: {len(ins)}")
cmd_cnt = collections.Counter()
samples = {}
for r in ins:
    b = bytes.fromhex(hexclean((r.get('data') or {}).get('hex')))
    key = (b[0], b[1]) if len(b) >= 2 else (None,)
    cmd_cnt[key] += 1
    samples.setdefault(key, b[:24].hex(' '))
for k, v in sorted(cmd_cnt.items(), key=lambda x: -x[1])[:20]:
    print(f"  {v:6d}  {k}  e.g. {samples[k]}")

# ---- 大报文之前/周围的小命令 ----
if big:
    t0 = big[0].get('ts') or 0
    print("\n== 首个大报文之前 5 秒内的所有 sendReport（小命令）")
    for r in sends:
        d = r.get('data') or {}
        ts = r.get('ts') or 0
        if t0 - 5000 <= ts <= t0 + 200:
            b = bytes.fromhex(hexclean(d.get('hex')))
            print(f"  ts={ts:10.1f} rid={r.get('reportId')} len={d.get('length'):4d}  {b[:24].hex(' ')}")

# ---- 会话结束后的小命令 ----
if big:
    t1 = big[-1].get('ts') or 0
    print("\n== 最后一个大报文之后 5 秒内的 sendReport")
    for r in sends:
        d = r.get('data') or {}
        ts = r.get('ts') or 0
        if t1 - 100 <= ts <= t1 + 5000:
            b = bytes.fromhex(hexclean(d.get('hex')))
            print(f"  ts={ts:10.1f} rid={r.get('reportId')} len={d.get('length'):4d}  {b[:24].hex(' ')}")
