import time
from flask import Blueprint, g, jsonify

chat_rt_bp = Blueprint("chat_rt", __name__)

_USUARIOS_ESCRIBIENDO = {}
_ULTIMO_COMENTARIO_TS = {}
TTL_ESCRIBIENDO = 2.5

def emitir_comentario_ticket(ticket_id, payload, destinatarios_ids=None):
    t_id = int(ticket_id)
    _ULTIMO_COMENTARIO_TS[t_id] = time.time()
    sala = _USUARIOS_ESCRIBIENDO.get(t_id, {})
    for k, v in list(sala.items()):
        if v[0] == payload.get("usuario"):
            sala.pop(k, None)

@chat_rt_bp.post("/api/tickets/<int:ticket_id>/escribiendo")
def api_marcar_escribiendo(ticket_id):
    u = g.get("usuario_token")
    if not u:
        return jsonify(error="No autorizado"), 401

    ahora = time.time()
    t_id = int(ticket_id)

    sala = _USUARIOS_ESCRIBIENDO.setdefault(t_id, {})
    sala[int(u["id"])] = (u["nombre"], u.get("rol", ""), ahora)

    for k in [k for k, v in sala.items() if ahora - v[2] > TTL_ESCRIBIENDO]:
        sala.pop(k, None)

    return jsonify(ok=True)

@chat_rt_bp.get("/api/tickets/<int:ticket_id>/estado-chat")
def api_estado_chat(ticket_id):
    u = g.get("usuario_token")
    if not u:
        return jsonify(error="No autorizado"), 401

    ahora = time.time()
    t_id = int(ticket_id)

    sala = _USUARIOS_ESCRIBIENDO.get(t_id, {})

    activos = [
        {"usuario": nombre, "rol": rol}
        for uid, (nombre, rol, ts) in list(sala.items())
        if ahora - ts <= TTL_ESCRIBIENDO and int(uid) != int(u["id"])
    ]

    ultimo_ts = _ULTIMO_COMENTARIO_TS.get(t_id, 0)
    return jsonify(ok=True, escribiendo=activos, ultimo_comentario_ts=ultimo_ts)