# AJAZZ MK87 · 逆向工程 + 跨平台配置工具

[English](README.md) · **简体中文**

**MK87 Studio** 是 AJAZZ MK87 机械键盘的非官方**跨平台配置工具**（Windows + Linux），基于对其
USB / 2.4G 协议的完整逆向实现，全部功能**离线本地运行**。

- **设备**：USB `VID 0x0C45 / PID 0x8047`；2.4G 接收器 `VID 0x0C45 / PID 0xFEFE`
- **官方网页驱动**（已逆向）：`https://ajazz.driveall.cn`
- **全程本地**：不访问外网、不上传数据、不依赖官方驱动
- **最新版本**：[v0.1.3](https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest)

## 界面截图

| 灯光效果（浅色 · 中文） | 深色界面（English） |
|---|---|
| <img src="driver/docs/screenshots/ui-light-zh.png" width="480" alt="灯光效果页，浅色主题"> | <img src="driver/docs/screenshots/ui-dark-en.png" width="480" alt="灯光效果页，深色主题"> |

| 音乐律动 · 当前方案 | 音乐律动 · 官方方案 |
|---|---|
| <img src="capture/ui_music_preview/03-music-current-running.png" width="480" alt="音乐律动，当前方案"> | <img src="capture/ui_music_preview/02-music-official-running.png" width="480" alt="音乐律动，官方方案"> |

| TFT 屏幕（240×135） | 日志与诊断 |
|---|---|
| <img src="driver/docs/screenshots/tft-upload-limits.png" width="480" alt="TFT 屏幕上传"> | <img src="driver/docs/screenshots/logs-settings.png" width="480" alt="日志与诊断"> |

> 音乐律动两张为无硬件演示模式截图，其余为真机界面。

## 下载

👉 **https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest**

| 平台 | 文件 | 说明 |
|---|---|---|
| Windows | `MK87Studio-*-win64-portable.zip` | 免安装：解压后双击 `MK87Config.exe` |
| Windows | `MK87Studio-*-win64-setup.exe` | 安装版：快捷方式、可选开机自启 |
| Linux · Debian/Ubuntu | `mk87_*_amd64.deb` | `sudo apt install ./mk87_*.deb` |
| Linux · Fedora/openSUSE | `mk87-*.x86_64.rpm` | `sudo dnf install ./mk87-*.rpm` |

Linux 包内已包含 udev 规则（免 root 访问 HID），安装后请重新插拔键盘。
发布由 GitHub Actions 自动构建，附件含 `SHA256SUMS.txt` 校验值。

## v0.1.3 更新

- **音乐律动 · 官方方案对齐官方 v1 真值** —— 显示模式下拉补回至 **21 项**：官方 v1 UI 原有的 12 项，
  加上之前逆向出、但官方 UI 没暴露的 9 项（14–22）。模式 4「曲率频阶」按官方 MusicPlug.exe 重新采样
  重写：17 列频谱柱、底部对齐（1200/1200 帧）、左低右高（对数，约 110Hz–12kHz）、径向色相以 `(2,8)`
  为原点、整块调色板约 275°/s 旋转。100 屏光联动仍回落「随曲起舞」。
- **LED 颜色（本工具自研增强）** —— 第三个下拉提供 **默认（官方配色）+ 9 套预设**：冰蓝 `#00E5FF`、
  紫罗兰 `#B36CFF`、热粉 `#FF2E88`、青柠 `#A8FF3E`、暖橙 `#FF6A00`，以及樱花
  `#FF7AB6→#B36CFF`、极光 `#3EFF9A→#00E5FF→#7A5CFF`、日落 `#FFC400→#FF6A00→#FF2E88`、
  冰火 `#00E5FF→#FEFEFE→#FF6A00` 渐变。只作用于动态多色模式 **1/2/4/5/13**，按原调色板位置/角度/
  相位在新渐变上采样并保留原有动画；纯色模式 6–11 与背景完全不受影响；`default` 与 v0.1.2 逐字节一致
  （220 组合快照回归）。
