/* =========================================================
   sla.js — Módulo SLA Sincronizado y Dinámico con la BD
   ========================================================= */

let ticketsGlobales = [];
let ticketsFiltradosSla = [];
let paginaActualSla = 1;
const pageSizeSla = 10;
let currentSlaFilter = "all";

// Variables para el panel de configuración
let categoriaSeleccionada = null; 
let prioridadesDisponibles = [];

const CLASE_PRIORIDAD = { Alta: 'priority-high', Media: 'priority-medium', Baja: 'priority-low' };
const CLASE_ESTADO = {
    Abierto: 'status-open',
    'En proceso': 'status-progress',
    Resuelto: 'status-resolved',
    Cerrado: 'status-closed'
};

document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("tickets-tbody")) {
        configurarEventosSla();
        cargarTicketsSla();
    }
});

function escaparHTML(texto) {
    return String(texto ?? '').replace(
        /[&<>"']/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
    );
}

function obtenerCodigoTicket(t) {
    if (t.codigo) return t.codigo;
    return 'CPV-' + String(t.id).padStart(4, '0');
}

function calcularPlazoVisualSla(t) {
    const horas = m => Math.max(0, Math.ceil((m || 0) / 60));
    switch (t.semaforo) {
        case 'cumplido':
            return { texto: 'Cumplido', clase: 'ok', nivel: 'finalizado', detalle: 'Resuelto dentro del plazo' };
        case 'incumplido':
            return { texto: 'Fuera de plazo', clase: 'danger', nivel: 'finalizado', detalle: 'Resuelto después del plazo' };
        case 'rojo':
            return { texto: 'Vencido', clase: 'danger', nivel: 'vencidos', detalle: 'Plazo excedido' };
        case 'amarillo':
            return { texto: `Por vencer (${horas(t.minutos_restantes)}h)`, clase: 'warning', nivel: 'por-vencer',
                     detalle: `${horas(t.minutos_restantes)}h restantes` };
        default:
            return { texto: `A tiempo (${horas(t.minutos_restantes)}h)`, clase: 'ok', nivel: 'en-tiempo',
                     detalle: `${horas(t.minutos_restantes)}h restantes` };
    }
}

async function cargarTicketsSla() {
    try {
        const res = await fetch('/api/tickets?mios=0&limite=200', {
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!res.ok) return;
        const data = await res.json();
        ticketsGlobales = data.tickets || [];
        
        poblarFiltrosDinamicosSla(ticketsGlobales);
        aplicarFiltrosSla();
    } catch (e) {
        console.error("Error al cargar SLA:", e);
    }
}

function poblarFiltrosDinamicosSla(tickets) {
    const llenar = (id, valores, textoTodos) => {
        const select = document.getElementById(id);
        if (!select) return;
        const actual = select.value;
        select.innerHTML = `<option value="">${textoTodos}</option>` +
            valores.map(v => `<option value="${escaparHTML(v)}">${escaparHTML(v)}</option>`).join('');
        if (valores.includes(actual)) select.value = actual;
    };
    const unicos = arr => [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
    llenar('technician-filter', unicos(tickets.map(t => t.tecnico || 'Sin asignar')), 'Todos los técnicos');
    llenar('category-filter', unicos(tickets.map(t => t.categoria)), 'Todas');
    llenar('status-filter', ['Abierto', 'En proceso', 'Resuelto', 'Cerrado'], 'Todos');
}

function aplicarFiltrosSla() {
    const globalSearch = document.getElementById('global-search');
    const query = (globalSearch?.value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const priority = document.getElementById('priority-filter')?.value || '';
    const category = document.getElementById('category-filter')?.value || '';
    const technician = document.getElementById('technician-filter')?.value || '';
    const status = document.getElementById('status-filter')?.value || '';

    ticketsFiltradosSla = ticketsGlobales.filter(row => {
        const codigoReal = obtenerCodigoTicket(row).toLowerCase();
        const searchText = `${codigoReal} ${row.asunto || ''} ${row.solicitante || ''} ${row.categoria || ''}`.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        if (query && !searchText.includes(query)) return false;

        const slaInfo = calcularPlazoVisualSla(row);
        if (currentSlaFilter === 'en-tiempo' && slaInfo.nivel !== 'en-tiempo') return false;
        if (currentSlaFilter === 'por-vencer' && slaInfo.nivel !== 'por-vencer') return false;
        if (currentSlaFilter === 'vencidos' && slaInfo.nivel !== 'vencidos') return false;

        if (priority && row.prioridad !== priority) return false;
        if (category && row.categoria !== category) return false;
        if (technician && (row.tecnico || 'Sin asignar') !== technician) return false;
        if (status && row.estado !== status) return false;

        return true;
    });

    paginaActualSla = 1;
    renderizarSla();
    actualizarMetricasSlaGlobales();
}

function actualizarMetricasSlaGlobales() {
    let enTiempo = 0, porVencer = 0, vencidos = 0, totalResueltos = 0, resueltosATiempo = 0;

    ticketsGlobales.forEach(t => {
        const info = calcularPlazoVisualSla(t);
        if (info.nivel === 'en-tiempo') enTiempo++;
        else if (info.nivel === 'por-vencer') porVencer++;
        else if (info.nivel === 'vencidos') vencidos++;

        if (t.estado === 'Resuelto' || t.estado === 'Cerrado') {
            totalResueltos++;
            if (t.semaforo === 'cumplido') resueltosATiempo++;
        }
    });

    const cumplimiento = totalResueltos > 0 ? Math.round((resueltosATiempo / totalResueltos) * 100) : 0;

    const metricCards = document.querySelectorAll('.stat-card, .metric-card');
    if (metricCards.length >= 4) {
        if (metricCards[0].querySelector('.stat-number, strong')) metricCards[0].querySelector('.stat-number, strong').textContent = `${cumplimiento}%`;
        if (metricCards[1].querySelector('.stat-number, strong')) metricCards[1].querySelector('.stat-number, strong').textContent = enTiempo;
        if (metricCards[2].querySelector('.stat-number, strong')) metricCards[2].querySelector('.stat-number, strong').textContent = porVencer;
        if (metricCards[3].querySelector('.stat-number, strong')) metricCards[3].querySelector('.stat-number, strong').textContent = vencidos;
    }

    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        const textoOriginal = tab.textContent.split('(')[0].trim();
        if (textoOriginal.includes('Todos')) tab.innerHTML = `Todos <span>(${ticketsGlobales.length})</span>`;
        if (textoOriginal.includes('En tiempo')) tab.innerHTML = `En tiempo <span>(${enTiempo})</span>`;
        if (textoOriginal.includes('Por vencer')) tab.innerHTML = `Por vencer <span>(${porVencer})</span>`;
        if (textoOriginal.includes('Vencidos')) tab.innerHTML = `Vencidos <span>(${vencidos})</span>`;
    });

    actualizarGraficoBarrasSla(enTiempo, porVencer, vencidos);
}

function actualizarGraficoBarrasSla(enTiempo, porVencer, vencidos) {
    const barColumns = document.querySelectorAll('.chart-bars .bar-column');
    if (barColumns.length < 3) return;

    const valorMaximo = Math.max(enTiempo, porVencer, vencidos, 1);
    const escalaAltura = 85;

    [{ valor: enTiempo, index: 0 }, { valor: porVencer, index: 1 }, { valor: vencidos, index: 2 }].forEach(item => {
        const col = barColumns[item.index];
        if (!col) return;
        const labelNumero = col.querySelector('b');
        const barraVisual = col.querySelector('.bar');
        if (labelNumero) labelNumero.textContent = item.valor;
        
        const alturaFinal = item.valor > 0 ? Math.max(Math.round((item.valor / valorMaximo) * escalaAltura), 8) : 4; 
        if (barraVisual) {
            barraVisual.style.height = `${alturaFinal}%`;
            barraVisual.style.setProperty('--bar-height', `${alturaFinal}%`);
        }
    });
}

function renderizarSla() {
    const tbody = document.getElementById('tickets-tbody');
    const resultsLabel = document.getElementById('results-label');
    if (!tbody) return;

    const total = ticketsFiltradosSla.length;
    const totalPaginas = Math.max(1, Math.ceil(total / pageSizeSla));
    paginaActualSla = Math.min(Math.max(1, paginaActualSla), totalPaginas);

    const inicio = (paginaActualSla - 1) * pageSizeSla;
    const paginaDatos = ticketsFiltradosSla.slice(inicio, inicio + pageSizeSla);

    if (total === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 24px; color: #58749a;">No hay tickets registrados que coincidan con los filtros.</td></tr>`;
        if (resultsLabel) resultsLabel.textContent = "Mostrando 0 tickets";
        renderizarPaginacionSla(1);
        return;
    }

    if (resultsLabel) resultsLabel.textContent = `Mostrando ${inicio + 1}–${Math.min(inicio + pageSizeSla, total)} de ${total} tickets`;

    tbody.innerHTML = paginaDatos.map(t => {
        const codigo = obtenerCodigoTicket(t);
        const plazo = calcularPlazoVisualSla(t);
        const tecnico = t.tecnico || 'Sin asignar';
        const urlDetalle = `/detalle_ticket?id=${t.id}`;
        
        let clasePill = 'ok';
        if (plazo.nivel === 'por-vencer') clasePill = 'warning';
        if (plazo.nivel === 'vencidos') clasePill = 'danger';

        const prioLower = (t.prioridad || 'Media').toLowerCase();
        const prioClase = prioLower === 'alta' ? 'high' : (prioLower === 'media' ? 'medium' : 'low');

        let estadoClase = 'pending';
        const estLower = (t.estado || '').toLowerCase();
        if (estLower.includes('proceso')) estadoClase = 'progress';
        else if (estLower.includes('resuelto') || estLower.includes('cerrado')) estadoClase = 'resolved';

        return `
        <tr data-id="${t.id}">
            <td class="check-col"><input class="row-check" type="checkbox" aria-label="Seleccionar ${escaparHTML(codigo)}"></td>
            <td><a class="ticket-code" href="${urlDetalle}">${escaparHTML(codigo)}</a></td>
            <td>
                <div style="font-weight: 700; color: #102b50; margin-bottom: 2px;">${escaparHTML(t.asunto)}</div>
                <small style="color: #56769f;">${escaparHTML(t.categoria)}</small>
            </td>
            <td><span class="priority-badge ${prioClase}"><i></i>${escaparHTML(t.prioridad)}</span></td>
            <td style="color: #254f81;">${tiempoRelativoSla(t.created_at)}</td>
            <td style="color: #58749a;">${t.fecha_limite ? formatearFechaSla(t.fecha_limite) : 'Estipulado por prioridad'}</td>
            <td>
                <span class="jira-pill-sla ${clasePill}" title="${plazo.detalle}">
                    <i style="width: 6px; height: 6px; border-radius: 50%; background: currentColor; display:inline-block;"></i>
                    ${plazo.texto}
                </span>
            </td>
            <td>${tecnico === 'Sin asignar' ? `<span class="unassigned">Sin asignar</span>` : `<div class="technician-chip"><i>${tecnico.charAt(0).toUpperCase()}</i><span>${escaparHTML(tecnico)}</span></div>`}</td>
            <td><span class="status-badge ${estadoClase}">${escaparHTML(t.estado)}</span></td>
            <td>
                <div class="row-actions">
                    <button type="button" class="icon-button" title="Ver detalle" onclick="location.href='${urlDetalle}'">◉</button>
                </div>
            </td>
        </tr>`;
    }).join('');

    renderizarPaginacionSla(totalPaginas);
}

function tiempoRelativoSla(iso) {
    if (!iso) return '—';
    const d = new Date(iso.replace(' ', 'T'));
    const min = Math.floor(Math.max(0, Date.now() - d.getTime()) / 60000);
    if (min < 60) return `Hace ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `Hace ${h} h`;
    return `Hace ${Math.floor(h / 24)} días`;
}

function formatearFechaSla(iso) {
    const d = new Date(iso.replace(' ', 'T'));
    return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('es-PE');
}

function renderizarPaginacionSla(totalPaginas) {
    const pagContainer = document.querySelector('.pagination');
    if (!pagContainer) return;
    
    let htmlPag = `<button id="prev-page" type="button" aria-label="Anterior" ${paginaActualSla === 1 ? 'disabled' : ''}>‹</button>`;
    for (let i = 1; i <= totalPaginas; i++) {
        htmlPag += `<button class="page-number ${i === paginaActualSla ? 'active' : ''}" type="button" data-page="${i}">${i}</button>`;
    }
    htmlPag += `<button id="next-page" type="button" aria-label="Siguiente" ${paginaActualSla === totalPaginas ? 'disabled' : ''}>›</button>`;
    pagContainer.innerHTML = htmlPag;

    pagContainer.querySelector('#prev-page')?.addEventListener('click', () => {
        if (paginaActualSla > 1) { paginaActualSla--; renderizarSla(); }
    });
    pagContainer.querySelector('#next-page')?.addEventListener('click', () => {
        if (paginaActualSla < totalPaginas) { paginaActualSla++; renderizarSla(); }
    });
    pagContainer.querySelectorAll('.page-number').forEach(btn => {
        btn.addEventListener('click', (e) => {
            paginaActualSla = parseInt(e.target.dataset.page);
            renderizarSla();
        });
    });
}

function configurarEventosSla() {
    document.querySelectorAll(".tab, [data-sla]").forEach(tab => {
        tab.addEventListener("click", () => {
            currentSlaFilter = tab.dataset.sla || 'all';
            document.querySelectorAll(".tab, [data-sla]").forEach(item => {
                const active = item === tab;
                item.classList.toggle("active", active);
                item.setAttribute("aria-selected", String(active));
            });
            aplicarFiltrosSla();
        });
    });

    ['priority-filter', 'category-filter', 'technician-filter', 'status-filter'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', aplicarFiltrosSla);
    });

    document.getElementById('global-search')?.addEventListener('input', aplicarFiltrosSla);
}


/* ---------------------------------------------------------
   Configuración Dinámica de Prioridades por Categoría
   --------------------------------------------------------- */
function mensajeSla(texto) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = texto;
    toast.classList.add('show');
    clearTimeout(mensajeSla.t);
    mensajeSla.t = setTimeout(() => toast.classList.remove('show'), 3200);
}

function mostrarConfirmacionSla(mensaje, alConfirmar) {
    const modal = document.getElementById('modal-confirm-sla');
    if (!modal) return;
    
    document.getElementById('texto-confirm-sla').textContent = mensaje;
    modal.style.display = 'flex';
    
    const btnOk = document.getElementById('btn-confirmar-sla-ok');
    const btnCancel = document.getElementById('btn-confirmar-sla-cancel');
    
    // Clonar para evitar eventos duplicados
    const nuevoBtnOk = btnOk.cloneNode(true);
    const nuevoBtnCancel = btnCancel.cloneNode(true);
    btnOk.parentNode.replaceChild(nuevoBtnOk, btnOk);
    btnCancel.parentNode.replaceChild(nuevoBtnCancel, btnCancel);
    
    nuevoBtnCancel.addEventListener('click', () => { modal.style.display = 'none'; });
    nuevoBtnOk.addEventListener('click', () => {
        modal.style.display = 'none';
        alConfirmar();
    });
}

function formatearTiempoPersonalizado(horas, minutos) {
    let result = [];
    if (horas > 0) result.push(`${horas}H`);
    if (minutos > 0) result.push(`${minutos}M`);
    return result.length ? result.join(' ') : '0M';
}

async function cargarConfiguracionCategoriasSla() {
    const contenedor = document.getElementById('lista-config-categorias');
    if (!contenedor) return;

    try {
        const res = await fetch('/api/configuracion/categorias-prioridad', { credentials: 'same-origin' });
        if (!res.ok) throw new Error("Error en red");
        
        const data = await res.json();
        const categorias = data.categorias || [];
        prioridadesDisponibles = data.prioridades || [];

        if (categorias.length === 0) {
            contenedor.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:15px; color:#94a3b8;">Sin categorías registradas</td></tr>`;
            return;
        }

        let html = "";
        categorias.forEach(cat => {
            const prio = prioridadesDisponibles.find(p => p.id === cat.prioridad_id) || { nombre: 'No asignada' };
            const prioLower = (prio.nombre || '').toLowerCase();
            const prioClase = prioLower === 'alta' ? 'high' : (prioLower === 'media' ? 'medium' : 'low');
            
            const h = cat.tiempo_horas !== undefined ? cat.tiempo_horas : (prio.sla_horas || 0);
            const m = cat.tiempo_minutos || 0;
            const tiempoFormateado = formatearTiempoPersonalizado(h, m);

            html += `
                <tr class="fila-categoria" data-id="${cat.categoria_id}" data-nombre="${cat.categoria_nombre}" data-prioridad="${prio.id}" data-horas="${h}" data-minutos="${m}" style="border-bottom: 1px solid #f1f5f9; cursor: pointer; transition: background 0.2s;">
                    <td style="padding: 6px 4px; font-weight: 600; color: #334155; white-space: nowrap; font-size: 0.7rem;">
                        ${escaparHTML(cat.categoria_nombre).toUpperCase()}
                    </td>
                    <td style="padding: 6px 4px; white-space: nowrap;">
                        <span class="priority-badge ${prioClase}" style="font-size: 0.6rem; padding: 2px 4px; margin: 0;"><i></i>${escaparHTML(prio.nombre).toUpperCase()}</span>
                    </td>
                    <td style="padding: 6px 4px; font-weight: 600; color: #475569; white-space: nowrap; font-size: 0.7rem;">
                        ${tiempoFormateado}
                    </td>
                </tr>
            `;
        });
        contenedor.innerHTML = html;
        
        const filas = document.querySelectorAll('.fila-categoria');
        filas.forEach(fila => {
            fila.addEventListener('click', () => {
                filas.forEach(f => f.style.backgroundColor = 'transparent');
                fila.style.backgroundColor = '#e2e8f0'; 
                
                categoriaSeleccionada = {
                    id: fila.getAttribute('data-id'),
                    nombre: fila.getAttribute('data-nombre'),
                    prioridad: fila.getAttribute('data-prioridad'),
                    horas: fila.getAttribute('data-horas'),
                    minutos: fila.getAttribute('data-minutos')
                };
            });
        });
    } catch (e) {
        contenedor.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:15px; color:#ef4444;">Error de conexión</td></tr>`;
    }
}

