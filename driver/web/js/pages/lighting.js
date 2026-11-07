/* pages/lighting.js — 灯光效果页：19 种模式 + 参数 + 实时预览 + 写入设备 */
import { LIGHTING_MODES, BRIGHTNESS_RANGE, SPEED_RANGE } from '../data/lighting.js';
import { KEY_LAYOUT } from '../data/keyboard.js';
import { icon } from '../icons.js';
import { h, clamp, debounce } from '../util.js';
import { Keyboard } from '../components/keyboard.js';
import { ColorPicker } from '../components/colorpicker.js';
import { createSegmented, createStepper, badge, sectionTitle } from '../components/widgets.js';

const DIRS = [
  { value: 0, label: '右' },
  { value: 1, label: '左' },
  { value: 2, label: '上' },
  { value: 3, label: '下' },
];

/* 官方面板只有两个方向按钮：directionPosition==='top' → 上/下，否则 左/右（spec-lighting.md §7.1） */
function dirOptionsFor(mode) {
  if (mode && mode.directionPosition === 'top') return [{ value: 2, label: '上' }, { value: 3, label: '下' }];
  return [{ value: 1, label: '左' }, { value: 0, label: '右' }];
}

const KEYS = KEY_LAYOUT.rows.flat().map((k) => ({
  slot: k.slot,
  x: k.x + k.w / 2,
  w: k.w,
  row: k.row,
  led: k.led,
}));

/* 亮度 1..6（设备上 1 = 全灭）→ 预览倍率 */
const BRIGHTNESS_MULT = [0, 0.04, 0.28, 0.44, 0.62, 0.8, 1.0];

function hslToRgb(hue, s = 100, l = 55) {
  hue = ((hue % 360) + 360) % 360;
  s /= 100; l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = l - c / 2;
  let rgb = [0, 0, 0];
  if (hue < 60) rgb = [c, x, 0];
  else if (hue < 120) rgb = [x, c, 0];
  else if (hue < 180) rgb = [0, c, x];
  else if (hue < 240) rgb = [0, x, c];
  else if (hue < 300) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  return rgb.map((v) => clamp(Math.round((v + m) * 255), 0, 255));
}

function mix(a, b, t) {
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ].map((v) => Math.round(clamp(v, 0, 255)));
}
function scale(c, m) { return c.map((v) => Math.round(clamp(v * m, 0, 255))); }
function hash01(n) {
  const s = Math.sin(n * 12.9898 + 78.233) * 43758.5453;
  return s - Math.floor(s);
}

const DESC_FALLBACK = {
  1: '整片键盘保持单一颜色', 2: '随机亮起一颗按键后熄灭', 3: '几乎全部熄灭，随机留下微光',
  4: '彩色光点随机闪烁', 5: '白光如雪花飘落', 6: '多种颜色交替绽放', 7: '亮度缓慢起伏',
  8: '色相沿光谱循环', 9: '色彩从中间向四周涌出', 10: '多色光带纵横交错',
  11: '颜色像水流一样漂移', 12: '光带旋转盘旋', 13: '随机位置瞬间爆闪',
  14: '左右对称同时亮起', 15: '从中心向外扩散涟漪', 16: '色彩持续单向流动',
  17: '层层叠叠的波浪', 18: '斜向光点落下', 19: '单色光带来回穿梭',
  128: '使用逐键灯效页自定义每颗按键',
};

