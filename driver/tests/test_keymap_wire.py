#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改键 wire 格式兼容回归测试（不连真机）。

覆盖 v0.1.3 实测 bug：前端 toWireAction 曾发内部别名 key/fn/combo keys[]，
后端 encode_entry 只认 keyboard/func/combo mods+key → MK87Error → HTTP 400。
这里验证别名与 canonical 编码逐字节等价，并走一遍 patch_matrix 的读-改-写。

运行：python -m unittest discover -s tests -q
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import const, keymap  # noqa: E402
from mk87lib.errors import MK87Error  # noqa: E402


class _FakeDevice:
    """最小 fake：按 CMD 存取 512 字节矩阵，记录写入（模拟读-改-写与回读校验）。"""

    def __init__(self) -> None:
        self.matrices = {
            const.CMD["GET_KEY"]: bytearray(keymap.MATRIX_LEN),
            const.CMD["GET_FN_KEY"]: bytearray(keymap.MATRIX_LEN),
        }
        self.writes = []

    def request(self, cmd, payload=b"", **kwargs):
        if cmd == const.CMD["SET_KEY"]:
            self.writes.append(("normal", bytes(payload)))
            self.matrices[const.CMD["GET_KEY"]][:] = bytes(payload)
            return b""
        if cmd == const.CMD["SET_FN_KEY"]:
            self.writes.append(("fn", bytes(payload)))
            self.matrices[const.CMD["GET_FN_KEY"]][:] = bytes(payload)
            return b""
        if cmd == const.CMD["GET_KEY"]:
            return bytes(self.matrices[const.CMD["GET_KEY"]])
        if cmd == const.CMD["GET_FN_KEY"]:
            return bytes(self.matrices[const.CMD["GET_FN_KEY"]])
        raise AssertionError(f"fake device 收到意外指令: {cmd}")

    def matrix(self, layer: str = "normal") -> bytes:
        cmd = const.CMD["GET_KEY"] if layer == "normal" else const.CMD["GET_FN_KEY"]
        return bytes(self.matrices[cmd])


class TestEncodeAliases(unittest.TestCase):
    """前端内部别名与 canonical 字段必须编出相同 4 字节。"""

    def assert_encodes(self, action: dict, want: str) -> None:
        self.assertEqual(keymap.encode_entry(action).hex(), want, msg=str(action))

    def test_key_alias(self):
        self.assert_encodes({"type": "key", "usage": 4}, "02000400")
        self.assert_encodes({"type": "keyboard", "value": 4}, "02000400")
        # value 优先；usage / keyCode 只是兜底
        self.assert_encodes({"type": "key", "value": 4, "usage": 104}, "02000400")
        self.assert_encodes({"type": "key", "keyCode": 104}, "02006800")

    def test_fn_alias(self):
        self.assert_encodes({"type": "fn", "id": 12}, "0d00000c")
        self.assert_encodes({"type": "func", "value": 12}, "0d00000c")
        self.assert_encodes({"type": "fn", "value": 234, "id": 12}, "0d0000ea")

    def test_combo_alias(self):
        self.assert_encodes({"type": "combo", "keys": [0xE0, 4]}, "07e00004")
        self.assert_encodes({"type": "combo", "mods": [0xE0], "key": 4}, "07e00004")
        self.assert_encodes({"type": "combo", "keys": [0xE1, 0xE4]}, "07e1e400")
        self.assert_encodes({"type": "combo", "mods": [0xE1, 0xE4], "key": 0}, "07e1e400")

    def test_consumer_alias(self):
        self.assert_encodes({"type": "consumer", "usage": 233}, "03e90000")
        self.assert_encodes({"type": "consumer", "value": 233}, "03e90000")
        self.assert_encodes({"type": "consumer", "value": 404}, "03940100")

    def test_macro_internal_alias(self):
        # 宏页面内部模型：slot / mask / count；slot 可回退 value/param1
        self.assert_encodes({"type": "macro", "slot": 6, "mask": 1, "count": 3}, "06060103")
        self.assert_encodes({"type": "macro", "value": 6, "repeat": 1, "count": 3}, "06060103")
        self.assert_encodes({"type": "macro", "param1": 6, "repeat": 1, "count": 3}, "06060103")
        self.assert_encodes({"type": "macro", "slot": 0}, "06000000")

    def test_canonical_bytes_unchanged(self):
        # 改动前 test_offline 已固定的向量，这里再钉一遍，防止兼容层改坏 default 默认档
        vectors = [
            ({"type": "default"}, "00000000"),
            ({"type": "keyboard", "value": 104}, "02006800"),
            ({"type": "combo", "mods": [224], "key": 6}, "07e00006"),
            ({"type": "consumer", "value": 404}, "03940100"),
            ({"type": "func", "value": 234}, "0d0000ea"),
            ({"type": "mouse", "param1": 3, "value": 255}, "0103ff00"),
            ({"type": "macro", "slot": 6, "mask": 1, "count": 3}, "06060103"),
        ]
        for action, want in vectors:
            self.assert_encodes(action, want)


