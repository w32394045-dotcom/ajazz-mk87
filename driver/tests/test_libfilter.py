# -*- coding: utf-8 -*-
"""打包策略单测：宿主系统库不进 PyInstaller 包（v0.1.8.3）。

背景见 ``driver/packaging/libfilter.py`` 顶部注释：v0.1.8.2 及更早的 Linux 包把
构建机上的 glib/libstdc++/wayland/xcb 打进 ``_internal``，在用户 Ubuntu 24.04 上
顶掉系统 Mesa/GLib，导致 EGL 不可用 + 段错误。这里的用例锁死过滤规则，防止回归。
"""

import importlib.util
import os
import unittest

# 直接按文件路径加载：driver/packaging 没有 __init__.py，且 PyPI 上也有一个同名
# 的 `packaging` 包，用 `import packaging.libfilter` 会被它抢先。
_SPEC = importlib.util.spec_from_file_location(
    "mk87_libfilter",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "packaging", "libfilter.py"),
)
libfilter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(libfilter)


class TestIsHostSystemLib(unittest.TestCase):
    def test_multiarch_system_lib(self):
        self.assertTrue(libfilter.is_host_system_lib(
            "/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0.7200.4"))

    def test_plain_usr_lib(self):
        self.assertTrue(libfilter.is_host_system_lib("/usr/lib/libstdc++.so.6"))

    def test_lib64(self):
        self.assertTrue(libfilter.is_host_system_lib("/lib64/libc.so.6"))
        self.assertTrue(libfilter.is_host_system_lib("/usr/lib64/libX11.so.6"))
        # 动态加载器由 PyInstaller 自己排除，不在这里的规则范围内
        self.assertFalse(libfilter.is_host_system_lib("/lib64/ld-linux-x86-64.so.2"))

    def test_qt_wheel_lib_kept(self):
        """wheel 自带的 Qt 库（site-packages 内）必须保留。"""
        self.assertFalse(libfilter.is_host_system_lib(
            "/home/u/.venv/lib/python3.12/site-packages/PyQt6/Qt6/lib/libQt6Core.so.6"))

    def test_python_extension_module_kept(self):
        """Python 扩展模块不以 lib 开头，即使在系统目录里也不能丢。"""
        self.assertFalse(libfilter.is_host_system_lib(
            "/usr/lib/python3.10/lib-dynload/_ssl.cpython-310-x86_64-linux-gnu.so"))
        self.assertFalse(libfilter.is_host_system_lib(
            "/usr/lib/python3/dist-packages/_cffi_backend.cpython-310-x86_64-linux-gnu.so"))

    def test_libpython_kept(self):
        """libpython 必须随包，否则目标机没有同版本解释器共享库。"""
        self.assertFalse(libfilter.is_host_system_lib(
            "/usr/lib/x86_64-linux-gnu/libpython3.10.so.1.0"))
        self.assertFalse(libfilter.is_host_system_lib(
            "/opt/hostedtoolcache/Python/3.12.14/x64/lib/libpython3.12.so.1.0"))

    def test_windows_path_ignored(self):
        self.assertFalse(libfilter.is_host_system_lib(
            r"C:\Program Files\WindowsApps\libxcb.so"))
        self.assertFalse(libfilter.is_host_system_lib(""))

    def test_symlink_inside_system_dir_resolved(self):
        """/usr/lib/.../libX.so.6 是符号链接时按真实文件判断。"""
        self.assertTrue(libfilter.is_host_system_lib(
            "/usr/lib/x86_64-linux-gnu/libX11.so.6"))

    def test_hostedtoolcache_lib_kept(self):
        """构建机 setup-python 的 Python 自带库不在系统目录，保留。"""
        self.assertFalse(libfilter.is_host_system_lib(
            "/opt/hostedtoolcache/Python/3.12.14/x64/lib/libffi-dummy.so"))


class TestSplitHostLibs(unittest.TestCase):
    def test_split_preserves_order_and_contents(self):
        entries = [
            ("libQt6Core.so.6", "/w/PyQt6/Qt6/lib/libQt6Core.so.6", "BINARY"),
            ("libglib-2.0.so.0", "/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0.7200.4", "BINARY"),
            ("libnss3.so", "/usr/lib/x86_64-linux-gnu/libnss3.so", "BINARY"),
            ("_ssl.cpython-312-x86_64-linux-gnu.so",
             "/usr/lib/python3.10/lib-dynload/_ssl.cpython-310-x86_64-linux-gnu.so", "EXTENSION"),
            ("libpython3.12.so.1.0",
             "/opt/hostedtoolcache/Python/3.12.14/x64/lib/libpython3.12.so.1.0", "BINARY"),
        ]
        kept, dropped = libfilter.split_host_libs(entries)
        self.assertEqual([e[0] for e in kept], [
            "libQt6Core.so.6", "_ssl.cpython-312-x86_64-linux-gnu.so", "libpython3.12.so.1.0"])
        self.assertEqual([e[0] for e in dropped], ["libglib-2.0.so.0", "libnss3.so"])

    def test_empty(self):
        kept, dropped = libfilter.split_host_libs([])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, [])

    def test_host_lib_names_unique_sorted(self):
        dropped = [
            ("a", "/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0.7200.4", "BINARY"),
            ("b", "/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0", "BINARY"),
            ("c", "/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.30", "BINARY"),
        ]
        names = libfilter.host_lib_names(dropped)
        self.assertEqual(names, sorted(names))
        self.assertIn("libstdc++.so.6.0.30", names)
        self.assertIn("libglib-2.0.so.0.7200.4", names)
        # POSIX 上符号链接会被解析成同一个真实文件，因此去重后只剩一项；
        # Windows 上不做 realpath（路径是 Linux 的），两条都会保留。
        expected = 2 if os.name == "posix" else 3
        self.assertEqual(len(names), expected)


if __name__ == "__main__":
    unittest.main()
