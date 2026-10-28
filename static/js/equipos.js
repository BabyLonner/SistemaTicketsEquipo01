/* =========================================================
   equipos.js — MÓDULO 3 (avance 2): inventario y etiquetas QR
     GET    /api/equipos                     lista + catálogos
     POST   /api/equipos                     registrar (Administrador)
     PUT    /api/equipos/<id>                editar (Administrador)
     DELETE /api/equipos/<id>                dar de baja (Administrador)
     POST   /api/equipos/<id>/regenerar-qr   nuevo QR (Administrador)
     GET    /api/equipos/etiquetas.pdf?ids=  PDF para imprimir
   El QR de cada tarjeta se dibuja con qrcode.js (nivel de corrección H).
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const $ = (id) => document.getElementById(id);
	const lista = $('eq-lista');
	const form = $('eq-form');
	const modal = $('eq-modal');
	const modalConfirmar = $('eq-confirmar');

	let equipos = [];
	let puedeEditar = false;
	let editandoId = null;
	const seleccion = new Set();

	const escapar = (t) =>
		String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

	function toast(msg) {
		const t = $('toast');
		t.textContent = msg;
		t.classList.add('show');
		clearTimeout(t._timer);
		t._timer = setTimeout(() => t.classList.remove('show'), 4200);
	}

	async function api(url, opciones = {}) {
		const res = await fetch(url, {
			headers: opciones.body ? { 'Content-Type': 'application/json' } : {},
			...opciones
		});
		const datos = await res.json().catch(() => ({}));
		if (res.status === 401) location.href = '/';
		if (!res.ok) {
			const error = new Error(datos.error || 'No se pudo completar la acción.');
			error.errores = datos.errores || {};
			throw error;
		}
		return datos;
	}

	/* ---------------- Carga ---------------- */
	async function cargar() {
		try {
			const d = await api('/api/equipos');
			equipos = d.equipos;
			puedeEditar = d.puede_editar;
			$('eq-nuevo').hidden = !puedeEditar;
			if (!$('eq-tipo').dataset.listo) {
				$('eq-tipo').insertAdjacentHTML('beforeend', d.tipos.map((t) => `<option>${escapar(t)}</option>`).join(''));
				form.tipo.innerHTML = '<option value="">Selecciona…</option>' + d.tipos.map((t) => `<option>${escapar(t)}</option>`).join('');
				form.area_id.innerHTML = '<option value="">Sin área</option>' +
					d.areas.map((a) => `<option value="${a.id}">${escapar(a.nombre)}</option>`).join('');
				form.codigo.placeholder = `${d.empresa.prefijo}-PC-002`;
				$('eq-tipo').dataset.listo = '1';
			}
			[...seleccion].forEach((id) => { if (!equipos.some((e) => e.id === id)) seleccion.delete(id); });
			pintar();
		} catch (e) {
			lista.innerHTML = '';
			mostrarAlerta(e.message);
		}
	}

	function mostrarAlerta(texto) {
		$('eq-alerta').textContent = texto;
		$('eq-alerta').hidden = !texto;
	}

	/* ---------------- Lista con QR ---------------- */
	function filtrados() {
		const texto = $('eq-buscar').value.trim().toLowerCase();
		const tipo = $('eq-tipo').value;
		return equipos.filter((e) =>
			(!tipo || e.tipo === tipo) &&
			(!texto || [e.codigo, e.nombre, e.ubicacion, e.serie, e.marca, e.modelo, e.area]
				.some((v) => (v || '').toLowerCase().includes(texto))));
	}

	function pintar() {
		const visibles = filtrados();
		$('eq-total').textContent = equipos.length;
		$('eq-pendientes').textContent = equipos.filter((e) => e.tickets_pendientes > 0).length;
		$('eq-incidencias').textContent = equipos.reduce((s, e) => s + e.total_tickets, 0);
		$('eq-seleccionados').textContent = seleccion.size;
		$('eq-imprimir').querySelector('span').textContent = seleccion.size
			? `Imprimir ${seleccion.size} etiqueta(s) (PDF)`
			: 'Imprimir todas las etiquetas (PDF)';
		$('eq-todos').checked = visibles.length > 0 && visibles.every((e) => seleccion.has(e.id));

		if (!visibles.length) {
			lista.innerHTML = `<p class="eq-vacio">${equipos.length ? 'Ningún equipo coincide con la búsqueda.'
				: puedeEditar ? 'Aún no hay equipos. Pulsa «Registrar equipo» para agregar el primero.'
					: 'Aún no hay equipos registrados.'}</p>`;
			return;
		}

		lista.innerHTML = visibles.map((e) => `
			<article class="eq-card ${seleccion.has(e.id) ? 'eq-card--sel' : ''}" data-id="${e.id}">
				<label class="eq-card__check" title="Seleccionar para imprimir">
					<input type="checkbox" data-sel="${e.id}" ${seleccion.has(e.id) ? 'checked' : ''}>
					<span class="sr-only">Seleccionar ${escapar(e.codigo)}</span>
				</label>
				<div class="eq-card__qr" data-qr="${escapar(e.qr_url)}" role="img" aria-label="Código QR de ${escapar(e.codigo)}"></div>
				<div class="eq-card__datos">
					<span class="eq-tipo">${escapar(e.tipo)}</span>
					<h3>${escapar(e.codigo)}</h3>
					<strong>${escapar(e.nombre)}</strong>
					<p>📍 ${escapar(e.ubicacion)}</p>
					<p class="eq-tenue">${escapar([e.marca, e.modelo].filter(Boolean).join(' · ') || 'Sin marca/modelo')}${e.serie ? ` · S/N ${escapar(e.serie)}` : ''}</p>
					<p class="eq-tenue">${escapar(e.area || 'Sin área')}</p>
					<span class="eq-incid ${e.tickets_pendientes ? 'eq-incid--pend' : ''}">
						${e.total_tickets} incidencia(s)${e.tickets_pendientes ? ` · ${e.tickets_pendientes} pendiente(s)` : ''}
					</span>
				</div>
				<div class="eq-card__acciones">
					<a class="eq-btn" href="/api/equipos/etiquetas.pdf?ids=${e.id}" target="_blank" rel="noopener">Etiqueta PDF</a>
					${puedeEditar ? `
					<button type="button" class="eq-btn" data-editar="${e.id}">Editar</button>
					<button type="button" class="eq-btn" data-regenerar="${e.id}">Regenerar QR</button>
					<button type="button" class="eq-btn eq-btn--peligro" data-baja="${e.id}">Dar de baja</button>` : ''}
				</div>
			</article>`).join('');

		// qrcode.js: nivel H = el QR se lee aunque se dañe hasta un 30 %
		lista.querySelectorAll('[data-qr]').forEach((caja) => {
			if (typeof QRCode === 'undefined') {
				caja.textContent = 'QR no disponible';
				return;
			}
			new QRCode(caja, {
				text: caja.dataset.qr,
				width: 132,
				height: 132,
				colorDark: '#0f2a47',
				colorLight: '#ffffff',
				correctLevel: QRCode.CorrectLevel.H
			});
			caja.removeAttribute('title'); // qrcode.js pone la URL como title
		});
	}

	lista.addEventListener('change', (e) => {
		const check = e.target.closest('[data-sel]');
		if (!check) return;
		const id = Number(check.dataset.sel);
		check.checked ? seleccion.add(id) : seleccion.delete(id);
		pintar();
	});

	lista.addEventListener('click', (e) => {
		const editar = e.target.closest('[data-editar]');
		const regenerar = e.target.closest('[data-regenerar]');
		const baja = e.target.closest('[data-baja]');
		if (editar) abrirFormulario(equipos.find((x) => x.id === Number(editar.dataset.editar)));
		if (regenerar) {
			const eq = equipos.find((x) => x.id === Number(regenerar.dataset.regenerar));
			confirmar('Regenerar QR',
				`Se creará un QR nuevo para ${eq.codigo}. La etiqueta que está pegada ahora DEJARÁ DE FUNCIONAR y tendrás que imprimir la nueva.\n\nÚsalo si la etiqueta se perdió o sospechas que fue cambiada.`,
				async () => {
					const d = await api(`/api/equipos/${eq.id}/regenerar-qr`, { method: 'POST' });
					toast(d.mensaje);
					await cargar();
				});
		}
		if (baja) {
			const eq = equipos.find((x) => x.id === Number(baja.dataset.baja));
			confirmar('Dar de baja',
				`${eq.codigo} · ${eq.nombre}\n\nEl equipo ya no aparecerá en la lista y su QR no permitirá registrar tickets. Su historial de incidencias se conserva.`,
				async () => {
					const d = await api(`/api/equipos/${eq.id}`, { method: 'DELETE' });
					toast(d.mensaje);
					seleccion.delete(eq.id);
					await cargar();
				});
		}
	});

	$('eq-buscar').addEventListener('input', pintar);
	$('eq-tipo').addEventListener('change', pintar);
	$('eq-todos').addEventListener('change', (e) => {
		filtrados().forEach((eq) => (e.target.checked ? seleccion.add(eq.id) : seleccion.delete(eq.id)));
		pintar();
	});

	$('eq-imprimir').addEventListener('click', () => {
		if (!equipos.length) return toast('No hay equipos para imprimir.');
		const ids = seleccion.size ? [...seleccion] : filtrados().map((e) => e.id);
		if (!ids.length) return toast('Ningún equipo coincide con el filtro.');
		window.open(`/api/equipos/etiquetas.pdf?ids=${ids.join(',')}`, '_blank', 'noopener');
	});

	/* ---------------- Formulario ---------------- */
	function abrirFormulario(equipo = null) {
		editandoId = equipo ? equipo.id : null;
		form.reset();
		form.querySelectorAll('[data-error]').forEach((el) => (el.textContent = ''));
		$('eq-modal-titulo').textContent = equipo ? `Editar ${equipo.codigo}` : 'Registrar equipo';
		if (equipo) {
			['codigo', 'nombre', 'tipo', 'marca', 'modelo', 'serie', 'ubicacion'].forEach((c) => (form[c].value = equipo[c] || ''));
			form.area_id.value = equipo.area_id || '';
		}
		modal.hidden = false;
		form.codigo.focus();
	}

	$('eq-nuevo').addEventListener('click', () => abrirFormulario());

	form.addEventListener('submit', async (e) => {
		e.preventDefault();
		form.querySelectorAll('[data-error]').forEach((el) => (el.textContent = ''));
		const datos = Object.fromEntries(new FormData(form));
		const errores = {};
		if (datos.codigo.trim().length < 2) errores.codigo = 'Escribe el código del equipo.';
		if (datos.nombre.trim().length < 3) errores.nombre = 'Escribe el nombre (mínimo 3 caracteres).';
		if (!datos.tipo) errores.tipo = 'Selecciona un tipo.';
		if (datos.ubicacion.trim().length < 3) errores.ubicacion = 'Indica dónde está el equipo.';
		if (Object.keys(errores).length) return pintarErrores(errores);

		$('eq-guardar').disabled = true;
		try {
			const d = await api(editandoId ? `/api/equipos/${editandoId}` : '/api/equipos', {
				method: editandoId ? 'PUT' : 'POST',
				body: JSON.stringify(datos)
			});
			modal.hidden = true;
			toast(d.mensaje);
			await cargar();
		} catch (err) {
			pintarErrores(err.errores);
			if (!Object.keys(err.errores).length) toast(err.message);
		} finally {
			$('eq-guardar').disabled = false;
		}
	});

	function pintarErrores(errores) {
		Object.entries(errores).forEach(([campo, msg]) => {
			const el = form.querySelector(`[data-error="${campo}"]`);
			if (el) el.textContent = msg;
		});
		form.querySelector('.eq-error:not(:empty)')?.previousElementSibling?.focus();
	}

	/* ---------------- Confirmación ---------------- */
	let accionPendiente = null;
	function confirmar(titulo, texto, accion) {
		$('eq-confirmar-titulo').textContent = titulo;
		$('eq-confirmar-texto').textContent = texto;
		accionPendiente = accion;
		modalConfirmar.hidden = false;
	}
	$('eq-confirmar-si').addEventListener('click', async () => {
		const boton = $('eq-confirmar-si');
		boton.disabled = true;
		try {
			await accionPendiente?.();
			modalConfirmar.hidden = true;
		} catch (e) {
			toast(e.message);
		} finally {
			boton.disabled = false;
		}
	});

	document.querySelectorAll('[data-cerrar]').forEach((b) =>
		b.addEventListener('click', () => { b.closest('.modal').hidden = true; }));
	document.addEventListener('keydown', (e) => {
		if (e.key === 'Escape') document.querySelectorAll('.modal').forEach((m) => (m.hidden = true));
	});

	cargar();
});
