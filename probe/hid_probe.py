#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJAZZ MK87 (VID 0x0C45 / PID 0x8047) HID 探针 v2
- 纯 ctypes 调 setupapi.dll / hid.dll，无需第三方包
- 枚举 HID 接口（usagePage/usage/报告长度/产品名）
- 写句柄与读句柄分开：写用同步 WriteFile，读用 OVERLAPPED 句柄
- 对每个可写接口发送 GET_DEVICE_INFO (0x10) 帧，打印收到的 input report
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

VID = 0x0C45
PID = 0x8047

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
ERROR_IO_PENDING = 997
ERROR_NO_MORE_ITEMS = 259
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
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
    _fields_ = [
        ('Usage', wt.USHORT), ('UsagePage', wt.USHORT),
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
        ('NumberFeatureDataIndices', wt.USHORT),
    ]


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
hid.HidD_GetManufacturerString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetManufacturerString.restype = wt.BOOL

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
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.WaitForSingleObject.restype = wt.DWORD
kernel32.ResetEvent.argtypes = [wt.HANDLE]
kernel32.ResetEvent.restype = wt.BOOL
kernel32.GetOverlappedResult.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wt.DWORD), wt.BOOL]
kernel32.GetOverlappedResult.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.CancelIoEx.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.CancelIoEx.restype = wt.BOOL


def P(*a):
    print(*a, flush=True)


def open_handle(path, access, overlapped=False):
    flags = FILE_FLAG_OVERLAPPED if overlapped else 0
    h = kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             None, OPEN_EXISTING, flags, None)
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


def get_string(fn, h):
    buf = ctypes.create_unicode_buffer(256)
    if fn(h, ctypes.cast(buf, ctypes.c_void_p), ctypes.sizeof(buf)):
        return buf.value
    return ''


def enumerate_hid():
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devs = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                         DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if not devs:
        return []
    out, idx = [], 0
    while True:
        did = SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(did)
        if not setupapi.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(guid), idx,
                                                    ctypes.byref(did)):
            break
        idx += 1
        required = wt.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(did), None, 0,
                                                  ctypes.byref(required), None)
        if not required.value:
            continue
        buf = ctypes.create_string_buffer(required.value)
        ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(did), buf,
                                                         required.value,
                                                         ctypes.byref(required), None):
            continue
        path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
        if not path.startswith('\\\\?\\'):
            path = ctypes.wstring_at(ctypes.addressof(buf) + 8)
        rd, rerr = open_handle(path, GENERIC_READ)
        wr, werr = open_handle(path, GENERIC_WRITE)
        entry = {'path': path, 'rerr': rerr, 'werr': werr, 'attrs': None,
                 'caps': None, 'product': '', 'manufacturer': ''}
        hl = rd if rd else wr
        if hl:
            at = HIDD_ATTRIBUTES()
            at.Size = ctypes.sizeof(at)
            if hid.HidD_GetAttributes(hl, ctypes.byref(at)):
                entry['attrs'] = {'vid': at.VendorID, 'pid': at.ProductID,
                                  'ver': at.VersionNumber}
            entry['caps'] = get_caps(hl)
            entry['product'] = get_string(hid.HidD_GetProductString, hl)
            entry['manufacturer'] = get_string(hid.HidD_GetManufacturerString, hl)
        if rd:
            kernel32.CloseHandle(rd)
        if wr:
            kernel32.CloseHandle(wr)
        out.append(entry)
    setupapi.SetupDiDestroyDeviceInfoList(devs)
    return out


def mi_from_path(path):
    p = path.lower()
    if 'mi_' in p:
        try:
            return 'MI_' + p.split('mi_')[1][:2]
        except Exception:
            pass
    return 'MI_??'


def hexs(b, n=64):
    return ' '.join(f'{x:02X}' for x in b[:n]) + (' ...' if len(b) > n else '')


