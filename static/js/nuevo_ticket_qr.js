/* =========================================================
   nuevo_ticket_qr.js — MÓDULO 3 (avance 2): escanear la etiqueta QR
   - Lee el QR con la cámara del celular o la laptop (html5-qrcode)
     o desde una foto de la etiqueta (si no hay cámara).
   - También funciona si el celular abrió el enlace del QR con su cámara normal:
     llega aquí como /nuevo_ticket?equipo=TOKEN.
   - Pide al servidor el equipo, su ubicación y su historial (GET /api/equipos/qr/<token>)
     y lo muestra en el formulario. Al enviar, nuevo_ticket.js manda el token.
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const $ = (id) => document.getElementById(id);
	const seccion = $('qr-seccion');
	if (!seccion) return;

	const params = new URLSearchParams(location.search);
	if (params.get('editar')) {
		seccion.hidden = true; // al editar un ticket no se cambia el equipo
		return;
	}

	const inputToken = $('equipo-token');
	const ficha = $('qr-ficha');
	const vacio = $('qr-vacio');
	const caja = $('qr-error');
	const modal = $('qr-modal');
	const estado = $('qr-estado');
	const PATRON_TOKEN = /^[A-Za-z0-9_-]{12,24}$/;
	const CATEGORIA_POR_TIPO = { Impresora: 'Impresoras', 'Equipo de red': 'Red e internet' };

	let lector = null;      // instancia de Html5Qrcode
	let camaras = [];
	let camaraActual = 0;
	let leyendo = false;

	const escapar = (t) =>
		String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
	const fecha = (iso) => new Date(iso).toLocaleDateString('es-PE', { day: '2-digit', month: 'short', year: 'numeric' });

	function error(texto, titulo = 'No se pudo usar este QR.') {
		caja.innerHTML = texto ? `<b>${escapar(titulo)}</b> ${escapar(texto)}` : '';
		caja.hidden = !texto;
	}

	/* ---------- 1. Del texto del QR al token ----------
	   Solo se aceptan enlaces de ESTE sistema (mismo dominio). Un QR de otra
	   página, un texto cualquiera o un enlace modificado se rechaza aquí,
	   y el servidor vuelve a comprobarlo (token + empresa). */
	function extraerToken(texto) {
		let url;
		try {
			url = new URL(String(texto).trim());
		} catch (e) {
			throw new Error('El QR no contiene un enlace del sistema de tickets.');
		}
		// localhost y 127.0.0.1 son la misma computadora (solo pasa en pruebas locales)
		const local = (h) => h === 'localhost' || h === '127.0.0.1';
		let hostEtiquetas = '';
		try { hostEtiquetas = new URL(seccion.dataset.urlPublica).host; } catch (e) { /* sin APP_URL_PUBLICA */ }
		const mismoSitio = url.host === location.host || url.host === hostEtiquetas ||
			(local(url.hostname) && local(location.hostname) && url.port === location.port);
		if (!mismoSitio) {
			throw new Error(`El QR apunta a otro sitio (${url.host}). Solo se aceptan etiquetas de este sistema.`);
		}
		const token = url.pathname.match(/^\/qr\/([^/]+)\/?$/)?.[1] || url.searchParams.get('equipo') || '';
		if (!PATRON_TOKEN.test(token)) throw new Error('El enlace del QR está incompleto o fue modificado.');
		return token;
	}

	/* ---------- 2. Pedir el equipo al servidor ---------- */
	async function cargarEquipo(token) {
		error('');
		ficha.hidden = false;
		ficha.innerHTML = '<p class="qr-equipo__cargando">Buscando el equipo…</p>';
		try {
			const res = await fetch(`/api/equipos/qr/${encodeURIComponent(token)}`);
			const d = await res.json().catch(() => ({}));
			if (res.status === 401) return (location.href = '/');
			if (!res.ok) throw new Error(d.error || 'No se pudo leer el equipo.');
			mostrarEquipo(d.equipo, d.historial);
		} catch (e) {
			limpiar();
			error(e.message);
		}
	}

	function mostrarEquipo(eq, historial) {
		inputToken.value = eq.token;
		vacio.hidden = true;
		ficha.hidden = false;
		const pendientes = historial.filter((h) => h.estado === 'Abierto' || h.estado === 'En proceso');
		ficha.innerHTML = `
			<div class="qr-ficha__cabecera">
				<span class="qr-ficha__ok" aria-hidden="true">✓</span>
				<div>
					<small>Equipo vinculado por QR</small>
					<h3>${escapar(eq.codigo)} · ${escapar(eq.nombre)}</h3>
				</div>
				<button type="button" class="qr-ficha__quitar" id="qr-quitar">Quitar</button>
			</div>
			<dl class="qr-ficha__datos">
				<div><dt>Ubicación</dt><dd>📍 ${escapar(eq.ubicacion)}</dd></div>
				<div><dt>Área</dt><dd>${escapar(eq.area || 'Sin área')}</dd></div>
				<div><dt>Tipo</dt><dd>${escapar(eq.tipo)}</dd></div>
				<div><dt>Marca / modelo</dt><dd>${escapar([eq.marca, eq.modelo].filter(Boolean).join(' ') || '—')}</dd></div>
				${eq.serie ? `<div><dt>N.º de serie</dt><dd>${escapar(eq.serie)}</dd></div>` : ''}
			</dl>
			${pendientes.length ? `<p class="qr-ficha__aviso">⚠ Este equipo ya tiene ${pendientes.length} ticket(s) sin resolver. Revisa si tu problema es el mismo antes de registrar otro.</p>` : ''}
			<h4>Historial de incidencias (${eq.total_tickets})</h4>
			${historial.length ? `<ul class="qr-ficha__historial">${historial.map((h) => `
				<li>
					<a href="/detalle_ticket?id=${h.id}">${escapar(h.codigo)}</a>
					<span>${escapar(h.asunto)}</span>
					<em class="qr-estado qr-estado--${escapar(h.estado.replace(' ', '-').toLowerCase())}">${escapar(h.estado)}</em>
					<small>${fecha(h.created_at)} · ${escapar(h.tecnico)}</small>
				</li>`).join('')}</ul>`
				: '<p class="qr-ficha__sin">Sin incidencias anteriores: es el primer ticket de este equipo.</p>'}`;
		$('qr-quitar').addEventListener('click', () => {
			limpiar();
			history.replaceState(null, '', location.pathname);
		});

		// Se completan el área y la categoría (el usuario puede cambiarlas)
		const area = $('area');
		const categoria = $('category');
		const poner = () => {
			if (eq.area_id && area && [...area.options].some((o) => o.value === String(eq.area_id))) area.value = eq.area_id;
			if (categoria && !categoria.value) {
				const nombre = CATEGORIA_POR_TIPO[eq.tipo] || 'Hardware';
				const op = [...categoria.options].find((o) => o.textContent.trim() === nombre);
				if (op) categoria.value = op.value;
			}
			area?.dispatchEvent(new Event('change'));
			categoria?.dispatchEvent(new Event('change'));
		};
		setTimeout(poner, 450); // nuevo_ticket.js llena las listas al cargar
		const asunto = $('subject');
		if (asunto && !asunto.value) asunto.placeholder = `Ej. ${eq.codigo} no enciende / muestra un error`;
	}

	function limpiar() {
		inputToken.value = '';
		ficha.hidden = true;
		ficha.innerHTML = '';
		vacio.hidden = false;
	}

	/* ---------- 3. Cámara (html5-qrcode) ---------- */
	function mensajeCamara(e) {
		const nombre = e?.name || '';
		const texto = String(e?.message || e || '');
		if (!window.isSecureContext) return 'La cámara solo funciona con HTTPS o en localhost. Usa «Subir foto del QR».';
		if (nombre === 'NotAllowedError' || /permission|denied/i.test(texto))
			return 'Negaste el permiso de la cámara. Actívalo en el candado de la barra de direcciones o usa «Subir foto del QR».';
		if (nombre === 'NotFoundError' || /not found|no camera|Requested device/i.test(texto))
			return 'No se encontró ninguna cámara en este dispositivo. Usa «Subir foto del QR».';
		if (nombre === 'NotReadableError' || /in use|could not start/i.test(texto))
			return 'La cámara está ocupada por otra aplicación. Ciérrala e inténtalo otra vez.';
		return 'No se pudo abrir la cámara. Usa «Subir foto del QR».';
	}

	async function abrirLector() {
		error('');
		if (typeof Html5Qrcode === 'undefined') return error('No se cargó el lector de QR (html5-qrcode).');
		modal.hidden = false;
		estado.textContent = 'Abriendo la cámara…';
		estado.className = 'qr-modal__estado';
		try {
			if (!window.isSecureContext) throw new Error('inseguro');
			if (!camaras.length) camaras = await Html5Qrcode.getCameras();
			if (!camaras.length) throw Object.assign(new Error('no camera'), { name: 'NotFoundError' });
			$('qr-cambiar').hidden = camaras.length < 2;
			// Preferir la cámara trasera del celular
			const trasera = camaras.findIndex((c) => /back|rear|trasera|environment/i.test(c.label));
			if (camaraActual === 0 && trasera > 0) camaraActual = trasera;
			await iniciar(camaras[camaraActual].id);
		} catch (e) {
			cerrarLector();
			error(mensajeCamara(e), 'No se pudo abrir la cámara.');
		}
	}

	async function iniciar(idCamara) {
		lector = lector || new Html5Qrcode('qr-lector', { verbose: false });
		await lector.start(
			idCamara,
			{ fps: 10 }, // se analiza todo el cuadro de la cámara
			alLeer,
			() => {} // cada cuadro sin QR: no se hace nada
		);
		leyendo = true;
		estado.textContent = 'Apunta la cámara a la etiqueta QR del equipo.';
	}

	async function alLeer(texto) {
		if (!leyendo) return;
		leyendo = false;
		if (navigator.vibrate) navigator.vibrate(80);
		await cerrarLector();
		procesar(texto);
	}

	function procesar(texto) {
		try {
			cargarEquipo(extraerToken(texto));
		} catch (e) {
			limpiar();
			error(e.message);
		}
	}

	async function cerrarLector() {
		leyendo = false;
		try {
			if (lector?.isScanning) await lector.stop();
			lector?.clear();
		} catch (e) { /* ya estaba detenido */ }
		modal.hidden = true;
	}

	$('qr-escanear').addEventListener('click', abrirLector);
	$('qr-cancelar').addEventListener('click', cerrarLector);
	$('qr-cerrar').addEventListener('click', cerrarLector);
	$('qr-cambiar').addEventListener('click', async () => {
		camaraActual = (camaraActual + 1) % camaras.length;
		try {
			if (lector?.isScanning) await lector.stop();
			await iniciar(camaras[camaraActual].id);
		} catch (e) {
			cerrarLector();
			error(mensajeCamara(e), 'No se pudo abrir la cámara.');
		}
	});

	/* ---------- 4. Desde una foto (laptop sin cámara) ---------- */
	$('qr-archivo').addEventListener('change', async (e) => {
		const archivo = e.target.files[0];
		e.target.value = '';
		if (!archivo) return;
		error('');
		if (typeof Html5Qrcode === 'undefined') return error('No se cargó el lector de QR (html5-qrcode).');
		const lectorArchivo = new Html5Qrcode('qr-lector-archivo', { verbose: false });
		try {
			procesar(await lectorArchivo.scanFile(archivo, false));
		} catch (err) {
			limpiar();
			error('Toma la foto más cerca, de frente y con buena luz.', 'No se encontró un código QR en la imagen.');
		} finally {
			try { lectorArchivo.clear(); } catch (x) { /* nada */ }
		}
	});

	// API pequeña para nuevo_ticket.js (después de registrar se limpia el equipo)
	window.EquipoQR = {
		limpiar() {
			limpiar();
			history.replaceState(null, '', location.pathname);
		}
	};

	/* ---------- 5. Llegó desde el enlace del QR ---------- */
	const tokenUrl = params.get('equipo');
	if (tokenUrl) {
		PATRON_TOKEN.test(tokenUrl) ? cargarEquipo(tokenUrl) : error('El enlace del QR está incompleto o fue modificado.');
	} else if (location.hash === '#escanear') {
		abrirLector();
	}
});
