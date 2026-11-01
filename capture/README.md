# AJAZZ 网页驱动 WebHID 抓包工具（零依赖）

用 Chrome DevTools Protocol 在**页面脚本执行之前**注入钩子，完整记录
<https://ajazz.driveall.cn> 这类网页驱动与 AJAZZ 键盘之间的全部 WebHID 通信。

- 目标设备：**VID `0x0C45`（3141）/ PID `0x8047`（32839）**，产品名 `AJAZZ KEYBOARD`
- 不需要 npm / Playwright / Puppeteer，只用 Node 内置模块（`fetch`、`WebSocket`、`fs`、`child_process`）
- 浏览器窗口**可见**（不是 headless）——因为 Chrome 的 HID 设备选择框必须由真实用户点击触发

---

## 1. 本机已验证的环境

| 项 | 值 |
|---|---|
| OS | Windows 10 LTSC |
| Node | `C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe`，**v24.21.0**（自带全局 `fetch` + `WebSocket`） |
| Chrome | `C:\Program Files\Google\Chrome Beta\Application\chrome.exe`，**158.0.8127.2** |
| 依赖 | **无**（不需要 `npm install`，不需要任何第三方包） |

---

## 2. 文件清单

| 文件 | 作用 |
|---|---|
| `hook.js` | 注入页面的钩子（document-start、主世界）。设备名适配 + 全通道拦截 + 记录推送 |
| `cdp.js` | 极简 CDP 客户端（内置 `fetch` 取 target，内置 `WebSocket` 连 `webSocketDebuggerUrl`），以及 `/json/*` 的辅助函数 |
| `run.js` | CLI 主程序：起 Chrome → 注入 → 导航 → 写 JSONL → 优雅退出 |
| `test/fakehid.html` | 本地验证页：纯前端伪造 `navigator.hid`，不需要真实键盘 |
| `test/verify.js` | 校验 JSONL 的断言脚本（33 项） |
| `run_test.ps1` | 一键端到端测试（跑 run.js + 跑 verify.js + 清理残留 Chrome） |
| `test/ajazz_test_log.jsonl` | 实测产出的日志样例（可直接打开看格式） |
| `test/run_test_stdout.txt` | 实测的完整控制台输出 |
| `README.md` | 本文件 |

---

## 3. 快速开始（真实键盘，半自动用法）

在 `C:\Users\ptfm\Documents\ajazz-re\capture\` 下执行：

```powershell
# 建议先 --keep 保留 profile，下次就不用重新授权（见第 6 节）
node run.js --url https://ajazz.driveall.cn --out ajazz_log.jsonl --keep
```

用完整路径时的等价写法：

```powershell
& 'C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe' `
  'C:\Users\ptfm\Documents\ajazz-re\capture\run.js' `
  --url https://ajazz.driveall.cn `
  --out C:\Users\ptfm\Documents\ajazz-re\capture\ajazz_log.jsonl `
  --keep
```

它会：

1. 用**独立临时 profile** 启动 Chrome Beta（不碰你日常用的 profile），窗口可见；
2. 导航前先注入钩子（`Page.addScriptToEvaluateOnNewDocument` + `runImmediately`）并注册
   `Runtime.addBinding('__ajazzFlush')`；
3. 导航到目标页，打印自检信息（`navigator.hid` 是否存在、`isSecureContext`、包装是否生效）；
4. 之后**你在页面上做的每一个操作都会被翻译成报文记录**，实时追加进 JSONL。

然后：**在网页上点「连接设备」→ 在弹出的 Chrome 原生窗口里选中
`AJAZZ KEYBOARD`（0x0C45 / 0x8047）→ 点「连接」**。剩下的交给工具，按 `Ctrl+C` 退出。

### 全部参数

```
node run.js [选项]

  --url <url>        要抓包的页面（默认 https://ajazz.driveall.cn）
  --out <file>       日志文件，JSONL，追加写（默认 ajazz_log.jsonl）
  --port <n>         Chrome 远程调试端口（默认 9333；被占用会自动 +1 找空位）
  --chrome <path>    Chrome 可执行文件（默认 Chrome Beta 的路径）
  --profile <dir>    指定 user-data-dir（默认在系统临时目录新建）
  --keep             退出时保留临时 profile —— ★ 里面存着 WebHID 授权，可复用
  --eval <js>        导航完成后在页面里执行一次这段 JS（返回值打印到 stdout）
  --eval-delay <ms>  执行 --eval 前等待的毫秒数（默认 0）
  --auto-exit <s>    运行 N 秒后自动优雅退出（默认 0 = 一直跑到 Ctrl+C）
  --quiet            不逐条打印抓到的记录
  -h, --help         帮助
```

