# MK87 网页驱动 · TFT 屏幕页全部逻辑还原

> 🔧 **真机测试已完成（2026-11-01）**：本文部分结论已被真机修正，必务先看 [TEST-REPORT.md](TEST-REPORT.md) §12。
>

> 目标 bundle：`assets/layout-classic-CMxiG14P.js`（3,335,710 字节 / 3,302,270 字符，rolldown 打包，未混淆）。
> 下文所有 `@0x…` 都是该 bundle 内的**字符偏移**，可直接 `SRC.slice(off, off+len)` 复核。
> 结论分三类标注：**【代码】**＝代码里直接读到；**【推断】**＝代码没写死、按上下文推的；**【未决】**＝bundle 里确实没有。
> 本次工作**未打开、未写入任何 HID 设备**，只做静态还原。

## 0. 一分钟结论

| 问题 | 结论 |
|---|---|
| 内置页怎么切 | 网页端**只有一条** `SET_TFT_BUILT_IN_INDEX(81)`，且只在「保存动画」时、`tftConfig.builtInCount > 1` 时才发；MK87 的配置**没有** `builtInCount`，所以**网页端从不发 0x51**。内置页（时钟/天气/系统信息/自定义动画）的切换在设备端，网页端只是被动配合。 |
| 系统信息 | 轮询函数完整存在（8s 一次，天气走 OpenWeatherMap，CPU/GPU 走本机 `http://127.0.0.1:9191/api/hardware/info`），但**只对 `tftConfig.isShowTftInfo === true` 的机型启用**（MK87 没有该键 ⇒ 不启用），并且要设备主动发 `0xFA/type=6` 通知且 `data[3]===1` 才真正开始。 |
| 上传 ACK | **每 4096 字节一包、每包都等 ACK**：壁纸等 `cmd=0x4D`，动画等 `cmd=0x41`（不是 0x50！）【**真机修正 2026-11-01**：`0x4D` 的逐包 ACK 实测也是 **0x41**，fw1.19 对 0x4D/0x50 都回 0x41；且 MK87 无壁纸页，0x4D 写入不可见】，超时 2000ms、最多重发 3 次；全部失败会 `device.forget()` 并跳回首页。 |
| GIF | 用 **omggif**（`GifReader/GifWriter`）不是 gifuct；`delay` 单位 = **厘秒(10ms)**；disposal 0/1/2/3 都先叠当前帧，2=清矩形、3=回滚保存帧；上限 140 帧在**保存时**才裁剪并弹确认框。 |
| 字节序 | `tftColorByteOrder=0` → **小端**（先低字节），`=1` → **大端**（先高字节）。`NV` 旋转/翻转作用在**已编码**的 RGB565 数据上（2 字节为单位的像素搬运），**与字节序无关**，且在拼 `MV` 延时表**之前**。 |
| 屏幕时间 | 10 字节 `5A 01 5A yy mm dd hh mm ss weekday`，`weekday = dayjs().day()`（0=周日）；连上设备时自动同步一次。 |

---

## 1. 设备与配置：MK87 的 `tftConfig` 只有 4 个键

**【代码】** 键盘配置表 `VY` 里 `productId:32839` → 导出符号 `TU`（@0x123adc）：

```js
TU={vendorId:3141,productId:32839,supplierName:`ajazz`,name:`AJAZZ KEYBOARD`,connectType:`USB`,
 routesName:[`customKeys`,`lighting`,`macro`,`tft`,`settings`],
 ...
 tftConfig:{name:`AK980_PRO`,localforageKey:`w240h135`,width:240,height:135},
 settingsConfig:{isShowSingleKeyWakeup:!1,isShowStabilityMode:!1,isShowAutoCalibration:!1,isShowReportRate:!1},
 ...}
```

要点（都影响 TFT 页行为）：

| 键 | MK87 取值 | 页面里的作用 |
|---|---|---|
| `width/height` | 240 × 135 | 画布尺寸、像素编码的宽高 |
| `localforageKey` | `w240h135` | 动画库存储键 `gif_files_w240h135` |
| `name` | `AK980_PRO` | 默认动画 URL `/gif/AK980_PRO/defaultGif.json` |
| `builtInCount` | **不存在** | 内置页选择器整块不渲染，也永不发 0x51 |
| `dataTransform` | **不存在** | `NV()` 直接原样返回（不旋转/不镜像） |
| `materialIds` | **不存在** | 页面里的「上传壁纸」按钮不显示 |
| `isShowTftInfo` | **不存在** | 系统信息轮询不启用 |
| `hideScreenTimeCalibration` | **不存在** | 显示「时间校准」按钮 |
| `defaultAnimationCount` | **不存在** | 只加载 1 个默认动画 |

page 侧对 `tftDirection` 的适配（@0x31c260 `Z9()` 里）：

```js
Cr(()=>c.value?.tftDirection,e=>{ if(e===1){ let e=s?.width,t=s?.height;
  l.value={...s,name:(s?.name||``)+`_h`,width:t,height:e,localforageKey:`w${t}h${e}`} } },{immediate:!0});
```

即 `tftDirection===1` 时把屏幕当竖屏：宽高互换、`localforageKey` 变 `w135h240`、动画库另存一份。`tftDirection===255` ＝无屏：主协议模块在 `deviceInit` 阶段直接把 `tft` 从 `routesName` 里剔除（@0x1d3cd7，`WX` 里 `n.tftDirection===255&&t.routesName.includes('tft')&&(…filter…)`），页面根本不会出现在路由里。

