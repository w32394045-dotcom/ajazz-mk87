"""开机自启（Windows / Linux）。

* Windows：写 `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`
* Linux  ：写 `~/.config/autostart/mk87.desktop`

统一以 `--tray` 参数启动（安静启动到系统托盘，不弹主窗口）。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Dict

APP_KEY = "MK87Studio"
APP_NAME = "MK87 Studio"
LINUX_DESKTOP = """[Desktop Entry]
Type=Application
Name={name}
Comment=AJAZZ MK87 keyboard configuration tool (unofficial)
Exec={cmd}
Icon=mk87
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
"""


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def launch_command() -> str:
    """返回开机自启时执行的完整命令行（带 --tray）。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    shell = os.path.join(_project_root(), "shell.py")
    return f'"{sys.executable}" "{shell}" --tray'


def _linux_desktop_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", "mk87.desktop")


# ----------------------------------------------------------------------
# Windows
# ----------------------------------------------------------------------
def _win_run_key():
    import winreg  # noqa: PLC0415

    return winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"


def _win_is_enabled() -> bool:
    import winreg  # noqa: PLC0415

    root, path = _win_run_key()
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_KEY)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _win_enable() -> None:
    import winreg  # noqa: PLC0415

    root, path = _win_run_key()
    with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_KEY, 0, winreg.REG_SZ, launch_command())


def _win_disable() -> None:
    import winreg  # noqa: PLC0415

    root, path = _win_run_key()
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_KEY)
    except FileNotFoundError:
        pass
    except OSError:
        pass


# ----------------------------------------------------------------------
# Linux
# ----------------------------------------------------------------------
def _linux_is_enabled() -> bool:
    return os.path.exists(_linux_desktop_path())


def _linux_enable() -> None:
    path = _linux_desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(LINUX_DESKTOP.format(name=APP_NAME, cmd=launch_command()))


def _linux_disable() -> None:
    try:
        os.remove(_linux_desktop_path())
    except FileNotFoundError:
        pass


# ----------------------------------------------------------------------
# 公共接口
# ----------------------------------------------------------------------
def supported() -> bool:
    return platform.system() in ("Windows", "Linux")


def status() -> Dict[str, object]:
    system = platform.system()
    if system == "Windows":
        enabled = _win_is_enabled()
        location = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    elif system == "Linux":
        enabled = _linux_is_enabled()
        location = _linux_desktop_path()
    else:
        enabled = False
        location = ""
    return {
        "supported": supported(),
        "enabled": bool(enabled),
        "command": launch_command(),
        "location": location,
        "platform": system,
    }


def enable() -> Dict[str, object]:
    if not supported():
        raise RuntimeError(f"当前平台不支持开机自启: {platform.system()}")
    if platform.system() == "Windows":
        _win_enable()
    else:
        _linux_enable()
    return status()


def disable() -> Dict[str, object]:
    if not supported():
        raise RuntimeError(f"当前平台不支持开机自启: {platform.system()}")
    if platform.system() == "Windows":
        _win_disable()
    else:
        _linux_disable()
    return status()


def set_enabled(enabled: bool) -> Dict[str, object]:
    return enable() if enabled else disable()
