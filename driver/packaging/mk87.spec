# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（Windows / Linux 通用）。

用法（在 driver/ 目录）::

    pip install pyinstaller
    pyinstaller packaging/mk87.spec --noconfirm --clean

产物：dist/MK87Config/
  Windows: dist/MK87Config/MK87Config.exe
  Linux  : dist/MK87Config/MK87Config

Linux 打包策略（v0.1.8.3 起，2026-11-06 修正）
--------------------------------------------
**Qt/WebEngine 随包（PyQt6 wheel 自带、版本自洽）；宿主系统库不随包。**

v0.1.8.2 及更早版本让 PyInstaller 顺着 Qt 库的 DT_NEEDED 把构建机 Ubuntu 22.04 的
glib 2.72 / libstdc++(GCC 12) / wayland 1.20 / xcb 1.14 / GTK3 / NSS 等整套系统库
打进 ``_internal/``。冻结程序把 ``_internal`` 放在库搜索路径最前面，于是系统组件
（GIO 模块、DRI 驱动、Mesa/libEGL）被这些"更旧的一份"顶上，用户 Ubuntu 24.04 上表现为：

* ``libdconfsettings.so: undefined symbol: g_assertion_message_cmpint``（glib 被顶）
* ``iHD_drv_video.so: GLIBCXX_3.4.32 not found``（libstdc++ 被顶）
* ``qt.qpa.wayland: EGL not available`` → QRhi 失败 → QtWebEngine **段错误**

修复：用 ``packaging/libfilter.py`` 把所有来自系统库目录（``/usr/lib``、``/lib``）的
共享库从 ``a.binaries`` 里滤掉，交给宿主发行版提供（deb ``Depends`` / rpm ``Requires``
已经声明齐全）。这样 Qt 用的 Mesa/glib/X11 和系统里其它程序是同一份，版本不会再错配。
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
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

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

# Linux：宿主系统库一律不随包（规则与原因见模块 docstring 与 packaging/libfilter.py）。
if sys.platform.startswith("linux"):
    import libfilter  # noqa: E402  （SPECPATH 已加入 sys.path）

    _kept, _dropped = libfilter.split_host_libs(a.binaries)
    a.binaries = _kept
    print("[mk87.spec] Linux 打包：保留 %d 个随包二进制，%d 个宿主系统库交给系统提供"
          % (len(_kept), len(_dropped)))
    for _name in libfilter.host_lib_names(_dropped):
        print("[mk87.spec]   host: %s" % _name)

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
