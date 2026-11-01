/* colorpicker.js — 自定义取色器：SV 面板 + 色相条 + HEX/RGB 输入 + 常用色板/最近使用 */
import { h, clamp, hexToRgb, rgbToHex, store, Emitter } from '../util.js';

export const PRESET_COLORS = [
  [255, 255, 255], [255, 64, 64], [255, 138, 0], [255, 214, 0], [154, 230, 0], [0, 230, 118],
  [0, 229, 255], [41, 121, 255], [124, 77, 255], [213, 0, 249], [255, 64, 129], [160, 174, 192],
];

function rgbToHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let hh = 0;
  if (d) {
    if (max === r) hh = ((g - b) / d) % 6;
    else if (max === g) hh = (b - r) / d + 2;
    else hh = (r - g) / d + 4;
  }
  hh = Math.round(hh * 60);
  if (hh < 0) hh += 360;
  return [hh, max === 0 ? 0 : d / max, max];
}

function hsvToRgb(h, s, v) {
  h = ((h % 360) + 360) % 360;
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let rgb = [0, 0, 0];
  if (h < 60) rgb = [c, x, 0];
  else if (h < 120) rgb = [x, c, 0];
  else if (h < 180) rgb = [0, c, x];
  else if (h < 240) rgb = [0, x, c];
  else if (h < 300) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  return rgb.map((n) => Math.round(clamp((n + m) * 255, 0, 255)));
}

const RECENT_KEY = 'mk87.recentColors';

export class ColorPicker extends Emitter {
  constructor({ value = [255, 64, 64], presets = PRESET_COLORS, showInputs = true } = {}) {
    super();
    [this.h, this.s, this.v] = rgbToHsv(value);
    this.rgb = [...value];
    this.el = h('div', { class: 'cp' });
    this._build(presets, showInputs);
    this._syncUI();
  }

  _build(presets, showInputs) {
    this.sv = h('div', { class: 'cp-sv', tabindex: '0', 'aria-label': '饱和度 / 明度选择' },
      h('div', { class: 'cp-cursor' }));
    this.sv.style.setProperty('--cp-h', String(this.h));
    this.hue = h('div', { class: 'cp-hue', tabindex: '0', 'aria-label': '色相选择' },
      h('div', { class: 'cp-cursor' }));

    this.preview = h('div', { class: 'cp-preview' });
    this.hexInput = h('input', { class: 'input cp-hex', maxlength: '7', spellcheck: 'false', 'aria-label': 'HEX 颜色' });
    this.rInput = h('input', { class: 'input', maxlength: '3', inputmode: 'numeric', 'aria-label': 'R' });
    this.gInput = h('input', { class: 'input', maxlength: '3', inputmode: 'numeric', 'aria-label': 'G' });
    this.bInput = h('input', { class: 'input', maxlength: '3', inputmode: 'numeric', 'aria-label': 'B' });

    this.el.append(this.sv, this.hue);
    if (showInputs) {
      this.el.append(h('div', { class: 'cp-bottom' },
        this.preview,
        h('div', { class: 'cp-fields' }, this.hexInput, this.rInput, this.gInput, this.bInput),
      ));
    }

    this.swatches = h('div', { class: 'swatches' });
    this.el.append(this.swatches);
    this._renderSwatches(presets);
    this._bindEvents();
  }

  _renderSwatches(presets) {
    this.swatches.innerHTML = '';
    const recent = store.get(RECENT_KEY, []);
    const all = [...presets, ...recent.filter((c) => !presets.some((p) => rgbToHex(p) === rgbToHex(c)))];
    for (const c of all.slice(0, presets.length + 10)) {
      this.swatches.append(h('button', {
        type: 'button',
        class: 'swatch-btn',
        title: rgbToHex(c),
        style: { background: `rgb(${c[0]}, ${c[1]}, ${c[2]})` },
        onclick: () => this.set(c),
      }));
    }
  }

