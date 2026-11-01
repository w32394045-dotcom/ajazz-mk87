/* api.js — REST + WebSocket 封装。契约见 driver/docs/design.md §4。
   - 正常模式：/api/* + /ws
   - mock 模式：?mock=1 强制，或启动时 /api/status 失败自动启用内置 mock 层
   - 事件总线：api.on('event', e => e.type) / api.on('ws:status', cb) */
import { Emitter } from './util.js';

const STATUS_TIMEOUT = 1600;

export class Api extends Emitter {
  constructor() {
    super();
    this.mode = 'detecting';       // detecting | live | mock
    this.ws = null;
    this.wsState = 'closed';       // closed | connecting | open
    this.mock = null;
    this._reconnectTimer = null;
    this._reconnectDelay = 1200;
    this._closedByUs = false;
    this._debug = new URLSearchParams(location.search).has('mock');
  }

  /* ------------------------------------------------------------ boot */
  async init() {
    const forced = new URLSearchParams(location.search).get('mock') === '1';
    if (!forced) {
      try {
        const status = await this._probeStatus();
        if (status && typeof status.connected === 'boolean') {
          this.mode = 'live';
          this.emit('mode', this.mode);
          return status;
        }
      } catch (e) {
        console.info('[api] /api/status 不可用，启用 mock 演示模式', e?.message || e);
      }
    }
    await this._useMock();
    return this.request('GET', '/api/status');
  }

  async _probeStatus() {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), STATUS_TIMEOUT);
    try {
      const res = await fetch('/api/status', { signal: ctrl.signal, headers: { Accept: 'application/json' } });
      if (!res.ok) return null;
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async _useMock() {
    if (this.mock) return;
    this.mode = 'mock';
    const { MockServer } = await import('./mock.js');
    this.mock = new MockServer((type, data) => this.dispatch({ type, data }));
    this.emit('mode', this.mode);
    this.emit('ws:open');
    this.wsState = 'open';
  }

  /* ------------------------------------------------------------ http */
  /** 按接口选择超时：转换/上传/备份恢复可能很慢 */
  _timeoutFor(path) {
    if (/\/api\/tft\/(convert|upload_file)/.test(path)) return 180000;
    if (/\/api\/backup\/restore/.test(path)) return 60000;
    if (/\/api\/lighting\/frames|\/api\/device\/raw/.test(path)) return 30000;
    return 12000;
  }

  async request(method, path, body) {
    if (this.mode === 'mock') {
      if (!this.mock) await this._useMock();
      return this.mock.handle(method, path, body);
    }
    const init = { method, headers: { Accept: 'application/json' } };
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this._timeoutFor(path));
    init.signal = ctrl.signal;
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      if (e && e.name === 'AbortError') {
        const err = new Error('请求超时（设备可能已休眠或后端忙）');
        err.code = 'timeout';
        throw err;
      }
      throw e;
    } finally {
      clearTimeout(timer);
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
    if (!res.ok) {
      const err = new Error(data?.message || data?.error || `HTTP ${res.status}`);
      err.status = res.status;
      err.code = data?.error;
      throw err;
    }
    return data;
  }

  get(path) { return this.request('GET', path); }
  post(path, body = {}) { return this.request('POST', path, body); }
  put(path, body = {}) { return this.request('PUT', path, body); }
  del(path) { return this.request('DELETE', path); }

  /* ------------------------------------------------------------ websocket */
  connect() {
    if (this.mode === 'mock') {
      // mock 层自己按需发事件（进度 / 音乐电平 / 状态），这里只需汇报已连接
      this.wsState = 'open';
      this.emit('ws:open');
      return;
    }
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws`;
    this.wsState = 'connecting';
    this.emit('ws:state', this.wsState);
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.wsState = 'open';
      this._reconnectDelay = 1200;
      this.emit('ws:state', 'open');
      this.emit('ws:open');
    };
    ws.onmessage = (ev) => {
      let payload;
      try { payload = JSON.parse(ev.data); } catch { return; }
      if (payload && payload.type) this.dispatch(payload);
    };
    ws.onerror = () => { this.emit('ws:state', 'error'); };
    ws.onclose = () => {
      this.ws = null;
      this.wsState = 'closed';
      this.emit('ws:state', 'closed');
      if (!this._closedByUs) this._scheduleReconnect();
    };
  }

  _scheduleReconnect() {
    if (this._reconnectTimer) return;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, this._reconnectDelay);
    this._reconnectDelay = Math.min(this._reconnectDelay * 1.6, 8000);
  }

  disconnect() {
    this._closedByUs = true;
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = null;
    try { this.ws?.close(); } catch { /* ignore */ }
    this.ws = null;
  }

  /** 统一事件：{type, data} → 'event' + 'ws:<type>' */
  dispatch(evt) {
    if (!evt || !evt.type) return;
    this.emit('event', evt);
    this.emit(`ws:${evt.type}`, evt.data);
  }

  get isMock() { return this.mode === 'mock'; }
}

/* 便于页面直接使用的“契约层”辅助函数 */
export function rgbToHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const d = max - min;
  let hh = 0;
  if (d !== 0) {
    if (max === r) hh = ((g - b) / d) % 6;
    else if (max === g) hh = (b - r) / d + 2;
    else hh = (r - g) / d + 4;
  }
  hh = Math.round(hh * 60);
  if (hh < 0) hh += 360;
  return [hh, max === 0 ? 0 : d / max, max];
}
