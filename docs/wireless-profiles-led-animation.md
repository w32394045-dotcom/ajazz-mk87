# MK87 的 2.4G 无线 / 多 Profile / 灯效动画上传 —— bundle 静态逆向

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

> 对象：AJAZZ MK87（VID `0x0C45` / PID `0x8047`），官方网页驱动 bundle
> `assets/layout-classic-CMxiG14P.js`（3.3 MB，未混淆）。
> 本轮**纯静态分析，未接触任何 HID 设备**；所有结论都能用 `scripts/wireless_ref.js` 复跑验证
> （该脚本把 bundle 里的官方实现载进 vm 沙箱，用 mock HID 设备跑出真实报文，再与我的重写实现逐字节对比）。
>
> 标 **【推断】** 的条目是"代码可读但缺真机证据"的部分，其余均为源码可直接核对的事实。

---

## 0. 结论速览（先看这张表）

| 主题 | 结论 |
|---|---|
| 2.4G 如何被识别 | 接收器以 `vid:pid:productName` 命中 store 里的 **S 常量（64 项）**后，用 `oe()` 再读一次 `GET_DEVICE_INFO` 拿到 `manufacturer`/`product`，拼成 **5 段完整设备 ID**，再用它去查 `vid-pid-name-mfr-product` 形式的配置文件键 |
| MK87 的 2.4G 配置 | **`3141-65278-2.4G Dongle-1-18`**（pid 65278 / productName `2.4G Dongle` / manufacturer 1 / product 18）。它的 87 键布局、musicConfig、tftConfig 与 MK87 的 USB 配置**逐键完全一致**，只是 `connectType` 变 `2.4G`、`routesName` 少一个 `tft` |
| 24G 专用命令 | `55`=整表读灯（4 字节头，电量在响应 `byte[3]`）、`59`=按灯号表读（8 字节头，电量在 `byte[5]`）、`60`=音乐流（8 字节头，RGB565 大端，**10 ms 超时 0 重发**）、`252`=链路通知 |
| 2.4G 独有的 ACK 规则 | 只有 **cmd 66（GIF 灯效）在 2.4G + frameVersion=1** 时才校验 ACK 里的包序号（`parseAddr = resp[2]<<8\|resp[3]`）；cmd 65 不校验 |
| 休眠/唤醒 | 休眠 = `55 FC 06`；唤醒 = **`A6 FF 01`（另一种帧头）**。驱动**不发任何命令、不写 feature report**，只被动改 UI 状态（`is24GSleeping`），整屏遮罩 |
| 断连/重置 | `55 FC 04` = 断连（关设备 + `forget` + 回首页 + 报错）；`55 FC 05` = 复位（`location.reload()`）。两者都**不会**自动重连 |
| SET_PROFILE(144) | 3 字节头 `AA 90 <n>`，**n 从 1 开始**；成功判据 = 响应 `byte[2]` 回显 n |
| maxProfile / currentProfile | 设备信息 `byte[33]` / `byte[19]`（1-based）；`maxProfile > 1` 才算"有板载 Profile"，否则只用本地（localforage）软件 Profile，上限 4 个 |
| 软件 Profile 切换 | 写入全套数据（keys/fn/LED/自定义灯/宏…）后 **只重读 key/fn**，LED/自定义灯/宏用 profile 里的值覆盖内存 → **不重读全量** |
| 板载 Profile 切换 | `SET_PROFILE` 之后 **`deviceInit` 全量重读** + `syncHardwareProfiles` 用设备里的 max/current 重建列表 |
| profiles 页 | 路由 `/profiles` 只在 `layout === 'tech'` 时才被放行；**本 bundle 的 `OH()` 硬编码 `classic`** → 页面 chunk 虽在（`assets/useProfiles-Bm0j-YvT.js`）但进不去；MK87 的 `routesName` 里也没有 `profiles` |
| 灯效动画上传 | `65`=LED/GIF 动画（帧数 u16LE + 延时 u16LE + 帧×灯×RGB888），`66`=GIF 灯效/实时同步；8 字节头 `AA 41/42 seqHi seqLo totalHi totalLo 0 0`；**每包数据 = reportCount-8**（2.4G 56 B，USB 走 0xFF67 通道 4096 B） |
| `SET_LED_BOOT_ANIMATION(64)` | **bundle 里只有枚举、零调用点**。开机动画实际复用 `SET_LED_USER_ANIMATION(65)`，靠 `ledId === 'startup'` 的灯效条目（帧数上限 200） |
| MK87 的灯效动画现状 | `gifMaxFrames = 0` → **GIF 灯效公式上不可能**（`Math.min(帧数, 0)`）；`ledMaxFrames = 0` 且没有 `ledConfig` → LED 动画页不出现；只有 TFT 动画（140 帧）可用 |

---

## 1. 方法与可复核性

三个层次，缺一不可：

1. **源码定位**：`scripts/wx_lib.js`（复制 `extract.js` 的 `matchPair`/`beautify`）+ `scripts/wx_probe.js`
   按 token 找偏移、按名字取函数体。所有偏移都写在 `docs/wireless-constants.json → sourceOffsets`。
2. **报文级复核**：`scripts/wireless_ref.js` 把 `docs/infra.js` + `docs/protocol_commands.js`
   **原封不动**载入 `vm` 沙箱（含官方 `PX/NX/IX/FX/MX/LX`），造一个只会
   `collections / sendReport / addEventListener` 的 mock 设备，按需回造响应帧，
   让官方函数真的跑一遍并捕获它发出的字节，然后与我重写的构造函数逐字节 `memcmp`。
3. **自检**：`node scripts/wireless_ref.js` → 11 项全 PASS（`--dump` 打印样例报文，`--verbose` 打开官方报错日志）。

```
================ wireless_ref.js 自检（对照 bundle 官方实现）================
[PASS] Profile 报文：setProfile(3) 与官方 iQ 逐字节一致 + 回显校验
[PASS] 灯效动画 cmd65：2.4G(64B 报告) 分包与官方 UZ 逐字节一致        15 包 × 64B
[PASS] 灯效动画 cmd65：USB(走 0xFF67 TFT 通道, 4104B) 与官方 UZ 逐字节一致
[PASS] GIF 灯效 cmd66：2.4G + frameVersion=1 的 checkAddr/parseAddr(seq) 分支与官方 MZ 一致
[PASS] 音乐 cmd60：24G 封包（RGB565 大端，10ms 超时 0 重发）与官方 TZ 逐字节一致
[PASS] 音乐 cmd50：USB 分支（原样 4B/灯）与官方 TZ 逐字节一致
[PASS] 24G 读回 cmd55：请求分包 + 电量/RGB 解析与官方 OZ 一致
[PASS] 24G 读回 cmd59：请求=灯号表(u16 LE) + 电量在响应 byte5，与官方 kZ 一致
[PASS] 2.4G 通知：252/4|5|6 与唤醒帧 A6 FF 01 的监听器与官方一致
[PASS] 帧上限与 speed→delay 规则与官方源码一致
[PASS] 2.4G 识别表 / 配置键 / MK87 映射自检
合计 11 项：PASS 11 / FAIL 0
```

