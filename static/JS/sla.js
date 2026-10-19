/* SLA: prototipo visual con datos ficticios. Todavía no conecta con Flask ni base de datos. */
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("tickets-tbody");
  const rows = [...tbody.querySelectorAll("tr")];
  const toast = document.getElementById("toast");
  const modal = document.getElementById("ticket-modal");
  let currentSla = "all";
  let currentPage = 1;
  const pageSize = 10;
  let toastTimer;

  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
  }
  function normalize(value) {
    return (value || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }
  function getMatches() {
    const query = normalize(document.getElementById("ticket-search").value.trim());
    const priority = document.getElementById("priority-filter").value;
    const category = document.getElementById("category-filter").value;
    const technician = document.getElementById("technician-filter").value;
    const status = document.getElementById("status-filter").value;
    return rows.filter(row => {
      const searchText = normalize(`${row.dataset.id} ${row.dataset.subject} ${row.dataset.requester}`);
      if (query && !searchText.includes(query)) return false;
      if (currentSla !== "all" && row.dataset.sla !== currentSla) return false;
      if (priority && row.dataset.priority !== priority) return false;
      if (category && row.dataset.category !== category) return false;
      if (technician && row.dataset.technician !== technician) return false;
      if (status && row.dataset.status !== status) return false;
      return true;
    });
  }
  function render() {
    const matches = getMatches();
    const pages = Math.max(1, Math.ceil(matches.length / pageSize));
    currentPage = Math.min(currentPage, pages);
    const start = (currentPage - 1) * pageSize;
    const visible = new Set(matches.slice(start, start + pageSize));
    rows.forEach(row => {
      row.hidden = !visible.has(row);
      if (!visible.has(row)) row.querySelector(".row-check").checked = false;
    });
    document.getElementById("results-label").textContent = `Mostrando ${Math.min(pageSize, Math.max(0, matches.length - start))} de ${matches.length} tickets`;
    document.querySelectorAll(".page-number").forEach(button => {
      button.hidden = Number(button.dataset.page) > pages;
      button.classList.toggle("active", Number(button.dataset.page) === currentPage);
    });
    document.getElementById("prev-page").disabled = currentPage <= 1;
    document.getElementById("next-page").disabled = currentPage >= pages;
    const visibleChecks = rows.filter(row => !row.hidden).map(row => row.querySelector(".row-check"));
    const checkedCount = visibleChecks.filter(check => check.checked).length;
    const selectAll = document.getElementById("select-all");
    selectAll.checked = visibleChecks.length > 0 && checkedCount === visibleChecks.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < visibleChecks.length;
  }
  function openModal(title, description) {
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-description").textContent = description;
    modal.hidden = false;
  }
  function closeModal() { modal.hidden = true; }

  document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => {
    currentSla = tab.dataset.sla;
    currentPage = 1;
    document.querySelectorAll(".tab").forEach(item => {
      const active = item === tab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    render();
  }));
  document.getElementById("apply-filters").addEventListener("click", () => {
    currentPage = 1;
    render();
    notify("Filtros aplicados a los tickets de ejemplo.");
  });
  document.getElementById("clear-filters").addEventListener("click", () => {
    document.getElementById("ticket-search").value = "";
    ["priority-filter", "category-filter", "technician-filter", "status-filter"].forEach(id => document.getElementById(id).value = "");
    currentSla = "all";
    currentPage = 1;
    document.querySelectorAll(".tab").forEach(tab => {
      const active = tab.dataset.sla === "all";
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    render();
    notify("Filtros limpiados.");
  });
  document.getElementById("ticket-search").addEventListener("input", () => { currentPage = 1; render(); });
  document.getElementById("global-search").addEventListener("keydown", event => {
    if (event.key === "Enter" && event.target.value.trim()) {
      document.getElementById("ticket-search").value = event.target.value.trim();
      currentPage = 1;
      render();
      notify("Búsqueda aplicada a la tabla SLA.");
    }
  });
  document.getElementById("select-all").addEventListener("change", event => {
    rows.filter(row => !row.hidden).forEach(row => row.querySelector(".row-check").checked = event.target.checked);
  });
  tbody.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    const row = button.closest("tr");
    if (button.classList.contains("view-ticket")) {
      openModal(`Detalle del ticket ${row.dataset.id}`, `Asunto: ${row.dataset.subject}\nSolicitante: ${row.dataset.requester}\nCategoría: ${row.dataset.category}\nPrioridad: ${row.dataset.priority}\nTécnico: ${row.dataset.technician}\nEstado: ${row.dataset.status}\nEstado SLA: ${row.dataset.sla}\nTiempo transcurrido: ${row.dataset.elapsed}\nTiempo límite: ${row.dataset.limit}`);
    }
    if (button.classList.contains("more-action")) {
      openModal(`Seguimiento SLA · ${row.dataset.id}`, `Este ticket está en estado SLA: ${row.dataset.sla}.\nTiempo transcurrido: ${row.dataset.elapsed}\nTiempo límite: ${row.dataset.limit}\n\nEn la versión funcional, aquí se mostraría el historial de eventos y las marcas de tiempo del ticket.`);
    }
  });
  document.getElementById("sla-config-form").addEventListener("submit", event => {
    event.preventDefault();
    const settings = [...event.currentTarget.querySelectorAll("select")].map(select => `${select.dataset.priority}: ${select.dataset.kind === "response" ? "respuesta" : "resolución"} ${select.value}`);
    notify("Configuración SLA actualizada visualmente.");
    openModal("Configuración guardada", `${settings.join("\n")}\n\nLos valores son de demostración y todavía no se guardan en el servidor.`);
  });
  document.getElementById("period-filter").addEventListener("change", event => {
    notify(`Periodo seleccionado: ${event.target.options[event.target.selectedIndex].text}. Los datos de muestra no cambian.`);
  });
  document.getElementById("notifications-button").addEventListener("click", () => { window.location.href = "notificaciones.html"; });
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal-confirm").addEventListener("click", closeModal);
  modal.addEventListener("click", event => { if (event.target === modal) closeModal(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeModal(); });
  document.getElementById("prev-page").addEventListener("click", () => { if (currentPage > 1) { currentPage--; render(); } });
  document.getElementById("next-page").addEventListener("click", () => { if (currentPage < Math.ceil(getMatches().length / pageSize)) { currentPage++; render(); } });
  document.querySelectorAll(".page-number").forEach(button => button.addEventListener("click", () => { currentPage = Number(button.dataset.page); render(); }));

  render();
});