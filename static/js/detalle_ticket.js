/* =========================================================
   detalle_ticket.js — Lógica conectada a la API real
   ========================================================= */

document.addEventListener('DOMContentLoaded', () => {
	const idTicket = new URLSearchParams(window.location.search).get('id');
	cargarDetalleTicket(idTicket);
	configurarEventosPanelDerecho(idTicket);
});

function formatearFecha(isoStr) {
	if (!isoStr) return '—';
	const d = new Date(isoStr);
	return isNaN(d)
		? '—'
		: d.toLocaleString('es-PE', {
				day: '2-digit',
				month: '2-digit',
				year: 'numeric',
				hour: '2-digit',
				minute: '2-digit'
			});
}

function iniciales(nombre) {
	return (nombre || 'US')
		.split(/\s+/)
		.slice(0, 2)
		.map((p) => p[0])
		.join('')
		.toUpperCase();
}

function mostrarToast(msg) {
	const toast = document.getElementById('toast');
	if (!toast) return;
	toast.textContent = msg;
	toast.classList.add('show');
	setTimeout(() => toast.classList.remove('show'), 3000);
}

const CLASE_PRIORIDAD_DET = {
	Alta: 'priority-high',
	Media: 'priority-medium',
	Baja: 'priority-low'
};
const CLASE_ESTADO_DET = {
	Abierto: 'status-open',
	'En proceso': 'status-progress',
	Resuelto: 'status-resolved',
	Cerrado: 'status-closed'
};

/* =========================================================================
   CARGAR DATOS DESDE LA API
   ========================================================================= */
async function cargarDetalleTicket(id) {
	try {
		const res = await fetch(`/api/tickets/${id}`);
		if (!res.ok) {
			document.getElementById('ticket-subject').textContent = 'Error al cargar el ticket';
			return;
		}

		const data = await res.json();
		const t = data.ticket;
		if (!t) return;

        document.getElementById('breadcrumb-code').textContent = t.codigo;
        document.getElementById('ticket-code').textContent = t.codigo;
        document.getElementById('ticket-subject').textContent = t.asunto;

		document.getElementById('ticket-priority-tag').className =
			`badge ${CLASE_PRIORIDAD_DET[t.prioridad] || ''}`;
        document.getElementById('ticket-priority-tag').textContent = `▥ ${t.prioridad}`;

		document.getElementById('ticket-status-tag').className =
			`badge ${CLASE_ESTADO_DET[t.estado] || ''}`;
        document.getElementById('ticket-status-tag').textContent = `▤ ${t.estado}`;

		const tagCategoria = document.querySelectorAll('.ticket-tags .category-tag')[0];
		const tagEmpresa = document.querySelectorAll('.ticket-tags .category-tag')[1];
        if (tagCategoria) tagCategoria.textContent = `◉ ${t.categoria}`;
        if (tagEmpresa) tagEmpresa.textContent = `▦ ${t.empresa}`;

		calcularSlaDetalleTicket(t);

        document.getElementById('ticket-description').textContent = t.descripcion;

		const metadataItems = document.querySelectorAll('.metadata-item strong');
		if (metadataItems.length >= 4) {
            metadataItems[0].textContent = t.solicitante;
            metadataItems[1].textContent = t.area;
            metadataItems[2].textContent = t.empresa;
			metadataItems[3].textContent = formatearFecha(t.created_at);
		}

		const selEstado = document.getElementById('property-status');
		const selPrio = document.getElementById('property-priority');
		const selCat = document.getElementById('property-category');
		const selTec = document.getElementById('property-technician');

		if (selEstado) selEstado.value = t.estado;
		if (selPrio) selPrio.value = t.prioridad;
		if (selCat && [...selCat.options].some((o) => o.value === t.categoria))
			selCat.value = t.categoria;

		if (selTec) {
			const tecValue = t.tecnico || 'Sin asignar';
			if (![...selTec.options].some((o) => o.value === tecValue)) {
				selTec.add(new Option(tecValue, tecValue));
			}
			selTec.value = tecValue;
		}

		ticketDetalleActual = {
			id: t.id,
			codigo: t.codigo,
			estado: t.estado,
			tecnico: t.tecnico || null
		};
		cargarTecnicosDetalle(t.tecnico);
		document.dispatchEvent(new CustomEvent('ticket:cargado', { detail: t }));

		const contenedorEvidencias = document.getElementById('contenedor-evidencias');
		if (contenedorEvidencias) {
			contenedorEvidencias.innerHTML = ''; // Limpiamos los datos de prueba
			if (t.evidencias && t.evidencias.length > 0) {
				t.evidencias.forEach((foto) => {
					contenedorEvidencias.innerHTML += `
                        <div class="evidencia-item" style="display:inline-block; margin-right:10px; border: 1px solid #ccc; padding: 5px; border-radius: 5px;">
                            <a href="${foto.imagen_url}" target="_blank">
                                <img src="${foto.miniatura_url}" alt="${escaparHTML(foto.nombre)}" style="max-height: 120px; object-fit: cover;">
                            </a>
                            <p style="font-size: 11px; text-align: center; margin: 5px 0 0 0;">${escaparHTML(foto.nombre)}</p>
                        </div>
                    `;
				});
			} else {
				contenedorEvidencias.innerHTML =
					'<p class="text-muted">No se adjuntaron fotos en este ticket.</p>';
			}
		}

		renderizarArchivos(t.evidencias || []);

		// --- NUEVO 6: OBTENER HISTORIAL Y CONVERSACIÓN ---
		cargarHistorial(id);

		document.getElementById('page-message').textContent =
			`Conectado a la base de datos · Ticket cargado correctamente.`;
	} catch (e) {
		console.error('Error al obtener detalle del ticket:', e);
		mostrarToast('No se pudo conectar con el servidor.');
	}
}

