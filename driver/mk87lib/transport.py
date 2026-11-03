"""跨平台 HID 传输层（Windows / Linux，基于 hidapi）。

设计要点
--------
* hidapi 的 ``write()`` 需要传入**完整 report**（首字节 = report ID，本设备为 0）；
* hidapi 的 ``read()`` 在 Windows 上对 report ID = 0 的设备**不返回** ID 字节，
  在 Linux hidraw 上会返回前导 0 —— 上层统一用 :func:`normalize_report` 归一化；
* 每个 HID 接口（MI）单独打开一个句柄；同接口并发读写会冲突（见 docs/TEST-REPORT.md）。

接口识别（实测，见 docs/FEATURES.md）::

    USB  0C45:8047  usagePage 0xFF68  payload 64   主协议
                    usagePage 0xFF67  payload 4104 TFT
    2.4G 0C45:FEFE usagePage 0xFF60  payload 32   主协议（工作通道）
                    usagePage 0xFF59  payload 64   无响应（忽略）
                    usagePage 0xFFFF  payload 4    唤醒帧（report ID 5）

Linux 后端（v0.1.6 起强制 hidraw）
---------------------------------
PyPI 的 ``hidapi`` wheel 在 Linux 上打包了**两个**扩展模块：
``hid``（libusb 后端）和 ``hidraw``（hidraw 后端）。cython-hidapi 的 setup.py
默认把 ``hid`` 编成 libusb 后端，于是 ``import hid`` 在 Linux 上拿到的是
libusb 实现：``enumerate()`` 的 path 形如 ``1-1.1:1.0``（不是 ``/dev/hidrawN``）、
usage_page 恒为 0、打开要 /dev/bus/usb 权限、还要和内核 HID 驱动抢接口 ——
配置键盘必须用 ``import hidraw``。v0.1.5 及以前误用 ``hid``，Linux 因此永远
识别不到设备（见 docs/DEVLOG.md §22）。
"""
from __future__ import annotations

import importlib
import logging
import os
import platform
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import const
from .errors import DeviceDisconnected, DeviceNotFound

log = logging.getLogger("mk87.transport")


def _load_hid_backend(importer=None):
    """选择 hidapi 的 Python 模块，返回 (module, 后端名)。

    * Linux：优先 ``hidraw``（path=/dev/hidrawN，enumerate 自带 usage_page）；
      没有 hidraw 模块时退回 ``hid``（libusb 后端，不可用于日常配置，只用于报错）。
    * Windows/macOS：``hid``（原生 HID API）。
    """
    imp = importer or importlib.import_module
    if platform.system() == "Linux":
        try:
            return imp("hidraw"), "hidraw"
        except Exception:  # noqa: BLE001 - 见 Backend 说明
            pass
        try:
            return imp("hid"), "libusb"
        except Exception:  # noqa: BLE001
            return None, "missing"
    try:
        return imp("hid"), "native"
    except Exception:  # noqa: BLE001
        return None, "missing"


hid, BACKEND = _load_hid_backend()


def _to_bytes(v) -> bytes:
    if isinstance(v, bytes):
        return v
    if isinstance(v, str):
        return v.encode()
    return bytes(v)


def _decode(v) -> str:
    try:
        b = _to_bytes(v)
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
    except Exception:
        pass
    return str(v or "")


@dataclass
class IfaceInfo:
    """一个 HID 接口的静态信息。"""

    path: bytes
    vid: int
    pid: int
    product: str
    manufacturer: str
    serial: str
    usage_page: int
    usage: int
    interface_number: int
    payload_len: int

    @property
    def out_report_len(self) -> int:
        """写入时完整 report 长度（含 report ID 字节）。"""
        return self.payload_len + 1

    @property
    def read_max_len(self) -> int:
        """读取时请求的最大长度（多留 1 字节给可能存在的 report ID）。"""
        return self.payload_len + 1

    @property
    def is_24g(self) -> bool:
        return self.pid == const.PID_DONGLE


def payload_len_for(pid: int, usage_page: int) -> int:
    return const.PAYLOAD_LEN.get((pid, usage_page), const.DEFAULT_PAYLOAD_LEN)


