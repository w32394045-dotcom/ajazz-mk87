# -*- coding: utf-8 -*-
"""Linux 音乐律动音频采集：libpulse-simple 优先、parec 兜底。

背景（2026-11-04 用户日志）：Linux 上 POST /api/music/start 返回 400。根因是
采集只走外部命令 parec，而 Fedora/Debian 的 PipeWire 桌面默认不装
pulseaudio-utils，`subprocess.Popen(["parec", ...])` 直接 FileNotFoundError。
现在默认用 libpulse-simple（libpulse0 / pulseaudio-libs 自带，安装包已声明依赖，
PipeWire 的 pulse 兼容层同样支持 @DEFAULT_MONITOR@），parec 只作兜底。
"""
import ctypes
import io
import unittest
from unittest import mock

import numpy as np

from mk87lib import music
from mk87lib.errors import MK87Error


class FakePulseLib:
    """假的 libpulse-simple：记录调用、按需回放声音数据。

    注意：用普通函数（lambda）挂在实例属性上，才能像 ctypes 函数那样设置
    ``restype`` / ``argtypes``；bound method 不允许设置属性。
    """

    def __init__(self, samples=None, new_returns=1, read_rc=0):
        self.samples = samples
        self.new_returns = new_returns
        self.read_rc = read_rc
        self.new_args = None
        self.freed = []
        self.read_bytes = 0

        def _new(*args):
            self.new_args = args
            return self.new_returns

        def _read(handle, buf, nbytes, error_ptr):
            self.read_bytes += int(nbytes)
            if self.read_rc < 0:
                return self.read_rc
            data = self.samples if self.samples is not None else b"\x00" * int(nbytes)
            data = data[:int(nbytes)]
            ctypes.memmove(buf, data, len(data))
            return 0

        def _free(handle):
            self.freed.append(handle)

        self.pa_simple_new = _new
        self.pa_simple_read = _read
        self.pa_simple_free = _free


def _stereo_bytes(frames):
    """构造 2ch float32 数据：左声道 0.5、右声道 -0.5 → 均值 0。"""
    inter = np.empty((frames, 2), dtype="<f4")
    inter[:, 0] = 0.5
    inter[:, 1] = -0.5
    return inter.tobytes()


class TestPulseSimpleRecorder(unittest.TestCase):
    def _patched(self, lib):
        fake_pulse = mock.Mock()
        fake_pulse.pa_strerror.return_value = b"Connection refused"

        def fake_cdll(name):
            if "pulse-simple" in name:
                return lib
            if name == "libpulse.so.0":
                return fake_pulse
            raise OSError(name)

        return mock.patch.object(music.ctypes, "CDLL", side_effect=fake_cdll), fake_pulse

    def test_open_read_mean_close(self):
        data = _stereo_bytes(128)
        lib = FakePulseLib(samples=data)
        patcher, _pulse = self._patched(lib)
        with patcher:
            rec = music.PulseSimpleRecorder(None, 48000)
            self.assertEqual(rec.device, music.DEFAULT_MONITOR)
            out = rec.read(128)
            self.assertEqual(out.shape, (128,))
            self.assertAlmostEqual(float(out.mean()), 0.0, places=6)
            self.assertEqual(lib.read_bytes, 128 * 2 * 4)
            rec.close()
        self.assertEqual(lib.freed, [1])
        # 采样参数：float32le / 48000 / 2ch
        spec = lib.new_args[5]._obj
        self.assertEqual(spec.format, music.PA_SAMPLE_FLOAT32LE)
        self.assertEqual(spec.rate, 48000)
        self.assertEqual(spec.channels, 2)

    def test_open_failure_reports_pa_error(self):
        lib = FakePulseLib(new_returns=0)
        patcher, _pulse = self._patched(lib)
        with patcher:
            with self.assertRaises(MK87Error) as ctx:
                music.PulseSimpleRecorder("alsa_output.foo.monitor", 48000)
        msg = str(ctx.exception)
        self.assertIn("Connection refused", msg)
        self.assertIn("alsa_output.foo.monitor", msg)

    def test_missing_library_is_actionable(self):
        def fake_cdll(name):
            raise OSError(name)

        with mock.patch.object(music.ctypes, "CDLL", side_effect=fake_cdll), \
                mock.patch.object(music.ctypes.util, "find_library", return_value=None):
            with self.assertRaises(MK87Error) as ctx:
                music.PulseSimpleRecorder()
        self.assertIn("libpulse-simple", str(ctx.exception))

    def test_read_after_close_raises(self):
        data = _stereo_bytes(64)
        lib = FakePulseLib(samples=data)
        patcher, _pulse = self._patched(lib)
        with patcher:
            rec = music.PulseSimpleRecorder()
            rec.close()
            with self.assertRaises(MK87Error):
                rec.read(64)

    def test_read_error_raises(self):
        lib = FakePulseLib(read_rc=-1)
        patcher, _pulse = self._patched(lib)
        with patcher:
            rec = music.PulseSimpleRecorder()
            with self.assertRaises(MK87Error) as ctx:
                rec.read(64)
        self.assertIn("Connection refused", str(ctx.exception))


