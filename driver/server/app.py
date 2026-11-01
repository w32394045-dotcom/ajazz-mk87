"""FastAPI 服务端：REST + WebSocket + 静态前端。

接口契约见 driver/docs/design.md §4。启动方式::

    python driver/run.py [--port 8477] [--no-browser] [--mock]
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mk87lib import backup as backup_mod
from mk87lib import keymap, lighting, macro, music, tft, wireless
from mk87lib import const
from mk87lib.errors import (
    DeviceDisconnected,
    DeviceNotFound,
    MK87Error,
    ProtocolTimeout,
    UnsupportedFeature,
)
from server import state

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
VERSION = "0.1.0"

manager = state.manager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    manager.attach_loop(asyncio.get_running_loop())
    manager.start()
    try:
        yield
    finally:
        manager.stop()


app = FastAPI(
    title="MK87 Config",
    version=VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# 通用
# ----------------------------------------------------------------------
def _dev():
    return manager.require()


def _hex(b) -> str:
    return bytes(b).hex() if b is not None else ""


@app.exception_handler(DeviceNotFound)
async def _h_not_found(request: Request, exc: DeviceNotFound):
    return JSONResponse(status_code=503, content={"error": "device_not_found", "message": str(exc)})


@app.exception_handler(DeviceDisconnected)
async def _h_disconnected(request: Request, exc: DeviceDisconnected):
    return JSONResponse(status_code=503, content={"error": "device_disconnected", "message": str(exc)})


@app.exception_handler(ProtocolTimeout)
async def _h_timeout(request: Request, exc: ProtocolTimeout):
    return JSONResponse(status_code=504, content={"error": "protocol_timeout", "message": str(exc)})


@app.exception_handler(UnsupportedFeature)
async def _h_unsupported(request: Request, exc: UnsupportedFeature):
    return JSONResponse(status_code=400, content={"error": "unsupported", "message": str(exc)})


@app.exception_handler(MK87Error)
async def _h_mk87(request: Request, exc: MK87Error):
    return JSONResponse(status_code=400, content={"error": "mk87_error", "message": str(exc)})


@app.exception_handler(ValueError)
async def _h_value(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": "bad_request", "message": str(exc)})


@app.get("/api/version")
def api_version():
    return {"version": VERSION, "mock": False, "platform": os.name}


@app.get("/api/status")
def api_status():
    return manager.status()


@app.post("/api/device/scan")
def api_scan():
    ok = manager._try_connect(quiet=True)
    st = manager.status()
    st["ok"] = ok
    if not ok:
        st["error"] = "未找到设备（请检查 USB 线 / 2.4G 接收器 / 设备驱动状态）"
    return st


# ----------------------------------------------------------------------
# 设备信息 / 设置 / 时间 / 调试
# ----------------------------------------------------------------------
@app.get("/api/device/info")
def api_device_info():
    dev = _dev()
    info = dev.get_device_info()
    info["raw"] = _hex(info["raw"])
    gm = dev.get_game_mode()
    gm["raw"] = _hex(gm["raw"])
    return {"info": info, "gameMode": gm, "status": manager.status()}


@app.get("/api/device/game-mode")
def api_game_mode():
    dev = _dev()
    gm = dev.get_game_mode()
    gm["raw"] = _hex(gm["raw"])
    return gm


@app.put("/api/device/game-mode")
def api_set_game_mode(payload: dict = Body(...)):
    dev = _dev()
    return wireless.set_game_mode_fields(dev, payload.get("fields") or payload)


@app.post("/api/device/time-sync")
def api_time_sync():
    dev = _dev()
    echo = dev.sync_time()
    return {"ok": True, "echo": _hex(echo)}


@app.post("/api/device/factory-reset")
def api_factory_reset(payload: dict = Body(default={})):
    if not payload.get("confirm"):
        raise ValueError("危险操作需要 confirm=true")
    dev = _dev()
    ok = dev.factory_reset()
    return {"ok": ok}


@app.post("/api/device/raw")
def api_raw(payload: dict = Body(...)):
    """高级调试：发送原始帧。

    两种模式：
      {"frame": [字节...]}                 直接写一个完整 report（自动补 report ID）
      {"cmd": 16, "data": [...], "content_size": 48}  走标准请求/响应
    """
    dev = _dev()
    if "frame" in payload:
        data = bytes(int(x) & 0xFF for x in payload["frame"])
        pkt = data if data and data[0] == 0 else bytes([0]) + data
        with dev._lock:  # noqa: SLF001
            dev.protocol.iface.write_report(pkt)
            resp = dev.protocol.iface.read_normalized(timeout=float(payload.get("timeout", 1.0)))
        return {"response": _hex(resp) if resp else None}
    cmd = int(payload.get("cmd", 0))
    data = bytes(int(x) & 0xFF for x in (payload.get("data") or []))
    content_size = payload.get("content_size")
    resp = dev.request(cmd, data, content_size=int(content_size) if content_size is not None else None,
                       timeout=float(payload.get("timeout", 1.0)),
                       retries=int(payload.get("retries", 1)))
    return {"cmd": cmd, "response": _hex(resp), "length": len(resp)}


@app.get("/api/device/notifications")
def api_notifications():
    return {"notifications": [e for e in manager.device.recent_events
                              if e.get("type") == "notification"][-50:]}


# ----------------------------------------------------------------------
# 改键 / FN
# ----------------------------------------------------------------------
@app.get("/api/keymap/layout")
def api_keymap_layout():
    return keymap.get_layout()


@app.get("/api/keymap")
def api_keymap():
    dev = _dev()
    normal = keymap.decode_matrix(keymap.read_normal_matrix(dev))
    fn = keymap.decode_matrix(keymap.read_fn_matrix(dev))
    return {
        "normal": normal,
        "fn": fn,
        "layout": keymap.get_layout()["layout"],
        "slotKeys": keymap.get_layout()["keyListBySlot"],
    }


@app.put("/api/keymap/normal")
def api_keymap_normal(payload: dict = Body(...)):
    dev = _dev()
    patches = {int(k): v for k, v in (payload.get("slots") or {}).items()}
    res = keymap.patch_matrix(dev, "normal", patches)
    if res.get("ok"):
        now = keymap.decode_matrix(keymap.read_normal_matrix(dev))
        res["normal"] = now
    return res


@app.put("/api/keymap/fn")
def api_keymap_fn(payload: dict = Body(...)):
    dev = _dev()
    patches = {int(k): v for k, v in (payload.get("slots") or {}).items()}
    res = keymap.patch_matrix(dev, "fn", patches)
    if res.get("ok"):
        res["fn"] = keymap.decode_matrix(keymap.read_fn_matrix(dev))
    return res


@app.get("/api/keymap/defaults")
def api_keymap_defaults():
    dev = _dev()
    return {
        "normal": keymap.decode_matrix(keymap.read_default_normal_matrix(dev)),
        "fn": keymap.decode_matrix(keymap.read_default_fn_matrix(dev)),
    }


@app.post("/api/keymap/restore")
def api_keymap_restore(payload: dict = Body(default={})):
    dev = _dev()
    layer = payload.get("layer", "normal")
    slots = payload.get("slots")
    out = {}
    if layer in ("normal", "both"):
        out["normal"] = keymap.restore_layer(dev, "normal", slots)
    if layer in ("fn", "both"):
        out["fn"] = keymap.restore_layer(dev, "fn", slots)
    return out


@app.get("/api/keymap/actions")
def api_keymap_actions():
    cat = keymap.get_actions_catalog()
    macros = []
    try:
        dev = _dev()
        table = macro.read_directory(dev)
        macros = [{"slot": s, "offset": o} for s, o in macro.decode_directory(table).items()]
    except Exception:
        pass
    cat["macros"] = macros
    return cat


# ----------------------------------------------------------------------
# 灯效
# ----------------------------------------------------------------------
@app.get("/api/lighting")
def api_lighting():
    dev = _dev()
    return lighting.get_effect(dev)


@app.put("/api/lighting")
def api_lighting_set(payload: dict = Body(...)):
    dev = _dev()
    cur = lighting.get_effect(dev)
    lighting.set_effect(
        dev,
        mode=int(payload.get("mode", cur["mode"])),
        rgb=tuple(payload.get("rgb", cur["rgb"])),
        secondary=tuple(payload.get("secondary", cur["secondary"])),
        color_mode=int(payload.get("colorMode", cur["colorMode"])),
        brightness=int(payload.get("brightness", cur["brightness"])),
        speed=int(payload.get("speed", cur["speed"])),
        direction=int(payload.get("direction", cur["direction"])),
        effect_mode_type=int(payload.get("effectModeType", cur["effectModeType"])),
    )
    return lighting.get_effect(dev)


@app.get("/api/lighting/modes")
def api_lighting_modes():
    return {
        "modes": lighting.get_modes(),
        "params": lighting.data()["params"],
        "custom": lighting.data()["custom"],
        "customFamily": list(lighting.CUSTOM_FAMILY),
        "customMode": lighting.CUSTOM_MODE,
    }


@app.get("/api/lighting/custom")
def api_custom_led():
    dev = _dev()
    return lighting.get_custom(dev)


@app.put("/api/lighting/custom")
def api_custom_led_set(payload: dict = Body(...)):
    dev = _dev()
    colors = {int(k): tuple(v) for k, v in (payload.get("colors") or {}).items()}
    res = lighting.set_custom(
        dev, colors,
        apply=bool(payload.get("apply", True)),
        brightness=int(payload.get("brightness", 5)),
        speed=int(payload.get("speed", 3)),
    )
    res["colors"] = {str(k): list(v) for k, v in sorted(colors.items())}
    return res


# ---- 逐键帧流（供「AI 灯效 / 自定义动画」调试） ----
class _FrameHolder:
    def __init__(self):
        self.colors = {}
        self.streamer = None


frame_holder = _FrameHolder()


@app.post("/api/lighting/frames/start")
def api_frames_start(payload: dict = Body(default={})):
    dev = _dev()
    frame_holder.colors = {int(k): tuple(v) for k, v in (payload.get("colors") or {}).items()}
    if frame_holder.streamer is not None:
        frame_holder.streamer.stop()
    fps = int(payload.get("fps", 20))
    streamer = lighting.FrameStreamer(dev, lambda: dict(frame_holder.colors), fps=fps)
    streamer.start()
    frame_holder.streamer = streamer
    return streamer.status()


@app.post("/api/lighting/frames/push")
def api_frames_push(payload: dict = Body(...)):
    frame_holder.colors = {int(k): tuple(v) for k, v in (payload.get("colors") or {}).items()}
    return {"ok": True, "keys": len(frame_holder.colors)}


@app.post("/api/lighting/frames/stop")
def api_frames_stop():
    if frame_holder.streamer is not None:
        frame_holder.streamer.stop()
        frame_holder.streamer = None
    return {"ok": True}


@app.get("/api/lighting/frames/status")
def api_frames_status():
    if frame_holder.streamer is None:
        return {"running": False, "fps": 0, "frames": 0, "acks": 0, "errors": 0, "lastError": ""}
    return frame_holder.streamer.status()


# ----------------------------------------------------------------------
# 宏
# ----------------------------------------------------------------------
@app.get("/api/macros")
def api_macros():
    dev = _dev()
    with manager.lock:
        return macro.read_all_macros(dev)


@app.put("/api/macros")
def api_macros_set(payload: dict = Body(...)):
    dev = _dev()
    slots = payload.get("slots") or []
    with manager.lock:
        res = macro.write_macros(dev, slots)
        if res.get("ok"):
            res["macros"] = macro.read_all_macros(dev)
    return res


@app.delete("/api/macros/{slot}")
def api_macro_delete(slot: int):
    dev = _dev()
    with manager.lock:
        data = macro.read_all_macros(dev)
        slots = [{"slot": s["slot"], "actions": s["actions"]}
                 for s in data["slots"] if s["slot"] != slot]
        res = macro.write_macros(dev, slots)
        if res.get("ok"):
            res["macros"] = macro.read_all_macros(dev)
    return res


# ----------------------------------------------------------------------
# TFT
# ----------------------------------------------------------------------
@app.get("/api/tft")
def api_tft():
    dev = _dev()
    return tft.device_tft_info(dev)


@app.post("/api/tft/upload")
def api_tft_upload(payload: dict = Body(...)):
    dev = _dev()
    mode = payload.get("mode", "animation")
    frames_b64 = payload.get("frames") or []
    if not frames_b64:
        raise ValueError("frames 不能为空")
    blobs = []
    for item in frames_b64:
        raw = base64.b64decode(item)
        if len(raw) != tft.FRAME_BYTES:
            raise ValueError(f"每帧必须是 {tft.FRAME_BYTES} 字节 RGB565（收到 {len(raw)}）")
        blobs.append(raw)
    data = b"".join(blobs)
    if mode == "static":
        def runner(progress, cancel):
            return tft.upload_material(dev, 0, blobs[0], progress=progress, cancel_check=cancel)
        return manager.tft_job.start(kind="static", frames=1, runner=runner)

    fps = max(1, min(30, int(payload.get("fps", 10))))
    delays = [max(1, int(round(100 / fps)))] * len(blobs)  # 单位 10ms
    def runner(progress, cancel):
        return tft.upload_animation(dev, delays, data, progress=progress, cancel_check=cancel)
    return manager.tft_job.start(kind="animation", frames=len(blobs), runner=runner)


@app.post("/api/tft/default")
def api_tft_default():
    dev = _dev()
    def runner(progress, cancel):
        return tft.restore_default(dev, progress=progress, cancel_check=cancel)
    return manager.tft_job.start(kind="default", frames=135, runner=runner)


@app.get("/api/tft/job")
def api_tft_job():
    return manager.tft_job.status()


@app.post("/api/tft/cancel")
def api_tft_cancel():
    return manager.tft_job.cancel()


# ----------------------------------------------------------------------
# 音乐律动
# ----------------------------------------------------------------------
@app.get("/api/music/devices")
def api_music_devices():
    return {"devices": music.list_devices(), "system": music.platform.system()}


@app.post("/api/music/start")
def api_music_start(payload: dict = Body(default={})):
    dev = _dev()
    manager.music.device = dev
    return manager.music.start(
        device_id=payload.get("deviceId"),
        style=payload.get("style", "spectrum"),
        sensitivity=float(payload.get("sensitivity", 1.0)),
        fps=int(payload.get("fps", 20)),
    )


@app.post("/api/music/stop")
def api_music_stop():
    return manager.music.stop()


@app.get("/api/music/status")
def api_music_status():
    st = manager.music.status()
    st["supported"] = manager.device.status.transport == "usb"
    return st


# ----------------------------------------------------------------------
# 2.4G / 按键测试 / 备份 / 设置
# ----------------------------------------------------------------------
@app.get("/api/wireless")
def api_wireless():
    dev = _dev()
    return wireless.get_info(dev)


@app.put("/api/wireless")
def api_wireless_set(payload: dict = Body(...)):
    dev = _dev()
    if "sleepTime" in payload:
        res = wireless.set_sleep_time(dev, payload["sleepTime"])
    else:
        res = wireless.set_game_mode_fields(dev, payload)
    res["info"] = wireless.get_info(dev)
    return res


@app.post("/api/keytest/start")
def api_keytest_start():
    manager.keytest.start()
    return manager.keytest.status()


@app.post("/api/keytest/stop")
def api_keytest_stop():
    manager.keytest.stop()
    return manager.keytest.status()


@app.get("/api/keytest/status")
def api_keytest_status():
    return manager.keytest.status()


@app.get("/api/backup")
def api_backup():
    dev = _dev()
    with manager.lock:
        return backup_mod.dump(dev)


@app.post("/api/backup/restore")
def api_backup_restore(payload: dict = Body(...)):
    if not payload.get("confirm"):
        raise ValueError("危险操作需要 confirm=true")
    dev = _dev()
    doc = payload.get("backup") or payload
    with manager.lock:
        return backup_mod.restore(dev, doc)


@app.get("/api/settings")
def api_settings():
    return manager.settings.get()


@app.put("/api/settings")
def api_settings_set(payload: dict = Body(...)):
    return manager.settings.update(payload)


# ----------------------------------------------------------------------
# WebSocket
# ----------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    q = manager.subscribe()
    try:
        await websocket.send_json({"type": "status", "data": manager.status()})
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15.0)
                await websocket.send_json(ev)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.unsubscribe(q)


# ----------------------------------------------------------------------
# 静态前端（必须放在最后）
# ----------------------------------------------------------------------
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
