# AJAZZ MK87（VID `0x0C45` / PID `0x8047`）按键映射 —— 4 字节条目编码完整还原

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

> **结论先行**：按键映射不是"键码表"，而是 **128 个槽 × 4 字节的「动作描述符」数组**，共 512 字节。
> 第 0 字节是 **pageType（动作页面类型）**，后 3 字节的含义 **完全由 pageType 决定**。
> 4 字节全 0 = 该槽不修改、沿用硬件默认。写入 = 把 512 字节整块 `SET_KEY(34)` 下去（FN 层用 `SET_FN_KEY(38)`）。
>
> 全部规则来自官方网页驱动 bundle `assets/layout-classic-CMxiG14P.js`（3.3 MB，rolldown 打包，未混淆）
> 里的 4 个函数：`pX`（编码）、`mX`（解码）、`kX`（FUNC_V2 解码）、`fX`（pageType 枚举）。
> 本文所有结论都在 `scripts/keymap.js` 里用**逐字移植的官方 pX/mX** 做了逐字节等价自检（34 条断言全绿），
> 详见 §11；并且已用 `docs/keymap_device_report.txt` 的**真机读回数据**做交叉验证（112 条普通层 + 26 条 FN 层
> 逐条回写 100% 一致，见 §15）。

偏移约定：文中的 `@1905191` 指 **bundle 文件内的字符偏移**（0-based；该 bundle 是单行，所以字符偏移 ≈ 字节偏移，仅非 ASCII 段落有差异）。
复现命令见 `scripts/slice.js`、`scripts/tables.js`、`scripts/gen_tables_json.js`。

---

## 0. 一页速查

| 项 | 值 |
|---|---|
| 缓冲区 | 512 字节 = **128 槽 × 4 字节** |
| 槽号 | **canonical key id**（`allKeyChars`/`rX` 的 `value`，0..127），字节偏移 = 槽号 × 4 |
| 条目布局 | `[pageType, param1, param2, param3]` |
| 全 0 | 该槽 = 硬件默认，不修改 |
| 读（全量） | `GET_KEY(18)` / `GET_FN_KEY(22)`，512 字节 |
| 写（全量） | `SET_KEY(34)` / `SET_FN_KEY(38)`，512 字节 |
| 读（单槽） | `GET_KEY(18)` + 8 字节自定义头 `AA 12 04 addrLo addrHi 00 00 00`，返回 4 字节 |
| pageType | 0=DEFAULT 1=MOUSE 2=KEYBOARD 3=CONSUMER_KEY 4=SYSTEM_KEY 5=EXTRA_FUNCTION 6=MACRO 7=CB 8=DKS 9=MT 10=TGL 11=SOCD 12=RS 13=FUNC 14=END 15=MPT **≥128=FUNC_V2** |
| 动作目录表 | 7 张（`basicChars`/`extendChars`/`jaExtendChars`/`specialChars`/`funcChars`/`funcV2Chars`/`allKeyChars`），全量见 `docs/keymap-tables.json` |
| MK87 实际键数 | 87 个槽被占用（41 个空槽） |
| **真机实测** | 普通层 **112/128** 槽非零；其中 **25 个槽不在配置 keyList 里**（小键盘 17 键 + 音量± + 0x98/0x7D/0xE7）；FN 层全部是 `pageType=13(FUNC)`；FN 层 = 出厂默认（差异 0）。详见 §15 |

三个高频编码（均可被 `scripts/keymap.js` 复算）：

```
Ctrl + C          → 07 E0 00 06      (CB 页: L-Ctrl 0xE0 + C 0x06)
媒体键 音量+      → 03 E9 00 00      (CONSUMER_KEY 页: HID consumer 0x0E9)
宏 M1             → 06 00 00 00      (MACRO 页: macroId=0)
F13（协议级）     → 02 00 68 00      (KEYBOARD 页: HID usage 0x68 = 104；官方动作表里没有 F13，见 §9.1)
```

---

## 1. 证据索引（bundle 中的位置）

| 符号 | 作用 | 偏移 | 说明 |
|---|---|---|---|
| `fX` | pageType 枚举 | `@1905045` | 16 个页面类型常量 |
| `pX` | **编码**：action 对象 → 4 字节 | `@1905191` | `function pX(e,t,n,r='')`，e=512缓冲，t=字节偏移 |
| `mX` | **解码**：4 字节 → action 对象 | `@1906069` | `pageType>=128` 转 `kX`，否则 15 路 switch |
| `hX` | 512 字节 → `keyList[].userKey` | `@1906554` | 只对 `keyList` 里存在的槽做解码 |
| `gX` | 512 字节 → `wheelKeys[].userKey` | `@1906769` | 滚轮键专用（MK87 无滚轮键） |
| `kX` | FUNC_V2 解码 | `@1909309` | 双 12/16 位功能码槽 |
| `_X vX yX bX xX SX CX wX TX EX DX AX OX` | 各 pageType 的解码器 | `@1907473…@1909715` | 见 §4 |
| `rX allKeyChars` | 121 条 canonical 键位表 | `@1868425` | `value`=槽号，`keyCode`=HID usage，`keyName`=DOM code |
| `iX basicChars` | 50 条基础字符 | `@1874490` | KEYBOARD 页可选项 |
| `aX extendChars` | 57 条扩展键 | `@1879846` | 含 7 个修饰键（带 `param1` 修饰位图） |
| `cX jaExtendChars` | 5 条日语键 | `@1900008` | 仅 `keyboardLang` 为 ja 时进列表 |
| `oX specialChars` | 24 条（7 MOUSE + 17 CONSUMER_KEY） | `@1882523` | 媒体/鼠标动作 |
| `sX funcChars` | 292 条 `FUNC`(13) 固件动作 | `@1884055` | `value`=24 位功能 id |
| `lX funcV2Chars` | 62 条 `FUNC_V2`(≥128) 固件动作 | `@1900260` | `value` + `keyType`（1=槽B / 2=槽A） |
| `nX` | 以上 7 张表的导出 map | `@1868284` | `allKeyChars/basicChars/extendChars/specialChars/funcChars/funcV2Chars/jaExtendChars` |
| `TU` | MK87 键盘配置（keyList 87 键） | `@1194719` | `vendorId:3141, productId:32839, name:'AJAZZ KEYBOARD'` |
| `WX` | `deviceInit` | `@1916075` | 决定初始化时读哪些数据 |
| `_` | 功能页列表过滤器 | `@2359604` | **决定用 FUNC 表还是 FUNC_V2 表** |

---

## 2. 512 字节 = 128 槽 × 4 字节：槽号语义（关键）

### 2.1 官方代码

```js
// pX 的调用点（setKeyData / fZ，@1925325 附近）
let r = n.value;                       // ← keyList 条目的 value
r >= 0 && r < 128 && n.userKey && pX(o, r * 4, n.userKey, `键盘按键`)
//                                   ↑ 字节偏移 = value*4
```

```js
// getKeyData / uZ：512 字节先切成 128 个 {pageType,param1,param2,param3}
for (let e = 0; e < 128; e++) {
  let t = e * 4, n = i[t], r = i[t+1], o = i[t+2], s = i[t+3];
  a.push({ pageType: n, param1: r, param2: o, param3: s });
}
let o = hX(a, t);                      // ← 再按 keyList 的 value 索引回填 userKey
```

```js
// hX @1906554：注意是 e[a]，a = keyList 条目的 value —— 直接当下标用
hX=(e,t)=>{let n=JSON.parse(JSON.stringify(t.keyList));
  for(let r=0;r<n.length;r++)for(let i=0;i<n[r].length;i++){
    let a=n[r][i].value;
    if(a>=0&&a<e.length&&e[a]){let o=e[a],s=mX(o,t);s&&(n[r][i].userKey=s)}}return n}
```

所以：**`keyList` 条目的 `value` 就是 4 字节条目在 512 缓冲里的下标（槽号）**，与它在数组里的行列位置无关。
同一份 `value` 也用于 `getSingleKeyData` 的地址：`a[3]=i*4&255, a[4]=i*4>>8&255`（8 字节自定义头里的 addr 就是 `槽号×4`）。

### 2.2 MK87 的 87 个槽（`TU` @1194719）

格式：`槽号 名称/HID usage`。

```
row0: 0 Esc/41 · 1 F1/58 · 2 F2/59 · 3 F3/60 · 4 F4/61 · 5 F5/62 · 6 F6/63 · 7 F7/64 · 8 F8/65
      9 F9/66 · 10 F10/67 · 11 F11/68 · 12 F12/69 · 99 Print/70 · 100 Scroll/71 · 102 Pause/72
row1: 16 `~/53 · 17 1/30 · 18 2/31 · 19 3/32 · 20 4/33 · 21 5/34 · 22 6/35 · 23 7/36 · 24 8/37
      25 9/38 · 26 0/39 · 27 -/45 · 28 =/46 · 92 Back/42 · 103 Insert/73 · 104 Home/74 · 105 PgUp/75
