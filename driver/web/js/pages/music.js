/* pages/music.js — 音乐律动（仅 USB）：两种方案
   * 当前方案：本工具参数（官方渲染器模式 13/14/17/4 + 灵敏度 + 帧率），键盘可视化为本地频谱动画
   * 官方方案：官方 v1 同款设置项（显示模式 21 种（含 100 屏光联动）/ 背景模式 11 种 / 背景亮度 / 振幅）
     + 本工具增强（LED 颜色覆盖、原生帧率 20/60/66，默认 66）；键盘可视化回放后端实发帧。
   两套参数表见 data/music.js（官方 v1 真值，来源 docs/music-v1-config.json +
   capture/official_music_colors3.jsonl 采样）；后端标注哪些 v1 模式已移植见 status.officialImplementedModes。
   引擎在 Python 后端（WASAPI loopback / PipeWire monitor → FFT → 逐键帧流 0x32）。
   仅 USB 支持：2.4G 下官方明确不支持（spec-lighting.md §4.6）。 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import {
  OFFICIAL_MUSIC_MODES, OFFICIAL_BACKGROUND_MODES, OFFICIAL_LIMITS,
  OFFICIAL_COLOR_SCHEMES, OFFICIAL_FRAME_RATES, OFFICIAL_DEFAULT_FRAME_RATE,
} from '../data/music.js';
import { icon } from '../icons.js';
import { h, clamp, store } from '../util.js';
import { Keyboard } from '../components/keyboard.js';
import { createSlider, createSegmented, createTabs, kvList } from '../components/widgets.js';

const BAND_COUNT = 32;
const KEYS = KEY_LAYOUT.rows.flat().map((k) => ({ slot: k.slot, col: clamp(Math.floor((k.x / 275) * BAND_COUNT), 0, BAND_COUNT - 1) }));
/** 当前方案默认模式（后端未返回时兜底） */
const DEFAULT_MODES = [
  { mode: 13, name: '律动节拍', nameEn: 'Dance to the Beat' },
  { mode: 14, name: '光尘螺旋', nameEn: 'Dust Glow Spiral' },
  { mode: 17, name: '萤火轨迹', nameEn: 'Firefly Trail' },
  { mode: 4, name: '曲率频谱', nameEn: 'Curvature Frequency Steps' },
];
/** 后端已移植的官方渲染器（21 项里除 100 屏光联动以外的 20 项；status.officialImplementedModes 可用时以它为准） */
const IMPLEMENTED_FALLBACK = [1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10, 14, 15, 16, 17, 18, 19, 20, 21, 22];
/** 已用官方采样逐项校验过的渲染器（14–22 为自研实现，不在其中） */
const VERIFIED_MODES = new Set([1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13]);

function hslToRgb(hue, s = 95, l = 55) {
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
  return rgb.map((v) => Math.round(clamp((v + m) * 255, 0, 255)));
}

