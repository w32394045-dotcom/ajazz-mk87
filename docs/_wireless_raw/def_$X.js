$X=async(e,t,n)=> {
  try {
    let t=e=> {
      let {
        data:t
      }=e,r=new Uint8Array(t.buffer);
      if(r.length>=3&&r[0]===166&&r[1]===255&&r[2]===1&&n&&typeof n==`function`)try {
        n()
      }catch(e) {
        console.error(`调用2.4G唤醒回调函数时出错:`,e)
      }
    };
    return e.addEventListener(`inputreport`,t), {
      success:!0,removeListener:()=> {
        e.removeEventListener(`inputreport`,t)
      }
    }
  }catch(e) {
    return console.error(`启动2.4G唤醒监听失败:`,e), {
      success:!1
    }
  }
}