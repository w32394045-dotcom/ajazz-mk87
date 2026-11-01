// ===== CMD  (local HX) =====
HX= {
  COMMUNICATION_START:1,COMMUNICATION_END:2,SET_FACTORY_RESET:15,GET_DEVICE_INFO:16,GET_GAME_MODE:17,GET_KEY:18,GET_LED_EFFECT:19,GET_CUSTOM_LED_DATA:20,GET_MACRO:21,GET_FN_KEY:22,GET_MAGNETIC_AXIS_RT:23,GET_MAGNETIC_AXIS_DKS_DATA:24,GET_LIGHT_BOX:27,GET_DEFAULT_FN_KEY_MATRIX:28,GET_SIDE_LIGHT:29,GET_TRIGGER_KEY:30,GET_DEFAULT_KEY_MATRIX:31,SET_GAME_MODE:33,SET_KEY:34,SET_LED_EFFECT:35,SET_CUSTOM_LED_DATA:36,SET_MACRO:37,SET_FN_KEY:38,SET_MAGNETIC_AXIS_RT:39,SET_MAGNETIC_AXIS_DKS_DATA:40,SET_DOT_MATRIX_MODE:42,SET_LIGHT_BOX:43,SET_SIDE_LIGHT:45,SET_TRIGGER_KEY:46,SET_KEYBOARD_CUSTOM_FUNCTION_ON:48,SET_KEYBOARD_CUSTOM_FUNCTION_OFF:49,GET_LED_DATA:50,GET_ALL_LIGHTS_RGB:51,SET_TEMPORARY_COMMAND_DATA:52,SET_MUSIC_DATA:53,CLEAR_LED_DATA:54,GET_ALL_LIGHTS_RGB_24G:55,GET_ALL_LIGHTS_RGB_24G_64_BYTE:59,SET_MUSIC_DATA_24G_64_BYTE:60,GET_DOT_MATRIX_CONFIG:61,SET_LED_BOOT_ANIMATION:64,SET_LED_USER_ANIMATION:65,SET_LED_DATA:66,SET_TFT_MATERIAL:77,SET_FLASH_DOWNLOAD:79,SET_TFT_USER_ANIMATION:80,SET_TFT_BUILT_IN_INDEX:81,GET_MAGNETIC_AXIS_KEY_STATUS:96,SET_CALIBRATION_ON:100,SET_CALIBRATION_OFF:101,SET_SIMULATION_TEST_ON:102,SET_SIMULATION_TEST_OFF:103,GET_MAGNETIC_AXIS_STATUS:104,SET_CALIBRATION_ON_V2:105,SET_CALIBRATION_OFF_V2:106,OTA_GET_DEVICE_SYSTEM_INFO:128,OTA_VERIFY_FIRMWARE_INFO:129,OTA_DEVICE_ENTER_BOOT:130,OTA_SEND_FIRMWARE_INFO:131,OTA_GET_DEVICE_SN:132,OTA_SWITCH_APP_PARTITION:133,OTA_SET_DEVICE_SN:134,SET_PROFILE:144,GET_DEVICE_NOTIFY:250,GET_MAGNETIC_AXIS_CALIBRATION_DATA:251,GET_24G_DISCONNECT_NOTIFY:252
}

// ===== FACTORY_RESET_TYPE  (local UX) =====
UX= {
  KEY_RESET:1,LIGHTING_RESET:2,MACRO_RESET:4,CLEAR_CALIBRATION:5,RESET_ALL:255
}

// ===== clearCalibration  (local cZ) =====
cZ=async(e,t)=>sZ(e,t,UX.CLEAR_CALIBRATION)

// ===== clearLedData  (local VZ) =====
VZ=async(e,t)=> {
  try {
    let t=BX.deviceStorage.deviceInfo?.frameVersion;
    return await NX(e, {
      cmd:HX.CLEAR_LED_DATA,timeout:t===1?2e3:500
    }),!0
  }catch(e) {
    return console.error(`清除LED数据失败:`,e),!1
  }
}

// ===== deviceInit  (local WX) =====
WX=async(e,t)=> {
  let n=await GX(e,!0,t);
  if(n.tftDirection===255&&t.routesName.includes(`tft`)&&(t.routesName=t.routesName.filter(e=>e!==`tft`)),n.firmwareStatus===1)return {
    deviceInfo:n
  };
  let r=await KX(e),i=await uZ(e,t),a,o,s,c,l,u,d,f,p,m,h,g=``;
  return t.customKeysConfig?.isShowFn&&(m=await mZ(e,t),h=await pZ(e)),t.routesName.includes(`lighting`)&&(a=await _Z(e),o=await yZ(e),t.lightingConfig?.isShowLightBox&&(s=await xZ(e)),t.lightingConfig?.isShowSideLight&&(c=await CZ(e))),t.routesName.includes(`led`)&&(l=await AZ(e)),t.routesName.includes(`macro`)&&(u=await NZ(e)),t.routesName.includes(`performance`)&&(d=await FZ(e)),t.routesName.includes(`trigger`)&&(p=await LZ(e)),t.routesName.includes(`advancedKeys`)&&t.advancedKeysConfig?.advancedKeysList.includes(`DKS`)&&(f=await zZ(e)),n.frameVersion===1&&(g=await nQ(e),BX.deviceStorage.sn=g), {
    deviceInfo:n,gameModeInfo:r,keyData:i,fnKeyData:m,ledEffect:a,customLedData:o,lightBoxData:s,sideLightData:c,ledData:l,macroDataList:u,magneticAxisRT:d,magneticAxisDKS:f,triggerData:p,defaultFnKeyMatrix:h,sn:g
  }
}

// ===== factoryReset  (local sZ) =====
sZ=async(e,t,...n)=> {
  let r=n[0]||255;
  try {
    let t=PX(HX.SET_FACTORY_RESET,r,0,void 0,e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32);
    return await e.sendReport(VX,t),await new Promise(e=>vY(e,100)),!0
  }catch(e) {
    return console.error(`恢复出厂设置失败:`,e),!1
  }
}

// ===== getAllLightsRGB  (local DZ) =====
DZ=async(e,t,n)=> {
  let r=new Uint8Array(512);
  for(let e=0;
  e<128;
  e++) {
    let t=e*4;
    r[t]=e,r[t+1]=0,r[t+2]=0,r[t+3]=0
  }let i=BX.deviceStorage.deviceInfo?.frameVersion,a=await NX(e, {
    cmd:HX.GET_ALL_LIGHTS_RGB,contentSize:512,data:r,abortSignal:n,timeout:i===1?2e3:500
  }),o=new Uint8Array(a.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),s=[];
  for(let e=0;
  e<128;
  e++) {
    let t=e*4,n=o[t],r=o[t+1],i=o[t+2],a=o[t+3];
    s.push( {
      ledId:n,red:r,green:i,blue:a
    })
  }return s
}

// ===== getAllLightsRGB24G  (local OZ) =====
OZ=async(e,t,n,r)=> {
  let i=(e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32)-4,a=n*2+1,o=Math.ceil(a/i),s=[],c=0;
  for(let t=0;
  t<o;
  t++) {
    if(r?.aborted)return Promise.reject( {
      allLightsRgb:[],battery:0
    });
    let n=new Uint8Array(4).fill(0);
    n[0]=170,n[1]=HX.GET_ALL_LIGHTS_RGB_24G,n[2]=t,n[3]=0;
    let a=new Uint8Array(i).fill(0),o=BX.deviceStorage.deviceInfo?.frameVersion,c=await NX(e, {
      cmd:HX.GET_ALL_LIGHTS_RGB_24G,contentSize:i,data:a,headerCount:n.length,customHeader:n,abortSignal:r,timeout:o===1?2e3:500
    });
    s.push(...c)
  }s.length>0&&(c=s[0][3]);
  let l=new Uint8Array(s.flatMap(e=>Array.from(e.slice(4)))).slice(0,n*2),u=[];
  for(let e=0;
  e<n;
  e++) {
    let t=e*2,n=l[t]<<8|l[t+1],r=(n>>11&31)<<3,i=(n>>5&63)<<2,a=(n&31)<<3;
    u.push( {
      red:r,green:i,blue:a
    })
  }return {
    allLightsRgb:u,battery:c
  }
}

