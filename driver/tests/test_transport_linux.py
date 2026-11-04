# -*- coding: utf-8 -*-
"""Linux HID 接口识别与后端选择。

背景（v0.1.5 → v0.1.6）：
* PyPI 的 hidapi wheel 在 Linux 上打包了两个扩展模块：
  ``hid``（libusb 后端）和 ``hidraw``（hidraw 后端）；
* ``import hid`` 拿到的是 libusb 后端：path 形如 ``1-1.1:1.0``、usage_page 恒为 0，
  Linux 上必须用 ``import hidraw``（path = /dev/hidrawN，usage_page 由 sysfs 解析）；
* 另外 hidraw 后端在少数发行版上也可能读不到 usage_page，所以保留
  report descriptor 解析 + sysfs 反查兜底。
"""
import os
import tempfile
import unittest
from unittest import mock

from mk87lib import transport
from mk87lib.transport import IfaceInfo


def _iface(path, pid=0x8047, usage_page=0, usage=0, iface=-1):
    return IfaceInfo(path=path, vid=0x0C45, pid=pid, product="AJAZZ KEYBOARD",
                     manufacturer="SONiX", serial="", usage_page=usage_page,
                     usage=usage, interface_number=iface, payload_len=64)


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


class TestBackendSelection(unittest.TestCase):
    """Linux 必须选 hidraw 后端；libusb 后端（官方 wheel 的默认 hid 模块）不可用。"""

    def test_linux_prefers_hidraw_module(self):
        real = object()
        calls = []

        def imp(name):
            calls.append(name)
            if name == "hidraw":
                return real
            raise ImportError(name)

        with mock.patch.object(transport.platform, "system", return_value="Linux"):
            mod, backend = transport._load_hid_backend(imp)
        self.assertIs(mod, real)
        self.assertEqual(backend, "hidraw")
        self.assertEqual(calls, ["hidraw"], "hidraw 命中后不应再尝试 hid")

    def test_linux_falls_back_to_libusb_when_hidraw_missing(self):
        libusb = object()

        def imp(name):
            if name == "hid":
                return libusb
            raise ImportError(name)

        with mock.patch.object(transport.platform, "system", return_value="Linux"):
            mod, backend = transport._load_hid_backend(imp)
        self.assertIs(mod, libusb)
        self.assertEqual(backend, "libusb")

    def test_missing_everything(self):
        def imp(name):
            raise ImportError(name)

        with mock.patch.object(transport.platform, "system", return_value="Linux"):
            mod, backend = transport._load_hid_backend(imp)
        self.assertIsNone(mod)
        self.assertEqual(backend, "missing")

    def test_windows_uses_native_hid(self):
        native = object()

        def imp(name):
            if name == "hid":
                return native
            raise ImportError(name)

        with mock.patch.object(transport.platform, "system", return_value="Windows"):
            mod, backend = transport._load_hid_backend(imp)
        self.assertIs(mod, native)
        self.assertEqual(backend, "native")

    def test_enumerate_rejects_libusb_backend_on_linux(self):
        with mock.patch.object(transport, "hid", mock.Mock()), \
                mock.patch.object(transport, "BACKEND", "libusb"), \
                mock.patch.object(transport.platform, "system", return_value="Linux"):
            with self.assertRaises(transport.DeviceNotFound) as ctx:
                transport.enumerate_ifaces(0x0C45)
        self.assertIn("hidraw", str(ctx.exception))


class TestInterfaceNumber(unittest.TestCase):
    def test_interface_zero_is_kept(self):
        self.assertEqual(transport._interface_number({"interface_number": 0}), 0)
        self.assertEqual(transport._interface_number({"interface_number": 3}), 3)
        self.assertEqual(transport._interface_number({"interface_number": None}), -1)
        self.assertEqual(transport._interface_number({"interface_number": "2"}), 2)
        self.assertEqual(transport._interface_number({}), -1)
        self.assertEqual(transport._interface_number(4), 4)


def _write_node(root: str, name: str, pid: int, iface: int, page: int,
                usage: int = 1, vid: int = 0x0C45) -> str:
    base = os.path.join(root, name)
    device = os.path.join(base, "device")
    os.makedirs(device, exist_ok=True)
    with open(os.path.join(device, "uevent"), "w", encoding="utf-8") as f:
        f.write(f"HID_ID=0003:{vid:08X}:{pid:08X}\nHID_NAME=AJAZZ KEYBOARD\n")
    with open(os.path.join(device, "report_descriptor"), "wb") as f:
        f.write(_desc(page, usage))
    with open(os.path.join(base, "bInterfaceNumber"), "w", encoding="utf-8") as f:
        f.write(f"{iface:02X}")
    return base


