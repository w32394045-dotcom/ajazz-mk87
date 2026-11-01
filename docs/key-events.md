# MK87 按键事件 / 按键测试页 / 设备通知 —— 纯静态逆向

> 【**真机补充 2026-11-01**】直接读键盘 HID `\kbd` 集合（MI_00 / MI_01 COL03）**CreateFile 失败 err=5 ACCESS_DENIED**（Windows 键盘类保护）；**Windows RawInput 方案可用**：`RegisterRawInputDevices`(1/6 + 0x0C/1) + 隐藏窗口 WM_INPUT，实测拿到 `vkey/make/flags/msg`，且 `GetRawInputDeviceInfo` 能取到 `VID_0C45&PID_8047&MI_00` 设备路径（可过滤本键盘）。RawInput 只给 VKey+MakeCode，不给 HID usage；要 usage 级映射需自维护 VKey→usage 表（见 §4.3）。


> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

> **目标**：`assets/layout-classic-CMxiG14P.js`（3,335,710 字符）、`assets/keyTest-wnjgu2NS.js`（7,964 字符）、`assets/main-_p8CH46K.js`（2,040 字符）
> **方法**：只读静态分析。**本轮没有 open/read/write 任何 HID 设备**；凡真机结论都注明来自 `docs/deepdive-mk87.md` / `docs/protocol.md`。
> **偏移约定**：文中的 `@偏移` 是**字符偏移**（bundle 是单行压缩文件，没有有意义的行号），复核方式：
> `node scripts/ctx.js slice assets/layout-classic-CMxiG14P.js <off-300> <off+600>`（美化输出）、
> `node scripts/ctx.js find assets/layout-classic-CMxiG14P.js '<正则>'`（只列位置）。
> **推测标注**：无法由代码直接证明的结论一律写【推断】。

---

## 0. 结论速览

| # | 问题 | 结论 | 关键证据 |
|---|---|---|---|
| 1 | `/key-test` 的按键状态从哪来 | **浏览器 DOM 事件**：`document.addEventListener('keydown'/'keyup')` + `KeyboardEvent.code`，**与 HID 完全无关** | `function u9()` @2375930；注册 @2380442 |
| 1a | 有没有解析 0x55 帧取按键 | **否**。全 bundle 只有 6 处 `[0]===85` 的判断，逐条列在 §3.1，没有一处是按键位图 | @1911782 / @1919131 / @1919591 / @1919996 / @1920389 / @1950126 |
| 1b | 有没有轮询 GET_KEY(18)/0x60(96)/0x68(104) | **否**。`GET_KEY` 只用于读键表；`GET_MAGNETIC_AXIS_KEY_STATUS(0x60)` 是**死枚举**（全 bundle 仅 1 处拼写）；`GET_MAGNETIC_AXIS_STATUS(0x68)` 只在 `frameVersion===1` 的磁轴校准循环里用 | @1923796 / @1915487 / @1922166 |
| 1c | 有没有直接读键盘 HID 使用页 | **否**。设备过滤器白名单是 `[0xFF68,0xFF80,0xFF60,0xFF00,0xFF01,0xFF5B]`，**不含 0x0001** | @1840243 |
| 2 | 0xFA 的 type 取值 | bundle 内**只有 type=6**（TFT 系统信息页）；`帧[3]===1` = 进入该页（开始推 CPU/GPU/天气），`0` = 离开 | 监听器 XZ @1949962、唯一调用点 P() @1838541 |
| 3 | 其它主动上报 | `55 FC 04/05/06`（2.4G 断开/重置/休眠）、`A6 FF 01`（2.4G 唤醒，**不是 0x55 帧**）、`55 FB …`（磁轴模拟量） | §3 |
| 4 | MK87 能否用厂商协议拿按键事件 | **不能**。厂商通道里根本没有按键事件；网页驱动自己也是靠 DOM 事件 | §4.1 |

---

## 1. 问题 1：`/key-test` 页面怎么拿到按键状态

### 1.1 页面与路由

```js
// 路由表（@1843410 附近，14 条路由之一）
{ path:`key-test`, name:`keyTest`, layout:`empty` }

// 免设备白名单（@1842256）
UY=[`/`,`/key-test`]        // 守卫 GY() 里：if(UY.includes(e.path)){ n(); return }  —— 不要求已连接设备
```

- `/key-test` 是 **`layout:'empty'`**：没有侧边栏、不依赖任何机型配置（`routesName` 里没有 `key-test`，见 `docs/device_config_32839.json`）。
- 页面 chunk `keyTest-wnjgu2NS.js` 只是薄壳：`__name:'keyTest'`，`setup(){ let {activeTab, keyList, keyCounts, keyLogs, …} = d() }`，
  其中 `d` 是 layout chunk 的导出 `m`：

```
import{…,m as d,…}from"./layout-classic-CMxiG14P.js"          // keyTest chunk 第 1 行
export{…, u9 as m, …}                                          // layout @3296577（导出表）
function u9(){ … }                                             // layout @2375930 ← 真正的逻辑
… }=u9();                                                      // layout @2384580（页面 setup 里调用）
```

### 1.2 组件实现（逐行证据）

虚拟键盘的**键表**是写死的 104 键 ANSI 布局（与机型无关）：

