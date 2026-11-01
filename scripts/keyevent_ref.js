#!/usr/bin/env node
'use strict';
/**
 * keyevent_ref.js — AJAZZ MK87 网页驱动「设备主动上报帧」解码器参考实现
 *
 * 纯静态逆向产物：所有字段顺序/长度/语义都来自 bundle
 *   assets/layout-classic-CMxiG14P.js
 * 里官方实现的逐字节抄录，见 docs/key-events.md 的证据表（偏移均为该文件的字符偏移）。
 *
 * 覆盖 4 类上报：
 *   0x55 0xFA <type> <payload...>   设备状态通知   (startDeviceStateListener  XZ @1949962, type=6 唯一调用点)
 *   0x55 0xFC <type>                2.4G 断开/重置/休眠 (XX @1919506, ZX @1919911, QX @1920304)
 *   0xA6 0xFF 0x01                  2.4G 唤醒      ($X @1920705，注意不是 0x55 帧)
 *   0x55 0xFB <12B>                 磁轴校准/模拟测试按键数据 (JX @1919110)
 * 以及标准「请求-响应」帧 0x55 <cmd> <lenOrType> <addrLo> <addrHi> ... data@8 (FX @1911775)。
 *
 * 用法：
 *   node scripts/keyevent_ref.js                # 跑自检（PASS/FAIL）
 *   node scripts/keyevent_ref.js --hex "55 FA 06 01"
 *   node scripts/keyevent_ref.js --demo         # 模拟一段设备事件流
 *   node scripts/keyevent_ref.js --selftest     # 同默认
 *
 * 无第三方依赖，Node >= 14。
 */

// ---------------------------------------------------------------- 常量表
const CMD = {
  GET_DEVICE_NOTIFY: 0xFA,                 // 250 设备状态通知
  GET_MAGNETIC_AXIS_CALIBRATION_DATA: 0xFB, // 251 磁轴按键模拟量（主动上报）
  GET_24G_DISCONNECT_NOTIFY: 0xFC,         // 252 2.4G 断开/重置/休眠
};

const CMD_NAMES = {
  0x10: 'GET_DEVICE_INFO', 0x11: 'GET_GAME_MODE', 0x12: 'GET_KEY', 0x13: 'GET_LED_EFFECT',
  0x14: 'GET_CUSTOM_LED_DATA', 0x15: 'GET_MACRO', 0x16: 'GET_FN_KEY',
  0x17: 'GET_MAGNETIC_AXIS_RT', 0x18: 'GET_MAGNETIC_AXIS_DKS_DATA',
  0x1B: 'GET_LIGHT_BOX', 0x1C: 'GET_DEFAULT_FN_KEY_MATRIX', 0x1D: 'GET_SIDE_LIGHT',
  0x1E: 'GET_TRIGGER_KEY', 0x1F: 'GET_DEFAULT_KEY_MATRIX',
  0x21: 'SET_GAME_MODE', 0x22: 'SET_KEY', 0x23: 'SET_LED_EFFECT', 0x24: 'SET_CUSTOM_LED_DATA',
  0x25: 'SET_MACRO', 0x26: 'SET_FN_KEY', 0x27: 'SET_MAGNETIC_AXIS_RT',
  0x28: 'SET_MAGNETIC_AXIS_DKS_DATA', 0x2A: 'SET_DOT_MATRIX_MODE', 0x2B: 'SET_LIGHT_BOX',
  0x2D: 'SET_SIDE_LIGHT', 0x2E: 'SET_TRIGGER_KEY',
  0x30: 'SET_KEYBOARD_CUSTOM_FUNCTION_ON', 0x31: 'SET_KEYBOARD_CUSTOM_FUNCTION_OFF',
  0x32: 'GET_LED_DATA', 0x33: 'GET_ALL_LIGHTS_RGB', 0x34: 'SET_TEMPORARY_COMMAND_DATA',
  0x35: 'SET_MUSIC_DATA', 0x36: 'CLEAR_LED_DATA',
  0x37: 'GET_ALL_LIGHTS_RGB_24G', 0x3B: 'GET_ALL_LIGHTS_RGB_24G_64_BYTE',
  0x3C: 'SET_MUSIC_DATA_24G_64_BYTE', 0x3D: 'GET_DOT_MATRIX_CONFIG',
  0x40: 'SET_LED_BOOT_ANIMATION', 0x41: 'SET_LED_USER_ANIMATION', 0x42: 'SET_LED_DATA',
  0x4D: 'SET_TFT_MATERIAL', 0x4F: 'SET_FLASH_DOWNLOAD', 0x50: 'SET_TFT_USER_ANIMATION',
  0x51: 'SET_TFT_BUILT_IN_INDEX', 0x60: 'GET_MAGNETIC_AXIS_KEY_STATUS',
  0x64: 'SET_CALIBRATION_ON', 0x65: 'SET_CALIBRATION_OFF',
  0x66: 'SET_SIMULATION_TEST_ON', 0x67: 'SET_SIMULATION_TEST_OFF', 0x68: 'GET_MAGNETIC_AXIS_STATUS',
  0x69: 'SET_CALIBRATION_ON_V2', 0x6A: 'SET_CALIBRATION_OFF_V2',
  0x80: 'OTA_GET_DEVICE_SYSTEM_INFO', 0x81: 'OTA_VERIFY_FIRMWARE_INFO', 0x82: 'OTA_DEVICE_ENTER_BOOT',
  0x83: 'OTA_SEND_FIRMWARE_INFO', 0x84: 'OTA_GET_DEVICE_SN', 0x85: 'OTA_SWITCH_APP_PARTITION',
  0x86: 'OTA_SET_DEVICE_SN', 0x90: 'SET_PROFILE',
  0xFA: 'GET_DEVICE_NOTIFY', 0xFB: 'GET_MAGNETIC_AXIS_CALIBRATION_DATA', 0xFC: 'GET_24G_DISCONNECT_NOTIFY',
};