class TestAudioCaptureLinux(unittest.TestCase):
    def _capture(self):
        cap = music.AudioCapture()
        cap.system = "Linux"
        return cap

    def test_prefers_libpulse(self):
        fake_rec = mock.Mock()
        fake_rec.read.return_value = np.zeros(16, dtype=np.float32)
        with mock.patch.object(music, "PulseSimpleRecorder", return_value=fake_rec) as m, \
                mock.patch.object(music, "_pactl_default_monitor", return_value=None), \
                mock.patch.object(music.subprocess, "Popen") as popen:
            cap = self._capture()
            cap._open_impl()
        self.assertEqual(cap._backend, "libpulse")
        self.assertIs(cap._pulse, fake_rec)
        popen.assert_not_called()
        m.assert_called_once()

    def test_falls_back_to_parec(self):
        data = _stereo_bytes(16)
        proc = mock.Mock()
        proc.stdout = io.BytesIO(data)
        proc.poll.return_value = None
        with mock.patch.object(music, "PulseSimpleRecorder", side_effect=MK87Error("no pulse")), \
                mock.patch.object(music.subprocess, "Popen", return_value=proc) as popen:
            cap = self._capture()
            cap._open_impl()
            out = cap._read_impl(16)
        self.assertEqual(cap._backend, "parec")
        self.assertEqual(out.shape, (16,))
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "parec")
        self.assertIn("--device=" + music.DEFAULT_MONITOR, args)

    def test_parec_eof_raises_instead_of_silence(self):
        proc = mock.Mock()
        proc.stdout = io.BytesIO(b"")
        proc.poll.return_value = 3
        with mock.patch.object(music, "PulseSimpleRecorder", side_effect=MK87Error("no pulse")), \
                mock.patch.object(music.subprocess, "Popen", return_value=proc):
            cap = self._capture()
            cap._open_impl()
            with self.assertRaises(MK87Error) as ctx:
                cap._read_impl(16)
        self.assertIn("parec", str(ctx.exception))

    def test_both_backends_fail_actionable_error(self):
        def popen_missing(*_a, **_kw):
            raise FileNotFoundError("parec")

        with mock.patch.object(music, "PulseSimpleRecorder", side_effect=MK87Error("no pulse")), \
                mock.patch.object(music.subprocess, "Popen", side_effect=popen_missing):
            cap = self._capture()
            with self.assertRaises(MK87Error) as ctx:
                cap._open_impl()
        msg = str(ctx.exception)
        self.assertIn("libpulse", msg)
        self.assertIn("parec", msg)
        self.assertIn("pipewire-pulse", msg)

    def test_retries_with_real_monitor_name(self):
        fake_rec = mock.Mock()
        calls = []

        def rec_factory(dev, rate):
            calls.append(dev)
            if len(calls) == 1:
                raise MK87Error("no special name")
            return fake_rec

        with mock.patch.object(music, "PulseSimpleRecorder", side_effect=rec_factory), \
                mock.patch.object(music, "_pactl_default_monitor",
                                  return_value="alsa_output.x.monitor"):
            cap = self._capture()
            cap._open_impl()
        self.assertEqual(calls, [None, "alsa_output.x.monitor"])
        self.assertEqual(cap._backend, "libpulse")
        self.assertIs(cap._pulse, fake_rec)

    def test_close_closes_pulse(self):
        fake_rec = mock.Mock()
        cap = self._capture()
        cap._pulse = fake_rec
        cap._close_impl()
        fake_rec.close.assert_called_once()
        self.assertIsNone(cap._pulse)


class TestPactlDefaultMonitor(unittest.TestCase):
    def test_returns_monitor_of_default_sink(self):
        res = mock.Mock(stdout="alsa_output.pci-0000_00_1f.3.analog-stereo\n")
        with mock.patch.object(music.subprocess, "run", return_value=res):
            self.assertEqual(
                music._pactl_default_monitor(),
                "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor",
            )

    def test_missing_pactl(self):
        with mock.patch.object(music.subprocess, "run", side_effect=FileNotFoundError("pactl")):
            self.assertIsNone(music._pactl_default_monitor())

    def test_empty_output(self):
        with mock.patch.object(music.subprocess, "run", return_value=mock.Mock(stdout="\n")):
            self.assertIsNone(music._pactl_default_monitor())


class TestListDevicesLinux(unittest.TestCase):
    def test_parses_pactl_sources(self):
        stdout = ("0\talsa_output.pci-0000_00_1f.3.analog-stereo.monitor\t"
                  "module-alsa-card.c\ts16le 2ch 48000Hz\tRUNNING\n")
        res = mock.Mock(stdout=stdout)
        with mock.patch.object(music.platform, "system", return_value="Linux"), \
                mock.patch.object(music.subprocess, "run", return_value=res):
            out = music.list_devices()
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["loopback"])
        self.assertTrue(out[0]["default"])
        self.assertIn("monitor", out[0]["id"])

    def test_pactl_missing_returns_default_monitor(self):
        with mock.patch.object(music.platform, "system", return_value="Linux"), \
                mock.patch.object(music.subprocess, "run", side_effect=FileNotFoundError("pactl")):
            out = music.list_devices()
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0]["id"])
        self.assertTrue(out[0]["loopback"])
        self.assertIn("默认输出回环", out[0]["name"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
