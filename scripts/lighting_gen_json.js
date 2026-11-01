// lighting_gen_json.js — 合成 docs/lighting-modes.json（全部数据来自 bundle 静态提取，不手抄）
// 输入：docs/_lighting_raw/{lighting-modes.raw.json, mk87-config.json, led-key-table.json}
// 输出：docs/lighting-modes.json
const fs = require('fs');
const IN = 'C:/Users/ptfm/Documents/ajazz-re/docs/_lighting_raw';
const OUT = 'C:/Users/ptfm/Documents/ajazz-re/docs/lighting-modes.json';

const raw = JSON.parse(fs.readFileSync(`${IN}/lighting-modes.raw.json`, 'utf8'));
const cfg = JSON.parse(fs.readFileSync(`${IN}/mk87-config.json`, 'utf8'));
const ledKey = JSON.parse(fs.readFileSync(`${IN}/led-key-table.json`, 'utf8'));

const DECORATE = (m) => {
  const params = [];
  if (m.isShowColor) params.push('color');
  if (m.isShowSecondaryRGB) params.push('secondaryColor');
  if (m.isShowSpeed) params.push('speed');
  if (m.isShowDirection) params.push('direction');
  if (m.isShowEffectModeType) params.push('effectModeType');
  if (m.isHideColorMode) params.push('(hidden:colorMode)');
  return {
    mode: m.value,
    name: m.name,
    textKey: m.text,
    icon: m.icon,
    sort: m.sort,
    ui: {
      isShowColor: m.isShowColor,
      isShowSecondaryRGB: m.isShowSecondaryRGB ?? false,
      isShowSpeed: m.isShowSpeed,
      speedValue: m.speedValue ?? null,
      isShowDirection: m.isShowDirection,
      directionPosition: m.directionPosition ?? null,
      directionValue: m.directionValue ?? null,
      isHideColorMode: m.isHideColorMode ?? false,
      isShowEffectModeType: m.isShowEffectModeType ?? false,
    },
    effectModeTypeOptions: m.effectModeTypeOptions ?? null,
    params,
  };
};

const lightingConfig = cfg.lightingConfig;
const mk87Modes = [...raw.defalutLightingModeList].sort((a, b) => (a.sort || 0) - (b.sort || 0));
const inUi = (list, value) => list.map(m => m.value).includes(value);

// 复现 bundle 里 initProtocol 的过滤逻辑，确认 MK87 最终列表
const hidden = lightingConfig.hiddenDefaultEffect ?? [];
const custom = lightingConfig.customEffect ?? [];
let computed = [...raw.defalutLightingModeList].filter(m => !hidden.includes(m.value));
for (const m of raw.appendLightingModeList) if (custom.includes(m.value)) computed.push(m);
computed = computed.sort((a, b) => (a.sort || 0) - (b.sort || 0));
if (lightingConfig.isSingleColor) computed = computed.map(m => ({ ...m, isShowColor: false }));