/** 0xFC 的 type（帧第 3 字节）→ 语义。来源：XX/ZX/QX 三个监听器的字面比较。 */
const FC_TYPE = {
  4: { event: '24g-disconnect', label: '2.4G 断开', handler: 'start24GDisconnectListener (XX @1919506)' },
  5: { event: 'device-reset', label: '设备重置', handler: 'startResetListener (ZX @1919911)' },
  6: { event: '24g-sleep', label: '2.4G 休眠', handler: 'start24GSleepListener (QX @1920304)' },
};

/** 0xFA 的 type。bundle 里只有 type=6 有调用点，其余为保留。 */
const FA_TYPE = {
  6: {
    event: 'tft-screen-state',
    label: 'TFT 系统信息页可见性',
    handler: 'startDeviceStateListener (XZ @1949962)',
    payload: {
      0: { name: 'systemInfoPage', desc: '1=屏幕停在「系统信息页」，主机开始推 CPU/GPU/天气；0=离开该页，停止推送' },
      1: { name: 'reserved', desc: 'bundle 未读取' },
    },
  },
};

/** 0xFA type=6 之后的推送节奏（主机侧），来源 RY() @1803404 + P() @1838541 */
const TFT_INFO_POLL_MS = 8000;

const FI = {
  GET_TFT_INFO_GATE: 'tftConfig.isShowTftInfo === true（MK87 配置里没有这个键 → 网页端永不注册该监听）',
  MK87_TFT_CONFIG: '{name:"AK980_PRO", localforageKey:"w240h135", width:240, height:135}',
};

// ---------------------------------------------------------------- 工具
const hex2 = (n) => n.toString(16).toUpperCase().padStart(2, '0');
const hex = (arr) => Array.from(arr, (b) => hex2(b & 0xFF)).join(' ');
const le16 = (a, i) => (a[i] | (a[i + 1] << 8)) & 0xFFFF;

// ---------------------------------------------------------------- 解码
/**
 * 解码一条 input report（WebHID event.data，已去掉 report ID）。
 * @param {Uint8Array|number[]} input
 * @returns {object}
 */
