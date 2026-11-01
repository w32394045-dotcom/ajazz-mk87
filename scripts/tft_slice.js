// Beautified slice dumper (TFT recon): node tft_slice.js <bundle> <startOff> <endOff> <outFile|->
const fs = require('fs');
const path = require('path');

const [, , FILE, S, E, OUT] = process.argv;
const SRC = fs.readFileSync(FILE, 'utf8');
const start = Number(S), end = Number(E);

const REGEX_PREV = new Set('(,=:[!&|?{};+-*%<>~^'.split(''));
function regexAllowed(prev) {
  if (!prev) return true;
  return REGEX_PREV.has(prev) || prev === 'return';
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
      if (c === '{') { add(' {\n'); indent++; out += pad(); col = indent * 2; prev = c; continue; }
      if (c === '}') {
        indent = Math.max(0, indent - 1);
        out = out.replace(/[ \t]*$/, '');
        out += '\n' + pad() + '}'; col = indent * 2 + 1;
        prev = c; continue;
      }
      if (c === ';') { out += ';'; nl(); prev = c; continue; }
      if ((c === ',' || c === '&' || c === '|' || c === '?') && col > 110) { add(c); nl(); prev = c; continue; }
      prev = c; add(c); continue;
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

const slice = SRC.slice(start, end);
const body = beautify(slice);
const header = `// slice 0x${start.toString(16)}..0x${end.toString(16)} (${start}..${end}) len=${end - start}\n`;
if (OUT && OUT !== '-') {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, header + body);
  console.log(`${OUT}: ${body.length} bytes beautified`);
} else {
  console.log(header + body);
}
