#!/usr/bin/env node
/*
 * tft_ref.js — AJAZZ MK87 (VID 0x0C45 / PID 0x8047) TFT 屏幕数据编码与报文组装的
 *              独立参考实现，逐字节等价于官方网页驱动 bundle
 *              assets/layout-classic-CMxiG14P.js 中的 AV / jV / PV / FV / IV / MV / NV / LV
 *              以及协议函数 setTftMaterial(KZ) / setTftUserAnimation(GZ) /
 *              setTftBuiltInIndex(qZ) / setTftDateTime(JZ) / setTftScreenInfo(YZ)。
 *
 * 无依赖，只用 Node 内置模块。运行：
 *      node tft_ref.js            # 跑自检（默认）
 *      node tft_ref.js --demo     # 额外演示一份 240x135 壁纸与 3 帧动画的报文头
 *
 * 本文件不打开任何 HID 设备，只产出字节。
 *
 * 关键事实（与 bundle 对应）：
 *   AV: rgb565 = (r&0xF8)<<8 | (g&0xFC)<<3 | (b&0xF8)>>3
 *   jV: [hi, lo] = [v>>8 & 255, v & 255]
 *   PV(buf, off, hi, lo, byteOrder): byteOrder===1 -> [hi,lo]（大端），否则 [lo,hi]（小端）
 *   FV: RGBA -> RGB565, 2 字节/像素
 *   IV: RGBA -> 每 2 像素 5 字节 = RGB565(p0) + RGB565(p1) + alpha 字节
 *       alpha 字节 = (a0>>4)<<4 | (a1>>4)   （每个像素取高 4 位，凑不满 2 像素时低位为 0）
 *   MV: 256 字节延时表，[0]=帧数，[1..n-1]=min(delay*5,255)，[n]=0，其余 255
 *       —— 注意最后一帧的延时槽被写成 0（终止符），不携带延时
 *   NV: 旋转/翻转，作用于**已编码**的 RGB565 数据（2 字节为单位的像素搬运），
 *       因此与字节序无关；对整段多帧数据按帧块处理
 *   LV: gif/gif_alpha -> [MV(delays)] + 每帧编码；image/image_alpha -> 仅第一帧编码
 */

'use strict';

const assert = require('node:assert');

// ---------------------------------------------------------------------------
// 0. 常量
// ---------------------------------------------------------------------------

const CMD = {
  SET_TEMPORARY_COMMAND_DATA: 0x34, // 52  屏幕时间 / 系统信息（走主通道 MI_02）
  SET_LED_USER_ANIMATION: 0x41,     // 65  同时被当作 TFT 动画上传的 ACK 命令字
  SET_TFT_MATERIAL: 0x4d,           // 77  壁纸（走 TFT 通道 MI_03）
  SET_TFT_USER_ANIMATION: 0x50,     // 80  用户动画（走 TFT 通道 MI_03）
  SET_TFT_BUILT_IN_INDEX: 0x51,     // 81  内置页索引（走 TFT 通道 MI_03）
};

const TFT_REPORT_COUNT = 4104; // TFT 接口 output report payload（4105 含 report id）
const TFT_HEADER_COUNT = 8;    // 自定义头 8 字节
const MAIN_REPORT_COUNT = 64;  // 主接口 payload
const FRAME_W = 240;
const FRAME_H = 135;
const FRAME_BYTES = FRAME_W * FRAME_H * 2; // 64800
const DELAY_TABLE_LEN = 256;
const MAX_FRAMES = 140;        // deviceInfo.tftMaxFrames（实测 140）

// ---------------------------------------------------------------------------
// 1. 像素编码原语（与 bundle 逐字节一致）
// ---------------------------------------------------------------------------

/** AV：一个像素 -> 16 位 RGB565 数值（bit15..11=R，bit10..5=G，bit4..0=B） */
function rgb565(r, g, b) {
  return (((r & 0xf8) << 8) | ((g & 0xfc) << 3) | ((b & 0xf8) >> 3)) & 0xffff;
}

/** jV：16 位 -> [高字节, 低字节] */
function split565(v) {
  return [(v >> 8) & 0xff, v & 0xff];
}