- **原生 20 / 60 / 66fps，默认 66** —— 官方 v1 实测 530.5 包/s ÷ 8 包/帧 ≈ **66.3fps**，官方方案默认
  66fps（当前方案仍为 15/20/30）。≤30fps 逐包 ACK；≥60fps 连写 7 包 + ACK 清道夫线程异步读回包
  （同步帧末 drain 实测 19.8ms/帧 → 只有 45.96fps；异步后 8.85ms/帧 → 66fps）。动画按实际帧间隔归一
  （dt_scale），切帧率观感速度不变。真机（USB fw1.19）66fps 连续 100s 实测 **65.78–65.89fps**（0 错误）；
  60fps=60.06、20fps=19.97；21 个模式 × 10 种颜色逐个切换 0 错误；停止后灯效恢复原值
  （mode=11、brightness=6、speed=3）。页面显示实测 fps，status 契约 `fps`=实测 float|null、
  `targetFps`=配置 int，WS 预览限速 30Hz。
- **电量 / 灯效健壮性** —— 电量、充电、工作模式每次读取都刷新并记日志（连接日志带
  battery/charging/workMode/transport，连接后延迟 2s 重读）；新增 2.4G 电量读取路径（cmd `0x37` 首包 +
  `GET_ALL_LIGHTS_RGB_24G` 回包），连续失败 3 次熔断 5 分钟并回退 USB 路径。灯效卡死根因修复：
  v0.1.2 音乐启动会写 LED mode **128**，进程被关机杀死时恢复逻辑没跑，fw1.19 把 128 固化成逐键自定义表
  （回读 mode=0）。现在音乐/帧流入口**绝不写 128**，帧模式固定写 20/21 并回读校验；恢复快照前校验
  mode，0/非法一律不写；退出顺序改为「停音乐并等恢复 → 按键测试 → 关设备管理器」；`GET /api/lighting` 在 mode 回读 0 时
  用 `GET_ALL_LIGHTS_RGB` 判断是否自定义并标 `isCustom`。（「重启后像游戏模式」与上条同源；全量日志证实
  工具从未写过 game-mode，0 条 cmd `0x21`。）
- **质量** —— 152 个单元测试全绿；无头 Chrome UI 自检 17 项 PASS（21 模式 / 3 下拉 / 10 颜色 /
  3 帧率档、热切换、英文界面无中文残留）。

## 功能

- **灯光效果** —— 19 种预设 + 颜色 / 亮度(1–6) / 速度(1–6) / 方向；RGB 或单色。
- **逐键灯效** —— 87 键画布：画笔、擦除、填充、吸管、拖拽连续上色、预设涂色；写入固件
  mode 20 / 21 / 128 共用的自定义灯表。
- **TFT 屏幕（240×135）** —— 图片 / GIF / 动态 WebP / APNG → 压缩管线（降采样、抽帧、去重、
  RGB565 抖动）→ 动画上传（≤140 帧）、时间同步、一键恢复官方默认动画。
- **宏** —— 100 槽 / 3072B 编辑器：录键、延迟、按下/抬起、重复 N 次、再按结束。
- **改键 / FN** —— 87 键主层 + FN 层：HID 键、组合键、宏、固件 FUNC 动作、禁用、恢复默认，
  实时预览 4B 编码；2.4G 下 FN 层只读。
- **音乐律动（仅 USB）** —— 两种方案：**官方方案**（21 种显示模式：官方 v1 的 12 项 + 补回的 14–22
  共 9 项 / 背景模式 11 种 / 背景亮度 / 振幅 / LED 颜色，播放中热切换）与**当前方案**（本工具的模式 /
  帧率 / 灵敏度）→ 原生 **20/60/66fps** 逐键帧流（官方方案默认 66；官方 v1 实测约 66.3fps）。模式 4
  为 17 列底部对齐频谱柱；LED 颜色覆盖（默认 + 9 套预设）只重着色 1/2/4/5/13。100 屏光联动由
  Music.exe 计算，回落「随曲起舞」。
- **无线** —— 2.4G 状态、电量、休眠时间（0/1/10/20/30 分钟）、断连 / 唤醒通知日志。
- **按键测试** —— OS 级捕获（Windows RawInput / Linux evdev），87 键三态高亮、事件日志、统计。
- **设备信息** —— 固件 / 电量 / 能力矩阵、游戏模式字段、时间同步、原始命令控制台。
- **备份恢复** —— 全量 JSON 导出 / 导入，恢复前二次确认。
- **设置** —— 浅色 / 深色 / 跟随系统、简体中文 / English 即时切换、开机自启、干净退出。
- **其它** —— 系统托盘、单实例、完整日志 + 一键导出诊断包。

## 设备能力（真机实测）

