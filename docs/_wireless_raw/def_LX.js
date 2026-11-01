LX=async(e,t=65383)=> {
  let n=(await navigator.hid.getDevices()).find(n=>n.collections.some(r=>r.usagePage===t&&n.productId===e));
  return n?(n.opened||await n.open(),n):(console.warn(`未找到usagePage为${t}的设备`),!1)
}