#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJAZZ MK87 HID 探针 v3.1
用 HidP_GetValueCaps 拿到每个 report ID 及其报文长度（不依赖报告描述符 IOCTL），
然后按正确 report ID 发送 GET_DEVICE_INFO (0x10) 并读取响应。
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
WAIT_OBJECT_0 = 0
HIDP_STATUS_SUCCESS = 0x00110000
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


class _VC_RANGE(ctypes.Structure):
    _fields_ = [('UsageMin', wt.USHORT), ('UsageMax', wt.USHORT),
                ('StringMin', wt.USHORT), ('StringMax', wt.USHORT),
                ('DesignatorMin', wt.USHORT), ('DesignatorMax', wt.USHORT),
                ('DataIndexMin', wt.USHORT), ('DataIndexMax', wt.USHORT)]


class _VC_NOTRANGE(ctypes.Structure):
    _fields_ = [('Usage', wt.USHORT), ('Reserved1', wt.USHORT),
                ('StringIndex', wt.USHORT), ('Reserved2', wt.USHORT),
                ('DesignatorIndex', wt.USHORT), ('Reserved3', wt.USHORT),
                ('DataIndex', wt.USHORT), ('Reserved4', wt.USHORT)]


class _VC_U(ctypes.Union):
    _fields_ = [('Range', _VC_RANGE), ('NotRange', _VC_NOTRANGE)]


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [('UsagePage', wt.USHORT), ('ReportID', ctypes.c_ubyte),
                ('IsAlias', ctypes.c_ubyte), ('BitField', wt.USHORT),
                ('LinkCollection', wt.USHORT), ('LinkUsage', wt.USHORT),
                ('LinkUsagePage', wt.USHORT), ('IsRange', ctypes.c_ubyte),
                ('IsStringRange', ctypes.c_ubyte), ('IsDesignatorRange', ctypes.c_ubyte),
                ('IsAbsolute', ctypes.c_ubyte), ('Reserved', wt.ULONG * 10),
                ('u', _VC_U)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_void_p), ('InternalHigh', ctypes.c_void_p),
                ('Offset', wt.DWORD), ('OffsetHigh', wt.DWORD), ('hEvent', wt.HANDLE)]


hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wt.BOOL
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = wt.LONG
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_GetProductString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetProductString.restype = wt.BOOL
hid.HidP_GetValueCaps.argtypes = [wt.INT, ctypes.POINTER(HIDP_VALUE_CAPS),
                                  ctypes.POINTER(wt.USHORT), ctypes.c_void_p]
hid.HidP_GetValueCaps.restype = wt.LONG

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

kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                               ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wt.BOOL
kernel32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                              ctypes.POINTER(wt.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.ReadFile.restype = wt.BOOL
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


def get_caps(h):
    pp = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
        return None, None
    caps = HIDP_CAPS()
    ok = hid.HidP_GetCaps(pp, ctypes.byref(caps))
    return (caps if ok else None), pp


def value_caps(pp, report_type):
    """report_type: 0=input 1=output 2=feature"""
    n = wt.USHORT(0)
    st = hid.HidP_GetValueCaps(report_type, None, ctypes.byref(n), pp)
    if not n.value:
        return []
    arr = (HIDP_VALUE_CAPS * n.value)()
    st = hid.HidP_GetValueCaps(report_type, arr, ctypes.byref(n), pp)
    if st != HIDP_STATUS_SUCCESS:
        P(f'    GetValueCaps({report_type}) status=0x{st & 0xFFFFFFFF:08X}')
        return []
    return list(arr[:n.value])


def summarize(report_type, vcaps):
    sizes = {}
    for c in vcaps:
        rid = c.ReportID
        bits = c.BitField
        byte_len = ((bits + 7) // 8) * 1
        sizes[rid] = sizes.get(rid, 0) + byte_len
    return sizes


def hexs(b, n=96):
    return ' '.join(f'{x:02X}' for x in b[:n]) + (' ...' if len(b) > n else '')


def read_loop(rd, in_len, duration_ms=1600, tag=''):
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
            P(f'    [{tag}] recv len={got.value}: {hexs(data)}')
        kernel32.ResetEvent(evt)
    kernel32.CloseHandle(evt)
    return reports


def build_pkt(total_bytes, rid, cmd, payload_len, addr=0, last=0, data=b''):
    body = bytearray(total_bytes - 1)
    body[0] = 0xAA
    body[1] = cmd
    body[2] = payload_len & 0xFF
    body[3] = addr & 0xFF
    body[4] = (addr >> 8) & 0xFF
    body[6] = last
    for k, x in enumerate(data):
        body[8 + k] = x
    return bytes([rid]) + bytes(body)


def main():
    P('== AJAZZ HID probe v3.1 (HidP_GetValueCaps) ==')
    paths = enumerate_hid()
    targets = []
    for path in paths:
        h, err = open_handle(path, GENERIC_READ)
        if not h:
            continue
        at = HIDD_ATTRIBUTES()
        at.Size = ctypes.sizeof(at)
        if hid.HidD_GetAttributes(h, ctypes.byref(at)) and at.VendorID == VID and at.ProductID == PID:
            caps, pp = get_caps(h)
            prod = ctypes.create_unicode_buffer(256)
            hid.HidD_GetProductString(h, ctypes.cast(prod, ctypes.c_void_p), ctypes.sizeof(prod))
            if caps:
                targets.append({'path': path, 'caps': caps, 'pp': pp, 'product': prod.value})
            else:
                kernel32.CloseHandle(h)
        else:
            kernel32.CloseHandle(h)

    for t in targets:
        c = t['caps']
        name = t['path'].split('#')[1].upper()
        P(f"\n===== {name} uPage=0x{c.UsagePage:04X} u=0x{c.Usage:04X} in={c.InputReportByteLength} out={c.OutputReportByteLength} feat={c.FeatureReportByteLength} product={t['product']!r}")
        ocaps = value_caps(t['pp'], 1)
        icaps = value_caps(t['pp'], 0)
        fcaps = value_caps(t['pp'], 2)
        osum = summarize(1, ocaps)
        isum = summarize(0, icaps)
        P(f'  output report ids -> body bytes: {osum}')
        P(f'  input  report ids -> body bytes: {isum}')
        for x in ocaps[:6]:
            P(f'    out cap rid={x.ReportID} page=0x{x.UsagePage:04X} bits={x.BitField} range={bool(x.IsRange)}')
        for x in icaps[:6]:
            P(f'    in  cap rid={x.ReportID} page=0x{x.UsagePage:04X} bits={x.BitField} range={bool(x.IsRange)}')

        out_len = c.OutputReportByteLength
        if not out_len or not osum:
            continue
        rid = sorted(osum.keys())[0]
        body = osum[rid]
        P(f'  --> 选 report ID {rid}, body={body} bytes, 总写长={out_len}')
        wr, werr = open_handle(t['path'], GENERIC_WRITE)
        rd, rderr = open_handle(t['path'], GENERIC_READ, overlapped=True)
        if not wr or not rd:
            P(f'  open wr={werr} rd={rderr}')
            if wr:
                kernel32.CloseHandle(wr)
            if rd:
                kernel32.CloseHandle(rd)
            continue
        chunk = body - 8
        total = 48
        n = max(1, (total + chunk - 1) // chunk)
        packets = []
        for k in range(n):
            addr = k * chunk
            w = min(total - k * chunk, chunk)
            packets.append(build_pkt(out_len, rid, 0x10, w, addr, 1 if k == n - 1 else 0))
        for k, pkt in enumerate(packets):
            written = wt.DWORD(0)
            buf = ctypes.create_string_buffer(pkt, len(pkt))
            ok = kernel32.WriteFile(wr, ctypes.cast(buf, ctypes.c_void_p), len(pkt),
                                    ctypes.byref(written), None)
            P(f'    send#{k} ok={bool(ok)} written={written.value} err={ctypes.get_last_error()}')
            time.sleep(0.01)
        read_loop(rd, c.InputReportByteLength, 1600, name)
        kernel32.CloseHandle(wr)
        kernel32.CloseHandle(rd)
        hid.HidD_FreePreparsedData(t['pp'])
        t['pp'] = None

    for t in targets:
        if t['pp']:
            hid.HidD_FreePreparsedData(t['pp'])


if __name__ == '__main__':
    main()
