#!/usr/bin/env node
/* ============================================================================
 * AJAZZ MK87 (VID 0x0C45 / PID 0x8047) —— 按键映射 4 字节条目 编/解码器
 *
 * 全部规则从官方网页驱动 bundle
 *   assets/layout-classic-CMxiG14P.js
 * 里逐字还原：
 *   pX @1905191  →  编码（action 对象 → 4 字节）
 *   mX @1906069  →  解码（4 字节 → action 对象）
 *   fX @1905045  →  pageType 枚举
 *   kX @1909309  →  FUNC_V2(pageType>=128) 解码
 *   动作表        →  iX/aX/cX/oX/sX/lX/rX @1874490/1879846/1900008/1882523/1884055/1900260/1868425
 *
 * 用法：
 *   node keymap.js                     跑自检（默认）
 *   node keymap.js decode 02 00 68 00  解 1 个条目
 *   node keymap.js matrix 00 00 ...    解 512 字节（128 条目）
 *   node keymap.js encode KEYBOARD value=104
 *   node keymap.js find 音量            在动作表里搜名字
 *   node keymap.js examples            打印 3 个示例的精确编码
 *
 * 无第三方依赖，只需要本文件 + ../docs/keymap-tables.json。
 * ==========================================================================*/
'use strict';
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------- 常量 / 枚举
// fX = {DEFAULT:0,MOUSE:1,KEYBOARD:2,CONSUMER_KEY:3,SYSTEM_KEY:4,EXTRA_FUNCTION:5,
//       MACRO:6,CB:7,DKS:8,MT:9,TGL:10,SOCD:11,RS:12,FUNC:13,END:14,MPT:15}
const PAGE = {
  DEFAULT: 0, MOUSE: 1, KEYBOARD: 2, CONSUMER_KEY: 3, SYSTEM_KEY: 4, EXTRA_FUNCTION: 5,
  MACRO: 6, CB: 7, DKS: 8, MT: 9, TGL: 10, SOCD: 11, RS: 12, FUNC: 13, END: 14, MPT: 15,
};
const PAGE_NAME = Object.fromEntries(Object.entries(PAGE).map(([k, v]) => [v, k]));
const FUNC_V2_MIN = 128;       // pageType >= 128 → FUNC_V2
const SLOT_A_MAX = 0x7fff;     // 槽 A 由 (pageType & 0x7F)<<8 | param1 组成，最高位被 0x80 占用
const MATRIX_LEN = 512;
const SLOT_COUNT = MATRIX_LEN / 4; // 128

// ---------------------------------------------------------------- 动作目录表
const TABLES_PATH = path.join(__dirname, '..', 'docs', 'keymap-tables.json');
let TABLES = null;
try {
  const j = JSON.parse(fs.readFileSync(TABLES_PATH, 'utf8'));
  TABLES = {
    allKeyChars: j.tables.allKeyChars.entries,
    basicChars: j.tables.basicChars.entries,
    extendChars: j.tables.extendChars.entries,
    jaExtendChars: j.tables.jaExtendChars.entries,
    specialChars: j.tables.specialChars.entries,
    funcChars: j.tables.funcChars.entries,
    funcV2Chars: j.tables.funcV2Chars.entries,
    mk87: j.mk87KeyboardConfig,
  };
} catch (e) {
  // 没有 JSON 也能编解码（只是查不到名字）
  TABLES = { allKeyChars: [], basicChars: [], extendChars: [], jaExtendChars: [], specialChars: [], funcChars: [], funcV2Chars: [], mk87: null };
  TABLES.__missing = e.message;
}
const T = TABLES;

const findIn = (tbl, pred) => tbl.find(pred);

/** 解码 KEYBOARD 页（bundle 里的 vX） */
function decodeKeyboard(param1, param2, cfg) {
  if (param1 !== 0) {
    const e = findIn(T.extendChars, x => x.param1 === param1);
    if (e) return { action: e, via: 'param1(修饰键位图)' };
  }
  if (param2 !== 0) {
    let e = findIn(T.basicChars, x => x.value === param2);
    if (!e) e = findIn(T.extendChars, x => x.value === param2);
    if (!e && cfg && (cfg.keyboardLang === 'jaText' || cfg.keyboardLang === 'jaTextBr')) e = findIn(T.jaExtendChars, x => x.value === param2);
    if (e) return { action: e, via: 'param2(HID usage)' };
  }
  return { action: null, via: null };
}
/** 解码 MOUSE 页（_X） */
function decodeMouse(param1, param2) {
  if (param1 === 1 || param1 === 3) {
    const e = findIn(T.specialChars, x => x.param1 === param1 && x.value === param2);
    return { action: e || null, via: 'param1/param2' };
  }
  return { action: null, via: null, warn: `未知的鼠标功能类型: ${param1}` };
}
/** 解码 CONSUMER_KEY 页（yX） */
function decodeConsumer(param1, param2) {
  const v = (param1 | (param2 << 8)) & 0xffff;
  const e = findIn(T.specialChars, x => x.page === 'CONSUMER_KEY' && x.value === v);
  return { action: e || null, via: `16bit ${v} (0x${v.toString(16)})` };
}
/** FUNC_V2 单槽查表（kX 里的规则） */
function lookupFuncV2Code(code) {
  if (code !== 0 && code < 4096) {
    const e = findIn(T.basicChars, x => x.value === code) || findIn(T.extendChars, x => x.value === code);
    if (e) return { entry: e, table: e.page === 'KEYBOARD' && findIn(T.basicChars, x => x.value === code) ? 'basicChars' : 'extendChars' };
  }
  const e = findIn(T.funcV2Chars, x => x.value === code);
  if (e) return { entry: e, table: 'funcV2Chars' };
  return { entry: null, table: null };
}

