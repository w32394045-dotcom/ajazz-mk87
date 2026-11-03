# 音乐律动 / 实时逐键灯效 —— 完整逆向（不依赖官方 Music.exe）

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，务必先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>
> 🆕 **v0.1.3（2026-11-03）**：官方 v1 重新采样（模式 4 真值）、21 模式下拉、LED 颜色覆盖层、原生
> 20/60/66fps 帧流见 **§12**；**§1–§9** 中出现的「50ms / 20fps / 15.5ms」等时序是 **v0.1.2 及以前**
> 的历史事实（§12 的 20fps 档除外），v0.1.3 默认 66fps（20fps 路径仍保留且行为不变）。
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
     → 每 50ms 一次 tick（v0.1.2 及以前；v0.1.3 见 §12.4）：背景 _e + 渲染器
       （v0.1.2 时 13 种；v0.1.3 主机侧 20 种）→ 网格 grid[行][列] = RGB
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

> **v0.1.2 及以前**：下面是官方 20fps 基准节奏（渲染器内部常量都按它标定）。v0.1.3 原生可选
> 20/60/66fps，但动画仍按 20fps 基准做 `dt_scale` 归一，因此本节的「每 tick 一次」语义不变；
> 只有发包节奏与 ACK 策略变了（见 §12.4）。

