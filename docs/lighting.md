# MK87 灯效系统逆向（纯静态：bundle + 官方站点 chunk）

> 【**真机补充 2026-11-01**】①亮度字段 1..6 为 identity，**brightness=1 = 全灭**（PWM 0/49/97/143/191/253），越界值未定义（0→255、7→11…），工具应钳 2..6；②`mode=0` 关灯后 **Fn 键仍亮红灯 = 充电指示灯**（无法用 LED 数据覆盖）；③**20/21/128 三个自定义族模式共用同一张 SET_CUSTOM_LED_DATA 表**（真机验证）；④**物理 LED 只有 86 个**：官方 keyList 标有键的 99/100/102 实际无灯（该处是小屏幕），标无键的 97/98 实际有灯（logo 灯区域）。详见 [TEST-REPORT.md](TEST-REPORT.md)。

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

设备：AJAZZ KEYBOARD，**VID 0x0C45 / PID 0x8047**（3141 / 32839），固件 1.19，240×135 TFT。
本文所有结论都来自**官方网页驱动 bundle 的静态分析**，本轮**没有打开任何 HID 设备**。
凡是没有代码直接证据的推断，一律标 **【推断】**，并在 §8 给出真机验证配方。

配套文件：

| 文件 | 内容 |
|---|---|
| [lighting-modes.json](lighting-modes.json) | 模式全表（mode/名称/文案键/参数约束）、自定义灯流程、LED↔键映射、i18n 键、线格式（`scripts/lighting_gen_json.js` 生成，不手抄） |
| [`scripts/lighting_ref.js`](../scripts/lighting_ref.js) | 可运行参考实现 + 自检：`encodeLedEffect` / `buildCustomLedPayload` / `buildLedAnimationPayload`，与 bundle 内官方实现**逐字节对比** |
| `scripts/lighting_fetch.js` | 从官方站点抓缺失 chunk（原始字节，UTF-8 无损） |
| `scripts/lighting_dump.js` / `lighting_offsets.js` / `lighting_beautify.js` | 偏移定位 / 关键字命中 / 迷你美化（自包含，不 require 别人的脚本） |
| `scripts/lighting_modes.js` / `lighting_devicecfg.js` / `lighting_gen_json.js` | 模式表求值 / MK87 设备配置提取 / JSON 合成 |
| `docs/_lighting_raw/` | 抓下来的原始 chunk + 切片 + 美化版（证据留存） |

---

## 0. TL;DR（先看这段）

1. **模式表不在 3.3MB 主 bundle 里**，而在懒加载的协议配置 chunk `assets/lighting-DzPku7KQ.js`
   （= 源码里的 `config/protocols/default/lighting.ts`）。主 bundle 只负责 `import()` 它并做过滤。
2. MK87 的 UI 模式列表 = **1..19 + 128（自定义）共 20 项**；协议里另有 12 个扩展模式
   （23/24/25/254/26..33），**因为 MK87 的 `lightingConfig` 没有 `customEffect` 字段，它们不出现在 MK87 网页上**。
3. `SET_LED_EFFECT(35)` 的 16 字节布局已完全确认，且与真机回读一字不差：
   `[0]=mode [1..3]=RGB [4]=0xFF(硬编码) [5..7]=副色 [8]=colorMode [9]=brightness [10]=speed [11]=direction [12]=effectModeType [13]=0 [14]=0xAA [15]=0x55`。
4. `colorMode`：**0 = 单色**（用 payload 里的 RGB；一碰取色器就强制 0），**1 = RGB/多色**（用固件内置配色）。
   设备实测出厂就是 `colorMode=1`。
5. `direction`：**0=右 1=左 2=上 3=下**；10/11/12/16/18 带方向按钮，切模式时 direction 会被重置成该模式的
   `directionValue`（10 默认 3，其余默认 0）。
6. **关灯 = `mode=0`**（灯效开关关闭时网页就是发 `mode=0`），不是靠亮度 0。
7. 自定义灯效：`mode=128` + `SET_CUSTOM_LED_DATA(36)` 512 字节（128×`[下标,R,G,B]`）。
   `isCustomMode` 的判定是 **`[20,21,128].includes(mode)`**；`isCustomLighting` 就是它的别名（同一个 computed）。
8. **颜色不做量化**：取色器给 sRGB 0..255 整数，直接进 512B 的 R/G/B 字节。
9. **LED id 就是键位矩阵槽位 `value`**：官方预览键盘直接 `find(t => t.ledId === key.value)` 上色，
   自定义灯数组也用 `key.value` 做下标。87 键的映射表已导出到 `lighting-modes.json.ledKeyMap`。
10. MK87 灯效页只有 **两个 tab**：`color`（灯效）和 `music`（音乐律动 v1）。灯箱/侧灯/GIF/AI 都没有
    （`isShowLightBox:false`，`isShowSideLight`/`isShowGifEffect` 字段缺省）。
11. 音乐律动 v1 由**本机助手 `Music.exe`（http://127.0.0.1:9191）**负责算灯并直接推设备，
    浏览器只下发键盘几何 + 参数（§4.1）。

---

## 1. 方法与证据来源

### 1.1 主 bundle 里缺的文件，从官方站点静态补抓

`layout-classic-CMxiG14P.js` 里模式表是懒加载的：

```js
// @1863050 (line 3973)  initProtocol
let t = await nY(Object.assign({
  "../config/protocols/default/lighting.ts": () => Q(() => import(`./lighting-DzPku7KQ.js`), [])
}), `../config/protocols/${r}/lighting.ts`, 5);
let i = [...t.defalutLightingModeList];                       // ← 默认模式列表
if (e?.keyboardConfig?.lightingConfig?.hiddenDefaultEffect?.length)
  i = i.filter(t => !e.keyboardConfig.lightingConfig.hiddenDefaultEffect.includes(t.value));
if (e?.keyboardConfig?.lightingConfig?.customEffect?.length)
  t.appendLightingModeList.forEach(t => {
    e.keyboardConfig.lightingConfig.customEffect.includes(t.value) && i.push(t);
  });
if (e?.keyboardConfig?.lightingConfig?.isSingleColor) i = i.map(e => ({ ...e, isShowColor: !1 }));
n.lightingList.value = i.sort((e, t) => (e.sort || 0) - (t.sort || 0));   // ← 按 sort 排序
n.CUSTOM_LIGHTING_MODE.value = t.CUSTOM_LIGHTING_MODE || 128;
```

`assets/` 目录里没有 `lighting-DzPku7KQ.js`（它是路由 chunk 之外的二级懒加载块），所以本轮用
`scripts/lighting_fetch.js` 对 `https://ajazz.driveall.cn/assets/lighting-DzPku7KQ.js` 做了一次**纯 HTTP GET**
（不涉及 HID）。先核对版本一致：`index.html` 引用的是 `main-_p8CH46K.js` / `layout-classic-CMxiG14P.js`，
与本地文件同名同哈希 → **是同一个构建**。