// MÓDULO 4: el servidor calcula el SLA en Python (semáforo, minutos y % del plazo);
// aquí solo se pinta el recuadro "SLA y tiempos".
function calcularSlaDetalleTicket(t) {
	const duracion = (min) => {
		min = Math.max(0, Math.round(min || 0));
		const d = Math.floor(min / 1440),
			h = Math.floor((min % 1440) / 60),
			m = min % 60;
		if (d) return `${d} d ${h} h`;
		if (h) return `${h} h ${m} min`;
		return `${m} min`;
	};
	const textos = {
		verde: ['En tiempo', `Quedan ${duracion(t.minutos_restantes)}`],
		amarillo: ['Por vencer', `Quedan ${duracion(t.minutos_restantes)}`],
		rojo: ['Plazo vencido', `Venció hace ${duracion(-(t.minutos_restantes || 0))}`],
		cumplido: ['Cumplido', 'Se resolvió dentro del plazo'],
		incumplido: ['Fuera de plazo', 'Se resolvió después del plazo']
	};
	const [titulo, detalle] = textos[t.semaforo] || ['Sin datos', ''];
	const caja = document.querySelector('.sla-warning-box');
	const tituloEl = document.getElementById('sla-title');
	if (tituloEl) {
		tituloEl.textContent = titulo;
		const small = tituloEl.parentElement.querySelector('small');
		if (small) small.textContent = detalle;
	}
	if (caja) {
		const colores = {
			verde: ['#e8f7ef', '#12805c'],
			cumplido: ['#e8f7ef', '#12805c'],
			amarillo: ['#fff6e0', '#9a6700'],
			rojo: ['#fdecec', '#b42318'],
			incumplido: ['#fdecec', '#b42318']
		};
		const [fondo, color] = colores[t.semaforo] || ['#eef3fa', '#24466b'];
		caja.style.background = fondo;
		caja.style.color = color;
		const icono = caja.querySelector('span');
		if (icono) {
			icono.textContent = ['verde', 'cumplido'].includes(t.semaforo) ? '✓' : '!';
			icono.style.background = color;
		}
	}
	const transcurrido = document.querySelector('.sla-stats .time-danger span');
	if (transcurrido) transcurrido.textContent = duracion(t.minutos_transcurridos);
	const limite = document.getElementById('sla-limit');
	if (limite) limite.textContent = `${t.sla_horas} h · ${formatearFecha(t.fecha_limite)}`;
	const nota = document.getElementById('sla-note');
	if (nota) nota.textContent = `Prioridad ${t.prioridad}: máximo ${t.sla_horas} h para resolverlo.`;
	const pct = Math.min(100, Math.round(t.porcentaje_sla || 0));
	const barra = document.getElementById('sla-progress-bar');
	if (barra) {
		barra.style.width = `${pct}%`;
		barra.style.background =
			{ verde: '#14b88a', cumplido: '#14b88a', amarillo: '#f0a500' }[t.semaforo] || '#f04452';
	}
	const porcentaje = document.getElementById('sla-percent');
	if (porcentaje) porcentaje.textContent = `${pct}%`;
}

/* =========================================================================
   NUEVO: CARGAR HISTORIAL (Línea de Tiempo y Chat)
   ========================================================================= */
async function cargarHistorial(ticketId) {
	try {
		const res = await fetch(`/api/tickets/${ticketId}/historial`);
		if (res.ok) {
			const data = await res.json();
			renderizarHistorial(data.historial || []);
			renderizarChat(data.historial || []);
		}
	} catch (e) {
		console.error('Error al cargar historial y comentarios', e);
	}
}

