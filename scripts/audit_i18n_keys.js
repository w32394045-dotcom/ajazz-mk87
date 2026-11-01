#!/usr/bin/env node
/**
 * audit_i18n_keys.js — 审计「bundle 里被引用的 i18n key」与「语言包里实际存在的 key」
 *
 * 做法：扫所有官方 chunk（含 layout + 懒加载 chunk + 语言包自身），
 *   1) 抓 $t(`key`) / $(`key`) / $t("key") 形式的字面量；
 *   2) 抓任何 .$t(`key`) 变量形式；
 *   与 docs/i18n-keys.json 对比，输出「被引用但语言包缺失」的键（官方 UI 会直接显示原始 key）。
 *
 * 用法：node scripts/audit_i18n_keys.js [--json]
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const ASSETS = path.join(ROOT, 'assets');
const i18n = JSON.parse(fs.readFileSync(path.join(ROOT, 'docs', 'i18n-keys.json'), 'utf8'));

const files = fs
  .readdirSync(ASSETS)
  .filter((f) => f.endsWith('.js'))
  .map((f) => path.join(ASSETS, f))
  .concat([path.join(ASSETS, 'i18n', 'zh.js')]);

const BT = String.fromCharCode(96); // `
const Q = String.fromCharCode(34); // "
const SQ = String.fromCharCode(39); // '

// 允许的 key 形状：字母数字下划线点横线，至少要有一个非数字（排除纯数字）
const KEY_RE = /^[A-Za-z0-9_.-]{2,60}$/;

const used = new Map(); // key -> Set(file)
function add(k, f) {
  if (!KEY_RE.test(k)) return;
  if (!used.has(k)) used.set(k, new Set());
  used.get(k).add(path.basename(f));
}

// 只认 i18n 调用形态：$(`key`) / $t(`key`) / $(`key`, ...) / $t("key")
// 注意 minify 后仍保留 `$` 这个标识符（bundle 里 `$ = lH.global.t`），
// 但调用点常写成 z($)(`key`) / t.$t(`key`) / e.$t(`key`)，所以用「$ 或 $t 紧跟 ( 」即可。
const CALL_RE = /\$(?:t)?\(\s*(`[^`\n]{2,60}`|"[^"\n]{2,60}"|'[^'\n]{2,60}')/g;

for (const f of files) {
  const t = fs.readFileSync(f, 'utf8');
  let m;
  while ((m = CALL_RE.exec(t))) {
    const k = m[1].slice(1, -1);
    if (/^[A-Za-z][A-Za-z0-9_.-]*$/.test(k)) add(k, f);
  }
}

const known = new Set(Object.keys(i18n));
const all = [...used.keys()];
const missing = all.filter((k) => !known.has(k)).sort();

// 再筛一遍：只保留「看起来确实是 i18n key」的（出现在 i18n 包里同风格、且不是常见函数参数）
const obvious = missing.filter((k) => k.length >= 3 && !/^(px|em|rem|svg|png|jpg|json|js|ts|css|html|GET|POST)$/i.test(k));

if (process.argv.includes('--json')) {
  console.log(JSON.stringify({ referenced: all.length, known: known.size, missing: obvious }, null, 2));
} else {
  console.log(`chunks scanned: ${files.length}`);
  console.log(`literal keys referenced: ${all.length}`);
  console.log(`keys in locale pack: ${known.size}`);
  console.log(`referenced but MISSING from pack: ${obvious.length}`);
  for (const k of obvious) console.log('  -', k, '<-', [...used.get(k)].join(','));
}
