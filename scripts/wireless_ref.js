#!/usr/bin/env node
// =============================================================================
// wireless_ref.js — AJAZZ MK87 网页驱动「2.4G 无线 / 多 Profile / 灯效动画上传」
// 逆向结论的可执行参考实现 + 自检（与 bundle 里官方实现逐字节对照）
//
// 用法：
//   node scripts/wireless_ref.js            # 跑全部自检，打印 PASS/FAIL
//   node scripts/wireless_ref.js --verbose  # 额外打印每包 hex
//   node scripts/wireless_ref.js --dump     # 只打印 24G/Profile/动画样例报文
//
// 自检原理（不碰任何 HID 设备）：
//   1. 把 docs/infra.js（官方 PX/IX/FX/NX 帧层）与 docs/protocol_commands.js
//      （官方 66 条命令实现）载入 vm 沙箱；
//   2. 造一个 mock HID 设备（只实现 collections / sendReport / addEventListener，
//      按需回造响应帧），让「官方代码」真的跑一遍，捕获它发出的原始报文；
//   3. 用本文件里我重写的构造函数生成同样的报文，逐字节比较；
//   4. 解析类（24G 读回）用同一批伪造响应，比较官方返回值与我的解析结果。
//   → 因此 PASS 表示「我的理解 == bundle 里官方实现的实际行为」。
//
// 官方实现位置（bundle 偏移，assets/layout-classic-CMxiG14P.js）：
//   HX 命令表 ......... @1915656 附近（见 docs/command_enum.txt）
//   MX sendReport 包装  @1909802
//   NX 发送/重试 ...... @1910023
//   PX 帧构造 ......... @1911457
//   FX 响应头解析 ..... @1911775
//   IX 响应等待 ....... @1911917
//   LX TFT 通道定位 ... @1912495
//   iQ setProfile ..... @1953899
//   DZ cmd51 / OZ cmd55 / kZ cmd59 / TZ setMusicData / MZ setGifLighting /
//   HZ setLedSyncAnimation / UZ setLedUserAnimation / VZ clearLedData ..... @1934410..@1949962
//   WX deviceInit ..... @1916075      GX getDeviceInfo ..... @1917136
//   XX/QX/ZX/$X 监听 .. @1919506 / @1920304 / @1919911 / @1920705
//   S 特殊 2.4G 表 .... @1832488（64 项 vid:pid:productName）
//   oe 完整设备 ID .... @1840806
//   24G store 状态机 .. @1832097..1842253（is24GSleeping / 三个监听器挂载）
//   profiles 模块 ..... @1983554 起（oQ：SQ/vQ/bQ/CQ/xQ…）
//   profile 页面 ...... assets/useProfiles-Bm0j-YvT.js
//   gifLighting 组合式  @2268676（g7）、编辑器 @2274519（Eae）、上传 S() @2270860
//   led 动画页面 ...... @2240031..2251461（ledMaxFrames/260/200 帧规则）
// =============================================================================
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');
const BUNDLE = path.join(ROOT, 'assets', 'layout-classic-CMxiG14P.js');
const VERBOSE = process.argv.includes('--verbose');
const DUMP = process.argv.includes('--dump');

// =============================================================================
// 0. 常量（来自 bundle 的 HX 枚举 / 实测推断，见 docs/wireless-constants.json）
// =============================================================================
const HX = {
  GET_DEVICE_INFO: 16,
  SET_LED_EFFECT: 35,
  GET_LED_DATA: 50,
  GET_ALL_LIGHTS_RGB: 51,
  SET_TEMPORARY_COMMAND_DATA: 52,
  SET_MUSIC_DATA: 53,
  CLEAR_LED_DATA: 54,
  GET_ALL_LIGHTS_RGB_24G: 55,
  GET_ALL_LIGHTS_RGB_24G_64_BYTE: 59,
  SET_MUSIC_DATA_24G_64_BYTE: 60,
  SET_LED_BOOT_ANIMATION: 64,
  SET_LED_USER_ANIMATION: 65,
  SET_LED_DATA: 66,
  SET_PROFILE: 144,
  GET_DEVICE_NOTIFY: 250,
  GET_24G_DISCONNECT_NOTIFY: 252,
};

// 报文常量
const FRAME_REQ_MAGIC = 0xaa;   // 请求帧首字节
const FRAME_RESP_MAGIC = 0x55;  // 响应/通知帧首字节
const FRAME_WAKE_MAGIC = 0xa6;  // 2.4G 唤醒通知首字节（唯一的非 0x55 帧）

// 24G 通知子类型（cmd 252 的第 3 字节）
const NOTIFY_24G = {
  4: 'disconnect',  // 接收器丢键盘 → 关闭设备 + 回首页 + 报错
  5: 'reset',       // 键盘复位 → location.reload()
  6: 'sleep',       // 休眠 → is24GSleeping = true
};
// 设备状态通知（cmd 250）已知子类型
const NOTIFY_DEVICE = {
  6: 'tftInfoToggle', // 第 4 字节 1=开始轮询屏幕系统信息, 0=停止
};

// 灯效动画/音乐参数
const ANIM = {
  GIF_MAX_FRAMES_OFFSET: 24,   // 官方 GX：gifMaxFrames=i[24..25]
  LED_MAX_FRAMES_OFFSET: 26,   // 官方 GX：ledMaxFrames=i[26..27]
  LED_FRAMES_FALLBACK: 260,    // deviceInfo.ledMaxFrames===0 时的兜底帧数
  BOOT_ANIMATION_MAX: 200,     // ledId==='startup' / 'LEOBOG_AMG65' 的帧数上限
  SPEED_MIN: 50,               // gif 编辑器导入时 clamp 到 50..104
  SPEED_MAX: 104,
  SPEED_DEFAULT: 100,
  DELAY_BASE: 106,             // delay = ceil(106 - speed)
  DATA_PER_PACKET_TRIM: 8,     // 动画数据每包容量 = reportCount - 8
  HEADER_BYTES: 8,             // 动画头实为 8 字节：[AA,cmd,seqHi,seqLo,totalHi,totalLo,0,0]
};

