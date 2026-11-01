# -*- coding: utf-8 -*-
"""把宏写入真机测试结果 + 97/98 定位结论写回文档（2026-11-01）"""
import os

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')


def p(f):
    return os.path.join(DOCS, f)


def read(f):
    return open(p(f), encoding='utf-8').read()


def write(f, s):
    open(p(f), 'w', encoding='utf-8').write(s)


def rep(f, old, new):
    s = read(f)
    if old in s:
        write(f, s.replace(old, new, 1))
        print('[OK]', f, '|', old.replace('\n', ' ')[:46])
    else:
        print('[MISS]', f, '|', old.replace('\n', ' ')[:46])


def app(f, text, marker):
    s = read(f)
    if marker in s:
        print('[SKIP]', f)
        return
    write(f, s.rstrip('\n') + text)
    print('[APPEND]', f)


T = 'TEST-REPORT.md'

# 1) Phase 3 宏写入结果
rep(T,
    '宏写入（3.6）：`SET_MACRO` 400B 偏移表 + 动作表的细节在 bundle 里没有完整编码器，**本轮未做**，\n'
    '保持「⬜ 待测」（自研工具实现前需要先补这块的静态结论）。',
    '### 3.6 宏写入（✅ 真机全通）\n\n'
    '官方 `PZ`(setMacroData) / `NZ`(getMacroData) 已完整还原（格式见 [keymap.md](keymap.md) §16），真机验证：\n\n'
    '| 测试 | 结果 |\n|---|---|\n'
    '| 写宏 "abc"（6 个动作：a/b/c 各 press+release，delay=10ms） | 偏移表 400B（8 包，全 last=0）+ 动作区 28B（1 包 last=1）ACK 全通 |\n'
    '| 回读 `GET_MACRO` | 偏移 `90 01 00 00`(=400)、块头 `0C 00`(=6 动作×2)、6 个动作 **逐字节一致** |\n'
    '| 绑定与执行 | 槽 103 Insert = `06 00 00 00`(MACRO 0) → 记事本按 Insert **打出 "abc"** |\n'
    '| mask=1（重复 N 次） | `06 00 01 03` → 按一下 Insert **打出 "aaa"**（重复 3 次） |\n'
    '| mask=2（再按结束） | `06 00 02 00` → 按一下开始连续刷、再按一下停 **符合预期** |\n'
    '| 收尾 | 清空宏表（回读无非空项）+ 槽 103 还原 + 灯效还原，全部逐字节一致 |\n')

# 2) 汇总表 Phase 3
rep(T,
    '| Phase 3 | 改键（普通层 / FUNC / FN 层 / phantom 槽）/ 25 槽语义 | ✅ 全通，产出 3 条新结论 |',
    '| Phase 3 | 改键（普通层 / FUNC / FN 层 / phantom 槽 / 25 槽语义 / 宏写入） | ✅ 全通，产出 4 条新结论 |')

# 3) §12 新事实追加
rep(T,
    '- 键盘 HID `\\kbd` 接口用户态读取被拒绝（err=5），**RawInput 可用且能拿到设备路径**',
    '- 键盘 HID `\\kbd` 接口用户态读取被拒绝（err=5），**RawInput 可用且能拿到设备路径**\n'
    '- **宏表二进制格式已还原并真机验证**：400B = 100×u32 LE 绝对偏移（数据区从 400 开始）；\n'
    '  宏块 = `[0..1]=动作数×2 (u16 LE) [2..3]=0` + 每动作 4B `[delay u16LE][keyCode(HID usage)][flags]`，\n'
    '  `flags = ((actionType&7)<<4) | (isPress?0x80:0)`（键盘动作 actionType=3 → 按下 0xB0 / 抬起 0x30）；\n'
    '  写入分两包：偏移表 `contentSize=400, addr=0, 全包 last=0`，动作区 `contentSize=len, addr=400, 末包 last=1`\n'
    '- **宏播放方式 mask**（param2）：0=常规单次、1=重复 param3 次（实测 3 → 3 遍）、2=再按结束（实测通过）\n'
    '- **槽 97/98 有 LED 驱动通道但无可见光**：自定义模式下写 97=红/98=绿，`GET_ALL_LIGHTS_RGB` 回读确认\n'
    '  缓冲里就是红/绿，但人眼看不到任何绿色灯（红色只有 Fn 充电指示灯）→ 判定为未装配/被遮挡的隐藏通道')