// ===== getAllLightsRGB24G64Byte  (local kZ) =====
kZ=async(e,t,n,r)=> {
  if(!n.length)return {
    allLightsRgb:[],battery:0
  };
  let i=(e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||64)-8;
  if(Math.floor(i/2)<=0)return {
    allLightsRgb:[],battery:0
  };
  let a=new Uint8Array(n.length*2);
  n.forEach((e,t)=> {
    let n=t*2;
    a[n]=e&255,a[n+1]=e>>8&255
  });
  let o=await NX(e, {
    cmd:HX.GET_ALL_LIGHTS_RGB_24G_64_BYTE,contentSize:a.length,data:a,abortSignal:r,timeout:2e3,checkAddr:!0
  }),s=0;
  o.length>0&&(s=o[0][5]);
  let c=new Uint8Array(o.flatMap(e=>Array.from(e.slice(8)))).slice(0,n.length*2),l=[];
  for(let e=0;
  e<n.length;
  e++) {
    let t=e*2,r=c[t]<<8|c[t+1],i=(r>>11&31)<<3,a=(r>>5&63)<<2,o=(r&31)<<3;
    l.push( {
      ledId:n[e],red:i,green:a,blue:o
    })
  }return {
    allLightsRgb:l,battery:s
  }
}

// ===== getCustomLEDData  (local yZ) =====
yZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_CUSTOM_LED_DATA,contentSize:512,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),i=[];
  for(let e=0;
  e<128;
  e++) {
    let t=e*4,n=r[t],a=r[t+1],o=r[t+2],s=r[t+3];
    i.push( {
      ledId:n,red:a,green:o,blue:s
    })
  }return BX.deviceStorage.customLedData=i,i
}

// ===== getDefaultFnKeyMatrix  (local pZ) =====
pZ=async e=> {
  try {
    let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
      cmd:HX.GET_DEFAULT_FN_KEY_MATRIX,contentSize:512,maxRetries:1,timeout:t===1?2e3:500
    }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),i=[],a=[];
    for(let e=0;
    e<128;
    e++) {
      let t=e*4,n=r[t],o=r[t+1],s=r[t+2],c=r[t+3];
      if(i.push( {
        pageType:n,param1:o,param2:s,param3:c
      }),n===13) {
        let e=o<<16|s<<8|c;
        e>0&&a.push(e)
      }if(BX.deviceStorage.deviceInfo?.frameVersion>0&&n>=128) {
        let e=(n&127)<<8|o,t=s<<8|c;
        e>0&&a.push(e),t>0&&a.push(t)
      }
    }BX.tempData.defaultFnKeyMatrix=i,BX.tempData.defaultFnFuncIds=a;
    try {
      let {
        useProtocol:e
      }=await Q(async()=> {
        let {
          useProtocol:e
        }=await Promise.resolve().then(()=>$Y);
        return {
          useProtocol:e
        }
      },void 0),t=e();
      t.defaultFnKeyMatrix.value=i,t.defaultFnFuncIds.value=a
    }catch(e) {
      console.warn(`更新 useProtocol defaultFnFuncIds 失败:`,e)
    }return i
  }catch(e) {
    console.warn(`读取默认 FN 矩阵失败（设备可能不支持）:`,e),BX.tempData.defaultFnKeyMatrix=[],BX.tempData.defaultFnFuncIds=[];
    try {
      let {
        useProtocol:e
      }=await Q(async()=> {
        let {
          useProtocol:e
        }=await Promise.resolve().then(()=>$Y);
        return {
          useProtocol:e
        }
      },void 0),t=e();
      t.defaultFnKeyMatrix.value=[],t.defaultFnFuncIds.value=[]
    }catch {

    }return[]
  }
}

// ===== getDeviceInfo  (local GX) =====
GX=async(e,t=!0,n)=> {
  let r=await NX(e, {
    cmd:HX.GET_DEVICE_INFO,contentSize:48
  }),i=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8)))).slice(0,48),a=i[2]|i[3]<<8,o=n?.macroConfig?.isGetMaxMacroSpaceSize?a:512,s= {
    romSize:i[0],macroSpaceSize:o,vid:i[4]|i[5]<<8,pid:i[6]|i[7]<<8,version:(((i[8]&15)+((i[8]&240)>>4)*10+i[9]*100)/100).toFixed(2),sensor:i[10]|i[11]<<8,manufacturer:i[12]|i[13]<<8,product:i[14]|i[15]<<8,workMode:i[16],batteryLevel:i[17],chargeStatus:i[18],currentProfile:i[19],axisInfo:i[20]|i[21]<<8,tftMaxFrames:i[22]|i[23]<<8,gifMaxFrames:i[24]|i[25]<<8,ledMaxFrames:i[26]|i[27]<<8,tftDirection:i[28],rtPrecision:i[29],frameVersion:i[30],lightingVersion:i[31],firmwareStatus:i[32],maxProfile:i[33],tftColorByteOrder:i[35]
  };
  return t&&(BX=dX(),BX.deviceStorage.deviceInfo=s),s
}

// ===== getDeviceSn  (local nQ) =====
nQ=async e=> {
  let t=new Uint8Array(8);
  t[0]=170,t[1]=HX.OTA_GET_DEVICE_SN;
  let n=await NX(e, {
    cmd:HX.OTA_GET_DEVICE_SN,contentSize:56,customHeader:t,headerCount:8,timeout:2e3
  });
  if(!n.length)return``;
  let r=Math.min(n[0][2]||8,56),i=n[0].slice(8,8+r),a=i.length;
  for(;
  a>0&&i[a-1]===0;
  )a--;
  return a===0?``:new TextDecoder(`utf-8`, {
    fatal:!1
  }).decode(i.subarray(0,a))
}

// ===== getDeviceSystemInfo  (local ZZ) =====
ZZ=async e=> {
  let t=new Uint8Array(8).fill(0);
  t[0]=170,t[1]=HX.OTA_GET_DEVICE_SYSTEM_INFO;
  let n=await NX(e, {
    cmd:HX.OTA_GET_DEVICE_SYSTEM_INFO,contentSize:56,headerCount:t.length,customHeader:t,timeout:2e3
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,56),i=r[4]|r[5]<<8,a=r[6]|r[7]<<8,o=r[8],s=r[9],c=`unknown`;
  return o===16?c=`app`:o===48&&(c=`boot`), {
    bootloaderVersion:parseFloat((((r[0]&15)+((r[0]&240)>>4)*10+r[1]*100)/100).toFixed(2)),appVersion:parseFloat((((r[2]&15)+((r[2]&240)>>4)*10+r[3]*100)/100).toFixed(2)),manufacturer:i,product:a,runningArea:c,workMode:s
  }
}

// ===== getDotMatrixMode  (local AZ) =====
AZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_DOT_MATRIX_CONFIG,contentSize:10,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,10),i=[1,2,3].includes(r[8])?r[8]:0,a= {
    bgRGB: {
      r:r[0],g:r[1],b:r[2]
    },textRGB: {
      r:r[3],g:r[4],b:r[5]
    },type:r[6],mode:r[7],dotMatrixMode:i,brightness:r[9]
  };
  return BX.deviceStorage.ledData=a,a
}

// ===== getFnKeyData  (local mZ) =====
mZ=async(e,t)=> {
  let n=BX.deviceStorage.deviceInfo?.frameVersion,r=await NX(e, {
    cmd:HX.GET_FN_KEY,contentSize:512,timeout:n===1?2e3:500
  }),i=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),a=[];
  for(let e=0;
  e<128;
  e++) {
    let t=e*4,n=i[t],r=i[t+1],o=i[t+2],s=i[t+3];
    a.push( {
      pageType:n,param1:r,param2:o,param3:s
    })
  }let o=hX(a,t);
  BX.deviceStorage.fnKeyList=o;
  try {
    let {
      useProtocol:e
    }=await Q(async()=> {
      let {
        useProtocol:e
      }=await Promise.resolve().then(()=>$Y);
      return {
        useProtocol:e
      }
    },void 0),t=e();
    t.fnKeyList.value=o
  }catch(e) {
    console.warn(`更新 useProtocol fnKeyList 失败:`,e)
  }return a
}

