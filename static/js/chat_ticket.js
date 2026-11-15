const INTERVALO_CHAT_MS = 1000;
const INTERVALO_ESCRIBIENDO_MS = 1000;
const MIN_COMENTARIO_CHAT = 2;
const CLASE_AVATAR_CHAT = { Solicitante: 'avatar-requester', Técnico: 'avatar-tech' };

const chat = {
	ticketId: null,
	permitido: false,
	escribir: false,
	ultimoComentario: null,
	consultando: false,
	temporizador: null,
	ultimoAvisoEscribiendo: 0
};

document.addEventListener('ticket:cargado', (e) => configurarChat(e.detail));

function configurarChat(ticket) {
	const primeraVez = chat.ticketId === null;
	chat.ticketId = ticket.id;
	chat.permitido = Boolean(ticket.permisos?.ver_chat);
	chat.escribir = Boolean(ticket.permisos?.escribir_chat);

	actualizarFormularioChat(ticket);
	if (primeraVez) registrarEventosChat();

	if (chat.permitido && ticket.estado !== 'Cerrado') iniciarConsultaChat();
	else detenerConsultaChat();
}

function actualizarFormularioChat(ticket) {
	const form = document.getElementById('reply-form');
	const aviso = document.getElementById('chat-aviso');
	if (form) form.hidden = !chat.escribir;
	if (!aviso) return;
	if (!chat.permitido) {
		aviso.textContent =
			'La conversación es solo del solicitante, el técnico asignado y el administrador.';
	} else if (ticket.estado === 'Cerrado') {
		aviso.textContent = 'El ticket está cerrado y ya no admite mensajes.';
	} else {
		aviso.textContent = '';
	}
	aviso.hidden = !aviso.textContent;
}

function registrarEventosChat() {
	const form = document.getElementById('reply-form');
	const input = document.getElementById('reply-text');
	if (!form || !input) return;

	input.addEventListener('input', () => {
		if (input.value.trim()) avisarEscribiendo();
	});
	form.addEventListener('submit', (e) => {
		e.preventDefault();
		enviarMensajeChat(form, input);
	});
	document.querySelector('[data-action="reply"]')?.addEventListener('click', () => {
		document.querySelector('.tab[data-tab="conversation"]')?.click();
		input.scrollIntoView({ behavior: 'smooth', block: 'center' });
		input.focus();
	});
	document.addEventListener('visibilitychange', () => {
		if (!document.hidden) revisarChat();
	});
}

function iniciarConsultaChat() {
	if (chat.temporizador) return;
	revisarChat();
	chat.temporizador = setInterval(revisarChat, INTERVALO_CHAT_MS);
}

function detenerConsultaChat() {
	clearInterval(chat.temporizador);
	chat.temporizador = null;
	mostrarEscribiendo([]);
}

async function revisarChat() {
	if (document.hidden || chat.consultando || !chat.permitido || chat.ultimoComentario === null)
		return;
	chat.consultando = true;
	try {
		const res = await fetch(`/api/tickets/${chat.ticketId}/estado-chat`);
		if (!res.ok) return;
		const estado = await res.json();
		if (estado.ultimo_comentario !== chat.ultimoComentario) {
			mostrarEscribiendo([]);
			await cargarHistorial(chat.ticketId);
		} else {
			mostrarEscribiendo(estado.escribiendo || []);
		}
	} catch (error) {
		console.error('No se pudo consultar el chat', error);
	} finally {
		chat.consultando = false;
	}
}

function avisarEscribiendo() {
	const ahora = Date.now();
	if (ahora - chat.ultimoAvisoEscribiendo < INTERVALO_ESCRIBIENDO_MS) return;
	chat.ultimoAvisoEscribiendo = ahora;
	fetch(`/api/tickets/${chat.ticketId}/escribiendo`, { method: 'POST' }).catch(() => {});
}

async function enviarMensajeChat(form, input) {
	const comentario = input.value.trim();
	if (comentario.length < MIN_COMENTARIO_CHAT) {
		mostrarToast('Escribe un mensaje.');
		input.focus();
		return;
	}
	const boton = form.querySelector('button[type="submit"]');
	if (boton) boton.disabled = true;
	try {
		const res = await fetch(`/api/tickets/${chat.ticketId}/comentarios`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ comentario })
		});
		const datos = await res.json().catch(() => ({}));
		if (!res.ok) {
			mostrarToast(datos.error || 'No se pudo enviar el mensaje.');
			return;
		}
		input.value = '';
		chat.ultimoAvisoEscribiendo = 0;
		fetch(`/api/tickets/${chat.ticketId}/escribiendo`, { method: 'DELETE' }).catch(() => {});
		await cargarHistorial(chat.ticketId);
	} catch (error) {
		mostrarToast('No se pudo conectar con el servidor.');
	} finally {
		if (boton) boton.disabled = false;
	}
}

function mostrarEscribiendo(nombres) {
	const indicador = document.getElementById('chat-escribiendo');
	if (!indicador) return;
	indicador.hidden = nombres.length === 0;
	indicador.textContent =
		nombres.length === 1
			? `${nombres[0]} está escribiendo`
			: `${nombres.join(', ')} están escribiendo`;
}

function renderizarChat(historial) {
	const contenedor = document.getElementById('contenedor-chat');
	if (!contenedor) return;
	if (!chat.permitido) {
		contenedor.innerHTML = '';
		return;
	}
	const mensajes = historial.filter((h) => h.tipo === 'COMENTARIO' || h.tipo === 'CREACION');
	chat.ultimoComentario = mensajes.reduce(
		(max, h) => (h.tipo === 'COMENTARIO' ? Math.max(max, h.id) : max),
		0
	);
	contenedor.innerHTML = mensajes.length
		? mensajes.map(mensajeChatHTML).join('')
		: '<p class="chat-vacio">Todavía no hay mensajes en la conversación.</p>';
}

function mensajeChatHTML(m) {
	const claseAvatar = CLASE_AVATAR_CHAT[m.usuario_rol] || 'avatar-admin';
	return `
        <article class="comment">
            <span class="comment-avatar ${claseAvatar}">${escaparHTML(iniciales(m.usuario))}</span>
            <div class="comment-body">
                <div class="comment-meta">
                    <strong>${escaparHTML(m.usuario)} <small>${escaparHTML(m.usuario_rol)}</small></strong>
                    <time datetime="${escaparHTML(m.created_at)}">${formatearFecha(m.created_at)}</time>
                </div>
                <p>${escaparHTML(m.comentario)}</p>
            </div>
        </article>`;
}
