// Build docs/keymap-tables.json from the minified bundle.
// Usage: node gen_tables_json.js
const fs = require('fs');
const path = require('path');
const { SRC, matchPair, findTable } = require('./tables.js');

const BUNDLE = 'C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js';
const OUT = path.join(__dirname, '..', 'docs', 'keymap-tables.json');

// ---------------------------------------------------------------- page types
// fX={DEFAULT:0,MOUSE:1,KEYBOARD:2,CONSUMER_KEY:3,SYSTEM_KEY:4,EXTRA_FUNCTION:5,
//     MACRO:6,CB:7,DKS:8,MT:9,TGL:10,SOCD:11,RS:12,FUNC:13,END:14,MPT:15}
const PAGE_DOC = [
  [0, 'DEFAULT', 'DEFAULT', '不修改 / 使用硬件默认', 'pX 不写任何字节 → 4 字节全 0', true],
  [1, 'MOUSE', 'MOUSE', '鼠标按键/滚轮', 'byte1=param1(1=按键,3=滚轮) byte2=value', true],
  [2, 'KEYBOARD', 'KEYBOARD', '键盘按键（HID usage）', 'byte2=value(HID usage)；byte1 写入时恒 0（读取时可携带修饰键位图）', true],
  [3, 'CONSUMER_KEY', 'CONSUMER_KEY', '多媒体/消费类按键（HID Consumer usage，16 位小端）', 'byte1=value&0xFF byte2=value>>8', true],
  [4, 'SYSTEM_KEY', 'SYSTEM_KEY', '系统键（保留，本驱动未实现）', 'pX/mX 都无分支 → 遇到会 warn「未知的页面类型」', false],
  [5, 'EXTRA_FUNCTION', 'EXTRA_FUNCTION', '扩展功能（保留，本驱动未实现）', '同上', false],
  [6, 'MACRO', 'MACRO', '执行宏', 'byte1=macroId byte2=掩码/模式 byte3=掩码参数', true],
  [7, 'CB', 'CB', 'Combination 组合键（修饰键+1 键）', 'byte1=修饰键1HID byte2=修饰键2HID byte3=主键HID', true],
  [8, 'DKS', 'DKS', 'Dynamic Keystroke（磁轴，MK87 不支持）', 'byte1=value(DKS 索引 0..63)', true],
  [9, 'MT', 'MT', 'Mod-Tap / 长按短按（磁轴高级键）', 'byte1=键1HID byte2=键2HID byte3=时间/10ms', true],
  [10, 'TGL', 'TGL', 'Toggle 切换键', 'byte1=value', true],
  [11, 'SOCD', 'SOCD', 'SOCD（磁轴高级键）', 'byte1=模式 byte2=键1HID byte3=键2HID', true],
  [12, 'RS', 'RS', 'Rapid Trigger 迅洁（磁轴高级键）', 'byte1 恒 0 byte2=键1HID byte3=键2HID', true],
  [13, 'FUNC', 'FUNC', '固件内置功能动作（24 位 id）', 'byte1..3 = value>>16, value>>8, value', true],
  [14, 'END', 'END', '双键（两键同时/先后？官方 UI 为两个槽位）', 'byte1=键1HID byte2=键2HID', true],
  [15, 'MPT', 'MPT', '多键同发（3 键）', 'byte1/2/3 = 3 个 HID usage', true],
];

const pageTypes = PAGE_DOC.map(([value, key, local, meaning, layout, implemented]) => ({
  value, key, local, meaning, layout, implemented,
  encodeImplemented: implemented,
  readBranch: value >= 128 ? 'kX (FUNC_V2)' : implemented ? `mX case ${key}` : 'mX default → warn',
}));
// FUNC_V2 pseudo page
pageTypes.push({
  value: '128..255', key: 'FUNC_V2', local: 'kX',
  meaning: '新一代功能动作页；pageType 最高位置 1，低 7 位是「功能码槽 A」的高 7 位',
  layout: 'byte0 = 0x80 | (slotA>>8)&0x7F, byte1 = slotA&0xFF, byte2 = (slotB>>8)&0xFF, byte3 = slotB&0xFF',
  implemented: true, encodeImplemented: true, readBranch: 'kX (pageType>=128)',
});

