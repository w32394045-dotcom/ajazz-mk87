# AJAZZ MK87 HID 协议规格（driver 实现版）

设备：AJAZZ KEYBOARD，USB `VID 0x0C45 / PID 0x8047`；2.4G dongle `VID 0x0C45 / PID 0xFEFE`（product string `2.4G Dongle`）。实测固件 **1.19**，240×135 TFT，`tftMaxFrames=140`、`ledMaxFrames=0`、`maxProfile=0`、`frameVersion=0`。
标记：✅ 真机实测 ｜ 🧪 官方 bundle 代码逐字节还原 ｜ ⬜ 未验证 ｜ ⛔ MK87 不支持/不适用。所有偏移默认指**去掉 report ID 后的 payload**；请求头偏移 0 从 `AA` 算起。
证据文件：`docs/protocol.md`、`docs/deepdive-mk87.md`、`docs/TEST-REPORT.md`、`docs/FEATURES.md`、`docs/keymap.md`、`docs/lighting.md`、`docs/tft-page.md`、`docs/music-rhythm.md`、`docs/key-events.md`、`probe/ajazz.py`、`probe/phase*.py`、`docs/*.json`。

## 1. 传输层

### 1.1 USB 键盘接口（复合设备，8 个 HID 顶层集合；`protocol.md:14`）

| 接口 | usagePage/usage | IN | OUT | 用途 | 证据 |
|---|---|---|---|---|---|
| MI_02 | 0xFF68 / 0x61 | 65 | 65 | **主协议**：设备信息/灯效/按键/宏/设置/音乐帧流 | `protocol.md:18` |
| MI_03 | 0xFF67 / 0x61 | 65 | **4105** | **TFT 上传**：壁纸/动画/内置索引；ACK 走本接口的 65B 输入报告 | `protocol.md:19`、`phase2_tft.json` |
| MI_01 COL05 | 0xFFFF / 0x01 | 4 | 0 | 厂商小接口，只读；2.4G 唤醒帧走同 usagePage 的接口（USB 侧用途未明） | `protocol.md:20` |
| MI_00 | 标准键盘 collection（RawInput 来源） | 未记录 | 未记录 | 系统键盘；用户态 `CreateFile` 读被拒 err=5，不能用于厂商协议 | `TEST-REPORT.md:292` |

其余为 MI_00/MI_01 下的键鼠/consumer collection；厂商协议只需 MI_02 / MI_03 / MI_01 COL05 三条。不要按 MI 号硬编码，按 `usagePage` 找。

### 1.2 2.4G dongle 接口（`TEST-REPORT.md:229-232`、`phase6_sleep_wake.py`）

| 接口 | usagePage | IN | OUT | 用途 | 结果 |
|---|---|---|---|---|---|
| MI_03 | **0xFF60** | 33 | 33 | **唯一可用协议口**：GET/SET/矩阵/灯效全部可通 | ✅ |
| MI_04 | 0xFF59 | 65 | 65 | 64B 协议口 | ❌ 对 GET 无任何响应，且不在官方 WebHID 过滤器表 |
| MI_02/COL05 | 0xFFFF | 4 | 0（USB 侧） | 2.4G 唤醒帧 `A6 FF 01`，report ID=**5** | ✅ |
| 其余 3 个 | — | — | — | 键盘/鼠标/consumer（dongle 共 6 个可读 HID 接口） | 不使用 |

dongle **没有 0xFF67**，即没有 TFT 专用通道。USB 的 0xFFFF 小接口在 `protocol.md` 记为 MI_01 COL05；dongle 实测记为 MI_02/COL05。两者 MI 号不同，**按 usagePage=0xFFFF + IN=4 查找**。

### 1.3 HID report ID 与长度关系

- 厂商报文 report ID 一律 = **0**。Win32 `OutputReportByteLength`/`InputReportByteLength` **含** 1 字节 report ID；WebHID `reportCount` **不含**。
- 对应：主协议 65 = 1+64（payload 64，标准头后每包数据 56）；TFT OUT 4105 = 1+4104（数据 4096），TFT IN 65；2.4G 33 = 1+32（标准头数据 24；4B 自定义头数据 28）；0xFFFF IN 4 = 1+3（report ID 5 + `A6 FF 01`）。
- **写**：缓冲区长度必须 == `out_len`，`buf[0]=0`，后跟 payload；不要只传 64B。WebHID 用 `sendReport(0, payload64)`，payload 不含 ID。
- **读**：`ReadFile`/hidraw 返回含 ID；解析前先 `payload = report[1:]`。首字节不是 `0x55`/`0xA6` 时，先检查是否忘了剥 ID。

### 1.4 枚举与打开

Windows（`ajazz.py:163-308`，纯 ctypes/P/Invoke）：

- `HidD_GetHidGuid` → `SetupDiGetClassDevsW(DIGCF_PRESENT|DIGCF_DEVICEINTERFACE)` → `SetupDiEnumDeviceInterfaces` → `SetupDiGetDeviceInterfaceDetailW` 调两次（先取长度，再填 `SP_DEVICE_INTERFACE_DETAIL_DATA_W`；x64 首 DWORD 填 8、x86 填 6）。
- `CreateFileW(path, GENERIC_READ|WRITE, FILE_SHARE_READ|WRITE, OPEN_EXISTING)`；参考实现给同一路径开**写句柄（同步）+ 读句柄（FILE_FLAG_OVERLAPPED）+ 事件**。
- `HidD_GetAttributes`（VID/PID/版本）→ `HidD_GetPreparsedData` + `HidP_GetCaps`（`UsagePage/Usage/InputReportByteLength/OutputReportByteLength`）→ `HidD_GetProductString`。
- 写：`WriteFile(wr, buf, out_len)`。读：`ReadFile` + `WaitForSingleObject(event, timeout)` + `GetOverlappedResult`；超时用 `CancelIoEx` 并 `ResetEvent`。
- 标准键盘 collection 的 `CreateFile` 会 err=5（系统保护），只打开厂商接口。

Linux（**本仓库未实测**，移植建议）：

