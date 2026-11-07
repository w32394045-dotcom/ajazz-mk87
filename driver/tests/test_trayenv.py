#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.1.8 / v0.1.8.6 托盘环境探测单元测试（Linux 逻辑在 Windows 上也能测）。

覆盖：
* 桌面环境 / 会话类型解析（XDG_CURRENT_DESKTOP、Wayland/X11 推断）；
* /etc/os-release 解析、发行版家族识别（debian/fedora/suse/arch/unknown、rpm-ostree）；
* GNOME AppIndicator 扩展「已装/未装/启用/未启用」判定（gsettings + gnome-extensions）；
* 包管理器识别与发行版偏好、提权方式（pkexec / sudo-tty / sudo-askpass / 无提权）；
* 安装命令生成（apt 先 update 且只提权一次、dnf/zypper/pacman、rpm-ostree 重启）；
* 安装计划与手动兜底命令（按发行版生成；已装未启用只启用、已装已启用不重装）；
* 安装失败归类（取消提权 / 无 polkit 代理 / 包管理器锁 / 源里没有 / 网络 / 超时 / 未知）；
* 汇总状态（Windows / 非 GNOME / GNOME 缺扩展 / 已装未启用 / 已装启用需重登 / 浏览器模式）
  以及 v0.1.8.6 的 action / shellMode / canAutoInstall / 发行版字段；
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
        # 已装未启用：兜底命令只启用，不重复安装包
        self.assertIn("gnome-extensions enable", "\n".join(plan["manualCommands"]))
        self.assertNotIn("install -y", "\n".join(plan["manualCommands"]))

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
        # 提权工具用绝对路径（pkexec 要求可执行文件路径），方便日志与复制
        self.assertEqual(plan["command"][:2], ["/usr/bin/pkexec", "/usr/bin/dnf"])
        self.assertEqual(plan["command"][-1], trayenv.PACKAGE_NAME)
        self.assertTrue(plan["requiresAdminPassword"])
        self.assertIn("gnome-extensions enable", "\n".join(plan["manualCommands"]))

    def test_apt_with_sudo_fallback(self):
        # 终端启动（有 tty）时 sudo 才能弹密码；GUI 无 tty 的情况见 TestElevation
        with mock.patch.object(trayenv, "_stdin_is_tty", lambda: True):
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


