# ajazz-mk87 开发日志（DEVLOG）

> 记录**过程与证据**：当时基线、做了什么、怎么验证、踩了什么坑、还剩什么没定。
> 现状/用法看 [README](../README.md)；协议结论看 `docs/` 下各专题文档。

## 0 元信息

| 项 | 值 |
|---|---|
| 本次记录 | 2026-11-02 · 音乐律动「官方效果」复刻调研（只测试，未改 driver/app 代码） |
| 项目 | MK87 Studio / ajazz-mk87（协议逆向 + 跨平台配置工具） |
| 仓库 | <https://github.com/w32394045-dotcom/ajazz-mk87>，`main` @ `2ff1e3e` |
| 本机环境 | Windows 10 LTSC 10.0.17763；驱动 venv Python 3.12.14；设备 AJAZZ MK87 `0C45:8047`，固件 1.19 |
| 官方侧 | Music.exe 插件 `MusicPlug.exe`（内部名 Music.exe 1.0.0.1，HFDMusic）；网页驱动 `https://ajazz.driveall.cn/lighting` |
| 标注规则 | **已实测** / **待真机** / **推断** / **未记录**（全文统一，禁止把推断写成结论） |
| 性质 | 长期项目日志，只追加；旧章节数字保留为「当时值」 |

### 0.1 怎么读

- 新读者先看 §1 基线，再按需看 §3—§6（音乐 v1 链路 → 插件协议 → 官方帧规格 → 采样数据）。
- 行号会随版本漂移；引用代码请用**文件名 / 函数名 / 章节号**定位。
- 本次结论只覆盖「官方 v1 插件路径」；网页 v2 渲染器（14—22 模式）不在本次实测范围。

---

## 1 基线（动手前）

| 项 | 现状 | 位置 / 证据 |
|---|---|---|
| 仓库状态 | `main` @ `2ff1e3e`，与 `origin/main` 一致；工作区仅有本次新增的未跟踪产物 | `git -C ajazz-re log --oneline -1`；`git status --short`（见 §8） |
| 自有音乐实现 | 20fps；7 包/帧；348B/87 键；已从网页 v2 bundle 移植模式 1/4/13/14/17，其余模式回退到 13 | `driver/mk87lib/music.py` 文件头；`docs/music-rhythm.md` |
| 官方 Music.exe | 运行中 PID 4744，监听 `127.0.0.1:9191`；大小 381,656 B，文件时间 2025-10-13 | 进程列表；HTTP 探测 `GET /api/audio/amplitude` 返回 200 |
| 官方网页 bundle | `layout-classic-CMxiG14P.js` **3,335,710 B**，与 11-01 抓 TFT 时同一 hash（`CMxiG14P`） | 已下载到 `capture/official_music_live/` |
| 设备 | MK87 USB，固件 1.19，电量 100% | `probe/ajazz.py` → `GET_DEVICE_INFO` |
| 官方页面状态 | 用户浏览器停在 `ajazz.driveall.cn/lighting` 音乐律动页，音乐在播（`/api/audio/amplitude` 有 0—636 波动） | 用户截图；HTTP 采样 |

---

## 2 目标与范围

**目标**：搞清 MK87 上「官方音乐律动效果」的真实实现——官方渲染器行为、插件驱动的正确顺序、实际下发的 HID 帧规格——为后续「复刻官方效果」提供可验收依据。

**范围**：
- 只读：线上 bundle、官方 Music.exe 的 HTTP 接口、被动 HID 监听、设备只读命令。
- **未改动** `driver/`、`mk87lib/`、`server/`、`shell.py` 等实现文件；本次只新增 `probe/` 抓取脚本和 `capture/` 数据。

**验收口径**：每条结论能落到「命令 + 输出 / 文件 + 大小 / HTTP 返回 / 帧字节」；视觉手感类只能标**待真机**。

---

## 3 官方音乐 v1 链路（静态提取，已实测）

从线上 bundle `layout-classic-CMxiG14P.js`（offset ≈ 2,301,704 的 `function D7` / `musicV1` 控制器）提取：

### 3.1 显示模式（12 个，参数 `mode`）

| label（UI） | value |
|---|---|
| 绿色/黄色/红色 | 1 |
| 彩虹色 | 2 |
| 随曲起舞 | 13 |
| 曲率频阶 | 4 |
| 频谱循环 | 5 |
| 白色 | 6 |
| 红色 | 7 |
| 橙色 | 8 |
| 黄色 | 9 |
| 蓝色 | **11**（bundle 中 text10 → 11） |
| 绿色 | **10**（bundle 中 text11 → 10） |
| 屏光联动 | 100 |

### 3.2 背景灯光模式（11 个，参数 `backmode`）

