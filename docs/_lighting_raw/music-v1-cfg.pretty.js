eyList:n
}=tX(),r=R(!1),i=()=> {
  EV(`https://config.driveall.cn/music/v2/Music.exe`)
},a=$I(`musicV1Config`, {
  mode:1,amplitude:30,backmode:0,backmodebrightness:100
}),o=R(0),s=R(a.value.mode||1),c=R(a.value.amplitude||30),l=R(a.value.backmode||0),u=R(a.value.backmodebrightness||100),d=K(()=> {
  let t=[ {
    label:$(`music_mode_text1`),value:1
  }, {
    label:$(`music_mode_text2`),value:2
  }, {
    label:$(`music_mode_text3`),value:13
  }, {
    label:$(`music_mode_text4`),value:4
  }, {
    label:$(`music_mode_text5`),value:5
  }, {
    label:$(`music_mode_text6`),value:6
  }, {
    label:$(`music_mode_text7`),value:7
  }, {
    label:$(`music_mode_text8`),value:8
  }, {
    label:$(`music_mode_text9`),value:9
  }, {
    label:$(`music_mode_text10`),value:11
  }, {
    label:$(`music_mode_text11`),value:10
  }, {
    label:$(`music_mode_text21`),value:100
  }];
  return e.keyboardConfig.musicConfig?.filterMusicMode?.length&&(t=t.filter(t=>e.keyboardConfig.musicConfig?.filterMusicMode?.includes(t.value)),s.value=t[0].value),t
}),f=K(()=>[ {
  label:$(`music_bg_text1`),value:0
}, {
  label:$(`music_bg_text2`),value:6
}, {
  label:$(`music_bg_text3`),value:7
}, {
  label:$(`music_bg_text4`),value:8
}, {
  label:$(`music_bg_text5`),value:9
}, {
  label:$(`music_bg_text6`),value:10
}, {
  label:$(`music_bg_text7`),value:11
}, {
  label:$(`music_bg_text8`),value:1
}, {
  label:$(`music_bg_text9`),value:2
}, {
  label:$(`music_bg_text10`),value:4
}, {
  label:$(`music_bg_text11`),value:5
}]),p=e=> {
  s.value=e,a.value.mode=e,v()
},m=e=> {
  c.value=e,a.value.amplitude=e,v()
};
l0(ii(`amplitudeRef`),c, {
  min:1,max:100,onChange:()=> {
    v()
  }
});
let h=e=> {
  l.value=e,a.value.backmode=e,v()
},g=e=> {
  u.value=e,a.value.backmodebrightness=e,v()
};
l0(ii(`backmodebrightnessRef`),u, {
  min:1,max:100,onChange:()=> {
    v()
  }
});
let _=async()=> {
  try {
    let e=await wY();
    if(r.value=!0,e) {
      let r=JSON.parse(JSON.stringify(n.value));
      r.forEach(t=> {
        t.forEach(t=> {
          let n=e.keys.find(e=>e.keyIndex===t.value);
          if(delete t.userKey,t.name=``,delete t.text,t.disabledLight) {
            delete t.bgColor;
            return
          }t.bgColor=n