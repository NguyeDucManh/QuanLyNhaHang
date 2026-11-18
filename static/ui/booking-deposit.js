(() => {
 const root=document.querySelector('[data-deposit-page]');if(!root)return;
 const offset=new Date(root.dataset.serverNow).getTime()-Date.now();
 const deadline=new Date(root.dataset.deadline).getTime();const timer=root.querySelector('[data-deposit-countdown]');
 function tick(){const seconds=Math.max(0,Math.floor((deadline-Date.now()-offset)/1000));if(timer)timer.textContent=Math.floor(seconds/60).toString().padStart(2,'0')+':'+(seconds%60).toString().padStart(2,'0');if(!seconds)root.querySelector('[data-checkout-submit]')?.setAttribute('disabled','');}
 const message=root.querySelector('[data-deposit-poll-message]');
 const started=Date.now();let busy=false,leaving=false;
 async function refresh(){
  if(document.hidden||busy||leaving)return;busy=true;
  try{
   const response=await fetch(root.dataset.statusUrl,{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
   if(!response.ok||response.redirected||!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('status');
   const state=await response.json();
   if(typeof state.confirmed!=='boolean'||typeof state.payment_state!=='string')throw new Error('payload');
   if(state.confirmed===true){leaving=true;location.replace(root.dataset.successUrl);}
   else if(state.status!==root.dataset.state||state.payment_state!==root.dataset.paymentState){leaving=true;location.reload();}
   else if(message)message.textContent=Date.now()-started>=60000?'Chưa nhận được webhook. Không thanh toán lại; liên hệ nhà hàng để kiểm tra.':'Đang chờ webhook hợp lệ. Không thanh toán lại.';
  }catch{if(message)message.textContent='Chưa kiểm tra được trạng thái. Không thanh toán lại; thử kiểm tra hoặc liên hệ nhà hàng.';}
  finally{busy=false;}
 }
 tick();const clock=setInterval(tick,1000);const poll=setInterval(refresh,5000);
 root.querySelector('[data-deposit-refresh]')?.addEventListener('click',refresh);
 root.querySelector('[data-deposit-checkout]')?.addEventListener('submit',event=>{
  if(leaving){event.preventDefault();return;}leaving=true;
  const button=root.querySelector('[data-checkout-submit]');if(button){button.disabled=true;button.textContent='Đang kiểm tra phiên Stripe…';}
 });
 window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
 window.addEventListener('pagehide',()=>{clearInterval(clock);clearInterval(poll);});
})();