示例：

```powershell
# 只探路：跑 10 秒，打印页面里 hook 的自检状态
node run.js --url https://ajazz.driveall.cn --out probe.jsonl --auto-exit 10 --eval-delay 3000 --eval "JSON.stringify(window.__ajazzState())"

# 用固定 profile，方便复用授权
node run.js --url https://ajazz.driveall.cn --out ajazz_log.jsonl --profile C:\Users\ptfm\Documents\ajazz-re\capture\profile-ajazz

# 抓完在页面里直接看内存里的记录条数
node run.js --url https://ajazz.driveall.cn --out ajazz_log.jsonl --eval "window.__ajazzLog.length"
```

---

## 4. 日志格式（JSONL，一行一个对象）

### 4.1 字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `ts` | number \| null | 页面内 `performance.now()`，毫秒，3 位小数。**浏览器侧的 meta 行为 `null`** |
| `epoch` | number | `Date.now()` 墙上时间，方便和抓图/抓包对齐 |
| `seq` | number \| null | 页面内自增序号（meta 行为 `null`） |
| `dir` | string | 通道方向，见 4.2 |
| `phase` | string | `call`（调用瞬间）/ `ok`（成功完成）/ `error`（失败） |
| `method` | string | 被拦截的方法名或事件名 |
| `reportId` | number \| null | HID report id（`0x00`…）。非报文类记录为 `null` |
| `data` | object \| null | `{ length, array:[...], hex:"55 10 00 …", ascii:"U....." }` |
| `device` | object \| null | `{ vendorId, productId, productName, opened }`（productName 已剥前缀） |
| `collections` | array \| null | `[{ usagePage, usage, type, children:[…] }]`，顶层集合 + 一层子集合 |
| `caller` | string \| null | `new Error().stack` 前 6 行（去掉了首行 `Error`）—— **用来定位是哪个 UI 操作触发的** |
| `error` | string \| null | 错误文本（`Name: message`） |
| `durationMs` | number \| null | 从调用到完成的耗时（`call` 行为 `null`） |
| `filters` | array \| null | 仅 `requestDevice`：页面传入的 `filters` / `exclusionFilters` |
| `devices` | array \| null | 仅 `getDevices`/`requestDevice` 的 `ok` 行：返回设备摘要 |
| `extra` | object \| null | 仅 `meta` 行：会话/自检信息 |

### 4.2 `dir` 的含义与「每个 API 产生几条记录」

| `dir` | 触发 | 记录数 |
|---|---|---|
| `out` | `HIDDevice.sendReport(id, data)` | 调用时 1 条（带完整报文）；失败再加 1 条 `error` |
| `out-feature` | `HIDDevice.sendFeatureReport(id, data)` | 同上 |
| `in-feature` | `HIDDevice.receiveFeatureReport(id)` | 调用时 1 条（`phase:call`，无 data）+ 完成时 1 条（`phase:ok`，`data` 是**读回来的字节**；失败则 `phase:error`） |
| `in` | `inputreport` 事件（键盘 → 主机） | 每个事件 1 条，在事件回调里**同步复制**字节（底层 buffer 会被复用） |
| `open` / `close` / `forget` | 设备生命周期 | 调用 1 条 + 完成 1 条（`ok`/`error`） |
| `hid` | `navigator.hid.getDevices()` / `requestDevice()` | 调用 1 条 + 完成 1 条（完成行带 `devices` 摘要） |
| `event` | `connect` / `disconnect`（同时监听 `deviceconnect` / `devicedisconnect` 兜底） | 每个事件 1 条 |
| `meta` | 钩子安装自检、宿主侧会话信息（`ts:null`） | 若干条 |

> 说明：WebHID 规范里的事件名其实是 `connect` / `disconnect`（`HIDConnectionEvent`）；
> 任务书里写的 `deviceconnect` / `devicedisconnect` 我们也一并监听了，作为兼容兜底。

