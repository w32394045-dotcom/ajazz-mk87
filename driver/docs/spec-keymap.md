# MK87 规格 · 改键 / FN 层 / 宏（4B 编码、槽位表、GET/SET_KEY、GET/SET_FN_KEY、宏表）

> 设备：AJAZZ MK87，USB `0C45:8047`（3141/32839），固件 v1.19，`frameVersion=0`（`protocol.md:94`）。本文件只覆盖改键 / FN / 宏。
> **引用约定**：`keymap.md:141` = `docs/keymap.md` 第 141 行；`TC.json` = `docs/keymap-tables.json`；`design.md:106` = `driver/docs/design.md`；
> `bundle@1905191` = 官方 web 驱动 `assets/layout-classic-CMxiG14P.js` 的字符偏移（`TC.json → meta.bundleOffsets`）。
> **可信度**：【实测】真机跑过（`TEST-REPORT.md` + `docs/phase*.json`/`device_dump*.json`）；【代码】官方 bundle/参考实现可复核；**【未验证】** 本仓库无证据。

## 0. 一页速查

| 主题 | 结论 | 证据 |
|---|---|---|
| 数据结构 | **512 B = 128 槽 × 4 B**，每槽 `[pageType,param1,param2,param3]`，字节偏移 = 槽号 × 4；**≥128 = FUNC_V2**，4/5 无实现 | `keymap.md:25,148-169`、`protocol_commands.js:334` |
| 有效槽 | **0..111**（112 个，两层真机全非零）；112..127 为模板残留（全 0，可写不生效） | `keymap_device_report.txt:117`、`device_dump_pre_test.json` |
| `00 00 00 00` | **= 恢复该键出厂默认**；25 个"配置外槽"写 0 被固件保护（保原值） | `TEST-REPORT.md:156-159,345` |
| FUNC vs FUNC_V2 | `frameVersion=0` ⇒ **一律 FUNC(13)**（28 条 FN 动作全是 `0d 00 00 xx`） | `protocol.md:94`、`keymap.md:496` |
| 读 | `GET_KEY 0x12`/`GET_FN_KEY 0x16`，`contentSize=512` → 10 包 = **560 B → 必须 slice(0,512)**；单槽读用 8 B 自定义头，`addr=槽×4` | `protocol_commands.js:331-334,492`、`ajazz.py:526` |
| 写 | `SET_KEY 0x22`/`SET_FN_KEY 0x26`，**只有整块 512 B，没有单槽写** | `keymap.md:554`、`protocol.md:60-64` |
| FN 默认动作 | **28 条**（旧文档写 26 是计数错误，§4.2） | `keymap_device.json → key_vs_fn_diffs`（28 项） |
| 默认矩阵 | `0x1F` 真机**回全 0**（不可用于恢复默认）；`0x1C` 可读且 = 当前 FN 层 | `device_dump_pre_test.json → default_*_matrix` |
| 宏 | 400 B 目录（100×u32 LE）+ 数据区（从 400 起），**两次 SET_MACRO**；设备报 3072 B、官方 UI 按 512 B 校验 | `keymap.md:928-946`、`bundle@1917360` |
| 宏播放 | `param2`：0 常规 / 1 重复 `param3` 次 / 2 再按结束（三种均【实测】） | `TEST-REPORT.md:170-171` |

## 1. 4 字节按键编码

### 1.1 布局与 pageType
| 字节 | 字段 | 说明 |
|---|---|---|
| 0 | `pageType` | 动作页面类型；**≥128 ⇒ FUNC_V2**（最高位是标记位，低 7 位才是数据） |
| 1/2/3 | `param1/2/3` | 语义完全由 pageType 决定（下表）；`pX` 未赋值的字节保持缓冲原值 |

```text
0  DEFAULT      全 0 → 该槽不修改 / 恢复默认
1  MOUSE        p1: 1=鼠标键位图 3=滚轮；p2: 键位图 1左/2右/4中/8后退/16前进，滚轮 1=上/255=下；p3: 0
2  KEYBOARD     p1: 写入恒 0（读取时是修饰位图，遗留态）；p2: HID Keyboard usage；p3: 0
3  CONSUMER_KEY p1=value&0xFF、p2=value>>8（HID Consumer usage，16 位小端）；p3: 0
4  SYSTEM_KEY / 5 EXTRA_FUNCTION  保留页：pX/mX 都无分支，写了会被忽略并告警（勿用）
6  MACRO        p1=macroId(0..99)；p2=mask(0/1/2)；p3=重复次数（仅 mask=1）
7  CB           p1=修饰键1(HID usage)；p2=修饰键2(可 0)；p3=主键(HID usage)
8..12 DKS/MT/TGL/SOCD/RS  磁轴高级键；MK87 配置无 advancedKeysConfig，不要写（keymap.md:435-448）
13 FUNC         p1..p3 = 24 位功能 id 的大端三字节（p1=id>>16, p2=id>>8, p3=id）
14 END          p1/p2=两个键；15 MPT p1/p2/p3=三个键（MK87 无入口）
≥128 FUNC_V2    字节0=0x80|(A>>8)&0x7F、字节1=A&0xFF、字节2=B>>8、字节3=B&0xFF（A=12位槽、B=16位槽）
```

枚举原文：`fX={DEFAULT:0,MOUSE:1,KEYBOARD:2,CONSUMER_KEY:3,SYSTEM_KEY:4,EXTRA_FUNCTION:5,MACRO:6,CB:7,DKS:8,MT:9,TGL:10,SOCD:11,RS:12,FUNC:13,END:14,MPT:15}`（`bundle@1905045`）。**4/5 在 `pX`/`mX` 里没有分支**（命中即 warn），16..127 同样无定义。

### 1.2 编码器（官方 `pX` 逐字，`bundle@1905191`）
```js
function pX(e,t,n,r=''){switch(n.page){
  case'DEFAULT':break;                                    // 一个字节都不写 → 全 0
  case'MOUSE':e[t]=1,e[t+1]=n.param1||1,e[t+2]=n.value||0;break;
  case'KEYBOARD':e[t]=2,e[t+2]=n.value||0;break;           // 不写 byte1
  case'CONSUMER_KEY':let i=n.value||0;e[t]=3,e[t+1]=i&255,e[t+2]=i>>8&255;break;
  case'MACRO':case'MT':case'SOCD':case'RS':case'CB':case'MPT':
      e[t]=fX[n.page],e[t+1]=n.param1||0,e[t+2]=n.param2||0,e[t+3]=n.param3||0;break;
  case'DKS':e[t]=8,e[t+1]=n.value||0;break;   case'TGL':e[t]=10,e[t+1]=n.value||0;break;
  case'FUNC':e[t]=13,e[t+1]=(n.value||0)>>16&255,e[t+2]=(n.value||0)>>8&255,e[t+3]=(n.value||0)&255;break;
  case'FUNC_V2':{let r=0,i=0;n.keyType?(r=n.keyType===2?n.value??0:0,i=n.keyType===1?n.value??0:0)
      :(r=n.param1??0,i=n.param2??0),e[t]=128|r>>8&127,e[t+1]=r&255,e[t+2]=i>>8&255,e[t+3]=i&255;break}
  case'END':e[t]=14,e[t+1]=n.param1||0,e[t+2]=n.param2||0;break;
  default:console.warn(`${r}未知的页面类型: ${n.page}`)}}
```

