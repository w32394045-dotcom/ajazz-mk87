// 临时工具：打印 bundle 关键符号偏移（供 docs 引用）。用 node scripts/_offsets.js 运行
const fs = require('fs');
const path = require('path');
const t = fs.readFileSync(path.join(__dirname, '..', 'assets', 'layout-classic-CMxiG14P.js'), 'utf8');
const marks = {
  'fX enum': 'fX={DEFAULT:0',
  'pX encoder': 'function pX(e,t,n,r=``)',
  'mX decoder': 'var mX=(e,t)=>{',
  'KEYBOARD enc': 'case`KEYBOARD`:e[t]=2,e[t+2]=n.value||0',
  'MACRO enc': 'case`MACRO`:case`MT`',
  'END enc': 'case`END`:e[t]=14',
  'vX keyboard dec': 'vX=(e,t)=>{let{param1:n,param2:r}=e',
  'AX end dec': 'AX=e=>{let{param1:t,param2:n}=e',
  'bX macro dec': 'bX=e=>{let{param1:t,param2:n,param3:r}=e',
  'i18n $=global.t': '$=lH.global.t',
  'cH locale switch': 'async function cH(e)',
  'aH fetch langs': 'async function aH(e)',
  'pL helper': 'function pL(e,t){return cL[e][t]}',
  'XV langs base': 'function XV(e){return',
  'uH merge': 'async function uH(e)',
  'iH deepmerge': 'function iH(e,t){let n={...e}',
  'tft anim header': 'i[6]=80,i[7]=6',
  'setTftBuiltInIndex qZ': 'qZ=async(e,t,...n)',
  'deviceNotify XZ': 'XZ=(e,t,n,r)=>{',
  'notify type6 call': "'startDeviceStateListener',6",
  'macro mask list': 'x=K(()=>[{label:$(`macro_mask_select1`',
  'macro param3 assign': 'param2:S.value,param3:S.value===1?C.value:0',
  'settings tft radio': 'TFT`+e.$t(`show_time`)',
  'gameMode enc a[7]': 'a[7]=i.tftDisplayTime||0',
  'plugin base': 'xY=`http://127.0.0.1:9191`',
  'Music.exe url': 'https://config.driveall.cn/music/v2/Music.exe',
  'MK87 cfg': 'productId:32839',
  'reset listener ZX': 'ZX=(e,t,n)=>{',
  'sleep listener QX': 'QX=(e,t,n)=>{',
  'musicV1 D7': 'function D7(e,t){',
};
for (const [k, v] of Object.entries(marks)) {
  const i = t.indexOf(v);
  console.log(String(i).padStart(9), k, i < 0 ? '<<MISS' : '');
}
