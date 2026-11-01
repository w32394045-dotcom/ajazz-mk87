// ctx.js - tiny context grep / slice helper for the AJAZZ bundles (new tool, doesn't touch existing files).
// Usage:
//   node ctx.js grep <file> <regexp> [before=160] [after=400] [max=20]
//   node ctx.js slice <file> <start> <end> [--raw]      (beautified by default)
//   node ctx.js find <file> <regexp>                    (print only match positions + line numbers)
const fs = require('fs');
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
function beautify(code) {
  let out = ''; let indent = 0; let state = 'code'; let prev = '';
  const pad = () => '  '.repeat(Math.max(0, indent));
  for (let i = 0; i < code.length; i++) {
    const c = code[i], n = code[i + 1];
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; out += c; continue; }
      if (c === '/' && n === '*') { state = 'block'; out += c; continue; }
      if (c === "'" || c === '"' || c === '`') { state = c; out += c; continue; }
      if (c === '/' && regexAllowed(prev)) { state = 'regex'; out += c; continue; }
      if (c === '{') { out += ' {\n'; indent++; out += pad(); prev = c; continue; }
      if (c === '}') { indent = Math.max(0, indent - 1); out = out.replace(/[ \t]*$/, ''); out += '\n' + pad() + '}'; prev = c; continue; }
      if (c === ';') { out += ';\n' + pad(); prev = c; continue; }
      if (c === ',') { out += ',\n' + pad(); prev = c; continue; }
      prev = c; out += c; continue;
    }
    if (state === 'line') { out += c; if (c === '\n') state = 'code'; continue; }
    if (state === 'block') { out += c; if (c === '*' && n === '/') { out += n; i++; state = 'code'; } continue; }
    if (state === 'regex') { out += c; if (c === '\\') { out += code[i+1] || ''; i++; } else if (c === '[') state = 'regexClass'; else if (c === '/') { state = 'code'; while (/[a-z]/i.test(code[i+1] || '')) out += code[++i]; } continue; }
    if (state === 'regexClass') { out += c; if (c === '\\') { out += code[i+1] || ''; i++; } else if (c === ']') state = 'regex'; continue; }
    if (state === "'" || state === '"') { out += c; if (c === '\\') { out += code[i+1] || ''; i++; } else if (c === state) state = 'code'; continue; }
    if (state === '`') { out += c; if (c === '\\') { out += code[i+1] || ''; i++; } else if (c === '`') state = 'code'; continue; }
  }
  return out;
}
function lineOf(s, idx) { let n = 1; for (let i = 0; i < idx; i++) if (s[i] === '\n') n++; return n; }

const [mode, file, ...rest] = process.argv.slice(2);
const SRC = fs.readFileSync(file, 'utf8');
if (mode === 'grep') {
  const re = new RegExp(rest[0], 'g');
  const before = Number(rest[1] ?? 160), after = Number(rest[2] ?? 400), max = Number(rest[3] ?? 20);
  let m, c = 0;
  while ((m = re.exec(SRC))) {
    if (c++ >= max) break;
    const a = Math.max(0, m.index - before), b = Math.min(SRC.length, m.index + m[0].length + after);
    console.log(`\n### #${c} @${m.index} (line ${lineOf(SRC, m.index)}) len=${m[0].length}`);
    console.log(JSON.stringify(SRC.slice(a, m.index)) + ' <<<MATCH>>> ' + JSON.stringify(SRC.slice(m.index + m[0].length, b)));
    if (m[0].length === 0) re.lastIndex++;
  }
  console.log(`\n[total shown ${Math.min(c, max)}]`);
} else if (mode === 'slice') {
  const text = SRC.slice(Number(rest[0]), Number(rest[1]));
  console.log(rest.includes('--raw') ? text : beautify(text));
} else if (mode === 'find') {
  const re = new RegExp(rest[0], 'g');
  let m, c = 0;
  while ((m = re.exec(SRC))) { c++; console.log(`@${m.index} line ${lineOf(SRC, m.index)} : ${JSON.stringify(m[0])}`); if (m[0].length === 0) re.lastIndex++; }
  console.log(`[count ${c}]`);
}
