# AJAZZ MK87 真机测试报告（Phase 0–7）

> 测试日期：2026-11-01 06:41–07:56（UTC+8）｜设备：VID 0C45 / PID 8047，固件 v1.19
> 测试方式：全部用自研 `probe/ajazz.py` 原生 HID 通道（不用官方网页驱动、不用官方 Music.exe）
> 结果文件：`docs/phase0_selftest.json` … `docs/phase7_rawinput.json`、`docs/restore_tft_default.json`
> 结论：**静态逆向的协议全部经真机确认可用**；同时发现 **8 处需要修正/补充的结论**（见 §12）。
> v0.1.3 音乐律动复核（2026-11-03）见 **§15**。
> 说明：§2–§14 的 20fps / 15.5ms 等数据为 **2026-11-01 基线（v0.1.2 及以前）**；v0.1.3 默认 66fps，复核见 §15。

---

## 0. 一句话结论

| 阶段 | 内容 | 结果 |
|---|---|---|
| Phase 0 | 写通道自检（5 条命令原样回写+回读） | ✅ 5/5 PASS |
| Phase 1 | 灯效模式表 / 关灯 / 亮度 / 自定义灯 / 游戏模式 / 屏幕时间 | ✅ 全通，产出 4 条新结论 |
| Phase 2 | TFT 壁纸 / 动画 / 内置索引 / 时间 / 12-24h / 页面结构 | ✅ 动画链路全通；壁纸与内置索引在 MK87 无显示通道 |
| Phase 3 | 改键（普通层 / FUNC / FN 层 / phantom 槽 / 25 槽语义 / 宏写入） | ✅ 全通，产出 4 条新结论 |
| Phase 4 | 逐键实时帧流（音乐通道 cmd 0x32） | ✅ **激活条件已找到**（H2 成立），20fps 稳定 |
| Phase 5 | 自研音乐律动链路（音频→算法→渲染→帧流） | ✅ 3 个官方渲染器全部在真机点亮 |
| Phase 6 | 2.4G 无线（身份/通道/灯效/矩阵/通知） | ✅ 全通；⛔ 音乐律动官方确认 2.4G 不支持；✅ 断连/唤醒帧已捕获 |
| Phase 7 | 按键事件捕获方案 | ✅ RawInput 可用；HID `\kbd` 直读被系统拒绝 |
| 收尾 | 全部被改状态恢复并逐字节比对 | ✅ ALL OK |

---

## 1. 测试环境

- Windows 10 LTSC 1809；Python 3.12（ctypes 原生 HID）；Node 24（渲染器）；Pillow（TFT 图像）
- 关键工具：`probe/phase0_selftest.py`（写通道自检）、`phase1_lighting.py/_diag*/_brightness`、
  `phase2_tft.py/_builtin.py`、`phase3_keys.py/_official.py`、`phase4_frames.py/_diag/_timeout`、
  `phase5_music.py` + `scripts/gen_music_frames.js`、`phase6_wireless.py`、`phase7_rawinput.py`、
  `restore_tft_default.py`
- 备份：`docs/device_dump_pre_test.json`（SHA256 `7CDD1ED7…`，13 类全量读取）

---

## 2. Phase 0：写通道自检（全 PASS）

| 命令 | 包数 | ACK | 回读 |
|---|---|---|---|
| `SET_GAME_MODE` 0x21 | 1 | 1 | 逐字节一致 |
| `SET_LED_EFFECT` 0x23 | 1 | 1 | 逐字节一致 |
| `SET_KEY` 0x22（512B） | 10 | 10 | 逐字节一致 |
| `SET_FN_KEY` 0x26（512B） | 10 | 10 | 逐字节一致 |
| `SET_CUSTOM_LED_DATA` 0x24（512B） | 10 | 10 | 逐字节一致 |

读取耗时基线：`GET_KEY` 512B ≈ 31.5 ms、`GET_LED_EFFECT` ≈ 1.7 ms、`GET_ALL_LIGHTS_RGB` ≈ 29 ms。
**ACK 是对所写 payload 的原样回显**（后续所有写命令都遵循此规律）。

---

## 3. Phase 1：灯效与设置

### 3.1 模式全表（1..19 + 20/21/128）

19 个官方模式**全部能点亮且行为符合名称**（自动采样：点亮键数 / 平均色 / 两帧间变化键数）：

