#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单包 ACK 测试：给 TFT 接口发 1 个真实的 AA 50 包，看多久回 55 41"""
import sys, time
sys.path.insert(0, r"C:\Users\ptfm\Documents\ajazz-re\probe")
import ajazz
from tft_upload_gif import load_gif, build_delay_table

GIF = r"C:\Users\ptfm\Pictures\Loli is a BEAST KILLING MACHINE ｜ Onimai Oniichan wa Oshimai!.gif"

kb = ajazz.AjazzKeyboard()
try:
    info = kb.get_device_info()
    print(f"device fw={info.get('version')} tftMaxFrames={info.get('tftMaxFrames')}")
    tft = kb.tft
    print(f"tft: mi={tft.mi} usagePage=0x{tft.usage_page:04X} in={tft.in_len} out={tft.out_len}")

    frames, delays, _, _ = load_gif(GIF, 140, 0)
    mv = build_delay_table(delays)
    data = bytes(mv) + b''.join(frames)
    body = tft.out_len - 1
    chunk = body - 8
    total = (len(data) + chunk - 1) // chunk
    part = data[:chunk]
    pkt = bytearray([0]) + bytearray(body)
    pkt[1:9] = bytes([0xAA, 0x50, 0, 0, total & 0xFF, (total >> 8) & 0xFF, 0x50, 0x06])
    pkt[9:9 + len(part)] = part
    print(f"total={total}, 发送首包 {len(pkt)}B ...")
    t0 = time.time()
    try:
        tft.write_report(bytes(pkt))
        print(f"write ok  ({time.time()-t0:.1f} ms)")
    except Exception as e:
        print(f"write error: {e}")

    print("监听 TFT 输入 3 秒 ...")
    n = 0
    while time.time() - t0 < 3.0:
        r = tft.read_report(timeout=0.3)
        if not r:
            continue
        n += 1
        print(f"  [{n}] +{(time.time()-t0)*1000:.0f}ms len={len(r)} {r[:24].hex(' ')}")
    print(f"共收到 {n} 帧")
finally:
    kb.close()
