// ===== RX =====
RX=e=> {
  let t=65535;
  for(let n=0;
  n<e.length;
  n++) {
    t^=(e[n]&255)<<8;
    for(let e=0;
    e<8;
    e++)t=t&32768?(t<<1^4129)&65535:t<<1&65535
  }return t&65535
}

// ===== PX =====
PX=(e,t,n,r,i=32,a,o,s=!1)=> {
  let c=new Uint8Array(i).fill(0);
  if(o)return c.set(o,0),r&&c.set(r,o.length),c;
  if(c[0]=170,c[1]=e,c[2]=t,c[3]=n&255,c[4]=n>>8&255,a&&Array.isArray(a))for(let e=0;
  e<Math.min(a.length,3);
  e++)a[e]!==void 0&&(c[5+e]=a[e]&255);
  return(!a||a.length<2||a[1]===void 0)&&(c[6]=+!!s),r&&c.set(r,8),c
}

// ===== IX =====
IX=(e,t,n)=> {
  let {
    command:r,timeout:i=50,addr:a,parseAddr:o,abortSignal:s
  }=t;
  return new Promise((t,c)=> {
    let l=0,u=!1,d=()=> {
      e.removeEventListener(`inputreport`,m),s?.removeEventListener(`abort`,p),l&&=(gY(l),0)
    },f=e=> {
      u||(u=!0,d(),c(e))
    },p=()=> {
      f(Error(`操作已中断`))
    };
    if(s?.aborted) {
      f(Error(`操作已中断`));
      return
    }l=vY(()=> {
      f(Error(`命令0x${r.toString(16)}响应超时`))
    },i),s?.addEventListener(`abort`,p);
    let m=e=> {
      let {
        data:i
      }=e,s=new Uint8Array(i.buffer),l=FX(s);
      if(l&&l.cmd===r&&(a===void 0||(o?o(s):l.addr)===a)&&!u) {
        u=!0,d();
        try {
          t(n(s))
        }catch(e) {
          c(e)
        }
      }
    };
    e.addEventListener(`inputreport`,m)
  })
}

// ===== FX =====
FX=e=>e[0]===85? {
  header:e[0],cmd:e[1],lenOrType:e[2],addr:e[3]|e[4]<<8,data:e.slice(8)
}:(console.error(`数据包头错误:0x${e[0].toString(16)}`),null)

// ===== NX =====
NX=async(e,t)=> {
  let {
    cmd:n,contentSize:r=24,addrStart:i=0,data:a,timeout:o=500,maxRetries:s=3,headerCount:c=8,otherHeader:l,customHeader:u,responseDevice:d=e,responseCmd:f=n,abortSignal:p,isNeedLastPacketFlag:m=!0,checkAddr:h=!1,parseAddr:g,skipResponse:_=!1
  }=t,v=[],y=e?.collections?.[0]?.outputReports?.[0]?.items?.[0]?.reportCount||32,b=y-c,x=Math.ceil(r/b);
  for(let t=0;
  t<x;
  t++) {
    if(p?.aborted)throw Error(`操作已中断`);
    let c=i+t*b,S=r-t*b,C=m?t===x-1:!1,w=t===x-1?S:b,T;
    if(a) {
      let e=t*b,n=Math.min(e+b,a.length);
      T=a.slice(e,n)
    }let E=PX(n,w,c,T,y,l,u,C);
    if(_) {
      await e.sendReport(0,E);
      continue
    }let D=0,O=null;
    for(;
    D<=s&&!O;
    ) {
      if(p?.aborted)throw Error(`操作已中断`);
      try {
        let t=IX(d, {
          command:f,timeout:o,addr:h?c:void 0,parseAddr:g,abortSignal:p
        },e=>e);
        t.catch(()=> {

        }),await MX(e,E,p),O=await t
      }catch(t) {
        if(p?.aborted||t instanceof Error&&t.message===`操作已中断`)throw Error(`操作已中断`);
        if(s===0)return[];
        if(D++,D<=s)console.warn(`数据包0x${n.toString(16)}响应超时，正在进行第${D}次重发`);
        else {
          if(console.error(`数据包0x${n.toString(16)}响应超时，已重发${s}次仍无响应: ${t}`),n===jX)return Promise.reject([]);
           {
            let {
              useWebHIDStore:t
            }=await Q(async()=> {
              let {
                useWebHIDStore:e
              }=await Promise.resolve().then(()=>BY);
              return {
                useWebHIDStore:e
              }
            },void 0),n=t(),r=n.currentDeviceId;
            r&&(await n.closeDevice(r),n.devices.delete(r),n.historyConnect= {

            }),await e.forget()
          }return location.pathname!==`/`&&($message.error($(`link_state`)),ZY.replace( {
            path:`/`
          })),Promise.reject([])
        }
      }
    }O&&v.push(O)
  }return v
}