---

> 【**真机补充 2026-11-01**】屏幕是**设备端菜单**（旋钮操作）：主页=时钟/电量/状态图标；设置=灯光效果/灯光颜色/灯光亮度/灯光速率/语言选择；另有自定义动画页。
> **没有系统信息页、没有壁纸页**。`SET_TFT_BUILT_IN_INDEX(0x51)` 发 0..5 设备回 ACK 但屏幕不切页。
> `tftDisplayTime`（12/24h）写入回读一致，但屏幕时钟格式**无可见变化**（fw1.19）。详见 [TEST-REPORT.md](TEST-REPORT.md)。

## 2. 屏幕显示模式 / 内置页（问题 1）

### 2.1 唯一的切换命令

**【代码】** `qZ` = `setTftBuiltInIndex`（@0x1db909）：

```js
qZ=async(e,t,...n)=>{ let r=BX.deviceStorage.deviceInfo?.frameVersion, i=n[0];
  if(typeof i!=`number`||i<0) return console.error(`无效的内置索引参数:`,i),!1;
  let n=t.connectType===`USB`?await LX(e.productId):e;          // ← 走 TFT 通道 (MI_03)
  let a=new Uint8Array(1).fill(0); a[0]=i&255;
  await NX(n,{cmd:HX.SET_TFT_BUILT_IN_INDEX,contentSize:1,data:a,
              timeout:r===1?2e3:50,maxRetries:0});              // ← 50ms、不重发
  return!0 }
```

- 索引只有 1 字节，`contentSize:1`，`maxRetries:0`（**不等结果**：超时返回 `[]`，函数仍返回 `true`）。
- 走的是 **TFT 通道**（`LX(productId)` 找 usagePage 0xFF67 的那个接口），所以报文是 **4104 字节**，只有第 8 字节有意义：`AA 51 01 00 00 00 01 00 <idx> …`。
- **【代码】** 全 bundle 只有**一个调用点**（@0x31e100，在 `saveGif`/`le()` 里）：

```js
if(f.value&&f.value.frameData.length!==0&&!(f.value.frameData.length>c.value.tftMaxFrames&&!await ce())){
  l.value?.builtInCount&&l.value.builtInCount>1&&await n(`setTftBuiltInIndex`,void 0,C.value),  // ← 只有这里
  v.value=0,y.value=!0; ... 逐帧编码 -> setTftUserAnimation
```

### 2.2 UI 列表内容：`1..builtInCount`，标签「内置N」

**【代码】** 页面渲染（`z(f)>1` @0x320035，按钮文字 `nei-zhi` @0x3200cd）：

```js
z(f)>1?(H(),U(`div`,She,[(H(!0),U($o,null,aa(z(f),t=>(H(),ls(F,{
  key:t,type:z(p)===t?`primary`:`default`,onClick:e=>p.value=t },
  {default:B(()=>[vs(L(e.$t(`nei-zhi`))+L(t),1)]),_:2},1032,[`type`,`onClick`]))),128))])):bs(``,!0)
```

- `f` = `builtInCount`，`p` = `currentBuiltIn`（`R(1)`，**1 基**，默认 1）。
- `aa(N, fn)` 是「按数字生成 1..N」，所以按钮文字就是 `内置1 … 内置N`。
- **点击只改本地 ref**，不发任何命令 → **不存在「选中即生效」**；真正下发只发生在保存动画那一刻（发的是**当前选中值**，而且是在上传动画**之前**）。
- `builtInCount` 从哪来：`S=R(l.value?.builtInCount||1)`（@0x31c2xx），`l` = `keyboardConfig.tftConfig`。**【代码】** 本 bundle 里**所有**机型的 `tftConfig` 都没有 `builtInCount`（全文 0 处 `builtInCount:` 定义），所以对 MK87：`S=1`，选择器不渲染，`setTftBuiltInIndex` 永不执行。

### 2.3 index 的含义

**【未决】** bundle 里没有任何 index →「时钟/天气/CPU 信息/自定义动画」的映射表；只能确定：

1. 语义是「设备内置页/内置动画索引」，1 基；
2. 网页端把它当「保存动画前先切到对应内置槽」来用；
3. MK87 上网页端不会发它 —— 屏幕当前显示哪一页完全由**设备端操作**决定；
4. **【推断】** 正因为网页端不知道当前页，设备才需要用 `0xFA` 通知（见 §3.3）告诉主机「我现在在系统信息页」，主机才开始推数据。

---

## 3. 系统信息推送（问题 2）

### 3.1 轮询主体 `RY()`（@0x1b848c）