四条易踩（`keymap.md:192-200`）：① 只写自己负责的字节 ⇒ 写入必须"**全 0 缓冲 + 只写目标槽**"；② `KEYBOARD` 形态恒为
`02 00 usage 00`；③ `MOUSE` 的 `param1` 缺省是 **1**（`||1`）；④ `CONSUMER_KEY` 是小端 16 位。

### 1.3 各写法示例（均可被 `scripts/keymap.js` 复算）
| 动作 | 4 字节 | 说明 |
|---|---|---|
| 主层普通键 | `02 00 04 00` | A（HID 0x04）；`02 00 29 00` = Esc 真机默认 |
| F13（官方表里没有） | `02 00 68 00` | HID 0x68=104；【实测】槽 120 写→回读一致，但 MK87 无此物理键（`TEST-REPORT.md:145`） |
| consumer 音量 + | `03 E9 00 00` | 0x0E9；`03 94 01 00` = 我的电脑(0x194) |
| FUNC 亮度 + | `0D 00 00 0D` | funcId 13；【实测】PgUp 写它背光变亮（`TEST-REPORT.md:147`） |
| FUNC 固件内置 CTRL+C | `0D 00 00 EA` | funcId 234（同族 233/235/265） |
| CB 组合键 Ctrl+C | `07 E0 00 06` | 224=LCtrl、0=无、6=C；`07 E0 E1 06` = Ctrl+Shift+C（两修饰是上限） |
| MACRO M1 | `06 00 00 00` | macroId=0、mask=0、p3=0；`06 00 01 03` = 重复 3 次【实测】 |
| **禁用（推荐）** | `02 00 6F 00` | 官方表里唯一形似"无"的项：`extendChars` 的 `⊠ value=111(0x6F)`；**设备是否真屏蔽【未验证】** |
| **恢复默认** | `00 00 00 00` | 写 0 = 该键出厂默认（§9 坑 1） |

> 「禁用」在官方体系里**没有独立 pageType、也没有 FUNC id**（`⊠` 只是键盘键目录的一个条目，`bundle@1882492`）。备选：绑成无副作用的
> FUNC（如 291「显示当前通道」）——未验证；或用 FUNC 68「屏蔽/开启按键宏」（全局开关，非单键）。**`00 00 00 00` 不是禁用，是恢复默认。**

### 1.4 解码规则（官方 `mX`，`bundle@1906069`）
`pageType≥128 → kX()`；否则 15 路 switch；`pageType=0` 直接 `return undefined`（上层就不给该键挂 `userKey`）。

- **KEYBOARD 两条路径**：`p1!==0` 先按 `extendChars` 的修饰位图查（`L-Ctrl=1,L-Shift=2,L-Alt=4,L-Win=8,R-Ctrl=16,R-Shift=32,R-Alt=64`）；
  `p2!==0` 依次查 `basicChars`(50) → `extendChars`(57) → `jaExtendChars`(5，仅日文)。官方 `pX` 从不写 `p1`，故 `02 01 06 00` 是**有损遗留形态**：
  读回再写会变成 `02 00 E0 00`（`keymap.md:261-266`）。
- **CONSUMER**：`value=p1|p2<<8` 到 `specialChars` 找 `page==='CONSUMER_KEY'`；**FUNC**：`id=(p1<<16)|(p2<<8)|p3` 到 `funcChars` 找名；
  **FUNC_V2**：`A=(byte0&0x7F)<<8|byte1`、`B=byte2<<8|byte3`，两槽独立查表（`<4096` 查 `basicChars`/`extendChars`，否则 `funcV2Chars`），
  **显示名优先槽 B**（`keymap.js:134-153`）。
- 参考实现的**参数约定**：`decodeEntry()` 的 `param1..3` 是**该页语义值**（FUNC_V2 → `param1=A`、`param2=B`），原始字节另存
  `raw`/`rawParam1..3`，以保证 `encodeEntry(decodeEntry(x))===x`（`keymap.md:628-630`，自检 34 条）。

## 2. 槽位表

### 2.1 哪些槽有效
| 范围 | 个数 | 性质 | 证据 |
|---|---|---|---|
| 0..111 | **112** | 有效槽，主层与 FN 层真机全非零；87 个有物理键、25 个无物理键但有固件默认值 | `keymap_device_report.txt:117`、`device_dump_pre_test.json`（非零槽 112） |
| 112..127 | 16 | phantom：全 0，**可写可回读但无任何效果**（槽 120 实测） | `TEST-REPORT.md:145`、`keymap.md:640-642` |

槽号 = `allKeyChars(rX)` 的 `value`（canonical key id）= `keyList` 条目的 `value`，与数组行列位置无关（`keymap.md:77-102`）；
`allKeyChars` 共 121 条（0..120），其中 `VOLINC/VOLDEC/MUTE/Fn/SWITCH/F13` 的 `keyCode` 为空串（无 HID 码、固件自用）。

### 2.2 87 键物理槽位表（`TC.json → mk87KeyboardConfig.keyListRaw` + 真机默认值）
`class` 为原样 UnoCSS 原子类（`—`=无 class=标准 1u；`flex-1`=自适应；`ml-NN/mr-NN/ml-auto/mr-auto`=外边距/靠边；
**像素换算本仓库无证据【未验证】**）。`col`=行内序号（0 基）。真机默认编码 **87/87** 等于 `02 00 <HID> 00`。

