# -*- coding: utf-8 -*-
"""2.4G 显示链路对照测试：先确认「静态灯效 / 自定义表」在 2.4G 下能不能显示，
再判断逐键帧流到底是没生效还是没显示。

时间线（脚本按顺序执行，每段之间有 0.5s 黑场）：
  t=0.0 +0.0~3.0  静态红（mode=1, colorMode=0, 亮度6）
  t=3.5 +0.0~3.0  自定义绿（mode=128 + SET_CUSTOM_LED_DATA 全绿）
  t=7.0 +0.0~2.0  自定义模式 + 0x35 绿色帧流
  t=9.5 +0.0~2.0  自定义模式 + 0x3C 蓝色帧流（64B 接口）
  t=12.0 +0.0~2.0 自定义模式 + 0x32 红色帧流
最后恢复原状。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import CMD  # noqa: E402
from phase4_frames import key_order  # noqa: E402
from _p6_variants import open_wireless, read_red, build_pkt  # noqa: E402
from _p6_stream import stream, rgb565_stream, payload4  # noqa: E402

ROOT = os.path.dirname(HERE)


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


def custom_all(kb, rgb):
    buf = bytearray(512)
    for i in range(128):
        buf[i * 4:i * 4 + 4] = bytes([i, rgb[0], rgb[1], rgb[2]])
    kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(buf), content_size=512)


def main():
    kb, proto64 = open_wireless()
    order = key_order()
    res = {'steps': []}
    try:
        orig = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        t0 = time.time()
        print('t=+0.0  静态红（3s）'); sys.stdout.flush()
        set_led(kb, 1, (255, 0, 0), 0, 6)
        time.sleep(3.0)
        res['steps'].append({'t': 0, 'what': 'static red', 'red': read_red(kb)})

        print('t=+3.5  自定义绿（3s）'); sys.stdout.flush()
        set_led(kb, 128, (255, 255, 255), 1, 6)
        custom_all(kb, (0, 255, 0))
        time.sleep(3.0)
        d = kb.read_all_lights_rgb()
        n_green = sum(1 for i in range(128)
                      if d[i * 4 + 2] > 150 and d[i * 4 + 1] < 80)
        res['steps'].append({'t': 3.5, 'what': 'custom green', 'n_green': n_green})

        print('t=+7.0  0x35 绿色帧流（2s）'); sys.stdout.flush()
        stream(kb.proto, 'B', rgb565_stream(order, (0, 255, 0)), 2.0, 'B')
        res['steps'].append({'t': 7.0, 'what': '0x35 frames'})

        print('t=+9.5  0x3C 蓝色帧流（2s）'); sys.stdout.flush()
        if proto64:
            stream(proto64, 'C', rgb565_stream(order, (0, 0, 255)), 2.0, 'C')
        res['steps'].append({'t': 9.5, 'what': '0x3C frames'})

        print('t=+12.0 0x32 红色帧流（2s）'); sys.stdout.flush()
        stream(kb.proto, 'D', payload4(order, (255, 0, 0)), 2.0, 'D')
        res['steps'].append({'t': 12.0, 'what': '0x32 frames'})

        time.sleep(1.0)
        kb.request(CMD['SET_LED_EFFECT'], orig, content_size=16)
        kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
        res['restored'] = True
        print('已恢复原灯效')
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase6_display.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
    finally:
        kb.close()


if __name__ == '__main__':
    main()
