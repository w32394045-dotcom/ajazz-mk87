// 从 bundle 中提取 MK87 (32839) 的官方键盘配置对象并转成 JSON
// node extract_config.js <bundle.js> <out.json>
const fs = require('fs');

const src = fs.readFileSync(process.argv[2], 'utf8');
const outPath = process.argv[3];

// 极简括号配对（处理 ' " ` 字符串与转义；配置对象里没有正则）
function matchBrace(s, start) {
  let depth = 0;
  let i = start;
  while (i < s.length) {
    const c = s[i];
    if (c === "'" || c === '"' || c === '`') {
      const q = c;
      i++;
      while (i < s.length) {
        if (s[i] === '\\') { i += 2; continue; }
        if (s[i] === q) { i++; break; }
        i++;
      }
      continue;
    }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return i; }
    i++;
  }
  return -1;
}

const marker = 'TU={vendorId:3141,productId:32839';
const idx = src.indexOf(marker);
if (idx < 0) { console.error('找不到 32839 配置'); process.exit(1); }
const start = src.indexOf('{', idx + marker.indexOf('{'));
const end = matchBrace(src, start);
const block = src.slice(start, end + 1);
console.log('TU block length =', block.length);

function grab(re) {
  const m = block.match(re);
  return m ? m[0] : null;
}

const config = {
  'routesName': null,
  'tftConfig': null,
  'lightingConfig': null,
  'musicConfig': null,
  'customKeysConfig': null,
  'macroConfig': null,
  'settingsConfig': null,
  'keyList': [],
};

const routes = block.match(/routesName:\[([^\]]+)\]/);
config.routesName = routes ? routes[1].replace(/`/g, '').split(',').map(s => s.trim()) : null;
for (const k of ['tftConfig', 'lightingConfig', 'musicConfig', 'customKeysConfig', 'macroConfig', 'settingsConfig']) {
  const re = new RegExp(k + ':(\\{[^{}]*\\})');
  const m = block.match(re);
  config[k] = m ? m[1] : null;
}
const keyRe = /\{className:(?:`[^`]*`|"[^"]*"),value:(\d+),name:(?:"([^"]*)"|`([^`]*)`),keyCode:(\d+)/g;
let m;
while ((m = keyRe.exec(block))) {
  config.keyList.push({ value: Number(m[1]), name: m[2] !== undefined ? m[2] : m[3], keyCode: Number(m[4]) });
}
// 有些条目可能是 name 带转义，兜底打印数量
console.log('keyList entries =', config.keyList.length);
const missing = [];
for (let i = 0; i < 128; i++) {
  if (!config.keyList.some(k => k.value === i)) missing.push(i);
}
console.log('value 缺失槽位:', missing.join(',') || '无');
fs.writeFileSync(outPath, JSON.stringify(config, null, 2));
console.log('saved', outPath);
