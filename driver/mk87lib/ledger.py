"""灯效账本：记录 / 检测 / 恢复键盘灯效状态（v0.1.8.7）。

问题背景（2026-11-07 真机事故）
--------------------------------
音乐律动、逐帧灯效等「帧流」必须先把键盘切到**自定义族**（mode 20/21/128）才能
显示逐键帧；帧流一停，固件约 5 秒后回落到**逐键自定义表**（docs/music-rhythm.md H3）。
如果这时没有把用户原来的灯效写回去（快照 mode=0 被跳过、设备离线、进程崩溃……），
键盘就一直停在逐键态——用户会看到「律动一停就变成逐键灯效」。

真机实测（2026-11-07）确认了三种状态都可以**软件写回**：

* 写 ``SET_LED_EFFECT`` mode=1..19 → 普通灯效，``GET_LED_EFFECT`` 回读同值；
* 写 mode=20/21/128 → 进入逐键自定义显示，回读 mode=0，``GET_ALL_LIGHTS_RGB``
  返回逐键表内容（mode 128 不是 11/01 记录的「灯灭」——当逐键表为空时看起来像灭灯）；
* 写 mode=0 → 关灯。

因此本模块维护一份**持久化账本**（``%APPDATA%\\mk87\\lighting_state.json`` /
``$XDG_CONFIG_HOME/mk87/lighting_state.json``）：

* ``last``    —— 最近一次「用户可见」的灯效（普通灯效 / 关灯 / 逐键），每次切换都记录；
* ``pending`` —— 进入帧流前落盘的「结束后要恢复成什么」，恢复成功后清除；
  进程崩溃 / 拔线 / 关软件后，下一次启动或重连据此自动补恢复。

恢复优先级：帧流前的运行时快照 → 账本 ``last`` → 当前设备状态 → 静态恒亮默认值。
写回后会**回读校验**（普通灯效看 mode；关灯/逐键看 ``GET_ALL_LIGHTS_RGB`` 与逐键表），
校验失败会降级重试一次，再失败则保留 ``pending`` 等下次重连/启动重试。
"""
from __future__ import annotations

import json
import logging
import os
import platform
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple

from . import const

log = logging.getLogger("mk87.ledger")

#: 普通灯效（可写回且回读可靠）的 mode 集合
EFFECT_MODES = frozenset(range(1, 20))
#: 自定义族（逐键帧流 / 逐键自定义显示）共用同一张灯表
CUSTOM_FAMILY = (20, 21, 128)
#: 逻辑上代表「逐键自定义」的 mode（写回时用 128，回读通常归零）
CUSTOM_MODE = 128
#: 账本文件版本
SCHEMA_VERSION = 1
#: 写回后等待回读的时间（docs/lighting-hardware-test.md §4：写后立即读会读到半更新帧）
VERIFY_DELAY = 0.25

RGB = Tuple[int, int, int]


# ----------------------------------------------------------------------
# 路径 / 文件
# ----------------------------------------------------------------------
def config_dir() -> str:
    """账本所在目录（与 settings.json 同目录）。"""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "mk87")


def default_path() -> str:
    """账本文件路径；``MK87_LEDGER_PATH`` 可覆盖（单测/多配置隔离用）。"""
    override = os.environ.get("MK87_LEDGER_PATH")
    if override:
        return override
    return os.path.join(config_dir(), "lighting_state.json")