const doc = {
  $schema: 'ajazz-mk87-lighting/1.0',
  generatedBy: 'scripts/lighting_gen_json.js',
  generatedAt: new Date().toISOString(),
  device: {
    vid: '0x0C45 (3141)', pid: '0x8047 (32839)', name: 'AJAZZ KEYBOARD',
    configOffsetInBundle: '1194719..1200783 (assets/layout-classic-CMxiG14P.js)',
    tftConfigName: cfg.tftConfig?.name ?? null,
    routesName: cfg.routesName,
    protocolsChunk: 'assets/lighting-DzPku7KQ.js = config/protocols/default/lighting.ts',
    note: 'keyboardConfig.protocol 未定义 → 走 default 协议配置，模式表来自上面这个 chunk',
  },
  sources: [
    { file: 'assets/lighting-DzPku7KQ.js', what: '模式表（defalutLightingModeList / appendLightingModeList / lightBoxModeList / sideLightModeList / CUSTOM_LIGHTING_MODE）' },
    { file: 'assets/lightingPane-J3Fl9UJi.js', what: '灯效参数面板：colorMode 单选、亮度/速度滑条、方向按钮、effectModeType、颜色选择器、键组选择器' },
    { file: 'assets/layout-classic-CMxiG14P.js @2439551..2452600', what: 'lighting 路由页 setup：tabs、isCustomMode=[20,21,128]、mode=0 关灯、定时切换、LED 实时回读' },
    { file: 'assets/layout-classic-CMxiG14P.js @2285100..2288300', what: 'lightingPane 组合式函数 C7：自定义模式判定、customLedData 写入、setCustomLEDData 防抖' },
    { file: 'assets/layout-classic-CMxiG14P.js @1930197..1931110', what: '协议实现 vZ(setLEDEffect) / bZ(setCustomLEDData) / _Z(getLEDEffect) / yZ(getCustomLEDData)' },
    { file: 'assets/keyboard-BfmQGlU0.js', what: '预览键盘（DOM 网格，非位图）：ledId ↔ 键 value 的实时上色' },
  ],
  lightingConfig,
  lightingConfigMeaning: {
    minBrightness: '亮度滑条下限（MK87=1）',
    maxBrightness: '亮度滑条上限（MK87=6）',
    minSpeed: '速度滑条下限（MK87=1）',
    maxSpeed: '速度滑条上限（MK87=6）',
    isShowLightBox: 'MK87=false → 不显示「灯箱」tab，也不读 GET_LIGHT_BOX',
    lightBoxList: '仅当 isShowLightBox=true 才用于过滤 lightBoxModeList（MK87 无效）',
    isShowLightBoxEdit: '灯箱编辑入口开关（MK87 因 tab 不显示而无效果）',
    absentFlags: {
      isShowSideLight: '缺省 → 无「侧灯」tab',
      isShowGifEffect: '缺省 → 无「GIF 灯效」tab，且 lighting 里 mode 255 分支不可达',
      isEnableLightSync: '缺省 → 预览键盘不做 getAllLightsRGB 实时上色轮询',
      isSingleColor: '缺省 → 不禁用颜色按钮',
      hiddenDefaultEffect: '缺省 → 不隐藏任何默认模式',
      customEffect: '缺省 → 不追加 23..33/254 这批扩展模式',
    },
  },
  modeListForThisDevice: computed.map(DECORATE),
  modeListForThisDeviceValues: computed.map(m => m.value),
  modeListAllProtocolModes: {
    default: raw.defalutLightingModeList.map(DECORATE),
    append: raw.appendLightingModeList.map(DECORATE),
    appendNote: '只有 lightingConfig.customEffect 里列出的才会出现在 UI；MK87 未配置 → 这 12 个模式在 MK87 网页上不可见',
  },
  lightBoxModes: raw.lightBoxModeList.map(DECORATE),
  sideLightModes: raw.sideLightModeList.map(DECORATE),
  customLighting: {
    CUSTOM_LIGHTING_MODE: raw.CUSTOM_LIGHTING_MODE,
    customModeFamily: [20, 21, 128],
    customModeFamilyEvidence: "isCustomMode = [20,21,128].includes(ledEffect.mode)  (bundle @2442576)",
    howUIEntersCustomMode: '点击模式网格里 value=128「自定义」→ handleChangeLightingMode → ledEffect.mode=128, direction=directionValue??0 → setLEDEffect',
    dataTable: 'SET_CUSTOM_LED_DATA(36) 512B = 128 × [idx, R, G, B]，idx 写数组下标',
    firmwareFnKeys: {
      '71': '自定义灯光1（Fn+1）',
      '72': '自定义灯光2（Fn+2）',
      '98': '自定义灯光3（Fn+3）',
      '99': '自定义灯光录制（Fn+`）',
      note: '来自 docs/keymap-tables.json funcChars；FUNC 动作由固件处理，网页端没有对应命令（SET_KEYBOARD_CUSTOM_FUNCTION_ON/OFF(48/49) 在 bundle 里从未被调用）',
    },
    recordCheckbox: '键组选择器的「录制」复选框只改选中行为（isRecord=true 时新框选会并入已选键），不下发任何命令；真正的录制是固件 Fn+` 触发',
    unknown: [
      '固件上报 20/21/128 与 FUNC 71/72/98 的一一对应关系未在 bundle 里写明（【推断】按顺序对应 1/2/3）',
      '20/21 是否共享同一张 512B 表未验证（网页端只写同一张表）',
    ],
  },
  customLightingFlow: {
    readOnInit: [
      'GET_LED_EFFECT(19) contentSize=16 → {mode,red,green,blue,driverSetting,secondary*,colorMode,brightness,speed,direction,effectModeType,checkCodeL/H}',
      'GET_CUSTOM_LED_DATA(20) contentSize=512 → 128 × {ledId,red,green,blue}',
      '两者都在 deviceInit 里，且仅当 routesName 含 "lighting"（bundle @1863050 附近 / protocol_commands.js deviceInit）',
    ],
    steps: [
      { step: 1, ui: '进入 lighting 页 → 点「自定义」(128)', wire: 'SET_LED_EFFECT(35) mode=128（其余字段沿用 deviceStorage.ledEffect；direction=directionValue??0）', note: 'isCustomMode 变 true → 预览键盘进入可点选状态 + 右侧出现颜色选择器/键组选择器', evidence: 'Ce @2444105' },
      { step: 2, ui: '在预览键盘上框选键（可全选/反选/按 WASD/数字/方向键分组）', wire: '自定义模式下会发 SET_CUSTOM_LED_DATA(36)：把当前取色器颜色刷到新选中的键', note: 'selectedKeys=[{row,col}]，disabledLight 的键被过滤；非自定义模式则纯前端不改数据', evidence: '_e @2443245' },
      { step: 3, ui: '选颜色（iro 取色器 / HEX / RGB 输入 / 预设色）', wire: '自定义模式下 → SET_CUSTOM_LED_DATA(36)；普通模式 → SET_LED_EFFECT(35) colorMode=0 + RGB', note: '取色器 emit getColor → {red,green,blue}，0..255 整数，不做量化', evidence: 're / Oe @2443606' },
      { step: 4, ui: '颜色落到已选中的键', wire: 'SET_CUSTOM_LED_DATA(36) 512B（300ms 防抖）', note: 'customLedData[key.value] = 颜色；发送前 pauseLightSync、发完 100ms 后 resumeLightSync（MK87 因 isEnableLightSync 缺省 → 空操作）', evidence: 'C7 le @2287426' },
      { step: 5, ui: '重置（清空自定义颜色）', wire: 'SET_CUSTOM_LED_DATA(36) 全 0', note: 'customLedData 全部 red/green/blue=0，index 字节仍写下标' },
      { step: 6, ui: '切到别的灯效模式', wire: 'SET_LED_EFFECT(35) mode=新模式', note: '离开自定义模式（isCustomMode=false，预览键盘回到不可点选）' },
    ],
    notUsed: [
      'setKeyData / SET_KEY(34)：只用于改键页，与灯效无关',
      'SET_KEYBOARD_CUSTOM_FUNCTION_ON/OFF(48/49)：enum 里有，bundle 里 0 次调用',
    ],
    colorQuantization: '无量化：iro 取色器输出 sRGB 0..255 整数，直接写进 512B 的 R/G/B 字节；HEX 输入按 2 位一组 parseInt(...,16)。仅音乐律动 2.4G 通道会把 RGB888 压成 RGB565（AV/jV），键盘灯效不走那条路',
  },
  params: {
    brightness: { field: 'payload[9]', rangeThisDevice: [lightingConfig.minBrightness, lightingConfig.maxBrightness], step: 1, ui: '滑块 step=1，值显示为 brightness + $t(gif_text14)', zeroMeaning: '协议层原样下发 0；网页 UI 最小值=1，所以「0」只能由外部工具发；是否等同关灯未在 bundle 里定义【推断】更可靠的做法是 mode=0' },
    speed: { field: 'payload[10]', rangeThisDevice: [lightingConfig.minSpeed, lightingConfig.maxSpeed], step: 1, ui: '仅 currentLighting.isShowSpeed 为 true 的模式显示', },
    direction: {
      field: 'payload[11]', values: { 0: '右/正向', 1: '左', 2: '上', 3: '下' },
      uiEvidence: "directionPosition==='top' 时两个按钮分别发 2/3 并显示上下箭头；否则发 1/0 并显示左右箭头（lightingPane chunk）",
      defaultsFromModeList: Object.fromEntries(raw.defalutLightingModeList.filter(m => m.isShowDirection).map(m => [m.value, m.directionValue])),
      note: '切模式时 handleChangeLightingMode 会把 direction 重置为该模式的 directionValue ?? 0',
    },
    colorMode: {
      field: 'payload[8]', values: { 0: '单色（用 payload[1..3] 的 RGB；取色器一动就强制 0）', 1: 'RGB/多色（用固件内置配色，忽略 payload[1..3]）' },
      uiEvidence: "$t('lighting_single_color')=0 与 'RGB'=1 两个单选；选颜色时 updateLedEffectPatch({colorMode:0,...})",
      default: '设备实测 colorMode=1',
      hiddenFor: '模式表里 isHideColorMode=true 的模式（仅 29 单色呼吸）不显示这个单选',
    },
    effectModeType: {
      field: 'payload[12]', onlyMode: 254,
      values: raw.appendLightingModeList.find(m => m.value === 254).effectModeTypeOptions,
      uiLabelKey: 'music_text1', note: 'MK87 无 254（未在 customEffect 里）→ 该控件不出现',
    },
    driverSetting: { field: 'payload[4]', value: '255 硬编码', note: '官方 setLEDEffect 不接受该字段；读回时字段名叫 driverSetting' },
    checkCode: { field: 'payload[14],[15]', value: '0xAA,0x55 固定', note: '读回时字段名叫 checkCodeL/checkCodeH，值恒为 AA/55' },
    payload13: '保留，恒 0',
    speedValueInModeList: 'lightingList 里的 speedValue 在 bundle 里从未被读取（死字段）；切模式不会自动改 speed',
  },
  wireFormats: {
    setLedEffect: {
      cmd: 35, ackCmd: '0x23', len: 16,
      layout: '[0]=mode [1]=R [2]=G [3]=B [4]=255 [5..7]=副色 [8]=colorMode [9]=brightness [10]=speed [11]=direction [12]=effectModeType [13]=0 [14]=0xAA [15]=0x55',
      frame: 'AA 23 10 00 00 00 01 00 | payload(16) ... 其余补 0（64B report）',
      verifiedOnDevice: '01 FF FF FF FF 00 00 00 01 05 03 00 00 00 AA 55（docs/protocol.md §6 实测回读）',
    },
    setCustomLedData: {
      cmd: 36, ackCmd: '0x24', len: 512,
      layout: '128 × [idx, R, G, B]；idx = 数组下标（不是读到过的 ledId 字段）',
      chunking: 'NX 按 reportCount-8=56 字节/包 切 10 包，addr 递增',
    },
    getLedEffect: { cmd: 19, len: 16, note: '读回字段名 driverSetting/checkCodeL/checkCodeH 与写入名不同' },
    getCustomLedData: { cmd: 20, len: 512 },
    streamFrameHeader: 'AA cmd seqHi seqLo totalHi totalLo 0 0 | 数据（每包 4104-8=4096 字节）',
    setLedUserAnimation: { cmd: 65, ackCmd: '0x41', payload: '4B 前导[帧数LE16, ceil(106-speed)LE16] + 帧数×键数×RGB' },
    setLedData: { cmd: 66, note: 'setGifLighting 用它做「GIF 灯效」下发/预览；setLedSyncAnimation 也可指定 ACK=65 复用此命令' },
    clearLedData: { cmd: 54, note: '网页端只在点阵屏/LED 数据组件用到（清 LED 缓冲），键盘灯效页不用' },
    musicData: {
      cmd: '50 (GET_LED_DATA 复用为写通道) / 53 (SET_MUSIC_DATA) / 60 (24G 64B)',
      v1Shape: '每键 4 字节 [ledId,R,G,B] + 1 字节 level(0..7)=round(amplitude*7)（v2 浏览器侧采样路径）',
      v1ForMK87: 'MK87 musicConfig.version=1 → 浏览器不发 LED 数据，交给本机助手 Music.exe（见 helperApi）',
    },
    helperApi: {
      base: 'http://127.0.0.1:9191',
      endpoints: [
        'GET /api/keyboard/layout/base64?data=<urlencoded base64(JSON)>  — 下发键盘几何（name,vid,pid,deviceMode,layouts{rows,cols,keys[{row,col,code,index,name,disabledLight}]}）',
        'GET /api/keyboard/musiceffect?param=<mode>&<amplitude>&<backmode>&<backmodebrightness>&1 — 设音乐律动参数（300ms 防抖）',
        'GET /api/keyboard/musiceffect/ — 读当前每键颜色（预览用）',
        'GET /api/keyboard/musiceffect/close/ — 关闭音乐律动',
        'GET /api/audio/amplitude — 读振幅（v2 用）',
        'GET /api/hardware/info — 硬件信息',
      ],
    },
  },
  musicConfig: cfg.musicConfig,
  musicTabs: {
    versionUsedByMK87: cfg.musicConfig?.version,
    componentSelected: 'version===1 → musicV1（O7）；version===2 → musicV2（X7）；MK87 走 musicV1',
    musicV1Ui: {
      modeList: [
        { value: 1, textKey: 'music_mode_text1' }, { value: 2, textKey: 'music_mode_text2' },
        { value: 13, textKey: 'music_mode_text3' }, { value: 4, textKey: 'music_mode_text4' },
        { value: 5, textKey: 'music_mode_text5' }, { value: 6, textKey: 'music_mode_text6' },
        { value: 7, textKey: 'music_mode_text7' }, { value: 8, textKey: 'music_mode_text8' },
        { value: 9, textKey: 'music_mode_text9' }, { value: 11, textKey: 'music_mode_text10' },
        { value: 10, textKey: 'music_mode_text11' }, { value: 100, textKey: 'music_mode_text21' },
      ],
      backmodeList: [0, 6, 7, 8, 9, 10, 11, 1, 2, 4, 5].map((v, i) => ({ value: v, textKey: `music_bg_text${i + 1}` })),
      amplitude: { min: 1, max: 100, unit: '%', textKey: 'music_text3' },
      backmodeBrightness: { min: 1, max: 100, unit: '%', textKey: 'music_text4' },
      storeKey: 'musicV1Config {mode,amplitude,backmode,backmodebrightness}',
      requiresPlugin: 'hasDownloadPlugin（未装 Music.exe 时显示下载按钮，指向 https://config.driveall.cn/music/v2/Music.exe）',
    },
    musicV2Ui: { note: 'MK87 不用；v2 多了 ledModeList/点阵屏显示模式、测试模式、10..100 背景亮度，浏览器侧采样画布后按 setMusicData 直发' },
  },
  gifLighting: {
    available: false,
    why: 'lightingConfig.isShowGifEffect 缺省 → tabs 里不 push gif；且 ledEffect.mode=255 分支不可达',
    protocolStillThere: {
      uploadCmd: '65 SET_LED_USER_ANIMATION（4B 前导 + 帧×键×RGB，4096B/包，8B 流式头）',
      bootCmd: '64 SET_LED_BOOT_ANIMATION 只在 enum 里，bundle 0 次调用（开机动画也走上一条 65）',
      maxFrames: 'deviceInfo.ledMaxFrames（GET_DEVICE_INFO[26..27]，MK87 实测 0 → 代码里退化成 260 帧上限）',
      frameRate: 'delay = ceil(106 - speed)（speed 来自 GIF 记录）',
      keyOrder: '只取非 disabledLight 的键，按 keyList 行优先顺序；数据来自编辑器画布像素（hex → RV() → {r,g,b}）',
    },
  },
  ledKeyMap: {
    howItWorks: 'LED id == 键位矩阵槽位 value；官方预览键盘用 ledId 直接匹配 key.value 上色，customLedData 也用 key.value 做下标',
    evidence: [
      "bundle @2442358: t.find(t=>t.ledId===e.value) → bgColor=`rgb(...)`（displayKeyList 生成）",
      "bundle @2443402: _.value[m.value[t.row][t.col].value].red=... （customLedData 下标 = 键 value）",
      "bundle @2441996: getAllLightsRGB24G 回包按 keyList 展平顺序逐键取色 → ledId: r.value",
    ],
    previewIsDomNotBitmap: '预览键盘是 DOM 网格（key-item w-14 h-14 + className 控制键宽），kb_bg.png 只是产品图（keyboardImg 字段），不参与逐键上色 → 不存在「从图里反推 LED 索引」的隐藏表',
    caveat: '【推断】87 键的实际 LED 序号 = 矩阵槽位序号；同一固件与 98 键带屏机型共用固定矩阵（128 槽），空槽位 13-15/29-31/45-47/61-63/77-79/93-98/101/109-127 在 87 键板上无对应物理灯。需真机逐点点亮确认（按 rowsInPreview 逐格点，不要按 0..86 数）',
    rowsInPreview: cfg.keyList.map((row, ri) => ({
      row: ri, width: row.length,
      keys: row.map(({ value, name, keyCode, className }) => ({ ledId: value, name, keyCode, className: className ?? '' })),
    })),
    table: ledKey.map(({ ledId, row, col, name, keyCode, key }) => ({ ledId, row, col, name, keyCode, key: key ?? null })),
    slotsWithoutKey: (() => { const s = new Set(ledKey.map(k => k.ledId)); const out = []; for (let i = 0; i < 128; i++) if (!s.has(i)) out.push(i); return out; })(),
  },
  uiI18nKeys: {
    tabs: { color: 'color_name', lightBox: 'light_box', sideLight: 'side_light', music: 'icon_6', musicDiy: 'music_diy', gif: 'gif_text2', aiLighting: 'ai-lighting' },
    panel: {
      title: 'lighting', editSection: 'lighting_edit', colorMode: 'lighting_color_mode',
      singleColor: 'lighting_single_color', brightness: 'lighting_brightness', speed: 'lighting_speed',
      direction: 'lighting_direction', colorSection: 'lighting_color', rgbSelect: 'lighting_rgb_select',
      mainRgb: 'lighting_main_rgb', secondaryRgb: 'lighting_secondary_rgb',
      unit: 'gif_text14', effectModeType: 'music_text1',
    },
    modeNames: Object.fromEntries([...raw.defalutLightingModeList, ...raw.appendLightingModeList].map(m => [m.value, m.text])),
  },
  openQuestions: [
    'mode 20/21 与 FUNC 71/72/98 的对应关系（bundle 只给出 [20,21,128] 三值判定）',
    'brightness=0 是否等同关灯（UI 不可达；协议未定义；建议用 mode=0）',
    '128 个 LED 里 87 个物理键的真实 LED 序号需真机逐点点亮验证',
    'GET_LED_EFFECT 里 driverSetting(=255) 的真实固件含义未知',
  ],
};

fs.writeFileSync(OUT, JSON.stringify(doc, null, 2));
console.log('written', OUT, fs.statSync(OUT).size, 'bytes');
console.log('MK87 UI modes:', computed.map(m => `${m.value}:${m.name}`).join(', '));
console.log('ledKeyMap entries:', doc.ledKeyMap.table.length, '| slots without key:', doc.ledKeyMap.slotsWithoutKey.length);
