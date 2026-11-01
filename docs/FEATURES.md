# AJAZZ MK87 功能逆向总表（静态逆向 + 真机验证均已完成）

> 状态标记：✅ 静态逆向完成 ｜ 🧪 已于真机验证 ｜ ⬜ 待真机 ｜ ⛔ MK87 不支持 / 死代码 / 已确认不可达
> **真机测试已完成（2026-11-01），完整结果见 [TEST-REPORT.md](TEST-REPORT.md)**；本表"真机"列已按实测更新。
> 本表是"功能都逆向完了"的总索引；每行的细节证据见对应文档（`docs/` 下）。

## 一、协议底座（所有功能共用）

| 项 | 状态 | 说明 |
|---|---|---|
| 帧格式 | ✅🧪 | 请求 `AA cmd len addrLo addrHi hdr5 last hdr7 data...`；响应 `55 cmd ... data...`（数据偏移 8）；见 [protocol.md](protocol.md) |
| 命令表 | ✅ | 66 条命令全量；[command_enum.txt](command_enum.txt)、[protocol_commands.js](protocol_commands.js) |
| ACK 规律 | ✅🧪 | 设备对写命令回显同 cmd 的帧（len/addr/data 原样）；**TFT 上传两条命令的 ACK 都是 0x41**；2.4G 下 `SET_LED_EFFECT` 的颜色回读可能不等于写入（显示正确） |
| 通道 | ✅🧪 | USB：MI_02 = 主协议（0xFF68，64B）、MI_03 = TFT（0xFF67，4104B）；2.4G：MI_03 = 0xFF60（32B）；MI_04 = 0xFF59（64B，无响应、不在官方过滤器表） |
| 报告长度 | ✅🧪 | 均含 1 字节 report ID=0（WebHID `sendReport(0, 数据)` 时数据不含该字节） |

## 二、功能总表

