#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""性能 / 日志治理回归测试（不连接真机）。

覆盖：
* HID 通知帧 / 干扰帧的 DEBUG 限流（5000 条洪水 → 少量摘要）；
* 音乐 ACK 帧完全不逐条记录，HID 超时 warning 不丢；
* 会话日志 32MB 上限（测试注入小上限）与会话日志启动清理；
* 宏表批量读取 vs 旧逐槽读取（请求数、返回值一致、失败回退）。

运行：python -m unittest discover -s tests -q
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import const, logsetup, macro, protocol  # noqa: E402
from mk87lib.errors import ProtocolTimeout  # noqa: E402


# ======================================================================
# fake HID / protocol
# ======================================================================
class _RepeatIface:
    """read_normalized 永远返回同一帧，模拟 ACK/通知洪水。"""

    def __init__(self, frame: bytes = b"", payload_len: int = 64) -> None:
        self.info = SimpleNamespace(payload_len=payload_len)
        self.frame = bytes(frame)
        self.writes = []

    def write_report(self, report: bytes) -> int:
        self.writes.append(bytes(report))
        return len(report)

    def read_normalized(self, timeout: float = 0.1):
        return self.frame

    def read_normalized_nonblocking(self):
        # 监听线程用非阻塞读；fake 复用固定帧逻辑
        return self.read_normalized(0)


class _QueueIface(_RepeatIface):
    """按顺序返回队列中的帧，用完后返回 None。"""

    def __init__(self, frames, payload_len: int = 64) -> None:
        super().__init__(b"", payload_len)
        self.frames = list(frames)

    def read_normalized(self, timeout: float = 0.1):
        return self.frames.pop(0) if self.frames else None


class TestProtocolLogThrottle(unittest.TestCase):
    def setUp(self) -> None:
        protocol.reset_rate_limits()

    def tearDown(self) -> None:
        protocol.reset_rate_limits()

    def test_5000_notification_frames_produce_few_debug_lines(self):
        frame = bytes([0x55, 0xFA]) + bytes(range(30))
        p = protocol.Protocol(_RepeatIface(frame))
        with self.assertLogs("mk87.protocol", level="DEBUG") as cap:
            for _ in range(5000):
                self.assertEqual(p.read_event(0), frame)
            protocol.flush_rate_limits()  # 把剩余计数汇总成一条，便于断言累计值
        self.assertLessEqual(len(cap.records), 20)
        text = "\n".join(r.getMessage() for r in cap.records)
        self.assertIn("聚合", text)
        self.assertIn("0xFA", text)
        self.assertIn("累计=5000", text)
        self.assertIn("last=", text)

    def test_music_ack_frames_are_not_logged(self):
        frame = b"\x55\x32" + bytes(62)  # 音乐 ACK 类帧
        p = protocol.Protocol(_RepeatIface(frame))
        with self.assertNoLogs("mk87.protocol", level="DEBUG"):
            for _ in range(5000):
                self.assertEqual(p.read_event(0), frame)

    def test_short_ack_frames_are_not_logged(self):
        frame = b"\x55\x41" + bytes(7)  # 短 ACK（≤10 字节）
        p = protocol.Protocol(_RepeatIface(frame))
        with self.assertNoLogs("mk87.protocol", level="DEBUG"):
            for _ in range(1000):
                p.read_event(0)

    def test_transact_other_cmd_noise_limited_but_warning_kept(self):
        frame = bytes([0x55, 0x33]) + bytes(40)  # 与请求 cmd 不匹配
        p = protocol.Protocol(_RepeatIface(frame))
        pkt = p.build_packet(0x10, 0, 0)
        with self.assertLogs("mk87.protocol", level="DEBUG") as cap:
            for _ in range(5):
                self.assertIsNone(p._transact(pkt, 0x10, 0.01, 0, None))
        msgs = [r.getMessage() for r in cap.records]
        self.assertLessEqual(len(msgs), 20)
        self.assertTrue(any("HID 超时" in m for m in msgs), msgs)
        self.assertTrue(any("HID RX 其它命令 聚合" in m for m in msgs), msgs)

    def test_transact_non_protocol_and_addr_mismatch_limited(self):
        # 非协议帧洪水
        p = protocol.Protocol(_RepeatIface(b"\x00" * 64))
        pkt = p.build_packet(0x10, 0, 0)
        with self.assertLogs("mk87.protocol", level="DEBUG") as cap:
            self.assertIsNone(p._transact(pkt, 0x10, 0.01, 0, None))
        msgs = [r.getMessage() for r in cap.records]
        self.assertLessEqual(len(msgs), 20)
        self.assertTrue(any("HID RX 非协议帧 聚合" in m for m in msgs), msgs)
        self.assertTrue(any("HID 超时" in m for m in msgs), msgs)

        # 地址不匹配洪水（cmd 匹配、addr 不匹配）
        protocol.reset_rate_limits()
        frame = bytes([0x55, 0x10, 0, 7, 0, 0, 0, 0]) + bytes(56)
        p2 = protocol.Protocol(_RepeatIface(frame))
        with self.assertLogs("mk87.protocol", level="DEBUG") as cap2:
            self.assertIsNone(p2._transact(pkt, 0x10, 0.01, 0, 9))
        msgs2 = [r.getMessage() for r in cap2.records]
        self.assertLessEqual(len(msgs2), 20)
        self.assertTrue(any("HID RX 地址不匹配 聚合" in m for m in msgs2), msgs2)
        self.assertTrue(any("want=9" in m for m in msgs2), msgs2)

    def test_successful_request_response_kept_per_line(self):
        resp = bytes([0x55, 0x10, 0, 0, 0, 0, 0, 0]) + bytes(56)
        p = protocol.Protocol(_QueueIface([resp]))
        with self.assertLogs("mk87.protocol", level="DEBUG") as cap:
            got = p._transact(p.build_packet(0x10, 0, 0), 0x10, 0.1, 0, None)
        self.assertEqual(got, resp)
        msgs = [r.getMessage() for r in cap.records]
        self.assertTrue(any(m.startswith("HID TX cmd=0x10") for m in msgs), msgs)
        self.assertTrue(any(m.startswith("HID RX cmd=0x10") for m in msgs), msgs)


