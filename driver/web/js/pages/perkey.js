/* pages/perkey.js — 逐键灯效：画笔 / 橡皮 / 填充 / 吸管 + 常用色板 + 写入自定义灯表 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { icon } from '../icons.js';
import { h, clamp, rgbToHex } from '../util.js';
import { Keyboard } from '../components/keyboard.js';
import { ColorPicker } from '../components/colorpicker.js';
import { badge } from '../components/widgets.js';

const ALL_KEYS = KEY_LAYOUT.rows.flat();
const NO_LED = new Set(KEY_LAYOUT.notes.noLed);
const DIM_LED = new Set(KEY_LAYOUT.notes.dimLed);

const TOOLS = [
  { id: 'brush', icon: 'paintbrush', label: '画笔' },
  { id: 'eraser', icon: 'eraser', label: '橡皮' },
  { id: 'fill', icon: 'bucket', label: '填充' },
  { id: 'pick', icon: 'eyedropper', label: '取色' },
];

function isOn(rgb) { return rgb && (rgb[0] + rgb[1] + rgb[2]) > 12; }

export default {
  id: 'perkey',
  async mount(root, ctx) {
    const { api, t } = ctx;

    let current = [56, 132, 255];
    let tool = 'brush';
    let colors = {};        // slot(string) -> [r,g,b]
    let saved = {};         // 最近一次从设备读取/写入成功的快照
    let painting = false;
    let dirty = false;

    /* ---------------- 加载 ---------------- */
    try {
      const resp = await api.get('/api/lighting/custom');
      colors = { ...(resp?.colors || {}) };
    } catch (e) { console.warn('[perkey] 读取自定义灯失败', e); }
    saved = JSON.parse(JSON.stringify(colors));

    /* ---------------- 组件 ---------------- */
    const kb = new Keyboard({ interactive: true, legends: true, mode: 'perkey' });
    const countBadge = badge('0 / 87', 'accent');
    const dirtyBadge = badge('已同步', 'ok');
    const colorChip = h('span', { class: 'swatch-btn', style: { width: '22px', height: '22px', cursor: 'default' } });

    const toolButtons = TOOLS.map((tl) => {
      const btn = h('button', {
        type: 'button',
        class: `tool-btn${tool === tl.id ? ' active' : ''}`,
        title: tl.label,
        onclick: () => {
          tool = tl.id;
          toolButtons.forEach((b, i) => b.classList.toggle('active', TOOLS[i].id === tool));
          if (tl.id === 'fill') fillAll();
          updateHint();
        },
      }, h('span', { html: icon(tl.icon, { size: 15 }) }), h('span', {}, tl.label));
      return btn;
    });

    const toolbar = h('div', { class: 'tool-bar' },
      ...toolButtons,
      h('div', { class: 'tool-divider' }),
      h('button', {
        class: 'tool-btn', title: '清空全部',
        onclick: () => { clearAll(); ctx.toast('已清空（记得点击应用写入）'); },
      }, h('span', { html: icon('trash', { size: 15 }) }), h('span', {}, '清空')),
      h('div', { class: 'spacer' }),
      h('span', { class: 'tiny muted' }, '当前颜色'),
      colorChip,
    );

    const hintEl = h('div', { class: 'tiny muted mt-8' });
    function updateHint() {
      const map = { brush: '按住鼠标在键盘上拖动即可连续上色', eraser: '点击 / 拖动擦除按键颜色（写入 RGB 0,0,0）', fill: '一键把全部 87 键填充为当前颜色', pick: '点击键盘上的按键，取它的颜色作为当前颜色' };
      hintEl.textContent = map[tool] || '';
      toolButtons.forEach((b, i) => b.classList.toggle('active', TOOLS[i].id === tool));
    }

    /* ---------------- 色板 ---------------- */
    const picker = new ColorPicker({ value: current });
    picker.onChange((rgb) => {
      current = rgb;
      colorChip.style.background = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
    });
    colorChip.style.background = `rgb(${current[0]},${current[1]},${current[2]})`;

    /* ---------------- 应用颜色到键盘 ---------------- */
    function paintSlot(slot) {
      const s = String(slot);
      const meta = ALL_KEYS.find((k) => k.slot === slot);
      if (tool === 'pick') {
        if (isOn(colors[s])) {
          current = [...colors[s]];
          picker.set(current, true);
          colorChip.style.background = `rgb(${current[0]},${current[1]},${current[2]})`;
          ctx.toast(`已取色 ${rgbToHex(current)}`, { timeout: 1500 });
        }
        return;
      }
      if (tool === 'eraser') {
        colors[s] = [0, 0, 0];
      } else if (tool === 'fill') {
        fillAll();
        return;
      } else {
        colors[s] = [...current];
      }
      if (NO_LED.has(slot)) ctx.toast('该键位无可见 LED（小屏幕位置），写入不生效', { timeout: 1800 });
      else if (DIM_LED.has(slot)) ctx.toast('该键位有 LED 驱动但真机上不可见（未装配）', { timeout: 1800 });
      renderKey(slot);
      markDirty();
    }

    function renderKey(slot) {
      const rgb = colors[String(slot)];
      kb.setColor(slot, isOn(rgb) ? rgb : null);
    }
    function renderAll() {
      for (const k of ALL_KEYS) renderKey(k.slot);
      updateCount();
    }
    function fillAll() {
      for (const k of ALL_KEYS) colors[String(k.slot)] = [...current];
      renderAll();
      markDirty();
      ctx.toast('已填充 87 键', { timeout: 1400 });
    }
    function clearAll() {
      for (const k of ALL_KEYS) colors[String(k.slot)] = [0, 0, 0];
      renderAll();
      markDirty();
    }
    function updateCount() {
      const n = ALL_KEYS.filter((k) => isOn(colors[String(k.slot)])).length;
      countBadge.textContent = `${n} / 87`;
    }
    function markDirty() {
      dirty = true;
      dirtyBadge.textContent = '未应用';
      dirtyBadge.className = 'badge warn';
    }
    function markClean() {
      dirty = false;
      dirtyBadge.textContent = '已同步';
      dirtyBadge.className = 'badge ok';
    }

    /* ---------------- 拖拽上色 ---------------- */
    kb.deck.addEventListener('pointerdown', (e) => {
      const keyEl = e.target.closest?.('.kb-key');
      if (!keyEl) return;
      e.preventDefault();
      painting = true;
      paintSlot(Number(keyEl.dataset.slot));
    });
    kb.deck.addEventListener('pointerover', (e) => {
      if (!painting) return;
      const keyEl = e.target.closest?.('.kb-key');
      if (!keyEl) return;
      paintSlot(Number(keyEl.dataset.slot));
    });
    const stopPainting = () => { painting = false; };
    window.addEventListener('pointerup', stopPainting);
    window.addEventListener('pointercancel', stopPainting);
    kb.deck.addEventListener('contextmenu', (e) => e.preventDefault());

    /* ---------------- 快捷预设 ---------------- */
    function presetRainbow() {
      for (const k of ALL_KEYS) {
        const hue = (k.x / 275) * 300 + k.row * 10;
        colors[String(k.slot)] = hslToRgb(hue);
      }
      renderAll(); markDirty(); ctx.toast('已应用彩虹渐变（未写入）');
    }
    function presetWave() {
      for (const k of ALL_KEYS) {
        const hue = 190 + Math.sin(k.x / 42 + k.row * 0.8) * 60;
        colors[String(k.slot)] = hslToRgb(hue - 20, 90, 54);
      }
      renderAll(); markDirty(); ctx.toast('已应用海浪预设（未写入）');
    }
    function presetOff() {
      for (const k of ALL_KEYS) colors[String(k.slot)] = [0, 0, 0];
      renderAll(); markDirty();
    }

    /* ---------------- 应用 / 读取 ---------------- */
    const applyBtn = h('button', {
      class: 'btn primary w-full',
      html: `${icon('save', { size: 15 })}<span>应用并切到自定义模式</span>`,
      onclick: apply,
    });
    const revertBtn = h('button', {
      class: 'btn w-full',
      html: `${icon('undo', { size: 15 })}<span>撤销未应用修改</span>`,
      onclick: () => {
        colors = JSON.parse(JSON.stringify(saved));
        renderAll(); markClean();
        ctx.toast('已撤销到上次同步状态');
      },
    });
    const reloadBtn = h('button', {
      class: 'btn w-full',
      html: `${icon('refresh', { size: 15 })}<span>从设备重新读取</span>`,
      onclick: reload,
    });

    async function apply() {
      applyBtn.disabled = true;
      applyBtn.querySelector('span').textContent = '正在写入…';
      try {
        await api.put('/api/lighting/custom', { colors, apply: true });
        saved = JSON.parse(JSON.stringify(colors));
        markClean();
        ctx.toastSuccess('已写入逐键灯表，设备已切换到「自定义」模式');
        ctx.refreshStatus?.();
      } catch (e) {
        ctx.toastError(`写入失败：${e.message || e}`);
      } finally {
        applyBtn.disabled = false;
        applyBtn.querySelector('span').textContent = '应用并切到自定义模式';
      }
    }

    async function reload() {
      try {
        const resp = await api.get('/api/lighting/custom');
        colors = { ...(resp?.colors || {}) };
        saved = JSON.parse(JSON.stringify(colors));
        renderAll(); markClean();
        ctx.toastSuccess('已从设备重新读取逐键灯表');
      } catch (e) {
        ctx.toastError(`读取失败：${e.message || e}`);
      }
    }

    /* ---------------- 布局 ---------------- */
    const kbCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '逐键上色（87 键）'),
          h('div', { class: 'card-desc' }, '官方 87 键几何 · 支持拖拽连续上色')),
        h('div', { class: 'spacer' }),
        countBadge,
      ),
      h('div', { class: 'card-body' },
        toolbar,
        hintEl,
        h('div', { class: 'mt-12', style: { padding: '10px 0 2px' } }, kb.deck),
        h('div', { class: 'kb-legend mt-12' },
          h('span', { class: 'item' }, h('span', { class: 'swatch', style: { background: 'rgb(90,160,255)' } }), '已上色按键'),
          h('span', { class: 'item' }, h('span', { class: 'swatch no-led' }), '无可见 LED（99 / 100 / 102）'),
          h('span', { class: 'item' }, 'Fn 键 LED 为充电指示灯'),
        ),
      ),
    );

    const paletteCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '颜色'), h('div', { class: 'card-desc' }, '常用色板 + 最近使用')),
        h('div', { class: 'spacer' }),
        h('span', { class: 'mono tiny muted' }, rgbToHex(current)),
      ),
      h('div', { class: 'card-body' }, picker.el),
    );

    const actionCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '写入设备')),
        h('div', { class: 'spacer' }), dirtyBadge,
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'stack' },
          applyBtn,
          h('div', { class: 'row' }, revertBtn),
          reloadBtn,
          h('div', { class: 'divider-dashed' }),
          h('div', { class: 'tiny muted' }, '应用时调用 PUT /api/lighting/custom { colors, apply: true }，并把灯效模式切到自定义（mode 128）。'),
        ),
      ),
    );

    const presetCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '快捷预设')),
      h('div', { class: 'card-body' },
        h('div', { class: 'row' },
          h('button', { class: 'btn sm', onclick: presetRainbow }, '彩虹渐变'),
          h('button', { class: 'btn sm', onclick: presetWave }, '海浪'),
          h('button', { class: 'btn sm danger', onclick: presetOff }, '全部关闭'),
        ),
      ),
    );

    const notesCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '说明')),
      h('div', { class: 'card-body' },
        h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
          h('p', {}, '· 设备灯表为 128 项 × [idx, R, G, B]，MK87 的 87 个物理键使用各自槽位号作为 LED id。'),
          h('p', {}, '· 模式 20 / 21 / 128 共用同一张自定义灯表；应用后自动切到 mode 128。'),
          h('p', {}, '· 亮度仍由「灯光效果」页的亮度参数控制。'),
          h('p', {}, '· 槽 97 / 98 有 LED 驱动通道但真机不可见；99 / 100 / 102 无 LED。'),
        ),
      ),
    );

    const right = h('div', { class: 'grid-stack' }, paletteCard, actionCard, presetCard, notesCard);
    root.append(h('div', { class: 'grid grid-main' }, h('div', { class: 'grid-stack' }, kbCard), right));

    renderAll();
    updateHint();
    kb.refreshSize();

    /* 键盘尺寸随窗口变化 */
    const ro = new ResizeObserver(() => kb.refreshSize());
    ro.observe(kbCard);

    return () => {
      window.removeEventListener('pointerup', stopPainting);
      window.removeEventListener('pointercancel', stopPainting);
      ro.disconnect();
      kb.destroy();
    };
  },
};

function hslToRgb(hue, s = 88, l = 56) {
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
