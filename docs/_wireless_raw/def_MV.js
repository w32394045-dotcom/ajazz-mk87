MV=e=> {
  let t=e.length,n=new Uint8Array(256).fill(255);
  n[0]=t;
  for(let r=0;
  r<t-1;
  r++)n[r+1]=Math.min(e[r]*5,255);
  return n[t]=0,n
}