// ---------------------------------------------------------------- decode
/**
 * decodeEntry(buf4) —— 4 字节 → 描述对象（严格照搬 bundle 的 mX）
 *
 * 返回对象的约定与官方 `userKey`（mX 的返回值）一致：
 *   - param1/param2/param3 用「该 page 的语义值」，**不是**原始字节：
 *       FUNC_V2   → param1 = 槽A(12bit)、param2 = 槽B(16bit)
 *       KEYBOARD/CONSUMER_KEY/DKS/TGL/FUNC → value 生效，param1..3 无意义
 *       MOUSE/MACRO/CB/MT/SOCD/RS/MPT/END → param1..3 就是 3 个原始字节
 *   - `raw` / `rawParam1..3` 永远保留原始 4 字节，需要字节视角时用它。
 * 因此 encodeEntry(decodeEntry(x)) 对「官方 pX 能产出的字节」是恒等的。
 * @param {ArrayLike<number>|Buffer} buf4
 * @param {{cfg?:object, lang?:string}} [opts] cfg=keyboardConfig（只用到 keyboardLang）
 * @returns {object} 描述对象；DEFAULT（全 0）时 kind='default'
 */
function decodeEntry(buf4, opts = {}) {
  const b = Array.from(buf4 || []);
  if (b.length < 4) throw new Error(`decodeEntry 需要 4 字节，收到 ${b.length}`);
  const raw = [b[0], b[1], b[2], b[3]];
  const pageType = raw[0];
  const rawParam1 = raw[1], rawParam2 = raw[2], rawParam3 = raw[3];
  const cfg = opts.cfg || null;
  const out = {
    raw, pageType, rawParam1, rawParam2, rawParam3,
    param1: rawParam1, param2: rawParam2, param3: rawParam3,
    isDefault: false, page: null, name: '', text: '', value: undefined, known: true,
  };
  const warn = (m) => { out.warn = m; out.known = false; };

  // ---- FUNC_V2（pageType >= 128）-------------------------------------------
  if (pageType >= FUNC_V2_MIN) {
    const slotA = ((pageType & 0x7f) << 8) | rawParam1;   // 12-bit
    const slotB = ((rawParam2 << 8) | rawParam3) >>> 0;   // 16-bit
    const A = lookupFuncV2Code(slotA);
    const B = lookupFuncV2Code(slotB);
    const primary = B.entry || A.entry || null;
    return Object.assign(out, {
      kind: 'func_v2',
      page: 'FUNC_V2',
      slotA, slotB,
      // ↓ 与官方 kX 返回一致：param1=槽A、param2=槽B、value=槽B
      param1: slotA, param2: slotB, param3: 0,
      slotAEntry: A.entry ? pickEntry(A.entry) : null,
      slotBEntry: B.entry ? pickEntry(B.entry) : null,
      name: primary ? primary.name : '',
      text: (B.entry || A.entry || {}).text || '',
      value: slotB,                    // 与 kX 的 `value:o` 一致（槽 B），仅作展示用
      action: primary ? pickEntry(primary) : null,
      known: !!(A.entry || B.entry),
    });
  }

  switch (pageType) {
    case PAGE.DEFAULT:
      return Object.assign(out, { kind: 'default', page: 'DEFAULT', isDefault: true, name: '(默认/不修改)', value: null });

    case PAGE.MOUSE: {
      const { action, warn: w } = decodeMouse(rawParam1, rawParam2);
      if (w) warn(w);
      return Object.assign(out, {
        kind: 'mouse', page: 'MOUSE',
        param1: action ? action.param1 : rawParam1,   // 1=按键 3=滚轮
        param2: 0,
        name: action ? action.name : '', text: action ? action.text : '',
        value: action ? action.value : rawParam2,
        action: action ? pickEntry(action) : null, known: !!action,
      });
    }

    case PAGE.KEYBOARD: {
      const { action, via } = decodeKeyboard(rawParam1, rawParam2, cfg);
      if (!action) warn(`未找到对应的键盘按键: param1=0x${rawParam1.toString(16)}, param2=0x${rawParam2.toString(16)}`);
      // 官方动作表（iX/aX/cX）没有的 HID usage：给个线索，便于诊断（真机上确实存在 0x98/0x7D/0xE7 这类值）
      const canon = rawParam2 ? findIn(T.allKeyChars, x => x.keyCode === rawParam2) : null;
      return Object.assign(out, {
        kind: 'keyboard', page: 'KEYBOARD',
        param1: 0,                                    // 官方 pX 从不写 byte1
        name: action ? action.name : '', text: '',
        // value 取解析到的动作（与官方 userKey 一致）；param1 形态是官方只读不写的遗留形态
        value: action ? action.value : rawParam2,
        hid: rawParam2 ? `0x${rawParam2.toString(16)}` : null,
        guess: action ? null : (canon ? canon.name : null),   // 仅 allKeyChars(rX) 能对上的名字，非官方 UI 可选项
        via,
        action: action ? pickEntry(action) : null, known: !!action,
      });
    }

    case PAGE.CONSUMER_KEY: {
      const { action, via } = decodeConsumer(rawParam1, rawParam2);
      const v = (rawParam1 | (rawParam2 << 8)) >>> 0;
      if (!action) warn(`未找到对应的多媒体按键: keyCode=0x${v.toString(16)}`);
      return Object.assign(out, {
        kind: 'consumer', page: 'CONSUMER_KEY',
        name: action ? action.name : '', text: action ? action.text : '',
        value: v, via,
        action: action ? pickEntry(action) : null, known: !!action,
      });
    }

    case PAGE.MACRO:
      return Object.assign(out, {
        kind: 'macro', page: 'MACRO',
        name: `M${rawParam1 + 1}`, text: '',
        macroId: rawParam1, mask: rawParam2, maskParam: rawParam3,
        value: rawParam1, action: null, known: true,
      });

    case PAGE.CB:
      return Object.assign(out, {
        kind: 'combo', page: 'CB', name: 'CB', text: '',
        mod1: rawParam1, mod2: rawParam2, key: rawParam3,
        modNames: [rawParam1, rawParam2].filter(Boolean).map(hidName),
        keyName: rawParam3 ? hidName(rawParam3) : '',
        value: rawParam3, action: null, known: true,
      });

    case PAGE.DKS: {
      if (rawParam1 < 0 || rawParam1 > 63) warn(`DKS地址索引超出范围: ${rawParam1}，有效范围为0~63`);
      return Object.assign(out, {
        kind: 'dks', page: 'DKS', name: `DKS${rawParam1}`, param1: 0, param2: 0, param3: 0,
        value: rawParam1, action: null, known: rawParam1 <= 63,
      });
    }

    case PAGE.MT:
      return Object.assign(out, { kind: 'mt', page: 'MT', name: 'MT', key1: rawParam1, key2: rawParam2, timeMs: rawParam3 * 10, value: rawParam1, action: null, known: true });

    case PAGE.TGL:
      return Object.assign(out, { kind: 'tgl', page: 'TGL', name: 'TGL', param1: 0, param2: 0, param3: 0, value: rawParam1, action: null, known: true });

    case PAGE.SOCD:
      if (rawParam1 < 1 || rawParam1 > 4) warn(`SOCD模式选择超出范围: ${rawParam1}`);
      return Object.assign(out, { kind: 'socd', page: 'SOCD', name: 'SOCD', mode: rawParam1, key1: rawParam2, key2: rawParam3, value: rawParam1, action: null, known: true });

    case PAGE.RS:
      if (rawParam1 !== 0) warn(`RS迅洁模式选择不为0x00: ${rawParam1.toString(16)}`);
      return Object.assign(out, { kind: 'rs', page: 'RS', name: 'RS', param1: 0, key1: rawParam2, key2: rawParam3, value: 0, action: null, known: true });

    case PAGE.FUNC: {
      const v = rawParam3 + (rawParam2 << 8) + (rawParam1 << 16);
      const e = findIn(T.funcChars, x => x.value === v);
      return Object.assign(out, {
        kind: 'func', page: 'FUNC', name: e ? e.name : 'FUNC', text: e ? (e.text || '') : '',
        param1: 0, param2: 0, param3: 0,
        funcId: v, value: v, action: e ? pickEntry(e) : null, known: !!e,
      });
    }

    case PAGE.END:
      return Object.assign(out, { kind: 'end', page: 'END', name: 'END', key1: rawParam1, key2: rawParam2, value: rawParam1, action: null, known: true });

    case PAGE.MPT:
      return Object.assign(out, { kind: 'mpt', page: 'MPT', name: 'MPT', keys: [rawParam1, rawParam2, rawParam3], value: rawParam1, action: null, known: true });

    default:
      warn(`未知的页面类型: ${pageType}`);
      return Object.assign(out, { kind: 'unknown', page: null, name: `(unknown pageType ${pageType})` });
  }
}