> 自检期间修正了两个**仅靠肉眼读 beautify 代码会读错**的地方，值得记下来：
> 1. 灯效动画头不是 6 字节而是 **8 字节**（官方 `new Uint8Array(8).fill(0)`，后两字节恒 0），
>    所以数据从偏移 8 开始、每包容量 `reportCount-8`；
> 2. `SET_MUSIC_DATA_24G_64_BYTE` 的 `otherHeader` 只传 **1 个元素** `[musicType]`，
>    这样 `PX` 才肯把"末包标志"写进 `byte[6]`（传 `[musicType,0]` 会让标志位永远为 0）。

---

## 2. 2.4G 设备是怎么被认出来的

### 2.1 S 常量：64 项「特殊 2.4G 设备名」表（`@1832488`）

store 里一个字符串常量，`split(',')` 后就是识别表，键是 **十进制** 的 `vid:pid:productName`：

```js
// @1832488（截取）
S=`1452:591:2.4G Dongle,1452:592:2.4G Dongle,1452:591:2.4G Wireless Receiver,
   3141:65278:2.4G Dongle,3141:65276:HS USB Dongle,3141:65278:2.4G Wireless Receiver,
   3141:65274:2.4G Wireless Receiver,3141:65273:HS USB Dongle,3141:65273:BOOM68Ultra-2.4G,
   3141:65278:VOICSKY KB,...,3141:36880:2.4G 8K Dongle,3141:59392:2.4G 8K Dongle,
   3141:65274:2.4G Wireless Keyboard,...,3141:65273:X75GC,3141:65278:QSENN2.4`.split(`,`)
```

- 64 项，`3141`(=0x0C45) 占 60 项，`1452`(=0x05AC) 占 4 项；
- 覆盖的 pid：`65273/0xFEF9`、`65274/0xFEFA`、`65276/0xFEFC`、`65278/0xFEFE`、`36880`、`59392`；
- 全表见 `docs/wireless-constants.json → identification.special24GDevices`。

**用途**只有一个：命中这张表就说明"这个 HID 设备是 2.4G 接收器的一种，`vid:pid:name` 不唯一，需要补读身份"。

### 2.2 `oe()`：完整设备 ID = `vid:pid:productName:manufacturer:product`（`@1840806`）

```js
async function oe(e){                       // e = HIDDevice
  try{
    e.opened||await e.open();
    let t=await l(`getDeviceInfo`,e,void 0,!1);   // 官方 getDeviceInfo，第 4 参 false = 不写 store
    return e.close(), `${e.vendorId}:${e.productId}:${e.productName}:${t.manufacturer}:${t.product}`;
  }catch(e){ return console.error(`获取通用2.4G设备完整设备ID失败:`,e), `` }
}
```

`manufacturer` = `GET_DEVICE_INFO` 的 `byte[12..13]`，`product` = `byte[14..15]`（MK87 实测 1 / 18）。

调用点（`requestDevices` 与 `reconnectDevices`）：

```js
let r=`${e.vendorId}:${e.productId}:${e.productName}`;
if(S.includes(r)){ let t=await oe(e); t&&(r=t); await wV(100) }   // ← 用完整 ID 覆盖去重键
```

### 2.3 配置文件键：`vid-pid-name[-mfr-product]`（`ae()`）

```js
async function ae(e){                                   // e = 上面那个去重键（3 段或 5 段）
  let [t,n,r,i,a]=e.split(`:`),
      o=`${t}-${n}-${r}${i?`-${i}`:``}${a?`-${a}`:``}`,  // 3141-65278-2.4G Dongle-1-18
      s=`ajazz`, c=ie(o,s);                             // 在 VY 映射表里找 /src/config/keyboards/ajazz/<o>.ts
  if(!c) throw Error(`所有路径都未找到配置文件: ${o}`);
  return c;
}
```

bundle 里 ajazz 一共 **118** 个配置，其中 **42** 个是带 `-manufacturer-product` 后缀的 2.4G 接收器专用配置
（`3141-65273-HS USB Dongle-1-103`、`3141-65274-2.4G Dongle-1-100`、`3141-65278-2.4G Dongle-1-18`、…）。
这就是"同一个接收器 pid 下不同键盘"的区分方式：**pid 只决定"是哪种接收器"，product 才决定"是哪把键盘"**。

### 2.4 MK87 的两套配置（本轮最实用的结论）

| | USB 有线 | 2.4G 接收器 |
|---|---|---|
| 配置键 | `3141-32839-AJAZZ KEYBOARD` | **`3141-65278-2.4G Dongle-1-18`** |
| 偏移 | `@1194734` | `@1665299` |
| `connectType` | `USB` | `2.4G` |
| `routesName` | `customKeys, lighting, macro, tft, settings` | `customKeys, lighting, macro, settings`（**无 tft**） |
| `keyList` | 87 键 | **87 键，逐键 `value`/`name` 完全一致（0 处差异，脚本已比对）** |
| `musicConfig` | `{version:1, keyOffset:[F1,Z,↑,Spacebar,R-Alt]}` | 完全相同 |
| `tftConfig` | `{name:'AK980_PRO', 240×135, localforageKey:'w240h135'}` | 完全相同 |
| `lightingConfig` | minBrightness/maxBrightness 1–6、minSpeed/maxSpeed 1–6、`isShowLightBox:false` | 相同（无 `isShowGifEffect`、无 `isEnableLightSync`） |
| `settingsConfig` | 关单键唤醒/稳定性/自动校准/回报率 | 相同 |

证据链：MK87 设备信息 `manufacturer=1 / product=18`（`docs/protocol.md` 实测）→ 键 `…-1-18` 唯一命中；
该配置的 87 键与 musicConfig、tftConfig 与 MK87 USB 配置完全一致。
**【推断】** 未能真机确认接收器上报的 `productName` 就是 `2.4G Dongle`（若是 `AJAZZ AK820MAX` 之类会落到通配配置）。

### 2.5 接口选择：`re()` / `LX()` / `zY`

```js
function re(e){  // 设备可用性过滤
  let t=e.collections||[];
  return t.length!==0 && t.some(e=>[65384,65408,65376,65280,65281,65307].includes(e.usagePage||0));
}
LX=async(e,t=65383)=>{ ... }   // @1912495：按 productId + usagePage=0xFF67 找 TFT 通道（仅 USB 有线有）
```

