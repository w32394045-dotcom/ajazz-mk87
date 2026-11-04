#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux 托盘环境探测 + GNOME AppIndicator 扩展安装引导（纯标准库）。

背景
----
2026-11-05 用户反馈 Linux 下托盘图标右键没有菜单。根因：本项目托盘原来走 pystray，
Linux 上没有 GTK/AppIndicator 的 `gi` 绑定时 pystray 总是回退到 `_xorg` 后端，而该
后端 `HAS_MENU = False`（只处理左键 activate）。v0.1.8 起 Linux 改用 Qt 的
`QSystemTrayIcon`（见 `tray_linux.py`），它自带右键菜单（StatusNotifierItem/dbusmenu）。

GNOME 上还有第二层问题：GNOME Shell 原生不显示任何托盘图标，必须安装
`gnome-shell-extension-appindicator`（Ubuntu 预装的同源扩展 uuid 不同）。本模块负责
把「桌面环境 / 会话类型 / 扩展是否安装与启用 / 可用的安装方式」探测出来，供设置页
「系统托盘」卡片与一键安装接口使用。

设计约束
--------
* 纯标准库，Windows 上也能 import（单测在 Windows + Ubuntu 两条 CI 矩阵都跑）；
* 不 import Qt / pystray，不触碰 GUI 线程；
* 所有子进程调用带超时，失败只降级不抛异常；
* 探测结果缓存 30s（/api/status 会带托盘摘要，不能每次轮询都跑 `gnome-shell --version`）。

一键安装策略（用户 2026-11-05 确认）
-----------------------------------
优先「发行版包 + 一次提权」（`pkexec`，其次 `sudo`）：
* 发行版维护的包与当前 GNOME Shell 版本匹配，不会出现「zip 版本不对被 Shell 拒载」；
* 失败 / 没有 pkexec / 没有包管理器时，前端回退成复制命令让用户自己执行。
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence

#: 上游 / Fedora / Debian 包里的扩展 uuid
APPINDICATOR_UUID = "appindicatorsupport@rgcjonas.gmail.com"
#: Ubuntu 预装的是同一个扩展的 Ubuntu 分支，uuid 不同
APPINDICATOR_UUID_UBUNTU = "ubuntu-appindicators@ubuntu.com"
APPINDICATOR_UUIDS: Sequence[str] = (APPINDICATOR_UUID, APPINDICATOR_UUID_UBUNTU)
#: 各发行版里的包名（Fedora / Debian / Ubuntu / openSUSE / Arch 通用）
PACKAGE_NAME = "gnome-shell-extension-appindicator"

GNOME_FAMILIES = {"gnome"}

#: 探测缓存 TTL（秒）
PROBE_TTL = 30.0

_LOG_PREFIX = "[trayenv] "


def _log(msg: str) -> None:
    # 不依赖 logging 初始化顺序：设置页可能在服务启动早期就调用
    try:
        import logging

        logging.getLogger("mk87.trayenv").info("%s", msg)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------
# 基础命令执行
# ----------------------------------------------------------------------
def _run(cmd: Sequence[str], timeout: float = 8.0, env: Optional[dict] = None) -> tuple:
    """执行命令，返回 (returncode, stdout, stderr)。任何异常都折成返回码。"""
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "命令不存在"
    except subprocess.TimeoutExpired:
        return 124, "", f"命令超时（>{timeout:.0f}s）"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def _tail(text: str, limit: int = 3000) -> str:
    text = text or ""
    return text if len(text) <= limit else "…" + text[-limit:]


