/* pages/music.js — 音乐律动：音频输出设备、灵敏度/风格、开始停止、实时电平与键盘可视化
   引擎在 Python 后端（WASAPI loopback / PipeWire monitor → FFT → 20fps 逐键帧流 0x32）。
   仅 USB 支持：2.4G 下官方明确不支持（spec-lighting.md §4.6）。 */
import { KEY_LAYOUT } from '../data/keyboard.js';
import { icon } from '../icons.js';
import { h, clamp } from '../util.js';
import { Keyboard } from '../components/keyboard.js';
import { createSlider, createSegmented, badge, kvList } from '../components/widgets.js';

const BAND_COUNT = 32;
const KEYS = KEY_LAYOUT.rows.flat().map((k) => ({ slot: k.slot, col: clamp(Math.floor((k.x / 275) * BAND_COUNT), 0, BAND_COUNT - 1) }));

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
    const { api, t } = ctx;

    let supported = ctx.status?.caps ? ctx.status.caps.music !== false : true;
    let musicStatus = { running: false, fps: 20, level: 0, device: null };
    let statusStyles = null;
    let statusStyle = null;
    let devices = [];
    let selectedDevice = null;
    let style = 'spectrum';
    let fps = 20;
    let levels = new Array(BAND_COUNT).fill(0);
    let targetLevels = new Array(BAND_COUNT).fill(0);
    let running = false;
    let raf = null;
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
        musicStatus = { ...musicStatus, ...st };
        running = !!st.running;
        if (st.deviceId) selectedDevice = st.deviceId;
        else if (st.device) selectedDevice = st.device;
        if (Array.isArray(st.styles) && st.styles.length) {
          statusStyles = st.styles;
          statusStyle = st.style || st.styles[0];
        }
        if (st.supported === false) supported = false;
      }
    } catch { /* ignore */ }

    /* ---------------- 组件 ---------------- */
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
    const levelMeter = h('div', { class: 'meter' },
      h('div', { class: 'meter-bar' }, h('i')),
    );
    const meterValue = h('span', { class: 'mono tiny muted' }, '0.000');
    const statusBadge = h('span', { class: 'badge' }, '未开始');
    const deviceList = h('div', { class: 'stack' });

    /* 灵敏度：后端 sensitivity 1.0 基准，滑块 10..100 → 0.2..2.0 */
    const sensSlider = createSlider({
      label: '灵敏度',
      min: 10, max: 100, step: 5, value: 50,
      format: (v) => `${(v / 50).toFixed(2)}×`,
    });
    const STYLE_LABELS = { spectrum: '频谱', rainbow: '彩虹', pulse: '脉冲', ripple: '涟漪', firefly: '萤火' };
    const styleOptions = (statusStyles || ['spectrum', 'pulse']).map((v) => ({ value: v, label: STYLE_LABELS[v] || v }));
    if (statusStyle) style = statusStyle;
    const styleSeg = createSegmented({
      options: styleOptions,
      value: style,
      onChange: (v) => { style = v; },
    });
    const fpsSeg = createSegmented({
      options: [{ value: 15, label: '15' }, { value: 20, label: '20' }, { value: 30, label: '30' }],
      value: 20, small: true,
      onChange: (v) => { fps = v; },
    });

    const startBtn = h('button', { class: 'btn primary lg', html: `${icon('play', { size: 16 })}<span>开始律动</span>` });
    const stopBtn = h('button', { class: 'btn lg', html: `${icon('stop', { size: 16 })}<span>停止</span>`, disabled: true });

    const supportBanner = h('div', { class: 'banner danger', style: { display: 'none', margin: '0 0 16px' } });

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
      if (running) {
        // 键盘可视化：列 = 频率带
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

    function setRunning(on) {
      running = on;
      startBtn.disabled = on || !supported;
      stopBtn.disabled = !on;
      statusBadge.textContent = on ? '律动中' : '未开始';
      statusBadge.className = `badge ${on ? 'ok' : ''}`;
      idleHint.style.display = on ? 'none' : '';
      levelBarWrap.style.opacity = on ? '1' : '.55';
      if (on) {
        if (!raf) loop();
      } else {
        keyboard.clearColors();
        targetLevels = new Array(BAND_COUNT).fill(0);
        setTimeout(() => {
          if (running) return;
          cancelAnimationFrame(raf); raf = null;
          levels = new Array(BAND_COUNT).fill(0);
          paintLevels();
        }, 400);
      }
    }

    async function startMusic() {
      if (!supported) { ctx.toastError('音乐律动仅支持 USB 有线连接'); return; }
      startBtn.disabled = true;
      try {
        await api.post('/api/music/start', { deviceId: selectedDevice, sensitivity: sensSlider.value / 50, style, fps });
        setRunning(true);
        ctx.toastSuccess('已开始音乐律动（逐键帧流 20fps，仅 USB）');
      } catch (e) {
        ctx.toastError(`启动失败：${e.message || e}`);
        startBtn.disabled = false;
      }
    }
    async function stopMusic() {
      try {
        await api.post('/api/music/stop');
      } catch (e) {
        ctx.toastError(`停止失败：${e.message || e}`);
      }
      setRunning(false);
    }
    startBtn.addEventListener('click', startMusic);
    stopBtn.addEventListener('click', stopMusic);

    /* ---------------- 布局 ---------------- */
    const controlCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '音乐律动'),
          h('div', { class: 'card-desc' }, '系统音频 → FFT 分析 → 20fps 逐键 RGB 帧流（USB 0x32）')),
        h('div', { class: 'spacer' }),
        statusBadge,
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'grid grid-2', style: { marginBottom: '14px' } },
          h('div', { class: 'field' }, h('div', { class: 'field-label' }, '风格'), styleSeg.el),
          h('div', { class: 'field' }, h('div', { class: 'field-label' }, '帧率（fps）'), h('div', { class: 'row' }, fpsSeg.el, h('span', { class: 'tiny muted' }, '实测 20fps 稳定'))),
        ),
        sensSlider.el,
        h('div', { class: 'row mt-16' }, startBtn, stopBtn,
          h('div', { class: 'spacer' }),
          h('span', { class: 'tiny muted' }, '比官方 v1 更省心：无需 Music.exe 插件'),
        ),
        h('div', { class: 'section-title', style: { marginTop: '20px' } }, h('h2', {}, '实时电平'), h('span', { class: 'hint' }, `32 段频谱 · ${meterValue.textContent}`)),
        levelBarWrap,
        h('div', { class: 'row mt-12', style: { gap: '12px' } },
          h('span', { class: 'tiny muted' }, '总振幅'), levelMeter, meterValue,
        ),
        h('div', { class: 'section-title', style: { marginTop: '20px' } }, h('h2', {}, '键盘可视化'), h('span', { class: 'hint' }, '本地预览（真实帧流由后端推送设备）')),
        keyboard.deck,
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
          ['激活条件', 'LED mode ∈ {20,21,128}，停帧约 5s 回落'],
          ['2.4G', '不支持（官方确认）'],
          ['当前连接', supported ? 'USB · 可用' : '2.4G · 不可用'],
        ]),
      ),
    );

    const noteCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '为什么不需要官方插件')),
      h('div', { class: 'card-body' },
        h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
          h('p', {}, '官方 v1 音乐律动把参数交给 Windows 专有的 Music.exe，由它用原生 HID 驱动键盘；浏览器也不发帧，所以跨平台不可用。'),
          h('p', {}, '本工具复刻的是官方 v2「浏览器侧链路」：后端捕获系统音频 → 计算振幅/频谱 → 20fps 逐键帧流（cmd 0x32，348B/帧，7 包串行等 ACK）。'),
          h('p', {}, '因此音乐律动完全在本地、跨平台可用，且不需要安装任何插件。'),
        ),
      ),
    );

    root.append(supportBanner, h('div', { class: 'grid grid-main' },
      h('div', { class: 'grid-stack' }, controlCard),
      h('div', { class: 'grid-stack' }, deviceCard, statusCard, noteCard),
    ));

    renderSupport();
    renderDevices();
    setRunning(running);
    if (!running) {
      cancelAnimationFrame(raf); raf = null;
      paintLevels();
    }

    return () => {
      offs.forEach((off) => off?.());
      cancelAnimationFrame(raf);
      keyboard.destroy();
    };
  },
};