```js
c9=[[{code:`Escape`,label:`Esc`},{code:`F1`,…},…],   // @2371971 起，6 行
    … ];                                             // 共 104 个 {code,label,className}
l9=c9.flat().map(e=>e.code);                          // @2375902
```

> 实测统计（脚本）：`code:` 出现 **104** 次，键名与标准 `KeyboardEvent.code` 完全一致：
> `Escape,F1..F12,PrintScreen,ScrollLock,Pause,Backquote,Digit1..Digit0,Minus,Equal,Backspace,Insert,Home,PageUp,NumLock,NumpadDivide,…`

状态与计数器（全部是 Vue ref）：

```js
function u9(){
  let e=R(`keyboard`),                                        // activeTab
      t=Kt(Object.fromEntries(l9.map(e=>[e,`unpressed`]))),   // 每键状态 unpressed/pressed/used
      n=Kt(Object.fromEntries(l9.map(e=>[e,0]))),             // 每键按下次数
      r=R(0), i=R(0),                                          // 按下总次数 / 抬起总次数
      a=new Set,                                               // 当前按住的键
      o=R([]),                                                 // 按键日志（上限 100 条）
      …
```

**按键处理函数（全部基于 DOM `e.code`）** @2379xxx：

```js
function p(e){                                              // keydown
  let i=e.code;
  Object.prototype.hasOwnProperty.call(t,i)&&(                // 只处理键表里的键
    e.preventDefault(),
    a.has(i)||(a.add(i), n[i]++, r.value++, t[i]=`pressed`,
      o.value.unshift({time:u(),key:d(i),action:`press`}),
      o.value.length>100&&o.value.pop()))                     // 日志上限 100
}
function m(e){                                              // keyup
  let n=e.code;
  … a.has(n)&&(a.delete(n), i.value++, t[n]=`used`, … action:`release` …)
}
function N(){ a.forEach(e=>{ t[e]=`used` }), a.clear() }     // window blur：把所有按住标成 used，防"卡住"
```

**事件注册/注销** @2380442：

```js
Hi(()=>{                                                    // onMounted
  document.addEventListener(`keydown`,p);
  document.addEventListener(`keyup`,m);
  document.addEventListener(`mousedown`,O,!0);              // 鼠标 tab 用（mouseTestRef 区域内）
  document.addEventListener(`mouseup`,k,!0);
  document.addEventListener(`auxclick`,ee,!0);
  document.addEventListener(`wheel`,A,j);
  document.addEventListener(`contextmenu`,te,!0);
  window.addEventListener(`blur`,N);
})
```

**反证（本组件没有任何设备依赖）**：对 `u9` 的整个函数体（2375930–2384600）做字符串扫描，

```
navigator.hid  → absent
inputreport    → absent
HY(            → absent        （useWebHIDStore）
currentDevice  → absent
deviceStorage  → absent
keyboardConfig → absent
navigator      → absent
```

### 1.3 为什么"浏览器能收到键盘"——它根本没打开键盘接口

网页驱动用 WebHID 只打开**厂商自定义 collection**，过滤器白名单：

```js
function re(e){ let t=e.collections||[]; return t.length!==0 && t.some(e=>
  [65384,65408,65376,65280,65281,65307].includes(e.usagePage||0)) }   // @1840243
```

| 十进制 | 十六进制 | 用途 |
|---|---|---|
| 65384 | 0xFF68 | 主协议通道（MK87 的 MI_02） |
| 65408 | 0xFF80 | 部分机型 |
| 65376 | 0xFF60 | 部分机型 |
| 65280 | 0xFF00 | 部分机型 |
| 65281 | 0xFF01 | 部分机型 |
| 65307 | 0xFF5B | 部分机型 |

**没有 0x0001（通用桌面 / 键盘/鼠标）**，也没有任何地方对 keyboard collection 调用 `open()` / 监听 `inputreport`。
所以：键盘的标准 HID 报告仍然由操作系统消费 → 浏览器照常产生 `keydown/keyup` → 页面拿到 `e.code`。

> 【推断】MK87 的复合设备里当然有标准键盘接口（否则无法打字），但网页驱动从不碰它；这一点需要在真机上用
> `probe/hid_probe.py` 枚举确认 usagePage=0x01/usage=0x06 的接口与 `InReportByteLength`（本轮禁止动设备，未验证）。

### 1.4 四个候选答案的判定

| 候选 | 判定 | 理由 |
|---|---|---|
| a) 监听 `inputreport` 解析 0x55 帧 | **否** | §3.1 把 bundle 里所有 `[0]===85` 消费点全列了，没有任何按键位图解析；`u9` 内连 `inputreport` 字样都没有 |
| b) 轮询命令（GET_KEY 18 / 0x60 / 0x68） | **否** | `GET_KEY` 只在 `getKeyData`(@1923796) / `getSingleKeyData`(@1924465) 里读键表；`0x60` 是死枚举；`0x68` 只在 performance 页 `frameVersion===1` 的校准循环里 |
| c) 直接读键盘 HID 使用页 | **否** | 过滤器白名单无 0x0001；代码里没有任何 keyboard-collection 相关分支 |
| **d) 浏览器 DOM 键盘事件** | **✅ 是** | `document.addEventListener('keydown'/'keyup')` + `e.code`，见 §1.2 |

