/* Gráficos del dashboard con Chart.js */
(function () {
  'use strict';
  const fuente = document.getElementById('datos-dashboard');
  if (!fuente || !window.Chart) return;
  const datos = JSON.parse(fuente.textContent);

  Chart.defaults.font.family = "'Figtree', system-ui, sans-serif";
  Chart.defaults.color = '#6B707A';

  const ejes = {
    grid: { color: '#EFEAE2' },
    border: { display: false },
    ticks: { precision: 0 }
  };

  new Chart(document.getElementById('grafico-prioridad'), {
    type: 'bar',
    data: {
      labels: datos.prioridad.map(function (p) { return p[0]; }),
      datasets: [{
        data: datos.prioridad.map(function (p) { return p[1]; }),
        backgroundColor: ['#3F4C8C', '#7C88C4', '#B9C1E6'],
        borderRadius: 6,
        barThickness: 18
      }]
    },
    options: {
      indexAxis: 'y',
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: Object.assign({ beginAtZero: true }, ejes), y: { grid: { display: false }, border: { display: false } } }
    }
  });

  new Chart(document.getElementById('grafico-tipo'), {
    type: 'bar',
    data: {
      labels: datos.categoria.map(function (c) { return c[0].split(' ')[0]; }),
      datasets: [{
        data: datos.categoria.map(function (c) { return c[1]; }),
        backgroundColor: '#7C88C4',
        borderRadius: { topLeft: 6, topRight: 6 },
        maxBarThickness: 36
      }]
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: function (items) { return datos.categoria[items[0].dataIndex][0]; } } }
      },
      scales: { y: Object.assign({ beginAtZero: true }, ejes), x: { grid: { display: false }, border: { display: false } } }
    }
  });
})();