row2: 32 Tab/43 · 33 Q/20 · 34 W/26 · 35 E/8 · 36 R/21 · 37 T/23 · 38 Y/28 · 39 U/24 · 40 I/12
      41 O/18 · 42 P/19 · 43 [/47 · 44 ]/48 · 60 反斜杠/49 · 106 Del/76 · 107 End/77 · 108 PgDn/78
row3: 48 Caps/57 · 49 A/4 · 50 S/22 · 51 D/7 · 52 F/9 · 53 G/10 · 54 H/11 · 55 J/13 · 56 K/14
      57 L/15 · 58 ;/51 · 59 '/52 · 76 Enter/40
row4: 64 L-Shift/225 · 65 Z/29 · 66 X/27 · 67 C/6 · 68 V/25 · 69 B/5 · 70 N/17 · 71 M/16
      72 ,/54 · 73 ./55 · 74 斜杠/56 · 75 R-Shift/229 · 90 ↑/82
row5: 80 L-Ctrl/224 · 81 L-Win/227 · 82 L-Alt/226 · 83 Spacebar/44 · 84 R-Alt/230 · 85 Fn/175
      86 Super/101 · 87 R-Ctrl/228 · 88 ←/80 · 89 ↓/81 · 91 →/79
```

**空槽（MK87 的 `keyList` 里没有的 41 个槽）**：
`13,14,15, 29,30,31, 45,46,47, 61,62,63, 77,78,79, 93,94,95, 96,97,98, 101, 109..127`

> ⚠️ **"配置里没有" ≠ "设备里是 0"**。真机读回显示这 41 个槽里有 **25 个是非零的**
> （小键盘整套 `29,30,31,45,46,47,61,62,63,77,78,79,93,94,95,109,110`、`13/14` = 音量±、
> `15` = HID 0x98、`96/111` = HID 0x7D、`97/98` = 反斜杠、`101` = HID 0xE7(RGUI)）。
> 官方驱动写 `SET_KEY` 时只填 `keyList` 里的 87 个槽，**其余一律写 0** —— 也就是说
> **用官方驱动的写法会把那 25 个槽清掉**。改键工具必须走"整块读 → 改目标槽 → 整块写回"，详见 §7.4 与 §15。

> **槽号语义已被机器验证**：这 87 个 `value` 与 `allKeyChars(rX)` 的 `value` 逐个对得上
> （名字或 HID usage 一致，0 例外；见 `scripts/keymap.js` 自检 §8）。
> 例如 `rX[16] = {name:'GAT', value:16, keyCode:53}` ↔ MK87 `16: '` ~' / 53`；`rX[90]={name:'UP',value:90,keyCode:82}` ↔ MK87 `90: ↑/82`。
>
> 这条也能解释别的机型：`QS87`（productId 32836）在槽 **120** 上有一个 `F13` 物理键
> （`{value:120,name:'F13',keyCode:-1}`，`keyCode:-1` = 无 HID 码、由固件处理）。MK87 没有 120 号键。

---

## 3. pageType 全表（`fX` @1905045）

```js
fX={DEFAULT:0,MOUSE:1,KEYBOARD:2,CONSUMER_KEY:3,SYSTEM_KEY:4,EXTRA_FUNCTION:5,MACRO:6,CB:7,
    DKS:8,MT:9,TGL:10,SOCD:11,RS:12,FUNC:13,END:14,MPT:15};
```

| pageType | 名字 | 含义 | 4 字节布局 | pX 实现? |
|---|---|---|---|---|
| 0 | `DEFAULT` | 不修改 / 硬件默认 | `00 00 00 00` | ✅（什么都不写） |
| 1 | `MOUSE` | 鼠标按键 / 滚轮 | `01 param1 value 00`，`param1`=1 按键 / 3 滚轮 | ✅ |
| 2 | `KEYBOARD` | 键盘按键（HID usage） | `02 00 value 00` | ✅ |
| 3 | `CONSUMER_KEY` | 多媒体键（HID consumer，16 位小端） | `03 lo hi 00` | ✅ |
| 4 | `SYSTEM_KEY` | 系统键 | 保留 | ❌ 无分支 |
| 5 | `EXTRA_FUNCTION` | 扩展功能 | 保留 | ❌ 无分支 |
| 6 | `MACRO` | 执行宏 | `06 macroId mask maskParam` | ✅ |
| 7 | `CB` | **Combination 组合键** | `07 mod1 mod2 key` | ✅ |
| 8 | `DKS` | 动态按键（磁轴） | `08 index 00 00`（index 0..63） | ✅ |
| 9 | `MT` | 长按/短按（磁轴高级键） | `09 key1 key2 time/10` | ✅ |
| 10 | `TGL` | Toggle 切换键 | `0A value 00 00` | ✅ |
| 11 | `SOCD` | SOCD（磁轴高级键） | `0B mode key1 key2`（mode 1..4） | ✅ |
| 12 | `RS` | Rapid Trigger 迅洁 | `0C 00 key1 key2`（byte1 恒 0） | ✅ |
| 13 | `FUNC` | **固件内置功能动作（24 位 id）** | `0D id>>16 id>>8 id` | ✅ |
| 14 | `END` | 双键（两个槽位） | `0E key1 key2 00` | ✅ |
| 15 | `MPT` | 多键同发（3 键） | `0F k1 k2 k3` | ✅ |
| **128..255** | `FUNC_V2` | **新一代功能动作页（双功能码槽）** | `0x80｜A>>8, A, B>>8, B` | ✅（独立分支） |

`pageType 4/5` 在 `pX`/`mX` 里都没有 case：命中会走 `default: console.warn('未知的页面类型: ...')`，即**本驱动版本既不写也不读**。
`pageType ≥ 16 且 < 128` 同样无定义（`mX` 会 warn）。`pageType ≥ 128` 一律按 FUNC_V2 解（最高位是标记位，低 7 位才是数据）。

### 3.1 编码器原文（`pX` @1905191，逐字）

```js
function pX(e,t,n,r=``){switch(n.page){
  case`DEFAULT`:break;
  case`MOUSE`:e[t]=1,e[t+1]=n.param1||1,e[t+2]=n.value||0;break;
  case`KEYBOARD`:e[t]=2,e[t+2]=n.value||0;break;
  case`CONSUMER_KEY`:let i=n.value||0;e[t]=3,e[t+1]=i&255,e[t+2]=i>>8&255;break;
  case`MACRO`:case`MT`:case`SOCD`:case`RS`:case`CB`:case`MPT`:
      e[t]=fX[n.page],e[t+1]=n.param1||0,e[t+2]=n.param2||0,e[t+3]=n.param3||0;break;
  case`DKS`:e[t]=8,e[t+1]=n.value||0;break;
  case`TGL`:e[t]=10,e[t+1]=n.value||0;break;
  case`FUNC`:e[t]=13,e[t+1]=(n.value||0)>>16&255,e[t+2]=(n.value||0)>>8&255,e[t+3]=(n.value||0)&255;break;
  case`FUNC_V2`:{let r=0,i=0;
      n.keyType?(r=n.keyType===2?n.value??0:0,i=n.keyType===1?n.value??0:0)
               :(r=n.param1??0,i=n.param2??0),
      e[t]=128|r>>8&127,e[t+1]=r&255,e[t+2]=i>>8&255,e[t+3]=i&255;break}
  case`END`:e[t]=14,e[t+1]=n.param1||0,e[t+2]=n.param2||0;break;
  default:console.warn(`${r}未知的页面类型: ${n.page}`)}}
