 {
  let e=eY(),t=Kt(new Map),n=R(``),r=K(()=>t.get(n.value)),i=R(!1),a=R(!1),o=R(!!navigator.hid),s=$I(`historyConnect`, {

  }), {
    sendReport:c,sendReportFromDevice:l
  }=rY(), {
    startGetTftInfo:u,stopGetTftInfo:d
  }=RY(),f=R(!1),p=R(!1),m=R(!1),h=R(!1),g=R(``),_=R(null),v=R(null),y=R(null),b=R(null),x=R(null),S=`1452:591:2.4G Dongle,1452:592:2.4G Dongle,1452:591:2.4G Wireless Receiver,3141:65278:2.4G Dongle,3141:65276:HS USB Dongle,3141:65278:2.4G Wireless Receiver,3141:65274:2.4G Wireless Receiver,3141:65273:HS USB Dongle,3141:65276:2.4G Wireless Receiver,3141:65273:BOOM68Ultra-2.4G,3141:65278:VOICSKY KB,3141:65276:AULA F108ProV2 Dongle,3141:65274:2.4G Dongle,3141:65273:2.4G Dongle,3141:65276:2.4G Dongle,3141:65276:2.4Ghz KB Dongle,3141:65276:AEMEATH 2.4G,3141:65278:Womier L98 2.4G,3141:65278:Fantech Atom HE68 PRO,3141:65278:8K Wireless Receiver,3141:65276:8K Wireless Receiver,3141:65273:8K Wireless Receiver,3141:65278:AULA NOVA98 Dongle,3141:65276:AULA NOVA98 Dongle,3141:65273:AULA NOVA98 Dongle,3141:65278:BOOM68Pro-2.4G,3141:65273:2.4G Wireless Receiver,3141:65276:BOOM68Ultra-2.4G,3141:65276:AULA NOVA87 Dongle,3141:65278:AULA NOVA87 Dongle,3141:65274:AULA NOVA87 Dongle,3141:65273:AULA NOVA87 Dongle,3141:65273:X87Pro,3141:65278:AULA F87 HS 2.4G,3141:65274:AULA F87 HS 2.4G,3141:65273:AULA F87 HS 2.4G,3141:65276:AULA F87 HS 2.4G,3141:65274:QSENN 2.4G,3141:65273:QSENN 2.4G,3141:65276:QSENN 2.4G,3141:65278:QSENN 2.4G,3141:65278:ABKO 2.4G,3141:65274:ABKO 2.4G,3141:65273:ABKO 2.4G,3141:65276:ABKO 2.4G,3141:65278:ABKO A108K 2.4G,3141:65274:ABKO A108K 2.4G,3141:65273:ABKO A108K 2.4G,3141:65276:ABKO A108K 2.4G,3141:36880:2.4G 8K Dongle,3141:59392:2.4G 8K Dongle,3141:65274:2.4G Wireless Keyboard,3141:65273:2.4G Wireless Keyboard,3141:65278:2.4G Wireless Keyboard,3141:65276:2.4G Wireless Keyboard,1452:592:2.4G Wireless Receiver,3141:65274:Langtu T87-2.4G,3141:65273:Wireless 2.4G Keyboard,3141:65274:Wireless 2.4G Keyboard,3141:65273:X75GC,3141:65274:QSENN2.4,3141:65273:QSENN2.4,3141:65276:QSENN2.4,3141:65278:QSENN2.4`.split(`,`);
  function C(e) {
    s.value= {
      productName:e.productName||``,productId:e.productId,vendorId:e.vendorId,usagePage:e.collections?.[0]?.usagePage||0
    }
  }async function w(e=[]) {
    if(!o.value)return!1;
    try {
      await D();
      let a=await navigator.hid.requestDevice( {
        filters:e
      }),o=!1;
      i.value=!0;
      for(let e of a) {
        if(o)break;
        let r=`${e.vendorId}:${e.productId}:${e.productName}`;
        if(!(a.length>1&&!re(e))) {
          if(S.includes(r)) {
            let t=await oe(e);
            t&&(r=t),await wV(100)
          }if(C(e),t.has(r)) {
            let e=t.get(r);
            await e.device.open(),e.isConnected=!0
          }else {
            await e.open();
            let n= {
              device:e,isConnected:!0,keyboardConfig:await ae(r)
            };
            if(!n.keyboardConfig)return await e.forget(),!1;
            t.set(r,n)
          }n.value=r,o=!0
        }
      }return r.value?.keyboardConfig?.otherConfig?.isJumpOldDrive?(A(),!1):(o&&await M(n.value),o&&r.value?.keyboardConfig?.connectType===`2.4G`&&(await te(n.value),await N(n.value),await ne(n.value)),o&&r.value?.keyboardConfig?.tftConfig?.isShowTftInfo&&await P(n.value),o)
    }catch(e) {
      return console.error(`请求连接新的设备失败: ${e}`),!1
    }finally {
      i.value=!1
    }
  }async function T(e) {
    await D();
    let r=t.get(e);
    if(r) {
      if(await r.device.open(),C(r.device),r.isConnected=!0,n.value=e,r.keyboardConfig?.otherConfig?.isJumpOldDrive) {
        A();
        return
      }await M(e),r.keyboardConfig?.connectType===`2.4G`&&(await te(e),await N(e),await ne(e)),r.keyboardConfig?.tftConfig?.isShowTftInfo&&await P(e)
    }
  }async function E(e) {
    let r=t.get(e);
    r&&r.device.opened&&await r.device.close(),n.value===e&&(n.value=``,_.value&&=(_.value(),null),y.value&&=(y.value(),null),b.value&&=(b.value(),null),m.value=!1,x.value&&=(x.value(),null),d())
  }async function D() {
    for(let e of t.keys())await E(e);
    n.value=``
  }function O(e) {
    let r=e.device,i=`${r.vendorId}:${r.productId}:${r.productName}`,a=i;
    if(S.includes(i)) {
      for(let[e,n]of t.entries())if(n.device===r) {
        a=e;
        break
      }
    }if(t.has(a)) {
      if(h.value&&a===n.value) {
        let e=t.get(a);
        e&&(e.isConnected=!1),console.log(`[OTA] 设备断开（等待重启重连）: ${a}`);
        return
      }k(a),console.log(`HID 设备已断开连接: ${a}`)
    }
  }function k(r) {
    t.delete(r),n.value===r&&(n.value=``,m.value=!1),s.value= {

    },setTimeout(()=> {
      e.replace( {
        path:`/`
      }),$message.error($(`link_state`))
    },1500)
  }async function ee(e,n=15e3) {
    if(!o.value)return null;
    let[r,i,a]=e.split(`:`),s=Number(r),c=Number(i),l=t.get(e)?.device??null,u=e=>e!==l&&e.vendorId===s&&e.productId===c&&e.productName===a&&re(e),d=async n=> {
      try {
        n.opened||await n.open();
        let r=t.get(e);
        return r&&(r.device=n,r.isConnected=!0),!0
      }catch(e) {
        return console.error(`[OTA] 重新打开设备失败:`,e),!1
      }
    };
    return new Promise(e=> {
      let t=!1,r=n=> {
        t||(t=!0,navigator.hid.removeEventListener(`connect`,i),clearInterval(o),clearTimeout(s),e(n))
      },i=async e=> {
        t||u(e.device)&&await d(e.device)&&r(e.device)
      };
      navigator.hid.addEventListener(`connect`,i);
      let a=async()=> {
        if(!t)try {
          let e=await navigator.hid.getDevices();
          for(let t of e)if(u(t)) {
            await d(t)&&r(t);
            return
          }
        }catch(e) {
          console.warn(`[OTA] 扫描已授权设备失败:`,e)
        }
      },o=setInterval(a,500),s=setTimeout(()=>r(null),n);
      a()
    })
  }function A() {
    location.href=location.href+`hub/#/?productId=${r.value?.device.productId}&vendorId=${r.value?.device.vendorId}&productName=${r.value?.device.productName}`
  }async function te(e) {
    _.value&&=(_.value(),null);
    let t=await c(`start24GDisconnectListener`,e,j);
    t&&typeof t==`object`&&`removeListener`in t&&(_.value=t.removeListener)
  }function j() {
    if(!p.value) {
      if(p.value=!0,_.value&&=(_.value(),null),y.value&&=(y.value(),null),b.value&&=(b.value(),null),m.value=!1,n.value&&t.has(n.value)) {
        let e=t.get(n.value);
        e.isConnected=!1
      }s.value= {

      },setTimeout(()=> {
        e.replace( {
          path:`/`
        }),p.value=!1,$message.error($(`link_state`))
      },1500)
    }
  }async function M(e) {
    v.value&&=(v.value(),null);
    let n=await c(`startResetListener`,e,async()=> {
      if(t.get(e)?.keyboardConfig?.routesName.includes(`performance`)) {
        let {
          updateCurrentProfile:t
        }=await Q(async()=> {
          let {
            updateCurrentProfile:e
          }=await Promise.resolve().then(()=>oQ);
          return {
            updateCurrentProfile:e
          }
        },void 0),n=$I(e, {

        });
        n.value.magneticAxisRTConfig&&(n.value.magneticAxisRTConfig=void 0,await t(e))
      }location.reload()
    });
    n&&typeof n==`object`&&`removeListener`in n&&(v.value=n.removeListener)
  }async function N(e) {
    y.value&&=(y.value(),null);
    let t=await c(`start24GSleepListener`,e,async()=> {
      console.log(`休眠了`),m.value=!0
    });
    t&&typeof t==`object`&&`removeListener`in t&&(y.value=t.removeListener)
  }async function ne(e) {
    b.value&&=(b.value(),null);
    let t=await c(`start24GWakeListener`,e,async()=> {
      console.log(`唤醒了`),m.value=!1
    });
    t&&typeof t==`object`&&`removeListener`in t&&(b.value=t.removeListener)
  }async function P(e) {
    x.value&&=(x.value(),null);
    let t=null,n=await c(`startDeviceStateListener`,e,6,e=> {
      let n=e[3]===1;
      n!==t&&(t=n,n?u():d())
    });
    n&&typeof n==`object`&&`removeListener`in n&&(x.value=n.removeListener)
  }async function F(e=!0) {
    if(!o.value)return!1;
    if(h.value)return console.log(`[OTA] 升级中，跳过 reconnectDevices`),!1;
    i.value=!0;
    try {
      e&&await D();
      let i=await navigator.hid.getDevices();
      if(!i.length)return!1;
      let a=s.value,o=a&&`vendorId`in a&&`productId`in a;
      if(!o)return!1;
      let c=i.filter(e=>re(e)),l=new Map,u=[...c];
      o&&u.sort((e,t)=>e.vendorId===a.vendorId&&e.productId===a.productId?-1:+(t.vendorId===a.vendorId&&t.productId===a.productId));
      let d=!1;
      for(let e=0;
      e<u.length;
      e++) {
        let r=u[e],i=`${r.vendorId}:${r.productId}:${r.productName}`;
        if(e===0&&S.includes(i)) {
          let e=l.get(i);
          if(e)i=e;
          else try {
            r.opened&&await r.close(),await wV(100),i=await oe(r),await wV(100),i&&l.set(`${r.vendorId}:${r.productId}:${r.productName}`,i)
          }catch(e) {
            console.error(`获取完整设备ID失败:`,e);
            continue
          }
        }if(e===0&&!o&&C(r),!S.includes(i))try {
          if(t.has(i)) {
            let e=t.get(i);
            e.device.opened||await e.device.open(),e.isConnected=!0
          }else {
            r.opened&&(await r.close(),await wV(50)),await r.open();
            let e= {
              device:r,isConnected:!0,keyboardConfig:await ae(i)
            };
            t.set(i,e)
          }
        }catch(e) {
          console.error(`打开设备失败:`,e);
          continue
        }e===0&&(n.value=i,d=!0)
      }return d&&await M(n.value),d&&r.value?.keyboardConfig?.connectType===`2.4G`&&(await te(n.value),await N(n.value),await ne(n.value)),d&&r.value?.keyboardConfig?.tftConfig?.isShowTftInfo&&await P(n.value),d
    }catch(e) {
      return console.error(`重新连接设备失败: ${e}`),!1
    }finally {
      i.value=!1
    }
  }function re(e) {
    let t=e.collections||[];
    return t.length!==0&&t.some(e=>[65384,65408,65376,65280,65281,65307].includes(e.usagePage||0))
  }function ie(e,t) {
    for(let[n,r]of Object.entries(VY)) {
      let i;
      if(i=t?`/src/config/keyboards/${t}/${e}.ts`:`/${e}.ts`,n.endsWith(i)||!t&&n.includes(`/${e}.ts`))return console.log(`✅ 找到配置文件: ${n}`),r.keyboardConfig||null
    }return null
  }async function ae(e) {
    try {
      let[t,n,r,i,a]=e.split(`:`),o=`${t}-${n}-${r}${i?`-$ {
        i
      }`:``}${a?`-$ {
        a
      }`:``}`,s=`ajazz`,c=ie(o,s);
      if(!c)throw Error(`所有路径都未找到配置文件: ${o}`);
      return console.log(`[生产模式] 从供应商 "${s}" 加载配置: ${o}`),c
    }catch(t) {
      return $message.error($(`message_driveall_error`)),console.error(`加载键盘${e}配置失败:`,t),null
    }
  }async function oe(e) {
    try {
      e.opened||await e.open();
      let t=await l(`getDeviceInfo`,e,void 0,!1);
      return e.close(),`${e.vendorId}:${e.productId}:${e.productName}:${t.manufacturer}:${t.product}`
    }catch(e) {
      return console.error(`获取通用2.4G设备完整设备ID失败:`,e),``
    }
  }async function se() {
    try {
      if(o.value) {
        if(f.value)return!0;
        $loadingBar.start(),navigator.hid.addEventListener(`disconnect`,O);
        let e=await F();
        if(n.value&&r.value?.keyboardConfig?.keyList) {
          let e=await c(`deviceInit`,n.value);
          if(e) {
            if(e.deviceInfo?.firmwareStatus===1)g.value=n.value;
            else {
              g.value=``;
              let {
                useProtocol:t
              }=await Q(async()=> {
                let {
                  useProtocol:e
                }=await Promise.resolve().then(()=>$Y);
                return {
                  useProtocol:e
                }
              },void 0), {
                setProtocolDataFromDeviceInit:r
              }=t();
              await r(e);
              let {
                syncHardwareProfiles:i,updateCurrentProfile:a
              }=await Q(async()=> {
                let {
                  syncHardwareProfiles:e,updateCurrentProfile:t
                }=await Promise.resolve().then(()=>oQ);
                return {
                  syncHardwareProfiles:e,updateCurrentProfile:t
                }
              },void 0);
              await i(n.value)||await a(n.value)
            }
          }!g.value&&r.value?.keyboardConfig?.tftConfig?.isShowTftInfo&&await P(n.value)
        }return $loadingBar.finish(),f.value=!0,e
      }return!1
    }catch {
      return $loadingBar.finish(),!1
    }
  }return {
    devices:t,isLoading:i,isDemoMode:a,isSupported:o,historyConnect:s,currentDeviceId:n,currentDevice:r,is24GSleeping:m,isOtaUpgrading:h,firmwareCorruptedDeviceId:g,requestDevices:w,openDevice:T,closeDevice:E,closeAllDevice:D,initialize:se,reconnectDevices:F,waitForDeviceReconnect:ee,removeDisconnectedDevice:k
  }
}