#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ajazz.py —— AJAZZ MK87 (VID 0x0C45 / PID 0x8047) 原生 HID 协议客户端
协议来自对 ajazz.driveall.cn 官方网页驱动 bundle 的静态还原（见 docs/protocol.md）。

用法:
  python ajazz.py info            # 读设备信息 / 游戏模式 / 灯效
  python ajazz.py raw AA 10 30 00 00 00 00 01   # 发一帧原始数据并打印回包
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time
import struct

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


def _err():
    return ctypes.get_last_error()


# ----------------------------- 命令表（来自官方 bundle HX 枚举） -----------------------------
CMD = {
    'COMMUNICATION_START': 1, 'COMMUNICATION_END': 2,
    'SET_FACTORY_RESET': 15, 'GET_DEVICE_INFO': 16, 'GET_GAME_MODE': 17,
    'GET_KEY': 18, 'GET_LED_EFFECT': 19, 'GET_CUSTOM_LED_DATA': 20,
    'GET_MACRO': 21, 'GET_FN_KEY': 22, 'GET_MAGNETIC_AXIS_RT': 23,
    'GET_MAGNETIC_AXIS_DKS_DATA': 24, 'GET_LIGHT_BOX': 27,
    'GET_DEFAULT_FN_KEY_MATRIX': 28, 'GET_SIDE_LIGHT': 29, 'GET_TRIGGER_KEY': 30,
    'GET_DEFAULT_KEY_MATRIX': 31, 'SET_GAME_MODE': 33, 'SET_KEY': 34,
    'SET_LED_EFFECT': 35, 'SET_CUSTOM_LED_DATA': 36, 'SET_MACRO': 37,
    'SET_FN_KEY': 38, 'SET_MAGNETIC_AXIS_RT': 39, 'SET_MAGNETIC_AXIS_DKS_DATA': 40,
    'SET_DOT_MATRIX_MODE': 42, 'SET_LIGHT_BOX': 43, 'SET_SIDE_LIGHT': 45,
    'SET_TRIGGER_KEY': 46, 'SET_KEYBOARD_CUSTOM_FUNCTION_ON': 48,
    'SET_KEYBOARD_CUSTOM_FUNCTION_OFF': 49, 'GET_LED_DATA': 50,
    'GET_ALL_LIGHTS_RGB': 51, 'SET_TEMPORARY_COMMAND_DATA': 52,
    'SET_MUSIC_DATA': 53, 'CLEAR_LED_DATA': 54, 'GET_ALL_LIGHTS_RGB_24G': 55,
    'GET_ALL_LIGHTS_RGB_24G_64_BYTE': 59, 'SET_MUSIC_DATA_24G_64_BYTE': 60,
    'GET_DOT_MATRIX_CONFIG': 61, 'SET_LED_BOOT_ANIMATION': 64,
    'SET_LED_USER_ANIMATION': 65, 'SET_LED_DATA': 66, 'SET_TFT_MATERIAL': 77,
    'SET_FLASH_DOWNLOAD': 79, 'SET_TFT_USER_ANIMATION': 80,
    'SET_TFT_BUILT_IN_INDEX': 81, 'GET_MAGNETIC_AXIS_KEY_STATUS': 96,
    'SET_CALIBRATION_ON': 100, 'SET_CALIBRATION_OFF': 101,
    'SET_SIMULATION_TEST_ON': 102, 'SET_SIMULATION_TEST_OFF': 103,
    'GET_MAGNETIC_AXIS_STATUS': 104, 'SET_CALIBRATION_ON_V2': 105,
    'SET_CALIBRATION_OFF_V2': 106, 'OTA_GET_DEVICE_SYSTEM_INFO': 128,
    'OTA_VERIFY_FIRMWARE_INFO': 129, 'OTA_DEVICE_ENTER_BOOT': 130,
    'OTA_SEND_FIRMWARE_INFO': 131, 'OTA_GET_DEVICE_SN': 132,
    'OTA_SWITCH_APP_PARTITION': 133, 'OTA_SET_DEVICE_SN': 134, 'SET_PROFILE': 144,
    'GET_DEVICE_NOTIFY': 250, 'GET_MAGNETIC_AXIS_CALIBRATION_DATA': 251,
    'GET_24G_DISCONNECT_NOTIFY': 252,
}
CMD_NAME = {v: k for k, v in CMD.items()}

# TFT 接口的 usagePage（官方 LX() 里写死的 65383 = 0xFF67）
USAGE_PAGE_TFT = 0xFF67
# 主协议接口：实测为 0xFF68 / usage 0x61
USAGE_PAGE_PROTOCOL = 0xFF68


def _enum_paths():
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


