# -*- coding: utf-8 -*-
"""监听设备主动上报（主协议接口 + TFT 接口），用于抓 0xFA 通知 / 按键唤醒等。

用法: python monitor_notify.py [秒数=60]
输出: 每条回包的时间、接口、hex；同时写 docs/notify_capture.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard  # noqa: E402

ROOT = os.path.dirname(HERE)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b)


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    kb = AjazzKeyboard()
    events = []
    t0 = time.time()
    print('监听 %.0f 秒（主协议 + TFT 两个接口），请开始操作键盘/旋钮…' % dur)
    try:
        # 先清空残留
        for _ in range(20):
            kb.proto.read_report(timeout=0.01)
            if kb.tft:
                kb.tft.read_report(timeout=0.01)
        while time.time() - t0 < dur:
            hit = False
            r = kb.proto.read_report(timeout=0.05)
            if r:
                hit = True
                events.append({'t_ms': round((time.time() - t0) * 1000),
                               'iface': 'PROTO', 'len': len(r),
                               'hex': hx(r[1:33]),
                               'cmd': r[2] if len(r) > 2 else None})
            if kb.tft:
                r2 = kb.tft.read_report(timeout=0.01 if hit else 0.05)
                if r2:
                    events.append({'t_ms': round((time.time() - t0) * 1000),
                                   'iface': 'TFT', 'len': len(r2),
                                   'hex': hx(r2[1:33]),
                                   'cmd': r2[2] if len(r2) > 2 else None})
            for e in events[-3:]:
                pass
    finally:
        kb.close()
        res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'duration': dur,
               'n_events': len(events), 'events': events}
        out = os.path.join(ROOT, 'docs', 'notify_capture.json')
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
        print('\n共 %d 条上报:' % len(events))
        for e in events[:80]:
            print('  %6dms %-5s cmd=%s len=%-3d %s'
                  % (e['t_ms'], e['iface'],
                     ('0x%02X' % e['cmd']) if e['cmd'] is not None else '?',
                     e['len'], e['hex']))
        print('saved', out)


if __name__ == '__main__':
    main()
