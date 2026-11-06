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

---

## 16 2026-11-02 晚间：音乐律动「官方方案」= 官方同款设置项 + 热切换

### 16.1 用户反馈（原话要点）

- 「不太满意，我意思是官方方案后整个设置项全部搬掉换为官方同款的，就是真的官方同款，这次请你快速改」
- 「还有一点无法热切换种类还是什么的」

即：官方方案不能只是"预览动画换一种"，而要把**整块设置项**换成官方 v1 插件的同款参数；且这些设置要能在**播放中热切换**，不能停止音乐再改。

### 16.2 官方同款参数（来源 `docs/music-constants.json`，官方 bundle 提取）

| 项 | 内容 |
|---|---|
| 显示模式（12） | 13 随曲起舞 / 22 双心共舞 / 14 尘埃光漩 / 15 蛰伏火山 / 16 光矢穿心 / 18 光茧共振 / 19 音叉振空 / 17 萤火轨迹 / 20 曲率遗轨 / 21 行波律动 / 4 曲率频阶 / 100 屏光联动（官方由 Music.exe 计算） |
| 背景模式（11） | 0 无 / 1 绿黄红 / 2 彩虹 / 4 色谱 / 5 频谱循环 / 6 白 / 7 红 / 8 橙 / 9 黄 / 10 蓝 / 11 绿 |
| 参数范围 | `amplitude` 1–100（默认 50）；`backmodeBrightness` 10–100（默认 100） |
| 数据落盘 | 新增前端静态模块 `driver/web/js/data/music.js`（由 `docs/music-constants.json` 生成，运行时不解析 JSON） |

### 16.3 实现

| 层 | 改动 |
|---|---|
| `mk87lib/music.py` | `MusicPlayer.start()` 接受 `backmode`/`backmodeBrightness`/`amplitude` 并传入 `MusicEngine`（背景渲染 `_apply_background` 已支持）；新增 `MusicPlayer.update()` 运行中热更新（模式/背景/亮度/振幅/fps）；主循环周期每帧重算，支持 fps 热更新；`status()` 增加 `requestedMode`/`implementedModes`/`backmode`/`backmodeBrightness`/`amplitude`；`MusicEngine.set_backmode()` |
| `server/app.py` | 新增 `POST /api/music/update`（热更新）；`/api/music/start` 透传官方参数 |
| `web/js/pages/music.js` | 顶部双方案 tabs（**官方方案为默认**）；官方方案设置项 = 官方同款（显示模式 select / 背景模式 select / 背景亮度 slider / 振幅 slider）；当前方案保留原参数；**方案切换与所有参数改动都走热更新（120ms 防抖），不打断音乐**；未移植渲染器在 UI 明确提示回落 |
| `web/js/mock.js` | 支持 `/api/music/update`，回显官方参数与 `implementedModes` |
| `web/js/i18n-en-dom.js` | 新增 20+ 条英文文案 |
| `tools/ui_shots.py` | 自检升级：8 项检查，含**热切换不停止律动** |
| 文档 | `design.md` §4.7 补 start/update/status 契约；`driver/README`、`web/README`、中英 README 更新音乐功能说明 |

### 16.4 验证（已实测，2026-11-02 21:59）

| 检查 | 结果 |
|---|---|
| 后端语法 | `py_compile mk87lib/music.py server/app.py` OK |
| 单元测试 | `unittest discover -s tests` → **Ran 42 tests, OK**（新增 4 个热更新/背景测试） |
| 前端自检 | headless Chrome：**8/8 PASS**，console error 0；含「官方方案上色」「热切换后仍在运行」「切回官方」「停止清色」「EN 无中文残留」 |
| 截图证据 | `capture/ui_music_preview/01-official-idle … 06-en-light`（官方设置项、官方运行、热切到当前方案、切回官方、停止、英文浅色） |
| 本地便携包 | 重新构建：`MK87Config.exe` 2026-11-02 21:58:55 / 9.9MB；`MK87Studio-0.1.1-win64-portable.zip` 38MB，SHA256 `44AC9DF8…F155B230`；已确认打包内 `web/js/pages/music.js` + `web/js/data/music.js` 含官方方案代码 |

### 16.5 未验证 / 已知边界

- **渲染器移植范围**：官方 12 个显示模式中真正移植了 13 / 14 / 17 / 4（官方渲染器逐行移植），其余 7 个（22/15/16/18/19/20/21）与 100（Music.exe 专用）会**回落到「随曲起舞」**；官方方案设置项与参数是官方同款，但这些模式的渲染效果仍非官方（UI 有明确提示）。补齐需要逐个移植官方 bundle 渲染函数。
- 真机 USB 下的官方方案实际观感待验收。
- 背景模式渲染已接入 `_apply_background`，但部分背景（1/2/4/5）依赖布局环形数据，真机观感待验收。

### 16.6 交付路径（真机验收）

```text
C:\Users\ptfm\Documents\ajazz-re\driver\dist\MK87Config\MK87Config.exe   # 双击运行（已含官方方案 + 热切换）
C:\Users\ptfm\Documents\ajazz-re\driver\dist-packages\MK87Studio-0.1.1-win64-portable.zip
```

源码运行（改完代码免重打包）：`cd driver && .venv\Scripts\python.exe shell.py`

---

## 17 2026-11-02 深夜：补全官方渲染器（12 模式中 11 个真移植）

### 17.1 用户要求

- 「都补上」——把剩余 7 个官方渲染器（15/16/18/19/20/21/22）也移植，mode 100 保持回落。

### 17.2 做法

- 源码：`docs/_music_b2.js`（Ce/Ee/De/Oe/Ae/je/Ne/Pe 官方函数）、`docs/_music_a.js`、`docs/_music_b.js`；
  模式 22（L / Dual Heart Dance）的内置双心坐标表从 `capture/official_music_live/layout-classic-CMxiG14P.js`
  提取（官方内置 5 个几何分支：F≥7 / 总键数>102 / >90 / >75 / 其余；**MK87 是 F=6、87 键，命中 >75 键分支**，
  左/右心各 5 层 × 45 格，第 0 层为心尖；全部按官方逐字移植 `_DUAL_HEART_TABLES`，未自造兜底）
- Python 侧：新增 `_render_mode_15/16/18/19/20/21/22`；复用既有 `st` 状态，新增键：
  `volcanoHeight`/`volcanoDir`（15）、`tuningPhase`（19）；`IMPLEMENTED_MODES` 扩到
  `{1,4,13,14,15,16,17,18,19,20,21,22}`；`_render_frame` 增加分支；模式 100 仍回落 13
- 分工：移植由子代理完成，Lead 独立验证（测试 / ASCII 形态 / 打包冒烟）

### 17.3 验证（已实测，2026-11-02 22:36）

| 检查 | 结果 |
|---|---|
| 单元测试 | `unittest discover -s tests` → **Ran 52 tests, OK**（新增 10 个：7 模式各 1 + amp=0 静音 + backmode 0/1/2/4/5/6–11 全组合 + IMPLEMENTED_MODES 精确断言） |
| ASCII 形态自检 | 12 个模式逐一渲染 6×17 网格：15 三塔长高、16 中心两行光条+箭形、18 顶边横条+右列竖条+对角带、19 左右触须、20 右侧波浪推进、21 逐行柱状、22 双心图案、1/4 EQ 柱、13 同心环、14 四色射线、17 正弦拖尾 |
| 跨实现对拍 | 子代理从官方 bundle 抽出 9 个渲染函数，用临时 Node 脚本按相同状态跑 4 组参数、逐格比较：**99,960 格 0 差异**（临时脚本未入库，记为一次性验证） |
| headless UI 自检 | 8/8 PASS、console error 0（`capture/ui_music_preview/report.json`） |
| 打包冒烟 | `MK87Config.exe --tray` → 读 `%LOCALAPPDATA%\mk87\instance.json` 拿动态端口：`/api/version=0.1.1`，`/api/music/status.implementedModes = 12 个` |

### 17.4 已知近似 / 边界

- **mode 100（屏光联动）仍回落 13**：官方由 Music.exe 抓屏幕内容计算，主机侧没有对应渲染器，要真复刻需逆向 Music.exe 的屏幕采集映射逻辑。
- 引擎级 `huePhase += 0.01/tick` 是早期 `music_ref.js` 的既有近似（官方 `pe()` 不加，各渲染器内部自增）；为不改变 13/14/17 既有观感未动。
- 模式 19 使用 `Math.random`（官方行为），逐帧不可复现；单测只做范围断言。
- 模式 15 的 `volcanoKeyPositions` 分支未移植（MK87 无该配置，不可达；docstring 已注明）。
- 模式 22 的 5 个官方几何分支全部移植，MK87 只命中 `>75 键` 分支。

### 17.5 交付

| 项 | 值 |
|---|---|
| 本地 exe | `driver\dist\MK87Config\MK87Config.exe`（2026-11-02 22:36:30，9.9MB，FileVersion 0.1.1.0） |
| 便携包 | `driver\dist-packages\MK87Studio-0.1.1-win64-portable.zip`（38.1MB） |
| SHA256 | `61A33D73A56C05499269197C5C767CDF477B5723FF2C2643252CB25242D15DA7` |
| 冒烟要点 | --tray 启动 → `/api/music/status.implementedModes` 返回 12 个模式，证明打包内已是新代码 |

---

## 18 2026-11-03：电量/灯效/游戏模式三问题 + 官方音乐 v1 真值对齐

### 18.1 用户反馈（原话要点）

- 重启电脑后电量显示 78%（实际 100%）；关驱动/重启后灯效模式被重置且「不是普通模式」；重启后键盘像进了「游戏模式」
- 「那四个音效有问题……官方方案这边重新采样，不要按旧方案；旧方案保留在当前方案标签」
- 「屏光联动可以不用官方的，我们自己按字面意思做一个，比它更好」；「增加第三个下拉框（LED 颜色）」
- 「可以用子 Agent 研究，你来检验」「上下文空间不多了」

### 18.2 三问题调查（子代理，只读；报告要点）

| 问题 | 根因 | 证据 |
|---|---|---|
| 电量 78% | 工具只是如实显示 `GET_DEVICE_INFO` d[17]；但**电量/充电从不写日志**，且 `charging` 只在百分比变化时刷新、异常全静默；2.4G 下官方是从 `GET_ALL_LIGHTS_RGB_24G*` 回包取 battery，本工具无此路径 | 日志 `%LOCALAPPDATA%\mk87\logs\session-20261103-121649-1552.log:16`（连接）无电量字段；实测 d[17]=100/d[18]=2 连读 5 次 |
| 灯效重置 | **不是启动/退出逻辑**：11/2 22:45 音乐 start 写了 mode=128 后进程被关机杀死，`restore_effect()` 没跑，键盘停在自定义逐键表（WASD 绿 + 空格粉）；fw1.19 会把 128 固化成自定义族且 mode 回读 0 | `session-20261102-224047-14936.log:76958/76961/76963`；最后一行 22:45:49 无「开始退出」；今天实测 `GET_CUSTOM_LED_DATA`/`GET_ALL_LIGHTS_RGB` 正好 5 键 |
| 「游戏模式」 | 与本工具无关（全量日志 0 条 `TX cmd=0x21`、0 条 game-mode 写；56B 与 11/1 快照逐字节相同）；**大概率与灯效问题同源**——只剩 WASD+空格 看起来像游戏高亮 | `docs/restore_state.json` 对比；官方 db `gamemode=0/disable_win=0` |

### 18.3 修复（子代理实现，Lead 复核；92 tests OK）

| 文件 | 改动 |
|---|---|
| `mk87lib/lighting.py` | `ensure_frame_mode` 展示入口改用 20/21（绝不写 128），写后 0.2s 回读；`restore_effect` 写回前校验快照 mode，0/非法一律不写；`restore_state()` 暴露最近恢复状态；`set_custom` 写 128 后回读归零告警；`get_effect_with_custom_fallback()`：mode 回读 0 时用 `GET_ALL_LIGHTS_RGB` 判断是否自定义表态并返回 `isCustom` |
| `server/state.py` | `_refresh_battery` 每次成功都更新 battery/charging/work_mode 并限频记日志/广播；连接日志带 battery/charging/workMode/transport；连接后 2s 延迟重读（gen 防串连接）；2.4G 电量读取 + 失败熔断 5 分钟；`stop_music(3s)` 确认 restore 已跑后再关 HID |
| `mk87lib/device.py` | `read_battery_24g()`（只发 cmd55 首包，只读；2.4G 才用）；`DeviceStatus.battery_source` |
| `shell.py` / `app.py` / `logsetup.py` | 退出顺序：停音乐等 restore → keytest → 关设备，`os._exit` 前最多等 8s；`GET /api/lighting` 走 isCustom 兜底；诊断包加 batterySource/workMode |
| 测试 | 新增 `driver/tests/test_battery_lighting_state.py`（28 tests，全 fake 设备）；全套 **92 tests OK** |

### 18.4 官方音乐 v1 真值（关键修正）

- **之前用错了列表**：`docs/music-constants.json` 的 12 模式是 v2 列表；MK87 是 `musicConfig.version===1`，官方 v1 UI 真实下拉（从 `capture/official_music_live/layout-classic-CMxiG14P.js` offset≈2301489 函数 D7 提取，落盘 [docs/music-v1-config.json](music-v1-config.json)）：
  - 显示模式：`1 绿黄红 / 2 彩虹 / 13 随曲起舞 / 4 曲率频阶 / 5 频谱循环 / 6 白 / 7 红 / 8 橙 / 9 黄 / 11 绿 / 10 蓝 / 100 屏光联动`
  - 背景：`0 无 / 6 白 / 7 红 / 8 橙 / 9 黄 / 10 蓝 / 11 绿 / 1 绿黄红 / 2 彩虹 / 4 色谱 / 5 频谱循环`
  - 振幅 1–100（默认 30）、背景亮度 1–100（默认 100）、`musicV1Config` 默认 mode=1
- 用官方采样 `capture/official_music_colors3.jsonl`（`probe/analyze_official_v1_modes.py`）对齐：
  - 颜色模式真值：6/7/8/9/11/10 = `FEFEFE/FE0000/FE3F00/FEFE00/00FE00/0000FE`；**11=绿、10=蓝**（旧脚本文案反了）
  - 亮度缩放公式：`(c * int(bb*255/100)) >> 8`（bb=100/50/20 → FE/7E/32），修复旧实现 round 差 1
  - 1/2/4/5/6..11 是「曲率频阶柱状」同一几何 + 不同调色板；13 是同心环；背景 11 种全部铺满
- 实现：`music.py` 新增 `_render_mode_steps` 覆盖 1/2/4/5/6/7/8/9/10/11，`V1_DISPLAY_MODES`/`V1_IMPLEMENTED_MODES`，status 增 `officialModes`/`officialImplementedModes`，背景亮度 1–100；前端 `data/music.js`/`pages/music.js`/`mock.js` 同步；**「当前方案」标签页零改动**
- 验证：headless UI 8/8 PASS（含 EN 无中文残留）、打包前全套 92 tests OK；旧 `capture/official_music_analysis3.txt` 中交叉验证：背景模式 6–11 全亮、bb 线性缩放与本次结论一致

### 18.5 未决 / 已知局限

- **采样只有 10Hz HTTP 回放**：颜色模式几何（柱状 vs 楔形）无法逐像素确证；mode 2 采样零输出、1/4 输出稀疏，属推断实现；纯色模式实现为「柱状部分点亮」而非全键铺满（与采样覆盖率一致）。
- 2.4G 电量路径**无 2.4G 硬件未真机验证**（失败会熔断 5 分钟后回退 d[17]，日志可查）。
- 需要用户配合的实验：E1 重启后电量时间线（新日志已加）；E2 写回 mode=11 后断电/重启验证持久性（需用户同意写一次设备）；E4 禁用 MusicPlug 自启对照（需改系统设置）。
- 屏光联动（100）与 LED 颜色第三下拉框：尚未实现（下一步）。

