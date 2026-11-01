# MK87 灯效 / 逐键帧流 / 音乐律动 —— 实现规格 v1

> 设备：AJAZZ MK87（USB `0C45:8047` fw 1.19；2.4G dongle `0C45:FEFE`）。本文只覆盖灯效线。
> 标记：**✅** 真机实测｜**📄** 官方 bundle 静态还原｜**⚠️** 未验证/推断。每块数据都带出处（`文件:行` 或 JSON 路径）。
> 帧层 `AA cmd len addrLo addrHi hdr5 last hdr7 data…`（data@8，MI_02 每包 56B，报文含 report ID=0 共 65B）：`docs/protocol.md:27-50`。
> 写命令 ACK = **原样回显所发 payload**（不是设备状态）：`docs/TEST-REPORT.md:48`。

## 0. 命令速查

`0x13` GET_LED_EFFECT（读 16B）｜`0x23` SET_LED_EFFECT（写 16B：模式/亮度/速度/方向/颜色）｜
`0x14`/`0x24` GET/SET_CUSTOM_LED_DATA（读/写 512B 逐键表）｜`0x33` GET_ALL_LIGHTS_RGB（读 512B 实时色）｜
`0x32` GET_LED_DATA（**逐键帧流写通道**，348B/帧）｜`0x35` SET_MUSIC_DATA（RGB565，MK87 不用）｜
`0x36` CLEAR_LED_DATA（24B 默认）。命令号：`docs/command_enum.txt:5-36`。

## 1. SET_LED_EFFECT 0x23 —— 16B 参数结构
### 1.1 帧与字段
帧 `AA 23 10 00 00 00 01 00 | payload[0..15] | 补 0 至 64B`（len=0x10；无自定义头 → byte6=last=1）
（`docs/lighting-modes.json $.wireFormats.setLedEffect`；官方编码器 `vZ`：`docs/lighting.md:145-155`）。

| 偏移 | 字段（写名/读名） | 取值 | 语义 |
|---:|---|---|---|
| 0 | mode | 0；1..19；20/21；128 | 0=关灯（§1.8） |
| 1 | red / red | 0..255 | 主色 R |
| 2 | green / green | 0..255 | 主色 G |
| 3 | blue / blue | 0..255 | 主色 B |
| 4 | driverSetting | **恒 255** | 写入端硬编码，不吃参数；读回也是 255 |
| 5 | secondaryRed | 0..255 | 副色 R（仅 mode 254 用，MK87 不可见） |
| 6 | secondaryGreen | 0..255 | 副色 G |
| 7 | secondaryBlue | 0..255 | 副色 B |
| 8 | colorMode | 0 / 1 | 0=单色（用[1..3]）；1=RGB（固件配色） |
| 9 | brightness | 1..6 | §1.4 |
| 10 | speed | 1..6 | §1.5 |
| 11 | direction | 0/1/2/3 | 右/左/上/下（§1.6） |
| 12 | effectModeType | 0..3 | 仅 mode 254 用 |
| 13 | — | 0 | 保留恒 0 |
| 14 | checkCodeL | **0xAA** | 固定 |
| 15 | checkCodeH | **0x55** | 固定 |

读回函数 `_Z` 字段名不同（`driverSetting`/`checkCodeL`/`checkCodeH`）但字节位置一致（`docs/lighting.md:158-165`）。
✅ 真机基线回读 `01 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55`（mode=1/白/colorMode=1/亮度 5/速度 3/方向 0；
`docs/protocol.md:114`；`scripts/lighting_ref.js:272-275` 断言同串）。
### 1.2 编码规则
实现要点：`[4]=255`、`[13]=0`、`[14..15]=AA 55` 必须写死；缺省字段按 0；**不做范围校验**（0/7/255 原样入字节）。

### 1.3 19 + 1 个可见模式
MK87 无 `hiddenDefaultEffect`/`customEffect` → 列表 = `defalutLightingModeList` 全 20 项按 `sort` 排序
（`docs/lighting.md:186-209`、`docs/lighting-modes.json $.modeListForThisDevice`）。

