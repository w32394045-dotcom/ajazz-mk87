// music_ref.js —— AJAZZ MK87 音乐律动 / 实时逐键灯效 的官方实现等价参考代码
// 来源：ajazz.driveall.cn bundle（layout-classic-CMxiG14P.js）静态还原，逐行对照官方函数重写。
// 用途：不依赖官方 Music.exe，自己采集音频 → 渲染每键颜色 → 走 HID 帧流把画面推到键盘。
//
// 运行：node music_ref.js            # 自检 + 演示
//      node music_ref.js --demo     # 只打印演示数据包
//
// 关键函数指纹（bundle 偏移）：
//   K7/Nse/q7/J7/Pse  ~2_315_600（音频分析）
//   Fe(模式1/4)/Se(13)/Ce(14)/Ee(15)/De(16)/je(17)/Oe(18)/Ae(19)/Ne(20)/Pe(21)/L(22)
//                    ~2_322_000–2_342_000（渲染器）
//   Y7 主循环 50ms    ~2_320_000（pe/he/me）
//   setMusicData=TZ  docs/protocol_commands.js 第 862 行（USB 走 cmd 50）

'use strict';
const fs = require('fs');
const path = require('path');

// ============================ 0. 配置 / 常量 ============================

const ANALYSER = {
  fftSize: 2048,
  smoothingTimeConstant: 0.75,
  // K7 总振幅归一化参数
  FLOOR: 0.01,
  ATTACK: 0.3,
  DECAY: 0.008,
  TIME_DOMAIN_MIX: { peak: 0.6, rms: 0.4 },
  // 静音门限（归一化后 <=5 视为 0）
  GATE: 5,
  // 3 段频带
  BANDS: [['low', 20, 250], ['mid', 250, 4000], ['high', 4000, 20000]],
};

// 音乐模式（官方 UI 下拉；MK87 musicConfig.version=1，无 filterMusicMode，全部可选）
const MUSIC_MODES = [
  { value: 13, i18n: 'music_mode_text3' },   // 默认（同心环/波纹）
  { value: 22, i18n: 'music_mode_text20' },  // 22 号渲染器 L
  { value: 14, i18n: 'music_mode_text12' },  // 旋转射线
  { value: 15, i18n: 'music_mode_text13' },  // 火山/三塔
  { value: 16, i18n: 'music_mode_text14' },
  { value: 18, i18n: 'music_mode_text16' },
  { value: 19, i18n: 'music_mode_text17' },
  { value: 17, i18n: 'music_mode_text15' },  // 正弦波行
  { value: 20, i18n: 'music_mode_text18' },
  { value: 21, i18n: 'music_mode_text19' },
  { value: 4, i18n: 'music_mode_text4' },    // 背景+柱状
  { value: 100, i18n: 'music_mode_text21' }, // 交给本地插件 Music.exe
];

// 背景模式（官方 _e 函数；0 = 黑）
const BG_MODES = [
  { value: 0, i18n: 'music_bg_text1' },   // 无背景
  { value: 6, i18n: 'music_bg_text2' },   // 白
  { value: 7, i18n: 'music_bg_text3' },   // 红
  { value: 8, i18n: 'music_bg_text4' },   // 橙
  { value: 9, i18n: 'music_bg_text5' },   // 黄
  { value: 10, i18n: 'music_bg_text6' },  // 蓝
  { value: 11, i18n: 'music_bg_text7' },  // 绿
  { value: 1, i18n: 'music_bg_text8' },   // 3 色横向分段
  { value: 2, i18n: 'music_bg_text9' },   // 6 色横向分段
  { value: 4, i18n: 'music_bg_text10' },  // 中心径向色相渐变
  { value: 5, i18n: 'music_bg_text11' },  // 纯色旋转色相
];

// 协议常量（来自 protocol_commands.js HX 枚举 + TZ 实现）
const CMD = {
  GET_LED_DATA: 50,              // 0x32 —— USB 音乐帧（4B/键）
  SET_MUSIC_DATA: 53,            // 0x35 —— 通用分支（RGB565 流，无键号）
  SET_MUSIC_DATA_24G_64: 60,     // 0x3C —— 2.4G 且 report=64 且 lightingVersion=1
};

// ============================ 1. 工具函数 ============================

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const round = Math.round;

/** 官方 kV(hue, saturation, value)：色相→RGB（0..255） */
function kV(hue, saturation = 1, value = 1) {
  const r = value * saturation;
  const i = r * (1 - Math.abs(((hue / 60) % 2) - 1));
  const a = value - r;
  let o, s, c;
  if (hue >= 0 && hue < 60) { o = r; s = i; c = 0; }
  else if (hue >= 60 && hue < 120) { o = i; s = r; c = 0; }
  else if (hue >= 120 && hue < 180) { o = 0; s = r; c = i; }
  else if (hue >= 180 && hue < 240) { o = 0; s = i; c = r; }
  else if (hue >= 240 && hue < 300) { o = i; s = 0; c = r; }
  else { o = r; s = 0; c = i; }
  return { r: round((o + a) * 255), g: round((s + a) * 255), b: round((c + a) * 255) };
}

