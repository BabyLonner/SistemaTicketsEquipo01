/* =========================================================
   app.js — Módulo 3: Asignación, estados e historial
   - Asignar / reasignar ticket a un técnico
   - Cambiar estado (Abierto / En proceso / Resuelto / Cerrado)
     con comentario obligatorio del técnico (UPDATE validado)
   - Línea de tiempo del historial con fechas relativas
   ========================================================= */

let db = cargarDB();
let ticketSeleccionadoId = db.tickets.length ? db.tickets[0].id : null;
let filtroEstado = "Todos";
let textoBusqueda = "";
let ultimoEventoNuevoId = null;

/* ---------- Utilidades ---------- */
const $ = (sel) => document.querySelector(sel);

function escaparHTML(texto) {
  return String(texto ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function claseEstado(estado) {
  return "badge--" + estado.replace(/\s/g, "");
}

function iniciales(nombre) {
  return nombre.split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

function buscarTicket(id)  { return db.tickets.find((t) => t.id === id); }
function buscarTecnico(id) { return db.tecnicos.find((t) => t.id === id); }

function historialDe(ticketId) {
  return db.historial
    .filter((h) => h.ticket_id === ticketId)
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
}

function siguienteId(lista) {
  return lista.reduce((max, item) => Math.max(max, item.id), 0) + 1;
}

/* ---------- Fechas relativas ---------- */
const rtf = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
const UNIDADES = [
  ["year", 31536000], ["month", 2592000], ["week", 604800],
  ["day", 86400], ["hour", 3600], ["minute", 60]
];

function tiempoRelativo(iso) {
  const segundos = (new Date(iso) - Date.now()) / 1000;
  if (Math.abs(segundos) < 60) return "hace un momento";
  for (const [unidad, valor] of UNIDADES) {
    if (Math.abs(segundos) >= valor) {
      return rtf.format(Math.round(segundos / valor), unidad);
    }
  }
  return "hace un momento";
}

function fechaCompleta(iso) {
  return new Date(iso).toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" });
}

/* <time> que se actualiza solo cada minuto */
function etiquetaTiempo(iso) {
  return `<time datetime="${iso}" data-relativo title="${fechaCompleta(iso)}">${tiempoRelativo(iso)}</time>`;
}

function refrescarFechasRelativas() {
  document.querySelectorAll("time[data-relativo]").forEach((el) => {
    el.textContent = tiempoRelativo(el.getAttribute("datetime"));
  });
}

function ultimaActividad(ticketId) {
  const h = historialDe(ticketId);
  return h.length ? h[0].timestamp : buscarTicket(ticketId).creado;
}

/* =========================================================
   Operaciones sobre los datos (simulan el backend)
   ========================================================= */

/* Asignar o reasignar un técnico */
function asignarTecnico(ticketId, tecnicoId) {
  const ticket = buscarTicket(ticketId);
  const tecnico = buscarTecnico(tecnicoId);

  if (!ticket)  return { ok: false, error: "El ticket no existe." };
  if (!tecnico) return { ok: false, error: "Selecciona un técnico de la lista." };
  if (ticket.estado === "Cerrado") return { ok: false, error: "Un ticket cerrado no se puede reasignar." };
  if (ticket.tecnico_id === tecnicoId) return { ok: false, error: `${tecnico.nombre} ya está asignado a este ticket.` };

  const anterior = ticket.tecnico_id ? buscarTecnico(ticket.tecnico_id) : null;
  ticket.tecnico_id = tecnicoId;

  const registro = {
    id: siguienteId(db.historial),
    ticket_id: ticket.id,
    tipo: "asignacion",
    estado_anterior: null,
    estado_nuevo: null,
    tecnico_id: tecnicoId,
    comentario: anterior
      ? `Ticket reasignado de ${anterior.nombre} a ${tecnico.nombre}.`
      : `Ticket asignado a ${tecnico.nombre}.`,
    timestamp: new Date().toISOString()
  };
  db.historial.push(registro);
  guardarDB(db);

  return { ok: true, registro, mensaje: anterior ? "Técnico reasignado" : "Técnico asignado" };
}

/* UPDATE validado del estado + INSERT en ticket_historial */
function cambiarEstado(ticketId, nuevoEstado, comentario) {
  const ticket = buscarTicket(ticketId);
  const texto = (comentario || "").trim();

  if (!ticket) return { ok: false, error: "El ticket no existe." };
  if (!ticket.tecnico_id) return { ok: false, error: "Asigna un técnico antes de cambiar el estado." };
  if (!ESTADOS.includes(nuevoEstado)) return { ok: false, error: "Elige el nuevo estado del ticket." };

  const permitidos = TRANSICIONES[ticket.estado] || [];
  if (!permitidos.includes(nuevoEstado)) {
    return { ok: false, error: `No se puede pasar de "${ticket.estado}" a "${nuevoEstado}".` };
  }
  if (texto.length === 0) {
    return { ok: false, error: "El comentario del técnico es obligatorio.", campo: "comentario" };
  }
  if (texto.length < MIN_COMENTARIO) {
    return { ok: false, error: `El comentario debe tener al menos ${MIN_COMENTARIO} caracteres.`, campo: "comentario" };
  }

  const estadoAnterior = ticket.estado;
  ticket.estado = nuevoEstado;

  const registro = {
    id: siguienteId(db.historial),
    ticket_id: ticket.id,
    tipo: "estado",
    estado_anterior: estadoAnterior,
    estado_nuevo: nuevoEstado,
    tecnico_id: ticket.tecnico_id,
    comentario: texto,
    timestamp: new Date().toISOString()
  };
  db.historial.push(registro);
  guardarDB(db);

  return { ok: true, registro, mensaje: `Estado cambiado a "${nuevoEstado}"` };
}

/* =========================================================
   Render: lista de tickets
   ========================================================= */
function ticketsFiltrados() {
  const q = textoBusqueda.toLowerCase();
  return db.tickets
    .filter((t) => filtroEstado === "Todos" || t.estado === filtroEstado)
    .filter((t) =>
      !q ||
      t.codigo.toLowerCase().includes(q) ||
      t.titulo.toLowerCase().includes(q) ||
      t.solicitante.toLowerCase().includes(q)
    )
    .sort((a, b) => new Date(ultimaActividad(b.id)) - new Date(ultimaActividad(a.id)));
}

function renderLista() {
  const lista = ticketsFiltrados();
  $("#contadorTickets").textContent = lista.length;

  if (!lista.length) {
    $("#listaTickets").innerHTML = `<li class="lista__vacia">No hay tickets con este filtro.</li>`;
    return;
  }

  $("#listaTickets").innerHTML = lista.map((t) => {
    const tecnico = t.tecnico_id ? buscarTecnico(t.tecnico_id) : null;
    return `
      <li>
        <button type="button"
          class="ticket-item ${t.id === ticketSeleccionadoId ? "seleccionado" : ""}"
          data-id="${t.id}" data-estado="${t.estado}"
          aria-current="${t.id === ticketSeleccionadoId}">
          <span class="ticket-item__fila">
            <span class="ticket-item__codigo">${t.codigo}</span>
            <span class="badge ${claseEstado(t.estado)}">${t.estado}</span>
          </span>
          <span class="ticket-item__titulo">${escaparHTML(t.titulo)}</span>
          <span class="ticket-item__fila ticket-item__meta">
            ${tecnico ? escaparHTML(tecnico.nombre) : `<span class="sin-asignar">Sin asignar</span>`}
            ${etiquetaTiempo(ultimaActividad(t.id))}
          </span>
        </button>
      </li>`;
  }).join("");
}

/* =========================================================
   Render: detalle del ticket
   ========================================================= */
function renderDetalle() {
  const contenedor = $("#detalle");
  const ticket = buscarTicket(ticketSeleccionadoId);

  if (!ticket) {
    contenedor.innerHTML = `
      <div class="tarjeta vacio">
        <h2>Selecciona un ticket</h2>
        <p>Elige un ticket de la lista para asignarlo, cambiar su estado y ver su historial.</p>
      </div>`;
    return;
  }

  contenedor.innerHTML = `
    ${htmlEncabezado(ticket)}
    <div class="acciones">
      ${htmlAsignacion(ticket)}
      ${htmlCambioEstado(ticket)}
    </div>
    ${htmlHistorial(ticket)}
  `;

  conectarEventosDetalle(ticket);
}

function htmlEncabezado(t) {
  return `
    <article class="tarjeta encabezado-ticket">
      <div class="encabezado-ticket__top">
        <span class="encabezado-ticket__codigo">${t.codigo}</span>
        <span class="badge ${claseEstado(t.estado)}">${t.estado}</span>
      </div>
      <h2 class="encabezado-ticket__titulo">${escaparHTML(t.titulo)}</h2>
      <p class="encabezado-ticket__desc">${escaparHTML(t.descripcion)}</p>
      <dl class="datos">
        <div><dt>Solicitante</dt><dd>${escaparHTML(t.solicitante)}</dd></div>
        <div><dt>Área</dt><dd>${escaparHTML(t.area)}</dd></div>
        <div><dt>Prioridad</dt><dd class="prioridad prioridad--${t.prioridad}">${t.prioridad}</dd></div>
        <div><dt>Creado</dt><dd>${etiquetaTiempo(t.creado)}</dd></div>
      </dl>
    </article>`;
}

function htmlAsignacion(t) {
  const tecnico = t.tecnico_id ? buscarTecnico(t.tecnico_id) : null;
  const cerrado = t.estado === "Cerrado";

  const actual = tecnico
    ? `<div class="tecnico-actual">
         <span class="avatar">${iniciales(tecnico.nombre)}</span>
         <div>
           <div class="tecnico-actual__nombre">${escaparHTML(tecnico.nombre)}</div>
           <div class="tecnico-actual__esp">${escaparHTML(tecnico.especialidad)}</div>
         </div>
       </div>`
    : `<div class="tecnico-actual">
         <span class="avatar avatar--vacio">?</span>
         <div>
           <div class="tecnico-actual__nombre">Sin técnico asignado</div>
           <div class="tecnico-actual__esp">Asigna a alguien para empezar la atención</div>
         </div>
       </div>`;

  const opciones = db.tecnicos.map((tec) =>
    `<option value="${tec.id}" ${tec.id === t.tecnico_id ? "selected" : ""}>
       ${escaparHTML(tec.nombre)} — ${escaparHTML(tec.especialidad)}
     </option>`
  ).join("");

  return `
    <form class="tarjeta" id="formAsignacion" novalidate>
      <h3 class="tarjeta__titulo">Técnico responsable</h3>
      <p class="tarjeta__ayuda">La asignación queda registrada en el historial.</p>
      ${actual}
      <label class="campo">
        <span class="campo__label">${tecnico ? "Reasignar a" : "Asignar a"}</span>
        <select id="selectTecnico" ${cerrado ? "disabled" : ""}>
          ${tecnico ? "" : `<option value="">Selecciona un técnico</option>`}
          ${opciones}
        </select>
      </label>
      <p class="mensaje-error" id="errorAsignacion"></p>
      <button type="submit" class="btn btn--primario" ${cerrado ? "disabled" : ""}>
        ${tecnico ? "Reasignar técnico" : "Asignar técnico"}
      </button>
    </form>`;
}

function htmlCambioEstado(t) {
  const permitidos = TRANSICIONES[t.estado] || [];

  let cuerpo;
  if (!permitidos.length) {
    cuerpo = `<p class="aviso">Este ticket está cerrado y ya no admite cambios de estado.</p>`;
  } else if (!t.tecnico_id) {
    cuerpo = `<p class="aviso">Asigna un técnico antes de cambiar el estado. El comentario de cada cambio lo registra el técnico responsable.</p>`;
  } else {
    const radios = permitidos.map((e, i) => `
      <label class="estado-opcion" data-estado="${e}">
        <input type="radio" name="nuevoEstado" value="${e}" ${i === 0 ? "checked" : ""}>
        <span>${e}</span>
      </label>`).join("");

    cuerpo = `
      <fieldset class="estados-opciones">
        <legend class="sr-only">Nuevo estado</legend>
        ${radios}
      </fieldset>
      <label class="campo" id="campoComentario">
        <span class="campo__label">Comentario del técnico (obligatorio)</span>
        <textarea id="txtComentario" maxlength="500"
          placeholder="Describe qué se hizo o por qué cambia el estado"></textarea>
        <span class="campo__pie">
          <span id="ayudaComentario">Mínimo ${MIN_COMENTARIO} caracteres</span>
          <span id="contadorComentario">0 / 500</span>
        </span>
      </label>
      <p class="mensaje-error" id="errorEstado"></p>
      <button type="submit" class="btn btn--primario">Guardar cambio de estado</button>`;
  }

  return `
    <form class="tarjeta" id="formEstado" novalidate>
      <h3 class="tarjeta__titulo">Cambiar estado</h3>
      <p class="tarjeta__ayuda">Estado actual: <span class="badge ${claseEstado(t.estado)}">${t.estado}</span></p>
      ${cuerpo}
    </form>`;
}

function htmlHistorial(t) {
  const eventos = historialDe(t.id);

  const items = eventos.map((h) => {
    const tecnico = h.tecnico_id ? buscarTecnico(h.tecnico_id) : null;
    let titulo, color;

    if (h.tipo === "estado") {
      titulo = `${h.estado_anterior}<span class="flecha" aria-label="a">→</span>${h.estado_nuevo}`;
      color = h.estado_nuevo;
    } else if (h.tipo === "asignacion") {
      titulo = "Asignación de técnico";
      color = "asignacion";
    } else {
      titulo = "Ticket creado";
      color = "creacion";
    }

    const autor = h.tipo === "estado" && tecnico
      ? `<p class="evento__autor">Registrado por ${escaparHTML(tecnico.nombre)}</p>`
      : "";

    return `
      <li class="evento ${h.id === ultimoEventoNuevoId ? "evento--nuevo" : ""}" data-color="${color}">
        <span class="evento__punto" aria-hidden="true"></span>
        <div class="evento__cabecera">
          <span class="evento__titulo">${titulo}</span>
          <span class="evento__fecha">${etiquetaTiempo(h.timestamp)}</span>
        </div>
        <p class="evento__comentario">${escaparHTML(h.comentario)}</p>
        ${autor}
      </li>`;
  }).join("");

  return `
    <section class="tarjeta">
      <h3 class="tarjeta__titulo">Historial del ticket</h3>
      <p class="tarjeta__ayuda">${eventos.length} ${eventos.length === 1 ? "movimiento" : "movimientos"}, del más reciente al más antiguo.</p>
      <ol class="timeline">${items}</ol>
    </section>`;
}

/* =========================================================
   Eventos
   ========================================================= */
function conectarEventosDetalle(ticket) {
  /* --- Asignación --- */
  const formAsig = $("#formAsignacion");
  formAsig.addEventListener("submit", (e) => {
    e.preventDefault();
    const valor = Number($("#selectTecnico").value);
    const res = asignarTecnico(ticket.id, valor);
    if (!res.ok) {
      $("#errorAsignacion").textContent = res.error;
      return;
    }
    ultimoEventoNuevoId = res.registro.id;
    mostrarToast(res.mensaje);
    renderTodo();
  });

  /* --- Cambio de estado --- */
  const formEstado = $("#formEstado");
  const txt = $("#txtComentario");
  if (!txt) return; // ticket cerrado o sin técnico

  txt.addEventListener("input", () => {
    const largo = txt.value.trim().length;
    $("#contadorComentario").textContent = `${txt.value.length} / 500`;
    const ayuda = $("#ayudaComentario");
    if (largo >= MIN_COMENTARIO) {
      ayuda.textContent = "Comentario válido";
      ayuda.className = "ok";
      $("#campoComentario").classList.remove("campo--error");
      $("#errorEstado").textContent = "";
    } else {
      ayuda.textContent = `Faltan ${MIN_COMENTARIO - largo} caracteres`;
      ayuda.className = "";
    }
  });

  formEstado.addEventListener("submit", (e) => {
    e.preventDefault();
    const elegido = formEstado.querySelector('input[name="nuevoEstado"]:checked');
    const res = cambiarEstado(ticket.id, elegido ? elegido.value : "", txt.value);
    if (!res.ok) {
      $("#errorEstado").textContent = res.error;
      if (res.campo === "comentario") {
        $("#campoComentario").classList.add("campo--error");
        txt.focus();
      }
      return;
    }
    ultimoEventoNuevoId = res.registro.id;
    mostrarToast(res.mensaje);
    renderTodo();
  });
}

function conectarEventosGenerales() {
  /* Seleccionar ticket en la lista */
  $("#listaTickets").addEventListener("click", (e) => {
    const boton = e.target.closest(".ticket-item");
    if (!boton) return;
    ticketSeleccionadoId = Number(boton.dataset.id);
    ultimoEventoNuevoId = null;
    renderTodo();
  });

  /* Filtros por estado */
  $("#filtros").addEventListener("click", (e) => {
    const boton = e.target.closest(".filtro");
    if (!boton) return;
    filtroEstado = boton.dataset.estado;
    document.querySelectorAll(".filtro").forEach((b) => b.classList.toggle("activo", b === boton));
    renderLista();
  });

  /* Búsqueda */
  $("#inputBusqueda").addEventListener("input", (e) => {
    textoBusqueda = e.target.value.trim();
    renderLista();
  });

  /* Restablecer datos */
  $("#btnReiniciar").addEventListener("click", () => {
    if (!confirm("Se borrarán los cambios y se cargarán los datos de ejemplo. ¿Continuar?")) return;
    db = reiniciarDB();
    ticketSeleccionadoId = db.tickets[0].id;
    ultimoEventoNuevoId = null;
    renderTodo();
    mostrarToast("Datos de ejemplo restablecidos");
  });
}

/* ---------- Toast ---------- */
let toastTimer;
function mostrarToast(mensaje) {
  const toast = $("#toast");
  toast.textContent = mensaje;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

/* ---------- Inicio ---------- */
function renderTodo() {
  renderLista();
  renderDetalle();
}

document.addEventListener("DOMContentLoaded", () => {
  conectarEventosGenerales();
  renderTodo();
  setInterval(refrescarFechasRelativas, 60000); // fechas relativas siempre al día
});
