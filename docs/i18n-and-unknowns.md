# i18n 语言包获取 + 剩余未知项结论（AJAZZ MK87 / 网页驱动静态分析）

> 目标：把 `https://ajazz.driveall.cn` 网页驱动的官方 i18n 语言包抓下来，用它消除一批「语义未知」项；
> 并把仍不能静态定论的疑点整理成真机待测表。
> 本轮**只做静态分析 + 网络下载**，未打开任何 HID 设备。

**一句话结论**：语言包**不在** `layout-classic-*.js` 里，而是**每个 locale 一个独立懒加载 chunk**；
服务端还有一层 `/langs/<locale>.json` 覆盖（本站在线环境该路径返回 SPA 首页 → 不存在）。
已抓到 **zh + en 全量各 1196 键**，并用它把 MACRO / KEYBOARD / pageType 4-5-14 / TFT 头 / `tftDisplayTime` / music 插件这几项全部结论化（其中 1 项修正了旧文档的错误结论）。

---

## 0. TL;DR

| # | 问题 | 结论 | 证据 |
|---|---|---|---|
| 1 | 语言包在哪 | 独立 chunk：`assets/zh-BkYJTITw.js`、`assets/en-DU86yCXE.js`（另有 25 个 locale）；`$('key')` = vue-i18n `global.t` | bundle `@1025602`（locale switch）/ `@1027755`（`$=lH.global.t`） |
| 2 | 有没有运行时 API | 有覆盖层 `fetch(`${location.origin}/langs/${i18n}.json`)`，但**本站不存在**（返回 `text/html` 794B 首页），代码的 content-type 校验会丢弃 | `@1022282` / `@1013641` / `@953972`；实测见 §2 |
| 3 | MACRO `param2` | **0=常规(单次)**、**1=重复播放(循环)**、**2=再次按键结束(toggle)**；UI 下拉顺序是 0/2/1，别按顺序记 | `@2456960` 选项表 + `@2457429` 赋值 |
| 4 | MACRO `param3` | **仅在 `param2===1` 时 = 重复次数**，其余情况写 0 | `@2457429`：`param3:S.value===1?C.value:0` |
| 5 | KEYBOARD `param1` | **读**：非 0 时按修饰键位图查表（1/2/4/8/16/32/64）；**写**：官方编码器**从不写这一字节**（恒 0）。固件是否认它 → 真机 | `@1879846`（aX 表）/ `@1907668`（解码）/ `@1905312`（编码） |
| 6 | pageType 4 / 5 | **死代码**：只在枚举里出现，编码器无 case、解码器无 case、UI 无入口 → 永远不会被写出，写出来也解不出 | `@1905045` vs `@1905191` / `@1906065` |
| 7 | pageType 14 END | 编码只写 **3 字节**（`14,param1,param2`，param3 不写），解码回 `{param1,param2}`；UI 组件存在但只对 `advancedKeysConfig.advancedKeysList` 含 `END` 的机型开放，**MK87 没有** → 网页端不可用 | `@1905955` / `@1909715` / `@2120439` |
| 8 | TFT 动画头 `50 06` | 头 8 字节：`AA 50 seqLo seqHi totalLo totalHi 50 06`；`50 06` 是**硬编码常量**，不是 materialId（对比 `SET_TFT_MATERIAL` 的 byte6/7 = materialId 小端）。ACK 走 `0x41` | `@1946712` |
| 9 | `SET_TFT_BUILT_IN_INDEX` 映射 | 只有「槽位索引」没有「名称表」：上传动画**之前**发 1 字节索引，条件是 `tftConfig.builtInCount > 1`；**MK87 无 `builtInCount` → 官方从不发 0x51** | `@1947913` + MK87 配置 `@1194734` |
| 10 | `55 FA 06` | 设备状态通知：`55 FA <type> <payload...>`；`type=6` 时 `payload[0]===1` 做边沿检测 → **启/停 TFT 系统信息轮询**；只在 `tftConfig.isShowTftInfo===true` 时注册，**MK87 没有 → 不注册** | `@1949962` + 调用点 `@1838547` |
| 11 | `time_1` / `time_2` | **24 小时制 / 12 小时制**，不是「开/关」！UI 标题是 `TFT`+`show_time`，选项 `value:0→time_1(24小时)`、`value:1→time_2(12小时)`。故 `tftDisplayTime`：**0=24h、1=12h**（旧文档「1=显示时钟」是错的） | `@2508754` / `@1918703` |
| 12 | `music_mode_error*` | 官方 v1/v2 音乐律动**必须依赖本地插件**（浏览器拿不到系统音频）：插件基址 `http://127.0.0.1:9191`，下载地址 `https://config.driveall.cn/music/v2/Music.exe` | `@1801123` / `@1804231` |
| 13 | `nei-zhi` 是什么 | **内置（built-in）**；但这个 key 在 zh/en 语言包里**缺失**，官方 UI 会直接显示字面量 `nei-zhi`（共 17 个这种漏翻译 key） | `@2409893` / `@3277006`，见 §3.6 |

---

## 1. i18n 加载链（完整证据）

bundle：`assets/layout-classic-CMxiG14P.js`（3,302,270 字节，rolldown 打包，未混淆故保留字面量）。
**偏移均按本文件字节位置，bundle 更新后会漂移**，重新定位用 `scripts/_offsets.js`。

### 1.1 代码链（按执行顺序）

```
cL = {en:{i18n:`en`,dayjs:`en`,...}, zh:{i18n:`zh`,dayjs:`zh-cn`,...}, ...}   @~950517
  └─ 27 个 locale 的「locale 名 → dayjs 名 / naiveUI locale / browser 名」映射

lL = [{value:`zh`,label:`简体中文`},{value:`zh-TW`,label:`繁體中文`},...]      @~952638
  └─ 设置页语言下拉用的 {value,label} 列表

pL(e,t) = cL[e][t]                                                              @953972
XV(e)   = `${location.origin}/langs/${e}`                                       @1013641

iH(e,t)      深合并（数组直接替换、对象递归，服务端覆盖本地优先）                @1022066
aH(locale)   fetch(XV(`${pL(locale,'i18n')}.json`))，非 application/json 返回 null @1022282
cH(locale)   switch(locale){ case 'zh': return import('./zh-BkYJTITw.js').default; ... } @1025602
uH(locale)   本地包 = cH(); 服务端 = aH(); 有则 iH 合并 → setLocaleMessage(locale, 合并结果) @1027769
lH = createI18n({ locale, messages:{}, fallbackLocale:'en', ... })              @~1027700
$ = lH.global.t      ← 业务代码里的 $('macro_mask_select1')、$t('screen_text1') 都是它  @1027755
```

