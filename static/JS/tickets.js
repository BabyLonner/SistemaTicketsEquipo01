/* Tickets: interacciones de interfaz y datos de ejemplo.
   Mantiene la navegación de las pantallas existentes. No reemplaza app.js
   ni realiza operaciones reales en la base de datos. */
document.addEventListener("DOMContentLoaded", () => {
  const rows = [...document.querySelectorAll(".ticket-row")];
  const search = document.getElementById("ticket-search");
  const status = document.getElementById("status-filter");
  const priority = document.getElementById("priority-filter");
  const technician = document.getElementById("technician-filter");
  const resultsCount = document.getElementById("results-count");
  const emptyState = document.getElementById("empty-state");
  const selectAll = document.getElementById("select-all");
  const toast = document.getElementById("toast");
  let toastTimer;

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function applyFilters() {
    const query = search.value.trim().toLocaleLowerCase("es");
    const chosenStatus = status.value;
    const chosenPriority = priority.value;
    const chosenTechnician = technician.value;
    let visible = 0;

    rows.forEach((row) => {
      const matchesText = `${row.dataset.code} ${row.dataset.subject} ${row.dataset.requester}`.toLocaleLowerCase("es").includes(query);
      const matchesStatus = !chosenStatus || row.dataset.status === chosenStatus;
      const matchesPriority = !chosenPriority || row.dataset.priority === chosenPriority;
      const matchesTechnician = !chosenTechnician || row.dataset.technician === chosenTechnician;
      const matches = matchesText && matchesStatus && matchesPriority && matchesTechnician;
      row.hidden = !matches;
      if (matches) visible++;
      const checkbox = row.querySelector(".row-check");
      if (!matches && checkbox) checkbox.checked = false;
    });

    resultsCount.textContent = visible
      ? `Mostrando ${visible} ticket${visible === 1 ? "" : "s"} de 47 tickets`
      : "Mostrando 0 tickets";
    emptyState.hidden = visible !== 0;
    selectAll.checked = false;
    selectAll.indeterminate = false;
  }

  [search, status, priority, technician].forEach((control) => {
    control.addEventListener(control === search ? "input" : "change", applyFilters);
  });

  document.getElementById("reset-filters").addEventListener("click", () => {
    search.value = "";
    status.value = "";
    priority.value = "";
    technician.value = "";
    applyFilters();
    showToast("Se limpiaron los filtros.");
  });

  document.getElementById("show-urgent").addEventListener("click", () => {
    status.value = "En proceso";
    priority.value = "Alta";
    applyFilters();
    showToast("Mostrando tickets de prioridad alta en proceso.");
  });

  selectAll.addEventListener("change", () => {
    rows.filter((row) => !row.hidden).forEach((row) => {
      row.querySelector(".row-check").checked = selectAll.checked;
    });
  });

  rows.forEach((row) => {
    row.querySelector(".row-check").addEventListener("change", () => {
      const visibleChecks = rows.filter((item) => !item.hidden).map((item) => item.querySelector(".row-check"));
      const checkedCount = visibleChecks.filter((checkbox) => checkbox.checked).length;
      selectAll.checked = visibleChecks.length > 0 && checkedCount === visibleChecks.length;
      selectAll.indeterminate = checkedCount > 0 && checkedCount < visibleChecks.length;
    });

    row.querySelector('[data-action="more"]').addEventListener("click", () => {
      showToast(`Acciones adicionales para ${row.dataset.code}: conecta este botón con tu backend.`);
    });
  });

  document.querySelectorAll(".pagination .page-number").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".pagination .page-number").forEach((item) => {
        item.classList.remove("current");
        item.removeAttribute("aria-current");
      });
      button.classList.add("current");
      button.setAttribute("aria-current", "page");
      showToast(`Página ${button.textContent}. La paginación real requiere consultar la API.`);
    });
  });

  document.querySelectorAll(".pagination button[aria-label='Página siguiente'], .pagination button[aria-label='Última página']").forEach((button) => {
    button.addEventListener("click", () => {
      const pages = [...document.querySelectorAll(".pagination .page-number")];
      const currentIndex = pages.findIndex((item) => item.classList.contains("current"));
      const nextIndex = button.getAttribute("aria-label") === "Última página" ? pages.length - 1 : Math.min(currentIndex + 1, pages.length - 1);
      pages[nextIndex].click();
    });
  });

  document.querySelectorAll(".pagination button[aria-label='Página anterior'], .pagination button[aria-label='Primera página']").forEach((button) => {
    button.addEventListener("click", () => {
      const pages = [...document.querySelectorAll(".pagination .page-number")];
      const currentIndex = pages.findIndex((item) => item.classList.contains("current"));
      const nextIndex = button.getAttribute("aria-label") === "Primera página" ? 0 : Math.max(currentIndex - 1, 0);
      pages[nextIndex].click();
    });
  });

  /* La búsqueda global filtra el listado visible en esta pantalla. */
  const globalSearch = document.getElementById("global-search");
  globalSearch.addEventListener("input", () => {
    search.value = globalSearch.value;
    applyFilters();
  });

  /* Inicializa contadores con los datos de ejemplo cargados en esta página. */
  const countByStatus = (value) => rows.filter((row) => row.dataset.status === value).length;
  document.getElementById("metric-open").textContent = countByStatus("Abierto");
  document.getElementById("metric-progress").textContent = countByStatus("En proceso");
  document.getElementById("metric-resolved").textContent = countByStatus("Resuelto");
  document.getElementById("metric-closed").textContent = countByStatus("Cerrado");
  applyFilters();
});