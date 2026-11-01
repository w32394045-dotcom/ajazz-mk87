rY=()=> {
  let e=HY();
  return {
    sendReport:async(t,n,...r)=> {
      try {
        n||=e.currentDeviceId;
        let i=e.devices.get(n),a=e.currentDevice?.keyboardConfig?.protocol||`default`,o=await nY(Object.assign( {
          "../config/protocols/default/index.ts":()=>Q(()=>Promise.resolve().then(()=>zX),void 0)
        }),`../config/protocols/${a}/index.ts`,5),s=[i?.device,i?.keyboardConfig,...r];
        return await o[t](...s)
      }catch(e) {
        return console.error(`发送${t}报告失败：`,e),null
      }
    },sendReportFromDevice:async(e,t,n=`default`,...r)=> {
      try {
        let i=await nY(Object.assign( {
          "../config/protocols/default/index.ts":()=>Q(()=>Promise.resolve().then(()=>zX),void 0)
        }),`../config/protocols/${n}/index.ts`,5),a=[t,...r];
        return await i[e](...a)
      }catch(t) {
        return console.error(`发送${e}报告失败：`,t),null
      }
    }
  }
}