// =============================================================================
// 1. 官方 PX 帧构造的等价实现（逐行对照 bundle @1909432）
// =============================================================================
function px(cmd, len, addr, data, size, otherHeader, customHeader, lastFlag) {
  const c = new Uint8Array(size).fill(0);
  if (customHeader) {
    c.set(customHeader, 0);
    if (data) c.set(data, customHeader.length);
    return c;
  }
  c[0] = FRAME_REQ_MAGIC;
  c[1] = cmd;
  c[2] = len & 0xff;
  c[3] = addr & 0xff;
  c[4] = (addr >> 8) & 0xff;
  if (otherHeader && Array.isArray(otherHeader)) {
    for (let i = 0; i < Math.min(otherHeader.length, 3); i++) {
      if (otherHeader[i] !== undefined) c[5 + i] = otherHeader[i] & 0xff;
    }
  }
  if (!otherHeader || otherHeader.length < 2 || otherHeader[1] === undefined) {
    c[6] = +!!lastFlag;
  }
  if (data) c.set(data, 8);
  return c;
}

// 标准 8 字节头 + 数据分包（NX 的等价：每包 reportCount-8 字节）
function frame8({ cmd, reportCount = 64, data = new Uint8Array(0), addrStart = 0, otherHeader, lastFlag = true }) {
  const packets = [];
  const chunk = reportCount - 8;
  const total = Math.ceil(data.length / chunk) || 1;
  for (let p = 0; p < total; p++) {
    const off = p * chunk;
    const part = data.subarray(off, Math.min(off + chunk, data.length));
    const len = data.length === 0 ? 0 : part.length;
    packets.push(px(cmd, len, addrStart + off, part, reportCount, otherHeader, undefined, p === total - 1 && lastFlag));
  }
  return packets;
}

// =============================================================================
// 2. 24G 专用构造器
// =============================================================================

// 2.1 GET_ALL_LIGHTS_RGB_24G(55)：4 字节自定义头 [AA,55,包序号,0]，每包 reportCount-4 字节
function build24GAllLightsReadPackets(ledCount, reportCount = 64) {
  const perPacket = reportCount - 4;
  const totalBytes = ledCount * 2 + 1;          // 官方 a = n*2+1（多算 1 字节电量）
  const packets = Math.ceil(totalBytes / perPacket);
  const out = [];
  for (let p = 0; p < packets; p++) {
    const hdr = Uint8Array.from([FRAME_REQ_MAGIC, HX.GET_ALL_LIGHTS_RGB_24G, p & 0xff, 0]);
    out.push(px(HX.GET_ALL_LIGHTS_RGB_24G, perPacket, 0, new Uint8Array(perPacket), reportCount, undefined, hdr));
  }
  return out;
}

// 2.2 解析 cmd55 响应：resp[0][3]=电量，resp[*].slice(4) 拼起来 = 每灯 2 字节 RGB565(大端)
//    官方最后会 slice(0, ledCount*2)，这里保持一致
function parse24GAllLights(responses, ledCount) {
  const battery = responses.length ? responses[0][3] : 0;
  const flat = [];
  for (const r of responses) for (let i = 4; i < r.length; i++) flat.push(r[i]);
  const want = ledCount * 2;
  const leds = [];
  for (let i = 0; i + 1 < Math.min(flat.length, want); i += 2) {
    const v = (flat[i] << 8) | flat[i + 1];
    leds.push({ red: ((v >> 11) & 31) << 3, green: ((v >> 5) & 63) << 2, blue: (v & 31) << 3 });
  }
  return { allLightsRgb: leds, battery };
}

// 2.3 GET_ALL_LIGHTS_RGB_24G_64_BYTE(59)：8 字节头 + 请求体 = 灯号表(每灯 u16 小端)
function build24GAllLights64ReadPackets(ledIds, reportCount = 64) {
  const payload = new Uint8Array(ledIds.length * 2);
  ledIds.forEach((id, i) => {
    payload[i * 2] = id & 0xff;
    payload[i * 2 + 1] = (id >> 8) & 0xff;
  });
  return frame8({ cmd: HX.GET_ALL_LIGHTS_RGB_24G_64_BYTE, reportCount, data: payload, addrStart: 0 });
}

// 2.4 解析 cmd59 响应：resp[0][5]=电量，resp[*].slice(8) = 每灯 2 字节 RGB565(大端)
function parse24GAllLights64(responses, ledIds) {
  const battery = responses.length ? responses[0][5] : 0;
  const flat = [];
  for (const r of responses) for (let i = 8; i < r.length; i++) flat.push(r[i]);
  const leds = [];
  for (let i = 0; i < ledIds.length; i++) {
    const hi = flat[i * 2], lo = flat[i * 2 + 1];
    if (hi === undefined || lo === undefined) break;
    const v = (hi << 8) | lo;
    leds.push({ ledId: ledIds[i], red: ((v >> 11) & 31) << 3, green: ((v >> 5) & 63) << 2, blue: (v & 31) << 3 });
  }
  return { allLightsRgb: leds, battery };
}

// 2.5 RGB888 → RGB565 / u16 → [hi,lo]（官方 AV / jV，bundle @1010885 / @1010930）
function av({ r, g, b }) {
  return (((r & 248) << 8) | ((g & 252) << 3) | ((b & 248) >> 3)) & 0xffff;
}
function jv(v) { return [(v >> 8) & 0xff, v & 0xff]; }

// 2.6 SET_MUSIC_DATA_24G_64_BYTE(60)：8 字节头（byte5=musicType，byte6=last），体 = RGB565 大端
//     输入 stream4 = [_,r,g,b] × N（音乐渲染器输出的 4 字节/灯 流）
function buildMusic24GPackets(stream4, musicType = 0, reportCount = 64) {
  const n = Math.floor(stream4.length / 4);
  const enc = new Uint8Array(n * 2);
  for (let i = 0; i < n; i++) {
    const [hi, lo] = jv(av({ r: stream4[i * 4 + 1] || 0, g: stream4[i * 4 + 2] || 0, b: stream4[i * 4 + 3] || 0 }));
    enc[i * 2] = hi;
    enc[i * 2 + 1] = lo;
  }
  return frame8({ cmd: HX.SET_MUSIC_DATA_24G_64_BYTE, reportCount, data: enc, addrStart: 0, otherHeader: [musicType] });
}

