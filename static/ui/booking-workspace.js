(() => {
  'use strict';
  for (const form of document.querySelectorAll('[data-booking-preview]')) {
    const target = form.querySelector('[data-booking-availability]');
    let timer, serial = 0;
    const availability = (text, state) => {
      target.textContent = text;
      target.dataset.state = state;
      document.querySelectorAll('[data-booking-availability-summary]').forEach(el => el.textContent = text);
    };
    const update = () => {
      const date = form.querySelector('[name=date]').value;
      const time = form.querySelector('[name=time]').value;
      const guests = form.querySelector('[name=guests]').value;
      const preferred_area = form.querySelector('[name=preferred_area]')?.value || '';
      const tableSelect = form.querySelector('[name=preferred_table]');
      const preferred_table = tableSelect?.value || '';
      document.querySelectorAll('[data-booking-table-summary]').forEach(el=>el.textContent=preferred_table?tableSelect.selectedOptions[0]?.textContent.split(' · ')[0]:'Tự động khi xác nhận');
      const map = form.querySelector('[data-booking-table-map]');
      // Remove stale availability immediately; server remains authoritative.
      if(map)map.replaceChildren();
      for (const [key, value] of [['date', date], ['time', time], ['guests', guests]]) {
        for (const el of document.querySelectorAll('[data-booking-selection="' + key + '"]')) {
          el.textContent = (key === 'date' && value ? value.split('-').reverse().join('/') : value) || 'Chưa chọn';
        }
      }
      clearTimeout(timer);
      const current = ++serial;
      if (!date || !time || !guests) { availability('Chưa kiểm tra', 'unknown'); return; }
      availability('Đang kiểm tra khả năng phục vụ…', 'loading');
      timer = setTimeout(async () => {
        try {
          const response = await fetch('/booking/availability/?' + new URLSearchParams({date, time, guests, preferred_area, preferred_table}), {headers: {Accept: 'application/json'}});
          if(!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('Invalid API response');
          const data = await response.json();
          if (current === serial) {
            availability(data.message, data.available ? 'available' : 'unavailable');
            for(const table of data.tables || []){
              const option=tableSelect && Array.from(tableSelect.options).find(o=>o.value===String(table.id));
              if(option){option.disabled=!table.available&&String(table.id)!==preferred_table;option.textContent=`${table.code} · ${table.area} · ${table.capacity} chỗ · ${table.reason}`;}
              if(!map)continue;
              const button=document.createElement('button');button.type='button';button.disabled=!table.available;
              button.className='booking-table-choice';button.dataset.state=table.state;button.setAttribute('aria-pressed',String(String(table.id)===preferred_table));
              button.textContent=`${table.code} · ${table.area} · ${table.capacity} chỗ — ${table.reason}`;
              button.addEventListener('click',()=>{tableSelect.value=String(table.id);tableSelect.dispatchEvent(new Event('change',{bubbles:true}));});map.append(button);
            }
          }
        } catch (error) {
          if (current === serial) availability('Chưa kiểm tra được. Hệ thống sẽ kiểm tra lại khi bạn gửi đặt bàn.', 'unavailable');
        }
      }, 450);
    };
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    update();
  }
})();
