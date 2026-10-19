/* =========================================================
   nuevo_ticket.js — Tickets: registrar / editar ticket con fotos
   ---------------------------------------------------------
   Requiere: tickets.js (cargado antes)

   nuevo_ticket.html            -> crear ticket (POST /api/tickets)
   nuevo_ticket.html?editar=7   -> editar ticket (PUT /api/tickets/7)
                                   + agregar/quitar fotos

   El solicitante NO se envía: el servidor lo toma del token.
   ========================================================= */
document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);
  const form = $("new-ticket-form");
  const campos = {
    asunto: $("subject"), descripcion: $("description"),
    categoria: $("category"), area: $("area")
  };
  // Nombre del campo en la API -> id del mensaje de error en el HTML
  const ERRORES = {
    asunto: "subject-error", descripcion: "description-error", categoria: "category-error",
    area: "area-error", prioridad: "priority-error", fotos: "attachments-error"
  };
  const MAX = TicketsAPI.MAX_FOTOS;

  const idEditar = (/^\d+$/.test(new URLSearchParams(location.search).get("editar") || ""))
    ? new URLSearchParams(location.search).get("editar") : null;

  let ticketEditando = null; // ticket cargado en modo edición
  let fotosNuevas = [];      // [{ archivo, url, optimizada, pesoOriginal }]
  let enviando = false;

  const avisar = (msg) => Evidencias.avisar(msg);
  const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const iniciales = (nombre) => (nombre || "?").split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

  function mostrarAlerta(html) {
    const alerta = $("alerta-servidor");
    alerta.innerHTML = html;
    alerta.hidden = !html;
  }

  /* =======================================================
     SESIÓN: solicitante automático
     ======================================================= */
  async function cargarSesion() {
    try {
      const { usuario } = await TicketsAPI.sesion();
      $("perfil-nombre").textContent = usuario.nombre;
      $("perfil-rol").textContent = usuario.rol;
      $("perfil-iniciales").textContent = iniciales(usuario.nombre);
      $("solicitante-nombre").textContent = `${usuario.nombre} · ${usuario.correo}`;
      $("solicitante-iniciales").textContent = iniciales(usuario.nombre);
      return true;
    } catch (e) {
      $("solicitante-nombre").textContent = "Sin sesión";
      $("submit-button").disabled = true;
      if (e.estado === 401 || e.estado === 422) {
        mostrarAlerta(`Tu sesión no es válida o expiró. <a href="index.html">Inicia sesión</a> para registrar tickets.`);
      } else if (e.estado === 0 || e.estado === 404 || e.estado === 405) {
        mostrarAlerta(`No se encontró el servidor Flask. Ejecuta <b>python run.py</b> y abre <a href="http://127.0.0.1:5000/nuevo_ticket.html">http://127.0.0.1:5000/nuevo_ticket.html</a>.`);
      } else {
        mostrarAlerta(escapar(e.message));
      }
      return false;
    }
  }

  /* =======================================================
     FOTOS DE EVIDENCIA (máximo 3 por ticket)
     ======================================================= */
  const fotosExistentes = () => (ticketEditando ? ticketEditando.evidencias : []);
  const espaciosLibres = () => MAX - fotosExistentes().length - fotosNuevas.length;

  async function agregarFotos(lista) {
    const errores = [];
    const optimizadas = [];
    let agregadas = 0;
    for (const archivo of lista) {
      if (espaciosLibres() <= 0) {
        errores.push(`Solo se permiten ${MAX} fotos por ticket.`);
        break;
      }
      const repetida = fotosNuevas.some((f) => f.nombreOriginal === archivo.name && f.pesoOriginal === archivo.size);
      if (repetida) continue;
      try {
        const preparada = await TicketsAPI.prepararFoto(archivo);
        fotosNuevas.push({ ...preparada, nombreOriginal: archivo.name, url: URL.createObjectURL(preparada.archivo) });
        agregadas++;
        if (preparada.optimizada) {
          optimizadas.push(`«${archivo.name}» se redujo de ${TicketsAPI.formatearPeso(preparada.pesoOriginal)} a ${TicketsAPI.formatearPeso(preparada.archivo.size)}`);
        }
      } catch (e) {
        errores.push(e.message);
      }
    }
    renderFotos();
    $("attachments-error").textContent = errores.join(" ");
    if (agregadas && !errores.length) {
      avisar(`${agregadas} foto(s) lista(s) para enviar.` + (optimizadas.length ? ` ${optimizadas.join("; ")}.` : ""));
    }
  }

  function quitarFotoNueva(indice) {
    URL.revokeObjectURL(fotosNuevas[indice].url);
    fotosNuevas.splice(indice, 1);
    renderFotos();
  }

  async function quitarFotoExistente(evidenciaId) {
    if (!confirm("¿Quitar esta foto del ticket? Se elimina del servidor y no se puede deshacer.")) return;
    try {
      const r = await TicketsAPI.eliminarEvidencia(ticketEditando.id, evidenciaId);
      ticketEditando = r.ticket;
      renderFotos();
      avisar(r.mensaje);
    } catch (e) {
      avisar(e.message);
    }
  }

  function renderFotos() {
    const cont = $("file-list");
    const existentes = fotosExistentes();
    const html = [];

    existentes.forEach((f) => html.push(`
      <figure class="m2-foto m2-foto--guardada">
        <button type="button" class="m2-foto__img" data-miniatura-url="${escapar(f.miniatura_url)}"
                data-imagen-url="${escapar(f.imagen_url)}" data-nombre="${escapar(f.nombre)}"
                data-galeria="formulario" aria-label="Ampliar ${escapar(f.nombre)}"></button>
        <figcaption><strong title="${escapar(f.nombre)}">${escapar(f.nombre)}</strong><small>Guardada · ${TicketsAPI.formatearPeso(f.tamano_bytes)}</small></figcaption>
        ${ticketEditando.permisos.editar ? `<button type="button" class="m2-foto__quitar" data-quitar-guardada="${f.id}" aria-label="Quitar ${escapar(f.nombre)}">×</button>` : ""}
      </figure>`));

    fotosNuevas.forEach((f, i) => html.push(`
      <figure class="m2-foto">
        <button type="button" class="m2-foto__img" data-imagen-url="${f.url}" data-nombre="${escapar(f.archivo.name)}"
                data-galeria="formulario" aria-label="Ampliar ${escapar(f.archivo.name)}"><img src="${f.url}" alt=""></button>
        <figcaption><strong title="${escapar(f.archivo.name)}">${escapar(f.archivo.name)}</strong>
          <small>${TicketsAPI.formatearPeso(f.archivo.size)}${f.optimizada ? " · optimizada" : ""} · por subir</small></figcaption>
        <button type="button" class="m2-foto__quitar" data-quitar-nueva="${i}" aria-label="Quitar ${escapar(f.archivo.name)}">×</button>
      </figure>`));

    for (let n = existentes.length + fotosNuevas.length; n < MAX; n++) {
      html.push(`<label class="m2-foto m2-foto--vacia" for="attachments"><span>＋</span><small>Foto ${n + 1}</small></label>`);
    }
    cont.innerHTML = html.join("");

    const total = existentes.length + fotosNuevas.length;
    $("attachment-count").textContent = `${total} de ${MAX} fotos`;
    $("dropzone").classList.toggle("m2-dropzone--llena", total >= MAX);
    $("attachments").disabled = total >= MAX;
  }

  $("file-list").addEventListener("click", (e) => {
    const nueva = e.target.closest("[data-quitar-nueva]");
    const guardada = e.target.closest("[data-quitar-guardada]");
    if (nueva) quitarFotoNueva(Number(nueva.dataset.quitarNueva));
    if (guardada) quitarFotoExistente(guardada.dataset.quitarGuardada);
  });

  const input = $("attachments");
  const dropzone = $("dropzone");
  input.addEventListener("change", () => { agregarFotos([...input.files]); input.value = ""; });
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  ["dragover", "dragenter"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.remove("drag-over")));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files?.length) agregarFotos([...e.dataTransfer.files]);
  });
  // Pegar una captura de pantalla (Impr Pant + Ctrl+V)
  document.addEventListener("paste", (e) => {
    const imagenes = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (!imagenes.length) return;
    e.preventDefault();
    const extension = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" };
    agregarFotos(imagenes.map((f, i) => new File([f], `captura-${Date.now()}-${i + 1}.${extension[f.type] || "png"}`, { type: f.type })));
  });

  /* =======================================================
     VALIDACIÓN DEL FORMULARIO (la misma regla que en Flask)
     ======================================================= */
  function leerValores() {
    return {
      asunto: campos.asunto.value.trim(),
      descripcion: campos.descripcion.value.trim(),
      categoria: campos.categoria.value,
      area: campos.area.value,
      prioridad: form.querySelector('input[name="prioridad"]:checked')?.value || ""
    };
  }

  function validar(v) {
    const errores = {};
    if (v.asunto.length < 5) errores.asunto = "El asunto debe tener al menos 5 caracteres.";
    if (v.descripcion.length < 10) errores.descripcion = "Describe el problema (mínimo 10 caracteres).";
    if (!v.categoria) errores.categoria = "Selecciona una categoría.";
    if (!v.area) errores.area = "Selecciona tu área.";
    if (!v.prioridad) errores.prioridad = "Selecciona una prioridad.";
    return errores;
  }

  function limpiarErrores() {
    Object.values(ERRORES).forEach((id) => { $(id).textContent = ""; });
    form.querySelectorAll(".m2-invalido").forEach((el) => el.classList.remove("m2-invalido"));
  }

  function pintarErrores(errores) {
    Object.entries(errores).forEach(([campo, mensaje]) => {
      if (ERRORES[campo]) $(ERRORES[campo]).textContent = mensaje;
      campos[campo]?.classList.add("m2-invalido");
    });
    form.querySelector(".field-error:not(:empty)")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  Object.entries(campos).forEach(([nombre, el]) => {
    el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => {
      $(ERRORES[nombre]).textContent = "";
      el.classList.remove("m2-invalido");
    });
  });
  campos.descripcion.addEventListener("input", actualizarContador);
  function actualizarContador() {
    $("description-count").textContent = `${campos.descripcion.value.length}/1000`;
  }

  document.querySelectorAll('input[name="prioridad"]').forEach((radio) => {
    radio.addEventListener("change", marcarPrioridad);
  });
  function marcarPrioridad() {
    document.querySelectorAll(".priority-option").forEach((op) => {
      op.classList.toggle("selected", op.querySelector("input").checked);
    });
    $("priority-error").textContent = "";
  }

  /* =======================================================
     ENVÍO
     ======================================================= */
  function bloquear(estado, texto) {
    enviando = estado;
    $("submit-button").disabled = estado;
    $("submit-text").textContent = texto;
  }

  function progreso(porcentaje) {
    const barra = $("progreso-envio");
    barra.hidden = porcentaje === null;
    if (porcentaje !== null) {
      barra.querySelector("i").style.width = `${porcentaje}%`;
      barra.querySelector("span").textContent = porcentaje < 100 ? `Subiendo… ${porcentaje}%` : "Procesando fotos en el servidor…";
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (enviando) return;
    limpiarErrores();
    const valores = leerValores();
    const errores = validar(valores);
    if (Object.keys(errores).length) return pintarErrores(errores);

    if (ticketEditando) return guardarEdicion(valores);

    const datos = new FormData();
    Object.entries(valores).forEach(([k, v]) => datos.append(k, v));
    fotosNuevas.forEach((f) => datos.append("fotos", f.archivo));

    bloquear(true, "Enviando…");
    progreso(fotosNuevas.length ? 0 : null);
    try {
      const r = await TicketsAPI.crear(datos, fotosNuevas.length ? progreso : null);
      mostrarConfirmacion(r.ticket);
      reiniciarFormulario();
      cargarRecientes();
    } catch (err) {
      manejarError(err);
    } finally {
      progreso(null);
      bloquear(false, "Enviar Ticket");
    }
  });

  async function guardarEdicion(valores) {
    bloquear(true, "Guardando…");
    try {
      let r = await TicketsAPI.actualizar(ticketEditando.id, valores);
      if (fotosNuevas.length) {
        const datos = new FormData();
        fotosNuevas.forEach((f) => datos.append("fotos", f.archivo));
        progreso(0);
        r = await TicketsAPI.agregarEvidencias(ticketEditando.id, datos, progreso);
        fotosNuevas.forEach((f) => URL.revokeObjectURL(f.url));
        fotosNuevas = [];
      }
      ticketEditando = r.ticket;
      renderFotos();
      cargarRecientes();
      avisar(`Cambios guardados en ${ticketEditando.codigo}.`);
    } catch (err) {
      manejarError(err);
    } finally {
      progreso(null);
      bloquear(false, "Guardar cambios");
    }
  }

  function manejarError(err) {
    if (Object.keys(err.errores || {}).length) pintarErrores(err.errores);
    if (err.estado === 401) {
      mostrarAlerta(`Tu sesión expiró. <a href="index.html">Vuelve a iniciar sesión</a>; no cierres esta pestaña para no perder lo escrito.`);
    }
    avisar(err.message);
  }

  function mostrarConfirmacion(t) {
    $("confirm-title").textContent = `Ticket ${t.codigo} registrado`;
    $("confirm-summary").textContent =
      `${t.asunto}\n${t.categoria} · ${t.area} · Prioridad ${t.prioridad}\n` +
      `Solicitante: ${t.solicitante} · Estado: ${t.estado}\n` +
      (t.evidencias.length ? `${t.evidencias.length} foto(s) de evidencia guardada(s).` : "Sin fotos de evidencia.");
    $("confirm-photos").innerHTML = t.evidencias.map((f) =>
      `<button type="button" class="m2-mini m2-mini--grande" data-miniatura-url="${escapar(f.miniatura_url)}"
               data-imagen-url="${escapar(f.imagen_url)}" data-nombre="${escapar(f.nombre)}"
               data-galeria="confirmacion" aria-label="Ver ${escapar(f.nombre)}"></button>`).join("");
    $("view-detail").href = `detalle_ticket.html?id=${t.id}`;
    $("confirm-modal").hidden = false;
    $("view-detail").focus();
  }

  function reiniciarFormulario() {
    form.reset();
    fotosNuevas.forEach((f) => URL.revokeObjectURL(f.url));
    fotosNuevas = [];
    limpiarErrores();
    actualizarContador();
    marcarPrioridad();
    renderFotos();
  }

  $("new-another").addEventListener("click", () => {
    $("confirm-modal").hidden = true;
    campos.asunto.focus();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("confirm-modal").hidden && document.querySelector(".m2-visor")?.hidden !== false) {
      $("confirm-modal").hidden = true;
    }
  });

  $("cancel-button").addEventListener("click", () => {
    if (ticketEditando) { location.href = `detalle_ticket.html?id=${ticketEditando.id}`; return; }
    const v = leerValores();
    if ((v.asunto || v.descripcion || v.categoria || v.area || fotosNuevas.length) &&
        !confirm("¿Quieres limpiar los datos ingresados en el formulario?")) return;
    reiniciarFormulario();
    avisar("Formulario limpiado.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  $("delete-button").addEventListener("click", async () => {
    if (!ticketEditando) return;
    if (!confirm(`¿Eliminar el ticket ${ticketEditando.codigo} y todas sus fotos? Esta acción no se puede deshacer.`)) return;
    try {
      const r = await TicketsAPI.eliminar(ticketEditando.id);
      avisar(r.mensaje);
      setTimeout(() => { location.href = "nuevo_ticket.html"; }, 900);
    } catch (e) {
      avisar(e.message);
    }
  });

  /* =======================================================
     MODO EDICIÓN  (?editar=ID)
     ======================================================= */
  async function cargarParaEditar(id) {
    try {
      const { ticket } = await TicketsAPI.obtener(id);
      ticketEditando = ticket;
      $("titulo-pagina").textContent = `Editar ticket ${ticket.codigo}`;
      $("subtitulo-pagina").textContent = ticket.permisos.editar
        ? "Puedes corregir los datos y las fotos mientras el ticket siga «Abierto»."
        : `Este ticket está «${ticket.estado}»; solo puedes agregar fotos.`;
      document.title = `Editar ${ticket.codigo} | Soporte TI`;
      campos.asunto.value = ticket.asunto;
      campos.descripcion.value = ticket.descripcion;
      campos.categoria.value = ticket.categoria;
      campos.area.value = ticket.area;
      form.querySelector(`input[name="prioridad"][value="${ticket.prioridad}"]`).checked = true;
      marcarPrioridad();
      actualizarContador();
      $("solicitante-nombre").textContent = ticket.solicitante;
      $("solicitante-iniciales").textContent = iniciales(ticket.solicitante);
      Object.values(campos).forEach((c) => { c.disabled = !ticket.permisos.editar; });
      form.querySelectorAll('input[name="prioridad"]').forEach((r) => { r.disabled = !ticket.permisos.editar; });
      $("submit-text").textContent = "Guardar cambios";
      $("cancel-button").textContent = "Volver al detalle";
      $("delete-button").hidden = !ticket.permisos.editar;
      renderFotos();
    } catch (e) {
      mostrarAlerta(`${escapar(e.message)} <a href="nuevo_ticket.html">Registrar un ticket nuevo</a>.`);
      $("submit-button").disabled = true;
    }
  }

  /* =======================================================
     MIS TICKETS RECIENTES (miniatura en listado)
     ======================================================= */
  async function cargarRecientes() {
    const lista = $("recent-tickets");
    try {
      const { tickets } = await TicketsAPI.listar({ mios: 1, limite: 5 });
      if (!tickets.length) {
        lista.innerHTML = `<li class="m2-recientes__vacio">Aún no registraste tickets.</li>`;
        return;
      }
      const claseEstado = { "Abierto": "abierto", "En proceso": "proceso", "Resuelto": "resuelto", "Cerrado": "cerrado" };
      lista.innerHTML = tickets.map((t) => `
        <li class="m2-recientes__item">
          ${Evidencias.miniaturaHTML(t)}
          <a class="m2-recientes__texto" href="detalle_ticket.html?id=${t.id}">
            <strong>${escapar(t.codigo)} · ${escapar(t.asunto)}</strong>
            <small><span class="m2-estado m2-estado--${claseEstado[t.estado] || "abierto"}">${escapar(t.estado)}</span> ${TicketsAPI.formatearFecha(t.created_at)}</small>
          </a>
          ${t.estado === "Abierto" ? `<a class="m2-recientes__editar" href="nuevo_ticket.html?editar=${t.id}" aria-label="Editar ${escapar(t.codigo)}" title="Editar">✎</a>` : ""}
        </li>`).join("");
    } catch (e) {
      lista.innerHTML = `<li class="m2-recientes__vacio">No se pudo cargar: ${escapar(e.message)}</li>`;
    }
  }

  /* Ejemplos: rellenan asunto, descripción y categoría */
  document.querySelectorAll(".example-item").forEach((boton) => {
    boton.addEventListener("click", () => {
      if (ticketEditando) return;
      campos.asunto.value = boton.dataset.subject || "";
      campos.descripcion.value = boton.dataset.description || "";
      if (boton.dataset.category) campos.categoria.value = boton.dataset.category;
      actualizarContador();
      limpiarErrores();
      campos.asunto.focus();
      avisar("Ejemplo cargado. Puedes editarlo antes de enviar.");
      if (window.matchMedia("(max-width: 1100px)").matches) {
        document.querySelector(".form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  /* ---------- Inicio ---------- */
  renderFotos();
  cargarSesion().then((ok) => {
    if (!ok) return;
    cargarRecientes();
    if (idEditar) cargarParaEditar(idEditar);
  });
});
