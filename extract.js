// Minimal JS scanner + protocol extractor for the minified AJAZZ web-driver bundle.
// Usage: node extract.js <bundle.js> [outDir]
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(process.argv[2], 'utf8');
const OUT = process.argv[3] || path.join(__dirname, 'docs');
fs.mkdirSync(OUT, { recursive: true });

const OPENERS = '({[';
const CLOSERS = ')}]';
const REGEX_PREV = new Set('(,=:[!&|?{};+-*%<>~^'.split(''));

function regexAllowed(prev) {
  if (!prev) return true;
  return REGEX_PREV.has(prev) || prev === 'return';
}

// Return index of matching close for opener at `start`.
function matchPair(s, start) {
  const main = [];
  const mode = []; // 'tpl' | 'expr'
  let exprDepth = []; // brace depth inside each active ${...}
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
            // closing a template expression
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

// Very small beautifier: break lines on ; { } and indent.
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
    if (state === 'regex') { out += c; if (c === '\\') { out += s[i + 1] || ''; i++; } else if (c === '[') state = 'regexClass'; else if (c === '/') { state = 'code'; while (/[a-z]/i.test(code[i + 1] || '')) out += code[++i]; } continue; }
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

function findDef(name) {
  // returns {kind, code, start}
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
        return { code: SRC.slice(m.index, end + 1), start: m.index };
      }
      // expression until top-level ; or ,
      let depth = 0; let i = startIdx;
      while (i < SRC.length) {
        const c = SRC[i];
        if (OPENERS.includes(c)) depth++;
        else if (CLOSERS.includes(c)) { if (depth === 0) break; depth--; }
        else if ((c === ';' || c === ',') && depth === 0) break;
        i++;
      }
      return { code: SRC.slice(m.index, i), start: m.index };
    }
    // locate body
    let i = m.index + m[0].length - 1; // points before '('
    // find first '(' from m start
    const pStart = SRC.indexOf('(', m.index + m[0].length - 2 >= 0 ? 0 : 0);
    // simpler: find '(' after the name
    let k = m.index + m[0].length - 1;
    while (k < SRC.length && SRC[k] !== '(') k++;
    const pEnd = matchPair(SRC, k);
    let j = pEnd + 1;
    while (j < SRC.length && /\s/.test(SRC[j])) j++;
    if (SRC[j] === '=' && SRC[j + 1] === '>') {
      j += 2; while (j < SRC.length && /\s/.test(SRC[j])) j++;
      if (SRC[j] === '{') {
        const end = matchPair(SRC, j);
        return { code: SRC.slice(m.index, end + 1), start: m.index };
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
      return { code: SRC.slice(m.index, q), start: m.index };
    }
    if (SRC[j] === '{') {
      const end = matchPair(SRC, j);
      return { code: SRC.slice(m.index, end + 1), start: m.index };
    }
  }
  return null;
}

function save(name, text) {
  fs.writeFileSync(path.join(OUT, name), text);
  return `${name}: ${text.length} bytes`;
}

// ---------- 1. all export maps `X=t({...})` ----------
const maps = [];
const reMap = /\b([A-Za-z_$][\w$]*)\s*=\s*t\(\{/g;
let m;
while ((m = reMap.exec(SRC))) {
  const brace = SRC.indexOf('{', m.index);
  const end = matchPair(SRC, brace);
  const body = SRC.slice(brace, end + 1);
  const entries = [...body.matchAll(/([A-Za-z_$][\w$]*)\s*:\s*\(\)\s*=>\s*([A-Za-z_$][\w$]*)/g)]
    .map(x => ({ name: x[1], local: x[2] }));
  maps.push({ mod: m[1], start: m.index, entries, body });
}
const mapReport = maps.map(x => `${x.mod} @${x.start} entries=${x.entries.length} ${x.entries.slice(0, 6).map(e => e.name).join(',')}`).join('\n');
console.log('=== export maps ===\n' + mapReport);

// pick the module containing "deviceInit" (protocol module)
const proto = maps.find(x => x.entries.some(e => e.name === 'deviceInit' && e.local)) || maps.find(x => x.entries.length > 30);
if (!proto) { console.error('protocol module not found'); process.exit(1); }
console.log(`\n=== protocol module: ${proto.mod} (${proto.entries.length} commands) ===`);
save('_map_' + proto.mod + '.json', JSON.stringify(proto.entries, null, 2));

// ---------- 2. extract each command implementation ----------
let missing = [];
let chunks = [];
for (const e of proto.entries) {
  const d = findDef(e.local);
  if (!d) { missing.push(e.name + ' -> ' + e.local); continue; }
  chunks.push(`// ===== ${e.name}  (local ${e.local}) =====\n` + beautify(d.code) + '\n');
}
save('protocol_commands.js', chunks.join('\n'));
console.log(`extracted commands: ${chunks.length}, missing: ${missing.length}`);
if (missing.length) console.log('MISSING:\n' + missing.join('\n'));

// ---------- 3. infra helpers ----------
const INFRA = ['RX', 'PX', 'IX', 'FX', 'NX', 'YX', 'wV', 'zY', 're', 'oe', 'HX', 'VX', 'UX', 'BX'];
let infraOut = [];
for (const n of INFRA) {
  const d = findDef(n);
  infraOut.push(`// ===== ${n} =====\n` + (d ? beautify(d.code) : 'NOT FOUND') + '\n');
}
save('infra.js', infraOut.join('\n'));
console.log('infra saved');

// HX enum as readable table
const hxDef = findDef('HX');
if (hxDef) {
  const body = hxDef.code.slice(hxDef.code.indexOf('{'), hxDef.code.lastIndexOf('}') + 1);
  const pairs = [...body.matchAll(/([A-Z][A-Z0-9_]+)\s*:\s*(\d+)/g)].map(x => `${x[1]} = ${x[2]} (0x${Number(x[2]).toString(16)})`);
  save('command_enum.txt', pairs.join('\n'));
  console.log('HX entries:', pairs.length);
}
