# -*- coding: utf-8 -*-
"""PyInstaller 产物过滤：**不要把构建机上的「宿主系统库」打进包**。

背景（v0.1.8.2 → v0.1.8.3，2026-11-06 用户 Ubuntu 24.04 现场）

v0.1.7/v0.1.8 把 Linux 构建机固定到 ``ubuntu-22.04``（glibc 2.35）后，
PyInstaller 顺着 PyQt6-Qt6 wheel 里 Qt 库的 DT_NEEDED，把**构建机上的整套系统库**
（glib 2.72 / libstdc++ GCC-12 / wayland 1.20 / xcb 1.14 / GTK3 / NSS …）一起收进了
``_internal/``。程序启动时 PyInstaller 把 ``_internal`` 放在库搜索路径最前面，于是：

* 系统 GIO 模块（``/usr/lib/x86_64-linux-gnu/gio/modules/libdconfsettings.so``）被
  **打包里更旧的 libglib** 顶上 → ``undefined symbol: g_assertion_message_cmpint``；
* 系统 DRI 驱动（``iHD_drv_video.so``）被**打包里更旧的 libstdc++** 顶上 →
  ``GLIBCXX_3.4.32 not found``；
* 系统 Mesa/libEGL 被**打包里的 libwayland / libxcb / libgbm** 顶上 →
  ``qt.qpa.wayland: EGL not available`` → QRhi 创建失败 → QtWebEngine 段错误。

也就是说：Qt/WebEngine 这些「应用库」可以随包（wheel 自带、版本自洽），但
**显卡栈、GLib/GTK、X11/Wayland、NSS/OpenSSL 这类「宿主系统库」必须由发行版提供**，
和系统里其它程序用同一份，版本才匹配。本模块就是这条规则的唯一实现处。

规则
----
* ``a.binaries`` 里的条目形如 ``(dest_name, src_path, typecode)``；
* 若 ``src_path`` 的真实路径落在发行版系统库目录（``/usr/lib/``、``/lib/`` 等）下，
  且文件名是共享库（``lib*.so*``），则**丢弃**——运行时由宿主提供；
* 例外：``libpython3.*.so`` 必须随包（目标机没有同版本 Python 共享库）；
* Python 扩展模块（``_ssl.cpython-312-x86_64-linux-gnu.so`` 等，不以 ``lib`` 开头）
  一律保留，即使它们位于系统 ``/usr/lib/python3/...`` 下。
"""

from __future__ import annotations

import os
import posixpath
from typing import Iterable, Sequence

#: 发行版系统库所在目录前缀：这些路径下的共享库属于「宿主提供」。
SYSTEM_LIB_DIR_PREFIXES = (
    "/usr/lib/",
    "/usr/lib64/",
    "/lib/",
    "/lib64/",
)

#: 例外：Python 解释器共享库必须随包携带（PyInstaller 冻结程序的运行基础）。
KEEP_LIB_PREFIXES = (
    "libpython3",
    "libpython",
)

TocEntry = Sequence[str]


def _posix_realpath(path: str) -> str:
    """尽量解析符号链接，但**始终按 POSIX 语义**处理路径。

    这些路径来自 Linux 构建机；本模块的单测也会在 Windows 上跑，而 Windows 的
    ``os.path.realpath('/usr/lib/...')`` 会把它当成「当前盘符下的相对路径」改写成
    ``C:\\usr\\lib\\...``，导致规则失效。所以只在 POSIX 上做 realpath。
    """
    if os.name == "posix":
        try:
            return os.path.realpath(path)
        except OSError:  # pragma: no cover - realpath 基本不会抛
            return path
    return path


def is_host_system_lib(src: str) -> bool:
    """``src`` 是否是构建机上的发行版系统库（True = 不应打进包，留给宿主）。

    只认 POSIX 绝对路径；Windows 构建（``C:\\\\...``）永远返回 False。
    """
    if not src:
        return False
    real = _posix_realpath(src)
    if not real.startswith("/"):
        return False
    if not any(real.startswith(prefix) for prefix in SYSTEM_LIB_DIR_PREFIXES):
        return False
    name = posixpath.basename(real)
    # 共享库一律以 lib 开头；Python 扩展模块（_ssl.cpython-...so）不以 lib 开头，
    # 即使位于 /usr/lib/python3/... 也必须保留。
    if not name.startswith("lib"):
        return False
    return not name.startswith(KEEP_LIB_PREFIXES)


def split_host_libs(binaries: Iterable[TocEntry]) -> tuple[list[TocEntry], list[TocEntry]]:
    """把 PyInstaller 的 binaries 列表拆成 ``(保留, 丢弃)``，保持原顺序。"""
    kept: list[TocEntry] = []
    dropped: list[TocEntry] = []
    for entry in binaries:
        src = entry[1] if len(entry) > 1 else ""
        if is_host_system_lib(src):
            dropped.append(entry)
        else:
            kept.append(entry)
    return kept, dropped


def host_lib_names(dropped: Iterable[TocEntry]) -> list[str]:
    """丢弃项的系统库名（去重排序，用于构建日志里说明「交给系统了」）。"""
    names = set()
    for entry in dropped:
        src = entry[1] if len(entry) > 1 else ""
        if not src:
            continue
        names.add(posixpath.basename(_posix_realpath(src)))
    return sorted(names)
