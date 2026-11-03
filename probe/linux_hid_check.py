#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux HID 诊断：为什么本工具在 Linux 上找不到 MK87。

背景：hidapi 的 Linux hidraw 后端在 ``hid.enumerate()`` 里 ``usage_page`` 恒为 0，
本工具又靠 usage page 区分 主协议(0xFF68) / TFT(0xFF67) / 2.4G(0xFF60) / 唤醒(0xFFFF)。
v0.1.5 起会自己读 HID report descriptor 解析 usage page。

用法（需要 python3 + hidapi 包）：
    python3 probe/linux_hid_check.py
若提示缺 hidapi：
    python3 -m pip install --user hidapi
没有 Python 环境时，直接把这些命令输出贴出来也行：
    lsusb -d 0c45:
    ls -l /dev/hidraw*
    for f in /dev/hidraw*; do echo "== $f"; udevadm info -q property -n "$f" | \
        grep -E 'ID_VENDOR_ID|ID_MODEL_ID|TAG'; done
    for f in /sys/class/hidraw/hidraw*/device/report_descriptor; \
        do echo "== $f"; head -c 32 "$f" | xxd; done
"""
import os
import platform
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "driver"))

VID = 0x0C45


def main() -> int:
    print("platform :", platform.platform())
    print("python   :", sys.version.split()[0], sys.executable)
    try:
        import hid  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print("\n[!] 没有安装 hidapi 的 Python 包:", exc)
        print("    请先: python3 -m pip install --user hidapi")
        print("    或按文件顶部注释里的 shell 命令收集信息。")
        return 2
    print("hidapi   :", getattr(hid, "version_str", "?"))

    try:
        raw = hid.enumerate(VID, 0)
    except Exception as exc:  # noqa: BLE001
        print("[!] hid.enumerate 失败:", exc)
        return 2
    print(f"\n== hid.enumerate(0x{VID:04X}, 0) -> {len(raw)} 个接口")
    for d in raw:
        print("  path={!r} pid=0x{:04X} product={!r} iface={} usage_page=0x{:04X} usage=0x{:04X}".format(
            d.get("path"), int(d.get("product_id", 0) or 0), d.get("product_string"),
            d.get("interface_number"), int(d.get("usage_page", 0) or 0), int(d.get("usage", 0) or 0)))

    from mk87lib import const, transport  # noqa: E402

    print("\n== 本工具解析后的接口（v0.1.5 会从 report descriptor 补齐 usage_page）")
    ifaces = transport.enumerate_ifaces(VID)
    for i in ifaces:
        path = i.path.decode("utf-8", "replace") if isinstance(i.path, (bytes, bytearray)) else str(i.path)
        perm = "?"
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            os.close(fd)
            perm = "可打开"
        except Exception as exc:  # noqa: BLE001
            perm = f"打不开: {exc}"
        print(f"  {path} pid=0x{i.pid:04X} iface={i.interface_number} "
              f"usagePage=0x{i.usage_page:04X} usage=0x{i.usage:04X} payload={i.payload_len} [{perm}]")
        if i.usage_page == 0:
            desc = transport._read_report_descriptor(i)
            if desc:
                up, usage = transport.parse_report_descriptor_usage(desc)
                print(f"    report descriptor ({len(desc)}B) -> usagePage=0x{(up or 0):04X} usage=0x{(usage or 0):04X}")
                print("    head:", desc[:24].hex())
            else:
                print("    [!] 读不到 report descriptor（hidraw 权限不足？）")

    def _has(pid, page):
        return any(i.pid == pid and i.usage_page == page for i in ifaces)

    print("\n== 结论")
    if _has(const.PID_USB, const.USAGE_PAGE_PROTOCOL):
        print("  ✓ 找到 USB 主协议接口（0x8047 / usagePage 0xFF68）")
        if not _has(const.PID_USB, const.USAGE_PAGE_TFT):
            print("  ! 没找到 TFT 接口（屏幕页可能不可用）")
        return 0
    if _has(const.PID_DONGLE, const.USAGE_PAGE_24G_PROTOCOL):
        print("  ✓ 找到 2.4G 主协议接口（接收器）")
        return 0
    print("  ✗ 没有找到任何 MK87 协议接口。若上面能看到 0c45 接口但 usagePage 仍为 0：")
    print("    - 确认已安装 udev 规则并重新插拔：")
    print("      sudo cp driver/packaging/udev/99-ajazz-mk87.rules /etc/udev/rules.d/")
    print("      sudo udevadm control --reload-rules && sudo udevadm trigger")
    print("    - 检查 /dev/hidraw* 对当前用户可读写（ls -l /dev/hidraw*）")
    print("    - 把本脚本输出 + ~/.local/state/mk87/logs/mk87.log 一起反馈")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
