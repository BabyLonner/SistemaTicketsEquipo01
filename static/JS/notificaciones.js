/* =========================================================
   notificaciones.js — Gestión global de la campana y la vista completa
   ========================================================= */

document.addEventListener('DOMContentLoaded', () => {
	const btnCampana = document.getElementById('btnCampanaNotif');
	const dropdown = document.getElementById('dropdownNotificaciones');
	const wrapper = document.getElementById('notifWrapper');
	const btnLeerTodas = document.getElementById('btnLeerTodas');

	// 1. Abrir / Cerrar el menú desplegable al hacer clic en la campana
	if (btnCampana && dropdown) {
		btnCampana.addEventListener('click', (e) => {
			e.stopPropagation();
			dropdown.classList.toggle('oculto');
		});

		// Cerrar el dropdown si el usuario hace clic fuera
		document.addEventListener('click', (e) => {
			if (wrapper && !wrapper.contains(e.target)) {
				dropdown.classList.add('oculto');
			}
		});
	}

	// 2. Botón "Marcar todas como leídas" en la campana
	if (btnLeerTodas) {
		btnLeerTodas.addEventListener('click', (e) => {
			e.stopPropagation();
			marcarTodasComoLeidas();
		});
	}

	// 3. Inicializar carga
	cargarNotificaciones();
	// Actualizar cada 30 segundos para no saturar el servidor
	setInterval(cargarNotificaciones, 30000);
});

// Función auxiliar para los headers (si usas tokens locales, aunque Flask ya maneja la sesión por cookies)
function obtenerHeadersAuth() {
	const headers = { 'Content-Type': 'application/json' };
	const token = localStorage.getItem('token');
	if (token) {
		headers['Authorization'] = `Bearer ${token}`;
	}
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

// Obtiene el ícono y color según el tipo de notificación (Tickets vs Sistema)
function obtenerEstiloIcono(tipo) {
	if (tipo === 'sistema') return { icono: '⚙', clase: 'notice-system', inicial: 'S' };
	if (tipo === 'alerta') return { icono: '!', clase: 'notice-danger', inicial: 'A' };
	return { icono: '▤', clase: 'notice-blue', inicial: 'T' }; // Por defecto: ticket
}

async function cargarNotificaciones() {
	try {
		const res = await fetch('/api/notificaciones', {
			method: 'GET',
			headers: obtenerHeadersAuth()
		});

		if (!res.ok) return;
		const data = await res.json();
		if (!data.ok) return;

		// Actualizar el contador rojo (Badge) de la campana
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

		// Renderizar lista en el dropdown de la campana (formato miniatura)
		const contenedorDropdown = document.getElementById('listaNotificacionesDropdown');
		if (contenedorDropdown) {
			renderizarDropdown(contenedorDropdown, data.notificaciones);
		}

		// Renderizar en notificaciones.html si estamos en esa página (formato fila)
		const contenedorPagina = document.getElementById('contenedorPaginaNotificaciones');
		if (contenedorPagina) {
			renderizarPaginaCompleta(contenedorPagina, data.notificaciones, data.no_leidas);
		}
	} catch (error) {
		console.error('Error al obtener notificaciones:', error);
	}
}

/* =========================================================================
   RENDER 1: Para el Dropdown de la campana
   ========================================================================= */
function renderizarDropdown(contenedor, notificaciones) {
	if (!notificaciones || notificaciones.length === 0) {
		contenedor.innerHTML = `<div class="notif-dropdown__empty">No tienes notificaciones recientes.</div>`;
		return;
	}

	// Solo mostramos las últimas 5 en la campana
	const recientes = notificaciones.slice(0, 5);

	contenedor.innerHTML = recientes
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
            </div>
        `;
		})
		.join('');
}

/* =========================================================================
   RENDER 2: Para la página completa (notificaciones_2.html)
   ========================================================================= */
function renderizarPaginaCompleta(contenedor, notificaciones, noLeidas) {
	// Actualizamos las tarjetas de métricas superiores
	const totalCount = document.getElementById('total-count');
	const unreadCount = document.getElementById('unread-count');

	if (totalCount) totalCount.textContent = notificaciones.length;
	if (unreadCount) unreadCount.textContent = noLeidas;

	if (!notificaciones || notificaciones.length === 0) {
		contenedor.innerHTML = `
            <div class="empty-state">
                <span aria-hidden="true">📭</span>
                <strong>No hay notificaciones</strong>
                <p>Estás al día con todas las actividades del sistema.</p>
            </div>`;
		return;
	}

	contenedor.innerHTML = notificaciones
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

/* =========================================================================
   ACCIONES
   ========================================================================= */
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
		console.error('Error al marcar todas como leídas:', error);
	}
}

// Utilidad para mostrar el toast en pantalla grande
function mostrarAlertaFlotante(mensaje) {
	const toast = document.getElementById('toast');
	if (toast) {
		toast.textContent = mensaje;
		toast.classList.add('show');
		setTimeout(() => toast.classList.remove('show'), 3000);
	}
}
