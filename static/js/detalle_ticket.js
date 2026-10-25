/* =========================================================
   detalle_ticket.js — Lógica conectada a la API real
   ========================================================= */

document.addEventListener('DOMContentLoaded', () => {
	const idTicket = new URLSearchParams(window.location.search).get('id');
	if (!idTicket) {
		mostrarToast('No se especificó un ID de ticket válido.');
		return;
	}

	cargarDetalleTicket(idTicket);
	configurarEventosPanelDerecho(idTicket);
});

function obtenerHeadersAuth() {
	const headers = { 'Content-Type': 'application/json' };
	const token = localStorage.getItem('token');
	if (token) headers['Authorization'] = `Bearer ${token}`;
	return headers;
}

function escaparHTML(texto) {
	return String(texto ?? '').replace(
		/[&<>"']/g,
		(c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
	);
}

function formatearFecha(isoStr) {
	if (!isoStr) return '—';
	const d = new Date(isoStr);
	return isNaN(d)
		? '—'
		: d.toLocaleString('es-PE', {
				day: '2-digit',
				month: '2-digit',
				year: 'numeric',
				hour: '2-digit',
				minute: '2-digit'
			});
}

function iniciales(nombre) {
	return (nombre || 'US')
		.split(/\s+/)
		.slice(0, 2)
		.map((p) => p[0])
		.join('')
		.toUpperCase();
}

function mostrarToast(msg) {
	const toast = document.getElementById('toast');
	if (!toast) return;
	toast.textContent = msg;
	toast.classList.add('show');
	setTimeout(() => toast.classList.remove('show'), 3000);
}

const CLASE_PRIORIDAD = { Alta: 'priority-high', Media: 'priority-medium', Baja: 'priority-low' };
const CLASE_ESTADO = {
	Abierto: 'status-open',
	'En proceso': 'status-progress',
	Resuelto: 'status-resolved',
	Cerrado: 'status-closed'
};

/* =========================================================================
   CARGAR DATOS DESDE LA API
   ========================================================================= */
async function cargarDetalleTicket(id) {
	try {
		const res = await fetch(`/api/tickets/${id}`, { method: 'GET', headers: obtenerHeadersAuth() });
		if (!res.ok) {
			document.getElementById('ticket-subject').textContent = 'Error al cargar el ticket';
			return;
		}

		const data = await res.json();
		const t = data.ticket;
		if (!t) return;

		// 1. Cabecera y Título
		document.getElementById('breadcrumb-code').textContent = escaparHTML(t.codigo);
		document.getElementById('ticket-code').textContent = escaparHTML(t.codigo);
		document.getElementById('ticket-subject').textContent = escaparHTML(t.asunto);

		// 2. Etiquetas (Tags) Superiores
		document.getElementById('ticket-priority-tag').className =
			`badge ${CLASE_PRIORIDAD[t.prioridad] || ''}`;
		document.getElementById('ticket-priority-tag').textContent = `▥ ${escaparHTML(t.prioridad)}`;

		document.getElementById('ticket-status-tag').className =
			`badge ${CLASE_ESTADO[t.estado] || ''}`;
		document.getElementById('ticket-status-tag').textContent = `▤ ${escaparHTML(t.estado)}`;

		const tagCategoria = document.querySelectorAll('.ticket-tags .category-tag')[0];
		const tagEmpresa = document.querySelectorAll('.ticket-tags .category-tag')[1];
		if (tagCategoria) tagCategoria.textContent = `◉ ${escaparHTML(t.categoria)}`;
		if (tagEmpresa) tagEmpresa.textContent = `▦ ${escaparHTML(t.empresa)}`;

		// 3. Descripción y Metadatos (Panel Izquierdo)
		document.getElementById('ticket-description').textContent = escaparHTML(t.descripcion);

		const metadataItems = document.querySelectorAll('.metadata-item strong');
		if (metadataItems.length >= 4) {
			metadataItems[0].textContent = escaparHTML(t.solicitante);
			metadataItems[1].textContent = escaparHTML(t.area);
			metadataItems[2].textContent = escaparHTML(t.empresa);
			metadataItems[3].textContent = formatearFecha(t.created_at);
		}

		// 4. Panel Lateral Derecho (Estado y Configuración)
		const selEstado = document.getElementById('property-status');
		const selPrio = document.getElementById('property-priority');
		const selCat = document.getElementById('property-category');
		const selTec = document.getElementById('property-technician');

		if (selEstado) selEstado.value = t.estado;
		if (selPrio) selPrio.value = t.prioridad;
		if (selCat && [...selCat.options].some((o) => o.value === t.categoria))
			selCat.value = t.categoria;

		// Manejar el técnico en el select
		if (selTec) {
			const tecValue = t.tecnico || 'Sin asignar';
			if (![...selTec.options].some((o) => o.value === tecValue)) {
				selTec.add(new Option(tecValue, tecValue));
			}
			selTec.value = tecValue;
		}

		// 5. Historial (Línea de tiempo)
		renderizarHistorial(t.historial || []);

		document.getElementById('page-message').textContent =
			`Conectado a la base de datos · Ticket cargado correctamente.`;
	} catch (e) {
		console.error('Error al obtener detalle del ticket:', e);
		mostrarToast('No se pudo conectar con el servidor.');
	}
}

/* =========================================================================
   HISTORIAL (Línea de Tiempo)
   ========================================================================= */
function renderizarHistorial(historialArray) {
	const list = document.getElementById('history-timeline');
	const counter = document.getElementById('history-count');
	const tabCounter = document.getElementById('history-tab-count');

	if (!list) return;

	if (counter) counter.textContent = `${historialArray.length} movimientos`;
	if (tabCounter) tabCounter.textContent = historialArray.length;

	if (historialArray.length === 0) {
		list.innerHTML = `<li>No hay movimientos registrados.</li>`;
		return;
	}

	list.innerHTML = historialArray
		.map((h) => {
			let iconoStr = '●';
			let claseColor = '';

			if (
				h.accion.toLowerCase().includes('creado') ||
				h.accion.toLowerCase().includes('registro')
			) {
				iconoStr = '＋';
				claseColor = 't-open';
			} else if (h.accion.toLowerCase().includes('estado')) {
				iconoStr = '⟳';
				claseColor = 't-progress';
			} else if (h.accion.toLowerCase().includes('asignado')) {
				iconoStr = '♙';
				claseColor = 't-assign';
			} else if (h.accion.toLowerCase().includes('resuelto')) {
				iconoStr = '✓';
				claseColor = 't-resolved';
			}

			const fechaFormat = formatearFecha(h.created_at);

			return `
        <li class="tl-item">
            <span class="tl-icon ${claseColor}" aria-hidden="true">${iconoStr}</span>
            <div class="tl-body">
                <div class="tl-title">${escaparHTML(h.accion)}</div>
                <div class="tl-meta">
                    <span>${escaparHTML(h.usuario)}</span>
                    <time datetime="${h.created_at}" title="${fechaFormat}">${fechaFormat}</time>
                </div>
                ${h.comentario ? `<p class="tl-comment">\${escaparHTML(h.comentario)}</p>` : ''}
            </div>
        </li>
        `;
		})
		.join('');
}

/* =========================================================================
   ACTUALIZAR TICKET (Panel Lateral Derecho)
   ========================================================================= */
function configurarEventosPanelDerecho(ticketId) {
	const formPanel = document.getElementById('ticket-properties');

	if (formPanel) {
		formPanel.addEventListener('submit', async (e) => {
			e.preventDefault();

			const estadoNuevo = document.getElementById('property-status')?.value;
			const prioNueva = document.getElementById('property-priority')?.value;
			const catNueva = document.getElementById('property-category')?.value;
			let tecNuevo = document.getElementById('property-technician')?.value;

			if (tecNuevo === 'Sin asignar') tecNuevo = null;

			const datos = {
				estado: estadoNuevo,
				prioridad: prioNueva,
				categoria: catNueva,
				tecnico: tecNuevo
			};

			const btnSave = formPanel.querySelector('.save-button');
			if (btnSave) {
				btnSave.disabled = true;
				btnSave.innerHTML = `<span>...</span>Guardando`;
			}

			try {
				const res = await fetch(`/api/tickets/${ticketId}`, {
					method: 'PUT',
					headers: obtenerHeadersAuth(),
					body: JSON.stringify(datos)
				});

				if (res.ok) {
					mostrarToast('Ticket actualizado correctamente.');
					// Recargar los datos para refrescar la interfaz (etiquetas e historial)
					cargarDetalleTicket(ticketId);
				} else {
					const err = await res.json();
					mostrarToast(err.msg || 'Error al actualizar.');
				}
			} catch (error) {
				mostrarToast('Error de conexión al guardar cambios.');
			} finally {
				if (btnSave) {
					btnSave.disabled = false;
					btnSave.innerHTML = `<span>▣</span>Guardar cambios`;
				}
			}
		});
	}

	// Lógica para las pestañas centrales (Tabs)
	document.querySelectorAll('.tab').forEach((tab) => {
		tab.addEventListener('click', () => {
			document.querySelectorAll('.tab').forEach((item) => {
				item.classList.toggle('active', item === tab);
				item.setAttribute('aria-selected', String(item === tab));
			});
			document.querySelectorAll('.tab-content').forEach((content) => (content.hidden = true));
			const panel = document.getElementById(`tab-${tab.dataset.tab}`);
			if (panel) panel.hidden = false;
		});
	});

	// Accesos directos: Botón Cerrar Ticket
	const btnCerrar = document.getElementById('close-ticket');
	if (btnCerrar) {
		btnCerrar.addEventListener('click', () => {
			const selStatus = document.getElementById('property-status');
			if (selStatus) {
				selStatus.value = 'Cerrado';
				formPanel.dispatchEvent(new Event('submit'));
			}
		});
	}
}