- 静态类：1 静态恒亮（85 键恒定）、2 单点亮（1 键跑动）、3 单熄灭（1 键熄灭）
- 动效类：4/5/6/8/9/10/11/12/16/17/18/19 均为动态（采样两帧间 13–85 键颜色变化）
- 触发类：13 一触即发 / 14 一石二鸟 / 15 涟漪扩散 在无按键时只有 1 颗亮（等待按键触发）
- 128 自定义生效；**20 / 21 / 128 三个模式共用同一张 `SET_CUSTOM_LED_DATA` 表**（三者显示完全相同，
  真机证实 `customModeFamily` 推断成立）

### 3.2 关灯 / 亮度（新结论）

- **`mode=0` 关灯后，Fn 键仍亮红灯**：这是**充电指示灯**（用户在充电，插线即亮），
  不属于 LED 数据可控制范围（全表写 0 也压不掉）。
- 亮度字段（payload[9]）真机映射：
  - **1..6 是 identity**（写入=回读），实际 PWM 为 0 / 49 / 97 / 143 / 191 / 253
  - 即 **brightness=1 = 键盘全灭**（官方 UI 最小值！）；2..6 近似线性
  - **越界值未定义**：0→回读 255、7→11、8→12、9→13、10→14、11→15、12→16、15→19、16/31→1、100→13、255→0
    （两次写一致，不是抖动；结论：不要发 1..6 以外的值）
  - 亮度切换**无渐变**（100ms 内立即到位）

### 3.3 自定义逐键灯（新结论）

`SET_LED_EFFECT(128)` + `SET_CUSTOM_LED_DATA`：写槽 0..7 = 红/绿/蓝/黄/品红/青/白/黑，
采样回读 **逐键完全对应**，颜色值 255 落回 253（驱动 PWM 上限）。

### 3.4 物理 LED 槽位表（修正官方 keyList）

用「128 槽全白」实测：**真有 LED 的槽 = 86 个**，与官方 `ledKeyMap` 的 87 键表有 5 处差异：

- 官方标「有键」但**无 LED**：**99 / 100 / 102**（Print/Scroll/Pause —— 用户确认这三颗键**没装**，
  该位置是一块小屏幕）
- 官方标「无键」但**有 LED**：**97 / 98**（用户观察：亮的是一个「logo 灯/跑马灯」位置，未定位到具体键）
- 其余 84 个槽与官方表一致；phantom 槽（如 102/127）写颜色**不点亮**，验证 index==槽位

### 3.5 设置项

- 游戏模式 56B：只改 `tftDisplayTime`(payload[7]) 其余原样回写 → 回读一致、其它字段未变 → ✅
- 屏幕时间 10B：`5A 01 5A 1A 0B 01 06 2C 30 00` 回显一致（年/月/日/时/分/秒/星期=0 正确）→ ✅

---

## 4. Phase 2：TFT 屏幕

### 4.1 上传通道（重要修正）

- **`SET_TFT_MATERIAL(0x4D)` 与 `SET_TFT_USER_ANIMATION(0x50)` 的逐包 ACK 都是 `0x41`**，
  不是官方代码里壁纸路径假设的 `0x4D`（官方壁纸路径在 MK87 上必然超时，幸好 UI 不可达）
- 每包 4105 字节（report ID + 4104 = 8B 头 + 4096B 数据），`write_report` 单包耗时约 **65 ms**
  （USB FS 64B/ms 的物理上限）→ 有效吞吐 ≈ **63 KB/s**
- ACK 延迟 ≈ 15 ms（去掉写时间后），逐包等待完全可行

### 4.2 壁纸 vs 动画（结论）

- 推一帧纯红壁纸（0x4D，16 包全 ACK）→ **屏幕无变化**；推 3 帧红/绿/蓝动画（0x50，48 包全 ACK）
  → **屏幕立即播放动画**。原因：**MK87 的屏幕 UI 里没有「壁纸页」**，只有设备端菜单
- 成功恢复官方默认动画：`config.driveall.cn/gif/AK980_PRO/defaultGif.json`（135 帧 240×135，
  delay=10cs），2136 包 / 8.75 MB / 311 秒上传完成，ACK 2099/2136（超时包不影响结果），
  **屏幕恢复为官方默认动画（用户确认）**

### 4.3 屏幕的页面结构（真机实测，静态未知项）

屏幕是**设备端菜单**，用旋钮操作（用户提供照片）：