# ----------------------------------------------------------------------
# Linux：接口身份（usage_page）的读取与补全
# ----------------------------------------------------------------------
def parse_report_descriptor_usage(desc) -> Tuple[Optional[int], Optional[int]]:
    """从 HID report descriptor 解析**第一个** Usage Page / Usage。

    本工具靠 usagePage 区分主协议/TFT/2.4G/唤醒接口。hidapi 的 hidraw 后端
    会自己从 sysfs 解析出 usage_page；但 libusb 后端不填（恒为 0），部分发行版
    的 sysfs 也可能读不到，所以这里保留一份纯 Python 解析作为兜底/诊断。
    按 HID short item 格式解析：前缀 = tag(4bit)<<4 | type(2bit)<<2 | size(2bit)，
    type 1=Global（Usage Page）、type 2=Local（Usage）；遇到第一个
    Collection(type 0, tag 0xA) 即停止。
    """
    b = bytes(desc or b"")
    n = len(b)
    i = 0
    usage_page: Optional[int] = None
    usage: Optional[int] = None
    while i < n:
        prefix = b[i]
        i += 1
        size = prefix & 0x03
        if size == 3:
            size = 4
        typ = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if i + size > n:
            break
        value = int.from_bytes(b[i:i + size], "little") if size else None
        i += size
        if typ == 1 and tag == 0 and usage_page is None and value is not None:
            usage_page = value
        elif typ == 2 and tag == 0 and usage is None and value is not None:
            usage = value
        elif typ == 0 and tag == 0xA:  # Collection：顶层集合开始，后面的 usage page 可能属于子集合
            break
    return usage_page, usage


SYSFS_HIDRAW_ROOT = "/sys/class/hidraw"


def read_sysfs_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001 - sysfs 不存在/无权限
        return None


def parse_sysfs_hid_id(uevent: Optional[str]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """解析 hidraw 的 uevent：``HID_ID=0003:00000C45:00008047`` -> (bus, vid, pid)。"""
    m = re.search(r"HID_ID=([0-9A-Fa-f]+):([0-9A-Fa-f]{8}):([0-9A-Fa-f]{8})", uevent or "")
    if not m:
        return None, None, None
    return int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)


def _sysfs_interface_number(device_dir: str) -> int:
    """从 sysfs 推断 hidraw 节点所属 USB 接口号（bInterfaceNumber / 1-1.1:1.0）。"""
    real = os.path.realpath(device_dir)
    try:
        with open(os.path.join(os.path.dirname(real), "bInterfaceNumber"), "r",
                  encoding="utf-8") as f:
            return int(f.read().strip(), 16)
    except Exception:  # noqa: BLE001 - 退化为解析 usb_interface 目录名
        pass
    m = re.search(r":(\d+)\.(\d+)$", os.path.basename(os.path.dirname(real)))
    return int(m.group(2)) if m else -1


def iter_sysfs_hidraw(root: str = SYSFS_HIDRAW_ROOT):
    """遍历 ``/sys/class/hidraw/hidraw*``，产出 (节点名, 设备目录)。"""
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return
    for name in names:
        if not name.startswith("hidraw"):
            continue
        base = os.path.join(root, name)
        device_dir = os.path.join(base, "device")
        if os.path.exists(os.path.join(device_dir, "uevent")):
            yield name, device_dir


def sysfs_descriptor_for(pid: int, interface_number: int = -1,
                         root: str = SYSFS_HIDRAW_ROOT) -> Optional[bytes]:
    """按 pid（+ 接口号）在 sysfs 里找 report descriptor。

    hidraw 后端的 path 是 ``/dev/hidrawN``，直接按路径取即可；但 libusb 后端的
    path 是 ``1-1.1:1.0`` 这类总线路径，只能用 pid/接口号反查。读到即可用于诊断。
    """
    for _name, device_dir in iter_sysfs_hidraw(root) or ():
        uevent = read_sysfs_text(os.path.join(device_dir, "uevent"))
        _bus, vid, node_pid = parse_sysfs_hid_id(uevent)
        if vid != const.VID or node_pid != pid:
            continue
        if interface_number >= 0:
            node_iface = _sysfs_interface_number(device_dir)
            if node_iface >= 0 and node_iface != interface_number:
                continue
        try:
            with open(os.path.join(device_dir, "report_descriptor"), "rb") as f:
                data = f.read(4096)
            if data:
                return data
        except Exception:  # noqa: BLE001
            continue
    return None