def _which(name: str, path: Optional[str] = None) -> Optional[str]:
    try:
        return shutil.which(name, path=path)
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------
# 桌面环境 / 会话
# ----------------------------------------------------------------------
def read_os_release(path: Optional[str] = None) -> Dict[str, str]:
    """解析 /etc/os-release（Linux），返回小写 key 的字典；失败返回 {}。"""
    candidates = [path] if path else ["/etc/os-release", "/usr/lib/os-release"]
    for candidate in candidates:
        try:
            with open(candidate, encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError:
            continue
        data: Dict[str, str] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            data[key.strip().lower()] = value
        if data:
            return data
    return {}


def desktop_family(current: str) -> str:
    """把 XDG_CURRENT_DESKTOP / DESKTOP_SESSION 归一化成桌面家族。"""
    c = (current or "").lower()
    if not c:
        return "unknown"
    if any(k in c for k in ("gnome", "ubuntu", "pop", "unity")):
        return "gnome"
    if "kde" in c or "plasma" in c:
        return "kde"
    if "xfce" in c:
        return "xfce"
    if "cinnamon" in c:
        return "cinnamon"
    if "mate" in c:
        return "mate"
    if "lxqt" in c:
        return "lxqt"
    if "lxde" in c:
        return "lxde"
    if "budgie" in c:
        return "budgie"
    if "deepin" in c:
        return "deepin"
    return "unknown"


#: 用于从 `ubuntu:GNOME` 这类复合值里挑出更好看的显示名
_KNOWN_DESKTOP_TOKENS = {
    "gnome", "kde", "plasma", "xfce", "cinnamon", "mate", "lxqt", "lxde",
    "budgie", "deepin", "unity", "pantheon", "sway", "i3", "kylin", "cosmic",
}


def _display_desktop(raw: str) -> str:
    """`ubuntu:GNOME` → `GNOME`；未知组合退回最长的一段。"""
    parts = [p for p in re.split(r"[:;]", raw or "") if p]
    if not parts:
        return ""
    known = [p for p in parts if p.lower() in _KNOWN_DESKTOP_TOKENS]
    if known:
        return max(known, key=len)
    return max(parts, key=len)


def desktop_environment(environ: Optional[dict] = None) -> Dict[str, object]:
    """解析当前桌面环境与会话类型。

    XDG_CURRENT_DESKTOP 可能形如 `ubuntu:GNOME`、`KDE`、`XFCE`、`X-Cinnamon`。
    没有 XDG_SESSION_TYPE 时按 WAYLAND_DISPLAY / DISPLAY 推断。
    """
    env = os.environ if environ is None else environ
    current = (env.get("XDG_CURRENT_DESKTOP") or "").strip()
    desktop_session = (env.get("DESKTOP_SESSION") or "").strip()
    raw = current or desktop_session
    display_name = _display_desktop(raw)
    session_type = (env.get("XDG_SESSION_TYPE") or "").strip().lower()
    if not session_type:
        if env.get("WAYLAND_DISPLAY"):
            session_type = "wayland"
        elif env.get("DISPLAY"):
            session_type = "x11"
        else:
            session_type = ""
    return {
        "currentDesktop": display_name,
        "rawDesktop": raw,
        "desktopSession": desktop_session,
        "sessionType": session_type,
        "family": desktop_family(raw),
        "isWayland": session_type == "wayland",
    }


def _is_linux(system: Optional[str] = None) -> bool:
    return (system or platform.system()) == "Linux"


# ----------------------------------------------------------------------
# GNOME Shell / 扩展
# ----------------------------------------------------------------------
def gnome_shell_version() -> Optional[str]:
    """`gnome-shell --version`，返回如 "47.0"；失败返回 None。"""
    rc, out, _ = _run(["gnome-shell", "--version"], timeout=6.0)
    if rc == 0 and out:
        m = re.search(r"(\d+(?:\.\d+){1,3})", out)
        if m:
            return m.group(1)
    return None


def _extension_dirs() -> List[str]:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return [
        os.path.join(data_home, "gnome-shell", "extensions"),
        "/usr/share/gnome-shell/extensions",
        "/usr/local/share/gnome-shell/extensions",
        "/var/lib/flatpak/exports/share/gnome-shell/extensions",
    ]


def extension_dirs() -> List[str]:
    """当前用户可见的 GNOME Shell 扩展目录（用户级 + 系统级）。"""
    return _extension_dirs()


def _parse_gsettings_list(text: str) -> List[str]:
    """解析 `gsettings get org.gnome.shell enabled-extensions` 的输出。"""
    return re.findall(r"'([^']+)'", text or "")


def _gsettings_list(key: str) -> Optional[List[str]]:
    rc, out, _ = _run(["gsettings", "get", "org.gnome.shell", key], timeout=6.0)
    if rc != 0:
        return None
    return _parse_gsettings_list(out)


def _gnome_extension_info_state(uuid: str) -> Optional[str]:
    """`gnome-extensions info <uuid>` 的 State 字段（ENABLED / DISABLED / ...）。"""
    rc, out, _ = _run(["gnome-extensions", "info", uuid], timeout=6.0)
    if rc != 0:
        return None
    m = re.search(r"^State:\s*(\S+)", out, re.MULTILINE)
    return m.group(1).upper() if m else None


def extension_state() -> Dict[str, object]:
    """探测 AppIndicator 扩展：是否安装、是否启用、系统级还是用户级。"""
    paths: List[str] = []
    matched_uuid: Optional[str] = None
    for directory in _extension_dirs():
        for uuid in APPINDICATOR_UUIDS:
            candidate = os.path.join(directory, uuid)
            if os.path.isdir(candidate):
                paths.append(candidate)
                matched_uuid = matched_uuid or uuid
    installed = bool(paths)
    home = os.path.expanduser("~")
    system_wide = any(not os.path.abspath(p).startswith(home) for p in paths)

    enabled: Optional[bool] = None
    enabled_source: Optional[str] = None
    uuid_for_enable = matched_uuid or APPINDICATOR_UUID
    if _which("gsettings") or _which("gnome-extensions"):
        enabled_list = _gsettings_list("enabled-extensions")
        disabled_list = _gsettings_list("disabled-extensions")
        if enabled_list is not None:
            enabled_source = "gsettings"
            active = [u for u in APPINDICATOR_UUIDS if u in enabled_list]
            blocked = [u for u in APPINDICATOR_UUIDS if disabled_list and u in disabled_list]
            if blocked:
                enabled = False
            elif active:
                enabled = True
                uuid_for_enable = active[0]
            else:
                # 扩展默认关闭：装了但不在 enabled-extensions 里 = 未启用
                enabled = False if installed else None
    if enabled is None and installed:
        state = _gnome_extension_info_state(uuid_for_enable)
        if state is not None:
            enabled = state == "ENABLED"
            enabled_source = "gnome-extensions"
    return {
        "uuid": uuid_for_enable,
        "installed": installed,
        "enabled": enabled,
        "enabledSource": enabled_source,
        "systemWide": system_wide,
        "paths": paths,
    }


# ----------------------------------------------------------------------
# 包管理器 / 提权
# ----------------------------------------------------------------------
#: (id, 可执行文件, 安装参数, 显示名)
_MANAGERS = (
    ("dnf", "dnf", ["install", "-y", PACKAGE_NAME], "Fedora / RHEL / CentOS"),
    ("apt", "apt-get", ["install", "-y", PACKAGE_NAME], "Debian / Ubuntu"),
    ("zypper", "zypper", ["install", "-y", PACKAGE_NAME], "openSUSE"),
    ("pacman", "pacman", ["-S", "--noconfirm", PACKAGE_NAME], "Arch Linux"),
)

ADVICE = {
    "ok": {
        "zh": "系统托盘正常：左键显示主窗口，右键可打开菜单（显示主窗口 / 开机自启 / 退出）。",
        "en": "System tray is working: click to show the window, right-click for the menu "
              "(Show window / Launch at start-up / Quit).",
    },
    "windows-ok": {
        "zh": "Windows 使用系统通知区域（pystray 后端），托盘与右键菜单始终可用，无需额外组件。",
        "en": "Windows uses the native notification area (pystray backend); the tray icon and "
              "right-click menu are always available and need no extra component.",
    },
    "browser": {
        "zh": "当前是浏览器模式（没有原生外壳），没有系统托盘。用桌面版启动即可使用托盘。",
        "en": "Running in browser mode (no native shell), so there is no system tray. "
              "Start the desktop app to use the tray.",
    },
    "gnome-missing-extension": {
        "zh": "GNOME 默认不显示托盘图标，需要安装 AppIndicator 扩展后才能显示 MK87 Studio 的托盘"
              "（装完需注销重新登录）。",
        "en": "GNOME does not show tray icons by default. Install the AppIndicator extension to "
              "show the MK87 Studio tray icon (log out and back in after installing).",
    },
    "gnome-extension-disabled": {
        "zh": "已安装 AppIndicator 扩展但尚未启用；启用并注销重新登录后托盘图标才会出现。",
        "en": "The AppIndicator extension is installed but not enabled. Enable it and log out/in "
              "for the tray icon to appear.",
    },
    "gnome-needs-relogin": {
        "zh": "AppIndicator 扩展已安装并启用，但当前登录会话还没加载它。"
              "Wayland 下请注销重新登录；X11 下可按 Alt+F2 输入 r 重启 GNOME Shell。",
        "en": "The AppIndicator extension is installed and enabled, but the current session has "
              "not loaded it yet. Log out and back in on Wayland; on X11 press Alt+F2 and run r.",
    },
    "no-tray-host": {
        "zh": "当前桌面环境没有提供系统托盘宿主（或未启用托盘插件），托盘图标无法显示。"
              "这种情况下关闭窗口会直接退出程序。",
        "en": "The current desktop environment provides no system tray host (or its tray plugin "
              "is disabled), so the tray icon cannot be shown. Closing the window quits the app.",
    },
    "unsupported": {
        "zh": "当前平台没有系统托盘支持。",
        "en": "System tray is not supported on this platform.",
    },
}

_REASON_TEXT = {
    "install": (
        "可以一键安装 AppIndicator 扩展（需要一次管理员密码）。",
        "The AppIndicator extension can be installed in one click (one admin password prompt).",
    ),
    "unsupported-platform": (ADVICE["unsupported"]["zh"], ADVICE["unsupported"]["en"]),
    "not-gnome": (
        "当前桌面环境不需要 AppIndicator 扩展（非 GNOME）。",
        "No AppIndicator extension is needed on this desktop (not GNOME).",
    ),
    "already-enabled": (
        "AppIndicator 扩展已安装并启用。",
        "The AppIndicator extension is already installed and enabled.",
    ),
    "installed-disabled": (
        "扩展已安装但未启用，只需启用（无需提权）。",
        "The extension is installed but disabled; just enable it (no root needed).",
    ),
    "no-package-manager": (
        "没有识别到受支持的包管理器，请按下方命令手动安装。",
        "No supported package manager found; install manually with the commands below.",
    ),
    "no-elevation": (
        "系统里没有 pkexec / sudo，无法自动提权，请按下方命令手动安装。",
        "Neither pkexec nor sudo is available, so automatic installation is not possible; "
        "install manually with the commands below.",
    ),
}


def package_manager(which=None) -> Dict[str, object]:
    """识别发行版包管理器。`which` 可注入（单测用）。"""
    finder = which or _which
    # 原子化系统（Fedora Silverblue / Bazzite 等）优先用 rpm-ostree，避免 dnf 只改临时层
    if os.path.exists("/run/ostree-booted") and finder("rpm-ostree"):
        return {
            "id": "rpm-ostree",
            "label": "Fedora Atomic / Silverblue",
            "path": finder("rpm-ostree"),
            "args": ["install", "-y", PACKAGE_NAME],
            "rebootRequired": True,
        }
    for manager_id, exe, args, label in _MANAGERS:
        path = finder(exe)
        if path:
            return {
                "id": manager_id,
                "label": label,
                "path": path,
                "args": list(args),
                "rebootRequired": False,
            }
    return {"id": None, "label": "", "path": None, "args": [], "rebootRequired": False}


def elevation_tool(which=None) -> Optional[str]:
    """首选提权工具：pkexec（图形密码框）→ sudo。"""
    finder = which or _which
    for name in ("pkexec", "sudo"):
        if finder(name):
            return name
    return None


def _shell_join(cmd: Sequence[str]) -> str:
    if sys.platform == "win32":
        return " ".join(cmd)
    import shlex

    return " ".join(shlex.quote(part) for part in cmd)


def manual_commands(plan: Optional[dict] = None) -> List[str]:
    """给用户复制的手动命令（带发行版包管理器版本）。"""
    plan = plan or install_plan()
    manager = plan.get("manager") or {}
    commands: List[str] = []
    if manager.get("id") == "rpm-ostree":
        commands.append(f"sudo rpm-ostree install {PACKAGE_NAME}")
        commands.append("sudo systemctl reboot  # 原子化系统需重启后生效")
    elif manager.get("id") == "dnf":
        commands.append(f"sudo dnf install -y {PACKAGE_NAME}")
    elif manager.get("id") == "apt":
        commands.append("sudo apt update")
        commands.append(f"sudo apt install -y {PACKAGE_NAME}")
    elif manager.get("id") == "zypper":
        commands.append(f"sudo zypper install -y {PACKAGE_NAME}")
    elif manager.get("id") == "pacman":
        commands.append(f"sudo pacman -S --noconfirm {PACKAGE_NAME}")
    else:
        commands.append(f"# 在发行版包管理器中安装 {PACKAGE_NAME}")
    commands.append(f"gnome-extensions enable {APPINDICATOR_UUID}")
    commands.append("# Wayland：注销重新登录；X11：Alt+F2 → r")
    return commands


def install_plan(
    *,
    extension: Optional[dict] = None,
    desktop: Optional[dict] = None,
    which=None,
    system: Optional[str] = None,
) -> Dict[str, object]:
    """给当前环境生成安装计划（是否支持、命令、提权方式、失败原因）。"""
    desktop = desktop or desktop_environment()
    ext = extension or extension_state()
    platform_name = (system or platform.system()).lower()

    def plan(supported: bool, reason: str, **extra) -> Dict[str, object]:
        base = {
            "supported": supported,
            "reason": reason,
            "reasonText": {"zh": _REASON_TEXT.get(reason, ("", ""))[0],
                           "en": _REASON_TEXT.get(reason, ("", ""))[1]},
            "manager": None,
            "package": PACKAGE_NAME,
            "command": [],
            "commandText": "",
            "needsRoot": True,
            "elevatedVia": None,
            "rebootRequired": False,
            "needsEnable": False,
            "manualCommands": [],
        }
        base.update(extra)
        base["manualCommands"] = manual_commands(base)
        return base

    if platform_name == "windows" or platform_name == "darwin":
        return plan(False, "unsupported-platform")
    if desktop.get("family") != "gnome":
        return plan(False, "not-gnome")
    if ext.get("installed") and ext.get("enabled"):
        return plan(False, "already-enabled")
    if ext.get("installed") and not ext.get("enabled"):
        return plan(False, "installed-disabled", needsEnable=True)

    manager = package_manager(which=which)
    if not manager.get("id"):
        return plan(False, "no-package-manager")
    elevator = elevation_tool(which=which)
    if not elevator:
        return plan(False, "no-elevation", manager=manager,
                    command=list(manager.get("args") or []))
    command = [elevator, manager["path"], *(manager.get("args") or [])]
    return plan(
        True,
        "install",
        manager=manager,
        command=command,
        commandText=_shell_join(command),
        needsRoot=True,
        elevatedVia=elevator,
        rebootRequired=bool(manager.get("rebootRequired")),
    )


# ----------------------------------------------------------------------
# 一键安装 / 启用
# ----------------------------------------------------------------------
def enable_extension(*, timeout: float = 20.0) -> Dict[str, object]:
    """启用 AppIndicator 扩展（免提权）。

    先试 `gnome-extensions enable`（需要 Shell 已扫描到扩展，刚装完时经常失败），
    失败则直接写 gsettings —— 这条路径不依赖 Shell 运行时，注销重登后生效。
    """
    ext = extension_state()
    uuid = str(ext.get("uuid") or APPINDICATOR_UUID)

    rc, out, err = _run(["gnome-extensions", "enable", uuid], timeout=timeout)
    if rc == 0:
        return {"ok": True, "uuid": uuid, "method": "gnome-extensions",
                "message": "扩展已启用", "output": _tail(out + "\n" + err)}

    enabled_list = _gsettings_list("enabled-extensions")
    if enabled_list is None:
        return {
            "ok": False,
            "uuid": uuid,
            "message": "无法启用扩展：gsettings 不可用",
            "output": _tail(out + "\n" + err),
            "manualCommands": manual_commands(),
        }
    if uuid not in enabled_list:
        enabled_list.append(uuid)
    variant = "[" + ", ".join("'" + item.replace("'", "") + "'" for item in enabled_list) + "]"
    rc2, out2, err2 = _run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", variant],
                           timeout=timeout)
    disabled_list = _gsettings_list("disabled-extensions") or []
    if uuid in disabled_list:
        remaining = [item for item in disabled_list if item != uuid]
        variant2 = "[" + ", ".join("'" + item.replace("'", "") + "'" for item in remaining) + "]"
        _run(["gsettings", "set", "org.gnome.shell", "disabled-extensions", variant2],
             timeout=timeout)
    if rc2 != 0:
        return {
            "ok": False,
            "uuid": uuid,
            "message": "写入 enabled-extensions 失败",
            "output": _tail((out + "\n" + err + "\n" + out2 + "\n" + err2).strip()),
            "manualCommands": manual_commands(),
        }
    return {
        "ok": True,
        "uuid": uuid,
        "method": "gsettings",
        "message": "已把扩展加入启用列表，注销重新登录（Wayland）或 Alt+F2 → r（X11）后生效",
        "output": _tail(out2 + "\n" + err2),
    }


