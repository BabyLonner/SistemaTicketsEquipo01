/* =========================================================
   asignacion.js — Funcionalidad conectada a la API de Flask
   (Versión robusta y tolerante a fallos de datos)
   ========================================================= */

let ticketsGlobales = [];
let tecnicosDisponibles = [];
let vistaActual = 'todos'; // 'todos', 'sin-asignar', 'activos'
let ticketActivo = null;

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
	if (isNaN(date.getTime())) return '—'; // Previene error si la fecha de BD es inválida
	const min = Math.floor(Math.max(0, Date.now() - date.getTime()) / 60000);
	if (min < 1) return 'hace un momento';
	if (min < 60) return `hace ${min} min`;
	const h = Math.floor(min / 60);
	if (h < 24) return `hace ${h} h`;
	const d = Math.floor(h / 24);
	if (d === 1) return 'ayer';
	return `hace ${d} días`;
}

function mostrarToast(msg) {
	const toast = document.getElementById('toast');
	if (!toast) return;
	toast.textContent = msg;
	toast.classList.add('show');
	setTimeout(() => toast.classList.remove('show'), 3000);
}

/* =========================================================================
   CARGA PRINCIPAL DE DATOS CON PROTECCIÓN (TRY/CATCH)
   ========================================================================= */
async function cargarDatosAsignacion() {
	try {
		const res = await fetch('/api/tickets?mios=0&limite=200', { headers: obtenerHeadersAuth() });
		if (!res.ok) return;
		const data = await res.json();
		ticketsGlobales = data.tickets || [];

		const tecnicosSet = new Set();
		ticketsGlobales.forEach((t) => {
			if (t.tecnico) tecnicosSet.add(t.tecnico);
		});
		tecnicosDisponibles = [...tecnicosSet].sort();

		if (tecnicosDisponibles.length === 0) {
			tecnicosDisponibles = ['Luis Ramos', 'Carla Mendoza', 'Pedro Salazar'];
		}

		// Si uno falla, los demás siguen funcionando
		try {
			actualizarFiltros();
		} catch (e) {
			console.error(e);
		}
		try {
			renderizarMetricas();
		} catch (e) {
			console.error(e);
		}
		try {
			renderizarCargaTrabajo();
		} catch (e) {
			console.error(e);
		}
		try {
			renderizarActividadReciente();
		} catch (e) {
			console.error(e);
		}
		try {
			aplicarFiltrosTabla();
		} catch (e) {
			console.error(e);
		}
	} catch (e) {
		console.error('Error al cargar la API:', e);
	}
}

function actualizarFiltros() {
	const filterTech = document.getElementById('assign-tech-filter');
	if (!filterTech) return;
	const actual = filterTech.value;
	let opciones = `<option value="">Todos</option><option value="Sin asignar">Sin asignar</option>`;
	tecnicosDisponibles.forEach(
		(t) => (opciones += `<option value="${escaparHTML(t)}">${escaparHTML(t)}</option>`)
	);
	filterTech.innerHTML = opciones;
	filterTech.value = actual;
}

/* =========================================================================
   MÉTRICAS Y PANELES LATERALES
   ========================================================================= */
function renderizarMetricas() {
	const contar = (estado) => ticketsGlobales.filter((t) => t.estado === estado).length;
	document.getElementById('metric-unassigned').textContent = ticketsGlobales.filter(
		(t) => !t.tecnico && t.estado !== 'Cerrado'
	).length;
	document.getElementById('metric-progress').textContent = contar('En proceso');
	document.getElementById('metric-resolved').textContent = contar('Resuelto');

	const hoy = new Date().toLocaleDateString('es-PE');
	const movHoy = ticketsGlobales.filter((t) => {
		if (!t.updated_at) return false;
		const d = new Date(t.updated_at);
		return !isNaN(d.getTime()) && d.toLocaleDateString('es-PE') === hoy;
	}).length;

	document.getElementById('metric-changes').textContent = movHoy;
	document.getElementById('tab-unassigned-count').textContent = ticketsGlobales.filter(
		(t) => !t.tecnico && t.estado !== 'Cerrado'
	).length;
}

