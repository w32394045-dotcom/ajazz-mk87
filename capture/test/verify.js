#!/usr/bin/env node
'use strict';
/*!
 * test/verify.js —— 校验 run.js 产出的 JSONL 是否符合预期（零依赖）
 *
 * 用法：node test/verify.js test/ajazz_test_log.jsonl
 * 退出码：0 全部通过；1 有失败项（输出会列出每一项 PASS/FAIL）
 *
 * 校验点：
 *   1. 文件存在且每行都是合法 JSON
 *   2. 必备字段齐全（ts/dir/phase/method/reportId/data/device/collections/caller/error）
 *   3. 覆盖到了所有关键通道：open / out / out-feature / in-feature / in / hid / event
 *   4. sendReport 的 reportId 与字节序列正确
 *   5. inputreport 的字节序列正确
 *   6. 设备名 "KEYBOARD " 前缀已被剥离；collections 带 usagePage
 *   7. requestDevice 的 filters 被记录
 *   8. caller 能定位到测试页
 *   9. 没有任何 error 记录
 */

const fs = require('node:fs');

let failures = 0;
let passes = 0;

function check(name, ok, detail) {
  if (ok) { passes++; console.log(`  PASS  ${name}` + (detail ? `  :: ${detail}` : '')); }
  else { failures++; console.log(`  FAIL  ${name}` + (detail ? `  :: ${detail}` : '')); }
}

