// lighting_offsets.js — print all matches (offset + line number) of argv patterns in the bundle
// Usage: node lighting_offsets.js "pat1" "pat2" ...
const fs = require('fs');
const P = 'C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js';
const s = fs.readFileSync(P, 'utf8');
const lineStart = [0];
for (let i = 0; i < s.length; i++) if (s[i] === '\n') lineStart.push(i + 1);
const lineOf = (off) => {
  let lo = 0, hi = lineStart.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (lineStart[mid] <= off) lo = mid; else hi = mid - 1; }
  return lo + 1;
};
for (const p of process.argv.slice(2)) {
  let i = -1; const hits = [];
  while ((i = s.indexOf(p, i + 1)) !== -1 && hits.length < 8) hits.push(`${i}(L${lineOf(i)})`);
  console.log(`${hits.length ? hits.join(' ') : 'NOT FOUND'}   <= ${JSON.stringify(p)}`);
}