// ===== getFnSingleKeyData  (local hZ) =====
hZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=new Uint8Array(8).fill(0);
  a[0]=170,a[1]=HX.GET_FN_KEY,a[2]=4,a[3]=i*4&255,a[4]=i*4>>8&255;
  let o=await NX(e, {
    cmd:HX.GET_FN_KEY,contentSize:4,headerCount:a.length,customHeader:a,timeout:r===1?2e3:500
  }),s=new Uint8Array(o.flatMap(e=>Array.from(e.slice(8)))).slice(0,4),c= {
    pageType:s[0],param1:s[1],param2:s[2],param3:s[3]
  },l=mX(c),u=BX.deviceStorage.fnKeyList||JSON.parse(JSON.stringify(t.keyList)),d=!1;
  for(let e=0;
  e<u.length;
  e++) {
    for(let t=0;
    t<u[e].length;
    t++)if(u[e][t].value===i) {
      l?u[e][t].userKey=l:delete u[e][t].userKey,d=!0;
      break
    }if(d)break
  }BX.deviceStorage.fnKeyList=u;
  try {
    let {
      useProtocol:e
    }=await Q(async()=> {
      let {
        useProtocol:e
      }=await Promise.resolve().then(()=>$Y);
      return {
        useProtocol:e
      }
    },void 0),t=e();
    t.fnKeyList.value=u
  }catch(e) {
    console.warn(`更新 useProtocol fnKeyList 失败:`,e)
  }return[c]
}

// ===== getGameMode  (local KX) =====
KX=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_GAME_MODE,contentSize:56,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,56),i= {
    gameMode:r[1],fnSwitch:r[2],sleepTime:r[3],keyDelay:r[4],reportRate:r[5],systemMode:r[6],tftDisplayTime:r[7],topDeadZone:r[8]/100,bottomDeadZone:r[9]/100,stabilityMode:r[11],autoCalibration:r[14],singleKeyWakeup:r[15],pushButtonMode:r[16],nkroSwitch:r[17],wirelessReportRate:r[18]|r[19]<<8,powerMode:r[20]
  };
  return BX.deviceStorage.gameModeInfo=i,i
}

// ===== getKeyData  (local uZ) =====
uZ=async(e,t)=> {
  let n=BX.deviceStorage.deviceInfo?.frameVersion,r=await NX(e, {
    cmd:HX.GET_KEY,contentSize:512,timeout:n===1?2e3:500
  }),i=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),a=[];
  for(let e=0;
  e<128;
  e++) {
    let t=e*4,n=i[t],r=i[t+1],o=i[t+2],s=i[t+3];
    a.push( {
      pageType:n,param1:r,param2:o,param3:s
    })
  }let o=hX(a,t);
  BX.deviceStorage.keyList=o;
  let s=[];
  t.wheelKeys?.length&&(s=gX(a,t),BX.deviceStorage.wheelKeys=s);
  try {
    let {
      useProtocol:e
    }=await Q(async()=> {
      let {
        useProtocol:e
      }=await Promise.resolve().then(()=>$Y);
      return {
        useProtocol:e
      }
    },void 0),t=e();
    t.keyList.value=o,t.wheelKeys.value=s
  }catch(e) {
    console.warn(`更新 useProtocol keyList 失败:`,e)
  }return a
}

// ===== getLEDEffect  (local _Z) =====
_Z=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_LED_EFFECT,contentSize:16,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,16),i= {
    mode:r[0],red:r[1],green:r[2],blue:r[3],driverSetting:r[4],secondaryRed:r[5],secondaryGreen:r[6],secondaryBlue:r[7],colorMode:r[8],brightness:r[9],speed:r[10],direction:r[11],effectModeType:r[12],checkCodeL:r[14],checkCodeH:r[15]
  };
  return BX.deviceStorage.ledEffect=i,i
}

// ===== getLightBox  (local xZ) =====
xZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_LIGHT_BOX,contentSize:24,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,24),i= {
    mode:r[0],red:r[1],green:r[2],blue:r[3],colorMode:r[8],brightness:r[9],speed:r[10]
  };
  return BX.deviceStorage.lightBoxData=i,i
}

// ===== getMacroData  (local NZ) =====
NZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_MACRO,contentSize:400,addrStart:0,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,400),i=BX?.deviceStorage?.macroDataList||[],a=[];
  for(let n=0;
  n<100;
  n++) {
    let o=n*4,s=r.slice(o,o+4),c=s[0]|s[1]<<8|s[2]<<16|s[3]<<24;
    if(c!==0)try {
      let r=await NX(e, {
        cmd:HX.GET_MACRO,contentSize:4,addrStart:c,timeout:t===1?2e3:500
      }),o=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8)))).slice(0,4),s=o[0]|o[1]<<8,l=Math.floor(s/2),u=[];
      if(l>0) {
        let n=l*4,r=await NX(e, {
          cmd:HX.GET_MACRO,contentSize:n,addrStart:c+4,timeout:t===1?2e3:500
        }),i=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8))));
        for(let e=0;
        e<l;
        e++) {
          let t=e*4,n=i.slice(t,t+4),r=n[0],a=n[1],o=n[2],s=n[3],c=!!(s&128),l=s>>4&7,d=r|a<<8;
          u.push( {
            isPress:c,actionType:l,keyCode:o,delay:d
          })
        }
      }let d=i.find(e=>e.macroId===n);
      a.push( {
        macroId:n,name:d?.name,actions:u
      })
    }catch(e) {
      console.warn(`读取宏ID ${n} 失败:`,e)
    }
  }return BX.deviceStorage.macroDataList=a,a
}

// ===== getMagneticAxisDKSData  (local zZ) =====
zZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=1024,r=await NX(e, {
    cmd:HX.GET_MAGNETIC_AXIS_DKS_DATA,contentSize:n,timeout:t===1?2e3:500
  }),i=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8)))).slice(0,n),a=[];
  for(let e=0;
  e<64;
  e++) {
    let t=e*16;
    if(i[t]===0&&i[t+1]===0&&i[t+2]===0&&i[t+3]===0)continue;
    let n=i[t],r=i[t+1],o=i[t+2],s=i[t+3],c=i[t+5],l=i[t+7],u=i[t+9],d=i[t+11],f=i[t+12],p=i[t+13],m=i[t+14],h=i[t+15],g=e=>( {
      single:e&15,hold:(e&240)>>4
    }),_=g(f),v=g(p),y=g(m),b=g(h),x=[_,v,y,b].map(e=>e.single&1?1:e.hold&1?2:0),S=[_,v,y,b].map(e=>e.single&2?1:e.hold&2?2:0),C=[_,v,y,b].map(e=>e.single&4?1:e.hold&4?2:0),w=[_,v,y,b].map(e=>e.single&8?1:e.hold&8?2:0);
    a.push( {
      index:e,makeValue1:n,makeValue2:r,breakValue1:o,breakValue2:s,action1:c,action2:l,action3:u,action4:d,action1States:x,action2States:S,action3States:C,action4States:w
    })
  }return BX.deviceStorage.magneticAxisDKS=a,a
}

// ===== getMagneticAxisRT  (local FZ) =====
FZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=1024,r=await NX(e, {
    cmd:HX.GET_MAGNETIC_AXIS_RT,contentSize:n,timeout:t===1?2e3:500
  }),i=new Uint8Array(r.flatMap(e=>Array.from(e.slice(8)))).slice(0,n),a=BX.deviceStorage.deviceInfo?.rtPrecision??0,o=a>0?1e3:100,s=a===2?1e3:100,c=[];
  for(let e=0;
  e<128;
  e++) {
    let t=e*8,n=i[t],r=i[t+1],a=!!(r&1),l=!!(r&2),u=i[t+2]|i[t+3]<<8,d=i[t+4]|i[t+5]<<8,f=i[t+6]|i[t+7]<<8;
    c.push( {
      axisType:n,isWholeFast:a,isRampageMode:l,triggerKeyStroke:u/s,pressRT:d/o,releaseRT:f/o
    })
  }return BX.deviceStorage.magneticAxisRT=c,BX.deviceStorage.magneticAxisRTConfig||(BX.deviceStorage.magneticAxisRTConfig= {
    currentModeName:`custom`,customModeRT:c
  }),c
}

