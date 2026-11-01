#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 device_dump.json 里的按键矩阵：把 128 个 4 字节条目翻译成人类可读描述，
并比较 主按键层 / FN层 / 默认FN层 的差异。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(os.path.dirname(HERE), 'docs', 'device_dump.json')

USAGE = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F', 0x0A: 'G',
    0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L', 0x10: 'M', 0x11: 'N',
    0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R', 0x16: 'S', 0x17: 'T', 0x18: 'U',
    0x19: 'V', 0x1A: 'W', 0x1B: 'X', 0x1C: 'Y', 0x1D: 'Z',
    0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4', 0x22: '5', 0x23: '6', 0x24: '7',
    0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'Enter', 0x29: 'Esc', 0x2A: 'Backspace', 0x2B: 'Tab', 0x2C: 'Space',
    0x2D: '-', 0x2E: '=', 0x2F: '[', 0x30: ']', 0x31: '\\', 0x32: 'NUBS',
    0x33: ';', 0x34: "'", 0x35: '`', 0x36: ',', 0x37: '.', 0x38: '/', 0x39: 'CapsLock',
    0x3A: 'F1', 0x3B: 'F2', 0x3C: 'F3', 0x3D: 'F4', 0x3E: 'F5', 0x3F: 'F6',
    0x40: 'F7', 0x41: 'F8', 0x42: 'F9', 0x43: 'F10', 0x44: 'F11', 0x45: 'F12',
    0x46: 'PrintScreen', 0x47: 'ScrollLock', 0x48: 'Pause',
    0x49: 'Insert', 0x4A: 'Home', 0x4B: 'PageUp', 0x4C: 'Delete', 0x4D: 'End',
    0x4E: 'PageDown', 0x4F: 'Right', 0x50: 'Left', 0x51: 'Down', 0x52: 'Up',
    0x53: 'NumLock', 0x54: 'KP/', 0x55: 'KP*', 0x56: 'KP-', 0x57: 'KP+',
    0x58: 'KPEnter', 0x59: 'KP1', 0x5A: 'KP2', 0x5B: 'KP3', 0x5C: 'KP4',
    0x5D: 'KP5', 0x5E: 'KP6', 0x5F: 'KP7', 0x60: 'KP8', 0x61: 'KP9', 0x62: 'KP0',
    0x63: 'KP.', 0x64: 'NonUS\\', 0x65: 'App', 0x66: 'Power', 0x67: 'KP=',
    0x68: 'F13', 0x69: 'F14', 0x6A: 'F15', 0x6B: 'F16', 0x6C: 'F17', 0x6D: 'F18',
    0x6E: 'F19', 0x6F: 'F20', 0x70: 'F21', 0x71: 'F22', 0x72: 'F23', 0x73: 'F24',
    0xE0: 'LCtrl', 0xE1: 'LShift', 0xE2: 'LAlt', 0xE3: 'LGUI',
    0xE4: 'RCtrl', 0xE5: 'RShift', 0xE6: 'RAlt', 0xE7: 'RGUI',
}
# 设备实测 pageType 3 的取值（可能是功能动作/媒体键，待官方动作表确认）
TYPE3 = {0xE9: 'Volume+ (推测)', 0xEA: 'Volume- (推测)'}


def entry(decoded, idx):
    b = decoded[idx * 4: idx * 4 + 4]
    return bytes([b[0], b[1], b[2], b[3]])


def describe(b):
    page_type, p1, p2, p3 = b[0], b[1], b[2], b[3]
    if page_type == 2:
        name = USAGE.get(p2, f'usage?0x{p2:02X}')
        return f'普通键 {name} (HID 0x{p2:02X})'
    if page_type == 3:
        name = TYPE3.get(p1, '')
        extra = f' {name}' if name else ''
        return f'type3 param1=0x{p1:02X}{extra}'
    if page_type == 0:
        return '未定义(全0)'
    return f'pageType={page_type} p1=0x{p1:02X} p2=0x{p2:02X} p3=0x{p3:02X}'


def as_list(v):
    if isinstance(v, dict):
        return v.get('bytes') or v.get('raw') or []
    return v


def main():
    with open(DUMP, encoding='utf-8') as f:
        d = json.load(f)
    key = as_list(d['key_matrix'])
    fn = as_list(d['fn_key_matrix'])
    dfn = as_list(d['default_fn_key_matrix'])
    dkey = as_list(d['default_key_matrix'])

    cfg_path = os.path.join(os.path.dirname(HERE), 'docs', 'device_config_32839.json')
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            c = json.load(f)
        cfg = {int(k['value']): k for k in c.get('keyList', [])}

    print(f'矩阵长度: key={len(key)} fn={len(fn)} default_fn={len(dfn)} default_key={len(dkey)}')
    print(f'官方配置键位: {len(cfg)} 个')

    def slot(i):
        c = cfg.get(i)
        return f'[{c["name"]}]' if c else '[未在配置中]'

    print('\n== 主按键层（全部非零槽位）==')
    non_zero = 0
    for i in range(128):
        b = entry(key, i)
        if b != b'\x00\x00\x00\x00':
            non_zero += 1
            print(f'  slot {i:3d} {slot(i):<16} {b.hex(" ")}  {describe(b)}')
    print(f'  非零条目: {non_zero}/128')

    print('\n== 主层 vs FN 层差异 ==')
    diffs = [i for i in range(128) if entry(key, i) != entry(fn, i)]
    if not diffs:
        print('  无差异')
    for i in diffs:
        print(f'  slot {i:3d} {slot(i):<16} 主={entry(key, i).hex(" ")} ({describe(entry(key, i))})'
              f'  FN={entry(fn, i).hex(" ")} ({describe(entry(fn, i))})')

    print('\n== FN 层 vs 默认FN层差异 ==')
    diffs2 = [i for i in range(128) if entry(fn, i) != entry(dfn, i)]
    print('  差异数量:', len(diffs2))
    for i in diffs2[:24]:
        print(f'  slot {i:3d} {slot(i):<16} FN={entry(fn, i).hex(" ")}  默认={entry(dfn, i).hex(" ")}')

    out = {
        'key_matrix': [describe(entry(key, i)) for i in range(128)],
        'fn_key_matrix': [describe(entry(fn, i)) for i in range(128)],
        'key_vs_fn_diffs': diffs,
        'fn_vs_default_fn_diffs': diffs2,
    }
    with open(os.path.join(os.path.dirname(HERE), 'docs', 'keymap_device.json'),
              'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\nsaved docs/keymap_device.json')


if __name__ == '__main__':
    main()