```js
var NY=R(null),PY=8e3,FY=R(!1),IY=R(!1),LY=R({maxTemp:0,minTemp:0,currentTemp:0,humidity:0,weather:0});
function RY(){
  async function e(){ try{ let e=await AY(),t=e.lat,n=e.lon; LY.value=await jY(t,n),IY.value=!0 }catch(e){...} }   // 天气
  async function t(){ if(!FY.value){ FY.value=!0; try{
      let{sendReport:t}=rY(), n=await OY();                       // 本机硬件信息
      IY.value||await e();                                        // 没拿到过天气就先取
      let r=Math.floor(n?.cpuTemp||0),i=Math.floor(n?.cpuUsage||0),a=Math.floor(n?.gpuTemp||0);
      await t(`setTftScreenInfo`,void 0,{cpuUsage:i,cpuTemp:r,gpuUsage:Math.floor(n?.gpuUsage||0),gpuTemp:a,
        currentTemp:LY.value.currentTemp,maxTemp:LY.value.maxTemp,minTemp:LY.value.minTemp,
        weather:LY.value.weather,humidity:LY.value.humidity}), FY.value=!1
    }catch(e){ ... $dialog.warning({...,content:$(`music_text`),onPositiveClick:()=>EV(`https://config.driveall.cn/music/v2/Music.exe`)}) } } }
  function n(){ if(VV()){ if(NY.value!==null) return; t(), NY.value=_Y(()=>{t()},PY) } }   // 立即一次 + 每 8s
  function r(){ NY.value!==null&&(hY(NY.value),NY.value=null),IY.value=!1,FY.value=!1 }
  return{startGetTftInfo:n,stopGetTftInfo:r,weatherData:LY,isFetching:FY,isWeatherFetched:IY} }
```

- **轮询间隔 `PY = 8e3` = 8000 ms**；启动时先同步执行一次再 `setInterval`。
- `VV()`（@0xf7487）= `/windows|win32/i.test(navigator.userAgent)` —— **只有 Windows 才启动**。
- 有 `FY`（isFetching）互斥锁，避免上一轮没回来就重入。
- 失败时弹窗引导下载 `Music.exe`（本机数据服务），正/负按钮都会复位 `FY`。

### 3.2 数据来源

| 数据 | 来源 | 证据 |
|---|---|---|
| CPU 占用/温度、GPU 占用/温度 | **本机 HTTP 服务**：`GET http://127.0.0.1:9191/api/hardware/info` | `xY='http://127.0.0.1:9191'`、`OY=async()=>(await yY(`${xY}/api/hardware/info`,SY)).data`（超时 500ms） |
| 天气 | OpenWeatherMap：`https://api.openweathermap.org/data/2.5/weather?lat=&lon=&appid=899a6885afbf0702188ef94eb3204236&units=metric&lang=zh_cn` | `jY`（@0x1b8063） |
| 经纬度 | IP 定位四级回退：`api.ipapi.is` → `ipwhois.app` → `get.geojs.io` → `ipapi.co` | `kY`/`AY`（@0x1b7f..） |
| 天气代码 | `MY(owm id)` 映射到 0–23 | `function MY` @0x1b8290，完整表见 §10 与 `tft-constants.json` |

`MY()` 原文（逐字节抄录，便于对照）：

```js
function MY(e){ return typeof e==`number`? e===800?0 : e===801||e===802?1 : e===803||e===804?2 :
  e>=200&&e<=232?9 : e>=300&&e<=321?3 : [500,501].includes(e)?4 : [502,503,504].includes(e)?5 :
  e===511?13 : e>=520&&e<=531? e>=522?7:6 : e===600?18 : e===601?19 : e===602?20 :
  e===611||e===612||e===613||e===615||e===616?23 : e>=620&&e<=622?21 : e===701||e===741?10 :
  e===711||e===721?11 : e===731||e===751?15 : e===761?14 : e===762||e===781?16 : 1 : 1 }
```

（0–23 中 **8/12/17/22 未被使用**；`setTftScreenInfo` 会校验 `weather ∈ [0,23]`。）

### 3.3 开启 / 停止条件（三层门控）

1. **OS**：`VV()` 为 Windows。
2. **机型配置**：`tftConfig.isShowTftInfo === true`。设备连接/重连/初始化成功后：`!g.value&&r.value?.keyboardConfig?.tftConfig?.isShowTftInfo&&await P(n.value)`（@0x1c1a9a 等 4 处）。
3. **设备状态通知**：`P()`（= `startDeviceStateListener`）注册监听，回调里 `e[3]===1` 就 `startGetTftInfo()`，否则 `stopGetTftInfo()`：

```js
}async function P(e){ x.value&&=(x.value(),null);
  let t=null,n=await c(`startDeviceStateListener`,e,6,e=>{ let n=e[3]===1; n!==t&&(t=n,n?u():d()) });
  ...}                                            // u=startGetTftInfo, d=stopGetTftInfo  (@0x1c0dcd)
```

`startDeviceStateListener`（`docs/protocol_commands.js` 第 1176 行）只放行：

```js
i.length>=4 && i[0]===85 /*0x55*/ && i[1]===HX.GET_DEVICE_NOTIFY /*0xFA*/ && i[2]===n /*6*/
```

即 **input report `55 FA 06 xx …` 的第 4 字节（帧偏移 11）** 就是开关。**【推断】** `1` 表示「屏幕处于系统信息页 / 可推送状态」。这是网页端唯一能感知「屏幕当前是哪一页」的信号，与 §2.3 的结论互相印证。

> 对 MK87：第 2 层不成立（`isShowTftInfo` 缺省），所以**网页驱动全程不会推 CPU/GPU/天气**，也不会启动这个 8s 轮询。要复现系统信息推送，可以手工调用 `setTftScreenInfo`（见 `scripts/tft_ref.js` 的 `buildScreenInfoPayload` / `temporaryCommandPacket`）。

### 3.4 `SET_TEMPORARY_COMMAND_DATA(52)` 的 24 字节布局

`YZ`（@0x1dbce7）：