// ===== getMagneticAxisStatus  (local iZ) =====
iZ=async(e,t,n,r,i,a)=> {
  try {
    if(a?.aborted)return[];
    let t=e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32,o=n.length*8,s=new Uint8Array(o).fill(0);
    for(let e=0;
    e<o/8;
    e++)s[e*8]=n[e]??0;
    let c=await NX(e, {
      cmd:HX.GET_MAGNETIC_AXIS_STATUS,contentSize:o,data:s,addrStart:r*(t-8),timeout:2e3,isNeedLastPacketFlag:i,checkAddr:!0,abortSignal:a
    }),l=new Uint8Array(c.flatMap(e=>Array.from(e.slice(8)))).slice(0,o),u=[];
    for(let e=0;
    e<n.length;
    e++) {
      let t=e*8;
      if(t+8>l.length)break;
      u.push( {
        keyValue:n[e],calibrationStatus:l[t],adcValue:l[t+1]|l[t+2]<<8,currentStroke:l[t+3]|l[t+4]<<8
      })
    }return u
  }catch(e) {
    return a?.aborted||e instanceof Error&&e.message===`操作已中断`||console.error(`获取磁轴按键状态失败:`,e),[]
  }
}

// ===== getSideLight  (local CZ) =====
CZ=async e=> {
  let t=BX.deviceStorage.deviceInfo?.frameVersion,n=await NX(e, {
    cmd:HX.GET_SIDE_LIGHT,contentSize:24,timeout:t===1?2e3:500
  }),r=new Uint8Array(n.flatMap(e=>Array.from(e.slice(8)))).slice(0,24),i= {
    mode:r[0],red:r[1],green:r[2],blue:r[3],colorMode:r[8],brightness:r[9],speed:r[10]
  };
  return BX.deviceStorage.sideLightData=i,i
}

// ===== getSingleKeyData  (local dZ) =====
dZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=new Uint8Array(8).fill(0);
  a[0]=170,a[1]=HX.GET_KEY,a[2]=4,a[3]=i*4&255,a[4]=i*4>>8&255;
  let o=await NX(e, {
    cmd:HX.GET_KEY,contentSize:4,headerCount:a.length,customHeader:a,timeout:r===1?2e3:500
  }),s=new Uint8Array(o.flatMap(e=>Array.from(e.slice(8)))).slice(0,4),c= {
    pageType:s[0],param1:s[1],param2:s[2],param3:s[3]
  },l=mX(c),u=BX.deviceStorage.keyList||JSON.parse(JSON.stringify(t.keyList)),d=!1;
  for(let e=0;
  e<u.length;
  e++) {
    for(let t=0;
    t<u[e].length;
    t++)if(u[e][t].value===i) {
      l?u[e][t].userKey=l:delete u[e][t].userKey,d=!0;
      break
    }if(d)break
  }BX.deviceStorage.keyList=u;
  try {
    let {
      useProtocol:e
    }=await Q(async()=> {
      let {
        useProtocol:e
      }=await Promise.resolve().then(()=>$Y);
      return {
        useProtocol:e
      }
    },void 0),t=e();
    t.keyList.value=u
  }catch(e) {
    console.warn(`更新 useProtocol keyList 失败:`,e)
  }return[c]
}

// ===== getTriggerConfig  (local LZ) =====
LZ=async e=> {
  let t=await NX(e, {
    cmd:HX.GET_TRIGGER_KEY,contentSize:512,timeout:2e3
  }),n=new Uint8Array(t.flatMap(e=>Array.from(e.slice(8)))).slice(0,512),r=[];
  for(let e=0;
  e<128;
  e++) {
    let t=e*4;
    r.push( {
      isFastTrigger:n[t]===1,triggerPoint:n[t+1],releasePoint:n[t+2],axisType:n[t+3]
    })
  }return BX.deviceStorage.triggerData=r,r
}

// ===== resetAll  (local lZ) =====
lZ=async(e,t)=>sZ(e,t,UX.RESET_ALL)

// ===== sendFirmwareInfo  (local tQ) =====
tQ=async(e,t,n)=> {
  let r=(e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32)-9;
  if(t.byteLength===0)throw RangeError(`OTA 0x83 固件数据不能为空`);
  let i=0,a=0;
  for(;
  a<t.byteLength;
  ) {
    let e=Math.min(r,t.byteLength-a),n=Math.floor(a/4096),o=a+e,s=Math.floor((o-1)/4096);
    n!==s&&(e=4096*s-a),a+=e,i++
  }if(i>65535)throw RangeError(`OTA 0x83 固件体积超出协议上限（总包数须 ≤65535）`);
  let o= {
    ok:!1,status:255,detail:255
  },s=0;
  for(let a=0;
  a<i;
  a++) {
    if(n?.abortSignal?.aborted)return console.error(`OTA 在第 ${a+1} 包前被中止`), {
      ok:!1,status:255,detail:255
    };
    let c=Math.min(r,t.byteLength-s),l=Math.floor(s/4096),u=s+c,d=Math.floor((u-1)/4096);
    l!==d&&(c=4096*d-s);
    let f=t.subarray(s,s+c);
    if(o=await eQ(e,a+1,i,f,t,s,n?.abortSignal),!o.ok)return console.error(`OTA 在第 ${a+1} 包终止发包，异常状态码: ${o.status.toString(16)}`),o;
    if(s+=c,n?.onProgress&&i>0) {
      let e=Math.floor((a+1)/i*100);
      n.onProgress(Math.min(e,99))
    }
  }return o
}

// ===== setCustomLEDData  (local bZ) =====
bZ=async(e,t,...n)=> {
  BX.deviceStorage.deviceInfo?.frameVersion;
  let r=n[0],i=new Uint8Array(512).fill(0);
  for(let e=0;
  e<r.length&&e<128;
  e++) {
    let t=e*4,n=r[e];
    i[t]=e,i[t+1]=n.red,i[t+2]=n.green,i[t+3]=n.blue
  }return await NX(e, {
    cmd:HX.SET_CUSTOM_LED_DATA,contentSize:512,data:i,timeout:2e3
  }),BX.deviceStorage.customLedData=r,!0
}

// ===== setDotMatrixMode  (local jZ) =====
jZ=async(e,t,n= {

})=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion;
  try {
    let t= {
      ...BX.deviceStorage.ledData,...n
    },i=new Uint8Array(10).fill(0);
    return i[0]=t.bgRGB.r,i[1]=t.bgRGB.g,i[2]=t.bgRGB.b,i[3]=t.textRGB.r,i[4]=t.textRGB.g,i[5]=t.textRGB.b,i[6]=t.type,i[7]=t.mode,i[8]=t.dotMatrixMode,i[9]=t.brightness,await NX(e, {
      cmd:HX.SET_DOT_MATRIX_MODE,contentSize:10,data:i,timeout:r===1?2e3:500
    }),BX.deviceStorage.ledData=t,!0
  }catch(e) {
    return console.error(`设置点阵屏内置模式失败:`,e),!1
  }
}

// ===== setFnKeyData  (local gZ) =====
gZ=async(e,t,...n)=> {
  try {
    let t=n[0],r=BX.deviceStorage.deviceInfo?.frameVersion,i=new Uint8Array(512).fill(0);
    for(let e=0;
    e<t.length;
    e++)for(let n=0;
    n<t[e].length;
    n++) {
      let r=t[e][n];
      if(!r)continue;
      let a=r.value;
      a>=0&&a<128&&r.userKey&&pX(i,a*4,r.userKey,`FN层按键`)
    }await NX(e, {
      cmd:HX.SET_FN_KEY,contentSize:512,data:i,timeout:r===1?2e3:500
    }),BX.deviceStorage.fnKeyList=t;
    try {
      let {
        useProtocol:e
      }=await Q(async()=> {
        let {
          useProtocol:e
        }=await Promise.resolve().then(()=>$Y);
        return {
          useProtocol:e
        }
      },void 0),n=e();
      n.fnKeyList.value=t
    }catch(e) {
      console.warn(`更新 useProtocol fnKeyList 失败:`,e)
    }return!0
  }catch(e) {
    return console.error(`写入FN层按键数据失败:`,e),!1
  }
}

