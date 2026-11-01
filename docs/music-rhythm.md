# 音乐律动 / 实时逐键灯效 —— 完整逆向（不依赖官方 Music.exe）

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

> 结论先说：**可以不依赖官方 Music.exe**。
> 官方网页驱动里有两条音乐路径：v1（依赖本地 `127.0.0.1:9191` 的 Music.exe 算颜色）和 v2（**浏览器自己用
> `getDisplayMedia` 抓系统音频 + WebAudio 分析 + 自己渲染**）。两条路径最终都把画面**通过同一个 HID 帧流**
> `setMusicData` 推给键盘（USB 下就是 cmd `0x32` 的逐键帧）。所以只要复刻帧格式 + 渲染算法，用任何音频源
> （浏览器 WebAudio / Python WASAPI 回环 / 麦克风 / 甚至假数据）都能驱动键盘音乐律动。
>
> 另外：MK87 的 `musicConfig.version` 是 **1**（官方 UI 走插件路径），但这不影响我们——渲染器算法与协议和
> version 2 通用，MK87 只是缺少 `ringKeyPositions/volcanoKeyPositions` 位置表，官方代码里本来就有"无表时的
> 兜底环形/柱状布局"（见渲染器 13/15）。

---

## 1. 官方三条音乐/实时灯效路径

| 路径 | 触发条件 | 音频来源 | 颜色计算 | 下发方式 |
|---|---|---|---|---|
| **v1 音乐**（MK87 官方 UI） | `musicConfig.version===1` | Music.exe 抓系统音频 | **Music.exe 算**，浏览器轮询 `/api/keyboard/musiceffect/` 取每键颜色画预览 | **Music.exe 自己直接驱动设备**；浏览器只发参数+键盘几何，**不发帧** |
| **v2 音乐**（新机型） | `musicConfig.version===2` | **浏览器 `getDisplayMedia` 抓系统/标签页音频** | 浏览器 `AnalyserNode` + 各渲染器 | 浏览器把颜色转帧 → `setMusicData` 逐键帧流 |
| **musicDiy / AI 灯效** | `isEnableMusicDiy` / `isEnableAILighting`（MK87 都未开） | 同上（浏览器） | 用户画布形状 → 每键颜色 | 同上（50ms 定时同步，走 `setMusicData`） |

> **v1 vs v2 的关键差异（与灯效线交叉确认）**：MK87 的官方 UI 是 **v1**——Music.exe 通过原生 HID
> **自己把灯效帧发给键盘**，浏览器只负责"告诉插件：模式/振幅/背景/亮度 + 键盘几何"，再轮询插件算好的
> 每键颜色来画网页预览（v1 组件代码里没有任何 `setMusicData`）。**v2 才是浏览器自己发帧**。
> → 自研工具要做的是复刻 **v2 那条浏览器侧链路**（抓音频→渲染→`setMusicData`），协议数据完全一样。
> 但要注意：MK87 固件是否像 v2 机型那样接受"主机逐键帧"仍待真机验证（见 §9 激活假设）。

三者共用同一套"逐键实时颜色流"通道；v2 里 `Music.exe` 只是**可选**的振幅兜底：
`pe()` 里优先用浏览器采集（`G7()`），没开采集才 `DY()` 去问插件要 `/api/audio/amplitude`。

> **重要修正（i18n 线交叉确认）**：官方**网页 UI 对 v1/v2 都强制依赖插件**——语言包 `music_mode_error`
> = "请下载插件…"、`music_mode_error2` = "仅限 win 系统运行"、`music_text` = "因为网页限制无法捕捉设备音频…"；
> v2 里那个「无需插件」按钮被写死 `isTestMode:false` 隐藏。**但浏览器采集/渲染的代码路径是完整可用的**
> （`getDisplayMedia` + `AnalyserNode` + 全部渲染器都在 bundle 里），只是官方没入口。
> 我们自研工具可以自己启用这条路径 —— 这正是"不依赖 Music.exe"的依据。

## 2. 一句话数据链路

```
音频 → AnalyserNode(fftSize 2048, smoothing .75)
     → 总振幅 K7/Nse（0..1000 → /1000）或 3 段能量 Pse（low/mid/high）
     → 每 50ms 一次 tick：背景 _e + 渲染器（13 种）→ 网格 grid[行][列] = RGB
     → 网格 → 逐键载荷 [keyValue, r, g, b] × 可见键
     → HID 帧流：USB = cmd 0x32（GET_LED_DATA），56 字节/包，7 包/帧（MK87 87 键）
     → 键盘实时显示
```

