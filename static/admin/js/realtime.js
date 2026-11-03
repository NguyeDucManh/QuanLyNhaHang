(() => {
  'use strict';
  const root = document.querySelector('main [data-realtime-root]');
  if (!root || !root.dataset.realtimeSocket) return;
  const region = root.querySelector('[data-realtime-region]');
  const label = root.querySelector('[data-realtime-status]');
  let socket, timer, stopped = false, retry = 0, refreshing = false, pending = false, posting = false;
  const status = text => { label.textContent = text; };
  const partialURL = () => root.dataset.realtimePartial + location.search;

  function drafts() {
    return [...region.querySelectorAll('form[data-realtime-dirty]')].map(form => ({
      action: form.action,
      fields: [...form.elements].filter(e => e.name && e.type !== 'hidden' && !['submit','button'].includes(e.type))
        .map(e => ({name:e.name, value:e.value, checked:e.checked}))
    }));
  }
  function patch(html) {
    const saved = drafts();
    const focus = document.activeElement;
    const focused = focus?.closest('form') && region.contains(focus)
      ? {action:focus.closest('form').action, name:focus.name, start:focus.selectionStart, end:focus.selectionEnd} : null;
    region.innerHTML = html; // Same-origin Django HTML, escaped and authorized by the existing views.
    for (const draft of saved) {
      const form = [...region.querySelectorAll('form')].find(f => f.action === draft.action);
      if (!form) continue;
      form.dataset.realtimeDirty = 'true';
      for (const field of draft.fields) {
        const input = form.elements.namedItem(field.name);
        if (input) { input.value = field.value; if (input.type === 'checkbox') input.checked = field.checked; }
      }
    }
    if (focused) {
      const form = [...region.querySelectorAll('form')].find(f => f.action === focused.action);
      const input = form?.elements.namedItem(focused.name);
      if (input) { input.focus({preventScroll:true}); try { input.setSelectionRange(focused.start, focused.end); } catch {} }
    }
  }
  async function refresh() {
    pending = true;
    if (refreshing || posting || stopped) return;
    refreshing = true;
    try {
      while (pending && !posting && !stopped) {
        pending = false;
        const response = await fetch(partialURL(), {headers:{'X-Realtime-Partial':'1'}, credentials:'same-origin', cache:'no-store'});
        if (!response.ok || response.redirected) throw new Error('Không thể cập nhật giao diện');
        const html=await response.text();
        if (posting) { pending=true; break; }
        patch(html);
      }
    } catch { status('Chưa cập nhật được · có thể làm mới thủ công'); }
    finally { refreshing = false; }
  }
  function connect() {
    if (stopped) return;
    status('Đang kết nối realtime…');
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(protocol + '//' + location.host + root.dataset.realtimeSocket);
    socket.onopen = () => { retry = 0; status('Realtime · Đã kết nối'); refresh(); };
    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data);
        if (['order.updated','kitchen.queue_changed','invoice.updated','payment.updated'].includes(message.type)) refresh();
      } catch { /* Ignore malformed notifications. HTTP remains the source of truth. */ }
    };
    socket.onclose = event => {
      if (stopped) return;
      if ([4403,4400,1008].includes(event.code)) { stopped = true; status('Không còn quyền realtime · hãy đăng nhập lại'); return; }
      status('Mất kết nối · HTTP vẫn hoạt động');
      const delay = Math.min(30000, 1000 * 2 ** Math.min(retry++, 5)) + Math.random() * 300;
      timer = setTimeout(connect, delay); // Reconnect only; never poll HTTP.
    };
    socket.onerror = () => status('Mất kết nối · HTTP vẫn hoạt động');
  }
  root.addEventListener('input', event => { const form=event.target.closest('form'); if(form) form.dataset.realtimeDirty='true'; });
  root.addEventListener('change', event => { const form=event.target.closest('form'); if(form) form.dataset.realtimeDirty='true'; });
  root.addEventListener('submit', async event => {
    const form=event.target;
    if (form.method.toLowerCase()!=='post' || !new URL(form.action).pathname.match(/\/(status|send-kitchen|confirm|payments\/add|items\/add|items\/\d+\/(quantity|remove|kitchen))\/$/)) return;
    if (posting) { event.preventDefault(); return; }
    event.preventDefault(); posting=true;
    const data=new FormData(form,event.submitter);
    const buttons=[...form.querySelectorAll('button')]; buttons.forEach(button=>button.disabled=true);
    try {
      const response=await fetch(form.action,{method:'POST',body:data,headers:{'X-Realtime-Partial':'1'},credentials:'same-origin',cache:'no-store'});
      if (!response.ok || new URL(response.url).pathname!==root.dataset.realtimePartial) throw new Error('Không thể gửi thao tác');
      delete form.dataset.realtimeDirty;
      patch(await response.text());
    } catch { status('Chưa xác nhận thao tác · hãy kiểm tra/làm mới trước khi thử lại'); }
    finally { posting=false; buttons.forEach(button=>button.disabled=false); if(pending) refresh(); }
  });
  window.addEventListener('pagehide',()=>{ stopped=true; clearTimeout(timer); socket?.close(); });
  window.addEventListener('pageshow',event=>{ if(event.persisted) { stopped=false; retry=0; connect(); } });
  connect();
})();