关键点：
- **`messages` 初始是空对象 `{}`**，所以 `macro_mask_select1` 在 layout chunk 里只出现 **1 次**（调用点），
  消息体在别的 chunk —— 这解释了为什么在 layout 里直接搜 key 只能搜到调用点。
- `cH()` 的 chunk 名表（同一 switch 内，`@1025602` 起）就是全部语言包文件名，见 §2.1。
- 服务端覆盖层是**可选**的：`aH()` 返回 `null` 或抛错时静默用本地包（`console.warn('从服务器加载语言包失败...')`）。
- `fH()` 里还有 `document.documentElement.setAttribute('lang', pL(locale,'browser'))`；
  若是 Electron 壳（`window.electronAPI`）还会把整包推给主进程。

### 1.2 语言列表有两处，别混

| 位置 | 内容 | 用途 |
|---|---|---|
| `lL` @~952638 | `{value,label}` 27 项（含 hu/tr/sr/hr/sl/mk/sq/ro/cs/uk） | 语言下拉选项 |
| 设置页 `y` computed @~2498898 | `'en,zh,zh-TW,ja,ko,fr,es,pt,ru,de,it,ar,vi,id,th,pt-BR,pl'.split(',')` 过滤 `lL` | **实际只暴露 17 种语言** |

即：语言包有 27 份，网页 UI 只让选 17 种（我们只关心 zh/en，都在 17 种内）。

---

## 2. 下载结果（`assets/i18n/`）

### 2.1 语言包 = 独立 chunk（chunk 名直接来自 bundle）

| locale | URL | HTTP | 字节 | 键数 |
|---|---|---|---|---|
| zh | `https://ajazz.driveall.cn/assets/zh-BkYJTITw.js` | 200 `application/javascript` | **77,755** | **1,196** |
| en | `https://ajazz.driveall.cn/assets/en-DU86yCXE.js` | 200 `application/javascript` | **84,817** | **1,196** |

其余 25 个（未下载，需要时 `node scripts/fetch_i18n.js <locale>` 即可）：
`zh-TW-BerMqD06.js`、`ja-BkmcTA5j.js`、`ko-BGJgjxXD.js`、`fr-Q3GqqbRr.js`、`es-DodscOn2.js`、
`pt-UTY4XCe4.js`、`ru-APbTdDYb.js`、`de-CoMCPMYw.js`、`it-COZIHFNy.js`、`ar-DUIncTbA.js`、
`vi-C18T211Z.js`、`id-COad8zkS.js`、`th-86cxy3Ij.js`、`pt-BR-DMrqZwyN.js`、`pl-B0KDO6NR.js`、
`hu-DlX73oy2.js`、`tr-BmpMbira.js`、`sr-mcLDeW7s.js`、`hr-BUlqktmB.js`、`sl-A-16hHi-.js`、
`mk-OmKfiNdd.js`、`sq-Go939iok.js`、`ro-NmpB1Fp2.js`、`cs-7fftMr4v.js`、`uk-CFN-y9PQ.js`

文件格式（ESM，模板字符串 + 命名导出，导出名就是 i18n key）：

```js
var ee=`修改密码`,te=`我的下载`,e=`密码限制6-25字符`, ...
export{ee as change_password,te as my_downloads,...,_ as macro_mask_select1,...}
```

→ 解析方式：把它当 ESM `import()`，导出命名空间就是 `{key: text}`（`scripts/fetch_i18n.js` 就是这么做的）。

### 2.2 服务端覆盖层：不存在（实测）

```
GET https://ajazz.driveall.cn/langs/zh.json → 200, content-type: text/html, 794 bytes
GET https://ajazz.driveall.cn/langs/en.json → 200, content-type: text/html, 794 bytes
内容 = 站点首页 index.html（SPA fallback）
```

代码里 `aH()` 明确检查 `if(!n || !n.includes('application/json')) return null` —— 所以这两条 200 会被丢弃，
**在线环境只吃本地 chunk**。`assets/i18n/_manifest.json` 里保留了这条探测记录（`serverOverlay.hit=false`）。
> 注意：`config.driveall.cn`（另一个域）走的是配置接口，与 i18n 无关，不要混淆。

### 2.3 产物清单

```
assets/i18n/zh.js            中文 chunk 原文（77,755 B）
assets/i18n/en.js            英文 chunk 原文（84,817 B）
assets/i18n/zh.json          解析后扁平 {key: 中文}
assets/i18n/en.json          解析后扁平 {key: 英文}
assets/i18n/_manifest.json   URL / 字节 / 键数 / 覆盖层探测结果
docs/i18n-keys.json          ★ 交付物：1196 个 key → {zh, en}（按 key 排序）
docs/func-i18n-map.json      附赠：FUNC(292)/FUNC_V2(62) 动作 id ↔ 官方中英文案 + MK87 FN 层实际用到的 28 个
```

`docs/i18n-keys.json` 结构（整包导出，按 key 索引，缺某语言时该字段不存在）：

```json
{
  "macro_mask_select1": { "zh": "常规", "en": "Routine" },
  "time_1":             { "zh": "24小时", "en": "24 Hour" }
}
```

---

## 3. 目标键速查（中 / 英）

### 3.1 MACRO（决定 pageType=6 的 param2/param3）

| key | zh | en |
|---|---|---|
| `macro_mask_select1` | 常规 | Routine |
| `macro_mask_select2` | 再次按键结束 | Press the key again to end |
| `macro_mask_select3` | 重复播放 | Repeat Playback |
| `macro_mask_select4` | 持有 | Hold |
| `macro_mask_title` | 添加快捷指令 | Add shortcut |
| `macro_mask_text` | 快捷指令,需要先录制快捷指令，然后在这里选择指定快捷指令配给键盘 | For shortcuts, you need to record the shortcuts first, and then choose to assign the shortcuts to the keyboard here. |
| `macro_select1` | 在动作列表光标条上方插入 | Insert above the action list cursor bar |
| `macro_select2` | 在动作列表光标条下方插入 | Insert below the action list cursor bar |
| `macro_repeat` | 重复次数 | Repeat Count |
| `macro_repeat_start` / `macro_repeat_end` | 开始录制 / 结束录制 | Start/End Recording |
| `macro_repeat_select1` | 记录输入间隔时间 | Record input interval time |
| `macro_repeat_select2` | 不记录输入间隔时间 | Do not record input interval time |
| `macro_repeat_select3` | 默认间隔 | Default Interval |
| `macro_repeat_select4` | 毫秒 | Milliseconds |
| `macro_msg_select` | 请选择快捷指令！！！ | Please select a shortcut! ! ! |
| `macro_msg_del` | 请选择删除键盘上的快捷指令键 | Please choose to delete the shortcut key on your keyboard |
| `macro_memory` | 快捷指令内存不足！！！ | Insufficient memory for shortcut commands! ! ! |
| `macro_install` / `macro_save` / `macro_success` | 插入 / 保存 / 操作成功！！！ | Insert / Save / Operation successful!!! |