function decodeReport(input) {
  const b = input instanceof Uint8Array ? input : Uint8Array.from(input || []);
  const out = { ok: false, raw: hex(b), length: b.length };
  if (b.length < 2) return { ...out, error: '帧太短（<2 字节）' };

  // ---- 2.4G 唤醒：A6 FF 01（不是 0x55 帧）----
  if (b[0] === 0xA6) {
    const r = { ...out, ok: true, kind: 'push', cmd: 0xA6, cmdName: 'WAKE_24G' };
    if (b[1] === 0xFF && b[2] === 0x01) {
      r.event = '24g-wake';
      r.known = true;
      r.handle = 'start24GWakeListener ($X @1920705)：is24GSleeping = false';
    } else {
      r.event = 'unknown-a6';
      r.known = false;
    }
    return r;
  }

  if (b[0] !== 0x55) {
    return { ...out, error: `帧头不是 0x55/0xA6（实际 0x${hex2(b[0])}）——这是发往设备的方向或坏帧` };
  }

  const cmd = b[1];
  const r = { ...out, ok: true, cmd, cmdName: CMD_NAMES[cmd] || 'UNKNOWN', kind: 'push' };

  // ---- 0xFA 设备状态通知：55 FA <type> <payload...>（扁平，无 8 字节大包头）----
  if (cmd === CMD.GET_DEVICE_NOTIFY) {
    r.type = b[2];
    r.payload = b.slice(3);
    r.payloadHex = hex(r.payload);
    const t = FA_TYPE[r.type];
    r.known = !!t;
    if (t) {
      r.event = t.event;
      r.handler = t.handler;
      // 官方回调：e[3]===1 → 整个帧第 4 字节（= payload[0]）
      r.data = { systemInfoPage: b[3] === 1, stateByte: b[3] };
      r.hostAction = b[3] === 1
        ? `startGetTftInfo()：立即推一次 + 每 ${TFT_INFO_POLL_MS} ms 调 setTftScreenInfo(0x34/24B)`
        : 'stopGetTftInfo()：停掉 8s 轮询';
    } else {
      r.event = 'device-notify-unknown-type';
      r.note = '该 type 在 bundle 内没有调用点（startDeviceStateListener 只有 type=6 一处）';
    }
    return r;
  }

  // ---- 0xFC 2.4G 断开 / 重置 / 休眠：55 FC <type> ----
  if (cmd === CMD.GET_24G_DISCONNECT_NOTIFY) {
    r.type = b[2];
    const t = FC_TYPE[r.type];
    r.known = !!t;
    if (t) {
      r.event = t.event;
      r.label = t.label;
      r.handler = t.handler;
      r.hostAction = {
        '24g-disconnect': '断开当前设备、清监听、跳回 / 并弹 «断开连接了！！！»（1.5s 后）',
        'device-reset': 'location.reload()（performance 机型先清 magneticAxisRTConfig）',
        '24g-sleep': 'is24GSleeping = true（无 UI 消费者，仅状态位）',
      }[t.event];
    } else {
      r.event = '24g-notify-unknown-type';
      r.note = 'bundle 内只有 4/5/6 三个字面比较';
    }
    return r;
  }

  // ---- 0xFB 磁轴按键模拟量：55 FB <keyValue> <status> <max LE16> <min LE16> <cur LE16> <stroke LE16> <maxStroke LE16> ----
  if (cmd === CMD.GET_MAGNETIC_AXIS_CALIBRATION_DATA) {
    r.event = 'magnetic-axis-key-data';
    r.known = true;
    r.handler = 'JX @1919110（由 YX 包装后交给 startCalibration / startSimulationTest 的回调）';
    r.keyValue = b[2];
    r.calibrationStatus = b[3];
    r.maxValue = le16(b, 4);
    r.minValue = le16(b, 6) & 0x7FFF;     // 官方 &32767：最高位被清掉
    r.currentValue = le16(b, 8);
    r.keyStroke = le16(b, 10);
    r.maxStroke = le16(b, 12);
    r.minValueRaw = le16(b, 6);
    r.unit = 'keyStroke/maxStroke 为设备原始计数；官方 UI 除以 100（rtPrecision=2 时除以 1000）得到 mm';
    if (b.length < 14) r.warn = `帧长 ${b.length} < 14，官方判定 length>=13 但会读到 b[13]`;
    return r;
  }

  // ---- 其余：标准「请求-响应」帧 55 <cmd> <lenOrType> <addrLo> <addrHi> 00 <last> 00 <data...> ----
  r.kind = 'response';
  r.event = 'request-response';
  r.lenOrType = b[2];
  r.addr = b[3] | (b[4] << 8);
  r.hdr5 = b[5];
  r.last = b[6];
  r.hdr7 = b[7];
  r.data = b.slice(8);
  r.dataHex = hex(r.data);
  r.note = '对请求的应答（IX 按 cmd + 可选 addr 匹配），不是主动上报';
  return r;
}