def install_extension(*, timeout: float = 300.0, which=None) -> Dict[str, object]:
    """一键安装 AppIndicator 扩展（发行版包 + 一次提权），随后自动启用。

    返回 dict：ok / message / command / output / needsLogout / rebootRequired / state。
    失败时附带 manualCommands，前端回退成「复制命令」。
    """
    desktop = desktop_environment()
    ext = extension_state()
    plan = install_plan(extension=ext, desktop=desktop, which=which)

    if plan.get("needsEnable") and not plan.get("supported"):
        enabled = enable_extension(timeout=min(timeout, 30.0))
        return {
            "ok": bool(enabled.get("ok")),
            "message": enabled.get("message") or "启用扩展失败",
            "command": [],
            "output": enabled.get("output") or "",
            "needsLogout": bool(enabled.get("ok")) and desktop.get("isWayland"),
            "needsReload": bool(enabled.get("ok")),
            "rebootRequired": False,
            "state": extension_state(),
            "manualCommands": disabled_manual_commands(),
        }
    if not plan.get("supported"):
        reason = (plan.get("reasonText") or {})
        return {
            "ok": False,
            "message": reason.get("zh") or "当前环境无法自动安装扩展",
            "command": [],
            "output": "",
            "needsLogout": False,
            "needsReload": False,
            "rebootRequired": False,
            "state": ext,
            "manualCommands": plan.get("manualCommands") or manual_commands(plan),
        }

    command = list(plan.get("command") or [])
    _log("安装 AppIndicator 扩展：" + _shell_join(command))
    env = os.environ.copy()
    if (plan.get("manager") or {}).get("id") == "apt":
        env["DEBIAN_FRONTEND"] = "noninteractive"
    rc, out, err = _run(command, timeout=timeout, env=env)
    output = _tail("\n".join(part for part in (out, err) if part).strip())

    if rc != 0:
        return {
            "ok": False,
            "message": f"安装失败（退出码 {rc}）" + ("，可能已取消提权或没有网络" if rc in (126, 127) else ""),
            "command": command,
            "commandText": plan.get("commandText") or _shell_join(command),
            "output": output or "（无输出）",
            "needsLogout": False,
            "needsReload": False,
            "rebootRequired": False,
            "state": extension_state(),
            "manualCommands": plan.get("manualCommands") or manual_commands(plan),
        }

    # 安装成功 → 再启用（免提权）。刚装完 Shell 一般还没扫描到，enable 内部会回退 gsettings。
    after = extension_state()
    enable_result: Dict[str, object] = {}
    if after.get("installed") and not after.get("enabled"):
        enable_result = enable_extension(timeout=min(timeout, 30.0))
        after = extension_state()
    needs_logout = bool(desktop.get("isWayland")) or bool(plan.get("rebootRequired"))
    return {
        "ok": True,
        "message": "扩展安装成功" + ("（需要重启系统）" if plan.get("rebootRequired") else
                                    "，注销重新登录后托盘图标生效" if desktop.get("isWayland")
                                    else "，按 Alt+F2 → r 重启 GNOME Shell 后生效"),
        "command": command,
        "commandText": plan.get("commandText") or _shell_join(command),
        "output": output or "（无输出）",
        "needsLogout": needs_logout,
        "needsReload": True,
        "rebootRequired": bool(plan.get("rebootRequired")),
        "enableResult": enable_result,
        "state": after,
        "manualCommands": [],
    }