| mode | 名称 | i18n | sort | 色 | 速 | 向 | dir默认 | 备注 |
|---:|---|---|---:|:--:|:--:|:--:|---:|---|
| 1 | 静态恒亮 | lighting_icon1 | 10 | ✓ | — | — | 0 | 出厂默认；85 键恒定 ✅ |
| 2 | 单点亮 | lighting_icon2 | 20 | ✓ | ✓ | — | 0 | 1 键跑动 ✅ |
| 3 | 单熄灭 | lighting_icon3 | 30 | ✓ | ✓ | — | 0 | 1 键熄灭 ✅ |
| 4 | 繁星点点 | lighting_icon4 | 40 | ✓ | ✓ | — | 0 | 动效 ✅ |
| 5 | 漫天飞雪 | lighting_icon5 | 50 | ✓ | ✓ | — | 0 | 动效 ✅ |
| 6 | 百花争艳 | lighting_icon6 | 60 | — | ✓ | — | 0 | 自带彩色，无取色器 |
| 7 | 动态呼吸 | lighting_icon7 | 70 | ✓ | ✓ | — | 0 | 动效 ✅ |
| 8 | 光谱循环 | lighting_icon8 | 80 | — | ✓ | — | 0 | 自带彩色 |
| 9 | 彩泉涌动 | lighting_icon9 | 90 | ✓ | ✓ | — | 0 | 动效 ✅ |
| 10 | 多彩纵横 | lighting_icon10 | 100 | ✓ | ✓ | ✓ | **3** | top 箭头（上下） |
| 11 | 随波逐流 | lighting_icon11 | 110 | ✓ | ✓ | ✓ | 0 | left（左右） |
| 12 | 峰回路转 | lighting_icon12 | 120 | ✓ | ✓ | ✓ | 0 | left |
| 13 | 一触即发 | lighting_icon13 | 130 | ✓ | ✓ | — | 0 | 触发类：无按键时仅 1 颗亮 ✅ |
| 14 | 一石二鸟 | lighting_icon14 | 140 | ✓ | ✓ | — | 0 | 触发类 ✅ |
| 15 | 涟漪扩散 | lighting_icon15 | 150 | ✓ | ✓ | — | 0 | 触发类 ✅ |
| 16 | 川流不息 | lighting_icon16 | 160 | ✓ | ✓ | ✓ | 0 | left |
| 17 | 重峦叠嶂 | lighting_icon17 | 170 | ✓ | ✓ | — | 0 | 动效 ✅ |
| 18 | 斜风细雨 | lighting_icon18 | 180 | ✓ | ✓ | ✓ | 0 | left |
| 19 | 来回穿梭 | lighting_icon19 | 190 | ✓ | ✓ | — | 0 | 动效 ✅ |
| **128** | **自定义** | lighting_icon20 | 1280 | ✓(逐键) | — | — | 0 | 见 §3 |
| 20/21 | 自定义族（UI 无名） | — | — | ✓ | — | — | 0 | 不进模式网格，与 128 同表（§3.3） |

死字段 `speedValue`：1..19 中除 mode 1 外全为 3，**全库 0 次读取** → 切模式**不会**改 speed（`docs/lighting.md:216-217,253-254`）。
12 个扩展模式（23/24/25/254/26..33）MK87 **不显示**，不要做 UI（`docs/lighting.md:234-251`）。

### 1.4 brightness（1..6）
✅ 1..6 identity（写=读），`1` = **全灭**（只余 Fn 充电灯），切换无渐变（100ms 内到位）（`docs/TEST-REPORT.md:63-73`）。

| 写入 | 回读 | 实测亮度（mode=1 白 255，85 灯均值 R） | 文档 PWM |
|---:|---:|---:|---:|
| 0 | **255** | 仍亮（85 灯，均值 26.9，偏暗但没灭） | 未定义 |
| 1 | 1 | **全灭**：n_lit=1（只 Fn） | 0 |
| 2 | 2 | 32.8 | 49 |
| 3 | 3 | 64.3 | 97 |
| 4 | 4 | 95.2 | 143 |
| 5 | 5 | 126.7 | 191 |
| 6 | 6 | 168.0 | 253 |

越界**未定义但稳定**（两次写一致，`docs/phase1_diag2.json $.brightness`）：7→11、8→12、9→13、10→14（变暗）、
11→15、12→16、15→19（很暗）、16→1、31→1（全灭）、100→13（全灭）、255→0（=6 亮度）。
⚠️ 口径冲突：`TEST-REPORT.md:69` 正文的 PWM 序列无 JSON 留底，而 `phase1_diag3.json $.brightness_curve` 的回读均值是
2.0/32.8/64.3/95.2/126.7/168.0，两者不能互算。**实现：只用 2..6；1 视作实际关灯；0 与 7..255 一律不发**，
工具侧钳 **2..6**（`docs/TEST-REPORT.md:379`、`docs/FEATURES.md:83-84`）。颜色回读上限 253（写 255→253）。

### 1.5 speed（1..6）
范围来自 `lightingConfig.{min,max}Speed` = 1..6，步进 1（`docs/lighting-modes.json $.lightingConfig`）。
`isShowSpeed=false` 的模式不显示滑条但**字节照发**（`docs/lighting.md:502-503`）。⚠️ speed→实际动画速率未实测，不承诺线性。

### 1.6 direction（0..3）
**0=右 1=左 2=上 3=下**；面板只有 2 键，按 `directionPosition` 决定发 2/3（上/下）还是 1/0（左/右）
（`docs/lighting.md:511-526`）。切模式官方把 direction 重置为 `directionValue ?? 0`（10→3；11/12/16/18→0；其余 0）。

### 1.7 colorMode（只有 0/1）
| 值 | 语义 | 证据 |
|---:|---|---|
| 0 | 单色：用 payload[1..3] | 单选 `lighting_single_color`=0 |
| 1 | RGB/多色：用固件配色，忽略[1..3] | 单选 `RGB`=1；出厂=1 |

⚠️ 任务前提「colorMode 1/2/3」**不成立**：官方只有 0/1（`docs/lighting.md:528-537`、`$.params.colorMode`），
`2/3` 在 bundle 中不存在（`rgbType` 仅透传、MK87 未渲染）。单选显示条件
`currentLighting.value !== 128 && isShowColor && !isShowSecondaryRGB && !isHideColorMode`
（`docs/_lighting_raw/lightingPane-J3Fl9UJi.pretty.js:109`）→ **128 不显示该单选**。
**一碰取色器即强制 colorMode=0**（`docs/lighting.md:536`）：「自定义颜色」= 切单色 + 写 RGB。