| label | value |
|---|---|
| 无 | 0 |
| 白色 | 6 |
| 红色 | 7 |
| 橙色 | 8 |
| 黄色 | 9 |
| 蓝色 | 10 |
| 绿色 | 11 |
| 绿色/黄色/红色 | 1 |
| 彩虹色 | 2 |
| 色谱 | 4 |
| 频谱循环 | 5 |

### 3.3 参数与调用

- 振幅、背景亮度均为 `1..100` 滑杆。
- 启动/切换：
  `GET http://127.0.0.1:9191/api/keyboard/musiceffect?param=<mode>&<amp>&<backmode>&<bb>&1`
  （最后一位固定 `1`，见 bundle `v=EI(async()=>{...TY(`${s.value}&${c.value}&${l.value}&${u.value}&1`)},300)`）
- 关停：`GET /api/keyboard/musiceffect/close/`
- 官方网页启动顺序（bundle `b()`）：
  1. `GET /api/keyboard/layout/base64?data=<URL-encoded base64(JSON)>` 发键盘布局；
  2. 发一次 `param`；
  3. **每 100ms** 轮询 `GET /api/keyboard/musiceffect/` 刷新预览（同时是 keepalive）。

> 证据：`capture/official_music_live/layout-classic-CMxiG14P.js`（3,335,710 B，已下载）。
> 注：以上 label→value 是 bundle 字面值；实测颜色与 label 的最终对应仍需按 §6 数据核对（见 §10 待决）。

---

## 4 官方插件驱动协议（实测）

| 步骤 | 命令 / 请求 | 实测结果 |
|---|---|---|
| 发布局 | `GET /api/keyboard/layout/base64?data=<layout b64>` | `{"status":"success","dataSize":4660,...}` |
| 启动 | `GET /api/keyboard/musiceffect?param=13&30&0&100&1` | 响应 `mode=13, amplitude=30`，开始渲染 |
| 保活 | 每 **100ms** `GET /api/keyboard/musiceffect/` | mode 保持 13；颜色逐帧变化 |
| 停用 | `GET /api/keyboard/musiceffect/close/` | `{"status":"close ok"}`，设备回落 |

**keepalive 判定（已实测，2026-11-02）**：轮询间隔 >200ms 时，插件会把 `mode` 归 0（会话断开）；100ms 可稳定维持。

**坑（已实测，重要）**：`GET /api/audio/amplitude` 会**重置音乐会话**（`mode`→0、颜色冻结）。在其后 3 次测试中重复出现：
`baseline mode=13 → 调用 amplitude → mode=0, colors 冻结`。因此**采样颜色期间禁止调用该接口**（第一次全黑采样就是这个原因）。

---

## 5 官方实际 HID 帧规格（实测，关键结论）

被动监听 MI_02（`usagePage=0xFF68`）上的 `55 32` 回显（插件发帧、设备回显）：

| 项 | 实测值 | 说明 |
|---|---|---|
| 帧分包 | **8 包/帧** | addr：0, 56, 112, 168, 224, 280, 336, 392；末包 40B，其余 56B |
| 帧长度 | **432 B = 108 项**（432/4） | 每项 4B；按 addr==0 切帧 |
| 包率 | **530.5 包/s**（2s 内 1061 包） | 帧率按 8 包/帧推算 ≈ **66fps**（**推断**，未逐帧打时间戳） |
| 帧头 | `i=0`、`last=0`（恒 0） | 官方不用 last 标志，帧起点以 addr==0 判定 |

**与我们当前实现的差异**：

| 项 | 官方 Music.exe（v1） | 我们 app（2026-11-02 前） |
|---|---|---|
| 每帧 | 8 包 / 432B / 108 项 | 7 包 / 348B / 87 键 |
| 帧率 | ≈60fps（包率实测 530.5/s） | 20fps |
| 帧标志 | `i=0,last=0`，addr==0 切帧 | 有 last 标志 |
| 模式集合 | v1 只有 §3.1 的 12 个 | 已移植 v2 的 1/4/13/14/17，其余回退 13 |

> **推断（未验证）**：60fps + 108 项网格帧是「官方效果更顺滑/更贴合」的主因，渲染公式差异次之——待方案 A 实测确认。

---

## 6 官方组合采样（数据集，已落盘）

### 6.1 采样器

- `probe/capture_official_music_v2.py`（11,374 B）：按官方顺序发 layout → param → 100ms 轮询采样；
  默认**不开 HID 监听**（避免与插件抢 ACK），`--frames` 才开；`--amp` 显式打开振幅轮询（会重置会话，仅用于单独测振幅）。
- 输出 JSONL：`param` 记录组合、`http` 记录每 100ms 的每键颜色（102 键，含 row/col）。
- 采样规模：**29 组组合 × 4s**，每组约 51 个样本（≈10Hz）。数据文件 `capture/official_music_colors3.jsonl`（5,172,142 B）。
- 分析输出：`capture/official_music_analysis3.txt`（2,955 B）。

