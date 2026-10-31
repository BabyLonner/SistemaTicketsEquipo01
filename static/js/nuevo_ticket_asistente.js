/* =========================================================
   nuevo_ticket_asistente.js — MÓDULO 6: asistente con IA
   ---------------------------------------------------------
   En "Nuevo Ticket", ANTES del formulario, el usuario describe su
   problema y el asistente responde con los artículos de la base de
   conocimiento (POST /api/kb/consultar).

     · "Sí, se resolvió"            → se guarda RESUELTO (no se crea ticket).
     · "No resolvió… crear ticket"  → se guarda TICKET y aparece el formulario:
                                      lo general de lo que escribió va al Asunto y
                                      los detalles a la Descripción.
     · "Cancelar" en el formulario  → se vuelve al asistente.

   No cambia nuevo_ticket.js: solo escribe en #subject y #description
   y dispara su evento "input", igual que el dictado por voz.
   Si se entra por un QR (?equipo=) o para editar (?editar=), el
   asistente no aparece y se va directo al formulario.
   ========================================================= */
(() => {
	'use strict';

	const MODOS = {
		IA: 'Redactado con IA',
		CACHE: 'Respuesta guardada',
		LOCAL: 'Artículo encontrado',
		SIN_ARTICULOS: 'Sin artículos'
	};

	let ui = {};
	let consulta = null;        // { id, pregunta, articulos }

	document.addEventListener('DOMContentLoaded', iniciar);

	function iniciar() {
		const $ = (id) => document.getElementById(id);
		ui = {
			panel: $('kb-asistente'), form: $('kb-form'), pregunta: $('kb-pregunta'), contador: $('kb-contador'),
			error: $('kb-error'), buscar: $('kb-buscar'), saltar: $('kb-saltar'), cargando: $('kb-cargando'),
			resultado: $('kb-resultado'), modo: $('kb-modo'), texto: $('kb-texto'), aviso: $('kb-aviso'),
			fuentesCaja: $('kb-fuentes-caja'), fuentes: $('kb-fuentes'), resuelto: $('kb-resuelto'), crear: $('kb-crear'),
			gracias: $('kb-gracias'), otra: $('kb-otra'),
			ticketForm: $('new-ticket-form'), asunto: $('subject'), descripcion: $('description')
		};
		if (!ui.panel || !ui.ticketForm) return;

		const params = new URLSearchParams(location.search);
		const directo = params.has('equipo') || params.has('editar') || location.hash === '#escanear';
		if (directo) return;   // QR o edición: el formulario se usa directamente

		ui.panel.hidden = false;
		ui.ticketForm.classList.add('kb-oculto');

		ui.pregunta.addEventListener('input', () => {
			ui.contador.textContent = `${ui.pregunta.value.length}/600`;
			ui.error.textContent = '';
		});
		ui.pregunta.addEventListener('keydown', (e) => {
			if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ui.form.requestSubmit();
		});
		ui.form.addEventListener('submit', (e) => { e.preventDefault(); preguntar(); });
		ui.saltar.addEventListener('click', () => mostrarFormulario(false));
		ui.resuelto.addEventListener('click', marcarResuelto);
		ui.crear.addEventListener('click', crearTicket);
		ui.otra.addEventListener('click', reiniciar);
		// «Cancelar» del formulario: nuevo_ticket.js lo limpia y aquí se vuelve al asistente
		document.getElementById('cancel-button')?.addEventListener('click', () => {
			reiniciar();
			ui.ticketForm.classList.add('kb-oculto');
			ui.panel.hidden = false;
			ui.panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
		});
	}

	/* -------------------------------------------------------
	   Consulta al asistente
	   ------------------------------------------------------- */
	async function preguntar() {
		const pregunta = ui.pregunta.value.trim();
		if (pregunta.length < 8) {
			ui.error.textContent = 'Cuéntanos un poco más del problema (al menos 8 caracteres).';
			ui.pregunta.focus();
			return;
		}
		ui.resultado.hidden = true;
		ui.gracias.hidden = true;
		ui.cargando.hidden = false;
		ui.buscar.disabled = true;

		try {
			const res = await fetch('/api/kb/consultar', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'same-origin',
				body: JSON.stringify({ pregunta })
			});
			if (res.status === 401) return (location.href = '/');
			const datos = await res.json().catch(() => ({}));
			if (!res.ok || !datos.ok) throw new Error(datos.error || 'El asistente no está disponible.');
			consulta = { id: datos.consulta_id, pregunta, articulos: datos.articulos || [] };
			pintarRespuesta(datos);
		} catch (e) {
			ui.error.textContent = `${e.message} Puedes crear el ticket directamente.`;
		} finally {
			ui.cargando.hidden = true;
			ui.buscar.disabled = false;
		}
	}

	function pintarRespuesta(datos) {
		ui.modo.textContent = MODOS[datos.modo] || '';
		ui.modo.dataset.modo = datos.modo;
		ui.resuelto.hidden = datos.modo === 'SIN_ARTICULOS';

		if (datos.modo === 'SIN_ARTICULOS') {
			ui.texto.innerHTML = '<p>No encontré artículos en la base de conocimiento que respondan a este problema. '
				+ 'Lo mejor es que lo revise un técnico: crea el ticket y ya lo dejamos lleno con lo que escribiste.</p>';
		} else {
			ui.texto.innerHTML = formatear(datos.respuesta || '');
		}
		ui.aviso.hidden = !datos.aviso;
		ui.aviso.textContent = datos.aviso || '';

		ui.fuentes.innerHTML = '';
		ui.fuentesCaja.hidden = !datos.articulos?.length;
		(datos.articulos || []).forEach((a) => ui.fuentes.append(itemArticulo(a)));

		ui.resultado.hidden = false;
		window.lucide?.createIcons?.();
		ui.resultado.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
	}

	/* Texto seguro: se escapa el HTML y luego se marcan negritas, listas y citas [A1] */
	function formatear(texto) {
		const esc = texto.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
		return esc
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
			.replace(/\[A(\d+)\]/g, '<span class="kb-cita" title="Artículo de origen A$1">A$1</span>')
			.split(/\n{2,}/)
			.map((parrafo) => `<p>${parrafo.replace(/\n/g, '<br>')}</p>`)
			.join('');
	}

	function itemArticulo(a) {
		const li = document.createElement('li');
		li.className = 'kb-fuente';
		const det = document.createElement('details');
		const sum = document.createElement('summary');
		const tag = document.createElement('span');
		tag.className = 'kb-cita';
		tag.textContent = a.etiqueta || 'A';
		const titulo = document.createElement('strong');
		titulo.textContent = a.titulo;
		const cat = document.createElement('small');
		cat.textContent = a.categoria || 'General';
		sum.append(tag, titulo, cat);
		const resumen = document.createElement('p');
		resumen.className = 'kb-fuente__resumen';
		resumen.textContent = a.resumen;
		const cuerpo = document.createElement('div');
		cuerpo.className = 'kb-fuente__contenido';
		cuerpo.textContent = a.contenido;
		det.append(sum, resumen, cuerpo);
		li.append(det);
		return li;
	}

	/* -------------------------------------------------------
	   Resultado de la consulta
	   ------------------------------------------------------- */
	async function guardarResultado(resultado) {
		if (!consulta?.id) return;
		try {
			await fetch(`/api/kb/consultas/${consulta.id}/resultado`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'same-origin',
				body: JSON.stringify({ resultado })
			});
		} catch (e) { /* no impide seguir */ }
	}

	async function marcarResuelto() {
		ui.resuelto.disabled = true;
		await guardarResultado('RESUELTO');
		ui.resuelto.disabled = false;
		ui.resultado.hidden = true;
		ui.form.hidden = true;
		ui.gracias.hidden = false;
	}

	async function crearTicket() {
		ui.crear.disabled = true;
		await guardarResultado('TICKET');
		ui.crear.disabled = false;
		prellenarFormulario();
		mostrarFormulario(true);
	}

	/* Lo que escribió el usuario se reparte sin repetirse:
	   lo general va al Asunto y los detalles a la Descripción.
	   Si es una sola idea corta, va solo al Asunto. */
	function prellenarFormulario() {
		if (!consulta) return;
		const { asunto, descripcion } = separarTexto(consulta.pregunta);
		if (!ui.asunto.value.trim() && asunto) escribir(ui.asunto, asunto);
		if (!ui.descripcion.value.trim() && descripcion) escribir(ui.descripcion, recortar(descripcion, 1000));
	}

	function separarTexto(original) {
		const texto = original.replace(/\s+/g, ' ').trim();
		let general = texto;
		let detalle = '';

		const frases = texto.split(/(?<=[.!?])\s+/);
		if (frases.length > 1) {
			// Varias oraciones: la primera es lo general
			general = frases[0];
			detalle = frases.slice(1).join(' ');
		} else if (/,\s/.test(texto) && texto.indexOf(',') >= 10) {
			// «La impresora no imprime, los documentos se quedan en cola»
			general = texto.slice(0, texto.indexOf(','));
			detalle = texto.slice(texto.indexOf(',') + 1);
		} else if (texto.length > 60) {
			// Una oración larga: se corta en «porque», «pero», «y», «desde», «cuando»…
			const corte = /\s(porque|ya que|pero|y|desde|cuando)\s/ig;
			let m;
			while ((m = corte.exec(texto))) {
				if (m.index < 15) continue;
				general = texto.slice(0, m.index);
				const conector = m[1].toLowerCase();
				detalle = texto.slice(m.index + (['desde', 'cuando'].includes(conector) ? 1 : m[0].length));
				break;
			}
		}

		// El asunto admite 150 caracteres: lo que sobre pasa a la descripción
		if (general.length > 150) {
			const espacio = general.lastIndexOf(' ', 140);
			detalle = `${general.slice(espacio + 1)} ${detalle}`.trim();
			general = general.slice(0, espacio);
		}
		general = mayuscula(general.replace(/[\s.,;:!?]+$/, ''));
		detalle = mayuscula(detalle.trim());
		if (detalle && !/[.!?]$/.test(detalle)) detalle += '.';
		return { asunto: general, descripcion: detalle };
	}

	function escribir(campo, valor) {
		campo.value = valor;
		campo.dispatchEvent(new Event('input', { bubbles: true }));   // contador y validación de nuevo_ticket.js
	}

	const mayuscula = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
	const recortar = (t, max) => (t.length > max ? t.slice(0, max) : t);

	function mostrarFormulario(desdeAsistente) {
		ui.panel.hidden = true;
		ui.ticketForm.classList.remove('kb-oculto');
		(desdeAsistente ? ui.asunto : ui.ticketForm.querySelector('input, textarea'))?.focus();
	}

	function reiniciar() {
		consulta = null;
		ui.gracias.hidden = true;
		ui.resultado.hidden = true;
		ui.form.hidden = false;
		ui.pregunta.value = '';
		ui.contador.textContent = '0/600';
		ui.pregunta.focus();
	}
})();
