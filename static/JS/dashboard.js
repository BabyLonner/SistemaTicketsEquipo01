/* Dashboard de Soporte TI
   Interacciones de demostración. Para datos reales, conectar estas vistas
   con los endpoints Flask de la API REST. */
document.addEventListener("DOMContentLoaded", () => {
  const palette = {
    blue: "#3479d9", lightBlue: "#75b8f8", green: "#31bd91",
    slate: "#637b93", teal: "#2499a7", gray: "#a5b8cb"
  };
  const commonOptions = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 14, color: "#28466e", font: { family: "Figtree", size: 11 } } } }
  };

  const statusChart = new Chart(document.getElementById("statusChart"), {
    type: "doughnut",
    data: { labels: ["Abierto", "En proceso", "Resuelto", "Cerrado"], datasets: [{ data: [32, 28, 50, 15], backgroundColor: [palette.blue, palette.lightBlue, palette.green, palette.slate], borderWidth: 0, hoverOffset: 5 }] },
    options: { ...commonOptions, cutout: "60%" }
  });

  const priorityChart = new Chart(document.getElementById("priorityChart"), {
    type: "bar",
    data: { labels: ["Alta", "Media", "Baja"], datasets: [{ data: [45, 62, 28], backgroundColor: [palette.blue, palette.lightBlue, palette.slate], borderRadius: 5, maxBarThickness: 48 }] },
    options: { ...commonOptions, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: "#28466e" } }, y: { beginAtZero: true, grid: { color: "#e8f0fa" }, ticks: { color: "#28466e", stepSize: 20 } } } }
  });

  const technicianChart = new Chart(document.getElementById("technicianChart"), {
    type: "bar",
    data: { labels: ["Juan Pérez", "María López", "Carlos Ruiz", "Ana Torres", "Otros"], datasets: [{ data: [40, 35, 28, 20, 30], backgroundColor: [palette.blue, "#4c91ed", "#5ca2f5", "#72b1fa", palette.gray], borderRadius: 5, maxBarThickness: 20 }] },
    options: { ...commonOptions, indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, grid: { color: "#e8f0fa" }, ticks: { color: "#28466e" } }, y: { grid: { display: false }, ticks: { color: "#28466e" } } } }
  });

  new Chart(document.getElementById("categoryChart"), {
    type: "doughnut",
    data: { labels: ["Hardware", "Software", "Redes", "Accesos", "Otros"], datasets: [{ data: [38, 45, 28, 18, 24], backgroundColor: [palette.blue, palette.lightBlue, palette.green, palette.teal, palette.gray], borderWidth: 0, hoverOffset: 5 }] },
    options: { ...commonOptions, cutout: "58%" }
  });

  const filterForm = document.getElementById("filters-form");
  const feedback = document.getElementById("filter-feedback");
  filterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const from = document.getElementById("desde").value;
    const to = document.getElementById("hasta").value;
    const area = document.getElementById("area").value;
    if (from && to && from > to) {
      feedback.textContent = "La fecha inicial debe ser anterior a la fecha final.";
      feedback.classList.add("error");
      return;
    }
    feedback.classList.remove("error");
    const areaText = area === "todas" ? "todas las áreas" : area;
    feedback.textContent = `Filtros seleccionados: ${from || "sin inicio"} – ${to || "sin fin"} · ${areaText}. Datos de demostración; falta conectar la API.`;
  });

  const globalSearch = document.querySelector(".global-search input");
  globalSearch.addEventListener("input", () => {
    const query = globalSearch.value.trim().toLowerCase();
    document.querySelectorAll("#recent-tickets tr").forEach((row) => {
      row.hidden = !row.textContent.toLowerCase().includes(query);
    });
  });
});