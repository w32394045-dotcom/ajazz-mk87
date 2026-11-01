ZX=(e,t,n)=> {
  try {
    let t=e=> {
      let {
        data:t
      }=e,r=new Uint8Array(t.buffer);
      if(r.length>=3&&r[0]===85&&r[1]===HX.GET_24G_DISCONNECT_NOTIFY&&r[2]===5&&n&&typeof n==`function`)try {
        n()
      }catch(e) {
        console.error(`调用重置回调函数时出错:`,e)
      }
    };
    return e.addEventListener(`inputreport`,t), {
      success:!0,removeListener:()=> {
        e.removeEventListener(`inputreport`,t)
      }
    }
  }catch(e) {
    return console.error(`启动重置监听失败:`,e), {
      success:!1
    }
  }
}