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

function calcularPlazoVisualSla(t) {
    if (t.estado === 'Resuelto' || t.estado === 'Cerrado') {
        return { texto: 'Cumplido', clase: 'ok', nivel: 'en-tiempo', detalle: 'SLA Finalizado' };
    }
    
    const prio = t.prioridad || 'Media';
    const limiteHoras = prio === 'Alta' ? 8 : (prio === 'Media' ? 24 : 72);
    
    if (t.created_at) {
        const fechaCreacion = new Date(t.created_at.replace(' ', 'T'));
        const ahora = new Date();
        const horasTranscurridas = (ahora - fechaCreacion) / (1000 * 60 * 60);
        
        if (horasTranscurridas > limiteHoras) {
            return { texto: 'Vencido', clase: 'danger', nivel: 'vencidos', detalle: 'Plazo excedido' };
        } else if (horasTranscurridas >= limiteHoras * 0.8) {
            const horasRestantes = Math.ceil(limiteHoras - horasTranscurridas);
            return { texto: `Por vencer (${horasRestantes}h)`, clase: 'warning', nivel: 'por-vencer', detalle: `${horasRestantes}h restantes` };
        } else {
            const horasRestantes = Math.floor(limiteHoras - horasTranscurridas);
            return { texto: `A tiempo (${horasRestantes}h)`, clase: 'ok', nivel: 'en-tiempo', detalle: `${horasRestantes}h restantes` };
        }
    }
    return { texto: 'A tiempo', clase: 'ok', nivel: 'en-tiempo', detalle: 'En curso' };
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
    // 1. Técnicos oficiales según requerimiento
    const selectTecnico = document.getElementById('technician-filter');
    if (selectTecnico) {
        const tecnicosOficiales = [
            "Luis Ramos",
            "Carla Mendoza",
            "José García",
            "María Torres",
            "Rosa Villanueva",
            "Sin asignar"
        ];
        let html = `<option value="">Todos los técnicos</option>`;
        tecnicosOficiales.forEach(tec => {
            html += `<option value="${escaparHTML(tec)}">${escaparHTML(tec)}</option>`;
        });
        selectTecnico.innerHTML = html;
        selectTecnico.value = ""; // Valor por defecto en "Todos"
    }

    // 2. Categorías oficiales según requerimiento
    const selectCategoria = document.getElementById('category-filter');
    if (selectCategoria) {
        const categoriasOficiales = [
            "Accesos y cuentas",
            "Correo",
            "Hardware",
            "Impresoras",
            "Red e internet",
            "Software"
        ];
        let html = `<option value="">Todas</option>`;
        categoriasOficiales.forEach(cat => {
            html += `<option value="${escaparHTML(cat)}">${escaparHTML(cat)}</option>`;
        });
        selectCategoria.innerHTML = html;
    }

    // 3. Estados oficiales según requerimiento (incluyendo "Abierto")
    const selectEstado = document.getElementById('status-filter');
    if (selectEstado) {
        const estadosOficiales = [
            "Abierto",
            "Pendiente",
            "Asignado",
            "En proceso",
            "Resuelto",
            "Cerrado"
        ];
        let html = `<option value="">Todos</option>`;
        estadosOficiales.forEach(est => {
            html += `<option value="${escaparHTML(est)}">${escaparHTML(est)}</option>`;
        });
        selectEstado.innerHTML = html;
    }
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
            if (info.nivel === 'en-tiempo' || info.texto.includes('Cumplido')) {
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