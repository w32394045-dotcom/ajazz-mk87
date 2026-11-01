i[0];
return r._dbInfo=null,r._ready=null,r.getDriver(e).then(function(e) {
  r._driver=e._driver,a(),r._wrapLibraryMethodsWithReady(),r._initDriver=s(i)
})
}).catch(function() {
  a();
  var e=Error(`No available storage method found.`);
  return r._driverSet=l.reject(e),r._driverSet
}),d(this._driverSet,t,n),this._driverSet
},e.prototype.supports=function(e) {
  return!!mt[e]
},e.prototype._extend=function(e) {
  xt(this,e)
},e.prototype._getSupportedDrivers=function(e) {
  for(var t=[],n=0,r=e.length;
  n<r;
  n++) {
    var i=e[n];
    this.supports(i)&&t.push(i)
  }return t
},e.prototype._wrapLibraryMethodsWithReady=function() {
  for(var e=0,t=vt.length;
  e<t;
  e++)bt(this,vt[e])
},e.prototype.createInstance=function(t) {
  return new e(t)
},e
}())
}, {
  3:3
}]
}, {

},[4])(4)
})
})),oQ=t( {
  applyProfileToDeviceStorage:()=>fQ,copyProfile:()=>pQ,createProfile:()=>dQ,deleteProfile:()=>mQ,exportProfile:()=>wQ,getHardwareMaxProfile:()=>xQ,getProfileConfig:()=>lQ,importProfile:()=>TQ,profileSwitchBus:()=>cQ,renameProfile:()=>hQ,saveProfileConfig:()=>uQ,switchAndApplyProfile:()=>bQ,switchHardwareProfile:()=>CQ,switchProfile:()=>gQ,syncDeviceStorageToProfile:()=>yQ,syncHardwareProfiles:()=>SQ,updateCurrentProfile:()=>vQ,updateProfile:()=>_Q
}),sQ=e(aQ(),1),cQ=oL(`profile-switch`),lQ=async e=> {
  try {
    let t=await sQ.default.getItem(`${e}-profile`);
    if(t)return t;
     {
      let t= {
        profileList:[ {
          profileName:`profile`,...tn($I(e, {

          }).value)
        }],currentProfileIndex:0
      };
      return await sQ.default.setItem(`${e}-profile`,tn(t)),t
    }
  }catch(e) {
    console.error(`初始化 Profile 配置失败:`,e)
  }
},uQ=async(e,t)=> {
  try {
    return await sQ.default.setItem(`${e}-profile`,tn(t)),!0
  }catch(e) {
    return console.error(`保存 Profile 配置失败:`,e),!1
  }
},dQ=async(e,t,n=`profile`)=> {
  try {
    let r=await lQ(e);
    if(!r)return!1;
    let i= {
      profileName:n,...t
    };
    return r.profileList.length===0?(r.profileList=[i],r.currentProfileIndex=0):r.profileList.push(i),await uQ(e,r),i
  }catch(e) {
    return console.error(`创建 Profile 失败:`,e),!1
  }
},fQ=(e,t)=> {
  let n=$I(e, {

  }), {
    profileName:r,...i
  }=JSON.parse(JSON.stringify(t)), {
    deviceInfo:a,sn:o
  }=n.value;
  n.value= {
    ...i,deviceInfo:a??i.deviceInfo,sn:o??i.sn
  }
},pQ=async(e,t,n)=> {
  try {
    let r=await lQ(e);
    if(!r||t<0||t>=r.profileList.length)return!1;
    let i=r.profileList[t],a= {
      ...JSON.parse(JSON.stringify(i)),profileName:n||`${i.profileName} Copy`
    };
    return r.profileList.push(a),await uQ(e,r),!0
  }catch(e) {
    return console.error(`复制 Profile 失败:`,e),!1
  }
},mQ=async(e,t)=> {
  try {
    let n=await lQ(e);
    return!n||t<0||t>=n.profileList.length||n.profileList.length<=1||t===n.currentProfileIndex?!1:(n.profileList.splice(t,1),t<n.currentProfileIndex&&n.currentProfileIndex--,await uQ(e,n),!0)
  }catch(e) {
    return console.error(`删除 Profile 失败:`,e),!1
  }
},hQ=async(e,t,n)=> {
  try {
    let r=await lQ(e);
    if(!r||t<0||t>=r.profileList.length)return!1;
    let i=n.trim();
    return r.profileList[t].profileName=i||`profile`,await uQ(e,r),!0
  }catch(e) {
    return console.error(`重命名 Profile 失败:`,e),!1
  }
},gQ=async(e,t)=> {
  try {
    let n=await lQ(e);
    return n?t>=0&&t<n.profileList.length&&(n.currentProfileIndex=t,await uQ(e,n),!0):!1
  }catch(e) {
    return console.error(`切换 Profile 失败:`,e),!1
  }
},_Q=async(e,t,n)=> {
  try {
    let r=await lQ(e);
    return!r||t<0||t>=r.profileList.length?!1:(Object.assign(r.profileList[t],n),await uQ(e,r),!0)
  }catch(e) {
    return console.error(`更新 Profile 失败:`,e),!1
  }
},vQ=async e=> {
  try {
    let t=await lQ(e);
    if(!t)return!1;
    let n=t.currentProfileIndex;
    return await _Q(e,n,tn( {
      ...tn($I(e, {

      }).value),profileName:t.profileList[n].profileName
    }))
  }catch(e) {
    return console.error(`更新当前 Profile 失败:`,e),!1
  }
},yQ=async(e,t)=> {
  try {
    let n=await lQ(e);
    if(!n)return console.error(`未找到 profile 配置`),!1;
    let r=n.currentProfileIndex;
    if(r<0||r>=n.profileList.length)return console.error(`无效的 profile 索引:`,r),!1;
    let i= {
      ...tn(t),profileName:n.profileList[r].profileName
    };
    return n.profileList[r]=i,await uQ(e,n),!0
  }catch(e) {
    return console.error(`❌ 同步设备存储到 Profile 失败:`,e),!1
  }
},bQ=async(e,t,n)=> {
  try {
    let {
      sendReport:r
    }=rY(),i=n;
    if(!i) {
      let n=await lQ(e);
      if(!n||t<0||t>=n.profileList.length)return console.error(`无效的 profile 索引或配置不存在`),!1;
      i=n.profileList[t]
    }if(!await gQ(e,t))return console.error(`切换 Profile 失败`),!1;
    i.keyList&&(i.wheelKeys?await r(`setKeyData`,e,i.keyList,i.wheelKeys):await r(`setKeyData`,e,i.keyList)),i.fnKeyList&&await r(`setFnKeyData`,e,i.fnKeyList),i.ledEffect&&await r(`setLEDEffect`,e,i.ledEffect),i.customLedData&&await r(`setCustomLEDData`,e,i.customLedData),i.macroDataList&&await r(`setMacroData`,e,i.macroDataList),i.magneticAxisRT&&await r(`setMagneticAxisRT`,e,i.magneticAxisRT),i.magneticAxisDKS&&await r(`setMagneticAxisDKSData`,e,i.magneticAxisDKS),i.lightBoxData&&await r(`setLightBox`,e,i.lightBoxData),i.sideLightData&&await r(`setSideLight`,e,i.sideLightData),i.fnKeyList&&await r(`getFnKeyData`,e),fQ(e,i);
    let {
      initProtocol:a
    }=tX();
    return await a(void 0, {
      ledEffect:i.ledEffect,customLedData:i.customLedData,macroDataList:i.macroDataList
    }),!0
  }catch(e) {
    return console.error(`切换并应用 Profile 失败:`,e),!1
  }
},xQ=e=> {
  let t=e?.maxProfile??0;
  return t>1?t:0
},SQ=async e=> {
  try {
    let t=$I(e, {

    }), {
      deviceInfo:n
    }=t.value,r=xQ(n);
    if(!r)return!1;
    let i=await lQ(e);
    if(!i)return!1;
    let a=JSON.parse(JSON.stringify(tn(t.value))),o=Math.min(Math.max((n?.currentProfile??1)-1,0),r-1),s=i.profileList.slice(0,r);
    for(let e=s.length;
    e<r;
    e++)s.push( {
      ...JSON.parse(JSON.stringify(a)),profileName:`Profile ${e+1}`
    });
    return s[o]= {
      ...a,profileName:s[o].profileName
    },i.profileList=s,i.currentProfileIndex=o,await uQ(e,i),!0
  }catch(e) {
    return console.error(`同步板载 Profile 失败:`,e),!1
  }
},CQ=async(e,t)=> {
  try {
    let {
      sendReport:n
    }=rY();
    if(!await n(`setProfile`,e,t+1))return!1;
    await gQ(e,t);
    let r=await n(`deviceInit`,e);
    if(!r)return!1;
    let {
      setProtocolDataFromDeviceInit:i
    }=tX();
    return await i(r),await SQ(e)
  }catch(e) {
    return console.error(`切换板载 Profile 失败:`,e),!1
  }
},wQ=async(e,t,n)=> {
  try {
    let r=await lQ(e);
    if(!r||t<0||t>=r.profileList.length)return console.error(`无效的 profile 索引或配置不存在`),!1;
    let i=r.profileList[t],a= {
      deviceId:e,profile:tn(i)
    },o=`${i.profileName}.json`,s=n||o;
    return TV(new Blob([JSON.stringify(a,null,2)], {
      type:`application/json`
    }),s),!0
  }catch(e) {
    return console.error(`导出 Profile 失败:`,e),!1
  }
},TQ=async(e,t,n= {

})=> {
  try {
    let {
      overwrite:r=!1,applyAfterImport:i=!1,replaceIndex:a
    }=n,o=await new Promise((e,n)=> {
      let r=new FileReader;
      r.onload=t=>e(t.target?.result),r.onerror=n,r.readAsText(t)
    }),s=JSON.parse(o);
    if(s.deviceId!==e||!s.profile)throw Error($(`invalid_profile_file_format`));
    let c=await lQ(e);
    if(!c)throw Error($(`unable_profile_file_format`));
    let l=JSON.parse(JSON.stringify(s.profile));
    if(a!==void 0) {
      if(a<0||a>=c.profileList.length)throw Error($(`unable_profile_file_format`));
      return c.profileList[a]=l,await uQ(e,c), {
        success:await bQ(e,a,l),profileIndex:a,isOverwrite:!0
      }
    }let u=c.profileList.findIndex(e=>e.profileName===l.profileName);
    if(u>=0) {
      if(r)return c.profileList[u]=l,await uQ(e,c),i&&await bQ(e,u,l), {
        success:!0,profileIndex:u,isOverwrite:!0
      };
       {
        let e=1,t=`${l.profileName} (${e})`;
        for(;
        c.profileList.some(e=>e.profileName===t);
        )e++,t=`${l.profileName} (${e})`;
        l.profileName=t
      }
    }if(u<0||!r) {
      c.profileList.push(l),await uQ(e,c);
      let t=c.profileList.length-1;
      return i&&await bQ(e,t,l), {
        success:!0,profileIndex:t,isOverwrite:!1
      }
    }return {
      success:!0,profileIndex:u,isOverwrite:r
    }
  }catch(e) {
    return console.error(`导入 Profile 失败:`,e), {
      success:!1,error:e instanceof Error?e.message:`unknown`
    }
  }
};
$I(`userInfo`, {

});
var EQ,DQ=typeof TextDecoder<`u`?new TextDecoder(`utf-8`, {
  ignoreBOM:!0,fatal:!0
}): {
  decode:()=> {
    throw Error(`TextDecoder not available`)
  }
};
typeof TextDecoder<`u`&&DQ.decode();
var OQ=null;
function kQ() {
  return(OQ===null||OQ.byteLength===0)&&(OQ=new Uint8Array(EQ.memory.buffer)),OQ
}function AQ(e,t) {
  return e>>>=0,DQ.decode(kQ().subarray(e,e+t))
}function jQ(e) {
  let t=EQ.__externref_table_alloc();
  return EQ.__wbindgen_export_2.set(t,e),t
}function MQ(e,t) {
  try {
    return e.apply(this,t)
  }catch(e) {
    let t=jQ(e);
    EQ.__wbindgen_exn_store(t)
  }
}function NQ(e) {
  return e==null
}var PQ=typeof FinalizationRegistry>`u`? {
  register:()=> {

  },unregister:()=> {

  }
}:new FinalizationRegistry(e=> {
  EQ.__wbindgen_export_3.get(e.dtor)(e.a,e.b)
});
function FQ(e,t,n,r) {
  let i= {
    a:e,b:t,cnt:1,dtor:n
  },a=(...e)=> {
    i.cnt++;
    let t=i.a;
    i.a=0;
    try {
      return r(t,i.b,...e)
    }finally {
      --i.cnt===0?(EQ.__wbindgen_export_3.get(i.dtor)(t,i.b),PQ.unregister(i)):i.a=t
    }
  };
  return a.original=i,PQ.register(a,i,i),a
}function IQ(e) {
  let t=typeof e;
  if(t==`number`||t==`boolean`||e==null)return`${e}`;
  if(t==`string`)return`"${e}"`;
  if(t==`symbol`) {
    let t=e.description;
    return t==null?`Symbol`:`Symbol(${t})`
  }if(t==`function`) {
    let t=e.name;
    return typeof t==`string`&&t.length>0?`Function(${t})`:`Function`
  }if(Array.isArray(e)) {
    let t=e.length,n=`[`;
    t>0&&(n+=IQ(e[0]));
    for(let r=1;
    r<t;
    r++)n+=`, `+IQ(e[r]);
    return n+=`]`,n
  }let n=/\[object ([^\]]+)\]/.exec(toString.call(e)),r;
  if(n&&n.length>1)r=n[1];
  else return toString.call(e);
  if(r==`Object`)try {
    return`Object(`+JSON.stringify(e)+`)`
  }catch {
    return`Object`
  }return e instanceof Error?`${e.name}: ${e.message}\n${e.stack}`:r
}var LQ=0,RQ=typeof TextEncoder<`u`?new TextEncoder(`utf-8`): {
  encode:()=> {
    throw Error(`TextEncoder not available`)
  }
},zQ=typeof RQ.encodeInto==`function`?function(e,t) {
  return RQ.encodeInto(e,t)
}:function(e,t) {
  let n=RQ.encode(e);
  return t.set(n), {
    read:e.length,written:n.length
  }
};
function BQ(e,t,n) {
  if(n===void 0) {
    let n=RQ.encode(e),r=t(n.length,1)>>>0;
    return kQ().subarray(r,r+n.length).set(n),LQ=n.length,r
  }let r=e.length,i=t(r,1)>>>0,a=kQ(),o=0;
  for(;
  o<r;
  o++) {
    let t=e.charCodeAt(o);
    if(t>127)break;
    a[i+o]=t
  }if(o!==r) {
    o!==0&&(e=e.slice(o)),i=n(i,r,r=o+e.length*3,1)>>>0;
    let t=kQ().subarray(i+o,i+r),a=zQ(e,t);
    o+=a.written,i=n(i,r,o,1)>>>0
  }return LQ=o,i
}var VQ=null;
function HQ() {
  return(VQ===null||VQ.buffer.detached===!0||VQ.buffer.detached===void 0&&VQ.buffer!==EQ.memory.buffer)&&(VQ=new DataView(EQ.memory.buffer)),VQ
}function UQ(e) {
  EQ.set_process_callback(NQ(e)?0:jQ(e))
}function WQ(e,t) {
  let n=t(e.length*1,1)>>>0;
  return kQ().set(e,n/1),LQ=e.length,n
}function GQ(e) {
  let t=EQ.__wbindgen_export_2.get(e);
  return EQ.__externref_table_dealloc(e),t
}function KQ(e) {
  let t=WQ(e,EQ.__wbindgen_malloc),n=LQ,r=EQ.snx_isp_load_hex_buffer(t,n);
  if(r[2])throw GQ(r[1]);
  return r[0]
}function qQ(e) {
  EQ.set_code_security(e)
}function JQ(e) {
  let t=BQ(e,EQ.__wbindgen_malloc,EQ.__wbindgen_realloc),n=LQ;
  return EQ.set_check_device_cmd(t,n)!==0
}function YQ(e) {
  EQ.set_reset_flag(e)
}function XQ(e) {
  return EQ.start_isp(e)
}function ZQ(e) {
  return EQ.set_chip_series_index(e)!==0
}function QQ(e,t,n) {
  EQ.closure14_externref_shim(e,t,n)
}function $Q(e,t) {
  EQ._dyn_core__ops__function__FnMut_____Output___R_as_wasm_bindgen__closure__WasmClosure___describe__invoke__hf13c641df3e1f335(e,t)
}function e$(e,t,n) {
  EQ.closure33_externref_shim(e,t,n)
}function t$(e,t,n,r) {
  EQ.closure54_externref_shim(e,t,n,r)
}async function n$(e,t) {
  if(typeof Response==`function`&&e instanceof Response) {
    if(typeof WebAssembly.instantiateStreaming==`function`)try {
      return await WebAssembly.instantiateStreaming(e,t)
    }catch(t) {
      if(e.headers.get(`Content-Type`)!=`application/wasm`)console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n",t);
      else throw t
    }let n=await e.arrayBuffer();
    return await WebAssembly.instantiate(n,t)
  } {
    let n=await WebAssembly.instantiate(e,t);
    return n instanceof WebAssembly.Instance? {
      instance:n,module:e
    }:n
  }
}function r$() {
  let e= {

  };
  return e.wbg= {

  },e.wbg.__wbg_addEventListener_b9481c2c2cab6047=function() {
    return MQ(function(e,t,n,r) {
      e.addEventListener(AQ(t,n),r)
    },arguments)
  },e.wbg.__wbg_buffer_61b7ce01341d7f88=function(e) {
    return e.buffer
  },e.wbg.__wbg_buffer_a1e3fb180d2a8775=function(e) {
    return e.buffer
  },e.wbg.__wbg_call_500db948e69c7330=function() {
    return MQ(function(e,t,n) {
      return e.call(t,n)
    },arguments)
  },e.wbg.__wbg_call_b0d8e36992d9900d=function() {
    return MQ(function(e,t) {
      return e.call(t)
    },arguments)
  },e.wbg.__wbg_clearTimeout_5a54f8841c30079a=function(e) {
    return clearTimeout(e)
  },e.wbg.__wbg_device_697893261dabb679=function(e) {
    return e.device
  },e.wbg.__wbg_error_fab41a42d22bf2bc=function(e) {
    console.error(e)
  },e.wbg.__wbg_hid_94d3748076cc70a5=function(e) {
    return e.hid
  },e.wbg.__wbg_instanceof_HidConnectionEvent_440ec1b2af3c9d77=function(e) {
    let t;
    try {
      t=e instanceof HIDConnectionEvent
    }catch {
      t=!1
    }return t
  },e.wbg.__wbg_instanceof_Window_d2514c6a7ee7ba60=function(e) {
    let t;
    try {
      t=e instanceof Window
    }catch {
      t=!1
    }return t
  },e.wbg.__wbg_is_e442492d1fb7967b=function(e,t) {
    return Object.is(e,t)
  },e.wbg.__wbg_length_65d1cd11729ced11=function(e) {
    return e.length
  },e.wbg.__wbg_log_464d1b2190ca1e04=function(e) {
    console.log(e)
  },e.wbg.__wbg_log_5c69f7234016be1d=function(e,t) {
    console.log(AQ(e,t))
  },e.wbg.__wbg_navigator_0fe968937104eaa7=function(e) {
    return e.navigator
  },e.wbg.__wbg_new_3d446df9155128ef=function(e,t) {
    try {
      var n= {
        a:e,b:t
      };
      return new Promise((e,t)=> {
        let r=n.a;
        n.a=0;
        try {
          return t$(r,n.b,e,t)
        }finally {
          n.a=r
        }
      })
    }finally {
      n.a=n.b=0
    }
  },e.wbg.__wbg_new_3ff5b33b1ce712df=function(e) {
    return new Uint8Array(e)
  },e.wbg.__wbg_new_688846f374351c92=function() {
    return {

    }
  },e.wbg.__wbg_newnoargs_fd9e4bf8be2bc16d=function(e,t) {
    return Function(AQ(e,t))
  },e.wbg.__wbg_newwithbyteoffsetandlength_ba35896968751d91=function(e,t,n) {
    return new Uint8Array(e,t>>>0,n>>>0)
  },e.wbg.__wbg_newwithlength_34ce8f1051e74449=function(e) {
    return new Uint8Array(e>>>0)
  },e.wbg.__wbg_now_62a101fe35b60230=function(e) {
    return e.now()
  },e.wbg.__wbg_open_ee448b95e3407411=function(e) {
    return e.open()
  },e.wbg.__wbg_opened_2326d05f53bc093e=function(e) {
    return e.opened
  },e.wbg.__wbg_performance_2e69ce813a883f21=function(e) {
    let t=e.performance;
    return NQ(t)?0:jQ(t)
  },e.wbg.__wbg_queueMicrotask_2181040e064c0dc8=function(e) {
    queueMicrotask(e)
  },e.wbg.__wbg_queueMicrotask_ef9ac43769cbcc4f=function(e) {
    return e.queueMicrotask
  },e.wbg.__wbg_receiveFeatureReport_f4f42dc8515a8193=function(e,t) {
    return e.receiveFeatureReport(t)
  },e.wbg.__wbg_resolve_0bf7c44d641804f9=function(e) {
    return Promise.resolve(e)
  },e.wbg.__wbg_sendFeatureReport_6d5966d4d5107cbe=function() {
    return MQ(function(e,t,n) {
      return e.sendFeatureReport(t,n)
    },arguments)
  },e.wbg.__wbg_setTimeout_db2dbaeefb6f39c7=function() {
    return MQ(function(e,t) {
      return setTimeout(e,t)
    },arguments)
  },e.wbg.__wbg_set_23d69db4e5c66a6e=function(e,t,n) {
    e.set(t,n>>>0)
  },e.wbg.__wbg_set_4e647025551483bd=function() {
    return MQ(function(e,t,n) {
      return Reflect.set(e,t,n)
    },arguments)
  },e.wbg.__wbg_static_accessor_GLOBAL_0be7472e492ad3e3=function() {
    let e=typeof global>`u`?null:global;
    return NQ(e)?0:jQ(e)
  },e.wbg.__wbg_static_accessor_GLOBAL_THIS_1a6eb482d12c9bfb=function() {
    let e=typeof globalThis>`u`?null:globalThis;
    return NQ(e)?0:jQ(e)
  },e.wbg.__wbg_static_accessor_SELF_1dc398a895c82351=function() {
    let e=typeof self>`u`?null:self;
    return NQ(e)?0:jQ(e)
  },e.wbg.__wbg_static_accessor_WINDOW_ae1c80c7eea8d64a=function() {
    let e=typeof window>`u`?null:window;
    return NQ(e)?0:jQ(e)
  },e.wbg.__wbg_subarray_46adeb9b86949d12=function(e,t,n) {
    return e.subarray(t>>>0,n>>>0)
  },e.wbg.__wbg_then_0438fad860fe38e1=function(e,t) {
    return e.then(t)
  },e.wbg.__wbg_then_0ffafeddf0e182a4=function(e,t,n) {
    return e.then(t,n)
  },e.wbg.__wbindgen_cb_drop=function(e) {
    let t=e.original;
    return t.cnt--==1&&(t.a=0,!0)
  },e.wbg.__wbindgen_closure_wrapper109=function(e,t,n) {
    return FQ(e,t,15,QQ)
  },e.wbg.__wbindgen_closure_wrapper299=function(e,t,n) {
    return FQ(e,t,27,$Q)
  },e.wbg.__wbindgen_closure_wrapper313=function(e,t,n) {
    return FQ(e,t,34,e$)
  },e.wb