> 直接用常规抓取工具会得到乱码（服务端没带 charset，UTF-8 被按 GBK 解码，
> 例如 `闈欐€佹亽浜`）。`lighting_fetch.js` 走 `fetch().arrayBuffer()` + `TextDecoder('utf-8')`，字节无损。

同批抓下来并用于本文的 chunk：

| chunk | 作用 |
|---|---|
| `lighting-DzPku7KQ.js` (7.7KB) | **模式表**（4 个列表 + `CUSTOM_LIGHTING_MODE`） |
| `lightingPane-J3Fl9UJi.js` (8.1KB) | 灯效参数面板（colorMode/亮度/速度/方向/effectModeType/取色器/键组选择器） |
| `keyboard-BfmQGlU0.js` (5.1KB) | 预览键盘（DOM 网格、逐键 `bgColor`） |
| `gifLighting-Ci_xahHI.js` / `colorPicker-CPHEf-gj.js` | GIF 灯效页 / iro 取色器 |
| `musicV1-BxjgapTH.js` / `musicV2-Czdpb4b6.js` / `musicDiy-53W-bGlE.js` | 音乐律动两个版本 |
| `lightBox-kK-8jmZF.js` / `sideLight-Cg0MWuKZ.js` | 灯箱 / 侧灯（MK87 不显示） |

### 1.2 MK87 的设备配置（权威副本，直接从 bundle 求值）

主 bundle 里 MK87 的配置对象在 **@1194719..1200783**（`vendorId:3141, productId:32839`）。
`scripts/lighting_devicecfg.js` 用括号配平截取该对象并 `new Function('return (' + text + ')')()` 求值，
得到（`docs/_lighting_raw/mk87-config.json`）：

```js
{
  vendorId: 3141, productId: 32839, supplierName: 'ajazz', name: 'AJAZZ KEYBOARD',
  connectType: 'USB',
  routesName: ['customKeys','lighting','macro','tft','settings'],
  keyboardImg: 'kb_bg.png',
  customKeysConfig: { isShowFn: true, isShowNormalFuncKeys: true, fnFuncIds: [], fnDisabledKeyIds: [1..12] },
  lightingConfig: { minBrightness: 1, maxBrightness: 6, minSpeed: 1, maxSpeed: 6,
                    isShowLightBox: false, lightBoxList: [1,2,3,5], isShowLightBoxEdit: true },
  musicConfig:    { version: 1, maxColOffset: 0, keyOffset: [ {F1,1,1}, {Z,65,1}, {↑,90,2}, {Spacebar,83,3}, {R-Alt,84,3} ] },
  macroConfig:    { isShowFn: true },
  tftConfig:      { name: 'AK980_PRO', localforageKey: 'w240h135', width: 240, height: 135 },
  settingsConfig: { isShowSingleKeyWakeup: false, ... },
  keyList: [ 6 行 × 共 87 键 ]
}
```

⚠️ 注意：之前 `docs/device_config_32839.json` 里这份配置是**有损的**
（`lightingConfig` 被存成了字符串、`musicConfig` 丢了）。以本轮 `_lighting_raw/mk87-config.json` 为准。

⚠️ 另有一处旧结论需要订正（本文不改别人的文件，只在此标注）：
`docs/deepdive-mk87.md` §4 写「音乐律动 v2：`musicConfig:{version:2,…}`」，
但 bundle 里 MK87 的权威配置是 **`version: 1`**（`docs/_lighting_raw/mk87-config.json`，
bundle @1194719..1200783）。版本号决定了灯效页渲染 `musicV1` 还是 `musicV2`（§4.1），所以这个数字很关键。

**关键缺省字段**（决定了 MK87 少掉哪些功能）：

| 字段 | MK87 | 影响 |
|---|---|---|
| `isShowLightBox` | `false`（显式） | 无「灯箱」tab，且不读 `GET_LIGHT_BOX` |
| `isShowSideLight` | 缺省 | 无「侧灯」tab，不读 `GET_SIDE_LIGHT` |
| `isShowGifEffect` | 缺省 | 无「GIF 灯效」tab；`ledEffect.mode=255` 分支不可达 |
| `isEnableLightSync` | 缺省 | 预览键盘**不做** `GET_ALL_LIGHTS_RGB` 实时上色轮询 |
| `isSingleColor` | 缺省 | 不禁用颜色按钮 |
| `hiddenDefaultEffect` | 缺省 | 不隐藏任何默认模式 |
| `customEffect` | 缺省 | **不追加** 23..33 / 254 那批扩展模式 |
| `musicConfig.version` | **1** | 音乐律动走 v1（不是 v2！） |

---

## 2. SET_LED_EFFECT(35) 的 mode 全表

### 2.1 payload 布局（已与真机回读对齐）

官方写入实现 `vZ`（**@1929958, line 4021**）：

```js
vZ = async (e, t, ...n) => {
  let r = BX.deviceStorage.deviceInfo?.frameVersion,
      i = n[0], a = new Uint8Array(16).fill(0);
  return a[0]=i.mode, a[1]=i.red, a[2]=i.green, a[3]=i.blue, a[4]=255,
         a[5]=i.secondaryRed, a[6]=i.secondaryGreen, a[7]=i.secondaryBlue,
         a[8]=i.colorMode, a[9]=i.brightness, a[10]=i.speed, a[11]=i.direction,
         a[12]=i.effectModeType,
         a[14]=170, a[15]=85,
         await NX(e, { cmd: HX.SET_LED_EFFECT, contentSize: 16, data: a, timeout: r===1?2e3:500 }),
         BX.deviceStorage.ledEffect = i, !0
}
```

官方读取 `_Z`（**@1929482**）字段名不同（`driverSetting` / `checkCodeL` / `checkCodeH`），但字节位置一致：

```js
i = { mode:r[0], red:r[1], green:r[2], blue:r[3], driverSetting:r[4],
      secondaryRed:r[5], secondaryGreen:r[6], secondaryBlue:r[7],
      colorMode:r[8], brightness:r[9], speed:r[10], direction:r[11],
      effectModeType:r[12], checkCodeL:r[14], checkCodeH:r[15] }
```

| 字节 | 字段 | 取值 | 说明 |
|---|---|---|---|
| 0 | mode | 见 §2.2 | 0 = 关灯 |
| 1..3 | red/green/blue | 0..255 | 主色；`colorMode=0` 时生效 |
| 4 | driverSetting | **恒 255** | 写入端硬编码，不吃外部参数 |
| 5..7 | secondaryRed/Green/Blue | 0..255 | 副色（只有 `isShowSecondaryRGB` 的模式用，MK87 无此模式） |
| 8 | colorMode | 0 / 1 | 0=单色，1=RGB |
| 9 | brightness | 1..6（本机） | 网页 UI 步进 1 |
| 10 | speed | 1..6（本机） | 网页 UI 步进 1；`isShowSpeed=false` 的模式不显示滑条（但字节照发） |
| 11 | direction | 0/1/2/3 | 右/左/上/下 |
| 12 | effectModeType | 0..3 | 仅 mode 254 用 |
| 13 | — | 0 | 保留 |
| 14..15 | checkCodeL/H | **0xAA 0x55** | 固定校验尾 |

