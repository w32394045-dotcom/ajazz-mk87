/* pages/keymap.js — 改键：主层 / FN 层，87 键点选 + 动作选择器 + 4 字节编码预览 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { ACTIONS, DEFAULT_KEYMAP, HID_NAMES, MK87_FN_IDS } from '../data/actions.js';
import { icon } from '../icons.js';
import { h, clamp, hex2, MODIFIERS } from '../util.js';
import { Keyboard } from '../components/keyboard.js';
import { badge } from '../components/widgets.js';
import { createSegmented } from '../components/widgets.js';

const ALL_KEYS = KEY_LAYOUT.rows.flat();
const FN_DISABLED_SLOTS = new Set(Array.from({ length: 12 }, (_, i) => i + 1)); // 官方 fnDisabledKeyIds=[1..12]
const MODIFIER_USAGES = new Set(MODIFIERS.map((m) => m.usage));

const TAB_DEFS = [
  { id: 'keyboard', label: '键盘键', icon: 'keyboard' },
  { id: 'consumer', label: '多媒体', icon: 'volume' },
  { id: 'mouse', label: '鼠标', icon: 'mouse' },
  { id: 'func', label: '功能动作', icon: 'zap' },
  { id: 'macro', label: '宏', icon: 'macro' },
  { id: 'combo', label: '组合键', icon: 'plus' },
  { id: 'special', label: '特殊', icon: 'shield' },
];

/* ---------------------------------------------------------------- 动作辅助 */
export function encodeAction(action) {
  if (!action) return [0, 0, 0, 0];
  switch (action.type) {
    case 'key': return [2, 0, action.usage & 0xff, 0];
    case 'consumer': {
      const v = Number(action.usage) || 0;
      return [3, v & 0xff, (v >> 8) & 0xff, 0];
    }
    case 'mouse': return [1, Number(action.param1) || 1, Number(action.button) & 0xff, 0];
    case 'combo': {
      const keys = action.keys || [];
      const mods = keys.filter((k) => MODIFIER_USAGES.has(k));
      const main = keys.find((k) => !MODIFIER_USAGES.has(k)) || 0;
      return [7, mods[0] ?? 0, mods[1] ?? 0, main & 0xff];
    }
    case 'macro': {
      const mask = Number(action.mask ?? action.repeat) || 0;
      return [6, Number(action.slot) & 0xff, mask, mask === 1 ? clamp(Number(action.count) || 1, 1, 255) : 0];
    }
    case 'fn': {
      const id = Number(action.id) || 0;
      return [13, (id >> 16) & 0xff, (id >> 8) & 0xff, id & 0xff];
    }
    // spec-keymap.md §1.3：官方动作表里唯一形似「无」的条目 extendChars ⊠ = HID 0x6F
    case 'disabled': return [2, 0, 0, 0x6f];
    case 'default': return [0, 0, 0, 0];
    case 'raw': return action.bytes || [0, 0, 0, 0];
    default: return [0, 0, 0, 0];
  }
}

function actionLabel(action) {
  if (!action) return '默认';
  switch (action.type) {
    case 'key': return action.name || `HID 0x${hex2(action.usage)}`;
    case 'consumer': return action.name || `多媒体 0x${action.usage}`;
    case 'mouse': return action.name || '鼠标';
    case 'combo': return (action.keys || []).map((u) => HID_NAMES[String(u)] || `0x${hex2(u)}`).join(' + ') || '组合键';
    case 'macro': {
      const mask = Number(action.mask ?? action.repeat) || 0;
      const suffix = mask === 1 ? ` ×${action.count || 1}` : mask === 2 ? ' 再按结束' : '';
      return `宏 ${action.slot}${suffix}`;
    }
    case 'fn': return action.name || `功能 ${action.id}`;
    case 'disabled': return '禁用';
    case 'default': return '默认';
    case 'raw': return `原始 ${action.bytes?.map((b) => hex2(b)).join(' ')}`;
    default: return '未知';
  }
}

function actionIconName(action) {
  if (!action) return 'keyboard';
  return ({ key: 'keyboard', consumer: 'volume', mouse: 'mouse', combo: 'plus', macro: 'macro', fn: 'zap', disabled: 'shield', default: 'undo' })[action.type] || 'keyboard';
}

