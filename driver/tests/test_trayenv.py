#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.1.8 托盘环境探测单元测试（Linux 逻辑在 Windows 上也能测）。

覆盖：
* 桌面环境 / 会话类型解析（XDG_CURRENT_DESKTOP、Wayland/X11 推断）；
* /etc/os-release 解析；
* GNOME AppIndicator 扩展「已装/未装/启用/未启用」判定（gsettings + gnome-extensions）；
* 包管理器 / 提权工具识别、安装计划与手动命令；
* 汇总状态（Windows / 非 GNOME / GNOME 缺扩展 / 已装未启用 / 已装启用需重登）；
* 外壳「无托盘时点 X 直接退出」逻辑。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.dirname(HERE)
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

from mk87lib import trayenv  # noqa: E402


def _which_factory(available):
    """构造 shutil.which 替身：available 里的命令返回 /usr/bin/<name>。"""

    def _which(name, path=None):
        return f"/usr/bin/{name}" if name in available else None

    return _which


class TmpExtensionDirs:
    """临时扩展目录 + 可控 gsettings 输出的上下文管理器。"""

    def __init__(self, *, uuid="appindicatorsupport@rgcjonas.gmail.com",
                 installed=True, enabled=None, gsettings_ok=True):
        self.uuid = uuid
        self.installed = installed
        self.enabled = enabled
        self.gsettings_ok = gsettings_ok
        self.tmp = tempfile.TemporaryDirectory()

    def __enter__(self):
        self.user_dir = os.path.join(self.tmp.name, "extensions")
        os.makedirs(self.user_dir, exist_ok=True)
        if self.installed:
            os.makedirs(os.path.join(self.user_dir, self.uuid), exist_ok=True)

        def fake_run(cmd, timeout=8.0, env=None):
            if list(cmd)[:2] == ["gsettings", "get"]:
                if not self.gsettings_ok:
                    return 1, "", "gsettings 不可用"
                key = list(cmd)[3] if len(cmd) > 3 else ""
                if key == "enabled-extensions":
                    if self.enabled:
                        return 0, f"['{self.uuid}']", ""
                    return 0, "@as []", ""
                if key == "disabled-extensions":
                    if self.enabled is False:
                        return 0, f"['{self.uuid}']", ""
                    return 0, "@as []", ""
            if list(cmd)[:2] == ["gnome-extensions", "info"]:
                if not self.installed:
                    return 1, "", "not installed"
                state = "ENABLED" if self.enabled else "DISABLED"
                return 0, f"Name: AppIndicator\nState: {state}\n", ""
            return 0, "", ""

        self._patches = [
            mock.patch.object(trayenv, "_extension_dirs", lambda: [self.user_dir]),
            mock.patch.object(trayenv, "_run", fake_run),
            mock.patch.object(trayenv, "_which", _which_factory({"gsettings", "gnome-extensions"})),
            mock.patch.object(trayenv, "_gsettings_list", self._gsettings_list),
        ]
        for p in self._patches:
            p.start()
        return self

    def _gsettings_list(self, key):
        if not self.gsettings_ok:
            return None
        return [self.uuid] if self.enabled and key == "enabled-extensions" else []

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        self.tmp.cleanup()
        return False


class TestDesktopEnvironment(unittest.TestCase):
    def test_family_mapping(self):
        cases = {
            "GNOME": "gnome",
            "ubuntu:GNOME": "gnome",
            "KDE": "kde",
            "plasma": "kde",
            "XFCE": "xfce",
            "X-Cinnamon": "cinnamon",
            "MATE": "mate",
            "LXQt": "lxqt",
            "": "unknown",
            "sway": "unknown",
        }
        for raw, want in cases.items():
            self.assertEqual(trayenv.desktop_family(raw), want, msg=raw)

    def test_environment_ubuntu_gnome_wayland(self):
        env = {
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
            "XDG_SESSION_TYPE": "wayland",
            "WAYLAND_DISPLAY": "wayland-0",
        }
        out = trayenv.desktop_environment(env)
        self.assertEqual(out["family"], "gnome")
        self.assertEqual(out["currentDesktop"], "GNOME")
        self.assertEqual(out["sessionType"], "wayland")
        self.assertTrue(out["isWayland"])

    def test_environment_infers_x11_without_session_type(self):
        out = trayenv.desktop_environment({"XDG_CURRENT_DESKTOP": "KDE", "DISPLAY": ":0"})
        self.assertEqual(out["sessionType"], "x11")
        self.assertFalse(out["isWayland"])

    def test_environment_empty(self):
        out = trayenv.desktop_environment({})
        self.assertEqual(out["family"], "unknown")
        self.assertEqual(out["sessionType"], "")