1. **主页**：`2026/11/01`、电量 %+充电图标、`19:11:03` 时钟、底部状态图标
   （WIN / U1(?) / BT2 / 锁 / A / 1）
2. **设置菜单**：灯光效果 / 灯光颜色 / 灯光亮度 / 灯光速率 / 语言选择
3. **自定义动画页**：播放主机上传的 `SET_TFT_USER_ANIMATION` 内容
4. 音量/旋钮数值 OSD、电量/连接状态

→ **没有系统信息页**（与静态一致：MK87 无 `isShowTftInfo`）；**没有壁纸页**。

### 4.4 内置索引 / 12-24h

- `SET_TFT_BUILT_IN_INDEX(0x51)` 发 0..5：设备每包都回 `55 41`（通用 ACK），但**屏幕无任何反应**
  → MK87 固件不支持 0x51 切页（页面完全由设备端菜单控制），与静态「官方从不发」一致
- `SET_GAME_MODE payload[7]`（12/24h）写 0/1 都成功、回读一致，但**屏幕时钟格式不变**
  （12h 模式下发 19:05，屏幕仍显示 19:05；24h 模式同样）→ fw 1.19 该字段对屏幕无可见作用
  （是否需重启/是否只影响其它页面：未决）

### 4.5 系统信息推送

无系统信息页，`SET_TEMPORARY_COMMAND_DATA` 24B 仍可发送（回显正常），但**无可观察目标**。
→ 该项在 MK87 上判「无页面，不可验证」（⛔）。

---

## 5. Phase 3：改键 / FN / 宏

| 测试 | 内容 | 结果 |
|---|---|---|
| 3.1 phantom 槽 | 槽 120 → `02 00 68 00`(F13) | 写→回读一致，无物理键变化 ✅ |
| 3.2 普通键 | 槽 103 Insert → `02 00 04 00`(A) | 记事本按 Insert 打出 `a` ✅ |
| 3.3 FUNC 动作 | 槽 105 PgUp → `0D 00 00 0D`(FUNC 13 亮度+) | 按 PgUp 背光变亮 ✅ |
| 3.4 FN 层 | FN 层槽 105 → `0D 00 00 0E`(FUNC 14 亮度-) | Fn+PgUp 背光变暗 ✅ |
| 3.7 全量还原 | 用 Phase 0 dump 整表回写 | 逐字节一致 ✅ |

### 3.5 25 个「配置外槽」语义（新结论，推翻静态推断）

静态推断：官方只写 keyList 87 槽、其余写 0，会「清掉」25 个配置外槽。
真机实测（模拟官方写法）：

- 写入 0 到 25 个配置外槽（13/14/15 音量、小键盘、96-98/101…）→ **回读仍是原值，固件拒绝清零**
- 另外验证：这些槽**写非零值可以生效**（槽 13 写 `02 00 04 00` 回读一致；槽 29 写 consumer 音量+ 生效）
- keyList 内的槽写 0 → **回读变成出厂默认**（槽 103 写 0 → `02 00 49 00` = Insert 默认）
- ⇒ **0 = 「恢复默认/保持默认」语义**，配置外槽受保护，静态度量「官方会丢功能」在 fw1.19 上**不成立**

### 3.6 宏写入（✅ 真机全通）

官方 `PZ`(setMacroData) / `NZ`(getMacroData) 已完整还原（格式见 [keymap.md](keymap.md) §16），真机验证：

| 测试 | 结果 |
|---|---|
| 写宏 "abc"（6 个动作：a/b/c 各 press+release，delay=10ms） | 偏移表 400B（8 包，全 last=0）+ 动作区 28B（1 包 last=1）ACK 全通 |
| 回读 `GET_MACRO` | 偏移 `90 01 00 00`(=400)、块头 `0C 00`(=6 动作×2)、6 个动作 **逐字节一致** |
| 绑定与执行 | 槽 103 Insert = `06 00 00 00`(MACRO 0) → 记事本按 Insert **打出 "abc"** |
| mask=1（重复 N 次） | `06 00 01 03` → 按一下 Insert **打出 "aaa"**（重复 3 次） |
| mask=2（再按结束） | `06 00 02 00` → 按一下开始连续刷、再按一下停 **符合预期** |
| 收尾 | 清空宏表（回读无非空项）+ 槽 103 还原 + 灯效还原，全部逐字节一致 |


---

## 6. Phase 4：逐键实时帧流（音乐通道）——H1/H2/H3 全部落定

