# -*- coding: utf-8 -*-
"""Phase 3.6 续：宏播放方式 mask 语义（param2 = 0 常规 / 1 重复N次 / 2 再按结束）

用法:
  python phase3_macro_mask.py ledread   # 确认 97/98 缓冲（人眼定位用）
  python phase3_macro_mask.py repeat 3  # 宏 = 单动作 "a"，绑定 Insert，mask=1 param3=3
  python phase3_macro_mask.py toggle    # mask=2（再按结束）
  python phase3_macro_mask.py normal    # mask=0（常规）
  python phase3_macro_mask.py restore   # 清空宏表 + 还原槽103 + 灯效
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402
from phase3_macro import (encode_action, build_macro_payloads, send_macro_chunk,
                          read_macro_table, hx)  # noqa: E402

ROOT = os.path.dirname(HERE)
DUMP = os.path.join(ROOT, 'docs', 'device_dump_pre_test.json')


def bind_slot(kb, slot, data4):
    m = bytearray(bytes(kb.read_key_matrix()))
    m[slot * 4:slot * 4 + 4] = data4
    kb.request(CMD['SET_KEY'], bytes(m), content_size=512, timeout=0.8, retries=1)
    now = bytes(kb.read_key_matrix())
    print('槽%d 回读: %s (期望 %s)' % (slot, hx(now[slot * 4:slot * 4 + 4]),
                                     hx(data4)))


def write_macro_a(kb):
    acts = [encode_action(10, 0x04, 3, True), encode_action(10, 0x04, 3, False)]
    table, data = build_macro_payloads([{'id': 0, 'actions': acts}])
    a1 = send_macro_chunk(kb, table, 0, last_flag=False)
    a2 = send_macro_chunk(kb, data, 400, last_flag=True)
    t = read_macro_table(kb)
    print('宏表偏移[0]:', hx(t[:4]), '| data:', hx(data),
          '| ACK', sum(a1) + sum(a2), '/', len(a1) + len(a2))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'repeat'
    kb = AjazzKeyboard()
    dump = json.load(open(DUMP, encoding='utf-8'))
    try:
        if action == 'ledread':
            d = kb.read_all_lights_rgb()
            lit = [(d[i * 4], d[i * 4 + 1], d[i * 4 + 2], d[i * 4 + 3])
                   for i in range(128) if max(d[i * 4 + 1:i * 4 + 4]) > 0]
            print('GET_ALL_LIGHTS_RGB 点亮:', lit)
            print('GET_CUSTOM_LED_DATA 97/98:',
                  hx(bytes(kb.read_custom_led_data())[97 * 4:98 * 4 + 4]))
        elif action in ('repeat', 'toggle', 'normal'):
            write_macro_a(kb)
            if action == 'repeat':
                n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
                bind_slot(kb, 103, bytes([0x06, 0x00, 0x01, n & 0xFF]))
                print('已绑定 Insert -> MACRO0 mask=1 重复次数=%d' % n)
            elif action == 'toggle':
                bind_slot(kb, 103, bytes([0x06, 0x00, 0x02, 0x00]))
                print('已绑定 Insert -> MACRO0 mask=2（再按结束）')
            else:
                bind_slot(kb, 103, bytes([0x06, 0x00, 0x00, 0x00]))
                print('已绑定 Insert -> MACRO0 mask=0（常规）')
        elif action == 'restore':
            a = send_macro_chunk(kb, bytes(400), 0, last_flag=True)
            print('清空宏表 ACK', sum(a), '/', len(a), '| 非空:',
                  [i for i in range(100)
                   if int.from_bytes(read_macro_table(kb)[i * 4:i * 4 + 4], 'little')])
            base = bytes.fromhex(dump['key_matrix']['hex'])
            cur = bytearray(bytes(kb.read_key_matrix()))
            cur[103 * 4:103 * 4 + 4] = base[103 * 4:103 * 4 + 4]
            kb.request(CMD['SET_KEY'], bytes(cur), content_size=512, timeout=0.8, retries=1)
            kb.request(CMD['SET_LED_EFFECT'],
                       bytes.fromhex(dump['led_effect']['raw']['hex']), content_size=16)
            kb.request(CMD['SET_CUSTOM_LED_DATA'],
                       bytes.fromhex(dump['custom_led_data']['hex']), content_size=512)
            time.sleep(0.3)
            print('恢复: key=%s led=%s' % (
                bytes(kb.read_key_matrix()) == base,
                bytes(kb.get_led_effect()['raw']) ==
                bytes.fromhex(dump['led_effect']['raw']['hex'])))
    finally:
        kb.close()


if __name__ == '__main__':
    main()
