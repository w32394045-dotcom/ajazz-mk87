# -*- coding: utf-8 -*-
"""HID 自检：为什么识别不到 MK87。

用途：用户反馈「设备识别不到」时，跑一条命令就能拿到所需全部信息：

    MK87Config --diagnose              # 打包版（Linux/Windows 均可用）
    python3 probe/linux_hid_check.py   # 源码仓库

输出内容：
* hidapi 后端（Linux 必须是 hidraw；libusb 后端不可用）；
* ``hidapi enumerate()`` 原始结果（path / usage_page / product）；
* 本工具解析后的接口（usage page、payload、能否打开）；
* ``/sys/class/hidraw`` 每个节点的 vid/pid/接口号/report descriptor/权限；
* udev 规则是否安装；
* 结论 + 下一步建议。

所有读取都做了异常包裹：诊断本身不允许抛异常，否则用户拿不到信息。
"""
from __future__ import annotations

import importlib
import os
import platform
import sys
from typing import List, Optional

from . import const, transport


def _fmt_path(path) -> str:
    if isinstance(path, (bytes, bytearray)):
        return bytes(path).decode("utf-8", "replace")
    return str(path)


def _read_node_descriptor(device_dir: str) -> Optional[bytes]:
    try:
        with open(os.path.join(device_dir, "report_descriptor"), "rb") as f:
            return f.read(4096)
    except Exception:  # noqa: BLE001
        return None


def _permission_text(path: str) -> str:
    try:
        read = os.access(path, os.R_OK)
        write = os.access(path, os.W_OK)
    except Exception:  # noqa: BLE001
        return "未知"
    if read and write:
        return "可读写"
    if read:
        return "只可读（缺写权限）"
    return "不可读写（权限不足）"


def _udev_rule_state() -> str:
    candidates = [
        "/etc/udev/rules.d/99-ajazz-mk87.rules",
        "/usr/lib/udev/rules.d/99-ajazz-mk87.rules",
        "/lib/udev/rules.d/99-ajazz-mk87.rules",
    ]
    found = [p for p in candidates if os.path.exists(p)]
    if not found:
        return "未找到 99-ajazz-mk87.rules（安装包会放到 /usr/lib/udev/rules.d/）"
    return "已安装: " + ", ".join(found)


def collect_diagnostics() -> List[str]:
    """收集诊断信息，返回可直接打印的文本行。"""
    lines: List[str] = []

    def add(text: str = "") -> None:
        lines.append(text)

    add("== 环境 ==")
    add(f"平台       : {platform.platform()}")
    add(f"Python     : {sys.version.split()[0]}")
    add(f"打包运行   : {getattr(sys, 'frozen', False)}")
    add(f"模块目录   : {os.path.dirname(os.path.abspath(__file__))}")
    if platform.system() == "Linux":
        try:
            add(f"内核       : {platform.release()}")
        except Exception:  # noqa: BLE001
            pass

    add()
    add("== hidapi 后端 ==")
    add(f"当前后端   : {transport.BACKEND}（Linux 必须是 hidraw）")
    add(f"已加载模块 : {getattr(transport.hid, '__file__', None) or '(未导入)'}")
    module_names = ("hidraw", "hid") if platform.system() == "Linux" else ("hid",)
    for name in module_names:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            add(f"import {name:<6}: 失败 —— {exc}")
            continue
        version = ""
        try:
            version = f"  version_str={mod.version_str()}"
        except Exception:  # noqa: BLE001
            pass
        add(f"import {name:<6}: OK -> {getattr(mod, '__file__', None)}{version}")

    add()
    add(f"== hidapi enumerate(0x{const.VID:04X}, 0) ==")
    if transport.hid is None:
        add("(hidapi 未加载，跳过)")
    else:
        try:
            raw = transport.hid.enumerate(const.VID, 0)
        except Exception as exc:  # noqa: BLE001
            add(f"enumerate 失败: {exc}")
        else:
            add(f"{len(raw)} 条记录")
            for d in raw:
                add("  path={!r} pid=0x{:04X} iface={} product={!r} usagePage=0x{:04X} "
                    "usage=0x{:04X}".format(
                        _fmt_path(d.get("path")), int(d.get("product_id", 0) or 0),
                        d.get("interface_number"), _decode(d.get("product_string")),
                        int(d.get("usage_page", 0) or 0), int(d.get("usage", 0) or 0)))

    add()
    add("== 本工具解析后的接口 ==")
    ifaces = []
    try:
        ifaces = transport.enumerate_ifaces(const.VID)
    except Exception as exc:  # noqa: BLE001
        add(f"解析失败: {exc}")
    else:
        add(f"{len(ifaces)} 个接口")
        for info in ifaces:
            path = _fmt_path(info.path)
            perm = ""
            if platform.system() == "Linux" and path.startswith("/dev/"):
                perm = " [" + _permission_text(path) + "]"
            add(f"  {path} pid=0x{info.pid:04X} iface={info.interface_number} "
                f"usagePage=0x{info.usage_page:04X} usage=0x{info.usage:04X} "
                f"payload={info.payload_len}{perm}")
            if info.usage_page == 0:
                desc = transport._read_report_descriptor(info)
                if desc:
                    up, usage = transport.parse_report_descriptor_usage(desc)
                    add(f"    report descriptor {len(desc)}B -> usagePage=0x{(up or 0):04X} "
                        f"usage=0x{(usage or 0):04X} head={desc[:16].hex()}")
                else:
                    add("    [!] 读不到 report descriptor")

    if platform.system() == "Linux":
        add()
        add("== /sys/class/hidraw ==")
        nodes = list(transport.iter_sysfs_hidraw() or ())
        if not nodes:
            add("(空 —— 内核没有 hidraw 节点，可能不是 HID 设备或驱动未绑定)")
        for name, device_dir in nodes:
            uevent = transport.read_sysfs_text(os.path.join(device_dir, "uevent")) or ""
            _bus, vid, pid = transport.parse_sysfs_hid_id(uevent)
            iface = transport._sysfs_interface_number(device_dir)
            desc = _read_node_descriptor(device_dir)
            up, usage = transport.parse_report_descriptor_usage(desc or b"")
            devnode = os.path.join("/dev", name)
            add(f"  {devnode} vid=0x{(vid or 0):04X} pid=0x{(pid or 0):04X} iface={iface} "
                f"usagePage=0x{(up or 0):04X} usage=0x{(usage or 0):04X} "
                f"[{_permission_text(devnode)}]")
        add()
        add("== udev 规则 ==")
        add("  " + _udev_rule_state())
        add("  安装命令: sudo cp packaging/udev/99-ajazz-mk87.rules /etc/udev/rules.d/ && "
            "sudo udevadm control --reload-rules && sudo udevadm trigger")

    add()
    add("== 结论 ==")
    lines.extend(_conclusion(ifaces))
    return lines


