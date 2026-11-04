#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux 原生托盘（Qt `QSystemTrayIcon` + `QMenu`）。

为什么不用 pystray（v0.1.7 及以前）
-----------------------------------
pystray 在 Linux 上按 ``appindicator → gtk → xorg`` 选后端；本项目打包体里没有
GTK/AppIndicator 的 ``gi`` 绑定，所以总是落到 ``_xorg``。而 ``pystray._xorg`` 里
``HAS_MENU = False``（源码注释 “Menus are not supported on X”），只处理左键
activate：图标能出现，右键没有任何反应 —— 这正是 2026-11-05 用户报告的现象。

Qt 的 ``QSystemTrayIcon``：
* X11 / Wayland 都由 Qt 实现 StatusNotifierItem + dbusmenu。KDE / XFCE /
  Cinnamon / MATE / Ubuntu GNOME 原生支持；GNOME 需要 AppIndicator 扩展
  （检测与一键安装见 ``trayenv.py``）。
* 右键菜单由 Qt 提供，图标与菜单在各桌面表现一致。
* Linux 打包体已经带 PyQt6（``pywebview[qt]`` 依赖），不需要新增运行时依赖。

线程模型
--------
Qt 控件只能在 GUI 线程创建。pywebview 的 ``webview.start(func=...)`` 会在**子线程**
调用 func，此时主线程的 ``QApplication`` 可能还没创建。所以：

1. 子线程里轮询 ``QApplication.instance()`` 直到就绪；
2. 建立一个 QObject 持有者并 ``moveToThread(app.thread())``；
3. 用 ``QMetaObject.invokeMethod(..., QueuedConnection)`` 把真正的创建工作投递到
   GUI 线程执行（与 pywebview 内部处理 js_api 的方式一致）；
