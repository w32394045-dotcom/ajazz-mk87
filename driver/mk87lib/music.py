"""音乐律动（USB only）：系统音频采集 → 频谱分析 → 逐键颜色 → 0x32 帧流。

协议真机结论（docs/music-rhythm.md §9 / TEST-REPORT §9）：
* 必须先 SET_LED_EFFECT 到自定义族 mode ∈ {20,21,128}，再发 cmd 0x32 逐键帧才显示；
* 一帧 = 87 键 × 4 字节，按 keyList 行优先；USB 下 7 包/帧，20fps 稳定；
* 停发约 5 秒后固件回落到自定义表；本模块停止时会主动恢复进入前的灯效；
* 2.4G 官方不支持，仅 USB 可用。

音频采集：
* Windows: `soundcard` WASAPI loopback（采集系统输出）
* Linux: `parec`（PulseAudio/PipeWire monitor）
"""
from __future__ import annotations

import colorsys
import math
import platform
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import keymap, lighting
from .errors import MK87Error

RGB = Tuple[int, int, int]


# ----------------------------------------------------------------------
# 键盘几何（渲染器用）
# ----------------------------------------------------------------------
def _key_geometry() -> Dict[int, Tuple[float, float]]:
    """{slot: (x01, y01)} —— x 归一化到 0..1，y 为行号/5。"""
    rows = keymap.tables().layout["rows"]
    total = keymap.tables().layout.get("totalWidth", 18.25)
    out: Dict[int, Tuple[float, float]] = {}
    for ri, row in enumerate(rows):
        for k in row:
            x = float(k["x"]) / max(1e-6, (total - 1.0))
            out[int(k["slot"])] = (min(1.0, max(0.0, x)), ri / 5.0)
    return out


_GEOM: Optional[Dict[int, Tuple[float, float]]] = None


def geometry() -> Dict[int, Tuple[float, float]]:
    global _GEOM
    if _GEOM is None:
        _GEOM = _key_geometry()
    return _GEOM


# ----------------------------------------------------------------------
# 音频分析（官方 K7/Nse 振幅 + 3 段能量，docs/music-rhythm.md §3）
# ----------------------------------------------------------------------
class Analyzer:
    def __init__(self, sample_rate: int = 48000, n_fft: int = 2048):
        self.sample_rate = int(sample_rate)
        self.n_fft = int(n_fft)
        self.window = np.hanning(n_fft).astype(np.float32)
        self.z = 0.01
        self.bases = [0.01, 0.01, 0.01]
        self.freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)
        self._ranges = [
            (self.freqs >= 20) & (self.freqs < 250),
            (self.freqs >= 250) & (self.freqs < 4000),
            (self.freqs >= 4000) & (self.freqs < 20000),
        ]

    def analyze(self, samples: np.ndarray) -> dict:
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size < self.n_fft:
            x = np.pad(x, (0, self.n_fft - x.size))
        elif x.size > self.n_fft:
            x = x[-self.n_fft:]
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
        raw = 0.6 * peak + 0.4 * rms
        if raw > self.z:
            self.z = self.z * 0.7 + raw * 0.3
        else:
            self.z = self.z * 0.992 + raw * 0.008
        self.z = max(self.z, 0.01)
        amp = min(1000, int(round(raw / self.z * 1000)))
        if amp <= 5:
            amp = 0
        spectrum = np.abs(np.fft.rfft(x * self.window)) / (self.n_fft / 2.0)
        bands = []
        for i, rng in enumerate(self._ranges):
            seg = spectrum[rng]
            e = float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0
            base = self.bases[i]
            r = 0.3 if e > base else 0.008
            base = max(base * (1 - r) + e * r, 0.01)
            self.bases[i] = base
            v = min(1000, int(round(e / base * 1000)))
            bands.append(0.0 if v <= 5 else v / 1000.0)
        return {
            "amp": amp / 1000.0,
            "bands": bands,
            "spectrum": spectrum,
            "peak": peak,
            "rms": rms,
        }


# ----------------------------------------------------------------------
# 渲染器（自研风格，官方渲染器不依赖协议，可自由替换）
# ----------------------------------------------------------------------
def _hsv(h: float, s: float, v: float) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)