# 4) §13 关闭第 1、5 条
rep(T,
    '| 1 | 宏写入 `SET_MACRO` | 400B 偏移表 + 动作表的完整编码未静态还原，本轮未测 | 先补静态（macro chunk），再真机 |',
    '| 1 | ~~宏写入 `SET_MACRO`~~ | **已关闭：格式已还原 + 真机全通（写/读回逐字节一致、mask 0/1/2 全部验证）** | — |')
rep(T,
    '| 5 | 97/98 这两颗 LED 的物理位置 | 用户只能确认「是 logo 灯/跑马灯区域」 | 逐颗点亮+拍照定位 |',
    '| 5 | ~~97/98 这两颗 LED 的物理位置~~ | **已关闭：有 LED 驱动通道但无可见光**（写红/绿回读正确但人眼不可见） | 不做 |')

# 5) 产物
rep(T,
    '`phase6_wireless.py`、`phase7_keyevents.py`、`phase7_rawinput.py`、`restore_tft_default.py`、',
    '`phase6_wireless.py`、`phase7_keyevents.py`、`phase7_rawinput.py`、`phase3_macro.py`、`phase3_macro_mask.py`、\n  `restore_tft_default.py`、')
rep(T,
    '`phase6_wireless.json`、`phase6_display.json`、`phase7_keyevents.json`、`phase7_rawinput.json`、',
    '`phase6_wireless.json`、`phase6_display.json`、`phase7_keyevents.json`、`phase7_rawinput.json`、\n  `phase3_macro.json`、')

F = 'FEATURES.md'
rep(F,
    '| 13 | 宏写入 | `SET_MACRO` 0x25 | ✅ | ⬜ 未测（偏移表+动作表编码未完整还原） | [keymap.md](keymap.md) §4.4 |',
    '| 13 | 宏写入 | `SET_MACRO` 0x25 | ✅ | 🧪 写宏 "abc"→回读逐字节一致；Insert 打出 abc；mask 0/1/2 语义实测确认 | [keymap.md](keymap.md) §16 |')
rep(F,
    '19. **官方确认 2.4G 模式不支持音乐律动**',
    '19. **宏表格式已还原并真机验证**（[keymap.md](keymap.md) §16）：400B 偏移表（u32 LE 绝对偏移，数据区从 400 起）\n'
    '    + 宏块 `[动作数×2][0][每动作: delay u16LE | HID usage | flags]`，`flags=((actionType&7)<<4)|(isPress?0x80:0)`；\n'
    '    写入按「偏移表 last=0 / 动作区 last=1」两次 `SET_MACRO`；mask 语义 0=单次、1=重复 N 次、2=再按结束（全部实测通过）。\n'
    '20. **槽 97/98 有 LED 驱动通道但无可见光**：真机写红/绿后缓冲回读正确、人眼不可见 → 判为未装配/被遮挡。\n'
    '21. **官方确认 2.4G 模式不支持音乐律动**')
rep(F,
    '**参考实现（scripts/）**：keymap.js（按键编解码，34 断言全绿）',
    '**参考实现（scripts/）**：keymap.js（按键编解码，34 断言全绿）｜**phase3_macro.py（宏表编解码，真机验证）**')
rep(F,
    '剩余项见 [TEST-REPORT.md](TEST-REPORT.md) §13：\n宏写入编码、2.4G 休眠通知、12/24h 重启验证、97/98 LED 物理定位（2.4G 音乐律动已确认不支持，关闭）。',
    '剩余项见 [TEST-REPORT.md](TEST-REPORT.md) §13：\n仅剩 2.4G 休眠/唤醒通知、12/24h 是否重启生效（宏写入、2.4G 音乐律动、97/98 定位均已关闭）。')

