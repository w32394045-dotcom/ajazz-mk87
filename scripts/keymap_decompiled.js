// =============================================================================
// AJAZZ MK87 按键映射 —— 官方 bundle 里与 4 字节编码/解码相关的函数（格式化还原）
//
// 本文件由 scripts/slice.js 按偏移分段生成，内容是从
//   assets/layout-classic-CMxiG14P.js
// 按偏移切出来的**原文**，仅做了换行/缩进格式化（逻辑一字未改）。
// 每个段落标题里的 @NNNNNN 是 bundle 内字符偏移，可直接用 scripts/slice.js 复核：
//   node scripts/slice.js <start> <end>
//
// 用途：给实现方（Lead）当权威参考；语义说明见 docs/keymap.md。
// =============================================================================


// ===== pageType 枚举 fX  +  编码器 pX（action 对象 → 4 字节）  @1905045..1906068 =====
fX= {
  DEFAULT:0,
  MOUSE:1,
  KEYBOARD:2,
  CONSUMER_KEY:3,
  SYSTEM_KEY:4,
  EXTRA_FUNCTION:5,
  MACRO:6,
  CB:7,
  DKS:8,
  MT:9,
  TGL:10,
  SOCD:11,
  RS:12,
  FUNC:13,
  END:14,
  MPT:15
};
function pX(e,
t,
n,
r=``) {
  switch(n.page) {
    case`DEFAULT`:break;
    case`MOUSE`:e[t]=1,
    e[t+1]=n.param1||1,
    e[t+2]=n.value||0;
    break;
    case`KEYBOARD`:e[t]=2,
    e[t+2]=n.value||0;
    break;
    case`CONSUMER_KEY`:let i=n.value||0;
    e[t]=3,
    e[t+1]=i&255,
    e[t+2]=i>>8&255;
    break;
    case`MACRO`:case`MT`:case`SOCD`:case`RS`:case`CB`:case`MPT`:e[t]=fX[n.page],
    e[t+1]=n.param1||0,
    e[t+2]=n.param2||0,
    e[t+3]=n.param3||0;
    break;
    case`DKS`:e[t]=8,
    e[t+1]=n.value||0;
    break;
    case`TGL`:e[t]=10,
    e[t+1]=n.value||0;
    break;
    case`FUNC`:e[t]=13,
    e[t+1]=(n.value||0)>>16&255,
    e[t+2]=(n.value||0)>>8&255,
    e[t+3]=(n.value||0)&255;
    break;
    case`FUNC_V2`: {
      let r=0,
      i=0;
      n.keyType?(r=n.keyType===2?n.value??0:0,
      i=n.keyType===1?n.value??0:0):(r=n.param1??0,
      i=n.param2??0),
      e[t]=128|r>>8&127,
      e[t+1]=r&255,
      e[t+2]=i>>8&255,
      e[t+3]=i&255;
      break
    }case`END`:e[t]=14,
    e[t+1]=n.param1||0,
    e[t+2]=n.param2||0;
    break;
    default:console.warn(`${r}鏈煡鐨勯〉闈㈢被鍨? ${n.page}`)
  }
}var

// ===== 解码器 mX（4 字节 → action 对象，15 路分派）  @1906069..1906553 =====
mX=(e,
t)=> {
  if(e.pageType>=128)return kX(e);
  switch(e.pageType) {
    case fX.DEFAULT:return;
    case fX.MOUSE:return _X(e);
    case fX.KEYBOARD:return vX(e,
    t);
    case fX.CONSUMER_KEY:return yX(e);
    case fX.MACRO:return bX(e);
    case fX.CB:return xX(e);
    case fX.DKS:return SX(e);
    case fX.MT:return CX(e);
    case fX.TGL:return wX(e);
    case fX.SOCD:return TX(e);
    case fX.RS:return EX(e);
    case fX.FUNC:return DX(e);
    case fX.END:return AX(e);
    case fX.MPT:return OX(e);
    default:console.warn(`鏈煡鐨勯〉闈㈢被鍨? ${e.pageType}`);
    return
  }
}

