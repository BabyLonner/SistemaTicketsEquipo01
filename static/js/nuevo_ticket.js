/* =========================================================
   nuevo_ticket.js — Tickets: registrar / editar ticket con fotos
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const $ = (id) => document.getElementById(id);
	const form = $('new-ticket-form');
	const campos = {
		asunto: $('subject'),
		descripcion: $('description'),
		categoria_id: $('category'),
		area_id: $('area')
	};

	const ERRORES = {
		asunto: 'subject-error',
		descripcion: 'description-error',
		categoria_id: 'category-error',
		area_id: 'area-error',
		prioridad: 'priority-error',
		fotos: 'attachments-error'
	};
	const MAX = TicketsAPI.MAX_FOTOS;

	const idEditar = /^\d+$/.test(new URLSearchParams(location.search).get('editar') || '')
		? new URLSearchParams(location.search).get('editar')
		: null;

	let ticketEditando = null;
	let fotosNuevas = [];
	let enviando = false;
	let areaUsuario = '';

	const avisar = (msg) => (Evidencias?.avisar ? Evidencias.avisar(msg) : alert(msg));
	const escapar = (t) =>
		String(t ?? '').replace(
			/[&<>"']/g,
			(c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
		);

	function mostrarAlerta(html) {
		const alerta = $('alerta-servidor');
		if (!alerta) return;
		alerta.innerHTML = html;
		alerta.hidden = !html;
	}

	/* =======================================================
       SESIÓN Y CATÁLOGOS
       ======================================================= */
	async function cargarSesion() {
		try {
			const respuesta = await TicketsAPI.sesion();

			// Extracción segura: si 'catalogos' no viene, asignamos arreglos vacíos para no romper el script
			const usuario = respuesta.usuario || {};
			const catalogos = respuesta.catalogos || { categorias: [], areas: [] };

			llenarSelect(campos.categoria_id, catalogos.categorias, 'Selecciona una categoría');
			llenarSelect(campos.area_id, catalogos.areas, 'Selecciona tu área');

			areaUsuario = usuario.area_id || '';
			setTimeout(() => {
				if (areaUsuario && campos.area_id) campos.area_id.value = areaUsuario;
			}, 100);

			if ($('solicitante-nombre')) {
				$('solicitante-nombre').textContent =
					`${usuario.nombre || 'Usuario'} · ${usuario.correo || 'Sin correo'}`;
			}
			return true;
		} catch (e) {
			console.error('Fallo al cargar sesión:', e);
			if ($('solicitante-nombre')) $('solicitante-nombre').textContent = 'Error de conexión';
			if ($('submit-button')) $('submit-button').disabled = true;

			if (e.estado === 401) {
				location.href = '/';
				return false;
			} else {
				mostrarAlerta(`Error al cargar datos del servidor: ${escapar(e.message)}`);
			}
			return false;
		}
	}

	function llenarSelect(select, opciones, textoVacio) {
		if (!select || !opciones) return;
		select.innerHTML =
			`<option value="">${textoVacio}</option>` +
			opciones.map((o) => `<option value="${o.id}">${escapar(o.nombre)}</option>`).join('');
	}

	/* =======================================================
       EVIDENCIAS (FOTOS)
       ======================================================= */
	const fotosExistentes = () => (ticketEditando ? ticketEditando.evidencias : []);
	const espaciosLibres = () => MAX - fotosExistentes().length - fotosNuevas.length;

	async function agregarFotos(lista) {
		const errores = [];
		let agregadas = 0;

		for (const archivo of lista) {
			if (espaciosLibres() <= 0) {
				errores.push(`Solo se permiten ${MAX} fotos.`);
				break;
			}

			const repetida = fotosNuevas.some(
				(f) => f.nombreOriginal === archivo.name && f.pesoOriginal === archivo.size
			);
			if (repetida) continue;

			try {
				// Si la API de optimización no está lista, hacemos un fallback simple
				let preparada = null;
				if (TicketsAPI.prepararFoto) {
					preparada = await TicketsAPI.prepararFoto(archivo);
				} else {
					preparada = { archivo: archivo, pesoOriginal: archivo.size, optimizada: false };
				}

				fotosNuevas.push({
					...preparada,
					nombreOriginal: archivo.name,
					url: URL.createObjectURL(preparada.archivo)
				});
				agregadas++;
			} catch (e) {
				errores.push(e.message);
			}
		}
		renderFotos();
		if ($('attachments-error')) $('attachments-error').textContent = errores.join(' ');
		if (agregadas && !errores.length) avisar(`${agregadas} foto(s) lista(s).`);
	}

	function quitarFotoNueva(indice) {
		URL.revokeObjectURL(fotosNuevas[indice].url);
		fotosNuevas.splice(indice, 1);
		renderFotos();
	}

	async function quitarFotoExistente(evidenciaId) {
		if (!confirm('¿Quitar esta foto del ticket?')) return;
		try {
			const r = await TicketsAPI.eliminarEvidencia(ticketEditando.id, evidenciaId);
			ticketEditando = r.ticket;
			renderFotos();
			avisar(r.mensaje);
		} catch (e) {
			avisar(e.message);
		}
	}

	function renderFotos() {
		const cont = $('file-list');
		if (!cont) return;

		const existentes = fotosExistentes();
		const html = [];

		existentes.forEach((f) =>
			html.push(`
            <figure class="m2-foto m2-foto--guardada">
                <button type="button" class="m2-foto__img" data-miniatura-url="${escapar(f.miniatura_url)}" data-imagen-url="${escapar(f.imagen_url)}"></button>
                <figcaption><strong>${escapar(f.nombre)}</strong><small>Guardada</small></figcaption>
                ${ticketEditando?.permisos?.editar ? `<button type="button" class="m2-foto__quitar" data-quitar-guardada="${f.id}">×</button>` : ''}
            </figure>`)
		);

		fotosNuevas.forEach((f, i) =>
			html.push(`
            <figure class="m2-foto">
                <button type="button" class="m2-foto__img"><img src="${f.url}" alt=""></button>
                <figcaption><strong>${escapar(f.archivo.name)}</strong><small>Por subir</small></figcaption>
                <button type="button" class="m2-foto__quitar" data-quitar-nueva="${i}">×</button>
            </figure>`)
		);

		for (let n = existentes.length + fotosNuevas.length; n < MAX; n++) {
			html.push(
				`<label class="m2-foto m2-foto--vacia" for="attachments"><span>＋</span><small>Foto ${n + 1}</small></label>`
			);
		}
		cont.innerHTML = html.join('');

		const total = existentes.length + fotosNuevas.length;
		if ($('attachment-count')) $('attachment-count').textContent = `${total} de ${MAX} fotos`;
		if ($('dropzone')) $('dropzone').classList.toggle('m2-dropzone--llena', total >= MAX);
		if ($('attachments')) $('attachments').disabled = total >= MAX;
	}

	if ($('file-list')) {
		$('file-list').addEventListener('click', (e) => {
			const nueva = e.target.closest('[data-quitar-nueva]');
			const guardada = e.target.closest('[data-quitar-guardada]');
			if (nueva) quitarFotoNueva(Number(nueva.dataset.quitarNueva));
			if (guardada) quitarFotoExistente(guardada.dataset.quitarGuardada);
		});
	}

	const input = $('attachments');
	const dropzone = $('dropzone');
	if (input && dropzone) {
		input.addEventListener('change', () => {
			agregarFotos([...input.files]);
			input.value = '';
		});

		dropzone.addEventListener('keydown', (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				input.click();
			}
		});

		['dragover', 'dragenter'].forEach((ev) =>
			dropzone.addEventListener(ev, (e) => {
				e.preventDefault();
				dropzone.classList.add('drag-over');
			})
		);

		['dragleave', 'drop'].forEach((ev) =>
			dropzone.addEventListener(ev, () => dropzone.classList.remove('drag-over'))
		);

		dropzone.addEventListener('drop', (e) => {
			e.preventDefault();
			if (e.dataTransfer?.files?.length) agregarFotos([...e.dataTransfer.files]);
		});
	}

	/* =======================================================
       VALIDACIÓN DEL FORMULARIO
       ======================================================= */
	function leerValores() {
		return {
			asunto: campos.asunto.value.trim(),
			descripcion: campos.descripcion.value.trim(),
			categoria_id: campos.categoria_id.value,
			area_id: campos.area_id.value,
			prioridad: form.querySelector('input[name="prioridad"]:checked')?.value || ''
		};
	}

	function validar(v) {
		const errores = {};
		if (v.asunto.length < 5) errores.asunto = 'El asunto debe tener al menos 5 caracteres.';
		if (v.descripcion.length < 10)
			errores.descripcion = 'Describe el problema (mínimo 10 caracteres).';
		if (!v.categoria_id) errores.categoria_id = 'Selecciona una categoría.';
		if (!v.area_id) errores.area_id = 'Selecciona tu área.';
		if (!v.prioridad) errores.prioridad = 'Selecciona una prioridad.';
		return errores;
	}

	function pintarErrores(errores) {
		Object.values(ERRORES).forEach((id) => {
			if ($(id)) $(id).textContent = '';
		});
		form.querySelectorAll('.m2-invalido').forEach((el) => el.classList.remove('m2-invalido'));

		Object.entries(errores).forEach(([campo, mensaje]) => {
			if (ERRORES[campo] && $(ERRORES[campo])) $(ERRORES[campo]).textContent = mensaje;
			if (campos[campo]) campos[campo].classList.add('m2-invalido');
		});

		form
			.querySelector('.field-error:not(:empty)')
			?.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}

	Object.entries(campos).forEach(([nombre, el]) => {
		if (el) {
			el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => {
				if ($(ERRORES[nombre])) $(ERRORES[nombre]).textContent = '';
				el.classList.remove('m2-invalido');
			});
		}
	});

	if (campos.descripcion) {
		campos.descripcion.addEventListener('input', () => {
			if ($('description-count'))
				$('description-count').textContent = `${campos.descripcion.value.length}/1000`;
		});
	}

	document.querySelectorAll('input[name="prioridad"]').forEach((radio) => {
		radio.addEventListener('change', () => {
			document.querySelectorAll('.priority-option').forEach((op) => {
				op.classList.toggle('selected', op.querySelector('input').checked);
			});
			if ($('priority-error')) $('priority-error').textContent = '';
		});
	});

	/* =======================================================
       ENVÍO AL BACKEND
       ======================================================= */
	function bloquear(estado, texto) {
		enviando = estado;
		if ($('submit-button')) $('submit-button').disabled = estado;
		if ($('submit-text')) $('submit-text').textContent = texto;
	}

	if (form) {
		form.addEventListener('submit', async (e) => {
			e.preventDefault();
			if (enviando) return;

			const valores = leerValores();
			const errores = validar(valores);

			if (Object.keys(errores).length > 0) return pintarErrores(errores);

			if (ticketEditando) {
				guardarEdicion(valores);
				return;
			}

			const datos = new FormData();
			Object.entries(valores).forEach(([k, v]) => datos.append(k, v));
			fotosNuevas.forEach((f) => datos.append('fotos', f.archivo));
			// MÓDULO 3 (avance 2): equipo escaneado con QR (lo llena nuevo_ticket_qr.js)
			if ($('equipo-token')?.value) datos.append('equipo', $('equipo-token').value);

			bloquear(true, 'Enviando…');

			try {
				const r = await TicketsAPI.crear(datos);
				mostrarConfirmacion(
					r.ticket || {
						codigo: 'Recién creado',
						asunto: valores.asunto,
						categoria: 'Pendiente',
						area: 'Pendiente',
						prioridad: valores.prioridad,
						solicitante: $('solicitante-nombre').textContent,
						estado: 'Abierto',
						evidencias: fotosNuevas,
						id: r.ticket_id || 1
					}
				);
				form.reset();
				window.EquipoQR?.limpiar(); // MÓDULO 3 (avance 2)
				fotosNuevas.forEach((f) => URL.revokeObjectURL(f.url));
				fotosNuevas = [];
				renderFotos();
			} catch (err) {
				mostrarAlerta(`Error al guardar: ${err.message || 'Desconocido'}`);
			} finally {
				bloquear(false, 'Enviar Ticket');
			}
		});
	}

	function mostrarConfirmacion(t) {
		if (!$('confirm-modal')) return;

		$('confirm-title').textContent = `Ticket ${t.codigo} registrado`;
		$('confirm-summary').textContent =
			`${t.asunto}\nPrioridad ${t.prioridad}\n` +
			`Solicitante: ${t.solicitante} · Estado: ${t.estado}\n` +
			(t.evidencias?.length
				? `${t.evidencias.length} foto(s) adjuntas.`
				: 'Sin fotos de evidencia.');

		$('view-detail').href = `/detalle_ticket?id=${t.id}`;
		$('confirm-modal').hidden = false;
	}

	if ($('new-another')) {
		$('new-another').addEventListener('click', () => {
			$('confirm-modal').hidden = true;
			if (campos.asunto) campos.asunto.focus();
		});
	}

	/* =======================================================
       INICIALIZACIÓN
       ======================================================= */
	renderFotos();
	cargarSesion();
});
