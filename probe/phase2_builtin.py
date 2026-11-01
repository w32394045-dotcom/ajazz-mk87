# -*- coding: utf-8 -*-
"""Phase 2 补充：SET_TFT_BUILT_IN_INDEX(0x51) 真机测试

官方网页驱动对 MK87 **从不发** 0x51（tftConfig.builtInCount 缺失），静态无法知道
设备是否支持。这里直接在 TFT 接口上按官方 NX() 报文格式发索引 0..5，看屏幕是否切页、
设备是否有回包。用法: python phase2_builtin.py [0 1 2 3 4 5]
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
    return ' '.join(f'{x:02X}' for x in b) if b else ''


def main():
    idxs = [int(x) for x in sys.argv[1:]] or [0, 1, 2, 3, 4, 5]
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'test': '0x51 built-in index',
           'sends': []}
    try:
        tft = kb.tft
        print('TFT iface:', tft.out_len)
        for idx in idxs:
            pkt = bytearray([0]) + bytearray(tft.out_len - 1)
            pkt[1:9] = bytes([0xAA, CMD['SET_TFT_BUILT_IN_INDEX'], 1, 0, 0, 0, 1, 0])
            pkt[9] = idx & 0xFF
            t0 = time.time()
            tft.write_report(bytes(pkt))
            wms = round((time.time() - t0) * 1000, 1)
            # 抓 300ms 回包
            got = []
            t1 = time.time()
            while time.time() - t1 < 0.3:
                r = tft.read_report(timeout=0.05)
                if r:
                    got.append(hx(r[1:17]))
                r2 = kb.proto.read_report(timeout=0.02)
                if r2:
                    got.append('PROTO ' + hx(r2[1:17]))
            row = {'index': idx, 'write_ms': wms, 'reports': got}
            res['sends'].append(row)
            print('  idx=%d 写 %5.1fms 回包: %s' % (idx, wms, got[:2]))
            time.sleep(1.0)
        print('\n>>> 索引 0..%d 已依次发送，请观察屏幕是否切页 <<<' % idxs[-1])
    finally:
        kb.close()
        out = os.path.join(ROOT, 'docs', 'phase2_tft.json')
        old = {'runs': []}
        if os.path.exists(out):
            try:
                old = json.load(open(out, encoding='utf-8'))
            except Exception:  # noqa: BLE001
                pass
        runs = old.get('runs', []) if isinstance(old, dict) else old
        runs.append(res)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'runs': runs}, f, ensure_ascii=False, indent=2)
        print('saved', out)


if __name__ == '__main__':
    main()