def _decode(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return str(value or "")


def _conclusion(ifaces) -> List[str]:
    out: List[str] = []
    usb_pages = {i.usage_page for i in ifaces if i.pid == const.PID_USB}
    dongle_pages = {i.usage_page for i in ifaces if i.pid == const.PID_DONGLE}
    if transport.BACKEND == "missing":
        out.append("✗ hidapi 没装/没打包进来：pip install hidapi（打包版请升级到 v0.1.6+）")
        return out
    if platform.system() == "Linux" and transport.BACKEND != "hidraw":
        out.append("✗ Linux 用的是 libusb 后端（模块 hid），不能用于配置键盘；需要 hidraw 模块。")
    if const.PID_USB in {i.pid for i in ifaces}:
        if const.USAGE_PAGE_PROTOCOL in usb_pages:
            out.append("✓ 键盘 USB 主协议接口 (0xFF68) 已识别 —— 设备连接应该正常。")
            if const.USAGE_PAGE_TFT in usb_pages:
                out.append("✓ TFT 接口 (0xFF67) 已识别。")
            else:
                out.append("! 没找到 TFT 接口 (0xFF67)：屏幕/动画功能可能不可用。")
        else:
            out.append("✗ 枚举到了 0x0C45:0x8047，但没有 0xFF68 主协议接口。")
            out.append("  若上面的 usagePage 都是 0x0000：用 hidraw 后端重试（或把本文件发给开发者）。")
            out.append("  若 sysfs 表里能看到 0xFF68：权限或后端不匹配，按 udev 规则处理后重插键盘。")
    elif const.PID_DONGLE in {i.pid for i in ifaces}:
        if const.USAGE_PAGE_24G_PROTOCOL in dongle_pages:
            out.append("✓ 2.4G 接收器主协议接口 (0xFF60) 已识别。")
        else:
            out.append("✗ 枚举到 2.4G 接收器但没有 0xFF60 接口。")
    else:
        out.append("✗ 没有枚举到任何 0x0C45 设备：")
        out.append("  * 键盘是否插好/开机？USB 线换口或换线试试；")
        out.append("  * Linux: lsusb | grep -i 0c45、ls -l /dev/hidraw* 看看有没有节点；")
        out.append("  * 2.4G: 接收器插上后键盘要开机并切到 2.4G 模式。")
    if platform.system() == "Linux" and transport.BACKEND == "hidraw":
        out.append("提示：若结论已 ✓ 但 UI 仍显示未连接，请把本输出 + "
                   "~/.local/state/mk87/logs/mk87.log 一起反馈。")
    return out
