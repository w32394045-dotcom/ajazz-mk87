// Regex finder: node tft_grep.js <bundle> <regexSrc> [minOff] [maxOff] [ctx]
const fs = require('fs');
const [, , FILE, RE, MIN, MAX, CTX] = process.argv;
const SRC = fs.readFileSync(FILE, 'utf8');
const min = Number(MIN || 0), max = Number(MAX || SRC.length), ctx = Number(CTX || 60);
const re = new RegExp(RE, 'g');
let m, n = 0;
while ((m = re.exec(SRC))) {
  if (m.index < min || m.index > max) continue;
  n++;
  const e = m.index + m[0].length;
  console.log(`@0x${m.index.toString(16)} (${m.index}) :: ${SRC.slice(Math.max(0, m.index - ctx), m.index)}⟦${m[0]}⟧${SRC.slice(e, e + ctx)}`);
  if (n > 400) break;
}
console.log(`-- ${n} matches`);