function abrirModal(modo) {
    const modal = document.getElementById('modal-sla');
    if (!modal) return;

    const titulo = document.getElementById('modal-sla-titulo');
    const inputNombre = document.getElementById('modal-sla-nombre');
    const selectPrioridad = document.getElementById('modal-sla-prioridad');
    const inputHoras = document.getElementById('modal-sla-horas');
    const inputMinutos = document.getElementById('modal-sla-minutos');

    selectPrioridad.innerHTML = prioridadesDisponibles.map(p => 
        `<option value="${p.id}">${p.nombre}</option>`
    ).join('');

    if (modo === 'agregar') {
        categoriaSeleccionada = null;
        document.querySelectorAll('.fila-categoria').forEach(f => f.style.backgroundColor = 'transparent');
        titulo.textContent = 'Agregar Categoría';
        inputNombre.value = '';
        inputHoras.value = '1';
        inputMinutos.value = '0';
    } else if (modo === 'editar') {
        if (!categoriaSeleccionada) {
            mensajeSla("Selecciona una categoría de la tabla primero.");
            return;
        }
        titulo.textContent = 'Editar Categoría';
        inputNombre.value = categoriaSeleccionada.nombre;
        selectPrioridad.value = categoriaSeleccionada.prioridad;
        inputHoras.value = categoriaSeleccionada.horas;
        inputMinutos.value = categoriaSeleccionada.minutos;
    }
    
    modal.style.display = 'flex';
}

