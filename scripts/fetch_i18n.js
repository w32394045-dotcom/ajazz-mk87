#!/usr/bin/env node
/**
 * fetch_i18n.js — 复现：抓取 AJAZZ 网页驱动 (https://ajazz.driveall.cn) 的 i18n 语言包
 *
 * 依据（bundle: assets/layout-classic-CMxiG14P.js）
 *   @~1.0210MB  nH=$I(`locale`,fL)                        // 默认 locale 由浏览器语言推导
 *   @~1.0223MB  aH(e) = fetch(XV(`${pL(e,'i18n')}.json`))  // 服务端覆盖层
 *   @~1.0136MB  XV(e) = `${location.origin}/langs/${e}`    // => /langs/<i18n>.json
 *   @~0.9539MB  pL(e,t) = cL[e][t]                         // cL = {zh:{i18n:'zh',...}, ...}
 *   @~1.0227MB  cH(e) = import(`./<locale>-<hash>.js`)      // 本地语言包（懒加载 chunk）
 *   @~1.0280MB  uH(e): 先 cH() 取本地包 -> 再 aH() 取服务端 json -> iH() 深合并且服务端优先
 *   @~1.0282MB  $ = lH.global.t                            // 就是业务代码里的 $('key')
 *
 * 结论：语言包**不在** layout chunk 里，而是每个 locale 一个独立 chunk；
 *       /langs/*.json 是叠加在上面的可选覆盖层（本站在线环境该路径返回 index.html，即不存在）。
 *
 * 用法：node scripts/fetch_i18n.js [locale ...]      # 默认 zh en
 * 产物：
 *   assets/i18n/<locale>.js       语言包 chunk 原文（ESM，var x=`...`; export{x as key,...}）
 *   assets/i18n/<locale>.json     解析后的扁平 key->text
 *   docs/i18n-keys.json           key -> { locale: text }（默认 zh/en 两列，可多列）
 *   assets/i18n/_manifest.json    抓取清单（URL / 字节数 / key 数 / 服务端覆盖层探测结果）
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const ROOT = path.resolve(__dirname, '..');
const ASSETS = path.join(ROOT, 'assets');
const I18N = path.join(ASSETS, 'i18n');
const TMP = path.join(I18N, '_tmp');
const DOCS = path.join(ROOT, 'docs');
const BASE = 'https://ajazz.driveall.cn';

// locale -> 本地 chunk 文件名。hash 直接从 bundle 的 cH() switch 表里抄的
// (layout-classic-CMxiG14P.js 偏移 ~1022xxx)。chunk 更新后 hash 会变，需重新从 bundle 提取。
const CHUNKS = {
  en: 'en-DU86yCXE.js',
  zh: 'zh-BkYJTITw.js',
  'zh-TW': 'zh-TW-BerMqD06.js',
  ja: 'ja-BkmcTA5j.js',
  ko: 'ko-BGJgjxXD.js',
  fr: 'fr-Q3GqqbRr.js',
  es: 'es-DodscOn2.js',
  pt: 'pt-UTY4XCe4.js',
  ru: 'ru-APbTdDYb.js',
  de: 'de-CoMCPMYw.js',
  it: 'it-COZIHFNy.js',
  ar: 'ar-DUIncTbA.js',
  vi: 'vi-C18T211Z.js',
  id: 'id-COad8zkS.js',
  th: 'th-86cxy3Ij.js',
  'pt-BR': 'pt-BR-DMrqZwyN.js',
  pl: 'pl-B0KDO6NR.js',
  hu: 'hu-DlX73oy2.js',
  tr: 'tr-BmpMbira.js',
  sr: 'sr-mcLDeW7s.js',
  hr: 'hr-BUlqktmB.js',
  sl: 'sl-A-16hHi-.js',
  mk: 'mk-OmKfiNdd.js',
  sq: 'sq-Go939iok.js',
  ro: 'ro-NmpB1Fp2.js',
  cs: 'cs-7fftMr4v.js',
  uk: 'uk-CFN-y9PQ.js',
};

// cL 里 i18n 字段对大部分 locale 等于 locale 本身；pt-BR 的 i18n 名也是 'pt-BR'
const I18N_NAME = Object.fromEntries(Object.keys(CHUNKS).map((k) => [k, k]));

function mkdirp(p) {
  fs.mkdirSync(p, { recursive: true });
}

async function download(url) {
  const res = await fetch(url, { redirect: 'follow' });
  const buf = Buffer.from(await res.arrayBuffer());
  return { status: res.status, ctype: res.headers.get('content-type') || '', buf };
}

/** 探测服务端覆盖层 /langs/<name>.json；只有 content-type 是 application/json 才算命中 */
async function probeServerOverlay(locale) {
  const url = `${BASE}/langs/${I18N_NAME[locale]}.json`;
  try {
    const { status, ctype, buf } = await download(url);
    if (!ctype.includes('application/json')) {
      return { url, status, ctype, hit: false, note: '非 JSON（SPA fallback index.html），覆盖层不存在' };
    }
    const json = JSON.parse(buf.toString('utf8'));
    const file = path.join(I18N, `server-${locale}.json`);
    fs.writeFileSync(file, buf);
    return { url, status, ctype, hit: true, bytes: buf.length, file: path.relative(ROOT, file), keys: Object.keys(json).length };
  } catch (e) {
    return { url, hit: false, error: String(e && e.message) };
  }
}

