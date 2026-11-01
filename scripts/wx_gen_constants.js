#!/usr/bin/env node
// wx_gen_constants.js — 从 bundle 重新生成 docs/wireless-constants.json（可复核）
// 用法: node scripts/wx_gen_constants.js
// 数据来源：
//   - assets/layout-classic-CMxiG14P.js（S 特殊 2.4G 表、HX 枚举、配置映射表、函数偏移）
//   - docs/_wireless_raw/config_map_parsed.json（由 scripts/wx_cfgmap.js 生成）
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./wx_lib');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'docs', 'wireless-constants.json');
const RAW = path.join(ROOT, 'docs', '_wireless_raw');

L.load();
const S = L.src();

// ---------- 1. S 特殊 2.4G 设备表 ----------
const anchor = '1452:591:2.4G Dongle';
const a = S.indexOf(anchor);
const tickStart = S.lastIndexOf('`', a);
const tickEnd = S.indexOf('`', a);
const special = S.slice(tickStart + 1, tickEnd).split(',').map(x => x.trim()).filter(Boolean);
if (special.length !== 64) throw new Error(`S 表应为 64 项，实际 ${special.length}`);

// ---------- 2. HX 枚举里与本主题相关的命令 ----------
const CMD_WANT = {
  GET_DEVICE_INFO: 16,
  GET_GAME_MODE: 17,
  GET_LED_EFFECT: 19,
  GET_KEY: 18,
  GET_MACRO: 21,
  GET_FN_KEY: 22,
  GET_LED_DATA: 50,
  GET_ALL_LIGHTS_RGB: 51,
  SET_TEMPORARY_COMMAND_DATA: 52,
  SET_MUSIC_DATA: 53,
  CLEAR_LED_DATA: 54,
  GET_ALL_LIGHTS_RGB_24G: 55,
  GET_ALL_LIGHTS_RGB_24G_64_BYTE: 59,
  SET_MUSIC_DATA_24G_64_BYTE: 60,
  SET_LED_BOOT_ANIMATION: 64,
  SET_LED_USER_ANIMATION: 65,
  SET_LED_DATA: 66,
  SET_TFT_MATERIAL: 77,
  SET_TFT_USER_ANIMATION: 80,
  SET_TFT_BUILT_IN_INDEX: 81,
  SET_PROFILE: 144,
  GET_DEVICE_NOTIFY: 250,
  GET_24G_DISCONNECT_NOTIFY: 252,
};
const hxDef = L.findDef('HX');
const hxBody = hxDef.code.slice(hxDef.code.indexOf('{'), hxDef.code.lastIndexOf('}') + 1);
const HX = {};
for (const m of hxBody.matchAll(/([A-Z][A-Z0-9_]+)\s*:\s*(\d+)/g)) HX[m[1]] = +m[2];
for (const k of Object.keys(CMD_WANT)) {
  if (HX[k] !== CMD_WANT[k]) throw new Error(`HX.${k} 期望 ${CMD_WANT[k]}，bundle 里是 ${HX[k]}`);
}

