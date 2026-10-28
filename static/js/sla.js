/* =========================================================
   sla.js — Módulo SLA Sincronizado y Dinámico con la BD
   ========================================================= */

let ticketsGlobales = [];
let ticketsFiltradosSla = [];
let paginaActualSla = 1;
const pageSizeSla = 10;
let currentSlaFilter = "all";

const CLASE_PRIORIDAD = { Alta: 'priority-high', Media: 'priority-medium', Baja: 'priority-low' };
const CLASE_ESTADO = {
    Abierto: 'status-open',
    'En proceso': 'status-progress',
    Resuelto: 'status-resolved',
    Cerrado: 'status-closed'
};

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("tickets-tbody")) return;
    configurarEventosSla();
    cargarTicketsSla();
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

// MÓDULO 4: el semáforo ya viene calculado por el servidor (Python) con los plazos reales
// de la tabla prioridades (Alta 4 h, Media 24 h, Baja 72 h). Aquí solo se traduce a la vista.
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
    // Opciones tomadas de los tickets reales de la empresa (nada escrito a mano)
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
        
        if (technician) {
            const tecRow = row.tecnico || 'Sin asignar';
            if (tecRow !== technician) return false;
        }

        if (status && row.estado !== status) return false;

        return true;
    });

    paginaActualSla = 1;
    renderizarSla();
    actualizarMetricasSlaGlobales();
}

function actualizarMetricasSlaGlobales() {
    let enTiempo = 0;
    let porVencer = 0;
    let vencidos = 0;
    let totalResueltos = 0;
    let resueltosATiempo = 0;

    ticketsGlobales.forEach(t => {
        const info = calcularPlazoVisualSla(t);
        
        // Conteo operativo actual
        if (info.nivel === 'en-tiempo') enTiempo++;
        else if (info.nivel === 'por-vencer') porVencer++;
        else if (info.nivel === 'vencidos') vencidos++;

        if (t.estado === 'Resuelto' || t.estado === 'Cerrado') {
            totalResueltos++;
            if (t.semaforo === 'cumplido') {
                resueltosATiempo++;
            }
        }
    });

    const cumplimiento = totalResueltos > 0 ? Math.round((resueltosATiempo / totalResueltos) * 100) : 0;

    // 1. Actualizar tarjetas superiores de métricas
    const metricCards = document.querySelectorAll('.stat-card, .metric-card');
    if (metricCards.length >= 4) {
        if (metricCards[0].querySelector('.stat-number, strong')) metricCards[0].querySelector('.stat-number, strong').textContent = `${cumplimiento}%`;
        if (metricCards[1].querySelector('.stat-number, strong')) metricCards[1].querySelector('.stat-number, strong').textContent = enTiempo;
        if (metricCards[2].querySelector('.stat-number, strong')) metricCards[2].querySelector('.stat-number, strong').textContent = porVencer;
        if (metricCards[3].querySelector('.stat-number, strong')) metricCards[3].querySelector('.stat-number, strong').textContent = vencidos;
    }

    // 2. Actualizar contadores de las pestañas superiores de la tabla
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        const textoOriginal = tab.textContent.split('(')[0].trim();
        if (textoOriginal.includes('Todos')) tab.innerHTML = `Todos <span>(${ticketsGlobales.length})</span>`;
        if (textoOriginal.includes('En tiempo')) tab.innerHTML = `En tiempo <span>(${enTiempo})</span>`;
        if (textoOriginal.includes('Por vencer')) tab.innerHTML = `Por vencer <span>(${porVencer})</span>`;
        if (textoOriginal.includes('Vencidos')) tab.innerHTML = `Vencidos <span>(${vencidos})</span>`;
    });

    // 3. Actualizar dinámicamente el Gráfico de Barras ("Tickets por estado de SLA")
    actualizarGraficoBarrasSla(enTiempo, porVencer, vencidos);
}

