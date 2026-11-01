#!/usr/bin/env node
/**
 * lighting_ref.js — AJAZZ MK87 (VID 0x0C45 / PID 0x8047) 灯效协议参考实现 + 自检
 *
 * 纯静态逆向产物：所有编码规则来自官方网页驱动 bundle 的静态分析，
 * 自检时把 bundle 里的**官方实现原样取出来 eval**（同一个文件、同一段源码），
 * 与自己写的编码器逐字节对比，所以 PASS 的含义是「与官方字节级一致」。
 *
 * 用法：
 *   node scripts/lighting_ref.js                 # 跑全部自检，打印 PASS/FAIL 摘要
 *   node scripts/lighting_ref.js --verbose       # 每条用例都打印
 *   node scripts/lighting_ref.js --dump          # 额外打印各模式 16 字节样例
 *   node scripts/lighting_ref.js encode '{"mode":7,"red":255,"green":0,"blue":0}'   # 打印 16 字节 hex
 *   node scripts/lighting_ref.js custom '[{"r":255,"g":0,"b":0},...]'                # 打印 512 字节 hex
 *
 * 只读 bundle，不打开任何 HID 设备。
 */
'use strict';
const fs = require('fs');
const path = require('path');

const BUNDLE = 'C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js';

// ---------------------------------------------------------------- 协议常量
const CMD = {
  GET_LED_EFFECT: 19,          // 0x13
  SET_LED_EFFECT: 35,          // 0x23
  GET_CUSTOM_LED_DATA: 20,     // 0x14
  SET_CUSTOM_LED_DATA: 36,     // 0x24
  GET_LED_DATA: 50,            // 0x32 (音乐律动写入复用此命令)
  CLEAR_LED_DATA: 54,          // 0x36
  SET_LED_USER_ANIMATION: 65,  // 0x41
  SET_LED_DATA: 66,            // 0x42
};

const LED_EFFECT_LEN = 16;
const CUSTOM_LED_LEN = 512;    // 128 × [ledId, R, G, B]
const CUSTOM_LED_COUNT = 128;

/** 灯效模式（MK87 实际可见列表 = 1..19 + 128；完整表见 docs/lighting-modes.json） */
const MODES = {
  1: '静态恒亮', 2: '单点亮', 3: '单熄灭', 4: '繁星点点', 5: '漫天飞雪', 6: '百花争艳',
  7: '动态呼吸', 8: '光谱循环', 9: '彩泉涌动', 10: '多彩纵横', 11: '随波逐流', 12: '峰回路转',
  13: '一触即发', 14: '一石二鸟', 15: '涟漪扩散', 16: '川流不息', 17: '重峦叠嶂', 18: '斜风细雨',
  19: '来回穿梭', 128: '自定义',
  // 协议配置里存在、但 MK87 的 lightingConfig 没把它们放进 customEffect → UI 不显示
  23: '彩虹风车', 24: '七彩聚拢', 25: '霓虹叠影', 254: '心动时刻', 26: '生命潮汐', 27: '硅基呼吸',
  28: '渐变常亮', 29: '单色呼吸', 30: '动态常亮', 31: '多彩纵横1', 32: 'RGB 动态呼吸', 33: '多彩纵横2',
};
/** MK87 的 UI 模式列表（顺序 = lightingList 排序后） */
const MK87_MODE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 128];
/** 需要方向按钮的模式 + 出厂 directionValue（directionPosition 决定按钮图标朝向） */
const DIRECTION_DEFAULT = { 10: 3, 11: 0, 12: 0, 16: 0, 18: 0 };
const CUSTOM_LIGHTING_MODE = 128;
const CUSTOM_MODE_FAMILY = [20, 21, 128];   // 官方 isCustomMode 判定

// ---------------------------------------------------------------- 编码器（本参考实现）
function u8(v) { return v === undefined || v === null ? 0 : v; }