### 6.1 帧格式（已按官方 `TZ` 逐字节复刻）

- 每帧 87 键 × 4B `[keyValue, r, g, b]` = 348 B；64B 报文下每包 56B → **7 包/帧**
- 头：`AA 32 len addrLo addrHi i last 0`，数据从 offset 8；`i` = 官方第二参数（MK87 实测 0 可用）
- **ACK `55 32 …` 原样回显所发数据**（不是设备状态）；延迟 ≈ **0.5–3 ms**

### 6.2 H1 / H2 / H3 结论

| 假设 | 结果 |
|---|---|
| H1「只要发帧就接管显示」 | ❌ 不成立：灯效 mode=1 时发帧无显示 |
| H2「需先切某个模式」 | ✅ **成立：`SET_LED_EFFECT` 的 mode ∈ {20, 21, 128}（自定义族）后帧流立即显示** |
| H3「停止后回落」 | ✅ 成立：停止发帧后 **≈5 秒**回落到该模式的自定义表（120 槽采样测得） |

- 帧流写入的是**同一块逐键 LED 缓冲**：`GET_ALL_LIGHTS_RGB` 能实时读回帧颜色（可程序化验证）
- 连续帧实测：**20.0 fps 稳定**（150 帧 / 7.50s），平均帧耗时 **15.5 ms**（7 包 ACK 全等），
  最大 20 ms，1050/1050 包 ACK → 20 fps 有充足余量（理论上限 ~60 fps）

---

## 7. Phase 5：音乐律动（完全自研，不依赖 Music.exe）

链路：**WAV → 官方 K7/Nse 振幅算法 → 官方渲染器 → 0x32 帧流 → 键盘**，全部用自研代码跑通：

1. `scripts/make_test_wav.py` 生成 10s 测试音频（前 3s 安静、后 7s 底鼓/军鼓/踩镲）
2. `scripts/gen_music_frames.js` 用 `music_ref.js` 的 `MusicEngine`（官方渲染器移植）按 20fps
   把 WAV 转成 160 帧（振幅用官方 `timeDomainAmplitude` + 自适应归一化 + 静音门限 5）
3. `probe/phase5_music.py` 先切 mode=128，再按 20fps 推帧

真机结果（用户目视 + 数据双确认）：

- **mode 13「Dance to the Beat」**：中心扩散彩色光圈随节拍脉动，**很跟手**；16s / 2240 包 ACK 全通
- **mode 14「Dust Glow Spiral」**、**mode 17「Firefly Trail」**：均正常显示且互相不同
- 停止后约 5 秒回落原灯效（与 H3 一致）

⇒ **「不用官方工具做音乐律动」在 MK87 上已完整验证可行**；剩余工作只是音频采集（WASAPI/浏览器
`getDisplayMedia`）与渲染器补齐，协议层无未决项。

---

## 8. Phase 6：2.4G 无线

### 8.1 身份（与静态完全一致）

`VID 0C45 / PID FEFE`（=3141 / 65278），product string **"2.4G Dongle"**；
`GET_DEVICE_INFO` 回 `manufacturer=1, product=18, workMode=2, battery=73%, charge=1, fw=1.19`
→ 正是静态还原的 `3141-65278-2.4G Dongle-1-18`。

### 8.2 协议接口

| 接口 | usagePage | 报文 | 结果 |
|---|---|---|---|
| MI_03 | **0xFF60** | 33B（32B payload） | ✅ 全部命令可用（GET/SET/读矩阵/读灯） |
| MI_04 | 0xFF59 | 65B（64B payload） | ❌ 无任何响应；且**不在官方 WebHID 过滤器表**里 |

- 2.4G 下 `GET_KEY`/`GET_FN_KEY` **与 USB 时代 dump 逐字节一致** → 配置存在键盘端，双通道共享
- 2.4G 灯效写入生效（写红→显示红），`GET_ALL_LIGHTS_RGB` 正常（85 键）
- 一个小坑：2.4G 下 `SET_LED_EFFECT` 写 `colorMode=0+RGB` 时，`GET_LED_EFFECT` 回读的
  color/colorMode 可能与写入不同（显示是对的）→ 2.4G 回读不可作为写成功判据，需回读 RGB/或改判据

### 8.3 2.4G 逐键帧流（未完全落定）

按官方 `TZ` 的三种分支各推 5–8 秒，用**不同颜色/白色脉冲**让人眼归属：