```

要点（这几点很容易踩坑）：

1. **`pX` 只写它负责的字节**，不写的地方保持缓冲原值。所以"4 字节条目"实际上是"**从全 0 缓冲开始，只写该页面的字段**"的结果（本文的表格都按这个前提给出完整 4 字节）。
2. `KEYBOARD` **不写 `param1`**（`e[t+1]` 没有赋值）→ 写入形态永远是 `02 00 usage 00`。
3. `MOUSE` 的 `param1` 缺省为 **1**（不是 0）：`n.param1||1`。
4. `CONSUMER_KEY` 是**小端 16 位**：`lo, hi`。
5. 第 4 个参数 `r`（`'键盘按键'`/`'FN层按键'`/`'滚轮按键'`）只用于 warn 文案，不参与编码。
6. `MACRO/MT/SOCD/RS/CB/MPT` 是"裸 3 字节"页面：`param1..3` 原样落到 byte1..3，语义由页面决定。
7. `FUNC` 用 24 位大端（`>>16, >>8, &255`），`FUNC_V2` 用"12 位 + 16 位"双槽（下节）。

---

## 4. 各 pageType 的字段语义（编码 ↔ 解码对照）

`mX` @1906069 分派：

```js
mX=(e,t)=>{if(e.pageType>=128)return kX(e);switch(e.pageType){
  case fX.DEFAULT:return;                       // ← 返回 undefined = 该键没有 userKey
  case fX.MOUSE:return _X(e);
  case fX.KEYBOARD:return vX(e,t);
  case fX.CONSUMER_KEY:return yX(e);
  case fX.MACRO:return bX(e);   case fX.CB:return xX(e);
  case fX.DKS:return SX(e);     case fX.MT:return CX(e);
  case fX.TGL:return wX(e);     case fX.SOCD:return TX(e);
  case fX.RS:return EX(e);      case fX.FUNC:return DX(e);
  case fX.END:return AX(e);     case fX.MPT:return OX(e);
  default:console.warn(`未知的页面类型: ${e.pageType}`);return}}
```

### 4.1 `MOUSE`(1) —— 鼠标

| 字节 | 语义 |
|---|---|
| 1 | `param1`：**1 = 鼠标键位图**，**3 = 滚轮** |
| 2 | `value`：`param1=1` 时是键位图（1 左 / 2 右 / 4 中 / 8 后退 / 16 前进）；`param1=3` 时 1=上滚、255(0xFF)=下滚 |
| 3 | 0 |

解码 `_X` @1907473：`param1===1 → oX.find(param1===1 && value===param2)`；`param1===3 → oX.find(param1===3 && value===param2)`。
官方表（`oX`）里 7 条：

```
01 01 01 00  鼠标左键      01 01 02 00  鼠标右键      01 01 04 00  鼠标中键
01 01 10 00  鼠标前进键     01 01 08 00  鼠标后退键
01 03 01 00  鼠标向上滚动   01 03 FF 00  鼠标向下滚动
```

> 注意 `向下滚动` 的 `value` 是 **255**，不是 -1 的补码巧合也不是 2 —— 官方表就这么写
> （`{name:'鼠标向下滚动',value:255,param1:3,text:'mouse_text5',page:'MOUSE'}` @1882788）。

### 4.2 `KEYBOARD`(2) —— 键盘按键

| 字节 | 语义 |
|---|---|
| 1 | 写入时恒 0；**读取**时若 ≠ 0，被当作「修饰键位图」优先解析（见下） |
| 2 | **HID Keyboard/Keypad usage id**（USB HID Usage Tables 第 7 章） |
| 3 | 0 |

解码 `vX` @1907668：

```js
vX=(e,t)=>{let{param1:n,param2:r}=e;
  if(n!==0){let e=aX.find(e=>e.param1===n);if(e)return e}      // ① 修饰键位图形态
  if(r!==0){let e=iX.find(e=>e.value===r);                     // ② 普通基本字符
    if(e||(e=aX.find(e=>e.value===r),e)                        // ③ 扩展键
      ||(t.keyboardLang===`jaText`||t.keyboardLang===`jaTextBr`)&&(e=cX.find(e=>e.value===r),e))return e}
  console.warn(`未找到对应的键盘按键: param1=0x${n.toString(16)}, param2=0x${r.toString(16)}`)}
```

- ②③ 就是正常形态：`param2` = HID usage，`iX`（50 条基础字符）→ `aX`（57 条扩展键）→ `cX`（5 条日语键，仅 ja 语言）。
- ① 是**遗留/只读形态**：`aX` 里 7 个修饰键带 `param1`，构成位图
  `L-Ctrl=1, L-Shift=2, L-Alt=4, L-Win=8, R-Ctrl=16, R-Shift=32, R-Alt=64`。
  形如 `02 01 06 00` 会被解成 `L-Ctrl`（而 `param2=6`=C 被忽略）。官方 `pX` 从不写 `param1`，
  所以**这是有损形态**：读回 `02 01 06 00` 再写下去会变成 `02 00 E0 00`。
  改键软件要么避开，要么自己定义语义（推测：固件在此字段塞修饰位图，但官方 UI 没用到）。

常用 HID usage：`A=4 … Z=29`，`1=30 … 0=39`，`Enter=40, Esc=41, Backspace=42, Tab=43, Space=44, Caps=57, F1=58 … F12=69`，
`Print=70, Scroll=71, Pause=72, Insert=73, Home=74, PgUp=75, Del=76, End=77, PgDn=78`，
`→=79, ←=80, ↓=81, ↑=82`，`L-Ctrl=224, L-Shift=225, L-Alt=226, L-Win=227, R-Ctrl=228, R-Shift=229, R-Alt=230`，`Fn=175`。

### 4.3 `CONSUMER_KEY`(3) —— 多媒体 / 消费类按键

| 字节 | 语义 |
|---|---|
| 1 | `value & 0xFF`（低字节） |
| 2 | `value >> 8`（高字节） |
| 3 | 0 |

`value` = **HID Consumer Page(0x0C) usage id**，16 位小端。解码 `yX` @1908017：`value = param1 | param2<<8`，到 `oX` 里找 `page==='CONSUMER_KEY'`。

官方 17 条（`oX` @1882523）：

| 名称 | value | 编码 |
|---|---|---|
| 我的电脑 | 404 (0x194) | `03 94 01 00` |
| 计算器 | 402 (0x192) | `03 92 01 00` |
| 邮箱 | 394 (0x18A) | `03 8A 01 00` |
| 多媒体 | 387 (0x183) | `03 83 01 00` |
| 播放/暂停 | 205 (0x0CD) | `03 CD 00 00` |
| 播放停止 | 183 (0x0B7) | `03 B7 00 00` |
| 上一首 | 182 (0x0B6) | `03 B6 00 00` |
| 下一首 | 181 (0x0B5) | `03 B5 00 00` |
| 音量 + | 233 (0x0E9) | `03 E9 00 00` |
| 音量 - | 234 (0x0EA) | `03 EA 00 00` |
| 静音 | 226 (0x0E2) | `03 E2 00 00` |
| 主页 | 547 (0x223) | `03 23 02 00` |
| 刷新 | 551 (0x227) | `03 27 02 00` |
| 前进 | 549 (0x225) | `03 25 02 00` |
| 后退 | 548 (0x224) | `03 24 02 00` |
| 收藏 | 554 (0x22A) | `03 2A 02 00` |
| 搜索 | 545 (0x221) | `03 21 02 00` |

### 4.4 `MACRO`(6) —— 执行宏

| 字节 | 语义 |
|---|---|
| 1 | `macroId`（0..99，宏槽号；宏本体是另一块 400 字节偏移表，每动作 4 字节 `[delayLo,delayHi,keyCode,flags]`） |
| 2 | 掩码/播放模式（UI 下拉 3 项，值 `0 / 2 / 1`，i18n 键 `macro_mask_select1/2/3`） |
| 3 | 掩码参数，**仅当 byte2===1** 时取 UI 的数字输入（默认 1），否则 0 |

官方 UI 原文（@2457xxx）：

```js
let e={name:w.value.name,page:`MACRO`,param1:w.value.id,
       param2:S.value,param3:S.value===1?C.value:0,value:w.value.id};
```

解码 `bX` @1908181：`{name:'M'+(param1+1), value:param1, page:'MACRO', param1, param2, param3}` ——
名字是占位 `M1/M2/...`，真实名字在拿到宏列表后由 store 用 `macroList.find(id===userKey.value)` 覆盖
（`u()` @1865xxx 里那段 `if(r.userKey&&r.userKey.page===`MACRO`)` 就是干这个的）。

> **推测**：byte2 的 `0/2/1` 三个枚举官方 i18n 未包含在本 bundle（是独立语言包 chunk），从命名（mask）与
> byte3 只在 `=1` 时生效来看，最可能是"宏触发模式/循环方式"。**改键只需字节级原样保留即可**，不必理解语义。

### 4.5 `CB`(7) —— 组合键（Ctrl+C 这类）

| 字节 | 语义 |
|---|---|
| 1 | 修饰键 1（HID usage，通常是 224..230） |
| 2 | 修饰键 2（同上，可为 0） |
| 3 | 主键（HID usage） |

官方 UI 构造（@2099447）：两个修饰槽只能从 `extendList` 里
`['L-Ctrl','R-Ctrl','L-Shift','R-Shift','L-Alt','R-Alt','L-Win']` 这 7 个里选
（`f=K(()=>r.value.filter(e=>[…].includes(e.name)))`），主键从 `basicList`+`extendList` 剔除修饰键后选；
保存条件 `canSave = (hotKeys[0] || hotKeys[1]) && regularKey` —— **至少一个修饰键 + 恰好 1 个主键**。

```js
i.value[t.row][t.col].userKey={name:`CB`,page:`CB`,
  param1:g.value.hotKeys[0]?.value||0,     // 修饰1
  param2:g.value.hotKeys[1]?.value||0,     // 修饰2
  param3:g.value.regularKey.value},        // 主键