// ===== setGameMode  (local qX) =====
qX=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=new Uint8Array(56).fill(0);
  a[1]=i.gameMode||0,a[2]=i.fnSwitch||0,a[3]=i.sleepTime||0,a[4]=i.keyDelay||0,a[5]=i.reportRate||0,a[6]=i.systemMode||0,a[7]=i.tftDisplayTime||0,a[8]=i.topDeadZone*100||0,a[9]=i.bottomDeadZone*100||0,a[11]=i.stabilityMode||0,a[14]=i.autoCalibration||0,a[15]=i.singleKeyWakeup||0,a[16]=i.pushButtonMode||0,a[17]=i.nkroSwitch||0;
  let o=i.wirelessReportRate||0;
  return a[18]=o&255,a[19]=o>>8&255,a[20]=i.powerMode||0,await NX(e, {
    cmd:HX.SET_GAME_MODE,contentSize:56,data:a,timeout:r===1?2e3:500
  }),BX.deviceStorage.gameModeInfo=i,!0
}

// ===== setGifLighting  (local MZ) =====
MZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=n[1],o=typeof n[2]==`function`?n[2]:void 0,s=[];
  for(let e of a)s.push(e.r,e.g,e.b);
  let c=new Uint8Array([...i,...s]),l=t.connectType===`USB`&&await LX(e.productId)||e;
  if(!l)return!1;
  let u=(l?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||4104)-8,d=Math.ceil(c.length/u);
  for(let e=0;
  e<d;
  e++) {
    let n=new Uint8Array(u).fill(0),i=e*u,a=Math.min(i+u,c.length);
    for(let e=i;
    e<a;
    e++)n[e-i]=c[e];
    let s=new Uint8Array(8).fill(0);
    if(s[0]=170,s[1]=HX.SET_LED_DATA,s[2]=e>>8&255,s[3]=e&255,s[4]=d>>8&255,s[5]=d&255,await NX(l, {
      cmd:HX.SET_LED_DATA,contentSize:u,data:n,headerCount:s.length,customHeader:s,timeout:2e3,checkAddr:r===1&&t.connectType===`2.4G`,addrStart:e,parseAddr:e=>e[2]<<8|e[3]
    }),o) {
      let t=Math.floor((e+1)/d*100);
      o(Math.min(t,99))
    }
  }return!0
}

// ===== setKeyData  (local fZ) =====
fZ=async(e,t,...n)=> {
  try {
    let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=n[1],o=new Uint8Array(512).fill(0);
    for(let e=0;
    e<i.length;
    e++)for(let t=0;
    t<i[e].length;
    t++) {
      let n=i[e][t];
      if(!n)continue;
      let r=n.value;
      r>=0&&r<128&&n.userKey&&pX(o,r*4,n.userKey,`键盘按键`)
    }a&&Array.isArray(a)&&a.forEach(e=> {
      if(!e||!e.userKey||e.value<0)return;
      let t=e.value;
      if(t>=0&&t<128) {
        let n=t*4;
        pX(o,n,e.userKey,`滚轮按键`)
      }
    }),await NX(e, {
      cmd:HX.SET_KEY,contentSize:512,data:o,timeout:r===1?2e3:1e3
    }),BX.deviceStorage.keyList=i,a&&Array.isArray(a)&&(t.wheelKeys&&=a,BX.deviceStorage.wheelKeys=a);
    try {
      let {
        useProtocol:e
      }=await Q(async()=> {
        let {
          useProtocol:e
        }=await Promise.resolve().then(()=>$Y);
        return {
          useProtocol:e
        }
      },void 0),t=e();
      t.keyList.value=i,a&&Array.isArray(a)&&(t.wheelKeys.value=a)
    }catch(e) {
      console.warn(`更新 useProtocol keyList 失败:`,e)
    }return!0
  }catch(e) {
    return console.error(`写入按键数据失败:`,e),!1
  }
}

// ===== setLEDEffect  (local vZ) =====
vZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=new Uint8Array(16).fill(0);
  return a[0]=i.mode,a[1]=i.red,a[2]=i.green,a[3]=i.blue,a[4]=255,a[5]=i.secondaryRed,a[6]=i.secondaryGreen,a[7]=i.secondaryBlue,a[8]=i.colorMode,a[9]=i.brightness,a[10]=i.speed,a[11]=i.direction,a[12]=i.effectModeType,a[14]=170,a[15]=85,await NX(e, {
    cmd:HX.SET_LED_EFFECT,contentSize:16,data:a,timeout:r===1?2e3:500
  }),BX.deviceStorage.ledEffect=i,!0
}

// ===== setLedDateTime  (local WZ) =====
WZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=n[1];
  try {
    let t=new Date(i);
    if(isNaN(t.getTime()))return console.error(`无效的时间格式:`,i),!1;
    if(a<0||a>6)return console.error(`无效的星期参数，应为0-6:`,a),!1;
    let n=new Uint8Array(10).fill(0);
    return n[0]=58,n[1]=1,n[2]=90,n[3]=t.getFullYear()%100,n[4]=t.getMonth()+1,n[5]=t.getDate(),n[6]=t.getHours(),n[7]=t.getMinutes(),n[8]=t.getSeconds(),n[9]=a,await NX(e, {
      cmd:HX.SET_TEMPORARY_COMMAND_DATA,data:n,timeout:r===1?2e3:500
    }),!0
  }catch(e) {
    return console.error(`设置点阵屏时间失败:`,e),!1
  }
}

// ===== setLedSyncAnimation  (local HZ) =====
HZ=async(e,t,...n)=> {
  try {
    let t=BX.deviceStorage.deviceInfo?.frameVersion,r=n[0],i=n[1]||!1,a=i?await LX(e.productId):e;
    if(!a)return!1;
    if(!r||r.length===0)return console.error(`无效的rgbData参数`),!1;
    let o=r.length;
    return await NX(a, {
      cmd:HX.SET_LED_DATA,contentSize:o,data:r,responseDevice:a,responseCmd:i?HX.SET_LED_USER_ANIMATION:HX.SET_LED_DATA,timeout:t===1?2e3:500
    }),!0
  }catch(e) {
    return console.error(`设置点阵屏同步动画失败:`,e),!1
  }
}

// ===== setLedUserAnimation  (local UZ) =====
UZ=async(e,t,...n)=> {
  let r=n[0],i=n[1],a=typeof n[2]==`function`?n[2]:void 0,o=[];
  for(let e of i)o.push(e.r,e.g,e.b);
  let s=new Uint8Array([...r,...o]),c=t.connectType===`USB`?await LX(e.productId):e;
  if(!c)return!1;
  let l=(c?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||4104)-8,u=Math.ceil(s.length/l);
  for(let e=0;
  e<u;
  e++) {
    let t=new Uint8Array(l).fill(0),n=e*l,r=Math.min(n+l,s.length);
    for(let e=n;
    e<r;
    e++)t[e-n]=s[e];
    let i=new Uint8Array(8).fill(0);
    if(i[0]=170,i[1]=HX.SET_LED_USER_ANIMATION,i[2]=e>>8&255,i[3]=e&255,i[4]=u>>8&255,i[5]=u&255,await NX(c, {
      cmd:HX.SET_LED_USER_ANIMATION,contentSize:l,data:t,headerCount:i.length,customHeader:i,timeout:2e3
    }),a) {
      let t=Math.floor((e+1)/u*100);
      a(Math.min(t,99))
    }
  }return!0
}