### 4.3 真实样例行（来自实测日志）

注入成功 + 页面自己调用 `getDevices`：

```json
{"ts":29.3,"epoch":1793482391201,"seq":1,"dir":"meta","phase":"ok","method":"hook-installed","reportId":null,"data":null,"device":null,"collections":null,"caller":null,"error":null,"durationMs":null,"extra":{"hookVersion":"1.0.0","href":"file:///C:/Users/ptfm/Documents/ajazz-re/capture/test/fakehid.html","webhid":true,"secure":true,"userAgent":"Mozilla/5.0 … Chrome/158.0.0.0 Safari/537.36","hidCtor":"function"}}
{"ts":39.8,"seq":2,"dir":"hid","phase":"call","method":"getDevices","reportId":null,"data":null,"device":null,"collections":null,"caller":"at callerStack (<anonymous>:165:15)\nat EventTarget.getDevices (<anonymous>:649:22)\nat run (file:///…/test/fakehid.html:248:26)\nat file:///…/test/fakehid.html:331:3","error":null,"durationMs":null,"filters":null}
```

一条输出报文（`sendReport`）：

```json
{"seq":10,"dir":"out","phase":"call","method":"sendReport","reportId":0,
 "data":{"length":8,"array":[85,16,0,1,160,11,0,0],"hex":"55 10 00 01 a0 0b 00 00","ascii":"U......."},
 "device":{"vendorId":3141,"productId":32839,"productName":"AJAZZ KEYBOARD","opened":true},
 "collections":[{"usagePage":65383,"usage":1,"type":"application","children":[…]}],
 "caller":"at callerStack (<anonymous>:165:15)\n…","error":null,"durationMs":null}
```

一条输入报文（`inputreport`）：

```json
{"seq":14,"dir":"in","phase":"call","method":"inputreport","reportId":1,
 "data":{"length":7,"array":[85,1,4,202,254,186,190],"hex":"55 01 04 ca fe ba be"},
 "device":{…},"collections":[…],"caller":"…","error":null}
```

### 4.4 读日志的小技巧

```powershell
# 只看输出报文
Get-Content ajazz_log.jsonl | Select-String '"dir":"out' | Select-Object -First 20

# 统计各通道条数（用 node，无需 jq）
node -e "const fs=require('fs');const c={};for(const l of fs.readFileSync('ajazz_log.jsonl','utf8').split(/\r?\n/)){if(!l.trim())continue;const r=JSON.parse(l);const k=r.dir+'/'+r.method;c[k]=(c[k]||0)+1}console.log(c)"

# 重新拼出某个 reportId 的字节流
node -e "const fs=require('fs');for(const l of fs.readFileSync('ajazz_log.jsonl','utf8').split(/\r?\n/)){if(!l.trim())continue;const r=JSON.parse(l);if(r.dir==='out-feature'&&r.reportId===5)console.log(r.ts,r.data.hex)}"
```

---

## 5. 自测（不需要真实键盘）

```powershell
cd C:\Users\ptfm\Documents\ajazz-re\capture
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_test.ps1
```

流程：起 Chrome（可见窗口）→ 打开 `test/fakehid.html` → 该页用 `Object.defineProperty`
伪造 `navigator.hid`，并自动执行
`getDevices → requestDevice → open → sendReport → sendFeatureReport → receiveFeatureReport → inputreport → connect/disconnect → close`
→ `--eval` 打印页内断言 → 退出后 `test/verify.js` 校验落盘结果。

> `test/fakehid.html` 故意把伪造的产品名写成 `KEYBOARD AJAZZ KEYBOARD`（Linux hidraw 的味道），
> 用来验证前缀剥离；也故意**不**把伪造的 `HIDDevice` 类挂到 `window` 上（保持 class 的顶层词法绑定），
> 这样 `hook.js` 无法补 `HIDDevice.prototype`，只能走「实例级包装」这条更难的路径。
> 最难的路都能过，真实 Chrome 里原型级 + 实例级双保险自然更稳。

### 5.1 实测结果（本机 PowerShell 5.1 + Chrome Beta 158.0.8127.2）

页面内断言 **23/23 全通过**（`window.__TEST_RESULT`）：