def _write_json_atomic(path: str, data: dict) -> None:
    """原子写 JSON（临时文件 + os.replace）：崩溃时不会留下半个文件。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".lighting_state.", suffix=".tmp",
                               dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ----------------------------------------------------------------------
# 状态模型（纯函数，便于单测）
# ----------------------------------------------------------------------
def make_payload(mode: int, *, rgb: Tuple[int, int, int] = (255, 255, 255),
                 brightness: int = 6, speed: int = 3, color_mode: int = 1,
                 direction: int = 0, effect_mode_type: int = 0) -> bytes:
    """构造 SET_LED_EFFECT 的 16 字节 payload（布局见 docs/lighting.md §2.1）。"""
    p = bytearray(16)
    p[0] = int(mode) & 0xFF
    p[1], p[2], p[3] = (int(x) & 0xFF for x in rgb)
    p[4] = 0xFF
    p[8] = int(color_mode) & 0xFF
    p[9] = int(brightness) & 0xFF
    p[10] = int(speed) & 0xFF
    p[11] = int(direction) & 0xFF
    p[12] = int(effect_mode_type) & 0xFF
    p[14] = 0xAA
    p[15] = 0x55
    return bytes(p)


def state_from_raw(raw, *, source: str = "device", ts: Optional[float] = None) -> dict:
    """16 字节 SET/GET_LED_EFFECT payload → 账本状态。

    mode 分类：1..19 = effect；20/21/128 = custom；0 = off（**注意**：mode=0 也可能是
    帧流残留，需要 :func:`read_state` 的 0x33 兜底判定，这里是纯函数不读设备）。
    """
    data = bytes(raw or b"")[:16]
    mode = data[0] if data else -1
    if mode in EFFECT_MODES:
        kind = "effect"
    elif mode in CUSTOM_FAMILY:
        kind = "custom"
    elif mode == 0:
        kind = "off"
    else:
        kind = "unknown"
    return {
        "kind": kind,
        "mode": int(mode),
        "raw": data.hex() if data else "",
        "rgb": [data[1], data[2], data[3]] if len(data) >= 4 else [255, 255, 255],
        "secondary": [data[5], data[6], data[7]] if len(data) >= 8 else [0, 0, 0],
        "colorMode": data[8] if len(data) >= 9 else 1,
        "brightness": data[9] if len(data) >= 10 else 6,
        "speed": data[10] if len(data) >= 11 else 3,
        "direction": data[11] if len(data) >= 12 else 0,
        "effectModeType": data[12] if len(data) >= 13 else 0,
        "source": source,
        "ts": float(ts if ts is not None else time.time()),
    }


def default_state(brightness: Optional[int] = None) -> dict:
    """兜底灯效：静态恒亮（白色）。"""
    b = 6 if brightness is None else max(1, min(6, int(brightness)))
    return state_from_raw(make_payload(1, rgb=(255, 255, 255), brightness=b),
                          source="default")


def payload_of(state: dict) -> bytes:
    """账本状态 → 可写设备的 16 字节 payload。

    逐键自定义统一写 mode=128（真机 2026-11-07 实测：128/20/21 都会进入逐键显示，
    但 128 是官方「自定义」语义、回读稳定为 0，作为恢复入口最可控）。
    """
    kind = state.get("kind")
    raw = bytes.fromhex(state.get("raw") or "")
    if len(raw) >= 16 and kind != "custom":
        return raw[:16]
    mode = int(state.get("mode") or 0)
    if kind == "custom":
        mode = CUSTOM_MODE
    elif kind == "off":
        mode = 0
    elif kind == "effect":
        mode = mode if mode in EFFECT_MODES else 1
    return make_payload(
        mode,
        rgb=tuple(state.get("rgb") or (255, 255, 255))[:3],
        brightness=int(state.get("brightness") or 6),
        speed=int(state.get("speed") or 3),
        color_mode=int(state.get("colorMode") if state.get("colorMode") is not None else 1),
        direction=int(state.get("direction") or 0),
        effect_mode_type=int(state.get("effectModeType") or 0),
    )


def _nonblack(colors: Optional[Dict[int, tuple]]) -> Dict[int, RGB]:
    out: Dict[int, RGB] = {}
    for slot, rgb in (colors or {}).items():
        try:
            r, g, b = (int(rgb[0]) & 0xFF, int(rgb[1]) & 0xFF, int(rgb[2]) & 0xFF)
        except Exception:  # noqa: BLE001
            continue
        if r or g or b:
            out[int(slot)] = (r, g, b)
    return out


def lights_match_custom(device) -> bool:
    """逐键显示判定：``GET_ALL_LIGHTS_RGB`` 的内容是否等于逐键自定义表。

    真机实测：设备处于自定义族显示时，0x33 返回逐键表；用户那张表是 5 个非黑槽
    （WASD 绿 + 空格粉），所以「非黑槽集合与颜色完全一致」才判为逐键态。
    逐键表为空时无法与「关灯」区分，按关灯处理。
    """
    try:
        table = _nonblack(device.get_custom_colors())
        frame = _nonblack(device.get_lights_frame())
    except Exception as exc:  # noqa: BLE001
        log.debug("读取逐键表/0x33 失败，无法判定逐键态: %s", exc)
        return False
    return bool(table) and table == frame


def read_state(device, *, deep: bool = True, source: str = "device") -> dict:
    """读设备当前灯效状态。

    mode 0 有两种含义（关灯 / 帧流残留的逐键态），``deep=True`` 时用 0x33 与逐键表
    比对做兜底；成本是两次 512B 读（约 60~100ms），只在必要时调用。
    """
    e = device.get_led_effect()
    state = state_from_raw(e.get("raw") if isinstance(e, dict) else e, source=source)
    if state["kind"] == "off" and deep:
        if lights_match_custom(device):
            state["kind"] = "custom"
            state["mode"] = CUSTOM_MODE
    return state


def states_match(target: dict, current: Optional[dict]) -> bool:
    """回读校验：恢复后的设备状态是否等于目标状态。"""
    if not current:
        return False
    kind = target.get("kind")
    cur_kind = current.get("kind")
    if kind == "effect":
        return cur_kind == "effect" and int(current.get("mode")) == int(target.get("mode"))
    if kind == "off":
        return cur_kind == "off"
    if kind == "custom":
        # 写入 128 后回读 mode=0；深判会走 0x33，读不到时接受自定义族 mode 回读
        return cur_kind == "custom" or int(current.get("mode") or -1) in CUSTOM_FAMILY
    return False


def _connected(device) -> bool:
    status = getattr(device, "status", None)
    if status is not None and getattr(status, "connected", None) is False:
        return False
    if hasattr(device, "protocol") and getattr(device, "protocol", None) is None:
        return False
    return True


# ----------------------------------------------------------------------
# 账本
# ----------------------------------------------------------------------
class LightingLedger:
    """持久化灯效账本（线程安全；每次变更原子落盘）。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_path()
        self.lock = threading.RLock()
        self.data: dict = {
            "version": SCHEMA_VERSION,
            "last": None,
            "pending": None,
            "updatedAt": 0.0,
        }
        self.load()

    # ---------------- 持久化 ----------------
    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                if isinstance(loaded.get("last"), dict):
                    self.data["last"] = loaded["last"]
                if isinstance(loaded.get("pending"), dict):
                    self.data["pending"] = loaded["pending"]
                self.data["updatedAt"] = float(loaded.get("updatedAt") or 0.0)
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("灯效账本读取失败（按空账本处理）: %s", exc)

    def _save_locked(self) -> None:
        # 记录更新时使用「存盘中的 last/pending」，避免半截状态
        self.data["updatedAt"] = time.time()
        try:
            _write_json_atomic(self.path, self.data)
        except Exception as exc:  # noqa: BLE001
            log.warning("灯效账本写入失败（下次再试）: %s", exc)

    # ---------------- last ----------------
    def last(self) -> Optional[dict]:
        with self.lock:
            rec = self.data.get("last")
            return dict(rec) if isinstance(rec, dict) else None

    def set_last(self, state: Optional[dict], *, source: Optional[str] = None) -> None:
        if not state or state.get("kind") not in ("effect", "custom", "off"):
            return
        rec = dict(state)
        rec["source"] = source or rec.get("source") or "app"
        rec["ts"] = time.time()
        with self.lock:
            self.data["last"] = rec
            self._save_locked()

    def clear_last(self) -> None:
        with self.lock:
            self.data["last"] = None
            self._save_locked()

    # ---------------- pending（帧流进行中 / 待恢复） ----------------
    def pending(self) -> Optional[dict]:
        with self.lock:
            rec = self.data.get("pending")
            return dict(rec) if isinstance(rec, dict) else None

    def set_pending(self, target: dict, *, reason: str = "stream") -> None:
        rec = {
            "target": dict(target),
            "reason": reason,
            "since": time.time(),
        }
        with self.lock:
            self.data["pending"] = rec
            self._save_locked()

    def clear_pending(self) -> None:
        with self.lock:
            if self.data.get("pending") is None:
                return
            self.data["pending"] = None
            self._save_locked()

    def view(self) -> dict:
        """给 API / 前端用的账本快照。"""
        with self.lock:
            return {"last": self.last(), "pending": self.pending(),
                    "updatedAt": self.data.get("updatedAt", 0.0), "path": self.path}


