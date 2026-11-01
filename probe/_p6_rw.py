# -*- coding: utf-8 -*-
"""2.4G 帧流格式探针 v2：边推边读（多线程）

一个线程按 20fps 推指定变体（全白/全绿等），主线程每 0.3s 读一次
GET_ALL_LIGHTS_RGB，看设备 LED 缓冲有没有被帧流改变。
若缓冲变了，说明该格式被固件接受（数据映射可能不同）。
用法: python _p6_rw.py D|C|B [秒=4]
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import CMD  # noqa: E402
from phase4_frames import key_order  # noqa: E402
from _p6_variants import open_wireless, build_pkt  # noqa: E402
from _p6_stream2 import pkts_for, set_led, custom_black  # noqa: E402

FPS = 20


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else 'D'
    sec = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    kb, proto64 = open_wireless()
    order = key_order()
    iface = proto64 if kind == 'C' else kb.proto
    stop = threading.Event()

    def build(kind, c):
        if kind == 'D':
            data = bytearray()
            for kv in order:
                data += bytes([kv, c, c, c])
            return bytes(data)
        v565 = ((c & 0xF8) << 8) | ((c & 0xFC) << 3) | ((c & 0xF8) >> 3)
        return bytes([(v565 >> 8) & 0xFF, v565 & 0xFF]) * len(order)

    def burst(col):
        data = build(kind, col)
        for p in pkts_for(iface, kind, data):
            iface.write_report(p)

    def streamer():
        t0 = time.time()
        f = 0
        while not stop.is_set() and time.time() - t0 < sec:
            burst(255)         # 全白
            f += 1
            target = t0 + f / FPS
            dt = target - time.time()
            if dt > 0:
                time.sleep(dt)

    try:
        orig = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        set_led(kb, 128, (255, 255, 255), 1, 6)
        custom_black(kb)
        time.sleep(0.4)
        base = kb.read_all_lights_rgb()
        print('基线点亮:', sum(1 for i in range(128) if max(base[i*4+1:i*4+4]) > 0))
        th = threading.Thread(target=streamer, daemon=True)
        th.start()
        rows = []
        t0 = time.time()
        while time.time() - t0 < sec:
            d = kb.read_all_lights_rgb()
            lit = [(d[i*4], d[i*4+1], d[i*4+2], d[i*4+3]) for i in range(128)
                   if max(d[i*4+1:i*4+4]) > 0]
            rows.append({'t': round(time.time() - t0, 2), 'n_lit': len(lit),
                         'first': lit[:2]})
            time.sleep(0.3)
        stop.set()
        th.join(timeout=1)
        for r in rows:
            print('  t=%.1fs 点亮 %2d 颗 首2=%s' % (r['t'], r['n_lit'], r['first']))
        changed = any(r['n_lit'] > 5 for r in rows)
        print('结论: 帧流%s改变 LED 缓冲' % ('有' if changed else '没有'))
        kb.request(CMD['SET_LED_EFFECT'], orig, content_size=16)
        kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
    finally:
        kb.close()


if __name__ == '__main__':
    main()
