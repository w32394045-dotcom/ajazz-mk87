// Extract named array/object literal tables from the bundle.
// Usage: node tables.js
const fs = require('fs');
const SRC = fs.readFileSync('C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js', 'utf8');

const OPENERS = '({[';
const CLOSERS = ')}]';
const REGEX_PREV = new Set('(,=:[!&|?{};+-*%<>~^'.split(''));
function regexAllowed(prev) { if (!prev) return true; return REGEX_PREV.has(prev) || prev === 'return'; }
function matchPair(s, start) {
  const main = []; const mode = []; let exprDepth = []; let state = 'code'; let prev = ''; let i = start;
  while (i < s.length) {
    const c = s[i], n = s[i + 1];
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; i += 2; continue; }
      if (c === '/' && n === '*') { state = 'block'; i += 2; continue; }
      if (c === "'" || c === '"') { state = c; i++; continue; }
      if (c === '`') { state = 'tpl'; mode.push('tpl'); i++; continue; }
      if (c === '/' && regexAllowed(prev)) { state = 'regex'; i++; continue; }
      if (OPENERS.includes(c)) { main.push(c); if (mode[mode.length-1] === 'expr') exprDepth[exprDepth.length-1]++; prev = c; i++; continue; }
      if (CLOSERS.includes(c)) {
        if (mode[mode.length-1] === 'expr') {
          if (exprDepth[exprDepth.length-1] > 0) { exprDepth[exprDepth.length-1]--; main.pop(); }
          else { mode.pop(); exprDepth.pop(); state = 'tpl'; prev = c; i++; continue; }
        } else { main.pop(); }
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
    if (state === 'regexClass') { if (c === '\\') { i += 2; continue; } if (c === ']') state = 'regex'; i++; continue; }
    if (state === "'" || state === '"') { if (c === '\\') { i += 2; continue; } if (c === state) state = 'code'; i++; continue; }
    if (state === 'tpl') {
      if (c === '\\') { i += 2; continue; }
      if (c === '`') { mode.pop(); state = mode.length ? 'code' : 'code'; i++; continue; }
      if (c === '$' && n === '{') { mode.push('expr'); exprDepth.push(0); state = 'code'; i += 2; continue; }
      i++; continue;
    }
    i++;
  }
  return s.length - 1;
}

// Find `IDENT=[` or `IDENT={` and return the balanced text.
function findTable(name, startSearch = 0) {
  const re = new RegExp('(?<![\\w$.])' + name.replace(/\$/g, '\\$') + '\\s*=\\s*([\\[{])', 'g');
  re.lastIndex = startSearch;
  const m = re.exec(SRC);
  if (!m) return null;
  const brace = m.index + m[0].length - 1;
  const end = matchPair(SRC, brace);
  return { start: m.index, end, open: m[1], text: SRC.slice(brace, end + 1) };
}

module.exports = { SRC, matchPair, findTable };

if (require.main === module) {
  const names = process.argv.slice(2);
  for (const n of names) {
    const t = findTable(n);
    if (!t) { console.log(`## ${n}: NOT FOUND`); continue; }
    console.log(`## ${n} @${t.start}..${t.end} len=${t.text.length}`);
    const out = `./table_${n}.js`;
    fs.writeFileSync(out, t.text);
    console.log(`   -> ${out}`);
  }
}