### 1.8 关灯 = mode 0（不是亮度 0）
官方关灯就是发 `mode=0`（`docs/lighting.md:479-496`）；`isOpenLight` = mode 是否在模式列表内。
✅ 写 brightness=0 后回读 255 且灯仍亮（`docs/phase1_diag.json $.brightness[0]`）→ **亮度 0 ≠ 关灯**。
✅ `mode=0` 后仍有一颗红灯 = Fn **充电指示灯**，硬件驱动，LED 数据压不掉（`docs/TEST-REPORT.md:66-67`）。

### 1.9 回读规则
- `GET_LED_EFFECT` 16B，真机 ≈ **1.7 ms**（`docs/TEST-REPORT.md:47`）；USB 写→读逐字节一致。
- ACK 只回显请求 → **判成功必须再读 0x13**。
- ⚠️ **2.4G 回读不可靠**：写 `colorMode=0+RGB` 后回读的 color/colorMode 可能与写入不同（显示是对的）
  → 2.4G 不能用 0x13 判写成功，改用 `0x33` 读回 RGB（`docs/TEST-REPORT.md:226-238`、`docs/FEATURES.md:90-91`）。

## 2. 读 / 清命令

**2.1 GET_LED_EFFECT 0x13**：请求 `AA 13 10 00 00 00 01 00`+16B 0（NX 默认 contentSize=16）；响应 data@8 起 16B，
布局同 §1（`docs/protocol_commands.js:360-372`、`probe/ajazz.py:475-484`）。用途：连接初始化必读（`docs/protocol.md:100-105`）、写完回读、页面高亮。

**2.2 GET_ALL_LIGHTS_RGB 0x33（唯一实时颜色读法）**：请求 payload = **512B 索引表** `128×[slot,0,0,0]`（10 包）；
响应 = 512B 扁平 `128×[slot,R,G,B]`（第 0 字节是设备回的 ledId）。真机 ≈ **29 ms**；2.4G 可用（回 85 键）
（`docs/protocol_commands.js:49-68`、`probe/ajazz.py:506-511`、`docs/TEST-REPORT.md:47,235,329`）。
2.4G 变体 `0x37`/`0x3B` 为 RGB565 且不回 slot（`docs/protocol_commands.js:70-130`）。

**2.3 CLEAR_LED_DATA 0x36**：只发 cmd 无 data（NX 默认 contentSize=24 → `AA 36 18 00 00 00 01 00`+24B 0），逐包等 ACK
（`docs/protocol_commands.js:14-24`）。网页端只在点阵屏组件调用，灯效页不用（`docs/lighting.md:328,563`）。
⚠️ 对逐键缓冲的实际影响未实测 → **不要用它关灯**，用 `mode=0`。

**2.4 读回验证三步法**：① 写目标（0x23/0x24/0x32）；② `0x13` 比对 16B（USB 严格，2.4G 只比 mode/RGB）；
③ `0x33` 抽样比对若干 slot 的 RGB（±2，253 上限；帧流场景必做，`probe/phase5_music.py:90-96`）。

## 3. GET/SET_CUSTOM_LED_DATA 0x14/0x24 —— 逐键自定义灯

### 3.1 布局：512B = 128 槽 × 4B
| 字段 | 取值 | 规则 |
|---|---|---|
| idx | 0..127 | **写数组下标**，不是颜色对象的 `ledId`（官方 `bZ`：`i[t]=e`，`docs/lighting.md:332-343`） |
| R/G/B | 0..255 | **无量化**，取色器 sRGB 整数直接落字节 |
| 长度 | 恒 512 | 不足补 0，超过 128 项截断 |
| 索引 | `customLedData[key.value]` | 用槽位号当下标（§3.4） |
| 颜色字段 | 只认 `red/green/blue` | 只给 `r/g/b` 官方写 **0**（`scripts/lighting_ref.js:106-117`） |

分包：`reportCount-8 = 56` 字节/包 → **10 包**，addr 0,56,…,504，逐包等 ACK（cmd=0x24 回显）。
⚠️ 每包 len 字段 = **剩余总长**（非本包长度），与官方 `NX` 一致（`docs/infra.js:66-121`、`probe/ajazz.py:360-425`）。

### 3.2 何时发（官方交互流，可照抄）
初始化：`0x13`(16B) + `0x14`(512B)。点「自定义」格：`0x23` mode=128（direction=`directionValue??0`，余字段沿用当前）。
框选/涂色/换色（自定义模式）：`0x24` **整表覆盖写**（300ms 防抖，可能连发）。换色（普通模式）：`0x23` colorMode=0 + 新 RGB。
重置：`0x24` 全 0（idx 仍写下标）。切到别的模式：`0x23` mode=新模式（`docs/lighting.md:297-328`）。
官方发送前 `pauseLightSync`，MK87 无 `isEnableLightSync` → 空操作，但序列仍是整表覆盖。

### 3.3 mode 20/21/128 共用同一张表
✅ `[20,21,128].includes(mode)` 即官方 `isCustomMode`（`docs/lighting.md:275-291`）；三个模式显示**完全相同**的逐键颜色
（`docs/TEST-REPORT.md:61-62`、`docs/phase1_diag2.json $.customFamily` 三者 first8 一致）→ 实现上**只有一张 512B 表**；
128 是 UI 入口，20/21 是固件侧另两个入口（推测 = Fn+1/2/3 → FUNC 71/72/98，⚠️ 对应关系未验证，`docs/lighting.md:745`）。

### 3.4 槽位图：128 槽 → 87 键 → 86 有驱动 → 84 可见
✅「128 槽全白」实测真有 LED 的槽 = **86 个**（`docs/phase1_diag.json $.physicalSlots.lit`）：