class TestOsRelease(unittest.TestCase):
    def test_parse(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".release", delete=False) as f:
            f.write('NAME="Fedora Linux"\nVERSION_ID=43\nID=fedora\n# comment\n')
            path = f.name
        try:
            data = trayenv.read_os_release(path)
            self.assertEqual(data["id"], "fedora")
            self.assertEqual(data["name"], "Fedora Linux")
            self.assertEqual(data["version_id"], "43")
        finally:
            os.unlink(path)

    def test_missing_file(self):
        self.assertEqual(trayenv.read_os_release("/nonexistent/os-release"), {})


class TestExtensionState(unittest.TestCase):
    def test_installed_and_enabled(self):
        with TmpExtensionDirs(installed=True, enabled=True) as ctx:
            st = trayenv.extension_state()
            self.assertTrue(st["installed"])
            self.assertTrue(st["enabled"])
            self.assertEqual(st["uuid"], ctx.uuid)
            self.assertIn(ctx.uuid, st["paths"][0])

    def test_installed_but_disabled(self):
        with TmpExtensionDirs(installed=True, enabled=False):
            st = trayenv.extension_state()
            self.assertTrue(st["installed"])
            self.assertFalse(st["enabled"])

    def test_not_installed(self):
        with TmpExtensionDirs(installed=False, enabled=False):
            st = trayenv.extension_state()
            self.assertFalse(st["installed"])
            self.assertIsNone(st["enabled"])

    def test_ubuntu_uuid_recognised(self):
        with TmpExtensionDirs(uuid="ubuntu-appindicators@ubuntu.com", installed=True, enabled=True):
            st = trayenv.extension_state()
            self.assertTrue(st["installed"])
            self.assertTrue(st["enabled"])
            self.assertEqual(st["uuid"], "ubuntu-appindicators@ubuntu.com")

    def test_gsettings_unavailable_falls_back_to_gnome_extensions(self):
        with TmpExtensionDirs(installed=True, enabled=True, gsettings_ok=False):
            st = trayenv.extension_state()
            self.assertTrue(st["installed"])
            self.assertIsInstance(st["enabled"], bool)


class TestInstallPlan(unittest.TestCase):
    GNOME_ENV = {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}

    def _desktop(self, env=None):
        return trayenv.desktop_environment(env or self.GNOME_ENV)

    def test_not_gnome(self):
        plan = trayenv.install_plan(
            extension={"installed": False, "enabled": None},
            desktop=self._desktop({"XDG_CURRENT_DESKTOP": "KDE"}),
            system="Linux",
        )
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["reason"], "not-gnome")

    def test_already_enabled(self):
        plan = trayenv.install_plan(
            extension={"installed": True, "enabled": True}, desktop=self._desktop(),
            system="Linux")
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["reason"], "already-enabled")

    def test_installed_disabled_needs_enable(self):
        plan = trayenv.install_plan(
            extension={"installed": True, "enabled": False}, desktop=self._desktop(),
            system="Linux")
        self.assertEqual(plan["reason"], "installed-disabled")
        self.assertTrue(plan["needsEnable"])
        self.assertFalse(plan["supported"])

    def test_fedora_pkexec_command(self):
        with TmpExtensionDirs(installed=False, enabled=False):
            plan = trayenv.install_plan(
                extension={"installed": False, "enabled": None},
                desktop=self._desktop(),
                which=_which_factory({"dnf", "pkexec"}),
                system="Linux",
            )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["elevatedVia"], "pkexec")
        self.assertEqual(plan["manager"]["id"], "dnf")
        self.assertEqual(plan["command"][:2], ["pkexec", "/usr/bin/dnf"])
        self.assertEqual(plan["command"][-1], trayenv.PACKAGE_NAME)
        self.assertIn("gnome-extensions enable", "\n".join(plan["manualCommands"]))

    def test_apt_with_sudo_fallback(self):
        plan = trayenv.install_plan(
            extension={"installed": False, "enabled": None},
            desktop=self._desktop(),
            which=_which_factory({"apt-get", "sudo"}),
            system="Linux",
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["elevatedVia"], "sudo")
        self.assertEqual(plan["manager"]["id"], "apt")
        self.assertIn("sudo apt update", plan["manualCommands"][0])

    def test_no_package_manager(self):
        plan = trayenv.install_plan(
            extension={"installed": False, "enabled": None},
            desktop=self._desktop(),
            which=_which_factory(set()),
            system="Linux",
        )
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["reason"], "no-package-manager")

    def test_no_elevation_tool(self):
        plan = trayenv.install_plan(
            extension={"installed": False, "enabled": None},
            desktop=self._desktop(),
            which=_which_factory({"dnf"}),
            system="Linux",
        )
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["reason"], "no-elevation")


