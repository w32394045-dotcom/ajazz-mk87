#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TFT 通道探测：哪些写变体能触发设备响应？
变体：
  A) 4105B 缓冲，首字节 reportID=0，随后 8B 头(AA 10 30 ...)
  B) 4104B 缓冲，直接 8B 头(AA 10 30 ...)  —— 无 report ID 前缀
  C) 4105B 缓冲，首字节 reportID=1
  D) 4105B 缓冲，首字节 reportID=2
每个变体后监听 TFT + 主接口，打印收到的帧。
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz as A

kb = A.AjazzKeyboard()
try:
    tft = kb.tft
    print(f'TFT {tft.mi} out={tft.out_len} in={tft.in_len}')
    body = tft.out_len - 1          # 4104

    def drain(tag):
        n = 0
        while True:
            r = tft.read_report(timeout=0.15)
            if not r:
                break
            n += 1
            if n <= 5:
                print(f'  [{tag}] drain: {r[1:20].hex(" ")}')
        return n

    print('初始残留:', drain('init'))

    def hdr10():
        h = bytearray(8)
        h[0] = 0xAA
        h[1] = 0x10
        h[2] = 0x30
        h[6] = 1
        return bytes(h)

    def try_write(tag, data):
        try:
            w = tft.write_report(data)
            print(f'{tag}: WriteFile OK written={w} len={len(data)}')
            return True
        except Exception as e:
            print(f'{tag}: WriteFile FAIL {e}')
            return False

    def listen(tag, dur=0.9):
        got = []
        end = time.time() + dur
        while time.time() < end:
            r = tft.read_report(timeout=0.2)
            if r:
                got.append(r[1:])
                print(f'  [{tag}] TFT recv: {r[1:24].hex(" ")}')
        end = time.time() + 0.3
        while time.time() < end:
            r = kb.proto.read_report(timeout=0.1)
            if r:
                print(f'  [{tag}] MI_02 recv: {r[1:24].hex(" ")}')
        return got

    h = hdr10()

    print('\n== A) 4105B, reportID=0 ==')
    pkt = bytes([0]) + h + bytes(body - 8)
    if try_write('A', pkt):
        listen('A')

    print('\n== B) 4104B, 无 reportID（直接 AA 头）==')
    pkt = h + bytes(body - 8)
    if try_write('B', pkt):
        listen('B')

    for rid in (1, 2, 3, 0x41):
        print(f'\n== C) 4105B, reportID={rid} ==')
        pkt = bytes([rid]) + h + bytes(body - 8)
        if try_write(f'rid{rid}', pkt):
            listen(f'rid{rid}')

    print('\n== 收尾 drain ==')
    drain('final')
finally:
    kb.close()
