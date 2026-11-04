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
