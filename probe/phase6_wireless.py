# -*- coding: utf-8 -*-
"""Phase 6：2.4G 无线真机测试（VID 0C45 / PID FEFE 的 "2.4G Dongle"）

协议接口：usagePage 0xFF60（32 字节报文，官方过滤器表里有 0xFF60）——
实测 GET_DEVICE_INFO/GET_GAME_MODE/GET_LED_EFFECT 都能通。

用法:
  python phase6_wireless.py info          # 身份/电量/工作模式/灯效/矩阵对比
  python phase6_wireless.py led           # 2.4G 下写灯效（红）→ 回读 → 恢复
  python phase6_wireless.py frames A|B|C  # 三种音乐帧打包变体，各推一帧全红
  python phase6_wireless.py notify [秒]   # 监听设备上报（55 FC / 55 FA / A6 FF 等）
输出 docs/phase6_wireless.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import (_enum_paths, HidInterface, AjazzKeyboard, CMD)  # noqa: E402
from phase4_frames import key_order  # noqa: E402

ROOT = os.path.dirname(HERE)
DUMP = os.path.join(ROOT, 'docs', 'device_dump_pre_test.json')


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b else ''


def open_wireless():
    """自动找 2.4G dongle 的协议接口（0xFF60）或 USB 协议接口（0xFF68）"""
    ifaces = []
    for p in _enum_paths():
        low = p.lower()
        if 'vid_0c45' not in low:
            continue
        try:
            h = HidInterface(p)
        except OSError:
            continue
        ifaces.append(h)
    proto = next((i for i in ifaces if i.usage_page == 0xFF60 and i.out_len > 1), None)
    kind = '2.4G(0xFF60)'
    if proto is None:
        proto = next((i for i in ifaces if i.usage_page == 0xFF68 and i.out_len > 1), None)
        kind = 'USB(0xFF68)'
    if proto is None:
        raise RuntimeError('找不到协议接口（2.4G dongle 不在？）')
    kb = AjazzKeyboard.__new__(AjazzKeyboard)
    kb.ifaces = ifaces
    kb.proto = proto
    kb.tft = next((i for i in ifaces if i.usage_page == 0xFF67), None)
    return kb, kind, ifaces


def pack_generic_frames(kb, payload4b, mode='B'):
    """官方 2.4G 通用分支：每键 rgb→RGB565 高低字节，包 4 字节自定义头 AA 35 seq i"""
    rep = kb.proto.out_len - 1
    n = rep - 4                       # 每包数据长（28）
    stream = bytearray()
    for i in range(0, len(payload4b), 4):
        r, g, b = payload4b[i + 1], payload4b[i + 2], payload4b[i + 3]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
        stream += bytes([(v >> 8) & 0xFF, v & 0xFF])
    total = (len(stream) + n - 1) // n
    if mode == 'A':                   # 官方代码字面：ceil(len/n/2) 个包
        total = max(1, -(-len(stream) // n // 2))
    pkts = []
    for k in range(total):
        part = stream[k * n:(k + 1) * n]
        pkt = bytearray([0]) + bytearray(rep)
        pkt[1:5] = bytes([0xAA, CMD['SET_MUSIC_DATA'], k & 0xFF, 0])
        pkt[5:5 + len(part)] = part
        pkts.append(bytes(pkt))
    return pkts, len(stream), total


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'info'
    kb, kind, ifaces = open_wireless()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'action': action,
           'iface_kind': kind,
           'protocol_iface': {'usagePage': '0x%04X' % kb.proto.usage_page,
                              'out_len': kb.proto.out_len, 'in_len': kb.proto.in_len}}
    try:
        if action == 'info':
            info = kb.get_device_info()
            gm = kb.get_game_mode()
            led = kb.get_led_effect()
            dump = json.load(open(DUMP, encoding='utf-8'))
            km = bytes(kb.read_key_matrix())
            fn = bytes(kb.read_fn_key_matrix())
            allc = kb.read_all_lights_rgb()
            res.update({
                'device': {k: v for k, v in info.items() if k != 'raw'},
                'device_raw': hx(info['raw']),
                'game_mode': {k: v for k, v in gm.items() if k != 'raw'},
                'led_effect': {k: v for k, v in led.items() if k != 'raw'},
                'battery': info['batteryLevel'], 'charge': info['chargeStatus'],
                'workMode': info['workMode'],
                'manufacturer': info['manufacturer'], 'product': info['product'],
                'key_matrix_matches_usb_dump': km == bytes.fromhex(
                    dump['key_matrix']['hex']),
                'fn_matrix_matches_usb_dump': fn == bytes.fromhex(
                    dump['fn_key_matrix']['hex']),
                'n_lit': sum(1 for i in range(0, 128) if max(
                    allc[i * 4 + 1], allc[i * 4 + 2], allc[i * 4 + 3]) > 0),
            })
            print('[%s] 身份: VID=%04X PID=%04X manufacturer=%d product=%d '
                  'workMode=%d battery=%d%% charge=%d'
                  % (kind, info['vid'], info['pid'], info['manufacturer'],
                     info['product'], info['workMode'], info['batteryLevel'],
                     info['chargeStatus']))
            print('  版本 %s | 灯效 mode=%d rgb=(%d,%d,%d) brightness=%d'
                  % (info['version'], led['mode'], led['red'], led['green'],
                     led['blue'], led['brightness']))
            print('  按键矩阵 == USB 时代 dump:', res['key_matrix_matches_usb_dump'],
                  '| FN 层 == dump:', res['fn_matrix_matches_usb_dump'])
            print('  GET_ALL_LIGHTS_RGB 点亮 %d 颗' % res['n_lit'])
            print('  device raw:', res['device_raw'])

        elif action == 'led':
            orig = bytes(kb.get_led_effect()['raw'])
            p = bytearray(16)
            p[0] = 1
            p[1:4] = b'\xFF\x00\x00'
            p[4] = 0xFF
            p[8] = 0
            p[9] = 6
            p[10] = 3
            p[14] = 0xAA
            p[15] = 0x55
            kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)
            time.sleep(0.5)
            got = bytes(kb.get_led_effect()['raw'])
            allc = kb.read_all_lights_rgb()
            n_red = sum(1 for i in range(128)
                        if allc[i * 4 + 1] > 150 and allc[i * 4 + 2] < 80)
            res['led'] = {'wrote': hx(p), 'readback': hx(got),
                          'readback_ok': got[:14] == bytes(p)[:14],
                          'n_red': n_red}
            print('2.4G 写灯效: 回读%s 红色键 %d 颗' %
                  ('一致' if res['led']['readback_ok'] else '不一致', n_red))
            print('  wrote:', hx(p))
            print('  got  :', hx(got))
            time.sleep(0.8)
            kb.request(CMD['SET_LED_EFFECT'], orig, content_size=16)
            res['led']['restored'] = bytes(kb.get_led_effect()['raw']) == orig
            print('  恢复原灯效:', res['led']['restored'])

        elif action == 'frames':
            variant = sys.argv[2] if len(sys.argv) > 2 else 'B'
            # 先切自定义模式（帧流显示条件）
            p = bytearray(16)
            p[0] = 128
            p[1:4] = b'\xFF\xFF\xFF'
            p[4] = 0xFF
            p[8] = 1
            p[9] = 6
            p[10] = 3
            p[14] = 0xAA
            p[15] = 0x55
            kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)
            time.sleep(0.4)
            order = key_order()
            payload = b''.join(bytes([kv, 255, 0, 0]) for kv in order)
            pkts, nbytes, total = pack_generic_frames(kb, payload, variant)
            print('变体 %s: RGB565 流 %d 字节 -> %d 包' % (variant, nbytes, total))
            t0 = time.time()
            for k, pkt in enumerate(pkts):
                kb.proto.write_report(pkt)
                time.sleep(0.01)
            time.sleep(0.3)
            allc = kb.read_all_lights_rgb()
            n_red = sum(1 for i in range(128)
                        if allc[i * 4 + 1] > 150 and allc[i * 4 + 2] < 80)
            res['frames'] = {'variant': variant, 'stream_bytes': nbytes,
                             'packets': total, 'n_red_after': n_red,
                             'pkt0': hx(pkts[0][:16]) if pkts else None}
            print('  发送后红色键 %d 颗（若 >50 说明 2.4G 帧流生效）' % n_red)
            print('  首包:', hx(pkts[0][:16]) if pkts else None)

        elif action == 'notify':
            dur = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
            print('监听 %.0f 秒设备上报（请转旋钮/按 Fn 组合/切换页面）…' % dur)
            events = []
            t0 = time.time()
            while time.time() - t0 < dur:
                r = kb.proto.read_report(timeout=0.05)
                if r:
                    events.append({'t_ms': round((time.time() - t0) * 1000),
                                   'hex': hx(r[:24])})
            res['notify'] = {'duration': dur, 'n': len(events), 'events': events[:60]}
            print('共 %d 条:' % len(events))
            for e in events[:40]:
                print('  %6dms %s' % (e['t_ms'], e['hex']))
    finally:
        kb.close()
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase6_wireless.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved docs/phase6_wireless.json')


if __name__ == '__main__':
    main()
