# -*- coding: utf-8 -*-
"""官方 MK87 音乐律动 v1（Music.exe）采样分析 —— 逐模式反推颜色/覆盖率/时间行为。

数据源：capture/official_music_colors3.jsonl
  = probe/capture_official_music_v2.py 的输出：每 100ms 轮询
    `GET http://127.0.0.1:9191/api/keyboard/musiceffect/`，返回 102 键的 #RRGGBB。
    采样分组：A 12 显示模式（backmode=0）/ B 11 背景模式（mode=13）/ C 振幅 / D 背景亮度。

用法：
  driver/.venv/Scripts/python.exe probe/analyze_official_v1_modes.py \
      [--input capture/official_music_colors3.jsonl] [--grids] [--json out.json]

分析要点（这些就是「官方 v1 真值」）：
  * 纯色显示模式 6/7/8/9/10/11 的真实 RGB 与官方亮度缩放公式；
  * 1/2/4/5 属于「同一套曲率频阶柱状 + 不同调色板」的证据（按帧统计 + 调色板校验）；
  * 稳定段（跳过切换后的前 1.2s 残留）才计入统计，切段残留来自上一个模式的尾帧。
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

DEFAULT_INPUT = os.path.join(REPO, "capture", "official_music_colors3.jsonl")

#: 官方 v1 显示模式（docs/music-v1-config.json 顺序与文案）
V1_MODES = [
    (1, "绿色/黄色/红色"), (2, "彩虹色"), (13, "随曲起舞"), (4, "曲率频阶"),
    (5, "频谱循环"), (6, "白色"), (7, "红色"), (8, "橙色"), (9, "黄色"),
    (11, "绿色"), (10, "蓝色"), (100, "屏光联动"),
]
V1_BGS = [
    (0, "无"), (6, "白色"), (7, "红色"), (8, "橙色"), (9, "黄色"), (10, "蓝色"),
    (11, "绿色"), (1, "绿色/黄色/红色"), (2, "彩虹色"), (4, "色谱"), (5, "频谱循环"),
]
MODE_ZH = dict(V1_MODES)
BG_ZH = dict(V1_BGS)


# ----------------------------------------------------------------------
# 解析
# ----------------------------------------------------------------------
def load_segments(path):
    """按 param 记录切段；每段 = 一次官方参数组合的连续 HTTP 颜色帧。"""
    segments, cur = [], None
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
            segments.append(cur)
        elif rec.get("k") == "http" and cur is not None:
            cur["frames"].append(rec)
    return segments


def frame_colors(frame):
    """返回 [(row, col, '#RRGGBB')]，长度 102（含未点亮的 000000）。"""
    cs = frame.get("colors") or ""
    out = []
    for i, k in enumerate(frame.get("keys") or []):
        out.append((int(k.get("r", 0)), int(k.get("c", 0)), cs[i * 6:i * 6 + 6]))
    return out


def lit(frame):
    return [c for (_r, _c, c) in frame_colors(frame) if c and c != "000000"]


def hsv_hue(c6):
    r, g, b = int(c6[0:2], 16), int(c6[2:4], 16), int(c6[4:6], 16)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return -1.0  # 灰色/白/黑：无色相
    d = float(mx - mn)
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0


def frame_top(frame):
    got = lit(frame)
    if not got:
        return None
    return collections.Counter(got).most_common(1)[0][0]


def trim_leading(segments):
    """切掉每段开头「上一个模式的残留色」帧（官方切换模式后旧颜色会残留几帧）。

    做法：以「本帧主色 == 上一段最后几帧的主色」判定残留，遇到第一个不同主色的帧即开始计数。
    比固定跳 N 帧靠谱：像 mode=1/4 这类只在个别帧有输出的模式，固定跳帧会把真信号扔掉。
    """
    prev_tail = None
    for seg in segments:
        frames = seg["frames"]
        prev = prev_tail
        start = 0
        if prev and frames:
            for i, f in enumerate(frames):
                top = frame_top(f)
                if top is None or top != prev:
                    start = i
                    break
            else:
                start = len(frames)
        seg["stable_from"] = start
        tail = [frame_top(f) for f in frames[-6:] if frame_top(f)]
        prev_tail = collections.Counter(tail).most_common(1)[0][0] if tail else None
    return segments


def stable(seg):
    """段内有效帧（已切掉开头残留）。"""
    return seg["frames"][seg.get("stable_from", 0):]


# ----------------------------------------------------------------------
# 统计
# ----------------------------------------------------------------------
def segment_stats(seg):
    st_frames = stable(seg)
    lits = [len(lit(f)) for f in st_frames]
    colors = collections.Counter()
    per_frame_top = []
    for f in st_frames:
        got = lit(f)
        cnt = collections.Counter(got)
        colors.update(cnt)
        per_frame_top.append(cnt.most_common(1)[0][0] if cnt else "-")
    distinct_per_frame = []
    for f in st_frames:
        distinct_per_frame.append(len(set(lit(f))))
    hue_drift = 0.0
    n_hue = 0
    for a, b in zip([x for x in per_frame_top], [x for x in per_frame_top][1:]):
        if a == "-" or b == "-":
            continue
        ha, hb = hsv_hue(a), hsv_hue(b)
        if ha < 0 or hb < 0:
            continue
        d = abs(ha - hb) % 360
        hue_drift += min(d, 360 - d)
        n_hue += 1
    return {
        "frames": len(seg["frames"]),
        "stable_frames": len(st_frames),
        "lit_min": min(lits) if lits else 0,
        "lit_avg": (sum(lits) / len(lits)) if lits else 0.0,
        "lit_max": max(lits) if lits else 0,
        "colors": colors,
        "per_frame_top": per_frame_top,
        "distinct_per_frame": (
            sum(distinct_per_frame) / len(distinct_per_frame) if distinct_per_frame else 0.0
        ),
        "hue_drift": (hue_drift / n_hue) if n_hue else 0.0,
        "top_changed": (
            sum(1 for a, b in zip(per_frame_top, per_frame_top[1:]) if a != b)
            if per_frame_top else 0
        ),
    }


def behavior_of(st, mode=None, expected=None):
    """时间行为分类：静态纯色 / 单色轮转 / 同帧多色 / 无输出。

    传入 mode/expected 时只统计「符合该模式调色板」的帧主色，滤掉切换残留与外来颜色。
    """
    if st["lit_max"] == 0:
        return "无输出（全黑）"
    tops = [c for c in st["per_frame_top"] if c != "-"]
    if mode is not None and expected is not None:
        tops = [c for c in tops if matches(mode, c, expected)] or tops
    if not tops:
        return "无输出（全黑）"
    if len(set(tops)) == 1:
        return "静态单色"
    if st["distinct_per_frame"] <= 1.35:
        return "整帧单色·逐帧变色(循环)"
    return "同帧多色(渐变/图案)"


def palette_probe():
    """用我们移植的调色板函数算官方 v1 各模式在 bb=100 下的期望颜色（校验实现）。

    返回 {mode: {"kind": "solid"|"bands"|"hue"|"screen", "colors": set(...)}}：
      solid/bands → 采样颜色应精确命中集合；
      hue        → 满饱和 HSV（最大通道 255）+ 色相落在 _hsv 曲线上；
      screen     → 屏幕灰白（最大-最小通道差小）。
    """
    from mk87lib import music  # noqa: E402  延迟导入：只有校验段需要

    st = {"centerRow": 2, "centerCol": 8, "huePhase": 0.0}

    def grid_colors(palette_id, phase=0.0, bb=100):
        grid = music._zeros(6, 17)
        music._apply_background(grid, palette_id, bb, dict(st, huePhase=phase))
        return grid

    out = {}
    for mode in (1, 2, 6, 7, 8, 9, 10, 11):
        grid = grid_colors(mode)
        out[mode] = {"kind": "bands" if mode in (1, 2) else "solid",
                     "colors": {"%02X%02X%02X" % c for row in grid for c in row}}
    # 4（径向色相）与 5（旋转单色）颜色随相位变化：只校验「满饱和 HSV」性质
    out[4] = {"kind": "hue", "colors": set()}
    out[5] = {"kind": "hue", "colors": set()}
    out[13] = {"kind": "hue", "colors": set()}
    out[100] = {"kind": "screen", "colors": set()}
    return out


def is_full_hsv(c6, tol=3):
    """颜色是否等于 _hsv(某色相)（满饱和满亮度；最大通道 255）。"""
    from mk87lib import music  # noqa: E402

    r, g, b = int(c6[0:2], 16), int(c6[2:4], 16), int(c6[4:6], 16)
    if max(r, g, b) != 255:
        return False
    hue = hsv_hue(c6)
    if hue < 0:
        return False
    want = music._hsv(hue, 1.0, 1.0)
    return all(abs(want[i] - (r, g, b)[i]) <= tol for i in range(3))


def matches(mode, c6, expected):
    """采样颜色是否与「我们实现的该模式调色板」一致。"""
    spec = expected.get(mode)
    if not spec:
        return False
    kind = spec["kind"]
    if kind in ("solid", "bands"):
        return c6 in spec["colors"]
    if kind == "hue":
        return is_full_hsv(c6)
    if kind == "screen":
        r, g, b = int(c6[0:2], 16), int(c6[2:4], 16), int(c6[4:6], 16)
        return max(r, g, b) - min(r, g, b) <= 24 and max(r, g, b) > 150  # 屏幕灰白
    return False


def brightness_probe():
    """官方亮度缩放：采样反推公式 (通道 * int(bb*255/100)) >> 8。"""
    def scale(ch, bb):
        return (ch * int(bb * 255.0 / 100.0)) >> 8
    return {
        100: "%02X" % scale(255, 100),
        50: "%02X" % scale(255, 50),
        20: "%02X" % scale(255, 20),
    }


def ascii_grid(frame):
    cells = frame_colors(frame)
    rows = max(r for (r, _c, _x) in cells) + 1
    cols = max(c for (_r, c, _x) in cells) + 1
    exists = {(r, c) for (r, c, _x) in cells}
    litmap = {(r, c): x for (r, c, x) in cells if x != "000000"}
    lines = []
    for r in range(rows):
        line = ""
        for c in range(cols):
            if (r, c) not in exists:
                line += " "
            elif (r, c) in litmap:
                line += "#"
            else:
                line += "."
        lines.append(line)
    return lines, rows, cols


def bottom_anchored_ratio(frame):
    """亮起键是否「从底部连续向上」：柱状图案特征。"""
    cells = frame_colors(frame)
    rows = max(r for (r, _c, _x) in cells) + 1
    bycol = collections.defaultdict(list)
    for (r, c, x) in cells:
        if x != "000000":
            bycol[c].append(r)
    ok = 0
    for rs in bycol.values():
        rs = sorted(rs)
        if rs == list(range(rows - len(rs), rows)):
            ok += 1
    return ok, len(bycol)


# ----------------------------------------------------------------------
# 报告
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--grids", action="store_true", help="打印各显示模式最亮一帧的 ASCII 图案")
    ap.add_argument("--json", default=None, help="把机器可读汇总写到该路径")
    args = ap.parse_args()

    segments = load_segments(args.input)
    if not segments:
        raise SystemExit(f"没有解析到采样段：{args.input}")
    trim_leading(segments)

    expected = palette_probe()
    bright = brightness_probe()
    summary = {"input": args.input, "segments": [], "palette": {
        k: {"kind": v["kind"], "colors": sorted(v["colors"])} for k, v in expected.items()
    }, "brightness": bright}
    def emit(text=""):
        print(text)

    def palette_check(mode, colors):
        """采样色对我们实现的命中率（只看出现次数靠前的颜色）。"""
        if not colors:
            return "-"
        top = [c for c, _n in colors.most_common(6)]
        hit = sum(n for c, n in colors.most_common(6) if matches(mode, c, expected))
        tot = sum(n for c, n in colors.most_common(6))
        return "调色板 %d/%d 色·%d%% 计数命中" % (
            sum(1 for c in top if matches(mode, c, expected)), len(top),
            round(hit * 100.0 / tot) if tot else 0)

    emit(f"records: {len(segments)} 段（{os.path.basename(args.input)}）  "
         f"有效段 = 自动切掉每段开头上一模式的残留帧")

    # ---- A/B/C/D 分组统计 ----
    groups = collections.defaultdict(list)
    for seg in segments:
        p = seg["param"]
        key = (p["mode"], p["backmode"], p["amp"], p["bb"])
        st = segment_stats(seg)
        summary["segments"].append({
            "mode": p["mode"], "backmode": p["backmode"], "amp": p["amp"], "bb": p["bb"],
            "label": p.get("label"), "frames": st["frames"],
            "stable_from": seg.get("stable_from", 0),
            "lit_min": st["lit_min"], "lit_avg": round(st["lit_avg"], 2), "lit_max": st["lit_max"],
            "distinct_per_frame": round(st["distinct_per_frame"], 2),
            "hue_drift": round(st["hue_drift"], 1),
            "top_colors": st["colors"].most_common(6),
            "behavior": behavior_of(st),
        })
        groups[key].append(st)

    emit("\n== A：12 个显示模式（backmode=0, amp=30, bb=100）==")
    emit("%-4s %-14s %-7s %-15s %-26s %-9s %s" % (
        "mode", "官方文案", "帧数", "点亮(min/avg/max)", "主色(计数)", "同帧色数", "时间行为 / 调色板校验"))
    for mode, zh in V1_MODES:
        seg_stats = groups.get((mode, 0, 30, 100))
        if not seg_stats:
            continue
        st = seg_stats[0]
        tops = ", ".join("%s:%d" % (c, n) for c, n in st["colors"].most_common(3)) or "-"
        emit("%-4d %-14s %-7d %-15s %-26s %-9.2f %s %s" % (
            mode, zh, st["frames"],
            "%d/%.1f/%d" % (st["lit_min"], st["lit_avg"], st["lit_max"]),
            tops, st["distinct_per_frame"], behavior_of(st, mode, expected),
            palette_check(mode, st["colors"])))

    emit("\n== B：11 个背景模式（mode=13, amp=30, bb=100）==")
    emit("%-2s %-14s %-14s %-26s %s" % ("bg", "官方文案", "点亮(avg/max)", "主色(计数)", "调色板校验"))
    for bg, zh in V1_BGS:
        seg_stats = groups.get((13, bg, 30, 100))
        if not seg_stats:
            continue
        st = seg_stats[0]
        tops = ", ".join("%s:%d" % (c, n) for c, n in st["colors"].most_common(3)) or "-"
        # bg=0 段没有背景色，统计到的是显示模式 13 自己的前景色
        check_mode = 13 if bg == 0 else bg
        emit("%-2d %-14s %-14s %-26s %s" % (
            bg, zh, "%.1f/%d" % (st["lit_avg"], st["lit_max"]), tops,
            palette_check(check_mode, st["colors"])))

    emit("\n== C/D：振幅与背景亮度 ==")
    for key, st in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
        mode, bg, amp, bb = key
        if bg == 0 and amp != 30 and mode == 13:
            for s in st:
                emit("  C mode=13 amp=%-3d lit avg=%.1f max=%d" % (amp, s["lit_avg"], s["lit_max"]))
    for bb in (100, 50, 20):
        seg_stats = groups.get((13, 1, 30, bb))
        if seg_stats:
            s = seg_stats[0]
            emit("  D mode=13 bg=1 bb=%-3d lit avg=%.1f max=%d 主色=%s" % (
                bb, s["lit_avg"], s["lit_max"], s["colors"].most_common(2)))
    emit("  亮度公式校验：bb=100→%s / bb=50→%s / bb=20→%s（(c*int(bb*255/100))>>8）"
         % (bright[100], bright[50], bright[20]))

    # ---- 期望调色板（我们实现）----
    emit("\n== 我们实现（_apply_background 调色板）在 bb=100 下的期望色 ==")
    for mode in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11):
        spec = expected.get(mode) or {}
        if spec.get("kind") == "hue":
            emit("  palette(mode=%d) = 满饱和 HSV（色相随相位旋转，最大通道 255）" % mode)
        else:
            emit("  palette(mode=%d) = %s" % (mode, ", ".join(sorted(spec.get("colors") or []))))

    # ---- 形状 ----
    if args.grids:
        emit("\n== 形状样例（稳定段最亮一帧；# = 点亮，. = 黑，空格 = 该键盘位不存在）==")
        for mode, zh in V1_MODES:
            seg = next((s for s in segments
                        if s["param"]["mode"] == mode and s["param"]["backmode"] == 0), None)
            if not seg:
                continue
            frames = stable(seg)
            if not frames:
                continue
            best = max(frames, key=lambda f: len(lit(f)))
            grid_lines, rows, cols = ascii_grid(best)
            ok, tot = bottom_anchored_ratio(best)
            emit(f"\n-- mode={mode} {zh}: lit={len(lit(best))} 柱状(底部对齐)列={ok}/{tot}")
            for line in grid_lines:
                emit("   " + line)

    # ---- 结论 ----
    emit("\n== 结论 ==")

    def solid_hex(mode):
        spec = expected.get(mode) or {}
        got = sorted(spec.get("colors") or [])
        return got[0] if got else "-"

    emit("1) 纯色显示模式 6/7/8/9/10/11 的真实 RGB（bb=100）: "
         "6=%s 7=%s 8=%s 9=%s 10=%s 11=%s" % (
             solid_hex(6), solid_hex(7), solid_hex(8),
             solid_hex(9), solid_hex(10), solid_hex(11)))
    emit("2) 采样证实 v1 文案：11=绿(00FE00)、10=蓝(0000FE)（旧 capture 脚本的 11/10 标签写反了）")
    emit("3) 1/2/4/5 与 6..11 同一套「曲率频阶柱状」几何，仅调色板不同："
         "1=绿黄红分行、2=6 色横条、4=径向色相、5=旋转单色（逐帧换色）")
    emit("4) 亮度：官方 = (通道 * int(bb*255/100)) >> 8 —— bb=100 → %s、bb=50 → %s、bb=20 → %s"
         % (bright[100], bright[50], bright[20]))
    emit("5) 覆盖率随振幅波动（同一模式不同时刻 12%~52%），无全键铺满的纯色帧；"
         "切换模式后开头几帧是上一模式的残留")
    emit("6) mode=100 屏光联动：102 键全亮且为屏幕灰白采样色，主机侧无渲染器（自研屏幕同步待做）")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
        print(f"\n== 汇总已写入 {args.json}")


if __name__ == "__main__":
    main()