### 6.2 观察摘要（`official_music_analysis3.txt`，仅颜色数据，已实测）

| 组 | 现象 |
|---|---|
| 背景模式 6—11（白/红/橙/黄/蓝/绿） | **102 键全部点亮**对应颜色；`mode=13` 时每 4s 50 次颜色变化（≈12.5Hz 采样变化） |
| 背景亮度 D 组 | bb=100 → 主色 `FE0000`；bb=50 → `7E0000`；bb=20 → `320000` → **亮度按 bb 线性缩放**（实测） |
| `mode=100 屏光联动` | 102 键全亮，颜色灰白（`F0F1F1`/`D7D7D8` 附近），4s 内 38 次变化 |
| `mode=13 随曲起舞` | 低覆盖动态点（lit 平均 4，max 9），颜色以绿/蓝为主，4s 内 23 次变化 |
| `mode=4 曲率频阶` | 近似全黑（lit 平均 0，max 1） |
| `mode=7/8/9/11` 等"纯色"模式 | 只有少量键点亮（lit 平均 3—14），不是整屏纯色；颜色与 label 对应（红/橙/黄/绿系） |
| 背景模式 0（无）+ mode=13 | lit 平均 11.2、max 40（动态点为主） |

> 说明：采样时音乐音量偏低（live amplitude 常见 0—150，个别到 636），低覆盖可能部分受振幅影响；该数据用于**结构对比**，不作为亮度定标。

### 6.3 失败与重采记录（保留，防止下次重复踩坑）

| 采样文件 | 时间 | 结果 | 原因 |
|---|---|---|---|
| `capture/official_music_capture.jsonl` | 19:59 | ❌ 0 帧 / 全黑 | 未按官方顺序（缺 layout）；HID 监听与插件抢 ACK |
| `capture/official_music_capture_v2.jsonl` | 20:10 | ❌ 0 帧 | 顺序 / 监听时机不对 |
| `capture/official_music_colors.jsonl` | 20:21 | ❌ 全黑 | 轮询了 `/api/audio/amplitude`，重置会话 |
| `capture/official_music_colors2.jsonl` | 20:25 | ❌ 全黑 | 同上（脚本当时仍每 5 次轮询一次 amplitude） |
| `capture/official_music_colors3.jsonl` | 20:29 | ✅ 成功 | layout → param → 100ms 轮询，全程不碰 amplitude |

---

## 7 事故：HID 抢 ACK 导致键盘 USB 挂起（已恢复）

| 项 | 内容 |
|---|---|
| 症状 | 采样脚本打开 MI_02 读句柄后，插件发帧停止/读不到；随后 `hid.write` 返回 -1、设备不响应，`Get-DeviceInfo` 打开卡住 |
| 触发条件 | 官方 Music.exe 正在以 ~60fps 发 `0x32` 帧时，另一个进程同时开 MI_02 读句柄（抢 ACK 回显） |
| 根因（推断） | HID 输入队列竞争/ACK 被抢，插件写循环卡住，设备侧输入缓冲积压 → USB 无响应（未做固件级验证） |
| 修法 | 停止采样进程；用户拔插键盘 USB 复位；之后采样**不再打开 HID 读句柄**（HTTP 颜色采样已足够做结构对比） |
| 防复发 | `capture_official_music_v2.py` 默认不开 HID 监听（`--frames` 显式开启并注明风险）；调试文档 `docs/music-rhythm.md` 补充「不要与 Music.exe 抢 ACK」 |
| 恢复验证 | 20:2x 拔插后 `GET_DEVICE_INFO` 正常：fw=1.19，battery=100%，耗时 15ms（已实测） |

---

## 8 仓库状态与本次产物

- 本地 `main` = `origin/main` = `2ff1e3e`；**没有提交本次调研产物**。
- 本次新增、未跟踪：
  - `probe/capture_official_music.py`（9,474 B）、`probe/capture_official_music_v2.py`（11,374 B）
  - `capture/official_music_analysis.txt`（2,049 B）、`official_music_analysis2.txt`（2,244 B）、`official_music_analysis3.txt`（2,955 B）
  - `capture/official_music_live/`（55 文件，3,927,289 B，官方线上 bundle 快照）
  - `capture/official_music_colors3.jsonl`（5,172,142 B）等采样数据 —— 按 `.gitignore`：`capture/*.jsonl`、`*.log` **不提交**
- 待决定：日志与抓取脚本是否提交 + 推送；采样 JSONL 是否归档到 Release/对象存储（体积 5MB 级）。

---

## 9 决策订正