const pickEntry = (e) => ({ name: e.name, value: e.value, page: e.page, text: e.text, param1: e.param1, keyType: e.keyType });

/** HID usage → 名字（借用 extendChars/basicChars/allKeyChars 做显示） */
function hidName(usage) {
  const e = findIn(T.basicChars, x => x.value === usage)
    || findIn(T.extendChars, x => x.value === usage)
    || findIn(T.allKeyChars, x => x.keyCode === usage);
  return e ? e.name : `HID:${usage}(0x${Number(usage).toString(16)})`;
}

// ---------------------------------------------------------------- encode
/**
 * encodeEntry(desc) —— 描述对象 → 4 字节数组（严格照搬 bundle 的 pX）
 *
 * 接受的 desc 形态（与官方 UI 构造的 userKey 完全一致）：
 *   {page:'DEFAULT'}
 *   {page:'MOUSE',   param1:1|3, value}
 *   {page:'KEYBOARD',value}                 // value = HID usage
 *   {page:'CONSUMER_KEY', value}            // 16-bit HID consumer usage
 *   {page:'MACRO',   param1:macroId, param2:mask, param3:maskParam}
 *   {page:'CB',      param1, param2, param3}
 *   {page:'DKS'|'TGL', value}
 *   {page:'MT'|'SOCD'|'RS'|'MPT', param1, param2, param3}
 *   {page:'FUNC',    value}                 // 24-bit 固件功能 id
 *   {page:'END',     param1, param2}
 *   {page:'FUNC_V2', keyType:1|2, value}    // 官方目录表条目
 *   {page:'FUNC_V2', param1:slotA, param2:slotB}   // 设备读回的对象
 * 也接受 decodeEntry() 的返回值直接回写。
 * @returns {number[]} 长度 4
 */
