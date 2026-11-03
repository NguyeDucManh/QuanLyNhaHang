(() => {
'use strict';
const navButton = document.getElementById('nav-toggle');
navButton?.addEventListener('click', () => {
  const open = document.getElementById('main-nav').classList.toggle('is-open');
  navButton.setAttribute('aria-expanded', String(open));
});
const helpButton = document.getElementById('help-toggle');
const helpPanel = document.getElementById('help-panel');
function toggleHelp(open) {
  helpPanel.hidden = !open;
  helpButton.setAttribute('aria-expanded', String(open));
}
helpButton?.addEventListener('click', () => toggleHelp(helpPanel.hidden));
document.getElementById('help-close')?.addEventListener('click', () => toggleHelp(false));
document.addEventListener('keydown', event => {
  if(event.key === 'Escape') {
    toggleHelp(false);
    document.getElementById('main-nav').classList.remove('is-open');
    navButton.setAttribute('aria-expanded', 'false');
  }
});
let toastTimer;
function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('visible'), 3200);
}
document.querySelectorAll('.add-form').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(form.action, {method:'POST', body:new FormData(form), headers:{Accept:'application/json'}, credentials:'same-origin'});
      if(!response.ok) throw new Error('Không thể thêm món. Vui lòng tải lại trang và thử lại.');
      const data = await response.json();
      document.querySelectorAll('.cart-count').forEach(el => el.textContent = data.count);
      document.querySelectorAll("[data-booking-cart-count]").forEach(el => el.textContent = data.food_count);
      document.querySelectorAll("[data-booking-cart-total]").forEach(el => el.textContent = data.food_total + " \u20ab");
      toast(data.message);
    } catch(error) {
      toast(error.message || 'Không thể kết nối. Vui lòng thử lại.');
    } finally {
      button.disabled = false;
    }
  });
});
})();