| # | 原计划 | 订正 | 原因 |
|---|---|---|---|
| 1 | 让用户点官方 UI 逐项采样 | **改为脚本直接驱动插件 HTTP** | bundle 里有完整参数表；脚本可复现、可批量 |
| 2 | 用 `/api/audio/amplitude` 同步振幅 | **采样颜色时禁止调用** | 实测该接口重置音乐会话（mode→0、颜色冻结） |
| 3 | 直接 PUT/调参即可启动 | **必须 layout → param → 100ms 轮询** | 缺 layout 不渲染；轮询慢于 200ms 会归 0 |
| 4 | 按网页 v2 bundle 移植 14—22 模式来复刻 | **MK87 v1 只有 12 个模式** | 官方 v1 插件不提供 14—22；先对齐 v1 集合 |
| 5 | 被动抓官方帧最直接 | **帧监听有设备风险，默认关闭** | 与插件抢 ACK 会把键盘 USB 打挂（§7） |

---

## 10 待决 / 下一步（需要拍板）

| # | 事项 | 说明 | 找谁定 |
|---|---|---|---|
| 1 | 方案选择 | A：先升级帧规格（60fps/108 项/无 last）验证观感；B：按采样数据逐模式对齐 12 个 v1 渲染器；C：先出逐模式差异报告 | 用户 |
| 2 | 108 项 ↔ 87 键映射 | 官方 432B 帧是 108 项，设备 87 键；项序/槽位映射未解（帧内容已抓到，待离线分析） | 下一轮 |
| 3 | 模式 10/11 标签核对 | 实测 mode 11 渲染偏绿、mode 10 偏蓝；与 i18n 标签需再核（bundle 中 text10→11 / text11→10） | 下一轮 |
| 4 | 屏光联动（100）依赖 | 需要屏幕内容采集才有效果，本次只看到灰白全亮，未验证联动逻辑 | 下一轮 |
| 5 | 视觉验收 | 以上所有只能算数据层；键盘实际观感需真机对比 | 待真机 |

---

## 11 复跑命令（从仓库根目录）

```bash
# 1) 下载官方线上 bundle（只读，落盘到 capture/official_music_live/）
curl -sL https://ajazz.driveall.cn/lighting -o capture/official_music_live/lighting.html
curl -sL https://ajazz.driveall.cn/assets/layout-classic-CMxiG14P.js -o capture/official_music_live/layout-classic-CMxiG14P.js

# 2) 组合采样（默认不开 HID 监听；--amp 会重置会话，慎用）
driver/.venv/Scripts/python.exe probe/capture_official_music_v2.py --per 4 \
  --out capture/official_music_colors3.jsonl

# 3) 分析（统计表 + 可选 ASCII 图案）
driver/.venv/Scripts/python.exe probe/analyze_official_music.py \
  --input capture/official_music_colors3.jsonl --grids \
  --out capture/official_music_analysis3.txt
```

> 注：官方 Music.exe 需先运行（`%LOCALAPPDATA%\Programs\AjazzDriver\Music\MusicPlug.exe -hide`，随官方驱动安装）；采样期间音乐播放、勿操作官方页面。

---

## 12 证据索引

| 文件 | 大小 | 说明 |
|---|---|---|
| `capture/official_music_live/layout-classic-CMxiG14P.js` | 3,335,710 B | 线上 v1 音乐 UI/参数表（offset ≈2,301,704） |
| `probe/capture_official_music_v2.py` | 11,374 B | 采样器（layout→param→100ms 轮询；可选帧监听/振幅） |
| `capture/official_music_colors3.jsonl` | 5,172,142 B | 29 组 × 4s × 10Hz × 102 键颜色（成功数据） |
| `capture/official_music_analysis3.txt` | 2,955 B | 统计表 + 代表模式 ASCII 图案 |
| `capture/official_music_colors.log` / `_colors2.log` / `_colors3.log` | 4,6xx B | 三次采样控制台日志（含失败原因） |
| `docs/music-rhythm.md` | 14,768 B | 既有音乐逆向文档（v2 渲染器/协议，需按本文 §5 补帧规格差异） |
| `driver/mk87lib/music.py` | — | 我方现有实现基线（20fps/87 键） |

---

## 13 本次没有验证 / 不要写成已通过

- 键盘在官方 60fps/108 项帧流下的**实际观感**（需要真机对比）——待真机。
- 官方帧 108 项与设备 87 键的**槽位映射**——未解。
- 66fps 是**由包率推算**（未逐帧打时间戳）；分辨率/抖动未测。
- 官方渲染公式与我们的实现逐帧差异——尚未做逐帧 diff（§10 方案 C）。
- 模式 10/11 的 UI 标签最终对应——待核对。

---

## 14 2026-11-02 晚：音乐页键盘预览双方案（当前方案 / 官方方案）

### 14.1 需求澄清（用户原话要点）