## 3. 音频分析规格（官方常量，逐项对照）

```
AudioContext + AnalyserNode
  fftSize = 2048
  smoothingTimeConstant = 0.75
  getDisplayMedia({ video:{displaySurface:'monitor'}, audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false} })
  注意：必须勾选"共享系统音频/标签页音频"，否则报错"未获取到音频轨道"

总振幅 K7（用 getFloatTimeDomainData）：
  peak = max(|sample|)
  rms  = sqrt(mean(sample²))
  raw  = 0.6*peak + 0.4*rms
  Nse 自适应归一化：
    z = (raw > z) ? z*0.7 + raw*0.3 : z*0.992 + raw*0.008
    z = max(z, 0.01)
    amp_1000 = min(1000, round(raw/z*1000))
    amp_1000 <= 5 → 0

3 段能量 Pse（用 getByteFrequencyData）：
  hzPerBin = sampleRate/fftSize
  low  = 20..250 Hz, mid = 250..4000 Hz, high = 4000..20000 Hz
  bandRms = sqrt(mean((bin/255)²))  over 区间
  J7 自适应归一化（每段独立）：r = e>base ? 0.3 : 0.008
    base = max(base*(1-r)+e*r, 0.01)
    v = min(1000, round(e/base*1000)); v<=5 → 0

静音处理：主循环有静音计数器 C=5 —— 连续 5 个 tick 振幅为 0 才把幅度归零（避免闪烁）。
测试模式：可绕过音频直接给 0..1000 的测试振幅。
```

## 4. 主循环时序

```
定时器 50ms（= 20 fps）：
  pe()   更新振幅 x（0..1）、静音计数、色相相位 re += 10（部分渲染器用）
  he()   申请网格 grid[F][P+1]，叠背景 _e(grid, backmode, brightness)
         按当前 mode 调渲染器
  me(t)  网格 → 逐键载荷 → setMusicData(...)（await，逐包等 ACK）
```

- `amplitude` 参数（UI 1..100，默认 50）控制平滑速度/亮度；
- `backmode`（背景模式）+ `backmodebrightness`（10..100）；
- 渲染器内部各自维护相位/平滑值（阶段变量 `ie/oe/se/w/T`）。

## 5. 逐键实时帧协议（关键，已精确还原）

### 5.1 USB（MK87 走这条）：cmd `0x32` GET_LED_DATA

```
每帧载荷 = 可见键数 × 4 字节：[keyValue, r, g, b] 依次排列（MK87 = 87×4 = 348 字节）
分包 = floor(reportPayload - 8) = 56 字节/包（14 键/包）
  → 348 字节 = 7 包（前 6 包 56，末包 12）

每包 64 字节报文（WebHID sendReport(0, payload) 的 payload；原生 HID 写入时前面再加 1 字节 report ID=0）：
偏移 0   : 0xAA
偏移 1   : 0x32（cmd = GET_LED_DATA）
偏移 2   : 本包数据字节数（0x38=56，末包 0x0C=12）
偏移 3-4 : 数据起始偏移 addr（LE，0,56,112,...）
偏移 5   : i（官方 setMusicData 第二参数；MK87 恒 0）
偏移 6   : last 标志（1 = 本帧最后一包）
偏移 7   : 0
偏移 8.. : 本包 4B/键数据
```

- 等待 ACK：官方 `NX` 每包等 cmd=0x32 的响应，timeout = `frameVersion===1 ? 2000 : 50` ms，重发 3 次；
  全部失败会 `device.forget()` 断开设备。自研驱动建议：等 ACK 或把超时压到很小；先发再说也可（测试阶段验证）。
- 帧率 20fps × 7 包 = 140 包/s ≈ 9.1 KB/s；单包 RTT 必须远小于 50ms 才跟得上（设备正常会秒回）。

### 5.2 2.4G 分支（report=64 且 lightingVersion=1）：cmd `0x3C` SET_MUSIC_DATA_24G_64_BYTE

- 载荷从 4B/键 转成 RGB565 流（2 字节/像素，无键号）：`[hi,lo] = jV(AV(rgb))`，按键顺序连续排列
- 分包同 56 字节/包，头 `AA 3C len addrLo addrHi i last 0`，`maxRetries:0, timeout:10ms`

### 5.3 通用分支（其它）：cmd `0x35` SET_MUSIC_DATA

