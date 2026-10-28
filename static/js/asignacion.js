/* =========================================================
   asignacion.js — MÓDULO 3: Asignación, estados e historial
   Conectado a la API de Flask (tickets.py):
     GET  /api/tickets?mios=0&limite=200   → bandeja
     GET  /api/tecnicos                    → técnicos activos de la empresa
     GET  /api/historial/reciente          → actividad reciente (ticket_historial)
     GET  /api/tickets/<id>/historial      → línea de tiempo de un ticket
     PUT  /api/tickets/<id>                → asignar / cambiar estado
   El servidor vuelve a validar todo; aquí se valida para avisar antes.
   ========================================================= */

let ticketsGlobales = [];
let tecnicosDisponibles = []; // [{ id, nombre, activos }]
let historialReciente = []; // últimos movimientos de ticket_historial
let movimientosHoy = 0;
let vistaActual = 'todos'; // 'todos', 'sin-asignar', 'activos'
let ticketActivo = null;

const MIN_COMENTARIO = 10;
const TRANSICIONES = {
	Abierto: ['En proceso'],
	'En proceso': ['Resuelto'],
	Resuelto: ['Cerrado', 'En proceso'],
	Cerrado: []
};
const CLASE_ESTADO = {
	Abierto: 'status-open',
	'En proceso': 'status-progress',
	Resuelto: 'status-resolved',
	Cerrado: 'status-closed'
};
const CLASE_PRIORIDAD = { Alta: 'priority-high', Media: 'priority-medium', Baja: 'priority-low' };

document.addEventListener('DOMContentLoaded', () => {
	if (!document.getElementById('assign-body')) return;
	configurarEventosUI();
	cargarDatosAsignacion();
	setInterval(cargarDatosAsignacion, 30000);
});

/* =========================================================================
   UTILIDADES
   ========================================================================= */
function obtenerHeadersAuth() {
	const headers = { 'Content-Type': 'application/json' };
	const token = localStorage.getItem('token');
	if (token) headers['Authorization'] = `Bearer ${token}`;
	return headers;
}