```
定时器 50ms（= 20 fps；v0.1.2 及以前的基准节奏）：
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
- **v0.1.2 及以前**：帧率 20fps × 7 包 = 140 包/s ≈ 9.1 KB/s；单包 RTT 必须远小于 50ms 才跟得上
  （设备正常会秒回）。**v0.1.3** 原生 66fps 时是 7 × 66 ≈ 462 包/s，且 ≥60fps 改走 burst + 异步
  ACK 清道夫（§12.4）。

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
| 1 / 2 / 5 / 6–11 | Green/Yellow/Red · Rainbow · Spectrum Cycle · White/Red/Orange/Yellow/Blue/Green | `Fe` | 曲率频阶柱状（EQ）+ 该 mode 号对应调色板（1 绿黄红分行 / 2 六色横条 / 5 旋转单色 / 6–11 纯色） | 无 |
| 4 | Curvature Frequency Steps | `_render_mode_4`（v0.1.3 重写） | **17 列频谱柱，底部对齐**；列=频率（左低右高，对数约 110Hz–12kHz）；颜色=以 `(2,8)` 为原点的径向色相，调色板约 275°/s 旋转；柱高随 amplitude 增长（§12.1） | 无 |
| 100 | Screen light linkage | 插件 | 交给 Music.exe 计算，浏览器只转发；本工具无渲染器，**回落 13** | 需插件 |

> 渲染器函数源码已从 bundle 倒出：`docs/_music_a.js`（模式列表/主循环/部分渲染器）、
> `docs/_music_b.js`、`docs/_music_b2.js`（Se/Ce/Ee/De/Oe/Ae/je/Ne/Pe/Fe 全量）。
> `scripts/music_ref.js` 已**逐行精确移植**：Kab（总振幅）、Pse（3 段）、背景全表、模式 1/13/14/17
> （以及当时与 1 共用 `Fe` 渲染器的 4；4 已在 v0.1.3 单独重写，见下）；
> **2026-11-02 补全**：15/16/18/19/20/21/22 也已按官方函数逐行移植进 `driver/mk87lib/music.py`
> （含从 `capture/official_music_live/layout-classic-CMxiG14P.js` 取出的模式 22 内置双心坐标表 5 个分支），
> 并与官方 bundle 做了跨实现逐帧对拍（6×17 网格，99,960 格 0 差异）。
> 模式 100（屏光联动）仍由 Music.exe 计算，主机侧没有渲染器，回落 13。
> `MK87` 无 `volcanoKeyPositions`，模式 15 走官方柱状兜底分支。
>
> **v0.1.3 变更**：模式 **4 不再与 1 共用 `Fe` 合成包络**，而是按官方 v1 真值单独实现为 17 列频谱柱
> （§12.1）；模式 **1/2/5/6–11** 仍走 `Fe` 柱状几何、模式号即调色板。14–22 这 9 个此前只存在于研究
> 代码里的模式，v0.1.3 已补回「官方方案」下拉，与官方 v1 原有的 12 项合计 **21 项**（§12.2）；
> 100 仍回落 13。

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

## 9. 激活 / 退出行为（✅ 真机已测，2026-11-01；v0.1.2 及以前）

> v0.1.3 起帧流入口**只写 20/21，绝不写 128**（128 的固化/卡死问题见 §12.5）；下表 H2 是
> 2026-11-01 当时含 128 的历史结论。

真机结论（详见 [TEST-REPORT.md](TEST-REPORT.md) §6）：

| 假设 | 结果 |
|---|---|
| **H1**「只要发帧就接管显示」 | ❌ 不成立：灯效 mode=1 时发 0x32 帧，屏幕/灯效无任何变化 |
| **H2**「需先切某个模式」 | ✅ **成立：先发 SET_LED_EFFECT(mode ∈ {20, 21, 128})（自定义族），再发 0x32 帧即立即显示**（128 不再由帧流入口写入，见 §12.5） |
| **H3**「停止后回落」 | ✅ 成立：停发后 **≈5 秒**回落到本模式的自定义表（无需额外命令） |

其它真机数据：

- **v0.1.2 及以前**：单包 ACK 延迟 **0.5–3 ms**，全帧（7 包 + 逐包 ACK）**15.5 ms** → **20 fps 稳定**
  （实测 150 帧/7.50s，1050/1050 包 ACK），理论上限 ~60 fps。v0.1.3 的 20fps 路径仍是逐包 ACK、行为不变；
  66fps 走 burst + 异步清道夫，实测见 §12.4
- 帧数据写入的是同一块逐键 LED 缓冲：GET_ALL_LIGHTS_RGB 可实时读回帧颜色（可用于自动化验证）
- 开始时必须处于自定义族模式；模式 20/21/128 共用同一张自定义表。**v0.1.3 起帧流入口绝不写 128**
  （fw1.19 会把 128 固化成自定义表并回读 mode=0，进程被关机杀死时恢复逻辑不跑就会卡死灯效），
  帧模式固定写 20/21 并回读校验（§12.5）
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

- 参考实现：[music_ref.js](../scripts/music_ref.js)（自检 31/31 通过 + demo）
- 常量表：[music-constants.json](music-constants.json)
- 官方代码倒出：`docs/_music_a.js`、`docs/_music_b.js`、`docs/_music_b2.js`、`docs/_v1music.txt`
- 相关真机能力：[deepdive-mk87.md](deepdive-mk87.md)（写通道已验证）、[protocol_commands.js](protocol_commands.js)（setMusicData=TZ 源码）
- **v0.1.3 新增**：官方 v1 配置真值 [music-v1-config.json](music-v1-config.json)；前端 21 模式 / 10 颜色 /
  3 帧率表 `driver/web/js/data/music.js`；模式 4 采样与分析
  `probe/capture_official_v1_mode4.py`、`probe/analyze_official_v1_mode4.py`、
  `capture/official_v1_mode4_{tone100,tone440,tone2000,tone4000,tone8000,sweep,amp,silence}.jsonl`；
  后端实现 `driver/mk87lib/music.py`（`_render_mode_4` / `Palette` / `MusicPlayer`）

### ⛔ 2.4G 分支（2026-11-01 更新）

**官方确认 2.4G 模式不支持音乐律动**。真机在 MK87 dongle（0xFF60，32B 报文）上试了三种官方打包
（cmd 0x32 4B/键、cmd 0x35 RGB565 28B/包、cmd 0x3C RGB565 走 0xFF59 64B 接口），
都只出现「短暂白脉冲 / 随机色 / 竖条纹」，没有任何一种能正确显示。
⇒ 自研音乐律动**只走 USB**（USB 下 cmd 0x32 + mode 20/21 已完整验证；v0.1.2 及以前曾用 128，
**v0.1.3 起不再写 128**，见 §9 / §12.5）。

---

## 12. 2026-11-03 官方 v1 重新采样与 v0.1.3 实现

> 本节是 **v0.1.3** 的新增内容。§1–§11 里出现的 50ms / 20fps / 15.5ms 等时序，除特别标注外均为
> **v0.1.2 及以前**的历史事实；v0.1.3 默认 66fps，但 20fps 路径保留且行为不变。

### 12.1 显示模式 4「曲率频阶」：官方 v1 真值

旧实现把 mode 4 当成「合成正弦包络」——不管声音频率/振幅，都点满左半边，与官方实际效果不符。
2026-11-03 直接对官方 v1 重新采样后重写。

**采样方法**

- 官方 `MusicPlug.exe` 本地 HTTP（`127.0.0.1:9191`）轮询 `/api/keyboard/musiceffect/`；
  音频源为 48kHz 正弦单音 **100 / 440 / 2k / 4k / 8k Hz**、**200→6400Hz 阶梯扫频**、
  振幅扫描（amp=30 / amp=100）与静音。
- **全程只走 HTTP**，没有发本工具的 HID 帧流，排除自研数据污染；官方插件自己算颜色、自己驱灯。
- 解析：官方返回 102 键 → MK87 6×17 网格（15 个非法键回溯成 `(0,0)`，同格取首现）→ 87 键；
  柱高 = 从最底行向上连续非黑格数。
- 采集/分析脚本：`probe/capture_official_v1_mode4.py`、`probe/analyze_official_v1_mode4.py`；
  原始数据：`capture/official_v1_mode4_*.jsonl`。

**真值表**

| 观测项 | 官方 v1 结果 |
|---|---|
| 几何 | **17 列频谱柱**，**100% 底部对齐（1200/1200 帧）** |
| 列 ↔ 频率 | 列=频率，**左低右高、对数**，约 **110Hz–12kHz**；**100Hz 只点最左 3 列**、**8kHz 只点最右 2 列** |
| 扫频 | 200→6400Hz 阶梯扫频时柱峰自左向右逐级移动 |
| 颜色 | 以 **`(2,8)`** 为原点的径向色相（满饱和，左右半屏约差 180°）；整块调色板以 **~275°/s** 旋转，**与 amplitude 无关** |
| 柱高 | 随 amplitude 增大：**amp=30 单音峰值约 4/6 行**；**amp=100 顶到 6/6 行** |
| 静音 | 非全黑，是一条约固定的近似轮廓（用于无频谱输入时兜底） |

**v0.1.3 实现**

- `_render_mode_4`：17 列、底部对齐；柱高 = 该列频段能量（Analyzer 32 段对数频谱压成 17 段）×
  amplitude 增益，无频谱输入时才退回按静音采样归一化的「曲率」轮廓（单测/外部直接 `tick(amp)` 场景）。
- 颜色 = 以 `(centerRow, centerCol)` 为原点的径向色相，`mode4Hue` 每 tick 推进、按 `dt_scale` 归一。
- 旧 `_render_mode_1or4` 仅作为模式 1/2/5/6–11 的 `Fe` 柱状几何保留，**模式 4 不再使用它**。

**仍属推断（不是官方常量）**

- 列↔频率边界由 **5 个单音 + 阶梯扫频反推**，110Hz / 12kHz 是拟合端点；
- 振幅-柱高只标定 **amp=30 / amp=100** 两点，中间按线性处理；
- 静音兜底轮廓为近似；
- 色相旋转按 ~275°/s 拟合，未逐帧复刻官方相位/抖动。

### 12.2 显示模式下拉：21 项与实现状态

「官方方案」下拉 = 官方 v1 UI 原有的 **12 项** + 之前逆向出、但官方 UI 没暴露的 **9 项（14–22）**
= **21 项**。顺序：`1, 2, 13, 4, 5, 6, 7, 8, 9, 11, 10, 14…22, 100`。

| 分组 | mode | 名称（中 / 英） | 主机侧实现 |
|---|---|---|---|
| 官方 v1 UI 原有（12） | 1 | 绿色/黄色/红色 · Green/Yellow/Red | `Fe` 柱状 + 绿黄红分行 |
| | 2 | 彩虹色 · Rainbow | `Fe` 柱状 + 六色横条 |
| | 13 | 随曲起舞 · Dance to the Beat（默认） | `Se` 同心环扩散 |
| | 4 | 曲率频阶 · Curvature Frequency Steps | **v0.1.3 重写：17 列频谱柱（§12.1）** |
| | 5 | 频谱循环 · Spectrum Cycle | `Fe` 柱状 + 旋转单色 |
| | 6 | 白色 · White | `Fe` 纯色柱 |
| | 7 | 红色 · Red | `Fe` 纯色柱 |
| | 8 | 橙色 · Orange | `Fe` 纯色柱 |
| | 9 | 黄色 · Yellow | `Fe` 纯色柱 |
| | 11 | 绿色 · Green | `Fe` 纯色柱 |
| | 10 | 蓝色 · Blue | `Fe` 纯色柱 |
| | 100 | 屏光联动 · Screen light linkage | ⛔ 无主机渲染器（Music.exe 读屏计算）→ **回落 13** |
| 补回（9，v1 UI 未暴露） | 14 | 光尘螺旋 · Dust Glow Spiral | `custom` 渲染器 |
| | 15 | 休眠火山 · Dormant Volcano | `custom` 渲染器（无坐标表走柱状兜底） |
| | 16 | 光箭穿刺 · Light Arrow Piercing | `custom` 渲染器 |
| | 17 | 萤火轨迹 · Firefly Trail | `custom` 渲染器 |
| | 18 | 光茧共鸣 · Light Cocoon Resonance | `custom` 渲染器 |
| | 19 | 音叉振动 · Tuning Fork Vibration | `custom` 渲染器 |
| | 20 | 曲率传承 · Curvature Legacy Track | `custom` 渲染器 |
| | 21 | 行波节奏 · Row Wave Rhythm | `custom` 渲染器 |
| | 22 | 双心共舞 · Dual Heart Dance | `custom` 渲染器（内置双心坐标表） |

- **20 项主机侧可渲染**（12 项原有中的 11 项 + 9 项补回）；**100 回落 13**，自研屏幕同步仍待做。
- 前端表在 `driver/web/js/data/music.js`（`OFFICIAL_MUSIC_MODES`）；后端模式表在
  `driver/mk87lib/music.py`（`V1_DISPLAY_MODES` / `V1_IMPLEMENTED_MODES`）。

### 12.3 LED 颜色覆盖层（本工具自研增强）

「官方方案」的第三个下拉「LED 颜色」不是官方 UI 设置项，是本工具在官方配色之上加的一层覆盖。

| id | 名称 | 色值 |
|---|---|---|
| `default` | 默认（官方配色） | 不覆盖 |
| `ice` | 冰蓝 | `#00E5FF` |
| `violet` | 紫罗兰 | `#B36CFF` |
| `pink` | 热粉 | `#FF2E88` |
| `lime` | 青柠 | `#A8FF3E` |
| `amber` | 暖橙 | `#FF6A00` |
| `sakura` | 樱花渐变 | `#FF7AB6 → #B36CFF` |
| `aurora` | 极光渐变 | `#3EFF9A → #00E5FF → #7A5CFF` |
| `sunset` | 落日渐变 | `#FFC400 → #FF6A00 → #FF2E88` |
| `icefire` | 冰火渐变 | `#00E5FF → #FEFEFE → #FF6A00` |

