# -*- coding: utf-8 -*-
"""分析官方 Music.exe 组合采样 JSONL（capture_official_music_v2.py 的输出）。

用法:
  driver/.venv/Scripts/python.exe probe/analyze_official_music.py \
      --input capture/official_music_colors3.jsonl [--grids] [--out report.txt]

输出:
  * 每个组合（param 记录切段）的样本数、颜色变化次数、点亮键数(lit avg/max)、高频颜色
  * --grids 时对代表性组合打印 ASCII 图案（按 row/col 摆放，R/G/B/Y/C/M/W/. 表示色系）
"""
import argparse
import collections
import json


def load(path):
    recs = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def segments(recs):
    segs, cur = [], None
    for r in recs:
        if r.get("k") == "param":
            cur = {"p": r, "s": []}
            segs.append(cur)
        elif r.get("k") == "http" and cur is not None:
            cur["s"].append(r)
    return segs


def sig(s):
    return s.get("colors", "")


def lit_count(s):
    cs = s.get("colors", "")
    return sum(1 for i in range(0, len(cs), 6) if cs[i:i + 6] != "000000")


def sym(c6):
    if not c6:
        return " "
    try:
        r, g, b = int(c6[0:2], 16), int(c6[2:4], 16), int(c6[4:6], 16)
    except Exception:
        return "?"
    m = max(r, g, b)
    if m < 10:
        return "."
    if abs(r - g) < 40 and abs(g - b) < 40 and abs(r - b) < 40:
        return "W"
    if r >= g and r >= b:
        return "R" if (g < 60 and b < 60) else ("Y" if g > b else "M")
    if g >= r and g >= b:
        return "G" if (r < 60 and b < 60) else ("C" if b > r else "Y")
    return "B" if (r < 60 and g < 60) else ("M" if r > g else "C")


def grid(s):
    keys = s.get("keys") or []
    cs = s.get("colors", "")
    if not keys:
        return ""
    rows = max(k.get("r", 0) for k in keys) + 1
    cols = max(k.get("c", 0) for k in keys) + 1
    g = [[" "] * cols for _ in range(rows)]
    for i, k in enumerate(keys):
        g[k.get("r", 0)][k.get("c", 0)] = sym(cs[i * 6:i * 6 + 6])
    return "\n".join("".join(r) for r in g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--grids", action="store_true", help="对代表性组合打印 ASCII 图案")
    ap.add_argument("--out", default=None, help="报告写入文件（默认仅 stdout）")
    ap.add_argument("--grid-labels", default="A mode=1,A mode=2,A mode=13,A mode=4,A mode=5,A mode=7,A mode=100",
                    help="逗号分隔，打印这些 label 的图案")
    args = ap.parse_args()

    recs = load(args.input)
    segs = segments(recs)
    lines = [f"records={len(recs)} segments={len(segs)}", ""]
    lines.append(f"{'label':26s} {'n':>3s} {'chg':>4s} {'lit':>6s} {'maxlit':>6s}  top")
    for seg in segs:
        p, s = seg["p"], seg["s"]
        if len(s) < 3:
            continue
        ch = sum(1 for a, b in zip(s, s[1:]) if sig(a) != sig(b))
        lits = [lit_count(x) for x in s]
        cnt = collections.Counter()
        for x in s:
            cs = x.get("colors", "")
            for i in range(0, len(cs), 6):
                c = cs[i:i + 6]
                if c != "000000":
                    cnt[c] += 1
        tops = ", ".join(f"{c}:{n}" for c, n in cnt.most_common(3))
        lines.append(f"{p.get('label', '?'):26s} {len(s):3d} {ch:4d} "
                     f"{sum(lits) / len(lits):6.1f} {max(lits):6d}  {tops}")
    if args.grids:
        want = {x.strip() for x in args.grid_labels.split(",") if x.strip()}
        for seg in segs:
            lab = seg["p"].get("label", "")
            if lab in want and seg["s"]:
                mid = seg["s"][len(seg["s"]) // 2]
                lines += ["", f"=== {lab} ===", grid(mid)]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    main()
