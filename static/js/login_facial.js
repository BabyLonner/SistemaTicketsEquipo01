/* =========================================================
   login_facial.js — "Ingresar con reconocimiento facial"
   1) pide el correo  2) verifica que la cuenta tenga rostro registrado  3) cámara  3) envía SOLO el descriptor
   4) el servidor compara con la distancia euclidiana y crea la sesión (JWT)
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
    const boton = document.getElementById('btn-facial');
    const modal = document.getElementById('modal-facial');
    if (!boton || !modal) return;
    const video = document.getElementById('facial-video');
    const estado = document.getElementById('facial-estado');
    const guia = document.getElementById('facial-guia');
    const reintentar = document.getElementById('facial-reintentar');
    const correo = document.getElementById('correo');
    let enCurso = false;

    function mostrar(texto, tipo = '') {
        estado.textContent = texto;
        estado.className = 'facial-estado' + (tipo ? ' ' + tipo : '');
        guia.className = 'facial-guia' + (tipo === 'ok' ? ' ok' : tipo === 'error' ? ' error' : '');
    }

    function errorCorreo(texto) {
        const p = document.getElementById('error-correo');
        if (p) p.textContent = texto;
        correo.focus();
    }

    function cerrar() {
        Rostro.apagarCamara(video);
        modal.hidden = true;
        enCurso = false;
    }

    async function intentar() {
        if (enCurso) return;
        enCurso = true;
        reintentar.hidden = true;
        try {
            mostrar('Cargando el modelo de reconocimiento…');
            await Rostro.cargarModelos();
            if (!video.srcObject) {
                mostrar('Encendiendo la cámara…');
                await Rostro.encenderCamara(video);
            }
            mostrar('Mira de frente a la cámara…');
            const descriptor = await Rostro.capturarRostro(video, (texto, bien) => mostrar(texto, bien ? 'ok' : ''));
            mostrar('Verificando tu identidad…', 'ok');
            const res = await fetch('/api/login-facial', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    correo: correo.value.trim(),
                    descriptor,
                    recordar: document.getElementById('recordar')?.checked || false,
                }),
            });
            const datos = await res.json().catch(() => ({}));
            if (res.ok && datos.ok) {
                mostrar(`${datos.mensaje} Ingresando…`, 'ok');
                Rostro.apagarCamara(video);
                window.location.href = datos.redirigir || '/';
                return;
            }
            mostrar(datos.error || 'No se pudo verificar tu rostro.', 'error');
            reintentar.hidden = Boolean(datos.bloqueado || datos.sin_registro);
            if (datos.bloqueado || datos.sin_registro) Rostro.apagarCamara(video);
        } catch (e) {
            mostrar(e.message || 'Ocurrió un error con la cámara.', 'error');
            reintentar.hidden = false;
        } finally {
            enCurso = false;
        }
    }

    boton.addEventListener('click', async () => {
        const valor = (correo.value || '').trim();
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(valor)) {
            errorCorreo('Escribe tu correo corporativo y luego elige el reconocimiento facial.');
            return;
        }
        errorCorreo('');
        // Antes de encender la cámara: ¿esta cuenta tiene un rostro registrado? ¿está bloqueada?
        try {
            const res = await fetch('/api/login-facial/estado?correo=' + encodeURIComponent(valor), { credentials: 'same-origin' });
            const estadoCuenta = await res.json();
            if (!estadoCuenta.registrado) {
                errorCorreo('Esta cuenta no tiene un rostro registrado. Ingresa con tu contraseña y regístralo en Mi Perfil.');
                return;
            }
            if (estadoCuenta.bloqueado) {
                errorCorreo(estadoCuenta.mensaje);
                return;
            }
        } catch (e) {
            errorCorreo('No se pudo conectar con el servidor.');
            return;
        }
        modal.hidden = false;
        intentar();
    });
    reintentar.addEventListener('click', intentar);
    document.getElementById('facial-cancelar').addEventListener('click', cerrar);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) cerrar(); });
});