| row | 槽位（keyList 顺序） | 键数 | 说明 |
|---:|---|---:|---|
| 0 | 0–12 (Esc,F1..F12) + **99,100,102** | 16 | 99/100/102 **无灯**（小屏位置） |
| 1 | 16–28 (`` ` `` 1..0 - =) + 92,103,104,105 | 17 | 全亮 |
| 2 | 32–44 (Tab Q..]) + 60,106,107,108 | 17 | 全亮 |
| 3 | 48–59 (Caps A..') + 76 | 13 | 全亮 |
| 4 | 64–75 (L-Shift Z../R-Shift) + 90(↑) | 13 | 全亮 |
| 5 | 80–89,91（含 83 Space、85 Fn、88←、89↓、91→） | 11 | 全亮 |

- 87 键槽 − 3 无灯 = **84 个实体键 LED**；另有 **97/98** 两个「无物理键但有驱动通道」的槽（✓点亮、✓0x33 可读回、✗人眼不可见，
  判为 logo 灯/未装配，`docs/TEST-REPORT.md:80-87,361-362`）→ 86 = 84+97+98。
- 41 个空槽（写色不亮，佐证 idx==槽位）：`13,14,15,29,30,31,45,46,47,61,62,63,77,78,79,93,94,95,96,97,98,101,109..127`
  （`$.ledKeyMap.slotsWithoutKey`；该表把 97/98 记为「无键」，与实测「有灯」不冲突）。
- Fn(85) 的 LED = **充电指示灯**，充电强制红，数据压不掉（`docs/TEST-REPORT.md:66-67`）。
- **LED 序号 = 矩阵槽位号，不要 0..85 连续编号**（`docs/lighting.md:594-618`）。

### 3.5 写入 / 回读
```python
buf = bytearray(512)                                  # colors[slot] = (r,g,b)
for slot, (r, g, b) in colors.items():
    buf[slot*4:slot*4+4] = bytes([slot, r, g, b])
dev.request(0x24, bytes(buf), content_size=512)       # 10 包，逐包等 ACK(0x24)
raw = dev.request(0x14, content_size=512)             # 128×[idx,R,G,B]，idx 是设备存回的第 0 字节
```

参考：`scripts/lighting_ref.js:106-127`（与官方 453 条用例逐字节一致）、`probe/ajazz.py:503-504`。
⚠️ 不要写非法 idx（≠槽位）：设备可能原样存回，显示按 idx 定位（未验证）。

## 4. 逐键帧流 cmd 0x32（SET_MUSIC_DATA / 枚举名 GET_LED_DATA）

**4.1 一帧 = 87 键 × 4B = 348B，7 包**。载荷 = `[slot,R,G,B]` 按 **keyList 行优先、过滤 `disabledLight`**
（MK87 无 disabledLight → 87 键全发，含 99/100/102 无效槽）（`probe/phase4_frames.py:27-36,88-93`、`docs/_music_a.js:3222-3250`）。
分包 `64-8 = 56B/包`（14 键）→ 7 包：第 k 包覆盖 `KEY_ORDER[14k..14k+13]`（addr 0,56,…,336），前 6 包 56B、**末包 12B = 3 键**
（348 = 6×56+12）。每包 65B 报文：

| 偏移 | 值 | 含义 |
|---:|---|---|
| 0 | 0xAA | 固定头 |
| 1 | **0x32** | cmd（把 GET_LED_DATA 复用为写通道） |
| 2 | 0x38 / 0x0C | 本包数据字节数（末包 12） |
| 3–4 | addr LE | 数据起始偏移（0,56,…,336） |
| 5 | **i** | 官方第二参数（MK87 实测恒 0 可用） |
| 6 | **last** | 1 = 本帧末包 |
| 7 | 0 | 保留 |
| 8.. | 4B/键 | `[slot,R,G,B]` 连续 |

✅ 首包 `00 AA 32 38 00 00 00 00 00 | 00 FF FF FF 01 FF FF FF 02 FF FF…`；末包 `… 55 32 0C 50 01 00 01 00`
（len=12、addr=0x0150=336、last=1）（`docs/phase4_frames.json $.runs[0].probe`）。
官方 `TZ`：`docs/protocol_commands.js:862-924`；参考打包：`scripts/music_ref.js:541-564`。

**4.2 激活条件（必须）**：✅ 先 `SET_LED_EFFECT` 到 **mode ∈ {20,21,128}** 再发 0x32 才立即显示；
普通模式（如 mode=1）发帧**完全无效果**（H1 ❌ / H2 ✅）。激活包示例：`mode=128, RGB=FFFFFF, [4]=FF, colorMode=1,
brightness=6, speed=3, [14..15]=AA 55`（`probe/phase5_music.py:56-66`、`docs/TEST-REPORT.md:185-196`）。
⚠️ 帧流亮度是否受 `payload[9]` 影响未验证 → 固定先设 brightness=6。

**4.3 时序预算（20fps）**：单包 ACK **0.5–3 ms**（首包 1.0、末包 2.99）；单帧平均 **15.5 ms**、最大 20.06 ms；
持续 **20.0 fps**（150 帧/7.50s，ACK 1050/1050）；理论上限 ≈ **60 fps**；带宽 140 包/s ≈ 9.1 KB/s
（`docs/phase4_frames.json $.runs[1..2]`、`docs/TEST-REPORT.md:194-195`）。
50ms/帧 − 15.5ms → 余量 ≈34ms；若还要读 `0x33`（29ms）必须放帧间空隙，否则掉帧（§8.2）。

**4.4 停止 / 回落 / 重连**：✅ 停发后 **≈5 s** 固件自动回落到该模式的自定义表，无需任何命令；实测彩色键数
4.50 s 仍 85、5.02 s 变 2 → 窗口 **4.5–5.0 s**，20/21 同（`docs/phase4_timeout.json $.mode_128/.mode_20/.mode_21`）。
设计按 5 s 计时，别自己发恢复命令。⚠️ 重连/切模式（建议策略）：重读 `0x13`；若要继续推帧必须**重发 mode∈{20,21,128}**
再恢复帧流；用户切走后帧流被忽略，前端应检测 `0x13.mode` 重新武装。
不要在帧流中发 `0x24`：帧流写的就是同一块逐键 LED 缓冲（`docs/TEST-REPORT.md:193`）。

**4.5 验证**：帧后读 `0x33`，缓冲颜色 = 帧颜色（`probe/phase5_music.py:90-96`：120 帧/6.00s=19.99fps、ACK 840/840）；
ACK 是请求回显（发 `01 02 03` 回 `01 02 03`，`docs/phase4_diag.json $.probe_echo`）→ 不能当设备状态；白 255 → 253。

**4.6 其它音乐帧通道（MK87 均不用）**：`0x35`（非 USB 通用分支，RGB565 + 4B 头 `AA 35 seq i`，60B/包）；
`0x3C`（2.4G 且 `report=64 && lightingVersion=1`，RGB565，56B/包）——MK87 `lightingVersion=0` 且只有 32B 口 → 不可达
（`docs/protocol_commands.js:880-919`、`docs/music-rhythm.md:121-129`）。⛔ **2.4G 不支持音乐律动**（官方确认；实测三种打包
只出现白脉冲/随机色/竖条纹，`docs/TEST-REPORT.md:239-252`）。

## 5. 音乐律动 v2 算法（自研要复刻的部分）

**5.1 链路**：音频 → AudioContext+AnalyserNode（fftSize 2048、smoothing .75）→ 每 50ms tick 算总振幅 → 渲染器按
`(row,col,amp,phase)` 生成 `grid[6][18]` → 逐键载荷 → 0x32 帧流（`docs/music-rhythm.md:43-50`、`scripts/music_ref.js:628-663`）。

**5.2 采样参数**：音频源 `getDisplayMedia({video:{displaySurface:'monitor'},audio:{echoCancellation:false,
noiseSuppression:false,autoGainControl:false}})`，必须勾「分享系统/标签页音频」；`fftSize=2048`、`smoothingTimeConstant=0.75`；
`hzPerBin = sampleRate/fftSize`（48k → 23.44Hz）；tick **50ms=20fps**（`docs/_music_recon.txt:14`、`docs/_music_a.js:3144-3158`、
`docs/music-constants.json $.audioAnalyzer $.timing`）。

**5.3 总振幅（K7 + Nse）**

```
peak = max(|x|)                    # getFloatTimeDomainData, 2048 点
rms  = sqrt(mean(x²));  raw = 0.6*peak + 0.4*rms
z = raw > z ? z*0.7 + raw*0.3 : z*0.992 + raw*0.008     # 初值/下限 0.01
amp1000 = min(1000, round(raw/z*1000));  if amp1000 <= 5: 0
amp = min(1, amp1000/1000)                              # 渲染器输入
```

静音：连续 **5 tick**（250ms）为 0 才归零（防闪烁）（`docs/music-rhythm.md:61-70`、`scripts/music_ref.js:173-197`、
`docs/_music_a.js:3186-3193`）。

**5.4 三频段（Pse）—— 关键：官方没有逐键频段映射**

```
hzPerBin = sampleRate/fftSize            # getByteFrequencyData
low 20..250Hz ; mid 250..4000Hz ; high 4000..20000Hz
bandRms = sqrt(mean((bin/255)²))         # 区间内
base = max(base*(1-r) + e*r, 0.01)       # r = e>base ? 0.3 : 0.008（每段独立）
v = min(1000, round(e/base*1000));  v <= 5 ? 0
```

（`docs/music-rhythm.md:71-79`、`scripts/music_ref.js:199-233`）
**结论（与任务前提相反）**：`Pse()` 全 bundle 仅 1 处调用（音乐页主循环把它们 `/1000` 存进响应式变量），
而渲染器调用点**只传 grid 与 mode**（`docs/_music_a.js:3292-3317`：`case 13:Se(t); case 14:Ce(t); …`）→
**逐键颜色只由 `(row,col)` + 全局振幅/相位决定，不存在「键→频段」表**。
若确要按频段点键，只能**自研**：18 列按对数分 18 段，`f_i = 20*(20000/20)^(i/17)`，每列亮度取该段 bandRms —— 非官方行为。

**5.5 网格与逐键映射**：`F = keyList.length = 6`；`P = max行键数(17) + maxColOffset(0) = 17`；网格宽 **18**；
`col = 行内下标 + 该行累计 offsetX`；`centerRow=2`、`centerCol=8`。偏移表（`musicConfig.keyOffset`）：
**F1(1)+1、Z(65)+1、↑(90)+2、Spacebar(83)+3、R-Alt(84)+3**（`docs/music-constants.json $.layout`、
`scripts/music_ref.js:110-137`、`docs/_music_a.js:3226-3241`）。载荷顺序 = keyList 行优先、过滤 disabledLight。

**5.6 颜色**：官方 `kV(hue,s,v)`（HSL 三角插值，s/v∈0..1，输出 0..255）：`r=v*s; i=r*(1-|((hue/60)%2)-1|); a=v-r;`
按 6 个 60° 区间取 (r,i,0)/(i,r,0)/(0,r,i)/(0,i,r)/(i,0,r)/(r,0,i) 再各 +a、×255（`scripts/music_ref.js:78-91`）。
色相轮转：每 tick `huePhase += 0.01`（部分渲染器）+ `hueStepPerTick=10`（角度，`re.value+=10`）。
渲染器多取 **S=1、V=1**，强度靠「亮哪些键」而非明暗。背景 `backmode`：0 无 / 1 绿黄红 3 段 / 2 六色段 / 4 中心径向色相 /
5 纯色旋转 / **6..11 = 白红橙黄蓝绿纯色**（`docs/music-rhythm.md:162-171`、`scripts/music_ref.js:253-330`）。

**5.7 灵敏度/平滑**：UI `amplitude` 1..100（默认 50）→ 渲染器平滑系数 `k=amplitude/100` 并缩放亮度/扩散；
attack/decay 0.3/0.008、静音门限 ≤5、静音计数 5 tick 均固定；`backmodebrightness` UI 1..100（v2 声明 10..100）
（`docs/music-constants.json $.uiParams`、`$.musicTabs.musicV1Ui`）。自研「sensitivity」单旋钮建议映射到 `amplitude`。

**5.8 渲染模式表**（`mode` → 官方函数 → 视觉；`docs/music-constants.json $.musicModes`、`docs/_music_a.js:3292-3317`、
`docs/music-rhythm.md:140-160`）：

- **13（默认）** 随曲起舞 / Dance to the Beat · `Se` · 中心同心环扩散，环数随振幅
- **14** 尘埃光漩 / Dust Glow Spiral · `Ce` · 中心 4 色射线旋转
- **15** 蛰伏火山 / Dormant Volcano · `Ee` · 左中右三塔（无位置表→按列兜底）
- **16** 光矢穿心 / Light Arrow Piercing · `De` · 脉冲粒子横条
- **17** 萤火轨迹 / Firefly Trail · `je` · 中心行正弦波 + 拖尾
- **18** 光茧共振 / Light Cocoon Resonance · `Oe` · 边框环绕 + 对角光带
- **19** 音叉振空 / Tuning Fork Vibration · `Ae` · 左右触须抖动
- **20** 曲率遗轨 / Curvature Legacy Track · `Ne` · 右侧向内弯波
- **21** 行波律动 / Row Wave Rhythm · `Pe` · 行波浪柱
- **22** 双心共舞 / Dual Heart Dance · `L` · 内置坐标图案
- **1 / 4** 曲率频阶 / Curvature Frequency Steps · `Fe` · 背景 + 列包络柱
- **100** 屏光联动 / Screen light linkage · 插件 · 交 Music.exe

移植状态：`scripts/music_ref.js` 已精确移植 1/4/13/14/17（其余回落 13），源码在 `docs/_music_b2.js`；
✅ 真机跑通 13/14/17（`docs/TEST-REPORT.md:199-216`）。

**5.9 与 0x32 帧的关系**：`grid → 4B/键载荷 → packUsbMusicFrames()` 即 §4 的帧，**没有额外「level」字节**。
⚠️ 文档冲突：`docs/lighting-modes.json $.wireFormats.musicData.v1Shape` 写「每键 4B + 1B level(0..7)」，与实测 348B/7 包
不符（加 1B 则为 435B/8 包）→ **以实测 4B/键为准**。`i`(byte5) 在 musicDiy 路径按 `ceil(amp*max(rows,cols))` 算
（`docs/_music_a.js:3251-3256`），MK87 实测 **i=0** 即可。

**5.10 可复现伪代码（Python）**

```python
KEY_ORDER = [...]                  # 87 个 slot，按 keyList 行优先（§3.4/§5.5）
def tick(samples, st, mode=13, amplitude=50):
    peak = max(abs(s) for s in samples); rms = math.sqrt(sum(s*s for s in samples)/len(samples))
    raw = 0.6*peak + 0.4*rms
    st.z = st.z*0.7 + raw*0.3 if raw > st.z else st.z*0.992 + raw*0.008
    st.z = max(st.z, 0.01)
    a1000 = min(1000, round(raw/st.z*1000)); a1000 = 0 if a1000 <= 5 else a1000
    st.silence = 0 if a1000 else st.silence + 1
    amp = min(1, a1000/1000) if st.silence < 5 else 0.0
    st.phase = (st.phase + 0.005) % 1; st.hue = (st.hue + 0.005) % 1
    grid = [[(0, 0, 0)]*18 for _ in range(6)]
    lit = max(1, round(amp*8)) if amp >= max(0.01, 0.06 - amp*0.05) else 0    # 简化 mode 13
    for r in range(6):
        for c in range(18):
            d = math.hypot(c-8, r-2); ring = int(d)
            if d < 0.6: grid[r][c] = kv(st.hue*360, 1, 1)
            elif 0 < ring <= lit: grid[r][c] = kv(((st.phase - ring/8 + 1) % 1 + st.hue) % 1*360, 1, 1)
    payload = bytearray()
    for cell in visible_cells(KEY_ORDER):        # (row,col,slot) 行优先
        r, g, b = grid[cell.row][cell.col]; payload += bytes([cell.slot, r, g, b])
    return payload

def packets(payload, i=0, report=64):            # §4.1
    chunk, out = report - 8, []
    for k in range((len(payload) + chunk - 1)//chunk):
        part, addr = payload[k*chunk:(k+1)*chunk], k*chunk
        pkt = bytearray([0, 0xAA, 0x32, len(part), addr & 255, addr >> 8, i,
                         1 if (k+1)*chunk >= len(payload) else 0, 0]) + part
        out.append(bytes(pkt) + bytes(report + 1 - len(pkt)))
    return out                                   # 20fps：每帧 7 包逐包等 ACK
```

完整实现（含 mode 14/17、背景全表、31 项自检）：`scripts/music_ref.js`；离线出帧：`scripts/gen_music_frames.js:42-76`
（WAV → 每 tick 2048 点窗 → JSON）；真机推流：`probe/phase5_music.py`。

## 6. 音乐 v1（Music.exe / 127.0.0.1:9191）—— 仅记录，不可用

MK87 `musicConfig.version = 1`（`docs/lighting.md:118-121`），官方 UI 走 v1：浏览器**不发任何灯数据**，只把参数 + 键盘几何
发给本机助手 `Music.exe`，助手用原生 HID 自己驱动设备；浏览器每 100ms 读助手算好的颜色，仅用于网页预览
（`docs/lighting.md:400-430`、`docs/music-rhythm.md:20-30`）。

| 端点（base `http://127.0.0.1:9191`，timeout 500ms） | 用途 |
|---|---|
| `GET /api/keyboard/musiceffect?param=<mode>&<amp>&<backmode>&<backBright>&1` | 设 v1 参数（300ms 防抖） |
| `GET /api/keyboard/musiceffect/` | 读每键颜色（预览） |
| `GET /api/keyboard/musiceffect/close/` | 关闭 |
| `GET /api/keyboard/layout/base64?data=<b64(JSON)>` | 下发键盘几何 |
| `GET /api/audio/amplitude`、`/api/hardware/info` | 振幅 / 硬件信息 |

**为什么不可用**：① 必须装 Windows 专有 `Music.exe`（`https://config.driveall.cn/music/v2/Music.exe`）；② 官方 UI 强制依赖插件
（`music_mode_error`「请下载插件」、`music_mode_error2`「仅限 win 系统运行」）；③ 助手私有 HID 协议未还原、无法跨平台复刻；
④ v2 的「无插件」按钮被写死 `isTestMode:false` 隐藏（`docs/music-rhythm.md:32-39`）。⇒ 自研一律复刻 v2 浏览器侧链路（§5）。

## 7. 前端所需元数据

**7.1 模式网格（19+1）**：顺序 = §1.3 的 `sort`；每格 = `icon`（carbon/i-ion 类名，`$.modeListForThisDevice[].icon`）+ 中文名 + i18n 键；
点击 → `SET_LED_EFFECT{mode, direction: directionValue??0, 其余沿用当前}`。

| 控件 | 显示条件 | 备注 |
|---|---|---|
| 灯泡总开关 | 恒显 | 关→`mode=0`；开→当前 mode 不在列表则落到第一个模式 |
| 亮度滑条 | `isOpenLight` 时恒显 | 1..6（UI 建议 2..6） |
| 速度滑条 | `currentLighting.isShowSpeed` | 1/128 无；1..6 |
| 方向按钮 | `currentLighting.isShowDirection` | 仅 10/11/12/16/18；10 用上下箭头，余左右 |
| 取色器 | `currentLighting.isShowColor` | 6/8 无（自带彩色） |
| 「单色/RGB」单选 | `mode !== 128 && isShowColor && !isShowSecondaryRGB && !isHideColorMode` | MK87 无 secondary/hideColorMode → 除 6/8/128 外都显示 |
| 「重置」 | 自定义模式 | 写 512B 全 0（idx 保留） |

（`docs/lighting.md:211-219,500-537`、`docs/_lighting_raw/lightingPane-J3Fl9UJi.pretty.js:109,151`）

**7.2 取色器语义**：**colorMode 只有 0/1**（§1.7）；一碰取色器 → 强制 `colorMode=0` + 写 RGB（普通模式走 0x23，自定义模式写进 512B 表）；
颜色**不量化**（0..255 整数直落字节，HEX 用 `parseInt(x,16)` 两位一组）；回读上限 253 → **不要把回读值回填成用户输入**，否则颜色漂移。

**7.3 逐键编辑器**：数据模型 `{slot: [r,g,b]}`（slot ∈ 128 槽，§3.4）；提交时补 0 到 128 槽、idx=slot。
可点击键 = 87 个 keyList 键，其中 **99/100/102 点了没效果**（建议置灰/提示）；**97/98 不在键盘图上**（无物理键），不要画进编辑器。
键盘几何/行列/宽度见 `spec-keymap.md`（`keyList` 的 `row/col/className`）；槽位↔键名对照 87 条见
`docs/lighting-modes.json $.ledKeyMap.table`（含 `ledId/row/col/name/keyCode/key`）。框选/多选、录制复选框（只改选中行为、不发命令）、
整表覆盖 + 300ms 防抖（`docs/lighting.md:309-328`）。

**7.4 参数范围来源**：`lightingConfig = {minBrightness:1,maxBrightness:6,minSpeed:1,maxSpeed:6}`、
`musicConfig = {version:1,maxColOffset:0,keyOffset:[…]}`（`$.lightingConfig`、`$.musicConfig`）→ 从设备配置读，缺失才用默认，别硬编码。

## 8. 性能与并发

**8.1 接口/通道**：USB 主协议 MI_02 = usagePage **0xFF68**（65B，单包写 1–2ms）；USB TFT MI_03 = **0xFF67**（4105B）；
2.4G 协议 MI_03 = **0xFF60**（33B/32B payload）；2.4G 64B 口 0xFF59 无响应（`docs/protocol.md:16-25`、`docs/TEST-REPORT.md:229-238`）。
⚠️ 帧流**只做 USB**（2.4G 官方明确不支持，实测乱码）。

**8.2 同接口读冲突（机制 + 实测）**：一个 HID 接口只有**一条 input 流**，所有请求都从里面按 cmd（可选 addr）匹配自己的响应
（官方 `IX` 装 `inputreport` 监听并按 cmd/addr 过滤：`docs/infra.js:43-54`；Python：`probe/ajazz.py:394-419`）→ 并发请求会**互相偷包**：
B 的超时重试期间 A 的应答可能被 B 读走 → A 超时重发 → 抖动。官方用 `checkAddr` 二次过滤缓解同 cmd 多包交错
（`docs/protocol_commands.js:114`）。实测：`0x33` 单次 ≈29ms > 16.7ms 帧预算；`probe/phase5_music.py` 每 10 帧才读一次
（放帧间空隙），仍 19.99fps / ACK 840/840（`docs/phase5_music.json $.stats`）→ **读可插空，绝不能与帧并发**；一帧 7 包必须串行逐包等 ACK。
⚠️ `driver/docs/design.md:64` 称「实测同接口并发读写冲突，见 TEST-REPORT」，但 TEST-REPORT 无此独立实测记录 → 按「机制成立 + 上述插读实测」表述，勿当量化结论。
规避：① 每设备一把 `RLock` 串行化普通命令；② 帧流线程独占句柄 + 自定节奏；③ 预览读 `0x33` 降到 ≤2fps 或只在停帧后读；④ 按 cmd+addr 双匹配收包。

**8.3 多接口并行**：USB 复合设备 8 个接口，帧流(0xFF68) 与 TFT 上传(0xFF67) 用**不同句柄可并行**（TFT 单包 65ms 受带宽限制，
`docs/TEST-REPORT.md:102-104`）；通知监听（`55 FC…`、唤醒 `A6 FF 01` 在 0xFFFF/reportID=5）放独立线程/句柄，别与灯效抢同一读循环
（`docs/TEST-REPORT.md:273-281`）。2.4G dongle 与 USB 同插同一控制器 → Windows `0xC000009A`，工具只能检测+提示（`docs/TEST-REPORT.md:253-259`）。

**8.4 USB vs 2.4G**：`SET_LED_EFFECT` 写两边都行（显示正确）；`GET_LED_EFFECT` USB 逐字节可信、2.4G 的 color/colorMode 可能≠写入
（不能当判据）；`SET/GET_CUSTOM_LED_DATA` 两边都行（配置共享）；`GET_ALL_LIGHTS_RGB` USB 128 槽、2.4G 回 85 键；
**逐键帧流/音乐律动 只有 USB**（2.4G ⛔）（`docs/TEST-REPORT.md:226-252`、`docs/FEATURES.md:90-91,101-102`）。

## 9. 未验证 / 待定（实现时按此降级）

| # | 项 | 现状 | 建议 |
|---:|---|---|---|
| 1 | brightness 的 PWM 真值 | 文档有 0/49/97/…，无 JSON 留底；JSON 只有回读均值 | 只用 2..6，不依赖精确 PWM |
| 2 | speed 1..6 → 实际速率 | 未实测 | UI 只暴露 1..6，别承诺线性 |
| 3 | mode 20/21 ↔ FUNC 71/72/98 | bundle 只给 `[20,21,128]` | 三个 mode 等价处理 |
| 4 | 写非法 idx（≠槽位） | 未验证 | 永远写 slot |
| 5 | `0x36` 是否清逐键缓冲 | 未验证 | 不用它关灯 |
| 6 | 帧流亮度是否受 payload[9] 影响 | 未验证 | 固定先设 brightness=6 |
| 7 | 帧流中重连/切模式后的恢复 | 部分推断 | 读 0x13 后按 §4.4 重新武装 |
| 8 | 3 频段在 UI 的用途 | 仅 1 处调用，渲染器不读 | 不实现逐键频段映射 |
| 9 | 渲染器 15/16/18/19/20/21/22 | 源码在 `docs/_music_b2.js`，未移植 | 先回落 13 |
| 10 | `driverSetting`(255) 语义 | 未知 | 恒写 255 |

## 10. 参考实现索引

`scripts/lighting_ref.js`（16B/512B 编解码 + 453 条官方对比自检）｜`scripts/music_ref.js`（音乐引擎，31 项自检）｜
`scripts/gen_music_frames.js`（WAV → 帧 JSON）｜`probe/phase1_lighting.py` + `phase1_diag{,2,3}.json`（模式/亮度/自定义灯）｜
`probe/phase4_frames.py` + `phase4_frames.json`（帧流/ACK/帧率）｜`probe/phase4_timeout.py` + `phase4_timeout.json`（回落）｜
`probe/phase5_music.py` + `phase5_music.json`（音乐链路）｜`probe/ajazz.py`（原生 HID 客户端）。