def render(style: str, analysis: dict, t: float, sensitivity: float = 1.0) -> Dict[int, RGB]:
    amp = max(0.0, min(1.0, analysis["amp"] * sensitivity))
    bands = [max(0.0, min(1.0, b * sensitivity)) for b in analysis["bands"]]
    low, mid, high = bands
    colors: Dict[int, RGB] = {}
    for slot, (x, y) in geometry().items():
        if style == "spectrum":
            # 横向 EQ：左低频 → 右高频，每列高度 = 能量
            e = low * (1 - x) + mid * (1 - abs(x - 0.5) * 2) + high * x
            e = max(0.0, min(1.0, e * 1.2))
            if e < 0.02:
                colors[slot] = (0, 0, 0)
                continue
            hue = 0.66 * (1 - x) * 0.9 + 0.0
            colors[slot] = _hsv(hue, 0.95, e * (0.9 + 0.1 * math.sin(t * 3 + x * 6)))
        elif style == "rainbow":
            hue = (x * 0.8 + t * 0.12) % 1.0
            colors[slot] = _hsv(hue, 0.9, 0.15 + 0.85 * amp)
        elif style == "pulse":
            hue = (t * 0.05 + y * 0.1) % 1.0
            colors[slot] = _hsv(hue, 0.75, 0.08 + 0.9 * amp)
        elif style == "ripple":
            cx, cy = 0.5, 0.45
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / 0.62
            ring = max(0.0, 1.0 - abs(d - amp))
            v = ring * (0.25 + 0.75 * amp)
            colors[slot] = _hsv((0.55 + d * 0.35 + t * 0.05) % 1.0, 0.9, v)
        elif style == "firefly":
            wave = 0.5 + 0.5 * math.sin(t * 2.2 + x * 9 + y * 4)
            v = amp * wave
            colors[slot] = _hsv((0.12 + x * 0.1 + t * 0.02) % 1.0, 0.85, v) if v > 0.03 else (0, 0, 0)
        else:
            colors[slot] = _hsv((x + t * 0.05) % 1.0, 0.85, 0.1 + 0.8 * amp)
    return colors


STYLES = ["spectrum", "rainbow", "pulse", "ripple", "firefly"]


