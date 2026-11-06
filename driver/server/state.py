"""服务端状态：设备管理、事件总线、后台任务、本地设置。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import threading
import time
from typing import Dict, List, Optional

from mk87lib import backup, keymap, lighting, macro, music, tft, wireless
from mk87lib import keyscan as keyscan_mod
from mk87lib.device import MK87Device
from mk87lib.errors import DeviceDisconnected, DeviceNotFound, MK87Error, UnsupportedFeature

log = logging.getLogger("mk87.state")


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
        log.info("TFT 任务开始 kind=%s frames=%s", self.kind, self.frames)
        attempts = 0
        try:
            while True:
                attempts += 1
                try:
                    res = runner(self._progress, self._cancel.is_set)
                except Exception as exc:  # noqa: BLE001
                    cancelled = self._cancel.is_set()
                    # 设备在上传中途 USB 复位（实测并发命令会触发）：等自动重连后重试一次
                    if (not cancelled and isinstance(exc, DeviceDisconnected)
                            and attempts == 1):
                        log.warning("TFT 任务因设备掉线中断，等待自动重连后重试一次: %s", exc)
                        self.manager.mark_disconnected(str(exc))
                        if self._wait_reconnect(30.0) and not self._cancel.is_set():
                            with self.lock:
                                self.phase = "upload"
                                self.pct = 0
                                self.sent = 0
                                self.total = 0
                                self.error = ""
                            continue
                    with self.lock:
                        self.phase = "cancelled" if cancelled else "error"
                        self.error = "" if cancelled else str(exc)
                        self.elapsed = time.time() - self.started_at
                    if cancelled:
                        log.info("TFT 任务取消 kind=%s frames=%s", self.kind, self.frames)
                    else:
                        log.error("TFT 任务失败 kind=%s frames=%s: %s", self.kind, self.frames,
                                  exc, exc_info=True)
                        self.manager.mark_disconnected(str(exc))
                    self.manager.emit({
                        "type": "job",
                        "data": {"job": "tft", "state": "cancelled" if cancelled else "error",
                                 "error": "" if cancelled else str(exc)},
                    })
                    return
                with self.lock:
                    self.phase = "done"
                    self.pct = 100
                    self.elapsed = time.time() - self.started_at
                log.info("TFT 任务完成 kind=%s frames=%s 用时 %.1fs result=%s",
                         self.kind, self.frames, self.elapsed, {k: res.get(k) for k in
                         ("packets", "bytes", "seconds", "acks", "frames") if k in res})
                self.manager.emit({"type": "job", "data": {"job": "tft", "state": "done",
                                                           "result": res}})
                return
        finally:
            with self.lock:
                self.running = False

    def _wait_reconnect(self, timeout: float) -> bool:
        """等设备自动重连（monitor 线程负责重连），最多 timeout 秒。"""
        deadline = time.time() + max(1.0, timeout)
        while time.time() < deadline:
            if self._cancel.is_set():
                return False
            if self.manager.connected:
                return True
            time.sleep(0.2)
        return False

    def cancel(self) -> dict:
        self._cancel.set()
        return self.status()


# ----------------------------------------------------------------------
# 音乐律动预览事件限速
# ----------------------------------------------------------------------
#: 键盘发包可以到 66fps，但 ``music_frame`` 每帧要带 87 键 × 4B 的 JSON
#: （~1.5KB），66Hz 会给浏览器和 WS 造成不必要负担；预览是「看个大概」，
#: 30Hz 已足够流畅（官方 UI 本身也只有 20fps 预览）。实测帧率仍按 30Hz 回传。
MUSIC_PREVIEW_MAX_FPS = 30


def _music_preview_period(target_fps) -> float:
    """预览事件的发送周期（秒）：目标帧率上限 66，预览上限 30fps。"""
    try:
        fps = float(target_fps)
    except (TypeError, ValueError):
        fps = float(music.DEFAULT_FPS)
    fps = max(float(music.FPS_MIN), min(float(music.FPS_MAX), fps))
    return 1.0 / min(fps, float(MUSIC_PREVIEW_MAX_FPS))


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
        self._last_battery_state: Optional[tuple] = None
        self._battery_error = ""
        self._battery_error_at = 0.0
        #: 2.4G 电量（cmd 0x37 首包 byte[3]）连续失败时熔断，避免每 2s 卡 1s 超时
        self._battery_24g_fails = 0
        self._battery_24g_retry_at = 0.0
        self._conn_gen = 0
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
        self._music_level_thread = threading.Thread(
            target=self._music_level_loop, name="mk87-music-level", daemon=True
        )
        self._music_level_thread.start()

    def _music_level_loop(self) -> None:
        """音乐律动运行时推送两类事件（v0.1.8.4 起再加健康/停止事件）：

        * ``music_level``（10fps）：总振幅 + 32 段频谱，给电平条/频谱条用；
        * ``music_frame``（跟随目标帧率、预览上限 30fps）：后端**实际发给键盘那一帧**的
          逐键颜色，前端「官方方案」预览直接回放它，保证屏幕预览与键盘逐键一致；
          事件里的 ``fps`` 是后端实测帧率（float），与 ``/api/music/status`` 同源；
        * ``music_health``（状态变化时）：自动恢复中 / 等待键盘 / 已恢复，前端显示徽章；
        * ``music_stopped``（运行中 → 不在运行）：意外停止时前端自动切回未开始并提示原因。
        """
        level_due = 0.0
        frame_due = 0.0
        last_health = None
        last_running = False
        while not self._stop.is_set():
            try:
                running = bool(self.music.running)
                if running != last_running:
                    if running:
                        last_health = getattr(self.music, "health", "ok")
                        self.emit({"type": "music_health",
                                   "data": self._music_health_event()})
                    else:
                        self.emit({
                            "type": "music_stopped",
                            "data": {
                                "reason": getattr(self.music, "last_error", "") or "",
                                "unexpected": not bool(
                                    getattr(self.music, "_user_stopped", False)),
                                "frames": int(getattr(self.music, "frames", 0)),
                                "errors": int(getattr(self.music, "errors", 0)),
                            },
                        })
                    last_running = running
                if running:
                    health = getattr(self.music, "health", "ok")
                    if health != last_health:
                        last_health = health
                        self.emit({"type": "music_health",
                                   "data": self._music_health_event()})
                    now = time.time()
                    if now >= level_due:
                        level_due = now + 0.1
                        self.emit({
                            "type": "music_level",
                            "data": {
                                "level": round(float(self.music.level), 3),
                                "bands": [round(float(b), 3) for b in self.music.levels32],
                            },
                        })
                    if now >= frame_due:
                        frame_due = now + _music_preview_period(
                            getattr(self.music, "fps", music.DEFAULT_FPS))
                        frame = self._music_frame_event()
                        if frame is not None:
                            self.emit(frame)
                    delay = min(level_due, frame_due) - time.time()
                    time.sleep(min(0.1, max(0.005, delay)))
                    continue
                level_due = frame_due = 0.0
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)

    def _music_health_event(self) -> dict:
        """音乐律动健康事件数据（兼容旧 MusicPlayer / 单测假对象）。"""
        return {
            "state": getattr(self.music, "health", "ok"),
            "lastError": getattr(self.music, "last_error", "") or "",
            "recoveries": int(getattr(self.music, "recoveries", 0)),
            "connected": bool(self.connected),
        }

    def _music_frame_event(self) -> Optional[dict]:
        """把 MusicPlayer 最近一帧的逐键颜色转成 WS 事件（还没出帧时返回 None）。

        ``fps`` 用实测值（``MusicPlayer.measured_fps``，float，样本不足为 None），
        不再用配置值冒充实测。
        """
        colors = self.music.last_colors
        if not colors:
            return None
        return {
            "type": "music_frame",
            "data": {
                "mode": int(self.music.mode),
                "frame": int(self.music.frames),
                "fps": getattr(self.music, "measured_fps", None),
                "colors": {str(int(slot)): [int(rgb[0]), int(rgb[1]), int(rgb[2])]
                           for slot, rgb in colors.items()},
            },
        }

    def stop_music(self, timeout: float = 3.0) -> bool:
        """停止音乐律动，并等待它 finally 里的 restore_effect 跑完。

        事故背景（2026-11-02 22:45）：音乐 start 后进程被关机杀死，restore 没执行，
        键盘一直停在自定义逐键表。music.stop() 只 join 2s；这里再按 lighting 侧
        记录的恢复时间戳确认恢复已发生，最多等 timeout 秒。返回是否确认恢复。
        """
        started = time.time()
        was_running = bool(getattr(self.music, "running", False))
        try:
            self.music.stop()
        except Exception as exc:  # noqa: BLE001
            log.warning("停止音乐律动失败: %s", exc)
        if not was_running:
            return True
        deadline = started + max(0.5, float(timeout))
        while time.time() < deadline:
            restore = lighting.restore_state()
            if float(restore.get("ts") or 0.0) >= started:
                log.info("音乐已停止，灯效恢复完成（mode=%s result=%s）",
                         restore.get("mode"), restore.get("result"))
                return True
            time.sleep(0.05)
        log.warning("等待音乐灯效恢复超时（%.1fs），继续关闭设备", timeout)
        return False

    def stop(self) -> None:
        log.info("设备管理停止")
        self._stop.set()
        # 顺序：先停音乐并等灯效恢复，再关 HID 句柄（否则 restore 写不进去）
        self.stop_music(3.0)
        try:
            self.keytest.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.device.close()
        except Exception:  # noqa: BLE001
            pass

    def _monitor(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.device.status.connected:
                    # 掉线必须允许重连（TFT 任务失败后正是在等自动重连再重试一次）；
                    # 重连不碰 TFT 通道，不会干扰进行中的上传。
                    self._try_connect(quiet=True)
                elif self.tft_job.running:
                    # TFT 上传进行中：绝不向设备发其它命令（并发命令会让固件 USB 复位，实测 1167）
                    pass
                else:
                    self._refresh_battery()
            except Exception:
                pass
            time.sleep(2.0)

    def _try_connect(self, quiet: bool = False) -> bool:
        with self.lock:
            try:
                status = self.device.connect()
                log.info("设备已连接: %s %s fw=%s transport=%s vid=0x%04X pid=0x%04X "
                         "battery=%d%% charging=%d workMode=%d",
                         status.product, status.manufacturer, status.firmware,
                         status.transport, status.vid, status.pid,
                         status.battery, status.charging, getattr(status, "work_mode", 0))
                self._was_connected = True
                self._last_battery = status.battery
                self._conn_gen += 1
                gen = self._conn_gen
                # 与官方一致：每次连接自动对时一次（MK87 屏幕时间）
                try:
                    self.device.sync_time()
                except Exception as exc:  # noqa: BLE001
                    log.debug("连接后屏幕对时失败: %s", exc)
                self.emit({"type": "status", "data": self.status()})
                # 刚连上时首读可能还是旧值（尤其 2.4G 唤醒/握手未完成）：延迟 2s 再读一次
                self._schedule_battery_recheck(gen)
                return True
            except Exception as exc:  # noqa: BLE001
                if not quiet:
                    log.error("设备连接失败: %s", exc, exc_info=True)
                    raise
                if self._was_connected:
                    self._was_connected = False
                    log.warning("设备已断开: %s", exc)
                    self.emit({"type": "toast",
                               "data": {"level": "warn", "message": f"设备已断开：{exc}"}})
                else:
                    log.debug("扫描未发现设备: %s", exc)
                return False

    def _schedule_battery_recheck(self, gen: int, delay: float = 2.0) -> None:
        """连接后延迟重读设备信息（不阻塞 FastAPI/监控线程）。

        用连接代号 gen 防止旧连接的延迟任务把数据写到新连接上。
        """

        def _run() -> None:
            if self._stop.wait(max(0.0, float(delay))):
                return
            if gen != self._conn_gen or self._stop.is_set():
                return
            if not self.device.status.connected or self.tft_job.running:
                return
            log.info("连接后延迟 %.1fs 重读设备信息（校准电量/充电/工作模式）", delay)
            self._refresh_battery()

        threading.Thread(target=_run, name="mk87-battery-recheck", daemon=True).start()

    def _read_battery_24g(self) -> Optional[int]:
        """2.4G 下读电量（官方用 0x37 回包的 battery 字节）；失败熔断 5 分钟。"""
        now = time.time()
        if now < self._battery_24g_retry_at:
            return None
        try:
            battery = self.device.read_battery_24g()
        except Exception as exc:  # noqa: BLE001
            self._battery_24g_fails += 1
            if self._battery_24g_fails >= 3:
                self._battery_24g_retry_at = now + 300.0
                log.warning("2.4G 电量读取连续失败 %d 次，暂停 5 分钟（暂用设备信息 d[17]）: %s",
                            self._battery_24g_fails, exc)
            else:
                log.warning("2.4G 电量读取失败（暂用设备信息 d[17]）: %s", exc)
            return None
        if isinstance(battery, int):
            self._battery_24g_fails = 0
            return battery
        return None

    def _refresh_battery(self) -> None:
        """每 2s 刷新电量/充电/工作模式。

        * 每次成功读取都覆写 status（不再只在百分比变化时更新，charging 才不会滞后）；
        * 2.4G 下优先用官方路径（0x37 回包电量），USB 用 GET_DEVICE_INFO d[17]；
        * 失败限频告警（错误变化或每 60s 一次），避免每 2s 刷屏。
        """
        transport = str(getattr(self.device.status, "transport", "") or "")
        try:
            info = self.device.get_device_info()
        except Exception as exc:  # noqa: BLE001
            now = time.time()
            msg = str(exc)
            if msg != self._battery_error or now - self._battery_error_at >= 60.0:
                log.warning("刷新电量失败: %s", exc)
                self._battery_error = msg
                self._battery_error_at = now
            return
        self._battery_error = ""

        st = self.device.status
        battery = int(info.get("batteryLevel", 0))
        charging = int(info.get("chargeStatus", 0))
        work_mode = int(info.get("workMode", getattr(st, "work_mode", 0)) or 0)
        source = "device_info"
        if transport == "2.4g":
            battery_24g = self._read_battery_24g()
            if battery_24g is not None and 0 <= battery_24g <= 100:
                battery = battery_24g
                source = "24g_rgb"
            elif battery_24g is None:
                source = "24g_fallback"

        prev = (int(getattr(st, "battery", 0)), int(getattr(st, "charging", 0)),
                int(getattr(st, "work_mode", 0)))
        st.battery = battery
        st.charging = charging
        if hasattr(st, "work_mode"):
            st.work_mode = work_mode
        if hasattr(st, "battery_source"):
            st.battery_source = source
        self._last_battery = battery
        now_state = (battery, charging, work_mode)
        if now_state != self._last_battery_state:
            self._last_battery_state = now_state
            log.info("设备状态: battery=%d%% charging=%d workMode=%d transport=%s source=%s",
                     battery, charging, work_mode, transport, source)
            self.emit({"type": "battery",
                       "data": {"percent": battery, "charging": charging,
                                "workMode": work_mode}})
        elif prev != now_state:
            log.debug("设备状态变化（不触发 UI）: %s -> %s", prev, now_state)

    # ------------------------------------------------------------------ 对外
    def mark_disconnected(self, reason: str = "") -> None:
        """标记设备掉线（如 TFT 上传中 USB 复位），交给 monitor 线程自动重连。"""
        try:
            self.device.status.connected = False
            if reason:
                self.device.status.last_error = reason
        except Exception:  # noqa: BLE001
            pass
        try:
            self.emit({"type": "status", "data": self.status()})
        except Exception:  # noqa: BLE001
            pass

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
        st["webVersion"] = "0.1.8.4"
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