- 枚举 `/sys/class/hidraw/hidraw*/device/uevent`（`HID_ID=0003:00000C45:00008047`、`HID_NAME`）或 hidapi `hid_enumerate(0x0C45, pid)`；按 `usage_page ∈ {0xFF68,0xFF67,0xFF60,0xFFFF}` 与 `interface_number` 选口。
- 打开 `/dev/hidrawN`（O_RDWR）；需要 udev 权限（`SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0c45", MODE="0666"`），否则 EACCES；`HIDIOCGRAWINFO` 可核对 vid/pid。
- hidraw 的 `read()/write()` 缓冲区**都含 report ID**（首字节 0）；读用 `poll()` 或非阻塞，不要用阻塞读卡死线程。长度按 `HIDIOCGRDESC` 描述符或 hidapi caps 计算，不要硬编码 65/4105。

## 2. 帧格式

### 2.1 请求（主机→设备，总长 = out_len，`protocol.md:29-40`、`infra.js` 的 `PX/NX`）

| payload 偏移 | 字段 | 含义 |
|---|---|---|
| 0 | `0xAA` | 帧头 |
| 1 | cmd | 命令字（§3） |
| 2 | len | **本包逻辑内容长度** = `min(chunk, 剩余)`；非末包=chunk，末包=余数。GET 请求即使不带 data 也要填请求的 contentSize |
| 3 | addrLo | 逻辑数据偏移低字节 |
| 4 | addrHi | 逻辑数据偏移高字节（小端 addr = Lo \| Hi<<8） |
| 5 | hdr5 | 通常 0；`0x32` 帧流用作参数 `i` |
| 6 | last | 末包=1；TFT 0x4D 的 [6..7]=materialId 小端，0x50 的 [6..7]=`50 06`，0x51 的 [6]=1（单包） |
| 7 | hdr7 | 通常 0；TFT 0x4D 为 materialId 高字节，0x50 固定 0x06 |
| 8.. | data | 数据；不足补 0 到 out_len |

- **last 语义**：标记一个逻辑内容单元的最后分包；SET_KEY 等整表写依赖末包置 1 提交；宏写分两阶段，目录段故意全 0、动作段末包 1（§4.8）。TFT 用 seq/total，不依赖 last。
- **addr 用途**：逻辑内容内偏移。整表命令按 `chunk` 递增（SET_KEY：0,56,112…）；单槽读键用 `slot*4`；宏用块绝对偏移（目录 0，数据区 400 起）；2.4G 64B 读灯用 `块号*(reportCount-8)`。
- **data 上限**：主协议 56B/包；TFT 4096B/包；2.4G 标准头 24B/包、4B 自定义头 28B/包。标准头命令总内容 ≤ 65535（addr 16 位）；TFT 用 seq/total 16 位（≤65535 包）。
- 示例：`GET_DEVICE_INFO` 请求 = `00 AA 10 30 00 00 00 01 00` + 0 填充（ID=0，cmd=10，len=48，addr=0，last=1）。

### 2.2 响应（设备→主机，`protocol.md:42-50`、`infra.js` 的 `FX`）

| payload 偏移 | 字段 | 含义 |
|---|---|---|
| 0 | `0x55` | 帧头 |
| 1 | cmd | 回应命令字 |
| 2 | lenOrType | 写 ACK 回显本包 len；`GET_DEVICE_INFO` 实测 `0xF9`；**不要用它校验** |
| 3 | addrLo | 写 ACK 回显块起点；读响应可能回显请求 addr |
| 4 | addrHi | 同上 |
| 5 | hdr5 | 通常 0 |
| 6 | last | 写 ACK 回显请求的 last |
| 7 | hdr7 | 通常 0/1 |
| 8.. | data | 读取内容；按 `contentSize` 截断 |

- 示例：`GET_DEVICE_INFO` 响应头 `55 10 F9 00 00 00 01 00`；`SET_GAME_MODE` ACK `55 21 38 00 00 00 01 00`（len=0x38=56，last=1）；`SET_KEY` 首包 ACK `55 22 38 00 00 00 00 00`（last=0）。
- **读取陷阱**：512B 内容按 56B/包 → 10 个响应共 560B，必须 `slice(0,512)`；否则多出的 48 个 0 会被当成第 129..140 槽（`keymap.md:594-596`）。

### 2.3 ACK 规律（写命令原样回显，`TEST-REPORT.md:40-48`、`deepdive-mk87.md:42-51`）

| 命令 | ACK cmd | ACK 内容 |
|---|---|---|
| `SET_GAME_MODE` 0x21 | 0x21 | 回显 56B，len=0x38 |
| `SET_LED_EFFECT` 0x23 | 0x23 | 回显 16B，len=0x10 |
| `SET_KEY` 0x22 / `SET_FN_KEY` 0x26 | 同 cmd | 每包回显本块 56B，len=0x38，addr=块起点，last 同步回显 |
| `SET_CUSTOM_LED_DATA` 0x24 | 0x24 | 每包回显 56B |
| `SET_TEMPORARY_COMMAND_DATA` 0x34 | 0x34 | 回显 payload（24B 时 len=0x18；10B 时 len=0x0A） |
| `SET_MACRO` 0x25 | 0x25 | 每包回显；目录段全包 last=0，动作段末包 last=1 |
| `0x32` 帧流 | 0x32 | 原样回显所发数据，延迟 0.5–3 ms |
| `SET_TFT_MATERIAL` 0x4D | **0x41** | 逐包 `55 41 00 01 00 00 00 00`（不是 0x4D） |
| `SET_TFT_USER_ANIMATION` 0x50 | **0x41** | 同上（官方 responseCmd 指定 0x41） |
| `SET_TFT_BUILT_IN_INDEX` 0x51 | **0x41** | 真机实测也是 0x41（`phase2_tft.json`），deepdive 的「ACK=0x51」是静态误判 |

- 读命令：ACK cmd = 请求 cmd，data@8；GET 的 `lenOrType` 不保证等于请求长度。
- `SET_FACTORY_RESET` **不等 ACK**（官方发完 sleep 100ms）。
- 主动上报帧（0xFA/0xFC/0xA6）是**扁平头**，不是本节的 8 字节响应头，见 §7。

### 2.4 超时/重试（官方 `NX` 默认 + 实测）

| 场景 | 超时 | 重试 | 说明 |
|---|---|---|---|
| 普通 GET/SET | 500 ms | 3（共 4 次） | `frameVersion==1` 时 2000 ms；MK87=0 |
| SET_KEY / SET_FN_KEY | 1000 ms | 1–2 | 512B→10 包，整表约 30 ms |
| TFT 逐包 | 2000 ms | 0（探测）/ 3（官方 NX 默认） | 同 seq 重发幂等（未单独实测）；默认动画 2136 包中 37 包未等到 ACK 仍成功 |
| 0x32 帧流 | 50 ms（官方）/ 120–200 ms（探测） | 官方 3 / 实践 0–1 | 追 20fps 时不要因单包超时拖死整帧 |
| 2.4G 音乐 0x3C | 10 ms | 0 | 官方故意不重发 |
| 通知监听 | 20–50 ms 轮询 | — | 见 §7 |

