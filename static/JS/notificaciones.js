/* =========================================================
   notificaciones.js — Gestión global, filtros y paginación
   ========================================================= */

// Variables de estado para la página completa
let notificacionesGlobales = [];
let notificacionesFiltradas = [];
let idsOcultos = new Set(); // Para las notificaciones que el usuario decida "ocultar" de la vista
let paginaActual = 1;
const itemsPorPagina = 8;
let pestanaActual = 'all';

document.addEventListener('DOMContentLoaded', () => {
	// 1. Lógica de la Campana (Header)
	const btnCampana = document.getElementById('btnCampanaNotif');
	const dropdown = document.getElementById('dropdownNotificaciones');
	const wrapper = document.getElementById('notifWrapper');
	const btnLeerTodas = document.getElementById('btnLeerTodas');

	if (btnCampana && dropdown) {
		btnCampana.addEventListener('click', (e) => {
			e.stopPropagation();
			dropdown.classList.toggle('oculto');
		});
		document.addEventListener('click', (e) => {
			if (wrapper && !wrapper.contains(e.target)) dropdown.classList.add('oculto');
		});
	}

	if (btnLeerTodas) {
		btnLeerTodas.addEventListener('click', (e) => {
			e.stopPropagation();
			marcarTodasComoLeidas();
		});
	}

	// 2. Lógica de la página completa (Tabs, Búsqueda, Filtros)
	configurarEventosPagina();

	// 3. Inicializar carga
	cargarNotificaciones();
	setInterval(cargarNotificaciones, 30000);
});

function obtenerHeadersAuth() {
	const headers = { 'Content-Type': 'application/json' };
	const token = localStorage.getItem('token');
	if (token) headers['Authorization'] = `Bearer ${token}`;
	return headers;
}

function formatearTiempo(minutos) {
	if (minutos < 1) return 'Hace un momento';
	if (minutos < 60) return `Hace ${minutos} min`;
	const horas = Math.floor(minutos / 60);
	if (horas < 24) return `Hace ${horas} h`;
	const dias = Math.floor(horas / 24);
	return `Hace ${dias} d`;
}

function obtenerEstiloIcono(tipo) {
	const t = (tipo || '').toLowerCase();
	if (t === 'sistema' || t === 'system')
		return { icono: '⚙', clase: 'notice-system', inicial: 'S' };
	if (t === 'alerta') return { icono: '!', clase: 'notice-danger', inicial: 'A' };
	return { icono: '▤', clase: 'notice-blue', inicial: 'T' };
}

/* =========================================================================
   CARGA DE DATOS DESDE LA API
   ========================================================================= */
async function cargarNotificaciones() {
	try {
		const res = await fetch('/api/notificaciones', {
			method: 'GET',
			headers: obtenerHeadersAuth()
		});
		if (!res.ok) return;
		const data = await res.json();
		if (!data.ok) return;

		// Guardamos los datos en memoria para paginar y filtrar rápido
		notificacionesGlobales = data.notificaciones || [];

		// Actualizar el Badge rojo de la campana
		const badge = document.getElementById('badgeNotificaciones');
		if (badge) {
			if (data.no_leidas > 0) {
				badge.textContent = data.no_leidas > 99 ? '99+' : data.no_leidas;
				badge.classList.remove('oculto');
			} else {
				badge.textContent = '0';
				badge.classList.add('oculto');
			}
		}

		// Renderizar en la campana (solo las últimas 5)
		const contenedorDropdown = document.getElementById('listaNotificacionesDropdown');
		if (contenedorDropdown) {
			renderizarDropdown(contenedorDropdown, notificacionesGlobales.slice(0, 5));
		}

		// Si estamos en la página de notificaciones, aplicar los filtros y paginar
		if (document.getElementById('contenedorPaginaNotificaciones')) {
			actualizarMetricas();
			aplicarFiltros();
		}
	} catch (error) {
		console.error('Error al obtener notificaciones:', error);
	}
}

