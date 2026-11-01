"""服务端状态：设备管理、事件总线、后台任务、本地设置。"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import threading
import time
from typing import Dict, List, Optional

from mk87lib import backup, keymap, lighting, macro, music, tft, wireless
from mk87lib import keyscan as keyscan_mod
from mk87lib.device import MK87Device
from mk87lib.errors import DeviceNotFound, MK87Error, UnsupportedFeature


# ----------------------------------------------------------------------
# 本地设置
# ----------------------------------------------------------------------
def _config_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "mk87")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "mk87")


DEFAULT_SETTINGS = {
    "theme": "auto",       # light / dark / auto
    "language": "zh",      # zh / en
    "startPage": "lighting",
    "autoReconnect": True,
}


class Settings:
    def __init__(self) -> None:
        self.path = os.path.join(_config_dir(), "settings.json")
        self.data = dict(DEFAULT_SETTINGS)
        self.lock = threading.Lock()
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in DEFAULT_SETTINGS})
        except Exception:
            pass

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self) -> dict:
        with self.lock:
            return dict(self.data)

    def update(self, patch: dict) -> dict:
        with self.lock:
            for k, v in (patch or {}).items():
                if k in DEFAULT_SETTINGS:
                    self.data[k] = v
            self.save()
            return dict(self.data)


# ----------------------------------------------------------------------
# TFT 上传任务
# ----------------------------------------------------------------------
class TftJob:
    def __init__(self, manager: "DeviceManager") -> None:
        self.manager = manager
        self.lock = threading.Lock()
        self.running = False
        self.phase = "idle"      # idle / upload / done / error / cancelled
        self.pct = 0
        self.sent = 0
        self.total = 0
        self.error = ""
        self.frames = 0
        self.kind = ""
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.started_at = 0.0
        self.elapsed = 0.0

    def status(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "phase": self.phase,
                "pct": self.pct,
                "sent": self.sent,
                "total": self.total,
                "error": self.error,
                "frames": self.frames,
                "kind": self.kind,
                "elapsed": round(self.elapsed, 1),
            }

    def start(self, *, kind: str, frames: int, runner) -> dict:
        if self.running:
            raise MK87Error("已有 TFT 上传任务在进行")
        self._cancel.clear()
        with self.lock:
            self.running = True
            self.phase = "upload"
            self.pct = 0
            self.sent = 0
            self.total = 0
            self.error = ""
            self.frames = frames
            self.kind = kind
            self.started_at = time.time()
            self.elapsed = 0.0
        self._thread = threading.Thread(target=self._run, args=(runner,), name="mk87-tft-job", daemon=True)
        self._thread.start()
        return self.status()

    def _progress(self, pct: int, sent: int, total: int) -> None:
        with self.lock:
            self.pct = pct
            self.sent = sent
            self.total = total
        self.manager.emit({
            "type": "progress",
            "data": {"job": "tft", "phase": "upload", "pct": pct, "sent": sent, "total": total},
        })

    def _run(self, runner) -> None:
        try:
            res = runner(self._progress, self._cancel.is_set)
            with self.lock:
                self.phase = "done"
                self.pct = 100
                self.elapsed = time.time() - self.started_at
            self.manager.emit({"type": "job", "data": {"job": "tft", "state": "done", "result": res}})
        except Exception as exc:  # noqa: BLE001
            cancelled = self._cancel.is_set()
            with self.lock:
                self.phase = "cancelled" if cancelled else "error"
                self.error = "" if cancelled else str(exc)
                self.elapsed = time.time() - self.started_at
            self.manager.emit({
                "type": "job",
                "data": {"job": "tft", "state": "cancelled" if cancelled else "error",
                         "error": "" if cancelled else str(exc)},
            })
        finally:
            with self.lock:
                self.running = False

    def cancel(self) -> dict:
        self._cancel.set()
        return self.status()


# ----------------------------------------------------------------------
# 设备管理器
# ----------------------------------------------------------------------
class DeviceManager:
    def __init__(self) -> None:
        self.device = MK87Device()
        self.lock = threading.RLock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.subscribers: List[asyncio.Queue] = []
        self.sub_lock = threading.Lock()
        self.settings = Settings()
        self.tft_job = TftJob(self)
        self.music = music.MusicPlayer(self.device)
        self.keytest = keyscan_mod.get_scanner(callback=self._on_key_event, only_ajazz=False)
        self._recent_events: List[dict] = []
        self._last_battery: Optional[int] = None
        self._stop = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._was_connected = False
        self.device.add_listener(self._on_device_event)

    # ------------------------------------------------------------------ 事件
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self.sub_lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self.sub_lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def emit(self, event: dict) -> None:
        event.setdefault("ts", time.time())
        self._recent_events.append(event)
        if len(self._recent_events) > 200:
            del self._recent_events[:100]
        loop = self.loop
        if loop is None:
            return
        with self.sub_lock:
            subs = list(self.subscribers)
        for q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                pass

    def _on_device_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "notification":
            self.emit({"type": "notification",
                       "data": {"kind": ev.get("kind"), "ts": ev.get("ts"), "source": ev.get("source")}})
        elif t == "disconnected":
            self.emit({"type": "status", "data": self.status()})
        elif t == "raw":
            pass

    def _on_key_event(self, ev: dict) -> None:
        self.emit({"type": "keyevent", "data": ev})

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        self._monitor_thread = threading.Thread(target=self._monitor, name="mk87-monitor", daemon=True)
        self._monitor_thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.music.stop()
        except Exception:
            pass
        try:
            self.keytest.stop()
        except Exception:
            pass
        try:
            self.device.close()
        except Exception:
            pass

    def _monitor(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.device.status.connected:
                    self._try_connect(quiet=True)
                else:
                    self._refresh_battery()
            except Exception:
                pass
            time.sleep(2.0)

    def _try_connect(self, quiet: bool = False) -> bool:
        with self.lock:
            try:
                status = self.device.connect()
                self._was_connected = True
                self._last_battery = status.battery
                # 与官方一致：每次连接自动对时一次（MK87 屏幕时间）
                try:
                    self.device.sync_time()
                except Exception:
                    pass
                self.emit({"type": "status", "data": self.status()})
                return True
            except Exception as exc:  # noqa: BLE001
                if not quiet:
                    raise
                if self._was_connected:
                    self._was_connected = False
                    self.emit({"type": "toast",
                               "data": {"level": "warn", "message": f"设备已断开：{exc}"}})
                return False

    def _refresh_battery(self) -> None:
        try:
            info = self.device.get_device_info()
            battery = int(info.get("batteryLevel", 0))
            if battery != self._last_battery:
                self._last_battery = battery
                self.device.status.battery = battery
                self.device.status.charging = int(info.get("chargeStatus", 0))
                self.emit({"type": "battery",
                           "data": {"percent": battery, "charging": self.device.status.charging}})
        except Exception:
            pass

    # ------------------------------------------------------------------ 对外
    @property
    def connected(self) -> bool:
        return bool(self.device.status.connected)

    def require(self) -> MK87Device:
        if not self.connected:
            raise DeviceNotFound("设备未连接")
        return self.device

    def status(self) -> dict:
        st = self.device.status.to_dict()
        st["mock"] = False
        st["shell"] = bool(getattr(self, "shell_mode", False))
        st["webVersion"] = "0.1.0"
        st["recentNotifications"] = [
            e for e in self.device.recent_events if e.get("type") == "notification"
        ][-10:]
        items = self._conflict_items()
        st["conflictItems"] = items
        st["conflicts"] = [i["zh"] for i in items]
        st["settings"] = self.settings.get()
        return st

    def _conflict_items(self) -> List[dict]:
        """结构化冲突提示（前端按当前语言选择 zh/en 渲染）。"""
        items: List[dict] = []
        if self.device.status.transport == "2.4g":
            items.append({
                "code": "usb_resource_conflict",
                "zh": (
                    "检测到设备冲突：当前使用 2.4G 连接。若键盘 USB 线也插着而未识别，"
                    "可能是 Windows 的 USB 复合设备资源不足（0xC000009A）—— "
                    "请拔掉 2.4G 接收器并重新插键盘 USB 线以使用 USB 模式。"
                ),
                "en": (
                    "Device conflict detected: currently connected via 2.4G. If the USB cable "
                    "is also plugged in but the keyboard is not detected, Windows may have failed "
                    "to start the USB composite device due to insufficient resources (0xC000009A) — "
                    "unplug the 2.4G dongle and reconnect the USB cable to use USB mode."
                ),
            })
        return items

    def _detect_conflicts(self) -> List[str]:
        return [i["zh"] for i in self._conflict_items()]


# 全局单例（app.py 使用）
manager = DeviceManager()
