/* Notificaciones: prototipo visual. Las acciones solo modifican el estado en esta página. */
document.addEventListener("DOMContentLoaded", () => {
  const list = document.getElementById("notification-list");
  const rows = [...list.querySelectorAll(".notification-row")];
  const toast = document.getElementById("toast");
  const emptyState = document.getElementById("empty-state");
  const contextMenu = document.getElementById("context-menu");
  const bulkToolbar = document.getElementById("bulk-toolbar");
  let toastTimer;
  let contextRow = null;
  let currentTab = "all";
  let currentPage = 1;
  const pageSize = 8;

  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
  }

  function markRead(row, read = true) {
    row.dataset.read = String(read);
    row.classList.toggle("unread", !read);
    const dot = row.querySelector(".unread-dot");
    dot.setAttribute("aria-label", read ? "Leída" : "No leída");
    row.querySelector(".notice-menu").setAttribute("aria-label", "Acciones de notificación");
  }

  function updateStats() {
    const activeRows = rows.filter((row) => !row.dataset.deleted);
    const unread = activeRows.filter((row) => row.dataset.read === "false").length;
    const tickets = activeRows.filter((row) => row.dataset.type === "ticket").length;
    const system = activeRows.filter((row) => row.dataset.type === "system").length;
    document.getElementById("total-count").textContent = activeRows.length;
    document.getElementById("unread-count").textContent = unread;
    document.getElementById("ticket-count").textContent = tickets;
    document.getElementById("system-count").textContent = system;
    document.getElementById("top-unread-count").textContent = unread;
    document.getElementById("top-unread-count").parentElement.setAttribute("aria-label", `Notificaciones, ${unread} sin leer`);
    document.getElementById("top-unread-count").hidden = unread === 0;
  }

  function getMatches() {
    const query = normalize(document.getElementById("notification-search").value.trim());
    const type = document.getElementById("type-filter").value;
    const state = document.getElementById("state-filter").value;
    const date = document.getElementById("date-filter").value;
    const sort = document.getElementById("sort-order").value;
    const now = new Date("2026-08-03T11:00:00");
    let matches = rows.filter((row) => {
      if (row.dataset.deleted) return false;
      const text = normalize(`${row.dataset.title} ${row.dataset.description}`);
      if (query && !text.includes(query)) return false;
      if (currentTab === "unread" && row.dataset.read !== "false") return false;
      if (currentTab !== "all" && currentTab !== "unread" && row.dataset.type !== currentTab) return false;
      if (type && row.dataset.type !== type) return false;
      if (state === "unread" && row.dataset.read !== "false") return false;
      if (state === "read" && row.dataset.read !== "true") return false;
      if (date) {
        const age = now - new Date(row.dataset.time);
        const limit = date === "today" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
        if (age < 0 || age > limit) return false;
      }
      return true;
    });
    matches.sort((a, b) => sort === "oldest"
      ? new Date(a.dataset.time) - new Date(b.dataset.time)
      : new Date(b.dataset.time) - new Date(a.dataset.time));
    return matches;
  }

  function updateBulkToolbar() {
    const checked = rows.filter((row) => !row.hidden && row.querySelector(".row-check").checked);
    bulkToolbar.hidden = checked.length === 0;
    document.getElementById("selected-count").textContent = `${checked.length} seleccionada(s)`;
  }

  function render() {
    const matches = getMatches();
    const totalPages = Math.max(1, Math.ceil(matches.length / pageSize));
    currentPage = Math.min(currentPage, totalPages);
    const start = (currentPage - 1) * pageSize;
    const visiblePageRows = new Set(matches.slice(start, start + pageSize));
    rows.forEach((row) => {
      row.hidden = !visiblePageRows.has(row);
      if (!visiblePageRows.has(row)) row.querySelector(".row-check").checked = false;
    });
    emptyState.hidden = matches.length > 0;
    list.hidden = matches.length === 0;
    const shown = Math.min(pageSize, Math.max(0, matches.length - start));
    document.getElementById("results-label").textContent = `Mostrando ${shown} de ${matches.length} notificaciones`;
    document.querySelectorAll(".page-number").forEach((button) => {
      const page = Number(button.dataset.page);
      button.hidden = page > totalPages;
      button.classList.toggle("active", page === currentPage);
    });
    document.getElementById("prev-page").disabled = currentPage <= 1;
    document.getElementById("next-page").disabled = currentPage >= totalPages;
    const visibleChecks = rows.filter((row) => !row.hidden).map((row) => row.querySelector(".row-check"));
    const checkedCount = visibleChecks.filter((box) => box.checked).length;
    document.querySelector(".notification-panel .row-check")?.setAttribute("aria-label", "Seleccionar notificación");
    updateBulkToolbar();
    updateStats();
  }

  function normalize(value) {
    return (value || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      currentTab = tab.dataset.type;
      currentPage = 1;
      document.querySelectorAll(".tab").forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
      render();
    });
  });

  document.getElementById("notification-search").addEventListener("input", () => { currentPage = 1; render(); });
  document.getElementById("sort-order").addEventListener("change", () => { currentPage = 1; render(); });
  document.getElementById("apply-filters").addEventListener("click", () => {
    currentPage = 1;
    render();
    notify("Filtros aplicados a las notificaciones de ejemplo.");
  });
  document.getElementById("mark-all-read").addEventListener("click", () => {
    rows.filter((row) => !row.dataset.deleted).forEach((row) => markRead(row, true));
    render();
    notify("Todas las notificaciones se marcaron como leídas en esta vista.");
  });

  list.addEventListener("change", (event) => {
    if (event.target.classList.contains("row-check")) updateBulkToolbar();
  });
  document.getElementById("mark-selected-read").addEventListener("click", () => {
    const selected = rows.filter((row) => !row.hidden && row.querySelector(".row-check").checked);
    selected.forEach((row) => { markRead(row, true); row.querySelector(".row-check").checked = false; });
    render();
    notify(`${selected.length} notificación(es) marcada(s) como leída(s).`);
  });
  document.getElementById("delete-selected").addEventListener("click", () => {
    const selected = rows.filter((row) => !row.hidden && row.querySelector(".row-check").checked);
    if (!selected.length) return;
    selected.forEach((row) => { row.dataset.deleted = "true"; row.querySelector(".row-check").checked = false; });
    render();
    notify(`${selected.length} notificación(es) ocultada(s) en esta vista.`);
  });
  document.getElementById("clear-selection").addEventListener("click", () => {
    rows.forEach((row) => row.querySelector(".row-check").checked = false);
    render();
  });

  list.addEventListener("click", (event) => {
    const button = event.target.closest(".notice-menu");
    if (!button) return;
    contextRow = button.closest(".notification-row");
    const rect = button.getBoundingClientRect();
    contextMenu.style.top = `${Math.min(rect.bottom + 3, window.innerHeight - 90)}px`;
    contextMenu.style.left = `${Math.min(rect.left - 145, window.innerWidth - 190)}px`;
    contextMenu.hidden = false;
    contextMenu.querySelector('[data-action="read"]').textContent = contextRow.dataset.read === "true" ? "Marcar como no leída" : "Marcar como leída";
  });
  contextMenu.addEventListener("click", (event) => {
    const action = event.target.closest("button")?.dataset.action;
    if (!action || !contextRow) return;
    if (action === "read") {
      markRead(contextRow, contextRow.dataset.read !== "true");
      notify(contextRow.dataset.read === "true" ? "Notificación marcada como leída." : "Notificación marcada como no leída.");
    } else if (action === "delete") {
      contextRow.dataset.deleted = "true";
      notify("Notificación ocultada en esta vista.");
    }
    contextMenu.hidden = true;
    contextRow = null;
    render();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".notice-menu") && !event.target.closest(".context-menu")) contextMenu.hidden = true;
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") contextMenu.hidden = true; });

  document.querySelectorAll(".toggle-input").forEach((toggle) => {
    toggle.addEventListener("change", () => {
      const name = toggle.closest(".preference-row").querySelector("strong").textContent;
      notify(`${name}: notificaciones ${toggle.checked ? "activadas" : "desactivadas"} en esta vista.`);
      document.getElementById("preferences-note").textContent = "Los cambios de preferencias son temporales y no se guardan.";
    });
  });

  document.getElementById("global-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.value.trim()) {
      event.preventDefault();
      document.getElementById("notification-search").value = event.target.value.trim();
      currentPage = 1;
      render();
      notify("Búsqueda aplicada a las notificaciones.");
    }
  });
  document.querySelector(".top-notification").addEventListener("click", () => {
    currentTab = "unread";
    currentPage = 1;
    document.querySelectorAll(".tab").forEach((tab) => {
      const active = tab.dataset.type === "unread";
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    render();
    notify("Mostrando notificaciones no leídas.");
  });

  document.getElementById("prev-page").addEventListener("click", () => {
    if (currentPage > 1) { currentPage--; render(); }
  });
  document.getElementById("next-page").addEventListener("click", () => {
    const total = getMatches().length;
    if (currentPage < Math.ceil(total / pageSize)) { currentPage++; render(); }
  });
  document.querySelectorAll(".page-number").forEach((button) => button.addEventListener("click", () => {
    currentPage = Number(button.dataset.page);
    render();
  }));

  render();
});