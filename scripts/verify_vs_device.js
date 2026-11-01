// 把 docs/keymap_device_report.txt（真机读回的 4 字节）与 docs/keymap.md 的模型做交叉验证。
// 只读这两个文件，不碰硬件。
const fs = require('fs');
const path = require('path');
const { decodeEntry, encodeEntry } = require('./keymap.js');

const DOCS = path.join(__dirname, '..', 'docs');
const txt = fs.readFileSync(path.join(DOCS, 'keymap_device_report.txt'), 'utf8');
const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'mk87_config.json'), 'utf8'));
const cfgSlots = new Set(cfg.keyList.flat().map(k => k.value));
const cfgName = new Map(cfg.keyList.flat().map(k => [k.value, k.name]));

const hex = (a) => a.map(x => x.toString(16).padStart(2, '0').toUpperCase()).join(' ');

// 解析 "  slot   0 [Esc]            02 00 29 00  普通键 Esc (HID 0x29)"
const rows = [];
const re = /slot\s+(\d+)\s+\[(.*?)\]\s+([0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2})/g;
let m;
while ((m = re.exec(txt))) {
  rows.push({ slot: Number(m[1]), name: m[2], bytes: m[3].split(' ').map(x => parseInt(x, 16)) });
}
// 主层是文件里第一段（"== 主按键层" 之后、"== 主层 vs FN" 之前）
const splitAt = txt.indexOf('== 主层 vs FN 层差异');
const mainRows = rows.filter(r => txt.indexOf(`slot ${String(r.slot).padStart(3)}`) < splitAt);
console.log(`解析到 ${rows.length} 行（其中主层 ${mainRows.length} 行）`);

let bad = 0, rt = 0;
console.log('\n== 主按键层：逐条解码 + 回写一致性 ==');
for (const r of mainRows) {
  const d = decodeEntry(r.bytes);
  const back = encodeEntry(d);
  const same = hex(back) === hex(r.bytes);
  if (!same) { rt++; console.log(`  ✗ slot ${r.slot} ${hex(r.bytes)} 回写变成 ${hex(back)}`); }
  const expectName = cfgName.get(r.slot);
  const okName = d.page === 'KEYBOARD' && d.value === (cfg.keyList.flat().find(k => k.value === r.slot) || {}).keyCode;
  if (!okName) { bad++; console.log(`  ? slot ${String(r.slot).padStart(3)} [${r.name}] ${hex(r.bytes)} → ${d.page}/${d.name} (config keyCode=${(cfg.keyList.flat().find(k => k.value === r.slot) || {}).keyCode})`); }
}
console.log(`回写不一致 ${rt} 条；与配置 keyCode 不符 ${bad} 条`);

// 额外槽（真机非零但不在 config keyList）
const extra = mainRows.filter(r => !cfgSlots.has(r.slot));
console.log(`\n== 真机非零、但 MK87 配置 keyList 里没有的槽：${extra.length} 个 ==`);
for (const r of extra) {
  const d = decodeEntry(r.bytes);
  console.log(`  slot ${String(r.slot).padStart(3)} ${hex(r.bytes)}  ${d.page}/${d.name}  (HID 0x${Number(d.value).toString(16)})`);
}
console.log('  槽号列表:', extra.map(r => r.slot).join(','));

// FN 层
const splitFn = txt.indexOf('== FN 层 vs 默认FN层差异');
const fnRows = rows.filter(r => {
  const idx = txt.indexOf(`slot ${String(r.slot).padStart(3)} [${r.name}]`);
  return idx > splitAt && idx < splitFn;
});
console.log(`\n== FN 层差异行：${fnRows.length} 行（文件里只列了与主层不同的） ==`);
// FN 段的行是 "主=.. FN=0d 00 00 2e"，单独再抓一次
const fnRe = /slot\s+(\d+)\s+\[(.*?)\]\s+主=([0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2})[^F]*FN=([0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2})/g;
let k, n = 0, pageTypes = new Set(), rtBad = 0, unknown = 0;
while ((k = fnRe.exec(txt))) {
  n++;
  const bytes = k[4].split(' ').map(x => parseInt(x, 16));
  const d = decodeEntry(bytes);
  pageTypes.add(d.pageType);
  const back = encodeEntry(d);
  if (hex(back) !== hex(bytes)) { rtBad++; console.log(`  ✗ FN slot ${k[1]} ${hex(bytes)} → ${hex(back)}`); }
  if (!d.known) { unknown++; console.log(`  ? FN slot ${k[1]} ${hex(bytes)} 解不出名字（pageType=${d.pageType}）`); }
  if (n <= 3) console.log(`  示例：slot ${k[1]} ${hex(bytes)} → ${d.page}/${d.name} (funcId=${d.funcId})`);
}
console.log(`FN 差异行 ${n} 条，pageType 集合 = {${[...pageTypes].join(',')}}，回写不一致 ${rtBad}，解不出名字 ${unknown}`);

// 560 vs 512 陷阱
console.log('\n== 560/512 陷阱 ==');
console.log('  512 字节数据 / 每包 56 字节 = 10 包 → 扁平化后 560 字节（末包补 0），必须 slice(0,512)');
console.log('  10*56 =', 10 * 56, '；512 落在第', Math.ceil(512 / 56), '包');

process.exitCode = (rt === 0 && rtBad === 0 && unknown === 0) ? 0 : 1;
