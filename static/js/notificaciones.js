(() => {
	const NOTIF_INTERVALO_MS = 10000;
	const NOTIF_POR_PAGINA = 8;
	const NOTIF_EN_CAMPANA = 5;
	const ESTILO_NOTIF = {
		NUEVO_TICKET: { clase: 'notice-blue', inicial: 'N', nombre: 'Nuevo ticket' },
		ASIGNACION: { clase: 'notice-purple', inicial: 'A', nombre: 'Asignación' },
		CAMBIO_ESTADO: { clase: 'notice-green', inicial: 'E', nombre: 'Cambio de estado' },
		COMENTARIO: { clase: 'notice-amber', inicial: 'C', nombre: 'Comentario' },
		SLA: { clase: 'notice-danger', inicial: '!', nombre: 'Alerta de SLA' }
	};

	const notif = {
		lista: [],
		filtradas: [],
		seleccion: new Set(),
		pagina: 1,
		pestana: 'all',
		firma: '',
		cargando: false
	};

	document.addEventListener('DOMContentLoaded', () => {
		document.getElementById('btnLeerTodas')?.addEventListener('click', (e) => {
			e.stopPropagation();
			marcarTodasComoLeidas();
		});
		document.getElementById('listaNotificacionesDropdown')?.addEventListener('click', (e) => {
			const item = e.target.closest('[data-notif]');
			if (item) abrirNotificacion(item.dataset);
		});
		document.addEventListener('visibilitychange', () => {
			if (!document.hidden) cargarNotificaciones();
		});
		document.addEventListener('notificaciones:actualizar', recargarNotificaciones);

		configurarPaginaNotificaciones();
		cargarNotificaciones();
		setInterval(cargarNotificaciones, NOTIF_INTERVALO_MS);
	});

	function escaparNotif(texto) {
		return String(texto ?? '').replace(
			/[&<>"']/g,
			(c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
		);
	}

	function normalizarTexto(texto) {
		return String(texto ?? '')
			.toLowerCase()
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '');
	}

	function formatearTiempo(minutos) {
		if (minutos < 1) return 'Hace un momento';
		if (minutos < 60) return `Hace ${minutos} min`;
		const horas = Math.floor(minutos / 60);
		if (horas < 24) return `Hace ${horas} h`;
		return `Hace ${Math.floor(horas / 24)} d`;
	}

	function estiloNotif(tipo) {
		return ESTILO_NOTIF[tipo] || { clase: 'notice-blue', inicial: 'T', nombre: tipo };
	}

	function enPaginaNotificaciones() {
		return Boolean(document.getElementById('contenedorPaginaNotificaciones'));
	}

	async function cargarNotificaciones() {
		if (document.hidden || notif.cargando) return;
		notif.cargando = true;
		try {
			const res = await fetch('/api/notificaciones');
			if (!res.ok) return;
			const data = await res.json();
			pintarBadge(data.resumen.no_leidas);
			if (enPaginaNotificaciones()) actualizarMetricas(data.resumen);

			const firma = data.notificaciones.map((n) => `${n.id}:${n.leido ? 1 : 0}`).join(',');
			if (firma === notif.firma) return;
			notif.firma = firma;
			notif.lista = data.notificaciones;
			const ids = new Set(notif.lista.map((n) => n.id));
			notif.seleccion.forEach((id) => ids.has(id) || notif.seleccion.delete(id));

			renderizarDropdown();
			if (enPaginaNotificaciones()) aplicarFiltros(false);
		} catch (error) {
			console.error('Error al obtener notificaciones:', error);
		} finally {
			notif.cargando = false;
		}
	}

	function recargarNotificaciones() {
		notif.firma = '';
		return cargarNotificaciones();
	}

	function pintarBadge(noLeidas) {
		const badge = document.getElementById('badgeNotificaciones');
		if (!badge) return;
		badge.textContent = noLeidas > 99 ? '99+' : noLeidas;
		badge.classList.toggle('oculto', noLeidas === 0);
	}

	function actualizarMetricas(resumen) {
		const valores = {
			'total-count': resumen.total,
			'unread-count': resumen.no_leidas,
			'ticket-count': resumen.tickets,
			'system-count': resumen.sistema
		};
		Object.entries(valores).forEach(([id, valor]) => {
			const el = document.getElementById(id);
			if (el) el.textContent = valor;
		});
	}

	function renderizarDropdown() {
		const contenedor = document.getElementById('listaNotificacionesDropdown');
		if (!contenedor) return;
		const recientes = notif.lista.slice(0, NOTIF_EN_CAMPANA);
		if (recientes.length === 0) {
			contenedor.innerHTML =
				'<div class="notif-dropdown__empty">No tienes notificaciones recientes.</div>';
			return;
		}
		contenedor.innerHTML = recientes
			.map(
				(n) => `
				<div class="notif-item ${n.leido ? '' : 'notif-item--unread'}" ${datosNotif(n)}>
					<div class="notif-item__content">
						<div class="notif-item__top">
							<span class="notif-item__title">${escaparNotif(n.titulo)}</span>
							${n.leido ? '' : '<span class="notif-item__dot"></span>'}
						</div>
						<p class="notif-item__msg">${escaparNotif(n.mensaje)}</p>
						<span class="notif-item__time">${formatearTiempo(n.hace_minutos)}</span>
					</div>
				</div>`
			)
			.join('');
	}

	function datosNotif(n) {
		return `data-notif="${n.id}" data-ticket="${n.referencia_ticket ?? ''}" data-leido="${n.leido ? 1 : 0}"`;
	}

	function configurarPaginaNotificaciones() {
		const contenedor = document.getElementById('contenedorPaginaNotificaciones');
		if (!contenedor) return;

		document.querySelectorAll('.tabs .tab').forEach((tab) => {
			tab.addEventListener('click', () => {
				document.querySelectorAll('.tabs .tab').forEach((t) => {
					t.classList.toggle('active', t === tab);
					t.setAttribute('aria-selected', String(t === tab));
				});
				notif.pestana = tab.dataset.type || 'all';
				aplicarFiltros(true);
			});
		});

		document
			.getElementById('notification-search')
			?.addEventListener('input', () => aplicarFiltros(true));
		document.getElementById('sort-order')?.addEventListener('change', () => aplicarFiltros(true));
		document.getElementById('apply-filters')?.addEventListener('click', () => {
			aplicarFiltros(true);
			mostrarAlertaFlotante('Filtros aplicados');
		});
		document.getElementById('mark-all-read-page')?.addEventListener('click', marcarTodasComoLeidas);

		contenedor.addEventListener('change', (e) => {
			if (!e.target.classList.contains('row-check')) return;
			const id = Number(e.target.closest('[data-notif]').dataset.notif);
			if (e.target.checked) notif.seleccion.add(id);
			else notif.seleccion.delete(id);
			actualizarBarraSeleccion();
		});
		contenedor.addEventListener('click', (e) => {
			const boton = e.target.closest('.notice-menu');
			if (boton) abrirNotificacion(boton.closest('[data-notif]').dataset);
		});

		document.querySelector('.pagination')?.addEventListener('click', (e) => {
			const boton = e.target.closest('button[data-page]');
			if (!boton || boton.disabled) return;
			notif.pagina = Number(boton.dataset.page);
			renderizarPagina();
		});

		document.getElementById('clear-selection')?.addEventListener('click', () => {
			notif.seleccion.clear();
			renderizarPagina();
		});
		document
			.getElementById('mark-selected-read')
			?.addEventListener('click', marcarSeleccionComoLeidas);
		document.getElementById('delete-selected')?.addEventListener('click', eliminarSeleccion);
	}

	function aplicarFiltros(reiniciarPagina) {
		const busqueda = normalizarTexto(document.getElementById('notification-search')?.value);
		const orden = document.getElementById('sort-order')?.value || 'newest';
		const tipo = document.getElementById('type-filter')?.value || '';
		const estado = document.getElementById('state-filter')?.value || '';
		const fecha = document.getElementById('date-filter')?.value || '';
		const maxMinutos = { today: 1440, week: 10080 }[fecha];

		notif.filtradas = notif.lista.filter((n) => {
			if (notif.pestana === 'unread' && n.leido) return false;
			if (notif.pestana === 'ticket' && n.categoria !== 'ticket') return false;
			if (tipo && n.tipo !== tipo) return false;
			if (estado === 'unread' && n.leido) return false;
			if (estado === 'read' && !n.leido) return false;
			if (maxMinutos && n.hace_minutos > maxMinutos) return false;
			return !busqueda || normalizarTexto(`${n.titulo} ${n.mensaje}`).includes(busqueda);
		});
		notif.filtradas.sort((a, b) => (orden === 'oldest' ? a.id - b.id : b.id - a.id));

		if (reiniciarPagina) notif.pagina = 1;
		renderizarPagina();
	}

	function renderizarPagina() {
		const contenedor = document.getElementById('contenedorPaginaNotificaciones');
		if (!contenedor) return;

		const total = notif.filtradas.length;
		const totalPaginas = Math.max(1, Math.ceil(total / NOTIF_POR_PAGINA));
		notif.pagina = Math.min(Math.max(1, notif.pagina), totalPaginas);
		const inicio = (notif.pagina - 1) * NOTIF_POR_PAGINA;
		const visibles = notif.filtradas.slice(inicio, inicio + NOTIF_POR_PAGINA);

		contenedor.innerHTML =
			total === 0
				? `<div class="empty-state">
					<span aria-hidden="true">📭</span>
					<strong>No se encontraron notificaciones</strong>
					<p>Prueba ajustando los filtros de búsqueda.</p>
				</div>`
				: visibles.map(filaNotificacion).join('');

		const etiqueta = document.getElementById('results-label');
		if (etiqueta) etiqueta.textContent = `Mostrando ${visibles.length} de ${total} notificaciones`;

		renderizarPaginacion(totalPaginas);
		actualizarBarraSeleccion();
	}

	function filaNotificacion(n) {
		const estilo = estiloNotif(n.tipo);
		const marcada = notif.seleccion.has(n.id) ? 'checked' : '';
		return `
			<div class="notification-row ${n.leido ? '' : 'unread'}" ${datosNotif(n)}>
				<input class="row-check" type="checkbox" aria-label="Seleccionar notificación" ${marcada}>
				<div class="notice-icon ${estilo.clase}" title="${escaparNotif(estilo.nombre)}">${estilo.inicial}</div>
				<div class="notice-content">
					<div class="notice-title">
						${escaparNotif(n.titulo)}
						${n.leido ? '' : '<span class="priority-tag">Nueva</span>'}
					</div>
					<p>${escaparNotif(n.mensaje)}</p>
				</div>
				<time title="${escaparNotif(n.fecha)}">${formatearTiempo(n.hace_minutos)}</time>
				<div class="unread-dot" aria-hidden="true"></div>
				<button type="button" class="notice-menu" title="Ver detalles">◉</button>
			</div>`;
	}

	function renderizarPaginacion(totalPaginas) {
		const paginacion = document.querySelector('.pagination');
		if (!paginacion) return;
		const actual = notif.pagina;
		let html = `<button type="button" aria-label="Página anterior" data-page="${actual - 1}" ${actual === 1 ? 'disabled' : ''}>‹</button>`;
		for (let i = 1; i <= totalPaginas; i++) {
			html += `<button class="page-number ${i === actual ? 'active' : ''}" type="button" data-page="${i}">${i}</button>`;
		}
		html += `<button type="button" aria-label="Página siguiente" data-page="${actual + 1}" ${actual === totalPaginas ? 'disabled' : ''}>›</button>`;
		paginacion.innerHTML = html;
	}

	function actualizarBarraSeleccion() {
		const barra = document.getElementById('bulk-toolbar');
		if (!barra) return;
		barra.hidden = notif.seleccion.size === 0;
		document.getElementById('selected-count').textContent =
			`${notif.seleccion.size} seleccionada(s)`;
	}

	async function enviarAccion(url, cuerpo) {
		const res = await fetch(url, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: cuerpo ? JSON.stringify(cuerpo) : undefined
		});
		const datos = await res.json().catch(() => ({}));
		if (!res.ok) throw new Error(datos.error || 'No se pudo completar la acción.');
		return datos;
	}

	async function abrirNotificacion({ notif: id, ticket, leido }) {
		try {
			if (leido === '0') await enviarAccion(`/api/notificaciones/${id}/leer`);
		} catch (error) {
			console.error('Error al marcar la notificación:', error);
		}
		if (ticket) window.location.href = `/detalle_ticket?id=${ticket}`;
		else recargarNotificaciones();
	}

	async function marcarTodasComoLeidas() {
		try {
			const datos = await enviarAccion('/api/notificaciones/leer-todas');
			mostrarAlertaFlotante(`${datos.marcadas} notificación(es) marcada(s) como leída(s).`);
			await recargarNotificaciones();
		} catch (error) {
			mostrarAlertaFlotante(error.message);
		}
	}

	async function marcarSeleccionComoLeidas() {
		try {
			const datos = await enviarAccion('/api/notificaciones/leer-seleccion', {
				ids: [...notif.seleccion]
			});
			notif.seleccion.clear();
			mostrarAlertaFlotante(`${datos.marcadas} notificación(es) marcada(s) como leída(s).`);
			await recargarNotificaciones();
		} catch (error) {
			mostrarAlertaFlotante(error.message);
		}
	}

	async function eliminarSeleccion() {
		const cantidad = notif.seleccion.size;
		if (!confirm(`¿Eliminar ${cantidad} notificación(es)? Esta acción no se puede deshacer.`))
			return;
		try {
			const datos = await enviarAccion('/api/notificaciones/eliminar', {
				ids: [...notif.seleccion]
			});
			notif.seleccion.clear();
			mostrarAlertaFlotante(`${datos.eliminadas} notificación(es) eliminada(s).`);
			await recargarNotificaciones();
		} catch (error) {
			mostrarAlertaFlotante(error.message);
		}
	}

	function mostrarAlertaFlotante(mensaje) {
		const toast = document.getElementById('toast');
		if (!toast) return;
		toast.textContent = mensaje;
		toast.classList.add('show');
		setTimeout(() => toast.classList.remove('show'), 3000);
	}
})();