真机回读（`docs/protocol.md` §6 实测）：`01 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55`。
参考实现在自检里也断言了这一串（`PASS 真机回读交叉验证`）。

### 2.2 MK87 实际可见的 20 个模式

`lightingConfig` 没有 `hiddenDefaultEffect` / `customEffect`，所以列表 = `defalutLightingModeList` 按 `sort` 排序后的全部 20 项：

| mode | 名称 | 文案键 | sort | 会用到的参数 | 备注 |
|---:|---|---|---:|---|---|
| 1 | 静态恒亮 | `lighting_icon1` | 10 | color | 出厂默认（真机 mode=1） |
| 2 | 单点亮 | `lighting_icon2` | 20 | color, speed(3) | |
| 3 | 单熄灭 | `lighting_icon3` | 30 | color, speed(3) | |
| 4 | 繁星点点 | `lighting_icon4` | 40 | color, speed(3) | |
| 5 | 漫天飞雪 | `lighting_icon5` | 50 | color, speed(3) | |
| 6 | 百花争艳 | `lighting_icon6` | 60 | speed(3) | `isShowColor:false`（自带彩色，不显示取色器） |
| 7 | 动态呼吸 | `lighting_icon7` | 70 | color, speed(3) | |
| 8 | 光谱循环 | `lighting_icon8` | 80 | speed(3) | `isShowColor:false` |
| 9 | 彩泉涌动 | `lighting_icon9` | 90 | color, speed(3) | |
| 10 | 多彩纵横 | `lighting_icon10` | 100 | color, speed(3), **direction** | `directionPosition:'top'`、默认 `direction=3`（向下） |
| 11 | 随波逐流 | `lighting_icon11` | 110 | color, speed(3), direction | 默认 `direction=0`（向右） |
| 12 | 峰回路转 | `lighting_icon12` | 120 | color, speed(3), direction | 默认 0 |
| 13 | 一触即发 | `lighting_icon13` | 130 | color, speed(3) | |
| 14 | 一石二鸟 | `lighting_icon14` | 140 | color, speed(3) | |
| 15 | 涟漪扩散 | `lighting_icon15` | 150 | color, speed(3) | |
| 16 | 川流不息 | `lighting_icon16` | 160 | color, speed(3), direction | 默认 0 |
| 17 | 重峦叠嶂 | `lighting_icon17` | 170 | color, speed(3) | |
| 18 | 斜风细雨 | `lighting_icon18` | 180 | color, speed(3), direction | 默认 0 |
| 19 | 来回穿梭 | `lighting_icon19` | 190 | color, speed(3) | |
| **128** | **自定义** | `lighting_icon20` | 1280 | color（逐键） | 见 §3；`isShowSpeed/isShowDirection:false` |

「会用到的参数」列的含义：

* `color` = 面板右侧出现取色器（`isShowColor`）→ 选了颜色就自动 `colorMode=0`；
* `colorMode` 单选的显示条件是 `isShowColor && !isShowSecondaryRGB && !isHideColorMode`，
  所以 **除 6/8（自带彩色、无取色器）和自定义 128（在自定义模式下隐藏）之外，1..19 都会显示「单色 / RGB」单选**；
* `speed` 滑条只在 `isShowSpeed` 时显示；**括号里的数字是模式表的 `speedValue`，bundle 从不读取它**
  （纯元数据，切模式不会自动改 speed）；
* `direction` 只在 `isShowDirection` 时显示（10/11/12/16/18）；
* `副色` / `effectModeType` 只有 254（MK87 不可见）会用到。

模式表原始数据（`docs/_lighting_raw/lighting-modes.raw.json`，由 `scripts/lighting_modes.js` 对 chunk 求值）：

```js
t = [ {name:`静态恒亮`, text:`lighting_icon1`, value:1, icon:`i-carbon:sun`,
       isShowSpeed:!1, isShowDirection:!1, isShowColor:!0, sort:10}, … ]
n = [ {name:`彩虹风车`, value:23, …}, {name:`心动时刻`, value:254,
       isShowSecondaryRGB:!0, isShowEffectModeType:!0,
       effectModeTypeOptions:[{name:`爱心呼吸`,text:`color_model_heart`,value:0},
                             {name:`背景呼吸`,text:`color_model_background`,value:1},
                             {name:`同时呼吸`,text:`color_model_both`,value:2},
                             {name:`常亮模式`,text:`color_model_constant`,value:3}]}, … ]
```

### 2.3 协议里存在、但 MK87 不显示的 12 个模式

`appendLightingModeList`（只有 `lightingConfig.customEffect` 里点名才会被 push）：

| mode | 名称 | 文案键 | 参数 | 备注 |
|---:|---|---|---|---|
| 23 | 彩虹风车 | `lighting_icon21` | speed(5), direction | `isShowColor:false` |
| 24 | 七彩聚拢 | `lighting_icon22` | color, speed(5) | |
| 25 | 霓虹叠影 | `lighting_icon23` | color, speed(5), direction | |
| **254** | **心动时刻** | `lighting_icon28` | color, **副色**, speed(5), **effectModeType** | 唯一用 `secondaryRGB` + `effectModeType` 的模式 |
| 26 | 生命潮汐 | `lighting_icon34` | color, speed(5) | |
| 27 | 硅基呼吸 | `lighting_icon35` | color, speed(5) | |
| 28 | 渐变常亮 | `lighting_icon37` | color | `isShowSpeed:false` |
| 29 | 单色呼吸 | `lighting_icon38` | color, speed(5) | `isHideColorMode:true`（不显示「单色/RGB」单选） |
| 30 | 动态常亮 | `lighting_icon39` | color | |
| 31 | 多彩纵横1 | `lighting_icon40` | color, speed(3) | |
| 32 | RGB 动态呼吸 | `lighting_icon41` | color, speed(3) | |
| 33 | 多彩纵横2 | `lighting_icon42` | color, speed(3) | |

> 模式表里每项还有个 `speedValue`（3 或 5）——**bundle 里从来没读过这个字段**（全库 0 次读取），
> 属于死元数据：切模式不会自动改 speed，speed 仍来自 `deviceStorage.ledEffect.speed`。

### 2.4 其它两组模式枚举（不属于 SET_LED_EFFECT，但同源）

`lightBoxModeList`（12 项，`SET_LIGHT_BOX(43)`，MK87 无硬件）：
1 流光 / 2 静态恒亮 / 3 动态呼吸 / 4 光谱循环 / **5 关闭背光** / 6 灵动 / 7 连锁反应 /
8..11 拾音灯效1-4 / 12 跑马灯效。MK87 即便有 tab 也只会显示 `lightBoxList:[1,2,3,5]` 这四个。

