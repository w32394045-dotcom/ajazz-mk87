#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按键矩阵深挖测试：单键读取 / 全量矩阵 / SET_KEY 原样回写（噪声级写入，不改变功能）"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz

kb = ajazz.AjazzKeyboard()
try:
    print('== 单键读取（自定义头 addr=key*4）==')
    for k in [0, 1, 12, 13, 14, 15, 16, 17, 99, 100, 102]:
        hdr = bytes([0xAA, ajazz.CMD['GET_KEY'], 4,
                     (k * 4) & 0xFF, (k * 4) >> 8 & 0xFF, 0, 0, 0])
        raw = kb.request(ajazz.CMD['GET_KEY'], b'', content_size=4,
                         custom_header=hdr, timeout=0.5, retries=1)
        print(f'  key {k:3d}: {raw.hex(" ")}')

    print('== 全量矩阵 ==')
    m = kb.read_key_matrix()
    print('  len =', len(m), ' first64 =', m[:64].hex(' '))
    f = kb.read_fn_key_matrix()
    print('  fn len =', len(f), ' same_as_main =', m == f)

    print('== SET_KEY 原样回写（不改变键位）==')
    resp = kb.request(ajazz.CMD['SET_KEY'], m, content_size=512,
                      timeout=0.8, retries=1)
    print('  SET_KEY 响应数据长度 =', len(resp))
    m2 = kb.read_key_matrix()
    print('  回写后矩阵完全一致 =', m == m2)
finally:
    kb.close()
