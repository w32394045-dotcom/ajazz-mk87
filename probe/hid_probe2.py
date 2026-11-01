#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJAZZ MK87 HID 探针 v3 —— 读取 HID 报告描述符，确定 report ID / 报告长度，
然后用正确的 report ID 发送 GET_DEVICE_INFO (0x10)，读取响应。
"""
import ctypes
import ctypes.wintypes as wt
import time
import sys

VID = 0x0C45
PID = 0x8047
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
ERROR_IO_PENDING = 997
IOCTL_HID_GET_REPORT_DESCRIPTOR = 0x000B0000
WAIT_OBJECT_0 = 0
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

hid = ctypes.WinDLL('hid.dll', use_last_error=True)
setupapi = ctypes.WinDLL('setupapi.dll', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32.dll', use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [('Data1', wt.DWORD), ('Data2', wt.WORD), ('Data3', wt.WORD),
                ('Data4', ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('InterfaceClassGuid', GUID),
                ('Flags', wt.DWORD), ('Reserved', ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('Size', wt.DWORD), ('VendorID', wt.WORD),
                ('ProductID', wt.WORD), ('VersionNumber', wt.WORD)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [('Usage', wt.USHORT), ('UsagePage', wt.USHORT),
                ('InputReportByteLength', wt.USHORT),
                ('OutputReportByteLength', wt.USHORT),
                ('FeatureReportByteLength', wt.USHORT),
                ('Reserved', wt.USHORT * 17),
                ('NumberLinkCollectionNodes', wt.USHORT),
                ('NumberInputButtonCaps', wt.USHORT),
                ('NumberInputValueCaps', wt.USHORT),
                ('NumberInputDataIndices', wt.USHORT),
                ('NumberOutputButtonCaps', wt.USHORT),
                ('NumberOutputValueCaps', wt.USHORT),
                ('NumberOutputDataIndices', wt.USHORT),
                ('NumberFeatureButtonCaps', wt.USHORT),
                ('NumberFeatureValueCaps', wt.USHORT),
                ('NumberFeatureDataIndices', wt.USHORT)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_void_p), ('InternalHigh', ctypes.c_void_p),
                ('Offset', wt.DWORD), ('OffsetHigh', wt.DWORD), ('hEvent', wt.HANDLE)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('ClassGuid', GUID),
                ('DevInst', wt.DWORD), ('Reserved', ctypes.c_void_p)]


hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wt.BOOL
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = wt.LONG
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_GetProductString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetProductString.restype = wt.BOOL

setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), wt.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiEnumDeviceInterfaces.restype = wt.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.restype = wt.BOOL

kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                               ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wt.BOOL
kernel32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                              ctypes.POINTER(wt.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.ReadFile.restype = wt.BOOL
kernel32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                     ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                     ctypes.c_void_p]
kernel32.DeviceIoControl.restype = wt.BOOL
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.WaitForSingleObject.restype = wt.DWORD
kernel32.GetOverlappedResult.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wt.DWORD), wt.BOOL]
kernel32.GetOverlappedResult.restype = wt.BOOL
kernel32.ResetEvent.argtypes = [wt.HANDLE]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CancelIoEx.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.CancelIoEx.restype = wt.BOOL


def P(*a):
    print(*a, flush=True)


def open_handle(path, access, overlapped=False):
    flags = FILE_FLAG_OVERLAPPED if overlapped else 0
    h = kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                             OPEN_EXISTING, flags, None)
    if not h or h == INVALID_HANDLE_VALUE:
        return None, ctypes.get_last_error()
    return h, 0


def get_caps(h):
    pp = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
        return None
    caps = HIDP_CAPS()
    ok = hid.HidP_GetCaps(pp, ctypes.byref(caps))
    hid.HidD_FreePreparsedData(pp)
    return caps if ok else None


def enumerate_hid():
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devs = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                         DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    out, idx = [], 0
    while True:
        did = SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(did)
        if not setupapi.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(guid), idx, ctypes.byref(did)):
            break
        idx += 1
        required = wt.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(did), None, 0, ctypes.byref(required), None)
        if not required.value:
            continue
        buf = ctypes.create_string_buffer(required.value)
        ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(did), buf, required.value, ctypes.byref(required), None):
            continue
        path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
        if not path.startswith('\\\\?\\'):
            path = ctypes.wstring_at(ctypes.addressof(buf) + 8)
        out.append(path)
    setupapi.SetupDiDestroyDeviceInfoList(devs)
    return out


def read_descriptor(path):
    h, err = open_handle(path, GENERIC_READ)
    if not h:
        return None, err
    buf = ctypes.create_string_buffer(8192)
    got = wt.DWORD(0)
    ok = kernel32.DeviceIoControl(h, IOCTL_HID_GET_REPORT_DESCRIPTOR, None, 0, buf,
                                  8192, ctypes.byref(got), None)
    err = ctypes.get_last_error()
    kernel32.CloseHandle(h)
    if not ok:
        return None, err
    return buf.raw[:got.value], 0


def parse_descriptor(d):
    """极简 HID 报告描述符解析，返回 output report ids / usages 摘要"""
    i = 0
    usage_page = 0
    report_id = 0
    report_size = 0
    report_count = 0
    usages = []
    out_reports = []
    in_reports = []
    feat_reports = []
    g = {'report_id': 0, 'report_size': 0, 'report_count': 0, 'usage_page': 0}
    while i < len(d):
        b = d[i]
        size_code = b & 0x03
        size = {0: 0, 1: 1, 2: 2, 3: 4}[size_code]
        btype = (b >> 2) & 0x03
        tag = (b >> 4) & 0x0F
        data = d[i + 1:i + 1 + size]
        i += 1 + size
        val = 0
        for k, x in enumerate(data):
            val |= x << (8 * k)
        if data and data[-1] & 0x80:
            val = val - (1 << (8 * len(data)))
        if btype == 0:
            if tag == 8:  # input
                in_reports.append({'id': g['report_id'], 'size': g['report_size'],
                                   'count': g['report_count'], 'page': g['usage_page'],
                                   'usage': usages[-1] if usages else None})
            elif tag == 9:  # output
                out_reports.append({'id': g['report_id'], 'size': g['report_size'],
                                    'count': g['report_count'], 'page': g['usage_page'],
                                    'usage': usages[-1] if usages else None})
            elif tag == 11:  # feature
                feat_reports.append({'id': g['report_id'], 'size': g['report_size'],
                                     'count': g['report_count'], 'page': g['usage_page']})
            usages = []
        elif btype == 1:
            if tag == 0:
                g['usage_page'] = val & 0xFFFF
            elif tag == 7:
                g['report_size'] = val
            elif tag == 8:
                g['report_id'] = val
            elif tag == 9:
                g['report_count'] = val
        elif btype == 2:
            if tag == 0:
                usages.append({'page': g['usage_page'], 'usage': val & 0xFFFF})
    return {'out': out_reports, 'in': in_reports, 'feat': feat_reports}


def hexs(b, n=80):
    return ' '.join(f'{x:02X}' for x in b[:n]) + (' ...' if len(b) > n else '')


def build_pkt(out_len, rid, cmd, payload_len, addr=0, last=0, data=b''):
    """构建一个包：Windows 写缓冲 = reportID 字节 + (out_len-1) 字节数据"""
    body = bytearray(out_len - 1)
    body[0] = 0xAA
    body[1] = cmd
    body[2] = payload_len & 0xFF
    body[3] = addr & 0xFF
    body[4] = (addr >> 8) & 0xFF
    body[6] = last
    for k, x in enumerate(data):
        body[8 + k] = x
    return bytes([rid]) + bytes(body)


def read_loop(rd, in_len, duration_ms=1500):
    evt = kernel32.CreateEventW(None, True, False, None)
    reports = []
    deadline = time.time() + duration_ms / 1000.0
    while time.time() < deadline:
        rbuf = ctypes.create_string_buffer(in_len)
        ov = OVERLAPPED()
        ov.hEvent = evt
        got = wt.DWORD(0)
        ok = kernel32.ReadFile(rd, ctypes.cast(rbuf, ctypes.c_void_p), in_len,
                               ctypes.byref(got), ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                P(f'    read error {err}')
                break
            if kernel32.WaitForSingleObject(evt, 200) != WAIT_OBJECT_0:
                kernel32.CancelIoEx(rd, ctypes.byref(ov))
                time.sleep(0.01)
                continue
            if not kernel32.GetOverlappedResult(rd, ctypes.byref(ov), ctypes.byref(got), False):
                kernel32.ResetEvent(evt)
                continue
        if got.value:
            data = rbuf.raw[:got.value]
            reports.append(data)
            P(f'    recv len={got.value}: {hexs(data)}')
        kernel32.ResetEvent(evt)
    kernel32.CloseHandle(evt)
    return reports


def main():
    P('== AJAZZ HID probe v3 ==')
    paths = enumerate_hid()
    target = []
    for path in paths:
        rd, err = open_handle(path, GENERIC_READ, overlapped=False)
        if not rd:
            continue
        at = HIDD_ATTRIBUTES()
        at.Size = ctypes.sizeof(at)
        if hid.HidD_GetAttributes(rd, ctypes.byref(at)) and at.VendorID == VID and at.ProductID == PID:
            caps = get_caps(rd)
            prod = ctypes.create_unicode_buffer(256)
            hid.HidD_GetProductString(rd, ctypes.cast(prod, ctypes.c_void_p), ctypes.sizeof(prod))
            target.append({'path': path, 'caps': caps, 'product': prod.value})
        kernel32.CloseHandle(rd)

    for t in target:
        c = t['caps']
        P(f"\n===== {t['path'].split('#')[1].upper()}  uPage=0x{c.UsagePage:04X} u=0x{c.Usage:04X} "
          f"in={c.InputReportByteLength} out={c.OutputReportByteLength} feat={c.FeatureReportByteLength} product={t['product']!r}")
        desc, err = read_descriptor(t['path'])
        if not desc:
            P(f'  读取报告描述符失败 err={err}')
            continue
        P(f'  descriptor {len(desc)} bytes: {hexs(desc, 160)}')
        info = parse_descriptor(desc)
        out_ids = sorted({r["id"] for r in info['out']})
        in_ids = sorted({r["id"] for r in info['in']})
        P(f'  output reports: ids={out_ids}')
        for r in info['out'][:8]:
            P(f'     out id={r["id"]} size={r["size"]} count={r["count"]} page=0x{(r["page"] or 0):04X} usage=0x{(r["usage"] or 0):04X}')
        P(f'  input reports: ids={in_ids}')
        for r in info['in'][:8]:
            P(f'     in  id={r["id"]} size={r["size"]} count={r["count"]} page=0x{(r["page"] or 0):04X}')
        out_len = c.OutputReportByteLength
        rid = out_ids[0] if out_ids else 0
        if not out_len:
            continue
        P(f'  --> 使用 report ID {rid} 发送 GET_DEVICE_INFO(0x10) ...')
        wr, werr = open_handle(t['path'], GENERIC_WRITE)
        rdh, rderr = open_handle(t['path'], GENERIC_READ, overlapped=True)
        if not wr or not rdh:
            P(f'  open wr={werr} rd={rderr}')
            if wr:
                kernel32.CloseHandle(wr)
            if rdh:
                kernel32.CloseHandle(rdh)
            continue
        chunk = out_len - 1 - 8
        if chunk <= 0:
            P('  报告长度不足')
            kernel32.CloseHandle(wr)
            kernel32.CloseHandle(rdh)
            continue
        total = 48
        n = (total + chunk - 1) // chunk
        for k in range(n):
            addr = k * chunk
            w = min(total - k * chunk, chunk)
            pkt = build_pkt(out_len, rid, 0x10, w, addr, 1 if k == n - 1 else 0)
            written = wt.DWORD(0)
            buf = ctypes.create_string_buffer(pkt, len(pkt))
            ok = kernel32.WriteFile(wr, ctypes.cast(buf, ctypes.c_void_p), len(pkt),
                                    ctypes.byref(written), None)
            P(f'    send#{k} ok={bool(ok)} written={written.value} err={ctypes.get_last_error()}')
            time.sleep(0.01)
        read_loop(rdh, c.InputReportByteLength, 1500)
        kernel32.CloseHandle(wr)
        kernel32.CloseHandle(rdh)


if __name__ == '__main__':
    main()