- `zY`（`docs/infra.js`）是 `requestDevice` 的过滤器表，MK87 走 `3141:32839`；
- **接收器不会命中 `LX`**：2.4G 下没有任何 0xFF67 接口，所以所有上传类命令里
  `connectType === 'USB' ? await LX(productId) : device` 永远走 `device` 分支。

---

## 3. 2.4G 的运行时：监听器、休眠状态机、断连

### 3.1 三个监听器在哪挂、何时挂

`requestDevices` / `openDevice` / `reconnectDevices` 三处，只要设备配置是 `2.4G` 就立刻挂上：

```js
// store，三处同款
o && r.value?.keyboardConfig?.connectType===`2.4G`
  && (await te(n.value),   // start24GDisconnectListener
      await N(n.value),    // start24GSleepListener
      await ne(n.value));  // start24GWakeListener
```

`closeDevice` 会把三个 `removeListener` 都调掉，并把 `is24GSleeping` 复位为 `false`。

### 3.2 五个监听器（3 个 2.4G 专属 + 复位 + 设备状态）

```js
// start24GDisconnectListener (XX, @1919506)
if(r.length>=3 && r[0]===85 && r[1]===HX.GET_24G_DISCONNECT_NOTIFY && r[2]===4) cb();
// start24GSleepListener (QX, @1920304)
if(r.length>=3 && r[0]===85 && r[1]===HX.GET_24G_DISCONNECT_NOTIFY && r[2]===6) cb();
// startResetListener (ZX, @1919911)
if(r.length>=3 && r[0]===85 && r[1]===HX.GET_24G_DISCONNECT_NOTIFY && r[2]===5) cb();
// start24GWakeListener ($X, @1920705) —— 注意帧头是 0xA6，不是 0x55
if(r.length>=3 && r[0]===166 && r[1]===255 && r[2]===1) cb();
// startDeviceStateListener (XZ) —— cmd 250，按子类型分发
if(i.length>=4 && i[0]===85 && i[1]===HX.GET_DEVICE_NOTIFY && i[2]===n) cb(i);
```

回调做的动作（store）：

| 监听器 | 回调行为 |
|---|---|
| 断连 `252/4` | `isConnected=false` + 清 `historyConnect` + `is24GSleeping=false` → `setTimeout(1500)` 后 `router.replace('/')` + `$message.error(link_state)`；**不 close、不 forget、不重连** |
| 休眠 `252/6` | `is24GSleeping = true` |
| 唤醒 `A6 FF 01` | `is24GSleeping = false` |
| 复位 `252/5` | 清磁轴自定义配置后 `location.reload()` |
| 设备状态 `250/6` | `bytes[3]===1` → 开始轮询/推送屏幕系统信息，`0` → 停止 |

### 3.3 `is24GSleeping` 状态机

```
                252/6 sleep                 A6 FF 01 wake
   [awake] ──────────────────► [sleeping] ──────────────────► [awake]
      ▲                            │
      └────────────────────────────┘  closeDevice / disconnect（store 里直接 m=false）
```

- 初值 `false`；`m` 在 store 里同时被 `closeDevice`（`m.value=!1`）和断连处理（`m.value=!1`）复位；
- UI 层是**整屏遮罩**（`assets/main-_p8CH46K.js`）：

```js
k = computed(()=>O.is24GSleeping)            // O = useWebHIDStore()
... m(k) ? h('div', E, [ e('div', D, a($t('sleeping-tips'))) ]) : v('',!0)   // 同时 router-view 仍在下面
```

### 3.4 唤醒流程要不要发命令？—— **不要**

- 全 bundle 只有 `start24GWakeListener` 一个地方处理唤醒，且只做 `m.value=!1`；
- 协议层完全**没有** `sendFeatureReport`：仅有的两处 `sendFeatureReport`/`receiveFeatureReport`
  字符串都在 wasm-bindgen 的 ISP/OTA 刷机胶水里（`@1996053`/`@1996227`），跟 HID 协议无关；
- 也没有 "wake"/"唤醒命令" 之类的命令字：`HX` 的 66 条命令里没有任何 wake。

**结论**：唤醒是键盘/接收器自己的硬件行为（按键/移动触发），驱动侧是纯被动——真机测试时如果发现
"发命令能唤醒"，那属于我们额外发现的固件彩蛋，不属于官方协议。

### 3.5 断连/超时的破坏性细节（真机测试前必须知道）

两条不同的路径，别混：

**(a) 收到断连通知 `252/4`** —— `j()`，**不调用 `forget()`**：

```js
function j(){ if(p.value)return; p.value=!0;
  _=null, y=null, b=null, m.value=!1;                     // 三个监听器引用清空 + is24GSleeping 复位
  n.value&&t.has(n.value)&&(t.get(n.value).isConnected=!1);
  s.value={};                                             // 清 historyConnect
  setTimeout(()=>{ router.replace({path:'/'}); p.value=!1; $message.error($(`link_state`)) },1500);
}
```
→ 设备对象还在 Map 里（只是 `isConnected=false`），但 UI 回首页、**不自动重连**。

**(b) `NX` 重试 3 次仍无响应** —— 这条才丢授权：

```js
r&&(await n.closeDevice(r), n.devices.delete(r), n.historyConnect={}), await e.forget();   // 丢掉 WebHID 授权
location.pathname!==`/` && ($message.error($(`link_state`)), router.replace('/'));
```

也就是说：**一次持续超时 = 设备被 `forget()`、页面回首页、要重新点"连接设备"**。
自研驱动不要照抄这两条策略（见 §8.6 的落地建议）。

---

## 4. 24G 专用命令：framing、数据布局、超时

### 4.1 帧层回顾（本次实测确认的细节）

- 请求包长 = `collections[0].outputReports[0].items[0].reportCount`（MK87 主接口 64，TFT 接口 4104），
  由 `MX()` 以 `sendReport(0, packet)` 发出（report ID 恒 0）；
- 标准 8 字节头：`[0]=0xAA [1]=cmd [2]=len [3]=addrLo [4]=addrHi [5..7]=otherHeader(+lastFlag)`，
  数据从 `byte[8]` 起，每包 `reportCount-8`；
- **自定义头**（`PX` 的 `customHeader` 分支）会跳过 len/addr/last 的写入，整包 = 自定义头原文 + data，
  数据偏移 = 自定义头长度；
- 响应：`FX` 要求 `bytes[0]===0x55`，`{cmd:bytes[1], lenOrType:bytes[2], addr:bytes[3]|bytes[4]<<8, data:bytes.slice(8)}`；
- `checkAddr`（默认 false）为真时，用 `addrStart` 与本包偏移比对响应 addr，可选 `parseAddr` 自定义解析。

### 4.2 GET_ALL_LIGHTS_RGB_24G(55) —— 整表读灯（`OZ` `@1934859`）