| 能力 | 状态 |
|---|---|
| 87 键改键（HID / 组合键 / 宏 / FN / 媒体键） | ✅ 可读写 |
| FN 层改键（26 条默认动作） | ✅ 可读写 |
| 19 种灯效 + 亮度 / 速度 + 逐键自定义灯 | ✅ |
| 逐键实时帧流（原生 20/60/66fps，默认 66；官方 v1 约 66.3fps；音乐律动 / AI 灯效） | ✅ 仅 USB（2.4G 固件不支持） |
| 宏：100 槽 / 3072B，格式完全还原 | ✅ 可读写 |
| TFT 240×135 自定义动画（≤140 帧，约 63 KB/s） | ✅ 可上传播放 |
| 屏幕时间同步 | ✅ |
| 游戏模式 / 休眠设置、电池 / 固件信息 | ✅ 部分字段 |
| 2.4G 无线（配置与 USB 共享，矩阵一致）+ 断连 / 唤醒通知 | ✅ |
| 磁轴、灯效 GIF、板载多 Profile、屏幕内置页、12/24h 显示 | ⛔ 固件 / 硬件不支持 |

## 仓库内容

1. **逆向文档（`docs/`）** —— 协议帧格式、66 条命令表、按键 / 宏二进制格式、19 种灯效参数、
   逐键 LED 帧流、TFT 屏幕（240×135 动画 / 时间同步）、音乐律动、2.4G 无线（休眠 / 唤醒通知）、
   官方 i18n 文案与未知项清单。
2. **参考实现与取证脚本（`scripts/`、`probe/`、`capture/`）** —— 带自检断言的编解码参考实现、
   直接驱动设备的 Python HID 客户端、Chrome CDP WebHID 抓包工具。
3. **跨平台工具（`driver/`）** —— 已发布的 Windows + Linux 应用，覆盖上述全部已验证能力。

```
docs/      逆向文档与实测数据（JSON 证据）
scripts/   参考实现与提取脚本（Node/Python）
probe/     真机测试脚本（Python + hidapi）
capture/   Chrome CDP WebHID 抓包与录制证据
assets/    官方网页驱动 bundle 提取物（分析原料）
driver/    跨平台配置工具（已发布）
```

## 逆向文档

- [docs/FEATURES.md](docs/FEATURES.md) —— 功能总表与能力边界（先看这个）
- [docs/TEST-REPORT.md](docs/TEST-REPORT.md) —— 真机测试报告（Phase 0–7 与证据）
- [docs/protocol.md](docs/protocol.md) —— 帧格式与命令表
- [docs/deepdive-mk87.md](docs/deepdive-mk87.md) —— 设备信息 / 游戏模式 / 屏幕时间
- [docs/keymap.md](docs/keymap.md) —— 按键映射与宏二进制格式（§16）
- [docs/lighting.md](docs/lighting.md) —— 灯效协议
- [docs/tft-page.md](docs/tft-page.md) —— TFT 屏幕协议
- [docs/music-rhythm.md](docs/music-rhythm.md) —— 音乐律动与逐键帧流
- [docs/wireless-profiles-led-animation.md](docs/wireless-profiles-led-animation.md) —— 2.4G 无线
- [docs/key-events.md](docs/key-events.md) —— 按键事件捕获（厂商协议无事件帧，需 RawInput/evdev）
- [docs/i18n-and-unknowns.md](docs/i18n-and-unknowns.md) —— 官方文案与未决项
- [driver/README.md](driver/README.md) —— 工具本身的说明

## 从源码构建与运行

```bash
git clone https://github.com/w32394045-dotcom/ajazz-mk87.git
cd ajazz-mk87/driver
python -m venv .venv

# Windows
.venv\Scripts\pip install -r packaging\requirements.txt
.venv\Scripts\python shell.py      # 原生窗口（推荐）
# .venv\Scripts\python run.py      # 浏览器模式

# Linux
.venv/bin/pip install -r packaging/requirements.txt
.venv/bin/python shell.py           # 原生窗口（需 Qt WebEngine）
# .venv/bin/python run.py           # 浏览器模式
```

## 许可证

MIT License，见 [LICENSE](LICENSE)。

> 注意：`assets/`、`tools/Music.exe`、`docs/` 中的官方 bundle 片段等原厂提取物版权归原厂所有，
> **不在 MIT 授权范围内**。

## 免责声明

非官方逆向工程，仅用于研究与个人使用，与 AJAZZ 官方无关。设备固件 / 协议可能随版本变化；
写操作（改键、宏、灯效、屏幕内容）前请自行备份。
