/* Casillas para adjuntar hasta 3 fotos con vista previa.
   Sin JavaScript, el formulario usa el campo de archivos normal. */
(function () {
  'use strict';
  const input = document.getElementById('fotos');
  const casillas = document.getElementById('fotos-casillas');
  const contador = document.getElementById('fotos-contador');
  if (!input || !casillas || typeof DataTransfer === 'undefined') return;

  const MAX = Number(input.dataset.max) || 3;
  const TIPOS = ['image/jpeg', 'image/png'];
  const MAX_BYTES = 5 * 1024 * 1024;
  let archivos = [];

  // Se oculta el campo nativo y se muestran las casillas
  input.classList.add('visually-hidden');
  casillas.classList.remove('d-none');

  function sincronizar() {
    const dt = new DataTransfer();
    archivos.forEach(function (a) { dt.items.add(a.file); });
    input.files = dt.files;
  }

  function pintar() {
    casillas.innerHTML = '';
    archivos.forEach(function (a, i) {
      const col = document.createElement('div');
      col.className = 'col-md-4';
      col.innerHTML = '<div class="foto-casilla"><img alt=""><span class="foto-casilla__nombre"></span>' +
        '<button type="button" class="foto-casilla__quitar"><i class="bi bi-x-lg" aria-hidden="true"></i></button></div>';
      col.querySelector('img').src = a.url;
      col.querySelector('img').alt = 'Foto ' + (i + 1) + ': ' + a.file.name;
      col.querySelector('.foto-casilla__nombre').textContent = a.file.name;
      const quitar = col.querySelector('button');
      quitar.setAttribute('aria-label', 'Quitar ' + a.file.name);
      quitar.addEventListener('click', function () {
        URL.revokeObjectURL(a.url);
        archivos.splice(i, 1);
        sincronizar();
        pintar();
      });
      casillas.appendChild(col);
    });
    for (let i = archivos.length; i < MAX; i++) {
      const col = document.createElement('div');
      col.className = 'col-md-4';
      col.innerHTML = '<button type="button" class="foto-agregar"><i class="bi bi-upload" aria-hidden="true"></i>Agregar foto</button>';
      col.querySelector('button').addEventListener('click', function () { selector.click(); });
      casillas.appendChild(col);
    }
    contador.textContent = archivos.length + ' de ' + MAX + ' · solo imágenes JPG o PNG';
  }

  // Selector auxiliar: el campo real solo guarda la lista final
  const selector = document.createElement('input');
  selector.type = 'file';
  selector.accept = 'image/jpeg,image/png';
  selector.multiple = true;
  selector.hidden = true;
  casillas.after(selector);

  selector.addEventListener('change', function () {
    Array.from(selector.files).forEach(function (file) {
      if (archivos.length >= MAX) {
        window.MesaTI.toast('Solo puedes adjuntar hasta ' + MAX + ' fotos.', 'error');
        return;
      }
      if (TIPOS.indexOf(file.type) === -1) {
        window.MesaTI.toast('"' + file.name + '" no es una imagen JPG o PNG.', 'error');
        return;
      }
      if (file.size > MAX_BYTES) {
        window.MesaTI.toast('"' + file.name + '" pesa más de 5 MB.', 'error');
        return;
      }
      archivos.push({ file: file, url: URL.createObjectURL(file) });
    });
    selector.value = '';
    sincronizar();
    pintar();
  });

  pintar();
})();