// 2.7 USB 分支：GET_LED_DATA(50)，原样 4 字节/灯，头 byte5=musicType，末包 byte6=1
function buildMusicUsbPackets(stream4, musicType = 0, reportCount = 64) {
  const chunk = reportCount - 8;
  const total = Math.ceil(stream4.length / chunk) || 1;
  const out = [];
  for (let p = 0; p < total; p++) {
    const off = p * chunk;
    const end = Math.min(off + chunk, stream4.length);
    const part = stream4.subarray ? stream4.subarray(off, end) : stream4.slice(off, end);
    const last = p === total - 1;
    out.push(px(HX.GET_LED_DATA, part.length, off,
      part, reportCount, last ? [musicType] : [musicType, 0], undefined, last));
  }
  return out;
}

// =============================================================================
// 3. Profile 切换报文（SET_PROFILE=144）
//    官方 iQ：customHeader=[AA,144,profileNumber]（3 字节），contentSize=1，
//    profile 号是 1-based（CQ/syncHardwareProfiles 用 currentProfile-1，切换时 +1），
//    响应 byte[2] 必须回显 profile 号。
// =============================================================================
function buildProfilePacket(profileNumber, reportCount = 64) {
  const hdr = Uint8Array.from([FRAME_REQ_MAGIC, HX.SET_PROFILE, profileNumber & 0xff]);
  return px(HX.SET_PROFILE, 1, 0, undefined, reportCount, undefined, hdr);
}
function parseProfileAck(responseBytes, expected) {
  return responseBytes.length > 2 && responseBytes[2] === expected;
}

// =============================================================================
// 4. 灯效动画分包器（SET_LED_USER_ANIMATION=65 / SET_LED_DATA=66）
//    payload = [帧数 u16 LE][帧延时 u16 LE][帧 × 灯 × RGB888]
//    每包：8 字节头 [AA,cmd,seqHi,seqLo,totalHi,totalLo,0,0] + (reportCount-8) 字节数据，
//    包长固定 = reportCount（seq 为**大端**包序号，total 为大端总包数）
// =============================================================================
function buildLedAnimationPackets({ cmd = HX.SET_LED_USER_ANIMATION, frames, delay, colors, reportCount = 64 }) {
  const body = new Uint8Array(4 + colors.length * 3);
  body[0] = frames & 0xff;
  body[1] = (frames >> 8) & 0xff;
  body[2] = delay & 0xff;
  body[3] = (delay >> 8) & 0xff;
  for (let i = 0; i < colors.length; i++) {
    const c = colors[i];
    body[4 + i * 3] = c.r & 0xff;
    body[5 + i * 3] = c.g & 0xff;
    body[6 + i * 3] = c.b & 0xff;
  }
  const perPacket = reportCount - ANIM.DATA_PER_PACKET_TRIM;
  const total = Math.ceil(body.length / perPacket);
  const out = [];
  for (let p = 0; p < total; p++) {
    const off = p * perPacket;
    const part = body.subarray(off, Math.min(off + perPacket, body.length));
    const hdr = Uint8Array.from([
      FRAME_REQ_MAGIC, cmd,
      (p >> 8) & 0xff, p & 0xff,
      (total >> 8) & 0xff, total & 0xff,
      0, 0,                                  // 官方 new Uint8Array(8).fill(0) 的后 2 字节恒 0
    ]);
    out.push(px(cmd, part.length, 0, part, reportCount, undefined, hdr));
  }
  return out;
}

// speed → 帧延时。官方 gif/LED 两处都用 Math.ceil(106-speed)；
// 预览定时器用 (106-speed)*10 或 *20 ms（两处不一致，固件单位待真机确认）。
function speedToDelay(speed) {
  return Math.ceil(ANIM.DELAY_BASE - speed);
}
// 解析设备信息里的帧上限字段
function frameLimits(deviceInfo48) {
  const u16 = (a, i) => a[i] | (a[i + 1] << 8);
  return {
    tftMaxFrames: u16(deviceInfo48, 22),
    gifMaxFrames: u16(deviceInfo48, ANIM.GIF_MAX_FRAMES_OFFSET),
    ledMaxFrames: u16(deviceInfo48, ANIM.LED_MAX_FRAMES_OFFSET),
    maxProfile: deviceInfo48[33],
    currentProfile: deviceInfo48[19],
  };
}
// LED 动画帧数上限策略（官方 led 页 b()）：startup 类 200；否则 ledMaxFrames；为 0 时 260
function ledFrameLimit(deviceInfo48, ledId) {
  if (ledId === 'startup' || ledId === 'LEOBOG_AMG65') return ANIM.BOOT_ANIMATION_MAX;
  const { ledMaxFrames } = frameLimits(deviceInfo48);
  return ledMaxFrames !== 0 ? ledMaxFrames : ANIM.LED_FRAMES_FALLBACK;
}
// GIF 灯效帧上限（官方 g7）：直接取 gifMaxFrames；为 0 时会被截断成 0 帧 → 等于不支持
function gifFrameLimit(deviceInfo48) {
  return frameLimits(deviceInfo48).gifMaxFrames;
}

// =============================================================================
// 5. 2.4G 通知解析（cmd 252 / 唤醒帧 / cmd 250）
// =============================================================================
function parse24GNotify(bytes) {
  if (!bytes || bytes.length < 3) return null;
  if (bytes[0] === FRAME_WAKE_MAGIC) {
    return (bytes[1] === 0xff && bytes[2] === 0x01) ? { kind: 'wake', state: 'awake' } : null;
  }
  if (bytes[0] !== FRAME_RESP_MAGIC) return null;
  if (bytes[1] === HX.GET_24G_DISCONNECT_NOTIFY) {
    const ev = NOTIFY_24G[bytes[2]];
    return ev ? { kind: ev, subtype: bytes[2] } : { kind: 'unknown24g', subtype: bytes[2] };
  }
  if (bytes[1] === HX.GET_DEVICE_NOTIFY) {
    const ev = NOTIFY_DEVICE[bytes[2]];
    if (ev === 'tftInfoToggle') return { kind: ev, subtype: bytes[2], enable: bytes[3] === 1 };
    return { kind: 'deviceNotify', subtype: bytes[2] };
  }
  return null;
}
// is24GSleeping 状态机（官方 store：true 仅由 252/6 触发；false 由唤醒帧/关闭设备/断连触发）
function reduceSleepState(state, notify) {
  if (!notify) return state;
  if (notify.kind === 'sleep') return true;
  if (notify.kind === 'wake') return false;
  return state;
}

