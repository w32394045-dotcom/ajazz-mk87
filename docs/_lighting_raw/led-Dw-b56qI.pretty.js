import {
  $i as e,Aa as t,Ea as n,Ma as r,Sa as i,Tr as a,Xi as o,aa as s,ea as c,ha as l,ia as u,ka as d,na as f,p,pa as m,qi as h,ra as g,ta as _,xa as v
}from"./layout-classic-CMxiG14P.js";
import {
  t as ee
}from"./ledCanvas-vb3lTQIs.js";
import {
  t as y
}from"./colorPicker-CPHEf-gj.js";
import {
  t as te
}from"./patternPane-COsR0yk-.js";
var b= {
  class:`flex flex-col h-full`
},x= {
  class:`flex-center shrink-0 h-124 mr-10 b-b-2 border-brand-border`
},S= {
  class:`overflow-hidden inline-block`
},C= {
  class:`flex flex-1 min-h-0`
},w= {
  key:0,class:`flex flex-col min-w-40 shrink-0 b-r-2 border-brand-border h-full`
},T=[`onClick`],E= {
  class:`flex flex-col flex-1 min-w-0 min-h-0`
},D= {
  key:0,class:`flex flex-1 min-h-0 mr-[clamp(0px,calc(30vw-200px),600px)]`
},O= {
  class:`flex-1 px-8 py-4`
},k= {
  class:`text-5 font-medium text-primary mb-4`
},A= {
  class:`flex-1 px-8 py-4 b-l-2 border-brand-border`
},j= {
  class:`text-5 font-medium text-primary mb-4`
},M= {
  key:2,class:`inline-flex flex-col gap-3 w-fit px-8 py-6`
},N=s( {
  __name:`led`,setup(s) {
    let {
      deviceStorage:N,keyboardConfig:P,modeList:F,currentModeName:I,handleChangeMode:L,handleCharTextColorChange:R,handleCharBgColorChange:z,charTextColorHex:B,charBgColorHex:V,voiceModeList:H,handleChangeVoiceMode:U,currentVoiceModeValue:W,brightness:G,maxBrightness:K,handleBrightnessChange:q,previewColors:J,previewSpeed:Y,ledCols:X,ledRows:Z,setPreviewColors:Q
    }=p(),$=n(!1);
    return(n,s)=> {
      let p=a;
      return m(),f(`div`,b,[e(`div`,x,[i(e(`div`,S,[u(ee, {
        colors:d(J),cols:d(X),rows:d(Z),"cell-size":16,speed:d(Y)
      },null,8,[`colors`,`cols`,`rows`,`speed`])],512),[[h,!d($)]]),s[1]||=e(`div`, {
        id:`led-matrix-preview`
      },null,-1)]),e(`div`,C,[d(F).length>1&&!d($)?(m(),f(`div`,w,[(m(!0),f(o,null,l(d(F),(e,i)=>(m(),f(`div`, {
        key:i,class:t([`h-16 px-10 flex-center cursor-pointer text-20px select-none font-medium`,d(I)===e.name?`bg-brand-surface text-primary shadow-[inset_0_4px_4px_rgba(0,0,0,0.05)]`:`b-b-2 border-brand-border text-[#939393]`]),onClick:t=>d(L)(e)
      },r(n.$t(e.text)),11,T))),128))])):_(``,!0),e(`div`,E,[d(I)===`charMode`?(m(),f(`div`,D,[e(`div`,O,[e(`h3`,k,r(n.$t(`gif_text12`)),1),u(y, {
        id:`textColorPicker`,color:d(B),onGetColor:d(R)
      },null,8,[`color`,`onGetColor`])]),e(`div`,A,[e(`h3`,j,r(n.$t(`gif_text13`)),1),u(y, {
        id:`bgColorPicker`,color:d(V),onGetColor:d(z)
      },null,8,[`color`,`onGetColor`])])])):_(``,!0),d(I)===`patternMode`&&d(P).ledConfig?(m(),c(te, {
        key:1,"led-config":d(P).ledConfig,"keyboard-config":d(P),"device-info":d(N).deviceInfo,brightness:d(G),"max-brightness":d(K),"on-preview-update":d(Q),"onUpdate:editing":s[0]||=e=>$.value=e,"onUpdate:brightness":d(q)
      },null,8,[`led-config`,`keyboard-config`,`device-info`,`brightness`,`max-brightness`,`on-preview-update`,`onUpdate:brightness`])):_(``,!0),d(I)===`voiceMode`?(m(),f(`div`,M,[(m(!0),f(o,null,l(d(H),(e,t)=>(m(),c(p, {
        key:t,type:e.value===d(W)?`primary`:`default`,size:`large`,class:`w-full`,onClick:t=>d(U)(e)
      }, {
        default:v(()=>[g(r(e.name),1)]),_:2
      },1032,[`type`,`onClick`]))),128))])):_(``,!0)])])])
    }
  }
});
export {
  N as default
};
