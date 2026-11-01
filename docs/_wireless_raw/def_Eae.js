Eae=V( {
  __name:`gifLighting`,props: {
    keyboardConfig: {

    },deviceInfo: {

    }
  },emits:[`update-key-list`],setup(e, {
    emit:t
  }) {
    let {
      themeVars:n,isShowEdit:r,syncDialogVisible:i,syncProgress:a,currentGifId:o,builtInGifList:s,customGifList:c,editGif:l,handleClickGifLighting:u,handleAddGifLighting:d,handleCopyGifLighting:f,handleEditGifLighting:p,handleDeleteGifLighting:m,handleApplyGifLighting:h,handleUploadGifLighting:g,mergeEditorSaveToCustomList:_
    }=g7(e,t);
    return(t,v)=> {
      let y=Ek,b=aM,x=XP,S=SM,C=iF,w=Vk,T=tM;
      return H(),U(`div`,pae,[W(`div`,mae,[W(`h3`,hae,L(t.$t(`gif_text3`)),1),G(y, {
        strong:``,type:`default`,onClick:z(d)
      }, {
        default:B(()=>[v[3]||=W(`i`, {
          class:`i-carbon:add`
        },null,-1),vs(L(t.$t(`led_text23`)),1)]),_:1
      },8,[`onClick`]),G(y, {
        strong:``,type:`default`,disabled:z(o)===``,onClick:z(h)
      }, {
        default:B(()=>[v[4]||=W(`i`, {
          class:`i-carbon:volume-block-storage mr-1`
        },null,-1),vs(L(t.$t(`led_text25`)),1)]),_:1
      },8,[`disabled`,`onClick`])]),W(`div`,gae,[(H(!0),U($o,null,aa(z(s),e=>(H(),U(`div`, {
        key:e.gifId,class:me([`rounded-lg p-2 b-2 hover:cursor-pointer`, {
          "b-primary":z(o)===e.gifId
        }]),onClick:t=>z(u)(e)
      },[W(`span`,null,L(e.text?t.$t(e.text):e.name),1),W(`span`, {
        class:`ml-2 text-primary`,onClick:t=>z(f)(e)
      },L(t.$t(`sty_name2`)),9,vae)],10,_ae))),128))]),G(b),W(`h3`,yae,L(t.$t(`gif_text4`)),1),W(`div`,bae,[(H(!0),U($o,null,aa(z(c),e=>(H(),U(`div`, {
        key:e.gifId,class:me([`rounded-lg p-2 b-2 hover:cursor-pointer`, {
          "b-primary":z(o)===e.gifId
        }]),onClick:t=>z(u)(e)
      },[W(`span`,null,L(e.name),1),W(`span`, {
        class:`ml-2 text-primary`,onClick:t=>z(f)(e)
      },L(t.$t(`sty_name2`)),9,Sae),W(`span`, {
        class:`ml-2 text-primary`,onClick:t=>z(p)(e)
      },L(t.$t(`led_text24`)),9,Cae),G(x, {
        onPositiveClick:t=>z(m)(e)
      }, {
        trigger:B(()=>[W(`span`,wae,L(t.$t(`sty_name4`)),1)]),default:B(()=>[vs(` `+L(t.$t(`gif_text5`)),1)]),_:1
      },8,[`onPositiveClick`])],10,xae))),128))]),z(l)?(H(),ls(S, {
        key:0,show:z(r),"onUpdate:show":v[1]||=e=>on(r)?r.value=e:null,height:`100vh`,placement:`bottom`,"show-mask":!1,"mask-closable":!1,"close-on-esc":!1
      }, {
        default:B(()=>[G(h7, {
          "key-list":e.keyboardConfig.keyList,"device-info":e.deviceInfo,"edit-gif":z(l),onBack:v[0]||=e=>r.value=!1,onSave:z(_),onUpload:z(g)
        },null,8,[`key-list`,`device-info`,`edit-gif`,`onSave`,`onUpload`])]),_:1
      },8,[`show`])):bs(``,!0),G(T, {
        title:t.$t(`gif_text6`),show:z(i),"onUpdate:show":v[2]||=e=>on(i)?i.value=e:null,maskClosable:!1,"close-on-esc":!1,class:`w-100`
      }, {
        default:B(()=>[G(w, {
          title:t.$t(`gif_text6`)
        }, {
          default:B(()=>[W(`p`,Tae,L(t.$t(`led_text27`)),1),G(C, {
            percentage:z(a),"indicator-placement":`inside`,color:z(n).primaryColor,processing:``
          },null,8,[`percentage`,`color`])]),_:1
        },8,[`title`])]),_:1
      },8,[`title`,`show`])])
    }
  }
})