```js
let i=(reportCount||32)-4, a=n*2+1, o=Math.ceil(a/i);        // n = 灯数
for(let t=0;t<o;t++){
  let n=new Uint8Array(4).fill(0);                            // 4 字节自定义头
  n[0]=170, n[1]=HX.GET_ALL_LIGHTS_RGB_24G, n[2]=t, n[3]=0;    // [AA,37,包序号,0]
  let a=new Uint8Array(i).fill(0);                            // 请求体全 0
  let c=await NX(e,{cmd:HX.GET_ALL_LIGHTS_RGB_24G,contentSize:i,data:a,
                    headerCount:n.length,customHeader:n,timeout:fr===1?2e3:500});
  s.push(...c);
}
s.length>0 && (c=s[0][3]);                                    // 电量 = 首包响应 byte[3]
let l=new Uint8Array(s.flatMap(e=>Array.from(e.slice(4)))).slice(0,n*2);   // 数据从 byte[4] 起
// 每灯 2 字节 RGB565 大端
```

| 项 | 值 |
|---|---|
| 请求头 | 4 字节 `[0xAA, 0x37, 包序号, 0]`，**没有 addr 字段** |
| 请求体 | 全 0，长度 `reportCount-4`（64B 报告 → 60B） |
| 包数 | `ceil((灯数*2+1) / (reportCount-4))`（128 灯 → 5 包） |
| 响应头 | 4 字节 `[0x55, 0x37, 包序号, 电量]` |
| 电量 | **响应 `byte[3]`**（只取首包） |
| 像素 | 从 `byte[4]` 起，RGB565 **大端**：`r=(v>>11&31)<<3, g=(v>>5&63)<<2, b=(v&31)<<3` |
| 超时 | `frameVersion===1 ? 2000 : 500`，重发 3 次 |

### 4.3 GET_ALL_LIGHTS_RGB_24G_64_BYTE(59) —— 按灯号表读（`kZ` `@1935649`）

```js
let i=(reportCount||64)-8;                       // 每包数据 56B
let a=new Uint8Array(n.length*2);                // 请求体 = 灯号表，每灯 u16 小端
n.forEach((e,t)=>{ a[t*2]=e&255; a[t*2+1]=e>>8&255 });
let o=await NX(e,{cmd:HX.GET_ALL_LIGHTS_RGB_24G_64_BYTE,contentSize:a.length,data:a,
                  abortSignal:r,timeout:2e3,checkAddr:!0});
o.length>0 && (s=o[0][5]);                       // 电量 = 首包响应 byte[5]
let c=new Uint8Array(o.flatMap(e=>Array.from(e.slice(8)))).slice(0,n.length*2);
```

| 项 | 值 |
|---|---|
| 请求头 | **标准 8 字节头**（无 otherHeader） |
| 请求体 | **要读的灯号表，每灯 u16 小端**（`2*灯数` 字节）→ 87 灯 = 174 B = 4 包 |
| checkAddr | `true`（期望响应 addr = 本包在灯号表里的字节偏移） |
| 响应头 | 8 字节，**电量在 `byte[5]`**，数据从 `byte[8]` 起 |
| 像素 | RGB565 大端，每包 28 灯 |
| 超时 | **固定 2000**（不看 frameVersion），重发 3 次 |

> 命令名里的 `64_BYTE` 指"给 64 字节报文的接收器用"，不是"每次读 64 字节"。

### 4.4 SET_MUSIC_DATA_24G_64_BYTE(60) —— 音乐流（`TZ` `@1932415`）

`TZ` 有四条分支，判据是 `connectType` + `reportCount` + `lightingVersion`：

```js
if(t.connectType===`USB`){ ... cmd:HX.GET_LED_DATA(50) ... 原样 4B/灯, timeout 50/2000 ... }
else if(t.connectType===`2.4G` && a===64 && s===1){        // a=reportCount, s=lightingVersion
  let t=a-8, n=Math.floor(r.length/4), i=new Uint8Array(n*2);
  for(let e=0;e<n;e++){ let t=e*4, [n,a]=jV(AV({r:r[t+1]||0,g:r[t+2]||0,b:r[t+3]||0})); i[e*2]=n,i[e*2+1]=a }
  let s=Math.ceil(i.length/t);
  for(let n=0;n<s;n++){ ... await NX(e,{cmd:HX.SET_MUSIC_DATA_24G_64_BYTE,contentSize:c,addrStart:l,data:u,
        otherHeader:o, maxRetries:0, timeout:10, isNeedLastPacketFlag:n===s-1}) }
}
else { ... cmd:HX.SET_MUSIC_DATA(53)，4 字节自定义头 [AA,53,包序号,musicType] ... }
```

| 分支 | cmd | 头 | 体 | 超时/重发 |
|---|---|---|---|---|
| USB 有线 | **50**（`GET_LED_DATA`） | 8B，`byte5=musicType`，非末包 `byte6=0`、末包 `byte6=1` | **原样 4 字节/灯** | 50 ms（fw1 → 2000）/ 3 次 |
| 2.4G + 64B 报告 + lightingVersion=1 | **60** | 8B，`otherHeader=[musicType]` → `byte5=musicType`，末包 `byte6=1` | **RGB565 大端 2 字节/灯**（`AV/jV` 量化） | **10 ms / 0 次**（流式，丢包不管） |
| 其它（老设备/BT） | 53 | 4B 自定义头 `[AA,53,包序号,musicType]` | `reportCount-4` | 10 ms / 0 次 |

量化函数（`@1010885` / `@1010930`）：

```js
AV=e=>(e.r&248)<<8|(e.g&252)<<3|(e.b&248)>>3     // RGB888 → RGB565
jV=e=>[e>>8&255,e&255]                            // u16 → [hi,lo]（大端）
```

> 音乐渲染主逻辑不在本轮范围（Lead 在做），这里只锁死"同一条流在 2.4G 下变成 2B/灯 + 10ms 不重发"。

### 4.5 GET_24G_DISCONNECT_NOTIFY(252) 与设备状态(250)

见 §3.2。要点：

- `252` 是**只从设备到主机**的通知，帧头仍是 `0x55`，`byte[2]` 为子类型（4/5/6）；
- `0xA6 0xFF 0x01` 是**唯一**非 `0x55` 头的帧，只表示"唤醒"；
- `250` 是设备状态通道，`byte[2]=子类型`、`byte[3]=状态值`；已确认的子类型只有 `6`（屏幕系统信息开关）。

---

## 5. 2.4G 与 USB 的差异总表