```js
let t=new Uint8Array(24).fill(0);
t[6]=90, t[12]=i /*cpuUsage*/, t[13]=a&255 /*cpuTemp*/, t[14]=o /*gpuUsage*/, t[15]=s&255 /*gpuTemp*/,
t[16]=c&255 /*currentTemp*/, t[17]=l&255 /*maxTemp*/, t[18]=u&255 /*minTemp*/, t[19]=d /*weather*/, t[20]=f /*humidity*/;
await NX(e,{cmd:HX.SET_TEMPORARY_COMMAND_DATA,data:t,maxRetries:0,timeout:r===1?2e3:500});
```

| 偏移 | 值 |
|---|---|
| 0–5 | 0 |
| **6** | `0x5A`（魔数/类型标记） |
| 7–11 | 0 |
| 12 | CPU 占用 0–100 |
| 13 | CPU 温度，**有符号** `& 0xFF`（-127..127） |
| 14 | GPU 占用 0–100 |
| 15 | GPU 温度 int8 |
| 16 | 当前气温 int8 |
| 17 | 当日最高温 int8 |
| 18 | 当日最低温 int8 |
| 19 | 天气代码 0–23 |
| 20 | 湿度 0–100 |
| 21–23 | 0 |

报文：**主通道（MI_02，64 字节 report）**，`contentSize` 用 `NX` 默认的 **24**，所以头是 `AA 34 18 00 00 00 01 00`，24 字节数据从偏移 8 开始，后面补 0 到 64。`maxRetries:0`、超时 500ms（`frameVersion===1` 时 2000ms）。

---

## 4. 壁纸 / 动画上传与 ACK（问题 3）

### 4.1 帧层（`PX`/`NX`，`docs/infra.js` 与 @0x1d2aa1 / @0x1d2507）

```
请求：AA cmd lenLo addrLo addrHi hdr5 last hdr7 | data...
响应：55 cmd lenOrType addrLo addrHi 0 0 1        | data...
```

- `len` = **本包数据字节数**（`NX` 里 `w = 最后一包 ? 剩余 : 每包容量`）；
- `last` = 1 表示最后一包（有自定义头时该位置被自定义头覆盖）；
- `NX` 每包都 `IX()` 等 input report 且 `cmd === responseCmd`（默认 = 本命令），超时 `timeout`，重发 `maxRetries` 次；
- TFT 通道每包容量 = `reportCount - 8`，`reportCount = collections[0].outputReports[0].items[0].reportCount || 4104` → **4104 − 8 = 4096 字节/包**。

### 4.2 壁纸 `KZ` = `setTftMaterial`（@0x1db570）

```js
let s=(o?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||4104)-8, c=Math.ceil(n.length/s);
for(let e=0;e<c;e++){ let t=e*s, i=new Uint8Array(s).fill(0); i.set(n.subarray(t,Math.min(t+s,n.length)));
  let l=new Uint8Array(8).fill(0);
  l[0]=170,l[1]=HX.SET_TFT_MATERIAL,l[2]=e&255,l[3]=e>>8&255,l[4]=c&255,l[5]=c>>8&255,l[6]=r&255,l[7]=r>>8&255;
  await NX(o,{cmd:HX.SET_TFT_MATERIAL,contentSize:s,data:i,headerCount:l.length,customHeader:l,timeout:2e3});
  if(a) a(Math.min(Math.floor((e+1)/c*100),99)) }
return!0
```

- `materialId = 0`（网页端唯一用的 id），**小端**放 `[6..7]`；
- 240×135×2 = **64800 字节 → 16 包**（末包有效 3360 字节 + 736 字节零填充）；
- **每包都等 `cmd=0x4D` 的响应**，`timeout:2000`，`maxRetries` 用默认 **3**（即首包 + 3 次重发，共 4 次尝试，最坏 8s/包）；
- 失败处理：`NX` 内部 `console.error` → 关设备、`device.forget()`、`historyConnect={}`、`location.pathname!=='/'` 时跳首页，并 `Promise.reject([])`；`KZ` 的 `catch` 把 `false` 返回给页面 → `$message.error($('screen_text14'))`。
- 成功后**没有**任何「刷新/生效」命令：写进去就是当前壁纸。

### 4.3 动画 `GZ` = `setTftUserAnimation`（@0x1db167）

```js
let n=MV(r) /*256B 延时表*/, o=new Uint8Array(n.length+i.length); o.set(n,0),o.set(i,n.length);
let c=(s?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||4104)-8, l=Math.ceil(o.length/c);
for(let e=0;e<l;e++){ ... let i=new Uint8Array(8).fill(0);
  i[0]=170,i[1]=HX.SET_TFT_USER_ANIMATION,i[2]=e&255,i[3]=e>>8&255,i[4]=l&255,i[5]=l>>8&255,i[6]=80,i[7]=6;
  await NX(s,{cmd:HX.SET_TFT_USER_ANIMATION,contentSize:c,data:t,headerCount:i.length,customHeader:i,
               timeout:2e3,responseCmd:HX.SET_LED_USER_ANIMATION});   // ← ACK 是 0x41
  if(a) a(Math.min(Math.floor((e+1)/l*100),99)) }
```