#: 模块级单例（服务端使用；单测用 ``new_ledger(path)`` 注入）
_default: Optional[LightingLedger] = None
_default_lock = threading.Lock()


def get() -> LightingLedger:
    global _default
    with _default_lock:
        if _default is None:
            _default = LightingLedger()
        return _default


def new_ledger(path: str) -> LightingLedger:
    """新建一个账本实例（单测用，不影响全局单例）。"""
    return LightingLedger(path)


def reset(path: Optional[str] = None) -> LightingLedger:
    global _default
    with _default_lock:
        _default = LightingLedger(path)
        return _default


# ----------------------------------------------------------------------
# 写回 / 恢复
# ----------------------------------------------------------------------
def _note_restore(mode: int, result: str) -> None:
    """把恢复结果同步给 lighting.restore_state()（shell 退出/停止音乐时等待用）。"""
    try:
        from . import lighting

        lighting.note_restore(mode, result)
    except Exception:  # noqa: BLE001
        pass


def apply_state(device, state: dict, *, verify: bool = True, reason: str = "") -> dict:
    """把账本状态写回设备并回读校验；失败返回 ok=False（不抛异常）。"""
    if not _connected(device):
        _note_restore(int(state.get("mode") or -1), "skipped-offline")
        return {"ok": False, "result": "offline", "target": state}
    raw = payload_of(state)
    mode = raw[0]
    try:
        device.request(const.CMD["SET_LED_EFFECT"], raw, content_size=16, timeout=0.8)
    except Exception as exc:  # noqa: BLE001
        _note_restore(mode, f"error: {exc}")
        log.warning("灯效写回失败（%s mode=%s）: %s", reason or "restore", mode, exc)
        return {"ok": False, "result": f"error: {exc}", "target": state}
    if not verify:
        _note_restore(mode, "restored")
        return {"ok": True, "result": "restored", "target": state}
    time.sleep(VERIFY_DELAY)
    try:
        current = read_state(device, deep=bool(state.get("kind") == "custom"))
    except Exception as exc:  # noqa: BLE001
        _note_restore(mode, f"verify-error: {exc}")
        log.warning("灯效写回后回读失败（mode=%s）: %s", mode, exc)
        return {"ok": False, "result": f"verify-error: {exc}", "target": state}
    ok = states_match(state, current)
    _note_restore(mode, "restored" if ok else "verify-mismatch")
    if ok:
        log.info("灯效已写回: kind=%s mode=%s（%s）", state.get("kind"), mode, reason or "restore")
        return {"ok": True, "result": "restored", "target": state, "current": current}
    log.warning("灯效写回后回读不一致（目标 %s/%s，实际 %s/%s）",
                state.get("kind"), mode, (current or {}).get("kind"),
                (current or {}).get("mode"))
    return {"ok": False, "result": "verify-mismatch", "target": state, "current": current}