function renderizarCargaTrabajo() {
	const list = document.getElementById('workload-list');
	if (!list) return;
	const carga = {};
	tecnicosDisponibles.forEach((t) => (carga[t] = 0));
	ticketsGlobales.forEach((t) => {
		if (t.tecnico && (t.estado === 'Abierto' || t.estado === 'En proceso')) {
			carga[t.tecnico] = (carga[t.tecnico] || 0) + 1;
		}
	});

	let html = '';
	Object.keys(carga)
		.sort()
		.forEach((tec) => {
			const c = carga[tec];
			const color = c >= 8 ? 'red' : c >= 5 ? 'amber' : 'green';
			html += `
        <li class="workload-item">
            <span class="tech-avatar">${initials(tec)}</span>
            <div class="workload-info">
                <strong>${escaparHTML(tec)}</strong>
                <div class="workload-bar ${color}"><span style="width:${Math.min(100, (c / 10) * 100)}%"></span></div>
            </div>
            <span class="workload-count" title="Tickets activos">${c}</span>
        </li>`;
		});
	list.innerHTML = html;
}

function renderizarActividadReciente() {
	const feed = document.getElementById('activity-feed');
	if (!feed) return;

	// Sort seguro evitando el problema de NaN con fechas inválidas
	const recientes = [...ticketsGlobales]
		.sort((a, b) => {
			const timeA = new Date(a.updated_at || a.created_at || 0).getTime() || 0;
			const timeB = new Date(b.updated_at || b.created_at || 0).getTime() || 0;
			return timeB - timeA;
		})
		.slice(0, 8);

	feed.innerHTML = recientes
		.map((t) => {
			let icono = '●';
			let clase = '';
			let desc = 'Ticket actualizado';
			if (t.estado === 'Abierto') {
				icono = '＋';
				clase = 't-open';
				desc = 'Ticket creado · estado inicial Abierto';
			} else if (t.estado === 'Resuelto') {
				icono = '✓';
				clase = 't-resolved';
				desc = `Estado: En proceso → Resuelto`;
			} else if (t.estado === 'Cerrado') {
				icono = '■';
				clase = 't-closed';
				desc = `Estado: Resuelto → Cerrado`;
			} else {
				icono = '⟳';
				clase = 't-progress';
				desc = `Ticket en proceso`;
			}

			return `
        <li class="tl-item">
            <span class="tl-icon ${clase}">${icono}</span>
            <div class="tl-body">
                <div class="tl-title"><a href="/detalle_ticket?id=${t.id}">${escaparHTML(t.codigo)}</a> · ${desc}</div>
                <div class="tl-meta">
                    <span>${escaparHTML(t.solicitante)}</span>
                    <time>${tiempoRelativo(t.updated_at || t.created_at)}</time>
                </div>
            </div>
        </li>`;
		})
		.join('');
	document.getElementById('activity-count').textContent = `Últimos ${recientes.length} movimientos`;
}

/* =========================================================================
   TABLA PRINCIPAL
   ========================================================================= */