/** 官方 AV(rgb) → RGB565 */
const AV = (c) => ((c.r & 0xF8) << 8) | ((c.g & 0xFC) << 3) | ((c.b & 0xF8) >> 3);
/** 官方 jV(v) → [高字节, 低字节] */
const jV = (v) => [(v >> 8) & 0xFF, v & 0xFF];

function zeros(rows, cols) {
  return Array.from({ length: rows }, () =>
    Array.from({ length: cols }, () => ({ r: 0, g: 0, b: 0 })));
}

// ============================ 2. 键盘布局（来自官方 config） ============================

/**
 * 按官方 me()/Re() 的规则生成布局网格：
 *  row = keyList 行号；col = 行内下标 + 该行累计 keyOffset.offsetX
 *  rows = keyList.length；cols(P) = 最长行 + maxColOffset；网格实际宽 P+1
 */
function buildLayout(keyboardConfig) {
  const musicConfig = keyboardConfig.musicConfig || {};
  const maxColOffset = musicConfig.maxColOffset || 0;
  const keyOffset = new Map((musicConfig.keyOffset || []).map((o) => [o.value, o.offsetX]));
  const rowsRaw = keyboardConfig.keyList;
  const F = rowsRaw.length;
  const P = rowsRaw.reduce((m, r) => Math.max(m, r.length), 0) + maxColOffset;

  const cells = [];
  rowsRaw.forEach((row, ri) => {
    let shift = 0;
    row.forEach((key, idx) => {
      let col = idx + shift;
      const off = keyOffset.get(key.value);
      if (off) { col += off; shift += off; }
      cells.push({
        row: ri, col, value: key.value, name: key.name,
        keyCode: key.keyCode, disabledLight: !!key.disabledLight,
      });
    });
  });
  const visible = cells.filter((c) => !c.disabledLight);
  // 行/列中点（官方 le / ce）
  const le = F % 2 === 0 ? F / 2 - 1 : Math.floor(F / 2);
  const rowLen = rowsRaw[le] ? rowsRaw[le].length : P;
  const ce = rowLen % 2 === 0 ? rowLen / 2 - 1 : Math.floor(rowLen / 2);
  return { F, P, width: P + 1, cells, visible, centerRow: le, centerCol: ce };
}

function loadMk87Config() {
  const p = path.join(__dirname, '..', 'docs', 'keymap-tables.json');
  try {
    const t = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (t.mk87KeyboardConfig && t.mk87KeyboardConfig.keyListRaw) {
      return {
        keyList: t.mk87KeyboardConfig.keyListRaw,
        musicConfig: t.mk87KeyboardConfig.musicConfig || {},
      };
    }
  } catch (e) { /* 落到内置兜底 */ }
  // 兜底：MK87 6 行 87 键（只用于离线自检，不参与颜色计算之外的东西）
  const rowVals = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 99, 100, 102],
    [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 92, 103, 104, 105],
    [32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 60, 106, 107, 108],
    [48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 76],
    [64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 90],
    [80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91],
  ];
  return {
    keyList: rowVals.map((vals) => vals.map((v) => ({ value: v, name: 'k' + v, keyCode: 0 }))),
    musicConfig: {
      version: 1, maxColOffset: 0,
      keyOffset: [
        { value: 1, offsetX: 1 }, { value: 65, offsetX: 1 }, { value: 90, offsetX: 2 },
        { value: 83, offsetX: 3 }, { value: 84, offsetX: 3 },
      ],
    },
  };
}

// ============================ 3. 音频分析（官方 K7 / Nse / q7 / J7 / Pse） ============================

