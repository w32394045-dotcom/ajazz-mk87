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
