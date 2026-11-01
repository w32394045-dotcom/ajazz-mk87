// wx_lib.js — 静态逆向辅助库（仅供本轮的 wireless/profiles/led-animation 分析用）
// 提供：bundle 载入、matchPair/beautify（复制自 extract.js）、按 token 找上下文、按名字找函数定义。
'use strict';
const fs = require('fs');
const path = require('path');

const BUNDLE = path.join(__dirname, '..', 'assets', 'layout-classic-CMxiG14P.js');

let SRC = '';
function load(file) {
  SRC = fs.readFileSync(file || BUNDLE, 'utf8');
  return SRC;
}
function src() { return SRC; }

const OPENERS = '({[';
const CLOSERS = ')}]';
const REGEX_PREV = new Set('(,=:[!&|?{};+-*%<>~^'.split(''));

function regexAllowed(prev) {
  if (!prev) return true;
  return REGEX_PREV.has(prev) || prev === 'return';
}

// --- matchPair / beautify: copied from ../extract.js (same algorithm) ---
function matchPair(s, start) {
  const main = [];
  const mode = [];
  let exprDepth = [];
  let state = 'code';
  let prev = '';
  let i = start;
  while (i < s.length) {
    const c = s[i], n = s[i + 1];
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; i += 2; continue; }
      if (c === '/' && n === '*') { state = 'block'; i += 2; continue; }
      if (c === "'" || c === '"') { state = c; i++; continue; }
      if (c === '`') { state = 'tpl'; mode.push('tpl'); i++; continue; }
      if (c === '/' && regexAllowed(prev)) { state = 'regex'; i++; continue; }
      if (OPENERS.includes(c)) {
        main.push(c);
        if (mode[mode.length - 1] === 'expr') exprDepth[exprDepth.length - 1]++;
        prev = c; i++; continue;
      }
      if (CLOSERS.includes(c)) {
        if (mode[mode.length - 1] === 'expr') {
          if (exprDepth[exprDepth.length - 1] > 0) {
            exprDepth[exprDepth.length - 1]--;
            main.pop();
          } else {
            mode.pop(); exprDepth.pop(); state = 'tpl';
            prev = c; i++; continue;
          }
        } else {
          main.pop();
        }
        if (!main.length) return i;
        prev = c; i++; continue;
      }
      if (!/\s/.test(c)) prev = c;
      i++; continue;
    }
    if (state === 'line') { if (c === '\n') state = 'code'; i++; continue; }
    if (state === 'block') { if (c === '*' && n === '/') { state = 'code'; i += 2; continue; } i++; continue; }
    if (state === 'regex') {
      if (c === '\\') { i += 2; continue; }
      if (c === '[') { state = 'regexClass'; i++; continue; }
      if (c === '/') { state = 'code'; i++; while (/[a-z]/i.test(s[i] || '')) i++; continue; }
      i++; continue;
    }
    if (state === 'regexClass') {
      if (c === '\\') { i += 2; continue; }
      if (c === ']') state = 'regex';
      i++; continue;
    }
    if (state === "'" || state === '"') {
      if (c === '\\') { i += 2; continue; }
      if (c === state) state = 'code';
      i++; continue;
    }
    if (state === 'tpl') {
      if (c === '\\') { i += 2; continue; }
      if (c === '`') { mode.pop(); state = mode.length ? 'code' : 'code'; i++; continue; }
      if (c === '$' && n === '{') {
        mode.push('expr'); exprDepth.push(0); state = 'code'; i += 2; continue;
      }
      i++; continue;
    }
    i++;
  }
  return s.length - 1;
}

function beautify(code) {
  let out = '';
  let indent = 0;
  let state = 'code';
  let prev = '';
  const pad = () => '  '.repeat(Math.max(0, indent));
  for (let i = 0; i < code.length; i++) {
    const c = code[i], n = code[i + 1];
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; out += c; continue; }
      if (c === '/' && n === '*') { state = 'block'; out += c; continue; }
      if (c === "'" || c === '"' || c === '`') { state = c; out += c; continue; }
      if (c === '/' && regexAllowed(prev)) { state = 'regex'; out += c; continue; }
      if (c === '{') { out += ' {\n'; indent++; out += pad(); prev = c; continue; }
      if (c === '}') {
        indent = Math.max(0, indent - 1);
        out = out.replace(/[ \t]*$/, '');
        out += '\n' + pad() + '}';
        prev = c; continue;
      }
      if (c === ';') { out += ';\n' + pad(); prev = c; continue; }
      prev = c; out += c; continue;
    }
    if (state === 'line') { out += c; if (c === '\n') state = 'code'; continue; }
    if (state === 'block') { out += c; if (c === '*' && n === '/') { out += n; i++; state = 'code'; } continue; }
    if (state === 'regex') { out += c; if (c === '\\') { out += code[i + 1] || ''; i++; } else if (c === '[') state = 'regexClass'; else if (c === '/') { state = 'code'; while (/[a-z]/i.test(code[i + 1] || '')) out += code[++i]; } continue; }
    if (state === 'regexClass') { out += c; if (c === '\\') { out += code[i + 1] || ''; i++; } else if (c === ']') state = 'regex'; continue; }
    if (state === "'" || state === '"') { out += c; if (c === '\\') { out += code[i + 1] || ''; i++; } else if (c === state) state = 'code'; continue; }
    if (state === '`') {
      out += c;
      if (c === '\\') { out += code[i + 1] || ''; i++; }
      else if (c === '`') state = 'code';
      continue;
    }
  }
  return out;
}