```text
slot row.col class            name      HID  default4  |  slot row.col class            name      HID  default4
  0 r0.c0  -                Esc       0x29 02 00 29 00  |    1 r0.c1  ml-15            F1        0x3A 02 00 3A 00
  2 r0.c2  -                F2        0x3B 02 00 3B 00  |    3 r0.c3  -                F3        0x3C 02 00 3C 00
  4 r0.c4  -                F4        0x3D 02 00 3D 00  |    5 r0.c5  ml-auto          F5        0x3E 02 00 3E 00
  6 r0.c6  -                F6        0x3F 02 00 3F 00  |    7 r0.c7  -                F7        0x40 02 00 40 00
  8 r0.c8  -                F8        0x41 02 00 41 00  |    9 r0.c9  ml-auto          F9        0x42 02 00 42 00
 10 r0.c10 -                F10       0x43 02 00 43 00  |   11 r0.c11 -                F11       0x44 02 00 44 00
 12 r0.c12 -                F12       0x45 02 00 45 00  |   99 r0.c13 ml-5             Print     0x46 02 00 46 00
100 r0.c14 -                Scroll    0x47 02 00 47 00  |  102 r0.c15 -                Pause     0x48 02 00 48 00
 16 r1.c0  -                ` ~       0x35 02 00 35 00  |   17 r1.c1  -                1 !       0x1E 02 00 1E 00
 18 r1.c2  -                2 @       0x1F 02 00 1F 00  |   19 r1.c3  -                3 #       0x20 02 00 20 00
 20 r1.c4  -                4 $       0x21 02 00 21 00  |   21 r1.c5  -                5 %       0x22 02 00 22 00
 22 r1.c6  -                6 ^       0x23 02 00 23 00  |   23 r1.c7  -                7 &       0x24 02 00 24 00
 24 r1.c8  -                8 *       0x25 02 00 25 00  |   25 r1.c9  -                9 (       0x26 02 00 26 00
 26 r1.c10 -                0 )       0x27 02 00 27 00  |   27 r1.c11 -                ˉ -       0x2D 02 00 2D 00
 28 r1.c12 -                = +       0x2E 02 00 2E 00  |   92 r1.c13 flex-1           Back      0x2A 02 00 2A 00
103 r1.c14 ml-5             Insert    0x49 02 00 49 00  |  104 r1.c15 -                Home      0x4A 02 00 4A 00
105 r1.c16 -                PgUp      0x4B 02 00 4B 00  |   32 r2.c0  w-22             Tab       0x2B 02 00 2B 00
 33 r2.c1  -                Q         0x14 02 00 14 00  |   34 r2.c2  -                W         0x1A 02 00 1A 00
 35 r2.c3  -                E         0x08 02 00 08 00  |   36 r2.c4  -                R         0x15 02 00 15 00
 37 r2.c5  -                T         0x17 02 00 17 00  |   38 r2.c6  -                Y         0x1C 02 00 1C 00
 39 r2.c7  -                U         0x18 02 00 18 00  |   40 r2.c8  -                I         0x0C 02 00 0C 00
 41 r2.c9  -                O         0x12 02 00 12 00  |   42 r2.c10 -                P         0x13 02 00 13 00
 43 r2.c11 -                [ {       0x2F 02 00 2F 00  |   44 r2.c12 -                ] }       0x30 02 00 30 00
 60 r2.c13 w-23             \ |       0x31 02 00 31 00  |  106 r2.c14 ml-5             Del       0x4C 02 00 4C 00
107 r2.c15 -                End       0x4D 02 00 4D 00  |  108 r2.c16 -                PgDn      0x4E 02 00 4E 00
 48 r3.c0  w-27             Caps      0x39 02 00 39 00  |   49 r3.c1  -                A         0x04 02 00 04 00
 50 r3.c2  -                S         0x16 02 00 16 00  |   51 r3.c3  -                D         0x07 02 00 07 00
 52 r3.c4  -                F         0x09 02 00 09 00  |   53 r3.c5  -                G         0x0A 02 00 0A 00
 54 r3.c6  -                H         0x0B 02 00 0B 00  |   55 r3.c7  -                J         0x0D 02 00 0D 00
 56 r3.c8  -                K         0x0E 02 00 0E 00  |   57 r3.c9  -                L         0x0F 02 00 0F 00
 58 r3.c10 -                ; :       0x33 02 00 33 00  |   59 r3.c11 -                ' "       0x34 02 00 34 00
 76 r3.c12 w-33 mr-auto     Enter     0x28 02 00 28 00  |   64 r4.c0  w-34             L-Shift   0xE1 02 00 E1 00
 65 r4.c1  -                Z         0x1D 02 00 1D 00  |   66 r4.c2  -                X         0x1B 02 00 1B 00
 67 r4.c3  -                C         0x06 02 00 06 00  |   68 r4.c4  -                V         0x19 02 00 19 00
 69 r4.c5  -                B         0x05 02 00 05 00  |   70 r4.c6  -                N         0x11 02 00 11 00
 71 r4.c7  -                M         0x10 02 00 10 00  |   72 r4.c8  -                , <       0x36 02 00 36 00
 73 r4.c9  -                . >       0x37 02 00 37 00  |   74 r4.c10 -                / ?       0x38 02 00 38 00
 75 r4.c11 w-41 mr-auto     R-Shift   0xE5 02 00 E5 00  |   90 r4.c12 ml-5 mr-15       ↑         0x52 02 00 52 00
 80 r5.c0  w-18             L-Ctrl    0xE0 02 00 E0 00  |   81 r5.c1  w-18             L-Win     0xE3 02 00 E3 00
 82 r5.c2  w-18             L-Alt     0xE2 02 00 E2 00  |   83 r5.c3  flex-1           Spacebar  0x2C 02 00 2C 00
 84 r5.c4  w-18             R-Alt     0xE6 02 00 E6 00  |   85 r5.c5  w-18             Fn        0xAF 02 00 AF 00
 86 r5.c6  w-18             Super     0x65 02 00 65 00  |   87 r5.c7  w-18             R-Ctrl    0xE4 02 00 E4 00
 88 r5.c8  ml-5             ←         0x50 02 00 50 00  |   89 r5.c9  -                ↓         0x51 02 00 51 00
 91 r5.c10 -                →         0x4F 02 00 4F 00  |
