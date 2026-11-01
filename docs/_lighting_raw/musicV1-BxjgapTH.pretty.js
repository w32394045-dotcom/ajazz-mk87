import {
  n as e
}from"./rolldown-runtime-Dd_uD5pT.js";
import {
  $i as t,Ca as n,Ma as r,Qt as i,Tr as a,aa as o,b as s,ia as c,ka as l,na as u,ot as d,pa as f,pr as p,ra as m,ta as h,xa as g
}from"./layout-classic-CMxiG14P.js";
var _= {
  class:`wh-full`
},v= {
  key:0,class:`flex wh-full`
},y= {
  class:`flex-1 min-w-0 pr-8`
},b= {
  class:`mt-4 mb-12`
},x= {
  class:`mb-4 flex items-center gap-2`
},ee= {
  class:`text-5 text-primary dark:text-white font-medium leading-normal`
},S= {
  ref:`amplitudeRef`,class:`mb-12`
},C= {
  class:`mb-4 flex items-center justify-between gap-4`
},w= {
  class:`flex items-center gap-2 text-[#939393] dark:text-white`
},T= {
  class:`text-4 font-medium`
},E= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},D= {
  key:0,class:`flex-1 min-w-0 pl-8 b-solid b-l-2 b-brand-border`
},O= {
  class:`mt-4 mb-12`
},k= {
  class:`mb-4 flex items-center gap-2`
},A= {
  class:`text-5 text-primary dark:text-white font-medium leading-normal`
},j= {
  ref:`backmodebrightnessRef`,class:`mb-12`
},M= {
  class:`mb-4 flex items-center justify-between gap-4`
},N= {
  class:`flex items-center gap-2 text-[#939393] dark:text-white`
},P= {
  class:`text-4 font-medium`
},F= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},I= {
  key:1,class:`h-full flex flex-col items-center justify-center gap-4 py-12`
},te= {
  class:`m-0 text-6 font-medium text-[#161616] dark:text-white`
},L= {
  class:`m-0 text-4 font-medium text-[#939393] dark:text-white`
},R= {
  class:`flex flex-wrap justify-center gap-6`
},z=o( {
  __name:`musicV1`,props: {
    keyboardConfig: {

    }
  },emits:[`update-key-list`],setup(e, {
    emit:o
  }) {
    let {
      hasDownloadPlugin:d,handleDownload:z,modeList:B,mode:V,amplitude:H,handleModeChange:U,handleAmplitudeChange:W,bgList:G,backmode:K,backmodebrightness:q,handleBackmodeChange:J,handleBrightnessChange:Y,setKeyboardLayout:X
    }=s(e,o);
    return(o,s)=> {
      let Z=p,Q=i,$=a;
      return f(),u(`div`,_,[l(d)?(f(),u(`div`,v,[t(`div`,y,[t(`div`,b,[t(`div`,x,[t(`span`,ee,r(o.$t(`music_text1`)),1)]),c(Z, {
        value:l(V),"onUpdate:value":[s[0]||=e=>n(V)?V.value=e:null,l(U)],options:l(B),class:`w-full`
      },null,8,[`value`,`options`,`onUpdate:value`])]),t(`div`,S,[t(`div`,C,[t(`div`,w,[t(`span`,T,r(o.$t(`music_text3`)),1)]),t(`span`,E,r(l(H))+`%`,1)]),c(Q, {
        value:l(H),"onUpdate:value":[s[1]||=e=>n(H)?H.value=e:null,l(W)],class:`lighting-pane-slider w-full`,min:1,max:100,step:1
      },null,8,[`value`,`onUpdate:value`])],512)]),e.keyboardConfig.musicConfig?.filterMusicMode?.length?h(``,!0):(f(),u(`div`,D,[t(`div`,O,[t(`div`,k,[t(`span`,A,r(o.$t(`music_text2`)),1)]),c(Z, {
        value:l(K),"onUpdate:value":[s[2]||=e=>n(K)?K.value=e:null,l(J)],options:l(G),class:`w-full`
      },null,8,[`value`,`options`,`onUpdate:value`])]),t(`div`,j,[t(`div`,M,[t(`div`,N,[t(`span`,P,r(o.$t(`music_text4`)),1)]),t(`span`,F,r(l(q))+`%`,1)]),c(Q, {
        value:l(q),"onUpdate:value":[s[3]||=e=>n(q)?q.value=e:null,l(Y)],class:`lighting-pane-slider w-full`,min:1,max:100,step:1
      },null,8,[`value`,`onUpdate:value`])],512)]))])):(f(),u(`div`,I,[t(`p`,te,r(o.$t(`music_mode_error`)),1),t(`p`,L,r(o.$t(`music_mode_error2`)),1),t(`div`,R,[c($, {
        type:`primary`,secondary:``,size:`large`,onClick:l(X)
      }, {
        default:g(()=>[s[4]||=t(`i`, {
          class:`i-material-symbols:refresh-rounded mr-2`
        },null,-1),t(`span`,null,r(o.$t(`medium_text13`)),1)]),_:1
      },8,[`onClick`]),c($, {
        type:`primary`,size:`large`,onClick:l(z)
      }, {
        default:g(()=>[m(r(o.$t(`music_btn`)),1)]),_:1
      },8,[`onClick`])])]))])
    }
  }
}),B=e( {
  default:()=>V
}),V=d(z,[[`__scopeId`,`data-v-2ba4bef3`]]);
export {
  B as n,V as t
};