- 头 8 字节：`AA 50 seqLo seqHi totalLo totalHi 50 06`（`[6]=0x50`、`[7]=0x06` 是**字面常量**，含义无文档）；
- 数据 = `MV(delays)` 256 字节 + 各帧 RGB565 连续拼接；
- **ACK 命令字是 65 / 0x41（`SET_LED_USER_ANIMATION`）**，`timeout:2000`，`maxRetries` 默认 3；
- 140 帧 = 256 + 140×64800 = **9,072,256 字节 → 2215 包**；
- 同样：成功后没有额外生效命令；进度回调 0–99，页面收到成功后把进度设 100、延迟 500ms 关框弹成功提示。
  **【推断】** 上传完即可见（固件把它当作「用户动画」内容直接播）；若固件当时停在其它内置页，网页端也无命令把它切回来 —— 这正是 §2.3 里那个「网页端不知道当前页」的盲区。

### 4.4 页面侧的完整交互（`Z9()`，@0x31c260）

```
点击「保存」saveGif(le)
 ├─ 若 帧数 > tftMaxFrames → 确认框（"最多 N 帧"）取消则中止
 ├─ 若 builtInCount>1 → setTftBuiltInIndex(currentBuiltIn)   （MK87 跳过）
 ├─ 显示进度对话框
 ├─ for n in 0..min(frames, tftMaxFrames)-1:
 │    load Image(dataUrl) → canvas 240x135 → ctx.getImageData → 逐像素 AV/jV → 按 tftColorByteOrder push
 ├─ delays = frameData.slice(0,n).map(f=>f.delay)
 ├─ pixels = NV(全部帧字节, 240,135, tftConfig.dataTransform)
 └─ setTftUserAnimation(delays, pixels)  → 逐包上传 + 等 0x41
```

「上传壁纸」`uploadWallpaper(I)`：帧数必须为 1（否则 `$message.warning('壁纸只支持一帧图片')`）→ 同一套 canvas 编码（但直接 `LV('image',[{pixels}], byteOrder)`）→ `setTftMaterial(0, data)`。

> 注意：MK87 的 `tftConfig.materialIds` 不存在，所以**按钮根本不渲染**，壁纸接口在 UI 上不可达（协议函数仍在）。

---

## 5. GIF 处理（问题 4）

### 5.1 解析器是 omggif，不是 gifuct

**【代码】** `Q6()`（@0x20c214）用 `J6.GifReader`（`numFrames() / frameInfo(i) / decodeAndBlitFrameRGBA`）；预览写回用 `J6.GifWriter`（`e8()` @0x20cba1）。`GifReader/GifWriter` 是 **omggif** 的 API。bundle 里 **没有** `gifuct` / `decompressFrames` 字样。

```js
async function Q6(e,t,n,r=!0){ let i=await e.arrayBuffer(),a=new Uint8Array(i),o=new J6.GifReader(a),s=o.numFrames();
  ... 4 个 canvas：u/d=当前帧, m/h=合成, g/_=黑底, v/y=回滚保存 ...
  r&&(_.fillStyle=`#000000`,_.fillRect(0,0,c,l)), h.drawImage(g,0,0);
  let b=Math.min(t/c,n/l),x=Math.round(c*b),S=Math.round(l*b),C=Math.floor((t-x)/2),w=Math.floor((n-S)/2),T=[];
  for(let e=0;e<s;e++){ let i=o.frameInfo(e); let a=i.x||0,s=i.y||0,g=i.width||c,_=i.height||l;
    d.clearRect(0,0,c,l); let b=d.createImageData(c,l);
    o.decodeAndBlitFrameRGBA(e,b.data), d.putImageData(b,0,0);
    switch(i.disposal){ case 0:case 1: h.drawImage(u,a,s,g,_,a,s,g,_); break;
                        case 2: h.drawImage(u,a,s,g,_,a,s,g,_); break;
                        case 3: h.drawImage(u,a,s,g,_,a,s,g,_); break;
                        default: console.warn(`未知的 disposal 方法: ${i.disposal}, 按照方法 1 处理`), h.drawImage(u,a,s,g,_,a,s,g,_) }
    p.clearRect(0,0,t,n), r&&(p.fillStyle=`#000000`,p.fillRect(0,0,t,n)), p.drawImage(m,0,0,c,l,C,w,x,S);
    let E=f.toDataURL(`image/png`);
    E&&E.startsWith(`data:image/png`)&&T.push({dataUrl:E,delay:Math.max(i.delay||10,1)});
    i.disposal===2 ? (h.clearRect(a,s,g,_), r&&(h.fillStyle=`#000000`,h.fillRect(a,s,g,_)))
    : i.disposal===3 ? (h.clearRect(0,0,c,l), h.drawImage(v,0,0))
    : (y.clearRect(0,0,c,l), y.drawImage(m,0,0)) }
  return {frameData:T,frames:T.length,width:c,height:l} }