function escaparHTML(t) {
	return String(t ?? '').replace(
		/[&<>"']/g,
		(c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
	);
}

function iniciales(n) {
	return (n || '?')
		.split(/\s+/)
		.slice(0, 2)
		.map((p) => p[0])
		.join('')
		.toUpperCase();
}

function tiempoRelativo(iso) {
	if (!iso) return '—';
	const date = new Date(iso);
	if (isNaN(date.getTime())) return '—';
	const min = Math.floor(Math.max(0, Date.now() - date.getTime()) / 60000);
	if (min < 1) return 'hace un momento';
	if (min < 60) return `hace ${min} min`;
	const h = Math.floor(min / 60);
	if (h < 24) return `hace ${h} h`;
	const d = Math.floor(h / 24);
	if (d === 1) return 'ayer';
	return `hace ${d} días`;
}

function fechaExacta(iso) {
	const d = new Date(iso);
	return isNaN(d.getTime()) ? '' : d.toLocaleString('es-PE');
}

function mostrarToast(msg) {
	const toast = document.getElementById('toast');
	if (!toast) return;
	toast.textContent = msg;
	toast.classList.add('show');
	setTimeout(() => toast.classList.remove('show'), 3500);
}

/* Lee el mensaje de error que devuelve Flask ({ error: "..." }) */
async function mensajeDeError(res, porDefecto) {
	try {
		const data = await res.json();
		return data.error || data.msg || porDefecto;
	} catch (e) {
		return porDefecto;
	}
}

/* Traduce un movimiento de ticket_historial a ícono, color y texto */
function describirMovimiento(h) {
	switch (h.tipo) {
		case 'CREACION':
			return { icono: '＋', clase: 't-open', texto: 'Ticket creado · estado inicial Abierto' };
		case 'ASIGNACION':
			return h.tecnico_anterior
				? { icono: '⇄', clase: 't-assign', texto: `Reasignado de ${h.tecnico_anterior} a ${h.tecnico_nuevo}` }
				: { icono: '♙', clase: 't-assign', texto: `Asignado a ${h.tecnico_nuevo}` };
		case 'CAMBIO_ESTADO': {
			const icono = { 'En proceso': '⟳', Resuelto: '✓', Cerrado: '■', Abierto: '!' }[h.estado_nuevo] || '●';
			const clase = { 'En proceso': 't-progress', Resuelto: 't-resolved', Cerrado: 't-closed', Abierto: 't-open' }[h.estado_nuevo] || '';
			const texto =
				h.estado_anterior === 'Resuelto' && h.estado_nuevo === 'En proceso'
					? 'Ticket reabierto · Resuelto → En proceso'
					: `Estado: ${h.estado_anterior} → ${h.estado_nuevo}`;
			return { icono, clase, texto };
		}
		case 'COMENTARIO':
			return { icono: '💬', clase: '', texto: 'Nuevo comentario' };
		default:
			return { icono: '●', clase: '', texto: 'Actualización' };
	}
}

function itemLineaDeTiempo(h, conCodigo) {
	const info = describirMovimiento(h);
	const enlace = conCodigo
		? `<a href="/detalle_ticket?id=${h.ticket_id}">${escaparHTML(h.codigo)}</a> · `
		: '';
	return `
        <li class="tl-item">
            <span class="tl-icon ${info.clase}" aria-hidden="true">${info.icono}</span>
            <div class="tl-body">
                <div class="tl-title">${enlace}${escaparHTML(info.texto)}</div>
                <div class="tl-meta">
                    <span>${escaparHTML(h.usuario)}${h.usuario_rol ? ` (${escaparHTML(h.usuario_rol)})` : ''}</span>
                    <time datetime="${escaparHTML(h.created_at)}" title="${fechaExacta(h.created_at)}">${tiempoRelativo(h.created_at)}</time>
                </div>
                ${h.comentario ? `<p class="tl-comment">${escaparHTML(h.comentario)}</p>` : ''}
            </div>
        </li>`;
}

/* Último movimiento registrado de cada ticket (para la columna "Actualizado") */
function ultimoMovimiento(ticketId) {
	return historialReciente.find((h) => h.ticket_id === ticketId) || null;
}

/* =========================================================================
   CARGA PRINCIPAL DE DATOS
   ========================================================================= */
async function cargarDatosAsignacion() {
	try {
		const [resTickets, resTecnicos, resHistorial] = await Promise.all([
			fetch('/api/tickets?mios=0&limite=200', { headers: obtenerHeadersAuth() }),
			fetch('/api/tecnicos', { headers: obtenerHeadersAuth() }),
			fetch('/api/historial/reciente?limite=200', { headers: obtenerHeadersAuth() })
		]);

		if (!resTickets.ok) {
			mostrarToast(await mensajeDeError(resTickets, 'No se pudieron cargar los tickets.'));
			return;
		}
		ticketsGlobales = (await resTickets.json()).tickets || [];

		if (resTecnicos.ok) {
			tecnicosDisponibles = (await resTecnicos.json()).tecnicos || [];
		} else {
			// Respaldo: técnicos que ya aparecen en los tickets
			const nombres = [...new Set(ticketsGlobales.map((t) => t.tecnico).filter(Boolean))].sort();
			tecnicosDisponibles = nombres.map((nombre) => ({ id: null, nombre, activos: null }));
		}

		if (resHistorial.ok) {
			const data = await resHistorial.json();
			historialReciente = data.historial || [];
			movimientosHoy = data.movimientos_hoy || 0;
		}

		const msg = document.getElementById('page-message');
		if (msg) msg.textContent = 'Conectado a la base de datos';

		// Si uno falla, los demás siguen funcionando
		[actualizarFiltros, renderizarMetricas, renderizarCargaTrabajo, renderizarActividadReciente, aplicarFiltrosTabla].forEach(
			(fn) => {
				try {
					fn();
				} catch (e) {
					console.error(e);
				}
			}
		);
	} catch (e) {
		console.error('Error al cargar la API:', e);
		mostrarToast('Error de conexión con el servidor.');
	}
}

function actualizarFiltros() {
	const filterTech = document.getElementById('assign-tech-filter');
	if (!filterTech) return;
	const actual = filterTech.value;
	let opciones = `<option value="">Todos</option><option value="Sin asignar">Sin asignar</option>`;
	tecnicosDisponibles.forEach(
		(t) => (opciones += `<option value="${escaparHTML(t.nombre)}">${escaparHTML(t.nombre)}</option>`)
	);
	filterTech.innerHTML = opciones;
	filterTech.value = actual;
}

/* =========================================================================
   MÉTRICAS Y PANELES LATERALES
   ========================================================================= */
function renderizarMetricas() {
	const contar = (estado) => ticketsGlobales.filter((t) => t.estado === estado).length;
	const sinAsignar = ticketsGlobales.filter((t) => !t.tecnico && t.estado !== 'Cerrado').length;
	document.getElementById('metric-unassigned').textContent = sinAsignar;
	document.getElementById('metric-progress').textContent = contar('En proceso');
	document.getElementById('metric-resolved').textContent = contar('Resuelto');
	document.getElementById('metric-changes').textContent = movimientosHoy;
	document.getElementById('tab-unassigned-count').textContent = sinAsignar;
}

function cargaDe(nombre) {
	return ticketsGlobales.filter(
		(t) => t.tecnico === nombre && (t.estado === 'Abierto' || t.estado === 'En proceso')
	).length;
}

function renderizarCargaTrabajo() {
	const list = document.getElementById('workload-list');
	if (!list) return;
	if (tecnicosDisponibles.length === 0) {
		list.innerHTML = '<li class="muted">No hay técnicos activos registrados.</li>';
		return;
	}
	const maximo = Math.max(4, ...tecnicosDisponibles.map((t) => cargaDe(t.nombre)));
	list.innerHTML = tecnicosDisponibles
		.map((tec) => {
			const c = cargaDe(tec.nombre);
			return `
        <li class="workload-item">
            <span class="tech-avatar">${iniciales(tec.nombre)}</span>
            <div class="workload-info">
                <strong>${escaparHTML(tec.nombre)}</strong>
                <div class="workload-bar ${c >= 3 ? 'high' : ''}"><span style="width:${(c / maximo) * 100}%"></span></div>
            </div>
            <span class="workload-count" title="Tickets abiertos o en proceso">${c}</span>
        </li>`;
		})
		.join('');
}

function renderizarActividadReciente() {
	const feed = document.getElementById('activity-feed');
	if (!feed) return;
	const recientes = historialReciente.slice(0, 10);
	feed.innerHTML = recientes.length
		? recientes.map((h) => itemLineaDeTiempo(h, true)).join('')
		: '<li class="muted">Todavía no hay movimientos registrados.</li>';
	document.getElementById('activity-count').textContent = `Últimos ${recientes.length} movimientos`;
}

/* =========================================================================
   TABLA PRINCIPAL
   ========================================================================= */
function aplicarFiltrosTabla() {
	const searchEl = document.getElementById('assign-search');
	const statusEl = document.getElementById('assign-status-filter');
	const techEl = document.getElementById('assign-tech-filter');

	const normalizar = (s) =>
		s
			.toLowerCase()
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '');
	const q = searchEl ? normalizar(searchEl.value) : '';
	const est = statusEl ? statusEl.value : '';
	const tec = techEl ? techEl.value : '';

	const filtrados = ticketsGlobales.filter((t) => {
		if (vistaActual === 'sin-asignar' && (t.tecnico || t.estado === 'Cerrado')) return false;
		if (vistaActual === 'activos' && t.estado !== 'Abierto' && t.estado !== 'En proceso')
			return false;
		const texto = normalizar(`${t.codigo || ''} ${t.asunto || ''} ${t.solicitante || ''}`);
		if (q && !texto.includes(q)) return false;
		if (est && t.estado !== est) return false;
		if (tec === 'Sin asignar' && t.tecnico) return false;
		if (tec && tec !== 'Sin asignar' && t.tecnico !== tec) return false;
		return true;
	});

	const tbody = document.getElementById('assign-body');
	const emptyState = document.getElementById('assign-empty');
	const countLabel = document.getElementById('assign-count');
	if (!tbody) return;

	if (filtrados.length === 0) {
		tbody.innerHTML = '';
		if (emptyState) emptyState.hidden = false;
		if (countLabel) countLabel.textContent = 'Mostrando 0 tickets';
		return;
	}

	if (emptyState) emptyState.hidden = true;
	if (countLabel) countLabel.textContent = `Mostrando ${filtrados.length} de ${ticketsGlobales.length} tickets`;

	tbody.innerHTML = filtrados
		.map((t) => {
			const canAssign = t.estado === 'Abierto' || t.estado === 'En proceso';
			const canChange = (TRANSICIONES[t.estado] || []).length > 0;
			const ultimo = ultimoMovimiento(t.id);
			const fechaUlt = ultimo ? ultimo.created_at : t.created_at;
			const quien = ultimo ? ultimo.usuario : t.solicitante;

			const techHTML = t.tecnico
				? `<div class="tech-cell"><span class="tech-avatar">${iniciales(t.tecnico)}</span>${escaparHTML(t.tecnico)}</div>`
				: `<span class="tech-none"><i></i>Sin asignar</span>`;

			return `
        <tr data-id="${t.id}" class="${t.tecnico ? '' : 'unassigned'}">
            <td><a class="ticket-code" href="/detalle_ticket?id=${t.id}">${escaparHTML(t.codigo)}</a></td>
            <td class="subject-cell">
                <strong title="${escaparHTML(t.asunto)}">${escaparHTML(t.asunto)}</strong>
                <small>${escaparHTML(t.solicitante)} · ${escaparHTML(t.categoria || t.empresa)}</small>
            </td>
            <td><span class="badge ${CLASE_PRIORIDAD[t.prioridad] || ''}">${escaparHTML(t.prioridad)}</span></td>
            <td><span class="badge ${CLASE_ESTADO[t.estado] || ''}">${escaparHTML(t.estado)}</span></td>
            <td>${techHTML}</td>
            <td class="updated">
                <time datetime="${escaparHTML(fechaUlt)}" title="${fechaExacta(fechaUlt)}">${tiempoRelativo(fechaUlt)}</time>
                <small>${escaparHTML(quien)}</small>
            </td>
            <td>
                <div class="row-actions">
                    <button type="button" class="row-btn ${t.tecnico ? '' : 'primary'}" onclick="abrirModalAsignacion(${t.id})" ${canAssign ? '' : 'disabled title="No se puede reasignar un ticket resuelto o cerrado"'}><span>♙</span>${t.tecnico ? 'Reasignar' : 'Asignar'}</button>
                    <button type="button" class="row-btn icon" onclick="abrirModalEstado(${t.id})" ${canChange ? 'title="Cambiar estado"' : 'disabled title="El ticket está cerrado"'} aria-label="Cambiar estado de ${escaparHTML(t.codigo)}">⟳</button>
                    <button type="button" class="row-btn icon" onclick="abrirModalHistorial(${t.id})" title="Ver historial" aria-label="Ver historial de ${escaparHTML(t.codigo)}">◷</button>
                </div>
            </td>
        </tr>`;
		})
		.join('');
}

/* =========================================================================
   EVENTOS DE INTERFAZ Y MODALES
   ========================================================================= */
function configurarEventosUI() {
	['assign-search', 'assign-status-filter', 'assign-tech-filter'].forEach((id) => {
		document
			.getElementById(id)
			?.addEventListener(id === 'assign-search' ? 'input' : 'change', aplicarFiltrosTabla);
	});

	document.getElementById('assign-reset')?.addEventListener('click', () => {
		['assign-search', 'assign-status-filter', 'assign-tech-filter'].forEach((id) => {
			if (document.getElementById(id)) document.getElementById(id).value = '';
		});
		aplicarFiltrosTabla();
	});

	document.querySelectorAll('.quick-tab').forEach((tab) => {
		tab.addEventListener('click', (e) => {
			document.querySelectorAll('.quick-tab').forEach((t) => {
				t.classList.remove('active');
				t.setAttribute('aria-selected', 'false');
			});
			e.currentTarget.classList.add('active');
			e.currentTarget.setAttribute('aria-selected', 'true');
			vistaActual = e.currentTarget.dataset.view;
			aplicarFiltrosTabla();
		});
	});

	// Buscador del encabezado (base.html): filtra la bandeja
	const buscadorGlobal = document.querySelector('.global-search input');
	buscadorGlobal?.addEventListener('input', (e) => {
		const search = document.getElementById('assign-search');
		if (search) search.value = e.target.value;
		aplicarFiltrosTabla();
	});

	// Cerrar modales
	document.querySelectorAll('.modal').forEach((m) => {
		m.addEventListener('click', (e) => {
			if (e.target === m || e.target.closest('[data-close]')) m.hidden = true;
		});
	});
	document.addEventListener('keydown', (e) => {
		if (e.key === 'Escape') document.querySelectorAll('.modal').forEach((m) => (m.hidden = true));
	});

	// Contadores de caracteres de los comentarios
	[
		['assign-comment', 'assign-comment-count', 'assign-comment-error'],
		['status-comment', 'status-comment-count', 'status-comment-error']
	].forEach(([campo, contador, error]) => {
		document.getElementById(campo)?.addEventListener('input', (e) => {
			document.getElementById(contador).textContent = e.target.value.length;
			if (e.target.value.trim().length >= MIN_COMENTARIO) {
				document.getElementById(error).textContent = '';
				e.target.removeAttribute('aria-invalid');
			}
		});
	});

	// Vista previa del nuevo estado (un solo listener)
	document.getElementById('status-options')?.addEventListener('change', () => {
		const check = document.querySelector('input[name="new-status"]:checked');
		const prev = document.getElementById('status-preview');
		if (check && prev) {
			prev.textContent = check.value;
			prev.className = `badge ${CLASE_ESTADO[check.value] || 'category-tag'}`;
			document.getElementById('status-option-error').textContent = '';
		}
	});

	document.getElementById('auto-progress')?.addEventListener('change', actualizarReglaComentarioAsignacion);
	document.getElementById('tech-options')?.addEventListener('change', () => {
		document.getElementById('assign-tech-error').textContent = '';
	});

	document.getElementById('assign-form')?.addEventListener('submit', submitAsignacion);
	document.getElementById('status-form')?.addEventListener('submit', submitEstado);
}

/* =========================================================================
   MODAL DE ASIGNACIÓN
   ========================================================================= */
/* El comentario es obligatorio si se reasigna o si el ticket también cambia de estado */
function comentarioObligatorioEnAsignacion() {
	if (!ticketActivo) return false;
	const autoProg = document.getElementById('auto-progress').checked;
	return Boolean(ticketActivo.tecnico) || (ticketActivo.estado === 'Abierto' && autoProg);
}

function actualizarReglaComentarioAsignacion() {
	const req = document.getElementById('assign-comment-req');
	if (req) req.hidden = !comentarioObligatorioEnAsignacion();
}

window.abrirModalAsignacion = function (id) {
	ticketActivo = ticketsGlobales.find((t) => t.id === id);
	if (!ticketActivo) return;

	document.getElementById('assign-modal-title').textContent = ticketActivo.tecnico
		? 'Reasignar técnico'
		: 'Asignar técnico';
	document.getElementById('assign-ticket-label').textContent =
		`${ticketActivo.codigo} · ${ticketActivo.asunto}`;

	let radiosHTML = `<legend>Selecciona el técnico responsable <span class="req">*</span></legend>`;
	if (tecnicosDisponibles.length === 0) {
		radiosHTML += `<p class="muted">No hay técnicos activos en tu empresa.</p>`;
	}
	tecnicosDisponibles.forEach((tec) => {
		const esActual = tec.nombre === ticketActivo.tecnico;
		const carga = cargaDe(tec.nombre);
		radiosHTML += `
        <label class="option-card">
            <input type="radio" name="tech" value="${escaparHTML(tec.nombre)}" ${esActual ? 'checked' : ''}>
            <span class="tech-avatar">${iniciales(tec.nombre)}</span>
            <span><strong>${escaparHTML(tec.nombre)} ${esActual ? '<span class="current-tag">· actual</span>' : ''}</strong></span>
            <span class="load ${carga >= 3 ? 'high' : ''}">${carga} activo${carga === 1 ? '' : 's'}</span>
        </label>`;
	});
	document.getElementById('tech-options').innerHTML = radiosHTML;

	document.getElementById('auto-progress-row').hidden = ticketActivo.estado !== 'Abierto';
	document.getElementById('auto-progress').checked = true;
	document.getElementById('assign-comment').value = '';
	document.getElementById('assign-comment-count').textContent = '0';
	document.getElementById('assign-tech-error').textContent = '';
	document.getElementById('assign-comment-error').textContent = '';
	actualizarReglaComentarioAsignacion();
	document.getElementById('assign-modal').hidden = false;
};

async function submitAsignacion(e) {
	e.preventDefault();
	const radio = document.querySelector('input[name="tech"]:checked');
	const comentarioEl = document.getElementById('assign-comment');
	const comentario = comentarioEl.value.trim();
	const errTec = document.getElementById('assign-tech-error');
	const errCom = document.getElementById('assign-comment-error');
	let ok = true;

	if (!radio) {
		errTec.textContent = 'Selecciona un técnico.';
		ok = false;
	} else if (radio.value === ticketActivo.tecnico) {
		errTec.textContent = `El ticket ya está asignado a ${ticketActivo.tecnico}. Elige otro técnico.`;
		ok = false;
	} else errTec.textContent = '';

	if (comentarioObligatorioEnAsignacion() && comentario.length < MIN_COMENTARIO) {
		errCom.textContent = `El comentario es obligatorio (mínimo ${MIN_COMENTARIO} caracteres).`;
		comentarioEl.setAttribute('aria-invalid', 'true');
		ok = false;
	} else errCom.textContent = '';
	if (!ok) return;

	const datos = { tecnico: radio.value };
	if (ticketActivo.estado === 'Abierto' && document.getElementById('auto-progress').checked) {
		datos.estado = 'En proceso';
	}
	if (comentario) datos.comentario = comentario;

	try {
		const res = await fetch(`/api/tickets/${ticketActivo.id}`, {
			method: 'PUT',
			headers: obtenerHeadersAuth(),
			body: JSON.stringify(datos)
		});
		if (res.ok) {
			mostrarToast(
				`${ticketActivo.codigo} asignado a ${radio.value}${datos.estado ? ' y pasó a En proceso' : ''}.`
			);
			document.getElementById('assign-modal').hidden = true;
			cargarDatosAsignacion();
		} else {
			errTec.textContent = await mensajeDeError(res, 'No se pudo asignar el ticket.');
		}
	} catch (err) {
		mostrarToast('Error de conexión.');
	}
}

/* =========================================================================
   MODAL DE CAMBIO DE ESTADO
   ========================================================================= */
window.abrirModalEstado = function (id) {
	ticketActivo = ticketsGlobales.find((t) => t.id === id);
	if (!ticketActivo) return;

	document.getElementById('status-ticket-label').textContent =
		`${ticketActivo.codigo} · ${ticketActivo.asunto}`;
	const actual = document.getElementById('status-current');
	actual.textContent = ticketActivo.estado;
	actual.className = `badge ${CLASE_ESTADO[ticketActivo.estado] || ''}`;
	const prev = document.getElementById('status-preview');
	prev.textContent = 'Selecciona';
	prev.className = 'badge category-tag';

	const permitidos = TRANSICIONES[ticketActivo.estado] || [];
	let radiosHTML = `<legend>Nuevo estado <span class="req">*</span></legend>`;
	['Abierto', 'En proceso', 'Resuelto', 'Cerrado']
		.filter((s) => s !== ticketActivo.estado)
		.forEach((s) => {
			let motivo = '';
			if (!permitidos.includes(s)) motivo = `No permitido desde ${ticketActivo.estado}`;
			else if (s === 'En proceso' && !ticketActivo.tecnico) motivo = 'Primero asigna un técnico';
			const etiqueta = s === 'En proceso' && ticketActivo.estado === 'Resuelto' ? 'Reabrir (En proceso)' : s;
			radiosHTML += `
        <label class="status-option ${motivo ? 'disabled' : ''}">
            <input type="radio" name="new-status" value="${s}" ${motivo ? 'disabled' : ''}>
            <span>${etiqueta} <small>${motivo}</small></span>
        </label>`;
		});
	document.getElementById('status-options').innerHTML = radiosHTML;

	// Si solo hay una opción permitida, se marca sola
	const habilitados = document.querySelectorAll('input[name="new-status"]:not([disabled])');
	if (habilitados.length === 1) {
		habilitados[0].checked = true;
		habilitados[0].dispatchEvent(new Event('change', { bubbles: true }));
	}

	const comentario = document.getElementById('status-comment');
	comentario.value = '';
	comentario.removeAttribute('aria-invalid');
	document.getElementById('status-comment-count').textContent = '0';
	document.getElementById('status-comment-error').textContent = '';
	document.getElementById('status-option-error').textContent = '';
	document.getElementById('status-modal').hidden = false;
	comentario.focus();
};

async function submitEstado(e) {
	e.preventDefault();
	const radio = document.querySelector('input[name="new-status"]:checked');
	const comentarioEl = document.getElementById('status-comment');
	const comentario = comentarioEl.value.trim();
	let ok = true;

	if (!radio) {
		document.getElementById('status-option-error').textContent = 'Selecciona el nuevo estado.';
		ok = false;
	}
	if (comentario.length < MIN_COMENTARIO) {
		document.getElementById('status-comment-error').textContent =
			`El comentario es obligatorio (mínimo ${MIN_COMENTARIO} caracteres).`;
		comentarioEl.setAttribute('aria-invalid', 'true');
		ok = false;
	}
	if (!ok) return;

	try {
		const res = await fetch(`/api/tickets/${ticketActivo.id}`, {
			method: 'PUT',
			headers: obtenerHeadersAuth(),
			body: JSON.stringify({ estado: radio.value, comentario })
		});
		if (res.ok) {
			mostrarToast(`${ticketActivo.codigo}: ${ticketActivo.estado} → ${radio.value}. Registrado en el historial.`);
			document.getElementById('status-modal').hidden = true;
			cargarDatosAsignacion();
		} else {
			document.getElementById('status-option-error').textContent = await mensajeDeError(
				res,
				'No se pudo cambiar el estado.'
			);
		}
	} catch (err) {
		mostrarToast('Error de conexión.');
	}
}

/* =========================================================================
   MODAL DE HISTORIAL (línea de tiempo del ticket)
   ========================================================================= */
window.abrirModalHistorial = async function (id) {
	const t = ticketsGlobales.find((x) => x.id === id);
	try {
		const res = await fetch(`/api/tickets/${id}/historial`, { headers: obtenerHeadersAuth() });
		if (!res.ok) {
			mostrarToast(await mensajeDeError(res, 'No se pudo cargar el historial.'));
			return;
		}
		const historial = ((await res.json()).historial || []).slice().reverse(); // más reciente primero

		document.getElementById('history-ticket-label').textContent = t
			? `${t.codigo} · ${t.asunto} · ${historial.length} movimientos`
			: `${historial.length} movimientos`;
		document.getElementById('history-timeline').innerHTML = historial.length
			? historial.map((h) => itemLineaDeTiempo(h, false)).join('')
			: '<li class="muted">No hay movimientos.</li>';

		const btnIrDetalle = document.querySelector('#history-modal .btn-secondary');
		if (btnIrDetalle) btnIrDetalle.href = `/detalle_ticket?id=${id}`;
		document.getElementById('history-modal').hidden = false;
	} catch (e) {
		mostrarToast('No se pudo cargar el historial.');
	}
};
