# -*- coding: utf-8 -*-
"""2.4G 音乐帧格式穷举探针：把「87 键全红」用多种打包方式发一遍，
每次之后读 GET_ALL_LIGHTS_RGB 看红色键数（>50 视为该格式生效）。

变体:
  A  0x35 SET_MUSIC_DATA，RGB565 流，官方代码字面包数 ceil(len/28/2)=4
  B  0x35，RGB565 流，28 字节/包 × 7 包
  C  0x3C SET_MUSIC_DATA_24G_64_BYTE，RGB565 流，56 字节/包（走 0xFF60）
  D  0x32 GET_LED_DATA，4B/键，24 字节/包（32B 报文的 USB 同款逻辑）
  E  0x3C，RGB565 流，24 字节/包
  F  0x35，走 0xFF59（64B 报文），60 字节/包
输出 docs/_p6_variants.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import _enum_paths, HidInterface, AjazzKeyboard, CMD  # noqa: E402
from phase4_frames import key_order  # noqa: E402

ROOT = os.path.dirname(HERE)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b else ''


def open_wireless():
    ifaces = []
    for p in _enum_paths():
        if 'vid_0c45' not in p.lower():
            continue
        try:
            h = HidInterface(p)
        except OSError:
            continue
        ifaces.append(h)
    proto = next((i for i in ifaces if i.usage_page == 0xFF60 and i.out_len > 1), None)
    proto64 = next((i for i in ifaces if i.usage_page == 0xFF59 and i.out_len > 1), None)
    kb = AjazzKeyboard.__new__(AjazzKeyboard)
    kb.ifaces = ifaces
    kb.proto = proto
    kb.tft = None
    return kb, proto64


def set_custom_mode(kb):
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


def read_red(kb):
    d = kb.read_all_lights_rgb()
    n = 0
    for i in range(128):
        r, g, b = d[i * 4 + 1], d[i * 4 + 2], d[i * 4 + 3]
        if r > 150 and g < 80 and b < 80:
            n += 1
    return n


def send_pkts(iface, pkts, name):
    t0 = time.time()
    for p in pkts:
        iface.write_report(p)
        time.sleep(0.005)
    ms = (time.time() - t0) * 1000
    # 静默读掉可能的回包
    t1 = time.time()
    n = 0
    while time.time() - t1 < 0.15:
        if iface.read_report(timeout=0.02):
            n += 1
    return round(ms, 1), n


def build_pkt(rep_len, hdr, data):
    pkt = bytearray([0]) + bytearray(rep_len)
    pkt[1:1 + len(hdr)] = hdr
    pkt[1 + len(hdr):1 + len(hdr) + len(data)] = data
    return bytes(pkt)


def main():
    kb, proto64 = open_wireless()
    order = key_order()
    payload4 = b''.join(bytes([kv, 255, 0, 0]) for kv in order)
    stream565 = bytearray()
    for i in range(0, len(payload4), 4):
        r, g, b = payload4[i + 1], payload4[i + 2], payload4[i + 3]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
        stream565 += bytes([(v >> 8) & 0xFF, v & 0xFF])
    stream565 = bytes(stream565)
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
           'proto32': {'usagePage': '0x%04X' % kb.proto.usage_page,
                       'out_len': kb.proto.out_len},
           'proto64': {'usagePage': '0x%04X' % proto64.usage_page,
                       'out_len': proto64.out_len} if proto64 else None,
           'variants': []}
    try:
        for name in 'ABCDEF':
            set_custom_mode(kb)
            base = read_red(kb)
            if name == 'A':
                n = 28
                total = max(1, -(-len(stream565) // n // 2))
                pkts = [build_pkt(32, bytes([0xAA, CMD['SET_MUSIC_DATA'],
                                             k & 0xFF, 0]), stream565[k * n:(k + 1) * n])
                        for k in range(total)]
                ms, nre = send_pkts(kb.proto, pkts, name)
            elif name == 'B':
                n = 28
                total = -(-len(stream565) // n)
                pkts = [build_pkt(32, bytes([0xAA, CMD['SET_MUSIC_DATA'],
                                             k & 0xFF, 0]), stream565[k * n:(k + 1) * n])
                        for k in range(total)]
                ms, nre = send_pkts(kb.proto, pkts, name)
            elif name == 'C':
                n = 56
                total = -(-len(stream565) // n)
                if not proto64:
                    ms, nre, pkts = 0, -1, []
                else:
                    pkts = [build_pkt(64, bytes([0xAA, CMD['SET_MUSIC_DATA_24G_64_BYTE'],
                                                 len(stream565[k * n:(k + 1) * n]) & 0xFF,
                                                 (k * n) & 0xFF, (k * n) >> 8, 0,
                                                 1 if k == total - 1 else 0]),
                                      stream565[k * n:(k + 1) * n]) for k in range(total)]
                    ms, nre = send_pkts(proto64, pkts, name)
            elif name == 'D':
                n = 24
                total = -(-len(payload4) // n)
                pkts = [build_pkt(32, bytes([0xAA, CMD['GET_LED_DATA'],
                                             len(payload4[k * n:(k + 1) * n]) & 0xFF,
                                             (k * n) & 0xFF, (k * n) >> 8, 0,
                                             1 if k == total - 1 else 0]),
                                  payload4[k * n:(k + 1) * n]) for k in range(total)]
                ms, nre = send_pkts(kb.proto, pkts, name)
            elif name == 'E':
                n = 24
                total = -(-len(stream565) // n)
                pkts = [build_pkt(32, bytes([0xAA, CMD['SET_MUSIC_DATA_24G_64_BYTE'],
                                             total & 0xFF, (total >> 8) & 0xFF,
                                             k & 0xFF, (k >> 8) & 0xFF,
                                             0, 1 if k == total - 1 else 0]),
                                  stream565[k * n:(k + 1) * n]) for k in range(total)]
                ms, nre = send_pkts(kb.proto, pkts, name)
            else:  # F: 0xFF59 64B 报文
                if not proto64:
                    ms, nre, pkts = 0, -1, []
                else:
                    n = 60
                    total = -(-len(stream565) // n)
                    pkts = [build_pkt(64, bytes([0xAA, CMD['SET_MUSIC_DATA'],
                                                 k & 0xFF, 0]), stream565[k * n:(k + 1) * n])
                            for k in range(total)]
                    ms, nre = send_pkts(proto64, pkts, name)
            time.sleep(0.25)
            red_after = read_red(kb)
            row = {'variant': name, 'packets': len(pkts), 'send_ms': ms,
                   'base_red': base, 'red_after': red_after,
                   'works': red_after > 50,
                   'first_pkt': hx(pkts[0][:20]) if pkts else None}
            res['variants'].append(row)
            print('[%s] %3d 包 %6.1fms 发送前红=%d 发送后红=%d %s'
                  % (name, len(pkts), ms, base, red_after,
                     '✅ 生效' if row['works'] else ''))
    finally:
        kb.close()
        json.dump(res, open(os.path.join(ROOT, 'docs', '_p6_variants.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved')


if __name__ == '__main__':
    main()
