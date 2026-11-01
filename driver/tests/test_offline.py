#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线单元测试（不需要设备）：改键/宏/灯效帧/TFT 载荷编解码。

运行： python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import keymap, lighting, macro, tft  # noqa: E402


class TestKeymap(unittest.TestCase):
    def test_fixed_vectors(self):
        # 与官方 pX 逐字节一致（scripts/keymap.js 自检向量）
        cases = [
            ({"type": "default"}, "00000000"),
            ({"type": "keyboard", "value": 4}, "02000400"),
            ({"type": "keyboard", "value": 104}, "02006800"),
            ({"type": "combo", "mods": [224], "key": 6}, "07e00006"),
            ({"type": "consumer", "value": 233}, "03e90000"),
            ({"type": "consumer", "value": 404}, "03940100"),
            ({"type": "macro", "slot": 0}, "06000000"),
            ({"type": "macro", "slot": 6, "mask": 1, "count": 3}, "06060103"),
            ({"type": "func", "value": 234}, "0d0000ea"),
            ({"type": "func", "value": 292}, "0d000124"),
            ({"type": "funcV2", "keyType": 2, "value": 4096}, "90000000"),
            ({"type": "funcV2", "keyType": 1, "value": 28682}, "8000700a"),
            ({"type": "mouse", "param1": 1, "value": 1}, "01010100"),
            ({"type": "mouse", "param1": 3, "value": 255}, "0103ff00"),
        ]
        for action, want in cases:
            self.assertEqual(keymap.encode_entry(action).hex(), want, msg=str(action))

    def test_decode_names(self):
        self.assertEqual(keymap.decode_entry(bytes.fromhex("02000400"))["name"], "A")
        self.assertEqual(keymap.decode_entry(bytes.fromhex("03e90000"))["name"], "音量 +")
        self.assertEqual(keymap.decode_entry(bytes.fromhex("0d0000ea"))["name"], "CTRL+C")
        d = keymap.decode_entry(bytes.fromhex("06060103"))
        self.assertEqual((d["type"], d["slot"], d["mask"], d["count"]), ("macro", 6, 1, 3))
        self.assertEqual(keymap.decode_entry(bytes.fromhex("00000000"))["type"], "default")

    def test_matrix_roundtrip(self):
        actions = {
            0: {"type": "keyboard", "value": 104},
            33: {"type": "combo", "mods": [224], "key": 6},
            34: {"type": "consumer", "value": 233},
            35: {"type": "macro", "slot": 0},
            41: {"type": "func", "value": 234},
            85: {"type": "funcV2", "keyType": 1, "value": 12290},
        }
        buf = keymap.encode_matrix(actions)
        self.assertEqual(len(buf), 512)
        decoded = keymap.decode_matrix(buf)
        again = {d["slot"]: d for d in decoded if d["type"] != "default"}
        self.assertEqual(sorted(again), sorted(actions))
        for slot, action in actions.items():
            self.assertEqual(again[slot]["type"], action["type"])

    def test_layout_87_keys(self):
        layout = keymap.get_layout()["layout"]
        slots = [k["slot"] for row in layout["rows"] for k in row]
        self.assertEqual(len(slots), 87)
        self.assertEqual(len(set(slots)), 87)