function renderizarHistorial(historialArray) {
	/* MÓDULO 3: línea de tiempo del ticket (tabla ticket_historial) */
	const list = document.getElementById('history-timeline');
	const counter = document.getElementById('history-count');
	const tabCounter = document.getElementById('history-tab-count');

	if (!list) return;
	if (counter) counter.textContent = `${historialArray.length} movimientos`;
	if (tabCounter) tabCounter.textContent = historialArray.length;

	if (historialArray.length === 0) {
		list.innerHTML = `<li>No hay movimientos registrados.</li>`;
		return;
	}

	list.innerHTML = [...historialArray]
		.reverse()
		.map((h) => {
			let iconoStr = '●';
			let claseColor = '';
			let accion = h.tipo;

			// Traducir el TIPO de MySQL a un texto amigable
			if (h.tipo === 'CREACION') {
				iconoStr = '＋';
				claseColor = 't-open';
				accion = 'Ticket creado · estado inicial Abierto';
			} else if (h.tipo === 'CAMBIO_ESTADO') {
				iconoStr =
					{ 'En proceso': '⟳', Resuelto: '✓', Cerrado: '■', Abierto: '!' }[h.estado_nuevo] || '⟳';
				claseColor =
					{
						'En proceso': 't-progress',
						Resuelto: 't-resolved',
						Cerrado: 't-closed',
						Abierto: 't-open'
					}[h.estado_nuevo] || 't-progress';
				accion =
					h.estado_anterior === 'Resuelto' && h.estado_nuevo === 'En proceso'
						? 'Ticket reabierto · Resuelto → En proceso'
						: `Estado: ${h.estado_anterior} → ${h.estado_nuevo}`;
			} else if (h.tipo === 'ASIGNACION') {
				iconoStr = '♙';
				claseColor = 't-assign';
				accion = h.tecnico_anterior
					? `Reasignado de ${h.tecnico_anterior} a ${h.tecnico_nuevo}`
					: `Asignado a ${h.tecnico_nuevo || 'Sin asignar'}`;
			} else if (h.tipo === 'COMENTARIO') {
				iconoStr = '💬';
				claseColor = 't-resolved';
				accion = 'Nuevo comentario';
			}

			const fechaFormat = formatearFecha(h.created_at);
			const rol = h.usuario_rol ? ` (${escaparHTML(h.usuario_rol)})` : '';
			return `
        <li class="tl-item">
            <span class="tl-icon ${claseColor}" aria-hidden="true">${iconoStr}</span>
            <div class="tl-body">
                <div class="tl-title">${escaparHTML(accion)}</div>
                <div class="tl-meta">
                    <span>${escaparHTML(h.usuario)}${rol}</span>
                    <time datetime="${escaparHTML(h.created_at)}" title="${fechaFormat}">${tiempoRelativoDetalle(h.created_at)}</time>
                </div>
                ${h.comentario ? `<p class="tl-comment">${escaparHTML(h.comentario)}</p>` : ''}
            </div>
        </li>
        `;
		})
		.join('');
}

function tiempoRelativoDetalle(iso) {
	const d = new Date(iso);
	if (isNaN(d.getTime())) return '—';
	const min = Math.floor(Math.max(0, Date.now() - d.getTime()) / 60000);
	if (min < 1) return 'hace un momento';
	if (min < 60) return `hace ${min} min`;
	const h = Math.floor(min / 60);
	if (h < 24) return `hace ${h} h`;
	const dias = Math.floor(h / 24);
	return dias === 1 ? 'ayer' : `hace ${dias} días`;
}

/* =========================================================================
   MÓDULO 3 — Estado y técnico desde el detalle
   Cada cambio de estado pide comentario (mínimo 10 caracteres) y solo se
   permiten las transiciones válidas. El servidor vuelve a validar.
   ========================================================================= */
let ticketDetalleActual = null; // { id, codigo, estado, tecnico }
let cambioEstadoPendiente = null; // datos a enviar cuando se confirme el comentario

const TRANSICIONES_DETALLE = {
	Abierto: ['En proceso'],
	'En proceso': ['Resuelto'],
	Resuelto: ['Cerrado', 'En proceso'],
	Cerrado: []
};
const MIN_COMENTARIO_DETALLE = 10;

async function cargarTecnicosDetalle(tecnicoActual) {
	const selTec = document.getElementById('property-technician');
	if (!selTec) return;
	try {
		const res = await fetch('/api/tecnicos');
		if (!res.ok) {
			// Solicitante u otro rol sin permiso: solo se muestra el técnico actual
			selTec.innerHTML = '';
			selTec.add(new Option(tecnicoActual || 'Sin asignar', tecnicoActual || 'Sin asignar'));
			selTec.disabled = true;
			return;
		}
		const tecnicos = (await res.json()).tecnicos || [];
		selTec.innerHTML = '';
		if (!tecnicoActual) selTec.add(new Option('Sin asignar', 'Sin asignar'));
		// MÓDULO 4: se indica quién no registró su WhatsApp (el servidor no permite asignarle)
		tecnicos.forEach((t) => {
			const sinWa =
				(t.tiene_whatsapp === 0 || t.tiene_whatsapp === false) && t.nombre !== tecnicoActual;
			selTec.add(
				new Option(sinWa ? `${t.nombre} · sin WhatsApp (no se puede asignar)` : t.nombre, t.nombre)
			);
		});
		selTec.value = tecnicoActual || 'Sin asignar';
	} catch (e) {
		console.error('No se pudieron cargar los técnicos', e);
	}
}

