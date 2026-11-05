/* =========================================================
   kb_dashboard.js — MÓDULO 6: dashboard del asistente con IA
   En la pantalla Tickets (Administrador y Técnico) muestra todos
   los intentos al asistente, cuántos fueron válidos y cuántos
   erróneos. Los datos vienen de GET /api/kb/estadisticas.
     · Válido  = el usuario pulsó «Sí, se resolvió mi problema»
     · Erróneo = cualquier otro caso
   ========================================================= */
(() => {
	'use strict';

	const $ = (id) => document.getElementById(id);
	let intentos = [];

	document.addEventListener('DOMContentLoaded', () => {
		if (!$('kbd')) return;
		$('kbd-filtro').addEventListener('change', pintarTabla);
		cargar();
	});

	async function cargar() {
		try {
			const res = await fetch('/api/kb/estadisticas', { credentials: 'same-origin' });
			const datos = await res.json().catch(() => ({}));
			if (!res.ok || !datos.ok) throw new Error(datos.error || `Error ${res.status}`);
			pintarResumen(datos.resumen);
			intentos = datos.intentos || [];
			pintarTabla();
		} catch (e) {
			$('kbd-intentos-lista').innerHTML = `<tr><td colspan="4">No se pudieron cargar las consultas: ${esc(e.message)}</td></tr>`;
		}
	}

	function pintarResumen(r) {
		$('kbd-intentos').textContent = r.intentos;
		$('kbd-validos').textContent = r.validos;
		$('kbd-erroneos').textContent = r.erroneos;
		$('kbd-efectividad').textContent = r.efectividad === null ? 'Aún no hay intentos' : `Efectividad: ${r.efectividad} %`;
		$('kbd-cuenta').textContent = `(${r.intentos})`;

		const total = r.intentos || 1;
		$('kbd-tramo-valido').style.width = `${(100 * r.validos) / total}%`;
		$('kbd-tramo-erroneo').style.width = `${(100 * r.erroneos) / total}%`;
		$('kbd-barra').classList.toggle('kbd__barra--vacia', !r.intentos);
	}

	function pintarTabla() {
		const filtro = $('kbd-filtro').value;
		const lista = intentos.filter((i) => !filtro || (filtro === 'VALIDO') === i.valido);
		$('kbd-intentos-lista').innerHTML = lista.length
			? lista.map((i) => `
				<tr>
					<td class="kbd__quien">${esc(i.usuario)}<small>${esc(i.fecha)}</small></td>
					<td class="kbd__pregunta">${esc(i.pregunta)}</td>
					<td>${i.articulo ? esc(i.articulo) : '<span class="kbd__nada">Sin resultado</span>'}</td>
					<td><span class="kbd__estado kbd__estado--${i.valido ? 'valido' : 'erroneo'}">${i.valido ? 'Válido' : 'Erróneo'}</span></td>
				</tr>`).join('')
			: '<tr><td colspan="4">No hay intentos para mostrar.</td></tr>';
	}

	function esc(t) {
		return String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
	}
})();
