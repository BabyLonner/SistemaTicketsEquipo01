/* Mis Tickets: prototipo visual con datos de ejemplo; aún no conectado a Flask ni a base de datos. */
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("tickets-tbody");
  const rows = [...tbody.querySelectorAll("tr")];
  const toast = document.getElementById("toast");
  const modal = document.getElementById("ticket-modal");
  const pageSize = 10;
  let currentPage = 1, toastTimer;
  const norm = value => (value || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  function notify(message) {
    toast.textContent = message; toast.classList.add("show"); clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2700);
  }
  function matches() {
    const q = norm(document.getElementById("ticket-search").value.trim());
    const status = document.getElementById("status-filter").value;
    const priority = document.getElementById("priority-filter").value;
    const category = document.getElementById("category-filter").value;
    return rows.filter(row => {
      const text = norm(`${row.dataset.id} ${row.dataset.subject} ${row.dataset.description} ${row.dataset.category}`);
      return (!q || text.includes(q)) && (!status || row.dataset.status === status)
        && (!priority || row.dataset.priority === priority) && (!category || row.dataset.category === category);
    });
  }
  function render() {
    const found = matches(), pages = Math.max(1, Math.ceil(found.length / pageSize));
    currentPage = Math.min(currentPage, pages);
    const start = (currentPage - 1) * pageSize, visible = new Set(found.slice(start, start + pageSize));
    rows.forEach(row => row.hidden = !visible.has(row));
    document.getElementById("results-label").textContent = found.length
      ? `Mostrando ${start + 1}–${Math.min(start + pageSize, found.length)} de ${found.length} tickets`
      : "No hay tickets que coincidan con los filtros";
    document.getElementById("empty-state").hidden = found.length > 0;
    document.querySelector(".table-wrap").hidden = found.length === 0;
    document.querySelectorAll(".page-number").forEach(btn => {
      btn.hidden = Number(btn.dataset.page) > pages;
      btn.classList.toggle("active", Number(btn.dataset.page) === currentPage);
    });
    document.getElementById("prev-page").disabled = currentPage <= 1;
    document.getElementById("next-page").disabled = currentPage >= pages;
  }
  function clearFilters() {
    document.getElementById("ticket-search").value = "";
    ["status-filter", "priority-filter", "category-filter"].forEach(id => document.getElementById(id).value = "");
    currentPage = 1; render(); notify("Se limpiaron los filtros.");
  }
  function openModal(title, description) {
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-description").textContent = description;
    modal.hidden = false;
  }
  function closeModal() { modal.hidden = true; }

  document.getElementById("apply-filters").addEventListener("click", () => { currentPage = 1; render(); notify("Filtros aplicados a tus tickets."); });
  document.getElementById("clear-filters").addEventListener("click", clearFilters);
  document.getElementById("empty-clear").addEventListener("click", clearFilters);
  document.getElementById("ticket-search").addEventListener("input", () => { currentPage = 1; render(); });
  document.getElementById("global-search").addEventListener("keydown", event => {
    if (event.key === "Enter" && event.target.value.trim()) {
      document.getElementById("ticket-search").value = event.target.value.trim();
      currentPage = 1; render(); notify("Búsqueda aplicada a tus tickets.");
    }
  });
  tbody.addEventListener("click", event => {
    const button = event.target.closest("button"); if (!button) return;
    const row = button.closest("tr");
    if (button.classList.contains("view-ticket")) {
      openModal(`Detalle de ${row.dataset.id}`, `Asunto: ${row.dataset.subject}\nDescripción: ${row.dataset.description}\nCategoría: ${row.dataset.category}\nPrioridad: ${row.dataset.priority}\nEstado: ${row.dataset.status}\nTécnico asignado: ${row.dataset.technician}\nFecha de creación: ${row.dataset.date}`);
    } else if (button.classList.contains("more-action")) {
      openModal(`Seguimiento · ${row.dataset.id}`, `Estado actual: ${row.dataset.status}\nTécnico: ${row.dataset.technician}\n\nEn la versión funcional aquí se podrá consultar el historial y las respuestas del equipo de soporte.`);
    }
  });
  document.querySelectorAll(".recent-item").forEach(item => item.addEventListener("click", () => {
    const row = rows.find(candidate => candidate.dataset.id === item.dataset.ticket);
    if (row) openModal(`Detalle de ${row.dataset.id}`, `Asunto: ${row.dataset.subject}\nEstado: ${row.dataset.status}\nPrioridad: ${row.dataset.priority}\nTécnico: ${row.dataset.technician}`);
  }));
  document.getElementById("view-all-tickets").addEventListener("click", () => {
    clearFilters(); document.querySelector(".tickets-panel").scrollIntoView({behavior:"smooth",block:"start"});
  });
  document.getElementById("notifications-button").addEventListener("click", () => { window.location.href = "notificaciones.html"; });
  document.getElementById("profile-button").addEventListener("click", () => { window.location.href = "perfil.html"; });
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal-confirm").addEventListener("click", closeModal);
  modal.addEventListener("click", event => { if (event.target === modal) closeModal(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeModal(); });
  document.getElementById("prev-page").addEventListener("click", () => { if (currentPage > 1) { currentPage--; render(); } });
  document.getElementById("next-page").addEventListener("click", () => { if (currentPage < Math.ceil(matches().length / pageSize)) { currentPage++; render(); } });
  document.querySelectorAll(".page-number").forEach(btn => btn.addEventListener("click", () => { currentPage = Number(btn.dataset.page); render(); }));
  document.getElementById("resolved-count").textContent = rows.filter(r => r.dataset.status === "Resuelto").length;
  document.getElementById("progress-count").textContent = rows.filter(r => r.dataset.status === "En proceso").length;
  document.getElementById("pending-count").textContent = rows.filter(r => r.dataset.status === "Pendiente").length;
  render();
});