// ---------------------------------------------------------------- char tables
const TABLES = [
  ['rX', 'allKeyChars', '全部物理键canonical表：value=键位序号(0..120)，keyCode=HID usage，keyName=DOM code'],
  ['iX', 'basicChars', 'KEYBOARD 页、基础字符（字母/数字/符号），value=HID usage'],
  ['aX', 'extendChars', 'KEYBOARD 页、扩展键（功能键/方向/小键盘/修饰键），value=HID usage；修饰键带 param1=修饰位图'],
  ['cX', 'jaExtendChars', 'KEYBOARD 页、日语键盘专用，value=HID usage'],
  ['oX', 'specialChars', 'MOUSE(7) + CONSUMER_KEY(17)，value=HID usage 或鼠标动作码，带 param1 区分鼠标子类型'],
  ['sX', 'funcChars', 'FUNC 页（pageType=13），value=24 位固件功能 id'],
  ['lX', 'funcV2Chars', 'FUNC_V2 页（pageType>=128），value=功能码，keyType=1 写入槽B / 2 写入槽A'],
];
const tables = {};
for (const [local, human, desc] of TABLES) {
  const t = findTable(local);
  const rows = new Function('return ' + t.text)();
  tables[human] = { local, offset: t.start, end: t.end, desc, count: rows.length, entries: rows };
}

// ---------------------------------------------------------------- MK87 config
const idx = SRC.indexOf('productId:32839');
const open = SRC.lastIndexOf('={', idx) + 1;
const close = matchPair(SRC, open);
const cfg = new Function('return (' + SRC.slice(open, close + 1) + ')')();
const flat = [];
cfg.keyList.forEach((row, r) => row.forEach(k => flat.push({ ...k, row: r })));
flat.sort((a, b) => a.value - b.value);

const mk87 = {
  local: 'TU', offset: open,
  vendorId: cfg.vendorId, productId: cfg.productId, name: cfg.name,
  connectType: cfg.connectType, routesName: cfg.routesName,
  customKeysConfig: cfg.customKeysConfig,
  macroConfig: cfg.macroConfig, tftConfig: cfg.tftConfig, musicConfig: cfg.musicConfig,
  wheelKeys: cfg.wheelKeys ?? null,
  keyCount: flat.length,
  keyListBySlot: flat.map(k => ({ slot: k.value, row: k.row, name: k.name, keyCode: k.keyCode, key: k.key })),
  keyListRaw: cfg.keyList,
  isEmptySlot: [...Array(128).keys()].filter(v => !flat.some(k => k.value === v)),
};

// ---------------------------------------------------------------- pageType facts
const facts = {
  bundle: BUNDLE,
  bundleLength: SRC.length,
  generatedAt: new Date().toISOString(),
  offsets: {
    fxEnum: SRC.indexOf('fX={DEFAULT:0'),
    pX_encode: SRC.indexOf('function pX('),
    mX_decode: SRC.indexOf('mX=(e,t)=>'),
    hX_decodeKeyList: SRC.indexOf('hX=(e,t)=>'),
    gX_decodeWheelKeys: SRC.indexOf('gX=(e,t)=>'),
    kX_decodeFuncV2: SRC.indexOf('kX=e=>'),
    allKeyChars: tables.allKeyChars.offset,
    basicChars: tables.basicChars.offset,
    extendChars: tables.extendChars.offset,
    jaExtendChars: tables.jaExtendChars.offset,
    specialChars: tables.specialChars.offset,
    funcChars: tables.funcChars.offset,
    funcV2Chars: tables.funcV2Chars.offset,
    charactersExportMap: SRC.indexOf('nX=t({'),
    mk87Config: open,
    deviceInit: SRC.indexOf('WX=async(e,t)=>'),
  },
  errorCodes: {},
};