/** 人类可读的一行描述 */
function describe(ev) {
  if (!ev.ok) return `BAD  ${ev.raw}  → ${ev.error}`;
  const head = `cmd=0x${hex2(ev.cmd)}(${ev.cmdName})`;
  switch (ev.event) {
    case 'tft-screen-state':
      return `PUSH ${head} type=${ev.type} → TFT 系统信息页 ${ev.data.systemInfoPage ? '出现（开始 8s 推送）' : '离开（停止推送）'}`;
    case '24g-disconnect':
    case 'device-reset':
    case '24g-sleep':
      return `PUSH ${head} type=${ev.type} → ${ev.label}`;
    case '24g-wake':
      return `PUSH cmd=0xA6(WAKE_24G) → 2.4G 唤醒`;
    case 'magnetic-axis-key-data':
      return `PUSH ${head} key=${ev.keyValue} status=${ev.calibrationStatus} stroke=${ev.keyStroke} cur=${ev.currentValue} max=${ev.maxValue} min=${ev.minValue}`;
    case 'request-response':
      return `RESP ${head} lenOrType=0x${hex2(ev.lenOrType)} addr=${ev.addr} last=${ev.last} data=[${ev.dataHex}]`;
    default:
      return `PUSH ${head} type=${ev.type} (${ev.event})`;
  }
}

// ---------------------------------------------------------------- 编码（构造帧，供自检/自研驱动使用）
function encodeFA(type, payload = []) { return Uint8Array.from([0x55, 0xFA, type, ...payload]); }
function encodeFC(type, payload = []) { return Uint8Array.from([0x55, 0xFC, type, ...payload]); }
function encodeWake() { return Uint8Array.from([0xA6, 0xFF, 0x01]); }
function encodeFB(o = {}) {
  const put = (arr, v) => { arr.push(v & 0xFF, (v >> 8) & 0xFF); };
  const body = [o.keyValue & 0xFF, o.calibrationStatus & 0xFF];
  put(body, o.maxValue || 0); put(body, o.minValue || 0); put(body, o.currentValue || 0);
  put(body, o.keyStroke || 0); put(body, o.maxStroke || 0);
  return Uint8Array.from([0x55, 0xFB, ...body]);   // 14 字节
}
function encodeResponse(cmd, data = [], o = {}) {
  const lenOrType = o.lenOrType !== undefined ? o.lenOrType : data.length;
  const addr = o.addr || 0;
  const hdr = [0x55, cmd, lenOrType, addr & 0xFF, (addr >> 8) & 0xFF, o.hdr5 || 0, o.last === undefined ? 1 : o.last, o.hdr7 || 0];
  return Uint8Array.from([...hdr, ...data]);
}

// ---------------------------------------------------------------- 状态机（设备事件 → 主机状态）
class DeviceMonitor {
  constructor() {
    this.connected = true;
    this.sleeping = false;
    this.tftPush = false;
    this.magneticKeys = new Map();
    this.log = [];
  }
  feed(frame) {
    const ev = decodeReport(frame);
    const s = { ev: describe(ev) };
    if (ev.ok) {
      switch (ev.event) {
        case 'tft-screen-state':
          if (this.tftPush !== ev.data.systemInfoPage) {
            this.tftPush = ev.data.systemInfoPage;
            s.tftPush = this.tftPush;
            s.action = this.tftPush ? `开始每 ${TFT_INFO_POLL_MS}ms 推 setTftScreenInfo` : '停止推送';
          }
          break;
        case '24g-disconnect': this.connected = false; s.action = '清监听 + 跳回首页 + 弹断开提示'; break;
        case 'device-reset': s.action = '全量重新初始化（官方直接 reload）'; break;
        case '24g-sleep': this.sleeping = true; s.sleeping = true; break;
        case '24g-wake': this.sleeping = false; s.sleeping = false; break;
        case 'magnetic-axis-key-data':
          this.magneticKeys.set(ev.keyValue, ev);
          s.key = ev.keyValue; s.stroke = ev.keyStroke;
          break;
      }
    }
    s.state = { connected: this.connected, sleeping: this.sleeping, tftPush: this.tftPush, keysTracked: this.magneticKeys.size };
    this.log.push(s);
    return s;
  }
}

// ---------------------------------------------------------------- 自检
function eq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