/**
 * SET_LED_EFFECT(35) 16 字节 payload 编码。
 * 官方实现（bundle 内 vZ）：
 *   [0]=mode [1]=R [2]=G [3]=B [4]=255(硬编码) [5..7]=副色
 *   [8]=colorMode [9]=brightness [10]=speed [11]=direction [12]=effectModeType
 *   [13]=0 [14]=0xAA [15]=0x55
 * 兼容短字段（r/g/b、secondaryR/G/B）；缺省按 0 处理（与官方 Uint8Array 隐式转换一致）。
 */
function encodeLedEffect(o = {}) {
  const b = new Uint8Array(LED_EFFECT_LEN);
  b[0] = u8(o.mode);
  b[1] = u8(o.red !== undefined ? o.red : o.r);
  b[2] = u8(o.green !== undefined ? o.green : o.g);
  b[3] = u8(o.blue !== undefined ? o.blue : o.b);
  b[4] = 255;                                    // ← 官方硬编码，不接受外部参数
  b[5] = u8(o.secondaryRed !== undefined ? o.secondaryRed : o.sr);
  b[6] = u8(o.secondaryGreen !== undefined ? o.secondaryGreen : o.sg);
  b[7] = u8(o.secondaryBlue !== undefined ? o.secondaryBlue : o.sb);
  b[8] = u8(o.colorMode);
  b[9] = u8(o.brightness);
  b[10] = u8(o.speed);
  b[11] = u8(o.direction);
  b[12] = u8(o.effectModeType);
  b[13] = 0;
  b[14] = 0xAA;
  b[15] = 0x55;
  return b;
}

/** 反向解析（等价官方 _Z / GET_LED_EFFECT 解码） */
function decodeLedEffect(bytes) {
  const r = Uint8Array.from(bytes);
  return {
    mode: r[0], red: r[1], green: r[2], blue: r[3], driverSetting: r[4],
    secondaryRed: r[5], secondaryGreen: r[6], secondaryBlue: r[7],
    colorMode: r[8], brightness: r[9], speed: r[10], direction: r[11],
    effectModeType: r[12], checkCodeL: r[14], checkCodeH: r[15],
  };
}

/**
 * SET_CUSTOM_LED_DATA(36) 512 字节 payload。
 * 官方实现（bundle 内 bZ）：index 字节写的是**数组下标**，不是颜色对象的 ledId 字段；
 * 颜色对象只读 red/green/blue 三个长字段（只给 r/g/b 时官方写入 0，本实现严格保持一致），
 * 缺项按 0。超过 128 项截断，不足补 0。
 */
function buildCustomLedPayload(colors = []) {
  const b = new Uint8Array(CUSTOM_LED_LEN);
  const n = Math.min(colors.length || 0, CUSTOM_LED_COUNT);
  for (let i = 0; i < n; i++) {
    const c = colors[i] || {};
    b[i * 4] = i;
    b[i * 4 + 1] = u8(c.red);
    b[i * 4 + 2] = u8(c.green);
    b[i * 4 + 3] = u8(c.blue);
  }
  return b;
}

/** 512 字节 → [{ledId,red,green,blue}]（等价官方 yZ / GET_CUSTOM_LED_DATA 解码） */
function parseCustomLedPayload(bytes) {
  const r = Uint8Array.from(bytes).slice(0, CUSTOM_LED_LEN);
  const out = [];
  for (let i = 0; i < CUSTOM_LED_COUNT; i++) {
    out.push({ ledId: r[i * 4], red: r[i * 4 + 1], green: r[i * 4 + 2], blue: r[i * 4 + 3] });
  }
  return out;
}

/** 8 字节流式帧头（SET_LED_DATA / SET_LED_USER_ANIMATION / 任何 customHeader 通道） */
function frameHeader(cmd, seq, total) {
  const h = new Uint8Array(8);
  h[0] = 0xAA; h[1] = cmd;
  h[2] = (seq >> 8) & 0xFF; h[3] = seq & 0xFF;
  h[4] = (total >> 8) & 0xFF; h[5] = total & 0xFF;
  return h;
}

