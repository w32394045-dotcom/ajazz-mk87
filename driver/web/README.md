# MK87 Studio — 前端（driver/web）

AJAZZ MK87（VID `0x0C45` / PID `0x8047`，2.4G `0xFEFE`）跨平台配置工具的本地 Web UI。
**原生 HTML / CSS / ES Modules，零构建步骤、零外部 CDN、完全离线可用。**

接口契约见 [`driver/docs/design.md`](../docs/design.md) §4，硬件规格见
`driver/docs/spec-protocol.md` / `spec-keymap.md` / `spec-lighting.md` / `spec-tft-wireless.md`。

---

## 1. 启动

### 正常使用（推荐，带真实设备）

```bash
# 在仓库根目录（Windows PowerShell 也可，用 .\driver\.venv\Scripts\python.exe 亦可）
python -m mk87            # 启动后端并自动打开浏览器（默认 http://127.0.0.1:8477/）
# 或只起服务：
mk87 --no-browser --port 8477
```

后端会直接托管本目录（`GET /` = `index.html`），**不需要额外静态服务器**。
`mk87 --mock` 时后端用模拟设备，前端仍走正常 REST/WS（不是前端内置 mock）。

### 纯前端调试（没有 Python 后端）

```bash
# 用任意静态服务器指向 driver/web
python -m http.server 8123 --directory driver/web
# 浏览器打开：
#   http://127.0.0.1:8123/            → 自动探测 /api/status，失败则自动进入 mock
#   http://127.0.0.1:8123/?mock=1     → 强制 mock（推荐，避免等待探测超时）
```

前端启动时先 `GET /api/status`（1.6s 超时）：成功 → 真实后端模式；失败 → 动态 import
`js/mock.js` 启用内置 mock。两种模式页面完全相同，数据层不同。

---

## 2. 目录结构

```text
driver/web/
├── index.html                # 单页应用外壳（侧边导航 / 顶栏 / 内容区 / toast / dialog 容器）
├── css/app.css               # 全部样式：两套主题变量 + 组件 + 页面
├── js/
│   ├── app.js                # 启动、hash 路由、主题、语言、设备状态栏、页面懒加载
│   ├── api.js                # REST + WebSocket 封装（live / mock 双模式、事件总线、自动重连）
│   ├── mock.js               # 内置 mock 后端：内存/本地持久化设备状态、20fps 电平、上传进度、TFT 压缩模拟
│   ├── i18n.js               # 界面外壳字典（导航/标题/通用词，zh + en）
│   ├── i18n-dom.js           # 页面级英文翻译层（中文为源，按字典/正则翻译 DOM 与动态节点）
│   ├── i18n-en-dom.js        # 页面文案中 → 英字典 + 动态文案正则（新增文案加这里）
│   ├── util.js               # DOM/格式化/存储/下载、DOM code ↔ HID usage ↔ 槽位映射
│   ├── icons.js              # 全部内联 SVG 图标（24×24 stroke）
│   ├── data/                 # 静态数据模块（由 docs/ 一次性生成后提交，运行时不解析 JSON）
│   │   ├── keyboard.js       # 官方 87 键几何（行/x/宽/槽位/键名/HID/无灯槽位）
│   │   ├── actions.js        # 动作目录 107 键 / 17 媒体 / 7 鼠标 / 292 FUNC / MK87 官方 28 FN + 出厂默认键位
│   │   └── lighting.js       # 19+1 灯效模式元数据（名称/参数/方向默认值）
│   ├── components/
│   │   ├── keyboard.js       # 87 键键盘渲染（绝对定位，支持上色/选中/按下/计数/角标/置灰）
│   │   ├── colorpicker.js    # 取色器（SV 面板 + 色相 + HEX/RGB + 常用/最近色板）
│   │   ├── dialog.js         # Promise 风格对话框（确认/提示/输入）
│   │   ├── toast.js          # 右上角浮层提示
│   │   └── widgets.js        # 滑块 / 分段控件 / 1-6 等级 / 进度条 / 标签页 / 统计卡等
│   └── pages/                # 11 个页面，均 export default { id, mount(root, ctx) → cleanup }
│       ├── lighting.js       # 灯光效果：19 模式 + 参数 + 19 种本地预览动画
│       ├── perkey.js         # 逐键灯效：画笔/橡皮/填充/取色 + 拖拽上色 + 色板
│       ├── screen.js         # TFT 屏幕：convert 预览 + trim + 压缩上传（ETA/取消/恢复默认）
│       ├── macro.js          # 宏：100 槽 + 录制 + 动作编辑 + 预算 + 绑定按键
│       ├── keymap.js         # 改键：主层/FN + 动作选择器 + 4B 编码预览（2.4G FN 只读）
│       ├── music.js          # 音乐律动：双方案（官方方案=官方 v1 同款设置项：显示模式/背景模式/背景亮度/振幅，运行中热切换；当前方案=本工具参数+本地预览）
│       ├── wireless.js       # 无线：2.4G 状态/身份/休眠/通知日志
│       ├── keytest.js        # 按键测试：高亮 + 三态计数 + 事件日志 + 统计
│       ├── device.js         # 设备信息：固件/电量/能力矩阵/56B 游戏模式/raw 控制台
│       ├── backup.js         # 备份恢复：导出/导入/二次确认（兼容后端 keyMatrix 格式）
│       └── settings.js       # 设置：主题/语言/关于/演示控制
├── README.md
└── (无 mock fixture 目录：mock 数据全部在 js/mock.js 内)
```