export default {
  id: 'lighting',
  async mount(root, ctx) {
    const { api, t } = ctx;

    /* ---------------- 数据加载 ---------------- */
    let modes = LIGHTING_MODES;
    let lighting = {
      mode: 7, brightness: 5, speed: 3, direction: 0, colorMode: 1,
      color: { r: 56, g: 132, b: 255 },
    };
    let customColors = {};
    try {
      const resp = await api.get('/api/lighting');
      if (resp) {
        const rgb = Array.isArray(resp.rgb) ? resp.rgb : null;
        const color = resp.color || (rgb ? { r: rgb[0], g: rgb[1], b: rgb[2] } : null);
        lighting = { ...lighting, ...resp, color: { ...lighting.color, ...(color || {}) } };
      }
    } catch (e) { console.warn('[lighting] 读取失败', e); }
    try {
      const resp = await api.get('/api/lighting/modes');
      const list = Array.isArray(resp) ? resp : resp?.modes;
      if (Array.isArray(list) && list.length) {
        // 后端返回的元数据可能字段不同，做一次宽松合并
        modes = LIGHTING_MODES.map((base) => {
          const hit = list.find((x) => Number(x.id ?? x.mode ?? x.value) === base.id);
          return hit ? { ...base, name: hit.name || base.name, params: hit.params || base.params } : base;
        });
      }
    } catch (e) { /* 使用内置数据 */ }
    try {
      const resp = await api.get('/api/lighting/custom');
      customColors = resp?.colors || {};
    } catch (e) { /* ignore */ }

    const state = {
      mode: Number(lighting.mode) || 0,
      brightness: clamp(Number(lighting.brightness) || 5, 1, 6),
      speed: clamp(Number(lighting.speed) || 3, 1, 6),
      direction: Number(lighting.direction) || 0,
      colorMode: Number(lighting.colorMode) ?? 1,
      color: [lighting.color.r ?? 56, lighting.color.g ?? 132, lighting.color.b ?? 255],
      lastMode: Number(lighting.mode) || 7,
    };

    /* ---------------- 布局骨架 ---------------- */
    const previewBadge = h('span', { class: 'preview-badge' }, h('span', { class: 'pulse' }), '本地预览 · 20 FPS');
    /* 只读的「当前设备灯效」：外部/键盘侧改动时只更新这里，不重建页面，避免重置正在拖动的滑块 */
    const currentEffectBadge = badge('—', 'accent');
    const currentEffectHint = badge('键盘侧已更改', 'warn');
    currentEffectHint.style.display = 'none';
    const keyboard = new Keyboard({ interactive: false, legends: false, mode: 'lighting' });
    const stage = h('div', { class: 'preview-stage' },
      h('div', { class: 'stage-head' },
        h('h3', {}, '87 键灯效预览'),
        h('div', { class: 'spacer' }),
        previewBadge,
      ),
      keyboard.deck,
      h('div', { class: 'kb-legend mt-12' },
        h('span', { class: 'item' }, h('span', { class: 'swatch', style: { background: 'var(--kb-deck-a)' } }), '设备 87 键布局（官方 keyListRaw 几何）'),
        h('span', { class: 'item' }, h('span', { class: 'swatch no-led' }), '3 颗无可见灯'),
      ),
    );

    /* 模式网格 */
    const modeGrid = h('div', { class: 'mode-grid' });
    const modeCards = new Map();
    function buildModeGrid() {
      modeGrid.innerHTML = '';
      modeCards.clear();
      for (const mode of modes) {
        const isCustom = mode.id === 128 || mode.custom;
        const card = h('button', {
          type: 'button',
          class: `mode-card${state.mode === mode.id ? ' active' : ''}`,
          title: mode.desc || '',
          onclick: () => selectMode(mode.id),
        },
          h('div', { class: 'mode-icon', html: icon(mode.icon || 'sun', { size: 18 }) }),
          h('div', { class: 'mode-name' }, mode.name),
          h('div', { class: 'mode-meta' },
            mode.color ? badge('颜色', 'accent') : null,
            mode.speed ? badge('速度', '') : null,
            mode.direction ? badge('方向', 'violet') : null,
            isCustom ? badge('逐键', 'ok') : null,
          ),
          h('div', { class: 'mode-desc' }, mode.desc || DESC_FALLBACK[mode.id] || ''),
        );
        modeGrid.append(card);
        modeCards.set(mode.id, card);
      }
    }

    /* 参数面板 */
    const colorModeSeg = createSegmented({
      options: [{ value: 0, label: '单色' }, { value: 1, label: 'RGB' }],
      value: state.colorMode,
      onChange: (v) => { state.colorMode = v; pushApply(); },
    });
    const colorModeField = h('div', { class: 'param-row' },
      h('div', { class: 'param-head' }, h('h4', {}, '颜色模式'), h('span', { class: 'tiny muted' }, '单色 = 使用下方颜色；RGB = 固件自动配色（0/1 两种）')),
      colorModeSeg.el,
    );

    const picker = new ColorPicker({ value: state.color });
    picker.onChange((rgb) => {
      state.color = rgb;
      state.colorMode = 0; // 与官方行为一致：选色即切到单色
      colorModeSeg.set(0);
      pushApply();
    });
    const colorField = h('div', { class: 'param-row' },
      h('div', { class: 'param-head' }, h('h4', {}, t('lighting.color'))),
      picker.el,
    );

    const brightnessStepper = createStepper({
      min: 2, max: 6, value: Math.max(2, state.brightness),
      onChange: (v) => { state.brightness = v; pushApply(); },
    });
    const brightnessNote = h('div', { class: 'field-hint' }, '设备亮度 1..6 为档位，1 实际全灭；因此这里只开放 2–6。要关灯请用「关闭背光」（mode=0），亮度 0 不会关灯。');
    const brightnessField = h('div', { class: 'param-row' },
      h('div', { class: 'param-head' }, h('h4', {}, t('lighting.brightness')), h('span', { class: 'tiny muted' }, '1–6')),
      h('div', { class: 'row' }, brightnessStepper.el),
      brightnessNote,
    );

    const speedStepper = createStepper({
      min: 1, max: 6, value: state.speed,
      onChange: (v) => { state.speed = v; pushApply(); },
    });
    const speedField = h('div', { class: 'param-row' },
      h('div', { class: 'param-head' }, h('h4', {}, t('lighting.speed')), h('span', { class: 'tiny muted' }, '1–6')),
      h('div', { class: 'row' }, speedStepper.el),
    );

    const dirPicker = h('div', { class: 'dir-picker' });
    let dirButtons = [];
    function renderDirButtons(mode) {
      const opts = dirOptionsFor(mode);
      dirPicker.innerHTML = '';
      dirButtons = opts.map((d) => h('button', {
        type: 'button', class: state.direction === d.value ? 'active' : '', title: d.label,
        onclick: () => {
          state.direction = d.value;
          dirButtons.forEach((b, i) => b.classList.toggle('active', opts[i].value === state.direction));
          pushApply();
        },
      }, d.label));
      dirPicker.append(...dirButtons);
    }
    const dirField = h('div', { class: 'param-row' },
      h('div', { class: 'param-head' }, h('h4', {}, t('lighting.direction')), h('span', { class: 'tiny muted' }, '仅 10/11/12/16/18 支持')),
      dirPicker,
    );

    const offBtn = h('button', { class: 'btn sm', onclick: toggleOff });
    const applyState = h('span', { class: 'tiny muted' }, '修改后自动写入设备');
    const applyBtn = h('button', {
      class: 'btn sm primary', html: `${icon('save', { size: 14 })}<span>${t('common.apply')}</span>`,
      onclick: () => pushApply(true),
    });
    const paramsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, t('lighting.params')),
          h('div', { class: 'card-desc' }, '参数会随模式自动显隐')),
        h('div', { class: 'spacer' }),
        badge('可实时写入', 'ok'),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'row', style: { marginBottom: '10px' } },
          h('span', { class: 'tiny muted' }, '当前灯效'),
          currentEffectBadge,
          currentEffectHint,
        ),
        h('div', { class: 'param-panel' },
          colorModeField,
          colorField,
          brightnessField,
          speedField,
          dirField,
          h('div', { class: 'divider' }),
          h('div', { class: 'row between' }, applyState, h('div', { class: 'row' }, offBtn, applyBtn)),
        ),
      ),
    );

    const customHint = h('div', { class: 'demo-box mt-16', style: { display: 'none' } },
      h('div', { class: 'demo-title', html: `${icon('palette', { size: 15 })}<span>自定义逐键灯效</span>` }),
      h('div', { class: 'tiny muted mt-8' }, '当前模式使用「逐键灯效」页保存的 87 键颜色表；可以先去逐键上色，再回到这里检查整体观感。'),
      h('div', { class: 'row mt-12' },
        h('button', { class: 'btn sm soft', html: `${icon('palette', { size: 14 })}<span>前往逐键灯效</span>`, onclick: () => ctx.go('perkey') }),
      ),
    );

    const left = h('div', { class: 'grid-stack' },
      h('section', { class: 'card' },
        h('div', { class: 'card-head' },
          h('div', {}, h('div', { class: 'card-title' }, '实时预览'), h('div', { class: 'card-desc' }, '前端本地渲染，不影响设备')),
        ),
        h('div', { class: 'card-body' }, stage),
      ),
      h('section', { class: 'card' },
        h('div', { class: 'card-head' },
          h('div', {}, h('div', { class: 'card-title' }, t('lighting.modes')),
            h('div', { class: 'card-desc' }, 'MK87 实际可用的 19 种灯效 + 自定义')),
        ),
        h('div', { class: 'card-body' }, modeGrid),
        customHint,
      ),
    );
    const right = h('div', { class: 'grid-stack' }, paramsCard);
    root.append(h('div', { class: 'grid grid-main' }, left, right));

    /* ---------------- 行为 ---------------- */
    const applyRemote = debounce(async (explicit = false) => {
      const body = {
        mode: state.mode,
        brightness: state.brightness,
        speed: state.speed,
        direction: state.direction,
        colorMode: state.colorMode,
        color: { r: state.color[0], g: state.color[1], b: state.color[2] },
      };
      applyState.textContent = '正在写入设备…';
      try {
        await api.put('/api/lighting', body);
        applyState.textContent = `已应用到设备 · ${new Date().toLocaleTimeString()}`;
        if (explicit) ctx.toastSuccess(t('lighting.applied'));
      } catch (e) {
        applyState.textContent = '写入失败（设备可能未连接）';
        if (explicit) ctx.toastError(`写入失败：${e.message || e}`);
      }
    }, 320);

    function pushApply(explicit = false) {
      applyState.textContent = '待写入…';
      applyRemote(explicit);
    }

    /* ---------------- 当前灯效（只读同步，不改动参数控件） ---------------- */
    let disposed = false;
    let liveHintTimer = null;
    let liveRefreshTimer = null;
    let liveRefreshSeq = 0;

    function effectLabel(info) {
      const mode = Number(info?.mode);
      const kind = info?.kind;
      if (kind === 'off' || mode === 0) return '已关灯';
      if (kind === 'custom' || mode === 20 || mode === 21 || mode === 128) return '自定义逐键灯效';
      const local = modes.find((m) => Number(m.id) === mode);
      if (local) return local.name;
      if (info?.name) return info.name;
      return Number.isFinite(mode) ? `模式 ${mode}` : '—';
    }

    function renderCurrentEffect(info) {
      if (!info) return;
      currentEffectBadge.textContent = effectLabel(info);
    }

    /** 键盘侧/外部改动：只在页面内闪一下小徽章，不弹窗、不打断操作 */
    function flashKeyboardSideHint() {
      currentEffectHint.style.display = '';
      clearTimeout(liveHintTimer);
      liveHintTimer = setTimeout(() => {
        currentEffectHint.style.display = 'none';
        liveHintTimer = null;
      }, 6000);
    }

    async function refreshCurrentEffect(seq) {
      try {
        const resp = await api.get('/api/lighting');
        if (disposed || seq !== liveRefreshSeq) return;
        const ledger = resp?.ledger && typeof resp.ledger === 'object' ? resp.ledger : null;
        renderCurrentEffect(ledger || { mode: resp?.mode });
      } catch (e) {
        console.warn('[lighting] 刷新当前灯效失败', e);
      }
    }

    /** 同一时间只发一次 GET，避免连续事件（拖动亮度等）打爆接口 */
    function scheduleCurrentEffectRefresh() {
      const seq = ++liveRefreshSeq;
      clearTimeout(liveRefreshTimer);
      liveRefreshTimer = setTimeout(() => {
        liveRefreshTimer = null;
        refreshCurrentEffect(seq);
      }, 180);
    }

    function selectedMode() {
      return modes.find((m) => m.id === state.mode) || modes[0];
    }

    function selectMode(id) {
      const mode = modes.find((m) => m.id === id);
      if (!mode) return;
      state.mode = id;
      if (id !== 0) state.lastMode = id;
      renderCurrentEffect({ mode: id });
      if (mode.direction) state.direction = mode.directionDefault ?? 0;
      if (mode.speed && state.speed < 1) state.speed = 3;
      modeCards.forEach((card, cid) => card.classList.toggle('active', cid === id));
      customHint.style.display = id === 128 ? '' : 'none';
      offBtn.innerHTML = id === 0 ? '开启背光' : '关闭背光';
      offBtn.classList.toggle('soft', id !== 0);
      syncParamVisibility();
      pushApply();
    }

    function toggleOff() {
      if (state.mode === 0) {
        state.mode = state.lastMode || 7;
      } else {
        state.lastMode = state.mode;
        state.mode = 0;
      }
      renderCurrentEffect({ mode: state.mode });
      modeCards.forEach((card, cid) => card.classList.toggle('active', cid === state.mode));
      customHint.style.display = state.mode === 128 ? '' : 'none';
      offBtn.innerHTML = state.mode === 0 ? '开启背光' : '关闭背光';
      syncParamVisibility();
      pushApply();
    }

    function syncParamVisibility() {
      const mode = selectedMode();
      const off = state.mode === 0;
      colorField.style.display = !off && mode && mode.color ? '' : 'none';
      colorModeField.style.display = !off && mode && mode.color && !mode.custom ? '' : 'none';
      speedField.style.display = !off && mode && mode.speed ? '' : 'none';
      dirField.style.display = !off && mode && mode.direction ? '' : 'none';
      brightnessField.style.display = off ? 'none' : '';
      applyState.textContent = off ? '背光已关闭' : '修改后自动写入设备';
      if (!off && mode) renderDirButtons(mode);
      speedStepper.set(state.speed);
      brightnessStepper.set(Math.max(2, state.brightness));
      previewBadge.innerHTML = `<span class="pulse"></span>${off ? '背光关闭' : (mode ? mode.name : '—')} · 本地预览 20 FPS`;
    }

    /* ---------------- 预览动画 ---------------- */
    let rafTimer = null;
    let frameTime = 0;
    const effectStart = performance.now();

    function colorFor(geo, tSec) {
      const mode = state.mode;
      const base = state.color;
      const bm = BRIGHTNESS_MULT[clamp(state.brightness, 0, 6)] ?? 1;
      const u = { x: geo.x / 275, y: geo.row / 5 };
      u.d = Math.hypot((geo.x - 137.5) / 275, (geo.row - 2.5) / 6);
      const sp = 0.5 + state.speed * 0.38;
      const tt = tSec * sp;
      const dir = state.direction;
      const axis = dir >= 2 ? geo.row / 5 : (dir === 1 ? 1 - geo.x / 275 : geo.x / 275);
      const mono = state.colorMode === 0;
      const hueShift = state.colorMode === 1;

      switch (mode) {
        case 0: return [0, 0, 0];
        case 1: { // 静态恒亮
          const m = bm * (0.94 + 0.06 * Math.sin(tt * 1.4));
          return scale(base, m);
        }
        case 2: { // 单点亮
          const phase = Math.floor(tSec * 3.2);
          const lit = hash01(geo.slot * 7.7 + phase * 13.1) > 0.93;
          if (lit) return scale(base, bm);
          return scale(base, bm * 0.07);
        }
        case 3: { // 单熄灭
          const phase = Math.floor(tSec * 2.4);
          const dark = hash01(geo.slot * 3.31 + phase * 5.7) > 0.95;
          return dark ? [0, 0, 0] : scale(base, bm * 0.9);
        }
        case 4: { // 繁星点点
          const v = hash01(geo.slot * 1.7 + Math.floor(tSec * 5) * 2.3);
          const bright = v > 0.86 ? bm : bm * (0.12 + v * 0.18);
          return hueShift ? scale(hslToRgb(geo.slot * 7 + tSec * 40), bright) : scale(base, bright);
        }
        case 5: { // 漫天飞雪
          const fall = (geo.row / 6 + tSec * 0.35) % 1;
          const sparkle = hash01(geo.slot * 5.1 + Math.floor(tSec * 4));
          const m = clamp(0.08 + Math.pow(Math.sin(fall * Math.PI), 3) * (0.55 + sparkle * 0.45), 0, 1) * bm;
          return mix([8, 12, 20], [235, 245, 255], m);
        }
        case 6: { // 百花争艳
          const hue = (geo.slot * 37 + tSec * 90) % 360;
          const m = bm * (0.55 + 0.45 * Math.sin(tSec * 2.2 + geo.x * 0.2));
          return scale(hslToRgb(hue), m);
        }
        case 7: { // 动态呼吸
          const breath = 0.5 + 0.5 * Math.sin(tt * 1.9);
          return scale(base, bm * (0.12 + 0.88 * Math.pow(breath, 1.6)));
        }
        case 8: { // 光谱循环
          const hue = (u.x * 360 + tSec * 80) % 360;
          return scale(hslToRgb(hue), bm * 0.92);
        }
        case 9: { // 彩泉涌动
          const wave = 0.5 + 0.5 * Math.sin((u.d * 9 - tt * 1.6) * Math.PI);
          const hue = (u.d * 300 + tSec * 70) % 360;
          return scale(hslToRgb(hue), bm * Math.pow(wave, 2));
        }
        case 10: { // 多彩纵横
          const band = 0.5 + 0.5 * Math.sin((axis * 9 - tt * 2.1) * Math.PI);
          const hue = (axis * 360 + geo.row * 28 + tSec * 120) % 360;
          return scale(hslToRgb(hue), bm * Math.pow(band, 2.2));
        }
        case 11: { // 随波逐流
          const wave = 0.5 + 0.5 * Math.sin((u.x * 8 - tt * 2.2 + u.y * 1.4) * Math.PI);
          return mono ? scale(base, bm * wave) : scale(hslToRgb((u.x * 260 + tSec * 90) % 360), bm * (0.25 + wave * 0.75));
        }
        case 12: { // 峰回路转
          const ang = Math.atan2(u.y - 0.5, u.x - 0.5);
          const wave = 0.5 + 0.5 * Math.sin(ang * 2.4 + u.d * 10 - tt * 2.4);
          return scale(hslToRgb((ang * 57 + tSec * 70 + 360) % 360), bm * Math.pow(wave, 2));
        }
        case 13: { // 一触即发
          const flash = hash01(geo.slot * 2.9 + Math.floor(tSec * 9) * 7.3) > 0.945;
          return flash ? mix(base, [255, 255, 255], 0.35) : scale(base, bm * 0.1);
        }
        case 14: { // 一石二鸟
          const dist = Math.abs(u.x - 0.5) * 2;
          const wave = 0.5 + 0.5 * Math.sin((dist * 8 - tt * 2.6) * Math.PI);
          return scale(base, bm * Math.pow(wave, 2.4));
        }
        case 15: { // 涟漪扩散
          const wave = 0.5 + 0.5 * Math.sin((u.d * 16 - tt * 2.8) * Math.PI);
          return scale(hslToRgb((u.d * 200 + 190 + tSec * 30) % 360), bm * Math.pow(wave, 3));
        }
        case 16: { // 川流不息
          const wave = 0.5 + 0.5 * Math.sin((axis * 11 + tt * 2.6) * Math.PI);
          return scale(mono ? base : hslToRgb((axis * 200 + tSec * 110) % 360), bm * (0.2 + 0.8 * wave));
        }
        case 17: { // 重峦叠嶂
          const wave = 0.5 + 0.5 * Math.sin((u.y * 9 + u.x * 4.5 - tt * 2) * Math.PI);
          const wave2 = 0.5 + 0.5 * Math.sin((u.x * 7 - tt * 1.3) * Math.PI);
          return scale(hslToRgb((u.y * 140 + tSec * 50) % 360), bm * Math.pow((wave + wave2) / 2, 2));
        }
        case 18: { // 斜风细雨
          const wave = 0.5 + 0.5 * Math.sin((u.x * 7 + u.y * 7 - tt * 3.2) * Math.PI);
          return mix([16, 24, 40], mix(base, [190, 230, 255], 0.45), bm * Math.pow(wave, 4));
        }
        case 19: { // 来回穿梭
          const pos = Math.abs(((tSec * 0.34) % 1) * 2 - 1);
          const m = Math.exp(-Math.pow((u.x - pos) / 0.09, 2)) * bm;
          return scale(base, clamp(0.1 + m, 0, 1));
        }
        case 128: { // 自定义
          const c = customColors[geo.slot] || [120, 160, 255];
          return scale(c, bm * 0.95);
        }
        default: return scale(base, bm * 0.6);
      }
      return scale(base, bm);
    }

    function tick(now) {
      const tSec = (now - effectStart) / 1000;
      if (now - frameTime >= 48) {
        frameTime = now;
        const frame = new Map();
        for (const geo of KEYS) frame.set(geo.slot, colorFor(geo, tSec));
        keyboard.applyColorFrame(frame);
      }
      rafTimer = requestAnimationFrame(tick);
    }

    /* ---------------- 初始化 ---------------- */
    buildModeGrid();
    keyboard.refreshSize();
    customHint.style.display = state.mode === 128 ? '' : 'none';
    offBtn.innerHTML = state.mode === 0 ? '开启背光' : '关闭背光';
    offBtn.classList.toggle('soft', state.mode !== 0);
    syncParamVisibility();
    const initialLedger = lighting.ledger && typeof lighting.ledger === 'object' ? lighting.ledger : null;
    renderCurrentEffect(initialLedger || { mode: state.mode });

    /* lighting_changed：后端/键盘侧灯效变化（api.dispatch 统一分发为 ws:lighting_changed） */
    const offLightingChanged = ctx.onEvent('lighting_changed', (data) => {
      if (disposed) return;
      if (data?.source === 'device') flashKeyboardSideHint();
      renderCurrentEffect(data);
      scheduleCurrentEffectRefresh();
    });

    rafTimer = requestAnimationFrame(tick);

    return () => {
      disposed = true;
      clearTimeout(liveHintTimer);
      clearTimeout(liveRefreshTimer);
      offLightingChanged?.();
      cancelAnimationFrame(rafTimer);
      applyRemote.cancel?.();
      keyboard.destroy();
    };
  },
};
