# AJAZZ MK87 逆向工程 + 跨平台配置工具

> 目标设备：**AJAZZ MK87**（USB `VID 0x0C45 / PID 0x8047`，2.4G 接收器 `0x0C45 / 0xFEFE`）
> 官方网页驱动：`https://ajazz.driveall.cn`
> 状态：**协议逆向完成（静态 + 真机验证全部收口）**，进入自有工具/驱动实现阶段。

## 下载（成品软件）

👉 **https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest**

| 平台 | 文件 | 说明 |
|---|---|---|
| Windows | `MK87Studio-*-win64-portable.zip` | 免安装，解压双击 `MK87Config.exe` |
| Windows | `MK87Studio-*-win64-setup.exe` | 安装版（快捷方式 / 可选开机自启） |
| Linux | `mk87_*_amd64.deb` | `sudo apt install ./mk87_*_amd64.deb` |
| Linux | `mk87-*.x86_64.rpm` | `sudo dnf install ./mk87-*.x86_64.rpm` |

Linux 包内含 udev 规则（免 root 访问 HID），装完重新插拔键盘即可。发布由 GitHub Actions
自动构建（Windows 便携/安装包、Linux deb/rpm + `SHA256SUMS.txt`）。

## 这是什么仓库

本仓库包含三部分：

1. **逆向资料（`docs/`）** —— 网驱 bundle 的全量逆向笔记：协议帧格式、66 条命令表、按键/改键编码、
   宏表二进制格式、19 种灯效参数、逐键 LED 帧流、TFT 屏幕（240×135 动画/时间同步）、
   音乐律动、2.4G 无线（含休眠/唤醒通知）、官方 i18n 文案与未知项清单。
2. **参考实现与取证脚本（`scripts/`、`probe/`、`capture/`）** —— 带自检断言的编解码参考实现、
   直接驱动设备的 Python HID 客户端、Chrome CDP WebHID 抓包工具。
3. **（进行中）跨平台桌面工具/驱动（`driver/`）** —— Linux + Windows，覆盖本仓库已验证的全部能力。

## 设备能力速览（真机实测）

| 能力 | 状态 |
|---|---|
| 87 键改键（HID / 组合键 / 宏 / FN / 媒体键） | ✅ 可读写 |
| FN 层改键（26 条默认动作） | ✅ 可读写 |
| 19 种灯效 + 亮度/速度 + 逐键自定义灯（mode 20/21/128 共用一张表） | ✅ |
| 逐键实时帧流（每小时 20fps，音乐律动/AI 灯效） | ✅ USB 专用（2.4G 官方不支持） |
| 宏：100 槽 / 3072B，格式完全还原（含重复/再按结束语义） | ✅ 可读写 |
| TFT 240×135 自定义动画（≤140 帧，约 63 KB/s） | ✅ 可上传播放 |
| 屏幕时间同步 | ✅ |
| 游戏模式/休眠设置、电池/固件信息 | ✅ 部分字段 |
| 2.4G 无线（配置与 USB 共享，矩阵一致）+ 断连/唤醒通知 | ✅ |
| 磁轴、灯效 GIF、板载多 Profile、屏幕内置页/壁纸页/系统信息页、12/24h 屏幕显示 | ⛔ 固件/硬件不支持 |

## 文档入口

- **[docs/FEATURES.md](docs/FEATURES.md)** —— 功能总表（能力边界 + 修正记录，先看这个）
- **[docs/TEST-REPORT.md](docs/TEST-REPORT.md)** —— 真机测试报告（Phase 0–7 全部结果与证据）
- [docs/protocol.md](docs/protocol.md) —— 帧格式与命令表
- [docs/deepdive-mk87.md](docs/deepdive-mk87.md) —— 设备信息/游戏模式/屏幕时间
- [docs/keymap.md](docs/keymap.md) —— 按键映射与 **宏二进制格式（§16）**
- [docs/lighting.md](docs/lighting.md) / [docs/lighting-modes.json](docs/lighting-modes.json) —— 灯效
- [docs/tft-page.md](docs/tft-page.md) / [docs/tft-constants.json](docs/tft-constants.json) —— 屏幕
- [docs/music-rhythm.md](docs/music-rhythm.md) / [docs/music-constants.json](docs/music-constants.json) —— 音乐律动与逐键帧流
- [docs/wireless-profiles-led-animation.md](docs/wireless-profiles-led-animation.md) —— 2.4G 无线
- [docs/key-events.md](docs/key-events.md) —— 按键事件捕获（厂商协议无事件帧，需 RawInput）
- [docs/i18n-and-unknowns.md](docs/i18n-and-unknowns.md) —— 官方文案与未决项

## 真机工具（当前可用）

`probe/ajazz.py` 是零依赖（hidapi）的原生 HID 客户端；各 `probe/phase*.py` 是分项测试脚本，
`docs/TEST-REPORT.md` §14 有用法与结果索引。

```bash
pip install hidapi
python probe/phase0_selftest.py        # 设备自检
python probe/phase1_lighting.py        # 灯效测试
python probe/phase3_keys.py            # 改键测试
python probe/phase6_wireless.py        # 2.4G 测试
```

## 跨平台工具（规划）

- 平台：**Linux + Windows**（同一套核心协议库 + 两平台打包）
- 外观：支持**白色 / 黑色**两种配色（UI 主题 + 自动识别设备）
- 覆盖：改键、FN、宏编辑器、灯效、逐键灯、TFT 图片/动画、音乐律动、按键测试、设备信息、2.4G 设置、备份/恢复
- 已知硬件限制：2.4G 接收器与键盘 USB 同时连接在同一个 USB2.0 Hub 下时，
  Windows 会因资源不足（`0xC000009A`）导致后枚举的复合设备启动失败 —— 工具需检测并提示（详见 TEST-REPORT.md §8.7）

## 目录结构

```
docs/      逆向文档与实测数据（JSON 证据）
scripts/   参考实现与提取脚本（Node/Python）
probe/     真机测试脚本（Python + hidapi）
capture/   Chrome CDP WebHID 抓包工具
assets/    网驱 bundle 提取物（分析原料）
driver/    跨平台配置工具（开发中）
```

## 免责声明

本项目为非官方逆向工程，仅用于研究与个人使用。设备厂商固件/协议可能随版本变化；
写操作（改键、宏、灯效、屏幕内容）请自行备份原值。仓库内 `assets/`、`tools/` 为原厂网页驱动/
工具的提取物，版权归原厂所有，仅作研究留存。