function createAudioAnalyzer() {
  let z = ANALYSER.FLOOR;                       // 总振幅自适应基准（官方 z7）
  const bandBase = { low: ANALYSER.FLOOR, mid: ANALYSER.FLOOR, high: ANALYSER.FLOOR }; // B7

  /** 官方 Nse(e)：总振幅自适应归一化（0..1000，<=5 → 0） */
  function normalize(e) {
    z = e > z ? z * 0.7 + e * ANALYSER.ATTACK : z * 0.992 + e * ANALYSER.DECAY;
    z = Math.max(z, ANALYSER.FLOOR);
    const ratio = e / z;
    const out = Math.min(1000, Math.round(ratio * 1000));
    return out <= ANALYSER.GATE ? 0 : out;
  }

  /** 官方 K7：时域波形 → 总振幅 0..1000 */
  function timeDomainAmplitude(floatTimeData) {
    let peak = 0, sum = 0;
    for (let i = 0; i < floatTimeData.length; i++) {
      const abs = Math.abs(floatTimeData[i] ?? 0);
      peak = Math.max(peak, abs);
      sum += abs * abs;
    }
    const rms = Math.sqrt(sum / floatTimeData.length);
    const raw = ANALYSER.TIME_DOMAIN_MIX.peak * peak + ANALYSER.TIME_DOMAIN_MIX.rms * rms;
    return normalize(raw);
  }

  /** 官方 q7：在 byte 频谱里按 Hz 区间求 RMS（0..1） */
  function bandRms(bytes, hzLo, hzHi, sampleRate, fftSize) {
    const hzPerBin = sampleRate / fftSize;
    const i0 = Math.max(0, Math.floor(hzLo / hzPerBin));
    const i1 = Math.min(bytes.length - 1, Math.ceil(hzHi / hzPerBin));
    if (i1 < i0) return 0;
    let sum = 0;
    for (let i = i0; i <= i1; i++) {
      const v = (bytes[i] ?? 0) / 255;
      sum += v * v;
    }
    return Math.sqrt(sum / (i1 - i0 + 1));
  }

  /** 官方 J7：频带自适应归一化（0..1000，<=5 → 0） */
  function normalizeBand(e, name) {
    const base = bandBase[name];
    const r = e > base ? ANALYSER.ATTACK : ANALYSER.DECAY;
    const next = Math.max(base * (1 - r) + e * r, ANALYSER.FLOOR);
    bandBase[name] = next;
    const ratio = Math.min(1000, Math.round((e / next) * 1000));
    return ratio <= ANALYSER.GATE ? 0 : ratio;
  }

  /** 官方 Pse：byte 频谱 → {low,mid,high} 0..1000 */
  function bands(byteFreqData, sampleRate = 48000, fftSize = ANALYSER.fftSize) {
    const out = {};
    for (const [name, lo, hi] of ANALYSER.BANDS) {
      out[name] = normalizeBand(bandRms(byteFreqData, lo, hi, sampleRate, fftSize), name);
    }
    return out;
  }

  function reset() { z = ANALYSER.FLOOR; bandBase.low = bandBase.mid = bandBase.high = ANALYSER.FLOOR; }
  return { timeDomainAmplitude, bands, reset, normalize };
}

// ============================ 4. 背景 / 渲染器（官方 _e / ve / xe / ye / be 系列） ============================

function makeRenderState(mode, params) {
  return {
    mode,
    amplitudeUI: params.amplitude ?? 50,          // 官方 g（1..100）
    backmode: params.backmode ?? 0,               // 官方 y
    backmodeBrightness: params.backmodeBrightness ?? 100, // 官方 b（10..100）
    amp: 0,                                        // 官方 x：归一化振幅 0..1
    smoothAmp: 0,                                  // 官方 w
    phase: 0,                                      // 官方 ie（渲染器各自的动画相位）
    huePhase: 0,                                   // 官方 oe
    smoothValue: 0,                                // 官方 se
    rotate: 0,                                     // 官方 T
  };
}

function fillSolid(grid, color, brightnessPct) {
  const k = round(brightnessPct * 2.55) / 256;
  const c = {
    r: round(round(brightnessPct * 2.55) * color.r / 256),
    g: round(round(brightnessPct * 2.55) * color.g / 256),
    b: round(round(brightnessPct * 2.55) * color.b / 256),
  };
  for (const row of grid) for (let i = 0; i < row.length; i++) row[i] = { ...c };
  return k;
}

/** 官方 xe：按行把网格分成 n 段颜色 */
function fillRowBands(grid, colors, brightnessPct) {
  const n = round(brightnessPct * 2.55);
  const rows = grid.length;
  const per = Math.floor(rows / colors.length);
  const extra = rows % colors.length;
  let rowIdx = 0;
  for (let ci = 0; ci < colors.length; ci++) {
    const cnt = per + (ci < extra ? 1 : 0);
    const c = {
      r: round(n * colors[ci].r / 256), g: round(n * colors[ci].g / 256),
      b: round(n * colors[ci].b / 256),
    };
    for (let k = 0; k < cnt && rowIdx < rows; k++, rowIdx++) {
      for (let col = 0; col < grid[rowIdx].length; col++) grid[rowIdx][col] = { ...c };
    }
  }
}

/** 官方 ye：以中心为原点的径向色相渐变 */
function fillRadialHue(grid, centerRow, centerCol, huePhase) {
  const rows = grid.length, cols = grid[0].length;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const angle = Math.atan2(r - centerRow, c - centerCol);
      let hue = huePhase + ((180 + (180 / Math.PI) * angle) % 360);
      if (hue < 0) hue += 360;
      if (hue >= 360) hue -= 360;
      grid[r][c] = kV(hue, 1, 1);
    }
  }
}