## 3. 命令表（66 条，`command_enum.txt`；MK87 状态按 FEATURES.md + 真机）

状态取自 `FEATURES.md` 各功能行（`#n`）与第三节能力边界；未标 `#` 的命令按官方代码/真机证据判定。

| cmd | 名称 | MK87 | 依据/备注 |
|---|---|---|---|
| 0x01 | COMMUNICATION_START | ⬜ | 未使用，无握手 |
| 0x02 | COMMUNICATION_END | ⬜ | 未使用 |
| 0x0F | SET_FACTORY_RESET | ⬜ | 官方类型 1/2/4/5/255；未在真机发送 |
| 0x10 | GET_DEVICE_INFO | ✅ | FEATURES #1 |
| 0x11 | GET_GAME_MODE | ✅ | FEATURES #20 |
| 0x12 | GET_KEY | ✅ | FEATURES #2，112/128 槽非零 |
| 0x13 | GET_LED_EFFECT | ✅ | FEATURES #6 |
| 0x14 | GET_CUSTOM_LED_DATA | ✅ | FEATURES #7 |
| 0x15 | GET_MACRO | ✅ | FEATURES #12，空表 |
| 0x16 | GET_FN_KEY | ✅ | FEATURES #3 |
| 0x17 | GET_MAGNETIC_AXIS_RT | ⛔ | 磁轴不适用 |
| 0x18 | GET_MAGNETIC_AXIS_DKS_DATA | ⛔ | 磁轴不适用 |
| 0x1B | GET_LIGHT_BOX | ✅ | 读回全 0（无硬件） |
| 0x1C | GET_DEFAULT_FN_KEY_MATRIX | ✅ | 与 FN 层逐字节一致 |
| 0x1D | GET_SIDE_LIGHT | ✅ | 读回全 0 |
| 0x1E | GET_TRIGGER_KEY | ⛔ | 磁轴不适用 |
| 0x1F | GET_DEFAULT_KEY_MATRIX | ⛔ | 真机返回全 0（不支持） |
| 0x21 | SET_GAME_MODE | ✅ | FEATURES #20 |
| 0x22 | SET_KEY | ✅ | FEATURES #4 |
| 0x23 | SET_LED_EFFECT | ✅ | FEATURES #6 |
| 0x24 | SET_CUSTOM_LED_DATA | ✅ | FEATURES #7 |
| 0x25 | SET_MACRO | ✅ | FEATURES #13 |
| 0x26 | SET_FN_KEY | ✅ | FEATURES #4 |
| 0x27 | SET_MAGNETIC_AXIS_RT | ⛔ | 磁轴 |
| 0x28 | SET_MAGNETIC_AXIS_DKS_DATA | ⛔ | 磁轴 |
| 0x2A | SET_DOT_MATRIX_MODE | ⛔ | 无点阵硬件 |
| 0x2B | SET_LIGHT_BOX | ⛔ | 无灯箱 |
| 0x2D | SET_SIDE_LIGHT | ⛔ | 无侧灯 |
| 0x2E | SET_TRIGGER_KEY | ⛔ | 磁轴 |
| 0x30 | SET_KEYBOARD_CUSTOM_FUNCTION_ON | ⬜ | 死代码（0 调用） |
| 0x31 | SET_KEYBOARD_CUSTOM_FUNCTION_OFF | ⬜ | 死代码 |
| 0x32 | GET_LED_DATA | ✅ | 官方 setMusicData 的 USB 分支当**写**用；FEATURES #10/#11 |
| 0x33 | GET_ALL_LIGHTS_RGB | ✅ | FEATURES #11，可验证帧流 |
| 0x34 | SET_TEMPORARY_COMMAND_DATA | ✅ | FEATURES #17（时间） |
| 0x35 | SET_MUSIC_DATA | ⬜ | USB 未单独验证；2.4G 试发无效果 |
| 0x36 | CLEAR_LED_DATA | ⬜ | 官方清 LED 缓冲；真机未发 |
| 0x37 | GET_ALL_LIGHTS_RGB_24G | ⬜ | 2.4G 读灯实际用 0x33 |
| 0x3B | GET_ALL_LIGHTS_RGB_24G_64_BYTE | ⬜ | 64B 口（0xFF59）无响应 |
| 0x3C | SET_MUSIC_DATA_24G_64_BYTE | ⛔ | 试发无效果；官方确认 2.4G 不支持音乐 |
| 0x3D | GET_DOT_MATRIX_CONFIG | ✅ | 读回全 0 |
| 0x40 | SET_LED_BOOT_ANIMATION | ⛔ | 死代码；无 LED 动画 |
| 0x41 | SET_LED_USER_ANIMATION | ⛔ | FEATURES #8；`ledMaxFrames=0`，但 TFT 0x50 的 ACK 用此值 |
| 0x42 | SET_LED_DATA | ⛔ | 无 LED 动画/GIF 灯效 |
| 0x4D | SET_TFT_MATERIAL | ✅ | 16 包全 ACK，但屏幕无壁纸页→不可见 |
| 0x4F | SET_FLASH_DOWNLOAD | ⬜ | OTA 相关，跳过 |
| 0x50 | SET_TFT_USER_ANIMATION | ✅ | FEATURES #15，真机播放 |
| 0x51 | SET_TFT_BUILT_IN_INDEX | ⛔ | ACK 但不切页（确认不支持） |
| 0x60 | GET_MAGNETIC_AXIS_KEY_STATUS | ⛔ | 死枚举 |
| 0x64/0x65 | SET_CALIBRATION_ON / SET_CALIBRATION_OFF | ⛔ | 磁轴 |
| 0x66/0x67 | SET_SIMULATION_TEST_ON / SET_SIMULATION_TEST_OFF | ⛔ | 磁轴 |
| 0x68 | GET_MAGNETIC_AXIS_STATUS | ⛔ | 磁轴 |
| 0x69/0x6A | SET_CALIBRATION_ON_V2 / SET_CALIBRATION_OFF_V2 | ⛔ | 磁轴 |
| 0x80 | OTA_GET_DEVICE_SYSTEM_INFO | ⛔ | 真机全 0（fw 不接受） |
| 0x81 | OTA_VERIFY_FIRMWARE_INFO | ⛔ | 跳过 OTA |
| 0x82 | OTA_DEVICE_ENTER_BOOT | ⛔ | 跳过 |
| 0x83 | OTA_SEND_FIRMWARE_INFO | ⛔ | 跳过 |
| 0x84 | OTA_GET_DEVICE_SN | ⛔ | 真机全 0（frameVersion=0） |
| 0x85 | OTA_SWITCH_APP_PARTITION | ⛔ | 跳过 |
| 0x86 | OTA_SET_DEVICE_SN | ⛔ | 跳过 |
| 0x90 | SET_PROFILE | ⛔ | FEATURES #21；`maxProfile=0`，纯本地 profile |
| 0xFA | GET_DEVICE_NOTIFY | ⬜ | FEATURES #25；真机未观察到 |
| 0xFB | GET_MAGNETIC_AXIS_CALIBRATION_DATA | ⛔ | 磁轴 |
| 0xFC | GET_24G_DISCONNECT_NOTIFY | ✅ | FEATURES #24；捕获 `55 FC 04` |