function aplicarFiltrosTabla() {
	const searchEl = document.getElementById('assign-search');
	const statusEl = document.getElementById('assign-status-filter');
	const techEl = document.getElementById('assign-tech-filter');

	const q = searchEl
		? searchEl.value
				.toLowerCase()
				.normalize('NFD')
				.replace(/[\u0300-\u036f]/g, '')
		: '';
	const est = statusEl ? statusEl.value : '';
	const tec = techEl ? techEl.value : '';

	const filtrados = ticketsGlobales.filter((t) => {
		if (vistaActual === 'sin-asignar' && (t.tecnico || t.estado === 'Cerrado')) return false;
		if (vistaActual === 'activos' && t.estado !== 'Abierto' && t.estado !== 'En proceso')
			return false;

		const texto = `${t.codigo || ''} ${t.asunto || ''} ${t.solicitante || ''}`
			.toLowerCase()
			.normalize('NFD')
			.replace(/[\u0300-\u036f]/g, '');
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
	if (countLabel) countLabel.textContent = `Mostrando ${filtrados.length} tickets`;

	tbody.innerHTML = filtrados
		.map((t) => {
			const canAssign = t.estado === 'Abierto' || t.estado === 'En proceso';
			const transPermitidas = TRANSICIONES[t.estado] || [];
			const canChange = transPermitidas.length > 0;

			const btnAssignClass = t.tecnico ? '' : 'primary';
			const btnAssignText = t.tecnico ? 'Reasignar' : 'Asignar';
			const techHTML = t.tecnico
				? `<div class="tech-cell"><span class="tech-avatar">${initials(t.tecnico)}</span>${escaparHTML(t.tecnico)}</div>`
				: `<span class="tech-none"><i></i>Sin asignar</span>`;

			return `
        <tr data-id="${t.id}" class="${t.tecnico ? '' : 'unassigned'}">
            <td><a class="ticket-code" href="/detalle_ticket?id=${t.id}">${escaparHTML(t.codigo)}</a></td>
            <td class="subject-cell">
                <strong title="${escaparHTML(t.asunto)}">${escaparHTML(t.asunto)}</strong>
                <small>${escaparHTML(t.solicitante)} · ${escaparHTML(t.empresa || t.categoria)}</small>
            </td>
            <td><span class="badge ${CLASE_PRIORIDAD[t.prioridad] || ''}">${escaparHTML(t.prioridad)}</span></td>
            <td><span class="badge ${CLASE_ESTADO[t.estado] || ''}">${escaparHTML(t.estado)}</span></td>
            <td>${techHTML}</td>
            <td class="updated">
                <time>${tiempoRelativo(t.updated_at || t.created_at)}</time>
                <small>${escaparHTML(t.solicitante)}</small>
            </td>
            <td>
                <div class="row-actions">
                    <button type="button" class="row-btn ${btnAssignClass}" onclick="abrirModalAsignacion(${t.id})" ${canAssign ? '' : 'disabled title="Cerrado/Resuelto"'}><span>♙</span>${btnAssignText}</button>
                    <button type="button" class="row-btn icon" onclick="abrirModalEstado(${t.id})" ${canChange ? '' : 'disabled title="Estado final"'} aria-label="Cambiar estado">⟳</button>
                    <button type="button" class="row-btn icon" onclick="abrirModalHistorial(${t.id})" aria-label="Ver historial">◷</button>
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

	// Cerrar modales
	document.querySelectorAll('.modal').forEach((m) => {
		m.addEventListener('click', (e) => {
			if (e.target === m || e.target.closest('[data-close]')) m.hidden = true;
		});
	});
	document.addEventListener('keydown', (e) => {
		if (e.key === 'Escape') document.querySelectorAll('.modal').forEach((m) => (m.hidden = true));
	});

	// Modales Submit
	document.getElementById('assign-form')?.addEventListener('submit', submitAsignacion);
	document.getElementById('status-form')?.addEventListener('submit', submitEstado);
}

/* =========================================================================
   MODAL DE ASIGNACIÓN
   ========================================================================= */
window.abrirModalAsignacion = function (id) {
	ticketActivo = ticketsGlobales.find((t) => t.id === id);
	if (!ticketActivo) return;

	document.getElementById('assign-modal-title').textContent = ticketActivo.tecnico
		? 'Reasignar técnico'
		: 'Asignar técnico';
	document.getElementById('assign-ticket-label').textContent =
		`${ticketActivo.codigo} · ${ticketActivo.asunto}`;

	let radiosHTML = `<legend>Selecciona el técnico responsable <span class="req">*</span></legend>`;
	tecnicosDisponibles.forEach((tec) => {
		const isCurrent = tec === ticketActivo.tecnico;
		radiosHTML += `
        <label class="option-card">
            <input type="radio" name="tech" value="${escaparHTML(tec)}" ${isCurrent ? 'checked' : ''}>
            <span class="tech-avatar">${initials(tec)}</span>
            <span><strong>${escaparHTML(tec)} ${isCurrent ? '<span class="current-tag">· actual</span>' : ''}</strong></span>
        </label>`;
	});
	document.getElementById('tech-options').innerHTML = radiosHTML;

	document.getElementById('auto-progress-row').hidden = ticketActivo.estado !== 'Abierto';
	document.getElementById('assign-comment').value = '';
	document.getElementById('assign-tech-error').textContent = '';
	document.getElementById('assign-modal').hidden = false;
};

async function submitAsignacion(e) {
	e.preventDefault();
	const radio = document.querySelector('input[name="tech"]:checked');
	if (!radio) {
		document.getElementById('assign-tech-error').textContent = 'Selecciona un técnico.';
		return;
	}

	const comment = document.getElementById('assign-comment').value.trim();
	const autoProg = document.getElementById('auto-progress').checked;

	const datos = { tecnico: radio.value };
	if (ticketActivo.estado === 'Abierto' && autoProg) datos.estado = 'En proceso';
	if (comment) datos.comentario = comment;

	try {
		const res = await fetch(`/api/tickets/${ticketActivo.id}`, {
			method: 'PUT',
			headers: obtenerHeadersAuth(),
			body: JSON.stringify(datos)
		});
		if (res.ok) {
			mostrarToast(`Ticket asignado exitosamente.`);
			document.getElementById('assign-modal').hidden = true;
			cargarDatosAsignacion();
		} else mostrarToast('Error al asignar el ticket.');
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
	document.getElementById('status-current').textContent = ticketActivo.estado;
	document.getElementById('status-current').className =
		`badge ${CLASE_ESTADO[ticketActivo.estado] || ''}`;

	const permitidos = TRANSICIONES[ticketActivo.estado] || [];
	let radiosHTML = `<legend>Nuevo estado <span class="req">*</span></legend>`;

	['Abierto', 'En proceso', 'Resuelto', 'Cerrado']
		.filter((s) => s !== ticketActivo.estado)
		.forEach((s) => {
			const isDisabled = !permitidos.includes(s) || (s === 'En proceso' && !ticketActivo.tecnico);
			let reason = '';
			if (!permitidos.includes(s)) reason = `No permitido desde ${ticketActivo.estado}`;
			else if (s === 'En proceso' && !ticketActivo.tecnico)
				reason = 'Requiere asignar un técnico primero';

			radiosHTML += `
        <label class="status-option ${isDisabled ? 'disabled' : ''}">
            <input type="radio" name="new-status" value="${s}" ${isDisabled ? 'disabled' : ''}>
            <span>${s} <small>${reason}</small></span>
        </label>`;
		});

	document.getElementById('status-options').innerHTML = radiosHTML;
	document.getElementById('status-comment').value = '';
	document.getElementById('status-modal').hidden = false;

	document.getElementById('status-options').addEventListener('change', () => {
		const check = document.querySelector('input[name="new-status"]:checked');
		const prev = document.getElementById('status-preview');
		if (check && prev) {
			prev.textContent = check.value;
			prev.className = `badge ${CLASE_ESTADO[check.value] || 'category-tag'}`;
		}
	});
};

async function submitEstado(e) {
	e.preventDefault();
	const radio = document.querySelector('input[name="new-status"]:checked');
	const comment = document.getElementById('status-comment').value.trim();

	if (!radio) {
		mostrarToast('Selecciona el nuevo estado.');
		return;
	}
	if (comment.length < 10) {
		document.getElementById('status-comment-error').textContent = 'Mínimo 10 caracteres.';
		return;
	}

	try {
		const res = await fetch(`/api/tickets/${ticketActivo.id}`, {
			method: 'PUT',
			headers: obtenerHeadersAuth(),
			body: JSON.stringify({ estado: radio.value, comentario: comment })
		});
		if (res.ok) {
			mostrarToast(`Estado cambiado a ${radio.value}.`);
			document.getElementById('status-modal').hidden = true;
			cargarDatosAsignacion();
		} else mostrarToast('Error al cambiar estado.');
	} catch (err) {
		mostrarToast('Error de conexión.');
	}
}

/* =========================================================================
   MODAL DE HISTORIAL RÁPIDO
   ========================================================================= */
window.abrirModalHistorial = async function (id) {
	try {
		const res = await fetch(`/api/tickets/${id}`, { headers: obtenerHeadersAuth() });
		if (!res.ok) return;
		const data = await res.json();
		const t = data.ticket;

		document.getElementById('history-ticket-label').textContent = `${t.codigo} · ${t.asunto}`;
		const tl = document.getElementById('history-timeline');

		if (!t.historial || t.historial.length === 0) {
			tl.innerHTML = `<li>No hay movimientos.</li>`;
		} else {
			tl.innerHTML = t.historial
				.map((h) => {
					let icono = '●';
					let clase = '';
					if (h.accion.toLowerCase().includes('creado')) {
						icono = '＋';
						clase = 't-open';
					} else if (h.accion.toLowerCase().includes('asignado')) {
						icono = '♙';
						clase = 't-assign';
					} else {
						icono = '⟳';
						clase = 't-progress';
					}

					const d = new Date(h.created_at);
					const fechaFormat = isNaN(d.getTime()) ? '—' : d.toLocaleString('es-PE');
					return `
                <li class="tl-item">
                    <span class="tl-icon ${clase}" aria-hidden="true">${icono}</span>
                    <div class="tl-body">
                        <div class="tl-title">${escaparHTML(h.accion)}</div>
                        <div class="tl-meta"><span>${escaparHTML(h.usuario)}</span><time>${fechaFormat}</time></div>
                        ${h.comentario ? `<p class="tl-comment">\${escaparHTML(h.comentario)}</p>` : ''}
                    </div>
                </li>`;
				})
				.join('');
		}

		const btnIrDetalle = document.querySelector('#history-modal .btn-secondary');
		if (btnIrDetalle) btnIrDetalle.href = `/detalle_ticket?id=${t.id}`;
		document.getElementById('history-modal').hidden = false;
	} catch (e) {
		mostrarToast('No se pudo cargar el historial.');
	}
};