/** 官方 be：纯色旋转色相铺满 */
function fillSolidHue(grid, huePhase, brightnessPct) {
  const hue = round(huePhase) % 360;
  const v = brightnessPct / 255;
  void v;
  const c = kV(hue, 1, brightnessPct / 255);
  for (const row of grid) for (let i = 0; i < row.length; i++) row[i] = { ...c };
}

/** 官方 _e：应用背景模式 */
function applyBackground(grid, backmode, brightnessPct, st, centers) {
  switch (backmode) {
    case 6: fillSolid(grid, { r: 255, g: 255, b: 255 }, brightnessPct); break;
    case 7: fillSolid(grid, { r: 255, g: 0, b: 0 }, brightnessPct); break;
    case 8: fillSolid(grid, { r: 255, g: 64, b: 0 }, brightnessPct); break;
    case 9: fillSolid(grid, { r: 255, g: 255, b: 0 }, brightnessPct); break;
    case 10: fillSolid(grid, { r: 0, g: 0, b: 255 }, brightnessPct); break;
    case 11: fillSolid(grid, { r: 0, g: 255, b: 0 }, brightnessPct); break;
    case 1:
      fillRowBands(grid, [
        { r: 0, g: 255, b: 0 }, { r: 255, g: 255, b: 0 }, { r: 255, g: 0, b: 0 },
      ], brightnessPct);
      break;
    case 2:
      fillRowBands(grid, [
        { r: 255, g: 0, b: 255 }, { r: 0, g: 0, b: 255 }, { r: 0, g: 255, b: 255 },
        { r: 0, g: 255, b: 0 }, { r: 255, g: 255, b: 0 }, { r: 255, g: 0, b: 0 },
      ], brightnessPct);
      break;
    case 4: fillRadialHue(grid, centers.centerRow, centers.centerCol, st.huePhase); break;
    case 5: fillSolidHue(grid, st.huePhase, brightnessPct); break;
    default: break; // 0 / 3 等 = 不画背景
  }
}

// ------- 渲染器：mode 1 / 4（Fe：背景 + 包络柱状，官方 Fe） -------
function renderMode1or4(grid, mode, layout, st) {
  const n = st.amplitudeUI / 100;
  st.smoothAmp += (st.amp - st.smoothAmp) * n;
  const bg = zeros(layout.F, layout.P);
  applyBackground(bg, mode, st.backmodeBrightness, st, layout);
  st.phase += st.amplitudeUI / 1000;
  const i = Math.min(st.smoothAmp, 1);
  const bars = [];
  for (let e = 0; e < layout.P; e++) {
    const t = e / layout.P;
    const base = 0.2 + 0.3 * Math.cos(t * Math.PI);
    const w1 = Math.sin(st.phase * Math.PI * 1.8 + e * 0.7) * 0.2;
    const w2 = Math.sin(st.phase * Math.PI * 0.9 + e * 1.3) * 0.15;
    const w3 = Math.sin(st.phase * Math.PI * 2.3 + e * 0.4) * 0.1;
    const w4 = Math.sin(e * 2.1 + st.phase * 3.2) * 0.3;
    let l = base + w1 + w2 + w3 + w4;
    l = l < 0.1 ? 0 : Math.pow(l, 1.5);
    l = clamp(l, 0, 1.2);
    const u = i * (st.amplitudeUI / 8) * l * layout.F;
    bars[e] = Math.max(0, Math.floor(u));
  }
  for (let row = 0; row < layout.F; row++) {
    const target = layout.F - 1 - row;
    for (let col = 0; col < layout.P; col++) {
      if (target < bars[col]) grid[row][col] = bg[row] ? bg[row][col] : { r: 0, g: 0, b: 0 };
    }
  }
}

// ------- 渲染器：mode 14（Ce：中心 4 色旋转射线） -------
function renderMode14(grid, layout, st) {
  const t = st.amplitudeUI / 100;
  st.smoothAmp += (st.amp - st.smoothAmp) * t;
  st.rotate += 4;
  if (st.rotate >= 360) st.rotate -= 360;
  let maxDist = 0;
  for (let r = 0; r < layout.F; r++) {
    for (let c = 0; c < layout.P; c++) {
      const dr = c - layout.centerCol, dc = r - layout.centerRow;
      const d = Math.sqrt(dr * dr + dc * dc);
      if (d > maxDist) maxDist = d;
    }
  }
  const r1 = Math.min(st.smoothAmp, 1);
  const len = Math.max(1, maxDist * r1);
  const a = r1;
  const colors = [
    { r: 0, g: 255, b: 0 }, { r: 0, g: 0, b: 255 },
    { r: 255, g: 255, b: 0 }, { r: 255, g: 0, b: 0 },
  ];
  const angles = [0, 45, 90, 135];
  for (let k = 0; k < 4; k++) {
    const c = colors[k];
    const rad = ((angles[k] + st.rotate) % 360) * Math.PI / -180;
    const dx = Math.cos(rad) * a * 2;
    const dy = Math.sin(rad) * a * 1;
    for (let m = -len; m <= len; m += 0.5) {
      const col = round(layout.centerCol + dx * m);
      const row = round(layout.centerRow + dy * m);
      if (col >= 0 && col < layout.P && row >= 0 && row < layout.F) grid[row][col] = c;
    }
  }
}