def make_get_device_info_packets(out_len):
    content = 48          # 官方 getDeviceInfo contentSize
    chunk = out_len - 8
    if chunk <= 0:
        return []
    count = (content + chunk - 1) // chunk
    pkts = []
    for i in range(count):
        addr = i * chunk
        w = min(content - i * chunk, chunk)
        pkt = bytearray(out_len)
        pkt[0] = 0xAA
        pkt[1] = 0x10
        pkt[2] = w & 0xFF
        pkt[3] = addr & 0xFF
        pkt[4] = (addr >> 8) & 0xFF
        pkt[6] = 1 if i == count - 1 else 0
        pkts.append(bytes(pkt))
    return pkts


def write_packets(wr_handle, packets):
    for idx, pkt in enumerate(packets):
        written = wt.DWORD(0)
        cbuf = ctypes.create_string_buffer(pkt, len(pkt))
        ok = kernel32.WriteFile(wr_handle, ctypes.cast(cbuf, ctypes.c_void_p), len(pkt),
                                ctypes.byref(written), None)
        err = ctypes.get_last_error()
        P(f'    send#{idx} len={len(pkt)} ok={bool(ok)} written={written.value} err={err}')
        if not ok:
            return False
        time.sleep(0.01)
    return True


def read_reports(rd_handle, in_len, duration_ms=1500):
    evt = kernel32.CreateEventW(None, True, False, None)
    if not evt:
        P('    CreateEvent failed')
        return []
    reports = []
    deadline = time.time() + duration_ms / 1000.0
    while time.time() < deadline:
        rbuf = ctypes.create_string_buffer(in_len)
        ov = OVERLAPPED()
        ov.hEvent = evt
        got = wt.DWORD(0)
        ok = kernel32.ReadFile(rd_handle, ctypes.cast(rbuf, ctypes.c_void_p), in_len,
                               ctypes.byref(got), ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                P(f'    read failed err={err}')
                break
            wait = kernel32.WaitForSingleObject(evt, 200)
            if wait != WAIT_OBJECT_0:
                kernel32.CancelIoEx(rd_handle, ctypes.byref(ov))
                time.sleep(0.02)
                continue
            if not kernel32.GetOverlappedResult(rd_handle, ctypes.byref(ov),
                                                ctypes.byref(got), False):
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
    P(f'== AJAZZ HID probe v2  VID={VID:#06x} PID={PID:#06x} ==')
    devs = enumerate_hid()
    mine = [d for d in devs if d['attrs'] and d['attrs']['vid'] == VID and d['attrs']['pid'] == PID]
    P(f'total HID interfaces={len(devs)}  matching={len(mine)}\n')
    for d in mine:
        c = d['caps']
        desc = 'no-caps' if not c else (f'uPage=0x{c.UsagePage:04X} usage=0x{c.Usage:04X} '
                                       f'in={c.InputReportByteLength} out={c.OutputReportByteLength} '
                                       f'feat={c.FeatureReportByteLength}')
        P(f"[{mi_from_path(d['path'])}] {desc}")
        P(f"    product={d['product']!r} manufacturer={d['manufacturer']!r} "
          f"ver={d['attrs']['ver']:#06x} rerr={d['rerr']} werr={d['werr']}")
        P(f"    path={d['path']}")
    P()
    targets = [d for d in mine if d['caps'] and d['caps'].OutputReportByteLength
               and d['caps'].InputReportByteLength]
    if not targets:
        P('没有可读写接口')
        return
    for d in targets:
        c = d['caps']
        P(f"===== probe {mi_from_path(d['path'])} uPage=0x{c.UsagePage:04X} "
          f"usage=0x{c.Usage:04X} out={c.OutputReportByteLength} in={c.InputReportByteLength} =====")
        wr, werr = open_handle(d['path'], GENERIC_WRITE)
        rd, rerr = open_handle(d['path'], GENERIC_READ, overlapped=True)
        if not wr or not rd:
            P(f'  open wr_err={werr} rd_err={rerr}')
            if wr:
                kernel32.CloseHandle(wr)
            if rd:
                kernel32.CloseHandle(rd)
            continue
        packets = make_get_device_info_packets(c.OutputReportByteLength)
        ok = write_packets(wr, packets)
        if ok:
            read_reports(rd, c.InputReportByteLength, 1200)
        kernel32.CloseHandle(wr)
        kernel32.CloseHandle(rd)
        P()


if __name__ == '__main__':
    main()
