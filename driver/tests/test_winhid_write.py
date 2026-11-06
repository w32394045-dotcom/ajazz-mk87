"""winhid 原生 HID 写超时 / 卡死保护的单测（仅 Windows 有意义）。

背景（用户 2026-11-06 实机事故）：系统进入连接待机后，原生同步 `WriteFile`
在 `mk87-music` 线程里永久阻塞（py-spy 栈：NativeHidChannel.write）。修复方式：
写句柄改为 overlapped + 超时 wait，超时后 CancelIoEx；取消不掉说明设备真挂起，
标记通道卡死、由上层重建；不关句柄（在途 IO 未完成）而是整条通道交给模块级
保活列表，避免内核写已释放内存。

这些测试用假 kernel32 验证分支，不打开真实设备。
"""
import sys
import unittest
from unittest import mock

if sys.platform == "win32":
    from mk87lib import winhid
else:  # pragma: no cover - 非 Windows 直接跳过整个文件
    winhid = None


@unittest.skipUnless(sys.platform == "win32", "winhid 仅 Windows 可用")
class TestNativeHidChannelWrite(unittest.TestCase):
    def setUp(self):
        self._orphans = list(winhid._ORPHAN_CHANNELS)
        winhid._ORPHAN_CHANNELS.clear()

    def tearDown(self):
        winhid._ORPHAN_CHANNELS[:] = self._orphans

    def _fake_kernel32(self, write_ok=0, wait_side=None):
        """构造假 kernel32：CreateFileW 返回两个句柄、CreateEventW 返回两个事件。"""
        fake = mock.Mock()
        fake.CreateFileW.side_effect = [0x1004, 0x1008]
        fake.CreateEventW.side_effect = [0x2004, 0x2008]
        fake.WriteFile.return_value = write_ok
        fake.WaitForSingleObject.side_effect = wait_side
        fake.GetOverlappedResult.return_value = 0
        fake.CancelIoEx.return_value = 1
        return fake

    def _make_channel(self, fake):
        with mock.patch.object(winhid, "kernel32", fake):
            return winhid.NativeHidChannel("\\\\?\\HID#fake", read_len=64, write_len=65)

    def test_sync_write_fast_path(self):
        fake = self._fake_kernel32(write_ok=1)
        channel = self._make_channel(fake)
        with mock.patch.object(winhid, "kernel32", fake):
            self.assertEqual(channel.write(b"\x00" * 65), 0)
        self.assertFalse(channel._write_stuck)

    def test_pending_write_times_out_and_raises(self):
        fake = self._fake_kernel32(
            wait_side=[winhid.WAIT_TIMEOUT, winhid.WAIT_TIMEOUT])
        channel = self._make_channel(fake)
        with mock.patch.object(winhid, "kernel32", fake), \
                mock.patch.object(winhid, "_last_error", return_value=winhid.ERROR_IO_PENDING):
            with self.assertRaises(OSError):
                channel.write(b"\x00" * 65)
        self.assertTrue(channel._write_stuck, "取消不掉必须标记卡死")
        # 第二次写应立刻失败（不再往挂起句柄写）
        with mock.patch.object(winhid, "kernel32", fake):
            with self.assertRaises(OSError):
                channel.write(b"\x00" * 65)

    def test_timeout_after_cancel_completes_is_reusable(self):
        """取消在宽限期内生效：报超时但通道可继续使用。"""
        fake = self._fake_kernel32(
            wait_side=[winhid.WAIT_TIMEOUT, winhid.WAIT_OBJECT_0])
        channel = self._make_channel(fake)
        with mock.patch.object(winhid, "kernel32", fake), \
                mock.patch.object(winhid, "_last_error", return_value=winhid.ERROR_IO_PENDING):
            with self.assertRaises(OSError):
                channel.write(b"\x00" * 65)
        self.assertFalse(channel._write_stuck, "取消成功则通道不应被标记卡死")

    def test_stuck_channel_close_is_orphaned_not_closed(self):
        fake = self._fake_kernel32(
            wait_side=[winhid.WAIT_TIMEOUT, winhid.WAIT_TIMEOUT])
        channel = self._make_channel(fake)
        with mock.patch.object(winhid, "kernel32", fake), \
                mock.patch.object(winhid, "_last_error", return_value=winhid.ERROR_IO_PENDING):
            with self.assertRaises(OSError):
                channel.write(b"\x00" * 65)
            channel.close()
        # 在途写未完成：绝不能 CloseHandle（内核可能仍在写），整条通道交给保活列表
        self.assertIn(channel, winhid._ORPHAN_CHANNELS)
        fake.CloseHandle.assert_not_called()
        # close 幂等
        with mock.patch.object(winhid, "kernel32", fake):
            channel.close()
        self.assertEqual(len(winhid._ORPHAN_CHANNELS), 1)

    def test_write_error_1167_raises_without_marking_stuck(self):
        fake = self._fake_kernel32(write_ok=0)
        channel = self._make_channel(fake)
        with mock.patch.object(winhid, "kernel32", fake), \
                mock.patch.object(winhid, "_last_error", return_value=1167):
            with self.assertRaises(OSError):
                channel.write(b"\x00" * 65)
        self.assertFalse(channel._write_stuck, "设备已移除是普通错误，交给会话重建")
        with mock.patch.object(winhid, "kernel32", fake):
            channel.close()
        fake.CloseHandle.assert_any_call(0x1004)
        fake.CloseHandle.assert_any_call(0x1008)


if __name__ == "__main__":
    unittest.main()