class TestMacro(unittest.TestCase):
    def test_encode_abc(self):
        acts = []
        for usage in (0x04, 0x05, 0x06):
            acts.append({"delay": 10, "usage": usage, "press": True})
            acts.append({"delay": 10, "usage": usage, "press": False})
        table, data = macro.encode_macros([{"slot": 0, "actions": acts}])
        self.assertEqual(table[:4].hex(), "90010000")  # 400 = 0x190
        self.assertEqual(data[:4].hex(), "0c000000")    # 6 个动作 × 2
        self.assertEqual(data[4:8].hex(), "0a0004b0")
        self.assertEqual(data[8:12].hex(), "0a000430")
        self.assertEqual(len(data), 28)

    def test_decode_block(self):
        table, data = macro.encode_macros([
            {"slot": 3, "actions": [
                {"delay": 100, "usage": 0x04, "press": True},
                {"delay": 50, "usage": 0x04, "press": False},
            ]}
        ])
        self.assertEqual(int.from_bytes(table[12:16], "little"), 400)
        acts = macro.decode_block(data[:4], data[4:12])
        self.assertEqual(len(acts), 2)
        self.assertEqual(acts[0]["delay"], 100)
        self.assertTrue(acts[0]["press"])
        self.assertFalse(acts[1]["press"])
        self.assertEqual(acts[0]["actionType"], 3)

    def test_capacity_guard(self):
        # 230 个动作 ≈ 920B，仍在 2672B 内 → 通过
        big = [{"delay": 1, "usage": 4, "press": True}] * 230
        table, data = macro.encode_macros([{"slot": 0, "actions": big}])
        self.assertLess(len(data), 2672)


class TestLighting(unittest.TestCase):
    def test_key_order_87(self):
        order = lighting.key_order()
        self.assertEqual(len(order), 87)
        self.assertEqual(order[0], 0)  # Esc

    def test_frame_payload(self):
        colors = {0: (255, 0, 0), 83: (0, 255, 0)}
        payload = lighting.build_frame_payload(colors)
        self.assertEqual(len(payload), 348)
        self.assertEqual(payload[:4], bytes([0, 255, 0, 0]))
        idx = lighting.key_order().index(83) * 4
        self.assertEqual(payload[idx:idx + 4], bytes([83, 0, 255, 0]))

    def test_frame_packets(self):
        payload = bytes(348)
        pkts = lighting.build_frame_packets(payload, 64, frame_index=7)
        self.assertEqual(len(pkts), 7)
        first = pkts[0]
        self.assertEqual(len(first), 65)
        self.assertEqual(first[0], 0)          # report ID
        self.assertEqual(first[1], 0xAA)
        self.assertEqual(first[2], 0x32)
        self.assertEqual(first[3], 56)         # 本包数据长
        self.assertEqual(first[6], 7)          # frame index
        self.assertEqual(first[7], 0)          # last
        self.assertEqual(first[9:13], payload[:4])
        last = pkts[-1]
        self.assertEqual(last[3], 348 - 6 * 56)  # 12 字节
        self.assertEqual(last[7], 1)
        self.assertEqual(last[4] | (last[5] << 8), 6 * 56)

    def test_clamp(self):
        self.assertEqual(lighting.clamp_brightness(0), 1)
        self.assertEqual(lighting.clamp_brightness(9), 6)
        self.assertEqual(lighting.clamp_speed(9), 6)


class TestTft(unittest.TestCase):
    def test_animation_blob(self):
        delays = [10, 10, 10]
        data = b"\x00" * (tft.FRAME_BYTES * 3)
        blob = tft.build_animation_blob(delays, data)
        self.assertEqual(len(blob), 256 + len(data))
        self.assertEqual(blob[0], 3)                 # 帧数
        self.assertEqual(blob[1], min(10 * 5, 255))  # 50
        self.assertEqual(blob[2], min(10 * 5, 255))
        self.assertEqual(blob[3], 0)                 # 终止符（顶掉最后一帧延时槽）

    def test_frame_bytes(self):
        self.assertEqual(tft.FRAME_BYTES, 240 * 135 * 2)
        self.assertEqual(tft.WIDTH, 240)
        self.assertEqual(tft.HEIGHT, 135)


class TestBackupValidate(unittest.TestCase):
    def test_reject_bad(self):
        from mk87lib import backup as backup_mod
        with self.assertRaises(ValueError):
            backup_mod.validate({"format": "nope"})
        with self.assertRaises(ValueError):
            backup_mod.validate({"format": "mk87-backup", "version": 1,
                                 "keyMatrix": "00" * 10})


if __name__ == "__main__":
    unittest.main(verbosity=2)