`sideLightModeList`（6 项，`SET_SIDE_LIGHT(45)`）：
1 流光 / 2 静态恒亮 / 3 动态呼吸 / 4 光谱循环 / **5 关闭背光** / 6 滚动颜色。

⚠️ 注意：灯箱/侧灯自己的枚举里 **5 = 关闭背光**，但**主灯效没有「关闭」这一项**，主灯效关灯用 `mode=0`（§5.1）。

---

## 3. 自定义灯效流程

### 3.1 判定：`isCustomMode` / `isCustomLighting`

页面组合式函数 `I9()`（**@2439246**，line 4023）：

```js
I = () => {
  let e = g.value;                                            // g = ledEffect
  if (e && (A.value = [20,21,128].includes(e.mode),           // ← isCustomMode
            ee.value = A.value || !!h.value.find(t => t.value === e.mode),  // isOpenLight
            e.mode === 255 && !ee.value)) {
    let e = h.value.find(e => e.value === 11), t = h.value[0];
    Ce(e ?? t), ee.value = !0;                                // 255(GIF) 但不在列表 → 落到 11 或第一项
  }
}
```

* **`isCustomMode` = `[20, 21, 128].includes(ledEffect.mode)`**（@2442575）；
* **`isCustomLighting` 只是它的别名**：`let L = K(() => A.value)`（同一个 computed，传给模板做「预览键盘可点选」），
  所以文档里两个名字可以视为同一件事；
* 面板里的 `currentLightingValue` 也做了折叠：`isCustomMode ? CUSTOM_LIGHTING_MODE(128) : ledEffect.mode`
  （**@2285177**，C7 组合式函数）→ 设备若报 20/21，UI 仍然高亮「自定义」那一格。

【推断】20/21/128 对应固件的三种「自定义灯光」：FN 动作表里
`Fn+1 = 自定义灯光1 (FUNC 71)`、`Fn+2 = 自定义灯光2 (72)`、`Fn+3 = 自定义灯光3 (98)`、`Fn+\` = 录制 (99)`
（见 `docs/keymap-tables.json` / `docs/fn-layer-decode.json`）。bundle 只给出三个值的判定，没写映射关系。

### 3.2 完整命令序列

| # | 用户动作 | 发什么 | 证据 |
|---:|---|---|---|
| 0 | 连上设备（初始化） | `GET_LED_EFFECT(19)` 16B → `GET_CUSTOM_LED_DATA(20)` 512B | `deviceInit`：`t.routesName.includes('lighting') && (a = await _Z(e), o = await yZ(e))` |
| 1 | 点模式格「自定义」 | `SET_LED_EFFECT(35)`：`mode=128`，`direction = directionValue ?? 0`，其余字段沿用 `ledEffect` | `Ce = e => { A.value = e.value===v.value, g.value.mode=e.value, g.value.direction=e.directionValue??0, …, pe() }` **@2444105** |
| 2 | 在预览键盘框选键（**自定义模式下**） | **会发** `SET_CUSTOM_LED_DATA(36)`：把「当前取色器颜色」刷到这些键 | `_e(t)` **@2443245**：`if (isCustomMode && paneRef && t.length) { let e = paneRef.getCurrentColor(); t.forEach(t => customLedData[keyList[row][col].value] = e); paneRef.sendLEDCustomDebounced() }` |
| 3 | 换颜色（键已选中） | 同上（涂已选键 → 512B） | `Oe(color)` **@2443606**：`selectedKeys.forEach(t => customLedData[...] = color); sendLEDCustomDebounced()` |
| 4 | 换颜色（**普通模式**下） | `SET_LED_EFFECT(35)`：`colorMode=0` + 新 RGB | `re(color)`：`if (isCustomMode) updateSelectedKeysColor(color) else updateLedEffectPatch({colorMode:0, red, green, blue})` |
| 5 | 重置 | `SET_CUSTOM_LED_DATA(36)` 全 0（index 字节仍写下标） | `handleReset(true)` → `customLedData.forEach(e => e.red=e.green=e.blue=0); I()` |
| 6 | 切到别的灯效模式 | `SET_LED_EFFECT(35)`：`mode=新模式`（离开自定义） | 同 #1 的 `Ce` |

发送端（C7 组合式函数，**@2287426** 附近）：

```js
le = EI(async () => {                     // EI = 防抖 300ms
  if (se.value) return; se.value = !0; let e = ce;
  try { await i(`setCustomLEDData`, r, o.value) }   // ← 512B 整表
  catch (e) { console.error(`发送自定义灯效设置失败:`, e) }
  finally { await wV(100); e === ce && t(`resumeLightSync`); se.value = !1 }
}, 300)
I = () => { ce++, t(`pauseLightSync`), le() }       // 发之前暂停 RGB 轮询
```

> MK87 没有 `isEnableLightSync`，所以 `pauseLightSync/resumeLightSync` 实际是空操作，
> 但**协议序列仍然是「整表 512B 覆盖写」**，一次绘制可能连发多次（300ms 防抖合并）。

**不需要/不会出现的命令**：

* `setKeyData` / `SET_KEY(34)`：只属于改键页，灯效流程完全没调用；
* `SET_KEYBOARD_CUSTOM_FUNCTION_ON/OFF(48/49)`：enum 里有定义，**全 bundle 0 次调用**；
* `CLEAR_LED_DATA(54)`：灯效页不调用（只在点阵屏组件里清 LED 缓冲）。

### 3.3 512 字节表结构与「取整/量化」

官方写入 `bZ`（**@1930776**）：

```js
bZ = async (e, t, ...n) => {
  let r = n[0], i = new Uint8Array(512).fill(0);
  for (let e = 0; e < r.length && e < 128; e++) {
    let t = e*4, n = r[e];
    i[t] = e, i[t+1] = n.red, i[t+2] = n.green, i[t+3] = n.blue;   // ← 下标写死为数组序号
  }
  return await NX(e, { cmd: HX.SET_CUSTOM_LED_DATA, contentSize: 512, data: i, timeout: 2e3 }),
         BX.deviceStorage.customLedData = r, !0;
}
```

官方读取 `yZ`（**@1930412**）返回 128 个 `{ledId, red, green, blue}`，其中 `ledId` 是设备存回来的第 0 字节。

| 规则 | 结论 |
|---|---|
| 表长 | 固定 **512B**（128 槽 × 4B），不足补 0，超过 128 项截断 |
| index 字节 | **写的是数组下标**，不是颜色对象里的 `ledId` 字段（读回时设备可能存别的值，写时一律归一化成下标） |
| 颜色字段 | 只读 `red/green/blue`（长名）；只给 `r/g/b` 时官方写 **0**，参考实现严格保持一致 |
| 量化 | **无**。iro 取色器 / HEX / RGB 输入都给 0..255 整数，直接落字节；HEX 走 `parseInt(x,16)` 两位一组 |
| 索引方式 | `customLedData[key.value]` —— 用**键位槽位号**当下标（见 §6） |
| 发送分片 | NX 按 `reportCount-8 = 56` 字节/包切 **10 包**，`addr` 递增，每包一个 ACK 回显（cmd=0x24） |