def disabled_manual_commands() -> List[str]:
    return [
        f"gnome-extensions enable {APPINDICATOR_UUID}",
        "# Wayland：注销重新登录；X11：Alt+F2 → r",
    ]


# ----------------------------------------------------------------------
# 汇总状态
# ----------------------------------------------------------------------
_PROBE_CACHE: Dict[str, object] = {"at": 0.0, "data": None}


def probe(*, refresh: bool = False) -> Dict[str, object]:
    """缓存 30s 的环境探测（桌面环境 / 扩展 / 版本 / 安装计划）。"""
    now = time.monotonic()
    cached = _PROBE_CACHE.get("data")
    if not refresh and isinstance(cached, dict) and (now - float(_PROBE_CACHE.get("at") or 0.0)) < PROBE_TTL:
        return cached
    desktop = desktop_environment()
    ext = extension_state()
    version = gnome_shell_version() if desktop.get("family") == "gnome" else None
    plan = install_plan(extension=ext, desktop=desktop)
    data = {"desktop": desktop, "extension": ext, "shellVersion": version, "plan": plan}
    _PROBE_CACHE["at"] = now
    _PROBE_CACHE["data"] = data
    return data


def reset_cache() -> None:
    _PROBE_CACHE["at"] = 0.0
    _PROBE_CACHE["data"] = None