## 4. 各命令 payload / 响应布局
### 4.1 GET_DEVICE_INFO 0x10 ✅

- 请求 data：无；`contentSize=48`；1 包：`00 AA 10 30 00 00 00 01 00` + 0 填充。
- 响应 data：偏移 8，48B；结构见 §5。响应头实测 `55 10 F9 00 00 00 01 00`。
- 真机：`version=1.19`、`batteryLevel` 随充电变化（TEST-REPORT 记录 50→52，FEATURES 记录至 75）、`tftMaxFrames=140`、`tftDirection=0`、`tftColorByteOrder=0`。官方在未开 `macroConfig.isGetMaxMacroSpaceSize` 时把 `macroSpaceSize` 显示成 512，raw 值是 **3072**。
### 4.2 GET_GAME_MODE 0x11 / SET_GAME_MODE 0x21 ✅

- GET：data 无，`contentSize=56`；响应 data@8，56B（§6）。
- SET：data 56B；ACK 回显 56B（`55 21 38 00 00 00 01 00` + data），随后 `GET_GAME_MODE` 逐字节回读一致。
- 真机：只改 `[7]`（12/24h）或 `[3]`（sleepTime）回写成功；其余字段原样保留。不要只发部分字段，官方实现固定发 56B 全量。
### 4.3 SET_FACTORY_RESET 0x0F ⬜

- 请求：1 包 `AA 0F <type> 00 00 00 00 00`（len=type、addr=0、last=0、data 无）；官方 `sendReport(0, packet)` 后 sleep 100ms，**不等 ACK**。
- type（`UX`）：1=键位、2=灯效、4=宏、5=清校准、255=全部。
- 真机：本仓库**未发送**（会清配置）；默认 FN 层 Fn+Space 绑定 FUNC 1（恢复出厂），是固件入口。复位后设备可能发 `55 FC 05`（§7）。
### 4.4 SET_TEMPORARY_COMMAND_DATA 0x34 ✅（时间 / 系统信息共用）

时间 payload（10B，`protocol.md:140-141`、`tft-page.md:392-412`）：

| 偏移 | 值 |
|---|---|
| 0–2 | `5A 01 5A` 固定头 |
| 3 | 年 `%100`（2026→26） |
| 4 | 月 1–12 |
| 5 | 日 |
| 6 | 时 0–23（本地时间） |
| 7 | 分 |
| 8 | 秒 |
| 9 | 星期：0=周日 … 6=周六 |

系统信息 payload（24B，`tft-page.md:187-214`）：`[6]=0x5A`；`[12]=CPU占用0–100`、`[13]=CPU温度int8`、`[14]=GPU占用`、`[15]=GPU温度int8`、`[16]=当前气温int8`、`[17]=最高`、`[18]=最低`、`[19]=天气码0–23`、`[20]=湿度0–100`；其余 0。

- contentSize：官方发 24（10B 时间也补到 24，头 `AA 34 18 00 00 00 01 00`）；探测发 10 也成功（头 `AA 34 0A …`）。ACK 原样回显 payload（24B→len=0x18，10B→len=0x0A）。
- 判定：`p[2]==0x5A` 为时间；`p[6]==0x5A` 为系统信息。
- 真机：时间 ACK `5A 01 5A 1A 0B 01 06 3B 17 00`（2026-11-01 06:59:23 周日）；系统信息 ACK 正常，但 MK87 无系统信息页 → 无可观察效果。
### 4.5 GET/SET_KEY 0x12/0x22、GET/SET_FN_KEY 0x16/0x26、默认矩阵 0x1C/0x1F

- 布局：512B = 128 槽 × 4B `[pageType, param1, param2, param3]`；槽号 = 官方 `keyList.value`，字节偏移 = `slot*4`。
- 读全表：`GET_KEY`/`GET_FN_KEY`，data 无，`contentSize=512`，响应 data@8；响应 560B 必须截 512。
- 读单槽：自定义头 `AA 12 04 <addrLo> <addrHi> 00 00 00`，addr=`slot*4`，`contentSize=4`，响应 data@8 取 4B（FN 用 `AA 16 ...`）。
- 写：`SET_KEY`/`SET_FN_KEY` data=512B，10 包（56×9+8），逐包 ACK（cmd 同、len=0x38、addr=块起点）。
- 默认矩阵：`GET_DEFAULT_FN_KEY_MATRIX(0x1C)` 512B 与 FN 层逐字节一致；`GET_DEFAULT_KEY_MATRIX(0x1F)` 真机返回全 0（不支持）。
- 语义：`pageType=2` 普通键（param2=HID usage）；`6` 宏（param1=宏 id、param2=mask 0/1/2、param3=mask 参数，mask=1 时为重复次数）；`13` FUNC（param1..3 为 24 位大端动作 id）；`0` 空/默认。完整 16 种 pageType 见 `keymap.md:141-203`。
- 真机注意：**没有单槽写**，每次整表 512B；写 0 = 恢复出厂默认（keyList 内的槽）；25 个配置外槽写 0 被固件保护、写非零生效（`TEST-REPORT.md:151-159`）。必须先读→只改目标槽→整表写回，不能只构造目标槽。
### 4.6 GET/SET_LED_EFFECT 0x13/0x23 ✅（16B）