// ------- 渲染器：mode 17（je：中心行正弦波） -------
function renderMode17(grid, layout, st) {
  const t = Math.min(st.amp, 1);
  st.phase += 0.5;
  if (st.phase >= Math.PI * 2) st.phase -= Math.PI * 2;
  st.huePhase = (st.huePhase + 0.02) % 1;
  const centers = layout.F % 2 === 0
    ? [Math.floor(layout.F / 2) - 1, Math.floor(layout.F / 2)]
    : [Math.floor(layout.F / 2)];
  for (let n = 0; n < layout.P; n++) {
    const phi = (n / layout.P) * Math.PI * 2;
    const wave = Math.sin(st.phase + phi);
    const fall = 1 - Math.pow(n / (layout.P - 1), 0.8);
    const scale = (1 + t * 2) * Math.max(0.3, st.amplitudeUI / 50) * fall;
    const c = round(wave * scale);
    const color = kV((n / layout.P * 360 + st.huePhase * 360) % 360, 1, 1);
    for (const cr of centers) {
      const row = cr + c;
      if (row >= 0 && row < layout.F) grid[row][n] = color;
      const trail = Math.min(3, Math.abs(c));
      for (let a = 1; a <= trail; a++) {
        const rr = cr + Math.sign(c) * a;
        if (rr >= 0 && rr < layout.F && rr !== row) {
          const f = 1 - a / (trail + 1);
          grid[rr][n] = { r: round(color.r * f * 0.6), g: round(color.g * f * 0.6), b: round(color.b * f * 0.6) };
        }
      }
    }
  }
}

// ------- 渲染器：mode 13（Se：中心同心环扩散，官方默认） -------
function buildFallbackRings(layout) {
  const rings = [];
  let maxR = 0;
  for (let t = 0; t < layout.F; t++) {
    for (let n = 0; n < layout.P; n++) {
      const dc = n - layout.centerCol, dr = t - layout.centerRow;
      maxR = Math.max(maxR, Math.sqrt(dc * dc + dr * dr));
    }
  }
  const r = Math.max(4, Math.ceil(maxR));
  for (let i = 0; i < r; i++) rings[i] = [];
  for (let t = 0; t < layout.F; t++) {
    for (let n = 0; n < layout.P; n++) {
      const dc = n - layout.centerCol, dr = t - layout.centerRow;
      const dist = Math.sqrt(dc * dc + dr * dr);
      const idx = Math.floor((dist / r) * (r - 0.01));
      const isCenter = idx === 0 && Math.abs(dc) < 0.5 && Math.abs(dr) < 0.5;
      if (!isCenter && idx >= 0 && idx < r) rings[idx].push({ row: t, col: n });
    }
  }
  // 官方修正：ring1 首元素移到 ring2、ring1 第 4 个或末尾也移到 ring2
  if (rings[1] && rings[1].length > 2 && rings[2]) {
    const a = rings[1].shift();
    let b = null;
    if (layout.F < 6) { b = rings[1][4]; rings[1].splice(4, 1); } else { b = rings[1].pop(); }
    if (a) rings[2].push(a);
    if (b) rings[2].push(b);
  }
  return rings;
}

function renderMode13(grid, layout, st) {
  const rings = buildFallbackRings(layout);
  const centerCells = rings[0] || [];
  const ringList = rings.slice(1);
  st.phase = (st.phase + 0.005) % 1;
  st.huePhase = (st.huePhase + 0.005) % 1;
  const ringCount = ringList.length;
  const phases = [];
  for (let e = 0; e < ringCount; e++) phases[e] = (st.phase - e / ringCount + 1) % 1;
  const amp = Math.min(st.amp, 1);
  const threshold = Math.max(0.01, 0.06 - amp * 0.05);
  const lit = amp < threshold ? 0 : Math.max(1, Math.min(ringCount, Math.round(st.amp * ringCount)));
  const k = st.amplitudeUI / 100;
  st.smoothValue += (lit - st.smoothValue) * k;
  const active = Math.round(st.smoothValue);
  // 中心点颜色
  const centerColor = kV((st.huePhase * 360) % 360, 1, 1);
  for (const cell of centerCells) {
    if (cell.row >= 0 && cell.row < layout.F && cell.col >= 0 && cell.col < layout.P) {
      grid[cell.row][cell.col] = centerColor;
    }
  }
  for (let e = 0; e < active; e++) {
    const ring = ringList[e];
    if (!ring || !ring.length) continue;
    const color = kV(((phases[e] + st.huePhase) * 360) % 360, 1, 1);
    for (const cell of ring) {
      if (cell.row >= 0 && cell.row < layout.F && cell.col >= 0 && cell.col < layout.P && cell.col < grid[cell.row].length) {
        grid[cell.row][cell.col] = color;
      }
    }
  }
}

