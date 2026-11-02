# AJAZZ MK87 · 逆向工程 + 跨平台配置工具

[English](README.md) · **简体中文**

**MK87 Studio** 是 AJAZZ MK87 机械键盘的非官方**跨平台配置工具**（Windows + Linux），基于对其
USB / 2.4G 协议的完整逆向实现，全部功能**离线本地运行**。

- **设备**：USB `VID 0x0C45 / PID 0x8047`；2.4G 接收器 `VID 0x0C45 / PID 0xFEFE`
- **官方网页驱动**（已逆向）：`https://ajazz.driveall.cn`
- **全程本地**：不访问外网、不上传数据、不依赖官方驱动
- **最新版本**：[v0.1.2](https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest)

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

## v0.1.2 更新

- **音乐律动 · 官方方案** —— 音乐页新增两种方案：**官方方案（默认）**使用与官方 v1 插件完全相同的设置项
  （显示模式 12 种 / 背景模式 11 种 / 背景亮度 / 振幅），并由官方渲染器代码绘制；**当前方案**保留本工具
  自己的参数与本地预览动画。
- **热切换** —— 播放中切换方案、显示模式、背景模式或拖动滑块立即生效，无需停止/重新开始。
- **官方 12 个渲染器中 11 个已逐行移植**（模式 1、4、13–22），包括模式 22 的官方内置双心坐标表；
  100 屏光联动由官方 Music.exe 计算，回落「随曲起舞」。
- 双语 README（英文默认 + 简体中文）内嵌截图；MIT 许可；修复英文界面 `<html lang>` 首屏问题。

## 功能

- **灯光效果** —— 19 种预设 + 颜色 / 亮度(1–6) / 速度(1–6) / 方向；RGB 或单色。
- **逐键灯效** —— 87 键画布：画笔、擦除、填充、吸管、拖拽连续上色、预设涂色；写入固件
  mode 20 / 21 / 128 共用的自定义灯表。
- **TFT 屏幕（240×135）** —— 图片 / GIF / 动态 WebP / APNG → 压缩管线（降采样、抽帧、去重、
  RGB565 抖动）→ 动画上传（≤140 帧）、时间同步、一键恢复官方默认动画。
- **宏** —— 100 槽 / 3072B 编辑器：录键、延迟、按下/抬起、重复 N 次、再按结束。
- **改键 / FN** —— 87 键主层 + FN 层：HID 键、组合键、宏、固件 FUNC 动作、禁用、恢复默认，
  实时预览 4B 编码；2.4G 下 FN 层只读。
- **音乐律动（仅 USB）** —— 两种方案：**官方方案**（与官方 v1 插件完全相同的设置项：显示模式 12 种 /
  背景模式 11 种 / 背景亮度 / 振幅，播放中热切换）与**当前方案**（本工具的模式 / 帧率 / 灵敏度）
  → 20fps 逐键帧流。官方 12 个渲染器中 11 个（1/4/13–22）已逐行移植；100 屏光联动由 Music.exe 计算，
  回落「随曲起舞」。
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
| 逐键实时帧流（20fps，音乐律动 / AI 灯效） | ✅ 仅 USB（2.4G 固件不支持） |
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