**数据文件说明**：`js/data/*.js` 是从 `docs/keymap-tables.json`、`docs/lighting-modes.json`、
`docs/fn-layer-decode.json` 一次性生成并提交的静态 ES 模块（内容含官方 `className` 反推的几何）。
运行时**没有任何构建/解析步骤**；docs 更新后由维护者本地重新生成（几何规则：`1u = 15 单位`，
行宽 `275` 单位，`w-NN`/`ml-NN`/`mr-NN`/`flex-1`/`ml-auto` 按原子类换算，见 `js/data/keyboard.js` 头注释）。

---

## 3. mock 模式

- 开启：URL 加 `?mock=1`，或 `/api/status` 不可用时自动启用（顶栏与设置页会显示 `MOCK`）。
- 实现：`js/api.js` 在 mock 模式下把每个 REST 调用交给 `MockServer.handle()`；WebSocket 事件由
  `MockServer` 用定时器/任务模拟（`status` / `battery` / `progress` / `job` / `notification` /
  `music_level` / `toast`）。
- 覆盖接口：`design.md` §4 的全部路由 + 屏幕页新增的 `POST /api/tft/convert`、
  `POST /api/tft/upload_file`（mock 内用浏览器 `ImageDecoder` / `createImageBitmap` 真实解码，
  再模拟压缩统计与上传进度；GIF 需 Chrome/Edge 的 `ImageDecoder`）。
- 持久化：设备状态（灯效/键位/宏/逐键灯/无线/设置）写入 `localStorage["mk87.mock.state"]`，
  刷新不丢；设置页可「重置演示数据」。
- 演示控制：设置页可模拟断连/重连、切换 USB ↔ 2.4G（相关页面的能力位/提示会联动）。
- 调试参数（仅 mock）：`?shell=1` 模拟原生外壳（设置页显示「退出 MK87 Studio」按钮，`POST /api/quit` 返回 `{ok:true}`）；`?conflict=1` 模拟结构化冲突横幅（验证 `conflictItems` 的中/英渲染）。

mock 的返回形状与真实后端对齐（`/api/keymap` 数组、`actions` 用 `value`、`lighting.rgb`、
`gameMode` 扁平字段、`wireless.sleepOptions`、秒级通知时间戳等）；页面里的归一化逻辑也兼容
两种形状，便于 mock/真机切换。

---

## 4. 主题（浅色 / 深色）

- 一套 DOM + CSS 变量：`css/app.css` 顶部 `:root`（浅色 token）与 `[data-theme="dark"]`（深色 token）。
  `<html data-theme="light|dark">` 切换，**默认跟随系统** `prefers-color-scheme`，可手动固定。
