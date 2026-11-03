# -*- coding: utf-8 -*-
"""宏表读取健壮性：坏目录快速失败（不拿垃圾偏移读设备）+ 会话日志 handler 重开。"""
import logging
import os
import tempfile
import types
import unittest
from unittest import mock

from mk87lib import logsetup, macro
from mk87lib.errors import ProtocolTimeout

DIR_SIZE = macro.DIR_SIZE
DATA_START = macro.DATA_START
CAP = 3072


class _FakeMacroDevice:
    """按 addr 返回目录/数据区内容的假设备；记录所有请求便于断言。"""

    def __init__(self, table: bytes, data: bytes, capacity: int = CAP):
        self.table = bytes(table).ljust(DIR_SIZE, b"\x00")[:DIR_SIZE]
        self.data = bytes(data)
        self.status = types.SimpleNamespace(macro_space=capacity)
        self.requests = []

    def request(self, cmd, payload=b"", content_size=None, addr_start=0,
                timeout=1.0, retries=2, need_response=True):
        size = int(content_size or 0)
        self.requests.append({"cmd": cmd, "addr": int(addr_start), "size": size})
        out = bytearray()
        for addr in range(int(addr_start), int(addr_start) + size):
            if addr < DATA_START:
                out.append(self.table[addr] if addr < len(self.table) else 0)
            else:
                idx = addr - DATA_START
                out.append(self.data[idx] if 0 <= idx < len(self.data) else 0)
        return bytes(out)


def _dir(offsets):
    buf = bytearray(DIR_SIZE)
    for slot, off in offsets.items():
        buf[slot * 4:slot * 4 + 4] = int(off).to_bytes(4, "little")
    return bytes(buf)


def _block(actions):
    """actions: [(delay, usage, flags)] → 宏块字节（count + 动作）。"""
    block = bytearray(4)
    n = len(actions)
    block[0] = (n * 2) & 0xFF
    block[1] = ((n * 2) >> 8) & 0xFF
    for delay, usage, flags in actions:
        block += bytes([delay & 0xFF, (delay >> 8) & 0xFF, usage & 0xFF, flags])
    return bytes(block)


class TestMacroCorruptDirectory(unittest.TestCase):
    def test_garbage_directory_returns_empty_without_device_reads(self):
        # fw1.19 实测坏目录：像宏动作数据的 u32（不是合法块偏移）
        garbage = _dir({i: v for i, v in enumerate([
            0x3200FF47, 0xA300FF48, 0xF200FF49, 0xFF00DC4A, 0x4B, 0x5A,
            0xF5FF50, 0xEAFF51] + [0xFFFFFFFF] * 11)})
        dev = _FakeMacroDevice(garbage, b"")
        payload = macro.read_all_macros(dev)
        self.assertEqual(payload["slots"], [], "坏目录不应解析出任何槽")
        self.assertTrue(payload["corruptDirectory"])
        self.assertEqual(len(payload["invalidSlots"]), 19)
        # 只允许读 400B 目录一次；绝不能拿垃圾偏移去读数据区
        self.assertEqual(len(dev.requests), 1, f"坏目录不应继续读设备: {dev.requests}")
        self.assertEqual(dev.requests[0]["size"], DIR_SIZE)
        self.assertEqual(dev.requests[0]["addr"], 0)

    def test_valid_directory_bulk_read_still_works(self):
        block = _block([(10, 0x04, 0xB0), (10, 0x04, 0x30)])
        dev = _FakeMacroDevice(_dir({0: DATA_START}), block)
        payload = macro.read_all_macros(dev)
        self.assertEqual(len(payload["slots"]), 1)
        self.assertEqual(payload["slots"][0]["slot"], 0)
        self.assertEqual(len(payload["slots"][0]["actions"]), 2)
        self.assertNotIn("corruptDirectory", payload)
        self.assertLessEqual(len(dev.requests), 8, f"应为目录+批量数据区读取: {dev.requests}")
        for req in dev.requests:
            self.assertLessEqual(req["addr"], CAP, f"读取地址越界: {req}")

    def test_mixed_directory_keeps_valid_slots_only(self):
        block = _block([(10, 0x04, 0xB0)])
        dev = _FakeMacroDevice(_dir({0: DATA_START, 1: 0x3200FF47, 2: 0xAAAA}), block)
        payload = macro.read_all_macros(dev)
        self.assertEqual([s["slot"] for s in payload["slots"]], [0])
        self.assertTrue(payload["corruptDirectory"])
        self.assertEqual(len(payload["invalidSlots"]), 2)

    def test_corrupt_directory_no_giant_reads_even_on_fallback(self):
        garbage = _dir({0: 0x3200FF47, 1: 0x8B8D})
        dev = _FakeMacroDevice(garbage, b"")
        with mock.patch.object(macro, "_read_region", side_effect=ProtocolTimeout("boom")):
            payload = macro.read_all_macros(dev)
        self.assertEqual(payload["slots"], [])
        for req in dev.requests:
            self.assertLessEqual(req["size"], DIR_SIZE, f"回退路径也不该大读: {req}")

    def test_valid_directory_but_region_timeout_falls_back_bounded(self):
        block = _block([(10, 0x04, 0xB0)])
        dev = _FakeMacroDevice(_dir({0: DATA_START}), block)
        with mock.patch.object(macro, "_read_region", side_effect=ProtocolTimeout("boom")):
            payload = macro.read_all_macros(dev)
        self.assertEqual(len(payload["slots"]), 1)
        self.assertEqual(len(payload["slots"][0]["actions"]), 1)
        # 第一条是 400B 目录读，之后的逐槽回退只能读 4B 块头（防坏块头大读）
        for req in dev.requests[1:]:
            self.assertLessEqual(req["size"], 4, f"逐槽回退只读块头: {req}")


class TestSessionHandlerReopen(unittest.TestCase):
    def test_emit_reopens_closed_stream(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "session-test.log")
            handler = logsetup._SessionFileHandler(path, max_bytes=1 << 20)
            handler.setFormatter(logsetup._fmt())
            handler.close()  # 模拟被第三方 dictConfig 关掉（stream=None）
            self.assertIsNone(handler.stream)
            handler.emit(logging.LogRecord("t", logging.INFO, __file__, 1,
                                           "hello after reopen", (), None))
            handler.close()
            with open(path, encoding="utf-8") as f:
                self.assertIn("hello after reopen", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
