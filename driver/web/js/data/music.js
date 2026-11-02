/* data/music.js — 官方 MK87 音乐律动参数表（官方 v1 UI 同款）
   来源：docs/music-constants.json（官方线上 bundle 提取），运行时不解析 JSON。
   显示模式 12 种 / 背景模式 11 种 / 振幅与背景亮度范围，与官方 v1 插件 UI 一致。 */

export const OFFICIAL_MUSIC_MODES = [
  { value: 13, zh: "随曲起舞", en: "Dance to the Beat", renderer: "Se", visual: "中心同心环扩散(默认)" },
  { value: 22, zh: "双心共舞", en: "Dual Heart Dance", renderer: "L", visual: "内置坐标图案" },
  { value: 14, zh: "尘埃光漩", en: "Dust Glow Spiral", renderer: "Ce", visual: "中心4色射线旋转" },
  { value: 15, zh: "蛰伏火山", en: "Dormant Volcano", renderer: "Ee", visual: "三塔/火山" },
  { value: 16, zh: "光矢穿心", en: "Light Arrow Piercing", renderer: "De", visual: "脉冲粒子横条" },
  { value: 18, zh: "光茧共振", en: "Light Cocoon Resonance", renderer: "Oe", visual: "边框环绕+对角光带" },
  { value: 19, zh: "音叉振空", en: "Tuning Fork Vibration", renderer: "Ae", visual: "左右闪电触须" },
  { value: 17, zh: "萤火轨迹", en: "Firefly Trail", renderer: "je", visual: "中心行正弦波" },
  { value: 20, zh: "曲率遗轨", en: "Curvature Legacy Track", renderer: "Ne", visual: "右侧向内波形" },
  { value: 21, zh: "行波律动", en: "Row Wave Rhythm", renderer: "Pe", visual: "矩阵雨柱" },
  { value: 4, zh: "曲率频阶", en: "Curvature Frequency Steps", renderer: "Fe", visual: "背景+包络柱状" },
  { value: 100, zh: "屏光联动", en: "Screen light linkage", renderer: "plugin", visual: "Music.exe 计算" },
];

export const OFFICIAL_BACKGROUND_MODES = [
  { value: 0, zh: "无", en: "None", effect: "无背景" },
  { value: 1, zh: "绿色/黄色/红色", en: "Green/Yellow/Red", effect: "3色横向分段(绿/黄/红)" },
  { value: 2, zh: "彩虹色", en: "Rainbow", effect: "6色横向分段(品红/蓝/青/绿/黄/红)" },
  { value: 4, zh: "色谱", en: "Color Spectrum", effect: "中心径向色相渐变" },
  { value: 5, zh: "频谱循环", en: "Spectrum Loop", effect: "纯色旋转色相" },
  { value: 6, zh: "白色", en: "White", effect: "白" },
  { value: 7, zh: "红色", en: "Red", effect: "红" },
  { value: 8, zh: "橙色", en: "Orange", effect: "橙" },
  { value: 9, zh: "黄色", en: "Yellow", effect: "黄" },
  { value: 10, zh: "蓝色", en: "Blue", effect: "蓝" },
  { value: 11, zh: "绿色", en: "Green", effect: "绿" },
];

/* 与官方 v1 UI 完全一致的参数范围 */
export const OFFICIAL_LIMITS = {
  amplitude: { min: 1, max: 100, default: 50 },
  backBrightness: { min: 10, max: 100, step: 10, default: 100 },
};