### 3.4 FUNC 71/72/98/99 与数据的关系

| FN 动作 | FUNC id | 网页端对应 | 数据 |
|---|---|---|---|
| 自定义灯光1 | 71 | 无（固件本地） | 同一张 512B 表【推断】 |
| 自定义灯光2 | 72 | 无 | 同上【推断】 |
| 自定义灯光3 | 98 | 无 | 同上【推断】 |
| 自定义灯光录制 | 99 | 无 | 固件把用户敲键的颜色写进 512B 表【推断】 |

* 网页端的「录制」复选框（`show-record-checkbox`）**不是**录制命令：`isRecord=true` 只是让
  框选行为从「替换选择」变成「并入选择」（`pe()` 里 `e.isRecord && i.push(...l.value)`，**@2027284**）。
* 真正的录制入口是键盘上的 `Fn+\``（FUNC 99），由固件完成，WebHID 侧没有任何报文。
* 因此「自定义灯光 1/2/3 是否共用一张表」网页代码无法判定 → 列入 §8 真机验证。

---

## 4. 灯效页其它 tab

### 4.1 music（音乐律动）——MK87 是 v1，由本机助手负责

tab 出现条件（**@2439246** 的 `I9()` 内 `lightingTabs` computed）：

```js
c.lightingConfig?.isShowLightBox && e.push({name:`lightBox`, label:$(`light_box`)}),
c.lightingConfig?.isShowSideLight && e.push({name:`sideLight`, label:$(`side_light`)}),
c.musicConfig && r && e.push({name:`music`, label:$(`icon_6`)}),      // r = isWindows（VV() 检测 UA）
d.value && e.push({name:`musicDiy`, label:$(`music_diy`)}),           // isEnableMusicDiy && version===2
c.lightingConfig?.isShowGifEffect && e.push({name:`gif`, label:$(`gif_text2`)}),
u.value && e.push({name:`aiLighting`, label:$(`ai-lighting`)}),       // isEnableAILighting && version===2
```

MK87：`musicConfig` 存在 + Windows → **只有 `color` + `music` 两个 tab**。
`musicConfig.version === 1` → 模板渲染 `musicV1`（`O7`），v2 的 `X7` 不挂载。

**v1 的 UI**（`musicV1-BxjgapTH.js` + 组合式函数 `D7()` **@2301378**）：

| 控件 | 文案键 | 取值 |
|---|---|---|
| 律动模式 | `music_text1` | 12 项：`1,2,13,4,5,6,7,8,9,11,10,100` ↔ `music_mode_text1..11,21` |
| 振幅 | `music_text3` | 1..100，单位 `%` |
| 背景灯模式 | `music_text2` | 11 项：`0,6,7,8,9,10,11,1,2,4,5` ↔ `music_bg_text1..11` |
| 背景灯亮度 | `music_text4` | 1..100，单位 `%` |

**v1 的数据通路 = 浏览器根本不下发灯数据**（这点最容易误解，代码很明确）：

```js
// @2303372  参数下发（300ms 防抖）——只是把参数字符串发给本机助手
v = EI(async () => {
  try { await TY(`${s.value}&${c.value}&${l.value}&${u.value}&1`) }   // mode&amplitude&backmode&backmodebrightness&1
  catch { console.error(`更改音乐律动模式失败`) }
}, 300)

// @2304117  下发键盘几何（助手按这个把灯对齐到键）
let f = { name, vendorId, productId, deviceMode: connectType===`USB`?0:1,
          layouts: { rows: keyList.length, cols: maxCols+maxColOffset,
                     keys: [{row, col, code, index: key.value, name, disabledLight}] } };
await CY(encodeURIComponent(btoa(JSON.stringify(f))));
// 之后每 100ms 调 _() 读一次助手的每键颜色，只用来给预览键盘上色
```

助手 HTTP 接口（`xY = http://127.0.0.1:9191`，**@1801123**）：

| 方法/路径 | 用途 |
|---|---|
| `GET /api/keyboard/layout/base64?data=<urlencoded base64(JSON)>` | 下发键盘几何 |
| `GET /api/keyboard/musiceffect?param=<mode>&<amp>&<back>&<backBright>&1` | 设音乐律动参数 |
| `GET /api/keyboard/musiceffect/` | 读当前每键颜色（预览用） |
| `GET /api/keyboard/musiceffect/close/` | 关闭律动 |
| `GET /api/audio/amplitude` | 读振幅（v2 用） |
| `GET /api/hardware/info` | 硬件信息 |
| 下载 | `https://config.driveall.cn/music/v2/Music.exe`（未安装时 UI 显示下载按钮） |

> 结论：**音乐律动 v1 是「Lead（本机助手）负责驱动设备」**，浏览器只做参数 + 几何 + 预览。
> 若要自己实现音乐律动，需要自己算频谱并走 §5.6 的 `SET_MUSIC_DATA` / `SET_LED_DATA` 通道，或者直接调这个助手。

> **与并行任务 `docs/music-rhythm.md` 的口径对齐**：那篇说「v1/v2 最终都通过同一个 `setMusicData` 帧流推给键盘」——
> 就**官方 UI 在 v1 机型（MK87）上的代码路径**而言不成立：`musicV1` 的组合式函数 `D7()`（@2301378–@2304618）
> 里**没有任何 `setMusicData` 调用**，它只 `TY()` 发参数、`wY()` 读颜色画预览。
> `setMusicData` 只出现在三处：TFT/点阵音乐组件（@2320441）、musicDiy / v2 帧发送器（@2414442、@2433533），
> 而这两条在 MK87 上都被配置关掉了（`isEnableMusicDiy` 缺省、`version=1`）。
> 所以「MK87 要不依赖 Music.exe 自己推帧」是**我们自己的实现选择**（按 v2 的帧格式发 `setMusicData` 即可），
> 不是官方 v1 的既有行为 —— 两篇的结论在「怎么自己实现」上一致，在「官方 v1 是否发帧」上以本文为准。

**v2 摘要**（MK87 不用）：多了「点阵屏显示模式」(`ledModeList`)、测试模式、背景亮度 10..100；
浏览器侧采样画布后按 `setMusicData` 直发 4 字节/键的 RGB 流（`musicV2-Czdpb4b6.js`）。

### 4.2 gif（GIF 灯效）——MK87 未开启，但协议已还原

`isShowGifEffect` 缺省 → tab 不显示、`mode=255` 不可达。协议仍在（`gifLighting` + `setLedUserAnimation`）：

```js
// @2241779  上传：帧数 + 速度 → 4 字节前导，随后整段 RGB
let i = r.length / ledConfig.cols / ledConfig.rows;          // 帧数
let o = new Uint8Array(4);
o[0] = i & 255;  o[1] = i >> 8 & 255;
o[2] = Math.ceil(106 - t.speed) & 255;  o[3] = Math.ceil(106 - t.speed) >> 8 & 255;
let a = r.map(e => RV(e));                                    // hex 颜色 → {r,g,b}
await n(`setLedUserAnimation`, void 0, o, a, progressCb);
```

