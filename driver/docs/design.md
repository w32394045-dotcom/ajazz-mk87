# MK87 跨平台配置工具 —— 架构与接口契约 v1

> 目标：把 AJAZZ MK87 已验证的全部能力做成一个 **Linux + Windows** 双平台图形工具（本地 Web UI）。
> 设备：USB `0C45:8047`、2.4G 接收器 `0C45:FEFE`。协议见 `docs/protocol.md`，能力边界见 `docs/FEATURES.md`。
> GUI 主题：**浅色（白色主题）/ 深色（黑色主题）** 两套，可跟随系统。

## 1. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 设备访问 | **hidapi**（PyPI `hidapi`） | Win/Linux 同 API；官方 WebHID 的限制（如 0xFF59 接口、唤醒帧 report ID 5、4104B 长报文）都能绕开 |
| 后端 | **Python 3.10+ + FastAPI + Uvicorn** | 与逆向脚本同语言，便于复用；WebSocket 推送实时状态 |
| 前端 | **原生 HTML/CSS/JS（无构建步骤）** | 零 npm 依赖、易维护、主题切换简单；两种主题共一套 DOM |
| 图像 | Pillow + numpy | TFT 240×135 帧转换/缩放 |
| 音频 | Windows: `soundcard`(WASAPI loopback)；Linux: `sounddevice`/PulseAudio monitor | 音乐律动需要捕获系统输出 |
| 按键捕获 | Windows: RawInput(ctypes)；Linux: evdev(`/dev/input/event*`) | 厂商协议无按键事件帧（见 docs/key-events.md） |
| 打包 | PyInstaller（单文件/单目录）；Linux 另附 .desktop + udev 规则 | Win exe / Linux 二进制 |

运行形态：`mk87`（或 `python -m mk87`）启动本地服务 `127.0.0.1:8477` 并自动打开浏览器；
也可 `mk87 --mock` 用模拟设备开发 UI，`mk87 --no-browser` 只起服务，`mk87 --port N` 改端口。

## 2. 目录结构

```
driver/
├── mk87lib/            # 协议核心库（纯 Python，可单独 import）
│   ├── const.py        # VID/PID、HID usagePage、report 长度、CMD 枚举、模式枚举
│   ├── transport.py    # hidapi 封装：枚举/打开/读写/超时/重连（Win+Linux）
│   ├── protocol.py     # AA/55 帧构造解析、请求-响应、ACK 匹配、分包
│   ├── device.py       # MK87Device：连接(USB/2.4G)、信息、时间同步、通知线程
│   ├── keymap.py       # 4B 按键编码、动作目录、布局、读写主层/FN、默认矩阵
│   ├── macro.py        # 400B 目录 + 宏块编解码、读写
│   ├── lighting.py     # 灯效参数/模式元数据/逐键自定义灯/0x32 帧流
│   ├── tft.py          # 240×135 帧转换、0x4D/0x50 上传、恢复默认动画
│   ├── music.py        # 音频采集→FFT→逐键帧→0x32 流（USB only）
│   ├── wireless.py     # 2.4G 身份/休眠设置/通知解析
│   ├── keyscan.py      # RawInput(Windows) / evdev(Linux) 按键事件
│   ├── backup.py       # 全量状态备份/恢复
│   ├── mock.py         # 模拟设备（--mock，供 UI 开发/演示）
│   └── errors.py
├── server/
│   ├── app.py          # FastAPI 应用、REST 路由、/ws
│   ├── state.py        # DeviceManager 单例、锁、后台任务/进度/事件总线
│   └── schemas.py      # pydantic 模型
├── web/                # 前端（原生 HTML/CSS/JS）
│   ├── index.html
│   ├── css/app.css     # 主题变量（light/dark）
│   ├── js/api.js       # fetch + WebSocket 封装、事件总线
│   ├── js/app.js       # 路由/导航/主题/语言
│   ├── js/pages/*.js   # 各页面
│   ├── js/components/*.js # 键盘图、取色器、对话框、进度条、toast
│   └── assets/         # 图标、默认动画数据（可选）
├── data/default_animation.json  # 官方默认 135 帧动画（恢复默认用）
├── cli.py              # mk87ctl 命令行（脚本化操作）
├── __main__.py         # python -m mk87
├── packaging/          # pyinstaller.spec、build-win.ps1、build-linux.sh、udev 规则
└── tests/              # 协议/编解码单元测试（离线）+ 真机冒烟脚本
```