| 项 | 内容 |
|---|---|
| 需求 | 「音乐律动他那个 UI 就一种动画……把那个改掉」→「律动那块做两个切换标签，一个是现在，一个是官方方案」 |
| 范围澄清 | 用户后来明确：「不是彻底改 UI，是键盘上面亮的那个动画只有一种」——最终只改音乐页的键盘可视化，不大改整体 UI |
| 后端 | 「不用大改 UI，就是微调后端就可以了」——只加预览需要的数据通路，不动设备协议/渲染公式 |
| 落点 | 键盘可视化标题右侧加 `当前方案 / 官方方案` 双标签；官方方案 = 回放**后端实际发给键盘的那一帧**，屏幕与键盘同源 |

### 14.2 协作决策（为什么不派队友）

- 最初按「整体重做 UI」评估，考虑过派一名前端队友（`web/` 文件域）自己接后端（`mk87lib/` + `server/`）。
- 需求澄清后，实际改动集中在 **1 个页面 + 1 个 WS 事件 + mock/i18n**，跨前后端但总量约 10 个文件、+250 行；派队友的上下文交接与文件协调成本大于收益。
- 结论：**自己改**。验证用 headless Chrome 自检脚本补上「没有队友帮看」的缺口。

### 14.3 后端实现（微调，不动协议）

| 文件 | 改动 | 要点 |
|---|---|---|
| `driver/mk87lib/music.py` | `MusicEngine.last_colors`、`MusicPlayer.last_colors`；start/stop/finally 重置；`status()` 运行中返回 `colors` | 颜色 = `tick()` 里构建 `build_frame_payload(colors)` 的**同一份 colors**，不是另算一套 → 预览与设备实发帧同源 |
| `driver/server/state.py` | `_music_level_loop` 升级为双事件；新增 `_music_frame_event()` | `music_level` 保持 10fps；新增 `music_frame` 跟随引擎 fps（默认 20fps）；还没出帧时不推 |

新增 WS 事件（契约已写入 `driver/docs/design.md` §4.9）：

```json
{"type":"music_frame","data":{"mode":13,"frame":123,"fps":20,
                             "colors":{"4":[255,0,0], "5":[0,128,255], ...}}}
```

- `colors` = 87 个 keyValue → `[r,g,b]`，与 0x32 帧载荷同一 colors dict。
- `GET /api/music/status` 运行中同样带 `colors` 快照（刷新页面/切标签立刻有画面）。
- 未改设备协议、未改官方渲染公式、未加依赖、未改 `server/app.py`（music 路由直接返回 `status()`）。

### 14.4 前端实现

| 文件 | 改动 |
|---|---|
| `driver/web/js/pages/music.js` | 「键盘可视化」标题右侧 `createTabs` 双标签；选择持久化 `localStorage["mk87.music.preview"]`；当前方案=原频谱列动画（标注「非设备输出」）；官方方案=回放 `ws:music_frame` 逐键颜色；停止清色；无帧显示「等待首帧…」；模式选择器改全宽一行并 `small`，避免中文名折行 |
| `driver/web/js/mock.js` | 无硬件也能看双标签：mock 音乐循环按 4 个官方模式生成**近似**逐键帧并广播 `music_frame`；`/api/music/status` 带 `mode/modes/colors` |
| `driver/web/js/i18n-en-dom.js` | 新增 14 条英文（标签/说明/状态/律动中/toast 等） |
| `driver/web/js/app.js` | 修 EN 首屏 `<html lang>` 未同步：`applyLanguageToDom()` 里设置 → 否则页面模块里的 `LANG_EN` 读到 `zh-CN`，动态模式名（律动节拍等）不翻译。这是本次英文自检发现的**既有小 bug** |
| `driver/web/css/app.css` | `.segmented button` 加 `white-space: nowrap`（防模式名折行） |
| 文档 | `driver/docs/design.md` §4.7/§4.9 补 `status.colors` 与 `music_frame`；`driver/README.md`、`driver/web/README.md` 更新音乐页说明 |
| 测试/工具 | `driver/tests/test_music_preview.py`（4 个离线回归）；`driver/tools/ui_shots.py`（headless Chrome CDP 截图 + 自检，不依赖 Playwright） |

两方案文案对照（中文源）：

- 当前方案：hint「本地频谱预览（非设备输出）」/ 说明「按键颜色 = 所在列的频率强度，是本工具自己的可视化；与设备实际输出无关」
- 官方方案：hint「设备实发帧（官方渲染器）」/ 说明「官方渲染器实发帧：逐键颜色与键盘同步」+ 模式 badge +「实时回放中 / 等待首帧…」+ `20 fps`

### 14.5 验证证据（已实测）