/** LED 动画 4 字节前导：[帧数 LE16][ceil(106-speed) LE16]（官方 UZ/MZ 一致） */
function animationPreamble(frameCount, speed) {
  const p = new Uint8Array(4);
  const delay = Math.ceil(106 - speed);
  p[0] = frameCount & 0xFF; p[1] = (frameCount >> 8) & 0xFF;
  p[2] = delay & 0xFF; p[3] = (delay >> 8) & 0xFF;
  return p;
}

/** 把 colors（[{r,g,b}]）拼成帧动画 payload = 4 字节前导 + 逐帧逐键 RGB */
function buildLedAnimationPayload(frames, speed) {
  const flat = [];
  for (const f of frames) for (const c of f) flat.push(u8(c.r), u8(c.g), u8(c.b));
  const head = animationPreamble(frames.length, speed);
  const out = new Uint8Array(head.length + flat.length);
  out.set(head, 0);
  out.set(flat, head.length);
  return out;
}

const hex = (arr) => Buffer.from(arr).toString('hex').toUpperCase();
const hexSpaced = (arr) => Array.from(arr).map(v => v.toString(16).padStart(2, '0').toUpperCase()).join(' ');

// ---------------------------------------------------------------- 官方实现加载器
let BUNDLE_SRC = null;
/** 从 bundle 里按 `name=async(...)=>...` 取出源码（括号配平），返回可调用函数 */
function loadOfficial(name, { BX, NX, HX, LX }) {
  const src = BUNDLE_SRC || (BUNDLE_SRC = fs.readFileSync(BUNDLE, 'utf8'));
  const re = new RegExp(name.replace(/\$/g, '\\$') + '\\s*=\\s*(?:async\\s*)?');
  const m = re.exec(src);
  if (!m) throw new Error('official impl not found: ' + name);
  let i = m.index + m[0].length;
  // 找到函数体起点：'(' 形参 → '{' 函数体；或单参箭头后直接 '{'
  let bodyStart = -1;
  if (src[i] === '(') bodyStart = src.indexOf('{', src.indexOf('=>', i));
  else bodyStart = src.indexOf('{', i);
  const end = matchPair(src, bodyStart);
  const code = src.slice(m.index, end + 1);
  const factory = new Function(
    'BX', 'NX', 'HX', 'LX', 'module', 'exports',
    'var module={exports:{}},exports=module.exports;' + code + '\nreturn ' + name + ';'
  );
  return { fn: factory(BX, NX, HX, LX, undefined, undefined), code, offset: m.index, end };
}

const OPENERS = '({[', CLOSERS = ')}]';
function matchPair(s, start) {
  let depth = 0, i = start, state = 'code';
  while (i < s.length) {
    const c = s[i], n = s[i + 1];
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; i += 2; continue; }
      if (c === '/' && n === '*') { state = 'block'; i += 2; continue; }
      if (c === '"' || c === "'" || c === '`') { state = c; i++; continue; }
      if (OPENERS.includes(c)) depth++;
      else if (CLOSERS.includes(c)) { depth--; if (!depth) return i; }
      i++; continue;
    }
    if (state === 'line') { if (c === '\n') state = 'code'; i++; continue; }
    if (state === 'block') { if (c === '*' && n === '/') { state = 'code'; i += 2; continue; } i++; continue; }
    if (c === '\\') { i += 2; continue; }
    if (c === state) state = 'code';
    i++;
  }
  return -1;
}

// ---------------------------------------------------------------- 自检
let pass = 0, fail = 0;
const failures = [];
function check(label, mine, official) {
  const a = hex(mine), b = hex(official);
  if (a === b) { pass++; if (VERBOSE) console.log(`  PASS ${label}`); return true; }
  fail++;
  failures.push({ label, mine: a, official: b });
  console.log(`  FAIL ${label}\n       mine    =${a}\n       official=${b}`);
  return false;
}
const VERBOSE = process.argv.includes('--verbose');