// ===== setLightBox  (local SZ) =====
SZ=async(e,t,...n)=> {
  let r=n[0],i=BX.deviceStorage.deviceInfo?.frameVersion,a=new Uint8Array(24).fill(0);
  return a[0]=r.mode,a[1]=r.red,a[2]=r.green,a[3]=r.blue,a[8]=r.colorMode,a[9]=r.brightness,a[10]=r.speed,await NX(e, {
    cmd:HX.SET_LIGHT_BOX,contentSize:24,data:a,timeout:i===1?2e3:500
  }),BX.deviceStorage.lightBoxData=r,!0
}

// ===== setMacroData  (local PZ) =====
PZ=async(e,t,...n)=> {
  let r=n[0];
  for(let e of r)if(e.macroId<0||e.macroId>=100)throw Error(`宏ID超出范围，应为0-99，当前为${e.macroId}`);
  let i=new Uint8Array(400).fill(0),a=400,o=[];
  for(let e of r) {
    let {
      macroId:t,actions:n
    }=e,r=n.length;
    if(r===0)continue;
    let s=4+r*4,c=new Uint8Array(s).fill(0),l=r*2;
    c[0]=l&255,c[1]=l>>8&255,c[2]=0,c[3]=0;
    for(let e=0;
    e<r;
    e++) {
      let t=n[e],r=4+e*4;
      c[r]=t.delay&255,c[r+1]=t.delay>>8&255,c[r+2]=t.keyCode&255;
      let i=0;
      i=t.actionType===1||t.actionType===2?t.isPress?144:16:t.isPress?176:48,c[r+3]=i
    }let u=t*4;
    u+3<i.length&&(i[u]=a&255,i[u+1]=a>>8&255,i[u+2]=a>>16&255,i[u+3]=a>>24&255),o.push( {
      macroId:t,data:c,size:s
    }),a+=s
  }let s=BX.deviceStorage.deviceInfo?.frameVersion;
  await NX(e, {
    cmd:HX.SET_MACRO,contentSize:400,isNeedLastPacketFlag:!1,addrStart:0,data:i,timeout:s===1?2e3:500
  });
  let c=o.reduce((e,t)=>e+t.size,0);
  if(c>0) {
    let t=new Uint8Array(c),n=0;
    for(let e of o)t.set(e.data,n),n+=e.size;
    await NX(e, {
      cmd:HX.SET_MACRO,contentSize:c,isNeedLastPacketFlag:!0,addrStart:400,data:t,timeout:s===1?2e3:500
    })
  }return BX.deviceStorage.macroDataList=r,!0
}

// ===== setMagneticAxisDKSData  (local BZ) =====
BZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=1024,o=new Uint8Array(a).fill(0);
  return i.forEach(e=> {
    if(e.index<0||e.index>=64) {
      console.warn(`DKS索引超出范围: ${e.index}，跳过此项`);
      return
    }let t=e.index*16;
    o[t]=e.makeValue1&255,o[t+1]=e.makeValue2&255,o[t+2]=e.breakValue1&255,o[t+3]=e.breakValue2&255,o[t+4]=0,o[t+5]=e.action1&255,o[t+7]=e.action2&255,o[t+9]=e.action3&255,o[t+11]=e.action4&255,o[t+6]=0,o[t+8]=0,o[t+10]=0;
    let n=[0,0,0,0];
    for(let t=0;
    t<4;
    t++) {
      let r=0,i=0;
      e.action1States&&e.action1States[t]===1&&(r|=1),e.action1States&&e.action1States[t]===2&&(i|=1),e.action2States&&e.action2States[t]===1&&(r|=2),e.action2States&&e.action2States[t]===2&&(i|=2),e.action3States&&e.action3States[t]===1&&(r|=4),e.action3States&&e.action3States[t]===2&&(i|=4),e.action4States&&e.action4States[t]===1&&(r|=8),e.action4States&&e.action4States[t]===2&&(i|=8),n[t]=r|i<<4
    }o[t+12]=n[0],o[t+13]=n[1],o[t+14]=n[2],o[t+15]=n[3]
  }),await NX(e, {
    cmd:HX.SET_MAGNETIC_AXIS_DKS_DATA,contentSize:a,data:o,timeout:r===1?2e3:500
  }),BX.deviceStorage.magneticAxisDKS=i,!0
}

// ===== setMagneticAxisRT  (local IZ) =====
IZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=1024,o=new Uint8Array(a).fill(0),s=BX.deviceStorage.deviceInfo?.rtPrecision??0,c=s>0?1e3:100,l=s===2?1e3:100;
  for(let e=0;
  e<128&&e<i.length;
  e++) {
    let t=e*8,n=i[e],r=0;
    n.isWholeFast&&(r|=1),n.isRampageMode&&(r|=2);
    let a=Math.round(n.triggerKeyStroke*l),s=Math.round(n.pressRT*c),u=Math.round(n.releaseRT*c);
    o[t]=n.axisType,o[t+1]=r,o[t+2]=a&255,o[t+3]=a>>8&255,o[t+4]=s&255,o[t+5]=s>>8&255,o[t+6]=u&255,o[t+7]=u>>8&255
  }return await NX(e, {
    cmd:HX.SET_MAGNETIC_AXIS_RT,contentSize:a,data:o,timeout:r===1?2e3:500
  }),BX.deviceStorage.magneticAxisRT=i,!0
}

// ===== setMusicData  (local TZ) =====
TZ=async(e,t,...n)=> {
  let r=n[0],i=n[1]||0,a=e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32,o=[i];
  try {
    let n=BX.deviceStorage.deviceInfo?.frameVersion,s=BX.deviceStorage.deviceInfo?.lightingVersion;
    if(t.connectType===`USB`) {
      let t=a-8,s=Math.ceil(r.length/t);
      for(let a=0;
      a<s;
      a++) {
        let c=new Uint8Array(t).fill(0),l=a*t,u=Math.min(l+t,r.length),d=u-l,f=a*t;
        for(let e=l;
        e<u;
        e++)c[e-l]=r[e];
        await NX(e, {
          cmd:HX.GET_LED_DATA,contentSize:d,addrStart:f,timeout:n===1?2e3:50,data:c,otherHeader:a===s-1?o:[i,0]
        })
      }
    }else if(t.connectType===`2.4G`&&a===64&&s===1) {
      let t=a-8,n=Math.floor(r.length/4),i=new Uint8Array(n*2);
      for(let e=0;
      e<n;
      e++) {
        let t=e*4,[n,a]=jV(AV( {
          r:r[t+1]||0,g:r[t+2]||0,b:r[t+3]||0
        }));
        i[e*2]=n,i[e*2+1]=a
      }let s=Math.ceil(i.length/t);
      for(let n=0;
      n<s;
      n++) {
        let r=n*t,a=Math.min(r+t,i.length),c=a-r,l=n*t,u=i.slice(r,a);
        await NX(e, {
          cmd:HX.SET_MUSIC_DATA_24G_64_BYTE,contentSize:c,addrStart:l,data:u,otherHeader:o,maxRetries:0,timeout:10,isNeedLastPacketFlag:n===s-1
        })
      }
    }else {
      let t=[];
      for(let e=0;
      e<r.length/2;
      e++) {
        let n=e*4,[i,a]=jV(AV( {
          r:r[n+1],g:r[n+2],b:r[n+3]
        }));
        t.push(i,a)
      }let n=a-4,o=Math.ceil(t.length/n/2);
      for(let r=0;
      r<o;
      r++) {
        let a=new Uint8Array(n).fill(0),o=r*n,s=Math.min(o+n,t.length);
        for(let e=o;
        e<s;
        e++)a[e-o]=t[e];
        let c=new Uint8Array(4).fill(0);
        c[0]=170,c[1]=HX.SET_MUSIC_DATA,c[2]=r,c[3]=i,await NX(e, {
          cmd:HX.SET_MUSIC_DATA,contentSize:n,maxRetries:0,timeout:10,data:a,headerCount:c.length,customHeader:c
        })
      }
    }return!0
  }catch(e) {
    return console.error(`发送音乐数据失败:`,e),!1
  }
}