```

解码 `xX` @1908306：`{name:'CB', page:'CB', param1, param2, param3}` —— 纯回传，不再细分。

> **注意**：CB 的 3 个字段都是**单个 HID usage**，不是修饰位图；两个修饰键最多。3 键以上组合/多主键不支持（那属于宏）。

### 4.6 `FUNC`(13) —— 固件内置功能动作（24 位 id）

| 字节 | 语义 |
|---|---|
| 1 | `id >> 16 & 0xFF` |
| 2 | `id >> 8 & 0xFF` |
| 3 | `id & 0xFF` |

解码 `DX` @1909043：`i = param3 + (param2<<8) + (param1<<16)`，然后到 `sX` 里按 `value===i` 找名字。

`sX`（`funcChars` @1884055）**292 条**，`value` 1..292，是"固件认识的功能 id 清单"，
包含大量预置组合键与灯效/系统动作，例如：

| id | 名称 | 编码 |
|---|---|---|
| 1 | 恢复出厂设置 | `0D 00 00 01` |
| 18 | ALT + TAB | `0D 00 00 12` |
| 53 | WIN + D | `0D 00 00 35` |
| 94 | 截屏 WIN+SHF+S | `0D 00 00 5E` |
| 156 | windows / MAC 系统切换 | `0D 00 00 9C` |
| 233 | CTRL+P | `0D 00 00 E9` |
| **234** | **CTRL+C** | `0D 00 00 EA` |
| 235 | CTRL+V | `0D 00 00 EB` |
| 265 | CTRL+X | `0D 00 01 09` |
| 291 | 显示当前通道 | `0D 00 01 23` |
| 292 | 复位灯效 | `0D 00 01 24` |

全 292 条见 `docs/keymap-tables.json` → `tables.funcChars.entries`。

### 4.7 `FUNC_V2`(≥128) —— 双功能码槽（新世代固件）

这是最容易看错的一页。**4 个字节里塞了两个独立的功能码**：

```
byte0 = 0x80 | (slotA >> 8) & 0x7F      ┐
byte1 =        slotA       & 0xFF       ┘ → slotA = (byte0 & 0x7F) << 8 | byte1   (12 位, 0..32767)
byte2 =        slotB >> 8  & 0xFF       ┐
byte3 =        slotB       & 0xFF       ┘ → slotB = byte2 << 8 | byte3            (16 位, 0..65535)
```

- `byte0` 的最高位 `0x80` 是**页面标记位**（这正是"pageType≥128 就是 FUNC_V2"的由来）。
- 编码 `pX`：`keyType===2 → 写 slotA`；`keyType===1 → 写 slotB`；没有 `keyType` → 用 `param1/param2` 当 slotA/slotB。
- 解码 `kX` @1909309：

```js
kX=e=>{let{pageType:t,param1:n,param2:r,param3:i}=e,
  a=(t&127)<<8|n,        // slotA
  o=r<<8|i,              // slotB
  s,c;
  if(a!==0&&a<4096){let e=iX.find(e=>e.value===a),t=aX.find(e=>e.value===a);s=e||t}else s=lX.find(e=>e.value===a);
  if(o!==0&&o<4096){let e=iX.find(e=>e.value===o),t=aX.find(e=>e.value===o);c=e||t}else c=lX.find(e=>e.value===o);
  return{name:c?.name||s?.name||``,text:c?.text||s?.text||``,value:o,page:`FUNC_V2`,param1:a,param2:o}}
```

  → 每个槽**独立查表**：`< 4096` 先查 `iX`/`aX`（即普通键盘按键也能塞进这个页面！），否则查 `lX`。
  名字优先取槽 B（`c?.name||s?.name`）。
- `lX`（`funcV2Chars` @1900260）**62 条**，`value` 4096..28682，`keyType` 决定它落在哪个槽。

| 名称 | value | keyType | 编码 |
|---|---|---|---|
| 恢复出厂设置 | 4096 | 2 | `90 00 00 00` |
| 切换至Windows系统 | 4097 | 2 | `90 01 00 00` |
| 切换至MAC系统 | 4098 | 2 | `90 02 00 00` |
| 切换至Android系统 | 4099 | 2 | `90 03 00 00` |
| 切换IOS系统 | 4100 | 2 | `90 04 00 00` |
| Win/MAC循环切换 | 4101 | 1 | `80 00 10 05` |
| WASD<->方向键 | 4102 | 1 | `80 00 10 06` |
| 查看电量 | 4103 | 1 | `80 00 10 07` |
| 锁定/解锁win键 | 4104 | 1 | `80 00 10 08` |
| 蓝牙通道1 | 8192 | 1 | `80 00 20 00` |
| 蓝牙通道1进入配对 | 8197 | 2 | `A0 05 00 00` |
| 无线回连 | 8202 | 1 | `80 00 20 0A` |
| 无线配对 | 8203 | 2 | `A0 0B 00 00` |
| 主灯光效果切换 | 12288 | 1 | `80 00 30 00` |
| 主灯光亮度+ | 12290 | 1 | `80 00 30 02` |
| 切换上一个界面 | 16384 | 1 | `80 00 40 00` |
| 打开驱动 | 28672 | 1 | `80 00 70 00` |
| 音量 + | 28682 | 1 | `80 00 70 0A` |

**为什么会有 1 和 2 两种 keyType？**（**推测**，但很可信）
观察分布：`keyType:2` 的恰好是 `{4096..4100, 8197..8201, 8203}` —— 恢复出厂、切 OS、蓝牙/无线**配对**，
都属于"整机状态切换/一次性系统动作"；`keyType:1` 则是灯效、媒体、屏幕导航、通道切换等"运行期动作"。
两个槽互相独立 ⇒ 固件很可能把它们看成**两张不同功能表**（系统级 / 运行期），而不是"优先级"或"叠加"。
官方 UI 每个动作只写一个槽，另一槽留 0；协议层面理论上可以两槽同时写（本驱动从没这么干过，**真机未验证**）。

### 4.8 磁轴高级键（MK87 不支持，仅备查）

MK87 的 `TU` 配置里**没有** `advancedKeysConfig`，`routesName` 也不含 `advancedKeys`，
所以下面 4 页在 MK87 上不会出现（`performanceConfig` 也没有）：

| 页 | 布局 | 官方构造点 |
|---|---|---|
| `DKS`(8) | `08 index 00 00`，index 0..63 | `{name:'DKS',page:'DKS',value:C.value.index}` @2081299 |
| `MT`(9) | `09 key1 key2 time/10`（time 默认 40 ⇒ 400ms？——单位见下） | `{page:'MT',param1:d[0].value,param2:d[1].value,param3:d[0].time/10||40}` @2089693 |
| `TGL`(10) | `0A value 00 00` | `{page:'TGL',value:u.value.value}` @2094484 |
| `SOCD`(11) | `0B mode key1 key2`，mode 1..4 | `{page:'SOCD',param1:E.value,param2:本键keyCode,param3:目标键keyCode}` @2068275 |
| `RS`(12) | `0C 00 key1 key2` | `{page:'RS',param1:0,param2:本键keyCode,param3:目标键keyCode}` @2055977 |
| `MPT`(15) | `0F k1 k2 k3` | `{page:'MPT',param1:_[0]?.value||0,param2:_[1]?.value||0,param3:_[2]?.value||0}` @2110947 |
| `END`(14) | `0E key1 key2 00` | `{name:'END',page:'END',param1:d[0].value,param2:d[1].value}` @2105212 |

> 这些页里 `key1/key2` 用的也是 **HID usage**（UI 传入的是 `char.value`），
> 与 §4.2 的 `param2` 同一套编码。`MT` 的 `time/10` 说明固件时间单位是 10ms（**推测**：`||40` 的 40 对应 400ms 量级才合理）。

---

## 5. 动作目录表（7 张）

`nX=t({...})` @1868284 一次性导出：

```js
nX=t({allKeyChars:()=>rX,basicChars:()=>iX,extendChars:()=>aX,funcChars:()=>sX,
      funcV2Chars:()=>lX,jaExtendChars:()=>cX,specialChars:()=>oX})