- 载荷 = RGB565 流；**4 字节自定义头** `AA 35 seq i`，每包数据长 = reportPayload-4 = 60
- `maxRetries:0, timeout:10ms`

### 5.4 帧 → 网格的映射（官方 me()）

```
grid[F][P+1]（F = 键盘行数 6；P = 最长行 + maxColOffset = 17；宽 18）
逐键：col = 行内下标 + 该行累计 keyOffset.offsetX（MK87 keyOffset：F1+1、Z+1、↑+2、Space+3、R-Alt+3）
载荷顺序 = 按行左到右、过滤 disabledLight 的可见键
payload[n] = keyValue；payload[n+1..3] = grid[row][col] 的 RGB
```

## 6. 音乐渲染器全表（mode → 官方函数 → 视觉）

| mode | 官方名（en） | 官方函数 | 视觉/行为 | 依赖配置 |
|---|---|---|---|---|
| 13（默认） | Dance to the Beat | `Se` | 中心同心环向外扩散，环数随振幅、彩虹相位 | `ringKeyPositions`（无则按中心距离兜底分环，MK87 走兜底） |
| 14 | Dust Glow Spiral | `Ce` | 中心 4 色射线旋转，长度随振幅（灰尘光螺旋） | 无 |
| 15 | Dormant Volcano | `Ee` | 三塔/火山状（左中右三层），彩虹色相 | `volcanoKeyPositions`（无则按列兜底） |
| 16 | Light Arrow Piercing | `De` | 光箭/横条穿刺（左右脉冲粒子横条） | 无 |
| 17 | Firefly Trail | `je` | 中心行正弦波 + 萤火拖尾，列色相渐变 | 无 |
| 18 | Light Cocoon Resonance | `Oe` | 光茧/边框环绕 + 对角光带，随振幅增长 | 无 |
| 19 | Tuning Fork Vibration | `Ae` | 音叉振动：左右两条触须带随机抖动与暗色拖尾 | 无 |
| 20 | Curvature Legacy Track | `Ne` | 从右边向内的弯曲波形 | 无 |
| 21 | Row Wave Rhythm | `Pe` | 行波浪节奏：每行不等长柱，色相渐变 | 无 |
| 22 | Dual Heart Dance | `L` | 双心/内置坐标图案（随振幅点亮） | 键位表 |
| 1 / 4 | （同 mode 4：Curvature Frequency Steps） | `Fe` | 背景 + 列包络柱状（EQ），背景取该 mode 值 | 无 |
| 100 | Screen light linkage | 插件 | 交给 Music.exe 计算，浏览器只转发 | 需插件 |

> 渲染器函数源码已从 bundle 倒出：`docs/_music_a.js`（模式列表/主循环/部分渲染器）、
> `docs/_music_b.js`、`docs/_music_b2.js`（Se/Ce/Ee/De/Oe/Ae/je/Ne/Pe/Fe 全量）。
> `scripts/music_ref.js` 已**逐行精确移植**：Kab（总振幅）、Pse（3 段）、背景全表、模式 1/4/13/14/17；
> 其余模式可照着 `_music_b2.js` 直接补进同一个 `renderMode*` 接口。

## 7. 背景模式表（官方 `_e`）

| value | 官方名（en） | 效果 |
|---|---|---|
| 0 | None | 无背景（黑） |
| 1 | Green/Yellow/Red | 3 色横向分段 |
| 2 | Rainbow | 6 色横向分段 |
| 4 | Color Spectrum | 以中心为原点的径向色相渐变（随时间转） |
| 5 | Spectrum Loop | 纯色持续旋转色相 |
| 6/7/8/9/10/11 | White / Red / Orange / Yellow / Blue / Green | 纯色（亮度 = backmodebrightness） |

## 8. 不用官方工具的实现方案

### 方案 A：浏览器单文件工具（推荐，WebHID）
```
getDisplayMedia({audio:true}) 抓系统音频（用户勾选共享音频）
→ AudioContext + AnalyserNode（参数见 §3）
→ 每 50ms：K7/Nse 得振幅 → renderFrame → gridToPayload → packUsbMusicFrames
→ device.sendReport(0, packet64)（注意 sendReport 的 data 是 64 字节，不含 report ID 字节）
```
`scripts/music_ref.js` 可直接被浏览器页面复用（改 `module.exports` 为全局即可）。

