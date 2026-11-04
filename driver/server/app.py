"""FastAPI 服务端：REST + WebSocket + 静态前端。

接口契约见 driver/docs/design.md §4。启动方式::

    python driver/run.py [--port 8477] [--no-browser] [--mock]
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
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
from mk87lib import keymap, lighting, logsetup, macro, music, tft, trayenv, wireless
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
VERSION = "0.1.8"

manager = state.manager
log = logging.getLogger("mk87.http")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    info = logsetup.ensure_logging(console=False)
    log.info("服务启动 v%s; 日志目录=%s", VERSION, info.get("dir"))
    manager.attach_loop(asyncio.get_running_loop())
    manager.start()
    try:
        yield
    finally:
        log.info("服务关闭")
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


@app.middleware("http")
async def _log_http(request: Request, call_next):
    """完整记录每个 API 调用（成功 DEBUG、写操作 INFO、失败 WARNING/ERROR）。"""
    t0 = time.perf_counter()
    try:
        resp = await call_next(request)
    except Exception:
        log.exception("HTTP %s %s 处理异常", request.method, request.url.path)
        raise
    dt = (time.perf_counter() - t0) * 1000.0
    path = request.url.path
    if resp.status_code >= 500:
        level = logging.ERROR
    elif resp.status_code >= 400:
        level = logging.WARNING
    elif request.method == "GET":
        level = logging.DEBUG
    else:
        level = logging.INFO
    log.log(level, "%s %s -> %d (%.1f ms)", request.method, path, resp.status_code, dt)
    return resp


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
    # HTTP 中间件只记录状态码；这里补一行 message，否则音乐律动这类 400
    # 在支持日志里只剩「POST /api/music/start -> 400」，看不出具体原因。
    log.warning("MK87Error %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=400, content={"error": "mk87_error", "message": str(exc)})


@app.exception_handler(ValueError)
async def _h_value(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": "bad_request", "message": str(exc)})


@app.get("/api/version")
def api_version():
    return {"version": VERSION, "mock": False, "platform": os.name}


#: 由原生外壳（shell.py）注入：唤起主窗口
activate_callback = None
#: 由原生外壳注入：完全退出程序（托盘「退出」同一路径）
quit_callback = None
#: 由原生外壳注入：托盘实际状态（可用性 / 后端 / 错误）
tray_status_callback = None


def _tray_state() -> Optional[dict]:
    """读取外壳注入的托盘状态；浏览器模式下返回 None。"""
    if not callable(tray_status_callback):
        return None
    try:
        state = tray_status_callback()
    except Exception:  # noqa: BLE001
        log.exception("读取托盘状态失败")
        return None
    return state if isinstance(state, dict) else None


@app.post("/api/activate")
def api_activate():
    if callable(activate_callback):
        try:
            activate_callback()
            return {"ok": True, "activated": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "activated": False, "message": "无窗口外壳（浏览器模式）"}


@app.post("/api/quit")
def api_quit():
    """退出程序（设置页「退出」按钮 / 托盘退出走同一路径）。"""
    if callable(quit_callback):
        import threading as _threading

        _threading.Timer(0.3, quit_callback).start()
        return {"ok": True, "message": "程序即将退出"}
    return {"ok": False, "message": "浏览器模式：请直接关闭终端/服务进程"}


@app.get("/api/autostart")
def api_autostart_get():
    from mk87lib import autostart

    return autostart.status()


@app.put("/api/autostart")
def api_autostart_set(payload: dict = Body(...)):
    from mk87lib import autostart

    enabled = payload.get("enabled")
    if enabled is None:
        raise ValueError("缺少 enabled 字段")
    return autostart.set_enabled(bool(enabled))


@app.get("/api/status")
def api_status():
    st = manager.status()
    # 前端横幅（托盘不可用时提示「关闭窗口将退出程序」）需要托盘可用性；
    # 只放摘要，完整的桌面环境/扩展检测走 /api/tray/status。
    state = _tray_state()
    st["tray"] = {
        "available": None if state is None else state.get("available"),
        "backend": None if state is None else state.get("backend"),
    }
    return st


# ----------------------------------------------------------------------
# 系统托盘（v0.1.8）：环境检测 + GNOME AppIndicator 扩展一键安装
# ----------------------------------------------------------------------
@app.get("/api/tray/status")
def api_tray_status(refresh: bool = False):
    """托盘环境：后端/可用性、桌面环境、GNOME 扩展状态、安装方式与建议文案。"""
    state = _tray_state()
    shell_mode = bool(getattr(manager, "shell_mode", False))
    return trayenv.status(state, shell_mode=shell_mode, refresh=bool(refresh))


@app.post("/api/tray/install-extension")
def api_tray_install_extension(payload: dict = Body(default={})):
    """一键安装 GNOME AppIndicator 扩展（发行版包 + pkexec 一次提权）。

    仅桌面外壳模式可用（浏览器模式下没有提权入口，也避免任意本地网页触发提权）；
    必须带 confirm=true（前端已弹确认框）。
    """
    if not getattr(manager, "shell_mode", False):
        raise ValueError("一键安装仅在桌面版（原生外壳）中可用")
    if payload.get("confirm") is not True:
        raise ValueError("缺少 confirm=true（需要用户确认）")
    log.info("托盘：开始一键安装 AppIndicator 扩展")
    result = trayenv.install_extension()
    trayenv.reset_cache()
    log.info("托盘：一键安装结果 ok=%s message=%s", result.get("ok"), result.get("message"))
    return result


@app.post("/api/tray/enable-extension")
def api_tray_enable_extension():
    """启用已安装的 AppIndicator 扩展（免提权，写 gsettings）。"""
    if not getattr(manager, "shell_mode", False):
        raise ValueError("启用扩展仅在桌面版（原生外壳）中可用")
    log.info("托盘：启用 AppIndicator 扩展")
    result = trayenv.enable_extension()
    trayenv.reset_cache()
    log.info("托盘：启用结果 ok=%s message=%s", result.get("ok"), result.get("message"))
    return result


# ----------------------------------------------------------------------
# 日志 / 诊断包
# ----------------------------------------------------------------------
@app.get("/api/logs")
def api_logs():
    """日志状态：目录、当前会话文件、各文件大小、最近导出包。"""
    return logsetup.logging_status()


@app.post("/api/logs/export")
def api_logs_export(payload: dict = Body(default={})):
    """把完整日志 + 系统/设备信息打包成 zip，返回下载地址。"""
    extra = {
        "note": payload.get("note") or "",
        "context": payload.get("context") or "",
        "status": manager.status(),
    }
    return logsetup.export_logs(extra=extra)


@app.get("/api/logs/download")
def api_logs_download(name: str):
    p = logsetup.find_export(name)
    if not p:
        raise HTTPException(status_code=404, detail="日志包不存在或已过期")
    return FileResponse(p, filename=os.path.basename(p), media_type="application/zip")


@app.post("/api/logs/open")
def api_logs_open():
    """在文件管理器里打开日志目录。"""
    return {"ok": logsetup.open_log_dir(), "dir": logsetup.log_dir()}


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
        # 真机发现：2.4G 下 FN 层回读会返回普通层（固件行为），编辑 FN 需 USB 连接
        "fnReliable": dev.transport == "usb",
        "note": "2.4G 下 FN 层回读不可靠（返回普通层），编辑 FN 请使用 USB 有线连接"
        if dev.transport != "usb" else "",
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
        # MK87 的 GET_DEFAULT_KEY_MATRIX(0x1F) 真机返回全 0（无数据）；恢复默认 = 写 0
        "normal": keymap.decode_matrix(keymap.read_default_normal_matrix(dev)),
        "normalSupported": False,
        "fn": keymap.decode_matrix(keymap.read_default_fn_matrix(dev)),
        "fnSupported": dev.transport == "usb",
        "note": "0x1F 默认矩阵在 MK87 上无数据；恢复默认请用 POST /api/keymap/restore（写 0）",
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
    # MK87 的 frameVersion=0 ⇒ 只能写 FUNC(13)，官方 UI 不会展示 FUNC_V2(≥128)
    cat["funcV2"] = []
    cat["notes"] = {
        "funcV2": "MK87 frameVersion=0，只能使用 FUNC(13)；FUNC_V2 不展示",
        "disabled": "官方无独立「禁用」编码；工具按 HID 0x6F（⊠）写，真机未验证",
        "writeZero": "写 0 = 恢复出厂默认（keyList 内 87 槽），不是禁用",
        "fnReliable": "2.4G 下 FN 层回读返回普通层，需 USB 连接编辑 FN",
    }
    macros = []
    try:
        dev = _dev()
        table = macro.read_directory(dev)
        macros = [{"slot": s, "offset": o} for s, o in macro.decode_directory(table).items()]
        cat["macros"] = macros
        cat["macroCapacity"] = max(0, dev.status.macro_space - const.MACRO_DIR_SIZE)
    except Exception:
        cat["macros"] = []
        cat["macroCapacity"] = const.MACRO_SPACE - const.MACRO_DIR_SIZE
    return cat


# ----------------------------------------------------------------------
# 灯效
# ----------------------------------------------------------------------
@app.get("/api/lighting")
def api_lighting():
    dev = _dev()
    # mode 回读 0 时兜底读一次逐键表：fw1.19 会把自定义族固化成 mode=0，
    # 灯其实还亮着自定义逐键颜色。字段不变，只把 isCustom 修正为 true。
    return lighting.get_effect_with_custom_fallback(dev)


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
    info = tft.device_tft_info(dev)
    info.update({
        "fitModes": list(tft.FIT_MODES),
        "temporalModes": list(tft.TEMPORAL_MODES),
        "resampleModes": list(tft.RESAMPLE_MODES),
        "secondsPerPacket": tft.SECONDS_PER_PACKET,
    })
    return info


def _tft_options(payload: dict) -> dict:
    o = payload.get("options") or {}
    return {
        "frame_count": o.get("frameCount"),
        "fps": o.get("fps"),
        "fit": o.get("fit", "cover"),
        "dither": bool(o.get("dither", False)),
        "dedupe": bool(o.get("dedupe", True)),
        "temporal": o.get("temporal", "uniform"),
        "resample": o.get("resample", "lanczos"),
        "trim_start_frame": o.get("trimStartFrame"),
        "trim_end_frame": o.get("trimEndFrame"),
    }


def _decode_upload(payload: dict) -> bytes:
    data = payload.get("data") or payload.get("file")
    if not data:
        raise ValueError("缺少文件数据（data: base64）")
    try:
        return base64.b64decode(data)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"base64 解码失败: {exc}") from exc


@app.post("/api/tft/convert")
def api_tft_convert(payload: dict = Body(...)):
    """高分辨率图片/GIF → 240×135 RGB565 预览与统计（不写设备）。"""
    dev = _dev()
    raw = _decode_upload(payload)
    res = tft.convert_animation(
        raw,
        max_frames=dev.status.tft_max_frames or const.TFT_MAX_FRAMES,
        byte_order=dev.status.tft_byte_order,
        preview=True,
        **_tft_options(payload),
    )
    res.pop("_frames565", None)
    return res


@app.post("/api/tft/upload_file")
def api_tft_upload_file(payload: dict = Body(...)):
    """高分辨率图片/GIF → 压缩 → 上传（异步任务，进度走 WS）。"""
    dev = _dev()
    raw = _decode_upload(payload)
    opts = _tft_options(payload)

    def runner(progress, cancel):
        return tft.convert_and_upload(dev, raw, progress=progress, cancel_check=cancel, **opts)

    return manager.tft_job.start(kind="file", frames=0, runner=runner)


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


def _music_color(payload: dict) -> str:
    """LED 颜色覆盖 id（本工具增强）。

    「官方方案」总会带 color；「当前方案」按设计**不带** color（零改动）→ 这里回落
    default，让切回「当前方案」时自动恢复官方配色。未知 id 由 MusicEngine 再回落
    default 并打 debug 日志，所以这里只做字符串化。
    """
    color = payload.get("color")
    return music.DEFAULT_COLOR if color is None else str(color)


@app.post("/api/music/start")
def api_music_start(payload: dict = Body(default={})):
    dev = _dev()
    manager.music.device = dev
    mode = payload.get("mode")
    return manager.music.start(
        device_id=payload.get("deviceId"),
        mode=int(mode) if mode is not None else None,
        style=payload.get("style"),
        sensitivity=float(payload.get("sensitivity", 1.0)),
        # 原生帧率：15/20/30/60/66。归一/非法回落统一由 music._clamp_fps 负责
        # （这里不做 int() 强转，非法值不会变成 500，而是回落默认 20）。
        fps=payload.get("fps", music.DEFAULT_FPS),
        # 官方 v1 参数（与官方 UI 同款）
        backmode=int(payload.get("backmode", 0) or 0),
        backmode_brightness=int(payload.get("backmodeBrightness", payload.get("backBrightness", 100)) or 100),
        amplitude=(int(payload["amplitude"]) if payload.get("amplitude") is not None else None),
        # LED 颜色覆盖（本工具增强，仅「官方方案」下发；缺省 default = 官方配色）
        color=_music_color(payload),
    )


@app.post("/api/music/stop")
def api_music_stop():
    return manager.music.stop()


@app.post("/api/music/update")
def api_music_update(payload: dict = Body(default={})):
    """运行中热更新音乐律动参数（显示模式 / 背景模式 / 背景亮度 / 振幅 / 帧率 / LED 颜色）。

    color 缺省 → default：「当前方案」标签页按设计不发 color，切回时自动恢复官方配色。
    返回体同 status：``fps`` 是实测值，``targetFps`` 是帧率配置值。
    """
    manager.music.update(
        mode=(int(payload["mode"]) if payload.get("mode") is not None else None),
        amplitude=(int(payload["amplitude"]) if payload.get("amplitude") is not None else None),
        backmode=(int(payload["backmode"]) if payload.get("backmode") is not None else None),
        backmode_brightness=(int(payload["backmodeBrightness"])
                             if payload.get("backmodeBrightness") is not None else None),
        # 帧率由 music._clamp_fps 归一（15/20/30/60/66；非法值回落 20）
        fps=payload.get("fps"),
        color=_music_color(payload),
    )
    st = manager.music.status()
    st["supported"] = manager.device.status.transport == "usb"
    return st


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
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "?"
    q = manager.subscribe()
    log.info("WS 连接建立 client=%s", client)
    try:
        await websocket.send_json({"type": "status", "data": manager.status()})
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15.0)
                await websocket.send_json(ev)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": time.time()})
    except WebSocketDisconnect:
        log.info("WS 连接断开 client=%s", client)
    except Exception:
        log.exception("WS 连接异常 client=%s", client)
    finally:
        manager.unsubscribe(q)


# ----------------------------------------------------------------------
# 静态前端（必须放在最后）
# ----------------------------------------------------------------------
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