function motivoCambioNoPermitido(estadoNuevo, tecnico) {
	const actual = ticketDetalleActual ? ticketDetalleActual.estado : null;
	if (!actual || estadoNuevo === actual) return '';
	const permitidos = TRANSICIONES_DETALLE[actual] || [];
	if (!permitidos.length) return 'El ticket está cerrado; ya no admite cambios de estado.';
	if (!permitidos.includes(estadoNuevo)) {
		return `No se puede pasar de ${actual} a ${estadoNuevo}. Desde ${actual} solo se permite: ${permitidos.join(' o ')}.`;
	}
	if (estadoNuevo === 'En proceso' && !tecnico)
		return 'Primero asigna un técnico para pasar el ticket a En proceso.';
	return '';
}

function restaurarSelectEstado() {
	const sel = document.getElementById('property-status');
	if (sel && ticketDetalleActual) sel.value = ticketDetalleActual.estado;
}

function abrirModalComentarioEstado(datos) {
	const modal = document.getElementById('status-modal');
	if (!modal) return;
	cambioEstadoPendiente = datos;
	const desde = document.getElementById('modal-status-from');
	const hacia = document.getElementById('modal-status-to');
	desde.textContent = ticketDetalleActual.estado;
	desde.className = `badge ${CLASE_ESTADO_DET[ticketDetalleActual.estado] || ''}`;
	hacia.textContent = datos.estado;
	hacia.className = `badge ${CLASE_ESTADO_DET[datos.estado] || ''}`;
	const extra = document.getElementById('modal-extra');
	const cambiaTecnico = datos.tecnico && datos.tecnico !== ticketDetalleActual.tecnico;
	extra.hidden = !cambiaTecnico;
	extra.textContent = cambiaTecnico ? `También se asignará el ticket a ${datos.tecnico}.` : '';
	const comentario = document.getElementById('status-comment');
	comentario.value = '';
	comentario.removeAttribute('aria-invalid');
	document.getElementById('status-comment-count').textContent = '0';
	document.getElementById('status-comment-error').textContent = '';
	modal.hidden = false;
	comentario.focus();
}

function cerrarModalComentarioEstado() {
	const modal = document.getElementById('status-modal');
	if (modal) modal.hidden = true;
	cambioEstadoPendiente = null;
	restaurarSelectEstado();
}