```

行长度 r0..r5 = 16/17/17/13/13/11（合计 87）。`Fn` 的 DOM code 是 `-1`、HID 0xAF 是固件自用码；`↑` 属 r4、`←↓→` 属 r5（官方表如此）。

### 2.3 25 个「配置外」槽（读-改-写必读）
不在 `keyList` 里但真机有值；官方 `setKeyData` 只遍历 `keyList`、其余写 0 —— **真机 fw1.19 拒绝清零、保持原值**（`TEST-REPORT.md:156-159`）：

```text
13:03 E9 00 00 音量+   14:03 EA 00 00 音量-   15:02 00 98 00 HID 0x98（FN 层是 0D 00 00 2E 旋钮模式切换）
29:02 00 53 NumLock  30:54 KP/  31:55 KP*  45:5F KP7  46:60 KP8  47:61 KP9  61:5C KP4  62:5D KP5  63:5E KP6
77:59 KP1  78:5A KP2  79:5B KP3  93:62 KP0  94:63 KP.  95:58 KPEnter  109:56 KP-  110:57 KP+
96:02 00 7D 00 HID 0x7D   111:02 00 7D 00 HID 0x7D   97:02 00 32 00 NUBS   98:02 00 64 00 IntlBackslash
101:02 00 E7 00 RGUI(右 Win)
```

（未标注前缀的均为 `02 00` + 第四字节 0；完整 hex 见 `keymap_device_report.txt`。`0x98`/`0x7D` 在官方动作表里查不到。）

### 2.4 空槽清单与物理 LED 槽
`isEmptySlot` 共 **41** 个 = 上面 25 个 + phantom 16 个（`TC.json → mk87KeyboardConfig.isEmptySlot`）：

```text
13 14 15 29 30 31 45 46 47 61 62 63 77 78 79 93 94 95 96 97 98 101 109 110 111 112..127
```

含义：**"配置里没有键" ≠ "设备里是 0"**。25 个非零，16 个（112..127）恒 0。
【实测】物理 LED 槽 = **86 个**（≠ 87 键，`TEST-REPORT.md:80-87`）：有键**无 LED** 的是 **99/100/102**（Print/Scroll/Pause 没装，该位置是一块
小屏幕）；无键**有 LED 通道**的是 **97/98**（logo 灯位置，写红/绿可回读但人眼不可见，`TEST-REPORT.md:361-362`）；其余 84 个一致；
**phantom 槽写颜色不点亮** ⇒ 自定义灯 `index == 槽位`。即 LED 集合 = (87 键 − {99,100,102}) ∪ {97,98} = **86**，UI 同时画"可改键/可点亮"
时必须用 87 / 86 两套集合。

## 3. `GET_KEY`(0x12) / `SET_KEY`(0x22)

### 3.1 帧层（主协议 MI_02，`usagePage 0xFF68`，65 B 报文 / 64 B payload）
```text
请求（含 report ID 的实际字节）：00 | AA cmd len addrLo addrHi 00 last 00 | data…   每包 56 B 数据
响应：                          00 | 55 cmd lenOrType addrLo addrHi 00 00 01 | data…
```

官方 `PX`：`c[0]=0xAA,c[1]=cmd,c[2]=len,c[3..4]=addr(LE),c[6]=last,c[8..]=data`，`sendReport(0,buf)` 再前置 report ID（`infra.js:15-21`）。
`len` = 本包**剩余**内容长度（末包 = 剩余字节数）；`maxRetries=3`、读 `timeout=500`（`frameVersion===1` 时 2000）、写 1000（`infra.js:68`）。
⚠️ `protocol.md:33` 的请求示意图漏画了 `len` 字节（图上 byte3/4 标成 addrLo/addrHi）；以 `infra.js:18` + `probe/ajazz.py:342-358` 为准
（addr 在 4..5），该 python 客户端已真机跑通。

### 3.2 读全部 / 读单槽 / 写
```text
读全部：GET_KEY(0x12) 或 GET_FN_KEY(0x16)，payload 空、contentSize=512 → 10 包 × 56 = 560 B → slice(0,512)
读单槽：同一命令 + 8 B 自定义头 AA 12 04 <槽×4 LE> 00 00 00，contentSize=4 → 返回 4 B（FN 层把 12 换成 16）
写    ：SET_KEY(0x22) / SET_FN_KEY(0x26)，contentSize=512、data=512 B → 10 包，逐包 ACK，全链路 ≈ 30 ms
```

- `getKeyData` 原文：`new Uint8Array(r.flatMap(p=>Array.from(p.slice(8)))).slice(0,512)`，再按 `pageType=i[4e],param1=i[4e+1]…` 切 128 槽
  （`protocol_commands.js:331-342`）。**必须 `slice(0,512)`**，否则多出 48 B 伪槽 128..140（`keymap.md:875-879`）。自定义头模式下整包就是
  "8 B 头 + 数据"，不写 len/addr/last（`infra.js:17`、`ajazz.py:526-531`）。
- `setKeyData` 原文：`o=new Uint8Array(512).fill(0); … pX(o, value*4, userKey)` → **只有 keyList 的槽被写，其它留在 0**
  （`protocol_commands.js:675-696`）；**没有"只写一个槽"的命令**（`keymap.md:554`）。
- **ACK = 原样回显所发 payload**（`55 22 …`），只代表收到、不代表生效；写完必须回读 512 B 比对（`protocol.md:197`、`phase3_keys.py:46-56`）。
  不需要"激活"命令：`SET_KEYBOARD_CUSTOM_FUNCTION_ON/OFF(48/49)` 有枚举、全库无调用点（`keymap.md:598`）。
- 【实测】写 103→`02 00 04 00`、105→`0D 00 00 0D`、120→`02 00 68 00` 后回读逐字节一致、其它槽未变（`probe/phase3_keys.py`、`docs/phase3_keys.json`）。

## 4. `GET_FN_KEY`(0x16) / `SET_FN_KEY`(0x26)

### 4.1 与普通层的异同
缓冲区结构**完全相同**（512 B / 128 槽 / 4 B），只是命令字不同；两层是**两份独立数据**，`SET_FN_KEY` 整块覆盖（`keymap.md:504`）。
`fnDisabledKeyIds=[1..12]`（F1..F12 槽号）：官方 UI 在 FN 层把这 12 键置灰，**协议层不阻止写入**（`TC.json → customKeysConfig`）；
`isShowNormalFuncKeys=true` ⇒ **普通层也能直接绑 FUNC 动作**（§3.2 实测印证）。【实测】FN 层 = 出厂默认（`fn_key_matrix` 与
`default_fn_key_matrix` 逐字节相等）。

### 4.2 28 条默认 FN 动作（= 主层/FN 差异槽 = `defaultFnFuncIds`）
| slot | 键 | FN 编码 | funcId | 动作 | slot | 键 | FN 编码 | funcId | 动作 |
|---|---|---|---|---|---|---|---|---|---|
| 15 | （旋钮） | `0D 00 00 2E` | 46 | 旋钮模式切换 | 76 | Enter | `0D 00 00 17` | 23 | 侧灯效果切换 |
| 16 | \` ~ | `0D 00 00 63` | 99 | 自定义灯光录制 | 81 | L-Win | `0D 00 00 16` | 22 | 锁定 Win |
| 17 | 1 ! | `0D 00 00 47` | 71 | 自定义灯光 1 | 83 | Spacebar | `0D 00 00 01` | 1 | **恢复出厂设置** |
| 18 | 2 @ | `0D 00 00 48` | 72 | 自定义灯光 2 | 88 | ← | `0D 00 00 4E` | 78 | 切换灯效方向 |
| 19 | 3 # | `0D 00 00 62` | 98 | 自定义灯光 3 | 89 | ↓ | `0D 00 00 0E` | 14 | 灯光亮度 − |
| 27 | ˉ - | `0D 00 00 10` | 16 | 灯光速度 − | 90 | ↑ | `0D 00 00 0D` | 13 | 灯光亮度 + |
| 28 | = + | `0D 00 00 0F` | 15 | 灯光速度 + | 91 | → | `0D 00 00 0C` | 12 | 灯光颜色切换 |
| 33 | Q | `0D 00 00 02` | 2 | 蓝牙通道 1 | 92 | Back | `0D 00 00 07` | 7 | 查询电量 |
| 34 | W | `0D 00 00 03` | 3 | 蓝牙通道 2 | 103 | Insert | `0D 00 00 27` | 39 | 关闭屏幕 |
| 35 | E | `0D 00 00 04` | 4 | 蓝牙通道 3 | 104 | Home | `0D 00 00 3F` | 63 | GIF 模式 |
| 36 | R | `0D 00 00 05` | 5 | 无线回连 | 106 | Del | `0D 00 00 59` | 89 | LOGO LED ON/OFF |
| 59 | ' " | `0D 00 00 18` | 24 | 侧灯颜色切换 | 107 | End | `0D 00 00 8A` | 138 | 开启屏幕下方按键灯 |
| 60 | \ \| | `0D 00 00 0B` | 11 | 灯光效果切换 | 66 | X | `0D 00 00 11` | 17 | 关闭灯光 |
| 67 | C | `0D 00 00 54` | 84 | 显示屏语言切汉语 | 68 | V | `0D 00 00 55` | 85 | 显示屏语言切英语 |

- **数量订正**：`keymap.md:844` / `FEATURES.md:23` 写 26 条；实测与数据都是 **28 条**（`keymap_device.json → key_vs_fn_diffs` 28 项、
  `keymap_device_report.txt:120-147` 28 行、`fn-layer-decode.json` 28 个非 null `func_id`）。
- 这 28 个 id = MK87 官方 UI「功能」页能选的全部固件动作（`fnFuncIds=[]` ∪ `defaultFnFuncIds`，`keymap.md:493-500`）；全部 `pageType=13`
  ⇒ **MK87 走 FUNC(13)，不要写 FUNC_V2**【实测】FN 层槽 105 写 `0D 00 00 0E`（FUNC 14 亮度−）→ 回读一致、**Fn+PgUp 背光变暗**（`TEST-REPORT.md:148`）。
- FN 层写 0 是否等于"恢复出厂 FN 层"**未验证**（只在主层验证过）；稳妥做法：用 `default_fn_key_matrix` 整块回写。同一槽两层可以是不同页
  （槽 15：主层 KEYBOARD 0x98 / FN 层 FUNC 46）。

## 5. 默认矩阵 `0x1F` / `0x1C`

| 命令 | 值 | 官方驱动调用点 | 真机 |
|---|---|---|---|
| `GET_DEFAULT_KEY_MATRIX` | 31 (0x1F) | 全库无调用（只有枚举） | 【实测】**512 B 全 0**（`device_dump_pre_test.json → default_key_matrix`） |
| `GET_DEFAULT_FN_KEY_MATRIX` | 28 (0x1C) | `getDefaultFnKeyMatrix`(pZ)，`contentSize=512`、`maxRetries=1` | 【实测】可读，**与当前 FN 层逐字节相等** |

- 布局与 `GET_KEY` 同构（512 B = 128×4），解析一致（`keymap.md:751-758`）。`pZ` 产出两份：`defaultFnKeyMatrix`（快照）与
  `defaultFnFuncIds`（功能 id 去重集合 = UI「功能」页白名单）；后者兼容两代：`pageType===13` 取 24 位 id；`pageType>=128 && frameVersion>0`
  时取槽 A / 槽 B 两个码。
- **实现建议**：恢复默认**不要依赖 0x1F**。① 写 `00 00 00 00` 让固件回默认（§9 坑 1/2，仅 keyList 内 87 槽有效）；② 用 keyList 的
  `keyCode` 自拼 `02 00 <keyCode> 00`（87/87 与真机默认一致，§2.2）。

## 6. 宏（`SET_MACRO` 0x25 / `GET_MACRO` 0x15）——【实测】2026-11-01

### 6.1 地址空间与宏块
- 地址 0..**399** = 目录区（100 个 u32 LE，第 i 项对应宏 id i）；地址 **400** 起 = 动作数据区，宏块按写入顺序紧排。`dir[i]` = 该宏块的
  **绝对**逻辑地址；`0` = 该宏为空（官方 PZ 对 `actions.length===0` 的宏直接 `continue`，不占空间）。
- 宏块：`[0..1]=动作数 n×2 (u16 LE，解码 n=值/2)`、`[2..3]=0`，之后 `n×4B = [delay u16LE][keyCode][flags]`，块长 `4+4n`。
  `keyCode`：键盘动作 = HID usage（a=0x04/b=0x05/c=0x06）；鼠标动作 = `specialChars` 的 MOUSE `value`。

### 6.2 `flags` 与 `actionType`
`flags = ((actionType & 7) << 4) | (isPress ? 0x80 : 0)`；解码 `actionType=(flags>>4)&7`、`isPress=!!(flags&0x80)`
（`keymap.md:956`、`protocol_commands.js:403-406`）。但**官方写出的值不是纯公式**：

| actionType | isPress | 官方 PZ 写出 | 公式算得 | 备注 |
|---|---|---|---|---|
| 3（键盘） | ✅ / ❌ | `0xB0` / `0x30` | 0xB0 / 0x30 ✅ | 所有真机样例都是它 |
| 1（鼠标） | ✅ / ❌ | `0x90` / `0x10` | 0x90 / 0x10 ✅ | 官方 UI 手动新增鼠标动作写 1 |
| 2 | ✅ / ❌ | **`0x90` / `0x10`** | 0xA0 / 0x20 ❌ | 官方对 `actionType ∈ {1,2}` **统一**写 0x90/0x10 ⇒ 读回只能得 1，**2 不可表示** |

原始分支（`protocol_commands.js:807`）：`i = (t.actionType===1||t.actionType===2) ? (t.isPress?144:16) : (t.isPress?176:48)`。
**写宏按官方分支实现，别照公式**；读回把 1 当鼠标动作即可。

### 6.3 写入：两次 `SET_MACRO`（顺序固定）
```text
第 1 次：SET_MACRO, contentSize=400,       addrStart=0,   isNeedLastPacketFlag=false → 8 包，全包 last=0（目录）
第 2 次：SET_MACRO, contentSize=len(data), addrStart=400, 末包 last=1               → 动作数据块
```

- 目录这次**故意不置 last**，让设备等后续数据；第 2 次才收尾（`protocol_commands.js:813-822`、`phase3_macro.py:127-130`）。
- 无宏时只发第 1 次（400 B 全 0）；清空宏表用 `SET_MACRO(400B 全 0, addr=0, last=1)` 也行（`phase3_macro.py:183`，实测 ACK 全通、回读无非空项）。
- 数据区是**一整块连续字节**：`data = block(id_a)+block(id_b)+…`，`dir[i] = 400 + 前面所有块长之和`（按数组顺序，不要求 id 升序）。
- `macroId` 必须 `0 ≤ id < 100`，否则官方直接 `throw`（`bundle@1939551`："宏ID超出范围，应为0-99"）。

### 6.4 读回 `GET_MACRO`
| 步骤 | 请求 | 响应 |
|---|---|---|
| ① 目录 | `contentSize=400, addrStart=0` | 400 B（8 包）→ `dir[i*4..]` u32 LE，`0` 跳过 |
| ② 块头 | `contentSize=4, addrStart=dir[i]` | 4 B → `n = u16le(buf[0..1]) / 2` |
| ③ 动作 | `contentSize=n*4, addrStart=dir[i]+4` | `n*4` B → 每 4 B 一个动作 |

（`protocol_commands.js:384-415`；`phase3_macro.py:166-179` 的 `verify` 子命令就是这三步。）

### 6.5 空间预算与校验
| 项 | 值 | 证据 |
|---|---|---|
| 设备上报 | `macroSpaceSize = 3072` B；扣掉 400 B 目录 ⇒ 数据区 **2672 B**；每动作 4 B、每个非空宏另加 4 B 块头 ⇒ 总动作数 ≤ `(2672 − 4×非空宏数)/4`（单宏时 667） | `protocol.md:77`、§6.1 + 算术 |
| 官方 UI 预算 | `macroConfig.isGetMaxMacroSpaceSize ? 设备值 : **512**`；MK87 的 `macroConfig={"isShowFn":true}` ⇒ **UI 按 512 B 校验** | `bundle@1917360`、`TC.json → mk87KeyboardConfig.macroConfig` |
| 官方校验式 | `macros.length*4 + Σactions*4 + reserve > macroSpaceSize` 或 `macros.length >= 100` ⇒ 报"内存不足"并拒绝；新增一对按下/抬起时 `reserve=8` | `bundle@2459278` 的 `ye()` |
| 删除保护 | 已被某键绑定（`userKey.page==='MACRO' && value===id`）的宏**不允许删** | `bundle@2459xxx`、i18n `macro_msg_del` |

> 驱动按 **2672 B** 算真实容量、UI 展示按设备 **3072** 报总容量；官方 UI 的 512 是"保守但会白报内存不足"的历史行为，自研不必跟随。

### 6.6 `mask`（`param2`）与 `param3`
| 写法 | param2 | param3 | 设备行为 | 验证 |
|---|---|---|---|---|
| `06 00 00 00` | 0 常规 | 0 | 按一次播放一遍 | 【实测】Insert 打出 "abc"（`TEST-REPORT.md:169`） |
| `06 00 01 03` | 1 重复播放 | **重复次数** | 连播 3 遍 | 【实测】打出 "aaa"（`TEST-REPORT.md:170`） |
| `06 00 02 00` | 2 再按结束 | 0 | 按一下开始连播、再按一下停 | 【实测】符合预期（`TEST-REPORT.md:171`） |

- `param3` **只在 `param2===1` 时有意义**，其它情况写 0（官方构造式 `param3: S.value===1 ? C.value : 0`，`keymap.md:310-316`），UI 默认 1。
- 下拉 3 项的**值顺序是 0 / 2 / 1**（`bundle@2457016`）；i18n：`macro_mask_select1=常规 / select2=再次按键结束 / select3=重复播放`，
  另有未使用的 `select4=持有`（`assets/i18n/zh.json`）。
- 宏**名字不在设备里**：解码只能得占位 `M{id+1}`，真名由本地 `macroDataList` 覆盖（`keymap.md:319-321`）⇒ 驱动需自己持久化名字与绑定关系。

### 6.7 真机样例：宏 0 = "abc"（`docs/phase3_macro.json`）
```text
目录[0..3] = 90 01 00 00          # 0x190 = 400（绝对地址）
数据 28 B  = 0C 00 00 00          # 6 个动作 ×2
             0A 00 04 B0 0A 00 04 30   0A 00 05 B0 0A 00 05 30   0A 00 06 B0 0A 00 06 30
