/* data/music.js — 官方 MK87 音乐律动 v1 参数表（官方 UI 真值）
   来源：
   * docs/music-v1-config.json（官方 v1 页面里函数 D7 的配置，2026-11-03 从线上 bundle 提取，权威）
   * capture/official_music_colors3.jsonl（官方 Music.exe 真实颜色采样，见 probe/analyze_official_v1_modes.py）

   官方 v1 与 v2（docs/music-constants.json）不是同一套：MK87 的 musicConfig.version===1，
   官方下拉只有 12 个显示模式 / 11 个背景模式。本表在此基础上补回研究阶段确认存在、
   但官方 v1 页面未暴露的 9 个模式（14–22，来自 v2 列表/采样），最终 21 项（含 100 屏光联动）。
   顺序按产品要求：1,2,13,4,5,6,7,8,9,11,10,14,15,16,17,18,19,20,21,22,100。

   渲染器列（renderer）说明：
   * Fe/*：官方「曲率频阶柱状」，模式号即调色板（1 绿黄红分行 / 2 六色横条 / 4 中心径向色相 /
     5 旋转单色 / 6..11 纯色）。采样反推：这些模式每帧只有单一颜色族，覆盖率随振幅 10%~50% 波动。
   * Se：同心环扩散（默认）。
   * custom：14–22 为官方 v2 研究得出的扩展模式，由本工具自研渲染器实现（未做官方采样校验）。
   * plugin：屏光联动由官方 Music.exe 读屏计算，本工具自研屏幕同步待做（当前回落 13）。

   LED 颜色覆盖（OFFICIAL_COLOR_SCHEMES）只作用于动态多色模式 1/2/4/5/13；
   纯色模式 6/7/8/9/10/11 保持官方采样色，default 表示不覆盖（与官方一致）。
   原生帧率（OFFICIAL_FRAME_RATES）是本工具增强，不是官方 UI 设置项，官方方案默认 66。 */

export const OFFICIAL_MUSIC_MODES = [
  { value: 1, zh: "绿色/黄色/红色", en: "Green/Yellow/Red", renderer: "Fe/gyr", visual: "曲率频阶柱状 · 绿黄红分行" },
  { value: 2, zh: "彩虹色", en: "Rainbow", renderer: "Fe/rainbow", visual: "曲率频阶柱状 · 六色横条" },
  { value: 13, zh: "随曲起舞", en: "Dance to the Beat", renderer: "Se", visual: "中心同心环扩散（默认）" },
  { value: 4, zh: "曲率频阶", en: "Curvature Frequency Steps", renderer: "Fe/radial", visual: "曲率频阶柱状 · 中心径向色相" },
  { value: 5, zh: "频谱循环", en: "Spectrum Cycle", renderer: "Fe/hue-cycle", visual: "曲率频阶柱状 · 旋转单色" },
  { value: 6, zh: "白色", en: "White", renderer: "Fe/solid", visual: "纯白柱状（FF→FE 亮度缩放）" },
  { value: 7, zh: "红色", en: "Red", renderer: "Fe/solid", visual: "纯红柱状" },
  { value: 8, zh: "橙色", en: "Orange", renderer: "Fe/solid", visual: "纯橙柱状" },
  { value: 9, zh: "黄色", en: "Yellow", renderer: "Fe/solid", visual: "纯黄柱状" },
  { value: 11, zh: "绿色", en: "Green", renderer: "Fe/solid", visual: "纯绿柱状" },
  { value: 10, zh: "蓝色", en: "Blue", renderer: "Fe/solid", visual: "纯蓝柱状" },
  { value: 14, zh: "光尘螺旋", en: "Dust Glow Spiral", renderer: "custom", visual: "螺旋光尘沿径向旋转扩散" },
  { value: 15, zh: "休眠火山", en: "Dormant Volcano", renderer: "custom", visual: "低频蓄能，爆发时整片点亮后回落" },
  { value: 16, zh: "光箭穿刺", en: "Light Arrow Piercing", renderer: "custom", visual: "光箭自中心向四周穿刺" },
  { value: 17, zh: "萤火轨迹", en: "Firefly Trail", renderer: "custom", visual: "萤火沿列轨迹游走" },
  { value: 18, zh: "光茧共鸣", en: "Light Cocoon Resonance", renderer: "custom", visual: "环形光茧随节拍呼吸共鸣" },
  { value: 19, zh: "音叉振动", en: "Tuning Fork Vibration", renderer: "custom", visual: "左右对称音叉式振动" },
  { value: 20, zh: "曲率传承", en: "Curvature Legacy Track", renderer: "custom", visual: "曲率频阶沿行传递的传承轨迹" },
  { value: 21, zh: "行波节奏", en: "Row Wave Rhythm", renderer: "custom", visual: "节拍以行波形态逐行推进" },
  { value: 22, zh: "双心共舞", en: "Dual Heart Dance", renderer: "custom", visual: "双中心交替搏动共舞" },
  { value: 100, zh: "屏光联动", en: "Screen light linkage", renderer: "plugin", visual: "官方 Music.exe 读屏（自研屏幕同步待做）" },
];

