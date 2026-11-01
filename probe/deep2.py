#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖：读 SN / OTA 系统信息 / 被动监听设备通知（5 秒）"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz

kb = ajazz.AjazzKeyboard()
try:
    print('== 设备 SN（OTA_GET_DEVICE_SN 0x84）==')
    hdr = bytes([0xAA, ajazz.CMD['OTA_GET_DEVICE_SN'], 0, 0, 0, 0, 0, 0])
    packets = kb.request(ajazz.CMD['OTA_GET_DEVICE_SN'], b'', content_size=56,
                         custom_header=hdr, timeout=1.2, retries=1, full_payloads=True)
    for p in packets:
        print('  payload:', p.hex(' '))
        if len(p) > 8:
            n = p[2] or 8
            n = min(n, 56)
            raw = p[8:8 + n]
            txt = raw.rstrip(b'\x00').decode('utf-8', 'replace')
            print(f'  长度字节={p[2]}  SN={txt!r}  hex={raw.hex(" ")}')

    print('\n== OTA 系统信息（0x80）==')
    hdr2 = bytes([0xAA, ajazz.CMD['OTA_GET_DEVICE_SYSTEM_INFO'], 0, 0, 0, 0, 0, 0])
    d = kb.request(ajazz.CMD['OTA_GET_DEVICE_SYSTEM_INFO'], b'', content_size=56,
                   custom_header=hdr2, timeout=1.2, retries=1)
    print('  raw:', d.hex(' '))
    if len(d) >= 10:
        def bcd(a, b):
            return ((a & 0x0F) + ((a & 0xF0) >> 4) * 10 + b * 100) / 100
        print(f'  bootloader={bcd(d[0], d[1])}  app={bcd(d[2], d[3])}')
        print(f'  manufacturer={d[4] | (d[5] << 8)} product={d[6] | (d[7] << 8)}')
        print(f'  runningArea={d[8]} (16=app, 48=boot) workMode={d[9]}')

    print('\n== 被动监听主协议接口 5 秒（设备主动上报）==')
    t0 = time.time()
    got = 0
    while time.time() - t0 < 5:
        r = kb.proto.read_report(timeout=0.4)
        if r:
            got += 1
            payload = r[1:]
            cmd = payload[1] if len(payload) > 1 else -1
            name = ajazz.CMD_NAME.get(cmd, '?')
            print(f'  [{time.time() - t0:5.2f}s] cmd=0x{cmd:02X} ({name}) '
                  f'len={len(payload)}: {payload.hex(" ")}')
    print(f'  5 秒内收到 {got} 个主动上报')
finally:
    kb.close()