def resolve_target(snapshot: Optional[dict] = None) -> Optional[dict]:
    """恢复目标优先级：运行时快照 → 账本 last → None。

    snapshot 可以是 ``ensure_frame_mode()`` 返回的 dict（含 ``before`` 16B）或直接 16B。
    """
    if snapshot:
        raw = snapshot.get("before") if isinstance(snapshot, dict) else snapshot
        try:
            st = state_from_raw(raw, source="snapshot")
            if st["kind"] in ("effect", "custom"):
                return st
            if st["kind"] == "off":
                # 快照 mode=0：无法区分「用户关灯」和「帧流残留」，交给账本
                pass
        except Exception:  # noqa: BLE001
            pass
    last = get().last()
    if last and last.get("kind") in ("effect", "custom", "off"):
        return last
    return None


def begin_stream(device, snapshot: Optional[dict] = None) -> dict:
    """帧流开始：计算「结束后要恢复成什么」并持久化 pending。幂等。"""
    led = get()
    pending = led.pending()
    if pending and isinstance(pending.get("target"), dict):
        target = pending["target"]
        log.info("帧流开始：沿用上次未完成的恢复目标（%s/%s）",
                 target.get("kind"), target.get("mode"))
    else:
        target = resolve_target(snapshot)
        if target is None:
            try:
                cur = read_state(device, deep=True)
                if cur.get("kind") in ("effect", "custom", "off"):
                    target = cur
            except Exception as exc:  # noqa: BLE001
                log.debug("帧流开始：读当前灯效失败: %s", exc)
        if target is None:
            target = default_state()
        led.set_pending(target, reason="stream")
    if target.get("kind") in ("effect", "custom", "off"):
        # 进入帧流前把「用户可见状态」记为 last（若账本还是空的）
        if led.last() is None:
            led.set_last(target, source="snapshot")
    log.info("帧流开始：结束后恢复目标 = %s/%s", target.get("kind"), target.get("mode"))
    return target