> ⚠️ 两个「名字骗人」的键：
> `macro_select1/2` **不是**选择模式，而是「宏动作列表里向上/向下插入」；
> `macro_repeat*` **不是**绑定参数，而是「录制时的间隔记录选项」。
> 真正的绑定模式只有 `macro_mask_select1/2/3`（下拉 3 项），`macro_mask_select4`(持有) 在本 bundle 里**未被引用**（保留给别的机型/固件）。

### 3.2 屏幕 / 时间

| key | zh | en |
|---|---|---|
| `time_1` | 24小时 | 24 Hour |
| `time_2` | 12小时 | 12 Hour |
| `show_time` | 显示时间 | Show Time |
| `icon_6` | 音乐律动 | Musical Rhythm |
| `nei-zhi` | ⚠️ **语言包里没有这个键**（见 §3.6）；由两处用法可确定语义 = **内置** | （缺失） |
| `screen_text1` | LED屏幕预览 | LED Screen Preview |
| `screen_text2` | 视频库 | Video Library |
| `screen_text3` | 帧 | Frame |
| `screen_text4` | 上传到键盘 | Upload to Keyboard |
| `screen_text5` | 时间校正 | Time Correction |
| `screen_text6` | 上传中，请耐心等待... | Uploading, please wait patiently... |
| `screen_text7` | 无效的图片文件：没有找到有效帧 | Invalid image file: no valid frame found |
| `screen_text8` | 成功导入图片，共 | Pictures imported successfully, total |
| `screen_text9` | 图片解析失败：未能提取有效帧 | Image parsing failed: Failed to extract valid frame |
| `screen_text10` | GIF处理失败： | GIF processing failed: |
| `screen_text11` | 最大支持 | Maximum supported |
| `screen_text12` | 帧，是否继续? | frames, continue? |
| `screen_text13` | 未找到可用设备 | No available devices found |
| `screen_text14` | 应用失败 | Application failed |
| `screen_text15` | 是否删除该视频? | Do you want to delete this video? |
| `screen_text16` | 至少需要保留一帧 | At least one frame needs to be retained |
| `screen_text17` | 确定要删除当前帧吗？ | Are you sure you want to delete the current frame? |
| `screen_text18` | 正在加载默认动画... | Loading default animations... |
| `screen_text19` | 暂无动画 | No animation yet |
| `screen_text20` | 请导入图片文件 | Please import image files |
| `screen_text21` | 正在转换视频，请稍候... | Converting video, please wait... |
| `screen_text22` | 这可能需要一些时间，请不要关闭页面 | This may take some time, please do not close the page |
| `screen_text23` | 视频转换失败 | Video conversion failed |

### 3.3 音乐律动（`music_*`，68 个键中的关键几条）

| key | zh | en |
|---|---|---|
| `music_text` | 因为网页限制无法捕捉设备音频。请下载专属插件实现音乐律动 | Due to web restrictions, device audio cannot be captured. Please download the dedicated plugin to enable music rhythm. |
| `music_mode_error` | 请下载插件，如下载请手动执行该插件 | Please download the plugin. If downloaded, please manually execute the plugin. |
| `music_mode_error2` | 仅限于win系统运行 | Only running on win system |
| `music_btn` | 下载插件 | Download Plugin |
| `music_btn2` | 重新连接 | Reconnect |
| `music_diy` | 音乐律动 DIY | Musical Groove DIY |
| `music_diy_audio` | 音频 | Audio |
| `music_diy_plugin_ready` | 音乐插件已连接 | Music plug-in is connected |
| `music_diy_test_mode` | 测试模式 | test mode |
| `music_diy_shape(s)` / `_limit` | 形状 / 最多可添加{0}个形状 | shape / Up to {0} shapes can be added |
| `music_text1` | 显示模式 | Display Mode |
| `music_text2` | 背景灯光显示模式 | Background Lighting Display Mode |
| `music_text3` | 振幅 | Amplitude |
| `music_text4` | 背景亮度 | Background Brightness |
| `music_mode_text1` | 绿色/黄色/红色 | Green/Yellow/Red |
| `music_mode_text2` | 彩虹色 | Rainbow |
| `music_mode_text3` | 随曲起舞 | Dance to the Beat |
| `music_mode_text4` | 曲率频阶 | Curvature Frequency Steps |
| `music_mode_text5` | 频谱循环 | Spectrum Cycle |
| `music_mode_text6..11` | 白/红/橙/黄/绿/蓝 | White/Red/Orange/Yellow/Green/Blue |
| `music_mode_text12..21` | 尘埃光漩 / 蛰伏火山 / 光矢穿心 / 萤火轨迹 / 光茧共振 / 音叉振空 / 曲率遗轨 / 行波律动 / 双心共舞 / 屏光联动 | Dust Glow Spiral / Dormant Volcano / Light Arrow Piercing / Firefly Trail / Light Cocoon Resonance / Tuning Fork Vibration / Curvature Legacy Track / Row Wave Rhythm / Dual Heart Dance / Screen light linkage |

完整 68 条见 `docs/i18n-keys.json`（`music_*` 前缀）。

### 3.4 灯效

| key | zh | en |
|---|---|---|
| `lighting` | 灯光效果 | Lighting Effects |
| `lighting_brightness` | 亮度 | Brightness |
| `lighting_speed` | 速度 | Speed |
| `lighting_direction` | 方向 | Direction |
| `lighting_color` / `lighting_color_mode` | 颜色 / 颜色模式 | Color / Color Mode |
| `lighting_single_color` / `lighting_rgb_select` | 单色 / RGB选择 | Single color / RGB Select |
| `lighting_main_rgb` / `lighting_secondary_rgb` | 主灯区颜色 / 副灯区颜色 | Main RGB / Secondary RGB |
| `lighting_edit` | 编辑 | Edit |
| `side_light` | 侧灯灯效 | Side light effect |
| `light_box` | 灯箱灯效 | Light box light effect |
| `lighting_icon1..42` | 静态恒亮 / 多彩纵横 / 随波逐流 / 峰回路转 / 一触即发 / 一石二鸟 / 涟漪扩散 / 川流不息 / 重峦叠嶂 / 斜风细雨 … | （同上，英文如 Static / Colorful Crisscross / Drifting …） |
| `lighting_icon20` | 自定义 | Custom |

