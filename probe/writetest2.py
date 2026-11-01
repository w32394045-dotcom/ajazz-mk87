#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写通道验证（不改任何可见状态）：
   1) SET_GAME_MODE 原样回写当前 56 字节 → 回读一致
   2) SET_CUSTOM_LED_DATA 原样回写当前 512 字节 → 回读一致
   并记录两者的 ACK 回显帧。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz

CMD = ajazz.CMD
kb = ajazz.AjazzKeyboard()
try:
    print('== 1) SET_GAME_MODE 原样回写 ==')
    gm = kb.get_game_mode()
    raw = bytes(gm['raw'])
    print('  当前 raw:', raw.hex(' '))
    packs = kb.request(CMD['SET_GAME_MODE'], raw, content_size=56,
                       timeout=0.8, retries=1, full_payloads=True)
    for p in packs:
        print(f'  ACK cmd=0x{p[1]:02X} lenByte=0x{p[2]:02X} addr={p[3] | (p[4] << 8)} '
              f'data={p[8:8+20].hex(" ")}')
    gm2 = kb.get_game_mode()
    print('  回读一致:', '是 ✓' if bytes(gm2['raw']) == raw else f'否 ✗ ({bytes(gm2["raw"]).hex(" ")})')

    print('\n== 2) SET_CUSTOM_LED_DATA 原样回写（当前全 0）==')
    led = kb.read_custom_led_data()
    print('  当前长度:', len(led), '前16字节:', led[:16].hex(' '))
    packs = kb.request(CMD['SET_CUSTOM_LED_DATA'], led, content_size=512,
                       timeout=0.8, retries=1, full_payloads=True)
    print('  ACK 数量:', len(packs))
    if packs:
        p = packs[0]
        print(f'  ACK#0 cmd=0x{p[1]:02X} lenByte=0x{p[2]:02X} addr={p[3] | (p[4] << 8)} '
              f'data={p[8:8+16].hex(" ")}')
    led2 = kb.read_custom_led_data()
    print('  回读一致:', '是 ✓' if led2 == led else '否 ✗')
finally:
    kb.close()
