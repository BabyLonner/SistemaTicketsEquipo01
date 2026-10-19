/* =========================================================
   MÓDULO 3 — Asignación, estados e historial
   ---------------------------------------------------------
   Interfaz de demostración (HTML + CSS + JS).
   - Asignar / reasignar ticket a un técnico.
   - Cambiar estado (Abierto / En proceso / Resuelto / Cerrado)
     con comentario OBLIGATORIO y transiciones validadas.
   - Línea de tiempo (historial) con fechas relativas.

   Los datos viven en el navegador (localStorage) para que el
   detalle del ticket muestre los mismos cambios. Al conectar con
   Flask, reemplazar las funciones marcadas con "API:".
   ========================================================= */
document.addEventListener("DOMContentLoaded", () => {
  const STORE_KEY = "soporteti_modulo3";
  const CURRENT_USER = { name: "Ana Díaz", role: "Administrador" };
  const TECHNICIANS = [
    { name: "Luis Ramos", specialty: "Servidores y software" },
    { name: "Carla Mendoza", specialty: "Redes y accesos" },
    { name: "Pedro Salazar", specialty: "Hardware e impresoras" }
  ];
  const STATES = ["Abierto", "En proceso", "Resuelto", "Cerrado"];
  /* Transiciones permitidas (la misma regla debe validarse en el UPDATE de Flask) */
  const TRANSITIONS = {
    "Abierto": ["En proceso"],
    "En proceso": ["Resuelto"],
    "Resuelto": ["Cerrado", "En proceso"],
    "Cerrado": []
  };
  const STATE_HINT = {
    "Abierto": "Pendiente de atención",
    "En proceso": "El técnico lo está atendiendo",
    "Resuelto": "Solución aplicada",
    "Cerrado": "Estado final"
  };
  const STATUS_CLASS = { "Abierto": "status-open", "En proceso": "status-progress", "Resuelto": "status-resolved", "Cerrado": "status-closed" };
  const PRIORITY_CLASS = { "Alta": "priority-high", "Media": "priority-medium", "Baja": "priority-low" };
  const MIN_COMMENT = 10;

  /* ---------- Datos de ejemplo (API: GET /api/tickets) ---------- */
  const ago = (min) => new Date(Date.now() - min * 60000).toISOString();
  function seedData() {
    return [
      { code: "TK-2294", subject: "Monitor parpadea constantemente", category: "Hardware", requester: "Diego Ruiz", company: "Grupo M&M", priority: "Baja", status: "Abierto", technician: null,
        history: [{ type: "created", to: "Abierto", by: "Diego Ruiz", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(25) }] },
      { code: "TK-2293", subject: "Sin internet en oficina de contabilidad", category: "Red e internet", requester: "Lucía Campos", company: "Agrofutura", priority: "Alta", status: "Abierto", technician: null,
        history: [{ type: "created", to: "Abierto", by: "Lucía Campos", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(48) }] },
      { code: "TK-2292", subject: "Correo no sincroniza en el celular", category: "Software", requester: "Jorge Paredes", company: "EPSEL", priority: "Media", status: "Abierto", technician: null,
        history: [{ type: "created", to: "Abierto", by: "Jorge Paredes", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(130) }] },
      { code: "TK-2291", subject: "Servidor de facturación caído", category: "Software", requester: "Rosa Villanueva", company: "Ángel Divino Bus", priority: "Alta", status: "En proceso", technician: "Luis Ramos",
        history: [
          { type: "created", to: "Abierto", by: "Rosa Villanueva", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(400) },
          { type: "assign", tech: "Luis Ramos", by: "Juan Pérez", role: "Administrador", comment: "Se asigna a Luis por ser responsable de los servidores.", at: ago(375) },
          { type: "status", from: "Abierto", to: "En proceso", by: "Luis Ramos", role: "Técnico", comment: "Revisando los logs del servidor. Parece un fallo en el servicio de base de datos.", at: ago(345) }
        ] },
      { code: "TK-2290", subject: "VPN no conecta desde almacén", category: "Red e internet", requester: "Carlos Méndez", company: "EPSEL", priority: "Alta", status: "En proceso", technician: "Carla Mendoza",
        history: [
          { type: "created", to: "Abierto", by: "Carlos Méndez", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(230) },
          { type: "assign", tech: "Carla Mendoza", by: "Ana Díaz", role: "Administrador", comment: "Asignado al área de redes.", at: ago(215) },
          { type: "status", from: "Abierto", to: "En proceso", by: "Carla Mendoza", role: "Técnico", comment: "Verificando certificados del cliente VPN en el equipo del almacén.", at: ago(190) }
        ] },
      { code: "TK-2289", subject: "Laptop no enciende", category: "Hardware", requester: "María López", company: "Grupo M&M", priority: "Media", status: "En proceso", technician: "Pedro Salazar",
        history: [
          { type: "created", to: "Abierto", by: "María López", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(1500) },
          { type: "assign", tech: "Pedro Salazar", by: "Ana Díaz", role: "Administrador", comment: "Revisión física del equipo.", at: ago(1460) },
          { type: "status", from: "Abierto", to: "En proceso", by: "Pedro Salazar", role: "Técnico", comment: "Se retiró la laptop para revisar la fuente de poder.", at: ago(1400) }
        ] },
      { code: "TK-2288", subject: "Impresora no imprime", category: "Impresoras", requester: "Juan Torres", company: "Agrofutura", priority: "Media", status: "Resuelto", technician: "Luis Ramos",
        history: [
          { type: "created", to: "Abierto", by: "Juan Torres", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(3000) },
          { type: "assign", tech: "Luis Ramos", by: "Ana Díaz", role: "Administrador", comment: "Asignado por disponibilidad.", at: ago(2950) },
          { type: "status", from: "Abierto", to: "En proceso", by: "Luis Ramos", role: "Técnico", comment: "Se revisa la cola de impresión del servidor.", at: ago(2900) },
          { type: "status", from: "En proceso", to: "Resuelto", by: "Luis Ramos", role: "Técnico", comment: "Se reinstaló el controlador y se limpió la cola. Impresión de prueba correcta.", at: ago(1700) }
        ] },
      { code: "TK-2287", subject: "Solicita acceso al sistema ERP", category: "Accesos y cuentas", requester: "Ana Torres", company: "Robotic Air Systems", priority: "Baja", status: "Cerrado", technician: "Carla Mendoza",
        history: [
          { type: "created", to: "Abierto", by: "Ana Torres", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(7300) },
          { type: "assign", tech: "Carla Mendoza", by: "Juan Pérez", role: "Administrador", comment: "Gestión de accesos.", at: ago(7200) },
          { type: "status", from: "Abierto", to: "En proceso", by: "Carla Mendoza", role: "Técnico", comment: "Se solicitó la aprobación del jefe de área.", at: ago(7100) },
          { type: "status", from: "En proceso", to: "Resuelto", by: "Carla Mendoza", role: "Técnico", comment: "Usuario creado con perfil de consulta.", at: ago(5900) },
          { type: "status", from: "Resuelto", to: "Cerrado", by: "Carla Mendoza", role: "Técnico", comment: "La usuaria confirmó que ya ingresa al ERP.", at: ago(4400) }
        ] }
    ];
  }

  function loadTickets() {
    let saved = [];
    try {
      const parsed = JSON.parse(localStorage.getItem(STORE_KEY));
      if (Array.isArray(parsed)) saved = parsed;
    } catch (e) { /* sin localStorage */ }
    /* Combina lo guardado (p. ej. cambios hechos en el detalle) con los datos de ejemplo */
    const seed = seedData();
    return seed.map((t) => saved.find((s) => s.code === t.code) || t)
      .concat(saved.filter((s) => !seed.some((t) => t.code === s.code)));
  }
  function saveTickets() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(tickets)); } catch (e) { /* sin localStorage */ }
  }

  let tickets = loadTickets();
  saveTickets();

  /* ---------- Utilidades ---------- */
  const $ = (id) => document.getElementById(id);
  const toast = $("toast");
  let toastTimer;
  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
  }
  const escapeHTML = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const initials = (name) => name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  const findTicket = (code) => tickets.find((t) => t.code === code);
  const lastUpdate = (t) => t.history[t.history.length - 1];
  const activeLoad = (tech) => tickets.filter((t) => t.technician === tech && (t.status === "Abierto" || t.status === "En proceso")).length;

  /* Fecha relativa: "hace 5 min", "hace 2 h", "ayer", ... */
  function relativeTime(iso) {
    const diff = Math.max(0, Date.now() - new Date(iso).getTime());
    const min = Math.floor(diff / 60000);
    if (min < 1) return "hace un momento";
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `hace ${h} h`;
    const d = Math.floor(h / 24);
    if (d === 1) return "ayer";
    if (d < 7) return `hace ${d} días`;
    return absoluteTime(iso).split(" ")[0];
  }
  function absoluteTime(iso) {
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  /* Texto e icono de cada evento del historial */
  function describe(entry) {
    switch (entry.type) {
      case "created": return { icon: "＋", cls: "t-open", title: "Ticket creado · estado inicial Abierto" };
      case "assign": return { icon: "♙", cls: "t-assign", title: `Asignado a ${entry.tech}` };
      case "reassign": return { icon: "⇄", cls: "t-assign", title: `Reasignado de ${entry.fromTech} a ${entry.tech}` };
      case "status": {
        const reopen = entry.from === "Resuelto" && entry.to === "En proceso";
        return { icon: { "En proceso": "⟳", "Resuelto": "✓", "Cerrado": "■", "Abierto": "!" }[entry.to] || "●",
          cls: { "Abierto": "t-open", "En proceso": "t-progress", "Resuelto": "t-resolved", "Cerrado": "t-closed" }[entry.to],
          title: reopen ? "Ticket reabierto · Resuelto → En proceso" : `Estado: ${entry.from} → ${entry.to}` };
      }
      default: return { icon: "●", cls: "", title: "Actualización" };
    }
  }

  function timelineItem(entry, code) {
    const info = describe(entry);
    const li = document.createElement("li");
    li.className = "tl-item";
    li.innerHTML = `
      <span class="tl-icon ${info.cls}" aria-hidden="true">${info.icon}</span>
      <div class="tl-body">
        <div class="tl-title">${code ? `<a href="#" data-history="${escapeHTML(code)}">${escapeHTML(code)}</a> · ` : ""}${escapeHTML(info.title)}</div>
        <div class="tl-meta"><span>${escapeHTML(entry.by)} (${escapeHTML(entry.role)})</span><time datetime="${entry.at}" title="${absoluteTime(entry.at)}" data-relative>${relativeTime(entry.at)}</time></div>
        ${entry.comment ? `<p class="tl-comment">${escapeHTML(entry.comment)}</p>` : ""}
      </div>`;
    return li;
  }

  /* ---------- Render: tabla ---------- */
  const body = $("assign-body");
  const search = $("assign-search");
  const statusFilter = $("assign-status-filter");
  const techFilter = $("assign-tech-filter");
  let view = "todos";

  function renderTable() {
    const q = search.value.trim().toLocaleLowerCase("es");
    const rows = tickets.filter((t) => {
      const text = `${t.code} ${t.subject} ${t.requester}`.toLocaleLowerCase("es");
      if (q && !text.includes(q)) return false;
      if (statusFilter.value && t.status !== statusFilter.value) return false;
      if (techFilter.value === "Sin asignar" && t.technician) return false;
      if (techFilter.value && techFilter.value !== "Sin asignar" && t.technician !== techFilter.value) return false;
      if (view === "sin-asignar" && t.technician) return false;
      if (view === "activos" && !(t.status === "Abierto" || t.status === "En proceso")) return false;
      return true;
    });

    body.innerHTML = rows.map((t) => {
      const last = lastUpdate(t);
      const canAssign = t.status === "Abierto" || t.status === "En proceso";
      const canChange = TRANSITIONS[t.status].length > 0;
      const tech = t.technician
        ? `<div class="tech-cell"><span class="tech-avatar">${initials(t.technician)}</span>${escapeHTML(t.technician)}</div>`
        : `<span class="tech-none"><i></i>Sin asignar</span>`;
      return `<tr class="${t.technician ? "" : "unassigned"}" data-code="${t.code}">
        <td><a class="ticket-code" href="detalle_ticket.html">${t.code}</a></td>
        <td class="subject-cell"><strong title="${escapeHTML(t.subject)}">${escapeHTML(t.subject)}</strong><small>${escapeHTML(t.requester)} · ${escapeHTML(t.company)}</small></td>
        <td><span class="badge ${PRIORITY_CLASS[t.priority]}">${t.priority}</span></td>
        <td><span class="badge ${STATUS_CLASS[t.status]}">${t.status}</span></td>
        <td>${tech}</td>
        <td class="updated"><time datetime="${last.at}" title="${absoluteTime(last.at)}" data-relative>${relativeTime(last.at)}</time><small>${escapeHTML(last.by)}</small></td>
        <td><div class="row-actions">
          <button type="button" class="row-btn ${t.technician ? "" : "primary"}" data-action="assign" ${canAssign ? "" : "disabled title=\"No se puede reasignar un ticket resuelto o cerrado\""}><span>♙</span>${t.technician ? "Reasignar" : "Asignar"}</button>
          <button type="button" class="row-btn icon" data-action="status" title="${canChange ? "Cambiar estado" : "El ticket está cerrado"}" aria-label="Cambiar estado de ${t.code}" ${canChange ? "" : "disabled"}>⟳</button>
          <button type="button" class="row-btn icon" data-action="history" title="Ver historial" aria-label="Ver historial de ${t.code}">◷</button>
        </div></td>
      </tr>`;
    }).join("");

    $("assign-empty").hidden = rows.length > 0;
    $("assign-count").textContent = `Mostrando ${rows.length} de ${tickets.length} tickets`;
  }

  /* ---------- Render: métricas, carga y actividad ---------- */
  function renderMetrics() {
    $("metric-unassigned").textContent = tickets.filter((t) => !t.technician && t.status !== "Cerrado").length;
    $("metric-progress").textContent = tickets.filter((t) => t.status === "En proceso").length;
    $("metric-resolved").textContent = tickets.filter((t) => t.status === "Resuelto").length;
    const today = new Date().toDateString();
    $("metric-changes").textContent = tickets.reduce((n, t) => n + t.history.filter((h) => h.type !== "created" && new Date(h.at).toDateString() === today).length, 0);
    $("tab-unassigned-count").textContent = tickets.filter((t) => !t.technician).length;
  }

  function renderWorkload() {
    const max = Math.max(4, ...TECHNICIANS.map((t) => activeLoad(t.name)));
    $("workload-list").innerHTML = TECHNICIANS.map((tech) => {
      const load = activeLoad(tech.name);
      return `<li class="workload-item">
        <span class="tech-avatar">${initials(tech.name)}</span>
        <div class="workload-info"><strong>${tech.name}</strong><small>${tech.specialty}</small>
          <div class="workload-bar ${load >= 3 ? "high" : ""}"><span style="width:${(load / max) * 100}%"></span></div></div>
        <span class="workload-count" title="Tickets abiertos o en proceso">${load}</span>
      </li>`;
    }).join("");
  }

  function renderActivity() {
    const all = tickets.flatMap((t) => t.history.map((h) => ({ ...h, code: t.code })))
      .sort((a, b) => new Date(b.at) - new Date(a.at)).slice(0, 10);
    const feed = $("activity-feed");
    feed.replaceChildren(...all.map((h) => timelineItem(h, h.code)));
    $("activity-count").textContent = `Últimos ${all.length} movimientos`;
  }

  function renderAll() { renderTable(); renderMetrics(); renderWorkload(); renderActivity(); }

  /* Refresca los textos "hace X min" cada minuto */
  setInterval(() => document.querySelectorAll("[data-relative]").forEach((el) => { el.textContent = relativeTime(el.getAttribute("datetime")); }), 60000);

  /* ---------- Modales ---------- */
  let activeCode = null;
  let lastFocus = null;
  function openModal(modal) {
    lastFocus = document.activeElement;
    modal.hidden = false;
    const first = modal.querySelector("input:not([disabled]), textarea, button.btn-primary");
    if (first) first.focus();
  }
  function closeModal(modal) {
    modal.hidden = true;
    if (lastFocus) lastFocus.focus();
  }
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (e) => { if (e.target === modal || e.target.closest("[data-close]")) closeModal(modal); });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".modal:not([hidden])").forEach(closeModal);
  });

  function setError(id, message, field) {
    $(id).textContent = message;
    if (field) field.setAttribute("aria-invalid", message ? "true" : "false");
  }
  function bindCounter(textarea, counter, errorId) {
    textarea.addEventListener("input", () => {
      $(counter).textContent = textarea.value.length;
      if (textarea.value.trim().length >= MIN_COMMENT) setError(errorId, "", textarea);
    });
  }

  /* ----- Asignar / reasignar ----- */
  const assignModal = $("assign-modal");
  const assignComment = $("assign-comment");
  const autoProgress = $("auto-progress");
  bindCounter(assignComment, "assign-comment-count", "assign-comment-error");

  function updateAssignCommentRule() {
    const t = findTicket(activeCode);
    const required = (t && t.technician) || (t && t.status === "Abierto" && autoProgress.checked);
    $("assign-comment-req").hidden = !required;
    assignComment.dataset.required = required ? "true" : "false";
  }
  autoProgress.addEventListener("change", updateAssignCommentRule);

  function openAssign(code) {
    const t = findTicket(code);
    activeCode = code;
    $("assign-modal-title").textContent = t.technician ? "Reasignar técnico" : "Asignar técnico";
    $("assign-ticket-label").textContent = `${t.code} · ${t.subject}`;
    const legend = $("tech-options").querySelector("legend");
    $("tech-options").replaceChildren(legend, ...TECHNICIANS.map((tech) => {
      const load = activeLoad(tech.name);
      const label = document.createElement("label");
      label.className = "option-card";
      label.innerHTML = `<input type="radio" name="tech" value="${tech.name}" ${tech.name === t.technician ? "checked" : ""}>
        <span class="tech-avatar">${initials(tech.name)}</span>
        <span><strong>${tech.name} ${tech.name === t.technician ? '<span class="current-tag">· actual</span>' : ""}</strong><small>${tech.specialty}</small></span>
        <span class="load ${load >= 3 ? "high" : ""}">${load} activo${load === 1 ? "" : "s"}</span>`;
      return label;
    }));
    $("auto-progress-row").hidden = t.status !== "Abierto";
    autoProgress.checked = true;
    assignComment.value = "";
    $("assign-comment-count").textContent = "0";
    setError("assign-tech-error", "");
    setError("assign-comment-error", "", assignComment);
    updateAssignCommentRule();
    openModal(assignModal);
  }

  $("assign-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = findTicket(activeCode);
    const chosen = assignModal.querySelector('input[name="tech"]:checked');
    const comment = assignComment.value.trim();
    let ok = true;

    if (!chosen) { setError("assign-tech-error", "Selecciona un técnico."); ok = false; }
    else if (chosen.value === t.technician) { setError("assign-tech-error", `El ticket ya está asignado a ${t.technician}. Elige otro técnico.`); ok = false; }
    else setError("assign-tech-error", "");

    if (assignComment.dataset.required === "true" && comment.length < MIN_COMMENT) {
      setError("assign-comment-error", `El comentario es obligatorio (mínimo ${MIN_COMMENT} caracteres).`, assignComment); ok = false;
    } else setError("assign-comment-error", "", assignComment);
    if (!ok) return;

    /* API: PUT /api/tickets/<code>/asignar  { tecnico, comentario } */
    const now = new Date().toISOString();
    const previous = t.technician;
    t.history.push(previous
      ? { type: "reassign", fromTech: previous, tech: chosen.value, by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at: now }
      : { type: "assign", tech: chosen.value, by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at: now });
    t.technician = chosen.value;

    let extra = "";
    if (t.status === "Abierto" && autoProgress.checked) {
      t.history.push({ type: "status", from: "Abierto", to: "En proceso", by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at: now });
      t.status = "En proceso";
      extra = " y pasó a En proceso";
    }
    saveTickets();
    closeModal(assignModal);
    renderAll();
    flashRow(t.code);
    notify(`${t.code} ${previous ? "reasignado" : "asignado"} a ${t.technician}${extra}.`);
  });

  /* ----- Cambiar estado ----- */
  const statusModal = $("status-modal");
  const statusComment = $("status-comment");
  bindCounter(statusComment, "status-comment-count", "status-comment-error");

  function openStatus(code) {
    const t = findTicket(code);
    activeCode = code;
    $("status-ticket-label").textContent = `${t.code} · ${t.subject}`;
    const current = $("status-current");
    current.textContent = t.status;
    current.className = `badge ${STATUS_CLASS[t.status]}`;
    const preview = $("status-preview");
    preview.textContent = "Selecciona";
    preview.className = "badge category-tag";

    const allowed = TRANSITIONS[t.status];
    const legend = $("status-options").querySelector("legend");
    $("status-options").replaceChildren(legend, ...STATES.filter((s) => s !== t.status).map((state) => {
      let reason = "";
      if (!allowed.includes(state)) reason = "No permitido desde " + t.status;
      else if (state === "En proceso" && !t.technician) reason = "Primero asigna un técnico";
      const label = document.createElement("label");
      label.className = "status-option" + (reason ? " disabled" : "");
      label.innerHTML = `<input type="radio" name="new-status" value="${state}" ${reason ? "disabled" : ""}><span>${state === "En proceso" && t.status === "Resuelto" ? "Reabrir (En proceso)" : state}<small>${reason || STATE_HINT[state]}</small></span>`;
      return label;
    }));
    const enabled = statusModal.querySelectorAll('input[name="new-status"]:not([disabled])');
    if (enabled.length === 1) { enabled[0].checked = true; updatePreview(); }

    statusComment.value = "";
    $("status-comment-count").textContent = "0";
    setError("status-option-error", "");
    setError("status-comment-error", "", statusComment);
    openModal(statusModal);
    statusComment.focus();
  }

  function updatePreview() {
    const chosen = statusModal.querySelector('input[name="new-status"]:checked');
    const preview = $("status-preview");
    preview.textContent = chosen ? chosen.value : "Selecciona";
    preview.className = "badge " + (chosen ? STATUS_CLASS[chosen.value] : "category-tag");
  }
  $("status-options").addEventListener("change", updatePreview);

  $("status-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = findTicket(activeCode);
    const chosen = statusModal.querySelector('input[name="new-status"]:checked');
    const comment = statusComment.value.trim();
    let ok = true;

    if (!chosen) { setError("status-option-error", "Selecciona el nuevo estado."); ok = false; }
    else if (!TRANSITIONS[t.status].includes(chosen.value)) { setError("status-option-error", "Ese cambio de estado no está permitido."); ok = false; }
    else setError("status-option-error", "");

    if (comment.length < MIN_COMMENT) {
      setError("status-comment-error", `El comentario es obligatorio (mínimo ${MIN_COMMENT} caracteres).`, statusComment); ok = false;
    } else setError("status-comment-error", "", statusComment);
    if (!ok) { (chosen ? statusComment : statusModal.querySelector('input[name="new-status"]:not([disabled])') || statusComment).focus(); return; }

    /* API: PUT /api/tickets/<code>/estado  { estado, comentario }  → inserta en ticket_historial */
    const from = t.status;
    t.status = chosen.value;
    t.history.push({ type: "status", from, to: t.status, by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at: new Date().toISOString() });
    saveTickets();
    closeModal(statusModal);
    renderAll();
    flashRow(t.code);
    notify(`${t.code}: ${from} → ${t.status}. Cambio registrado en el historial.`);
  });

  /* ----- Historial ----- */
  const historyModal = $("history-modal");
  function openHistory(code) {
    const t = findTicket(code);
    $("history-ticket-label").textContent = `${t.code} · ${t.subject} · ${t.history.length} movimientos`;
    $("history-timeline").replaceChildren(...[...t.history].reverse().map((h) => timelineItem(h)));
    openModal(historyModal);
  }

  function flashRow(code) {
    const row = body.querySelector(`tr[data-code="${code}"]`);
    if (row) { row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }
  }

  /* ---------- Eventos ---------- */
  body.addEventListener("click", (e) => {
    const button = e.target.closest("[data-action]");
    if (!button || button.disabled) return;
    const code = button.closest("tr").dataset.code;
    if (button.dataset.action === "assign") openAssign(code);
    if (button.dataset.action === "status") openStatus(code);
    if (button.dataset.action === "history") openHistory(code);
  });
  $("activity-feed").addEventListener("click", (e) => {
    const link = e.target.closest("[data-history]");
    if (!link) return;
    e.preventDefault();
    openHistory(link.dataset.history);
  });

  [search, statusFilter, techFilter].forEach((control) => control.addEventListener(control === search ? "input" : "change", renderTable));
  $("assign-reset").addEventListener("click", () => {
    search.value = ""; statusFilter.value = ""; techFilter.value = "";
    renderTable();
    notify("Se limpiaron los filtros.");
  });
  document.querySelectorAll(".quick-tab").forEach((tab) => tab.addEventListener("click", () => {
    view = tab.dataset.view;
    document.querySelectorAll(".quick-tab").forEach((item) => {
      item.classList.toggle("active", item === tab);
      item.setAttribute("aria-selected", String(item === tab));
    });
    renderTable();
  }));
  $("global-search").addEventListener("input", (e) => { search.value = e.target.value; renderTable(); });

  renderAll();
});