- `index.html` 内联脚本在首屏前读取 `localStorage["mk87.theme"]`，避免闪白/闪黑。
- 切换入口：顶栏三段式（浅色/深色/跟随系统）、设置页主题卡片。
- 持久化：`localStorage["mk87.theme"]` + `PUT /api/settings { theme }`（服务端配置文件）。
- 新增主题色：在 `:root` 和 `[data-theme="dark"]` 里成对添加变量；组件只用 `var(--xxx)`。
  键盘键帽、光效发光另有 `--kb-*` 变量，保证键盘在浅色/深色下都有质感。

---

## 5. i18n（中文默认 / 英文预留）

中文是源语言：页面源码直接写中文。英文采用**两层**：

1. **外壳字典** `js/i18n.js`：导航、页面标题/副标题、按钮/状态等通用键（`t('nav.lighting')`），
   `zh` / `en` 两份对象；`I18n.setLang()` 触发整页重挂载。
2. **页面翻译层** `js/i18n-dom.js` + `js/i18n-en-dom.js`：切英文时遍历 DOM 文本节点与
   `placeholder/title/aria-label`，按「整段中文原文」查 `EN_TEXT`，或用 `EN_PATTERNS` 正则处理
   带数字/插值的动态文案；`MutationObserver` 持续翻译之后插入的节点（toast / 日志 / 计数等）。
   切回中文时页面重挂载恢复原文。

**加一条英文翻译**：在 `js/i18n-en-dom.js` 的 `EN_TEXT` 里加 `"中文原文": "English"`；
动态文案（如 `已上传 3 帧`）在 `EN_PATTERNS` 加 `[/^已上传 (\d+) 帧$/, 'Uploaded $1 frames']`。
键必须与渲染后的中文完全一致（含空格与全角标点）。

持久化：`localStorage["mk87.lang"]` + `PUT /api/settings { language }`。
当前覆盖率：11 页在英文模式下**无中文残留**（唯一保留的是语言选择器里的原生名称「简体中文」）。

---

## 6. 页面 ↔ 主要接口

| 页面 | 主要接口 |
|---|---|
| 灯光效果 | `GET/PUT /api/lighting`、`GET /api/lighting/modes`、`GET /api/lighting/custom` |
| 逐键灯效 | `GET/PUT /api/lighting/custom`（`colors:{slot:[r,g,b]}, apply:true`） |
| TFT 屏幕 | `GET /api/tft`、`POST /api/tft/convert`、`POST /api/tft/upload_file`、`GET /api/tft/job`、`POST /api/tft/cancel`、`POST /api/tft/default` |
| 宏 | `GET/PUT /api/macros`、`DELETE /api/macros/{slot}`、`GET/PUT /api/keymap`（绑定） |
| 改键 | `GET /api/keymap`、`GET /api/keymap/layout`、`GET /api/keymap/actions`、`PUT /api/keymap/{normal,fn}`、`POST /api/keymap/restore` |
| 音乐律动 | `GET /api/music/devices`、`POST /api/music/start`、`POST /api/music/stop`、`GET /api/music/status` + WS `music_level` |
| 无线 | `GET/PUT /api/wireless` + WS `notification` |
| 按键测试 | `POST /api/keytest/start`、`POST /api/keytest/stop`、`GET /api/keytest/status` + WS `keyevent`（mock 下用浏览器 keydown/keyup） |
| 设备信息 | `GET /api/device/info`、`GET/PUT /api/device/game-mode`、`POST /api/device/raw`、`POST /api/device/time-sync`、`POST /api/device/factory-reset`、`POST /api/device/scan` |
| 备份恢复 | `GET /api/backup`、`POST /api/backup/restore { backup, confirm:true }` |
| 设置 | `GET/PUT /api/settings`（theme / language 等） |

全局：`GET /api/status` 低频轮询兜底 + WebSocket `/ws`（`status/battery/notification/progress/job/keyevent/music_level/toast`）。

---

## 7. 键盘组件与几何

