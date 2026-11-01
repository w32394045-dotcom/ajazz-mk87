# -*- coding: utf-8 -*-
"""生成音乐律动测试用 WAV（48kHz / 16bit / 单声道）：
4 秒安静 + 6 秒节拍（底鼓/军鼓/踩镲 + 和弦垫），用于验证「音频→振幅→渲染→帧流」整条链路。
用法: python make_test_wav.py [输出路径] [秒数]
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, 'docs', '_test_audio.wav')
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    n = int(SR * dur)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float64)

    # 和弦垫（整段，轻微）
    for f, a in ((220.0, 0.05), (277.2, 0.04), (329.6, 0.04)):
        y += a * np.sin(2 * np.pi * f * t)

    # 前 3 秒：安静（只有垫音）；3 秒后开始节拍
    beat_start = 3.0
    if dur > beat_start:
        rng = np.random.default_rng(7)
        # 底鼓 0.5s 一次
        k = 0
        while beat_start + k * 0.5 < dur:
            t0 = beat_start + k * 0.5
            m = int(0.18 * SR)
            seg = np.arange(m) / SR
            env = np.exp(-seg / 0.05)
            freq = 55 + 40 * np.exp(-seg / 0.02)
            kick = 0.9 * env * np.sin(2 * np.pi * freq * seg)
            i0 = int(t0 * SR)
            i1 = min(n, i0 + m)
            y[i0:i1] += kick[:i1 - i0]
            k += 1
        # 军鼓 1s 一次（0.25 偏移）
        k = 0
        while beat_start + 0.25 + k * 1.0 < dur:
            t0 = beat_start + 0.25 + k * 1.0
            m = int(0.10 * SR)
            seg = np.arange(m) / SR
            noise = rng.standard_normal(m) * np.exp(-seg / 0.02)
            y[int(t0 * SR):min(n, int(t0 * SR) + m)] += 0.45 * noise[:max(0, min(n, int(t0 * SR) + m) - int(t0 * SR))]
            k += 1
        # 踩镲 0.125s 一次
        k = 0
        while beat_start + k * 0.125 < dur:
            t0 = beat_start + k * 0.125
            m = int(0.03 * SR)
            seg = np.arange(m) / SR
            hat = rng.standard_normal(m) * np.exp(-seg / 0.004)
            y[int(t0 * SR):min(n, int(t0 * SR) + m)] += 0.12 * hat[:max(0, min(n, int(t0 * SR) + m) - int(t0 * SR))]
            k += 1

    peak = np.max(np.abs(y)) or 1.0
    y = y / peak * 0.9
    pcm = (y * 32767).astype('<i2')
    import wave
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print('saved', out, '%.1fs %d samples' % (dur, n))


if __name__ == '__main__':
    main()
