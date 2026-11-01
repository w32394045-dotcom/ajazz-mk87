# -*- coding: utf-8 -*-
"""Phase 1 补充诊断：模式0残留灯 / 亮度取值 / 自定义模式族 20/21/128 / 物理槽位表

1) mode=0 时仍亮的那 1 颗 LED 是哪一颗（对照 ledKeyMap 命名）
2) brightness 0..7 / 255 的回读归一化与实际亮度
3) mode 20/21/128 的 6 颗绿灯是哪 6 颗
4) 把 128 个槽位全部写白色 -> 采样 -> 得出「真的有物理 LED 的槽位集合」，
   并与官方 ledKeyMap 的 slotsWithoutKey 对比（验证表是否准确）
5) 键位映射抽检：槽 0/1/5/33/49/83 逐个点亮，供人眼确认 index==槽位

所有改动在 finally 恢复。输出 docs/phase1_diag.json
用法: python phase1_diag.py [--skip-sweep]
"""
import json
import os
import sys
import time
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

ROOT = os.path.dirname(HERE)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b is not None else None


def load_keymap():
    p = os.path.join(ROOT, 'docs', 'lighting-modes.json')
    if not os.path.exists(p):
        return {}, []
    d = json.load(open(p, encoding='utf-8'))
    m = d['ledKeyMap']
    tbl = {x['ledId']: x['name'] for x in m['table']}
    return tbl, m['slotsWithoutKey']


