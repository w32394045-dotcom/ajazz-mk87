/* pages/macro.js — 宏 / 快捷指令：100 槽位、录制、动作编辑、重复模式绑定、3072B 空间预算
   后端契约（spec-keymap.md §6 / design.md §4.4）：
   GET  /api/macros  → {capacity, used, slots:[{slot, actions:[{delay, usage, press, type}]}]}
   PUT  /api/macros  → {slots:[{slot, actions:[...]}]}（整表两次 SET_MACRO）
   宏绑定在改键 4B 编码里：{type:'macro', slot, mask, count}，mask=0 常规 / 1 重复 N 次 / 2 再按结束 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { ACTIONS, HID_NAMES } from '../data/actions.js';
import { icon } from '../icons.js';
import { h, clamp, codeToHidUsage, hex2 } from '../util.js';
import { badge } from '../components/widgets.js';

const SLOT_COUNT = 100;
const CAPACITY = 3072;
const DIR_ENTRY_BYTES = 400; // 400B 目录 → 数据区 2672B（spec-keymap.md §6.5）
const KEY_OPTIONS = ACTIONS.keyboard;
const MOUSE_OPTIONS = ACTIONS.mouse;
const ALL_KEYS = KEY_LAYOUT.rows.flat();

function macroBlockBytes(actions) {
  return actions && actions.length ? 4 + actions.length * 4 : 0;
}
function totalDataBytes(slots) {
  return slots.reduce((sum, m) => sum + macroBlockBytes(m.actions), 0);
}
function actionLabel(a) {
  if (!a) return '—';
  if (a.type === 'mouse') {
    const m = MOUSE_OPTIONS.find((x) => Number(x.button) === Number(a.usage));
    return m ? m.name : `鼠标 ${a.usage}`;
  }
  return HID_NAMES[String(a.usage)] || (a.usage === 0x6f ? '⊠' : `HID 0x${hex2(a.usage || 0)}`);
}

export default {
  id: 'macro',
  async mount(root, ctx) {
    const { api, t } = ctx;

    /* ---------------- 数据 ---------------- */
    let capacity = CAPACITY;
    let usedFromDevice = 0;
    let slots = Array.from({ length: SLOT_COUNT }, (_, i) => ({ slot: i, actions: [] }));
    try {
      const resp = await api.get('/api/macros');
      if (resp) {
        capacity = Number(resp.capacity) || CAPACITY;
        usedFromDevice = Number(resp.used) || 0;
        const bySlot = new Map((resp.slots || []).map((m) => [Number(m.slot), m.actions || []]));
        slots = Array.from({ length: SLOT_COUNT }, (_, i) => ({
          slot: i,
          actions: (bySlot.get(i) || []).map((a) => ({
            delay: Number(a.delay) || 0,
            usage: Number(a.usage ?? a.keyCode ?? 0),
            press: a.press !== false,
            type: a.type === 'mouse' ? 'mouse' : 'keyboard',
          })),
        }));
      }
    } catch (e) {
      console.warn('[macro] 读取失败', e);
      ctx.toastError(`读取宏表失败：${e.message || e}`);
    }
    let baseSlots = JSON.parse(JSON.stringify(slots));
    let currentSlot = slots.findIndex((m) => m.actions.length) >= 0 ? slots.findIndex((m) => m.actions.length) : 0;
    let dirty = false;
    let recording = false;
    let recordTimer = null;
    let lastRecordTs = 0;
    let keymapNormal = {};
    try {
      const km = await api.get('/api/keymap');
      keymapNormal = km?.normal || {};
    } catch { /* ignore */ }

    /* ---------------- 工具 ---------------- */
    function markDirty() {
      dirty = true;
      saveBadge.textContent = '未保存';
      saveBadge.className = 'badge warn';
      updateBudget();
    }
    function markClean() {
      dirty = false;
      saveBadge.textContent = '已同步';
      saveBadge.className = 'badge ok';
    }

    /* ---------------- 布局骨架 ---------------- */
    const saveBadge = badge('已同步', 'ok');
    const slotGrid = h('div', { class: 'macro-slots' });
    const budgetBar = h('div', { class: 'progress-bar' }, h('i'));
    const budgetCard = h('div', { class: 'stack' },
      h('div', { class: 'budget-meta' },
        h('span', {}, '宏空间（含 400B 目录）'),
        h('span', {}, h('strong', {}, '0'), ` / ${capacity} B`),
      ),
      budgetBar,
      h('div', { class: 'tiny muted' }, `设备上报 ${capacity} B；扣掉 400 B 目录后数据区约 ${capacity - DIR_ENTRY_BYTES} B。每个非空宏 = 4B 块头 + 每动作 4B。`),
    );

    /* 编辑器 */
    const slotTitle = h('div', { class: 'card-title' }, '宏 #1');
    const slotSub = h('div', { class: 'card-desc' }, '选择一个槽位开始编辑');
    const actionList = h('div', { class: 'action-table' });
    const editorEmpty = h('div', { class: 'empty' },
      h('div', { html: icon('macro', { size: 26 }) }),
      h('div', {}, '选择或新建一个宏槽位'),
      h('div', { class: 'tiny' }, '新建宏后可以手动添加动作，或用浏览器录制键盘输入'),
    );
    const editorBody = h('div', { class: 'stack' });
    const recordBtn = h('button', { class: 'btn', html: `${icon('target', { size: 15 })}<span>开始录制</span>` });
    const addKeyBtn = h('button', { class: 'btn sm soft', html: `${icon('plus', { size: 14 })}<span>键盘动作</span>` });
    const addMouseBtn = h('button', { class: 'btn sm soft', html: `${icon('plus', { size: 14 })}<span>鼠标动作</span>` });
    const clearSlotBtn = h('button', { class: 'btn sm danger', html: `${icon('trash', { size: 14 })}<span>清空此槽</span>` });
    const copySlotBtn = h('button', { class: 'btn sm', html: `${icon('copy', { size: 14 })}<span>复制</span>` });
    const pasteSlotBtn = h('button', { class: 'btn sm', html: `${icon('save', { size: 14 })}<span>粘贴</span>`, disabled: true });
    let clipboardActions = null;
    const saveBtn = h('button', { class: 'btn primary', html: `${icon('save', { size: 15 })}<span>保存全部宏</span>` });

    /* 绑定到按键 */
    const bindKeySelect = h('select', { class: 'select' },
      h('option', { value: '' }, '选择要绑定的按键…'),
      ...ALL_KEYS.map((k) => h('option', { value: String(k.slot) }, `${k.name}（槽位 ${k.slot}）`)),
    );
    const bindMaskSelect = h('select', { class: 'select' },
      h('option', { value: '0' }, '0 · 常规（按一次播放一遍）'),
      h('option', { value: '1' }, '1 · 重复 N 次'),
      h('option', { value: '2' }, '2 · 再按一次结束'),
    );
    const bindCountInput = h('input', { class: 'input sm', type: 'number', min: '1', max: '255', value: '1', style: { width: '86px' } });
    const bindCountWrap = h('div', { class: 'row', style: { display: 'none' } }, h('span', { class: 'tiny muted' }, 'param3 次数'), bindCountInput);
    bindMaskSelect.addEventListener('change', () => { bindCountWrap.style.display = bindMaskSelect.value === '1' ? '' : 'none'; });
    const bindBtn = h('button', { class: 'btn sm soft', html: `${icon('link', { size: 14 })}<span>写入按键绑定</span>` });
    const bindCard = h('div', { class: 'stack' },
      h('div', { class: 'field' }, h('div', { class: 'field-label' }, '目标按键（主层）'), bindKeySelect),
      h('div', { class: 'field' }, h('div', { class: 'field-label' }, '触发方式（param2 / mask）'), bindMaskSelect),
      bindCountWrap,
      bindBtn,
      h('div', { class: 'tiny muted' }, '绑定走 PUT /api/keymap/normal，写入 4 字节 06 macroId mask param3。'),
    );

    /* ---------------- 槽位网格 ---------------- */
    function renderSlotGrid() {
      slotGrid.innerHTML = '';
      slots.forEach((m, i) => {
        const node = h('button', {
          type: 'button',
          class: `macro-slot${i === currentSlot ? ' active' : ''}${m.actions.length ? ' used' : ''}`,
          title: m.actions.length ? `${m.actions.length} 个动作 · ${macroBlockBytes(m.actions)} B` : '空槽',
          onclick: () => { if (recording) stopRecording(); currentSlot = i; renderSlotGrid(); renderEditor(); },
        },
          h('span', { class: 'n' }, String(i + 1)),
          h('span', { class: 'c' }, m.actions.length ? String(m.actions.length) : ''),
        );
        slotGrid.append(node);
      });
    }

    /* ---------------- 预算 ---------------- */
    function usedBytes() { return totalDataBytes(slots); }
    function updateBudget() {
      const used = usedBytes();
      const pct = clamp((used / capacity) * 100, 0, 100);
      budgetBar.style.setProperty('--pct', `${pct.toFixed(1)}%`);
      budgetCard.querySelector('.budget-meta').innerHTML = '';
      budgetCard.querySelector('.budget-meta').append(
        h('span', {}, '宏数据区使用量'),
        h('span', {}, h('strong', {}, String(used)), ` / ${capacity} B`),
      );
      budgetBar.classList.toggle('over', used > capacity - DIR_ENTRY_BYTES);
      if (used > capacity - DIR_ENTRY_BYTES) {
        budgetCard.querySelector('.progress-bar').style.setProperty('--pct', '100%');
      }
      saveBadge.textContent = dirty ? '未保存' : '已同步';
      saveBadge.className = `badge ${dirty ? 'warn' : 'ok'}`;
    }

    /* ---------------- 编辑器 ---------------- */
    function renderEditor() {
      const m = slots[currentSlot];
      slotTitle.textContent = `宏 #${currentSlot + 1}（slot ${currentSlot}）`;
      slotSub.textContent = m.actions.length
        ? `${m.actions.length} 个动作 · ${macroBlockBytes(m.actions)} B · ${m.actions.filter((a) => a.press).length} 次按下`
        : '空槽位：添加动作或直接录制';
      editorEmpty.style.display = m.actions.length ? 'none' : '';
      actionList.innerHTML = '';

      m.actions.forEach((a, idx) => {
        const typeSelect = h('select', { class: 'select' },
          h('option', { value: 'keyboard', selected: a.type !== 'mouse' }, '键盘'),
          h('option', { value: 'mouse', selected: a.type === 'mouse' }, '鼠标'),
        );
        const options = a.type === 'mouse' ? MOUSE_OPTIONS : KEY_OPTIONS;
        const actionSelect = h('select', { class: 'select' },
          ...options.map((it) => h('option', {
            value: String(a.type === 'mouse' ? it.button : it.usage),
            selected: Number(a.usage) === Number(a.type === 'mouse' ? it.button : it.usage),
          }, `${it.name}（${a.type === 'mouse' ? '值 ' : 'HID '}${a.type === 'mouse' ? it.button : it.usage}）`)),
        );
        const delayInput = h('input', { class: 'input', type: 'number', min: '0', max: '65535', value: String(a.delay) });
        const pressSelect = h('select', { class: 'select' },
          h('option', { value: 'down', selected: a.press }, '按下'),
          h('option', { value: 'up', selected: !a.press }, '抬起'),
        );
        const delBtn = h('button', { class: 'del', title: '删除此动作', html: icon('trash', { size: 14 }) });
        delBtn.addEventListener('click', () => { m.actions.splice(idx, 1); markDirty(); renderSlotGrid(); renderEditor(); });
        typeSelect.addEventListener('change', () => {
          a.type = typeSelect.value;
          a.usage = a.type === 'mouse' ? Number(MOUSE_OPTIONS[0].button) : Number(KEY_OPTIONS[0].usage);
          markDirty();
          renderEditor();
        });
        actionSelect.addEventListener('change', () => { a.usage = Number(actionSelect.value); markDirty(); renderEditor(); });
        delayInput.addEventListener('input', () => {
          a.delay = clamp(parseInt(delayInput.value, 10) || 0, 0, 65535);
          markDirty();
        });
        pressSelect.addEventListener('change', () => { a.press = pressSelect.value === 'down'; markDirty(); renderEditor(); });

        actionList.append(h('div', { class: 'action-row' },
          h('span', { class: 'idx' }, String(idx + 1)),
          h('div', { class: 'kind-tag', title: a.type === 'mouse' ? '鼠标动作' : '键盘动作' }, h('span', { class: 'mono', style: { fontSize: '14px' } }, a.type === 'mouse' ? '🖱' : '⌨')),
          delayInput,
          typeSelect,
          actionSelect,
          pressSelect,
          delBtn,
        ));
      });

      if (m.actions.length) {
        actionList.append(h('div', { class: 'tiny muted', style: { padding: '6px 4px' } },
          `每动作 4B：[delay u16 LE][usage][flags]，当前槽 ${macroBlockBytes(m.actions)} B。保存时除最后一条外的 delay 会按官方规则钳到 ≥5ms。`));
      }
    }

    /* ---------------- 录制 ---------------- */
    function setRecording(on) {
      recording = on;
      recordBtn.innerHTML = on
        ? `${icon('stop', { size: 15 })}<span>停止录制</span>`
        : `${icon('target', { size: 15 })}<span>开始录制</span>`;
      recordBtn.classList.toggle('danger', on);
      addKeyBtn.disabled = on;
      addMouseBtn.disabled = on;
      clearSlotBtn.disabled = on;
      if (on) {
        lastRecordTs = performance.now();
        ctx.toast('开始录制：在浏览器里按键，按下/抬起会记录为动作；再次点击停止', { timeout: 3000 });
      }
    }

    function stopRecording() {
      if (!recording) return;
      setRecording(false);
      markDirty();
      renderSlotGrid();
      renderEditor();
    }

    function onRecordKey(e) {
      const usage = codeToHidUsage(e.code);
      if (e.code === 'F24' || e.key === 'Process') return;
      if (usage === null || usage === undefined) {
        if (!e.repeat && (e.key.length === 1 || e.code.startsWith('F'))) {
          ctx.toast(`无法映射按键 ${e.code} 到 HID usage（已忽略）`, { type: 'warn', timeout: 2000 });
        }
        return;
      }
      e.preventDefault();
      if (e.repeat) return;
      const m = slots[currentSlot];
      const now = performance.now();
      const delay = clamp(Math.round(now - lastRecordTs), 0, 65535);
      lastRecordTs = now;
      const isDown = e.type === 'keydown';
      m.actions.push({ delay: isDown ? delay : 10, usage, press: isDown, type: 'keyboard' });
      if (m.actions.length > 600) { ctx.toastError('录制动作过多，已自动停止'); stopRecording(); return; }
      renderSlotGrid();
      renderEditor();
    }
    window.addEventListener('keydown', onRecordKey, true);
    window.addEventListener('keyup', onRecordKey, true);

    /* ---------------- 动作按钮 ---------------- */
    addKeyBtn.addEventListener('click', () => {
      const m = slots[currentSlot];
      m.actions.push({ delay: 10, usage: 4, press: true, type: 'keyboard' });
      m.actions.push({ delay: 10, usage: 4, press: false, type: 'keyboard' });
      markDirty(); renderSlotGrid(); renderEditor();
    });
    addMouseBtn.addEventListener('click', () => {
      const m = slots[currentSlot];
      m.actions.push({ delay: 10, usage: Number(MOUSE_OPTIONS[0].button), press: true, type: 'mouse' });
      m.actions.push({ delay: 10, usage: Number(MOUSE_OPTIONS[0].button), press: false, type: 'mouse' });
      markDirty(); renderSlotGrid(); renderEditor();
    });
    clearSlotBtn.addEventListener('click', async () => {
      const ok = await ctx.confirmDialog({ title: `清空宏 #${currentSlot + 1}`, message: '该槽位的全部动作会被删除（需点击保存后写入设备）。', confirmText: '清空' });
      if (!ok) return;
      slots[currentSlot].actions = [];
      markDirty(); renderSlotGrid(); renderEditor();
    });
    copySlotBtn.addEventListener('click', () => {
      clipboardActions = JSON.parse(JSON.stringify(slots[currentSlot].actions));
      pasteSlotBtn.disabled = false;
      ctx.toast('已复制此槽动作到剪贴板（浏览器内）');
    });
    pasteSlotBtn.addEventListener('click', async () => {
      if (!clipboardActions) return;
      if (slots[currentSlot].actions.length) {
        const ok = await ctx.confirmDialog({ title: '粘贴覆盖', message: `宏 #${currentSlot + 1} 已有 ${slots[currentSlot].actions.length} 个动作，粘贴会覆盖。`, confirmText: '覆盖粘贴' });
        if (!ok) return;
      }
      slots[currentSlot].actions = JSON.parse(JSON.stringify(clipboardActions));
      markDirty(); renderSlotGrid(); renderEditor();
    });
    recordBtn.addEventListener('click', () => { if (recording) stopRecording(); else setRecording(true); });

    /* 绑定到按键 */
    bindBtn.addEventListener('click', async () => {
      const slot = parseInt(bindKeySelect.value, 10);
      if (!slots[currentSlot].actions.length) { ctx.toastWarn('这个宏还是空的，请先添加或录制动作并保存'); return; }
      if (Number.isNaN(slot)) { ctx.toastWarn('请先选择目标按键'); return; }
      const mask = parseInt(bindMaskSelect.value, 10) || 0;
      const count = mask === 1 ? clamp(parseInt(bindCountInput.value, 10) || 1, 1, 255) : 0;
      const action = { type: 'macro', slot: currentSlot, mask, count, name: `宏 #${currentSlot + 1}` };
      try {
        await api.put('/api/keymap/normal', { slots: { [slot]: action } });
        ctx.toastSuccess(`已将 宏 #${currentSlot + 1} 绑定到槽位 ${slot}（mask=${mask}${mask === 1 ? `，次数=${count}` : ''}）`);
      } catch (e) {
        ctx.toastError(`绑定失败：${e.message || e}`);
      }
    });

    /* ---------------- 保存 ---------------- */
    saveBtn.addEventListener('click', async () => {
      if (recording) stopRecording();
      // 官方保存前把除最后一条外的 delay 钳到 ≥5ms（spec-keymap.md §6.7）
      const normalized = slots.map((m) => {
        const actions = m.actions.map((a, i) => ({
          delay: i < m.actions.length - 1 ? Math.max(5, clamp(Number(a.delay) || 0, 0, 65535)) : clamp(Number(a.delay) || 0, 0, 65535),
          usage: Number(a.usage) & 0xff,
          press: !!a.press,
          type: a.type === 'mouse' ? 'mouse' : 'keyboard',
        }));
        return { slot: m.slot, actions };
      });
      const used = normalized.reduce((sum, m) => sum + macroBlockBytes(m.actions), 0);
      if (used > capacity - DIR_ENTRY_BYTES) {
        ctx.toastError(`宏空间不足：需要 ${used} B，数据区上限约 ${capacity - DIR_ENTRY_BYTES} B`);
        return;
      }
      saveBtn.disabled = true;
      saveBtn.querySelector('span').textContent = '正在写入…';
      try {
        const resp = await api.put('/api/macros', { slots: normalized });
        slots = normalized;
        baseSlots = JSON.parse(JSON.stringify(slots));
        capacity = Number(resp?.capacity) || capacity;
        markClean();
        renderSlotGrid();
        renderEditor();
        updateBudget();
        ctx.toastSuccess(`已写入 ${normalized.filter((m) => m.actions.length).length} 个宏，共 ${used} B`);
      } catch (e) {
        ctx.toastError(`保存失败：${e.message || e}`);
      } finally {
        saveBtn.disabled = false;
        saveBtn.querySelector('span').textContent = '保存全部宏';
      }
    });

    /* ---------------- 页面布局 ---------------- */
    const slotCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '宏槽位（100）'),
          h('div', { class: 'card-desc' }, '点击选择；有动作的槽位右上角有标记')),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn sm primary', html: `${icon('plus', { size: 14 })}<span>新建</span>`,
          onclick: () => {
            const empty = slots.findIndex((m) => !m.actions.length);
            if (empty < 0) { ctx.toastWarn('100 个槽位都已使用'); return; }
            currentSlot = empty;
            slots[empty].actions = [];
            renderSlotGrid(); renderEditor();
            ctx.toast(`已定位到空槽位 #${empty + 1}`);
          },
        }),
      ),
      h('div', { class: 'card-body tight' }, budgetCard),
      h('div', { class: 'divider' }),
      slotGrid,
      h('div', { class: 'card-body tight' },
        h('div', { class: 'tiny muted' }, '已使用宏：'),
        h('div', { class: 'tiny', style: { marginTop: '4px', fontFamily: 'var(--mono)' } },
          slots.map((m, i) => m.actions.length ? `#${i + 1}` : null).filter(Boolean).join('  ') || '（无）'),
      ),
    );

    const editorCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, slotTitle, slotSub),
        h('div', { class: 'spacer' }),
        saveBadge,
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'row', style: { marginBottom: '12px' } },
          ...(recording ? [] : []),
          recordBtn, addKeyBtn, addMouseBtn,
          h('div', { class: 'spacer' }),
          copySlotBtn, pasteSlotBtn, clearSlotBtn,
        ),
        editorEmpty,
        actionList,
        h('div', { class: 'divider-dashed', style: { margin: '14px 0' } }),
        h('div', { class: 'row between' }, saveBtn, h('span', { class: 'tiny muted' }, '保存时会整表写入（两次 SET_MACRO：目录 400B + 数据区）')),
        editorBody,
        h('div', { class: 'section-title', style: { marginTop: '22px' } }, h('h2', {}, '绑定到按键')),
        bindCard,
        h('div', { class: 'section-title', style: { marginTop: '22px' } }, h('h2', {}, '说明')),
        h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
          h('p', {}, '· 宏名不在设备里，回读只能得到 M1..M100，名字由设备端占位；本工具按槽位号显示。'),
          h('p', {}, '· 每个动作 4B：delay(u16 LE) + HID usage + flags；键盘动作 actionType=3（按下 0xB0 / 抬起 0x30）。'),
          h('p', {}, '· 官方保存时除最后一条外的 delay 钳到 ≥5ms；宏数据区约 2672B（3072 − 400B 目录）。'),
          h('p', {}, '· 重复方式不在宏表里，而是写在「按键绑定」的 4B 编码中（06 macroId mask param3）。'),
        ),
      ),
    );

    root.append(h('div', { class: 'grid macro-layout' },
      h('div', { class: 'grid-stack' }, slotCard),
      editorCard,
    ));

    /* ---------------- 初始化 ---------------- */
    renderSlotGrid();
    renderEditor();
    updateBudget();

    return () => {
      window.removeEventListener('keydown', onRecordKey, true);
      window.removeEventListener('keyup', onRecordKey, true);
      if (recording) setRecording(false);
    };
  },
};
