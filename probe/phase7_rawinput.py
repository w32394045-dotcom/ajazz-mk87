# -*- coding: utf-8 -*-
"""Phase 7b：RawInput 按键事件捕获（HID 键盘接口被系统独占，直接读 \kbd 会 ACCESS_DENIED）

用 RegisterRawInputDevices + 隐藏窗口 + WM_INPUT 拿原始键盘报告：
  - 设备路径/VID/PID
  - HID usagePage/usage
  - VKey / MakeCode / Flags / Message
  - HID 原始报告字节（bRawData）
用法: python phase7_rawinput.py [秒数=30]
输出 docs/phase7_rawinput.json
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes as wt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOT = os.path.dirname(HERE)
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WM_INPUT = 0x00FF
WM_DESTROY = 0x0002
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RIM_TYPEKEYBOARD = 1
RIM_TYPEHID = 2


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [('usUsagePage', wt.USHORT), ('usUsage', wt.USHORT),
                ('dwFlags', wt.DWORD), ('hwndTarget', wt.HWND)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [('hDevice', wt.HANDLE), ('dwType', wt.DWORD)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [('dwType', wt.DWORD), ('dwSize', wt.DWORD),
                ('hDevice', wt.HANDLE), ('wParam', wt.WPARAM)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [('MakeCode', wt.USHORT), ('Flags', wt.USHORT),
                ('Reserved', wt.USHORT), ('VKey', wt.USHORT),
                ('Message', wt.UINT), ('ExtraInformation', wt.ULONG)]


class RAWHID(ctypes.Structure):
    _fields_ = [('dwSizeHid', wt.DWORD), ('dwCount', wt.DWORD),
                ('bRawData', ctypes.c_ubyte * 1)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [('header', RAWINPUTHEADER), ('keyboard', RAWKEYBOARD)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CreateWindowExW.restype = wt.HWND
user32.RegisterClassW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE,
                                   wt.LPVOID]
user32.GetRawInputData.restype = wt.UINT
user32.GetMessageW.restype = wt.BOOL
user32.PeekMessageW.restype = wt.BOOL


def hx(b):
    return ' '.join(f'{x:02X}' for x in b)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC),
                ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON),
                ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH),
                ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR)]


def wndproc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def get_device_name(hdevice):
    size = wt.UINT(0)
    user32.GetRawInputDeviceInfoW(hdevice, 0x20000007, None, ctypes.byref(size))  # RIDI_DEVICENAME
    if not size.value:
        return ''
    buf = ctypes.create_unicode_buffer(size.value)
    user32.GetRawInputDeviceInfoW(hdevice, 0x20000007, buf, ctypes.byref(size))
    return buf.value


def parse_raw(lparam, events):
    size = wt.UINT(0)
    user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size),
                           ctypes.sizeof(RAWINPUTHEADER))
    if not size.value:
        return
    buf = ctypes.create_string_buffer(size.value)
    n = user32.GetRawInputData(lparam, RID_INPUT, buf, ctypes.byref(size),
                               ctypes.sizeof(RAWINPUTHEADER))
    if n == 0xFFFFFFFF:
        return
    hdr = RAWINPUTHEADER.from_buffer_copy(buf.raw[:ctypes.sizeof(RAWINPUTHEADER)])
    rec = {'device': get_device_name(hdr.hDevice)}
    if hdr.dwType == RIM_TYPEKEYBOARD:
        kb = RAWKEYBOARD.from_buffer_copy(
            buf.raw[ctypes.sizeof(RAWINPUTHEADER):
                    ctypes.sizeof(RAWINPUTHEADER) + ctypes.sizeof(RAWKEYBOARD)])
        rec.update({'type': 'keyboard', 'vkey': kb.VKey, 'make': kb.MakeCode,
                    'flags': kb.Flags, 'msg': kb.Message,
                    'extra': kb.ExtraInformation})
    elif hdr.dwType == RIM_TYPEHID:
        off = ctypes.sizeof(RAWINPUTHEADER)
        size_hid, count = ctypes.c_uint32.from_buffer_copy(buf.raw[off:off + 4]), \
            ctypes.c_uint32.from_buffer_copy(buf.raw[off + 4:off + 8])
        data = buf.raw[off + 8:off + 8 + size_hid.value]
        rec.update({'type': 'hid', 'size_hid': size_hid.value,
                    'count': count.value, 'hex': hx(data)})
    else:
        rec.update({'type': 'other(%d)' % hdr.dwType})
    events.append(rec)


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = WNDPROC(wndproc)
    wc.hInstance = hinst
    wc.lpszClassName = 'ajazz_rawinput'
    atom = user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, 'ajazz_rawinput', 'ajazz', 0, 0, 0, 0, 0,
                                  None, None, hinst, None)
    if not hwnd:
        raise OSError('CreateWindow failed %d' % ctypes.get_last_error())

    devs = (RAWINPUTDEVICE * 2)()
    devs[0].usUsagePage, devs[0].usUsage = 0x01, 0x06      # keyboard
    devs[0].dwFlags, devs[0].hwndTarget = RIDEV_INPUTSINK, hwnd
    devs[1].usUsagePage, devs[1].usUsage = 0x0C, 0x01      # consumer control
    devs[1].dwFlags, devs[1].hwndTarget = RIDEV_INPUTSINK, hwnd
    ok = user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE))
    if not ok:
        raise OSError('RegisterRawInputDevices failed %d' % ctypes.get_last_error())

    print('RawInput 已注册（键盘 + 消费键），监听 %.0f 秒，请按键…' % dur)
    events = []
    t0 = time.time()
    msg = wt.MSG()
    try:
        while time.time() - t0 < dur:
            got = False
            while user32.PeekMessageW(ctypes.byref(msg), hwnd, 0, 0, 0x0001):  # PM_REMOVE
                got = True
                if msg.message == WM_INPUT:
                    parse_raw(msg.lParam, events)
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if not got:
                time.sleep(0.002)
    finally:
        res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'duration': dur,
               'n_events': len(events), 'events': events}
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase7_rawinput.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('共 %d 条事件:' % len(events))
        for e in events[:80]:
            if e.get('type') == 'keyboard':
                print('  vkey=0x%02X make=0x%02X flags=0x%04X msg=0x%04X dev=%s'
                      % (e['vkey'], e['make'], e['flags'], e['msg'],
                         e['device'].split('#')[1] if '#' in e['device'] else e['device'][:40]))
            elif e.get('type') == 'hid':
                print('  HID  len=%d count=%d %s  dev=%s'
                      % (e['size_hid'], e['count'], e['hex'],
                         e['device'].split('#')[1] if '#' in e['device'] else e['device'][:40]))
        print('saved docs/phase7_rawinput.json')


if __name__ == '__main__':
    main()
