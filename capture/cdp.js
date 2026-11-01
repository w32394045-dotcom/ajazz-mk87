'use strict';
/*!
 * cdp.js —— 极简 Chrome DevTools Protocol 客户端（零依赖）
 * ---------------------------------------------------------------------------
 * 只依赖 Node 内置能力：
 *   - fetch       : 访问 http://127.0.0.1:<port>/json/* 这些 HTTP 端点
 *   - WebSocket   : Node 22+ 全局内置（本机 Node v24），连 webSocketDebuggerUrl
 *
 * 提供的接口：
 *   const { CDP } = require('./cdp');
 *   const cdp = await CDP.connect('ws://127.0.0.1:9333/devtools/page/XXXX');
 *   const v   = await cdp.send('Runtime.evaluate', { expression: '1+1' });
 *   const off = cdp.on('Runtime.bindingCalled', p => console.log(p.name, p.payload));
 *
 * 另外导出几个 HTTP 辅助函数：
 *   httpJson(port, path, method, timeout)
 *   waitForVersion(port, opts)
 *   listTargets(port)
 *   findPageTarget(port)
 *   newPage(port, url)
 *
 * 说明：本工具只连「page target」，直连其 webSocketDebuggerUrl，
 *       因此不需要 flat session（sessionId）机制。
 * ---------------------------------------------------------------------------
 */

const DEFAULT_SEND_TIMEOUT = 30_000;   // 单条命令默认超时
const DEFAULT_HTTP_TIMEOUT = 3_000;

/* ============================ HTTP 辅助 ============================ */

/**
 * 请求 Chrome 的 /json/* 端点。
 * @param {number} port  远程调试端口
 * @param {string} pathAndQuery 形如 '/json/list'
 * @param {string} [method] 默认 GET
 * @param {number} [timeout]
 * @returns {Promise<any>} 解析后的 JSON（若响应体不是 JSON，返回原始文本）
 */
