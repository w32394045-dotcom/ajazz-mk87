#!/usr/bin/env node
'use strict';
/*!
 * run.js —— AJAZZ 网页驱动 WebHID 抓包 CLI（零依赖）
 * ---------------------------------------------------------------------------
 * 用法：
 *   node run.js --url https://ajazz.driveall.cn --out ajazz_log.jsonl \
 *               [--port 9333] [--chrome <path>] [--profile <dir>] [--keep] \
 *               [--eval "<js>"] [--eval-delay 0] [--auto-exit 0] [--quiet]
 *
 * 做了什么：
 *   1. 用独立临时 profile 启动 Chrome Beta（可见窗口，绝不 headless）；
 *   2. 等 /json/version 就绪，找一个 type=page 的 target（没有就用 /json/new 建）；
 *   3. 连 CDP：Page.enable / Runtime.enable / Runtime.addBinding('__ajazzFlush')
 *      / Page.addScriptToEvaluateOnNewDocument(hook.js) → Page.navigate(目标 URL)；
 *   4. 把 Runtime.bindingCalled 的 payload 逐行追加写入 JSONL（每行立刻落盘）；
 *   5. 打印自检信息 + 中文操作提示；支持 --eval 在导航后执行一段 JS；
 *   6. Ctrl+C 时优雅关闭：关 Chrome、关文件、必要时删临时 profile。
 *
 * 只使用 Node 内置模块（fs / path / os / net / child_process / url）。
 * ---------------------------------------------------------------------------
 */

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const {
  CDP,
  waitForVersion,
  listTargets,
  findPageTarget,
  newPage,
  sleep,
} = require('./cdp');

/* ============================ 默认值 ============================ */

const DEFAULT_CHROME = 'C:\\Program Files\\Google\\Chrome Beta\\Application\\chrome.exe';
const DEFAULT_PORT = 9333;
const DEFAULT_URL = 'https://ajazz.driveall.cn';
const DEFAULT_OUT = 'ajazz_log.jsonl';
const HOOK_PATH = path.join(__dirname, 'hook.js');

/* ============================ 参数解析 ============================ */

const USAGE = `
AJAZZ WebHID 抓包工具（零依赖，CDP 注入）

用法:
  node run.js [选项]

选项:
  --url <url>       要抓包的页面（默认 ${DEFAULT_URL}）
  --out <file>      日志文件，JSONL，追加写（默认 ${DEFAULT_OUT}）
  --port <n>        Chrome 远程调试端口（默认 ${DEFAULT_PORT}，被占用会自动 +1 找空位）
  --chrome <path>   Chrome 可执行文件（默认 ${DEFAULT_CHROME}）
  --profile <dir>   指定 user-data-dir（默认在系统临时目录新建一个，不动你现有的 profile）
  --keep            退出时保留临时 profile（里面存着 WebHID 授权，可复用）
  --eval <js>       导航完成后在页面里执行一次这段 JS（返回值打印到 stdout）
  --eval-delay <ms> 执行 --eval 前等待的毫秒数（默认 0，页面异步初始化时可设 1000+）
  --auto-exit <s>   运行 N 秒后自动优雅退出（默认 0 = 一直跑到 Ctrl+C）
  --quiet           不逐条打印抓到的记录（只打关键日志）
  -h, --help        显示本帮助

示例:
  node run.js --url https://ajazz.driveall.cn --out ajazz_log.jsonl
  node run.js --url "file:///C:/.../test/fakehid.html" --out test/log.jsonl --auto-exit 12
`;

