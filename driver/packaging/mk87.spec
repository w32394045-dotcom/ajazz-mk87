# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（Windows / Linux 通用）。

用法（在 driver/ 目录）::

    pip install pyinstaller
    pyinstaller packaging/mk87.spec --noconfirm --clean

产物：dist/MK87Config/
  Windows: dist/MK87Config/MK87Config.exe
  Linux  : dist/MK87Config/MK87Config
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# spec 可能从 driver/ 或 packaging/ 运行，统一解析 driver 根目录
# （PyInstaller 的 spec 里没有 __file__，用 SPECPATH 或当前目录推断）
_HERE = globals().get("SPECPATH") or os.getcwd()
if os.path.basename(_HERE) == "packaging":
    ROOT = os.path.abspath(os.path.join(_HERE, ".."))
else:
    ROOT = os.path.abspath(_HERE)
if not os.path.isdir(os.path.join(ROOT, "web")):
    ROOT = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(ROOT, "web"), "web"),
    (os.path.join(ROOT, "data"), "data"),
    (os.path.join(ROOT, "docs"), "docs"),
    (os.path.join(ROOT, "assets"), "assets"),
]

binaries = []
hiddenimports = []
for pkg in ("uvicorn", "soundcard", "hidapi", "fastapi", "pydantic", "websockets",
            "webview", "pystray"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass
# Linux 原生窗口用 Qt 后端（PySide6/QtWebEngine）保证自包含；Windows 用系统 WebView2
if sys.platform != "win32":
    try:
        d, b, h = collect_all("PySide6")
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["server.app", "server.state", "mk87lib"]
# hidapi wheel 在 Linux 上打包了两个扩展模块：hid（libusb 后端）和 hidraw
# （hidraw 后端）。本工具 Linux 只用 hidraw（transport 里用 importlib 动态导入，
# PyInstaller 静态分析看不到），Windows 用 hid。见 mk87lib/transport.py 顶部说明。
if sys.platform.startswith("linux"):
    hiddenimports += ["hidraw"]
else:
    hiddenimports += ["hid"]

# Linux：PyInstaller 会漏收少量 PyQt6/Qt 6.12 依赖的系统库（它已经收了一部分，
# 但没有递归收全 libQt6Core/Qt6Gui 的系统依赖）。2026-11-05 用户 Ubuntu 上
# "No Qt bindings could be found / PyQt6 导入失败" 就是缺这些库（Ubuntu 桌面如果
# 没装 Qt 生态，默认不带 libpcre2-16 / libdouble-conversion / libb2 / libmd4c）。
# 这里把必需的库显式打进来，做成自包含（deb/rpm 的 Depends/Requires 仍然会声明，
# 双保险；这样即使用 dpkg -i 强装跳过依赖也能跑）。
if sys.platform.startswith("linux"):
    import glob as _glob

    _LINUX_EXTRA_LIBS = (
        # Qt 6 核心依赖（QtCore/QtGui 直接链接）
        "libpcre2-16.so.0",
        "libdouble-conversion.so.3",
        "libb2.so.1",
        "libmd4c.so.0",
        # X11 / Wayland 运行库（Qt xcb/wayland 插件、WebEngine 会用到）
        "libxcb.so.1",
        "libxcb-present.so.0",
        "libxcb-dri3.so.0",
        "libxcb-icccm.so.4",
        "libxcb-keysyms.so.1",
        "libxcb-shape.so.0",
        "libXres.so.1",
        "libwayland-client.so.0",
        "libwayland-cursor.so.0",
        "libwayland-egl.so.1",
    )
    _existing = {os.path.basename(src) for src, _dest in binaries}
    for _name in _LINUX_EXTRA_LIBS:
        if _name in _existing:
            continue
        for _root in ("/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"):
            _matches = _glob.glob(os.path.join(_root, _name))
            if _matches:
                binaries.append((_matches[0], "."))
                _existing.add(_name)
                break

icon = os.path.join(ROOT, "assets", "mk87.ico")
version_file = os.path.join(ROOT, "packaging", "windows", "version_info.txt")

a = Analysis(
    [os.path.join(ROOT, "shell.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MK87Config",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon if os.path.exists(icon) else None,
    version=version_file if (sys.platform == "win32" and os.path.exists(version_file)) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MK87Config",
)
