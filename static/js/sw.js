/* =========================================================
   MÓDULO 7 — Service Worker para Notificaciones Web Push SLA
   ========================================================= */
self.addEventListener('push', (event) => {
	let data = {
		title: 'Alerta SLA · Soporte TI',
		body: 'Tienes una notificación crítica de SLA.',
		url: '/sla'
	};
	if (event.data) {
		try {
			data = JSON.parse(event.data.text());
		} catch (e) {
			data.body = event.data.text();
		}
	}

	const options = {
		body: data.body,
		icon: '/static/img/logos/grupo-mm.png',
		badge: '/static/img/logos/grupo-mm.png',
		vibrate: [200, 100, 200],
		data: { url: data.url || '/sla' }
	};

	event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const destino = event.notification.data?.url || '/sla';
	event.waitUntil(clients.openWindow(destino));
});
