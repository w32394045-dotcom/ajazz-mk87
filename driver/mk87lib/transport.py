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
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from . import const
from .errors import DeviceDisconnected, DeviceNotFound

try:  # hidapi 包在 import 时叫 hid
    import hid  # type: ignore
except Exception:  # pragma: no cover - 环境缺依赖时给出清晰错误
    hid = None  # type: ignore


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


def enumerate_ifaces(vid: int = const.VID) -> List[IfaceInfo]:
    """枚举所有 AJAZZ HID 接口（键盘 USB + 2.4G 接收器）。"""
    if hid is None:
        raise DeviceNotFound("缺少 hidapi 依赖：pip install hidapi")
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
                interface_number=int(d.get("interface_number", -1) or -1),
                payload_len=payload_len_for(pid, usage_page),
            )
        )
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