键绑定     = 槽 103 Insert ← 06 00 00 00
```

默认值：官方 UI 手动新增动作**固定插入"按下+抬起"两条、`delay=10`**，`actionType` 键盘=3、鼠标=1（`bundle@2462829`）；录制模式：
不记间隔 `delay=5`、记间隔用实测值，**保存前把除最后一条外的 `delay` 钳到 ≥5**（`_e()`，`bundle@2458600`）。

## 7. 编码器 / 解码器伪代码（Python，可直接照抄签名）

```python
PAGE = {'DEFAULT':0,'MOUSE':1,'KEYBOARD':2,'CONSUMER_KEY':3,'MACRO':6,'CB':7,'FUNC':13,'END':14,'MPT':15}
FUNC_V2_MIN = 128

def decode_entry(b4, cfg=None):
    """照搬 mX。param1..3 = 语义值（FUNC_V2 → A/B），raw = 原始字节。"""
    t, p1, p2, p3 = b4
    if t >= FUNC_V2_MIN:                                  # 槽A 12 位、槽B 16 位，各自查表，名字优先 B
        a, b = ((t & 0x7F) << 8) | p1, (p2 << 8) | p3
        return {'kind':'func_v2','slotA':a,'slotB':b,'param1':a,'param2':b,
                'name': lookup_v2(b) or lookup_v2(a) or '', 'raw': list(b4)}
    if t == 0:  return {'kind':'default','name':'(默认)','raw':list(b4)}
    if t == 2:  return decode_keyboard(p1, p2, cfg)      # 修饰位图 / HID usage 查表（§1.4）
    if t == 3:  return {'kind':'consumer','value':p1 | (p2 << 8),'raw':list(b4)}
    if t == 6:  return {'kind':'macro','macroId':p1,'mask':p2,'maskParam':p3,'name':f'M{p1+1}','raw':list(b4)}
    if t == 7:  return {'kind':'combo','mod1':p1,'mod2':p2,'key':p3,'name':'CB','raw':list(b4)}
    if t == 13: return {'kind':'func','funcId':(p1<<16)|(p2<<8)|p3,'raw':list(b4)}
    if t == 1:  return {'kind':'mouse','param1':p1 or 1,'value':p2,'raw':list(b4)}
    if t in (14, 15): return {'kind':'multikey','keys':[k for k in (p1,p2,p3) if k],'raw':list(b4)}
    raise ValueError(f'未知页面类型 {t}')               # 4/5/8..12/16..127

