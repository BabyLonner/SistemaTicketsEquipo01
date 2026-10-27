/* Mis Tickets: tickets reales del usuario (GET /api/tickets?mios=1). */
const escMis = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const CLASE_PRIO_MIS = { Alta: "high", Media: "medium", Baja: "low" };
const CLASE_EST_MIS = { Abierto: "pending", "En proceso": "progress", Resuelto: "resolved", Cerrado: "resolved" };

function fechaMis(iso) {
  if (!iso) return ["—", ""];
  const d = new Date(iso);
  return [d.toLocaleDateString("es-PE"), d.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })];
}

async function cargarMisTickets() {
  const tbody = document.getElementById("tickets-tbody");
  const res = await fetch("/api/tickets?mios=1&limite=500", { credentials: "same-origin" });
  if (res.status === 401) { location.href = "/"; return []; }
  const datos = await res.json().catch(() => ({}));
  const tickets = datos.tickets || [];
  tbody.innerHTML = tickets.map((t, i) => {
    const [fecha, hora] = fechaMis(t.created_at);
    const url = `/detalle_ticket?id=${t.id}`;
    return `<tr data-id="${escMis(t.codigo)}" data-subject="${escMis(t.asunto)}" data-description=""
        data-category="${escMis(t.categoria)}" data-priority="${escMis(t.prioridad)}" data-status="${escMis(t.estado)}"
        data-technician="${escMis(t.tecnico || "Sin asignar")}" data-date="${escMis(fecha + " " + hora)}" data-url="${url}">
      <td>${i + 1}</td>
      <td><a class="ticket-code" href="${url}">${escMis(t.codigo)}</a></td>
      <td>${escMis(t.asunto)}</td>
      <td>${escMis(t.categoria)}</td>
      <td><span class="priority ${CLASE_PRIO_MIS[t.prioridad] || ""}">● ${escMis(t.prioridad)}</span></td>
      <td><span class="status ${CLASE_EST_MIS[t.estado] || ""}">● ${escMis(t.estado)}</span></td>
      <td>${escMis(t.tecnico || "Sin asignar")}</td>
      <td>${escMis(fecha)}<br>${escMis(hora)}</td>
      <td><a class="icon-button view-ticket" title="Ver detalle" aria-label="Ver ${escMis(t.codigo)}" href="${url}">◉</a><button
          class="icon-button more-action" title="Más acciones" aria-label="Más acciones ${escMis(t.codigo)}">···</button></td>
    </tr>`;
  }).join("");
  const recientes = document.querySelector(".recent-list");
  if (recientes) {
    recientes.innerHTML = tickets.slice(0, 3).map((t) =>
      `<a class="recent-item text-decoration-none" href="/detalle_ticket?id=${t.id}" data-ticket="${escMis(t.codigo)}"><b>${escMis(t.codigo)}</b><span>${escMis(t.asunto)}</span><small class="status ${CLASE_EST_MIS[t.estado] || ""}">${escMis(t.estado)}</small></a>`
    ).join("") || `<p style="color:#58749a;margin:0">Aún no registraste tickets.</p>`;
  }
  const categorias = [...new Set(tickets.map((t) => t.categoria).filter(Boolean))].sort();
  const selCat = document.getElementById("category-filter");
  if (selCat) selCat.innerHTML = `<option value="">Todas</option>` + categorias.map((c) => `<option>${escMis(c)}</option>`).join("");
  document.getElementById("total-count").textContent = tickets.length;
  return tickets;
}

document.addEventListener("DOMContentLoaded", async () => {
  const tbody = document.getElementById("tickets-tbody");
  if (!tbody) return;
  try { await cargarMisTickets(); } catch (e) { console.error(e); }
  const rows = [...tbody.querySelectorAll("tr[data-id]")];
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
    if (!rows.length) {
      document.getElementById("results-label").textContent = "Aún no registraste tickets";
      document.getElementById("empty-state").hidden = false;
      document.querySelector(".table-wrap").hidden = true;
      return;
    }
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
  document.querySelector(".global-search input")?.addEventListener("keydown", event => {
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
      window.location.href = row.dataset.url;
    }
  });
  document.getElementById("view-all-tickets").addEventListener("click", () => {
    clearFilters(); document.querySelector(".tickets-panel").scrollIntoView({behavior:"smooth",block:"start"});
  });
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
  document.getElementById("pending-count").textContent = rows.filter(r => r.dataset.status === "Abierto").length;
  render();
});