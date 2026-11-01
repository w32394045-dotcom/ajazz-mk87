/* keyboard.js — 87 键键盘渲染组件
   几何数据来自官方 keyListRaw（1u = 15 单位，行宽 275 单位），绝对定位渲染。
   复用于：灯光预览 / 逐键上色 / 改键（主层 + FN）/ 按键测试 / 音乐律动。
   颜色写入使用行内样式，20fps 逐键动画也不会触发重排。 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { h, clamp } from '../util.js';

const ROW_W = KEY_LAYOUT.rowWidth;
const ROW_PITCH = KEY_LAYOUT.rowPitch;
const KEY_SIZE = KEY_LAYOUT.keySize;
const INSET = 0.55; // 键帽左右内缩（单位）

function splitLegend(name) {
  const n = String(name || '').trim();
  const parts = n.split(/\s+/);
  if (parts.length === 2 && parts[0].length <= 3 && parts[1].length <= 3) {
    return { main: parts[1], sub: parts[0] };
  }
  return { main: n, sub: '' };
}

function luminance([r, g, b]) {
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

export class Keyboard {
  constructor(opts = {}) {
    this.opts = {
      interactive: true,
      legends: true,
      showSlots: false,
      mode: 'layout',            // layout | perkey | lighting | keytest | preview
      onKeyClick: null,
      onKeyHover: null,
      ...opts,
    };
    this.keys = new Map();       // slot -> { node, key, legends }
    this.selected = new Set();
    this.colors = new Map();     // slot -> [r,g,b]
    this.pressed = new Set();
    this.used = new Map();       // slot -> count
    this._build();
  }

  /* ------------------------------------------------------------ build */
  _build() {
    this.kb = h('div', {
      class: `kb ${this.opts.interactive ? 'interactive' : ''}`,
      role: 'group',
      'aria-label': 'MK87 87 键键盘',
    });
    for (const row of KEY_LAYOUT.rows) {
      for (const k of row) {
        const { main, sub } = splitLegend(k.name);
        const legendWrap = h('div', { class: 'kb-legends' });
        const mainEl = h('span', { class: 'kb-legend-main' }, main);
        legendWrap.append(mainEl);
        let subEl = null;
        if (sub) {
          subEl = h('span', { class: 'kb-legend-shift' }, sub);
          legendWrap.append(subEl);
        }
        const slotEl = h('span', { class: 'kb-slot' }, String(k.slot));
        const node = h('button', {
          type: 'button',
          class: 'kb-key',
          'data-slot': String(k.slot),
          'aria-label': `${k.name}（槽位 ${k.slot}）`,
          title: `${k.name} · 槽位 ${k.slot}${k.keyCode ? ` · HID ${k.keyCode}` : ''}${k.led === 0 ? ' · 无可见灯' : ''}`,
          style: {
            left: `calc(var(--ku) * ${(k.x + INSET / 2).toFixed(3)})`,
            top: `calc(var(--ku) * ${(k.row * ROW_PITCH + (ROW_PITCH - KEY_SIZE) / 2).toFixed(3)})`,
            width: `calc(var(--ku) * ${(k.w - INSET).toFixed(3)})`,
            height: `calc(var(--ku) * ${KEY_SIZE})`,
          },
        }, this.opts.legends ? legendWrap : null, slotEl);
        if (k.led === 0) node.classList.add('no-led');
        if (k.led === 2) node.classList.add('dim-led');
        node.addEventListener('click', (e) => {
          e.preventDefault();
          this._onClick(k.slot, e);
        });
        node.addEventListener('pointerenter', () => this.opts.onKeyHover?.(k.slot, k));
        node.addEventListener('pointerleave', () => this.opts.onKeyHover?.(null, null));
        this.kb.append(node);
        this.keys.set(k.slot, { node, key: k, mainEl, subEl, legendWrap });
      }
    }

    this.deck = h('div', { class: `kb-deck kb-mode-${this.opts.mode}` }, this.kb);
    this._ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width;
      if (w) this.kb.style.setProperty('--ku', `${(w / ROW_W).toFixed(4)}px`);
    });
    this._ro.observe(this.kb);
  }

  mount(parent) {
    parent.append(this.deck);
    this.refreshSize();
    return this;
  }

  /** 重新按当前宽度计算 --ku（用于 deck 已手动插入 DOM 的场景） */
  refreshSize() {
    const sync = () => {
      const w = this.kb.getBoundingClientRect().width;
      if (w) this.kb.style.setProperty('--ku', `${(w / ROW_W).toFixed(4)}px`);
    };
    sync();
    requestAnimationFrame(sync);
  }

  destroy() {
    this._ro?.disconnect();
    this.deck.remove();
  }

  _onClick(slot, ev) {
    if (!this.opts.interactive) return;
    this.opts.onKeyClick?.(slot, ev);
  }

  keyNode(slot) { return this.keys.get(Number(slot))?.node || null; }

  /* ------------------------------------------------------------ selection */
  setSelected(slot, on = true) {
    const n = this.keyNode(slot);
    if (!n) return;
    n.classList.toggle('is-selected', !!on);
    if (on) this.selected.add(Number(slot)); else this.selected.delete(Number(slot));
  }
  clearSelected() {
    for (const slot of this.selected) this.keyNode(slot)?.classList.remove('is-selected');
    this.selected.clear();
  }

  /* ------------------------------------------------------------ colors */
  setColor(slot, rgb, { glow = true } = {}) {
    const rec = this.keys.get(Number(slot));
    if (!rec) return;
    const node = rec.node;
    if (!rgb) {
      node.style.background = '';
      node.style.boxShadow = '';
      node.style.color = '';
      node.style.borderColor = '';
      this.colors.delete(Number(slot));
      return;
    }
    const [r, g, b] = rgb;
    this.colors.set(Number(slot), [r, g, b]);
    node.style.background = `linear-gradient(180deg, rgb(${Math.min(255, r + 26)}, ${Math.min(255, g + 26)}, ${Math.min(255, b + 26)}), rgb(${Math.max(0, r - 14)}, ${Math.max(0, g - 14)}, ${Math.max(0, b - 14)}))`;
    node.style.borderColor = `rgba(${r}, ${g}, ${b}, .85)`;
    node.style.color = luminance([r, g, b]) > 0.62 ? 'rgba(8, 12, 20, .82)' : 'rgba(255, 255, 255, .94)';
    node.style.boxShadow = glow
      ? `0 0 ${Math.round(6 + luminance([r, g, b]) * 10)}px rgba(${r}, ${g}, ${b}, var(--kb-glow)), inset 0 1px 0 rgba(255,255,255,.28)`
      : 'inset 0 1px 0 rgba(255,255,255,.2)';
    node.querySelectorAll('.kb-legend-sub, .kb-legend-shift').forEach((el) => { el.style.color = 'currentColor'; el.style.opacity = '.72'; });
  }

  setColors(map) {
    for (const [slot, rgb] of Object.entries(map || {})) this.setColor(Number(slot), rgb);
  }

  clearColors() {
    for (const slot of Array.from(this.colors.keys())) this.setColor(slot, null);
    this.colors.clear();
  }

  /* 一次性刷新（逐键动画每帧调用；只写有变化的键） */
  applyColorFrame(frame) {
    for (const [slot, rgb] of frame) {
      const prev = this.colors.get(slot);
      if (prev && Math.abs(prev[0] - rgb[0]) + Math.abs(prev[1] - rgb[1]) + Math.abs(prev[2] - rgb[2]) < 3) continue;
      this.setColor(slot, rgb);
    }
  }

  /* ------------------------------------------------------------ states */
  setPressed(slot, on = true) {
    const node = this.keyNode(slot);
    if (!node) return;
    node.classList.toggle('is-pressed', !!on);
    if (on) this.pressed.add(Number(slot)); else this.pressed.delete(Number(slot));
  }
  clearPressed() {
    for (const slot of this.pressed) this.keyNode(slot)?.classList.remove('is-pressed');
    this.pressed.clear();
  }

  setUsed(slot, used, count = 0) {
    const rec = this.keys.get(Number(slot));
    if (!rec) return;
    rec.node.classList.toggle('is-used', !!used);
    if (used) this.used.set(Number(slot), count);
    else this.used.delete(Number(slot));
    // 次数角标
    let badge = rec.node.querySelector('.kb-count');
    if (used && count > 0) {
      if (!badge) {
        badge = h('span', { class: 'kb-count' });
        rec.node.append(badge);
      }
      badge.textContent = String(count);
    } else if (badge) {
      badge.remove();
    }
  }

  setBadge(slot, text, { kind = 'badge' } = {}) {
    const rec = this.keys.get(Number(slot));
    if (!rec) return;
    let node = rec.node.querySelector(kind === 'count' ? '.kb-count' : '.kb-badge');
    if (!text) { node?.remove(); return; }
    if (!node) {
      node = h('span', { class: kind === 'count' ? 'kb-count' : 'kb-badge' });
      rec.node.append(node);
    }
    node.textContent = text;
  }

  setDisabled(slot, disabled = true) {
    const n = this.keyNode(slot);
    if (!n) return;
    n.classList.toggle('is-off', !!disabled);
    n.disabled = !!disabled;
  }

  clearStates() {
    for (const { node } of this.keys.values()) {
      node.classList.remove('is-selected', 'is-pressed', 'is-used', 'is-off', 'is-dim');
      node.querySelector('.kb-count, .kb-badge')?.remove();
    }
    this.selected.clear();
    this.pressed.clear();
    this.used.clear();
  }

  setLegend(slot, main, sub = '') {
    const rec = this.keys.get(Number(slot));
    if (!rec) return;
    rec.mainEl.textContent = main ?? '';
    if (rec.subEl) rec.subEl.textContent = sub;
  }

  /* 兼容 alias */
  mountTo(parent) { return this.mount(parent); }
}

export function createKeyboard(opts) {
  return new Keyboard(opts);
}