### 1.5 触发频率 / 上限 / 行为

- **没有轮询**：纯事件驱动，按一次算一次。
- 去重：`a`（Set）保证"按住不放"只记一次 press（auto-repeat 的重复 keydown 被 `a.has(i)` 挡掉）；
  抬起后状态从 `pressed` 变 `used`（页面用不同颜色区分"激活中/按过后/未按过"）。
- 计数：每键按下次数无上限；日志列表 100 条封顶（`o.value.length>100&&o.value.pop()`）。
- 失焦兜底：`window blur` 时把所有仍按住的键标成 `used` 并清空 Set。
- 与设备无关：任何键盘（包括笔记本自带键盘）都能点亮这张虚拟键盘——它测的是"浏览器收到的按键"，不是"键盘发来的报文"。

### 1.6 普通机械键盘（MK87）vs 磁轴机型

| 能力 | 普通机械（MK87） | 磁轴机型 | 走哪条分支 |
|---|---|---|---|
| `/key-test` 页面（按下/抬起/计数/日志） | ✅ 有（104 键） | ✅ 有（同一套 104 键） | **DOM 事件**，两者完全相同 |
| 按键行程/RT 实时曲线 | ❌ 无 | ✅ `performance` 页的"模拟测试" | `SET_SIMULATION_TEST_ON(102)` + `55 FB` 推送（frameVersion=0）；或 `SET_CALIBRATION_ON_V2(105)` + 轮询 `GET_MAGNETIC_AXIS_STATUS(104)`（frameVersion=1） |
| 页面路由 | `routesName = [customKeys, lighting, macro, tft, settings]`，**没有 performance/trigger** | `routesName` 含 `performance` | 路由守卫 `GY()` 按 `routesName` 拦截 |

- MK87 的 `performanceConfig` 在 `docs/device_config_32839.json` 里**不存在**，`deviceInfo.rtPrecision=0`、`axisInfo=0`（`docs/protocol.md` §4），
  所以磁轴那套 UI/协议分支在 MK87 上永远不会执行。
- 关键点：**磁轴的实时行程也不是 `/key-test` 页**，而是 `performance` 页里的"测试行程"开关（`handleChangeTestTrip` @2490310）。
  `/key-test` 自始至终只有 DOM 一条路径。

---

## 2. 问题 2：设备通知 `0xFA`

### 2.1 帧格式（扁平结构，不是 8 字节大包头）

上报帧与"请求-响应"帧**不是同一种头**，这是最容易踩的坑：

```
请求-响应（设备回包）:  55 <cmd> <lenOrType> <addrLo> <addrHi> <hdr5> <last> <hdr7>  data@8
主动上报（0xFA/0xFC/0xFB）: 55 <cmd> <p0> <p1> <p2> ...        ← payload 直接从第 3 字节开始
唤醒帧（唯一例外）:      A6 FF 01
```

证据：所有 push 监听器都是直接 `arr[2]`（类型/键号）、`arr[3..]`（payload），而 `FX()/@1911775`（响应帧解析器）用的是 `slice(8)`：

```js
XZ=(e,t,n,r)=>{ … let t=e=>{ let {data:t}=e, i=new Uint8Array(t.buffer);
  if(i.length>=4 && i[0]===85 && i[1]===HX.GET_DEVICE_NOTIFY && i[2]===n && r&&typeof r==`function`) … r(i) …
```

### 2.2 type 常量全表

| cmd | type | 语义 | 处理者 | 依据 |
|---|---|---|---|---|
| **0xFA** | **6** | TFT 屏幕是否停在「系统信息页」；`帧[3]===1` → 开始推送，`0` → 停止 | `startDeviceStateListener`（local `XZ` @1949962） | 唯一调用点 P() @1838541 |
| 0xFA | 其它 | **bundle 内不存在**（枚举里没有常量、没有调用者）；监听器是通用 API，`i[2]===type` 由调用方给 | — | `XZ` 全 bundle 仅 2 处：定义 @1949962、模块导出表 @1914233 |

> 也就是说：**"0xFA 有哪些 type"这个问题，在本 bundle 里只有一个答案：6。** 其它 type 只能靠真机盲扫或厂商文档。

### 2.3 唯一调用点与三层门控

```js
// store（useWebHID）里 P() @1838541
async function P(e){
  x.value&&=(x.value(),null);
  let t=null,
      n=await c(`startDeviceStateListener`, e, 6, e=>{      // ← type 硬编码 6
        let n=e[3]===1;                                     // ← 帧第 4 字节
        n!==t&&(t=n, n?u():d())                             // u=startGetTftInfo, d=stopGetTftInfo
      });
  …
}
// u/d 的来源 @1832262 附近：
let {sendReport:c, sendReportFromDevice:l}=rY(), {startGetTftInfo:u, stopGetTftInfo:d}=RY();
```

调用条件（4 处完全相同的门控，缺一不可）：

| 层 | 条件 | 位置 |
|---|---|---|
| 1 | OS 是 Windows（`VV()` 判 UA；只影响 8s 轮询是否启动） | `RY()` @1803404 |
| 2 | `keyboardConfig.tftConfig.isShowTftInfo === true` | @1835029 / @1835427 / @1840019 / @1841818 |
| 3 | 设备主动发 `55 FA 06 01` | 运行时 |