function actualizarGraficoBarrasSla(enTiempo, porVencer, vencidos) {
    const barColumns = document.querySelectorAll('.chart-bars .bar-column');
    if (barColumns.length < 3) return;

    // Calculamos el valor máximo para escalar las alturas de forma proporcional (mínimo 1 para evitar división por cero)
    const valorMaximo = Math.max(enTiempo, porVencer, vencidos, 1);
    
    // Altura máxima en porcentaje para la barra más alta (ej. 85% para que no tope el techo)
    const escalaAltura = 85;

    const datosBarras = [
        { valor: enTiempo, index: 0 },
        { valor: porVencer, index: 1 },
        { valor: vencidos, index: 2 }
    ];

    datosBarras.forEach(item => {
        const col = barColumns[item.index];
        if (!col) return;

        const labelNumero = col.querySelector('b');
        const barraVisual = col.querySelector('.bar');

        // Actualizar el número flotante sobre la barra
        if (labelNumero) {
            labelNumero.textContent = item.valor;
        }

        // Calcular la altura proporcional de la barra
        const alturaPorcentual = Math.round((item.valor / valorMaximo) * escalaAltura);
        const alturaFinal = item.valor > 0 ? Math.max(alturaPorcentual, 8) : 4; // Mínimo 4px para que se note si es 0

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

    if (resultsLabel) {
        resultsLabel.textContent = `Mostrando ${inicio + 1}–${Math.min(inicio + pageSizeSla, total)} de ${total} tickets`;
    }

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

        // Mapeo seguro de estado visual
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

    const globalSearch = document.getElementById('global-search');
    globalSearch?.addEventListener('input', aplicarFiltrosSla);
}

/* ---------------------------------------------------------
   Configuración de SLA: muestra los plazos reales de la BD y
   los guarda (solo el superusuario; son iguales para todas las empresas).
   --------------------------------------------------------- */
function mensajeSla(texto) {
    const toast = document.getElementById('toast');
    if (!toast) { alert(texto); return; }
    toast.textContent = texto;
    toast.classList.add('show');
    clearTimeout(mensajeSla.t);
    mensajeSla.t = setTimeout(() => toast.classList.remove('show'), 3200);
}

function horasDeOpcion(texto) {
    const n = parseInt(texto, 10);
    if (isNaN(n)) return null;
    return /d[ií]a/i.test(texto) ? n * 24 : (/min/i.test(texto) ? null : n);
}

async function cargarConfiguracionSla() {
    const form = document.getElementById('sla-config-form');
    if (!form) return;
    try {
        const res = await fetch('/api/sla/configuracion', { credentials: 'same-origin' });
        if (!res.ok) return;
        const { prioridades } = await res.json();
        prioridades.forEach(p => {
            const select = form.querySelector(`select[data-priority="${p.nombre}"][data-kind="resolution"]`);
            if (!select) return;
            let opcion = [...select.options].find(o => horasDeOpcion(o.textContent) === p.sla_horas);
            if (!opcion) {
                opcion = new Option(`${p.sla_horas} horas`);
                select.add(opcion, 0);
            }
            select.value = opcion.value;
        });
    } catch (e) {
        console.error('No se pudo leer la configuración de SLA', e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('sla-config-form');
    if (!form) return;
    cargarConfiguracionSla();
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const prioridades = {};
        form.querySelectorAll('select[data-kind="resolution"]').forEach(s => {
            const horas = horasDeOpcion(s.options[s.selectedIndex].textContent);
            if (horas) prioridades[s.dataset.priority] = horas;
        });
        try {
            const res = await fetch('/api/sla/configuracion', {
                method: 'PUT', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prioridades })
            });
            const datos = await res.json();
            mensajeSla(datos.mensaje || datos.error || 'No se pudo guardar.');
            if (res.ok) cargarTicketsSla();
        } catch (err) {
            mensajeSla('No se pudo conectar con el servidor.');
        }
    });
});