def end_stream(device, snapshot: Optional[dict] = None, *, reason: str = "stream-end") -> dict:
    """帧流结束：按 pending/账本恢复，成功则清 pending；失败保留等重连/启动重试。"""
    led = get()
    pending = led.pending()
    target = None
    if pending and isinstance(pending.get("target"), dict):
        target = pending["target"]
    if target is None:
        target = resolve_target(snapshot) or default_state()
        led.set_pending(target, reason=reason)
    res = apply_state(device, target, reason=reason)
    fb = default_state(target.get("brightness"))
    if (not res.get("ok") and res.get("result") != "offline"
            and states_match_rough(target, fb) is False):
        # 降级：写「静态恒亮」，避免停在逐键态；失败则保留 pending
        log.warning("灯效按账本恢复失败（%s），降级为静态恒亮", res.get("result"))
        res2 = apply_state(device, fb, reason=reason + "-fallback")
        if res2.get("ok"):
            led.set_last(fb, source="restore")
            led.clear_pending()
            return res2
        return res
    if res.get("ok"):
        led.set_last(target, source="restore")
        led.clear_pending()
    return res


def states_match_rough(target: dict, other: dict) -> bool:
    """两个账本状态是否等价（仅比较关键字段，避免 raw 字符串差异）。"""
    if not target or not other:
        return False
    if target.get("kind") != other.get("kind"):
        return False
    if int(target.get("mode") or -1) != int(other.get("mode") or -1):
        return target.get("kind") == "custom"
    return True


def public_view(state: Optional[dict]) -> dict:
    """账本状态 → 前端/WS 用的对外视图（``lighting_changed`` 事件 data）。"""
    if not state:
        return {}
    kind = state.get("kind") or "unknown"
    try:
        mode = int(state.get("mode") or -1)
    except Exception:  # noqa: BLE001
        mode = -1
    if kind == "off":
        name = "关灯"
    elif kind == "custom":
        name = "自定义（逐键）"
    else:
        try:
            from . import lighting

            name = lighting.mode_name(mode)
        except Exception:  # noqa: BLE001
            name = f"模式 {mode}"
    return {
        "kind": kind,
        "mode": mode,
        "name": name,
        "brightness": state.get("brightness"),
        "speed": state.get("speed"),
        "source": state.get("source") or "",
        "ts": float(state.get("ts") or 0.0),
    }


def flush_pending(device, *, reason: str = "reconnect") -> dict:
    """有 pending 就立刻补恢复（重连 / 启动 / 退出前调用）。"""
    led = get()
    pending = led.pending()
    if not pending or not isinstance(pending.get("target"), dict):
        return {"ok": True, "result": "none"}
    target = pending["target"]
    res = apply_state(device, target, reason=reason)
    if not res.get("ok"):
        fb = default_state(target.get("brightness"))
        res = apply_state(device, fb, reason=reason + "-fallback")
        if res.get("ok"):
            target = fb
    if res.get("ok"):
        led.set_last(target, source="restore")
        led.clear_pending()
        log.info("待恢复灯效已补写（%s）：%s/%s", reason,
                 target.get("kind"), target.get("mode"))
    else:
        log.warning("待恢复灯效补写失败（%s）: %s", reason, res.get("result"))
    return res


def resync(device, *, reason: str = "startup") -> dict:
    """启动 / 重连后对齐账本：先补 pending，否则把设备当前状态记为 last。"""
    led = get()
    if led.pending():
        return flush_pending(device, reason=reason)
    try:
        cur = read_state(device, deep=True, source="device")
    except Exception as exc:  # noqa: BLE001
        log.debug("重连后读取灯效失败: %s", exc)
        return {"ok": False, "result": f"error: {exc}"}
    if cur.get("kind") in ("effect", "custom", "off"):
        led.set_last(cur, source="device")
    return {"ok": True, "result": "synced", "current": cur}