**MK87 的第 2 层不成立**：`docs/device_config_32839.json` 的 `tftConfig = {name:"AK980_PRO", localforageKey:"w240h135", width:240, height:135}`，**没有 `isShowTftInfo`** → 网页驱动永远不会注册这个监听。

### 2.4 `data[3]` 到底是什么

官方回调拿到的是**整帧** `Uint8Array`（含 `0x55`），所以 `e[3]`：

```
帧:   [0]=55  [1]=FA  [2]=06  [3]=0/1  [4..]=…
       ↑      ↑      ↑      ↑
      hdr    cmd   type   systemInfoPage
                        = payload[0]（若按"payload=data.slice(3)"理解）
```

`1` → `startGetTftInfo()`：

- 立即推一次，然后 **每 8000ms**（`PY=8e3`）推一次 `setTftScreenInfo`；
- 数据源：CPU/GPU 占用与温度来自本机 `http://127.0.0.1:9191/api/hardware/info`；气温/天气码/湿度来自 OpenWeatherMap；
- 报文：`SET_TEMPORARY_COMMAND_DATA(0x34)`，payload 24 字节 `[6]=0x5A,[12]=cpuUsage,[13]=cpuTemp,[14]=gpuUsage,[15]=gpuTemp,[16]=当前气温,[17]=最高,[18]=最低,[19]=天气码(0–23),[20]=湿度`（`YZ` @1948903，详见 `docs/tft-page.md` §3.4）。

`0` → `stopGetTftInfo()`：停掉轮询、复位天气缓存标志。

> 【推断】`1` 的物理含义是"屏幕当前停在系统信息页（可推送）"。bundle 里没有其它注释或反例，这个语义是从"进入才推、离开就停"的行为反推的。

---

## 3. 问题 3：其它主动上报

### 3.1 全量枚举方法（可复现）

主动上报的唯一可靠特征是**监听器自己比较帧头字节**。对 bundle 做字面扫描：

```powershell
node scripts/ctx.js find assets\layout-classic-CMxiG14P.js '\[0\]===85'     # 6 处
node scripts/ctx.js find assets\layout-classic-CMxiG14P.js '\[0\]===166'    # 1 处（0xA6 唤醒）
node scripts/ctx.js find assets\layout-classic-CMxiG14P.js 'inputreport'    # 16 处（7 个常驻监听器 + IX 的临时监听 + 2 处音乐页死代码）
```

6 处 `[0]===85` 对应全部 0x55 消费点：

| 偏移 | 函数 | 匹配 | 语义 |
|---|---|---|---|
| @1911782 | `FX()` | 任意 `55 cmd` | **响应帧解析器**（`55 cmd lenOrType addr … data@8`），供 `IX()` 等请求用 |
| @1919131 | `JX()` | `55 FB` | 磁轴按键模拟量（§3.4） |
| @1919591 | `XX()` `start24GDisconnectListener` | `55 FC 04` | 2.4G 断开 |
| @1919996 | `ZX()` `startResetListener` | `55 FC 05` | 设备重置 |
| @1920389 | `QX()` `start24GSleepListener` | `55 FC 06` | 2.4G 休眠 |
| @1950126 | `XZ()` `startDeviceStateListener` | `55 FA <type>` | 设备状态通知（§2） |

> 结论：**没有任何一处解析按键位图/按键事件**。如果设备真的会推按键，bundle 里必然有第 7 个消费点——没有。

### 3.2 `0xFC`（252）2.4G 断开 / 重置 / 休眠

```js
XX=(e,t,n)=>{ … if(r.length>=3 && r[0]===85 && r[1]===HX.GET_24G_DISCONNECT_NOTIFY && r[2]===4) n() … }   // @1919506
ZX=(e,t,n)=>{ …                                             r[2]===5 … }                                   // @1919911
QX=(e,t,n)=>{ …                                             r[2]===6 … }                                   // @1920304
```

| type | 语义 | 注册条件 | 主机反应（store 里的回调） |
|---|---|---|---|
| 4 | 2.4G 链路断开 | 仅 `connectType==='2.4G'` | `j()` @1837352：清监听、`isConnected=false`、清 `historyConnect`，1.5s 后 `location.replace('/')` + 弹 `断开连接了！！！`（i18n `link_state`） |
| 5 | 设备重置 | **所有设备**（连接成功即注册，`M()` @1837647） | 若 `routesName` 含 `performance` 先清 `magneticAxisRTConfig`，然后 `location.reload()` |
| 6 | 2.4G 休眠 | 仅 `connectType==='2.4G'` | `is24GSleeping=true` → **App 根组件全屏遮罩**：`fixed inset-0 z-9999 auto-bg-600:80` + 文案「设备已进入休眠，请按任意按键唤醒」（`main-_p8CH46K.js` @1238，i18n `sleeping-tips`） |

### 3.3 `0xA6 0xFF 0x01` —— 2.4G 唤醒（唯一的非 0x55 上报）

```js
$X=async(e,t,n)=>{ … if(r.length>=3 && r[0]===166 && r[1]===255 && r[2]===1) n() … }   // @1920705
```

