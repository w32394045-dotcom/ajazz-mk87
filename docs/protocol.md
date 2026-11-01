# AJAZZ MK87 键盘协议逆向笔记（VID 0x0C45 / PID 0x8047）

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

> 结论：**不需要抓包**。官方网页驱动 `https://ajazz.driveall.cn` 的 JS bundle 本身就包含完整协议实现，
> 已从中还原出帧格式、66 条命令、屏幕/灯效数据布局，并用纯 ctypes 直连 HID 在真机上验证了读写。
> 设备实测：**MK87（AJAZZ KEYBOARD），固件 1.19，240×135 TFT 屏，最多 140 帧动画，电量 50% 充电中**。

---

## 1. 设备接口（实测 `HidD_GetAttributes` / `HidP_GetCaps`）

Windows 上 MK87 是一个 USB 复合设备，暴露 8 个 HID 接口；与驱动相关的是下面两个：

| 接口 | usagePage | usage | InReportByteLength | OutReportByteLength | 用途 |
|---|---|---|---|---|---|
| MI_02 | 0xFF68 | 0x61 | 65 | 65 | **主协议通道**：设备信息/灯效/按键/宏/设置 |
| MI_03 | 0xFF67 | 0x61 | 65 | **4105** | **TFT 屏幕通道**：壁纸/GIF/内置动画 |
| MI_01 COL05 | 0xFFFF | 0x01 | 4 | 0 | 厂商小接口（只读，用途未明） |

- 两条通道的报文长度都**含 1 字节 report ID**（实际 report ID = 0），所以 MI_02 的 payload 是 64 字节，
  MI_03 的 payload 是 **4104 字节**（官方代码里写死的 `|| 4104` 就是这么来的）。
- 官方代码用 `usagePage === 65383 (0xFF67)` 查找 TFT 设备（`LX()`），主协议接口则由
  `navigator.hid.requestDevice({filters:[{vendorId,productId}]})` 取第一条可用设备。

## 2. 帧格式

请求报文（总长 = 接口 OutReportByteLength，首字节是 report ID，实际填 0）：

```
偏移  0     1     2        3      4      5     6      7     8...
     [ID]  AA    cmd      addrLo addrHi hdr5  last   hdr7  data...
```

- `cmd`：命令字，见命令表；
- `len`：本包**剩余内容长度**（不是本包 data 长度；最后一包填剩余字节数）；
- `addr`：数据偏移（大端存于 3、4 字节，小端数值）；
- `last`：最后一包标志（无自定义头时置 1 表示完整帧结束）；
- data 从偏移 8 开始。每包可携带 `payloadLen - 8` 字节（MI_02 = 56 字节/包）。

响应报文（input report）：先去掉首字节 report ID，再按下面格式解析：

```
偏移 0    1     2         3      4      5 6 7   8...
     55   cmd   lenOrType addrLo addrHi 0 0 1   data...
```

- 实测响应头为 `55 10 F9 00 00 00 01 00 ...`（cmd=0x10 时 lenOrType=0xF9），data 从偏移 8 开始；
- 等待响应时按 `cmd`（以及可选的 addr）匹配；超时 500ms、重发 3 次（官方 `NX()` 逻辑）。

## 3. 命令表

完整 66 条见 [command_enum.txt](command_enum.txt)（`docs/` 目录）。核心：

| 命令 | 值 | 说明 |
|---|---|---|
| GET_DEVICE_INFO | 16 (0x10) | 读设备信息，48 字节 |
| GET_GAME_MODE / SET_GAME_MODE | 17 / 33 | 游戏模式（MK87 大部分字段返回 0xFF=不支持） |
| GET_KEY / SET_KEY | 18 / 34 | 按键映射，512 字节 |
| GET_LED_EFFECT / SET_LED_EFFECT | 19 / 35 | 灯效，16 字节 |
| GET_CUSTOM_LED_DATA / SET_CUSTOM_LED_DATA | 20 / 36 | 自定义灯，512 字节 |
| GET_MACRO / SET_MACRO | 21 / 37 | 宏 |
| GET_FN_KEY / SET_FN_KEY | 22 / 38 | FN 层按键，512 字节 |
| SET_TEMPORARY_COMMAND_DATA | 52 (0x34) | 临时命令：屏幕时间、系统信息 |
| SET_TFT_MATERIAL | 77 (0x4D) | 上传 TFT 壁纸（MI_03） |
| SET_TFT_USER_ANIMATION | 80 (0x50) | 上传 TFT 动画（MI_03） |
| SET_TFT_BUILT_IN_INDEX | 81 (0x51) | 切换内置动画索引 |
| GET_DEVICE_NOTIFY / GET_24G_DISCONNECT_NOTIFY | 250 / 252 | 设备通知/2.4G 断开通知 |
| MAGNETIC_AXIS_* / SET_CALIBRATION_* / OTA_* | 23…134 | 磁轴、校准、OTA（MK87 不支持磁轴相关） |