# ======================================================================
# 会话日志上限 / 清理
# ======================================================================
def _write_bytes(path: str, size: int) -> None:
    with open(path, "wb") as f:
        f.write(b"x" * size)


class TestSessionLogCleanup(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mk87-logclean-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_sessions(self, count: int, size: int = 1024) -> list:
        base = 1_700_000_000
        paths = []
        for i in range(count):
            p = os.path.join(self.tmp, f"session-2026010{i}-0000-1.log")
            _write_bytes(p, size)
            os.utime(p, (base + i, base + i))  # i 越大越新
            paths.append(p)
        return paths

    def test_keeps_five_newest_and_never_touches_main_logs(self):
        paths = self._seed_sessions(7)
        main = os.path.join(self.tmp, "mk87.log")
        err = os.path.join(self.tmp, "errors.log")
        other = os.path.join(self.tmp, "notes.txt")
        _write_bytes(main, 64)
        _write_bytes(err, 64)
        _write_bytes(other, 64)

        res = logsetup.cleanup_session_logs(
            self.tmp, keep=5, total_max=10 * 1024 * 1024)
        self.assertEqual(len(res["removed"]), 2)
        self.assertEqual(res["kept"], 5)
        remaining = [n for n in os.listdir(self.tmp) if n.startswith("session-")]
        self.assertEqual(len(remaining), 5)
        # 最旧的两个被删除，最新的 5 个保留
        self.assertFalse(os.path.exists(paths[0]))
        self.assertFalse(os.path.exists(paths[1]))
        for p in paths[2:]:
            self.assertTrue(os.path.exists(p))
        for keep in (main, err, other):
            self.assertTrue(os.path.isfile(keep))

    def test_enforces_total_size_budget(self):
        self._seed_sessions(5)
        res = logsetup.cleanup_session_logs(self.tmp, keep=5, total_max=2500)
        self.assertLessEqual(res["kept"], 2)
        self.assertLessEqual(res["totalBytes"], 2500)
        remaining = [n for n in os.listdir(self.tmp) if n.startswith("session-")]
        self.assertLessEqual(len(remaining), 2)
        self.assertLessEqual(sum(os.path.getsize(os.path.join(self.tmp, n))
                                 for n in remaining), 2500)

    def test_excluded_current_session_is_protected(self):
        paths = self._seed_sessions(3, size=2048)
        current = paths[0]  # 即使最旧也不会被删
        res = logsetup.cleanup_session_logs(
            self.tmp, keep=2, total_max=10 * 1024 * 1024, exclude=current)
        self.assertTrue(os.path.exists(current))
        self.assertEqual(res["kept"], 2)
        self.assertIn(os.path.basename(current), res["keptNames"])


class TestSessionSizeCap(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mk87-logcap-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_handler_stops_writing_after_cap(self):
        path = os.path.join(self.tmp, "session-cap.log")
        handler = logsetup._SessionFileHandler(path, max_bytes=2048)
        logger = logging.getLogger("mk87.test.sessioncap")
        old_handlers, old_propagate, old_level = (
            list(logger.handlers), logger.propagate, logger.level)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        try:
            with self.assertLogs("mk87", level="WARNING") as cap:
                for _ in range(100):
                    logger.debug("%s", "x" * 100)
            self.assertTrue(handler.capped)
            size1 = os.path.getsize(path)
            # 上限 + 终止标记（标记长度另算，但只写一次）
            self.assertLessEqual(size1, 2048 + 512)
            self.assertTrue(any("会话日志达到上限" in r.getMessage()
                                for r in cap.records), [r.getMessage() for r in cap.records])

            for _ in range(100):
                logger.debug("after cap %s", "y" * 100)
            self.assertEqual(os.path.getsize(path), size1, "达到上限后文件不应再增长")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("已停止写入", text)
            self.assertEqual(text.count("已停止写入"), 1, "终止标记只能写一次")
        finally:
            logger.handlers = old_handlers
            logger.propagate = old_propagate
            logger.setLevel(old_level)
            handler.close()


class TestSetupLoggingCleanup(unittest.TestCase):
    """setup_logging 启动时清理旧会话日志，并记录上限/清理结果。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mk87-setupclean-")
        self._old_env = os.environ.get("MK87_LOG_DIR")
        os.environ["MK87_LOG_DIR"] = self.tmp
        logsetup._installed = False
        self._old_handlers = list(logging.getLogger().handlers)

    def tearDown(self) -> None:
        root = logging.getLogger()
        for h in list(root.handlers):
            if h not in self._old_handlers:
                root.removeHandler(h)
                try:
                    h.close()
                except Exception:  # noqa: BLE001
                    pass
        for h in self._old_handlers:
            root.addHandler(h)
        logsetup._installed = False
        if self._old_env is None:
            os.environ.pop("MK87_LOG_DIR", None)
        else:
            os.environ["MK87_LOG_DIR"] = self._old_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_prunes_and_logs_limits(self):
        base = 1_700_000_000
        for i in range(7):
            p = os.path.join(self.tmp, f"session-2025010{i}-0000-1.log")
            _write_bytes(p, 1024)
            os.utime(p, (base + i, base + i))

        st = logsetup.setup_logging(console=False, role="test")
        names = [f["name"] for f in logsetup.list_logs()
                 if f["name"].startswith("session-")]
        self.assertLessEqual(len(names), logsetup.SESSION_KEEP_FILES)
        self.assertIn(os.path.basename(st["session"]), names)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "mk87.log")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "errors.log")))
        with open(st["session"], encoding="utf-8") as f:
            text = f.read()
        self.assertIn("会话上限=32.0MB", text)
        self.assertIn("清理旧会话", text)

    def test_export_still_works_after_session_cap(self):
        st = logsetup.setup_logging(
            console=False, role="test", session_max_bytes=1024)
        log = logging.getLogger("mk87.test.exportcap")
        for _ in range(100):
            log.debug("%s", "z" * 100)
        res = logsetup.export_logs()
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.isfile(res["path"]))
        self.assertGreaterEqual(res["files"], 1)
        self.assertIn(os.path.basename(st["session"]),
                      [f["name"] for f in logsetup.list_logs()])


# ======================================================================
# 宏表批量读取
# ======================================================================
class _FakeMacroDevice:
    """按逻辑地址空间返回宏区镜像；记录每次 request(addr, size)。"""

    def __init__(self, image: bytes, macro_space=None, fail_region: bool = False) -> None:
        self.image = bytes(image)
        self.status = SimpleNamespace(
            macro_space=len(self.image) if macro_space is None else macro_space)
        self.calls = []
        self.fail_region = fail_region

    def request(self, cmd, payload=b"", content_size=None, timeout=0.5, retries=2,
                addr_start=0, need_response=True):
        n = int(content_size or 0)
        self.calls.append((int(addr_start), n))
        if self.fail_region and int(addr_start) >= macro.DATA_START and n > macro.DIR_SIZE:
            raise ProtocolTimeout("模拟宏数据区批量读超时")
        data = self.image[int(addr_start):int(addr_start) + n]
        return data + b"\x00" * (n - len(data))


def _macro_image() -> tuple:
    """构造 10 个已用槽位的宏区镜像（目录 + 数据 + 零填充）。"""
    raw = []
    for i, slot in enumerate([0, 2, 5, 9, 17, 23, 30, 44, 61, 88]):
        acts = [{"delay": i * 10 + j, "usage": 4 + (j % 20), "press": bool(j % 2)}
                for j in range(i + 1)]
        raw.append({"slot": slot, "actions": acts})
    table, data = macro.encode_macros(raw)
    image = bytes(table) + bytes(data)
    image += bytes(max(0, const.MACRO_SPACE - len(image)))
    return image, len(raw)


class TestMacroBatchRead(unittest.TestCase):
    def test_batch_matches_legacy_with_fewer_requests(self):
        image, used_slots = _macro_image()
        batch_dev = _FakeMacroDevice(image)
        got = macro.read_all_macros(batch_dev)

        legacy_dev = _FakeMacroDevice(image)
        expected = macro._read_all_macros_legacy(legacy_dev)
        self.assertEqual(got, expected, "批量读取结果必须与旧逐槽实现完全一致")
        self.assertEqual(len(got["slots"]), used_slots)

        batch_calls = len(batch_dev.calls)
        legacy_calls = len(legacy_dev.calls)
        self.assertLessEqual(batch_calls, 10, batch_dev.calls)
        self.assertGreaterEqual(legacy_calls, used_slots * 2, legacy_dev.calls)
        self.assertLess(batch_calls, legacy_calls)
        # 单次批量块 ≤512 字节
        for addr, size in batch_dev.calls:
            self.assertLessEqual(size, macro.MACRO_READ_CHUNK, (addr, size))

    def test_batch_respects_device_macro_space(self):
        image, _ = _macro_image()
        dev = _FakeMacroDevice(image, macro_space=2048)
        got = macro.read_all_macros(dev)
        self.assertEqual(got["capacity"], 2048)
        self.assertEqual(got["dataCapacity"], 2048 - macro.DATA_START)
        region_calls = [(a, n) for a, n in dev.calls if a >= macro.DATA_START]
        self.assertEqual(sum(n for _, n in region_calls),
                         min(2048, const.MACRO_SPACE) - macro.DATA_START)
        for _, n in region_calls:
            self.assertLessEqual(n, macro.MACRO_READ_CHUNK)

    def test_batch_failure_falls_back_to_legacy(self):
        image, _ = _macro_image()
        dev = _FakeMacroDevice(image, fail_region=True)
        with self.assertLogs("mk87.macro", level="WARNING") as cap:
            got = macro.read_all_macros(dev)
        expected = macro._read_all_macros_legacy(_FakeMacroDevice(image))
        self.assertEqual(got, expected)
        self.assertTrue(any("回退" in r.getMessage() for r in cap.records))
        self.assertTrue(any(a == macro.DATA_START and n > macro.DIR_SIZE
                            for a, n in dev.calls), dev.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