| # | 功能 | 协议入口 | 静态 | 真机 | 细节文档 / 产物 |
|---|---|---|---|---|---|
| 1 | 设备信息（固件/电量/屏幕参数） | `GET_DEVICE_INFO` 0x10 | ✅ | 🧪 固件 1.19，tftMaxFrames=140，maxProfile=0，battery 50→75% | [deepdive-mk87.md](deepdive-mk87.md) |
| 2 | 按键映射读取（普通层） | `GET_KEY` 0x12 | ✅ | 🧪 112/128 槽非零；USB/2.4G 读取逐字节一致 | [keymap.md](keymap.md) |
| 3 | FN 层读取 | `GET_FN_KEY` 0x16 | ✅ | 🧪 26 条动作，出厂默认 | [fn-layer-decode.json](fn-layer-decode.json) |
| 4 | 按键映射写入（普通/FN） | `SET_KEY` 0x22 / `SET_FN_KEY` 0x26 | ✅ | 🧪 改 Insert→a、PgUp→亮度+、FN 层→亮度- 全部实际生效 | [keymap.md](keymap.md) |
| 5 | 4 字节编码（16 种 pageType + 490 条动作表） | pX/mX | ✅ | 🧪 主层/consumer/FUNC 实测；**写 0 = 恢复出厂默认** | [keymap-tables.json](keymap-tables.json)、[keymap.js](../scripts/keymap.js) |
| 6 | 灯效模式表（20 项） | `SET_LED_EFFECT` 0x23 | ✅ | 🧪 19 模式全部点亮且行为符合名称；16B 回读逐字节一致 | [lighting.md](lighting.md)、[lighting-modes.json](lighting-modes.json) |
| 7 | 自定义逐键灯 | `SET_CUSTOM_LED_DATA` 0x24 | ✅ | 🧪 写 8 色逐键对应；**mode 20/21/128 共用同一张表** | [lighting.md](lighting.md) |
| 8 | 灯效动画（GIF 灯效/开机动画） | 0x41/0x42/0x40/0x36 | ✅ | ⛔ MK87 `ledMaxFrames=0`、无 `isShowGifEffect` | [lighting.md](lighting.md) |
| 9 | 音乐律动（官方 v1，插件） | 本地 `127.0.0.1:9191` | ✅ | ⛔ 官方 UI 强制 Music.exe；插件直接驱动设备 | [music-rhythm.md](music-rhythm.md) §1 |
| 10 | 音乐律动（自研链路） | `setMusicData`（USB→cmd 0x32） | ✅ | 🧪 **激活 = 先切 LED mode 20/21/128**；20fps / 15.5ms/帧；停帧 ~5s 回落 | [music-rhythm.md](music-rhythm.md)、[music_ref.js](../scripts/music_ref.js) |
| 11 | 逐键实时帧流（AI 灯效/同步通道） | cmd 0x32（4B/键） | ✅ | 🧪 7 包/帧、ACK 0.5–3ms、可读回 `GET_ALL_LIGHTS_RGB` 验证 | [music-constants.json](music-constants.json) |
| 12 | 宏读取 | `GET_MACRO` 0x15 | ✅ | 🧪 空表、空间 3072B | [protocol_commands.js](protocol_commands.js) |
| 13 | 宏写入 | `SET_MACRO` 0x25 | ✅ | 🧪 写宏 "abc"→回读逐字节一致；Insert 打出 abc；mask 0/1/2 语义实测确认 | [keymap.md](keymap.md) §16 |
| 14 | TFT 壁纸（单帧） | `SET_TFT_MATERIAL` 0x4D | ✅ | 🧪 可写入（16 包 ACK=0x41），但 MK87 **无壁纸页 → 不可见** | [tft-page.md](tft-page.md) |
| 15 | TFT 动画（≤140 帧 240×135） | `SET_TFT_USER_ANIMATION` 0x50 | ✅ | 🧪 3 帧测试动画 + 官方 135 帧默认动画均正常播放 | [tft-constants.json](tft-constants.json) |
| 16 | TFT 内置页索引 | `SET_TFT_BUILT_IN_INDEX` 0x51 | ✅ | 🧪 发 0..5 设备回 ACK 但**屏幕不切页**（确认不支持） | [tft-page.md](tft-page.md) |
| 17 | TFT 屏幕时间 | `SET_TEMPORARY_COMMAND_DATA` 0x34 | ✅ | 🧪 10B 时间帧 ACK 回显一致 | [deepdive-mk87.md](deepdive-mk87.md) |
| 18 | TFT 系统信息（CPU/GPU/天气） | 0x34（24B）+ 0xFA type6 门控 | ✅ | ⛔ MK87 屏幕无系统信息页（真机确认） | [tft-page.md](tft-page.md) |
| 19 | 屏幕 12/24 小时制 | `SET_GAME_MODE` payload[7] | ✅ | ⛔ 写入/回读一致、断电重启后仍**无可见变化** → MK87 无效果 | [i18n-and-unknowns.md](i18n-and-unknowns.md) §4.5 |
| 20 | 游戏模式/设置 | 0x11/0x21 | ✅ | 🧪 56B 原样回写一致；多数字段 0xFF 不支持 | [deepdive-mk87.md](deepdive-mk87.md) |
| 21 | 多 Profile（软件） | `SET_PROFILE` 0x90 | ✅ | ⛔ `maxProfile=0`，纯本地 profile；`/profiles` 路由被重定向 | [wireless-profiles-led-animation.md](wireless-profiles-led-animation.md) |
| 22 | 2.4G 无线身份/配置 | 接收器复合 ID | ✅ | 🧪 dongle = `3141-65278 "2.4G Dongle"`；`manufacturer=1/product=18/workMode=2`；按键矩阵与 USB 逐字节一致 | 同上 |
| 23 | 2.4G 专用命令（0x37/0x3B/0x3C/0xFC） | — | ✅ | 🧪 0xFF60 通道常规命令全通；**音乐律动：官方确认 2.4G 不支持**（⛔，帧流仅 USB 可用） | [wireless-constants.json](wireless-constants.json) |
| 24 | 休眠/唤醒/断开通知 | 0xFC / `A6 FF 01` | ✅ | 🧪 实测：`55 FC 04` 断连在 0xFF60、`A6 FF 01` 唤醒在 0xFFFF(reportID=5)；`0xFC/6` 未见 | [key-events.md](key-events.md) |
| 25 | 设备通知（0xFA/0xFC/0xFB） | 事件监听 | ✅ | 🧪 空闲/旋钮切页 75s 内 **0 条上报** | [device-notifications.json](device-notifications.json) |
| 26 | 实时按键事件捕获 | — | ⛔ 厂商协议**没有**按键事件帧 | 🧪 HID `\kbd` 直读 err=5 被拒；**RawInput 可用**（VKey+MakeCode+设备名） | [key-events.md](key-events.md) §4.3 |
| 27 | OTA / 固件升级 | 0x80–0x86 | ⛔ 按用户决定跳过 | — | — |
| 28 | 社区图库/分享 API | HTTP | ⛔ 按用户决定跳过 | — | — |

## 三、MK87 能力边界（实测/配置双重确认）

