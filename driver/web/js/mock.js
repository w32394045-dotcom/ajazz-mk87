/* mock.js — 内置 mock 设备/后端：让全部页面在没有 Python 后端时也能交互演示。
   - 由 api.js 在 ?mock=1 或 /api/status 失败时自动实例化
   - 状态持久化到 localStorage（mk87.mock.state），刷新不丢
   - 按需模拟 20fps 音乐电平 / TFT 上传进度 / 电池变化等 WebSocket 事件
   契约与实际后端一致（design.md §4），只是数据是假的。 */
import { KEY_LAYOUT } from './data/keyboard.js';
import { ACTIONS, DEFAULT_KEYMAP } from './data/actions.js';
import { LIGHTING_MODES } from './data/lighting.js';
import { OFFICIAL_COLOR_SCHEMES, OFFICIAL_COLOR_MODE_VALUES, OFFICIAL_FRAME_RATES, OFFICIAL_DEFAULT_FRAME_RATE } from './data/music.js';
import { store, clamp } from './util.js';

const TFT_W = 240;
const TFT_H = 135;
const TFT_MAX_FRAMES = 140;
const TFT_FRAME_BYTES = TFT_W * TFT_H * 2; // 64800
const MACRO_CAPACITY = 3072;
const MACRO_SLOT_COUNT = 100;
const SLEEP_TIMES = [0, 1, 10, 20, 30];

const KEY_SLOTS = KEY_LAYOUT.rows.flat().map((k) => k.slot);

/* ---------------------------------------------------------------- 音乐律动 mock
   仅 mock 演示用的“近似官方渲染器”：真实逐键帧由后端 Python 渲染器生成，
   这里只是让没有硬件/后端时键盘可视化也有动画可看。 */
const MUSIC_MODES = [
  { mode: 13, name: '律动节拍', nameEn: 'Dance to the Beat' },
  { mode: 14, name: '光尘螺旋', nameEn: 'Dust Glow Spiral' },
  { mode: 17, name: '萤火轨迹', nameEn: 'Firefly Trail' },
  { mode: 4, name: '曲率频阶', nameEn: 'Curvature Frequency Steps' },
];
/* 官方方案显示模式（21 项，含 100 屏光联动；顺序与 data/music.js 一致） */
const MUSIC_OFFICIAL_MODES = [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10, 14, 15, 16, 17, 18, 19, 20, 21, 22, 100];
/* 官方方案已移植的渲染器：21 项里除 100（屏光联动，自研屏幕同步待做）之外的 20 项；
   与后端 mk87lib.music.V1_IMPLEMENTED_MODES 保持一致。 */