- `166=0xA6`、`255=0xFF`、`1`：三个字节全固定，后面有没有 payload 代码不关心。
- 注册条件：仅 `connectType==='2.4G'`。
- 反应：`console.log('唤醒了')` + `is24GSleeping=false`（遮罩消失）。
- 【推断】这是 dongle 侧的唤醒通知；USB 直连时是否也会发未验证。

### 3.4 `0xFB`（251）磁轴按键模拟量（校准 / 模拟测试共用）

解析器 `JX` @1919110（逐字节抄录）：

```js
JX = e => e.length>=13 && e[0]===85 && e[1]===HX.GET_MAGNETIC_AXIS_CALIBRATION_DATA ? {
  keyValue:          e[2],
  calibrationStatus: e[3],
  maxValue:          e[4] | e[5]<<8,
  minValue:         (e[6] | e[7]<<8) & 32767,     // 最高位被清掉
  currentValue:      e[8] | e[9]<<8,
  keyStroke:        e[10] | e[11]<<8,
  maxStroke:        e[12] | e[13]<<8
} : null
```

帧 = **14 字节扁平结构**（`55 FB` + 12 字节）：
`keyValue(1) | status(1) | max(2) | min(2) | current(2) | keyStroke(2) | maxStroke(2)`，全部小端。

- **开启方式（必须先发命令）**：
  - `SET_CALIBRATION_ON(0x64=100)` → 帧 `AA 64 00 00 00 …`，等 ACK `55 64 …`（1000ms）后挂 `0xFB` 监听（`eZ` @1921087）；
  - 或 `SET_SIMULATION_TEST_ON(0x66=102)` → `AA 66 …`，等 ACK 后挂监听（`aZ` @1922872）；
  - 关闭：`SET_CALIBRATION_OFF(101)` / `SET_SIMULATION_TEST_OFF(103)`。
- **frameVersion=1 的机型不用 0xFB**：走 `SET_CALIBRATION_ON_V2(105)` + 轮询 `getMagneticAxisStatus`（cmd 104，`iZ` @1922166）：
  请求 payload = N×8 字节（每 8 字节第 1 字节是键号），`addrStart = 块号×(reportCount-8)`、`checkAddr:true`、`isNeedLastPacketFlag` 控制末包；
  响应每键 8 字节：`[0]=calibrationStatus, [1..2]=adcValue(LE16), [3..4]=currentStroke(LE16)`。
- 消费方：`performance` 页（磁轴校准/行程测试）。**MK87 没有这个页面 → 这条链路与 MK87 无关。**
  - v0 分支（`frameVersion!==1`）：`startCalibration` @2488437 + `0xFB` 推送回调（`calibrationStatus===1` → 该键标绿）；
  - v1 分支（`frameVersion===1`）：`startCalibrationV2` @2487512 + 轮询 `getMagneticAxisStatus`（cmd 104）；
  - 行程测试：`startSimulationTest` @2490310（`handleChangeTestTrip`）。

### 3.5 汇总表（cmd → 语义 → 处理）

| cmd | 方向 | 触发条件 | 语义 | bundle 处理 | MK87 相关？ |
|---|---|---|---|---|---|
| 0xFA/6 | 设备→主机 | 屏幕切到/离开系统信息页 | TFT 信息页可见性 | 起/停 8s 推送（`setTftScreenInfo`） | ❌ 不注册（无 `isShowTftInfo`） |
| 0xFC/4 | 设备→主机 | 2.4G 断链 | 断开 | 清设备、跳首页、弹提示 | ❌（USB 直连不注册） |
| 0xFC/5 | 设备→主机 | 设备复位 | 重置 | `location.reload()` | ✅ **会注册** |
| 0xFC/6 | 设备→主机 | 2.4G 休眠 | 休眠 | 全屏"已休眠"遮罩 | ❌（非 2.4G） |
| 0xA6 FF 01 | 设备→主机 | 2.4G 唤醒 | 唤醒 | 撤掉遮罩 | ❌（非 2.4G） |
| 0xFB | 设备→主机 | 已发 100/102 | 单键模拟量 | 校准/行程 UI | ❌（无磁轴） |
| 0x12 / 0x60 / 0x68 | 主机→设备 | 请求 | 键表 / 磁轴按键状态 / 磁轴状态 | 见 §1.4 | 0x12 ✅、0x60/0x68 ❌ |

### 3.6 没有的东西（同样是结论）

- **没有全局帧路由**：不存在"收到一帧 → 分发到各模块"的中心；每个监听器各自 `addEventListener('inputreport')` 各自过滤。
- **ACK 不算主动上报**：`IX()` 只按 `cmd`（可选 `addr`）匹配，匹配到就 `resolve`；匹配不到的帧被**静默丢弃**（没有日志、没有 fallback）。
- **没有按键事件、没有电量推送、没有 0x60 推送**。

---

## 4. 问题 4：自研驱动的事件解码器规格

### 4.1 先给结论