// 所有出现位置
function findAll(token, limit = 1e9) {
  const out = [];
  let i = 0;
  for (;;) {
    const k = SRC.indexOf(token, i);
    if (k < 0 || out.length >= limit) break;
    out.push(k);
    i = k + 1;
  }
  return out;
}
function count(token) { return findAll(token).length; }

// 上下文窗口
function ctx(pos, before = 200, after = 400) {
  const a = Math.max(0, pos - before), b = Math.min(SRC.length, pos + after);
  return SRC.slice(a, b);
}

// 找函数定义（function foo( / foo=( / foo=async( / foo=()=> / foo={ )
function findDef(name) {
  const esc = name.replace(/\$/g, '\\$');
  const tries = [
    { re: new RegExp('(?:async\\s+)?function\\s+' + esc + '\\s*\\('), kind: 'function' },
    { re: new RegExp('\\b' + esc + '\\s*=\\s*async\\s*(?:function\\b)?\\s*\\('), kind: 'assign' },
    { re: new RegExp('\\b' + esc + '\\s*=\\s*(?:function)\\s*\\('), kind: 'assign' },
    { re: new RegExp('\\b' + esc + '\\s*=\\s*\\('), kind: 'assign' },
    { re: new RegExp('\\b' + esc + '\\s*=\\s*'), kind: 'any' },
  ];
  for (const t of tries) {
    const m = t.re.exec(SRC);
    if (!m) continue;
    if (t.kind === 'any') {
      const startIdx = m.index + m[0].length;
      const first = SRC[startIdx];
      if (first === '{' || first === '[') {
        const end = matchPair(SRC, startIdx);
        return { code: SRC.slice(m.index, end + 1), start: m.index, end: end + 1 };
      }
      let depth = 0; let i = startIdx;
      while (i < SRC.length) {
        const c = SRC[i];
        if (OPENERS.includes(c)) depth++;
        else if (CLOSERS.includes(c)) { if (depth === 0) break; depth--; }
        else if ((c === ';' || c === ',') && depth === 0) break;
        i++;
      }
      return { code: SRC.slice(m.index, i), start: m.index, end: i };
    }
    let k = m.index + m[0].length - 1;
    while (k < SRC.length && SRC[k] !== '(') k++;
    const pEnd = matchPair(SRC, k);
    let j = pEnd + 1;
    while (j < SRC.length && /\s/.test(SRC[j])) j++;
    if (SRC[j] === '=' && SRC[j + 1] === '>') {
      j += 2; while (j < SRC.length && /\s/.test(SRC[j])) j++;
      if (SRC[j] === '{') {
        const end = matchPair(SRC, j);
        return { code: SRC.slice(m.index, end + 1), start: m.index, end: end + 1 };
      }
      let depth = 0;
      let q = j;
      while (q < SRC.length) {
        const c = SRC[q];
        if (OPENERS.includes(c)) depth++;
        else if (CLOSERS.includes(c)) { if (depth === 0) break; depth--; }
        else if ((c === ';' || c === ',') && depth === 0) break;
        q++;
      }
      return { code: SRC.slice(m.index, q), start: m.index, end: q };
    }
    if (SRC[j] === '{') {
      const end = matchPair(SRC, j);
      return { code: SRC.slice(m.index, end + 1), start: m.index, end: end + 1 };
    }
  }
  return null;
}

// 从某个 '{' 位置取整个对象/块
function blockAt(pos) {
  const end = matchPair(SRC, pos);
  return { code: SRC.slice(pos, end + 1), start: pos, end: end + 1 };
}

module.exports = { load, src, findAll, count, ctx, matchPair, beautify, findDef, blockAt, BUNDLE };