function actualizarMetricas() {
	const visibles = notificacionesGlobales.filter((n) => !idsOcultos.has(n.id));
	const noLeidas = visibles.filter((n) => n.leido === 0).length;
	const tickets = visibles.filter((n) => (n.tipo || '').toLowerCase() === 'ticket').length;
	const sistema = visibles.filter(
		(n) => (n.tipo || '').toLowerCase() === 'sistema' || (n.tipo || '').toLowerCase() === 'system'
	).length;

	if (document.getElementById('total-count'))
		document.getElementById('total-count').textContent = visibles.length;
	if (document.getElementById('unread-count'))
		document.getElementById('unread-count').textContent = noLeidas;
	if (document.getElementById('ticket-count'))
		document.getElementById('ticket-count').textContent = tickets;
	if (document.getElementById('system-count'))
		document.getElementById('system-count').textContent = sistema;
}

/* =========================================================================
   SISTEMA DE FILTRADO Y ORDENAMIENTO (Página Completa)
   ========================================================================= */
function aplicarFiltros() {
	const searchInput = document.getElementById('notification-search');
	const query = searchInput
		? searchInput.value
				.toLowerCase()
				.normalize('NFD')
				.replace(/[\u0300-\u036f]/g, '')
		: '';
	const sort = document.getElementById('sort-order')?.value || 'newest';

	// Filtros del panel derecho
	const typeFilter = document.getElementById('type-filter')?.value.toLowerCase() || '';
	const stateFilter = document.getElementById('state-filter')?.value || '';
	const dateFilter = document.getElementById('date-filter')?.value || '';

	notificacionesFiltradas = notificacionesGlobales.filter((n) => {
		// 1. Si el usuario la "eliminó" de su vista temporal
		if (idsOcultos.has(n.id)) return false;

		// 2. Filtro de Pestañas (Tabs)
		if (pestanaActual === 'unread' && n.leido !== 0) return false;
		if (pestanaActual === 'ticket' && (n.tipo || '').toLowerCase() !== 'ticket') return false;

		// 3. Filtros del panel derecho
		if (typeFilter && (n.tipo || '').toLowerCase() !== typeFilter) return false;
		if (stateFilter === 'unread' && n.leido !== 0) return false;
		if (stateFilter === 'read' && n.leido === 0) return false;
		if (dateFilter === 'today' && n.hace_minutos > 1440) return false; // 24 horas
		if (dateFilter === 'week' && n.hace_minutos > 10080) return false; // 7 días

		// 4. Búsqueda Textual
		const texto = `${n.titulo} ${n.mensaje}`
			.toLowerCase()
			.normalize('NFD')
			.replace(/[\u0300-\u036f]/g, '');
		if (query && !texto.includes(query)) return false;

		return true;
	});

	// Ordenar (hace_minutos: menor valor es más reciente)
	notificacionesFiltradas.sort((a, b) => {
		if (sort === 'oldest') return b.hace_minutos - a.hace_minutos;
		return a.hace_minutos - b.hace_minutos;
	});

	// Reiniciar a la página 1 cada vez que se filtran datos
	paginaActual = 1;
	renderizarPaginacion();
}

/* =========================================================================
   SISTEMA DE PAGINACIÓN Y RENDER (Página Completa)
   ========================================================================= */
