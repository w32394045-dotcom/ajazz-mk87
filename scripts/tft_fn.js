// Extract one JS definition by anchor (function/arrow body), beautified.
// node tft_fn.js <bundle> <anchorLiteral> <outFile|-> [occurrence(1-based)]
const fs = require('fs');
const path = require('path');
const [, , FILE, ANCHOR, OUT, OCC] = process.argv;
const SRC = fs.readFileSync(FILE, 'utf8');

const OPENERS = '({[';
const CLOSERS = ')}]';
const REGEX_PREV = new Set('(,=:[!&|?{};+-*%<>~^'.split(''));
function regexAllowed(prev) {
  if (!prev) return true;
  return REGEX_PREV.has(prev) || prev === 'return';
}
function matchPair(s, start) {
  const main = [];
  const mode = [];
  const exprDepth = [];
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
      if (c === '`') { mode.pop(); state = 'code'; i++; continue; }
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
  let col = 0;
  const pad = () => '  '.repeat(Math.max(0, indent));
  const nl = () => { out += '\n' + pad(); col = indent * 2; };
  const add = (s) => { out += s; col += s.length; };
  for (let i = 0; i < code.length; i++) {
    const c = code[i], n = code[i + 1];
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; add(c); continue; }
      if (c === '/' && n === '*') { state = 'block'; add(c); continue; }
      if (c === "'" || c === '"' || c === '`') { state = c; add(c); continue; }
      if (c === '/' && regexAllowed(prev)) { state = 'regex'; add(c); continue; }
      if (c === '{') { add(' {'); nl(); indent++; out += pad(); col = indent * 2; prev = c; continue; }
      if (c === '}') {
        indent = Math.max(0, indent - 1);
        out = out.replace(/[ \t]*$/, '');
        out += '\n' + pad() + '}'; col = indent * 2 + 1;
        prev = c; continue;
      }
      if (c === ';') { out += ';'; nl(); prev = c; continue; }
      if ((c === ',' && col > 110) || ((c === '&' || c === '|') && col > 100)) { add(c); nl(); prev = c; continue; }
      prev = c; add(c); continue;
    }
    if (state === 'line') { add(c); if (c === '\n') state = 'code'; continue; }
    if (state === 'block') { add(c); if (c === '*' && n === '/') { add(n); i++; state = 'code'; } continue; }
    if (state === 'regex') { add(c); if (c === '\\') { add(code[i + 1] || ''); i++; } else if (c === '[') state = 'regexClass'; else if (c === '/') { state = 'code'; while (/[a-z]/i.test(code[i + 1] || '')) add(code[++i]); } continue; }
    if (state === 'regexClass') { add(c); if (c === '\\') { add(code[i + 1] || ''); i++; } else if (c === ']') state = 'regex'; continue; }
    if (state === "'" || state === '"') { add(c); if (c === '\\') { add(code[i + 1] || ''); i++; } else if (c === state) state = 'code'; continue; }
    if (state === '`') {
      add(c);
      if (c === '\\') { add(code[i + 1] || ''); i++; }
      else if (c === '`') state = 'code';
      continue;
    }
  }
  return out;
}

// find anchor occurrence
const want = Number(OCC || 1);
let idx = -1, seen = 0;
let from = 0;
while ((idx = SRC.indexOf(ANCHOR, from)) !== -1) {
  seen++;
  if (seen === want) break;
  from = idx + 1;
}
if (idx === -1) { console.log(`anchor not found: ${ANCHOR}`); process.exit(1); }

// find first '(' or '{' after anchor
let k = idx + ANCHOR.length;
while (k < SRC.length && (SRC[k] === ' ' || SRC[k] === '\n' || SRC[k] === '\t' || SRC[k] === '\r')) k++;
if (SRC[k] !== '(' && SRC[k] !== '{' && SRC[k] !== '[') {
  while (k < SRC.length && SRC[k] !== '(' && SRC[k] !== '{' && SRC[k] !== '[') k++;
}
let end;
if (SRC[k] === '{') {
  end = matchPair(SRC, k);
} else if (SRC[k] === '[') {
  end = matchPair(SRC, k);
} else {
  const pEnd = matchPair(SRC, k);
  let j = pEnd + 1;
  while (j < SRC.length && /\s/.test(SRC[j])) j++;
  if (SRC[j] === '=' && SRC[j + 1] === '>') {
    j += 2; while (j < SRC.length && /\s/.test(SRC[j])) j++;
    if (SRC[j] === '{') end = matchPair(SRC, j);
    else {
      let depth = 0; let q = j;
      while (q < SRC.length) {
        const c = SRC[q];
        if (OPENERS.includes(c)) depth++;
        else if (CLOSERS.includes(c)) { if (depth === 0) break; depth--; }
        else if ((c === ';' || c === ',') && depth === 0) break;
        q++;
      }
      end = q;
    }
  } else if (SRC[j] === '{') end = matchPair(SRC, j);
  else end = pEnd;
}
const text = SRC.slice(idx, end + 1);
const header = `// anchor "${ANCHOR}" @0x${idx.toString(16)} len=${text.length}\n`;
if (OUT && OUT !== '-') {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, header + beautify(text));
  console.log(`${OUT}: ${beautify(text).length} bytes beautified (src ${text.length})`);
} else {
  console.log(header + beautify(text));
}
