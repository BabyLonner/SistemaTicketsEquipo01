/* ================= DATOS Y LÓGICA DE JAVASCRIPT ================= */

// 1. Simulación de base de datos
const ticketsData = [
    { id: '8VT-PZU-BRG9', updated: '25 Sep 26', name: 'Klemen', subject: 'Ticket priority Critical', status: 'New', replier: 'Klemen', priority: 'Alta', horasTranscurridas: 5 }, // Vencido (Límite 4h)[cite: 3]
    { id: 'VER-EWV-63B2', updated: '25 Sep 26', name: 'Jane Doe', subject: 'Another critical ticket', status: 'Replied', replier: 'Jane Doe', priority: 'Alta', horasTranscurridas: 3.5 }, // Por vencer (Límite 4h)[cite: 3]
    { id: 'PBG-J12-UJ9W', updated: '24 Sep 26', name: 'Jesus', subject: 'Ticket priority high', status: 'New', replier: 'Jesus', priority: 'Media', horasTranscurridas: 2 }, // A tiempo (Límite 24h)[cite: 3]
    { id: 'GST-MBA-DYA6', updated: '22 Sep 26', name: 'Admin', subject: 'Ticket priority medium', status: 'New', replier: 'Admin', priority: 'Baja', horasTranscurridas: 65 }, // Por vencer (Límite 72h)[cite: 3]
    { id: 'MN9-GNE-WX1D', updated: '23 Sep 26', name: 'Carlos', subject: 'Ticket priority low', status: 'New', replier: 'Carlos', priority: 'Media', horasTranscurridas: 26 } // Vencido (Límite 24h)[cite: 3]
];

// 2. Motor de cálculo de SLA[cite: 3]
function evaluarSLA(horas, prioridad) {
    let maxHoras = 24; // Por defecto
    
    if (prioridad === 'Alta') maxHoras = 4;
    else if (prioridad === 'Media') maxHoras = 24;
    else if (prioridad === 'Baja') maxHoras = 72;

    if (horas >= maxHoras) {
        return { color: 'rojo', claseFila: 'row-danger', texto: 'Vencido' };
    } else if (horas >= (maxHoras * 0.75)) {
        return { color: 'amarillo', claseFila: 'row-warning', texto: 'Por vencer' };
    } else {
        return { color: 'verde', claseFila: '', texto: 'A tiempo' };
    }
}

// 3. Renderizado de la interfaz
function cargarTickets() {
    const tbody = document.getElementById('tickets-tbody');
    let dueSoonCount = 0;
    let overdueCount = 0;
    let htmlFilas = '';

    // Procesar cada ticket
    ticketsData.forEach(ticket => {
        const sla = evaluarSLA(ticket.horasTranscurridas, ticket.priority);
        
        // Actualizar contadores para los botones superiores[cite: 1]
        if (sla.color === 'rojo') overdueCount++;
        if (sla.color === 'amarillo') dueSoonCount++;

        // Generar HTML de la fila con las clases calculadas[cite: 1, 3]
        htmlFilas += `
            <tr class="${sla.claseFila}">
                <td><input type="checkbox"></td>
                <td><a href="#" class="text-link">${ticket.id}</a></td>
                <td>${ticket.updated}</td>
                <td>${ticket.name}</td>
                <td><a href="#" class="text-link">${ticket.subject}</a></td>
                <td style="color: ${ticket.status === 'New' ? '#dc3545' : '#6f42c1'};">${ticket.status}</td>
                <td>${ticket.replier}</td>
                <td>
                    <span class="prioridad-icono sla-${sla.color}" title="${sla.texto} (${ticket.horasTranscurridas}h transcurridas)"></span>
                    ${ticket.priority}
                </td>
            </tr>
        `;
    });

    // Inyectar en la tabla y actualizar números
    tbody.innerHTML = htmlFilas;
    document.getElementById('count-open').innerText = ticketsData.length;
    document.getElementById('count-due').innerText = dueSoonCount;
    document.getElementById('count-overdue').innerText = overdueCount;
}

// Ejecutar cuando el HTML cargue
document.addEventListener('DOMContentLoaded', cargarTickets);