"""音乐律动健康 / 停止 WS 事件的契约测试（v0.1.8.4）。

前端 `music.js` 依赖这些事件显示「恢复中… / 等待键盘 / 已自动恢复」并自动切回
未开始状态；这里用假 MusicPlayer 验证 DeviceManager._music_level_loop 只在状态
变化时推送，且字段与前端契约一致。
"""
import threading
import time
import unittest
from types import SimpleNamespace

from server import state


class _FakeMusic:
    def __init__(self):
        self.running = False
        self.health = "stopped"
        self.last_error = ""
        self.recoveries = 0
        self.level = 0.5
        self.levels32 = [0.25] * 32
        self.fps = 20
        self.last_colors = {}
        self.mode = 13
        self.frames = 0
        self.errors = 0
        self._user_stopped = False
        self.measured_fps = None


def _wait_until(pred, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return False


class TestMusicHealthEvents(unittest.TestCase):
    def _manager(self):
        mgr = object.__new__(state.DeviceManager)  # 不启动真实设备/线程
        mgr._stop = threading.Event()
        mgr.music = _FakeMusic()
        mgr.device = SimpleNamespace(status=SimpleNamespace(connected=True))
        self.events = []
        mgr.emit = self.events.append
        self.thread = threading.Thread(target=mgr._music_level_loop, daemon=True)
        self.thread.start()
        self.addCleanup(self._join)
        return mgr

    def _join(self):
        self._stop_flag.set()
        self.thread.join(timeout=2.0)

    def test_health_and_stopped_events(self):
        mgr = self._manager()
        self._stop_flag = mgr._stop
        # 1) 开始运行：推一条 music_health(ok)
        mgr.music.running = True
        mgr.music.health = "ok"
        self.assertTrue(_wait_until(lambda: any(
            e.get("type") == "music_health" for e in self.events)))
        ev = [e for e in self.events if e.get("type") == "music_health"][0]
        self.assertEqual(ev["data"]["state"], "ok")
        self.assertEqual(ev["data"]["recoveries"], 0)
        self.assertTrue(ev["data"]["connected"])
        self.assertIn("lastError", ev["data"])
        # 2) 自动恢复中：状态变化再推一条
        count = len(self.events)
        mgr.music.health = "recovering"
        mgr.music.recoveries = 1
        mgr.music.last_error = "音频采集卡死"
        self.assertTrue(_wait_until(lambda: any(
            e.get("type") == "music_health" and e["data"]["state"] == "recovering"
            for e in self.events[count:])))
        # 3) 意外停止：推 music_stopped(unexpected=True) 且带原因
        count = len(self.events)
        mgr.music.running = False
        self.assertTrue(_wait_until(lambda: any(
            e.get("type") == "music_stopped" for e in self.events[count:])))
        ev = [e for e in self.events[count:] if e.get("type") == "music_stopped"][0]
        self.assertTrue(ev["data"]["unexpected"])
        self.assertIn("音频采集卡死", ev["data"]["reason"])
        self.assertIn("frames", ev["data"])
        self.assertIn("errors", ev["data"])

    def test_user_stop_is_not_unexpected(self):
        mgr = self._manager()
        self._stop_flag = mgr._stop
        mgr.music.running = True
        mgr.music.health = "ok"
        self.assertTrue(_wait_until(lambda: any(
            e.get("type") == "music_health" for e in self.events)))
        mgr.music._user_stopped = True
        mgr.music.running = False
        self.assertTrue(_wait_until(lambda: any(
            e.get("type") == "music_stopped" for e in self.events)))
        ev = [e for e in self.events if e.get("type") == "music_stopped"][0]
        self.assertFalse(ev["data"]["unexpected"], "用户主动停止不应提示「意外停止」")

    def test_health_event_tolerates_legacy_player(self):
        """旧 MusicPlayer / 单测假对象没有 health 字段时用默认值，不抛异常。"""
        mgr = object.__new__(state.DeviceManager)
        mgr.music = SimpleNamespace(last_error="", running=False)
        mgr.device = SimpleNamespace(status=SimpleNamespace(connected=False))
        ev = mgr._music_health_event()
        self.assertEqual(ev["state"], "ok")
        self.assertEqual(ev["recoveries"], 0)
        self.assertFalse(ev["connected"])


if __name__ == "__main__":
    unittest.main()