function parseArgs(argv) {
  const opts = {
    url: DEFAULT_URL,
    out: DEFAULT_OUT,
    port: DEFAULT_PORT,
    chrome: DEFAULT_CHROME,
    profile: null,
    keep: false,
    eval: null,
    evalDelay: 0,
    autoExit: 0,
    quiet: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const need = () => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`参数 ${a} 缺少取值`);
      return v;
    };
    switch (a) {
      case '--url': opts.url = need(); break;
      case '--out': opts.out = need(); break;
      case '--port': opts.port = Number(need()); break;
      case '--chrome': opts.chrome = need(); break;
      case '--profile': opts.profile = need(); break;
      case '--keep': opts.keep = true; break;
      case '--eval': opts.eval = need(); break;
      case '--eval-delay': opts.evalDelay = Number(need()); break;
      case '--auto-exit': opts.autoExit = Number(need()); break;
      case '--quiet': opts.quiet = true; break;
      case '-h':
      case '--help':
        process.stdout.write(USAGE);
        process.exit(0);
        break;
      default:
        // 允许用 `--` 之外的未知参数时报错，避免拼错参数悄悄跑错
        throw new Error(`未知参数: ${a}\n${USAGE}`);
    }
  }

  if (!Number.isFinite(opts.port) || opts.port <= 0) throw new Error('--port 必须是正整数');
  if (!Number.isFinite(opts.evalDelay) || opts.evalDelay < 0) throw new Error('--eval-delay 必须 >= 0');
  if (!Number.isFinite(opts.autoExit) || opts.autoExit < 0) throw new Error('--auto-exit 必须 >= 0');
  return opts;
}

/* ============================ 小工具 ============================ */

function log(...args) {
  process.stdout.write(args.join(' ') + '\n');
}
function logErr(...args) {
  process.stderr.write(args.join(' ') + '\n');
}

/** 找一个可用端口：从 start 开始逐个试探（最多 30 个） */
function findFreePort(start) {
  return new Promise((resolve, reject) => {
    let port = start;
    let tries = 0;
    const attempt = () => {
      if (tries++ > 30) {
        reject(new Error(`从 ${start} 开始连续 30 个端口都被占用，请用 --port 指定其它端口`));
        return;
      }
      const srv = net.createServer();
      srv.unref();
      srv.once('error', () => { srv.close(); port++; attempt(); });
      srv.once('listening', () => {
        const p = srv.address().port;
        srv.close(() => resolve(p));
      });
      try {
        srv.listen(port, '127.0.0.1');
      } catch {
        port++;
        attempt();
      }
    };
    attempt();
  });
}

/** 0x0c45 这种格式（不足 4 位补零） */
function hex4(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '????';
  return '0x' + Number(n).toString(16).padStart(4, '0');
}

/* ============================ 主流程 ============================ */