def encode_entry(d):
    """照搬 pX：从全 0 开始，只写该页负责的字节。"""
    b, p = bytearray(4), d['page']
    if p == 'KEYBOARD':       b[0], b[2] = 2, d.get('value', 0) & 0xFF
    elif p == 'CONSUMER_KEY': v = d.get('value', 0) & 0xFFFF; b[0], b[1], b[2] = 3, v & 0xFF, v >> 8
    elif p == 'MOUSE':        b[0], b[1], b[2] = 1, d.get('param1') or 1, d.get('value', 0) & 0xFF
    elif p == 'FUNC':         v = d.get('value', 0); b[:] = bytes([13, v>>16 & 0xFF, v>>8 & 0xFF, v & 0xFF])
    elif p in ('MACRO','CB','MPT','END'):                # + DKS/MT/TGL/SOCD/RS（MK87 不用）
        b[0] = PAGE[p]; b[1:4] = bytes([d.get('param1',0)&0xFF, d.get('param2',0)&0xFF, d.get('param3',0)&0xFF])
    elif p == 'FUNC_V2':                                 # keyType 2→槽A、1→槽B；无 keyType 用 param1/2
        kt, v = d.get('keyType'), d.get('value', 0)
        a = v if kt == 2 else (d.get('param1', 0) if kt is None else 0)
        z = v if kt == 1 else (d.get('param2', 0) if kt is None else 0)
        b[:] = bytes([0x80 | (a>>8 & 0x7F), a & 0xFF, z>>8 & 0xFF, z & 0xFF])
    elif p != 'DEFAULT': raise ValueError(p)
    return bytes(b)