```
[--eval] 结果:
{"ok":true,"pass":23,"total":23,"assertions":[
 {"name":"navigator.hid 存在","ok":true,"detail":"yes"},
 {"name":"navigator.hid.getDevices 不是原生实现（已被 hook 包装）","ok":true,
  "detail":"function () { /*__ajazz_hook__*/ …"},
 {"name":"productName 的 \"KEYBOARD \" 前缀已被剥离","ok":true,
  "detail":"raw=KEYBOARD AJAZZ KEYBOARD / seen=AJAZZ KEYBOARD"},
 {"name":"sendReport 报文到达设备","ok":true,"detail":"85 16 0 1 160 11 0 0"},
 …
 ],"hookState":{"version":"1.0.0","hidWrapped":true,"devicesPatched":1,"pending":0,"errors":[]}}
```

控制台实时打印（关键片段）：

```
[+] 钩子已注入（31744 字节，主世界，document-start）
[*] 导航到 file:///C:/Users/ptfm/Documents/ajazz-re/capture/test/fakehid.html ...
[+] 页面钩子自检: webhid=true secure=true href=file:///…/test/fakehid.html
  0002 hid/call         getDevices
  0003 hid/ok           getDevices
  0004 hid/call         requestDevice
  0007 open/call        open                   [0x0c45:0x8047]
  0010 out/call         sendReport             [0x0c45:0x8047] id=0x00 len=8  55 10 00 01 a0 0b 00 00
  0011 out-feature/call sendFeatureReport      [0x0c45:0x8047] id=0x05 len=8  55 80 01 02 03 04 05 06
  0012 in-feature/call  receiveFeatureReport   [0x0c45:0x8047] id=0x05
  0013 in-feature/ok    receiveFeatureReport   [0x0c45:0x8047] id=0x05 len=7  55 05 04 de ad be ef
  0014 in/call          inputreport            [0x0c45:0x8047] id=0x01 len=7  55 01 04 ca fe ba be
  0015 event/call       connect                [0x0c45:0x8047]
  0016 event/call       disconnect             [0x0c45:0x8047]
  0017 close/call       close                  [0x0c45:0x8047]
[自检] 钩子已安装 = true  hid.getDevices 已包装 = true  requestDevice 已包装 = true
[自检] 已授权设备 1 个：VID=0x0c45 PID=0x8047 usagePage=0xff67 "AJAZZ KEYBOARD" opened=false
[*] 已关闭 Chrome（pid=7560，signal=SIGTERM）
```

JSONL 断言 **33/33 全通过**：

```
  PASS  日志非空  :: 25 行
  PASS  每行都是合法 JSON  :: 解析失败 0 行
  PASS  覆盖 dir=meta/open/out/out-feature/in-feature/in/hid/event  :: (8 项)
  PASS  sendReport reportId == 0  :: 0
  PASS  sendReport 字节序列正确  :: 55 10 00 01 a0 0b 00 00
  PASS  sendReport 记录了 collections（usagePage）  :: usagePage=0xff67
  PASS  sendReport 的 caller 能定位到测试页  :: at callerStack …
  PASS  设备记录里 productName 已剥离 "KEYBOARD " 前缀  :: "AJAZZ KEYBOARD"
  PASS  inputreport 字节序列正确  :: 55 01 04 ca fe ba be
  PASS  receiveFeatureReport 返回字节正确  :: 55 05 04 de ad be ef
  PASS  requestDevice 的 filters 被记录  :: {"filters":[{"vendorId":3141,"productId":32839,"usagePage":65383}]}
  PASS  没有任何 error 记录  :: ok
结果: 33 通过, 0 失败
测试通过 ✔
```

### 5.2 真实站点验证（只验证注入链路，未插键盘）

```powershell
node run.js --url https://ajazz.driveall.cn --out test\real_site_log.jsonl --port 9412 --auto-exit 12
```

```
[+] 已连接调试端口，浏览器: Chrome/158.0.8127.2
[+] 钩子已注入（31744 字节，主世界，document-start）
[+] 页面钩子自检: webhid=true secure=true href=https://ajazz.driveall.cn/
  0002 hid/call         getDevices        ← 这是**站点自己的代码**在扫描已授权设备
  0003 hid/ok           getDevices
[自检] 钩子已安装 = true  hid.getDevices 已包装 = true  requestDevice 已包装 = true
[自检] 已授权设备 0 个：
        (无 —— 这是正常的：首次必须在页面上真实点击"连接设备"，Chrome 会弹原生选择框)
```