> **用厂商协议（0x55 帧）捕获 MK87 的按键事件：不可行。**
>
> 1. 协议里没有任何"按键位图/按键事件"上报（§3.1 已穷举 6 个消费点）；
> 2. 唯一可疑的 `GET_MAGNETIC_AXIS_KEY_STATUS(0x60)` 在 bundle 里**从未被发送**，也没有解析器（死枚举）；
> 3. `0xFB` 是磁轴模拟量、且需要先开校准/模拟测试；MK87 无磁轴；
> 4. 官方"按键测试页"自己都不用 HID，而是监听 DOM 键盘事件（§1）。
>
> 真机侧也印证了这一点：空闲 5 秒 0 条主动上报（`docs/deepdive-mk87.md` §3）。

### 4.2 仍然值得实现的上报解码器（0xFA/0xFC/0xFB/0xA6）

规格见 `docs/device-notifications.json`，参考实现 + 自检见 `scripts/keyevent_ref.js`（`decodeReport()` / `DeviceMonitor`）。

要点：

| 帧 | 头 | 关键字段 | 备注 |
|---|---|---|---|
| `55 FA <type> <p…>` | 扁平 | `type`(帧[2])、`payload`(帧[3..]) | type=6 时 `帧[3]` = 系统信息页 0/1 |
| `55 FC <type>` | 扁平 | `type` = 4/5/6 | 无 payload |
| `A6 FF 01` | 固定 3 字节 | — | 唤醒 |
| `55 FB …` | 扁平 12B | 见 §3.4 | 需先发 100/102 开启 |
| `55 <cmd> <len> <addr> …` | 8 字节头 | `addr`(帧[3..4] LE)、`data`(帧[8..]) | 请求响应，别和上面的 push 混用 |

**是否需要先"开启"上报？**

| 上报 | 需要开启命令吗 |
|---|---|
| 0xFA / 0xFC / 0xA6 | **不需要**（设备自己发；只要注册监听） |
| 0xFB | **需要**：`SET_CALIBRATION_ON(0x64)` 或 `SET_SIMULATION_TEST_ON(0x66)`；关闭用 101/103 |
| 0x68 轮询 | 需要先 `SET_CALIBRATION_ON_V2(0x69)`（frameVersion=1） |

**MK87 是否支持**：0xFA 网页端不监听（缺 `isShowTftInfo`），设备是否真会发**未验证**；0xFC/5 会注册且可能触发；0xFB 预期无数据。

### 4.3 想拿按键事件，只能走"标准键盘"这条路

官方页面的做法已经给出答案：**读操作系统解析后的键盘输入**。自研驱动可以照抄这个思路，三种实现（按推荐度）：

**方案 A：直接读标准 HID 键盘接口（推荐，跨平台）**

1. 枚举 MK87 的 HID 接口，找 `usagePage=0x01, usage=0x06`（Keyboard）的 collection（不是 0xFF68 那条）；
2. `CreateFile` + `HidD_GetPreparsedData`/`HidP_GetCaps` 取 `InputReportByteLength`；
3. 阻塞 `ReadFile` 循环（或 `WaitForSingleObject` + overlapped）；
4. 解析 8 字节 boot 报告：`[0]=修饰键位图(LCtrl..RGui)`、`[1]=保留`、`[2..7]=6 个 HID usage`（NKRO 机型可能是位图报告，需要按报告描述符解析）；
5. 与上一帧差集 → press/release 事件；
6. HID usage → 键名：见下表（该表与 `/key-test` 页的 104 键**一一对应**，已用脚本核对：104/104 全中）。

**方案 B：Windows RawInput（RIDEV_INPUTSINK）** — 拿到 `RAWKEYBOARD`（`MakeCode`/`VKey`/`Flags` 的 break 位），比 HID 更省事，但只能在 Windows 用。

**方案 C：低级键盘钩子（WH_KEYBOARD_LL）** — 最简单，但会被反作弊/安全软件盯上，且拿不到物理键位（只有 VK）。

> 注意：经用户改键（`SET_KEY`，pageType=13 的固件功能键、宏、组合键）之后，标准键盘报告里只会出现**映射后的 usage**，
> 拿不到"物理上是哪个键"。要物理键位只能靠固件上报——而固件没有这个上报（这就是本节的结论）。

**HID usage(page 0x07) → `KeyboardEvent.code` 对照表（与 `/key-test` 的 104 键完全一致）**