async function enviarCambiosTicket(ticketId, datos) {
	const formPanel = document.getElementById('ticket-properties');
	const btnSave = formPanel ? formPanel.querySelector('.save-button') : null;
	if (btnSave) {
		btnSave.disabled = true;
		btnSave.innerHTML = `<span>...</span>Guardando`;
	}
	try {
		const res = await fetch(`/api/tickets/${ticketId}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(datos)
		});
		if (res.ok) {
			mostrarToast(
				datos.comentario
					? `Estado cambiado a ${datos.estado}. Registrado en el historial.`
					: 'Ticket actualizado correctamente.'
			);
			cargarDetalleTicket(ticketId);
			return true;
		}
		let msg = 'Error al actualizar.';
		try {
			const err = await res.json();
			msg = err.error || err.msg || msg;
		} catch (e) {
			/* respuesta sin JSON */
		}
		mostrarToast(msg);
		restaurarSelectEstado();
		return false;
	} catch (error) {
		mostrarToast('Error de conexión al guardar cambios.');
		return false;
	} finally {
		if (btnSave) {
			btnSave.disabled = false;
			btnSave.innerHTML = `<span>▣</span>Guardar cambios`;
		}
	}
}

/* =========================================================================
   ACTUALIZAR TICKET (Panel Lateral Derecho)
   ========================================================================= */
function configurarEventosPanelDerecho(ticketId) {
	const formPanel = document.getElementById('ticket-properties');

	if (formPanel) {
		formPanel.addEventListener('submit', async (e) => {
			e.preventDefault();

			const estadoNuevo = document.getElementById('property-status')?.value;
			const prioNueva = document.getElementById('property-priority')?.value;
			const catNueva = document.getElementById('property-category')?.value;
			let tecNuevo = document.getElementById('property-technician')?.value;

			if (tecNuevo === 'Sin asignar') tecNuevo = null;

			const datos = {
				estado: estadoNuevo,
				prioridad: prioNueva,
				categoria: catNueva,
				tecnico: tecNuevo
			};

			// MÓDULO 3: si cambia el estado, primero validar y pedir el comentario
			if (ticketDetalleActual && estadoNuevo !== ticketDetalleActual.estado) {
				const motivo = motivoCambioNoPermitido(estadoNuevo, tecNuevo);
				if (motivo) {
					mostrarToast(motivo);
					restaurarSelectEstado();
					return;
				}
				abrirModalComentarioEstado(datos);
				return;
			}

			await enviarCambiosTicket(ticketId, datos);
		});
	}

	// MÓDULO 3: confirmar el cambio de estado con el comentario obligatorio
	const statusForm = document.getElementById('status-form');
	const statusComment = document.getElementById('status-comment');
	if (statusForm && statusComment) {
		statusComment.addEventListener('input', () => {
			document.getElementById('status-comment-count').textContent = statusComment.value.length;
			if (statusComment.value.trim().length >= MIN_COMENTARIO_DETALLE) {
				document.getElementById('status-comment-error').textContent = '';
				statusComment.removeAttribute('aria-invalid');
			}
		});
		statusForm.addEventListener('submit', async (e) => {
			e.preventDefault();
			const comentario = statusComment.value.trim();
			if (comentario.length < MIN_COMENTARIO_DETALLE) {
				document.getElementById('status-comment-error').textContent =
					`El comentario es obligatorio (mínimo ${MIN_COMENTARIO_DETALLE} caracteres).`;
				statusComment.setAttribute('aria-invalid', 'true');
				statusComment.focus();
				return;
			}
			if (!cambioEstadoPendiente) return;
			const datos = { ...cambioEstadoPendiente, comentario };
			const ok = await enviarCambiosTicket(ticketId, datos);
			if (ok) {
				document.getElementById('status-modal').hidden = true;
				cambioEstadoPendiente = null;
				document.querySelector('[data-tab="history"]')?.click();
			} else {
				document.getElementById('status-comment-error').textContent =
					'No se guardó el cambio. Revisa el mensaje y vuelve a intentarlo.';
			}
		});
		document.getElementById('status-modal')?.addEventListener('click', (e) => {
			if (e.target.id === 'status-modal' || e.target.closest('[data-close]'))
				cerrarModalComentarioEstado();
		});
		document.addEventListener('keydown', (e) => {
			const modal = document.getElementById('status-modal');
			if (e.key === 'Escape' && modal && !modal.hidden) cerrarModalComentarioEstado();
		});
	}

	// MÓDULO 3: "Cambiar estado" rápido desde Acciones
	const quickStatus = document.getElementById('quick-status');
	if (quickStatus) {
		quickStatus.addEventListener('change', () => {
			const valor = quickStatus.value;
			quickStatus.value = '';
			if (!valor) return;
			const selStatus = document.getElementById('property-status');
			if (selStatus) selStatus.value = valor;
			formPanel?.requestSubmit();
		});
	}

	// MÓDULO 3: "Asignar a otro técnico" lleva al selector de técnico
	document.querySelector('[data-action="assign"]')?.addEventListener('click', () => {
		const selTec = document.getElementById('property-technician');
		if (!selTec) return;
		selTec.focus();
		selTec.scrollIntoView({ behavior: 'smooth', block: 'center' });
		mostrarToast('Elige el técnico y pulsa "Guardar cambios".');
	});

	document.querySelectorAll('.tab').forEach((tab) => {
		tab.addEventListener('click', () => {
			document.querySelectorAll('.tab').forEach((item) => {
				item.classList.toggle('active', item === tab);
				item.setAttribute('aria-selected', String(item === tab));
			});
			document.querySelectorAll('.tab-content').forEach((content) => (content.hidden = true));
			const panel = document.getElementById(`tab-${tab.dataset.tab}`);
			if (panel) panel.hidden = false;
		});
	});

	// MÓDULO 3: "Cerrar ticket" solo desde Resuelto (pide comentario)
	const btnCerrar = document.getElementById('close-ticket');
	if (btnCerrar) {
		btnCerrar.addEventListener('click', () => {
			if (!ticketDetalleActual) return;
			if (ticketDetalleActual.estado === 'Cerrado') {
				mostrarToast('El ticket ya está cerrado.');
				return;
			}
			if (ticketDetalleActual.estado !== 'Resuelto') {
				mostrarToast('Para cerrar el ticket primero debe estar en estado Resuelto.');
				return;
			}
			const selStatus = document.getElementById('property-status');
			if (selStatus) {
				selStatus.value = 'Cerrado';
				formPanel?.requestSubmit();
			}
		});
	}
}

/* =========================================================================
   Evidencias: agregar fotos desde el detalle (POST /api/tickets/<id>/evidencias)
   ========================================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const idTicket = new URLSearchParams(window.location.search).get('id');
	const input = document.getElementById('evidence-input');
	const zona = input ? input.closest('.upload-zone') : null;
	if (!idTicket || !input) return;

	async function subir(archivos) {
		const fotos = [...archivos].filter((f) => /^image\/(jpeg|png|webp)$/.test(f.type));
		if (!fotos.length) {
			mostrarToast('Solo se aceptan imágenes JPG, PNG o WEBP.');
			return;
		}
		const datos = new FormData();
		fotos.forEach((f) => datos.append('fotos', f));
		mostrarToast(`Subiendo ${fotos.length} foto(s)...`);
		try {
			const res = await fetch(`/api/tickets/${idTicket}/evidencias`, {
				method: 'POST',
				body: datos,
				credentials: 'same-origin'
			});
			const r = await res.json().catch(() => ({}));
			mostrarToast(r.mensaje || r.error || 'No se pudo subir la foto.');
			if (res.ok) cargarDetalleTicket(idTicket);
		} catch (e) {
			mostrarToast('No se pudo conectar con el servidor.');
		} finally {
			input.value = '';
		}
	}

	input.addEventListener('change', () => input.files.length && subir(input.files));
	if (zona) {
		['dragenter', 'dragover'].forEach((ev) =>
			zona.addEventListener(ev, (e) => {
				e.preventDefault();
				zona.classList.add('dragging');
			})
		);
		['dragleave', 'drop'].forEach((ev) =>
			zona.addEventListener(ev, (e) => {
				e.preventDefault();
				zona.classList.remove('dragging');
			})
		);
		zona.addEventListener(
			'drop',
			(e) => e.dataTransfer?.files?.length && subir(e.dataTransfer.files)
		);
	}
});

/* =========================================================================
   Pestaña Archivos: lista de las fotos de evidencia del ticket
   ========================================================================= */
function renderizarArchivos(evidencias) {
	const lista = document.getElementById('file-list');
	if (!lista) return;
	if (!evidencias.length) {
		lista.innerHTML =
			'<li class="text-muted"><small>Este ticket no tiene archivos adjuntos.</small></li>';
		return;
	}
	lista.innerHTML = evidencias
		.map(
			(f) => `
        <li><span>▧ ${escaparHTML(f.nombre)}</span>
            <small>${f.tamano_bytes ? Math.round(f.tamano_bytes / 1024) + ' KB' : ''}</small>
            <a href="${f.imagen_url}" target="_blank" rel="noopener">Ver</a></li>`
		)
		.join('');
}

/* =========================================================================
   Pestaña Tareas (GET/POST /api/tickets/<id>/tareas, PUT/DELETE /api/tareas/<id>)
   ========================================================================= */
document.addEventListener('DOMContentLoaded', () => {
	const idTicket = new URLSearchParams(window.location.search).get('id');
	const lista = document.getElementById('task-list');
	const form = document.getElementById('task-form');
	const input = document.getElementById('task-text');
	if (!idTicket || !lista || !form) return;
	let puedeEditar = false;

	function pintar(tareas) {
		if (!tareas.length) {
			lista.innerHTML =
				'<li class="text-muted"><small>Aún no hay tareas para este ticket.</small></li>';
			return;
		}
		lista.innerHTML = tareas
			.map(
				(t) => `
            <li data-id="${t.id}">
                <label><input type="checkbox" ${t.completada ? 'checked' : ''} ${puedeEditar ? '' : 'disabled'}>
                    ${t.completada ? `<s>${escaparHTML(t.descripcion)}</s>` : escaparHTML(t.descripcion)}</label>
                <span>${t.completada ? `Hecha · ${escaparHTML(t.completada_por || '')}` : 'Pendiente'}</span>
                ${puedeEditar ? '<button type="button" class="icon-button" data-borrar title="Eliminar tarea" aria-label="Eliminar tarea">×</button>' : ''}
            </li>`
			)
			.join('');
	}

	async function pedir(url, opciones = {}) {
		const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opciones });
		const datos = await res.json().catch(() => ({}));
		if (!res.ok) throw new Error(datos.error || 'No se pudo completar la acción.');
		return datos;
	}

	async function cargar() {
		try {
			const datos = await pedir(`/api/tickets/${idTicket}/tareas`);
			puedeEditar = datos.puede_editar;
			form.hidden = !puedeEditar;
			pintar(datos.tareas);
		} catch (e) {
			lista.innerHTML = `<li class="text-muted"><small>${escaparHTML(e.message)}</small></li>`;
		}
	}

	form.addEventListener('submit', async (e) => {
		e.preventDefault();
		const descripcion = input.value.trim();
		if (descripcion.length < 3) {
			mostrarToast('Describe la tarea (mínimo 3 caracteres).');
			return;
		}
		try {
			const datos = await pedir(`/api/tickets/${idTicket}/tareas`, {
				method: 'POST',
				body: JSON.stringify({ descripcion })
			});
			input.value = '';
			pintar(datos.tareas);
			mostrarToast(datos.mensaje);
		} catch (err) {
			mostrarToast(err.message);
		}
	});

	lista.addEventListener('change', async (e) => {
		if (e.target.type !== 'checkbox') return;
		const id = e.target.closest('li').dataset.id;
		try {
			const datos = await pedir(`/api/tareas/${id}`, {
				method: 'PUT',
				body: JSON.stringify({ completada: e.target.checked })
			});
			pintar(datos.tareas);
			if (e.target.checked) cargarHistorial(idTicket);
		} catch (err) {
			mostrarToast(err.message);
			cargar();
		}
	});

	lista.addEventListener('click', async (e) => {
		if (!e.target.closest('[data-borrar]')) return;
		const id = e.target.closest('li').dataset.id;
		if (!confirm('¿Eliminar esta tarea?')) return;
		try {
			const datos = await pedir(`/api/tareas/${id}`, { method: 'DELETE' });
			pintar(datos.tareas);
		} catch (err) {
			mostrarToast(err.message);
		}
	});

	// Botón "Agregar tarea" del panel Acciones
	document.querySelector('[data-action="task"]')?.addEventListener('click', () => {
		document.querySelector('.tab[data-tab="tasks"]')?.click();
		if (puedeEditar) {
			input.focus();
		} else {
			mostrarToast('Solo el administrador o el técnico asignado pueden agregar tareas.');
		}
	});

	// Clip del cuadro de comentario: adjunta una foto al ticket
	document.getElementById('reply-file')?.addEventListener('change', (e) => {
		const evidencia = document.getElementById('evidence-input');
		if (!evidencia || !e.target.files.length) return;
		const dt = new DataTransfer();
		[...e.target.files].forEach((f) => dt.items.add(f));
		evidencia.files = dt.files;
		evidencia.dispatchEvent(new Event('change'));
		e.target.value = '';
	});

	cargar();
});

// =========================================================================
// RELOJ SLA EN VIVO EN DETALLE DE TICKET (1s visual + 15s sincronización)
// =========================================================================
document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const ticketId = params.get("id");
  const barraSla = document.getElementById("sla-progress-bar");
  if (!ticketId || !barraSla) return;

  let ticketEnVivo = null;

  const headersSla = () => {
    const headers = { "Content-Type": "application/json" };
    const token = localStorage.getItem("token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  };

  const formatearSegundosSla = (segTotales) => {
    const s = Math.max(0, Math.floor(segTotales));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}h ${m}m ${sec}s`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
  };

  const pintarSlaDetalleVivo = (t) => {
    if (!t || !t.created_at || !t.fecha_limite) return;

    const creadoMs = Date.parse(t.created_at);
    const limiteMs = Date.parse(t.fecha_limite);
    if (isNaN(creadoMs) || isNaN(limiteMs)) return;

    const ahoraMs = Date.now();
    const plazoSeg = Math.max((limiteMs - creadoMs) / 1000, 1);
    const transcurridoSeg = Math.max((ahoraMs - creadoMs) / 1000, 0);
    const pct = Math.min(Math.round((transcurridoSeg / plazoSeg) * 100), 100);

    const elLimit = document.getElementById("sla-limit");
    if (elLimit) {
      const minsTot = t.sla_minutos || Math.round(plazoSeg / 60);
      const hLim = Math.floor(minsTot / 60);
      const mLim = minsTot % 60;
      elLimit.textContent = mLim > 0 ? `${hLim}h ${mLim}m` : `${hLim}h`;
    }

    const elElapsed = document.querySelector(".sla-stats .time-danger span");
    if (elElapsed && t.estado !== "Resuelto" && t.estado !== "Cerrado") {
      elElapsed.textContent = formatearSegundosSla(Math.min(transcurridoSeg, plazoSeg));
    }

    barraSla.style.width = `${pct}%`;
    const elPercent = document.getElementById("sla-percent");
    if (elPercent) elPercent.textContent = `${pct}%`;

    const elTitle = document.getElementById("sla-title");
    const elSmall = elTitle ? elTitle.parentElement.querySelector("small") : null;
    const elNote = document.getElementById("sla-note");
    const box = document.querySelector(".sla-warning-box");
    const icono = box ? box.querySelector("span") : null;

    if (t.estado === "Resuelto" || t.estado === "Cerrado") {
      const cumplido = t.semaforo === "cumplido";
      if (elTitle) elTitle.textContent = cumplido ? "SLA Cumplido" : "Resuelto fuera de plazo";
      if (elSmall) elSmall.textContent = cumplido ? "Se resolvió dentro del plazo" : "Se resolvió después del plazo";
      barraSla.style.background = cumplido ? "#14b88a" : "#f04452";
      if (box) {
        box.style.background = cumplido ? "#e8f7ef" : "#fdecec";
        box.style.color = cumplido ? "#12805c" : "#b42318";
      }
      if (icono) {
        icono.textContent = cumplido ? "✓" : "!";
        icono.style.background = cumplido ? "#12805c" : "#b42318";
      }
      return;
    }

    if (ahoraMs > limiteMs) {
      const excesoSeg = (ahoraMs - limiteMs) / 1000;
      if (elTitle) elTitle.textContent = "SLA Vencido";
      if (elSmall) elSmall.textContent = `Venció hace ${formatearSegundosSla(excesoSeg)}`;
      if (elNote) elNote.textContent = `Plazo superado hace ${formatearSegundosSla(excesoSeg)}.`;
      barraSla.style.background = "#f04452";
      if (box) {
        box.style.background = "#fdecec";
        box.style.color = "#b42318";
      }
      if (icono) {
        icono.textContent = "!";
        icono.style.background = "#b42318";
      }
    } else if (transcurridoSeg >= plazoSeg * 0.75) {
      const restanteSeg = (limiteMs - ahoraMs) / 1000;
      if (elTitle) elTitle.textContent = "SLA Por vencer";
      if (elSmall) elSmall.textContent = `Quedan ${formatearSegundosSla(restanteSeg)}`;
      if (elNote) elNote.textContent = `Quedan ${formatearSegundosSla(restanteSeg)} para el vencimiento.`;
      barraSla.style.background = "#f0a500";
      if (box) {
        box.style.background = "#fff6e0";
        box.style.color = "#9a6700";
      }
      if (icono) {
        icono.textContent = "!";
        icono.style.background = "#9a6700";
      }
    } else {
      const restanteSeg = (limiteMs - ahoraMs) / 1000;
      if (elTitle) elTitle.textContent = "SLA En tiempo";
      if (elSmall) elSmall.textContent = `Quedan ${formatearSegundosSla(restanteSeg)}`;
      if (elNote) elNote.textContent = `Quedan ${formatearSegundosSla(restanteSeg)} dentro del plazo.`;
      barraSla.style.background = "#14b88a";
      if (box) {
        box.style.background = "#e8f7ef";
        box.style.color = "#12805c";
      }
      if (icono) {
        icono.textContent = "✓";
        icono.style.background = "#12805c";
      }
    }
  };

  const sincronizarDetalleSla = async () => {
    try {
      const resAlertas = await fetch("/api/sla/verificar-alertas", {
        method: "POST",
        credentials: "same-origin",
        headers: headersSla(),
      });
      if (resAlertas.ok) {
        const dataAlertas = await resAlertas.json();
        const huboEventos = (dataAlertas.escalados?.length > 0) || (dataAlertas.alertados?.length > 0);
        if (huboEventos) {
          if ("Notification" in window && Notification.permission === "granted") {
            dataAlertas.escalados?.forEach((t) => {
              new Notification(`🚨 SLA Vencido y Escalado: ${t.codigo}`, {
                body: `${t.asunto} superó el plazo y subió a prioridad Alta.`,
                tag: `sla-vencido-${t.id}`,
              });
            });
            dataAlertas.alertados?.forEach((t) => {
              new Notification(`⚠️ SLA por vencer: ${t.codigo}`, {
                body: `Quedan ${t.restantes} min para resolver «${t.asunto}».`,
                tag: `sla-por-vencer-${t.id}`,
              });
            });
          }
          if (typeof cargarHistorial === "function") cargarHistorial(ticketId);
        }
      }

      const resp = await fetch(`/api/tickets/${ticketId}`, {
        credentials: "same-origin",
        headers: headersSla(),
      });
      if (resp.ok) {
        const data = await resp.json();
        ticketEnVivo = data.ticket;
        pintarSlaDetalleVivo(ticketEnVivo);

        const tagPrio = document.getElementById("ticket-priority-tag");
        if (tagPrio && ticketEnVivo?.prioridad) {
          tagPrio.textContent = `▥ ${ticketEnVivo.prioridad}`;
        }
        const selectPrio = document.getElementById("property-priority");
        if (selectPrio && ticketEnVivo?.prioridad) {
          selectPrio.value = ticketEnVivo.prioridad;
        }
      }
    } catch (e) {
      console.warn("Error sincronizando SLA del detalle:", e);
    }
  };

  setInterval(() => {
    if (ticketEnVivo) pintarSlaDetalleVivo(ticketEnVivo);
  }, 1000);

  setInterval(sincronizarDetalleSla, 15000);
  sincronizarDetalleSla();
});