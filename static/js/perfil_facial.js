/* =========================================================
   perfil_facial.js — registrar / eliminar el rostro (Mi Perfil)
   Envía al servidor 3 descriptores; el servidor verifica que sean
   de la misma persona y guarda su promedio.
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
    const panel = document.getElementById('panel-rostro');
    if (!panel) return;
    const estadoPanel = document.getElementById('estado-rostro');
    const btnRegistrar = document.getElementById('btn-registrar-rostro');
    const btnEliminar = document.getElementById('btn-eliminar-rostro');
    const modal = document.getElementById('modal-registro-rostro');
    const video = document.getElementById('registro-video');
    const estado = document.getElementById('registro-estado');
    const guia = document.getElementById('registro-guia');
    const clave = document.getElementById('registro-clave');
    const comenzar = document.getElementById('registro-comenzar');
    const pasos = [...modal.querySelectorAll('.facial-pasos i')];
    let enCurso = false;

    const json = (r) => r.json().catch(() => ({}));

    function mostrar(texto, tipo = '') {
        estado.textContent = texto;
        estado.className = 'facial-estado' + (tipo ? ' ' + tipo : '');
        guia.className = 'facial-guia' + (tipo === 'ok' ? ' ok' : tipo === 'error' ? ' error' : '');
    }

    async function actualizarEstado() {
        const datos = await json(await fetch('/api/rostro', { credentials: 'same-origin' }));
        if (datos.registrado) {
            estadoPanel.innerHTML = `<span class="status-badge active"><i></i>Registrado</span> Actualizado el ${datos.actualizado}`;
            btnRegistrar.innerHTML = '<span>↻</span>Volver a registrar';
            btnEliminar.hidden = false;
        } else {
            estadoPanel.innerHTML = '<span class="status-badge inactive"><i></i>Sin registrar</span> Solo puedes ingresar con contraseña';
            btnRegistrar.innerHTML = '<span>＋</span>Registrar mi rostro';
            btnEliminar.hidden = true;
        }
    }

    function cerrar() {
        Rostro.apagarCamara(video);
        modal.hidden = true;
        enCurso = false;
    }

    btnRegistrar.addEventListener('click', () => {
        pasos.forEach((p) => p.classList.remove('hecho'));
        clave.value = '';
        comenzar.disabled = false;
        mostrar('Escribe tu contraseña y pulsa «Comenzar».');
        modal.hidden = false;
        clave.focus();
    });

    comenzar.addEventListener('click', async () => {
        if (enCurso) return;
        if (!clave.value) { mostrar('Escribe tu contraseña actual.', 'error'); clave.focus(); return; }
        enCurso = true;
        comenzar.disabled = true;
        pasos.forEach((p) => p.classList.remove('hecho'));
        try {
            mostrar('Cargando el modelo de reconocimiento…');
            await Rostro.cargarModelos();
            if (!video.srcObject) {
                mostrar('Encendiendo la cámara…');
                await Rostro.encenderCamara(video);
            }
            const descriptores = await Rostro.capturarMuestras(video, 3, (hechas, texto, bien) => {
                pasos.forEach((p, i) => p.classList.toggle('hecho', i < hechas));
                mostrar(texto, bien ? 'ok' : '');
            });
            mostrar('Guardando…', 'ok');
            const res = await fetch('/api/rostro', {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clave: clave.value, descriptores }),
            });
            const datos = await json(res);
            if (!res.ok) { mostrar(datos.error || 'No se pudo registrar.', 'error'); comenzar.disabled = false; return; }
            mostrar(datos.mensaje, 'ok');
            Rostro.apagarCamara(video);
            await actualizarEstado();
            setTimeout(cerrar, 1600);
        } catch (e) {
            mostrar(e.message || 'Ocurrió un error con la cámara.', 'error');
            comenzar.disabled = false;
        } finally {
            enCurso = false;
        }
    });

    btnEliminar.addEventListener('click', async () => {
        if (!confirm('¿Eliminar tu rostro registrado? Solo podrás ingresar con tu contraseña.')) return;
        const datos = await json(await fetch('/api/rostro', { method: 'DELETE', credentials: 'same-origin' }));
        alert(datos.mensaje || datos.error);
        actualizarEstado();
    });

    document.getElementById('registro-cancelar').addEventListener('click', cerrar);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) cerrar(); });
    actualizarEstado();
});