`lighting_icon1..42` 是 42 种灯效模式的**显示名**；模式编号 ↔ 名称的映射表由协议模块
（`../config/protocols/<protocol>/lighting`，运行时由 `nY()` 动态解析）提供，**不在 layout 顶层**，
本次没有展开（与 MK87 协议无关：MK87 用的是 `GET_LED_EFFECT` 的 mode 字段，见 `docs/protocol.md`）。

### 3.5 `fun_text*` / `fun2_*` / `medium_text*` 与 FUNC 表对照

- 语言包里：`fun_text1..245`（**缺 222**，共 244 个）、`fun2_*` 46 个、`medium_text*` 18 个。
- `FUNC` 表（`sX`，292 条）+ `FUNC_V2` 表（`lX`，62 条）共引用 **316 个** i18n key。
- 交叉校验结果：**315 个能对上，1 个缺 key** —— `FUNC id 265 (CTRL+X)` 引用 `fun_text222`，而语言包里没有这个键
  → 官方 UI 会把 `fun_text222` 原样显示出来（官方 bundle 自身的小 bug/漏翻译）。
- 已导出 `docs/func-i18n-map.json`，含：
  `FUNC`/`FUNC_V2` 全表 id→{官方中文名, i18nKey, zh, en, keyType}，以及 **MK87 FN 层实际用到的 28 个动作**。

MK87 FN 层用到的 28 个动作（真机解码 `docs/fn-layer-decode.json` × 语言包）：

