"""TFT 屏幕（240×135）：图片/动画转换与上传、恢复官方默认动画。

协议（真机验证，见 docs/tft-page.md / docs/TEST-REPORT.md §6）：
* TFT 通道 = USB 接口 usagePage 0xFF67，payload 4104 字节（report 4105 含 report ID）；
* 每包数据区 = 4096 字节（4104 - 8 字节自定义头）；
* 单帧墙纸: SET_TFT_MATERIAL(0x4D)，头 [AA,4D,seqLo,seqHi,countLo,countHi,matLo,matHi]
  —— MK87 无壁纸页，写入不可见（保留能力，不推荐使用）；
* 动画: SET_TFT_USER_ANIMATION(0x50)，头 [AA,50,seqLo,seqHi,countLo,countHi,80,06]，
  数据 = 256 字节帧延时表 + RGB565 数据（240×135×2 = 64800 字节/帧）；
* ACK 统一为 0x41，官方实现不做逐包确认；实测吞吐 ≈ 63 KB/s（约 65ms/包）。
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import time
from typing import Callable, List, Optional, Tuple

import numpy as np

from . import const
from .errors import MK87Error, UnsupportedFeature

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

WIDTH = const.TFT_WIDTH
HEIGHT = const.TFT_HEIGHT
FRAME_BYTES = const.TFT_FRAME_BYTES  # 64800

ProgressFn = Callable[[int, int, int], None]  # pct, sent, total


# ----------------------------------------------------------------------
# 像素转换
# ----------------------------------------------------------------------
def _fit_cover(im):
    """等比缩放并居中裁剪到 240×135（与官方 setTftMaterial 行为一致）。"""
    from PIL import Image

    im = im.convert("RGB")
    src_w, src_h = im.size
    scale = max(WIDTH / src_w, HEIGHT / src_h)
    nw, nh = max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - WIDTH) // 2
    top = (nh - HEIGHT) // 2
    return im.crop((left, top, left + WIDTH, top + HEIGHT))


def _to_rgb565(im, byte_order: int = 0) -> bytes:
    """PIL Image(RGB, 240×135) → RGB565 字节流（byte_order=0 小端，1 大端）。"""
    px = im.tobytes()
    out = bytearray(WIDTH * HEIGHT * 2)
    for i in range(WIDTH * HEIGHT):
        r = px[3 * i]
        g = px[3 * i + 1]
        b = px[3 * i + 2]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
        hi = (v >> 8) & 0xFF
        lo = v & 0xFF
        if byte_order == 1:
            out[2 * i] = hi
            out[2 * i + 1] = lo
        else:
            out[2 * i] = lo
            out[2 * i + 1] = hi
    return bytes(out)


def image_to_rgb565(source, byte_order: int = 0) -> bytes:
    """图片路径或 PIL.Image → 240×135 RGB565（单帧）。"""
    from PIL import Image

    im = Image.open(source) if isinstance(source, (str, bytes, os.PathLike)) else source
    return _to_rgb565(_fit_cover(im), byte_order)


def gif_frames(source, max_frames: int = const.TFT_MAX_FRAMES,
               byte_order: int = 0) -> Tuple[List[int], bytes]:
    """GIF/多帧图片 → (delays_10ms, 拼接的 RGB565 数据)。delays 单位 = 10ms。"""
    from PIL import Image, ImageSequence

    im = Image.open(source)
    delays: List[int] = []
    chunks: List[bytes] = []
    for frame in ImageSequence.Iterator(im):
        if len(delays) >= max_frames:
            break
        chunks.append(_to_rgb565(_fit_cover(frame.convert("RGB")), byte_order))
        d = int(frame.info.get("duration", 100) or 100)
        delays.append(max(1, min(255, int(round(d / 10)))))
    if not delays:
        raise MK87Error("GIF 没有可用帧")
    return delays, b"".join(chunks)


def rgb565_to_png(data: bytes, frame_index: int = 0, byte_order: int = 0) -> bytes:
    """RGB565 数据里的某一帧 → PNG bytes（预览/导出用）。"""
    from PIL import Image

    off = frame_index * FRAME_BYTES
    chunk = data[off:off + FRAME_BYTES]
    if len(chunk) < FRAME_BYTES:
        raise MK87Error("帧数据不足")
    im = Image.new("RGB", (WIDTH, HEIGHT))
    px = []
    for i in range(WIDTH * HEIGHT):
        lo, hi = chunk[2 * i], chunk[2 * i + 1]
        if byte_order == 1:
            v = (lo << 8) | hi
        else:
            v = (hi << 8) | lo
        r = (v >> 11) & 0x1F
        g = (v >> 5) & 0x3F
        b = v & 0x1F
        px.append(((r * 255) // 31, (g * 255) // 63, (b * 255) // 31))
    im.putdata(px)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------
# 默认动画
# ----------------------------------------------------------------------
_default_cache: Optional[Tuple[List[int], bytes]] = None


def default_animation(byte_order: int = 0) -> Tuple[List[int], bytes]:
    """官方默认 135 帧动画（docs/_default_gif.json → RGB565）。"""
    global _default_cache
    if _default_cache is not None and _default_cache[1]:
        return _default_cache[0], _default_cache[1]
    from PIL import Image

    path = os.path.join(DATA_DIR, "default_animation.json")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    delays: List[int] = []
    chunks: List[bytes] = []
    for entry in doc["frameData"]:
        url = entry["dataUrl"]
        b64 = url.split(",", 1)[1]
        im = Image.open(io.BytesIO(base64.b64decode(b64)))
        chunks.append(_to_rgb565(_fit_cover(im), byte_order))
        delays.append(int(entry.get("delay", 10)) or 10)
    _default_cache = (delays, b"".join(chunks))
    return _default_cache


# ----------------------------------------------------------------------
# 上传
# ----------------------------------------------------------------------
def _check_tft(device):
    if device.transport != "usb" or device.tft_protocol is None:
        raise UnsupportedFeature("TFT 上传仅支持 USB 有线连接（2.4G 通道不支持）")


def build_animation_blob(delays: List[int], rgb565_data: bytes) -> bytes:
    """256 字节帧延时表 + RGB565 数据（官方 setTftUserAnimation 的载荷）。"""
    mv = bytearray(256)
    n = len(delays)
    mv[0] = n & 0xFF
    for i in range(max(0, n - 1)):
        mv[i + 1] = min(delays[i] * 5, 255)
    if n < 256:
        mv[n] = 0
    return bytes(mv) + bytes(rgb565_data)


def _upload(device, cmd: int, data: bytes, header_tail: bytes,
            progress: Optional[ProgressFn] = None,
            cancel_check: Optional[Callable[[], bool]] = None,
            sleep_between: float = 0.001) -> dict:
    _check_tft(device)
    iface = device.tft_protocol.iface
    body = iface.info.payload_len
    chunk = body - 8
    total = max(1, (len(data) + chunk - 1) // chunk)
    t0 = time.time()
    for k in range(total):
        if cancel_check and cancel_check():
            raise MK87Error("上传已取消")
        part = data[k * chunk:(k + 1) * chunk]
        hdr = bytes([
            0xAA, cmd & 0xFF,
            k & 0xFF, (k >> 8) & 0xFF,
            total & 0xFF, (total >> 8) & 0xFF,
            header_tail[0], header_tail[1],
        ])
        pkt = bytearray([0]) + bytearray(body)
        pkt[1:9] = hdr
        pkt[9:9 + len(part)] = part
        iface.write_report(bytes(pkt))
        if progress:
            progress(int((k + 1) * 100 / total), k + 1, total)
        if sleep_between:
            time.sleep(sleep_between)
    dt = time.time() - t0
    return {
        "ok": True,
        "packets": total,
        "bytes": len(data),
        "seconds": round(dt, 2),
        "kbps": round(len(data) / dt / 1024, 1) if dt > 0 else None,
    }


def upload_material(device, material_id: int, rgb565_data: bytes,
                    progress: Optional[ProgressFn] = None,
                    cancel_check: Optional[Callable[[], bool]] = None) -> dict:
    """单帧墙纸（0x4D）。MK87 无壁纸页 → 写入不可见。"""
    if len(rgb565_data) != FRAME_BYTES:
        raise MK87Error(f"单帧数据必须是 {FRAME_BYTES} 字节，收到 {len(rgb565_data)}")
    return _upload(device, const.CMD["SET_TFT_MATERIAL"], rgb565_data,
                   bytes([material_id & 0xFF, (material_id >> 8) & 0xFF]),
                   progress=progress, cancel_check=cancel_check)


def upload_animation(device, delays: List[int], rgb565_data: bytes,
                     progress: Optional[ProgressFn] = None,
                     cancel_check: Optional[Callable[[], bool]] = None) -> dict:
    """动画上传（0x50），帧数 ≤ tftMaxFrames。"""
    max_frames = device.status.tft_max_frames or const.TFT_MAX_FRAMES
    frame_count = len(rgb565_data) // FRAME_BYTES
    if not delays or frame_count <= 0:
        raise MK87Error("动画没有帧")
    if len(delays) != frame_count:
        raise MK87Error(f"帧数不一致：delays={len(delays)} data={frame_count}")
    if frame_count > max_frames:
        raise MK87Error(f"帧数超限：{frame_count} > 设备上限 {max_frames}")
    if len(rgb565_data) != frame_count * FRAME_BYTES:
        raise MK87Error("动画数据长度必须是整帧")
    blob = build_animation_blob(delays, rgb565_data)
    res = _upload(device, const.CMD["SET_TFT_USER_ANIMATION"], blob, bytes([80, 6]),
                  progress=progress, cancel_check=cancel_check)
    res["frames"] = frame_count
    return res


def restore_default(device, progress: Optional[ProgressFn] = None,
                    cancel_check: Optional[Callable[[], bool]] = None) -> dict:
    delays, data = default_animation(device.status.tft_byte_order)
    res = upload_animation(device, delays, data, progress=progress, cancel_check=cancel_check)
    res["default"] = True
    return res


def device_tft_info(device) -> dict:
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "frameBytes": FRAME_BYTES,
        "maxFrames": device.status.tft_max_frames or const.TFT_MAX_FRAMES,
        "pixelFormat": "rgb565",
        "byteOrder": device.status.tft_byte_order,
        "supported": device.transport == "usb" and device.tft_protocol is not None,
    }


# ======================================================================
# 高分辨率 → 240×135 动画压缩管线（自研）
#
#   空间：Lanczos/Area 降采样 + cover/contain/stretch 适配
#   时间：目标帧数 / 目标帧率重采样；uniform（等时抽帧）或 adaptive（动作优先）
#   去重：量化后相同帧合并（静态画面可从几百帧压到 1 帧）
#   色彩：RGB565 量化 + 8×8 Bayer 有序抖动（减轻渐变色带）
#
# 设备端不做任何解码：屏幕只接受 240×135 RGB565 原始帧，所以"压缩"发生在主机侧，
# 直接决定上传时间（约 146ms/包 ≈ 2.3s/帧）。
# ======================================================================
FIT_MODES = ("cover", "contain", "stretch")
TEMPORAL_MODES = ("uniform", "adaptive")
RESAMPLE_MODES = ("lanczos", "bicubic", "bilinear", "area")
#: 端到端上传速度实测估算（秒/包，见 spec-tft-wireless.md §1）
SECONDS_PER_PACKET = 0.146
MAX_INPUT_BYTES = 48 * 1024 * 1024

_RESAMPLE_MAP = {
    "lanczos": "LANCZOS",
    "bicubic": "BICUBIC",
    "bilinear": "BILINEAR",
    "area": "AREA",
}

# 8×8 Bayer 矩阵，归一化到 [-0.5, 0.5]
_BAYER8 = (np.array([
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
], dtype=np.float32) / 64.0) - 0.5


def _resample_filter(name: str):
    from PIL import Image

    resampling = getattr(Image, "Resampling", Image)  # Pillow>=9.1 用 Resampling 枚举
    return getattr(resampling, _RESAMPLE_MAP.get(name, "LANCZOS"), resampling.LANCZOS)


def _fit_to_screen(im, fit: str = "cover", resample: str = "lanczos"):
    """把任意尺寸图片适配到 240×135：cover 裁剪 / contain 黑边 / stretch 拉伸。"""
    from PIL import Image

    im = im.convert("RGB")
    filt = _resample_filter(resample)
    if fit == "stretch":
        return im.resize((WIDTH, HEIGHT), filt)
    src_w, src_h = im.size
    scale = (max if fit == "cover" else min)(WIDTH / src_w, HEIGHT / src_h)
    nw = max(1, int(round(src_w * scale)))
    nh = max(1, int(round(src_h * scale)))
    im2 = im.resize((nw, nh), filt)
    if fit == "cover":
        left = max(0, (nw - WIDTH) // 2)
        top = max(0, (nh - HEIGHT) // 2)
        return im2.crop((left, top, left + WIDTH, top + HEIGHT))
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    canvas.paste(im2, ((WIDTH - nw) // 2, (HEIGHT - nh) // 2))
    return canvas


def _rgb_to_565_matrix(rgb: np.ndarray, dither: bool = False) -> np.ndarray:
    """(H,W,3) uint8 → (H,W) uint16 RGB565；dither 时加 8×8 Bayer 抖动。"""
    h, w = rgb.shape[:2]
    if dither:
        tile = _BAYER8[np.arange(h) % 8][:, np.arange(w) % 8]
        r = rgb[..., 0].astype(np.float32) + tile * 8.0
        g = rgb[..., 1].astype(np.float32) + tile * 4.0
        b = rgb[..., 2].astype(np.float32) + tile * 8.0
    else:
        r = rgb[..., 0].astype(np.float32)
        g = rgb[..., 1].astype(np.float32)
        b = rgb[..., 2].astype(np.float32)
    r5 = (np.clip(r, 0, 255).astype(np.uint16) >> 3) & 0x1F
    g6 = (np.clip(g, 0, 255).astype(np.uint16) >> 2) & 0x3F
    b5 = (np.clip(b, 0, 255).astype(np.uint16) >> 3) & 0x1F
    return (r5 << 11) | (g6 << 5) | b5


def _frames565(frames_rgb: List, byte_order: int = 0, dither: bool = False) -> List[bytes]:
    dtype = "<u2" if byte_order == 0 else ">u2"
    out = []
    for im in frames_rgb:
        arr = np.asarray(im, dtype=np.uint8)
        out.append(_rgb_to_565_matrix(arr, dither).astype(dtype).tobytes())
    return out


def _load_source_frames(raw: bytes):
    """解码 GIF / 动态 WebP / APNG / 静图 → [(PIL.Image RGB, duration_ms)]。"""
    from PIL import Image, ImageSequence

    try:
        im = Image.open(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise MK87Error(f"无法解析图片/动画文件: {exc}") from exc
    frames = []
    try:
        for frame in ImageSequence.Iterator(im):
            dur = frame.info.get("duration", 100)
            try:
                dur = int(dur or 100)
            except Exception:
                dur = 100
            frames.append((frame.convert("RGB"), max(10, dur)))
    except Exception as exc:  # noqa: BLE001
        raise MK87Error(f"动画解码失败: {exc}") from exc
    if not frames:
        raise MK87Error("文件里没有可用帧")
    return frames


def _frame_starts(frames) -> List[int]:
    starts = []
    t = 0
    for _, d in frames:
        starts.append(t)
        t += d
    return starts


def _pick_frame_at(starts: List[int], t_ms: float) -> int:
    import bisect

    j = bisect.bisect_right(starts, t_ms) - 1
    return max(0, min(len(starts) - 1, j))


def _resample_frames(frames, n: int, temporal: str = "uniform"):
    """把源帧缩放到目标帧数 n（时间轴保持总时长）。返回 [(Image, duration_ms)]。"""
    if n >= len(frames):
        return [(im, d) for im, d in frames]
    starts = _frame_starts(frames)
    total = starts[-1] + frames[-1][1]

    if temporal == "adaptive" and len(frames) > 2:
        # 用缩略灰度图的变化量做"动作优先"抽帧：静止段少给帧，运动段多给帧
        small = [
            np.asarray(im.convert("L").resize((48, 27), _resample_filter("area")), dtype=np.float32)
            for im, _ in frames
        ]
        scores = [0.0]
        for i in range(1, len(small)):
            scores.append(float(np.mean(np.abs(small[i] - small[i - 1]))))
        cum = np.cumsum(scores)
        total_change = float(cum[-1])
        if total_change > 1e-6:
            targets = np.linspace(0.0, total_change, n + 1)[1:-1]
            idxs = [0]
            for t in targets:
                j = int(np.searchsorted(cum, t, side="left"))
                j = max(j, idxs[-1] + 1)
                idxs.append(min(j, len(frames) - 1))
            idxs[-1] = len(frames) - 1
            # 去掉重复索引（源帧不足时）
            uni = []
            for j in idxs:
                if not uni or j > uni[-1]:
                    uni.append(j)
            if uni[-1] != len(frames) - 1:
                uni.append(len(frames) - 1)
            out = []
            for k, j in enumerate(uni):
                end = starts[uni[k + 1]] if k + 1 < len(uni) else total
                out.append((frames[j][0], max(10, int(round(end - starts[j])))))
            if out:
                return out

    # uniform：按时间等分，每个输出帧覆盖一个等长时间片
    out = []
    bounds = [int(round(i * total / n)) for i in range(n + 1)]
    for k in range(n):
        t_mid = (bounds[k] + bounds[k + 1]) / 2.0
        j = _pick_frame_at(starts, t_mid)
        out.append((frames[j][0], max(10, bounds[k + 1] - bounds[k])))
    return out


def _dedupe(frames565: List[bytes], delays_ms: List[int]) -> Tuple[List[bytes], List[int]]:
    out_f, out_d = [], []
    for data, dur in zip(frames565, delays_ms):
        if out_f and data == out_f[-1]:
            out_d[-1] += dur
            continue
        out_f.append(data)
        out_d.append(dur)
    return out_f, out_d


def _png_data_url(im) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _estimate_upload(frame_count: int) -> dict:
    packets = int(math.ceil((256 + frame_count * FRAME_BYTES) / const.TFT_PACKET_DATA))
    return {
        "packets": packets,
        "bytes": 256 + frame_count * FRAME_BYTES,
        "estimatedSeconds": round(packets * SECONDS_PER_PACKET, 1),
    }


def convert_animation(
    raw: bytes,
    *,
    max_frames: int = const.TFT_MAX_FRAMES,
    frame_count: Optional[int] = None,
    fps: Optional[float] = None,
    fit: str = "cover",
    dither: bool = False,
    dedupe: bool = True,
    temporal: str = "uniform",
    pad_last: bool = False,
    resample: str = "lanczos",
    preview: bool = True,
    byte_order: int = 0,
    trim_start_frame: Optional[int] = None,
    trim_end_frame: Optional[int] = None,
) -> dict:
    """高分辨率图片/GIF → 设备可接受的 240×135 RGB565 动画。

    frame_count: 用户指定的目标帧数（1..max_frames）；None 时若给 fps 则按时长换算。
                 超过设备上限时**钳制到 max_frames 并返回 warnings**（不静默成功）。
    trim_start_frame / trim_end_frame:
                 只取源动画的第 N..M 帧（1 起始、含首尾），用于截取片段后压缩；
                 例如源 300 帧、用户选 10..150 → 只压这 141 帧。
    temporal:    uniform=等时抽帧；adaptive=动作优先抽帧（静止段少、运动段多）。
    preview:     是否返回每帧 PNG dataURL（前端预览用；上传时可关掉省内存）。
    """
    if len(raw) > MAX_INPUT_BYTES:
        raise MK87Error(f"文件过大（>{MAX_INPUT_BYTES // 1024 // 1024}MB）")
    if fit not in FIT_MODES:
        raise MK87Error(f"fit 只支持 {FIT_MODES}")
    if temporal not in TEMPORAL_MODES:
        raise MK87Error(f"temporal 只支持 {TEMPORAL_MODES}")

    warnings: List[str] = []
    source_all = _load_source_frames(raw)
    raw_source_frames = len(source_all)

    # 源帧区间裁剪（1 起始、含首尾）
    t_start = 1 if trim_start_frame is None else int(trim_start_frame)
    t_end = raw_source_frames if trim_end_frame is None else int(trim_end_frame)
    if t_start < 1 or t_end < 1 or t_start > t_end or t_end > raw_source_frames:
        raise MK87Error(
            f"帧区间无效：{t_start}..{t_end}（源动画共 {raw_source_frames} 帧，应为 1..{raw_source_frames}）"
        )
    source = source_all[t_start - 1:t_end]
    if (t_start, t_end) != (1, raw_source_frames):
        warnings.append(f"已截取源帧区间 {t_start}..{t_end}（共 {len(source)} 帧）")
    src_total = sum(d for _, d in source)
    src_frames = len(source)

    # 目标帧数（超出设备上限时钳制 + 明确提示）
    requested = None
    if frame_count is not None:
        requested = int(frame_count)
        n = requested
    elif fps:
        n = int(round(src_total / 1000.0 * float(fps)))
    else:
        n = src_frames
    max_frames = int(max_frames)
    if n > max_frames:
        warnings.append(f"目标帧数 {n} 超过设备上限 {max_frames}，已按 {max_frames} 帧压缩")
    if n < 1:
        warnings.append("目标帧数小于 1，已按 1 帧处理")
    n = max(1, min(max_frames, n, const.TFT_MAX_FRAMES))
    if requested is not None and requested < 1:
        n = 1

    selected = _resample_frames(source, n, temporal)
    fitted = [_fit_to_screen(im, fit, resample) for im, _ in selected]
    delays_ms = [int(d) for _, d in selected]
    if len(source) < n and requested is not None:
        warnings.append(f"源只有 {len(source)} 帧，无法补帧，实际 {len(selected)} 帧")

    frames565 = _frames565(fitted, byte_order, dither)
    if dedupe:
        frames565, delays_ms = _dedupe(frames565, delays_ms)

    # 帧时长 → 协议延时表单位（10ms 厘秒；表内 1 = 2ms，故 *5；上限 255）
    delays_cs = []
    clamped = 0
    for d in delays_ms:
        cs = int(round(d / 10.0))
        if cs > 51:
            cs = 51
            clamped += 1
        delays_cs.append(max(1, cs))
    if clamped:
        warnings.append(f"{clamped} 帧的单帧时长超过 510ms 上限，已截断（长停顿动画会变快）")

    # 补 1 帧：协议延时表 t[n]=0 是终止符，会顶掉最后一帧的延时槽，
    # 因此复制末帧占位，让真正最后一帧的时长也能写进表里（上限内才补）。
    pads = 1 if (pad_last and len(frames565) >= 1 and len(frames565) < int(max_frames)) else 0
    if pads:
        frames565 = frames565 + [frames565[-1]]
        # 占位帧不占实际时长（它的延时槽就是终止符），只在上传数据里占一帧
        delays_cs = delays_cs + [delays_cs[-1]]

    total_bytes = 256 + len(frames565) * FRAME_BYTES
    est = _estimate_upload(len(frames565))
    out = {
        "framesCount": len(frames565),
        "displayFrames": len(delays_ms),
        "sourceFrames": src_frames,
        "rawSourceFrames": raw_source_frames,
        "requestedFrames": requested,
        "trim": {
            "startFrame": t_start,
            "endFrame": t_end,
            "frames": src_frames,
            "trimmed": (t_start, t_end) != (1, raw_source_frames),
        },
        "sourceDurationMs": src_total,
        "delaysMs": delays_ms,
        "delaysCs": delays_cs,
        "paddedLastFrame": bool(pads),
        "clampedDelays": clamped,
        "warnings": warnings,
        "fit": fit,
        "temporal": temporal,
        "dither": bool(dither),
        "dedupe": bool(dedupe),
        "stats": {
            "sourceBytes": len(raw),
            "decodedBytes": src_frames * FRAME_BYTES,
            "outputBytes": total_bytes,
            "packets": est["packets"],
            "estimatedSeconds": est["estimatedSeconds"],
            "frameReduction": round(1 - len(frames565) / max(1, src_frames), 3),
            "sizeRatio": round(total_bytes / max(1, src_frames * FRAME_BYTES), 3),
        },
        "_frames565": frames565,
    }
    if preview:
        previews = []
        for data in frames565:
            png = rgb565_to_png(data, 0, byte_order)
            previews.append("data:image/png;base64," + base64.b64encode(png).decode("ascii"))
        out["frames"] = previews
    return out


def convert_and_upload(
    device,
    raw: bytes,
    *,
    frame_count: Optional[int] = None,
    fps: Optional[float] = None,
    fit: str = "cover",
    dither: bool = False,
    dedupe: bool = True,
    temporal: str = "uniform",
    resample: str = "lanczos",
    trim_start_frame: Optional[int] = None,
    trim_end_frame: Optional[int] = None,
    progress: Optional[ProgressFn] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """一步完成：高分辨率文件 → 压缩 → 上传（转换耗时 <2s，进度只报上传）。"""
    _check_tft(device)
    if cancel_check and cancel_check():
        raise MK87Error("上传已取消")
    res = convert_animation(
        raw,
        max_frames=device.status.tft_max_frames or const.TFT_MAX_FRAMES,
        frame_count=frame_count,
        fps=fps,
        fit=fit,
        dither=dither,
        dedupe=dedupe,
        temporal=temporal,
        pad_last=True,
        resample=resample,
        trim_start_frame=trim_start_frame,
        trim_end_frame=trim_end_frame,
        preview=False,
        byte_order=device.status.tft_byte_order,
    )
    delays = res["delaysCs"]
    data = b"".join(res["_frames565"])
    if progress:
        progress(0, 0, 1)
    meta = upload_animation(device, delays, data, progress=progress, cancel_check=cancel_check)
    meta.update({
        "sourceFrames": res["sourceFrames"],
        "outputFrames": res["framesCount"],
        "sourceDurationMs": res["sourceDurationMs"],
        "paddedLastFrame": res["paddedLastFrame"],
        "clampedDelays": res["clampedDelays"],
        "fit": fit,
        "temporal": temporal,
        "dither": bool(dither),
        "dedupe": bool(dedupe),
    })
    return meta

