import {
  n as e
}from"./rolldown-runtime-Dd_uD5pT.js";
import {
  $i as t,Aa as n,Ca as r,Ma as i,Qt as a,Xi as o,aa as s,er as c,ha as l,ia as u,ka as d,na as f,ot as p,pa as m,ra as h,ta as g,tr as _,v,xa as y
}from"./layout-classic-CMxiG14P.js";
import {
  t as b
}from"./colorPicker-CPHEf-gj.js";
var x= {
  class:`flex h-full`
},S= {
  class:`w-1/3 pr-8`
},ee= {
  class:`mt-4 mb-8 flex items-center justify-between gap-4`
},C= {
  class:`text-5 text-primary dark:text-white font-medium leading-normal`
},w= {
  class:`grid grid-cols-3 gap-4 mb-6`
},T=[`title`,`onClick`],E= {
  class:`pointer-events-none min-w-0 truncate text-[14px] leading-none font-normal`
},D= {
  key:0,class:`w-1/3 px-8 b-solid b-l-2 b-brand-border`
},O= {
  class:`mt-4 mb-8 text-5 text-primary dark:text-white font-medium leading-normal`
},k= {
  key:0,class:`mb-12`
},A= {
  class:`mb-4 flex items-center gap-2`
},j= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},M= {
  ref:`brightnessRef`,class:`mb-12`
},N= {
  class:`mb-4 flex items-center justify-between gap-4`
},P= {
  class:`flex items-center gap-2 text-[#939393] dark:text-white`
},F= {
  class:`text-4 font-medium`
},I= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},L= {
  key:1,ref:`speedRef`,class:`mb-12`
},R= {
  class:`mb-4 flex items-center justify-between gap-4`
},te= {
  class:`flex items-center gap-2 text-[#939393] dark:text-white`
},z= {
  class:`text-4 font-medium`
},B= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},V= {
  key:1,class:`w-1/3 pl-8 b-solid b-l-2 b-brand-border`
},H= {
  class:`mt-4 mb-4 text-5 text-primary dark:text-white font-medium leading-normal`
},U=s( {
  __name:`sideLight`,props: {
    sideLightData: {

    }
  },emits:[`pauseLightSync`,`resumeLightSync`],setup(e, {
    expose:s,emit:p
  }) {
    let {
      sideLightList:U,currentLightingValue:W,currentLighting:G,currentColor:K,isShowSideLightEdit:q,colorMode:J,brightness:Y,speed:X,minBrightness:Z,maxBrightness:Q,minSpeed:ne,maxSpeed:re,handleChangeLightingMode:ie,handleBrightnessChange:ae,handleSpeedChange:oe,handleColorChange:se,handleColorModeChange:ce,getCurrentColor:$
    }=v(e,p);
    return s( {
      getCurrentColor:$
    }),(e,s)=> {
      let p=_,v=c,$=a;
      return m(),f(`div`,x,[t(`div`,S,[t(`div`,ee,[t(`span`,C,i(e.$t(`lighting`)),1)]),t(`div`,w,[(m(!0),f(o,null,l(d(U),(r,a)=>(m(),f(`div`, {
        key:a,role:`button`,tabindex:`0`,class:n([`box-border flex h-12 min-w-0 cursor-pointer items-center gap-2 rounded-lg border-2 border-solid px-3 transition-colors`,d(W)===r.value?`border-primary bg-primary text-white`:`border-[#939393] bg-brand-bg text-[#939393] dark:text-white hover:bg-primary/10`]),title:e.$t(r.text),onClick:e=>d(ie)(r)
      },[t(`i`, {
        class:n([`pointer-events-none shrink-0 text-[24px] leading-none`,r.icon]),"aria-hidden":`true`
      },null,2),t(`span`,E,i(e.$t(r.text)),1)],10,T))),128))])]),d(q)&&d(W)!==5?(m(),f(`div`,D,[t(`div`,O,i(e.$t(`lighting_edit`)),1),d(G)?.isShowColor?(m(),f(`div`,k,[t(`div`,A,[s[3]||=t(`i`, {
        class:`i-material-symbols:palette-outline shrink-0 text-[32px] text-[#939393] dark:text-white`,"aria-hidden":`true`
      },null,-1),t(`span`,j,i(e.$t(`lighting_color_mode`)),1)]),u(v, {
        value:d(J),"onUpdate:value":[s[0]||=e=>r(J)?J.value=e:null,d(ce)]
      }, {
        default:y(()=>[u(p, {
          value:0,class:`text-primary`
        }, {
          default:y(()=>[h(i(e.$t(`lighting_single_color`)),1)]),_:1
        }),u(p, {
          value:1,class:`ml-12`
        }, {
          default:y(()=>[...s[4]||=[h(`RGB`,-1)]]),_:1
        })]),_:1
      },8,[`value`,`onUpdate:value`])])):g(``,!0),t(`div`,M,[t(`div`,N,[t(`div`,P,[s[5]||=t(`i`, {
        class:`i-material-symbols:brightness-6-outline shrink-0 text-[32px]`,"aria-hidden":`true`
      },null,-1),t(`span`,F,i(e.$t(`lighting_brightness`)),1)]),t(`span`,I,i(d(Y))+i(e.$t(`gif_text14`)),1)]),u($, {
        value:d(Y),"onUpdate:value":[s[1]||=e=>r(Y)?Y.value=e:null,d(ae)],class:`lighting-pane-slider w-full`,step:1,min:d(Z),max:d(Q)
      },null,8,[`value`,`min`,`max`,`onUpdate:value`])],512),d(G)?.isShowSpeed?(m(),f(`div`,L,[t(`div`,R,[t(`div`,te,[s[6]||=t(`i`, {
        class:`i-material-symbols:speed-outline shrink-0 text-[32px]`,"aria-hidden":`true`
      },null,-1),t(`span`,z,i(e.$t(`lighting_speed`)),1)]),t(`span`,B,i(d(X))+i(e.$t(`gif_text14`)),1)]),u($, {
        value:d(X),"onUpdate:value":[s[2]||=e=>r(X)?X.value=e:null,d(oe)],class:`lighting-pane-slider w-full`,step:1,min:d(ne),max:d(re)
      },null,8,[`value`,`min`,`max`,`onUpdate:value`])],512)):g(``,!0)])):g(``,!0),d(G)?.isShowColor?(m(),f(`div`,V,[t(`div`,H,i(e.$t(`lighting_color`)),1),u(b, {
        id:`lightBoxLightingColorPicker`,color:d(K),onGetColor:d(se)
      },null,8,[`color`,`onGetColor`])])):g(``,!0)])
    }
  }
}),W=e( {
  default:()=>G
}),G=p(U,[[`__scopeId`,`data-v-9e2918ab`]]);
export {
  W as n,G as t
};
