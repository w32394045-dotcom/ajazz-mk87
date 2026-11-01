# -*- coding: utf-8 -*-
"""Phase 4 补充：mode=128 下逐键帧的生效与「停止后回落」时间

1. LED 效果切到 mode=128（自定义）
2. 发一帧全红（87 键）
3. 之后每 0.25s 读一次 GET_ALL_LIGHTS_RGB，连续 6s，记录红色键数变化
   -> 判断固件在停止收帧后多久回落到自定义表（H3 的量化）
4. 测试 mode=20 / 21 是否同样能显示帧
5. 收尾恢复原灯效 + 原自定义灯表
输出 docs/phase4_timeout.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402
from phase4_frames import key_order, pack_frame  # noqa: E402

ROOT = os.path.dirname(HERE)
DUMP = os.path.join(ROOT, 'docs', 'device_dump_pre_test.json')


def read_all(kb):
    d = kb.read_all_lights_rgb()
    return [{'led': d[i * 4], 'r': d[i * 4 + 1], 'g': d[i * 4 + 2],
             'b': d[i * 4 + 3]} for i in range(min(128, len(d) // 4))]


def n_red(kb):
    d = read_all(kb)
    return sum(1 for x in d if x['r'] > 150 and x['g'] < 80 and x['b'] < 80)


def send_frame(kb, payload, wait_ack=True):
    for pkt in pack_frame(payload):
        kb.proto.write_report(pkt)
        if wait_ack:
            t0 = time.time()
            while time.time() - t0 < 0.3:
                r = kb.proto.read_report(timeout=0.02)
                if not r:
                    continue
                p = r[1:]
                if len(p) >= 2 and p[0] == 0x55 and p[1] == 0x32:
                    break


def main():
    kb = AjazzKeyboard()
    order = key_order()
    red = b''.join(bytes([kv, 255, 0, 0]) for kv in order)
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    dump = json.load(open(DUMP, encoding='utf-8'))
    orig_led = bytes.fromhex(dump['led_effect']['raw']['hex'])
    orig_custom = bytes.fromhex(dump['custom_led_data']['hex'])
    try:
        for mode in (128, 20, 21):
            kb.request(CMD['SET_LED_EFFECT'],
                       bytes([mode, 255, 0, 0, 255, 0, 0, 0, 1, 6, 3, 0, 0, 0,
                              0xAA, 0x55]), content_size=16)
            time.sleep(0.5)
            base = n_red(kb)
            t0 = time.time()
            send_frame(kb, red)
            send_ms = round((time.time() - t0) * 1000, 1)
            samples = []
            for i in range(25):
                samples.append({'ms': round((time.time() - t0) * 1000),
                                'n_red': n_red(kb)})
                time.sleep(0.24)
            # 停止收帧后是否回落
            row = {'mode': mode, 'base_n_red': base, 'send_ms': send_ms,
                   'samples': samples}
            res['mode_%d' % mode] = row
            print('mode %3d: 基线红 %d 颗, 发帧 %sms -> 采样 n_red: %s'
                  % (mode, base, send_ms, [s['n_red'] for s in samples]))
    finally:
        kb.request(CMD['SET_LED_EFFECT'], orig_led, content_size=16)
        kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
        time.sleep(0.3)
        res['restore'] = {'led_ok': bytes(kb.get_led_effect()['raw']) == orig_led,
                          'custom_ok': bytes(kb.read_custom_led_data()) == orig_custom}
        print('恢复:', res['restore'])
        kb.close()
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase4_timeout.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved')


if __name__ == '__main__':
    main()
