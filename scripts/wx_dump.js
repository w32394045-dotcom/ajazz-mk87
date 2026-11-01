// wx_dump.js — 定向提取：S 表、$X/oe/LX 等函数
'use strict';
const L = require('./wx_lib');
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, '..', 'docs', '_wireless_raw');
fs.mkdirSync(OUT, { recursive: true });
L.load();
const S = L.src();

function save(name, text) {
  const f = path.join(OUT, name);
  fs.writeFileSync(f, text);
  console.log(`saved ${f} (${text.length} bytes)`);
}

// ---- 1. S 特殊 2.4G 设备名表 ----
const sIdx = S.indexOf('1452:591:2.4G Dongle');
const tickStart = S.lastIndexOf('`', sIdx);
const tickEnd = S.indexOf('`', sIdx);
const sRaw = S.slice(tickStart + 1, tickEnd);
save('S_special24G.txt', sRaw + '\n');
const entries = sRaw.split(',').map(x => x.trim()).filter(Boolean);
const parsed = entries.map(x => {
  const [vid, pid, ...name] = x.split(':');
  return { raw: x, vendorId: +vid, productId: +pid, productName: name.join(':') };
});
save('S_special24G.json', JSON.stringify(parsed, null, 2));
console.log(`S entries = ${entries.length}`);
const byVid = {};
for (const p of parsed) byVid[p.vendorId] = (byVid[p.vendorId] || 0) + 1;
console.log('by vid:', JSON.stringify(byVid));
console.log('vendorId 3141 (0x0C45) entries:', parsed.filter(p => p.vendorId === 3141).length);
console.log('distinct productIds for 3141:', [...new Set(parsed.filter(p => p.vendorId === 3141).map(p => p.productId))].join(','));

// ---- 2. $X 唤醒监听（extract.js 因 \b 边界漏掉） ----
function findDollar(name) {
  const re = new RegExp('(^|[^\\w$.])' + name.replace(/\$/g, '\\$') + '\\s*=\\s*', 'g');
  const m = re.exec(S);
  if (!m) return null;
  const start = m.index + m[1].length;
  const afterEq = start + m[0].length - m[1].length;
  let j = afterEq;
  // async arrow?
  const tail = S.slice(j, j + 20);
  if (tail.startsWith('async')) j += 5;
  // skip spaces
  while (/\s/.test(S[j])) j++;
  let bodyStart = -1;
  if (S[j] === '(') {
    const pEnd = L.matchPair(S, j);
    let k = pEnd + 1;
    while (/\s/.test(S[k])) k++;
    if (S[k] === '=' && S[k + 1] === '>') {
      k += 2;
      while (/\s/.test(S[k])) k++;
      bodyStart = k;
    }
  }
  if (bodyStart < 0) return null;
  let end;
  if (S[bodyStart] === '{') end = L.matchPair(S, bodyStart);
  else {
    let depth = 0, q = bodyStart;
    while (q < S.length) {
      const c = S[q];
      if ('({['.includes(c)) depth++;
      else if (')}]'.includes(c)) { if (depth === 0) break; depth--; }
      else if ((c === ';' || c === ',') && depth === 0) break;
      q++;
    }
    end = q - 1;
  }
  return { code: S.slice(start, end + 1), start };
}

for (const n of ['$X', 'XX', 'QX', 'ZX']) {
  const d = findDollar(n);
  console.log(`\n### ${n}: ${d ? '@' + d.start : 'NOT FOUND'}`);
  if (d) {
    const b = L.beautify(d.code);
    console.log(b.slice(0, 1200));
    save(`def_${n}.js`, b);
  }
}

// ---- 3. oe / LX ----
for (const n of ['oe', 'LX', 're']) {
  const d = L.findDef(n);
  if (!d) { console.log(`\n### ${n}: NOT FOUND`); continue; }
  console.log(`\n### ${n}: @${d.start} len=${d.code.length}`);
  const b = L.beautify(d.code);
  console.log(b.slice(0, 2500));
  save(`def_${n}.js`, b);
}