def frame(kb):
    d = kb.read_all_lights_rgb()
    return [{'led': d[j * 4], 'r': d[j * 4 + 1], 'g': d[j * 4 + 2],
             'b': d[j * 4 + 3]} for j in range(min(128, len(d) // 4))]


def lit(f, names, thr=0):
    return [{'led': x['led'], 'key': names.get(x['led'], '?'),
             'rgb': [x['r'], x['g'], x['b']]}
            for x in f if max(x['r'], x['g'], x['b']) > thr]


def main():
    skip_sweep = '--skip-sweep' in sys.argv
    names, no_key = load_keymap()
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'ledKeyMap_size': len(names),
           'slotsWithoutKey_doc': no_key}
    orig_led = orig_custom = orig_gm = None
    try:
        orig_led = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        orig_gm = bytes(kb.get_game_mode()['raw'])

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
            return bytes(p)

        def write_custom(entries):
            buf = bytearray(512)
            for i, (r, g, b) in entries.items():
                buf[i * 4:i * 4 + 4] = bytes([i, r, g, b])
            kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(buf), content_size=512)
            return bytes(buf)

        # ---------- 1) mode=0 残留 ----------
        set_raw(0)
        time.sleep(0.6)
        f0 = frame(kb)
        res['mode0'] = {'lit': lit(f0, names), 'all_zero': all(
            max(x['r'], x['g'], x['b']) == 0 for x in f0)}
        print('[mode0] 残留:', res['mode0']['lit'])

        # ---------- 2) 亮度归一化 ----------
        br_rows = []
        for br in [0, 1, 2, 3, 4, 5, 6, 7, 255]:
            set_raw(1, (255, 0, 0), 0, br, 3, 0)   # colorMode=0 单色红
            time.sleep(0.35)
            rb = kb.get_led_effect()
            f = frame(kb)
            row = {'wrote': br, 'stored': rb['brightness'],
                   'stored_mode': rb['mode'], 'stored_cm': rb['colorMode'],
                   'n_lit': sum(1 for x in f if max(x['r'], x['g'], x['b']) > 0),
                   'red_max': max((x['r'] for x in f), default=0),
                   'red_mean': round(sum(x['r'] for x in f) / len(f), 1)}
            br_rows.append(row)
            print('[亮度] 写 %3d -> 存 %3d 点亮 %3d/%d 最大R %3d 平均R %s'
                  % (br, row['stored'], row['n_lit'], len(f), row['red_max'],
                     row['red_mean']))
        res['brightness'] = br_rows

        # ---------- 3) 模式 20/21/128 ----------
        fam = {}
        for m in (20, 21, 128):
            set_raw(m, (255, 255, 255), 1, 6, 3, 0)
            time.sleep(0.6)
            fam[m] = {'lit': lit(frame(kb), names)}
            print('[模式 %d] 点亮 %d 颗: %s' % (m, len(fam[m]['lit']),
                                           [x['led'] for x in fam[m]['lit']]))
        res['customFamily'] = fam

        # ---------- 4) 全白自定义 -> 物理槽位集合 ----------
        if not skip_sweep:
            set_raw(128, (255, 255, 255), 1, 6, 3, 0)
            time.sleep(0.2)
            write_custom({i: (255, 255, 255) for i in range(128)})
            time.sleep(1.2)
            f = frame(kb)
            physical = [x['led'] for x in f if max(x['r'], x['g'], x['b']) > 0]
            missing = [i for i in range(128) if i not in physical]
            # 再采一次确认静态
            time.sleep(0.5)
            f2 = frame(kb)
            physical2 = [x['led'] for x in f2 if max(x['r'], x['g'], x['b']) > 0]
            res['physicalSlots'] = {
                'n_lit': len(physical), 'lit': physical,
                'missing': missing, 'stable': physical == physical2,
                'doc_physical_expected': sorted(set(range(128)) - set(no_key)),
                'doc_missing_match': sorted(missing) == sorted(no_key),
                'unexpected_lit': [i for i in physical if i in no_key],
                'missing_but_doc_has_key': [i for i in missing if i not in no_key],
                'white_sample': [{'led': x['led'], 'key': names.get(x['led'], '?'),
                                  'rgb': [x['r'], x['g'], x['b']]}
                                 for x in f if max(x['r'], x['g'], x['b']) > 0][:4],
            }
            print('\n[全白] 点亮 %d 槽 (文档预期 %d)' % (
                len(physical), 128 - len(no_key)))
            print('  实际无灯槽:', missing)
            print('  文档无灯槽:', sorted(no_key))
            print('  文档说无灯但实际有灯:', res['physicalSlots']['unexpected_lit'])
            print('  文档说有线但实际无灯:', res['physicalSlots']['missing_but_doc_has_key'])
            print('  两次采样一致:', res['physicalSlots']['stable'])

            # ---------- 5) 单槽点亮抽检（给人眼看位置） ----------
            spot = [0, 5, 33, 49, 83, 91, 102, 127]
            rows = []
            for s in spot:
                write_custom({i: (255, 255, 255) if i == s else (0, 0, 0)
                              for i in range(128)})
                time.sleep(0.45)
                f = frame(kb)
                l = lit(f, names)
                rows.append({'slot': s, 'key': names.get(s, '?'),
                             'n_lit': len(l), 'lit': l})
                print('[单槽 %3d %-8s] 点亮 %d 颗 %s'
                      % (s, names.get(s, '?'), len(l),
                         [(x['led'], x['rgb']) for x in l][:3]))
            res['spotCheck'] = rows

    finally:
        try:
            if orig_led is not None:
                kb.request(CMD['SET_LED_EFFECT'], orig_led, content_size=16)
            if orig_custom is not None:
                kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
            if orig_gm is not None:
                kb.set_game_mode_raw(orig_gm)
            time.sleep(0.3)
            res['restore'] = {
                'led_ok': bytes(kb.get_led_effect()['raw']) == orig_led,
                'custom_ok': bytes(kb.read_custom_led_data()) == orig_custom,
                'game_mode_ok': bytes(kb.get_game_mode()['raw']) == orig_gm}
            print('\n恢复:', res['restore'])
        except Exception as e:  # noqa: BLE001
            res['restore'] = {'error': str(e)}
            print('恢复异常:', e)
        finally:
            kb.close()
            out = os.path.join(ROOT, 'docs', 'phase1_diag.json')
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            print('saved', out)


if __name__ == '__main__':
    main()
