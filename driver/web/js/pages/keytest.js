/* pages/keytest.js — 按键测试：按键高亮 + 三态计数 + 事件日志 + 统计
   注意（spec-tft-wireless.md §5）：厂商协议没有按键事件帧，后端用 OS 级捕获
   （Windows RawInput / Linux evdev）。因此只测「OS 收到的按键」：改键/宏后看到的是映射后的键值。 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { HID_NAMES } from '../data/actions.js';
import { icon } from '../icons.js';
import { h, clamp, fmtClock, codeToHidUsage, codeToLayoutSlot, hex2 } from '../util.js';
import { Keyboard } from '../components/keyboard.js';
import { badge } from '../components/widgets.js';

const ALL_KEYS = KEY_LAYOUT.rows.flat();
const SLOT_BY_USAGE = new Map(ALL_KEYS.filter((k) => Number.isFinite(k.keyCode)).map((k) => [k.keyCode, k.slot]));
const SLOT_BY_NAME = new Map(ALL_KEYS.map((k) => [String(k.name).toLowerCase(), k.slot]));
const SLOT_BY_CODE = new Map(ALL_KEYS.filter((k) => k.key).map((k) => [k.key, k.slot]));
const SCREEN_SLOTS = new Set(KEY_LAYOUT.notes.noLed); // 99/100/102：屏幕区，无物理按键
const LOG_LIMIT = 200;

export default {
  id: 'keytest',
  async mount(root, ctx) {
    const { api } = ctx;

    const state = {
      running: false,
      backend: '—',
      pressed: new Set(),
      counts: new Map(),
      log: [],
      totalDown: 0,
      totalUp: 0,
      maxSimultaneous: 0,
      mockLocal: ctx.isMock,
    };
    const offs = [];

    /* ---------------- 组件 ---------------- */
    const kb = new Keyboard({ interactive: false, legends: true, mode: 'keytest' });
    for (const slot of SCREEN_SLOTS) kb.setDisabled(slot, true);

    const runBadge = h('span', { class: 'badge' }, '未开始');
    const startBtn = h('button', { class: 'btn primary', html: `${icon('play', { size: 15 })}<span>开始测试</span>` });
    const stopBtn = h('button', { class: 'btn', html: `${icon('stop', { size: 15 })}<span>停止</span>`, disabled: true });
    const resetBtn = h('button', { class: 'btn sm ghost', html: `${icon('undo', { size: 14 })}<span>重置统计</span>` });

    const statValues = {};
    function statCard(key, label, unit = '') {
      const valueEl = h('div', { class: 'stat-value' }, '0', unit ? h('small', {}, unit) : null);
      statValues[key] = valueEl;
      return h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, label), valueEl);
    }
    const statsGrid = h('div', { class: 'stat-grid' },
      statCard('down', '按下次数'),
      statCard('up', '抬起次数'),
      statCard('keys', '已测试按键'),
      statCard('max', '同时按下峰值'),
    );
    const lastKeyText = h('div', { class: 'tiny muted' }, '等待按键事件…');

    const logBody = h('div', { class: 'log-body' });
    const logCount = h('span', { class: 'tiny muted' }, '0 条');

    function updateStats() {
      statValues.down.textContent = String(state.totalDown);
      statValues.up.textContent = String(state.totalUp);
      statValues.keys.textContent = String(state.counts.size);
      statValues.max.textContent = String(state.maxSimultaneous);
      lastKeyText.textContent = state.log.length
        ? `最近事件：${state.log[0].name} ${state.log[0].down ? '按下' : '抬起'} · ${fmtClock(state.log[0].ts)}`
        : '等待按键事件…';
    }

    function renderLog() {
      logBody.innerHTML = '';
      logCount.textContent = `${state.log.length} 条${state.log.length >= LOG_LIMIT ? '（仅保留最新 ' + LOG_LIMIT + ' 条）' : ''}`;
      for (const ev of state.log) {
        logBody.append(h('div', { class: 'log-line' },
          h('span', { class: 't' }, fmtClock(ev.ts)),
          h('span', { class: 'tag', style: { color: ev.down ? 'var(--accent-strong)' : 'var(--muted)' } }, ev.down ? 'DOWN' : 'UP  '),
          h('span', { style: { minWidth: '92px', display: 'inline-block' } }, ev.name || '—'),
          h('span', { style: { color: 'var(--muted)' } }, `slot ${ev.slot ?? '—'}`),
          h('span', { style: { marginLeft: 'auto', color: 'var(--muted-2)' } },
            [ev.vkey !== undefined ? `vkey 0x${ev.vkey.toString(16).toUpperCase()}` : null,
              ev.code ? `code ${ev.code}` : null,
              ev.hidUsage !== undefined ? `hid 0x${hex2(ev.hidUsage)}` : null].filter(Boolean).join(' · ')),
        ));
      }
      if (!state.log.length) {
        logBody.append(h('div', { class: 'empty', style: { padding: '30px 10px' } },
          h('div', {}, '还没有事件'),
          h('div', { class: 'tiny' }, state.running ? '现在按下键盘任意按键试试' : '点击「开始测试」后再按键'),
        ));
      }
    }

    function slotForEvent(ev) {
      if (ev.hidUsage !== undefined && SLOT_BY_USAGE.has(Number(ev.hidUsage))) return SLOT_BY_USAGE.get(Number(ev.hidUsage));
      if (ev.code && SLOT_BY_CODE.has(ev.code)) return SLOT_BY_CODE.get(ev.code);
      if (ev.name) {
        const key = String(ev.name).toLowerCase();
        if (SLOT_BY_NAME.has(key)) return SLOT_BY_NAME.get(key);
      }
      return null;
    }

    function handleEvent(ev) {
      if (!ev || typeof ev.down !== 'boolean') return;
      const slot = ev.slot !== undefined && ev.slot !== null ? Number(ev.slot) : slotForEvent(ev);
      const name = ev.name || (slot !== null ? ALL_KEYS.find((k) => k.slot === slot)?.name : undefined) || '未知按键';
      const entry = {
        ts: ev.ts ? (ev.ts > 1e12 ? ev.ts : ev.ts * 1000) : Date.now(),
        down: ev.down,
        name,
        slot: slot ?? null,
        vkey: ev.vkey,
        code: ev.code,
        // 后端 keyscan 事件字段叫 hid（HID usage），旧版前端只认 hidUsage → Alt/Win
        // 等修饰键会显示成「slot — / 未知」。这里统一映射，兼容两种形状。
        hidUsage: ev.hidUsage !== undefined ? ev.hidUsage : ev.hid,
      };
      state.log.unshift(entry);
      if (state.log.length > LOG_LIMIT) state.log.pop();

      if (ev.down) {
        state.totalDown += 1;
        if (slot !== null && !SCREEN_SLOTS.has(slot)) {
          state.pressed.add(slot);
          state.maxSimultaneous = Math.max(state.maxSimultaneous, state.pressed.size);
          state.counts.set(slot, (state.counts.get(slot) || 0) + 1);
          kb.setPressed(slot, true);
        }
      } else {
        state.totalUp += 1;
        if (slot !== null) {
          state.pressed.delete(slot);
          kb.setPressed(slot, false);
          if (!SCREEN_SLOTS.has(slot)) kb.setUsed(slot, true, state.counts.get(slot) || 0);
        }
      }
      updateStats();
      renderLog();
    }

    function resetStats() {
      state.pressed.clear();
      state.counts.clear();
      state.log = [];
      state.totalDown = 0;
      state.totalUp = 0;
      state.maxSimultaneous = 0;
      kb.clearPressed();
      for (const k of ALL_KEYS) if (!SCREEN_SLOTS.has(k.slot)) kb.setUsed(k.slot, false, 0);
      updateStats();
      renderLog();
      ctx.toast('统计已重置');
    }

    /* ---------------- 捕获控制 ---------------- */
    function setRunning(on) {
      state.running = on;
      runBadge.textContent = on ? '测试中' : '未开始';
      runBadge.className = `badge ${on ? 'ok' : ''}`;
      startBtn.disabled = on;
      stopBtn.disabled = !on;
      kb.deck.classList.toggle('interactive', on);
      renderLog();
    }

    async function start() {
      startBtn.disabled = true;
      try {
        const resp = await api.post('/api/keytest/start');
        setRunning(true);
        state.backend = ctx.isMock ? 'mock / 浏览器 keydown' : (resp?.backend || 'rawinput');
        backendBadge.textContent = state.backend;
        ctx.toast(ctx.isMock
          ? '演示模式：使用浏览器 keydown/keyup 模拟按键事件'
          : `已开始 OS 级按键捕获（${state.backend}）。请把焦点留在本页面。`, { timeout: 4000 });
      } catch (e) {
        ctx.toastError(`启动失败：${e.message || e}`);
        startBtn.disabled = false;
      }
    }
    async function stop() {
      try { await api.post('/api/keytest/stop'); } catch { /* ignore */ }
      setRunning(false);
      state.pressed.clear();
      kb.clearPressed();
      ctx.toast('已停止按键捕获');
    }
    startBtn.addEventListener('click', start);
    stopBtn.addEventListener('click', stop);
    resetBtn.addEventListener('click', resetStats);

    /* ---------------- 键盘 Win/Mac 模式检测 ----------------
       MK87 背面有 Win/Mac 拨动开关。固件在 Mac 模式下把 Win/Alt 互换，OS 侧看到的是
       「按物理 Win 键 → VK 0x12(Alt)」；Windows 模式下则是 VK 0x5B(Win)。
       这里只监听一次按键做判定，并把结果写进 settings.osMode，供改键页提醒复用。 */
    const detect = { active: false, timer: null, autoStarted: false };
    let osMode = '';
    let osModeAt = 0;
    const modeBadge = h('span', { class: 'badge' }, '未检测');
    const modeDesc = h('div', { class: 'tiny muted', style: { lineHeight: '1.7' } },
      '点「开始检测」后按一下键盘上印着 Win（⊞）的键，用 OS 实际收到的键值判断键盘处于 Windows 还是 Mac 模式。');
    const modeBtn = h('button', {
      class: 'btn primary',
      html: `${icon('keyboard', { size: 15 })}<span>开始检测</span>`,
      onclick: () => { beginModeDetect(); },
    });

    function renderOsMode() {
      if (osMode === 'windows') {
        modeBadge.className = 'badge ok';
        modeBadge.textContent = 'Windows 模式';
        modeDesc.textContent = '最近检测：按物理 Win 键得到 VK_0x5B（Win）→ 当前为 Windows 模式，Win/Alt 位置正常。'
          + (osModeAt ? ` 检测于 ${fmtClock(osModeAt * 1000)}。` : '');
      } else if (osMode === 'mac') {
        modeBadge.className = 'badge danger';
        modeBadge.textContent = 'Mac 模式（Win/Alt 互换）';
        modeDesc.textContent = '最近检测：按物理 Win 键得到 VK_0x12（Alt）→ 键盘处于 Mac 模式，Win 与 Alt 已互换。'
          + '把键盘背面 Win/Mac 拨动开关拨回 Windows，等键盘重新连接（会短暂断连）后重新检测即可。'
          + '此模式下改键仍然有效，只是按键位置与预期不同。'
          + (osModeAt ? ` 检测于 ${fmtClock(osModeAt * 1000)}。` : '');
      } else {
        modeBadge.className = 'badge';
        modeBadge.textContent = '未检测';
      }
    }

    async function beginModeDetect() {
      if (detect.active) return;
      detect.active = true;
      detect.autoStarted = false;
      modeBtn.disabled = true;
      modeBadge.className = 'badge';
      modeBadge.textContent = '检测中…';
      modeDesc.textContent = '请现在按一下键盘上印着 Win（⊞）的键（10 秒内有效；按其他键会继续等）…';
      if (!state.running) {
        detect.autoStarted = true;
        await start();
      }
      detect.timer = setTimeout(() => { finishModeDetect(null); }, 10000);
    }

    function finishModeDetect(mode) {
      if (!detect.active) return;
      detect.active = false;
      if (detect.timer) {
        clearTimeout(detect.timer);
        detect.timer = null;
      }
      modeBtn.disabled = false;
      if (detect.autoStarted) {
        detect.autoStarted = false;
        stop();
      }
      if (!mode) {
        modeBadge.className = 'badge';
        modeBadge.textContent = '未收到按键';
        modeDesc.textContent = '10 秒内没有收到 Win 键：请确认键盘已连接后重试。'
          + '（也可以先点「开始测试」，确认页面能看到按键事件。）';
        return;
      }
      osMode = mode;
      osModeAt = Math.floor(Date.now() / 1000);
      renderOsMode();
      api.put('/api/settings', { osMode, osModeCheckedAt: osModeAt }).catch(() => {});
      ctx.toast(mode === 'windows'
        ? '检测完成：Windows 模式（Win/Alt 正常）'
        : '检测到 Mac 模式：Win/Alt 已互换，请把键盘背面开关拨回 Windows', { timeout: 6000 });
    }

    function onModeDetectEvent(ev) {
      if (!detect.active || !ev || typeof ev.down !== 'boolean' || !ev.down) return;
      const vk = Number(ev.vkey);
      const name = String(ev.name || '');
      if (vk === 0x5B) { finishModeDetect('windows'); return; }
      if (vk === 0x12) { finishModeDetect('mac'); return; }
      // 其它键：提示继续按 Win，不结束检测
      if (name) modeDesc.textContent = `收到「${name}」，请继续按键盘上印着 Win（⊞）的那个键…`;
    }

    /* 浏览器事件（mock 模式 / 或后端未提供 keyevent 时兜底） */
    function onKey(e, down) {
      if (!state.running || !ctx.isMock) return;
      if (e.repeat) return;
      const slot = codeToLayoutSlot(e.code);
      if (slot === null) return;
      e.preventDefault();
      if (down && detect.active) onModeDetectEvent({ down, vkey: e.keyCode, name: ALL_KEYS.find((k) => k.slot === slot)?.name });
      handleEvent({ down, name: ALL_KEYS.find((k) => k.slot === slot)?.name, slot, vkey: e.keyCode, code: e.code, hidUsage: codeToHidUsage(e.code), ts: Date.now() });
    }
    const onDown = (e) => onKey(e, true);
    const onUp = (e) => onKey(e, false);
    const onBlur = () => { state.pressed.clear(); kb.clearPressed(); };
    window.addEventListener('keydown', onDown, true);
    window.addEventListener('keyup', onUp, true);
    window.addEventListener('blur', onBlur);

    /* 后端 WS 事件 */
    offs.push(api.on('ws:keyevent', (d) => {
      if (!state.running || ctx.isMock) return;
      if (detect.active) onModeDetectEvent(d);
      handleEvent(d);
    }));

    /* ---------------- 布局 ---------------- */
    const backendBadge = h('span', { class: 'badge' }, '—');

    const modeCard = h('section', { class: 'card', style: { marginBottom: '16px' } },
      h('div', { class: 'card-head' },
        h('div', {},
          h('div', { class: 'card-title' }, '键盘模式检测（Windows / Mac）'),
          h('div', { class: 'card-desc' },
            'MK87 背面有 Win/Mac 拨动开关；切到 Mac 时 Win 与 Alt 互换，很多「按键错位」其实只是模式不对')),
        h('div', { class: 'spacer' }),
        modeBadge,
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'row', style: { marginBottom: '10px', gap: '10px', alignItems: 'center' } },
          modeBtn,
          h('span', { class: 'tiny muted' }, '检测只读：仅监听一次按键，不会修改键盘设置'),
        ),
        modeDesc,
      ),
    );

    const kbCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '按键测试（87 键）'),
          h('div', { class: 'card-desc' }, '深色 = 正在按住 · 淡色 = 已按过 · 角标 = 该键按下次数')),
        h('div', { class: 'spacer' }),
        runBadge,
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'row between', style: { marginBottom: '12px' } },
          h('div', { class: 'row' }, startBtn, stopBtn, resetBtn),
          h('div', { class: 'row' }, h('span', { class: 'tiny muted' }, '捕获后端'), backendBadge),
        ),
        kb.deck,
        h('div', { class: 'kb-legend mt-12' },
          h('span', { class: 'item' }, badge('按住', 'accent')),
          h('span', { class: 'item' }, badge('已按', '')),
          h('span', { class: 'item' }, '角标 = 按键次数'),
          h('span', { class: 'item' }, 'Print / Scroll / Pause 为屏幕区，无物理按键'),
        ),
        lastKeyText,
      ),
    );

    const statsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '统计')),
        h('div', { class: 'spacer' }),
      ),
      h('div', { class: 'card-body' }, statsGrid),
    );

    const logCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '事件日志'),
          h('div', { class: 'card-desc' }, '按下 / 抬起逐条记录（含时间、槽位、扫描码）')),
        h('div', { class: 'spacer' }),
        logCount,
      ),
      h('div', { class: 'card-body', style: { padding: '0' } },
        h('div', { class: 'log-panel event-log', style: { border: '0', borderRadius: '0 0 16px 16px' } },
          h('div', { class: 'log-head' }, 'TIME / EVENT / KEY / SLOT / CODE'),
          logBody,
        ),
      ),
    );

    const noteCard = h('section', { class: 'card' },
      h('div', { class: 'card-body' },
        h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
          h('p', {}, '· 厂商 HID 协议没有按键事件帧（穷举 6 个 0x55 消费点均无），后端改用 Windows RawInput / Linux evdev 捕获 OS 收到的按键。'),
          h('p', {}, '· 因此这里只反映「映射之后」的键值：如果你把某键改成了多媒体键或宏，测到的会是映射后的 usage。'),
          h('p', {}, '· Windows 下请保持本页面在前台；点击开始后按任意键即可看到高亮与日志。'),
        ),
      ),
    );

    root.append(modeCard, h('div', { class: 'grid keytest-layout' },
      h('div', { class: 'grid-stack' }, kbCard, noteCard),
      h('div', { class: 'grid-stack' }, statsCard, logCard),
    ));

    /* 读取已有状态 */
    try {
      const st = await api.get('/api/keytest/status');
      if (st) {
        state.backend = ctx.isMock ? 'mock / 浏览器 keydown' : (st.backend || '—');
        backendBadge.textContent = state.backend;
        if (st.running) setRunning(true);
        const history = Array.isArray(st.events) ? st.events : (Array.isArray(st.recent) ? st.recent : []);
        history.filter((ev) => ev && typeof ev.down === 'boolean').forEach((ev) => handleEvent(ev));
      }
    } catch { /* ignore */ }
    try {
      const s = await api.get('/api/settings');
      osMode = s?.osMode === 'windows' || s?.osMode === 'mac' ? s.osMode : '';
      osModeAt = Number(s?.osModeCheckedAt) || 0;
    } catch { /* ignore */ }
    renderOsMode();

    updateStats();
    renderLog();
    kb.refreshSize();
    const ro = new ResizeObserver(() => kb.refreshSize());
    ro.observe(kbCard);

    return () => {
      if (detect.timer) { clearTimeout(detect.timer); detect.timer = null; }
      detect.active = false;
      window.removeEventListener('keydown', onDown, true);
      window.removeEventListener('keyup', onUp, true);
      window.removeEventListener('blur', onBlur);
      offs.forEach((off) => off?.());
      ro.disconnect();
      kb.destroy();
    };
  },
};
