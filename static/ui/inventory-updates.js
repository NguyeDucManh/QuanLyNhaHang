(() => {
  if (!['ingredients','transactions','stock-alerts','purchase-orders','food-cost'].includes(document.body.dataset.adminPage)) return;
  let dirty = false, busy = false;
  document.addEventListener('input', event => { if(event.target.closest('form[method="post"]')) dirty = true; });
  const socket = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/management/inventory/');
  socket.addEventListener('message', async event => {
    if (JSON.parse(event.data).type !== 'inventory.updated' || dirty || busy || document.hidden) return;
    busy = true;
    try {
      const response = await fetch(location.href, {cache:'no-store', credentials:'same-origin'});
      if (!response.ok || response.redirected) return;
      const next = new DOMParser().parseFromString(await response.text(),'text/html').querySelector('#server-content');
      if (next && !dirty) document.querySelector('#main').innerHTML = next.innerHTML;
    } catch { /* Retain the last view; an inventory transport error never submits a form. */ }
    finally { busy = false; }
  });
  window.addEventListener('pagehide', () => socket.close());
})();