| 维度 | USB 有线 | 2.4G |
|---|---|---|
| 设备过滤 | `zY` 里 `3141:32839`；`re()` 的 usagePage 白名单 | 额外命中 `S` 表 → `oe()` 补 manufacturer/product |
| 配置键 | 3 段 `3141-32839-AJAZZ KEYBOARD` | 5 段 `3141-65278-2.4G Dongle-1-18` |
| 路由 | 含 `tft` | **无 `tft`**（TFT 页不出现；`deviceInit` 还会在 `tftDirection===255` 时剔掉 tft 路由） |
| 报文长度 | 主接口 64B / TFT 接口 4104B | 只有接收器接口 64B（**没有** 0xFF67） |
| 灯效/TFT 上传 | `connectType==='USB' ? await LX(productId) : dev` → 走 4104B 通道，4096B/包 | 走接收器，56B/包 |
| 灯效读回 | `getAllLightsRGB(51)`：512B 整表 | `getAllLightsRGB24G64Byte(59)`（64B 报告 + lightingVersion=1）或 `getAllLightsRGB24G(55)` |
| 电量来源 | `GET_DEVICE_INFO.byte[17]` | 同上，但轮询时用 `55/59` 返回的电量刷新 `deviceInfo.batteryLevel` |
| 音乐 | cmd 50，原样 4B/灯，50ms 超时 3 重发 | cmd 60，RGB565 2B/灯，**10ms 超时 0 重发** |
| 灯效动画 ACK | 只按 cmd 匹配 | cmd 66 还需回显包序号（frameVersion=1） |
| 超时基线 | 500ms | fw1 设备 2000ms（`frameVersion===1` 分支） |
| 监听器 | 只挂 `startResetListener`（252/5） | 额外挂断连/休眠/唤醒 3 个（复位那个本来就有；设备状态监听另由 `tftConfig.isShowTftInfo` 决定） |
| 设置页 | 回报率 = `reportRate` | 回报率 = `wirelessReportRate`(u16)、强制显示休眠时间、`powerMode` 三档 |
| 错误文案 | `message_driveall_error` | `message_driveall_error2`（2.4G 专用） |
| 性能页 | 可切轴体 | `connectType!=='USB'` 隐藏轴体切换；重置 tab 需 `isShow24GCalibration` |

---

## 6. 多 Profile

### 6.1 SET_PROFILE(144) 的语义（`iQ` `@1953899`）

```js
iQ=async(e,t,n)=>{                                  // n = profile 号（1-based）
  try{
    let t=new Uint8Array([170,HX.SET_PROFILE,n&255]); // 3 字节自定义头 AA 90 nn
    return (await NX(e,{cmd:HX.SET_PROFILE,contentSize:1,customHeader:t,timeout:2e3}))[0]?.[2]===n;
  }catch(e){ return console.error(`切换 Profile 失败:`,e),!1 }
}
```

- 报文（64B 报告）：`aa 90 03 00 00 …`（profile=3），**没有数据区**，`contentSize=1`；
- 成功判据：响应 `byte[2]` 必须回显 profile 号（`(await NX())[0]?.[2] === n`）；
- **n 从 1 开始**：调用方 `CQ` 传 `t+1`，读设备字段后 `-1` 变本地下标。

### 6.2 `maxProfile` / `currentProfile`

| 字段 | 偏移 | 语义 |
|---|---|---|
| `currentProfile` | `byte[19]` | 当前板载 profile，**1-based** |
| `maxProfile` | `byte[33]` | 板载 profile 数量 |

```js
xQ=e=>{ let t=e?.maxProfile??0; return t>1?t:0 }     // >1 才算支持板载，0/1 → 纯软件
SQ: let r=xQ(n),  o=Math.min(Math.max((n?.currentProfile??1)-1,0), r-1)   // 设备 1-based → 本地 0-based
```

- `maxProfile = 0`（**MK87 就是 0**）或 1 → `isHardwareProfile = false`；
- 软件 Profile 上限：`D = maxProfile || 4` → 纯软件时 **4 个**；板载时上限 = `maxProfile`。

### 6.3 Profile 里到底存了什么

Profile = **一份完整的 deviceStorage 快照**（localforage，键 `` `${deviceId}-profile` ``）：

```js
{ profileList:[{ profileName, keyList, fnKeyList, wheelKeys, ledEffect, customLedData,
                 macroDataList, magneticAxisRT, magneticAxisRTConfig, lightBoxData,
                 sideLightData, ledData, ... }], currentProfileIndex }
```

"新建 Profile"不是空白，而是**按官方模板重置**（`useProfiles` 的 `H()`）：

```js
ledEffect     = {...原值, mode:11, colorMode:1, direction:0, brightness:5, speed:3}
customLedData = 128 × {ledId:i, red:0, green:0, blue:0}
fnKeyList     = 由 GET_DEFAULT_FN_KEY_MATRIX 重建
macroDataList = []            // routesName 含 macro 时
magneticAxisRT= 128 × {axisType:0, …, triggerKeyStroke:0, pressRT:0, releaseRT:0}
keyList/wheelKeys = 去掉 userKey（回到固件默认）
```

### 6.4 软件 Profile 切换：**不重读全量**

`bQ = switchAndApplyProfile(dev, index, profile?)`：

```js
if(!await gQ(e,t)) return !1;                       // 1) 只改 currentProfileIndex 并落盘
i.keyList      && await r(`setKeyData`, e, i.keyList[, i.wheelKeys]);
i.fnKeyList    && await r(`setFnKeyData`, e, i.fnKeyList);
i.ledEffect    && await r(`setLEDEffect`, e, i.ledEffect);
i.customLedData&& await r(`setCustomLEDData`, e, i.customLedData);
i.macroDataList&& await r(`setMacroData`, e, i.macroDataList);
i.magneticAxisRT / magneticAxisDKS / lightBoxData / sideLightData … 同理
i.fnKeyList    && await r(`getFnKeyData`, e);        // 2) 只回读 FN 层
fQ(e,i);                                            // 3) profile → deviceStorage（保留当前 deviceInfo/sn）
await a(void 0,{ledEffect:i.ledEffect, customLedData:i.customLedData, macroDataList:i.macroDataList});
                                                    // 4) initProtocol 用 profile 值覆盖内存，不重读这三项
```

页面层还会先 `syncDeviceStorageToProfile(dev, 当前快照)` 把改动存回旧 profile，再切；
切换过程通过 `profileSwitchBus`（mitt，`'profile-switch'`）广播 `start/finish`，
lighting 等页面收到后显示遮罩/刷新。

### 6.5 板载 Profile 切换：**全量重读**

`CQ = switchHardwareProfile(dev, index)`：

```js
if(!await n(`setProfile`, e, t+1)) return !1;   // 1) SET_PROFILE
await gQ(e,t);                                 // 2) 本地下标
let r=await n(`deviceInit`, e);                // 3) 全量重读（deviceInfo/gameMode/key/fn/led/macro/…）
await i(r);                                    // 4) setProtocolDataFromDeviceInit
await SQ(e);                                   // 5) 用设备 maxProfile/currentProfile 重建本地列表
```

