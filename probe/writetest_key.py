#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改键写入通道验证：给一个「配置里不存在的槽位」写入映射 → 回读 → 还原。
   不使用真实按键的槽位，保证不改动任何实际功能键。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz

SLOT = 120  # MK87 官方配置 87 键里没有 value=120 的键，写入不影响任何实体键

kb = ajazz.AjazzKeyboard()
try:
    m = kb.read_key_matrix()
    assert len(m) == 512, len(m)
    orig = bytes(m[SLOT * 4:SLOT * 4 + 4])
    print(f'槽位 {SLOT} 原值: {orig.hex(" ")}')

    test = bytearray(m)
    test[SLOT * 4:SLOT * 4 + 4] = bytes([2, 0, 0x04, 0])  # pageType2, HID usage 0x04 = A
    print('写入测试值:', bytes(test[SLOT * 4:SLOT * 4 + 4]).hex(' '))
    resp = kb.request(ajazz.CMD['SET_KEY'], bytes(test), content_size=512,
                      timeout=0.8, retries=2)
    print('SET_KEY 响应长度:', len(resp))
    after = kb.read_key_matrix()
    got = bytes(after[SLOT * 4:SLOT * 4 + 4])
    print(f'回读槽位 {SLOT}: {got.hex(" ")}  ->', '写入成功 ✓' if got == bytes([2, 0, 0x04, 0]) else '未生效 ✗')

    print('还原原矩阵 ...')
    kb.request(ajazz.CMD['SET_KEY'], m, content_size=512, timeout=0.8, retries=2)
    final = kb.read_key_matrix()
    print('还原后整表一致:', '是 ✓' if final == m else '否 ✗')
    if final != m:
        diff = [i for i in range(128) if final[i * 4:i * 4 + 4] != m[i * 4:i * 4 + 4]]
        print('  不一致槽位:', diff)
finally:
    kb.close()
