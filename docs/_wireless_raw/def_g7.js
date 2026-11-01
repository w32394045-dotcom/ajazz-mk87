function g7(e,t) {
  let n=OF(), {
    sendReport:r
  }=rY(), {
    keyList:i
  }=tX(),a=R(!1),o=R(!1),s=R(0),c=R(``),l=R([]),u=R([]),d=R(),f=K(()=> {
    let t=``;
    return e.keyboardConfig.keyList.forEach(e=> {
      t+=t?`_${e.length}`:e.length
    }),t
  });
  (async()=> {
    let t=e.keyboardConfig?.lightingConfig?.gifEffectIds||[];
    try {
      t.forEach(async e=> {
        let t=await fetch(GV(`/gif-lighting/${e}.json`)).then(e=>e.json());
        l.value.push(t)
      })
    }catch(e) {
      console.warn(`获取GIF内置灯效失败:`,e)
    }
  })(),(async()=> {
    let e=await sQ.default.getItem(`gifLightingList_${f.value}`)||[];
    e.length&&e.forEach(async e=> {
      let t=await sQ.default.getItem(`gifLightingItem_${e}`);
      t&&u.value.push(t)
    })
  })();
  let p=e=>JSON.parse(JSON.stringify(tn(e))),m=e=> {
    c.value=e.gifId
  },h=async()=> {
    let t=d7(),n= {
      gifId:t,name:$(`led_text55`),data:Array(e.keyboardConfig.keyList.flat().length).fill(`#000`),speed:100
    };
    u.value.push(n);
    let r=await sQ.default.getItem(`gifLightingList_${f.value}`)||[];
    r.push(t),await sQ.default.setItem(`gifLightingList_${f.value}`,r),await sQ.default.setItem(`gifLightingItem_${t}`,n)
  },g=async e=> {
    let t=JSON.parse(JSON.stringify(e)),n= {
      gifId:d7(),name:t.text?$(t.text):t.name,data:t.data,speed:t.speed
    };
    u.value.push(n);
    let r=await sQ.default.getItem(`gifLightingList_${f.value}`)||[];
    r.push(n.gifId),await sQ.default.setItem(`gifLightingList_${f.value}`,r),await sQ.default.setItem(`gifLightingItem_${n.gifId}`,n)
  },_=e=> {
    F(),a.value=!0,c.value=e.gifId,d.value=p(e)
  },v=e=> {
    let t=u.value.findIndex(t=>t.gifId===e.gifId);
    t!==-1&&(u.value[t]=p(e))
  },y=()=> {
    a.value=!1,d.value=void 0
  },b=async e=> {
    u.value=u.value.filter(t=>t.gifId!==e.gifId),c.value=``;
    let t=await sQ.default.getItem(`gifLightingList_${f.value}`)||[];
    t.splice(t.indexOf(e.gifId),1),await sQ.default.setItem(`gifLightingList_${f.value}`,t),await sQ.default.removeItem(`gifLightingItem_${e.gifId}`)
  },x=()=>new Promise(t=> {
    $dialog.warning( {
      title:$(`update_title`),content:$(`led_text30`)+e.deviceInfo.gifMaxFrames,positiveText:$(`confirm`),negativeText:$(`cancel`),onPositiveClick:()=> {
        t(!0)
      },onNegativeClick:()=> {
        t(!1)
      }
    })
  }),S=async()=> {
    let t=[...l.value,...u.value].find(e=>e.gifId===c.value);
    if(!t)return;
    let n=e.keyboardConfig.keyList.flat(),i=n.length,a=t.data.length/i;
    if(a>e.deviceInfo.gifMaxFrames&&!await x())return;
    s.value=0,o.value=!0;
    let d=Math.min(a,e.deviceInfo.gifMaxFrames),f=new Uint8Array(4);
    f[0]=d&255,f[1]=d>>8&255,f[2]=Math.ceil(106-t.speed)&255,f[3]=Math.ceil(106-t.speed)>>8&255;
    let p=n.map((e,t)=>e.disabledLight?-1:t).filter(e=>e>=0),m=Array.from( {
      length:d
    },(e,n)=>p.map(e=>RV(t.data[n*i+e]))).flat();
    await r(`setGifLighting`,void 0,f,m,e=> {
      s.value=e
    }),s.value=100,setTimeout(()=> {
      o.value=!1
    },500)
  },C=K(()=>e.keyboardConfig.communityConfig?.communityList?.includes(`gif`)),w=R(!1),T=R(!1),E=R(``),D=R(),O=R(!1),k=$I(`userInfo`, {

  }),ee=e=> {
    if(D.value=e,!Object.keys(k.value).length) {
      O.value=!0;
      return
    }E.value=``,w.value=!0
  },A=()=> {
    D.value&&(E.value=``,w.value=!0)
  },te=async t=> {
    let n=e.keyboardConfig.keyList.flat().length,r=t.data.length/n,i=e.deviceInfo.gifMaxFrames;
    if(i&&r>i&&!await x())return null;
    let a= {
      gifId:t.gifId,name:t.text?$(t.text):t.name,data:i?t.data.slice(0,i*n):t.data,speed:t.speed
    },o=new Blob([JSON.stringify(a)], {
      type:`application/json`
    }),s=await F6(new File([o],`gif_lighting.json`, {
      type:`application/json`
    }));
    return s.code===1?s:($message.error(s.msg||$(`screen_text14`)),null)
  },j=async()=> {
    let t=D.value;
    if(!t)return;
    if(!E.value.trim()) {
      $message.warning($(`tables_title4`)+$(`login_tips3`));
      return
    }let n=e.keyboardConfig.communityConfig?.communityDeviceInfo,r=n?.deviceProductId||e.keyboardConfig.productId,i=n?.deviceName||e.keyboardConfig.name;
    if(!r||!i) {
      $message.error($(`screen_text14`));
      return
    }T.value=!0;
    try {
      let e=await te(t);
      if(!e)return;
      let n=await I6( {
        file_name:t.text?$(t.text):t.name,file_description:E.value.trim(),file_json:[e.data.fullurl],device_id:r,device_model:i,sensitive:0,type:4
      });
      if(n.code!==1) {
        $message.error(n.msg||$(`screen_text14`));
        return
      }w.value=!1,E.value=``,$message.success($(`macro_success`))
    }catch(e) {
      console.error(`分享失败:`,e),$message.error($(`screen_text14`)+(e.message||``))
    }finally {
      T.value=!1
    }
  },M=async e=> {
    let t=u.value.findIndex(e=>e.gifId===c.value);
    t!==-1&&(u.value[t]=p(e),await S())
  },N=null,ne=0,P=()=> {
    let n=[...l.value,...u.value].find(e=>e.gifId===c.value);
    if(!n)return;
    let r=JSON.parse(JSON.stringify(i.value)),a=new Map(r.flat().map(e=>[e.value,e])),o=e.keyboardConfig.keyList,s=o.flat().length,d=Math.floor(n.data.length/s);
    if(d===0)return;
    let f=ne%d*s,p=0;
    o.forEach(e=> {
      e.forEach(e=> {
        let t=a.get(e.value);
        if(t) {
          delete t.userKey,t.name=``,delete t.text;
          let r=n.data[f+p];
          e.disabledLight?delete t.bgColor:r&&(t.bgColor=r)
        }p++
      })
    }),t(`update-key-list`,r),ne++
  },F=()=> {
    N!==null&&(clearInterval(N),N=null),ne=0
  },re=()=> {
    if(a.value)return;
    F();
    let e=[...l.value,...u.value].find(e=>e.gifId===c.value);
    if(!e)return;
    ne=0,P();
    let t=Math.ceil(106-e.speed)*20;
    N=window.setInterval(()=> {
      P()
    },t)
  };
  return Cr(c,e=> {
    e?re():(F(),t(`update-key-list`,[]))
  }),Cr(a,e=> {
    e?F():c.value&&re()
  }),Cr(l,e=> {
    e.length>0&&!c.value&&(c.value=e[0].gifId)
  }, {
    deep:!0
  }),Ki(()=> {
    F()
  }), {
    themeVars:n,isShowEdit:a,syncDialogVisible:o,syncProgress:s,currentGifId:c,builtInGifList:l,customGifList:u,editGif:d,handleClickGifLighting:m,handleAddGifLighting:h,handleCopyGifLighting:g,handleEditGifLighting:_,handleDeleteGifLighting:b,handleApplyGifLighting:S,handleUploadGifLighting:M,mergeEditorSaveToCustomList:v,closeGifEditor:y,isShowShare:C,isShare:w,shareLoading:T,shareDescription:E,showLoginModal:O,handleShare:ee,handleAddShare:j,handleLoginSuccess:A
  }
}