// =============================================================================
// 6. 自检装置
// =============================================================================
const results = [];
const hex = (u8, max = 64) => {
  const a = Array.from(u8.slice(0, max)).map(b => b.toString(16).padStart(2, '0'));
  return a.join(' ') + (u8.length > max ? ` ... (${u8.length}B)` : '');
};
function eqBytes(a, b, label) {
  if (a.length !== b.length) throw new Error(`${label}: 长度不同 mine=${a.length} official=${b.length}`);
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) {
      throw new Error(`${label}: 偏移 ${i} 不同 mine=0x${a[i].toString(16)} official=0x${b[i].toString(16)}\n  mine    =${hex(a, 40)}\n  official=${hex(b, 40)}`);
    }
  }
  return true;
}
function eqPackets(mine, official, label) {
  if (mine.length !== official.length) throw new Error(`${label}: 包数不同 mine=${mine.length} official=${official.length}`);
  mine.forEach((p, i) => eqBytes(p, official[i], `${label} 第${i}包`));
  return `${mine.length} 包 × ${mine[0] ? mine[0].length : 0}B 完全一致`;
}

// ---- 6.1 搭沙箱：载入官方 infra.js + protocol_commands.js ----
function buildSandbox() {
  const sandbox = {
    console: { log() {}, warn() {}, error(...a) { if (VERBOSE) console.error('[official]', ...a); } },
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 5)),
    clearTimeout: (id) => clearTimeout(id),
    setInterval: (fn, ms) => setInterval(fn, ms),
    clearInterval: (id) => clearInterval(id),
    Uint8Array, Uint16Array, Uint32Array, Int8Array, DataView, Array, Object, Math, JSON, Promise,
    Number, String, Boolean, Error, RangeError, TypeError, Date, Map, Set, Symbol, RegExp, TextDecoder, TextEncoder,
    location: { pathname: '/' },
    navigator: { hid: { getDevices: async () => sandbox.__devices, requestDevice: async () => [] } },
    $message: { error() {}, success() {}, warning() {} },
    $loadingBar: { start() {}, finish() {} },
    $dialog: { warning() {} },
    __devices: [],
    jX: -999,
    ZY: { replace() {} },
    wV: (ms) => new Promise(r => setTimeout(r, Math.min(ms || 0, 5))),
    vY: (fn, ms) => setTimeout(fn, ms),
    gY: (id) => clearTimeout(id),
    Q: async (fn) => { try { return await fn(); } catch (e) { throw e; } },
    dX: () => ({ deviceStorage: {} }),
    BY: {}, $Y: {}, VY: {},
    parseInt, parseFloat, isNaN,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  const infra = fs.readFileSync(path.join(DOCS, 'infra.js'), 'utf8');
  const cmds = fs.readFileSync(path.join(DOCS, 'protocol_commands.js'), 'utf8');
  vm.runInContext(infra, sandbox, { filename: 'docs/infra.js' });
  vm.runInContext(cmds, sandbox, { filename: 'docs/protocol_commands.js' });

  // 官方 $X（唤醒监听）在 protocol_commands.js 里缺失（extract.js 的 \b 边界 bug），
  // 这里补上 bundle @1920705 的原文。
  const WAKE_OFFICIAL = '$X=async(e,t,n)=>{try{let t=e=>{let{data:t}=e,r=new Uint8Array(t.buffer);if(r.length>=3&&r[0]===166&&r[1]===255&&r[2]===1&&n&&typeof n==`function`)try{n()}catch(e){console.error(`调用2.4G唤醒回调函数时出错:`,e)}};return e.addEventListener(`inputreport`,t),{success:!0,removeListener:()=>{e.removeEventListener(`inputreport`,t)}}}catch(e){return console.error(`启动2.4G唤醒监听失败:`,e),{success:!1}}};';
  vm.runInContext(WAKE_OFFICIAL, sandbox, { filename: 'bundle@1920705' });

  // 官方 MX（真正调用 device.sendReport 的那层，bundle @1909802）与 LX（TFT 通道定位，
  // bundle @1912495）都没被 extract.js 收进 infra.js，这里按 bundle 原文补上。
  vm.runInContext(
    'MX=(e,t,n)=>{let r=e.sendReport(0,t);return n?new Promise((e,t)=>{let i=()=>t(Error(`操作已中断`));if(n.aborted)return i();n.addEventListener(`abort`,i,{once:!0}),r.then(e,t).finally(()=>n.removeEventListener(`abort`,i))}):r};' +
    'LX=async(e,t=65383)=>{let n=(await navigator.hid.getDevices()).find(n=>n.collections.some(r=>r.usagePage===t&&n.productId===e));return n?(n.opened||await n.open(),n):(console.warn(`未找到usagePage为${t}的设备`),!1)};',
    sandbox, { filename: 'bundle@1909802+1912495' });

  // 官方 AV/jV（bundle @1010885/@1010930）——protocol_commands.js 里被 TZ 引用但未随文件导出
  vm.runInContext('AV=e=>(e.r&248)<<8|(e.g&252)<<3|(e.b&248)>>3;jV=e=>[e>>8&255,e&255];', sandbox, { filename: 'bundle@1010885' });

  // 官方 BX（deviceStorage）：TZ 读 frameVersion/lightingVersion
  sandbox.BX = { deviceStorage: { deviceInfo: { frameVersion: 1, lightingVersion: 1 } } };
  return sandbox;
}

// ---- 6.2 mock HID 设备 ----
function makeDevice({ productId = 0x8047, reportCount = 64, usagePage = 65376, responder } = {}) {
  const listeners = new Set();
  const packets = [];
  const dev = {
    productId,
    opened: true,
    collections: [{ usagePage, outputReports: [{ items: [{ reportCount }] }] }],
    async open() { this.opened = true; },
    async close() { this.opened = false; },
    async forget() {},
    addEventListener(type, cb) { if (type === 'inputreport') listeners.add(cb); },
    removeEventListener(type, cb) { if (type === 'inputreport') listeners.delete(cb); },
    async sendReport(reportId, data) {
      const pkt = Uint8Array.from(data);
      packets.push(pkt);
      if (responder) {
        const resp = responder(pkt, packets.length - 1, packets);
        if (resp) {
          const bytes = Uint8Array.from(resp);
          setTimeout(() => {
            const dv = new DataView(bytes.buffer, 0, bytes.length);
            for (const cb of Array.from(listeners)) cb({ data: dv });
          }, 0);
        }
      }
      return undefined;
    },
  };
  const emit = (bytes) => {
    const b = Uint8Array.from(bytes);
    const dv = new DataView(b.buffer, 0, b.length);
    for (const cb of Array.from(listeners)) cb({ data: dv });
  };
  return { dev, packets, listeners, emit };
}

