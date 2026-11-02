#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无 Playwright 的 UI 截图 + 自检：headless Chrome/Edge + CDP。

用法（先起静态服务，或直接对真实后端）：

    python -m http.server 8123 --directory driver/web          # 纯前端 mock
    python tools/ui_shots.py "http://127.0.0.1:8123/?mock=1#music" capture/ui_music_preview

检查内容：
* 控制台 error / 未捕获异常（Runtime.exceptionThrown / Log.entryAdded）；
* 音乐页「当前方案 / 官方方案」双标签存在；
* 点「开始律动」后两套预览都有逐键颜色（mock 模式下由前端 mock 生成帧）；
* 输出截图 + 返回退出码（有 console error 时非 0）。

仅用于本地开发自检，不打包、不被运行时引用。
"""
from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    import websockets
except ImportError:  # pragma: no cover
    print("需要 websockets：pip install websockets", file=sys.stderr)
    raise SystemExit(2)

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

VIEWPORT = (1440, 1000)


def find_browser() -> str:
    for p in CHROME_CANDIDATES:
        if pathlib.Path(p).exists():
            return p
    hit = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("msedge")
    if hit:
        return hit
    raise SystemExit("找不到 Chrome/Edge（可用 CHROME 环境变量指定路径）")


class CDP:
    """极简 CDP 客户端（并发读响应 + 收集事件）。"""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.mid = 0
        self.pending: dict[int, asyncio.Future] = {}
        self.events: list[dict] = []
        self._reader = asyncio.ensure_future(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self.pending:
                    fut = self.pending.pop(msg["id"])
                    if not fut.done():
                        fut.set_result(msg)
                else:
                    self.events.append(msg)
        except Exception:  # noqa: BLE001
            pass

    async def call(self, method: str, **params):
        self.mid += 1
        mid = self.mid
        fut = asyncio.get_event_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        msg = await asyncio.wait_for(fut, timeout=30)
        if "error" in msg:
            raise RuntimeError(f"{method} 失败: {msg['error']}")
        return msg.get("result", {})

    async def eval(self, expr: str):
        r = await self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                            awaitPromise=True)
        return (r.get("result") or {}).get("value")

    async def wait_for(self, js_expr: str, timeout: float = 12.0, interval: float = 0.15) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if await self.eval(js_expr):
                    return True
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(interval)
        return False

    async def shot(self, path: pathlib.Path) -> None:
        res = await self.call("Page.captureScreenshot", format="png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(res["data"]))
        print(f"  截图 -> {path}")

    def errors(self) -> list[str]:
        out: list[str] = []
        for ev in self.events:
            m = ev.get("method")
            p = ev.get("params") or {}
            if m == "Runtime.exceptionThrown":
                det = (p.get("exceptionDetails") or {})
                txt = det.get("text") or (det.get("exception") or {}).get("description") or "exception"
                out.append(f"exception: {txt}")
            elif m == "Runtime.consoleAPICalled" and p.get("type") == "error":
                args = p.get("args") or []
                out.append("console.error: " + " ".join(str(a.get("value", a.get("description", ""))) for a in args))
            elif m == "Log.entryAdded":
                e = p.get("entry") or {}
                if e.get("level") == "error":
                    out.append(f"log.error: {e.get('text')} {e.get('url') or ''}")
        return out


async def run(url: str, out_dir: pathlib.Path) -> int:
    chrome = find_browser()
    profile = tempfile.mkdtemp(prefix="mk87-ui-shots-")
    port = 9377
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={port}", "--remote-allow-origins=*",
         f"--user-data-dir={profile}", f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
         "--no-first-run", "--no-default-browser-check", "--disable-extensions",
         "--force-device-scale-factor=1", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # 等 DevTools HTTP 端口
        deadline = time.time() + 20
        targets = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as r:
                    targets = json.load(r)
                if targets:
                    break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.2)
        page = next((t for t in (targets or []) if t.get("type") == "page"), None)
        if not page:
            raise SystemExit("拿不到 Chrome page target（浏览器可能启动失败）")

        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
            cdp = CDP(ws)
            await cdp.call("Runtime.enable")
            await cdp.call("Page.enable")
            await cdp.call("Log.enable")

            report: dict = {"url": url, "checks": {}, "errors": []}

            # 1) 应用启动 + 音乐页双标签
            ok = await cdp.wait_for(
                "document.readyState==='complete' && !!document.querySelector('.tabs')"
                " && document.querySelectorAll('.tabs button').length>=2", timeout=20)
            report["checks"]["boot+tabs"] = bool(ok)
            labels = await cdp.eval("Array.from(document.querySelectorAll('.tabs button')).map(b=>b.textContent.trim())")
            report["tabs"] = labels or []
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "01-music-current-idle.png")

            # 2) 当前方案：开始律动
            started = await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('开始律动'));"
                " if(!b) return false; b.click(); return true; })()")
            report["checks"]["start-clicked"] = bool(started)
            running = await cdp.wait_for(
                "!!document.querySelector('.kb-key[style*=\"background\"]')", timeout=8)
            painted = await cdp.eval(
                "document.querySelectorAll('.kb-key[style*=\"background\"]').length")
            report["checks"]["current-preview-painted"] = bool(running and (painted or 0) > 60)
            report["currentPainted"] = painted
            await asyncio.sleep(1.0)
            await cdp.eval("document.querySelector('.kb-deck')?.scrollIntoView({block:'center'}); true")
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "02-music-current-running.png")

            # 3) 官方方案
            switched = await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('.tabs button')].find(x=>x.textContent.includes('官方'));"
                " if(!b) return false; b.click(); return true; })()")
            report["checks"]["official-tab-clicked"] = bool(switched)
            official = await cdp.wait_for(
                "(() => { const tabs=[...document.querySelectorAll('.tabs button')];"
                " const on=tabs.some(b=>b.classList.contains('active') && b.textContent.includes('官方'));"
                " const n=document.querySelectorAll('.kb-key[style*=\"background\"]').length;"
                " return on && n>60; })()", timeout=8)
            painted2 = await cdp.eval(
                "document.querySelectorAll('.kb-key[style*=\"background\"]').length")
            report["checks"]["official-preview-painted"] = bool(official and (painted2 or 0) > 60)
            report["officialPainted"] = painted2
            await asyncio.sleep(1.0)
            # 滚到键盘可视化，截图里能同时看到双标签与说明文字
            await cdp.eval("document.querySelector('.kb-deck')?.scrollIntoView({block:'center'}); true")
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "03-music-official-running.png")

            # 4) 停止后不应残留颜色
            await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='停止');"
                " if(b) b.click(); return true; })()")
            await asyncio.sleep(1.2)
            left = await cdp.eval("document.querySelectorAll('.kb-key[style*=\"background\"]').length")
            report["checks"]["stopped-clears-colors"] = (left or 0) == 0
            report["stoppedLeft"] = left
            await cdp.shot(out_dir / "04-music-official-stopped.png")

            # 5) 英文 + 浅色主题：不应有中文残留（语言选择器里的「简体中文」除外）
            await cdp.eval("localStorage.setItem('mk87.lang', JSON.stringify('en'));"
                           "localStorage.setItem('mk87.theme', JSON.stringify('light')); true")
            await cdp.call("Page.reload")
            await asyncio.sleep(1.2)
            await cdp.wait_for("document.readyState==='complete' && !!document.querySelector('.tabs')", timeout=20)
            await asyncio.sleep(1.2)
            cjk = await cdp.eval(
                "(() => { const skip={SCRIPT:1,STYLE:1,NOSCRIPT:1,TEMPLATE:1};"
                " const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);"
                " const bad=[]; let n; while(n=walker.nextNode()){"
                "  const t=n.textContent.trim(); if(!t) continue;"
                "  const p=n.parentElement; if(p && skip[p.tagName]) continue;"
                "  if(/[\\u4e00-\\u9fff]/.test(t) && t!=='简体中文') bad.push(t.slice(0,40)); }"
                " return bad.slice(0,10); })()")
            report["checks"]["en-mode-no-cjk"] = not cjk
            report["cjkLeft"] = cjk or []
            await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Start rhythm'));"
                " if(b) b.click(); return true; })()")
            await asyncio.sleep(1.2)
            await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('.tabs button')].find(x=>/Official/.test(x.textContent));"
                " if(b) b.click(); return true; })()")
            await asyncio.sleep(1.0)
            await cdp.shot(out_dir / "05-music-official-en-light.png")

            report["errors"] = cdp.errors()
            (out_dir / "report.json").parent.mkdir(parents=True, exist_ok=True)
            (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            failed = [k for k, v in report["checks"].items() if not v] + (["console-errors"] if report["errors"] else [])
            print("\n结果:", "PASS" if not failed else f"FAIL {failed}")
            return 0 if not failed else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123/?mock=1#music"
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "capture/ui_music_preview")
    env = False
    try:
        return asyncio.run(run(url, out))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
