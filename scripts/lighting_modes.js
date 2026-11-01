// lighting_modes.js — evaluate the official protocol lighting config chunk into JSON (data-only module)
// Usage: node lighting_modes.js [pathToChunk] [outJson]
const fs = require('fs');
const IN = process.argv[2] || 'C:/Users/ptfm/Documents/ajazz-re/docs/_lighting_raw/lighting-DzPku7KQ.js';
const OUT = process.argv[3] || 'C:/Users/ptfm/Documents/ajazz-re/docs/_lighting_raw/lighting-modes.raw.json';

let src = fs.readFileSync(IN, 'utf8');
const m = src.match(/export\s*\{([^}]*)\}\s*;?\s*$/);
if (!m) throw new Error('export block not found');
const exprs = m[1].split(',').map(s => s.trim()).filter(Boolean).map(pair => {
  const [local, exported] = pair.split(/\s+as\s+/).map(s => s.trim());
  return `${exported}:${local}`;
});
src = src.slice(0, m.index) + `\n;module.exports={${exprs.join(',')}};`;
fs.writeFileSync(OUT.replace(/\.json$/, '.eval.js'), src);
const mod = { exports: {} };
new Function('module', 'exports', src)(mod, mod.exports);
const data = mod.exports;
fs.writeFileSync(OUT, JSON.stringify(data, null, 2));
console.log('written', OUT);
for (const k of Object.keys(data)) {
  const v = data[k];
  console.log(`\n===== ${k} (${Array.isArray(v) ? v.length + ' items' : typeof v}) =====`);
  if (!Array.isArray(v)) { console.log(JSON.stringify(v)); continue; }
  for (const it of v) {
    const extra = Object.entries(it).filter(([kk]) => !['name', 'text', 'value', 'icon', 'sort'].includes(kk))
      .map(([kk, vv]) => `${kk}=${JSON.stringify(vv)}`).join(' ');
    console.log(`  value=${String(it.value).padStart(3)}  ${it.name}  [${it.text}]  sort=${it.sort}  ${extra}`);
  }
}