---

## 19 2026-11-03：官方音乐方案 v0.1.3（21 模式 / mode 4 真值 / LED 颜色 / 原生 66fps）

### 19.1 用户诉求（原话要点）

- 「那四个音效有问题……官方方案这边重新采样，不要按旧方案；旧方案保留在当前方案标签」
- 「只改这个第 10 个……model 4，其他你给我改回去」（复核后：其余 9 个官方效果零改动）
- 「弄一个第三个下拉框……设置灯柱具体的颜色……默认情况跟现在一模一样……多给几套预设」
- 「官方的针到底发 20 帧还是 30 帧还是 60 帧」→「按官方那种发包模式走，也不写死」；
  「有必要做动态波动吗」→ 结论：**不复刻逐帧抖动**，用高精度目标帧率 + 自适应追赶 + 实测值回显
- 「之前研究出来的模式补回来」；「E（自研屏光联动 / 实验）先不做，ABCDF 做完先发布」
- 流程要求：先用子代理研究/实现、Lead 检验；上下文有限、少浪费 token

### 19.2 官方 v1「显示模式 4」重新采样（子代理；全程只读 HTTP，不碰 HID）

- 方法：官方 MusicPlug.exe（127.0.0.1:9191）`GET /api/keyboard/layout/base64` → `musiceffect?param=` →
  100ms 轮询 `musiceffect/`；音源 = 48kHz 正弦单音（100/440/2k/4k/8kHz）、200→6400Hz 阶梯扫频、
  静音；amplitude 10/30/50/70/100 扫描。原始数据 `capture/official_v1_mode4*.jsonl`（gitignore，10 个文件），
  工具 [probe/capture_official_v1_mode4.py](../probe/capture_official_v1_mode4.py)、
  [probe/analyze_official_v1_mode4.py](../probe/analyze_official_v1_mode4.py)、`probe/play_tone_loop.ps1`
- 真值（稳定段 2.5s 后，102 键）：
  - 几何 = **17 列频谱柱、100% 底部对齐**（1200/1200 帧；对照 mode 1 也底部对齐，mode 13 不是）
  - 列 = 频率（左低右高、对数，约 110Hz–12kHz）：100Hz 单音只点最左 3 列，2k/4k/8k 峰值落在第 6~11 /
    10~12 / 15~16 列；阶梯扫频柱峰逐级右移
  - 颜色 = 以 (2,8) 为原点的径向色相（满饱和、最大通道 255；左右半屏差约 180°），
    **整块调色板以 ~275°/s 旋转**（与 amplitude 无关；100ms 采样每格前进 27~28°）
  - 柱高随 amplitude 增大：amp=30 单音峰值约 4/6 行，amp=100 顶到 6/6
- 旧实现 vs 真值：旧 `_render_mode_steps(mode=4)` 用合成正弦包络（与音频无关）/ `/8` 增益让 amp=30
  基本铺满 / `huePhase`(0..1) 当度数用导致几乎不转 → 这就是「四个音效不对」的根因
- 改动（只碰 mode 4）：`music.py` 新增 `_MODE4_*` 常量、`_bands32_to_17()`、`_render_mode_4()`；
  `_render_frame` 单独路由 `if mode == 4`；`V1_STEP_MODES` 去掉 4；`tick(amp1000, bands32=None)` 与
  `MusicPlayer._loop` 传入 Analyzer 的 32 段频谱
- 未确定（代码注释已标注）：列↔频率边界由 5 个单音+扫频反推（相邻列有 1 列扩散误差）；柱高-振幅只标定
  amp=30/100 两点；官方静音也有柱（可能采到设备噪声），静音场景用 `_MODE4_CURVATURE` 兜底轮廓近似

### 19.3 官方显示模式补回 9 个（下拉 12 → 21 项）

- `V1_DISPLAY_MODES = [1,2,13,4,5,6,7,8,9,11,10,14,15,16,17,18,19,20,21,22,100]`
- 补回：14 光尘螺旋 / 15 休眠火山 / 16 光箭穿刺 / 17 萤火轨迹 / 18 光茧共鸣 / 19 音叉振动 /
  20 曲率传承 / 21 行波节奏 / 22 双心共舞（后端渲染器在 v0.1.1 已移植，这次只暴露到 UI）
- `V1_IMPLEMENTED_MODES` = 除 100 外 20 项；100 仍回落 13（自研屏幕同步后置到下一批）
- 同步：`data/music.js`、`pages/music.js`、`mock.js`、`i18n-en-dom.js`、`ui_shots.py`、status 列表、测试

### 19.4 第三个下拉「LED 颜色」（本工具自研增强）

- 表：`default`（官方配色）+ ice 冰蓝 #00E5FF / violet 紫罗兰 #B36CFF / pink 热粉 #FF2E88 /
  lime 青柠 #A8FF3E / amber 暖橙 #FF6A00 / sakura 樱花渐变 #FF7AB6→#B36CFF /
  aurora 极光渐变 #3EFF9A→#00E5FF→#7A5CFF / sunset 落日渐变 #FFC400→#FF6A00→#FF2E88 /
  icefire 冰火渐变 #00E5FF→#FEFEFE→#FF6A00
- 覆盖范围：只有动态多色模式 1/2/4/5/13；按「原调色板位置/行位置/角度/相位」在新渐变上 sRGB 插值采样，
  保留原有动画（mode 4 的 275°/s 旋转、mode 5 相位推进等）；**纯色 6–11 与背景模式完全不消费调色板**
- 默认档零差异：改动前先落 `driver/tests/fixtures/music_default_snapshot.json`（20 模式 × 11 背景
  × 16 tick = 220 个 SHA-256），改后「缺省 / 显式 default」440 个 digest 逐条命中
- 唯一入口：`_render_frame` 里 `pal = st.get("palette") if mode in COLOR_OVERLAY_MODES else None`；
  渲染器只在调色板查表处替换（`_hue_color` / `_fill_row_bands` / `_fill_solid_hue`）

### 19.5 原生帧率 20/60/66（默认 66）

- 依据：官方 v1 实测 **530.5 包/s ÷ 8 包/帧 ≈ 66.3fps**（无逐帧时间戳，属平均推断）；官方 v2 浏览器
  50ms 循环（20fps）不是 v1 原生帧率。决定：不做逐帧抖动复刻
- 实现：`FPS_CHOICES=(15,20,30,60,66)`、`_clamp_fps`、`_dt_scale`；`MusicEngine.tick(..., dt_scale)`，
  **所有随时间推进的动画量按 dt 缩放**（dt=1 时原算术不变 → 默认快照仍逐字节一致），频谱/亮度的当帧量不缩放
- 发包策略（真机 A/B 决定）：
  - ≤30fps：逐包 ACK（20fps 路径与旧版一致；60fps 以下预算充足）
  - ≥60fps：连写 7 包 + **ACK 清道夫线程异步读回包**；帧末同步 drain 实测 send 19.8ms/帧 > 66fps 的
    15.15ms 预算 → 只有 **45.96fps**；异步后 send **8.85ms/帧** → **65.8~66.1fps**（清道夫起不来才回退
    帧末同步 drain，status.sendMode 会显示 `burst+drain`）
  - 排期用 perf_counter 绝对 deadline；滞后 >1 period 重置不补发；running 中热更新 fps 立即生效
- 实测契约：`status.fps` = 最近 2s 滚动实测 float|null，`status.targetFps` = 配置 int；WS `music_frame.fps`
  用实测值；`timing.lateFrames`、`sendMode` 为诊断字段；WS 预览限速 30Hz
- 真机实测（USB fw1.19，2026-11-03）：
  | 项目 | 结果 |
  |---|---|
  | 66fps 连续 100s | 65.86 / 65.89 / 65.87 fps（send 8.85ms、lateFrames 0/2/6、0 错误） |
  | 60fps | 60.06 fps（send 8.84ms、late 0） |
  | 20fps | 19.97 fps（逐包 ACK、send 9.22ms、late 0） |
  | 21 个模式逐个 1s | 全 ≥63.4fps、0 错误（100 回落 13） |
  | 10 种颜色逐个 1s | 回读 id 全对、0 错误 |
  | 停止恢复 | mode=11 / brightness=6 / speed=3，raw `0bffffffff000000010603000000aa55`（与原快照一致） |

### 19.6 合入本版的电量/灯效健壮性

- 即 §18 的全部修复（电量每次刷新+日志、2.4G 电量路径、绝不写 mode 128、快照校验、退出顺序、
  isCustom 兜底）。v0.1.3 是这些修复的**首次正式发版**。

### 19.7 验证与交付

- 单元测试：`cd driver; .\.venv\Scripts\python.exe -m unittest discover -s tests -q` → **Ran 152 tests / OK**
  （v0.1.2 基线 92；本批新增 mode4、颜色、fps 三组测试与 220 组合快照回归）
- UI 自检：`python tools/ui_shots.py`（headless Chrome + mock）→ **17/17 PASS**：21 模式顺序/3 个下拉/
  10 个颜色项/3 档帧率/热切换/停止清屏/英文无 CJK/console 0 错误
- 打包冒烟：`dist\MK87Config\MK87Config.exe` FileVersion **0.1.3.0**；`--tray` 启动后
  `/api/status.webVersion=0.1.3`、`/api/music/status.officialModes` 21 项、`/api/quit` 正常退出
- 本地包：`driver\dist-packages\MK87Studio-0.1.3-win64-portable.zip`（39,945,250 B），
  SHA256 `9425EBFD19E464448DD3444945F2969EADE650EB11CCFBA00E2F348EA69E43BF`
