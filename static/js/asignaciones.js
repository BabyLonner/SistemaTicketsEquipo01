/* Asignaciones: interacciones de demostración. No guarda cambios en servidor ni base de datos. */
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("tickets-tbody");
  const rows = [...tbody.querySelectorAll("tr")];
  const toast = document.getElementById("toast");
  const modal = document.getElementById("assignment-modal");
  const form = document.getElementById("assignment-form");
  const ticketSelect = document.getElementById("ticket-select");
  const technicianSelect = document.getElementById("technician-select");
  const prioritySelect = document.getElementById("assignment-priority");
  const noteField = document.getElementById("assignment-note");
  const selectAll = document.getElementById("select-all");
  let toastTimer;
  let activeRow = null;
  let currentState = "all";
  let currentPage = 1;
  const pageSize = 10;

  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
  }
  function normalize(value) {
    return (value || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }
  function initials(name) {
    return name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  }
  function statusClass(status) {
    return ({ "Pendiente": "pending", "Asignado": "assigned", "En proceso": "progress", "Resuelto": "resolved", "Vencido": "overdue" })[status] || "pending";
  }
  function updateStats() {
    const active = rows.filter((row) => !row.dataset.hiddenForever);
    document.getElementById("pending-count").textContent = active.filter((row) => row.dataset.status === "Pendiente").length;
    document.getElementById("assigned-count").textContent = active.filter((row) => row.dataset.status === "Asignado").length;
    document.getElementById("progress-count").textContent = active.filter((row) => row.dataset.status === "En proceso").length;
    document.getElementById("overdue-count").textContent = active.filter((row) => row.dataset.status === "Vencido").length;
  }
  function updateWorkload() {
    const counts = {};
    rows.forEach((row) => {
      const tech = row.dataset.technician;
      if (tech && tech !== "Sin asignar" && row.dataset.status !== "Resuelto") counts[tech] = (counts[tech] || 0) + 1;
    });
    document.querySelectorAll(".workload-item").forEach((item) => {
      const tech = item.dataset.tech;
      const count = counts[tech] || 0;
      const max = 10;
      item.querySelector(".workload-number").innerHTML = `<b>${count}</b> / ${max}`;
      item.querySelector(".progress-track span").style.width = `${Math.min(100, count / max * 100)}%`;
    });
  }
  function getMatches() {
    const query = normalize(document.getElementById("ticket-search").value.trim());
    const priority = document.getElementById("priority-filter").value;
    const category = document.getElementById("category-filter").value;
    const tech = document.getElementById("technician-filter").value;
    const status = document.getElementById("status-filter").value;
    return rows.filter((row) => {
      if (row.dataset.hiddenForever) return false;
      const searchText = normalize(`${row.dataset.id} ${row.dataset.subject} ${row.dataset.requester}`);
      if (query && !searchText.includes(query)) return false;
      if (currentState !== "all" && row.dataset.status !== currentState) return false;
      if (priority && row.dataset.priority !== priority) return false;
      if (category && row.dataset.category !== category) return false;
      if (tech && row.dataset.technician !== tech) return false;
      if (status && row.dataset.status !== status) return false;
      return true;
    });
  }
  function render() {
    const matches = getMatches();
    const totalPages = Math.max(1, Math.ceil(matches.length / pageSize));
    currentPage = Math.min(currentPage, totalPages);
    const start = (currentPage - 1) * pageSize;
    const visible = new Set(matches.slice(start, start + pageSize));
    rows.forEach((row) => {
      row.hidden = !visible.has(row);
      if (!visible.has(row)) row.querySelector(".row-check").checked = false;
    });
    document.getElementById("results-label").textContent = `Mostrando ${Math.min(pageSize, Math.max(0, matches.length - start))} de ${matches.length} tickets`;
    document.querySelectorAll(".page-number").forEach((button) => {
      button.hidden = Number(button.dataset.page) > totalPages;
      button.classList.toggle("active", Number(button.dataset.page) === currentPage);
    });
    document.getElementById("prev-page").disabled = currentPage <= 1;
    document.getElementById("next-page").disabled = currentPage >= totalPages;
    selectAll.checked = false;
    selectAll.indeterminate = false;
    updateStats();
    updateWorkload();
  }
  function updateTechnicianCell(row) {
    const cell = row.children[6];
    const tech = row.dataset.technician;
    if (!tech || tech === "Sin asignar") {
      cell.innerHTML = '<span class="unassigned">Sin asignar</span>';
      return;
    }
    cell.innerHTML = `<span class="technician-chip"><i>${initials(tech)}</i>${tech}</span>`;
  }
  function updateStatusCell(row) {
    row.children[7].innerHTML = `<span class="status-badge ${statusClass(row.dataset.status)}">${row.dataset.status}</span>`;
  }
  function openModal(title, description, confirmText = "Entendido", row = null) {
    activeRow = row;
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-description").textContent = description;
    document.getElementById("modal-confirm").textContent = confirmText;
    modal.hidden = false;
  }
  function closeModal() { modal.hidden = true; activeRow = null; }
  function openAssignmentFor(row) {
    ticketSelect.value = row.dataset.id;
    technicianSelect.value = row.dataset.technician === "Sin asignar" ? "" : row.dataset.technician;
    prioritySelect.value = row.dataset.priority;
    noteField.value = "";
    document.getElementById("note-count").textContent = "0";
    form.scrollIntoView({ behavior: "smooth", block: "center" });
    technicianSelect.focus({ preventScroll: true });
    notify(`Formulario preparado para el ticket ${row.dataset.id}.`);
  }

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      currentState = tab.dataset.state;
      currentPage = 1;
      document.querySelectorAll(".tab").forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
      render();
    });
  });
  document.getElementById("apply-filters").addEventListener("click", () => {
    currentPage = 1;
    render();
    notify("Filtros aplicados a los tickets de ejemplo.");
  });
  document.getElementById("clear-filters").addEventListener("click", () => {
    document.getElementById("ticket-search").value = "";
    ["priority-filter", "category-filter", "technician-filter", "status-filter"].forEach((id) => document.getElementById(id).value = "");
    currentState = "all";
    currentPage = 1;
    document.querySelectorAll(".tab").forEach((tab) => {
      const active = tab.dataset.state === "all";
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    render();
    notify("Filtros limpiados.");
  });
  document.getElementById("ticket-search").addEventListener("input", () => { currentPage = 1; render(); });
  selectAll.addEventListener("change", () => {
    rows.filter((row) => !row.hidden).forEach((row) => row.querySelector(".row-check").checked = selectAll.checked);
  });
  tbody.addEventListener("change", (event) => {
    if (!event.target.classList.contains("row-check")) return;
    const checks = rows.filter((row) => !row.hidden).map((row) => row.querySelector(".row-check"));
    const selected = checks.filter((check) => check.checked).length;
    selectAll.checked = checks.length > 0 && selected === checks.length;
    selectAll.indeterminate = selected > 0 && selected < checks.length;
  });
  tbody.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const row = button.closest("tr");
    if (button.classList.contains("edit-assignment")) openAssignmentFor(row);
    if (button.classList.contains("more-action")) {
      openModal(`Ticket ${row.dataset.id}`, `Asunto: ${row.dataset.subject}\nSolicitante: ${row.dataset.requester}\nTécnico: ${row.dataset.technician}\nPrioridad: ${row.dataset.priority}\nEstado: ${row.dataset.status}\nFecha límite: ${row.dataset.due.replace("T", " ")}`, "Cerrar", row);
    }
  });

  noteField.addEventListener("input", () => document.getElementById("note-count").textContent = noteField.value.length);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const ticketId = ticketSelect.value;
    const tech = technicianSelect.value;
    document.getElementById("ticket-error").textContent = "";
    document.getElementById("technician-error").textContent = "";
    let valid = true;
    if (!ticketId) { document.getElementById("ticket-error").textContent = "Selecciona un ticket."; valid = false; }
    if (!tech) { document.getElementById("technician-error").textContent = "Selecciona un técnico."; valid = false; }
    if (!valid) return;
    const row = rows.find((item) => item.dataset.id === ticketId);
    if (!row) { notify("No se encontró el ticket de ejemplo."); return; }
    const previousTech = row.dataset.technician;
    row.dataset.technician = tech;
    row.dataset.priority = prioritySelect.value;
    if (row.dataset.status === "Pendiente") row.dataset.status = "Asignado";
    updateTechnicianCell(row);
    updateStatusCell(row);
    row.querySelector(".row-check").checked = false;
    render();
    notify(`Ticket ${ticketId} asignado visualmente a ${tech}.`);
    openModal("Asignación realizada", `Ticket: ${ticketId}\nTécnico: ${tech}\nPrioridad: ${prioritySelect.value}${noteField.value.trim() ? "\nObservaciones: " + noteField.value.trim() : ""}\n\nEste cambio solo se mantiene en esta página de demostración.`, "Entendido");
    if (previousTech !== tech) updateWorkload();
  });

  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal-confirm").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });
  document.getElementById("global-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.value.trim()) {
      event.preventDefault();
      document.getElementById("ticket-search").value = event.target.value.trim();
      currentPage = 1;
      render();
      notify("Búsqueda aplicada a las asignaciones.");
    }
  });
  document.querySelector(".top-notification").addEventListener("click", () => {
    window.location.href = "notificaciones.html";
  });
  document.getElementById("prev-page").addEventListener("click", () => { if (currentPage > 1) { currentPage--; render(); } });
  document.getElementById("next-page").addEventListener("click", () => {
    if (currentPage < Math.ceil(getMatches().length / pageSize)) { currentPage++; render(); }
  });
  document.querySelectorAll(".page-number").forEach((button) => button.addEventListener("click", () => {
    currentPage = Number(button.dataset.page);
    render();
  }));

  render();
});