### 方案 B：Python 原生 HID（与现有 `probe/ajazz.py` 同一通道）
- 音频：WASAPI loopback（`pyaudiowpatch`/`soundcard`）或麦克风；
- 计算：照 §3 公式实现 K7/Nse（Python 版 20 行）；
- 发送：`probe/ajazz.py` 里补一个 `set_music_data(payload)`，按 §5.1 组 7 个包，写入 MI_02；
- 渲染器可先只用 mode 13（重心环）或做"纯色呼吸/按列柱状"等自定义效果（不一定要 1:1 复刻官方）。

### 方案 C：任意振幅源
没有系统音频采集条件时，可用麦克风、播放器音量、甚至鼠标位置当"振幅"输入 —— 协议只要求每 50ms 一帧颜色。

## 9. 激活 / 退出行为（✅ 真机已测，2026-11-01）

真机结论（详见 [TEST-REPORT.md](TEST-REPORT.md) §6）：

| 假设 | 结果 |
|---|---|
| **H1**「只要发帧就接管显示」 | ❌ 不成立：灯效 mode=1 时发 0x32 帧，屏幕/灯效无任何变化 |
| **H2**「需先切某个模式」 | ✅ **成立：先发 SET_LED_EFFECT(mode ∈ {20, 21, 128})（自定义族），再发 0x32 帧即立即显示** |
| **H3**「停止后回落」 | ✅ 成立：停发后 **≈5 秒**回落到本模式的自定义表（无需额外命令） |

其它真机数据：

- 单包 ACK 延迟 **0.5–3 ms**，全帧（7 包 + 逐包 ACK）**15.5 ms** → **20 fps 稳定**（实测 150 帧/7.50s，1050/1050 包 ACK），理论上限 ~60 fps
- 帧数据写入的是同一块逐键 LED 缓冲：GET_ALL_LIGHTS_RGB 可实时读回帧颜色（可用于自动化验证）
- 开始时必须处于上述模式；模式 20/21/128 共用同一张自定义表，三者均可作为帧流展示模式
- 自研链路已跑通：WAV → 官方 K7/Nse 振幅算法 → 官方渲染器（mode 13/14/17）→ 0x32 帧流 → 键盘，三个渲染器均在真机正常显示

## 10. 官方 Music.exe 接口契约（仅为兼容/参考，自研不需要）

基础地址 `http://127.0.0.1:9191`，timeout 500ms：

| 方法/路径 | 用途 | 数据 |
|---|---|---|
| GET `/api/audio/amplitude` | 当前总振幅 | `{ amplitude: number }`（0..1000，页面 /1000 用） |
| GET `/api/keyboard/musiceffect/` | 插件算好的每键颜色 | `{ keys:[{ keyIndex, keyCode, row, col, color:'#rrggbb' }] }` |
| GET `/api/keyboard/musiceffect?param=<mode>&<...>&<...>&<...>&1` | 启动/切换插件音乐模式 | 参数串：mode & 100 & backmode & 100 & flag（官方调用样例 `13&100&0&100&0`） |
| GET `/api/keyboard/musiceffect/close/` | 停止插件音乐模式 | — |
| GET `/api/keyboard/layout/base64?data=<base64(JSON)>` | 把键盘布局告诉插件 | `{name,vendorId,productId,deviceMode(0=USB,1=2.4G),layouts:{rows,cols,keys:[{row,col,code,index,name}]}}` |
| GET `/api/hardware/info` | CPU/GPU 温度占用（屏幕系统信息用） | `{cpuUsage,cpuTemp,gpuUsage,gpuTemp}` |

## 11. 文件索引

- 参考实现：[music_ref.js](music_ref.js)（自检 31/31 通过 + demo）
- 常量表：[music-constants.json](music-constants.json)
- 官方代码倒出：`docs/_music_a.js`、`docs/_music_b.js`、`docs/_music_b2.js`、`docs/_v1music.txt`
- 相关真机能力：[deepdive-mk87.md](deepdive-mk87.md)（写通道已验证）、[protocol_commands.js](protocol_commands.js)（setMusicData=TZ 源码）

### ⛔ 2.4G 分支（2026-11-01 更新）

**官方确认 2.4G 模式不支持音乐律动**。真机在 MK87 dongle（0xFF60，32B 报文）上试了三种官方打包
（cmd 0x32 4B/键、cmd 0x35 RGB565 28B/包、cmd 0x3C RGB565 走 0xFF59 64B 接口），
都只出现「短暂白脉冲 / 随机色 / 竖条纹」，没有任何一种能正确显示。
⇒ 自研音乐律动**只走 USB**（USB 下 cmd 0x32 + mode 20/21/128 已完整验证，见 §9）。
