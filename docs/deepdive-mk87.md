# MK87 深挖记录（真机 + bundle 交叉验证）

设备：AJAZZ KEYBOARD（VID 0x0C45 / PID 0x8047），固件 v1.19，240×135 TFT，98 键固件矩阵。
所有结论均来自本机真实 HID 通信（`probe/ajazz.py`）与官方网页驱动 bundle 静态分析。

---

## 1. 按键矩阵（GET_KEY / GET_FN_KEY，各 512 字节）

- 512 字节 = 128 个槽位 × 4 字节：`[pageType, param1, param2, param3]`
- 槽位下标 = 官方配置里的 `value`（键位编号），实测吻合（slot 16=`、99=PrintScreen、100=ScrollLock、102=Pause）

### pageType 实测语义

| pageType | 含义 | 实测证据 |
|---|---|---|
| **2** | 普通键盘按键，`param2` = **HID 键盘 usage** | slot 0 `02 00 29 00` = Esc(0x29)、slot 1 = F1(0x3A)…slot 83 = Space(0x2C)、slot 64 = LShift(0xE1) 全部吻合 |
| **13 (0x0D)** | **FN 层动作**，`param3` = 动作 ID | FN 层实测 slot 16 (` ~)=`0d 00 00 63`、slot 33(Q)=`0d 00 00 02`…，官方默认 FN 层 |
| 0 | 空槽位 / 未定义 | 未使用的槽位全 0 |

### 真机矩阵特征

- 主层非零槽位 **112/128**；官方 MK87 配置只有 87 个按键（`docs/device_config_32839.json`），
  多出的 25 个槽位是固件公共矩阵（小键盘 NumLock/KP*、KP1-9、NumEnter、NUBS 等），
  说明该固件与 98 键带屏机型（如 AK980 PRO，tftConfig 里就写着 `AK980_PRO`）共用。
- **FN 层 = 工厂默认**（与 `GET_DEFAULT_FN_KEY_MATRIX` 逐字节一致，差异 0 处）。
- `GET_DEFAULT_KEY_MATRIX`(31) 在 MK87 上返回全 0（该命令不支持/不适用）。
- 完整解码表：[keymap_device_report.txt](keymap_device_report.txt)、[keymap_device.json](keymap_device.json)

### 改键写入通道（已验证）

1. `SET_KEY`(34)：payload = 512 字节整表（按 `value*4` 定位槽位），分 10 包发送（每包 56 字节内容）；
2. 设备对每包回一个 **ACK 回显帧**（cmd=0x22，`lenByte`=本块内容长，`addr`=块起点）；
3. 测试：向**配置里不存在的槽位 120** 写入 `02 00 04 00`（HID-A）→ 回读一致 → 再写回原全 0 → 整表完全还原 ✓
   （不动任何实体键，证明"改键 → 断电保存"通道可用）
4. FN 层同理：`SET_FN_KEY`(38)。

---

## 2. 写命令的 ACK 规律（真机抓到的帧）

设备对写命令的响应是"**回显自己刚收到的帧**"：

| 命令 | ACK cmd | lenByte | 说明 |
|---|---|---|---|
| SET_LED_EFFECT(35) | 0x23 | 0x10 | 回显 16 字节灯效 payload |
| SET_KEY(34) | 0x22 | 0x38(56) | 每包回显本块 56 字节，`addr`=块偏移（0,56,112…） |
| SET_TEMPORARY_COMMAND_DATA(52) | 0x34 | 0x18 | 回显 24 字节 payload（屏幕时间命令实测被接收） |

> 实测 `SET_TEMPORARY_COMMAND_DATA` 回显：`5a 01 5a 1a 0b 01 05 2e 23 ...`（我们发的就是当前时间 26-11-01 05:46:35）
> —— 说明"TFT 显示时间"的内部时钟写入通道正常。

---

## 3. 设备状态实读（`python ajazz.py dump` 采集）

| 项 | 实测 |
|---|---|
| 电量/充电 | 50% → 52%（充电中，`chargeStatus=1`） |
| 当前灯效 | mode=1，白色 255/255/255，colorMode=1，亮度 5，速度 3（亮度/速度有效范围 1–6） |
| `GET_ALL_LIGHTS_RGB` | 128 组 `[ledId,R,G,B]`，当前是彩虹流动效果，例如 led0=(0x91,0x00,0x2C)、led1=(0xBE,0,0)、led2=(0x91,0x2C,0)… |
| `GET_CUSTOM_LED_DATA` | 128×[id,0,0,0] 全 0 → 未自定义过单键颜色 |
| `GET_MACRO` | 400 字节宏表全 0 → 没有宏；宏空间 3072 字节（设备信息） |
| `GET_GAME_MODE` | sleepMode=5min、keyDelay=2、其余字段 0xFF = 不支持（稳定性/自动校准/单键唤醒/回报率等） |
| DotMatrix / LightBox / SideLight | 全 0（MK87 无这些硬件，与官方配置 flag 一致） |
| `OTA_GET_DEVICE_SN`(132) / `OTA_GET_DEVICE_SYSTEM_INFO`(128) | 全 0（frameVersion=0，该固件不接受这两个 OTA 查询） |
| 空闲 5 秒主动上报 | 0 条（设备通知只在 2.4G 断开/休眠/重置等事件时发 0xFC 帧） |