// ===== setMusicDataV1  (local EZ) =====
EZ=async(e,t,...n)=> {
  let r=n[0]||0,i=n[1]||0,a=n[2]||0,o=n[3]||[],s=e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32;
  try {
    let t=Array(21).fill(0);
    for(let e=0;
    e<Math.min(o.length,21);
    e++)t[e]=o[e]&255;
    let n=new Uint8Array(s).fill(0);
    n[0]=170,n[1]=HX.SET_MUSIC_DATA,n[2]=0,n[3]=r&255,n[4]=i&255,n[5]=a&255;
    for(let e=0;
    e<21;
    e++)n[6+e]=t[e];
    let c=0;
    for(let e=0;
    e<31;
    e++)c+=n[e];
    return n[31]=c&255,await e.sendReport(0,n),!0
  }catch(e) {
    return console.error(`发送音乐数据失败:`,e),!1
  }
}

// ===== setProfile  (local iQ) =====
iQ=async(e,t,n)=> {
  try {
    let t=new Uint8Array([170,HX.SET_PROFILE,n&255]);
    return(await NX(e, {
      cmd:HX.SET_PROFILE,contentSize:1,customHeader:t,timeout:2e3
    }))[0]?.[2]===n
  }catch(e) {
    return console.error(`切换 Profile 失败:`,e),!1
  }
}

// ===== setSideLight  (local wZ) =====
wZ=async(e,t,...n)=> {
  let r=n[0],i=BX.deviceStorage.deviceInfo?.frameVersion,a=new Uint8Array(24).fill(0);
  return a[0]=r.mode,a[1]=r.red,a[2]=r.green,a[3]=r.blue,a[8]=r.colorMode,a[9]=r.brightness,a[10]=r.speed,await NX(e, {
    cmd:HX.SET_SIDE_LIGHT,contentSize:24,data:a,timeout:i===1?2e3:500
  }),BX.deviceStorage.sideLightData=r,!0
}

// ===== setTftBuiltInIndex  (local qZ) =====
qZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0];
  try {
    if(typeof i!=`number`||i<0)return console.error(`无效的内置索引参数:`,i),!1;
    let n=t.connectType===`USB`?await LX(e.productId):e;
    if(!n)return console.error(`无法获取目标设备`),!1;
    let a=new Uint8Array(1).fill(0);
    return a[0]=i&255,await NX(n, {
      cmd:HX.SET_TFT_BUILT_IN_INDEX,contentSize:1,data:a,timeout:r===1?2e3:50,maxRetries:0
    }),!0
  }catch(e) {
    return console.error(`设置TFT内置索引失败:`,e),!1
  }
}

// ===== setTftDateTime  (local JZ) =====
JZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion,i=n[0],a=n[1];
  try {
    let t=new Date(i);
    if(isNaN(t.getTime()))return console.error(`无效的时间格式:`,i),!1;
    if(a<0||a>6)return console.error(`无效的星期参数，应为0-6:`,a),!1;
    let n=new Uint8Array(10).fill(0);
    return n[0]=90,n[1]=1,n[2]=90,n[3]=t.getFullYear()%100,n[4]=t.getMonth()+1,n[5]=t.getDate(),n[6]=t.getHours(),n[7]=t.getMinutes(),n[8]=t.getSeconds(),n[9]=a,await NX(e, {
      cmd:HX.SET_TEMPORARY_COMMAND_DATA,data:n,timeout:r===1?2e3:500
    }),!0
  }catch(e) {
    return console.error(`设置TFT屏幕时间失败:`,e),!1
  }
}

// ===== setTftMaterial  (local KZ) =====
KZ=async(e,t,...n)=> {
  let r=n[0],i=n[1],a=typeof n[2]==`function`?n[2]:void 0;
  try {
    if(typeof r!=`number`||r<0||r>65535)return console.error(`无效的素材ID:`,r),!1;
    if(!i||i.length===0)return console.error(`无效的素材数据`),!1;
    let n=i instanceof Uint8Array?i:new Uint8Array(i),o=t.connectType===`USB`?await LX(e.productId):e;
    if(!o)return console.error(`无法获取目标设备`),!1;
    let s=(o?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||4104)-8,c=Math.ceil(n.length/s);
    for(let e=0;
    e<c;
    e++) {
      let t=e*s,i=new Uint8Array(s).fill(0);
      i.set(n.subarray(t,Math.min(t+s,n.length)));
      let l=new Uint8Array(8).fill(0);
      if(l[0]=170,l[1]=HX.SET_TFT_MATERIAL,l[2]=e&255,l[3]=e>>8&255,l[4]=c&255,l[5]=c>>8&255,l[6]=r&255,l[7]=r>>8&255,await NX(o, {
        cmd:HX.SET_TFT_MATERIAL,contentSize:s,data:i,headerCount:l.length,customHeader:l,timeout:2e3
      }),a) {
        let t=Math.floor((e+1)/c*100);
        a(Math.min(t,99))
      }
    }return!0
  }catch(e) {
    return console.error(`写入TFT素材失败:`,e),!1
  }
}

// ===== setTftScreenInfo  (local YZ) =====
YZ=async(e,t,...n)=> {
  let r=BX.deviceStorage.deviceInfo?.frameVersion, {
    cpuUsage:i=0,cpuTemp:a=0,gpuUsage:o=0,gpuTemp:s=0,currentTemp:c=0,maxTemp:l=0,minTemp:u=0,weather:d=0,humidity:f=0
  }=n[0]|| {

  };
  try {
    if(i<0||i>100)return console.error(`无效的CPU占用率，应为0-100:`,i),!1;
    if(a<-127||a>127)return console.error(`无效的CPU温度，应为-127到127:`,a),!1;
    if(o<0||o>100)return console.error(`无效的GPU占用率，应为0-100:`,o),!1;
    if(s<-127||s>127)return console.error(`无效的GPU温度，应为-127到127:`,s),!1;
    if(c<-127||c>127)return console.error(`无效的当前气温，应为-127到127:`,c),!1;
    if(l<-127||l>127)return console.error(`无效的最高气温，应为-127到127:`,l),!1;
    if(u<-127||u>127)return console.error(`无效的最低气温，应为-127到127:`,u),!1;
    if(d<0||d>23)return console.error(`无效的天气代码，应为0-23:`,d),!1;
    if(f<0||f>100)return console.error(`无效的湿度，应为0-100:`,f),!1;
    let t=new Uint8Array(24).fill(0);
    return t[6]=90,t[12]=i,t[13]=a&255,t[14]=o,t[15]=s&255,t[16]=c&255,t[17]=l&255,t[18]=u&255,t[19]=d,t[20]=f,await NX(e, {
      cmd:HX.SET_TEMPORARY_COMMAND_DATA,data:t,maxRetries:0,timeout:r===1?2e3:500
    }),!0
  }catch(e) {
    return console.error(`设置TFT屏幕系统信息失败:`,e),!1
  }
}

// ===== setTftUserAnimation  (local GZ) =====
GZ=async(e,t,...n)=> {
  let r=n[0],i=n[1],a=typeof n[2]==`function`?n[2]:void 0;
  try {
    if(!r||!Array.isArray(r)||r.length===0)return console.error(`无效的帧延时数组`),!1;
    if(!i||!Array.isArray(i)||i.length===0)return console.error(`无效的RGB565数据数组`),!1;
    let n=MV(r),o=new Uint8Array(n.length+i.length);
    o.set(n,0),o.set(i,n.length);
    let s=t.connectType===`USB`?await LX(e.productId):e;
    if(!s)return console.error(`无法获取目标设备`),!1;
    let c=(s?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||4104)-8,l=Math.ceil(o.length/c);
    for(let e=0;
    e<l;
    e++) {
      let t=new Uint8Array(c).fill(0),n=e*c,r=Math.min(n+c,o.length);
      for(let e=n;
      e<r;
      e++)t[e-n]=o[e];
      let i=new Uint8Array(8).fill(0);
      if(i[0]=170,i[1]=HX.SET_TFT_USER_ANIMATION,i[2]=e&255,i[3]=e>>8&255,i[4]=l&255,i[5]=l>>8&255,i[6]=80,i[7]=6,await NX(s, {
        cmd:HX.SET_TFT_USER_ANIMATION,contentSize:c,data:t,headerCount:i.length,customHeader:i,timeout:2e3,responseCmd:HX.SET_LED_USER_ANIMATION
      }),a) {
        let t=Math.floor((e+1)/l*100);
        a(Math.min(t,99))
      }
    }return!0
  }catch(e) {
    return console.error(`设置TFT用户动画失败:`,e),!1
  }
}