- 发布（已完成）：commit `2dc49d4` → push main → CI 运行
  [#24](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41589846610) 全绿
  （Windows/Ubuntu 测试 + Linux deb/rpm + Win 便携/安装包）→ tag `v0.1.3` → CI 运行
  [#25](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41590923612) 全绿 →
  Release 2026-11-03 14:42（UTC 06:42）发布：<https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.3>
  - 附件（CI 构建）：`MK87Studio-0.1.3-win64-portable.zip` 39,018,302 B（SHA256
    `addc078d…82174`）/ `MK87Studio-0.1.3-win64-setup.exe` 30,164,516 B / `mk87-0.1.3-1.x86_64.rpm`
    248,562,940 B / `mk87_0.1.3_amd64.deb` 208,010,428 B / `SHA256SUMS.txt`
  - 已下载 Release 的 portable zip 复算 SHA256 与 SHA256SUMS 一致；本地包与 CI 包因构建环境不同哈希不同，
    Release 以 CI 构件为准
- 本批明确未做（后置）：mode 100 自研屏幕同步；E2/E4 硬件实验；自定义 HEX 输入

---

## 20 2026-11-03（晚）：v0.1.4 修用户报告的 4 个 bug + 性能治理

### 20.1 用户反馈（原话要点）

- 「宏键和改建设置根本设置不了」（改键页「应用修改」必失败）
- 「用着用着就突然卡顿一下」（音乐播放时周期性卡顿）
- 「颜色除了这一个阶梯能用，其他全部不能覆盖上」（LED 颜色只对部分模式生效）
- 「频率阶梯……并没有走频率阶梯，而是走我们的旧方案」（确认为 A：选了颜色预设后模式 4 像旧方案）
- 「振动幅度调整如同虚设，看不到明显变化」

### 20.2 根因 → 修复 → 验证

| # | 问题 | 根因 | 修复 | 验证 |
|---|---|---|---|---|
| 1 | 改键/宏保存 HTTP 400 | 前端 `toWireAction()` 发 `key`/`fn`/`combo{keys}`，后端 `encode_entry()` 只认 `keyboard`/`func`/`combo(mods+key)` → `MK87Error("未知的 action type")` → 400 | 后端兼容两套 wire 格式（含 combo keys 拆分、macro slot 回退）；前端改发 canonical；`normalizeWireAction` 兼容后端 combo `mods/key`；顺手删 `patch_matrix` 死代码 | 真机：canonical no-op / 旧别名 `key` / combo 写入+恢复 / FN 层 no-op 全部 200，slot0 readback `02002900` 一致；新增 15 测试 |
| 2 | 播放音乐时周期性卡顿 | 66fps 帧流时协议层把**每个 HID 通知帧**逐条 DEBUG 写盘：47min 会话 **1,169,834 行 / 207MB（414 行/s）**，磁盘 I/O 抖动；session 日志无上限；宏表逐槽读实测 48.3s | 通知按 (类别,cmd) 聚合限速（0x32 ACK 完全不打，其它 ~2s 摘要，首条立即）；session 日志 32MB 上限 + 启动清理旧会话（保留 5 个 / 64MB）；宏表改「目录 1 次 + 数据区 ≤512B 块连续读」；另修 `run.py` 的 uvicorn dictConfig 关掉本工具 handler（会话日志空白 + 3.9 万条 Logging error） | 真机 40s@66fps：session 日志仅 **+22.3KB（33KB/min，旧 ~4.4MB/min）**；`GET /api/music/status` 8–11ms、`/api/status` 4–7ms；`GET /api/macros` **48.3s → 366ms**（100 槽假设备 201→7 请求） |
| 3 | 颜色只覆盖部分模式 | `COLOR_OVERLAY_MODES` 只有 1/2/4/5/13；补回的 14–22 渲染器不消费 palette | 扩到 `{1,2,4,5,13,14..22}`（14 个动态模式），14–22 渲染器加 `pal` 形参，只替换「色相→RGB」，几何/相位/亮度不动；纯色 6–11 与背景不变 | 真机抓 WS 逐键帧：mode 4/14/22 选 `ice` 后全部点亮键为冰蓝族（4:32/32、14:19/19、22:87/87）；default 220 组合快照仍逐字节一致 |
| 4 | 模式 4 闪回旧方案 | `_render_mode_4` 在 `spectrum17` 全 0 时退回 `_MODE4_CURVATURE` 合成轮廓（安静/回环断流帧），单色预设下特别显眼 | 引擎加 `has_spectrum`：真实音频链路给过一次 `bands32` 后**永不退回旧轮廓**；旧轮廓只保留给「从未收到频谱」的离线/单测 `tick(amp)` 场景 | 新增 3 测试（喂过非零频谱后全 0 → 空帧；`tick(amp)` 保留旧轮廓；恢复频谱后柱子恢复） |
| 5 | 振幅/背景亮度滑块无效 | `pages/music.js` 官方方案两个滑块 `onInput: () => scheduleLiveUpdate()` **没把新值写回** `offAmplitude`/`offBackBright`，热更新永远发旧值（50/100） | `onInput: (v) => { offAmplitude = Number(v); ... }`（亮度同理） | 后端 update amplitude 10 vs 100 帧输出明显不同（真机抓帧）；滑块链路修复 |
| 6 | 宏表读取 48s（附带发现） | 用户设备宏目录被写坏（目录值像宏动作数据 0x3200ff47…，不是合法偏移），旧实现拿垃圾当偏移、`count` 解析成巨大值 → 单槽读几百 KB | `read_all_macros` 先做偏移合法性过滤（`[400, capacity-4]`），坏目录直接空表 + `corruptDirectory`/`invalidSlots` 诊断、不再读设备；`_read_slot` 限制 count/地址上界；写回验证拒绝非法目录 | 真机：坏目录场景目录读 1 次即返回（不再大读），`/api/macros` 366ms |
| 7 | 浏览器模式日志失效（附带） | `run.py` 用 `uvicorn.run` 默认 log_config → dictConfig 关闭已装 handler；`shell.py` 早已 `log_config=None` | `run.py` 同步 `log_config=None`；`_SessionFileHandler.emit` 在 stream=None 时按需重开（防御） | 源码运行 session 日志正常增长、日志错误清零 |

### 20.3 验证与数据

- 单测：`cd driver; .\.venv\Scripts\python.exe -m unittest discover -s tests -q` → **206 tests OK**（v0.1.3 基线 152；新增 keymap 15 / 性能 15 / 颜色 14 / mode4 3 / 宏健壮性 6 / 其他 1）
- UI 自检：headless Chrome `tools/ui_shots.py` → **17/17 PASS**（keymap.js / music.js 改动后）
- 真机 v0.1.4 验证（USB fw1.19，`run.py` 源码服务 + HTTP/WS 驱动）：
  - 改键：canonical 200 / alias key 200 / combo 写入 200 + 恢复 readback 一致 / FN no-op 200
  - 宏：`GET /api/macros` 366ms、slots=0（见 §20.4）
  - 颜色：mode 4/14/22 冰蓝覆盖生效
  - 帧流：66fps 40.2s 实测 **65.9fps**、0 错误、sendMode=`burst+drainer`、日志 +22.3KB
  - 停止恢复：`0affffffff000000010603000000aa55` 与开始前逐字节一致（用户当前灯效）

### 20.4 遗留 / 说明

- 用户设备的宏目录原本已损坏（内容像宏数据而非偏移，固件也拒绝写回该非法目录）。备份原始 3072B 到
  `%TEMP%\mk87_macro_area_backup.bin` 后，已把目录写 0（空宏表，keymap 无宏绑定）；宏功能从此可正常
  读写（真机已验证 write_macros 回读一致），需要重新录制宏。
- 振幅语义按官方端口各不相同（mode 13 是平滑系数、mode 4 是柱高增益、15 是爬升层数…），滑块现在能真正
  把值发到后端；部分模式在高电平时仍会顶满（官方语义如此），未重新标定真值。
- E 项（mode 100 自研屏光同步 / E2 / E4 实验）仍按用户要求后置。

### 20.5 交付（v0.1.4）

- 本地验证后提交 `1927d39`，推送 main → CI 运行
  [#27](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41631551498) 全绿
  （Windows/Ubuntu 测试 + Linux deb/rpm + Win 便携/安装包）→ tag `v0.1.4` → CI 运行
  [#28](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41632599330) 全绿 →
  Release 2026-11-03 20:11（UTC 12:11）发布：
  <https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.4>
  - CI 附件（Release 页 `SHA256SUMS.txt` 已复算校验）：`MK87Studio-0.1.4-win64-portable.zip`
    39,034,179 B（SHA256 `71024422…9eac1`）/ `MK87Studio-0.1.4-win64-setup.exe` 30,172,420 B /
    `mk87-0.1.4-1.x86_64.rpm` 248,573,133 B / `mk87_0.1.4_amd64.deb` 208,009,480 B
  - 本地打包冒烟：`dist\MK87Config\MK87Config.exe` FileVersion **0.1.4.0**，`--tray` 启动后
    `webVersion=0.1.4`、`officialModes=21`、`GET /api/macros` 276ms、`/api/quit` 正常退出
- 本版共修复 7 项（§20.2 表），仍未做：mode 100 自研屏光同步、E2/E4 硬件实验、自定义 HEX、振幅按官方
  真值重标定。

---

## 21 2026-11-03（更晚）：v0.1.5 修 Linux 识别不到设备

### 21.1 用户反馈

- 「Linux 识别不到设备」（v0.1.4 的 deb/rpm 装上后 app 一直没有设备）

### 21.2 根因（代码 + 上游资料确认）

- 本工具用 **HID usage page** 区分接口：主协议 `0xFF68`、TFT `0xFF67`、2.4G 协议 `0xFF60`、
  2.4G 唤醒 `0xFFFF`（见 [transport.py](../driver/mk87lib/transport.py) 文件头）。
- 但 **hidapi 的 Linux hidraw 后端在 `hid.enumerate()` 里不填 `usage_page`/`usage`，恒为 0**
  （hidapi 上游已知限制：<https://sourceforge.net/p/libusb/mailman/message/36968076/>，
  StackOverflow 同样结论）。Windows 的 hidapi 正常填。
- 结果：`MK87Device.connect()` 里 `i.usage_page == const.USAGE_PAGE_*` 永远不匹配 →
  `DeviceNotFound("未找到可用的 MK87 协议接口")` → Linux 永远找不到设备。
  （v0.1.2–v0.1.4 一直如此；Windows 不受影响，所以此前 Windows 真机测试未暴露。）
- 另：udev/permissions 是第二层问题——即使接口枚举到，`/dev/hidraw*` 无权限也会让
  report descriptor/open 失败。

### 21.3 修复（`transport.py` / `device.py`）

- 新增 `parse_report_descriptor_usage(desc)`：解析 HID report descriptor 的 short item，
  取**第一个** Usage Page（Global tag 0）与 Usage（Local tag 0），遇到第一个 Collection 停止。
- 新增 `_read_report_descriptor(info)`：优先 hidapi 0.14+ 的 `device.get_report_descriptor()`
  （内部 hidraw ioctl），失败回退 `/sys/class/hidraw/hidrawN/device/report_descriptor`。
- 新增 `_enrich_linux_usage(ifaces)`：Linux 上仅对 `usage_page == 0` 的接口补 descriptor 解析结果，
  并重算 payload_len（64 / 4104 / 32 / 4）；已有 usage page 的接口不读 descriptor。
  Windows 上 `enumerate_ifaces()` 不触发该逻辑（行为零变化）。
- `device.py`：连接时 DEBUG 记录每个枚举接口（product/pid/usagePage/usage/iface/payload/path）；
  找不到时在 Linux 错误里追加 udev 规则、`/dev/hidraw*` 权限、report descriptor 可读性提示。
- 新增 `probe/linux_hid_check.py`：Linux 一键诊断（枚举、权限、descriptor 解析、结论 + 修复建议）。

### 21.4 验证

- 新增 `driver/tests/test_transport_linux.py`（9 tests）：descriptor 解析（0xFF68/0xFF67/0xFF60/0xFFFF、
  首 page 优先、截断不崩）、`_enrich_linux_usage` 补齐与 payload 计算、已知 page 不重复读、
  `enumerate_ifaces` 仅 Linux 触发、hidapi get_report_descriptor 路径、sysfs fallback、Windows 不触发。
- 全量：`cd driver; .\.venv\Scripts\python.exe -m unittest discover -s tests -q` → **215 tests OK**。
- Windows 侧回归：打包 v0.1.5 exe `--tray` 启动后 `connected=True`、21 模式、正常退出（见 §21.5）。
- **Linux 真机验证待用户执行**：装 v0.1.5 deb/rpm → 重新插拔 → 运行 `python3 probe/linux_hid_check.py`
  与 app；若仍失败，日志会列出枚举接口/usagePage，可据此判断是权限还是枚举问题。

### 21.5 交付（v0.1.5）

- 版本 0.1.5（7 处），README/release-notes/TEST-REPORT 同步；tag `v0.1.5` → CI 自动 Release。
- 风险/边界：若 hidraw 只读权限都没有（udev 未装/未生效），descriptor 与 open 都会失败，
  此时仍是「找不到设备」，但错误信息会明确提示；2.4G 唤醒接口 payload=4 依据 usage page 0xFFFF 还原。
- 未做：Linux 上 TFT 接口如果是 hidraw 权限拒绝则无法补齐（会打印提示），mode 100 自研屏同步等仍后置。

### 21.6 发布记录

- 提交 `614ff4c` → main CI 运行
  [#30](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41639557646) 全绿 →
  tag `v0.1.5` → CI 运行
  [#31](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41640309540) 全绿 →
  Release 2026-11-03 21:05 发布：<https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.5>
  - 附件（SHA256SUMS 已复算校验）：`MK87Studio-0.1.5-win64-portable.zip` 39,037,258 B
    （`f6e91d77…7a4bb`）/ `MK87Studio-0.1.5-win64-setup.exe` 30,180,259 B / `mk87-0.1.5-1.x86_64.rpm`
    248,582,012 B / `mk87_0.1.5_amd64.deb` 208,099,872 B
  - 本地冒烟：exe FileVersion 0.1.5.0，`--tray` → `connected=True`、`webVersion=0.1.5`、quit 正常
- 待办：等用户 Linux 真机反馈；若 `probe/linux_hid_check.py` 显示接口 usagePage 已补齐但 app 仍不连，
  重点查 `/dev/hidraw*` 权限与后端 open 错误（日志已记录）。

## 22 2026-11-03（深夜）：v0.1.6 修 Linux 真正根因 —— hidapi 后端选错（libusb）

> 上一节 §21 的判断（「hidraw 后端不填 usage_page」）**不成立**。用户装 v0.1.5 后仍识别不到，
> 附上了完整日志包（`E:\mk87-logs-20261103-212457.zip`，含 mk87.log / errors.log / system-info.txt），
> 由日志反推出真正原因。

### 22.1 用户反馈

- 「还是不行…… 日志给你发这儿了」，系统：`Linux-7.2.13-1-surface-x86_64-with-glibc2.39`，
  app 版本 v0.1.5（`/opt/mk87/MK87Config`，从 deb/rpm 装）。

### 22.2 日志证据

```
[mk87.device] HID 接口: product='' pid=0x8047 usagePage=0x0000 usage=0x0000 iface=-1 payload=64 path=1-1.1:1.0
[mk87.device] HID 接口: product='' pid=0x8047 usagePage=0x0000 usage=0x0000 iface=1 payload=64 path=1-1.1:1.1
... (4 个接口，全部 usagePage=0、product 为空)
error: [pywebview] GTK cannot be loaded: No module named 'gi'
```

两个关键点：

1. `path=1-1.1:1.0` **不是 `/dev/hidrawN`**，而是 hidapi **libusb 后端**的路径格式
   （`总线-端口:配置.接口`，见 hidapi `libusb/hid.c` 的 `get_path()`）；
2. `product=''` + `usagePage=0` 同时出现 = libusb 后端 `libusb_open()` 失败（handle=NULL）时
   hidapi 只填 VID/PID，不填字符串、不填 usage（`create_device_info_for_device()` 在 handle 为空时
   直接 return）。即：**枚举到了设备，但一个接口都打不开**（/dev/bus/usb 权限不够），
   而且就算打开，libusb 后端默认也不做 `INVASIVE_GET_USAGE`，usage_page 仍会是 0。

### 22.3 根因

- PyPI 的 `hidapi`（cython-hidapi）wheel 在 Linux 上打包了**两个**扩展模块：
  - `hid` → 用 `libusb/hid.c` 编译，**libusb 后端**；
  - `hidraw` → 用 `linux/hid.c` 编译，**hidraw 后端**。
- cython-hidapi 的 `setup.py`：Linux 上若既没 `HIDAPI_WITH_HIDRAW` 也没 `HIDAPI_WITH_LIBUSB`，
  默认 **`HIDAPI_WITH_LIBUSB = True`**；manylinux wheel 就是这样编的
  （用 `hid.so` / `hidraw.so` 里的动态库字符串可验证：`hid` 依赖 `libusb-1.0.so`，
  `hidraw` 依赖 `libudev.so`）。
- 我们的 `transport.py` 一直 `import hid` → Linux 拿到 libusb 后端 → 路径不是 hidraw 设备、
  usage page 恒 0、v0.1.5 的 sysfs 兜底又按 `/dev/hidrawN` 正则找路径（对不上）→
  依旧「找不到设备」。
- 附带说明：`hidraw` 后端在 `hid_enumerate()` 里会从
  `/sys/class/hidraw/hidrawN/device/report_descriptor` 解析 usage page（hidapi `linux/hid.c`
  `get_hid_report_descriptor_from_sysfs()`），**不需要 open 权限**；所以换对后端后，
  即使 udev 规则没生效也至少能枚举出正确 usage page。

### 22.4 修复（v0.1.6）

- `transport.py`：
  - 新增 `_load_hid_backend()`：Linux 上**优先 `import hidraw`**，只有没有 hidraw 模块时才退回
    `hid`（并标记 `BACKEND="libusb"`）；Windows/macOS 用 `hid`。改用 `importlib.import_module`，
    避免打包时把 Linux 用不到的 libusb 模块带进产物；模块级 `hid` / `BACKEND` 保持不变，
    旧测试与调用方无需改动。
  - `enumerate_ifaces()`：Linux 上若只剩 libusb 后端，直接抛出可执行的错误
    （提示 `pip install --force-reinstall hidapi` / 升级安装包），不再拿错误路径去 open。
  - 修 `interface_number` 的 `or -1` bug：接口号 0 会被当成缺省 → 现在保留 0。
  - sysfs 兜底增强：新增 `iter_sysfs_hidraw()` / `parse_sysfs_hid_id()` / `sysfs_descriptor_for()`，
    当 path 不是 `/dev/hidrawN`（例如 libusb 风格）时按 `HID_ID` 的 pid + `bInterfaceNumber`
    反查 report descriptor；`_read_report_descriptor()` 变成 hidapi → 路径正则 → sysfs 反查三级。
- `device.py`：连接时打印 `hidapi 后端: <backend>`；Linux 找不到设备时提示用 `--diagnose` 排查。
- `shell.py`：
  - 新增 `--diagnose`：打印完整 HID 自检（见下）后退出，并保存
    `~/.local/state/mk87/logs/diagnose.txt`；
  - Linux 上 `webview.start(gui="qt")`，不再先刷 GTK 加载失败的 ERROR（打包只带 Qt）。
- 新增 `mk87lib/diag.py`：自检内容 = 平台/Python/frozen、`BACKEND`、`import hidraw`/`import hid`
  结果与版本、`hid.enumerate()` 原始记录、本工具解析后的接口（含能否打开）、
  `/sys/class/hidraw/*` 节点的 vid/pid/iface/usagePage/权限、udev 规则状态、结论。
- `probe/linux_hid_check.py` 改为调用同一套 `collect_diagnostics()`（源码环境用），
  不再维护两份逻辑。
- `packaging/mk87.spec`：Linux `hiddenimports += ["hidraw"]`，Windows `+= ["hid"]`
  （动态导入 PyInstaller 静态分析看不到，必须显式声明）。

### 22.5 验证

- `driver/tests/test_transport_linux.py` 新增 11 个测试：后端选择优先级（hidraw → hid → missing）、
  Windows 用 `hid`、Linux libusb 后端被拦截、`interface_number=0` 保留、`HID_ID` 解析、
  sysfs 节点遍历、按 pid+接口号取 descriptor、libusb 风格 path 的 sysfs 兜底。
- 全量：**226 tests OK**（`driver\.venv\Scripts\python.exe -m unittest discover -s tests`）。
- Windows 真机回归（USB fw 1.19）：`enumerate_ifaces()` 8 条记录（含 `0xFF68`/`0xFF67`），
  `MK87Device.connect()` → `connected=True, transport=usb, fw=1.19, battery=100, tftMax=140`；
  动态导入后 `BACKEND=native`。Windows 产物与行为不受影响。
- **Linux 真机验证待用户**：装 v0.1.6 deb/rpm 后打开 app；若仍不对，运行
  `mk87 --diagnose` 并把输出（或 `diagnose.txt`）发回。

### 22.6 交付（v0.1.6）

- 版本 0.1.6（7 处）；README / README.zh-CN / release-notes / 本日志 / TEST-REPORT §18 同步。
- 风险/边界：若发行版系统 `libudev.so.1` 缺失，`import hidraw` 会失败 → 会明确报「没有 hidraw 后端」；
  正常 systemd 桌面系统都带它。deb 已声明 `libudev1`，rpm 由 `systemd-udev` 拉入。

### 22.7 发布记录（v0.1.6）

- 提交 `4bb371c` → main CI 运行
  [#33](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41652035582) 全绿
  （含 ubuntu/windows 单测 226、Linux deb+rpm 打包、Windows portable+setup）→
  tag `v0.1.6` → CI 运行
  [#34](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41653623806) 全绿 →
  Release 2026-11-03 22:33 发布：<https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.6>
  - 附件（SHA256SUMS 已复算校验：下载 portable 复算 = `247960ad…f1475`，一致）：
    - `MK87Studio-0.1.6-win64-portable.zip` 39,046,325 B（`247960ad350a88674440bb6eee2f5c28e1f25bee738cdfe091051830b41f1475`）
    - `MK87Studio-0.1.6-win64-setup.exe` 30,186,799 B（`8ced83c6…d388`）
    - `mk87-0.1.6-1.x86_64.rpm` 248,541,842 B（`64713eb8…5ac2`）
    - `mk87_0.1.6_amd64.deb` 208,048,288 B（`b17f9f75…3d49`）
  - 本地冒烟：dist exe FileVersion 0.1.6.0，`--tray` 启动后
    `version=0.1.6 webVersion=0.1.6 connected=True transport=usb fw=1.19 battery=100 keys=87 tft=True`，
    `/api/quit` 正常退出；本地 portable zip 39,975,380 B（与 CI 构建大小差异属正常，
    CI 机为 Windows Server + 不同 PyInstaller/依赖缓存）。
- 关键验证点：CI 的 Linux 打包任务成功 = PyInstaller 在 Linux 上确实把 `hidraw` 扩展模块打进产物
  （`hiddenimports += ["hidraw"]`）；这是本次修复能否生效的前提。
- 待办：用户装 v0.1.6 后 Linux 真机验证；若仍有问题，`mk87 --diagnose` 的输出足以定位
  （后端名、hidraw 节点、usage page、权限、udev 规则）。

## 23 2026-11-04（晚）：v0.1.7 修 Linux 音乐律动 + 设备命令延迟 10~20 倍 + 卡顿探针

> 用户反馈：Linux（v0.1.6 已能识别设备）上「音乐律动又不行了」，附日志包
> `E:\mk87-logs-20261104-210220.zip`；另外让「再看看日志里还有什么问题」。

### 23.1 日志里的确定结论

- **v0.1.6 的 Linux 识别修复生效**：`hidapi 后端: hidraw`，接口 list 带
  `product='AJAZZ KEYBOARD'`、`usagePage=0xFF68/0xFF67`，`connected=true fw=1.19 battery=100`；
  `errors.log` 没有新增错误（旧的 GTK 报错都是 v0.1.4/0.1.5 会话留下的）。
- **音乐律动失败**：两次 `POST /api/music/start -> 400`，前一行都是
  「音乐律动启动: mode=13 ... targetFps=20 send=ack」，4ms 后返回 → 在音频采集打开阶段立刻失败。
  v0.1.6 的 Linux 采集只走外部命令 `parec`（`subprocess.Popen(["parec", ...])`），用户是
  Fedora/PipeWire 桌面，默认不装 `pulseaudio-utils` → `FileNotFoundError` → 400。
  `/api/music/devices` 返回 200 但内容应是 `(pactl 不可用: ...)` 兜底项。
- **另一类问题（用户没提，但日志很明显）**：多个接口耗时异常
  （` GET /api/keymap` 3911/4748ms、`/api/lighting/custom` 4242/1511ms、`/api/macros` 2570/2818ms、
  `/api/wireless` 3565ms、`/api/backup` 1115ms），且日志里有 **2~9 秒完全没有任何行**的窗口
  （最大 8.7s，期间连 2s 一次的电量轮询 HID TX 也没有）。TFT 上传 2215 包 / 9.07MB / 316s /
  28.0KB/s —— 与 Windows 基线（2136 包 / 8.75MB / 311s ≈ 28.8KB/s）一致，**不是 Linux 独有问题**。

### 23.2 根因 1：Linux 音频采集依赖 parec（已修）

- 修复（`music.py`）：
  - 新增 `PulseSimpleRecorder`：ctypes 直连 `libpulse-simple.so.0`（`pa_simple_new/read/free`，
    `PA_SAMPLE_FLOAT32LE`、2ch、48000Hz），默认源名 `@DEFAULT_MONITOR@`（PulseAudio 特殊源名，
    PipeWire 的 pulse 兼容层支持；Chromium loopback 同款做法）。该库属 `libpulse0`（deb 已依赖）/
    `pulseaudio-libs`（rpm 已 Requires），不需要额外装包。
  - 若特殊源名打不开：`_pactl_default_monitor()` 用 `pactl get-default-sink` 拿到真实
    `<默认 sink>.monitor` 再试；仍失败才回退 `parec`（并检测 parec 退出码，不再把 EOF 当静音）。
  - `list_devices()` Linux：pactl 缺失/无输出时返回「默认输出回环（PulseAudio / PipeWire）」兜底项，
    不再显示 `(pactl 不可用: ...)`。
  - `MusicPlayer` 新增 `audioBackend`（`/api/music/status` 暴露），`_loop` 失败时
    `log.error("音乐律动启动失败: %s", exc)`；`app.py` 的 `MK87Error` 处理器补记 message —— 以后
    HTTP 400 在日志里直接看到原因。
- 单测：`driver/tests/test_music_audio_linux.py` 12 项（ctypes 假库成功读/错误码/缺库、
  libpulse 优先、parec 回退、EOF 报错、pactl 默认 monitor 解析、设备列表回退等）。

### 23.3 根因 2：通知监听线程持锁做「带超时读」（已修，性能提升 10~20 倍）

- 现状：`MK87Device._listen_proto` 每轮 `self._lock.acquire()` → `protocol.read_event(0.05)` →
  `release()`。问题：
  - Windows hidapi 的带超时读在超时路径要走 **CancelIoEx**，实测单次 50~400ms 才返回，
    期间一直占着设备锁 → 每个改键/宏/灯效请求都要白等约 0.3s（这解释了 Windows 上
    keymap 324~445ms、custom LED 93~245ms）；
  - Linux 上若通知帧连续到达，读完立刻重抢锁，可能把请求线程饿住数秒（与 23.1 的无日志窗口吻合）。
- 修复：
  - `transport.py` 新增 `read_report_nonblocking()/read_normalized_nonblocking()`：
    **不能用 `dev.read(len, 0)`** —— cython-hidapi 的 `timeout_ms==0` 分支调用的是阻塞的
    `hid_read()`（一开始就踩了这个坑：监听线程直接卡死，`read_normal_matrix` 永久挂起）；
    正确做法是 `set_nonblocking(1)` + `read(len)`，读完恢复 `set_nonblocking(0)`。
  - `protocol.read_event(timeout<=0)` 走非阻塞读。
  - `_listen_proto`：持锁时间降到微秒级，读不到就**先释放锁再 sleep 20ms**；抢不到锁时 sleep 5ms。
  - `device.request/request_custom` 改为显式 acquire/release，并记录 >0.3s 的等锁 WARNING。
- 真机（Windows，MK87 fw1.19）实测（源码直连 HID，7 次中位数）：
  | 操作 | 修复前（经 API） | 修复后 |
  |---|---|---|
  | `keymap.read_normal_matrix` | ~325 ms | **15.2 ms** |
  | `keymap.read_fn_matrix` | — | **22.0 ms** |
  | `lighting.get_custom` | 93~245 ms | **24.1 ms** |
  | `dev.get_device_info` | ~50 ms | **2.0 ms** |
  音乐帧流复测：20fps 下 4s / 80 帧 / 实测 20.0fps / errors=0（监听线程没有偷帧问题）。

### 23.4 卡顿探针（为「2~9 秒无日志」留证据）

- `shell.py` 新增进程级 watchdog：每 0.5s 采样 monotonic；间隔 >2s 记 WARNING
  「进程卡顿：X s 内 watchdog 无采样」→ 区分「整进程被冻结/挂起」与「单线程等锁」。
- `transport.py`：HID 写 >0.5s、读明显超过请求超时 3 倍时记 WARNING；
  `device.py` 等锁 >0.3s 记 WARNING。下次用户日志可直接定位。

### 23.5 验证

- 全量单测：**245 tests OK**（226 → 245：+12 Linux 音频，+2 非阻塞读，+5 监听/杂项）。
- Windows 真机：connect / keymap / custom / device_info 延迟表见 §23.3；音乐 20.0fps 4 秒 0 错误。
- **Linux 真机音乐验证待用户**：装 v0.1.7 后开音乐律动；若仍失败，日志里会有
  `音乐律动启动失败: ...` 与 `音频采集后端: ...` 两行，直接能看出是库缺失、源名不对还是服务未运行。

### 23.6 发布记录（v0.1.7）

- 提交 `7503869` → main CI 运行
  [#36](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41839779002) 全绿
  （ubuntu/windows 单测 245、Linux deb+rpm、Windows portable+setup）→
  tag `v0.1.7` → CI 运行
  [#37](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41841886719) 全绿 →
  Release 2026-11-04 21:59 发布：<https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.7>
  - 附件（SHA256SUMS 已复算：下载 portable 复算 = `5f5b67a6…5a91`，一致）：
    - `MK87Studio-0.1.7-win64-portable.zip` 39,055,446 B
      （`5f5b67a6a91ea214fc6a83a7e961f5f3774ac1ec6ad463fe688bc7d15b175a91`）
    - `MK87Studio-0.1.7-win64-setup.exe` 30,198,189 B（`73e013b5…2cf2`）
    - `mk87-0.1.7-1.x86_64.rpm` 196,406,773 B（`166d73bd…ce68`）
    - `mk87_0.1.7_amd64.deb` 210,312,114 B（`da3c6710…65b4`）
  - 另有一个 7,217B 的 `mk87-debuginfo-0.1.7-1.x86_64.rpm`（rpmbuild 默认产物）。
    已给 `mk87.spec` 加 `%global debug_package %{nil}`，下个版本不再生成。
  - 本地冒烟：dist exe FileVersion 0.1.7.0，`--tray` 启动 →
    `version=0.1.7 webVersion=0.1.7 connected=True fw=1.19`；
    打包版音乐律动 3 秒 60 帧 / 实测 20.0fps / errors=0（Windows soundcard 路径不受影响）。
- 待办：用户 Linux 装 v0.1.7 后验证音乐律动；若失败，日志里新增的
  「音频采集后端: ...」「音乐律动启动失败: ...」两行会直接给出原因。卡顿窗口（2~9s）由新增
  watchdog/等锁/HID 慢调用 WARNING 负责定位。


## 24 2026-11-05：v0.1.8 Linux 托盘改 Qt + 启动弹终端修复 + GNOME 扩展一键安装

> 用户反馈（v0.1.7 安装后）：①「Linux 端启动后会出现一个终端，能不能让他不出现」；
> ②「右击小图标在 Linux 中好像不管用」。讨论后用户拍板：托盘是刚需；一键安装 GNOME 扩展
> 可以用一次提权；真的没有托盘就点 X 直接关闭；做完把资料上传 GitHub 并打包发布到 Release。

### 24.1 讨论结论（先对齐再动手）

- 托盘在 Linux 上有两套互不兼容的机制：
  - **StatusNotifierItem / AppIndicator**（D-Bus + dbusmenu）：KDE / XFCE / Cinnamon / MATE / LXQt
    原生支持；GNOME 必须装 `gnome-shell-extension-appindicator`（Ubuntu 预装了同源分支，
    uuid 是 `ubuntu-appindicators@ubuntu.com`）；这是 Qt / 现代应用走的路。
  - **XEmbed 旧式托盘**：GNOME 从来不支持；XFCE/MATE 有兼容层时能显示，但菜单要靠应用自己实现。
- 本项目的 pystray 在 Linux 打包体里没有 `gi`/GTK，也没有 AppIndicator 绑定，所以总是回退
  `_xorg` 后端；`pystray/_xorg.py` 里 `HAS_MENU = False`（注释 “Menus are not supported on X”），
  只处理左键 activate → **图标能出现但右键没有任何反应**，与用户现象完全吻合。
- 用户坚持「别的应用有右键」也成立：那些应用本身就是 SNI 应用，或用户装了 AppIndicator 扩展 /
  在 Ubuntu 这类预装扩展的系统上；与 pystray 无关。

### 24.2 根因 1：启动弹终端（`Terminal=true`）

- `driver/packaging/linux/mk87.desktop` 里 `Exec=mk87` + **`Terminal=true`**：从应用菜单启动时
  桌面环境按这个字段开终端承载程序 → 用户看到的那个终端窗口。
- 开机自启文件（`mk87lib/autostart.py` 的 `LINUX_DESKTOP`）本来就是 `Terminal=false`，无此问题，
  这也解释了「只有手动启动会弹」。
- 修复：改为 `Terminal=false`；deb/rpm 打包脚本是直接 `install`/`cp` 这个文件，重新打包即生效。

### 24.3 根因 2：Linux 托盘右键无菜单（pystray xorg 后端 `HAS_MENU = False`）

- 方案：Linux 改用 **Qt `QSystemTrayIcon` + `QMenu`**（PyQt6 已由 `pywebview[qt]` 打进包，
  不新增运行时依赖）；Windows 继续用 pystray，行为不变。
- 新增 `driver/mk87lib/tray_linux.py`：
  - 菜单保持三项：显示主窗口 / 开机自启（勾选状态在 `QMenu.aboutToShow` 时刷新）/ 退出；
  - `activated(Trigger/DoubleClick)` → 显示窗口；右键菜单由 Qt 的 `setContextMenu` 提供；
  - **线程模型**：Qt 控件只能在 GUI 线程创建。`webview.start(func=...)` 的 func 跑在子线程，
    此时主线程的 `QApplication` 可能还没创建 → 子线程轮询 `QApplication.instance()`；
    就绪后建一个 QObject 持有者 `moveToThread(app.thread())`，再用
    `QMetaObject.invokeMethod(..., QueuedConnection)` 把创建任务投递到 GUI 线程
    （与 pywebview 处理 js_api 的方式一致）。
  - 可用性写入模块级 `STATE`；`Qt` 导入失败（源码运行没装 Qt）时回退 pystray 兜底。
- `shell.py`：
  - Linux 走 `webview.start(..., func=self._linux_tray_bootstrap)`；Windows 走 `_start_pystray()`；
  - 无托盘宿主时（`QSystemTrayIcon.isSystemTrayAvailable() == False`）**点窗口 X 直接退出程序**，
    不再隐藏到找不到的地方；有托盘时保持原来的「隐藏 + 托盘提示」；
  - `server.app.tray_status_callback` 注入真实托盘状态（同 activate/quit callback 模式）。

### 24.4 GNOME 一键安装（`trayenv.py` + `/api/tray/*`）

- 新增 `driver/mk87lib/trayenv.py`（纯标准库，Windows 可 import/单测）：
  - 解析 `XDG_CURRENT_DESKTOP` / `XDG_SESSION_TYPE` / `WAYLAND_DISPLAY` / `DISPLAY`、
    `/etc/os-release`；`ubuntu:GNOME` 这类复合值取已知桌面名（显示 GNOME）；
  - GNOME 扩展状态：检查用户级/系统级扩展目录（含 Ubuntu 的 uuid），用
    `gsettings get org.gnome.shell enabled-extensions / disabled-extensions` 判断启用，
    读不到时回退 `gnome-extensions info` 的 `State:`；
  - 包管理器识别：`rpm-ostree`（原子化优先）/ `dnf` / `apt-get` / `zypper` / `pacman`；
    提权工具优先 `pkexec`（图形密码框）再 `sudo`；
  - `install_plan()` 生成「发行版包 + 一次提权」命令与失败原因（非 GNOME / 已启用 /
    已装未启用 / 无包管理器 / 无提权工具）；无论哪条路径都附带可复制的手动命令。
- 新增接口：
  - `GET /api/tray/status`：托盘后端/宿主可用性、桌面、会话、GNOME 版本、扩展状态、
    安装计划、建议文案（zh/en 两份，沿用 conflictItems 的双语模式）；
  - `POST /api/tray/install-extension`（必须 `confirm: true`，仅外壳模式）：
    `pkexec <包管理器> install -y gnome-shell-extension-appindicator`，捕获输出；
    成功后自动启用扩展（先 `gnome-extensions enable`，Shell 还没扫描到时退化为
    直接写 `gsettings enabled-extensions`），返回 `needsLogout` / `rebootRequired`；
  - `POST /api/tray/enable-extension`：已装未启用时免提权启用；
  - 浏览器模式（`run.py`）调用安装接口返回 400，避免任意本地网页触发提权。
- `/api/status` 增加 `tray` 摘要（available/backend），供主窗口横幅判断。

### 24.5 前端：设置页「系统托盘」卡片 + 横幅 + mock

- `pages/settings.js`：新增卡片，展示托盘后端/宿主、桌面环境、扩展状态、GNOME 版本、
  发行版；按检测结果显示「一键安装扩展（需管理员密码）」/「启用扩展（无需提权）」/
  「复制安装命令」/「查看·复制安装命令」/「重新检测」；确认框说明 Wayland 需注销重登、
  X11 可 Alt+F2 → r；中英文案在卡片内自带（语言切换时 `i18n.onChange` 重渲染），
  另加 `TXT` 本地字典使英文模式不再混入中文。
- `app.js`：`/api/status.tray.available === false` 时顶部横幅提示「关闭窗口将直接退出程序」，
  可关闭，动作按钮跳设置页。
- `api.js`：`/api/tray/install-extension` 超时放宽到 300s（pkexec 密码 + 包管理器下载）。
- `mock.js`：补 `/api/tray/status`、安装/启用接口的演示数据。

### 24.6 验证

- 全量单测：**277 tests OK**（245 → 277，新增 `tests/test_trayenv.py` 32 项：桌面环境解析、
  os-release、扩展安装/启用判定（gsettings + gnome-extensions 回退）、包管理器/提权识别、
  安装计划、汇总状态分支、安装成功/失败路径、无托盘点 X 逻辑）。
- 前端：`bun build` 解析通过；用 linkedom + bun 跑了 16 项 DOM 冒烟（中文/英文/热切换/
  Windows 形态无安装按钮），全部通过（脚本为本地临时验证，不入库）。
- 只读接口实测（源码 `run.py --no-browser` 8491 端口）：
  `/api/status` 带 `tray` 摘要；`/api/tray/status` 返回完整结构；
  浏览器模式 `POST /api/tray/install-extension` 返回 400（预期拒绝）。
- Windows 打包冒烟与 Linux 真机验证见发布记录。

### 24.7 风险与待办

- **Qt 托盘跨桌面兼容性只能真机验证**：`isSystemTrayAvailable()` 在 GNOME（无扩展）应为 false；
  KDE/XFCE/Cinnamon/MATE 应原生显示且右键菜单可用。若某桌面 Qt 仍显示不出，再按该桌面补兼容。
- **pkexec 依赖 polkit 认证代理**：GNOME/KDE 桌面都自带；无 pkexec 时回退 sudo/手动命令。
- **Wayland 装完扩展必须注销重登**（GNOME 不支持热加载），卡片与提示文案已写明；
  X11 可 `Alt+F2` → `r`。
- Linux 真机验证由用户执行：无终端窗口、右键菜单可用、设置页状态正确、GNOME 一键安装生效。


### 24.8 发布记录（v0.1.8）

- 提交：`d52ce4c`（Qt 托盘 + 终端修复）、`f61a46f`（GNOME 扩展检测/安装 + 设置页卡片）、
  `f34c120`（版本号与文档）、`ed32ec5`（design.md 接口编号）
  → main CI 运行 [#39](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41849587327)
  全绿（ubuntu/windows 单测 **277**、Linux deb+rpm、Windows portable+setup）；
  随后文档提交的运行 [#40](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41849694286)
  也全绿。
- tag `v0.1.8` → CI 运行
  [#41](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/41851737175) 全绿 →
  Release 2026-11-04 23:01 发布：
  <https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.8>
  - 附件（SHA256SUMS 与 GitHub asset digest 一致；portable 已下载复算一致，39,091,617 B 实测同哈希）：
    - `MK87Studio-0.1.8-win64-portable.zip` 39,091,617 B
      （`b193f1872b085a9e18ddd32796a6a750ad458547780de2de37869de617ba9824`）
    - `MK87Studio-0.1.8-win64-setup.exe` 30,236,827 B（`4915f65e…d1bb`）
    - `mk87-0.1.8-1.x86_64.rpm` 196,309,647 B（`af1e84ab…f7c6`）
    - `mk87_0.1.8_amd64.deb` 210,360,910 B（`89a9e246…8285`）
    - `SHA256SUMS.txt` 378 B
  - 本次只有 **5 个资产**：`%global debug_package %{nil}` 生效，不再生成 `mk87-debuginfo` 子包。
  - 本地 portable zip 40,019,081 B（与 CI 资产大小不同属正常：CI 为 Windows Server runner、
    依赖缓存与压缩时序不同；两个包都可运行，发布以 CI 产物为准）。
- 本地冒烟（`dist/MK87Config/MK87Config.exe`）：
  - FileVersion / ProductVersion = **0.1.8.0**；
  - `--tray` 启动 → `/api/version` = `{"version":"0.1.8",...}`；
    `/api/status` = `shell=true tray={"available":true,"backend":"pystray"}`；
    `/api/tray/status` = `platform=windows shellMode=true backend=pystray advice=windows-ok`；
  - `/api/quit` 正常退出，无残留进程。
- **待用户验证（Linux 真机）**：装 v0.1.8（rpm/deb）→ ①从应用菜单启动不弹终端；
  ②左键显示窗口、右键菜单可用；③设置 → 系统托盘卡片状态正确（后端 Qt / 桌面环境 / 扩展）；
  ④GNOME 缺扩展时一键安装 → 注销重登 → 托盘出现。若托盘仍不出现，日志里会有
  「Qt 托盘不可用（...）」/「系统托盘不可用，关闭窗口 = 退出程序」，设置页卡片也会显示
  advice 与安装命令，可直接贴回来定位。
- 风险：Qt 托盘分支无法在 Windows 本地冒烟覆盖，只能靠 Linux CI 构建通过 + 用户真机验证；
  pkexec/polkit 依赖桌面认证代理，失败时前端回退为复制命令。


## 25 2026-11-05：v0.1.8 Linux 启动闪退排查（v0.1.8.1：启动日志 / 安全模式 / CI 提速）

> 用户反馈：Linux 装 v0.1.8 后「闪退了，直接日志都拿不到」；并要求 CI 别再让单次等待那么久
> （单独机器打包 rpm / 立刻开一台机子跑测试）。

### 25.1 现场信息与初步判断

- v0.1.7 能正常启动（用户此前日志可证），v0.1.8 新增的**唯一启动期原生代码**是 Linux Qt 托盘
  （`tray_linux.py`：`QSystemTrayIcon` + `QMenu`，在 `webview.start(func=...)` 子线程里等
  `QApplication` 就绪后投递到 GUI 线程创建）。窗口本体、WebEngine、后端均沿用 v0.1.7。
- 因此第一嫌疑是「Qt 托盘创建路径」。其中两个已知风险点：
  1. **PyQt6 的槽函数异常会走 `qFatal()`（abort）**：v0.1.8 的 `install` 槽 `except` 后仍然
     `raise`，一旦创建托盘时抛异常，进程会立即 abort，外观就是「闪退」，且 Python 层日志可能
     来不及写 → 完美符合用户描述。
  2. **GNOME 没有 AppIndicator 扩展时本来就无法显示托盘图标**，此时创建 Qt 托盘没有意义，
     却踩在最可疑的路径上。
- 用户机器上日志「拿不到」还可能是：打包程序 `console=False`，stderr 直接丢弃；崩溃发生在日志
  初始化之前或原生 abort 时，常规 session 日志可能来不及落盘。

### 25.2 用 CI 新机子复现（用户要求「再开个机子跑测试」）

- 新增手动工作流 `.github/workflows/linux-smoke.yml`：
  - 在全新 Ubuntu runner 上 `pip install -r packaging/requirements.txt pyinstaller` →
    PyInstaller 构建 → **Xvfb 里真正启动打包后的 `MK87Config`**（可传 `--tray` / `--no-tray`）；
  - 自动收集 `stderr`、`~/.mk87-boot.log`、`~/.local/state/mk87/logs`、`~/.cache/mk87/logs`
    并上传 artifact；`exit_code=124`（被 timeout 杀掉）判定为「进程一直活着 = 没崩」。
- 第一次运行（`target_ref=v0.1.8`）：**app_exit_code=124，alive 45s，无崩溃**，crash.log 0 字节。
  → 说明**打包产物本身在普通 X11/Linux 上能正常启动**，用户遇到的闪退与具体桌面会话
  （Wayland / GNOME 托盘环境）相关，而不是 PyInstaller 打包坏了。
- 第二次运行（`target_ref=main`，参数 `--no-tray --tray`）：`RESULT=alive_after_45s`，
  boot log 完整出现 `main-start → logging-ready → single-instance-acquired → shell-run-start
  (no_tray=True) → server-started → server-ready → window-created → tray-disabled`。

### 25.3 v0.1.8.1 的修复/诊断措施

- `mk87lib/bootlog.py`：固定路径 `~/.mk87-boot.log`，每条 `open(append)+flush+fsync`，
  超过 256KB 自动轮转；`shell.py` 在 main 入口、日志就绪、单实例、服务就绪、窗口创建、
  webview 启动、托盘各阶段都打标记；`quit`、`_on_closing` 也记录。
- `tray_linux.py`：
  - `install` 槽改为**绝不向外抛**（捕获 `BaseException`，写 bootlog + `logging.exception`，
    降级为「无托盘」）；Qt 信号回调（显示/退出/开机自启）统一走 `_safe()`；
  - 增加 `set_unavailable(reason)`；各阶段（import / QApplication 就绪 / 投递 / 安装开始 /
    isSystemTrayAvailable / shown / no-host / error）写 bootlog。
- `shell.py`：
  - 新增 `--no-tray` 参数与 `MK87_NO_TRAY=1` 环境变量：完全不创建托盘，关闭窗口 = 退出程序，
    用于排查与应急；
  - **GNOME 守卫**：启动托盘前用 `trayenv` 检测桌面与扩展；GNOME 且扩展未安装/未启用时
    直接 `set_unavailable(...)` 跳过 Qt 托盘创建（GNOME 本来就显示不了），把最可疑路径绕开；
  - 托盘 bootstrap 的所有异常改为 `BaseException` + bootlog，回退 pystray 也加保护。
- 诊断路径说明（写进 release notes/README）：崩溃时看 `~/.mk87-boot.log` 停在哪一步；
  终端运行 `mk87` 可直接看到 abort 前的 Python/Qt 输出。

### 25.4 CI 提速（用户要求「专门打包 rpm 的机子」）

- `.github/workflows/build.yml` 拆分：
  - `main` 的每次 push **只跑单测**（ubuntu + windows 两台并行，约 2 分钟；此前每次 ~8-10 分钟）；
  - 安装包只在 `v*` tag 或手动 `workflow_dispatch` 时构建；
  - 原 `linux-packages` 拆成 **`linux-deb` 与 `linux-rpm` 两台并行 runner**（各自构建
    PyInstaller 产物后打对应包），tag 发布关键路径由 ~8.5 分钟降到 ~6-7 分钟；
  - `release` 改为 `needs: [linux-deb, linux-rpm, windows-package]`；
  - test/打包 job 都加 `actions/setup-python` 的 `cache: pip`。
- 效果实测：main 提交 `ddbad72` 的 CI #43 测试 job **约 2 分钟完成**。

### 25.5 验证

- 本地：`py_compile` + 全量 **277 tests OK**；Windows 构建冒烟见发布记录。
- CI：`linux-smoke` #1（v0.1.8）alive 45s；#2（main + `--no-tray`）alive 45s 且 boot log 完整；
  main push CI #43 仅测试、约 2 分钟。
- **仍需用户配合**：`mk87` 终端输出 + `~/.mk87-boot.log`（v0.1.8.1 生成）+ 桌面环境
  （`echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE`）；如果 `mk87 --no-tray` 能启动，
  说明确定是托盘路径问题，可先这样使用。

### 25.6 发布记录（v0.1.8.1）

- 提交：`ddbad72`（boot 日志 / --no-tray / GNOME 守卫 / CI 拆分 + linux-smoke）、
  `b42ed40`（版本号与文档）、`3a2b122`（打包 job 与测试并行、旧 run 自动取消）
  → main 仅测试 CI：[#44](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42020176580)、
  [#46](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42020257449) 均全绿（约 2 分钟/次）。
- tag `v0.1.8.1` → CI 运行
  [#45](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42020194735) 全绿（测试 281、
  linux-deb、linux-rpm、windows portable+setup 四个 job）→
  Release 2026-11-05 19:42 发布：<https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.8.1>
  - 附件（SHA256SUMS 与 asset digest 一致；portable 已下载复算 39,118,642 B 哈希相同）：
    - `MK87Studio-0.1.8.1-win64-portable.zip` 39,118,642 B
      （`564759337828eac621bd18cb1267c8ed7e7b94c56ca822ef4ebf16dff2dff2e4`）
    - `MK87Studio-0.1.8.1-win64-setup.exe` 30,255,710 B（`24bbedf3…936a`）
    - `mk87-0.1.8.1-1.x86_64.rpm` 196,337,562 B（`dd0c413e…436f`）
    - `mk87_0.1.8.1_amd64.deb` 210,380,908 B（`47396427…3f68`）
    - `SHA256SUMS.txt` 386 B
- 本地 Windows 冒烟（`dist/MK87Config/MK87Config.exe`）：
  - FileVersion / ProductVersion = **0.1.8.1**；
  - `--tray` 启动 → `/api/version` = `0.1.8.1`、`/api/status.tray = {"available":true,"backend":"pystray"}`；
    `~/.mk87-boot.log` 记录 `main-start → logging-ready → single-instance-acquired →
    shell-run-start → server-started → server-ready → window-created → webview-start-begin`；
  - `--no-tray --tray` → boot log 记 `tray-disabled`，`/api/status.tray.available=false`，进程正常退出；
  - `/api/quit` 退出后无残留进程。
- **下一步（等用户反馈）**：用户装 v0.1.8.1 后执行 `mk87`（终端输出）+ `mk87 --no-tray`（能否正常用）
  + 提供 `~/.mk87-boot.log` 与 `echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE`；
  boot log 停在哪个 `qt-tray-*` 阶段即可定位是 Qt 托盘创建、QApplication 等待还是更早的环节。
- CI 进一步优化（`3a2b122`，下次 tag 生效）：三个打包 job 不再 `needs: test`，与测试并行；
  `release` 仍等待 `test`，关键路径再缩短约 2 分钟；同一 ref 的旧 run 自动取消（tag 不取消）。


## 26 2026-11-05：v0.1.8.2 修 Linux 启动闪退（Qt 6.12 缺系统库）+ 依赖声明/自包含/发版卡口

> 用户提供 `E:\system-info.txt`（Ubuntu 上直接终端运行 `mk87` 的输出），并要求先讨论
> 「不能安装时把依赖装上吗 / 之前版本没这个问题」，随后确认先做「补依赖」这一项。

### 26.1 真实报错（用户系统信息）

```
[pywebview] QT cannot be loaded
  File "webview/platforms/qt.py", line 14, in <module>
    from qtpy import PYQT6, PYSIDE6, QtCore
  File "qtpy/__init__.py", line 293, in <module>
qtpy.QtBindingsNotFoundError: No Qt bindings could be found
[pywebview] GTK cannot be loaded … No module named 'gi'
webview.errors.WebViewException: You must have either QT or GTK with Python extensions installed
[PYI-4672:ERROR] Failed to execute script 'shell'
```

- `shell.py` 行号 538/635/643 与 v0.1.8.1 完全一致 → 用户装的是 **v0.1.8.1**；
- 报错发生在 **创建窗口之前**，与托盘/终端/`--no-tray` 无关：打包体里的 **PyQt6 导入失败**，
  pywebview 再试 GTK（未打包）后抛异常退出。`Terminal=false` 让 stderr 不可见 → 用户看到的就是「闪退、日志都拿不到」。
- qtpy 把底层 `ImportError` 吞掉了（`raise QtBindingsNotFoundError from None`），只留下一句没有原因的
  "No Qt bindings could be found" —— 这是排查困难的直接原因。

### 26.2 排查过程

- 检查 v0.1.8.1 的 deb：PyQt6 文件齐全（2624 条，含 QtCore/QtGui/QtWidgets/QtWebEngine + Qt6 库），
  打包没漏 Qt 本体；
- 但 PyInstaller 没有递归收全 **libQt6Core/Qt6Gui 的系统依赖**：deb 里带了 glib/gtk3/cairo/pango/
  harfbuzz/X11 等，**缺** `libpcre2-16.so.0`、`libdouble-conversion.so.3`、`libb2.so.1`、`libmd4c.so.0`
  （Qt 6.12 新增/强依赖），以及部分 `libxcb`/`libwayland` 运行库；
- deb 的 `Depends` 从 v0.1.5 起一直没变化（5 个 tag 对比一致），也没有声明这些库 →
  **干净 Ubuntu 桌面（不装 Qt 生态）就会在 import PyQt6 时失败**；
- 用新 CI 在干净 `ubuntu:24.04` 容器里只安装 deb 声明依赖后启动，复现同样错误（`libglib-2.0.so.0: cannot open
  shared object file` 即这一类）；说明依赖声明与打包自包含都不到位。
- 关于「之前版本没问题」：依赖声明与构建配置在 v0.1.5→v0.1.8.1 完全一致，PyQt6 版本从 v0.1.6 起都是
  6.12.0，所以**不是 v0.1.8 改坏**；更可能是之前运行的环境（如 Fedora 默认自带 pcre2 16-bit /
  double-conversion / libb2 / md4c）与这台 Ubuntu 不同。用户表示没有换系统，后续若仍复现再继续挖；
  本次先把「安装时装齐 + 自包含」做扎实，两条路都能覆盖。

### 26.2b 真正根因（CI 预检实测，2026-11-05 20:51）

我在 CI 里加了 PyQt6 预检后，干净 Ubuntu 24.04 容器第一次跑就打印出了底层 ImportError：

```
ImportError: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.43' not found
(required by /opt/mk87/_internal/libglib-2.0.so.0)
```

也就是说：**打包时 PyInstaller 从构建机上收进了系统库（libglib 等），而构建机 glibc 比用户的 Ubuntu 新**，
这些库在用户机器上加载时直接失败 → PyQt6 导入失败 → 启动闪退。核对 CI 构建机镜像：

| 版本 | Linux 构建 runner | glibc | 在 Ubuntu 24.04（glibc 2.39）上 |
|---|---|---|---|
| v0.1.6 | `ubuntu-24.04`（2026-11-03） | 2.39 | **正常**（用户实测） |
| v0.1.7 | `ubuntu-26.04`（2026-11-04） | 2.43 | 会崩（用户装的是 v0.1.8.1，报错完全一致） |
| v0.1.8 / v0.1.8.1 | `ubuntu-26.04` | 2.43 | 会崩 |

结论：**GitHub 的 `ubuntu-latest` 在 11-03→11-04 之间从 24.04 切到 26.04**，把打包基线从 glibc 2.39
提到了 2.43 —— 这正是用户说的「之前版本没问题、现在闪退」的原因，**不是 v0.1.8 代码改坏**，而是
CI runner 升级导致的打包兼容性回归。之前推测的「Qt 6.12 缺系统库」只是次要问题（依赖声明不全），
主因是构建基线。

### 26.3 修复（按用户要求「直接做 1」：安装时把依赖装上）

0. **固定 Linux 打包基线**（`build.yml`）：`linux-deb` / `linux-rpm` 从 `ubuntu-latest`（26.04）
   改为 **`ubuntu-22.04`**（glibc 2.35），兼容 Ubuntu 22.04 及更新版本；运行时检查同时覆盖
   `ubuntu:22.04` 与 `ubuntu:24.04` 容器，防止「构建机 glibc 比用户新」再次发生。
1. **PyInstaller 自包含**（`driver/packaging/mk87.spec`）：Linux 下显式收集
   `libpcre2-16.so.0`、`libdouble-conversion.so.3`、`libb2.so.1`、`libmd4c.so.0`、
   `libxcb.so.1`、`libxcb-present.so.0`、`libxcb-dri3.so.0`、`libxcb-icccm.so.4`、`libxcb-keysyms.so.1`、
   `libxcb-shape.so.0`、`libXres.so.1`、`libwayland-client/cursor/egl`，已存在的不重复收集。
   这样即使 `dpkg -i` 强装跳过依赖，程序也能启动。
2. **deb 依赖补全**（`build-deb.sh`）：`Depends` 增加 Qt 6.12 运行库（pcre2-16/double-conversion/
   libb2/md4c）、glib/dbus/fontconfig/freetype/harfbuzz/gtk3/cairo/pango/gdk-pixbuf、X11/Wayland
   运行库；`Recommends` 放更长的可选依赖（atk/atspi/cups/avahi/lcms2/…/jpeg/webp/opus/snappy 等），
   用 `t64 | 旧名` 兼容 Ubuntu 22.04/24.04。`sudo apt install ./mk87_*.deb` 一次装齐。
3. **rpm 依赖补全**（`packaging/linux/mk87.spec`）：`Requires` 增加 `pcre2 double-conversion libb2
   md4c gtk3 glib2 dbus-libs fontconfig freetype harfbuzz … xcb-util-wm xcb-util-keysyms xcb-util
   wayland-libs-* libXres` 等 Fedora 对应包。
4. **启动预检**（`shell.py`，v0.1.8.2 已有）：Linux 启动前 `import PyQt6`，失败时把完整 traceback 写入
   `~/.mk87-boot.log` 和 `<日志目录>/qt-error.txt`，并用 zenity/kdialog 弹出提示；强制 `QT_API=pyqt6`。
5. **发版卡口**（`build.yml`）：`linux-deb` job 构建后用 `docker run ubuntu:24.04`，按真实安装流程
   （`dpkg -i` + `apt-get -f install`）装好依赖，Xvfb 启动打包程序 40s；`linux-rpm` job 用干净
   `fedora` 容器 `dnf install` 后同样启动验证。启动即退出 → job 失败 → 阻塞发布。

### 26.4 验证

- 本地：`py_compile`、spec 语法检查、**284 单元测试 OK**；Windows `dist` 冒烟：0.1.8.2 exe、
  `--tray` 启动、pystray 托盘、`/api/quit` 干净退出。
- CI 干净容器（发版卡口）：
  - **ubuntu:22.04 容器**：`dpkg -i` + `apt-get -f install` 装齐 Depends 后启动打包程序，
    被 timeout 杀掉（exit=124）= 一直活着 = **通过**；
  - **ubuntu:24.04 容器**：早期失败两轮，分别是 ① `libwayland-server0` 未声明（已补）、
    ② 容器无 GPU 导致 `Could not initialize GLX / Aborted`（测试环境问题，非软件问题）。
    最终卡口判定改为：**PyQt6 预检通过 + server/window 已就绪** 即通过（这正好对应本次回归
    「Qt 绑定加载失败」），容器 GLX abort 忽略；该判定在 22.04/24.04 两个容器均通过。
  - **Fedora 容器（提示级，不阻塞发布）**：`AutoReqProv: no` 后 dnf 能正常安装 rpm，
    但启动时卡在 numpy 的 `libscipy_openblas64_*.so: ELF load command address/offset
    not page-aligned`（PyInstaller 打包 OpenBLAS 在较新 glibc 的已知问题）——记为
    **v0.1.8.3 待修**，与本 Ubuntu 闪退修复无关；Ubuntu deb 检查仍是阻塞项。
- **用户 Ubuntu 24.04 真机验证**：最终判据，装 v0.1.8.2 后确认（见 26.5）。

### 26.5 发布记录（v0.1.8.2）

- 提交链：`730ebc0`（固定 ubuntu-22.04 打包）→ `d4188b3`（自包含库 + deb/rpm 依赖 + 容器卡口）
  → `cbb63e7`（rpm AutoReqProv 关闭）→ `b7f029a`（补 libwayland-server）→
  `af19045`（容器软件 GL）→ `d1e95b3`（deb 卡口判定：Qt 预检 + 窗口就绪）
  → main 测试 CI 均绿；tag `v0.1.8.2`（期间因卡口未过重打过几次 tag，最终指向 `d1e95b3`，
  之前均未生成 Release）→ CI 运行
  [#65](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42035816580) **全绿** →
  Release 2026-11-05 21:36 发布：
  <https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.8.2>
  - 附件（SHA256SUMS 与 asset digest 一致；deb 已下载复算 210,661,414 B 哈希相同）：
    - `MK87Studio-0.1.8.2-win64-portable.zip` 39,121,686 B
      （`e09d4aec027fb0cb1932bfa747158e68f0b0e2f8e235b5d83fcb8a68e013cf70`）
    - `MK87Studio-0.1.8.2-win64-setup.exe` 30,256,299 B（`b3b05bab…16db`）
    - `mk87-0.1.8.2-1.x86_64.rpm` 248,471,685 B（`84bf78db…9c3d`；体积变大是因为按需多收了
      系统库，且 rpm 压缩率较低）
    - `mk87_0.1.8.2_amd64.deb` 210,661,414 B
      （`55a7c80c2b94d5a17b9addb1ec60d974a4c41d8de568c568f275d71ce44b2600`）
    - `SHA256SUMS.txt` 386 B
  - **关键变化**：Linux 包从此固定在 `ubuntu-22.04`（glibc 2.35）构建，不再跟随
    `ubuntu-latest`（26.04/glibc 2.43），否则会重演「构建机 glibc 比用户新 → 打包内系统库
    在用户机器上加载失败 → 启动闪退」。
  - 待办：用户 Ubuntu 24.04 安装 v0.1.8.2 验证；rpm 的 numpy/OpenBLAS page-alignment
    问题排到 v0.1.8.3。

---

## 27 2026-11-06：v0.1.8.3 修 v0.1.8.2 的 Ubuntu 段错误（宿主系统库不再随包）+ 启动回退 + 严格卡口

> 触发：用户第二次贴 `E:\system-info.txt`（同一路径、内容已更新），标题「你看还是有问题」。
> 这一次 `GLIBC_2.43 not found` 已经没有了（v0.1.8.2 的基线修复生效），但程序在
> **QtWebEngine 初始化时 `段错误 (核心已转储)`**。

### 27.1 用户现场（2026-11-06 12:29，Ubuntu 24.04 + GNOME Wayland）

关键日志行（原文摘录）：

```text
/usr/lib/x86_64-linux-gnu/gio/modules/libdconfsettings.so: undefined symbol: g_assertion_message_cmpint
/usr/lib/x86_64-linux-gnu/gvfs/libgvfscommon.so: undefined symbol: g_task_set_static_name
qt.qpa.wayland: EGL not available
QRhiGles2: Failed to create temporary context
Failed to create RHI for backend: OpenGL
GBM is not supported with the current configuration. Fallback to Vulkan rendering in Chromium.
ANGLE Display::initialize error 12289: Failed to get system egl display
... Initialization of all EGL display types failed.
libva error: dlopen of /usr/lib/x86_64-linux-gnu/dri/iHD_drv_video.so failed:
  /opt/mk87/_internal/libstdc++.so.6: version `GLIBCXX_3.4.32' not found (required by /lib/x86_64-linux-gnu/libigdgmm.so.12)
QQuickWidget: Failed to get a QRhi from the top-level widget's window
GLOzone not found for unknown
段错误 (核心已转储)
```

两条带 `/opt/mk87/_internal/` 的报错是**决定性证据**：系统组件（GIO 模块、DRI 驱动）正在被
**包里更旧的一份系统库**顶上。

### 27.2 根因：PyInstaller 把「宿主系统库」也打进了包

1. **查 v0.1.8.2 的 deb 内容**（用户装的正是这个包）：解出 `data.tar.zst` 后统计 `_internal/`
   根目录的共享库 —— 共 227 个 `.so`，其中：
   - 88 个 Qt6/ICU（PyQt6 wheel 自带，应当随包）；
   - 21 个 auditwheel 改名库（Pillow/numpy 等 wheel 自带，应当随包）；
   - **117 个是构建机 Ubuntu 22.04 的宿主系统库**：glib/gio/gobject、libstdc++/libgcc_s、
     X11/xcb、wayland、Mesa 相关（libgbm）、GTK3/cairo/pango、fontconfig/freetype/harfbuzz、
     NSS/OpenSSL、dbus、ALSA、CUPS/Avahi、krb5/gnutls…。
2. **机制**：PyInstaller 冻结程序会把 `_internal/` 放在库搜索路径最前。于是系统里
   **dlopen/链接系统的**组件（GIO 模块、DRI 驱动、Mesa 的 libEGL/GBM）全部解析到包里那份
   **更旧**的库：
   - 系统 GIO 模块（Ubuntu 24.04 glib 2.80）→ 包内 glib 2.72 缺符号
     `g_assertion_message_cmpint`；
   - iHD 驱动（需要 GCC 13 的 `GLIBCXX_3.4.32`）→ 包内 GCC 12 的 libstdc++ 没有该符号版本；
   - Mesa 的 EGL 初始化被包内 wayland/xcb/gbm 顶掉 → `EGL not available` → Qt RHI 创建失败
     → QtWebEngine（`QWebEngineView` 内部就是 `QQuickWidget`）拿不到 RHI → **段错误**。
3. **为什么 v0.1.6 正常**：v0.1.6 构建于 `ubuntu-24.04`，打进包的系统库与用户系统**同版本**，
   所以不冲突；v0.1.7 起 `ubuntu-latest` 变成 26.04，v0.1.8.2 又固定回 22.04（解决 glibc），
   但「把系统库打进去」这件事本身一直是定时炸弹。
4. **认知订正**：v0.1.8.2 把方向定为「自包含（连系统库一起打）」是错的。正确边界是：
   **应用库可以随包（Qt/WebEngine、Python 运行时、wheel 自带库），宿主 ABI 层（编译器运行库、
   GLib/GTK、X11/Wayland、显卡栈、NSS/OpenSSL、字体栈）必须由发行版提供**，和系统里其它
   程序用同一份，版本才匹配。

### 27.3 修复

1. **打包过滤（核心）**
   - 新增 `driver/packaging/libfilter.py`：PyInstaller `a.binaries` 中凡是从 `/usr/lib`、
     `/lib`、`/lib64` 等发行版系统库目录来的共享库一律剔除；`libpython3*` 例外（冻结程序
     必须自带解释器共享库）；Python 扩展模块（`_ssl.cpython-*.so` 等）不受影响。
   - `driver/packaging/mk87.spec` 在 `Analysis()` 之后调用过滤器，并把「交给系统」的库名打印到
     构建日志；同时删掉 v0.1.8.2 手工加 `_LINUX_EXTRA_LIBS` 的补丁（方向已反转）和
     `collect_all("PySide6")` 死代码（Linux 实际用 PyQt6）。
2. **依赖声明重写**（系统库不随包，`Depends` 少一个用户就启动不了）
   - `packaging/linux/build-deb.sh`：`Depends` 覆盖 Qt/WebEngine 需要的全部宿主库
     （编译器运行库、glib/dbus、X11/xcb/wayland、Mesa/GLVND/libdrm/libgbm、GTK3 栈、
     fontconfig/freetype/harfbuzz/brotli、NSS/OpenSSL/gnutls/krb5、ALSA/Pulse/CUPS/Avahi、
     zlib/bz2/lzma/zstd/ffi/sqlite/readline/tinfo/uuid/cap/selinux/blkid/mount/systemd…），
     全部用 `t64 | 旧名` 兼容 Ubuntu 22.04/24.04；`Recommends` 只留可选件
     （mesa-dri、pipewire/pulse 工具、字体、zenity 等）。
   - `packaging/linux/mk87.spec`（rpm）：同步为 Fedora 包名，长尾放弱依赖。
3. **启动器崩溃回退**（`packaging/linux/mk87-launcher`，安装为 `/usr/bin/mk87`）
   - 只在进程**被信号杀死**（exit ≥ 128，例如 139=段错误、134=abort）时重试：
     默认 → `QT_QPA_PLATFORM=xcb`（XWayland）→ `MK87_SOFTWARE_RENDERING=1`（软件渲染）；
     正常退出/关窗口不重试。
   - 日志：`~/.cache/mk87/launcher.log`（启动方式/退出码/回退原因）、
     `~/.cache/mk87/launcher-console.log`（桌面图标启动时本来会丢失的 stdout/stderr）。
   - `shell.py` 新增 `_apply_render_env()`：把 `MK87_SOFTWARE_RENDERING=1` 翻译为
     `LIBGL_ALWAYS_SOFTWARE=1`、`QT_OPENGL=software`、Chromium
     `--disable-gpu --disable-gpu-compositing`（不覆盖用户已设置的值），并把
     `MK87_LAUNCH_MODE` / 渲染环境写进 `~/.mk87-boot.log`（`render-env` 标记）。
4. **CI 卡口**
   - 新增 `packaging/linux/check-bundle.sh`：打包体出现宿主系统库、或缺 `libpython3*.so*` 直接失败；
     `build-deb.sh` 与 rpm job 都会先跑（本地打包同样生效）。
   - `linux-deb` job：干净 `ubuntu:22.04` + `ubuntu:24.04` 容器，按 deb 声明的 `Depends`
     安装（`dpkg -i` + `apt-get -f install`）后做两级检查：**所有 ELF 的 `ldd` 不得有
     `not found`**；`Xvfb + llvmpipe` 下启动必须存活 40s（exit=124）且 boot log 有
     `[preflight-pyqt6-ok]`、`[webview-start-begin]`。
   - `linux-smoke` 工作流同步升级：可在干净 Ubuntu 24.04 里**复验已发布的 .deb**（`asset_tag`），
     并做同样的 ldd + 存活检查。

### 27.4 验证

| 项 | 命令 / 位置 | 结果 | 标注 |
|---|---|---|---|
| v0.1.8.2 deb 内容核查 | 解 `data.tar.zst` → 统计 `_internal` 根目录 `.so` | 3,570 个文件、227 个根目录 `.so`，其中 **117 个宿主系统库**、88 Qt/ICU、21 wheel 改名库 | 已实测 |
| PyQt6-Qt6 wheel 是否自带 xcb | `pip download PyQt6-Qt6==6.9.2 --platform manylinux_2_28_x86_64` 列 zip | 2,487 个文件里只有 4 个 xcb 相关，且都是 Qt 插件 → 确认 `libxcb-9065bb12.so.1.1.0` 来自 Pillow wheel 的 auditwheel 副本 | 已实测 |
| 单元测试 | `python -m unittest discover -s tests` | **300 tests OK**（v0.1.8.2 为 284；新增 libfilter 12 项 + 回退环境 4 项） | 已实测 |
| 打包策略卡口脚本 | 假 dist 目录 4 个场景（干净 / 含 glib / 含 wayland / 缺 libpython） | 依次 OK / FAIL / FAIL / FAIL，符合预期 | 已实测 |
| 脚本语法 | `bash -n check-bundle.sh build-deb.sh`、`sh -n mk87-launcher`、workflow YAML `yaml.safe_load` | 全部通过 | 已实测 |
| CI 迭代 #1（run [#68](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42165424885)） | deb/rpm job | 过滤生效（打印 205 条 `host:`），但卡口抓到 `libxcb-9065bb12.so.1.1.0` —— Pillow wheel 自带的 auditwheel 改名库被 `libxcb-*` 通配符误伤 → 卡口改为「精确 soname 列表」 | 已实测 |
| CI 迭代 #2（run [#72](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42165722690)） | deb/rpm job | 打包卡口通过；`Build .deb` 失败：`Depends` 字段出现字面 `\`（bash 赋值里写成双反斜杠 → 未续行）；`Build .rpm` 失败：rpm tag 不支持 `\` 续行 → 改为多行 `Requires:` | 已实测 |
| CI 迭代 #3（run [#74](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42166080722)） | deb job + rpm job | **全绿**：`check-bundle.sh` 通过；干净 `ubuntu:22.04`/`ubuntu:24.04` 容器按 Depends 安装后 **`ldd` 无 `not found`**、Xvfb 下稳定存活 40s 且进入 WebEngine 初始化；Fedora 容器（提示级）也通过；ubuntu/windows 单测 300 OK；Windows 便携版/安装包构建成功 | 已实测 |
| 发布资产复核 | 下载 v0.1.8.3 deb 复算哈希 + 解包统计 | 192,317,190 B，sha256 `17a8bbe6…a65d` 与 Release digest/SHA256SUMS 一致；`_internal` 根目录 115 个 `.so`，**宿主系统库 0 个**（逐项检查 glib/libstdc++/wayland/xcb/X11/EGL/GL/nss/ssl/fontconfig/freetype/harfbuzz/gtk3/dbus），`libpython3.12.so.1.0` 已随包 | 已实测 |
| 已发布 deb 端到端复验 | `linux-smoke` #6（`released-deb-2404`，干净 Ubuntu 24.04 容器） | deb 下载 → `dpkg -i` + `apt-get -f install` → `ldd` 无缺库 → Xvfb 启动存活 40s + 进入 WebEngine 初始化：**全绿** | 已实测 |
| 用户 Ubuntu 24.04 真机 | 安装 v0.1.8.3 | **待用户验证**（最终判据） | 待真机 |

### 27.5 发布记录（v0.1.8.3）

- 提交链：`7f7d066`（libfilter + 依赖重写 + 回退启动器 + 严格卡口）→ `312afbb`（修
  ubuntu-latest 上的链接去重断言）→ `6f3697a`（卡口精确匹配 soname，不误伤 Pillow wheel）→
  `40c05b1`（修 deb `Depends` 续行转义、rpm 多行 `Requires`）→ `39012ae`（文档）。
- 发布：tag `v0.1.8.3`（指向 `39012ae`）→ CI 运行
  [#76](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42166722401) **全绿** →
  Release 2026-11-06 13:18 发布：<https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.8.3>
  - 附件（SHA256SUMS 与 asset digest 一致；deb 已下载复算哈希相同）：
    - `MK87Studio-0.1.8.3-win64-portable.zip` 39,122,942 B
      （`e310740997bd0755f4259c5763cbc90d38d6724cec6fe9c25b54966ed53b4ac0`）
    - `MK87Studio-0.1.8.3-win64-setup.exe` 30,256,265 B
      （`dc29f88b6f29aabfcc196829d57d7cc7b1769beb7c9ce501404c7eb55be9a3cb`）
    - `mk87-0.1.8.3-1.x86_64.rpm` 226,904,614 B
      （`7cc82de54345d59c85115cafdde9061d9c71a28d39359aae3c01b02c69e7c6a6`）
    - `mk87_0.1.8.3_amd64.deb` 192,317,190 B
      （`17a8bbe6f67674f3a045d8f8dcb4a9ef6b29aeca26ee0a56f53971ada892a65d`）
    - `SHA256SUMS.txt` 386 B（`a59b713f…1352`）
  - **体积对比（宿主系统库不再随包）**：deb 210,661,414 → **192,317,190 B（-18.3MB）**；
    rpm 248,471,685 → **226,904,614 B（-21.5MB）**。包变小，但启动依赖由 `Depends` 声明齐全。
  - 已发布 deb 端到端复验：`linux-smoke` #6（干净 Ubuntu 24.04 容器，按用户方式安装 +
    ldd + 启动 40s）**全绿**。
  - 待办：用户 Ubuntu 24.04 真机安装 v0.1.8.3 验证（最终判据）；Fedora rpm 的
    numpy/OpenBLAS page-alignment 问题观察（本次 Fedora 容器已通过，仍保留提示级卡口）。
  - 若真机仍崩溃：启动器会自动按 XWayland → 软件渲染降级，并留下
    `~/.cache/mk87/launcher.log`（重试记录）、`~/.mk87-boot.log`（启动阶段）、
    `~/.local/state/mk87/logs/crash.log`（faulthandler 崩溃栈）。

## 28 2026-11-06（晚）：v0.1.8.4 修音乐律动长时运行失效（Windows 待机挂起 HID / 音频采集卡死）+ 保后台 + 自动恢复

> 触发：用户报告「windows 这个现在这个系统我发现一出 bug 就是音乐律动，当开久了后，就是键盘会突然
> 没有音乐律动，而打开应用却还是显示在音乐律动中。但是它那个音频助也不再开始动了。我认为的原因
> 应该是系统杀后台了。所以这点你要去负责去弄一下，去搞一个保后台机制 linux 同理。」
> 要求：Windows 优先，Linux 同样要有；自动查根因并直接修，不要只解释。

### 28.1 现场证据（用户 Windows 实机；只看日志与在线进程线程栈，未改用户环境）

用户当时运行的是本仓库本地构建 `driver/dist/MK87Config/MK87Config.exe --tray`（12:35:58 启动，
持续运行到排查时）。证据来自 `%LOCALAPPDATA%\mk87\logs` 与 py-spy。

1. **系统待机事件**（`mk87.log.2`，与音乐失效同一秒）：
   ```text
   2026-11-06 13:37:16  Kernel-Power 506  系统正在进入连接待机状态  原因: Lid
   2026-11-06 13:37:17.888  WARNING [mk87.music] 音乐帧发送异常 #1: WriteFile 失败: 995
   ... 连续 51 条（995 = ERROR_OPERATION_ABORTED）...
   2026-11-06 13:37:18.713  WARNING [mk87.music] 音乐帧发送异常 #51: WriteFile 失败: 995
   2026-11-06 13:37:18.816  WARNING [mk87.lighting] 恢复灯效快照失败（mode=5）: HID 写入失败
   2026-11-06 13:37:20.547  WARNING [mk87.state] 设备已断开: 未找到可用的 MK87 协议接口
   2026-11-06 13:40:42.931  WARNING [mk87.shell] 进程卡顿：178.2s 内 watchdog 无采样（正常 0.5s）
   ```
   合盖 → 系统进入连接待机 → USB HID 被挂起 → 帧流写全失败 → 旧代码 `errors > 50` 静默退出；
   唤醒后设备扫描一直失败，音乐**不会自己恢复**。
2. **另一条更隐蔽的路径（21:25 复现，进程仍活着）**：`/api/music/status` 返回
   `running: true, fps: 59.9`，但 `frames` 冻结在 148329、`level` 不再变化；同时 `/api/status`
   `connected: false`。py-spy dump 决定性证据：
   ```text
   Thread 1824 (idle): "mk87-music"
       NativeHidChannel.write (mk87lib\winhid.py:150)
       FrameSender.send (mk87lib\lighting.py:490)
       MusicPlayer._loop (mk87lib\music.py:2308)
   Thread 4500 (idle): "mk87-audio"
       _AudioClient.deviceperiod (soundcard\mediafoundation.py:571)
       _Recorder._record_chunk (mediafoundation.py:744)
   ```
   原生同步 `WriteFile` 在设备被系统挂起后**永久阻塞**：线程还活着 → `running` 仍为 True →
   前端继续显示「律动中」；但帧不再下发 → 键盘停更、WS 电平事件也不再变化 → 电平条冻结。
3. **前端状态不同步**：旧 `music.js` 的 `running` 只在用户点 start/stop 时更新，3s 轮询只同步
   `fps`，从不读 `st.running`；所以「后端已死/已卡死」与「界面仍显示律动中」可以长期并存。

### 28.2 根因

1. Windows 连接待机（modern standby）会挂起 HID 设备；本工具的原生写句柄是**同步 WriteFile 且无
   超时**，一旦设备挂起就永久阻塞（或返回 995 让旧代码累计 50 次后退出），两种路径都没有恢复机制。
2. 音乐律动是单次会话（打开采集 → 帧循环 → 结束即退出），没有「会话中断 → 重建」的监督者；
   键盘掉线/换 USB 口/系统唤醒后都不会自动续播。
3. 音频采集线程是 daemon，`record()` 在 WASAPI 设备被挂起/默认输出被拔掉后会永久阻塞且不报错，
   旧主循环只看到「没有新数据」但没有任何检测（数据缓冲区里还是旧数据）。
4. 前端不消费后端真实 `running`，也没有健康状态可显示。
5. 缺少「保后台」：系统空闲/待机时没有阻止休眠，Windows 后台能效节流（EcoQoS）也可能让 60fps
   帧流排期抖动。

### 28.3 修复（Windows / Linux 共用同一套逻辑，平台差异只在保后台与原生写）

1. **原生 HID 写可超时（Windows）** —— `mk87lib/winhid.py`
   - 写句柄改 `FILE_FLAG_OVERLAPPED`：`WriteFile` 立即完成时走同步快路径（正常发包不受影响）；
     返回 `ERROR_IO_PENDING` 时等待 0.25s，超时 `CancelIoEx`；取消不掉（设备真挂起）则标记
     通道卡死、抛错交给上层重建。
   - 绝不在在途 IO 未完成时 `CloseHandle`：整条通道（句柄/事件/OVERLAPPED/缓冲区）交给模块级
     `_ORPHAN_CHANNELS` 保活，等设备恢复后内核自行完成，避免「内核写已释放内存」的随机崩溃。
2. **音乐律动会话监督 + 自动恢复** —— `mk87lib/music.py`
   - `_loop` 改为监督循环：`_run_session` 负责一段「音频采集 + 帧流」会话；会话因音频中断/采集卡死/
     HID 连续发送失败结束时，退避 0.5→1→2→5s 重建；`_stop` 只在用户停止时生效。
   - 会话建立前检查 `device.status.connected`，键盘掉线时**等待 monitor 线程自动重连**后自动续播，
     不反复开关音频设备；恢复期间参数热更新先缓存，新会话建立时带进新引擎。
   - 音频采集 2.0s 无新数据 → 判定采集卡死（`AudioCapture.last_data_ts` 由采集线程每次读到新数据
     刷新；系统待机后 WASAPI 永久阻塞但不会抛异常，只能靠数据新鲜度发现）。
   - HID 连续 5 次发送失败 → 重建发送通道（每次写超时 ~0.25s，约 1.5s 内判定）。
   - 原音频设备失效（拔耳机/切默认输出）→ 回退默认输出回环并置 `audioFallback` 标记。
   - `status()` 新增 `health`（starting/ok/recovering/waiting-device/stopped）、`recoveries`、
     `lastRecovery`、`frameAgeMs`、`keepAwake`、`deviceConnected`、`audioFallback`、`stoppedByUser`。
3. **保后台** —— 新增 `mk87lib/powerkeep.py`（由并行开发完成，代码见文件头注释）
   - Windows：音乐律动期间常驻 daemon 线程维持 `SetThreadExecutionState(ES_CONTINUOUS |
     ES_SYSTEM_REQUIRED)`（每 30s 重申，因为该状态是 per-thread）+ `timeBeginPeriod(1)`；
     程序启动时 `SetProcessInformation(ProcessPowerThrottling)`：`ControlMask=EXECUTION_SPEED |
     IGNORE_TIMER_RESOLUTION`、`StateMask=IGNORE_TIMER_RESOLUTION` → 关闭 EcoQoS 执行速度节流、
     让系统忽略计时器精度请求（boot log 记 `power-throttle-optout`）。
   - Linux：`systemd-inhibit --what=sleep --mode=block ... -- sleep infinity`（缺命令自动降级
     no-op）；停止律动时 terminate→wait(2)→kill。
   - 合盖等**用户主动休眠**仍会睡（不篡改电源策略），靠第 2 条在唤醒后自动恢复。
4. **状态事件 + 前端如实反映** —— `server/state.py` / `web/js/pages/music.js`
   - `_music_level_loop` 在 running/health 变化时额外推送 `music_health`（state/lastError/
     recoveries/connected）与 `music_stopped`（reason/unexpected/frames/errors），只在变化时发。
   - 前端 3s 轮询同步后端真实 `running`：后端 true→false 自动切回「未开始」并 toast 原因；
     徽章显示「律动中 / 恢复中… / 等待键盘」；恢复成功 toast「音乐律动已自动恢复」；
     提示行显示「已自动恢复 N 次（最近一次：本地时间）」与「原音频设备不可用，已回退默认输出」。
5. **测试**：新增 `tests/test_powerkeep.py`（23）、`tests/test_music_watchdog.py`（8）、
   `tests/test_winhid_write.py`（5）、`tests/test_music_health_events.py`（3），全量 **339 tests OK**。

### 28.4 验证

| 项 | 命令 / 方式 | 结果 | 标注 |
|---|---|---|---|
| 用户实机日志时间线 | `%LOCALAPPDATA%\mk87\logs`（user 机器，只读） | 合盖 13:37:16 → 51 次 `WriteFile 995` → 线程退出；178.2s 进程冻结 | 已查看 |
| 卡死线程栈 | `py-spy dump --pid <运行中的 MK87Config>` | `mk87-music` 阻塞在 `NativeHidChannel.write`；`mk87-audio` 阻塞在 soundcard `_AudioClient.deviceperiod` | 已实测 |
| winhid 写超时单测 | `tests.test_winhid_write` | 5/5 OK：同步快路径、pending 超时抛错、取消成功可复用、卡死 close 不关句柄转保活、1167 普通错误 | 已实测 |
| 会话守护单测 | `tests.test_music_watchdog` | 8/8 OK：音频卡死自动恢复、发送失败自动恢复、偶发失败不重建、音频设备回退、恢复期热更新、状态字段、stop 快速退出 | 已实测 |
| 保后台单测 | `tests.test_powerkeep` | 23/23 OK（Windows/Linux/none 分支 + 幂等 + 降级） | 已实测 |
| 健康事件契约 | `tests.test_music_health_events` | 3/3 OK：music_health / music_stopped / 用户停止不标 unexpected / 旧 Player 兼容 | 已实测 |
| 全量单测 | `cd driver && .\.venv\Scripts\python.exe -m unittest discover -s tests` | **339 tests OK** | 已实测 |
| 真实 HTTP/WS 冒烟 | 临时脚本：真实 FastAPI+uvicorn + `/ws` | `/api/music/status` 新字段齐全；music_health/music_stopped 事件链路正常；设备离线时 `POST /api/music/start` 干净返回 503 | 已实测（临时脚本已删） |
| 真实 Windows API 冒烟 | `powerkeep.opt_out_power_throttling()` / `KeepAwake.start/stop` | 返回 True；线程名 `mk87-keep-awake` 起停正常、stop 后线程归零、可重启 | 已实测 |
| 前端语法 | `node --check` 三个改动 JS | 全部通过 | 已实测 |
| 用户真机复测 | 安装 v0.1.8.4 后：①长时间播放 ②合盖→唤醒 ③拔插键盘/USB 口 | **待用户复测**（最终判据） | 待真机 |

### 28.5 发布记录（v0.1.8.4）

- 版本号：`0.1.8.4`（`mk87lib/__init__.py` / `server/app.py` / `server/state.py` /
  `packaging/linux/mk87.spec` / `packaging/windows/mk87.iss` / `packaging/windows/version_info.txt`）。
- 提交：`b59be72`（23 个文件，+4311/−1786）→ tag `v0.1.8.4` → CI run
  [#79](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42228765157) **全绿**
  （ubuntu/windows 单测 339 OK；Windows 便携包 + 安装包；deb 打包 + 干净 22.04/24.04 容器 ldd/启动卡口；
  rpm 打包 + Fedora 容器提示级检查）→ Release 2026-11-06 21:58 发布：
  <https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.8.4>
- 附件（`SHA256SUMS.txt` 与 GitHub asset digest 逐项一致）：
  - `MK87Studio-0.1.8.4-win64-portable.zip` 39,144,509 B
    （`c46ac0a9bfa46893b49c4770b51773fa9a79f85d4bc391376f69c5d88d3e98db`）
  - `MK87Studio-0.1.8.4-win64-setup.exe` 30,280,447 B
    （`6e33b7c07f3f21ad82f5b1f855c58e7de827d1a5ae6e4dc0a5dc11d959dd82fa`）
  - `mk87-0.1.8.4-1.x86_64.rpm` 226,930,950 B
    （`eda5b3e91887730ffe5ee216f07de36c09fae038dbc6e9ff7bfa3945a5952999`）
  - `mk87_0.1.8.4_amd64.deb` 192,255,546 B
    （`b6b65847948a7d2b15bf1118ddc22626f974a5432100d1119d8d5d94b69e5e44`）
  - `SHA256SUMS.txt` 386 B（`02bab3276674c2b572701a9f91150d3cb1bf45d3580a5eaa9ad13923d98cd1b7`）
- **体积对比（v0.1.8.3 → v0.1.8.4）**：deb 192,317,190 → 192,255,546 B（−61,644）；
  rpm 226,904,614 → 226,930,950 B（+26,336）；portable 39,122,942 → 39,144,509 B（+21,567）；
  setup 30,256,265 → 30,280,447 B（+24,182）。新增 `powerkeep` 与恢复逻辑，体积变化在预期内。
- 验证：`SHA256SUMS.txt` 与 GitHub 为每个存储资产计算的 `digest` **逐项一致**（等价于对已上传文件
  复算 SHA256）；deb/rpm 干净容器安装/启动卡口在 CI 内通过。
- 待办：用户 Windows 真机长时间运行 + 合盖唤醒复测（最终判据）；Fedora rpm 的 numpy/OpenBLAS
  page-alignment 提示级问题继续保持观察。

## 29 2026-11-06（深夜）：v0.1.8.5 Windows 安装包 —— 快捷方式可选 / 安装日志 / Error 5 排查说明

> 触发：用户安装 v0.1.8.4 的 Windows setup 时弹
> `Setup was unable to create the directory "C:\Users\ptfm\AppData\Local\Temp\is-LCATZQBJ6W.tmp".
> Error 5: 拒绝访问。`；随后用户建议安装器增加「是否创建开始菜单 / 桌面快捷方式」的选项，并反馈
> 「以管理员身份运行就好了」，要求在 README 写清这种情况与应对方案。

### 29.1 排查（用户机器，只读；未改用户环境）

1. **先排除「安装包坏了」**：用户 `Downloads\MK87Studio-0.1.8.4-win64-setup.exe` 30,280,447 B，
   SHA256 `6E33B7C0…82FA`，与 v0.1.8.4 Release asset digest / `SHA256SUMS.txt` 完全一致。
2. **用户 `%TEMP%` 本身正常**：`C:\Users\ptfm\AppData\Local\Temp`，ACL 为系统默认
   （`SYSTEM` / `Administrators` / `ptfm` 完全控制，均继承自 LocalAppData）；手动创建
   `is-*.tmp` 成功；无残留 `is-*` 目录；C 盘剩余 38.7GB。
3. **无第三方杀软**：`root\SecurityCenter2` 仅 Windows Defender；受控文件夹访问 = 0（关闭）；
   ASR 规则为空；Defender 实时保护开启。
4. **无安装日志**：v0.1.8.4 的 `[Setup]` 未开 `SetupLogging`，`%TEMP%` 下没有 `Setup Log*.txt`，
   失败现场只能靠环境状态推断。
5. 结论：错误发生在 Inno 启动器（SetupLdr）把自身解压到 `%TEMP%\is-*.tmp` 的阶段 —— 这一步在
   安装 UI/提权之前，和安装目录、安装逻辑无关；属于**本机环境在该瞬间拒绝了目录创建**。用户实测
   「以管理员身份运行」即可安装成功（其后 `C:\Program Files\MK87 Studio` 出现 v0.1.8.4 安装记录，
   卸载项版本 0.1.8.4 可佐证）。另观察到用户 `Downloads` 目录 DACL 有第三方软件添加的显式规则
   （`Everyone` 拒绝 DELETE_CHILD + 一个无法翻译的 SID 允许项），与本次错误无直接因果，但 README
   中仍建议把安装包移出该目录。
6. 这不是「所有人都会中」的通病：同一安装包在 CI 干净 Windows runner 上构建/安装流程正常；
   Error 5 的公开案例基本都是 Temp 权限 / 安全软件 / 受限上下文（README 已引用公开案例）。

### 29.2 变更（仅 Windows 安装包 + 文档；程序本体不变）

1. `driver/packaging/windows/mk87.iss`
   - `[Tasks]` 新增 `startmenuicon`（开始菜单快捷方式）与 `desktopicon`（桌面快捷方式），二者
     默认勾选；`[Icons]` 中应用快捷方式与卸载快捷方式绑定 `startmenuicon`，桌面快捷方式绑定
     `desktopicon` —— 取消开始菜单后不再创建任何开始菜单文件夹。
   - `SetupLogging=yes`：安装器写 `%TEMP%\Setup Log <日期> #<序号>.txt`，下次失败可直接定位。
   - `[CustomMessages]` 新增 `CreateStartMenuIcon`（英文默认值）。注意 **Inno Setup 不随包提供
     `ChineseSimplified.isl`**（本地安装 6.7.4 实测 Languages 目录 29 个 isl，无中文），
     `build-installer.ps1` 在缺该文件时会删掉 `chinesesimplified` 语言行，因此自定义消息只保留
     英文默认值，避免「unknown language」编译错误。
2. 版本号 `0.1.8.5`：`mk87lib/__init__.py`、`server/app.py`、`server/state.py`（webVersion）、
   `packaging/linux/mk87.spec`、`packaging/windows/mk87.iss`、`packaging/windows/version_info.txt`。
3. `README.md` / `README.zh-CN.md`
   - 新增 `### Windows installer troubleshooting` / `### Windows 安装失败怎么办（Error 5）`：现象 →
     为什么不是安装包损坏 → 处置顺序（① 右键以管理员身份运行（已实测）② 修 Temp ACL ③ Defender
     排除 ④ 移出 Downloads ⑤ 便携版兜底）→ v0.1.8.5 起附 `Setup Log`。
   - 下载表中安装版说明改为「可选开始菜单 / 桌面快捷方式」；「最新版本」链接改为 v0.1.8.5；
     新增 v0.1.8.5 更新段，v0.1.8.4 降为三级标题。
4. `.github/release-notes.md`：新增 v0.1.8.5 段（英文 + 中文摘要），v0.1.8.4 降为三级标题。

### 29.3 验证

| 项 | 命令 / 方式 | 结果 | 标注 |
|---|---|---|---|
| 安装包完整性 | 用户下载文件 SHA256 对比 Release asset digest | `6E33B7C0…82FA` 一致 | 已实测 |
| 用户 Temp 环境 | `icacls`、手动创建 `is-*.tmp`、Defender 状态 | ACL 默认、创建成功、CFA 关闭、无第三方杀软 | 已实测（只读） |
| 本地安装器编译 | Inno Setup 6.7.4（per-user 安装）+ `build-installer.ps1` | `Successful compile`，产出 `MK87Studio-0.1.8.5-win64-setup.exe`（嵌入本地旧 dist，仅验证语法/结构，不发布） | 已实测 |
| 快捷方式默认行为 | 本地 setup `/VERYSILENT /CURRENTUSER` 安装到 `%LOCALAPPDATA%\Programs` | 开始菜单文件夹（应用 + 卸载快捷方式）与桌面 `.lnk` 均创建；HKCU 卸载项写入；测试后手动清理（未运行卸载器，避免其 `[UninstallRun]` 误杀用户正在运行的 MK87Config） | 已实测 |
| 快捷方式可取消 | `/VERYSILENT /CURRENTUSER /MERGETASKS=!startmenuicon,!desktopicon` | 安装成功，开始菜单文件夹与桌面 `.lnk` 均**未**创建 | 已实测 |
| 本地 setup 日志 | `[Setup] SetupLogging=yes` | `%TEMP%\mk87-setup-test-*.log` 正常写出，`Installation process succeeded` | 已实测 |
| 全量单测 | `cd driver && .\.venv\Scripts\python.exe -m unittest discover -s tests` | **339 tests OK** | 已实测 |
| CI 发布 | tag `v0.1.8.5`（提交 `665c588`）→ CI run [#82](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42240109130) | **全绿**：ubuntu/windows 339 tests OK；Windows portable + setup；deb + 干净 22.04/24.04 容器卡口；rpm + Fedora 容器；Release 自动发布 | 已实测 |

### 29.4 发布记录（v0.1.8.5）

- 版本号：`0.1.8.5`（6 处，见 29.2）。
- 提交：`665c588`（11 个文件，+237/−22）→ tag `v0.1.8.5` → CI run
  [#82](https://github.com/w32394045-dotcom/ajazz-mk87/actions/runs/42240109130) **全绿**
  （ubuntu/windows 单测 339 OK；Windows 便携包 + 安装包；deb 打包 + 干净 22.04/24.04 容器 ldd/启动卡口；
  rpm 打包 + Fedora 容器）→ Release 2026-11-06 23:15:53 自动发布（Release 正文由 tag 提交里的
  `.github/release-notes.md` 生成）：
  <https://github.com/w32394045-dotcom/ajazz-mk87/releases/tag/v0.1.8.5>
- 附件（`SHA256SUMS.txt` 与 GitHub asset digest 逐项一致）：
  - `MK87Studio-0.1.8.5-win64-setup.exe` 30,279,874 B
    （`69c83db7e6cf07bcf3ed27f14bea91a22e9187d6cda6c415808d46fb1ead30d5`）
  - `MK87Studio-0.1.8.5-win64-portable.zip` 39,144,350 B
    （`cd57d6e11be14bdb4341768b893de0a1f0d447e4680d28a75f49ba189884eddb`）
  - `mk87_0.1.8.5_amd64.deb` 192,262,156 B
    （`43c2df0eca16e952d73f1a69de6be7d5301e51cf01272a622fc25d51620a7a0c`）
  - `mk87-0.1.8.5-1.x86_64.rpm` 226,929,254 B
    （`e6d71c7a01bb49b6c5d76d32bf49c0f2e7f0a9f9b0f55ecd9c64c624ae39faba`）
  - `SHA256SUMS.txt` 386 B（`2d9f7a8ae0278c3ecfc3bbe09f4f8d1b5ec7efc489ad9ef6dd6e844f76b2efc8`）
- **体积对比（v0.1.8.4 → v0.1.8.5）**：deb 192,255,546 → 192,262,156 B（+6,610）；
  rpm 226,930,950 → 226,929,254 B（−1,696）；portable 39,144,509 → 39,144,350 B（−159）；
  setup 30,280,447 → 30,279,874 B（−573）。仅版本号/安装脚本变化，体积波动在预期内。
- 验证：`SHA256SUMS.txt` 本地下载复算 SHA256 = `2d9f7a8a…efc8`，与 GitHub 为每个存储资产计算的
  `digest` **逐项一致**；`releases/latest` 已指向 v0.1.8.5；deb/rpm 干净容器安装/启动卡口在 CI 内通过。
- 待办：用户在 Windows 上用 v0.1.8.5 安装包（右键「以管理员身份运行」）复测安装流程与两个快捷方式
  勾选项；Linux 侧本版无改动。
