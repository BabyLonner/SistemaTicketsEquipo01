"""
MÓDULO 5 — Chat y Comentarios en Tiempo Real con Flask-SocketIO.
"""

from flask import session
from flask_socketio import SocketIO, emit, join_room, leave_room

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def inicializar_socketio(app):
    socketio.init_app(app)
    return socketio


def emitir_comentario_ticket(ticket_id, payload):
    """Emite un nuevo comentario en tiempo real a todos los que estén viendo el ticket."""
    socketio.emit("nuevo_comentario", payload, to=f"ticket_{ticket_id}")


@socketio.on("unirse_ticket")
def handle_unirse_ticket(data):
    ticket_id = data.get("ticket_id")
    if not ticket_id:
        return
    room = f"ticket_{ticket_id}"
    join_room(room)
    emit(
        "estado_sala",
        {
            "ticket_id": ticket_id,
            "usuario": session.get("nombre", "Usuario"),
            "mensaje": "Conectado al canal en tiempo real",
        },
        to=room,
    )


@socketio.on("salir_ticket")
def handle_salir_ticket(data):
    ticket_id = data.get("ticket_id")
    if ticket_id:
        leave_room(f"ticket_{ticket_id}")


@socketio.on("escribiendo_ticket")
def handle_escribiendo(data):
    ticket_id = data.get("ticket_id")
    if not ticket_id:
        return
    emit(
        "usuario_escribiendo",
        {
            "ticket_id": ticket_id,
            "usuario": session.get("nombre", "Alguien"),
            "rol": session.get("rol", ""),
        },
        to=f"ticket_{ticket_id}",
        include_self=False,
    )
