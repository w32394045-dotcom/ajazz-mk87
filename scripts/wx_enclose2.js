// wx_enclose2.js — 找包含 token 的最小合理函数体（限定回扫窗口，避免命中整包模块）
// node wx_enclose2.js <token> [occIndex] [backWindow=40000] [maxSize=60000]
'use strict';
const L = require('./wx_lib');
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, '..', 'docs', '_wireless_raw');
fs.mkdirSync(OUT, { recursive: true });
L.load();
const S = L.src();
const token = process.argv[2];
const occ = +(process.argv[3] || 0);
const backWindow = +(process.argv[4] || 40000);
const maxSize = +(process.argv[5] || 60000);

const hits = L.findAll(token);
const pos = hits[occ];
if (pos === undefined) { console.log('no hit'); process.exit(1); }

const from = Math.max(0, pos - backWindow);
const window = S.slice(from, pos + 1);

// 候选起点：'function '、'=>{'、')=>{'、'=()=>' 等
const cands = new Set();
for (const re of [/function\s+[A-Za-z_$][\w$]*\s*\(/g, /=>\s*\{/g]) {
  let m;
  while ((m = re.exec(window))) {
    cands.add(from + (re.source.startsWith('function') ? m.index : m.index + m[0].length - 1));
  }
}

function bodyFromBrace(b) {
  const e = L.matchPair(S, b);
  return { start: b, end: e };
}
function bodyFromFn(k) {
  let j = k + 8;
  let guard = 0;
  while (j < S.length && S[j] !== '(' && guard++ < 400) j++;
  if (S[j] !== '(') return null;
  const pEnd = L.matchPair(S, j);
  let b = pEnd + 1;
  while (b < S.length && /\s/.test(S[b])) b++;
  if (S[b] !== '{') return null;
  return bodyFromBrace(b);
}

let best = null;
for (const c of [...cands].sort((a, b) => a - b)) {
  let r;
  if (S.slice(c, c + 8) === 'function') r = bodyFromFn(c);
  else if (S[c] === '{') r = bodyFromBrace(c);
  if (!r) continue;
  if (!(r.start < pos && r.end > pos)) continue;
  const size = r.end - r.start + 1;
  if (size > maxSize) continue;
  if (!best || size > best.size) best = { ...r, size };
}
if (!best) { console.log('no enclosing body under size limit'); process.exit(1); }
console.log(`token ${token}[${occ}] @${pos}; enclosing @${best.start}..${best.end} (${best.size} bytes)`);
const code = S.slice(best.start, best.end + 1);
const label = `encl_${token.replace(/[^\w$]/g, '_')}_${occ}.js`;
fs.writeFileSync(path.join(OUT, label), L.beautify(code));
console.log(`saved ${path.join(OUT, label)}`);
