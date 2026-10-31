/* =========================================================
   nuevo_ticket_voz.js — MÓDULO 2 (avance 2): ticket por voz
   ---------------------------------------------------------
   Usa la Web Speech API del navegador (SpeechRecognition) para
   que el usuario dicte su incidencia en español. El texto llena
   el asunto y la descripción y el usuario lo corrige antes de enviar.

   No reemplaza a nuevo_ticket.js: solo escribe en los campos
   #subject y #description y dispara el evento "input", así el
   contador de caracteres y la validación existentes siguen igual.

   Cómo se reparte lo dictado (una sola grabación llena los dos campos):
     · Palabras clave: lo que se dice después de «asunto» va al Asunto y
       lo que se dice después de «descripción» va a la Descripción, en el
       orden que sea. Cada campo se va llenando MIENTRAS el usuario habla.
       Ej.: «Asunto: la impresora no imprime. Descripción: desde la mañana
       los documentos se quedan en cola.»
     · Sin palabras clave: la primera frase es el asunto y el resto la
       descripción (si hubo una sola frase, va a un solo campo).
   Los micrófonos pequeños junto a cada campo dictan solo en ese campo.
   ========================================================= */
(() => {
	'use strict';

	const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
	const IDIOMA = 'es-PE';            // español de Perú
	const MAX_SEGUNDOS = 60;           // corte de seguridad por dictado
	const SILENCIO_MS = 7000;          // se detiene solo tras 7 s sin hablar
	const MAX_ASUNTO = 150;            // mismos límites que el formulario
	const MAX_DESCRIPCION = 1000;

	const MENSAJES_ERROR = {
		'not-allowed': 'No se dio permiso al micrófono. Haz clic en el candado de la barra de direcciones, permite el micrófono y vuelve a intentar.',
		'service-not-allowed': 'El navegador bloqueó el servicio de dictado. Revisa el permiso del micrófono o escribe la incidencia.',
		'audio-capture': 'No se encontró un micrófono conectado.',
		'no-speech': 'No se escuchó nada. Acércate al micrófono e inténtalo de nuevo.',
		'network': 'No hay conexión con el servicio de reconocimiento de voz (el audio se procesa por internet). Revisa tu conexión o escribe la incidencia.',
		'language-not-supported': 'El dictado en español no está disponible en este navegador.',
		'bad-grammar': 'El navegador no pudo procesar el dictado. Inténtalo de nuevo.'
	};

	const ICONO_MIC = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 17v4"/><path d="M8 21h8"/></svg>';

	let ui = {};
	let reco = null;
	let estado = null;            // datos del dictado en curso

	document.addEventListener('DOMContentLoaded', iniciarModulo);

	/* -------------------------------------------------------
	   Inicio: detectar soporte y preparar la interfaz
	   ------------------------------------------------------- */
	function iniciarModulo() {
		const $ = (id) => document.getElementById(id);
		ui = {
			panel: $('voz-panel'), boton: $('voz-boton'), textoBoton: $('voz-boton-texto'),
			ayuda: $('voz-ayuda'), grabando: $('voz-grabando'), tiempo: $('voz-tiempo'),
			vivo: $('voz-vivo'), aviso: $('voz-aviso'), privacidad: $('voz-privacidad-texto'),
			detener: $('voz-detener'), descartar: $('voz-descartar'),
			asunto: $('subject'), descripcion: $('description'), form: $('new-ticket-form')
		};
		if (!ui.panel || !ui.asunto || !ui.descripcion) return;

		if (!Reconocimiento) {
			return bloquearPanel('no-soportado',
				'Tu navegador no permite el dictado por voz (Firefox lo trae desactivado). Usa Google Chrome, Microsoft Edge o Safari, o escribe la incidencia.');
		}
		const incompatible = navegadorIncompatible();
		if (incompatible) {
			return bloquearPanel('no-soportado',
				`${incompatible} no es compatible con el dictado por voz: aunque trae la función, bloquea el servicio que convierte la voz en texto. Usa Google Chrome, Microsoft Edge o Safari, o escribe la incidencia.`);
		}
		if (!window.isSecureContext) {
			return bloquearPanel('inseguro',
				`El dictado necesita una conexión segura: abre el sistema con HTTPS o desde «localhost». Ahora estás en ${location.origin}.`);
		}

		agregarMicrofonoACampo(ui.asunto, 'asunto', 'Dictar solo el asunto');
		agregarMicrofonoACampo(ui.descripcion, 'descripcion', 'Dictar solo la descripción');

		ui.boton.addEventListener('click', () => (estado ? detener() : comenzar('auto')));
		ui.detener.addEventListener('click', detener);
		ui.descartar.addEventListener('click', descartar);
		ui.form?.addEventListener('reset', () => { if (estado) descartar(); ocultarAviso(); });
		document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && estado) descartar(); });

		revisarPermisoMicrofono();
		ui.panel.dataset.estado = 'listo';
	}

	/* Navegadores que tienen SpeechRecognition pero no lo dejan funcionar:
	   el reconocimiento usa el servicio de voz de Google y ellos no tienen acceso a él,
	   así que al grabar solo responden con el error "network".
	   · Brave se identifica con navigator.brave (forma oficial de detectarlo).
	   · Opera agrega "OPR/" a su userAgent. */
	function navegadorIncompatible() {
		if (navigator.brave) return 'Brave';
		if (/\bOPR\/|\bOPX\//.test(navigator.userAgent) || window.opr) return 'Opera';
		return null;
	}

	function bloquearPanel(motivo, mensaje) {
		ui.panel.dataset.estado = motivo;
		ui.boton.disabled = true;
		ui.textoBoton.textContent = 'Dictado no disponible';
		mostrarAviso(mensaje, 'info');
	}

	/* Si el permiso del micrófono ya fue denegado, se avisa antes de que el usuario pulse */
	async function revisarPermisoMicrofono() {
		try {
			const permiso = await navigator.permissions?.query({ name: 'microphone' });
			if (!permiso) return;
			const pintar = () => {
				if (permiso.state === 'denied') mostrarAviso(MENSAJES_ERROR['not-allowed']);
				else if (ui.aviso.dataset.codigo === 'not-allowed') ocultarAviso();
			};
			pintar();
			permiso.onchange = pintar;
		} catch (e) { /* el navegador no permite consultar el permiso */ }
	}

	function agregarMicrofonoACampo(campo, destino, etiqueta) {
		const contenedor = campo.closest('.form-field');
		const label = contenedor?.querySelector('label');
		if (!label) return;
		const boton = document.createElement('button');
		boton.type = 'button';
		boton.className = 'voz-campo';
		boton.dataset.destino = destino;
		boton.title = etiqueta;
		boton.setAttribute('aria-label', etiqueta);
		boton.innerHTML = ICONO_MIC;
		boton.addEventListener('click', () => (estado ? detener() : comenzar(destino)));
		// La etiqueta y su micrófono van juntos en una línea
		const fila = document.createElement('span');
		fila.className = 'voz-etiqueta';
		label.before(fila);
		fila.append(label, boton);
	}

	/* -------------------------------------------------------
	   Grabación
	   ------------------------------------------------------- */
	function comenzar(destino) {
		ocultarAviso();
		try {
			reco = new Reconocimiento();
		} catch (e) {
			return mostrarAviso('No se pudo iniciar el dictado en este navegador.');
		}
		reco.lang = IDIOMA;
		reco.continuous = true;       // sigue escuchando entre pausas
		reco.interimResults = true;   // muestra el texto mientras se habla
		reco.maxAlternatives = 1;

		estado = {
			destino, finales: [], interino: '', inicio: Date.now(), error: null, descartado: false, reloj: null, silencio: null,
			conClaves: false,
			// Para poder deshacer con «Descartar» lo que se llenó en vivo
			originales: { asunto: ui.asunto.value, descripcion: ui.descripcion.value }
		};

		reco.onstart = () => pintarGrabando(true);
		reco.onresult = alRecibirResultado;
		reco.onerror = (e) => {
			if (!estado) return;
			estado.error = e.error;
			if (e.error !== 'aborted') mostrarAviso(MENSAJES_ERROR[e.error] || `Error de dictado (${e.error}).`, 'error', e.error);
		};
		reco.onend = alTerminar;

		try {
			reco.start();
		} catch (e) {
			estado = null;
			return mostrarAviso('El micrófono está ocupado. Espera un momento e inténtalo de nuevo.');
		}
		estado.reloj = setInterval(actualizarReloj, 250);
		reiniciarSilencio();
	}

	function alRecibirResultado(evento) {
		if (!estado) return;
		// Se recorre la lista completa cada vez: así una frase nunca se repite
		const finales = [];
		let interino = '';
		for (let i = 0; i < evento.results.length; i++) {
			const texto = evento.results[i][0].transcript.trim();
			if (!texto) continue;
			if (evento.results[i].isFinal) finales.push(texto);
			else interino += (interino ? ' ' : '') + texto;
		}
		estado.finales = finales;
		estado.interino = interino;
		if (estado.destino === 'auto') llenarEnVivo();
		pintarTextoEnVivo();
		reiniciarSilencio();
	}

	/* Con palabras clave, cada parte va a su campo mientras el usuario habla */
	function llenarEnVivo() {
		const texto = textoDictado([...estado.finales, estado.interino]);
		const claves = dividirPorPalabrasClave(texto);
		estado.conClaves = Boolean(claves);
		if (!claves) return;
		if (claves.asunto !== null) escribir(ui.asunto, claves.asunto, MAX_ASUNTO, true);
		if (claves.descripcion !== null) escribir(ui.descripcion, claves.descripcion, MAX_DESCRIPCION, true);
	}

	function detener() {
		if (!estado) return;
		try { reco.stop(); } catch (e) { alTerminar(); }
	}

	function descartar() {
		if (!estado) return;
		estado.descartado = true;
		try { reco.abort(); } catch (e) { alTerminar(); }
	}

	function alTerminar() {
		if (!estado) return;
		clearInterval(estado.reloj);
		clearTimeout(estado.silencio);
		const { finales, interino, destino, descartado, error, originales } = estado;
		estado = null;
		reco = null;
		pintarGrabando(false);

		// Si el navegador cortó antes de cerrar la última frase, se usa igual
		const segmentos = interino ? [...finales, interino] : finales;
		if (descartado) {
			escribir(ui.asunto, originales.asunto, MAX_ASUNTO, true);
			escribir(ui.descripcion, originales.descripcion, MAX_DESCRIPCION, true);
			return avisarToast('Dictado descartado.');
		}
		if (!segmentos.length) {
			if (!error) mostrarAviso(MENSAJES_ERROR['no-speech']);
			return;
		}
		aplicarTexto(segmentos, destino);
	}

	function reiniciarSilencio() {
		if (!estado) return;
		clearTimeout(estado.silencio);
		estado.silencio = setTimeout(detener, SILENCIO_MS);
	}

	function actualizarReloj() {
		if (!estado) return;
		const seg = Math.floor((Date.now() - estado.inicio) / 1000);
		ui.tiempo.textContent = `${Math.floor(seg / 60)}:${String(seg % 60).padStart(2, '0')}`;
		if (seg >= MAX_SEGUNDOS) detener();
	}

	/* -------------------------------------------------------
	   Texto dictado → asunto y descripción
	   ------------------------------------------------------- */
	function aplicarTexto(segmentos, destino) {
		const partes = segmentos.map(puntuacionHablada).filter(Boolean);
		const completo = textoDictado(segmentos);
		const llenados = [];

		if (destino === 'asunto') {
			escribir(ui.asunto, unir(ui.asunto.value, formatearAsunto(completo)), MAX_ASUNTO);
			llenados.push(ui.asunto);
		} else if (destino === 'descripcion') {
			escribir(ui.descripcion, unir(ui.descripcion.value, formatearDescripcion(completo)), MAX_DESCRIPCION);
			llenados.push(ui.descripcion);
		} else if (dividirPorPalabrasClave(completo)) {
			// Una sola grabación con «asunto» y «descripción»: cada parte a su campo
			const claves = dividirPorPalabrasClave(completo);
			if (claves.asunto) {
				escribir(ui.asunto, formatearAsunto(claves.asunto), MAX_ASUNTO);
				llenados.push(ui.asunto);
			}
			if (claves.descripcion) {
				escribir(ui.descripcion, formatearDescripcion(claves.descripcion), MAX_DESCRIPCION);
				llenados.push(ui.descripcion);
			}
		} else {
			const { asunto, descripcion } = separarAsuntoYDescripcion(partes, completo);
			if (!ui.asunto.value.trim() && asunto) {
				escribir(ui.asunto, formatearAsunto(asunto), MAX_ASUNTO);
				llenados.push(ui.asunto);
			}
			if (descripcion) {
				escribir(ui.descripcion, unir(ui.descripcion.value, formatearDescripcion(descripcion)), MAX_DESCRIPCION);
				llenados.push(ui.descripcion);
			}
		}

		llenados.forEach(resaltar);
		llenados[0]?.focus();
		avisarToast('Texto dictado listo. Revísalo y corrígelo antes de enviar.');
	}

	/* Texto completo de lo dictado, con la puntuación hablada ya convertida */
	function textoDictado(segmentos) {
		return segmentos.filter(Boolean).map(puntuacionHablada).filter(Boolean)
			.join(' ').replace(/\s+([.,;:])/g, '$1').trim();
	}

	/* Busca las palabras clave «asunto» y «descripción» en cualquier parte y en
	   cualquier orden. Devuelve { asunto, descripcion } con el texto que va
	   después de cada una (null si esa palabra no se dijo), o null si no se dijo ninguna.
	   Si solo se dijo una palabra clave, lo dicho antes va al otro campo; si se dijeron
	   las dos, lo dicho antes («bueno…», «a ver…») se descarta. */
	function dividirPorPalabrasClave(texto) {
		const buscar = (regex) => {
			const m = regex.exec(texto);
			return m ? { inicio: m.index, fin: m.index + m[0].length } : null;
		};
		const pa = buscar(/(^|[^\p{L}])asunto(?![\p{L}])/iu);
		const pd = buscar(/(^|[^\p{L}])descripci[oó]n(?![\p{L}])/iu);
		if (!pa && !pd) return null;

		const limpiar = (t) => t.replace(/^[\s:;,.\-–—]+/, '').replace(/[\s:;,\-–—]+$/, '').trim();
		const tramo = (desde, otra) => limpiar(texto.slice(desde.fin, otra && otra.inicio > desde.inicio ? otra.inicio : undefined));
		const antes = limpiar(texto.slice(0, Math.min(pa?.inicio ?? Infinity, pd?.inicio ?? Infinity)));

		const resultado = {
			asunto: pa ? tramo(pa, pd) : (antes || null),
			descripcion: pd ? tramo(pd, pa) : null
		};
		if (pa && !pd && antes) resultado.descripcion = antes;
		return resultado;
	}

	function separarAsuntoYDescripcion(partes, completo) {
		// 1) Hubo pausas: la primera frase es el asunto
		if (partes.length > 1) return { asunto: partes[0], descripcion: partes.slice(1).join(' ') };

		// 2) Una sola frase: va a un solo campo, sin repetirse.
		//    Si el asunto está vacío va al asunto; si ya tiene texto, a la descripción.
		if (ui.asunto.value.trim()) return { asunto: '', descripcion: completo };
		return { asunto: completo, descripcion: '' };
	}

	/* Puntuación dicha en voz alta ("punto y aparte", "nueva línea") */
	function puntuacionHablada(texto) {
		return texto
			.replace(/\s*\bpunto y aparte\b\s*/gi, '.\n')
			.replace(/\s*\b(nueva l[ií]nea|nuevo p[aá]rrafo)\b\s*/gi, '\n')
			.replace(/\s*\bpunto seguido\b\s*/gi, '. ')
			.replace(/\s*\bpunto final\b\s*/gi, '.')
			.trim();
	}

	function formatearAsunto(texto) {
		return mayuscula(texto.replace(/[\s.,;:]+$/, '').replace(/\s*\n+\s*/g, ' ').trim());
	}

	function formatearDescripcion(texto) {
		const limpio = texto.trim();
		if (!limpio) return '';
		const conMayusculas = limpio.replace(/(^|[.!?]\s+|\n)([a-záéíóúñ])/g, (m, a, b) => a + b.toUpperCase());
		return /[.!?]$/.test(conMayusculas) ? conMayusculas : `${conMayusculas}.`;
	}

	const mayuscula = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
	/* Agrega lo dictado al texto que ya había; si la frase anterior no terminó,
	   la continuación va en minúscula */
	function unir(actual, nuevo) {
		const previo = actual.trim();
		if (!previo || !nuevo) return previo || nuevo;
		const sigue = /[.!?]$/.test(previo) ? nuevo : nuevo.charAt(0).toLowerCase() + nuevo.slice(1);
		return `${previo} ${sigue}`;
	}

	/* Escribe en el campo y avisa a nuevo_ticket.js con el evento "input" */
	function escribir(campo, valor, maximo, silencioso = false) {
		let texto = valor;
		if (texto.length > maximo) {
			texto = texto.slice(0, maximo);
			if (!silencioso) avisarToast(`El texto se recortó a ${maximo} caracteres.`);
		}
		if (campo.value === texto) return;
		campo.value = texto;
		campo.dispatchEvent(new Event('input', { bubbles: true }));
	}

	function resaltar(campo) {
		campo.classList.remove('voz-dictado');
		void campo.offsetWidth;
		campo.classList.add('voz-dictado');
		setTimeout(() => campo.classList.remove('voz-dictado'), 2400);
	}

	/* -------------------------------------------------------
	   Interfaz
	   ------------------------------------------------------- */
	function pintarGrabando(activo) {
		ui.panel.dataset.estado = activo ? 'grabando' : 'listo';
		ui.grabando.hidden = !activo;
		ui.boton.setAttribute('aria-pressed', String(activo));
		ui.textoBoton.textContent = activo ? 'Terminar dictado' : 'Dictar incidencia';
		document.querySelectorAll('.voz-campo').forEach((b) => {
			b.classList.toggle('voz-campo--activo', activo && estado?.destino === b.dataset.destino);
		});
		if (activo) {
			ui.tiempo.textContent = '0:00';
			ui.vivo.hidden = false;
			ui.vivo.innerHTML = '<span class="voz__vivo-guia">Habla ahora…</span>';
		} else {
			ui.vivo.hidden = true;
		}
	}

	function pintarTextoEnVivo() {
		const esc = (t) => t.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
		const finales = estado.finales.map(esc).join(' ');
		const interino = esc(estado.interino);
		const guia = estado.conClaves
			? '<span class="voz__vivo-guia">Llenando cada campo según la palabra clave («asunto» / «descripción»)…</span><br>'
			: '';
		ui.vivo.innerHTML = `${guia}${finales}${finales && interino ? ' ' : ''}<span class="voz__vivo-interino">${interino}</span>`;
	}

	function mostrarAviso(mensaje, tipo = 'error', codigo = '') {
		ui.aviso.textContent = mensaje;
		ui.aviso.dataset.tipo = tipo;
		ui.aviso.dataset.codigo = codigo || (mensaje === MENSAJES_ERROR['not-allowed'] ? 'not-allowed' : '');
		ui.aviso.hidden = false;
	}

	function ocultarAviso() {
		if (!ui.aviso) return;
		ui.aviso.hidden = true;
		ui.aviso.dataset.codigo = '';
	}

	function avisarToast(mensaje) {
		const toast = document.getElementById('toast');
		if (!toast) return;
		toast.textContent = mensaje;
		toast.classList.add('show');
		clearTimeout(avisarToast.t);
		avisarToast.t = setTimeout(() => toast.classList.remove('show'), 3200);
	}
})();