class TestComboKeySplit(unittest.TestCase):
    def test_two_modifiers_have_no_main_key(self):
        raw = keymap.encode_entry({"type": "combo", "keys": [0xE1, 0xE4]})
        self.assertEqual(raw.hex(), "07e1e400")
        decoded = keymap.decode_entry(raw)
        self.assertEqual(decoded["mods"], [0xE1, 0xE4])
        self.assertEqual(decoded["key"], 0)

    def test_modifier_plus_main_key(self):
        raw = keymap.encode_entry({"type": "combo", "keys": [0xE0, 0x04]})
        self.assertEqual(raw.hex(), "07e00004")
        decoded = keymap.decode_entry(raw)
        self.assertEqual(decoded["mods"], [0xE0])
        self.assertEqual(decoded["key"], 0x04)

    def test_more_than_two_modifiers_keeps_first_two(self):
        raw = keymap.encode_entry({"type": "combo", "keys": [0xE0, 0xE1, 0xE2, 0x04]})
        self.assertEqual(raw.hex(), "07e0e104")

    def test_main_key_is_last_non_modifier(self):
        raw = keymap.encode_entry({"type": "combo", "keys": [0xE0, 0x04, 0x05]})
        self.assertEqual(raw.hex(), "07e00005")


class TestPatchMatrixWireCompat(unittest.TestCase):
    def setUp(self) -> None:
        self.dev = _FakeDevice()

    def test_key_alias_patch_writes_matrix(self):
        res = keymap.patch_matrix(self.dev, "normal", {0: {"type": "key", "usage": 4}})
        self.assertTrue(res["ok"])
        matrix = self.dev.matrix("normal")
        self.assertEqual(len(matrix), keymap.MATRIX_LEN)
        self.assertEqual(matrix[0:4].hex(), "02000400")
        self.assertEqual(matrix[4:8].hex(), "00000000", "未 patch 的槽必须保持原值")
        self.assertEqual(len(self.dev.writes), 1)
        self.assertEqual(self.dev.writes[0][0], "normal")

    def test_fn_alias_patch_writes_matrix(self):
        slot = 12
        res = keymap.patch_matrix(self.dev, "normal", {slot: {"type": "fn", "id": 12}})
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.matrix("normal")[slot * 4:slot * 4 + 4].hex(), "0d00000c")

    def test_combo_keys_patch_writes_matrix(self):
        slot = 33
        res = keymap.patch_matrix(self.dev, "normal", {slot: {"type": "combo", "keys": [0xE0, 0x04]}})
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.matrix("normal")[slot * 4:slot * 4 + 4].hex(), "07e00004")

    def test_fn_layer_patch_uses_fn_command(self):
        res = keymap.patch_matrix(self.dev, "fn", {0: {"type": "key", "usage": 4}})
        self.assertTrue(res["ok"])
        self.assertEqual(self.dev.writes[0][0], "fn")
        self.assertEqual(self.dev.matrix("fn")[0:4].hex(), "02000400")
        self.assertEqual(self.dev.matrix("normal")[0:4].hex(), "00000000", "FN 层写入不能碰主层")

    def test_unknown_type_still_raises(self):
        with self.assertRaises(MK87Error):
            keymap.encode_entry({"type": "not-a-real-type"})
        with self.assertRaises(MK87Error):
            keymap.patch_matrix(self.dev, "normal", {0: {"type": "not-a-real-type"}})
        self.assertEqual(self.dev.writes, [], "编码失败时不得写设备")


if __name__ == "__main__":
    unittest.main(verbosity=2)
