#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MK87 HID 自检（源码仓库版）：为什么识别不到设备。

打包版不需要 Python 环境，直接跑同一条自检：

    /opt/mk87/MK87Config --diagnose

本脚本用于源码/开发环境（需要 python3 + hidapi）：

    python3 -m pip install --user hidapi
    python3 probe/linux_hid_check.py

输出包含：hidapi 后端、enumerate 原始结果、本工具解析出的接口、
/sys/class/hidraw 节点 + usage page + 权限、udev 规则状态、结论。
把整份输出贴给开发者即可定位问题。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "driver"))


def main() -> int:
    print("MK87 HID 自检（源码版）")
    print("-" * 60)
    try:
        from mk87lib.diag import collect_diagnostics
    except Exception as exc:  # noqa: BLE001
        print(f"[!] 无法导入 mk87lib.diag: {exc}")
        print("    请在仓库根目录运行：python3 probe/linux_hid_check.py")
        print("    （或安装 hidapi：python3 -m pip install --user hidapi）")
        return 2
    try:
        lines = collect_diagnostics()
    except Exception as exc:  # noqa: BLE001
        print(f"[!] 自检失败: {exc}")
        return 2
    print("\n".join(lines))
    print("-" * 60)
    print("反馈时请附上以上全部输出 + ~/.local/state/mk87/logs/mk87.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
