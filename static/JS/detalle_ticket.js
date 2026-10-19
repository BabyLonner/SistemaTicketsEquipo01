/* Detalle del ticket: interacciones de demostración.
   Los cambios son locales a la interfaz; conectar a Flask/API para persistencia. */
document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  let toastTimer;

  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("show"), 2800);
  }

  const statusSelect = document.getElementById("property-status");
  const prioritySelect = document.getElementById("property-priority");
  const categorySelect = document.getElementById("property-category");
  const technicianSelect = document.getElementById("property-technician");
  const statusTag = document.getElementById("ticket-status-tag");
  const priorityTag = document.getElementById("ticket-priority-tag");

  function updateStatusTag(value) {
    statusTag.textContent = value === "En proceso" ? "▤ En proceso" : value;
    statusTag.className = "badge " + ({
      "Abierto": "status-open",
      "En proceso": "status-progress",
      "Resuelto": "status-resolved",
      "Cerrado": "status-closed"
    }[value] || "category-tag");
  }

  function updatePriorityTag(value) {
    priorityTag.textContent = "▥ " + value;
    priorityTag.className = "badge " + ({
      "Alta": "priority-high",
      "Media": "priority-medium",
      "Baja": "priority-low"
    }[value] || "priority-medium");
  }

  /* =========================================================
     MÓDULO 3 — Asignación, estados e historial (detalle)
     - Cada cambio de estado pide comentario obligatorio.
     - Solo se permiten transiciones válidas.
     - La pestaña "Historial" muestra la línea de tiempo con
       fechas relativas. Comparte datos con asignacion.html
       mediante localStorage (demo). API: reemplazar por fetch.
     ========================================================= */
  const STORE_KEY = "soporteti_modulo3";
  const CURRENT_USER = { name: "Juan Pérez", role: "Administrador" };
  const MIN_COMMENT = 10;
  const TRANSITIONS = {
    "Abierto": ["En proceso"],
    "En proceso": ["Resuelto"],
    "Resuelto": ["Cerrado", "En proceso"],
    "Cerrado": []
  };
  const STATUS_CLASS = { "Abierto": "status-open", "En proceso": "status-progress", "Resuelto": "status-resolved", "Cerrado": "status-closed" };
  const ticketCode = document.getElementById("ticket-code").textContent.trim();
  const ago = (min) => new Date(Date.now() - min * 60000).toISOString();

  function loadStore() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE_KEY));
      if (Array.isArray(saved)) return saved;
    } catch (e) { /* sin localStorage */ }
    return [];
  }
  const store = loadStore();
  let ticket = store.find((t) => t.code === ticketCode);
  if (!ticket) {
    /* API: GET /api/tickets/<code>/historial */
    ticket = {
      code: ticketCode, subject: document.getElementById("ticket-subject").textContent.trim(), category: "Software",
      requester: "Rosa Villanueva", company: "Ángel Divino Bus", priority: prioritySelect.value, status: statusSelect.value,
      technician: technicianSelect.value === "Sin asignar" ? null : technicianSelect.value,
      history: [
        { type: "created", to: "Abierto", by: "Rosa Villanueva", role: "Solicitante", comment: "Ticket registrado desde el formulario.", at: ago(400) },
        { type: "assign", tech: "Luis Ramos", by: "Juan Pérez", role: "Administrador", comment: "Se asigna a Luis por ser responsable de los servidores.", at: ago(375) },
        { type: "status", from: "Abierto", to: "En proceso", by: "Luis Ramos", role: "Técnico", comment: "Revisando los logs del servidor. Parece un fallo en el servicio de base de datos.", at: ago(345) }
      ]
    };
    store.push(ticket);
  }
  function saveStore() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); } catch (e) { /* sin localStorage */ }
  }
  saveStore();

  const escapeHTML = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function absoluteTime(iso) {
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function relativeTime(iso) {
    const min = Math.floor(Math.max(0, Date.now() - new Date(iso).getTime()) / 60000);
    if (min < 1) return "hace un momento";
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `hace ${h} h`;
    const d = Math.floor(h / 24);
    if (d === 1) return "ayer";
    if (d < 7) return `hace ${d} días`;
    return absoluteTime(iso).split(" ")[0];
  }
  function describe(entry) {
    if (entry.type === "created") return { icon: "＋", cls: "t-open", title: "Ticket creado · estado inicial Abierto" };
    if (entry.type === "assign") return { icon: "♙", cls: "t-assign", title: `Asignado a ${entry.tech}` };
    if (entry.type === "reassign") return { icon: "⇄", cls: "t-assign", title: `Reasignado de ${entry.fromTech} a ${entry.tech}` };
    const reopen = entry.from === "Resuelto" && entry.to === "En proceso";
    return {
      icon: { "En proceso": "⟳", "Resuelto": "✓", "Cerrado": "■", "Abierto": "!" }[entry.to] || "●",
      cls: { "Abierto": "t-open", "En proceso": "t-progress", "Resuelto": "t-resolved", "Cerrado": "t-closed" }[entry.to] || "",
      title: reopen ? "Ticket reabierto · Resuelto → En proceso" : `Estado: ${entry.from} → ${entry.to}`
    };
  }

  const timeline = document.getElementById("history-timeline");
  function renderHistory(highlightLast) {
    const items = [...ticket.history].reverse().map((entry, index) => {
      const info = describe(entry);
      const li = document.createElement("li");
      li.className = "tl-item" + (highlightLast && index === 0 ? " is-new" : "");
      li.innerHTML = `<span class="tl-icon ${info.cls}" aria-hidden="true">${info.icon}</span>
        <div class="tl-body"><div class="tl-title">${escapeHTML(info.title)}</div>
          <div class="tl-meta"><span>${escapeHTML(entry.by)} (${escapeHTML(entry.role)})</span><time datetime="${entry.at}" title="${absoluteTime(entry.at)}" data-relative>${relativeTime(entry.at)}</time></div>
          ${entry.comment ? `<p class="tl-comment">${escapeHTML(entry.comment)}</p>` : ""}</div>`;
      return li;
    });
    timeline.replaceChildren(...items);
    document.getElementById("history-count").textContent = `${ticket.history.length} movimientos`;
    document.getElementById("history-tab-count").textContent = ticket.history.length;
  }
  setInterval(() => document.querySelectorAll("[data-relative]").forEach((el) => { el.textContent = relativeTime(el.getAttribute("datetime")); }), 60000);

  function syncControls() {
    statusSelect.value = ticket.status;
    technicianSelect.value = ticket.technician || "Sin asignar";
    updateStatusTag(ticket.status);
  }
  syncControls();
  renderHistory(false);

  function showHistoryTab() {
    const tab = document.querySelector('[data-tab="history"]');
    if (tab) tab.click();
  }

  function recordTechnician(newTech, comment, at) {
    if (newTech === ticket.technician) return false;
    ticket.history.push(ticket.technician
      ? { type: "reassign", fromTech: ticket.technician, tech: newTech, by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at }
      : { type: "assign", tech: newTech, by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at });
    ticket.technician = newTech;
    return true;
  }

  /* ----- Modal de cambio de estado ----- */
  const statusModal = document.getElementById("status-modal");
  const statusComment = document.getElementById("status-comment");
  const commentError = document.getElementById("status-comment-error");
  let pending = null;

  function requestStatusChange(newStatus, newTech) {
    const tech = newTech === undefined ? ticket.technician : newTech;
    if (!newStatus || newStatus === ticket.status) return;
    if (!TRANSITIONS[ticket.status].includes(newStatus)) {
      const allowed = TRANSITIONS[ticket.status];
      notify(allowed.length
        ? `No se puede pasar de ${ticket.status} a ${newStatus}. Desde ${ticket.status} solo se permite: ${allowed.join(" o ")}.`
        : "El ticket está cerrado; ya no admite cambios de estado.");
      syncControls();
      return;
    }
    if (newStatus === "En proceso" && !tech) {
      notify("Primero asigna un técnico para pasar el ticket a En proceso.");
      syncControls();
      return;
    }
    pending = { status: newStatus, tech };
    const from = document.getElementById("modal-status-from");
    const to = document.getElementById("modal-status-to");
    from.textContent = ticket.status; from.className = `badge ${STATUS_CLASS[ticket.status]}`;
    to.textContent = newStatus; to.className = `badge ${STATUS_CLASS[newStatus]}`;
    const extra = document.getElementById("modal-extra");
    extra.hidden = !(tech && tech !== ticket.technician);
    extra.textContent = extra.hidden ? "" : `También se asignará el ticket a ${tech}.`;
    statusComment.value = "";
    statusComment.setAttribute("aria-invalid", "false");
    document.getElementById("status-comment-count").textContent = "0";
    commentError.textContent = "";
    statusModal.hidden = false;
    statusComment.focus();
  }

  function closeStatusModal() {
    statusModal.hidden = true;
    pending = null;
    syncControls();
  }
  statusModal.addEventListener("click", (event) => {
    if (event.target === statusModal || event.target.closest("[data-close]")) closeStatusModal();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !statusModal.hidden) closeStatusModal(); });
  statusComment.addEventListener("input", () => {
    document.getElementById("status-comment-count").textContent = statusComment.value.length;
    if (statusComment.value.trim().length >= MIN_COMMENT) { commentError.textContent = ""; statusComment.setAttribute("aria-invalid", "false"); }
  });

  document.getElementById("status-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const comment = statusComment.value.trim();
    if (comment.length < MIN_COMMENT) {
      commentError.textContent = `El comentario es obligatorio (mínimo ${MIN_COMMENT} caracteres).`;
      statusComment.setAttribute("aria-invalid", "true");
      statusComment.focus();
      return;
    }
    /* API: PUT /api/tickets/<code>/estado  { estado, comentario } → INSERT en ticket_historial */
    const at = new Date().toISOString();
    if (pending.tech) recordTechnician(pending.tech, comment, at);
    const from = ticket.status;
    ticket.status = pending.status;
    ticket.history.push({ type: "status", from, to: ticket.status, by: CURRENT_USER.name, role: CURRENT_USER.role, comment, at });
    saveStore();
    statusModal.hidden = true;
    pending = null;
    syncControls();
    renderHistory(true);
    showHistoryTab();
    notify(`Estado cambiado: ${from} → ${ticket.status}. Registrado en el historial.`);
  });

  /* ----- Formulario "Estado actual" ----- */
  document.getElementById("ticket-properties").addEventListener("submit", (event) => {
    event.preventDefault();
    updatePriorityTag(prioritySelect.value);
    document.getElementById("sla-limit").textContent = prioritySelect.value === "Alta" ? "4 h" : prioritySelect.value === "Media" ? "8 h" : "24 h";
    const newTech = technicianSelect.value === "Sin asignar" ? null : technicianSelect.value;
    if (!newTech && ticket.technician) {
      notify("Un ticket asignado no puede quedar sin técnico. Elige otro técnico para reasignarlo.");
      technicianSelect.value = ticket.technician;
      return;
    }
    if (statusSelect.value !== ticket.status) {
      requestStatusChange(statusSelect.value, newTech);
      return;
    }
    if (newTech && recordTechnician(newTech, "", new Date().toISOString())) {
      saveStore();
      renderHistory(true);
      notify(`Ticket asignado a ${newTech}. Registrado en el historial.`);
      return;
    }
    notify(`Cambios preparados: prioridad ${prioritySelect.value}, categoría ${categorySelect.value}. Falta guardar en el backend.`);
  });

  document.getElementById("quick-status").addEventListener("change", (event) => {
    const value = event.target.value;
    event.target.value = "";
    requestStatusChange(value);
  });

  document.getElementById("close-ticket").addEventListener("click", () => {
    if (ticket.status === "Cerrado") { notify("El ticket ya está cerrado."); return; }
    if (ticket.status !== "Resuelto") { notify("Para cerrar el ticket primero debe estar en estado Resuelto."); return; }
    requestStatusChange("Cerrado");
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => {
        item.classList.toggle("active", item === tab);
        item.setAttribute("aria-selected", String(item === tab));
      });
      document.querySelectorAll(".tab-content").forEach((content) => content.hidden = true);
      const panel = document.getElementById(`tab-${tab.dataset.tab}`);
      if (panel) panel.hidden = false;
    });
  });

  document.getElementById("reply-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("reply-text");
    const message = input.value.trim();
    if (!message) return;
    const comment = document.createElement("article");
    comment.className = "comment";
    comment.innerHTML = `<span class="comment-avatar avatar-admin">JP</span><div class="comment-body"><div class="comment-meta"><strong>Juan Pérez <small>(Administrador)</small></strong><time>Ahora</time></div><p></p></div>`;
    comment.querySelector("p").textContent = message;
    document.getElementById("conversation-list").appendChild(comment);
    input.value = "";
    notify("Comentario añadido a la vista. Para guardarlo permanentemente, conecta el endpoint de comentarios.");
  });

  document.querySelectorAll('[data-action="reply"]').forEach((button) => button.addEventListener("click", () => {
    document.getElementById("reply-text").focus();
    document.getElementById("tab-conversation").scrollIntoView({ behavior: "smooth", block: "center" });
  }));
  document.querySelector('[data-action="task"]').addEventListener("click", () => {
    document.querySelector('[data-tab="tasks"]').click();
    document.getElementById("task-text").focus();
  });
  document.querySelector('[data-action="assign"]').addEventListener("click", () => {
    technicianSelect.focus();
    technicianSelect.scrollIntoView({ behavior: "smooth", block: "center" });
    notify("Selecciona el técnico y pulsa “Guardar cambios”.");
  });

  document.getElementById("task-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("task-text");
    const task = input.value.trim();
    if (!task) return;
    const item = document.createElement("li");
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    label.append(checkbox, document.createTextNode(" " + task));
    const status = document.createElement("span");
    status.textContent = "Pendiente";
    checkbox.addEventListener("change", () => status.textContent = checkbox.checked ? "Completada" : "Pendiente");
    item.append(label, status);
    document.getElementById("task-list").appendChild(item);
    input.value = "";
    notify("Tarea añadida a la vista.");
  });

  const evidenceInput = document.getElementById("evidence-input");
  evidenceInput.addEventListener("change", () => {
    const files = [...evidenceInput.files];
    const grid = document.getElementById("evidence-grid");
    files.forEach((file) => {
      if (file.size > 10 * 1024 * 1024) {
        notify(`${file.name} supera el límite de 10 MB.`);
        return;
      }
      const card = document.createElement("article");
      card.className = "evidence-card";
      const preview = document.createElement("button");
      preview.type = "button";
      preview.className = "evidence-preview";
      preview.setAttribute("aria-label", `Vista previa de ${file.name}`);
      preview.textContent = file.type.startsWith("image/") ? "▧ Vista previa" : "📄 Archivo adjunto";
      const name = document.createElement("div");
      name.className = "evidence-name";
      name.textContent = file.name;
      card.append(preview, name);
      grid.insertBefore(card, grid.querySelector(".upload-zone"));
      preview.addEventListener("click", () => openPreview(preview.cloneNode(true), file.name));
      const fileItem = document.createElement("li");
      fileItem.textContent = "▧ ";
      const fileName = document.createElement("span");
      fileName.textContent = file.name;
      const fileInfo = document.createElement("small");
      fileInfo.textContent = `${Math.max(1, Math.round(file.size / 1024))} KB`;
      fileItem.append(fileName, fileInfo);
      document.getElementById("file-list").appendChild(fileItem);
    });
    document.getElementById("file-count").textContent = `${grid.querySelectorAll(".evidence-card").length} archivos`;
    if (files.length) notify("Archivos añadidos a la vista. Debes conectarlos al backend para almacenarlos.");
    evidenceInput.value = "";
  });

  const modal = document.getElementById("preview-modal");
  const previewContent = document.getElementById("preview-content");
  const previewCaption = document.getElementById("preview-caption");

  function openPreview(node, name) {
    previewContent.replaceChildren(node);
    previewCaption.textContent = name;
    modal.hidden = false;
  }

  document.querySelectorAll("[data-preview]").forEach((button) => {
    button.addEventListener("click", () => openPreview(button.cloneNode(true), button.getAttribute("aria-label").replace("Ver ", "")));
  });
  document.querySelector(".upload-zone").addEventListener("dragover", (event) => {
    event.preventDefault();
    event.currentTarget.classList.add("drag-over");
  });
  document.querySelector(".upload-zone").addEventListener("dragleave", (event) => event.currentTarget.classList.remove("drag-over"));
  document.querySelector(".upload-zone").addEventListener("drop", (event) => {
    event.preventDefault();
    event.currentTarget.classList.remove("drag-over");
    const transfer = event.dataTransfer;
    if (transfer && transfer.files.length) {
      evidenceInput.files = transfer.files;
      evidenceInput.dispatchEvent(new Event("change"));
    }
  });
  document.getElementById("close-preview").addEventListener("click", () => modal.hidden = true);
  modal.addEventListener("click", (event) => { if (event.target === modal) modal.hidden = true; });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") modal.hidden = true; });

  document.getElementById("global-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const query = event.target.value.trim();
      if (query && !document.getElementById("ticket-subject").textContent.toLowerCase().includes(query.toLowerCase()) && !document.getElementById("ticket-code").textContent.toLowerCase().includes(query.toLowerCase())) {
        notify("La búsqueda global necesita conectarse con la API de tickets.");
      }
    }
  });
});