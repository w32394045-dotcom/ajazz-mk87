#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动阶段日志（固定路径，每条立即 flush）。

为什么需要它
------------
2026-11-05 用户报告 v0.1.8 Linux 启动「闪退」，且日志目录里看不到东西。
打包程序 console=False，崩溃时 stderr 直接丢掉；如果是 PyInstaller 引导阶段、
日志初始化之前、或者 Qt 原生代码里的崩溃，常规日志根本来不及写。

本模块在 `shell.py` 的最早期就会调用，把「走到了哪一步」追加到用户主目录下的
固定文件 `~/.mk87-boot.log`（无论如何都能找到），用来区分：

* 连 `main-start` 都没有   → 程序根本没跑起来（打包/动态库/启动器问题）；
* 停在 `logging-ready` 之前 → 日志初始化或环境问题；
* 停在 `window-created` / `webview-start` → Qt/WebEngine 初始化问题；
* 停在 `tray-*`             → 托盘（QSystemTrayIcon）相关崩溃。

文件超过 256KB 时自动截断重写，避免无限增长。
"""
from __future__ import annotations

import os
import sys
import time

MAX_BYTES = 256 * 1024


def path() -> str:
    """启动日志固定路径（用户主目录，最容易找到）。"""
    return os.path.join(os.path.expanduser("~"), ".mk87-boot.log")


def _truncate_if_needed(file_path: str) -> None:
    try:
        if os.path.getsize(file_path) > MAX_BYTES:
            os.replace(file_path, file_path + ".1")
    except OSError:
        pass


def mark(stage: str, **fields) -> None:
    """追加一条启动阶段日志；任何失败都静默（不能因为诊断代码影响启动）。"""
    try:
        file_path = path()
        _truncate_if_needed(file_path)
        extra = ""
        if fields:
            extra = " " + " ".join(f"{k}={v!r}" for k, v in fields.items())
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} [{stage}]{extra}\n"
        with open(file_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except Exception:  # noqa: BLE001 - 诊断代码绝不影响启动
        pass


def read_tail(limit: int = 200) -> list:
    """读取最近的启动日志行（诊断包/设置页可用）。"""
    try:
        with open(path(), encoding="utf-8", errors="replace") as f:
            return f.readlines()[-limit:]
    except OSError:
        return []


def installed() -> bool:
    return os.path.exists(path())


# 方便在非常早期就用：模块导入时记一条，便于区分「导入 shell 就崩」
if __name__ == "__main__":
    mark("bootlog-standalone", argv=sys.argv[1:])
