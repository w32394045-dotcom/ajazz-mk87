"""完整日志 + 一键导出（诊断包）。

目标：成品软件出问题时，用户点一下「导出日志」就能拿到一份可直接发给开发者的 zip。

日志落盘位置：
    Windows: %LOCALAPPDATA%\\mk87\\logs
    Linux  : $XDG_STATE_HOME/mk87/logs（默认 ~/.local/state/mk87/logs）
    macOS  : ~/Library/Logs/mk87
可用环境变量 MK87_LOG_DIR 覆盖（测试/绿色版用）。

包含三份日志：
    mk87.log            滚动总日志（5 MB × 8，DEBUG，保留最近若干次运行）
    session-<时间>.log  当前这次运行的完整日志（DEBUG，达到 32 MB 后停止写入）
    errors.log          ERROR 及以上（滚动，便于快速定位）

会话日志治理：
    * 单次会话文件达到 32 MB 即停止写入，并留一条 WARNING/终止标记；
    * 启动时只保留最近 5 个 session-*.log 且总量 ≤ 64 MB，删除最旧的；
    * mk87.log / errors.log 的滚动策略不受影响。

导出内容（zip）：
    全部 *.log + system-info.txt（系统/环境/版本/设备快照）+ sessions.json + README.txt
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import platform
import shutil
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from typing import Dict, List, Optional

APP_NAME = "mk87"
_LOGGER_NAME = "mk87"
_session_file: Optional[str] = None
_session_started: Optional[str] = None
_installed = False
_lock = threading.RLock()
_max_exports = 10

#: 单次会话日志上限（达到后停止写入，避免 200 MB+ 的会话文件拖慢磁盘）。
SESSION_MAX_BYTES = 32 * 1024 * 1024
#: 启动清理：session-*.log 最多保留的文件数与总量。
SESSION_KEEP_FILES = 5
SESSION_TOTAL_MAX_BYTES = 64 * 1024 * 1024


# ----------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------
def log_dir() -> str:
    env = os.environ.get("MK87_LOG_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME, "logs")
    if system == "Darwin":
        return os.path.expanduser("~/Library/Logs/mk87")
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, APP_NAME, "logs")


def export_dir() -> str:
    d = os.path.join(log_dir(), "exports")
    os.makedirs(d, exist_ok=True)
    return d


def _app_version() -> str:
    try:
        from . import __version__  # noqa: PLC0415

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "?"


# ----------------------------------------------------------------------
# 初始化
# ----------------------------------------------------------------------
def _fmt() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


class _SessionFileHandler(logging.FileHandler):
    """会话日志 handler：达到体积上限后写一条终止标记并停止写入。

    文件名保持 ``session-<时间>.log`` 不变（导出逻辑无需感知滚动/后缀）；
    上限只影响本次会话文件，``mk87.log`` 仍按 5 MB × 8 滚动。
    """

    def __init__(self, filename: str, max_bytes: Optional[int] = None,
                 encoding: str = "utf-8") -> None:
        super().__init__(filename, mode="a", encoding=encoding)
        self.max_bytes = max(1, int(SESSION_MAX_BYTES if max_bytes is None else max_bytes))
        try:
            self._written = os.path.getsize(filename)
        except OSError:
            self._written = 0
        self._capped = False
        self._capped_at: Optional[str] = None

    @property
    def capped(self) -> bool:
        """是否已因超过上限而停止写入。"""
        return self._capped

    def emit(self, record: logging.LogRecord) -> None:
        if self._capped:
            return
        try:
            # 防御：第三方（如 uvicorn 默认 dictConfig）可能 close 掉已装的 handler，
            # 导致 stream 变 None。这里按需重开，避免每条日志都抛 "Logging error"。
            if self.stream is None:
                self.stream = self._open()
            msg = self.format(record) + self.terminator
            data_len = len(msg.encode(self.encoding or "utf-8", "replace"))
            if self._written + data_len > self.max_bytes:
                self._cap()
                return
            self.stream.write(msg)
            self._written += data_len
            self.flush()
        except Exception:  # noqa: BLE001 - 单条日志失败不应影响应用
            self.handleError(record)

    def _cap(self) -> None:
        if self._capped:
            return
        self._capped = True
        self._capped_at = datetime.now().isoformat(timespec="seconds")
        marker = (
            f"===== 会话日志达到上限 {self.max_bytes / 1048576.0:.1f} MB，"
            f"已停止写入（{self._capped_at}；完整日志见 mk87.log）=====\n"
        )
        try:
            self.stream.write(marker)
            self.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            # 本 handler 已标记 capped，这条 WARNING 不会递归写回会话文件。
            logging.getLogger(f"{_LOGGER_NAME}.logsetup").warning(
                "会话日志达到上限 %.1f MB，已停止写入: %s",
                self.max_bytes / 1048576.0, self.baseFilename)
        except Exception:  # noqa: BLE001
            pass


def cleanup_session_logs(directory: Optional[str] = None,
                         keep: Optional[int] = None,
                         total_max: Optional[int] = None,
                         exclude: Optional[str] = None) -> dict:
    """清理陈旧会话日志：只保留最近 ``keep`` 个且总量 ≤ ``total_max``。

    默认值在调用时读取模块常量（便于测试注入小上限）。
    只处理 ``session-*.log``（不碰 mk87.log / errors.log / exports）。
    ``exclude`` 用于保护当前正在写的会话文件。删除失败（被占用）不重试，
    避免卡住启动。
    """
    d = os.path.abspath(directory or log_dir())
    keep = max(1, int(SESSION_KEEP_FILES if keep is None else keep))
    total_max = max(1, int(SESSION_TOTAL_MAX_BYTES if total_max is None else total_max))
    excluded = os.path.abspath(exclude) if exclude else None
    try:
        names = [n for n in os.listdir(d)
                 if n.startswith("session-") and n.endswith(".log")]
    except OSError:
        return {"dir": d, "removed": [], "failed": [], "kept": 0, "totalBytes": 0}

    entries = []
    for name in names:
        path = os.path.join(d, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        entries.append({
            "name": name,
            "path": path,
            "size": int(st.st_size),
            "mtime": float(st.st_mtime),
            "excluded": bool(excluded and os.path.abspath(path) == excluded),
        })
    # 旧 → 新；同名时间戳按文件名兜底。
    entries.sort(key=lambda e: (e["mtime"], e["name"]))
    candidates = [e for e in entries if not e["excluded"]]
    removed: List[str] = []
    failed: List[str] = []

    def _remaining() -> List[dict]:
        gone = set(removed)  # 删除失败的文件仍占空间，继续计入 kept/totalBytes
        return [e for e in entries if e["name"] not in gone]

    while True:
        remaining = _remaining()
        if len(remaining) <= keep and sum(e["size"] for e in remaining) <= total_max:
            break
        if not candidates:
            break
        victim = candidates.pop(0)
        try:
            os.remove(victim["path"])
            removed.append(victim["name"])
        except OSError:
            failed.append(victim["name"])

    remaining = _remaining()
    return {
        "dir": d,
        "removed": removed,
        "failed": failed,
        "kept": len(remaining),
        "totalBytes": sum(e["size"] for e in remaining),
        "keptNames": [e["name"] for e in remaining],
    }


def _ensure_console_safe() -> bool:
    try:
        return bool(sys.stderr) and sys.stderr.isatty() or sys.stdout is not None
    except Exception:  # noqa: BLE001
        return False


def _write_session_header(path: str) -> None:
    info = session_info()
    lines = [
        "=" * 78,
        f"MK87 Studio 日志会话  {info['startedAt']}",
        f"版本      : {info['version']}  ({'frozen/exe' if info['frozen'] else 'source'})",
        f"平台      : {info['platform']}  {info['machine']}",
        f"Python    : {info['python']}",
        f"PID       : {info['pid']}",
        f"命令行    : {' '.join(info['argv'])}",
        f"运行目录  : {info['cwd']}",
        "=" * 78,
    ]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _install_exception_hooks() -> None:
    log = logging.getLogger(_LOGGER_NAME)

    def _sys_hook(exc_type, exc, tb):  # noqa: ANN001
        if issubclass(exc_type, KeyboardInterrupt):
            return
        log.critical("未捕获异常:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _sys_hook

    def _thread_hook(args):  # noqa: ANN001
        log.critical(
            "线程未捕获异常 (%s):\n%s",
            getattr(args.thread, "name", "?"),
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    try:
        threading.excepthook = _thread_hook
    except Exception:  # noqa: BLE001
        pass


def setup_logging(level: str = "DEBUG", console: bool = True,
                  role: str = "app", tag: Optional[str] = None,
                  session_max_bytes: Optional[int] = None) -> dict:
    """安装日志（幂等）。role 只用于会话文件命名/头部标记，如 app/shell/tray。"""
    global _installed, _session_file, _session_started
    with _lock:
        if _installed:
            return logging_status()
        d = log_dir()
        os.makedirs(d, exist_ok=True)
        now = datetime.now()
        _session_started = now.isoformat(timespec="seconds")
        name = f"session-{now.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.log"
        _session_file = os.path.join(d, name)
        _write_session_header(_session_file)
        cap = (SESSION_MAX_BYTES if session_max_bytes is None
               else max(1, int(session_max_bytes)))
        # 启动时清理陈旧会话日志（保护当前文件；只动 session-*.log）。
        cleanup = cleanup_session_logs(d, exclude=_session_file)

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        for h in list(root.handlers):  # 清掉 basicConfig 等残留 handler，避免重复
            root.removeHandler(h)

        fmt = _fmt()
        session_h = _SessionFileHandler(_session_file, max_bytes=cap, encoding="utf-8")
        session_h.setLevel(logging.DEBUG)
        session_h.setFormatter(fmt)
        root.addHandler(session_h)

        main_h = logging.handlers.RotatingFileHandler(
            os.path.join(d, "mk87.log"), maxBytes=5 * 1024 * 1024,
            backupCount=8, encoding="utf-8")
        main_h.setLevel(logging.DEBUG)
        main_h.setFormatter(fmt)
        root.addHandler(main_h)

        err_h = logging.handlers.RotatingFileHandler(
            os.path.join(d, "errors.log"), maxBytes=2 * 1024 * 1024,
            backupCount=3, encoding="utf-8")
        err_h.setLevel(logging.ERROR)
        err_h.setFormatter(fmt)
        root.addHandler(err_h)

        if console and _ensure_console_safe():
            try:
                con = logging.StreamHandler(sys.stderr or sys.stdout)
                con.setLevel(logging.INFO)
                con.setFormatter(fmt)
                root.addHandler(con)
            except Exception:  # noqa: BLE001
                pass

        logging.captureWarnings(True)
        _install_exception_hooks()
        _installed = True
        log = logging.getLogger(f"{_LOGGER_NAME}.logsetup")
        log.info(
            "日志已初始化 role=%s tag=%s dir=%s session=%s level=%s "
            "会话上限=%.1fMB 清理旧会话: 删除%d 失败%d 保留%d (%.1fMB)",
            role, tag or "", d, name, level, cap / 1048576.0,
            len(cleanup["removed"]), len(cleanup["failed"]), cleanup["kept"],
            cleanup["totalBytes"] / 1048576.0,
        )
        return logging_status()


def ensure_logging(console: bool = True) -> dict:
    """在未初始化时兜底初始化（run.py / shell.py / cli.py 都可安全调用）。"""
    if _installed:
        return logging_status()
    return setup_logging(console=console)


# ----------------------------------------------------------------------
# 状态 / 会话信息
# ----------------------------------------------------------------------
def session_info() -> dict:
    return {
        "app": "MK87 Studio",
        "version": _app_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "pid": os.getpid(),
        "startedAt": _session_started or datetime.now().isoformat(timespec="seconds"),
        "argv": list(sys.argv),
        "cwd": os.getcwd(),
    }


def _file_info(path: str) -> dict:
    try:
        st = os.stat(path)
        return {
            "name": os.path.basename(path),
            "path": path,
            "size": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }
    except OSError:
        return {"name": os.path.basename(path), "path": path, "size": 0, "modified": ""}


def list_logs() -> List[dict]:
    d = log_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".log"):
            continue
        info = _file_info(os.path.join(d, name))
        info["session"] = name.startswith("session-")
        info["current"] = bool(_session_file and name == os.path.basename(_session_file))
        out.append(info)
    return out


def logging_status() -> dict:
    d = log_dir()
    files = list_logs()
    exports = []
    ed = os.path.join(d, "exports")
    if os.path.isdir(ed):
        exports = [_file_info(os.path.join(ed, n)) for n in sorted(os.listdir(ed))
                   if n.endswith(".zip")]
    device = None
    try:
        from . import music  # noqa: F401  (确保包已加载)

        device = _device_snapshot()
    except Exception:  # noqa: BLE001
        device = None
    return {
        "dir": d,
        "session": _session_file,
        "sessionStartedAt": _session_started,
        "installed": _installed,
        "files": files,
        "totalSize": sum(f["size"] for f in files),
        "exports": exports[-_max_exports:],
        "info": session_info(),
        "device": device,
    }


def _device_snapshot() -> Optional[dict]:
    """尽力抓一份设备状态（失败不影响导出）。"""
    try:
        from server import state  # noqa: PLC0415

        dev = getattr(state.manager, "device", None)
        if dev is None:
            return None
        st = dev.status
        return {
            "connected": bool(getattr(st, "connected", False)),
            "transport": getattr(st, "transport", ""),
            "product": getattr(st, "product", ""),
            "firmware": getattr(st, "firmware", ""),
            "vid": getattr(st, "vid", None),
            "pid": getattr(st, "pid", None),
            "battery": getattr(st, "battery", None),
            "charging": getattr(st, "charging", None),
            "batterySource": getattr(st, "battery_source", ""),
            "workMode": getattr(st, "work_mode", None),
            "tftMaxFrames": getattr(st, "tft_max_frames", None),
            "tftByteOrder": getattr(st, "tft_byte_order", None),
            "lastError": getattr(st, "last_error", ""),
        }
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------
# 导出
# ----------------------------------------------------------------------
def _read_text(path: str, max_bytes: int = 8 * 1024 * 1024) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
        return data.decode("utf-8", "replace")
    except OSError:
        return ""


def export_logs(extra: Optional[Dict[str, object]] = None,
                dest: Optional[str] = None) -> dict:
    """把完整日志 + 环境信息打包成 zip，返回 {path,name,size,files,createdAt}。"""
    with _lock:
        d = log_dir()
        os.makedirs(d, exist_ok=True)
        out_dir = os.path.abspath(dest) if dest else export_dir()
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"mk87-logs-{ts}.zip"
        path = os.path.join(out_dir, name)
        info = session_info()
        if extra:
            info["extra"] = extra
        dev = _device_snapshot()
        logs = [f for f in list_logs() if f["size"] > 0]
        written = []
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for f in logs:
                try:
                    z.write(f["path"], arcname=f["name"])
                    written.append(f)
                except OSError:
                    # 日志刚被清理/占用时不中断导出，跳过该文件继续打包其余内容。
                    continue
            z.writestr("system-info.txt",
                       json.dumps({"session": info, "device": dev}, ensure_ascii=False, indent=2))
            z.writestr("sessions.json",
                       json.dumps([{"name": f["name"], "size": f["size"],
                                    "modified": f["modified"], "current": f["current"]}
                                   for f in written], ensure_ascii=False, indent=2))
            z.writestr("README.txt", _export_readme(info, dev, written))
        # 清理旧导出（保留最近 N 个）
        try:
            olds = sorted(
                (os.path.join(out_dir, n) for n in os.listdir(out_dir)
                 if n.startswith("mk87-logs-") and n.endswith(".zip")),
                key=os.path.getmtime)
            for old in olds[:-_max_exports]:
                os.remove(old)
        except OSError:
            pass
        sz = os.path.getsize(path)
        logging.getLogger(f"{_LOGGER_NAME}.logsetup").info(
            "导出日志: %s (%d 文件, %.1f KB)", path, len(written), sz / 1024.0)
        return {
            "ok": True,
            "path": path,
            "name": name,
            "size": sz,
            "files": len(written),
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "downloadUrl": f"/api/logs/download?name={name}",
        }


def _export_readme(info: dict, device: Optional[dict], logs: List[dict]) -> str:
    lines = [
        "MK87 Studio 诊断日志包",
        "=" * 40,
        f"导出时间   : {datetime.now().isoformat(timespec='seconds')}",
        f"应用版本   : {info['version']}",
        f"运行方式   : {'打包 exe' if info['frozen'] else '源码运行'}",
        f"平台       : {info['platform']}",
        f"Python     : {info['python']}",
        f"启动时间   : {info['startedAt']}",
        f"日志目录   : {log_dir()}",
        "",
        f"包含 {len(logs)} 个日志文件：",
    ]
    for f in logs:
        lines.append(f"  - {f['name']}  ({f['size'] / 1024.0:.1f} KB)")
    lines += ["", "设备状态：",
              json.dumps(device, ensure_ascii=False, indent=2) if device else "  (未连接/不可用)",
              "", "日志级别为 DEBUG，包含 HID 收发概要（大报文仅记录头部与长度）。"]
    return "\n".join(lines)


def find_export(name: str) -> Optional[str]:
    """按文件名找导出 zip（防目录穿越）。"""
    if not name or "/" in name or "\\" in name or not name.endswith(".zip"):
        return None
    p = os.path.join(export_dir(), os.path.basename(name))
    return p if os.path.isfile(p) else None


def open_log_dir() -> bool:
    """在系统文件管理器里打开日志目录。"""
    d = log_dir()
    os.makedirs(d, exist_ok=True)
    try:
        if platform.system() == "Windows":
            os.startfile(d)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            import subprocess

            subprocess.Popen(["open", d])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", d])
        return True
    except Exception:  # noqa: BLE001
        return False


def redact(text: str, limit: int = 200) -> str:
    """日志里大报文只留头部（供 HID 层写日志用）。"""
    if text is None:
        return ""
    try:
        s = text if isinstance(text, str) else bytes(text).hex()
    except Exception:  # noqa: BLE001
        return str(text)
    return s if len(s) <= limit else f"{s[:limit]}…({len(s)}B)"