// ---------- 3. 配置映射表（含 4/5 段键） ----------
let cfgParsed = [];
const cfgFile = path.join(RAW, 'config_map_parsed.json');
if (fs.existsSync(cfgFile)) cfgParsed = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));
else {
  // 退化：直接从 bundle 抓键
  const re = /"\/src\/config\/keyboards\/([^/"]+)\/([^"]+)\.ts":([A-Za-z_$][\w$]*)/g;
  let m;
  while ((m = re.exec(S))) cfgParsed.push({ path: m[1], file: m[2], local: m[3], at: m.index });
}
const dongleKeys = cfgParsed
  .map(e => e.file)
  .filter(f => /-\d+-\d+$/.test(f) && /Dongle|2\.4G|Wireless/i.test(f))
  .sort();

// ---------- 4. 函数/数据结构偏移 ----------
function off(name) {
  if (name === '$X') {
    const m = /(?:^|[^\w$.])\$X\s*=\s*async\s*\(/.exec(S);
    return m ? m.index + (m[0][0] === '$' ? 0 : 1) : null;
  }
  const d = L.findDef(name);
  return d ? d.start : null;
}
const offsets = {};
const OFF_WANT = [
  'PX', 'IX', 'FX', 'NX', 'MX', 'LX', 'RX', 'YX',
  'GX', 'WX', 'DZ', 'OZ', 'kZ', 'TZ', 'MZ', 'UZ', 'HZ', 'VZ', 'iQ',
  'XX', 'QX', 'ZX', '$X', 'XZ', 'iZ', 'MV', 'AV', 'jV', 'RV', 'rY',
  'oQ', 'lQ', 'uQ', 'dQ', 'fQ', 'pQ', 'mQ', 'hQ', 'gQ', '_Q', 'vQ', 'yQ', 'bQ', 'xQ', 'SQ', 'CQ', 'wQ', 'TQ',
  'g7', 'Eae',
];
for (const n of OFF_WANT) {
  const o = off(n);
  if (o !== null) offsets[n] = o;
}
// store / S 表 / 2.4G UI 分支（手工核对过的锚点）
offsets['__special24GTable'] = tickStart;
offsets['__webHIDStore'] = 1832097;
offsets['__profilesModuleExport'] = S.indexOf('oQ=t({');
offsets['__ledAnimationPage'] = 2240031;

// ---------- 5. 组装 ----------
const C = {
  meta: {
    title: 'AJAZZ MK87（VID 0x0C45 / PID 0x8047）2.4G / Profile / 灯效动画 静态逆向常量表',
    source: 'assets/layout-classic-CMxiG14P.js（3.3MB，未混淆）',
    generatedBy: 'scripts/wx_gen_constants.js',
    selfCheck: 'node scripts/wireless_ref.js',
    bundleLength: S.length,
    offsetsMeaning: '偏移 = 该定义在 bundle 中的字符下标（0-based）',
    note: '标 inferred:true 的字段是【推断】，其余为 bundle 源码直接可读的事实',
  },

  identification: {
    // ---- 2.4G 接收器识别：store 里的 S 常量（64 项，vid:pid:productName 十进制） ----
    special24GDevices: special,
    special24GDevicesCount: special.length,
    keyFormat: '`${device.vendorId}:${device.productId}:${device.productName}`（十进制 vid/pid）',
    matchMode: 'includes() —— 完整字符串相等（不是前缀/模糊匹配）',
    usage: [
      'requestDevices()/reconnectDevices() 里：命中 S 表 → 追加调用 oe() 读取“完整设备 ID”做去重键',
      'disconnect 处理里：命中 S 表 → 用 device 对象反查已登记的完整 ID',
    ],
    // ---- oe(): 完整设备 ID ----
    completeId: {
      func: 'oe',
      offset: offsets.oe !== undefined ? offsets.oe : 1840806,
      formula: '`${vid}:${pid}:${productName}:${manufacturer}:${product}`',
      how: 'open() → sendReportFromDevice("getDeviceInfo", dev, undefined, false) → close()，取 GET_DEVICE_INFO 的 manufacturer(bytes12..13) / product(bytes14..15)',
      why: '同一个接收器会暴露多个同名 HID 接口/多个同型号接收器，vid:pid:name 不足以唯一；加 manufacturer+product 才能落到具体机型配置',
    },
    // ---- 配置文件键 ----
    configKey: {
      format: '`${vendorId}-${productId}-${productName}[-${manufacturer}-${product}]`',
      mapPath: '/src/config/keyboards/<supplier>/<key>.ts',
      supplier: 'ajazz（本 bundle 只含 ajazz 一家：共 ' + cfgParsed.length + ' 个配置）',
      totalConfigs: cfgParsed.length,
      dongleConfigCount: dongleKeys.length,
      dongleConfigKeys: dongleKeys,
      lookup: 'ae(id)：把 id 按 ":" 切成 5 段，用前 3 段 + 可选后 2 段拼键，在 VY 映射表里查；找不到 → $message.error(message_driveall_error) 并返回 null',
    },
    // ---- 设备过滤器 ----
    hidFilters: {
      userSelectFilter: 'zY（docs/infra.js）里 suppliers 含 ajazz 的条目',
      acceptFilter: 're(device)：任一 collection 的 usagePage ∈ {65384(0xFF68), 65408(0xFF80), 65376(0xFF60), 65280(0xFF00), 65281(0xFF01), 65307(0xFF1B)}',
      tftChannel: 'LX(productId, 65383=0xFF67)：按 productId + usagePage 找 TFT 通道设备（仅 USB 有线有这条接口）',
    },
    // ---- MK87 的两套配置 ----
    mk87: {
      usb: {
        configKey: '3141-32839-AJAZZ KEYBOARD',
        vendorId: 3141, productId: 32839, productName: 'AJAZZ KEYBOARD',
        connectType: 'USB',
        routesName: ['customKeys', 'lighting', 'macro', 'tft', 'settings'],
        configOffset: 1194734,
      },
      wireless24g: {
        configKey: '3141-65278-2.4G Dongle-1-18',
        vendorId: 3141, productId: 65278, productName: '2.4G Dongle',
        manufacturer: 1, product: 18,
        connectType: '2.4G',
        routesName: ['customKeys', 'lighting', 'macro', 'settings'],
        configOffset: 1665299,
        evidence: [
          'MK87 设备信息 manufacturer=1 / product=18（docs/protocol.md 实测）',
          '3141-65278-2.4G Dongle-1-18 的 keyList 与 MK87 USB 配置逐键一致（87 键，value/name 完全相同）',
          'musicConfig.keyOffset（F1/Z/↑/Spacebar/R-Alt）与 MK87 USB 配置完全相同',
          'tftConfig 同为 {name:"AK980_PRO", 240x135, localforageKey:"w240h135"}',
          'inferred: true —— 没有真机 2.4G 连接，无法 100% 确认接收器上报的 productName 就是 "2.4G Dongle"',
        ],
        inferred: true,
      },
      wildcard: {
        configKey: '3141-65278-AJAZZ AK820MAX',
        note: 'S 表里还有 "AJAZZ AK820MAX" 这种带型号名的接收器；同一 pid 下靠 productName + manufacturer/product 区分机型',
      },
    },
    connectTypeValues: ['USB', '2.4G'],
    connectType2_4GDefinitions: [
      { where: 'requestDevices / openDevice / reconnectDevices（store）', effect: '挂 3 个监听器：start24GDisconnectListener / start24GSleepListener / start24GWakeListener' },
      { where: 'setMusicData(TZ)', effect: 'reportCount===64 && lightingVersion===1 时走 cmd60 的 2.4G 通路' },
      { where: 'setGifLighting(MZ)', effect: 'checkAddr/parseAddr 生效（ACK 需回显包序号）' },
      { where: 'lighting 页轮询 le()', effect: 'reportCount===64 && lightingVersion===1 → getAllLightsRGB24G64Byte(cmd59)，否则 getAllLightsRGB24G(cmd55)；二者都用返回的电量刷 deviceInfo.batteryLevel' },
      { where: 'TFT/灯效上传（UZ/MZ/KZ/qZ）', effect: 'connectType==="USB" 时才 await LX(productId) 切到 0xFF67 通道；2.4G 直接写接收器（报文 64B，每包 56B 数据）' },
      { where: 'settings 页', effect: '2.4G 强制显示休眠时间；回报率用 gameModeInfo.wirelessReportRate(u16, r[18..19]) 而不是 reportRate；powerMode 有 3 档' },
      { where: 'performance 页', effect: 'connectType!=="USB" 时隐藏“切换轴体”，重置 tab 需 performanceConfig.isShow24GCalibration' },
      { where: 'deviceInit 失败提示', effect: '2.4G 用 message_driveall_error2（专用文案），USB 用 message_driveall_error' },
      { where: 'led 页外链音乐客户端', effect: 'deviceMode = connectType==="USB" ? 0 : 1' },
    ],
  },

  framing: {
    requestPacket: '长度 = collections[0].outputReports[0].items[0].reportCount（含 0xAA），sendReport(reportId=0, packet)',
    responseParse: 'FX：bytes[0]===0x55 才有效 → {cmd: bytes[1], lenOrType: bytes[2], addr: bytes[3]|bytes[4]<<8, data: bytes.slice(8)}',
    standardHeader8: {
      layout: '[0]=0xAA [1]=cmd [2]=len&0xFF [3]=addrLo [4]=addrHi [5..7]=otherHeader [6]=lastFlag(当 otherHeader 无第二项)',
      dataOffset: 8,
      dataPerPacket: 'reportCount - 8',
    },
    customHeader: 'PX(customHeader) 提前返回：整包 = customHeader 原文 + data（不写 len/addr/last），customHeader 长度即数据偏移',
    timeouts: {
      rule: 'frameVersion===1（新一代固件/2.4G 接收器）→ 大部分命令 timeout 2000ms；否则 500ms。灯效高频命令例外（见各命令）',
      default: 500,
      frameVersion1: 2000,
      defaultRetries: 3,
      retryExhausted: '重发 3 次仍无响应 → closeDevice/forget + 回首页 + $message.error(link_state)，Promise.reject([])',
    },
  },

  commands24g: [
    {
      name: 'GET_ALL_LIGHTS_RGB_24G',
      cmd: 55,
      direction: 'read',
      request: {
        header: '4 字节自定义头 [0xAA, 55, 包序号, 0]',
        body: '全 0 填充（长度 = reportCount-4，64B 报告 → 60B）',
        addrField: '不使用（自定义头没有 addr 字段）；包序号放在 byte2',
      },
      response: {
        header: '4 字节 [0x55, 55, 包序号, 电量]',
        battery: '响应 byte[3]（仅首包有效；官方只取 responses[0][3]）',
        dataOffset: 4,
        pixelFormat: 'RGB565 大端：hi=(v>>11&31)<<3 / mid=(v>>5&63)<<2 / lo=(v&31)<<3',
      },
      packetCount: 'ceil((ledCount*2 + 1) / (reportCount-4))（官方 a=ledCount*2+1）',
      timeoutMs: '500（frameVersion===1 → 2000）',
      retries: 3,
      note: '没有灯号表：按物理灯序号顺序读全部灯；用于不认识 ledId 列表时的兜底',
    },
    {
      name: 'GET_ALL_LIGHTS_RGB_24G_64_BYTE',
      cmd: 59,
      direction: 'read',
      request: {
        header: '标准 8 字节头（无 otherHeader）',
        body: '要读的灯号列表，每灯 u16 小端（ledCount*2 字节），addrStart=0',
        addrField: '期望响应 addr = 本包数据在灯号表里的字节偏移（checkAddr:true）',
      },
      response: {
        header: '8 字节 [0x55, 59, len, addrLo, addrHi, 电量, 1, 0]',
        battery: '响应 byte[5]（仅首包有效）',
        dataOffset: 8,
        pixelFormat: 'RGB565 大端，每包 28 灯（56B/包，64B 报告）',
      },
      packetCount: 'ceil(ledCount*2 / (reportCount-8))',
      timeoutMs: 2000,
      retries: 3,
      note: '只回你点名的灯（可按 keyList 过滤 disabledLight），比 cmd55 精确；命令名里的 64_BYTE 指接收器 64 字节报文',
    },
    {
      name: 'SET_MUSIC_DATA_24G_64_BYTE',
      cmd: 60,
      direction: 'write',
      request: {
        header: '标准 8 字节头，otherHeader=[musicType] → byte5=musicType，末包 byte6=1',
        body: '每灯 2 字节 RGB565 大端（由 AV/jV 从 4 字节/灯的流量化）',
        addrField: 'addrStart = 该包在编码流里的字节偏移（每包 +56）',
      },
      response: { header: '标准 8 字节（cmd=60），内容不解析', note: 'ACK 丢包也无所谓' },
      timeoutMs: 10,
      retries: 0,
      note: '真正的“流式”写：10ms 超时 + 0 重发，官方故意不等确认（音乐律动每秒几十帧）',
    },
    {
      name: 'SET_MUSIC_DATA（USB 分支）',
      cmd: 50,
      direction: 'write',
      request: {
        header: '标准 8 字节头，otherHeader=[musicType,0]（非末包）/ [musicType]（末包 → byte6=1）',
        body: '原样 4 字节/灯，不量化、不压缩',
        addrField: 'byte offset',
      },
      timeoutMs: '50（frameVersion===1 → 2000）',
      retries: 3,
      note: '注意 cmd 名是 GET_LED_DATA(50) 但实际当写命令用（bundle 里就是 cmd: HX.GET_LED_DATA）',
    },
    {
      name: 'SET_MUSIC_DATA（其它/BT 分支）',
      cmd: 53,
      direction: 'write',
      request: { header: '4 字节自定义头 [0xAA, 53, 包序号, musicType]', body: 'reportCount-4 字节' },
      timeoutMs: 10,
      retries: 0,
      note: 'MK87/USB 与 2.4G 都不走这条；仅老设备',
    },
    {
      name: 'CLEAR_LED_DATA',
      cmd: 54,
      direction: 'write',
      request: { header: '标准 8 字节头，无数据', body: '空' },
      timeoutMs: '500（frameVersion===1 → 2000）',
      retries: 3,
      note: '清掉灯效动画缓存；LED 动画/同步动画前常用',
    },
    {
      name: 'GET_24G_DISCONNECT_NOTIFY',
      cmd: 252,
      direction: 'device→host',
      request: null,
      response: { header: '[0x55, 0xFC, 子类型, ...]（长度≥3）', subtypes: { 4: 'disconnect', 5: 'reset', 6: 'sleep' } },
      note: '详见 notifications 段',
    },
    {
      name: 'SET_LED_BOOT_ANIMATION',
      cmd: 64,
      direction: 'write',
      request: null,
      implemented: false,
      note: 'bundle 里只有枚举、没有任何调用点。开机动画实际复用 SET_LED_USER_ANIMATION(65)，用 ledId==="startup" 的灯效条目（帧数上限 200）',
    },
  ],

  ledAnimation: {
    commands: {
      SET_LED_USER_ANIMATION: { cmd: 65, usedFor: ['led 页自定义灯效动画（含 ledId==="startup" 开机动画）'] },
      SET_LED_DATA: { cmd: 66, usedFor: ['GIF 灯效（lighting 页 gif tab）', '实时同步动画 setLedSyncAnimation（isBigData=false）'] },
    },
    payload: {
      layout: '[0..1]=帧数 u16 LE  [2..3]=每帧延时 u16 LE  [4..]=帧 × 灯 × RGB888（每灯 3 字节）',
      frameCountRule: '帧数 = data.length / 灯数',
      delayFormula: 'delay = Math.ceil(106 - speed)，speed 默认 100（可用范围 50..104）',
      delayUnit: 'inferred: 固件侧单位未知；官方预览定时器用 (106-speed)*10 或 *20 ms，两者不一致 → 真机需实测',
      ledOrder: 'keyList.flat() 的顺序；disabledLight 的灯**整灯剔除**（不是填 0），因此每帧字节数 = 有效灯数 × 3',
      noSeparateDelayTable: '与 TFT 动画不同：LED 动画只有 1 个全局延时，没有 256 字节延时表',
    },
    packet: {
      header: '8 字节 [0xAA, cmd, seqHi, seqLo, totalHi, totalLo, 0, 0]（seq/total 均大端）',
      dataPerPacket: 'reportCount - 8 → 2.4G 接收器 56B，USB 走 0xFF67 TFT 通道 4096B',
      packetLen: '固定 = reportCount（64 或 4104），末包不足补 0',
      totalFormula: 'total = ceil((4 + 3*有效灯数*帧数) / (reportCount-8))',
      ack: {
        cmd65: '响应 cmd=65，按 cmd 匹配即可',
        cmd66: '2.4G 且 frameVersion===1 → checkAddr:true + addrStart=包序号 + parseAddr=(resp[2]<<8|resp[3])，接收器必须回显包序号；USB 不校验',
      },
      timeoutMs: 2000,
      retries: 3,
    },
    limits: {
      source: 'GET_DEVICE_INFO 48 字节响应',
      tftMaxFrames: { offset: 22, bytes: 2 },
      gifMaxFrames: { offset: 24, bytes: 2, usedBy: 'GIF 灯效：帧数 > gifMaxFrames 时弹窗；实际发送 Math.min(帧数, gifMaxFrames) → 0 就等于不支持' },
      ledMaxFrames: { offset: 26, bytes: 2, usedBy: 'LED 页动画：!=0 用它，==0 时兜底 260 帧；ledId==="startup"/"LEOBOG_AMG65" 固定 200 帧上限' },
      mk87: { tftMaxFrames: 140, gifMaxFrames: 0, ledMaxFrames: 0, meaning: 'MK87 只能走 TFT 动画（140 帧）；GIF 灯效不支持；LED 动画按 260 帧兜底' },
    },
    gifLightingEditor: {
      jsonFormat: '{ name, speed, data: ["#rrggbb", ...], cols: [每行键数...] }',
      dataLengthRule: 'data.length = 帧数 × keyList.flat().length（灯数）',
      speedClamp: '导入时 clamp 到 50..104（默认 100）',
      storage: 'localforage：gifLightingList_<keyList 形状签名> + gifLightingItem_<gifId>',
      builtinSource: 'keyboardConfig.lightingConfig.gifEffectIds[] → fetch /gif-lighting/<id>.json',
      exportBin: '同上 4 字节头 + 帧×有效灯×RGB888',
      gate: 'keyboardConfig.lightingConfig.isShowGifEffect===true 才显示 gif tab（MK87 没有该字段 → 不显示）',
    },
    ledPageAnimation: {
      editor: 'led 页（lightingConfig 之外的 ledConfig 机型，如 r5c63）',
      frameCountRule: '帧数 = data.length / (ledConfig.rows*ledConfig.cols)',
      limits: 'ledId==="startup"/"LEOBOG_AMG65" → 200；否则 ledMaxFrames(≠0) 或 260',
      upload: 'setLedUserAnimation(dev, cfg, 4字节头, [{r,g,b}...]) → cmd65',
      extra: 'r5c63/r5c63_aula 机型会按 G5 调色板重排颜色后再发',
    },
  },

  profiles: {
    setProfile: {
      cmd: 144,
      direction: 'write',
      request: {
        header: '3 字节自定义头 [0xAA, 144, profileNumber]',
        body: '无（contentSize=1）',
        packetLen: 'reportCount（64）',
        profileNumberRule: '1-based：官方 CQ 传 t+1；读回 currentProfile(设备信息 byte19) 后减 1 作为本地下标',
      },
      response: { match: '响应 byte[2] === 发送的 profileNumber 才算成功', note: '即设备的 lenOrType 字段被用来回显 profile 号' },
      timeoutMs: 2000,
      retries: 3,
    },
    deviceFields: {
      currentProfile: { offset: 19, bytes: 1, note: '1-based' },
      maxProfile: { offset: 33, bytes: 1, note: '板载 profile 数量；0/1 = 不支持板载（只能软件 profile）' },
    },
    hardwareThreshold: 1,
    hardwareRule: 'getHardwareMaxProfile(di) = di.maxProfile > 1 ? di.maxProfile : 0 → 0 表示纯软件 profile',
    softwareLimits: { maxProfiles: 4, rule: 'isHardwareProfile===false 时最多 4 个（useProfiles: D = maxProfile || 4）' },
    storage: {
      kind: 'localforage（IndexedDB），不写设备',
      key: '`${deviceId}-profile`（deviceId 是 vid:pid:productName[:manufacturer:product]）',
      shape: '{ profileList: [{ profileName, keyList, fnKeyList, ledEffect, customLedData, macroDataList, magneticAxisRT, ... }], currentProfileIndex }',
      defaultName: 'profile',
      exportedFile: '{ deviceId, profile }',
    },
    switchFlows: {
      software: {
        api: 'switchAndApplyProfile(dev, index, profile?)',
        steps: [
          'syncDeviceStorageToProfile(dev, 当前 deviceStorage) —— 先把当前改动存回旧 profile',
          'switchProfile(dev, index) —— 只改 currentProfileIndex + 落 localforage',
          '按 profile 内容依次下发：setKeyData → setFnKeyData → setLEDEffect → setCustomLEDData → setMacroData →（磁轴/灯箱/侧灯）',
          'applyProfileToDeviceStorage：把 profile 写进 $I store，但**保留当前 deviceInfo/sn**',
          'initProtocol(undefined, {ledEffect, customLedData, macroDataList}) —— 用 profile 的值覆盖内存，不重读这三项',
        ],
        reReadFull: false,
      },
      hardware: {
        api: 'switchHardwareProfile(dev, index) → setProfile',
        steps: [
          'setProfile(dev, index+1) 写板载槽位',
          'switchProfile(dev, index) 同步本地下标',
          'deviceInit(dev) —— **全量重读**（deviceInfo/gameMode/key/fn/ledEffect/customLed/macro/…）',
          'setProtocolDataFromDeviceInit(init) + syncHardwareProfiles(dev) —— 用设备里的 maxProfile/currentProfile 重建本地列表',
        ],
        reReadFull: true,
      },
    },
    pageGate: {
      route: '/profiles（name: "profiles", layout: "sider"）',
      gate: 'router guard: new Set([...keyboardConfig.routesName, ...(layout==="tech" ? ["profiles"] : [])])',
      layout: 'bundle 里 OH() 硬编码 layout="classic" → 追加表为空',
      conclusion: '本 bundle（classic 布局）下 /profiles 路由不可达：MK87 的 routesName 里也没有 profiles；页面 chunk（assets/useProfiles-Bm0j-YvT.js）虽被打包但进不去',
      devicesWithHardwareProfiles: 'ledConfig/performanceConfig 那些机型；MK87 maxProfile=0 → 纯软件 profile 且页面不开放',
    },
  },

  notifications: {
    frameParse: '监听器都自己 new Uint8Array(event.data.buffer)，要求 length>=3',
    twoFamilies: {
      'cmd250': 'GET_DEVICE_NOTIFY —— 设备状态（第 3 字节 = 子类型）',
      'cmd252': 'GET_24G_DISCONNECT_NOTIFY —— 2.4G 链路事件（第 3 字节 = 子类型）',
      wake: '唤醒通知是**另一种帧头** 0xA6（不是 0x55），三字节 0xA6 0xFF 0x01',
    },
    listeners: {
      start24GDisconnectListener: { cmd: 252, subtype: 4, action: '关闭设备/标记 isConnected=false/清 historyConnect/回首页/$message.error(link_state)' },
      start24GSleepListener: { cmd: 252, subtype: 6, action: 'is24GSleeping=true（App 层整屏遮罩 sleeping-tips，隐藏 router-view）' },
      start24GWakeListener: { cmd: '0xA6 0xFF 0x01', subtype: null, action: 'is24GSleeping=false' },
      startResetListener: { cmd: 252, subtype: 5, action: '清 magneticAxisRTConfig 后 location.reload()' },
      startDeviceStateListener: {
        cmd: 250,
        subtype: 6,
        action: 'bytes[3]===1 → startGetTftInfo()（开始轮询/推送屏幕系统信息），0 → stop',
      },
    },
    is24GSleepingStateMachine: {
      initial: false,
      toTrue: ['252/6 sleep 通知'],
      toFalse: ['0xA6 0xFF 0x01 唤醒通知', 'closeDevice（E）', 'disconnect 处理（j/k）'],
      note: '没有“发命令/写 feature report 唤醒”的代码路径：唤醒完全由设备主动上报，驱动只被动更新 UI 状态',
      mountedWhen: '2.4G 设备在 openDevice/requestDevices/reconnectDevices 成功后立刻挂 3 个监听器',
    },
  },

  deviceInfoFields48: [
    { offset: 0, len: 1, name: 'romSize', mk87: 64 },
    { offset: 2, len: 2, name: 'macroSpaceSize', mk87: 3072 },
    { offset: 4, len: 2, name: 'vid', mk87: 3141 },
    { offset: 6, len: 2, name: 'pid', mk87: 32839 },
    { offset: 8, len: 2, name: 'version(BCD)', mk87: '1.19' },
    { offset: 12, len: 2, name: 'manufacturer', mk87: 1 },
    { offset: 14, len: 2, name: 'product', mk87: 18 },
    { offset: 16, len: 1, name: 'workMode' },
    { offset: 17, len: 1, name: 'batteryLevel', mk87: '50 → 2.4G 下由 cmd55/59 刷新' },
    { offset: 18, len: 1, name: 'chargeStatus', mk87: 1 },
    { offset: 19, len: 1, name: 'currentProfile', mk87: 0 },
    { offset: 22, len: 2, name: 'tftMaxFrames', mk87: 140 },
    { offset: 24, len: 2, name: 'gifMaxFrames', mk87: 0 },
    { offset: 26, len: 2, name: 'ledMaxFrames', mk87: 0 },
    { offset: 28, len: 1, name: 'tftDirection', mk87: 0, note: '255 = 无屏 → 官方把 tft 路由剔掉' },
    { offset: 30, len: 1, name: 'frameVersion', mk87: 0, note: '===1 → 所有命令 timeout 拉到 2000ms，且启用 SN 读取与 2.4G ACK 序号校验' },
    { offset: 31, len: 1, name: 'lightingVersion', mk87: 0, note: '===1 且 2.4G 且 64B 报告 → 音乐走 cmd60、灯效读回走 cmd59' },
    { offset: 32, len: 1, name: 'firmwareStatus', note: '1 = 固件损坏（只显示修复页）' },
    { offset: 33, len: 1, name: 'maxProfile', mk87: 0 },
    { offset: 35, len: 1, name: 'tftColorByteOrder' },
  ],

  sourceOffsets: offsets,

  openQuestions: [
    'inferred: 2.4G 下接收器的 outputReport reportCount 是否为 64、usagePage 是哪一个（代码里用 `||32`/`||64` 兜底，无法从静态代码确定）',
    'inferred: LED 动画帧延时字段（u16）在固件里的时间单位（预览用 ×10 与 ×20 两种换算）',
    'inferred: MK87 的 2.4G 接收器上报的 productName 是否为 "2.4G Dongle"（若是别的名字会落到 3141-65278-AJAZZ AK820MAX 之类的通配配置）',
    '未验证: 2.4G 下 tftDirection 是否为 255（若是，官方会进一步剔掉 tft 路由；不过 2.4G 配置本身就没给 tft 路由）',
    '未验证: cmd55 响应 byte[2] 是“包序号回显”还是别的（官方不校验，只按 cmd 匹配）',
    '未验证: 2.4G 下 SET_PROFILE(144) 是否真的被接收器转发到键盘（bundle 只按回显判断）',
    'cmd64 (SET_LED_BOOT_ANIMATION) 无任何实现，开机动画的真实固件入口未知',
  ],
};

fs.writeFileSync(OUT, JSON.stringify(C, null, 2) + '\n', 'utf8');
console.log(`wrote ${OUT} (${fs.statSync(OUT).size} bytes)`);
console.log(`S 表 ${special.length} 项；配置 ${cfgParsed.length} 个，其中 dongle 键 ${dongleKeys.length} 个`);
console.log('offsets:', JSON.stringify(offsets).slice(0, 400));