* 通道：`SET_LED_USER_ANIMATION(65)`，8 字节头 `AA 41 seqHi seqLo totalHi totalLo 00 00`，每包 `4104-8 = 4096` 数据字节；
* payload = `[帧数 LE16][ceil(106-speed) LE16]` + `帧数 × (rows×cols) × RGB`；
  每帧像素数来自 `keyboardConfig.ledConfig.{rows,cols}`（**MK87 没有 ledConfig 字段**，所以这条路在 MK87 上根本不会启用）；
* 帧数据是编辑器画布的**全像素**（`data.map(RV)`，`RV` 把 `#RRGGBB` 转 `{r,g,b}`），不按 87 键过滤；
* 帧数上限：`deviceInfo.ledMaxFrames`（`GET_DEVICE_INFO[26..27]`，MK87 实测 **0**）。
  代码在 0 时的退化规则：`startup` 类动画 >200 帧截断，其它 >260 帧截断并弹窗确认；
* `SET_LED_BOOT_ANIMATION(64)`：**enum 里有，全 bundle 0 次调用**（开机动画也走 65 号命令，靠 `ledId==='startup'` 区分）；
* `setGifLighting`（=`MZ`，**@1937224**）走 `SET_LED_DATA(66)`，是「应用/预览社区 GIF」的通道，
  同样是 `4 字节前导 + RGB`；它对帧像素按 `keyList.flat()` 的**全量位置**索引，
  但只输出 `!disabledLight` 的键（成交错过滤：`n.map((e,t)=>e.disabledLight?-1:t).filter(e=>e>=0)`）。

### 4.3 lightBox / sideLight（MK87 不支持，简述）

* 各自独立的命令与数据：`GET/SET_LIGHT_BOX(27/43)` 24 字节、`GET/SET_SIDE_LIGHT(29/45)` 24 字节；
* 布局：`[0]=mode [1..3]=RGB [8]=colorMode [9]=brightness [10]=speed`（其余保留 0）；
* 模式枚举见 §2.4，且**有独立的亮/灭语义（mode 5 = 关闭背光）**；
* MK87：`isShowLightBox:false` + `isShowSideLight` 缺省 → 页面不显示；真机 `GET_LIGHT_BOX`/`GET_SIDE_LIGHT` 全 0（无硬件）。

---

## 5. 灯效参数取值域

### 5.1 关灯 = `mode = 0`

页面开关（**@2443114**）：

```js
ge = e => {
  if (ee.value = e, Ee(), g.value) {
    if (!e) { g.value.mode = 0, pe(); return }                 // ← 关灯：mode=0 + setLEDEffect
    if (h.value.some(t => t.value === g.value?.mode)) pe();     // 开灯：模式有效就直接发
    else { let e = h.value[0]; e && Ce(e) }                     // 否则落到第一个模式
  }
}
```

* `isOpenLight` 的初值也是「mode 是否落在列表里」：`ee = isCustomMode || lightingList.some(v => v.value === mode)`；
  设备报 mode=0 → 开关显示为关。
* **亮度 0 ≠ 关灯**：协议层 `brightness` 原样下发（自检已验证 `0` 会落到 `[9]`），网页 UI 最小值是
  `minBrightness=1` 所以点不到 0；固件对 0 的处理没有代码可证 → **【推断】想要关灯请用 `mode=0`**。

### 5.2 brightness / speed

| 参数 | 字段 | 本机范围 | 步进 | UI 行为 |
|---|---|---|---|---|
| brightness | `[9]` | **1..6** | 1 | 滑条常驻（在 `isOpenLight` 的中间栏），显示 `值 + $t('gif_text14')` |
| speed | `[10]` | **1..6** | 1 | 仅 `currentLighting.isShowSpeed` 的模式显示；`isShowSpeed=false` 时字节仍按当前值发送 |

范围来自 `keyboardConfig.lightingConfig.{min,max}{Brightness,Speed}`，面板里：

```js
l0(E, m, { min: S.value, max: C.value, onChange: e => t(`updateLedEffectPatch`, {brightness:e}) })
```

### 5.3 direction

面板只有两个按钮，语义由模式的 `directionPosition` 决定（`lightingPane` chunk；下面是示意，
原码里两个按钮各自是同一个 handler，按 `directionPosition==='top'` 选 2/3 还是 1/0）：

```html
<!-- directionPosition === 'top' -->
<button :class="{'bg-primary': direction===2 || direction===1}" @click="setDirection(2)">↑</button>
<button :class="{'bg-primary': direction===3 || direction===0}" @click="setDirection(3)">↓</button>
<!-- 否则 -->
<button ... @click="setDirection(1)">←</button>
<button ... @click="setDirection(0)">→</button>
```

→ **0 = 右，1 = 左，2 = 上，3 = 下**。切模式时 `Ce` 会把 direction 重置为该模式的
`directionValue ?? 0`（10 → 3，11/12/16/18 → 0，其余 0）。

### 5.4 colorMode

| 值 | 语义 | 证据 |
|---:|---|---|
| 0 | **单色**（用 payload `[1..3]` 的 RGB） | 面板单选 `$t('lighting_single_color')` = 0 |
| 1 | **RGB / 多色**（用固件内置配色，忽略 `[1..3]`） | 面板单选 `RGB` = 1；真机出厂 `colorMode=1` |

* 单选只在 `currentLighting.isShowColor && !isShowSecondaryRGB && !isHideColorMode` 时显示；
* **一碰取色器就强制 `colorMode=0`**：`re = n => { p.value = 0; … t('updateLedEffectPatch', {colorMode:0, red:…}) }`；
* 所以「选自定义颜色」实际是「切到单色模式 + 写 RGB」。

### 5.5 effectModeType

仅 `mode=254`（心动时刻）使用，`[12]` 取值 0..3：

| 值 | 名称 | 文案键 |
|---:|---|---|
| 0 | 爱心呼吸 | `color_model_heart` |
| 1 | 背景呼吸 | `color_model_background` |
| 2 | 同时呼吸 | `color_model_both` |
| 3 | 常亮模式 | `color_model_constant` |

MK87 的列表里没有 254（`customEffect` 缺省），所以这个控件不会出现。

### 5.6 相关但不同的三条数据通道

