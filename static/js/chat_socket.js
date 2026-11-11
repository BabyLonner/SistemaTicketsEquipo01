document.addEventListener('DOMContentLoaded', () => {
    const idTicket = new URLSearchParams(window.location.search).get('id');
    const replyForm = document.getElementById('reply-form');
    const inputComentario = document.getElementById('reply-text');
    if (!idTicket || !replyForm) return;

    let miNombre = "Usuario";

    fetch('/api/tickets/sesion', { headers: typeof obtenerHeadersAuth === 'function' ? obtenerHeadersAuth() : {} })
        .then(r => r.json())
        .then(data => {
            if (data.usuario && data.usuario.nombre) {
                miNombre = data.usuario.nombre;
                const iniciales = miNombre.split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase();
                const avatarSpan = document.querySelector('.reply-form .comment-avatar');
                if (avatarSpan) avatarSpan.textContent = iniciales;
            }
        }).catch(() => {});

    const typingDiv = document.createElement('div');
    typingDiv.style.padding = '5px 15px';
    typingDiv.style.marginBottom = '12px';
    typingDiv.style.color = '#3479d9';
    typingDiv.style.fontSize = '13.5px';
    typingDiv.style.display = 'none';
    typingDiv.style.fontWeight = '500';
    replyForm.parentElement.insertBefore(typingDiv, replyForm);

    let typingTimeout = null;
    let ultimoHistorial = 0;
    let ultimoEnvio = 0;

    function animarEscribiendo(usuario) {
        typingDiv.innerHTML = `✍️ <b>${usuario}</b> está escribiendo...`;
        typingDiv.style.display = 'block';
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            typingDiv.style.display = 'none';
        }, 2000);
    }

    if (inputComentario) {
        inputComentario.addEventListener('input', () => {
            if (inputComentario.value.trim().length > 0) {
                localStorage.setItem(`escribiendo_${idTicket}`, JSON.stringify({
                    user: miNombre,
                    time: Date.now()
                }));

                const ahora = Date.now();
                if (ahora - ultimoEnvio > 800) {
                    ultimoEnvio = ahora;
                    fetch(`/api/tickets/${idTicket}/escribiendo`, {
                        method: 'POST',
                        headers: typeof obtenerHeadersAuth === 'function' ? obtenerHeadersAuth() : {}
                    }).catch(() => {});
                }
            }
        });
    }

    let consultandoEstado = false;
    setInterval(() => {
        if (document.hidden) return;

        try {
            const typingData = JSON.parse(localStorage.getItem(`escribiendo_${idTicket}`));
            if (typingData && typingData.user !== miNombre && (Date.now() - typingData.time) < 2000) {
                animarEscribiendo(typingData.user);
            }
        } catch(e) {}

        if (consultandoEstado) return;
        consultandoEstado = true;

        fetch(`/api/tickets/${idTicket}/estado-chat`, {
            headers: typeof obtenerHeadersAuth === 'function' ? obtenerHeadersAuth() : {}
        })
        .then(r => r.json())
        .then(data => {
            if (data.escribiendo && data.escribiendo.length > 0) {
                const nombres = data.escribiendo.map((u) => u.usuario).join(', ');
                animarEscribiendo(nombres);
            }
            if (data.ultimo_comentario_ts) {
                if (ultimoHistorial === 0) {
                    ultimoHistorial = data.ultimo_comentario_ts;
                } else if (data.ultimo_comentario_ts > ultimoHistorial) {
                    ultimoHistorial = data.ultimo_comentario_ts;
                    typingDiv.style.display = 'none';
                    if (typeof cargarHistorial === 'function') cargarHistorial(idTicket);
                }
            }
        })
        .catch(() => {})
        .finally(() => { consultandoEstado = false; });

    }, 800);
});