`devicesPatched: 0` 是预期结果：全新 profile 里没有任何 WebHID 授权，
`getDevices()` 返回空数组，所以还没有设备可打补丁。点一次「连接设备」后就会有。

---

## 6. 关键操作细节：怎么让页面弹出 HID 选择框

1. **必须真实用户点击。** `navigator.hid.requestDevice()` 需要 transient user activation
   （临时用户激活）。CDP 的 `Runtime.evaluate({userGesture:true})` 虽然能骗过部分 API，
   **但弹不出 Chrome 的 HID 设备选择原生窗口**——那个窗口只认真实的鼠标/键盘事件。
   所以本工具刻意做成「**用户点一下、工具记全部**」的半自动形态。
2. 点击后 Chrome 弹出原生列表，选 `AJAZZ KEYBOARD`（`0x0C45` / `0x8047`），点「连接」。
   这个选择窗口是**浏览器进程**的窗口，走 CDP 也抓不到内容，只能由人来点。
3. 授权结果按 **(profile, origin)** 存进 Chrome 的权限数据库（`WebHID 权限`）。
   所以在**同一个 `user-data-dir` + 同一个来源**下，之后 `navigator.hid.getDevices()`
   **不需要任何手势**就能拿到已授权的设备对象，直接 `open()` 即可通信。
4. 这正是后续做**全自动化**的正确路径：

   ```powershell
   # 第 1 次：人工授权一次，profile 留着
   node run.js --url https://ajazz.driveall.cn --out seed.jsonl --profile .\profile-ajazz --keep

   # 以后：同一个 profile，页面自己 getDevices 就能免手势重连，全程无需人工
   node run.js --url https://ajazz.driveall.cn --out run.jsonl --profile .\profile-ajazz --auto-exit 40
   ```

   注意：`--keep` 只是「不删除默认临时 profile」，用 `--profile` 指定固定目录更省心
   （两者可同时用）。换域名/换 profile 都要重新授权一次。

---

## 7. 常见坑

### 7.1 键盘/鼠标的顶层集合会被 Chrome 屏蔽

WebHID 出于安全考虑，**不会**把「键盘/鼠标」这类顶层集合暴露给网页：
`usagePage 0x0001 + usage 0x0002/0x0006`（Mouse/Keyboard）的设备在
`requestDevice` 的列表里直接不出现。网页驱动真正用的是**厂商自定义集合**：

- 本站实测：`usagePage === 65383`（`0xFF67`）。
  这是从站点 bundle 里直接读到的判定条件
  （`n.collections.some(r => r.usagePage === 65383)`），本工具的实测日志也印证了它
  （`collections[0].usagePage=0xff67`）；
- `0xFF00` / `0xFF60` 是 QMK 等固件常见的另一个厂商集合页；
- 都不是 `0x0001`。

所以：如果「连接设备」列表里看不到键盘，先看工具抓到的 `collections[].usagePage`，
再对照网页驱动的过滤条件；不要以为是工具没注入。

### 7.2 WebHID 只在安全上下文可用

`https://`、`http://localhost`、`file://` 都算安全上下文；`http://` 的普通域名不行
（`navigator.hid` 是 `undefined`）。自检行会直接告诉你：

```
[自检] navigator.hid = 不存在（WebHID 不可用！）
[自检] isSecureContext = false
```

### 7.3 profile 决定授权是否还在

默认每次运行都新建临时 profile 并在退出时删除 → **每次都要重新点一次授权**。
要复用授权就加 `--keep` 或 `--profile <固定目录>`。

### 7.4 不要 headless

headless 没有真实的用户手势，也没有 HID 选择框，`requestDevice` 永远弹不出来。
本工具默认就是可见窗口，也不提供 `--headless` 开关。

### 7.5 Windows PowerShell 5.1 的两个坑（本工具已处理）

- **脚本编码**：PS 5.1 用 ANSI/GBK 解 `.ps1`，UTF-8 中文会把语法搞坏。
  `run_test.ps1` 已存成 **UTF-8 with BOM**。
