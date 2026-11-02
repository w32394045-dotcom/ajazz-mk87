# MK87 Studio · AJAZZ MK87 跨平台配置工具

> 非官方逆向工程工具 · **Windows + Linux** · 全部功能离线本地运行（不访问外网）

本次发布由 GitHub Actions 自动构建（Windows 便携/安装包、Linux deb/rpm），附件含
`SHA256SUMS.txt` 校验值。

## 下载 / Downloads

| 平台 | 文件 | 说明 |
|---|---|---|
| Windows | `MK87Studio-*-win64-portable.zip` | 免安装：解压后双击 `MK87Config.exe`（`_internal` 目录需同目录） |
| Windows | `MK87Studio-*-win64-setup.exe` | 安装版：开始菜单/桌面快捷方式、可选开机自启 |
| Linux | `mk87_*_amd64.deb` | Debian / Ubuntu：`sudo apt install ./mk87_*.deb` |
| Linux | `mk87-*.x86_64.rpm` | Fedora / openSUSE：`sudo dnf install ./mk87-*.rpm` |

Linux 包内已包含 `99-ajazz-mk87.rules`（免 root 访问 HID），安装后请重新插拔键盘。

## 功能

- **改键**：87 键主层 + FN 层，支持 HID 键码 / 组合键 / 宏 / 媒体键，实时预览编码
- **宏**：100 槽 / 3072B，支持重复播放、再按结束语义；鼠标动作与掩码
- **灯效**：19 种预设 + 颜色/亮度/速度/方向；逐键自定义灯（mode 20/21/128）
- **音乐律动**：官方渲染器（律动节拍 / 光尘螺旋 / 萤火轨迹 / 曲率频谱），USB 20fps 逐键帧流
- **TFT 屏幕（240×135）**：图片/GIF 上传（≤140 帧、cover 裁剪、RGB565、逐包 ACK），时间同步，恢复官方默认动画
- **设备**：信息/电池/固件、游戏模式、2.4G 无线设置与通知
- **按键测试**、**备份/恢复**、**完整日志 + 一键导出诊断包**
- 浅色 / 深色主题，中文 / English；系统托盘 + 开机自启；单实例

## 已知限制

- **音乐律动仅 USB 有线**（官方确认 2.4G 不支持帧流）
- **TFT 上传是独占总线操作**：上传期间请勿操作其它功能（app 已自动暂停后台电量轮询；上传前会显示压缩后帧数/大小/预计耗时）
- 屏幕内容**只能写不能读回**，换内容/恢复默认只能重传
- 2.4G 接收器与 USB 同时插在同一 USB2.0 Hub 时，Windows 可能因资源不足（`0xC000009A`）导致后枚举设备启动失败（详见 docs/TEST-REPORT.md §8.7）
- 磁轴高级键、灯效 GIF、屏幕内置页/壁纸页/系统信息页、板载多 Profile：固件/硬件不支持

## 从源码运行

```bash
git clone https://github.com/w32394045-dotcom/ajazz-mk87.git
cd ajazz-mk87/driver
python -m venv .venv && .venv\Scripts\pip install -r packaging/requirements.txt   # Windows
.venv/bin/pip install -r packaging/requirements.txt                              # Linux
.venv/Scripts/python shell.py        # 原生窗口（Windows）
.venv/bin/python shell.py            # 原生窗口（Linux，需 Qt WebEngine）
python run.py                        # 浏览器模式
```

更多协议/逆向资料见仓库 `docs/`（FEATURES / TEST-REPORT / protocol / keymap / lighting / tft-page / music-rhythm / wireless）。
