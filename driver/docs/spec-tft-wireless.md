# MK87 规格 · TFT 屏幕 / 2.4G 无线 / 按键事件捕获

> 设备：AJAZZ MK87，USB `0C45:8047`（3141/32839），2.4G 接收器 `0C45:FEFE`（3141/65278），固件 v1.19。
> 引用约定：`tft-page.md:232` = `docs/tft-page.md` 第 232 行；`design.md:141` = `driver/docs/design.md`；
> `TC.json → commands.SET_TFT_MATERIAL` = `docs/tft-constants.json` 的 JSON 路径。
> 标注：【实测】真机跑过（TEST-REPORT + `docs/phase*.json`）；【代码】官方 bundle 静态可复核；**【未验证】** 本仓库无证据（多为设计建议）。
> 分工：传输层/帧格式/命令表/游戏模式 56B 见 `spec-protocol.md`；灯效见 `spec-lighting.md`；键位图见 `spec-keymap.md`。本文件只写 TFT / 2.4G / 按键捕获，数字已与 `spec-protocol.md §4.11/§6` 对齐。

## 0. 一页速查

| 主题 | 结论 | 证据 |
|---|---|---|
| 屏幕+通道 | 240×135 RGB565、`tftMaxFrames=140`、`tftDirection=0`、`tftColorByteOrder=0`（小端）、行优先无 padding；USB 专用 `usagePage 0xFF67`（MI_03），report 4104B + 1B report ID = **4105B/包**，数据 **4096B/包** | `protocol.md:89-98`、`tft-page.md:230`、`TEST-REPORT.md:102` |
| 命令 | `SET_TFT_MATERIAL 0x4D` / `SET_TFT_USER_ANIMATION 0x50` / `SET_TFT_BUILT_IN_INDEX 0x51` | `protocol.md:66-68` |
| ACK | **0x4D 与 0x50 的逐包 ACK 都是 `0x41`**；0x51 也回 `55 41`（官方壁纸路径按 0x4D 判 ACK = 必超时） | `TEST-REPORT.md:100-101` |
| 帧上限 | 140（设备信息）；官方默认动画 135 帧 / 10fps | `restore_tft_default.json`、`_default_gif.json` |
| 2.4G 身份 | `3141-65278-2.4G Dongle-1-18`（manufacturer=1 / product=18 / workMode=2） | `TEST-REPORT.md:221-225` |
| 2.4G 通道 | 仅 `0xFF60`（33B 报告 / 32B payload）可用；`0xFF59`（65B）无响应 | `TEST-REPORT.md:229-232` |
| 唤醒帧 | `A6 FF 01` 走 `0xFFFF`/MI_02 COL05/**report ID=5**，不在官方 WebHID 过滤器表 | `phase6_sleep_wake.json` |
| 按键 | 厂商协议无事件帧；HID `\kbd` err=5；**Windows RawInput 可用** | `key-events.md:263-284`、`TEST-REPORT.md:290-301` |

## 1. TFT 上传协议

### 1.1 通道与帧层

- 只有 USB 有 TFT 通道（`usagePage 0xFF67`，官方 `LX()` 按 productId 找）；**2.4G 无此接口**，且无线配置的 `routesName` 无 `tft`
  → **无线模式不能上传屏幕内容**（`wireless-profiles-led-animation.md:137,159-160`）。
- 帧格式（TFT 与主协议共用，`TC.json → framing`、`protocol.md:11`）：请求 `AA cmd len addrLo addrHi hdr5 last hdr7 | data`，响应 `55 cmd lenOrType addrLo addrHi 0 0 1 | data`。
- **0x4D/0x50 走 `PX()` 的 customHeader 分支**：整包 = 8B 自定义头原文 + data（不写 len/addr/last），数据偏移恒 8；**0x51 用默认 8B 头**（`tft-page.md:222-231`、`scripts/tft_ref.js:214-243`）。
- 每包 = `reportCount-8`；TFT `reportCount=4104` → 4096B。写入前加 report ID 0 → 实际 **4105B/次**（`TEST-REPORT.md:102`、`FEATURES.md:14-15`）。TFT 命令**不用 CRC**（`TC.json → framing.crc`）。

### 1.2 三条命令 payload（逐字段）

**`SET_TFT_MATERIAL` 0x4D**（`tft-page.md:232-248`、`tft_ref.js:251-279`）：`AA 4D seqLo seqHi totalLo totalHi matLo matHi | 像素…`

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 / 1 | `AA` / `4D` | 帧头 / 命令 |
| 2..3 | seq（u16 **小端**） | 0 基包序号 |
| 4..5 | total（u16 小端） | 总包数 |
| 6..7 | materialId（u16 小端） | **0 = 壁纸**（网页端只用 0） |
| 8..4103 | 像素 | 4096B/包，末包零填充；**无延时表** |

**`SET_TFT_USER_ANIMATION` 0x50**（`tft-page.md:250-267`、`tft_ref.js:287-319`）：`AA 50 seqLo seqHi totalLo totalHi 50 06 | 数据…`

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 / 1 | `AA` / `50` | 帧头 / 命令 |
| 2..3、4..5 | seq、total（u16 小端） | 同上 |
| 6 / 7 | `0x50` / `0x06` | **字面常量**（0x50 恰为命令字，6 疑为格式/类型，含义无文档） |
| 8..4103 | `256B 延时表 + 各帧 RGB565 连续拼接` | 见 §2.1 |

**`SET_TFT_BUILT_IN_INDEX` 0x51**（`tft-page.md:72-83`、`probe/phase2_builtin.py:33-35`）：头 `AA 51 01 00 00 00 01 00`（offset2=1 为 len、offset6=1 为 last）+ **1 字节 index**，其余补 0 到 4104。
`contentSize=1`、`timeout=50ms`（`frameVersion===1`→2000）、`maxRetries=0`，**不等结果**（超时返回 `[]` 但函数返回 `true`）。

**0x4D vs 0x50**

| 维度 | 0x4D 壁纸 | 0x50 动画 |
|---|---|---|
| 头 [6..7] | materialId u16 LE | 固定 `50 06` |
| 数据体 | 纯像素，强制 1 帧 | 256B 延时表 + N 帧像素（1..140） |
| ACK（fw1.19） | **0x41** | **0x41** |
| 可见性 | ❌ 无壁纸页 → 写入成功但**不可见**（实测） | ✅ 自定义动画页立即播放（实测） |
| 官方 UI | `tftConfig.materialIds` 缺省 → 按钮不渲染 | 有（保存时上传） |

> 任务书的「40/50」应为 **0x4D/0x50**；`0x40` 是 `SET_LED_BOOT_ANIMATION`（LED 开机动画，bundle 内 0 调用），与本页无关。

### 1.3 ACK 规律

- 所有 TFT 上传包逐包回 `55 41 …`（记录时只截前 16B：`55 41 00 01 00 00 00 00 …`，lenOrType=0、addr=1）（`phase2_tft.json`）。
- 官方壁纸路径等 `cmd=0x4D`（`tft-page.md:246`）→ fw1.19 上**4 次尝试后必超时**；只因壁纸 UI 不可达才没暴露（`TEST-REPORT.md:100-101`；`phase2_tft.json` 的 `red` run 记录了 `55 41` 却标 `ack=false`，该 run 早于脚本改成按 0x41 判 ACK，现见 `probe/phase2_tft.py:115-117`）。
- 动画路径官方显式 `responseCmd: SET_LED_USER_ANIMATION(65/0x41)` —— **只有动画路径是对的**（`TC.json → commands.SET_TFT_USER_ANIMATION.expected_ack_cmd=65`、`device-notifications.json:190`）。
- 0x51 发 0..5 每包回 `55 41`，**屏幕不切页**（`phase2_tft.json` 第 4 run、`TEST-REPORT.md:128`）。
- 实现：ACK 只认 `55 41`，靠"当前是否有 TFT 上传在途"与 LED 动画的同字 ACK 区分。

### 1.4 单帧 vs 动画：上传流程

```
单帧（16 包）                              动画（ceil((256+N*64800)/4096) 包）
1. 图片→240×135→RGB565（按设备字节序）      1. 逐帧 GIF帧/图片→240×135→RGB565
2. data = 64800B（无延时表）                2. delays = 各帧 delay（厘秒）
3. total = ceil(64800/4096) = 16            3. （可选）NV(rotate/flip) 作用于像素段
4. 逐包：写 4105B → 等 0x41 → 下一包         4. blob = MV(delays)[256B] + 帧0 + 帧1 + …
5. 无"生效"命令（写完即当前壁纸，但不可见）   5. 逐包：写 4105B → 等 0x41 → 下一包
                                           6. 无"生效"命令，固件直接播放
```

- 页面实际顺序（`tft-page.md:269-281`）：帧数超限确认 → （`builtInCount>1` 才发 0x51，MK87 跳过）→ 进度框 → 逐帧 canvas 编码 → `NV()` → `setTftUserAnimation(delays,pixels)` → 进度 0..99 → 成功置 100、延迟 500ms 关框。
- **先编码后旋转**：`NV()` 以 2 字节为像素单位整块搬运，与字节序无关（`tft-page.md:370-386`）。
- 单帧 64800B → 16 包，末包有效 3360B + 736B 零填充（`tft-page.md:245`）。3 帧实测 blob=194656B → 48 包（`phase2_tft.json` `anim` run）。

### 1.5 帧数上限、容量与实测性能

| 项 | 值 | 证据 |
|---|---|---|
| 设备上限 | `deviceInfo[22..23]` = **140** | `protocol.md:89` |
| 官方默认 | **135 帧**（<140，无需裁剪） | `restore_tft_default.json` |
| 单帧字节 | `240*135*2` = **64800** | `TC.json → pixel_encoding.frame_bytes` |
| 140 帧 | `256+140*64800` = **9,072,256B → 2215 包** | `tft-page.md:265` |
| 135 帧实测 | **8,748,256B → 2136 包 / 311.3s / ACK 2099·2136** | `restore_tft_default.json` |
| 单包写入 | **≈65.4ms**（4105B ÷ USB FS 64B/ms ≈ 64.1ms，带宽上限） | `phase2_tft.json`、`TEST-REPORT.md:102` |
| 纯写入吞吐 | **≈63KB/s**（4096B/65ms） | `TEST-REPORT.md:103,331` |
| 端到端吞吐 | **≈28KB/s**（2136 包/311.3s ≈ **146ms/包**） | 由 `restore_tft_default.json` 算得 |

> ⚠️ `TEST-REPORT.md:331` 的「63KB/s；135 帧 8.75MB ≈311s」不自洽：63KB/s 是纯写入上限，端到端还含等 ACK 与脚本轮询（每包最多等 0.35s、10ms 粒度）。按 **146ms/包** 估时最准：1 帧 ≈2.3s、3 帧 ≈7s、135 帧 ≈5.2min、140 帧 ≈5.4min。

### 1.6 像素格式与 PNG/GIF → RGB565 算法

- **RGB565、2B/像素、行优先（上→下、左→右）、无行填充/调色板**（`protocol.md:117-126`）。
- `v = (r&0xF8)<<8 | (g&0xFC)<<3 | (b&0xF8)>>3`（`TC.json → pixel_encoding.rgb565`、`tft_ref.js:59-62`）。
- 字节序由 `deviceInfo[35] tftColorByteOrder` 定（MK87=0）：**0 = 小端先低后高**（纯红 `00 F8`、纯绿 `E0 07`）；1 = 大端先高后低（`F8 00`/`07 E0`）（`tft-page.md:365-368`）。
- 转换步骤（前端 canvas 与后端 PIL 必须一致，`design.md:146`）：
  1. 解码 → RGB（丢 alpha，GIF 透明像素按黑）；
  2. **等比缩放 + 居中 + 黑底**：`s=min(240/w,135/h)`、`dw=round(w*s)`、`dh=round(h*s)`、`dx=floor((240-dw)/2)`、`dy=floor((135-dh)/2)`（官方页面就这么做，`tft-page.md:298-307,323`）；
  3. 逐像素 RGB565 → 按字节序写 2B；
  4. 断言单帧长度 = **64800**。
- 非 240×135 必须重采样（`restore_tft_default.py:32-33` LANCZOS；`probe/phase2_tft.py:59-88` 测试图）。导入图片任一边 >2000 直接拒绝（`TC.json → limits`）。
- GIF 逐帧合成（omggif）：disposal 2 = 清该矩形为黑、3 = 回滚上一保存帧、其它 = 保留；帧延时 = `frameInfo().delay`（厘秒）（`tft-page.md:295-325`）。

### 1.7 超时 / 重试 / 断线恢复

- 官方 `NX()`：每包等 `cmd===responseCmd` 的 input report，`timeout=2000ms`、`maxRetries=3`（首包+3 重发 = 最坏 8s/包）（`tft-page.md:229,246`）。
- 失败后果（**照抄必踩**）：`console.error` → 关设备 → `device.forget()`（丢 WebHID 授权）→ 清 `historyConnect` → `router.replace('/')` → `reject([])` → `$message.error`（`tft-page.md:247`、`wireless-profiles-led-animation.md:248-256`）。
- 自研建议（`design.md:64-66` 已定架构，细化为**【未验证】**）：
  1. ACK 超时压到 **300–500ms**（实测 ACK 延迟 ≈15ms，`TEST-REPORT.md:104`），失败立即重发同 `seq`；
  2. **重发幂等**：包内带 seq/total，固件按 `seq*4096` 定位写入（**推断，未验证**）；
  3. **断点续传**：记录最后被 ACK 的 `seq`，重连后从 `seq+1` 继续（固件是否接受非 0 起始 seq **未验证**）；保守方案整段重传（135 帧 ≈5min）；
  4. **绝不 `forget()`**：只标离线 + 提示重连（`wireless-profiles-led-animation.md:653`）；
  5. 上传线程独占 TFT 句柄（同接口并发读写会抢 report，`design.md:64`）；
  6. 取消 = 置标志位、下一包前退出，**不发命令**（协议无"取消上传"）。
- **丢 ACK ≠ 失败**：`restore_tft_default.json` 有 37 包未收到 ACK（2099/2136），屏幕仍完整恢复为官方默认动画 → 别拿 ACK 数量当成功判据。

## 2. 动画格式

### 2.1 数据组织：256B 延时表 + 帧拼接

`0x50` 数据体 = **256 字节延时表 + N×64800 字节像素**（`protocol.md:133-135`、`tft_ref.js:287-296`）：

```
t[0]      = 帧数 n
t[1..n-1] = min(delay_cs[i]*5, 255)   // i=0..n-2，最后一帧不写
t[n]      = 0                          // 终止符，正好覆盖"最后一帧的延时槽"
t[n+1..]  = 255                        // 其余填满
```

- 单位：表内 **1 = 2ms**（`delay_cs*5` = `delay_ms/2`），上限 255 → **单帧最长 510ms**（`TC.json → pixel_encoding.delay_table`、`tft_ref.js:120-132`）。
- **第 n 帧的延时永不上传**（被终止符 0 顶掉）→ 可见时长 ≈ Σ(前 n-1 帧)（**推断，未验证**）。
- 像素段**纯拼接**：无分隔符、无帧头、无索引表，帧边界只能靠 64800 整除算出。
- **分包与帧边界不对齐**：包 0 = `256B 表 + 帧0 前 3840B`；之后每 4096B 一块（`tft-page.md:230,265`）→ **不能按帧发包**，先拼整段 blob 再切。
- 旋转/镜像只作用像素段、且在拼表**之前**（`tft-page.md:386`）；MK87 无 `dataTransform` → 恒等。

### 2.2 帧率控制

- **命令里没有 fps/interval 字段**，帧率完全由延时表逐帧给定（`tft_ref.js:120-132`）。
- 换算：`delay_cs = round(100/fps)`；`t = min(delay_cs*5, 255)`。`fps=10 → 10 → t=50 → 100ms/帧`；`fps=20 → 5 → 25 → 50ms`；低于 ~1.96fps 被 510ms 截断。
- 官方默认 135 帧**全部 `delay=10`（厘秒）** → 10fps、13.5s 一轮（`_default_gif.json`）。
- `design.md:141` 的 `fps` 参数按上式转延时表，**不要在协议层另造 fps 字段**。循环次数不可配；是否循环播放 **未验证**（只确认"推上去就播放"，`TEST-REPORT.md:108-112`）。

### 2.3 官方默认动画 JSON 结构

来源 `https://config.driveall.cn/gif/AK980_PRO/defaultGif.json`（页面路径 `/gif/<tftConfig.name>/defaultGif.json`，MK87 的 `name=AK980_PRO`；`tft-page.md:43,349`、`restore_tft_default.py:2-5`）。

```json
{ "width": 240, "height": 135, "frames": 135,
  "frameData": [ { "dataUrl": "data:image/png;base64,iVBORw0K…", "delay": 10 } ] }
```

| 字段 | 实测 | 说明 |
|---|---|---|
| `width`/`height` | 240 / 135 | 与 `tftConfig` 一致 |
| `frames` | 135 | = `frameData.length` |
| `frameData[i].dataUrl` | `data:image/png;base64,…` | **PNG**，非原始像素；本地副本 `docs/_default_gif.json` |
| `frameData[i].delay` | 全为 `10` | 单位**厘秒(10ms)**，来自 omggif |
| 播放参数 | **无** | 没有 fps/loop/disposal；播放语义全靠延时表 |

- 前端动画库同 schema，存 localforage 键 `gif_files_w240h135`（竖屏 `gif_files_w135h240`），导出名 `defaultGif.json`（`TC.json → storage`、`tft-page.md:340-349`）。静图分支固定 `delay:100`（1s）、1 帧（`tft-page.md:324`）。

### 2.4 恢复默认动画（脚本流程，可照抄）

`probe/restore_tft_default.py`（135 帧 / 311.3s 实测成功）：

1. 读 `docs/_default_gif.json` → `frameData`/`delays`（支持 `--limit N`、`--dry`）；
2. `GET_DEVICE_INFO` 取 `tftMaxFrames`（校验）与 `tftColorByteOrder`（决定字节序）；
3. 逐帧：base64 → PNG → `convert('RGB')` → 非 240×135 则 LANCZOS 缩放 → 逐像素 RGB565 → 64800B；
4. `mv[0]=len(delays)`、`mv[i+1]=min(delays[i]*5,255)`、`mv[len(delays)]=0`，**其余保持 0**（脚本未按官方填 255；135<256 故不影响）；
5. `blob = mv + pixels`；`packets = ceil(len/4096)`；
6. 逐包：头 `AA 50 seqLo seqHi totalLo totalHi 50 06` + 4096B（末包零填充），写 4105B → 轮询等 `55 41`（窗口 0.35s）；
7. 统计 ACK/耗时写 `docs/restore_tft_default.json` 供回归。
- UI 对应 `POST /api/tft/default`（异步任务 + 进度，`design.md:142`），默认动画随包分发（`design.md:53`）。
- 恢复前**无法备份原屏幕内容**（协议无读回命令，`TEST-REPORT.md:315`）→ 必须二次确认。

## 3. 屏幕相关其它能力

### 3.1 时间同步：10B `SET_TEMPORARY_COMMAND_DATA(0x34)`

走**主协议通道**（0xFF68，64B 报告），`contentSize` 用默认 **24**（8..17 放 10B 数据，其余补 0），`timeout=500ms`（`frameVersion===1`→2000），`maxRetries=3`（`tft-page.md:392-415`、`protocol.md:140-141`）。

| 偏移 | 字段 | 说明 |
|---|---|---|
| 0..2 | `5A 01 5A` | 固定魔数头 |
| 3 | 年 `%100` | 2026 → `0x1A` |
| 4 / 5 | 月 1–12 / 日 | |
| 6 / 7 / 8 | 时 / 分 / 秒 | **本地时间**，无时区字段 |
| 9 | 星期 | `dayjs().day()`，**0=周日**…6=周六 |

- 实测回显 `5A 01 5A 1A 0B 01 06 3B 17 00`（2026-11-01 06:59:23 周日，原样 ACK，`phase2_tft.json` 的 `time` run；另一样本 `5A 01 5A 1A 0B 01 06 2C 30 00` 见 `TEST-REPORT.md:92`）。
- **每次连接自动对时一次**（MK87 无 `hideScreenTimeCalibration`、`tftDirection≠255`），另有「时间校准」按钮（`tft-page.md:416-424`）；接口 `POST /api/device/time-sync`（`design.md:82`）。

### 3.2 12/24 小时制（`tftDisplayTime`）—— 无可见效果

- 位置：`SET_GAME_MODE(0x21/33)` payload **偏移 7**；**0=24h、1=12h**（不是"是否显示时间"）（`deepdive-mk87.md:73-74`、`FEATURES.md:39,68`）。
- 实测：写 0/1 均成功、回读一致、**断电重启后仍一致**，但屏幕时钟格式**始终不变**（发 19:05，12h 下仍 19:05）→ fw1.19 无可见作用，判 ⛔（`TEST-REPORT.md:130-132,283-288`）。
- UI 可保留该开关（写回原值），但**不要承诺任何屏幕变化**；默认 0。

### 3.3 内置页索引 / 系统信息 —— 均不支持

- `0x51` 发 0..5：每包回 `55 41`（通用 ACK），**屏幕无反应** → 固件不支持切页；页面完全由设备端菜单控制（`TEST-REPORT.md:128-129`）。官方也从不发（无 `builtInCount`）→ 死代码。
- 系统信息（CPU/GPU/温度/天气，`0x34` 24B）**可发且回显正常，但 MK87 无系统信息页** → 无可观察目标（`TEST-REPORT.md:134-137`、`tft-page.md:187-214`）；8s 轮询还需 `isShowTftInfo===true`（MK87 缺省）+ `55 FA 06 01` 门控。
- **不要实现**：内置页切换、系统信息推送、壁纸页 UI（写入不可见）。

### 3.4 设备端菜单结构（真机，`TEST-REPORT.md:114-124`）

| 页面 | 内容 |
|---|---|
| 主页 | 日期 `2026/11/01`、电量%+充电图标、时钟 `19:11:03`、底部状态图标（WIN/U1/BT2/锁/A/1） |
| 设置菜单 | 灯光效果 / 灯光颜色 / 灯光亮度 / 灯光速率 / 语言选择（**旋钮操作**） |
| 自定义动画页 | 播放主机通过 0x50 推上去的内容；另有音量/旋钮数值 OSD、电量/连接状态 |

- 无系统信息页、无壁纸页、无 TFT 亮度命令（`brightness` 只属灯效）、除 `tftDisplayTime` 外无屏保配置（`tft-page.md:428-439`）。
- 方向只由 `deviceInfo[28] tftDirection` 决定：`0` 横屏 / `1` 竖屏（宽高互换、键 `w135h240`）/ `255` 无屏（剔除 tft 路由）。

## 4. 2.4G 无线

### 4.1 身份与读取顺序

| 项 | 值 | 证据 |
|---|---|---|
| VID/PID | `0x0C45` / `0xFEFE`（3141 / 65278） | `TEST-REPORT.md:223` |
| product string | **`2.4G Dongle`** | 同上 |
| `GET_DEVICE_INFO` | `manufacturer=1`（`byte[12..13]`）、`product=18`（`byte[14..15]`）、`workMode=2`（`byte[16]`）、battery=73%、charge=1、fw=1.19 | `TEST-REPORT.md:224-225`、`protocol.md:82-86` |
| 完整设备 ID | `${vid}:${pid}:${productName}:${manufacturer}:${product}` = `3141:65278:2.4G Dongle:1:18` | `wireless-profiles-led-animation.md:93-105` |
| 配置键 | `3141-65278-2.4G Dongle-1-18` | `wireless-constants.json:11-190` |

- 流程：枚举 HID → `vid:pid:productName` 命中 64 项特殊 2.4G 表 → 打开读一次 `GET_DEVICE_INFO` 取 manufacturer/product → 拼 5 段 ID → 查机型配置（`wireless-profiles-led-animation.md:74-128`、`S_special24G.json`）。
- **不要用 pid 猜机型**：同一接收器 pid 下有多把键盘（bundle 内 42 个接收器配置），pid 只决定"哪种接收器"，product 才决定"哪把键盘"（`wireless-profiles-led-animation.md:126-128,601`）。

### 4.2 协议接口

| 接口 | usagePage | 报告长度 | 结论 |
|---|---|---|---|
| MI_03 | **0xFF60** | **33B（32B payload）** | ✅ 唯一可用协议口：GET/SET/读矩阵/读灯全通 |
| MI_04 | 0xFF59 | 65B（64B payload） | ❌ **无任何响应**，且不在官方 WebHID 过滤器表 |
| MI_02/COL05 | 0xFFFF | in=4B（report ID=5） | 只用于**唤醒帧** `05 A6 FF 01` |

- 证据：`TEST-REPORT.md:229-232`、`docs/_p6_variants.json`（`proto32 {0xFF60, out_len 33}` / `proto64 {0xFF59, out_len 65}`）、`docs/phase6_wireless.json`。
- 官方过滤器表 `[0xFF68,0xFF80,0xFF60,0xFF00,0xFF01,0xFF5B]`：**含 0xFF60，不含 0xFFFF/0xFF59**（`key-events.md:131-142`）→ 官方收不到唤醒帧，自研必须自己打开 0xFFFF。
- **2.4G 没有 0xFF67（TFT）接口**，上传类命令 `connectType==='USB' ? LX() : device` 恒走接收器（`wireless-profiles-led-animation.md:159-160,371-372`）。

### 4.3 命令可用性与配置共享

- 2.4G 下 `GET_DEVICE_INFO / GET_GAME_MODE / GET_LED_EFFECT / GET_KEY / GET_FN_KEY / GET_ALL_LIGHTS_RGB(51/55/59)` 均可用（`TEST-REPORT.md:231-235`、`phase6_wireless.json`）。
- **配置存在键盘端，双通道共享**：2.4G 的 `GET_KEY`/`GET_FN_KEY` 与 USB dump **逐字节一致**（`TEST-REPORT.md:234`）→ 改键/宏只需在一种连接下做。
- 2.4G 写灯效生效，但 `SET_LED_EFFECT` 的 color/colorMode **回读可能 ≠ 写入**（显示是对的）→ **不能拿回读当写成功判据**，改判 `GET_ALL_LIGHTS_RGB`（`TEST-REPORT.md:235-237`）。

### 4.4 休眠时间（`sleepTime`）

| 项 | 值 | 证据 |
|---|---|---|
| 命令 | `GET_GAME_MODE(17)` / `SET_GAME_MODE(33)`，payload **56B** | `TEST-REPORT.md:91`、`deepdive-mk87.md:91` |
| 字段 | payload **偏移 3**（u8） | `TC.json → game_mode.offsets.3`、`probe/phase6_sleep_wake.py:72-79` |
| 单位/取值 | **分钟**；`0`=关；官方 UI 1/10/20/30 | `TEST-REPORT.md:275` |
| 出厂实测 | **5 min**（56B 原始 `[3]=05`） | `restore_state.json`、`deepdive-mk87.md:64` |
| 2.4G UI | **强制显示**休眠时间（USB 下由配置决定） | `wireless-profiles-led-animation.md:379` |

- 写流程：读 56B → 只改 `[3]` → 整包回写（其余字段尤其 `0xFF`=不支持 原样保留）→ 回读校验（`probe/phase6_sleep_wake.py:72-79`）。接口 `PUT /api/wireless {sleepTime}`（`design.md:177`）。
- 实测：设 1 分钟 → 闲置 **59.96s** 收到断连通知（`phase6_sleep_wake.json`）。注：`TC.json` 的 `game_mode.payload_len: 24` 是静态误记，真机 `GET_GAME_MODE` 为 **56B**（`TEST-REPORT.md:91`、`design.md:80`）。

### 4.5 通知帧：断连 / 休眠 / 唤醒

| 时间（实测） | 接口 | 帧（含 report ID） | 判定 |
|---|---|---|---|
| 闲置 59.96s | `0xFF60`（33B） | `00 55 FC 04 30 00 00 01 00 FF FF…` | **断连 `0xFC/type=4`** |
| 按键唤醒 213.66s | `0xFFFF`/MI_02 COL05（in=4，report ID=5） | `05 A6 FF 01` | **唤醒** |
| 再次闲置 273.81s | `0xFF60` | `00 55 FC 04 …` | 断连，**可复现** |

（`docs/phase6_sleep_wake.json`、`TEST-REPORT.md:267-271`）

- **上报帧是扁平结构**：`55 <cmd> <subtype> <payload…>`，subtype 在 `帧[2]` —— 没有 8 字节大包头，**别用响应帧解析器 slice(8) 去解**（`device-notifications.json:37-47`、`key-events.md:185-200`）。
- `0xFC`(252) 子类型：`4`=断连、`5`=设备复位、`6`=休眠；MK87 实测**只见到 4**，未捕获 `0xFC/6`（`TEST-REPORT.md:276-277`）。
- 唤醒帧是**唯一非 0x55 上报**：`A6 FF 01` 三字节固定（`key-events.md:300-309`）。
- 通道结论：**断连/复位/休眠在 0xFF60；唤醒在 0xFFFF/report ID=5**，分别监听（`TEST-REPORT.md:363-364`、`design.md:63`）。
- 驱动侧**不发任何命令**唤醒（bundle 无 wake 命令、无 feature report），唤醒是硬件行为（`wireless-profiles-led-animation.md:222-230`）；空闲无心跳：75s 0 条（`docs/notify_capture.json`）、5s 0 条（`deepdive-mk87.md:67`）。
- 状态机：`READY →(0xFC/4) DISCONNECTED`（提示重连、不 forget）；`READY →(0xFC/6) SLEEPING`（全屏遮罩）；`SLEEPING →(A6 FF 01) READY`（`wireless-constants.json:556-568`）。

### 4.6 2.4G 不支持的能力

| 能力 | 结论 | 证据 |
|---|---|---|
| 音乐律动 | **官方明确不支持**；真机 0x32/0x35/0x3C 三种帧格式 6 个变体全 `works:false`，只出现「短暂白脉冲/随机色/竖条纹」 | `TEST-REPORT.md:239-251`、`_p6_variants.json` |
| 根因 | 官方 2.4G 音乐分支要求 `reportCount===64 && lightingVersion===1`；MK87 是 **33B 报告 + lightingVersion=0** | `TEST-REPORT.md:246-248` |
| TFT 上传/屏幕页 | 无 0xFF67 接口、`routesName` 无 `tft` | `wireless-profiles-led-animation.md:137,159-160` |
| 灯效 GIF 动画 | `gifMaxFrames=0`（与连接方式无关） | `wireless-constants.json:411-430` |

→ 无线模式下音乐律动、TFT 页应**直接禁用并说明原因**（`design.md:94` 已有 `music`/`tft` 能力位）。

### 4.7 USB + dongle 同插的 Windows 资源冲突（检测思路）

**现象【实测】**：dongle 首次插入报 **Code 10（`CM_PROB_FAILED_START`）**，`ProblemStatus=0xC000009A`（`STATUS_INSUFFICIENT_RESOURCES`）；与键盘 USB 复合设备同插也触发；**拔掉 dongle 后键盘立刻恢复**。本质是 Windows 复合设备资源分配（8 个 HID 顶层集合 × 2 设备），非固件问题，**驱动侧无法修复**（`TEST-REPORT.md:253-259`、`FEATURES.md:92`、`design.md:218-220`）。

**工具侧只能"检测 + 提示"**（**设计建议，本仓库未实现，未验证**）：

1. **枚举判定（跨平台最省事）**：`hid.enumerate(0x0C45)` 按 pid 分类 —— 期望同时看到 `32839`（键盘）与 `65278`（dongle）；只看到一个即提示"另一个未枚举成功"。注意区分"没插"（USB 层就没有）与"插了没起来"（需第 2 步）。
2. **Windows 设备状态（能区分 Code 10）**：`CM_Get_Device_ID_List("USB\\VID_0C45&PID_FEFE", …)` → `CM_Locate_DevNodeW` → `CM_Get_DevNode_Status`（`DN_HAS_PROBLEM` + problem）→ `CM_Get_DevNode_Registry_PropertyW(CM_DRP_PROBLEM_CODE)` 取 `0xC000009A`；等价做法 `Get-PnpDevice -PresentOnly | ? InstanceId -match 'VID_0C45&PID_(8047|FEFE)'` 看 `Status/Problem`。
3. 文案：「2.4G 接收器与键盘争用 USB 资源（0xC000009A），请插到不同 USB 控制器/根集线器，或只保留一个」；**不建议**软件禁用/重启 devnode 去"修复"（需管理员且易误伤，`design.md:215`）；结果上报 `GET /api/status` 的 `conflicts[]`（`design.md:96-100`）。

> `design.md:220` 提到「软件禁用不可行（`CR_NOT_DISABLEABLE`）」，但本仓库 `TEST-REPORT.md` 只到 §8.6，找不到 §8.7 与该常量 → 该条按 **【未验证】** 处理，实现前需复核。

## 5. 按键事件捕获

### 5.1 为什么厂商协议拿不到

- 全 bundle 只有 **6 处** `[0]===85`（0x55）消费点，穷举后**无一处解析按键位图/事件**（`key-events.md:263-284`）。
- 可疑命令都不成立：`GET_MAGNETIC_AXIS_KEY_STATUS(0x60)` 是**死枚举**（仅 1 处拼写、从未发送、无解析器）；`GET_MAGNETIC_AXIS_STATUS(0x68)` 只用于 `frameVersion===1` 磁轴校准轮询；`GET_KEY(0x12)` 读的是**键表映射**不是按下状态（`key-events.md:364-373`、`device-notifications.json:202-228`）。
- 设备侧印证：空闲 75s / 5s 均 **0 条**主动上报（`notify_capture.json`、`deepdive-mk87.md:67`）。
- 官方"按键测试页"自己也不用 HID：`document.addEventListener('keydown'/'keyup')` + `KeyboardEvent.code`，104 键 ANSI 写死（`key-events.md:55-125`、`FEATURES.md:69`）。
- ⇒ 只能读 OS 解析后的键盘输入。代价：改键/宏生效后只能看到**映射后**的 usage，拿不到物理键位（`key-events.md:416-417`）。

### 5.2 Windows：RawInput 实现要点（已实测可用）

`probe/phase7_rawinput.py`（纯 ctypes）：

1. 注册窗口类 + **隐藏窗口**（`CreateWindowExW` 0 尺寸、无 WS_VISIBLE）；`RAWINPUTDEVICE[2]` = `{0x01,0x06,RIDEV_INPUTSINK(0x100),hwnd}`（键盘）+ `{0x0C,0x01,RIDEV_INPUTSINK,hwnd}`（consumer），`RegisterRawInputDevices(devs,2,sizeof(RAWINPUTDEVICE))`；
2. 消息泵：`PeekMessageW(PM_REMOVE)` → `WM_INPUT(0x00FF)` → `GetRawInputData(RID_INPUT,lParam,…)`（两次调用：先取 size 再取数据）；
3. 解析 `RAWINPUTHEADER{dwType,dwSize,hDevice,wParam}`：`RIM_TYPEKEYBOARD(1)` → `RAWKEYBOARD{MakeCode,Flags,VKey,Message,ExtraInformation}`；`RIM_TYPEHID(2)` → `{dwSizeHid,dwCount,bRawData[]}`；
4. **设备归属过滤**：`GetRawInputDeviceInfoW(hDevice, RIDI_DEVICENAME=0x20000007, …)` 取路径，判前缀 `\\?\HID#VID_0C45&PID_8047&MI_00#`；其它键盘路径不同直接丢弃（`phase7_rawinput.py:94-101`、`phase7_rawinput.json`）。

**字段语义（实测 5 条事件）**

| 字段 | 含义 | 实测样例 |
|---|---|---|
| `VKey` | 虚拟键码（**不是 HID usage**） | `0x42`(B)、`0x31`('1')、`0x0D`(Enter) |
| `MakeCode` | PS/2 扫描码 | `0x30`(B)、`0x02`('1')、`0x1C`(Enter) |
| `Flags` | bit0=`RI_KEY_BREAK`（**1=抬起**）；bit1=E0 扩展键 | 按下 0 / 抬起 1 |
| `Message` | `0x0100`=WM_KEYDOWN、`0x0101`=WM_KEYUP | 256 / 257 |

（`docs/phase7_rawinput.json`、`TEST-REPORT.md:294-297`）

- 坑：RawInput **不给 HID usage**（`TEST-REPORT.md:299-300`）→ 要 usage 级映射必须自维护 `VKey→usage` 表，或改用 HID 键盘集合（Windows 上被拒，见 §5.4）。
- 必须带 `RIDEV_INPUTSINK`，否则窗口不在前台收不到（`phase7_rawinput.py:151-153`）；`ExtraInformation` 实测恒 0。
- 服务端：独立线程 + 隐藏窗口消息泵，事件经总线推 WS（`design.md:16,63,195`），**不要**在主线程跑消息泵。

### 5.3 Linux：evdev（**未验证**，本仓库无 Linux 实测）

- 权限：`/dev/input/event*` 属 `root:input`，需 `input` 组或 udev 规则（`design.md:217`）。
- 读取：`open("/dev/input/eventN")` → `read()` 出 `input_event{timeval,type,code,value}`（24B/条，64 位）；只取 `type==EV_KEY(1)`，`value` 1=按下 / 0=抬起 / **2=自动重复（丢弃）**。
- 定位设备：`/sys/class/input/event*/device/uevent` 里的 `HID_ID`（形如 `0003:00000C45:00008047`）/`HID_NAME`，或 libudev 匹配 VID/PID；`/proc/bus/input/devices` 亦可。
- **`code` 是 Linux `KEY_*`（input-event-codes.h），不是 HID usage**（`KEY_A=30` vs HID `0x04`；`KEY_ENTER=28` vs HID `0x28`）→ 需自建 `KEY_*→usage` 表，**不要复用 Windows 的 VKey 表**。
- 其它差异：`SYN_REPORT` 同步事件、需要独占时用 `EVIOCGRAB`；Wayland 下可考虑 libinput。

### 5.4 HID `\kbd` 直读：err=5 的结论

- 直接 `CreateFile` 打开键盘集合 `HID\VID_0C45&PID_8047&MI_00` 的 `\kbd` → **失败 err=5（ACCESS_DENIED）**；`MI_01 COL03` 同样被拒 —— Windows 把键盘类 HID 保留给系统（`TEST-REPORT.md:292-293`）。
- 结果佐证：`docs/phase7_keyevents.json` 的 `n_events: 0`、`ifaces: []`（0 个接口成功打开）。
- ⇒ Windows 放弃 HID 直读，走 RawInput；Linux 的 `hidraw` 通常可读（`/dev/hidraw*` + udev 规则），可作备选（**未验证**）。

### 5.5 按键测试页需要的数据字段

| 字段 | 必需 | 说明 / 来源 |
|---|---|---|
| `down`（按下/抬起） | ✅ | RawInput `Flags&1` 或 `Message`；evdev `value` |
| `keyName` | ✅ | 键名（`A`/`Enter`/`F5`…），由映射表给 |
| `code`（扫描码/位置码） | ✅ | RawInput `MakeCode`；evdev `code`；用于区分左右 Ctrl/Shift |
| `vkey` / `hidUsage` | 二选一 | Windows 给 `VKey`，Linux 给 `KEY_*`；统一层建议内部存 HID usage |
| `devicePath` | ✅ | 归属过滤证据（`\\?\HID#VID_0C45&PID_8047&MI_00#…`） |
| `ts` 时间戳 | ✅ | 按下/抬起都记，用于延迟/APM 统计 |
| `pressedCount`/`totalDown`/`totalUp` | 建议 | 官方页有：每键按下次数、按下总数、抬起总数（`key-events.md:71-97`） |
| APM / 单键延迟 / 消抖 | 可选（**自研扩展**） | 官方页面**没有**，需自己用 `ts` 算 |