```

| 导出名 | 局部名 | 条数 | 用途 | 关键字段 |
|---|---|---|---|---|
| `allKeyChars` | `rX` @1868425 | 121 | **canonical 键位表**（槽号定义） | `value`(0..120,槽号) `keyCode`(HID) `keyName`(DOM code) |
| `basicChars` | `iX` @1874490 | 50 | KEYBOARD 页基础字符 | `value`=HID usage |
| `extendChars` | `aX` @1879846 | 57 | KEYBOARD 页扩展键 | `value`=HID；7 个修饰键带 `param1` 位图 |
| `jaExtendChars` | `cX` @1900008 | 5 | 日语专用 | `value`=HID (135..139) |
| `specialChars` | `oX` @1882523 | 24 | MOUSE(7) + CONSUMER_KEY(17) | `value` + `param1`(鼠标子类型) |
| `funcChars` | `sX` @1884055 | 292 | FUNC 页动作 | `value`=24 位功能 id (1..292) |
| `funcV2Chars` | `lX` @1900260 | 62 | FUNC_V2 页动作 | `value` + `keyType`(1/2) |

**UI 上的 4 个标签页**（`characters` 组件 @2074000 起）就是：`basic / extend / special / func`
（`funcV2List` 不作单独标签，它和 `funcList` **二选一**塞进 `func` 标签，见下）。

### 5.1 用 FUNC 还是 FUNC_V2？——由设备的 `frameVersion` 决定

`@2359604`（FN/普通层共用的功能页列表）：

```js
_=K(()=>(i.value?.deviceInfo?.frameVersion===1?p.value:f.value).filter(e=>{
    if(!e.value||a.value===`normal`&&!r.customKeysConfig?.isShowNormalFuncKeys)return;
    let t=r.customKeysConfig?.fnFuncIds||[];
    return[...new Set([...t,...m.value])].includes(e.value)}))
//        p=funcV2List(lX)                  f=funcList(sX)
//        t=配置里写死的 fnFuncIds            m=defaultFnFuncIds（从设备 GET_DEFAULT_FN_KEY_MATRIX 读出来的）
```

结论（**事实**）：

- **`deviceInfo.frameVersion === 1` → 功能页用 `lX` / FUNC_V2(≥128)；否则用 `sX` / FUNC(13)。**
- 功能页只显示 `fnFuncIds ∪ defaultFnFuncIds` 里的 id —— 也就是说**可选项是从设备默认 FN 层读出来的**，
  不是全表铺开。MK87 的 `customKeysConfig.fnFuncIds` 是 `[]`（空），所以完全依赖设备回读
  （`GET_DEFAULT_FN_KEY_MATRIX` → `defaultFnFuncIds`，见 §10）。
- ✅ **MK87 走 FUNC(13)，已由真机数据证实**：`docs/keymap_device_report.txt` 里 FN 层相对主层的 26 个差异条目
  **全部是 `0d 00 00 XX`（pageType=13）**，没有一条 `≥128`。所以 MK87 的 `frameVersion ≠ 1`
  （与 `docs/protocol.md` §4 记录的 `byte30 = 0` 一致）。→ **改键时功能动作请按 §4.6 的 24 位 `FUNC` 编码写，
  不要写 FUNC_V2**（除非真机确认固件也吃 ≥128）。
- 反过来，`defaultFnFuncIds` 的收集逻辑同时兼容两代（13 页取 24 位、≥128 页取双槽），见 §10。

### 5.2 FN 层与普通层的关系

- 两层的缓冲区结构**完全相同**（512 字节 / 128 槽 / 4 字节），只是命令字不同：`GET_KEY(18)/SET_KEY(34)` vs `GET_FN_KEY(22)/SET_FN_KEY(38)`。
- FN 层有"不能改"的键：MK87 `customKeysConfig.fnDisabledKeyIds = [1..12]`（即 F1..F12 的槽号 1..12），
  UI 只做置灰（`disabled: fnDisabledKeyIds.includes(e.value)`），**协议层不阻止写入**。
- `customKeysConfig.isShowNormalFuncKeys = true` ⇒ MK87 的普通层也能直接绑固件功能动作（不必靠 Fn 组合）。

---

## 6. 4 字节全 0 = 「默认 / 未修改」

`mX` 对 `pageType===0` 直接 `return`（undefined）：

```js
case fX.DEFAULT:return;
```

上层 `hX` 于是**不给该键挂 `userKey`**，UI 就显示键盘配置里的默认键名：

```js
let o=e[a], s=mX(o,t); s&&(n[r][i].userKey=s)     // 解不出东西就不写 userKey
```

写入侧对称：`pX` 的 `case 'DEFAULT': break;` 一个字节都不写，全 0 缓冲保持全 0 ⇒ **写 0 = 恢复该键默认**。

三个推论（都很实用）：

1. 条目是**绝对描述**，不是"相对默认的差异"。想把某个键改回默认，就往该槽写 `00 00 00 00`。
2. 空槽（MK87 那 41 个）读回来也是 0，写 0 无害。
3. **`00 00 00 00` 不是"没有数据"，而是"有效值：用默认"** —— 所以 512 字节全 0 是合法状态（整机全默认）。

---

## 7. 改键写入流程（可直接实现）

### 7.1 读

```
全量：  发 GET_KEY(0x12)   contentSize=512  → 512 字节 → 128 槽
       发 GET_FN_KEY(0x16) contentSize=512  → FN 层
单槽：  发 GET_KEY(0x12) + 8 字节自定义头  contentSize=4
        头 = AA 12 04 <addrLo> <addrHi> 00 00 00   其中 addr = 槽号*4
        响应 → 4 字节 → mX