// ============================ 5. 渲染调度 + 网格 → 载荷 ============================

/**
 * 一次 50ms tick：根据振幅渲染一帧网格
 * @returns grid[F][P+1] {r,g,b}
 */
function renderFrame(layout, st, mode) {
  const grid = zeros(layout.F, layout.width);
  if (st.backmode) applyBackground(grid, st.backmode, st.backmodeBrightness, st, layout);
  if (st.amp <= 0 && mode !== 13) {
    // 官方：无振幅时只发背景（mode 13 有中心点/回环仍可动，官方 he() 在 !e 时直接 me(t)）
  }
  switch (mode) {
    case 1: case 4: renderMode1or4(grid, mode, layout, st); break;
    case 13: renderMode13(grid, layout, st); break;
    case 14: renderMode14(grid, layout, st); break;
    case 17: renderMode17(grid, layout, st); break;
    default:
      // 其它官方渲染器（15/16/18/19/20/21/22）见 docs/_music_b2.js；
      // 这里回退到默认 ripple，便于先跑通链路
      renderMode13(grid, layout, st);
      break;
  }
  return grid;
}

/** 官方 me()：网格 → 4B/键 载荷（[keyValue, r, g, b] × 键数） */
function gridToPayload(grid, layout) {
  const out = new Uint8Array(layout.visible.length * 4);
  layout.visible.forEach((cell, i) => {
    const c = (grid[cell.row] && grid[cell.row][cell.col]) || { r: 0, g: 0, b: 0 };
    const o = i * 4;
    out[o] = cell.value & 0xFF;
    out[o + 1] = clamp(round(c.r), 0, 255);
    out[o + 2] = clamp(round(c.g), 0, 255);
    out[o + 3] = clamp(round(c.b), 0, 255);
  });
  return out;
}

// ============================ 6. 协议打包（官方 TZ = setMusicData） ============================

/**
 * USB 路径：cmd 50（0x32），每包 56 字节数据（14 键），头：
 *   [0]=0xAA [1]=0x32 [2]=本包数据长 [3..4]=addr(LE) [5]=i [6]=last [7]=0
 * 返回 Buffer[]（每个 = report ID 字节 0 + 64 字节报文）
 */
function packUsbMusicFrames(payload4BPerKey, opts = {}) {
  const reportPayload = opts.reportPayload || 64;      // 不含 report ID 字节
  const i = opts.i || 0;
  const chunk = reportPayload - 8;                     // 56
  const total = Math.ceil(payload4BPerKey.length / chunk) || 1;
  const packets = [];
  for (let k = 0; k < total; k++) {
    const addr = k * chunk;
    const part = payload4BPerKey.subarray(addr, Math.min(addr + chunk, payload4BPerKey.length));
    const pkt = Buffer.alloc(reportPayload + 1);
    pkt[0] = 0;                                        // report ID
    pkt[1] = 0xAA;
    pkt[2] = 0x32;                                     // GET_LED_DATA
    pkt[3] = part.length & 0xFF;                       // contentSize = 本包数据长
    pkt[4] = addr & 0xFF;
    pkt[5] = (addr >> 8) & 0xFF;
    pkt[6] = i & 0xFF;
    pkt[7] = k === total - 1 ? 1 : 0;                  // last flag
    pkt[8] = 0;
    Buffer.from(part).copy(pkt, 9);
    packets.push(pkt);
  }
  return packets;
}

/** 通用分支：cmd 53（0x35），payload = RGB565 流（无键号），4 字节自定义头 */
function packGenericMusicFrames(payload4BPerKey, opts = {}) {
  const reportPayload = opts.reportPayload || 64;
  const i = opts.i || 0;
  // 官方：每 4 字节一个键，转 RGB565 高低字节拼接
  const pairs = [];
  for (let e = 0; e < payload4BPerKey.length / 4; e++) {
    const n = e * 4;
    const [hi, lo] = jV(AV({ r: payload4BPerKey[n + 1], g: payload4BPerKey[n + 2], b: payload4BPerKey[n + 3] }));
    pairs.push(hi, lo);
  }
  const chunk = reportPayload - 4;                     // 60
  const total = Math.ceil(pairs.length / chunk) || 1;
  const packets = [];
  for (let k = 0; k < total; k++) {
    const part = Buffer.from(pairs.slice(k * chunk, (k + 1) * chunk));
    const pkt = Buffer.alloc(reportPayload + 1);
    pkt[0] = 0;
    pkt[1] = 0xAA;
    pkt[2] = 0x35;
    pkt[3] = k & 0xFF;                                 // 官方自定义头 c[2]=r（序号）
    pkt[4] = i & 0xFF;                                 // c[3]=i
    part.copy(pkt, 5);
    packets.push(pkt);
  }
  return packets;
}