**设计**

- 作用于**全部动态多色模式 1 / 2 / 4 / 5 / 13 与补回的 14–22**；纯色模式 6–11 与背景（backmode）完全不受影响。
- 只替换「色相 → RGB」这一层：按原始调色板位置 `t` / 径向角度 / 环相位在新渐变上采样
  （`Palette.at(t)`），各渲染器的相位推进、径向角度、环扩散等动画原样保留。
- `default` = 不覆盖，走官方采样配色；**与改动前逐字节一致**（220 组合快照回归）。
- 未知/空 id 归一化回 `default`（debug 日志，不报错）；单色方案在任意 `t` 返回同一颜色。

### 12.4 原生帧率：20 / 60 / 66fps（默认 66）

**官方依据**：官方 v1 实测发包 **530.5 包/s ÷ 8 包/帧 ≈ 66.3fps**。
（官方每帧 8 包；本工具 MK87 是 87 键 × 4B → 7 包/帧，66fps 时为 462 包/s。）
因此「官方方案」提供 **20 / 60 / 66fps** 三档，**默认 66**；「当前方案」仍是 15 / 20 / 30。

| 目标档位 | 发送策略 | 依据 |
|---|---|---|
| 20fps（≤30） | 逐包写 + 逐包等 ACK，7 包/帧 | 7 包逐包 ACK 约 15.5ms/帧，50ms 预算充足；**与旧版 20fps 路径逐位一致** |
| 60 / 66fps（≥60） | 连写 7 包（burst）+ **ACK 清道夫线程异步读回包**；清道夫起不来时回退帧末同步 drain | 66fps 每帧预算 15.15ms；同步帧末 drain 实测 **19.8ms/帧 → 只有 45.96fps**；异步后 **send 8.85ms/帧 → 66fps** |

