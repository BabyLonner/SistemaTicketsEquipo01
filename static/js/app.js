/* Mesa de Ayuda TI — comportamiento de la interfaz (sin librerías) */
(function () {
  'use strict';

  /* Selects que envían su formulario al cambiar (filtros, selector de empresa) */
  document.querySelectorAll('select[data-autoenviar]').forEach(function (sel) {
    sel.addEventListener('change', function () { sel.form && sel.form.submit(); });
  });

  /* Confirmación antes de acciones delicadas */
  document.querySelectorAll('form[data-confirmar]').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      var texto = form.getAttribute('data-confirmar');
      if (texto && !window.confirm(texto)) ev.preventDefault();
    });
  });

  /* Módulo 5: contador de la campana por fetch cada 30 s */
  var campana = document.querySelector('[data-contador-url]');
  var globo = document.getElementById('globo-notificaciones');
  if (campana && globo) {
    var actualizar = function () {
      fetch(campana.getAttribute('data-contador-url'), { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (datos) {
          if (!datos || typeof datos.no_leidas !== 'number') return;
          var n = datos.no_leidas;
          globo.textContent = n > 99 ? '99+' : n;
          globo.hidden = n === 0;
          campana.setAttribute('aria-label', 'Notificaciones, ' + n + ' sin leer');
        })
        .catch(function () { /* sin conexión: se reintenta en el siguiente ciclo */ });
    };
    setInterval(actualizar, 30000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) actualizar(); });
  }

  /* Login: muestra la empresa apenas se reconoce el dominio del correo */
  var correoLogin = document.querySelector('[data-empresa-url]');
  var identidad = document.getElementById('identidad-empresa');
  if (correoLogin && identidad) {
    var ultimoDominio = '';
    var buscarEmpresa = function () {
      var valor = correoLogin.value.trim().toLowerCase();
      var dominio = valor.indexOf('@') > -1 ? valor.split('@').pop() : '';
      if (dominio === ultimoDominio) return;
      ultimoDominio = dominio;
      if (!dominio || dominio.indexOf('.') === -1) { identidad.classList.remove('visible'); return; }
      fetch(correoLogin.getAttribute('data-empresa-url') + '?correo=' + encodeURIComponent(valor))
        .then(function (r) { return r.json(); })
        .then(function (datos) {
          var e = datos && datos.empresa;
          if (!e) { identidad.classList.remove('visible'); return; }
          identidad.querySelector('span').textContent = e.titulo_sistema;
          identidad.querySelector('i').style.background = e.color_primario;
          identidad.style.background = e.color_secundario;
          identidad.style.color = e.color_primario;
          identidad.classList.add('visible');
          document.documentElement.style.setProperty('--primario', e.color_primario);
          document.documentElement.style.setProperty('--secundario', e.color_secundario);
        })
        .catch(function () {});
    };
    var espera;
    correoLogin.addEventListener('input', function () { clearTimeout(espera); espera = setTimeout(buscarEmpresa, 350); });
    correoLogin.addEventListener('blur', buscarEmpresa);
    if (correoLogin.value) buscarEmpresa();
  }

  /* Nuevo ticket: 3 ranuras de fotos con vista previa y validación */
  var ranuras = document.querySelector('[data-ranuras]');
  if (ranuras) {
    var maxMb = parseInt(ranuras.getAttribute('data-max-mb'), 10) || 5;
    var contador = document.getElementById('contador-fotos');
    var tipos = ['image/jpeg', 'image/png', 'image/webp'];
    var contar = function () {
      var n = ranuras.querySelectorAll('.ranura.llena').length;
      contador.textContent = n + ' de 3 · solo imágenes JPG, PNG o WEBP';
    };
    ranuras.querySelectorAll('.ranura').forEach(function (ranura) {
      var input = ranura.querySelector('input[type=file]');
      var original = ranura.querySelector('span').outerHTML;
      var limpiar = function () {
        input.value = '';
        ranura.classList.remove('llena');
        ranura.querySelectorAll('img, .quitar, .nombre-archivo').forEach(function (el) { el.remove(); });
        if (!ranura.querySelector('span')) ranura.insertAdjacentHTML('beforeend', original);
        contar();
      };
      input.addEventListener('change', function () {
        var archivo = input.files && input.files[0];
        if (!archivo) { limpiar(); return; }
        if (tipos.indexOf(archivo.type) === -1) { alert('«' + archivo.name + '» no es una imagen JPG, PNG o WEBP.'); limpiar(); return; }
        if (archivo.size > maxMb * 1024 * 1024) { alert('«' + archivo.name + '» supera los ' + maxMb + ' MB.'); limpiar(); return; }
        var span = ranura.querySelector('span');
        if (span) span.remove();
        var img = document.createElement('img');
        img.alt = archivo.name;
        img.src = URL.createObjectURL(archivo);
        var quitar = document.createElement('button');
        quitar.type = 'button';
        quitar.className = 'quitar';
        quitar.setAttribute('aria-label', 'Quitar ' + archivo.name);
        quitar.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>';
        quitar.addEventListener('click', function (ev) { ev.preventDefault(); ev.stopPropagation(); limpiar(); });
        var nombre = document.createElement('span');
        nombre.className = 'nombre-archivo';
        nombre.textContent = archivo.name;
        ranura.append(img, quitar, nombre);
        ranura.classList.add('llena');
        contar();
      });
    });
    contar();
  }

  /* Detalle: galería de evidencias */
  var visor = document.getElementById('visor-imagen');
  if (visor) {
    var enlace = document.getElementById('visor-enlace');
    document.querySelectorAll('.tira').forEach(function (tira) {
      tira.addEventListener('click', function () {
        visor.src = tira.getAttribute('data-imagen');
        visor.alt = tira.getAttribute('data-nombre');
        enlace.href = tira.getAttribute('data-imagen');
        document.querySelectorAll('.tira').forEach(function (t) { t.setAttribute('aria-pressed', t === tira ? 'true' : 'false'); });
      });
    });
  }

  /* Cambio de estado: comentario obligatorio */
  document.querySelectorAll('form[data-requiere-comentario]').forEach(function (form) {
    var area = form.querySelector('textarea');
    var mensaje = form.querySelector('[data-mensaje]');
    form.addEventListener('submit', function (ev) {
      if (area.value.trim().length < 3) {
        ev.preventDefault();
        area.classList.add('con-error');
        mensaje.hidden = false;
        area.focus();
      }
    });
    area.addEventListener('input', function () { area.classList.remove('con-error'); mensaje.hidden = true; });
  });

  /* Registrar usuario: áreas y dominio según la empresa elegida */
  var formUsuario = document.querySelector('[data-form-usuario]');
  if (formUsuario) {
    var empresa = formUsuario.querySelector('[data-empresa]');
    var areas = formUsuario.querySelector('[data-areas]');
    var correo = formUsuario.querySelector('[data-correo]');
    var ayuda = formUsuario.querySelector('[data-ayuda-dominio]');
    var aplicar = function () {
      var id = empresa.value;
      var dominio = empresa.tagName === 'SELECT'
        ? (empresa.selectedOptions[0] && empresa.selectedOptions[0].getAttribute('data-dominio')) || ''
        : empresa.getAttribute('data-dominio') || '';
      Array.prototype.forEach.call(areas.options, function (op) {
        var visible = !op.value || op.getAttribute('data-empresa') === id;
        op.hidden = !visible;
        if (!visible && op.selected) areas.value = '';
      });
      if (dominio) {
        correo.placeholder = 'nombre.apellido@' + dominio;
        ayuda.textContent = 'Debe terminar en @' + dominio;
      }
    };
    empresa.addEventListener('change', aplicar);
    aplicar();
  }

  /* Formulario de empresa: vista previa de la identidad visual */
  var color1 = document.querySelector('[data-vista-color1]');
  if (color1) {
    var color2 = document.querySelector('[data-vista-color2]');
    var titulo = document.querySelector('[data-vista-titulo]');
    var nombreEmp = document.querySelector('[data-vista-nombre]');
    var pintar = function () {
      document.querySelector('[data-vista-barra]').style.background = color2.value;
      document.querySelector('[data-vista-barra]').style.color = color1.value;
      document.querySelector('[data-vista-icono]').style.background = color1.value;
      document.querySelector('[data-vista-boton]').style.background = color1.value;
      document.querySelector('[data-vista-texto]').textContent =
        titulo.value || (nombreEmp.value ? 'Mesa de Ayuda ' + nombreEmp.value : 'Vista previa');
    };
    [color1, color2, titulo, nombreEmp].forEach(function (el) { el.addEventListener('input', pintar); });
    pintar();
  }
})();