function renderizarPaginacion() {
	const contenedorPagina = document.getElementById('contenedorPaginaNotificaciones');
	if (!contenedorPagina) return;

	const total = notificacionesFiltradas.length;
	const totalPaginas = Math.max(1, Math.ceil(total / itemsPorPagina));
	paginaActual = Math.min(Math.max(1, paginaActual), totalPaginas);

	const inicio = (paginaActual - 1) * itemsPorPagina;
	const fin = inicio + itemsPorPagina;
	const paginaActualDatos = notificacionesFiltradas.slice(inicio, fin);

	// 1. Renderizar el HTML de los items
	if (total === 0) {
		contenedorPagina.innerHTML = `
            <div class="empty-state">
                <span aria-hidden="true">📭</span>
                <strong>No se encontraron notificaciones</strong>
                <p>Prueba ajustando los filtros de búsqueda.</p>
            </div>`;
	} else {
		contenedorPagina.innerHTML = paginaActualDatos
			.map((n) => {
				const claseUnread = n.leido === 0 ? 'unread' : '';
				const tiempo = formatearTiempo(n.hace_minutos);
				const estilo = obtenerEstiloIcono(n.tipo);

				return `
                <div class="notification-row ${claseUnread}" data-id="${n.id}">
                    <input class="row-check" type="checkbox" aria-label="Seleccionar notificación">
                    <div class="notice-icon ${estilo.clase}">${estilo.inicial}</div>
                    <div class="notice-content">
                        <div class="notice-title">
                            ${n.titulo}
                            ${n.leido === 0 ? '<span class="priority-tag">Nueva</span>' : ''}
                        </div>
                        <p>${n.mensaje || ''}</p>
                    </div>
                    <time>${tiempo}</time>
                    <div class="unread-dot" aria-hidden="true"></div>
                    <button type="button" class="notice-menu" onclick="abrirNotificacion(${n.id}, ${n.referencia_ticket}, ${n.leido})" title="Ver detalles">◉</button>
                </div>
            `;
			})
			.join('');
	}

	// 2. Renderizar Controles de Paginación UI
	const resultsLabel = document.getElementById('results-label');
	if (resultsLabel) {
		resultsLabel.textContent = `Mostrando ${paginaActualDatos.length} de ${total} notificaciones`;
	}

	const pagContainer = document.querySelector('.pagination');
	if (pagContainer) {
		let htmlPag = `<button id="prev-page" type="button" aria-label="Página anterior" ${paginaActual === 1 ? 'disabled' : ''}>‹</button>`;
		for (let i = 1; i <= totalPaginas; i++) {
			htmlPag += `<button class="page-number ${i === paginaActual ? 'active' : ''}" type="button" data-page="${i}">${i}</button>`;
		}
		htmlPag += `<button id="next-page" type="button" aria-label="Página siguiente" ${paginaActual === totalPaginas ? 'disabled' : ''}>›</button>`;
		pagContainer.innerHTML = htmlPag;

		// Bind clicks de paginación
		pagContainer.querySelector('#prev-page').addEventListener('click', () => {
			if (paginaActual > 1) {
				paginaActual--;
				renderizarPaginacion();
			}
		});
		pagContainer.querySelector('#next-page').addEventListener('click', () => {
			if (paginaActual < totalPaginas) {
				paginaActual++;
				renderizarPaginacion();
			}
		});
		pagContainer.querySelectorAll('.page-number').forEach((btn) => {
			btn.addEventListener('click', (e) => {
				paginaActual = parseInt(e.target.dataset.page);
				renderizarPaginacion();
			});
		});
	}

	actualizarBarraSeleccion(); // Esconde la barra múltiple al cambiar de página
}

/* =========================================================================
   EVENTOS DE UI Y BARRA MÚLTIPLE (Página Completa)
   ========================================================================= */
