/* data/music.js — 官方 MK87 音乐律动 v1 参数表（官方 UI 真值）
   来源：
   * docs/music-v1-config.json（官方 v1 页面里函数 D7 的配置，2026-11-03 从线上 bundle 提取，权威）
   * capture/official_music_colors3.jsonl（官方 Music.exe 真实颜色采样，见 probe/analyze_official_v1_modes.py）

   官方 v1 与 v2（docs/music-constants.json）不是同一套：MK87 的 musicConfig.version===1，
   下拉里是下面 12 个显示模式 / 11 个背景模式；v2 的 13/22/14/15/16/18/19/17/20/21 列表不适用于它。

   渲染器列（renderer）说明：
   * Fe/*：官方「曲率频阶柱状」，模式号即调色板（1 绿黄红分行 / 2 六色横条 / 4 中心径向色相 /
     5 旋转单色 / 6..11 纯色）。采样反推：这些模式每帧只有单一颜色族，覆盖率随振幅 10%~50% 波动。
   * Se：同心环扩散（默认）。
   * plugin：屏光联动由官方 Music.exe 读屏计算，本工具自研屏幕同步待做（当前回落 13）。 */

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
  { value: 100, zh: "屏光联动", en: "Screen light linkage", renderer: "plugin", visual: "官方 Music.exe 读屏（自研屏幕同步待做）" },
];

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