function encodeEntry(desc) {
  const buf = [0, 0, 0, 0];
  if (!desc) throw new Error('encodeEntry(desc) 需要对象');
  let page = desc.page;
  if (page == null && desc.pageType != null) page = desc.pageType >= FUNC_V2_MIN ? 'FUNC_V2' : PAGE_NAME[desc.pageType];
  const at = (i, v) => { buf[i] = v & 0xff; };
  const keyTypeOf = desc.keyType;

  switch (page) {
    case 'DEFAULT': case undefined: case null:
      if (page == null) throw new Error('desc 必须带 page 或 pageType');
      return buf;                                     // 不写任何字节 → 全 0

    case 'MOUSE':
      at(0, 1); at(1, desc.param1 || 1); at(2, desc.value || 0);
      return buf;

    case 'KEYBOARD':
      at(0, 2); at(2, desc.value || 0);                // 官方 pX 不写 param1
      return buf;

    case 'CONSUMER_KEY': {
      const v = (desc.value || 0) >>> 0;
      at(0, 3); at(1, v & 0xff); at(2, (v >> 8) & 0xff);
      return buf;
    }

    case 'MACRO': case 'MT': case 'SOCD': case 'RS': case 'CB': case 'MPT':
      at(0, PAGE[page]); at(1, desc.param1 || 0); at(2, desc.param2 || 0); at(3, desc.param3 || 0);
      return buf;

    case 'DKS': case 'TGL':
      at(0, PAGE[page]); at(1, desc.value || 0);
      return buf;

    case 'FUNC': {
      const v = desc.value || 0;
      at(0, 13); at(1, (v >> 16) & 0xff); at(2, (v >> 8) & 0xff); at(3, v & 0xff);
      return buf;
    }

    case 'FUNC_V2': {
      let a = 0, i = 0;
      if (keyTypeOf) {
        if (keyTypeOf === 2) a = desc.value ?? 0; else i = desc.value ?? 0;
      } else if (desc.param1 !== undefined || desc.param2 !== undefined) {
        a = desc.param1 ?? 0; i = desc.param2 ?? 0;
      } else if (desc.value !== undefined) {
        // 没有 keyType 也没有 param：按 lX 表多数派（keyType=1）写入槽 B
        i = desc.value ?? 0;
      }
      if (a < 0 || a > SLOT_A_MAX) throw new Error(`FUNC_V2 槽 A 超出 12 位范围: ${a}`);
      if (i < 0 || i > 0xffff) throw new Error(`FUNC_V2 槽 B 超出 16 位范围: ${i}`);
      at(0, 0x80 | ((a >> 8) & 0x7f)); at(1, a & 0xff); at(2, (i >> 8) & 0xff); at(3, i & 0xff);
      return buf;
    }

    case 'END':
      at(0, 14); at(1, desc.param1 || 0); at(2, desc.param2 || 0);
      return buf;

    case 'SYSTEM_KEY': case 'EXTRA_FUNCTION':
      throw new Error(`pageType ${page} 在官方 pX 里没有实现（会 warn「未知的页面类型」）`);

    default:
      throw new Error(`未知的 page: ${page}`);
  }
}
const encodeEntryHex = (desc) => encodeEntry(desc).map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');

// ---------------------------------------------------------------- 512 字节矩阵
/**
 * decodeMatrix(buf512) —— 128 条目整体解码（等价于 getKeyData/getFnKeyData 里
 * `hX(entries, keyList)` 之前的 4 字节切分那一步）
 * @returns {{slots: object[], nonDefault: object[]}}
 */
function decodeMatrix(buf512, opts = {}) {
  const b = Array.from(buf512 || []);
  if (b.length !== MATRIX_LEN) throw new Error(`矩阵必须是 ${MATRIX_LEN} 字节，收到 ${b.length}`);
  const slots = [];
  for (let i = 0; i < SLOT_COUNT; i++) {
    const e = decodeEntry(b.slice(i * 4, i * 4 + 4), opts);
    e.slot = i;
    // keyList 里该槽的物理键名（MK87 配置）
    const phy = T.mk87 && T.mk87.keyListBySlot ? T.mk87.keyListBySlot.find(k => k.slot === i) : null;
    e.slotKeyName = phy ? phy.name : null;
    e.slotHid = phy ? phy.keyCode : null;
    slots.push(e);
  }
  return { slots, nonDefault: slots.filter(s => !s.isDefault) };
}

/**
 * encodeMatrix(slots) —— 生成 512 字节待写缓冲
 * @param {Array<{slot:number, desc?:object}>|Map<number,object>|object} slots
 *        槽号 → 动作对象；未给出的槽写 0（= 恢复默认）
 * @returns {number[]} 512
 */
function encodeMatrix(slots) {
  const buf = new Array(MATRIX_LEN).fill(0);
  let pairs = [];
  if (slots instanceof Map) pairs = [...slots.entries()];
  else if (Array.isArray(slots)) pairs = slots.map(s => [s.slot, s.desc ?? s]);
  else pairs = Object.entries(slots).map(([k, v]) => [Number(k), v]);
  for (const [slot, desc] of pairs) {
    if (!(slot >= 0 && slot < SLOT_COUNT)) throw new Error(`槽号越界: ${slot}`);
    if (!desc || (desc.page === undefined && desc.pageType === undefined)) continue;
    if (desc.page === 'DEFAULT' || desc.pageType === 0) continue;
    const b4 = encodeEntry(desc);
    buf[slot * 4] = b4[0]; buf[slot * 4 + 1] = b4[1]; buf[slot * 4 + 2] = b4[2]; buf[slot * 4 + 3] = b4[3];
  }
  return buf;
}

