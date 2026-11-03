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
import threading
import time
from typing import List, Optional

from . import logsetup
from .errors import ProtocolTimeout
from .transport import HidInterface, normalize_report

log = logging.getLogger("mk87.protocol")

#: 音乐 ACK 类回包的主命令字节（66fps 播放时每秒数百条，逐条记日志没有价值）。
_QUIET_ACK_CMD = 0x32
#: 设备主动上报（断连/休眠/复位/notify）：即使帧很短也必须保留，不能当短 ACK 静默。
_NOTIFY_CMDS = frozenset((0xFA, 0xFC))


class _Bucket:
    """一个聚合键的计数状态。"""

    __slots__ = ("headline", "total", "pending", "last_emit", "sample", "extra")

    def __init__(self, now: float):
        self.headline = ""
        self.total = 0
        self.pending = 0
        self.last_emit = now
        self.sample = b""
        self.extra = ""


class _RateLimitedLogger:
    """把高频 DEBUG 按 key 聚合成摘要，避免每条 HID 回包都格式化 + 写盘。

    规则（同一 key）：

    * 首条立即输出，便于确认通道有数据；
    * 之后最多每 ``interval`` 秒输出一条摘要（累计条数 + 最近 24 字节 payload）；
    * 累计达到 ``max_count`` 且距上次输出超过 ``min_interval`` 时可提前输出。

    真正需要逐条诊断的低频路径（HID TX、请求-响应配对的 HID RX）不走这里。
    所有状态都在实例里，测试可通过 :func:`reset_rate_limits` 重置。
    """

    def __init__(
        self,
        logger: logging.Logger = log,
        interval: float = 2.0,
        max_count: int = 200,
        min_interval: float = 0.5,
    ) -> None:
        self.logger = logger
        self.interval = max(0.0, float(interval))
        self.max_count = max(1, int(max_count))
        self.min_interval = max(0.0, float(min_interval))
        self._buckets = {}
        self._lock = threading.Lock()

    def note(self, key, headline: str, sample: bytes = b"", extra: str = "") -> None:
        """计一条；只有满足限速条件时才真正格式化并写 DEBUG。"""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(now)
                self._buckets[key] = bucket
            bucket.headline = headline
            bucket.total += 1
            bucket.pending += 1
            bucket.sample = sample
            bucket.extra = extra
            elapsed = now - bucket.last_emit
            should_emit = (
                bucket.total == 1
                or elapsed >= self.interval
                or (bucket.pending >= self.max_count and elapsed >= self.min_interval)
            )
            if not should_emit:
                return
            total, pending = bucket.total, bucket.pending
            sample, extra = bucket.sample, bucket.extra
            bucket.pending = 0
            bucket.last_emit = now
        self._write(headline, extra, total, pending, sample)

    def _write(self, headline: str, extra: str, total: int, pending: int,
               sample: bytes) -> None:
        try:
            suffix = f" last={logsetup.redact(sample, 48)}" if sample else ""
            more = f" (+{pending})" if pending > 1 else ""
            self.logger.debug("%s 聚合 %s 累计=%d%s%s",
                              headline, extra, total, more, suffix)
        except Exception:  # noqa: BLE001 - 日志自身失败绝不能影响协议收发
            pass

    def flush(self) -> None:
        """输出所有尚未写出的聚合计数（测试 / 退出前用）。"""
        with self._lock:
            pending = [
                (b.headline, b.extra, b.total, b.pending, b.sample)
                for b in self._buckets.values() if b.pending
            ]
            for bucket in self._buckets.values():
                bucket.pending = 0
        for headline, extra, total, count, sample in pending:
            self._write(headline, extra, total, count, sample)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


_rx_log = _RateLimitedLogger(log)


def reset_rate_limits() -> None:
    """重置 HID RX 限速日志状态（单测用）。"""
    _rx_log.reset()


def flush_rate_limits() -> None:
    """立即输出待聚合计数（单测 / 诊断用）。"""
    _rx_log.flush()


def _is_quiet_frame(report: bytes) -> bool:
    """音乐 ACK / 短 ACK 帧：只计数不逐条记录。"""
    if len(report) < 2 or report[0] != 0x55:
        return False
    cmd = report[1]
    if cmd == _QUIET_ACK_CMD:
        return True
    if cmd in _NOTIFY_CMDS:
        return False
    return len(report) <= 10


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
                    _rx_log.note(("nonproto",), "HID RX 非协议帧",
                                 sample=r, extra=f"len={len(r)}")
                    continue
                if r[1] != (cmd & 0xFF):
                    _rx_log.note(("other", r[1]), "HID RX 其它命令",
                                 sample=r, extra=f"cmd=0x{r[1]:02X} len={len(r)}")
                    continue
                if expect_addr is not None:
                    addr = r[3] | (r[4] << 8)
                    if addr != expect_addr:
                        _rx_log.note(("addr", r[1]), "HID RX 地址不匹配", sample=r,
                                     extra=f"cmd=0x{r[1]:02X} got={addr} want={expect_addr}")
                        continue
                log.debug("HID RX cmd=0x%02X len=%d", cmd, len(r))
                return r
        log.warning("HID 超时 cmd=0x%02X timeout=%.3fs retries=%d", cmd, timeout, retries)
        return None

    def read_event(self, timeout: float = 0.05) -> Optional[bytes]:
        """读取一条非请求响应（通知帧 / 异步 ACK），原样返回 payload。

        高频回包（音乐 ACK / 短 ACK）不逐条写日志；其它通知按 cmd 聚合并限速，
        避免 66fps 播放时每秒数百条 DEBUG 拖慢磁盘。
        """
        r = self.iface.read_normalized(timeout)
        if r is None:
            return None
        if not _is_quiet_frame(r):
            if len(r) >= 2 and r[0] == 0x55:
                _rx_log.note(("notify", r[1]), "HID 通知帧", sample=r,
                             extra=f"cmd=0x{r[1]:02X} len={len(r)}")
            else:
                _rx_log.note(("raw",), "HID 通知帧", sample=r, extra=f"len={len(r)}")
        return r
