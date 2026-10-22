/* Usuarios: interacciones de demostración para el prototipo visual.
   No persiste información ni se conecta con un servidor. */
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("users-tbody");
  const rows = [...tbody.querySelectorAll("tr")];
  const search = document.getElementById("user-search");
  const roleFilter = document.getElementById("role-filter");
  const companyFilter = document.getElementById("company-filter");
  const statusFilter = document.getElementById("status-filter");
  const resultsLabel = document.getElementById("results-label");
  const selectAll = document.getElementById("select-all");
  const toast = document.getElementById("toast");
  const modal = document.getElementById("user-modal");
  let toastTimer;
  let modalUserRow = null;

  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
  }

  function normalize(value) {
    return (value || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function getVisibleMatches() {
    const query = normalize(search.value.trim());
    return rows.filter((row) => {
      const text = normalize(`${row.dataset.name} ${row.dataset.email} ${row.dataset.company} ${row.dataset.area}`);
      return (!query || text.includes(query))
        && (!roleFilter.value || row.dataset.role === roleFilter.value)
        && (!companyFilter.value || row.dataset.company === companyFilter.value)
        && (!statusFilter.value || row.dataset.status === statusFilter.value);
    });
  }

  function applyFilters(showNotice = false) {
    const matches = getVisibleMatches();
    rows.forEach((row) => { row.hidden = !matches.includes(row); });
    resultsLabel.textContent = `Mostrando ${matches.length} de ${rows.length} usuarios de ejemplo`;
    selectAll.checked = false;
    selectAll.indeterminate = false;
    if (showNotice) notify(`Filtros aplicados: ${matches.length} usuario(s) encontrados.`);
  }

  search.addEventListener("input", () => applyFilters());
  document.getElementById("apply-filters").addEventListener("click", () => applyFilters(true));
  document.getElementById("reset-filters").addEventListener("click", () => {
    search.value = "";
    roleFilter.value = "";
    companyFilter.value = "";
    statusFilter.value = "";
    applyFilters();
    notify("Filtros limpiados.");
  });
  [roleFilter, companyFilter, statusFilter].forEach((select) => select.addEventListener("change", () => applyFilters()));

  function visibleRows() {
    return rows.filter((row) => !row.hidden);
  }
  selectAll.addEventListener("change", () => {
    visibleRows().forEach((row) => row.querySelector(".row-check").checked = selectAll.checked);
  });
  tbody.addEventListener("change", (event) => {
    if (!event.target.classList.contains("row-check")) return;
    const visible = visibleRows().map((row) => row.querySelector(".row-check"));
    const checked = visible.filter((box) => box.checked).length;
    selectAll.checked = visible.length > 0 && checked === visible.length;
    selectAll.indeterminate = checked > 0 && checked < visible.length;
  });

  function openUserModal(row, mode = "edit") {
    modalUserRow = row;
    const name = row.dataset.name;
    document.getElementById("modal-title").textContent = mode === "edit" ? `Editar usuario: ${name}` : `Acciones para ${name}`;
    document.getElementById("modal-description").textContent = mode === "edit"
      ? `Correo: ${row.dataset.email}\nRol: ${row.dataset.role} · Empresa: ${row.dataset.company}\nÁrea: ${row.dataset.area} · Estado: ${row.dataset.status}\n\nEsta ventana es una demostración visual; no se guardarán cambios.`
      : `Usuario: ${name}\nEstado actual: ${row.dataset.status}\n\nPuedes alternar su estado en esta demostración. El cambio no se guardará fuera de esta página.`;
    document.getElementById("confirm-modal").textContent = mode === "edit" ? "Cerrar vista" : (row.dataset.status === "Activo" ? "Marcar inactivo" : "Marcar activo");
    document.getElementById("confirm-modal").dataset.mode = mode;
    modal.hidden = false;
  }

  tbody.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const row = button.closest("tr");
    if (button.classList.contains("edit-user")) openUserModal(row, "edit");
    if (button.classList.contains("more-user")) openUserModal(row, "more");
  });

  function closeModal() { modal.hidden = true; modalUserRow = null; }
  document.getElementById("close-modal").addEventListener("click", closeModal);
  document.getElementById("cancel-modal").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });
  document.getElementById("confirm-modal").addEventListener("click", (event) => {
    if (!modalUserRow) { closeModal(); return; }
    if (event.currentTarget.dataset.mode === "more") {
      modalUserRow.dataset.status = modalUserRow.dataset.status === "Activo" ? "Inactivo" : "Activo";
      const status = modalUserRow.querySelector(".status-badge");
      const active = modalUserRow.dataset.status === "Activo";
      status.className = `status-badge ${active ? "active" : "inactive"}`;
      status.innerHTML = `<i></i>${active ? "Activo" : "Inactivo"}`;
      notify(`Estado de ${modalUserRow.dataset.name} cambiado visualmente a ${active ? "Activo" : "Inactivo"}.`);
      applyFilters();
    } else {
      notify("Vista de edición cerrada. La edición real se implementará más adelante.");
    }
    closeModal();
  });

  const createForm = document.getElementById("create-user-form");
  createForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = document.getElementById("new-name");
    const email = document.getElementById("new-email");
    const role = document.getElementById("new-role");
    const company = document.getElementById("new-company");
    const area = document.getElementById("new-area");
    const fields = [
      [name, "new-name-error", "Ingresa el nombre completo."],
      [email, "new-email-error", "Ingresa un correo corporativo válido."],
      [role, "new-role-error", "Selecciona un rol."],
      [company, "new-company-error", "Selecciona una empresa."]
    ];
    let valid = true;
    fields.forEach(([field, errorId, message]) => {
      const error = document.getElementById(errorId);
      error.textContent = "";
      const invalidEmail = field === email && field.value.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(field.value.trim());
      if (!field.value.trim() || invalidEmail) {
        error.textContent = invalidEmail ? "Escribe un correo válido." : message;
        valid = false;
      }
    });
    if (!valid) {
      createForm.querySelector(".field-error:not(:empty)")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const initials = name.value.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
    const preview = document.createElement("div");
    preview.textContent = `Vista previa: ${name.value.trim()} · ${role.value} · ${company.value}${area.value ? " · " + area.value : ""}`;
    document.getElementById("modal-title").textContent = "Usuario preparado";
    document.getElementById("modal-description").textContent = `${preview.textContent}\nCorreo: ${email.value.trim()}\n\nEste prototipo no crea usuarios de forma permanente.`;
    document.getElementById("confirm-modal").textContent = "Entendido";
    document.getElementById("confirm-modal").dataset.mode = "preview";
    modalUserRow = null;
    modal.hidden = false;
    createForm.dataset.pendingInitials = initials;
  });

  document.getElementById("global-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.value.trim()) {
      event.preventDefault();
      search.value = event.target.value.trim();
      applyFilters();
      notify("Búsqueda aplicada a la lista de usuarios de ejemplo.");
      document.querySelector(".filters-panel").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  document.querySelector(".notification").addEventListener("click", () => notify("Las notificaciones se implementarán en una etapa posterior."));

  document.querySelectorAll(".page-number").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".page-number").forEach((item) => item.classList.toggle("active", item === button));
      notify(`Página ${button.dataset.page} seleccionada en el prototipo visual.`);
    });
  });
  document.getElementById("previous-page").addEventListener("click", () => {
    const active = document.querySelector(".page-number.active");
    const previous = active?.previousElementSibling;
    if (previous?.classList.contains("page-number")) previous.click();
    else notify("Ya estás en la primera página.");
  });
  document.getElementById("next-page").addEventListener("click", () => {
    const active = document.querySelector(".page-number.active");
    const next = active?.nextElementSibling;
    if (next?.classList.contains("page-number")) next.click();
    else notify("Has llegado a la última página de ejemplo.");
  });

  applyFilters();
});