function runSelfTest() {
  const cases = [
    {
      name: '0xFA type=6, data[3]=1 → 系统信息页出现（官方 e[3]===1 分支）',
      frame: encodeFA(6, [0x01, 0x00]),
      want: { ok: true, kind: 'push', cmd: 0xFA, type: 6, event: 'tft-screen-state', 'data.systemInfoPage': true },
      line: '55 FA 06 01 ...',
    },
    {
      name: '0xFA type=6, data[3]=0 → 离开系统信息页',
      frame: encodeFA(6, [0x00]),
      want: { cmd: 0xFA, type: 6, event: 'tft-screen-state', 'data.systemInfoPage': false },
      line: '55 FA 06 00',
    },
    {
      name: '0xFA type=7 → 未知 type（bundle 无调用点，但不能崩）',
      frame: encodeFA(7, [0x01]),
      want: { cmd: 0xFA, type: 7, known: false, event: 'device-notify-unknown-type' },
      line: '55 FA 07 01',
    },
    {
      name: '0xFC type=4 → 2.4G 断开',
      frame: encodeFC(4),
      want: { cmd: 0xFC, type: 4, event: '24g-disconnect', known: true },
      line: '55 FC 04',
    },
    {
      name: '0xFC type=5 → 重置（官方 location.reload）',
      frame: encodeFC(5),
      want: { cmd: 0xFC, type: 5, event: 'device-reset' },
      line: '55 FC 05',
    },
    {
      name: '0xFC type=6 → 2.4G 休眠',
      frame: encodeFC(6),
      want: { cmd: 0xFC, type: 6, event: '24g-sleep' },
      line: '55 FC 06',
    },
    {
      name: '0xA6 FF 01 → 2.4G 唤醒（非 0x55 帧）',
      frame: encodeWake(),
      want: { cmd: 0xA6, event: '24g-wake', known: true },
      line: 'A6 FF 01',
    },
    {
      name: '0xFB 磁轴按键数据 → 12 字节扁平 payload',
      frame: encodeFB({ keyValue: 0x10, calibrationStatus: 1, maxValue: 0x1234, minValue: 0x0000, currentValue: 0x0020, keyStroke: 5, maxStroke: 3 }),
      want: { cmd: 0xFB, event: 'magnetic-axis-key-data', keyValue: 16, calibrationStatus: 1, maxValue: 0x1234, minValue: 0, currentValue: 32, keyStroke: 5, maxStroke: 3 },
      line: '55 FB 10 01 34 12 00 00 20 00 05 00 03 00',
    },
    {
      name: '0xFB minValue 最高位被 &0x7FFF 清掉',
      frame: encodeFB({ keyValue: 3, calibrationStatus: 2, maxValue: 1000, minValue: 0x8001, currentValue: 7, keyStroke: 42, maxStroke: 100 }),
      want: { cmd: 0xFB, keyValue: 3, minValueRaw: 0x8001, minValue: 1 },
      line: '55 FB 03 02 E8 03 01 80 07 00 2A 00 64 00',
    },
    {
      name: '标准响应帧（GET_DEVICE_INFO，cmd=0x10）→ 走 8 字节头解析',
      frame: encodeResponse(0x10, [0x40, 0x00, 0x00, 0x0C], { lenOrType: 0xF9 }),
      want: { kind: 'response', cmd: 0x10, event: 'request-response', lenOrType: 0xF9, addr: 0, last: 1, 'dataHex': '40 00 00 0C' },
      line: '55 10 F9 00 00 00 01 00 40 00 00 0C',
    },
    {
      name: '即便设备回 0x60(GET_MAGNETIC_AXIS_KEY_STATUS) 也只会被当成响应帧（bundle 无主动解析）',
      frame: encodeResponse(0x60, [0xFF, 0xFF]),
      want: { kind: 'response', cmd: 0x60, lenOrType: 2, dataHex: 'FF FF' },
      line: '55 60 02 00 00 00 01 00 FF FF',
    },
    {
      name: '发往设备的 0xAA 帧必须被拒绝',
      frame: Uint8Array.from([0xAA, 0x12, 0x04, 0x00]),
      want: { ok: false },
      line: 'AA 12 04 00',
    },
  ];

  let pass = 0, fail = 0;
  const failures = [];
  console.log('=== keyevent_ref.js 自检（构造帧） ===\n');
  for (const c of cases) {
    const got = decodeReport(c.frame);
    const bad = [];
    for (const [k, v] of Object.entries(c.want)) {
      const g = k.split('.').reduce((o, p) => (o == null ? o : o[p]), got);
      if (!eq(g, v)) bad.push(`${k}: want ${JSON.stringify(v)} got ${JSON.stringify(g)}`);
    }
    if (bad.length === 0) {
      pass++;
      console.log(`PASS  ${c.line}`);
      console.log(`      ${c.name}`);
      console.log(`      → ${describe(got)}`);
    } else {
      fail++;
      failures.push({ line: c.line, bad });
      console.log(`FAIL  ${c.line}`);
      console.log(`      ${c.name}`);
      for (const b of bad) console.log(`      ! ${b}`);
    }
    console.log('');
  }

  // ---- 状态机串测：一条完整事件流 ----
  console.log('=== 状态机串测（模拟一次 2.4G 会话 + TFT 系统信息页进出） ===\n');
  const mon = new DeviceMonitor();
  const stream = [
    ['55 FC 06', encodeFC(6)],
    ['A6 FF 01', encodeWake()],
    ['55 FA 06 01', encodeFA(6, [0x01])],
    ['55 FA 06 00', encodeFA(6, [0x00])],
    ['55 FA 06 01', encodeFA(6, [0x01])],
    ['55 FC 04', encodeFC(4)],
  ];
  for (const [label, f] of stream) {
    const s = mon.feed(f);
    console.log(`  ${label.padEnd(12)} → ${s.ev}`);
    console.log(`  ${''.padEnd(12)}   state=${JSON.stringify(s.state)}${s.action ? '  action=' + s.action : ''}`);
  }
  const last = mon.log[mon.log.length - 1];
  const okFinal = last.state.connected === false && mon.log[4].state.tftPush === true && mon.log[2].state.tftPush === true && mon.log[3].state.tftPush === false;
  console.log(`\n${okFinal ? 'PASS' : 'FAIL'}  状态机终态：connected=${last.state.connected} tftPush 轨迹=${mon.log.filter((l) => 'tftPush' in l).map((l) => l.tftPush).join('→')}`);
  if (okFinal) pass++; else fail++;

  // ---- 编码/解码互逆 ----
  console.log('\n=== 编解码互逆 ===\n');
  const rt = [
    ['FA(6,01 02)', encodeFA(6, [1, 2])],
    ['FC(5)', encodeFC(5)],
    ['FB(key=64,stroke=120)', encodeFB({ keyValue: 64, calibrationStatus: 0, maxValue: 3000, minValue: 0, currentValue: 512, keyStroke: 120, maxStroke: 300 })],
    ['wake', encodeWake()],
    ['resp(0x34,[1,2,3])', encodeResponse(0x34, [1, 2, 3])],
  ];
  for (const [label, f] of rt) {
    const a = decodeReport(f), b = decodeReport(Uint8Array.from(f));
    const same = eq(a, b) && a.ok === true;
    console.log(`${same ? 'PASS' : 'FAIL'}  ${label.padEnd(24)} ${hex(f)}`);
    if (same) pass++; else fail++;
  }

  console.log(`\n===== 结果：PASS ${pass}  FAIL ${fail} =====`);
  if (fail) {
    for (const f of failures) console.log(`FAILED: ${f.line} :: ${f.bad.join('; ')}`);
    process.exitCode = 1;
  }
  return fail === 0;
}