function configurarEventosPagina() {
	if (!document.getElementById('contenedorPaginaNotificaciones')) return;

	// Pestañas (Todas, No leídas, Tickets)
	document.querySelectorAll('.tabs .tab').forEach((tab) => {
		tab.addEventListener('click', (e) => {
			document.querySelectorAll('.tabs .tab').forEach((t) => t.classList.remove('active'));
			e.target.classList.add('active');
			pestanaActual = e.target.dataset.type || 'all';
			aplicarFiltros();
		});
	});

	// Inputs inmediatos
	document.getElementById('notification-search')?.addEventListener('input', aplicarFiltros);
	document.getElementById('sort-order')?.addEventListener('change', aplicarFiltros);

	// Botón "Aplicar filtros" panel derecho
	document.getElementById('apply-filters')?.addEventListener('click', () => {
		aplicarFiltros();
		mostrarAlertaFlotante('Filtros aplicados');
	});

	// Checkboxes y barra múltiple
	document.getElementById('contenedorPaginaNotificaciones').addEventListener('change', (e) => {
		if (e.target.classList.contains('row-check')) actualizarBarraSeleccion();
	});

	document.getElementById('clear-selection')?.addEventListener('click', () => {
		document.querySelectorAll('.row-check').forEach((cb) => (cb.checked = false));
		actualizarBarraSeleccion();
	});

	document.getElementById('mark-selected-read')?.addEventListener('click', async () => {
		const checkboxes = document.querySelectorAll('.row-check:checked');
		const promises = [];
		checkboxes.forEach((cb) => {
			const id = cb.closest('.notification-row').dataset.id;
			promises.push(
				fetch(`/api/notificaciones/${id}/leer`, { method: 'POST', headers: obtenerHeadersAuth() })
			);
		});
		await Promise.all(promises);
		document.getElementById('bulk-toolbar').hidden = true;
		mostrarAlertaFlotante(`${checkboxes.length} notificación(es) marcada(s) como leída(s).`);
		cargarNotificaciones(); // Recargamos para actualizar el badge y JSON
	});

	document.getElementById('delete-selected')?.addEventListener('click', () => {
		const checkboxes = document.querySelectorAll('.row-check:checked');
		checkboxes.forEach((cb) => {
			const id = parseInt(cb.closest('.notification-row').dataset.id);
			idsOcultos.add(id); // La "eliminamos" visualmente del frontend
		});
		document.getElementById('bulk-toolbar').hidden = true;
		actualizarMetricas();
		aplicarFiltros();
		mostrarAlertaFlotante(`${checkboxes.length} notificación(es) ocultada(s).`);
	});
}

function actualizarBarraSeleccion() {
	const seleccionados = document.querySelectorAll('.row-check:checked').length;
	const toolbar = document.getElementById('bulk-toolbar');
	if (toolbar) {
		toolbar.hidden = seleccionados === 0;
		document.getElementById('selected-count').textContent = `${seleccionados} seleccionada(s)`;
	}
}

/* =========================================================================
   ACCIONES A LA API (Comunes)
   ========================================================================= */
function renderizarDropdown(contenedor, notificaciones) {
	if (!notificaciones || notificaciones.length === 0) {
		contenedor.innerHTML = `<div class="notif-dropdown__empty">No tienes notificaciones recientes.</div>`;
		return;
	}
	contenedor.innerHTML = notificaciones
		.map((n) => {
			const claseNoLeida = n.leido === 0 ? 'notif-item--unread' : '';
			const tiempo = formatearTiempo(n.hace_minutos);
			return `
            <div class="notif-item ${claseNoLeida}" onclick="abrirNotificacion(${n.id}, ${n.referencia_ticket}, ${n.leido})">
                <div class="notif-item__content">
                    <div class="notif-item__top">
                        <span class="notif-item__title">${n.titulo}</span>
                        ${n.leido === 0 ? '<span class="notif-item__dot"></span>' : ''}
                    </div>
                    <p class="notif-item__msg">${n.mensaje || ''}</p>
                    <span class="notif-item__time">${tiempo}</span>
                </div>
            </div>`;
		})
		.join('');
}

async function abrirNotificacion(notifId, ticketId, yaLeido) {
	try {
		if (yaLeido === 0) {
			await fetch(`/api/notificaciones/${notifId}/leer`, {
				method: 'POST',
				headers: obtenerHeadersAuth()
			});
		}
		if (ticketId) {
			window.location.href = `/detalle_ticket?id=${ticketId}`;
		} else {
			cargarNotificaciones();
		}
	} catch (error) {
		console.error('Error al marcar notificación:', error);
	}
}

async function marcarTodasComoLeidas() {
	try {
		const res = await fetch('/api/notificaciones/leer-todas', {
			method: 'POST',
			headers: obtenerHeadersAuth()
		});
		if (res.ok) {
			cargarNotificaciones();
			mostrarAlertaFlotante('Todas las notificaciones marcadas como leídas');
		}
	} catch (error) {
		console.error('Error al marcar todas:', error);
	}
}

function mostrarAlertaFlotante(mensaje) {
	const toast = document.getElementById('toast');
	if (toast) {
		toast.textContent = mensaje;
		toast.classList.add('show');
		setTimeout(() => toast.classList.remove('show'), 3000);
	}
}