function cerrarModal() {
    const modal = document.getElementById('modal-sla');
    if (modal) modal.style.display = 'none';
}

// Inicialización de la configuración lateral al cargar la vista
// Inicialización de la configuración lateral al cargar la vista
document.addEventListener('DOMContentLoaded', () => {
    cargarConfiguracionCategoriasSla();

    document.getElementById('btn-agregar-sla')?.addEventListener('click', () => abrirModal('agregar'));
    document.getElementById('btn-editar-sla')?.addEventListener('click', () => abrirModal('editar'));
    document.getElementById('btn-cancelar-sla')?.addEventListener('click', cerrarModal);
    
    document.getElementById('btn-eliminar-sla')?.addEventListener('click', () => {
        if (!categoriaSeleccionada) {
            mensajeSla("Selecciona una categoría de la tabla primero.");
            return;
        }
        
        mostrarConfirmacionSla(
            `¿Estás seguro de que deseas eliminar la categoría "${categoriaSeleccionada.nombre}"?`,
            async () => {
                try {
                    const res = await fetch(`/api/configuracion/categoria-individual/${categoriaSeleccionada.id}`, {
                        method: 'DELETE',
                        credentials: 'same-origin'
                    });
                    if (res.ok) {
                        mensajeSla(`Categoría "${categoriaSeleccionada.nombre}" eliminada.`);
                        categoriaSeleccionada = null; 
                        cargarConfiguracionCategoriasSla(); 
                    } else {
                        mensajeSla("Error al eliminar en la base de datos.");
                    }
                } catch (e) {
                    mensajeSla("Error de conexión con el servidor.");
                }
            }
        );
    });

    // Enlace directo y seguro para el botón Guardar del Modal
    const btnGuardarModal = document.getElementById('btn-guardar-modal-sla');
    if (btnGuardarModal) {
        btnGuardarModal.addEventListener('click', async () => {
            const nombreInput = document.getElementById('modal-sla-nombre');
            const prioridadSelect = document.getElementById('modal-sla-prioridad');
            const horasInput = document.getElementById('modal-sla-horas');
            const minutosInput = document.getElementById('modal-sla-minutos');

            const nombre = nombreInput ? nombreInput.value.trim() : '';
            const prioridad = prioridadSelect ? prioridadSelect.value : '';
            const horas = horasInput ? horasInput.value : '0';
            const minutos = minutosInput ? minutosInput.value : '0';
            
            if (!nombre) {
                mensajeSla("El nombre de la categoría es obligatorio.");
                return;
            }
            
            const payload = {
                categoria_id: categoriaSeleccionada ? categoriaSeleccionada.id : null,
                nombre: nombre,
                prioridad_id: parseInt(prioridad, 10),
                horas: parseInt(horas, 10) || 0,
                minutos: parseInt(minutos, 10) || 0
            };

            try {
                const res = await fetch('/api/configuracion/categoria-individual', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                
                if (res.ok) {
                    mensajeSla("Configuración guardada exitosamente.");
                    cerrarModal();
                    categoriaSeleccionada = null;
                    cargarConfiguracionCategoriasSla(); // Recarga la tabla de inmediato
                } else {
                    mensajeSla("Error al guardar: " + (data.error || "Desconocido"));
                }
            } catch (e) {
                mensajeSla("Error de conexión con el servidor.");
            }
        });
    }
});