class TestStatus(unittest.TestCase):
    GNOME_ENV = {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}

    def _status(self, tray, env=None, system="Linux"):
        with mock.patch.object(trayenv, "read_os_release",
                               lambda *a, **k: {"id": "fedora", "name": "Fedora Linux 43",
                                                "version_id": "43"}):
            return trayenv.status(tray, shell_mode=True, environ=env or self.GNOME_ENV,
                                  system=system,
                                  which=_which_factory({"dnf", "pkexec", "gsettings"}))

    def test_windows_status(self):
        out = trayenv.status({"available": True, "backend": "pystray"}, shell_mode=True,
                             system="Windows")
        self.assertEqual(out["platform"], "windows")
        self.assertEqual(out["advice"]["code"], "windows-ok")
        self.assertFalse(out["install"]["supported"])
        self.assertFalse(out["gnome"]["detected"])

    def test_linux_gnome_missing_extension(self):
        with TmpExtensionDirs(installed=False, enabled=False):
            out = self._status({"available": False, "backend": "qt"})
        self.assertEqual(out["advice"]["code"], "gnome-missing-extension")
        self.assertTrue(out["gnome"]["detected"])
        self.assertFalse(out["extension"]["installed"])
        self.assertTrue(out["install"]["supported"])
        self.assertIn("zh", out["advice"])
        self.assertIn("en", out["advice"])

    def test_linux_gnome_extension_disabled(self):
        with TmpExtensionDirs(installed=True, enabled=False):
            out = self._status({"available": False, "backend": "qt"})
        self.assertEqual(out["advice"]["code"], "gnome-extension-disabled")
        self.assertTrue(out["install"]["needsEnable"])

    def test_linux_gnome_extension_enabled_needs_relogin(self):
        with TmpExtensionDirs(installed=True, enabled=True):
            out = self._status({"available": False, "backend": "qt"})
        self.assertEqual(out["advice"]["code"], "gnome-needs-relogin")

    def test_linux_gnome_tray_ok(self):
        with TmpExtensionDirs(installed=True, enabled=True):
            out = self._status({"available": True, "backend": "qt"})
        self.assertEqual(out["advice"]["code"], "ok")

    def test_linux_non_gnome_no_tray_host(self):
        with TmpExtensionDirs(installed=False, enabled=False):
            out = self._status({"available": False, "backend": "qt"},
                               env={"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11"})
        self.assertEqual(out["advice"]["code"], "no-tray-host")
        self.assertEqual(out["install"]["reason"], "not-gnome")

    def test_browser_mode(self):
        out = trayenv.status(None, shell_mode=False, system="Linux")
        self.assertEqual(out["advice"]["code"], "browser")