| 偏移 | 字段 | 取值/说明 |
|---|---|---|
| 0 | mode | 0=关灯；1–19 内置；20/21/128 自定义族 |
| 1–3 | R/G/B | 主色，`colorMode=0` 时生效 |
| 4 | driverSetting | 写端恒 **255** |
| 5–7 | 副色 R/G/B | 仅 mode 254 等使用，MK87 无 |
| 8 | colorMode | 0=单色，1=RGB |
| 9 | brightness | 1–6；**1=全灭**（PWM 0/49/97/143/191/253），越界未定义 |
| 10 | speed | 1–6 |
| 11 | direction | 0/1/2/3 = 右/左/上/下 |
| 12 | effectModeType | 0–3，仅 mode 254 |
| 13 | — | 0 |
| 14–15 | 校验尾 | **0xAA 0x55** |

- GET：data 无，`contentSize=16`，响应 data@8；SET：data 16B；ACK 回显 16B（`55 23 10 ...`）。
- 真机：19 个模式全部可点亮；20/21/128 共用同一张 `SET_CUSTOM_LED_DATA` 表；2.4G 下写后颜色/colorMode 回读可能不等于写入（显示正确）→ 2.4G 不要用回读判成功。
### 4.7 GET/SET_CUSTOM_LED_DATA 0x14/0x24 ✅（512B）

- 布局：128 组 × 4B `[ledId, R, G, B]`；`ledId` = 槽号 0–127；未用槽写 0。
- GET：data 无，`contentSize=512`，响应 data@8；SET：data 512B（10 包，每包 56B，ACK cmd 0x24）。
- 真机：逐键颜色对应；写 255 回读 253（PWM 上限）。物理 LED 86 个：99/100/102 无 LED（位置是小屏），97/98 有驱动通道但人眼不可见；Fn 键红灯是充电指示灯，不受 LED 数据控制（`TEST-REPORT.md:80-88`）。
### 4.8 GET/SET_MACRO 0x15/0x25 ✅（400B 目录 + 动作区）

- 逻辑地址：目录 0..399 = 100 × u32 LE 绝对偏移（0=空）；动作区从 **400** 开始，块按写入顺序排列（目录负责 id→offset 映射）。
- GET：先 `contentSize=400, addrStart=0` 读目录；对每个非 0 偏移 `c`：读 4B 块头（`addrStart=c`），`count=u16LE/2`；再 `contentSize=count*4, addrStart=c+4` 读动作。响应 data 均 @8。
- 块格式：`[0..1]=动作数×2 (u16LE) [2..3]=0`；每动作 4B：`delay u16LE | keyCode(HID usage) | flags`，`flags=((actionType&7)<<4)|(isPress?0x80:0)`；键盘 `actionType=3` → 按下 0xB0 / 抬起 0x30；鼠标 1/2 → 0x90/0x10。
- 写（两次 `SET_MACRO`）：① `contentSize=400, addrStart=0`，**所有包 last=0**（官方 `isNeedLastPacketFlag:false`）；② `contentSize=len(data), addrStart=400`，末包 last=1。清空：只写 400B 全 0 且 last=1。
- 真机：写 "abc" 回读逐字节一致；Insert 绑定 `06 00 00 00` 生效；mask 0/1/2 实测（`keymap.md:928-982`）。目录段 last=0 是官方实现的关键细节，普通 NX 实现要单独处理。
### 4.9 GET_ALL_LIGHTS_RGB 0x33 ✅（512B）

- 请求 data：512B = 128 × `[ledId,0,0,0]`（`ledId` 0..127）；`contentSize=512`，10 包。
- 响应 data：偏移 8，512B = 128 × `[ledId,R,G,B]`；560B 截 512。
- 真机：约 29 ms；读的是当前逐键 LED 缓冲，可用于验证 0x32 帧流（发帧后立即读回帧颜色）；85–86 颗点亮。2.4G 同样可用（实测 85 键）。
### 4.10 GET_LED_DATA 0x32（官方 setMusicData 的 USB 写通道）✅

- 帧载荷：87 个可见键 × 4B `[keyValue, R, G, B]` = **348B**；顺序 = `lighting-modes.json` 的 `ledKeyMap.rowsInPreview` 行优先展平（可见键，非 128 槽）。
- 分包：每包 56B（14 键）→ 前 6 包 56B + 末包 12B，共 **7 包/帧**。
- 头：`AA 32 <len> <addrLo> <addrHi> <i> <last> 00`；`len`=本包数据长（0x38/0x0C），`i`=官方第二参数（MK87 恒 0 可用），末包 last=1。
- 响应：cmd 0x32 原样回显所发数据（不是设备状态）；ACK 0.5–3 ms。
- 真机：必须先 `SET_LED_EFFECT` 切到 **mode 20/21/128**（否则无显示）；停止发帧约 **5 s** 回落到自定义表；20 fps 稳定，平均 15.5 ms/帧（7 包，1050/1050 ACK），理论上限约 60 fps（`TEST-REPORT.md:177-196`）。2.4G 下三种格式（0x32/0x35/0x3C）均只出现短暂白脉冲/随机色/竖条纹，**官方确认 2.4G 不支持音乐律动**。
### 4.11 TFT 系列 0x4D / 0x50 / 0x51（TFT 接口 MI_03，每包 4105B，数据 4096B）

**通用**：`out_len=4105`，payload 4104 = 8B 自定义头 + 4096B 数据；`IN=65`；逐包等 ACK **0x41**（`55 41 00 01 00 00 00 00`）；单包写约 65 ms；phase2 JSON 实测等 ACK 约 72–80 ms/包（135 帧 8.75MB 用 311 s，整包约 145 ms、约 28 KB/s；TEST-REPORT 记“ACK 15 ms”与上传时长不符，按实测规划）。TFT 包不使用标准 len/addr/last，头部自有序号/总包数。

**0x4D SET_TFT_MATERIAL（壁纸）**：头 `AA 4D seqLo seqHi totalLo totalHi matLo matHi`（`materialId` 小端，网页只用 0）；数据 RGB565。240×135×2=**64800B → 16 包**（末包 3360B + 736B 零填充）。真机：16 包全 ACK，但 MK87 屏幕**没有壁纸页 → 不可见**；官方代码按 0x4D 等 ACK 会超时。