/* 官方方案 LED 颜色覆盖方案。default = 不覆盖（完全沿用官方采样色）。
   colors 为十六进制数组，单色一套用 1 个点，渐变用 2–3 个点。 */
export const OFFICIAL_COLOR_SCHEMES = [
  { id: "default", zh: "不覆盖（官方采样色）", en: "No override (official sampled colors)", colors: [] },
  { id: "ice", zh: "冰蓝", en: "Ice Blue", colors: ["#00E5FF"] },
  { id: "violet", zh: "紫罗兰", en: "Violet", colors: ["#B36CFF"] },
  { id: "pink", zh: "热粉", en: "Hot Pink", colors: ["#FF2E88"] },
  { id: "lime", zh: "青柠", en: "Lime", colors: ["#A8FF3E"] },
  { id: "amber", zh: "暖橙", en: "Warm Amber", colors: ["#FF6A00"] },
  { id: "sakura", zh: "樱花渐变", en: "Sakura Gradient", colors: ["#FF7AB6", "#B36CFF"] },
  { id: "aurora", zh: "极光渐变", en: "Aurora Gradient", colors: ["#3EFF9A", "#00E5FF", "#7A5CFF"] },
  { id: "sunset", zh: "落日渐变", en: "Sunset Gradient", colors: ["#FFC400", "#FF6A00", "#FF2E88"] },
  { id: "icefire", zh: "冰火渐变", en: "Ice & Fire Gradient", colors: ["#00E5FF", "#FEFEFE", "#FF6A00"] },
];

/* LED 颜色覆盖能生效的动态多色模式（纯色 6/7/8/9/10/11 不受影响） */
export const OFFICIAL_COLOR_MODE_VALUES = [1, 2, 4, 5, 13];

/* 原生帧率选项：本工具增强（官方 v1 固定 20fps），官方方案默认 66 */
export const OFFICIAL_FRAME_RATES = [20, 60, 66];
export const OFFICIAL_DEFAULT_FRAME_RATE = 66;

/* 顺序与官方 v1 UI 下拉一致（0 无 → 6..11 纯色 → 1 绿黄红 → 2 彩虹 → 4 色谱 → 5 频谱循环）。
   调色板已用采样校验：6 FEFEFE / 7 FE0000 / 8 FE3F00 / 9 FEFE00 / 10 0000FE / 11 00FE00。 */
export const OFFICIAL_BACKGROUND_MODES = [
  { value: 0, zh: "无", en: "None", effect: "无背景" },
  { value: 6, zh: "白色", en: "White", effect: "纯白铺满（bb=100 → FE）" },
  { value: 7, zh: "红色", en: "Red", effect: "纯红铺满" },
  { value: 8, zh: "橙色", en: "Orange", effect: "纯橙铺满（255,64,0）" },
  { value: 9, zh: "黄色", en: "Yellow", effect: "纯黄铺满" },
  { value: 10, zh: "蓝色", en: "Blue", effect: "纯蓝铺满" },
  { value: 11, zh: "绿色", en: "Green", effect: "纯绿铺满" },
  { value: 1, zh: "绿色/黄色/红色", en: "Green/Yellow/Red", effect: "三色横向分段（上绿/中黄/下红）" },
  { value: 2, zh: "彩虹色", en: "Rainbow", effect: "六色横向分段（品红/蓝/青/绿/黄/红）" },
  { value: 4, zh: "色谱", en: "Color Spectrum", effect: "中心径向色相渐变" },
  { value: 5, zh: "频谱循环", en: "Spectrum Loop", effect: "整屏单色，色相旋转" },
];

/* 与官方 v1 UI 完全一致的参数范围（振幅 1–100 默认 30；背景亮度 1–100 默认 100） */
export const OFFICIAL_LIMITS = {
  amplitude: { min: 1, max: 100, step: 1, default: 30 },
  backBrightness: { min: 1, max: 100, step: 1, default: 100 },
};