| FUNC id | 官方名（bundle） | zh（语言包） | en（语言包） | 绑定键（真机 FN 层） |
|---|---|---|---|---|
| 1 | 恢复出厂设置 | 恢复出厂设置 | Restore Factory Settings | Spacebar |
| 2 | 蓝牙通道1 | 蓝牙通道1 | Bluetooth Channel 1 | Q |
| 3 | 蓝牙通道2 | 蓝牙通道2 | Bluetooth Channel 2 | W |
| 4 | 蓝牙通道3 | 蓝牙通道3 | Bluetooth Channel 3 | E |
| 5 | 无线回连 | 无线回连 | Wireless Reconnect | R |
| 7 | 查询电量 | 查询电量 | Check Battery | Back |
| 11 | 灯光效果切换 | 灯光效果切换 | Light Effect Switch | 反斜杠键 |
| 12 | 灯光颜色切换 | 灯光颜色切换 | Light Color Switch | → |
| 13 | 灯光亮度+ | 灯光亮度+ | Increase Light Brightness | ↑ |
| 14 | 灯光亮度- | 灯光亮度- | Decrease Light Brightness | ↓ |
| 15 | 灯光速度+ | 灯光速度+ | Increase Light Speed | = + |
| 16 | 灯光速度- | 灯光速度- | Decrease Light Speed | ˉ - |
| 17 | 关闭灯光 | 关闭灯光 | Turn Off Lights | X |
| 22 | 锁定Win | 锁定Win | Lock Win | L-Win |
| 23 | 侧灯效果切换 | 侧灯效果切换 | Side Light Effect Switch | Enter |
| 24 | 侧灯颜色切换 | 侧灯颜色切换 | Side Light Color Switch | ' " |
| 39 | 关闭屏幕 | 关闭屏幕 | Turn Off Screen | Insert |
| 46 | 旋钮模式切换 | 旋钮模式切换 | Knob Mode Switch | （该槽位不在 keyList 内，无键名） |
| 63 | GIF模式 | GIF模式 | GIF Mode | Home |
| 71 | 自定义灯光1 | 自定义灯光1 | Custom Lights 1 | 1 ! |
| 72 | 自定义灯光2 | 自定义灯光2 | Custom Lights 2 | 2 @ |
| 78 | 切换灯效方向 | 切换灯效方向 | Switch the lighting effect direction | ← |
| 84 | 显示屏语言切换为汉语 | 显示屏语言切换为汉语 | Switch the display language to Chinese | C |
| 85 | 显示屏语言切换为英语 | 显示屏语言切换为英语 | Switch the display language to English | V |
| 89 | LOGO LED ON/OFF | ⚠️ 该条**没有 i18n key**（用内置名） | — | Del |
| 98 | 自定义灯光3 | 自定义灯光3 | Custom Lights 3 | 3 # |
| 99 | 自定义灯光录制 | 自定义灯光录制 | Custom light recording | ` ~ |
| 138 | 开启屏幕下方按键灯 | 开启屏幕下方按键灯 | Turn on the button light below the screen | End |

> 语言包与 bundle 内置中文名**逐条一致**（315/316），说明官方 FUNC 表就是照这套 i18n 写的 ——
> 因此 `docs/keymap-tables.json` 里那 292 条动作名可信度很高。

### 3.6 反向审计：**被 bundle 引用、但语言包里缺失的 key**（官方 UI 会显示原始 key）

用 `scripts/audit_i18n_keys.js` 扫全部 13 个官方 chunk 的 `$(` / `$t(` 字面量，与语言包对比：
**444 个字面 key 被引用，其中 17 个在 zh/en 语言包里不存在**（`fallbackLocale:'en'` 也没有 → 必然露出原始 key）：

| 缺失 key | 出现处 | 推断语义（由调用上下文） |
|---|---|---|
| `nei-zhi` | `@2409893` 灯效预设按钮：`isBuiltIn ? $t('nei-zhi') : $t('lighting_icon20')`；`@3277006` 视频库内置页签：`$t('nei-zhi') + index` | **内置**。这两处直接把 `nei-zhi` 与「自定义(`lighting_icon20`)」对立使用，且拼成「内置1/内置2」→ 语义确定 |
| `dian-zhen-ping-xian-shi-mo-shi` | 键位动作/提示 | 点阵屏显示模式 |
| `dang-qian-an-jian-bu-zhi-chi-hong-lu-zhi` | 宏录制提示 | 当前按键不支持宏录制 |
| `mei-you-dong-zuo-ke-qing-kong` | 宏编辑 | 没有动作可清空 |
| `qing-xian-xuan-ze-yao-shan-chu-de-dong-zuo` | 宏编辑 | 请先选择要删除的动作 |
| `qing-xian-xuan-ze-yao-yi-dong-de-dong-zuo` | 宏编辑 | 请先选择要移动的动作 |
| `que-ren-shan-chu` / `que-ren-shan-chu-gai-hong` | 对话框 | 确认删除 / 确认删除该宏 |
| `yi-cun-zai` | 导入校验 | 已存在 |
| `continue` | 通用按钮 | 继续 |
| `docs-btn` | 帮助/文档按钮 | 文档 |
| `forget-reset-success` | 忘记密码/重置 | 重置成功 |
| `bluetooth-nonsupport-tips` | 连接页 | 蓝牙不支持提示 |
| `led-max-frame-limit` | 灯效动画编辑 | 灯效帧数上限 |
| `max-bind-keys-tips` | 高级键编辑 | 最多可绑定 N 个键 |
| `ai-lighting` / `ai-lighting-material` | AI 灯效 tab | AI 灯效 / AI 灯效素材 |

> 这批是**官方漏翻译**（或打包版本不一致），不是我们抓漏：`zh.js` 里确实没有这些导出名。
> 对逆向的意义：见到这些 pinyin key 不要当成「协议字段」，它们只是没翻译的 UI 文案。
> 复核：`node scripts/audit_i18n_keys.js`。

---

## 4. 剩余未知项：逐条结论

### 4.1 MACRO pageType（6）的 `param2` / `param3` —— ✅ 已确定

绑定宏时构造的 userKey（`@2457429`，宏页 `E()`）：

```js
let e = {
  name: w.value.name,
  page: 'MACRO',
  param1: w.value.id,                     // 宏 id
  param2: S.value,                        // 模式
  param3: S.value === 1 ? C.value : 0,    // 只有「重复播放」才写重复次数
  value: w.value.id                       // 与 param1 相同
};
```

模式下拉（`@2456960`，注意 UI 的值顺序是 **0,2,1**）：

```js
x = computed(() => [
  { label: $('macro_mask_select1'), value: 0 },   // 常规          → 单次播放
  { label: $('macro_mask_select2'), value: 2 },   // 再次按键结束  → toggle
  { label: $('macro_mask_select3'), value: 1 },   // 重复播放      → 循环
]);
S = ref(0);   // param2 默认 0
C = ref(1);   // 重复次数默认 1
```

编码/解码：
- 编码 `pX` `@1905436`：`case 'MACRO'` 与 MT/SOCD/RS/CB/MPT 共用
  `e[t]=6; e[t+1]=param1; e[t+2]=param2; e[t+3]=param3;`（4 字节全写）
- 解码 `bX` `@1908181`：原样回读 `{param1, param2, param3}`，不改写

**结论**：

| param2 | 含义 | param3 |
|---|---|---|
| 0 | 常规（按一下播一次） | 0 |
| 1 | 重复播放（循环） | **重复次数**（1..N，1 字节） |
| 2 | 再次按键结束（按一下开始、再按一下停） | 0 |

- `macro_mask_select4`（持有 / Hold）语言包里有，但 **bundle 无任何引用** → 该机型不支持，属于其它固件/机型的保留项。
- 真机侧仍建议确认：模式 2 的「再次按键结束」在固件里是否真的表现为 toggle（驱动只负责写，行为由固件解释）。

### 4.2 KEYBOARD pageType（2）的 `param1` —— ✅ 读语义确定；写入「无意义」但固件行为未定

解码 `vX` `@1907668`：

```js
vX = (e, t) => {
  let { param1: n, param2: r } = e;
  if (n !== 0) { let e = aX.find(e => e.param1 === n); if (e) return e; }   // ← param1 优先！
  if (r !== 0) { let e = iX.find(e => e.value === r); ... }                // ← 否则用 param2 查 HID usage
}
```

`aX`（extendChars，`@1879846`）里只有 7 个条目带 `param1`，就是**修饰键位图**：

| param1 | 键 | value(HID usage) |
|---|---|---|
| 1 | L-Ctrl | 224 |
| 2 | L-Shift | 225 |
| 4 | L-Alt | 226 |
| 8 | L-Win | 227 |
| 16 | R-Ctrl | 228 |
| 32 | R-Shift | 229 |
| 64 | R-Alt | 230 |

即：**param1 是「修饰键位图」，非 0 时 param2 被忽略**。

但编码 `pX` `@1905312` 对 KEYBOARD 只写两个字节：

```js
case 'KEYBOARD': e[t] = 2, e[t + 2] = n.value || 0;   // ← e[t+1] (param1) 根本不写，保持缓冲区的 0
```

**结论**：
- 官方驱动**从不写** `param1`；一个修饰键被写成 `02 00 E1 00`（param1=0, param2=usage），
  读回时走 `param2` 分支（`aX.find(x=>x.value===224)`）也能正确识别 → 官方自己不需要 param1。
- 所以「写入 param1 是否有意义」= **对官方驱动无意义**；但**固件是否认这一字节，静态无法证明**
  （协议层允许，值域 1/2/4/8/16/32/64 很可能被固件当修饰位图）。→ 真机可测（见 §5）。
- 附带风险：由于读路径 `param1` 优先，若你写入 `param1≠0 且 param2≠0`，官方 UI 会显示成修饰键而丢掉 param2 —— 这是**网页端**的行为，不是固件行为。

### 4.3 pageType 4 SYSTEM_KEY / 5 EXTRA_FUNCTION / 14 END

枚举（`fX`，`@1905045`）：

```js
fX = {DEFAULT:0, MOUSE:1, KEYBOARD:2, CONSUMER_KEY:3, SYSTEM_KEY:4, EXTRA_FUNCTION:5,
      MACRO:6, CB:7, DKS:8, MT:9, TGL:10, SOCD:11, RS:12, FUNC:13, END:14, MPT:15};
```

**4 / 5 = 死代码**，三处证据：
1. 编码器 `pX`（`@1905191`）的 `switch(n.page)` **没有** `SYSTEM_KEY` / `EXTRA_FUNCTION` 分支，
   落到 `default: console.warn('未知的页面类型: ...')` → 一个字节都不写；
2. 解码器 `mX`（`@1906065`）的 `switch(e.pageType)` 也**没有** case 4/5 → `console.warn('未知的页面类型')` 并 `return undefined`；
3. 全 bundle 里 `SYSTEM_KEY` / `EXTRA_FUNCTION` 各只出现 **1 次**（就上面那行枚举），
   没有任何 UI 选项、列表条目、i18n key 引用它们。

**14 END = 有实现但只对特定机型开放**：
- 编码（`@1905955`）：`case 'END': e[t]=14, e[t+1]=param1||0, e[t+2]=param2||0;` —— **param3 不写**（只占 3 字节）；
- 解码（`AX`，`@1909715`）：`return {name:'END', page:'END', param1, param2}` —— 只有两参；
- UI 组件挂在高级键注册表 `{RS,SOCD,DKS,MT,TGL,CB,END,MPT}`（`@2120439`），
  但只有 `advancedKeysConfig.advancedKeysList` 里含 `END` 的机型才会出现该 pane；
- **MK87 的 `routesName` = `['customKeys','lighting','macro','tft','settings']`（无 `advancedKeys`），也没有 `advancedKeysConfig`**
  → 网页端对 MK87 完全不暴露 END。

**结论**：4/5 可以当「不存在」处理（既不会出现也不会被解释）；14 是「双键/顺序按键」类动作，
结构 = `[14, param1, param2]`，`param1/param2` 的**具体含义（两个 HID usage？两个键位 id？延迟在哪？）静态无解**
—— 编码器只是原样搬运 UI 传进来的两个参数，而 MK87 拿不到那个 UI。→ 真机/磁轴机型才能验证。

### 4.4 TFT：`50 06` 头、`SET_TFT_BUILT_IN_INDEX`、`55 FA 06` 通知

#### (a) 动画头 `AA 50 … 50 06`（`@1946712`，`GZ = setTftUserAnimation`）

```js
let i = new Uint8Array(8).fill(0);
i[0]=170;                       // 0xAA
i[1]=HX.SET_TFT_USER_ANIMATION; // 0x50
i[2]=seq&255; i[3]=seq>>8;      // 包序号
i[4]=total&255; i[5]=total>>8;  // 总包数
i[6]=80; i[7]=6;                // ← 固定 0x50, 0x06
await NX(s,{cmd:0x50, contentSize:4096, data:t, headerCount:8, customHeader:i,
            timeout:2000, responseCmd:HX.SET_LED_USER_ANIMATION /* 0x41 */});
```

对比壁纸命令 `KZ = setTftMaterial`：`l[6]=materialId&255; l[7]=materialId>>8`（**materialId 小端**）。
所以动画头的 `50 06` 在**结构位置上等价于 materialId**，但值是常量 `0x0650 = 1616`。

**结论**：
- 事实层面确定：`[6]=0x50`（= 命令字回显）、`[7]=0x06`，**硬编码，不随任何 UI 变化**。
- 推断（标注为推断）：`0x0650` 很可能是固件约定的「用户动画」素材/类型号（1616），
  固件靠它区分「这条 0x50 通道写的是用户动画」；**静态不能证明固件把它当类型号还是当 magic**。
- ACK 走 `SET_LED_USER_ANIMATION` = **0x41**（`responseCmd` 显式指定），与 `docs/deepdive-mk87.md` 记录一致。

#### (b) `SET_TFT_BUILT_IN_INDEX`（0x51）—— 只有槽位索引，没有名称表

功能函数 `qZ`（`@1947913`）：

```js
a = new Uint8Array(1); a[0] = index & 255;
await NX(tftDevice, {cmd: 0x51, contentSize: 1, data: a, timeout: frameVersion===1?2000:50, maxRetries: 0});
// 注意：USB 连接时先 LX(productId) 取 usagePage=0xFF67 的 TFT 接口再发
```

调用点（`@3268948`，TFT 页 `le()` 保存动画时）：

```js
l.value?.builtInCount && l.value.builtInCount > 1 && await n('setTftBuiltInIndex', void 0, C.value);
// 发完索引 → 再 GZ() 上传用户动画
```

`builtInCount` 来自 `tftConfig.builtInCount`（`S = ref(tftConfig.builtInCount || 1)`，`C = ref(1)`），
即：**「机内有 N 个内置动画槽，先把槽位索引告诉固件，再把动画写进该槽」**。

**结论**：
- 0x51 的语义 = **选择内置动画槽位**（1 字节），不是「选择某个内置动画内容」；
  bundle 里**不存在** index→名称的映射表，所以「索引 1/2/3 分别是什么动画」只能看设备实际显示。
- **MK87 的 `tftConfig` 没有 `builtInCount`**（`@1194734`：`{name:'AK980_PRO', localforageKey:'w240h135', width:240, height:135}`）
  → `builtInCount>1` 为假 → **官方网页驱动对 MK87 从不发 0x51**；内置页/时钟页切换是设备端行为
  （与 `docs/tft-page.md`/`deepdive` 一致，本次从代码再次确认）。

#### (c) `55 FA 06` 通知

解析器 `XZ = startDeviceStateListener`（`@1949962`）：

```js
XZ = (device, _, type, cb) => {
  const h = (ev) => {
    const r = new Uint8Array(ev.data.buffer);
    if (r.length >= 4 && r[0] === 85 /*0x55*/ && r[1] === HX.GET_DEVICE_NOTIFY /*0xFA*/ && r[2] === type)
      cb(r);
  };
  device.addEventListener('inputreport', h); ...
}
```

调用点（`@1838547`，WebHID store 的 `P(e)`）：

```js
let n = await c('startDeviceStateListener', e, 6, (frame) => {
  const charging = frame[3] === 1;          // ← 第 1 个 payload 字节
  if (charging !== last) { last = charging; charging ? startGetTftInfo() : stopGetTftInfo(); }
});
// 且仅在 keyboardConfig.tftConfig.isShowTftInfo === true 时才注册这个监听
```

**结论**：
- 帧格式：`55 FA <type> <payload...>`（WebHID 的 `data` 不含 report ID，`[0]` 直接是 0x55）。
- `55 FA 06` = `cmd=0xFA(GET_DEVICE_NOTIFY)`、`type=6`、`payload[0]` 是状态位；
  官方用法是**边沿检测 → 开始/停止 TFT 系统信息（CPU/GPU/温度/天气）轮询**。
- payload[0]==1 到底是「充电中」还是「USB 已连接」：代码里没有命名（只叫 `charging` 是我按语义取的变量名），
  但结合它触发的是 `startGetTftInfo()`（该轮询依赖本地插件读硬件信息）→ **更可能是「USB/有线连接」状态**。
  **静态不能定论 → 真机可测**（见 §5）。
- **MK87 的 `tftConfig` 没有 `isShowTftInfo`** → 网页端对 MK87 **不注册**这个监听，所以真机即使有 `55 FA 06` 也没人接。

顺带补全**设备通知/状态帧全表**（同一 store 里四个监听器）：

| 帧 | 监听器 | 触发 | 备注 |
|---|---|---|---|
| `55 FA 06 <b0> …` | `XZ` `@1949962` | 设备状态变化（b0 边沿） | 仅 `tftConfig.isShowTftInfo` 机型注册 |
| `55 FC 05` | `ZX` `@1919911` | 重置（恢复出厂等） | 回调 `location.reload()` |
| `55 FC 06` | `QX` `@1920304` | 2.4G 休眠 | 仅 `connectType==='2.4G'` |
| `A6 FF 01` | `$X` `@~1920800` | 2.4G 唤醒 | **完全不同的头**，不是 55 系 |

### 4.5 `tftDisplayTime` 与 `time_1/time_2` —— ✅ 已确定（**修正旧结论**）

读写（`@1918219` / `@1918703`，GET/SET_GAME_MODE 的 56 字节 payload）：

```js
// 读
i = {..., tftDisplayTime: r[7], ...}          // byte 7
// 写
a[7] = i.tftDisplayTime || 0;                 // byte 7
```

官方 UI（settings 页，`@2508754`）：

```js
settingsConfig?.isShowTftTimeMode ? (
  <h3>TFT + $t('show_time')</h3>               // 「TFT显示时间」
  <RadioGroup value={tftTimeMode}>
    <Radio value={0}>$t('time_1')</Radio>      // 24小时 / 24 Hour
    <Radio value={1}>$t('time_2')</Radio>      // 12小时 / 12 Hour
  </RadioGroup>
) : null
// 保存时： e.tftDisplayTime = tftTimeMode.value
```

**结论**：
- `time_1` = 24 小时制、`time_2` = 12 小时制；因此 **`tftDisplayTime` 是「12/24 小时制」选择器，不是开关**：
  **0 = 24 小时制（默认），1 = 12 小时制**。
- 旧文档 `docs/deepdive-mk87.md` §4 写「1 = 屏幕显示时钟（本次实测当前为 0）」——**该结论应更正**为
  「1 = 12 小时制」。当时推测为「显示开关」是因为 UI 标题写「显示时间」且只有两档。
- 对 MK87 的额外事实：`settingsConfig` 里**没有 `isShowTftTimeMode`**（`@1194734`）→ 该单选项在 MK87 页面上**不显示**；
  但保存设置时 `e.tftDisplayTime = tftTimeMode.value` 会**原值回写**（read 时 `r[7]` → 原样写回），即网页端不会改变它。
- 固件是否真按 12/24 渲染时钟：静态无法证明（这层 UI 本来也不是 MK87 的）。→ 真机可测。

### 4.6 `music_mode_error*` 与「本地插件」—— ✅ 已确定

文案（见 §3.3）：`music_mode_error` = 请下载插件…；`music_mode_error2` = **仅限于win系统运行**；
`music_text` = **因为网页限制无法捕捉设备音频。请下载专属插件实现音乐律动**。

插件机制（`@1801123` 起）：

```js
xY = 'http://127.0.0.1:9191';             // 本地插件 HTTP 基址，所有请求 timeout 500ms
CY(data) => GET /api/keyboard/layout/base64?data=<b64>   // 把键盘布局推给插件
wY()     => GET /api/keyboard/musiceffect/               // 探测插件是否在线（hasDownloadPlugin）
TY(p)    => GET /api/keyboard/musiceffect?param=<p>      // 设置律动参数
EY()     => GET /api/keyboard/musiceffect/close/         // 关闭
DY()     => GET /api/audio/amplitude                     // ★ 拿音频幅度 low/mid/high
OY()     => GET /api/hardware/info                       // CPU/GPU/温度（TFT 系统信息用）
```

下载地址（`@1804231`，两处 `$dialog` / 按钮点击都一样）：

```js
EV('https://config.driveall.cn/music/v2/Music.exe')
```

界面逻辑（`musicV1` `D7` `@2301378`、`musicV2`、`musicDiy`）：
- `hasDownloadPlugin === true` → 显示完整配置面板（模式/振幅/背景/亮度 + 形状 DIY + 测试模式）；
- `hasDownloadPlugin === false` → 整个面板被替换成
  `music_mode_error` + `music_mode_error2` + [重新连接] + [下载插件] 两行两按钮；
- 有个「无需插件」的测试入口，但 **正式构建里 `isTestMode:false` 被写死**
  （`return {..., isTestMode:!1, ...}`），按钮不会渲染 → 生产环境无「不装插件也能用」的路径。

**结论**：
- **官方 v1 音乐律动必须依赖本地插件（Music.exe）**：浏览器无法采集系统音频，插件负责采音 → 算幅度 → 再经
  `SET_MUSIC_DATA(0x35)` / `SET_MUSIC_DATA_24G_64_BYTE(0x3C)` 写灯（v2 还有 `setLedSyncAnimation` 之类的整帧推流）。
- 插件**只支持 Windows**（`music_mode_error2` 文案直说），且是 `.exe`，非开源、无协议文档。
- 因此「纯网页 / 纯 HID 复刻」在 v1 音乐律动上**不可能绕过插件拿到音频**；但**协议本身不依赖插件**：
  `SET_MUSIC_DATA` 只是一个普通命令，谁算出幅度谁就能发。我们完全可以自己采音后直接调用该命令（需真机验证帧格式）。
- v1 与 v2 的差别（`musicConfig.version`）：v1 = 单色/彩虹等 13 种固定模式 + 振幅/背景亮度；
  v2 = 多列频段 + `keyOffset` 列偏移 + DIY 形状 + AI 灯效。二者都要插件。

### 4.7 顺带修正：MK87 的 `musicConfig` 不是 `null`

`docs/device_config_32839.json` 里写 `musicConfig: null`（据此 `docs/deepdive-mk87.md` 推断「MK87 无音乐页」）。
**当前线上 bundle** 的 MK87 配置（`@1194734`）实际是：

```js
TU = {vendorId:3141, productId:32839, supplierName:'ajazz', name:'AJAZZ KEYBOARD', connectType:'USB',
  routesName:['customKeys','lighting','macro','tft','settings'],
  customKeysConfig:{isShowFn:!0,isShowNormalFuncKeys:!0,fnFuncIds:[],fnDisabledKeyIds:[1..12]},
  lightingConfig:{minBrightness:1,maxBrightness:6,minSpeed:1,maxSpeed:6,
                  isShowLightBox:!1,lightBoxList:[1,2,3,5],isShowLightBoxEdit:!0},
  musicConfig:{version:1,maxColOffset:0,keyOffset:[{F1,1,1},{Z,65,1},{↑,90,2},{Spacebar,83,3},{R-Alt,84,3}]},
  macroConfig:{isShowFn:!0},
  tftConfig:{name:'AK980_PRO',localforageKey:'w240h135',width:240,height:135},
  settingsConfig:{isShowSingleKeyWakeup:!1,isShowStabilityMode:!1,isShowAutoCalibration:!1,isShowReportRate:!1}}
```

- `musicConfig.version = 1` → **MK87 有「音乐律动」tab**（`icon_6`），走 `musicV1` 组件 → **需要 Music.exe 插件**。
- `tftConfig` 没有 `builtInCount` / `isShowTftInfo` / `hideScreenTimeCalibration` → 不发 0x51、不注册 `55 FA 06`、显示「时间校正」。
- `lightingConfig.isShowLightBox = false`（但 `lightBoxList` 存在）→ 灯箱 tab 不显示。
- 没有 `isShowSideLight` → 侧灯 tab 不显示。
- `settingsConfig` 没有 `isShowTftTimeMode` / `isShowKeyDelay` → 这两项设置 MK87 页面不显示。
- 该配置与 `docs/keymap-tables.json` 的 `mk87KeyboardConfig` 一致（那份是对的）；`docs/device_config_32839.json` 的
  `musicConfig: null` 与 `settingsConfig` 缺失项属于**旧版本/旧提取**遗留，建议以本次为准。

---

## 5. 仍需真机验证（静态到此为止）

| # | 疑点 | 为什么静态无解 | 真机怎么测 |
|---|---|---|---|
| 1 | KEYBOARD `param1` 写入固件是否认 | 官方编码器从不写该字节，只有解码路径读它；固件解释代码不在 JS 里 | 往一个**未使用槽位**写 `02 01 04 00`（param1=1=LCtrl、param2=4=HID-A），回读确认后**实际按键**：若输出 Ctrl+A 而不是 A，则固件认 param1；再写 `02 00 04 00` 对比。测完写回全 0 |
| 2 | MACRO `param2=2`（再次按键结束）的固件行为 | 驱动只写值，toggle 由固件实现 | 写一个含 2~3 个动作的宏（如 A、延时、B），绑定到某槽位：`param2=2,param3=0` 保存 → 按一次看是否开始播、再按一次是否停；再与 `param2=0` 对比 |
| 3 | MACRO `param2=1`（重复播放）+ `param3=N` 是否生效 | 同上，且重复次数是 1 字节，固件上限未知 | 绑定 `param2=1,param3=3`，按一次，数宏动作播放次数是否正好 3 次；再把 param3 改成 2/10 对比（注意可能需重连才生效） |
| 4 | MACRO `param3` 在 `param2≠1` 时是否被固件忽略 | 驱动写 0，无法知道固件是否读 | 试 `param2=0,param3=5` 看是否有差异（预期无差异） |
| 5 | pageType 14 END 的两参数含义 | 编码器原样搬运 UI 参数，MK87 不暴露该 UI | 需要**支持 END 的机型**（`advancedKeysList` 含 `END`）先点一次再抓 4 字节；MK87 上可试写 `0E xx yy 00` 观察是否被设备接受/执行（风险：可能被当非法键，建议先做 phantom 槽位 + 还原） |
| 6 | TFT 动画头 `50 06` 固件怎么解释 | 常量，JS 里没有分支 | 上传 1 帧动画（会覆盖屏幕内容，需先备份壁纸）。若 0x50/0x06 被改（如改 `50 00`）导致失败/无效果 → 说明是 magic/类型号。**强破坏性，最后再做** |
| 7 | `SET_TFT_BUILT_IN_INDEX` 的索引语义 | 无名称表；MK87 无 `builtInCount`，官方不发 | 向 TFT 接口发 `AA 51 00 00 00 00 00 01 01`（1 字节索引=1）后回读屏幕，看显示内容是否切到「第 1 个内置动画」；逐个索引试 0..N 并记录屏幕画面 |
| 8 | `tftDisplayTime` 0/1 在固件里的真实渲染 | UI 语义=24h/12h 来自别的机型页面，MK87 不显示该项 | 先 `GET_GAME_MODE` 读当前值；写 `[7]=0` 与 `[7]=1`，看屏幕时钟显示 `14:30` 还是 `2:30 PM`（需屏幕处于时钟页） |
| 9 | `55 FA 06` 的 payload[0] 是「充电」还是「USB 连接」 | 代码里变量名/注释都没写；只知道它启停 TFT 信息轮询 | 插拔 USB / 拔掉充电器，用 HID 监听抓 `55 FA xx` 帧，对比 `GET_DEVICE_INFO[17]=batteryLevel`、`[18]=chargeStatus` 的变化组合 |
| 10 | 音乐律动 `SET_MUSIC_DATA` 帧格式（脱离插件自采音） | 插件是 exe，内部算法/帧格式不在网页 bundle 里；bundle 只发 `[cmd, …]` | 用官方插件跑一次并在 HID 层抓 `cmd=0x35` 的 64 字节 payload，对比自己算的 low/mid/high 幅度；MK87 是 `musicConfig.version=1`，先抓 v1 |
| 11 | 灯效模式号 ↔ 名称（42 个 `lighting_icon*`） | 映射表在运行时动态解析的协议模块里，不在 layout 顶层 | 逐模式 `SET_LED_EFFECT` 写 mode=1..N，看官方 UI 下拉显示的名称/图标，或反查 `GET_LED_EFFECT` 回读 |

> 真机测试纪律（沿用 `docs/deepdive-mk87.md`）：**只写 phantom 槽位 / 先读后写原样回写 / 每次改完立即还原并回读比对**；
> TFT 相关会覆盖屏幕内容，放最后。

---

## 6. 复现

```powershell
$node = "C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"

# 1) 抓语言包（默认 zh en；可传任意 locale，如 zh-TW ja de）
& $node scripts/fetch_i18n.js            # → assets/i18n/*.js|json + docs/i18n-keys.json

# 2) FUNC/FUNC_V2 动作 id ↔ 官方文案 对照
& $node scripts/build_func_i18n.js       # → docs/func-i18n-map.json

# 3) 反向审计：哪些被引用的 key 在语言包里缺失
& $node scripts/audit_i18n_keys.js       # → 控制台列 17 个缺失 key

# 4) 重新定位本文所有 bundle 偏移（bundle 更新后跑这个）
& $node scripts/_offsets.js
```

无 npm 依赖：只用 Node 内置 `fetch` / `fs` / `import()`。

---

## 7. 文件清单（本次新增）

| 文件 | 说明 |
|---|---|
| `docs/i18n-and-unknowns.md` | 本文 |
| `docs/i18n-keys.json` | ★ i18n 全量 1196 键 → {zh,en} |
| `assets/i18n/zh.js` / `en.js` | 语言包 chunk 原文（未改动） |
| `assets/i18n/zh.json` / `en.json` | 解析后的扁平 key→text |
| `assets/i18n/_manifest.json` | 抓取清单 + `/langs/*.json` 覆盖层探测结果 |
| `docs/func-i18n-map.json` | 附赠：FUNC(292)/FUNC_V2(62) id↔文案 + MK87 FN 层 28 个动作 |
| `scripts/fetch_i18n.js` | 语言包抓取 + 解析 + 导出 |
| `scripts/build_func_i18n.js` | FUNC 表 × 语言包 join |
| `scripts/audit_i18n_keys.js` | 反向审计：被引用但语言包缺失的 key（§3.6 的 17 条） |
| `scripts/_offsets.js` | 临时工具：打印关键符号偏移（便于复核引用的 @偏移） |
| `assets/lightingPane-J3Fl9UJi.js` | 附赠：灯效面板 chunk（`lighting_*` UI 文案，未展开分析） |

未改动任何既有文件。