- 键位图（87 键物理布局、槽位号、空的显示区、LED 槽）**不在本文件**：见 `spec-keymap.md`（写作时 `driver/docs/` 下只有 `design.md`，该文件尚未生成，只留引用）。
- 官方键表是**写死的 104 键 ANSI**（`KeyboardEvent.code`），与实际 87 键不一一对应；自研页应按 `spec-keymap.md` 的 87 键画，被屏幕占位的 PrintScreen/ScrollLock/Pause 单独说明（`key-events.md:57-66`、`TEST-REPORT.md:80-87`）。

## 6. 前端所需

### 6.1 TFT 页（对应 `design.md:136-147`）

| 元数据 | 值 | 来源 |
|---|---|---|
| `width`/`height` | 240 / 135 | `deviceInfo`/`tftConfig` |
| `pixelFormat` | `rgb565`（2B/px，行优先，无 padding） | `protocol.md:117-126` |
| `byteOrder` | 0=小端（MK87） | `deviceInfo[35]` |
| `maxFrames` | **140**（从设备读，别写死） | `deviceInfo[22..23]` |
| 官方默认 | **135 帧 / 10fps / delay=10cs** | `_default_gif.json` |
| 单帧字节 | 64800（前端转换后必须断言） | §1.6 |
| 进度 | 0..99 逐包，100 = 完成（再等 ~500ms 关框） | `TC.json → limits` |
| 预计耗时 | ≈146ms/包 → 1 帧 ≈2.3s、135 帧 ≈5.2min（显示 ETA） | §1.5 |
| 帧数超限 | 保存时裁剪 + 二次确认（「最多 N 帧」） | `TC.json → limits.max_frames_device`、`ui.i18n_keys.screen_text11/12` |
| 恢复默认 | 独立按钮 + 二次确认（**无法备份原内容**） | §2.4 |
| 必须隐藏 | 壁纸上传、内置页选择器、系统信息推送、屏幕亮度 | §3.3 |
| 可保留 | 时间校准按钮（连接时也会自动对时）、12/24h 开关（**注明无可见效果**） | §3.1/§3.2 |

