(() => {
  'use strict';
  const start=()=>{
    const region=document.getElementById('chat-history'); if(!region || region.dataset.initialized)return;
    region.dataset.initialized='1'; const state=document.getElementById('chat-state');
    let socket,timer,delay=1000,closed=false,busy=false,again=false;
    async function refresh(){
      if(busy){again=true;return;} busy=true;
      try{const r=await fetch(region.dataset.source,{headers:{'X-Realtime-Partial':'1'},cache:'no-store'});
        if(!r.ok||r.redirected)throw new Error('permission');
        region.innerHTML=await r.text();
      }catch{state.textContent='Chưa tải được lịch sử; hãy làm mới trang.';}
      finally{busy=false;if(again){again=false;refresh();}}
    }
    function connect(){
      if(closed)return;
      socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+region.dataset.socket);
      socket.onopen=()=>{delay=1000;state.textContent='Đã kết nối';refresh();};
      socket.onmessage=()=>refresh();
      socket.onclose=e=>{state.textContent='Mất kết nối';if(closed||[4400,4403,1008].includes(e.code))return;timer=setTimeout(connect,delay+Math.random()*500);delay=Math.min(delay*2,30000);};
    }
    connect(); window.addEventListener('pagehide',()=>{closed=true;clearTimeout(timer);socket?.close();});
    const form=document.getElementById('chat-send');
    form?.addEventListener('submit',async event=>{
      event.preventDefault(); const button=form.querySelector('button');button.disabled=true;
      try{
        const r=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{Accept:'application/json'}});
        if(!r.ok)throw new Error('Gửi chưa thành công; kiểm tra lịch sử trước khi thử lại.');
        const data=await r.json(); form.elements.request_key.value=data.request_key; form.elements.content.value='';refresh();
      }catch(error){state.textContent=error.message;}finally{button.disabled=false;}
    });
    window.addEventListener('pageshow',e=>{if(e.persisted){closed=false;connect();}});
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
  document.addEventListener('admin:content-ready',start);
})();
