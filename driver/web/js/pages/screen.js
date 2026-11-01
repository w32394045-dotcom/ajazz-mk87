/* pages/screen.js — TFT 屏幕：后端压缩管线（/api/tft/convert）预览 + /api/tft/upload_file 上传
   流程：选图片/GIF → base64 → POST /api/tft/convert（后端解码/裁剪/抽帧/压缩/抖动）→ 预览帧+统计
        → POST /api/tft/upload_file（同 data+options，异步任务，WS progress/job 推送）
   规格：spec-tft-wireless.md §1/§2/§6.1；后端 frames 为 PNG dataURL（240×135）。
   前端不再自己算 RGB565（避免两套逻辑），本地 canvas 仅用于首帧快速缩略图。 */
import { icon } from '../icons.js';
import { h, clamp, fmtBytes, debounce, downloadText } from '../util.js';
import { createSlider, createSegmented, createProgress, badge, kvList } from '../components/widgets.js';

const TFT_W = 240;
const TFT_H = 135;
const FRAME_BYTES = TFT_W * TFT_H * 2;

const FIT_LABELS = { cover: '裁剪填满', contain: '完整黑边', stretch: '拉伸' };
const TEMPORAL_LABELS = { uniform: '等时抽帧', adaptive: '智能抽帧' };
const RESAMPLE_LABELS = { lanczos: 'Lanczos', bicubic: 'Bicubic', bilinear: 'Bilinear', area: 'Area' };

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(String(fr.result));
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(file);
  });
}

function fmtSeconds(sec) {
  const s = Number(sec) || 0;
  if (s <= 0) return '—';
  if (s < 60) return `约 ${s.toFixed(1)} 秒`;
  const m = Math.floor(s / 60);
  const rest = Math.round(s % 60);
  return `约 ${m} 分 ${rest} 秒`;
}