// ===== setTriggerConfig  (local RZ) =====
RZ=async(e,t,...n)=> {
  let r=n[0],i=new Uint8Array(512).fill(0);
  for(let e=0;
  e<128&&e<r.length;
  e++) {
    let t=e*4,n=r[e];
    n&&(i[t]=+!!n.isFastTrigger,i[t+1]=n.triggerPoint&255,i[t+2]=n.releasePoint&255,i[t+3]=n.axisType)
  }return await NX(e, {
    cmd:HX.SET_TRIGGER_KEY,contentSize:512,data:i,timeout:2e3
  }),BX.deviceStorage.triggerData=r,!0
}

// ===== start24GDisconnectListener  (local XX) =====
XX=(e,t,n)=> {
  try {
    let t=e=> {
      let {
        data:t
      }=e,r=new Uint8Array(t.buffer);
      if(r.length>=3&&r[0]===85&&r[1]===HX.GET_24G_DISCONNECT_NOTIFY&&r[2]===4&&n&&typeof n==`function`)try {
        n()
      }catch(e) {
        console.error(`调用2.4G断开连接回调函数时出错:`,e)
      }
    };
    return e.addEventListener(`inputreport`,t), {
      success:!0,removeListener:()=> {
        e.removeEventListener(`inputreport`,t)
      }
    }
  }catch(e) {
    return console.error(`启动2.4G断开连接监听失败:`,e), {
      success:!1
    }
  }
}

// ===== start24GSleepListener  (local QX) =====
QX=(e,t,n)=> {
  try {
    let t=e=> {
      let {
        data:t
      }=e,r=new Uint8Array(t.buffer);
      if(r.length>=3&&r[0]===85&&r[1]===HX.GET_24G_DISCONNECT_NOTIFY&&r[2]===6&&n&&typeof n==`function`)try {
        n()
      }catch(e) {
        console.error(`调用2.4G休眠回调函数时出错:`,e)
      }
    };
    return e.addEventListener(`inputreport`,t), {
      success:!0,removeListener:()=> {
        e.removeEventListener(`inputreport`,t)
      }
    }
  }catch(e) {
    return console.error(`启动2.4G休眠监听失败:`,e), {
      success:!1
    }
  }
}

// ===== startCalibration  (local eZ) =====
eZ=async(e,t,n)=> {
  let r=PX(HX.SET_CALIBRATION_ON,0,0,void 0,e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32);
  try {
    let t=IX(e, {
      command:HX.SET_CALIBRATION_ON,timeout:1e3
    },e=>e);
    await e.sendReport(VX,r),await t;
    let i=YX(n,`校准数据`);
    return e.addEventListener(`inputreport`,i),!0
  }catch(e) {
    return console.error(`开启校准失败:`,e),!1
  }
}

// ===== startCalibrationV2  (local nZ) =====
nZ=async(e,t)=> {
  try {
    let t=new Uint8Array(8).fill(0);
    return t[0]=170,t[1]=HX.SET_CALIBRATION_ON_V2,await NX(e, {
      cmd:HX.SET_CALIBRATION_ON_V2,contentSize:24,headerCount:t.length,customHeader:t,timeout:2e3
    }),!0
  }catch(e) {
    return console.error(`开启校准（新协议）失败:`,e),!1
  }
}

// ===== startDeviceStateListener  (local XZ) =====
XZ=(e,t,n,r)=> {
  try {
    if(typeof n!=`number`||n<0)return console.error(`无效的设备状态类型:`,n), {
      success:!1
    };
    let t=e=> {
      let {
        data:t
      }=e,i=new Uint8Array(t.buffer);
      if(i.length>=4&&i[0]===85&&i[1]===HX.GET_DEVICE_NOTIFY&&i[2]===n&&r&&typeof r==`function`)try {
        r(i)
      }catch(e) {
        console.error(`调用设备状态回调函数时出错:`,e)
      }
    };
    return e.addEventListener(`inputreport`,t), {
      success:!0,removeListener:()=> {
        e.removeEventListener(`inputreport`,t)
      }
    }
  }catch(e) {
    return console.error(`启动设备状态监听失败:`,e), {
      success:!1
    }
  }
}

// ===== startResetListener  (local ZX) =====
ZX=(e,t,n)=> {
  try {
    let t=e=> {
      let {
        data:t
      }=e,r=new Uint8Array(t.buffer);
      if(r.length>=3&&r[0]===85&&r[1]===HX.GET_24G_DISCONNECT_NOTIFY&&r[2]===5&&n&&typeof n==`function`)try {
        n()
      }catch(e) {
        console.error(`调用重置回调函数时出错:`,e)
      }
    };
    return e.addEventListener(`inputreport`,t), {
      success:!0,removeListener:()=> {
        e.removeEventListener(`inputreport`,t)
      }
    }
  }catch(e) {
    return console.error(`启动重置监听失败:`,e), {
      success:!1
    }
  }
}

// ===== startSimulationTest  (local aZ) =====
aZ=async(e,t,n)=> {
  let r=PX(HX.SET_SIMULATION_TEST_ON,0,0,void 0,e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32);
  try {
    let t=IX(e, {
      command:HX.SET_SIMULATION_TEST_ON,timeout:1e3
    },e=>e);
    await e.sendReport(VX,r),await t;
    let i=YX(n,`模拟测试数据`);
    return e.addEventListener(`inputreport`,i),!0
  }catch(e) {
    return console.error(`开启模拟测试失败:`,e),!1
  }
}

// ===== stopCalibration  (local tZ) =====
tZ=async(e,t)=> {
  try {
    let t=PX(HX.SET_CALIBRATION_OFF,0,0,void 0,e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32);
    return await e.sendReport(VX,t),!0
  }catch(e) {
    return console.error(`结束校准失败:`,e),!1
  }
}

// ===== stopCalibrationV2  (local rZ) =====
rZ=async(e,t)=> {
  try {
    let t=new Uint8Array(8).fill(0);
    return t[0]=170,t[1]=HX.SET_CALIBRATION_OFF_V2,await NX(e, {
      cmd:HX.SET_CALIBRATION_OFF_V2,contentSize:24,headerCount:t.length,customHeader:t,timeout:2e3
    }),!0
  }catch(e) {
    return console.error(`结束校准（新协议）失败:`,e),!1
  }
}

// ===== stopSimulationTest  (local oZ) =====
oZ=async(e,t)=> {
  try {
    let t=PX(HX.SET_SIMULATION_TEST_OFF,0,0,void 0,e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32);
    return await e.sendReport(VX,t),!0
  }catch(e) {
    return console.error(`结束模拟测试失败:`,e),!1
  }
}

// ===== switchAppPartition  (local rQ) =====
rQ=async(e,t)=> {
  let n=t===1?65:66,r=new Uint8Array(8);
  r[0]=170,r[1]=HX.OTA_SWITCH_APP_PARTITION,r[2]=n;
  let i=await NX(e, {
    cmd:HX.OTA_SWITCH_APP_PARTITION,contentSize:24,customHeader:r,headerCount:8,timeout:2e3
  });
  return i.length?i[0][2]===0:!1
}

// ===== verifyFirmwareInfo  (local QZ) =====
QZ=async(e,t,n)=> {
  let r=t&65535,i=n&65535,a=new Uint8Array(8);
  a[0]=170,a[1]=HX.OTA_VERIFY_FIRMWARE_INFO,a[2]=r>>8&255,a[3]=r&255,a[4]=i>>8&255,a[5]=i&255;
  let o=await NX(e, {
    cmd:HX.OTA_VERIFY_FIRMWARE_INFO,contentSize:24,customHeader:a,headerCount:8,timeout:2e3,maxRetries:0
  });
  if(!o.length)return {
    ok:!1,status:255
  };
  let s=o[0][2]??255;
  return {
    ok:s===1,status:s
  }
}
