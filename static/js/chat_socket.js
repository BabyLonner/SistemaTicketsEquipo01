/* =========================================================
   MÓDULO 5 — Cliente WebSocket (Socket.IO) para detalle_ticket
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const idTicket = new URLSearchParams(window.location.search).get('id');
	const chatContainer = document.getElementById('contenedor-chat');
	const inputComentario = document.getElementById('reply-text');
	if (!idTicket || !chatContainer || typeof io === 'undefined') return;

	const socket = io({ transports: ['websocket', 'polling'] });

	// Indicador visual de conexión y de "escribiendo..."
	const barraEstado = document.createElement('div');
	barraEstado.className = 'chat-live-bar';
	barraEstado.innerHTML = `
        <span class="live-dot"></span>
        <span class="live-text">Chat en tiempo real activo</span>
        <span id="typing-indicator" class="typing-indicator" hidden></span>
    `;
	chatContainer.parentElement.insertBefore(barraEstado, chatContainer);

	socket.on('connect', () => {
		socket.emit('unirse_ticket', { ticket_id: idTicket });
	});

	// Emitir evento cuando el usuario escribe
	let typingTimeout = null;
	if (inputComentario) {
		inputComentario.addEventListener('input', () => {
			socket.emit('escribiendo_ticket', { ticket_id: idTicket });
		});
	}

	// Mostrar cuando otro usuario está escribiendo
	socket.on('usuario_escribiendo', (data) => {
		const indicator = document.getElementById('typing-indicator');
		if (!indicator) return;
		indicator.textContent = `✍️ ${data.usuario} está escribiendo...`;
		indicator.hidden = false;
		clearTimeout(typingTimeout);
		typingTimeout = setTimeout(() => {
			indicator.hidden = true;
		}, 2200);
	});

	// Recibir nuevo comentario en vivo sin recargar toda la página
	socket.on('nuevo_comentario', (m) => {
		if (String(m.ticket_id) !== String(idTicket)) return;
		if (typeof cargarHistorial === 'function') {
			cargarHistorial(idTicket);
		}
	});

	window.addEventListener('beforeunload', () => {
		socket.emit('salir_ticket', { ticket_id: idTicket });
	});
});
