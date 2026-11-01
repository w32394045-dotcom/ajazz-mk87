MX=(e,t,n)=> {
  let r=e.sendReport(0,t);
  return n?new Promise((e,t)=> {
    let i=()=>t(Error(`操作已中断`));
    if(n.aborted)return i();
    n.addEventListener(`abort`,i, {
      once:!0
    }),r.then(e,t).finally(()=>n.removeEventListener(`abort`,i))
  }):r
}