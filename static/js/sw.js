/* =========================================================
   MÓDULO 7 — Service Worker para Notificaciones Web Push SLA
   Se sirve desde /sw.js (ruta de sla_push.py) para controlar toda la app.
   ========================================================= */
self.addEventListener('push', (event) => {
    let data = {
        title: 'Alerta SLA · Soporte TI',
        body: 'Tienes una notificación crítica de SLA.',
        url: '/sla'
    };
    if (event.data) {
        try {
            data = { ...data, ...event.data.json() };
        } catch (e) {
            data.body = event.data.text();
        }
    }
    event.waitUntil(self.registration.showNotification(data.title, {
        body: data.body,
        icon: '/static/img/logos/grupo-mm.png',
        badge: '/static/img/logos/grupo-mm.png',
        vibrate: [200, 100, 200],
        data: { url: data.url || '/sla' }
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const destino = (event.notification.data && event.notification.data.url) || '/sla';
    event.waitUntil(clients.openWindow(destino));
});
