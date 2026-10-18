/* Nuevo Ticket: prototipo de interfaz.
   No envía datos a un servidor ni guarda registros permanentemente. */
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("new-ticket-form");
  const subject = document.getElementById("subject");
  const description = document.getElementById("description");
  const category = document.getElementById("category");
  const area = document.getElementById("area");
  const attachmentsInput = document.getElementById("attachments");
  const fileList = document.getElementById("file-list");
  const attachmentCount = document.getElementById("attachment-count");
  const dropzone = document.getElementById("dropzone");
  const toast = document.getElementById("toast");
  const modal = document.getElementById("confirm-modal");
  const summary = document.getElementById("confirm-summary");
  const allowedExtensions = new Set(["jpg", "jpeg", "png", "pdf", "docx"]);
  const maxSize = 10 * 1024 * 1024;
  let selectedFiles = [];
  let toastTimer;

  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
  }

  function extensionOf(fileName) {
    return fileName.includes(".") ? fileName.split(".").pop().toLowerCase() : "";
  }

  function formatSize(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function renderFiles() {
    fileList.replaceChildren();
    selectedFiles.forEach((file, index) => {
      const chip = document.createElement("div");
      chip.className = "file-chip";
      const thumb = document.createElement("span");
      thumb.className = "file-thumb";
      thumb.textContent = file.type.startsWith("image/") ? "▧" : file.type === "application/pdf" ? "PDF" : "▤";
      if (file.type.startsWith("image/")) {
        const img = document.createElement("img");
        img.alt = "";
        img.src = URL.createObjectURL(file);
        thumb.replaceChildren(img);
      }
      const details = document.createElement("span");
      details.className = "file-details";
      const name = document.createElement("strong");
      name.textContent = file.name;
      const size = document.createElement("small");
      size.textContent = formatSize(file.size);
      details.append(name, size);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-file";
      remove.setAttribute("aria-label", `Quitar ${file.name}`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        selectedFiles.splice(index, 1);
        renderFiles();
      });
      chip.append(thumb, details, remove);
      fileList.append(chip);
    });
    attachmentCount.textContent = `${selectedFiles.length} ${selectedFiles.length === 1 ? "archivo" : "archivos"}`;
    document.getElementById("attachments-error").textContent = "";
  }

  function addFiles(fileCollection) {
    const incoming = [...fileCollection];
    let added = 0;
    incoming.forEach((file) => {
      const ext = extensionOf(file.name);
      if (!allowedExtensions.has(ext)) {
        notify(`${file.name}: formato no permitido.`);
        return;
      }
      if (file.size > maxSize) {
        notify(`${file.name}: supera el límite de 10 MB.`);
        return;
      }
      if (selectedFiles.some((existing) => existing.name === file.name && existing.size === file.size)) return;
      selectedFiles.push(file);
      added++;
    });
    renderFiles();
    if (added) notify(`${added} archivo(s) añadido(s) a la vista.`);
  }

  description.addEventListener("input", () => {
    document.getElementById("description-count").textContent = `${description.value.length}/1000`;
    document.getElementById("description-error").textContent = "";
  });
  subject.addEventListener("input", () => document.getElementById("subject-error").textContent = "");
  category.addEventListener("change", () => document.getElementById("category-error").textContent = "");
  area.addEventListener("change", () => document.getElementById("area-error").textContent = "");

  document.querySelectorAll('input[name="priority"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".priority-option").forEach((option) => {
        option.classList.toggle("selected", option.contains(radio) && radio.checked);
      });
    });
  });

  attachmentsInput.addEventListener("change", () => {
    addFiles(attachmentsInput.files);
    attachmentsInput.value = "";
  });
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("drag-over");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag-over");
    if (event.dataTransfer?.files?.length) addFiles(event.dataTransfer.files);
  });

  document.querySelectorAll(".example-item").forEach((button) => {
    button.addEventListener("click", () => {
      subject.value = button.dataset.subject || "";
      description.value = button.dataset.description || "";
      document.getElementById("description-count").textContent = `${description.value.length}/1000`;
      document.getElementById("subject-error").textContent = "";
      document.getElementById("description-error").textContent = "";
      subject.focus();
      notify("Ejemplo cargado. Puedes editarlo antes de continuar.");
      if (window.matchMedia("(max-width: 1100px)").matches) {
        document.querySelector(".form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = {
      subject: subject.value.trim(),
      description: description.value.trim(),
      category: category.value,
      area: area.value,
      priority: form.querySelector('input[name="priority"]:checked')?.value || ""
    };
    let valid = true;
    const errors = {
      subject: document.getElementById("subject-error"),
      description: document.getElementById("description-error"),
      category: document.getElementById("category-error"),
      area: document.getElementById("area-error")
    };
    Object.values(errors).forEach((element) => element.textContent = "");
    if (!values.subject) { errors.subject.textContent = "Ingresa un asunto para la incidencia."; valid = false; }
    if (!values.description) { errors.description.textContent = "Describe el problema para que TI pueda ayudarte."; valid = false; }
    if (!values.category) { errors.category.textContent = "Selecciona una categoría."; valid = false; }
    if (!values.area) { errors.area.textContent = "Selecciona tu área."; valid = false; }
    if (!values.priority) { notify("Selecciona una prioridad."); valid = false; }
    if (!valid) {
      form.querySelector(".field-error:not(:empty)")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    summary.textContent = `Asunto: ${values.subject}\nCategoría: ${values.category} · Área: ${values.area}\nPrioridad: ${values.priority}\nArchivos adjuntos: ${selectedFiles.length}\n\nEste es un prototipo visual: el ticket no se enviará ni guardará en ningún sistema.`;
    modal.hidden = false;
  });

  document.getElementById("edit-ticket").addEventListener("click", () => modal.hidden = true);
  document.getElementById("finish-preview").addEventListener("click", () => {
    modal.hidden = true;
    notify("Vista previa finalizada. No se ha creado ningún ticket.");
  });

  document.getElementById("cancel-button").addEventListener("click", () => {
    if (subject.value || description.value || category.value || area.value || selectedFiles.length) {
      const shouldClear = window.confirm("¿Quieres limpiar los datos ingresados en el formulario?");
      if (!shouldClear) return;
    }
    form.reset();
    selectedFiles = [];
    renderFiles();
    document.getElementById("description-count").textContent = "0/1000";
    document.querySelectorAll(".field-error").forEach((element) => element.textContent = "");
    document.querySelectorAll(".priority-option").forEach((option) => option.classList.remove("selected"));
    document.querySelector('.priority-option-medium').classList.add("selected");
    notify("Formulario limpiado.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  document.getElementById("global-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.value.trim()) {
      event.preventDefault();
      notify("La búsqueda global se conectará cuando trabajemos la lógica del sistema.");
    }
  });
  document.querySelector(".notification").addEventListener("click", () => notify("Las notificaciones se implementarán en la siguiente etapa."));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") modal.hidden = true;
  });
});