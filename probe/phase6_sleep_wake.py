# -*- coding: utf-8 -*-
"""Phase 6：2.4G 休眠/唤醒通知真机捕获

- 先把 sleepTime 设为 1 分钟（官方 UI 选项：1/10/20/30 min，0=关闭）
- 打开 dongle 所有可读 HID 接口，监听所有输入报告
- 识别：`55 FC 06`=休眠、`A6 FF 01`=唤醒、`55 FC 04`=断连、`55 FC 05`=复位、`55 FA xx`=设备通知
用法: python phase6_sleep_wake.py [秒数=420]
输出 docs/phase6_sleep_wake.json
"""
import ctypes
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import _enum_paths, CMD  # noqa: E402
from phase7_keyevents import ReadOnlyHid  # noqa: E402
from phase6_wireless import open_wireless  # noqa: E402

ROOT = os.path.dirname(HERE)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b)


def iface_name(path):
    low = path.lower()
    if 'mi_02&col05' in low:
        return 'MI_02/COL05(0xFFFF)'
    if 'mi_02&col04' in low:
        return 'MI_02/COL04(multi-axis)'
    if 'mi_02&col03' in low:
        return 'MI_02/COL03(kbd)'
    if 'mi_02&col01' in low:
        return 'MI_02/COL01(consumer)'
    if 'mi_02&col02' in low:
        return 'MI_02/COL02(sysctl)'
    if 'mi_03' in low:
        return 'MI_03(0xFF60)'
    if 'mi_04' in low:
        return 'MI_04(0xFF59)'
    if 'mi_01' in low:
        return 'MI_01(mouse)'
    if 'mi_00' in low:
        return 'MI_00(kbd)'
    return path.split('#')[1][:24]


def classify(payload):
    p = bytes(payload)
    if len(p) >= 3 and p[0] == 0x55 and p[1] == 0xFC:
        t = p[2]
        return {4: 'DISCONNECT(0xFC/4)', 5: 'RESET(0xFC/5)',
                6: 'SLEEP(0xFC/6)'}.get(t, 'NOTIFY(0xFC/%d)' % t)
    if len(p) >= 3 and p[0] == 0xA6 and p[1] == 0xFF and p[2] == 0x01:
        return 'WAKE(A6 FF 01)'
    if len(p) >= 3 and p[0] == 0x55 and p[1] == 0xFA:
        return 'DEVICE_NOTIFY(0xFA/type=%d)' % p[2]
    if len(p) >= 3 and p[0] == 0x55 and p[1] == 0xFB:
        return 'CALIB(0xFB)'
    return None


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 420.0
    # 1) 设 sleepTime = 1 分钟
    kb, kind, _ = open_wireless()
    try:
        gm = bytes(kb.get_game_mode()['raw'])
        origin = gm[3]
        raw = bytearray(gm)
        raw[3] = 1
        kb.request(CMD['SET_GAME_MODE'], bytes(raw), content_size=56)
        time.sleep(0.3)
        print('sleepTime: %d -> %d (回读 %d)' %
              (origin, 1, kb.get_game_mode()['sleepTime']), flush=True)
        print('设备在线 (kind=%s)' % kind, flush=True)
    finally:
        kb.close()

    # 2) 打开 dongle 所有可读接口
    readers = []
    for p in _enum_paths():
        low = p.lower()
        if 'vid_0c45' not in low or 'fefe' not in low:
            continue
        try:
            r = ReadOnlyHid(p)
        except OSError:
            continue
        readers.append((iface_name(p), r))
        print('监听接口:', iface_name(p), 'in_len=%d' % r.in_len, flush=True)
    events = []
    t0 = time.time()
    print('开始监听 %.0f 秒（键盘请勿触碰，等它自己休眠）…' % dur, flush=True)
    last_report = time.time()
    try:
        while time.time() - t0 < dur:
            hit = False
            for name, r in readers:
                rep = r.poll()
                if not rep:
                    continue
                hit = True
                payload = rep[1:]
                tag = classify(payload)
                ev = {'t_ms': round((time.time() - t0) * 1000), 'iface': name,
                      'hex': hx(rep), 'tag': tag}
                events.append(ev)
                if tag:
                    print('>>> %6dms %-22s %-22s %s' %
                          (ev['t_ms'], name, tag, hx(payload)), flush=True)
                else:
                    print('    %6dms %-22s %s' % (ev['t_ms'], name, hx(payload)),
                          flush=True)
            if not hit:
                time.sleep(0.003)
    finally:
        for _, r in readers:
            r.close()
        res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'duration': dur,
               'n_events': len(events), 'events': events,
               'sleep_seen': any(e['tag'] and e['tag'].startswith('SLEEP')
                                 for e in events),
               'wake_seen': any(e['tag'] == 'WAKE(A6 FF 01)' for e in events)}
        out = os.path.join(ROOT, 'docs', 'phase6_sleep_wake.json')
        json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('\n监听结束：%d 条上报；SLEEP=%s WAKE=%s' %
              (len(events), res['sleep_seen'], res['wake_seen']), flush=True)
        print('saved', out, flush=True)


if __name__ == '__main__':
    main()
