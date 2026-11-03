# -*- coding: utf-8 -*-
"""Linux HID 接口识别：hidapi(hidraw) 不填 usage_page → 解析 report descriptor 补齐。

背景：hidapi 的 Linux hidraw 后端在 hid.enumerate() 里 usage_page/usage 恒为 0，
而本工具靠 usagePage 区分 主协议(0xFF68)/TFT(0xFF67)/2.4G(0xFF60)/唤醒(0xFFFF)。
不补齐时 Linux 上永远「未找到可用的 MK87 协议接口」。
"""
import unittest
from unittest import mock

from mk87lib import transport
from mk87lib.transport import IfaceInfo


def _iface(path, pid=0x8047, usage_page=0, usage=0):
    return IfaceInfo(path=path, vid=0x0C45, pid=pid, product="AJAZZ KEYBOARD",
                     manufacturer="SONiX", serial="", usage_page=usage_page,
                     usage=usage, interface_number=-1, payload_len=64)


def _desc(usage_page: int, usage: int = 1, trailing: bytes = b"") -> bytes:
    return bytes([0x06, usage_page & 0xFF, (usage_page >> 8) & 0xFF,
                  0x09, usage & 0xFF, 0xA1, 0x01]) + trailing


class TestDescriptorParser(unittest.TestCase):
    def test_vendor_pages(self):
        cases = [
            (0xFF68, 0x01), (0xFF67, 0x02), (0xFF60, 0x00), (0xFFFF, 0x05),
        ]
        for page, usage in cases:
            got = transport.parse_report_descriptor_usage(_desc(page, usage))
            self.assertEqual(got, (page, usage), f"0x{page:04X}")

    def test_first_page_wins_and_collection_stops(self):
        # 顶层 0xFF68 之后还有子集合 0x0000/0x0001 —— 只取第一个
        desc = _desc(0xFF68, 1, trailing=bytes([0x06, 0x00, 0xFF, 0x09, 0x01, 0xA1, 0x01]))
        self.assertEqual(transport.parse_report_descriptor_usage(desc), (0xFF68, 1))

    def test_usage_absent_and_empty(self):
        self.assertEqual(transport.parse_report_descriptor_usage(b""), (None, None))
        # 只有 Usage Page、没有 Usage
        got = transport.parse_report_descriptor_usage(bytes([0x06, 0x68, 0xFF, 0xA1, 0x01]))
        self.assertEqual(got[0], 0xFF68)

    def test_truncated_input_does_not_crash(self):
        self.assertEqual(transport.parse_report_descriptor_usage(b"\x06\x68"), (None, None))
        self.assertEqual(transport.parse_report_descriptor_usage(b"\x07"), (None, None))


class TestLinuxEnrichment(unittest.TestCase):
    def test_enrich_fills_usage_and_payload(self):
        callbacks = {
            b"/dev/hidraw1": _desc(0xFF68, 1),
            b"/dev/hidraw2": _desc(0xFF67, 2),
            b"/dev/hidraw3": _desc(0xFF60, 0),
            b"/dev/hidraw4": _desc(0xFFFF, 5),
        }
        ifaces = [
            _iface(b"/dev/hidraw1", 0x8047),
            _iface(b"/dev/hidraw2", 0x8047),
            _iface(b"/dev/hidraw3", 0xFEFE),
            _iface(b"/dev/hidraw4", 0xFEFE),
            _iface(b"/dev/hidraw5", 0x8047, usage_page=0xFF68, usage=1),  # 已知的跳过
        ]
        read = lambda info: callbacks.get(info.path)  # noqa: E731
        with mock.patch.object(transport, "_read_report_descriptor", side_effect=read) as m:
            out = transport._enrich_linux_usage(ifaces)
        self.assertEqual([i.usage_page for i in out[:4]], [0xFF68, 0xFF67, 0xFF60, 0xFFFF])
        self.assertEqual([i.payload_len for i in out[:4]], [64, 4104, 32, 4])
        self.assertEqual(out[4].usage_page, 0xFF68, "已有 usagePage 的接口保持不变")
        self.assertEqual(m.call_count, 4, "已知 usagePage 的接口不需要读 descriptor")

    def test_enrich_keeps_zero_when_descriptor_unreadable(self):
        ifaces = [_iface(b"/dev/hidraw9", 0x8047)]
        with mock.patch.object(transport, "_read_report_descriptor", return_value=None):
            out = transport._enrich_linux_usage(ifaces)
        self.assertEqual(out[0].usage_page, 0)
        self.assertEqual(out[0].payload_len, 64, "读不到时回落默认 payload")

    def test_enumerate_enriches_only_on_linux(self):
        raw = [{"path": b"/dev/hidraw1", "vendor_id": 0x0C45, "product_id": 0x8047,
                "product_string": "AJAZZ KEYBOARD", "manufacturer_string": "SONiX",
                "serial_number": "", "usage_page": 0, "usage": 0, "interface_number": 2}]
        fake_hid = mock.Mock()
        fake_hid.enumerate.return_value = raw
        with mock.patch.object(transport, "hid", fake_hid), \
                mock.patch.object(transport.platform, "system", return_value="Linux"), \
                mock.patch.object(transport, "_read_report_descriptor",
                                  return_value=_desc(0xFF68, 1)) as rd:
            out = transport.enumerate_ifaces(0x0C45)
        self.assertEqual(out[0].usage_page, 0xFF68)
        self.assertEqual(out[0].payload_len, 64)
        self.assertEqual(rd.call_count, 1)

        fake_hid.enumerate.return_value = raw
        with mock.patch.object(transport, "hid", fake_hid), \
                mock.patch.object(transport.platform, "system", return_value="Windows"), \
                mock.patch.object(transport, "_read_report_descriptor") as rd2:
            out = transport.enumerate_ifaces(0x0C45)
        self.assertEqual(out[0].usage_page, 0, "Windows 不触发 Linux 补齐")
        rd2.assert_not_called()

    def test_read_report_descriptor_uses_hidapi_first(self):
        fake_dev = mock.Mock()
        fake_dev.get_report_descriptor.return_value = list(_desc(0xFF68, 1))
        fake_hid = mock.Mock()
        fake_hid.device.return_value = fake_dev
        info = _iface(b"/dev/hidraw1")
        with mock.patch.object(transport, "hid", fake_hid):
            desc = transport._read_report_descriptor(info)
        self.assertEqual(desc, _desc(0xFF68, 1))
        fake_dev.open_path.assert_called_once_with(b"/dev/hidraw1")
        fake_dev.close.assert_called_once()

    def test_read_report_descriptor_sysfs_fallback(self):
        fake_hid = mock.Mock()
        fake_hid.device.side_effect = IOError("permission denied")
        info = _iface(b"/dev/hidraw2")
        m = mock.mock_open(read_data=_desc(0xFF67, 2))
        with mock.patch.object(transport, "hid", fake_hid), \
                mock.patch("builtins.open", m):
            desc = transport._read_report_descriptor(info)
        self.assertEqual(desc, _desc(0xFF67, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
