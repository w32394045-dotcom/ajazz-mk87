.then(()=>uX),void 0)
}),`../store/modules/protocols/${r}.ts`,5);
return n.protocolStore.value=e.useProtocolStore(),n.keyList.value=n.protocolStore.value.deviceStorage.keyList,n.fnKeyList.value=n.protocolStore.value.deviceStorage.fnKeyList,n.wheelKeys.value=n.protocolStore.value.deviceStorage.wheelKeys||[],n.defaultFnKeyMatrix.value=n.protocolStore.value.tempData?.defaultFnKeyMatrix||[],n.defaultFnFuncIds.value=n.protocolStore.value.tempData?.defaultFnFuncIds||[],n.protocolStore.value
}catch(e) {
  return console.error(`获取协议存储失败:`,e),null
}
},a=async t=> {
  let r=t||e?.keyboardConfig?.protocol||`default`;
  try {
    let t=await nY(Object.assign( {
      "../config/protocols/default/characters.ts":()=>Q(()=>Promise.resolve().then(()=>nX),void 0)
    }),`../config/protocols/${r}/characters.ts`,5);
    return n.allKeyCharsList.value=t.allKeyChars||[],n.basicList.value=t.basicChars||[],[`jaText`,`jaTextBr`].includes(e?.keyboardConfig?.keyboardLang??``)&&t.jaExtendChars&&(n.basicList.value=[...n.basicList.value,...t.jaExtendChars]),n.extendList.value=t.extendChars||[],n.specialList.value=t.specialChars||[],n.funcList.value=t.funcChars||[],n.funcV2List.value=t.funcV2Chars||[], {
      allKeyChars:n.allKeyCharsList.value,basicChars:n.basicList.value,extendChars:n.extendList.value,specialChars:n.specialList.value,funcChars:n.funcList.value,funcV2Chars:n.funcV2List.value,module:t
    }
  }catch(e) {
    return console.error(`获取协议字符失败:`,e),n.basicList.value=[],n.extendList.value=[],n.specialList.value=[], {
      allKeyChars:[],basicChars:[],extendChars:[],specialChars:[],funcChars:[],module:null
    }
  }
},o=async t=> {
  let r=t||e?.keyboardConfig?.protocol||`default`;
  try {
    let t=await nY(Object.assign( {
      "../config/protocols/default/lighting.ts":()=>Q(()=>import(`./lighting-DzPku7KQ.js`),[])
    }),`../config/protocols/${r}/lighting.ts`,5),i=[...t.defalutLightingModeList];
    if(e?.keyboardConfig?.lightingConfig?.hiddenDefaultEffect?.length&&(i=i.filter(t=>!e?.keyboardConfig?.lightingConfig?.hiddenDefaultEffect?.includes(t.value))),e?.keyboardConfig?.lightingConfig?.customEffect?.length&&t.appendLightingModeList.forEach(t=> {
      e?.keyboardConfig?.lightingConfig?.customEffect?.includes(t.value)&&i.push(t)
    }),e?.keyboardConfig?.lightingConfig?.isSingleColor&&(i=i.map(e=>( {
      ...e,isShowColor:!1
    }))),n.lightingList.value=i.sort((e,t)=>(e.sort||0)-(t.sort||0))||[],n.CUSTOM_LIGHTING_MODE.value=t.CUSTOM_LIGHTING_MODE||128,e?.keyboardConfig?.lightingConfig?.isShowLightBox) {
      let r=t.lightBoxModeList.filter(t=>e?.keyboardConfig?.lightingConfig?.lightBoxList?.includes(t.value));
      n.lightBoxList.value=r.sort((e,t)=>(e.sort||0)-(t.sort||0))||[]
    }else n.lightBoxList.value=[];
    if(e?.keyboardConfig?.lightingConfig?.isShowSideLight) {
      let r=t.sideLightModeList.filter(t=>e?.keyboardConfig?.lightingConfig?.sideLightList?.includes(t.value));
      n.sideLightList.value=r.sort((e,t)=>(e.sort||0)-(t.sort||0))||[]
    }else n.sideLightList.value=[];
    return {
      lightingList:n.lightingList.value,CUSTOM_LIGHTING_MODE:n.CUSTOM_LIGHTING_MODE.value,lightBoxList:n.lightBoxList.value
    }
  }catch(e) {
    return console.error(`获取协议灯光失败:`,e),n.lightingList.value=[],n.CUSTOM_LIGHTING_MODE.value=128, {
      lightingList:[],CUSTOM_LIGHTING_MODE:128
    }
  }
},s=async t=> {
  let r=t||e?.keyboardConfig?.protocol||`default`;
  if(!e?.device)throw Error(`请先连接设备`);
  try {
    let t=await nY(Object.assign( {
      "../config/protocols/default/index.ts":()=>Q(()=>Promise.resolve().then(()=>zX),void 0)
    }),`../config/protocols/${r}/index.ts`,5);
    if(!t.getLEDEffect)throw Error(`当前协议不支持LED特效区功能`);
    let i=await t.getLEDEffect(e.device);
    return n.ledEffect.value=i,n.ledEffect.value
  }catch(e) {
    throw console.error(`获取LED特效设置失败:`,e),e
  }
},c=async t=> {
  let r=t||e?.keyboardConfig?.protocol||`default`;
  if(!e?.device)throw Error(`请先连接设备`);
  try {
    let t=await nY(Object.assign( {
      "../config/protocols/default/index.ts":()=>Q(()=>Promise.resolve().then(()=>zX),void 0)
    }),`../config/protocols/${r}/index.ts`,5);
    if(!t.getCustomLEDData)throw Error(`当前协议不支持自定义LED数据功能`);
    let i=await t.getCustomLEDData(e.device);
    return n.customLedData.value=i,n.customLedData.value
  }catch(e) {
    throw console.error(`获取自定义LED数据失败:`,e),e
  }
},l=async t=> {
  let r=t||e?.keyboardConfig?.protocol||`default`;
  if(!e?.device)throw Error(`请先连接设备`);
  try {
    let t=await nY(Object.assign( {
      "../config/protocols/default/index.ts":()=>Q(()=>Promise.resolve().then(()=>zX),void 0)
    }),`../config/protocols/${r}/index.ts`,5);
    if(!t.getMacroData)throw Error(`当前协议不支持宏功能`);
    let i=await t.getMacroData(e.device);
    n.macroList.value=i;
    let a=n.keyList.value.flat(),o=n.macroList.value.map(t=>( {
      id:t.macroId,name:t.name||`M${t.macroId+1}`,actions:t.actions.map(t=> {
        let r=n.allKeyCharsList.value.find(e=>t.actionType===3&&e.keyCode===t.keyCode)?.name||``;
        return e?.keyboardConfig?.keyboardLang&&(r=a.find(e=>e.keyCode===t.keyCode)?.name||``), {
          name:r,text:n.specialList.value.find(e=>e.page===`MOUSE`&&(t.actionType===1||t.actionType===2)&&e.value===t.keyCode)?.text||``,actionType:t.actionType,value:t.keyCode,isPress:t.isPress,delay:t.delay
        }
      })
    }));
    return n.macroList.value=o,u(),o
  }catch(e) {
    throw console.error(`获取宏数据失败:`,e),n.macroList.value=[],e
  }
},u=()=> {
  if(n.keyList.value&&n.macroList.value) {
    for(let e=0;
    e<n.keyList.value.length;
    e++)for(let t=0;
    t<n.keyList.value[e].length;
    t++) {
      let r=n.keyList.value[e][t];
      if(r.userKey&&r.userKey.page===`MACRO`) {
        let e=r.userKey.value,t=n.macroList.value.find(t=>t.id===e);
        t&&(r.userKey.name=t.name)
      }
    }if(n.fnKeyList.value&&n.fnKeyList.value.length>0)for(let e=0;
    e<n.fnKeyList.value.length;
    e++)for(let t=0;
    t<n.fnKeyList.value[e].length;
    t++) {
      let r=n.fnKeyList.value[e][t];
      if(r.userKey&&r.userKey.page===`MACRO`) {
        let e=r.userKey.value,t=n.macroList.value.find(t=>t.id===e);
        t&&(r.userKey.name=t.name)
      }
    }
  }
},d=async t=> {
  if(t.ledEffect&&(n.ledEffect.value=t.ledEffect),t.customLedData&&(n.customLedData.value=t.customLedData),t.macroDataList) {
    let r=n.keyList.value.flat(),i=t.macroDataList.map(t=>( {
      id:t.macroId,name:t.name||`M${t.macroId+1}`,actions:t.actions.map(t=> {
        let i=n.allKeyCharsList.value.find(e=>t.actionType===3&&e.keyCode===t.keyCode)?.name||``;
        return e?.keyboardConfig?.keyboardLang&&(i=r.find(e=>e.keyCode===t.keyCode)?.name||``), {
          name:i,text:n.specialList.value.find(e=>e.page===`MOUSE`&&(t.actionType===1||t.actionType===2)&&e.value===t.keyCode)?.text||``,actionType:t.actionType,value:t.keyCode,isPress:t.isPress,delay:t.delay
        }
      })
    }));
    n.macroList.value=i,u()
  }
},f=async(e,t)=> {
  await i(e),await a(e),await o(e),t?await d(t):(await s(e),await c(e),await l(e))
};
if(t&&n.lastInitializedDeviceId.value!==t) {
  n.lastInitializedDeviceId.value=t;
  let r=e?.keyboardConfig?.protocol||`default`;
  i(r),a(r),o(r)
}return {
  keyList:n.keyList,fnKeyList:n.fnKeyList,wheelKeys:n.wheelKeys,allKeyChars:n.allKeyCharsList,basicList:n.basicList,extendList:n.extendList,specialList:n.specialList,funcList:n.funcList,funcV2List:n.funcV2List,defaultFnKeyMatrix:n.defaultFnKeyMatrix,defaultFnFuncIds:n.defaultFnFuncIds,lightingList:n.lightingList,lightBoxList:n.lightBoxList,sideLightList:n.sideLightList,CUSTOM_LIGHTING_MODE:n.CUSTOM_LIGHTING_MODE,ledEffect:n.ledEffect,customLedData:n.customLedData,macroList:n.macroList,isShowChars:r,initProtocol:f,setProtocolDataFromDevice