**结论**：软件 Profile 切换后只需重读 key/FN（LED/宏用 Profile 值覆盖）；板载 Profile 必须全量 `deviceInit`。

### 6.6 profiles 页：tech 布局专属，本 bundle 进不去

```js
var DH=[`classic`,`tech`];
function OH(){ let e=`classic`; return DH.includes(e)?e:`tech` }        // @1056353 —— e 被硬编码成 classic
...
WY = OH()===`tech` ? [`profiles`] : [];                                 // 允许路由白名单
let a=new Set([...routesName, ...WY]); if(!a.has(route.name)) next('/');
```

- 路由表里确实有 `{path:'profiles', name:'profiles', layout:'sider'}`；
- 但 `OH()` 恒返回 `classic` → `WY=[]`，且 MK87 的 `routesName` 也没有 `profiles`
  → **本 bundle 下 `/profiles` 永远被重定向回首页**；
- 页面实现仍在包里（`assets/useProfiles-Bm0j-YvT.js`，5 个导出：`t` = 组合式函数），
  逻辑就是 §6.3–6.5 那套（`getHardwareMaxProfile / switchHardwareProfile / switchAndApplyProfile /
  syncDeviceStorageToProfile / importProfile / exportProfile`）。

### 6.7 MK87 的实际行为

- `maxProfile = 0` → 纯软件 Profile；SPA 页面不可达 → **MK87 用户实际用不到 Profile 功能**；
- 但初始化时仍会执行 `syncHardwareProfiles(dev) || updateCurrentProfile(dev)`：
  `xQ()` 返回 0 → `SQ` 直接 `return false` → 退化成"把当前 deviceStorage 存成 profile[0]"，
  即**本地始终有一份名为 `profile` 的快照**，只是没有 UI 去切。

---

## 7. 灯效动画上传

### 7.1 命令与用途矩阵

| cmd | 名称 | 谁在用 | 用途 |
|---|---|---|---|
| 54 | `CLEAR_LED_DATA` | `VZ` | 清灯效动画缓存（LED/GIF 上传前） |
| **64** | `SET_LED_BOOT_ANIMATION` | **无调用点** | 开机动画；实际复用 65（`ledId='startup'`，≤200 帧） |
| **65** | `SET_LED_USER_ANIMATION` | `UZ` | LED 页自定义动画（含开机动画） |
| **66** | `SET_LED_DATA` | `MZ`（GIF 灯效）、`HZ`（实时同步动画） | 帧动画 / 逐灯实时色 |
| 50 | `GET_LED_DATA`（当写用） | `TZ` USB 音乐 | 音乐律动 |
| 80 | `SET_TFT_USER_ANIMATION` | `GZ` | TFT 屏动画（另一条 256B 延时表格式，见 `docs/protocol_commands.js` 与 `docs/tft-page.md`） |

### 7.2 payload 与分包（cmd 65/66 共用）

```
payload = [帧数 u16 LE][每帧延时 u16 LE][帧0: 灯0 RGB, 灯1 RGB, …][帧1: …]…

每包 = reportCount 字节
  byte0..5 : AA cmd seqHi seqLo totalHi totalLo      （seq/total 都是大端）
  byte6..7 : 恒 0                                     （官方 new Uint8Array(8) 的尾巴）
  byte8..  : payload 的 reportCount-8 字节切片
total = ceil((4 + 3*灯数*帧数) / (reportCount-8))
```

- 2.4G：`reportCount=64` → 56 B/包。例：87 灯 × 3 帧 = 787 B → **15 包**（`--dump` 可看）；
- USB：先 `await LX(productId)` 拿到 0xFF67 通道（`reportCount=4104`）→ 4096 B/包，末包补 0；
- 超时 2000 ms，重发 3 次；
- **ACK 差异**：cmd 65 只按 cmd 匹配；cmd 66 在 `2.4G && frameVersion===1` 时 `checkAddr:true`
  + `addrStart=包序号` + `parseAddr = resp[2]<<8|resp[3]` → **接收器必须回显包序号，否则每包都超时**
  （自检里用官方 `NX` 正向/反向各验了一次）。

### 7.3 帧数据格式与帧上限从哪来

- **灯序**：`keyboardConfig.keyList.flat()` 的顺序；`disabledLight` 的灯**整灯剔除**（不是填黑），
  所以每帧字节数 = 有效灯数 × 3，帧数 = `data.length / 灯数`；
- **延时**：全局一个值，`delay = Math.ceil(106 - speed)`，speed 默认 100（编辑器导入时 clamp 到 **50..104**）；
  **【推断】** 固件侧时间单位未知 —— 官方预览定时器在两处分别用 `(106-speed)*10` 和 `*20` ms，自相矛盾；
- **帧上限**（全部来自 `GET_DEVICE_INFO`）：

| 字段 | 偏移 | 用途 | MK87 |
|---|---|---|---|
| `tftMaxFrames` | 22 | TFT 动画 | 140 |
| `gifMaxFrames` | 24 | **GIF 灯效**：超了弹窗；实际发送 `Math.min(帧数, gifMaxFrames)` | **0** |
| `ledMaxFrames` | 26 | **LED 页动画**：`!=0` 用它，`==0` 兜底 **260**；`ledId==='startup'` 固定 **200** | **0** |

- GIF 灯效的 `Math.min(帧数, 0)` = 0 帧 → 等于"公式上不可能"。这正好解释了
  `lightingConfig.isShowGifEffect` 为什么必须为 true 才显示 gif tab，
  而 MK87 的 `lightingConfig` 里根本没有这个字段。

### 7.4 GIF 灯效编辑器的数据格式（`g7` `@2268676` / `Eae` `@2274519`）

```js
// 上传（handleApplyGifLighting → S()）
let n=keyboardConfig.keyList.flat(), i=n.length, a=t.data.length/i;        // 帧数
if(a>deviceInfo.gifMaxFrames && !await x()) return;                        // 超帧数确认弹窗
let d=Math.min(a,deviceInfo.gifMaxFrames),
    f=new Uint8Array(4);
f[0]=d&255, f[1]=d>>8&255,                                               // 帧数 u16 LE
f[2]=Math.ceil(106-t.speed)&255, f[3]=Math.ceil(106-t.speed)>>8&255;      // 延时 u16 LE
let p=n.map((e,t)=>e.disabledLight?-1:t).filter(e=>e>=0),                 // 有效灯索引
    m=Array.from({length:d},(e,n)=>p.map(e=>RV(t.data[n*i+e]))).flat();   // 帧×有效灯 → {r,g,b}
await r(`setGifLighting`, void 0, f, m, progressCb);                      // → MZ → cmd 66
```

- JSON 格式：`{ name, speed, data:["#rrggbb", …], cols:[每行键数…] }`，
  `data.length` 必须 = 帧数 × 灯数（导入时校验 `cols` 与 `keyList` 行长度一致）；
