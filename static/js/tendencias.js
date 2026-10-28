/* =========================================================
   tendencias.js — llena los indicadores "vs. mes anterior" de las
   tarjetas con datos reales (GET /api/tendencias).
   Cada indicador tiene data-tendencia="grupo.metrica", por ejemplo
   data-tendencia="tickets.abiertos".
   ========================================================= */
document.addEventListener('DOMContentLoaded', async () => {
    const elementos = document.querySelectorAll('[data-tendencia]');
    if (!elementos.length) return;
    // Métricas en las que BAJAR es bueno
    const menosEsMejor = ['abiertos', 'vencidos', 'pendientes', 'no_leidas'];
    let datos = {};
    try {
        const res = await fetch('/api/tendencias', { credentials: 'same-origin' });
        if (!res.ok) throw new Error();
        datos = await res.json();
    } catch (e) {
        elementos.forEach((el) => (el.firstChild.textContent = '— '));
        return;
    }
    elementos.forEach((el) => {
        const [grupo, metrica] = el.dataset.tendencia.split('.');
        const m = (datos[grupo] || {})[metrica];
        const sufijo = el.querySelector('em, small, i');
        if (sufijo) sufijo.textContent = 'vs. mes anterior';
        let texto, favorable = true;
        if (!m) {
            texto = '— ';
        } else if (m.variacion === null) {
            texto = m.actual ? `+${m.actual} este mes ` : '＝ 0% ';
            favorable = !(m.actual && menosEsMejor.includes(metrica));
        } else {
            const flecha = m.variacion > 0 ? '↑' : (m.variacion < 0 ? '↓' : '＝');
            texto = `${flecha} ${Math.abs(m.variacion)}% `;
            favorable = menosEsMejor.includes(metrica) ? m.variacion <= 0 : m.variacion >= 0;
        }
        // Reemplaza solo el texto antes del sufijo, conserva el diseño
        [...el.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).forEach((n) => n.remove());
        el.insertBefore(document.createTextNode(texto), el.firstChild);
        if (m) el.title = `Este mes: ${m.actual} · Mes anterior: ${m.anterior}`;
        // Colores de cada página (positive/negative, up/down, good/bad)
        const pares = [['positive', 'negative'], ['up', 'down'], ['good', 'bad']];
        pares.forEach(([bien, mal]) => {
            if (el.classList.contains(bien) || el.classList.contains(mal)) {
                el.classList.toggle(bien, favorable);
                el.classList.toggle(mal, !favorable);
            }
        });
    });
});
