// 用官方还原的 MusicEngine（scripts/music_ref.js）把 WAV 转成 USB 帧序列 JSON。
// 用法: node gen_music_frames.js <wav> <mode> <out.json> [fps=20] [maxFrames]
// 输出: { mode, fps, frames: [ { amp, packets: ["00aaff...", ...7个] } ] }
const fs = require('fs');
const path = require('path');
const ref = require(path.join(__dirname, 'music_ref.js'));

function readWav(file) {
  const b = fs.readFileSync(file);
  if (b.toString('ascii', 0, 4) !== 'RIFF' || b.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error('不是 WAV 文件');
  }
  let off = 12;
  let fmt = null;
  let data = null;
  while (off + 8 <= b.length) {
    const id = b.toString('ascii', off, off + 4);
    const size = b.readUInt32LE(off + 4);
    const body = off + 8;
    if (id === 'fmt ') {
      fmt = {
        channels: b.readUInt16LE(body + 2),
        sampleRate: b.readUInt32LE(body + 4),
        bits: b.readUInt16LE(body + 14),
      };
    } else if (id === 'data') {
      data = b.subarray(body, Math.min(b.length, body + size));
    }
    off = body + size + (size & 1);
  }
  if (!fmt || !data) throw new Error('WAV 缺 fmt/data');
  if (fmt.bits !== 16) throw new Error('只支持 16bit WAV');
  const n = Math.floor(data.length / 2 / fmt.channels);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const idx = i * fmt.channels * 2;
    out[i] = data.readInt16LE(idx) / 32768;
  }
  return { samples: out, sampleRate: fmt.sampleRate, channels: fmt.channels };
}

function main() {
  const [wav, modeArg, outArg, fpsArg, maxArg] = process.argv.slice(2);
  if (!wav || !outArg) {
    console.error('用法: node gen_music_frames.js <wav> <mode> <out.json> [fps] [maxFrames]');
    process.exit(1);
  }
  const mode = parseInt(modeArg || '13', 10);
  const fps = parseFloat(fpsArg || '20');
  const maxFrames = maxArg ? parseInt(maxArg, 10) : 0;
  const { samples, sampleRate } = readWav(wav);
  const step = Math.round(sampleRate / fps);       // 每 tick 前进的样本数
  const win = 2048;                                // 官方 fftSize
  const total = Math.floor((samples.length - win) / step) + 1;
  const nFrames = maxFrames > 0 ? Math.min(total, maxFrames) : total;

  const engine = new ref.MusicEngine({ mode });
  const frames = [];
  for (let f = 0; f < nFrames; f++) {
    const end = Math.min(samples.length, f * step + win);
    const start = Math.max(0, end - win);
    const winData = new Float32Array(win);
    winData.set(samples.subarray(start, end), win - (end - start));
    const r = engine.tick({ floatTimeData: winData });
    frames.push({
      amp: r.amplitude,
      packets: r.packets.map((p) => Buffer.from(p).toString('hex')),
    });
  }
  const out = { mode, fps, nFrames, sampleRate, frames };
  fs.writeFileSync(outArg, JSON.stringify(out));
  const amps = frames.map((x) => x.amp);
  const nz = amps.filter((a) => a > 0).length;
  console.log(`mode=${mode} frames=${nFrames} 有声帧=${nz} amp max=${Math.max(...amps)} ` +
    `min=${Math.min(...amps)} -> ${outArg} (${(fs.statSync(outArg).size / 1024).toFixed(0)} KB)`);
}

main();
