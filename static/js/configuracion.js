// Pantalla de Configuración: vista previa en vivo de los colores, el título y el logo
(function () {
  const c1 = document.getElementById('color_primario'), c2 = document.getElementById('color_secundario');
  const titulo = document.getElementById('titulo_sistema'), logo = document.getElementById('logo_url');
  const pintar = () => {
    document.getElementById('prev-button').style.background = c1.value;
    const badge = document.getElementById('prev-badge');
    badge.style.background = c2.value; badge.style.color = c1.value;
    document.getElementById('prev-title').textContent = titulo.value;
    const img = document.getElementById('prev-logo');
    img.hidden = !logo.value; if (logo.value) img.src = logo.value;
  };
  [c1, c2, titulo, logo].forEach((el) => el.addEventListener('input', pintar));
})();

// Módulo 8: la casilla "Envío semanal" se guarda al marcarla
document.querySelectorAll('.check-semanal').forEach((casilla) => {
  casilla.addEventListener('change', () => casilla.form.requestSubmit());
});

// Módulo 8: el reporte tiene datos internos, se confirma a quién se envía
document.getElementById('form-envio-manual').addEventListener('submit', (evento) => {
  const formulario = evento.target;
  const correos = [...formulario.querySelectorAll('input[name="destinatarios"]:checked')].map((c) => c.dataset.correo);
  const otro = formulario.elements.otro_correo.value.trim().toLowerCase();
  if (otro && !correos.includes(otro)) correos.push(otro);
  if (correos.length && !confirm(`Se enviará a ${correos.join(', ')}. ¿Continuar?`)) evento.preventDefault();
});