- `speed` 导入时 `Math.max(50, Math.min(104, floor(speed)))`；
- 内置素材：`lightingConfig.gifEffectIds[]` → `fetch('/gif-lighting/<id>.json')`；
- 本地存储：`gifLightingList_<keyList 形状签名>` + `gifLightingItem_<gifId>`；
- 预览：`setInterval(…, Math.ceil(106-speed)*20)` 循环切帧，纯前端。

### 7.5 `MV` 是 TFT 动画的延时表，不要跟 LED 动画混

```js
MV=e=>{ let t=e.length, n=new Uint8Array(256).fill(255); n[0]=t;      // 256 字节延时表
        for(let r=0;r<t-1;r++) n[r+1]=Math.min(e[r]*5,255); n[t]=0; return n }
```

TFT 动画（cmd 80）payload = `256 字节延时表 + 各帧 RGB565`；LED 动画（cmd 65/66）**只有 4 字节头**。
两者头也不同（TFT 自定义头 8 字节 `AA 50 seqLo seqHi totalLo totalHi 50 06`）。

### 7.6 MK87 的灯效动画现状

| 能力 | 条件 | MK87 |
|---|---|---|
| TFT 屏动画 | 走 cmd 80 / 0xFF67 通道，≤`tftMaxFrames`=140 帧 | ✅ 可用（另一条通道，见 `tft-page.md`） |
| GIF 灯效 | `isShowGifEffect` + `gifMaxFrames>0` | ❌ 两者都没有 |
| LED 页自定义动画 | `keyboardConfig.ledConfig`（rows/cols） | ❌ 配置里没有 `ledConfig` |
| 实时灯效同步 | `lightingConfig.isEnableLightSync` | ❌ 没开（所以那个 10ms 轮询也不会跑） |
| 音乐律动 | `musicConfig.version`（MK87=1） | ✅ 协议通，但 2.4G 下才是 cmd 60 |

---

## 8. 自研驱动在 2.4G 模式下要怎么做（落地结论）

### 8.1 识别与选接口

1. 枚举 HID，按 `usagePage ∈ {0xFF68,0xFF80,0xFF60,0xFF00,0xFF01,0xFF1B}` 过滤（官方 `re()`）；
2. 用 `vid:pid:productName` 命中 64 项 S 表 → 判定"这是 2.4G 接收器"；
3. 打开后**先读一次 `GET_DEVICE_INFO`（cmd 16，48B）**，取 `manufacturer`(12..13)、`product`(14..15)，
   拼 5 段 ID，再据此选机型配置 —— 不要用 `pid` 猜机型（接收器 pid 是共用的）；
4. 报文长度取 `reportCount`（接收器通常是 64），**不要硬编码 64**；没有 0xFF67 接口时不要尝试 `LX`。

### 8.2 初始化序列（2.4G）

```
GET_DEVICE_INFO(16) → 判 frameVersion/lightingVersion/maxProfile/tftDirection
   ├ frameVersion===1 → 之后所有命令 timeout 用 2000ms
   └ tftDirection===255 → 不提供 TFT 功能
GET_GAME_MODE(17) → GET_KEY(18) → GET_FN_KEY(22) → GET_LED_EFFECT(19) → GET_CUSTOM_LED_DATA(20)
   →（tft 路由存在才读屏幕相关）→ GET_MACRO(21)
电量：不必单独命令 —— 2.4G 用 cmd 59（或 55）响应里带回的电量刷新 UI
```

> `deviceInit` 本身**没有** 2.4G 分支；差异都在"用哪套 keyboardConfig"和 `frameVersion` 拉长的超时上。

### 8.3 灯效动画上传（2.4G）

```
1) CLEAR_LED_DATA(54)                                  // 可选，清缓存
2) payload = 帧数(u16LE) + delay(u16LE) + 帧×有效灯×RGB888
   delay = ceil(106 - speed)，speed 100 → 6        【固件时间单位待真机标定】
3) 8 字节头 AA <65|66> seqHi seqLo totalHi totalLo 00 00，每包 56B 数据
4) 每包等 ACK：
     - cmd 65：匹配 cmd 即可
     - cmd 66 + frameVersion=1：必须校验响应 byte2..3 == 包序号（大端）
5) 超时 2000ms / 3 次重发；收到 ACK 再发下一包（官方是串行的）
6) 实时同步动画（HZ/cmd 66）走同一 cmd，但**不打动画头**：直接发原始颜色字节，
   2.4G 下每包只有 56B → 一次最多 18 灯，需要自己切片并考虑刷新率
```

### 8.4 音乐律动（24G 通路）

```
输入：4 字节/灯的流 [_, r, g, b]
编码：v = (r&0xF8)<<8 | (g&0xFC)<<3 | (b&0xF8)>>3   → 大端 2 字节
封包：8 字节头 AA 3C lenLo addrLo addrHi musicType last 00，数据=编码流切片（56B/包）
发送：timeout 10ms、maxRetries 0 —— **不要重发**，下一帧覆盖即可（否则延迟累积）
```

### 8.5 Profile

- 若 `maxProfile > 1`：`SET_PROFILE(1..maxProfile)` → **必须全量 `deviceInit` 重读**，再用
  `currentProfile`（1-based）校准 UI；
- 若 `maxProfile <= 1`（MK87）：不要显示板载 Profile 入口；要本地多套配置就自己存 JSON（官方那套
  localforage 结构可参考，键 `` `${deviceId}-profile` ``，上限 4 套）；
- 成功判据务必实现"响应 `byte[2]` 回显 profile 号"，否则会把失败当成功。

### 8.6 陷阱清单（照抄官方会踩的坑）

| 坑 | 说明 | 建议 |
|---|---|---|
| 断连就 `forget()` | 官方 2.4G 掉线会丢授权 + 回首页 | 改成"标记离线 + 定时/按事件重连"，别丢授权 |
| 重试耗尽抛异常 | `NX` 重试 3 次后会走 `useWebHIDStore` 的关闭流程并 reject | 自己实现"每命令独立超时 + 可取消" |
| `SET_LED_DATA(50)` 名不副实 | 它是当**写**命令用的（音乐数据） | 命名按语义来 |
| cmd 66 的 ACK 序号 | 2.4G + frameVersion=1 必须回显 seq | 写死"按 seq 校验"，别只按 cmd |
| 动画头是 8 字节 | 不是 6 字节；后 2 字节恒 0，数据从 8 开始 | 别自己"优化"成 6 字节 |
| 音乐 10ms/0 重发 | 官方故意不等 ACK | 别加重试 |
| 延时单位未知 | `106-speed` 的物理单位没标定 | 真机用 2~3 个 delay 值量帧率 |
| `min(帧数, 0)` | gifMaxFrames=0 时官方会算出 0 帧 | 先判上限 >0 再进 GIF 流程 |