```

`getSingleKeyData`（局部名 `dZ`，`docs/protocol_commands.js` 第 489 行）原文：

```js
let a=new Uint8Array(8).fill(0);
a[0]=170,a[1]=HX.GET_KEY,a[2]=4,a[3]=i*4&255,a[4]=i*4>>8&255;   // i = 槽号
```

> 注意：**没有单槽写**。官方只有整块 512 写入，`SET_KEY` 每次都要给全部 128 槽。

### 7.2 改（内存里做，等价于官方 UI）

```js
// 1) 用 GET_KEY 拿回 512 字节，切成 128 个 {pageType,param1,param2,param3}
// 2) 解码成 keyList[r][c].userKey（= hX 做的事）
// 3) 把目标槽改成新的 action 对象（= 官方各行 handleSave 做的事）
// 4) 用 pX 把「所有」userKey 重新写进一个 512 字节全 0 缓冲
```

### 7.3 写

```
SET_KEY(0x22)  contentSize=512  data=512 字节
SET_FN_KEY(0x26) 同构
```

`setKeyData`（`fZ`）原文（`docs/protocol_commands.js` 第 675 行）：

```js
o=new Uint8Array(512).fill(0);
for(...) { let r=n.value; r>=0&&r<128&&n.userKey&&pX(o,r*4,n.userKey,`键盘按键`) }
a&&Array.isArray(a)&&a.forEach(e=>{ ... pX(o,t*4,e.userKey,`滚轮按键`) });
await NX(e,{cmd:HX.SET_KEY,contentSize:512,data:o,timeout:r===1?2e3:1e3})
```

帧层：`SET_KEY` 512 字节 → 按 32/64 字节报文切包（MK87 MI_02 每包 8 字节头 + 56 字节数据 ⇒ **10 包**），
头格式与应答匹配见 `docs/protocol.md` §2 与 `docs/infra.js`（`PX`/`NX`）。

### 7.4 ⚠️ 三条必须注意的坑

1. **整块覆盖**：`SET_KEY` 写的是完整的 128 槽。缓冲里没被 `pX` 写入的槽会被**写成 0 = 恢复默认**。
   所以必须"先读 512 → 只改目标槽 → 整块写回"，**绝不能只构造目标槽就发**。
   （官方 UI 之所以没这个问题，是因为它的 `keyList` 就是整块读回来的 —— 但见第 2 条，它其实仍有副作用。）
2. **⚠️ 官方写法会清掉 25 个"配置外"槽（真机已验证这些槽非零）**：MK87 的 `keyList` 只覆盖 87 个槽，
   而设备里实际有 **112** 个非零槽：小键盘整套（`29,30,31,45,46,47,61,62,63,77,78,79,93,94,95,109,110`）、
   `13/14` = 音量±、`15` = `02 00 98 00`、`96/111` = `02 00 7D 00`、`97/98` = 反斜杠、`101` = `02 00 E7 00`(RGUI)。
   这 25 个槽**不在 `keyList` 里**，官方 `setKeyData` 会让它们保持 0 → **一次"应用"就可能丢掉小键盘/音量功能**。
   ⇒ 自己实现时必须"整块读回原值 → 只覆盖目标槽 → 整块写回"，**不要**学官方只填 `keyList`。
3. **读回长度陷阱**：512 字节数据按 56 字节/包传输 → **10 包 = 560 字节**（末包补 0）。
   官方代码是 `new Uint8Array(packets.flatMap(p=>p.slice(8))).slice(0,512)` —— **必须 `slice(0,512)`**，
   否则会把 48 个填充 0 当成第 129..140 槽（`docs/keymap_device_report.txt` 首行 `矩阵长度: key=560` 就是这种扁平化结果）。
4. **`FN` 层与普通层是两份独立数据**，别混用命令字；`SET_FN_KEY` 会整块覆盖 FN 层。
   另外，官方从未使用 `SET_KEYBOARD_CUSTOM_FUNCTION_ON(48)/OFF(49)`（枚举里有、全库无调用点），
   所以**不需要"激活自定义按键"这一步**。

---

## 8. 解码/编码工具

`scripts/keymap.js`（无依赖，`node scripts/keymap.js`）：

```js
const { decodeEntry, encodeEntry, decodeMatrix, encodeMatrix } = require('./keymap.js');
decodeEntry([0x07, 0xE0, 0x00, 0x06]);
// { page:'CB', kind:'combo', param1:224, param2:0, param3:6, name:'CB',
//   modNames:['L-Ctrl'], keyName:'C', combo:'L-Ctrl + C', ... }
encodeEntry({ page:'CB', param1:224, param2:0, param3:6 });   // [7, 224, 0, 6]
decodeMatrix(readBack512);      // { slots:[128 项], nonDefault:[...] }
encodeMatrix({ 0:{page:'KEYBOARD',value:104}, 33:{page:'CB',param1:224,param3:6} });  // 512 字节
```

CLI：

```
node scripts/keymap.js                 # 自检（34 条断言）
node scripts/keymap.js examples        # 打印示例编码
node scripts/keymap.js decode 07 E0 00 06
node scripts/keymap.js matrix <512 个 hex 字节>
node scripts/keymap.js find CTRL       # 在动作表里搜名字 → 直接给编码
node scripts/keymap.js encode FUNC_V2 keyType=1 value=12290
```

> **参数约定（重要）**：`decodeEntry` 返回的 `param1/param2/param3` 用的是**该页面的语义值**，
> 不是原始字节 —— 对 FUNC_V2 就是 `param1 = 槽A(12位)`、`param2 = 槽B(16位)`。
> 需要字节视角时用 `raw` / `rawParam1..3`。这样才能保证 `encodeEntry(decodeEntry(x)) === x`。

---

## 9. 示例（精确 4 字节）

### 9.1 示例 A：F13

这个题目有个陷阱：**F13 在官方体系里有三种不同含义，其中只有一种能写进 4 字节**。

1. **作为"物理键槽位"**：`allKeyChars(rX)` 里 `{name:'F13', value:120, keyCode:'', keyName:''}` @1874444 ——
   槽号 **120**，但 `keyCode` 是**空串**（别的机型 `QS87` 写作 `keyCode:-1`），意思是"没有 HID 码，由固件自己处理"。
   MK87 的 87 个键里**没有槽 120**，所以这条对 MK87 无意义。
2. **作为"可指派动作"**：`basicChars(iX)`/`extendChars(aX)` 里**没有 F13**（只有 F1..F12 = 58..69）。
   也就是说**官方 UI 无法把某个键改成"发 F13"**（下拉里根本没这一项）。
   （**推测**：宏动作的 `keyCode` 也只有单字节，104 塞得下；但宏编辑器的可选项同样来自这些表，所以官方路子里也拿不到 F13。
   要 F13 只能走协议层或固件自定义。）
3. **作为"协议级 HID usage"**：`KEYBOARD` 页的 `param2` 就是 HID usage，F13 = `0x68` = 104。于是：

```
02 00 68 00     ← 槽内 4 字节：pageType=2(KEYBOARD), param1=0, param2=0x68(104=F13), param3=0
```

**明确标注**：`02 00 68 00` 是**由协议结构推出、但官方动作表里没有对应项**的编码（**推测**）——
它符合"firmware 收到 KEYBOARD 页就把 param2 当 HID usage 发出去"的模型，但**未在真机验证**，
而且官方 UI 永远不会产生它。验证方法见 §12 第 1 条。

如果你要的是"让某个物理键变成 F13"，**在 MK87 上更稳的等效做法**是把那个槽写成 `KEYBOARD` 的 F1..F12 之外的键，
或改用 `MACRO`。真机若接受 `02 00 68 00`，那就是最直接的答案。

### 9.2 示例 B：Ctrl + C 组合键

官方有**两条**完全不同的实现路径，语义也不同：

**(1) `CB`(7) 组合键页 —— 真正的"修饰键 + 主键"**（推荐）

```
07 E0 00 06
 │  │  │  └─ param3 = 0x06 = HID usage C
 │  │  └──── param2 = 0x00 = 第二个修饰键（无）
 │  └─────── param1 = 0xE0 = 224 = HID usage L-Ctrl
 └────────── pageType = 7 = CB
```

`{name:'CB',page:'CB',param1:224,param2:0,param3:6}`（官方 UI 就是这么构造的，见 §4.5）

变体：
```
07 E1 00 06    L-Shift + C        (0xE1=225)
07 E0 E1 06    L-Ctrl + L-Shift + C
07 E4 00 06    L-Alt + C          (0xE4=226)
```

**(2) `FUNC`(13) 固件内置 CTRL+C —— 只有 id 表里那几条固定组合可用**

```
0D 00 00 EA
 │  │  │  └─ param3 = 0xEA = 234 = sX 里的 "CTRL+C"
 │  │  └──── param2 = 0
 │  └─────── param1 = 0
 └────────── pageType = 13 = FUNC
```
（同族：CTRL+P=233 → `0D 00 00 E9`，CTRL+V=235 → `0D 00 00 EB`，CTRL+X=265 → `0D 00 01 09`）

> 差异（**推测**）：`CB` 由固件**实时合成**按键上报（按住才按住），`FUNC 234` 更像固件的"一键宏/一次触发"。
> 若要做"按住 Ctrl 再按 C"的语义，用 `CB`。

### 9.3 示例 C：媒体键（音量 +）

```
03 E9 00 00
 │  │  │  └─ param3 = 0
 │  │  └──── param2 = 0x00  (高字节)
 │  └─────── param1 = 0xE9  (低字节)   → value = 0x00E9 = 233
 └────────── pageType = 3 = CONSUMER_KEY
```
`233 (0xE9)` = HID Consumer `Volume Increment`。其它见 §4.3 表。

### 9.4 示例 D：宏

```
06 00 00 00        ← 槽内 4 字节：MACRO, macroId=0, mask=0, maskParam=0  （= 宏 M1，默认播放方式）
06 06 01 03        ← MACRO, macroId=6 (M7), mask=1, maskParam=3
```
`{name:<宏名>, page:'MACRO', param1:macroId, param2:mask, param3:maskParam, value:macroId}`
宏本体不在 512 里：`GET_MACRO(21)` 前 400 字节 = 100 个宏的地址表，每动作 4 字节 `[delayLo,delayHi,keyCode,flags]`。

### 9.5 示例 E：FUNC_V2（若真机 frameVersion=1）

```
90 00 00 00    → 槽A=0x1000=4096 (恢复出厂设置, keyType:2)   槽B=0
80 00 70 0A    → 槽A=0                 槽B=0x700A=28682 (音量 +, keyType:1)
A0 05 00 00    → 槽A=0x2005=8197 (蓝牙通道1进入配对, keyType:2) 槽B=0
```

### 9.6 示例 F：一个完整的"改 3 个键"的 512 字节片段

假设把 `Esc(槽0)` 改成 F13、`Q(槽33)` 改成 Ctrl+C、`W(槽34)` 改成音量+，其余不动：

```
offset  0x00: 02 00 68 00     ← 槽0   Esc  → KEYBOARD F13
offset  0x84: 07 E0 00 06     ← 槽33  Q    → CB Ctrl+C     (33*4 = 132 = 0x84)
offset  0x88: 03 E9 00 00     ← 槽34  W    → CONSUMER 音量+ (34*4 = 136 = 0x88)
其余 125 槽：保持读回值（或全 0 = 恢复默认）
```

`scripts/keymap.js` 的 `encodeMatrix({0:{page:'KEYBOARD',value:104},33:{...},34:{...}})` 可直接生成这 512 字节，
自检 §6 已用官方 `pX` 逐槽写的结果比对过，**逐字节一致**。

---

## 10. 「默认键位矩阵」`GET_DEFAULT_KEY_MATRIX` / `GET_DEFAULT_FN_KEY_MATRIX`

| 命令 | 值 | 驱动里用了吗 | 说明 |
|---|---|---|---|
| `GET_DEFAULT_KEY_MATRIX` | 31 (0x1F) | ❌ **只有枚举定义，全库无调用点** | 布局**推断**与 `GET_KEY` 相同（128×4，同样的 `{pageType,param1,param2,param3}`） |
| `GET_DEFAULT_FN_KEY_MATRIX` | 28 (0x1C) | ✅ `getDefaultFnKeyMatrix`（局部名 `pZ`） | `contentSize=512`，`maxRetries=1`，失败会被 catch 成空数组 |

`pZ` 原文（`docs/protocol_commands.js` 第 145 行）：

```js
let r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),i=[],a=[];
for(let e=0;e<128;e++){let t=e*4,n=r[t],o=r[t+1],s=r[t+2],c=r[t+3];
  if(i.push({pageType:n,param1:o,param2:s,param3:c}),n===13){        // ① FUNC 页
    let e=o<<16|s<<8|c;  e>0&&a.push(e) }
  if(BX.deviceStorage.deviceInfo?.frameVersion>0&&n>=128){           // ② FUNC_V2 页
    let e=(n&127)<<8|o, t=s<<8|c;  e>0&&a.push(e), t>0&&a.push(t) }}
