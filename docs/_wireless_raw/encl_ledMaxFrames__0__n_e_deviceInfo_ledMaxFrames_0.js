 {
  let t=VV(), {
    sendReport:n
  }=rY(), {
    currentDeviceId:r
  }=HY(),i=$I(r, {

  }),a=OF(),o=R([]),s=R(!1),c=R(0),l=R(!1),u=R(null),d=R(!1),f=GV(`markdown/AI_LED_GUIDE.md`),p=K(()=>$(`ai_led_prompt`,[e.ledConfig.rows,e.ledConfig.cols,e.deviceInfo.ledMaxFrames])),m=R(``),h=R(!1),g=R(``),_=K(()=>o.value.filter(e=>e.type)),v=K(()=>t?o.value.filter(e=>!e.type):o.value.filter(e=>!e.type&&!i7(e.ledId))),y=async e=> {
    g.value!==e.ledId&&(g.value=e.ledId,window.dispatchEvent(new Event(`stop-led-sync`)),await n(`setDotMatrixMode`,void 0, {
      type:e.type,dotMatrixMode:2
    }))
  },b=(t,n)=>(t.ledId===`startup`||t.ledId===`LEOBOG_AMG65`)&&n>200?new Promise(e=> {
    $dialog.warning( {
      title:$(`update_title`),content:$(`led_text29`),positiveText:$(`confirm`),negativeText:$(`cancel`),onPositiveClick:()=> {
        e(!0)
      },onNegativeClick:()=> {
        e(!1)
      }
    })
  }):e.deviceInfo.ledMaxFrames!=0&&n>e.deviceInfo.ledMaxFrames?new Promise(t=> {
    $dialog.warning( {
      title:$(`update_title`),content:$(`led_text30`)+e.deviceInfo.ledMaxFrames,positiveText:$(`confirm`),negativeText:$(`cancel`),onPositiveClick:()=> {
        t(!0)
      },onNegativeClick:()=> {
        t(!1)
      }
    })
  }):e.deviceInfo.ledMaxFrames==0&&n>260?new Promise(e=> {
    $dialog.warning( {
      title:$(`update_title`),content:$(`led_text31`),positiveText:$(`confirm`),negativeText:$(`cancel`),onPositiveClick:()=> {
        e(!0)
      },onNegativeClick:()=> {
        e(!1)
      }
    })
  }):Promise.resolve(!0),x=async t=> {
    window.dispatchEvent(new Event(`stop-led-sync`)),g.value=t.ledId;
    let r=t.data,i=r.length/e.ledConfig.cols/e.ledConfig.rows;
    if(!await b(t,i))return;
    if([`r5c63`,`r5c63_aula`].includes(e.ledConfig.localforageKey)) {
      let t=[];
      for(let n=0;
      n<i;
      n++) {
        let i=n*e.ledConfig.cols*e.ledConfig.rows,a=(n+1)*e.ledConfig.cols*e.ledConfig.rows,o=zV(r.slice(i,a),G5);
        t=t.concat(o)
      }r=t
    }let a=r.map(e=>RV(e)),o=new Uint8Array(4);
    o[0]=i&255,o[1]=i>>8&255,o[2]=Math.ceil(106-t.speed)&255,o[3]=Math.ceil(106-t.speed)>>8&255,s.value=!0,await n(`setLedUserAnimation`,void 0,o,a,e=> {
      c.value=e
    }),s.value=!1,c.value=0
  },S=e=> {
    s.value=e.show,c.value=e.percent
  },C=(e,t)=> {
    lie(e,x,t)
  },w=K(()=>e.keyboardConfig.communityConfig?.communityList?.includes(`led`)),T=R(!1),E=R(!1),D=R(``),O=R(),k=R(!1),ee=$I(`userInfo`, {

  }),A=e=> {
    if(e?.data?.length&&!n7(e.ledId)) {
      if(O.value=e,!Object.keys(ee.value).length) {
        k.value=!0;
        return
      }D.value=``,T.value=!0
    }
  },te=()=> {
    O.value&&(D.value=``,T.value=!0)
  },j=async t=> {
    let n=e.ledConfig.cols*e.ledConfig.rows,r=t.data.length/n;
    if(!await b(t,r))return null;
    let i=e.deviceInfo.ledMaxFrames,a=t.data;
    (t.ledId===`startup`||t.ledId===`LEOBOG_AMG65`)&&r>200?a=t.data.slice(0,200*n):i!=0&&r>i?a=t.data.slice(0,i*n):i==0&&r>260&&(a=t.data.slice(0,260*n));
    let o= {
      ledId:t.ledId,name:t.text?$(t.text):t.name,data:a,speed:t.speed
    },s=new Blob([JSON.stringify(o)], {
      type:`application/json`
    }),c=await F6(new File([s],`led_animation.json`, {
      type:`application/json`
    }));
    return c.code===1?c:($message.error(c.msg||$(`screen_text14`)),null)
  },M=async()=> {
    let t=O.value;
    if(!t)return;
    if(!D.value.trim()) {
      $message.warning($(`tables_title4`)+$(`login_tips3`));
      return
    }let n=e.keyboardConfig.communityConfig?.communityDeviceInfo,r=n?.deviceProductId||e.keyboardConfig.productId,i=n?.deviceName||e.keyboardConfig.name;
    if(!r||!i) {
      $message.error($(`screen_text14`));
      return
    }E.value=!0;
    try {
      let e=await j(t);
      if(!e)return;
      let n=await I6( {
        file_name:t.text?$(t.text):t.name,file_description:D.value.trim(),file_json:[e.data.fullurl],device_id:r,device_model:i,sensitive:0,type:5
      });
      if(n.code!==1) {
        $message.error(n.msg||$(`screen_text14`));
        return
      }T.value=!1,D.value=``,$message.success($(`macro_success`))
    }catch(e) {
      console.error(`分享失败:`,e),$message.error($(`screen_text14`)+(e.message||``))
    }finally {
      E.value=!1
    }
  },N=async t=> {
    h.value=!0;
    try {
      let n=JSON.parse(t),r=Rie(e.deviceInfo.ledMaxFrames),i=zie(n,e.ledConfig.cols,e.ledConfig.rows,r);
      if(!i.ok) {
        switch(i.error) {
          case`data_length_mismatch`:$message.error($(`led_import_data_length_mismatch`,[i.dataLength??0,i.rows??e.ledConfig.rows,i.cols??e.ledConfig.cols,i.cellCount??e.ledConfig.cols*e.ledConfig.rows]));
          break;
          case`frame_limit_exceeded`:$message.error($(`led_text30`)+(i.maxFrames??r));
          break;
          default:$message.error($(`ai_lighting_import_invalid`))
        }return
      }let a=d7(),s= {
        ledId:a,...i.item
      },c=await sQ.default.getItem(`led_list_`+e.ledConfig.localforageKey)||[];
      c.push(a),await sQ.default.setItem(`led_list_`+e.ledConfig.localforageKey,c),await sQ.default.setItem(`led_item_`+e.ledConfig.localforageKey+`_`+a,s),o.value.push(s),g.value=a,$message.success($(`ai_lighting_import_success`)),d.value=!1,m.value=``
    }catch {
      $message.error($(`ai_lighting_import_failed`))
    }finally {
      h.value=!1
    }
  },ne=async()=> {
    let t=d7();
    g.value=t;
    let n= {
      ledId:t,name:$(`led_text55`),data:Array(e.ledConfig.cols*e.ledConfig.rows).fill(`#000000`),speed:100
    },r=await sQ.default.getItem(`led_list_`+e.ledConfig.localforageKey)||[];
    r.unshift(t),await sQ.default.setItem(`led_list_`+e.ledConfig.localforageKey,r),await sQ.default.setItem(`led_item_`+e.ledConfig.localforageKey+`_`+t,n),o.value.unshift(n)
  },P=async()=> {
    if(!g.value)return;
    let t=await sQ.default.getItem(`led_item_`+e.ledConfig.localforageKey+`_`+g.value);
    t&&(u.value=t,l.value=!0)
  },F=()=> {
    l.value=!1,u.value=null,o.value=[],he()
  },re=async e=> {
    await x(e)
  },ie=async()=> {
    if(!g.value)return;
    let t=await sQ.default.getItem(`led_item_`+e.ledConfig.localforageKey+`_`+g.value);
    if(!t)return;
    let n=d7(),r= {
      ledId:n,name:t.text?$(t.text):t.name,data:t.data,speed:t.speed
    };
    await sQ.default.setItem(`led_item_`+e.ledConfig.localforageKey+`_`+n,r),o.value.push(r);
    let i=await sQ.default.getItem(`led_list_`+e.ledConfig.localforageKey)||[];
    i.push(n),await sQ.default.setItem(`led_list_`+e.ledConfig.localforageKey,i),g.value=n
  },ae=()=> {
    $dialog.warning( {
      title:$(`update_title`),content:$(`led_text28`),positiveText:$(`confirm`),negativeText:$(`cancel`),onPositiveClick:async()=> {
        if(!g.value)return;
        let t=await sQ.default.getItem(`led_list_`+e.ledConfig.localforageKey)||[];
        t.splice(t.indexOf(g.value),1),await sQ.default.setItem(`led_list_`+e.ledConfig.localforageKey,t),await sQ.default.removeItem(`led_item_`+e.ledConfig.localforageKey+`_`+g.value),o.value=o.value.filter(e=>e.ledId!==g.value),g.value=``
      }
    })
  },oe=R(null),se=async()=> {
    let e=await OY();
    oe.value=e
  },ce=R(null),le=()=> {
    v.value.some(e=>[`r5c63NetworkSpeed`,`r5c63CPU`,`r5c63GPU`,`r5c63Music`].includes(e.ledId))&&(se(),ce.value=_Y(()=> {
      se()
    },1e3))
  },I=R(null),ue=async()=> {
    let e=await wY();
    I.value=e
  },de=R(null),fe=async()=> {
    if(v.value.some(e=>[`r5c63Music`,`r5c51Music`].includes(e.ledId))) {
      let t= {
        name:e.keyboardConfig.name,vendorId:e.keyboardConfig.vendorId,productId:e.keyboardConfig.productId,deviceMode:e.keyboardConfig.connectType===`USB`?0:1,layouts: {
          rows:e.ledConfig.rows,cols:e.ledConfig.cols,keys:pe(e.ledConfig.rows,e.ledConfig.cols)
        }
      };
      await CY(encodeURIComponent(me(JSON.stringify(t)))),await TY(`2&30&0&0&0`),de.value=_Y(()=> {
        ue()
      },50)
    }
  },pe=(e,t)=> {
    let n=[],r=0;
    for(let i=0;
    i<e;
    i++)for(let e=0;
    e<t;
    e++)n.push( {
      row:i,col:e,name:``,code:i*t+e
    }),r++;
    return n
  },me=e=> {
    let t=new TextEncoder().encode(e);
    return btoa(String.fromCharCode.apply(null,Array.from(t)))
  },he=async()=> {
    let n=await sQ.default.getItem(`led_list_`+e.ledConfig.localforageKey)||[];
    if(n.length===0)switch(e.ledConfig.localforageKey) {
      case`r5c63`:await _e([`LEOBOG_AMG65`,`cpu`,`gpu`,`network_speed`,`datetime`,`tips`,`music`,`tree`,`aurora`,`rainbow`,`spaceTime`]),await ge();
      break;
      case`r5c63_aula`:await _e([`AULA_AMG65`,`cpu`,`gpu`,`network_speed`,`datetime`,`tips`,`music`,`tree`,`aurora`,`rainbow`,`spaceTime`]),await ge();
      break;
      case`r7c7`:await _e([`aula`,`chart`,`happy`,`iLoveYou`,`meteorShower`,`bouncingBall`,`rollingColorBar`,`rollingRedHeart`,`rollingBall`,`exciteMood`,`failingAtBothEnds`,`floatingfern`,`sokoban`,`downFloor`,`spinballs`]);
      break;
      case`r5c51`:await _e([`cycleEffect`,`eatEffect`,`flowEffect`,`gameEffect`,`jumpEffect`,`ledEffect`,`ledEffect1`,`runEffect`,`music`,`rzEffect`]);
      break;
      case`r5c67`:await _e([`eatEffect`,`gameEffect`,`coldRain`,`kirby`,`zombies`]);
      break;
      case`r6c41`:await _e([`gattmoo`,`cat`,`gameEffect`,`tiger`,`meteor`,`fallGuys`]);
      break;
      case`r7c7_xiberia`:await _e([`rainbowLove`,`monochromeLove`,`intersection`,`emotionalDialog`,`snake`,`rain`,`musicWave`,`rainyDay`]);
      break;
      case`r5c51_atmos`:await _e([`cycleEffect`,`eatEffect`,`flowEffect`,`gameEffect`,`jumpEffect`,`ledEffect`,`ledEffect1`,`runEffect`,`music`,`rzEffect`,`ssEffect`,`userAnimation`]);
      break;
      case`r9c24`:await _e([`r9c24Aula`]);
      break;
      case`r7c14`:await _e([`r7c14RainbowCar`,`r7c14HeartArrow`,`r7c14Eye`,`r7c14WoodFish`,`r7c14BeautifulFireworks`,`r7c14RunningBall`]);
      break;
      case`r7c7_p75`:await _e([`r7c7P75Iloveu`,`r7c7P75Block`,`r7c7P75Excite`,`r7c7P75Gorgeous`,`r7c7P75Rainbow`,`r7c7P75RainbowCart`,`r7c7P75Spring`]);
      break;
      case`r7c28`:await _e([`r7c28Hello`,`r7c28Wow`,`r7c28Hopscotch`,`r7c28EludeBarrage`]);
      break;
      case`r7c28_epomaker`:await _e([`r7c28EpomakerHappy`,`r7c28EpomakerSpring`,`r7c28EpomakerDemon`,`r7c28EpomakerFish`,`r7c28EpomakerPet`,`r7c28EpomakerFireworks`,`r7c28EpomakerBall`,`r7c28EpomakerSpider`]);
      break;
      case`r7c7_ajazz`:await _e([`r7c7AjazzRainbowCar`,`r7c7AjazzSpring`,`r7c7AjazzHorse`,`r7c7AjazzTetris`,`r7c7AjazzPikachu`,`r7c7AjazzFace`,`r7c7AjazzExcited`,`r7c7AjazzBounce`,`r7c7AjazzSnake`,`r7c7AjazzUp`,`r7c7AjazzKaleidoscope`,`r7c7AjazzFireworks`]);
      break;
      case`r7c7_hfd`:await _e([`r7c7HfdRainbowCar`,`r7c7HfdSpring`,`r7c7HfdHorse`,`r7c7HfdTetris`,`r7c7HfdPikachu`,`r7c7HfdFace`,`r7c7HfdExcited`,`r7c7HfdBounce`,`r7c7HfdSnake`,`r7c7HfdUp`,`r7c7HfdKaleidoscope`,`r7c7HfdFireworks`]);
      break;
      default:console.warn(`未找到默认图案：`,e.ledConfig.localforageKey)
    }else for(let t of n) {
      let n=await sQ.default.getItem(`led_item_${e.ledConfig.localforageKey}_${t}`);
      n&&o.value.push(n)
    }let r=i.value.ledData?.type,a=o.value.find(e=>e.type===r);
    if(a&&(g.value=a.ledId),!g.value) {
      let e=o.value.filter(e=>e.type);
      if(e.length>0)g.value=e[0].ledId;
      else {
        let e=t?o.value.filter(e=>!e.type):o.value.filter(e=>!e.type&&!i7(e.ledId));
        e.length>0&&(g.value=e[0].ledId)
      }
    }
  };
  (async()=> {
    await he(),le(),fe()
  })();
  let ge=async()=> {
    let t=[`Amazing`,`Lets_go`,`AcrossTheRainbow`,`HeartRhythm`,`Cyberstreamer`,`Spaceman`,`Gorgeous`,`VideohvieSta`];
    for(let n=0;
    n<t.length;
    n++) {
      let r=await ve(e.ledConfig.localforageKey,t[n]);
      await sQ.default.setItem(`led_item_`+e.ledConfig.localforageKey+`_`+t[n],r)
    }
  },_e=async t=> {
    await sQ.default.setItem(`led_list_`+e.ledConfig.localforageKey,t);
    let n=[];
    for(let r of t) {
      let t=await ve(e.ledConfig.localforageKey,r);
      n.push(t),await sQ.default.setItem(`led_item_`+e.ledConfig.localforageKey+`_`+r,t)
    }o.value=n
  },ve=async(e,t)=> {
    let n=GV(`/json/${e}/${t}.json`),r=await fetch(n);
    if(!r.ok)throw Error(`Failed to fetch ${n}`);
    return await r.json()
  };
  function ye() {
    let e=(0,QV.default)().format(`YYYY-MM-DD HH:mm:ss`),t=(0,QV.default)().day();
    n(`setLedDateTime`,void 0,e,t)
  }return Ki(()=> {
    ce.value&&hY(ce.value),de.value&&hY(de.value)
  }), {
    themeVars:a,builtInList:_,customList:v,currentledId:g,hardwareInfo:oe,ledMusicData:I,syncDialogVisible:s,syncProgress:c,editorVisible:l,editingLed:u,handleChangeBuiltInLed:y,handleAddLedAnimation:ne,handleEditLedAnimation:P,handleCopyLedAnimation:ie,handleDeleteLedAnimation:ae,handleTimeCalibration:ye,handleSyncProgress:S,handleApply:x,applyCustomLedItem:C,handleEditorBack:F,handleEditorUpload:re,showImportModal:d,importGuideUrl:f,importPromptText:p,importCode:m,importing:h,handleImportLedAnimation:N,isSystemLedId:cie,isSyncLedId:n7,isShowShare:w,isShare:T,shareLoading:E,shareDescription:D,showLoginModal:k,handleShare:A,handleAddShare:M,handleLoginSuccess:te
  }
}