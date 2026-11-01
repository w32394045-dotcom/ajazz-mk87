#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记录各写命令的 ACK 帧格式（用于协议文档）"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz

CMD = ajazz.CMD
kb = ajazz.AjazzKeyboard()
try:
    def show(label, packets):
        if not packets:
            print(f'{label}: 无响应/超时')
            return
        for i, p in enumerate(packets):
            print(f'{label} ACK#{i}: cmd=0x{p[1]:02X} lenByte=0x{p[2]:02X} '
                  f'addr={p[3] | (p[4] << 8)} data={p[8:8+16].hex(" ")} (payload {len(p)}B)')

    print('== SET_LED_EFFECT ACK ==')
    p = bytearray(16)
    p[0], p[1], p[2], p[3], p[4] = 1, 255, 255, 255, 255
    p[8], p[9], p[10] = 1, 5, 3
    p[14], p[15] = 0xAA, 0x55
    show('LED', kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16,
                           timeout=0.8, retries=0, full_payloads=True))

    print('\n== SET_TEMPORARY_COMMAND_DATA（屏幕时间）ACK ==')
    now = time.localtime()
    q = bytearray(10)
    q[0], q[1], q[2] = 90, 1, 90
    q[3], q[4], q[5] = now.tm_year % 100, now.tm_mon, now.tm_mday
    q[6], q[7], q[8], q[9] = now.tm_hour, now.tm_min, now.tm_sec, (now.tm_wday + 1) % 7
    show('TIME', kb.request(CMD['SET_TEMPORARY_COMMAND_DATA'], bytes(q), content_size=24,
                            timeout=1.0, retries=0, full_payloads=True))

    print('\n== SET_KEY ACK ==')
    m = kb.read_key_matrix()
    show('KEY', kb.request(CMD['SET_KEY'], m, content_size=512, timeout=0.8,
                           retries=0, full_payloads=True)[:2])
finally:
    kb.close()
