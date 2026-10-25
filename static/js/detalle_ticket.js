/* =========================================================
   detalle_ticket.js — Lógica conectada a la API real
   ========================================================= */

document.addEventListener('DOMContentLoaded', () => {
    const idTicket = new URLSearchParams(window.location.search).get('id');
    if (!idTicket) {
        mostrarToast('No se especificó un ID de ticket válido.');
        return;
    }

    cargarDetalleTicket(idTicket);
    configurarEventosPanelDerecho(idTicket);
});

function obtenerHeadersAuth() {
    const headers = { 'Content-Type': 'application/json' };
    // Cambia esto si en tu proyecto usas cookies en lugar de localStorage
    const token = localStorage.getItem('token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
}

function escaparHTML(texto) {
    return String(texto ?? '').replace(
        /[&<>"']/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
    );
}

function formatearFecha(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return isNaN(d)
        ? '—'
        : d.toLocaleString('es-PE', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
}

function iniciales(nombre) {
    return (nombre || 'US')
        .split(/\s+/)
        .slice(0, 2)
        .map((p) => p[0])
        .join('')
        .toUpperCase();
}

function mostrarToast(msg) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

const CLASE_PRIORIDAD = { Alta: 'priority-high', Media: 'priority-medium', Baja: 'priority-low' };
const CLASE_ESTADO = {
    Abierto: 'status-open',
    'En proceso': 'status-progress',
    Resuelto: 'status-resolved',
    Cerrado: 'status-closed'
};

/* =========================================================================
   CARGAR DATOS DESDE LA API
   ========================================================================= */
async function cargarDetalleTicket(id) {
    try {
        const res = await fetch(`/api/tickets/${id}`, { method: 'GET', headers: obtenerHeadersAuth() });
        if (!res.ok) {
            document.getElementById('ticket-subject').textContent = 'Error al cargar el ticket';
            return;
        }

        const data = await res.json();
        const t = data.ticket;
        if (!t) return;

        // 1. Cabecera y Título
        document.getElementById('breadcrumb-code').textContent = escaparHTML(t.codigo);
        document.getElementById('ticket-code').textContent = escaparHTML(t.codigo);
        document.getElementById('ticket-subject').textContent = escaparHTML(t.asunto);

        // 2. Etiquetas (Tags) Superiores
        document.getElementById('ticket-priority-tag').className = `badge ${CLASE_PRIORIDAD[t.prioridad] || ''}`;
        document.getElementById('ticket-priority-tag').textContent = `▥ ${escaparHTML(t.prioridad)}`;

        document.getElementById('ticket-status-tag').className = `badge ${CLASE_ESTADO[t.estado] || ''}`;
        document.getElementById('ticket-status-tag').textContent = `▤ ${escaparHTML(t.estado)}`;

        const tagCategoria = document.querySelectorAll('.ticket-tags .category-tag')[0];
        const tagEmpresa = document.querySelectorAll('.ticket-tags .category-tag')[1];
        if (tagCategoria) tagCategoria.textContent = `◉ ${escaparHTML(t.categoria)}`;
        if (tagEmpresa) tagEmpresa.textContent = `▦ ${escaparHTML(t.empresa)}`;

        // 3. Descripción y Metadatos (Panel Izquierdo)
        document.getElementById('ticket-description').textContent = escaparHTML(t.descripcion);

        const metadataItems = document.querySelectorAll('.metadata-item strong');
        if (metadataItems.length >= 4) {
            metadataItems[0].textContent = escaparHTML(t.solicitante);
            metadataItems[1].textContent = escaparHTML(t.area);
            metadataItems[2].textContent = escaparHTML(t.empresa);
            metadataItems[3].textContent = formatearFecha(t.created_at);
        }

        // 4. Panel Lateral Derecho (Estado y Configuración)
        const selEstado = document.getElementById('property-status');
        const selPrio = document.getElementById('property-priority');
        const selCat = document.getElementById('property-category');
        const selTec = document.getElementById('property-technician');

        if (selEstado) selEstado.value = t.estado;
        if (selPrio) selPrio.value = t.prioridad;
        if (selCat && [...selCat.options].some((o) => o.value === t.categoria)) selCat.value = t.categoria;

        if (selTec) {
            const tecValue = t.tecnico || 'Sin asignar';
            if (![...selTec.options].some((o) => o.value === tecValue)) {
                selTec.add(new Option(tecValue, tecValue));
            }
            selTec.value = tecValue;
        }

        // --- NUEVO 5: PROYECTAR EVIDENCIAS (IMÁGENES) ---
        const contenedorEvidencias = document.getElementById('contenedor-evidencias');
        if (contenedorEvidencias) {
            contenedorEvidencias.innerHTML = ''; // Limpiamos los datos de prueba
            if (t.evidencias && t.evidencias.length > 0) {
                t.evidencias.forEach(foto => {
                    contenedorEvidencias.innerHTML += `
                        <div class="evidencia-item" style="display:inline-block; margin-right:10px; border: 1px solid #ccc; padding: 5px; border-radius: 5px;">
                            <a href="${foto.imagen_url}" target="_blank">
                                <img src="${foto.miniatura_url}" alt="${escaparHTML(foto.nombre)}" style="max-height: 120px; object-fit: cover;">
                            </a>
                            <p style="font-size: 11px; text-align: center; margin: 5px 0 0 0;">${escaparHTML(foto.nombre)}</p>
                        </div>
                    `;
                });
            } else {
                contenedorEvidencias.innerHTML = '<p class="text-muted">No se adjuntaron fotos en este ticket.</p>';
            }
        }

        // --- NUEVO 6: OBTENER HISTORIAL Y CONVERSACIÓN ---
        cargarHistorial(id);

        document.getElementById('page-message').textContent = `Conectado a la base de datos · Ticket cargado correctamente.`;
    } catch (e) {
        console.error('Error al obtener detalle del ticket:', e);
        mostrarToast('No se pudo conectar con el servidor.');
    }
}

/* =========================================================================
   NUEVO: CARGAR HISTORIAL (Línea de Tiempo y Chat)
   ========================================================================= */
async function cargarHistorial(ticketId) {
    try {
        const res = await fetch(`/api/tickets/${ticketId}/historial`, { headers: obtenerHeadersAuth() });
        if (res.ok) {
            const data = await res.json();
            renderizarHistorial(data.historial || []);
            renderizarChat(data.historial || []);
        }
    } catch (e) {
        console.error("Error al cargar historial y comentarios", e);
    }
}

function renderizarHistorial(historialArray) {
    const list = document.getElementById('history-timeline');
    const counter = document.getElementById('history-count');
    const tabCounter = document.getElementById('history-tab-count');

    if (!list) return;
    if (counter) counter.textContent = `${historialArray.length} movimientos`;
    if (tabCounter) tabCounter.textContent = historialArray.length;

    if (historialArray.length === 0) {
        list.innerHTML = `<li>No hay movimientos registrados.</li>`;
        return;
    }

    list.innerHTML = historialArray.map((h) => {
        let iconoStr = '●';
        let claseColor = '';
        let accion = h.tipo;

        // Traducir el TIPO de MySQL a un texto amigable
        if (h.tipo === 'CREACION') {
            iconoStr = '＋'; claseColor = 't-open'; accion = 'Ticket registrado';
        } else if (h.tipo === 'CAMBIO_ESTADO') {
            iconoStr = '⟳'; claseColor = 't-progress'; accion = `Cambió de ${h.estado_anterior} a ${h.estado_nuevo}`;
        } else if (h.tipo === 'ASIGNACION') {
            iconoStr = '♙'; claseColor = 't-assign'; accion = `Asignado a ${h.tecnico_nuevo || 'Sin asignar'}`;
        } else if (h.tipo === 'COMENTARIO') {
            iconoStr = '💬'; claseColor = 't-resolved'; accion = 'Nuevo comentario';
        }

        const fechaFormat = formatearFecha(h.created_at);
        return `
        <li class="tl-item">
            <span class="tl-icon ${claseColor}" aria-hidden="true">${iconoStr}</span>
            <div class="tl-body">
                <div class="tl-title">${escaparHTML(accion)}</div>
                <div class="tl-meta">
                    <span>${escaparHTML(h.usuario)}</span>
                    <time datetime="${h.created_at}" title="${fechaFormat}">${fechaFormat}</time>
                </div>
                ${h.comentario ? `<p class="tl-comment">\${escaparHTML(h.comentario)}</p>` : ''}
            </div>
        </li>
        `;
    }).join('');
}

function renderizarChat(historialArray) {
    const chatContainer = document.getElementById('contenedor-chat');
    if (!chatContainer) return;

    chatContainer.innerHTML = ''; // Limpiamos el chat quemado de "Rosa Villanueva"

    // Filtramos para mostrar solo la creación y los comentarios en la pestaña Conversación
    const mensajes = historialArray.filter(h => h.tipo === 'COMENTARIO' || h.tipo === 'CREACION');

    if (mensajes.length === 0) {
        chatContainer.innerHTML = '<p class="text-muted">No hay mensajes en la conversación aún.</p>';
        return;
    }

    mensajes.forEach(m => {
        chatContainer.innerHTML += `
            <div class="mensaje" style="display: flex; gap: 15px; margin-bottom: 20px; padding: 10px; border-bottom: 1px solid #eee;">
                <div class="avatar" style="width: 40px; height: 40px; border-radius: 50%; background: #2672C7; color: white; display: flex; align-items: center; justify-content: center; font-weight: bold;">
                    ${iniciales(m.usuario)}
                </div>
                <div class="contenido" style="flex: 1;">
                    <div style="margin-bottom: 5px;">
                        <strong style="color: #333;">${escaparHTML(m.usuario)}</strong>
                        <small style="color: #888; font-size: 12px; margin-left: 5px;">(${escaparHTML(m.usuario_rol)}) - ${formatearFecha(m.created_at)}</small>
                    </div>
                    <p style="margin: 0; color: #555; line-height: 1.4;">${escaparHTML(m.comentario)}</p>
                </div>
            </div>
        `;
    });
}

/* =========================================================================
   ACTUALIZAR TICKET (Panel Lateral Derecho)
   ========================================================================= */
function configurarEventosPanelDerecho(ticketId) {
    const formPanel = document.getElementById('ticket-properties');

    if (formPanel) {
        formPanel.addEventListener('submit', async (e) => {
            e.preventDefault();

            const estadoNuevo = document.getElementById('property-status')?.value;
            const prioNueva = document.getElementById('property-priority')?.value;
            const catNueva = document.getElementById('property-category')?.value;
            let tecNuevo = document.getElementById('property-technician')?.value;

            if (tecNuevo === 'Sin asignar') tecNuevo = null;

            const datos = {
                estado: estadoNuevo,
                prioridad: prioNueva,
                categoria: catNueva,
                tecnico: tecNuevo
            };

            const btnSave = formPanel.querySelector('.save-button');
            if (btnSave) {
                btnSave.disabled = true;
                btnSave.innerHTML = `<span>...</span>Guardando`;
            }

            try {
                const res = await fetch(`/api/tickets/${ticketId}`, {
                    method: 'PUT',
                    headers: obtenerHeadersAuth(),
                    body: JSON.stringify(datos)
                });

                if (res.ok) {
                    mostrarToast('Ticket actualizado correctamente.');
                    cargarDetalleTicket(ticketId);
                } else {
                    const err = await res.json();
                    mostrarToast(err.msg || 'Error al actualizar.');
                }
            } catch (error) {
                mostrarToast('Error de conexión al guardar cambios.');
            } finally {
                if (btnSave) {
                    btnSave.disabled = false;
                    btnSave.innerHTML = `<span>▣</span>Guardar cambios`;
                }
            }
        });
    }

    document.querySelectorAll('.tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach((item) => {
                item.classList.toggle('active', item === tab);
                item.setAttribute('aria-selected', String(item === tab));
            });
            document.querySelectorAll('.tab-content').forEach((content) => (content.hidden = true));
            const panel = document.getElementById(`tab-${tab.dataset.tab}`);
            if (panel) panel.hidden = false;
        });
    });

    const btnCerrar = document.getElementById('close-ticket');
    if (btnCerrar) {
        btnCerrar.addEventListener('click', () => {
            const selStatus = document.getElementById('property-status');
            if (selStatus) {
                selStatus.value = 'Cerrado';
                formPanel.dispatchEvent(new Event('submit'));
            }
        });
    }
}