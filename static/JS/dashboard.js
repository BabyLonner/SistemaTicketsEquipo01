
document.addEventListener("DOMContentLoaded", () => {
  const dataElement = document.getElementById("dashboard-data");
  const feedback = document.getElementById("filter-feedback");

  if (!dataElement || typeof Chart === "undefined") {
    if (feedback) feedback.textContent = "No se pudieron cargar los datos del dashboard.";
    return;
  }

  const datos = JSON.parse(dataElement.textContent);

  const palette = {
    blue: "#3479d9",
    lightBlue: "#75b8f8",
    green: "#31bd91",
    slate: "#637b93",
    teal: "#2499a7",
    gray: "#a5b8cb"
  };

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          usePointStyle: true,
          boxWidth: 8,
          padding: 14,
          color: "#28466e",
          font: { family: "Figtree", size: 11 }
        }
      }
    }
  };

  function crearGrafico(id, tipo, labels, valores, colores, opciones = {}) {
    const canvas = document.getElementById(id);
    if (!canvas) return;

    new Chart(canvas, {
      type: tipo,
      data: {
        labels,
        datasets: [{
          data: valores,
          backgroundColor: colores,
          borderWidth: 0,
          borderRadius: tipo === "bar" ? 5 : 0,
          maxBarThickness: 48
        }]
      },
      options: {
        ...commonOptions,
        ...opciones
      }
    });
  }

  const estados = datos.estados || [];
  crearGrafico(
    "statusChart",
    "doughnut",
    estados.map(x => x.estado),
    estados.map(x => Number(x.total)),
    [palette.blue, palette.lightBlue, palette.green, palette.slate],
    { cutout: "60%" }
  );

  const prioridades = datos.prioridades || [];
  crearGrafico(
    "priorityChart",
    "bar",
    prioridades.map(x => x.prioridad),
    prioridades.map(x => Number(x.total)),
    [palette.blue, palette.lightBlue, palette.slate],
    {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#28466e" } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#e8f0fa" } }
      }
    }
  );

  const tecnicos = datos.tecnicos || [];
  crearGrafico(
    "technicianChart",
    "bar",
    tecnicos.map(x => x.tecnico || "Sin asignar"),
    tecnicos.map(x => Number(x.total)),
    [palette.blue, "#4c91ed", "#5ca2f5", "#72b1fa", palette.gray],
    {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#e8f0fa" } },
        y: { grid: { display: false }, ticks: { color: "#28466e" } }
      }
    }
  );

  const categorias = datos.categorias || [];
  crearGrafico(
    "categoryChart",
    "doughnut",
    categorias.map(x => x.categoria),
    categorias.map(x => Number(x.total)),
    [palette.blue, palette.lightBlue, palette.green, palette.teal, palette.gray],
    { cutout: "58%" }
  );

  // Los datos recientes se renderizan en el servidor con Jinja.
  // Búsqueda visual sobre las filas que ya están en la tabla.
  const globalSearch = document.querySelector(".global-search input");

  if (globalSearch) {
    globalSearch.addEventListener("input", () => {
      const query = globalSearch.value.trim().toLowerCase();

      document.querySelectorAll("#recent-tickets tr").forEach(row => {
        row.hidden = !row.textContent.toLowerCase().includes(query);
      });
    });
  }

  if (feedback) {
    feedback.textContent = "Datos reales de la empresa autenticada";
  }
});