class TestSysfsFallback(unittest.TestCase):
    """libusb 后端的 path 不是 /dev/hidrawN 时，用 sysfs 反查 report descriptor。"""

    def test_parse_hid_id(self):
        self.assertEqual(transport.parse_sysfs_hid_id("HID_ID=0003:00000C45:00008047"),
                         (3, 0x0C45, 0x8047))
        self.assertEqual(transport.parse_sysfs_hid_id(""), (None, None, None))

    def test_iter_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_node(tmp, "hidraw1", 0x8047, 2, 0xFF68)
            _write_node(tmp, "hidraw5", 0x8047, 3, 0xFF67)
            names = [name for name, _dir in transport.iter_sysfs_hidraw(tmp)]
            self.assertEqual(names, ["hidraw1", "hidraw5"])

    def test_descriptor_lookup_by_pid_and_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_node(tmp, "hidraw1", 0x8047, 2, 0xFF68, 1)
            _write_node(tmp, "hidraw2", 0x8047, 3, 0xFF67, 2)
            _write_node(tmp, "hidraw9", 0xFEFE, 0, 0xFF60, 0)
            self.assertEqual(transport.sysfs_descriptor_for(0x8047, 2, tmp),
                             _desc(0xFF68, 1))
            self.assertEqual(transport.sysfs_descriptor_for(0x8047, 3, tmp),
                             _desc(0xFF67, 2))
            self.assertIsNone(transport.sysfs_descriptor_for(0x8047, 1, tmp))
            self.assertEqual(transport.sysfs_descriptor_for(0xFEFE, 0, tmp),
                             _desc(0xFF60, 0))

    def test_empty_sysfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(transport.iter_sysfs_hidraw(tmp)), [])
            self.assertIsNone(transport.sysfs_descriptor_for(0x8047, -1, tmp))

    def test_read_report_descriptor_libusb_style_path(self):
        info = _iface(b"1-1.1:1.0", iface=2)
        with mock.patch.object(transport, "hid", None), \
                mock.patch.object(transport, "sysfs_descriptor_for",
                                  return_value=_desc(0xFF67, 2)) as m:
            desc = transport._read_report_descriptor(info)
        self.assertEqual(desc, _desc(0xFF67, 2))
        m.assert_called_once_with(0x8047, 2)


class TestReadReportTimeout(unittest.TestCase):
    """通知监听线程用非阻塞读；普通请求用毫秒超时。

    注意 cython-hidapi 的 ``dev.read(len, 0)`` 其实是阻塞的（走 hid_read），
    非阻塞必须 ``set_nonblocking(1)`` + ``read(len)``。
    """

    def _iface_obj(self):
        return transport.HidInterface(_iface(b"/dev/hidraw1"))

    def test_nonblocking_read_toggles_mode(self):
        fake_dev = mock.Mock()
        fake_dev.read.return_value = []
        h = self._iface_obj()
        h._dev = fake_dev
        self.assertIsNone(h.read_report_nonblocking())
        self.assertEqual(
            fake_dev.set_nonblocking.call_args_list,
            [mock.call(1), mock.call(0)],
        )
        fake_dev.read.assert_called_once_with(65)  # payload 64 + 1

    def test_nonblocking_read_returns_report(self):
        fake_dev = mock.Mock()
        fake_dev.read.return_value = list(b"\x55\xfa" + b"\x00" * 62)
        h = self._iface_obj()
        h._dev = fake_dev
        data = h.read_report_nonblocking()
        self.assertEqual(data[0], 0x55)
        self.assertEqual(len(data), 64)

    def test_positive_timeout_passes_milliseconds(self):
        fake_dev = mock.Mock()
        fake_dev.read.return_value = list(bytes([0x55]) + b"\x00" * 63)
        h = self._iface_obj()
        h._dev = fake_dev
        data = h.read_report(0.05)
        fake_dev.read.assert_called_once_with(65, 50)
        self.assertEqual(data[0], 0x55)


if __name__ == "__main__":
    unittest.main(verbosity=2)