| 检查 | 命令 / 结果 | 判定 |
|---|---|---|
| 后端语法 | `python -m py_compile mk87lib/music.py server/state.py` | OK |
| 渲染器颜色 | 13/14/17/4/1 各 tick 30 次：87 键、载荷 348B、存在非黑颜色（mode 14 有 44 键非黑、mode 13 有 78 键非黑） | OK（无设备） |
| 单元测试 | `python -m unittest discover -s tests -q` → **Ran 38 tests, OK**（原 34 + 新增 4） | OK |
| 真实后端 JSON | `run.py --no-connect --port 8478` → `GET /api/music/status` 返回 `mode/modes/colors:{}`，无 500 | OK |
| 前端自检 | `tools/ui_shots.py` 对 `http://127.0.0.1:8123/?mock=1#music`（headless Chrome 156） | **PASS 7/7** |
| 自检项 | boot+tabs / start-clicked / current-preview-painted(87) / official-tab-clicked / official-preview-painted(87) / stopped-clears-colors(0) / en-mode-no-cjk | 7/7 PASS |
| 控制台错误 | `Runtime.exceptionThrown` + `console.error` + `Log.error` = **0** | PASS |
| 截图 | 01 空闲 / 02 当前方案运行中 / 03 官方方案运行中 / 04 官方方案停止后 / 05 官方方案·英文浅色 | 见 §14.7 |

`capture/ui_music_preview/report.json` 原文摘要：

```json
{"checks":{"boot+tabs":true,"start-clicked":true,"current-preview-painted":true,
 "official-tab-clicked":true,"official-preview-painted":true,
 "stopped-clears-colors":true,"en-mode-no-cjk":true},
 "errors":[],"tabs":["当前方案","官方方案"],
 "currentPainted":87,"officialPainted":87,"stoppedLeft":0,"cjkLeft":[]}
```

复跑命令：