---

## 4. 设置项语义（从官方 settings 页代码还原）

- **TFT 时间格式（tftDisplayTime）= 0/1**：`SET_GAME_MODE` payload 的 `[7]`；官方 i18n 已确认：**0 = 24 小时制，1 = 12 小时制**
  （`time_1`=24 Hour / `time_2`=12 Hour，随 SET_GAME_MODE 一起保存；**不是"是否显示时间"**，当前设备值 0）
- 休眠时间 `[3]`（分钟，1–30）；按键延迟 `[4]`（3/4/5）；回报率 `[5]`（1000→3、2000→4、4000→5、8000→6）
- 灯效亮度/速度范围 1–6（`lightingConfig.minBrightness/maxBrightness/minSpeed/maxSpeed`）
- 音乐律动：`musicConfig:{version:1, maxColOffset:0, keyOffset:[...]}`（F1/Z/↑/Spacebar/R-Alt 的列偏移表）；
  **MK87 是 v1**——官方 UI 走本地 Music.exe（`127.0.0.1:9191`）算灯并直接驱动设备，浏览器不发帧，
  详见 [music-rhythm.md](music-rhythm.md)
- MK87 不支持：单键唤醒、稳定性模式、自动校准、回报率设置（`settingsConfig` 里全是 false）

---

## 5. 结论与待验证

### 已打通的写通道（全部用「原样回写 + 回读比对」验证，不改可见状态）

| 通道 | 命令 | 验证结果 |
|---|---|---|
| 改键（整表） | SET_KEY(0x22) | phantom 槽位写入 → 回读一致 → 还原成功 ✓ |
| 游戏模式/设置 | SET_GAME_MODE(0x21) | 56 字节原样回写，回读完全一致 ✓ |
| 自定义单键灯 | SET_CUSTOM_LED_DATA(0x24) | 512 字节原样回写，回读一致 ✓ |
| 灯效 | SET_LED_EFFECT(0x23) | 原样回写 + 回读一致 ✓ |
| 屏幕时间 | SET_TEMPORARY_COMMAND_DATA(0x34) | 设备 ACK 回显时间 payload ✓ |
| TFT 壁纸/动画 | 0x4D / 0x50 | 代码已实现，**待屏幕写真验证** |

> 新增工具命令：`ajazz.py key get <slot>` / `key usage <slot> <usage>` / `key reset <slot>` /
> `key set <slot> AA BB CC DD`、`ajazz.py led [n]`、`ajazz.py tft-time <0|1>`、`ajazz.py dump`。

- ✅ 按键矩阵读取、FN 层读取、改键写入（含还原）全部打通
- ✅ 灯效读取/写入、自定义单键灯写入、游戏模式写入、屏幕时间写入、设备状态全量读取打通
- ⬜ **TFT 壁纸/GIF 上传**：数据编码已按官方实现还原（RGB565 + 字节序 + 4096/包），但还没往屏幕写真
  （会覆盖当前壁纸；等确认屏幕"内置页/时钟页"切换逻辑后一起验证，见 `tft-page.md`）
- ⬜ 屏幕内置动画索引（`SET_TFT_BUILT_IN_INDEX`）取值表

---

## 6. 4 字节键位编码全表（从 bundle 还原，`pageTypes`）

| pageType | 名称 | 含义 / 布局 |
|---|---|---|
| 0 | DEFAULT | 不修改，4 字节全 0 |
| 1 | MOUSE | `byte1`=1 按键 / 3 滚轮，`byte2`=按键值 |
| 2 | KEYBOARD | `byte2`=HID usage（本机主层全部用这个） |
| 3 | CONSUMER_KEY | `byte1..2`=16 位小端 Consumer usage（本机 slot13/14 = 0xE9/0xEA = 音量±） |
| 4/5 | SYSTEM_KEY / EXTRA_FUNCTION | 保留，驱动未实现 |
| 6 | MACRO | `byte1`=宏 id，`byte2`=掩码/模式，`byte3`=掩码参数 |
| 7 | CB | 组合键：`byte1/2`=两个修饰键 HID，`byte3`=主键 HID |
| 8/9/11/12 | DKS / MT / SOCD / RS | 磁轴高级键（MK87 不适用） |
| 10 | TGL | Toggle 切换键 |
| **13** | **FUNC** | **固件功能 id（24 位，`byte1..3` 大端）**；本机 FN 层全部用这个 |
| 14 | END | 双键 |
| 15 | MPT | 三键同发 |
| 128..255 | FUNC_V2 | 新一代功能动作（slotA/slotB 双 12/16 位槽） |