// =============================================================================
// 7. 跑自检
// =============================================================================
async function run() {
  if (!fs.existsSync(path.join(DOCS, 'protocol_commands.js'))) {
    console.error('缺少 docs/protocol_commands.js —— 无法与官方实现对照');
    process.exit(2);
  }
  const sb = buildSandbox();
  const add = (name, ok, detail) => results.push({ name, ok, detail: detail || '' });
  const checkAsync = async (name, fn) => {
    try {
      const r = await fn();
      add(name, r !== false, typeof r === 'string' ? r : '');
    } catch (e) {
      const extra = process.env.WX_DEBUG && e && e.stack ? ' | ' + e.stack.split('\n').slice(1, 6).join(' ') : '';
      add(name, false, (e && e.message ? e.message : String(e)) + extra);
    }
  };
  const checkSync = (name, fn) => checkAsync(name, async () => fn());

  // TFT 通道设备（usagePage 65383 = 0xFF67，reportCount 4104），供官方 LX() 找到
  const tft = makeDevice({ productId: 0x8047, reportCount: 4104, usagePage: 65383, responder: () => null });
  sb.__devices = [tft.dev];

  // ---------- 7.1 SET_PROFILE(144) ----------
  await checkAsync('Profile 报文：setProfile(3) 与官方 iQ 逐字节一致 + 回显校验', async () => {
    const okDev = makeDevice({
      responder: (pkt) => {
        const resp = new Uint8Array(16);
        resp[0] = 0x55; resp[1] = HX.SET_PROFILE; resp[2] = pkt[2]; resp[6] = 1;
        return resp;
      },
    });
    const ok = await sb.iQ(okDev.dev, {}, 3);
    eqBytes(buildProfilePacket(3, 64), okDev.packets[0], 'cmd144');
    if (ok !== true) throw new Error('官方 iQ 未返回 true（回显校验失败）');
    const badDev = makeDevice({
      responder: (pkt) => {
        const resp = new Uint8Array(16);
        resp[0] = 0x55; resp[1] = HX.SET_PROFILE; resp[2] = (pkt[2] + 1) & 0xff; resp[6] = 1;
        return resp;
      },
    });
    const badOk = await sb.iQ(badDev.dev, {}, 3);
    if (badOk !== false) throw new Error('回显不匹配时官方为何返回 true?');
    if (!parseProfileAck([0x55, 0x90, 3], 3) || parseProfileAck([0x55, 0x90, 4], 3)) throw new Error('parseProfileAck 错误');
    return '64B 包；byte2 = profile 号(1-based)；设备响应 byte2 回显，官方据此判成功';
  });

  // ---------- 7.2 灯效动画 cmd65 ----------
  await checkAsync('灯效动画 cmd65：2.4G(64B 报告) 分包与官方 UZ 逐字节一致', async () => {
    const frames = 3, delay = speedToDelay(100), leds = 87;
    const colors = Array.from({ length: frames * leds }, (_, i) => ({ r: i & 0xff, g: (i * 3) & 0xff, b: (i * 7) & 0xff }));
    const d = makeDevice({
      reportCount: 64,
      responder: (pkt) => { const r = new Uint8Array(64); r[0] = 0x55; r[1] = HX.SET_LED_USER_ANIMATION; r[2] = pkt[2]; r[3] = pkt[3]; r[6] = 1; return r; },
    });
    const ok = await sb.UZ(d.dev, { connectType: '2.4G' }, Uint8Array.from([frames & 0xff, frames >> 8, delay & 0xff, delay >> 8]), colors);
    if (!ok) throw new Error('官方 UZ 返回 false');
    const mine = buildLedAnimationPackets({ cmd: HX.SET_LED_USER_ANIMATION, frames, delay, colors, reportCount: 64 });
    return eqPackets(mine, d.packets, 'cmd65@64B') + `；payload=${4 + colors.length * 3}B，delay=${delay}`;
  });

  await checkAsync('灯效动画 cmd65：USB(走 0xFF67 TFT 通道, 4104B) 与官方 UZ 逐字节一致', async () => {
    const frames = 2, delay = speedToDelay(90), leds = 87;
    const colors = Array.from({ length: frames * leds }, (_, i) => ({ r: (i * 5) & 0xff, g: (i * 11) & 0xff, b: (i * 13) & 0xff }));
    const d = makeDevice({
      reportCount: 4104, usagePage: 65383,
      responder: (pkt) => { const r = new Uint8Array(4104); r[0] = 0x55; r[1] = HX.SET_LED_USER_ANIMATION; r[2] = pkt[2]; r[3] = pkt[3]; r[6] = 1; return r; },
    });
    sb.__devices = [d.dev];
    const ok = await sb.UZ(d.dev, { connectType: 'USB' }, Uint8Array.from([frames & 0xff, frames >> 8, delay & 0xff, delay >> 8]), colors);
    sb.__devices = [tft.dev];
    if (!ok) throw new Error('官方 UZ 返回 false');
    const mine = buildLedAnimationPackets({ cmd: HX.SET_LED_USER_ANIMATION, frames, delay, colors, reportCount: 4104 });
    return eqPackets(mine, d.packets, 'cmd65@4104B') + '（USB 每包 4096B / 2.4G 每包 56B）';
  });

  // ---------- 7.3 GIF 灯效 cmd66 ----------
  await checkAsync('GIF 灯效 cmd66：2.4G + frameVersion=1 的 checkAddr/parseAddr(seq) 分支与官方 MZ 一致', async () => {
    const frames = 2, delay = speedToDelay(80), leds = 87;
    const colors = Array.from({ length: frames * leds }, (_, i) => ({ r: (i * 2) & 0xff, g: (i * 4) & 0xff, b: (i * 6) & 0xff }));
    const d = makeDevice({
      reportCount: 64,
      responder: (pkt) => {
        const r = new Uint8Array(64);
        r[0] = 0x55; r[1] = HX.SET_LED_DATA;
        r[2] = pkt[2]; r[3] = pkt[3];   // 官方 parseAddr = e[2]<<8|e[3] = 包序号
        r[6] = 1;
        return r;
      },
    });
    sb.BX.deviceStorage.deviceInfo.frameVersion = 1;
    const ok = await sb.MZ(d.dev, { connectType: '2.4G' }, Uint8Array.from([frames & 0xff, frames >> 8, delay & 0xff, delay >> 8]), colors);
    if (!ok) throw new Error('官方 MZ 返回 false');
    const mine = buildLedAnimationPackets({ cmd: HX.SET_LED_DATA, frames, delay, colors, reportCount: 64 });
    eqPackets(mine, d.packets, 'cmd66@64B');
    // 反例：直接用官方 NX（maxRetries:0 避免 6 秒重试风暴）验证 checkAddr+parseAddr 语义
    // —— 接收器必须把包序号回显在响应 byte2..3，否则 ACK 不被接受
    const hdr = (seq, total) => Uint8Array.from([0xAA, HX.SET_LED_DATA, (seq >> 8) & 0xff, seq & 0xff, (total >> 8) & 0xff, total & 0xff, 0, 0]);
    const nxOnce = async (echoSeq) => {
      const dd = makeDevice({
        reportCount: 64,
        responder: (pkt) => {
          const r = new Uint8Array(64);
          r[0] = 0x55; r[1] = HX.SET_LED_DATA;
          const s = echoSeq(pkt);
          r[2] = (s >> 8) & 0xff; r[3] = s & 0xff; r[6] = 1;
          return r;
        },
      });
      const out = await sb.NX(dd.dev, {
        cmd: HX.SET_LED_DATA, contentSize: 56, data: new Uint8Array(56),
        headerCount: 8, customHeader: hdr(0, 2), timeout: 30, maxRetries: 0,
        checkAddr: true, addrStart: 0, parseAddr: (e) => (e[2] << 8) | e[3],
      });
      return out.length;
    };
    if (await nxOnce((pkt) => pkt[2] << 8 | pkt[3]) !== 1) throw new Error('序号匹配时 ACK 应被接受');
    if (await nxOnce(() => 5) !== 0) throw new Error('序号不匹配时 ACK 不该被接受');
    return '2.4G 必须由接收器在响应 byte2..3 回显包序号（parseAddr=e[2]<<8|e[3]），USB 不校验';
  });

  // ---------- 7.4 音乐 ----------
  await checkAsync('音乐 cmd60：24G 封包（RGB565 大端，10ms 超时 0 重发）与官方 TZ 逐字节一致', async () => {
    const leds = 87;
    const stream4 = new Uint8Array(leds * 4);
    for (let i = 0; i < leds; i++) {
      stream4[i * 4] = i;
      stream4[i * 4 + 1] = (i * 3) & 0xff;
      stream4[i * 4 + 2] = (i * 5) & 0xff;
      stream4[i * 4 + 3] = (i * 7) & 0xff;
    }
    sb.BX.deviceStorage.deviceInfo.lightingVersion = 1;
    sb.BX.deviceStorage.deviceInfo.frameVersion = 1;
    const d = makeDevice({ reportCount: 64, responder: () => { const r = new Uint8Array(64); r[0] = 0x55; r[1] = HX.SET_MUSIC_DATA_24G_64_BYTE; r[6] = 1; return r; } });
    const ok = await sb.TZ(d.dev, { connectType: '2.4G' }, stream4, 0);
    if (!ok) throw new Error('官方 TZ 返回 false');
    const mine = buildMusic24GPackets(stream4, 0, 64);
    return eqPackets(mine, d.packets, 'cmd60');
  });

  await checkAsync('音乐 cmd50：USB 分支（原样 4B/灯）与官方 TZ 逐字节一致（对照用）', async () => {
    const leds = 20;
    const stream4 = new Uint8Array(leds * 4);
    for (let i = 0; i < leds * 4; i++) stream4[i] = (i * 9) & 0xff;
    let responded = 0, lastEvent = null;
    const d = makeDevice({ reportCount: 64, responder: () => { responded++; const r = new Uint8Array(64); r[0] = 0x55; r[1] = HX.GET_LED_DATA; r[6] = 1; return r; } });
    d.dev.addEventListener('inputreport', (ev) => { lastEvent = Array.from(new Uint8Array(ev.data.buffer).slice(0, 8)).join('/'); });
    const ok = await sb.TZ(d.dev, { connectType: 'USB' }, stream4, 2);
    if (!ok) throw new Error(`官方 TZ 返回 false（已发 ${d.packets.length} 包，responded=${responded}，lastEvent=${lastEvent}，监听器 ${d.listeners.size}）`);
    const mine = buildMusicUsbPackets(stream4, 2, 64);
    return eqPackets(mine, d.packets, 'cmd50');
  });

  // ---------- 7.5 24G 读回 ----------
  await checkAsync('24G 读回 cmd55：请求分包 + 电量/RGB 解析与官方 OZ 一致', async () => {
    const leds = 128;
    const fake = Array.from({ length: leds }, (_, i) => (((i * 7) & 31) << 11) | (((i * 13) & 63) << 5) | ((i * 3) & 31));
    const perPkt = 60;
    const respond = (pkt) => {
      const p = pkt[2];
      const resp = new Uint8Array(64);
      resp[0] = 0x55; resp[1] = HX.GET_ALL_LIGHTS_RGB_24G;
      resp[2] = p; resp[3] = p === 0 ? 77 : 0;
      for (let k = 0; k < perPkt / 2; k++) {
        const idx = p * (perPkt / 2) + k;
        const v = fake[idx] === undefined ? 0 : fake[idx];
        resp[4 + k * 2] = (v >> 8) & 0xff;
        resp[5 + k * 2] = v & 0xff;
      }
      return resp;
    };
    const d = makeDevice({ reportCount: 64, responder: respond });
    const off = await sb.OZ(d.dev, {}, leds, undefined);
    const mine = parse24GAllLights(d.packets.map(pkt => respond(pkt)), leds);
    if (off.battery !== mine.battery) throw new Error(`电量不同 official=${off.battery} mine=${mine.battery}`);
    if (off.allLightsRgb.length !== mine.allLightsRgb.length) throw new Error(`灯数不同 official=${off.allLightsRgb.length} mine=${mine.allLightsRgb.length}`);
    for (let i = 0; i < leds; i++) {
      const a = off.allLightsRgb[i], b = mine.allLightsRgb[i];
      if (a.red !== b.red || a.green !== b.green || a.blue !== b.blue) throw new Error(`灯 ${i} 不同 official=${JSON.stringify(a)} mine=${JSON.stringify(b)}`);
    }
    eqPackets(build24GAllLightsReadPackets(leds, 64), d.packets, 'cmd55 请求');
    return `电量=响应 byte[3]；${d.packets.length} 包请求（4B 头 + 60B）；RGB565 大端`;
  });

  await checkAsync('24G 读回 cmd59：请求=灯号表(u16 LE) + 电量在响应 byte5，与官方 kZ 一致', async () => {
    const ledIds = Array.from({ length: 87 }, (_, i) => i);
    const fake = ledIds.map((_, i) => (((i * 5) & 31) << 11) | (((i * 9) & 63) << 5) | ((i * 11) & 31));
    const perPkt = 56;
    const respond = (pkt) => {
      const addr = pkt[3] | (pkt[4] << 8);
      const resp = new Uint8Array(64);
      resp[0] = 0x55; resp[1] = HX.GET_ALL_LIGHTS_RGB_24G_64_BYTE;
      resp[2] = pkt[2]; resp[3] = pkt[3]; resp[4] = pkt[4];
      resp[5] = addr === 0 ? 55 : 0;
      resp[6] = 1;
      const first = addr / 2;
      for (let k = 0; k < perPkt / 2; k++) {
        const v = fake[first + k] === undefined ? 0 : fake[first + k];
        resp[8 + k * 2] = (v >> 8) & 0xff;
        resp[9 + k * 2] = v & 0xff;
      }
      return resp;
    };
    const d = makeDevice({ reportCount: 64, responder: respond });
    const off = await sb.kZ(d.dev, {}, ledIds, undefined);
    const mine = parse24GAllLights64(d.packets.map(pkt => respond(pkt)), ledIds);
    if (off.battery !== mine.battery) throw new Error(`电量不同 official=${off.battery} mine=${mine.battery}`);
    for (let i = 0; i < ledIds.length; i++) {
      const a = off.allLightsRgb[i], b = mine.allLightsRgb[i];
      if (!a || !b) throw new Error(`灯 ${i} 缺失`);
      if (a.ledId !== b.ledId || a.red !== b.red || a.green !== b.green || a.blue !== b.blue) {
        throw new Error(`灯 ${i} 不同 official=${JSON.stringify(a)} mine=${JSON.stringify(b)}`);
      }
    }
    eqPackets(build24GAllLights64ReadPackets(ledIds, 64), d.packets, 'cmd59 请求');
    return '电量=响应 byte[5]；请求体 87×u16LE=174B → 4 包；响应每包 28 灯';
  });

  // ---------- 7.6 通知 ----------
  await checkAsync('2.4G 通知：252/4|5|6 与唤醒帧 A6 FF 01 的监听器与官方一致', async () => {
    const d1 = makeDevice({ responder: () => null });
    const d2 = makeDevice({ responder: () => null });
    const d3 = makeDevice({ responder: () => null });
    let nDisconnect = 0, nReset = 0, nSleep = 0, nWake = 0;
    sb.XX(d1.dev, {}, () => nDisconnect++);
    sb.ZX(d2.dev, {}, () => nReset++);
    sb.QX(d1.dev, {}, () => nSleep++);
    sb.$X(d3.dev, {}, () => nWake++);
    d1.emit([0x55, 0xfc]);            // 太短
    d1.emit([0x54, 0xfc, 4]);         // 错 magic
    d1.emit([0x55, 0xfb, 4]);         // 错 cmd
    d1.emit([0x55, 0xfc, 9]);         // 未知 subtype
    d3.emit([0x55, 0xff, 1]);         // 唤醒监听只认 0xA6
    d2.emit([0xa6, 0xff, 1]);         // 重置监听只认 0x55/252/5
    d1.emit([0x55, 0xfc, 4, 0, 0, 0, 1, 0]);
    d1.emit([0x55, 0xfc, 6, 0, 0, 0, 1, 0]);
    d2.emit([0x55, 0xfc, 5, 0, 0, 0, 1, 0]);
    d3.emit([0xa6, 0xff, 0x01, 0, 0, 0, 1, 0]);
    if (nDisconnect !== 1) throw new Error(`disconnect 回调次数=${nDisconnect}`);
    if (nReset !== 1) throw new Error(`reset 回调次数=${nReset}`);
    if (nSleep !== 1) throw new Error(`sleep 回调次数=${nSleep}`);
    if (nWake !== 1) throw new Error(`wake 回调次数=${nWake}`);
    const cases = [
      [[0x55, 0xfc, 4], 'disconnect'],
      [[0x55, 0xfc, 5], 'reset'],
      [[0x55, 0xfc, 6], 'sleep'],
      [[0xa6, 0xff, 0x01], 'wake'],
      [[0x55, 0xfa, 6, 1], 'tftInfoToggle'],
    ];
    for (const [bytes, kind] of cases) {
      const r = parse24GNotify(bytes);
      if (!r || r.kind !== kind) throw new Error(`parse24GNotify(${hex(Uint8Array.from(bytes))}) = ${JSON.stringify(r)}，期望 ${kind}`);
    }
    let st = false;
    st = reduceSleepState(st, parse24GNotify([0x55, 0xfc, 6]));
    if (st !== true) throw new Error('sleep 未置 true');
    st = reduceSleepState(st, parse24GNotify([0xa6, 0xff, 1]));
    if (st !== false) throw new Error('wake 未置 false');
    return '4=断开 / 5=重置(reload) / 6=休眠；唤醒帧用 0xA6 帧头；cmd250/6=屏幕信息开关';
  });

  // ---------- 7.7 帧上限 / speed→delay ----------
  await checkSync('帧上限与 speed→delay 规则与官方源码一致', () => {
    const cmds = fs.readFileSync(path.join(DOCS, 'protocol_commands.js'), 'utf8');
    for (const s of ['gifMaxFrames:i[24]|i[25]<<8', 'ledMaxFrames:i[26]|i[27]<<8', 'maxProfile:i[33]', 'currentProfile:i[19]', 'batteryLevel:i[17]']) {
      if (!cmds.includes(s)) throw new Error(`protocol_commands.js 里找不到 ${s}`);
    }
    if (fs.existsSync(BUNDLE)) {
      const b = fs.readFileSync(BUNDLE, 'utf8');
      for (const s of ['(106-t.speed)&255', 'AV=e=>(e.r&248)<<8|(e.g&252)<<3|(e.b&248)>>3', 'jV=e=>[e>>8&255,e&255]', 'r[0]===166&&r[1]===255&&r[2]===1']) {
        if (!b.includes(s)) throw new Error(`bundle 里找不到 ${s}`);
      }
    }
    const di = new Uint8Array(48);
    di[22] = 140;
    const lim = frameLimits(di);
    if (lim.tftMaxFrames !== 140 || lim.gifMaxFrames !== 0 || lim.ledMaxFrames !== 0 || lim.maxProfile !== 0) throw new Error('字段解析错误');
    if (speedToDelay(100) !== 6 || speedToDelay(50) !== 56) throw new Error('speed→delay 错误');
    if (ledFrameLimit(di, 'startup') !== 200) throw new Error('startup 帧上限应为 200');
    if (ledFrameLimit(di, 'x') !== 260) throw new Error('ledMaxFrames=0 应兜底 260');
    if (gifFrameLimit(di) !== 0) throw new Error('gifMaxFrames=0（MK87）应如实返回 0');
    return '偏移 22/24/26/33；led 兜底 260、startup 200；delay=ceil(106-speed)';
  });

  // ---------- 7.8 识别表 ----------
  await checkSync('2.4G 识别表 / 配置键 / MK87 映射自检', () => {
    const cj = path.join(DOCS, 'wireless-constants.json');
    if (!fs.existsSync(cj)) throw new Error('缺少 docs/wireless-constants.json');
    const C = JSON.parse(fs.readFileSync(cj, 'utf8'));
    const S = C.identification.special24GDevices;
    if (!Array.isArray(S) || S.length !== 64) throw new Error(`识别表应有 64 项，实际 ${S && S.length}`);
    for (const n of ['3141:65273:HS USB Dongle', '3141:65278:2.4G Dongle', '1452:591:2.4G Dongle']) {
      if (!S.includes(n)) throw new Error(`识别表缺少 ${n}`);
    }
    const mk = C.identification.mk87;
    if (mk.usb.configKey !== '3141-32839-AJAZZ KEYBOARD') throw new Error('MK87 USB 配置键错误');
    if (mk.wireless24g.configKey !== '3141-65278-2.4G Dongle-1-18') throw new Error('MK87 2.4G 配置键错误');
    if (mk.wireless24g.manufacturer !== 1 || mk.wireless24g.product !== 18) throw new Error('MK87 manufacturer/product 错误');
    const key = mk.wireless24g.vendorId + '-' + mk.wireless24g.productId + '-' + mk.wireless24g.productName
      + '-' + mk.wireless24g.manufacturer + '-' + mk.wireless24g.product;
    if (key !== mk.wireless24g.configKey) throw new Error('配置键拼装规则不一致');
    if (C.profiles.hardwareThreshold !== 1) throw new Error('硬件 Profile 阈值应为 maxProfile>1');
    return `64 项识别表；MK87 2.4G → ${mk.wireless24g.configKey}（87 键布局与 USB 完全一致）`;
  });

  return results;
}