def _advice(code: str) -> Dict[str, str]:
    text = ADVICE.get(code) or ADVICE["unsupported"]
    return {"code": code, "zh": text["zh"], "en": text["en"]}


def status(
    tray: Optional[dict] = None,
    *,
    shell_mode: bool = False,
    refresh: bool = False,
    environ: Optional[dict] = None,
    system: Optional[str] = None,
    which=None,
) -> Dict[str, object]:
    """设置页「系统托盘」卡片 / /api/status 的托盘摘要数据。

    :param tray: 原生外壳注入的实际托盘状态 {"available", "backend", "error"}；
                 浏览器模式下为 None。
    :param shell_mode: 是否运行在原生外壳里（shell.py 启动）。
    """
    platform_name = system or platform.system()
    tray_info = {
        "available": None,
        "backend": None,
        "error": None,
    }
    if tray:
        tray_info.update({k: tray.get(k) for k in ("available", "backend", "error")})

    if platform_name != "Linux":
        code = "windows-ok" if platform_name == "Windows" else "unsupported"
        return {
            "platform": platform_name.lower(),
            "shellMode": bool(shell_mode),
            "tray": tray_info,
            "desktop": {"currentDesktop": "", "family": platform_name.lower(),
                        "sessionType": "", "isWayland": False},
            "os": {"id": platform_name.lower(), "name": platform_name, "version": ""},
            "gnome": {"detected": False, "shellVersion": None},
            "extension": {"uuid": APPINDICATOR_UUID, "installed": None, "enabled": None,
                          "systemWide": False, "paths": []},
            "install": {
                "supported": False,
                "reason": "unsupported-platform",
                "reasonText": {"zh": _REASON_TEXT["unsupported-platform"][0],
                               "en": _REASON_TEXT["unsupported-platform"][1]},
                "manager": None, "package": PACKAGE_NAME, "command": [],
                "commandText": "", "needsRoot": False, "elevatedVia": None,
                "rebootRequired": False, "needsEnable": False, "manualCommands": [],
            },
            "advice": _advice(code),
        }

    # Linux 分支
    if environ is not None:
        desktop = desktop_environment(environ)
        ext = extension_state()
        version = gnome_shell_version() if desktop.get("family") == "gnome" else None
        plan = install_plan(extension=ext, desktop=desktop, which=which, system=platform_name)
        os_release = read_os_release()
        data = {"desktop": desktop, "extension": ext, "shellVersion": version, "plan": plan}
    else:
        data = probe(refresh=refresh)
        desktop = data["desktop"]
        ext = data["extension"]
        version = data["shellVersion"]
        plan = data["plan"]
        os_release = read_os_release()

    gnome = desktop.get("family") == "gnome"
    available = tray_info["available"]
    advice_code = "ok"
    if available is None:
        advice_code = "browser" if not shell_mode else "gnome-missing-extension" if gnome else "no-tray-host"
    elif available is False:
        if not gnome:
            advice_code = "no-tray-host"
        elif not ext.get("installed"):
            advice_code = "gnome-missing-extension"
        elif not ext.get("enabled"):
            advice_code = "gnome-extension-disabled"
        else:
            advice_code = "gnome-needs-relogin"
    # 已确认托盘可用时一律显示正常，不再提示扩展（Ubuntu 预装扩展也会让 isSystemTrayAvailable 为真）
    if available is True:
        advice_code = "ok"

    return {
        "platform": "linux",
        "shellMode": bool(shell_mode),
        "tray": tray_info,
        "desktop": desktop,
        "os": {
            "id": os_release.get("id", ""),
            "name": os_release.get("name") or os_release.get("pretty_name", ""),
            "version": os_release.get("version_id", ""),
        },
        "gnome": {"detected": bool(gnome), "shellVersion": version},
        "extension": ext,
        "install": plan,
        "advice": _advice(advice_code),
    }
