/* pages/device.js — 设备信息：固件/电量/能力矩阵 + 游戏模式 56B + 原始命令控制台
   GET /api/device/info → {info, gameMode, status}（字段多为 hex 字符串，见 spec-protocol.md）
   POST /api/device/raw → {data:[..], timeout, expect} → {cmd,response:"hex",length} 或 {response:"hex"|null} */
import { icon } from '../icons.js';
import { h, hex2, fmtDateTime, fmtBytes } from '../util.js';
import { badge, kvList, sectionTitle } from '../components/widgets.js';
import { confirmDialog } from '../components/dialog.js';

const GAME_MODE_FIELDS = [
  ['sleepTime', '空闲休眠（分钟）'],
  ['displayTime', '显示时间'],
  ['debounceTime', '按键延迟（ms）'],
  ['reportRate', '回报率'],
  ['gameMode', '游戏模式'],
  ['tftDisplayTime', '12/24 小时制（无可见效果）'],
  ['keyDelay', '按键延迟档位'],
  ['powerMode', '电源模式'],
];

function toHexString(bytes) {
  return bytes.map((b) => (Number(b) & 0xff).toString(16).toUpperCase().padStart(2, '0')).join(' ');
}
function parseHex(text) {
  const clean = String(text).replace(/0x/gi, '').replace(/[^0-9a-fA-F]/g, '');
  if (clean.length % 2 !== 0) throw new Error('十六进制字符个数必须是偶数');
  if (!clean.length) throw new Error('请输入十六进制字节');
  const out = [];
  for (let i = 0; i < clean.length; i += 2) out.push(parseInt(clean.slice(i, i + 2), 16));
  return out;
}
function hexdump(bytes, perLine = 16) {
  if (!bytes || !bytes.length) return '（无数据）';
  const lines = [];
  for (let i = 0; i < bytes.length; i += perLine) {
    const chunk = bytes.slice(i, i + perLine);
    lines.push(`${i.toString(16).toUpperCase().padStart(4, '0')}  ${toHexString(chunk).padEnd(perLine * 3 - 1)}  ${chunk.map((b) => (b >= 32 && b < 127 ? String.fromCharCode(b) : '.')).join('')}`);
  }
  return lines.join('\n');
}

