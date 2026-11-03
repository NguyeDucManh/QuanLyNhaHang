(() => {
 const root=document.querySelector('[data-deposit-page]');if(!root)return;
 const offset=new Date(root.dataset.serverNow).getTime()-Date.now();
 const deadline=new Date(root.dataset.deadline).getTime();const timer=root.querySelector('[data-deposit-countdown]');
 function tick(){const seconds=Math.max(0,Math.floor((deadline-Date.now()-offset)/1000));if(timer)timer.textContent=Math.floor(seconds/60).toString().padStart(2,'0')+':'+(seconds%60).toString().padStart(2,'0');if(!seconds)root.querySelector('[data-checkout-submit]')?.setAttribute('disabled','');}
 tick();let busy=false;const clock=setInterval(tick,1000);
 const poll=setInterval(async()=>{if(document.hidden||busy)return;busy=true;try{const response=await fetch(root.dataset.statusUrl,{cache:'no-store',credentials:'same-origin'});if(!response.ok||response.redirected)return;const state=await response.json();if(state.confirmed)location.replace(root.dataset.successUrl);else if(state.status!==root.dataset.state)location.reload();}catch{}finally{busy=false;}},5000);
 root.querySelector('[data-deposit-checkout]')?.addEventListener('submit',()=>{const button=root.querySelector('[data-checkout-submit]');if(button){button.disabled=true;button.textContent='Đang mở Stripe Checkout…';}});
 window.addEventListener('pagehide',()=>{clearInterval(clock);clearInterval(poll);});
})();