def _read_report_descriptor(info: IfaceInfo) -> Optional[bytes]:
    """读取一个接口的 report descriptor（hidapi API 优先，sysfs 兜底）。"""
    # A) hidapi >= 0.14 暴露 get_report_descriptor()（hidraw ioctl / USB 控制传输）
    if hid is not None:
        try:
            dev = hid.device()
            dev.open_path(info.path)
            try:
                desc = dev.get_report_descriptor()
            finally:
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
            if desc:
                return bytes(bytearray(desc))
        except Exception:  # noqa: BLE001 - 权限/内核不支持/后端不匹配时走 sysfs
            pass
    # B) path 就是 /dev/hidrawN
    try:
        path = info.path.decode("utf-8", "ignore") if isinstance(info.path, (bytes, bytearray)) else str(info.path)
        m = re.search(r"hidraw(\d+)\s*$", path)
        if m:
            with open(f"/sys/class/hidraw/hidraw{m.group(1)}/device/report_descriptor", "rb") as f:
                data = f.read(4096)
            if data:
                return data
    except Exception:  # noqa: BLE001
        pass
    # C) path 不是 /dev/hidrawN（例如 libusb 后端的 1-1.1:1.0）→ 用 pid/接口号反查
    try:
        return sysfs_descriptor_for(info.pid, info.interface_number)
    except Exception:  # noqa: BLE001
        return None


def _enrich_linux_usage(ifaces: List[IfaceInfo]) -> List[IfaceInfo]:
    """Linux：为 usage_page=0 的接口补齐 usage_page/usage/payload_len。

    只对缺 usage_page 的接口做（Windows 上 enumerate 已带 usage_page，不受影响）。
    hidraw 后端正常情况下 enumerate 已经填好，这里是兜底；仍失败时保持 0，
    由上层给出 Linux 后端/权限提示。
    """
    for info in ifaces:
        if info.usage_page:
            continue
        desc = _read_report_descriptor(info)
        if not desc:
            log.debug("Linux: 读不到 report descriptor pid=0x%04X iface=%s path=%r "
                      "(后端=%s)", info.pid, info.interface_number, info.path, BACKEND)
            continue
        usage_page, usage = parse_report_descriptor_usage(desc)
        if usage_page is None:
            log.debug("Linux: report descriptor 里没解析出 usage page pid=0x%04X iface=%s",
                      info.pid, info.interface_number)
            continue
        info.usage_page = int(usage_page)
        info.usage = int(usage or 0)
        info.payload_len = payload_len_for(info.pid, info.usage_page)
        log.debug("Linux: report descriptor 补齐 pid=0x%04X iface=%s usagePage=0x%04X",
                  info.pid, info.interface_number, info.usage_page)
    return ifaces


def _interface_number(raw) -> int:
    """取 interface_number；注意 0 不是「缺省」（旧代码 ``or -1`` 会把 0 变成 -1）。"""
    try:
        value = raw.get("interface_number") if hasattr(raw, "get") else raw
    except Exception:  # noqa: BLE001
        return -1
    if value is None:
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def enumerate_ifaces(vid: int = const.VID) -> List[IfaceInfo]:
    """枚举所有 AJAZZ HID 接口（键盘 USB + 2.4G 接收器）。"""
    if hid is None:
        raise DeviceNotFound("缺少 hidapi 依赖：pip install hidapi")
    if platform.system() == "Linux" and BACKEND == "libusb":
        # 官方 wheel 的 hid 模块是 libusb 后端：path 不是 /dev/hidrawN、拿不到
        # usage_page、打开还要 /dev/bus/usb 权限并和内核 HID 驱动抢接口。
        # 这种状态下「连接成功」也不可靠，直接给出可执行的修法。
        raise DeviceNotFound(
            "Linux 上 hidapi 只找到了 libusb 后端（模块 hid），没有 hidraw 后端（模块 hidraw）。"
            "请安装官方 hidapi wheel（pip install --force-reinstall hidapi）后重启；"
            "若为打包版，请升级到 v0.1.6 及以上"
        )
    ifaces: List[IfaceInfo] = []
    try:
        raw = hid.enumerate(vid, 0)
    except Exception as exc:  # pragma: no cover
        raise DeviceNotFound(f"HID 枚举失败: {exc}") from exc
    for d in raw:
        pid = int(d.get("product_id", 0))
        usage_page = int(d.get("usage_page", 0) or 0)
        ifaces.append(
            IfaceInfo(
                path=_to_bytes(d.get("path", b"")),
                vid=int(d.get("vendor_id", 0)),
                pid=pid,
                product=_decode(d.get("product_string")),
                manufacturer=_decode(d.get("manufacturer_string")),
                serial=_decode(d.get("serial_number")),
                usage_page=usage_page,
                usage=int(d.get("usage", 0) or 0),
                interface_number=_interface_number(d),
                payload_len=payload_len_for(pid, usage_page),
            )
        )
    if platform.system() == "Linux":
        ifaces = _enrich_linux_usage(ifaces)
    return ifaces


