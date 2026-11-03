(() => {
  let floor = document.querySelector('.pos-floor');
  if (!document.querySelector('.pos-layout')) return;
  let status = '';
  let category = '', foodQuery = '';
  function filterCatalog() {
    document.querySelectorAll('[data-food-category]').forEach(card => {
      card.hidden = !!((category && card.dataset.foodCategory !== category) || !card.dataset.foodName.toLocaleLowerCase('vi').includes(foodQuery));
    });
  }
  let area = document.getElementById('pos-area');
  function filter() {
    if (!floor?.querySelector('.pos-table-grid') || !area) return;
    let visible = 0;
    floor.querySelectorAll('.pos-table').forEach(table => {
      table.hidden = !!((status && table.dataset.status !== status) || (area.value && table.dataset.area !== area.value));
      if (!table.hidden) visible++;
    });
    document.getElementById('pos-filter-empty').hidden = visible > 0;
    const areaTables = [...floor.querySelectorAll('.pos-table')].filter(table => !area.value || table.dataset.area === area.value);
    floor.querySelectorAll('[data-pos-status]').forEach(button => {
      const count = areaTables.filter(table => !button.dataset.posStatus || table.dataset.status === button.dataset.posStatus).length;
      button.textContent = button.textContent.replace(/\s*\(\d+\)$/, '') + ' (' + count + ')';
    });
  }
  document.addEventListener('change', event => { if (event.target.id === 'pos-area') filter(); });
  document.addEventListener('input', event => { if(event.target.id==='pos-food-search'){foodQuery=event.target.value.trim().toLocaleLowerCase('vi');filterCatalog();} });
  document.addEventListener('click', event => {
    if(event.target.closest('[data-pos-print]'))window.print();
    const kitchenButton=event.target.closest('[data-pos-kitchen]');
    if(kitchenButton){const state=kitchenButton.dataset.posKitchen;document.querySelectorAll('[data-pos-kitchen]').forEach(b=>b.setAttribute('aria-pressed',String(b===kitchenButton)));document.querySelectorAll('[data-kitchen-states]').forEach(card=>{card.hidden=!!(state&&!card.dataset.kitchenStates.split(' ').includes(state));});}
    const categoryButton=event.target.closest('[data-pos-category]');
    if(categoryButton){category=categoryButton.dataset.posCategory;document.querySelectorAll('[data-pos-category]').forEach(b=>b.setAttribute('aria-pressed',String(b===categoryButton)));filterCatalog();}
    const button = event.target.closest('[data-pos-status]');
    if (button) {
      status = button.dataset.posStatus;
      floor.querySelectorAll('[data-pos-status]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      filter();
      document.querySelector('#pos-food-search').value=foodQuery;
      document.querySelectorAll('[data-pos-category]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.posCategory===category)));
      filterCatalog();
    }
    const table = event.target.closest('.pos-table');
    if (table && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
      event.preventDefault();
      refresh(new URL(table.href), true);
    }
  });
  let busy = false;
  async function refresh(url = new URL(location.href), navigate = false) {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const response = await fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (!response.ok || response.redirected) return;
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const next = doc.querySelector('.pos-layout');
      if (!next) return;
      const selectedArea = area?.value || '';
      document.querySelector('.pos-layout').replaceWith(next);
      floor = next.querySelector('.pos-floor');
      area = next.querySelector('#pos-area');
      if (area) area.value = selectedArea;
      floor.querySelectorAll('[data-pos-status]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.posStatus === status)));
      filter();
      document.querySelector('#pos-food-search').value = foodQuery;
      document.querySelectorAll('[data-pos-category]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.posCategory === category)));
      filterCatalog();
      if (navigate) history.pushState({}, '', url);
    } catch { /* Retain the last successful view when the network is unavailable. */ }
    finally { busy = false; }
  }
  window.addEventListener('popstate', () => refresh());
  const interval = setInterval(() => refresh(), 30000);
  let socket;
  if (document.querySelector('.pos-layout').dataset.kitchenAccess === 'true') {
    socket = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/management/kitchen/');
    socket.addEventListener('message', () => refresh());
  }
  window.addEventListener('pagehide', () => { clearInterval(interval); socket?.close(); });
})();
