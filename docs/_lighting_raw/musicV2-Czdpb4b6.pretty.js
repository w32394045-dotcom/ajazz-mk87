import {
  n as e
}from"./rolldown-runtime-Dd_uD5pT.js";
import {
  $i as t,Aa as ee,Ca as n,Ma as r,Qt as te,Tr as ne,Xi as re,Xt as ie,aa as i,ea as a,ha as ae,ia as o,ka as s,na as c,ot as l,pa as u,pr as oe,ra as d,ta as f,xa as p,y as m
}from"./layout-classic-CMxiG14P.js";
var h= {
  class:`wh-full`
},g= {
  key:0,class:`flex wh-full`
},se= {
  key:0,class:`flex-1 min-w-0 pr-8`
},ce= {
  class:`mt-4 mb-12`
},le= {
  class:`mb-4 flex items-center gap-2`
},ue= {
  class:`text-5 text-primary dark:text-white font-medium leading-normal`
},de= {
  class:`flex flex-wrap gap-3`
},_= {
  class:`mt-4`
},v= {
  class:`mb-12`
},y= {
  class:`mb-4 flex items-center gap-2`
},b= {
  class:`text-5 text-primary dark:text-white font-medium leading-normal`
},x= {
  ref:`amplitudeRef`,class:`mb-12`
},S= {
  class:`mb-4 flex items-center justify-between gap-4`
},C= {
  class:`flex items-center gap-2 text-[#939393] dark:text-white`
},w= {
  class:`text-4 font-medium`
},T= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},E= {
  class:`flex-1 min-w-0 pl-8 b-solid b-l-2 b-brand-border`
},D= {
  class:`mt-4 mb-12`
},O= {
  class:`mb-4 flex items-center gap-2`
},k= {
  class:`text-5 text-primary dark:text-white font-medium leading-normal`
},A= {
  ref:`backmodebrightnessRef`,class:`mb-12`
},j= {
  class:`mb-4 flex items-center justify-between gap-4`
},M= {
  class:`flex items-center gap-2 text-[#939393] dark:text-white`
},N= {
  class:`text-4 font-medium`
},P= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},F= {
  key:1,class:`h-full flex flex-col items-center justify-center gap-4 py-12`
},I= {
  class:`m-0 text-6 font-medium text-[#161616] dark:text-white`
},L= {
  class:`m-0 text-4 font-medium text-[#939393] dark:text-white`
},R= {
  class:`flex flex-wrap justify-center gap-6`
},z= {
  key:2,class:`mt-10 b-solid b-t-2 b-brand-border py-8`
},fe= {
  class:`mb-12`
},B= {
  class:`mb-4 flex items-center gap-4`
},V= {
  key:0
},pe= {
  class:`mb-4 flex items-center justify-between gap-4`
},me= {
  class:`text-4 font-medium text-[#939393] dark:text-white`
},H=i( {
  __name:`musicV2`,props: {
    keyboardConfig: {

    }
  },emits:[`update-key-list`],setup(e, {
    emit:i
  }) {
    let {
      hasDownloadPlugin:l,handleDownload:H,handleStartSystemAudio:U,isShowLedMode:W,ledModeList:he,currentFontLedMode:ge,handleClickLedMode:_e,mode:G,modeList:ve,handleModeChange:ye,amplitude:K,handleAmplitudeChange:be,isOpenTestMode:q,testAmplitude:J,backmode:Y,bgList:xe,handleBackmodeChange:Se,backmodebrightness:X,handleBrightnessChange:Ce,startWorker:we,isTestMode:Z
    }=m(e,i);
    return(e,i)=> {
      let m=ne,Q=oe,$=te,Te=ie;
      return u(),c(`div`,h,[s(l)?(u(),c(`div`,g,[s(W)?(u(),c(`div`,se,[t(`div`,ce,[t(`div`,le,[t(`span`,ue,r(e.$t(`dian-zhen-ping-xian-shi-mo-shi`)),1)]),t(`div`,de,[(u(!0),c(re,null,ae(s(he),(e,t)=>(u(),a(m, {
        key:t,type:s(ge)===e.value?`primary`:`default`,size:`medium`,onClick:t=>s(_e)(e)
      }, {
        default:p(()=>[d(r(e.name),1)]),_:2
      },1032,[`type`,`onClick`]))),128))])])])):f(``,!0),t(`div`, {
        class:ee([`flex-1 min-w-0`,s(W)?`px-8 b-solid b-l-2 b-brand-border`:`pr-8`])
      },[t(`div`,_,[t(`div`,v,[t(`div`,y,[t(`span`,b,r(e.$t(`music_text1`)),1)]),o(Q, {
        value:s(G),"onUpdate:value":[i[0]||=e=>n(G)?G.value=e:null,s(ye)],options:s(ve),class:`w-full`
      },null,8,[`value`,`options`,`onUpdate:value`])]),t(`div`,x,[t(`div`,S,[t(`div`,C,[t(`span`,w,r(e.$t(`music_text3`)),1)]),t(`span`,T,r(s(K))+`%`,1)]),o($, {
        value:s(K),"onUpdate:value":[i[1]||=e=>n(K)?K.value=e:null,s(be)],class:`lighting-pane-slider w-full`,min:1,max:100,step:1
      },null,8,[`value`,`onUpdate:value`])],512)])],2),t(`div`,E,[t(`div`,D,[t(`div`,O,[t(`span`,k,r(e.$t(`music_text2`)),1)]),o(Q, {
        value:s(Y),"onUpdate:value":[i[2]||=e=>n(Y)?Y.value=e:null,s(Se)],options:s(xe),class:`w-full`
      },null,8,[`value`,`options`,`onUpdate:value`])]),t(`div`,A,[t(`div`,j,[t(`div`,M,[t(`span`,N,r(e.$t(`music_text4`)),1)]),t(`span`,P,r(s(X))+`%`,1)]),o($, {
        value:s(X),"onUpdate:value":[i[3]||=e=>n(X)?X.value=e:null,s(Ce)],class:`lighting-pane-slider w-full`,min:10,max:100,step:1
      },null,8,[`value`,`onUpdate:value`])],512)])])):(u(),c(`div`,F,[t(`p`,I,r(e.$t(`music_mode_error`)),1),t(`p`,L,r(e.$t(`music_mode_error2`)),1),t(`div`,R,[o(m, {
        type:`primary`,secondary:``,size:`large`,onClick:s(we)
      }, {
        default:p(()=>[i[6]||=t(`i`, {
          class:`i-material-symbols:refresh-rounded mr-2`
        },null,-1),t(`span`,null,r(e.$t(`medium_text13`)),1)]),_:1
      },8,[`onClick`]),o(m, {
        type:`primary`,size:`large`,onClick:s(H)
      }, {
        default:p(()=>[d(r(e.$t(`music_btn`)),1)]),_:1
      },8,[`onClick`]),s(Z)?(u(),a(m, {
        key:0,type:`primary`,size:`large`,onClick:s(U)
      }, {
        default:p(()=>[...i[7]||=[d(` 无需插件 `,-1)]]),_:1
      },8,[`onClick`])):f(``,!0)])])),s(Z)?(u(),c(`div`,z,[t(`div`,fe,[t(`div`,B,[i[8]||=t(`div`, {
        class:`flex items-center gap-2 text-[#939393] dark:text-white`
      },[t(`span`, {
        class:`text-4 font-medium`
      },`测试模式`)],-1),o(Te, {
        value:s(q),"onUpdate:value":i[4]||=e=>n(q)?q.value=e:null
      },null,8,[`value`])]),s(q)?(u(),c(`div`,V,[t(`div`,pe,[i[9]||=t(`div`, {
        class:`flex items-center gap-2 text-[#939393] dark:text-white`
      },[t(`span`, {
        class:`text-4 font-medium`
      },`测试振幅`)],-1),t(`span`,me,r(s(J)),1)]),o($, {
        value:s(J),"onUpdate:value":i[5]||=e=>n(J)?J.value=e:null,class:`lighting-pane-slider w-full`,min:0,max:1e3,step:1
      },null,8,[`value`])])):f(``,!0)])])):f(``,!0)])
    }
  }
}),U=e( {
  default:()=>W
}),W=l(H,[[`__scopeId`,`data-v-d129aadf`]]);
export {
  U as n,W as t
};
