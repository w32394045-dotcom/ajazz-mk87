/* util.js — 无依赖工具函数（DOM / 格式化 / 存储 / 映射） */
import { KEY_LAYOUT } from './data/keyboard.js';

/* ---------------------------------------------------------------- DOM helpers */
/** 轻量 hyperscript：h('div', {class:'x', onclick:fn}, '文本', childNode) */
export function h(tag, props, ...children) {
  const node = document.createElement(tag);
  if (props && typeof props === 'object' && !(props instanceof Node) && !Array.isArray(props)) {
    for (const [k, v] of Object.entries(props)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class' || k === 'className') node.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
      else if (k === 'html') node.innerHTML = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'selected' || k === 'multiple') node[k] = v;
      else node.setAttribute(k, v === true ? '' : v);
    }
  } else if (props) {
    children.unshift(props);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

/** 从 HTML 字符串创建元素（返回第一个元素节点） */
export function el(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

/** 转义 HTML，避免把用户输入当标签 */
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function $(sel, root = document) { return root.querySelector(sel); }
export function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

/* ---------------------------------------------------------------- numbers / format */
export const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
export const pad2 = (n) => String(n).padStart(2, '0');
export const hex2 = (n) => n.toString(16).toUpperCase().padStart(2, '0');
export const hex4 = (n) => n.toString(16).toUpperCase().padStart(4, '0');

export function fmtBytes(n) {
  if (n === null || n === undefined) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 2 : 1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function fmtClock(ts) {
  const d = new Date(ts);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}
export function fmtDateTime(ts) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}
export function timeAgo(ts) {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return '刚刚';
  if (s < 60) return `${s} 秒前`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分钟前`;
  const hh = Math.floor(m / 60);
  if (hh < 24) return `${hh} 小时前`;
  return `${Math.floor(hh / 24)} 天前`;
}

export const rgbCss = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
export const rgbToHex = (c) => '#' + c.map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('').toUpperCase();
export function hexToRgb(hex) {
  let s = String(hex).replace('#', '').trim();
  if (s.length === 3) s = s.split('').map((x) => x + x).join('');
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}
export const clampByte = (v) => clamp(Math.round(Number(v) || 0), 0, 255);

/* ---------------------------------------------------------------- events / timers */
export function debounce(fn, wait = 200) {
  let t = null;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
  wrapped.cancel = () => clearTimeout(t);
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  return wrapped;
}
export function throttle(fn, wait = 50) {
  let last = 0, timer = null, lastArgs = null;
  return (...args) => {
    lastArgs = args;
    const now = Date.now();
    const remain = wait - (now - last);
    if (remain <= 0) {
      last = now;
      fn(...args);
    } else if (!timer) {
      timer = setTimeout(() => { timer = null; last = Date.now(); fn(...lastArgs); }, remain);
    }
  };
}
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let _uid = 0;
export const uid = (p = 'u') => `${p}${++_uid}`;

/** 极简事件总线 */
export class Emitter {
  constructor() { this._map = new Map(); }
  on(type, fn) {
    if (!this._map.has(type)) this._map.set(type, new Set());
    this._map.get(type).add(fn);
    return () => this.off(type, fn);
  }
  off(type, fn) { this._map.get(type)?.delete(fn); }
  emit(type, payload) {
    for (const fn of this._map.get(type) || []) {
      try { fn(payload); } catch (e) { console.error('[emitter]', type, e); }
    }
  }
  clear() { this._map.clear(); }
}

/* ---------------------------------------------------------------- storage */
export const store = {
  get(key, fallback = null) {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
  },
  remove(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } },
};

/* ---------------------------------------------------------------- file helpers */
export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
export function downloadText(filename, text, mime = 'application/json') {
  downloadBlob(filename, new Blob([text], { type: mime + ';charset=utf-8' }));
}
export function readFileAsArrayBuffer(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(fr.error);
    fr.readAsArrayBuffer(file);
  });
}
export function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(fr.error);
    fr.readAsText(file);
  });
}
export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fallthrough */ }
  try {
    const ta = h('textarea', { style: { position: 'fixed', opacity: '0' } });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    return true;
  } catch { return false; }
}

/* ---------------------------------------------------------------- keyboard mapping
   官方 87 键几何数据里的 DOM code（key）<-> HID usage / 槽位。 */
const codeToUsage = new Map();
const codeToSlot = new Map();
const slotToKey = new Map();
const slotToUsage = new Map();
for (const row of KEY_LAYOUT.rows) {
  for (const k of row) {
    if (k.key && k.key !== '-1') {
      if (!codeToSlot.has(k.key)) codeToSlot.set(k.key, k.slot);
      if (typeof k.keyCode === 'number' && k.keyCode > 0 && !codeToUsage.has(k.key)) codeToUsage.set(k.key, k.keyCode);
    }
    slotToKey.set(k.slot, k);
    if (typeof k.keyCode === 'number') slotToUsage.set(k.slot, k.keyCode);
  }
}
/* 补充不在 87 键物理布局里的常用 DOM code（录制宏 / 按键测试时可能遇到） */
const EXTRA_CODE_USAGE = {
  Numpad0: 98, Numpad1: 89, Numpad2: 90, Numpad3: 91, Numpad4: 92, Numpad5: 93,
  Numpad6: 94, Numpad7: 95, Numpad8: 96, Numpad9: 97, NumpadDecimal: 99,
  NumpadAdd: 87, NumpadSubtract: 86, NumpadMultiply: 85, NumpadDivide: 84,
  NumpadEnter: 88, NumLock: 83,
  F13: 104, F14: 105, F15: 106, F16: 107, F17: 108, F18: 109, F19: 110, F20: 111,
  F21: 112, F22: 113, F23: 114, F24: 115,
  Backquote: 53, Minus: 45, Equal: 46, BracketLeft: 47, BracketRight: 48,
  Backslash: 49, Semicolon: 51, Quote: 52, Comma: 54, Period: 55, Slash: 56,
  IntlBackslash: 100, PrintScreen: 70, ScrollLock: 71, Pause: 72,
  Insert: 73, Home: 74, PageUp: 75, Delete: 76, End: 77, PageDown: 78,
  ArrowUp: 82, ArrowDown: 81, ArrowLeft: 80, ArrowRight: 79,
  ControlLeft: 224, ShiftLeft: 225, AltLeft: 226, MetaLeft: 227,
  ControlRight: 228, ShiftRight: 229, AltRight: 230, MetaRight: 231,
  Tab: 43, CapsLock: 57, Enter: 40, Space: 44, Escape: 41, Backspace: 42,
  ContextMenu: 101,
};
for (const [code, usage] of Object.entries(EXTRA_CODE_USAGE)) {
  if (!codeToUsage.has(code)) codeToUsage.set(code, usage);
}

export function codeToHidUsage(code) { return codeToUsage.get(code) ?? null; }
export function codeToLayoutSlot(code) { return codeToSlot.get(code) ?? null; }
export function slotMeta(slot) { return slotToKey.get(Number(slot)) || null; }
export function slotToHidUsage(slot) { return slotToUsage.get(Number(slot)) ?? null; }

/* 组合键可用的修饰键（HID usage + 简称） */
export const MODIFIERS = [
  { usage: 224, code: 'Ctrl', label: 'LCtrl' },
  { usage: 225, code: 'Shift', label: 'LShift' },
  { usage: 226, code: 'Alt', label: 'LAlt' },
  { usage: 227, code: 'Win', label: 'LGui' },
  { usage: 228, code: 'RCtrl', label: 'RCtrl' },
  { usage: 229, code: 'RShift', label: 'RShift' },
  { usage: 230, code: 'RAlt', label: 'RAlt' },
  { usage: 231, code: 'RGui', label: 'RGui' },
];

/* 把浏览器 KeyboardEvent 转成宏动作使用的中文/可读名字 */
export function keyDisplayName(evOrUsage) {
  let usage;
  if (typeof evOrUsage === 'number') usage = evOrUsage;
  else if (evOrUsage && evOrUsage.keyCode in EXTRA_CODE_USAGE) usage = EXTRA_CODE_USAGE[evOrUsage.keyCode];
  else usage = codeToUsage.get(evOrUsage?.code);
  for (const m of MODIFIERS) if (m.usage === usage) return m.label;
  return usage !== undefined && usage !== null ? `HID ${hex2(usage)}` : '—';
}

/* ---------------------------------------------------------------- misc */
export function nextFrame() {
  return new Promise((r) => requestAnimationFrame(() => r()));
}
export function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
export function lerp(a, b, t) { return a + (b - a) * t; }
export function hsla(h, s, l, a = 1) { return `hsla(${h}, ${s}%, ${l}%, ${a})`; }
export function seededRandom(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

/** 根据当前 CSS 变量取色（用于 canvas / 键盘动画） */
export function cssVar(name, fallback = '') {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