// ---------------------------------------------------------------- CLI
function main(argv) {
  const mode = argv[2];
  if (mode === '--hex') {
    const s = (argv[3] || '').replace(/0x/gi, '').split(/[^0-9a-f]+/i).filter(Boolean).map((h) => parseInt(h, 16));
    const ev = decodeReport(Uint8Array.from(s));
    console.log(describe(ev));
    console.log(JSON.stringify(ev, null, 2));
    return;
  }
  if (mode === '--demo') {
    const mon = new DeviceMonitor();
    for (const f of [encodeFC(6), encodeWake(), encodeFA(6, [1]), encodeFB({ keyValue: 33, calibrationStatus: 1, maxValue: 0x0BB8, minValue: 0, currentValue: 0x0200, keyStroke: 120, maxStroke: 300 }), encodeFA(6, [0])]) {
      const s = mon.feed(f);
      console.log(`${hex(f).padEnd(34)} ${s.ev}`);
    }
    console.log('\nfinal state:', JSON.stringify(mon.log[mon.log.length - 1].state));
    return;
  }
  const ok = runSelfTest();
  if (!ok) process.exitCode = 1;
}

if (require.main === module) main(process.argv);
module.exports = { decodeReport, describe, encodeFA, encodeFC, encodeFB, encodeResponse, encodeWake, DeviceMonitor, CMD, FC_TYPE, FA_TYPE, TFT_INFO_POLL_MS };