# 动作构造器（前端 action → 4 字节）：keyboard(4) 02 00 u 00 / consumer 03 lo hi 00 / func 0D h h h / combo 07 m1 m2 k
keyboard = lambda u:     {'page':'KEYBOARD','value':u}                              # 组合键 CB 就是 combo(m1,m2,key)
consumer = lambda v:     {'page':'CONSUMER_KEY','value':v}                          # usage 表见 §8.1 / TC.json
func     = lambda fid:   {'page':'FUNC','value':fid}                                # 宏引用见 macro(id,mask,n)
combo    = lambda m1, m2, k: {'page':'CB','param1':m1,'param2':m2,'param3':k}
macro    = lambda mid, mask=0, n=0: {'page':'MACRO','param1':mid,'param2':mask,'param3':n if mask==1 else 0}
default  = lambda:       {'page':'DEFAULT'}

def decode_matrix(buf512, cfg=None):
    assert len(buf512) == 512
    return [dict(decode_entry(buf512[i*4:i*4+4], cfg), slot=i) for i in range(128)]

def encode_matrix(patch, base):
    """base = 刚读回的 512 B；只覆盖 patch 的槽。禁止从全 0 开始。"""
    b = bytearray(base)
    for slot, desc in patch.items():
        assert 0 <= slot < 128
        b[slot*4:slot*4+4] = encode_entry(desc)
    return bytes(b)

def encode_action(delay, keycode, action_type=3, is_press=True):
    if action_type in (1, 2): flags = 0x90 if is_press else 0x10    # 官方 PZ 分支，不是通用公式
    else:                     flags = 0xB0 if is_press else 0x30
    return bytes([delay & 0xFF, delay >> 8 & 0xFF, keycode & 0xFF, flags])

def build_macro_payloads(macros):
    """[{'id':0,'actions':[bytes(4)…]}] → (400 B 目录, 数据区)；空 actions 不占空间。"""
    table, data, off = bytearray(400), bytearray(), 400
    for m in macros:
        if not m['actions']: continue
        n = len(m['actions']); blk = bytearray([(n*2) & 0xFF, (n*2) >> 8 & 0xFF, 0, 0])
        for a in m['actions']: blk += a
        table[m['id']*4:m['id']*4+4] = off.to_bytes(4, 'little')
        data += blk; off += len(blk)
    return bytes(table), bytes(data)

def decode_macro_block(block):
    n = int.from_bytes(block[0:2], 'little') // 2
    return [{'delay': int.from_bytes(block[4+i*4:6+i*4], 'little'), 'keyCode': block[6+i*4],
             'isPress': bool(block[7+i*4] & 0x80), 'actionType': (block[7+i*4] >> 4) & 7} for i in range(n)]

def read_key_matrix(kb):    return kb.request(CMD['GET_KEY'],    b'', content_size=512)[:512]
def read_fn_key_matrix(kb): return kb.request(CMD['GET_FN_KEY'], b'', content_size=512)[:512]
def write_key_matrix(kb, m512):
    kb.request(CMD['SET_KEY'], m512, content_size=512, timeout=1.0, retries=1)
    return read_key_matrix(kb)                       # 必须回读校验