# ----------------------------------------------------------------------
# 音频采集
# ----------------------------------------------------------------------
class AudioCapture:
    """系统输出回环采集（Windows: soundcard / Linux: parec）。"""

    def __init__(self, device_id: Optional[str] = None, samplerate: int = 48000):
        self.device_id = device_id
        self.samplerate = int(samplerate)
        self._impl = None
        self._rec = None
        self._proc = None
        self.system = platform.system()

    # ------------------------------------------------- Windows
    def _open_windows(self):
        import soundcard as sc  # type: ignore

        if self.device_id:
            mic = sc.get_microphone(id=self.device_id, include_loopback=True)
        else:
            spk = sc.default_speaker()
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        rec = mic.recorder(samplerate=self.samplerate)
        rec.__enter__()
        self._impl = rec
        return rec

    def _read_windows(self, frames: int) -> np.ndarray:
        data = self._impl.record(numframes=frames)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        return np.asarray(data, dtype=np.float32)

    # ------------------------------------------------- Linux
    def _open_linux(self):
        device = self.device_id or "@DEFAULT_MONITOR@"
        self._proc = subprocess.Popen(
            ["parec", "--format=float32le", f"--rate={self.samplerate}",
             "--channels=2", f"--device={device}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        return self._proc

    def _read_linux(self, frames: int) -> np.ndarray:
        need = frames * 2 * 4  # 2ch float32
        buf = self._proc.stdout.read(need)
        if not buf:
            return np.zeros(frames, dtype=np.float32)
        arr = np.frombuffer(buf, dtype="<f4").reshape(-1, 2).mean(axis=1)
        return arr.astype(np.float32)

    # ------------------------------------------------- 通用
    def open(self):
        if self.system == "Windows":
            return self._open_windows()
        if self.system == "Linux":
            return self._open_linux()
        raise MK87Error(f"当前平台不支持系统音频采集: {self.system}")

    def read(self, frames: int = 2048) -> np.ndarray:
        if self.system == "Windows":
            return self._read_windows(frames)
        return self._read_linux(frames)

    def close(self):
        if self._impl is not None:
            try:
                self._impl.__exit__(None, None, None)
            except Exception:
                pass
            self._impl = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


def list_devices() -> List[dict]:
    """列出可用于音乐律动的音频设备（默认：系统输出回环）。"""
    system = platform.system()
    if system == "Windows":
        try:
            import soundcard as sc  # type: ignore

            default_speaker = sc.default_speaker()
            out = []
            for mic in sc.all_microphones(include_loopback=True):
                is_loop = bool(getattr(mic, "isloopback", False))
                out.append({
                    "id": str(mic.id),
                    "name": mic.name,
                    "loopback": is_loop,
                    "default": is_loop and default_speaker is not None
                    and default_speaker.name in mic.name,
                })
            return out
        except Exception as exc:  # noqa: BLE001
            return [{"id": None, "name": f"(音频设备不可用: {exc})", "loopback": False, "default": True}]
    if system == "Linux":
        try:
            res = subprocess.run(["pactl", "list", "short", "sources"],
                                 capture_output=True, text=True, timeout=3)
            out = []
            for line in res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    name = parts[1]
                    out.append({
                        "id": name,
                        "name": name,
                        "loopback": name.endswith(".monitor"),
                        "default": name.startswith("@DEFAULT") or ".monitor" in name,
                    })
            return out
        except Exception as exc:  # noqa: BLE001
            return [{"id": None, "name": f"(pactl 不可用: {exc})", "loopback": False, "default": True}]
    return []


# ----------------------------------------------------------------------
# 播放器
# ----------------------------------------------------------------------
class MusicPlayer:
    def __init__(self, device):
        self.device = device
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.style = "spectrum"
        self.sensitivity = 1.0
        self.fps = 20
        self.device_id: Optional[str] = None
        self.level = 0.0
        self.bands: List[float] = [0.0, 0.0, 0.0]
        self.frames = 0
        self.errors = 0
        self.last_error = ""
        self._snapshot: Optional[dict] = None
        self._capture: Optional[AudioCapture] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, device_id: Optional[str] = None, style: str = "spectrum",
              sensitivity: float = 1.0, fps: int = 20) -> dict:
        if self.device.transport != "usb":
            raise MK87Error("音乐律动仅支持 USB 有线连接（2.4G 官方不支持）")
        self.stop()
        self.style = style if style in STYLES else "spectrum"
        self.sensitivity = max(0.1, min(4.0, float(sensitivity)))
        self.fps = max(5, min(40, int(fps)))
        self.device_id = device_id
        self._snapshot = lighting.ensure_frame_mode(self.device)
        self._stop.clear()
        self.errors = 0
        self.last_error = ""
        self.frames = 0
        self._thread = threading.Thread(target=self._loop, name="mk87-music", daemon=True)
        self._thread.start()
        return self.status()

    def _loop(self) -> None:
        try:
            capture = AudioCapture(self.device_id)
            capture.open()
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = f"音频采集打开失败: {exc}"
            return
        self._capture = capture
        analyzer = Analyzer(capture.samplerate)
        period = 1.0 / self.fps
        t0 = time.time()
        next_t = time.time()
        try:
            while not self._stop.is_set():
                try:
                    samples = capture.read(2048)
                    analysis = analyzer.analyze(samples)
                    self.level = analysis["amp"]
                    self.bands = analysis["bands"]
                    colors = render(self.style, analysis, time.time() - t0, self.sensitivity)
                    payload = lighting.build_frame_payload(colors)
                    lighting.send_frame(self.device, payload, self.frames & 0xFF,
                                        wait_ack=True, timeout=0.03)
                    self.frames += 1
                except MK87Error:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = str(exc)
                    if self.errors > 50:
                        break
                next_t += period
                sleep = next_t - time.time()
                if sleep < -period:
                    next_t = time.time()
                elif sleep > 0:
                    time.sleep(sleep)
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            self.last_error = str(exc)
        finally:
            capture.close()
            self._capture = None
            if self._snapshot:
                lighting.restore_effect(self.device, self._snapshot["before"])
                self._snapshot = None

    def stop(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        return self.status()

    def status(self) -> dict:
        return {
            "running": self.running,
            "style": self.style,
            "styles": STYLES,
            "sensitivity": self.sensitivity,
            "fps": self.fps,
            "deviceId": self.device_id,
            "level": round(float(self.level), 3),
            "bands": [round(float(b), 3) for b in self.bands],
            "frames": self.frames,
            "errors": self.errors,
            "lastError": self.last_error,
            "supported": self.device.transport == "usb",
        }