| 命令 | 号 | 用途 | 备注 |
|---|---:|---|---|
| `SET_LED_EFFECT` | 35 | **灯效参数**（16B） | §2 |
| `SET_CUSTOM_LED_DATA` | 36 | **逐键颜色表**（512B） | §3 |
| `GET_ALL_LIGHTS_RGB` | 51 | **读实时颜色**（USB） | 请求体是 128×`[idx,0,0,0]` 的 512B 索引表，回 128×`[ledId,R,G,B]`（`DZ`） |
| `GET_ALL_LIGHTS_RGB_24G` / `_64_BYTE` | 55 / 59 | 2.4G 下的实时颜色 | 回包是 RGB565，2 字节/LED，带电量字节 |
| `SET_LED_DATA` | 66 | **流式写 RGB 帧** | `setGifLighting`（GIF 预览/应用）、`setLedSyncAnimation` 都用它；8 字节头 `AA 42 seq…` |
| `SET_LED_USER_ANIMATION` | 65 | **写 LED 动画**（帧数+速度+RGB） | §4.2 |
| `SET_MUSIC_DATA` / `_24G_64_BYTE` | 53 / 60 | **音乐律动 RGB 流** | 每键 4B `[ledId,R,G,B]` + 1B level；2.4G 通道压成 RGB565 |
| `CLEAR_LED_DATA` | 54 | 清 LED 数据缓冲 | 网页端只在点阵屏/LED 数据组件调用，键盘灯效页不用 |
| `SET_LIGHT_BOX` / `SET_SIDE_LIGHT` | 43 / 45 | 灯箱 / 侧灯（24B） | MK87 无硬件 |

---

## 6. LED id ↔ 物理键映射

### 6.1 结论：**LED id == 键位矩阵槽位 `value`**，映射表可直接导出

官方预览键盘的实时上色（**@2442358**，`displayKeyList` 生成）：

```js
let e = JSON.parse(JSON.stringify(m.value)).map(row => row.map(key => {
  delete key.userKey; key.name = ``; delete key.text;
  if (b.value.has(key.value)) { delete key.bgColor; return key; }      // disabledLight
  let n = t.find(t => t.ledId === key.value);                          // ← 直接按 ledId === value 匹配
  return n ? { ...key, bgColor: `rgb(${n.red}, ${n.green}, ${n.blue})` } : { ...key, bgColor: `#000` };
}));
```

其它同源证据：

* 自定义灯写入：`_.value[m.value[t.row][t.col].value].red = …`（**@2443402**）——数组下标就是键 `value`；
* 2.4G 读回：`m.value.forEach(row => row.forEach(k => { t.push({ ledId: k.value, red: n[e].red, … }) }))`
  （**@2441996**）——回包按 `keyList` 展平顺序逐键取色；
* 预览键盘是 **DOM 网格**（`keyboard-BfmQGlU0.js`：`div.key-item.w-14.h-14` + 每键 `className` 控制宽度、
  `style.backgroundColor = bgColor`），**不是位图**。

> 所以 `kb_bg.png` 只是产品图（配置字段 `keyboardImg`，用在首页/经典布局），
> **不存在「从图片反推 LED 索引」的隐藏表**。真正的位置信息在 `keyList` 的 `row/col/className` 里。

### 6.2 导出的映射表

`docs/lighting-modes.json` → `ledKeyMap.table`（87 条，含 `ledId/row/col/name/keyCode/key`），
`slotsWithoutKey` 列出 128 槽里没有物理键的 41 个。

MK87 的 `keyList` 是 **6 行**，`value` 按行优先递增（这里就是官方预览网格的行列顺序，也是 LED 序号顺序）：

| 行 | 槽位 → 键 |
|---|---|
| row0 (16) | `0`Esc, `1..12`F1–F12, `99`Print, `100`Scroll, `102`Pause |
| row1 (17) | `16` \` ~, `17..28` 1..0 - =, `92`Back, `103`Insert, `104`Home, `105`PgUp |
| row2 (17) | `32`Tab, `33..44` Q..] , `60` \ , `106`Del, `107`End, `108`PgDn |
| row3 (13) | `48`Caps, `49..59` A..' , `76`Enter |
| row4 (13) | `64`L-Shift, `65..75` Z../R-Shift, `90`↑ |
| row5 (11) | `80`L-Ctrl, `81`L-Win, `82`L-Alt, `83`Spacebar, `84`R-Alt, `85`Fn, `86`Super, `87`R-Ctrl, `88`←, `89`↓, `91`→ |

没有物理键的空槽位（41 个）：`13,14,15, 29,30,31, 45,46,47, 61,62,63, 77,78,79, 93,94,95,96,97,98, 101, 109..127`。

> 空槽位不是随机分布的：它们正好是每行末尾/固定列位置上「这块 87 键板没装键」的格子
> （例如 row0 的 13-15 是 F12 之后、row2 的 45-47 在 `\` 之前）。说明固件用的是与 98 键带屏机型
> 共用的固定矩阵，网页配置只是填了 87 个真实键。→ 推论：**LED 序号按同一个固定网格编号**，
> 而不是「87 个灯连续编号」。这一点对 §8-3 的验证很关键（要按上表逐格点，而不是 0..86 顺序数）。

（键名与槽位的完整机器可读版见 JSON；槽位与物理键的对应关系此前已由真机 `GET_KEY` 验证过，
见 `docs/keymap.md` / `docs/deepdive-mk87.md` §1。）

⚠️ **【推断】** 「LED 序号 = 矩阵槽位号」这一点只有 bundle 的逻辑证据，没有真机光学验证。
真机验证配方见 §8-3。

---

## 7. 参考实现与自检

```powershell
$node = 'C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
cd C:\Users\ptfm\Documents\ajazz-re

& $node scripts\lighting_ref.js               # 自检（默认）
& $node scripts\lighting_ref.js --verbose     # 每条用例都打印
& $node scripts\lighting_ref.js --dump        # 20 个模式的 16 字节样例
& $node scripts\lighting_ref.js encode '{"mode":7,"r":255,"g":128,"b":0,"brightness":6,"speed":2,"direction":1,"colorMode":0}'
& $node scripts\lighting_ref.js custom '[{"red":255,"green":0,"blue":0},{"red":0,"green":255,"blue":0}]'
```

自检不是「自己跟自己对」，而是**把 bundle 里官方函数源码原样截取出来 `new Function(...)` 执行**，
用假 `NX` 截获它真正要发给设备的字节，再与本实现逐字节 diff：

* `vZ` → `SET_LED_EFFECT` 16B（19+12 个模式 × 默认参数 + 边界 + 400 组随机 fuzz）
* `bZ` → `SET_CUSTOM_LED_DATA` 512B（128 满表/全 0/全 255/不足 128/超 128 截断/短字段名/`ledId≠下标`）
* `_Z` / `yZ` → 读回解码
* `UZ` / `MZ` → 动画通道 payload + 8 字节流式帧头（`AA 41 …` / `AA 42 …`）

### 7.1 实跑输出（2026-11-01 本轮）

```
== AJAZZ MK87 lighting_ref self-test ==
bundle: C:/Users/ptfm/Documents/ajazz-re/assets/layout-classic-CMxiG14P.js (3335710 bytes)

[1] encodeLedEffect  vs  bundle vZ (SET_LED_EFFECT 16B)
  PASS 真机回读交叉验证 (protocol.md §6): 01FFFFFFFF000000010503000000AA55