class TestRenderEnvFallback(unittest.TestCase):
    """v0.1.8.3：launcher 崩溃回退时 MK87_SOFTWARE_RENDERING=1 的落地逻辑。"""

    def test_not_requested_keeps_env(self):
        import shell

        with mock.patch.dict(shell.os.environ, {}, clear=False):
            shell.os.environ.pop("MK87_SOFTWARE_RENDERING", None)
            shell.os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
            info = shell._apply_render_env()
            self.assertFalse(info["requested"])
            self.assertNotIn("QTWEBENGINE_CHROMIUM_FLAGS", shell.os.environ)

    def test_software_mode_sets_flags_once(self):
        import shell

        with mock.patch.dict(shell.os.environ, {"MK87_SOFTWARE_RENDERING": "1",
                                                "MK87_LAUNCH_MODE": "xwayland+software"}):
            info = shell._apply_render_env()
            self.assertTrue(info["requested"])
            self.assertEqual(info["launch_mode"], "xwayland+software")
            self.assertEqual(shell.os.environ["LIBGL_ALWAYS_SOFTWARE"], "1")
            self.assertEqual(shell.os.environ["QT_OPENGL"], "software")
            flags = shell.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
            self.assertIn("--disable-gpu", flags.split())
            self.assertIn("--disable-gpu-compositing", flags.split())
            # 重复调用不得重复追加
            shell._apply_render_env()
            self.assertEqual(shell.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"], flags)

    def test_software_mode_keeps_user_flags(self):
        import shell

        with mock.patch.dict(shell.os.environ, {
                "MK87_SOFTWARE_RENDERING": "1",
                "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
        }):
            shell._apply_render_env()
            flags = shell.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
            self.assertEqual(flags.count("--no-sandbox"), 1)
            self.assertEqual(flags.count("--disable-gpu"), 1)

    def test_env_snapshot_has_fallback_keys(self):
        import shell

        snap = shell._env_snapshot()
        for key in ("MK87_LAUNCH_MODE", "MK87_SOFTWARE_RENDERING",
                    "QTWEBENGINE_CHROMIUM_FLAGS", "LIBGL_ALWAYS_SOFTWARE"):
            self.assertIn(key, snap)


class TestDistroInfo(unittest.TestCase):
    """v0.1.8.6：发行版家族识别 + 首选包管理器（决定一键安装命令与兜底命令）。"""

    def test_family_mapping(self):
        cases = {
            "ubuntu": ("debian", "apt"),
            "linuxmint": ("debian", "apt"),
            "fedora": ("fedora", "dnf"),
            "rhel": ("fedora", "dnf"),
            "opensuse-tumbleweed": ("suse", "zypper"),
            "arch": ("arch", "pacman"),
            "endless": ("unknown", ""),
        }
        for distro_id, (family, hint) in cases.items():
            info = trayenv.distro_info({"id": distro_id})
            self.assertEqual(info["family"], family, msg=distro_id)
            self.assertEqual(info["packageManagerHint"], hint, msg=distro_id)

    def test_id_like_fallback(self):
        info = trayenv.distro_info({"id": "nobara", "id_like": "fedora"})
        self.assertEqual(info["family"], "fedora")
        self.assertEqual(info["packageManagerHint"], "dnf")

    def test_unknown_keeps_labels(self):
        info = trayenv.distro_info({"id": "plan9", "name": "Plan 9"})
        self.assertEqual(info["family"], "unknown")
        self.assertEqual(info["name"], "Plan 9")
        self.assertEqual(info["packageManagerLabel"], "未知发行版")

    def test_atomic_flag_from_variant(self):
        info = trayenv.distro_info({"id": "kinoite", "id_like": "fedora"})
        self.assertTrue(info["atomic"])

    def test_ubuntu_os_release_end_to_end(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".release", delete=False) as f:
            f.write('NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n')
            path = f.name
        try:
            parsed = trayenv.read_os_release(path)
            # 注意：不能在这里再 mock read_os_release 后调它自己（会无限递归）
            with mock.patch.object(trayenv, "read_os_release", lambda *a, **k: dict(parsed)):
                info = trayenv.distro_info()
        finally:
            os.unlink(path)
        self.assertEqual(info["family"], "debian")
        self.assertEqual(info["packageManagerHint"], "apt")
        self.assertEqual(info["version"], "24.04")


class TestPackageManager(unittest.TestCase):
    """包管理器探测：发行版首选 + rpm-ostree 原子化系统。"""

    def test_ostree_preferred_on_atomic_system(self):
        with mock.patch.object(trayenv, "_ostree_booted", lambda: True):
            manager = trayenv.package_manager(
                which=_which_factory({"rpm-ostree", "dnf", "pkexec"}),
                os_release={"id": "fedora"},
            )
        self.assertEqual(manager["id"], "rpm-ostree")
        self.assertTrue(manager["rebootRequired"])
        self.assertIn("rpm-ostree", manager["path"])

    def test_debian_prefers_apt_even_if_dnf_installed(self):
        manager = trayenv.package_manager(
            which=_which_factory({"dnf", "apt-get"}),
            os_release={"id": "ubuntu", "id_like": "debian"},
        )
        self.assertEqual(manager["id"], "apt")
        self.assertTrue(manager["updateRequired"])

    def test_fedora_prefers_dnf(self):
        manager = trayenv.package_manager(
            which=_which_factory({"apt-get", "dnf"}),
            os_release={"id": "fedora"},
        )
        self.assertEqual(manager["id"], "dnf")
        self.assertFalse(manager["updateRequired"])

    def test_no_manager(self):
        manager = trayenv.package_manager(which=_which_factory(set()),
                                          os_release={"id": "arch"})
        self.assertIsNone(manager["id"])


class TestElevation(unittest.TestCase):
    """提权探测：pkexec 优先；只有 sudo 时必须能真的弹密码（tty / 图形 askpass）。"""

    def test_pkexec_preferred_over_sudo(self):
        info = trayenv.elevation_info(which=_which_factory({"pkexec", "sudo"}))
        self.assertEqual(info["tool"], "pkexec")
        self.assertTrue(info["available"])
        self.assertTrue(info["gui"])
        self.assertEqual(trayenv.elevation_tool(which=_which_factory({"pkexec", "sudo"})), "pkexec")

    def test_sudo_without_tty_is_unusable(self):
        with mock.patch.object(trayenv, "_stdin_is_tty", lambda: False), \
                mock.patch.dict(os.environ, {"SUDO_ASKPASS": ""}):
            info = trayenv.elevation_info(which=_which_factory({"sudo"}))
            tool = trayenv.elevation_tool(which=_which_factory({"sudo"}))
        self.assertEqual(info["tool"], "sudo")
        self.assertFalse(info["available"])
        self.assertEqual(info["reason"], "sudo-no-tty")
        self.assertIsNone(tool)

    def test_sudo_with_tty_usable(self):
        with mock.patch.object(trayenv, "_stdin_is_tty", lambda: True):
            info = trayenv.elevation_info(which=_which_factory({"sudo"}))
        self.assertTrue(info["available"])
        self.assertFalse(info["gui"])
        self.assertEqual(info["reason"], "sudo-tty")

    def test_sudo_with_askpass_usable(self):
        with mock.patch.object(trayenv, "_stdin_is_tty", lambda: False), \
                mock.patch.dict(os.environ, {"SUDO_ASKPASS": "/usr/bin/ssh-askpass"}):
            info = trayenv.elevation_info(which=_which_factory({"sudo"}))
        self.assertTrue(info["available"])
        self.assertEqual(info["args"], ["-A"])
        self.assertTrue(info["gui"])

    def test_no_elevation_tool(self):
        info = trayenv.elevation_info(which=_which_factory(set()))
        self.assertIsNone(info["tool"])
        self.assertEqual(info["reason"], "no-elevation")


class TestInstallCommand(unittest.TestCase):
    """安装命令生成：apt 先 update 且只提权一次；提权不可用时不动命令。"""

    GNOME_ENV = {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}

    def _plan(self, which, distro=None, desktop=None):
        return trayenv.install_plan(
            extension={"installed": False, "enabled": None, "uuid": trayenv.APPINDICATOR_UUID},
            desktop=desktop or trayenv.desktop_environment(self.GNOME_ENV),
            which=which,
            system="Linux",
            distro=distro,
        )

    def test_apt_plan_runs_update_then_install_in_one_elevation(self):
        plan = self._plan(_which_factory({"apt-get", "pkexec"}),
                          distro={"id": "ubuntu", "family": "debian"})
        self.assertTrue(plan["supported"])
        self.assertTrue(plan["updateRequired"])
        cmd = plan["command"]
        self.assertEqual(cmd[:3], ["/usr/bin/pkexec", "/bin/sh", "-c"])
        script = cmd[3]
        self.assertIn("apt-get update", script)
        self.assertIn("apt-get install -y " + trayenv.PACKAGE_NAME, script)
        self.assertIn("DEBIAN_FRONTEND=noninteractive", script)
        self.assertEqual(plan["commandText"].split()[0], "/usr/bin/pkexec")
        # 只调用一次提权（一次密码框）
        self.assertEqual(sum(1 for part in cmd if "pkexec" in part), 1)

    def test_dnf_plan_is_single_direct_command(self):
        plan = self._plan(_which_factory({"dnf", "pkexec"}), distro={"id": "fedora", "family": "fedora"})
        self.assertEqual(plan["command"][:2], ["/usr/bin/pkexec", "/usr/bin/dnf"])
        self.assertNotIn("/bin/sh", plan["command"])
        self.assertFalse(plan["updateRequired"])

    def test_ostree_plan_marks_reboot_required(self):
        with mock.patch.object(trayenv, "_ostree_booted", lambda: True):
            plan = self._plan(_which_factory({"rpm-ostree", "pkexec"}), distro={"id": "fedora"})
        self.assertTrue(plan["supported"])
        self.assertTrue(plan["rebootRequired"])
        self.assertIn("rpm-ostree", plan["command"][1])

    def test_no_gui_elevation_reason(self):
        with mock.patch.object(trayenv, "_stdin_is_tty", lambda: False), \
                mock.patch.dict(os.environ, {"SUDO_ASKPASS": ""}):
            plan = self._plan(_which_factory({"apt-get", "sudo"}),
                              distro={"id": "ubuntu", "family": "debian"})
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["reason"], "no-gui-elevation")
        self.assertEqual(plan["action"], "manual")
        # 兜底命令仍然给 apt 版本，而不是让用户自己猜包名
        self.assertIn("sudo apt update", plan["manualCommands"][0])
        self.assertIn("gnome-extensions enable", "\n".join(plan["manualCommands"]))

    def test_manual_commands_use_distro_family_when_manager_missing(self):
        plan = {"platform": "linux", "reason": "no-package-manager", "manager": None,
                "distro": {"family": "arch"}, "uuid": trayenv.APPINDICATOR_UUID}
        commands = trayenv.manual_commands(plan)
        self.assertIn("sudo pacman -S --noconfirm " + trayenv.PACKAGE_NAME, commands)

    def test_manual_commands_empty_when_nothing_to_do(self):
        for reason in ("already-enabled", "not-gnome", "unsupported-platform"):
            plan = {"platform": "linux", "reason": reason, "manager": None,
                    "distro": {"family": "debian"}, "uuid": trayenv.APPINDICATOR_UUID}
            self.assertEqual(trayenv.manual_commands(plan), [], msg=reason)

    def test_manual_commands_for_ostree_include_reboot(self):
        plan = {"platform": "linux", "reason": "install",
                "manager": {"id": "rpm-ostree"}, "distro": {"family": "fedora"},
                "uuid": trayenv.APPINDICATOR_UUID}
        commands = trayenv.manual_commands(plan)
        self.assertTrue(commands[0].startswith("sudo rpm-ostree install"))
        self.assertIn("reboot", commands[1])


