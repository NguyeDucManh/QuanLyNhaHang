(() => {
  'use strict';
  document.querySelectorAll('.report-bars').forEach(chart => {
    const rows = [...chart.children];
    const values = rows.map(row => Number(row.dataset.value));
    if (!values.length || values.some(value => !Number.isFinite(value) || value < 0) || chart.getAttribute('aria-label').includes('Kho')) {
      chart.hidden = true;
      return;
    }
    const maximum = Math.max(...values, 1);
    rows.forEach((row, index) => {
      row.querySelector('i').style.width = `${values[index] / maximum * 100}%`;
    });
  });
})();
