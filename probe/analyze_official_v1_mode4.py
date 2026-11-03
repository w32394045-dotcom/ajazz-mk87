# -*- coding: utf-8 -*-
"""官方 v1（MusicPlug.exe）显示模式 4「曲率频阶」采样分析 —— 反推几何/调色板/频谱映射。

数据源：probe/capture_official_v1_mode4.py 的输出（capture/official_v1_mode4_*.jsonl）：
  每 100ms 轮询 `GET http://127.0.0.1:9191/api/keyboard/musiceffect/`，返回 102 键
  （MK87 6×17 网格；其中 15 个非法键回溯成 (0,0) 占位，按「每个格子取第一次出现」去重 → 87 键）。
采样时的音源由外部决定（440/100/2k/4k/8k 正弦、阶梯扫频、静音），见脚本头 --help。

用法：
  driver/.venv/Scripts/python.exe probe/analyze_official_v1_mode4.py [--grids] [--json out.json]

分析要点（= 官方 v1 真值）：
  * 柱子**底部对齐**（每列亮起的行永远是 6-1..5 的连续一段）→ 列柱状，不是曲线/环；
  * 17 列 = 频率：单音只点亮它所在的 1~3 列，扫频时柱峰随频率右移 → 左低右高；
  * 颜色 = 以 (2,8) 为原点的径向色相（满饱和，左右半屏约差 180°），整块以 ~0.8 圈/s 旋转；
  * 柱高随 amplitude 增大（amp=30 时单音峰值约 4/6 行，amp=100 时 6/6）。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRIVER = os.path.join(REPO, "driver")
if DRIVER not in sys.path:
    sys.path.insert(0, DRIVER)

DEFAULT_FILES = [
    os.path.join(REPO, "capture", "official_v1_mode4.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_amp.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_silence.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_tone100.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_tone440.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_tone2000.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_tone4000.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_tone8000.jsonl"),
    os.path.join(REPO, "capture", "official_v1_mode4_sweep.jsonl"),
]
COLS, ROWS = 17, 6


def load_segments(path):
    segs, cur = [], None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if rec.get("k") == "param":
            cur = {"param": rec, "frames": []}
            segs.append(cur)
        elif rec.get("k") == "http" and cur is not None:
            cur["frames"].append(rec)
    return segs


def cells(frame):
    """{(row, col): '#rrggbb'}：每个格子取第一次出现的键（15 个非法键会回溯成 (0,0)）。"""
    out = {}
    colors = frame.get("colors") or ""
    for i, k in enumerate(frame.get("keys") or []):
        key = (int(k.get("r", 0)), int(k.get("c", 0)))
        if key not in out:
            out[key] = colors[i * 6:i * 6 + 6]
    return out


def bars(frame):
    """每列柱高：从最底行往上连续点亮的格子数（缺键的行跳过）。"""
    d = cells(frame)
    out = []
    for c in range(COLS):
        rows = [r for r in range(ROWS) if (r, c) in d]
        h = 0
        for r in reversed(rows):
            if d[(r, c)] != "000000":
                h += 1
            else:
                break
        out.append(h)
    return out


def hue(c6):
    r, g, b = int(c6[0:2], 16) / 255.0, int(c6[2:4], 16) / 255.0, int(c6[4:6], 16) / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return -1.0
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0


def stable_frames(seg, settle=2.5):
    fr = seg["frames"]
    if not fr:
        return []
    t0 = fr[0]["t"]
    return [f for f in fr if f["t"] - t0 >= settle]


def ascii_heat(frames):
    on = collections.Counter()
    for f in frames:
        d = cells(f)
        for (r, c), v in d.items():
            if v != "000000":
                on[(r, c)] += 1
    lines = []
    for r in range(ROWS):
        line = ""
        for c in range(COLS):
            line += str(min(9, on[(r, c)] * 9 // max(1, len(frames))))
        lines.append(line)
    return lines


def ascii_sample(frame):
    d = cells(frame)
    return [
        "".join("." if d.get((r, c), "000000") == "000000" else "#" for c in range(COLS))
        for r in range(ROWS)
    ]


def bottom_aligned_ratio(frames):
    ok = tot = 0
    for f in frames:
        d = cells(f)
        for c in range(COLS):
            rows = [r for r in range(ROWS) if (r, c) in d]
            lit = [r for r in rows if d[(r, c)] != "000000"]
            if not lit:
                continue
            tot += 1
            if lit == rows[-len(lit):]:
                ok += 1
    return ok, tot


def hue_rotation(frames):
    """同一格（优先最底行 col 0..16）在相邻帧之间的色相增量（度/100ms）。"""
    deltas = []
    prev = {}
    for f in frames:
        d = cells(f)
        cur = {}
        for (r, c), v in d.items():
            if v != "000000" and r == 5:
                cur[c] = hue(v)
        for c, h in cur.items():
            if c in prev and h >= 0 and prev[c] >= 0:
                deltas.append((h - prev[c]) % 360.0)
        prev = cur
    return deltas


def our_grid(amp, bands=None):
    """用当前实现渲染一帧（不推进引擎状态太多），用于和采样对照。"""
    from mk87lib import music  # noqa: E402

    engine = music.MusicEngine(4, amplitude_ui=amp)
    for _ in range(10):
        engine.tick(800, bands)
    grid = music._render_frame(engine.lay, dict(engine.st), 4)
    return ["".join("." if sum(grid[r][c]) == 0 else "#" for c in range(COLS))
            for r in range(ROWS)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="*", default=DEFAULT_FILES)
    ap.add_argument("--grids", action="store_true", help="打印每段的平均热力图与一帧样例")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    summary = []
    for path in args.input:
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        print(f"\n### {name}")
        for seg in load_segments(path):
            p = seg["param"]
            frames = stable_frames(seg)
            if not frames:
                continue
            H = [bars(f) for f in frames]
            lits = [sum(h) for h in H]
            mean = [sum(h[c] for h in H) / len(H) for c in range(COLS)]
            meanstr = " ".join("%.1f" % x for x in mean)
            ok, tot = bottom_aligned_ratio(frames)
            deltas = hue_rotation(frames)
            deltas = [d for d in deltas if d < 180]
            rot = sum(deltas) / len(deltas) if deltas else 0.0
            print("  %-22s mode=%d amp=%-3d bg=%-2d  lit(min/avg/max)=%d/%.1f/%d"
                  % (p.get("label", ""), p["mode"], p["amp"], p["backmode"],
                     min(lits), sum(lits) / len(lits), max(lits)))
            print("     mean bars/col: %s" % meanstr)
            print("     bottom-aligned %d/%d 色相旋转 %.1f°/100ms (%.0f°/s @10Hz)"
                  % (ok, tot, rot, rot * 10))
            summary.append({
                "file": name, "label": p.get("label"), "mode": p["mode"], "amp": p["amp"],
                "frames": len(frames), "lit_min": min(lits),
                "lit_avg": round(sum(lits) / len(lits), 2), "lit_max": max(lits),
                "mean_bars": [round(x, 2) for x in mean],
                "bottom_aligned": [ok, tot], "hue_deg_per_100ms": round(rot, 1),
            })
            if args.grids and len(frames) > 10:
                print("     热力图(9=每帧都亮):")
                for line in ascii_heat(frames):
                    print("       " + line)
                print("     样例帧:")
                for line in ascii_sample(frames[len(frames) // 2]):
                    print("       " + line)

    # 与当前实现对照
    print("\n## 当前实现（_render_mode_4）对照：amp=30 / amp=100")
    for amp in (30, 100):
        print("  --- amp=%d（无频谱 → 曲率兜底轮廓；有全频段 → 满柱）---" % amp)
        for line in our_grid(amp):
            print("    " + line)
    if args.json:
        json.dump(summary, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n== 汇总已写入 %s" % args.json)


if __name__ == "__main__":
    main()
