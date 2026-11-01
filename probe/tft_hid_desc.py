#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TFT 接口 HID 报告描述符 / report ID 诊断
目标：确认 MI_03（usagePage 0xFF67）的大号 output report 到底用哪个 report ID、
每包数据多长 —— 这决定我们原生写 4105 字节时首字节该填什么。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz as A  # 复用枚举/结构

IOCTL_HID_GET_REPORT_DESCRIPTOR = 0x000B0000
kernel32, hid = A.kernel32, A.hid

DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                            ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
DeviceIoControl.restype = wt.BOOL


# ---- HIDP_VALUE_CAPS（与 probe3.py 相同的 ctypes 布局，x64 下 sizeof 应为 72） ----
class _R(ctypes.Structure):
    _fields_ = [('UsageMin', wt.USHORT), ('UsageMax', wt.USHORT),
                ('StringMin', wt.USHORT), ('StringMax', wt.USHORT),
                ('DesignatorMin', wt.USHORT), ('DesignatorMax', wt.USHORT),
                ('DataIndexMin', wt.USHORT), ('DataIndexMax', wt.USHORT)]


class _NR(ctypes.Structure):
    _fields_ = [('Usage', wt.USHORT), ('Reserved1', wt.USHORT),
                ('StringIndex', wt.USHORT), ('Reserved2', wt.USHORT),
                ('DesignatorIndex', wt.USHORT), ('Reserved3', wt.USHORT),
                ('DataIndex', wt.USHORT), ('Reserved4', wt.USHORT)]


class _U(ctypes.Union):
    _fields_ = [('Range', _R), ('NotRange', _NR)]


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [('UsagePage', wt.USHORT), ('ReportID', ctypes.c_ubyte),
                ('IsAlias', ctypes.c_ubyte), ('BitField', wt.USHORT),
                ('LinkCollection', wt.USHORT), ('LinkUsage', wt.USHORT),
                ('LinkUsagePage', wt.USHORT), ('IsRange', ctypes.c_ubyte),
                ('IsStringRange', ctypes.c_ubyte), ('IsDesignatorRange', ctypes.c_ubyte),
                ('IsAbsolute', ctypes.c_ubyte), ('Reserved', wt.ULONG * 10),
                ('u', _U)]


hid.HidP_GetValueCaps.argtypes = [wt.INT, ctypes.POINTER(HIDP_VALUE_CAPS),
                                  ctypes.POINTER(wt.USHORT), ctypes.c_void_p]
hid.HidP_GetValueCaps.restype = wt.LONG
HIDP_STATUS_SUCCESS = 0x00110000


def open_handle(path, access):
    return kernel32.CreateFileW(path, access, A.FILE_SHARE_READ | A.FILE_SHARE_WRITE,
                                None, A.OPEN_EXISTING, 0, None)


def read_descriptor(path):
    for name, access in (('rw', A.GENERIC_READ | A.GENERIC_WRITE), ('r', A.GENERIC_READ)):
        h = open_handle(path, access)
        if not h or h == A.INVALID_HANDLE_VALUE:
            continue
        buf = ctypes.create_string_buffer(8192)
        got = wt.DWORD(0)
        ok = DeviceIoControl(h, IOCTL_HID_GET_REPORT_DESCRIPTOR, None, 0, buf, 8192,
                             ctypes.byref(got), None)
        err = ctypes.get_last_error()
        kernel32.CloseHandle(h)
        if ok and got.value:
            return buf.raw[:got.value], 0, name
    return None, err, name


def parse_descriptor(d):
    i = 0
    g = {'report_id': 0, 'report_size': 0, 'report_count': 0}
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
            if tag in (8, 9, 11) and g['report_size'] and g['report_count']:
                kind = {8: 'in', 9: 'out', 11: 'feat'}[tag]
                nbytes = (g['report_size'] * g['report_count'] + 7) // 8
                key = (kind, g['report_id'])
                reports[key] = reports.get(key, 0) + nbytes
        elif btype == 1:
            if tag == 7:
                g['report_size'] = val
            elif tag == 8:
                g['report_id'] = val
            elif tag == 9:
                g['report_count'] = val
    return reports


def mi_of(path):
    p = path.lower()
    try:
        return 'MI_' + p.split('mi_')[1][:2]
    except Exception:
        return 'MI_??'


def main():
    print(f'HIDP_VALUE_CAPS sizeof = {ctypes.sizeof(HIDP_VALUE_CAPS)} (x64 期望 72)')
    targets = []
    for path in A._enum_paths():
        h = open_handle(path, A.GENERIC_READ)
        if not h or h == A.INVALID_HANDLE_VALUE:
            continue
        at = A.HIDD_ATTRIBUTES()
        at.Size = ctypes.sizeof(at)
        ok = hid.HidD_GetAttributes(h, ctypes.byref(at))
        if ok and at.VendorID == A.VID and at.ProductID == A.PID:
            pp = ctypes.c_void_p()
            caps = None
            if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                c = A.HIDP_CAPS()
                if hid.HidP_GetCaps(pp, ctypes.byref(c)):
                    caps = c
                hid.HidD_FreePreparsedData(pp)
            targets.append((path, caps))
        kernel32.CloseHandle(h)

    for path, caps in targets:
        if not caps:
            continue
        name = mi_of(path)
        print(f'\n=== {name} uPage=0x{caps.UsagePage:04X} in={caps.InputReportByteLength} '
              f'out={caps.OutputReportByteLength} feat={caps.FeatureReportByteLength}')
        desc, err, mode = read_descriptor(path)
        if desc:
            print(f'  描述符 OK（{mode}）{len(desc)}B: {desc[:200].hex(" ")}')
            rep = parse_descriptor(desc)
            for kind in ('out', 'in', 'feat'):
                for (k, rid), n in sorted(rep.items()):
                    if k == kind:
                        print(f'   {kind:4s} rid={rid:3d} 数据={n}B '
                              f'含ID总长={n + (1 if rid else 0)}B')
        else:
            print(f'  描述符失败 err={err}')

        h = open_handle(path, A.GENERIC_READ)
        pp = ctypes.c_void_p()
        if not h or not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            continue
        try:
            for rtype, tname in ((1, 'out'), (0, 'in'), (2, 'feat')):
                n = wt.USHORT(0)
                hid.HidP_GetValueCaps(rtype, None, ctypes.byref(n), pp)
                if not n.value:
                    continue
                arr = (HIDP_VALUE_CAPS * n.value)()
                st = hid.HidP_GetValueCaps(rtype, arr, ctypes.byref(n), pp)
                if st != HIDP_STATUS_SUCCESS:
                    print(f'   {tname}: GetValueCaps 0x{st & 0xFFFFFFFF:08X}')
                    continue
                for c in arr[:n.value]:
                    print(f'   {tname}: rid={c.ReportID} page=0x{c.UsagePage:04X} '
                          f'bits={c.BitField} cnt={c.ReportCount} '
                          f'bytes={(c.BitField * c.ReportCount + 7) // 8}')
        finally:
            hid.HidD_FreePreparsedData(pp)
            kernel32.CloseHandle(h)


if __name__ == '__main__':
    main()