def normalize_report(report: bytes) -> bytes:
    """去掉 Linux hidraw 可能带的前导 report ID=0 字节。"""
    if report and report[0] == 0 and len(report) > 8 and report[1] == 0x55:
        return report[1:]
    return report


class HidInterface:
    """一个已打开的 HID 接口句柄。"""

    def __init__(self, info: IfaceInfo):
        self.info = info
        self._dev = None

    # ------------------------------------------------------------------ 生命周期
    @property
    def is_open(self) -> bool:
        return self._dev is not None

    def open(self) -> "HidInterface":
        if hid is None:
            raise DeviceNotFound("缺少 hidapi 依赖")
        try:
            dev = hid.device()
            dev.open_path(self.info.path)
            try:
                dev.set_nonblocking(0)  # 阻塞 + 超时读
            except Exception:
                pass
        except Exception as exc:
            raise DeviceDisconnected(
                f"打开 HID 接口失败（{self.info.product} usagePage=0x{self.info.usage_page:04X}）: {exc}"
            ) from exc
        self._dev = dev
        return self

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    # ------------------------------------------------------------------ 读写
    def write_report(self, report: bytes) -> int:
        """写入完整 report（含 report ID 首字节）。长度不足时补零。"""
        if self._dev is None:
            raise DeviceDisconnected("接口未打开")
        want = self.info.out_report_len
        if len(report) > want:
            raise ValueError(f"report 长度 {len(report)} 超过接口上限 {want}")
        if len(report) < want:
            report = bytes(report) + b"\x00" * (want - len(report))
        try:
            n = int(self._dev.write(list(report)))
        except Exception as exc:
            raise DeviceDisconnected(f"HID 写入失败: {exc}") from exc
        if n < 0:
            # hidapi 用 -1 表示写失败（大报文 TFT 通道常见）。不能静默当成功！
            raise DeviceDisconnected(
                f"HID 写入失败（hidapi 返回 -1，长度 {len(report)}）: usagePage=0x{self.info.usage_page:04X}"
            )
        return n

    def read_report(self, timeout: float = 0.1) -> Optional[bytes]:
        """读取一个 input report（可能含 report ID）。超时返回 None。"""
        if self._dev is None:
            raise DeviceDisconnected("接口未打开")
        try:
            data = self._dev.read(self.info.read_max_len, max(1, int(timeout * 1000)))
        except Exception as exc:
            raise DeviceDisconnected(f"HID 读取失败: {exc}") from exc
        if not data:
            return None
        return bytes(data)

    def read_normalized(self, timeout: float = 0.1) -> Optional[bytes]:
        r = self.read_report(timeout)
        return normalize_report(r) if r else None

    def drain(self, duration: float = 0.02) -> None:
        """把接口缓冲区里的残留帧读掉。"""
        end = time.time() + duration
        while time.time() < end:
            if self.read_report(timeout=min(0.01, max(0.001, end - time.time()))) is None:
                break

    def __repr__(self) -> str:  # pragma: no cover
        i = self.info
        return (
            f"<HidInterface {i.product!r} pid=0x{i.pid:04X} "
            f"usagePage=0x{i.usage_page:04X} payload={i.payload_len}>"
        )