export default {
  id: 'screen',
  async mount(root, ctx) {
    const { api } = ctx;

    /* ---------------- 设备参数 ---------------- */
    let tftInfo = {
      width: TFT_W, height: TFT_H, maxFrames: 140, pixelFormat: 'rgb565', byteOrder: 0,
      fitModes: ['cover', 'contain', 'stretch'],
      temporalModes: ['uniform', 'adaptive'],
      resampleModes: ['lanczos', 'bicubic', 'bilinear', 'area'],
      secondsPerPacket: 0.146,
      supported: true,
    };
    try {
      const resp = await api.get('/api/tft');
      if (resp) tftInfo = { ...tftInfo, ...resp };
    } catch (e) { console.warn('[screen] /api/tft 失败', e); }
    const maxFrames = Number(tftInfo.maxFrames) || 140;
    const secPerPacket = Number(tftInfo.secondsPerPacket) || 0.146;
    const fitModes = (tftInfo.fitModes || ['cover', 'contain', 'stretch']).filter((f) => FIT_LABELS[f]);
    const temporalModes = (tftInfo.temporalModes || ['uniform', 'adaptive']).filter((m) => TEMPORAL_LABELS[m]);
    const resampleModes = (tftInfo.resampleModes || ['lanczos', 'bicubic', 'bilinear', 'area']).filter((m) => RESAMPLE_LABELS[m]);
    let tftSupported = (ctx.status?.caps ? ctx.status.caps.tft !== false : true) && tftInfo.supported !== false;

    /* ---------------- 状态 ---------------- */
    const state = {
      file: null,
      result: null,
      converting: false,
      uploading: false,
      convertToken: 0,
      playing: false,
      playIndex: 0,
      jobTotal: 0,
      uploadStartedAt: 0,
      autoFrames: false,
      frameCount: Math.min(60, maxFrames),
      timingMode: 'fps',
      fps: 10,
      durationSec: 6,
      fit: fitModes.includes('cover') ? 'cover' : fitModes[0],
      temporal: temporalModes.includes('uniform') ? 'uniform' : temporalModes[0],
      dither: false,
      dedupe: false,
      resample: 'lanczos',
      trimStart: 1,
      trimEnd: null,
      rawSourceFrames: 0,
      warnings: [],
    };
    const offs = [];
    let playTimer = null;
    let pollTimer = null;

    /* ---------------- DOM：素材 ---------------- */
    const fileInput = h('input', { type: 'file', accept: 'image/*,.gif,.webp,.apng', style: { display: 'none' } });
    const dropzone = h('div', { class: 'dropzone', role: 'button', tabindex: '0' },
      h('div', { html: icon('image', { size: 30 }) }),
      h('div', { class: 'dz-title' }, '拖入图片 / GIF，或点击选择文件'),
      h('div', { class: 'tiny' }, '支持 PNG / JPG / WebP / GIF / 动态 WebP / APNG · 后端统一解码压缩 · 完全本地'),
      fileInput,
    );
    const fileRow = h('div', { class: 'backup-file', style: { display: 'none' } });
    const sourceStats = h('div', { class: 'tiny muted' });
    const warningsBanner = h('div', { class: 'banner', style: { display: 'none', margin: '10px 0 0' } });

    const previewCanvas = h('canvas', { width: String(TFT_W), height: String(TFT_H) });
    const previewFrame = h('div', { class: 'tft-canvas-frame' }, previewCanvas, h('div', { class: 'screen-glare' }));
    const previewWrap = h('div', { class: 'tft-preview-wrap', style: { display: 'none' } }, previewFrame);
    const previewEmpty = h('div', { class: 'empty' },
      h('div', { html: icon('monitor', { size: 28 }) }),
      h('div', {}, '还没有选择素材'),
      h('div', { class: 'tiny' }, '选择图片或 GIF 后，后端会压缩并返回 240×135 预览帧'),
    );
    const previewCtx = previewCanvas.getContext('2d');
    const playBtn = h('button', { class: 'btn sm', html: `${icon('play', { size: 13 })}<span>预览动画</span>`, disabled: true });
    const frameStrip = h('div', { class: 'frame-strip' });
    const stripMeta = h('div', { class: 'tiny muted' }, '转换后会在这里显示输出帧');
    const convertState = h('div', { class: 'tiny muted' }, '选择素材后自动转换预览');

    /* ---------------- DOM：转换设置 ---------------- */
    const autoCheck = h('input', { type: 'checkbox' });
    const frameSlider = createSlider({
      label: '帧数', min: 1, max: maxFrames, step: 1, value: state.frameCount,
      format: (v) => `${v} 帧`,
      onInput: (v) => { state.frameCount = v; refreshTimingHint(); scheduleConvert(); },
    });
    const autoRow = h('label', { class: 'check tiny' }, autoCheck, h('span', {}, `自动帧数（不指定时按源帧数 / 帧率换算，上限 ${maxFrames}）`));
    autoCheck.addEventListener('change', () => {
      state.autoFrames = autoCheck.checked;
      frameSlider.el.style.opacity = state.autoFrames ? '.45' : '1';
      frameSlider.el.style.pointerEvents = state.autoFrames ? 'none' : '';
      if (state.autoFrames && state.timingMode === 'duration') setTimingMode('fps');
      refreshTimingHint();
      scheduleConvert();
    });

    const durationInput = h('input', { class: 'input sm', type: 'number', min: '0.5', max: '60', step: '0.5', value: '6', style: { width: '84px' } });
    const fpsInput = h('input', { class: 'input sm', type: 'number', min: '1', max: '60', step: '1', value: '10', style: { width: '84px' } });
    const durationWrap = h('div', { class: 'row', style: { display: 'none' } }, h('span', { class: 'tiny muted' }, '总时长（秒）'), durationInput);
    const fpsWrap = h('div', { class: 'row' }, h('span', { class: 'tiny muted' }, '帧率（fps）'), fpsInput);
    const timingSeg = createSegmented({
      options: [{ value: 'fps', label: '按帧率' }, { value: 'duration', label: '按总时长' }],
      value: 'fps',
      small: true,
      onChange: (v) => setTimingMode(v),
    });
    const timingHint = h('div', { class: 'tiny muted' });
    function effectiveFps() {
      if (state.timingMode === 'duration') {
        const frames = state.autoFrames ? (state.result?.sourceFrames || 60) : state.frameCount;
        return clamp(frames / state.durationSec, 0.1, 60);
      }
      return clamp(state.fps, 0.1, 60);
    }
    function refreshTimingHint() {
      const fps = effectiveFps();
      const frames = state.result?.framesCount || (state.autoFrames ? null : state.frameCount);
      timingHint.textContent = `输出时长 ≈ ${frames ? (frames / fps).toFixed(1) : '—'} 秒（${fps.toFixed(1)} fps）`;
    }
    function setTimingMode(mode) {
      if (mode === 'duration' && state.autoFrames) {
        state.autoFrames = false;
        autoCheck.checked = false;
        frameSlider.el.style.opacity = '1';
        frameSlider.el.style.pointerEvents = '';
        if (!state.result?.framesCount) frameSlider.set(Math.min(60, maxFrames));
        ctx.toast('「按总时长」需要指定帧数，已自动切换为手动帧数', { timeout: 2600 });
      }
      state.timingMode = mode;
      timingSeg.set(mode);
      fpsWrap.style.display = mode === 'fps' ? '' : 'none';
      durationWrap.style.display = mode === 'duration' ? '' : 'none';
      refreshTimingHint();
      scheduleConvert();
    }
    fpsInput.addEventListener('input', () => { state.fps = clamp(parseFloat(fpsInput.value) || 10, 1, 60); refreshTimingHint(); scheduleConvert(); });
    durationInput.addEventListener('input', () => { state.durationSec = clamp(parseFloat(durationInput.value) || 6, 0.5, 60); refreshTimingHint(); scheduleConvert(); });

    const fitSeg = createSegmented({
      options: fitModes.map((f) => ({ value: f, label: FIT_LABELS[f] })),
      value: state.fit,
      onChange: (v) => { state.fit = v; scheduleConvert(); },
    });
    const temporalSeg = createSegmented({
      options: temporalModes.map((m) => ({ value: m, label: TEMPORAL_LABELS[m] })),
      value: state.temporal,
      onChange: (v) => { state.temporal = v; scheduleConvert(); },
    });
    const ditherCheck = h('input', { type: 'checkbox' });
    const dedupeCheck = h('input', { type: 'checkbox', checked: false });
    ditherCheck.addEventListener('change', () => { state.dither = ditherCheck.checked; scheduleConvert(); });
    dedupeCheck.addEventListener('change', () => { state.dedupe = dedupeCheck.checked; scheduleConvert(); });
    const resampleSelect = h('select', { class: 'select' },
      ...resampleModes.map((m) => h('option', { value: m, selected: m === state.resample }, RESAMPLE_LABELS[m])),
    );
    resampleSelect.addEventListener('change', () => { state.resample = resampleSelect.value; scheduleConvert(); });

    /* ---------------- DOM：源动画截取 ---------------- */
    const sourceInfoText = h('div', { class: 'tiny muted' }, '选择素材并完成一次转换后即可截取源动画帧区间');
    const trimStartInput = h('input', { class: 'input sm', type: 'number', min: '1', step: '1', value: '1', style: { width: '100px' } });
    const trimEndInput = h('input', { class: 'input sm', type: 'number', min: '1', step: '1', placeholder: '源末帧', style: { width: '100px' } });
    const trimAllBtn = h('button', { class: 'btn sm ghost', html: `${icon('check-circle', { size: 13 })}<span>全选</span>` });
    const trimHint = h('div', { class: 'tiny muted' }, '只压缩源动画的这段区间（含首尾帧，1 起始）');
    function clampTrimInputs() {
      const total = state.rawSourceFrames;
      let start = parseInt(trimStartInput.value, 10) || 1;
      let end = trimEndInput.value === '' ? (total || null) : (parseInt(trimEndInput.value, 10) || null);
      start = clamp(start, 1, total || 1e9);
      if (end !== null) end = clamp(end, start, total || 1e9);
      trimStartInput.value = String(start);
      trimEndInput.value = end !== null ? String(end) : '';
      state.trimStart = start;
      state.trimEnd = end;
      const frames = total ? (end !== null ? end - start + 1 : null) : null;
      trimHint.textContent = total
        ? `将截取 ${start}–${end ?? total} 帧，共 ${frames ?? '?'} 帧（源共 ${total} 帧）`
        : '只压缩源动画的这段区间（含首尾帧，1 起始）';
    }
    trimStartInput.addEventListener('change', () => { clampTrimInputs(); scheduleConvert(); });
    trimEndInput.addEventListener('change', () => { clampTrimInputs(); scheduleConvert(); });
    trimAllBtn.addEventListener('click', () => {
      trimStartInput.value = '1';
      trimEndInput.value = state.rawSourceFrames ? String(state.rawSourceFrames) : '';
      clampTrimInputs();
      scheduleConvert();
    });
    const sourceCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '源动画'),
          h('div', { class: 'card-desc' }, '截取源帧区间后再压缩（默认全选）')),
        h('div', { class: 'spacer' }),
        badge('trim', ''),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'stack' },
          sourceInfoText,
          h('div', { class: 'row', style: { gap: '10px' } },
            h('label', { class: 'field' }, h('span', { class: 'field-label' }, '起始帧'), trimStartInput),
            h('label', { class: 'field' }, h('span', { class: 'field-label' }, '结束帧'), trimEndInput),
            h('div', { class: 'spacer' }),
            trimAllBtn,
          ),
          trimHint,
        ),
      ),
    );

    const convertBtn = h('button', { class: 'btn primary', html: `${icon('refresh-cw', { size: 15 })}<span>重新转换</span>` });
    const resetOptBtn = h('button', { class: 'btn sm ghost', html: `${icon('undo', { size: 14 })}<span>恢复默认参数</span>` });

    /* ---------------- DOM：上传 ---------------- */
    const uploadProgress = createProgress({ label: '等待转换' });
    const jobInfo = h('div', { class: 'row between tiny muted' }, h('span', {}, '等待上传'), h('span', { class: 'mono' }, 'ETA —'));
    const uploadBtn = h('button', { class: 'btn primary', html: `${icon('upload', { size: 15 })}<span>压缩并上传到键盘</span>`, disabled: true });
    const cancelBtn = h('button', { class: 'btn', html: `${icon('x', { size: 15 })}<span>取消上传</span>`, disabled: true });
    const restoreBtn = h('button', { class: 'btn danger w-full', html: `${icon('refresh-cw', { size: 15 })}<span>恢复官方默认动画</span>` });
    const resultStats = h('div', { class: 'stat-grid' });

    /* ---------------- 选项组装 ---------------- */
    function buildOptions() {
      const opts = {
        fit: state.fit,
        temporal: state.temporal,
        dither: !!state.dither,
        dedupe: !!state.dedupe,
        resample: state.resample,
      };
      if (!state.autoFrames) opts.frameCount = clamp(state.frameCount, 1, maxFrames);
      opts.fps = Math.round(effectiveFps() * 100) / 100;
      if (state.trimStart && (state.trimEnd || state.rawSourceFrames)) {
        opts.trimStartFrame = clamp(state.trimStart, 1, state.rawSourceFrames || maxFrames);
        opts.trimEndFrame = clamp(state.trimEnd || state.rawSourceFrames || maxFrames, opts.trimStartFrame, state.rawSourceFrames || maxFrames);
      }
      return opts;
    }

    /* ---------------- 转换（防抖 400ms） ---------------- */
    const doConvert = debounce(async () => {
      if (!state.file) return;
      const token = ++state.convertToken;
      state.converting = true;
      uploadBtn.disabled = true;
      convertBtn.disabled = true;
      convertState.textContent = '后端转换中…';
      uploadProgress.indeterminate('转换中…');
      try {
        const resp = await api.post('/api/tft/convert', {
          data: state.file.data,
          filename: state.file.name,
          options: buildOptions(),
        });
        if (token !== state.convertToken) return;
        state.result = resp;
        applyConvertMeta(resp);
        renderResult();
        renderStrip();
        drawFrame(0);
        startPlayback();
        ctx.toastSuccess(`转换完成：${resp.sourceFrames} 帧 → ${resp.framesCount} 帧`, { timeout: 2400 });
      } catch (e) {
        if (token !== state.convertToken) return;
        console.error('[screen] convert 失败', e);
        convertState.textContent = `转换失败：${e.message || e}`;
        uploadProgress.error('转换失败');
        ctx.toastError(`转换失败：${e.message || e}`);
      } finally {
        if (token === state.convertToken) {
          state.converting = false;
          convertBtn.disabled = false;
          uploadBtn.disabled = !state.result || !tftSupported;
          if (state.result) uploadProgress.set(0, '准备上传');
        }
      }
    }, 420);
    function scheduleConvert() {
      if (!state.file) return;
      convertState.textContent = '参数已变更，等待转换…';
      doConvert();
    }

    /* ---------------- 结果元信息（源帧数 / warnings / trim） ---------------- */
    function applyConvertMeta(resp) {
      const total = Number(resp.rawSourceFrames ?? resp.sourceFrames ?? 0);
      if (total) {
        const first = !state.rawSourceFrames;
        state.rawSourceFrames = total;
        trimStartInput.max = String(total);
        trimEndInput.max = String(total);
        if (first || state.trimEnd === null || state.trimEnd > total) state.trimEnd = total;
        if (state.trimStart < 1) state.trimStart = 1;
        if (state.trimStart > total) state.trimStart = 1;
        if (state.trimEnd < state.trimStart) state.trimEnd = total;
        trimStartInput.value = String(state.trimStart);
        trimEndInput.value = String(state.trimEnd);
        clampTrimInputs();
        const srcDur = Number(resp.sourceDurationMs) || 0;
        sourceInfoText.textContent = `源动画共 ${total} 帧${srcDur ? ` · 总时长 ${(srcDur / 1000).toFixed(1)} 秒` : ''}`;
      }
      state.warnings = Array.isArray(resp.warnings) ? resp.warnings.slice() : [];
      renderWarnings();
    }
    function renderWarnings() {
      warningsBanner.innerHTML = '';
      if (!state.warnings.length) { warningsBanner.style.display = 'none'; return; }
      warningsBanner.style.display = '';
      warningsBanner.append(
        h('div', { class: 'banner-icon', html: icon('alert-triangle', { size: 17 }) }),
        h('div', {}, ...state.warnings.map((w) => h('div', { class: 'tiny' }, w))),
      );
    }

    /* ---------------- 结果渲染 ---------------- */
    function renderResult() {
      const r = state.result;
      if (!r) return;
      const stats = r.stats || {};
      const rawSource = r.rawSourceFrames ?? r.sourceFrames ?? '—';
      const trim = r.trim || {};
      const sourceLabel = trim.trimmed ? `${rawSource} → ${trim.frames} 帧` : String(rawSource);
      convertState.textContent = `转换完成 · ${r.framesCount} 帧 · ${fmtBytes(stats.outputBytes || r.framesCount * FRAME_BYTES)}`;
      resultStats.innerHTML = '';
      const cards = [
        ['源帧数（截取后）', sourceLabel, ''],
        ['输出帧数', r.framesCount ?? '—', '帧'],
        ['压缩比', stats.frameReduction !== undefined ? `${Math.round(stats.frameReduction * 100)}` : '—', '%'],
        ['输出大小', fmtBytes(stats.outputBytes ?? r.framesCount * FRAME_BYTES), ''],
        ['预计上传', fmtSeconds(stats.estimatedSeconds ?? (stats.packets || 0) * secPerPacket), ''],
        ['上传包数', stats.packets ?? '—', '包'],
      ];
      if (r.requestedFrames && r.requestedFrames > (r.framesCount || 0) && r.requestedFrames > maxFrames) {
        convertState.textContent += ` · 目标 ${r.requestedFrames} 帧超过设备上限 ${maxFrames}，已按 ${maxFrames} 帧压缩`;
      }
      for (const [label, value, unit] of cards) {
        resultStats.append(h('div', { class: 'stat' },
          h('div', { class: 'stat-label' }, label),
          h('div', { class: 'stat-value' }, String(value), unit ? h('small', {}, unit) : null),
        ));
      }
      if (r.framesCount === 1) convertState.textContent += ' · 静态画面（末帧占位），上传约几秒';
    }

    function renderStrip() {
      frameStrip.innerHTML = '';
      const r = state.result;
      if (!r || !r.frames?.length) { stripMeta.textContent = '还没有输出帧'; return; }
      let frames = r.frames;
      const showMax = 70;
      if (frames.length > showMax) {
        const step = frames.length / showMax;
        frames = Array.from({ length: showMax }, (_, i) => r.frames[Math.round(i * step)]);
        stripMeta.textContent = `${r.framesCount} 帧（缩略图仅显示 ${showMax} 帧）· 点击可定位`;
      } else {
        stripMeta.textContent = `${r.framesCount} 帧 · 点击可定位`;
      }
      frames.forEach((src, i) => {
        frameStrip.append(h('div', {
          class: 'frame-thumb',
          title: `第 ${i + 1} 帧`,
          onclick: () => { stopPlayback(); drawFrame(Math.round(i * (r.frames.length / frames.length))); },
        },
          h('img', { src, style: { width: '100%', height: '100%', objectFit: 'cover' }, loading: 'lazy' }),
          h('span', { class: 'idx' }, String(i + 1)),
        ));
      });
      playBtn.disabled = (r.frames?.length || 0) < 2;
    }

    /* ---------------- 预览播放 ---------------- */
    const frameImages = new Map();
    function getImage(src) {
      if (frameImages.has(src)) return frameImages.get(src);
      const img = new Image();
      img.decoding = 'async';
      img.src = src;
      frameImages.set(src, img);
      return img;
    }
    function drawFrame(index) {
      const r = state.result;
      if (!r || !r.frames?.length) return;
      state.playIndex = ((index % r.frames.length) + r.frames.length) % r.frames.length;
      const img = getImage(r.frames[state.playIndex]);
      const paint = () => {
        previewCtx.fillStyle = '#000';
        previewCtx.fillRect(0, 0, TFT_W, TFT_H);
        previewCtx.drawImage(img, 0, 0, TFT_W, TFT_H);
      };
      if (img.complete && img.naturalWidth) paint();
      else img.onload = paint;
      previewWrap.style.display = '';
      previewEmpty.style.display = 'none';
    }
    function startPlayback() {
      stopPlayback();
      const r = state.result;
      if (!r || !r.frames || r.frames.length < 2) {
        playBtn.innerHTML = `${icon('play', { size: 13 })}<span>预览动画</span>`;
        return;
      }
      state.playing = true;
      playBtn.innerHTML = `${icon('pause', { size: 13 })}<span>暂停预览</span>`;
      const delay = r.delaysMs?.[0] || Math.round(1000 / effectiveFps());
      playTimer = setInterval(() => drawFrame(state.playIndex + 1), clamp(delay, 30, 2000));
    }
    function stopPlayback() {
      if (playTimer) clearInterval(playTimer);
      playTimer = null;
      state.playing = false;
    }
    playBtn.addEventListener('click', () => {
      if (state.playing) { stopPlayback(); playBtn.innerHTML = `${icon('play', { size: 13 })}<span>预览动画</span>`; }
      else startPlayback();
    });

    /* ---------------- 选文件 ---------------- */
    async function chooseFile(file) {
      if (!file) return;
      if (file.size > 30 * 1024 * 1024) { ctx.toastError('文件超过 30 MB，请先压缩'); return; }
      const dataUrl = await readFileAsDataURL(file);
      state.file = { name: file.name, size: file.size, type: file.type, data: dataUrl.split(',')[1] };
      state.result = null;
      state.rawSourceFrames = 0;
      state.trimStart = 1;
      state.trimEnd = null;
      state.warnings = [];
      renderWarnings();
      frameImages.clear();
      stopPlayback();
      fileRow.style.display = '';
      fileRow.innerHTML = '';
      fileRow.append(
        h('div', { class: 'ic', html: icon(/gif|webp|apng/i.test(file.type + file.name) ? 'image' : 'file', { size: 18 }) }),
        h('div', { style: { minWidth: 0 } },
          h('div', { style: { fontWeight: '600', fontSize: '13px' } }, file.name),
          h('div', { class: 'tiny muted' }, `${fmtBytes(file.size)} · ${file.type || '未知类型'} · 本地 base64`),
        ),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn sm ghost', html: `${icon('refresh', { size: 13 })}<span>重新选择</span>`,
          onclick: (e) => { e.stopPropagation(); fileInput.click(); },
        }),
      );
      dropzone.style.display = 'none';
      sourceStats.textContent = '正在解码首帧预览…';
      previewWrap.style.display = 'none';
      try {
        const bitmap = await createImageBitmap(file);
        previewCtx.fillStyle = '#000';
        previewCtx.fillRect(0, 0, TFT_W, TFT_H);
        const s = Math.min(TFT_W / bitmap.width, TFT_H / bitmap.height);
        const dw = bitmap.width * s, dh = bitmap.height * s;
        previewCtx.drawImage(bitmap, (TFT_W - dw) / 2, (TFT_H - dh) / 2, dw, dh);
        sourceStats.textContent = `源尺寸 ${bitmap.width}×${bitmap.height} · 正在调用后端转换…`;
        bitmap.close?.();
        previewWrap.style.display = '';
        previewEmpty.style.display = 'none';
      } catch { /* 动态图本地解码失败时等后端 */ }
      convertState.textContent = '正在调用后端转换…';
      doConvert();
    }

    /* ---------------- 上传 / 恢复默认 ---------------- */
    function setUploading(on) {
      state.uploading = on;
      uploadBtn.disabled = on || !state.result || !tftSupported;
      cancelBtn.disabled = !on;
      restoreBtn.disabled = on || !tftSupported;
      convertBtn.disabled = on;
    }
    function jobEta(d) {
      if (!d?.total || !d?.sent) return null;
      const elapsed = (Date.now() - state.uploadStartedAt) / 1000;
      const perPacket = elapsed / Math.max(1, d.sent);
      return perPacket * Math.max(0, d.total - d.sent);
    }
    async function upload() {
      if (!state.file) { ctx.toastWarn('请先选择素材'); return; }
      if (!state.result) { ctx.toastWarn('请等待转换完成'); return; }
      if (!tftSupported) { ctx.toastError('当前连接不支持 TFT 上传（2.4G 无线），请使用 USB 有线连接'); return; }
      setUploading(true);
      state.uploadStartedAt = Date.now();
      uploadProgress.reset('提交压缩上传任务…');
      jobInfo.firstChild.textContent = '任务已提交';
      try {
        await api.post('/api/tft/upload_file', {
          data: state.file.data,
          filename: state.file.name,
          options: buildOptions(),
        });
        startPoll();
        ctx.toast('上传任务已提交，进度实时显示', { timeout: 2600 });
      } catch (e) {
        uploadProgress.error(`提交失败：${e.message || e}`);
        setUploading(false);
        ctx.toastError(`提交失败：${e.message || e}`);
      }
    }
    async function cancelUpload() {
      try { await api.post('/api/tft/cancel'); ctx.toast('已请求取消上传'); } catch (e) { ctx.toastError(e.message || String(e)); }
      stopPoll();
      setUploading(false);
      uploadProgress.error('已取消');
    }
    async function restoreDefault() {
      const ok = await ctx.confirmDialog({
        title: '恢复官方默认动画',
        message: '将向键盘写入官方默认 135 帧动画，上传约 5 分钟（8.75 MB）。期间请勿关闭页面。',
        extra: '恢复前无法备份原屏幕内容（协议无读回命令）。',
        confirmText: '恢复默认动画',
      });
      if (!ok) return;
      setUploading(true);
      state.uploadStartedAt = Date.now();
      uploadProgress.reset('正在写入官方默认动画…');
      jobInfo.firstChild.textContent = '恢复默认动画任务已提交';
      try {
        await api.post('/api/tft/default');
        startPoll();
      } catch (e) {
        uploadProgress.error(`提交失败：${e.message || e}`);
        setUploading(false);
        ctx.toastError(`提交失败：${e.message || e}`);
      }
    }
    function startPoll() {
      stopPoll();
      pollTimer = setInterval(async () => {
        try {
          const job = await api.get('/api/tft/job');
          if (!job || !job.total) return;
          state.jobTotal = job.total;
          if (job.running) {
            const pct = job.pct ?? Math.round(((job.sent || 0) / job.total) * 100);
            uploadProgress.set(pct, `上传中 ${job.sent || 0} / ${job.total} 包…`);
            const eta = jobEta({ sent: job.sent, total: job.total });
            jobInfo.lastElementChild.textContent = eta !== null ? `ETA ${fmtSeconds(eta)}` : 'ETA —';
            return;
          }
          if (job.error) {
            uploadProgress.error(job.error === 'cancelled' ? '已取消' : `失败：${job.error}`);
            jobInfo.lastElementChild.textContent = 'ETA —';
            setUploading(false);
            stopPoll();
            return;
          }
          if (job.phase === 'done' || job.pct === 100) {
            uploadProgress.done('上传完成');
            jobInfo.lastElementChild.textContent = '完成';
            setUploading(false);
            stopPoll();
            ctx.toastSuccess('已上传到键盘屏幕');
          }
        } catch { /* 任务接口不可用时靠 WS */ }
      }, 900);
    }
    function stopPoll() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

    /* ---------------- WS 事件 ---------------- */
    offs.push(api.on('ws:progress', (d) => {
      if (!d || d.job !== 'tft') return;
      const pct = d.pct ?? (d.total ? Math.round((d.sent / d.total) * 100) : 0);
      state.jobTotal = d.total || state.jobTotal;
      uploadProgress.set(pct, `上传中 ${d.sent ?? 0} / ${d.total ?? '?'} 包…`);
      jobInfo.firstChild.textContent = `阶段 ${d.phase || 'upload'}`;
      const eta = jobEta(d);
      jobInfo.lastElementChild.textContent = eta !== null ? `ETA ${fmtSeconds(eta)}` : 'ETA —';
    }));
    offs.push(api.on('ws:job', (d) => {
      if (!d || d.job !== 'tft') return;
      if (d.state === 'done') {
        uploadProgress.done('上传完成');
        jobInfo.lastElementChild.textContent = '完成';
        setUploading(false);
        stopPoll();
        ctx.toastSuccess('已上传到键盘屏幕');
      } else if (d.state === 'error') {
        uploadProgress.error(d.error === 'cancelled' ? '已取消' : `失败：${d.error || '未知错误'}`);
        setUploading(false);
        stopPoll();
        if (d.error !== 'cancelled') ctx.toastError(`上传失败：${d.error || '未知错误'}`);
      }
    }));

    /* ---------------- 交互绑定 ---------------- */
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
    fileInput.addEventListener('change', () => { const f = fileInput.files?.[0]; if (f) chooseFile(f); fileInput.value = ''; });
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => { e.preventDefault(); dropzone.classList.remove('dragover'); const f = e.dataTransfer?.files?.[0]; if (f) chooseFile(f); });
    convertBtn.addEventListener('click', () => doConvert());
    uploadBtn.addEventListener('click', upload);
    cancelBtn.addEventListener('click', cancelUpload);
    restoreBtn.addEventListener('click', restoreDefault);
    resetOptBtn.addEventListener('click', () => {
      state.autoFrames = false; autoCheck.checked = false;
      frameSlider.el.style.opacity = '1'; frameSlider.el.style.pointerEvents = '';
      state.frameCount = Math.min(60, maxFrames); frameSlider.set(state.frameCount);
      state.timingMode = 'fps'; timingSeg.set('fps'); fpsWrap.style.display = ''; durationWrap.style.display = 'none';
      state.fps = 10; fpsInput.value = '10';
      state.fit = fitModes.includes('contain') ? 'contain' : fitModes[0]; fitSeg.set(state.fit);
      state.temporal = temporalModes[0]; temporalSeg.set(state.temporal);
      state.dither = false; ditherCheck.checked = false;
      state.dedupe = false; dedupeCheck.checked = false;
      state.resample = 'lanczos'; resampleSelect.value = 'lanczos';
      state.trimStart = 1; state.trimEnd = state.rawSourceFrames || null;
      trimStartInput.value = '1'; trimEndInput.value = state.rawSourceFrames ? String(state.rawSourceFrames) : '';
      clampTrimInputs();
      refreshTimingHint();
      scheduleConvert();
    });
    function renderSupportNotice() {
      supportBanner.style.display = tftSupported ? 'none' : '';
      uploadBtn.disabled = state.uploading || !state.result || !tftSupported;
    }
    ctx.onStatus?.((st) => {
      const next = (st?.caps ? st.caps.tft !== false : true) && tftInfo.supported !== false;
      if (next !== tftSupported) { tftSupported = next; renderSupportNotice(); }
    });

    /* ---------------- 布局 ---------------- */
    const supportBanner = h('div', { class: 'banner danger', style: { display: 'none', margin: '0 0 16px' } },
      h('div', { class: 'banner-icon', html: icon('alert-triangle', { size: 17 }) }),
      h('div', {}, h('strong', {}, '当前连接不支持 TFT 屏幕'),
        h('div', { class: 'tiny', style: { marginTop: '2px' } }, '2.4G 无线连接没有 TFT 通道（0xFF67），无法上传屏幕内容。请改用 USB 有线连接。')),
    );

    const materialCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '素材与预览'),
          h('div', { class: 'card-desc' }, '解码 / 裁剪 / 抽帧 / RGB565 全部由后端处理，前端只展示结果')),
        h('div', { class: 'spacer' }),
        badge('本地压缩', 'ok'),
      ),
      h('div', { class: 'card-body' },
        dropzone,
        fileRow,
        sourceStats,
        warningsBanner,
        h('div', { class: 'mt-16' }, previewWrap),
        previewEmpty,
        h('div', { class: 'row between mt-12' }, convertState, playBtn),
        frameStrip,
        stripMeta,
      ),
    );

    const settingsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '转换设置'),
          h('div', { class: 'card-desc' }, '参数变化后 400ms 自动重新转换预览')),
        h('div', { class: 'spacer' }),
        h('button', { class: 'btn sm ghost', html: `${icon('refresh-cw', { size: 13 })}<span>立即转换</span>`, onclick: () => doConvert() }),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'stack' },
          h('div', { class: 'field' },
            h('div', { class: 'field-label' }, '输出帧数（上限来自设备 maxFrames）'),
            autoRow,
            frameSlider.el,
          ),
          h('div', { class: 'field' }, h('div', { class: 'field-label' }, '时间控制（二选一）'), h('div', { class: 'row' }, timingSeg.el, fpsWrap, durationWrap), timingHint),
          h('div', { class: 'field' }, h('div', { class: 'field-label' }, '适配模式'), fitSeg.el),
          temporalModes.length > 1 ? h('div', { class: 'field' }, h('div', { class: 'field-label' }, '抽帧方式'), temporalSeg.el) : null,
          h('div', { class: 'field' }, h('div', { class: 'field-label' }, '重采样'), resampleSelect),
          h('div', { class: 'stack', style: { gap: '8px' } },
            h('label', { class: 'check' }, ditherCheck, h('span', {}, 'RGB565 抖动（8×8 Bayer，减轻渐变色带）')),
            h('label', { class: 'check' }, dedupeCheck, h('span', {}, '合并重复帧（静态画面会压到 1 帧）')),
          ),
          h('div', { class: 'row' }, convertBtn, resetOptBtn),
        ),
      ),
    );

    const resultCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '转换结果'),
          h('div', { class: 'card-desc' }, '帧数 / 压缩比 / 预计上传时间')),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn sm ghost', html: `${icon('download', { size: 13 })}<span>导出帧</span>`,
          onclick: () => {
            if (!state.result?.frames) { ctx.toastWarn('还没有可导出的帧'); return; }
            downloadText(`mk87-tft-${Date.now()}.json`, JSON.stringify({ ...state.result, options: buildOptions() }), 'application/json');
            ctx.toastSuccess('已导出转换结果 JSON');
          },
        }),
      ),
      h('div', { class: 'card-body' }, resultStats, h('div', { class: 'tiny muted mt-12' }, 'stats 来自后端 /api/tft/convert（estimatedSeconds 按实测 ≈146ms/包估算，实际进度以 WS 为准）。')),
    );

    const uploadCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '压缩并上传'),
          h('div', { class: 'card-desc' }, 'POST /api/tft/upload_file · 进度与 ETA 走 WebSocket')),
        h('div', { class: 'spacer' }),
        badge('USB only', 'accent'),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'stack' },
          uploadProgress.el,
          jobInfo,
          h('div', { class: 'row' }, uploadBtn, cancelBtn),
          h('div', { class: 'divider-dashed' }),
          restoreBtn,
          h('div', { class: 'tiny muted' },
            h('p', {}, '· 静态图输出 1 帧 + 末帧占位，上传约几秒；135 帧官方动画约 5 分钟。'),
            h('p', {}, '· 上传中不要关闭页面；取消会调用 /api/tft/cancel，已写入的帧可能残留。'),
          ),
        ),
      ),
    );

    const deviceCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '屏幕参数')),
      h('div', { class: 'card-body' },
        kvList([
          ['分辨率', `${tftInfo.width} × ${tftInfo.height}`],
          ['像素格式', `${tftInfo.pixelFormat || 'rgb565'}（${Number(tftInfo.byteOrder) === 1 ? '大端' : '小端'}）`],
          ['最大帧数', `${maxFrames} 帧`],
          ['上传命令', '0x50 动画 / 0x4D 静态（MK87 不可见）'],
          ['当前连接', tftSupported ? 'USB · 支持 TFT 上传' : '2.4G · 不支持 TFT 上传'],
          ['实测吞吐', `≈${Math.round(secPerPacket * 1000)} ms/包 · 135 帧约 5.2 分钟`],
        ]),
      ),
    );

    root.append(supportBanner, h('div', { class: 'grid grid-main' },
      h('div', { class: 'grid-stack' }, materialCard, resultCard),
      h('div', { class: 'grid-stack' }, sourceCard, settingsCard, uploadCard, deviceCard),
    ));

    /* ---------------- 初始化 ---------------- */
    autoCheck.checked = state.autoFrames;
    refreshTimingHint();
    renderSupportNotice();
    api.get('/api/tft/job').then((job) => {
      if (job && job.running) {
        setUploading(true);
        state.uploadStartedAt = Date.now();
        uploadProgress.indeterminate(`设备上已有上传任务… ${job.sent || 0}/${job.total || '?'}`);
        startPoll();
      }
    }).catch(() => {});

    return () => {
      stopPoll();
      stopPlayback();
      doConvert.cancel?.();
      offs.forEach((off) => off?.());
    };
  },
};