```

`lookup_*` 的数据来自 `TC.json → tables.funcChars|funcV2Chars|basicChars|extendChars|specialChars`；`scripts/keymap.js`（34 断言全绿）是
逐字等价官方 `pX`/`mX` 的参考实现，`probe/phase3_macro.py` 是宏表的真机验证实现。

## 8. 前端所需数据

### 8.1 动作分类（`design.md:112` 的 `/api/keymap/actions`）
| 类别 | 条数 | 结构 | 来源 |
|---|---|---|---|
| HID 键盘键 | **107** | `{usage, name}` | `basicChars`(50) + `extendChars`(57)，两表 `value` **无交集** |
| consumer 媒体键 | **17** | `{usage, name, text}` | `specialChars` 中 `page==='CONSUMER_KEY'`（表见 §1.3、`keymap.md:284-302`） |
| 鼠标键 | **7** | `{param1, value, name}` | `specialChars` 中 `page==='MOUSE'`（`param1`：1=按键、3=滚轮；下滚 value=**255**） |
| FUNC 动作 | **28（MK87 可用）/ 292（全表）** | `{id, name}` | `funcChars`；MK87 白名单 = §4.2 的 28 个 id |
| FUNC_V2 动作 | 62（**MK87 不用**） | `{value, keyType, name}` | `funcV2Chars`（仅 `frameVersion=1` 机型，`keymap.md:477-500`） |
| 宏 | **100** 槽（0..99） | `{id, name, actions[]}` | §6；名字只在本地 |
| 禁用 / 恢复默认 | 各 1 | `{type:'disabled'}` → `02 00 6F 00`；`{type:'default'}` → `00 00 00 00` | §1.3 / §9 坑 1 |

107 个 HID usage 分段（`TC.json → tables.basicChars|extendChars`）：

```text
4..29 A..Z（26）   30..39 1..0（10）   45..56 - = [ ] \ ; ' ` , . /（12；49/50/100 都是反斜杠变体）   100 "\"   175 Fn
40 Enter  41 Esc  42 Backspace  43 Tab  44 Space  57 Caps  58..69 F1..F12  70 Print  71 Scroll  72 Pause
73 Ins  74 Home  75 PgUp  76 Del  77 End  78 PgDn  79..82 ←→↓↑  83 NumLock  84 Num/  85 Num*  86 Num-  87 Num+
88 NumEnter  89..98 Num1..Num9,Num0  99 Num.  111 ⊠  224..230 L-Ctrl/L-Shift/L-Alt/L-Win/R-Ctrl/R-Shift/R-Alt
（224..230 这 7 个在 extendChars 里另带 param1 位图 1/2/4/8/16/32/64）
```

> `104` 来自**另一套东西**：官方按键测试页的 104 键 ANSI 表（`KeyboardEvent.code`，`key-events.md:57-66`），与"可指派动作表"无关；
> 可指派动作 = 50 + 57 = **107**（逐条见 `TC.json`，勿写死 104）。

### 8.2 87 键布局（`/api/keymap/layout`，`design.md:106`）
- 6 行，行长度 `[16,17,17,13,13,11]`；每键 `{slot, row, col, className, name, keyCode, default4}`（全量见 §2.2）。
- `x` 建议直接用 `col`（同行排序）；`w` 建议原样套 `className` —— **class → 像素宽度本仓库无证据**（UnoCSS 原子类：`w-NN`=宽、
  `ml-NN`/`mr-NN`=外边距、`flex-1`=自适应、`ml-auto`/`mr-auto`=靠边推；键盘容器 1u 宽度未落盘 ⇒ **【未验证】**）。
- `label` 用 `name`（含上档字符，如 `1 !`、`[ {`）；官方 `name` 混了日/多语言变体（`basicChars[*].jaText/frText/…`），显示名建议前端另建映射。
- 同一份 layout 可复用于按键测试页（`design.md:207`），但注意 §2.4：**可点亮槽 86 ≠ 可改键槽 87**。

## 9. 真机坑清单（改键 / FN / 宏）

1. **`00 00 00 00` = 恢复该键出厂默认**（keyList 内 87 槽写 0 → 回读出厂默认，如槽 103→`02 00 49 00`）；不是"无修改"，更不是禁用（`TEST-REPORT.md:158`）。
2. **25 个"配置外槽"写 0 被固件保护**（保持原值），但**写非零生效**（槽 13 写 `02 00 04 00`、槽 29 写 consumer 音量+ 均验证）⇒ 静态阶段
   "官方写法会丢小键盘/音量"的推断在 fw1.19 上**不成立**，但"整块读-改-写"仍必须做（`TEST-REPORT.md:156-159`）。
3. **读回 560 ≠ 512**：10 包 × 56 B = 560 B，**必须 `slice(0,512)`**，否则多出 48 B 伪槽（`keymap_device_report.txt:1`）。
4. **没有单槽写**：`SET_KEY` 永远整块 512 B；只构造目标槽就发 = 把其余 127 槽写成 0。
5. **宏必须写两次 `SET_MACRO`**：目录这次**全包 last=0**、数据末包 last=1；顺序反/只写一次 → 宏表不完整（§6.3）。
6. **宏 flags 别照公式写 actionType=2**：官方对 1/2 统一写 `0x10/0x90`，公式会写 `0x20/0xA0`；读回只能得 1（§6.2）。
7. **`delay` 有下限**：官方保存时把除最后一条外的 `delay` 钳到 **≥5 ms**；`delay` 是 u16（≤65535）（§6.7）。
8. **官方 UI 的宏空间预算是 512 B（不是 3072）**，别把它的"内存不足"当设备真实容量（§6.5）。
9. **宏名不在设备里**：回读只有 `M{id+1}` 占位；名字与"宏绑在哪个键"必须自己存（§6.6）。
10. **`GET_DEFAULT_KEY_MATRIX(0x1F)` 在 MK87 上回全 0**，不能拿它恢复默认（§5）。
11. **FN 层与主层是两份数据**、命令字不同；`fnDisabledKeyIds=[1..12]` 只是 UI 置灰，协议不拦（§4.1）。
12. **不要写 FUNC_V2**（`frameVersion=0`）；也不要写 pageType 4/5/8..15（无实现或磁轴专用）。
13. **`KEYBOARD` 的 `param1` 是有损遗留态**（读回 `02 01 06 00` 原样写下去会变成 `02 00 E0 00`，§1.4）；
    **`SET_KEY` 的 ACK 只是回显**，不代表生效，每次写完必须回读 512 B 比对（§3.2）。

## 10. 未验证清单

1. 「禁用」的权威写法（`02 00 6F 00` 是否真屏蔽按键）——§1.3。
2. FN 层写 0 是否等于"恢复出厂 FN 层"（只验证过主层）——§4.2。
3. 宏动作里鼠标"向上滚动"（`param1=3,value=1`）与"鼠标左键"（`param1=1,value=1`）在 1 字节 `keyCode` 上**无法区分**，设备按哪个执行——§6.1。
4. `macroSpaceSize=3072` 是否含 400 B 目录（按绝对地址推算应含，数据区 2672 B）——§6.5。
5. `w-NN`/`ml-NN` 的像素换算与键盘容器 1u 宽度——§8.2。
6. `MT` 的 `time/10` 单位、`END`/`MPT` 触发语义（MK87 无入口）；`FUNC_V2` 两槽同时写的执行顺序（MK87 用不到）——`keymap.md:443-451,801,806`。

## 11. 主要证据文件

| 文件 | 用途 |
|---|---|
| `docs/keymap.md` | 4 字节编码主文档（§3 pageType、§4 各页语义、§16 宏格式） |
| `docs/keymap-tables.json` | 7 张动作表全量（490 条）+ `pageTypes` + MK87 `keyListRaw`/`keyListBySlot`/`isEmptySlot` |
| `docs/fn-layer-decode.json` / `docs/keymap_device_report.txt` / `keymap_device.json` | 112 槽逐槽解码 + 真机读回（28 条 FN 差异、560 B 陷阱） |
| `docs/device_dump_pre_test.json` | 原始 512 B 矩阵 ×4（key/fn/default_key/default_fn）+ 400 B 空宏表 |
| `scripts/keymap.js` / `scripts/keymap_decompiled.js` | 逐字等价官方 `pX`/`mX` 的编解码器（34 断言）+ 反编译原文 |
| `probe/phase3_keys.py` / `phase3_macro.py` / `phase3_macro_mask.py` | 改键、宏写入、mask 语义的真机脚本 |
| `probe/ajazz.py` | 帧层与全部读写命令的 python 参考实现（真机跑通） |
| `docs/protocol_commands.js` / `docs/infra.js` / `docs/TEST-REPORT.md` | 官方命令实现（`uZ/fZ/mZ/hZ/NZ/PZ`）、`PX/NX` 帧层、真机结论 |