// ============================================================================
//                              自检（self-test）
// ============================================================================
// 下面两个 reference 实现是从 bundle 里逐字抄下来的原文（只把形参改名），
// 用来证明本文件的 encodeEntry / decodeEntry 与官方行为逐字节一致。
function referencePX(e, t, n, r = '') {              // ← bundle @1905191 的 pX
  switch (n.page) {
    case 'DEFAULT': break;
    case 'MOUSE': e[t] = 1, e[t + 1] = n.param1 || 1, e[t + 2] = n.value || 0; break;
    case 'KEYBOARD': e[t] = 2, e[t + 2] = n.value || 0; break;
    case 'CONSUMER_KEY': { const i = n.value || 0; e[t] = 3, e[t + 1] = i & 255, e[t + 2] = i >> 8 & 255; break; }
    case 'MACRO': case 'MT': case 'SOCD': case 'RS': case 'CB': case 'MPT':
      e[t] = PAGE[n.page], e[t + 1] = n.param1 || 0, e[t + 2] = n.param2 || 0, e[t + 3] = n.param3 || 0; break;
    case 'DKS': e[t] = 8, e[t + 1] = n.value || 0; break;
    case 'TGL': e[t] = 10, e[t + 1] = n.value || 0; break;
    case 'FUNC':
      e[t] = 13, e[t + 1] = (n.value || 0) >> 16 & 255, e[t + 2] = (n.value || 0) >> 8 & 255, e[t + 3] = (n.value || 0) & 255; break;
    case 'FUNC_V2': {
      let r = 0, i = 0;
      n.keyType ? (r = n.keyType === 2 ? n.value ?? 0 : 0, i = n.keyType === 1 ? n.value ?? 0 : 0)
                : (r = n.param1 ?? 0, i = n.param2 ?? 0);
      e[t] = 128 | r >> 8 & 127, e[t + 1] = r & 255, e[t + 2] = i >> 8 & 255, e[t + 3] = i & 255; break;
    }
    case 'END': e[t] = 14, e[t + 1] = n.param1 || 0, e[t + 2] = n.param2 || 0; break;
    default: return 'WARN_UNKNOWN_PAGE';
  }
  return 'OK';
}

function assert(cond, msg, bag) {
  if (!cond) { bag.fail.push(msg); return false; }
  bag.ok++; return true;
}
const hex = (a) => Array.from(a).map(x => x.toString(16).padStart(2, '0').toUpperCase()).join(' ');

