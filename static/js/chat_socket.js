document.addEventListener('DOMContentLoaded', () => {
	const idTicket = new URLSearchParams(window.location.search).get('id');
	const replyForm = document.getElementById('reply-form');
	const inputComentario = document.getElementById('reply-text');
	if (!idTicket || !replyForm) return;

	fetch('/api/tickets/sesion', {
		headers: typeof obtenerHeadersAuth === 'function' ? obtenerHeadersAuth() : {}
	})
		.then((r) => r.json())
		.then((data) => {
			if (data.usuario && data.usuario.nombre) {
				const iniciales = data.usuario.nombre
					.split(/\s+/)
					.slice(0, 2)
					.map((p) => p[0])
					.join('')
					.toUpperCase();
				const avatarSpan = document.querySelector('.reply-form .comment-avatar');
				if (avatarSpan) avatarSpan.textContent = iniciales;
			}
		})
		.catch(() => {});

	const typingDiv = document.createElement('div');
	typingDiv.style.padding = '5px 15px';
	typingDiv.style.marginBottom = '12px';
	typingDiv.style.color = '#58749a';
	typingDiv.style.fontSize = '13.5px';
	typingDiv.style.display = 'none';
	replyForm.parentElement.insertBefore(typingDiv, replyForm);

	let typingTimeout = null;
	let ultimoEnvio = 0;

	function animarEscribiendo(usuario) {
		typingDiv.innerHTML = `✍️ <b>${usuario}</b> está escribiendo<span class="animated-dots"></span>`;
		typingDiv.style.display = 'block';
		clearTimeout(typingTimeout);
		typingTimeout = setTimeout(() => {
			typingDiv.style.display = 'none';
		}, 2800);
	}

	const evtSource = new EventSource(`/api/tickets/${idTicket}/stream`);

	evtSource.addEventListener('usuario_escribiendo', (e) => {
		try {
			const data = JSON.parse(e.data);
			animarEscribiendo(data.usuario);
		} catch (err) {}
	});

	evtSource.addEventListener('nuevo_comentario', () => {
		typingDiv.style.display = 'none';
		if (typeof cargarHistorial === 'function') cargarHistorial(idTicket);
	});

	evtSource.onerror = () => {
		console.log('Reconectando EventSource...');
	};

	if (inputComentario) {
		inputComentario.addEventListener('input', () => {
			if (!inputComentario.value.trim()) return;
			const ahora = Date.now();
			if (ahora - ultimoEnvio < 1500) return;
			ultimoEnvio = ahora;

			fetch(`/api/tickets/${idTicket}/escribiendo`, {
				method: 'POST',
				headers: typeof obtenerHeadersAuth === 'function' ? obtenerHeadersAuth() : {}
			}).catch(() => {});
		});
	}
});
