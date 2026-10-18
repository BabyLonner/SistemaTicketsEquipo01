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

  document.getElementById("ticket-properties").addEventListener("submit", (event) => {
    event.preventDefault();
    updateStatusTag(statusSelect.value);
    updatePriorityTag(prioritySelect.value);
    document.getElementById("sla-limit").textContent = prioritySelect.value === "Alta" ? "4 h" : prioritySelect.value === "Media" ? "8 h" : "24 h";
    notify(`Cambios preparados: ${statusSelect.value}, prioridad ${prioritySelect.value}, técnico ${technicianSelect.value}. Falta guardar en el backend.`);
  });

  document.getElementById("quick-status").addEventListener("change", (event) => {
    if (!event.target.value) return;
    statusSelect.value = event.target.value;
    updateStatusTag(event.target.value);
    notify(`Estado cambiado visualmente a: ${event.target.value}. Pulsa “Guardar cambios” para confirmar en la interfaz.`);
    event.target.value = "";
  });

  document.getElementById("close-ticket").addEventListener("click", () => {
    statusSelect.value = "Cerrado";
    updateStatusTag("Cerrado");
    notify("El ticket aparece como cerrado. Este cambio aún no se guarda en la base de datos.");
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