**0x50 SET_TFT_USER_ANIMATION（动画）**：头 `AA 50 seqLo seqHi totalLo totalHi 50 06`；数据 = **256B 延时表 + 各帧 RGB565 连续拼接**。
延时表：`[0]=帧数 n`；`[1..n-1]=min(delay_cs*5,255)`（最后一帧不写）；`[n]=0` 终止符；**其余全部 255**（`scripts/tft_ref.js:117-132`；`probe/ajazz.py` 未填 255，属实现差异）。固件时间单位 **2 ms**（厘秒×5 = ms/2）。单帧 64800B；140 帧 = 256+140×64800 = **9,072,256B → 2215 包**；135 帧默认动画 8.75MB/2136 包/311 s（`TEST-REPORT.md:109-112`）。像素 RGB565，`tftColorByteOrder=0` → 每像素先低字节后高字节。真机：3 帧/135 帧均正常播放。

**0x51 SET_TFT_BUILT_IN_INDEX（内置索引）**：请求 data 1B（索引），`contentSize=1`；头 `AA 51 01 00 00 00 01 00 <idx>`（TFT 接口）。真机发 0..5 每包回 `55 41`，**屏幕无任何反应** → MK87 不支持切页；页面由设备端菜单控制。
### 4.12 0x40 / 0x41 / 0x42 / 0x2B（LED 动画 / 灯箱）⛔

MK87 `ledMaxFrames=0`、无 `ledConfig`、`isShowGifEffect` 缺省、无灯箱/侧灯 → 这组不可用；仅记录官方格式（注意：**没有 0x43 命令**；灯箱是十进制 43 = `0x2B`）：

- `0x40 SET_LED_BOOT_ANIMATION`：枚举存在，bundle 0 调用；开机动画实际复用 0x41（`ledId='startup'`）。
- `0x41 SET_LED_USER_ANIMATION`：8B 头 `AA 41 seqHi seqLo totalHi totalLo 00 00`（**大端序号**）；数据 = `[帧数 u16LE][ceil(106-speed) u16LE]` + 帧×行×列×RGB888；每包 4096B。
- `0x42 SET_LED_DATA`：8B 头 `AA 42 seqHi seqLo totalHi totalLo 00 00`；4B 前导 + RGB 流；`setGifLighting`/`setLedSyncAnimation` 用。
- `0x2B SET_LIGHT_BOX`：24B payload，`[0]=mode [1..3]=RGB [8]=colorMode [9]=brightness [10]=speed`，其余 0；MK87 无硬件。
### 4.13 CLEAR_LED_DATA 0x36 ⬜

- 请求：无 data；官方 `NX` 未指定 contentSize → 默认 24，1 包 `AA 36 18 00 00 00 01 00` + 0；ACK `55 36`。超时 500 ms（`frameVersion=1` 时 2000）。
- 用途：清 LED 数据缓冲（官方仅点阵屏/LED 数据组件调用）。**真机未验证**；对灯效持久设置的影响未知。
### 4.14 0xFA / 0xFB / 0xFC / 0xA6 主动上报

这四条不是请求-响应帧，payload 直接从第 3 字节开始（`key-events.md:183-193`）；详见 §7。

- `0xFA`：`55 FA <type> <p...>`；已知 type=6，`p0=帧[3]` = TFT 系统信息页 0/1。
- `0xFB`：`55 FB` + 12B = 14B 扁平帧：`keyValue(1)|status(1)|max(u16LE)|min(u16LE)|current(u16LE)|keyStroke(u16LE)|maxStroke(u16LE)`；需先发 0x64/0x66。
- `0xFC`：`55 FC <type>`；4=2.4G 断连、5=复位、6=休眠。
- `0xA6`：唤醒帧，完整 report `05 A6 FF 01`（0xFFFF 接口，report ID=5）。

## 5. GET_DEVICE_INFO 48B 结构（实测）

| 偏移 | 类型 | 字段 | 实测值 |
|---|---|---|---|
| 0 | u8 | romSize | 64 |
| 2 | u16LE | macroSpaceSize | 3072（0x0C00） |
| 4 | u16LE | vid | 0x0C45 |
| 6 | u16LE | pid | 0x8047 |
| 8 | 2B | version（版本编码） | 0x0119 → **1.19** |
| 10 | u16LE | sensor | 0xFFFF |
| 12 | u16LE | manufacturer | 1 |
| 14 | u16LE | product | 18 |
| 16 | u8 | workMode | 0=USB，**2=2.4G** |
| 17 | u8 | batteryLevel | 50–75（充电中） |
| 18 | u8 | chargeStatus | 1=充电 |
| 19 | u8 | currentProfile | 0 |
| 20 | u16LE | axisInfo | 0 |
| 22 | u16LE | tftMaxFrames | **140** |
| 24 | u16LE | gifMaxFrames | 0 |
| 26 | u16LE | ledMaxFrames | **0** |
| 28 | u8 | tftDirection | 0（0=横屏，1=竖屏，255=无屏） |
| 29 | u8 | rtPrecision | 0 |
| 30 | u8 | frameVersion | 0 |
| 31 | u8 | lightingVersion | 0 |
| 32 | u8 | firmwareStatus | 0 |
| 33 | u8 | maxProfile | 0 |
| 34 | u8 | 保留 | 0 |
| 35 | u8 | tftColorByteOrder | 0（0=小端 RGB565，1=大端） |
| 36–47 | — | 未用 | 全 0 |

- 版本解码（官方）：`((d[8]&0x0F) + ((d[8]&0xF0)>>4)*10 + d[9]*100)/100`；`0x19,0x01` → 1.19。
- 实测 raw（`device_dump.json`）：`40 00 00 0C 45 0C 47 80 19 01 FF FF 01 00 12 00 00 3E 01 00 00 00 8C 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`。
- **没有 keyCount 字段**：键数来自其它证据 —— 128 槽、主层 112 个非零槽、官方配置 87 键、物理 LED 86 个、固件矩阵 98 键（`deepdive-mk87.md:3`、`deepdive-mk87.md:21-27`）。

## 6. 游戏模式 56B 结构（GET 0x11 / SET 0x21）