---

## 9. 未解问题（留给真机）

1. **【推断】** 接收器的 `reportCount` 是否真是 64、以及它到底曝光哪个 `usagePage`（代码里是 `||32`/`||64` 兜底）；
2. **【推断】** MK87 接收器上报的 `productName` 是否就是 `2.4G Dongle`（决定命中 `…-1-18` 还是某个通配配置）；
3. **【推断】** LED 动画帧延时字段（u16）的固件时间单位（官方预览 ×10 / ×20 自相矛盾）；
4. 2.4G 下 `tftDirection` 是否 255（若是，官方还会再剔一次 tft 路由）；
5. cmd 55 响应 `byte[2]` 是包序号回显还是别的（官方不校验）；
6. 2.4G 下 `SET_PROFILE(144)` 是否真被接收器转发到键盘（官方只按回显判成功）；
7. `SET_LED_BOOT_ANIMATION(64)` 的真实固件入口（bundle 零调用，只能靠真机试）;
8. 2.4G 下 `SET_MUSIC_DATA` 的实际帧率上限（10ms 超时意味着驱动侧至少要 10ms/包）。

---

## 10. 交付物与复核

| 文件 | 内容 |
|---|---|
| `docs/wireless-profiles-led-animation.md` | 本文件 |
| `docs/wireless-constants.json` | 24G 识别表（64 项）、42 个接收器配置键、命令差异、通知语义、Profile 结构、动画帧格式、设备信息字段、全部 bundle 偏移、未解问题 |
| `scripts/wireless_ref.js` | 可执行参考实现 + 自检（`node scripts/wireless_ref.js`，11 项 PASS） |
| `scripts/wx_gen_constants.js` | 从 bundle 重新生成 `wireless-constants.json`（可复核，防止手抄错） |
| `scripts/wx_lib.js` / `wx_probe.js` / `wx_kw.js` / `wx_dump.js` / `wx_cfgmap.js` / `wx_enclose2.js` | 定位/提取工具（`wx_dump.js` 产出 `docs/_wireless_raw/` 的原始片段） |
| `docs/_wireless_raw/` | 原始提取物：`S_special24G.json`、`config_map*.json`、`def_$X.js`、`encl_is24GSleeping_0.js`、`useProfiles.beauty.js`、`def_g7.js`、`def_Eae.js`、`mk87_*_config_raw.js` … |

复核命令：

```powershell
$node = "C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
cd C:\Users\ptfm\Documents\ajazz-re
& $node scripts\wireless_ref.js              # 11 项自检 → PASS 11 / FAIL 0
& $node scripts\wireless_ref.js --dump       # 打印各命令样例报文
& $node scripts\wx_gen_constants.js          # 重新生成常量表（幂等）
```

## 11. 与既有文档的关系

- `docs/protocol.md`：帧格式、66 命令表、TFT 通道、GET_DEVICE_INFO 字段 —— 本轮修正/补充了
  `start24GWakeListener`（`$X`，此前缺失是因为 `extract.js` 的 `\b` 边界匹配不到 `$X=`），
  以及"没有唤醒命令/feature report"这个结论；
- `docs/deepdive-mk87.md`：真机侧数据（电量、灯效、按键矩阵）——本轮补充 2.4G 侧的字段来源差异
  （电量来自 cmd 55/59 响应，而不是设备信息）；
- `docs/protocol_commands.js` / `docs/infra.js`：官方实现原文 —— 本轮**未修改**，仅作为自检的被测对象
  （缺失的 `$X`/`MX`/`LX` 在沙箱内按 bundle 原文注入，见脚本头部注释）。

---

## 真机实测结果（2026-11-01）

- 接收器 = `VID 0C45 / PID FEFE`，product string "2.4G Dongle"；
  `GET_DEVICE_INFO` 回 `manufacturer=1, product=18, workMode=2, fw=1.19, battery 73%, charge=1`
  → 与静态还原的 `3141-65278-2.4G Dongle-1-18` 完全命中。
- 可用协议接口 = **MI_03 / usagePage 0xFF60 / 33B 报文**（官方过滤器表包含 0xFF60）；
  MI_04 / 0xFF59 / 65B 对 GET 命令**无响应**、且**不在**官方过滤器表
  `[65384, 65408, 65376, 65280, 65281, 65307]`。
- 2.4G 下 `GET_KEY`/`GET_FN_KEY` 与 USB 时代 dump **逐字节一致**（配置存在键盘端，双通道共享）。
- 2.4G 写灯效生效；但 `SET_LED_EFFECT` 的**颜色 / colorMode 回读可能不等于写入**（显示正确）
  → 回读不能作为 2.4G 写成功判据。
- 逐键帧流：三种官方打包分支（0x32 / 0x35 / 0x3C）在 MK87 2.4G 下都出现
  「短暂白脉冲 + 随机色 + 竖条纹」→ 通道收到了帧数据但**格式/映射不对**，未还原
  （官方逻辑本身要求 `reportCount=64 && lightingVersion=1`，MK87 两者都不满足）。
- **Windows 兼容**：dongle 与键盘 USB 同插会报 Code 10 / **0xC000009A
  (STATUS_INSUFFICIENT_RESOURCES)**，拔掉其一即恢复；不是固件问题，
  建议两设备插不同 USB 控制器。

详见 [TEST-REPORT.md](TEST-REPORT.md) §8。

### 2026-11-01 补充：官方确认 2.4G 不支持音乐律动

用户转述官方说明：**2.4G 模式下不支持音乐律动**。与真机现象一致（三种帧格式都只出现
「短暂白脉冲 / 随机色 / 竖条纹」，属于通道收了数据但固件没有合法 2.4G 帧映射）。
⇒ 自研音乐律动工具**只做 USB 模式**；2.4G 仅支持常规灯效/自定义灯/改键/设置。

### 2.4G 通知帧真机捕获（2026-11-01）

| 时间 | 接口 | 帧 | 判定 |
|---|---|---|---|
| 闲置 1 分钟 | **0xFF60**（33B） | `55 FC 04 30 00 00 01 00 FF FF…` | 断连 `0xFC/type=4` |
| 按键唤醒 | **0xFFFF / MI_02 COL05**（in=4，report ID=5） | `A6 FF 01` | 唤醒（非 0x55 头） |
| 再次闲置 | 0xFF60 | `55 FC 04` | 可复现 |

- `sleepTime` 单位 = **分钟**（官方 UI 1/10/20/30，0=关闭）
- MK87 实测只发 **`0xFC/type=4` 断连**，未捕获 `0xFC/type=6`（休眠）
- **唤醒帧走 0xFFFF 接口，不在官方 WebHID 过滤器表** → 官方驱动在 MK87 上收不到唤醒帧