- 前端职责：图片/GIF → canvas 240×135（等比缩放+居中+黑底）→ RGB565 base64（64800B/帧）→ `POST /api/tft/upload {mode,fps,frames[]}`；进度走 WS `progress`；`POST /api/tft/cancel` 取消（`design.md:141-146,193`）。
- 预览用 `delay`（厘秒）驱动定时器 = 设备帧率；必须显示「帧数 / 上限」与预计耗时。动画库存 localforage 键 `gif_files_w240h135`（item = `{width,height,frames,frameData:[{dataUrl,delay}]}`，`TC.json → storage`）。

### 6.2 无线页（对应 `design.md:172-177`）

| 字段 | 说明 |
|---|---|
| `transport` | `"2.4g"`/`"usb"`（按实际打开的接口：0xFF60 → 2.4g） |
| `connected` | 收到 `0xFC/4` 或枚举消失 → false（提示重连，**不要自动 forget**） |
| `identity` | `{manufacturer:1, product:18, workMode:2, productName:"2.4G Dongle", pid:65278}`，展示 5 段 ID |
| `battery`/`charging` | `GET_DEVICE_INFO[17]/[18]`；2.4G 也可用 cmd55/59 响应里的电量刷新 |
| `sleepTime` | 分钟；下拉 `0=关/1/10/20/30`；写 `SET_GAME_MODE[3]` 后回读校验 |
| 能力位 | 2.4G 下 `music=false`、`tft=false`（禁用入口并说明原因） |
| 通知状态 | `SLEEPING` 全屏遮罩「设备已进入休眠，请按任意按键唤醒」；`A6 FF 01` 解除；唤醒监听在 `0xFFFF`（report ID=5） |
| 冲突提示 | `conflicts[]`：USB+dongle 同插 → 换控制器/拔一个（§4.7） |

