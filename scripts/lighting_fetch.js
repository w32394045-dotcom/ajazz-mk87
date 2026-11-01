// lighting_fetch.js — download the official web-driver JS chunks (static HTTP GET only, no HID)
// Saves raw bytes (UTF-8) into docs/_lighting_raw/ so later analysis is lossless.
// Usage: node lighting_fetch.js [chunk1.js chunk2.js ...]
//        node lighting_fetch.js --index          # just print index.html asset refs
const fs = require('fs');
const path = require('path');
const OUT = 'C:/Users/ptfm/Documents/ajazz-re/docs/_lighting_raw';
const BASE = 'https://ajazz.driveall.cn/';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36';

async function get(u) {
  const r = await fetch(u, { headers: { 'user-agent': UA, accept: '*/*' } });
  if (!r.ok) throw new Error(`${r.status} ${u}`);
  return Buffer.from(await r.arrayBuffer());
}
function decodeUtf8(buf) { return new TextDecoder('utf-8').decode(buf); }

(async () => {
  const args = process.argv.slice(2);
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
  if (!args.length || args[0] === '--index') {
    const html = decodeUtf8(await get(BASE));
    fs.writeFileSync(path.join(OUT, '_index.html'), html);
    const refs = [...html.matchAll(/(?:src|href)="([^"]+\.(?:js|css|png|json|webp|svg))"/g)].map(m => m[1]);
    console.log('index.html saved,', html.length, 'chars');
    console.log(refs.join('\n'));
    if (args[0] === '--index') return;
  }
  for (const name of args) {
    const url = name.startsWith('http') ? name : BASE + 'assets/' + name;
    try {
      const buf = await get(url);
      const file = path.join(OUT, path.basename(name));
      fs.writeFileSync(file, buf);
      const txt = decodeUtf8(buf);
      console.log(`OK ${name} -> ${buf.length} bytes | ${txt.length} chars | head: ${JSON.stringify(txt.slice(0, 120))}`);
    } catch (e) {
      console.log(`FAIL ${name}: ${e.message}`);
    }
  }
})();