BX.tempData.defaultFnKeyMatrix=i; BX.tempData.defaultFnFuncIds=a;
```

- **布局**：与 `GET_KEY` 完全一致（512 字节 = 128×4）：`[pageType, param1, param2, param3]`。
- **用途**：`i` → `defaultFnKeyMatrix`（默认 FN 层快照）；`a` → `defaultFnFuncIds`（**默认 FN 层用到的功能 id 集合**）。
  后者是 UI「功能」标签页的可选项白名单（§5.1），也是"这个机型到底支持哪些固件功能动作"的权威答案。
- **重要**：`defaultFnFuncIds` 既收 `pageType===13` 的 24 位 id，**也**收 `pageType>=128` 的槽 A / 槽 B 两个码
  （`frameVersion>0` 时）。所以同一段逻辑能同时兼容两代功能页。
- `GET_DEFAULT_KEY_MATRIX(31)` 在本驱动版本里**完全没被调用**，想用它的返回值只能自己发命令；
  按 `SET_KEY` 的同构性推断（**推测**）它返回的也是 512 字节 128×4 的"出厂普通层键位快照"，用途应是"恢复默认"。

---

## 11. 与官方实现的等价性自检（`node scripts/keymap.js`）

自检不是"我自己觉得对"，而是把官方实现**逐字抄进来当参照**再比对：

| # | 检查 | 结果 |
|---|---|---|
| 1 | 14 个固定字节向量（含本文所有示例） | ✅ |
| 2 | **`encodeEntry` ≡ 官方 `pX`**：490 个动作表条目逐个比对输出字节 | ✅ 490/490 一致 |
| 3 | 485 个条目 `encode → decode → encode` 字节稳定 | ✅ 0 例外 |
| 4 | 名字解析抽查（A / L-Ctrl / 音量+ / 我的电脑 / CTRL+C / 复位灯效 / 恢复出厂设置 / 鼠标右键 / M1） | ✅ |
| 5 | 20000 次随机"可达"编码往返稳定 | ✅ 0 例外 |
| 6 | 512 字节矩阵：`encodeMatrix` ≡ 官方"全 0 缓冲 + 逐槽 pX"；`decodeMatrix` 可逆 | ✅ |
| 7 | `GET_DEFAULT_FN_KEY_MATRIX` 解析（13 页 24 位 id / ≥128 页双槽） | ✅ |
| 8 | MK87 87 个槽号 ≡ `allKeyChars` 的 `value` | ✅ 0 例外 |
| 9 | **真机数据**：112 条普通层 + 26 条 FN 层逐条 `decode → encode` 回写 | ✅ 0 例外（`scripts/verify_vs_device.js`，见 §14） |

第 2 条最关键：`referencePX` 就是从 bundle `@1905191` 原样复制过来的函数体，
所以"我们的编码器 = 官方编码器"是被**逐字节证明**的，而不是靠肉眼读代码。

历史记录（说明自检真能抓错）：第一版把 `decodeEntry` 的 `param1/param2` 当成原始字节返回，
自检第 3/5/6 条立刻报 `62/485`、`2580/20000` 失败（FUNC_V2 的槽 B 被错写成 `param2` 单字节）；
改成"语义值约定"（FUNC_V2 的 `param1`=槽A、`param2`=槽B）后全部转绿。

---

## 12. 仍不确定 / 需要真机验证的清单

| # | 问题 | 现状 | 怎么验证 |
|---|---|---|---|
| 1 | `02 00 68 00`（KEYBOARD + HID 0x68 = F13）真机是否接受？ | **推测**成立（协议结构如此），官方表无此项 | 写单槽 → 用键盘测试页/`GET_KEY` 回读；观察按该键是否上报 F13 |
| 2 | MK87 的 `frameVersion` 到底是 0 还是 1（决定 FUNC vs FUNC_V2） | ✅ **已定**：真机 FN 层 26 条全是 `pageType=13` ⇒ 走 FUNC(13)（与 protocol.md 的 `byte30=0` 一致）；仍可直接读 byte30 复核 | 见 §14.1 / §5.1 |
| 3 | `FUNC_V2` 两个槽能否**同时**写（槽A+槽B） | 官方从不这么干，**未验证**；MK87 既然走 FUNC 页，这条优先级已降低 | 写 `90 00 70 0A`（槽A=4096, 槽B=28682）看固件执行哪个/都执行 |
| 4 | `keyType` 1 vs 2 的真实语义 | **推测**：两套功能码表（系统级 / 运行期） | 需要固件侧信息；改键时按官方表照抄 `keyType` 即可 |
| 5 | `MACRO` 的 `param2`(0/2/1) 与 `param3` 语义 | 官方 i18n 缺失，**推测**是播放/循环模式 | 在官方 UI 里把三种都试一遍，读回 4 字节对照 |
| 6 | `KEYBOARD` 页 `param1`（修饰位图）的写入语义 | 官方**只读不写**，写入有损 | 手写 `02 01 06 00` 看是否产生 Ctrl+C；若是，则可绕过 CB 做组合键 |
| 7 | `pageType 4/5`（`SYSTEM_KEY`/`EXTRA_FUNCTION`） | 本驱动**无实现** | 可尝试盲写，风险未知（建议不做） |
| 8 | `END`(14) 的真机语义（两个键同时？顺序？） | `param1/param2` 两个 HID usage，**语义未知** | MK87 无此入口，优先级最低 |
| 9 | 写 `SET_KEY` 后是否需要额外"生效"命令 | 驱动无（`SET_KEYBOARD_CUSTOM_FUNCTION_ON/OFF` 有枚举无调用） | 写完直接回读 + 敲键验证 |
| 10 | 槽 13/14/15/29../101../109..111 这些"配置外"槽在固件里到底驱动什么 | 真机**确实非零**（§14.2），但 MK87 没这些物理键，可能是共用模板的残留/复用（15 号在 FN 层是"旋钮模式切换"，`0x98`/`0x7D` 官方表都查不到） | 写回原值即可保证不破坏；想探究可逐槽改一个可见功能（如 F13）试 |
| 11 | `SET_KEY` 写入是否**真的**会清掉那 25 个槽（还是固件忽略未映射槽） | **推测**会清（代码如此），真机未做"写入后回读全 512"的对照 | 写一次全 0 之外的值后回读 512，看 13/14/29 是否变 0 —— **这条必须测，别把音量键刷没了** |

---

## 13. 一图流：一个键从"配置"到"字节"

```
TU.keyList[row][col] = {value: 33, name:'Q', keyCode:20, key:'KeyQ'}
                          │        └ value 就是槽号(33)，keyCode 只是默认 HID 供显示
                          ▼ 用户在 UI 里把 Q 改成 Ctrl+C
userKey = {name:'CB', page:'CB', param1:224, param2:0, param3:6}
                          ▼ pX(buf, 33*4, userKey, '键盘按键')
buf[132]=7, buf[133]=224, buf[134]=0, buf[135]=6      // 07 E0 00 06
                          ▼ SET_KEY(0x22) contentSize=512（10 个 HID 报文）
