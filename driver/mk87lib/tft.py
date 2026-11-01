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
import os
import time
from typing import Callable, List, Optional, Tuple

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