export default {
  id: 'music',
  async mount(root, ctx) {
    const { api } = ctx;
    const LANG_EN = (document.documentElement.lang || 'zh').toLowerCase().startsWith('en');

    /* ---------------- 状态 ---------------- */
    let supported = ctx.status?.caps ? ctx.status.caps.music !== false : true;
    let devices = [];
    let selectedDevice = null;
    let running = false;
    let raf = null;
    let scheme = store.get('mk87.music.scheme', 'official');
    if (scheme !== 'official') scheme = 'current';

    /* 当前方案参数 */
    let mode = 13;
    let fps = 20;
    let statusModes = null;

    /* 官方方案参数（与官方 v1 插件 UI 一致） */
    let offMode = OFFICIAL_MUSIC_MODES[0].value;
    let offBackmode = 0;
    let offBackBright = OFFICIAL_LIMITS.backBrightness.default;
    let offAmplitude = OFFICIAL_LIMITS.amplitude.default;
    /* 本工具增强：LED 颜色覆盖 / 原生帧率（仅官方方案使用） */
    let offColor = 'default';
    let offFps = OFFICIAL_DEFAULT_FRAME_RATE;

    /* 后端实时状态 */
    let backendMode = null;        // 实际渲染模式（未移植的模式会回落到 13）
    let backendRequested = null;   // 请求的模式
    let backendFps = null;         // 后端回传的帧率（官方方案为实测值，可能是浮点）
    let measuredFps = null;        // 官方方案页面上显示的「实测」帧率；null → 显示 —
    let implementedModes = IMPLEMENTED_FALLBACK.slice();
    let officialColors = null;     // Map<slot, [r,g,b]> 后端最近一帧
    /* 引擎健康状态（后端自动恢复 / 等待设备） */
    let healthState = 'stopped';   // starting | ok | recovering | waiting-device | stopped
    let recoveries = 0;            // 后端自动恢复次数
    let lastRecovery = null;       // 最近一次恢复开始的 unix 时间戳
    let lastError = '';            // 后端最近错误（可能为空）
    let audioFallback = false;     // 原音频设备失效后是否回退到默认输出
    let frameAgeMs = null;         // 运行中距最后一帧成功下发的毫秒数
    let statusTimer = null;
    let levels = new Array(BAND_COUNT).fill(0);
    let targetLevels = new Array(BAND_COUNT).fill(0);
    const offs = [];

    /* ---------------- 数据 ---------------- */
    try {
      devices = await api.get('/api/music/devices') || [];
      if (!Array.isArray(devices)) devices = devices.devices || [];
      selectedDevice = (devices.find((d) => d.default) || devices.find((d) => d.active) || devices[0])?.id || 'default';
    } catch (e) { console.warn('[music] 设备列表失败', e); }
    try {
      const st = await api.get('/api/music/status');
      if (st) {
        running = !!st.running;
        if (st.supported === false) supported = false;
        if (st.deviceId) selectedDevice = st.deviceId;
        else if (st.device) selectedDevice = st.device;
        if (Array.isArray(st.modes) && st.modes.length) {
          statusModes = st.modes;
          mode = Number(st.mode || st.modes[0].mode || 13);
        }
        if (Array.isArray(st.officialImplementedModes) && st.officialImplementedModes.length) {
          implementedModes = st.officialImplementedModes.map(Number);
        } else if (Array.isArray(st.implementedModes) && st.implementedModes.length) {
          implementedModes = st.implementedModes.map(Number);
        }
        if (st.mode != null) backendMode = Number(st.mode);
        if (st.requestedMode != null) backendRequested = Number(st.requestedMode);
        if (st.fps != null) backendFps = Number(st.fps);
        if (running && st.fps != null) measuredFps = Number(st.fps);
        /* 健康状态回填：刷新 / 重开页面时与后端自动恢复状态一致 */
        if (typeof st.health === 'string') healthState = st.health;
        if (st.recoveries != null) recoveries = Number(st.recoveries) || 0;
        lastRecovery = st.lastRecovery != null ? Number(st.lastRecovery) : null;
        if (typeof st.lastError === 'string') lastError = st.lastError;
        if (typeof st.audioFallback === 'boolean') audioFallback = st.audioFallback;
        if (st.frameAgeMs != null) frameAgeMs = Number(st.frameAgeMs);
        // 官方参数回填（刷新页面 / 从别处启动时保持一致）
        if (st.amplitude != null) offAmplitude = Number(st.amplitude);
        if (st.backmode != null) offBackmode = Number(st.backmode);
        if (st.backmodeBrightness != null) offBackBright = Number(st.backmodeBrightness);
        /* 新增字段向后兼容：老后端没有 color/fps 时保持 default / 66 */
        if (typeof st.color === 'string' && OFFICIAL_COLOR_SCHEMES.some((c) => c.id === st.color)) {
          offColor = st.color;
        }
        /* 原生帧率：status.targetFps 是后端配置值（20/60/66）；status.fps 是实测值，不能用于回填 */
        if (OFFICIAL_FRAME_RATES.includes(Number(st.targetFps))) {
          offFps = Number(st.targetFps);
        }
        const req = st.requestedMode != null ? Number(st.requestedMode) : Number(st.mode);
        if (OFFICIAL_MUSIC_MODES.some((m) => m.value === req)) offMode = req;
        if (st.colors && typeof st.colors === 'object') officialColors = officialFrameMap(st.colors);
      }
    } catch { /* ignore */ }

    /* ---------------- 基础组件 ---------------- */
    const keyboard = new Keyboard({ interactive: false, legends: false, mode: 'lighting' });
    keyboard.deck.classList.add('kb-compact');

    const idleHint = h('div', { class: 'level-idle-hint' }, '开始律动后显示实时频谱');
    const levelBarWrap = h('div', { class: 'level-visual', style: { position: 'relative' } }, idleHint);
    const bars = [];
    for (let i = 0; i < BAND_COUNT; i++) {
      const bar = h('div', { class: 'level-bar', style: { height: '4%' } });
      bars.push(bar);
      levelBarWrap.append(bar);
    }
    const levelMeter = h('div', { class: 'meter' }, h('div', { class: 'meter-bar' }, h('i')));
    const meterValue = h('span', { class: 'mono tiny muted' }, '0.000');
    const statusBadge = h('span', { class: 'badge' }, '未开始');
    /* 自动恢复提示（start/stop 行下方）：文案随后端健康状态变化，非恢复场景隐藏 */
    const healthHintMain = h('span', {}, '');
    const healthHintFallback = h('span', {}, '');
    const healthHint = h('div', {
      class: 'tiny muted',
      style: { marginTop: '8px', display: 'none' },
    }, healthHintMain, healthHintFallback);
    const deviceList = h('div', { class: 'stack' });

    /* 徽章反映后端真实健康状态；样式使用 app.css 已有的 .badge.ok / .badge.warn */
    function applyHealthBadge() {
      if (!running) {
        statusBadge.textContent = '未开始';
        statusBadge.className = 'badge';
        return;
      }
      if (healthState === 'recovering') {
        statusBadge.textContent = '恢复中…';
        statusBadge.className = 'badge warn';
      } else if (healthState === 'waiting-device') {
        statusBadge.textContent = '等待键盘';
        statusBadge.className = 'badge warn';
      } else {
        statusBadge.textContent = '律动中';
        statusBadge.className = 'badge ok';
      }
    }

    /* 恢复提示：自动恢复次数 / 恢复中 / 等待键盘 / 音频回退 */
    function refreshHealthHint() {
      let main = '';
      if (running) {
        if (healthState === 'recovering') {
          main = '音频/键盘中断，正在自动恢复…';
        } else if (healthState === 'waiting-device') {
          main = '键盘已断开，等待重新连接后自动恢复律动';
        } else if (healthState === 'ok' && recoveries > 0) {
          const seconds = Number(lastRecovery);
          const when = Number.isFinite(seconds) && seconds > 0
            ? new Date(seconds * 1000).toLocaleTimeString()
            : '';
          main = when ? `已自动恢复 ${recoveries} 次（最近一次：${when}）` : `已自动恢复 ${recoveries} 次`;
        }
      }
      const fallbackNote = running && audioFallback ? '（原音频设备不可用，已回退默认输出）' : '';
      healthHintMain.textContent = main;
      healthHintFallback.textContent = fallbackNote;
      healthHint.style.display = (main || fallbackNote) ? '' : 'none';
    }

    /* ---------------- 当前方案控件 ---------------- */
    const modeLabel = (m) => (LANG_EN ? (m.nameEn || m.name) : (m.name || m.nameEn));
    const modeOptions = (statusModes || DEFAULT_MODES).map((m) => ({ value: Number(m.mode), label: modeLabel(m) }));
    const styleSeg = createSegmented({
      options: modeOptions,
      value: mode,
      small: true,
      onChange: (v) => { mode = Number(v); scheduleLiveUpdate(); },
    });
    const fpsSeg = createSegmented({
      options: [{ value: 15, label: '15' }, { value: 20, label: '20' }, { value: 30, label: '30' }],
      value: 20, small: true,
      onChange: (v) => { fps = v; scheduleLiveUpdate(); },
    });
    /* 灵敏度：后端 sensitivity 1.0 基准，滑块 10..100 → 0.2..2.0 */
    const sensSlider = createSlider({
      label: '灵敏度',
      min: 10, max: 100, step: 5, value: 50,
      format: (v) => `${(v / 50).toFixed(2)}×`,
      onInput: () => scheduleLiveUpdate(),
    });
    const currentParams = h('div', {},
      h('div', { class: 'field' }, h('div', { class: 'field-label' }, '模式'), styleSeg.el),
      h('div', { class: 'field', style: { marginTop: '12px' } },
        h('div', { class: 'field-label' }, '帧率（fps）'),
        h('div', { class: 'row' }, fpsSeg.el, h('span', { class: 'tiny muted' }, '实测 20fps 稳定'))),
      h('div', { style: { marginTop: '14px' } }, sensSlider.el),
    );

    /* ---------------- 官方方案控件（官方 v1 同款设置项 + 本工具增强） ---------------- */
    const offLabel = (o) => (LANG_EN ? o.en : o.zh);
    const implementedSet = () => new Set(implementedModes);
    const isPorted = (value) => implementedSet().has(Number(value));
    const colorById = (id) => OFFICIAL_COLOR_SCHEMES.find((c) => c.id === id) || OFFICIAL_COLOR_SCHEMES[0];
    const colorPreviewBackground = (id) => {
      const s = colorById(id);
      return s.colors.length ? `linear-gradient(90deg, ${s.colors.join(', ')})` : 'rgba(127,127,127,.28)';
    };

    const officialModeSelect = h('select', { class: 'select' });
    for (const m of OFFICIAL_MUSIC_MODES) {
      officialModeSelect.append(h('option', { value: String(m.value) }, offLabel(m)));
    }
    officialModeSelect.value = String(offMode);
    const officialModeHint = h('div', { class: 'field-hint' });
    function refreshOfficialModeHint() {
      const m = OFFICIAL_MUSIC_MODES.find((x) => x.value === Number(officialModeSelect.value));
      let text = '';
      if (m) {
        if (m.renderer === 'plugin') text = '屏光联动由官方 Music.exe 读取屏幕内容；本工具的自研屏幕同步待做，会回落到「随曲起舞」';
        else if (!isPorted(m.value)) text = '该模式渲染器尚未移植，会回落到「随曲起舞」';
        else if (!VERIFIED_MODES.has(Number(m.value))) text = '该模式渲染器已移植（自研实现，未做官方采样校验）';
        else text = '官方渲染器已移植（颜色/调色板已用官方采样校验）';
      }
      officialModeHint.textContent = text;
    }
    officialModeSelect.addEventListener('change', () => {
      offMode = Number(officialModeSelect.value);
      refreshOfficialModeHint();
      scheduleLiveUpdate();
    });

    const officialBgSelect = h('select', { class: 'select' });
    for (const b of OFFICIAL_BACKGROUND_MODES) {
      officialBgSelect.append(h('option', { value: String(b.value) }, offLabel(b)));
    }
    officialBgSelect.value = String(offBackmode);
    officialBgSelect.addEventListener('change', () => {
      offBackmode = Number(officialBgSelect.value);
      scheduleLiveUpdate();
    });

    const offBrightSlider = createSlider({
      label: '背景亮度', min: OFFICIAL_LIMITS.backBrightness.min, max: OFFICIAL_LIMITS.backBrightness.max,
      step: OFFICIAL_LIMITS.backBrightness.step, value: offBackBright, format: (v) => `${v}%`,
      onInput: (v) => { offBackBright = Number(v); scheduleLiveUpdate(); },
    });
    const offAmpSlider = createSlider({
      label: '振幅', min: OFFICIAL_LIMITS.amplitude.min, max: OFFICIAL_LIMITS.amplitude.max,
      step: 1, value: offAmplitude, format: (v) => String(v),
      onInput: (v) => { offAmplitude = Number(v); scheduleLiveUpdate(); },
    });

    /* LED 颜色覆盖（本工具增强；default = 不覆盖，与官方完全一致） */
    const officialColorSelect = h('select', { class: 'select' });
    for (const c of OFFICIAL_COLOR_SCHEMES) {
      officialColorSelect.append(h('option', { value: c.id }, offLabel(c)));
    }
    officialColorSelect.value = offColor;
    const colorPreview = h('div', {
      class: 'music-color-preview', 'aria-hidden': 'true',
      style: {
        height: '6px', borderRadius: '999px', marginTop: '8px',
        background: colorPreviewBackground(offColor),
        boxShadow: 'inset 0 0 0 1px rgba(127,127,127,.18)',
      },
    });
    const colorHint = h('div', { class: 'field-hint', style: { marginTop: '6px' } },
      'LED 颜色覆盖对全部动态多色模式生效（1/2/4/5/13 与补回的 14–22）；纯色模式 6/7/8/9/10/11 仍使用官方采样色。');
    officialColorSelect.addEventListener('change', () => {
      offColor = officialColorSelect.value;
      colorPreview.style.background = colorPreviewBackground(offColor);
      scheduleLiveUpdate();
    });

    /* 原生帧率（本工具增强；官方 v1 固定 20fps） */
    const officialFpsSeg = createSegmented({
      options: OFFICIAL_FRAME_RATES.map((v) => ({ value: v, label: String(v) })),
      value: offFps, small: true,
      onChange: (v) => { offFps = Number(v); scheduleLiveUpdate(); },
    });
    const fpsReadout = h('span', { class: 'mono tiny' }, '—');
    function updateFpsReadout() {
      fpsReadout.textContent = measuredFps == null || !Number.isFinite(Number(measuredFps))
        ? '—'
        : Number(measuredFps).toFixed(1);
    }
    const fpsReadoutRow = h('div', { class: 'row', style: { gap: '8px', marginTop: '6px', alignItems: 'baseline' } },
      h('span', { class: 'tiny muted' }, '实测帧率'),
      fpsReadout,
      h('span', { class: 'tiny muted' }, 'fps'),
    );
    const fpsHint = h('div', { class: 'field-hint', style: { marginTop: '6px' } },
      '自研增强：官方方案默认 66 fps（不是官方 UI 的设置项）');

    const officialParams = h('div', {},
      h('div', { class: 'field' },
        h('div', { class: 'field-label' }, '显示模式'), officialModeSelect, officialModeHint),
      h('div', { class: 'field', style: { marginTop: '12px' } },
        h('div', { class: 'field-label' }, '背景模式'), officialBgSelect),
      h('div', { style: { marginTop: '14px' } }, offBrightSlider.el),
      h('div', { style: { marginTop: '8px' } }, offAmpSlider.el),
      h('div', { class: 'field', style: { marginTop: '14px' } },
        h('div', { class: 'field-label' }, 'LED 颜色', h('span', { class: 'badge' }, '自研增强')),
        officialColorSelect, colorPreview, colorHint),
      h('div', { class: 'field', style: { marginTop: '12px' } },
        h('div', { class: 'field-label' }, '原生帧率', h('span', { class: 'badge' }, '自研增强')),
        officialFpsSeg.el, fpsReadoutRow, fpsHint),
      h('div', { class: 'tiny muted mt-12' },
        '官方 v1 设置项：显示模式 21 种（含屏光联动）/ 背景模式 11 种 / 背景亮度 / 振幅；LED 颜色与原生帧率为本工具增强'),
    );

    function syncOfficialControls() {
      officialModeSelect.value = String(offMode);
      officialBgSelect.value = String(offBackmode);
      offBrightSlider.set(offBackBright);
      offAmpSlider.set(offAmplitude);
      officialColorSelect.value = offColor;
      colorPreview.style.background = colorPreviewBackground(offColor);
      officialFpsSeg.set(offFps);
      updateFpsReadout();
      refreshOfficialModeHint();
    }

    /* ---------------- 热更新：运行中改参数不打断音乐 ---------------- */
    let liveTimer = null;
    function payloadForScheme() {
      if (scheme === 'official') {
        return {
          mode: offMode,
          backmode: offBackmode,
          backmodeBrightness: offBackBright,
          amplitude: offAmplitude,
          color: offColor,
          fps: offFps,
        };
      }
      return {
        mode,
        amplitude: Math.round(sensSlider.value),
        backmode: 0,
        backmodeBrightness: 100,
        fps,
      };
    }
    function applyStatus(st) {
      if (!st) return;
      if (st.mode != null) backendMode = Number(st.mode);
      if (st.requestedMode != null) backendRequested = Number(st.requestedMode);
      if (st.fps != null) {
        const v = Number(st.fps);
        if (Number.isFinite(v)) { backendFps = v; measuredFps = v; }
      }
      if (OFFICIAL_FRAME_RATES.includes(Number(st.targetFps))) offFps = Number(st.targetFps);
      if (Array.isArray(st.officialImplementedModes) && st.officialImplementedModes.length) {
        implementedModes = st.officialImplementedModes.map(Number);
      } else if (Array.isArray(st.implementedModes) && st.implementedModes.length) {
        implementedModes = st.implementedModes.map(Number);
      }
      if (st.colors && typeof st.colors === 'object') officialColors = officialFrameMap(st.colors);
      updateFpsReadout();
      refreshOfficialModeHint();
    }
    /* 状态轮询：完整同步后端状态（running / 健康 / 恢复次数 / 实测帧率）。
       后端停止（或放弃自动恢复）后前端如实切回未开始并提示原因，不再只同步 fps */
    async function pollStatusFps() {
      try {
        const st = await api.get('/api/music/status');
        if (!st) return;
        /* 后端 running 与本地不一致时以真实状态为准（典型：待机/设备断开后后端已停止） */
        if (typeof st.running === 'boolean' && st.running !== running) {
          const wasRunning = running;
          setRunning(st.running);
          if (wasRunning && !st.running) {
            const reason = String(st.lastError || '').trim();
            ctx.toastWarn(reason ? `音乐律动已停止：${reason}` : '音乐律动已停止（原因未知）');
          }
        }
        /* 健康状态：恢复中 / 等待键盘 / 已恢复次数 / 音频回退 */
        if (typeof st.health === 'string') healthState = st.health;
        if (st.recoveries != null) {
          const n = Number(st.recoveries);
          if (Number.isFinite(n)) recoveries = n;
        }
        lastRecovery = st.lastRecovery != null ? Number(st.lastRecovery) : null;
        if (typeof st.lastError === 'string') lastError = st.lastError;
        if (typeof st.audioFallback === 'boolean') audioFallback = st.audioFallback;
        frameAgeMs = st.frameAgeMs != null ? Number(st.frameAgeMs) : null;
        if (!running) healthState = 'stopped';
        applyHealthBadge();
        refreshHealthHint();
        /* 实测帧率：status.fps 是后端回传的实测值（可能是浮点） */
        if (st.fps != null) {
          const v = Number(st.fps);
          if (Number.isFinite(v)) { backendFps = v; measuredFps = v; }
        } else {
          measuredFps = null;
        }
        updateFpsReadout();
        refreshPreviewNote();
      } catch { /* 轮询失败不影响律动 */ }
    }
    function startStatusPoll() {
      if (statusTimer) return;
      statusTimer = setInterval(pollStatusFps, 3000);
    }
    function stopStatusPoll() {
      if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
    }
    async function liveUpdate() {
      if (!running) return;
      try {
        const st = await api.post('/api/music/update', payloadForScheme());
        applyStatus(st);
        refreshPreviewNote();
      } catch (e) {
        ctx.toastWarn(`热更新失败：${e.message || e}`);
      }
    }
    function scheduleLiveUpdate() {
      if (!running) return;
      clearTimeout(liveTimer);
      liveTimer = setTimeout(() => { liveTimer = null; liveUpdate(); }, 120);
    }

    /* ---------------- 方案切换（热切换，不停止律动） ---------------- */
    const schemeHint = h('span', { class: 'hint' }, '');
    const schemeTabs = createTabs({
      tabs: [{ id: 'current', label: '当前方案' }, { id: 'official', label: '官方方案' }],
      active: scheme,
      onChange: (v) => { switchScheme(v); },
    });
    const schemeBar = h('div', { class: 'row', style: { gap: '12px', flexWrap: 'wrap', marginBottom: '14px' } },
      schemeTabs.el, h('div', { class: 'spacer' }), schemeHint);

    /* ---------------- 预览说明 ---------------- */
    const previewHint = h('span', { class: 'hint' }, '');
    const previewNoteMain = h('span', {}, '');
    const previewNoteBadge = h('span', { class: 'badge accent', style: { display: 'none' } });
    const previewNoteState = h('span', {}, '');
    const previewNoteFps = h('span', {}, '');
    const previewNote = h('div', {
      class: 'tiny muted',
      style: { marginTop: '10px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' },
    }, previewNoteMain, previewNoteBadge, previewNoteState, previewNoteFps);

    const startBtn = h('button', { class: 'btn primary lg', html: `${icon('play', { size: 16 })}<span>开始律动</span>` });
    const stopBtn = h('button', { class: 'btn lg', html: `${icon('stop', { size: 16 })}<span>停止</span>`, disabled: true });
    const supportBanner = h('div', { class: 'banner danger', style: { display: 'none', margin: '0 0 16px' } });

    /* ---------------- 预览 / 渲染 ---------------- */
    function officialFrameMap(colors) {
      const map = new Map();
      if (!colors || typeof colors !== 'object') return map;
      for (const [slot, rgb] of Object.entries(colors)) {
        if (Array.isArray(rgb) && rgb.length >= 3) {
          map.set(Number(slot), [Number(rgb[0]) || 0, Number(rgb[1]) || 0, Number(rgb[2]) || 0]);
        }
      }
      return map;
    }

    function modeNameOfValue(value, official) {
      const v = Number(value);
      if (official) {
        const m = OFFICIAL_MUSIC_MODES.find((x) => x.value === v);
        return m ? offLabel(m) : `mode ${v}`;
      }
      const list = statusModes || DEFAULT_MODES;
      const hit = list.find((m) => Number(m.mode) === v);
      return hit ? modeLabel(hit) : `mode ${v}`;
    }

    function refreshPreviewNote() {
      const official = scheme === 'official';
      if (!official) {
        previewNoteMain.textContent = '按键颜色 = 所在列的频率强度，是本工具自己的可视化；与设备实际输出无关';
        previewNoteBadge.style.display = 'none';
        previewNoteBadge.textContent = '';
        previewNoteState.textContent = '';
        previewNoteFps.textContent = '';
        return;
      }
      previewNoteMain.textContent = '官方渲染器实发帧：逐键颜色与键盘同步';
      previewNoteBadge.textContent = modeNameOfValue(backendMode != null ? backendMode : offMode, true);
      previewNoteBadge.style.display = '';
      previewNoteState.textContent = running
        ? (officialColors ? '实时回放中' : '等待首帧…')
        : '开始律动后显示实时回放';
      const shownFps = measuredFps != null
        ? Number(measuredFps).toFixed(1)
        : (backendFps != null ? Number(backendFps).toFixed(1) : null);
      previewNoteFps.textContent = shownFps ? `${shownFps} fps` : (running ? '— fps' : `${offFps} fps`);
    }

    function applyScheme(clear = false) {
      if (clear) keyboard.clearColors();
      const official = scheme === 'official';
      currentParams.style.display = official ? 'none' : '';
      officialParams.style.display = official ? '' : 'none';
      schemeHint.textContent = official
        ? '官方同款设置项 + 本工具增强（LED 颜色 / 原生帧率）'
        : '本工具参数（模式 / 帧率 / 灵敏度），预览为本地频谱动画';
      previewHint.textContent = official ? '设备实发帧（官方渲染器）' : '本地频谱预览（非设备输出）';
      refreshPreviewNote();
    }

    async function switchScheme(v) {
      const next = v === 'official' ? 'official' : 'current';
      if (next === scheme) return;
      scheme = next;
      store.set('mk87.music.scheme', scheme);
      applyScheme();
      if (running) {
        // 热切换：直接把新方案的参数推给运行中的引擎，不打断音乐
        clearTimeout(liveTimer);
        liveTimer = null;
        await liveUpdate();
        ctx.toast('已切换方案（热生效，未停止律动）');
      }
    }

    /* ---------------- 电平原画 ---------------- */
    function paintLevels() {
      for (let i = 0; i < BAND_COUNT; i++) {
        levels[i] += (targetLevels[i] - levels[i]) * 0.35;
        const pct = clamp(levels[i], 0, 1) * 100;
        bars[i].style.height = `${Math.max(3, pct)}%`;
        const hue = 190 + i * 4.6;
        bars[i].style.background = `linear-gradient(180deg, hsl(${hue} 95% 68%), hsl(${hue + 40} 90% 55%) 60%, hsl(${hue + 70} 85% 45%))`;
      }
      const avg = levels.reduce((a, b) => a + b, 0) / BAND_COUNT;
      levelMeter.querySelector('i').style.width = `${clamp(avg / 0.55, 0, 1) * 100}%`;
      meterValue.textContent = avg.toFixed(3);
      if (!running) return;
      if (scheme === 'official') {
        // 官方方案：直接回放后端发给键盘的那一帧（逐键颜色同源）
        if (officialColors && officialColors.size) keyboard.applyColorFrame(officialColors);
      } else {
        // 当前方案：本地频谱动画（列 = 频率带），仅前端预览
        const frame = new Map();
        for (const k of KEYS) {
          const v = clamp(levels[k.col] * 1.15, 0, 1);
          const rgb = v < 0.02 ? [22, 28, 40] : hslToRgb(196 + k.col * 4.8, 95, 42 + v * 26);
          frame.set(k.slot, rgb);
        }
        keyboard.applyColorFrame(frame);
      }
    }
    function loop() {
      paintLevels();
      raf = requestAnimationFrame(loop);
    }

    /* ---------------- 事件 ---------------- */
    offs.push(api.on('ws:music_level', (d) => {
      if (!d) return;
      targetLevels = Array.from({ length: BAND_COUNT }, (_, i) => clamp(Number(d.bands?.[i] ?? d.level ?? 0), 0, 1));
    }));
    offs.push(api.on('ws:music_frame', (d) => {
      if (!d) return;
      const firstFrame = !officialColors || !officialColors.size;
      if (d.mode != null) backendMode = Number(d.mode);
      if (d.fps != null) {
        const v = Number(d.fps);
        if (Number.isFinite(v)) {
          const changed = backendFps !== v;
          backendFps = v;
          measuredFps = v;
          if (changed) {
            updateFpsReadout();
            if (scheme === 'official') refreshPreviewNote();
          }
        }
      }
      officialColors = officialFrameMap(d.colors);
      if (firstFrame && officialColors.size) refreshPreviewNote();
    }));
    /* 后端健康状态推送：自动恢复中 / 等待键盘 / 恢复成功。只在状态值变化时 toast，避免每帧刷屏 */
    offs.push(api.on('ws:music_health', (d) => {
      if (!d) return;
      const prev = healthState;
      const next = typeof d.state === 'string' && d.state ? d.state : prev;
      if (d.lastError != null) lastError = String(d.lastError || '');
      if (d.recoveries != null) {
        const n = Number(d.recoveries);
        if (Number.isFinite(n)) recoveries = n;
      }
      healthState = running ? next : 'stopped';
      applyHealthBadge();
      refreshHealthHint();
      if (!running || next === prev) return;
      if (next === 'recovering') {
        ctx.toastWarn('音频采集中断，正在自动恢复…');
      } else if (next === 'waiting-device') {
        ctx.toastWarn('键盘连接中断，等待重连后自动恢复律动');
      } else if (next === 'ok' && (prev === 'recovering' || prev === 'waiting-device')) {
        ctx.toastSuccess('音乐律动已自动恢复');
      }
    }));
    /* 后端停止推送：前端立刻切回未开始；意外停止（待机/设备断开后放弃恢复）用 error 提示原因 */
    offs.push(api.on('ws:music_stopped', (d) => {
      const data = d || {};
      if (running) {
        setRunning(false);
      } else {
        applyHealthBadge();
        refreshHealthHint();
      }
      if (data.unexpected) {
        ctx.toastError('音乐律动已停止：' + (data.reason || '未知原因'));
      }
    }));

    function setRunning(on) {
      running = on;
      startBtn.disabled = on || !supported;
      stopBtn.disabled = !on;
      if (!on) healthState = 'stopped';
      applyHealthBadge();
      refreshHealthHint();
      idleHint.style.display = on ? 'none' : '';
      levelBarWrap.style.opacity = on ? '1' : '.55';
      if (on) {
        startStatusPoll();
        if (!raf) loop();
      } else {
        stopStatusPoll();
        measuredFps = null;
        updateFpsReadout();
        keyboard.clearColors();
        officialColors = null;
        targetLevels = new Array(BAND_COUNT).fill(0);
        setTimeout(() => {
          if (running) return;
          cancelAnimationFrame(raf); raf = null;
          levels = new Array(BAND_COUNT).fill(0);
          paintLevels();
        }, 400);
      }
      refreshPreviewNote();
    }

    function renderSupport() {
      supportBanner.innerHTML = '';
      if (supported) { supportBanner.style.display = 'none'; return; }
      supportBanner.style.display = '';
      supportBanner.append(
        h('div', { class: 'banner-icon', html: icon('alert-triangle', { size: 17 }) }),
        h('div', {}, h('strong', {}, '音乐律动仅支持 USB 有线连接'),
          h('div', { class: 'tiny', style: { marginTop: '2px' } }, '官方明确 2.4G 不支持音乐律动（帧流通道只在 USB 可用）；请改用 USB 有线连接，或先停止律动。')),
      );
      startBtn.disabled = true;
    }
    ctx.onStatus?.((st) => {
      const next = st?.caps ? st.caps.music !== false : true;
      if (next !== supported) { supported = next; renderSupport(); }
    });

    function renderDevices() {
      deviceList.innerHTML = '';
      if (!devices.length) {
        deviceList.append(h('div', { class: 'empty' }, h('div', {}, '没有检测到音频输出设备')));
        return;
      }
      for (const d of devices) {
        const active = d.id === selectedDevice;
        deviceList.append(h('div', {
          class: `music-device${active ? ' active' : ''}`,
          onclick: () => {
            if (running) { ctx.toastWarn('请先停止律动再切换音频设备'); return; }
            selectedDevice = d.id;
            renderDevices();
          },
        },
          h('div', { class: 'ic', html: icon(d.id === 'default' ? 'speaker' : 'volume', { size: 16 }) }),
          h('div', { style: { minWidth: 0 } },
            h('div', { class: 'nm' }, d.name || d.id),
            h('div', { class: 'ds' }, d.description || ''),
          ),
          h('span', { class: 'chk', html: icon('check', { size: 16 }) }),
        ));
      }
    }

    /* ---------------- 启动 / 停止 ---------------- */
    async function startMusic() {
      if (!supported) { ctx.toastError('音乐律动仅支持 USB 有线连接'); return; }
      startBtn.disabled = true;
      try {
        let body;
        if (scheme === 'official') {
          if (!isPorted(offMode)) {
            const m = OFFICIAL_MUSIC_MODES.find((x) => x.value === Number(offMode));
            ctx.toastWarn(m?.renderer === 'plugin'
              ? '屏光联动由官方 Music.exe 读屏计算；本工具自研屏幕同步待做，将回落到「随曲起舞」'
              : '该模式的官方渲染器尚未移植，将回落到「随曲起舞」');
          }
          body = {
            deviceId: selectedDevice,
            fps: offFps,
            color: offColor,
            mode: offMode,
            backmode: offBackmode,
            backmodeBrightness: offBackBright,
            amplitude: offAmplitude,
          };
        } else {
          body = { deviceId: selectedDevice, sensitivity: sensSlider.value / 50, mode, fps };
        }
        const st = await api.post('/api/music/start', body);
        applyStatus(st);
        backendRequested = st?.requestedMode != null ? Number(st.requestedMode) : Number(body.mode);
        backendFps = Number(st?.fps || body.fps || 20);
        /* 启动成功：后端已给健康状态就用它，否则先按 starting（下一轮轮询转 ok） */
        healthState = (typeof st?.health === 'string' && st.health !== 'stopped') ? st.health : 'starting';
        /* 新一轮启动后端会把自动恢复计数清零，这里同步回填，避免残留上一次的恢复提示 */
        if (st && typeof st === 'object') {
          if (st.recoveries != null) recoveries = Number(st.recoveries) || 0;
          lastRecovery = st.lastRecovery != null ? Number(st.lastRecovery) : null;
          if (typeof st.lastError === 'string') lastError = st.lastError;
          if (typeof st.audioFallback === 'boolean') audioFallback = st.audioFallback;
        }
        frameAgeMs = null;
        setRunning(true);
        ctx.toastSuccess(scheme === 'official'
          ? '已开始音乐律动（官方方案 · 官方同款参数）'
          : '已开始音乐律动（当前方案 · 逐键帧流）');
      } catch (e) {
        ctx.toastError(`启动失败：${e.message || e}`);
        startBtn.disabled = false;
      }
    }
    async function stopMusic() {
      clearTimeout(liveTimer);
      liveTimer = null;
      try {
        await api.post('/api/music/stop');
      } catch (e) {
        ctx.toastError(`停止失败：${e.message || e}`);
      }
      healthState = 'stopped';
      setRunning(false);
    }
    startBtn.addEventListener('click', startMusic);
    stopBtn.addEventListener('click', stopMusic);

    /* ---------------- 布局 ---------------- */
    const controlCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '音乐律动'),
          h('div', { class: 'card-desc' }, '系统音频 → 官方渲染器 → 逐键 RGB 帧流（USB 0x32）')),
        h('div', { class: 'spacer' }),
        statusBadge,
      ),
      h('div', { class: 'card-body' },
        schemeBar,
        currentParams,
        officialParams,
        h('div', { class: 'row mt-16' }, startBtn, stopBtn,
          h('div', { class: 'spacer' }),
          h('span', { class: 'tiny muted' }, '参数由本地引擎计算，无需 Music.exe'),
        ),
        healthHint,
        h('div', { class: 'section-title', style: { marginTop: '20px' } },
          h('h2', {}, '实时电平'), h('span', { class: 'hint' }, `32 段频谱 · ${meterValue.textContent}`)),
        levelBarWrap,
        h('div', { class: 'row mt-12', style: { gap: '12px' } },
          h('span', { class: 'tiny muted' }, '总振幅'), levelMeter, meterValue,
        ),
        h('div', { class: 'section-title', style: { marginTop: '20px' } },
          h('h2', {}, '键盘可视化'), previewHint),
        keyboard.deck,
        previewNote,
      ),
    );

    const deviceCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '音频输出设备'),
          h('div', { class: 'card-desc' }, '选择要捕获的系统输出（loopback / monitor）')),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn sm ghost', title: '刷新设备', html: icon('refresh', { size: 14 }),
          onclick: async () => {
            try {
              devices = await api.get('/api/music/devices') || [];
              if (!Array.isArray(devices)) devices = devices.devices || [];
              renderDevices();
              ctx.toast('设备列表已刷新');
            } catch (e) { ctx.toastError(e.message || String(e)); }
          },
        }),
      ),
      h('div', { class: 'card-body' }, deviceList,
        h('div', { class: 'tiny muted mt-12' }, 'Windows 使用 WASAPI loopback；Linux 使用 PulseAudio / PipeWire monitor。设备由后端枚举。'),
      ),
    );

    const statusCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '引擎参数')),
      h('div', { class: 'card-body' },
        kvList([
          ['FFT', 'fftSize 2048 · smoothing 0.75'],
          ['主循环', '50 ms tick（20 fps）'],
          ['帧载荷', '87 键 × 4B = 348B / 帧（7 包）'],
          ['官方参数', '显示模式 / 背景模式 / 背景亮度 / 振幅（与官方 v1 同款）'],
          ['自研增强', 'LED 颜色覆盖 · 原生帧率 20 / 60 / 66（默认 66）'],
          ['激活条件', 'LED mode ∈ {20,21,128}，停帧约 5s 回落'],
          ['2.4G', '不支持（官方确认）'],
          ['当前连接', supported ? 'USB · 可用' : '2.4G · 不可用'],
        ]),
      ),
    );

    const noteCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '两种方案与官方同款参数')),
      h('div', { class: 'card-body' },
        h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
          h('p', {}, '官方 v1 音乐律动把参数交给 Windows 专有的 Music.exe，由它用原生 HID 驱动键盘；浏览器也不发帧，所以跨平台不可用。'),
          h('p', {}, '本工具的「官方方案」使用与官方 v1 插件相同的设置项：显示模式（21 种，含 100 屏光联动）、背景模式（11 种）、背景亮度、振幅，并增加本工具自研的 LED 颜色覆盖与原生帧率（20/60/66，默认 66）；由本地移植的官方渲染器计算逐键帧并发送（cmd 0x32）。'),
          h('p', {}, '其中 1/2/4/5/6/7/8/9/10/11 是官方「曲率频阶柱状」的不同调色板（模式号即调色板），13 是同心环，14–22 是扩展模式（自研渲染器）；1/2/4/5/6/7/8/9/10/11/13 的颜色、覆盖率与亮度缩放都用官方采样（capture/official_music_colors3.jsonl）逐项校验过。'),
          h('p', {}, '显示模式 100「屏光联动」由官方 Music.exe 读屏计算，本工具的自研屏幕同步待做，当前会回落到 13。'),
          h('p', {}, '「当前方案」保留本工具自己的参数（模式 / 帧率 / 灵敏度）与本地频谱预览动画，用于对比调试。'),
          h('p', {}, '因此音乐律动完全在本地、跨平台可用，且不需要安装任何插件。'),
        ),
      ),
    );

    root.append(supportBanner, h('div', { class: 'grid grid-main' },
      h('div', { class: 'grid-stack' }, controlCard),
      h('div', { class: 'grid-stack' }, deviceCard, statusCard, noteCard),
    ));

    syncOfficialControls();
    renderSupport();
    renderDevices();
    setRunning(running);
    applyScheme();
    if (!running) {
      cancelAnimationFrame(raf); raf = null;
      paintLevels();
    }

    return () => {
      offs.forEach((off) => off?.());
      clearTimeout(liveTimer);
      stopStatusPoll();
      cancelAnimationFrame(raf);
      keyboard.destroy();
    };
  },
};