[2] buildCustomLedPayload  vs  bundle bZ (SET_CUSTOM_LED_DATA 512B)
  PASS 512B 里 index 字节写的是数组下标（不是颜色对象的 ledId）
  PASS parseCustomLedPayload 与官方 yZ 解码一致 (128×{ledId,red,green,blue})
[3] buildLedAnimationPayload  vs  bundle UZ/MZ (4B 前导 + RGB 帧流)
  PASS UZ 8 字节流式帧头 AA 41 seqHi seqLo totalHi totalLo 0 0
  PASS MZ 8 字节流式帧头 AA 42 seqHi seqLo totalHi totalLo 0 0
[4] 模式表 / 参数域自检
  PASS MK87 UI 模式列表 20 项全部有名称: 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,128
  PASS direction 0/1/2/3 原样落入 [11]（0=右 1=左 2=上 3=下）
  PASS brightness 1..6 落 [9]、0 也原样下发（协议不校验，UI 最小值为 1）

== 结果: PASS 453 / FAIL 0 ==
```

（`FAIL 0` 时进程退出码 0；有用例失败会打印 mine/official 两份 hex 并以退出码 1 结束。
本轮耗时 < 1s。）

### 7.2 `--dump` 节选

```
模式 | 名称 | 16 字节 payload（默认参数 colorMode=1,brightness=5,speed=3,direction=0）
  1 | 静态恒亮 | 01 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55
  7 | 动态呼吸 | 07 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55
 10 | 多彩纵横 | 0A FF FF FF FF 00 00 00 01 05 03 03 00 00 AA 55     ← direction 默认 3（向下）
128 | 自定义   | 80 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55
```

### 7.3 CLI 例子

```
& $node scripts\lighting_ref.js encode '{"mode":7,"r":255,"g":128,"b":0,"brightness":6,"speed":2,"direction":1,"colorMode":0}'
07 FF 80 00 FF 00 00 00 00 06 02 01 00 00 AA 55
```

> `r/g/b` 是参考实现提供的短别名（长名 `red/green/blue` 优先）；官方只认长名。
> `buildCustomLedPayload` 为了严格对齐官方，**不接受**短名（只给 `r/g/b` 会写 0，与官方一致）。

---

## 8. 待真机验证（按优先级）

1. **自定义模式族 20/21/128**：依次按 `Fn+1` / `Fn+2` / `Fn+3`，每次读 `GET_LED_EFFECT` 的 `[0]`。
   预期得到 20/21/128 的某个排列 → 即可确认 FUNC 71/72/98 与 mode 的对应关系。
   再写一次 `SET_CUSTOM_LED_DATA`（比如键 A 设红），看三个自定义档是否同时变 → 判断是否共用一张表。
2. **mode 0 与亮度 0**：发 `SET_LED_EFFECT` `brightness=0`（mode 保持 1），观察是否全灭；
   再发 `mode=0`。两种都灭则「亮度 0 = 关灯」成立；只有后者灭则确认必须用 mode 0。
3. **LED↔键光学验证**：把 87 个键逐个写成唯一颜色（如 `customLedData[i] = {red:255,green:0,blue:0}`，一次只点一个），
   看哪个物理键亮 → 得到真实 LED 序号。重点验 76/80/83/88-91 这几处（R-Shift/底排/方向键）是否与槽位一致。
4. **速度/亮度极值**：发 0 与 7（超范围）看固件是否 clamp（UI 只给 1..6）。
5. **`SET_CUSTOM_LED_DATA` 的 index 字节**：故意写 `index=i+1`，回读看设备是否原样存回
   （网页端永远写下标，所以这条只影响我们自己的写入策略）。
6. **音乐律动 v1**：装上 `Music.exe` 后抓 `127.0.0.1:9191` 的 HTTP，确认助手是直接对设备发
   `SET_MUSIC_DATA(53)` 还是自己走 HID（网页端没有发灯数据的代码路径）。

---

## 9. 复现步骤（从零）

```powershell
$node = 'C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
cd C:\Users\ptfm\Documents\ajazz-re

# 1) 抓缺失 chunk（纯 HTTP GET；已核对与本地 bundle 同一构建）
& $node scripts\lighting_fetch.js --index
& $node scripts\lighting_fetch.js lighting-DzPku7KQ.js lightingPane-J3Fl9UJi.js keyboard-BfmQGlU0.js `
    gifLighting-Ci_xahHI.js colorPicker-CPHEf-gj.js musicV1-BxjgapTH.js musicV2-Czdpb4b6.js `
    lightBox-kK-8jmZF.js sideLight-Cg0MWuKZ.js

# 2) 模式表求值 → JSON + 人读表
& $node scripts\lighting_modes.js

# 3) MK87 设备配置 + LED↔键表
& $node scripts\lighting_devicecfg.js

# 4) 合成 docs/lighting-modes.json
& $node scripts\lighting_gen_json.js

# 5) 自检
& $node scripts\lighting_ref.js

# 6) 定位任意证据（偏移 + 行号）
& $node scripts\lighting_dump.js ctx 2442358 300 600
& $node scripts\lighting_offsets.js "isCustomMode" "[20,21,128]" "ledId===e.value"
```

---

## 10. 仍未解 / 不确定

| # | 问题 | 现状 |
|---:|---|---|
| 1 | mode 20/21 与 FUNC 71/72/98 的一一对应 | bundle 只给 `[20,21,128]` 判定，无映射；需按 §8-1 验证 |
| 2 | 20/21/128 是否共用同一张 512B 表 | 【推断】共用（网页只维护一张表）；需真机验证 |
| 3 | `brightness=0` 是否等于关灯 | 协议不校验，UI 不可达；官方关灯走 `mode=0` |
| 4 | 87 个物理键的真实 LED 序号 | 【推断】= 矩阵槽位号；需 §8-3 逐点点亮 |
| 5 | `driverSetting`（payload[4]=255）的固件语义 | 写入恒 255、读回也是 255，含义未知 |
| 6 | 音乐律动 v1 助手是否自己发 HID | 网页端只发参数/几何，设备灯数据由助手负责【推断】 |
| 7 | `SET_LED_BOOT_ANIMATION(64)` 是否被固件接受 | enum 有、bundle 0 调用；未知 |
| 8 | `speedValue` 字段用途 | 全库 0 读取，判定为死字段（不排除固件侧有默认速度差异） |

### 补充（2026-11-01 真机）：槽 97 / 98 有驱动通道但无可见光

自定义模式下写 槽97=红、槽98=绿，`GET_ALL_LIGHTS_RGB` 回读确认缓冲里就是红/绿
（`(97,253,0,0)` / `(98,0,253,0)`），但人眼看不到任何绿色灯（红色只有 Fn 充电指示灯）。
⇒ 这两颗是**未装配或被外壳/屏幕遮挡的隐藏 LED 通道**；实际可见可控 LED = 84 颗实体键
（其中 Fn 键被充电指示灯强制红色）+ 品牌 logo 灯（跑马灯，由固件功能控制，不走逐键数据）。