### 6.3 按键测试页（对应 `design.md:178-180`）

- 键位图：引用 `spec-keymap.md`（87 键物理布局 + 槽位号 + 空槽说明）。
- 事件字段见 §5.5；WS 形状与 `design.md:195` 一致 `{"type":"keyevent","data":{"vkey":65,"name":"A","down":true,"ts":…}}`，建议补 `code`（扫描码）与 `hidUsage`。
- 交互：三态着色（未按/按下中/按过）、每键计数、按下/抬起总数、日志 100 条（`key-events.md:71-97`）、`blur` 时清"按住"集合。
- 页面须标注"只测 OS 收到的按键，不区分物理键位；改键/宏后看到的是映射后的键"（§5.1）。

## 7. 未验证清单（实现前需复核）

1. 断点续传可行性（固件是否接受非 0 起始 `seq`）与重发同 `seq` 是否幂等——§1.7。
2. 延时表末帧槽被 0 覆盖后，固件对末帧实际时长的处理——§2.1。
3. 动画是否循环、循环次数是否可配——§2.2。
4. `0xFC/type=6`（休眠）在 MK87 上是否永不发送（420s 监听未捕获）——§4.5。
5. `design.md:220` 的 `CR_NOT_DISABLEABLE`：本仓库 TEST-REPORT 无 §8.7，无法复核——§4.7。
6. `CM_*` 设备状态查询的具体实现与文案——§4.7（纯设计建议）。
7. Linux evdev 路径（权限、`KEY_*→usage` 映射、Wayland 兼容）——§5.3。
8. RawInput 对 `0x0C/0x01`（consumer）返回 `RIM_TYPEKEYBOARD` 还是 `RIM_TYPEHID`（实测样本无多媒体键）。
9. 2.4G 下 `sleepTime` 之外的 game mode 字段（`powerMode` 等）MK87 是否支持（多数回 0xFF）。

## 8. 主要证据文件

| 文件 | 用途 |
|---|---|
| `docs/TEST-REPORT.md` | 真机主源（TFT / 2.4G / 按键 / 性能 / 8 条修正） |
| `docs/tft-page.md`、`docs/tft-constants.json` | TFT 静态还原 + 常量表 |
| `docs/wireless-profiles-led-animation.md`、`docs/wireless-constants.json` | 2.4G 身份/通道/通知/动画 |
| `docs/key-events.md`、`docs/device-notifications.json`、`docs/protocol.md` | 按键事件、上报帧语义、帧格式与命令表 |
| `probe/phase2_tft.py`、`restore_tft_default.py`、`phase2_builtin.py`、`scripts/tft_ref.js` | TFT 上传/恢复/0x51 参考实现 + 逐字节等价编解码 |
| `probe/phase6_wireless.py`、`phase6_sleep_wake.py`、`monitor_notify.py`、`phase7_rawinput.py`、`phase7_keyevents.py` | 2.4G 身份/通知、RawInput 与 HID 直读对照实验 |
| `docs/_default_gif.json`、`docs/restore_tft_default.json`、`docs/phase*.json` | 实测结果数据 |
