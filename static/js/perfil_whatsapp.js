/* =========================================================
   perfil_whatsapp.js — MÓDULO 4
   El técnico registra su número de WhatsApp y envía una prueba.
     GET  /api/mi-whatsapp         → número guardado y estado de Vonage
     PUT  /api/mi-whatsapp         → guardar / borrar número
     POST /api/mi-whatsapp/prueba  → mensaje de prueba por Vonage
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const panel = document.getElementById('wa-panel');
	if (!panel) return;

	const form = document.getElementById('wa-form');
	const input = document.getElementById('wa-telefono');
	const error = document.getElementById('wa-error');
	const estado = document.getElementById('wa-estado');
	const btnGuardar = document.getElementById('wa-guardar');
	const btnProbar = document.getElementById('wa-probar');
	let guardado = null; // número que está en la base de datos

	function toast(msg) {
		let t = document.getElementById('toast-wa');
		if (!t) {
			t = document.createElement('div');
			t.id = 'toast-wa';
			t.className = 'toast';
			t.setAttribute('role', 'status');
			t.setAttribute('aria-live', 'polite');
			document.body.appendChild(t);
		}
		t.textContent = msg;
		t.classList.add('show');
		clearTimeout(t._timer);
		t._timer = setTimeout(() => t.classList.remove('show'), 4000);
	}

	function pintarEstado(tipo, texto) {
		estado.dataset.estado = tipo;
		estado.querySelector('span').textContent = texto;
	}

	/* Muestra el número sin el 51 (el prefijo +51 ya está a la izquierda) */
	function paraElInput(numero) {
		if (!numero) return '';
		const local = numero.startsWith('51') && numero.length === 11 ? numero.slice(2) : '+' + numero;
		return local.replace(/^(\d{3})(\d{3})(\d{3})$/, '$1 $2 $3');
	}

	async function leerError(res, porDefecto) {
		try {
			const d = await res.json();
			return d.error || porDefecto;
		} catch (e) {
			return porDefecto;
		}
	}

	async function cargar() {
		try {
			const res = await fetch('/api/mi-whatsapp');
			if (!res.ok) throw new Error(await leerError(res, 'No se pudo cargar tu número.'));
			const d = await res.json();
			guardado = d.telefono;
			input.value = paraElInput(d.telefono);
			const sandbox = document.getElementById('wa-sandbox');
			if (sandbox && d.numero_sandbox) sandbox.textContent = d.numero_sandbox;
			if (!d.configurado) {
				pintarEstado('error', 'El administrador aún no configuró Vonage en el servidor.');
			} else if (d.telefono) {
				pintarEstado('ok', `Avisos activos en ${d.telefono_visible}`);
			} else {
				pintarEstado('vacio', 'Sin número: no recibirás avisos por WhatsApp');
			}
			btnProbar.disabled = !d.telefono;
		} catch (e) {
			pintarEstado('error', e.message);
		}
	}

	input.addEventListener('input', () => {
		error.textContent = '';
		input.removeAttribute('aria-invalid');
	});

	form.addEventListener('submit', async (e) => {
		e.preventDefault();
		const valor = input.value.trim();
		// Validación rápida en el navegador (el servidor vuelve a validar)
		const digitos = valor.replace(/[\s\-().+]/g, '');
		if (valor && !/^\d{9,15}$/.test(digitos)) {
			error.textContent = 'Escribe tu celular de 9 dígitos, por ejemplo 987 654 321.';
			input.setAttribute('aria-invalid', 'true');
			input.focus();
			return;
		}
		btnGuardar.disabled = true;
		try {
			const res = await fetch('/api/mi-whatsapp', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ telefono: valor })
			});
			if (!res.ok) {
				error.textContent = await leerError(res, 'No se pudo guardar el número.');
				input.setAttribute('aria-invalid', 'true');
				return;
			}
			const d = await res.json();
			toast(d.mensaje);
			await cargar();
		} catch (err) {
			toast('Error de conexión.');
		} finally {
			btnGuardar.disabled = false;
		}
	});

	btnProbar.addEventListener('click', async () => {
		const soloDigitos = (t) => (t || '').replace(/\D/g, '');
		if (soloDigitos(input.value) !== soloDigitos(paraElInput(guardado))) {
			toast('Primero guarda el número que escribiste.');
			return;
		}
		btnProbar.disabled = true;
		btnProbar.textContent = 'Enviando…';
		try {
			const res = await fetch('/api/mi-whatsapp/prueba', { method: 'POST' });
			const d = await res.json().catch(() => ({}));
			if (res.ok) {
				toast(d.mensaje || 'Mensaje de prueba enviado.');
				pintarEstado('ok', 'Prueba enviada · revisa tu WhatsApp');
			} else {
				toast(d.error || 'No se pudo enviar la prueba.');
				pintarEstado('error', d.error || 'No se pudo enviar la prueba.');
			}
		} catch (err) {
			toast('Error de conexión.');
		} finally {
			btnProbar.disabled = !guardado;
			btnProbar.textContent = 'Enviar prueba';
		}
	});

	cargar();
});