## 3. 后端线程模型

- FastAPI 事件循环只做 I/O；**所有设备操作在 worker 线程**执行（`def` 端点自动进线程池），全局 `RLock` 串行化同一设备的读写。
- **通知监听线程**：常驻读通知通道（USB: MI_02 + 0xFFFF reportID5；2.4G: 0xFF60），解析 `55 FC 04/05/06`、`A6 FF 01`，推给事件总线。
- **流任务**（音乐/逐键帧流/TFT 上传）各自独立线程 + 独立接口句柄（实测同接口并发读写会冲突，见 TEST-REPORT）。
- 事件总线 → `asyncio.Queue` → WebSocket 广播；前端也可轮询 `/api/status`。
- 断线/睡眠：状态机 `DISCONNECTED → CONNECTING → READY`；后台每 2s 重扫，重连后自动重放"待应用"配置（可选）。

## 4. REST 接口契约（v1）

约定：`Content-Type: application/json`；错误 `HTTP 4xx/5xx {"error": "code", "message": "..."}`。
所有写操作返回 `{"ok": true}` 或操作结果。`/api/status` 是唯一高频轮询接口（无副作用）。

### 4.1 设备/状态

| 方法 | 路径 | 说明 / 返回 |
|---|---|---|
| GET | `/api/status` | 连接状态、传输方式、设备信息、电量、能力、冲突提示 |
| POST | `/api/device/scan` | 重新扫描/连接，返回 status |
| GET | `/api/device/info` | `GET_DEVICE_INFO` 解析结果 + 游戏模式原始 56B |
| GET | `/api/device/game-mode` | `{raw:[56], fields:{sleepTime, displayTime, ...}}` |
| PUT | `/api/device/game-mode` | `{fields:{...}}` 合并写回 56B |
| POST | `/api/device/time-sync` | 把主机时间写入屏幕（0x34 10B 帧） |
| POST | `/api/device/factory-reset` | `{confirm:true}` 恢复出厂（0x0F） |
| POST | `/api/device/raw` | `{data:[..], timeout:0.5, expect:true}` 高级调试：发原始帧 |

`GET /api/status` 返回示例：
```json
{
  "connected": true, "mock": false, "transport": "usb",
  "device": {"vid": 3141, "pid": 32839, "product": "AJAZZ KEYBOARD",
             "manufacturer": "SONiX", "firmware": "1.19", "serial": "..."},
  "battery": {"percent": 76, "charging": true},
  "caps": {"keyCount": 87, "tft": true, "tftMaxFrames": 140, "ledMaxFrames": 0,
            "maxProfile": 0, "music": true, "wireless": false},
  "wireless": null,
  "conflicts": [],
  "recentNotifications": [{"ts": 1699999999, "kind": "wake"}]
}
```
`transport`: `"usb" | "2.4g" | "none"`。`conflicts` 为字符串数组（如 USB+dongle 同插资源冲突的提示）。

