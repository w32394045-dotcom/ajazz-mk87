# 关于「内核级驱动」的评估与结论

> 一句话结论：**这个工具不需要内核模块**，Linux 侧用 `hidraw + udev + evdev` 已经完全够用；
> 内核驱动只会在维护成本上增加负担，不带来任何功能增量。本文记录评估过程和理由，
> 也说明如果将来真的需要「内核级」能力，应该走什么方案。

## 1. 硬件与协议事实

- MK87 是**标准 USB HID 复合设备**（VID 0x0C45），Linux 内核的 `hid-generic` 驱动会自动绑定，
  并给每个接口创建 `/dev/hidrawN` 节点；
- 我们逆向出的全部配置命令（改键/宏/灯效/TFT/音乐帧流/无线设置）都是**普通的 HID output report**
  （`AA ...` 帧）+ 读取 input report（`55 ...` 回显），**没有任何厂商私有 USB 请求/控制传输**；
- 因此，用户态通过 hidapi（Linux 下即 hidraw 读写）就能完成全部操作 —— 社区同类工具
  （VIA/QMK、OpenRGB、各厂商 Linux 配置工具）也都是用户态实现。

## 2. 为什么不做内核模块

| 维度 | 用户态（现状） | 内核模块 |
|---|---|---|
| 功能覆盖 | 全部配置命令、逐键 20fps 帧流、TFT 上传 | 无新增能力 |
| 权限 | udev 规则 `TAG+="uaccess"` 即可免 root | 同样要处理设备权限 |
| 安装 | deb/rpm 里放一条 udev 规则，零编译 | 需要 DKMS/内核头文件/每次内核升级重编 |
| Secure Boot | 不受影响 | 模块必须签名，否则需要关闭 Secure Boot |
| 发行版 | 一个包走天下 | 每个发行版/内核版本都要适配与审核 |
| 稳定性风险 | 用户态崩溃不影响系统 | 内核 oops/panic 影响整机 |
| 维护 | 协议层 Python 改起来快 | 需要长期跟进内核 HID/输入子系统 API |

**结论**：除非出现「必须在内核态完成」的硬需求，否则不应引入内核模块。

## 3. 可能被误认为需要内核的场景（其实不需要）

| 场景 | 事实方案 |
|---|---|
| 让配置工具读到键盘 HID 接口 | `/dev/hidraw*` + udev 权限规则（本项目已提供） |
| 让配置工具读到按键事件（按键测试） | Linux：读 `/dev/input/event*`（evdev，input 组）；Windows：RawInput |
| 宏回放 / 输入注入 | 用户态 `uinput`（`python-evdev` 的 `UInput`）即可创建虚拟键盘，不需要内核模块 |
| 灯效逐帧 20fps | 用户态写 hidraw，实测 20fps 稳定（见 `docs/TEST-REPORT.md`） |
| 2.4G + USB 同时插的资源冲突 | 属于枚举期资源分配问题，内核模块也解决不了；只能物理/拓扑层规避（见 TEST-REPORT §8.7） |
| 绕过官方驱动的 WebHID 过滤表 | 用户态 hidapi 本就不受 WebHID 限制 |

> 唯一「形似内核级」的事：写一个 `hid-mk87` 模块把设备重新注册一遍 —— 它最终效果和
> `hid-generic + hidraw` 完全等价，属于纯粹的重复劳动，**不做**。

## 4. Linux 实际采用的方案（已实现）

1. **HID 访问**：`hidapi`（read/write `/dev/hidraw*`），见 `mk87lib/transport.py`；
2. **权限**：`packaging/udev/99-ajazz-mk87.rules`（`MODE=0666` + `TAG+="uaccess"`），
   安装 deb/rpm 时自动放到 `/usr/lib/udev/rules.d/`；
3. **按键事件**：`evdev`（`/dev/input/event*`，需 `input` 组）；
4. **音乐回环**：PulseAudio/PipeWire 的 `parec`（`@DEFAULT_MONITOR@`），见 `mk87lib/music.py`；
5. **打包**：`.deb` / `.rpm` 两种方式，安装后直接 `mk87` 启动（见 `packaging/README.md`）。

## 5. 如果将来真需要内核级能力

按优先级排列：

1. **输入注入/宏回放** → 用户态 `uinput`（无需 root，无需模块）；
2. **更底层的 USB 控制**（例如切厂商模式）→ `libusb` 用户态 + udev 规则；
3. **只有确实需要在内核态拦截/改写键值流时**，才考虑写 `hid-mk87` 模块（DKMS + 签名），
   本项目的协议逆向文档（`docs/spec-*.md`）可以直接作为内核模块的实现依据。

现阶段：**不实现内核模块**。如果你希望我把它作为一个可选项继续做，请明确要它解决的具体问题，
否则按上面的方案交付即可。
