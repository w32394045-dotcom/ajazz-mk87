/* pages/keymap.js — 改键：主层 / FN 层，87 键点选 + 动作选择器 + 4 字节编码预览 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { ACTIONS, DEFAULT_KEYMAP, HID_NAMES } from '../data/actions.js';
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
      const repeat = Number(action.repeat) || 0;
      return [6, Number(action.slot) & 0xff, repeat, repeat === 1 ? clamp(Number(action.count) || 1, 1, 255) : 0];
    }
    case 'fn': {
      const id = Number(action.id) || 0;
      return [13, (id >> 16) & 0xff, (id >> 8) & 0xff, id & 0xff];
    }
    case 'disabled': return [2, 0, 0, 0]; // KEYBOARD + usage 0 = 不发送按键
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
      const rep = Number(action.repeat) || 0;
      const suffix = rep === 1 ? ` ×${action.count || 1}` : rep === 2 ? ' 再按结束' : '';
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
      macroRepeat: 0,
      macroCount: 1,
      comboMods: [],
      comboKey: null,
    };

    try {
      const resp = await api.get('/api/keymap');
      if (resp) {
        state.maps.normal = { ...(resp.normal || {}) };
        state.maps.fn = { ...(resp.fn || {}) };
      }
    } catch (e) {
      console.warn('[keymap] 读取键位失败，使用内置默认', e);
      state.maps.normal = { ...DEFAULT_KEYMAP.normal };
      state.maps.fn = { ...DEFAULT_KEYMAP.fn };
    }
    try {
      const resp = await api.get('/api/keymap/actions');
      if (resp) {
        actionsCatalog = {
          keyboard: resp.keyboard?.length ? resp.keyboard : ACTIONS.keyboard,
          consumer: resp.consumer?.length ? resp.consumer : ACTIONS.consumer,
          mouse: resp.mouse?.length ? resp.mouse : ACTIONS.mouse,
          func: resp.func?.length ? resp.func : ACTIONS.func,
          macros: resp.macros || [],
          pageTypes: resp.pageTypes || ACTIONS.pageTypes,
        };
      }
    } catch (e) { /* 使用内置目录 */ }

    /* ---------------- 组件骨架 ---------------- */
    const kb = new Keyboard({ interactive: true, legends: true, mode: 'layout' });
    const pendingBadge = badge('0 项未保存', 'ok');
    const layerSeg = createSegmented({
      options: [{ value: 'normal', label: t('keymap.layer.normal') }, { value: 'fn', label: 'FN 层' }],
      value: state.layer,
      onChange: (v) => { state.layer = v; renderKeyboard(); renderCurrentKeyCard(); buildPicker(); },
    });

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
      for (const k of ALL_KEYS) {
        kb.setBadge(k.slot, '');
        const off = state.layer === 'fn' && FN_DISABLED_SLOTS.has(k.slot);
        kb.setDisabled(k.slot, off);
        if (off) continue;
        const act = effectiveAction(state.layer, k.slot);
        if (!act) {
          if (state.layer === 'fn') kb.setBadge(k.slot, '未设', { kind: 'badge' });
          continue;
        }
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
          await api.put(`/api/keymap/${layer}`, { slots });
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
      const render = (kw = '') => {
        list.innerHTML = '';
        const k = kw.trim().toLowerCase();
        const filtered = actionsCatalog.func.filter((it) => !k || String(it.name).toLowerCase().includes(k) || String(it.id).includes(k));
        if (!filtered.length) {
          list.append(h('div', { class: 'empty', style: { gridColumn: '1 / -1' } }, '没有匹配的功能动作'));
          return;
        }
        for (const it of filtered.slice(0, 120)) {
          const active = isSameAction(currentAction, { type: 'fn', id: it.id, name: it.name });
          list.append(h('button', {
            type: 'button', class: `action-item${active ? ' active' : ''}`, title: `${it.name} · id ${it.id}`,
            onclick: () => setKeyAction(state.selected, { type: 'fn', id: it.id, name: it.name }),
          },
            h('span', { class: 'ai-name' }, it.name),
            h('span', { class: 'ai-sub' }, `#${it.id}`),
          ));
        }
        if (filtered.length > 120) list.append(h('div', { class: 'tiny muted', style: { gridColumn: '1 / -1', padding: '8px' } }, `仅显示前 120 条，输入关键词继续筛选（共 ${filtered.length} 条）`));
      };
      search.addEventListener('input', () => render(search.value));
      tabContent.append(h('div', { class: 'stack' },
        h('div', { class: 'search-box' }, h('div', { html: icon('search', { size: 15 }) }), search),
        h('div', { class: 'tiny muted' }, 'FUNC 页（24 位固件功能 id）。FN 层改键默认就是这一类动作。'),
        list,
      ));
      render('');
    }

    function buildMacroPicker(currentAction) {
      const macros = actionsCatalog.macros || [];
      if (!macros.length) {
        tabContent.append(h('div', { class: 'empty' }, h('div', { html: icon('macro', { size: 26 }) }), h('div', {}, '还没有已使用的宏槽位'), h('div', { class: 'tiny' }, '先到「宏 / 快捷指令」页创建并保存宏')));
        return;
      }
      const repeatSeg = createSegmented({
        options: [{ value: 0, label: '常规' }, { value: 1, label: '重复 N 次' }, { value: 2, label: '再按结束' }],
        value: state.macroRepeat, small: true,
        onChange: (v) => { state.macroRepeat = v; countWrap.style.display = v === 1 ? '' : 'none'; },
      });
      const countInput = h('input', { class: 'input sm', type: 'number', min: '1', max: '255', value: String(state.macroCount), style: { width: '80px' } });
      countInput.addEventListener('input', () => { state.macroCount = clamp(parseInt(countInput.value, 10) || 1, 1, 255); });
      const countWrap = h('div', { class: 'row', style: { display: state.macroRepeat === 1 ? '' : 'none' } },
        h('span', { class: 'tiny muted' }, '重复次数 param3'), countInput);

      const list = h('div', { class: 'action-list' });
      for (const m of macros) {
        const active = currentAction?.type === 'macro' && Number(currentAction.slot) === Number(m.slot);
        list.append(h('button', {
          type: 'button', class: `action-item${active ? ' active' : ''}`,
          onclick: () => setKeyAction(state.selected, {
            type: 'macro', slot: Number(m.slot), repeat: state.macroRepeat,
            count: state.macroRepeat === 1 ? state.macroCount : 0,
            name: m.name || `宏 ${m.slot}`,
          }),
        },
          h('span', { class: 'ai-name' }, m.name || `宏 ${m.slot}`),
          h('span', { class: 'ai-sub' }, `#${m.slot} · ${m.actions ?? '?'} 动作`),
        ));
      }
      tabContent.append(h('div', { class: 'stack' },
        h('div', { class: 'field' }, h('div', { class: 'field-label' }, '重复方式（param2）'), repeatSeg.el),
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
        { label: '禁用此键', desc: '写入 KEYBOARD usage 0，按键不再发送任何键值', action: { type: 'disabled' }, icon: 'shield' },
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