function isSameAction(a, b) {
  if (!a || !b || a.type !== b.type) return false;
  return encodeAction(a).join(',') === encodeAction(b).join(',');
}

/** 后端 → 前端内部模型。
    兼容两种形状：
    - mock 内部：{type:'key'|'consumer'|'fn'|'macro'|'combo'|'mouse', usage|id|slot, mask, count}
    - 真实后端：{type:'keyboard'|'consumer'|'func'|'macro'|'combo'|'mouse', value, param1..3, name/display, slot} */
export function normalizeWireAction(a) {
  if (!a || typeof a !== 'object') return a;
  switch (a.type) {
    case 'keyboard':
      return { type: 'key', usage: Number(a.usage ?? a.value ?? a.keyCode ?? 0), name: a.display || a.name || a.keyName, legacyParam1: Number(a.param1) || 0 };
    case 'key':
      return { ...a, usage: Number(a.usage ?? a.value ?? 0), name: a.display || a.name };
    case 'consumer':
      return { ...a, usage: Number(a.usage ?? a.value ?? 0), name: a.name || a.display };
    case 'func':
      return { type: 'fn', id: Number(a.id ?? a.value ?? 0), name: a.name || a.display };
    case 'fn':
      return { ...a, id: Number(a.id ?? a.value ?? 0) };
    case 'macro': {
      const mask = Number(a.mask ?? a.param2 ?? a.repeat ?? 0);
      const count = Number(a.count ?? a.param3 ?? a.maskParam ?? 0);
      return { type: 'macro', slot: Number(a.slot ?? a.value ?? a.param1 ?? 0), mask, count, name: a.name };
    }
    case 'combo': {
      const keys = Array.isArray(a.keys) ? a.keys : [a.param1, a.param2, a.param3].filter((x) => x);
      return { type: 'combo', keys };
    }
    case 'mouse':
      return { type: 'mouse', button: Number(a.button ?? a.value ?? 0), param1: Number(a.param1) || 1, name: a.name };
    case 'default':
      return { type: 'default' };
    case 'disabled':
      return { type: 'disabled' };
    default:
      return a;
  }
}

/** 键位表：兼容 {slot:action} 对象 与 后端 [{slot,...}] 数组（只保留非默认项） */
function actionListToMap(raw) {
  if (!raw) return {};
  const out = {};
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      if (!entry || typeof entry !== 'object') continue;
      const slot = Number(entry.slot ?? entry.value);
      if (!Number.isFinite(slot)) continue;
      const act = normalizeWireAction(entry);
      if (!act || act.type === 'default') continue;
      out[String(slot)] = act;
    }
    return out;
  }
  for (const [slot, entry] of Object.entries(raw)) {
    const act = normalizeWireAction(entry);
    if (!act || act.type === 'default') continue;
    out[String(slot)] = act;
  }
  return out;
}

/** 动作目录归一化：后端 keyboard/consumer 用 value 而不是 usage；func 用 value 而不是 id */
function normalizeCatalog(resp) {
  const arr = (x) => (Array.isArray(x) ? x : []);
  return {
    keyboard: arr(resp.keyboard).map((it) => ({ type: 'key', usage: Number(it.usage ?? it.value ?? 0), name: it.name, text: it.text })),
    consumer: arr(resp.consumer).map((it) => ({ type: 'consumer', usage: Number(it.usage ?? it.value ?? 0), name: it.name })),
    mouse: arr(resp.mouse).map((it) => ({ type: 'mouse', button: Number(it.button ?? it.value ?? 0), param1: Number(it.param1) || 1, name: it.name })),
    func: arr(resp.func).map((it) => ({ type: 'fn', id: Number(it.id ?? it.value ?? 0), name: it.name, text: it.text })),
    macros: arr(resp.macros),
    macroCapacity: Number(resp.macroCapacity) || 2672,
    notes: resp.notes || null,
    pageTypes: resp.pageTypes || ACTIONS.pageTypes,
  };
}

