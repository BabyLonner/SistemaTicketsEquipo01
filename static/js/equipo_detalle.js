/* =========================================================
   equipo_detalle.js — MÓDULO 3 (avance 2)
   En el detalle del ticket muestra el equipo vinculado por QR
   y sus otras incidencias.   GET /api/tickets/<id>/equipo
   ========================================================= */
document.addEventListener('DOMContentLoaded', async () => {
	const panel = document.getElementById('qr-detalle');
	const id = new URLSearchParams(location.search).get('id');
	if (!panel || !/^\d+$/.test(id || '')) return;

	const escapar = (t) =>
		String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

	try {
		const res = await fetch(`/api/tickets/${id}/equipo`);
		if (!res.ok) return;
		const { equipo: eq, historial } = await res.json();
		if (!eq) return; // ticket registrado sin QR: no se muestra nada
		document.getElementById('qr-detalle-cuerpo').innerHTML = `
			<p class="qr-detalle__codigo">${escapar(eq.codigo)}</p>
			<p class="qr-detalle__nombre">${escapar(eq.nombre)}${eq.activo ? '' : ' · <b style="color:#c62f3c">dado de baja</b>'}</p>
			<dl class="qr-ficha__datos">
				<div><dt>Ubicación</dt><dd>📍 ${escapar(eq.ubicacion)}</dd></div>
				<div><dt>Área</dt><dd>${escapar(eq.area || 'Sin área')}</dd></div>
				<div><dt>Tipo</dt><dd>${escapar(eq.tipo)}</dd></div>
				<div><dt>Serie</dt><dd>${escapar(eq.serie || '—')}</dd></div>
			</dl>
			<h4>Otras incidencias del equipo</h4>
			${historial.length ? `<ul class="qr-ficha__historial">${historial.map((h) => `
				<li>
					<a href="/detalle_ticket?id=${h.id}">${escapar(h.codigo)}</a>
					<span>${escapar(h.asunto)}</span>
					<em class="qr-estado qr-estado--${escapar(h.estado.replace(' ', '-').toLowerCase())}">${escapar(h.estado)}</em>
				</li>`).join('')}</ul>` : '<p class="qr-ficha__sin">Es la primera incidencia de este equipo.</p>'}`;
		panel.hidden = false;
	} catch (e) {
		/* si falla, el detalle del ticket sigue funcionando igual */
	}
});