function main() {
  const file = process.argv[2] || 'test/ajazz_test_log.jsonl';
  console.log('='.repeat(72));
  console.log(`校验日志: ${file}`);
  console.log('='.repeat(72));

  if (!fs.existsSync(file)) {
    console.log(`  FAIL  文件不存在`);
    process.exit(1);
  }
  const raw = fs.readFileSync(file, 'utf8');
  const lines = raw.split(/\r?\n/).filter((l) => l.trim());
  check('日志非空', lines.length > 0, `${lines.length} 行`);

  const recs = [];
  let badLines = 0;
  for (const line of lines) {
    try { recs.push(JSON.parse(line)); } catch { badLines++; }
  }
  check('每行都是合法 JSON', badLines === 0, `解析失败 ${badLines} 行`);

  /* ---------- 2. 必备字段 ---------- */
  const required = ['ts', 'dir', 'phase', 'method', 'reportId', 'data', 'device', 'collections', 'caller', 'error'];
  const missing = [];
  for (const r of recs) {
    for (const k of required) {
      if (!(k in r)) missing.push(`${k}@seq${r.seq}`);
    }
  }
  check('所有记录字段齐全', missing.length === 0, missing.slice(0, 5).join(', ') || 'ok');

  /* ---------- 3. 通道覆盖 ---------- */
  const dirs = new Set(recs.map((r) => r.dir));
  const methods = new Set(recs.map((r) => r.method));
  for (const d of ['meta', 'open', 'out', 'out-feature', 'in-feature', 'in', 'hid', 'event']) {
    check(`覆盖 dir=${d}`, dirs.has(d), `实际 dirs: ${[...dirs].sort().join(',')}`);
  }
  check('覆盖 method=sendReport', methods.has('sendReport'));
  check('覆盖 method=sendFeatureReport', methods.has('sendFeatureReport'));
  check('覆盖 method=receiveFeatureReport', methods.has('receiveFeatureReport'));
  check('覆盖 method=inputreport', methods.has('inputreport'));
  check('覆盖 method=requestDevice', methods.has('requestDevice'));
  check('覆盖 method=connect / disconnect 事件', methods.has('connect') && methods.has('disconnect'));

  /* ---------- 4. sendReport 内容 ---------- */
  const outCall = recs.find((r) => r.dir === 'out' && r.method === 'sendReport' && r.phase === 'call');
  check('有 sendReport 调用记录', !!outCall);
  if (outCall) {
    check('sendReport reportId == 0', outCall.reportId === 0, String(outCall.reportId));
    const expect = [0x55, 0x10, 0x00, 0x01, 0xa0, 0x0b, 0x00, 0x00];
    check('sendReport 字节序列正确',
      !!outCall.data && Array.isArray(outCall.data.array) && outCall.data.array.join(',') === expect.join(','),
      outCall.data ? outCall.data.array.join(' ') : '(无 data)');
    check('sendReport data.hex 存在', !!(outCall.data && typeof outCall.data.hex === 'string' && outCall.data.hex.length > 0),
      outCall.data ? outCall.data.hex : '');
    check('sendReport 记录了 device 的 VID/PID',
      !!outCall.device && outCall.device.vendorId === 0x0C45 && outCall.device.productId === 0x8047,
      outCall.device ? `0x${outCall.device.vendorId.toString(16)}:0x${outCall.device.productId.toString(16)}` : '');
    check('sendReport 记录了 collections（usagePage）',
      Array.isArray(outCall.collections) && outCall.collections.length > 0 &&
      outCall.collections[0].usagePage === 0xFF67,
      outCall.collections ? `usagePage=0x${Number(outCall.collections[0].usagePage).toString(16)}` : '');
    check('sendReport 的 caller 能定位到测试页',
      typeof outCall.caller === 'string' && outCall.caller.indexOf('fakehid') !== -1,
      (outCall.caller || '').split('\n')[0]);
  }

  /* ---------- 5. 设备名剥离 ---------- */
  const anyDevice = recs.map((r) => r.device).find((d) => d && d.productId === 0x8047);
  check('设备记录里 productName 已剥离 "KEYBOARD " 前缀',
    !!anyDevice && anyDevice.productName === 'AJAZZ KEYBOARD',
    anyDevice ? JSON.stringify(anyDevice.productName) : '(无设备)');

  /* ---------- 6. inputreport 字节 ---------- */
  const inRec = recs.find((r) => r.dir === 'in' && r.method === 'inputreport');
  check('有 inputreport 记录', !!inRec);
  if (inRec) {
    check('inputreport reportId == 1', inRec.reportId === 1, String(inRec.reportId));
    check('inputreport 字节序列正确',
      !!inRec.data && inRec.data.array.join(',') === [0x55, 0x01, 0x04, 0xca, 0xfe, 0xba, 0xbe].join(','),
      inRec.data ? inRec.data.array.join(' ') : '(无 data)');
  }

  /* ---------- 7. in-feature 返回数据 ---------- */
  const featOk = recs.find((r) => r.dir === 'in-feature' && r.method === 'receiveFeatureReport' && r.phase === 'ok');
  check('有 receiveFeatureReport 的结果记录', !!featOk);
  if (featOk) {
    check('receiveFeatureReport 返回字节正确',
      !!featOk.data && featOk.data.array.join(',') === [0x55, 0x05, 0x04, 0xde, 0xad, 0xbe, 0xef].join(','),
      featOk.data ? featOk.data.array.map((b) => b.toString(16).padStart(2, '0')).join(' ') : '(无 data)');
  }

  /* ---------- 8. requestDevice filters ---------- */
  const rd = recs.find((r) => r.dir === 'hid' && r.method === 'requestDevice' && r.phase === 'call');
  check('requestDevice 的 filters 被记录',
    !!rd && !!rd.filters && Array.isArray(rd.filters.filters) &&
    rd.filters.filters[0] && rd.filters.filters[0].vendorId === 0x0C45, rd ? JSON.stringify(rd.filters) : '');

  /* ---------- 9. 无错误 ---------- */
  const errors = recs.filter((r) => r.error);
  check('没有任何 error 记录', errors.length === 0,
    errors.slice(0, 3).map((e) => `${e.method}: ${e.error}`).join(' | ') || 'ok');

  /* ---------- 10. 钩子自检 ---------- */
  const installed = recs.find((r) => r.method === 'hook-installed');
  check('hook 安装记录存在', !!installed,
    installed && installed.extra ? `webhid=${installed.extra.webhid} secure=${installed.extra.secure}` : '');

  console.log('');
  console.log(`结果: ${passes} 通过, ${failures} 失败`);
  process.exit(failures === 0 ? 0 : 1);
}

main();