// =============================================================================
// 8. --dump：打印样例报文
// =============================================================================
function dump() {
  console.log('== SET_PROFILE(144) profile=3, 64B 报告 ==');
  console.log(hex(buildProfilePacket(3, 64), 8));
  console.log('\n== GET_ALL_LIGHTS_RGB_24G(55) 128 灯 ==');
  const p55 = build24GAllLightsReadPackets(128, 64);
  console.log(`包数=${p55.length}`);
  p55.slice(0, 2).forEach((p, i) => console.log(`#${i} ` + hex(p, 20)));
  console.log('\n== GET_ALL_LIGHTS_RGB_24G_64_BYTE(59) 灯号 0..86 ==');
  const p59 = build24GAllLights64ReadPackets(Array.from({ length: 87 }, (_, i) => i), 64);
  console.log(`包数=${p59.length}`);
  console.log('#0 ' + hex(p59[0], 24));
  console.log('\n== SET_MUSIC_DATA_24G_64_BYTE(60) 87 灯 musicType=0 ==');
  const stream = Uint8Array.from({ length: 87 * 4 }, (_, i) => i & 0xff);
  const pm = buildMusic24GPackets(stream, 0, 64);
  console.log(`包数=${pm.length}`);
  console.log('#0 ' + hex(pm[0], 24));
  console.log('\n== SET_LED_USER_ANIMATION(65) 2 帧 × 4 灯 delay=6 ==');
  const colors = [{ r: 255, g: 0, b: 0 }, { r: 0, g: 255, b: 0 }, { r: 0, g: 0, b: 255 }, { r: 1, g: 2, b: 3 },
    { r: 4, g: 5, b: 6 }, { r: 7, g: 8, b: 9 }, { r: 10, g: 11, b: 12 }, { r: 13, g: 14, b: 15 }];
  const pa = buildLedAnimationPackets({ cmd: 65, frames: 2, delay: 6, colors, reportCount: 64 });
  console.log(`包数=${pa.length}`);
  console.log('#0 ' + hex(pa[0], 40));
  console.log('\n== 通知分类 ==');
  for (const b of [[0x55, 0xfc, 4], [0x55, 0xfc, 5], [0x55, 0xfc, 6], [0xa6, 0xff, 1], [0x55, 0xfa, 6, 1]]) {
    console.log(hex(Uint8Array.from(b)) + '  ->  ' + JSON.stringify(parse24GNotify(b)));
  }
}

// =============================================================================
// main
// =============================================================================
if (DUMP) { dump(); process.exit(0); }

run().then((res) => {
  let pass = 0, fail = 0;
  console.log('================ wireless_ref.js 自检（对照 bundle 官方实现）================');
  for (const r of res) {
    const tag = r.ok ? 'PASS' : 'FAIL';
    if (r.ok) pass++; else fail++;
    console.log(`[${tag}] ${r.name}${r.detail ? '\n        ' + r.detail : ''}`);
  }
  console.log('--------------------------------------------------------------------------');
  console.log(`合计 ${res.length} 项：PASS ${pass} / FAIL ${fail}`);
  if (VERBOSE) {
    console.log('\n--verbose：样例报文');
    dump();
  }
  process.exit(fail === 0 ? 0 : 1);
}).catch((e) => {
  console.error('自检装置异常：', e);
  process.exit(3);
});
