# -*- coding: utf-8 -*-
"""2.4G 帧流归属测试：三种打包各推 6 秒「脉冲」但颜色不同，便于人眼归属。

时间线：
  0-6s    变体 B（cmd 0x35，0xFF60，28B/包）：绿色脉冲
  6-7.5s  黑场
  7.5-13.5s 变体 C（cmd 0x3C，0xFF59，56B/包）：蓝色脉冲
  13.5-15s  黑场
  15-21s  变体 D（cmd 0x32，0xFF60，24B/包）：红色脉冲
最后恢复。
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import CMD  # noqa: E402
from phase4_frames import key_order  # noqa: E402
from _p6_variants import open_wireless, build_pkt  # noqa: E402

FPS = 20


def pkts_for(iface, kind, data):
    rep = iface.out_len - 1
    if kind == 'B':
        n = rep - 4
        total = -(-len(data) // n)
        return [build_pkt(rep, bytes([0xAA, CMD['SET_MUSIC_DATA'], k & 0xFF, 0]),
                          data[k * n:(k + 1) * n]) for k in range(total)]
    if kind == 'C':
        n = rep - 8
        total = -(-len(data) // n)
        return [build_pkt(rep, bytes([0xAA, CMD['SET_MUSIC_DATA_24G_64_BYTE'],
                                      len(data[k * n:(k + 1) * n]) & 0xFF,
                                      (k * n) & 0xFF, (k * n) >> 8, 0,
                                      1 if k == total - 1 else 0]),
                          data[k * n:(k + 1) * n]) for k in range(total)]
    n = rep - 8
    total = -(-len(data) // n)
    return [build_pkt(rep, bytes([0xAA, CMD['GET_LED_DATA'],
                                  len(data[k * n:(k + 1) * n]) & 0xFF,
                                  (k * n) & 0xFF, (k * n) >> 8, 0,
                                  1 if k == total - 1 else 0]),
                      data[k * n:(k + 1) * n]) for k in range(total)]


def stream_pulse(iface, kind, order, rgb, seconds):
    t0 = time.time()
    frames = 0
    while time.time() - t0 < seconds:
        v = 0.5 - 0.5 * math.cos((frames / FPS) * 2 * math.pi * 1.5)  # 1.5Hz 脉冲
        c = tuple(int(x * v) for x in rgb)
        if kind == 'D':
            data = bytearray()
            for kv in order:
                data += bytes([kv, c[0], c[1], c[2]])
            data = bytes(data)
        else:
            v565 = ((c[0] & 0xF8) << 8) | ((c[1] & 0xFC) << 3) | ((c[2] & 0xF8) >> 3)
            data = bytes([(v565 >> 8) & 0xFF, v565 & 0xFF]) * len(order)
        for p in pkts_for(iface, kind, data):
            iface.write_report(p)
        frames += 1
        target = t0 + frames / FPS
        dt = target - time.time()
        if dt > 0:
            time.sleep(dt)


def set_led(kb, mode, rgb=(255, 255, 255), cm=1, br=6):
    p = bytearray(16)
    p[0] = mode
    p[1:4] = bytes(rgb)
    p[4] = 0xFF
    p[8] = cm
    p[9] = br
    p[10] = 3
    p[14] = 0xAA
    p[15] = 0x55
    kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)


def custom_black(kb):
    buf = bytearray(512)
    for i in range(128):
        buf[i * 4:i * 4 + 4] = bytes([i, 0, 0, 0])
    kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(buf), content_size=512)


def main():
    kb, proto64 = open_wireless()
    order = key_order()
    try:
        orig = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        set_led(kb, 128, (255, 255, 255), 1, 6)
        custom_black(kb)
        time.sleep(0.4)
        print('0-6s  绿 = 0x35 (0xFF60)'); sys.stdout.flush()
        stream_pulse(kb.proto, 'B', order, (0, 255, 0), 6.0)
        time.sleep(1.5)
        print('7.5-13.5s 蓝 = 0x3C (0xFF59)'); sys.stdout.flush()
        if proto64:
            stream_pulse(proto64, 'C', order, (0, 0, 255), 6.0)
        time.sleep(1.5)
        print('15-21s 红 = 0x32 (0xFF60)'); sys.stdout.flush()
        stream_pulse(kb.proto, 'D', order, (255, 0, 0), 6.0)
        time.sleep(1.0)
        kb.request(CMD['SET_LED_EFFECT'], orig, content_size=16)
        kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
        print('恢复完成')
    finally:
        kb.close()


if __name__ == '__main__':
    main()
