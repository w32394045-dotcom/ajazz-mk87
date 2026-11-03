#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无 Playwright 的 UI 截图 + 自检：headless Chrome/Edge + CDP。

用法（先起静态服务，或直接对真实后端）：

    python -m http.server 8123 --directory driver/web          # 纯前端 mock
    python tools/ui_shots.py "http://127.0.0.1:8123/?mock=1#music" ../capture/ui_music_preview

检查内容：
* 控制台 error / 未捕获异常（Runtime.exceptionThrown / Log.entryAdded）；
* 音乐页「当前方案 / 官方方案」双方案切换（官方默认）；
* 开始律动后两套方案都有逐键颜色，且方案热切换不停止律动；
* 停止后键盘无残留颜色；
* 英文 + 浅色主题无中文残留；
* 输出截图 + report.json，返回退出码（有检查失败时非 0）。

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
CDP_PORT = 9377


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


PAINTED = 'document.querySelectorAll(\'.kb-key[style*="background"]\').length'
STOP_ENABLED = ("(() => { const b=[...document.querySelectorAll('button')]"
                ".find(x=>x.textContent.trim()==='停止' || x.textContent.trim()==='Stop');"
                " return !!b && !b.disabled; })()")

# 官方方案新增控件（21 项显示模式 / 3 个下拉 / 原生帧率 3 档 / 实测 fps）
FIELD_INFO = ("(() => {{ const lab=[...document.querySelectorAll('.field-label')]"
              ".find(x=>x.textContent.includes('{label}')); if(!lab) return null;"
              " const field=lab.parentElement;"
              " const sel=field.querySelector('select');"
              " return {{options: sel?sel.options.length:0, value: sel?sel.value:null}}; }})()")
NATIVE_FPS_BUTTONS = ("(() => { const lab=[...document.querySelectorAll('.field-label')]"
                      ".find(x=>x.textContent.includes('原生帧率')); if(!lab) return 0;"
                      " const seg=lab.parentElement.querySelector('.segmented');"
                      " return seg?seg.querySelectorAll('button').length:0; })()")
FPS_READOUT = ("(() => { const lab=[...document.querySelectorAll('.field-label')]"
               ".find(x=>x.textContent.includes('原生帧率')); if(!lab) return null;"
               " const el=lab.parentElement.querySelector('.mono');"
               " return el?el.textContent.trim():null; })()")


def tab_active(match: str) -> str:
    return ("(() => { const tabs=[...document.querySelectorAll('.tabs button')];"
            f" return tabs.some(b=>b.classList.contains('active') && b.textContent.includes('{match}')); }})()")


async def click_tab(cdp: CDP, match: str) -> bool:
    return bool(await cdp.eval(
        "(() => { const tabs=[...document.querySelectorAll('.tabs button')];"
        f" const b=tabs.find(x=>x.textContent.includes('{match}')); if(!b) return false; b.click(); return true; }})()"))


