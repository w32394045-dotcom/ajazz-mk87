// wx_probe.js — 通用上下文探针
// 用法: node wx_probe.js ctx <token> [before] [after] [maxHits]
//       node wx_probe.js def <name>[,...]          // 打印函数定义（美化）
//       node wx_probe.js block <token> [which]      // 从 token 后第一个 { 起取整块
//       node wx_probe.js count <token>[,...]
'use strict';
const L = require('./wx_lib');
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, '..', 'docs', '_wireless_raw');
fs.mkdirSync(OUT, { recursive: true });

L.load();
const [cmd, ...rest] = process.argv.slice(2);

function log(s) { process.stdout.write(s + '\n'); }

if (cmd === 'ctx') {
  const token = rest[0];
  const before = +(rest[1] ?? 150), after = +(rest[2] ?? 400), maxHits = +(rest[3] ?? 40);
  const hits = L.findAll(token).slice(0, maxHits);
  log(`# token=${token} hits=${L.count(token)} shown=${hits.length}`);
  hits.forEach((p, i) => log(`\n===== [${i}] @${p} =====\n` + L.ctx(p, before, after)));
} else if (cmd === 'def') {
  for (const name of rest) {
    const d = L.findDef(name);
    if (!d) { log(`### ${name}: NOT FOUND`); continue; }
    const body = L.beautify(d.code);
    log(`### ${name} @${d.start}..${d.end} (${d.code.length} chars)`);
    log(body);
    const f = path.join(OUT, `def_${name.replace(/[^\w$]/g, '_')}.js`);
    fs.writeFileSync(f, body);
    log(`(saved ${f})`);
  }
} else if (cmd === 'block') {
  const token = rest[0];
  const which = +(rest[1] ?? 0);
  const hits = L.findAll(token);
  if (!hits[which]) { log('no hit'); process.exit(1); }
  const p = L.src().indexOf('{', hits[which]);
  const b = L.blockAt(p);
  log(`### block after "${token}"[${which}] @${b.start}..${b.end} (${b.code.length} chars)`);
  log(L.beautify(b.code));
  fs.writeFileSync(path.join(OUT, `block_${token.replace(/[^\w$]/g, '_')}_${which}.js`), L.beautify(b.code));
} else if (cmd === 'count') {
  for (const t of rest) log(`${t}\t${L.count(t)}`);
} else {
  log('usage: node wx_probe.js ctx|def|block|count ...');
}