/** 前端内部模型 → 后端 wire 字段（spec-keymap.md §1 / design.md §4.6） */
export function toWireAction(a) {
  if (!a || typeof a !== 'object') return a;
  if (a.type === 'macro') {
    const mask = Number(a.mask ?? a.repeat ?? 0);
    return { type: 'macro', slot: Number(a.slot), mask, count: mask === 1 ? clamp(Number(a.count) || 1, 1, 255) : 0, name: a.name };
  }
  if (a.type === 'mouse') {
    return { type: 'mouse', param1: Number(a.param1) || 1, value: Number(a.button ?? a.value ?? 0), name: a.name };
  }
  if (a.type === 'key') return { type: 'key', usage: Number(a.usage), name: a.name };
  if (a.type === 'consumer') return { type: 'consumer', usage: Number(a.usage), name: a.name };
  if (a.type === 'combo') return { type: 'combo', keys: a.keys };
  if (a.type === 'fn') return { type: 'fn', id: Number(a.id), name: a.name };
  return a;
}

export default {
  id: 'keymap',
  async mount(root, ctx) {
    const { api, t } = ctx;

    /* ---------------- 数据 ---------------- */
    let actionsCatalog = {
      keyboard: ACTIONS.keyboard,
      consumer: ACTIONS.consumer,
      mouse: ACTIONS.mouse,
      func: ACTIONS.func,
      macros: [],
      pageTypes: ACTIONS.pageTypes,
    };
    const state = {
      layer: 'normal',
      maps: { normal: {}, fn: {} },
      defaults: { normal: {}, fn: {} },
      pending: { normal: {}, fn: {} },
      selected: null,
      tab: 'keyboard',
      macroMask: 0,
      macroCount: 1,
      comboMods: [],
      comboKey: null,
      fnReliable: true,
      macrosDetail: [],
    };

    try {
      const resp = await api.get('/api/keymap');
      if (resp) {
        state.maps.normal = actionListToMap(resp.normal);
        state.maps.fn = actionListToMap(resp.fn);
        // 2.4G 下固件对 GET_FN_KEY 返回主层 → 后端 fnReliable=false
        state.fnReliable = resp.fnReliable !== false && ctx.status?.transport !== '2.4g';
        state.apiNote = resp.note;
      }
    } catch (e) {
      console.warn('[keymap] 读取键位失败，使用内置默认', e);
      state.maps.normal = { ...DEFAULT_KEYMAP.normal };
      state.maps.fn = { ...DEFAULT_KEYMAP.fn };
    }
    try {
      const resp = await api.get('/api/macros');
      state.macrosDetail = (resp?.slots || [])
        .map((x) => ({ slot: Number(x.slot), name: x.name, actions: x.actions || [] }))
        .filter((x) => x.actions.length);
    } catch (e) { /* 宏列表失败不影响改键 */ }
    try {
      const resp = await api.get('/api/keymap/actions');
      if (resp) {
        const cat = normalizeCatalog(resp);
        actionsCatalog = {
          keyboard: cat.keyboard.length ? cat.keyboard : ACTIONS.keyboard,
          consumer: cat.consumer.length ? cat.consumer : ACTIONS.consumer,
          mouse: cat.mouse.length ? cat.mouse : ACTIONS.mouse,
          func: cat.func.length ? cat.func : ACTIONS.func,
          macros: cat.macros,
          macroCapacity: cat.macroCapacity,
          notes: cat.notes,
          pageTypes: cat.pageTypes,
        };
      }
    } catch (e) { /* 使用内置目录 */ }

    /* ---------------- 组件骨架 ---------------- */
    const kb = new Keyboard({ interactive: true, legends: true, mode: 'layout' });
    const pendingBadge = badge('0 项未保存', 'ok');
    const layerSeg = createSegmented({
      options: [{ value: 'normal', label: t('keymap.layer.normal') }, { value: 'fn', label: 'FN 层' }],
      value: state.layer,
      onChange: (v) => {
        state.layer = v;
        if (v === 'fn' && !state.fnReliable) {
          ctx.toast('2.4G 下 FN 层回读返回的是主层数据（固件行为），已切换为只读；编辑 FN 请用 USB 连接', { type: 'warn', timeout: 6500 });
        }
        updateFnWarning();
        renderKeyboard();
        if (v === 'fn' && !state.fnReliable) { kb.clearSelected(); state.selected = null; }
        renderCurrentKeyCard();
        buildPicker();
      },
    });

    const fnWarning = h('div', { class: 'banner danger', style: { display: 'none', margin: '0 0 12px' } },
      h('div', { class: 'banner-icon', html: icon('alert-triangle', { size: 17 }) }),
      h('div', { style: { minWidth: 0 } },
        h('strong', {}, 'FN 层在当前连接下不可靠'),
        h('div', { class: 'tiny', style: { marginTop: '2px' } },
          '2.4G 无线连接时，固件对 GET_FN_KEY 返回的是主层键位（已知固件行为），为避免写坏 FN 层，本页在 2.4G 下只读。请改用 USB 有线连接编辑 FN 层。'),
      ),
    );
    function updateFnWarning() {
      fnWarning.style.display = state.layer === 'fn' && !state.fnReliable ? '' : 'none';
    }

    const restoreBtn = h('button', {
      class: 'btn sm', title: '写 0 恢复出厂默认',
      html: `${icon('undo', { size: 14 })}<span>恢复默认</span>`,
      onclick: restoreDefaults,
    });
    const applyBtn = h('button', {
      class: 'btn sm primary',
      html: `${icon('save', { size: 14 })}<span>应用修改</span>`,
      onclick: applyChanges,
    });

    const currentCard = h('div');
    const pickerHost = h('div', { class: 'action-picker' });

    const leftCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '键位映射'),
          h('div', { class: 'card-desc' }, '点击按键后在右侧选择动作；MK87 官方 87 键布局')),
        h('div', { class: 'spacer' }),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'row between mb-12', style: { marginBottom: '12px' } },
          h('div', { class: 'row' }, layerSeg.el, pendingBadge),
          h('div', { class: 'row' }, restoreBtn, applyBtn),
        ),
        fnWarning,
        kb.deck,
        h('div', { class: 'kb-legend mt-12' },
          h('span', { class: 'item' }, badge('已改', 'accent'), '当前有非默认动作'),
          h('span', { class: 'item' }, 'FN 层 F1–F12 官方锁定（fnDisabledKeyIds）'),
          h('span', { class: 'item' }, '槽位号见按键左下角（悬停显示）'),
        ),
      ),
    );

    const right = h('div', { class: 'grid-stack' },
      h('section', { class: 'card' }, h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '当前按键')),
        h('div', { class: 'spacer' }),
      ), h('div', { class: 'card-body' }, currentCard)),
      h('section', { class: 'card' }, h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, t('keymap.action')),
          h('div', { class: 'card-desc' }, '选择要绑定到此按键的动作')),
      ), h('div', { class: 'card-body' }, pickerHost)),
    );
    root.append(h('div', { class: 'grid keymap-layout' }, leftCard, right));

    /* ---------------- 渲染键盘 ---------------- */
    function effectiveAction(layer, slot) {
      const s = String(slot);
      if (state.pending[layer][s] !== undefined) return state.pending[layer][s];
      return state.maps[layer][s];
    }

    function renderKeyboard() {
      // 清角标
      const fnLocked = state.layer === 'fn' && !state.fnReliable;
      kb.opts.interactive = !fnLocked;
      kb.deck.classList.toggle('interactive', !fnLocked);
      for (const k of ALL_KEYS) {
        kb.setBadge(k.slot, '');
        const officialLock = state.layer === 'fn' && FN_DISABLED_SLOTS.has(k.slot);
        kb.setDisabled(k.slot, fnLocked || officialLock);
        if (fnLocked) {
          kb.setBadge(k.slot, '只读', { kind: 'badge' });
          continue;
        }
        if (officialLock) continue;
        const act = effectiveAction(state.layer, k.slot);
        if (!act) continue;
        if (act.type === 'default') { kb.setBadge(k.slot, '默认'); continue; }
        if (act.type === 'key' && act.usage === keyDefaultUsage(k.slot)) continue; // 与默认一致不显示
        kb.setBadge(k.slot, actionLabel(act));
      }
      updatePendingUI();
    }

    function keyDefaultUsage(slot) {
      const meta = ALL_KEYS.find((k) => k.slot === slot);
      return meta?.keyCode ?? null;
    }

    function updatePendingUI() {
      const n = Object.keys(state.pending.normal).length + Object.keys(state.pending.fn).length;
      pendingBadge.textContent = n ? `${n} 项未保存` : '已同步';
      pendingBadge.className = `badge ${n ? 'warn' : 'ok'}`;
      applyBtn.disabled = n === 0;
      restoreBtn.classList.toggle('danger', false);
    }

    kb.opts.onKeyClick = (slot) => selectSlot(slot);

    function selectSlot(slot) {
      if (state.layer === 'fn' && !state.fnReliable) {
        ctx.toast('2.4G 下 FN 层只读：请用 USB 连接后再编辑', { type: 'warn' });
        return;
      }
      if (state.layer === 'fn' && FN_DISABLED_SLOTS.has(slot)) {
        ctx.toast('官方 FN 层不允许修改 F1–F12（fnDisabledKeyIds）', { type: 'warn' });
        return;
      }
      state.selected = slot;
      kb.clearSelected();
      kb.setSelected(slot, true);
      renderCurrentKeyCard();
      buildPicker();
    }

    /* ---------------- 当前按键卡片 ---------------- */
    function renderCurrentKeyCard() {
      currentCard.innerHTML = '';
      if (state.selected === null) {
        currentCard.append(h('div', { class: 'empty', style: { padding: '28px 10px' } },
          h('div', { html: icon('target', { size: 26 }) }),
          h('div', {}, t('keymap.selectKey')),
        ));
        return;
      }
      const slot = state.selected;
      const meta = ALL_KEYS.find((k) => k.slot === slot);
      const act = effectiveAction(state.layer, slot);
      const bytes = encodeAction(act);
      const label = actionLabel(act);
      const isDefault = !act || act.type === 'default';

      currentCard.append(
        h('div', { class: 'current-key-card' },
          h('div', { class: 'cap' }, meta?.name || String(slot)),
          h('div', { class: 'arrows', html: icon('arrow-right', { size: 16 }) }),
          h('div', { class: 'target' },
            h('div', { class: 't1' }, isDefault ? '出厂默认' : label),
            h('div', { class: 't2' }, `槽位 ${slot} · ${state.layer === 'fn' ? 'FN 层' : '主层'} · HID ${meta?.keyCode ?? '—'}`),
          ),
        ),
        h('div', { class: 'row between mt-12' },
          h('div', { class: 'byte-preview' },
            h('span', {}, '4B'),
            ...bytes.map((b) => h('span', { class: 'byte' }, hex2(b))),
          ),
          h('div', { class: 'row' },
            h('button', {
              class: 'btn sm ghost', title: '恢复此键为默认',
              html: `${icon('undo', { size: 13 })}<span>此键默认</span>`,
              onclick: () => setKeyAction(slot, { type: 'default' }),
            }),
          ),
        ),
        h('div', { class: 'tiny muted mt-8' }, '4 字节编码按官方 pX 规则实时计算（写入时由后端编码）。'),
      );
    }

    /* ---------------- 设置动作 ---------------- */
    function setKeyAction(slot, action) {
      state.pending[state.layer][String(slot)] = action;
      renderKeyboard();
      renderCurrentKeyCard();
      buildPicker();
      kb.keyNode(slot)?.classList.add('kb-flash');
      setTimeout(() => kb.keyNode(slot)?.classList.remove('kb-flash'), 320);
    }

    /* ---------------- 应用 / 恢复 ---------------- */
    async function applyChanges() {
      const layers = Object.entries(state.pending).filter(([, m]) => Object.keys(m).length);
      if (!layers.length) return;
      applyBtn.disabled = true;
      try {
        for (const [layer, slots] of layers) {
          const wireSlots = Object.fromEntries(Object.entries(slots).map(([k, v]) => [k, toWireAction(v)]));
          await api.put(`/api/keymap/${layer}`, { slots: wireSlots });
          Object.assign(state.maps[layer], slots);
          state.pending[layer] = {};
        }
        renderKeyboard();
        renderCurrentKeyCard();
        ctx.toastSuccess('键位已写入设备');
      } catch (e) {
        ctx.toastError(`写入失败：${e.message || e}`);
      } finally {
        updatePendingUI();
      }
    }

    async function restoreDefaults() {
      const layer = state.layer;
      const ok = await ctx.confirmDialog({
        title: `恢复${layer === 'fn' ? 'FN 层' : '主层'}出厂默认`,
        message: '将向设备写入 0 恢复该层的出厂默认键位矩阵，当前未保存的修改会丢失。',
        confirmText: '恢复默认',
      });
      if (!ok) return;
      try {
        await api.post('/api/keymap/restore', { layer });
        state.pending[layer] = {};
        try {
          const resp = await api.get('/api/keymap');
          if (resp) state.maps[layer] = { ...(resp[layer] || {}) };
        } catch { /* keep */ }
        kb.clearSelected();
        state.selected = null;
        renderKeyboard();
        renderCurrentKeyCard();
        ctx.toastSuccess('已恢复出厂默认键位');
      } catch (e) {
        ctx.toastError(`恢复失败：${e.message || e}`);
      }
    }

    /* ---------------- 动作选择器 ---------------- */
    const tabsEl = h('div', { class: 'tabs' });
    const tabContent = h('div');

    function buildTabs() {
      tabsEl.innerHTML = '';
      for (const tab of TAB_DEFS) {
        tabsEl.append(h('button', {
          type: 'button',
          class: state.tab === tab.id ? 'active' : '',
          onclick: () => { state.tab = tab.id; buildPicker(); },
        }, h('span', { html: icon(tab.icon, { size: 14 }) }), tab.label));
      }
    }

    function buildPicker() {
      buildTabs();
      pickerHost.innerHTML = '';
      pickerHost.append(tabsEl, tabContent);
      tabContent.innerHTML = '';
      const currentAction = state.selected !== null ? effectiveAction(state.layer, state.selected) : null;

      if (state.selected === null) {
        tabContent.append(h('div', { class: 'empty', style: { padding: '26px 10px' } },
          h('div', {}, '先在左侧键盘点选一个按键，再选择动作'),
        ));
        return;
      }

      switch (state.tab) {
        case 'keyboard': buildActionGrid(actionsCatalog.keyboard, currentAction, '此分类没有键盘按键'); break;
        case 'consumer': buildActionGrid(actionsCatalog.consumer, currentAction, '此分类没有多媒体动作'); break;
        case 'mouse': buildActionGrid(actionsCatalog.mouse, currentAction, '此分类没有鼠标动作'); break;
        case 'func': buildFuncGrid(currentAction); break;
        case 'macro': buildMacroPicker(currentAction); break;
        case 'combo': buildComboPicker(currentAction); break;
        case 'special': buildSpecialPicker(currentAction); break;
        default: break;
      }
    }

    function buildActionGrid(items, currentAction, emptyText) {
      const search = h('input', { class: 'input sm', placeholder: '搜索按键 / 名称…' });
      const list = h('div', { class: 'action-list' });
      const render = (kw = '') => {
        list.innerHTML = '';
        const k = kw.trim().toLowerCase();
        const filtered = items.filter((it) => {
          if (!k) return true;
          const nm = String(it.name || '').toLowerCase();
          const sub = it.usage !== undefined ? `0x${it.usage.toString(16)} ${it.usage}` : '';
          return nm.includes(k) || sub.includes(k);
        });
        if (!filtered.length) {
          list.append(h('div', { class: 'empty', style: { gridColumn: '1 / -1' } }, emptyText));
          return;
        }
        for (const it of filtered) {
          const active = isSameAction(currentAction, it);
          list.append(h('button', {
            type: 'button', class: `action-item${active ? ' active' : ''}`, title: it.name,
            onclick: () => setKeyAction(state.selected, { ...it }),
          },
            h('span', { class: 'ai-name' }, it.name),
            it.usage !== undefined ? h('span', { class: 'ai-sub' }, `0x${hex2(Math.min(255, it.usage))}`) : null,
          ));
        }
      };
      search.addEventListener('input', () => render(search.value));
      tabContent.append(h('div', { class: 'stack' }, h('div', { class: 'search-box' }, h('div', { html: icon('search', { size: 15 }) }), search), list));
      render('');
    }

    function buildFuncGrid(currentAction) {
      const search = h('input', { class: 'input sm', placeholder: '搜索功能动作（292 条固件功能）…' });
      const list = h('div', { class: 'action-list', style: { maxHeight: '300px' } });
      const official = actionsCatalog.func.filter((it) => MK87_FN_IDS.includes(Number(it.id)));
      const mkItem = (it) => {
        const active = isSameAction(currentAction, { type: 'fn', id: it.id, name: it.name });
        return h('button', {
          type: 'button', class: `action-item${active ? ' active' : ''}`, title: `${it.name} · FUNC id ${it.id}`,
          onclick: () => setKeyAction(state.selected, { type: 'fn', id: it.id, name: it.name }),
        },
          h('span', { class: 'ai-name' }, it.name),
          h('span', { class: 'ai-sub' }, `#${it.id}`),
        );
      };
      const render = (kw = '') => {
        list.innerHTML = '';
        const k = kw.trim().toLowerCase();
        if (!k) {
          list.append(h('div', { class: 'tiny muted', style: { gridColumn: '1 / -1', padding: '2px 4px 4px' } }, `MK87 官方「功能」页内置 ${official.length} 项（默认 FN 层动作）`));
          official.forEach((it) => list.append(mkItem(it)));
          list.append(h('div', { class: 'tiny muted', style: { gridColumn: '1 / -1', padding: '8px 4px 4px' } }, '其他固件 FUNC 功能（共 ' + actionsCatalog.func.length + ' 条，真机行为未逐一验证）'));
          return;
        }
        const filtered = actionsCatalog.func.filter((it) => String(it.name).toLowerCase().includes(k) || String(it.id).includes(k));
        if (!filtered.length) {
          list.append(h('div', { class: 'empty', style: { gridColumn: '1 / -1' } }, '没有匹配的功能动作'));
          return;
        }
        filtered.slice(0, 140).forEach((it) => list.append(mkItem(it)));
        if (filtered.length > 140) list.append(h('div', { class: 'tiny muted', style: { gridColumn: '1 / -1', padding: '8px' } }, `仅显示前 140 条，继续输入关键词筛选（共 ${filtered.length} 条）`));
      };
      search.addEventListener('input', () => render(search.value));
      tabContent.append(h('div', { class: 'stack' },
        h('div', { class: 'search-box' }, h('div', { html: icon('search', { size: 15 }) }), search),
        h('div', { class: 'tiny muted' }, 'FUNC(13) 页 · 24 位固件功能 id；MK87 frameVersion=0，不使用 FUNC_V2。'),
        list,
      ));
      render('');
    }

    function buildMacroPicker(currentAction) {
      // /api/keymap/actions 的宏只有 {slot,offset}，动作数/详情走 /api/macros
      const detailBySlot = new Map(state.macrosDetail.map((m) => [Number(m.slot), m]));
      const macros = (state.macrosDetail.length ? state.macrosDetail : (actionsCatalog.macros || []))
        .map((m) => ({ slot: Number(m.slot), name: m.name || `宏 ${Number(m.slot) + 1}`, actions: (detailBySlot.get(Number(m.slot))?.actions || m.actions || []).length, bytes: (detailBySlot.get(Number(m.slot))?.actions || m.actions || []).length * 4 + 4 }));
      if (!macros.length) {
        tabContent.append(h('div', { class: 'empty' }, h('div', { html: icon('macro', { size: 26 }) }), h('div', {}, '还没有已使用的宏槽位'), h('div', { class: 'tiny' }, '先到「宏 / 快捷指令」页创建并保存宏')));
        return;
      }
      const repeatSeg = createSegmented({
        options: [{ value: 0, label: '常规' }, { value: 1, label: '重复 N 次' }, { value: 2, label: '再按结束' }],
        value: state.macroMask, small: true,
        onChange: (v) => { state.macroMask = v; countWrap.style.display = v === 1 ? '' : 'none'; },
      });
      const countInput = h('input', { class: 'input sm', type: 'number', min: '1', max: '255', value: String(state.macroCount), style: { width: '80px' } });
      countInput.addEventListener('input', () => { state.macroCount = clamp(parseInt(countInput.value, 10) || 1, 1, 255); });
      const countWrap = h('div', { class: 'row', style: { display: state.macroMask === 1 ? '' : 'none' } },
        h('span', { class: 'tiny muted' }, '重复次数（param3）'), countInput);

      const list = h('div', { class: 'action-list' });
      for (const m of macros) {
        const active = currentAction?.type === 'macro' && Number(currentAction.slot) === Number(m.slot);
        list.append(h('button', {
          type: 'button', class: `action-item${active ? ' active' : ''}`,
          onclick: () => setKeyAction(state.selected, {
            type: 'macro', slot: Number(m.slot), mask: state.macroMask,
            count: state.macroMask === 1 ? state.macroCount : 0,
            name: m.name || `宏 ${m.slot}`,
          }),
        },
          h('span', { class: 'ai-name' }, m.name || `宏 ${m.slot}`),
          h('span', { class: 'ai-sub' }, `#${m.slot} · ${m.actions ?? '?'} 动作`),
        ));
      }
      tabContent.append(h('div', { class: 'stack' },
        h('div', { class: 'field' }, h('div', { class: 'field-label' }, '触发方式（param2 / mask）'), repeatSeg.el),
        countWrap,
        h('div', { class: 'tiny muted' }, '官方编码：06 macroId param2 param3，param2=0 常规 / 1 重复 N 次 / 2 再按结束；param3 仅 param2=1 时有效。'),
        list,
      ));
    }

    function buildComboPicker(currentAction) {
      const modChips = MODIFIERS.map((m) => {
        const active = state.comboMods.includes(m.usage);
        const btn = h('button', {
          type: 'button', class: `mod-chip${active ? ' active' : ''}`,
          onclick: () => {
            if (state.comboMods.includes(m.usage)) {
              state.comboMods = state.comboMods.filter((u) => u !== m.usage);
            } else {
              state.comboMods = [...state.comboMods, m.usage].slice(-2);
            }
            buildPicker();
          },
        }, m.label);
        return btn;
      });

      const keyOptions = actionsCatalog.keyboard
        .filter((it) => !MODIFIER_USAGES.has(it.usage))
        .map((it) => ({ usage: it.usage, name: it.name }));
      const select = h('select', { class: 'select' },
        h('option', { value: '' }, '选择主键…'),
        ...keyOptions.map((it) => h('option', { value: String(it.usage), selected: state.comboKey === it.usage }, `${it.name}（HID ${it.usage}）`)),
      );
      select.addEventListener('change', () => { state.comboKey = select.value ? Number(select.value) : null; });

      const preview = h('div', { class: 'row' },
        ...state.comboMods.map((u) => h('span', { class: 'mod-chip active' }, HID_NAMES[String(u)] || `0x${hex2(u)}`)),
        h('span', { class: 'mod-chip' }, state.comboKey ? (HID_NAMES[String(state.comboKey)] || `0x${hex2(state.comboKey)}`) : '主键'),
      );

      tabContent.append(h('div', { class: 'combo-builder' },
        h('div', { class: 'field' }, h('div', { class: 'field-label' }, '修饰键（最多 2 个，param1/param2）'), h('div', { class: 'mod-chips' }, ...modChips)),
        h('div', { class: 'field' }, h('div', { class: 'field-label' }, '主键（param3）'), select),
        h('div', { class: 'field' }, h('div', { class: 'field-label' }, '预览'), preview),
        h('button', {
          class: 'btn primary', html: `${icon('check', { size: 15 })}<span>使用此组合键</span>`,
          disabled: !(state.comboMods.length && state.comboKey),
          onclick: () => setKeyAction(state.selected, { type: 'combo', keys: [...state.comboMods, state.comboKey] }),
        }),
        h('div', { class: 'tiny muted' }, '官方要求：至少 1 个修饰键 + 恰好 1 个主键；更多按键请使用宏。'),
      ));
    }

    function buildSpecialPicker(currentAction) {
      const items = [
        { label: '使用出厂默认', desc: '写入 0x00000000，恢复该键出厂行为', action: { type: 'default' }, icon: 'undo' },
        { label: '禁用此键', desc: '绑定官方 ⊠（HID 0x6F → 02 00 6F 00）；设备是否真屏蔽按键尚未真机验证', action: { type: 'disabled' }, icon: 'shield' },
      ];
      for (const it of items) {
        const active = isSameAction(currentAction, it.action);
        tabContent.append(h('button', {
          type: 'button', class: `action-item${active ? ' active' : ''}`, style: { padding: '12px', marginBottom: '8px', width: '100%' },
          onclick: () => setKeyAction(state.selected, { ...it.action }),
        },
          h('span', { html: icon(it.icon, { size: 16 }) }),
          h('span', { class: 'stack', style: { gap: '2px' } },
            h('span', { class: 'ai-name' }, it.label),
            h('span', { class: 'tiny muted' }, it.desc),
          ),
        ));
      }
    }

    /* ---------------- 初始化 ---------------- */
    updateFnWarning();
    renderKeyboard();
    renderCurrentKeyCard();
    buildPicker();
    kb.refreshSize();
    const ro = new ResizeObserver(() => kb.refreshSize());
    ro.observe(leftCard);

    return () => {
      ro.disconnect();
      kb.destroy();
    };
  },
};
