/* =========================================================
   usuarios.js — MÓDULO 1: gestión real de usuarios
   (antes era un prototipo con datos de ejemplo; ahora usa la API)

   GET  /api/usuarios               lista + áreas + dominio de la empresa
   POST /api/usuarios               registrar
   PUT  /api/usuarios/<id>          editar / restablecer contraseña
   POST /api/usuarios/<id>/estado   activar / desactivar
   ========================================================= */
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("users-tbody");
  if (!tbody) return;

  const $ = (id) => document.getElementById(id);
  const search = $("user-search");
  const roleFilter = $("role-filter");
  const companyFilter = $("company-filter");
  const statusFilter = $("status-filter");
  const resultsLabel = $("results-label");
  const selectAll = $("select-all");
  const toast = $("toast");
  const modal = $("user-modal");
  const editForm = $("edit-user-form");
  const POR_PAGINA = 10;

  let usuarios = [];
  let areas = [];
  let dominios = [];
  let miId = null;
  let pagina = 1;
  let usuarioModal = null;
  let modoModal = null;
  let toastTimer;

  /* ---------- utilidades ---------- */
  function notify(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
  }
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const normalize = (v) => (v || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const iniciales = (n) => (n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
  const claseRol = { Administrador: "role-admin", "Técnico": "role-tech", Solicitante: "role-requester" };

  async function api(url, opciones = {}) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...opciones,
    });
    const datos = await res.json().catch(() => ({}));
    if (res.status === 401) { location.href = "/"; throw new Error("sesión"); }
    return { ok: res.ok, datos };
  }

  /* ---------- carga ---------- */
  async function cargar() {
    try {
      const { ok, datos } = await api("/api/usuarios");
      if (!ok) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:#b42318;">${esc(datos.error || "No se pudieron cargar los usuarios.")}</td></tr>`;
        return;
      }
      usuarios = datos.usuarios || [];
      areas = datos.areas || [];
      dominios = datos.dominios || [];
      miId = datos.yo;
      llenarSelects(datos.empresa);
      actualizarContadores();
      aplicarFiltros();
    } catch (e) {
      if (e.message !== "sesión") notify("No se pudo conectar con el servidor.");
    }
  }

  function llenarSelects(empresa) {
    const nombre = empresa ? empresa.nombre : "";
    companyFilter.innerHTML = `<option value="">Todas las empresas</option>` + (nombre ? `<option>${esc(nombre)}</option>` : "");
    $("new-company").innerHTML = nombre ? `<option value="${empresa.id}">${esc(nombre)}</option>` : `<option value="">Sin empresa</option>`;
    const opcionesArea = areas.map((a) => `<option value="${a.id}">${esc(a.nombre)}</option>`).join("");
    $("new-area").innerHTML = `<option value="">Selecciona un área</option>` + opcionesArea;
    $("edit-area").innerHTML = `<option value="">Sin área</option>` + opcionesArea;
    if (dominios.length) $("new-email").placeholder = `nombre.apellido@${dominios[0]}`;
  }

  function actualizarContadores() {
    $("total-users").textContent = usuarios.length;
    $("total-admins").textContent = usuarios.filter((u) => u.rol === "Administrador").length;
    $("total-techs").textContent = usuarios.filter((u) => u.rol === "Técnico").length;
    $("total-requesters").textContent = usuarios.filter((u) => u.rol === "Solicitante").length;
  }

  /* ---------- filtros, tabla y paginación ---------- */
  function filtrados() {
    const query = normalize(search.value.trim());
    return usuarios.filter((u) => {
      const texto = normalize(`${u.nombre} ${u.correo} ${u.empresa} ${u.area || ""}`);
      const estado = u.activo ? "Activo" : "Inactivo";
      return (!query || texto.includes(query))
        && (!roleFilter.value || u.rol === roleFilter.value)
        && (!companyFilter.value || u.empresa === companyFilter.value)
        && (!statusFilter.value || estado === statusFilter.value);
    });
  }

  function fila(u) {
    const [fecha, hora] = (u.created_at || "— ").split(" ");
    const activo = u.activo;
    return `
      <tr data-id="${u.id}">
        <td><input class="row-check" type="checkbox" aria-label="Seleccionar ${esc(u.nombre)}"></td>
        <td><div class="user-cell"><span class="user-avatar">${esc(iniciales(u.nombre))}</span>
          <div><strong>${esc(u.nombre)}</strong><small>${esc(u.correo)}</small></div></div></td>
        <td><span class="role-badge ${claseRol[u.rol] || ""}">${esc(u.rol)}</span></td>
        <td>${esc(u.empresa)}</td>
        <td>${esc(u.area || "—")}</td>
        <td><span class="status-badge ${activo ? "active" : "inactive"}"><i></i>${activo ? "Activo" : "Inactivo"}</span></td>
        <td>${esc(fecha)}<br><small>${esc(hora || "")}</small></td>
        <td><div class="row-actions"><button type="button" class="icon-button edit-user"
            aria-label="Editar ${esc(u.nombre)}" title="Editar">✎</button><button type="button"
            class="icon-button more-user" aria-label="Activar o desactivar a ${esc(u.nombre)}"
            title="${activo ? "Desactivar" : "Activar"}">···</button></div></td>
      </tr>`;
  }

  function aplicarFiltros(volverAlInicio = true) {
    if (volverAlInicio) pagina = 1;
    const lista = filtrados();
    const paginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA));
    pagina = Math.min(pagina, paginas);
    const inicio = (pagina - 1) * POR_PAGINA;
    const visibles = lista.slice(inicio, inicio + POR_PAGINA);
    tbody.innerHTML = visibles.length
      ? visibles.map(fila).join("")
      : `<tr><td colspan="8" style="text-align:center;padding:24px;color:#58749a;">No hay usuarios que coincidan con los filtros.</td></tr>`;
    resultsLabel.textContent = lista.length
      ? `Mostrando ${inicio + 1}–${Math.min(inicio + POR_PAGINA, lista.length)} de ${lista.length} usuarios`
      : "Mostrando 0 usuarios";
    selectAll.checked = false;
    selectAll.indeterminate = false;
    paginacion(paginas);
  }

  function paginacion(paginas) {
    const cont = document.querySelector(".table-footer .pagination");
    if (!cont) return;
    let html = `<button type="button" id="previous-page" aria-label="Página anterior" ${pagina === 1 ? "disabled" : ""}>‹</button>`;
    for (let i = 1; i <= paginas; i++) {
      html += `<button type="button" class="page-number ${i === pagina ? "active" : ""}" data-page="${i}">${i}</button>`;
    }
    html += `<button type="button" id="next-page" aria-label="Página siguiente" ${pagina === paginas ? "disabled" : ""}>›</button>`;
    cont.innerHTML = html;
    cont.querySelector("#previous-page").addEventListener("click", () => { if (pagina > 1) { pagina--; aplicarFiltros(false); } });
    cont.querySelector("#next-page").addEventListener("click", () => { if (pagina < paginas) { pagina++; aplicarFiltros(false); } });
    cont.querySelectorAll(".page-number").forEach((b) => b.addEventListener("click", () => { pagina = Number(b.dataset.page); aplicarFiltros(false); }));
  }

  search.addEventListener("input", () => aplicarFiltros());
  $("apply-filters").addEventListener("click", () => { aplicarFiltros(); notify(`Filtros aplicados: ${filtrados().length} usuario(s).`); });
  $("reset-filters").addEventListener("click", () => {
    search.value = ""; roleFilter.value = ""; companyFilter.value = ""; statusFilter.value = "";
    aplicarFiltros();
    notify("Filtros limpiados.");
  });
  [roleFilter, companyFilter, statusFilter].forEach((s) => s.addEventListener("change", () => aplicarFiltros()));

  selectAll.addEventListener("change", () => {
    tbody.querySelectorAll(".row-check").forEach((box) => (box.checked = selectAll.checked));
  });
  tbody.addEventListener("change", (event) => {
    if (!event.target.classList.contains("row-check")) return;
    const boxes = [...tbody.querySelectorAll(".row-check")];
    const marcados = boxes.filter((b) => b.checked).length;
    selectAll.checked = boxes.length > 0 && marcados === boxes.length;
    selectAll.indeterminate = marcados > 0 && marcados < boxes.length;
  });

  /* ---------- modal: editar o activar/desactivar ---------- */
  function limpiarErrores(prefijo) {
    document.querySelectorAll(`[id^="${prefijo}"][id$="-error"]`).forEach((e) => (e.textContent = ""));
  }

  function abrirModal(usuario, modo) {
    usuarioModal = usuario;
    modoModal = modo;
    limpiarErrores("edit-");
    if (modo === "edit") {
      $("modal-title").textContent = `Editar usuario: ${usuario.nombre}`;
      $("modal-description").textContent = `Empresa: ${usuario.empresa} · Último acceso: ${usuario.ultimo_acceso || "nunca"}`;
      $("edit-name").value = usuario.nombre;
      $("edit-email").value = usuario.correo;
      $("edit-role").value = usuario.rol;
      $("edit-role").disabled = usuario.id === miId;
      $("edit-area").value = usuario.area_id || "";
      $("edit-password").value = "";
      editForm.hidden = false;
      $("confirm-modal").textContent = "Guardar cambios";
    } else {
      $("modal-title").textContent = `${usuario.activo ? "Desactivar" : "Activar"} a ${usuario.nombre}`;
      $("modal-description").textContent = usuario.activo
        ? `${usuario.nombre} ya no podrá iniciar sesión hasta que lo vuelvas a activar. Sus tickets e historial se conservan.`
        : `${usuario.nombre} podrá volver a iniciar sesión con su correo ${usuario.correo}.`;
      editForm.hidden = true;
      $("confirm-modal").textContent = usuario.activo ? "Desactivar" : "Activar";
    }
    modal.hidden = false;
  }

  function cerrarModal() { modal.hidden = true; usuarioModal = null; modoModal = null; }

  tbody.addEventListener("click", (event) => {
    const boton = event.target.closest("button");
    if (!boton) return;
    const usuario = usuarios.find((u) => u.id === Number(boton.closest("tr").dataset.id));
    if (!usuario) return;
    if (boton.classList.contains("edit-user")) abrirModal(usuario, "edit");
    if (boton.classList.contains("more-user")) {
      if (usuario.id === miId) { notify("No puedes desactivar tu propia cuenta."); return; }
      abrirModal(usuario, "estado");
    }
  });

  $("close-modal").addEventListener("click", cerrarModal);
  $("cancel-modal").addEventListener("click", cerrarModal);
  modal.addEventListener("click", (event) => { if (event.target === modal) cerrarModal(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !modal.hidden) cerrarModal(); });

  function reemplazar(usuario) {
    const i = usuarios.findIndex((u) => u.id === usuario.id);
    if (i >= 0) usuarios[i] = usuario; else usuarios.push(usuario);
    actualizarContadores();
    aplicarFiltros(false);
  }

  function mostrarErrores(prefijo, errores, mapa) {
    Object.entries(errores || {}).forEach(([campo, msg]) => {
      const el = $(`${prefijo}-${mapa[campo] || campo}-error`);
      if (el) el.textContent = msg;
    });
  }

  $("confirm-modal").addEventListener("click", async () => {
    if (!usuarioModal) { cerrarModal(); return; }
    const boton = $("confirm-modal");
    boton.disabled = true;
    try {
      if (modoModal === "edit") {
        limpiarErrores("edit-");
        const cuerpo = {
          nombre: $("edit-name").value, correo: $("edit-email").value, rol: $("edit-role").value,
          area_id: $("edit-area").value || null, clave: $("edit-password").value,
        };
        const { ok, datos } = await api(`/api/usuarios/${usuarioModal.id}`, { method: "PUT", body: JSON.stringify(cuerpo) });
        if (!ok) {
          mostrarErrores("edit", datos.errores, { nombre: "name", correo: "email", rol: "role", clave: "password" });
          notify(datos.error || "No se pudo guardar.");
          return;
        }
        reemplazar(datos.usuario);
        notify(datos.mensaje);
      } else {
        const { ok, datos } = await api(`/api/usuarios/${usuarioModal.id}/estado`, { method: "POST" });
        if (!ok) { notify(datos.error || "No se pudo cambiar el estado."); return; }
        reemplazar(datos.usuario);
        notify(datos.mensaje);
      }
      cerrarModal();
    } finally {
      boton.disabled = false;
    }
  });

  /* ---------- registrar usuario ---------- */
  const createForm = $("create-user-form");
  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    limpiarErrores("new-");
    const campos = [
      ["new-name", "Ingresa el nombre completo."], ["new-email", "Ingresa un correo corporativo válido."],
      ["new-password", "Escribe una contraseña temporal."], ["new-role", "Selecciona un rol."],
    ];
    let valido = true;
    campos.forEach(([id, msg]) => {
      if (!$(id).value.trim()) { $(`${id}-error`).textContent = msg; valido = false; }
    });
    if (!valido) return;
    const boton = createForm.querySelector("button[type=submit]");
    boton.disabled = true;
    try {
      const cuerpo = {
        nombre: $("new-name").value, correo: $("new-email").value, clave: $("new-password").value,
        rol: $("new-role").value, area_id: $("new-area").value || null,
      };
      const { ok, datos } = await api("/api/usuarios", { method: "POST", body: JSON.stringify(cuerpo) });
      if (!ok) {
        mostrarErrores("new", datos.errores, { nombre: "name", correo: "email", rol: "role", clave: "password", area_id: "area" });
        notify(datos.error || "No se pudo registrar el usuario.");
        return;
      }
      createForm.reset();
      llenarSelects({ id: datos.usuario.empresa_id, nombre: datos.usuario.empresa });
      reemplazar(datos.usuario);
      notify(`${datos.mensaje} Comparte la contraseña temporal por un canal seguro.`);
    } finally {
      boton.disabled = false;
    }
  });

  /* ---------- buscador de la cabecera ---------- */
  document.querySelector(".global-search input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.value.trim()) {
      event.preventDefault();
      search.value = event.target.value.trim();
      aplicarFiltros();
    }
  });

  cargar();
});