### 4.2 改键 / FN

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/keymap/layout` | 87 键布局：`[{slot,row,x,w,name,label,keyCode}]` + 空槽/物理 LED 槽说明 |
| GET | `/api/keymap` | `{normal:{slot:action}, fn:{id:action}}`（action 见 4.6） |
| PUT | `/api/keymap/normal` | `{slots:{slot:action}}` 只写变更项 |
| PUT | `/api/keymap/fn` | `{slots:{id:action}}` |
| GET | `/api/keymap/defaults` | 从设备读默认矩阵（普通+FN） |
| POST | `/api/keymap/restore` | `{layer:"normal"|"fn"}` 写 0 恢复默认 |
| GET | `/api/keymap/actions` | 动作目录：`{keyboard:[], consumer:[], func:[], mouse:[], macros:[], pageTypes:[]}` |

### 4.3 灯效 / 逐键灯

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/lighting` | 当前灯效参数 `{mode,brightness,speed,direction,colorMode,color:{r,g,b},raw}` |
| PUT | `/api/lighting` | 设置灯效（同字段，部分字段可缺省） |
| GET | `/api/lighting/modes` | 19 种模式的 UI 元数据（id/名称/是否支持颜色/方向/速度） |
| GET | `/api/lighting/custom` | 逐键自定义灯表 `{colors:{slot:[r,g,b]}, count}` |
| PUT | `/api/lighting/custom` | `{colors:{slot:[r,g,b]}, apply:true}` 写入并切到自定义模式 |
| POST | `/api/lighting/frames/start` | 开始逐键帧流 `{fps:20}`（自定义动画/AI 灯效用） |
| POST | `/api/lighting/frames/push` | 推一帧 `{keys:{slot:[r,g,b]}}`（可选：前端做效果） |
| POST | `/api/lighting/frames/stop` | 停止帧流（~5s 后回落） |
| GET | `/api/lighting/frames/status` | `{running,fps,frames}` |

### 4.4 宏

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/macros` | `{capacity:3072, used:0, slots:[{slot,actions:[{delay,type,press,usage,keyName}]}]}` |
| PUT | `/api/macros` | `{slots:[...]}` 全表写入（两次 SET_MACRO） |
| DELETE | `/api/macros/{slot}` | 清空某槽 |

### 4.5 屏幕 TFT

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tft` | `{width:240,height:135,maxFrames:140,pixelFormat:"rgb565"}` |
| POST | `/api/tft/upload` | `{mode:"static"|"animation", fps:10, frames:["<base64 RGB565 64800B>"]}` 异步任务，进度走 WS；返回 `{job:"tft"}` |
| POST | `/api/tft/default` | 恢复官方默认 135 帧动画（异步任务） |
| GET | `/api/tft/job` | `{running,phase:"upload"|"done", sent,total,pct,error}` |
| POST | `/api/tft/cancel` | 取消上传 |

前端负责把用户选的图片/GIF **在 `<canvas>` 里转成 240×135 RGB565**（base64），后端只管可靠上传；
后端 `tft.py` 提供同样的转换函数供 CLI 用。

### 4.6 动作（action）数据模型

```json
{"type":"key",      "usage": 4,          "name":"A"}              // HID 主键盘 usage
{"type":"consumer", "usage": 233,        "name":"MediaPlay"}      // 多媒体
{"type":"combo",    "keys":[224,4]}                               // 组合键 CB
{"type":"macro",    "slot": 0}                                    // 宏引用
{"type":"fn",       "id": 1, "name":"亮度+"}                      // FN 动作
{"type":"mouse",    "button": 1}                                  // 鼠标键（如支持）
{"type":"disabled"}                                               // 禁用
{"type":"default"}                                                // 写 0 = 出厂默认
```
设备层最终编码为 4 字节（见 `spec-keymap.md`）。

### 4.7 音乐律动（USB only）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/music/devices` | 音频输出设备列表（loopback 候选） |
| POST | `/api/music/start` | `{deviceId, sensitivity:1.0, style:"spectrum"|"pulse", fps:20}` |
| POST | `/api/music/stop` | 停止 |
| GET | `/api/music/status` | `{running,fps,level,device}` |

### 4.8 无线 / 按键测试 / 备份 / 设置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/wireless` | `{transport:"2.4g", connected, sleepTime, identity:{manufacturer,product,workMode}}` |
| PUT | `/api/wireless` | `{sleepTime:1}`（单位分钟，0=关，1/10/20/30） |
| POST | `/api/keytest/start` | 开始 OS 级按键捕获（RawInput/evdev） |
| POST | `/api/keytest/stop` | 停止 |
| GET | `/api/keytest/status` | `{running,backend:"rawinput"|"evdev",events:[...]}` |
| GET | `/api/backup` | 全量备份 JSON（keymap/fn/macro/lighting/custom/device info/时间） |
| POST | `/api/backup/restore` | `{backup:<obj>, confirm:true}` |
| GET | `/api/settings` | `{theme:"light"|"dark"|"auto", language:"zh"|"en"}` |
| PUT | `/api/settings` | 更新设置（服务端持久化到用户配置目录） |

