/* =========================================================
   tickets.js — Tickets: registro con evidencias fotográficas
   ---------------------------------------------------------
   Se carga en tickets.html, nuevo_ticket.html y detalle_ticket.html.
     PARTE 1  TicketsAPI  -> llamadas fetch a Flask (token, subida con progreso,
                             validación de imágenes por firma binaria)
     PARTE 2  Evidencias  -> miniaturas, visor con zoom y fotos del detalle
     PARTE 3  Listado     -> tabla de tickets (solo en tickets.html)
   ========================================================= */



/* #########################################################
   PARTE 1 — TicketsAPI
   ######################################################### */
/* =========================================================
   TicketsAPI — cliente de la API de tickets
   ---------------------------------------------------------
   Centraliza las llamadas fetch al backend Flask para que
   las tres pantallas de tickets no repitan código.

   - Usa la sesión del login (cookie de Flask): solo un usuario con
     sesión iniciada puede usar la API y ver las fotos.
   - Las fotos no son públicas: se piden a /api/evidencias/... y se
     muestran con URL.createObjectURL.
   - Incluye la validación de imágenes por firma binaria
     (magic numbers), igual que en el servidor.
   ========================================================= */
const TicketsAPI = (() => {
  const BASE = window.API_BASE || "";

  const MIME_PERMITIDOS = ["image/jpeg", "image/png", "image/webp"];
  const MAX_FOTOS = 3;
  const MAX_BYTES = 5 * 1024 * 1024;

  class ErrorAPI extends Error {
    constructor(mensaje, estado, errores = {}) {
      super(mensaje);
      this.estado = estado;   // código HTTP (0 = sin conexión)
      this.errores = errores; // errores por campo { asunto: "...", fotos: "..." }
    }
  }

  async function pedir(ruta, opciones = {}) {
    let respuesta;
    try {
      respuesta = await fetch(BASE + ruta, { credentials: "same-origin", ...opciones });
    } catch (e) {
      throw new ErrorAPI("No se pudo conectar con el servidor. Verifica que Flask esté en ejecución.", 0);
    }
    const datos = await respuesta.json().catch(() => ({}));
    if (!respuesta.ok) {
      throw new ErrorAPI(datos.error || datos.msg || `Error ${respuesta.status}`, respuesta.status, datos.errores || {});
    }
    return datos;
  }

  /* Envío multipart con barra de progreso (fetch no informa el avance de subida). */
  function enviarConProgreso(ruta, formData, alProgresar) {
    return new Promise((resolver, rechazar) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", BASE + ruta);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && alProgresar) alProgresar(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        let datos = {};
        try { datos = JSON.parse(xhr.responseText); } catch (e) { /* respuesta no JSON */ }
        if (xhr.status >= 200 && xhr.status < 300) resolver(datos);
        else rechazar(new ErrorAPI(datos.error || datos.msg || `Error ${xhr.status}`, xhr.status, datos.errores || {}));
      };
      xhr.onerror = () => rechazar(new ErrorAPI("No se pudo conectar con el servidor.", 0));
      xhr.send(formData);
    });
  }

  /* ---------- Endpoints de tickets ---------- */
  const sesion = () => pedir("/api/tickets/sesion");
  const listar = (filtros = {}) => pedir("/api/tickets?" + new URLSearchParams(filtros));
  const obtener = (id) => pedir(`/api/tickets/${id}`);
  const crear = (formData, alProgresar) => enviarConProgreso("/api/tickets", formData, alProgresar);
  const actualizar = (id, datos) => pedir(`/api/tickets/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos)
  });
  const eliminar = (id) => pedir(`/api/tickets/${id}`, { method: "DELETE" });
  const agregarEvidencias = (id, formData, alProgresar) =>
    enviarConProgreso(`/api/tickets/${id}/evidencias`, formData, alProgresar);
  const eliminarEvidencia = (id, evidenciaId) =>
    pedir(`/api/tickets/${id}/evidencias/${evidenciaId}`, { method: "DELETE" });

  /* ---------- Imágenes protegidas ---------- */
  const cacheImagenes = new Map();
  async function urlImagen(ruta) {
    if (cacheImagenes.has(ruta)) return cacheImagenes.get(ruta);
    const promesa = fetch(BASE + ruta, { credentials: "same-origin" }).then((r) => {
      if (!r.ok) throw new ErrorAPI("No se pudo cargar la imagen.", r.status);
      return r.blob();
    }).then((blob) => URL.createObjectURL(blob));
    cacheImagenes.set(ruta, promesa);
    promesa.catch(() => cacheImagenes.delete(ruta));
    return promesa;
  }

  /* ---------- Validación de imágenes en el navegador ---------- */
  async function detectarMimeReal(archivo) {
    const b = new Uint8Array(await archivo.slice(0, 12).arrayBuffer());
    if (b[0] === 0xFF && b[1] === 0xD8 && b[2] === 0xFF) return "image/jpeg";
    if ([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A].every((v, i) => b[i] === v)) return "image/png";
    const texto = (desde, hasta) => String.fromCharCode(...b.slice(desde, hasta));
    if (texto(0, 4) === "RIFF" && texto(8, 12) === "WEBP") return "image/webp";
    return null;
  }

  /* Si la foto pesa más de 5 MB (típico de celulares), se reduce a 1920 px en JPEG. */
  async function optimizarSiEsGrande(archivo) {
    if (archivo.size <= MAX_BYTES) return archivo;
    const bitmap = await createImageBitmap(archivo);
    const escala = Math.min(1, 1920 / Math.max(bitmap.width, bitmap.height));
    const lienzo = document.createElement("canvas");
    lienzo.width = Math.round(bitmap.width * escala);
    lienzo.height = Math.round(bitmap.height * escala);
    const ctx = lienzo.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, lienzo.width, lienzo.height);
    ctx.drawImage(bitmap, 0, 0, lienzo.width, lienzo.height);
    bitmap.close();
    const blob = await new Promise((ok) => lienzo.toBlob(ok, "image/jpeg", 0.85));
    const nombre = archivo.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], nombre, { type: "image/jpeg" });
  }

  /* Devuelve { archivo, optimizada } listo para enviar, o lanza Error con el motivo. */
  async function prepararFoto(archivo) {
    const extension = (archivo.name.split(".").pop() || "").toLowerCase();
    if (!["jpg", "jpeg", "png", "webp"].includes(extension)) {
      throw new Error(`«${archivo.name}»: solo se permiten imágenes JPG, PNG o WEBP.`);
    }
    const mimeReal = await detectarMimeReal(archivo);
    if (!mimeReal) {
      throw new Error(`«${archivo.name}»: el contenido no es una imagen real.`);
    }
    // Se reempaqueta con el MIME real, por si el sistema operativo no lo informa
    let lista = new File([archivo], archivo.name, { type: mimeReal });
    let optimizada = false;
    if (lista.size > MAX_BYTES) {
      try {
        lista = await optimizarSiEsGrande(lista);
        optimizada = true;
      } catch (e) {
        throw new Error(`«${archivo.name}»: supera 5 MB y no se pudo optimizar.`);
      }
      if (lista.size > MAX_BYTES) throw new Error(`«${archivo.name}»: supera el máximo de 5 MB.`);
    }
    return { archivo: lista, optimizada, pesoOriginal: archivo.size };
  }

  function formatearPeso(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatearFecha(iso) {
    if (!iso) return "—";
    const fecha = new Date(iso);
    return fecha.toLocaleString("es-PE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  /* Muestra en la barra superior el usuario de la sesión (si la página tiene .profile) */
  async function pintarPerfil() {
    try {
      const { usuario } = await sesion();
      const ini = usuario.nombre.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
      const avatar = document.querySelector(".profile .avatar");
      const nombre = document.querySelector(".profile-copy strong");
      const rol = document.querySelector(".profile-copy small");
      if (avatar) avatar.textContent = ini;
      if (nombre) nombre.textContent = usuario.nombre;
      if (rol) rol.textContent = usuario.rol;
      return usuario;
    } catch (e) {
      return null;
    }
  }

  return {
    ErrorAPI, pintarPerfil, MIME_PERMITIDOS, MAX_FOTOS, MAX_BYTES,
    sesion, listar, obtener, crear, actualizar, eliminar,
    agregarEvidencias, eliminarEvidencia, urlImagen,
    detectarMimeReal, prepararFoto, formatearPeso, formatearFecha
  };
})();


/* #########################################################
   PARTE 2 — Evidencias
   ######################################################### */
/* =========================================================
   Evidencias — fotos de evidencia en las pantallas de tickets
   ---------------------------------------------------------
   Usa TicketsAPI (parte 1)

   1) Miniaturas automáticas: cualquier elemento con
        data-miniatura-url="/api/evidencias/5/miniatura"
        data-imagen-url="/api/evidencias/5/imagen"
      muestra la miniatura y, al hacer clic, abre el visor.
      En el listado (tickets.html) basta con generar la celda así:
        celda.innerHTML = Evidencias.miniaturaHTML(ticket);

   2) Visor con zoom: rueda del mouse, botones + / −, doble clic,
      arrastrar para mover, flechas ← → entre fotos, Esc para cerrar.

   3) Detalle del ticket (detalle_ticket.html?id=7): reemplaza el
      panel de evidencias de ejemplo por las fotos reales del ticket
      y permite agregar/quitar fotos según los permisos.
   ========================================================= */
const Evidencias = (() => {
  const escapar = (texto) => String(texto ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function avisar(mensaje) {
    const toast = document.getElementById("toast");
    if (!toast) return alert(mensaje);
    toast.textContent = mensaje;
    toast.classList.add("show");
    clearTimeout(avisar.t);
    avisar.t = setTimeout(() => toast.classList.remove("show"), 3200);
  }

  /* =======================================================
     VISOR (imagen completa con zoom)
     ======================================================= */
  const Visor = (() => {
    let raiz, img, titulo, contador, etiquetaZoom, enlaceDescarga;
    let fotos = [], indice = 0;
    let escala = 1, x = 0, y = 0, arrastre = null;
    let focoPrevio = null;

    function construir() {
      raiz = document.createElement("div");
      raiz.className = "m2-visor";
      raiz.hidden = true;
      raiz.setAttribute("role", "dialog");
      raiz.setAttribute("aria-modal", "true");
      raiz.setAttribute("aria-label", "Foto de evidencia");
      raiz.innerHTML = `
        <div class="m2-visor__barra">
          <div class="m2-visor__info"><strong class="m2-visor__titulo"></strong><span class="m2-visor__contador"></span></div>
          <div class="m2-visor__acciones">
            <button type="button" data-accion="alejar" aria-label="Alejar">−</button>
            <span class="m2-visor__zoom" aria-live="polite">100%</span>
            <button type="button" data-accion="acercar" aria-label="Acercar">+</button>
            <button type="button" data-accion="ajustar">Ajustar</button>
            <a class="m2-visor__descargar" data-accion="descargar" download>Descargar</a>
            <button type="button" data-accion="cerrar" class="m2-visor__cerrar" aria-label="Cerrar visor">×</button>
          </div>
        </div>
        <button type="button" class="m2-visor__nav m2-visor__nav--prev" data-accion="anterior" aria-label="Foto anterior">‹</button>
        <div class="m2-visor__lienzo"><img class="m2-visor__img" alt=""><span class="m2-visor__cargando">Cargando…</span></div>
        <button type="button" class="m2-visor__nav m2-visor__nav--next" data-accion="siguiente" aria-label="Foto siguiente">›</button>
        <p class="m2-visor__ayuda">Rueda o doble clic para hacer zoom · arrastra para mover · ← → para cambiar de foto</p>`;
      document.body.appendChild(raiz);

      img = raiz.querySelector(".m2-visor__img");
      titulo = raiz.querySelector(".m2-visor__titulo");
      contador = raiz.querySelector(".m2-visor__contador");
      etiquetaZoom = raiz.querySelector(".m2-visor__zoom");
      enlaceDescarga = raiz.querySelector(".m2-visor__descargar");
      const lienzo = raiz.querySelector(".m2-visor__lienzo");

      raiz.addEventListener("click", (e) => {
        const accion = e.target.closest("[data-accion]")?.dataset.accion;
        if (accion === "cerrar") cerrar();
        if (accion === "acercar") zoom(escala * 1.4);
        if (accion === "alejar") zoom(escala / 1.4);
        if (accion === "ajustar") zoom(1);
        if (accion === "anterior") mostrar(indice - 1);
        if (accion === "siguiente") mostrar(indice + 1);
        if (e.target === lienzo) cerrar(); // clic fuera de la foto
      });
      lienzo.addEventListener("wheel", (e) => {
        e.preventDefault();
        zoom(escala * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
      }, { passive: false });
      img.addEventListener("dblclick", () => zoom(escala > 1 ? 1 : 2.5));
      img.addEventListener("pointerdown", (e) => {
        if (escala <= 1) return;
        e.preventDefault();
        arrastre = { px: e.clientX, py: e.clientY, x, y };
        img.setPointerCapture(e.pointerId);
        img.classList.add("is-arrastrando");
      });
      img.addEventListener("pointermove", (e) => {
        if (!arrastre) return;
        x = arrastre.x + (e.clientX - arrastre.px);
        y = arrastre.y + (e.clientY - arrastre.py);
        aplicar();
      });
      const soltar = () => { arrastre = null; img.classList.remove("is-arrastrando"); };
      img.addEventListener("pointerup", soltar);
      img.addEventListener("pointercancel", soltar);

      document.addEventListener("keydown", (e) => {
        if (raiz.hidden) return;
        if (e.key === "Escape") cerrar();
        if (e.key === "ArrowLeft") mostrar(indice - 1);
        if (e.key === "ArrowRight") mostrar(indice + 1);
        if (e.key === "+" || e.key === "=") zoom(escala * 1.4);
        if (e.key === "-") zoom(escala / 1.4);
        if (e.key === "0") zoom(1);
      });
    }

    function aplicar() {
      if (escala <= 1) { x = 0; y = 0; }
      img.style.transform = `translate(${x}px, ${y}px) scale(${escala})`;
      img.classList.toggle("is-ampliada", escala > 1);
      etiquetaZoom.textContent = `${Math.round(escala * 100)}%`;
    }

    function zoom(nueva) {
      escala = Math.min(6, Math.max(1, nueva));
      aplicar();
    }

    async function mostrar(nuevoIndice) {
      if (!fotos.length) return;
      indice = (nuevoIndice + fotos.length) % fotos.length;
      const foto = fotos[indice];
      escala = 1; aplicar();
      titulo.textContent = foto.nombre || "Evidencia";
      contador.textContent = fotos.length > 1 ? `${indice + 1} de ${fotos.length}` : "";
      raiz.classList.toggle("m2-visor--una", fotos.length < 2);
      raiz.classList.add("is-cargando");
      img.removeAttribute("src");
      img.alt = `Evidencia ${foto.nombre || ""}`;
      try {
        const url = await TicketsAPI.urlImagen(foto.imagen);
        if (fotos[indice] !== foto) return; // el usuario ya cambió de foto
        img.src = url;
        enlaceDescarga.href = url;
        enlaceDescarga.download = foto.nombre || "evidencia";
      } catch (e) {
        avisar("No se pudo cargar la imagen completa.");
      } finally {
        raiz.classList.remove("is-cargando");
      }
    }

    function abrir(lista, inicio = 0) {
      if (!raiz) construir();
      fotos = lista;
      focoPrevio = document.activeElement;
      raiz.hidden = false;
      document.body.classList.add("m2-sin-scroll");
      mostrar(inicio);
      raiz.querySelector(".m2-visor__cerrar").focus();
    }

    function cerrar() {
      raiz.hidden = true;
      document.body.classList.remove("m2-sin-scroll");
      if (focoPrevio) focoPrevio.focus();
    }

    return { abrir, cerrar };
  })();

  /* =======================================================
     MINIATURAS AUTOMÁTICAS  [data-miniatura-url]
     ======================================================= */
  function miniaturaHTML(ticket, galeria) {
    if (!ticket.miniatura_url) {
      return `<span class="m2-mini m2-mini--vacia" title="Sin fotos de evidencia" aria-label="Sin fotos">▧</span>`;
    }
    const total = ticket.total_evidencias > 1 ? `<b class="m2-mini__total">${ticket.total_evidencias}</b>` : "";
    return `<button type="button" class="m2-mini" data-miniatura-url="${escapar(ticket.miniatura_url)}"
              data-imagen-url="${escapar(ticket.imagen_url)}" data-nombre="${escapar(ticket.codigo)}"
              ${galeria ? `data-galeria="${escapar(galeria)}"` : ""}
              aria-label="Ver foto de evidencia de ${escapar(ticket.codigo)}">${total}</button>`;
  }

  async function hidratar(elemento) {
    if (elemento.dataset.m2Listo) return;
    elemento.dataset.m2Listo = "1";
    elemento.classList.add("is-cargando");
    const imagen = document.createElement("img");
    imagen.alt = "";
    imagen.loading = "lazy";
    elemento.prepend(imagen);
    try {
      imagen.src = await TicketsAPI.urlImagen(elemento.dataset.miniaturaUrl);
    } catch (e) {
      elemento.classList.add("m2-mini--error");
      elemento.title = "No se pudo cargar la miniatura";
    } finally {
      elemento.classList.remove("is-cargando");
    }
  }

  function hidratarTodo(contenedor = document) {
    contenedor.querySelectorAll("[data-miniatura-url]").forEach(hidratar);
  }

  // Clic en cualquier miniatura -> visor (agrupa por data-galeria)
  document.addEventListener("click", (e) => {
    const mini = e.target.closest("[data-imagen-url]");
    if (!mini || !mini.dataset.imagenUrl || mini.dataset.imagenUrl === "null") return;
    e.preventDefault();
    e.stopPropagation(); // evita que la fila del listado navegue al detalle
    const grupo = mini.dataset.galeria
      ? [...document.querySelectorAll(`[data-galeria="${CSS.escape(mini.dataset.galeria)}"][data-imagen-url]`)]
      : [mini];
    const fotos = grupo.map((el) => ({ imagen: el.dataset.imagenUrl, nombre: el.dataset.nombre }));
    Visor.abrir(fotos, grupo.indexOf(mini));
  }, true);

  // Miniaturas que se agreguen después (por ejemplo, el listado al cargar de la API)
  new MutationObserver((cambios) => {
    cambios.forEach((c) => c.addedNodes.forEach((nodo) => {
      if (nodo.nodeType !== 1) return;
      if (nodo.matches("[data-miniatura-url]")) hidratar(nodo);
      hidratarTodo(nodo);
    }));
  }).observe(document.documentElement, { childList: true, subtree: true });

  /* =======================================================
     DETALLE DEL TICKET  (detalle_ticket.html?id=N)
     ======================================================= */
  function rellenarCabecera(t) {
    const poner = (id, texto) => { const el = document.getElementById(id); if (el) el.textContent = texto; };
    poner("breadcrumb-code", t.codigo);
    poner("ticket-code", t.codigo);
    poner("ticket-subject", t.asunto);
    poner("ticket-description", t.descripcion);
    poner("ticket-priority-tag", `▥ ${t.prioridad}`);
    poner("ticket-status-tag", `▤ ${t.estado}`);
    const prioridad = document.getElementById("ticket-priority-tag");
    if (prioridad) prioridad.className = `badge priority-${{ Alta: "high", Media: "medium", Baja: "low" }[t.prioridad]}`;
    const estado = document.getElementById("ticket-status-tag");
    const claseEstado = { "Abierto": "status-open", "En proceso": "status-progress", "Resuelto": "status-resolved", "Cerrado": "status-closed" };
    if (estado) estado.className = `badge ${claseEstado[t.estado] || ""}`;
    const categoria = document.querySelector(".ticket-tags .category-tag");
    if (categoria) categoria.textContent = `◉ ${t.categoria}`;
    const empresa = document.querySelectorAll(".ticket-tags .category-tag")[1];
    if (empresa && t.empresa) empresa.textContent = `▦ ${t.empresa}`;
    // Valores actuales en el panel "Estado actual"
    [["property-status", t.estado], ["property-priority", t.prioridad], ["property-category", t.categoria],
     ["property-technician", t.tecnico || "Sin asignar"]].forEach(([id, valor]) => {
      const select = document.getElementById(id);
      if (!select) return;
      if (![...select.options].some((o) => o.value === valor)) select.add(new Option(valor, valor));
      select.value = valor;
    });
    document.querySelectorAll(".metadata-item").forEach((item) => {
      const etiqueta = item.querySelector("small")?.textContent.trim();
      const valor = item.querySelector("strong");
      if (!valor) return;
      if (etiqueta === "Solicitante") valor.textContent = t.solicitante;
      if (etiqueta === "Área") valor.textContent = t.area;
      if (etiqueta === "Creado") valor.textContent = TicketsAPI.formatearFecha(t.created_at);
      if (etiqueta === "Empresa" && t.empresa) valor.textContent = t.empresa;
    });
    document.title = `${t.codigo} · ${t.asunto} | Soporte TI`;
  }

  function panelDetalle(panelOriginal, ticketId) {
    // Se crea un panel nuevo (sin los eventos de ejemplo del prototipo)
    const panel = document.createElement("section");
    panel.className = "panel evidence-panel m2-panel";
    panel.setAttribute("aria-label", "Fotos de evidencia");
    panelOriginal.replaceWith(panel);
    let ticket = null;
    let subiendo = false;

    function render() {
      const fotos = ticket.evidencias;
      const libres = ticket.max_evidencias - fotos.length;
      const puedeAgregar = ticket.permisos.adjuntar && libres > 0;
      panel.innerHTML = `
        <div class="panel-heading">
          <h2><span class="section-icon">▧</span>Fotos de evidencia</h2>
          <span class="muted">${fotos.length} de ${ticket.max_evidencias} fotos</span>
        </div>
        <div class="m2-galeria">
          ${fotos.map((f) => `
            <figure class="m2-galeria__item">
              <button type="button" class="m2-galeria__foto" data-miniatura-url="${escapar(f.miniatura_url)}"
                      data-imagen-url="${escapar(f.imagen_url)}" data-nombre="${escapar(f.nombre)}"
                      data-galeria="ticket-${ticket.id}" aria-label="Ampliar ${escapar(f.nombre)}">
                <span class="m2-galeria__lupa" aria-hidden="true">⤢</span>
              </button>
              <figcaption>
                <span class="m2-galeria__nombre" title="${escapar(f.nombre)}">${escapar(f.nombre)}</span>
                <small>Foto ${f.orden} · ${TicketsAPI.formatearPeso(f.tamano_bytes)} · ${escapar(f.subido_por)}</small>
              </figcaption>
              ${ticket.permisos.editar ? `<button type="button" class="m2-galeria__quitar" data-quitar="${f.id}" aria-label="Quitar ${escapar(f.nombre)}">×</button>` : ""}
            </figure>`).join("")}
          ${puedeAgregar ? `
            <label class="m2-galeria__agregar">
              <input type="file" accept="image/jpeg,image/png,image/webp" ${libres > 1 ? "multiple" : ""} hidden>
              <span class="m2-galeria__mas" aria-hidden="true">＋</span>
              <strong>Agregar foto</strong>
              <small>Quedan ${libres} · JPG, PNG o WEBP</small>
              <span class="m2-progreso" hidden><i></i></span>
            </label>` : ""}
        </div>
        ${fotos.length === 0 && !puedeAgregar ? `<p class="m2-vacio">Este ticket no tiene fotos de evidencia.</p>` : ""}`;
    }

    async function subir(archivos) {
      if (subiendo) return;
      const libres = ticket.max_evidencias - ticket.evidencias.length;
      if (archivos.length > libres) {
        avisar(`Solo puedes agregar ${libres} foto(s) más (máximo ${ticket.max_evidencias} por ticket).`);
        return;
      }
      const datos = new FormData();
      try {
        for (const a of archivos) datos.append("fotos", (await TicketsAPI.prepararFoto(a)).archivo);
      } catch (e) {
        avisar(e.message);
        return;
      }
      subiendo = true;
      const progreso = panel.querySelector(".m2-progreso");
      progreso.hidden = false;
      try {
        const r = await TicketsAPI.agregarEvidencias(ticket.id, datos, (p) => {
          progreso.firstElementChild.style.width = `${p}%`;
        });
        ticket = r.ticket;
        render();
        avisar(r.mensaje);
      } catch (e) {
        avisar(e.message);
        progreso.hidden = true;
      } finally {
        subiendo = false;
      }
    }

    panel.addEventListener("change", (e) => {
      if (e.target.matches('input[type="file"]')) {
        subir([...e.target.files]);
        e.target.value = "";
      }
    });
    panel.addEventListener("dragover", (e) => { e.preventDefault(); panel.classList.add("is-sobre"); });
    panel.addEventListener("dragleave", () => panel.classList.remove("is-sobre"));
    panel.addEventListener("drop", (e) => {
      e.preventDefault();
      panel.classList.remove("is-sobre");
      if (ticket?.permisos.adjuntar && e.dataTransfer.files.length) subir([...e.dataTransfer.files]);
    });
    panel.addEventListener("click", async (e) => {
      const boton = e.target.closest("[data-quitar]");
      if (!boton) return;
      if (!confirm("¿Quitar esta foto del ticket? No se puede deshacer.")) return;
      try {
        const r = await TicketsAPI.eliminarEvidencia(ticket.id, boton.dataset.quitar);
        ticket = r.ticket;
        render();
        avisar(r.mensaje);
      } catch (err) {
        avisar(err.message);
      }
    });

    panel.innerHTML = `<div class="panel-heading"><h2><span class="section-icon">▧</span>Fotos de evidencia</h2></div><p class="m2-vacio">Cargando fotos…</p>`;
    TicketsAPI.pintarPerfil();
    TicketsAPI.obtener(ticketId).then((r) => {
      ticket = r.ticket;
      rellenarCabecera(ticket);
      render();
      // Otros módulos (3, 4) pueden reutilizar los datos sin volver a pedirlos
      document.dispatchEvent(new CustomEvent("ticket:cargado", { detail: ticket }));
    }).catch((e) => {
      panel.innerHTML = `<div class="panel-heading"><h2><span class="section-icon">▧</span>Fotos de evidencia</h2></div><p class="m2-vacio m2-vacio--error">${escapar(e.message)}</p>`;
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    hidratarTodo();
    const id = new URLSearchParams(location.search).get("id");
    const panel = document.querySelector(".evidence-panel");
    if (panel && id && /^\d+$/.test(id)) panelDetalle(panel, id);
  });

  return { Visor, miniaturaHTML, hidratarTodo, avisar };
})();


/* #########################################################
   PARTE 3 — Listado de tickets (tickets.html)
   ######################################################### */
/* =========================================================
   tickets.js — Listado de tickets (conectado a Flask)
   ---------------------------------------------------------
   Usa TicketsAPI y Evidencias (partes 1 y 2)

   - Carga los tickets desde GET /api/tickets.
   - Columna "Foto": miniatura de la primera evidencia; al hacer
     clic se abre la imagen completa (visor de la parte 2).
   - Filtros, contadores, alerta de plazos y paginación en el navegador.
   - Si el servidor Flask no está corriendo (por ejemplo, abierto con
     Live Server), se quedan las filas de ejemplo del HTML.
   ========================================================= */
document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);
  const tbody = $("tickets-body");
  if (!tbody) return; // esta parte solo corre en tickets.html
  const search = $("ticket-search");
  const status = $("status-filter");
  const priority = $("priority-filter");
  const technician = $("technician-filter");
  const selectAll = $("select-all");
  const POR_PAGINA = 10;
  const CLASE_PRIORIDAD = { Alta: "priority-high", Media: "priority-medium", Baja: "priority-low" };
  const CLASE_ESTADO = { "Abierto": "status-open", "En proceso": "status-progress", "Resuelto": "status-resolved", "Cerrado": "status-closed" };

  let rows = [...document.querySelectorAll(".ticket-row")];
  let totalTickets = rows.length;
  let pagina = 1;
  let modoReal = false;

  const avisar = (m) => Evidencias.avisar(m);
  const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ---------- Plazo (semáforo) ---------- */
  // El semáforo y los minutos restantes los calcula la vista v_tickets de la BD
  function calcularPlazo(t) {
    const tiempo = (min) => {
      min = Math.abs(min || 0);
      if (min < 60) return `${min} min`;
      if (min < 2880) return `${Math.round(min / 60)} h`;
      return `${Math.round(min / 1440)} d`;
    };
    switch (t.semaforo) {
      case "rojo": return { texto: `Vencido hace ${tiempo(t.minutos_restantes)}`, clase: "sla-danger", nivel: "Vencido" };
      case "amarillo": return { texto: `Por vencer (${tiempo(t.minutos_restantes)})`, clase: "sla-warning", nivel: "Por vencer" };
      case "verde": return { texto: `Quedan ${tiempo(t.minutos_restantes)}`, clase: "sla-ok", nivel: "A tiempo" };
      case "cumplido": return { texto: "Cumplido", clase: "sla-ok", nivel: "" };
      case "incumplido": return { texto: "Fuera de plazo", clase: "sla-danger", nivel: "" };
      default: return { texto: "—", clase: "sla-neutral", nivel: "" };
    }
  }

  /* ---------- Fila de la tabla ---------- */
  function filaHTML(t) {
    const plazo = calcularPlazo(t);
    const tecnico = t.tecnico || "Sin asignar";
    const detalle = `detalle_ticket.html?id=${t.id}`;
    return `
      <tr class="ticket-row${plazo.nivel === "Vencido" ? " urgent" : ""}" data-id="${t.id}" data-href="${detalle}"
          data-code="${escapar(t.codigo)}" data-subject="${escapar(t.asunto)}" data-requester="${escapar(t.solicitante)}"
          data-technician="${escapar(tecnico)}" data-priority="${t.prioridad}" data-status="${t.estado}" data-sla="${plazo.nivel}">
        <td><input class="row-check" type="checkbox" aria-label="Seleccionar ${escapar(t.codigo)}"></td>
        <td>${Evidencias.miniaturaHTML(t)}</td>
        <td><a class="ticket-code" href="${detalle}">${escapar(t.codigo)}</a></td>
        <td><strong>${escapar(t.asunto)}</strong><small>${escapar(t.categoria)} · ${escapar(t.area)}</small></td>
        <td>${escapar(t.solicitante)}<small>${TicketsAPI.formatearFecha(t.created_at)}</small></td>
        <td>${escapar(tecnico)}</td>
        <td><span class="badge ${CLASE_PRIORIDAD[t.prioridad]}">${t.prioridad}</span></td>
        <td><span class="badge ${CLASE_ESTADO[t.estado]}">${t.estado}</span></td>
        <td><span class="sla ${plazo.clase}"><i></i>${plazo.texto}</span></td>
        <td><div class="row-actions">
          <a href="${detalle}" aria-label="Ver ${escapar(t.codigo)}" title="Ver detalle">◉</a>
          ${t.estado === "Abierto" ? `<a href="nuevo_ticket.html?editar=${t.id}" aria-label="Editar ${escapar(t.codigo)}" title="Editar">✎</a>` : ""}
        </div></td>
      </tr>`;
  }

  async function cargarTickets() {
    try {
      const { tickets } = await TicketsAPI.listar({ limite: 200 });
      modoReal = true;
      tbody.innerHTML = tickets.map(filaHTML).join("");
      rows = [...tbody.querySelectorAll(".ticket-row")];
      totalTickets = tickets.length;
      $("page-message").textContent = `Datos en vivo · actualizado ${new Date().toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}`;

      // Técnicos reales para el filtro
      const tecnicos = [...new Set(rows.map((r) => r.dataset.technician))].sort();
      technician.innerHTML = `<option value="">Todos los técnicos</option>` +
        tecnicos.map((n) => `<option>${escapar(n)}</option>`).join("");
    } catch (e) {
      if (e.estado === 401) { location.href = "/"; return; }
      // Sin backend: se mantienen las filas de ejemplo del HTML
      $("page-message").textContent = e.estado === 401
        ? "Inicia sesión para ver los tickets."
        : "Modo demostración · ejecuta «python run.py» para ver los tickets reales";
    }
    actualizarMetricas();
    activarFilas();
    pagina = 1;
    applyFilters();
  }

  function activarFilas() {
    rows.forEach((row) => {
      row.querySelector(".row-check")?.addEventListener("change", sincronizarSeleccion);
      row.addEventListener("click", (e) => {
        if (!modoReal || e.target.closest("a, button, input")) return;
        location.href = row.dataset.href;
      });
      row.querySelector('[data-action="more"]')?.addEventListener("click", () => {
        avisar(`Acciones adicionales para ${row.dataset.code}.`);
      });
    });
  }

  /* ---------- Contadores y alerta de plazos ---------- */
  function actualizarMetricas() {
    const contar = (estado) => rows.filter((r) => r.dataset.status === estado).length;
    const total = rows.length || 1;
    [["metric-open", "Abierto"], ["metric-progress", "En proceso"], ["metric-resolved", "Resuelto"], ["metric-closed", "Cerrado"]]
      .forEach(([id, estado]) => {
        const n = contar(estado);
        $(id).textContent = n;
        const nota = $(id).closest(".metric").querySelector("small");
        if (nota && modoReal) nota.innerHTML = `${Math.round((n / total) * 100)}% <em>del total</em>`;
      });

    if (!modoReal) return;
    const vencidos = rows.filter((r) => r.dataset.sla === "Vencido").length;
    const porVencer = rows.filter((r) => r.dataset.sla === "Por vencer").length;
    const alerta = $("sla-alert");
    alerta.hidden = vencidos + porVencer === 0;
    alerta.querySelector("strong").textContent =
      `${vencidos} ticket${vencidos === 1 ? "" : "s"} venció su plazo y ${porVencer} ${porVencer === 1 ? "está" : "están"} por vencer.`;
  }

  /* ---------- Filtros + paginación ---------- */
  function applyFilters() {
    const query = (search.value || "").trim().toLocaleLowerCase("es");
    const urgentes = $("show-urgent").dataset.activo === "1";
    const visibles = rows.filter((row) => {
      const texto = `${row.dataset.code} ${row.dataset.subject} ${row.dataset.requester}`.toLocaleLowerCase("es");
      return texto.includes(query)
        && (!status.value || row.dataset.status === status.value)
        && (!priority.value || row.dataset.priority === priority.value)
        && (!technician.value || row.dataset.technician === technician.value)
        && (!urgentes || row.dataset.sla === "Vencido" || row.dataset.sla === "Por vencer");
    });

    const paginas = Math.max(1, Math.ceil(visibles.length / POR_PAGINA));
    pagina = Math.min(pagina, paginas);
    const inicio = (pagina - 1) * POR_PAGINA;
    const enPagina = new Set(visibles.slice(inicio, inicio + POR_PAGINA));
    rows.forEach((row) => {
      row.hidden = !enPagina.has(row);
      if (row.hidden) row.querySelector(".row-check").checked = false;
    });

    $("results-count").textContent = visibles.length
      ? `Mostrando ${inicio + 1}–${inicio + enPagina.size} de ${visibles.length} ticket${visibles.length === 1 ? "" : "s"}` +
        (visibles.length !== totalTickets ? ` (de ${totalTickets})` : "")
      : "Mostrando 0 tickets";
    $("empty-state").hidden = visibles.length !== 0;
    $("empty-state").textContent = rows.length ? "No se encontraron tickets con esos filtros." : "Todavía no hay tickets registrados.";
    pintarPaginacion(paginas);
    selectAll.checked = false;
    selectAll.indeterminate = false;
  }

  function pintarPaginacion(paginas) {
    const nav = document.querySelector(".pagination");
    const numeros = Array.from({ length: paginas }, (_, i) => i + 1)
      .map((n) => `<button type="button" class="page-number${n === pagina ? " current" : ""}" data-pagina="${n}" ${n === pagina ? 'aria-current="page"' : ""}>${n}</button>`).join("");
    nav.innerHTML =
      `<button type="button" data-pagina="1" aria-label="Primera página" ${pagina === 1 ? "disabled" : ""}>«</button>` +
      `<button type="button" data-pagina="${pagina - 1}" aria-label="Página anterior" ${pagina === 1 ? "disabled" : ""}>‹</button>` +
      numeros +
      `<button type="button" data-pagina="${pagina + 1}" aria-label="Página siguiente" ${pagina === paginas ? "disabled" : ""}>›</button>` +
      `<button type="button" data-pagina="${paginas}" aria-label="Última página" ${pagina === paginas ? "disabled" : ""}>»</button>`;
  }

  document.querySelector(".pagination").addEventListener("click", (e) => {
    const boton = e.target.closest("[data-pagina]");
    if (!boton || boton.disabled) return;
    pagina = Number(boton.dataset.pagina);
    applyFilters();
  });

  [search, status, priority, technician].forEach((control) => {
    control.addEventListener(control === search ? "input" : "change", () => { pagina = 1; applyFilters(); });
  });

  $("reset-filters").addEventListener("click", () => {
    search.value = ""; status.value = ""; priority.value = ""; technician.value = "";
    $("show-urgent").dataset.activo = "";
    pagina = 1;
    applyFilters();
    avisar("Se limpiaron los filtros.");
  });

  $("show-urgent").addEventListener("click", () => {
    const boton = $("show-urgent");
    boton.dataset.activo = boton.dataset.activo === "1" ? "" : "1";
    pagina = 1;
    applyFilters();
    avisar(boton.dataset.activo ? "Mostrando tickets vencidos o por vencer." : "Mostrando todos los tickets.");
  });

  /* ---------- Selección ---------- */
  selectAll.addEventListener("change", () => {
    rows.filter((r) => !r.hidden).forEach((r) => { r.querySelector(".row-check").checked = selectAll.checked; });
  });
  function sincronizarSeleccion() {
    const visibles = rows.filter((r) => !r.hidden).map((r) => r.querySelector(".row-check"));
    const marcados = visibles.filter((c) => c.checked).length;
    selectAll.checked = visibles.length > 0 && marcados === visibles.length;
    selectAll.indeterminate = marcados > 0 && marcados < visibles.length;
  }

  /* La búsqueda global de la barra superior filtra este listado */
  $("global-search").addEventListener("input", (e) => {
    search.value = e.target.value;
    pagina = 1;
    applyFilters();
  });

  TicketsAPI.pintarPerfil();
  cargarTickets();
});