- `0x32`（4B/键，0xFF60）、`0x35`（RGB565，4B 头，0xFF60）、`0x3C`（RGB565，56B/包，0xFF59）
- 观察结果：**出现过一次很短的全白脉冲，随后「随机色」、最后出现「竖条纹橙色闪烁」**
  → 说明 2.4G 通道**确实收到了某种帧数据**，但**数据映射/格式不对**（不是完全无效果）
- 静态证据：官方 2.4G 音乐分支要求 `reportCount===64 && lightingVersion===1`，
  MK87 的 `lightingVersion=0` 且唯一可用接口是 32B → 官方逻辑在 MK87 上**本来就走不通**
  （v1 音乐由 Music.exe 用私有协议驱动）
- **结论（2026-11-01 更新）：官方明确表示 2.4G 模式不支持音乐律动** —— 与真机现象一致：
  帧数据虽被通道接收，但固件没有合法的 2.4G 帧映射（表现为短暂白脉冲/随机色/竖条纹）。
  ⇒ 该项由「⬜ 待解」改为 **⛔ 设备不支持**；自研音乐律动工具**仅走 USB 模式**（USB 下已完整验证）。

### 8.4 2.4G dongle 的 Windows 兼容问题（重要）

- 首次插入报 **Code 10（CM_PROB_FAILED_START），ProblemStatus=0xC000009A（STATUS_INSUFFICIENT_RESOURCES）**
- 与键盘 USB 复合设备同时插着时也会触发同一错误 → **拔掉 dongle 后键盘 USB 立刻恢复**
- 这不是键盘固件问题，是 Windows 复合设备资源分配问题（8 个 HID 顶层集合 × 2 设备）
- 「一劳永逸」建议：**两个设备插在不同 USB 控制器/根集线器上**（如一个接 USB3 口、一个接 USB2 口），
  或在只用一个时拔掉另一个；自研驱动侧无法修复，只能做**检测+提示**（枚举失败时提示用户拔掉另一个设备）

---

### 8.5 2.4G 通知帧（休眠 / 断连 / 唤醒）——真机捕获

场景：dongle 单独连接（数据线拔掉），把 `sleepTime` 临时改成 **1 分钟**，同时监听 dongle 全部 6 个可读 HID 接口：

| 时间 | 接口 | 帧 | 判定 |
|---|---|---|---|
| t≈59.9 s（闲置 1 分钟） | **MI_03 / 0xFF60**（33B 报告） | `55 FC 04 30 00 00 01 00 FF FF…` | **断连通知（0xFC/type=4）** |
| t≈213.7 s（按键唤醒） | **MI_02/COL05 / usagePage 0xFFFF**（in=4，**report ID=5**） | `A6 FF 01` | **唤醒帧**（不是 0x55 头） |
| t≈273.8 s（再次闲置 1 分钟） | MI_03 / 0xFF60 | `55 FC 04 …` | 第二次断连，**可复现** |

结论：

- **`sleepTime` 单位 = 分钟**（官方 UI 选项 1/10/20/30 min，0=关闭；回读 payload[3]）。
- MK87 上「闲置后」dongle 发的是 **`0xFC/type=4` 断连**，**没有捕获到 `0xFC/type=6`（休眠）** ——
  与官方 UI 里 type 6 才显示"睡眠遮罩"的预期不同（可能 type 6 属其它机型/其它条件）。
- **唤醒帧 `A6 FF 01` 走 MI_02/COL05（usagePage 0xFFFF, report ID=5）**，而这个接口
  **不在官方 WebHID 过滤器表** `[0xFF68,0xFF80,0xFF60,0xFF00,0xFF01,0xFF5B]` 里
  → 官方驱动在 MK87 上**收不到唤醒帧**；自研工具要监听它必须自己打开 0xFFFF 接口。
- 官方"唤醒后取消睡眠遮罩"的逻辑在 MK87 上实际不可用（收不到 type 6 也收不到 A6）。

### 8.6 12/24 小时制（重启验证）

- 写 `tftDisplayTime=1` → 回读 1 → **断电重启** → 回读仍为 1（设置持久化 ✅）→ 重新下发 19:05
- 屏幕时钟**仍显示 19:05**（不是 7:05）
- ⇒ 结论：**该字段对 MK87 屏幕时钟格式无可见作用**（重启也不能生效），判 ⛔ 不支持/无效果；
  最终已改回 0（24h）并同步真实时间。