## 4. GET_DEVICE_INFO（48 字节，实测值）

| 偏移 | 字段 | 实测 |
|---|---|---|
| 0 | romSize | 64 |
| 2..3 | macroSpaceSize | 3072 |
| 4..5 | vid | 0x0C45 |
| 6..7 | pid | 0x8047 |
| 8..9 | version（BCD） | 1.19 |
| 10..11 | sensor | 0xFFFF |
| 12..13 | manufacturer | 1 |
| 14..15 | product | 18 |
| 16 | workMode | 0 |
| 17 | batteryLevel | 50 |
| 18 | chargeStatus | 1 |
| 19 | currentProfile | 0 |
| 20..21 | axisInfo | 0 |
| 22..23 | **tftMaxFrames** | **140** |
| 24..25 | gifMaxFrames | 0 |
| 26..27 | ledMaxFrames | 0 |
| 28 | tftDirection | 0（255 = 无屏，官方据此隐藏 tft 页面） |
| 29 | rtPrecision | 0 |
| 30 | frameVersion | 0 |
| 31 | lightingVersion | 0 |
| 32 | firmwareStatus | 0 |
| 33 | maxProfile | 0 |
| 35 | **tftColorByteOrder** | 0（0=小端 RGB565，1=大端） |

## 5. 初始化流程（官方 `deviceInit`）

连上后依次 GET：`GET_DEVICE_INFO` → `GET_GAME_MODE` → `GET_KEY`(512) → `GET_FN_KEY`(512)
→ `GET_LED_EFFECT`(16) → `GET_CUSTOM_LED_DATA`(512) →（有灯箱/侧灯才读）→ `GET_DOT_MATRIX_CONFIG`(10)
→ `GET_MACRO`(400) → `GET_MAGNETIC_AXIS_RT`(1024) → `GET_TRIGGER_KEY`(512) → `GET_MAGNETIC_AXIS_DKS_DATA`(1024)
→（frameVersion==1 时读 SN）。**没有握手/激活命令**（COMMUNICATION_START 未被实际使用）。

## 6. 灯效 SET_LED_EFFECT（16 字节）

```
[0] 模式  [1]R [2]G [3]B  [4]=255  [5..7]副色  [8]颜色模式 [9]亮度(0-6?)
[10]速度  [11]方向 [12]效果类型  [14]=0xAA [15]=0x55
```
实测当前状态：模式 1、白色(255,255,255)、colorMode=1、亮度 5、速度 3；
写入同样数值后回读 `raw = 01 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55`，**写入通道已验证**。
（MK87 亮度范围 1–6、速度 1–6，来自键盘配置 `lightingConfig`。）

## 7. TFT 屏幕（240×135，RGB565）

壁纸 / 静态图 —— `SET_TFT_MATERIAL`，走 MI_03，自定义 8 字节头：

```
AA 4D seqLo seqHi totalLo totalHi matLo matHi | 数据...
```
- 每包数据 = 4104 - 8 = **4096 字节**；一整屏 240×135×2 = **64800 字节 → 16 包**
- `material_id = 0` 就是壁纸
- 像素格式 RGB565；`tftColorByteOrder`=0 → 每像素先低字节后高字节

GIF / 动画 —— `SET_TFT_USER_ANIMATION`，头为：

```
AA 50 seqLo seqHi totalLo totalHi 50 06 | 数据...
```
- 数据 = **256 字节帧延时表 + 各帧 RGB565 依次拼接**
- 帧延时表：`[0]=帧数`，`[i+1]=min(delay×5,255)`，`[len]=0`，其余填 255
- 最多 140 帧（tftMaxFrames）；240×135×2×140 ≈ 9 MB，官方按 4096/包上传
- 帧数据可选旋转/镜像（官方 `NV()`：0/90/180/270 + flip，按像素重排）

内置动画 —— `SET_TFT_BUILT_IN_INDEX`，1 字节索引。

屏幕时间 —— `SET_TEMPORARY_COMMAND_DATA`，payload 10 字节：
`[0..2]=5A 01 5A, [3]=年%100, [4]=月, [5]=日, [6]=时, [7]=分, [8]=秒, [9]=星期(0=周日)`。

