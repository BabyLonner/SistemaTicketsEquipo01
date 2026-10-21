/* =========================================================
   tickets.js — Tickets: API, Evidencias fotográficas y Listado
   ========================================================= */

/* #########################################################
   PARTE 1 — TicketsAPI
   ######################################################### */
const TicketsAPI = (() => {
	const BASE = window.API_BASE || '';
	const MIME_PERMITIDOS = ['image/jpeg', 'image/png', 'image/webp'];
	const MAX_FOTOS = 3;
	const MAX_BYTES = 5 * 1024 * 1024;

	class ErrorAPI extends Error {
		constructor(mensaje, estado, errores = {}) {
			super(mensaje);
			this.estado = estado;
			this.errores = errores;
		}
	}

	async function pedir(ruta, opciones = {}) {
		let respuesta;
		try {
			respuesta = await fetch(BASE + ruta, { credentials: 'same-origin', ...opciones });
		} catch (e) {
			throw new ErrorAPI(
				'No se pudo conectar con el servidor. Verifica que Flask esté en ejecución.',
				0
			);
		}
		const datos = await respuesta.json().catch(() => ({}));
		if (!respuesta.ok) {
			throw new ErrorAPI(
				datos.error || datos.msg || `Error ${respuesta.status}`,
				respuesta.status,
				datos.errores || {}
			);
		}
		return datos;
	}

	function enviarConProgreso(ruta, formData, alProgresar) {
		return new Promise((resolver, rechazar) => {
			const xhr = new XMLHttpRequest();
			xhr.open('POST', BASE + ruta);
			xhr.upload.onprogress = (e) => {
				if (e.lengthComputable && alProgresar) alProgresar(Math.round((e.loaded / e.total) * 100));
			};
			xhr.onload = () => {
				let datos = {};
				try {
					datos = JSON.parse(xhr.responseText);
				} catch (e) {}
				if (xhr.status >= 200 && xhr.status < 300) resolver(datos);
				else rechazar(
					new ErrorAPI(
						datos.error || datos.msg || `Error ${xhr.status}`,
						xhr.status,
						datos.errores || {}
					)
				);
			};
			xhr.onerror = () => rechazar(new ErrorAPI('No se pudo conectar con el servidor.', 0));
			xhr.send(formData);
		});
	}

	const sesion = () => pedir('/api/tickets/sesion');
	const listar = (filtros = {}) => pedir('/api/tickets?' + new URLSearchParams(filtros));
	const obtener = (id) => pedir(`/api/tickets/${id}`);
	const crear = (formData, alProgresar) => enviarConProgreso('/api/tickets', formData, alProgresar);
	const actualizar = (id, datos) =>
		pedir(`/api/tickets/${id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(datos)
		});
	const eliminar = (id) => pedir(`/api/tickets/${id}`, { method: 'DELETE' });
	const agregarEvidencias = (id, formData, alProgresar) =>
		enviarConProgreso(`/api/tickets/${id}/evidencias`, formData, alProgresar);
	const eliminarEvidencia = (id, evidenciaId) =>
		pedir(`/api/tickets/${id}/evidencias/${evidenciaId}`, { method: 'DELETE' });

	const cacheImagenes = new Map();
	async function urlImagen(ruta) {
		if (cacheImagenes.has(ruta)) return cacheImagenes.get(ruta);
		const promesa = fetch(BASE + ruta, { credentials: 'same-origin' })
			.then((r) => {
				if (!r.ok) throw new ErrorAPI('No se pudo cargar la imagen.', r.status);
				return r.blob();
			})
			.then((blob) => URL.createObjectURL(blob));
		cacheImagenes.set(ruta, promesa);
		promesa.catch(() => cacheImagenes.delete(ruta));
		return promesa;
	}

	async function detectarMimeReal(archivo) {
		const b = new Uint8Array(await archivo.slice(0, 12).arrayBuffer());
		if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'image/jpeg';
		if ([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((v, i) => b[i] === v))
			return 'image/png';
		const texto = (desde, hasta) => String.fromCharCode(...b.slice(desde, hasta));
		if (texto(0, 4) === 'RIFF' && texto(8, 12) === 'WEBP') return 'image/webp';
		return null;
	}

	async function optimizarSiEsGrande(archivo) {
		if (archivo.size <= MAX_BYTES) return archivo;
		const bitmap = await createImageBitmap(archivo);
		const escala = Math.min(1, 1920 / Math.max(bitmap.width, bitmap.height));
		const lienzo = document.createElement('canvas');
		lienzo.width = Math.round(bitmap.width * escala);
		lienzo.height = Math.round(bitmap.height * escala);
		const ctx = lienzo.getContext('2d');
		ctx.fillStyle = '#fff';
		ctx.fillRect(0, 0, lienzo.width, lienzo.height);
		ctx.drawImage(bitmap, 0, 0, lienzo.width, lienzo.height);
		bitmap.close();
		const blob = await new Promise((ok) => lienzo.toBlob(ok, 'image/jpeg', 0.85));
		const nombre = archivo.name.replace(/\.[^.]+\$/, '') + '.jpg';
		return new File([blob], nombre, { type: 'image/jpeg' });
	}

	async function prepararFoto(archivo) {
		const extension = (archivo.name.split('.').pop() || '').toLowerCase();
		if (!['jpg', 'jpeg', 'png', 'webp'].includes(extension))
			throw new Error(`«${archivo.name}»: solo JPG, PNG o WEBP.`);
		const mimeReal = await detectarMimeReal(archivo);
		if (!mimeReal) throw new Error(`«${archivo.name}»: el contenido no es una imagen real.`);
		let lista = new File([archivo], archivo.name, { type: mimeReal });
		let optimizada = false;
		if (lista.size > MAX_BYTES) {
			try {
				lista = await optimizarSiEsGrande(lista);
				optimizada = true;
			} catch (e) {
				throw new Error(`«${archivo.name}»: no se pudo optimizar.`);
			}
			if (lista.size > MAX_BYTES) throw new Error(`«${archivo.name}»: supera 5 MB.`);
		}
		return { archivo: lista, optimizada, pesoOriginal: archivo.size };
	}

	function formatearPeso(bytes) {
		if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatearFecha(iso) {
		if (!iso) return '—';
		return new Date(iso).toLocaleString('es-PE', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	async function pintarPerfil() {
		try {
			const { usuario } = await sesion();
			const ini = usuario.nombre
				.split(/\s+/)
				.slice(0, 2)
				.map((p) => p[0])
				.join('')
				.toUpperCase();
			const avatar = document.querySelector('.profile .avatar');
			const nombre = document.querySelector('.profile-copy strong');
			const rol = document.querySelector('.profile-copy small');
			if (avatar) avatar.textContent = ini;
			if (nombre) nombre.textContent = usuario.nombre;
			if (rol) rol.textContent = usuario.rol;
			return usuario;
		} catch (e) {
			return null;
		}
	}

	return {
		ErrorAPI,
		pintarPerfil,
		MIME_PERMITIDOS,
		MAX_FOTOS,
		MAX_BYTES,
		sesion,
		listar,
		obtener,
		crear,
		actualizar,
		eliminar,
		agregarEvidencias,
		eliminarEvidencia,
		urlImagen,
		detectarMimeReal,
		prepararFoto,
		formatearPeso,
		formatearFecha
	};
})();

/* #########################################################
   PARTE 2 — Evidencias
   ######################################################### */
const Evidencias = (() => {
	const escapar = (texto) =>
		String(texto ?? '').replace(
			/[&<>"']/g,
			(c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
		);

	function avisar(mensaje) {
		const toast = document.getElementById('toast');
		if (!toast) return alert(mensaje);
		toast.textContent = mensaje;
		toast.classList.add('show');
		clearTimeout(avisar.t);
		avisar.t = setTimeout(() => toast.classList.remove('show'), 3200);
	}

	const Visor = (() => {
		let raiz, img, titulo, contador, etiquetaZoom, enlaceDescarga;
		let fotos = [],
			indice = 0,
			escala = 1,
			x = 0,
			y = 0,
			arrastre = null,
			focoPrevio = null;

		function construir() {
			raiz = document.createElement('div');
			raiz.className = 'm2-visor';
			raiz.hidden = true;
			raiz.setAttribute('role', 'dialog');
			raiz.innerHTML = `
            <div class="m2-visor__barra">
              <div class="m2-visor__info"><strong class="m2-visor__titulo"></strong><span class="m2-visor__contador"></span></div>
              <div class="m2-visor__acciones">
                <button type="button" data-accion="alejar">−</button>
                <span class="m2-visor__zoom">100%</span>
                <button type="button" data-accion="acercar">+</button>
                <button type="button" data-accion="ajustar">Ajustar</button>
                <a class="m2-visor__descargar" data-accion="descargar" download>Descargar</a>
                <button type="button" data-accion="cerrar" class="m2-visor__cerrar">×</button>
              </div>
            </div>
            <button type="button" class="m2-visor__nav m2-visor__nav--prev" data-accion="anterior">‹</button>
            <div class="m2-visor__lienzo"><img class="m2-visor__img" alt=""><span class="m2-visor__cargando">Cargando…</span></div>
            <button type="button" class="m2-visor__nav m2-visor__nav--next" data-accion="siguiente">›</button>`;
			document.body.appendChild(raiz);

			img = raiz.querySelector('.m2-visor__img');
			titulo = raiz.querySelector('.m2-visor__titulo');
			contador = raiz.querySelector('.m2-visor__contador');
			etiquetaZoom = raiz.querySelector('.m2-visor__zoom');
			enlaceDescarga = raiz.querySelector('.m2-visor__descargar');
			const lienzo = raiz.querySelector('.m2-visor__lienzo');

			raiz.addEventListener('click', (e) => {
				const accion = e.target.closest('[data-accion]')?.dataset.accion;
				if (accion === 'cerrar') cerrar();
				if (accion === 'acercar') zoom(escala * 1.4);
				if (accion === 'alejar') zoom(escala / 1.4);
				if (accion === 'ajustar') zoom(1);
				if (accion === 'anterior') mostrar(indice - 1);
				if (accion === 'siguiente') mostrar(indice + 1);
				if (e.target === lienzo) cerrar();
			});
			lienzo.addEventListener(
				'wheel',
				(e) => {
					e.preventDefault();
					zoom(escala * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
				},
				{ passive: false }
			);
			img.addEventListener('dblclick', () => zoom(escala > 1 ? 1 : 2.5));
			img.addEventListener('pointerdown', (e) => {
				if (escala > 1) {
					e.preventDefault();
					arrastre = { px: e.clientX, py: e.clientY, x, y };
					img.setPointerCapture(e.pointerId);
					img.classList.add('is-arrastrando');
				}
			});
			img.addEventListener('pointermove', (e) => {
				if (arrastre) {
					x = arrastre.x + (e.clientX - arrastre.px);
					y = arrastre.y + (e.clientY - arrastre.py);
					aplicar();
				}
			});
			const soltar = () => {
				arrastre = null;
				img.classList.remove('is-arrastrando');
			};
			img.addEventListener('pointerup', soltar);
			img.addEventListener('pointercancel', soltar);

			document.addEventListener('keydown', (e) => {
				if (raiz.hidden) return;
				if (e.key === 'Escape') cerrar();
				if (e.key === 'ArrowLeft') mostrar(indice - 1);
				if (e.key === 'ArrowRight') mostrar(indice + 1);
			});
		}

		function aplicar() {
			if (escala <= 1) {
				x = 0;
				y = 0;
			}
			img.style.transform = `translate(${x}px, ${y}px) scale(${escala})`;
			img.classList.toggle('is-ampliada', escala > 1);
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
			escala = 1;
			aplicar();
			titulo.textContent = foto.nombre || 'Evidencia';
			contador.textContent = fotos.length > 1 ? `${indice + 1} de ${fotos.length}` : '';
			raiz.classList.add('is-cargando');
			img.removeAttribute('src');
			try {
				const url = await TicketsAPI.urlImagen(foto.imagen);
				if (fotos[indice] === foto) {
					img.src = url;
					enlaceDescarga.href = url;
				}
			} catch (e) {
				avisar('No se pudo cargar la imagen.');
			} finally {
				raiz.classList.remove('is-cargando');
			}
		}

		function abrir(lista, inicio = 0) {
			if (!raiz) construir();
			fotos = lista;
			focoPrevio = document.activeElement;
			raiz.hidden = false;
			document.body.classList.add('m2-sin-scroll');
			mostrar(inicio);
		}

		function cerrar() {
			raiz.hidden = true;
			document.body.classList.remove('m2-sin-scroll');
			if (focoPrevio) focoPrevio.focus();
		}

		return { abrir, cerrar };
	})();

	function miniaturaHTML(ticket, galeria) {
		if (!ticket.miniatura_url) return `<span class="m2-mini m2-mini--vacia">▧</span>`;
		const total =
			ticket.total_evidencias > 1 ? `<b class="m2-mini__total">${ticket.total_evidencias}</b>` : '';
		return `<button type="button" class="m2-mini" data-miniatura-url="${escapar(ticket.miniatura_url)}" data-imagen-url="${escapar(ticket.imagen_url)}" data-nombre="${escapar(ticket.codigo)}" ${galeria ? `data-galeria="\${escapar(galeria)}"` : ''}>${total}</button>`;
	}

	async function hidratar(elemento) {
		if (elemento.dataset.m2Listo) return;
		elemento.dataset.m2Listo = '1';
		elemento.classList.add('is-cargando');
		const imagen = document.createElement('img');
		elemento.prepend(imagen);
		try {
			imagen.src = await TicketsAPI.urlImagen(elemento.dataset.miniaturaUrl);
		} catch (e) {
			elemento.classList.add('m2-mini--error');
		} finally {
			elemento.classList.remove('is-cargando');
		}
	}

	function hidratarTodo(contenedor = document) {
		contenedor.querySelectorAll('[data-miniatura-url]').forEach(hidratar);
	}

	document.addEventListener(
		'click',
		(e) => {
			const mini = e.target.closest('[data-imagen-url]');
			if (!mini || !mini.dataset.imagenUrl || mini.dataset.imagenUrl === 'null') return;
			e.preventDefault();
			e.stopPropagation();
			const grupo = mini.dataset.galeria
				? [
						...document.querySelectorAll(
							`[data-galeria="${CSS.escape(mini.dataset.galeria)}"][data-imagen-url]`
						)
					]
				: [mini];
			Visor.abrir(
				grupo.map((el) => ({ imagen: el.dataset.imagenUrl, nombre: el.dataset.nombre })),
				grupo.indexOf(mini)
			);
		},
		true
	);

	return { Visor, miniaturaHTML, hidratarTodo, avisar };
})();

/* #########################################################
   PARTE 3 — Listado principal de tickets
   ######################################################### */
let ticketsGlobales = [];
let ticketsFiltrados = [];
let paginaActualTickets = 1;
const ticketsPorPagina = 10;
const CLASE_PRIORIDAD = { Alta: 'priority-high', Media: 'priority-medium', Baja: 'priority-low' };
const CLASE_ESTADO = {
	Abierto: 'status-open',
	'En proceso': 'status-progress',
	Resuelto: 'status-resolved',
	Cerrado: 'status-closed'
};

document.addEventListener('DOMContentLoaded', () => {
	if (!document.getElementById('tickets-body')) return;
	configurarEventosFiltros();
	cargarListaTickets();
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

async function cargarListaTickets() {
	try {
		const res = await fetch('/api/tickets?mios=0&limite=200', {
			method: 'GET',
			headers: obtenerHeadersAuth()
		});
		if (!res.ok) {
			document.getElementById('page-message').textContent =
				'Modo demostración: El servidor no devolvió tickets.';
			return;
		}
		const data = await res.json();
		ticketsGlobales = data.tickets || [];
		actualizarFiltroTecnicos(ticketsGlobales);
		if (document.getElementById('page-message'))
			document.getElementById('page-message').textContent =
				`Datos en vivo · actualizado ${new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })}`;
		aplicarFiltrosTickets();
	} catch (e) {
		document.getElementById('page-message').textContent = 'Error de conexión con el servidor.';
	}
}

function actualizarFiltroTecnicos(tickets) {
	const selectTecnico = document.getElementById('technician-filter');
	if (!selectTecnico) return;
	const tecnicosSet = new Set();
	tickets.forEach((t) => {
		if (t.tecnico) tecnicosSet.add(t.tecnico);
	});
	let opcionesHTML = `<option value="">Todos los técnicos</option>`;
	[...tecnicosSet].sort().forEach((tec) => {
		opcionesHTML += `<option value="${escaparHTML(tec)}">${escaparHTML(tec)}</option>`;
	});
	opcionesHTML += `<option value="Sin asignar">Sin asignar</option>`;
	selectTecnico.innerHTML = opcionesHTML;
}

function calcularPlazoVisual(t) {
	if (t.estado === 'Cerrado') return { texto: '—', clase: 'sla-neutral', nivel: '' };
	if (t.estado === 'Resuelto') return { texto: 'Cumplido', clase: 'sla-ok', nivel: '' };
	if (t.semaforo) {
		if (t.semaforo === 'rojo') return { texto: 'Vencido', clase: 'sla-danger', nivel: 'Vencido' };
		if (t.semaforo === 'amarillo')
			return { texto: 'Por vencer', clase: 'sla-warning', nivel: 'Por vencer' };
		if (t.semaforo === 'verde') return { texto: 'A tiempo', clase: 'sla-ok', nivel: 'A tiempo' };
	}
	if (t.fecha_limite) {
		const horasRestantes = (new Date(t.fecha_limite) - new Date()) / (1000 * 60 * 60);
		if (horasRestantes < 0) return { texto: 'Vencido', clase: 'sla-danger', nivel: 'Vencido' };
		if (horasRestantes <= 2)
			return {
				texto: `Por vencer (${Math.ceil(horasRestantes)}h)`,
				clase: 'sla-warning',
				nivel: 'Por vencer'
			};
		return { texto: `${Math.ceil(horasRestantes)} h`, clase: 'sla-ok', nivel: 'A tiempo' };
	}
	return { texto: '—', clase: 'sla-neutral', nivel: '' };
}

function actualizarMetricasSuperiores() {
	const contar = (estado) => ticketsFiltrados.filter((t) => t.estado === estado).length;
	if (document.getElementById('metric-open'))
		document.getElementById('metric-open').textContent = contar('Abierto');
	if (document.getElementById('metric-progress'))
		document.getElementById('metric-progress').textContent = contar('En proceso');
	if (document.getElementById('metric-resolved'))
		document.getElementById('metric-resolved').textContent = contar('Resuelto');
	if (document.getElementById('metric-closed'))
		document.getElementById('metric-closed').textContent = contar('Cerrado');
	const vencidos = ticketsFiltrados.filter(
		(t) => calcularPlazoVisual(t).nivel === 'Vencido'
	).length;
	const porVencer = ticketsFiltrados.filter(
		(t) => calcularPlazoVisual(t).nivel === 'Por vencer'
	).length;
	const alerta = document.getElementById('sla-alert');
	if (alerta) {
		alerta.hidden = vencidos + porVencer === 0;
		const textoAlerta = alerta.querySelector('strong');
		if (textoAlerta)
			textoAlerta.textContent = `${vencidos} ticket(s) vencido(s) y ${porVencer} por vencer en esta vista.`;
	}
}

function aplicarFiltrosTickets() {
	const query = (document.getElementById('ticket-search')?.value || '')
		.toLowerCase()
		.normalize('NFD')
		.replace(/[\u0300-\u036f]/g, '');
	const estadoStr = document.getElementById('status-filter')?.value || '';
	const prioridadStr = document.getElementById('priority-filter')?.value || '';
	const tecnicoStr = document.getElementById('technician-filter')?.value || '';
	const verUrgentes = document.getElementById('show-urgent')?.dataset.activo === '1';
	ticketsFiltrados = ticketsGlobales.filter((t) => {
		const texto = `${t.codigo || ''} ${t.asunto || ''} ${t.solicitante || ''}`
			.toLowerCase()
			.normalize('NFD')
			.replace(/[\u0300-\u036f]/g, '');
		if (query && !texto.includes(query)) return false;
		if (estadoStr && t.estado !== estadoStr) return false;
		if (prioridadStr && t.prioridad !== prioridadStr) return false;
		if (tecnicoStr && (t.tecnico || 'Sin asignar') !== tecnicoStr) return false;
		const plazoInfo = calcularPlazoVisual(t);
		if (verUrgentes && plazoInfo.nivel !== 'Vencido' && plazoInfo.nivel !== 'Por vencer')
			return false;
		return true;
	});
	paginaActualTickets = 1;
	renderizarTablaTickets();
	actualizarMetricasSuperiores();
}

function configurarEventosFiltros() {
	['ticket-search', 'status-filter', 'priority-filter', 'technician-filter'].forEach((id) => {
		const el = document.getElementById(id);
		if (el) el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', aplicarFiltrosTickets);
	});
	document.getElementById('reset-filters')?.addEventListener('click', () => {
		['ticket-search', 'status-filter', 'priority-filter', 'technician-filter'].forEach((id) => {
			if (document.getElementById(id)) document.getElementById(id).value = '';
		});
		if (document.getElementById('show-urgent'))
			document.getElementById('show-urgent').dataset.activo = '';
		aplicarFiltrosTickets();
	});
	const btnUrgent = document.getElementById('show-urgent');
	if (btnUrgent) {
		btnUrgent.addEventListener('click', () => {
			btnUrgent.dataset.activo = btnUrgent.dataset.activo === '1' ? '' : '1';
			aplicarFiltrosTickets();
		});
	}
	document.getElementById('select-all')?.addEventListener('change', (e) => {
		document.querySelectorAll('.row-check').forEach((cb) => (cb.checked = e.target.checked));
	});
}

function formatearFechaLista(fechaISO) {
	if (!fechaISO) return '—';
	const d = new Date(fechaISO);
	return isNaN(d)
		? '—'
		: d.toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function generarFilaHTML(t) {
	const plazo = calcularPlazoVisual(t);
	const tecnico = t.tecnico || 'Sin asignar';
	const urlDetalle = `/detalle_ticket?id=${t.id}`;
	const fotoHTML = t.miniatura_url
		? `<button type="button" class="m2-mini" data-imagen-url="${escaparHTML(t.imagen_url)}"><img src="${escaparHTML(t.miniatura_url)}" alt="Evidencia"></button>`
		: `<span class="photo-icon" title="Sin foto">▧</span>`;
	return `
      <tr class="ticket-row ${plazo.nivel === 'Vencido' ? 'urgent' : ''}">
        <td><input class="row-check" type="checkbox" aria-label="Seleccionar ${escaparHTML(t.codigo)}"></td>
        <td>${fotoHTML}</td>
        <td><a class="ticket-code" href="${urlDetalle}">${escaparHTML(t.codigo)}</a></td>
        <td><strong>${escaparHTML(t.asunto)}</strong><small>${escaparHTML(t.categoria)} · ${escaparHTML(t.area)}</small></td>
        <td>${escaparHTML(t.solicitante)}<br><small>${formatearFechaLista(t.created_at)}</small></td>
        <td>${escaparHTML(tecnico)}</td>
        <td><span class="badge ${CLASE_PRIORIDAD[t.prioridad] || ''}">${escaparHTML(t.prioridad)}</span></td>
        <td><span class="badge ${CLASE_ESTADO[t.estado] || ''}">${escaparHTML(t.estado)}</span></td>
        <td><span class="sla ${plazo.clase}"><i></i>${plazo.texto}</span></td>
        <td>
            <div class="row-actions">
                <a href="${urlDetalle}" aria-label="Ver detalle">◉</a>
                ${t.estado === 'Abierto' ? `<a href="/nuevo_ticket?editar=\${t.id}" aria-label="Editar">✎</a>` : ''}
            </div>
        </td>
      </tr>
    `;
}

function renderizarTablaTickets() {
	const tbody = document.getElementById('tickets-body');
	const emptyState = document.getElementById('empty-state');
	const resultsCount = document.getElementById('results-count');
	if (!tbody || !emptyState) return;
	const total = ticketsFiltrados.length;
	const totalPaginas = Math.max(1, Math.ceil(total / ticketsPorPagina));
	paginaActualTickets = Math.min(Math.max(1, paginaActualTickets), totalPaginas);
	const inicio = (paginaActualTickets - 1) * ticketsPorPagina;
	const dataPagina = ticketsFiltrados.slice(inicio, inicio + ticketsPorPagina);
	if (total === 0) {
		tbody.innerHTML = '';
		emptyState.hidden = false;
		resultsCount.textContent = 'Mostrando 0 tickets';
	} else {
		emptyState.hidden = true;
		tbody.innerHTML = dataPagina.map(generarFilaHTML).join('');
		resultsCount.textContent = `Mostrando ${inicio + 1}–${inicio + dataPagina.length} de ${total} ticket(s)`;
	}
	renderizarPaginacion(totalPaginas);
	if (document.getElementById('select-all')) document.getElementById('select-all').checked = false;
}

function renderizarPaginacion(totalPaginas) {
	const pagContainer = document.querySelector('.pagination');
	if (!pagContainer) return;
	if (totalPaginas <= 1 && ticketsFiltrados.length === 0) {
		pagContainer.innerHTML = '';
		return;
	}
	let htmlPag = `<button type="button" data-nav="primera" ${paginaActualTickets === 1 ? 'disabled' : ''}>«</button>`;
	htmlPag += `<button type="button" data-nav="anterior" ${paginaActualTickets === 1 ? 'disabled' : ''}>‹</button>`;
	for (let i = 1; i <= totalPaginas; i++) {
		htmlPag += `<button type="button" class="page-number ${i === paginaActualTickets ? 'current' : ''}" data-page="${i}">${i}</button>`;
	}
	htmlPag += `<button type="button" data-nav="siguiente" ${paginaActualTickets === totalPaginas ? 'disabled' : ''}>›</button>`;
	htmlPag += `<button type="button" data-nav="ultima" ${paginaActualTickets === totalPaginas ? 'disabled' : ''}>»</button>`;
	pagContainer.innerHTML = htmlPag;
	pagContainer.querySelectorAll('button').forEach((btn) => {
		btn.addEventListener('click', (e) => {
			if (e.target.disabled) return;
			const nav = e.target.dataset.nav;
			const pag = e.target.dataset.page;
			if (nav === 'primera') paginaActualTickets = 1;
			else if (nav === 'anterior') paginaActualTickets--;
			else if (nav === 'siguiente') paginaActualTickets++;
			else if (nav === 'ultima') paginaActualTickets = totalPaginas;
			else if (pag) paginaActualTickets = parseInt(pag);
			renderizarTablaTickets();
		});
	});
}