// ===== YX =====
YX=(e,t=`数据`)=>n=> {
  let {
    data:r
  }=n,i=JX(new Uint8Array(r.buffer));
  if(i&&e&&typeof e==`function`)try {
    e(i)
  }catch(e) {
    console.error(`调用${t}回调函数时出错:`,e)
  }
}

// ===== wV =====
wV=(e=1e3)=>new Promise(t=> {
  setTimeout(()=> {
    t()
  },e)
})

// ===== zY =====
zY=[ {
  vendorId:3141,productId:32816,suppliers:[`vter`,`ganss`]
}, {
  vendorId:3141,productId:32817,suppliers:[`aula`,`leobog`,`leobog_rk`]
}, {
  vendorId:3141,productId:32818,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32821,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32822,suppliers:[`eweadn`,`1stplayer`]
}, {
  vendorId:3141,productId:34816,suppliers:[`gptx`,`zidli`,`jc`,`gptx_new`]
}, {
  vendorId:3141,productId:32823,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32840,suppliers:[`rk`]
}, {
  vendorId:1452,productId:591,suppliers:[`xiberia`,`ganss`,`zuohe`,`womier_jx`,`colorfulkb`,`epomaker`,`cidoo`,`varo`,`leobog`,`leobog_rk`,`nubi`,`io`,`aula`,`darkprojectru`,`darkprojecteu`,`rsq`,`nu31`,`gconic`,`aula_en`,`tecware`,`epomaker-uk`,`colorfulkb`]
}, {
  vendorId:3141,productId:32838,suppliers:[`rk`,`ajazz`]
}, {
  vendorId:3141,productId:32851,suppliers:[`gk68`,`ajazz`]
}, {
  vendorId:3141,productId:32853,suppliers:[`womier`,`womier_en`]
}, {
  vendorId:3141,productId:32849,suppliers:[`vter`,`ajazz`]
}, {
  vendorId:3141,productId:32832,suppliers:[`womier`,`womier_en`]
}, {
  vendorId:3141,productId:32833,suppliers:[`womier`,`womier_en`]
}, {
  vendorId:3141,productId:32867,suppliers:[`latenpow`]
}, {
  vendorId:3141,productId:32869,suppliers:[`womier`,`womier_en`]
}, {
  vendorId:3141,productId:32837,suppliers:[`eweadn`,`ajazz`]
}, {
  vendorId:3141,productId:32855,suppliers:[]
}, {
  vendorId:3141,productId:32819,suppliers:[`ajazz`,`ajazz_`]
}, {
  vendorId:3141,productId:32874,suppliers:[`scorpion`,`eweadn`]
}, {
  vendorId:3141,productId:32875,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32880,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32881,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32887,suppliers:[`langtu`,`xinmeng`]
}, {
  vendorId:3141,productId:32888,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32893,suppliers:[`bigexing`]
}, {
  vendorId:3141,productId:32894,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32895,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32896,suppliers:[`eweadn`,`langtu`]
}, {
  vendorId:3141,productId:32897,suppliers:[`qsenn`,`langtu`]
}, {
  vendorId:3141,productId:32901,suppliers:[`youtaidu`]
}, {
  vendorId:3141,productId:32908,suppliers:[`jianshangjia`]
}, {
  vendorId:3141,productId:32841,suppliers:[`rk`,`ajazz`]
}, {
  vendorId:3141,productId:32910,suppliers:[`gms`]
}, {
  vendorId:3141,productId:32912,suppliers:[]
}, {
  vendorId:3141,productId:65278,suppliers:`aula.ajazz.ganss.langtu.he68pro.xinmeng.io.dgsisun.amechkb.a-jazz.xiberia.glick.iblancod.epomaker.cidoo.varo.womier_jx.nubi.pj05.aoc-k68.mechlands.fxr-hkw.darkprojecteu.jize.xvx.gamepowerpc.kisnt.codingcdn.boy.fire.ldon.a-jazz-fr.a-jazz-es.aether.1stplayer.turkish.kx87.fantech.womiercustomer.titanwolf.darkprojectru.avax.havitsmart.xinmeng.gwings.egaxjjkss2p1.genshin.magnus.lecoo.naceb.yunzii.womier_l98.keysync.rsq.redthunder.hawkgaming.swift.nsyca.imice.slnc.ega-type-cmk13.ega-type-cmk14.rampage.k68.nu31.basike.leobog.leobog.vrlkyborad.ega-jjkss2p2.noirgear.sarukx99zodiac.portronics`.split(`.`)
}, {
  vendorId:3141,productId:32914,suppliers:[`epomaker`,`cidoo`,`varo`]
}, {
  vendorId:3141,productId:32905,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32850,suppliers:[`vter`,`ajazz`]
}, {
  vendorId:3141,productId:32915,suppliers:[`repoem`]
}, {
  vendorId:3141,productId:32889,suppliers:[`langtu`,`bigexing`]
}, {
  vendorId:3141,productId:32916,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32917,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32918,suppliers:[`ganss`]
}, {
  vendorId:3141,productId:32919,suppliers:[`iblancod`]
}, {
  vendorId:3141,productId:32920,suppliers:[`iblancod`]
}, {
  vendorId:3141,productId:32922,suppliers:[`gptx`,`zidli`,`gptx_new`]
}, {
  vendorId:3141,productId:32836,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32879,suppliers:[`jc`]
}, {
  vendorId:3141,productId:65277,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32923,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32825,suppliers:[`a-jazz`,`ajazz`,`redthunder`]
}, {
  vendorId:3141,productId:32777,suppliers:`xiberia.a-jazz.epomaker.cidoo.varo.ajazz.fxr-hkw.ganss.io.boy.aether.turkish.kx87.eswn.womiercustomer.avax.titanwolf.kbtest5.darkprojectru.havitsmart.genshin.womier_l98.hawkgaming.imice.ega-type-cmk13.ega-type-cmk14.rampage.nu31.ega-jjkss2p2.noirgear.portronics`.split(`.`)
}, {
  vendorId:3141,productId:32925,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32924,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32926,suppliers:[`eweadn`]
}, {
  vendorId:3141,productId:32927,suppliers:[`ganss`]
}, {
  vendorId:3141,productId:32835,suppliers:[`ajazz`,`onikua`,`vida`]
}, {
  vendorId:3141,productId:32820,suppliers:[`sunt`]
}, {
  vendorId:3141,productId:32865,suppliers:[]
}, {
  vendorId:3141,productId:32928,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:65276,suppliers:[`ajazz`,`leobog`,`aula`,`leobog_rk`,`qsenn`,`bigexing`,`langtu`,`aoc-k68`,`xiberia`,`archon`,`xinmeng`,`jz_hub`,`kurokey-gemrise`,`yunzii`,`jdjz`,`kb884l_he`,`k68`,`darkprojectru`,`darkprojecteu`,`aoc-k68`,`thunderobot`,`colorfulkb`]
}, {
  vendorId:3141,productId:32778,suppliers:`leobog.leobog_rk.ganss.epomaker.cidoo.varo.womier_jx.pj05.darkprojecteu.aula.ajazz.a-jazz.a-jazz-fr.a-jazz-es.havitsmart.egaxjjkss2p1.yunzii.darkprojectru.nsyca.imice.1stplayer.rampage.nu31.aula_en.ega-type-cmk13.ega-jjkss2p2.womier_l98`.split(`.`)
}, {
  vendorId:3141,productId:32929,suppliers:[`leobog`,`leobog_rk`,`aula`,`langtu`,`gattmoo`]
}, {
  vendorId:3141,productId:32930,suppliers:[`leobog`,`leobog_rk`,`aula`,`aoc-k68`,`rsq`]
}, {
  vendorId:3141,productId:32931,suppliers:[`gattmoo`]
}, {
  vendorId:3141,productId:32932,suppliers:[`gattmoo`,`youtaidu`,`jc`]
}, {
  vendorId:3141,productId:32885,suppliers:[]
}, {
  vendorId:3141,productId:32934,suppliers:[]
}, {
  vendorId:3141,productId:32935,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32936,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32937,suppliers:[]
}, {
  vendorId:3141,productId:32933,suppliers:[]
}, {
  vendorId:3141,productId:32938,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32939,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32940,suppliers:[`rsq`,`darkprojecteu`]
}, {
  vendorId:3141,productId:32941,suppliers:[`qsenn`,`rsq`]
}, {
  vendorId:3141,productId:32942,suppliers:[]
}, {
  vendorId:3141,productId:32774,suppliers:[`xiberia`,`xinmeng`,`dgsisun`,`a-jazz`,`iblancod`,`langtu`,`epomaker`,`cidoo`,`varo`,`mechlands`,`jize`,`ajazz`,`kisnt`,`codingcdn`,`aether`,`light67`,`1stplayer`,`lecoo`,`darkprojectru`,`womier_l98`,`valinor`,`darkprojecteu`,`rampage`,`xpanse`]
}, {
  vendorId:13357,productId:58383,suppliers:[`gattmooProtocol`]
}, {
  vendorId:1046,productId:49989,suppliers:[`gattmooProtocol`]
}, {
  vendorId:6700,productId:5396,suppliers:[`gattmooProtocol`]
}, {
  vendorId:3141,productId:32945,suppliers:[`ajazz`,`qsenn`,`aula`]
}, {
  vendorId:3141,productId:34817,suppliers:[`glick`,`qsenn`,`aula`,`ldon`,`fire`,`gamepowerpc`,`ajazz`,`fantech`,`aether`,`keysync`,`slnc`]
}, {
  vendorId:3141,productId:32944,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32946,suppliers:[`ajazz`,`aula`,`xiberia`,`xinmeng`,`langtu`,`k-trajectory`]
}, {
  vendorId:3141,productId:32947,suppliers:[`xiberia`,`xinmeng`,`ndiy`,`acefast`,`thinkway`]
}, {
  vendorId:3141,productId:32948,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32949,suppliers:[`langtu`,`youtaidu`]
}, {
  vendorId:3141,productId:32950,suppliers:[]
}, {
  vendorId:3141,productId:32943,suppliers:[`apeha`,`rsq`,`darkprojecteu`,`nu31`,`kiberpride`]
}, {
  vendorId:3141,productId:591,suppliers:[`glick`]
}, {
  vendorId:3141,productId:32951,suppliers:[`ajazz`,`jc`]
}, {
  vendorId:3141,productId:32952,suppliers:[`onikua`]
}, {
  vendorId:3141,productId:32854,suppliers:[]
}, {
  vendorId:3141,productId:32954,suppliers:[`freewolfgaming`,`ganss`,`attackshark`,`dsm`]
}, {
  vendorId:3141,productId:34818,suppliers:[`ajazz`,`weikav`]
}, {
  vendorId:3141,productId:32903,suppliers:[]
}, {
  vendorId:3141,productId:598,suppliers:[`io`,`nubi`,`darkprojecteu`]
}, {
  vendorId:1452,productId:598,suppliers:[`io`,`nubi`,`rsq`,`darkprojecteu`]
}, {
  vendorId:6790,productId:65024,suppliers:[]
}, {
  vendorId:3141,productId:32775,suppliers:[`1stplayer`,`xinmeng`,`light67`,`imice`,`epomaker`,`darkprojecteu`]
}, {
  vendorId:3141,productId:32953,suppliers:[`ajazz`,`ajazz_`,`attackshark`]
}, {
  vendorId:3141,productId:32956,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32955,suppliers:[`attackshark`,`xiberia`,`langtu`]
}, {
  vendorId:3141,productId:32963,suppliers:[`newmen`]
}, {
  vendorId:3141,productId:32957,suppliers:[]
}, {
  vendorId:3141,productId:32958,suppliers:[`gameon`,`scorpion`,`attackshark`,`hjsdzhi`]
}, {
  vendorId:3141,productId:32970,suppliers:[`io`]
}, {
  vendorId:3141,productId:32906,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32962,suppliers:[`ajazz`,`1stplayer`]
}, {
  vendorId:3141,productId:32971,suppliers:[`he68pro`,`newmen`]
}, {
  vendorId:3141,productId:32899,suppliers:[`langtu`]
}, {
  vendorId:14502,productId:10001,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10002,suppliers:[`aula`,`archon`,`jz_hub`,`jdjz`]
}, {
  vendorId:14502,productId:1e4,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32793,suppliers:[`amechkb`,`ajazz`]
}, {
  vendorId:3141,productId:32973,suppliers:[`gameunctrl`,`edravn`,`gattmoo`,`xiberia`]
}, {
  vendorId:3141,productId:32974,suppliers:[`he68pro`]
}, {
  vendorId:3141,productId:32972,suppliers:[`blkey`,`gattmoo`,`fire`,`ldon`,`darkprojecteu`,`rsq`,`he68pro`,`vrlkyborad`]
}, {
  vendorId:3141,productId:32966,suppliers:[]
}, {
  vendorId:3141,productId:32964,suppliers:[]
}, {
  vendorId:3141,productId:32967,suppliers:[]
}, {
  vendorId:3141,productId:32959,suppliers:[]
}, {
  vendorId:3141,productId:32790,suppliers:[`io`,`nubi`,`ajazz`]
}, {
  vendorId:3504,productId:59976,suppliers:[]
}, {
  vendorId:3141,productId:32968,suppliers:[]
}, {
  vendorId:3141,productId:32969,suppliers:[`nubi`,`io`,`nu31`]
}, {
  vendorId:1452,productId:592,suppliers:[`epomaker`,`cidoo`,`varo`,`avax`,`titanwolf`,`epomaker-uk`]
}, {
  vendorId:3141,productId:34822,suppliers:[`xvx`,`ajazz`,`gwings`]
}, {
  vendorId:14502,productId:10003,suppliers:[`k68`]
}, {
  vendorId:3141,productId:32960,suppliers:[]
}, {
  vendorId:3141,productId:35329,suppliers:[`aoc-k68`,`spawn`,`aoc-k68`]
}, {
  vendorId:3141,productId:32839,suppliers:[`onikua`,`ajazz`]
}, {
  vendorId:3141,productId:32921,suppliers:[`ajazz`]
}, {
  vendorId:14502,productId:10010,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32792,suppliers:[`apeha`]
}, {
  vendorId:10406,productId:10015,suppliers:[`fortrek`]
}, {
  vendorId:3141,productId:32977,suppliers:[`attackshark`]
}, {
  vendorId:3141,productId:32780,suppliers:[`ajazz`,`meypalie`,`imice`,`epomaker`]
}, {
  vendorId:1452,productId:599,suppliers:[`darkprojecteu`]
}, {
  vendorId:3141,productId:32803,suppliers:[]
}, {
  vendorId:1452,productId:593,suppliers:[`epomaker-uk`]
}, {
  vendorId:14502,productId:10011,suppliers:[`aula`]
}, {
  vendorId:3141,productId:10001,suppliers:[]
}, {
  vendorId:3141,productId:32961,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:65273,suppliers:[`xiberia`,`weikav`,`langtu`,`jdjz`,`1stplayer`,`ajazz`]
}, {
  vendorId:3141,productId:64256,suppliers:[]
}, {
  vendorId:3141,productId:32848,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:10003,suppliers:[]
}, {
  vendorId:1452,productId:594,suppliers:[`darkprojectru`]
}, {
  vendorId:3141,productId:32809,suppliers:[`a-jazz`,`ajazz`]
}, {
  vendorId:10406,productId:10018,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32991,suppliers:[]
}, {
  vendorId:3141,productId:32852,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:33033,suppliers:[`naceb`,`sades`]
}, {
  vendorId:3141,productId:32980,suppliers:[`ldon`]
}, {
  vendorId:3141,productId:32981,suppliers:[`ajazz`,`darkprojecteu`]
}, {
  vendorId:3141,productId:32982,suppliers:[`io`,`ajazz`,`lunacy`,`swift`,`nu31`]
}, {
  vendorId:3141,productId:32983,suppliers:[`dsm`,`ajazz`,`io`,`nu31`]
}, {
  vendorId:3141,productId:32984,suppliers:[`fire`,`k-trajectory`]
}, {
  vendorId:3141,productId:32779,suppliers:[`epomaker`,`nsyca`]
}, {
  vendorId:3141,productId:32993,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:65273,suppliers:[]
}, {
  vendorId:3141,productId:36865,suppliers:[]
}, {
  vendorId:3141,productId:34827,suppliers:[]
}, {
  vendorId:3141,productId:34828,suppliers:[`weikav`,`jdjz`]
}, {
  vendorId:3141,productId:34820,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32787,suppliers:[]
}, {
  vendorId:3141,productId:34819,suppliers:[`ajazz`,`archon`,`xiberia`]
}, {
  vendorId:3141,productId:65274,suppliers:`light67.ganss.xiberia.xinmeng.langtu.ajazz.k-trajectory.meypalie.darkprojecteu.attackshark.sades.ndiy.basike.womiercustomer.thunderobot.gamepro.graviontr.edra.ega-type-cmk13.hjsdzhi.nacodex.ega-jjkss2p2.xpanse.epomaker.game.lunacy.szstarwave.weikav.acefast.thinkway`.split(`.`)
}, {
  vendorId:14502,productId:10018,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10019,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10020,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10023,suppliers:[`aula`]
}, {
  vendorId:10024,productId:14502,suppliers:[`aula`,`magnus`]
}, {
  vendorId:3141,productId:32784,suppliers:[`ganss`,`epomaker`,`colorfulkb`]
}, {
  vendorId:6645,productId:22368,suppliers:[]
}, {
  vendorId:14502,productId:10015,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32985,suppliers:[`io`]
}, {
  vendorId:3141,productId:10002,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10036,suppliers:[`aula`]
}, {
  vendorId:3141,productId:33024,suppliers:[`epomaker`]
}, {
  vendorId:14502,productId:10012,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32986,suppliers:[`the-g-lab`]
}, {
  vendorId:3141,productId:32785,suppliers:[`epomaker`,`kb884l_he`]
}, {
  vendorId:14502,productId:10037,suppliers:[`jdjz-g75`,`jdjz`]
}, {
  vendorId:3141,productId:32776,suppliers:[`epomaker`,`darkprojectru`,`kisnt`,`imice`,`langtu`]
}, {
  vendorId:14502,productId:10497,suppliers:[]
}, {
  vendorId:14502,productId:10024,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10043,suppliers:[`aula`]
}, {
  vendorId:3141,productId:34829,suppliers:[`ajazz`,`womiercustomer`,`nacodex`]
}, {
  vendorId:14502,productId:10049,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32988,suppliers:[]
}, {
  vendorId:14502,productId:10048,suppliers:[]
}, {
  vendorId:3141,productId:32994,suppliers:[`re68`]
}, {
  vendorId:3141,productId:32883,suppliers:[`xinmeng`]
}, {
  vendorId:3141,productId:10011,suppliers:[`kurokey-gemrise`]
}, {
  vendorId:6127,productId:25328,suppliers:[`aula`]
}, {
  vendorId:3141,productId:10025,suppliers:[]
}, {
  vendorId:14502,productId:10047,suppliers:[]
}, {
  vendorId:14502,productId:10059,suppliers:[`swift`]
}, {
  vendorId:14502,productId:10057,suppliers:[]
}, {
  vendorId:14502,productId:10058,suppliers:[]
}, {
  vendorId:14502,productId:10056,suppliers:[]
}, {
  vendorId:14502,productId:10055,suppliers:[]
}, {
  vendorId:14502,productId:10054,suppliers:[]
}, {
  vendorId:14502,productId:10061,suppliers:[`hyekit`]
}, {
  vendorId:14502,productId:32929,suppliers:[]
}, {
  vendorId:14502,productId:10504,suppliers:[`aula`]
}, {
  vendorId:3141,productId:1452,suppliers:[`darkprojecteu`]
}, {
  vendorId:3141,productId:36881,suppliers:[]
}, {
  vendorId:14502,productId:10045,suppliers:[`aula`,`yunzii`]
}, {
  vendorId:6127,productId:25329,suppliers:[]
}, {
  vendorId:3141,productId:32987,suppliers:[`darkprojectru`]
}, {
  vendorId:14502,productId:10065,suppliers:[`kinet`]
}, {
  vendorId:3141,productId:32782,suppliers:[`weikav`]
}, {
  vendorId:14502,productId:10040,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10039,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10038,suppliers:[`aula`]
}, {
  vendorId:3141,productId:33037,suppliers:[`ajazz`]
}, {
  vendorId:14502,productId:10510,suppliers:[`leobog`]
}, {
  vendorId:14502,productId:10509,suppliers:[`leobog`]
}, {
  vendorId:14502,productId:10060,suppliers:[`k68`]
}, {
  vendorId:14502,productId:10046,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10069,suppliers:[`aula`]
}, {
  vendorId:3141,productId:34821,suppliers:[]
}, {
  vendorId:14502,productId:10072,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10511,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10070,suppliers:[`aula`]
}, {
  vendorId:3141,productId:33011,suppliers:[]
}, {
  vendorId:14502,productId:10071,suppliers:[`aula`]
}, {
  vendorId:3141,productId:34824,suppliers:[`graviontr`]
}, {
  vendorId:14502,productId:10073,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10026,suppliers:[`aula`]
}, {
  vendorId:3141,productId:34826,suppliers:[`gamepro`,`game`]
}, {
  vendorId:3141,productId:32799,suppliers:[`ajazz`]
}, {
  vendorId:14502,productId:10508,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32978,suppliers:[`xiberia`]
}, {
  vendorId:3141,productId:33009,suppliers:[`lunacy`,`darkprojecteu`]
}, {
  vendorId:14502,productId:10507,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10074,suppliers:[`aula`]
}, {
  vendorId:3141,productId:33034,suppliers:[`darkprojecteu`,`sarukx99zodiac`]
}, {
  vendorId:3141,productId:32995,suppliers:[]
}, {
  vendorId:3141,productId:32771,suppliers:[`lunacy`]
}, {
  vendorId:3141,productId:33012,suppliers:[`darkprojectru`]
}, {
  vendorId:3141,productId:32958,suppliers:[`xinmeng`]
}, {
  vendorId:3141,productId:32904,suppliers:[`langtu`]
}, {
  vendorId:14502,productId:10025,suppliers:[`lunacy`]
}, {
  vendorId:3141,productId:33035,suppliers:[]
}, {
  vendorId:3141,productId:10004,suppliers:[]
}, {
  vendorId:3141,productId:35073,suppliers:[]
}, {
  vendorId:3141,productId:34830,suppliers:[`ajazz`]
}, {
  vendorId:14502,productId:10079,suppliers:[`thunderobot`]
}, {
  vendorId:3141,productId:32786,suppliers:[`epomaker`]
}, {
  vendorId:3504,productId:42914,suppliers:[]
}, {
  vendorId:3141,productId:33290,suppliers:[]
}, {
  vendorId:3141,productId:32783,suppliers:[`ajazz`,`nsyca`]
}, {
  vendorId:3141,productId:34831,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:32979,suppliers:[`weikav`]
}, {
  vendorId:3141,productId:34832,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:33015,suppliers:[`ajazz`]
}, {
  vendorId:14502,productId:10078,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10077,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10080,suppliers:[`aim-mag68`]
}, {
  vendorId:3141,productId:34833,suppliers:[`ajazz`]
}, {
  vendorId:14502,productId:34821,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32789,suppliers:[`basike`]
}, {
  vendorId:14502,productId:9007,suppliers:[`aula`]
}, {
  vendorId:14502,productId:9004,suppliers:[`aula`]
}, {
  vendorId:3141,productId:33041,suppliers:[`edra`]
}, {
  vendorId:3141,productId:38912,suppliers:[]
}, {
  vendorId:3141,productId:59392,suppliers:[]
}, {
  vendorId:3141,productId:33019,suppliers:[]
}, {
  vendorId:3141,productId:32862,suppliers:[]
}, {
  vendorId:14502,productId:9009,suppliers:[]
}, {
  vendorId:3141,productId:32794,suppliers:[]
}, {
  vendorId:14502,productId:10076,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32858,suppliers:[]
}, {
  vendorId:14502,productId:10085,suppliers:[`thunderobot`]
}, {
  vendorId:14502,productId:10082,suppliers:[`aula`]
}, {
  vendorId:3141,productId:34835,suppliers:[]
}, {
  vendorId:14707,productId:274,suppliers:[`thunderobot`]
}, {
  vendorId:3141,productId:34834,suppliers:[`ajazz`]
}, {
  vendorId:3141,productId:33020,suppliers:[`sades`]
}, {
  vendorId:3141,productId:34837,suppliers:[]
}, {
  vendorId:3141,productId:34838,suppliers:[]
}, {
  vendorId:3141,productId:32798,suppliers:[]
}, {
  vendorId:3141,productId:33274,suppliers:[`lunacy`]
}, {
  vendorId:3141,productId:33016,suppliers:[]
}, {
  vendorId:14502,productId:9008,suppliers:[`aula`]
}, {
  vendorId:3141,productId:34840,suppliers:[`szstarwave`]
}, {
  vendorId:3141,productId:32797,suppliers:[]
}, {
  vendorId:3141,productId:32810,suppliers:[]
}, {
  vendorId:14502,productId:10088,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32801,suppliers:[]
}, {
  vendorId:3141,productId:10010,suppliers:[]
}, {
  vendorId:3141,productId:34049,suppliers:[`langtu`]
}, {
  vendorId:3141,productId:32795,suppliers:[]
}, {
  vendorId:3141,productId:32886,suppliers:[]
}, {
  vendorId:14502,productId:9006,suppliers:[`aula`]
}, {
  vendorId:14502,productId:10089,suppliers:[`kinet`,`cudy`]
}, {
  vendorId:14502,productId:10086,suppliers:[`aula`]
}, {
  vendorId:3141,productId:32769,suppliers:[]
}, {
  vendorId:3141,productId:34864,suppliers:[`nacodex`]
}, {
  vendorId:3141,productId:34865,suppliers:[`nacodex`]
}, {
  vendorId:3141,productId:34866,suppliers:[`nacodex`]
}, {
  vendorId:3141,productId:34573,suppliers:[]
}, {
  vendorId:14502,productId:9016,suppliers:[]
}, {
  vendorId:3141,productId:36885,suppliers:[]
}, {
  vendorId:3141,productId:36888,suppliers:[]
}, {
  vendorId:3141,productId:36880,suppliers:[]
}, {
  vendorId:3141,productId:32796,suppliers:[]
}, {
  vendorId:3141,productId:34839,suppliers:[]
}, {
  vendorId:3141,productId:34859,suppliers:[`graviontr`]
}, {
  vendorId:3141,productId:32975,suppliers:[]
}, {
  vendorId:3141,productId:34317,suppliers:[]
}, {
  vendorId:3141,productId:34319,suppliers:[]
}, {
  vendorId:3141,productId:33023,suppliers:[]
}, {
  vendorId:3141,productId:32989,suppliers:[]
}, {
  vendorId:3141,productId:34858,suppliers:[]
}, {
  vendorId:3141,productId:34860,suppliers:[]
}, {
  vendorId:3141,productId:34853,suppliers:[]
}, {
  vendorId:3141,productId:32781,suppliers:[`ajazz`]
}]

