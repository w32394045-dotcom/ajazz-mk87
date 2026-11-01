// wx_kw.js — 关键词附近片段聚类：node wx_kw.js <token> <afterChars> [uniqOnly]
'use strict';
const L = require('./wx_lib');
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, '..', 'docs', '_wireless_raw');

L.load();
const token = process.argv[2];
const after = +(process.argv[3] || 60);
const uniqOnly = process.argv[4] !== 'all';
const hits = L.findAll(token);
const seen = new Map();
for (const p of hits) {
  const s = L.ctx(p, 0, after).replace(/\s+/g, ' ');
  if (!seen.has(s)) seen.set(s, p);
}
let out = `# token=${token} hits=${hits.length} uniq=${seen.size}\n`;
for (const [s, p] of seen) out += `@${p}\t${s}\n`;
fs.writeFileSync(path.join(OUT, `kw_${token.replace(/[^\w$]/g, '_')}.txt`), out);
console.log(out);