// ---------------------------------------------------------------- device (optional)
// 如果 Lead 已经跑过真机读取（docs/keymap_device_report.txt），把这份"实测"数据一并挂进 JSON，
// 让实现方一眼能看到「配置里的 87 槽」与「设备里真实的 112 个非零槽」的差异。
function readDeviceReport() {
  const p = path.join(__dirname, '..', 'docs', 'keymap_device_report.txt');
  if (!fs.existsSync(p)) return null;
  const txt = fs.readFileSync(p, 'utf8');
  const grab = (re, s) => [...s.matchAll(re)].map(m => m.slice(1));
  // 注意：键名里可能含 ']'（如 slot 44 的 `[] }]`），所以用非贪婪到「] + 空白 + 4 组 hex」
  const normal = grab(/slot\s+(\d+)\s+\[(.*?)\]\s+([0-9a-f]{2} [0-9a-f]{2} [0-9a-f]{2} [0-9a-f]{2})/g,
    txt.slice(0, Math.max(0, txt.indexOf('== 主层 vs FN'))));
  const fn = grab(/slot\s+(\d+)\s+\[(.*?)\]\s+主=\S+ \S+ \S+ \S+[^F]*FN=([0-9a-f]{2} [0-9a-f]{2} [0-9a-f]{2} [0-9a-f]{2})/g,
    txt.slice(txt.indexOf('== 主层 vs FN'), txt.indexOf('== FN 层 vs 默认FN层')));
  const declared = (txt.match(/非零条目:\s*(\d+)\s*\/\s*(\d+)/) || []).slice(1, 3).map(Number);
  const cfgSlots = new Set(flat.map(k => k.value));
  const normalRows = normal.map(([slot, name, bytes]) => ({ slot: +slot, name, bytes }));
  return {
    source: 'docs/keymap_device_report.txt（硬件通道由 Lead 读取；本 JSON 只做汇总）',
    caution: '真机普通层非零槽里有若干不在 keyboardConfig.keyList 里；SET_KEY 是整块覆盖，改键必须读-改-写整 512 字节。',
    readLengthPitfall: '512 字节按 56 字节/包传 → 扁平化得 560 字节，官方代码 .slice(0,512)，必须截断。',
    normalNonZeroCount: declared[0] || normalRows.length,
    normalSlotCount: declared[1] || 128,
    normalEntries: normalRows,
    extraNonZeroSlotsNotInConfig: normalRows.filter(r => !cfgSlots.has(r.slot)),
    fnPageTypes: [...new Set(fn.map(([, , b]) => parseInt(b.slice(0, 2), 16)))],
    fnVsNormalEntries: fn.map(([slot, name, bytes]) => ({ slot: +slot, name, fnBytes: bytes })),
  };
}
const device = readDeviceReport();

const out = {
  meta: {
    title: 'AJAZZ MK87 (VID 0x0C45 / PID 0x8047) 按键映射 4 字节编码 —— 动作/页面类型表',
    source: 'assets/layout-classic-CMxiG14P.js（官方网页驱动 bundle，rolldown 打包，未混淆）',
    generator: 'scripts/gen_tables_json.js',
    generatedAt: facts.generatedAt,
    bundleOffsets: facts.offsets,
    note: 'table 里的 offset 是 bundle 内字符偏移（0-based）。条目内容为原样 JSON 化，未做语义改名。',
  },
  pageTypes,
  pageTypeEnumSource: "fX={DEFAULT:0,MOUSE:1,KEYBOARD:2,CONSUMER_KEY:3,SYSTEM_KEY:4,EXTRA_FUNCTION:5,MACRO:6,CB:7,DKS:8,MT:9,TGL:10,SOCD:11,RS:12,FUNC:13,END:14,MPT:15}",
  funcV2Layout: {
    marker: '0x80',
    slotA: '12-bit: (pageType & 0x7F) << 8 | param1  → 0..32767',
    slotB: '16-bit: param2 << 8 | param3 → 0..65535',
    keyType1: 'value 写入 slotB（byte2/byte3），slotA=0',
    keyType2: 'value 写入 slotA（byte0/byte1），slotB=0',
    decodeNameRule: 'name = table_B.name || table_A.name（优先槽 B）；两槽各自独立查 iX/aX（当值 <4096）或 lX（否则）',
  },
  tables,
  tablesOrder: TABLES.map(t => t[1]),
  mk87KeyboardConfig: mk87,
  keyboardLayoutNote: '512 字节 = 128 槽 × 4 字节；槽号 = allKeyChars(rX) 的 value（canonical key id），也是 MK87 keyList 里每个键的 value（slot = value*4 的字节偏移）',
};
if (device) out.deviceObserved = device;

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
console.log('wrote', OUT);
for (const k of Object.keys(tables)) console.log(`  ${k}: ${tables[k].count} entries @${tables[k].offset}`);
console.log('  mk87 keys:', mk87.keyCount, 'empty slots:', mk87.isEmptySlot.length);
console.log('  offsets:', JSON.stringify(facts.offsets, null, 1));
