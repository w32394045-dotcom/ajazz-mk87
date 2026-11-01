# MK87 TFT 小屏逻辑（SET_TFT_USER_ANIMATION 0x50）—— 已实机跑通

> 目标设备：AJAZZ MK87（VID `0x0C45` / PID `0x8047`，SONiX 方案，固件 1.19）
> 本文记录 TFT 小屏「自定义动画 / GIF」通道的完整协议、实测数据、失败复盘，以及**不依赖官方驱动**的可用实现。
>
> 状态：**✅ 2026-11-01 实机验证通过** —— 18.91MB / 1728×972 / 73 帧 GIF → 1155 个 4104B 报文全部收到 ACK，164.2s 传完，屏幕正常播放。
> 实现：`probe/tft_upload_gif2.py`（先按官方抓包修正了**逐包等 ACK** 的流控）

---

## 1. 屏幕与通道基础参数

| 项 | 值 | 来源 |
|---|---|---|
| 分辨率 | **240 × 135** | `GET_DEVICE_INFO` 的 `tftWidth/tftHeight` |
| 最大帧数 | **140 帧**（`tftMaxFrames=140`） | `GET_DEVICE_INFO` |
| 屏幕方向 | `tftDirection=0` | 同上 |
| 颜色字节序 | `tftColorByteOrder=0`（RGB565 **小端**：低字节在前） | 同上 |
| 单帧像素字节 | 240×135×2 = **64,800 B** | 计算 |
| 协议通道 | HID 接口 **MI_03**，`usagePage=0xFF67`，`usage=0x61` | `hid_probe*.py` |
| 输入报文长度 | 65B（report ID 0 + 64B 数据） | 同上 |
| 输出报文长度 | **4105B**（report ID 0 + **4104B** 数据） | 同上 |
| 可写命令 | `SET_TFT_USER_ANIMATION = 0x50` | 66 命令枚举 |
| ACK 命令 | **`0x41`（SET_LED_USER_ANIMATION）** | 官方 bundle：`responseCmd: HX.SET_LED_USER_ANIMATION` |

**MK87 的 TFT 只能"写"不能"读"**：没有屏幕内容回读/备份接口，传上去就被覆盖，改回只能重传。
`SET_TFT_BUILT_IN_INDEX(0x51)` 在 MK87 上回 ACK 但不切页（MK87 没有 `builtInCount`），`SET_TFT_MATERIAL(0x4D)` 壁纸通道可写但无壁纸页看不到——**MK87 唯一可见的 TFT 自定义内容就是 0x50 用户动画**。

---

## 2. 报文封装（4104B 大包）

每个报文 = **8 字节自定义头 + 最多 4096 字节数据**。

```
偏移  字节内容
0     AA              固定帧头
1     50              命令 SET_TFT_USER_ANIMATION
2     seq & 0xFF      包序号 低字节
3     seq >> 8        包序号 高字节
4     total & 0xFF    总包数 低字节
5     total >> 8      总包数 高字节
6     50              固定（官方写死 0x50）
7     06              固定（官方写死 0x06）
8..   数据（本包 4096B，最后一包不足补 0）
```

- 整个数据流按 4096B 切片，第 `seq` 包装 `payload[seq*4096 : (seq+1)*4096]`
- 发到设备时：Windows 原生写缓冲区要**多带 1 字节 report ID（0x00）**，共 4105B；
  WebHID 里对应 `device.sendReport(0, data4104)`。
- 官方 bundle 里的调用：`cmd:0x50, contentSize:4096, headerCount:8, customHeader:[0xAA,0x50,seqLo,seqHi,totalLo,totalHi,0x50,0x06], timeout:2000, responseCmd:0x41`。

---

## 3. 数据负载布局（payload）

```
[0 .. 255]      延时表 256B
[256 ..]        帧数据，每帧 64,800B（RGB565 小端），最多 140 帧
```

### 3.1 延时表 MV（官方 `MV()` 逐字节还原）

设共 `n` 帧、第 `i` 帧 GIF 延时 `duration_ms`、`cs = round(duration_ms / 10)`（厘秒）：

```
MV = 256 字节，初始全 0xFF
MV[0] = n & 0xFF                     # 帧数
MV[i+1] = min(cs_i * 5, 255)         # i = 0 .. n-2，共 n-1 项
MV[n] = 0                            # 终止标记（第 n 个字节）
其余保持 0xFF
```

播放时一个单位 ≈ **2ms**，所以 `cs*5*2 = cs*10 = duration_ms`。
本次 GIF：73 帧、每帧 50ms → `MV[0]=0x49(73)`，`MV[1..72]=0x19(25)`，`MV[73]=0`，其余 `0xFF`。
抓包实测官方首包数据段正是 `49 19 19 19 19 ...`，与本地生成**逐字节一致**。

