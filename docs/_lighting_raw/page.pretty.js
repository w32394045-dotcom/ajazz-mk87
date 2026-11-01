isEnableAILighting||!1)&&c.musicConfig?.version===2),d=K(()=>c.musicConfig?.isEnableMusicDiy&&c.musicConfig?.version===2),f=K(()=> {
  let e=[ {
    name:`color`,label:$(`color_name`)
  }];
  return c.lightingConfig?.isShowLightBox&&e.push( {
    name:`lightBox`,label:$(`light_box`)
  }),c.lightingConfig?.isShowSideLight&&e.push( {
    name:`sideLight`,label:$(`side_light`)
  }),c.musicConfig&&r&&e.push( {
    name:`music`,label:$(`icon_6`)
  }),d.value&&e.push( {
    name:`musicDiy`,label:$(`music_diy`)
  }),c.lightingConfig?.isShowGifEffect&&e.push( {
    name:`gif`,label:$(`gif_text2`)
  }),u.value&&e.push( {
    name:`aiLighting`,label:$(`ai-lighting`)
  }),e
}),p=R(`color`), {
  keyList:m,lightingList:h,ledEffect:g,customLedData:_,CUSTOM_LIGHTING_MODE:v
}=tX(), {
  toggleKeyGroup:y
}=x7(),b=K(()=> {
  let e=new Set;
  return c.keyList?.forEach(t=> {
    t.forEach(t=> {
      t.disabledLight&&e.add(t.value)
    })
  }),e
}),x=ii(`keyboardRef`),S=ii(`lightingPaneRef`),C=t?ii(`gifLightingRef`):R(null),w=R(!1),T=R(!0),E=K(()=>t&&!!c.lightingConfig?.isShowGifEffect&&p.value===`gif`&&w.value),D=R([]),O=R(!1),k=R(!1),ee=R(!1),A=R(!1),te=K(()=>s.value.lightBoxData||null),j=K(()=>s.value.sideLightData||null),M=K(()=> {
  let e=P.value.length?P.value:m.value;
  return!L.value&&!E.value?e:e.map(e=>e.map(e=>b.value.has(e.value)? {
    ...e,disabled:!0
  }:e))
}),N=null,ne=R(!1),P=sn([]),F=e=> {
  P.value=e
},re=null,ie=null,ae=0,oe=()=>!!c.lightingConfig?.isEnableLightSync&&(p.value===`color`||p.value===`lightBox`||p.value===`sideLight`),se=async()=> {
  if(ne.value||!c.lightingConfig?.isEnableLightSync)return;
  ce(),ie=new AbortController;
  let e=++ae,t=async()=> {
    e===ae&&(await le(),e===ae&&re!==null&&(re=window.setTimeout(t,10)))
  };
  re=window.setTimeout(t,10)
},ce=()=> {
  ae++,ie&&=(ie.abort(),null),re!==null&&(clearTimeout(re),re=null)
},le=async()=> {
  let e=ie;
  if(e&&!e.signal.aborted)try {
    let t=[],n=i?.device?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||64;
    if(c.connectType===`USB`) {
      let n=await o(`getAllLightsRGB`,void 0,e.signal);
      n&&Array.isArray(n)&&(t=n)
    }else if(c.connectType===`2.4G`&&n===64&&s.value?.deviceInfo?.lightingVersion===1) {
      let n=m.value.flatMap(e=>e.map(e=>e.value)),r=await o(`getAllLightsRGB24G64Byte`,void 0,n,e.signal);
      r&&r.allLightsRgb&&Array.isArray(r.allLightsRgb)&&(t=r.allLightsRgb,s.value?.deviceInfo&&(s.value.deviceInfo.batteryLevel=r.battery))
    }else {
      let n=m.value.reduce((e,t)=>e+t.length,0),r=await o(`getAllLightsRGB24G`,void 0,n,e.signal);
      if(r&&r.allLightsRgb&&Array.isArray(r.allLightsRgb)) {
        let e=0,n=r.allLightsRgb;
        m.value.forEach(r=> {
          r.forEach(r=> {
            e<n.length&&(t.push( {
              ledId:r.value,red:n[e].red,green:n[e].green,blue:n[e].blue
            }),e++)
          })
        }),s.value?.deviceInfo&&(s.value.deviceInfo.batteryLevel=r.battery)
      }
    }if(e.signal.aborted||e!==ie)return;
    if(t.length>0) {
      let e=JSON.parse(JSON.stringify(m.value)).map(e=>e.map(e=> {
        if(delete e.userKey,e.name=``,delete e.text,b.value.has(e.value))return delete e.bgColor,e;
        let n=t.find(t=>t.ledId===e.value);
        return n? {
          ...e,bgColor:`rgb(${n.red}, ${n.green}, ${n.blue})`
        }: {
          ...e,bgColor:`#000`
        }
      }));
      P.value=e
    }
  }catch(e) {
    e?.message!==`操作已中断`&&console.error(`获取灯光RGB数据失败:`,e)
  }
},I=()=> {
  let e=g.value;
  if(e&&(A.value=[20,21,128].includes(e.mode),ee.value=A.value||!!h.value.find(t=>t.value===e.mode),e.mode===255&&!ee.value)) {
    let e=h.value.find(e=>e.value===11),t=h.value[0];
    Ce(e??t),ee.value=!0
  }
},ue=()=> {
  I()
},de=!1,fe=!1,pe=async()=> {
  if(g.value&&i?.device) {
    if(de) {
      fe=!0;
      return
    }de=!0,fe=!1;
    try {
      ce(),await o(`setLEDEffect`,a, {
        ...g.value
      })
    }catch(e) {
      console.error(`下发 LED 设置失败:`,e)
    }finally {
      await wV(500),de=!1,fe?(fe=!1,Yn(()=>pe())):oe()&&se()
    }
  }
},me=EI(pe,300),he=e=> {
  g.value&&(Object.assign(g.value,e),ce(),me())
},ge=e=> {
  if(ee.value=e,Ee(),g.value) {
    if(!e) {
      g.value.mode=0,pe();
      return
    }if(h.value.some(e=>e.value===g.value?.mode))pe();
    else {
      let e=h.value[0];
      e&&Ce(e)
    }
  }
};
function _e(e) {
  let t=e.filter(( {
    row:e,col:t
  })=>!c.keyList?.[e]?.[t]?.disabledLight);
  if(D.value=t,Se(),A.value&&S.value&&t.length>0) {
    let e=S.value.getCurrentColor();
    t.forEach(t=> {
      _.value[m.value[t.row][t.col].value].red=e.red,_.value[m.value[t.row][t.col].value].green=e.green,_.value[m.value[t.row][t.col].value].blue=e.blue
    }),S.value.sendLEDCustomDebounced()
  }
}function ve(e) {
  let t=e.filter(( {
    row:e,col:t
  })=>!c.keyList?.[e]?.[t]?.disabledLight);
  E.value&&C.value?.relayParentKeySelect(t),_e(t)
}function ye(e,t) {
  if(E.value) {
    let n=e.filter(( {
      row:e,col:t
    })=>!c.keyList?.[e]?.[t]?.disabledLight);
    C.value?.relayParentKeyPaint(n,t)
  }
}function be() {
  x.value?.selectAll()
}function xe() {
  x.value?.invertSelection()
}function Se() {
  x.value&&L.value?O.value=x.value.isAllSelected():O.value=!1
}let L=K(()=>A.value),Ce=e=> {
  A.value=e.value===v.value,g.value&&(g.value.mode=e.value,g.value.direction=e.directionValue??0,e.value!==v.value&&(O.value=!1),pe())
},we=e=> {
  x.value&&L.value&&(e?x.value.selectAll():x.value.clearSelection())
},Te=e=> {
  k.value=e
},Ee=()=> {
  D.value=[],O.value=!1,x.value?.clearSelection()
};
function De(e) {
  w.value&&!e&&Ee(),w.value=e
}let Oe=e=> {
  D.value.length>0&&(D.value.forEach(t=> {
    _.value[m.value[t.row][t.col].value].red=e.red,_.value[m.value[t.row][t.col].value].green=e.green,_.value[m.value[t.row][t.col].value].blue=e.blue
  }),S.value?.sendLEDCustomDebounced())
},ke=()=> {
  ce()
},Ae=()=> {
  oe()&&se()
},je=(e,t)=> {
  if(!x.value||!L.value)return;
  let n=y(e,t,D.value);
  x.value.selectKeys(n)
};
Cr(L,e=> {
  e?Yn(()=> {
    Se()
  }):O.value=!1
});
let Me=async e=> {
  p.value=e,A.value=!1,D.value=[],O.value=!1,x.value?.clearSelection(),e!==`color`&&(Ne.value=!1),e===`gif`&&g.value&&(g.value.mode=255,await o(`setLEDEffect`,void 0,g.value)),e===`color`&&ue(),oe()?re===null&&(P.value=[],se()):(ce(),P.value=[])
},Ne=R(!1),Pe=R(5),Fe=null,Ie=()=> {
  Le(),h.value.length!==0&&(Fe=window.setInterval(()=> {
    if(!g.value)return;
    let e=(h.value.findIndex(e=>e.value===g.value?.mode)+1)%h.value.length,t=h.value[e];
    Ce(t),o(`setLEDEffect`,void 0,g.value)
  },Pe.value*1e3))
},Le=()=> {
  Fe&&=(clearInterval(Fe),null)
};
return Cr([Ne,Pe],()=> {
  Ne.value?Ie():Le()
}),Cr(f,e=> {
  e.some(e=>e.name===p.value)||Me(e[0].name)
}, {
  immediate:!0
}),Hi(()=> {
  g.value?.mode===255&&c.lightingConfig?.isShowGifEffect?Me(`gif`):ue(),oe()&&se(),N=cQ.on(e=> {
    e.type===`start`?(ne.value=!0,Ee(),ce()):e.type===`finish`&&(ne.value=!1,e.success&&(I(),oe()&&se()))
  })
}),Ki(()=> {
  ce(),Le(),N&&=(N(),null)
}), {
  isWindows:r,keyboardConfig:c,keyboardDisplayName:l,deviceStorage:s,keyList:m,lightingList:h,ledEffect:g,customLedData:_,displayKeyList:M,isCustomLighting:L,selectedKeys:D,handleKeysSelected:_e,handleLightingKeyboardSelect:ve,isCheckedAll:O,isRecord:k,isOpenLight:ee,isCustomMode:A,lightBoxData:te,sideLightData:j,handleUpdateKeyList:F,handleLightingModeChange:Ce,handleCancelSelect:Ee,handleUpdateCheckedAll:we,handleUpdateRecord:Te,handleUpdateOpenLight:ge,handleUpdateSelectedKeysColor:Oe,handleUpdateLedEffectPatch:he,handlePauseLightSync:ke,handleResumeLightSync:Ae,handleToggleKeyGroup:je,activeLightingTab:p,lightingTabs:f,isAiLightingEnabled:u,isMusicDiyEnabled:d,selectedPreset:n,handleTabChange:Me,isTestMode:!1,isAutoSwitchLighting:Ne,autoSwitchInterval:Pe,...t? {
    gifLightingRef:C,gifEditorActive:w,onGifEditingChange:De,gifKeyboardSelectable:E,gifBrushModeEnabled:T,handleGifPaintKeys:ye,handleGifSelectAll:be,handleGifInvertSelect:xe
  }: {

  }
}
}var L9=20,R9=[ {
  id:`default-bar`,type:`bar`,visible:!0,colorMode:`rgb`,color:`#ffffff`,direction:`up`,amplitude:100,count:36,spacing:4,transform: {
    x:.5,y:.5,width:1,height:1
  }
}];
function z9(e) {
  return e.slice(0,L9).map(e=> {
    let t= {
      ...JSON.parse(JSON.stringify(e)),visible:e.visible!==!1,colorMode:e.colorMode===`single`?`single`:`rgb`,transform: {
        x:e.transform.x,y:e.transform.y,width:e.transform.width,height:e.transform.height
      }
    };
    return e.type===`bar`?(t.count=Math.min(50,Math.max(1,Number(e.count??36))),t.spacing=Math.min(10,Math.max(0,Number(e.spacing??4))),delete t.thickness):e.type===`line`?(t.thickness=Math.min(30,Math.max(1,Number(e.thickness??12))),delete t.count,delete t.spacing):(delete t.count,delete t.spacing,delete t.thickness),t
  })
}function Xde() {
  return typeof crypto?.randomUUID==`function`?crypto.randomUUID():`music-diy-${Date.now()}-${Math.random().toString(16).slice(2)}`
}function B9(e,t) {
  let n= {
    id:Xde(),type:e,visible:!0,colorMode:`rgb`,color:`#ffffff`,amplitude:100,transform: {
      x:.5,y:.5,width:1,height:1
    }
  };
  return e===`bar`? {
    ...n,direction:`up`,count:36,spacing:4
  }:e===`line`? {
    ...n,direction:`horizontal`,thickness:12
  }:e===`circle`? {
    ...n,direction:`radial`,transform: {
      ...n.transform,width:.36,height:.58
    }
  }: {
    ...n,direction:`up`
  }
}function V9(e) {
  let t=e.deviceStorage.value.musicDiyConfig?.shapes,n=sn(z9(t?.length?t:R9)),r=R(n.value[0]?.id??``),i=R(0),a=R( {
    low:0,mid:0,high:0
  }),o=R(!1),s=R(!1),c=R(1e3),l=R(!1),u=0,d=!1,f=0,p=null,m=K(()=>n.value.find(e=>e.id===r.value)??null);
  function h() {
    e.deviceStorage.value= {
      ...e.deviceStorage.value,musicDiyConfig: {
        shapes:z9(n.value)
      }
    }
  }function g(e,t) {
    n.value=n.value.map(n=>n.id===e?t(n):n),h()
  }function _(e,t) {
    g(e,e=>( {
      ...e,...t,transform:t.transform? {
        ...e.transform,...t.transform
      }:e.transform
    }))
  }function v(e,t) {
    g(e,e=>( {
      ...e,transform: {
        ...e.transform,...t
      }
    }))
  }function y(e) {
    if(n.value.length>=L9) {
      $message.warning($(`music_diy_limit`,[L9]));
      return
    }let t=B9(e,n.value.length);
    n.value=[...n.value,t],r.value=t.id,h()
  }function b(e) {
    if(n.value.length<=1)return;
    let t=n.value.findIndex(t=>t.id===e);
    n.value=n.value.filter(t=>t.id!==e),r.value=n.value[Math.max(0,t-1)]?.id??n.value[0]?.id??``,h()
  }function x(e) {
    let t=n.value.find(t=>t.id===e);
    if(!t)return;
    let r=B9(t.type,Math.max(0,n.value.indexOf(t)));
    g(e,()=>( {
      ...r,id:e
    }))
  }function S() {
    n.value=z9(R9),r.value=n.value[0]?.id??``,h()
  }function C() {
    let t=e.deviceStorage.value.musicDiyConfig?.shapes;
    n.value=z9(t?.length?t:R9),r.value=n.value[0]?.id??``
  }function w(e) {
    e>0?(f=0,i.value=Math.min(1,e/1e3)):++f>=5&&(i.value=0)
  }async function T() {
    try {
      await U7(),o.value=!0,u||D()
    }catch(e) {
      console.error(`系统音频采集失败:`,e),$message.error(e instanceof Error?e.message:`系统音频采集失败`)
    }
  }async function E() {
    if(!(d||l.value||!dn(e.enabled))) {
      if(G7()) {
        w(K7());
        let e=Pse();
        a.value= {
          low:e.low/1e3,mid:e.mid/1e3,high:e.high/1e3
        },o.value=!0;
        return
      }d=!0;
      try {
        let e=await DY();
        if(typeof e?.amplitude!=`number`)return;
        w(Math.max(0,e.amplitude)),a.value= {
          low:typeof e.low==`number`?Math.min(1,e.low/1e3):i.value,mid:typeof e.mid==`number`?Math.min(1,e.mid/1e3):i.value,high:typeof e.high==`number`?Math.min(1,e.high/1e3):i.value
        },o.value=!0
      }catch {
        o.value=!1,i.value=0,O()
      }finally {
        d=!1
      }
    }
  }function D() {
    u||!dn(e.enabled)||l.value||(E(),u=_Y(()=>void E(),50))
  }function O() {
    u&&=(hY(u),0),d=!1,i.value=0,a.value= {
      low:0,mid:0,high:0
    }
  }function k() {
    o.value=!0,D(),E()
  }function ee() {
    EV(`https://config.driveall.cn/music/v2/Music.exe`)
  }return Cr(()=>dn(e.enabled),e=> {
    e?D():(O(),W7(),EY())
  }, {
    immediate:!0
  }),Cr(s,()=> {
    dn(e.enabled)&&D()
  }),Hi(()=> {
    p=cQ.on(t=> {
      t.type===`start`?(l.value=!0,O()):(l.value=!1,t.success&&C(),dn(e.enabled)&&D())
    })
  }),Gi(()=> {
    O(),W7(),p?.(),p=null,EY()
  }), {
    shapes:n,selectedShapeId:r,selectedShape:m,currentAmplitude:i,frequencyBands:a,hasDownloadPlugin:o,isOpenTestMode:s,testAmplitude:c,isTestMode:!1,selectShape:e=> {
      r.value=e
    },addShape:y,removeShape:b,updateShape:_,updateShapeTransform:v,resetShape:x,resetAllShapes:S,retryPlugin:k,handleDownload:ee,handleStartSystemAudio:T,start:D,stop:O
  }
}var Zde= {
  class:`flex-center mt-20`
},Qde= {
  key:0,class:`overflow-hidden rounded-lg b b-gray-200 dark:b-gray-700`
},$de= {
  key:1,class:`overflow-hidden rounded-lg b b-gray-200 dark:b-gray-700`
},efe= {
  class:`flex-center mx-auto mt-20 w-98% xl:w-80% 2xl:w-60%`
},tfe= {
  key:0,class:`w-full flex gap-5 auto-bg rounded-lg py-10 px-4 mt-5`
},nfe= {
  class:`w-full flex flex-col gap-3`
},rfe= {
  class:`flex items-center mb-3`
},ife= {
  key:0,class:`flex items-center gap-3`
},afe= {
  class:`auto-bg pb-4 rounded-lg`
},ofe=V( {
  __name:`lighting`,setup(e) {
    let {
      isWindows:t,keyboardConfig:n,keyboardDisplayName:r,deviceStorage:i,ledEffect:a,displayKeyList:o,isCustomLighting:s,selectedKeys:c,handleLightingKeyboardSelect:l,isCheckedAll:u,isRecord:d,isOpenLight:f,isCustomMode:p,lightBoxData:m,sideLightData:h,handleUpdateKeyList:g,handleLightingModeChange:_,handleCancelSelect:v,handleUpdateCheckedAll:y,handleUpdateRecord:b,handleUpdateOpenLight:x,handleUpdateSelectedKeysColor:S,handleUpdateLedEffectPatch:C,handlePauseLightSync:w,handleResumeLightSync:T,handleToggleKeyGroup:E,activeLightingTab:D,isAiLightingEnabled:O,isMusicDiyEnabled:k,selectedPreset:ee,handleTabChange:A,isTestMode:te,isAutoSwitchLighting:j,autoSwitchInterval:M
    }=I9(),N=V9( {
      keyboardConfig:()=>n,deviceStorage:i,enabled:K(()=>D.value===`musicDiy`)
    });
    return(e,ne)=> {
      let P=gF,F=OP,re=yF,ie=CF;
      return H(),U(`div`,null,[W(`div`,Zde,[z(D)===`musicDiy`&&z(k)?(H(),U(`div`,Qde,[G(F9, {
        controller:z(N),"keyboard-config":z(n),enabled:z(D)===`musicDiy`,onUpdateKeyList:z(g)
      },null,8,[`controller`,`keyboard-config`,`enabled`,`onUpdateKeyList`])])):z(D)===`aiLighting`&&z(O)?(H(),U(`div`,$de,[G(k9, {
        preset:z(ee),"canvas-width":800,"canvas-height":480,"keyboard-list":z(n).keyList,"keyboard-name":z(r),"keyboard-config":z(n),onUpdateKeyList:z(g)
      },null,8,[`preset`,`keyboard-list`,`keyboard-name`,`keyboard-config`,`onUpdateKeyList`])])):(H(),ls(X$, {
        key:2,ref:`keyboardRef`,"keyboard-list":z(o),clickable:z(s),"multi-select":z(s),"is-record":z(d),"is-show-context-menu":!1,onSelectKeys:z(l)
      },nu