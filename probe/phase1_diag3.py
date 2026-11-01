# -*- coding: utf-8 -*-
"""Phase 1 补充诊断 3：亮度曲线/淡入淡出复测 + 槽 97(红)/98(绿) 常亮供人眼定位

1) 淡入淡出：从亮度 0 切到 6，每 100ms 采样 1.5s，看是否为渐变
2) 亮度 1..6：每个值等 2.0s，采样 3 次，得出亮度曲线（排除过渡态）
3) 进入自定义模式，槽 97=红、槽 98=绿 同时常亮，脚本退出后保持不恢复
   （供人眼确认这两颗 LED 对应哪两个物理键；下次运行 probe/restore_orig.py 恢复）
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

ROOT = os.path.dirname(HERE)
STATE = os.path.join(ROOT, 'docs', 'restore_state.json')


def frame(kb):
    d = kb.read_all_lights_rgb()
    return [{'led': d[j * 4], 'r': d[j * 4 + 1], 'g': d[j * 4 + 2],
             'b': d[j * 4 + 3]} for j in range(min(128, len(d) // 4))]


def meanR(f):
    return round(sum(x['r'] for x in f) / len(f), 1)


def main():
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    try:
        orig_led = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        orig_gm = bytes(kb.get_game_mode()['raw'])
        with open(STATE, 'w', encoding='utf-8') as f:
            json.dump({'led': orig_led.hex(), 'custom': orig_custom.hex(),
                       'game_mode': orig_gm.hex(),
                       'note': 'Phase 1 诊断前原始状态，用于 restore_orig.py'},
                      f, indent=2)
        print('已保存原始状态 ->', STATE)

        def set_raw(mode=1, rgb=(255, 0, 0), cm=0, br=6, sp=3, direction=0):
            p = bytearray(16)
            p[0] = mode
            p[1:4] = bytes(rgb)
            p[4] = 255
            p[8] = cm
            p[9] = br
            p[10] = sp
            p[11] = direction
            p[14] = 0xAA
            p[15] = 0x55
            kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)

        # ---------- 1) 淡入淡出 ----------
        set_raw(1, (255, 0, 0), 0, 1, 3, 0)
        time.sleep(1.5)
        set_raw(1, (255, 0, 0), 0, 6, 3, 0)
        t0 = time.time()
        ramp = []
        for i in range(15):
            time.sleep(0.1)
            f = frame(kb)
            ramp.append({'t_ms': round((time.time() - t0) * 1000),
                         'meanR': meanR(f),
                         'maxR': max((x['r'] for x in f), default=0)})
        res['ramp_1_to_6'] = ramp
        print('[渐变] 亮度 1->6 每 100ms:',
              ' '.join(str(x['meanR']) for x in ramp))

        # ---------- 2) 亮度曲线（充分稳定） ----------
        rows = []
        for br in [1, 2, 3, 4, 5, 6]:
            set_raw(1, (255, 0, 0), 0, br, 3, 0)
            time.sleep(2.0)
            ms, mx = [], []
            for _ in range(3):
                f = frame(kb)
                ms.append(meanR(f))
                mx.append(max((x['r'] for x in f), default=0))
                time.sleep(0.1)
            # 单灯最大值 = 前景 LED 亮度
            single = round(sum(ms) * 128 / max(1, sum(
                1 for x in f if max(x['r'], x['g'], x['b']) > 0)), 1)
            rb = kb.get_led_effect()
            row = {'brightness': br, 'stored': rb['brightness'],
                   'meanR': ms, 'maxR': mx, 'per_led_estimate': single}
            rows.append(row)
            print('[亮度] %d -> 存%d 平均R %s 单灯≈%s' %
                  (br, rb['brightness'], ms, single))
        res['brightness_curve'] = rows

        # ---------- 3) 97 红 / 98 绿（保持不恢复） ----------
        set_raw(128, (255, 255, 255), 1, 6, 3, 0)
        time.sleep(0.2)
        buf = bytearray(512)
        buf[97 * 4:97 * 4 + 4] = bytes([97, 255, 0, 0])    # 槽97 = 红
        buf[98 * 4:98 * 4 + 4] = bytes([98, 0, 255, 0])    # 槽98 = 绿
        kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(buf), content_size=512)
        time.sleep(0.8)
        f = frame(kb)
        lit = [(x['led'], x['r'], x['g'], x['b']) for x in f
               if max(x['r'], x['g'], x['b']) > 0]
        print('\n>>> 已设置：槽97=红, 槽98=绿, 其它全灭。保持常亮，请人眼确认。')
        print('    实测点亮:', lit)
        res['locate'] = {'lit': [{'led': a, 'r': b, 'g': c, 'b': d}
                                 for a, b, c, d in lit]}
    finally:
        kb.close()
        out = os.path.join(ROOT, 'docs', 'phase1_diag3.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print('saved', out)


if __name__ == '__main__':
    main()