class TestEnableAndInstall(unittest.TestCase):
    def test_enable_via_gnome_extensions(self):
        results = []

        def fake_run(cmd, timeout=8.0, env=None):
            results.append(list(cmd))
            return 0, "enabled", ""

        with mock.patch.object(trayenv, "_run", fake_run), \
                mock.patch.object(trayenv, "extension_state",
                                  lambda: {"uuid": trayenv.APPINDICATOR_UUID,
                                           "installed": True, "enabled": False}):
            out = trayenv.enable_extension()
        self.assertTrue(out["ok"])
        self.assertEqual(out["method"], "gnome-extensions")

    def test_enable_falls_back_to_gsettings(self):
        calls = []

        def fake_run(cmd, timeout=8.0, env=None):
            calls.append(list(cmd))
            if list(cmd)[:2] == ["gnome-extensions", "enable"]:
                return 1, "", "not loaded"
            if list(cmd)[:3] == ["gsettings", "get", "org.gnome.shell"]:
                return 0, "@as []", ""
            return 0, "", ""

        with mock.patch.object(trayenv, "_run", fake_run), \
                mock.patch.object(trayenv, "extension_state",
                                  lambda: {"uuid": trayenv.APPINDICATOR_UUID,
                                           "installed": True, "enabled": False}):
            out = trayenv.enable_extension()
        self.assertTrue(out["ok"])
        self.assertEqual(out["method"], "gsettings")
        self.assertTrue(any(cmd[:2] == ["gsettings", "set"] for cmd in calls))

    def test_install_unsupported_returns_manual_commands(self):
        with mock.patch.object(trayenv, "extension_state",
                               lambda: {"uuid": trayenv.APPINDICATOR_UUID,
                                        "installed": False, "enabled": None}), \
                mock.patch.object(trayenv, "install_plan",
                                  lambda **kwargs: {"supported": False,
                                                    "reason": "no-package-manager",
                                                    "reasonText": {"zh": "没有包管理器",
                                                                   "en": "no pm"},
                                                    "manualCommands": ["sudo dnf install x"],
                                                    "needsEnable": False,
                                                    "command": []}):
            out = trayenv.install_extension()
        self.assertFalse(out["ok"])
        self.assertIn("没有包管理器", out["message"])
        self.assertEqual(out["manualCommands"], ["sudo dnf install x"])

    def test_install_success_triggers_enable(self):
        states = [
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None},
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": True, "enabled": False},
        ]
        plan = {
            "supported": True,
            "reason": "install",
            "reasonText": {"zh": "可安装", "en": "installable"},
            "manager": {"id": "dnf"},
            "command": ["pkexec", "/usr/bin/dnf", "install", "-y", trayenv.PACKAGE_NAME],
            "commandText": "pkexec dnf install -y x",
            "rebootRequired": False,
            "manualCommands": [],
        }
        with mock.patch.object(trayenv, "extension_state",
                               lambda: states.pop(0) if states else {
                                   "uuid": trayenv.APPINDICATOR_UUID, "installed": True,
                                   "enabled": True}), \
                mock.patch.object(trayenv, "install_plan", lambda **kwargs: dict(plan)), \
                mock.patch.object(trayenv, "desktop_environment",
                                  lambda: {"family": "gnome", "isWayland": True}), \
                mock.patch.object(trayenv, "_run", lambda *a, **k: (0, "installed ok", "")), \
                mock.patch.object(trayenv, "enable_extension",
                                  lambda **k: {"ok": True, "message": "已启用"}):
            out = trayenv.install_extension()
        self.assertTrue(out["ok"])
        self.assertTrue(out["needsLogout"])
        self.assertIn("installed ok", out["output"])


