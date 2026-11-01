# -*- coding: utf-8 -*-
"""Phase 4 诊断：0x32 帧流到底改没改设备 LED 缓冲？0x32 回包是「回显」还是「设备状态」？

步骤（全部可程序化判定，不需要人眼）：
1. 把 LED 效果设成静态白（mode=1,colorMode=0,亮度6）→ 读 GET_ALL_LIGHTS_RGB 基线
2. 发一帧 0x32：87 键全红 → 立刻读 GET_ALL_LIGHTS_RGB，看是否变红
3. 再发一帧 0x32：87 键全 (1,2,3) 这种不可能是设备状态的值 → 看 0x32 的回包数据是回显还是设备状态
4. 把 0x32 请求数据全 0（黑）→ 看回包
输出 docs/phase4_diag.json
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


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b else ''


def read_all(kb):
    d = kb.read_all_lights_rgb()
    return [{'led': d[i * 4], 'r': d[i * 4 + 1], 'g': d[i * 4 + 2],
             'b': d[i * 4 + 3]} for i in range(min(128, len(d) // 4))]


def send_frame_collect(kb, payload):
    """发一帧，返回每包 ACK 数据段（前 24 字节）"""
    pkts = pack_frame(payload)
    acks = []
    for pkt in pkts:
        kb.proto.write_report(pkt)
        t0 = time.time()
        hit = None
        while time.time() - t0 < 0.3:
            r = kb.proto.read_report(timeout=0.02)
            if not r:
                continue
            p = r[1:]
            if len(p) >= 2 and p[0] == 0x55 and p[1] == 0x32:
                hit = p
                break
        acks.append(hx(hit[:28]) if hit else None)
    return acks


def main():
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    order = key_order()
    try:
        # 1) 基线：静态白
        kb.set_led_effect(1, 255, 255, 255, color_mode=0, brightness=6, speed=3,
                          direction=0)
        time.sleep(0.8)
        base = read_all(kb)
        lit = [x for x in base if max(x['r'], x['g'], x['b']) > 0]
        res['baseline'] = {'n_lit': len(lit), 'sample': lit[:4]}
        print('基线 静态白: 点亮 %d 颗, 前4=%s'
              % (len(lit), [(x['led'], x['r'], x['g'], x['b']) for x in lit[:4]]))

        # 2) 帧 = 全红
        payload = b''.join(bytes([kv, 255, 0, 0]) for kv in order)
        acks = send_frame_collect(kb, payload)
        time.sleep(0.2)
        after = read_all(kb)
        lit2 = [x for x in after if max(x['r'], x['g'], x['b']) > 0]
        n_red = sum(1 for x in lit2 if x['r'] > 200 and x['g'] < 50 and x['b'] < 50)
        res['after_allred'] = {'n_lit': len(lit2), 'n_red': n_red,
                               'sample': lit2[:4],
                               'acks': [a[:56] for a in acks if a]}
        print('发全红帧后: 点亮 %d 颗, 其中红色 %d 颗, 前4=%s'
              % (len(lit2), n_red, [(x['led'], x['r'], x['g'], x['b'])
                                    for x in lit2[:4]]))
        print('  首包 ACK:', acks[0])

        # 3) 帧 = 全是 (1,2,3) 不可能的值，看回包是回显还是设备状态
        payload2 = b''.join(bytes([kv, 1, 2, 3]) for kv in order)
        acks2 = send_frame_collect(kb, payload2)
        res['probe_echo'] = {'acks': [a[:56] for a in acks2 if a]}
        print('发的数据 1,2,3 -> 首包 ACK:', acks2[0])

        # 4) 帧 = 全 0
        payload3 = b''.join(bytes([kv, 0, 0, 0]) for kv in order)
        acks3 = send_frame_collect(kb, payload3)
        res['probe_zero'] = {'acks': [a[:56] for a in acks3 if a]}
        print('发的数据 0,0,0 -> 首包 ACK:', acks3[0])
    finally:
        kb.close()
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase4_diag.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved')


if __name__ == '__main__':
    main()