## 9. Phase 7：按键事件捕获

- 直接读 HID 键盘接口 `HID\VID_0C45&PID_8047&MI_00`（`\kbd` 集合）→ **CreateFile 失败 err=5
  (ACCESS_DENIED)**（Windows 对键盘类 HID 的读保护），MI_01 COL03 同样被拒
- **Windows RawInput 方案可用**：`RegisterRawInputDevices`(usagePage 1/usage 6 + 0x0C/0x01)
  + 隐藏窗口 `WM_INPUT`，实测捕获到
  `vkey=0x31 make=0x02`(数字 1)、`vkey=0x0D make=0x1C`(Enter)、`vkey=0x42 make=0x30`(B)
  且 **`GetRawInputDeviceInfo` 能拿到 `VID_0C45&PID_8047&MI_00` 设备名**（可做设备归属过滤）
- 与静态结论一致：厂商协议 0x60/0x68 都不提供按键事件，替代方案 = RawInput（或官方那种 DOM 事件）
- ⚠️ RawInput 只给 VKey + MakeCode，**不给 HID usage**；要 usage 级映射需用 vendor 接口或
  自行维护 VKey→usage 表（`key-events.md §4.3` 已有 104 键对照表）

---

## 10. 收尾：状态恢复验证（全部通过）

用 `docs/device_dump_pre_test.json` 逐项比对（USB 模式下）：

| 项 | 结果 |
|---|---|
| `GET_LED_EFFECT`（mode 11 白/亮度6/速度3） | ✅ 一致 |
| `GET_GAME_MODE` | ✅ 一致 |
| `GET_KEY` 512B | ✅ 一致 |
| `GET_FN_KEY` 512B | ✅ 一致 |
| `GET_CUSTOM_LED_DATA` 512B | ✅ 一致 |
| TFT 内容 | 已恢复官方默认动画（原内容不可读、无法备份，用户已确认接受） |

> 注：屏幕时间在测试中被改成过 19:05 等值，收尾已重新同步为当前时间。

---

## 11. 实测性能数据（供工具实现参考）

| 指标 | 数值 |
|---|---|
| 主协议单包写 | ≈ 1–2 ms（64B） |
| 写命令 ACK 回包 | ≈ 0.5–3 ms |
| `SET_KEY` 512B（10 包 + ACK） | ≈ 30 ms |
| `GET_ALL_LIGHTS_RGB` | ≈ 29 ms |
| 音乐帧（7 包/帧，逐包 ACK） | **15.5 ms/帧**（20 fps 稳，余量到 ~60 fps） |
| TFT 单包（4105B） | ≈ 65 ms（USB FS 带宽上限 64B/ms） |
| TFT 吞吐 | ≈ 63 KB/s；135 帧默认动画 8.75MB ≈ 311 s |
| 帧流停止后回落 | ≈ 5 s |

---

## 12. 对静态文档的修正（8 条，全部有真机证据）

1. **TFT ACK**：`0x4D`（壁纸）的逐包 ACK 也是 **`0x41`**，不是 0x4D（[tft-page.md](tft-page.md) §4.2 需改）
2. **TFT 壁纸页不存在**：MK87 屏幕上没有壁纸页，0x4D 写入「成功但不可见」
3. **屏幕页面结构**：主页(时钟/电量/状态) + 设置菜单(灯光效果/颜色/亮度/速率/语言) + 自定义动画页；
   **无系统信息页、无壁纸页**（静态「内置页」猜测 → 真机 = 设备端菜单）
4. **0x51 内置索引**：设备回 ACK 但**不切页** → MK87 不支持
5. **12/24h（`tftDisplayTime`）**：字段写入生效、回读一致，但**屏幕时钟格式无变化**（fw1.19 无可见作用，未决）
6. **亮度字段**：1..6 identity，**brightness=1 = 全灭**；越界值未定义（0→255、7→11…）
7. **25 个配置外槽不会因写 0 丢失**（固件保护），**0 = 恢复默认**（keyList 槽会变出厂默认）
8. **逐键帧流激活条件**：必须先 `SET_LED_EFFECT` 切到 **mode 20/21/128**，且停止后 ~5s 回落（H2/H3 落定）

### 其它新事实（非修正，补充）

