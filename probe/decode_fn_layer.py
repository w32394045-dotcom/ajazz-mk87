#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解码真机 FN 层：把 0d 00 00 XX 的 param3 映射到官方 FUNC 功能表名称。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(os.path.dirname(HERE), 'docs')

with open(os.path.join(DOCS, 'device_dump.json'), encoding='utf-8') as f:
    dump = json.load(f)
with open(os.path.join(DOCS, 'keymap-tables.json'), encoding='utf-8') as f:
    tables = json.load(f)
with open(os.path.join(DOCS, 'device_config_32839.json'), encoding='utf-8') as f:
    cfg = json.load(f)

func_entries = tables['tables']['funcChars']['entries']
func_by_value = {e['value']: e['name'] for e in func_entries}
# 也把 FUNC_V2 的条目按 value 索引（pageType>=128 用）
fv2 = tables['tables']['funcV2Chars']['entries']
fv2_by_value = {e['value']: e['name'] for e in fv2}

cfg_by_slot = {k['value']: k for k in cfg['keyList']}


def as_bytes(v):
    if isinstance(v, dict):
        return bytes(v.get('bytes') or v.get('raw') or [])
    return bytes(v)


key = as_bytes(dump['key_matrix'])
fn = as_bytes(dump['fn_key_matrix'])

print('槽位  按键名        主层(4B)            主层含义                FN层(4B)             FN层含义')
print('-' * 110)
rows = []
for i in range(128):
    a = key[i * 4:i * 4 + 4]
    b = fn[i * 4:i * 4 + 4]
    if b == b'\x00\x00\x00\x00':
        continue
    name = cfg_by_slot.get(i, {}).get('name', '(未知)')
    # FN 层解码
    if b[0] == 0x0D:
        fv = (b[1] << 16) | (b[2] << 8) | b[3]
        fname = func_by_value.get(fv, fv2_by_value.get(fv, '?'))
        fn_desc = f'FUNC {fv} = {fname}'
    elif b[0] == 2:
        fn_desc = f'按键 usage 0x{b[2]:02X}'
    else:
        fn_desc = f'pageType={b[0]} p1={b[1]:02X} p2={b[2]:02X} p3={b[3]:02X}'
    # 主层解码
    if a[0] == 2:
        main_desc = f'按键 usage 0x{a[2]:02X}'
    elif a[0] == 3:
        main_desc = f'多媒体 0x{a[1]:02X}{a[2]:02X}'
    else:
        main_desc = f'pageType={a[0]}'
    print(f'{i:4d}  {name:12s} {a.hex(" "):19s} {main_desc:22s} {b.hex(" "):19s} {fn_desc}')
    rows.append({'slot': i, 'key': name, 'main': a.hex(' '), 'main_desc': main_desc,
                 'fn': b.hex(' '), 'fn_desc': fn_desc, 'func_id': (b[1] << 16) | (b[2] << 8) | b[3] if b[0] == 13 else None})

with open(os.path.join(DOCS, 'fn-layer-decode.json'), 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
print('\nsaved docs/fn-layer-decode.json')