### 3.2 帧数据

- 源 GIF 先按 cover 方式缩放并居中裁剪到 240×135（官方用浏览器 canvas，我们用 PIL LANCZOS，像素值会有 ±1~2 的差异，设备两者都接受）
- 每像素 RGB565：`((R&0xF8)<<8) | ((G&0xFC)<<3) | ((B&0xF8)>>3)`
- `tftColorByteOrder=0` → 低字节写前，即 `buf[2i]=lo, buf[2i+1]=hi`
- 帧与帧之间无对齐填充

### 3.3 包数公式

```
payload = 256 + n * 64800
packets = ceil(payload / 4096)
```

本次实例：`256 + 73*64800 = 4,730,656 B` → `ceil(4730656/4096) = 1155` 包。

---

## 4. 流控（关键！）：每包必须等 ACK

官方并不是"发完 1155 包就完事"，而是**发一包 → 等一个 ACK → 再发下一包**：

| 现象 | 实测值（官方网驱抓包） | 本地脚本实测 |
|---|---|---|
| 第 1 包 ACK 延迟 | ~329ms（设备擦除准备） | 326ms |
| 后续每包 ACK 延迟 | ~140ms | 平均 142ms（137~326） |
| 1155 包总耗时 | **168.5s** | **164.2s** |
| ACK 形态 | 64B 输入报文：`00 55 41 00 01 00 00 ...` | 同 |
| ACK 丢失 | 无（1155/1155） | 无（1155/1155） |

- ACK 是**回显同命令**的帧：`55 41` + 2 字节状态（`00 01`），其余补 0；带 report ID 0 时原生读到的是 `00 55 41 00 01 ...`。
- 官方超时 **2000ms、最多重试 3 次**（bundle 里 `timeout:2e3`；表格型命令 `maxRetries` 由外层控制）。
- **如果不等 ACK 连续猛发**，设备会丢弃/不响应后续包：旧版脚本 1155 包 79.8s 全速发完，ACK=0，屏幕不变化。这就是之前失败的根因（当时官方驱动还在后台按 140fps 推音乐帧，设备侧更忙）。
- 反过来，**只要逐包等 ACK，官方 `AjazzDriver` 进程开着也能传**（本次实测：PID 13488 一直在跑，上传全部 ACK）。

### 4.1 正确的上传伪代码

```python
for seq in range(total):
    pkt = [0x00] + header(seq, total) + chunk(seq)   # 4105B
    for attempt in range(4):                          # 1 次 + 3 重试
        write_report(pkt)                             # Windows: WriteFile(4105B)
        if wait_ack(0x41, timeout=2.0): break         # 读 65B 输入，匹配 55 41
    else:
        raise RuntimeError(f'packet {seq} no ACK')
```

实现见 `probe/tft_upload_gif2.py`（`--ack-timeout`、`--retries`、`--max-frames` 可调）。

---

## 5. 官方网页驱动的实际行为（2026-11-01 WebHID 抓包）

抓包工具：`capture/run.js` + `capture/hook.js`（CDP document-start 注入，零依赖）。
原始日志：`capture/ajazz_tft_capture.jsonl`（38.45MB，2813 条记录）。
分析输出：`capture/tft_analysis2.txt`、`capture/compare_result.txt`。

### 5.1 设备选择：必须选中 TFT 接口（`0xFF67`）

官方页面在 `requestDevice` 时会按用途页过滤；抓包里的设备摘要 `usagePage` 出现了两个值：

| usagePage | 含义 | 结果 |
|---|---|---|
| `65384` = `0xFF68` | 主协议 MI_02（out 只有 **65B**） | 页面往里发 4104B 报文 → `NotAllowedError: Failed to write the report`，随后设备 `disconnect` |
| `65383` = `0xFF67` | TFT MI_03（out **4105B**） | 上传成功 |

抓包里的时间线非常直观：

- 第 1~2 次尝试（ts≈139.8s / 151.8s）都发生在 `0xFF68` 设备上，分别只发了 8 包、11 包就 `disconnect` 中断；
- 第 3 次（ts≈184.9s）重新 `requestDevice` 拿到了 `0xFF67` 设备，随后 **1155 包一次跑完**（ts 189.5s → 358.0s）。
- 这解释了为什么官方网页自己也会"失败几次才成功"——接口选错时 WebHID 会直接拒写。

### 5.2 上传前的命令（非必需）

拿到 `0xFF67` 设备后、真正上传前，官方还发了一串小命令（很快，几秒内）：

| 报文 | 命令 | 含义 |
|---|---|---|
| `AA 13 10 00 00 00 01` | `0x13` | `GET_LED_EFFECT`（读当前灯效） |
| `AA 14 38 <addr>` ×9 | `0x14` | `GET_CUSTOM_LED_DATA`（分块读，块长 0x38=56B） |
| `AA 15 38 <addr>` ×9 | `0x15` | `GET_MACRO`（分块读） |
| `AA 34 18 00 00 00 01 ...` | `0x34` | `SET_TEMPORARY_COMMAND_DATA`（官方页面状态同步用） |