// ===== re =====
function re(t) {
  let {
    onFocus:n,showOnFocus:r
  }=e, {
    nTriggerFormFocus:i
  }=te;
  n&&gh(n,t),i(),r&&ce()
}

// ===== oe =====
function oe() {
  P.value=!1,e.ignoreComposition&&k(re),re=null
}

// ===== HX =====
HX= {
  COMMUNICATION_START:1,COMMUNICATION_END:2,SET_FACTORY_RESET:15,GET_DEVICE_INFO:16,GET_GAME_MODE:17,GET_KEY:18,GET_LED_EFFECT:19,GET_CUSTOM_LED_DATA:20,GET_MACRO:21,GET_FN_KEY:22,GET_MAGNETIC_AXIS_RT:23,GET_MAGNETIC_AXIS_DKS_DATA:24,GET_LIGHT_BOX:27,GET_DEFAULT_FN_KEY_MATRIX:28,GET_SIDE_LIGHT:29,GET_TRIGGER_KEY:30,GET_DEFAULT_KEY_MATRIX:31,SET_GAME_MODE:33,SET_KEY:34,SET_LED_EFFECT:35,SET_CUSTOM_LED_DATA:36,SET_MACRO:37,SET_FN_KEY:38,SET_MAGNETIC_AXIS_RT:39,SET_MAGNETIC_AXIS_DKS_DATA:40,SET_DOT_MATRIX_MODE:42,SET_LIGHT_BOX:43,SET_SIDE_LIGHT:45,SET_TRIGGER_KEY:46,SET_KEYBOARD_CUSTOM_FUNCTION_ON:48,SET_KEYBOARD_CUSTOM_FUNCTION_OFF:49,GET_LED_DATA:50,GET_ALL_LIGHTS_RGB:51,SET_TEMPORARY_COMMAND_DATA:52,SET_MUSIC_DATA:53,CLEAR_LED_DATA:54,GET_ALL_LIGHTS_RGB_24G:55,GET_ALL_LIGHTS_RGB_24G_64_BYTE:59,SET_MUSIC_DATA_24G_64_BYTE:60,GET_DOT_MATRIX_CONFIG:61,SET_LED_BOOT_ANIMATION:64,SET_LED_USER_ANIMATION:65,SET_LED_DATA:66,SET_TFT_MATERIAL:77,SET_FLASH_DOWNLOAD:79,SET_TFT_USER_ANIMATION:80,SET_TFT_BUILT_IN_INDEX:81,GET_MAGNETIC_AXIS_KEY_STATUS:96,SET_CALIBRATION_ON:100,SET_CALIBRATION_OFF:101,SET_SIMULATION_TEST_ON:102,SET_SIMULATION_TEST_OFF:103,GET_MAGNETIC_AXIS_STATUS:104,SET_CALIBRATION_ON_V2:105,SET_CALIBRATION_OFF_V2:106,OTA_GET_DEVICE_SYSTEM_INFO:128,OTA_VERIFY_FIRMWARE_INFO:129,OTA_DEVICE_ENTER_BOOT:130,OTA_SEND_FIRMWARE_INFO:131,OTA_GET_DEVICE_SN:132,OTA_SWITCH_APP_PARTITION:133,OTA_SET_DEVICE_SN:134,SET_PROFILE:144,GET_DEVICE_NOTIFY:250,GET_MAGNETIC_AXIS_CALIBRATION_DATA:251,GET_24G_DISCONNECT_NOTIFY:252
}

// ===== VX =====
VX=0

// ===== UX =====
UX= {
  KEY_RESET:1,LIGHTING_RESET:2,MACRO_RESET:4,CLEAR_CALIBRATION:5,RESET_ALL:255
}

// ===== BX =====
BX=null
