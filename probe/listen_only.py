#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只监听不写：确认 MI_02 上 0x32 帧是否持续（判断是否外部软件在轮询/流式发帧）"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz as A

kb = A.AjazzKeyboard()
try:
    print('监听 MI_02 共 3 秒（不做任何写）...')
    end = time.time() + 3
    cnt = 0
    addrs = []
    first = True
    while time.time() < end:
        r = kb.proto.read_report(timeout=0.3)
        if not r:
            continue
        cnt += 1
        p = r[1:]
        if first:
            print('  首帧:', p[:32].hex(' '))
            first = False
        if len(p) >= 8 and p[0] == 0x55:
            addrs.append((p[1], p[3] | (p[4] << 8), p[5]))
    print(f'  MI_02 收到 {cnt} 帧 / 3s ≈ {cnt / 3:.1f} fps')
    if addrs:
        print('  前 12 个 (cmd, addr, i):', addrs[:12])
    print('\n监听 TFT 通道 1 秒（不做任何写）...')
    end = time.time() + 1
    got = 0
    while time.time() < end:
        r = kb.tft.read_report(timeout=0.2)
        if r:
            got += 1
            print('  TFT:', r[1:24].hex(' '))
    print('  TFT 帧数:', got)
finally:
    kb.close()
