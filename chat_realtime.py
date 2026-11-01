import json
import queue

from flask import Blueprint, Response, g, jsonify

chat_rt_bp = Blueprint("chat_rt", __name__)

_suscriptores_sse = {}

def emitir_comentario_ticket(ticket_id, payload, destinatarios_ids=None):
    t_id = str(ticket_id)
    if t_id in _suscriptores_sse:
        evento = f"event: nuevo_comentario\ndata: {json.dumps(payload)}\n\n"
        for q in _suscriptores_sse[t_id]:
            try:
                q.put_nowait(evento)
            except queue.Full:
                pass

@chat_rt_bp.post("/api/tickets/<int:ticket_id>/escribiendo")
def api_marcar_escribiendo(ticket_id):
    from auth import validar_peticion
    validar_peticion()
    u = g.get("usuario_token")
    if not u:
        return jsonify(error="No autorizado"), 401

    t_id = str(ticket_id)
    if t_id in _suscriptores_sse:
        payload = {"usuario": u["nombre"], "ticket_id": ticket_id}
        evento = f"event: usuario_escribiendo\ndata: {json.dumps(payload)}\n\n"
        for q in _suscriptores_sse[t_id]:
            try:
                q.put_nowait(evento)
            except queue.Full:
                pass
    return jsonify(ok=True)

@chat_rt_bp.get("/api/tickets/<int:ticket_id>/stream")
def sse_stream(ticket_id):
    t_id = str(ticket_id)
    
    def generar_eventos():
        q = queue.Queue(maxsize=20)
        _suscriptores_sse.setdefault(t_id, []).append(q)
        try:
            yield "data: conectado\n\n"
            while True:
                try:
                    mensaje = q.get(timeout=15)
                    yield mensaje
                except queue.Empty:
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            pass
        finally:
            if t_id in _suscriptores_sse and q in _suscriptores_sse[t_id]:
                _suscriptores_sse[t_id].remove(q)

    return Response(generar_eventos(), mimetype="text/event-stream")