| | | | |
|---|---|---|---|
| `A` = 0x04 | `B` = 0x05 | `C` = 0x06 | `D` = 0x07 |
| `E` = 0x08 | `F` = 0x09 | `G` = 0x0A | `H` = 0x0B |
| `I` = 0x0C | `J` = 0x0D | `K` = 0x0E | `L` = 0x0F |
| `M` = 0x10 | `N` = 0x11 | `O` = 0x12 | `P` = 0x13 |
| `Q` = 0x14 | `R` = 0x15 | `S` = 0x16 | `T` = 0x17 |
| `U` = 0x18 | `V` = 0x19 | `W` = 0x1A | `X` = 0x1B |
| `Y` = 0x1C | `Z` = 0x1D | `Digit1` = 0x1E | `Digit2` = 0x1F |
| `Digit3` = 0x20 | `Digit4` = 0x21 | `Digit5` = 0x22 | `Digit6` = 0x23 |
| `Digit7` = 0x24 | `Digit8` = 0x25 | `Digit9` = 0x26 | `Digit0` = 0x27 |
| `Enter` = 0x28 | `Escape` = 0x29 | `Backspace` = 0x2A | `Tab` = 0x2B |
| `Space` = 0x2C | `Minus` = 0x2D | `Equal` = 0x2E | `BracketLeft` = 0x2F |
| `BracketRight` = 0x30 | `Backslash` = 0x31 | `Semicolon` = 0x33 | `Quote` = 0x34 |
| `Backquote` = 0x35 | `Comma` = 0x36 | `Period` = 0x37 | `Slash` = 0x38 |
| `CapsLock` = 0x39 | `F1` = 0x3A | `F2` = 0x3B | `F3` = 0x3C |
| `F4` = 0x3D | `F5` = 0x3E | `F6` = 0x3F | `F7` = 0x40 |
| `F8` = 0x41 | `F9` = 0x42 | `F10` = 0x43 | `F11` = 0x44 |
| `F12` = 0x45 | `PrintScreen` = 0x46 | `ScrollLock` = 0x47 | `Pause` = 0x48 |
| `Insert` = 0x49 | `Home` = 0x4A | `PageUp` = 0x4B | `Delete` = 0x4C |
| `End` = 0x4D | `PageDown` = 0x4E | `ArrowRight` = 0x4F | `ArrowLeft` = 0x50 |
| `ArrowDown` = 0x51 | `ArrowUp` = 0x52 | `NumLock` = 0x53 | `NumpadDivide` = 0x54 |
| `NumpadMultiply` = 0x55 | `NumpadSubtract` = 0x56 | `NumpadAdd` = 0x57 | `NumpadEnter` = 0x58 |
| `Numpad1` = 0x59 | `Numpad2` = 0x5A | `Numpad3` = 0x5B | `Numpad4` = 0x5C |
| `Numpad5` = 0x5D | `Numpad6` = 0x5E | `Numpad7` = 0x5F | `Numpad8` = 0x60 |
| `Numpad9` = 0x61 | `Numpad0` = 0x62 | `NumpadDecimal` = 0x63 | `ContextMenu` = 0x65 |
| `ControlLeft` = 0xE0 | `ShiftLeft` = 0xE1 | `AltLeft` = 0xE2 | `MetaLeft` = 0xE3 |
| `ControlRight` = 0xE4 | `ShiftRight` = 0xE5 | `AltRight` = 0xE6 | `MetaRight` = 0xE7 |

> 缺的 `0x32/0x64` 等是 ISO/JIS 专用 usage，`/key-test` 的 ANSI 104 键里没有，属正常。

**推荐实现步骤（方案 A）**

1. `HidD_GetHidGuid` + `SetupDiEnumDeviceInterfaces` 枚举所有 HID；
2. 对每个接口 `HidD_GetAttributes` 过滤 VID/PID = `0x0C45/0x8047`；
3. `HidP_GetCaps` 找 `UsagePage==0x01 && Usage==0x06` 的那个接口（记录 `InputReportByteLength`，通常是 9 或 65）；
4. 打开后 `ReadFile` 死循环读 input report（**不要**用 WebHID 的 output report 打扰设备）；
5. 按报告描述符解析（Boot 键盘：`[1]`修饰键、`[3..8]`6 个 usage；NKRO：位图）；
6. 差分 → `press/release`，按上表映射成 `code`，就能复刻 `/key-test` 页的全部效果（含多键同时、计数、日志）。

---

## 5. 自检（`scripts/keyevent_ref.js`，真实输出）

> 下面是**实际运行**后做过去重/合并行的摘要（完整输出请直接跑 `node scripts/keyevent_ref.js`，与下列结论逐行一致）：

```
> node scripts/keyevent_ref.js

=== keyevent_ref.js 自检（构造帧） ===

PASS  55 FA 06 01 ...        → PUSH cmd=0xFA(GET_DEVICE_NOTIFY) type=6 → TFT 系统信息页 出现（开始 8s 推送）
PASS  55 FA 06 00            → TFT 系统信息页 离开（停止推送）
PASS  55 FA 07 01            → 未知 type（不崩，known=false）
PASS  55 FC 04               → 2.4G 断开
PASS  55 FC 05               → 设备重置
PASS  55 FC 06               → 2.4G 休眠
PASS  A6 FF 01               → 2.4G 唤醒
PASS  55 FB 10 01 34 12 00 00 20 00 05 00 03 00
                             → key=16 status=1 stroke=5 cur=32 max=0x1234 min=0
PASS  55 FB 03 02 E8 03 01 80 07 00 2A 00 64 00
                             → minValue 0x8001 &0x7FFF = 1
PASS  55 10 F9 00 00 00 01 00 40 00 00 0C
                             → RESP cmd=0x10 lenOrType=0xF9 addr=0 last=1 data=[40 00 00 0C]
PASS  55 60 02 00 00 00 01 00 FF FF
                             → 即使设备回 0x60 也只会被当成响应帧（bundle 无解析器）
PASS  AA 12 04 00            → 正确拒绝（发往设备方向的帧）

=== 状态机串测（2.4G 会话 + 系统信息页进出） ===
  55 FC 06     → sleep        state={"connected":true,"sleeping":true,"tftPush":false}
  A6 FF 01     → wake         state={"connected":true,"sleeping":false,"tftPush":false}
  55 FA 06 01  → tft on       state={…,"tftPush":true}   action=开始每 8000ms 推 setTftScreenInfo
  55 FA 06 00  → tft off      state={…,"tftPush":false}  action=停止推送
  55 FA 06 01  → tft on       再次进入
  55 FC 04     → disconnect   state={"connected":false,…}
PASS  状态机终态：connected=false tftPush 轨迹=true→false→true

=== 编解码互逆 ===
PASS  FA(6,01 02) / FC(5) / FB(key=64,stroke=120) / wake / resp(0x34,[1,2,3])

===== 结果：PASS 18  FAIL 0 =====     (exit code 0)
```