/** 把 ESM chunk 当模块 import 进来，拿到「导出名 == i18n key」的命名空间 */
async function importLocale(locale, jsText) {
  const file = path.join(TMP, `${locale}.mjs`);
  fs.writeFileSync(file, jsText);
  const ns = await import(pathToFileURL(file).href);
  const out = {};
  for (const [k, v] of Object.entries(ns)) {
    if (k === 'default') continue;
    if (typeof v === 'string') out[k] = v;
  }
  return out;
}

async function main() {
  const wanted = process.argv.slice(2).filter((a) => !a.startsWith('-'));
  const locales = wanted.length ? wanted : ['zh', 'en'];

  mkdirp(I18N);
  mkdirp(TMP);
  mkdirp(DOCS);

  const manifest = { base: BASE, generatedAt: new Date().toISOString(), locales: {} };
  const flat = {}; // key -> { locale: text }

  for (const locale of locales) {
    const chunk = CHUNKS[locale];
    if (!chunk) {
      console.error(`[skip] 未知 locale: ${locale}`);
      continue;
    }
    const url = `${BASE}/assets/${chunk}`;
    process.stderr.write(`[get ] ${locale.padEnd(6)} ${url}\n`);
    let text;
    try {
      const { status, ctype, buf } = await download(url);
      if (status !== 200 || !ctype.includes('javascript')) {
        console.error(`[fail] ${locale}: status=${status} ctype=${ctype}`);
        manifest.locales[locale] = { url, chunk, ok: false, status, ctype };
        continue;
      }
      text = buf.toString('utf8');
      fs.writeFileSync(path.join(I18N, `${locale}.js`), text);
    } catch (e) {
      console.error(`[fail] ${locale}: ${e.message}`);
      manifest.locales[locale] = { url, chunk, ok: false, error: String(e.message) };
      continue;
    }

    let map;
    try {
      map = await importLocale(locale, text);
    } catch (e) {
      console.error(`[fail] ${locale}: import 失败 ${e.message}`);
      manifest.locales[locale] = { url, chunk, ok: false, bytes: text.length, error: String(e.message) };
      continue;
    }

    fs.writeFileSync(path.join(I18N, `${locale}.json`), JSON.stringify(map, null, 2) + '\n');
    for (const [k, v] of Object.entries(map)) {
      (flat[k] || (flat[k] = {}))[locale] = v;
    }
    const overlay = await probeServerOverlay(locale);
    manifest.locales[locale] = {
      url,
      chunk,
      ok: true,
      bytes: Buffer.byteLength(text, 'utf8'),
      keys: Object.keys(map).length,
      serverOverlay: overlay,
    };
    process.stderr.write(`[ ok ] ${locale.padEnd(6)} keys=${Object.keys(map).length} bytes=${Buffer.byteLength(text, 'utf8')}\n`);
  }

  // 按 key 排序输出，方便 diff
  const sorted = {};
  for (const k of Object.keys(flat).sort()) sorted[k] = flat[k];
  const outFile = path.join(DOCS, 'i18n-keys.json');
  fs.writeFileSync(outFile, JSON.stringify(sorted, null, 2) + '\n');
  manifest.output = { file: path.relative(ROOT, outFile), keys: Object.keys(sorted).length, locales };
  fs.writeFileSync(path.join(I18N, '_manifest.json'), JSON.stringify(manifest, null, 2) + '\n');

  console.log(`\nWrote ${path.relative(ROOT, outFile)}  keys=${Object.keys(sorted).length}  locales=${locales.join(',')}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