| 偏移 | 字段 | MK87 实测 | 说明 |
|---|---|---|---|
| 0 | 未解析 | 0 | 固定 0 |
| 1 | gameMode | 0 | 官方 UI 可写；MK87 上行为未验证 |
| 2 | fnSwitch | 0 | FN 层开关 |
| 3 | **sleepTime** | **5** | **单位=分钟**；0=关闭；官方 UI 选项 1/10/20/30；实测 1 分钟即触发 2.4G 断连 |
| 4 | keyDelay | 2 | 官方 UI 选项 3/4/5；实测 2，行为未量化 |
| 5 | reportRate | 0 | 1000→3、2000→4、4000→5、8000→6（静态映射）；MK87 不支持 |
| 6 | systemMode | 0 | UI 从不修改，原值回写 |
| 7 | **tftDisplayTime** | 0 | **0=24h，1=12h**；写入/回读/断电重启均生效，但屏幕时钟格式**无可见变化** |
| 8 | topDeadZone×100 | 0xFF | 磁轴死区，不支持 |
| 9 | bottomDeadZone×100 | 0xFF | 同上 |
| 10 | 未解析 | 0xFF | — |
| 11 | stabilityMode | 0xFF | 不支持 |
| 12–13 | 未解析 | 0xFF | — |
| 14 | autoCalibration | 0xFF | 不支持 |
| 15 | singleKeyWakeup | 0xFF | 不支持 |
| 16 | pushButtonMode | 0xFF | 不支持 |
| 17 | nkroSwitch | 0xFF | 不支持 |
| 18–19 | wirelessReportRate | 0xFFFF | u16LE，不支持 |
| 20 | powerMode | 0xFF | 不支持 |
| 21–55 | — | 0xFF | 保留；必须原样回写 |

- 读写：GET `contentSize=56`；SET data 56B + 回读校验；ACK 回显 56B。`0xFF` 字段表示固件不支持，写回 `0xFF` 即保持。
- 真机结论：`sleepTime`、`tftDisplayTime` 已实测可写且回读一致（后者对屏幕无可见效果，重启后仍 24h）；`keyDelay` 字段存在（当前 2），单独改写后的行为未量化；多数字段 `0xFF` 不可改。

## 7. 通知 / 事件通道
### 7.1 帧与通道

| 帧 | 从哪读 | 触发 | 解析 | MK87 |
|---|---|---|---|---|
| `55 FA <type> <p...>` | 主协议接口（USB MI_02 / 2.4G 0xFF60） | 设备状态变化 | 扁平：type=帧[2]，payload=帧[3..]；type=6 时 `p0`=TFT 信息页 0/1 | ⬜ 未观察到；官方因缺 `isShowTftInfo` 从不注册 |
| `55 FB …`（14B） | 主协议 | 已发 0x64/0x66 | 扁平 12B 字段（§4.14） | ⛔ 磁轴，无数据 |
| `55 FC 04` | 2.4G 0xFF60（33B） | 2.4G 断链 | 扁平；type=帧[2]=4 | ✅ 捕获 |
| `55 FC 05` | 主协议口（USB/2.4G 均可能） | 设备复位/恢复出厂 | 扁平；type=5 | ⬜ 未捕获（官方所有设备都注册） |
| `55 FC 06` | 2.4G 0xFF60 | 2.4G 休眠 | 扁平；type=6 | ⬜ 未捕获（实测只有 type=4） |
| `A6 FF 01` | **0xFFFF 接口**（IN=4，report ID=5） | 2.4G 按键唤醒 | 固定 3B，无 payload | ✅ 完整 report `05 A6 FF 01` |

- 实测断连帧原文（`phase6_sleep_wake.json`）：`00 55 FC 04 30 00 00 01 00 FF FF FF FF FF FF FF FF 00…`（首字节 00 是 report ID；后面是扁平 payload，**不要**按 8 字节响应头解析）。
- 唤醒帧：该接口 OUT=0、IN=4，`A6 FF 01` 是唯一非 0x55 头上报；USB 直连是否也发**未验证**。
### 7.2 官方驱动缺失的部分

- `0xFA/6` 被 `tftConfig.isShowTftInfo` 门控，MK87 的 tftConfig 无此键 → 官方从不监听系统信息页。MK87 屏幕也没有系统信息页。
- 唤醒帧走 0xFFFF 接口，而官方 WebHID 过滤器表是 `[0xFF68,0xFF80,0xFF60,0xFF00,0xFF01,0xFF1B]`（bundle 常量 `65307`；FEATURES/TEST-REPORT 写作 `0xFF5B`，与常量不符），**不含 0xFFFF** → 官方收不到唤醒帧。
- `0x4D` 壁纸路径按 `0x4D` 等 ACK，真机实际回 `0x41` → 官方壁纸上传必然超时（且 MK87 无壁纸页）。
- `0x51` 因 `builtInCount` 未定义，官方网页从不发送。
- 2.4G 音乐分支要求 `reportCount==64 && lightingVersion==1`，MK87 是 32B/0 → 官方逻辑在 MK87 上本来就走不通。
- 厂商协议**没有按键事件**；官方按键测试页监听浏览器 DOM。用户态读 `\kbd` 被拒 err=5，Windows 只能用 RawInput（VKey+MakeCode+设备名），Linux 走 evdev。
### 7.3 监听实现建议

- 每个接口一个 reader 线程/协程，读超时 20–50 ms，循环取帧；不要阻塞式无限等待。
- 先按帧头分流：`0x55` 且 cmd 是待匹配命令 → 请求响应；`0x55 FA/FC` → 事件队列；`0x55 FB` → 磁轴事件；`0xA6 FF 01` → 唤醒；其余丢弃（未知帧不要当 ACK）。
- 0xFA/0xFC 是扁平结构，**禁止**用 `data[8:]` 解析；0xFC 只有 type 有定义，后续字节无文档（实测有 `30 00 00 01 00 FF…`）。
- 请求等待 ACK 期间，暂停同一接口的监听派发（或由同一 reader 按 cmd 分发），否则 ACK 会被监听逻辑吃掉。
- 2.4G 要同时打开 6 个可读接口；断连/休眠在 0xFF60，唤醒只在 0xFFFF。收到 `55 FC 04` 标记离线并重连；不要像官方那样 `forget()` 丢授权。
- USB 无 0xFC/4（非 2.4G），空闲 5 s/75 s 内 0 条主动上报（`deepdive-mk87.md:67`、`FEATURES.md:45`）。

## 8. 2.4G 与 USB 的行为差异