**动画归一（dt_scale）**

- 所有渲染器常量仍按官方 20fps 标定；实际帧间隔换算 `dt_scale = 帧间隔 × 20`（钳制 0.2–3.0），
  66fps 时每帧只推进约 0.303 个基准 tick，累计 1 秒仍是 20 个基准 tick。
- 平滑/AGC/相位推进都按等效时间常数换算，**切 66fps 观感速度不变**；不做逐帧抖动复刻。

**接口契约**

- 页面显示**实测 fps**；`/api/music/status` 与 WS 事件里：
  `fps` = 实测值（float，未运行/样本不足为 `null`），`targetFps` = 配置档位（int）。
- 运行中 `/api/music/update` 可热切模式/背景/亮度/振幅/帧率/颜色；WS 预览限速 **30Hz**（键盘仍按目标帧率发包）。

**真机实测（USB，fw1.19，2026-11-03）**

| 目标 | 时长 | 实测 | 备注 |
|---|---|---|---|
| 66fps | 连续 100s | **65.78–65.89fps** | send 8.85ms/帧、lateFrames ≤6、**0 错误** |
| 60fps | — | **60.06fps** | — |
| 20fps | — | **19.97fps** | 逐包 ACK 路径 |

- 21 个模式 + 10 种颜色逐个切换：**0 错误**。
- 停止后灯效恢复原值：**mode=11、brightness=6、speed=3**，raw
  `0bffffffff000000010603000000aa55`。