**支持**：87 键改键（HID 键 / 组合键 CB / 宏 / FN 动作 / consumer 媒体键）、FN 层改键、19 种灯效 + 逐键自定义灯
（20/21/128 同一张表）、240×135 TFT 自定义动画（≤140 帧，实测 135 帧 8.75MB / 311s 上传）、屏幕时间同步、
游戏模式部分设置（休眠、按键延迟、12/24h 可写）、电池/充电读取、**主机逐键实时帧流（音乐/AI 灯效，20fps 稳定）**、
2.4G 无线（0xFF60 通道，配置与 USB 共享，矩阵逐字节一致；**音乐律动仅 USB，官方确认 2.4G 不支持**）。

**不支持 / 未启用**：磁轴全家（DKS/RT/SOCD/MT/TGL/RS）、侧灯/灯箱/点阵屏、灯效 GIF 动画（ledMaxFrames=0）、
屏幕内置页切换（0x51 无效果）、TFT 壁纸页（写入不可见）、屏幕系统信息页、板载多 Profile（maxProfile=0）、
官方音乐 UI（强依赖 Music.exe）、官方系统信息 UI（缺 isShowTftInfo）、12/24h 对屏幕无可见作用。

**死代码 / 不可达**：pageType 4/5（无编解码分支）、`GET_MAGNETIC_AXIS_KEY_STATUS(0x60)`（仅枚举）、
`SET_KEYBOARD_CUSTOM_FUNCTION_ON/OFF(48/49)`（0 调用）、`SET_LED_BOOT_ANIMATION(64)`（0 调用，开机动画复用 65 + `ledId='startup'`）、pageType 14 END（MK87 无 advancedKeys 路由）。

## 四、修正记录

**静态阶段最后几轮订正**

1. `tftDisplayTime` = **12/24 小时制选择器**（0=24h、1=12h），不是"显示时间/时钟开关"。
2. `/key-test` 页 = **浏览器 DOM 键盘事件**，与 HID 无关；点阵/虚拟键盘是写死的 104 键 ANSI 表。
3. **厂商协议无法获取实时按键事件**（6 个 0x55 消费点穷举；0x60 为死枚举，`iZ` 实为 0x68 `getMagneticAxisStatus`）。
4. **音乐 v1 浏览器不发帧**：Music.exe 直接驱动设备；只有 v2 才由浏览器发 `setMusicData` 逐键帧。
5. MACRO：`param2` 0=常规/1=重复播放/2=再次按键结束；`param3` 仅在 `param2===1` 时为重复次数。
6. `docs/device_config_32839.json` 已重新生成为**无损版**（旧版 musicConfig 丢失、lightingConfig 字符串化）。
7. `extract.js` 的 `findDef` 用 `\b` 漏抓 `$X`（start24GWakeListener 等），无线线已用原文补齐并纳入自检；`docs/infra.js` 仍为旧版（不影响文档结论）。
8. 2.4G 身份 = `3141-65278-2.4G Dongle-1-18`（真机设备信息 manufacturer=1/product=18 与配置命中一致）。

**真机阶段修正（2026-11-01，证据见 [TEST-REPORT.md](TEST-REPORT.md) §12）**

9. **TFT 上传 ACK**：`0x4D`（壁纸）与 `0x50`（动画）的逐包 ACK 都是 **0x41**（官方壁纸路径按 0x4D 等 ACK 是错的）。
10. **屏幕没有壁纸页 / 系统信息页**；页面 = 设备端菜单（主页时钟 / 设置：灯光效果·颜色·亮度·速率·语言 / 自定义动画）。
11. **0x51 内置索引**：设备回 ACK 但不切页 → MK87 不支持。
12. **12/24h 写入生效但屏幕无变化**（fw1.19，未决是否需重启）。
13. **亮度字段**：1..6 是 identity，**brightness=1 = 全灭**（PWM 0/49/97/143/191/253）；越界值未定义
    （0→255、7→11、8→12…16→1、255→0），工具侧应钳到 2..6。
14. **写 0 的语义**：keyList 内的槽写 0 = **恢复出厂默认**；25 个配置外槽写 0 **被固件保护**（保持原值），
    写非零则生效 → 「官方写法会丢小键盘/音量」的静态推断在 fw1.19 上**不成立**。
15. **逐键帧流激活条件**：必须先 `SET_LED_EFFECT` 切到 **mode ∈ {20,21,128}**；停止收帧 ~5s 后回落到自定义表（H2/H3 落定，H1 否）。
16. **物理 LED 槽 86 个**：官方 keyList 标有键的 99/100/102 实际无灯（该位置是小屏幕），标无键的 97/98 实际有灯；
    Fn 键 LED 是**充电指示灯**（充电时强制红，LED 数据压不掉）。
