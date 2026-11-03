#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MK87 配置工具启动入口。

    python driver/run.py                  # 启动本地服务并打开浏览器（默认 127.0.0.1:8477）
    python driver/run.py --port 9000      # 指定端口
    python driver/run.py --no-browser     # 不自动打开浏览器
    python driver/run.py --no-connect     # 不自动连接设备（UI 里手动连接）
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import uvicorn  # noqa: E402

from mk87lib import logsetup  # noqa: E402

logsetup.setup_logging(console=True, role="run")

from server.app import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="AJAZZ MK87 配置工具")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8477, help="监听端口（默认 8477）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--no-connect", action="store_true", help="启动时不自动扫描设备")
    parser.add_argument("--log-level", default="info", help="uvicorn 日志级别")
    args = parser.parse_args()

    if args.no_connect:
        os.environ["MK87_NO_AUTOCONNECT"] = "1"

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        def _open():
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()

    print("=" * 62)
    print("  AJAZZ MK87 配置工具")
    print(f"  Web UI : {url}")
    print(f"  API    : {url}api/docs")
    print("  关闭窗口 / Ctrl+C 退出")
    print("=" * 62)
    # uvicorn 默认日志配置会 dictConfig → 关掉我们已装好的 root handler
    # （会话日志/txt 日志全部失效，还刷 "Logging error" traceback），
    # 与 shell.py 一致：跳过 uvicorn 日志配置，让日志统一进本工具 handler。
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level,
                log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
