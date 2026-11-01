ible)continue;
let {
  transform:r
}=o,s=Math.max(1,r.width*t),c=Math.max(1,r.height*n),l=o.amplitude/100,u=A9(i.amplitude*l,0,1.5);
e.save(),e.translate(r.x*t,r.y*n),e.beginPath(),e.rect(-s/2,-c/2,s,c),e.clip();
let d=o.colorMode===`single`?o.color:Ide(e,o,s,c,a);
e.fillStyle=d,e.strokeStyle=d,o.type===`bar`?Rde(e,s,c,o.direction,i,l,o.count??36,o.spacing??4):o.type===`line`?zde(e,s,c,o.direction,i,l,o.thickness??12,a):o.type===`circle`?(e.beginPath(),e.ellipse(0,0,s*u/2,c*u/2,0,0,Math.PI*2),e.fill()):Lde(e,s,c,o.direction,u),e.restore()
}
}function Vde(e) {
  let t=e.length/4;
  if(!t)return {
    r:0,g:0,b:0
  };
  let n=0,r=0,i=0;
  for(let t=0;
  t<e.length;
  t+=4)n+=e[t]??0,r+=e[t+1]??0,i+=e[t+2]??0;
  return {
    r:Math.round(n/t),g:Math.round(r/t),b:Math.round(i/t)
  }
}function M9(e,t,n) {
  let r=e.keyList[t],i=r?.[n];
  if(!i)return n;
  let a=0;
  for(let t=0;
  t<n;
  t++)a+=e.musicConfig?.keyOffset?.find(e=>e.value===r[t]?.value)?.offsetX??0;
  return n+a+(e.musicConfig?.keyOffset?.find(e=>e.value===i.value)?.offsetX??0)
}function Hde(e) {
  let t=e.keyList.reduce((e,t)=>Math.max(e,t.length),0)+(e.musicConfig?.maxColOffset??0)+1;
  return Array.from( {
    length:e.keyList.length
  },()=>Array.from( {
    length:t
  },()=>( {
    r:0,g:0,b:0
  })))
}function Ude(e,t,n,r) {
  let i=r.getBoundingClientRect(),a=t.width/n.width,o=t.height/n.height,s=Math.max(0,(i.left-n.left)*a),c=Math.max(0,(i.top-n.top)*o),l=Math.min(t.width,(i.right-n.left)*a),u=Math.min(t.height,(i.bottom-n.top)*o);
  if(s>=l||c>=u)return {
    r:0,g:0,b:0
  };
  let d=Math.floor(s),f=Math.floor(c),p=Math.max(1,Math.min(t.width-d,Math.ceil(l-s))),m=Math.max(1,Math.min(t.height-f,Math.ceil(u-c)));
  return Vde(e.getImageData(d,f,p,m).data)
}function Wde(e) {
  let {
    sendReport:t
  }=rY(), {
    keyList:n
  }=tX(),r=0,i=!1,a=null;
  function o() {
    let t=e.getCanvas(),n=dn(e.keyboardConfig),r=e.getKeyElements();
    if(!t||!r.length)return null;
    let i=t.getContext(`2d`, {
      willReadFrequently:!0
    });
    if(!