```

细节（逐条对应代码）：

1. **disposal 处理**：四个分支做的事**完全一样**（都是 `h.drawImage(u, a,s,g,_, a,s,g,_)`，把当前帧矩形叠到合成画布 `m`），真正的差别在**每帧末尾**：
   - `disposal===2` → 把该矩形清成黑色（若需要黑底）；
   - `disposal===3` → 用保存画布 `v` 整屏回滚（`v` 在上一帧末由 `m` 复制）；
   - 其它（0/1/未知）→ 把 `m` 存进 `v`（供下一帧 disposal 3 用）。
   - 注意 `switch` 里 `case 0/1/2/3` 都有 `break`，`default` 是告警后按 1 处理 —— 也就是说这个 `switch` 是**冗余**的（原库改成 omggif 时留下的痕迹），行为不变。
2. **每帧输出**：先把合成画布 `m`（原始 GIF 尺寸 c×l）按 `min(t/c, n/l)` **等比缩放 + 居中**画到 240×135，可选项 `r` 先铺黑底（页面调用时传 `!0`，所以**有黑边**），再 `toDataURL('image/png')` 存成 dataURL。
3. **帧延时**：`delay = Math.max(i.delay||10, 1)`，单位是 omggif 的 **厘秒（1/100 s = 10ms）**；缺省 10（=100ms）。**静图分支** `$6`（@0x20c8e5）固定 `delay:100`（=1s）。
4. **帧数上限**：导入时不裁剪；`saveGif` 时才 `Math.min(frameData.length, tftMaxFrames)`，超限先弹确认框 `screen_text11 + tftMaxFrames + screen_text12`。
5. **导入尺寸限制**：`BV()` 读宽高，任一边 > 2000 → `$message.error($('led_text59',[2000]))`。
6. **视频导入**：ffmpeg.wasm（worker `/assets/worker-A4ZT02e5.js`）`convertVideoToGif(file,{fps:10,maxDuration:30,maxWidth:480})`，滤镜 `fps=N,scale='min(480,iw)':-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse`，`-loop 0`；转出的 GIF 再走一遍 `Q6`。
7. **`tui-image-editor` 的作用**：**逐帧编辑器**（不改编码）。@0x31ce8b 初始化：

```js
b.value=new ahe.default(x.value,{includeUI:{loadImage:{path:f.value.frameData[h.value].dataUrl,name:`frame`},
  menu:[`crop`,`flip`,`rotate`,`draw`,`shape`,`icon`,`text`,`filter`],initMenu:`filter`,
  uiSize:{width:`1000px`,height:`600px`},menuBarPosition:`bottom`,theme:j,locale:ohe(i.locale)},
  cssMaxWidth:1e3,cssMaxHeight:600,usageStatistics:!1})
```

   - 劫持了 `removeActiveObject` → 变成「删除当前帧」（≤1 帧时拒绝，否则确认后 splice 并写库）；
   - 劫持 `.tui-image-editor-download-btn` 的 click（捕获阶段 `stopImmediatePropagation`）→ 走自己的 `F()`：`toDataURL()` → 按 `min` 等比缩放居中画到 240×135 **黑底** canvas → 写回 `frameData[h].dataUrl` 并落库；
   - 切帧/换语言会把编辑器 destroy 再重建（`P()`/`ne()`）。
8. **导入/导出格式**：动画库是 localforage 里的一个数组，键 **`gif_files_${tftConfig.localforageKey}` = `gif_files_w240h135`**（`tftDirection===1` 时 `gif_files_w135h240`）。元素结构：

```json
{ "width": 240, "height": 135, "frames": 3,
  "frameData": [ { "dataUrl": "data:image/png;base64,...", "delay": 10 }, ... ] }
```

   - 导出（`ve()` → `DV(item,'defaultGif')`，@0xf68a4）：`JSON.stringify(item,null,2)` 存成 **`defaultGif.json`**；
   - 导入分享/社区：`/api/common/upload`（`F6`）→ `/api/fileinfo/add`（`I6`，`type:3`, `device_id:32839`, `device_model:'AJAZZ KEYBOARD'`）；社区下载回来时把 `{height,width,frames,frameData}` push 进同一个 `gif_files_*` 数组（@0x20e4ed）；
   - 默认动画：`/gif/AK980_PRO/defaultGif.json`（`defaultAnimationCount>1` 时还有 `defaultGif2.json…`）。
9. **预览**：`oe()` → `e8(frameData.map(delay), 240,135, ...)` 用 `GifWriter` 重新合成 GIF（限 256 色调色板），`gif.js` 风格的 `{delay: t[i]||10, disposal:2}` —— 这里 delay 直接当**厘秒**写入，再次印证单位是 10ms。

---

## 6. RGB565 字节序与 `NV`（问题 5）

**【代码】** 编码四件套（@0xf6cc5 / 0xf6cf2 / 0xf6f32 / 0xf6f70）：

```js
AV=e=>(e.r&248)<<8|(e.g&252)<<3|(e.b&248)>>3          // RGB565 数值
jV=e=>[e>>8&255,e&255]                                // -> [hi, lo]
PV=(e,t,n,r,i=0)=>{ i===1?(e[t]=n,e[t+1]=r):(e[t]=r,e[t+1]=n) }   // i=tftColorByteOrder
FV=(e,t=0)=>{ ... [a,o]=jV(AV({r,g,b})); PV(r,i*2,a,o,t) }        // 2 字节/像素
```

| `tftColorByteOrder` | 每像素写入顺序 | 例：纯红 `0xF800` | 例：纯绿 `0x07E0` |
|---|---|---|---|
| `0`（MK87 实测） | **小端**：`[lo, hi]` | `00 F8` | `E0 07` |
| `1` | **大端**：`[hi, lo]` | `F8 00` | `07 E0` |

`NV()`（@0xf6d89）——旋转/翻转：

```js
NV=(e,t,n,r)=>{ let i=r?.rotate??0,a=!!r?.flip; if(i===0&&!a)return e;
  let o=t*n*2; if(!o||e.length%o!==0) return console.warn(`TFT 数据长度与分辨率不匹配，跳过旋转/翻转`),e;
  let s=i===90||i===270?n:t, c=Array(e.length);
  for(let r=0;r<e.length;r+=o) for(let o=0;o<n;o++) for(let l=0;l<t;l++){
    let u=l,d=o;
    i===90?(u=n-1-o,d=l):i===180?(u=t-1-l,d=n-1-o):i===270&&(u=o,d=t-1-l);
    a&&(u=s-1-u);
    let f=r+(o*t+l)*2, p=r+(d*s+u)*2; c[p]=e[f],c[p+1]=e[f+1] } return c }
```

- 参数是 `(数据, 宽, 高, {rotate,flip})`，**作用在已编码的 RGB565 字节上**，以 **2 字节为像素单位**整块搬运 → **与字节序无关**（先编码再旋转，字节对整体搬家，顺序不变）。
- 旋转后目标宽 `s = (90||270) ? 高 : 宽`；`flip` 在**目标坐标系**做 `u = s-1-u`（水平镜像）。
- 可以对**整段多帧数据**一次调用（按 `宽*高*2` 分块循环）；长度不整除时告警并**原样返回**。
- 调用顺序（页面 @0x31e3d9）：**逐帧编码 → 全部帧拼成一个数组 → `NV()` → `setTftUserAnimation()`（内部才拼 `MV` 延时表）**。所以延时表永远在旋转之后、且不参与旋转。

---

## 7. 屏幕时间（问题 6）

`JZ` = `setTftDateTime`（@0x1dbac7）：

```js
let t=new Date(i); if(isNaN(t.getTime())) return ...;
if(a<0||a>6) return ...;
let n=new Uint8Array(10).fill(0);
n[0]=90,n[1]=1,n[2]=90,n[3]=t.getFullYear()%100,n[4]=t.getMonth()+1,n[5]=t.getDate(),
n[6]=t.getHours(),n[7]=t.getMinutes(),n[8]=t.getSeconds(),n[9]=a;
await NX(e,{cmd:HX.SET_TEMPORARY_COMMAND_DATA,data:n,timeout:r===1?2e3:500});
```

| 偏移 | 含义 |
|---|---|
| 0–2 | `5A 01 5A`（固定头） |
| 3 | 年 `% 100`（如 2026 → 26） |
| 4 | 月 **1–12** |
| 5 | 日 |
| 6 | 时（0–23，**本地时间**） |
| 7 | 分 |
| 8 | 秒 |
| 9 | 星期：`dayjs().day()`，**0=周日** … 6=周六 |

- **没有时区字段**：页面直接把本地时间字符串 `dayjs().format('YYYY-MM-DD HH:mm:ss')` 传进来，取的是浏览器本地时间；设备侧按「本地时间」理解。
- 报文：主通道 64 字节，`contentSize` 走 `NX` 默认 **24**（数据只有 10 字节，18..63 补 0）。
- 调用点两处：TFT 页「时间校准」按钮 `_e()`（@0x31f1ef），以及**设备连接后自动同步**（@0x1ed0e7）：

```js
let D=async(e,t)=>{ if(e.ledConfig?.isShowTimeCalibration){...setLedDateTime...}
  if(e.tftConfig&&!e.tftConfig.hideScreenTimeCalibration&&t?.tftDirection!==255){
    let e=dayjs().format(`YYYY-MM-DD HH:mm:ss`),t=dayjs().day(); await i(`setTftDateTime`,void 0,e,t) } }
```

→ MK87（无 `hideScreenTimeCalibration`、`tftDirection=0`）**每次连接都会自动对时一次**。

---

## 8. 其它屏幕相关（问题 7）

| 项 | 结论 | 证据 |
|---|---|---|
| 屏幕亮度 | **网页端没有 TFT 亮度命令**（`brightness` 只属于灯效 `setLedEffect`） | 全 bundle 无 tft 亮度 |
| 息屏 / 显示时间 | `gameMode.tftDisplayTime`，`SET_GAME_MODE(33)` payload **偏移 7**；UI 是 0/1 二值（`time_1`/`time_2`），受 `settingsConfig.isShowTftTimeMode` 控制；MK87 该项隐藏（但保存其它设置时会把现有值原样回写） | @0x2621xx、@0x264793 |
| 屏幕方向 | 只由 `deviceInfo.tftDirection` 决定：`0` 横屏；`1` 竖屏（页面宽高互换、存储键 `w135h240`）；`255` 无屏（路由剔除 `tft`） | @0x31c2xx |
| 屏保 | 除 `tftDisplayTime` 外无其它屏保配置 | — |
| 时间显示开关 | `settingsConfig.isShowTftTimeMode` 只影响 UI 是否出现「TFT 显示时间」开关，不额外发命令 | @0x264793 |
| 游戏模式 `systemMode` | payload 偏移 6，UI 从不修改，原值回写 | @0x1d44fb / @0x1d46e1 |
| 社区/分享 | 仅当 `communityConfig.communityList` 含 `tft` 时显示分享按钮；MK87 无 `communityConfig` → 不显示 | @0x320421 |

---

## 9. 交付物与自检

### 9.1 `scripts/tft_ref.js`

逐字节等价实现了：

| 官方 | 参考实现 | 说明 |
|---|---|---|
| `AV` | `rgb565(r,g,b)` | `(r&0xF8)<<8 \| (g&0xFC)<<3 \| (b&0xF8)>>3` |
| `jV` | `split565(v)` | → `[hi, lo]` |
| `PV` | `putPixel(buf,off,hi,lo,byteOrder)` | 0=小端 / 1=大端 |
| `FV` | `encodeRgba565(rgba, byteOrder)` | 2 字节/像素 |
| `IV` | `encodeRgba565Alpha(rgba, byteOrder)` | 5 字节/2 像素 + alpha 半字节 |
| `MV` | `buildDelayTable(delays)` | 256 字节，末帧槽 = 0 |
| `NV` | `transform565(data,w,h,{rotate,flip})` | 2 字节像素搬运 |
| `LV` | `encodeLV(type, frames, byteOrder)` | gif 前缀延时表 / image 只取首帧 |
| `PX` | `buildFrame({...})` | 含 customHeader 早返回语义 |
| `KZ` | `tftMaterialPackets(materialId, data)` | 16 包/整屏，头 `AA 4D …` |
| `GZ` | `tftAnimationPackets(delays, pixels)` | 头 `AA 50 … 50 06` |
| `qZ` | `tftBuiltInIndexPacket(index)` | 4104 字节只带 1 字节数据 |
| `JZ` | `buildTimePayload(date, weekday)` + `temporaryCommandPacket` | 10 字节 + 24 的 contentSize |
| `YZ` | `buildScreenInfoPayload(info)` | 24 字节布局 |

运行：

```powershell
& "C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe" `
  C:\Users\ptfm\Documents\ajazz-re\scripts\tft_ref.js --demo
```

