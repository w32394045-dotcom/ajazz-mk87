// lighting_devicecfg.js — extract the authoritative device config object for MK87 (0C45:8047) from the bundle
// and dump it as JSON (data-only eval). Also exports LED id <-> key table.
// Usage: node lighting_devicecfg.js [vid] [pid]
const fs = require('fs');
const BUNDLE = 'C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js';
const OUTDIR = 'C:/Users/ptfm/Documents/ajazz-re/docs/_lighting_raw';
const s = fs.readFileSync(BUNDLE, 'utf8');
const vid = Number(process.argv[2] || 3141), pid = Number(process.argv[3] || 32839);

const OPENERS = '({[', CLOSERS = ')}]';
function matchPair(str, start) {
  let depth = 0, i = start, state = 'code';
  while (i < str.length) {
    const c = str[i], n = str[i + 1];
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
    if (state === '"' || state === "'" || state === '`') {
      if (c === '\\') { i += 2; continue; }
      if (c === state) state = 'code';
      i++; continue;
    }
  }
  return -1;
}

const needle = `productId:${pid}`;
let hits = [], idx = -1;
while ((idx = s.indexOf(needle, idx + 1)) !== -1) hits.push(idx);
console.log('productId hits:', hits.length);
let found = null;
for (const h of hits) {
  // walk back to the '{' that opens this device object: search backwards for 'vendorId'
  const backWindow = s.slice(Math.max(0, h - 4000), h);
  const vIdx = backWindow.lastIndexOf('vendorId:');
  if (vIdx < 0) continue;
  const absV = Math.max(0, h - 4000) + vIdx;
  // the object must start with '{' immediately before vendorId (allow whitespace)
  let ob = absV - 1;
  while (ob > 0 && /\s/.test(s[ob])) ob--;
  if (s[ob] !== '{') continue;
  const candidateVid = Number(s.slice(absV + 9, absV + 20).match(/\d+/)[0]);
  if (candidateVid !== vid) continue;
  const end = matchPair(s, ob);
  if (end < 0) continue;
  const text = s.slice(ob, end + 1);
  if (!text.includes('keyList')) continue;   // skip the vendor/product filter table entries
  found = { start: ob, end, text };
  break;
}
if (!found) { console.error('MK87 device config object not found'); process.exit(1); }
console.log(`MK87 config object: offset ${found.start}..${found.end} (${found.text.length} chars)`);
fs.writeFileSync(`${OUTDIR}/mk87-config.raw.js`, found.text);
const cfg = new Function('return (' + found.text + ')')();
fs.writeFileSync(`${OUTDIR}/mk87-config.json`, JSON.stringify(cfg, null, 2));
console.log('lightingConfig =', JSON.stringify(cfg.lightingConfig));
console.log('musicConfig    =', JSON.stringify(cfg.musicConfig));
console.log('keyboardImg    =', cfg.keyboardImg, '| routesName =', JSON.stringify(cfg.routesName));
console.log('keyList rows   =', cfg.keyList.length, '| total keys =', cfg.keyList.reduce((a, r) => a + r.length, 0));

// LED id <-> key table (ledId == key.value, per bundle preview code)
const table = [];
cfg.keyList.forEach((row, ri) => row.forEach((k, ci) => {
  table.push({ ledId: k.value, row: ri, col: ci, name: k.name, keyCode: k.keyCode, key: k.key, className: k.className });
}));
table.sort((a, b) => a.ledId - b.ledId);
fs.writeFileSync(`${OUTDIR}/led-key-table.json`, JSON.stringify(table, null, 2));
console.log('wrote led-key-table.json entries=', table.length);
console.log('ledIds:', table.map(t => t.ledId).join(','));
const missing = [];
for (let i = 0; i < 128; i++) if (!table.some(t => t.ledId === i)) missing.push(i);
console.log('slots without a key in the 87-key config:', missing.join(','));