class TestFailureClassification(unittest.TestCase):
    """安装失败归类：把 pkexec / 包管理器输出翻成用户看得懂的原因。"""

    def test_lock(self):
        out = "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 123"
        failure = trayenv._classify_failure(100, out)
        self.assertEqual(failure["code"], "package-lock")
        self.assertTrue(failure["retryable"])
        self.assertTrue(failure["zh"] and failure["en"])

    def test_package_not_found(self):
        failure = trayenv._classify_failure(
            100, "E: Unable to locate package gnome-shell-extension-appindicator")
        self.assertEqual(failure["code"], "package-not-found")

    def test_network(self):
        failure = trayenv._classify_failure(100, "Temporary failure resolving 'archive.ubuntu.com'")
        self.assertEqual(failure["code"], "network")

    def test_auth_cancelled(self):
        failure = trayenv._classify_failure(126, "Error executing command as another user: Not authorized")
        self.assertEqual(failure["code"], "auth-cancelled")
        self.assertTrue(failure["retryable"])

    def test_no_polkit_agent(self):
        failure = trayenv._classify_failure(127, "No authentication agent found")
        self.assertEqual(failure["code"], "no-polkit-agent")

    def test_timeout(self):
        failure = trayenv._classify_failure(124, "")
        self.assertEqual(failure["code"], "timeout")

    def test_unknown(self):
        failure = trayenv._classify_failure(1, "something exploded")
        self.assertEqual(failure["code"], "unknown")
        self.assertTrue(failure["manualFallback"])

    def test_output_tail_truncation(self):
        text = "x" * 10000
        tail = trayenv._tail(text)
        self.assertTrue(tail.startswith("…"))
        self.assertEqual(len(tail), trayenv.OUTPUT_LIMIT + 1)
        self.assertEqual(trayenv._tail("short"), "short")