| 项 | USB | 2.4G |
|---|---|---|
| 设备 | PID 0x8047 | PID 0xFEFE，product `2.4G Dongle`；`workMode=2` |
| 协议口 | MI_02 / 0xFF68 / 65B（数据 56B/包） | MI_03 / 0xFF60 / 33B（标准头 24B/包；512B 表 → 22 包） |
| TFT 口 | MI_03 / 0xFF67 / 4105B，✅ 可上传 | 无 0xFF67；官方函数会退化到协议口 32B 包，**未验证/不建议** |
| 0xFF59 64B 口 | 无 | MI_04，GET 无响应，不在官方过滤器表 → 不用 |
| 按键/FN 矩阵 | 512B | 与 USB dump **逐字节一致**（配置存在键盘端） |
| 灯效写入 | ✅ | ✅ 生效；但 `GET_LED_EFFECT` 的 color/colorMode 回读可能不等于写入 → 用 `GET_ALL_LIGHTS_RGB` 或人眼判 |
| `GET_ALL_LIGHTS_RGB` | 0x33 ✅ | 0x33 也 ✅（85 键）；官方的 0x37/0x3B 未验证 |
| 音乐律动 | 0x32 ✅ 20fps | ⛔ 固件不支持（0x32/0x35/0x3C 均异常显示） |
| 通知 | 0xFC/5 可能；无 0xFC/4 | `55 FC 04` 断连；`A6 FF 01` 唤醒（0xFFFF） |
| 休眠 | — | `sleepTime` 分钟到点断连；`0xFC/6` 未见过 |
| TFT 上传耗时 | 4105B/包；仅写约 63 KB/s，含 ACK 实测约 28 KB/s（135 帧 8.75MB/311s） | 若按 32B 包（24B 数据）会慢约 **170×**，且未实测 |
| Windows 兼容 | 正常 | dongle 与键盘 USB 同插可能 Code 10 / `0xC000009A`（资源不足）；拔掉其一即恢复，建议插不同控制器 |

2.4G 下不要实现：音乐帧流（0x32/0x35/0x3C，官方确认不支持）、TFT 上传（无 0xFF67，未验证）、OTA、磁轴全家、`SET_PROFILE`（maxProfile=0）。2.4G 仍可做：设备信息、游戏模式、键/FN 矩阵读写、灯效/自定义灯、宏读写、`GET_ALL_LIGHTS_RGB`、断连/唤醒监听。

## 9. 给 Python 实现的移植要点

- **hidapi 长度**：`hid_write` 的 buffer 首字节必须是 report ID（0 也要显式给），长度 = `OutputReportByteLength`（主协议 65、TFT 4105、2.4G 33）。不要传 64B 让库“自动补 0”；不同后端/版本对 report ID 的补/去行为不一致，启动时用 `GET_DEVICE_INFO` 自检：写 65B 能通、首回包剥掉 ID 后是 `55 10`。
- `hid_read` / hidraw `read` 返回的 buffer 通常**含 report ID**；`hid_read_timeout(…, 20~50)` 做非阻塞轮询；Windows 用 OVERLAPPED+`CancelIoEx`，Linux 用 `poll()`。
- 选口：`hid_enumerate(0x0C45, 0x8047/0xFEFE)` 后按 `usage_page`（0xFF68/0xFF67/0xFF60/0xFFFF）与 `interface_number` 选；Windows 的 HIDAPI `interface_number` 可能为 -1，优先用 `path` 中的 `mi_0x` 与 usage_page。
- **读写分离**：同一路径开写句柄 + 读句柄（参考 `ajazz.py`），不要多线程同时 ReadFile 同一句柄；同一接口只能有一个 reader 消费输入报告，否则 ACK 会被抢走。TFT 与主协议是不同接口，可并行；2.4G 全部命令共享 0xFF60，必须串行/分发。
- **并发实测边界**：本仓库没有专门做“双 reader 抢同一接口”的对照实验（未验证）；但 `_p6_rw.py` 证明“独立读/写句柄 + 边推 0x32 边读 0x33”可行，前提是同一 reader 按 cmd 分流、把 0x32 的 ACK 与 0x33 的响应分开。任何“一个线程等 ACK、另一个线程轮询状态”的实现都必须共用同一 reader 队列。
- 超时：普通 500 ms、`frameVersion==1` 2000 ms、TFT 2000 ms、0x32 50–200 ms、通知 20–50 ms。重试 2–3 次，按命令独立超时并可取消；重试耗尽只报错，**不要** `device.forget()`/关设备（官方会，别学）。
- 读整表必须截断：GET_KEY/FN/CUSTOM/ALL_LIGHTS 的 512B 内容会收到 10 包×56B=560B，`data[:512]`；否则多出的 48B 0 会被误当槽位。
- 写整表必须读改写：先 GET 512B，只改目标槽，再整表 SET；不要用官方“只填 keyList、其余写 0”的写法（0 会重置 keyList 内的槽）。
- 宏写两阶段：目录 400B **全包 last=0**，动作区末包 last=1；不要用普通 `request()` 自动置 last。
- 0x32 帧流：先 `SET_LED_EFFECT(mode=20/21/128)`，再按 20fps 发 7 包/帧；逐包等 0x32 ACK（超时 120–200 ms），不要因一包超时停流；停流约 5 s 自动回落。
- 2.4G 写灯后等 300–500 ms 再回读（`phase6_wireless.py` 用 0.5 s）；回读不一致不等于写失败，以实际灯效/`GET_ALL_LIGHTS_RGB` 为准。
- TFT 上传是分钟级阻塞任务：单包写约 65 ms + ACK 等待，135 帧默认动画实测 311 s（140 帧上限约 5–6 分钟量级）；放后台线程、按包回调进度、允许取消；同 seq 重发可接受。
- 时间同步：连接后发 10B 时间帧（contentSize 24 更贴近官方），本地时间、无时区；weekday 0=周日。
## 10. 未验证 / 风险清单

- `SET_FACTORY_RESET(0x0F)` 各 type 的真机行为（未发送，会清配置）。
- `CLEAR_LED_DATA(0x36)` 的实际效果（仅官方代码还原）。
- `0x37/0x3B` 2.4G 读灯、`0x35` USB 音乐、`0x2B` 灯箱：均未在 MK87 验证。
- TFT 上传走 2.4G（无 0xFF67）未验证，不建议实现。
- `0xFA`（含 type=6）在 MK87 上是否真的会发；`0xFC/6` 休眠帧未捕获。
- `0x51` 内置索引的取值表（真机只确认“不切页”）。
- `0x4D` 壁纸写入“成功但不可见”；是否有隐藏页面/需要设备端切换未知。
- 12/24h（`tftDisplayTime`）对屏幕无可见作用，是否影响其它页面未知。
- Linux hidraw/hidapi 路径未在本仓库真机验证（Windows 已全通）。