固件把这 4 字节存进 33 号键的映射槽
                          ▼ 回读 GET_KEY(0x12) 512 字节
mX({pageType:7,param1:224,param2:0,param3:6}) → xX → {name:'CB',page:'CB',param1:224,param2:0,param3:6}
                          ▼ hX 把它挂回 keyList[?][?].userKey（按 value===33 找）
UI 显示 "Ctrl + C"
```

---

## 14. 真机数据交叉验证（`docs/keymap_device_report.txt`）

> 数据来源：`docs/keymap_device_report.txt` / `docs/keymap_device.json`（硬件通道由 Lead 完成读取，本文件不做任何 HID 操作）。
> 复核脚本：`node scripts/verify_vs_device.js`（只读那两个文件 + 本模块的编解码器）。

### 14.1 结果：模型与真机 100% 吻合

| 检查 | 数据量 | 结果 |
|---|---|---|
| 普通层每条 4 字节 → 解码 → **回写**是否等于真机字节 | 112 条 | ✅ 0 条不一致 |
| 普通层 87 个配置槽：解码出的 `value` 是否等于该键的 `keyCode` | 87 条 | ✅ 全部相等 |
| FN 层差异条目：能否解出名字 & 回写是否一致 | 26 条 | ✅ 0 条解不出、0 条不一致 |
| FN 层条目的 pageType 集合 | 26 条 | **{13}**（全是 FUNC，没有一条 ≥128） |

也就是说：真机普通层全是 `02 00 <HID> 00`（正是 §4.2 的写法），FN 层全是 `0d 00 00 <id>`
（正是 §4.6 的 24 位 FUNC 写法），与本文字节级规则**逐字节一致**。

### 14.2 普通层里 25 个「配置外但非零」的槽（**改键必读**）

真机普通层 112/128 槽非零，其中这 25 个槽 **不在** MK87 的 `keyList` 里：

| 槽 | 真机 4 字节 | 解码 |
|---|---|---|
| 13 | `03 E9 00 00` | CONSUMER_KEY 音量 + |
| 14 | `03 EA 00 00` | CONSUMER_KEY 音量 - |
| 15 | `02 00 98 00` | KEYBOARD HID 0x98（官方表无此项；FN 层它是 `0D 00 00 2E` = 旋钮模式切换） |
| 29 / 30 / 31 | `02 00 53/54/55` | 小键盘 NumLock / KP÷ / KP× |
| 45 / 46 / 47 | `02 00 5F/60/61` | 小键盘 7 / 8 / 9 |
| 61 / 62 / 63 | `02 00 5C/5D/5E` | 小键盘 4 / 5 / 6 |
| 77 / 78 / 79 | `02 00 59/5A/5B` | 小键盘 1 / 2 / 3 |
| 93 / 94 / 95 | `02 00 62/63/58` | 小键盘 0 / . / Enter |
| 109 / 110 | `02 00 56/57` | 小键盘 - / + |
| 96 / 111 | `02 00 7D 00` | HID 0x7D（官方表无此项） |
| 97 / 98 | `02 00 32 00` / `02 00 64 00` | HID 0x32 / 0x64（非 US 反斜杠两兄弟） |
| 101 | `02 00 E7 00` | HID 0xE7 = RGUI（右 Win；`aX` 里只有 227/L-Win，所以官方表查不到） |

**直接后果**：官方 `setKeyData` 只遍历 `keyList`（87 槽），其余槽写 0 ⇒
**【真机修正 2026-11-01】写 0 并不会清空这 25 个槽**：fw1.19 会拒绝置零、保持原值（写非零则生效）；而 keyList 内的槽写 0 = **恢复出厂默认**（例：Insert 写 0 → `02 00 49 00`）。静态阶段的「会丢小键盘/音量」推断实测不成立，保留原文作对比。
这不是猜测，是真机数据 + 代码两条线合起来的结论。⇒ 自己实现务必**整块读-改-写**（§7.3/§7.4）。

> 顺带解释了「为什么会有 41 个空槽」：MK87 是 87 键的键盘，但固件矩阵用的是**同一套 104+ 键模板**
> （含完整小键盘与音量键），只是这台机器上没装那些键。槽号 96..111 就是"小键盘/编辑区"位置。

### 14.3 读回长度：560 vs 512

报告首行 `矩阵长度: key=560 fn=560 default_fn=560 default_key=560` ——
512 字节按 56 字节/包传输是 **10 包 = 560 字节**（末包补 0）。官方代码一律 `.slice(0,512)`。
自己实现时**必须截断到 512**，否则会多出 48 个"伪槽"（129..140）。

### 14.4 FN 层与出厂默认

报告 `FN 层 vs 默认FN层差异: 0` ⇒ 当前 FN 层就是出厂默认，没有用户改动。
26 个差异条目里有意义的几条（可用来对照 §4.6 的 id 表）：

| 槽 | 物理键 | FN 层字节 | funcId | 动作 |
|---|---|---|---|---|
| 15 | (旋钮) | `0D 00 00 2E` | 46 | 旋钮模式切换 |
| 16 | ` ~ | `0D 00 00 63` | 99 | 自定义灯光录制 |
| 17 / 18 / 19 | 1 / 2 / 3 | `0D 00 00 47/48/62` | 71 / 72 / 98 | 自定义灯光 1 / 2 / 3 |
| 27 / 28 | - / = | `0D 00 00 10/0F` | 16 / 15 | 灯光速度- / + |
| 33 / 34 / 35 / 36 | Q / W / E / R | `0D 00 00 02/03/04/05` | 2 / 3 / 4 / 5 | 蓝牙通道1/2/3 / 无线回连 |
| 59 / 60 | ' / \ | `0D 00 00 18/0B` | 24 / 11 | 侧灯颜色切换 / 灯光效果切换 |
| 66 | X | `0D 00 00 11` | 17 | 关闭灯光 |
| 67 / 68 | C / V | `0D 00 00 54/55` | 84 / 85 | 显示屏语言切中文 / 英文 |
| 76 | Enter | `0D 00 00 17` | 23 | 侧灯效果切换 |
| 81 | L-Win | `0D 00 00 16` | 22 | 锁定 Win |
| 83 | Space | `0D 00 00 01` | 1 | 恢复出厂设置 |
| 88..91 | ← ↓ ↑ → | `0D 00 00 4E/0E/0D/0C` | 78/14/13/12 | 方向键转换/亮度-/亮度+/颜色切换 |
| 92 | Back | `0D 00 00 07` | 7 | 查询电量 |
| 103 / 104 | Insert / Home | `0D 00 00 27/3F` | 39 / 63 | 关闭屏幕 / GIF模式 |
| 106 / 107 | Del / End | `0D 00 00 59/8A` | 89 / 138 | LOGO LED 开关 / 开启屏幕下方按键灯 |

> 这 26 条 = `defaultFnFuncIds` 的真机内容（去重后的 id 集合），也就是官方 UI「功能」标签页在 MK87 上
> 实际能选的**全部**固件动作（§5.1 的 `fnFuncIds ∪ defaultFnFuncIds` 逻辑）。

---

## 15. 相关文件

| 文件 | 内容 |
|---|---|
| `docs/keymap.md` | 本文件 |
| `docs/keymap-tables.json` | 7 张动作表全量 + pageType 表 + MK87 配置 + 所有 bundle 偏移 |
| `scripts/keymap.js` | `decodeEntry` / `encodeEntry` / `decodeMatrix` / `encodeMatrix` + 自检 + CLI |
| `scripts/keymap_decompiled.js` | **官方 pX/mX/hX/gX/kX 及 13 个解码器的格式化原文**（带偏移标记，实现时对着看） |
| `scripts/verify_vs_device.js` | 用真机读回数据反向校验本模型（只读文件，不碰硬件） |
| `scripts/mk87_config.json` | MK87 `keyboardConfig` 全量（含 87 键 keyList 原样结构） |
| `scripts/tables.js` | 从 bundle 里定位/切出命名数据表（含 `matchPair` 的复用） |
| `scripts/slice.js` | 按偏移切 bundle 并格式化（调试用） |
| `scripts/gen_tables_json.js` | 重新生成 `docs/keymap-tables.json` |
| `scripts/mk87cfg.js` | 单独抽 MK87 `keyboardConfig` |
| `docs/protocol.md` / `docs/protocol_commands.js` / `docs/infra.js` | 帧层与 66 条命令（已有成果） |
| `docs/keymap_device_report.txt` / `docs/keymap_device.json` | **真机读回数据**（Lead 产出，本文件只读引用） |

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