/** PV：把 [hi, lo] 按字节序写入 buf[off..off+1]；byteOrder=1 为大端，其余为小端 */
function putPixel(buf, off, hi, lo, byteOrder = 0) {
  if (byteOrder === 1) {
    buf[off] = hi;
    buf[off + 1] = lo;
  } else {
    buf[off] = lo;
    buf[off + 1] = hi;
  }
}

/** FV：RGBA 缓冲 -> RGB565，长度 floor(len/4)*2 */
function encodeRgba565(pixels, byteOrder = 0) {
  const n = Math.floor(pixels.length / 4);
  const out = new Uint8Array(n * 2);
  for (let i = 0; i < n; i++) {
    const p = i * 4;
    const [hi, lo] = split565(rgb565(pixels[p], pixels[p + 1], pixels[p + 2]));
    putPixel(out, i * 2, hi, lo, byteOrder);
  }
  return out;
}

/**
 * IV：RGBA 缓冲 -> 「2 像素 5 字节」的带 alpha 编码
 *   [0..1] RGB565(p0)  [2..3] RGB565(p1)  [4] alpha 字节
 *   alpha 字节 = (a0 >> 4) << 4 | (a1 >> 4)
 * 奇数像素时最后一个 alpha 低 4 位为 0（循环 break 掉第二个像素）。
 */
function encodeRgba565Alpha(pixels, byteOrder = 0) {
  const n = Math.floor(pixels.length / 4);
  const pairs = Math.ceil(n / 2);
  const out = new Uint8Array(pairs * 5);
  for (let a = 0; a < pairs; a++) {
    const base = a * 5;
    let alphaByte = 0;
    for (let s = 0; s < 2; s++) {
      const idx = a * 2 + s;
      if (idx >= n) break;
      const p = idx * 4;
      const [hi, lo] = split565(rgb565(pixels[p], pixels[p + 1], pixels[p + 2]));
      putPixel(out, base + s * 2, hi, lo, byteOrder);
      alphaByte |= (pixels[p + 3] >> 4) << (s === 0 ? 4 : 0);
    }
    out[base + 4] = alphaByte;
  }
  return out;
}

/**
 * MV：帧延时表（256 字节）
 *   table[0] = 帧数 n
 *   table[1..n-1] = min(delay*5, 255)      （官方循环 for(r=0; r<n-1; r++)，最后一帧不写）
 *   table[n] = 0                            （终止符，覆盖最后一帧的延时槽）
 *   其余 = 255
 * delay 的单位是 GIF 的厘秒（10ms）；表内单位 = 2ms（即 delay_cs*5 = delay_ms/2）。
 */
function buildDelayTable(delays) {
  const n = delays.length;
  const t = new Uint8Array(DELAY_TABLE_LEN).fill(255);
  t[0] = n & 0xff;
  for (let i = 0; i < n - 1; i++) t[i + 1] = Math.min(delays[i] * 5, 255);
  t[n] = 0;
  return t;
}

/**
 * NV：旋转/翻转（在 RGB565 编码之后、按 2 字节像素搬运）
 *   transform = { rotate: 0|90|180|270, flip: boolean }
 * 返回新数组；当 rotate=0 且无 flip 时原样返回；长度不是 帧字节数 的整数倍时告警并原样返回。
 * 注意 destW：90/270 时目标宽 = 原高。
 */
function transform565(data, width, height, transform) {
  const rotate = (transform && transform.rotate) || 0;
  const flip = !!(transform && transform.flip);
  if (rotate === 0 && !flip) return data;
  const frameBytes = width * height * 2;
  if (!frameBytes || data.length % frameBytes !== 0) {
    console.warn('TFT 数据长度与分辨率不匹配，跳过旋转/翻转');
    return data;
  }
  const destW = rotate === 90 || rotate === 270 ? height : width;
  const out = new Uint8Array(data.length);
  for (let base = 0; base < data.length; base += frameBytes) {
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let u = x;
        let d = y;
        if (rotate === 90) {
          u = height - 1 - y;
          d = x;
        } else if (rotate === 180) {
          u = width - 1 - x;
          d = height - 1 - y;
        } else if (rotate === 270) {
          u = y;
          d = width - 1 - x;
        }
        if (flip) u = destW - 1 - u;
        const src = base + (y * width + x) * 2;
        const dst = base + (d * destW + u) * 2;
        out[dst] = data[src];
        out[dst + 1] = data[src + 1];
      }
    }
  }
  return out;
}

