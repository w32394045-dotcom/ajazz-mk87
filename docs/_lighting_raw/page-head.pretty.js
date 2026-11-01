o, {
  key:0
},aa(d,e=>W(`span`, {
  key:e.mode,class:me([`absolute size-3 rounded-full bg-primary shadow`,e.className]),style:I( {
    cursor:e.cursor
  }),onPointerdown:n=>z(u).startInteraction(e.mode,t,n)
},null,46,Yde)),64)):bs(``,!0)],46,Jde))),128))],34))
}
});
function I9(e) {
  let t=e?.enableGifKeyboardRelay??!1, {
    selectedPreset:n
  }=w9(),r=VV(), {
    currentDevice:i,currentDeviceId:a
  }=HY(), {
    sendReport:o
  }=rY(),s=$I(a, {

  }),c=i?.keyboardConfig,l=K(()=> {
    let e=c.nameSuffix??``;
    return`${c.name}${e}`
  }),u=K(()=>(c.musicConfig?.isEnableAILighting||!1)&&c.musicConfig?.version===2),d=K(()=>c.musicConfig?.isEnableMusicDiy&&c.musicConfig?.version===2),f=K(()=> {
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
        t.disable