K = 'keymap.md'
app(K, '''

---

## 16. 宏表二进制格式（SET_MACRO / GET_MACRO，2026-11-01 真机验证）

> 来源：bundle `PZ`(setMacroData) / `NZ`(getMacroData) 逐字节还原 + 真机写读对比。
> 真机结果：写宏 "abc" 后 `GET_MACRO` 回读**逐字节一致**，绑定 Insert 后能打出 "abc"，mask 0/1/2 全部验证。

### 16.1 逻辑地址空间

- 宏区起始 **逻辑地址 0** = 400 字节目录（100 × u32 LE）
- 动作数据区从逻辑地址 **400** 开始，依次排列各宏块

### 16.2 写入（两次 SET_MACRO）

```
第一次：SET_MACRO, contentSize=400, addrStart=0,   所有包 last=0   → 400 字节目录
第二次：SET_MACRO, contentSize=len(data), addrStart=400, 末包 last=1 → 动作数据块
```

目录项（宏 ID `i`，0..99）：`dir[i*4 .. i*4+3] = offset(u32 LE)`，`offset` = 该宏块在逻辑地址空间中的**绝对偏移**
（第一个宏通常就是 400）。`0` = 该宏为空。

### 16.3 宏块

```
[0..1] = 动作数 × 2   (u16 LE)     ← 解码时 count = value/2
[2..3] = 0
之后每个动作 4 字节：
  [0..1] = delay (ms, u16 LE)
  [2]    = keyCode（HID usage，如 a=0x04、b=0x05、c=0x06；鼠标动作另有约定）
  [3]    = flags = ((actionType & 7) << 4) | (isPress ? 0x80 : 0)
```

- 键盘动作 `actionType = 3`：**按下 → 0xB0，抬起 → 0x30**（一个按键 = 两条动作）
- 鼠标/特殊动作 `actionType ∈ {1,2}`：按下 0x90 / 抬起 0x10（官方 UI 的 mouse 分支）
- 官方 UI 新建一个键盘动作固定插入「按下 + 抬起」两条，delay 默认 10ms

### 16.4 播放方式（按键 4 字节的第 3 字节 param2 / 第 4 字节 param3）

| param2 | 含义 | 真机 |
|---|---|---|
| 0 | 常规：按一次播放一遍 | ✅（"abc" 打出一次） |
| 1 | 重复播放 param3 次 | ✅（param3=3 → "aaa"） |
| 2 | 再按一次结束（连播开关） | ✅（按一下开始连刷、再按结束） |

### 16.5 真机样例（宏 0 = "abc"）

```
目录[0..4] = 90 01 00 00                          # 0x190 = 400
数据(28B)  = 0C 00 00 00                          # 6 个动作 ×2
             0A 00 04 B0  0A 00 04 30             # a 按下/抬起
             0A 00 05 B0  0A 00 05 30             # b
             0A 00 06 B0  0A 00 06 30             # c
键绑定     = 槽103 Insert <- 06 00 00 00          # MACRO page, macroId=0, mask=0
```

清空宏：`SET_MACRO` 写 400 字节全 0（`addrStart=0`，last=1 即可），不再写数据区。
''', '## 16. 宏表二进制格式')

L = 'lighting.md'
app(L, '''

### 补充（2026-11-01 真机）：槽 97 / 98 有驱动通道但无可见光

自定义模式下写 槽97=红、槽98=绿，`GET_ALL_LIGHTS_RGB` 回读确认缓冲里就是红/绿
（`(97,253,0,0)` / `(98,0,253,0)`），但人眼看不到任何绿色灯（红色只有 Fn 充电指示灯）。
⇒ 这两颗是**未装配或被外壳/屏幕遮挡的隐藏 LED 通道**；实际可见可控 LED = 84 颗实体键
（其中 Fn 键被充电指示灯强制红色）+ 品牌 logo 灯（跑马灯，由固件功能控制，不走逐键数据）。
''', '槽 97 / 98 有驱动通道但无可见光')

print('done')