- 单元测试 **152 个全绿**；无头 Chrome UI 自检 **17 项 PASS**（21 模式 / 3 下拉 / 10 颜色 /
  3 帧率档、热切换、英文无中文残留）。

### 12.5 帧流入口与灯效恢复（v0.1.3 修复）

- **根因**：v0.1.2 音乐启动会写 LED **mode=128**；进程被关机杀死时恢复逻辑没跑，fw1.19 把 128
  固化成逐键自定义表（回读 mode=0），看起来就像「灯效卡死 / 重启后像游戏模式」。
- **帧流入口现在绝不写 128**：帧模式固定写 **20/21**，每次写入后回读校验；`ensure_frame_mode` 只在
  进入前保存快照，不通过写 128 进入/恢复帧流。
- **恢复快照前校验 mode**：只有 `1..19 ∪ {20,21,128}` 才允许写回（128 仅用于兼容历史快照）；快照
  mode 为 0/非法一律跳过（`restore_effect` 打 warning），可传安全 fallback。
- **退出顺序**：「停音乐并等恢复 → 按键测试 → 关设备管理器」，保证恢复先于句柄关闭。
- `GET /api/lighting` 在 mode 回读 0 时补读 `GET_ALL_LIGHTS_RGB`，逐键表有非黑颜色则标
  `isCustom=true`（2.4G 不探测，避免 22 包读灯开销）。
- 全量日志证实工具**从未写过 game-mode**（0 条 cmd `0x21`）；「像游戏模式」与 128 固化同源。
- 电量/充电/工作模式每次读取都刷新并记日志（连接日志带 battery/charging/workMode/transport，
  连接后延迟 2s 重读）；2.4G 电量走 cmd `0x37` 首包 + `GET_ALL_LIGHTS_RGB_24G` 回包，连续失败
  3 次熔断 5 分钟并回退 USB 路径。

### 12.6 已知边界

- 列↔频率映射是**反推**（5 个单音 + 扫频拟合），不是官方常量；110Hz / 12kHz 为端点近似。
- 振幅-柱高只在 **amp=30 / amp=100** 两点标定，中间按线性处理。
- 静音兜底轮廓为**近似**（来自静音采样归一化）。
- **未复刻官方逐帧抖动/相位噪声**；颜色旋转按 ~275°/s 拟合。
- 100 屏光联动仍**回落 13**，自研屏幕同步待做。
- LED 颜色覆盖支持 **1/2/4/5/13 + 14–22** 全部动态模式（单色方案下多色结构会退化为同色相）；
  纯色 6–11 与背景的自带配色不受影响。
- 音乐律动仍**仅 USB**（官方确认 2.4G 不支持）。