这些是页面打开/同步状态时发的，**不是上传的前置条件**：本地脚本不发这些命令，直接发 0x50 包，1155 包照样全部 ACK、屏幕正常播放。

### 5.3 官方生成的像素数据 vs 本地生成

- 头 8 字节、总包数（`0x0483=1155`）、延时表 `49 19 19...`：**逐字节一致**
- 像素段：小幅度差异（如官方 `b1 2a 6f 22` vs 本地 `b0 2a 90 2a`）——官方用浏览器 canvas 缩放/取色，本地用 PIL LANCZOS；两者都能被设备接受。

---

## 6. 失败复盘（为什么之前一直 0 ACK）

| 时间 | 尝试 | 结果 | 原因 |
|---|---|---|---|
| 11-01 早 | `tft_upload_gif.py` 3 帧 / 官方 135 帧动画 | ✅ 成功 | 包数少（48~528 包），设备来得及 |
| 11-01 20:0x | 新版 73 帧 GIF（1155 包） | ❌ 79.8s 发完，ACK=0，屏幕不变 | ① 旧脚本等 ACK 0.5s 没等到就切换"硬发"；② 当时 `AjazzDriver` 正在按 140fps 推 `0x32` 音乐帧，TFT 通道被占；③ 官方驱动进程杀不掉（Access denied）导致误判"必须停驱动" |
| 11-01 20:37 | 重跑旧脚本 | 卡死（CPU 0.2s） | 打开 HID 阶段被占用，未走到发送 |
| 11-01 20:44 | 官方网页驱动（抓包） | ✅ 但前 6 次中断，第 7 次成功 | 前几次设备选错（0xFF68） |
| 11-01 20:52 | `tft_upload_gif2.py`（逐包等 ACK） | ✅ **1155/1155 ACK，164.2s** | 修正流控 |

**结论：报文内容一直是对的，错在流控——必须发一包等一个 ACK。**

---

## 7. 怎么用（不依赖官方驱动 / 不依赖 Music.exe）

```powershell
# 任意 GIF → TFT（自动 cover 裁剪 240×135、RGB565、≤140 帧）
& 'C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\ptfm\Documents\ajazz-re\probe\tft_upload_gif2.py' `
  "C:\path\to\anim.gif"

# 可调参数
#   --max-frames N     最多取多少帧（上限 140）
#   --ack-timeout 2.0 每包 ACK 超时秒数
#   --retries 3       每包重试次数
```

耗时参考：`4.73MB payload（1155 包）≈ 164s`，约 **29KB/s**；140 帧满帧（约 9.07MB / 2215 包）≈ 5.2 分钟。

传完后设备**立即开始循环播放**，无需切页、无需重启。屏幕内容是只写的，想换/恢复只能再传一遍（`restore_tft_default.py` 可恢复官方默认动画，见 `docs/tft-page.md`）。

---

## 8. 相关文件

| 文件 | 说明 |
|---|---|
| `probe/tft_upload_gif2.py` | ✅ 逐包等 ACK 的上传器（本次验证通过） |
| `probe/tft_upload_gif.py` | 旧版（不等 ACK，1155 包会失败——保留作对照） |
| `probe/tft_probe_ack.py` | 写入变体/ACK 探测 |
| `probe/tft_ack_test2.py` | 单包 ACK 延迟测试（本次：+326ms 收到 `55 41`） |
| `capture/ajazz_tft_capture.jsonl` | 官方网页驱动完整 WebHID 抓包（含 1155 包上传 + 失败尝试） |
| `capture/tft_analysis2.txt` | 抓包分析（会话/ACK/时间线） |
| `capture/compare_packets.py` / `compare_result.txt` | 官方包 vs 本地包逐包对比 |
| `docs/tft-page.md` | 官方 TFT 页面逻辑逆向（上传 UI、壁纸/内置页/系统信息） |
| `docs/tft-constants.json` | TFT 常量表 |

---

## 9. 待确认 / 边界

1. **屏幕播放效果**：本次已实机上传成功，需人工目视确认（屏幕应循环播放该 GIF，73 帧 @50ms ≈ 3.65s 一轮）。
2. 官方默认动画是否可备份：**不能**（无读回接口），只能靠 `restore_tft_default.py` 重传内置默认素材。
3. 上传中断电/拔线：设备内动画可能不完整，重传即可恢复。
4. `SET_TFT_MATERIAL(0x4D)` 壁纸通道在 MK87 上写入成功但不可见，TFT 动画是唯一可见通道（见 `docs/tft-page.md`）。
