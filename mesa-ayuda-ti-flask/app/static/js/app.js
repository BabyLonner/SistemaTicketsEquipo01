/* Mesa de Ayuda TI — comportamiento común a todas las páginas */
(function () {
  'use strict';

  /* ---------- Token CSRF para peticiones fetch ----------
     El JWT viaja en una cookie HttpOnly. Para PUT/POST/DELETE con fetch
     hay que enviar el token CSRF en el header X-CSRF-TOKEN. */
  function leerCookie(nombre) {
    const par = document.cookie.split('; ').find(function (c) { return c.startsWith(nombre + '='); });
    return par ? decodeURIComponent(par.split('=')[1]) : '';
  }

  window.MesaTI = {
    peticion: function (url, opciones) {
      opciones = opciones || {};
      const headers = Object.assign({ 'Accept': 'application/json' }, opciones.headers || {});
      if (opciones.method && opciones.method !== 'GET') headers['X-CSRF-TOKEN'] = leerCookie('csrf_access_token');
      return fetch(url, Object.assign({ credentials: 'same-origin' }, opciones, { headers: headers }))
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
    },
    toast: function (mensaje, tipo) {
      const zona = document.getElementById('zona-toasts');
      if (!zona || !window.bootstrap) return;
      const el = document.createElement('div');
      el.className = 'toast align-items-center' + (tipo === 'error' ? ' toast--error' : '');
      el.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
      el.innerHTML = '<div class="d-flex"><div class="toast-body"></div>' +
        '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Cerrar"></button></div>';
      el.querySelector('.toast-body').textContent = mensaje;
      zona.appendChild(el);
      el.addEventListener('hidden.bs.toast', function () { el.remove(); });
      new bootstrap.Toast(el, { delay: 4000 }).show();
    },
    actualizarCampana: function (total) {
      const badge = document.getElementById('campana-badge');
      const campana = document.getElementById('campana');
      if (!badge || !campana) return;
      badge.textContent = total > 9 ? '9+' : String(total);
      badge.hidden = total === 0;
      campana.setAttribute('aria-label', total ? 'Notificaciones, ' + total + ' sin leer' : 'Notificaciones');
    }
  };

  /* ---------- Mensajes flash de Flask ---------- */
  document.querySelectorAll('#zona-toasts .toast').forEach(function (el) {
    if (window.bootstrap) new bootstrap.Toast(el).show();
  });

  /* ---------- Fechas relativas: "hace 3 h" ---------- */
  function duracion(segundos) {
    const min = Math.max(1, Math.round(segundos / 60));
    if (min < 60) return min + ' min';
    const h = Math.floor(min / 60), rm = min % 60;
    if (h < 24) return h < 10 && rm ? h + ' h ' + rm + ' min' : h + ' h';
    const d = Math.floor(h / 24), rh = h % 24;
    return rh ? d + ' d ' + rh + ' h' : d + ' d';
  }
  function relativa(fecha) {
    const seg = (Date.now() - fecha.getTime()) / 1000;
    if (seg < 60) return 'hace un momento';
    if (seg >= 86400 && seg < 172800) return 'ayer';
    return 'hace ' + duracion(seg);
  }
  function pintarFechas() {
    document.querySelectorAll('time[data-relativa]').forEach(function (t) {
      const fecha = new Date(t.getAttribute('datetime'));
      if (!isNaN(fecha)) t.textContent = relativa(fecha);
    });
  }
  pintarFechas();
  setInterval(pintarFechas, 60000);

  /* ---------- Formularios que se envían al cambiar un select ---------- */
  document.querySelectorAll('form[data-autoenviar] select').forEach(function (s) {
    s.addEventListener('change', function () { s.form.submit(); });
  });
  document.querySelectorAll('select[data-autoenviar-campo]').forEach(function (s) {
    s.addEventListener('change', function () { s.form.submit(); });
  });

  /* ---------- Contador de la campana (AJAX cada minuto) ---------- */
  if (document.getElementById('campana')) {
    setInterval(function () {
      window.MesaTI.peticion('/api/notificaciones/contador')
        .then(function (d) { window.MesaTI.actualizarCampana(d.no_leidas); })
        .catch(function () { /* sin conexión: se intenta en el siguiente ciclo */ });
    }, 60000);
  }

  /* ---------- Marcar notificaciones como leídas sin recargar ---------- */
  document.querySelectorAll('form[data-ajax]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const boton = form.querySelector('button');
      if (boton) boton.disabled = true;
      window.MesaTI.peticion(form.dataset.api, { method: 'PUT' })
        .then(function (d) {
          if (form.dataset.ajax === 'marcar-todas') {
            document.querySelectorAll('.notif.is-unread').forEach(marcarFila);
            window.MesaTI.toast('Todas las notificaciones quedaron como leídas.');
          } else {
            marcarFila(form.closest('.notif'));
          }
          window.MesaTI.actualizarCampana(d.no_leidas);
          const resumen = document.getElementById('resumen-notif');
          if (resumen) resumen.textContent = d.no_leidas === 0 ? 'Estás al día' : d.no_leidas === 1 ? '1 sin leer' : d.no_leidas + ' sin leer';
        })
        .catch(function () { form.submit(); }); // si falla el AJAX, se usa el formulario normal
    });
  });

  function marcarFila(fila) {
    if (!fila) return;
    fila.classList.remove('is-unread');
    const form = fila.querySelector('form[data-ajax]');
    if (form) {
      const leida = document.createElement('span');
      leida.className = 'notif__read';
      leida.textContent = 'Leída';
      form.replaceWith(leida);
    }
  }

  /* ---------- Visor de fotos del detalle ---------- */
  const visorImg = document.getElementById('visor-img');
  document.querySelectorAll('[data-foto]').forEach(function (b) {
    b.addEventListener('click', function () {
      visorImg.src = b.dataset.foto;
      visorImg.alt = b.dataset.alt;
      document.getElementById('visor').href = b.dataset.foto;
      document.querySelectorAll('[data-foto]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
    });
  });

  /* ---------- Cuentas de prueba en el login ---------- */
  document.querySelectorAll('[data-demo-correo]').forEach(function (b) {
    b.addEventListener('click', function () {
      document.getElementById('correo').value = b.dataset.demoCorreo;
      document.getElementById('clave').value = 'demo1234';
      document.querySelector('form button[type="submit"]').focus();
    });
  });

  /* ---------- Enlaces aún no disponibles ---------- */
  document.querySelectorAll('[data-pronto]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      window.MesaTI.toast(a.dataset.pronto + ' estará disponible pronto.');
    });
  });
})();