```bash
# 纯前端 mock + headless Chrome 自检（不需要设备/后端）
cd driver
.venv/Scripts/python.exe -m http.server 8123 --directory web --bind 127.0.0.1
.venv/Scripts/python.exe tools/ui_shots.py "http://127.0.0.1:8123/?mock=1#music" ../capture/ui_music_preview

# 离线回归（含新增音乐预览测试）
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

### 14.6 证据索引（本地 untracked 文件）

| 文件 | 大小 | SHA256 前 16 位 | 说明 |
|---|---|---|---|
| `capture/ui_music_preview/report.json` | 468 B | `8255577DFA541DC1` | 自检结果（7/7 PASS、0 error） |
| `capture/ui_music_preview/01-music-current-idle.png` | 221,782 B | `07E6A909DC192ED5` | 未开始：双标签 + 当前方案说明 |
| `capture/ui_music_preview/02-music-current-running.png` | 293,578 B | `69914D4C6DD99643` | 当前方案运行中（频谱列动画） |
| `capture/ui_music_preview/03-music-official-running.png` | 290,109 B | `5F962536BB8510C3` | 官方方案运行中（回放逐键帧 + 模式 badge + 实时回放中 20 fps） |
| `capture/ui_music_preview/04-music-official-stopped.png` | 228,428 B | `5B204FD90396F229` | 停止后键盘无残留色 |
| `capture/ui_music_preview/05-music-official-en-light.png` | 272,959 B | `51FE73FC6B19DCB7` | 英文 + 浅色主题（无中文残留） |
| `driver/mk87lib/music.py` | 39,143 B | `3B0681CFC4164894` | 渲染器 + 颜色快照 |
| `driver/server/state.py` | 18,765 B | `106B8ACAC4F0001F` | WS 双事件 |
| `driver/web/js/pages/music.js` | 19,145 B | `9520AC8A92125835` | 双标签预览 |
| `driver/web/js/mock.js` | 42,146 B | `9BAA402F22009BD0` | mock 近似帧 |
| `driver/web/js/i18n-en-dom.js` | 52,575 B | `735C67D409EBA345` | 新增英文 |
| `driver/web/js/app.js` | 19,881 B | `58C7F7FCB58F6785` | lang 同步修复 |
| `driver/web/css/app.css` | 63,822 B | `9798963495447824` | segmented 不折行 |
| `driver/tests/test_music_preview.py` | 2,784 B | `9608062AA4ACBCAD` | 4 个离线回归 |
| `driver/tools/ui_shots.py` | 12,932 B | `8EF270AB2FE79B86` | CDP 自检脚本 |

### 14.7 本次没有验证 / 不要写成已通过

- **真机视觉验收**：「官方方案」预览与键盘实际颜色的逐键一致性，需要 USB 接键盘 + 播放音乐实测；本次没接硬件。此前的教训（§7）是不要在插件流式发帧时开读句柄，本次流程本身不读句柄，但仍需真机才能验收。
- mock 的「官方方案」动画是**近似占位**（`mock.js` 里按模式画的），不是后端渲染器输出；真实观感以后端 `music_frame` 为准。
- WS 20fps × 87 键（≈1.5 KB/帧、≈30 KB/s）只在本地 mock 路径跑过；真实后端 + 慢客户端未压测（订阅队列满时会丢事件，不阻塞音乐线程）。
- 30/40fps 档位下 `music_frame` 的实际推送频率未实测（后端按 `music.fps` 计算间隔，前端 fps 文本读事件字段）。
- 官方 v1 的 8 包 / 108 项 / ≈66fps 帧规格**没有**用到「官方方案」——它回放的是我方官方渲染器的实发帧；真正对齐 §5 帧规格仍是 §10 的方案 A。

### 14.8 待决 / 下一步

| # | 事项 | 说明 |
|---|---|---|
| 1 | 真机视觉验收 | USB 接键盘 + 音乐，对比「官方方案」预览 ↔ 键盘实际颜色；确认 mode 13/14/17/4/1 观感 |
| 2 | 未开始时的官方演示 | 现在未开始显示「开始律动后显示实时回放」；若想静态预览，可回放采样帧（需另做） |
| 3 | 帧规格对齐（承接 §10 方案 A） | 官方 8 包/108 项/≈66fps 是否作为第三方案实现，待观感验证后再定 |
| 4 | 本次改动提交/推送 | 见 §14.9 |

### 14.9 仓库状态（本节结束时实测，2026-11-02 21:01）

- 本地 `main` HEAD 仍 = `2ff1e3e`；本节改动**全部未提交**。
- 已跟踪文件改动 10 个：`driver/README.md`、`driver/docs/design.md`、`driver/mk87lib/music.py`、`driver/server/state.py`、`driver/web/README.md`、`driver/web/css/app.css`、`driver/web/js/app.js`、`driver/web/js/i18n-en-dom.js`、`driver/web/js/mock.js`、`driver/web/js/pages/music.js`（`git diff --stat`：+251 / −31）。
- 新增未跟踪 2 个：`driver/tests/test_music_preview.py`、`driver/tools/ui_shots.py`。
- 仍是未跟踪（上一节调研产物）：`docs/DEVLOG.md`、`probe/*.py`、`capture/official_music_*`、本节 `capture/ui_music_preview/`。
- 未改：`driver/web/js/data/*`、`driver/server/app.py`、打包/CI 配置。

---

## 15 2026-11-02 晚间：发布 v0.1.1（已上线）

### 15.1 做了什么

| 项 | 内容 |
|---|---|
| 发布页 | GitHub Release `v0.1.1`（tag `v0.1.1` → 提交 `bbb5c58`），由 CI 自动构建并发布 |
| 版本号 | `0.1.0 → 0.1.1`，7 处：`mk87lib.__version__`、`server.VERSION`、`status.webVersion`、Windows `version_info.txt`（filevers/prodvers/FileVersion/ProductVersion）、`mk87.iss`、Linux `mk87.spec` |
| Release notes | `.github/release-notes.md` 新增「v0.1.1 更新」段（音乐预览双标签、英文 lang 修复、测试/自检脚本、WS 文档）；功能表音乐条目补「当前方案 / 官方方案」 |
| 修掉的发布隐患 | `mk87.spec` 的 `Version:` 之前硬编码 `0.1.0`，而 `build-rpm.sh` 虽传 `--define version_override`，spec 没接 → 升版本后 RPM 会锁死旧版本号。现改为 `%{?version_override}%{!?version_override:0.1.1}` |
| CI | tag 触发 run #14（`41452181866`）：offline tests（win/ubuntu）、linux deb+rpm、windows portable+installer、publish release **全部 success** |

### 15.2 发布页实测（2026-11-02 21:27 +08:00）

- URL：https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.1 （`draft=false`、`prerelease=false`）

| 资产 | 大小（字节） | SHA256（前 16 位） |
|---|---|---|
| `MK87Studio-0.1.1-win64-portable.zip` | 38,966,363 | `3dcdd3ee1ffc634e` |
| `MK87Studio-0.1.1-win64-setup.exe` | 30,116,590 | `61661e3595b95e11` |
| `mk87_0.1.1_amd64.deb` | 207,913,858 | `e67150c0afe7cf1d` |
| `mk87-0.1.1-1.x86_64.rpm` | 248,454,402 | `d05192cd9ed4c0b0` |
| `SHA256SUMS.txt` | 378 | `1832cc978b3d33d1` |

### 15.3 复跑 / 排查命令

```bash
# 触发发布：打 tag 并推送（CI 自动构建 + 发布；版本号先按 §15.1 的 7 处同步改好）
git tag -a v0.1.1 -m "MK87 Studio v0.1.1" && git push origin v0.1.1

# 查看构建与产物
curl -s "$API/repos/w32394045-dotcom/ajazz-mk87/actions/runs?per_page=3"
curl -s "$API/repos/w32394045-dotcom/ajazz-mk87/releases/tags/v0.1.1"
```

### 15.4 未验证 / 注意

- 安装包体积：Linux deb/rpm 约 200–240MB（PyInstaller 打包 Qt/WebEngine 的既有现象，v0.1.0 相同）——本次未优化。
- **v0.1.1 安装包里的音乐双预览效果仍需真机验收**（同 §14.7）。
- Windows 安装包在 CI 里 `continue-on-error: true`，本次实际成功；若以后失败，release 仍会发布但会少 `setup.exe`（release job `fail_on_unmatched_files: false`）。

### 15.5 发布页改版：README 风格 · 双语 · 截图 · MIT（2026-11-02 21:33）

| 项 | 内容 |
|---|---|
| 需求（用户原话） | 「更像 readme，双语，再加截图」「还有加个 MIT」 |
| 发布页 | `.github/release-notes.md` 重写为 README 风格（10,858 B）：双语标题 + tagline、6 张截图表格、v0.1.1 更新、下载、功能、已知限制、源码运行、文档入口、许可、免责声明 |
| 截图 | 固定 `v0.1.1` tag 的 `raw.githubusercontent.com` URL（不随 main 变化）：UI 浅色/深色（真机）、TFT 屏幕、日志与设置、音乐页「当前方案 / 官方方案」（后两张为演示模式截图）；**6/6 URL 实测 HTTP 200** |
| 许可 | 新增根目录 `LICENSE`（MIT · Copyright (c) 2026 w32394045-dotcom，1,073 B）；根 `README.md` 与 `driver/README.md` 增加许可段；`mk87.spec` `License: Freeware → MIT`；Windows `version_info.txt` 的 `LegalCopyright` 改为 MIT；并注明 `assets/`、`tools/Music.exe` 等原厂提取物**不在 MIT 授权范围** |
| 上线方式 | 不重打 tag：用 GitHub API `PATCH /releases/431494652` 更新已发布的 v0.1.1 页面正文；发布页 HTTP 200，正文含 6 张图 / 许可 / 双语段落 |
| 事故（已修） | 第一次 PATCH 用 PowerShell `Invoke-RestMethod -Body <byte[]>`，GitHub 把正文存成了 PowerShell 对象字符串（`{"value" => "...\\n..."}`，33,570 字符、0 个真实换行、页面渲染错乱）。改用 Python `urllib.request` + `json.dumps` PATCH 后恢复正常：8,588 字符 / 10,858 B（与本地文件一致）、148 个真实换行、6 张图 |
| 防复发 | GitHub API 的写操作统一用 Python urllib（或 `curl --data-binary @file -H 'Content-Type: application/json'`），不用 PowerShell 的 byte[] `-Body` |
| 验证 | 发布页 `https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.1` 返回 200；API 读取正文：`startswith('# MK87 Studio')`=True、含 `界面 / Screenshots`、`许可 / License`、`MIT License`、`v0.1.1 更新`，6 个图片 URL 全部 200 |
| 备注 | deb 控制文件本身没有 License 字段（Debian 规范），RPM spec 的 `License: MIT` 生效；已发布的 v0.1.1 安装包内不含 LICENSE 文件，下一个版本会随打包带 README 许可段 |

### 15.6 README 双语独立化 + 截图内嵌 + 本地包重建（2026-11-02 21:45）

| 项 | 内容 |
|---|---|
| 用户澄清 | 「完全独立的双语（EN 为默认）」+「截图直接内嵌到 README」——不是同一段里中英逐行对照 |
| README | `README.md` 重写为英文（仓库默认语言）；新增 `README.zh-CN.md` 独立完整中文版；两文件顶部互相链接 |
| 截图内嵌 | 6 张图改用仓库相对路径（`driver/docs/screenshots/*.png` + `capture/ui_music_preview/*.png`），GitHub 仓库首页直接渲染；音乐两张标注为演示模式 |
| 发布页 | `.github/release-notes.md` 改为英文默认（满足 EN 默认），中文入口链接到 `README.zh-CN.md`；截图不再重复放在发布页，改为链接 README |
| 本地包重建 | 删除旧 `driver/dist/MK87Config` 后执行 `packaging/windows/build-portable.ps1`：`MK87Config.exe` 10,390,408 B / FileVersion **0.1.1.0** / LegalCopyright 含 MIT；便携包 `driver/dist-packages/MK87Studio-0.1.1-win64-portable.zip` 39,893,935 B；已确认打包内 `_internal/web/js/pages/music.js` 含「当前方案 / 官方方案」新代码 |
| 交付路径（真机验收用） | `driver\dist\MK87Config\MK87Config.exe`（双击即用，免安装）；便携 zip 见上 |