function selfTest(verbose = true) {
  const bag = { ok: 0, fail: [] };
  const log = (...a) => { if (verbose) console.log(...a); };
  const eq = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

  log('== 0. 数据源 ==');
  if (T.__missing) log(`   ⚠ 未加载 keymap-tables.json（${T.__missing}），名字解析与查表测试会被跳过`);
  else log(`   已加载动作表：basic=${T.basicChars.length} extend=${T.extendChars.length} special=${T.specialChars.length} func=${T.funcChars.length} funcV2=${T.funcV2Chars.length} allKeys=${T.allKeyChars.length}，MK87 键位 ${T.mk87.keyListBySlot.length} 个`);

  // ---------------------------------------------------------------- 1. 固定向量
  log('\n== 1. 固定字节向量 ==');
  const vectors = [
    ['默认/不修改（全 0）', { page: 'DEFAULT' }, [0x00, 0x00, 0x00, 0x00]],
    ['KEYBOARD A (HID 0x04)', { page: 'KEYBOARD', value: 4 }, [0x02, 0x00, 0x04, 0x00]],
    ['KEYBOARD F13 (HID 0x68，官方表无此项)', { page: 'KEYBOARD', value: 104 }, [0x02, 0x00, 0x68, 0x00]],
    ['CB Ctrl+C = L-Ctrl(0xE0) + C(0x06)', { page: 'CB', param1: 224, param2: 0, param3: 6 }, [0x07, 0xE0, 0x00, 0x06]],
    ['CONSUMER_KEY 音量+ (0xE9)', { page: 'CONSUMER_KEY', value: 233 }, [0x03, 0xE9, 0x00, 0x00]],
    ['CONSUMER_KEY 我的电脑 (0x194)', { page: 'CONSUMER_KEY', value: 404 }, [0x03, 0x94, 0x01, 0x00]],
    ['MACRO 宏 1 (id 0, mask 0)', { page: 'MACRO', param1: 0, param2: 0, param3: 0 }, [0x06, 0x00, 0x00, 0x00]],
    ['MACRO 宏 7 (id 6, mask 1, param 3)', { page: 'MACRO', param1: 6, param2: 1, param3: 3 }, [0x06, 0x06, 0x01, 0x03]],
    ['FUNC 234 = CTRL+C（固件内置动作）', { page: 'FUNC', value: 234 }, [0x0D, 0x00, 0x00, 0xEA]],
    ['FUNC 292 = 复位灯效', { page: 'FUNC', value: 292 }, [0x0D, 0x00, 0x01, 0x24]],
    ['FUNC_V2 4096 恢复出厂设置 (keyType2→槽A)', { page: 'FUNC_V2', keyType: 2, value: 4096 }, [0x90, 0x00, 0x00, 0x00]],
    ['FUNC_V2 28682 音量+ (keyType1→槽B)', { page: 'FUNC_V2', keyType: 1, value: 28682 }, [0x80, 0x00, 0x70, 0x0A]],
    ['MOUSE 左键', { page: 'MOUSE', param1: 1, value: 1 }, [0x01, 0x01, 0x01, 0x00]],
    ['MOUSE 滚轮下滚', { page: 'MOUSE', param1: 3, value: 255 }, [0x01, 0x03, 0xFF, 0x00]],
  ];
  for (const [label, desc, want] of vectors) {
    const got = encodeEntry(desc);
    const ok = assert(eq(got, want), `[1] ${label}: 期望 ${hex(want)} 实际 ${hex(got)}`, bag);
    if (ok) log(`   ✓ ${label.padEnd(46)} → ${hex(got)}`);
  }

  // ---------------------------------------------------------------- 2. encodeEntry ≡ 官方 pX
  log('\n== 2. encodeEntry 与官方 pX 逐字节等价（对全部动作表条目） ==');
  {
    let n = 0, bad = 0;
    const all = [
      ...T.basicChars, ...T.extendChars, ...T.jaExtendChars, ...T.specialChars,
      ...T.funcChars, ...T.funcV2Chars,
    ];
    for (const entry of all) {
      const bufA = new Array(4).fill(0), bufB = new Array(8).fill(0); // B 用 8 字节便于发现越界写
      referencePX(bufA, 0, entry, 'test');
      const enc = encodeEntry(entry);
      n++;
      if (!eq(bufA, enc) || bufB.some((x, i) => i >= 4 && x !== 0)) { bad++; if (bag.fail.length < 12) bag.fail.push(`[2] ${entry.page}:${entry.name} pX=${hex(bufA)} enc=${hex(enc)}`); }
    }
    assert(bad === 0, `[2] ${bad}/${n} 个条目与 pX 不一致`, bag);
    log(`   ✓ ${n} 个动作表条目，encodeEntry 与 pX 输出完全一致（bad=${bad}）`);
  }

  // ---------------------------------------------------------------- 3. 往返：条目 → 字节 → 解码 → 字节
  log('\n== 3. 官方动作表条目 往返一致性（entry → bytes → decode → bytes） ==');
  {
    let n = 0, bad = 0, nameBad = 0;
    const check = (entry, label) => {
      if ((entry.page === 'DKS') && (entry.value > 63)) return;          // 表里没有越界值，保守跳过
      const b1 = encodeEntry(entry);
      const d = decodeEntry(b1);
      const b2 = encodeEntry(d);
      n++;
      if (!eq(b1, b2)) { bad++; if (bag.fail.length < 20) bag.fail.push(`[3] ${label} ${entry.name} v=${entry.value} ${hex(b1)} -> ${hex(b2)} (decoded name=${d.name})`); }
      if (!d.isDefault && d.name && d.name !== entry.name && entry.page !== 'FUNC_V2' && entry.page !== 'FUNC') { nameBad++; }
    };
    T.basicChars.forEach(e => check(e, 'basicChars'));
    T.extendChars.forEach(e => check(e, 'extendChars'));
    T.specialChars.forEach(e => check(e, 'specialChars'));
    T.funcChars.forEach(e => check(e, 'funcChars'));
    T.funcV2Chars.forEach(e => check(e, 'funcV2Chars'));
    assert(bad === 0, `[3] ${bad}/${n} 个条目往返后字节变化`, bag);
    log(`   ✓ ${n} 个条目 往返字节稳定（bad=${bad}，名字不一致 ${nameBad} 例——见第 4 节的说明）`);
  }

  // ---------------------------------------------------------------- 4. 名字解析一致性
  log('\n== 4. 名字解析抽查 ==');
  {
    const cases = [
      [[0x02, 0x00, 0x04, 0x00], 'A'],
      [[0x02, 0x00, 0xE0, 0x00], 'L-Ctrl'],
      [[0x03, 0xE9, 0x00, 0x00], '音量 +'],
      [[0x03, 0x94, 0x01, 0x00], '我的电脑'],
      [[0x0D, 0x00, 0x00, 0xEA], 'CTRL+C'],
      [[0x0D, 0x00, 0x01, 0x24], '复位灯效'],
      [[0x90, 0x00, 0x00, 0x00], '恢复出厂设置'],
      [[0x80, 0x00, 0x70, 0x0A], '音量 +'],
      [[0x01, 0x01, 0x02, 0x00], '鼠标右键'],
      [[0x06, 0x00, 0x00, 0x00], 'M1'],
    ];
    for (const [bytes, want] of cases) {
      const d = decodeEntry(bytes);
      const ok = assert(d.name === want, `[4] ${hex(bytes)} 期望 name=${want} 实际 ${d.name}`, bag);
      if (ok) log(`   ✓ ${hex(bytes)} → ${d.page}/${d.name}`);
    }
    // 特殊：KEYBOARD param1 修饰位图形态（官方只读不写，属于有损形态）
    const d = decodeEntry([0x02, 0x01, 0x06, 0x00]);
    log(`   · 备注：02 01 06 00 走 param1 分支 → 名 ${d.name}，回写会变成 ${hex(encodeEntry(d))}（官方 pX 不写 param1，属有损形态）`);
  }

  // ---------------------------------------------------------------- 5. 随机往返稳定性
  log('\n== 5. 随机（可达）编码 往返稳定性 20000 次 ==');
  {
    let seed = 0x12345678;
    const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
    const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
    const pool = [...T.basicChars, ...T.extendChars, ...T.specialChars, ...T.funcChars, ...T.funcV2Chars]
      .filter(e => e.page !== 'DEFAULT');
    let bad = 0;
    for (let k = 0; k < 20000; k++) {
      const e = pick(pool);
      const b1 = encodeEntry(e);
      const b2 = encodeEntry(decodeEntry(b1));
      if (!eq(b1, b2)) { bad++; if (bag.fail.length < 24) bag.fail.push(`[5] ${e.page}/${e.name} ${hex(b1)} -> ${hex(b2)}`); }
    }
    assert(bad === 0, `[5] ${bad}/20000 次随机往返不稳定`, bag);
    log(`   ✓ 20000 次随机条目往返全部稳定（bad=${bad}）`);
  }

  // ---------------------------------------------------------------- 6. 512 字节矩阵
  log('\n== 6. 512 字节矩阵 编/解码 ==');
  {
    const slots = {
      0: { page: 'KEYBOARD', value: 104 },                                  // Esc → F13(HID 0x68)
      33: { page: 'CB', param1: 224, param2: 0, param3: 6 },               // Q → Ctrl+C
      34: { page: 'CONSUMER_KEY', value: 233 },                            // W → 音量+
      35: { page: 'MACRO', param1: 0, param2: 0, param3: 0 },              // E → 宏 1
      41: { page: 'FUNC', value: 234 },                                    // O → CTRL+C（固件动作）
      85: { page: 'FUNC_V2', keyType: 1, value: 12290 },                   // Fn → 主灯光亮度+
    };
    const buf = encodeMatrix(slots);
    assert(buf.length === 512, '[6] 矩阵长度必须 512', bag);
    assert(buf.filter((x, i) => x !== 0 && i % 4 === 0).length === 6, `[6] 非零条目数应为 6，实际 ${buf.filter((x, i) => x !== 0 && i % 4 === 0).length}`, bag);
    const dec = decodeMatrix(buf);
    assert(dec.nonDefault.length === 6, `[6] 非默认条目应为 6，实际 ${dec.nonDefault.length}`, bag);
    for (const s of dec.nonDefault) log(`   ✓ slot ${String(s.slot).padStart(3)} [${s.slotKeyName || '-'}] ${hex(s.raw)} → ${s.page}/${s.name}`);
    // 与 pX 写 512 缓冲的结果比对
    const ref = new Uint8Array(512).fill(0);
    for (const [slot, d] of Object.entries(slots)) referencePX(ref, Number(slot) * 4, d, 'ref');
    assert(eq(Array.from(ref), buf), '[6] encodeMatrix 与逐个 pX 写入结果不一致', bag);
    log('   ✓ encodeMatrix 与官方「512 缓冲 + pX 逐槽写」结果逐字节一致');
    // 回写一致性
    assert(eq(encodeMatrix(dec.nonDefault.map(s => ({ slot: s.slot, desc: s }))), buf), '[6] decode→encode 矩阵不可逆', bag);
    log('   ✓ 矩阵 decode → encode 可逆');
  }

  // ---------------------------------------------------------------- 7. default FN matrix 解析
  log('\n== 7. GET_DEFAULT_FN_KEY_MATRIX 解析演示（getDefaultFnKeyMatrix / pZ） ==');
  {
    const fake = new Array(512).fill(0);
    // 槽 1（F1）：pageType=13, param1=0,param2=1,param3=0  → funcId 256
    fake[4] = 13; fake[5] = 0; fake[6] = 1; fake[7] = 0;
    // 槽 2（F2）：pageType=13, param1=0,param2=0,param3=234 → funcId 234 (CTRL+C)
    fake[8] = 13; fake[9] = 0; fake[10] = 0; fake[11] = 234;
    // 槽 3（F3）：FUNC_V2 槽A=4096, 槽B=0   → 0x90 0x00 0x00 0x00
    fake[12] = 0x90; fake[13] = 0x00; fake[14] = 0x00; fake[15] = 0x00;
    // 槽 4（F4）：FUNC_V2 槽A=0, 槽B=28682 → 0x80 0x00 0x70 0x0A
    fake[16] = 0x80; fake[17] = 0x00; fake[18] = 0x70; fake[19] = 0x0A;
    const dec = decodeMatrix(fake);
    const fnFuncIds = [];
    for (const s of dec.nonDefault) {
      // 官方 pZ(getDefaultFnKeyMatrix) 用的是原始字节：
      //   n=pageType, o=param1, s=param2, c=param3     （都是字节）
      const n0 = s.raw[0], o = s.raw[1], s2 = s.raw[2], c = s.raw[3];
      if (n0 === 13) { const v = (o << 16) | (s2 << 8) | c; if (v > 0) fnFuncIds.push(v); }
      if (n0 >= 128) {                              // frameVersion>0 分支
        const a = ((n0 & 127) << 8) | o, b = (s2 << 8) | c;
        if (a > 0) fnFuncIds.push(a); if (b > 0) fnFuncIds.push(b);
      }
    }
    log('   fnFuncIds =', JSON.stringify(fnFuncIds), '（= 官方 defaultFnFuncIds，功能页只显示这些 id）');
    assert(JSON.stringify(fnFuncIds) === JSON.stringify([256, 234, 4096, 28682]), '[7] defaultFnMatrix → fnFuncIds 解析不符', bag);
  }

  // ---------------------------------------------------------------- 8. MK87 槽号语义
  log('\n== 8. MK87 keyList 槽号 ≡ allKeyChars 序号 ==');
  if (T.mk87 && T.allKeyChars.length) {
    let checked = 0, mismatch = 0;
    for (const k of T.mk87.keyListBySlot) {
      const canon = T.allKeyChars.find(x => x.value === k.slot);
      if (!canon) continue;
      checked++;
      const sameName = canon.name.toUpperCase() === String(k.name).toUpperCase();
      const sameHid = String(canon.keyCode) === String(k.keyCode);
      if (!sameName && !sameHid) { mismatch++; if (bag.fail.length < 26) bag.fail.push(`[8] slot ${k.slot}: 配置 ${k.name}/${k.keyCode} vs canonical ${canon.name}/${canon.keyCode}`); }
    }
    assert(mismatch === 0, `[8] ${mismatch}/${checked} 个槽号语义不一致`, bag);
    log(`   ✓ ${checked} 个已用槽号，名字或 HID 全部对得上 allKeyChars（mismatch=${mismatch}）`);
    log(`   · MK87 空槽（未使用）：${T.mk87.isEmptySlot.join(',')}`);
    log(`   · F13 的 canonical 槽号 = ${(T.allKeyChars.find(x => x.name === 'F13') || {}).value}（MK87 无此物理键）`);
  } else {
    log('   ⚠ 缺少 MK87 配置或 allKeyChars，跳过');
  }

  // ---------------------------------------------------------------- 汇总
  log('\n================ 自检汇总 ================');
  log(`通过断言 ${bag.ok} 条，失败 ${bag.fail.length} 条`);
  if (bag.fail.length) { bag.fail.forEach(f => console.log('  ✗ ' + f)); process.exitCode = 1; }
  else log('全部通过 ✅');
  return bag;
}