const MUSIC_OFFICIAL_IMPLEMENTED = MUSIC_OFFICIAL_MODES.filter((m) => m !== 100);
const MUSIC_IMPLEMENTED = [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
/* LED 颜色覆盖作用于全部动态多色模式（纯色 6/7/8/9/10/11 保持官方采样色） */
const MUSIC_COLOR_OVERRIDE_MODES = new Set(OFFICIAL_COLOR_MODE_VALUES);
const KEY_GEO = KEY_LAYOUT.rows.flat().map((k) => ({
  slot: k.slot,
  row: k.row,
  col: (k.x + k.w / 2) / KEY_LAYOUT.rowWidth,
  mid: (k.row + 0.5) / KEY_LAYOUT.rows.length,
}));
const KEY_DIST = KEY_GEO.map((k) => clamp(Math.hypot((k.col - 0.5) * 1.9, (k.mid - 0.5) * 1.15) / 1.05, 0, 1));

/* 官方 v1 纯色显示模式在 mock 里的颜色（与采样真值一致：FE 是 255 经 (c*n)>>8 缩放） */
const MOCK_SOLID = { 6: [254, 254, 254], 7: [254, 0, 0], 8: [254, 63, 0], 9: [254, 254, 0], 10: [0, 0, 254], 11: [0, 254, 0] };

/* LED 颜色覆盖：mock 只改变动态多色模式（1/2/4/5/13 + 14–22）的演示颜色，纯色模式保持官方采样色 */
function hexToRgb(hex) {
  const n = parseInt(String(hex).replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const MOCK_SCHEME_STOPS = new Map();
for (const c of OFFICIAL_COLOR_SCHEMES) {
  if (c.colors.length) MOCK_SCHEME_STOPS.set(c.id, c.colors.map(hexToRgb));
}
function schemeColorAt(id, t) {
  const stops = MOCK_SCHEME_STOPS.get(id);
  if (!stops || !stops.length) return null;
  if (stops.length === 1) return stops[0];
  const x = clamp(t, 0, 1) * (stops.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = stops[i];
  const b = stops[Math.min(i + 1, stops.length - 1)];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
function tintFrameColor(rgb, colorId, t) {
  const base = schemeColorAt(colorId, t);
  if (!base) return rgb;
  const intensity = Math.max(rgb[0], rgb[1], rgb[2]) / 255;
  const k = 0.12 + 0.88 * intensity;
  return base.map((v) => Math.round(clamp(v * k, 0, 255)));
}

function musicMockColors(mode, phase, level, levels, color) {
  const schemeId = color && color !== 'default' && MUSIC_COLOR_OVERRIDE_MODES.has(mode) ? color : null;
  const colors = {};
  for (let i = 0; i < KEY_GEO.length; i++) {
    const k = KEY_GEO[i];
    const d = KEY_DIST[i];
    let rgb = [0, 0, 0];
    if (mode === 13) {
      const wave = Math.max(0, Math.sin(d * 8.5 - phase * 2.4));
      const v = clamp(level * 1.9 * wave + wave * 0.12, 0, 1);
      rgb = hsl((20 + d * 250 + phase * 8) % 360, 95, 20 + v * 38);
    } else if (mode === 14) {
      const ang = Math.atan2(k.mid - 0.5, k.col - 0.5);
      const ray = Math.max(0, Math.sin(ang * 3 + phase * 1.4));
      const v = clamp(level * 1.7 * (0.3 + 0.7 * ray), 0, 1);
      rgb = hsl((ang * 57 + 200 + phase * 30) % 360, 90, 18 + v * 40);
    } else if (mode === 17) {
      const wave = Math.max(0, Math.sin(k.col * 7 - phase * 2.2)) * Math.max(0, 1 - Math.abs(k.mid - 0.5) * 1.3);
      const v = clamp(level * 1.8 * wave, 0, 1);
      rgb = hsl((190 + k.col * 90 + phase * 10) % 360, 95, 16 + v * 42);
    } else if (MOCK_SOLID[mode]) {
      // 官方 v1 纯色模式：单一颜色，按列频率强度调亮度
      const band = clamp(Math.floor(k.col * 32), 0, 31);
      const v = clamp((levels[band] || 0) * 1.5, 0, 1);
      if (v > 0.03) rgb = MOCK_SOLID[mode].map((x) => Math.round(x * v));
    } else {
      const band = clamp(Math.floor(k.col * 32), 0, 31);
      const v = clamp((levels[band] || 0) * 1.5, 0, 1);
      if (v > 0.03) rgb = hsl((205 + band * 5) % 360, 95, 16 + v * 42);
    }
    if (schemeId) rgb = tintFrameColor(rgb, schemeId, mode === 13 ? d : k.col);
    colors[k.slot] = rgb;
  }
  return colors;
}


/* mock 的「实测帧率」：官方方案在原生帧率附近抖动（浮点，60~66 之间），当前方案返回设定值 */
function musicMeasuredFps(m) {
  if (!m.running) return null;
  const base = m.official
    ? (Number(m.nativeFps) || OFFICIAL_DEFAULT_FRAME_RATE)
    : (Number(m.fps) || 20);
  const jitter = m.official ? (Math.random() * 1.4 - 0.7) : 0;
  let value = base + jitter;
  if (m.official && base >= 60) value = clamp(value, 60, 66);
  return Math.round(value * 10) / 10;
}


/* HSL → [r,g,b] */
function hsl(h, s, l) {
  h = ((h % 360) + 360) % 360; s /= 100; l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let rgb = [0, 0, 0];
  if (h < 60) rgb = [c, x, 0];
  else if (h < 120) rgb = [x, c, 0];
  else if (h < 180) rgb = [0, c, x];
  else if (h < 240) rgb = [0, x, c];
  else if (h < 300) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  return rgb.map((v) => Math.round(clamp((v + m) * 255, 0, 255)));
}

const NO_LED_SLOTS = new Set(KEY_LAYOUT.notes.noLed); // 99/100/102 屏幕位置，无 LED
function defaultCustomColors() {
  const colors = {};
  for (const row of KEY_LAYOUT.rows) {
    for (const k of row) {
      if (NO_LED_SLOTS.has(k.slot)) continue;
      const hue = (k.x / 275) * 300 + k.row * 12;
      colors[k.slot] = hsl(hue, 88, 56);
    }
  }
  return colors;
}

function defaultMacros() {
  const slots = Array.from({ length: MACRO_SLOT_COUNT }, (_, i) => ({ slot: i, actions: [] }));
  const mk = (usage) => ([
    { delay: 10, type: 'keyboard', press: true, usage },
    { delay: 10, type: 'keyboard', press: false, usage },
  ]);
  slots[0].actions = [...mk(4), ...mk(5), ...mk(6), ...mk(40)];
  slots[1].actions = [
    { delay: 0, type: 'keyboard', press: true, usage: 224 },
    ...mk(6),
    { delay: 0, type: 'keyboard', press: false, usage: 224 },
  ];
  slots[2].actions = [...mk(29)];
  return slots;
}

function macroBytes(actions) {
  if (!actions || !actions.length) return 0;
  return 4 + actions.length * 4;
}

const DEFAULT_SETTINGS = { theme: 'auto', language: 'zh' };
const DEFAULT_LIGHTING = {
  mode: 8,
  brightness: 5,
  speed: 3,
  direction: 0,
  colorMode: 1,
  color: { r: 56, g: 132, b: 255 },
};

const PERSIST_KEY = 'mk87.mock.state';

export class MockServer {
  constructor(emit) {
    this.emitEvent = emit;        // (type, data) => void
    this.timers = new Set();
    const debugParams = new URLSearchParams(location.search);
    this.simulateShell = debugParams.get('shell') === '1';
    this.simulateConflict = debugParams.get('conflict') === '1';
    this._tick = 0;
    this._i = 0;

    const saved = store.get(PERSIST_KEY, null) || {};
    this.state = {
      connected: saved.connected !== undefined ? saved.connected : true,
      transport: saved.transport || 'usb',
      battery: saved.battery || { percent: 76, charging: true },
      lighting: { ...DEFAULT_LIGHTING, ...(saved.lighting || {}) },
      custom: { colors: saved.custom?.colors || defaultCustomColors() },
      keymap: {
        normal: { ...DEFAULT_KEYMAP.normal, ...(saved.keymap?.normal || {}) },
        fn: { ...DEFAULT_KEYMAP.fn, ...(saved.keymap?.fn || {}) },
      },
      macros: saved.macros || defaultMacros(),
      sleepTime: saved.sleepTime !== undefined ? saved.sleepTime : 10,
      settings: { ...DEFAULT_SETTINGS, ...(saved.settings || {}) },
      autostart: saved.autostart === undefined ? false : !!saved.autostart,
      notifications: [
        { kind: 'wake', ts: Date.now() - 1000 * 60 * 37 },
        { kind: 'connect', ts: Date.now() - 1000 * 60 * 52 },
      ],
      conflicts: saved.conflicts || [],
      frames: { running: false, fps: 20, frames: 0 },
      music: {
        running: false, deviceId: 'default', sensitivity: 1.0, style: 'spectrum', fps: 20,
        mode: 13, requestedMode: 13, backmode: 0, backmodeBrightness: 100, amplitude: 50,
        color: 'default', nativeFps: OFFICIAL_DEFAULT_FRAME_RATE, official: false, measuredFps: null,
        level: 0, colors: {}, frame: 0,
      },
      tftJob: null,
      keytest: { running: false, events: [] },
      rawLog: [],
      info: {
        vid: 3141,
        pid: 32839,
        vendorId: 0x0c45,
        productId: 0x8047,
        product: 'AJAZZ KEYBOARD',
        manufacturer: 'SONiX',
        firmware: '1.19',
        serial: 'MK87-DEMO-0001',
        protocol: '0x8047',
        interface: '0xFF68 (MI_02)',
        frameVersion: 0,
      },
    };
    this._seedRandom = 12345;
    this._batteryTimer = setInterval(() => this._batteryTick(), 40000);
    this.timers.add(this._batteryTimer);
    this._notifyTimer = setInterval(() => this._notifyTick(), 52000);
    this.timers.add(this._notifyTimer);
  }

  /* ------------------------------------------------------------ helpers */
  _rand() {
    this._seedRandom = (this._seedRandom * 16807) % 2147483647;
    return this._seedRandom / 2147483647;
  }

  _save() {
    const s = this.state;
    store.set(PERSIST_KEY, {
      connected: s.connected,
      transport: s.transport,
      battery: s.battery,
      lighting: s.lighting,
      custom: s.custom,
      keymap: s.keymap,
      macros: s.macros,
      sleepTime: s.sleepTime,
      settings: s.settings,
      conflicts: s.conflicts,
      autostart: s.autostart,
    });
  }

  _emit(type, data) { this.emitEvent(type, data); }

  _toast(level, message) { this._emit('toast', { level, message }); }

  _mkdir(ms, fn) {
    const id = setTimeout(() => { this.timers.delete(id); fn(); }, ms);
    this.timers.add(id);
    return id;
  }

  _later(ms, value) {
    return new Promise((resolve, reject) => {
      this._mkdir(ms, () => (value instanceof Error ? reject(value) : resolve(value)));
    });
  }

  static fail(message, code = 'mock_error', status = 400) {
    const e = new Error(message);
    e.code = code;
    e.status = status;
    return e;
  }

  status() {
    const s = this.state;
    const wireless = s.transport === '2.4g'
      ? { transport: '2.4g', connected: s.connected, sleepTime: s.sleepTime, identity: { manufacturer: 1, product: 18, workMode: 2 } }
      : null;
    return {
      connected: s.connected,
      mock: true,
      shell: !!this.simulateShell,
      conflictItems: this.simulateConflict
        ? [{ code: 'usb_resource_conflict', zh: '模拟冲突：2.4G 接收器与键盘 USB 同插可能触发 Windows USB 资源不足（0xC000009A），请只保留一种连接。', en: 'Simulated conflict: plugging the 2.4G receiver and keyboard USB together may trigger a Windows USB resource shortage (0xC000009A) — keep only one connection.' }]
        : [],
      transport: s.connected ? s.transport : 'none',
      device: {
        vid: s.info.vid, pid: s.info.pid,
        product: s.info.product, manufacturer: s.info.manufacturer,
        firmware: s.info.firmware, serial: s.info.serial,
      },
      battery: { percent: s.battery.percent, charging: s.battery.charging },
      caps: {
        keyCount: 87, tft: true, tftMaxFrames: TFT_MAX_FRAMES, ledMaxFrames: 0,
        maxProfile: 0, music: true, wireless: true,
      },
      wireless,
      conflicts: s.conflicts,
      recentNotifications: s.notifications.slice(-8),
    };
  }

  _pushNotification(kind) {
    const n = { kind, ts: Date.now() };
    this.state.notifications.push(n);
    if (this.state.notifications.length > 60) this.state.notifications.splice(0, this.state.notifications.length - 60);
    this._emit('notification', n);
  }

  _batteryTick() {
    if (!this.state.connected) return;
    const b = this.state.battery;
    if (b.charging) {
      b.percent = Math.min(100, b.percent + 1);
    } else {
      b.percent = Math.max(20, b.percent - 1);
    }
    this._emit('battery', { ...b });
    this._emit('status', this.status());
  }

  _notifyTick() {
    if (!this.state.connected) return;
    // 低频模拟一条无线通知，让「无线」页的通知日志有内容
    const kinds = ['wake', 'sleep', 'wake'];
    this._pushNotification(kinds[Math.floor(this._rand() * kinds.length)]);
  }

  /* 供设置页的演示控制使用 */
  simulateDisconnect() {
    this.state.connected = false;
    this._save();
    this._emit('status', this.status());
    this._pushNotification('disconnect');
    return this.status();
  }

  simulateReconnect() {
    this.state.connected = true;
    this.state.transport = 'usb';
    this._save();
    this._emit('status', this.status());
    this._pushNotification('connect');
    return this.status();
  }

  setTransport(transport) {
    this.state.transport = transport === '2.4g' ? '2.4g' : 'usb';
    this.state.connected = true;
    this._save();
    this._emit('status', this.status());
    return this.status();
  }

  /* ------------------------------------------------------------ router */
  async handle(method, path, body) {
    method = method.toUpperCase();
    const rawPath = path.split('?')[0];
    const m = this._match(method, rawPath);
    if (!m) {
      console.warn('[mock] 未实现的接口', method, rawPath);
      throw MockServer.fail(`mock 未实现接口 ${method} ${rawPath}`, 'not_implemented', 404);
    }
    return m(body || {});
  }

  _match(method, path) {
    const routes = this._routes();
    for (const r of routes) {
      if (r.method !== method) continue;
      if (r.path instanceof RegExp) {
        const mm = path.match(r.path);
        if (mm) return (body) => r.handler(body, mm);
      } else if (r.path === path) {
        return (body) => r.handler(body);
      }
    }
    return null;
  }

  _routes() {
    const S = this.state;
    return [
      /* ---------------- 设备 / 状态 ---------------- */
      { method: 'GET', path: '/api/status', handler: () => this.status() },
      {
        method: 'POST', path: '/api/device/scan', handler: async () => {
          await this._later(220);
          S.connected = true;
          this._save();
          this._emit('status', this.status());
          this._toast('info', '已重新连接 AJAZZ KEYBOARD（mock）');
          return this.status();
        },
      },
      {
        method: 'GET', path: '/api/device/info', handler: async () => {
          await this._later(120);
          const fields = {
            sleepTime: S.sleepTime, displayTime: 0, debounceTime: 8, reportRate: 1000,
            gameMode: 0, tftDisplayTime: 0, keyDelay: 3, powerMode: 1,
          };
          return {
            ...S.info,
            battery: { ...S.battery },
            keyCount: 87,
            tft: { width: TFT_W, height: TFT_H, maxFrames: TFT_MAX_FRAMES },
            caps: { ledMaxFrames: 0, maxProfile: 0, music: true, wireless: true },
            frameVersion: 0,
            gameMode: { raw: this._gameModeRaw(fields), fields },
          };
        },
      },
      {
        method: 'GET', path: '/api/device/game-mode', handler: async () => {
          const fields = { sleepTime: S.sleepTime, displayTime: 0, debounceTime: 8, reportRate: 1000, gameMode: 0, tftDisplayTime: 0, keyDelay: 3, powerMode: 1 };
          return { raw: this._gameModeRaw(fields), fields };
        },
      },
      {
        method: 'PUT', path: '/api/device/game-mode', handler: async (body) => {
          const f = body.fields || body || {};
          if (typeof f.sleepTime === 'number' && SLEEP_TIMES.includes(f.sleepTime)) S.sleepTime = f.sleepTime;
          this._save();
          return { ok: true, fields: f };
        },
      },
      {
        method: 'POST', path: '/api/device/time-sync', handler: async () => {
          await this._later(90);
          const d = new Date();
          const frame = [0x5a, 0x01, 0x5a, d.getFullYear() % 100, d.getMonth() + 1, d.getDate(),
            d.getHours(), d.getMinutes(), d.getSeconds(), 0];
          return { ok: true, sent: frame, time: d.toISOString() };
        },
      },
      {
        method: 'POST', path: '/api/device/factory-reset', handler: async (body) => {
          if (body.confirm !== true) throw MockServer.fail('恢复出厂需要 confirm:true', 'confirm_required');
          await this._later(700);
          this._resetState();
          return { ok: true };
        },
      },
      {
        method: 'POST', path: '/api/device/raw', handler: async (body) => {
          const data = (body.data || []).map((x) => Number(x) & 0xff);
          if (!data.length) throw MockServer.fail('data 不能为空', 'bad_request');
          await this._later(40);
          const cmd = data[1] ?? 0;
          const recv = [0x55, cmd, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00];
          while (recv.length < 40) recv.push(0);
          const entry = { ts: Date.now(), sent: data, received: recv };
          S.rawLog.unshift(entry);
          if (S.rawLog.length > 50) S.rawLog.pop();
          const hex = recv.map((b) => b.toString(16).toUpperCase().padStart(2, '0')).join(' ');
          return { cmd, response: hex, length: recv.length };
        },
      },

      /* ---------------- 改键 ---------------- */
      {
        method: 'GET', path: '/api/keymap/layout', handler: () => ({
          keys: KEY_LAYOUT.rows.flat().map((k) => ({
            slot: k.slot, row: k.row, x: k.x, w: k.w, name: k.name, label: k.name, keyCode: k.keyCode,
          })),
          meta: {
            unit: KEY_LAYOUT.unit, rowWidth: KEY_LAYOUT.rowWidth, rowPitch: KEY_LAYOUT.rowPitch,
            keySize: KEY_LAYOUT.keySize, rows: KEY_LAYOUT.rows.length,
            noLedSlots: KEY_LAYOUT.notes.noLed, dimLedSlots: KEY_LAYOUT.notes.dimLed,
            emptySlots: [13, 14, 15, 29, 30, 31, 45, 46, 47, 61, 62, 63, 77, 78, 79, 93, 94, 95, 96, 97, 98, 101],
          },
        }),
      },
      { method: 'GET', path: '/api/keymap', handler: () => ({ normal: S.keymap.normal, fn: S.keymap.fn, fnReliable: true }) },
      {
        method: 'PUT', path: '/api/keymap/normal', handler: async (body) => {
          const slots = body.slots || {};
          Object.assign(S.keymap.normal, slots);
          this._save();
          this._mkdir(120, () => this._toast('success', `主层已写入 ${Object.keys(slots).length} 个按键（mock）`));
          return { ok: true, changed: Object.keys(slots).length };
        },
      },
      {
        method: 'PUT', path: '/api/keymap/fn', handler: async (body) => {
          const slots = body.slots || {};
          Object.assign(S.keymap.fn, slots);
          this._save();
          return { ok: true, changed: Object.keys(slots).length };
        },
      },
      {
        method: 'GET', path: '/api/keymap/defaults', handler: async () => {
          await this._later(150);
          return { normal: { ...DEFAULT_KEYMAP.normal }, fn: { ...DEFAULT_KEYMAP.fn } };
        },
      },
      {
        method: 'POST', path: '/api/keymap/restore', handler: async (body) => {
          const layer = body.layer === 'fn' ? 'fn' : 'normal';
          await this._later(400);
          S.keymap[layer] = { ...DEFAULT_KEYMAP[layer] };
          this._save();
          return { ok: true, layer };
        },
      },
      {
        method: 'GET', path: '/api/keymap/actions', handler: () => ({
          keyboard: ACTIONS.keyboard,
          consumer: ACTIONS.consumer,
          mouse: ACTIONS.mouse,
          func: ACTIONS.func,
          macros: S.macros.filter((x) => x.actions.length).map((x) => ({ slot: x.slot, offset: 400 + macroBytes(x.actions) })),
          macroCapacity: MACRO_CAPACITY,
          notes: ['MK87 frameVersion=0：只用 FUNC(13)，不展示 FUNC_V2', '禁用键 = 02 00 6F 00（真机未验证）'],
          pageTypes: ACTIONS.pageTypes,
        }),
      },

      /* ---------------- 灯效 ---------------- */
      {
        method: 'GET', path: '/api/lighting', handler: () => ({
          ...S.lighting,
          raw: Array.from({ length: 16 }, (_, i) => [0xff, 0xff, 0xff][i] ?? 0),
        }),
      },
      {
        method: 'PUT', path: '/api/lighting', handler: async (body) => {
          const b = body || {};
          if (b.mode !== undefined) S.lighting.mode = Number(b.mode) | 0;
          if (b.brightness !== undefined) S.lighting.brightness = clamp(Number(b.brightness), 1, 6);
          if (b.speed !== undefined) S.lighting.speed = clamp(Number(b.speed), 1, 6);
          if (b.direction !== undefined) S.lighting.direction = clamp(Number(b.direction), 0, 3);
          if (b.colorMode !== undefined) S.lighting.colorMode = Number(b.colorMode) ? 1 : 0;
          if (b.color) S.lighting.color = { r: clamp(Number(b.color.r) | 0, 0, 255), g: clamp(Number(b.color.g) | 0, 0, 255), b: clamp(Number(b.color.b) | 0, 0, 255) };
          this._save();
          await this._later(30);
          return { ok: true, lighting: S.lighting };
        },
      },
      {
        method: 'GET', path: '/api/lighting/modes', handler: () => LIGHTING_MODES,
      },
      {
        method: 'GET', path: '/api/lighting/custom', handler: () => ({ colors: S.custom.colors, count: Object.keys(S.custom.colors).length }),
      },
      {
        method: 'PUT', path: '/api/lighting/custom', handler: async (body) => {
          const colors = body.colors || {};
          S.custom.colors = { ...S.custom.colors, ...colors };
          if (body.apply !== false) S.lighting.mode = 128;
          this._save();
          await this._later(160);
          return { ok: true, count: Object.keys(S.custom.colors).length };
        },
      },
      {
        method: 'POST', path: '/api/lighting/frames/start', handler: async (body) => {
          S.frames = { running: true, fps: Number(body.fps) || 20, frames: 0 };
          return { ok: true, running: true, fps: S.frames.fps };
        },
      },
      {
        method: 'POST', path: '/api/lighting/frames/push', handler: async (body) => {
          const keys = body.keys || {};
          const n = Object.keys(keys).length;
          await this._later(Math.max(14, 1000 / (S.frames.fps || 20)));
          S.frames.frames++;
          return { ok: true, keys: n };
        },
      },
      {
        method: 'POST', path: '/api/lighting/frames/stop', handler: async () => {
          S.frames.running = false;
          return { ok: true };
        },
      },
      { method: 'GET', path: '/api/lighting/frames/status', handler: () => S.frames },

      /* ---------------- 宏 ---------------- */
      {
        method: 'GET', path: '/api/macros', handler: () => {
          const used = S.macros.reduce((sum, m) => sum + macroBytes(m.actions), 0);
          return { capacity: MACRO_CAPACITY, used, slots: S.macros };
        },
      },
      {
        method: 'PUT', path: '/api/macros', handler: async (body) => {
          const slots = body.slots || [];
          const used = slots.reduce((sum, m) => sum + macroBytes(m.actions), 0);
          if (used > MACRO_CAPACITY) throw MockServer.fail(`宏空间不足：需要 ${used}B，上限 ${MACRO_CAPACITY}B`, 'macro_full');
          await this._later(320);
          S.macros = Array.from({ length: MACRO_SLOT_COUNT }, (_, i) => {
            const found = slots.find((x) => Number(x.slot) === i);
            return { slot: i, actions: found ? structuredClone(found.actions || []) : [] };
          });
          this._save();
          return { ok: true, used, capacity: MACRO_CAPACITY };
        },
      },
      {
        method: 'DELETE', path: /^\/api\/macros\/(\d+)$/, handler: async (body, mm) => {
          const slot = Number(mm[1]);
          const found = S.macros.find((x) => x.slot === slot);
          if (found) found.actions = [];
          this._save();
          return { ok: true, slot };
        },
      },

      /* ---------------- 屏幕 TFT ---------------- */
      {
        method: 'GET', path: '/api/tft', handler: () => ({
          width: TFT_W, height: TFT_H, maxFrames: TFT_MAX_FRAMES,
          pixelFormat: 'rgb565', byteOrder: 0, frameBytes: TFT_FRAME_BYTES,
          fitModes: ['cover', 'contain', 'stretch'],
          temporalModes: ['uniform', 'adaptive'],
          resampleModes: ['lanczos', 'bicubic', 'bilinear', 'area'],
          secondsPerPacket: 0.146,
          supported: true,
        }),
      },
      {
        method: 'POST', path: '/api/tft/convert', handler: async (body) => {
          await this._later(120);
          return this._convertTft(body);
        },
      },
      {
        method: 'POST', path: '/api/tft/upload_file', handler: async (body) => {
          await this._later(120);
          const result = await this._convertTft(body);
          this._startJob('tft', 'upload', result.stats.packets, { mode: 'file', fps: Number(body?.options?.fps) || 10, frames: result.framesCount });
          return { job: 'tft', frames: result.framesCount, packets: result.stats.packets, stats: result.stats };
        },
      },
      {
        method: 'POST', path: '/api/tft/upload', handler: async (body) => {
          const frames = body.frames || [];
          const mode = body.mode === 'animation' ? 'animation' : 'static';
          if (!frames.length) throw MockServer.fail('frames 不能为空', 'bad_request');
          if (frames.length > TFT_MAX_FRAMES) throw MockServer.fail(`最多 ${TFT_MAX_FRAMES} 帧`, 'frame_limit');
          for (const f of frames.slice(0, 3)) {
            if (typeof f !== 'string' || f.length < 100) throw MockServer.fail('帧数据不是合法 base64', 'bad_frame');
          }
          this._startJob('tft', 'upload', frames.length, { mode, fps: Number(body.fps) || 10 });
          return { job: 'tft', total: frames.length, mode };
        },
      },
      {
        method: 'POST', path: '/api/tft/default', handler: async () => {
          this._startJob('tft', 'upload', 135, { mode: 'animation', fps: 10, default: true });
          return { job: 'tft', total: 135, mode: 'default' };
        },
      },
      { method: 'GET', path: '/api/tft/job', handler: () => this._jobSnapshot() },
      {
        method: 'POST', path: '/api/tft/cancel', handler: async () => {
          this._stopJob(true);
          return { ok: true };
        },
      },

      /* ---------------- 音乐律动 ---------------- */
      {
        method: 'GET', path: '/api/music/devices', handler: async () => {
          await this._later(120);
          return [
            { id: 'default', name: '系统默认输出', description: '跟随系统主输出设备（loopback）', active: true },
            { id: 'speaker-realtek', name: '扬声器 (Realtek High Definition Audio)', description: '笔记本内置扬声器', active: false },
            { id: 'headphone', name: '耳机 (USB Audio Device)', description: '3.5mm / USB 耳机输出', active: false },
            { id: 'hdmi', name: '数字输出 (HDMI)', description: '显示器 HDMI 音频', active: false },
          ];
        },
      },
      {
        method: 'POST', path: '/api/music/start', handler: async (body) => {
          if (S.transport !== 'usb') throw MockServer.fail('音乐律动仅支持 USB 有线连接（2.4G 不支持）', 'usb_only');
          if (!S.music.running) this._startMusic(body);
          return {
            ok: true, running: true, mode: S.music.mode, requestedMode: S.music.requestedMode,
            color: S.music.color, fps: S.music.running ? (S.music.official ? S.music.measuredFps : S.music.fps) : null,
            targetFps: S.music.official ? (S.music.nativeFps || OFFICIAL_DEFAULT_FRAME_RATE) : (S.music.fps || 20),
          };
        },
      },
      {
        method: 'POST', path: '/api/music/stop', handler: async () => {
          if (S.music.running) this._stopMusic();
          return { ok: true, running: false };
        },
      },
      {
        method: 'GET', path: '/api/music/status', handler: () => ({
          running: S.music.running, mode: S.music.mode, requestedMode: S.music.requestedMode,
          modes: MUSIC_MODES,
          /* 运行健康状态（与真实后端契约一致：自动恢复 / 保后台 / 设备在线 / 音频回退） */
          health: S.music.running ? 'ok' : 'stopped',
          recoveries: 0,
          lastRecovery: null,
          frameAgeMs: S.music.running ? 50 : null,
          keepAwake: S.music.running,
          deviceConnected: true,
          lastError: '',
          audioFallback: false,
          fps: S.music.running ? (S.music.official ? S.music.measuredFps : S.music.fps) : null,
          targetFps: S.music.official ? (S.music.nativeFps || OFFICIAL_DEFAULT_FRAME_RATE) : (S.music.fps || 20),
          color: S.music.color || 'default',
          level: S.music.level, device: S.music.deviceId,
          amplitude: S.music.amplitude, backmode: S.music.backmode,
          backmodeBrightness: S.music.backmodeBrightness,
          implementedModes: MUSIC_IMPLEMENTED,
          officialModes: MUSIC_OFFICIAL_MODES,
          officialImplementedModes: MUSIC_OFFICIAL_IMPLEMENTED,
          colors: S.music.colors || {},
        }),
      },
      {
        method: 'POST', path: '/api/music/update', handler: async (body) => {
          const m = S.music;
          if (!m.running) throw MockServer.fail('音乐律动未在运行，无法热更新参数', 'not_running');
          if (body.mode !== undefined) {
            const req = Number(body.mode) || 13;
            m.requestedMode = req;
            m.mode = MUSIC_IMPLEMENTED.includes(req) ? req : 13;
          }
          if (body.backmode !== undefined) m.backmode = Number(body.backmode) || 0;
          if (body.backmodeBrightness !== undefined) m.backmodeBrightness = Number(body.backmodeBrightness) || 100;
          if (body.amplitude !== undefined) m.amplitude = Number(body.amplitude) || 50;
          if (body.fps !== undefined) {
            const n = Number(body.fps);
            m.fps = n || 20;
            if (OFFICIAL_FRAME_RATES.includes(n)) m.nativeFps = n;
          }
          /* 前端只在官方方案带 color；当前方案零改动（不带 color） */
          if (body.color !== undefined) {
            m.color = String(body.color) || 'default';
            m.official = true;
          } else {
            m.official = false;
          }
          m.measuredFps = musicMeasuredFps(m);
          return {
            ok: true, running: true, mode: m.mode, requestedMode: m.requestedMode,
            backmode: m.backmode, backmodeBrightness: m.backmodeBrightness,
            amplitude: m.amplitude, color: m.color,
            fps: m.official ? m.measuredFps : m.fps,
            targetFps: m.official ? (m.nativeFps || OFFICIAL_DEFAULT_FRAME_RATE) : (m.fps || 20),
            implementedModes: MUSIC_IMPLEMENTED,
            officialModes: MUSIC_OFFICIAL_MODES,
            officialImplementedModes: MUSIC_OFFICIAL_IMPLEMENTED,
          };
        },
      },

      /* ---------------- 无线 ---------------- */
      {
        method: 'GET', path: '/api/wireless', handler: async () => {
          await this._later(100);
          const demo = S.transport !== '2.4g';
          return {
            transport: '2.4g',
            connected: S.connected,
            sleepTime: S.sleepTime,
            identity: { manufacturer: 1, product: 18, workMode: 2, productName: '2.4G Dongle', vid: 3141, pid: 65278 },
            battery: { ...S.battery },
            notifications: S.notifications.slice(-20),
            demo,
          };
        },
      },
      {
        method: 'PUT', path: '/api/wireless', handler: async (body) => {
          const t = Number(body.sleepTime);
          if (!SLEEP_TIMES.includes(t)) throw MockServer.fail('休眠时间只支持 0/1/10/20/30 分钟', 'bad_value');
          S.sleepTime = t;
          this._save();
          this._pushNotification('config');
          return { ok: true, sleepTime: t };
        },
      },

      /* ---------------- 按键测试 ---------------- */
      {
        method: 'POST', path: '/api/keytest/start', handler: async () => {
          S.keytest.running = true;
          return { ok: true, running: true, backend: 'rawinput' };
        },
      },
      {
        method: 'POST', path: '/api/keytest/stop', handler: async () => {
          S.keytest.running = false;
          return { ok: true, running: false };
        },
      },
      {
        method: 'GET', path: '/api/keytest/status', handler: () => ({
          running: S.keytest.running, backend: 'rawinput', events: S.keytest.events.slice(-50),
          supported: true,
        }),
      },

      /* ---------------- 备份 / 设置 ---------------- */
      {
        method: 'GET', path: '/api/backup', handler: async () => {
          await this._later(150);
          return {
            version: 1,
            app: 'MK87 Studio',
            createdAt: new Date().toISOString(),
            device: { ...S.info },
            keymap: structuredClone(S.keymap),
            macro: {
              capacity: MACRO_CAPACITY,
              used: S.macros.reduce((sum, m) => sum + macroBytes(m.actions), 0),
              slots: structuredClone(S.macros),
            },
            lighting: structuredClone(S.lighting),
            custom: structuredClone(S.custom),
            wireless: { sleepTime: S.sleepTime },
            settings: structuredClone(S.settings),
          };
        },
      },
      {
        method: 'POST', path: '/api/backup/restore', handler: async (body) => {
          if (body.confirm !== true) throw MockServer.fail('恢复备份需要 confirm:true', 'confirm_required');
          const b = body.backup;
          if (!b || typeof b !== 'object') throw MockServer.fail('备份内容无效', 'bad_backup');
          await this._later(500);
          if (b.keymap?.normal) S.keymap.normal = { ...b.keymap.normal };
          if (b.keymap?.fn) S.keymap.fn = { ...b.keymap.fn };
          if (Array.isArray(b.macro?.slots)) {
            S.macros = Array.from({ length: MACRO_SLOT_COUNT }, (_, i) => {
              const found = b.macro.slots.find((x) => Number(x.slot) === i);
              return { slot: i, actions: found ? structuredClone(found.actions || []) : [] };
            });
          }
          if (b.lighting) S.lighting = { ...S.lighting, ...b.lighting };
          if (b.custom?.colors) S.custom.colors = { ...b.custom.colors };
          if (typeof b.wireless?.sleepTime === 'number') S.sleepTime = b.wireless.sleepTime;
          this._save();
          this._emit('status', this.status());
          return { ok: true, restoredAt: new Date().toISOString() };
        },
      },
      {
        method: 'GET', path: '/api/autostart', handler: async () => {
          await this._later(120);
          return {
            supported: true,
            enabled: !!S.autostart,
            command: 'C:\\Program Files\\MK87 Studio\\MK87Studio.exe --autostart',
            location: 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\MK87Studio',
            platform: 'windows',
            shell: false,
          };
        },
      },
      {
        method: 'PUT', path: '/api/autostart', handler: async (body) => {
          await this._later(200);
          S.autostart = !!body.enabled;
          this._save();
          return {
            supported: true,
            enabled: !!S.autostart,
            command: 'C:\\Program Files\\MK87 Studio\\MK87Studio.exe --autostart',
            location: 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\MK87Studio',
            platform: 'windows',
            shell: false,
          };
        },
      },
      {
        method: 'GET', path: '/api/tray/status', handler: async () => {
          await this._later(80);
          return {
            platform: 'windows',
            shellMode: !!this.simulateShell,
            tray: { available: true, backend: 'pystray', error: null },
            desktop: { currentDesktop: '', family: 'windows', sessionType: '', isWayland: false },
            os: { id: 'windows', name: 'Windows', version: '' },
            gnome: { detected: false, shellVersion: null },
            extension: {
              uuid: 'appindicatorsupport@rgcjonas.gmail.com',
              installed: null, enabled: null, systemWide: false, paths: [],
            },
            install: {
              supported: false,
              reason: 'unsupported-platform',
              reasonText: {
                zh: '当前平台没有系统托盘支持。',
                en: 'System tray is not supported on this platform.',
              },
              manager: null, package: 'gnome-shell-extension-appindicator',
              command: [], commandText: '', needsRoot: false, elevatedVia: null,
              rebootRequired: false, needsEnable: false, manualCommands: [],
            },
            advice: {
              code: 'windows-ok',
              zh: 'Windows 使用系统通知区域（pystray 后端），托盘与右键菜单始终可用，无需额外组件。',
              en: 'Windows uses the native notification area (pystray backend); the tray icon and right-click menu are always available and need no extra component.',
            },
          };
        },
      },
      {
        method: 'POST', path: '/api/tray/install-extension', handler: async () => {
          await this._later(240);
          return {
            ok: false,
            message: '演示模式（mock）无法安装系统扩展',
            output: 'mock: package manager not available',
            needsLogout: false, needsReload: false, rebootRequired: false,
            manualCommands: [],
          };
        },
      },
      {
        method: 'POST', path: '/api/tray/enable-extension', handler: async () => {
          await this._later(180);
          return {
            ok: false,
            message: '演示模式（mock）无法修改扩展状态',
            output: 'mock: gsettings not available',
            manualCommands: [],
          };
        },
      },
      {
        method: 'POST', path: '/api/quit', handler: async () => {
          await this._later(160);
          if (this.simulateShell) return { ok: true };
          return { ok: false, message: '浏览器模式（mock）没有可退出的原生程序，请直接关闭服务进程' };
        },
      },
      { method: 'GET', path: '/api/settings', handler: () => ({ ...S.settings }) },
      {
        method: 'PUT', path: '/api/settings', handler: async (body) => {
          if (body.theme !== undefined) S.settings.theme = body.theme;
          if (body.language !== undefined) S.settings.language = body.language;
          this._save();
          return { ok: true, settings: { ...S.settings } };
        },
      },
    ];
  }

  /* ------------------------------------------------------------ TFT convert（模拟后端压缩管线） */
  static _sniffImageType(bytes) {
    if (bytes.length > 8 && bytes[0] === 0x89 && bytes[1] === 0x50) return 'image/png';
    if (bytes.length > 3 && bytes[0] === 0xff && bytes[1] === 0xd8) return 'image/jpeg';
    if (bytes.length > 6 && bytes[0] === 0x47 && bytes[1] === 0x49) return 'image/gif';
    if (bytes.length > 12 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[8] === 0x57) return 'image/webp';
    return 'image/png';
  }

  async _decodeSourceFrames(base64, filename) {
    const bin = atob(base64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const type = MockServer._sniffImageType(bytes);
    const isLikelyAnim = /gif|webp|apng/i.test(type + (filename || ''));
    let sourceFrames = 1;
    let provider = null;
    if (typeof ImageDecoder === 'function' && isLikelyAnim) {
      try {
        const decoder = new ImageDecoder({ data: bytes.buffer, type });
        await decoder.completed;
        const track = decoder.tracks.selectedTrack;
        sourceFrames = track?.frameCount || 1;
        provider = async (index) => {
          const { image } = await decoder.decode({ frameIndex: Math.min(index, sourceFrames - 1) });
          return image;
        };
      } catch (e) {
        console.warn('[mock] ImageDecoder 失败，按静态图处理', e);
        provider = null;
      }
    }
    if (!provider) {
      const bitmap = await createImageBitmap(new Blob([bytes], { type }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      canvas.getContext('2d').drawImage(bitmap, 0, 0);
      bitmap.close?.();
      provider = async () => canvas;
      sourceFrames = 1;
    }
    return { provider, sourceFrames };
  }

  _drawFit(ctx, src, sw, sh, fit) {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, TFT_W, TFT_H);
    let dw;
    let dh;
    if (fit === 'stretch') {
      dw = TFT_W; dh = TFT_H;
    } else {
      const scale = fit === 'cover' ? Math.max(TFT_W / sw, TFT_H / sh) : Math.min(TFT_W / sw, TFT_H / sh);
      dw = sw * scale; dh = sh * scale;
    }
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(src, (TFT_W - dw) / 2, (TFT_H - dh) / 2, dw, dh);
  }

  async _convertTft(body) {
    const { data, filename, options = {} } = body || {};
    if (!data) throw MockServer.fail('data 不能为空', 'bad_request');
    const { provider, sourceFrames: rawSourceFrames } = await this._decodeSourceFrames(data, filename);
    const fps = Math.min(60, Math.max(0.5, Number(options.fps) || 10));
    /* 源帧区间裁剪（1 起始，含首尾；非法区间返回 400） */
    let trimStart = Number(options.trimStartFrame) || 1;
    let trimEnd = Number(options.trimEndFrame) || rawSourceFrames;
    if (trimStart < 1 || trimEnd < trimStart || trimEnd > rawSourceFrames) {
      throw MockServer.fail(`帧区间非法：${trimStart}..${trimEnd}（源共 ${rawSourceFrames} 帧）`, 'bad_trim');
    }
    trimStart = Math.round(trimStart);
    trimEnd = Math.round(trimEnd);
    const trimmedFrames = trimEnd - trimStart + 1;
    let requested = Number(options.frameCount) || 0;
    if (!requested) requested = trimmedFrames;
    const warnings = [];
    if (requested > TFT_MAX_FRAMES) {
      warnings.push(`目标帧数 ${requested} 超过设备上限 ${TFT_MAX_FRAMES}，已按 ${TFT_MAX_FRAMES} 帧压缩`);
    }
    const maxOut = Math.max(1, Math.min(TFT_MAX_FRAMES, Math.round(requested)));
    const indices = [];
    for (let i = 0; i < maxOut; i++) {
      const rel = maxOut === 1 ? 0 : Math.round((i * (trimmedFrames - 1)) / (maxOut - 1));
      indices.push(trimStart - 1 + rel);
    }
    const dedupe = options.dedupe !== false;
    const unique = [];
    for (const idx of indices) {
      if (dedupe && unique.length && unique[unique.length - 1] === idx) continue;
      unique.push(idx);
    }
    const outFrames = [];
    const canvas = document.createElement('canvas');
    canvas.width = TFT_W;
    canvas.height = TFT_H;
    const ctx = canvas.getContext('2d');
    for (const idx of unique) {
      const image = await provider(idx);
      this._drawFit(ctx, image, image.displayWidth || image.width, image.displayHeight || image.height, options.fit || 'contain');
      image.close?.();
      outFrames.push(canvas.toDataURL('image/png'));
    }
    const framesCount = outFrames.length;
    const delaysMs = new Array(framesCount).fill(Math.round(1000 / fps));
    const packets = Math.ceil((256 + framesCount * TFT_FRAME_BYTES) / 4096);
    const outputBytes = framesCount * TFT_FRAME_BYTES;
    const sourceBytes = Math.ceil((data.length * 3) / 4);
    return {
      frames: outFrames,
      framesCount,
      displayFrames: framesCount,
      sourceFrames: rawSourceFrames,
      rawSourceFrames,
      requestedFrames: requested,
      sourceDurationMs: rawSourceFrames * 100,
      trim: { startFrame: trimStart, endFrame: trimEnd, frames: trimmedFrames, trimmed: trimmedFrames !== rawSourceFrames },
      warnings,
      delaysMs,
      delaysCs: delaysMs.map((ms) => Math.round(ms / 10)),
      paddedLastFrame: true,
      clampedDelays: [],
      fit: options.fit || 'contain',
      temporal: options.temporal || 'uniform',
      dither: !!options.dither,
      dedupe,
      stats: {
        sourceBytes,
        outputBytes,
        packets,
        estimatedSeconds: Math.round(packets * 146) / 1000,
        frameReduction: trimmedFrames ? Math.max(0, 1 - framesCount / trimmedFrames) : 0,
        sizeRatio: sourceBytes ? outputBytes / sourceBytes : 0,
      },
      mode: options.dither ? 'dither' : 'plain',
      resample: options.resample || 'lanczos',
    };
  }

  /* ------------------------------------------------------------ job simulation */
  _jobSnapshot() {
    const j = this.state.tftJob;
    if (!j) return { running: false, phase: 'done', sent: 0, total: 0, pct: 0, error: null };
    return {
      running: j.running, phase: j.phase, sent: j.sent, total: j.total,
      pct: j.total ? Math.round((j.sent / j.total) * 100) : 0, error: j.error || null,
      mode: j.meta?.mode, fps: j.meta?.fps,
    };
  }

  _startJob(job, phase, total, meta) {
    this._stopJob(false);
    const j = { running: true, phase, sent: 0, total, meta, error: null, timer: null };
    this.state.tftJob = j;
    this._emit('job', { job, state: 'running' });
    const step = Math.max(24, Math.round(600 / Math.max(1, Math.min(total, 40))));
    j.timer = setInterval(() => {
      if (!j.running) return;
      j.sent = Math.min(total, j.sent + Math.max(1, Math.round(total / 45)));
      const pct = Math.round((j.sent / total) * 100);
      this._emit('progress', { job, phase: 'upload', sent: j.sent, total, pct });
      if (j.sent >= total) {
        j.running = false;
        j.phase = 'done';
        clearInterval(j.timer);
        this._emit('progress', { job, phase: 'upload', sent: total, total, pct: 100 });
        this._emit('job', { job, state: 'done', error: null });
        this._emit('toast', { level: 'success', message: meta?.default ? '官方默认动画已恢复（mock）' : `已上传 ${total} 帧到屏幕（mock）` });
      }
    }, step);
    this.timers.add(j.timer);
  }

  _stopJob(cancelled = false) {
    const j = this.state.tftJob;
    if (!j) return;
    if (j.timer) clearInterval(j.timer);
    j.running = false;
    if (cancelled) {
      j.phase = 'error';
      j.error = 'cancelled';
      this._emit('job', { job: 'tft', state: 'error', error: 'cancelled' });
    }
  }

  /* ------------------------------------------------------------ music simulation */
  _startMusic(body) {
    const m = this.state.music;
    m.running = true;
    m.deviceId = body.deviceId || 'default';
    m.sensitivity = Number(body.sensitivity) || 1.0;
    m.style = body.style === 'pulse' ? 'pulse' : 'spectrum';
    m.fps = Number(body.fps) || 20;
    /* 前端只在官方方案带 color；当前方案零改动（不带 color） */
    m.official = body.color !== undefined;
    m.color = m.official ? (String(body.color) || 'default') : 'default';
    if (OFFICIAL_FRAME_RATES.includes(Number(body.fps))) m.nativeFps = Number(body.fps);
    else if (!m.nativeFps) m.nativeFps = OFFICIAL_DEFAULT_FRAME_RATE;
    m.measuredFps = musicMeasuredFps(m);
    m.requestedMode = Number(body.mode) || 13;
    m.mode = MUSIC_IMPLEMENTED.includes(m.requestedMode) ? m.requestedMode : 13;
    m.backmode = Number(body.backmode) || 0;
    m.backmodeBrightness = Number(body.backmodeBrightness) || 100;
    m.amplitude = Number(body.amplitude) || Math.round((Number(body.sensitivity) || 1) * 50);
    m.colors = {};
    m.frame = 0;
    m.phase = 0;
    m.levels = new Array(32).fill(0);
    const target = new Array(32).fill(0);
    m.timer = setInterval(() => {
      m.phase += 0.22;
      let sum = 0;
      for (let i = 0; i < 32; i++) {
        let t = 0;
        if (m.style === 'spectrum') {
          t = (Math.sin(m.phase * (0.6 + i * 0.045) + i * 0.55) * 0.5 + 0.5) *
              (0.55 + 0.45 * Math.sin(m.phase * 0.8 + i * 0.18)) * (1.05 - i / 40);
        } else {
          t = (Math.sin(m.phase * 1.3 + i * 0.32) * 0.5 + 0.5) * (0.9 - i / 42);
        }
        t = Math.max(0, Math.min(1, t * (0.65 + m.sensitivity * 0.45)));
        target[i] = t;
        m.levels[i] += (target[i] - m.levels[i]) * 0.55;
        sum += m.levels[i];
      }
      m.level = Math.round((sum / 32) * 1000) / 1000;
      this._emit('music_level', { level: m.level, bands: m.levels.map((v) => Math.round(v * 1000) / 1000) });
      m.frame = (m.frame || 0) + 1;
      m.colors = musicMockColors(m.mode, m.phase, m.level, m.levels, m.color);
      this._emit('music_frame', {
        mode: m.mode, fps: m.official ? (m.measuredFps || m.fps) : m.fps,
        frame: m.frame, colors: m.colors,
      });
    }, Math.round(1000 / m.fps));
    this.timers.add(m.timer);
  }

  _stopMusic() {
    const m = this.state.music;
    if (m.timer) clearInterval(m.timer);
    m.timer = null;
    m.running = false;
    m.level = 0;
    m.measuredFps = null;
    m.colors = {};
    m.frame = 0;
    m.levels = new Array(32).fill(0);
  }

  /* ------------------------------------------------------------ reset / cleanup */
  _gameModeRaw(fields) {
    const raw = new Array(56).fill(0);
    raw[0] = 0x01;
    raw[1] = fields.sleepTime ?? 0;
    raw[2] = fields.displayTime ?? 0;
    raw[3] = fields.debounceTime ?? 0;
    raw[4] = 0xe8;
    raw[5] = 0x03;
    raw[6] = fields.gameMode ?? 0;
    raw[7] = fields.tftDisplayTime ?? 0;
    for (let i = 8; i < 56; i++) raw[i] = 0xff;
    return raw;
  }

  _resetState() {
    this.state.lighting = { ...DEFAULT_LIGHTING };
    this.state.custom = { colors: defaultCustomColors() };
    this.state.keymap = { normal: { ...DEFAULT_KEYMAP.normal }, fn: { ...DEFAULT_KEYMAP.fn } };
    this.state.macros = defaultMacros();
    this.state.sleepTime = 10;
    this._save();
    this._emit('status', this.status());
    this._emit('toast', { level: 'success', message: '设备已恢复出厂设置（mock）' });
  }

  dispose() {
    for (const t of this.timers) clearInterval(t);
    this.timers.clear();
    if (this.state.music.timer) clearInterval(this.state.music.timer);
    if (this.state.tftJob?.timer) clearInterval(this.state.tftJob.timer);
  }
}
