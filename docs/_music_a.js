pe;
return e===`line`?[ {
  label:$(`music_diy_horizontal`),
  value:`horizontal`
},
 {
  label:$(`music_diy_vertical`),
  value:`vertical`
}]:e===`circle`?[ {
  label:$(`music_diy_radial`),
  value:`radial`
}]:[ {
  label:$(`music_diy_up`),
  value:`up`
},
 {
  label:$(`music_diy_down`),
  value:`down`
},
 {
  label:$(`music_diy_left`),
  value:`left`
},
 {
  label:$(`music_diy_right`),
  value:`right`
}]
});
function a(e) {
  return r.value.find(t=>t.value===e)?.label??e
}return(e,
o)=> {
  let s=Ek,
  c=Xk,
  l=gne,
  u=qA,
  d=uA,
  f=_A,
  p=lF,
  m=OP,
  h=gF;
  return H(),
  U(`div`,
  poe,
  [W(`section`,
  moe,
  [W(`div`,
  hoe,
  [W(`h3`,
  goe,
  L(z($)(`music_diy_shapes`)),
  1),
  G(s,
   {
    size:`small`,
    secondary:``,
    onClick:z(t).resetAllShapes
  },
   {
    default:B(()=>[vs(L(z($)(`music_diy_reset_all`)),
    1)]),
    _:1
  },
  8,
  [`onClick`])]),
  W(`div`,
  _oe,
  [(H(!0),
  U($o,
  null,
  aa(z(r),
  e=>(H(),
  ls(s,
   {
    key:e.value,
    size:`small`,
    onClick:n=>z(t).addShape(e.value)
  },
   {
    default:B(()=>[vs(L(e.label),
    1)]),
    _:2
  },
  1032,
  [`onClick`]))),
  128))]),
  W(`div`,
  voe,
  [(H(!0),
  U($o,
  null,
  aa(z(t).shapes.value,
  (e,
  n)=>(H(),
  U(`div`,
   {
    key:e.id,
    class:`flex items-center gap-2`
  },
  [G(c,
   {
    checked:e.visible,
    "onUpdate:checked":n=>z(t).updateShape(e.id,
     {
      visible:n
    })
  },
  null,
  8,
  [`checked`,
  `onUpdate:checked`]),
  W(`button`,
   {
    type:`button`,
    class:me([`min-w-0 flex flex-1 items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors`,
    e.id===z(t).selectedShapeId.value?`border-primary bg-primary/10 text-primary`:`border-brand-border bg-transparent`]),
    onClick:n=>z(t).selectShape(e.id)
  },
  [W(`span`,
   {
    class:me( {
      "opacity-45":!e.visible
    })
  },
  L(a(e.type))+` `+L(n+1),
  3),
  W(`span`,
   {
    class:me([`size-4 rounded-full`,
     {
      "music-diy-rgb-swatch":e.colorMode===`rgb`,
      "opacity-45":!e.visible
    }]),
    style:I(e.colorMode===`single`? {
      backgroundColor:e.color
    }:void 0)
  },
  null,
  6)],
  10,
  yoe)]))),
  128))])]),
  z(n)?(H(),
  U(`section`,
  boe,
  [W(`h3`,
  xoe,
  L(z($)(`music_diy_shape_config`)),
  1),
  W(`div`,
  Soe,
  [W(`div`,
  Coe,
  L(z($)(`lighting_color_mode`)),
  1),
  G(u,
   {
    value:z(n).colorMode,
    "onUpdate:value":o[0]||=e=>z(t).updateShape(z(n).id,
     {
      colorMode:e
    })
  },
   {
    default:B(()=>[G(l,
     {
      value:`rgb`
    },
     {
      default:B(()=>[...o[11]||=[vs(`RGB`,
      -1)]]),
      _:1
    }),
    G(l,
     {
      value:`single`
    },
     {
      default:B(()=>[vs(L(z($)(`lighting_single_color`)),
      1)]),
      _:1
    })]),
    _:1
  },
  8,
  [`value`])]),
  z(n).colorMode===`single`?(H(),
  U(`div`,
  woe,
  [W(`div`,
  Toe,
  L(z($)(`music_diy_color`)),
  1),
  G(d,
   {
    value:z(n).color,
    "show-alpha":!1,
    "onUpdate:value":o[1]||=e=>z(t).updateShape(z(n).id,
     {
      color:e
    })
  },
  null,
  8,
  [`value`])])):bs(``,
  !0),
  z(n).type===`circle`?bs(``,
  !0):(H(),
  U(`div`,
  Eoe,
  [W(`div`,
  Doe,
  L(z($)(`music_diy_direction`)),
  1),
  G(f,
   {
    value:z(n).direction,
    options:z(i),
    "onUpdate:value":o[2]||=e=>z(t).updateShape(z(n).id,
     {
      direction:e
    })
  },
  null,
  8,
  [`value`,
  `options`])])),
  W(`div`,
  Ooe,
  [W(`div`,
  koe,
  [W(`span`,
  null,
  L(z($)(`music_text3`)),
  1),
  W(`span`,
  null,
  L(z(n).amplitude)+`%`,
  1)]),
  G(p,
   {
    value:z(n).amplitude,
    min:10,
    max:200,
    step:5,
    "onUpdate:value":o[3]||=e=>z(t).updateShape(z(n).id,
     {
      amplitude:e
    })
  },
  null,
  8,
  [`value`])]),
  z(n).type===`bar`?(H(),
  U(`div`,
  Aoe,
  [W(`div`,
  joe,
  L(z($)(`music_diy_count`)),
  1),
  G(m,
   {
    value:z(n).count??36,
    min:1,
    max:50,
    "onUpdate:value":o[4]||=e=>z(t).updateShape(z(n).id,
     {
      count:e??36
    })
  },
  null,
  8,
  [`value`])])):bs(``,
  !0),
  z(n).type===`bar`?(H(),
  U(`div`,
  Moe,
  [W(`div`,
  Noe,
  [W(`span`,
  null,
  L(z($)(`music_diy_spacing`)),
  1),
  W(`span`,
  null,
  L(z(n).spacing??4),
  1)]),
  G(p,
   {
    value:z(n).spacing??4,
    min:1,
    max:10,
    step:1,
    "onUpdate:value":o[5]||=e=>z(t).updateShape(z(n).id,
     {
      spacing:e
    })
  },
  null,
  8,
  [`value`])])):bs(``,
  !0),
  z(n).type===`line`?(H(),
  U(`div`,
  Poe,
  [W(`div`,
  Foe,
  [W(`span`,
  null,
  L(z($)(`music_diy_thickness`)),
  1),
  W(`span`,
  null,
  L(z(n).thickness??12),
  1)]),
  G(p,
   {
    value:z(n).thickness??12,
    min:1,
    max:30,
    step:1,
    "onUpdate:value":o[6]||=e=>z(t).updateShape(z(n).id,
     {
      thickness:e
    })
  },
  null,
  8,
  [`value`])])):bs(``,
  !0),
  W(`div`,
  Ioe,
  [G(s,
   {
    secondary:``,
    onClick:o[7]||=e=>z(t).resetShape(z(n).id)
  },
   {
    default:B(()=>[vs(L(z($)(`music_diy_reset_shape`)),
    1)]),
    _:1
  }),
  G(s,
   {
    type:`error`,
    secondary:``,
    disabled:z(t).shapes.value.length<=1,
    onClick:o[8]||=e=>z(t).removeShape(z(n).id)
  },
   {
    default:B(()=>[vs(L(z($)(`music_diy_delete_shape`)),
    1)]),
    _:1
  },
  8,
  [`disabled`])])])):bs(``,
  !0),
  W(`section`,
  Loe,
  [W(`h3`,
  Roe,
  L(z($)(`music_diy_audio`)),
  1),
  z(t).hasDownloadPlugin.value?(H(),
  U(`div`,
  Uoe,
  [o[13]||=W(`span`,
   {
    class:`size-2 rounded-full bg-green-500`
  },
  null,
  -1),
  W(`span`,
  null,
  L(z($)(`music_diy_plugin_ready`)),
  1)])):(H(),
  U(`div`,
  zoe,
  [W(`p`,
  Boe,
  L(z($)(`music_mode_error`)),
  1),
  W(`p`,
  Voe,
  L(z($)(`music_mode_error2`)),
  1),
  W(`div`,
  Hoe,
  [z(t).isTestMode?(H(),
  ls(s,
   {
    key:0,
    size:`small`,
    type:`primary`,
    onClick:z(t).handleStartSystemAudio
  },
   {
    default:B(()=>[...o[12]||=[vs(` 无需插件 `,
    -1)]]),
    _:1
  },
  8,
  [`onClick`])):bs(``,
  !0),
  G(s,
   {
    size:`small`,
    secondary:``,
    onClick:z(t).retryPlugin
  },
   {
    default:B(()=>[vs(L(z($)(`medium_text13`)),
    1)]),
    _:1
  },
  8,
  [`onClick`]),
  G(s,
   {
    size:`small`,
    type:`primary`,
    onClick:z(t).handleDownload
  },
   {
    default:B(()=>[vs(L(z($)(`music_btn`)),
    1)]),
    _:1
  },
  8,
  [`onClick`])])])),
  z(t).isTestMode?(H(),
  U(`div`,
  Woe,
  [W(`div`,
  Goe,
  [W(`span`,
  null,
  L(z($)(`music_diy_test_mode`)),
  1),
  G(h,
   {
    value:z(t).isOpenTestMode.value,
    "onUpdate:value":o[9]||=e=>z(t).isOpenTestMode.value=e
  },
  null,
  8,
  [`value`])]),
  z(t).isOpenTestMode.value?(H(),
  ls(p,
   {
    key:0,
    value:z(t).testAmplitude.value,
    "onUpdate:value":o[10]||=e=>z(t).testAmplitude.value=e,
    min:0,
    max:1e3,
    step:1
  },
  null,
  8,
  [`value`])):bs(``,
  !0)])):bs(``,
  !0)])])
}
}
}),
[[`__scopeId`,
`data-v-97673abb`]]),
Koe= {
  class:`auto-bg rounded-lg px-4`
},
qoe=V( {
  __name:`musicDiy`,
  props: {
    controller: {

    }
  },
  setup(e) {
    return(t,
    n)=>(H(),
    U(`div`,
    Koe,
    [G(T7,
     {
      controller:e.controller
    },
    null,
    8,
    [`controller`])]))
  }
}),
Joe=t( {
  default:()=>E7
}),
E7=qoe;
function D7(e,
t) {
  let {
    keyList:n
  }=tX(),
  r=R(!1),
  i=()=> {
    EV(`https://config.driveall.cn/music/v2/Music.exe`)
  },
  a=$I(`musicV1Config`,
   {
    mode:1,
    amplitude:30,
    backmode:0,
    backmodebrightness:100
  }),
  o=R(0),
  s=R(a.value.mode||1),
  c=R(a.value.amplitude||30),
  l=R(a.value.backmode||0),
  u=R(a.value.backmodebrightness||100),
  d=K(()=> {
    let t=[ {
      label:$(`music_mode_text1`),
      value:1
    },
     {
      label:$(`music_mode_text2`),
      value:2
    },
     {
      label:$(`music_mode_text3`),
      value:13
    },
     {
      label:$(`music_mode_text4`),
      value:4
    },
     {
      label:$(`music_mode_text5`),
      value:5
    },
     {
      label:$(`music_mode_text6`),
      value:6
    },
     {
      label:$(`music_mode_text7`),
      value:7
    },
     {
      label:$(`music_mode_text8`),
      value:8
    },
     {
      label:$(`music_mode_text9`),
      value:9
    },
     {
      label:$(`music_mode_text10`),
      value:11
    },
     {
      label:$(`music_mode_text11`),
      value:10
    },
     {
      label:$(`music_mode_text21`),
      value:100
    }];
    return e.keyboardConfig.musicConfig?.filterMusicMode?.length&&(t=t.filter(t=>e.keyboardConfig.musicConfig?.filterMusicMode?.includes(t.value)),
    s.value=t[0].value),
    t
  }),
  f=K(()=>[ {
    label:$(`music_bg_text1`),
    value:0
  },
   {
    label:$(`music_bg_text2`),
    value:6
  },
   {
    label:$(`music_bg_text3`),
    value:7
  },
   {
    label:$(`music_bg_text4`),
    value:8
  },
   {
    label:$(`music_bg_text5`),
    value:9
  },
   {
    label:$(`music_bg_text6`),
    value:10
  },
   {
    label:$(`music_bg_text7`),
    value:11
  },
   {
    label:$(`music_bg_text8`),
    value:1
  },
   {
    label:$(`music_bg_text9`),
    value:2
  },
   {
    label:$(`music_bg_text10`),
    value:4
  },
   {
    label:$(`music_bg_text11`),
    value:5
  }]),
  p=e=> {
    s.value=e,
    a.value.mode=e,
    v()
  },
  m=e=> {
    c.value=e,
    a.value.amplitude=e,
    v()
  };
  l0(ii(`amplitudeRef`),
  c,
   {
    min:1,
    max:100,
    onChange:()=> {
      v()
    }
  });
  let h=e=> {
    l.value=e,
    a.value.backmode=e,
    v()
  },
  g=e=> {
    u.value=e,
    a.value.backmodebrightness=e,
    v()
  };
  l0(ii(`backmodebrightnessRef`),
  u,
   {
    min:1,
    max:100,
    onChange:()=> {
      v()
    }
  });
  let _=async()=> {
    try {
      let e=await wY();
      if(r.value=!0,
      e) {
        let r=JSON.parse(JSON.stringify(n.value));
        r.forEach(t=> {
          t.forEach(t=> {
            let n=e.keys.find(e=>e.keyIndex===t.value);
            if(delete t.userKey,
            t.name=``,
            delete t.text,
            t.disabledLight) {
              delete t.bgColor;
              return
            }t.bgColor=n?.color||`#000`
          })
        }),
        t(`update-key-list`,
        r)
      }
    }catch {

    }
  },
  v=EI(async()=> {
    try {
      await TY(`${s.value}&${c.value}&${l.value}&${u.value}&1`)
    }catch {
      console.error(`更改音乐律动模式失败`)
    }
  },
  300),
  y=e=> {
    let t=new TextEncoder().encode(e);
    return btoa(String.fromCharCode.apply(null,
    Array.from(t)))
  },
  b=async()=> {
    try {
      let {
        name:t,
        vendorId:n,
        productId:i,
        connectType:a,
        keyList:s,
        musicConfig:c
      }=e.keyboardConfig,
      l=s.reduce((e,
      t)=>Math.max(e,
      t.length),
      0),
      u=c?.maxColOffset||0,
      d=s.map((e,
      t)=> {
        let n=0;
        return e.map((e,
        r)=> {
          let i=r+n;
          if(c?.keyOffset) {
            let t=c.keyOffset.find(t=>t.value===e.value);
            t&&(i+=t.offsetX,
            n+=t.offsetX)
          }return {
            row:t,
            col:i,
            code:e.keyCode,
            index:e.value,
            name:e.name,
            disabledLight:e.disabledLight
          }
        })
      }).flat().filter(e=>!e.disabledLight),
      f= {
        name:t,
        vendorId:n,
        productId:i,
        deviceMode:a===`USB`?0:1,
        layouts: {
          rows:s.length,
          cols:l+u,
          keys:d
        }
      };
      await CY(encodeURIComponent(y(JSON.stringify(f)))),
      r.value=!0,
      v(),
      hY(o.value),
      o.value=_Y(()=> {
        _()
      },
      100)
    }catch {
      r.value=!1
    }
  };
  b();
  let x=null,
  S=()=> {
    hY(o.value),
    o.value=0,
    EY()
  };
  return Hi(()=> {
    x=cQ.on(e=> {
      e.type===`start`?S():e.type===`finish`&&e.success&&b()
    })
  }),
  Ki(()=> {
    hY(o.value),
    EY(),
    x&&=(x(),
    null)
  }),
   {
    hasDownloadPlugin:r,
    handleDownload:i,
    modeList:d,
    mode:s,
    amplitude:c,
    handleModeChange:p,
    handleAmplitudeChange:m,
    bgList:f,
    backmode:l,
    backmodebrightness:u,
    handleBackmodeChange:h,
    handleBrightnessChange:g,
    setKeyboardLayout:b
  }
}var Yoe= {
  class:`w-full`
},
Xoe= {
  key:0,
  class:`flex w-full`
},
Zoe= {
  class:`w-full flex gap-5 auto-bg rounded-lg py-10 px-4`
},
Qoe= {
  class:`flex-1 flex flex-col gap-6`
},
$oe= {
  class:`flex flex-col gap-3`
},
ese= {
  class:`text-base font-semibold`
},
tse= {
  class:`flex flex-col gap-3`
},
nse= {
  class:`text-base font-semibold`
},
rse= {
  class:`flex items-center gap-4`
},
ise= {
  class:`text-sm font-medium min-w-[50px] text-center`
},
ase= {
  key:0,
  class:`flex-1 flex flex-col gap-6`
},
ose= {
  class:`flex flex-col gap-3`
},
sse= {
  class:`text-base font-semibold`
},
cse= {
  class:`flex flex-col gap-3`
},
lse= {
  class:`text-base font-semibold`
},
use= {
  class:`flex items-center gap-4`
},
dse= {
  class:`text-sm font-medium min-w-[50px] text-center`
},
fse= {
  key:1,
  class:`flex flex-col items-center justify-center gap-4 h-50`
},
pse= {
  class:`font-bold m-0`
},
mse= {
  class:`font-bold m-0`
},
hse= {
  class:`flex gap-2`
},
gse=V( {
  __name:`musicV1`,
  props: {
    keyboardConfig: {

    }
  },
  emits:[`update-key-list`],
  setup(e,
   {
    emit:t
  }) {
    let {
      hasDownloadPlugin:n,
      handleDownload:r,
      modeList:i,
      mode:a,
      amplitude:o,
      handleModeChange:s,
      handleAmplitudeChange:c,
      bgList:l,
      backmode:u,
      backmodebrightness:d,
      handleBackmodeChange:f,
      handleBrightnessChange:p,
      setKeyboardLayout:m
    }=D7(e,
    t);
    return(t,
    h)=> {
      let g=_A,
      _=lF,
      v=Ek;
      return H(),
      U(`div`,
      Yoe,
      [z(n)?(H(),
      U(`div`,
      Xoe,
      [W(`div`,
      Zoe,
      [W(`div`,
      Qoe,
      [W(`div`,
      $oe,
      [W(`h4`,
      ese,
      L(t.$t(`music_text1`)),
      1),
      G(g,
       {
        value:z(a),
        "onUpdate:value":[h[0]||=e=>on(a)?a.value=e:null,
        z(s)],
        options:z(i),
        class:`w-full`
      },
      null,
      8,
      [`value`,
      `options`,
      `onUpdate:value`])]),
      W(`div`,
      tse,
      [W(`h4`,
      nse,
      L(t.$t(`music_text3`)),
      1),
      W(`div`,
      rse,
      [G(_,
       {
        ref:`amplitudeRef`,
        value:z(o),
        "onUpdate:value":[h[1]||=e=>on(o)?o.value=e:null,
        z(c)],
        min:1,
        max:100,
        step:1,
        class:`flex-1`
      },
      null,
      8,
      [`value`,
      `onUpdate:value`]),
      W(`span`,
      ise,
      L(z(o)+`%`),
      1)])])]),
      e.keyboardConfig.musicConfig?.filterMusicMode?.length?bs(``,
      !0):(H(),
      U(`div`,
      ase,
      [W(`div`,
      ose,
      [W(`h4`,
      sse,
      L(t.$t(`music_text2`)),
      1),
      G(g,
       {
        value:z(u),
        "onUpdate:value":[h[2]||=e=>on(u)?u.value=e:null,
        z(f)],
        options:z(l),
        class:`w-full`
      },
      null,
      8,
      [`value`,
      `options`,
      `onUpdate:value`])]),
      W(`div`,
      cse,
      [W(`h4`,
      lse,
      L(t.$t(`music_text4`)),
      1),
      W(`div`,
      use,
      [G(_,
       {
        ref:`backmodebrightnessRef`,
        value:z(d),
        "onUpdate:value":[h[3]||=e=>on(d)?d.value=e:null,
        z(p)],
        min:1,
        max:100,
        step:1,
        class:`flex-1`
      },
      null,
      8,
      [`value`,
      `onUpdate:value`]),
      W(`span`,
      dse,
      L(z(d)+`%`),
      1)])])]))])])):(H(),
      U(`div`,
      fse,
      [W(`p`,
      pse,
      L(t.$t(`music_mode_error`)),
      1),
      W(`p`,
      mse,
      L(t.$t(`music_mode_error2`)),
      1),
      W(`div`,
      hse,
      [G(v,
       {
        type:`primary`,
        onClick:z(r)
      },
       {
        default:B(()=>[vs(L(t.$t(`music_btn`)),
        1)]),
        _:1
      },
      8,
      [`onClick`]),
      G(v,
       {
        type:`primary`,
        secondary:``,
        onClick:z(m)
      },
       {
        default:B(()=>[h[4]||=W(`i`,
         {
          class:`i-carbon:update-now mr-2`
        },
        null,
        -1),
        W(`span`,
        null,
        L(t.$t(`medium_text13`)),
        1)]),
        _:1
      },
      8,
      [`onClick`])])]))])
    }
  }
}),
_se=t( {
  default:()=>O7
}),
O7=gse,
vse=[[ {
  row:2,
  col:6
}],
[ {
  row:1,
  col:6
},
 {
  row:1,
  col:7
},
 {
  row:2,
  col:5
},
 {
  row:2,
  col:7
},
 {
  row:3,
  col:6
},
 {
  row:3,
  col:7
}],
[ {
  row:0,
  col:6
},
 {
  row:0,
  col:7
},
 {
  row:0,
  col:8
},
 {
  row:1,
  col:5
},
 {
  row:1,
  col:8
},
 {
  row:2,
  col:4
},
 {
  row:2,
  col:8
},
 {
  row:3,
  col:5
},
 {
  row:3,
  col:8
},
 {
  row:4,
  col:4
},
 {
  row:4,
  col:5
},
 {
  row:4,
  col:6
},
 {
  row:4,
  col:7
}],
[ {
  row:0,
  col:5
},
 {
  row:0,
  col:9
},
 {
  row:1,
  col:4
},
 {
  row:1,
  col:9
},
 {
  row:2,
  col:3
},
 {
  row:2,
  col:9
},
 {
  row:3,
  col:4
},
 {
  row:3,
  col:9
},
 {
  row:4,
  col:3
}],
[ {
  row:0,
  col:4
},
 {
  row:0,
  col:10
},
 {
  row:1,
  col:3
},
 {
  row:1,
  col:10
},
 {
  row:2,
  col:2
},
 {
  row:2,
  col:10
},
 {
  row:3,
  col:3
},
 {
  row:3,
  col:10
}],
[ {
  row:0,
  col:3
},
 {
  row:0,
  col:11
},
 {
  row:1,
  col:2
},
 {
  row:1,
  col:11
},
 {
  row:2,
  col:1
},
 {
  row:2,
  col:11
},
 {
  row:3,
  col:2
},
 {
  row:3,
  col:11
},
 {
  row:4,
  col:2
},
 {
  row:4,
  col:8
}],
[ {
  row:0,
  col:2
},
 {
  row:0,
  col:12
},
 {
  row:1,
  col:1
},
 {
  row:1,
  col:12
},
 {
  row:2,
  col:0
},
 {
  row:2,
  col:12
},
 {
  row:3,
  col:0
},
 {
  row:3,
  col:1
},
 {
  row:3,
  col:12
},
 {
  row:3,
  col:13
},
 {
  row:4,
  col:1
},
 {
  row:4,
  col:9
},
 {
  row:4,
  col:10
}],
[ {
  row:0,
  col:0
},
 {
  row:0,
  col:1
},
 {
  row:0,
  col:13
},
 {
  row:0,
  col:14
},
 {
  row:1,
  col:0
},
 {
  row:1,
  col:13
},
 {
  row:1,
  col:14
},
 {
  row:2,
  col:13
},
 {
  row:2,
  col:14
},
 {
  row:3,
  col:14
},
 {
  row:4,
  col:0
},
 {
  row:4,
  col:11
},
 {
  row:4,
  col:12
},
 {
  row:4,
  col:13
},
 {
  row:4,
  col:14
}]],
yse=[[ {
  row:2,
  col:8
}],
[ {
  row:1,
  col:8
},
 {
  row:1,
  col:9
},
 {
  row:2,
  col:7
},
 {
  row:2,
  col:9
},
 {
  row:3,
  col:7
},
 {
  row:3,
  col:8
}],
[ {
  row:0,
  col:7
},
 {
  row:0,
  col:8
},
 {
  row:0,
  col:9
},
 {
  row:1,
  col:7
},
 {
  row:1,
  col:10
},
 {
  row:2,
  col:6
},
 {
  row:2,
  col:10
},
 {
  row:3,
  col:6
},
 {
  row:3,
  col:9
},
 {
  row:4,
  col:7
},
 {
  row:4,
  col:8
},
 {
  row:4,
  col:9
}],
[ {
  row:0,
  col:6
},
 {
  row:1,
  col:6
},
 {
  row:1,
  col:11
},
 {
  row:2,
  col:5
},
 {
  row:2,
  col:11
},
 {
  row:3,
  col:5
},
 {
  row:3,
  col:10
},
 {
  row:4,
  col:10
},
 {
  row:4,
  col:6
}],
[ {
  row:1,
  col:5
},
 {
  row:2,
  col:4
},
 {
  row:3,
  col:4
},
 {
  row:4,
  col:5
},
 {
  row:5,
  col:4
},
 {
  row:5,
  col:5
},
 {
  row:5,
  col:6
},
 {
  row:5,
  col:7
},
 {
  row:5,
  col:8
},
 {
  row:5,
  col:9
},
 {
  row:0,
  col:10
},
 {
  row:1,
  col:12
},
 {
  row:2,
  col:12
},
 {
  row:3,
  col:11
},
 {
  row:4,
  col:11
},
 {
  row:5,
  col:10
}],
[ {
  row:0,
  col:5
},
 {
  row:1,
  col:4
},
 {
  row:2,
  col:3
},
 {
  row:3,
  col:3
},
 {
  row:4,
  col:4
},
 {
  row:0,
  col:11
},
 {
  row:1,
  col:13
},
 {
  row:2,
  col:13
},
 {
  row:3,
  col:12
},
 {
  row:5,
  col:3
},
 {
  row:5,
  col:11
}],
[ {
  row:0,
  col:4
},
 {
  row:1,
  col:3
},
 {
  row:2,
  col:2
},
 {
  row:3,
  col:2
},
 {
  row:3,
  col:13
},
 {
  row:4,
  col:3
},
 {
  row:0,
  col:12
},
 {
  row:0,
  col:13
},
 {
  row:5,
  col:12
},
 {
  row:5,
  col:13
},
 {
  row:4,
  col:12
},
 {
  row:4,
  col:13
}],
[ {
  row:0,
  col:3
},
 {
  row:1,
  col:2
},
 {
  row:2,
  col:1
},
 {
  row:3,
  col:1
},
 {
  row:3,
  col:14
},
 {
  row:4,
  col:2
},
 {
  row:4,
  col:14
},
 {
  row:0,
  col:14
},
 {
  row:1,
  col:14
},
 {
  row:2,
  col:14
},
 {
  row:5,
  col:2
},
 {
  row:5,
  col:14
}],
[ {
  row:0,
  col:2
},
 {
  row:1,
  col:1
},
 {
  row:2,
  col:0
},
 {
  row:3,
  col:0
},
 {
  row:3,
  col:15
},
 {
  row:4,
  col:0
},
 {
  row:4,
  col:1
},
 {
  row:5,
  col:1
},
 {
  row:0,
  col:15
},
 {
  row:1,
  col:15
},
 {
  row:2,
  col:15
},
 {
  row:4,
  col:15
},
 {
  row:5,
  col:15
}],
[ {
  row:0,
  col:0
},
 {
  row:1,
  col:0
},
 {
  row:0,
  col:1
},
 {
  row:0,
  col:16
},
 {
  row:1,
  col:16
},
 {
  row:2,
  col:16
},
 {
  row:3,
  col:16
},
 {
  row:4,
  col:16
},
 {
  row:5,
  col:0
},
 {
  row:5,
  col:16
}]],
bse=[[ {
  row:2,
  col:9
}],
[ {
  row:1,
  col:9
},
 {
  row:1,
  col:10
},
 {
  row:2,
  col:8
},
 {
  row:2,
  col:10
},
 {
  row:3,
  col:8
},
 {
  row:3,
  col:9
}],
[ {
  row:0,
  col:8
},
 {
  row:0,
  col:9
},
 {
  row:0,
  col:10
},
 {
  row:1,
  col:8
},
 {
  row:1,
  col:11
},
 {
  row:2,
  col:7
},
 {
  row:2,
  col:11
},
 {
  row:3,
  col:7
},
 {
  row:3,
  col:10
},
 {
  row:4,
  col:8
},
 {
  row:4,
  col:9
},
 {
  row:4,
  col:10
}],
[ {
  row:0,
  col:7
},
 {
  row:1,
  col:7
},
 {
  row:1,
  col:12
},
 {
  row:2,
  col:6
},
 {
  row:2,
  col:12
},
 {
  row:3,
  col:6
},
 {
  row:3,
  col:11
},
 {
  row:4,
  col:11
},
 {
  row:4,
  col:7
}],
[ {
  row:0,
  col:6
},
 {
  row:1,
  col:6
},
 {
  row:2,
  col:5
},
 {
  row:3,
  col:5
},
 {
  row:4,
  col:6
},
 {
  row:5,
  col:5
},
 {
  row:5,
  col:6
},
 {
  row:5,
  col:7
},
 {
  row:5,
  col:8
},
 {
  row:5,
  col:9
},
 {
  row:5,
  col:10
},
 {
  row:0,
  col:11
},
 {
  row:1,
  col:13
},
 {
  row:2,
  col:13
},
 {
  row:3,
  col:12
},
 {
  row:4,
  col:12
},
 {
  row:5,
  col:11
}],
[ {
  row:1,
  col:5
},
 {
  row:2,
  col:4
},
 {
  row:3,
  col:4
},
 {
  row:4,
  col:5
},
 {
  row:0,
  col:12
},
 {
  row:0,
  col:13
},
 {
  row:4,
  col:13
},
 {
  row:1,
  col:14
},
 {
  row:2,
  col:14
},
 {
  row:3,
  col:13
},
 {
  row:5,
  col:4
},
 {
  row:5,
  col:12
},
 {
  row:5,
  col:13
}],
[ {
  row:0,
  col:5
},
 {
  row:1,
  col:4
},
 {
  row:2,
  col:3
},
 {
  row:3,
  col:3
},
 {
  row:3,
  col:14
},
 {
  row:4,
  col:4
},
 {
  row:0,
  col:14
},
 {
  row:0,
  col:15
},
 {
  row:1,
  col:15
},
 {
  row:2,
  col:15
},
 {
  row:5,
  col:3
},
 {
  row:5,
  col:14
},
 {
  row:4,
  col:14
}],
[ {
  row:0,
  col:4
},
 {
  row:1,
  col:3
},
 {
  row:2,
  col:2
},
 {
  row:3,
  col:2
},
 {
  row:3,
  col:15
},
 {
  row:4,
  col:3
},
 {
  row:4,
  col:15
},
 {
  row:5,
  col:15
},
 {
  row:0,
  col:16
},
 {
  row:1,
  col:16
},
 {
  row:2,
  col:16
}],
[ {
  row:0,
  col:3
},
 {
  row:1,
  col:2
},
 {
  row:2,
  col:1
},
 {
  row:3,
  col:1
},
 {
  row:3,
  col:16
},
 {
  row:4,
  col:2
},
 {
  row:5,
  col:2
},
 {
  row:4,
  col:16
},
 {
  row:5,
  col:16
},
 {
  row:0,
  col:17
},
 {
  row:1,
  col:17
},
 {
  row:2,
  col:17
}],
[ {
  row:2,
  col:0
},
 {
  row:3,
  col:0
},
 {
  row:0,
  col:1
},
 {
  row:1,
  col:1
},
 {
  row:0,
  col:2
},
 {
  row:3,
  col:17
},
 {
  row:4,
  col:17
},
 {
  row:5,
  col:17
},
 {
  row:0,
  col:18
},
 {
  row:1,
  col:18
},
 {
  row:2,
  col:18
},
 {
  row:5,
  col:18
}],
[ {
  row:1,
  col:0
},
 {
  row:4,
  col:0
},
 {
  row:4,
  col:1
},
 {
  row:5,
  col:1
},
 {
  row:3,
  col:18
},
 {
  row:4,
  col:18
},
 {
  row:0,
  col:19
},
 {
  row:1,
  col:19
},
 {
  row:2,
  col:19
},
 {
  row:5,
  col:19
}],
[ {
  row:0,
  col:0
},
 {
  row:3,
  col:19
},
 {
  row:4,
  col:19
},
 {
  row:5,
  col:19
},
 {
  row:5,
  col:0
},
 {
  row:0,
  col:20
},
 {
  row:1,
  col:20
},
 {
  row:2,
  col:20
}]];
function xse(e) {
  if(e)return e===`ring_68`?vse:e===`ring_87`?yse:e===`ring_108`?bse:e
}function k7(e,
t,
n) {
  let r=[];
  for(let i=t;
  i<=n;
  i++)r.push( {
    row:e,
    col:i
  });
  return r
}var Sse= {
  left:[k7(4,
  0,
  2),
  k7(3,
  0,
  2),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  1)],
  middle:[k7(4,
  3,
  8),
  k7(3,
  4,
  10),
  k7(2,
  4,
  9),
  k7(1,
  6,
  8),
  k7(0,
  7,
  8)],
  right:[k7(4,
  9,
  14),
  k7(3,
  12,
  14),
  k7(2,
  12,
  14),
  k7(1,
  13,
  14),
  k7(0,
  14,
  14)]
},
Cse= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  10),
  k7(4,
  4,
  10),
  k7(3,
  4,
  9),
  k7(2,
  5,
  9),
  k7(1,
  6,
  9),
  k7(0,
  6,
  8)],
  right:[k7(5,
  11,
  14),
  k7(4,
  12,
  14),
  k7(3,
  12,
  14),
  k7(2,
  12,
  14),
  k7(1,
  13,
  14),
  k7(0,
  14,
  14)]
},
wse= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  12),
  k7(4,
  4,
  11),
  k7(3,
  4,
  10),
  k7(2,
  5,
  9),
  k7(1,
  6,
  9),
  k7(0,
  6,
  8)],
  right:[k7(5,
  13,
  16),
  k7(4,
  14,
  16),
  k7(3,
  13,
  16),
  k7(2,
  14,
  16),
  k7(1,
  15,
  16),
  k7(0,
  16,
  16)]
},
Tse= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  1),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  12),
  k7(4,
  3,
  11),
  k7(3,
  4,
  10),
  k7(2,
  5,
  9),
  k7(1,
  6,
  9),
  k7(0,
  6,
  8)],
  right:[k7(5,
  13,
  16),
  k7(4,
  13,
  16),
  k7(3,
  13,
  16),
  k7(2,
  14,
  16),
  k7(1,
  15,
  16),
  k7(0,
  16,
  16)]
},
Ese= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  12),
  k7(4,
  4,
  11),
  k7(3,
  4,
  10),
  k7(2,
  5,
  9),
  k7(1,
  6,
  9),
  k7(0,
  6,
  8)],
  right:[k7(5,
  13,
  16),
  k7(4,
  14,
  16),
  k7(3,
  14,
  16),
  k7(2,
  14,
  16),
  k7(1,
  15,
  16),
  k7(0,
  16,
  16)]
},
Dse= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  14),
  k7(4,
  4,
  12),
  k7(3,
  4,
  11),
  k7(2,
  5,
  11),
  k7(1,
  6,
  10),
  k7(0,
  6,
  8)],
  right:[k7(5,
  15,
  17),
  k7(4,
  14,
  17),
  k7(3,
  14,
  17),
  k7(2,
  16,
  17),
  k7(1,
  17,
  17),
  k7(0,
  17,
  17)]
},
Ose= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  14),
  k7(4,
  4,
  13),
  k7(3,
  4,
  12),
  k7(2,
  5,
  12),
  k7(1,
  8,
  11),
  k7(0,
  9,
  9)],
  right:[k7(5,
  15,
  18),
  k7(4,
  15,
  18),
  k7(3,
  15,
  18),
  k7(2,
  17,
  18),
  k7(1,
  18,
  18),
  k7(0,
  18,
  18)]
},
kse= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  14),
  k7(4,
  4,
  13),
  k7(3,
  4,
  12),
  k7(2,
  5,
  12),
  k7(1,
  8,
  11),
  k7(0,
  9,
  9)],
  right:[k7(5,
  15,
  18),
  k7(4,
  15,
  18),
  k7(3,
  15,
  18),
  k7(2,
  17,
  18),
  k7(1,
  18,
  18),
  k7(0,
  18,
  18)]
},
Ase= {
  left:[k7(5,
  0,
  2),
  k7(4,
  0,
  2),
  k7(3,
  0,
  1),
  k7(2,
  0,
  1),
  k7(1,
  0,
  1),
  k7(0,
  0,
  0)],
  middle:[k7(5,
  3,
  14),
  k7(4,
  4,
  13),
  k7(3,
  4,
  12),
  k7(2,
  5,
  12),
  k7(1,
  8,
  11),
  k7(0,
  9,
  9)],
  right:[k7(5,
  13,
  18),
  k7(4,
  15,
  18),
  k7(3,
  15,
  18),
  k7(2,
  17,
  18),
  k7(1,
  18,
  18),
  k7(0,
  17,
  17)]
};
function jse(e) {
  if(e)return e===`volcano_64`?Sse:e===`volcano_80_iso`?Cse:e===`volcano_84_iso`?wse:e===`volcano_86_iso`?Tse:e===`volcano_87`?Ese:e===`volcano_96`?Dse:e===`volcano_98`?Ose:e===`volcano_101_iso`?Ase:e===`volcano_102`?kse:e
}var A7=5,
j7=.01,
M7=.3,
N7=.008,
P7=null,
F7=null,
I7=null,
L7=null,
R7=null,
z7=j7,
B7= {
  low:j7,
  mid:j7,
  high:j7
},
V7=!1;
function Mse() {
  P7=null,
  F7=null,
  I7=null,
  L7=null,
  R7=null,
  z7=j7,
  B7= {
    low:j7,
    mid:j7,
    high:j7
  },
  V7=!1
}function Nse(e) {
  z7=e>z7?z7*.7+e*M7:z7*.992+e*N7,
  z7=Math.max(z7,
  j7);
  let t=e/z7;
  return Math.min(1e3,
  Math.round(t*1e3))
}function H7() {
  W7()
}async function U7() {
  if(!V7) {
    if(!navigator.mediaDevices?.getDisplayMedia)throw Error(`当前浏览器不支持 getDisplayMedia`);
    try {
      let e=await navigator.mediaDevices.getDisplayMedia( {
        video: {
          displaySurface:`monitor`
        },
        audio: {
          echoCancellation:!1,
          noiseSuppression:!1,
          autoGainControl:!1
        }
      }),
      t=e.getAudioTracks();
      if(t.length===0)throw e.getTracks().forEach(e=>e.stop()),
      Error(`未获取到音频轨道，请勾选分享系统音频或标签页音频`);
      e.getVideoTracks().forEach(e=>e.stop()),
      P7=new AudioContext,
      F7=P7.createAnalyser(),
      F7.fftSize=2048,
      F7.smoothingTimeConstant=.75,
      P7.createMediaStreamSource(e).connect(F7),
      I7=e,
      L7=new Float32Array(F7.fftSize),
      R7=new Uint8Array(F7.frequencyBinCount),
      z7=j7,
      V7=!0,
      t.forEach(e=> {
        e.addEventListener(`ended`,
        H7)
      })
    }catch(e) {
      throw e instanceof Error&&e.name===`NotAllowedError`?Error(`取消了授权`):e
    }
  }
}function W7() {
  (V7||I7||P7)&&(I7?.getAudioTracks().forEach(e=> {
    e.removeEventListener(`ended`,
    H7),
    e.stop()
  }),
  I7?.getVideoTracks().forEach(e=>e.stop()),
  I7=null,
  P7?.state!==`closed`&&P7?.close(),
  Mse())
}function G7() {
  return V7
}function K7() {
  if(!V7||!F7||!L7)return 0;
  F7.getFloatTimeDomainData(L7);
  let e=0,
  t=0;
  for(let n=0;
  n<L7.length;
  n++) {
    let r=Math.abs(L7[n]??0);
    e=Math.max(e,
    r),
    t+=r*r
  }let n=Math.sqrt(t/L7.length),
  r=Nse(e*.6+n*.4);
  return r<=A7?0:r
}function q7(e,
t,
n) {
  if(!P7||!F7)return 0;
  let r=P7.sampleRate/F7.fftSize,
  i=Math.max(0,
  Math.floor(t/r)),
  a=Math.min(e.length-1,
  Math.ceil(n/r));
  if(a<i)return 0;
  let o=0;
  for(let t=i;
  t<=a;
  t++) {
    let n=(e[t]??0)/255;
    o+=n*n
  }return Math.sqrt(o/(a-i+1))
}function J7(e,
t) {
  let n=B7[t],
  r=e>n?M7:N7,
  i=Math.max(n*(1-r)+e*r,
  j7);
  B7[t]=i;
  let a=Math.min(1e3,
  Math.round(e/i*1e3));
  return a<=A7?0:a
}function Pse() {
  return!V7||!F7||!R7? {
    low:0,
    mid:0,
    high:0
  }:(F7.getByteFrequencyData(R7),
   {
    low:J7(q7(R7,
    20,
    250),
    `low`),
    mid:J7(q7(R7,
    250,
    4e3),
    `mid`),
    high:J7(q7(R7,
    4e3,
    2e4),
    `high`)
  })
}function Y7(e,
t) {
  let {
    sendReport:n
  }=rY(),
   {
    keyList:r
  }=tX(),
   {
    currentDeviceId:i
  }=HY(),
  a=$I(i,
   {

  }),
  o=R(!1),
  s=()=> {
    EV(`https://config.driveall.cn/music/v2/Music.exe`)
  },
  c=async()=> {
    try {
      await U7(),
      o.value=!0,
      m.value||I()
    }catch(e) {
      console.error(`系统音频采集失败:`,
      e),
      $message.error(e instanceof Error?e.message:`系统音频采集失败`)
    }
  },
  l=K(()=>e.keyboardConfig.routesName?.includes(`led`)&&e.keyboardConfig.ledConfig?.isShowVoiceMode||!1),
  u=R(a.value.ledData?.mode||1),
  d=K(()=>[ {
    name:$(`gif_tft_text4`),
    value:1
  },
   {
    name:$(`gif_tft_text5`),
    value:3
  },
   {
    name:$(`gif_tft_text6`),
    value:2
  }]),
  f=EI(async e=> {
    ue(),
    await new Promise(e=>vY(e,
    100)),
    u.value=e.value,
    await n(`setDotMatrixMode`,
    void 0,
     {
      mode:e.value,
      dotMatrixMode:3
    }),
    await new Promise(e=>vY(e,
    100)),
    I()
  },
  300),
  p=$I(`musicV2Config`,
   {
    mode:13,
    amplitude:50,
    backmode:0,
    backmodebrightness:100
  }),
  m=R(0),
  h=R(p.value.mode||13),
  g=R(p.value.amplitude||50),
  _=R(!1),
  v=R(1e3),
  y=R(p.value.backmode||0),
  b=R(p.value.backmodebrightness||100),
  x=R(0),
  S=R(0),
  C=R(5),
  w=R(0),
  T=R(0),
  E=R(null),
  D=R(!1),
  O=R(null),
  k=R(!1),
  ee=null,
  A=K(()=> {
    let t=[ {
      label:$(`music_mode_text3`),
      value:13
    },
     {
      label:$(`music_mode_text20`),
      value:22
    },
     {
      label:$(`music_mode_text12`),
      value:14
    },
     {
      label:$(`music_mode_text13`),
      value:15
    },
     {
      label:$(`music_mode_text14`),
      value:16
    },
     {
      label:$(`music_mode_text16`),
      value:18
    },
     {
      label:$(`music_mode_text17`),
      value:19
    },
     {
      label:$(`music_mode_text15`),
      value:17
    },
     {
      label:$(`music_mode_text18`),
      value:20
    },
     {
      label:$(`music_mode_text19`),
      value:21
    },
     {
      label:$(`music_mode_text4`),
      value:4
    },
     {
      label:$(`music_mode_text21`),
      value:100
    }];
    return e.keyboardConfig.musicConfig?.filterMusicMode?.length&&(t=t.filter(t=>e.keyboardConfig.musicConfig?.filterMusicMode?.includes(t.value)),
    h.value=t[0].value),
    t
  }),
  te=K(()=>[ {
    label:$(`music_bg_text1`),
    value:0
  },
   {
    label:$(`music_bg_text2`),
    value:6
  },
   {
    label:$(`music_bg_text3`),
    value:7
  },
   {
    label:$(`music_bg_text4`),
    value:8
  },
   {
    label:$(`music_bg_text5`),
    value:9
  },
   {
    label:$(`music_bg_text6`),
    value:10
  },
   {
    label:$(`music_bg_text7`),
    value:11
  },
   {
    label:$(`music_bg_text8`),
    value:1
  },
   {
    label:$(`music_bg_text9`),
    value:2
  },
   {
    label:$(`music_bg_text10`),
    value:4
  },
   {
    label:$(`music_bg_text11`),
    value:5
  }]),
  j=e=> {
    h.value=e,
    p.value.mode=e
  },
  M=e=> {
    g.value=e,
    p.value.amplitude=e
  };
  l0(ii(`amplitudeRef`),
  g,
   {
    min:1,
    max:100
  });
  let N=e=> {
    y.value=e,
    p.value.backmode=e
  },
  ne=e=> {
    b.value=e,
    p.value.backmodebrightness=e
  };
  l0(ii(`backmodebrightnessRef`),
  b,
   {
    min:10,
    max:100
  });
  let P=K(()=> {
    let {
      keyList:t,
      musicConfig:n
    }=e.keyboardConfig;
    return t.reduce((e,
    t)=>Math.max(e,
    t.length),
    0)+(n?.maxColOffset||0)
  }),
  F=K(()=> {
    let {
      keyList:t
    }=e.keyboardConfig;
    return t.length
  }),
  re=R(0),
  ie=R(0),
  ae=R(.005),
  oe=R(0),
  se=R(0),
  ce=K(()=> {
    let {
      keyList:t
    }=e.keyboardConfig,
    n=t[le.value].length;
    return n%2==0?n/2-1:Math.floor(n/2)
  }),
  le=K(()=> {
    let {
      keyList:t
    }=e.keyboardConfig;
    return t.length%2==0?t.length/2-1:Math.floor(t.length/2)
  }),
  I=()=> {
    m.value=_Y(()=> {
      if(h.value===100)Le();
      else {
        Ie.value=!1,
        pe();
        try {
          if(!o.value)return;
          he()
        }catch(e) {
          console.log(`绘画矩阵失败:`,
          e)
        }
      }
    },
    50)
  };
  I();
  let ue=()=> {
    m.value&&=(hY(m.value),
    0)
  },
  de=()=> {
    k.value=!0,
    ue(),
    Ie.value=!1,
    O.value=null,
    D.value=!1,
    EY()
  },
  fe=()=> {
    k.value=!1,
    I()
  },
  pe=async()=> {
    if(!m.value||k.value)return;
    if(_.value) {
      S.value=0,
      x.value=v.value/1e3,
      re.value>=360&&(re.value=0),
      re.value+=10,
      o.value=!0;
      return
    }let e=e=> {
      e>0?(S.value=0,
      x.value=Math.min(1,
      e/1e3)):(S.value++,
      S.value>=C.value&&(x.value=0)),
      re.value>=360&&(re.value=0),
      re.value+=10
    };
    if(G7()) {
      e(K7()),
      o.value=!0;
      return
    }try {
      let t=await DY();
      typeof t?.amplitude==`number`&&e(t.amplitude||0),
      o.value=!0
    }catch {
      ue(),
      o.value=!1
    }
  },
  me=async t=> {
    if(!k.value) {
      if(ge(t),
      D.value) {
        O.value= {
          keysRgb:t
        };
        return
      }D.value=!0;
      try {
        let {
          keyList:r,
          musicConfig:i,
          ledConfig:a
        }=e.keyboardConfig,
        o=r.map((e,
        t)=> {
          let n=0;
          return e.map((e,
          r)=> {
            let a=r+n;
            if(i?.keyOffset) {
              let t=i.keyOffset.find(t=>t.value===e.value);
              t&&(a+=t.offsetX,
              n+=t.offsetX)
            }return {
              row:t,
              col:a,
              keyCode:e.keyCode,
              value:e.value,
              name:e.name,
              disabledLight:e.disabledLight
            }
          })
        }).flat().filter(e=>!e.disabledLight),
        s=Array(o.length*4).fill(0);
        for(let e=0;
        e<o.length;
        e++) {
          let n=e*4;
          s[n]=o[e].value,
          s[n+1]=t[o[e].row][o[e].col].r,
          s[n+2]=t[o[e].row][o[e].col].g,
          s[n+3]=t[o[e].row][o[e].col].b
        }let c=0;
        if(a) {
          let e=Math.max(a.rows,
          a.cols);
          c=Math.ceil(x.value*1e3/(1e3/e))
        }await n(`setMusicData`,
        void 0,
        s,
        c)
      }catch(e) {
        console.error(`发送音乐律动数据失败`,
        e)
      }finally {
        if(D.value=!1,
        O.value) {
          let e=O.value;
          O.value=null,
          me(e.keysRgb)
        }
      }
    }
  },
  he=()=> {
    let e=x.value>0,
    t=Array.from( {
      length:F.value
    },
    ()=>Array.from( {
      length:P.value+1
    },
    ()=>( {
      r:0,
      g:0,
      b:0
    })));
    if(E.value=t,
    y.value&&_e(t,
    y.value),
    !e) {
      me(t);
      return
    }switch(h.value) {
      case 1:Fe(t,
      h.value);
      break;
      case 4:Fe(t,
      h.value);
      break;
      case 13:Se(t);
      break;
      case 14:Ce(t);
      break;
      case 15:Ee(t);
      break;
      case 16:De(t);
      break;
      case 17:je(t);
      break;
      case 18:Oe(t);
      break;
      case 19:Ae(t);
      break;
      case 20:Ne(t);
      break;
      case 21:Pe(t);
      break;
      case 22:L(t)
    }
  },
  ge=n=> {
    if(!r.value||r.value.length===0)return;
    let {
      keyList:i,
      musicConfig:a
    }=e.keyboardConfig,
    o=JSON.parse(JSON.stringify(r.value)),
    s=new Map(o.flat().map(e=>[e.value,
    e]));
    i.forEach((e,
    t)=> {
      let r=0;
      e.forEach((e,
      i)=> {
        let o=s.get(e.value);
        if(!o)return;
        let c=i+r;
        if(a?.keyOffset) {
          let t=a.keyOffset.find(t=>t.value===e.value);
          t&&(c+=t.offsetX,
          r+=t.offsetX)
        }if(delete o.userKey,
        o.name=``,
        delete o.text,
        e.disabledLight) {
          delete o.bgColor;
          return
        }if(n[t]&&n[t][c]) {
          let e=n[t][c];
          o.bgColor=`rgba(${e.r}, ${e.g}, ${e.b}, 1)`
        }
      })
    }),
    t(`update-key-list`,
    o)
  },
  _e=(e,
  t,
  n)=> {
    switch(t) {
      case 6:ve(e,
       {
        r:255,
        g:255,
        b:255
      });
      break;
      case 7:ve(e,
       {
        r:255,
        g:0,
        b:0
      });
      break;
      case 8:ve(e,
       {
        r:255,
        g:64,
        b:0
      });
      break;
      case 9:ve(e,
       {
        r:255,
        g:255,
        b:0
      });
      break;
      case 10:ve(e,
       {
        r:0,
        g:0,
        b:255
      });
      break;
      case 11:ve(e,
       {
        r:0,
        g:255,
        b:0
      });
      break;
      case 1:xe(e,
      [ {
        r:0,
        g:255,
        b:0
      },
       {
        r:255,
        g:255,
        b:0
      },
       {
        r:255,
        g:0,
        b:0
      }]);
      break;
      case 2:xe(e,
      [ {
        r:255,
        g:0,
        b:255
      },
       {
        r:0,
        g:0,
        b:255
      },
       {
        r:0,
        g:255,
        b:255
      },
       {
        r:0,
        g:255,
        b:0
      },
       {
        r:255,
        g:255,
        b:0
      },
       {
        r:255,
        g:0,
        b:0
      }]);
      break;
      case 4:ye(e,
      n