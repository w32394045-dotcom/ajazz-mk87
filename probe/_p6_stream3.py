# -*- coding: utf-8 -*-
"""2.4G 帧流归属（第二轮）：三种打包按 D→C→B 顺序各推 8 秒**全键盘白色脉冲**，
中间 2.5 秒全黑间隔。人眼只需数「看到几次白色脉冲」。

  1) 0-8s    变体 D: cmd 0x32, 0xFF60, 24B/包, 4B/键
  2) 10.5-18.5s 变体 C: cmd 0x3C, 0xFF59, 56B/包, RGB565
  3) 21-29s  变体 B: cmd 0x35, 0xFF60, 28B/包, RGB565
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
from _p6_stream2 import pkts_for, set_led, custom_black  # noqa: E402

FPS = 20


def stream_white(iface, kind, order, seconds, freq=1.2):
    t0 = time.time()
    frames = 0
    while time.time() - t0 < seconds:
        v = 0.5 - 0.5 * math.cos((frames / FPS) * 2 * math.pi * freq)
        c = int(255 * v)
        if kind == 'D':
            data = bytearray()
            for kv in order:
                data += bytes([kv, c, c, c])
            data = bytes(data)
        else:
            v565 = ((c & 0xF8) << 8) | ((c & 0xFC) << 3) | ((c & 0xF8) >> 3)
            data = bytes([(v565 >> 8) & 0xFF, v565 & 0xFF]) * len(order)
        for p in pkts_for(iface, kind, data):
            iface.write_report(p)
        frames += 1
        target = t0 + frames / FPS
        dt = target - time.time()
        if dt > 0:
            time.sleep(dt)


def main():
    kb, proto64 = open_wireless()
    order = key_order()
    try:
        orig = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        set_led(kb, 128, (255, 255, 255), 1, 6)
        custom_black(kb)
        time.sleep(0.4)
        print('1) 0-8s   D 0x32  白色脉冲'); sys.stdout.flush()
        stream_white(kb.proto, 'D', order, 8.0)
        time.sleep(2.5)
        print('2) 10.5-18.5s C 0x3C  白色脉冲'); sys.stdout.flush()
        if proto64:
            stream_white(proto64, 'C', order, 8.0)
        time.sleep(2.5)
        print('3) 21-29s B 0x35  白色脉冲'); sys.stdout.flush()
        stream_white(kb.proto, 'B', order, 8.0)
        time.sleep(1.0)
        kb.request(CMD['SET_LED_EFFECT'], orig, content_size=16)
        kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
        print('恢复完成')
    finally:
        kb.close()


if __name__ == '__main__':
    main()
