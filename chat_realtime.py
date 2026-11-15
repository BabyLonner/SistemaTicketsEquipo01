import time

from flask import Blueprint, g, jsonify

from db import consultar
from tickets import login_requerido, ticket_de_chat

chat_rt_bp = Blueprint("chat_rt", __name__)

SEGUNDOS_ESCRIBIENDO = 3
_salas_escribiendo = {}


def _quitar_vencidos(sala):
    limite = time.time() - SEGUNDOS_ESCRIBIENDO
    for usuario_id in [u for u, datos in sala.items() if datos["momento"] < limite]:
        sala.pop(usuario_id, None)


def _ultimo_comentario(ticket_id):
    fila = consultar(
        """SELECT MAX(id) AS ultimo
             FROM ticket_historial
            WHERE ticket_id = %s AND tipo = 'COMENTARIO'""",
        (ticket_id,),
        uno=True,
    )
    return int(fila["ultimo"] or 0)


@chat_rt_bp.post("/api/tickets/<int:ticket_id>/escribiendo")
@login_requerido
def marcar_escribiendo(ticket_id):
    _, error = ticket_de_chat(ticket_id)
    if error:
        return error
    sala = _salas_escribiendo.setdefault(ticket_id, {})
    sala[g.usuario["id"]] = {"nombre": g.usuario["nombre"], "momento": time.time()}
    return jsonify(ok=True)


@chat_rt_bp.delete("/api/tickets/<int:ticket_id>/escribiendo")
@login_requerido
def dejar_de_escribir(ticket_id):
    _, error = ticket_de_chat(ticket_id)
    if error:
        return error
    _salas_escribiendo.get(ticket_id, {}).pop(g.usuario["id"], None)
    return jsonify(ok=True)


@chat_rt_bp.get("/api/tickets/<int:ticket_id>/estado-chat")
@login_requerido
def estado_chat(ticket_id):
    _, error = ticket_de_chat(ticket_id)
    if error:
        return error
    sala = _salas_escribiendo.get(ticket_id, {})
    _quitar_vencidos(sala)
    escribiendo = [
        datos["nombre"]
        for usuario_id, datos in sala.items()
        if usuario_id != g.usuario["id"]
    ]
    return jsonify(
        escribiendo=escribiendo, ultimo_comentario=_ultimo_comentario(ticket_id)
    )
