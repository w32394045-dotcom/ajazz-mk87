#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux 托盘环境探测 + GNOME AppIndicator 扩展安装/启用（纯标准库）。

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

一键安装策略（用户 2026-11-05 / 2026-11-07 确认）
------------------------------------------------
优先「发行版包 + 一次提权」（`pkexec`，其次带图形 askpass 的 `sudo`）：
* 发行版维护的包与当前 GNOME Shell 版本匹配，不会出现「zip 版本不对被 Shell 拒载」；
* 提权必须能弹图形密码框：无 pkexec 且不是从终端启动时，**不**盲目跑 `sudo`
  （GUI 进程没有 tty，sudo 必然失败），而是把命令交给用户复制到终端执行；
* apt 系先 `apt-get update` 再安装（软件源过期时「找不到包」是最常见的失败原因），
  两条命令合并进同一次提权，避免两次密码框；
* 安装成功后自动 `gnome-extensions enable`（失败则回退直接写 gsettings），并返回
  Wayland 注销重登 / X11 Alt+F2→r / 原子化系统重启的提示；
* 失败时返回人话原因（取消提权 / 无 polkit 代理 / 包管理器锁 / 源里没有包 / 网络 / 超时）
  与可复制的手动命令。

v0.1.8.6 起还补充了发行版识别（debian/fedora/suse/arch/unknown + rpm-ostree 原子化）、
`no-elevation` / `no-gui-elevation` 区分、`already-enabled` 不重装、安装输出截断与日志。
"""
from __future__ import annotations

import os
import platform
import re
import shlex
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
#: 扩展显示名（前端/日志用）
PACKAGE_LABEL = "AppIndicator / KStatusNotifierItem Support"

GNOME_FAMILIES = {"gnome"}

#: 探测缓存 TTL（秒）
PROBE_TTL = 30.0

#: 安装输出最多回传给前端的字符数（避免 pkexec/apt 输出把界面刷爆）
OUTPUT_LIMIT = 3000

#: 单个安装步骤/整体安装的默认超时（秒）；pkexec 密码框等待时间也算在里面
INSTALL_TIMEOUT = 300.0
COMMAND_TIMEOUT = 8.0

_LOG_PREFIX = "[trayenv] "


def _log(msg: str) -> None:
    # 不依赖 logging 初始化顺序：设置页可能在服务启动早期就调用
    try:
        import logging

        logging.getLogger("mk87.trayenv").info("%s%s", _LOG_PREFIX, msg)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------
# 基础命令执行
# ----------------------------------------------------------------------
def _run(cmd: Sequence[str], timeout: float = COMMAND_TIMEOUT, env: Optional[dict] = None) -> tuple:
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


def _tail(text: str, limit: int = OUTPUT_LIMIT) -> str:
    text = text or ""
    return text if len(text) <= limit else "…" + text[-limit:]


def _which(name: str, path: Optional[str] = None) -> Optional[str]:
    try:
        return shutil.which(name, path=path)
    except Exception:  # noqa: BLE001
        return None


def _stdin_is_tty() -> bool:
    """当前进程是否从终端启动（决定 sudo 能否直接弹密码提示）。"""
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:  # noqa: BLE001
        return False


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
# 发行版识别
# ----------------------------------------------------------------------
#: /etc/os-release ID / ID_LIKE → 发行版家族
_DISTRO_FAMILIES = {
    # Debian 系
    "debian": "debian", "ubuntu": "debian", "linuxmint": "debian", "pop": "debian",
    "elementary": "debian", "zorin": "debian", "kali": "debian", "raspbian": "debian",
    "neon": "debian", "mx": "debian", "deepin": "debian", "devuan": "debian",
    # Fedora / RHEL 系
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora", "rocky": "fedora",
    "almalinux": "fedora", "ol": "fedora", "nobara": "fedora", "bazzite": "fedora",
    "silverblue": "fedora", "kinoite": "fedora", "sericea": "fedora",
    # openSUSE 系
    "opensuse": "suse", "opensuse-tumbleweed": "suse", "opensuse-leap": "suse",
    "opensuse-microos": "suse", "sles": "suse", "suse": "suse", "sled": "suse",
    # Arch 系
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch", "cachyos": "arch",
    "artix": "arch", "garuda": "arch", "arcolinux": "arch",
}

#: 家族 → (首选包管理器, 显示名)
_DISTRO_PACKAGE_HINT = {
    "debian": ("apt", "Debian / Ubuntu · apt"),
    "fedora": ("dnf", "Fedora / RHEL · dnf"),
    "suse": ("zypper", "openSUSE · zypper"),
    "arch": ("pacman", "Arch Linux · pacman"),
    "unknown": ("", "未知发行版"),
}

#: 家族 → 包管理器探测顺序（首选排前面：同一台机器装了多个包管理器时选发行版自己的）
_FAMILY_PREFERENCE = {
    "debian": ["apt", "dnf", "zypper", "pacman"],
    "fedora": ["dnf", "apt", "zypper", "pacman"],
    "suse": ["zypper", "dnf", "apt", "pacman"],
    "arch": ["pacman", "dnf", "apt", "zypper"],
    "unknown": ["dnf", "apt", "zypper", "pacman"],
}


def distro_info(os_release: Optional[dict] = None) -> Dict[str, object]:
    """从 os-release 识别发行版家族与推荐的包管理器（供设置页展示/回退命令）。"""
    data = read_os_release() if os_release is None else (os_release or {})
    raw_id = (data.get("id") or "").strip().lower()
    like = [token for token in (data.get("id_like") or "").strip().lower().split() if token]
    family = _DISTRO_FAMILIES.get(raw_id)
    if not family:
        for token in like:
            family = _DISTRO_FAMILIES.get(token)
            if family:
                break
    family = family or "unknown"
    manager_id, manager_label = _DISTRO_PACKAGE_HINT.get(family, _DISTRO_PACKAGE_HINT["unknown"])
    return {
        "id": raw_id,
        "name": data.get("name") or data.get("pretty_name") or "",
        "prettyName": data.get("pretty_name") or data.get("name") or "",
        "version": data.get("version_id") or "",
        "family": family,
        "idLike": like,
        "packageManagerHint": manager_id,
        "packageManagerLabel": manager_label,
        "atomic": bool(_ostree_booted()) or raw_id in ("silverblue", "kinoite", "bazzite"),
    }


def _ostree_booted() -> bool:
    """是否运行在 rpm-ostree 原子化系统上（Fedora Silverblue / Bazzite 等）。"""
    try:
        return os.path.exists("/run/ostree-booted")
    except Exception:  # noqa: BLE001
        return False


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

#: 可配合 `sudo -A` 使用的图形 askpass（zenity 本身不能直接当 askpass）
_GUI_ASKPASS = ("ssh-askpass", "ksshaskpass", "lxqt-openssh-askpass", "x11-ssh-askpass")

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
        "zh": "当前是浏览器模式（没有原生外壳），没有系统托盘。用桌面版启动即可使用托盘；"
              "一键安装扩展只在桌面版里可用。",
        "en": "Running in browser mode (no native shell), so there is no system tray. Start the "
              "desktop app to use the tray; the one-click extension install is desktop-only.",
    },
    "gnome-missing-extension": {
        "zh": "GNOME 默认不显示托盘图标，还差一个 AppIndicator 扩展。打开「设置 → 系统托盘」，"
              "点一次「一键安装 AppIndicator 扩展」并输入管理员密码即可；装完注销重新登录"
              "（Wayland）或按 Alt+F2 → r（X11）。",
        "en": "GNOME does not show tray icons by default; one AppIndicator extension is missing. "
              "Open Settings → System tray and click \"Install AppIndicator extension\" once "
              "(one admin password). Afterwards log out and back in (Wayland) or press Alt+F2 → r "
              "(X11).",
    },
    "gnome-extension-disabled": {
        "zh": "已安装 AppIndicator 扩展但尚未启用。在「设置 → 系统托盘」点一次「启用扩展」"
              "（无需管理员密码），然后注销重新登录（Wayland）或按 Alt+F2 → r（X11）。",
        "en": "The AppIndicator extension is installed but not enabled. Click \"Enable extension\" "
              "in Settings → System tray (no admin password needed), then log out and back in "
              "(Wayland) or press Alt+F2 → r (X11).",
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
        "可以一键安装 AppIndicator 扩展（只需要输入一次管理员密码，装完自动启用）。",
        "The AppIndicator extension can be installed in one click (one admin password; it is "
        "enabled automatically afterwards).",
    ),
    "unsupported-platform": (ADVICE["unsupported"]["zh"], ADVICE["unsupported"]["en"]),
    "not-gnome": (
        "当前桌面环境不需要 AppIndicator 扩展（非 GNOME）。",
        "No AppIndicator extension is needed on this desktop (not GNOME).",
    ),
    "already-enabled": (
        "AppIndicator 扩展已安装并启用；如果托盘还没出现，注销重新登录即可。",
        "The AppIndicator extension is already installed and enabled; if the tray icon is still "
        "missing, log out and back in.",
    ),
    "installed-disabled": (
        "扩展已安装但未启用，只需启用（无需提权）。",
        "The extension is installed but disabled; just enable it (no root needed).",
    ),
    "no-package-manager": (
        "没有识别到受支持的包管理器，请按下方命令手动安装（只需要一次管理员密码）。",
        "No supported package manager found; install manually with the commands below "
        "(one admin password).",
    ),
    "no-elevation": (
        "系统里没有 pkexec / sudo，无法自动提权，请按下方命令手动安装。",
        "Neither pkexec nor sudo is available, so automatic installation is not possible; "
        "install manually with the commands below.",
    ),
    "no-gui-elevation": (
        "系统只有 sudo，但当前不是从终端启动、也没有图形密码助手，弹不出密码框。"
        "请把下方命令复制到终端执行，或用发行版「软件」应用安装 gnome-shell-extension-appindicator。",
        "Only sudo is available, but this app was not launched from a terminal and no graphical "
        "askpass helper is installed, so no password prompt can be shown. Copy the commands "
        "below into a terminal, or install gnome-shell-extension-appindicator from your distro's "
        "software center.",
    ),
}

#: 安装计划 reason → 前端动作
_REASON_ACTION = {
    "install": "install",
    "installed-disabled": "enable",
    "already-enabled": "relogin",
    "no-package-manager": "manual",
    "no-elevation": "manual",
    "no-gui-elevation": "manual",
    "not-gnome": "none",
    "unsupported-platform": "none",
}


def package_manager(which=None, os_release: Optional[dict] = None) -> Dict[str, object]:
    """识别发行版包管理器。`which` / `os_release` 可注入（单测用）。"""
    finder = which or _which
    family = str(distro_info(os_release).get("family") or "unknown")
    order = _FAMILY_PREFERENCE.get(family) or _FAMILY_PREFERENCE["unknown"]
    # 原子化系统（Fedora Silverblue / Bazzite 等）优先用 rpm-ostree，避免 dnf 只改临时层
    if _ostree_booted() and finder("rpm-ostree"):
        return {
            "id": "rpm-ostree",
            "label": "Fedora Atomic / Silverblue",
            "path": finder("rpm-ostree"),
            "args": ["install", "-y", PACKAGE_NAME],
            "updateRequired": False,
            "rebootRequired": True,
        }
    for manager_id in order:
        for mid, exe, args, label in _MANAGERS:
            if mid != manager_id:
                continue
            path = finder(exe)
            if path:
                return {
                    "id": manager_id,
                    "label": label,
                    "path": path,
                    "args": list(args),
                    "updateRequired": manager_id == "apt",
                    "rebootRequired": False,
                }
    return {"id": None, "label": "", "path": None, "args": [],
            "updateRequired": False, "rebootRequired": False}


def elevation_info(which=None, *, stdin_tty: Optional[bool] = None) -> Dict[str, object]:
    """提权方式详情：优先 pkexec（图形密码框），其次可用的 sudo。

    只有 sudo 时还要判断能不能真的弹出密码：从终端启动（有 tty）或装了图形 askpass
    才可用；否则 GUI 进程里的 sudo 必定报「no tty present」，应直接回退手动命令。
    """
    finder = which or _which
    tty = _stdin_is_tty() if stdin_tty is None else bool(stdin_tty)

    pkexec = finder("pkexec")
    if pkexec:
        return {
            "tool": "pkexec", "path": pkexec, "args": [], "gui": True,
            "available": True, "reason": "pkexec", "askpass": None,
        }

    sudo = finder("sudo")
    if sudo:
        askpass = (os.environ.get("SUDO_ASKPASS") or "").strip()
        if not askpass:
            for name in _GUI_ASKPASS:
                found = finder(name)
                if found:
                    askpass = found
                    break
        if askpass:
            return {
                "tool": "sudo", "path": sudo, "args": ["-A"], "gui": True,
                "available": True, "reason": "sudo-askpass", "askpass": askpass,
            }
        if tty:
            return {
                "tool": "sudo", "path": sudo, "args": [], "gui": False,
                "available": True, "reason": "sudo-tty", "askpass": None,
            }
        return {
            "tool": "sudo", "path": sudo, "args": [], "gui": False,
            "available": False, "reason": "sudo-no-tty", "askpass": None,
        }

    return {
        "tool": None, "path": None, "args": [], "gui": False,
        "available": False, "reason": "no-elevation", "askpass": None,
    }


def elevation_tool(which=None) -> Optional[str]:
    """首选提权工具：pkexec（图形密码框）→ 可用的 sudo；都不可用返回 None。"""
    info = elevation_info(which=which)
    return str(info["tool"]) if info.get("available") and info.get("tool") else None


def _shell_join(cmd: Sequence[str]) -> str:
    """把 argv 拼成可复制到终端执行的命令文本（Linux 目标平台，统一用 POSIX 引号）。"""
    return " ".join(shlex.quote(part) for part in cmd)


def _manager_steps(manager: dict) -> List[List[str]]:
    """包管理器安装步骤（不含提权前缀）。apt 需要先 update 再 install。"""
    path = str(manager.get("path") or "")
    if not path:
        return []
    if manager.get("id") == "apt":
        return [[path, "update"], [path, "install", "-y", PACKAGE_NAME]]
    return [[path, *list(manager.get("args") or [])]]


def _install_argv(manager: dict, elevation: dict) -> List[str]:
    """生成「一次提权」的完整安装命令。

    apt 的两步（update + install）合并进同一个 `sh -c`，只弹一次密码框；
    其它包管理器一步即可。提权不可用时返回 []。
    """
    if not elevation.get("available"):
        return []
    prefix = [str(elevation.get("path") or elevation.get("tool") or "")] + list(elevation.get("args") or [])
    steps = _manager_steps(manager)
    if not steps:
        return []
    if len(steps) == 1:
        return prefix + steps[0]
    parts: List[str] = []
    for step in steps:
        text = _shell_join(step)
        if "apt-get" in step[0]:
            # 非交互环境变量必须写进 sh -c 里：pkexec 会清掉父进程的 env
            text = "DEBIAN_FRONTEND=noninteractive " + text
        parts.append(text)
    return prefix + ["/bin/sh", "-c", " && ".join(parts)]


def _family_manual_commands(family: str) -> List[str]:
    """没有识别到包管理器时，按发行版家族给出兜底手动命令。"""
    commands: List[str] = []
    if family == "debian":
        commands.append("sudo apt update")
        commands.append(f"sudo apt install -y {PACKAGE_NAME}")
    elif family in ("fedora",):
        commands.append(f"sudo dnf install -y {PACKAGE_NAME}")
    elif family == "suse":
        commands.append(f"sudo zypper install -y {PACKAGE_NAME}")
    elif family == "arch":
        commands.append(f"sudo pacman -S --noconfirm {PACKAGE_NAME}")
    else:
        commands.append(f"# 用发行版包管理器安装 {PACKAGE_NAME}")
    return commands


def manual_commands(plan: Optional[dict] = None) -> List[str]:
    """给用户复制的手动安装/启用命令（带发行版包管理器版本）。"""
    plan = plan or install_plan()
    if str(plan.get("platform") or "linux") != "linux":
        return []
    reason = str(plan.get("reason") or "")
    if reason in ("not-gnome", "already-enabled", "unsupported-platform"):
        return []
    if reason == "installed-disabled":
        # 只差「启用」，不需要再装包
        return disabled_manual_commands(str(plan.get("uuid") or APPINDICATOR_UUID))
    manager = plan.get("manager") or {}
    distro = plan.get("distro") or {}
    family = str(distro.get("family") or "unknown")
    commands: List[str] = []
    manager_id = manager.get("id")
    if manager_id == "rpm-ostree":
        commands.append(f"sudo rpm-ostree install {PACKAGE_NAME}")
        commands.append("sudo systemctl reboot  # 原子化系统需重启后生效")
    elif manager_id == "dnf":
        commands.append(f"sudo dnf install -y {PACKAGE_NAME}")
    elif manager_id == "apt":
        commands.append("sudo apt update")
        commands.append(f"sudo apt install -y {PACKAGE_NAME}")
    elif manager_id == "zypper":
        commands.append(f"sudo zypper install -y {PACKAGE_NAME}")
    elif manager_id == "pacman":
        commands.append(f"sudo pacman -S --noconfirm {PACKAGE_NAME}")
    else:
        commands.extend(_family_manual_commands(family))
    uuid = str(plan.get("uuid") or APPINDICATOR_UUID)
    commands.append(f"gnome-extensions enable {uuid}")
    commands.append("# Wayland：注销重新登录；X11：Alt+F2 → r")
    return commands


def _reload_hint(desktop: Optional[dict], *, reboot_required: bool = False) -> Dict[str, str]:
    """安装/启用后需要用户做什么才能让扩展生效。"""
    desktop = desktop or {}
    if reboot_required:
        return {
            "zh": "扩展已装好，但原子化系统需要重启后才会生效：请重启系统。",
            "en": "The extension is installed, but atomic systems need a reboot before it "
                  "becomes active. Please reboot.",
        }
    if desktop.get("isWayland"):
        return {
            "zh": "请注销并重新登录（或重启系统）：Wayland 下 GNOME 不支持热加载扩展。",
            "en": "Log out and back in (or reboot): GNOME cannot hot-load extensions on Wayland.",
        }
    return {
        "zh": "按 Alt+F2 → 输入 r → 回车，重启 GNOME Shell 后托盘图标就会出现。",
        "en": "Press Alt+F2, type r and press Enter to restart GNOME Shell; the tray icon will "
              "then appear.",
    }


def install_plan(
    *,
    extension: Optional[dict] = None,
    desktop: Optional[dict] = None,
    which=None,
    system: Optional[str] = None,
    distro: Optional[dict] = None,
) -> Dict[str, object]:
    """给当前环境生成安装计划（是否支持、命令、提权方式、失败原因、手动兜底命令）。"""
    desktop = desktop or desktop_environment()
    ext = extension or extension_state()
    platform_name = (system or platform.system()).lower()
    distro_data = distro or distro_info()
    uuid = str(ext.get("uuid") or APPINDICATOR_UUID)

    def plan(supported: bool, reason: str, **extra) -> Dict[str, object]:
        base = {
            "supported": supported,
            "reason": reason,
            "action": _REASON_ACTION.get(reason, "none"),
            "reasonText": {"zh": _REASON_TEXT.get(reason, ("", ""))[0],
                           "en": _REASON_TEXT.get(reason, ("", ""))[1]},
            "platform": platform_name,
            "distro": {
                "id": distro_data.get("id"),
                "name": distro_data.get("name"),
                "prettyName": distro_data.get("prettyName"),
                "family": distro_data.get("family"),
                "packageManagerHint": distro_data.get("packageManagerHint"),
                "packageManagerLabel": distro_data.get("packageManagerLabel"),
            },
            "manager": None,
            "elevation": {"tool": None, "path": None, "args": [], "gui": False,
                          "available": False, "reason": "not-required", "askpass": None},
            "package": PACKAGE_NAME,
            "uuid": uuid,
            "command": [],
            "commandText": "",
            "needsRoot": True,
            "elevatedVia": None,
            "requiresAdminPassword": False,
            "updateRequired": False,
            "rebootRequired": False,
            "needsEnable": False,
            "manualCommands": [],
            "canAutoInstall": False,
        }
        base.update(extra)
        base["manualCommands"] = manual_commands(base)
        return base

    if platform_name == "windows" or platform_name == "darwin":
        return plan(False, "unsupported-platform", needsRoot=False)
    if desktop.get("family") != "gnome":
        return plan(False, "not-gnome", needsRoot=False)
    if ext.get("installed") and ext.get("enabled"):
        return plan(False, "already-enabled", needsRoot=False)
    if ext.get("installed") and not ext.get("enabled"):
        return plan(False, "installed-disabled", needsEnable=True, needsRoot=False)

    manager = package_manager(which=which)
    if not manager.get("id"):
        return plan(False, "no-package-manager", manager=manager)
    elevation = elevation_info(which=which)
    if not elevation.get("available"):
        reason = "no-elevation" if elevation.get("tool") is None else "no-gui-elevation"
        return plan(False, reason, manager=manager, elevation=elevation)
    command = _install_argv(manager, elevation)
    if not command:
        return plan(False, "no-package-manager", manager=manager, elevation=elevation)
    return plan(
        True,
        "install",
        manager=manager,
        elevation=elevation,
        command=command,
        commandText=_shell_join(command),
        needsRoot=True,
        elevatedVia=elevation.get("tool"),
        requiresAdminPassword=True,
        updateRequired=bool(manager.get("updateRequired")),
        rebootRequired=bool(manager.get("rebootRequired")),
        canAutoInstall=True,
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
    desktop = desktop_environment()

    def ok(method: str, message: str, output: str, verified: Optional[bool] = None) -> Dict[str, object]:
        result: Dict[str, object] = {
            "ok": True,
            "uuid": uuid,
            "method": method,
            "message": message,
            "output": _tail(output),
            "needsLogout": bool(desktop.get("isWayland")),
            "needsReload": True,
            "sessionType": desktop.get("sessionType"),
            "reloadHint": _reload_hint(desktop),
            "manualCommands": [],
        }
        if verified is not None:
            result["verified"] = verified
        return result

    def fail(message: str, output: str) -> Dict[str, object]:
        return {
            "ok": False,
            "uuid": uuid,
            "message": message,
            "output": _tail(output),
            "needsLogout": False,
            "needsReload": False,
            "sessionType": desktop.get("sessionType"),
            "manualCommands": disabled_manual_commands(uuid),
        }

    rc, out, err = _run(["gnome-extensions", "enable", uuid], timeout=timeout)
    if rc == 0:
        return ok("gnome-extensions", "扩展已启用", out + "\n" + err)

    enabled_list = _gsettings_list("enabled-extensions")
    if enabled_list is None:
        return fail("无法启用扩展：gsettings 不可用", out + "\n" + err)
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
    combined = (out + "\n" + err + "\n" + out2 + "\n" + err2).strip()
    if rc2 != 0:
        return fail("写入 enabled-extensions 失败", combined)
    verified = uuid in (_gsettings_list("enabled-extensions") or [])
    return ok(
        "gsettings",
        "已把扩展加入启用列表，注销重新登录（Wayland）或 Alt+F2 → r（X11）后生效",
        out2 + "\n" + err2,
        verified=verified,
    )


def disabled_manual_commands(uuid: Optional[str] = None) -> List[str]:
    """「已安装但未启用」时给用户复制的手动启用命令。"""
    return [
        f"gnome-extensions enable {uuid or APPINDICATOR_UUID}",
        "# Wayland：注销重新登录；X11：Alt+F2 → r",
    ]


#: 安装失败输出 → 人话原因（小写子串匹配；顺序有意义）
_FAILURE_PATTERNS = (
    ("no-polkit-agent", (
        "no authentication agent", "authentication agent",
    ), (
        "系统里没有正在运行的 polkit 认证代理，pkexec 无法弹出密码框。"
        "请在终端执行下面的命令，或安装并启用 polkit 认证代理后重试。",
        "No polkit authentication agent is running, so pkexec cannot show a password prompt. "
        "Run the commands below in a terminal, or install/enable a polkit agent and retry.",
    )),
    ("auth-cancelled", (
        "not authorized", "authorization", "dismissed", "cancel", "denied", "not permitted",
        "没有授权", "已取消", "认证失败", "密码错误",
    ), (
        "提权被取消或密码没有通过（没有安装任何东西）。可以重试；也可以复制下面的命令到终端执行。",
        "Elevation was cancelled or the password was rejected (nothing was installed). Retry, "
        "or copy the commands below into a terminal.",
    )),
    ("package-lock", (
        "could not get lock", "unable to acquire the dpkg frontend lock", "another process",
        "is locked", "waiting for package manager", "lock file", "被锁定", "正在被使用",
        "zypper is locked", "the package manager is locked",
    ), (
        "包管理器正被其它程序占用（多半是系统正在更新）。等更新结束后点「重试」即可。",
        "The package manager is busy (usually a system update is running). Wait for it to "
        "finish, then click retry.",
    )),
    ("package-not-found", (
        "unable to locate package", "no packages found", "target not found", "not found in",
        "nothing provides", "没有可用的软件包", "no candidate",
    ), (
        "软件源里找不到这个扩展包（软件源列表可能过期）。请先更新软件源再试，"
        "或复制下面的命令到终端执行。",
        "The extension package is not in your configured repositories (the package lists may be "
        "stale). Update the repositories and retry, or run the commands below in a terminal.",
    )),
    ("network", (
        "failed to fetch", "temporary failure resolving", "network is unreachable",
        "could not resolve", "connection timed out", "download failed", "curl error",
        "connection failed", "unable to connect", "no route to host",
    ), (
        "网络不可用或软件源连接失败（没有安装任何东西）。检查网络/代理后重试，"
        "或复制下面的命令到终端执行。",
        "The network or the software repository is unreachable (nothing was installed). Check "
        "your network/proxy and retry, or run the commands below in a terminal.",
    )),
    ("disk-space", (
        "no space left", "disk space", "空间不足",
    ), (
        "磁盘空间不足，安装没有完成。清理磁盘后重试。",
        "Not enough disk space; the install did not complete. Free up space and retry.",
    )),
)

_FAILURE_UNKNOWN = (
    "安装命令执行失败（没有安装完成）。可以点「重试」；如果仍然失败，请把下面的输出发给开发者，"
    "或复制命令到终端执行后看完整报错。",
    "The install command failed (nothing was installed). Retry; if it keeps failing, send the "
    "output below to the developer, or run the commands in a terminal to see the full error.",
)


def _classify_failure(rc: int, output: str) -> Dict[str, object]:
    """把包管理器/pkexec 的失败输出归类成人话（供前端展示与回退）。"""
    text = (output or "").lower()
    code = "unknown"
    zh, en = _FAILURE_UNKNOWN
    if rc == 124:
        code = "timeout"
        zh = "安装超时（可能网络太慢或密码框一直没有输入）。可以重试；也可以复制命令到终端执行。"
        en = ("The install timed out (slow network, or the password prompt was never answered). "
              "Retry, or copy the commands into a terminal.")
    else:
        for pattern_code, needles, texts in _FAILURE_PATTERNS:
            if any(needle in text for needle in needles):
                code = pattern_code
                zh, en = texts
                break
        if code == "unknown" and rc in (126, 127):
            code = "auth-or-missing"
            zh = ("提权没有完成（密码被取消，或缺少 pkexec/polkit 组件）。可以重试；"
                  "也可以复制下面的命令到终端执行。")
            en = ("Elevation did not complete (password cancelled, or pkexec/polkit is missing). "
                  "Retry, or copy the commands below into a terminal.")
    return {
        "code": code,
        "zh": zh,
        "en": en,
        "retryable": code in ("auth-cancelled", "auth-or-missing", "no-polkit-agent",
                              "network", "package-lock", "timeout", "unknown"),
        "manualFallback": True,
    }


def _install_failure_result(*, plan: dict, desktop: dict, command: List[str],
                            rc: int, output: str, elapsed: float) -> Dict[str, object]:
    failure = _classify_failure(rc, output)
    suffix = ""
    if rc == 124:
        suffix = "（超时）"
    elif rc != 0:
        suffix = f"（退出码 {rc}）"
    return {
        "ok": False,
        "action": "manual",
        "message": "安装失败" + suffix,
        "command": command,
        "commandText": plan.get("commandText") or _shell_join(command),
        "output": output or "（无输出）",
        "failure": failure,
        "needsLogout": False,
        "needsReload": False,
        "rebootRequired": False,
        "sessionType": desktop.get("sessionType"),
        "elevation": plan.get("elevation"),
        "distro": plan.get("distro"),
        "state": extension_state(),
        "manualCommands": plan.get("manualCommands") or manual_commands(plan),
        "warnings": [],
        "elapsedSeconds": round(elapsed, 1),
    }


def install_extension(*, timeout: float = INSTALL_TIMEOUT, which=None) -> Dict[str, object]:
    """一键安装 AppIndicator 扩展（发行版包 + 一次提权），随后自动启用。

    返回 dict：ok / action / message / command / commandText / output / failure /
    needsLogout / needsReload / reloadHint / rebootRequired / state / manualCommands /
    warnings / elapsedSeconds。失败时附带手动命令，前端回退成「复制命令」。
    """
    desktop = desktop_environment()
    ext = extension_state()
    plan = install_plan(extension=ext, desktop=desktop, which=which)
    reason = str(plan.get("reason") or "")
    uuid = str(ext.get("uuid") or APPINDICATOR_UUID)

    # 已装未启用：不重装，只启用（免提权）
    if plan.get("needsEnable") and not plan.get("supported"):
        enabled = enable_extension(timeout=min(timeout, 30.0))
        ok = bool(enabled.get("ok"))
        return {
            "ok": ok,
            "action": "enable",
            "message": enabled.get("message") or "启用扩展失败",
            "command": [],
            "commandText": "",
            "output": enabled.get("output") or "",
            "failure": None if ok else {
                "code": "enable-failed",
                "zh": "扩展已安装，但自动启用失败。可以再点一次「启用扩展」，或复制下面的命令到终端执行。",
                "en": "The extension is installed but enabling it failed. Try \"Enable extension\" "
                      "again, or copy the commands below into a terminal.",
                "retryable": True,
                "manualFallback": True,
            },
            "needsLogout": bool(enabled.get("needsLogout")),
            "needsReload": ok,
            "rebootRequired": False,
            "sessionType": desktop.get("sessionType"),
            "reloadHint": enabled.get("reloadHint") or _reload_hint(desktop),
            "enableResult": enabled,
            "state": extension_state(),
            "manualCommands": [] if ok else disabled_manual_commands(uuid),
            "warnings": [],
            "elapsedSeconds": 0.0,
        }

    if not plan.get("supported"):
        # already-enabled 不算失败：不重装，直接提示重登
        if reason == "already-enabled":
            return {
                "ok": True,
                "action": "relogin",
                "alreadyInstalled": True,
                "message": "AppIndicator 扩展已经安装并启用，不需要重复安装",
                "command": [],
                "commandText": "",
                "output": "",
                "failure": None,
                "needsLogout": bool(desktop.get("isWayland")),
                "needsReload": True,
                "rebootRequired": False,
                "sessionType": desktop.get("sessionType"),
                "reloadHint": _reload_hint(desktop),
                "state": ext,
                "manualCommands": [],
                "warnings": [],
                "elapsedSeconds": 0.0,
            }
        reason_text = (plan.get("reasonText") or {})
        return {
            "ok": False,
            "action": "manual",
            "message": reason_text.get("zh") or "当前环境无法自动安装扩展",
            "command": list(plan.get("command") or []),
            "commandText": plan.get("commandText") or "",
            "output": "",
            "failure": {
                "code": reason or "unsupported",
                "zh": reason_text.get("zh") or "",
                "en": reason_text.get("en") or "",
                "retryable": False,
                "manualFallback": True,
            },
            "needsLogout": False,
            "needsReload": False,
            "rebootRequired": False,
            "sessionType": desktop.get("sessionType"),
            "elevation": plan.get("elevation"),
            "state": ext,
            "manualCommands": plan.get("manualCommands") or manual_commands(plan),
            "warnings": [],
            "elapsedSeconds": 0.0,
        }

    command = list(plan.get("command") or [])
    _log("安装 AppIndicator 扩展：" + _shell_join(command))
    env = os.environ.copy()
    if (plan.get("manager") or {}).get("id") == "apt":
        env["DEBIAN_FRONTEND"] = "noninteractive"
    # sudo -A 需要 SUDO_ASKPASS；如果是我们探测到的图形 askpass，要显式传进子进程
    askpass = (plan.get("elevation") or {}).get("askpass")
    if askpass:
        env.setdefault("SUDO_ASKPASS", str(askpass))
    started = time.monotonic()
    rc, out, err = _run(command, timeout=timeout, env=env)
    elapsed = time.monotonic() - started
    output = _tail("\n".join(part for part in (out, err) if part).strip())
    _log(f"安装命令结束 rc={rc} 耗时={elapsed:.1f}s 输出={_tail(output, 1200)}")

    if rc != 0:
        return _install_failure_result(plan=plan, desktop=desktop, command=command,
                                       rc=rc, output=output, elapsed=elapsed)

    # 安装成功 → 再启用（免提权）。刚装完 Shell 一般还没扫描到，enable 内部会回退 gsettings。
    after = extension_state()
    enable_result: Dict[str, object] = {}
    warnings: List[Dict[str, str]] = []
    if not after.get("enabled"):
        # 即使扩展目录探测没命中（极少见：发行版把扩展放在非常规目录），也尝试启用一次：
        # 写进 gsettings 的 uuid 在扩展真的存在时会在下次登录生效，失败也无副作用。
        enable_result = enable_extension(timeout=min(timeout, 30.0))
        after = extension_state()
        if not enable_result.get("ok"):
            warnings.append({
                "code": "enable-failed",
                "zh": "扩展已安装，但自动启用失败。请点「启用扩展」，或按下面命令手动启用。",
                "en": "The extension is installed but enabling it failed. Click \"Enable "
                      "extension\", or enable it manually with the commands below.",
            })
        elif not after.get("installed"):
            warnings.append({
                "code": "not-detected",
                "zh": "扩展包已经装好，但没有在常规扩展目录里检测到它。若注销重登后托盘仍不出现，"
                      "请把日志发给开发者，或用「复制安装命令」里的启用命令排查。",
                "en": "The extension package is installed but was not found in the usual extension "
                      "directories. If the tray icon is still missing after logging back in, send "
                      "the logs to the developer or use the enable command from \"Copy install "
                      "commands\".",
            })
    elif not after.get("installed"):
        warnings.append({
            "code": "not-detected",
            "zh": "没有在常规扩展目录里检测到已安装的扩展，但启用状态已写入；注销重登后若托盘仍不出现，"
                  "请把日志发给开发者。",
            "en": "The extension was not found in the usual extension directories, but it is marked "
                  "as enabled; if the tray icon is still missing after logging back in, send the "
                  "logs to the developer.",
        })

    reboot_required = bool(plan.get("rebootRequired"))
    reload_hint = _reload_hint(desktop, reboot_required=reboot_required)
    message = "扩展安装成功"
    if reboot_required:
        message += "（需要重启系统后生效）"
    elif desktop.get("isWayland"):
        message += "，注销重新登录后托盘图标生效"
    else:
        message += "，按 Alt+F2 → r 重启 GNOME Shell 后生效"

    return {
        "ok": True,
        "action": "relogin",
        "alreadyInstalled": False,
        "message": message,
        "command": command,
        "commandText": plan.get("commandText") or _shell_join(command),
        "output": output or "（无输出）",
        "failure": None,
        "needsLogout": bool(desktop.get("isWayland")) or reboot_required,
        "needsReload": True,
        "rebootRequired": reboot_required,
        "sessionType": desktop.get("sessionType"),
        "reloadHint": reload_hint,
        "elevation": plan.get("elevation"),
        "distro": plan.get("distro"),
        "enableResult": enable_result,
        "state": after,
        "manualCommands": [],
        "warnings": warnings,
        "elapsedSeconds": round(elapsed, 1),
    }


# ----------------------------------------------------------------------
# 汇总状态
# ----------------------------------------------------------------------
_PROBE_CACHE: Dict[str, object] = {"at": 0.0, "data": None}


def probe(*, refresh: bool = False) -> Dict[str, object]:
    """缓存 30s 的环境探测（桌面环境 / 扩展 / 版本 / 安装计划 / 发行版）。"""
    now = time.monotonic()
    cached = _PROBE_CACHE.get("data")
    if not refresh and isinstance(cached, dict) and (now - float(_PROBE_CACHE.get("at") or 0.0)) < PROBE_TTL:
        return cached
    desktop = desktop_environment()
    ext = extension_state()
    version = gnome_shell_version() if desktop.get("family") == "gnome" else None
    distro = distro_info()
    plan = install_plan(extension=ext, desktop=desktop, distro=distro)
    data = {"desktop": desktop, "extension": ext, "shellVersion": version,
            "distro": distro, "plan": plan}
    _PROBE_CACHE["at"] = now
    _PROBE_CACHE["data"] = data
    return data


def reset_cache() -> None:
    _PROBE_CACHE["at"] = 0.0
    _PROBE_CACHE["data"] = None


def _advice(code: str) -> Dict[str, str]:
    text = ADVICE.get(code) or ADVICE["unsupported"]
    return {"code": code, "zh": text["zh"], "en": text["en"]}


def _base_install(*, platform_name: str, reason: str, shell_mode: bool) -> Dict[str, object]:
    """非 Linux 平台/浏览器模式的 install 结构（字段与 Linux 分支保持一致，前端少判空）。"""
    return {
        "supported": False,
        "reason": reason,
        "action": "none",
        "reasonText": {"zh": _REASON_TEXT.get(reason, ("", ""))[0],
                       "en": _REASON_TEXT.get(reason, ("", ""))[1]},
        "platform": platform_name,
        "distro": {"id": platform_name, "name": platform_name, "prettyName": "",
                   "family": platform_name, "packageManagerHint": "",
                   "packageManagerLabel": ""},
        "manager": None,
        "elevation": {"tool": None, "path": None, "args": [], "gui": False,
                      "available": False, "reason": "not-required", "askpass": None},
        "package": PACKAGE_NAME,
        "uuid": APPINDICATOR_UUID,
        "command": [],
        "commandText": "",
        "needsRoot": False,
        "elevatedVia": None,
        "requiresAdminPassword": False,
        "updateRequired": False,
        "rebootRequired": False,
        "needsEnable": False,
        "manualCommands": [],
        "canAutoInstall": False,
        "shellMode": bool(shell_mode),
        "browserMode": not bool(shell_mode),
    }


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
            "os": {"id": platform_name.lower(), "name": platform_name, "version": "",
                   "family": platform_name.lower(), "prettyName": "",
                   "packageManagerHint": "", "atomic": False},
            "gnome": {"detected": False, "shellVersion": None},
            "extension": {"uuid": APPINDICATOR_UUID, "installed": None, "enabled": None,
                          "systemWide": False, "paths": []},
            "install": _base_install(platform_name=platform_name.lower(),
                                     reason="unsupported-platform",
                                     shell_mode=shell_mode),
            "advice": _advice(code),
        }

    # Linux 分支
    if environ is not None:
        desktop = desktop_environment(environ)
        ext = extension_state()
        version = gnome_shell_version() if desktop.get("family") == "gnome" else None
        os_release = read_os_release()
        distro = distro_info(os_release)
        plan = install_plan(extension=ext, desktop=desktop, which=which,
                            system=platform_name, distro=distro)
        data = {"desktop": desktop, "extension": ext, "shellVersion": version,
                "distro": distro, "plan": plan}
    else:
        data = probe(refresh=refresh)
        desktop = data["desktop"]
        ext = data["extension"]
        version = data["shellVersion"]
        distro = data.get("distro") or distro_info()
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

    # 复制一份 install 计划再加「当前运行模式」字段，避免污染 30s 缓存里的 plan
    install = dict(plan)
    install["shellMode"] = bool(shell_mode)
    install["browserMode"] = not bool(shell_mode)
    install["canAutoInstall"] = bool(shell_mode and install.get("supported"))
    install["canEnable"] = bool(shell_mode and install.get("needsEnable"))
    action = str(install.get("action") or "none")
    if not shell_mode:
        if action == "install":
            action = "manual-install"
        elif action == "enable":
            action = "manual-enable"
        elif action in ("relogin",):
            action = "manual"
    if advice_code == "gnome-needs-relogin":
        action = "relogin"
    elif advice_code == "ok":
        action = "none"
    install["action"] = action
    if not shell_mode:
        install["canAutoInstall"] = False
        install["canEnable"] = False

    return {
        "platform": "linux",
        "shellMode": bool(shell_mode),
        "tray": tray_info,
        "desktop": desktop,
        "os": {
            "id": os_release.get("id", "") or distro.get("id", ""),
            "name": os_release.get("name") or os_release.get("pretty_name", "")
                    or distro.get("name", ""),
            "version": os_release.get("version_id", "") or distro.get("version", ""),
            "family": distro.get("family", "unknown"),
            "prettyName": distro.get("prettyName", ""),
            "packageManagerHint": distro.get("packageManagerHint", ""),
            "atomic": bool(distro.get("atomic")),
        },
        "gnome": {"detected": bool(gnome), "shellVersion": version},
        "extension": ext,
        "install": install,
        "advice": _advice(advice_code),
    }