// ============================================================================
//                                    CLI
// ============================================================================
function printDecode(bytes, opts) {
  const d = decodeEntry(bytes, opts);
  const out = {
    raw: hex(d.raw),
    pageType: d.pageType === undefined ? undefined : `${d.pageType}${d.pageType >= 128 ? ' (FUNC_V2)' : ' (' + (PAGE_NAME[d.pageType] || '?') + ')'}`,
    page: d.page, kind: d.kind,
    param1: d.param1, param2: d.param2, param3: d.param3,
    name: d.name, text: d.text || undefined, value: d.value,
    known: d.known, warn: d.warn,
  };
  if (d.page === 'KEYBOARD' && d.param2) out.hidUsage = `0x${Number(d.param2).toString(16)}`;
  if (d.page === 'KEYBOARD' && !d.name && (d.hid || d.guess)) out.unknownAction = `${d.hid || ''}${d.guess ? ' ≈ ' + d.guess + '（仅 allKeyChars 有，官方 UI 不可选）' : '（官方动作表无此 usage）'}`;
  if (d.page === 'CONSUMER_KEY' && d.value) out.consumerUsage = `0x${Number(d.value).toString(16)}`;
  if (d.page === 'CB') out.combo = `${d.modNames.join('+') || '(无修饰)'} + ${d.keyName}`;
  if (d.page === 'FUNC') out.funcId = d.funcId;
  if (d.kind === 'func_v2') { out.slotA = d.slotA; out.slotB = d.slotB; out.slotAName = d.slotAEntry && d.slotAEntry.name; out.slotBName = d.slotBEntry && d.slotBEntry.name; }
  console.log(JSON.stringify(out, null, 2));
}

