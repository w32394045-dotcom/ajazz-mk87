"""备份 / 恢复：把设备全部可写状态导出为 JSON，或写回设备。

备份内容（全部来自真机可读项）：
  keyMatrix / fnMatrix / defaultKeyMatrix / defaultFnMatrix（512B hex）
  ledEffect（16B hex） / customLedData（512B hex）
  gameMode（56B hex）
  macros（100 槽动作，逻辑重建）
  deviceInfo（48B hex + 解析）
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from . import const, keymap, lighting, macro

BACKUP_VERSION = 1
ProgressFn = Callable[[str, int], None]


def dump(device, include_defaults: bool = True) -> dict:
    """导出完整备份（不写入设备）。"""
    info = device.get_device_info()
    gm = device.get_game_mode()
    led = device.get_led_effect()
    km = keymap.read_normal_matrix(device)
    fn = keymap.read_fn_matrix(device)
    backup = {
        "format": "mk87-backup",
        "version": BACKUP_VERSION,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "transport": device.transport,
        "device": {
            "vid": info.get("vid"),
            "pid": info.get("pid"),
            "firmware": info.get("version"),
            "manufacturer": info.get("manufacturer"),
            "product": info.get("product"),
            "macroSpaceSize": info.get("macroSpaceSize"),
            "tftMaxFrames": info.get("tftMaxFrames"),
        },
        "deviceInfoRaw": bytes(info["raw"]).hex(),
        "gameModeRaw": bytes(gm["raw"]).hex(),
        "ledEffectRaw": bytes(led["raw"]).hex(),
        "keyMatrix": bytes(km).hex(),
        "fnMatrix": bytes(fn).hex(),
        "customLedData": device.read_custom_led_data().hex(),
        "macros": {
            "directory": macro.read_directory(device).hex(),
            "slots": _export_macros(device),
        },
    }
    if include_defaults:
        try:
            backup["defaultKeyMatrix"] = keymap.read_default_normal_matrix(device).hex()
            backup["defaultFnMatrix"] = keymap.read_default_fn_matrix(device).hex()
        except Exception:
            pass
    return backup


def _export_macros(device) -> list:
    table = macro.read_directory(device)
    out = []
    for slot, off in macro.decode_directory(table).items():
        try:
            head = macro.read_raw(device, off, 4)
            count = (head[0] | (head[1] << 8)) // 2
            body = macro.read_raw(device, off + 4, count * 4) if count > 0 else b""
            acts = macro.decode_block(head, body)
        except Exception:
            continue
        out.append({
            "slot": slot,
            "actions": [
                {
                    "delay": a["delay"], "usage": a["usage"],
                    "press": a["press"], "actionType": a["actionType"],
                }
                for a in acts
            ],
        })
    return out


def validate(backup: dict) -> None:
    if not isinstance(backup, dict):
        raise ValueError("备份必须是 JSON 对象")
    if backup.get("format") != "mk87-backup":
        raise ValueError("不是 MK87 备份文件（format != mk87-backup）")
    if int(backup.get("version", 0)) > BACKUP_VERSION:
        raise ValueError(f"备份版本 {backup.get('version')} 高于本工具支持的 {BACKUP_VERSION}")
    for field, size in (("keyMatrix", 1024), ("fnMatrix", 1024),
                        ("ledEffectRaw", 32), ("gameModeRaw", 112),
                        ("customLedData", 1024)):
        if field in backup and len(backup[field]) != size:
            raise ValueError(f"备份字段 {field} 长度异常（{len(backup[field])} != {size}）")


def restore(device, backup: dict, progress: Optional[ProgressFn] = None,
            restore_macros: bool = True) -> dict:
    """把备份写回设备，并逐项回读校验。"""
    validate(backup)
    result = {}

    def step(name: str, pct: int):
        if progress:
            progress(name, pct)

    # 1) 宏（先写，避免键映射指向空宏）
    if restore_macros and backup.get("macros"):
        step("macros", 5)
        slots = backup["macros"].get("slots") or []
        result["macros"] = macro.write_macros(device, slots)
    else:
        result["macros"] = {"skipped": True}

    # 2) 普通层
    step("keymap", 30)
    km = bytes.fromhex(backup["keyMatrix"])
    ok, now = keymap.write_normal_matrix(device, km, verify=True)
    result["keyMatrix"] = {"ok": bool(ok), "match": now == km if now else False}

    # 3) FN 层
    step("fn", 50)
    fn = bytes.fromhex(backup["fnMatrix"])
    ok, now = keymap.write_fn_matrix(device, fn, verify=True)
    result["fnMatrix"] = {"ok": bool(ok), "match": now == fn if now else False}

    # 4) 自定义灯
    step("customLed", 65)
    custom = bytes.fromhex(backup["customLedData"])
    read_back = device.write_custom_led_data(custom)
    result["customLedData"] = {"ok": read_back == custom}

    # 5) 灯效
    step("ledEffect", 80)
    led = bytes.fromhex(backup["ledEffectRaw"])
    device.request(const.CMD["SET_LED_EFFECT"], led, content_size=16, timeout=0.8)
    now_led = bytes(device.get_led_effect()["raw"])
    result["ledEffect"] = {"ok": now_led == led}

    # 6) 游戏模式
    step("gameMode", 90)
    gm = bytes.fromhex(backup["gameModeRaw"])
    ok, now_gm = device.set_game_mode_raw(gm, verify=True)
    result["gameMode"] = {"ok": bool(ok), "match": now_gm == gm if now_gm else False}

    step("done", 100)
    result["ok"] = all(
        isinstance(v, dict) and (v.get("ok") or v.get("match") or v.get("skipped"))
        for v in result.values()
    )
    return result