// ===== hX：512 字节 → keyList[].userKey（按 keyList.value 索引槽）  @1906554..1906768 =====
hX=(e,
t)=> {
  let n=JSON.parse(JSON.stringify(t.keyList));
  for(let r=0;
  r<n.length;
  r++)for(let i=0;
  i<n[r].length;
  i++) {
    let a=n[r][i].value;
    if(a>=0&&a<e.length&&e[a]) {
      let o=e[a],
      s=mX(o,
      t);
      s&&(n[r][i].userKey=s)
    }
  }return n
}

// ===== gX：512 字节 → wheelKeys[].userKey（滚轮键）  @1906769..1907472 =====
gX=(e,
t)=> {
  let n=JSON.parse(JSON.stringify(t.wheelKeys));
  for(let r=0;
  r<n.length;
  r++) {
    let i=e[n[r].value];
    switch(i.pageType) {
      case fX.DEFAULT:break;
      case fX.MOUSE:n[r].userKey=_X(i);
      break;
      case fX.KEYBOARD:n[r].userKey=vX(i,
      t);
      break;
      case fX.CONSUMER_KEY:n[r].userKey=yX(i);
      break;
      case fX.MACRO:n[r].userKey=bX(i);
      break;
      case fX.CB:n[r].userKey=xX(i);
      break;
      case fX.DKS:n[r].userKey=SX(i);
      break;
      case fX.MT:n[r].userKey=CX(i);
      break;
      case fX.TGL:n[r].userKey=wX(i);
      break;
      case fX.SOCD:n[r].userKey=TX(i);
      break;
      case fX.RS:n[r].userKey=EX(i);
      break;
      case fX.FUNC:n[r].userKey=DX(i);
      break;
      case fX.END:n[r].userKey=AX(i);
      break;
      case fX.MPT:n[r].userKey=OX(i);
      break;
      default:console.warn(`鏈煡鐨勯〉闈㈢被鍨? ${i.pageType}`)
    }
  }return n
}

// ===== _X：MOUSE(1) 解码  @1907473..1907667 =====
_X=e=> {
  let {
    param1:t,
    param2:n
  }=e;
  switch(t) {
    case 1:return oX.find(e=>e.param1===1&&e.value===n);
    case 3:return oX.find(e=>e.param1===3&&e.value===n);
    default:console.warn(`鏈煡鐨勯紶鏍囧姛鑳界被鍨? ${t}`);
    return
  }
}

// ===== vX：KEYBOARD(2) 解码（含 param1 修饰位图遗留形态）  @1907668..1908016 =====
vX=(e,
t)=> {
  let {
    param1:n,
    param2:r
  }=e;
  if(n!==0) {
    let e=aX.find(e=>e.param1===n);
    if(e)return e
  }if(r!==0) {
    let e=iX.find(e=>e.value===r);
    if(e||(e=aX.find(e=>e.value===r),
    e)||(t.keyboardLang===`jaText`||t.keyboardLang===`jaTextBr`)&&(e=cX.find(e=>e.value===r),
    e))return e
  }console.warn(`鏈壘鍒板搴旂殑閿洏鎸夐敭: param1=0x${n.toString(16)}, param2=0x${r.toString(16)}`)
}

// ===== yX：CONSUMER_KEY(3) 解码  @1908017..1908180 =====
yX=e=> {
  let {
    param1:t,
    param2:n
  }=e,
  r=t|n<<8,
  i=oX.find(e=>e.page===`CONSUMER_KEY`&&e.value===r);
  if(i)return i;
  console.warn(`鏈壘鍒板搴旂殑澶氬獟浣撴寜閿? keyCode=0x${r.toString(16)}`)
}

// ===== bX：MACRO(6) 解码  @1908181..1908305 =====
bX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e,
  i=t,
  a=n,
  o=r;
  return {
    name:`M${i+1}`,
    value:i,
    page:`MACRO`,
    param1:i,
    param2:a,
    param3:o
  }
}

// ===== xX：CB(7) 解码  @1908306..1908402 =====
xX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e;
  return {
    name:`CB`,
    page:`CB`,
    param1:t,
    param2:n,
    param3:r
  }
}