function makeHarness() {
  const captured = [];
  const BX = { deviceStorage: { deviceInfo: { frameVersion: 0 }, ledEffect: null, customLedData: null } };
  const NX = async (dev, opts) => { captured.push({ ...opts, dev }); return []; };
  const HX = { ...CMD };
  const LX = async () => device;
  const device = {
    productId: 0x8047, connectType: '2.4G',
    collections: [{ outputReports: [{ items: [{ reportCount: 4104 }] }] }],
  };
  return { captured, BX, NX, HX, LX, device };
}

/** 用官方函数跑一次，返回它实际发给设备的数据 */
async function officialCall(loaderArgs, fnName, argsBuilder, { payloadLen } = {}) {
  const h = makeHarness();
  const { fn } = loadOfficial(fnName, h);
  await fn(h.device, { connectType: '2.4G', productId: 0x8047 }, ...argsBuilder());
  const caps = h.captured;
  if (!payloadLen) return { caps, data: caps.length ? caps[0].data : null };
  // 多包通道：把各包 data 拼起来，截到逻辑长度
  const joined = Buffer.concat(caps.map(c => Buffer.from(c.data || [])));
  return { caps, data: joined.subarray(0, payloadLen) };
}

async function selfTest() {
  console.log('== AJAZZ MK87 lighting_ref self-test ==');
  console.log('bundle:', BUNDLE, `(${fs.statSync(BUNDLE).size} bytes)`);
  console.log('');

  // 1) SET_LED_EFFECT — 官方 vZ vs 本实现
  console.log('[1] encodeLedEffect  vs  bundle vZ (SET_LED_EFFECT 16B)');
  const { fn: vZ } = loadOfficial('vZ', makeHarness());
  const cases = [];
  for (const mode of MK87_MODE_ORDER) {
    cases.push({ mode, red: 255, green: 255, blue: 255, secondaryRed: 0, secondaryGreen: 0, secondaryBlue: 0, colorMode: 1, brightness: 5, speed: 3, direction: 0, effectModeType: 0 });
  }
  cases.push({ mode: 1, red: 255, green: 255, blue: 255, colorMode: 1, brightness: 5, speed: 3, direction: 0 }); // 真机回读
  cases.push({ mode: 0, brightness: 0, speed: 0, colorMode: 0 });                                             // 关灯
  cases.push({ mode: 1, red: 0, green: 0, blue: 0, colorMode: 0, brightness: 1, speed: 1, direction: 0 });
  cases.push({ mode: 254, red: 12, green: 34, blue: 56, secondaryRed: 78, secondaryGreen: 90, secondaryBlue: 123, colorMode: 0, brightness: 6, speed: 6, direction: 3, effectModeType: 3 });
  for (const m of [23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 128]) {
    cases.push({ mode: m, red: m, green: 255 - m, blue: (m * 7) & 0xFF, secondaryRed: 1, secondaryGreen: 2, secondaryBlue: 3, colorMode: m & 1, brightness: 6, speed: 6, direction: 3, effectModeType: 3 });
  }
  let rnd = 12345;
  const rand = () => (rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF) & 0xFF;
  for (let k = 0; k < 400; k++) {
    cases.push({ mode: rand(), red: rand(), green: rand(), blue: rand(), secondaryRed: rand(), secondaryGreen: rand(), secondaryBlue: rand(), colorMode: rand(), brightness: rand(), speed: rand(), direction: rand(), effectModeType: rand() });
  }
  for (const c of cases) {
    const off = await officialCall(null, 'vZ', () => [c]);
    check(`mode=${c.mode} bri=${c.brightness} spd=${c.speed} dir=${c.direction} cm=${c.colorMode} emt=${c.effectModeType}`, encodeLedEffect(c), off.data);
  }
  // 真机回读交叉验证（protocol.md §6 实测 raw）
  const devReadback = '01FFFFFFFF000000010503000000AA55';
  const mineDev = hex(encodeLedEffect({ mode: 1, red: 255, green: 255, blue: 255, colorMode: 1, brightness: 5, speed: 3, direction: 0 }));
  if (mineDev === devReadback) { pass++; console.log(`  PASS 真机回读交叉验证 (protocol.md §6): ${mineDev}`); }
  else { fail++; failures.push({ label: 'device readback', mine: mineDev, official: devReadback }); console.log(`  FAIL 真机回读 mine=${mineDev} expected=${devReadback}`); }

  // 2) SET_CUSTOM_LED_DATA — 官方 bZ vs 本实现
  console.log('[2] buildCustomLedPayload  vs  bundle bZ (SET_CUSTOM_LED_DATA 512B)');
  const custom = [];
  custom.push(Array.from({ length: 128 }, (_, i) => ({ red: i, green: 255 - i, blue: (i * 3) & 0xFF })));
  custom.push(Array.from({ length: 128 }, () => ({ red: 0, green: 0, blue: 0 })));
  custom.push(Array.from({ length: 128 }, () => ({ red: 255, green: 255, blue: 255 })));
  custom.push(Array.from({ length: 10 }, (_, i) => ({ red: i * 20, green: 7, blue: 200 })));   // 不足 128
  custom.push(Array.from({ length: 200 }, (_, i) => ({ red: i & 0xFF, green: 1, blue: 2 })));  // 超 128 → 截断
  custom.push([{ r: 1, g: 2, b: 3 }, { r: 4, g: 5, b: 6 }]);   // 只给短字段名 r/g/b → 官方写 0，本实现同样写 0
  custom.push(Array.from({ length: 128 }, (_, i) => ({ red: 255, green: 0, blue: 0, ledId: 200 - i })));  // ledId ≠ index → 索引仍写下标
  for (const [i, colors] of custom.entries()) {
    const off = await officialCall(null, 'bZ', () => [colors]);
    check(`custom case #${i} (n=${colors.length})`, buildCustomLedPayload(colors), off.data);
  }
  const twoColors = buildCustomLedPayload([{ red: 1, green: 2, blue: 3 }, { red: 4, green: 5, blue: 6 }]);
  const idxOk = twoColors[0] === 0 && twoColors[4] === 1 && twoColors[1] === 1 && twoColors[5] === 4;
  if (idxOk) { pass++; console.log('  PASS 512B 里 index 字节写的是数组下标（不是颜色对象的 ledId）'); }
  else { fail++; failures.push({ label: 'index byte', mine: '-', official: '-' }); }
  // 官方读回（yZ）解码一致性
  const back = await (async () => {
    const h = makeHarness();
    const payload = buildCustomLedPayload(custom[0]);
    h.NX = async () => {
      const frame = new Uint8Array(8 + 512);
      frame.set(payload, 8);
      return [frame];
    };
    const { fn } = loadOfficial('yZ', h);
    return fn(h.device);
  })();
  const mineBack = parseCustomLedPayload(buildCustomLedPayload(custom[0]));
  const backOk = JSON.stringify(back) === JSON.stringify(mineBack);
  if (backOk) { pass++; console.log('  PASS parseCustomLedPayload 与官方 yZ 解码一致 (128×{ledId,red,green,blue})'); }
  else { fail++; failures.push({ label: 'parse custom', mine: JSON.stringify(mineBack).slice(0, 80), official: JSON.stringify(back).slice(0, 80) }); console.log('  FAIL parseCustomLedPayload'); }

  // 3) LED 动画通道（GIF 灯效）— 官方 UZ/MZ vs 本实现（比较逻辑 payload 与每包 8 字节头）
  console.log('[3] buildLedAnimationPayload  vs  bundle UZ/MZ (4B 前导 + RGB 帧流)');
  const frames = [
    [{ r: 1, g: 2, b: 3 }, { r: 4, g: 5, b: 6 }, { r: 7, g: 8, b: 9 }],
    [{ r: 10, g: 11, b: 12 }, { r: 13, g: 14, b: 15 }, { r: 16, g: 17, b: 18 }],
  ];
  const speed = 50;                      // delay = ceil(106-50) = 56
  const mineAnim = buildLedAnimationPayload(frames, speed);
  for (const [name, cmdn, apiName] of [['UZ', CMD.SET_LED_USER_ANIMATION, 'setLedUserAnimation'], ['MZ', CMD.SET_LED_DATA, 'setGifLighting']]) {
    const h = makeHarness();
    const { fn } = loadOfficial(name, h);
    await fn(h.device, { connectType: '2.4G', productId: 0x8047 }, animationPreamble(frames.length, speed), frames.flat());
    const joined = Buffer.concat(h.captured.map(c => Buffer.from(c.data || []))).subarray(0, mineAnim.length);
    check(`${name}(${apiName}) payload (${frames.length} 帧)`, mineAnim, joined);
    const hdrOk = h.captured.every((c, i) => {
      const exp = frameHeader(cmdn, i, h.captured.length);
      return hex(c.customHeader) === hex(exp);
    });
    if (hdrOk) { pass++; console.log(`  PASS ${name} 8 字节流式帧头 AA ${cmdn.toString(16).toUpperCase()} seqHi seqLo totalHi totalLo 0 0`); }
    else { fail++; failures.push({ label: name + ' header', mine: 'header mismatch', official: hex(h.captured[0]?.customHeader || []) }); console.log(`  FAIL ${name} 帧头`); }
  }

  // 4) 模式表完整性
  console.log('[4] 模式表 / 参数域自检');
  const mk87 = MK87_MODE_ORDER.every(m => MODES[m]);
  if (mk87) { pass++; console.log(`  PASS MK87 UI 模式列表 ${MK87_MODE_ORDER.length} 项全部有名称: ${MK87_MODE_ORDER.join(',')}`); }
  else { fail++; failures.push({ label: 'mode table', mine: 'missing name', official: '-' }); console.log('  FAIL 模式表缺名称'); }
  const dirOk = [0, 1, 2, 3].every(d => encodeLedEffect({ direction: d })[11] === d);
  if (dirOk) { pass++; console.log('  PASS direction 0/1/2/3 原样落入 [11]（0=右 1=左 2=上 3=下）'); }
  else { fail++; failures.push({ label: 'direction', mine: '-', official: '-' }); }
  const briOk = [1, 6].every(v => encodeLedEffect({ brightness: v })[9] === v) && encodeLedEffect({ brightness: 0 })[9] === 0;
  if (briOk) { pass++; console.log('  PASS brightness 1..6 落 [9]、0 也原样下发（协议不校验，UI 最小值为 1）'); }
  else { fail++; failures.push({ label: 'brightness', mine: '-', official: '-' }); }

  console.log('');
  console.log(`== 结果: PASS ${pass} / FAIL ${fail} ==`);
  if (fail) {
    console.log('失败用例:');
    for (const f of failures) console.log(` - ${f.label}\n   mine=${f.mine}\n   off =${f.official}`);
    process.exitCode = 1;
  }
  return { pass, fail };
}

// ---------------------------------------------------------------- CLI
(async () => {
  const argv = process.argv.slice(2);
  if (argv[0] === 'encode') {
    const o = JSON.parse(argv[1] || '{}');
    const b = encodeLedEffect(o);
    console.log(hexSpaced(b));
    console.log(hex(b));
    return;
  }
  if (argv[0] === 'custom') {
    const colors = JSON.parse(argv[1] || '[]');
    const b = buildCustomLedPayload(colors);
    console.log(`len=${b.length}`);
    console.log(hex(b));
    return;
  }
  if (argv.includes('--dump')) {
    console.log('模式 | 名称 | 16 字节 payload（默认参数 colorMode=1,brightness=5,speed=3,direction=0）');
    for (const m of MK87_MODE_ORDER) {
      const b = encodeLedEffect({ mode: m, red: 255, green: 255, blue: 255, colorMode: 1, brightness: 5, speed: 3, direction: DIRECTION_DEFAULT[m] ?? 0 });
      console.log(`${String(m).padStart(3)} | ${MODES[m]} | ${hexSpaced(b)}`);
    }
    console.log('');
  }
  await selfTest();
})().catch(e => { console.error('ERROR', e); process.exit(1); });