### 4.9 WebSocket `/ws`

服务端 → 客户端事件（`type` 字段）：
```json
{"type":"status", "data": <status obj>}          // 连接/断开/电量变化
{"type":"notification", "data":{"kind":"sleep"|"wake"|"disconnect","ts":...}}
{"type":"battery", "data":{"percent":76,"charging":true}}
{"type":"progress", "data":{"job":"tft","phase":"upload","sent":120,"total":135,"pct":88}}
{"type":"job", "data":{"job":"tft","state":"done"|"error","error":null}}
{"type":"keyevent", "data":{"vkey":65,"name":"A","down":true,"ts":...}}
{"type":"music_level", "data":{"level":0.6,"bands":[...]}}   // 节流 10fps
{"type":"toast", "data":{"level":"info"|"warn"|"error","message":"..."}}
{"type":"log", "data":{"line":"..."}}             // 调试控制台
```

## 5. 前端要求

- **主题**：一套 DOM，CSS 变量切换 `data-theme="light"|"dark"`；默认跟随系统（`prefers-color-scheme`），可手动固定；
  设置持久化到 localStorage + 服务端 `/api/settings`。浅色主题=白色底/深色文字，深色主题=黑灰底/浅色文字。
- **语言**：中文界面，预留英文 i18n（键值对 dictionary）。
- **导航页**（左侧或顶部）：灯光 / 逐键灯效 / 屏幕 / 宏 / 改键 / FN / 音乐律动 / 无线 / 按键测试 / 设备信息 / 备份恢复 / 设置。
- **键盘组件**（`components/keyboard.js`）：87 键 SVG/绝对定位布局，支持选中、多选、逐键上色、按下高亮（按键测试复用）。
- **状态栏**：连接方式（USB/2.4G）、电量、固件、设备名；断连时全局提示 + 重连按钮。
- **所有危险操作**（恢复出厂、写宏、恢复备份）二次确认对话框。
- **无外网依赖**：所有资源本地，离线可用。

## 6. 平台差异与权限

- **Windows**：hidapi 直接可用（HID 无需管理员）。RawInput 无需提权。音频 loopback 用 `soundcard`。
  仅"设备复位/冲突修复"类操作才需要管理员（本工具不做自动修复，只提示，见下）。
- **Linux**：需要 hidraw 权限 —— 提供 `packaging/udev/99-ajazz-mk87.rules`（`MODE="0666"` 或 `TAG+="uaccess"`）
  与安装脚本；或加入 `plugdev` 组。evdev 读取需要 `input` 组。音频需要 PulseAudio/PipeWire monitor。
- **已知硬件冲突**（不影响工具功能）：2.4G 接收器与键盘 USB 同接一个 USB2.0 Hub 时，Windows 会给后枚举的
  复合设备 `0xC000009A`（资源不足）→ 工具在 `conflicts` 中提示"请拔掉 2.4G 接收器以使用 USB 模式"。
  （`docs/TEST-REPORT.md` §8.7；软件禁用方案不可行，实测 CR_NOT_DISABLEABLE。）

## 7. 里程碑

- **M1 核心库**：transport/protocol/device/keymap/macro/lighting/tft/wireless + 单元测试 + mock 设备
- **M2 服务端**：FastAPI 全套 REST + WS + 任务/进度 + 冲突检测
- **M3 前端**：主题框架 + 12 个页面 + 键盘组件
- **M4 打包**：Windows exe、Linux 二进制/deb/AppImage + udev + 文档
- **M5 真机回归**：USB 与 2.4G 两种连接下逐页验证；恢复默认；与 `device_dump_pre_test.json` 对比

## 8. 文件所有权（多人协作时）

- `mk87lib/`、`server/`、`cli.py`、`packaging/`、`tests/`：Lead
- `web/`：前端负责人（独立文件域，不碰 Python）
- 接口变更只能改本文档 + `server/schemas.py`，并同步通知