export default {
  id: 'device',
  async mount(root, ctx) {
    const { api } = ctx;

    let info = {};
    let gameMode = null;
    let status = ctx.status;
    try {
      const resp = await api.get('/api/device/info');
      info = resp?.info || resp || {};
      gameMode = resp?.gameMode || null;
      if (resp?.status) status = resp.status;
    } catch (e) {
      console.warn('[device] 读取设备信息失败', e);
      ctx.toastError(`读取设备信息失败：${e.message || e}`);
    }
    if (!gameMode) {
      try { gameMode = await api.get('/api/device/game-mode'); } catch { /* ignore */ }
    }

    const caps = status?.caps || {};
    const device = status?.device || {};
    const battery = status?.battery || info.battery || {};
    const firmware = status?.device?.firmware || info.firmware || info.version || '—';

    function infoValue(keys, fallback = '—') {
      for (const k of keys) {
        const v = k.split('.').reduce((o, p) => (o && o[p] !== undefined ? o[p] : undefined), { info, ...info, status });
        if (v !== undefined && v !== null && v !== '') return v;
      }
      return fallback;
    }

    /* ---------------- 概览 ---------------- */
    const heroCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '设备概览'),
          h('div', { class: 'card-desc' }, 'VID 0x0C45 / PID 0x8047 · AJAZZ MK87 · 87 键 TKL')),
        h('div', { class: 'spacer' }),
        badge(status?.transport === '2.4g' ? '2.4G 无线' : status?.transport === 'usb' ? 'USB 有线' : '未连接', status?.connected ? 'ok' : 'danger'),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'stat-grid', style: { marginBottom: '16px' } },
          h('div', { class: 'stat accent' }, h('div', { class: 'stat-label' }, '固件版本'), h('div', { class: 'stat-value' }, firmware)),
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, '电量'), h('div', { class: 'stat-value' }, `${battery.percent ?? '—'}`, h('small', {}, '%')), h('div', { class: 'tiny muted' }, battery.charging ? '充电中' : '电池供电')),
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, '按键数'), h('div', { class: 'stat-value' }, String(caps.keyCount ?? 87), h('small', {}, '键'))),
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, '屏幕最大帧'), h('div', { class: 'stat-value' }, String(caps.tftMaxFrames ?? 140), h('small', {}, '帧'))),
        ),
        kvList([
          ['产品名', status?.device?.product || info.product || 'AJAZZ KEYBOARD'],
          ['制造商', status?.device?.manufacturer || info.manufacturer || 'SONiX'],
          ['序列号', status?.device?.serial || info.serial || '—'],
          ['传输方式', status?.transport === '2.4g' ? '2.4G 无线（0xFF60）' : status?.transport === 'usb' ? 'USB 有线（0xFF68 / TFT 0xFF67）' : '未连接'],
          ['frameVersion', String(info.frameVersion ?? 0)],
          ['协议 / 接口', `${info.protocol || '0x8047'} · ${info.interface || '0xFF68 (MI_02)'}`],
        ]),
      ),
    );

    /* ---------------- 能力矩阵 ---------------- */
    const capsRows = [
      ['改键（87 键 / 主层+FN）', true, 'SET_KEY 0x22 / SET_FN_KEY 0x26'],
      ['19 种灯效 + 逐键自定义灯', true, 'mode 20/21/128 共用同一张 512B 灯表'],
      ['灯效 GIF 动画', false, 'ledMaxFrames=0，MK87 不支持'],
      ['TFT 自定义动画（≤140 帧）', !!caps.tft, '240×135 RGB565 小端，0x50 上传'],
      ['TFT 静态壁纸', false, '0x4D 可写但 MK87 无壁纸页，不可见'],
      ['屏幕内置页切换', false, '0x51 设备回 ACK 但不切页'],
      ['音乐律动（逐键帧流）', !!caps.music, '仅 USB；2.4G 官方不支持'],
      ['宏（100 槽 / 3072B）', true, '两次 SET_MACRO：400B 目录 + 数据区'],
      ['2.4G 无线配置', !!caps.wireless, '0xFF60，配置与 USB 共享'],
      ['板载多 Profile', false, 'maxProfile=0'],
      ['磁轴高级键（DKS/RT/…）', false, 'MK87 配置无 advancedKeysConfig'],
      ['屏幕系统信息 / 天气', false, 'MK87 无系统信息页'],
    ];
    const capsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '能力矩阵'),
          h('div', { class: 'card-desc' }, '来自真机逆向结论与当前连接能力位')),
      ),
      h('div', { class: 'card-body' },
        h('table', { class: 'caps-table' },
          h('tbody', {}, ...capsRows.map(([name, ok, note]) => h('tr', {},
            h('td', {}, h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
              badge(ok ? '支持' : '不支持', ok ? 'ok' : 'danger'),
              h('span', {}, name),
            )),
            h('td', { class: 'tiny muted', style: { textAlign: 'right' } }, note),
          ))),
        ),
      ),
    );

    /* ---------------- 游戏模式 56B ---------------- */
    const gameRaw = (() => {
      const raw = gameMode?.raw;
      if (Array.isArray(raw)) return raw.map((x) => (typeof x === 'string' ? parseInt(x, 16) : Number(x) & 0xff));
      if (typeof raw === 'string') return parseHex(raw);
      return [];
    })();
    const gameFields = gameMode?.fields
      || (gameMode && typeof gameMode === 'object' && gameMode.gameMode !== undefined
        ? Object.fromEntries(Object.entries(gameMode).filter(([k]) => k !== 'raw'))
        : {});
    const gameCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '游戏模式（56B）'),
          h('div', { class: 'card-desc' }, 'GET_GAME_MODE 0x11 / SET_GAME_MODE 0x21 · 多数字段 0xFF 表示不支持')),
        h('div', { class: 'spacer' }),
        badge(`${gameRaw.length || 56} B`, ''),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'grid grid-2' },
          h('div', {},
            h('div', { class: 'kv' }, ...GAME_MODE_FIELDS.map(([key, label]) => h('div', { class: 'kv-row' },
              h('div', { class: 'k' }, label),
              h('div', { class: 'v mono' }, gameFields[key] !== undefined ? String(gameFields[key]) : '—'),
            ))),
          ),
          h('div', {},
            h('div', { class: 'tiny muted', style: { marginBottom: '6px' } }, '原始 56 字节（hex）'),
            h('div', { class: 'hexdump', style: { maxHeight: '260px' } }, hexdump(gameRaw)),
          ),
        ),
      ),
    );

    /* ---------------- 快捷操作 ---------------- */
    const timeSyncBtn = h('button', { class: 'btn', html: `${icon('clock', { size: 15 })}<span>同步主机时间到屏幕</span>`, onclick: timeSync });
    const scanBtn = h('button', { class: 'btn', html: `${icon('refresh', { size: 15 })}<span>重新扫描设备</span>`, onclick: scan });
    const factoryBtn = h('button', { class: 'btn danger', html: `${icon('alert-triangle', { size: 15 })}<span>恢复出厂设置</span>`, onclick: factoryReset });
    const actionCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '设备操作')),
      h('div', { class: 'card-body' },
        h('div', { class: 'row' }, timeSyncBtn, scanBtn, h('div', { class: 'spacer' }), factoryBtn),
        h('div', { class: 'tiny muted mt-12' }, '恢复出厂会清空灯光、改键、宏与无线设置且不可撤销；恢复前请先在「备份与恢复」页导出备份。'),
      ),
    );

    /* ---------------- 原始命令控制台 ---------------- */
    const consoleLog = h('div', { class: 'log-body' });
    const hexInput = h('textarea', {
      class: 'textarea mono hex-input', rows: '3', spellcheck: 'false',
      placeholder: '示例：AA 13 10 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
    });
    const timeoutInput = h('input', { class: 'input sm', type: 'number', step: '0.1', min: '0.05', max: '10', value: '0.5', style: { width: '90px' } });
    const expectCheck = h('input', { type: 'checkbox', checked: true });
    const sendBtn = h('button', { class: 'btn primary', html: `${icon('terminal', { size: 15 })}<span>发送</span>` });
    const clearLogBtn = h('button', { class: 'btn sm ghost', onclick: () => { consoleLog.innerHTML = ''; } }, '清空日志');

    function appendConsole(lines) {
      for (const line of lines) {
        consoleLog.append(h('div', { class: `log-line${line.cls ? ' ' + line.cls : ''}` },
          h('span', { class: 't' }, fmtDateTime(Date.now()).slice(11)),
          h('span', { class: 'tag' }, line.tag || ''),
          h('span', { style: { wordBreak: 'break-all' } }, line.text),
        ));
      }
      consoleLog.scrollTop = consoleLog.scrollHeight;
    }

    const QUICK = [
      {
        name: '读灯效 0x13',
        build: () => [0xaa, 0x13, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, ...new Array(16).fill(0)],
      },
      {
        name: '读设备信息 0x10',
        build: () => [0xaa, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
      },
      {
        name: '读游戏模式 0x11',
        build: () => [0xaa, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
      },
      {
        name: '关灯 mode=0',
        build: () => [0xaa, 0x23, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00,
          0, 255, 255, 255, 255, 0, 0, 0, 1, 5, 3, 0, 0, 0, 0xaa, 0x55],
        danger: true,
      },
    ];
    const quickRow = h('div', { class: 'quick-cmd' },
      ...QUICK.map((q) => h('button', {
        type: 'button',
        title: q.danger ? '会立即改变设备状态' : '只读命令',
        onclick: () => { hexInput.value = toHexString(q.build()); ctx.toast(`已填入「${q.name}」，确认后点发送`); },
      }, q.name)),
    );

    async function sendRaw() {
      let data;
      try {
        data = parseHex(hexInput.value);
      } catch (e) {
        ctx.toastError(e.message);
        return;
      }
      if (data.length > 4104) { ctx.toastError('单帧最多 4104 字节'); return; }
      sendBtn.disabled = true;
      appendConsole([{ tag: '→', text: `${data.length} B  ${toHexString(data).slice(0, 96)}${data.length > 32 ? ' …' : ''}` }]);
      try {
        const resp = await api.post('/api/device/raw', {
          data,
          timeout: Number(timeoutInput.value) || 0.5,
          expect: expectCheck.checked,
        });
        if (resp?.response === null || resp?.response === undefined) {
          appendConsole([{ tag: '←', text: '无响应（timeout）', cls: 'dim' }]);
        } else {
          const hex = typeof resp.response === 'string' ? resp.response : toHexString(resp.response || []);
          appendConsole([
            { tag: '←', text: `response ${resp.length ?? (hex.split(' ').length)} B  ${hex}` },
            { tag: ' ', text: hexdump(hex.trim().split(/\s+/).filter(Boolean).map((x) => parseInt(x, 16))), cls: 'dim' },
          ]);
          if (resp.cmd !== undefined) appendConsole([{ tag: 'i', text: `cmd=0x${Number(resp.cmd).toString(16).toUpperCase()}`, cls: 'dim' }]);
        }
      } catch (e) {
        appendConsole([{ tag: '!', text: `发送失败：${e.message || e}`, cls: 'err' }]);
        ctx.toastError(`发送失败：${e.message || e}`);
      } finally {
        sendBtn.disabled = false;
      }
    }
    sendBtn.addEventListener('click', sendRaw);
    hexInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendRaw(); });

    const consoleCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '原始命令控制台'),
          h('div', { class: 'card-desc' }, '直接与设备通信（高级调试）。写操作会立即改变设备状态，请谨慎。')),
        h('div', { class: 'spacer' }),
        badge('POST /api/device/raw', 'accent'),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'console-wrap' },
          h('div', { class: 'field' },
            h('div', { class: 'field-label' }, '十六进制帧（自动忽略空格 / 0x 前缀）'),
            hexInput,
          ),
          quickRow,
          h('div', { class: 'row' },
            h('span', { class: 'tiny muted' }, 'timeout'),
            timeoutInput,
            h('label', { class: 'check tiny' }, expectCheck, h('span', {}, '等待响应')),
            h('div', { class: 'spacer' }),
            clearLogBtn, sendBtn,
          ),
          h('div', { class: 'log-panel console-log' },
            h('div', { class: 'log-head' }, 'RAW CONSOLE'),
            consoleLog,
          ),
        ),
      ),
    );

    /* ---------------- 操作 ---------------- */
    async function timeSync() {
      timeSyncBtn.disabled = true;
      try {
        const resp = await api.post('/api/device/time-sync');
        const sent = resp?.sent ? toHexString(resp.sent) : '';
        ctx.toastSuccess(`已写入屏幕时间${sent ? `（${sent}）` : ''}`);
      } catch (e) {
        ctx.toastError(`时间同步失败：${e.message || e}`);
      } finally {
        timeSyncBtn.disabled = false;
      }
    }
    async function scan() {
      scanBtn.disabled = true;
      try {
        const st = await api.post('/api/device/scan');
        ctx.toastSuccess('设备已重新扫描');
        await ctx.refreshStatus?.();
      } catch (e) {
        ctx.toastError(`扫描失败：${e.message || e}`);
      } finally {
        scanBtn.disabled = false;
      }
    }
    async function factoryReset() {
      const ok = await confirmDialog({
        title: '恢复出厂设置',
        message: '将向设备发送 0x0F 恢复出厂：灯光、改键、FN、宏、无线设置都会被清空，且无法撤销。',
        extra: '建议先在「备份与恢复」页导出当前配置。',
        confirmText: '确认恢复出厂',
      });
      if (!ok) return;
      const really = await confirmDialog({
        title: '二次确认',
        message: '真的要恢复出厂设置吗？设备会立即重启相关配置。',
        confirmText: '我确定',
      });
      if (!really) return;
      try {
        await api.post('/api/device/factory-reset', { confirm: true });
        ctx.toastSuccess('已发送恢复出厂命令');
        await ctx.refreshStatus?.();
      } catch (e) {
        ctx.toastError(`恢复出厂失败：${e.message || e}`);
      }
    }

    /* ---------------- 布局 ---------------- */
    root.append(heroCard);
    root.append(h('div', { class: 'grid grid-main mt-16' },
      h('div', { class: 'grid-stack' }, gameCard, consoleCard),
      h('div', { class: 'grid-stack' }, capsCard, actionCard),
    ));
  },
};