4. 创建完成后把可用性写入模块级 ``STATE``，外壳据此决定「点窗口 X」是隐藏还是退出。
"""
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional

#: 托盘状态：available=False 表示没有托盘宿主（GNOME 缺扩展 / 桌面无托盘），
#: 外壳会因此在点窗口 X 时直接退出程序，避免窗口藏起来找不回。
STATE: Dict[str, object] = {"available": None, "backend": None, "error": None, "holder": None}


def reset_state() -> None:
    STATE.update({"available": None, "backend": None, "error": None, "holder": None})


def state() -> Dict[str, object]:
    return {
        "available": STATE.get("available"),
        "backend": STATE.get("backend"),
        "error": STATE.get("error"),
    }


def _set(**kwargs) -> None:
    STATE.update(kwargs)


def _import_qt():
    """返回 (QtCore, QtGui, QtWidgets)；qtpy 会按已安装的绑定选 PyQt6/PySide6。"""
    from qtpy import QtCore, QtGui, QtWidgets  # noqa: PLC0415

    return QtCore, QtGui, QtWidgets


def _make_holder(QtCore, QtGui, QtWidgets, host, icon_path: str, app_name: str):
    """在调用线程里定义 QObject 持有者（之后 moveToThread 到 GUI 线程）。

    :param host: 外壳对象，需提供
        ``show_window()`` / ``quit_app()`` / ``autostart_enabled()`` /
        ``toggle_autostart(checked) -> bool`` / ``tray_notify(title, message)``。
    """

    class TrayHolder(QtCore.QObject):
        def __init__(self) -> None:
            super().__init__()
            self.tray = None
            self.menu = None
            self.actions: Dict[str, object] = {}

        # ---------------------------------------------------------- GUI 线程
        def _icon(self):
            try:
                if icon_path and os.path.exists(icon_path):
                    return QtGui.QIcon(icon_path)
            except Exception:  # noqa: BLE001
                pass
            try:
                style = QtWidgets.QApplication.style()
                return style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon)
            except Exception:  # noqa: BLE001
                try:
                    return QtWidgets.QApplication.style().standardIcon(
                        QtWidgets.QStyle.SP_ComputerIcon)
                except Exception:  # noqa: BLE001
                    return QtGui.QIcon()

        def _refresh_autostart(self) -> None:
            action = self.actions.get("autostart")
            if action is None:
                return
            try:
                action.setChecked(bool(host.autostart_enabled()))
            except Exception:  # noqa: BLE001
                pass

        def _toggle_autostart(self, checked: bool) -> None:
            try:
                actual = host.toggle_autostart(bool(checked))
            except Exception:  # noqa: BLE001
                actual = not bool(checked)
            try:
                self.actions["autostart"].setChecked(bool(actual))
            except Exception:  # noqa: BLE001
                pass

        def _on_activated(self, reason) -> None:
            try:
                reasons = QtWidgets.QSystemTrayIcon.ActivationReason
                show_reasons = {reasons.Trigger, reasons.DoubleClick}
                if reason in show_reasons:
                    host.show_window()
            except Exception:  # noqa: BLE001
                try:
                    host.show_window()
                except Exception:  # noqa: BLE001
                    pass

        @QtCore.Slot()
        def install(self) -> None:
            """在 GUI 线程创建托盘图标与菜单（由 start() 通过 QueuedConnection 投递）。"""
            try:
                available = bool(QtWidgets.QSystemTrayIcon.isSystemTrayAvailable())
                tray = QtWidgets.QSystemTrayIcon()
                tray.setIcon(self._icon())
                tray.setToolTip(app_name)
                menu = QtWidgets.QMenu()

                act_show = menu.addAction("显示主窗口")
                act_show.triggered.connect(lambda *_: host.show_window())
                act_auto = menu.addAction("开机自启")
                act_auto.setCheckable(True)
                act_auto.triggered.connect(self._toggle_autostart)
                menu.addSeparator()
                act_quit = menu.addAction("退出")
                act_quit.triggered.connect(lambda *_: host.quit_app())

                tray.setContextMenu(menu)
                tray.activated.connect(self._on_activated)
                menu.aboutToShow.connect(self._refresh_autostart)
                self.actions = {"show": act_show, "autostart": act_auto, "quit": act_quit}
                self.tray = tray
                self.menu = menu
                if available:
                    tray.show()
                else:
                    _set(available=False, backend="qt",
                         error="当前桌面没有托盘宿主（GNOME 需要 AppIndicator 扩展）")
                    return
                _set(available=True, backend="qt", error=None, holder=self)
                self._refresh_autostart()
            except Exception as exc:  # noqa: BLE001
                _set(available=False, backend="qt", error=f"创建托盘失败: {exc}")
                raise

        # ---------------------------------------------------------- 跨线程入口
        def notify(self, title: str, message: str) -> None:
            try:
                icon = QtWidgets.QSystemTrayIcon.MessageIcon.Information
            except Exception:  # noqa: BLE001
                icon = getattr(QtWidgets.QSystemTrayIcon, "Information", 1)
            try:
                self.tray.showMessage(str(title), str(message), icon, 5000)
            except Exception:  # noqa: BLE001
                pass

        def stop(self) -> None:
            try:
                if self.tray is not None:
                    self.tray.hide()
            except Exception:  # noqa: BLE001
                pass

        @QtCore.Slot()
        def hide(self) -> None:
            """GUI 线程隐藏托盘图标（退出流程用）。"""
            self.stop()

    return TrayHolder()


def start(
    host,
    *,
    icon_path: str = "",
    app_name: str = "MK87 Studio",
    timeout: float = 20.0,
) -> bool:
    """启动 Qt 托盘。

    必须在 ``webview.start(func=...)`` 的子线程里调用（不能阻塞 GUI 主线程）。
    返回 True 表示创建工作已成功投递到 GUI 线程；是否真的显示要看 ``STATE``。
    """
    try:
        QtCore, QtGui, QtWidgets = _import_qt()
    except Exception as exc:  # noqa: BLE001
        _set(available=False, backend="qt", error=f"Qt 不可用: {exc}")
        return False

    app = None
    deadline = time.time() + max(1.0, float(timeout))
    while time.time() < deadline:
        try:
            app = QtWidgets.QApplication.instance()
        except Exception as exc:  # noqa: BLE001
            _set(available=False, backend="qt", error=f"读取 QApplication 失败: {exc}")
            return False
        if app is not None:
            break
        time.sleep(0.05)
    if app is None:
        _set(available=False, backend="qt", error="等待 QApplication 超时")
        return False

    try:
        holder = _make_holder(QtCore, QtGui, QtWidgets, host, icon_path, app_name)
        holder.moveToThread(app.thread())
        QtCore.QMetaObject.invokeMethod(
            holder, "install", QtCore.Qt.ConnectionType.QueuedConnection
        )
        _set(holder=holder, backend="qt")
        return True
    except Exception as exc:  # noqa: BLE001
        _set(available=False, backend="qt", error=f"投递托盘创建任务失败: {exc}")
        return False


def notify(title: str, message: str) -> bool:
    """托盘气泡通知（仅 GUI 线程调用；其它线程请改用外壳包装）。"""
    holder = STATE.get("holder")
    if holder is None:
        return False
    try:
        holder.notify(title, message)
        return True
    except Exception:  # noqa: BLE001
        return False


def stop() -> None:
    holder = STATE.get("holder")
    if holder is None:
        return
    try:
        holder.stop()
    except Exception:  # noqa: BLE001
        pass


def hide_async() -> bool:
    """从任意线程请求 GUI 线程隐藏托盘图标（退出流程用，不保证一定执行）。"""
    holder = STATE.get("holder")
    if holder is None:
        return False
    try:
        QtCore = _import_qt()[0]
        QtCore.QMetaObject.invokeMethod(
            holder, "hide", QtCore.Qt.ConnectionType.QueuedConnection
        )
        return True
    except Exception:  # noqa: BLE001
        return False
