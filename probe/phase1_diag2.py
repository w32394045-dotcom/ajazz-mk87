# -*- coding: utf-8 -*-
"""Phase 1 补充诊断 2：亮度归一化复测 / 20-21-128 是否共用自定义表 / 97-98 槽位人眼定位

1) brightness 越界值(0,7..255) 回读规律，写两遍看是否稳定
2) 写 8 个槽位颜色后，分别在 mode 20 / 21 / 128 下采样，判断是否共用同一张自定义表
3) 槽 97 亮红色 3s -> 槽 98 亮绿色 4s（留绿色供人眼确认这两颗是哪两个键）
最后恢复原灯效/自定义数据。输出 docs/phase1_diag2.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

ROOT = os.path.dirname(HERE)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b is not None else None


def frame(kb):
    d = kb.read_all_lights_rgb()
    return [{'led': d[j * 4], 'r': d[j * 4 + 1], 'g': d[j * 4 + 2],
             'b': d[j * 4 + 3]} for j in range(min(128, len(d) // 4))]


def main():
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    orig_led = orig_custom = None
    try:
        orig_led = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())

        def set_raw(mode, rgb=(255, 255, 255), cm=1, br=6, sp=3, direction=0):
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

        def write_custom(entries):
            buf = bytearray(512)
            for i, (r, g, b) in entries.items():
                buf[i * 4:i * 4 + 4] = bytes([i, r, g, b])
            kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(buf), content_size=512)

        # ---------- 1) 亮度越界复测（每个值写两遍，中间读一次） ----------
        set_raw(1, (255, 0, 0), 0, 6, 3, 0)  # 静态红
        time.sleep(0.4)
        rows = []
        for br in [0, 1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16, 31, 100, 255]:
            rec = {'wrote': br}
            for rep in (1, 2):
                rb = bytearray(orig_led)
                rb[0] = 1
                rb[1:4] = b'\xFF\x00\x00'
                rb[8] = 0
                rb[9] = br
                kb.request(CMD['SET_LED_EFFECT'], bytes(rb), content_size=16)
                time.sleep(0.30)
                got = kb.get_led_effect()
                rec[f'stored{rep}'] = got['brightness']
                f = frame(kb)
                rec[f'meanR{rep}'] = round(sum(x['r'] for x in f) / len(f), 1)
                rec[f'nlit{rep}'] = sum(1 for x in f if max(x['r'], x['g'], x['b']) > 0)
            rec['stable'] = rec['stored1'] == rec['stored2']
            rows.append(rec)
            print('[亮度复测] 写 %3d -> 存 %3d/%3d 平均R %6s/%6s 点亮 %d/%d %s'
                  % (br, rec['stored1'], rec['stored2'], rec['meanR1'], rec['meanR2'],
                     rec['nlit1'], rec['nlit2'], '' if rec['stable'] else '<-- 不稳定'))
        res['brightness'] = rows

        # ---------- 2) 20/21/128 是否共用自定义表 ----------
        test_colors = {0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255),
                       3: (255, 255, 0), 4: (255, 0, 255), 5: (0, 255, 255),
                       6: (255, 255, 255), 7: (0, 0, 0)}
        fam = {}
        for m in (20, 21, 128):
            set_raw(m, (255, 255, 255), 1, 6, 3, 0)
            time.sleep(0.25)
            write_custom(test_colors)
            time.sleep(0.8)
            f = frame(kb)
            first8 = [(x['led'], x['r'], x['g'], x['b']) for x in f[:8]]
            n_lit = sum(1 for x in f if max(x['r'], x['g'], x['b']) > 0)
            fam[m] = {'first8': [{'led': a, 'r': b, 'g': c, 'b': d}
                                 for a, b, c, d in first8], 'n_lit': n_lit}
            print('[模式 %3d] 写 8 色后: 点亮 %2d 颗, 前8=%s'
                  % (m, n_lit, ' '.join('%d:%02X%02X%02X' % (a, b, c, d)
                                       for a, b, c, d in first8)))
        res['customFamily'] = fam

        # ---------- 3) 97 红 / 98 绿（人眼定位） ----------
        set_raw(128, (255, 255, 255), 1, 6, 3, 0)
        time.sleep(0.2)
        write_custom({97: (255, 0, 0)})
        print('\n>>> 现在只有槽 97 亮【红色】，保持 3 秒，请看是哪个键 <<<')
        time.sleep(3.0)
        write_custom({98: (0, 255, 0)})
        print('>>> 现在只有槽 98 亮【绿色】，保持 5 秒，请看是哪个键 <<<')
        time.sleep(5.0)
        res['locate'] = {'note': '97=红 98=绿'}
    finally:
        try:
            if orig_led is not None:
                kb.request(CMD['SET_LED_EFFECT'], orig_led, content_size=16)
            if orig_custom is not None:
                kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
            time.sleep(0.3)
            res['restore'] = {'led_ok': bytes(kb.get_led_effect()['raw']) == orig_led,
                              'custom_ok': bytes(kb.read_custom_led_data()) == orig_custom}
            print('恢复:', res['restore'])
        except Exception as e:  # noqa: BLE001
            res['restore'] = {'error': str(e)}
        finally:
            kb.close()
            out = os.path.join(ROOT, 'docs', 'phase1_diag2.json')
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            print('saved', out)


if __name__ == '__main__':
    main()
