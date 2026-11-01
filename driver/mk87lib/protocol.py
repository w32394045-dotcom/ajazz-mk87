"""AA/55 帧协议层：分帧、发送、响应收集、重试、ACK 匹配。

帧格式（详见 docs/protocol.md）::

    请求: AA cmd len addrLo addrHi hdr5 last hdr7 data...
          len   = 剩余内容长度（不是本包数据长度）
          addr  = 本包在逻辑内容中的字节偏移
          last  = 最后一包为 1
    响应: 55 cmd len addrLo addrHi hdr5 hdr6 hdr7 data...
          数据从 offset 8 开始，跨包按原序拼接

真机注意事项：
* 响应与请求的 cmd 相同即视为 ACK；addr 匹配只在 check_addr=True 时校验；
* 同接口并发读写会互相抢帧，调用方需串行化（设备层持锁）；
* TFT 上传（0x4D/0x50）的 ACK 是 0x41，且官方实现不做逐包确认，本层提供 no-response 模式。
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from . import logsetup
from .errors import ProtocolTimeout
from .transport import HidInterface, normalize_report

log = logging.getLogger("mk87.protocol")


class Protocol:
    """一条协议通道（一个 HID 接口）。"""

    def __init__(self, iface: HidInterface):
        self.iface = iface
        self.body_len = iface.info.payload_len  # 不含 report ID

    # ------------------------------------------------------------------ 帧构造
    def build_packet(
        self,
        cmd: int,
        content_len: int,
        addr: int,
        data: bytes = b"",
        last: bool = True,
    ) -> bytes:
        pkt = bytearray(self.body_len)
        pkt[0] = 0xAA
        pkt[1] = cmd & 0xFF
        pkt[2] = content_len & 0xFF
        pkt[3] = addr & 0xFF
        pkt[4] = (addr >> 8) & 0xFF
        pkt[6] = 1 if last else 0
        if data:
            pkt[8:8 + len(data)] = data
        return bytes([0]) + bytes(pkt)

    def write_raw_report(self, report: bytes) -> int:
        """直接写一个完整 report（含 report ID）。"""
        return self.iface.write_report(report)

    # ------------------------------------------------------------------ 请求
    def request(
        self,
        cmd: int,
        payload: bytes = b"",
        addr_start: int = 0,
        timeout: float = 0.5,
        retries: int = 2,
        content_size: Optional[int] = None,
        need_response: bool = True,
        check_addr: bool = False,
        collect: bool = True,
    ) -> bytes:
        """发送一条命令并收集响应数据段（不含 8 字节头）。

        content_size: 逻辑内容总长（默认 len(payload)）。设备会按
        (payload_len - 8) 切块，逐包响应。
        """
        payload = bytes(payload or b"")
        total = content_size if content_size is not None else len(payload)
        chunk = max(1, self.body_len - 8)
        count = max(1, (total + chunk - 1) // chunk) if total > 0 else 1
        out = bytearray()
        for k in range(count):
            addr = addr_start + k * chunk
            rest = total - k * chunk
            w = rest if k == count - 1 else chunk
            part = payload[k * chunk:k * chunk + chunk]
            last = k == count - 1
            pkt = self.build_packet(cmd, w, addr, part, last)
            if not need_response:
                self.iface.write_report(pkt)
                continue
            resp = self._transact(pkt, cmd, timeout, retries, addr if check_addr else None)
            if resp is None:
                raise ProtocolTimeout(f"命令 0x{cmd:02X} 第 {k + 1}/{count} 包无响应")
            if collect:
                out += resp[8:]
        if total > 0:
            return bytes(out[:total])
        return bytes(out)

    def request_full(
        self,
        cmd: int,
        payload: bytes = b"",
        addr_start: int = 0,
        timeout: float = 0.5,
        retries: int = 2,
        content_size: Optional[int] = None,
    ) -> List[bytes]:
        """与 request 相同，但返回每个包的完整响应（含 8 字节头）。"""
        payload = bytes(payload or b"")
        total = content_size if content_size is not None else len(payload)
        chunk = max(1, self.body_len - 8)
        count = max(1, (total + chunk - 1) // chunk) if total > 0 else 1
        out: List[bytes] = []
        for k in range(count):
            addr = addr_start + k * chunk
            rest = total - k * chunk
            w = rest if k == count - 1 else chunk
            part = payload[k * chunk:k * chunk + chunk]
            resp = self._transact(
                self.build_packet(cmd, w, addr, part, k == count - 1), cmd, timeout, retries
            )
            if resp is None:
                raise ProtocolTimeout(f"命令 0x{cmd:02X} 第 {k + 1}/{count} 包无响应")
            out.append(resp)
        return out

    # ------------------------------------------------------------------ 底层
    def _transact(
        self, pkt: bytes, cmd: int, timeout: float, retries: int, expect_addr: Optional[int]
    ) -> Optional[bytes]:
        for _attempt in range(retries + 1):
            log.debug("HID TX cmd=0x%02X len=%d %s", cmd, len(pkt), logsetup.redact(pkt, 96))
            self.iface.write_report(pkt)
            deadline = time.time() + timeout
            while time.time() < deadline:
                r = self.iface.read_normalized(timeout=max(0.005, deadline - time.time()))
                if r is None:
                    break
                if len(r) < 9 or r[0] != 0x55:
                    log.debug("HID RX 非协议帧 len=%d %s", len(r), logsetup.redact(r, 96))
                    continue
                if r[1] != (cmd & 0xFF):
                    log.debug("HID RX 其它命令 cmd=0x%02X len=%d", r[1], len(r))
                    continue
                if expect_addr is not None:
                    addr = r[3] | (r[4] << 8)
                    if addr != expect_addr:
                        log.debug("HID RX 地址不匹配 got=%d want=%d", addr, expect_addr)
                        continue
                log.debug("HID RX cmd=0x%02X len=%d", cmd, len(r))
                return r
        log.warning("HID 超时 cmd=0x%02X timeout=%.3fs retries=%d", cmd, timeout, retries)
        return None

    def read_event(self, timeout: float = 0.05) -> Optional[bytes]:
        """读取一条非请求响应（通知帧 / 异步 ACK），原样返回 payload。"""
        r = self.iface.read_normalized(timeout)
        if r is not None:
            log.debug("HID 通知帧 len=%d %s", len(r), logsetup.redact(r, 96))
        return r