async def run(url: str, out_dir: pathlib.Path) -> int:
    chrome = find_browser()
    profile = tempfile.mkdtemp(prefix="mk87-ui-shots-")
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={profile}", f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
         "--no-first-run", "--no-default-browser-check", "--disable-extensions",
         "--force-device-scale-factor=1", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20
        targets = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=1) as r:
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

            # 1) 应用启动 + 双方案标签（官方方案为默认）
            ok = await cdp.wait_for(
                "document.readyState==='complete' && !!document.querySelector('.tabs')"
                " && document.querySelectorAll('.tabs button').length>=2", timeout=20)
            report["checks"]["boot+scheme-tabs"] = bool(ok)
            report["tabs"] = await cdp.eval(
                "Array.from(document.querySelectorAll('.tabs button')).map(b=>b.textContent.trim())")
            report["defaultOfficial"] = await cdp.eval(tab_active("官方"))
            # 1b) 官方方案新增控件：21 项显示模式 / 3 个下拉 / 原生帧率 3 档 / LED 颜色 10 项
            mode_info = await cdp.eval(FIELD_INFO.format(label="显示模式"))
            bg_info = await cdp.eval(FIELD_INFO.format(label="背景模式"))
            color_info = await cdp.eval(
                "(() => { const lab=[...document.querySelectorAll('.field-label')]"
                ".find(x=>x.textContent.includes('LED 颜色')); if(!lab) return null;"
                " const sel=lab.parentElement.querySelector('select');"
                " return sel?{options:sel.options.length,value:sel.value}:null; })()")
            select_count = await cdp.eval("document.querySelectorAll('select.select').length")
            fps_buttons = await cdp.eval(NATIVE_FPS_BUTTONS)
            mode_values = await cdp.eval(
                "Array.from(document.querySelectorAll('select.select')[0]?.options || [])"
                ".map(o=>Number(o.value))")
            report["officialModeSelect"] = mode_info
            report["officialBackgroundSelect"] = bg_info
            report["officialColorSelect"] = color_info
            report["officialSelectCount"] = select_count
            report["nativeFpsButtons"] = fps_buttons
            report["officialModeValues"] = mode_values
            report["checks"]["official-display-modes-21"] = bool(mode_info and mode_info.get("options") == 21)
            report["checks"]["official-mode-order"] = mode_values == [
                1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10, 14, 15, 16, 17, 18, 19, 20, 21, 22, 100]
            report["checks"]["official-background-modes-11"] = bool(bg_info and bg_info.get("options") == 11)
            report["checks"]["official-led-colors-10"] = bool(
                color_info and color_info.get("options") == 10 and color_info.get("value") == "default")
            report["checks"]["official-selects-3"] = select_count == 3
            report["checks"]["native-fps-3-options"] = fps_buttons == 3
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "01-music-official-idle.png")

            # 2) 官方方案开始律动（mock 生成逐键帧）
            started = await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('button')]"
                ".find(x=>x.textContent.includes('开始律动') || x.textContent.includes('Start rhythm'));"
                " if(!b) return false; b.click(); return true; })()")
            report["checks"]["start-clicked"] = bool(started)
            painted = await cdp.wait_for(f"({PAINTED})>60", timeout=10)
            report["checks"]["official-preview-painted"] = bool(painted)
            report["officialPainted"] = await cdp.eval(PAINTED)
            # 2b) 热更新 LED 颜色 / 原生帧率（不停止律动），并显示后端实测 fps
            await cdp.eval(
                "(() => {"
                " const clab=[...document.querySelectorAll('.field-label')]"
                ".find(x=>x.textContent.includes('LED 颜色'));"
                " if(clab){ const sel=clab.parentElement.querySelector('select');"
                "  if(sel){ sel.value='aurora'; sel.dispatchEvent(new Event('change',{bubbles:true})); } }"
                " const flab=[...document.querySelectorAll('.field-label')]"
                ".find(x=>x.textContent.includes('原生帧率'));"
                " if(flab){ const b=[...flab.parentElement.querySelectorAll('.segmented button')]"
                ".find(x=>x.textContent.trim()==='60'); if(b) b.click(); }"
                " return true; })()")
            await asyncio.sleep(0.8)
            fps_readout = await cdp.eval(FPS_READOUT)
            report["officialFpsReadout"] = fps_readout
            try:
                report["checks"]["official-fps-readout"] = float(fps_readout) >= 20
            except (TypeError, ValueError):
                report["checks"]["official-fps-readout"] = False
            await asyncio.sleep(0.8)
            await cdp.eval("document.querySelector('.kb-deck')?.scrollIntoView({block:'center'}); true")
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "02-music-official-running.png")

            # 3) 热切换 → 当前方案（不应停止律动）
            switched = await click_tab(cdp, "当前")
            report["checks"]["hot-switch-to-current"] = bool(switched)
            hot = await cdp.wait_for(
                f"({PAINTED})>60 && {STOP_ENABLED}", timeout=10)
            report["checks"]["hot-switch-keeps-running"] = bool(hot)
            report["currentPainted"] = await cdp.eval(PAINTED)
            await asyncio.sleep(0.8)
            await cdp.eval("document.querySelector('.kb-deck')?.scrollIntoView({block:'center'}); true")
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "03-music-current-running.png")

            # 4) 热切换回官方方案（仍然运行）
            await click_tab(cdp, "官方")
            back = await cdp.wait_for(
                f"({PAINTED})>60 && {STOP_ENABLED} && {tab_active('官方')}", timeout=10)
            report["checks"]["hot-switch-back-official"] = bool(back)
            await asyncio.sleep(0.6)
            await cdp.shot(out_dir / "04-music-official-running-again.png")

            # 5) 停止后无残留颜色
            await cdp.eval(
                "(() => { const b=[...document.querySelectorAll('button')]"
                ".find(x=>x.textContent.trim()==='停止' || x.textContent.trim()==='Stop');"
                " if(b) b.click(); return true; })()")
            cleared = await cdp.wait_for(f"({PAINTED})===0", timeout=8)
            report["checks"]["stopped-clears-colors"] = bool(cleared)
            report["stoppedLeft"] = await cdp.eval(PAINTED)
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "05-music-official-stopped.png")

            # 6) 英文 + 浅色主题：不应有中文残留（语言选择器里的「简体中文」除外）
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
                "(() => { const b=[...document.querySelectorAll('button')]"
                ".find(x=>x.textContent.includes('Start rhythm')); if(b) b.click(); return true; })()")
            await asyncio.sleep(1.2)
            await cdp.eval("document.querySelector('.kb-deck')?.scrollIntoView({block:'center'}); true")
            await asyncio.sleep(0.4)
            await cdp.shot(out_dir / "06-music-official-en-light.png")

            report["errors"] = cdp.errors()
            out_dir.mkdir(parents=True, exist_ok=True)
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
    try:
        return asyncio.run(run(url, out))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