async function httpJson(port, pathAndQuery, method = 'GET', timeout = DEFAULT_HTTP_TIMEOUT) {
  const url = `http://127.0.0.1:${port}${pathAndQuery}`;
  const res = await fetch(url, {
    method,
    signal: AbortSignal.timeout(timeout),
    headers: { 'Content-Type': 'application/json' },
  });
  const text = await res.text();
  if (!res.ok) {
    // /json/new 在旧版本上 GET 会 405，这里把状态码带出去让调用方决定
    const err = new Error(`HTTP ${res.status} ${res.statusText} for ${method} ${pathAndQuery}`);
    err.status = res.status;
    err.body = text;
    throw err;
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 轮询 /json/version 直到 Chrome 的调试端口就绪。
 * @returns {Promise<object>} 版本信息（含 Browser / webSocketDebuggerUrl）
 */
async function waitForVersion(port, { timeout = 30_000, interval = 200 } = {}) {
  const deadline = Date.now() + timeout;
  let lastErr = null;
  while (Date.now() < deadline) {
    try {
      const v = await httpJson(port, '/json/version', 'GET', 2_000);
      if (v && typeof v === 'object' && v.webSocketDebuggerUrl) return v;
      lastErr = new Error('/json/version 返回内容异常');
    } catch (err) {
      lastErr = err;
    }
    await sleep(interval);
  }
  throw new Error(`等待调试端口 ${port} 超时（${timeout}ms）：${lastErr && lastErr.message}`);
}

/** 列出所有 target（HTTP /json/list） */
async function listTargets(port) {
  const list = await httpJson(port, '/json/list');
  return Array.isArray(list) ? list : [];
}

/** 找一个 type === 'page' 的 target；优先 about:blank（我们自己开的那一个） */
async function findPageTarget(port, { preferUrl = 'about:blank' } = {}) {
  const list = await listTargets(port);
  const pages = list.filter((t) => t && t.type === 'page' && t.webSocketDebuggerUrl);
  if (!pages.length) return null;
  if (preferUrl) {
    const preferred = pages.find((t) => t.url === preferUrl);
    if (preferred) return preferred;
  }
  return pages[0];
}

/**
 * 新建一个 page target。
 * Chrome 111+ 要求 PUT，老版本是 GET —— 两个都试。
 */
async function newPage(port, url = 'about:blank') {
  const q = `/json/new?${encodeURIComponent(url)}`;
  for (const method of ['PUT', 'GET']) {
    try {
      const t = await httpJson(port, q, method, 10_000);
      if (t && t.id) return t;
      if (t && typeof t === 'string') {
        // 某些版本返回纯文本，退化成再查一次列表
        const found = await findPageTarget(port, { preferUrl: url });
        if (found) return found;
      }
    } catch (err) {
      if (method === 'GET') throw err;
    }
  }
  const found = await findPageTarget(port, { preferUrl: url });
  if (found) return found;
  throw new Error('无法创建新的 page target');
}

/* ============================ WebSocket 客户端 ============================ */

class CDP {
  /**
   * @param {string} wsUrl 形如 ws://127.0.0.1:9333/devtools/page/ABCD
   */
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.msgId = 0;
    this.pending = new Map();     // id -> {resolve, reject, timer, method}
    this.handlers = new Map();    // eventName -> Set<fn>
    this.allHandlers = new Set(); // 所有事件（调试用）
    this.closed = false;
    this.lastError = null;
  }

  /** 建立连接（等 open 事件） */
  static connect(wsUrl, { timeout = 15_000 } = {}) {
    return new Promise((resolve, reject) => {
      let ws;
      try {
        ws = new WebSocket(wsUrl);   // Node 22+ 内置
      } catch (err) {
        reject(new Error(`创建 WebSocket 失败: ${err.message}`));
        return;
      }

      const client = new CDP(wsUrl);
      client.ws = ws;

      const timer = setTimeout(() => {
        try { ws.close(); } catch {}
        reject(new Error(`连接 ${wsUrl} 超时（${timeout}ms）`));
      }, timeout);

      ws.addEventListener('open', () => {
        clearTimeout(timer);
        resolve(client);
      }, { once: true });

      ws.addEventListener('error', (ev) => {
        clearTimeout(timer);
        const msg = (ev && (ev.message || ev.error)) ? String(ev.error || ev.message) : 'unknown';
        reject(new Error(`WebSocket 连接错误: ${msg}`));
      }, { once: true });

      ws.addEventListener('close', () => {
        client.closed = true;
        client._rejectAll(new Error('WebSocket 已关闭'));
      });

      ws.addEventListener('message', (ev) => client._onMessage(ev));
    });
  }

  _onMessage(ev) {
    let text = ev.data;
    if (typeof text !== 'string') {
      try {
        if (text instanceof ArrayBuffer) text = Buffer.from(text).toString('utf8');
        else if (typeof text === 'object' && text && typeof text.text === 'function') {
          // Blob 情况：改成异步读
          text.text().then((t) => this._handleText(t)).catch(() => {});
          return;
        } else text = String(text);
      } catch {
        return;
      }
    }
    this._handleText(text);
  }

  _handleText(text) {
    let msg;
    try {
      msg = JSON.parse(text);
    } catch {
      return;   // 非 JSON 直接忽略
    }

    // ① 命令响应
    if (typeof msg.id === 'number' && this.pending.has(msg.id)) {
      const slot = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (slot.timer) clearTimeout(slot.timer);
      if (msg.error) {
        const err = new Error(`${slot.method} 失败: ${msg.error.message || JSON.stringify(msg.error)}`);
        err.code = msg.error.code;
        err.data = msg.error.data;
        slot.reject(err);
      } else {
        slot.resolve(msg.result || {});
      }
      return;
    }

    // ② 事件
    if (typeof msg.method === 'string') {
      const set = this.handlers.get(msg.method);
      if (set) {
        for (const fn of Array.from(set)) {
          try { fn(msg.params || {}, msg); } catch { /* 处理器异常不影响连接 */ }
        }
      }
      for (const fn of Array.from(this.allHandlers)) {
        try { fn(msg.method, msg.params || {}, msg); } catch {}
      }
    }
  }

  _rejectAll(err) {
    for (const [, slot] of this.pending) {
      if (slot.timer) clearTimeout(slot.timer);
      try { slot.reject(err); } catch {}
    }
    this.pending.clear();
  }

  /**
   * 发送一条 CDP 命令。
   * @param {string} method 例如 'Runtime.evaluate'
   * @param {object} [params]
   * @param {{timeout?:number}} [opts]
   */
  send(method, params = {}, opts = {}) {
    const timeout = opts.timeout ?? DEFAULT_SEND_TIMEOUT;
    if (!this.ws || this.closed) return Promise.reject(new Error(`发送 ${method} 失败：连接已关闭`));
    const id = ++this.msgId;
    return new Promise((resolve, reject) => {
      const timer = timeout > 0
        ? setTimeout(() => {
            if (this.pending.has(id)) {
              this.pending.delete(id);
              reject(new Error(`${method} 超时（${timeout}ms）`));
            }
          }, timeout)
        : null;
      this.pending.set(id, { resolve, reject, timer, method });
      try {
        this.ws.send(JSON.stringify({ id, method, params }));
      } catch (err) {
        if (timer) clearTimeout(timer);
        this.pending.delete(id);
        reject(new Error(`${method} 发送失败: ${err.message}`));
      }
    });
  }

  /**
   * 订阅事件，返回取消订阅函数。
   * @param {string} eventName 例如 'Runtime.bindingCalled'
   * @param {(params:object, msg:object)=>void} handler
   */
  on(eventName, handler) {
    let set = this.handlers.get(eventName);
    if (!set) {
      set = new Set();
      this.handlers.set(eventName, set);
    }
    set.add(handler);
    return () => set.delete(handler);
  }

  /** 订阅所有事件（返回取消函数） */
  onAny(handler) {
    this.allHandlers.add(handler);
    return () => this.allHandlers.delete(handler);
  }

  /** 等一次事件（可选超时） */
  once(eventName, timeout = 15_000) {
    return new Promise((resolve, reject) => {
      const off = this.on(eventName, (params, msg) => {
        off();
        if (timer) clearTimeout(timer);
        resolve(params);
      });
      const timer = timeout > 0
        ? setTimeout(() => { off(); reject(new Error(`等待事件 ${eventName} 超时（${timeout}ms）`)); }, timeout)
        : null;
    });
  }

  /** 关掉 WebSocket，拒绝所有在途命令 */
  close() {
    this.closed = true;
    this._rejectAll(new Error('客户端已关闭'));
    try { this.ws && this.ws.close(); } catch {}
  }
}

module.exports = {
  CDP,
  httpJson,
  waitForVersion,
  listTargets,
  findPageTarget,
  newPage,
  sleep,
};