function findNames(q) {
  const hits = [];
  for (const [name, tbl] of Object.entries(T)) {
    if (!Array.isArray(tbl)) continue;
    for (const e of tbl) if (String(e.name).includes(q) || String(e.text || '').includes(q)) hits.push({ table: name, ...e });
  }
  if (!hits.length) return console.log(`没有名字包含「${q}」的动作`);
  for (const h of hits) {
    let bytes = [];
    try { bytes = encodeEntry(h); } catch (e) { bytes = null; }
    const note = h.table === 'allKeyChars' ? '（键位表，不是动作）' : '';
    console.log(`${(h.table + '').padEnd(13)} ${String(h.name).padEnd(22)} page=${String(h.page).padEnd(13)} value=${String(h.value).padEnd(6)} bytes=${bytes ? hex(bytes) : '(不可编码)'} ${note}`);
  }
}

function main() {
  const argv = process.argv.slice(2);
  const cmd = argv[0] || 'selftest';
  const parseHex = (arr) => arr.map(x => parseInt(x, 16));
  const parseKV = (arr) => {
    const o = {};
    for (const a of arr) { const [k, v] = a.split('='); o[k] = /^-?\d+$/.test(v) ? Number(v) : v; }
    return o;
  };
  if (cmd === 'selftest' || cmd === 'test' || cmd === '') return selfTest(true);
  if (cmd === 'decode') {
    const bytes = parseHex(argv.slice(1));
    if (bytes.length !== 4) throw new Error('decode 需要 4 个十六进制字节');
    return printDecode(bytes);
  }
  if (cmd === 'matrix') {
    const bytes = parseHex(argv.slice(1));
    const dec = decodeMatrix(bytes, { cfg: T.mk87 });
    console.log(`共 ${dec.slots.length} 槽，其中非默认 ${dec.nonDefault.length} 个`);
    for (const s of dec.nonDefault) {
      const nm = s.name || (s.guess ? `${s.guess}?` : '(官方动作表无此值)');
      console.log(`  slot ${String(s.slot).padStart(3)} [${(s.slotKeyName || '-').padEnd(10)}] ${hex(s.raw)}  ${s.page}/${nm}${s.raw[0] >= 128 ? ` (A=${s.slotA} B=${s.slotB})` : ''}`);
    }
    return;
  }
  if (cmd === 'encode') {
    const page = argv[1];
    const desc = Object.assign({ page }, parseKV(argv.slice(2)));
    console.log(hex(encodeEntry(desc)), JSON.stringify(desc));
    return;
  }
  if (cmd === 'find') return findNames(argv[1] || '');
  if (cmd === 'examples') {
    const rows = [
      ['F13（协议级 KEYBOARD，HID 0x68=104；官方表里没有 F13）', { page: 'KEYBOARD', value: 104 }],
      ['Ctrl+C（CB 组合键页：L-Ctrl 0xE0 + C 0x06）', { page: 'CB', param1: 224, param2: 0, param3: 6 }],
      ['媒体键 音量+（CONSUMER_KEY 0x0E9）', { page: 'CONSUMER_KEY', value: 233 }],
      ['宏 M1（MACRO，macroId 0）', { page: 'MACRO', param1: 0, param2: 0, param3: 0 }],
      ['固件内置 CTRL+C（FUNC 234）', { page: 'FUNC', value: 234 }],
      ['FUNC_V2 28682 音量+（槽 B）', { page: 'FUNC_V2', keyType: 1, value: 28682 }],
    ];
    for (const [label, d] of rows) console.log(`${hex(encodeEntry(d))}   ${label}`);
    return;
  }
  console.log(`未知命令: ${cmd}\n可用: selftest | decode <4 hex> | matrix <512 hex> | encode <PAGE> k=v ... | find <名字> | examples`);
}

module.exports = { decodeEntry, encodeEntry, decodeMatrix, encodeMatrix, encodeEntryHex, PAGE, PAGE_NAME, TABLES: T, selfTest };

if (require.main === module) main();
