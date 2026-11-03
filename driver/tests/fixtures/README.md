# 默认档（LED 颜色覆盖 = `default`）逐字节回归快照

`music_default_snapshot.json` 是「官方方案」渲染器在**不加颜色覆盖**时的输出指纹，
用来卡住这条约束：**`color` 缺省或显式 `"default"` 时，每一帧 348B 载荷必须与加入
颜色覆盖层之前完全一致。**

## 文件内容

- `meta`：生成时的 `music.py` SHA-256、模式/背景模式列表、固定振幅序列、随机种子、
  模式 4 的固定频谱公式等；
- `cases["<mode>/<backmode>"]`：固定 16 tick 喂料下，全部 `87*4` 字节载荷**拼接后**的
  SHA-256（每个组合一个哈希）。

## 矩阵（定义在 `tests/test_music_preview.py`）

| 维度 | 取值 |
|---|---|
| 显示模式 | `sorted(music.IMPLEMENTED_MODES)` 全部 20 个（1,2,4,5,6,7,8,9,10,11,13,14…22） |
| 背景模式 | `BACKMODES` 全部 11 个（0,1,2,4,5,6,7,8,9,10,11） |
| 每格 tick 数 | 16（前 6 tick 静音，覆盖官方 C=5 振幅归零；之后 300/700/1000/520/0/0/0/0/0/820） |
| 频谱 | 每 tick 喂固定 32 段（只有模式 4 消费），公式见 `meta.bands32` |
| 随机 | 模式 19 使用 `random.random()`，固定种子 `0x5EED` 才能复现 |

共 20 × 11 = 220 个哈希。

## 快照来源

由**加入颜色覆盖层之前**的 `music.py` 生成，哈希记录在 `meta.music_py_sha256`。当时
工作树 = commit `20c1e07` + 另一代理刚完成的「官方 v1 显示模式 4 真值（17 列频谱柱 +
径向色相旋转）」修复。生成之后**没有**再改动任何 `cases` 哈希（新代码跑同一矩阵得到的
哈希与之逐条一致，见 `tests/test_music_preview.py::TestColorDefaultByteIdentical`）。

平台说明：快照在 Windows + CPython 3.12 上生成。不同 libm（如 Linux glibc）的
`sin/cos/atan2/pow` 末位可能不同，因此**精确哈希比对只在 Windows 上执行**；其它平台
自动跳过，跨平台仍由 `test_omitted_and_default_color_are_identical`（同一进程内比较
「缺省」与 `"default"` 两种写法）覆盖。

## 重新生成（仅当渲染器被**有意**修改时）

1. 先确认新旧输出的差异正是这次修改想要的（逐模式对照 `capture/` 里的官方采样）；
2. 在 `driver/` 下运行下面的脚本重新生成；
3. `git diff` 审查 `cases` 的每一处变化，提交时写清哪个模式/为什么变。

```python
# driver/_gen_music_default_snapshot.py
import datetime, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

from mk87lib import music          # noqa: E402
import test_music_preview as t     # noqa: E402

cases = {f"{m}/{b}": t.music_default_digest(m, b) for m, b in t.snapshot_cases()}
with open(os.path.join(HERE, "mk87lib", "music.py"), "rb") as f:
    py_sha = hashlib.sha256(f.read()).hexdigest()
meta = {
    "note": "color 缺省/default 的逐字节回归快照",
    "music_py_sha256": py_sha,
    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "mode_count": len(music.IMPLEMENTED_MODES),
    "modes": sorted(music.IMPLEMENTED_MODES),
    "backmodes": list(t.BACKMODES),
    "amps": list(t.SNAPSHOT_AMPS),
    "amplitude_ui": 60,
    "backmode_brightness": 55,
    "random_seed": 0x5EED,
    "bands32": "[(tick*7 + i*3) % 11 / 10 for i in range(32)]",
    "tick_count": len(t.SNAPSHOT_AMPS),
}
with open(os.path.join(HERE, "tests", "fixtures", "music_default_snapshot.json"),
          "w", encoding="utf-8", newline="\n") as f:
    json.dump({"meta": meta, "cases": cases}, f, ensure_ascii=False, indent=1, sort_keys=True)
    f.write("\n")
```