  _bindEvents() {
    const dragSV = (e) => {
      const rect = this.sv.getBoundingClientRect();
      const x = clamp((e.clientX - rect.left) / rect.width, 0, 1);
      const y = clamp((e.clientY - rect.top) / rect.height, 0, 1);
      this.s = x;
      this.v = 1 - y;
      this._emitColor();
    };
    const dragHue = (e) => {
      const rect = this.hue.getBoundingClientRect();
      this.h = Math.round(clamp((e.clientX - rect.left) / rect.width, 0, 0.999) * 360);
      this._emitColor();
    };
    this.sv.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.sv.setPointerCapture(e.pointerId);
      dragSV(e);
      const move = (ev) => dragSV(ev);
      const up = () => {
        this.sv.removeEventListener('pointermove', move);
        this.sv.removeEventListener('pointerup', up);
        this._remember();
      };
      this.sv.addEventListener('pointermove', move);
      this.sv.addEventListener('pointerup', up);
    });
    this.hue.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.hue.setPointerCapture(e.pointerId);
      dragHue(e);
      const move = (ev) => dragHue(ev);
      const up = () => {
        this.hue.removeEventListener('pointermove', move);
        this.hue.removeEventListener('pointerup', up);
        this._remember();
      };
      this.hue.addEventListener('pointermove', move);
      this.hue.addEventListener('pointerup', up);
    });

    const commitHex = () => {
      const rgb = hexToRgb(this.hexInput.value);
      if (rgb) this.set(rgb);
      else this._syncUI();
    };
    this.hexInput.addEventListener('change', commitHex);
    this.hexInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') commitHex(); });
    const commitRgb = () => {
      const rgb = [this.rInput, this.gInput, this.bInput].map((i) => clamp(parseInt(i.value, 10) || 0, 0, 255));
      this.set(rgb);
    };
    for (const i of [this.rInput, this.gInput, this.bInput]) {
      i.addEventListener('change', commitRgb);
      i.addEventListener('keydown', (e) => { if (e.key === 'Enter') commitRgb(); });
    }
  }

  _emitColor() {
    this.rgb = hsvToRgb(this.h, this.s, this.v);
    this._syncUI();
    this.emit('change', this.rgb);
  }

  _remember() {
    const hex = rgbToHex(this.rgb);
    const recent = store.get(RECENT_KEY, []).filter((c) => rgbToHex(c) !== hex);
    recent.unshift([...this.rgb]);
    store.set(RECENT_KEY, recent.slice(0, 10));
    this._renderSwatches(PRESET_COLORS);
  }

  _syncUI() {
    this.sv.style.setProperty('--cp-h', String(this.h));
    this.sv.querySelector('.cp-cursor').style.left = `${this.s * 100}%`;
    this.sv.querySelector('.cp-cursor').style.top = `${(1 - this.v) * 100}%`;
    this.hue.querySelector('.cp-cursor').style.left = `${(this.h / 360) * 100}%`;
    this.hue.querySelector('.cp-cursor').style.setProperty('--cp-hue-color', `hsl(${this.h} 100% 50%)`);
    this.preview.style.background = `rgb(${this.rgb[0]}, ${this.rgb[1]}, ${this.rgb[2]})`;
    if (document.activeElement !== this.hexInput) this.hexInput.value = rgbToHex(this.rgb);
    if (document.activeElement !== this.rInput) this.rInput.value = String(this.rgb[0]);
    if (document.activeElement !== this.gInput) this.gInput.value = String(this.rgb[1]);
    if (document.activeElement !== this.bInput) this.bInput.value = String(this.rgb[2]);
  }

  set(rgb, silent = false) {
    this.rgb = rgb.map((n) => clamp(Math.round(n), 0, 255));
    [this.h, this.s, this.v] = rgbToHsv(this.rgb);
    this._syncUI();
    if (!silent) this.emit('change', this.rgb);
  }

  get value() { return [...this.rgb]; }

  onChange(fn) { return this.on('change', fn); }
}
