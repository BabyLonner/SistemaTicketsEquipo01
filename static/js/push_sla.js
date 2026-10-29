/* =========================================================
   MÓDULO 7 — Suscripción Web Push y Verificador SLA en vivo
   ========================================================= */
function urlBase64ToUint8Array(base64String) {
	const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
	const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
	const rawData = window.atob(base64);
	return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

async function activarNotificacionesPush() {
	if (!('serviceWorker' in navigator) || !('Notification' in window)) {
		mensajeSla('Tu navegador no soporta notificaciones Web Push.');
		return;
	}

	const permiso = await Notification.requestPermission();
	if (permiso !== 'granted') {
		mensajeSla('Debes permitir las notificaciones en el navegador.');
		return;
	}

	try {
		const reg = await navigator.serviceWorker.register('/sw.js');
		const resKey = await fetch('/api/push/vapid-public-key');
		const { publicKey } = await resKey.json();

		let sub = await reg.pushManager.getSubscription();
		if (!sub) {
			sub = await reg.pushManager.subscribe({
				userVisibleOnly: true,
				applicationServerKey: urlBase64ToUint8Array(publicKey)
			});
		}

		await fetch('/api/push/suscribir', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(sub.toJSON())
		});

		// Mostrar notificación nativa inmediata de confirmación
		reg.showNotification('🔔 Alertas Push SLA Activadas', {
			body: 'Recibirás alertas críticas cuando un ticket esté por vencer o se escale.',
			icon: '/static/img/logos/grupo-mm.png'
		});

		const btn = document.getElementById('btn-activar-push');
		if (btn) {
			btn.textContent = '✓ Alertas Push Activas';
			btn.disabled = true;
		}
		mensajeSla('Notificaciones Web Push activadas correctamente.');
	} catch (err) {
		console.error('Error al registrar Push:', err);
		mensajeSla('Permiso concedido. Alertas locales del navegador activadas.');
	}
}

async function ejecutarVerificacionSla() {
	const btn = document.getElementById('btn-verificar-sla');
	if (btn) btn.disabled = true;
	try {
		const res = await fetch('/api/sla/verificar-alertas', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' }
		});
		const data = await res.json();
		if (!res.ok) {
			mensajeSla(data.error || 'No se pudo verificar el SLA.');
			return;
		}

		mensajeSla(data.mensaje);

		// Si el navegador ya dio permiso, dispara una notificación nativa por cada alerta/escalamiento nuevo
		if ('Notification' in window && Notification.permission === 'granted') {
			(data.escalados || []).forEach((t) => {
				new Notification(`🚨 SLA Vencido y Escalado: ${t.codigo}`, {
					body: `El ticket "${t.asunto}" fue escalado automáticamente a prioridad Alta.`
				});
			});
			(data.alertados || []).forEach((t) => {
				new Notification(`⚠️ SLA Por Vencer: ${t.codigo}`, {
					body: `Quedan ${t.restantes} min para resolver "${t.asunto}".`
				});
			});
		}

		if (typeof cargarTicketsSla === 'function') cargarTicketsSla();
		if (typeof cargarNotificaciones === 'function') cargarNotificaciones();
	} catch (e) {
		mensajeSla('Error al conectar con el verificador de SLA.');
	} finally {
		if (btn) btn.disabled = false;
	}
}

document.addEventListener('DOMContentLoaded', () => {
	document.getElementById('btn-activar-push')?.addEventListener('click', activarNotificacionesPush);
	document.getElementById('btn-verificar-sla')?.addEventListener('click', ejecutarVerificacionSla);
});