自检覆盖：2×2 像素（红/绿/蓝/白，两种字节序）、`IV` alpha 打包（`00F8 E007 84`）、3 帧延时表（`03 32 64 00 FF…`）、`NV` 的 90/180/270/flip 与「4×90° 复原」、整屏 16 包与末包零填充、3 帧动画 48 包与首包头/首包延时表、内置索引/时间/系统信息报文逐字节、`LV` 与页面内联编码一致性。全部通过。

### 9.2 `docs/tft-constants.json`

从 bundle 抽出的常量表：机型配置、deviceInfo 偏移、5 条命令（含 ACK 与超时/重发）、帧格式、像素编码、天气 OWM→设备码映射表、IP 定位链、8s 轮询与本机服务端点、UI/i18n 键、存储键与 JSON schema、分享 API、gameMode 偏移、视频转 GIF 参数、以及 `uncertain` 清单。

### 9.3 复现脚本（本次新增）

| 文件 | 作用 |
|---|---|
| `scripts/tft_grep.js` | 按正则定位并打印 offset + 上下文（`node tft_grep.js <bundle> <regex> [min] [max] [ctx]`） |
| `scripts/tft_fn.js` | 按锚点（如 `HY=`、`async function Q6`）用括号/字符串/模板感知配对切出一个定义并美化 |
| `scripts/tft_slice.js` | 按偏移切区间并美化（长行自动折行） |

---

## 10. 天气代码表（`MY()` 完整映射）

| 设备码 | OWM condition id | 含义 |
|---|---|---|
| 0 | 800 | 晴 |
| 1 | 801, 802；**默认值** | 少云/晴间多云 |
| 2 | 803, 804 | 多云/阴 |
| 3 | 300–321 | 毛毛雨 |
| 4 | 500, 501 | 小雨 |
| 5 | 502, 503, 504 | 大雨/暴雨 |
| 6 | 520, 521 | 小阵雨 |
| 7 | 522–531 | 强阵雨 |
| 9 | 200–232 | 雷暴 |
| 10 | 701, 741 | 薄雾/雾 |
| 11 | 711, 721 | 烟/霾 |
| 13 | 511 | 冻雨 |
| 14 | 761 | 尘 |
| 15 | 731, 751 | 沙尘 |
| 16 | 762, 781 | 火山灰/龙卷 |
| 18 | 600 | 小雪 |
| 19 | 601 | 中雪 |
| 20 | 602 | 大雪 |
| 21 | 620–622 | 阵雪 |
| 23 | 611, 612, 613, 615, 616 | 雨夹雪/冻雨夹雪 |
| — | 8, 12, 17, 22 | **未被 `MY` 使用** |

---

## 11. 仍未确定的问题

1. **内置页 index 的语义**：bundle 里没有 index → 页面名的映射；`builtInCount` 在本 bundle 的任何机型配置里都不存在，所以选择器是**死代码**。哪个 index 对应时钟/天气/CPU 页，只能靠真机逐个试。
2. **动画头 `[6]=0x50, [7]=0x06`** 的含义（`0x50` 恰为命令字，`6` 疑为格式/类型）——无注释、无第二处用法。
3. **`GET_DEVICE_NOTIFY 0xFA / type=6 / data[3]===1`** 的确切语义（推断为「屏幕处于系统信息页」），以及 type=6 的其余字节含义。
4. **设备是否真的对 0x4D / 0x41 回 ACK**：官方逻辑强依赖 ACK（无 ACK 会 4 次尝试后 `forget` 设备）。真机上如果固件不回，官方网页驱动本身也会失败；自研驱动建议「发了就不等」或把超时压到很小。
5. **`tftDisplayTime` 的单位/语义**（0/1 二值，实际是「常亮/自动息屏」还是分钟数）——UI 只有两个选项，没有更多线索。
6. **`IV`（alpha 编码）在 TFT 路径上不可达**：`LV` 只被 `LV('image', …)` 调用一次，`gif_alpha`/`image_alpha` 分支在本 bundle 中无调用者（可能供其它机型/灯效动画使用）。其公式已按代码还原并经自检。