- 官方 `docs/keymap-tables.json → mk87KeyboardConfig.keyListRaw` 给出 6 行 87 键与 UnoCSS 原子类；
  前端按 `1u = 15 单位`、行宽 `275` 单位（≈18.33u）反推绝对坐标：
  `w-NN`/`ml-NN`/`mr-NN` 按单位、`flex-1` 吃掉剩余空间、`ml-auto`/`mr-auto` 平分剩余间隙；
  6 行实测与标准 TKL 完全吻合（16/17/17/13/13/11）。
- 灯位：可改键 87 槽；**可点亮 84 键**（槽 99/100/102 = Print/Scroll/Pause 被小屏占用，无 LED，置灰）；
  槽 97/98 有 LED 通道但真机不可见（不在键盘图上）；Fn(85) 的 LED 是充电指示灯。
- 组件 API（`js/components/keyboard.js`）：`setColor/applyColorFrame/clearColors`、
  `setSelected/clearSelected`、`setPressed/clearPressed`、`setUsed(slot,count)`、
  `setBadge/clearBadges`、`setDisabled`、`refreshSize`、`destroy`。
  行内样式着色，20fps 逐键动画不触发布局重排。

---

## 8. 自测建议（无浏览器自动化时）

1. `python -m http.server 8123 --directory driver/web` → 打开 `http://127.0.0.1:8123/?mock=1`。
2. 逐页检查：切换主题（浅/深/跟随系统）、切换语言（中/英，整页应即时变化且无中文残留）。
3. 交互：灯光选模式/改色/亮度（mock 写入 localStorage）；逐键拖拽上色后「应用」；
   改键点键→选动作→应用 → 刷新后仍在；宏录制/保存；屏幕拖入图片 → 自动转换 → 上传进度到 100%；
   音乐开始/停止；无线切换休眠；按键测试按键高亮与计数；设备 raw 控制台发只读命令；
   备份导出/导入摘要与二次确认。
4. 浏览器控制台不应出现 error / 404。需要 `color-mix()`（Chrome 111+ / Edge 111+ / Firefox 113+ / Safari 16.2+）；
   mock 的 GIF 解码需要 `ImageDecoder`（Chrome / Edge）。
5. 真实后端联调：打开 `http://127.0.0.1:8477/`，顶栏不应出现 `MOCK`；2.4G 连接时
   屏幕/音乐页应显示「仅 USB 支持」，改键页 FN 层应提示只读（固件 2.4G 下 FN 回读返回普通层）。

---

## 9. 与契约的偏差 / 已知假设

1. `/api/device/raw` 返回按 `{cmd, response:"hex", length}` 与 `{response:"hex"|null}` 两种都兼容读取。
2. 宏动作发送 `{delay, usage, press, type:"keyboard"|"mouse"}`；改键绑定宏发送
   `{type:"macro", slot, mask, count}`（兼容 `repeat` 别名）；鼠标动作发送 `{type:"mouse", param1, value}`。
3. 「禁用按键」无官方编码，前端按 spec-keymap.md §1.3 预览 `02 00 6F 00`（HID 0x6F ⊠），真机未验证。
4. `/api/keymap/fn` 的键为槽位号；2.4G 下后端返回 `fnReliable:false` 时 FN 层只读并提示改用 USB。
5. `/api/keymap/actions` 的键盘/媒体项使用 `value` 字段、FUNC 使用 `value` 作为 id；前端已归一化。
6. `/api/tft` 返回 `byteOrder: 0|1`（数字）而非字符串；`fitModes/temporalModes/resampleModes/secondsPerPacket`
   缺失时使用默认值。
7. 屏幕页不再由前端转 RGB565：统一走 `/api/tft/convert` 预览 + `/api/tft/upload_file` 上传
   （避免两套压缩逻辑）；导出帧仅导出后端返回的 dataURL JSON。
8. 备份页兼容两种格式：真实后端 `format:"mk87-backup"`（`keyMatrix/fnMatrix/customLedData` hex）
   与本前端 mock 的对象格式。
9. `/api/keytest/status` 的 `events` 在真实后端是计数，前端优先读 `recent` 数组，mock 下用浏览器事件模拟。
10. 音乐风格来自 `GET /api/music/status.styles`（当前后端提供 spectrum/rainbow/pulse/ripple/firefly）；
    2.4G 下 `supported:false` 时禁用开始按钮并显示原因。