- 模式 **20/21/128 共用同一张自定义表**
- 物理 LED 槽 86 个：99/100/102 无灯（键位被屏幕替代），97/98 有灯（logo 灯位置）
- Fn 键 LED = **充电指示灯**（充电时强制红，不可被 LED 数据覆盖）
- 2.4G dongle = **0xFF60（32B）** 协议口，0xFF59（64B）无响应且不在官方过滤器表
- 2.4G 与 USB **共享同一份按键/FN 配置**（逐字节一致）
- 键盘 HID `\kbd` 接口用户态读取被拒绝（err=5），**RawInput 可用且能拿到设备路径**
- **宏表二进制格式已还原并真机验证**：400B = 100×u32 LE 绝对偏移（数据区从 400 开始）；
  宏块 = `[0..1]=动作数×2 (u16 LE) [2..3]=0` + 每动作 4B `[delay u16LE][keyCode(HID usage)][flags]`，
  `flags = ((actionType&7)<<4) | (isPress?0x80:0)`（键盘动作 actionType=3 → 按下 0xB0 / 抬起 0x30）；
  写入分两包：偏移表 `contentSize=400, addr=0, 全包 last=0`，动作区 `contentSize=len, addr=400, 末包 last=1`
- **宏播放方式 mask**（param2）：0=常规单次、1=重复 param3 次（实测 3 → 3 遍）、2=再按结束（实测通过）
- **槽 97/98 有 LED 驱动通道但无可见光**：自定义模式下写 97=红/98=绿，`GET_ALL_LIGHTS_RGB` 回读确认
  缓冲里就是红/绿，但人眼看不到任何绿色灯（红色只有 Fn 充电指示灯）→ 判定为未装配/被遮挡的隐藏通道
- **2.4G 通知走两条不同通道**：断连/复位/休眠（`55 FC 04/05/06`）在 **0xFF60** 协议口上；
  **唤醒帧 `A6 FF 01` 在 MI_02/COL05 的 usagePage=0xFFFF 接口（report ID=5）**，该接口不在官方过滤器表
- **`sleepTime` 单位 = 分钟**（官方 UI 1/10/20/30 min，0=关闭），实测 1 分钟即断连
- **`tftDisplayTime`（12/24h）对 MK87 屏幕无可见作用**，断电重启后仍无变化

---

## 13. 仍未解决 / 后续工作

| # | 项 | 说明 | 建议 |
|---|---|---|---|
| 1 | ~~宏写入 `SET_MACRO`~~ | **已关闭：格式已还原 + 真机全通（写/读回逐字节一致、mask 0/1/2 全部验证）** | — |
| 2 | ~~2.4G 逐键帧流格式~~ | **已关闭：官方确认 2.4G 不支持音乐律动**（真机异常显示与此一致） | 不做；音乐律动工具强制 USB |
| 3 | ~~2.4G 唤醒/休眠通知~~ | **已关闭：实测捕获 `55 FC 04`(0xFF60) 断连 + `A6 FF 01`(0xFFFF/reportID=5) 唤醒；未见 0xFC/6** | 工具监听 0xFFFF 接口即可 |
| 4 | ~~12/24h 是否需重启生效~~ | **已关闭：断电重启后仍无可见变化 → 该字段对 MK87 屏幕无作用** | 不做 |
| 5 | ~~97/98 这两颗 LED 的物理位置~~ | **已关闭：有 LED 驱动通道但无可见光**（写红/绿回读正确但人眼不可见） | 不做 |
| 6 | 亮度=1 全灭是否符合官方 UI 预期 | 真机行为如此（PWM=0），可能是固件特性 | 记录，工具侧把最小亮度钳到 2 |
| 7 | 2.4G dongle + USB 同插的 Windows 资源冲突 | 0xC000009A | 插不同控制器 / 工具侧检测提示 |
| 8 | 系统信息页 | MK87 无此页面 | 不做 |

---

## 14. 本轮新增/更新的产物

- 脚本：`probe/phase0_selftest.py`、`phase1_lighting.py`、`phase1_diag.py`、`phase1_diag2.py`、
  `phase1_diag3.py`、`phase2_tft.py`、`phase2_builtin.py`、`phase3_keys.py`、`phase3_official.py`、
  `phase4_frames.py`、`phase4_diag.py`、`phase4_timeout.py`、`phase5_music.py`、
  `phase6_wireless.py`、`phase7_keyevents.py`、`phase7_rawinput.py`、`phase3_macro.py`、`phase3_macro_mask.py`、
  `restore_tft_default.py`、
  `monitor_notify.py`、`bundle_grep.py`、`_p6_*.py`；`scripts/make_test_wav.py`、`scripts/gen_music_frames.js`