class TestShellClosingWithoutTray(unittest.TestCase):
    """无托盘宿主时点窗口 X 必须退出程序（而不是把窗口藏起来找不回）。"""

    def _make_shell(self):
        from shell import Shell

        shell = Shell(silent=False)
        shell.window = mock.MagicMock()
        return shell

    def test_close_quits_when_tray_unavailable(self):
        shell = self._make_shell()
        shell._tray_backend = "pystray"
        shell.tray = None  # 没有托盘图标
        shell.quit = mock.MagicMock()
        self.assertTrue(shell._on_closing())
        shell.quit.assert_called_once()
        shell.window.hide.assert_not_called()

    def test_close_hides_when_tray_available(self):
        shell = self._make_shell()
        shell._tray_backend = "pystray"
        shell.tray = mock.MagicMock()
        shell._notify_tray_running = mock.MagicMock()
        self.assertFalse(shell._on_closing())
        shell.window.hide.assert_called_once()

    def test_close_quits_when_qt_tray_unavailable(self):
        shell = self._make_shell()
        shell._tray_backend = "qt"
        shell.quit = mock.MagicMock()
        with mock.patch("mk87lib.tray_linux.STATE",
                        {"available": False, "backend": "qt", "error": "no host"}):
            self.assertTrue(shell._on_closing())
        shell.quit.assert_called_once()

    def test_no_tray_mode_quits_on_close(self):
        """--no-tray / MK87_NO_TRAY=1：完全不创建托盘，关闭窗口 = 退出程序。"""
        shell = self._make_shell()
        shell.no_tray = True
        shell.tray = mock.MagicMock()  # 即使有残留对象也应按 no_tray 处理
        shell.quit = mock.MagicMock()
        self.assertFalse(shell._tray_available())
        self.assertTrue(shell._on_closing())
        shell.quit.assert_called_once()
        shell.window.hide.assert_not_called()

    def test_no_tray_env(self):
        from shell import Shell

        with mock.patch.dict("os.environ", {"MK87_NO_TRAY": "1"}):
            self.assertTrue(Shell(silent=False).no_tray)
        with mock.patch.dict("os.environ", {"MK87_NO_TRAY": ""}):
            self.assertFalse(Shell(silent=False).no_tray)


class TestBootlog(unittest.TestCase):
    """启动阶段日志：固定路径、立即 flush，崩溃排查用。"""

    def test_mark_writes_line(self):
        from mk87lib import bootlog

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "boot.log")
            with mock.patch.object(bootlog, "path", lambda: path):
                bootlog.mark("unit-test-stage", foo=1, bar="x")
                bootlog.mark("second-stage")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("[unit-test-stage]", text)
            self.assertIn("foo=1", text)
            self.assertIn("[second-stage]", text)
            self.assertIn("pid=", text)

    def test_mark_never_raises(self):
        from mk87lib import bootlog

        with mock.patch.object(bootlog, "path", lambda: "/nonexistent-dir/x/boot.log"):
            bootlog.mark("should-not-raise")


class TestQtPreflight(unittest.TestCase):
    """v0.1.8.2：Linux 启动前 PyQt6 预检（把 webview 吞掉的 ImportError 记进 boot log）。"""

    def test_non_linux_returns_true(self):
        import shell

        with mock.patch.object(shell.sys, "platform", "win32"):
            self.assertTrue(shell._preflight_qt())

    def test_env_snapshot_has_expected_keys(self):
        import shell

        snap = shell._env_snapshot()
        self.assertIn("QT_API", snap)
        self.assertIn("XDG_SESSION_TYPE", snap)

    def test_linux_preflight_failure_is_logged_and_reported(self):
        import shell
        from mk87lib import bootlog

        marks = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(shell.sys, "platform", "linux"), \
                mock.patch.object(shell, "LOG_DIR", tmp), \
                mock.patch.object(bootlog, "mark", lambda stage, **kw: marks.append(stage)), \
                mock.patch.dict(shell.os.environ, {"QT_API": "pyqt6"}), \
                mock.patch.dict(shell.sys.modules, {"PyQt6": None}):
            # sys.modules["PyQt6"] = None 时 `import PyQt6` 必抛 ImportError（CI 的 Ubuntu 环境
            # 本身装了 PyQt6，必须显式屏蔽才能覆盖失败分支）。
            ok = shell._preflight_qt()
            self.assertTrue(os.path.exists(os.path.join(tmp, "qt-error.txt")))
        self.assertFalse(ok)
        self.assertIn("preflight-pyqt6-start", marks)
        self.assertIn("preflight-pyqt6-failed", marks)
        self.assertIn("preflight-pyqt6-system-failed", marks)


if __name__ == "__main__":
    unittest.main()
