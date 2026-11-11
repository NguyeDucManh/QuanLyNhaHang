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
          const response = await fetch('/booking/availability/?' + new URLSearchParams({date, time, guests, preferred_area}), {headers: {Accept: 'application/json'}});
          const data = await response.json();
          if (current === serial) availability(data.message, data.available ? 'available' : 'unavailable');
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