async function main() {
  const opts = parseArgs(process.argv.slice(2));

  /* ---------- 0. 准备路径 / 日志文件 ---------- */
  const outPath = path.resolve(process.cwd(), opts.out);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  if (!fs.existsSync(opts.chrome)) {
    throw new Error(`找不到 Chrome: ${opts.chrome}\n请用 --chrome 指定正确路径`);
  }
  if (!fs.existsSync(HOOK_PATH)) {
    throw new Error(`找不到 hook.js: ${HOOK_PATH}（必须和 run.js 放同一目录）`);
  }
  const hookSource = fs.readFileSync(HOOK_PATH, 'utf8');

  // 日志文件：追加模式，低层 writeSync 保证「每行立即落盘」
  const fd = fs.openSync(outPath, 'a');
  let closed = false;

  const writeLine = (obj) => {
    if (closed) return;
    let line;
    try {
      line = JSON.stringify(obj);
    } catch {
      line = JSON.stringify({ dir: 'meta', phase: 'error', method: 'host-serialize', error: 'JSON 序列化失败' });
    }
    try {
      fs.writeSync(fd, line + '\n');
    } catch (err) {
      logErr(`[!] 写日志失败: ${err.message}`);
    }
  };

  /** 宿主侧（非页面侧）的元信息行：ts 为 null，epoch 为墙上时间 */
  const writeMeta = (method, extra) => {
    writeLine({
      ts: null,
      epoch: Date.now(),
      seq: null,
      dir: 'meta',
      phase: 'ok',
      method,
      reportId: null,
      data: null,
      device: null,
      collections: null,
      caller: null,
      error: null,
      durationMs: null,
      extra: extra || null,
    });
  };

  /* ---------- 1. 临时 profile ---------- */
  const ownProfile = !opts.profile;
  const profileDir = opts.profile
    ? path.resolve(process.cwd(), opts.profile)
    : path.join(os.tmpdir(), `ajazz-cdp-profile-${process.pid}-${Date.now().toString(36)}`);
  fs.mkdirSync(profileDir, { recursive: true });

  /* ---------- 2. 端口 ---------- */
  const port = await findFreePort(opts.port);

  /* ---------- 3. 启动 Chrome ---------- */
  const chromeArgs = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--enable-features=WebHID',
    '--remote-allow-origins=*',       // 允许非浏览器客户端发起的 WS 连接（Chrome 111+）
    '--disable-popup-blocking',
    '--window-size=1280,900',
    '--no-service-autorun',
    '--noerrdialogs',
    'about:blank',                    // 先开个空白页，注入完钩子再导航
  ];

  log('');
  log('══════════════════════════════════════════════════════════════');
  log('  AJAZZ WebHID 抓包工具  (CDP 注入 · 零依赖)');
  log('══════════════════════════════════════════════════════════════');
  log(`  Chrome : ${opts.chrome}`);
  log(`  Profile: ${profileDir}${ownProfile ? '  (临时，退出时清理)' : '  (--profile 指定)'}`);
  log(`  调试端口: ${port}`);
  log(`  日志    : ${outPath}`);
  log(`  目标页  : ${opts.url}`);
  log('──────────────────────────────────────────────────────────────');

  let chrome = null;
  let cdp = null;
  let shuttingDown = false;
  let autoExitTimer = null;

  /**
   * 判断子进程是否已结束。
   * ★ Windows 坑：被 kill() 终止的进程，Node 里 exitCode 仍然是 null，
   *   只有 signalCode 变成 'SIGTERM'。只看 exitCode 会误判「还活着」。
   */
  const isExited = (c) => !c || c.exitCode !== null || c.signalCode !== null;

  const chromeExitPromise = new Promise((resolve) => {
    chrome = spawn(opts.chrome, chromeArgs, {
      // ★ 用参数数组，绝不拼字符串 —— 路径里有空格也不会出错
      stdio: 'ignore',
      windowsHide: false,     // ★ 窗口必须可见
      detached: false,
    });
    chrome.once('error', (err) => {
      logErr(`[!] 启动 Chrome 失败: ${err.message}`);
      resolve('error');
    });
    chrome.once('exit', (code, signal) => resolve({ code, signal }));
  });

  writeMeta('session-start', {
    hookVersion: null,
    chromePath: opts.chrome,
    profile: profileDir,
    port,
    url: opts.url,
    pid: process.pid,
    chromePid: chrome && chrome.pid,
    node: process.version,
  });

  /* ---------- 4. 优雅关闭 ---------- */
  const shutdown = async (reason) => {
    if (shuttingDown) return;
    shuttingDown = true;
    log('');
    log(`[*] 正在退出（${reason}）...`);
    if (autoExitTimer) clearTimeout(autoExitTimer);

    writeMeta('session-end', { reason, out: outPath });

    try { cdp && cdp.close(); } catch {}

    // 关 Chrome（只针对我们自己启动的那个 PID）
    try {
      if (chrome && !isExited(chrome) && !chrome.killed) {
        // 注意：这里必须用「异步等待」。用 Atomics.wait 之类的同步阻塞会让
        // Node 事件循环停摆，child 的 'exit' 事件永远不会被处理。
        const waitExit = async (ms) => {
          const deadline = Date.now() + ms;
          while (!isExited(chrome) && Date.now() < deadline) await sleep(120);
          return isExited(chrome);
        };
        try { chrome.kill(); } catch (err) { logErr(`[!] chrome.kill 出错: ${err.message}`); }
        if (await waitExit(4000)) {
          log(`[*] 已关闭 Chrome（pid=${chrome.pid}，signal=${chrome.signalCode || 'exit' + chrome.exitCode}）`);
        } else {
          log('[*] Chrome 未响应正常退出，强制结束进程树...');
          try {
            spawnSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
          } catch {}
          await waitExit(3000);
        }
      }
    } catch (err) {
      logErr(`[!] 关闭 Chrome 时出错: ${err.message}`);
    }

    // 关日志文件
    if (!closed) {
      closed = true;
      try { fs.closeSync(fd); } catch {}
    }

    // 清理临时 profile
    if (ownProfile && !opts.keep) {
      try {
        fs.rmSync(profileDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
      } catch (err) {
        logErr(`[!] 清理临时 profile 失败（可以手动删）: ${profileDir}`);
      }
    } else if (ownProfile && opts.keep) {
      log(`[*] 已保留临时 profile: ${profileDir}`);
    }

    log('[*] 已退出，日志：' + outPath);
    process.exit(0);
  };

  for (const sig of ['SIGINT', 'SIGTERM', 'SIGBREAK', 'SIGHUP']) {
    try {
      process.on(sig, () => { shutdown(`收到 ${sig}`); });
    } catch {}
  }
  process.on('uncaughtException', (err) => {
    logErr(`[!] 未捕获异常: ${err && err.stack ? err.stack : err}`);
    shutdown('uncaughtException');
  });
  process.on('unhandledRejection', (err) => {
    logErr(`[!] 未处理的 Promise 拒绝: ${err && err.stack ? err.stack : err}`);
  });

  /* ---------- 5. 等调试端口、找 target ---------- */
  log('[*] 等待 Chrome 远程调试端口就绪...');
  let version;
  try {
    version = await waitForVersion(port, { timeout: 45_000 });
  } catch (err) {
    writeMeta('error', { stage: 'waitForVersion', error: err.message });
    throw new Error(`${err.message}\n提示：若 Chrome 提示「用户数据目录已在另一个进程中使用」，请换 --profile 或用 --keep 复用`);
  }
  log(`[+] 已连接调试端口，浏览器: ${version.Browser || '(未知)'}`);

  let target = await findPageTarget(port, { preferUrl: 'about:blank' });
  if (!target) {
    log('[*] 没有 page target，新建一个...');
    target = await newPage(port, 'about:blank');
  }
  if (!target || !target.webSocketDebuggerUrl) {
    throw new Error('找不到可用的 page target（webSocketDebuggerUrl 为空）');
  }
  log(`[+] 使用 target: ${target.id}  ${target.url || ''}`);
  writeMeta('target-attached', { targetId: target.id, url: target.url, wsUrl: target.webSocketDebuggerUrl });

  /* ---------- 6. 连 CDP ---------- */
  cdp = await CDP.connect(target.webSocketDebuggerUrl, { timeout: 20_000 });
  writeMeta('cdp-connected', { wsUrl: target.webSocketDebuggerUrl });

  // 6.1 先把 binding 和钩子挂好，再去导航 —— 顺序很重要
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');

  try {
    await cdp.send('Runtime.addBinding', { name: '__ajazzFlush' });
  } catch (err) {
    throw new Error(`Runtime.addBinding 失败: ${err.message}`);
  }

  const injection = await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
    source: hookSource,
    runImmediately: true,
    worldName: undefined,     // 明确：主世界，和页面共享 window
  });
  writeMeta('hook-injected', { identifier: injection && injection.identifier, bytes: hookSource.length });
  log(`[+] 钩子已注入（${hookSource.length} 字节，主世界，document-start）`);

  // 6.2 记录所有来自页面的抓包数据
  let recordCount = 0;
  const dirCounts = Object.create(null);
  cdp.on('Runtime.bindingCalled', (params) => {
    if (!params || params.name !== '__ajazzFlush') return;
    const payload = params.payload;
    if (typeof payload !== 'string' || !payload) return;
    recordCount++;

    // payload 本身就是一行合法 JSON（hook 用 JSON.stringify 生成），原样落盘
    if (closed) return;
    try {
      fs.writeSync(fd, payload + '\n');
    } catch (err) {
      logErr(`[!] 写日志失败: ${err.message}`);
    }

    if (opts.quiet) return;
    // 控制台实时摘要（只打印关键字段，避免刷屏）
    try {
      const rec = JSON.parse(payload);
      dirCounts[rec.dir] = (dirCounts[rec.dir] || 0) + 1;
      if (rec.dir === 'meta' && rec.method === 'hook-installed') {
        log(`[+] 页面钩子自检: webhid=${rec.extra && rec.extra.webhid} secure=${rec.extra && rec.extra.secure} href=${(rec.extra && rec.extra.href) || ''}`);
        return;
      }
      const idText = rec.reportId == null ? '' : ` id=0x${rec.reportId.toString(16).padStart(2, '0')}`;
      const lenText = rec.data && typeof rec.data.length === 'number' ? ` len=${rec.data.length}` : '';
      let hex = (rec.data && rec.data.hex) ? rec.data.hex : '';
      if (hex.length > 78) hex = hex.slice(0, 78) + '…';
      const errText = rec.error ? `  ERROR(${rec.error})` : '';
      const devText = rec.device && rec.device.productId != null
        ? ` [${hex4(rec.device.vendorId)}:${hex4(rec.device.productId)}]`
        : '';
      log(`  ${String(rec.seq).padStart(4, '0')} ${(rec.dir + '/' + rec.phase).padEnd(16)} ${String(rec.method).padEnd(22)}${devText}${idText}${lenText}${hex ? '  ' + hex : ''}${errText}`);
    } catch {
      log(`  ${payload.slice(0, 160)}`);
    }
  });

  /* ---------- 7. 导航 ---------- */
  log(`[*] 导航到 ${opts.url} ...`);
  let navResult = null;
  try {
    navResult = await cdp.send('Page.navigate', { url: opts.url });
  } catch (err) {
    logErr(`[!] 导航失败: ${err.message}`);
  }
  if (navResult && navResult.errorText) {
    logErr(`[!] 导航返回错误: ${navResult.errorText}`);
    writeMeta('error', { stage: 'navigate', error: navResult.errorText });
  }

  // 等页面加载完成（轮询 readyState，避免和事件时序斗智斗勇）
  const waitReady = async (timeout = 20_000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      try {
        const r = await cdp.send('Runtime.evaluate', {
          expression: 'document.readyState',
          returnByValue: true,
        }, { timeout: 5_000 });
        if (r && r.result && r.result.value === 'complete') return true;
      } catch { /* 导航中执行上下文可能被销毁，忽略重试 */ }
      await sleep(200);
    }
    return false;
  };
  const ready = await waitReady();
  log(ready ? '[+] 页面已加载完成' : '[!] 等待页面加载超时，继续运行');

  /* ---------- 8. 自检 ---------- */
  const selfCheckExpr = `(async () => {
    const h = navigator.hid;
    const out = {
      href: location.href,
      webhid: !!h,
      secure: (typeof isSecureContext === 'boolean') ? isSecureContext : null,
      userActivation: navigator.userActivation ? {
        isActive: navigator.userActivation.isActive,
        hasBeenActive: navigator.userActivation.hasBeenActive
      } : null,
      hookInstalled: !!window.__ajazzHookInstalled,
      hookState: (typeof window.__ajazzState === 'function') ? window.__ajazzState() : null,
      getDevicesPatched: !!(h && h.getDevices && !/\\{\\s*\\[native code\\]\\s*\\}/.test(Function.prototype.toString.call(h.getDevices))),
      requestDevicePatched: !!(h && h.requestDevice && !/\\{\\s*\\[native code\\]\\s*\\}/.test(Function.prototype.toString.call(h.requestDevice))),
      devices: null
    };
    try {
      if (h) {
        const list = await h.getDevices();
        out.devices = list.map(d => ({
          vendorId: d.vendorId, productId: d.productId, productName: d.productName,
          opened: d.opened,
          usagePage: (d.collections && d.collections[0] && d.collections[0].usagePage) || null
        }));
        out.deviceCount = list.length;
      }
    } catch (e) { out.devicesError = String(e); }
    return out;
  })()`;

  try {
    const sc = await cdp.send('Runtime.evaluate', {
      expression: selfCheckExpr,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    }, { timeout: 10_000 });
    const v = sc && sc.result && sc.result.value;
    if (v) {
      log('──────────────────────────────────────────────────────────────');
      log('[自检] navigator.hid =', v.webhid ? '存在' : '不存在（WebHID 不可用！）');
      log('[自检] isSecureContext =', v.secure);
      log('[自检] 用户激活状态 =', JSON.stringify(v.userActivation));
      log('[自检] 钩子已安装 =', v.hookInstalled, ' hid.getDevices 已包装 =', v.getDevicesPatched, ' requestDevice 已包装 =', v.requestDevicePatched);
      if (v.hookState) log('[自检] 钩子状态 =', JSON.stringify(v.hookState));
      if (v.devices) {
        log(`[自检] 已授权设备 ${v.devices.length} 个：`);
        if (!v.devices.length) log('        (无 —— 这是正常的：首次必须在页面上真实点击"连接设备"，Chrome 会弹原生选择框)');
        for (const d of v.devices) {
          log(`        VID=${hex4(d.vendorId)} PID=${hex4(d.productId)} usagePage=${hex4(d.usagePage)} "${d.productName}" opened=${d.opened}`);
        }
      }
      if (v.devicesError) log('[自检] getDevices 出错 =', v.devicesError);
      writeMeta('self-check', v);
    } else if (sc && sc.exceptionDetails) {
      log('[!] 自检脚本抛错:', sc.exceptionDetails.text || '');
    }
  } catch (err) {
    logErr(`[!] 自检失败: ${err.message}`);
  }

  /* ---------- 9. --eval ---------- */
  if (opts.eval) {
    if (opts.evalDelay > 0) {
      log(`[*] 等待 ${opts.evalDelay}ms 后执行 --eval ...`);
      await sleep(opts.evalDelay);
    }
    try {
      const r = await cdp.send('Runtime.evaluate', {
        expression: opts.eval,
        awaitPromise: true,
        returnByValue: true,
        userGesture: true,
        includeCommandLineAPI: true,
      }, { timeout: 30_000 });
      if (r && r.exceptionDetails) {
        logErr('[--eval] 页面抛错: ' + JSON.stringify(r.exceptionDetails.text || r.exceptionDetails));
        writeMeta('eval-error', r.exceptionDetails);
      } else {
        const val = r && r.result ? r.result.value : undefined;
        const text = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
        log('──────────────────────────────────────────────────────────────');
        log('[--eval] 结果:');
        log(text === undefined ? String(val) : text);
        writeMeta('eval-result', { value: val });
      }
    } catch (err) {
      logErr(`[--eval] 执行失败: ${err.message}`);
    }
  }

  /* ---------- 10. 中文操作提示 ---------- */
  log('══════════════════════════════════════════════════════════════');
  log('  浏览器已打开：' + opts.url);
  log('');
  log('  ▶ 请在网页上点击「连接设备」按钮，然后在弹出的原生窗口里');
  log('    选中 AJAZZ 键盘（VID 0x0C45 / PID 0x8047，"AJAZZ KEYBOARD"）并点「连接」。');
  log('  ▶ 之后页面里的每一次 USB 交互都会被自动记录。');
  log('');
  log('  日志文件：' + outPath);
  log('  按 Ctrl+C 退出（会自动关闭这个 Chrome 实例）。');
  log('══════════════════════════════════════════════════════════════');

  if (opts.autoExit > 0) {
    log(`[*] ${opts.autoExit} 秒后自动退出（--auto-exit）`);
    autoExitTimer = setTimeout(() => { shutdown('--auto-exit 到期'); }, opts.autoExit * 1000);
  }

  /* ---------- 11. 等浏览器退出 / Ctrl+C ---------- */
  try {
    const exited = await chromeExitPromise;
    if (exited && typeof exited === 'object' && !shuttingDown) {
      log(`[*] Chrome 已退出（code=${exited.code} signal=${exited.signal}）`);
      writeMeta('chrome-exit', exited);
      await shutdown('Chrome 进程结束');
    }
  } catch { /* 忽略 */ }

  // 打印统计（正常不会走到这里，Ctrl+C 时由 shutdown 直接 process.exit）
  if (!shuttingDown) {
    log(`[*] 共捕获 ${recordCount} 条记录；按 dir 统计: ${JSON.stringify(dirCounts)}`);
    await shutdown('流程结束');
  }
}

main().catch((err) => {
  logErr('');
  logErr('[错误] ' + (err && err.stack ? err.stack : String(err)));
  process.exit(1);
});
