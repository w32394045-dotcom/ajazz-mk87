);
break;
case 5:be(e)
}
},
ve=(e,
t)=> {
  let n=Math.round(b.value*(255/100));
  e.forEach(e=> {
    let r=Math.round(n*t.r/256),
    i=Math.round(n*t.g/256),
    a=Math.round(n*t.b/256);
    for(let t=0;
    t<e.length;
    t++)e[t]= {
      r,
      g:i,
      b:a
    }
  })
},
ye=(e,
t)=> {
  let n=Math.round(b.value*(255/100));
  for(let r=0;
  r<F.value;
  r++)for(let i=0;
  i<P.value;
  i++)if(e[r]&&e[r][i]!==void 0) {
    let a=Math.atan2(r-le.value,
    i-ce.value),
    o=re.value+(180+180/Math.PI*a)%360;
    o<0&&(o+=360),
    o>=360&&(o-=360);
    let s= {
      hue:o,
      saturation:1,
      value:t||n/255
    },
    c=kV(s.hue,
    s.saturation,
    s.value);
    e[r][i]= {
      r:c.r,
      g:c.g,
      b:c.b
    }
  }
},
be=e=> {
  let t=Math.round(b.value*(255/100)),
  n= {
    hue:Math.round(re.value)%360,
    saturation:1,
    value:t/255
  },
  r=kV(n.hue,
  n.saturation,
  n.value);
  for(let t=0;
  t<F.value;
  t++)for(let n=0;
  n<P.value;
  n++)e[t]&&e[t][n]!==void 0&&(e[t][n]= {
    r:r.r,
    g:r.g,
    b:r.b
  })
},
xe=(e,
t)=> {
  if(!t||!Array.isArray(t)||t.length===0) {
    console.warn(`颜色数组不能为空`);
    return
  }let n=Math.round(b.value*(255/100)),
  r=t.length,
  i=Math.floor(F.value/r),
  a=F.value%r,
  o=0;
  for(let s=0;
  s<r;
  s++) {
    let r=t[s],
    c=i+ +(s<a),
    l=Math.round(n*r.r/256),
    u=Math.round(n*r.g/256),
    d=Math.round(n*r.b/256);
    for(let t=0;
    t<c&&o<F.value;
    t++) {
      for(let t=0;
      t<P.value;
      t++)e[o]&&e[o][t]!==void 0&&(e[o][t]= {
        r:l,
        g:u,
        b:d
      });
      o++
    }
  }
},
Se=t=> {
  let n=xse(e.keyboardConfig.musicConfig?.ringKeyPositions),
  r=[],
  i=null,
  a=0;
  if(n&&n.length>1)i=n[0][0]??null,
  n.slice(1).forEach(e=> {
    r.push(e.map(e=>( {
      ...e
    })))
  }),
  a=r.length;
  else {
    let e=0;
    for(let t=0;
    t<F.value;
    t++)for(let n=0;
    n<P.value;
    n++) {
      let r=n-ce.value,
      i=t-le.value,
      a=Math.sqrt(r*r+i*i);
      a>e&&(e=a)
    }a=Math.max(4,
    Math.ceil(e));
    for(let e=0;
    e<a;
    e++)r[e]=[];
    for(let t=0;
    t<F.value;
    t++)for(let n=0;
    n<P.value;
    n++) {
      let i=n-ce.value+0,
      o=t-le.value,
      s=Math.sqrt(i*i+o*o),
      c=Math.floor(s/e*(a-.01));
      c===0&&Math.abs(i)<.5&&Math.abs(o)<.5||c>=0&&c<a&&r[c].push( {
        row:t,
        col:n+0
      })
    }if(r[1]&&r[1].length>2&&r[2]) {
      let e=r[1].shift(),
      t=null;
      F.value<6?(t=r[1][4],
      r[1].splice(4,
      1)):t=r[1].pop(),
      e&&r[2].push(e),
      t&&r[2].push(t)
    }
  }ie.value+=ae.value,
  ie.value>=1&&(ie.value=0),
  oe.value+=.005,
  oe.value>=1&&(oe.value=0);
  let o=[];
  for(let e=0;
  e<a;
  e++)o[e]=(ie.value-e/a+1)%1;
  let s=Math.min(x.value,
  1),
  c=Math.max(.01,
  .06-s*.05),
  l;
  l=s<c?0:Math.max(1,
  Math.min(a,
  Math.round(x.value*a)));
  let u=g.value/100;
  se.value+=(l-se.value)*u;
  let d=Math.round(se.value),
  f=i?? {
    row:le.value,
    col:ce.value
  };
  if(f.col>=0&&f.col<P.value&&f.row>=0&&f.row<F.value) {
    let e=kV(oe.value*360%360,
    1,
    1);
    t[f.row][f.col]=e
  }for(let e=0;
  e<d;
  e++) {
    if(!r[e]?.length)continue;
    let n=kV((o[e]+oe.value)*360%360,
    1,
    1);
    for(let i of r[e]) {
      let {
        row:e,
        col:r
      }=i;
      r>=0&&r<P.value&&e>=0&&e<F.value&&(t[e][r]=n)
    }
  }me(t)
},
L=t=> {
  let {
    keyList:n
  }=e.keyboardConfig,
  r=n[le.value].length,
  i=Math.floor(r/4),
  a=i,
  o=r-i-1,
  s=le.value,
  c=le.value,
  l=0;
  for(let e=0;
  e<F.value;
  e++)for(let t=0;
  t<P.value;
  t++) {
    let n=t-a,
    r=e-s,
    i=Math.sqrt(n*n+r*r),
    u=t-o,
    d=e-c,
    f=Math.sqrt(u*u+d*d),
    p=Math.min(i,
    f);
    p>l&&(l=p)
  }let u=[],
  d=[],
  f=n.flat().length;
  F.value>=7?(u=[[ {
    x:3,
    y:3
  }],
  [ {
    x:3,
    y:2
  },
   {
    x:4,
    y:2
  },
   {
    x:2,
    y:3
  },
   {
    x:4,
    y:3
  },
   {
    x:2,
    y:4
  },
   {
    x:3,
    y:4
  }],
  [ {
    x:2,
    y:1
  },
   {
    x:3,
    y:1
  },
   {
    x:4,
    y:1
  },
   {
    x:5,
    y:1
  },
   {
    x:1,
    y:2
  },
   {
    x:5,
    y:2
  },
   {
    x:1,
    y:3
  },
   {
    x:5,
    y:3
  },
   {
    x:1,
    y:5
  },
   {
    x:2,
    y:5
  },
   {
    x:3,
    y:5
  },
   {
    x:4,
    y:5
  },
   {
    x:5,
    y:5
  },
   {
    x:2,
    y:2
  },
   {
    x:4,
    y:4
  }],
  [ {
    x:0,
    y:0
  },
   {
    x:1,
    y:0
  },
   {
    x:2,
    y:0
  },
   {
    x:3,
    y:0
  },
   {
    x:4,
    y:0
  },
   {
    x:6,
    y:1
  },
   {
    x:0,
    y:2
  },
   {
    x:6,
    y:2
  },
   {
    x:0,
    y:3
  },
   {
    x:6,
    y:3
  },
   {
    x:0,
    y:4
  },
   {
    x:6,
    y:4
  },
   {
    x:0,
    y:5
  },
   {
    x:6,
    y:5
  },
   {
    x:1,
    y:6
  },
   {
    x:2,
    y:6
  },
   {
    x:3,
    y:6
  },
   {
    x:4,
    y:6
  },
   {
    x:5,
    y:6
  },
   {
    x:5,
    y:4
  },
   {
    x:1,
    y:4
  },
   {
    x:1,
    y:1
  }],
  [ {
    x:5,
    y:0
  },
   {
    x:7,
    y:1
  },
   {
    x:7,
    y:2
  },
   {
    x:7,
    y:3
  },
   {
    x:7,
    y:4
  },
   {
    x:7,
    y:5
  },
   {
    x:0,
    y:6
  },
   {
    x:6,
    y:6
  }],
  [ {
    x:6,
    y:0
  },
   {
    x:7,
    y:6
  },
   {
    x:0,
    y:1
  }]],
  d=[[ {
    x:11,
    y:3
  }],
  [ {
    x:11,
    y:2
  },
   {
    x:12,
    y:2
  },
   {
    x:10,
    y:3
  },
   {
    x:12,
    y:3
  },
   {
    x:10,
    y:4
  },
   {
    x:11,
    y:4
  }],
  [ {
    x:10,
    y:1
  },
   {
    x:11,
    y:1
  },
   {
    x:12,
    y:1
  },
   {
    x:13,
    y:1
  },
   {
    x:9,
    y:2
  },
   {
    x:13,
    y:2
  },
   {
    x:9,
    y:3
  },
   {
    x:13,
    y:3
  },
   {
    x:9,
    y:5
  },
   {
    x:10,
    y:5
  },
   {
    x:11,
    y:5
  },
   {
    x:12,
    y:5
  },
   {
    x:13,
    y:5
  },
   {
    x:10,
    y:2
  },
   {
    x:12,
    y:4
  }],
  [ {
    x:8,
    y:0
  },
   {
    x:9,
    y:0
  },
   {
    x:10,
    y:0
  },
   {
    x:11,
    y:0
  },
   {
    x:12,
    y:0
  },
   {
    x:14,
    y:1
  },
   {
    x:8,
    y:2
  },
   {
    x:14,
    y:2
  },
   {
    x:8,
    y:3
  },
   {
    x:14,
    y:3
  },
   {
    x:8,
    y:4
  },
   {
    x:14,
    y:4
  },
   {
    x:8,
    y:5
  },
   {
    x:14,
    y:5
  },
   {
    x:9,
    y:6
  },
   {
    x:10,
    y:6
  },
   {
    x:11,
    y:6
  },
   {
    x:12,
    y:6
  },
   {
    x:13,
    y:6
  },
   {
    x:13,
    y:4
  },
   {
    x:9,
    y:4
  },
   {
    x:9,
    y:1
  }],
  [ {
    x:7,
    y:0
  },
   {
    x:13,
    y:0
  },
   {
    x:15,
    y:1
  },
   {
    x:15,
    y:2
  },
   {
    x:15,
    y:3
  },
   {
    x:15,
    y:4
  },
   {
    x:15,
    y:5
  },
   {
    x:8,
    y:6
  },
   {
    x:14,
    y:6
  }],
  [ {
    x:14,
    y:0
  },
   {
    x:15,
    y: