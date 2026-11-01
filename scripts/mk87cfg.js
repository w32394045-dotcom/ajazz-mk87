// Extract the MK87 (productId 32839) keyboardConfig object from the bundle.
const fs = require('fs');
const { SRC, matchPair } = require('./tables.js');

const marks = [];
let i = -1;
while ((i = SRC.indexOf('productId:32839', i + 1)) >= 0) marks.push(i);
console.log('productId:32839 at', marks);

const idx = marks[0];
const eq = SRC.lastIndexOf('={', idx);       // config object starts at eq+1
const open = eq + 1;
const close = matchPair(SRC, open);
const text = SRC.slice(open, close + 1);
console.log('config object @', open, '..', close, 'len', text.length);
fs.writeFileSync('./mk87_config_raw.js', text);

const obj = new Function('return (' + text + ')')();
fs.writeFileSync('./mk87_config.json', JSON.stringify(obj, null, 1));
console.log('top keys:', Object.keys(obj).join(','));
console.log('name:', obj.name, 'vid', obj.vendorId, 'pid', obj.productId);
console.log('keyList rows:', obj.keyList.length, 'wheelKeys:', JSON.stringify(obj.wheelKeys));
const flat = obj.keyList.flat();
console.log('total keys:', flat.length, 'value min/max', Math.min(...flat.map(k => k.value)), Math.max(...flat.map(k => k.value)));
const seen = new Map();
for (const k of flat) { if (seen.has(k.value)) console.log('DUP value', k.value, k.name); seen.set(k.value, k.name); }
console.log('missing values 0..127:', [...Array(128).keys()].filter(v => !seen.has(v)).join(','));
console.log('sample:', JSON.stringify(flat.slice(0, 6)));