屏幕系统信息 —— `SET_TEMPORARY_COMMAND_DATA`，payload 24 字节：
`[6]=0x5A, [12]=CPU占用, [13]=CPU温度(有符号), [14]=GPU占用, [15]=GPU温度, [16]=当前气温, [17]=最高, [18]=最低, [19]=天气代码, [20]=湿度`。

## 8. 其他结构（来自官方代码，未在本机验证）

- `SET_KEY` / `SET_FN_KEY`：512 字节 = 128 键 × 4 字节 `[pageType, param1, param2, param3]`
- `SET_MACRO`：前 400 字节是 100 个宏的偏移表，之后是宏动作数据（每动作 4 字节：delay,delayHi,keyCode,flags）
- `SET_MAGNETIC_AXIS_RT` / `SET_MAGNETIC_AXIS_DKS_DATA`：1024 字节（磁轴键盘用，MK87 不适用）
- `SET_CUSTOM_LED_DATA`：512 字节 = 128 灯 × 4 字节 `[灯号, R, G, B]`
- 帧层还有 CRC-16/CCITT-FALSE（poly 0x1021, init 0xFFFF，官方 `RX()`），本机这些命令未用到

## 9. 本仓库文件

```
Documents/ajazz-re/
├─ assets/                     官方网页驱动 JS（静态分析原料）
├─ docs/
│  ├─ protocol.md              本文件
│  ├─ protocol_commands.js     66 个命令函数的还原源码（已格式化）
│  ├─ infra.js                 帧层函数 PX/NX/IX/FX/RX 与设备过滤器表
│  ├─ command_enum.txt         命令字表
│  └─ device_config_32839.json MK87 的官方键盘配置（键位/路由/屏幕参数）
├─ probe/
│  ├─ ajazz.py                 原生 HID 协议客户端（Python，纯 ctypes，无依赖*）
│  ├─ hid_probe.py / hid_probe2.py / hid_probe3.py   接口枚举与探测脚本
├─ capture/                    Chrome CDP WebHID 抓包工具（半自动模式，备用）
└─ extract.js                  从 bundle 提取协议函数的脚本
```
\* 仅 `screen`/`gif` 子命令需要 Pillow（当前环境已内置）。

## 10. 使用

```powershell
$py = "C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py Documents\ajazz-re\probe\ajazz.py info              # 设备信息/游戏模式/灯效
& $py Documents\ajazz-re\probe\ajazz.py light 1 0 128 255 # 设灯效（模式1，蓝色，亮度5）
& $py Documents\ajazz-re\probe\ajazz.py screen 图片.png    # 上传壁纸到 240x135 屏
& $py Documents\ajazz-re\probe\ajazz.py gif 动画.gif       # 上传动画（≤140 帧）
& $py Documents\ajazz-re\probe\ajazz.py time              # 同步屏幕时间
& $py Documents\ajazz-re\probe\ajazz.py builtin 1         # 切内置动画
& $py Documents\ajazz-re\probe\ajazz.py raw AA 10 30 00 00 00 00 01   # 原始帧
```

## 11. 验证状态

- ✅ 接口枚举 / 设备信息读取（真机）
- ✅ GET_GAME_MODE / GET_LED_EFFECT 读取（真机）
- ✅ SET_LED_EFFECT 写入 + 回读确认（真机，未改变可见状态）
- ⬜ TFT 壁纸 / 动画上传（代码已实现，待真机验证；会覆盖当前屏幕内容）

---

## 10. 真机实测补充（2026-11-01，详见 [TEST-REPORT.md](TEST-REPORT.md)）

- **写命令 ACK = 原样回显所发 payload**（含 TFT 上传的 4096 字节数据包）；
  `SET_TFT_MATERIAL(0x4D)` 与 `SET_TFT_USER_ANIMATION(0x50)` 的逐包 ACK 都是 **0x41**。
- `GET_LED_DATA(0x32)` 写入的是**逐键 LED 缓冲**：发帧后 `GET_ALL_LIGHTS_RGB(0x33)` 可读回帧颜色；
  0x32 的响应数据是「回显请求数据」，不是设备状态。
- 帧流展示前必须 `SET_LED_EFFECT` 切到 **mode 20/21/128**；停帧约 5s 回落。
- 常规写包耗时：主协议 64B 包约 1–2 ms；TFT 4105B 包约 65 ms（USB FS 64B/ms 上限，实测吞吐约 63 KB/s）。
- 2.4G：协议口为 usagePage **0xFF60**（33B 报文）；0xFF59（65B）无响应且不在官方过滤器表。