- **native 参数不自动加引号**：变量里带空格的参数会被拆成多个 argv。
  `run_test.ps1` 里的 `--eval` 表达式刻意写成**不含空格**的
  `JSON.stringify(window.__TEST_RESULT)`。手工调用时，含空格的表达式请自行加引号
  或用 `pwsh`（PowerShell 7）执行。

### 7.6 端口 / 残留进程

- 默认端口 9333 被占用时，会自动往后找空位（命令行会打印实际端口）。
- 正常 `Ctrl+C` / `--auto-exit` 都会**只关闭自己启动的那个 Chrome PID**，
  并清理临时 profile。若被强杀（如 taskkill 掉 node），Chrome 可能残留，
  可以这样只清理「本工具拉起的」Chrome，不动你自己开的浏览器：

  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -like '*ajazz-cdp-profile*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  ```

### 7.7 为什么一定要「设备名适配」

站点代码用 `${device.vendorId}:${device.productId}:${device.productName}`
拼 key 去查配置表（我在 bundle 里查到表里确有 `3141:32839` → `AJAZZ KEYBOARD`）。
Linux 上 Chrome 读到的产品串可能带 `KEYBOARD ` 前缀，拼出来就是
`3141:32839:KEYBOARD AJAZZ KEYBOARD` → 查不到配置 → 页面报「不支持该设备」。
`hook.js` 把 `productName` 的前缀剥掉，Windows 上原样不动，没有副作用。

### 7.8 已知取舍（不是 bug）

- 钩子会挂 `then` 的 rejection handler 来记录错误，因此页面原本可能打印的
  `Unhandled promise rejection` 警告可能不再出现；**页面自己的 `try/catch` 完全不受影响**。
- `sendReport`/`sendFeatureReport` 只在「调用瞬间」记一条（报文完整），失败再补一条 error，
  成功不再重复记一条 —— 避免把日志量翻倍。
- 只抓当前 page target 的主世界。页面里的跨域 iframe、worker 不在范围内。
- 钩子对页面零侵入：所有包装都 `try/catch`，任何内部异常都不会冒泡到页面。

---

## 8. 从站点 bundle 得到的情报（实测，供后续逆向参考）

我在 `C:\Users\ptfm\Documents\ajazz-re\assets\` 下的站点产物里读到：

1. 驱动是 **Rust + wasm-bindgen**：`__wbg_sendFeatureReport_*` / `__wbg_receiveFeatureReport_*`
   直接转发到 `HIDDevice.sendFeatureReport` / `receiveFeatureReport`。
   → 所以**特性报文（feature report）才是主通道**，`inputreport` 主要用于协议回包监听。
2. 设备集合判定用 `usagePage === 65383`（`0xFF67`）。
3. 配置表里有 `{vendorId:3141, productId:32839, name:'AJAZZ KEYBOARD', connectType:'USB'}`，
   以及 2.4G dongle 的 `0xFEF9/0xFEFC/0xFEFE` 等 PID。
4. 设备匹配 key 是 `VID:PID:productName` 字符串拼接（见 7.7）。
5. 报文本身是 `0x55` 开头的自定义帧：`[0x55, cmd, lenOrType, addr_lo, addr_hi, …, data…]`，
   读回用 `FX()` 解析；超时约 50ms；高亮/灯效等走 `cmd` 区分。

这些都和本工具抓到的 `dir`/`method`/`reportId`/`data` 字段一一对应，
可以直接拿 JSONL 去做协议还原。

---

## 9. 排错清单

| 现象 | 检查 |
|---|---|
| 日志里没有 `hook-installed` | 看 stdout 是否报 `Page.addScriptToEvaluateOnNewDocument` 失败；确认 `hook.js` 与 `run.js` 同目录 |
| `[自检] navigator.hid = 不存在` | 不是 https / localhost / file；或用了过老的 Chrome（本机 158 没问题） |
| 页面列表里看不到键盘 | 见 7.1（键盘顶层集合被屏蔽），对照 `collections[].usagePage` |
| `devicesPatched: 0` 且 `devices: []` | 该 profile 还没授权，点一次「连接设备」 |
| 报文记录里 `reportId` 一直是 0 | 正常：很多键盘只用 report 0 |
| 想让页面在导航后自动做点事 | `--eval "<js>"`，配 `--eval-delay` |
| 日志为空文件 | 记录靠 `Runtime.bindingCalled`，确认没有别的调试客户端抢占了该 target |