class TestInstallExtensionResult(unittest.TestCase):
    """install_extension 的返回契约（前端据此渲染进度/失败回退/重登提示）。"""

    AWAYLAND = {"family": "gnome", "isWayland": True, "sessionType": "wayland"}

    def _patch_env(self, *, plan, states, run, enable=None):
        """states：extension_state 依次返回值（最后一个重复使用）。"""
        state_list = list(states)

        def ext_state():
            return state_list.pop(0) if len(state_list) > 1 else state_list[0]

        patches = [
            mock.patch.object(trayenv, "desktop_environment", lambda: dict(self.AWAYLAND)),
            mock.patch.object(trayenv, "extension_state", ext_state),
            mock.patch.object(trayenv, "install_plan", lambda **kwargs: dict(plan)),
            mock.patch.object(trayenv, "_run", run),
        ]
        if enable is not None:
            patches.append(mock.patch.object(trayenv, "enable_extension", lambda **k: dict(enable)))
        return patches

    def _plan(self, **over):
        base = {
            "supported": True, "reason": "install", "action": "install",
            "reasonText": {"zh": "可安装", "en": "installable"},
            "manager": {"id": "dnf"}, "elevation": {"tool": "pkexec", "gui": True, "available": True},
            "command": ["/usr/bin/pkexec", "/usr/bin/dnf", "install", "-y", trayenv.PACKAGE_NAME],
            "commandText": "/usr/bin/pkexec /usr/bin/dnf install -y " + trayenv.PACKAGE_NAME,
            "rebootRequired": False, "needsEnable": False,
            "manualCommands": ["sudo dnf install -y " + trayenv.PACKAGE_NAME],
        }
        base.update(over)
        return base

    def test_failure_is_classified_with_manual_fallback(self):
        not_installed = {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None}
        run = mock.MagicMock(return_value=(100, "", "E: Unable to locate package x"))
        patches = self._patch_env(plan=self._plan(), states=[not_installed], run=run)
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertFalse(out["ok"])
        self.assertEqual(out["action"], "manual")
        self.assertEqual(out["failure"]["code"], "package-not-found")
        self.assertTrue(out["manualCommands"])
        self.assertIn("Unable to locate", out["output"])
        self.assertTrue(out["commandText"].startswith("/usr/bin/pkexec"))
        self.assertIn("退出码 100", out["message"])

    def test_timeout_message_marks_timeout(self):
        not_installed = {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None}
        run = mock.MagicMock(return_value=(124, "", ""))
        patches = self._patch_env(plan=self._plan(), states=[not_installed], run=run)
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension(timeout=5)
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertFalse(out["ok"])
        self.assertEqual(out["failure"]["code"], "timeout")
        self.assertIn("超时", out["message"])

    def test_success_auto_enables_and_warns_on_enable_failure(self):
        states = [
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None},
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": True, "enabled": False},
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": True, "enabled": False},
        ]
        run = mock.MagicMock(return_value=(0, "installed ok", ""))
        patches = self._patch_env(plan=self._plan(), states=states, run=run,
                                  enable={"ok": False, "message": "启用失败"})
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "relogin")
        self.assertTrue(out["needsLogout"])
        self.assertIn("注销重新登录", out["message"])
        self.assertTrue(out["warnings"])
        self.assertEqual(out["warnings"][0]["code"], "enable-failed")
        self.assertIn("installed ok", out["output"])

    def test_success_warns_when_extension_not_detected(self):
        """极少见：包 rc=0 但扩展目录没探测到 —— 仍尝试启用并给出 not-detected 警告。"""
        not_installed = {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None}
        run = mock.MagicMock(return_value=(0, "installed ok", ""))
        patches = self._patch_env(plan=self._plan(), states=[not_installed, not_installed, not_installed],
                                  run=run, enable={"ok": True, "message": "已启用"})
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertTrue(out["ok"])
        self.assertTrue(out["warnings"])
        self.assertEqual(out["warnings"][0]["code"], "not-detected")

    def test_success_on_x11_tells_alt_f2(self):
        x11 = {"family": "gnome", "isWayland": False, "sessionType": "x11"}
        states = [
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None},
            {"uuid": trayenv.APPINDICATOR_UUID, "installed": True, "enabled": True},
        ]
        run = mock.MagicMock(return_value=(0, "", ""))
        patches = [
            mock.patch.object(trayenv, "desktop_environment", lambda: dict(x11)),
            mock.patch.object(trayenv, "extension_state",
                              lambda: states.pop(0) if len(states) > 1 else states[0]),
            mock.patch.object(trayenv, "install_plan", lambda **kwargs: dict(self._plan())),
            mock.patch.object(trayenv, "_run", run),
        ]
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertTrue(out["ok"])
        self.assertFalse(out["needsLogout"])
        self.assertIn("Alt+F2", out["reloadHint"]["zh"])

    def test_already_enabled_is_not_reinstalled(self):
        installed = {"uuid": trayenv.APPINDICATOR_UUID, "installed": True, "enabled": True}
        plan = {"supported": False, "reason": "already-enabled", "needsEnable": False,
                "reasonText": {"zh": "已启用", "en": "enabled"}, "manualCommands": []}
        run = mock.MagicMock(return_value=(0, "", ""))
        patches = self._patch_env(plan=plan, states=[installed], run=run)
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("alreadyInstalled"))
        self.assertEqual(out["manualCommands"], [])
        self.assertEqual(out["command"], [])
        run.assert_not_called()

    def test_installed_disabled_only_enables(self):
        installed_disabled = {"uuid": trayenv.APPINDICATOR_UUID, "installed": True, "enabled": False}
        plan = {"supported": False, "reason": "installed-disabled", "needsEnable": True,
                "reasonText": {"zh": "未启用", "en": "disabled"}, "manualCommands": []}
        run = mock.MagicMock(return_value=(0, "", ""))
        patches = self._patch_env(
            plan=plan, states=[installed_disabled], run=run,
            enable={"ok": True, "message": "扩展已启用", "needsLogout": True,
                    "needsReload": True, "reloadHint": {"zh": "注销重登", "en": "relogin"}})
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "enable")
        self.assertEqual(out["command"], [])
        run.assert_not_called()

    def test_unsupported_keeps_manual_commands(self):
        not_installed = {"uuid": trayenv.APPINDICATOR_UUID, "installed": False, "enabled": None}
        plan = {"supported": False, "reason": "no-elevation", "needsEnable": False,
                "reasonText": {"zh": "没有提权工具", "en": "no elevation"},
                "manualCommands": ["sudo dnf install -y x"],
                "command": [], "commandText": ""}
        patches = self._patch_env(plan=plan, states=[not_installed], run=mock.MagicMock())
        for p in patches:
            p.start()
        try:
            out = trayenv.install_extension()
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertFalse(out["ok"])
        self.assertEqual(out["failure"]["code"], "no-elevation")
        self.assertEqual(out["manualCommands"], ["sudo dnf install -y x"])

    def test_enable_failure_uses_installed_uuid(self):
        uuid = "ubuntu-appindicators@ubuntu.com"

        def failing_run(cmd, timeout=8.0, env=None):
            if list(cmd)[:2] == ["gnome-extensions", "enable"]:
                return 1, "", "not loaded"
            if list(cmd)[:2] == ["gsettings", "set"]:
                return 1, "", "cannot set"
            return 0, "@as []", ""

        with TmpExtensionDirs(uuid=uuid, installed=True, enabled=False), \
                mock.patch.object(trayenv, "desktop_environment",
                                  lambda: {"family": "gnome", "isWayland": True}):
            with mock.patch.object(trayenv, "_run", failing_run):
                out = trayenv.enable_extension()
        self.assertFalse(out["ok"])
        self.assertIn(uuid, "\n".join(out["manualCommands"]))