- 官方动作表 292 条（FUNC）+ 409 条（FUNC_V2）已导出到 [keymap-tables.json](keymap-tables.json)
- 编码工具：`scripts/keymap.js`（`node scripts/keymap.js` 可跑编解码自检）
- **MACRO 页 mask 语义（i18n 已确认）**：`param2` = 0 Routine（单次）/ 2 "再按一次结束"（按住循环，再按停止）/ 1 "Repeat Playback"（按 `param3` 次重复）；
  `param1` = 宏 id（0–99）。例：`06 00 00 00` = 宏 M1 单次。

## 7. FN 层实测解码（真机读回 → 官方 FUNC 表对照）

> 本机 FN 层是**出厂默认**（与 `GET_DEFAULT_FN_KEY_MATRIX` 完全一致）。多数键为"透传主层"，
> 真正有 FN 动作的槽位如下（完整表见 [fn-layer-decode.json](fn-layer-decode.json)）：

| 组合 | 动作（FUNC id） |
|---|---|
| Fn+` | 自定义灯光录制 (99) |
| Fn+1 / 2 / 3 | 自定义灯光1/2/3 (71/72/98) |
| Fn+Q / W / E / R | 蓝牙通道1/2/3 (2/3/4)、无线回连 (5) |
| Fn+- / = | 灯光速度-/+ (16/15) |
| Fn+方向键 ← ↓ ↑ → | 切换灯效方向 (78) / 亮度- (14) / 亮度+ (13) / 颜色切换 (12) |
| Fn+\ | 灯光效果切换 (11) |
| Fn+' | 侧灯颜色切换 (24) |
| Fn+Enter | 侧灯效果切换 (23) |
| Fn+X | 关闭灯光 (17) |
| Fn+C / V | 屏幕语言→汉语/英语 (84/85) |
| Fn+Win | 锁定 Win (22) |
| Fn+Backspace | 查询电量 (7) |
| Fn+Insert / Home / Del / End | 关闭屏幕 (39) / GIF模式 (63) / LOGO LED 开关 (89) / 屏幕下方按键灯 (138) |
| **Fn+Space** | **恢复出厂设置 (1)** ⚠️ 固件出厂默认，慎按 |

- slot 13/14/15 是官方 87 键配置里没有的槽位：固件里分别是**音量+/音量-/旋钮模式切换**（说明该固件与带旋钮的 98 键机型共用矩阵）。
- 结论：改键不仅能映射普通 HID 键，还能直接绑定 `pageType=13 + FUNC id` 的固件功能（如灯效切换、蓝牙通道、屏幕开关，
  甚至 `屏幕左切/右切/确认` 35/36/37、`切换成APP键`、`打开驱动` 等）。

## 8. TFT 屏幕上传（据 bundle 精确还原，尚未写真）

- **MK87 的网页驱动走的是"动画"通道**（`setTftUserAnimation`），不是壁纸通道：
  `tftConfig` 里没有 `materialIds`，所以网页上"上传壁纸"按钮根本不显示；保存按钮统一发动画。
- 所以给 MK87 推图 = 按动画发 1 帧：`SET_TFT_USER_ANIMATION(0x50)`，MI_03 通道，报文 4104 字节（头 8 + 数据 4096）。
- 数据 = **256 字节延时表 + N 帧 RGB565**；
  - 延时表：`[0]=帧数n`，`[1..n-1]=min(厘秒×5,255)`，`[n]=0`，其余填 255
  - 固件时间单位 = **2ms**（厘秒×5 = 毫秒/2，即 100ms → 50）
  - 单帧 240×135×2 = 64800 字节；RGB565，`tftColorByteOrder=0` → 先低字节后高字节
  - 最多 140 帧（`tftMaxFrames`）
- 头部：`[0]=0xAA [1]=0x50 [2..3]=序号 [4..5]=总包数 [6]=0x50 [7]=0x06`，数据从第 8 字节开始
- **ACK 命令字 = 0x41**（官方 `responseCmd` 显式指定 `SET_LED_USER_ANIMATION`；本机探测也确实收到过 `55 41 ...` 帧）
- `SET_TFT_MATERIAL`(0x4D) 的 ACK 是 0x4D；`SET_TFT_BUILT_IN_INDEX`(0x51) 的 ACK 是 0x51
- `builtInCount` 在 MK87 的配置里未定义 → 网页端从不发 0x51，**内置页/时钟页是设备端自己切换的**
  （另有 Fn+Home=GIF模式、Fn+Insert=关闭屏幕、Fn+End=屏幕下方按键灯 等固件功能可切）
- 系统信息（CPU/GPU/温度/天气）推送条件：`tftConfig.isShowTftInfo===true` + 本机助手 `127.0.0.1:9191`
  （MK87 未开启该配置，官方网页不会推；但协议层 `SET_TEMPORARY_COMMAND_DATA` 是通的，我们可自行推）
- 天气来源：OpenWeatherMap（appid 硬编码在 bundle 里）；IP 定位链 ipapi.is/ipwhois/geojs/ipapi.co


