# -*- coding: utf-8 -*-
"""Phase 1：灯效与设置真机测试

覆盖 TEST-PLAN Phase 1：
  1.3 关灯(mode=0)          -> 采样应全 0
  1.4 brightness=0          -> 是否等同关灯
  1.2 模式全表 1..19 + 128  -> 逐个下发，采样两帧，记录「点亮键数/颜色/是否在动」
  额外 20/21                -> 自定义模式族(20/21/128)是否为活模式
  1.5 自定义灯              -> 槽位 0..7 写 8 种颜色，验证 index==槽位
  1.6 游戏模式              -> 仅改 tftDisplayTime 位并原样回写(其余字段不动)
  1.7 屏幕时间              -> SET_TEMPORARY_COMMAND_DATA 时间帧回显

所有写操作在 finally 里恢复原值（led effect + custom led data + game mode）。
输出: docs/phase1_lighting.json
用法: python phase1_lighting.py [--skip-modes]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

MODE_NAMES = {
    1: '静态恒亮', 2: '单点亮', 3: '单熄灭', 4: '繁星点点', 5: '漫天飞雪',
    6: '百花争艳', 7: '动态呼吸', 8: '光谱循环', 9: '彩泉涌动', 10: '多彩纵横',
    11: '随波逐流', 12: '峰回路转', 13: '一触即发', 14: '一石二鸟', 15: '涟漪扩散',
    16: '川流不息', 17: '重峦叠嶂', 18: '斜风细雨', 19: '来回穿梭',
    20: '(自定义族20)', 21: '(自定义族21)', 128: '自定义',
}
MODE_DIR = {10: 3, 11: 0, 12: 0, 16: 0, 18: 0}


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b is not None else None


def sample(kb, n=2, gap=0.35):
    """采样 n 帧逐键颜色，返回 [{led,r,g,b}...] 列表"""
    out = []
    for i in range(n):
        d = kb.read_all_lights_rgb()
        frame = [{'led': d[j * 4], 'r': d[j * 4 + 1], 'g': d[j * 4 + 2],
                  'b': d[j * 4 + 3]} for j in range(min(128, len(d) // 4))]
        out.append(frame)
        if i != n - 1:
            time.sleep(gap)
    return out


def summarize(frames):
    f0 = frames[0]
    lit = [x for x in f0 if max(x['r'], x['g'], x['b']) > 0]
    s = {'n_led': len(f0), 'n_lit': len(lit)}
    if lit:
        s['mean'] = [round(sum(x[c] for x in lit) / len(lit)) for c in 'rgb']
        s['mean_hex'] = '#%02X%02X%02X' % tuple(s['mean'])
        # 色相分布广度：不同通道主导的灯数
        dom = {'r': 0, 'g': 0, 'b': 0, 'tie': 0}
        for x in lit:
            mx = max(x['r'], x['g'], x['b'])
            ch = [c for c in 'rgb' if x[c] == mx]
            if len(ch) == 1:
                dom[ch[0]] += 1
            else:
                dom['tie'] += 1
        s['dominance'] = dom
        s['max_ch'] = max(max(x['r'], x['g'], x['b']) for x in lit)
    if len(frames) > 1:
        f1 = frames[-1]
        s['flicker'] = max(
            abs(a['r'] - b['r']) + abs(a['g'] - b['g']) + abs(a['b'] - b['b'])
            for a, b in zip(f0, f1))
        s['n_changed'] = sum(1 for a, b in zip(f0, f1)
                             if (a['r'], a['g'], a['b']) != (b['r'], b['g'], b['b']))
        s['animated'] = s['n_changed'] > 0
    return s


def main():
    skip_modes = '--skip-modes' in sys.argv
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'tests': []}
    orig_led = None
    orig_custom = None
    orig_gm = None
    try:
        info = kb.get_device_info()
        res['device'] = {k: v for k, v in info.items() if k != 'raw'}
        orig_led = bytes(kb.get_led_effect()['raw'])
        orig_custom = bytes(kb.read_custom_led_data())
        orig_gm = bytes(kb.get_game_mode()['raw'])
        res['orig'] = {'led': hx(orig_led), 'custom_sha': __import__('hashlib').sha256(
            orig_custom).hexdigest(), 'game_mode': hx(orig_gm)}
        print('原始灯效:', hx(orig_led))
        print('battery=%d%% charge=%d' % (info['batteryLevel'], info['chargeStatus']))

        def set_led(mode, rgb=(255, 255, 255), cm=1, br=6, sp=3, direction=None):
            if direction is None:
                direction = MODE_DIR.get(mode, 0)
            return kb.set_led_effect(mode, rgb[0], rgb[1], rgb[2],
                                     color_mode=cm, brightness=br, speed=sp,
                                     direction=direction)

        def record(name, extra):
            res['tests'].append(dict(name=name, **extra))
            return extra

        # ---------- 基线 ----------
        base = summarize(sample(kb))
        record('基线(当前模式11)', {'sample': base})
        print('[基线] mode11 点亮 %d/%d 平均 %s 变化%d'
              % (base['n_lit'], base['n_led'], base.get('mean_hex'), base['n_changed']))

        # ---------- 1.3 关灯 ----------
        set_led(0)
        time.sleep(0.5)
        s = summarize(sample(kb))
        record('1.3 关灯 mode=0', {'sample': s,
                                 'pass': s['n_lit'] == 0,
                                 'note': '采样全 0 即通过'})
        print('[1.3] mode=0 -> 点亮 %d/%d %s' % (s['n_lit'], s['n_led'],
                                               'PASS' if s['n_lit'] == 0 else 'FAIL'))

        # ---------- 1.4 brightness=0（保持原模式） ----------
        raw = bytearray(orig_led)
        raw[9] = 0
        kb.request(CMD['SET_LED_EFFECT'], bytes(raw), content_size=16)
        time.sleep(0.5)
        s = summarize(sample(kb))
        back = bytes(kb.get_led_effect()['raw'])
        record('1.4 brightness=0', {'sample': s, 'readback': hx(back),
                                   'readback_ok': back == bytes(raw),
                                   'brightness_stored': kb.get_led_effect()['brightness'],
                                   'pass': s['n_lit'] == 0})
        print('[1.4] brightness=0 -> 点亮 %d/%d (回读 brightness=%d) %s'
              % (s['n_lit'], s['n_led'], kb.get_led_effect()['brightness'],
                 'PASS(等同关灯)' if s['n_lit'] == 0 else 'NOT-OFF(仅存值)'))

        # ---------- 恢复原灯效 ----------
        set_led(11, (255, 255, 255), 1, 6, 3, 0)

        # ---------- 1.2 模式全表 ----------
        if not skip_modes:
            sweep = []
            for m in list(range(1, 20)) + [20, 21, 128]:
                set_led(m)
                time.sleep(0.9)
                s = summarize(sample(kb))
                s['mode'] = m
                s['name'] = MODE_NAMES.get(m, '?')
                s['lit'] = s['n_lit'] > 0
                sweep.append(s)
                print('[1.2] mode %3d %-8s 亮:%3d/%d 平均:%-8s 动:%3d/%d 峰值:%3d %s'
                      % (m, s['name'], s['n_lit'], s['n_led'],
                         s.get('mean_hex', '-'), s.get('n_changed', 0), s['n_led'],
                         s.get('max_ch', 0),
                         '' if s['lit'] else '<-- 不亮!'))
            res['tests'].append({'name': '1.2 模式全表', 'sweep': sweep,
                                 'all_lit': all(x['lit'] for x in sweep)})
            print('[1.2] 全部模式是否都点亮:', 'YES' if all(x['lit'] for x in sweep)
                  else 'NO -> ' + ','.join(str(x['mode']) for x in sweep if not x['lit']))

        # ---------- 1.5 自定义灯（index==槽位 验证） ----------
        test_colors = [(0, 255, 0, 0), (1, 0, 255, 0), (2, 0, 0, 255),
                       (3, 255, 255, 0), (4, 255, 0, 255), (5, 0, 255, 255),
                       (6, 255, 255, 255), (7, 0, 0, 0)]
        set_led(128)
        time.sleep(0.3)
        wrote = bytearray(512)
        for s_i, r, g, b in test_colors:
            wrote[s_i * 4:s_i * 4 + 4] = bytes([s_i, r, g, b])
        kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(wrote), content_size=512)
        time.sleep(0.8)
        frames = sample(kb, n=2, gap=0.4)
        rb = bytes(kb.read_custom_led_data())
        s = summarize(frames)
        got = [(x['led'], x['r'], x['g'], x['b']) for x in frames[0][:8]]
        record('1.5 自定义灯', {
            'readback_ok': rb == bytes(wrote),
            'first8_readback': [{'led': rb[i * 4], 'r': rb[i * 4 + 1],
                                 'g': rb[i * 4 + 2], 'b': rb[i * 4 + 3]}
                                for i in range(8)],
            'first8_samples': [{'led': a, 'r': b, 'g': c, 'b': d} for a, b, c, d in got],
            'sample': s,
            'pass': s['n_lit'] > 0 and rb == bytes(wrote),
        })
        print('[1.5] 自定义: 回读%s 采样点亮 %d/%d 前8=%s'
              % ('一致' if rb == bytes(wrote) else '不一致', s['n_lit'], s['n_led'],
                 ' '.join('%d:%02X%02X%02X' % (a, b, c, d) for a, b, c, d in got)))

        # ---------- 1.7 屏幕时间帧 ----------
        try:
            resp = kb.set_tft_datetime()
            ok = bool(resp)
            record('1.7 屏幕时间', {'resp_hex': hx(resp), 'pass': ok})
            print('[1.7] 时间帧回显:', hx(resp))
        except Exception as e:  # noqa: BLE001
            record('1.7 屏幕时间', {'error': str(e), 'pass': False})
            print('[1.7] 时间帧异常:', e)

        # ---------- 1.6 游戏模式：只改 tftDisplayTime 位，原样回写 ----------
        try:
            gm = bytearray(bytes(kb.get_game_mode()['raw']))
            gm[7] = 1 if gm[7] == 0 else 0
            ok, now = kb.set_game_mode_raw(bytes(gm))
            rb = bytes(kb.get_game_mode()['raw'])
            same = rb[:7] == bytes(gm)[:7] and rb[8:] == bytes(gm)[8:]
            record('1.6 游戏模式位写入', {'wrote': hx(gm), 'readback': hx(rb),
                                        'match': ok, 'others_unchanged': same,
                                        'pass': ok and same})
            print('[1.6] 游戏模式 tftDisplayTime=%d 写入%s 其它字段%s'
                  % (gm[7], '一致' if ok else '不一致',
                     '未变' if same else '被改动!'))
            kb.set_game_mode_raw(orig_gm)  # 恢复
            print('      已恢复原 game_mode:', hx(kb.get_game_mode()['raw']) == hx(orig_gm))
        except Exception as e:  # noqa: BLE001
            record('1.6 游戏模式位写入', {'error': str(e), 'pass': False})
            print('[1.6] 异常:', e)

    finally:
        # ---------- 恢复 ----------
        try:
            if orig_led is not None:
                kb.request(CMD['SET_LED_EFFECT'], orig_led, content_size=16)
            if orig_custom is not None:
                kb.request(CMD['SET_CUSTOM_LED_DATA'], orig_custom, content_size=512)
            if orig_gm is not None:
                kb.set_game_mode_raw(orig_gm)
            time.sleep(0.3)
            now = bytes(kb.get_led_effect()['raw'])
            res['restore'] = {
                'led': hx(now), 'led_ok': now == orig_led,
                'custom_ok': bytes(kb.read_custom_led_data()) == orig_custom,
                'game_mode_ok': bytes(kb.get_game_mode()['raw']) == orig_gm,
            }
            print('\n恢复: led=%s custom=%s game_mode=%s'
                  % (res['restore']['led_ok'], res['restore']['custom_ok'],
                     res['restore']['game_mode_ok']))
        except Exception as e:  # noqa: BLE001
            res['restore'] = {'error': str(e)}
            print('恢复异常:', e)
        finally:
            kb.close()
            out = os.path.join(os.path.dirname(HERE), 'docs', 'phase1_lighting.json')
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            print('saved', out)


if __name__ == '__main__':
    main()
