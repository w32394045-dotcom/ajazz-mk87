/* pages/backup.js — 备份与恢复：导出/导入全量 JSON，危险操作二次确认
   GET /api/backup → {version, app, createdAt, device, keymap, macro, lighting, custom, wireless, settings}
   POST /api/backup/restore {backup, confirm:true} */
import { icon } from '../icons.js';
import { h, fmtBytes, fmtDateTime, downloadText, readFileAsText, copyText, hexToRgb } from '../util.js';

/** 后端备份把矩阵存成 1024 个 hex 字符（512B）；统计非 0 槽数 */
function countMatrixSlots(hex) {
  if (typeof hex !== 'string') return 0;
  const clean = hex.replace(/[^0-9a-fA-F]/g, '');
  const bytes = [];
  for (let i = 0; i + 1 < clean.length; i += 2) bytes.push(parseInt(clean.slice(i, i + 2), 16));
  let n = 0;
  for (let i = 0; i + 3 < bytes.length; i += 4) {
    if (bytes[i] || bytes[i + 1] || bytes[i + 2] || bytes[i + 3]) n += 1;
  }
  return n;
}
function countCustomLed(hex) {
  if (typeof hex !== 'string') return 0;
  const clean = hex.replace(/[^0-9a-fA-F]/g, '');
  const bytes = [];
  for (let i = 0; i + 1 < clean.length; i += 2) bytes.push(parseInt(clean.slice(i, i + 2), 16));
  let n = 0;
  for (let i = 0; i + 3 < bytes.length; i += 4) {
    if (bytes[i + 1] + bytes[i + 2] + bytes[i + 3] > 12) n += 1;
  }
  return n;
}
function parseBackupDate(str) {
  if (!str) return null;
  const t = new Date(String(str).replace(/([+-]\d{2})(\d{2})$/, '$1:$2')).getTime();
  return Number.isFinite(t) ? t : null;
}
import { badge, kvList } from '../components/widgets.js';
import { confirmDialog, openDialog } from '../components/dialog.js';

function summarize(backup) {
  if (!backup || typeof backup !== 'object') return null;
  /* ---- 真实后端格式：format='mk87-backup'，矩阵是 hex ---- */
  if (backup.format === 'mk87-backup' || (backup.keyMatrix && !backup.keymap)) {
    const slots = Array.isArray(backup.macros) ? backup.macros : (backup.macros?.slots || []);
    const usedMacros = slots.filter((m) => (m.actions || []).length);
    const actions = usedMacros.reduce((sum, m) => sum + m.actions.length, 0);
    const usedBytes = usedMacros.reduce((sum, m) => sum + 4 + m.actions.length * 4, 0);
    const modeHex = String(backup.ledEffectRaw || '').slice(0, 2);
    return {
      app: 'MK87 Studio',
      version: backup.version ?? '—',
      createdAt: backup.createdAt || null,
    transport: backup.transport,
      firmware: backup.device?.firmware ?? '—',
      normal: countMatrixSlots(backup.keyMatrix),
      fn: countMatrixSlots(backup.fnMatrix),
      macroCount: usedMacros.length,
      macroActions: actions,
      macroBytes: usedBytes,
      customCount: countCustomLed(backup.customLedData),
      lightingMode: modeHex ? parseInt(modeHex, 16) : undefined,
      sleepTime: backup.wireless?.sleepTime,
      theme: backup.settings?.theme,
      language: backup.settings?.language,
      transport: backup.transport,
    };
  }
  const normal = Object.keys(backup.keymap?.normal || {}).length;
  const fn = Object.keys(backup.keymap?.fn || {}).length;
  const slots = backup.macro?.slots || [];
  const usedMacros = slots.filter((m) => (m.actions || []).length);
  const actions = usedMacros.reduce((sum, m) => sum + m.actions.length, 0);
  const usedBytes = usedMacros.reduce((sum, m) => sum + 4 + m.actions.length * 4, 0);
  const customCount = Object.keys(backup.custom?.colors || {}).filter((k) => {
    const c = backup.custom.colors[k];
    return c && (c[0] + c[1] + c[2]) > 12;
  }).length;
  return {
    app: backup.app || 'MK87 Studio',
    version: backup.version ?? '—',
    createdAt: backup.createdAt || null,
    firmware: backup.device?.firmware || '—',
    normal, fn,
    macroCount: usedMacros.length,
    macroActions: actions,
    macroBytes: usedBytes,
    customCount,
    lightingMode: backup.lighting?.mode,
    sleepTime: backup.wireless?.sleepTime,
    theme: backup.settings?.theme,
    language: backup.settings?.language,
  };
}

