# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（Windows / Linux 通用）。

用法（在 driver/ 目录）::

    pip install pyinstaller
    pyinstaller packaging/mk87.spec --noconfirm

产物：dist/MK87Config/（onedir，包含 web/ 与 data/）
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(os.getcwd()))
if os.path.basename(ROOT) != "driver":
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

datas = [
    (os.path.join(ROOT, "web"), "web"),
    (os.path.join(ROOT, "data"), "data"),
    (os.path.join(ROOT, "docs"), "docs"),
]

binaries = []
hiddenimports = []
for pkg in ("uvicorn", "soundcard", "hidapi", "fastapi", "pydantic", "websockets"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["server.app", "server.state", "mk87lib"]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas"],
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
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MK87Config",
)