/** 2.4G 64B 分支：cmd 60（0x3C），RGB565 流，8 字节头（otherHeader [i] / [i,0] 同 USB 逻辑） */
function pack24G64MusicFrames(payload4BPerKey, opts = {}) {
  const reportPayload = opts.reportPayload || 64;
  const i = opts.i || 0;
  const pairs = [];
  for (let e = 0; e < payload4BPerKey.length / 4; e++) {
    const n = e * 4;
    const [hi, lo] = jV(AV({ r: payload4BPerKey[n + 1], g: payload4BPerKey[n + 2], b: payload4BPerKey[n + 3] }));
    pairs.push(hi, lo);
  }
  const chunk = reportPayload - 8;                     // 56
  const total = Math.ceil(pairs.length / chunk) || 1;
  const packets = [];
  for (let k = 0; k < total; k++) {
    const addr = k * chunk;
    const part = Buffer.from(pairs.slice(addr, addr + chunk));
    const pkt = Buffer.alloc(reportPayload + 1);
    pkt[0] = 0;
    pkt[1] = 0xAA;
    pkt[2] = 0x3C;
    pkt[3] = part.length & 0xFF;
    pkt[4] = addr & 0xFF;
    pkt[5] = (addr >> 8) & 0xFF;
    pkt[6] = i & 0xFF;
    pkt[7] = k === total - 1 ? 1 : 0;
    pkt[8] = 0;
    part.copy(pkt, 9);
    packets.push(pkt);
  }
  return packets;
}

// ============================ 7. 引擎：把一个音频帧变成要发的 HID 包 ============================

class MusicEngine {
  constructor({ keyboardConfig, mode = 13, amplitude = 50, backmode = 0, backmodeBrightness = 100 } = {}) {
    this.config = keyboardConfig || loadMk87Config();
    this.layout = buildLayout(this.config);
    this.analyzer = createAudioAnalyzer();
    this.mode = mode;
    this.st = makeRenderState(mode, { amplitude, backmode, backmodeBrightness });
    this.lastPackets = null;
  }

  /** 每个 50ms tick 调一次：传当前音频（float 时域 或 byte 频谱） */
  tick({ floatTimeData, byteFreqData, sampleRate = 48000, testAmplitude } = {}) {
    let amp1000 = 0;
    if (typeof testAmplitude === 'number') amp1000 = testAmplitude;
    else if (floatTimeData) amp1000 = this.analyzer.timeDomainAmplitude(floatTimeData);
    else if (byteFreqData) {
      const b = this.analyzer.bands(byteFreqData, sampleRate);
      amp1000 = Math.max(b.low, b.mid, b.high); // 供渲染器参考；官方主循环用 K7
    }
    if (amp1000 > 0) { this.silence = 0; this.st.amp = Math.min(1, amp1000 / 1000); }
    else {
      this.silence = (this.silence || 0) + 1;
      if (this.silence >= 5) this.st.amp = 0; // 官方 C=5：连续 5 tick 静音才归零
    }
    this.st.huePhase = (this.st.huePhase + 0.01) % 1; // 官方 he() 里未显式加，渲染器内部自增
    const grid = renderFrame(this.layout, this.st, this.mode);
    const payload = gridToPayload(grid, this.layout);
    this.lastPackets = packUsbMusicFrames(payload, { i: 0 });
    return { amplitude: amp1000, grid, payload, packets: this.lastPackets };
  }

  setMode(mode) { this.mode = mode; this.st.mode = mode; }
  setAmplitude(v) { this.st.amplitudeUI = v; }
  setBackmode(v) { this.st.backmode = v; }
  setBackmodeBrightness(v) { this.st.backmodeBrightness = v; }
}

// ============================ 8. 自检 / 演示 ============================