export default {
  id: 'backup',
  async mount(root, ctx) {
    const { api } = ctx;
    let backup = null;
    let summary = null;
    let loadError = null;

    async function load() {
      try {
        backup = await api.get('/api/backup');
        summary = summarize(backup);
        loadError = null;
      } catch (e) {
        loadError = e;
        summary = null;
      }
      renderSummary();
    }

    const summaryHost = h('div', { class: 'backup-summary' });
    const fileInfo = h('div', { class: 'tiny muted' }, '尚未选择备份文件');
    const importPreview = h('div', { class: 'stack' });
    const importBtn = h('button', { class: 'btn primary', html: `${icon('upload', { size: 15 })}<span>选择备份文件并恢复</span>`, disabled: true });
    const fileInput = h('input', { type: 'file', accept: '.json,application/json', style: { display: 'none' } });
    let pendingBackup = null;

    function renderSummary() {
      summaryHost.innerHTML = '';
      if (loadError) {
        summaryHost.append(h('div', { class: 'empty' },
          h('div', { html: icon('alert-triangle', { size: 26 }) }),
          h('div', {}, `读取备份失败：${loadError.message || loadError}`),
          h('button', { class: 'btn sm mt-12', onclick: load }, '重试'),
        ));
        return;
      }
      if (!summary) {
        summaryHost.append(h('div', { class: 'empty' }, h('div', {}, '暂无备份数据')));
        return;
      }
      summaryHost.append(
        h('div', { class: 'backup-file' },
          h('div', { class: 'ic', html: icon('file-json', { size: 18 }) }),
          h('div', { style: { minWidth: 0 } },
            h('div', { style: { fontWeight: '600', fontSize: '13px' } }, `MK87 全量配置备份 v${summary.version}`),
            h('div', { class: 'tiny muted' }, summary.createdAt ? `生成时间 ${fmtDateTime(parseBackupDate(summary.createdAt) || new Date(summary.createdAt).getTime())}` : '生成时间未知'),
          ),
          h('div', { class: 'spacer' }),
          badge('完整备份', 'ok'),
        ),
        h('div', { class: 'stat-grid' },
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, '主层改键'), h('div', { class: 'stat-value' }, String(summary.normal), h('small', {}, '槽'))),
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, 'FN 层改键'), h('div', { class: 'stat-value' }, String(summary.fn), h('small', {}, '槽'))),
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, '宏'), h('div', { class: 'stat-value' }, String(summary.macroCount), h('small', {}, `槽 / ${summary.macroBytes} B`))),
          h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, '逐键灯'), h('div', { class: 'stat-value' }, String(summary.customCount), h('small', {}, '键'))),
        ),
        kvList([
          ['设备固件', summary.firmware],
          ['灯效', `mode ${summary.lightingMode ?? '—'}${summary.lightingMode === 128 ? '（自定义）' : ''}`],
          ['无线休眠', summary.sleepTime === undefined ? '—' : `${summary.sleepTime} 分钟`],
          ['界面设置', `${summary.theme || 'auto'} · ${summary.language || 'zh'}`],
        ]),
      );
    }

    function downloadBackup() {
      if (!backup) { ctx.toastWarn('还没有可导出的备份'); return; }
      const name = `mk87-backup-${new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)}.json`;
      downloadText(name, JSON.stringify(backup, null, 2), 'application/json');
      ctx.toastSuccess(`已导出 ${name}`);
    }

    async function copyBackup() {
      if (!backup) return;
      const ok = await copyText(JSON.stringify(backup, null, 2));
      ctx.toast(ok ? '备份 JSON 已复制到剪贴板' : '复制失败', { type: ok ? 'success' : 'error' });
    }

    async function onFileChosen(file) {
      if (!file) return;
      try {
        const text = await readFileAsText(file);
        const parsed = JSON.parse(text);
        const isReal = parsed && parsed.format === 'mk87-backup' && (parsed.keyMatrix || parsed.fnMatrix);
        const isMock = parsed && (parsed.keymap || parsed.macro || parsed.lighting);
        if (!parsed || typeof parsed !== 'object' || (!isReal && !isMock)) {
          throw new Error('文件不是 MK87 Studio 的备份（缺少 keyMatrix/keymap 等字段）');
        }
        pendingBackup = parsed;
        const s = summarize(parsed);
        importPreview.innerHTML = '';
        importPreview.append(
          h('div', { class: 'backup-file' },
            h('div', { class: 'ic', html: icon('file', { size: 18 }) }),
            h('div', { style: { minWidth: 0 } },
              h('div', { style: { fontWeight: '600', fontSize: '13px' } }, file.name),
              h('div', { class: 'tiny muted' }, `${fmtBytes(file.size)} · 备份版本 v${s.version} · ${s.createdAt ? fmtDateTime(parseBackupDate(s.createdAt) || new Date(s.createdAt).getTime()) : '时间未知'}`),
            ),
          ),
          h('div', { class: 'tiny muted', style: { lineHeight: '1.75' } },
            `将恢复：主层 ${s.normal} 槽 · FN 层 ${s.fn} 槽 · ${s.macroCount} 个宏（${s.macroBytes} B）· 逐键灯 ${s.customCount} 键 · 灯效 mode ${s.lightingMode ?? '—'}。`,
          ),
          h('div', { class: 'banner danger', style: { margin: '0' } },
            h('div', { class: 'banner-icon', html: icon('alert-triangle', { size: 17 }) }),
            h('div', {}, h('strong', {}, '恢复会覆盖设备当前配置'),
              h('div', { class: 'tiny', style: { marginTop: '2px' } }, '主层/FN 键位、宏表、逐键灯表、灯效参数、无线休眠都会按备份写入，当前配置不可撤销。')),
          ),
          h('div', { class: 'row' },
            h('button', {
              class: 'btn', onclick: () => { pendingBackup = null; importPreview.innerHTML = ''; importBtn.disabled = true; fileInfo.textContent = '尚未选择备份文件'; fileInput.value = ''; },
            }, '重新选择'),
            h('button', { class: 'btn danger', onclick: doRestore }, h('span', { html: icon('upload', { size: 15 }) }), '确认恢复到此设备'),
          ),
        );
        fileInfo.textContent = `已选择：${file.name}`;
        importBtn.disabled = false;
        ctx.toast('备份文件已解析，请确认下方内容后恢复');
      } catch (e) {
        pendingBackup = null;
        importPreview.innerHTML = '';
        ctx.toastError(`无法解析备份：${e.message || e}`);
      }
    }

    async function doRestore() {
      if (!pendingBackup) return;
      const s = summarize(pendingBackup);
      const ok = await confirmDialog({
        title: '恢复备份',
        message: `确认把备份（主层 ${s.normal} 槽 / FN ${s.fn} 槽 / ${s.macroCount} 个宏 / ${s.customCount} 键逐键灯）写入设备？当前配置会被覆盖。`,
        extra: '恢复过程中请勿拔线或关闭页面。',
        confirmText: '确认恢复',
      });
      if (!ok) return;
      try {
        await api.post('/api/backup/restore', { backup: pendingBackup, confirm: true });
        ctx.toastSuccess('备份已恢复到设备');
        await ctx.refreshStatus?.();
        await load();
      } catch (e) {
        ctx.toastError(`恢复失败：${e.message || e}`);
      }
    }
    importBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => { const f = fileInput.files?.[0]; if (f) onFileChosen(f); fileInput.value = ''; });

    /* 拖放导入 */
    const dropzone = h('div', { class: 'dropzone', role: 'button', tabindex: '0' },
      h('div', { html: icon('file-json', { size: 28 }) }),
      h('div', { class: 'dz-title' }, '拖入备份 JSON 或点击选择文件'),
      h('div', { class: 'tiny' }, '支持本工具导出的全量备份；解析后会先展示摘要并要求二次确认'),
      fileInput,
    );
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      const f = e.dataTransfer?.files?.[0];
      if (f) onFileChosen(f);
    });

    /* ---------------- 布局 ---------------- */
    const exportCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '当前配置备份'),
          h('div', { class: 'card-desc' }, '键位 / FN / 宏 / 灯效 / 逐键灯 / 无线 / 设置全量 JSON')),
        h('div', { class: 'spacer' }),
        h('button', { class: 'btn sm ghost', title: '刷新', html: icon('refresh', { size: 14 }), onclick: load }),
      ),
      h('div', { class: 'card-body' },
        summaryHost,
        h('div', { class: 'row mt-16' },
          h('button', { class: 'btn primary', html: `${icon('download', { size: 15 })}<span>导出备份 JSON</span>`, onclick: downloadBackup }),
          h('button', { class: 'btn', html: `${icon('copy', { size: 15 })}<span>复制到剪贴板</span>`, onclick: copyBackup }),
        ),
      ),
    );

    const importCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '从备份恢复'),
          h('div', { class: 'card-desc' }, '先解析并显示摘要，确认后才写入设备')),
        h('div', { class: 'spacer' }),
        badge('危险操作 · 二次确认', 'danger'),
      ),
      h('div', { class: 'card-body' },
        dropzone,
        fileInfo,
        importPreview,
      ),
    );

    const tipsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '说明')),
      h('div', { class: 'card-body' },
        h('div', { class: 'tiny muted', style: { lineHeight: '1.85' } },
          h('p', {}, '· 备份内容来自后端 /api/backup：包含整个 512B 主层与 FN 层矩阵、100 个宏槽、逐键灯表、灯效参数和无线设置。'),
          h('p', {}, '· 恢复走 POST /api/backup/restore（后端按整块读-改-写流程写入，不会丢 25 个配置外槽）。'),
          h('p', {}, '· 宏名字与「宏绑在哪个键」不在设备里：本工具的备份包含它们；换机器恢复时这些本地信息随备份一起迁移。'),
          h('p', {}, '· 如需回到完全出厂状态，请到「设备信息」页使用恢复出厂设置（比恢复旧备份更彻底）。'),
        ),
      ),
    );

    root.append(h('div', { class: 'grid grid-main' },
      h('div', { class: 'grid-stack' }, exportCard, importCard),
      h('div', { class: 'grid-stack' }, tipsCard),
    ));

    await load();
  },
};
