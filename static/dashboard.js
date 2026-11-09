'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('activity-chart');
  const status = document.getElementById('chart-status');
  if (!canvas || !window.Chart) return;
  let chart;
  async function update() {
    try {
      const response = await fetch('/api/stats?days=' + canvas.dataset.days, {redirect: 'error'});
      if (!response.ok) throw new Error('stats');
      const stats = await response.json();
      const labels = stats.activity.map(row => row.time.replace('T', ' ') + (canvas.dataset.days === '1' ? ':00' : ''));
      const sets = [
        {label: 'Connections', data: stats.activity.map(row => row.connections), borderColor: '#73e2ba', backgroundColor: '#73e2ba16', fill: true, tension: .25, pointRadius: 2},
        {label: 'Attempts', data: stats.activity.map(row => row.attempts), borderColor: '#d8af70', backgroundColor: 'transparent', tension: .25, pointRadius: 2}
      ];
      if (chart) {
        chart.data.labels = labels;
        chart.data.datasets = sets;
        chart.update('none');
      } else {
        chart = new Chart(canvas, {type: 'line', data: {labels, datasets: sets}, options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: {legend: {display: false}}, interaction: {intersect: false, mode: 'index'},
          scales: {x: {grid: {color: '#ffffff07'}, ticks: {color: '#87978f', maxTicksLimit: 8}},
                   y: {beginAtZero: true, grid: {color: '#ffffff09'}, ticks: {color: '#87978f', precision: 0}}}
        }});
      }
      status.textContent = '';
    } catch (_) {
      status.textContent = 'Unable to refresh the chart. Check your connection or sign in again.';
    }
  }
  update();
  setInterval(update, 10000);
});
