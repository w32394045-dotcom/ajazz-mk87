#!/usr/bin/env node
/**
 * build_func_i18n.js — 把「FUNC / FUNC_V2 动作表」和「i18n 语言包」join 起来
 *
 * 输入（均已有成果，只读）：
 *   docs/keymap-tables.json    tables.funcChars(292) / funcV2Chars(62) / specialChars / extendChars
 *   docs/i18n-keys.json        由 scripts/fetch_i18n.js 生成的 key->{zh,en}
 *   docs/fn-layer-decode.json  MK87 真机 FN 层 128 槽解码（含 func_id）
 * 输出：
 *   docs/func-i18n-map.json    id -> {name(官方中文名), i18nKey, zh, en, page}
 *
 * 用途：确认 bundle 里 FUNC 表的动作名与官方语言包文案一致（哪条缺 key、哪条文案被改过）。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const P = (f) => path.join(ROOT, f);
const readJson = (f) => JSON.parse(fs.readFileSync(P(f), 'utf8'));

const tables = readJson('docs/keymap-tables.json');
const i18n = readJson('docs/i18n-keys.json');
const fnLayer = readJson('docs/fn-layer-decode.json');

function joinTable(list, page) {
  const out = {};
  const missing = [];
  for (const e of list) {
    const key = e.text || null;
    const t = key ? i18n[key] : null;
    if (key && !t) missing.push({ value: e.value, name: e.name, i18nKey: key });
    out[e.value] = {
      value: e.value,
      page,
      name: e.name || null,
      i18nKey: key,
      zh: t ? t.zh : null,
      en: t ? t.en : null,
      keyType: e.keyType ?? null,
    };
  }
  return { entries: out, missing };
}

const func = joinTable(tables.tables.funcChars.entries, 'FUNC');
const funcV2 = joinTable(tables.tables.funcV2Chars.entries, 'FUNC_V2');

// MK87 FN 层实际用到的 FUNC id（真机解码）
const usedIds = [...new Set(fnLayer.map((s) => s.func_id).filter((v) => typeof v === 'number'))].sort((a, b) => a - b);
const usedOnMk87 = usedIds.map((id) => {
  const e = func.entries[id] || null;
  const slots = fnLayer.filter((s) => s.func_id === id).map((s) => s.key || s.slot);
  return {
    funcId: id,
    name: e?.name ?? null,
    i18nKey: e?.i18nKey ?? null,
    zh: e?.zh ?? null,
    en: e?.en ?? null,
    slots,
  };
});

// 语言包里存在但 FUNC 表没引用的 fun_text*（多为历史遗留/别机型动作）
const referenced = new Set(
  Object.values(tables.tables)
    .flatMap((t) => t.entries || [])
    .map((e) => e.text)
    .filter(Boolean)
);
const unreferenced = Object.keys(i18n)
  .filter((k) => /^(fun_text|fun2_|medium_text)/.test(k) && !referenced.has(k))
  .sort();

const out = {
  meta: {
    title: 'FUNC / FUNC_V2 动作 id ↔ 官方 i18n 文案',
    source: [
      'assets/layout-classic-CMxiG14P.js（sX=funcChars @1884055, lX=funcV2Chars @1900260, oX=specialChars @1882523）',
      'assets/i18n/zh.js + en.js（官方语言包 chunk）',
      'docs/fn-layer-decode.json（MK87 真机 FN 层）',
    ],
    generator: 'scripts/build_func_i18n.js',
    generatedAt: new Date().toISOString(),
    counts: {
      func: Object.keys(func.entries).length,
      funcV2: Object.keys(funcV2.entries).length,
      usedOnMk87: usedIds.length,
      i18nKeysReferenced: referenced.size,
      i18nMissingKeys: func.missing.length + funcV2.missing.length,
      i18nUnreferenced: unreferenced.length,
    },
  },
  FUNC: func.entries,
  FUNC_V2: funcV2.entries,
  mk87FnLayerActions: usedOnMk87,
  i18nMissingInPack: [...func.missing, ...funcV2.missing.map((m) => ({ ...m, page: 'FUNC_V2' }))],
  i18nKeysNotReferencedByTables: unreferenced,
};

fs.writeFileSync(P('docs/func-i18n-map.json'), JSON.stringify(out, null, 2) + '\n');
console.log(
  `docs/func-i18n-map.json: FUNC=${out.meta.counts.func} FUNC_V2=${out.meta.counts.funcV2} ` +
    `MK87用到的动作=${usedIds.length} 缺key=${out.meta.counts.i18nMissingKeys} 未引用key=${unreferenced.length}`
);
if (out.i18nMissingInPack.length) console.log('缺 key:', JSON.stringify(out.i18nMissingInPack));