class TestStatusExtraFields(unittest.TestCase):
    """v0.1.8.6：/api/tray/status 新增 action / shellMode / canAutoInstall / 发行版字段。"""

    GNOME_ENV = {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}
    #: 注意用 staticmethod：普通 class 属性里的函数会被绑定成方法（which(name) 传成 self）
    WHICH = staticmethod(_which_factory({"dnf", "pkexec", "gsettings", "gnome-extensions"}))

    def _status(self, tray, *, shell_mode=True, env=None):
        with mock.patch.object(trayenv, "read_os_release",
                               lambda *a, **k: {"id": "fedora", "name": "Fedora Linux 43",
                                                "pretty_name": "Fedora Linux 43",
                                                "version_id": "43"}):
            return trayenv.status(tray, shell_mode=shell_mode, environ=env or self.GNOME_ENV,
                                  system="Linux", which=self.WHICH)

    def test_missing_extension_action_install(self):
        with TmpExtensionDirs(installed=False, enabled=False):
            out = self._status({"available": False, "backend": "qt"})
        install = out["install"]
        self.assertEqual(install["action"], "install")
        self.assertTrue(install["canAutoInstall"])
        self.assertTrue(install["shellMode"])
        self.assertFalse(install["browserMode"])
        self.assertEqual(install["elevation"]["tool"], "pkexec")
        self.assertEqual(out["os"]["family"], "fedora")
        self.assertEqual(out["os"]["name"], "Fedora Linux 43")

    def test_browser_mode_marks_manual_install(self):
        with TmpExtensionDirs(installed=False, enabled=False):
            out = self._status({"available": False, "backend": "qt"}, shell_mode=False)
        install = out["install"]
        self.assertEqual(install["action"], "manual-install")
        self.assertFalse(install["canAutoInstall"])
        self.assertTrue(install["browserMode"])
        self.assertTrue(install["manualCommands"])

    def test_disabled_extension_action_enable(self):
        with TmpExtensionDirs(installed=True, enabled=False):
            out = self._status({"available": False, "backend": "qt"})
        self.assertEqual(out["install"]["action"], "enable")
        self.assertTrue(out["install"]["canEnable"])

    def test_needs_relogin_action(self):
        with TmpExtensionDirs(installed=True, enabled=True):
            out = self._status({"available": False, "backend": "qt"})
        self.assertEqual(out["advice"]["code"], "gnome-needs-relogin")
        self.assertEqual(out["install"]["action"], "relogin")

    def test_tray_ok_action_none(self):
        with TmpExtensionDirs(installed=True, enabled=True):
            out = self._status({"available": True, "backend": "qt"})
        self.assertEqual(out["advice"]["code"], "ok")
        self.assertEqual(out["install"]["action"], "none")

    def test_windows_install_shape_is_stable(self):
        out = trayenv.status({"available": True, "backend": "pystray"}, shell_mode=True,
                             system="Windows")
        install = out["install"]
        self.assertEqual(install["action"], "none")
        self.assertIn("elevation", install)
        self.assertFalse(install["canAutoInstall"])
        self.assertIn("family", out["os"])


if __name__ == "__main__":
    unittest.main()