> 说明：以上为**构造帧**（`encodeFA/encodeFC/encodeFB/encodeResponse`），不是真机抓包；自检只验证"我的解码器与 bundle 里的解析逻辑一致"。

---

## 6. 未解问题（需要真机或更多 chunk 才能闭环）

1. **0xFA 其它 type**：bundle 里只有 6，没有第二个 type 常量/调用点。若设备还有别的通知类型，只能真机盲扫。
2. **MK87 会不会发 `55 FA 06 xx`**：网页端不监听（无 `isShowTftInfo`），所以无法从代码判断；真机测法：开 `inputreport` 监听 → 在键盘屏幕上切到/切走"系统信息"页 → 看有没有 `55 FA 06 01/00`。
3. **`GET_MAGNETIC_AXIS_KEY_STATUS(0x60)` 的请求/响应格式**：bundle 未实现，只能真机试探（发 `AA 60 00 …` 看回包；MK87 可能直接超时/忽略）。
4. **MK87 的 `SET_CALIBRATION_ON(0x64)` 行为**：预期回 ACK 但无 `0xFB` 数据流，未验证。
5. **`A6 FF 01` 是 dongle 还是键盘发的**：bundle 不区分；USB 直连是否也会发未知。
6. **标准键盘接口的细节**：MK87 的键盘 collection 是 Boot 8 字节还是 NKRO 位图、`InputReportByteLength` 多少，需要 `probe/hid_probe*.py` 在真机上枚举（本轮禁止动设备）。

---

## 7. 本轮产出

| 文件 | 内容 |
|---|---|
| `docs/key-events.md` | 本文件：结论 + 证据偏移 + 自研驱动建议 |
| `docs/device-notifications.json` | 0xFA/0xFB/0xFC/0xA6 通知帧的 cmd/type/payload 语义表（含门控、UI 反应、MK87 支持情况、未解问题） |
| `scripts/keyevent_ref.js` | 可 `node` 运行的解码器（`decodeReport` / `DeviceMonitor` / 编码器）+ 18 项自检，`node scripts/keyevent_ref.js` 即跑 |
| `scripts/ctx.js` | 本次新增的取证小工具：`grep/slice/find`，用于按偏移复核本文所有片段（未改动任何既有文件） |

**证据索引（本文引用的所有偏移）**

| 偏移 | 说明 |
|---|---|
| 1840243 | HID 过滤器 usagePage 白名单（不含 0x0001） |
| 1842256 | `UY=['/','/key-test']` 免设备白名单 |
| 1843410 | 路由 `{path:'key-test',name:'keyTest',layout:'empty'}` |
| 2371971 | 虚拟键盘 104 键表 `c9` |
| 2375902 | `l9=c9.flat().map(e=>e.code)` |
| 2375930 | `function u9()` —— key-test 逻辑本体 |
| 2380442 | keydown/keyup/mouse/wheel/blur 事件注册 |
| 2384580 | 页面 `…}=u9()` |
| 3296577 | 导出表 `u9 as m` |
| 1911775 | `FX()` 响应帧解析（data@8） |
| 1915487 | `GET_MAGNETIC_AXIS_KEY_STATUS:96` 唯一出现处（死枚举） |
| 1919110 | `JX()` 0xFB 磁轴数据解析 |
| 1919506 / 1919911 / 1920304 | `start24GDisconnectListener` / `startResetListener` / `start24GSleepListener` |
| 1920705 | `start24GWakeListener`（`A6 FF 01`） |
| 1949962 | `startDeviceStateListener`（0xFA） |
| 1838541 | 唯一调用点 `P()`：type=6 + `e[3]===1` |
| 1835029 / 1835427 / 1840019 / 1841818 | 四处 `tftConfig.isShowTftInfo` 门控 |
| 1803404 | `RY()` TFT 信息轮询（8000ms） |
| 1948903 | `setTftScreenInfo`（0x34，24 字节 payload） |
| 1837352 / 1837647 | 0xFC/4 断开回调 `j()`、0xFC/5 重置回调 `M()` |
| 1238（main chunk） | App 根组件 `is24GSleeping` 全屏休眠遮罩 |
| 2488437 / 2487512 / 2490310 | performance 页：v0 校准 `startCalibration`（吃 0xFB）/ v1 `startCalibrationV2`（轮询 0x68）/ 行程测试 `startSimulationTest` |
| 1922166 | `getMagneticAxisStatus`（0x68 轮询请求/响应布局） |
| 1911457 / 1910023 | `PX()` 组帧 / `NX()` 分片发送（每包 payload = reportCount-8） |
