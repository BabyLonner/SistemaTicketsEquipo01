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

self.addEventListener('push', function(event) {
    let data = { title: 'Alerta de SLA', body: 'Tienes una actualización en los tickets.', url: '/sla' };
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: '/static/img/logos/grupo-mm.png', // Ajusta la ruta de tu ícono si es diferente
        badge: '/static/img/logos/grupo-mm.png',
        data: { url: data.url || '/sla' },
        vibrate: [200, 100, 200]
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});