/**
 * LV：类型化入口
 *   type: 'image' | 'image_alpha' | 'gif' | 'gif_alpha'
 *   frames: [{ pixels: Uint8Array|number[] (RGBA), delay?: number(厘秒) }, ...]
 *   byteOrder: deviceInfo.tftColorByteOrder（0=小端，1=大端）
 * 返回：直接交给 setTftMaterial / setTftUserAnimation 的像素数据
 *   gif*   -> MV(delays) 前缀 + 各帧编码
 *   image* -> 只取第一帧，无延时表
 */
function encodeLV(type, frames, byteOrder = 0) {
  const isGif = type === 'gif' || type === 'gif_alpha';
  const encoder = type === 'gif_alpha' || type === 'image_alpha' ? encodeRgba565Alpha : encodeRgba565;
  const list = isGif ? frames : frames.slice(0, 1);
  const parts = [];
  if (isGif) parts.push(buildDelayTable(list.map((f) => f.delay ?? 0)));
  for (const f of list) parts.push(encoder(f.pixels, byteOrder));
  const total = parts.reduce((a, b) => a + b.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}

// ---------------------------------------------------------------------------
// 2. 报文组装（PX 帧层 + NX 分包层，逐字节一致）
// ---------------------------------------------------------------------------

/**
 * PX 等价：构造一个完整 output report（长度 = reportCount）
 *   contentLen -> 字节[2]（本包携带的数据字节数）
 *   addr       -> 字节[3..4] 小端
 *   otherHeader-> 字节[5..7]（前 3 字节，未定义则跳过），若 otherHeader[1] 未定义则写 last 标志到字节[6]
 *   customHeader-> 直接覆盖字节[0..]并把 data 放在 customHeader.length 之后（此时其余参数不生效）
 */
function buildFrame(opts) {
  const {
    cmd,
    contentLen = 0,
    addr = 0,
    data,
    reportCount = TFT_REPORT_COUNT,
    otherHeader,
    customHeader,
    last = true,
  } = opts;
  const buf = new Uint8Array(reportCount);
  if (customHeader) {
    buf.set(customHeader, 0);
    if (data) buf.set(data, customHeader.length);
    return buf;
  }
  buf[0] = 0xaa;
  buf[1] = cmd;
  buf[2] = contentLen & 0xff;
  buf[3] = addr & 0xff;
  buf[4] = (addr >> 8) & 0xff;
  if (Array.isArray(otherHeader)) {
    for (let i = 0; i < Math.min(otherHeader.length, 3); i++) {
      if (otherHeader[i] !== undefined) buf[5 + i] = otherHeader[i] & 0xff;
    }
  }
  if (!otherHeader || otherHeader.length < 2 || otherHeader[1] === undefined) buf[6] = last ? 1 : 0;
  if (data) buf.set(data, 8);
  return buf;
}

/**
 * setTftMaterial(0, data)：壁纸
 * 每个 report = AA 4D seqLo seqHi totalLo totalHi matLo matHi + 4096B 数据（末包零填充）
 * 每包都独立等待 cmd=0x4D 的响应（timeout 2000ms，重发 3 次）
 */
function tftMaterialPackets(materialId, data, reportCount = TFT_REPORT_COUNT) {
  const chunk = reportCount - TFT_HEADER_COUNT;
  const total = Math.ceil(data.length / chunk);
  const packets = [];
  for (let seq = 0; seq < total; seq++) {
    const off = seq * chunk;
    const payload = new Uint8Array(chunk);
    payload.set(data.subarray(off, Math.min(off + chunk, data.length)));
    const header = new Uint8Array(TFT_HEADER_COUNT);
    header[0] = 0xaa;
    header[1] = CMD.SET_TFT_MATERIAL;
    header[2] = seq & 0xff;
    header[3] = (seq >> 8) & 0xff;
    header[4] = total & 0xff;
    header[5] = (total >> 8) & 0xff;
    header[6] = materialId & 0xff;
    header[7] = (materialId >> 8) & 0xff;
    packets.push(
      buildFrame({
        cmd: CMD.SET_TFT_MATERIAL,
        contentLen: chunk,
        data: payload,
        reportCount,
        customHeader: header,
      })
    );
  }
  return packets;
}

/**
 * setTftUserAnimation(delays, pixels)：
 *   blob = MV(delays) + pixels（这里是 setTftUserAnimation 内部拼的，NV 变换在像素数据上、拼表之前）
 *   每个 report = AA 50 seqLo seqHi totalLo totalHi 50 06 + 4096B（末包零填充）
 *   每包等待 cmd=0x41 (SET_LED_USER_ANIMATION) 的响应
 */
function tftAnimationPackets(delays, pixelData, reportCount = TFT_REPORT_COUNT) {
  const table = buildDelayTable(delays);
  const blob = new Uint8Array(table.length + pixelData.length);
  blob.set(table, 0);
  blob.set(pixelData, table.length);
  const chunk = reportCount - TFT_HEADER_COUNT;
  const total = Math.ceil(blob.length / chunk);
  const packets = [];
  for (let seq = 0; seq < total; seq++) {
    const off = seq * chunk;
    const payload = new Uint8Array(chunk);
    payload.set(blob.subarray(off, Math.min(off + chunk, blob.length)));
    const header = new Uint8Array(TFT_HEADER_COUNT);
    header[0] = 0xaa;
    header[1] = CMD.SET_TFT_USER_ANIMATION;
    header[2] = seq & 0xff;
    header[3] = (seq >> 8) & 0xff;
    header[4] = total & 0xff;
    header[5] = (total >> 8) & 0xff;
    header[6] = 0x50; // 80 = SET_TFT_USER_ANIMATION（原样来自官方代码）
    header[7] = 0x06; // 6  = 类型/格式字段，含义未见文档
    packets.push(
      buildFrame({
        cmd: CMD.SET_TFT_USER_ANIMATION,
        contentLen: chunk,
        data: payload,
        reportCount,
        customHeader: header,
      })
    );
  }
  return packets;
}

/** setTftBuiltInIndex(index)：TFT 通道，4104 字节 report，只有 1 字节数据 */
function tftBuiltInIndexPacket(index, reportCount = TFT_REPORT_COUNT) {
  const data = new Uint8Array([index & 0xff]);
  return buildFrame({
    cmd: CMD.SET_TFT_BUILT_IN_INDEX,
    contentLen: 1,
    addr: 0,
    data,
    reportCount,
    last: true,
  });
}

/** SET_TEMPORARY_COMMAND_DATA(payload)：主通道 64 字节 report，contentSize 固定 24 */
function temporaryCommandPacket(payload, reportCount = MAIN_REPORT_COUNT) {
  return buildFrame({
    cmd: CMD.SET_TEMPORARY_COMMAND_DATA,
    contentLen: 24,
    addr: 0,
    data: payload,
    reportCount,
    last: true,
  });
}

// payload builders -----------------------------------------------------------

/**
 * 屏幕时间：10 字节
 *   [0]=0x5A [1]=0x01 [2]=0x5A [3]=年%100 [4]=月(1-12) [5]=日 [6]=时 [7]=分 [8]=秒 [9]=星期(0=周日)
 * 调用侧传的是 dayjs().format('YYYY-MM-DD HH:mm:ss') 与 dayjs().day()。
 */
function buildTimePayload(date, weekday) {
  const d = date instanceof Date ? date : new Date(String(date).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) throw new Error('无效的时间格式');
  if (!(weekday >= 0 && weekday <= 6)) throw new Error('无效的星期参数，应为0-6');
  const out = new Uint8Array(10);
  out[0] = 0x5a;
  out[1] = 0x01;
  out[2] = 0x5a;
  out[3] = d.getFullYear() % 100;
  out[4] = d.getMonth() + 1;
  out[5] = d.getDate();
  out[6] = d.getHours();
  out[7] = d.getMinutes();
  out[8] = d.getSeconds();
  out[9] = weekday;
  return out;
}

/**
 * 系统信息：24 字节
 *   [6]=0x5A  [12]=CPU%(0-100) [13]=CPU温度(int8) [14]=GPU%(0-100) [15]=GPU温度(int8)
 *   [16]=当前气温(int8) [17]=最高温(int8) [18]=最低温(int8) [19]=天气代码(0-23) [20]=湿度(0-100)
 *   其余为 0
 */
function buildScreenInfoPayload(info) {
  const {
    cpuUsage = 0, cpuTemp = 0, gpuUsage = 0, gpuTemp = 0,
    currentTemp = 0, maxTemp = 0, minTemp = 0, weather = 0, humidity = 0,
  } = info || {};
  const checks = [
    [cpuUsage, 0, 100, 'CPU占用率'], [cpuTemp, -127, 127, 'CPU温度'],
    [gpuUsage, 0, 100, 'GPU占用率'], [gpuTemp, -127, 127, 'GPU温度'],
    [currentTemp, -127, 127, '当前气温'], [maxTemp, -127, 127, '最高气温'],
    [minTemp, -127, 127, '最低气温'], [weather, 0, 23, '天气代码'],
    [humidity, 0, 100, '湿度'],
  ];
  for (const [v, lo, hi, name] of checks) if (v < lo || v > hi) throw new Error(`无效的${name}: ${v}`);
  const t = new Uint8Array(24);
  t[6] = 0x5a;
  t[12] = cpuUsage & 0xff;
  t[13] = cpuTemp & 0xff;
  t[14] = gpuUsage & 0xff;
  t[15] = gpuTemp & 0xff;
  t[16] = currentTemp & 0xff;
  t[17] = maxTemp & 0xff;
  t[18] = minTemp & 0xff;
  t[19] = weather & 0xff;
  t[20] = humidity & 0xff;
  return t;
}

// ---------------------------------------------------------------------------
// 3. 便捷封装（把上面组合成「官方页面一次点击发出的全部报文」）
// ---------------------------------------------------------------------------

/** 壁纸上传：官方 LV('image', [{pixels}], byteOrder) + setTftMaterial(materialId=0, data) */
function makeWallpaper(rgba, byteOrder, materialId = 0, reportCount = TFT_REPORT_COUNT) {
  const data = encodeLV('image', [{ pixels: rgba }], byteOrder);
  return { data, packets: tftMaterialPackets(materialId, data, reportCount) };
}

/**
 * 动画上传：官方页面是「手工逐帧编码 -> NV 变换 -> setTftUserAnimation(delays, 像素)」。
 * frames: [{ pixels: RGBA, delay: 厘秒 }]，maxFrames 上限裁剪与官方一致（只传前 tftMaxFrames 帧）。
 */
function makeAnimation(frames, byteOrder, opts = {}) {
  const {
    maxFrames = MAX_FRAMES,
    transform,
    width = FRAME_W,
    height = FRAME_H,
    reportCount = TFT_REPORT_COUNT,
  } = opts;
  const used = frames.slice(0, Math.min(frames.length, maxFrames));
  const delays = used.map((f) => f.delay ?? 0);
  let pixels = new Uint8Array(used.length * width * height * 2);
  let off = 0;
  for (const f of used) {
    const enc = encodeRgba565(f.pixels, byteOrder);
    pixels.set(enc, off);
    off += enc.length;
  }
  pixels = transform565(pixels, width, height, transform);
  return { delays, pixels, packets: tftAnimationPackets(delays, pixels, reportCount) };
}

// ---------------------------------------------------------------------------
// 4. 自检
// ---------------------------------------------------------------------------

function runTests() {
  const hex = (arr) => Buffer.from(arr).toString('hex').toUpperCase();

  // --- 1) RGB565 + 字节序：2x2 像素 (红/绿/蓝/白) ---
  const px = new Uint8Array([
    255, 0, 0, 255, // 红
    0, 255, 0, 255, // 绿
    0, 0, 255, 255, // 蓝
    255, 255, 255, 255, // 白
  ]);
  assert.strictEqual(rgb565(255, 0, 0), 0xf800);
  assert.strictEqual(rgb565(0, 255, 0), 0x07e0);
  assert.strictEqual(rgb565(0, 0, 255), 0x001f);
  assert.strictEqual(rgb565(255, 255, 255), 0xffff);
  assert.deepStrictEqual(split565(0xf800), [0xf8, 0x00]);
  assert.strictEqual(hex(encodeRgba565(px, 0)), '00F8E0071F00FFFF'); // 小端：低字节在前
  assert.strictEqual(hex(encodeRgba565(px, 1)), 'F80007E0001FFFFF'); // 大端：高字节在前
  console.log('OK  AV/jV/PV/FV  2x2 红绿蓝白  byteOrder0 = 00F8 E007 1F00 FFFF');

  // --- 2) IV：alpha 5 字节/2 像素 ---
  const px2 = new Uint8Array([
    255, 0, 0, 0x80, // 红 a=0x80
    0, 255, 0, 0x40, // 绿 a=0x40
  ]);
  const alpha = encodeRgba565Alpha(px2, 0);
  assert.strictEqual(alpha.length, 5);
  assert.strictEqual(hex(alpha), '00F8E00784'); // (0x80>>4)<<4 | (0x40>>4) = 0x80|0x04
  // 奇数像素：仍按整对分配 5 字节，第二个像素槽为 0，alpha 低 4 位为 0
  const one = encodeRgba565Alpha(px.slice(0, 4), 0);
  assert.strictEqual(one.length, 5);
  assert.strictEqual(hex(one), '00F80000F0'); // a=0xFF -> (0xF)<<4
  assert.deepStrictEqual(Array.from(encodeRgba565Alpha(px, 1).slice(0, 5)), [0xf8, 0x00, 0x07, 0xe0, 0xff]);
  console.log('OK  IV  alpha 打包 = 00F8 E007 0x84  (a0>>4)<<4 | (a1>>4)');

  // --- 3) MV：3 帧延时表 ---
  const table = buildDelayTable([10, 20, 30]);
  assert.strictEqual(table.length, 256);
  assert.strictEqual(table[0], 3);
  assert.strictEqual(table[1], 50); // 10*5
  assert.strictEqual(table[2], 100); // 20*5
  assert.strictEqual(table[3], 0); // 终止符：第 3 帧延时(30*5=150) 未被写入
  assert.strictEqual(table[4], 255);
  assert.strictEqual(table[255], 255);
  assert.strictEqual(table[250], 255);
  // 饱和：delay>=51 一律 255
  const sat = buildDelayTable([51, 200]);
  assert.strictEqual(sat[1], 255);
  assert.strictEqual(sat[2], 0);
  console.log('OK  MV  3 帧 [10,20,30]cs -> [3,50,100,0,255...]  (末帧延时=0 终止符)');

  // --- 4) NV：旋转/翻转 ---
  // 2x1 图像，两个像素 P0 P1 -> rotate90 变成 1x2 竖排（目标宽 1）
  const two = new Uint8Array([0x11, 0x11, 0x22, 0x22]);
  assert.strictEqual(hex(transform565(two, 2, 1, { rotate: 90 })), '11112222');
  // 2x2：像素编号 1..4（每像素 2 字节同值）验证 90/180/270 与 flip
  const sq = new Uint8Array([1, 1, 2, 2, 3, 3, 4, 4]); // 行0: 1 2 ; 行1: 3 4
  // rotate90: src(x,y)->dst(destW-1-... ) 具体：u=h-1-y, d=x, destW=h=2
  //  (0,0)->(u=1,d=0) => 位置 0*2+1=1 ; (1,0)->(u=1,d=1)=>3 ; (0,1)->(u=0,d=0)=>0 ; (1,1)->(u=0,d=1)=>2
  assert.deepStrictEqual(Array.from(transform565(sq, 2, 2, { rotate: 90 })), [3, 3, 1, 1, 4, 4, 2, 2]);
  assert.deepStrictEqual(Array.from(transform565(sq, 2, 2, { rotate: 180 })), [4, 4, 3, 3, 2, 2, 1, 1]);
  assert.deepStrictEqual(Array.from(transform565(sq, 2, 2, { rotate: 270 })), [2, 2, 4, 4, 1, 1, 3, 3]);
  assert.deepStrictEqual(Array.from(transform565(sq, 2, 2, { flip: true })), [2, 2, 1, 1, 4, 4, 3, 3]);
  // rotate90 x4 回到原样；flip x2 回到原样
  let r = sq;
  for (let i = 0; i < 4; i++) r = transform565(r, 2, 2, { rotate: 90 });
  assert.deepStrictEqual(Array.from(r), Array.from(sq));
  console.log('OK  NV  rotate90/180/270 + flip 像素搬运正确，4x90 复原');

  // --- 5) 壁纸整屏：64800 字节 -> 16 包 ---
  const wallPixels = new Uint8Array(FRAME_W * FRAME_H * 4).fill(0x7f);
  const wall = makeWallpaper(wallPixels, 0);
  assert.strictEqual(wall.data.length, FRAME_BYTES);
  assert.strictEqual(wall.packets.length, 16);
  assert.strictEqual(wall.packets[0].length, TFT_REPORT_COUNT);
  assert.strictEqual(hex(wall.packets[0].slice(0, 8)), 'AA4D000010000000');
  assert.strictEqual(hex(wall.packets[15].slice(0, 8)), 'AA4D0F0010000000');
  assert.strictEqual(wall.packets[15].slice(8).length, 4096);
  // 末包有效数据 = 64800 - 15*4096 = 3360，其余零填充
  const tail = wall.data.subarray(15 * 4096);
  assert.strictEqual(tail.length, 3360);
  assert.deepStrictEqual(Array.from(wall.packets[15].slice(8, 8 + 3360)), Array.from(tail));
  assert.strictEqual(wall.packets[15][8 + 3360], 0);
  assert.strictEqual(wall.packets[15][8 + 4095], 0);
  // materialId 编码：小端在 [6..7]
  const mat5 = tftMaterialPackets(0x1234, new Uint8Array(4), TFT_REPORT_COUNT)[0];
  assert.strictEqual(hex(mat5.slice(6, 8)), '3412');
  console.log('OK  setTftMaterial  64800B -> 16 包, 头 AA4D seq16 total16 mat16');

  // --- 6) 动画：3 帧 + 延时表 ---
  const frames = [0, 1, 2].map((k) => ({
    pixels: new Uint8Array(FRAME_W * FRAME_H * 4).fill(0x10 * (k + 1)),
    delay: [10, 20, 30][k],
  }));
  const anim = makeAnimation(frames, 0);
  assert.strictEqual(anim.pixels.length, 3 * FRAME_BYTES);
  assert.strictEqual(anim.delays.join(','), '10,20,30');
  const blobLen = 256 + anim.pixels.length;
  assert.strictEqual(anim.packets.length, Math.ceil(blobLen / 4096));
  assert.strictEqual(hex(anim.packets[0].slice(0, 8)), 'AA500000' + '30' + '00' + '5006');
  // ^ total = ceil((256+194400)/4096) = 48 = 0x30 -> header: AA 50 seq=0000 total=3000 50 06
  assert.strictEqual(anim.packets[0][8], 3); // 帧数
  assert.strictEqual(anim.packets[0][9], 50);
  assert.strictEqual(anim.packets[0][10], 100);
  assert.strictEqual(anim.packets[0][11], 0);
  // 像素数据紧接 256 字节延时表；首像素 RGBA(0x10,0x10,0x10) -> RGB565 0x1082 -> 小端 82 10
  assert.strictEqual(anim.packets[0][256 + 8], 0x82);
  assert.strictEqual(anim.packets[0][256 + 9], 0x10);
  console.log(`OK  setTftUserAnimation  3 帧 -> ${anim.packets.length} 包, 头 AA50 0000 3000 5006, 首包[8..11]=03 32 64 00`);

  // --- 7) 内置索引 / 时间 / 系统信息报文 ---
  const idx = tftBuiltInIndexPacket(3);
  assert.strictEqual(idx.length, TFT_REPORT_COUNT);
  assert.strictEqual(hex(idx.slice(0, 9)), 'AA5101000000010003');
  const time = buildTimePayload(new Date(2026, 10, 1, 5, 40, 29), 6);
  assert.strictEqual(hex(time), '5A015A1A0B0105281D06');
  const timePkt = temporaryCommandPacket(time);
  assert.strictEqual(timePkt.length, MAIN_REPORT_COUNT);
  assert.strictEqual(hex(timePkt.slice(0, 8)), 'AA34180000000100');
  assert.strictEqual(hex(timePkt.slice(8, 18)), '5A015A1A0B0105281D06');
  const info = buildScreenInfoPayload({
    cpuUsage: 37, cpuTemp: -5, gpuUsage: 12, gpuTemp: 61,
    currentTemp: 18, maxTemp: 22, minTemp: 9, weather: 4, humidity: 55,
  });
  assert.strictEqual(info[6], 0x5a);
  assert.strictEqual(hex(info.slice(12, 21)), '25FB0C3D12 1609 04 37'.replace(/ /g, ''));
  console.log('OK  setTftBuiltInIndex / setTftDateTime / setTftScreenInfo 报文逐字节校验');

  // --- 8) LV 与「页面手工编码」等价性 ---
  const pageManual = new Uint8Array(FRAME_W * FRAME_H * 2);
  for (let i = 0, o = 0; i < wallPixels.length; i += 4, o += 2) {
    const [hi, lo] = split565(rgb565(wallPixels[i], wallPixels[i + 1], wallPixels[i + 2]));
    pageManual[o] = lo; // tftColorByteOrder !== 1
    pageManual[o + 1] = hi;
  }
  assert.deepStrictEqual(Array.from(encodeLV('image', [{ pixels: wallPixels }], 0)), Array.from(pageManual));
  console.log('OK  LV 与页面内联逐像素编码逐字节一致');

  console.log('\n全部自检通过。');
}

function demo() {
  const line = (t) => console.log(t);
  const wallPixels = new Uint8Array(FRAME_W * FRAME_H * 4);
  for (let y = 0; y < FRAME_H; y++) {
    for (let x = 0; x < FRAME_W; x++) {
      const i = (y * FRAME_W + x) * 4;
      wallPixels[i] = Math.round((x / (FRAME_W - 1)) * 255);
      wallPixels[i + 1] = Math.round((y / (FRAME_H - 1)) * 255);
      wallPixels[i + 2] = 64;
      wallPixels[i + 3] = 255;
    }
  }
  const hex8 = (a) => Buffer.from(a.slice(0, 8)).toString('hex').toUpperCase();
  const wall = makeWallpaper(wallPixels, 0);
  line(`壁纸：${wall.data.length} 字节 -> ${wall.packets.length} 包`);
  line(`  首包头 ${hex8(wall.packets[0])}  末包头 ${hex8(wall.packets[wall.packets.length - 1])}`);

  const frames = [0, 1, 2].map((k) => ({
    pixels: new Uint8Array(wallPixels).fill(0x20 * (k + 1)),
    delay: [10, 20, 30][k],
  }));
  const anim = makeAnimation(frames, 0);
  line(`动画：3 帧, 延时 ${anim.delays.join('/')}cs -> ${anim.packets.length} 包`);
  line(`  首包头 ${hex8(anim.packets[0])}  首包[8..12]=${Array.from(anim.packets[0].slice(8, 13)).join(',')}`);
  line(`  总字节 ${256 + anim.pixels.length}（256B 延时表 + ${anim.pixels.length}B 像素）`);
}

if (require.main === module) {
  runTests();
  if (process.argv.includes('--demo')) {
    console.log('\n--- demo ---');
    demo();
  }
}

module.exports = {
  CMD,
  TFT_REPORT_COUNT,
  TFT_HEADER_COUNT,
  MAIN_REPORT_COUNT,
  FRAME_W,
  FRAME_H,
  FRAME_BYTES,
  MAX_FRAMES,
  rgb565,
  split565,
  putPixel,
  encodeRgba565,
  encodeRgba565Alpha,
  buildDelayTable,
  transform565,
  encodeLV,
  buildFrame,
  tftMaterialPackets,
  tftAnimationPackets,
  tftBuiltInIndexPacket,
  temporaryCommandPacket,
  buildTimePayload,
  buildScreenInfoPayload,
  makeWallpaper,
  makeAnimation,
  runTests,
};