17. **2.4G 协议口 = 0xFF60（32B）**；0xFF59（64B）无响应且不在官方 WebHID 过滤器表；2.4G 下 `SET_LED_EFFECT`
    的颜色回读可能不等于写入（显示正确），回读不能作为写成功判据。
18. **2.4G dongle 与键盘 USB 同插会触发 Windows 0xC000009A（资源不足）**，拔掉其一即恢复；不是固件问题。
19. **宏表格式已还原并真机验证**（[keymap.md](keymap.md) §16）：400B 偏移表（u32 LE 绝对偏移，数据区从 400 起）
    + 宏块 `[动作数×2][0][每动作: delay u16LE | HID usage | flags]`，`flags=((actionType&7)<<4)|(isPress?0x80:0)`；
    写入按「偏移表 last=0 / 动作区 last=1」两次 `SET_MACRO`；mask 语义 0=单次、1=重复 N 次、2=再按结束（全部实测通过）。
20. **槽 97/98 有 LED 驱动通道但无可见光**：真机写红/绿后缓冲回读正确、人眼不可见 → 判为未装配/被遮挡。
21. **2.4G 通知帧走两条通道**：断连/复位/休眠 `55 FC 04/05/06` 在 **0xFF60** 协议口；
    **唤醒帧 `A6 FF 01` 在 MI_02/COL05（usagePage 0xFFFF，report ID=5）**，该接口不在官方 WebHID 过滤器表
    → 官方驱动收不到唤醒帧；`sleepTime` 单位=分钟（1/10/20/30，0=关），实测 1 分钟即断连（收到 `0xFC/4`，未收到 `0xFC/6`）。
22. **`tftDisplayTime`（12/24h）对 MK87 屏幕无效果**：断电重启后仍显示 24h 格式（19:05 不变 7:05）。
23. **官方确认 2.4G 模式不支持音乐律动**（用户转述官方说明）：真机三种帧格式均只产生「短暂白脉冲/随机色/竖条纹」，
    与「通道收到数据但固件无 2.4G 帧映射」一致 → 该项从「待还原」改为 **⛔ 设备不支持**，自研音乐律动只做 USB。

## 五、产物索引

**文档（docs/）**：protocol.md｜deepdive-mk87.md｜keymap.md｜keymap-tables.json｜fn-layer-decode.json｜keymap_device_report.txt｜lighting.md｜lighting-modes.json｜tft-page.md｜tft-constants.json｜i18n-and-unknowns.md｜i18n-keys.json｜func-i18n-map.json｜key-events.md｜device-notifications.json｜wireless-profiles-led-animation.md｜wireless-constants.json｜music-rhythm.md｜music-constants.json｜device_config_32839.json｜device_dump.json｜**TEST-REPORT.md（真机测试报告）**｜FEATURES.md（本文）｜TEST-PLAN.md

**参考实现（scripts/）**：keymap.js（按键编解码，34 断言全绿）｜**phase3_macro.py（宏表编解码，真机验证）**｜lighting_ref.js（453/0）｜keyevent_ref.js（18/0）｜wireless_ref.js（11/0）｜music_ref.js（31/31，真机链路已跑通）｜tft_ref.js（自检全绿）｜make_test_wav.py｜gen_music_frames.js｜各类取证/复现脚本

**真机工具（probe/）**：ajazz.py（原生 HID 客户端）｜phase0_selftest.py｜phase1_lighting/_diag*/phase4_*/phase5_music/phase6_wireless/phase7_*｜restore_tft_default.py 等（见 TEST-REPORT.md §14）

**备用（capture/）**：零依赖 Chrome CDP WebHID 抓包工具（半自动，23/23 + 33/33 测试通过）

**原料（assets/、docs/_lighting_raw/、docs/_wireless_raw/）**：网页驱动 bundle、页面 chunk、i18n 语言包、各线原始提取物

## 六、下一步

静态逆向 → 真机验证**均已收口**。**真机测试项已全部关闭**（宏写入、2.4G 音乐律动、2.4G 休眠通知、12/24h、97/98 定位）。
下一步转入工具/驱动实现：音乐律动（USB）、宏编辑器、改键工具，以及 2.4G+USB 同时连接的
Windows 资源冲突处理方案（见对话记录里的"方案 B：软件隔离 + UAC helper"）。