class HidInterface:
    def __init__(self, path):
        self.path = path
        self.handle = None
        self.rd = None
        self.event = None
        self.caps = None
        self.product = ''
        self.usage_page = 0
        self.usage = 0
        h = kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                 None, OPEN_EXISTING, 0, None)
        err = ctypes.get_last_error()
        if not h or h == INVALID_HANDLE_VALUE:
            raise OSError(f'open read failed err={err} path={path}')
        self.handle = h
        at = HIDD_ATTRIBUTES()
        at.Size = ctypes.sizeof(at)
        hid.HidD_GetAttributes(h, ctypes.byref(at))
        self.vid, self.pid, self.ver = at.VendorID, at.ProductID, at.VersionNumber
        pp = ctypes.c_void_p()
        if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            caps = HIDP_CAPS()
            if hid.HidP_GetCaps(pp, ctypes.byref(caps)):
                self.caps = caps
                self.usage_page, self.usage = caps.UsagePage, caps.Usage
            hid.HidD_FreePreparsedData(pp)
        prod = ctypes.create_unicode_buffer(256)
        hid.HidD_GetProductString(h, ctypes.cast(prod, ctypes.c_void_p), ctypes.sizeof(prod))
        self.product = prod.value
        # 写句柄
        self.wr = kernel32.CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                       None, OPEN_EXISTING, 0, None)
        err = ctypes.get_last_error()
        if not self.wr or self.wr == INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(h)
            raise OSError(f'open write failed err={err}')
        # 读句柄（OVERLAPPED）
        self.rd = kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                       None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        err = ctypes.get_last_error()
        if not self.rd or self.rd == INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(h)
            kernel32.CloseHandle(self.wr)
            raise OSError(f'open rd failed err={err}')
        self.event = kernel32.CreateEventW(None, True, False, None)
        self.buf = None

    @property
    def mi(self):
        p = self.path.lower()
        try:
            return 'MI_' + p.split('mi_')[1][:2]
        except Exception:
            return 'MI_??'

    @property
    def out_len(self):
        return self.caps.OutputReportByteLength if self.caps else 0

    @property
    def in_len(self):
        return self.caps.InputReportByteLength if self.caps else 0

    def write_report(self, data: bytes):
        """data 长度必须等于 OutputReportByteLength（含 report ID 字节）"""
        if len(data) != self.out_len:
            raise ValueError(f'report len {len(data)} != {self.out_len}')
        written = wt.DWORD(0)
        buf = ctypes.create_string_buffer(data, len(data))
        ok = kernel32.WriteFile(self.wr, ctypes.cast(buf, ctypes.c_void_p), len(data),
                                ctypes.byref(written), None)
        if not ok:
            raise OSError(f'WriteFile failed err={_err()}')
        return written.value

    def read_report(self, timeout=1.0):
        """返回一个 input report（含 report ID 字节），超时返回 None"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            rbuf = ctypes.create_string_buffer(self.in_len)
            ov = OVERLAPPED()
            ov.hEvent = self.event
            got = wt.DWORD(0)
            ok = kernel32.ReadFile(self.rd, ctypes.cast(rbuf, ctypes.c_void_p), self.in_len,
                                   ctypes.byref(got), ctypes.byref(ov))
            if not ok:
                err = _err()
                if err != ERROR_IO_PENDING:
                    raise OSError(f'ReadFile failed err={err}')
                wait_ms = max(10, int((deadline - time.time()) * 1000))
                if kernel32.WaitForSingleObject(self.event, wait_ms) != WAIT_OBJECT_0:
                    kernel32.CancelIoEx(self.rd, ctypes.byref(ov))
                    kernel32.ResetEvent(self.event)
                    return None
                if not kernel32.GetOverlappedResult(self.rd, ctypes.byref(ov),
                                                    ctypes.byref(got), False):
                    kernel32.ResetEvent(self.event)
                    continue
            kernel32.ResetEvent(self.event)
            if got.value:
                return rbuf.raw[:got.value]
        return None

    def drain(self, duration=0.05):
        end = time.time() + duration
        while time.time() < end:
            r = self.read_report(timeout=0.02)
            if not r:
                break

    def close(self):
        for h in (self.rd, self.wr, self.handle):
            if h:
                kernel32.CloseHandle(h)
        if self.event:
            kernel32.CloseHandle(self.event)


class AjazzKeyboard:
    """对 MK87 的协议封装：帧格式 AA cmd len addr(last) + data[8:]，响应 55 cmd ... data[8:]"""

    def __init__(self):
        ifaces = []
        for path in _enum_paths():
            try:
                h = HidInterface(path)
            except OSError:
                continue
            if h.vid == VID and h.pid == PID:
                ifaces.append(h)
            else:
                h.close()
        self.ifaces = ifaces
        self.proto = next((i for i in ifaces if i.usage_page == USAGE_PAGE_PROTOCOL), None)
        self.tft = next((i for i in ifaces if i.usage_page == USAGE_PAGE_TFT), None)
        if self.proto is None:
            # 兜底：取第一条可写且非 TFT 的接口
            cand = [i for i in ifaces if i.out_len > 1 and i.usage_page != USAGE_PAGE_TFT]
            self.proto = cand[0] if cand else None
        if self.proto is None:
            raise RuntimeError('未找到主协议 HID 接口（键盘没连？）')

    def close(self):
        for i in self.ifaces:
            try:
                i.close()
            except Exception:
                pass

    # --------- 帧构造 / 收发 ---------
    def _build_packet(self, iface, cmd, payload_len, addr, data, last, custom_header=None):
        body_len = iface.out_len - 1          # 不含 report ID 字节
        pkt = bytearray(body_len)
        if custom_header:
            pkt[:len(custom_header)] = custom_header
            if data:
                pkt[len(custom_header):len(custom_header) + len(data)] = data
            return bytes([0]) + bytes(pkt)
        pkt[0] = 0xAA
        pkt[1] = cmd & 0xFF
        pkt[2] = payload_len & 0xFF
        pkt[3] = addr & 0xFF
        pkt[4] = (addr >> 8) & 0xFF
        pkt[6] = 1 if last else 0
        if data:
            pkt[8:8 + len(data)] = data
        return bytes([0]) + bytes(pkt)

    def request(self, cmd, payload=b'', addr_start=0, iface=None, timeout=0.5,
                retries=3, check_addr=False, custom_header=None, need_response=True,
                collect=True, content_size=None, full_payloads=False):
        """
        模仿官方 NX(): 按 (报文-8) 切块，逐包发送并等待对应响应。
        content_size 对应官方 NX 参数 r（默认取 len(payload)）：
        包头的长度字段填的是"剩余内容长度"w，而不是实际携带的数据长度。
        默认返回响应 data 段拼接后的 bytes（不含 8 字节头）；
        full_payloads=True 时返回每个包完整响应 payload 的列表（含 55 头）。
        """
        iface = iface or self.proto
        body = iface.out_len - 1
        chunk = body - len(custom_header or b'') if custom_header else body - 8
        if chunk <= 0:
            raise ValueError('报文太小')
        total = content_size if content_size is not None else len(payload)
        count = max(1, (total + chunk - 1) // chunk) if total > 0 else 1
        out = bytearray()
        acc_full = []
        for k in range(count):
            addr = addr_start + k * chunk
            rest = total - k * chunk
            w = rest if k == count - 1 else chunk
            part = payload[k * chunk:k * chunk + chunk] if payload else b''
            ln = len(part)
            last = (k == count - 1)
            pkt = self._build_packet(iface, cmd, w, addr, part, last, custom_header)
            if custom_header:
                # 自定义头里已有 addr/序号等，data 跟在头后面
                pkt = bytearray([0]) + bytearray(iface.out_len - 1)
                pkt[1:1 + len(custom_header)] = custom_header
                if ln:
                    pkt[1 + len(custom_header):1 + len(custom_header) + ln] = part
                pkt = bytes(pkt)
            for attempt in range(retries + 1):
                iface.write_report(pkt)
                if not need_response:
                    break
                deadline = time.time() + timeout
                matched = None
                while time.time() < deadline:
                    r = iface.read_report(timeout=max(0.01, deadline - time.time()))
                    if not r:
                        break
                    payload_r = r[1:]           # 去掉 report ID 字节
                    if len(payload_r) < 8 or payload_r[0] != 0x55:
                        continue
                    rcmd = payload_r[1]
                    raddr = payload_r[3] | (payload_r[4] << 8)
                    if rcmd != (cmd & 0xFF):
                        continue
                    if check_addr and raddr != addr:
                        continue
                    matched = payload_r
                    break
                if matched is not None:
                    if collect:
                        out += matched[8:]
                    acc_full.append(matched)
                    break
        if full_payloads:
            return acc_full
        # 与官方一致：只取逻辑内容长度（官方各 getXxx 里有 .slice(0, contentSize)）
        if total > 0:
            return bytes(out[:total])
        return bytes(out)

    # --------- 具体命令 ---------
    def get_device_info(self):
        raw = self.request(CMD['GET_DEVICE_INFO'], b'', content_size=48)
        # 与官方 getDeviceInfo 一致：解析 48 字节
        d = raw[:48]
        if len(d) < 36:
            raise RuntimeError(f'设备信息长度异常: {len(d)}')
        ver = ((d[8] & 0x0F) + ((d[8] & 0xF0) >> 4) * 10 + d[9] * 100) / 100
        return {
            'romSize': d[0],
            'macroSpaceSize': d[2] | (d[3] << 8),
            'vid': d[4] | (d[5] << 8),
            'pid': d[6] | (d[7] << 8),
            'version': ver,
            'sensor': d[10] | (d[11] << 8),
            'manufacturer': d[12] | (d[13] << 8),
            'product': d[14] | (d[15] << 8),
            'workMode': d[16],
            'batteryLevel': d[17],
            'chargeStatus': d[18],
            'currentProfile': d[19],
            'axisInfo': d[20] | (d[21] << 8),
            'tftMaxFrames': d[22] | (d[23] << 8),
            'gifMaxFrames': d[24] | (d[25] << 8),
            'ledMaxFrames': d[26] | (d[27] << 8),
            'tftDirection': d[28],
            'rtPrecision': d[29],
            'frameVersion': d[30],
            'lightingVersion': d[31],
            'firmwareStatus': d[32],
            'maxProfile': d[33],
            'tftColorByteOrder': d[35],
            'raw': d,
        }

    def get_game_mode(self):
        raw = self.request(CMD['GET_GAME_MODE'], content_size=56)
        d = raw[:56]
        return {
            'gameMode': d[1], 'fnSwitch': d[2], 'sleepTime': d[3], 'keyDelay': d[4],
            'reportRate': d[5], 'systemMode': d[6], 'tftDisplayTime': d[7],
            'topDeadZone': d[8] / 100, 'bottomDeadZone': d[9] / 100,
            'stabilityMode': d[11], 'autoCalibration': d[14],
            'singleKeyWakeup': d[15], 'pushButtonMode': d[16], 'nkroSwitch': d[17],
            'wirelessReportRate': d[18] | (d[19] << 8), 'powerMode': d[20],
            'raw': d,
        }

    def get_led_effect(self):
        raw = self.request(CMD['GET_LED_EFFECT'], content_size=16)
        d = raw[:16]
        return {
            'mode': d[0], 'red': d[1], 'green': d[2], 'blue': d[3],
            'driverSetting': d[4], 'secondary': (d[5], d[6], d[7]),
            'colorMode': d[8], 'brightness': d[9], 'speed': d[10],
            'direction': d[11], 'effectModeType': d[12],
            'raw': d,
        }

    # --------- 原始读取（contentSize 与官方 getXxx 一致） ---------
    def read_cmd(self, cmd, content_size, payload=b'', timeout=0.5, retries=2):
        return self.request(cmd, payload, content_size=content_size,
                            timeout=timeout, retries=retries)

    def read_key_matrix(self):
        return self.read_cmd(CMD['GET_KEY'], 512)

    def read_fn_key_matrix(self):
        return self.read_cmd(CMD['GET_FN_KEY'], 512)

    def read_default_key_matrix(self):
        return self.read_cmd(CMD['GET_DEFAULT_KEY_MATRIX'], 512)

    def read_default_fn_key_matrix(self):
        return self.read_cmd(CMD['GET_DEFAULT_FN_KEY_MATRIX'], 512)

    def read_custom_led_data(self):
        return self.read_cmd(CMD['GET_CUSTOM_LED_DATA'], 512)

    def read_all_lights_rgb(self):
        """官方 getAllLightsRGB：payload 是 128 个 [ledId,0,0,0] 的 512 字节请求"""
        payload = bytearray(512)
        for i in range(128):
            payload[i * 4] = i
        return self.read_cmd(CMD['GET_ALL_LIGHTS_RGB'], 512, bytes(payload))

    def read_macro_table(self):
        return self.read_cmd(CMD['GET_MACRO'], 400)

    def read_dot_matrix_config(self):
        return self.read_cmd(CMD['GET_DOT_MATRIX_CONFIG'], 10)

    def read_light_box(self):
        return self.read_cmd(CMD['GET_LIGHT_BOX'], 24)

    def read_side_light(self):
        return self.read_cmd(CMD['GET_SIDE_LIGHT'], 24)

    # --------- 改键（已验证：写整表 + 回读校验） ---------
    def key_get(self, slot):
        """读单个槽位（官方 getSingleKeyData：4 字节自定义头，addr=slot*4）"""
        hdr = bytes([0xAA, CMD['GET_KEY'], 4, (slot * 4) & 0xFF,
                     (slot * 4) >> 8 & 0xFF, 0, 0, 0])
        return self.request(CMD['GET_KEY'], b'', content_size=4,
                            custom_header=hdr, timeout=0.5, retries=1)

    def key_set_matrix(self, matrix, verify=True):
        """整表写入 SET_KEY(512 字节)，可选回读校验"""
        m = bytes(matrix)
        if len(m) != 512:
            raise ValueError(f'按键矩阵必须是 512 字节，实际 {len(m)}')
        self.request(CMD['SET_KEY'], m, content_size=512, timeout=0.8, retries=1)
        if not verify:
            return True, None
        now = self.read_key_matrix()
        return now == m, now

    def key_set_usage(self, slot, hid_usage):
        """把某槽位改成普通键盘键（pageType=2, param2=HID usage）"""
        m = bytearray(self.read_key_matrix())
        m[slot * 4:slot * 4 + 4] = bytes([2, 0, hid_usage & 0xFF, 0])
        return self.key_set_matrix(m)

    def key_set_entry(self, slot, page_type, p1, p2, p3):
        """把某槽位写成任意 4 字节编码（pageType 13 可写 FN 动作）"""
        m = bytearray(self.read_key_matrix())
        m[slot * 4:slot * 4 + 4] = bytes([page_type & 0xFF, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF])
        return self.key_set_matrix(m)

    def key_reset_slot(self, slot):
        m = bytearray(self.read_key_matrix())
        m[slot * 4:slot * 4 + 4] = b'\x00\x00\x00\x00'
        return self.key_set_matrix(m)

    # --------- 设置（原始读改写，保留不认识的字段） ---------
    def set_game_mode_raw(self, raw56):
        m = bytes(raw56)
        if len(m) != 56:
            raise ValueError(f'game mode payload 必须是 56 字节，实际 {len(m)}')
        self.request(CMD['SET_GAME_MODE'], m, content_size=56, timeout=0.8, retries=1)
        now = bytes(self.get_game_mode()['raw'])
        return now == m, now

    def set_tft_display_time(self, on):
        """切换「TFT 显示时间」开关（游戏模式 payload[7]，读改写避免动未知字段）"""
        raw = bytearray(self.get_game_mode()['raw'])
        raw[7] = 1 if on else 0
        return self.set_game_mode_raw(raw)

    # --------- 灯 ---------
    def read_all_lights_rgb_parsed(self):
        d = self.read_all_lights_rgb()
        out = []
        for i in range(min(128, len(d) // 4)):
            out.append({'ledId': d[i * 4], 'r': d[i * 4 + 1],
                        'g': d[i * 4 + 2], 'b': d[i * 4 + 3]})
        return out

    def write_custom_led_colors(self, colors):
        """写自定义单键颜色：colors=[(ledId, r, g, b), ...]，512 字节 = 128×[id,R,G,B]"""
        buf = bytearray(512)
        for led, r, g, b in colors:
            if 0 <= led < 128:
                buf[led * 4:led * 4 + 4] = bytes([led, r & 0xFF, g & 0xFF, b & 0xFF])
        self.request(CMD['SET_CUSTOM_LED_DATA'], bytes(buf), content_size=512,
                     timeout=1.0, retries=1)
        return self.read_custom_led_data()

    def set_tft_screen_info(self, cpu_usage=0, cpu_temp=0, gpu_usage=0, gpu_temp=0,
                            current_temp=0, max_temp=0, min_temp=0, weather=0, humidity=0):
        """官方 setTftScreenInfo：SET_TEMPORARY_COMMAND_DATA + 24 字节 payload"""
        p = bytearray(24)
        p[6] = 90
        p[12] = cpu_usage & 0xFF
        p[13] = cpu_temp & 0xFF
        p[14] = gpu_usage & 0xFF
        p[15] = gpu_temp & 0xFF
        p[16] = current_temp & 0xFF
        p[17] = max_temp & 0xFF
        p[18] = min_temp & 0xFF
        p[19] = weather & 0xFF
        p[20] = humidity & 0xFF
        return self.request(CMD['SET_TEMPORARY_COMMAND_DATA'], bytes(p), timeout=0.5,
                            retries=0)

    def set_tft_material(self, material_id, data, progress=None, iface=None):
        """官方 setTftMaterial：TFT 接口，每包 4104 字节，自定义头 8 字节"""
        tft = iface or self.tft
        if tft is None:
            raise RuntimeError('未找到 TFT HID 接口 (usagePage=0xFF67)')
        body = tft.out_len - 1
        chunk = body - 8
        count = (len(data) + chunk - 1) // chunk
        for k in range(count):
            part = data[k * chunk:(k + 1) * chunk]
            hdr = bytes([0xAA, CMD['SET_TFT_MATERIAL'], k & 0xFF, (k >> 8) & 0xFF,
                         count & 0xFF, (count >> 8) & 0xFF,
                         material_id & 0xFF, (material_id >> 8) & 0xFF])
            pkt = bytearray([0]) + bytearray(body)
            pkt[1:1 + 8] = hdr
            pkt[9:9 + len(part)] = part
            tft.write_report(bytes(pkt))
            if progress:
                progress(int((k + 1) / count * 100))
            time.sleep(0.001)
        return True

    def set_tft_user_animation(self, delays, rgb565_data, progress=None, iface=None):
        """官方 setTftUserAnimation：帧延时表(256B) + RGB565 数据，TFT 接口"""
        tft = iface or self.tft
        if tft is None:
            raise RuntimeError('未找到 TFT HID 接口')
        mv = bytearray(256)
        mv[0] = len(delays) & 0xFF
        for i in range(len(delays) - 1):
            mv[i + 1] = min(delays[i] * 5, 255)
        mv[len(delays)] = 0
        data = bytes(mv) + rgb565_data
        body = tft.out_len - 1
        chunk = body - 8
        count = (len(data) + chunk - 1) // chunk
        for k in range(count):
            part = data[k * chunk:(k + 1) * chunk]
            hdr = bytes([0xAA, CMD['SET_TFT_USER_ANIMATION'], k & 0xFF, (k >> 8) & 0xFF,
                         count & 0xFF, (count >> 8) & 0xFF, 80, 6])
            pkt = bytearray([0]) + bytearray(body)
            pkt[1:1 + 8] = hdr
            pkt[9:9 + len(part)] = part
            tft.write_report(bytes(pkt))
            if progress:
                progress(int((k + 1) / count * 100))
            time.sleep(0.001)
        return True


    def set_led_effect(self, mode=1, red=255, green=255, blue=255, secondary=(0, 0, 0),
                       color_mode=1, brightness=5, speed=3, direction=0,
                       effect_mode_type=0):
        """官方 setLEDEffect：SET_LED_EFFECT(35)，16 字节 payload"""
        p = bytearray(16)
        p[0] = mode & 0xFF
        p[1] = red & 0xFF
        p[2] = green & 0xFF
        p[3] = blue & 0xFF
        p[4] = 255
        p[5] = secondary[0] & 0xFF
        p[6] = secondary[1] & 0xFF
        p[7] = secondary[2] & 0xFF
        p[8] = color_mode & 0xFF
        p[9] = brightness & 0xFF
        p[10] = speed & 0xFF
        p[11] = direction & 0xFF
        p[12] = effect_mode_type & 0xFF
        p[14] = 0xAA
        p[15] = 0x55
        return self.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)

    def set_tft_datetime(self, dt=None, weekday=None):
        """官方 setTftDateTime：SET_TEMPORARY_COMMAND_DATA + marker 0x5A"""
        import datetime as _dt
        dt = dt or _dt.datetime.now()
        if weekday is None:
            weekday = dt.isoweekday() % 7   # 0=周日
        p = bytearray(10)
        p[0] = 90
        p[1] = 1
        p[2] = 90
        p[3] = dt.year % 100
        p[4] = dt.month
        p[5] = dt.day
        p[6] = dt.hour
        p[7] = dt.minute
        p[8] = dt.second
        p[9] = weekday & 0xFF
        return self.request(CMD['SET_TEMPORARY_COMMAND_DATA'], bytes(p),
                            timeout=1.0, retries=0)

    def set_tft_built_in_index(self, index):
        """官方 setTftBuiltInIndex：切换 TFT 内置动画索引"""
        return self.request(CMD['SET_TFT_BUILT_IN_INDEX'], bytes([index & 0xFF]),
                            timeout=1.0, retries=0)

    def set_profile(self, index):
        hdr = bytes([0xAA, CMD['SET_PROFILE'], index & 0xFF])
        return self.request(CMD['SET_PROFILE'], b'\x00', content_size=1,
                            custom_header=hdr, timeout=1.0)


# ----------------------------- 图像 → RGB565 -----------------------------
def image_to_rgb565(path, width=240, height=135, byte_order=0):
    """把图片转成屏幕用的 RGB565 字节流（含缩放裁剪 + 字节序）"""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    src_w, src_h = im.size
    scale = max(width / src_w, height / src_h)
    nw, nh = max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - width) // 2
    top = (nh - height) // 2
    im = im.crop((left, top, left + width, top + height))
    px = im.tobytes()
    out = bytearray(width * height * 2)
    for i in range(width * height):
        r = px[3 * i]
        g = px[3 * i + 1]
        b = px[3 * i + 2]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
        hi = (v >> 8) & 0xFF
        lo = v & 0xFF
        if byte_order == 1:
            out[2 * i] = hi
            out[2 * i + 1] = lo
        else:
            out[2 * i] = lo
            out[2 * i + 1] = hi
    return bytes(out)


def gif_frames_to_rgb565(path, width=240, height=135, byte_order=0, max_frames=None):
    """把 GIF 拆成帧：返回 (delays_ms 列表, 拼接后的 RGB565 数据)"""
    from PIL import Image, ImageSequence
    im = Image.open(path)
    delays, chunks = [], []
    n = 0
    for frame in ImageSequence.Iterator(im):
        if max_frames and n >= max_frames:
            break
        f = frame.convert('RGB')
        src_w, src_h = f.size
        scale = max(width / src_w, height / src_h)
        nw, nh = max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale)))
        f = f.resize((nw, nh), Image.LANCZOS)
        left = (nw - width) // 2
        top = (nh - height) // 2
        f = f.crop((left, top, left + width, top + height))
        px = f.tobytes()
        buf = bytearray(width * height * 2)
        for i in range(width * height):
            r = px[3 * i]
            g = px[3 * i + 1]
            b = px[3 * i + 2]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
            hi = (v >> 8) & 0xFF
            lo = v & 0xFF
            if byte_order == 1:
                buf[2 * i] = hi
                buf[2 * i + 1] = lo
            else:
                buf[2 * i] = lo
                buf[2 * i + 1] = hi
        chunks.append(bytes(buf))
        delays.append(frame.info.get('duration', 100) // 10 or 10)  # 单位: 10ms
        n += 1
    return delays, b''.join(chunks)


def main():
    args = sys.argv[1:]
    kb = AjazzKeyboard()
    try:
        if not args or args[0] == 'info':
            print('== 接口 ==')
            for i in kb.ifaces:
                print(f'  {i.mi} usagePage=0x{i.usage_page:04X} usage=0x{i.usage:04X} '
                      f'in={i.in_len} out={i.out_len} product={i.product!r}')
            print('== DEVICE INFO ==')
            info = kb.get_device_info()
            for k, v in info.items():
                if k == 'raw':
                    continue
                print(f'  {k}: {v}')
            print(f'  raw: {" ".join(f"{x:02X}" for x in info["raw"])}')
            print('== GAME MODE ==')
            gm = kb.get_game_mode()
            print(' ', {k: v for k, v in gm.items() if k != 'raw'})
            print('  raw:', ' '.join(f'{x:02X}' for x in gm['raw']))
            print('== LED EFFECT ==')
            le = kb.get_led_effect()
            print(' ', {k: v for k, v in le.items() if k != 'raw'})
            print('  raw:', ' '.join(f'{x:02X}' for x in le['raw']))
        elif args[0] == 'light':
            # light <mode> <r> <g> <b> [brightness] [speed] [colorMode]
            mode = int(args[1]); r = int(args[2]); g = int(args[3]); b = int(args[4])
            br = int(args[5]) if len(args) > 5 else 5
            sp = int(args[6]) if len(args) > 6 else 3
            cm = int(args[7]) if len(args) > 7 else 1
            rep = kb.set_led_effect(mode, r, g, b, brightness=br, speed=sp, color_mode=cm)
            print('SET_LED_EFFECT ok, resp len =', len(rep))
            print('device now:', kb.get_led_effect())
        elif args[0] == 'time':
            kb.set_tft_datetime()
            print('屏幕时间已同步')
        elif args[0] == 'builtin':
            kb.set_tft_built_in_index(int(args[1]))
            print('已切换内置动画索引', args[1])
        elif args[0] in ('screen', 'gif'):
            if len(args) < 2:
                print('用法: screen <图片> [宽] [高] / gif <GIF> [最大帧] [宽] [高]')
                return
            path = args[1]
            if args[0] == 'screen':
                w = int(args[2]) if len(args) > 2 else 240
                h = int(args[3]) if len(args) > 3 else 135
                info = kb.get_device_info()
                bo = info.get('tftColorByteOrder', 0)
                print(f'图片 → RGB565 ({w}x{h}, byteOrder={bo}) ...')
                data = image_to_rgb565(path, w, h, bo)
                print(f'数据 {len(data)} 字节，开始上传到 TFT (material 0) ...')
                def _p(pct):
                    print(f'\r上传 {pct}%', end='', flush=True)
                kb.set_tft_material(0, data, progress=_p)
                print('\n上传完成')
            else:
                maxf = int(args[2]) if len(args) > 2 else 140
                w = int(args[3]) if len(args) > 3 else 240
                h = int(args[4]) if len(args) > 4 else 135
                info = kb.get_device_info()
                bo = info.get('tftColorByteOrder', 0)
                delays, data = gif_frames_to_rgb565(path, w, h, bo, maxf)
                print(f'GIF → {len(delays)} 帧, 共 {len(data)} 字节 RGB565, byteOrder={bo}')
                def _q(pct):
                    print(f'\r上传 {pct}%', end='', flush=True)
                kb.set_tft_user_animation(delays, data, progress=_q)
                print('\n动画上传完成')
        elif args[0] == 'dump':
            import json
            import os

            def _jsonable(v):
                if isinstance(v, (bytes, bytearray)):
                    return {'len': len(v), 'hex': bytes(v).hex(),
                            'bytes': list(v)}
                if isinstance(v, dict):
                    return {k: _jsonable(x) for k, x in v.items()}
                if isinstance(v, (list, tuple)):
                    return [_jsonable(x) for x in v]
                return v

            reads = [
                ('device_info', kb.get_device_info),
                ('game_mode', kb.get_game_mode),
                ('led_effect', kb.get_led_effect),
                ('key_matrix', kb.read_key_matrix),
                ('fn_key_matrix', kb.read_fn_key_matrix),
                ('default_key_matrix', kb.read_default_key_matrix),
                ('default_fn_key_matrix', kb.read_default_fn_key_matrix),
                ('custom_led_data', kb.read_custom_led_data),
                ('all_lights_rgb', kb.read_all_lights_rgb),
                ('macro_table', kb.read_macro_table),
                ('dot_matrix_config', kb.read_dot_matrix_config),
                ('light_box', kb.read_light_box),
                ('side_light', kb.read_side_light),
            ]
            out = {}
            for name, fn in reads:
                t0 = time.time()
                try:
                    v = fn()
                    out[name] = _jsonable(v)
                    if isinstance(v, (bytes, bytearray)):
                        print(f'{name}: len={len(v)} ({time.time() - t0:.2f}s)')
                        print('   ', ' '.join(f'{x:02X}' for x in v[:64]),
                              '...' if len(v) > 64 else '')
                    else:
                        print(f'{name}: {json.dumps(_jsonable(v), ensure_ascii=False)[:300]}')
                except Exception as e:
                    out[name] = {'error': str(e)}
                    print(f'{name}: FAILED {e}')
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'docs', 'device_dump.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print('saved', path)
        elif args[0] == 'key':
            sub = args[1] if len(args) > 1 else 'get'
            if sub == 'get':
                slot = int(args[2])
                print('slot', slot, '=>', kb.key_get(slot).hex(' '))
            elif sub == 'set':
                slot = int(args[2])
                data = bytes(int(x, 16) for x in args[3:7])
                ok, now = kb.key_set_matrix(
                    bytearray(kb.read_key_matrix()[:slot * 4]) + data
                    + kb.read_key_matrix()[slot * 4 + 4:])
                print('写入', data.hex(' '), '=>', '成功 ✓' if ok else '失败 ✗')
            elif sub == 'usage':
                slot = int(args[2])
                usage = int(args[3], 16) if len(args[3]) > 1 and args[3].lower().startswith('0x') \
                    else int(args[3])
                ok, now = kb.key_set_usage(slot, usage)
                print(f'slot {slot} -> HID 0x{usage:02X} =>', '成功 ✓' if ok else '失败 ✗')
            elif sub == 'reset':
                slot = int(args[2])
                ok, now = kb.key_reset_slot(slot)
                print(f'slot {slot} 清空 =>', '成功 ✓' if ok else '失败 ✗')
            else:
                print('用法: key get <slot> | key set <slot> AA BB CC DD | '
                      'key usage <slot> <usage> | key reset <slot>')
        elif args[0] == 'tft-time':
            on = args[1] in ('1', 'on', 'true') if len(args) > 1 else True
            ok, now = kb.set_tft_display_time(on)
            print('TFT 显示时间 =', on, '=>', '已写入 ✓' if ok else '未生效 ✗')
        elif args[0] == 'led':
            n = int(args[1]) if len(args) > 1 else 24
            for x in kb.read_all_lights_rgb_parsed()[:n]:
                print(f"  LED {x['ledId']:3d}: #{x['r']:02X}{x['g']:02X}{x['b']:02X}")
        elif args[0] == 'raw':
            data = bytes(int(x, 16) for x in args[1:])
            if kb.proto:
                if len(data) < kb.proto.out_len:
                    data = data + b'\x00' * (kb.proto.out_len - len(data))
                kb.proto.write_report(data)
                rep = kb.proto.read_report(timeout=1.0)
                print('recv:', ' '.join(f'{x:02X}' for x in rep) if rep else None)
        else:
            print('未知命令')
    finally:
        kb.close()


if __name__ == '__main__':
    main()
