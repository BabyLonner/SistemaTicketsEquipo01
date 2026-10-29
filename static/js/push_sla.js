// ==========================================
// MÓDULO 7 — GESTIÓN DE PUSH Y ALERTAS SLA PERSONALIZADAS
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    inicializarBotonPush();
    // Verificación única al cargar la página (sin bucles molestos de 30 segundos)
    ejecutarVerificacionSlaSilenciosa();
});

// Sistema de Cola para Notificaciones Personalizadas
let notifQueue = [];
let isShowingNotif = false;

function mostrarAlertaPersonalizada(titulo, mensaje, ticketId) {
    // Evitar duplicados en la sesión actual
    const keyNotif = `notif_vista_${ticketId}_${titulo}`;
    if (sessionStorage.getItem(keyNotif)) return;
    sessionStorage.setItem(keyNotif, 'true');

    notifQueue.push({ titulo, mensaje, ticketId });
    procesarColaNotificaciones();
}

function procesarColaNotificaciones() {
    if (isShowingNotif || notifQueue.length === 0) return;
    isShowingNotif = true;

    const notifData = notifQueue.shift();

    let container = document.getElementById('custom-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'custom-toast-container';
        container.style.cssText = 'position: fixed; bottom: 25px; right: 25px; z-index: 99999; display: flex; flex-direction: column; gap: 12px; max-width: 380px; width: 100%;';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.style.cssText = `
        background: #ffffff;
        border-left: 6px solid #0d6efd;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
        border-radius: 10px;
        padding: 16px 20px;
        font-family: inherit;
        animation: slideInRight 0.3s ease-out;
    `;

    toast.innerHTML = `
        <div style="font-weight: 700; font-size: 15px; color: #212529; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
            ${notifData.titulo}
        </div>
        <div style="font-size: 13px; color: #495057; margin-bottom: 14px; line-height: 1.4;">
            ${notifData.mensaje}
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 10px;">
            <button id="toast-btn-ok" style="background: #6c757d; color: white; border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;">OK</button>
            <button id="toast-btn-ver" style="background: #0d6efd; color: white; border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;">Ver Ticket</button>
        </div>
    `;

    container.appendChild(toast);

    toast.querySelector('#toast-btn-ok').addEventListener('click', () => {
        toast.style.animation = 'fadeOut 0.2s ease-out';
        setTimeout(() => {
            toast.remove();
            isShowingNotif = false;
            procesarColaNotificaciones();
        }, 200);
    });

    toast.querySelector('#toast-btn-ver').addEventListener('click', () => {
        window.location.href = `/detalle_ticket?id=${notifData.ticketId}`;
    });
}

// Verificación inteligente de SLA al entrar a la vista
async function ejecutarVerificacionSlaSilenciosa() {
    try {
        const res = await fetch('/api/sla/verificar-alertas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            (data.escalados || []).forEach((t) => {
                mostrarAlertaPersonalizada(
                    `🚨 SLA Vencido: ${t.codigo}`,
                    `El ticket "${t.asunto}" superó el tiempo y fue escalado a prioridad Alta.`,
                    t.id
                );
            });
            (data.alertados || []).forEach((t) => {
                mostrarAlertaPersonalizada(
                    `⚠️ SLA Por Vencer: ${t.codigo}`,
                    `Quedan ${t.restantes} min para resolver "${t.asunto}".`,
                    t.id
                );
            });
            if (typeof cargarTicketsSla === 'function') cargarTicketsSla();
            if (typeof cargarNotificaciones === 'function') cargarNotificaciones();
        }
    } catch (e) {
        console.error('Error al verificar SLA en segundo plano.');
    }
}

async function inicializarBotonPush() {
    const btnPush = document.getElementById('btn-activar-push');
    if (!btnPush) return;

    try {
        const registration = await navigator.serviceWorker.ready;
        let subscription = await registration.pushManager.getSubscription();

        const actualizarUI = (activo) => {
            if (activo) {
                btnPush.textContent = '✅ Alertas Push Activas (Clic para desactivar)';
                btnPush.style.backgroundColor = '#198754';
                btnPush.style.color = '#fff';
            } else {
                btnPush.textContent = '🔔 Activar Alertas Push';
                btnPush.style.backgroundColor = '#0d6efd';
                btnPush.style.color = '#fff';
            }
        };

        actualizarUI(subscription !== null && Notification.permission === 'granted');

        btnPush.onclick = async () => {
            try {
                const currentSub = await registration.pushManager.getSubscription();

                if (currentSub) {
                    // DESACTIVAR
                    const endpoint = currentSub.endpoint;
                    await currentSub.unsubscribe();

                    await fetch('/api/push/desactivar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ endpoint })
                    });

                    actualizarUI(false);
                    console.log('Notificaciones Push desactivadas correctamente.');
                } else {
                    // ACTIVAR
                    const permission = await Notification.requestPermission();
                    if (permission === 'granted') {
                        const resKey = await fetch('/api/push/vapid-public-key');
                        const dataKey = await resKey.json();

                        if (!dataKey.publicKey) {
                            alert('No se pudo obtener la llave VAPID del servidor.');
                            return;
                        }

                        const newSub = await registration.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: urlBase64ToUint8Array(dataKey.publicKey)
                        });

                        const resSub = await fetch('/api/push/suscribir', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(newSub)
                        });

                        const dataSub = await resSub.json();
                        if (resSub.ok && dataSub.ok) {
                            actualizarUI(true);
                            console.log('Notificaciones Push activadas y guardadas correctamente.');
                        } else {
                            alert('Error en el servidor al registrar: ' + (dataSub.error || 'Desconocido'));
                        }
                    } else {
                        alert('El permiso de notificaciones fue denegado en el navegador.');
                    }
                }
            } catch (err) {
                // AQUÍ VEREMOS EL ERROR EXACTO EN PANTALLA Y CONSOLA
                console.error('Detalle del error push:', err);
                alert('Error técnico: ' + err.message);
            }
        };
    } catch (e) {
        console.error('Error inicializando el botón push:', e);
    }
}

// Función auxiliar indispensable para convertir la llave VAPID
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + base64String).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function registrarSuscripcionPushServidor() {
    const resKey = await fetch('/api/push/vapid-public-key');
    const { publicKey } = await resKey.json();
    
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    await fetch('/api/push/suscribir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription)
    });
}

// Función auxiliar corregida para la llave VAPID
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, '+')
        .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}