function selfTest() {
  const results = [];
  const ok = (name, cond, extra = '') => results.push({ name, pass: !!cond, extra });

  const cfg = loadMk87Config();
  const layout = buildLayout(cfg);
  ok('MK87 行数=6', layout.F === 6, `F=${layout.F}`);
  ok('MK87 键数=87', layout.cells.length === 87, `n=${layout.cells.length}`);
  ok('网格宽度 = P+1', layout.width === layout.P + 1, `P=${layout.P} w=${layout.width}`);

  // 1) 载荷格式
  const st = makeRenderState(13, { amplitude: 60 });
  st.amp = 0.8;
  const grid = renderFrame(layout, st, 13);
  const payload = gridToPayload(grid, layout);
  ok('载荷 = 键数×4', payload.length === layout.visible.length * 4, `len=${payload.length}`);
  const pkts = packUsbMusicFrames(payload, { i: 7 });
  ok('USB 分包数 = ceil(348/56) = 7', pkts.length === 7, `n=${pkts.length}`);
  const p0 = pkts[0];
  ok('包头 AA 32', p0[1] === 0xAA && p0[2] === 0x32);
  ok('首包 last=0', p0[7] === 0);
  ok('末包 last=1', pkts[pkts.length - 1][7] === 1);
  ok('字节6 = i', p0[6] === 7);
  ok('首包 addr=0', p0[4] === 0 && p0[5] === 0);
  ok('第二包 addr=56', pkts[1][4] === 56);
  ok('总长 65 字节', p0.length === 65, `len=${p0.length}`);
  ok('末包数据长 12', pkts[6][3] === 12, `len=${pkts[6][3]}`);

  // 2) 音频归一化
  const an = createAudioAnalyzer();
  const zerosFloat = new Float32Array(2048);
  ok('静音 → 振幅 0', an.timeDomainAmplitude(zerosFloat) === 0);
  const loud = new Float32Array(2048).map((_, i) => Math.sin(i / 8) * 0.5);
  const a1 = an.timeDomainAmplitude(loud);
  ok('正弦 → 振幅 > 0', a1 > 0, `a=${a1}`);
  const a2 = an.timeDomainAmplitude(loud);
  ok('连续相同输入 → 归一化不爆炸', a2 >= 0 && a2 <= 1000, `a2=${a2}`);

  // 3) 渲染器输出范围 + 非全黑
  for (const mode of [1, 4, 13, 14, 17]) {
    const s = makeRenderState(mode, { amplitude: 80 });
    s.amp = 1.0;
    const g = renderFrame(layout, s, mode);
    let nonZero = 0, inRange = true;
    for (const row of g) for (const c of row) {
      if (c.r || c.g || c.b) nonZero++;
      if ([c.r, c.g, c.b].some((v) => !Number.isFinite(v) || v < 0 || v > 255)) inRange = false;
    }
    ok(`mode ${mode} 有颜色输出`, nonZero > 0, `cells=${nonZero}`);
    ok(`mode ${mode} 颜色在 0..255`, inRange);
  }

  // 4) RGB565 打包
  const g2 = zeros(layout.F, layout.width);
  g2[0][0] = { r: 255, g: 0, b: 0 };
  const p2 = gridToPayload(g2, layout);
  const gen = packGenericMusicFrames(p2);
  ok('通用分支包头 AA 35', gen[0][1] === 0xAA && gen[0][2] === 0x35);
  const g24 = pack24G64MusicFrames(p2);
  ok('24G 分支包头 AA 3C', g24[0][1] === 0xAA && g24[0][2] === 0x3C);
  const r565 = AV({ r: 255, g: 0, b: 0 });
  ok('RGB565 纯红 = 0xF800', r565 === 0xF800, `v=0x${r565.toString(16)}`);

  const modeList = MUSIC_MODES.map((m) => m.value).join(',');
  ok('模式表非空', MUSIC_MODES.length >= 10, modeList);
  ok('背景表非空', BG_MODES.length >= 10);

  for (const r of results) {
    console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name}${r.extra ? '  (' + r.extra + ')' : ''}`);
  }
  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n${results.length - failed}/${results.length} 通过`);
  if (failed) process.exitCode = 1;
}

function demo() {
  const cfg = loadMk87Config();
  const layout = buildLayout(cfg);
  const eng = new MusicEngine({ keyboardConfig: cfg, mode: 13, amplitude: 70 });
  // 用合成"音频"喂 3 个 tick
  const fakeAudio = new Float32Array(2048).map((_, i) => Math.sin(i / 6) * 0.35);
  for (let k = 0; k < 3; k++) {
    const r = eng.tick({ floatTimeData: fakeAudio, sampleRate: 48000 });
    console.log(`tick ${k}: amplitude(0..1000)=${r.amplitude} 包数=${r.packets.length} ` +
      `载荷前 8 字节=${Array.from(r.payload.slice(0, 8)).map((x) => x.toString(16).padStart(2, '0')).join(' ')}`);
    console.log('  首包:', Array.from(r.packets[0].slice(0, 16)).map((x) => x.toString(16).padStart(2, '0')).join(' '));
  }
  console.log('\n假设 50ms/tick（20fps），每帧 7 包，共 140 包/秒；每包 65 字节 → 约 9.1 KB/s。');
}

if (require.main === module) {
  if (process.argv.includes('--demo')) demo();
  else { selfTest(); if (!process.exitCode) { console.log('\n=== demo ==='); demo(); } }
}

module.exports = {
  ANALYSER, MUSIC_MODES, BG_MODES, CMD,
  kV, AV, jV, buildLayout, loadMk87Config, createAudioAnalyzer,
  makeRenderState, renderFrame, gridToPayload,
  packUsbMusicFrames, packGenericMusicFrames, pack24G64MusicFrames, MusicEngine,
};
