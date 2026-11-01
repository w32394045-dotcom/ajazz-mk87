# -*- coding: utf-8 -*-
"""Phase 0：真机测试前自检（只做「原样回写 + 回读比对」，不改任何有效配置）

覆盖 TEST-PLAN Phase 0 / 1.1：
  - 设备连接与全量读取
  - SET_GAME_MODE / SET_LED_EFFECT / SET_KEY / SET_FN_KEY / SET_CUSTOM_LED_DATA
    五条写通道：原样回写 -> 回读 -> 逐字节比对
  - 记录每条命令的 ACK 响应（hex）与往返耗时

用法:
  python phase0_selftest.py            # 完整自检
  python phase0_selftest.py --no-write # 只读，不写任何东西
结果写到 docs/phase0_selftest.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402


def hx(b, n=None):
    if b is None:
        return None
    b = bytes(b)
    if n is not None:
        b = b[:n]
    return ' '.join(f'{x:02X}' for x in b)


def main():
    no_write = '--no-write' in sys.argv
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'no_write': no_write, 'checks': []}
    try:
        info = kb.get_device_info()
        res['device'] = {k: v for k, v in info.items() if k != 'raw'}
        print('设备:', 'VID=%04X PID=%04X' % (info['vid'], info['pid']),
              'fw=%s' % info['version'], 'workMode=%d' % info['workMode'],
              'battery=%d%%' % info['batteryLevel'],
              'charge=%d' % info['chargeStatus'])

        # ---- 基线读数 ----
        gm = bytes(kb.get_game_mode()['raw'])
        led = bytes(kb.get_led_effect()['raw'])
        keys = bytes(kb.read_key_matrix())
        fn = bytes(kb.read_fn_key_matrix())
        cled = bytes(kb.read_custom_led_data())
        res['baseline'] = {
            'game_mode': hx(gm), 'led_effect': hx(led),
            'key_matrix_sha': __import__('hashlib').sha256(keys).hexdigest(),
            'fn_matrix_sha': __import__('hashlib').sha256(fn).hexdigest(),
            'custom_led_sha': __import__('hashlib').sha256(cled).hexdigest(),
        }
        print('基线: game_mode', hx(gm, 8), '... / led', hx(led))
        print('      key_matrix 512B sha256=%s…' % res['baseline']['key_matrix_sha'][:16])

        if no_write:
            print('\n--no-write：只读模式，跳过所有写通道自检')
            return
        print()

        def check(name, cmd, payload, reader, size):
            r = {'name': name, 'cmd': f'0x{cmd:02X}', 'payload_len': len(payload),
                 'cmd_name': next((k for k, v in CMD.items() if v == cmd), '?')}
            t0 = time.time()
            resp = kb.request(cmd, payload, content_size=size, timeout=1.0,
                              retries=1, full_payloads=True)
            r['roundtrip_ms'] = round((time.time() - t0) * 1000, 1)
            r['resp_packets'] = len(resp)
            r['resp0_hex'] = hx(resp[0][:16]) if resp else None
            t1 = time.time()
            now = bytes(reader())
            r['readback_ms'] = round((time.time() - t1) * 1000, 1)
            r['match'] = now == bytes(payload)
            if not r['match']:
                bad = [i for i in range(min(len(now), len(payload)))
                       if now[i] != payload[i]]
                r['first_diffs'] = [{'off': i, 'wrote': payload[i], 'read': now[i]}
                                    for i in bad[:8]]
                r['n_diff'] = len(bad)
            res['checks'].append(r)
            print('[%s] %-24s cmd=%s len=%-3d ack=%d包 %6.1fms 回读%s'
                  % ('PASS' if r['match'] else 'FAIL', name, r['cmd'],
                     len(payload), r['resp_packets'], r['roundtrip_ms'],
                     '一致' if r['match'] else ('差异 %d 字节' % r['n_diff'])))
            print('       ACK:', r['resp0_hex'])
            return r['match']

        check('SET_GAME_MODE 回写', CMD['SET_GAME_MODE'], gm,
              lambda: kb.get_game_mode()['raw'], 56)
        check('SET_LED_EFFECT 回写', CMD['SET_LED_EFFECT'], led,
              lambda: kb.get_led_effect()['raw'], 16)
        check('SET_KEY 512B 回写', CMD['SET_KEY'], keys, kb.read_key_matrix, 512)
        check('SET_FN_KEY 512B 回写', CMD['SET_FN_KEY'], fn, kb.read_fn_key_matrix, 512)
        check('SET_CUSTOM_LED_DATA 回写', CMD['SET_CUSTOM_LED_DATA'], cled,
              kb.read_custom_led_data, 512)

        # ---- 纯读取通道耗时基线（供 Phase 4/5 的帧率预算参考） ----
        for name, fn in (('GET_KEY 512B', kb.read_key_matrix),
                         ('GET_LED_EFFECT 16B', lambda: kb.get_led_effect()['raw']),
                         ('GET_ALL_LIGHTS_RGB 512B', kb.read_all_lights_rgb)):
            t0 = time.time()
            fn()
            ms = (time.time() - t0) * 1000
            res['checks'].append({'name': name + ' 读取耗时', 'read_ms': round(ms, 1),
                                  'match': True})
            print('[INFO] %-26s %6.1f ms' % (name, ms))

        ok = all(c.get('match', True) for c in res['checks'])
        res['all_pass'] = ok
        print('\n== 自检结论:', 'PASS（五条写通道均原样回写一致）' if ok else 'FAIL', '==')
    finally:
        kb.close()
        out = os.path.join(os.path.dirname(HERE), 'docs', 'phase0_selftest.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print('saved', out)


if __name__ == '__main__':
    main()
