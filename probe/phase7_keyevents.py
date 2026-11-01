# -*- coding: utf-8 -*-
"""Phase 7：按键事件捕获（标准 HID 键盘接口 MI_00 / MI_01 COL03）

静态结论：厂商协议没有按键事件帧，官方 /key-test 只是浏览器 DOM 事件。
真机验证替代方案：直接读键盘的 HID 输入报告（MI_00 的 `\\kbd` 集合）。

用法:
  python phase7_keyevents.py [秒数=25]
监听期间请按键（建议：a、b、c、Ctrl+C、Fn+1、方向键、音量旋钮）；
输出 docs/phase7_keyevents.json
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes as wt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import (GENERIC_READ, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
                   FILE_FLAG_OVERLAPPED, INVALID_HANDLE_VALUE, OVERLAPPED,
                   ERROR_IO_PENDING, WAIT_OBJECT_0, _enum_paths, _err,
                   HIDD_ATTRIBUTES, HIDP_CAPS, kernel32, hid)  # noqa: E402

ROOT = os.path.dirname(HERE)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b)


class ReadOnlyHid:
    def __init__(self, path):
        self.path = path
        self.h = kernel32.CreateFileW(path, GENERIC_READ,
                                      FILE_SHARE_READ | FILE_SHARE_WRITE,
                                      None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if not self.h or self.h == INVALID_HANDLE_VALUE:
            raise OSError('open failed err=%d' % _err())
        at = HIDD_ATTRIBUTES()
        at.Size = ctypes.sizeof(at)
        hid.HidD_GetAttributes(self.h, ctypes.byref(at))
        self.vid, self.pid = at.VendorID, at.ProductID
        pp = ctypes.c_void_p()
        self.usage_page = self.usage = 0
        self.in_len = 0
        if hid.HidD_GetPreparsedData(self.h, ctypes.byref(pp)):
            caps = HIDP_CAPS()
            if hid.HidP_GetCaps(pp, ctypes.byref(caps)):
                self.usage_page, self.usage = caps.UsagePage, caps.Usage
                self.in_len = caps.InputReportByteLength
            hid.HidD_FreePreparsedData(pp)
        self.event = kernel32.CreateEventW(None, True, False, None)
        self.ov = OVERLAPPED()
        self.ov.hEvent = self.event
        self.pending = False
        self.buf = ctypes.create_string_buffer(max(64, self.in_len))

    def poll(self):
        """非阻塞读：返回 bytes 或 None"""
        if not self.pending:
            got = wt.DWORD(0)
            ok = kernel32.ReadFile(self.h, ctypes.cast(self.buf, ctypes.c_void_p),
                                   self.in_len, ctypes.byref(got), ctypes.byref(self.ov))
            if ok:
                self.pending = False
                return self.buf.raw[:got.value]
            if _err() != ERROR_IO_PENDING:
                self.pending = False
                return None
            self.pending = True
            return None
        if kernel32.WaitForSingleObject(self.event, 0) != WAIT_OBJECT_0:
            return None
        got = wt.DWORD(0)
        ok = kernel32.GetOverlappedResult(self.h, ctypes.byref(self.ov),
                                          ctypes.byref(got), False)
        kernel32.ResetEvent(self.event)
        self.pending = False
        if not ok or got.value == 0:
            return None
        return self.buf.raw[:got.value]

    def close(self):
        try:
            if self.pending:
                kernel32.CancelIoEx(self.h, ctypes.byref(self.ov))
            kernel32.CloseHandle(self.h)
            kernel32.CloseHandle(self.event)
        except Exception:  # noqa: BLE001
            pass


def find_kbd_paths():
    out = []
    for p in _enum_paths():
        low = p.lower()
        if 'vid_0c45' in low and 'pid_8047' in low and low.endswith('\\kbd'):
            out.append(p)
    return out


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    paths = find_kbd_paths()
    print('找到键盘 HID 接口 %d 个:' % len(paths))
    readers = []
    for p in paths:
        try:
            r = ReadOnlyHid(p)
            readers.append(r)
            print('  %s usagePage=0x%04X usage=0x%04X in_len=%d'
                  % (p.split('#')[1], r.usage_page, r.usage, r.in_len))
        except OSError as e:
            print('  打不开:', p.split('#')[1], e)
    events = []
    t0 = time.time()
    print('\n监听 %.0f 秒，请开始按键…' % dur)
    try:
        while time.time() - t0 < dur:
            hit = False
            for r in readers:
                rep = r.poll()
                if rep:
                    hit = True
                    events.append({'t_ms': round((time.time() - t0) * 1000),
                                   'iface': r.path.split('#')[1].split('&mi_')[1][:2] +
                                   ('-kbd' if '\\kbd' in r.path else ''),
                                   'len': len(rep), 'hex': hx(rep)})
            if not hit:
                time.sleep(0.002)
    finally:
        for r in readers:
            r.close()
        res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'duration': dur,
               'n_events': len(events), 'events': events,
               'ifaces': [{'path': p.split('#')[1],
                           'usage': '0x%04X/0x%04X' % (r.usage_page, r.usage),
                           'in_len': r.in_len}
                          for p, r in zip(paths, readers)]}
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase7_keyevents.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('\n共 %d 条输入报告' % len(events))
        for e in events[:60]:
            print('  %6dms %-6s len=%-3d %s' % (e['t_ms'], e['iface'], e['len'], e['hex']))
        print('saved docs/phase7_keyevents.json')


if __name__ == '__main__':
    main()
