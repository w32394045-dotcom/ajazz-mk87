#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尝试多组 IOCTL 常量读取 MI_03 的 HID 报告描述符，并打印/解析 report ID 与报告长度。"""
import ctypes
import ctypes.wintypes as wt
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz as A

kernel32, hid = A.kernel32, A.hid
DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                            ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
DeviceIoControl.restype = wt.BOOL

CANDIDATES = [0x000B0000, 0x000B0001, 0x000B0002, 0x000B0003, 0x000B0004,
              0x000B0007, 0x000B000B]


def parse(d):
    i = 0
    g = {'rid': 0, 'rs': 0, 'rc': 0}
    reports = {}
    while i < len(d):
        b = d[i]
        size = {0: 0, 1: 1, 2: 2, 3: 4}[b & 3]
        btype = (b >> 2) & 3
        tag = (b >> 4) & 0x0F
        data = d[i + 1:i + 1 + size]
        i += 1 + size
        val = 0
        for k, x in enumerate(data):
            val |= x << (8 * k)
        if btype == 0:
            if tag in (8, 9, 11) and g['rs'] and g['rc']:
                kind = {8: 'in', 9: 'out', 11: 'feat'}[tag]
                nbytes = (g['rs'] * g['rc'] + 7) // 8
                reports[(kind, g['rid'])] = reports.get((kind, g['rid']), 0) + nbytes
        elif btype == 1:
            if tag == 7:
                g['rs'] = val
            elif tag == 8:
                g['rid'] = val
            elif tag == 9:
                g['rc'] = val
    return reports


def main():
    for path in A._enum_paths():
        h = kernel32.CreateFileW(path, A.GENERIC_READ | A.GENERIC_WRITE,
                                 A.FILE_SHARE_READ | A.FILE_SHARE_WRITE, None,
                                 A.OPEN_EXISTING, 0, None)
        if not h or h == A.INVALID_HANDLE_VALUE:
            h = kernel32.CreateFileW(path, A.GENERIC_READ,
                                     A.FILE_SHARE_READ | A.FILE_SHARE_WRITE, None,
                                     A.OPEN_EXISTING, 0, None)
        if not h or h == A.INVALID_HANDLE_VALUE:
            continue
        at = A.HIDD_ATTRIBUTES()
        at.Size = ctypes.sizeof(at)
        ok = hid.HidD_GetAttributes(h, ctypes.byref(at))
        if not (ok and at.VendorID == A.VID and at.ProductID == A.PID):
            kernel32.CloseHandle(h)
            continue
        pp = ctypes.c_void_p()
        caps = None
        if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            c = A.HIDP_CAPS()
            if hid.HidP_GetCaps(pp, ctypes.byref(c)):
                caps = c
            hid.HidD_FreePreparsedData(pp)
        if not caps or caps.UsagePage not in (0xFF67, 0xFF68):
            kernel32.CloseHandle(h)
            continue
        p_low = path.lower()
        mi = 'MI_' + p_low.split('mi_')[1][:2] if 'mi_' in p_low else '?'
        print(f'\n=== {mi} out={caps.OutputReportByteLength} in={caps.InputReportByteLength} '
              f'feat={caps.FeatureReportByteLength}')
        for code in CANDIDATES:
            buf = ctypes.create_string_buffer(8192)
            got = wt.DWORD(0)
            ok = DeviceIoControl(h, code, None, 0, buf, 8192, ctypes.byref(got), None)
            err = ctypes.get_last_error()
            if ok and got.value:
                print(f'  IOCTL 0x{code:08X}: OK, {got.value} 字节')
                data = buf.raw[:got.value]
                print('  descriptor:', data[:260].hex(' '))
                for (kind, rid), n in sorted(parse(data).items()):
                    print(f'    {kind:4s} reportId={rid:3d} 数据={n}B '
                          f'(含 report ID 总长={n + (1 if rid else 0)})')
                break
            else:
                print(f'  IOCTL 0x{code:08X}: fail err={err}')
        kernel32.CloseHandle(h)


if __name__ == '__main__':
    main()