// ===== SX：DKS(8) 解码  @1908403..1908537 =====
SX=e=> {
  let {
    param1:t
  }=e,
  n=t;
  if(n<0||n>63) {
    console.warn(`DKS鍦板潃绱㈠紩瓒呭嚭鑼冨洿: ${n}锛屾湁鏁堣寖鍥翠负0~63`);
    return
  }return {
    name:`DKS${n}`,
    value:n,
    page:`DKS`
  }
}

// ===== CX：MT(9) 解码  @1908538..1908634 =====
CX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e;
  return {
    name:`MT`,
    page:`MT`,
    param1:t,
    param2:n,
    param3:r
  }
}

// ===== wX：TGL(10) 解码  @1908635..1908696 =====
wX=e=> {
  let {
    param1:t
  }=e;
  return {
    name:`TGL`,
    value:t,
    page:`TGL`
  }
}

// ===== TX：SOCD(11) 解码  @1908697..1908875 =====
TX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e,
  i=t,
  a=n,
  o=r;
  return(i<1||i>4)&&console.warn(`SOCD妯″紡閫夋嫨瓒呭嚭鑼冨洿: ${i}`),
   {
    name:`SOCD`,
    text:`senior_btn2`,
    page:`SOCD`,
    param1:i,
    param2:a,
    param3:o
  }
}

// ===== EX：RS(12) 解码  @1908876..1909042 =====
EX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e,
  i=t,
  a=n,
  o=r;
  return i!==0&&console.warn(`RS杩呮磥妯″紡閫夋嫨涓嶄负0x00: ${i.toString(16)}`),
   {
    name:`RS`,
    page:`RS`,
    param1:0,
    param2:a,
    param3:o
  }
}

// ===== DX：FUNC(13) 解码（24 位 id）  @1909043..1909209 =====
DX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e,
  i=r+(n<<8)+(t<<16);
  return {
    name:sX.find(e=>e.value===i)?.name||`FUNC`,
    text:sX.find(e=>e.value===i)?.text,
    value:i,
    page:`FUNC`
  }
}

// ===== OX：MPT(15) 解码  @1909210..1909308 =====
OX=e=> {
  let {
    param1:t,
    param2:n,
    param3:r
  }=e;
  return {
    name:`MPT`,
    page:`MPT`,
    param1:t,
    param2:n,
    param3:r
  }
}

// ===== kX：FUNC_V2(pageType>=128) 解码（双功能码槽）  @1909309..1909714 =====
kX=e=> {
  let {
    pageType:t,
    param1:n,
    param2:r,
    param3:i
  }=e,
  a=(t&127)<<8|n,
  o=r<<8|i,
  s,
  c;
  if(a!==0&&a<4096) {
    let e=iX.find(e=>e.value===a),
    t=aX.find(e=>e.value===a);
    s=e||t
  }else s=lX.find(e=>e.value===a);
  if(o!==0&&o<4096) {
    let e=iX.find(e=>e.value===o),
    t=aX.find(e=>e.value===o);
    c=e||t
  }else c=lX.find(e=>e.value===o);
  return {
    name:c?.name||s?.name||``,
    text:c?.text||s?.text||``,
    value:o,
    page:`FUNC_V2`,
    param1:a,
    param2:o
  }
}

// ===== AX：END(14) 解码  @1909715..1909801 =====
AX=e=> {
  let {
    param1:t,
    param2:n
  }=e;
  return {
    name:`END`,
    page:`END`,
    param1:t,
    param2:n
  }
},
jX=28

// ===== 配套：512 字节整块的读/写（原文见 docs/protocol_commands.js） =====
// 读：getKeyData  uZ  (GET_KEY=18, contentSize=512)  / getFnKeyData  mZ (GET_FN_KEY=22)
// 写：setKeyData  fZ  (SET_KEY=34, contentSize=512)  / setFnKeyData  gZ (SET_FN_KEY=38)
// 单槽读：getSingleKeyData dZ —— 8 字节自定义头 AA 12 04 <slot*4 lo> <slot*4 hi> 00 00 00，contentSize=4
// 默认矩阵：getDefaultFnKeyMatrix pZ (GET_DEFAULT_FN_KEY_MATRIX=28, contentSize=512)
//           GET_DEFAULT_KEY_MATRIX(31) 在枚举里存在但全库无调用点。
