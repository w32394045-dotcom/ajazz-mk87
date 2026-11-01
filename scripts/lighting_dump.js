// lighting_dump.js — offsets/snippet dump helper for layout-classic bundle (self-contained, no require)
// Usage:
//   node lighting_dump.js ctx <offset> <before> <after>
//   node lighting_dump.js find <keyword> [maxHits] [sliceLen]
//   node lighting_dump.js lines <startOffset> <endOffset>       // print with line numbers
//   node lighting_dump.js grep <regex> [maxHits] [sliceLen]
const fs = require('fs');
const P = 'C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js';
const s = fs.readFileSync(P, 'utf8');

// precompute line starts
const lineStart = [0];
for (let i = 0; i < s.length; i++) if (s[i] === '\n') lineStart.push(i + 1);
function lineOf(off) {
  let lo = 0, hi = lineStart.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (lineStart[mid] <= off) lo = mid; else hi = mid - 1; }
  return lo + 1; // 1-based
}
function colOf(off) { return off - lineStart[lineOf(off) - 1] + 1; }

const [, , cmd, a1, a2, a3] = process.argv;
if (cmd === 'ctx') {
  const off = +a1, b = +(a2 || 300), af = +(a3 || 300);
  const st = Math.max(0, off - b), en = Math.min(s.length, off + af);
  console.log(`[offset ${off}] line ${lineOf(off)} col ${colOf(off)}`);
  process.stdout.write(s.slice(st, en));
  console.log('\n--- end ---');
} else if (cmd === 'find') {
  const kw = a1, max = +(a2 || 20), len = +(a3 || 600);
  let i = -1, n = 0;
  while ((i = s.indexOf(kw, i + 1)) !== -1 && n < max) {
    n++;
    console.log(`### hit #${n} offset=${i} line=${lineOf(i)} col=${colOf(i)}`);
    console.log(s.slice(i, i + len).replace(/\n/g, '\\n'));
    console.log('');
  }
  console.log(`total hits scanned: ${n}`);
} else if (cmd === 'grep') {
  const re = new RegExp(a1, 'g');
  const max = +(a2 || 20), len = +(a3 || 400);
  let m, n = 0;
  while ((m = re.exec(s)) !== null && n < max) {
    n++;
    console.log(`### hit #${n} offset=${m.index} line=${lineOf(m.index)} col=${colOf(m.index)} :: ${JSON.stringify(m[0]).slice(0, 200)}`);
    console.log(s.slice(m.index, m.index + len).replace(/\n/g, '\\n'));
    console.log('');
    if (m[0].length === 0) re.lastIndex++;
  }
  console.log(`hits printed: ${n}`);
} else if (cmd === 'lines') {
  const st = +a1, en = +a2;
  const l0 = lineOf(st), l1 = lineOf(en);
  for (let l = l0; l <= l1; l++) {
    const a = lineStart[l - 1], b = l < lineStart.length ? lineStart[l] : s.length;
    console.log(`${l} [${a}] ${s.slice(Math.max(a, st), Math.min(b, en))}`);
  }
} else {
  console.log('cmd: ctx|find|grep|lines');
}