- 数据：`docs/device_dump_pre_test.json`、`docs/phase0_selftest.json`、`phase1_lighting.json`、
  `phase1_diag.json`/`2`/`3`、`phase2_tft.json`、`phase3_keys.json`、`phase3_official.json`、
  `phase4_frames.json`、`phase4_diag.json`、`phase4_timeout.json`、`phase5_music.json`、
  `phase6_wireless.json`、`phase6_display.json`、`phase7_keyevents.json`、`phase7_rawinput.json`、
  `phase3_macro.json`、
  `restore_tft_default.json`、`notify_capture.json`、`_p6_variants.json`、`_default_gif.json`、
  `_test_audio.wav`、`_music_frames_13/14/17.json`
- 参考实现：`scripts/music_ref.js`（31 项自检）已在真机链路上跑通

---

## 15. v0.1.3 音乐律动复核（2026-11-03）

> 设备：MK87 USB（VID `0C45` / PID `8047`），固件 **v1.19**；日期 **2026-11-03**。
> 方法：官方 v1 模式 4 用官方 `MusicPlug.exe` 本地 HTTP 采样；v0.1.3 帧流用本工具 **HTTP API** 驱动真机。
> §11 的 2026-11-01 基线（20fps / 15.5ms/帧）保留为 **v0.1.2 及以前**的历史数据，与本轮不冲突。

### 15.1 方法

- **官方 v1 模式 4 真值**：官方 `MusicPlug.exe` 的 `127.0.0.1:9191` HTTP 接口，
  音频为 48kHz 正弦单音 **100 / 440 / 2k / 4k / 8k Hz**、**200→6400Hz 阶梯扫频**、
  振幅扫描（amp=30 / amp=100）与静音。**只走 HTTP，不发本工具 HID 帧**，避免自研帧流污染采样。
  脚本：`probe/capture_official_v1_mode4.py`、`probe/analyze_official_v1_mode4.py`；
  数据：`capture/official_v1_mode4_*.jsonl`。
- **v0.1.3 帧流**：通过 `/api/music/start`、`/api/music/update`、`/api/music/stop` 驱动真机，
  USB 直连；分别跑 **66 / 60 / 20fps**，再逐个切换 **21 个显示模式**与 **10 种 LED 颜色**；
  停止后读回 `GET_LED_EFFECT` 校验恢复值。

### 15.2 结果

| 项 | 结果 |
|---|---|
| 模式 4 几何 | 17 列频谱柱，**底部对齐 1200/1200 帧** |
| 模式 4 频率 | 100Hz 只点最左 3 列、8kHz 只点最右 2 列；200→6400Hz 扫频柱峰逐级右移 |
| 模式 4 颜色 | 径向色相原点 `(2,8)`，整块调色板 **~275°/s** 旋转（与 amplitude 无关） |
| 模式 4 柱高 | amp=30 单音峰值约 **4/6 行**；amp=100 顶到 **6/6 行** |
| 66fps × 100s | **65.78–65.89fps**；send 8.85ms/帧；lateFrames ≤6；**0 错误** |
| 60fps | **60.06fps** |
| 20fps | **19.97fps**（逐包 ACK 路径） |
| 21 模式 + 10 颜色逐个切换 | **0 错误** |
| 停止恢复 | mode=11、brightness=6、speed=3；raw `0bffffffff000000010603000000aa55` |
| 自检 | **152 个单元测试全绿**；无头 Chrome UI **17 项 PASS**（21 模式 / 3 下拉 / 10 颜色 / 3 帧率档、热切换、英文无中文残留） |

### 15.3 结论

- 官方 v1 模式 4 的「合成正弦包络」旧结论被推翻：真值是 **17 列频谱柱 + 旋转径向色相**，
  v0.1.3 已按采样重写（实现与边界见 [music-rhythm.md](music-rhythm.md) §12.1）。
- 官方 v1 的 **~66.3fps**（530.5 包/s ÷ 8 包/帧）在本工具 7 包/帧、burst + 异步 ACK 架构下可稳定复现
  （66fps 连续 100s 65.78–65.89fps，0 错误）。
- 21 模式、10 颜色热切换与停止恢复均通过；灯效卡死根因（旧版写 LED mode 128）已消除，
  v0.1.3 帧流入口**不再写 128**，帧模式固定 20/21 并回读校验。
