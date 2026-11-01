// wx_cfgmap.js — 导出 VY（配置文件映射表）的 key 列表，并按 pid/名分类
'use strict';
const L = require('./wx_lib');
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, '..', 'docs', '_wireless_raw');
fs.mkdirSync(OUT, { recursive: true });
L.load();
const S = L.src();

// 找 key 形如 "/src/config/keyboards/<supplier>/<vid>-<pid>-<name>[-<mfr>-<prod>].ts"
const re = /"\/src\/config\/keyboards\/([^/"]+)\/([^"]+)\.ts":([A-Za-z_$][\w$]*)/g;
const entries = [];
let m;
while ((m = re.exec(S))) {
  entries.push({ path: m[1], file: m[2], local: m[3], at: m.index });
}
fs.writeFileSync(path.join(OUT, 'config_map.json'), JSON.stringify(entries, null, 2));
console.log(`config entries = ${entries.length}`);

const suppliers = {};
for (const e of entries) suppliers[e.path] = (suppliers[e.path] || 0) + 1;
console.log('suppliers:', JSON.stringify(suppliers));

const is24 = entries.filter(e => /2\.4G|Dongle|Wireless|8K/i.test(e.file));
console.log(`2.4G-ish configs = ${is24.length}`);
fs.writeFileSync(path.join(OUT, 'config_map_24g.json'), JSON.stringify(is24, null, 2));

// 解析 5/3 段
const parsed = entries.map(e => {
  const parts = e.file.split('-');
  // vid-pid-rest...
  const vid = parts[0], pid = parts[1];
  const rest = parts.slice(2);
  // 末两段是 manufacturer/product（数字）
  let mfr = null, prod = null;
  if (rest.length >= 3 && /^\d+$/.test(rest[rest.length - 1]) && /^\d+$/.test(rest[rest.length - 2])) {
    mfr = +rest[rest.length - 2]; prod = +rest[rest.length - 1];
    rest.length -= 2;
  }
  return { ...e, vendorId: +vid, productId: +pid, name: rest.join('-'), manufacturer: mfr, product: prod };
});
fs.writeFileSync(path.join(OUT, 'config_map_parsed.json'), JSON.stringify(parsed, null, 2));
const withMfr = parsed.filter(p => p.manufacturer !== null);
console.log(`configs with manufacturer/product suffix = ${withMfr.length}`);
console.log('sample:', withMfr.slice(0, 5).map(p => `${p.vendorId}-${p.productId}-${p.name}-${p.manufacturer}-${p.product}`).join(' | '));
console.log('\n== 2.4G configs with mfr/prod (sorted by pid) ==');
for (const p of withMfr.filter(p => /2\.4G|Dongle|Wireless/i.test(p.name)).sort((a, b) => a.productId - b.productId || a.name.localeCompare(b.name))) {
  console.log(`${p.vendorId}-${p.productId}-${p.name}-${p.manufacturer}-${p.product}\t${p.local}@${p.at}`);
}
console.log('\n== mfr/prod values frequency ==');
const mp = {};
for (const p of withMfr) { const k = `${p.manufacturer}:${p.product}`; mp[k] = (mp[k] || 0) + 1; }
console.log(JSON.stringify(mp));
